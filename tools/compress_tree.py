#!/usr/bin/env python3
"""
compress_tree.py — uiautomator XML 节点树压缩器（离线，无依赖）

把 AccessibilityService / uiautomator dump 出的原始节点树，压缩成 LLM 可消费的
紧凑表示：合并「文字锚点 + 可点容器」、丢弃纯布局层、分配短 ID、层级缩进（≤3 层）。

用法:
    python compress_tree.py <dump.xml> [--max-depth 3] [--show-dropped]
    python compress_tree.py --self-test

输出:
    1) 压缩后的节点条目（缩进 = 层级，超出 max-depth 拍平）
    2) 反查表：短 ID -> (resource-id, text, class)，供执行层定位真实节点

保留规则（任务 B2 核心要求）:
    - clickable / scrollable / long-clickable / EditText(editable) 节点
    - 上述节点的「直接文字来源」（相邻后代里的 text / content-desc）
丢弃规则:
    - 纯布局容器（无文字、不可交互）
    - bounds 面积为 0 或完全超出屏幕的节点
    - 同一文字锚点下的重复嵌套包装层（保留最外层）
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET

MAX_DEPTH_DEFAULT = 3
ANCHOR_LOOKAHEAD = 2  # 文字锚点只找「可点容器」往下的最近 2 层后代（直接文字来源）

# ---------------------------------------------------------------- 解析

def parse_bounds(s):
    """'[l,t][r,b]' -> (l, t, r, b)；解析失败返回 None"""
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", s or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def bounds_area(b):
    if not b:
        return 0
    l, t, r, bb = b
    return max(0, r - l) * max(0, bb - t)


def node_flags(a):
    """从节点属性推导保留标志集（字符串，按固定顺序）"""
    flags = []
    if a.get("clickable") == "true":
        flags.append("clickable")
    if a.get("scrollable") == "true":
        flags.append("scrollable")
    if a.get("long-clickable") == "true":
        flags.append("long-clickable")
    if "EditText" in a.get("class", "") or a.get("editable") == "true":
        flags.append("editable")
    return flags


def is_interactive(a):
    return bool(node_flags(a))


def own_text(a):
    """节点自身的文字来源：text 优先，content-desc 兜底"""
    t = a.get("text")
    if t and t.strip():
        return t
    cd = a.get("content-desc")
    if cd and cd.strip():
        return cd
    return None


def screen_bounds(root_elem):
    """以根节点的第一个子节点（顶层 window decor）的 bounds 作为可见屏幕范围"""
    for child in root_elem:
        b = parse_bounds(child.get("bounds"))
        if b:
            return b
    return None


def within_screen(b, screen):
    """完全在屏幕外 -> False；与屏幕有交集即可（含跨界）"""
    if not b or not screen:
        return False if not b else True
    l, t, r, bb = b
    sl, st, sr, sb = screen
    return r > sl and bb > st and l < sr and t < sb


# ---------------------------------------------------------------- 压缩

class Entry:
    __slots__ = ("id", "text", "flags", "cls", "rid", "depth", "flattened", "anchor_cls")

    def __init__(self, eid, text, flags, cls, rid, depth, flattened, anchor_cls=None):
        self.id = eid
        self.text = text or ""
        self.flags = flags
        self.cls = cls
        self.rid = rid or ""
        self.depth = depth
        self.flattened = flattened
        self.anchor_cls = anchor_cls

    def render(self):
        label = self.text if self.text else "(no text)"
        flags = "|".join(self.flattened + self.flags) if self.flattened else "|".join(self.flags)
        flags = flags or "-"
        rid = f" id={self.rid}" if self.rid else ""
        return f"[{self.id}] {label} | {flags} | {self.cls}{rid}"


def compress(root_elem, max_depth=MAX_DEPTH_DEFAULT):
    """主流程：返回 (entries, reverse_lookup, stats)"""
    screen = screen_bounds(root_elem)
    stats = {"total": 0, "kept": 0, "dropped_noflags": 0, "dropped_bounds": 0,
             "dropped_wrapper": 0, "merged_anchors": 0, "flattened": 0}

    # 第一遍：收集所有节点（含父引用），按 DFS 顺序
    nodes = []  # (elem, parent_index)
    for child in root_elem:
        stack = [(child, -1)]
        while stack:
            n, p = stack.pop()
            idx = len(nodes)
            nodes.append((n, p))
            for c in reversed(list(n)):
                stack.append((c, idx))

    # 第二遍：判保留。先算出每个交互节点的文字锚点
    def find_anchor(elem, depth=0):
        """在 elem 往下的 ANCHOR_LOOKAHEAD 条边内找第一个非交互的文字节点"""
        if depth > ANCHOR_LOOKAHEAD:
            return None
        a = elem.attrib
        t = own_text(a)
        if t is not None and not is_interactive(a):
            return (t, a.get("class"))
        for c in elem:
            r = find_anchor(c, depth + 1)
            if r:
                return r
        return None

    kept = []  # (elem, parent_kept_idx, depth, text, flags, anchor_cls)
    parent_of = {}
    for idx, (elem, p) in enumerate(nodes):
        a = elem.attrib
        b = parse_bounds(a.get("bounds"))
        # 丢弃 1：bounds 面积 0 或超出屏幕
        if bounds_area(b) <= 0 or not within_screen(b, screen):
            stats["dropped_bounds"] += 1
            continue
        flags = node_flags(a)
        if not flags:
            stats["dropped_noflags"] += 1
            continue
        # 文字锚点：自身 text/cd 优先，否则找最近的后代文字
        text = own_text(a)
        anchor_cls = None
        if text is None:
            r = find_anchor(elem)
            if r:
                text, anchor_cls = r
                stats["merged_anchors"] += 1
            else:
                text = ""
        kept.append((elem, p, text, flags, anchor_cls))

    # 第三遍：嵌套包装去重 —— 同一文字锚点下的多个交互层，保留最外层
    kept_info = {id(elem): (text, flags) for (elem, p, text, flags, anchor_cls) in kept}
    deduped = []
    for k in kept:
        elem, p, text, flags, anchor_cls = k
        # 向上沿父链找第一个已保留的交互祖先，锚点文字相同则本层是重复包装
        cur = p
        dup = False
        for _ in range(ANCHOR_LOOKAHEAD + 1):
            if cur < 0:
                break
            info = kept_info.get(id(nodes[cur][0]))
            if info is not None and info[1]:
                if info[0] == text:
                    dup = True
                break
            cur = nodes[cur][1]
        if dup:
            stats["dropped_wrapper"] += 1
            continue
        deduped.append(k)
    kept = deduped

    # 第四遍：层级（depth cap = 拍平）+ 短 ID
    node_kept_idx = {id(elem): i for i, (elem, p, text, flags, anchor_cls) in enumerate(kept)}
    kept_ancestor = {}
    for i, (elem, p, text, flags, anchor_cls) in enumerate(kept):
        cur = p
        found = None
        while cur >= 0:
            j = node_kept_idx.get(id(nodes[cur][0]))
            if j is not None:
                found = j
                break
            cur = nodes[cur][1]
        kept_ancestor[i] = found

    entries = []
    lookup = []
    depth_of = {}
    for i, (elem, p, text, flags, anchor_cls) in enumerate(kept):
        pa = kept_ancestor[i]
        d = 0 if pa is None else depth_of[pa] + 1
        flattened = d > max_depth
        if flattened:
            d = max_depth
            stats["flattened"] += 1
        depth_of[i] = d
        e = Entry(len(entries), text, flags, elem.get("class"),
                  elem.get("resource-id") or "", d, flattened, anchor_cls)
        entries.append(e)
        lookup.append({"id": e.id, "resource-id": e.rid, "text": e.text,
                       "class": e.cls, "anchor_class": anchor_cls})
        stats["kept"] += 1
    stats["total"] = len(nodes)
    return entries, lookup, stats


# ---------------------------------------------------------------- 输出

def render_tree(entries):
    out = []
    for e in entries:
        out.append("  " * e.depth + e.render())
    return "\n".join(out)


def render_lookup(lookup):
    out = ["--- reverse lookup: short ID -> real node ---"]
    for e in lookup:
        rid = e["resource-id"] or "null"
        out.append(f"[{e['id']}] rid={rid} text='{e['text']}' class={e['class']} "
                   f"anchor_class={e['anchor_class'] or '-'}")
    return "\n".join(out)


# ---------------------------------------------------------------- 自测

SELF_TEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.android.settings" content-desc="" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="com.android.settings" content-desc="" clickable="true" bounds="[0,100][1080,300]">
      <node index="0" text="Magnification" resource-id="android:id/title" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[40,120][400,200]"/>
    </node>
    <node index="1" text="" resource-id="" class="android.widget.LinearLayout" package="com.android.settings" content-desc="" clickable="true" bounds="[0,300][1080,500]">
      <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="com.android.settings" content-desc="" clickable="true" bounds="[0,300][1080,500]">
        <node index="0" text="Nested row" resource-id="" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[40,320][400,400]"/>
      </node>
    </node>
    <node index="2" text="" resource-id="" class="android.widget.FrameLayout" package="com.android.settings" content-desc="" clickable="false" bounds="[0,0][0,0]"/>
    <node index="3" text="Search settings" resource-id="com.android.settings:id/search_action_bar" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="true" bounds="[40,600][800,700]"/>
    <node index="4" text="" resource-id="" class="android.widget.EditText" package="com.android.settings" content-desc="Search box" bounds="[40,800][800,900]"/>
  </node>
</hierarchy>
"""


