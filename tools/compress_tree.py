#!/usr/bin/env python3
"""
compress_tree.py — uiautomator XML 节点树压缩器 + 分层降级定位器（离线，无依赖）

把 AccessibilityService / uiautomator dump 出的原始节点树，压缩成 LLM 可消费的
紧凑表示：合并「文字锚点 + 可点容器」、丢弃纯布局层、分配短 ID、层级缩进（≤3 层），
并为每个逻辑条目生成一个 **locator 对象**（六层降级定位策略，任务 C1）。

用法:
    python compress_tree.py <dump.xml> [--max-depth 3] [--show-dropped]
    python compress_tree.py <dump.xml> --assess        # C2 新指标统计
    python compress_tree.py --self-test

输出:
    1) 压缩后的节点条目（缩进 = 层级，超出 max-depth 拍平），每条附 locator
    2) 反查表：短 ID -> locator，供执行层定位真实节点
    3) --assess: 新指标（可交互节点总数 / 可唯一指认数 / 可指认率 / 策略分布）

保留规则（任务 B2 核心要求）:
    - clickable / scrollable / long-clickable / EditText(editable) 节点
    - 上述节点的「直接文字来源」（相邻后代里的 text / content-desc）
丢弃规则:
    - 纯布局容器（无文字、不可交互）
    - bounds 面积为 0 或完全超出屏幕的节点
    - 同一文字锚点下的重复嵌套交互包装层（保留**最内层** —— 锚点向上爬命中的那个，
      与执行语义一致；B2 版保留最外层，C1 修正为最内层）

locator 六层策略（C1，唯一性一律在当前树的范围内判定）:
    L1 resource_id                —— id 存在且当前树内唯一
    L2 resource_id + text         —— id 存在但重复（用 text 消歧）
    L3 content_desc               —— 无可用 id，contentDescription 存在且唯一
    L4 text + class_name          —— 无可用 id/desc，text 唯一
    L5 text + 同类序号             —— text 重复，取第 N 个（精确匹配的 DFS 序）
    L6 结构路径（父 text + 子序号） —— 以上全无（或父链也无文字 -> no-anchor）

锚点合并（E3 附带发现 3）: 文字在子节点、可点在父节点，合并为一个逻辑条目；
locator 的文字来自锚点，并在 resolve 中写明「按 text 找到锚点后向上爬可执行节点，
爬不到用原节点兜底」—— 查找规则写进 locator，不靠执行层猜。
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET

MAX_DEPTH_DEFAULT = 3
ANCHOR_LOOKAHEAD = 2  # 文字锚点只找「可点容器」往下的最近 2 条边内的后代文字

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


def is_editable(a):
    return "EditText" in a.get("class", "") or a.get("editable") == "true"


def own_text(a):
    """节点自身的文字来源：text 优先，content-desc 兜底（展示用）"""
    t = a.get("text")
    if t and t.strip():
        return t
    cd = a.get("content-desc")
    if cd and cd.strip():
        return cd
    return None


def text_attr(a):
    """text 属性（非空才返回）—— 参与 findByText 的查找宇宙"""
    t = a.get("text")
    return t if t and t.strip() else None


def cd_attr(a):
    """content-desc 属性（非空才返回）—— 参与 findByContentDescription 的查找宇宙"""
    cd = a.get("content-desc")
    return cd if cd and cd.strip() else None


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


def collect_nodes(root_elem):
    """所有节点（含父引用），按 DFS 顺序。返回 [(elem, parent_index)]"""
    nodes = []
    for child in root_elem:
        stack = [(child, -1)]
        while stack:
            n, p = stack.pop()
            idx = len(nodes)
            nodes.append((n, p))
            for c in reversed(list(n)):
                stack.append((c, idx))
    return nodes


def compute_tree_counts(nodes):
    """当前树范围内的出现次数（唯一性判定依据）"""
    id_count, text_count, cd_count = {}, {}, {}
    for elem, _p in nodes:
        a = elem.attrib
        rid = a.get("resource-id")
        if rid:
            id_count[rid] = id_count.get(rid, 0) + 1
        t = a.get("text")
        if t and t.strip():
            text_count[t] = text_count.get(t, 0) + 1
        cd = a.get("content-desc")
        if cd and cd.strip():
            cd_count[cd] = cd_count.get(cd, 0) + 1
    return id_count, text_count, cd_count


def text_ordinals(nodes):
    """text 精确匹配的出现顺序（DFS 序）：id(elem) -> 第几个（从 0 起）"""
    seen = {}
    ordinal = {}
    for elem, _p in nodes:
        t = elem.get("text")
        if t and t.strip():
            i = seen.get(t, 0)
            ordinal[id(elem)] = i
            seen[t] = i + 1
    return ordinal


# ---------------------------------------------------------------- locator

def build_locator(elem, resolved_text, anchor_elem, counts, text_ord):
    """
    六层降级定位器。返回 locator dict（含 strategy / 信号字段 / resolve 描述）。
    elem          : 执行节点（可点容器）元素
    resolved_text : 条目文字（自身文字 或 合并后的锚点文字，可能为 None）
    anchor_elem   : 锚点元素；None 表示文字就在执行节点自身
    """
    a = elem.attrib
    id_count, text_count, cd_count = counts
    rid = a.get("resource-id") or ""
    cd = a.get("content-desc")
    if cd is not None and not cd.strip():
        cd = None
    anchor_child = anchor_elem is not None

    # L1 / L2: resource-id
    if rid:
        n = id_count.get(rid, 0)
        if n == 1:
            return {
                "strategy": "L1", "resource_id": rid,
                "resolve": f"findAccessibilityNodeInfosByViewId('{rid}') -> hits[0] 为执行节点",
            }
        t = resolved_text or ""
        return {
            "strategy": "L2", "resource_id": rid, "text": t,
            "resolve": (f"findAccessibilityNodeInfosByViewId('{rid}') 命中 {n} 个"
                        f" -> 取锚点/自身文字 == '{t}' 的那个为执行节点"),
        }

    # L3: content-desc（无可用 id 时，desc 先于 text）
    if cd is not None and cd_count.get(cd, 0) == 1:
        return {
            "strategy": "L3", "content_desc": cd,
            "resolve": f"findAccessibilityNodeInfosByContentDescription('{cd}') -> hits[0] 为执行节点",
        }

    # L4 / L5: text（自身文字或锚点文字；唯一性按精确匹配计数）
    if resolved_text:
        n = text_count.get(resolved_text, 0)
        climb = ("（文字在子节点：命中后向上爬第一个可执行节点，爬不到用原节点兜底）"
                 if anchor_child else "")
        if n == 1:
            return {
                "strategy": "L4", "text": resolved_text, "class": a.get("class"),
                "resolve": f"findAccessibilityNodeInfosByText('{resolved_text}') 唯一命中{climb}",
            }
        ord_idx = text_ord.get(id(anchor_elem if anchor_elem is not None else elem), 0)
        return {
            "strategy": "L5", "text": resolved_text, "ordinal": ord_idx,
            "class": a.get("class"),
            "resolve": (f"findAccessibilityNodeInfosByText('{resolved_text}') 按精确匹配取第 {ord_idx} 个"
                        f"（DFS 序）{climb}"),
        }

    # L6: 结构路径 —— 沿父链找最近有文字的祖先，记录子序号路径
    return None  # 调用方补充 L6（或标记 no-anchor）


def build_l6(elem, nodes, node_index, text_ord):
    """结构路径：最近的有文字祖先 + child index 路径（index 取 XML index 属性）"""
    cur = node_index
    path = []
    a = elem.attrib
    # 自身无文字，沿父链向上找锚点
    anchor_text = None
    anchor_elem = None
    while cur >= 0:
        anc = nodes[cur][0].attrib
        t = anc.get("text")
        if not t or not t.strip():
            t = anc.get("content-desc")
        if t and t.strip():
            anchor_text = t
            anchor_elem = nodes[cur][0]
            break
        idx = elem.get("index")
        path.insert(0, int(idx) if idx and idx.isdigit() else 0)
        cur = nodes[cur][1]
        elem = nodes[cur][0] if cur >= 0 else elem
    if anchor_text is None:
        return {"strategy": "L6", "resolve": "NO ANCHOR: 节点自身及父链均无 text/content-desc，无法定位"}
    return {
        "strategy": "L6", "parent_text": anchor_text, "path": path,
        "resolve": (f"findAccessibilityNodeInfosByText('{anchor_text}') -> 命中（取第 "
                    f"{text_ord.get(id(anchor_elem), 0)} 个）-> 沿 child index 路径 {path} 下钻"
                    f" -> 目标不可执行则向上爬兜底"),
    }


def find_anchor(elem, depth=0):
    """在 elem 往下的 ANCHOR_LOOKAHEAD 条边内找第一个非交互的文字节点。
    返回 (text, class, anchor_elem, source)；source in ('text','cd')，无则 None"""
    if depth > ANCHOR_LOOKAHEAD:
        return None
    a = elem.attrib
    t = text_attr(a)
    if t is not None and not is_interactive(a):
        return (t, a.get("class"), elem, "text")
    t = cd_attr(a)
    if t is not None and not is_interactive(a):
        return (t, a.get("class"), elem, "cd")
    for c in elem:
        r = find_anchor(c, depth + 1)
        if r:
            return r
    return None


# ---------------------------------------------------------------- 压缩

class Entry:
    __slots__ = ("id", "text", "flags", "cls", "rid", "depth", "flattened",
                 "anchor_cls", "locator")

    def __init__(self, eid, text, flags, cls, rid, depth, flattened,
                 anchor_cls=None, locator=None):
        self.id = eid
        self.text = text or ""
        self.flags = flags
        self.cls = cls
        self.rid = rid or ""
        self.depth = depth
        self.flattened = flattened
        self.anchor_cls = anchor_cls
        self.locator = locator

    def render(self):
        label = self.text if self.text else "(no text)"
        flags = "|".join(self.flags) or "-"
        mark = "~" if self.flattened else ""
        rid = f" id={self.rid}" if self.rid else ""
        return f"[{self.id}]{mark} {label} | {flags} | {self.cls}{rid}"

    def render_locator(self):
        return "    locator: " + fmt_locator(self.locator)


def fmt_locator(loc):
    if not loc:
        return "{strategy: ???}"
    parts = []
    for k in ("strategy", "resource_id", "content_desc", "text", "class",
              "ordinal", "parent_text", "path"):
        if k in loc:
            parts.append(f'{k}: "{loc[k]}"' if isinstance(loc[k], str) else f'{k}: {loc[k]}')
    return "{" + ", ".join(parts) + "}"


def compress(root_elem, max_depth=MAX_DEPTH_DEFAULT):
    """主流程：返回 (entries, lookup, stats)"""
    screen = screen_bounds(root_elem)
    stats = {"total": 0, "kept": 0, "dropped_noflags": 0, "dropped_bounds": 0,
             "dropped_wrapper": 0, "merged_anchors": 0, "flattened": 0}

    nodes = collect_nodes(root_elem)
    counts = compute_tree_counts(nodes)
    text_ord = text_ordinals(nodes)

    kept = []  # (elem, parent_idx, text, flags, anchor_cls, anchor_elem, anchor_source)
    for idx, (elem, p) in enumerate(nodes):
        a = elem.attrib
        b = parse_bounds(a.get("bounds"))
        if bounds_area(b) <= 0 or not within_screen(b, screen):
            stats["dropped_bounds"] += 1
            continue
        flags = node_flags(a)
        if not flags:
            stats["dropped_noflags"] += 1
            continue
        text = own_text(a)
        anchor_cls = None
        anchor_elem = None
        anchor_source = "text" if text_attr(a) else ("cd" if cd_attr(a) else None)
        if text is None:
            r = find_anchor(elem)
            if r:
                text, anchor_cls, anchor_elem, anchor_source = r
                stats["merged_anchors"] += 1
            else:
                text = ""
        kept.append((elem, p, text, flags, anchor_cls, anchor_elem, anchor_source))

    # 第二遍：嵌套包装去重 —— 同一**text 属性**锚点下的多个交互层，保留**最内层**
    # （锚点文字向上爬命中的是内层；保留外层会让 locator 解析到错误目标。
    #  仅 text 属性参与去重：cd 不参与 findByText 查找宇宙，不会与 text 锚点冲突）
    kept_info = {}
    for (elem, p, text, flags, anchor_cls, anchor_elem, anchor_source) in kept:
        if text and anchor_source == "text":
            kept_info[id(elem)] = (text, flags)
    deduped = []
    for k in kept:
        elem, p, text, flags, anchor_cls, anchor_elem, anchor_source = k
        dup = False
        if text and anchor_source == "text":  # 空文字/cd 锚点不参与去重
            stack = [(elem, 0)]
            while stack:
                cur, depth = stack.pop()
                if depth > ANCHOR_LOOKAHEAD:
                    continue
                for c in cur:
                    info = kept_info.get(id(c))
                    if info is not None and info[1]:
                        if info[0] == text:
                            dup = True
                        continue
                    stack.append((c, depth + 1))
        if dup:
            stats["dropped_wrapper"] += 1
            continue
        deduped.append(k)
    kept = deduped

    # 第三遍：层级（depth cap = 拍平）+ 短 ID + locator
    node_kept_idx = {id(elem): i for i, (elem, p, text, flags, ac, ae, asrc)
                     in enumerate(kept)}
    kept_ancestor = {}
    for i, (elem, p, text, flags, ac, ae, asrc) in enumerate(kept):
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
    elem_idx = {id(n): i for i, (n, _pp) in enumerate(nodes)}
    for i, (elem, p, text, flags, anchor_cls, anchor_elem, anchor_source) in enumerate(kept):
        pa = kept_ancestor[i]
        d = 0 if pa is None else depth_of[pa] + 1
        flattened = d > max_depth
        if flattened:
            d = max_depth
            stats["flattened"] += 1
        depth_of[i] = d

        loc = build_locator(elem, text or None, anchor_elem, counts, text_ord)
        if loc is None:
            loc = build_l6(elem, nodes, elem_idx[id(elem)], text_ord)
        e = Entry(len(entries), text, flags, elem.get("class"),
                  elem.get("resource-id") or "", d, flattened, anchor_cls, loc)
        entries.append(e)
        lookup.append({"id": e.id, "text": e.text, "class": e.cls,
                       "anchor_class": anchor_cls, "locator": loc})
        stats["kept"] += 1
    stats["total"] = len(nodes)
    return entries, lookup, stats


# ---------------------------------------------------------------- C2 新指标

def assess(root_elem):
    """
    新指标（任务 C2）：
      - 可交互节点总数：clickable / editable / scrollable 为 true 的节点
      - 可唯一指认数：其中能通过 L1–L5 任一策略唯一定位的数量
      - 可指认率 = 可唯一指认数 / 可交互节点总数
      - 策略分布 L1..L6 / no-anchor
      - 旧指标（附注）：规范 resource-id 覆盖率、android.view.View 占比
    """
    screen = screen_bounds(root_elem)
    nodes = collect_nodes(root_elem)
    counts = compute_tree_counts(nodes)
    text_ord = text_ordinals(nodes)

    def find_anchor_local(elem, depth=0):
        if depth > ANCHOR_LOOKAHEAD:
            return None
        a = elem.attrib
        t = text_attr(a)
        if t is not None and not is_interactive(a):
            return (t, a.get("class"), elem)
        t = cd_attr(a)
        if t is not None and not is_interactive(a):
            return (t, a.get("class"), elem)
        for c in elem:
            r = find_anchor_local(c, depth + 1)
            if r:
                return r
        return None

    interactive = []
    for i, (elem, p) in enumerate(nodes):
        a = elem.attrib
        b = parse_bounds(a.get("bounds"))
        if bounds_area(b) <= 0 or not within_screen(b, screen):
            continue
        if a.get("clickable") != "true" and a.get("scrollable") != "true" \
                and not is_editable(a):
            continue
        interactive.append((i, elem))

    # 预解析每个交互节点的文字信号（text 属性宇宙）与 cd 信号（cd 属性宇宙）
    # 锚点合并只影响展示文字；定位冲突只看属性宇宙：
    #   findByText 只看 text 属性；findByContentDescription 只看 content-desc 属性
    signals = {}
    for i, elem in interactive:
        a = elem.attrib
        own_t = text_attr(a)
        own_cd = cd_attr(a)
        anchor_t = anchor_cd = None
        r = find_anchor_local(elem) if (own_t is None and own_cd is None) else None
        if r:
            at, _ac, ael = r
            if text_attr(ael.attrib):
                anchor_t = at
            else:
                anchor_cd = at
        signals[id(elem)] = (set([own_t, anchor_t]) - {None},
                             set([own_cd, anchor_cd]) - {None})

    # shadowed：A 的信号与某个交互后代 B 的信号相同（A 的锚点向上爬会解析到 B，
    # 或 A/B 文字相同导致查找命中不唯一）—— A 不可唯一定位
    shadowed_ids = set()
    for i, elem in interactive:
        sig_t, sig_cd = signals[id(elem)]
        if not sig_t and not sig_cd:
            continue
        stack = [(elem, 0)]
        while stack:
            cur, depth = stack.pop()
            if depth > ANCHOR_LOOKAHEAD:
                continue
            for c in cur:
                if id(c) in signals:
                    dt, dcd = signals[id(c)]
                    if (sig_t & dt) or (sig_cd & dcd):
                        shadowed_ids.add(id(elem))
                stack.append((c, depth + 1))

    strat = {"L1": 0, "L2": 0, "L3": 0, "L4": 0, "L5": 0, "L6": 0,
             "no-anchor": 0, "shadowed": 0}
    details = []
    for i, elem in interactive:
        a = elem.attrib
        if id(elem) in shadowed_ids:
            strat["shadowed"] += 1
            details.append((elem, {"strategy": "shadowed",
                                   "resolve": "信号与交互后代相同，查找命中不唯一，本节点不可唯一定位"}))
            continue
        text = own_text(a)
        anchor_elem = None
        if text is None:
            r = find_anchor_local(elem)
            if r:
                text, _ac, anchor_elem = r
        loc = build_locator(elem, text, anchor_elem, counts, text_ord)
        if loc is None:
            loc = build_l6(elem, nodes, i, text_ord)
        s = loc.get("strategy", "no-anchor")
        if s == "L6" and "NO ANCHOR" in loc.get("resolve", ""):
            s = "no-anchor"
        strat[s] = strat.get(s, 0) + 1
        details.append((elem, loc))

    total = len(interactive)
    unique = sum(strat[k] for k in ("L1", "L2", "L3", "L4", "L5"))
    rate = 100.0 * unique / total if total else 0.0

    # 旧指标（附注）：规范 id 覆盖率 / View 占比
    canon = re.compile(r"^[a-z][a-z0-9_.]*:id/[a-zA-Z0-9_.]+$")
    total_all = len(nodes)
    with_id = sum(1 for n, _p in nodes if n.get("resource-id"))
    canon_id = sum(1 for n, _p in nodes
                   if n.get("resource-id") and canon.match(n.get("resource-id")))
    view_cnt = sum(1 for n, _p in nodes if n.get("class") == "android.view.View")

    return {
        "interactive_total": total, "unique_locatable": unique,
        "rate": rate, "strategy": strat, "details": details,
        "old": {"total": total_all, "with_id": with_id, "canon_id": canon_id,
                "view_ratio": 100.0 * view_cnt / total_all if total_all else 0.0,
                "view_cnt": view_cnt},
    }


def render_assess(path, res):
    out = [f"## {path}"]
    out.append(f"interactive_total: {res['interactive_total']}   "
               f"(clickable/editable/scrollable 节点)")
    out.append(f"unique_locatable: {res['unique_locatable']}   "
               f"rate: {res['rate']:.1f}%")
    d = res["strategy"]
    out.append("strategy distribution: " + ", ".join(f"{k}={d.get(k, 0)}" for k in
              ("L1", "L2", "L3", "L4", "L5", "L6", "no-anchor", "shadowed")))
    out.append(f"unlocatable: {res['interactive_total'] - res['unique_locatable']}"
               f" (L6={d.get('L6', 0)} no-anchor={d.get('no-anchor', 0)} shadowed={d.get('shadowed', 0)})")
    old = res["old"]
    out.append(f"old-metrics (附注): canon_id={old['canon_id']}/{old['with_id']}"
               f" (id 覆盖率 {100.0*old['canon_id']/old['total']:.0f}%)  "
               f"android.view.View={old['view_cnt']}/{old['total']} ({old['view_ratio']:.0f}%)")
    out.append("per-node (index, class, text/desc, strategy, resolve):")
    for elem, loc in res["details"]:
        a = elem.attrib
        lbl = (a.get("text") or a.get("content-desc") or "(no text)")[:30]
        out.append(f"  {a.get('index')}:{a.get('class','').split('.')[-1]:16s} "
                   f"'{lbl}' -> {loc.get('strategy')}: {loc.get('resolve','')[:80]}")
    return "\n".join(out)


# ---------------------------------------------------------------- 输出

def render_tree(entries):
    out = []
    for e in entries:
        out.append("  " * e.depth + e.render())
        out.append("  " * e.depth + e.render_locator())
    return "\n".join(out)


def render_lookup(lookup):
    out = ["--- reverse lookup: short ID -> locator ---"]
    for e in lookup:
        out.append(f"[{e['id']}] text='{e['text']}' class={e['class']} "
                   f"anchor_class={e['anchor_class'] or '-'} locator={fmt_locator(e['locator'])}")
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
    <node index="5" text="" resource-id="com.android.settings:id/dup" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[40,900][400,1000]">
      <node index="0" text="Repeat A" resource-id="" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[60,920][200,980]"/>
    </node>
    <node index="6" text="" resource-id="com.android.settings:id/dup" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[440,900][800,1000]">
      <node index="0" text="Repeat B" resource-id="" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[460,920][600,980]"/>
    </node>
    <node index="7" text="" resource-id="" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[40,1100][400,1200]">
      <node index="0" text="Repeat" resource-id="" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[60,1120][200,1180]"/>
    </node>
    <node index="8" text="" resource-id="" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[440,1100][800,1200]">
      <node index="0" text="Repeat" resource-id="" class="android.widget.TextView" package="com.android.settings" content-desc="" clickable="false" bounds="[460,1120][600,1180]"/>
    </node>
    <node index="9" text="" resource-id="" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[40,1300][400,1400]"/>
    <node index="10" text="Group" resource-id="" class="android.widget.LinearLayout" package="com.android.settings" content-desc="" clickable="false" bounds="[0,1500][1080,1700]">
      <node index="0" text="" resource-id="" class="android.widget.Button" package="com.android.settings" content-desc="" clickable="true" bounds="[40,1520][400,1620]"/>
    </node>
  </node>
</hierarchy>
"""


def self_test():
    root = ET.fromstring(SELF_TEST_XML)
    entries, lookup, stats = compress(root)
    tree = render_tree(entries)
    print(tree)
    print(render_lookup(lookup))
    assert stats["total"] == 20, stats
    # B2 原有断言：合并 / 零面积 / cd 兜底
    assert len(entries) == 10, [e.render() for e in entries]
    assert entries[0].text == "Magnification" and entries[0].flags == ["clickable"]
    assert entries[0].cls == "android.widget.LinearLayout" and entries[0].anchor_cls == "android.widget.TextView"
    texts = [e.text for e in entries]
    assert "Search settings" in texts and "Search box" in texts, texts
    # C1 修正：嵌套包装保留最内层（外层被去重）
    assert entries[1].text == "Nested row" and entries[1].cls == "android.widget.LinearLayout"
    assert "Nested row" not in [e.text for e in entries[2:]]

    # C1 locator 断言（六层全覆盖）
    l0 = entries[0].locator
    assert l0["strategy"] == "L4" and l0["text"] == "Magnification", l0
    assert "向上爬" in l0["resolve"], l0            # 锚点合并：爬取规则写进 locator
    assert entries[2].locator["strategy"] == "L1", entries[2].locator
    assert entries[2].locator["resource_id"] == "com.android.settings:id/search_action_bar"
    assert entries[3].locator["strategy"] == "L3" and entries[3].locator["content_desc"] == "Search box"
    # 重复 id -> L2（text 消歧）
    assert entries[4].locator["strategy"] == "L2" and entries[4].locator["text"] == "Repeat A"
    assert entries[5].locator["strategy"] == "L2" and entries[5].locator["text"] == "Repeat B"
    # 重复 text 无 id -> L5（ordinal 0/1）
    assert entries[6].locator["strategy"] == "L5" and entries[6].locator["ordinal"] == 0
    assert entries[7].locator["strategy"] == "L5" and entries[7].locator["ordinal"] == 1
    # L6：无锚点 与 结构路径
    assert entries[8].locator["strategy"] == "L6" and "NO ANCHOR" in entries[8].locator["resolve"]
    l9 = entries[9].locator
    assert l9["strategy"] == "L6" and l9["parent_text"] == "Group" and l9["path"] == [0], l9
    # 反查表含 locator
    assert all("locator" in e for e in lookup)

    # C2 指标自测
    res = assess(root)
    print("--- assess ---")
    print(render_assess("self-test", res))
    assert res["interactive_total"] == 11, res
    assert res["unique_locatable"] == 8, res
    assert abs(res["rate"] - 72.7) < 0.1, res
    d = res["strategy"]
    assert d["L1"] == 1 and d["L2"] == 2 and d["L3"] == 1 and d["L4"] == 2 \
        and d["L5"] == 2 and d["L6"] == 1 and d["no-anchor"] == 1 and d["shadowed"] == 1, d
    print("self-test PASS: B2 merge/bounds/cd-fallback + C1 locator L1-L6 + C2 assess 全部符合预期")


# ---------------------------------------------------------------- 主入口

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml", nargs="?", help="uiautomator dump 的 XML 文件")
    ap.add_argument("--max-depth", type=int, default=MAX_DEPTH_DEFAULT)
    ap.add_argument("--show-dropped", action="store_true")
    ap.add_argument("--assess", action="store_true", help="C2 新指标统计（替代 --self-test）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.xml:
        ap.error("需要提供 XML 文件路径，或使用 --self-test")

    root = ET.parse(args.xml).getroot()
    if args.assess:
        print(render_assess(args.xml, assess(root)))
        return

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