def self_test():
    root = ET.fromstring(SELF_TEST_XML)
    entries, lookup, stats = compress(root)
    tree = render_tree(entries)
    print(tree)
    print(render_lookup(lookup))
    assert stats["total"] == 9, stats
    # 1: Magnification 合并成一条可点条目；2: Nested row 双层包装只保留最外层
    assert len(entries) == 4, [e.render() for e in entries]
    assert entries[0].text == "Magnification" and entries[0].flags == ["clickable"], entries[0].render()
    assert entries[0].cls == "android.widget.LinearLayout" and entries[0].anchor_cls == "android.widget.TextView"
    assert entries[1].text == "Nested row" and entries[1].flags == ["clickable"]
    # 3: 零面积节点被丢
    assert "FrameLayout" not in " ".join(e.render() for e in entries)
    # 4: 自带文字的交互节点（search bar）与 content-desc 兜底（EditText）
    texts = [e.text for e in entries]
    assert "Search settings" in texts and "Search box" in texts, texts
    print("self-test PASS: merge / wrapper-dedup / zero-bounds / cd-fallback 全部符合预期")


# ---------------------------------------------------------------- 主入口

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml", nargs="?", help="uiautomator dump 的 XML 文件")
    ap.add_argument("--max-depth", type=int, default=MAX_DEPTH_DEFAULT)
    ap.add_argument("--show-dropped", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.xml:
        ap.error("需要提供 XML 文件路径，或使用 --self-test")

    root = ET.parse(args.xml).getroot()
    entries, lookup, stats = compress(root, args.max_depth)
    print(f"# {args.xml}: total={stats['total']} kept={stats['kept']} "
          f"(dropped: bounds={stats['dropped_bounds']} noflags={stats['dropped_noflags']} "
          f"wrapper={stats['dropped_wrapper']}) merged_anchors={stats['merged_anchors']} "
          f"flattened={stats['flattened']}")
    print(render_tree(entries))
    print()
    print(render_lookup(lookup))
    if args.show_dropped:
        print()
        print("--- dropped (sample, first 30) ---")
        dropped = 0
        for n in root.iter("node"):
            a = n.attrib
            b = parse_bounds(a.get("bounds"))
            if bounds_area(b) <= 0 or not node_flags(a):
                if dropped < 30:
                    print(f"drop {a.get('class')} bounds={a.get('bounds')}")
                dropped += 1
        print(f"(total dropped-ish: {dropped})")


if __name__ == "__main__":
    main()
