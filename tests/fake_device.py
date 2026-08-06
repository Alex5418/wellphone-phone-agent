"""离线用的假设备：一棵 Settings 风格的节点树 + 一份 locator 解析器。

解析器是 Kotlin 侧 `LocatorResolver` 的**同语义重写**，用来在没有真机时验证
「Python 生成的 locator 能不能解析回它想指的那个节点」这条闭环。

⚠ 它证明不了真机行为 —— 真机侧的验证是 HARNESS-SPEC §10 的阶段 4，必须单独做。
它能证明的是：两侧约定的匹配规则（合并宇宙、DFS 序、target 三态、爬取兜底）
在 Python 侧的实现是自洽的，且 loop 的接线是通的。
"""

from __future__ import annotations

import copy

# ---------------------------------------------------------------- 节点树构造


def node(idx, parent, depth, cls, **kw):
    d = {
        "idx": idx, "parent": parent, "depth": depth, "class": cls,
        "resource_id": None, "text": None, "content_desc": None,
        "clickable": False, "long_clickable": False, "scrollable": False,
        "editable": False, "checkable": False, "checked": False,
        "focused": False, "enabled": True, "visible": True,
        "hint_text": False, "bounds": [0, 0, 1280, 720], "actions": [],
    }
    d.update(kw)
    return d


def settings_tree() -> list[dict]:
    """一棵覆盖 L1–L6 全部分支的树。结构刻意贴近实测的 Preference 布局。"""
    n = []
    a = n.append
    # 0 根
    a(node(0, None, 0, "android.widget.FrameLayout",
           resource_id="com.android.settings:id/content"))
    # 1 返回按钮：无 id、无 text，只有 content_desc -> L3
    a(node(1, 0, 1, "android.widget.ImageButton", content_desc="返回",
           clickable=True, bounds=[0, 0, 80, 80]))
    # 2 搜索框：唯一 id -> L1；空 EditText 的 text 是 hint
    a(node(2, 0, 1, "android.widget.EditText",
           resource_id="com.android.settings:id/search_bar",
           text="搜索设置", hint_text=True, editable=True, clickable=True,
           bounds=[80, 0, 1200, 80]))
    # 3 列表容器：可滚动、有唯一 id -> L1
    a(node(3, 0, 1, "androidx.recyclerview.widget.RecyclerView",
           resource_id="com.android.settings:id/recycler_view",
           scrollable=True, bounds=[0, 80, 1280, 720]))
    # 4-6 行一：整行可点，文字在子节点 -> L4 + ancestor_clickable
    a(node(4, 3, 2, "android.widget.LinearLayout", clickable=True,
           bounds=[0, 80, 1280, 200]))
    a(node(5, 4, 3, "android.widget.TextView", resource_id="android:id/title",
           text="网络和互联网", bounds=[40, 90, 600, 140]))
    a(node(6, 4, 3, "android.widget.TextView", resource_id="android:id/summary",
           text="已连接 WLAN", bounds=[40, 140, 600, 190]))
    # 7-10 行二：整行可点 + 行内 Switch。**同一句文字，两种行为**
    a(node(7, 3, 2, "android.widget.LinearLayout", clickable=True,
           bounds=[0, 200, 1280, 320]))
    a(node(8, 7, 3, "android.widget.LinearLayout", bounds=[0, 200, 1000, 320]))
    a(node(9, 8, 4, "android.widget.TextView", resource_id="android:id/title",
           text="深色主题", bounds=[40, 210, 600, 260]))
    a(node(10, 7, 3, "android.widget.Switch",
           resource_id="android:id/switch_widget",
           clickable=True, checkable=True, checked=True,
           bounds=[1000, 220, 1200, 300]))
    # 11-14 两个同 id 不同文字的按钮 -> L2
    a(node(11, 3, 2, "android.widget.Button", resource_id="com.android.settings:id/btn",
           clickable=True, bounds=[0, 320, 600, 400]))
    a(node(12, 11, 3, "android.widget.TextView", text="安装", bounds=[20, 330, 300, 390]))
    a(node(13, 3, 2, "android.widget.Button", resource_id="com.android.settings:id/btn",
           clickable=True, bounds=[600, 320, 1200, 400]))
    a(node(14, 13, 3, "android.widget.TextView", text="卸载", bounds=[620, 330, 900, 390]))
    # 15-18 两个文字完全相同的按钮 -> L5（ordinal）
    a(node(15, 3, 2, "android.widget.Button", clickable=True, bounds=[0, 400, 600, 480]))
    a(node(16, 15, 3, "android.widget.TextView", text="打开", bounds=[20, 410, 300, 470]))
    a(node(17, 3, 2, "android.widget.Button", clickable=True, bounds=[600, 400, 1200, 480]))
    a(node(18, 17, 3, "android.widget.TextView", text="打开", bounds=[620, 410, 900, 470]))
    # 19 什么锚点都没有的可点节点 -> L6
    a(node(19, 3, 2, "android.widget.ImageView", clickable=True,
           bounds=[0, 480, 200, 560]))
    # 20 屏幕外的条目（裁剪测试用）
    a(node(20, 3, 2, "android.widget.Button", clickable=True, text="页脚",
           bounds=[0, 2000, 600, 2080]))
    # 21-23 第二个开关行：故意让 switch 的 id 与行二重复。
    # 真机上 Preference 列表里 android:id/switch_widget 每行一个，id 从来不唯一 ——
    # 固定成"唯一 id"会把 L1 之外的分支全测不到。
    a(node(21, 3, 2, "android.widget.LinearLayout", clickable=True,
           bounds=[0, 560, 1280, 680]))
    a(node(22, 21, 3, "android.widget.TextView", resource_id="android:id/title",
           text="自动亮度", bounds=[40, 570, 600, 620]))
    a(node(23, 21, 3, "android.widget.Switch",
           resource_id="android:id/switch_widget",
           clickable=True, checkable=True, checked=False,
           bounds=[1000, 580, 1200, 660]))
    return n


# ---------------------------------------------------------------- 解析器（Kotlin 同语义）


class FakeResolver:
    def __init__(self, nodes: list[dict]):
        self.nodes = nodes

    def _label(self, n: dict) -> str | None:
        t = n.get("text")
        if t and t.strip() and not n.get("hint_text"):
            return t
        cd = n.get("content_desc")
        return cd if cd and cd.strip() else None

    def _children(self, idx: int) -> list[int]:
        return [n["idx"] for n in self.nodes if n["parent"] == idx]

    def _text_match(self, n: dict, want: str | None) -> bool:
        return want is not None and (n.get("text") == want or n.get("content_desc") == want)

    def _label_matches(self, n: dict, want: str | None) -> bool:
        if want is None:
            return True
        if self._text_match(n, want):
            return True
        frontier, d = self._children(n["idx"]), 1
        while frontier and d <= 3:
            for i in frontier:
                if self._text_match(self.nodes[i], want):
                    return True
            frontier = [c for i in frontier for c in self._children(i)]
            d += 1
        return False

    def _interactive(self, n: dict) -> bool:
        return bool(n["clickable"] or n["long_clickable"] or n["scrollable"] or n["editable"])

    def _climb(self, idx: int) -> int | None:
        cur = self.nodes[idx]["parent"]
        while cur is not None:
            if self._interactive(self.nodes[cur]):
                return cur
            cur = self.nodes[cur]["parent"]
        return None

    def _descendant_class(self, base: int, cls: str) -> int | None:
        queue = list(self._children(base))
        while queue:
            i = queue.pop(0)
            if self.nodes[i]["class"] == cls:
                return i
            queue.extend(self._children(i))
        return None

    def _by_path(self, path: list[int]) -> list[int]:
        roots = [n["idx"] for n in self.nodes if n["parent"] is None]
        if not path or path[0] >= len(roots):
            return []
        cur = roots[path[0]]
        for step in path[1:]:
            kids = self._children(cur)
            if step >= len(kids):
                return []
            cur = kids[step]
        return [cur]

    def resolve(self, loc: dict) -> tuple[int | None, int]:
        """@return (执行节点 idx, 候选数)"""
        s = loc.get("strategy")
        if s == "L1":
            cands = [n["idx"] for n in self.nodes if n.get("resource_id") == loc.get("resource_id")]
        elif s == "L2":
            cands = [n["idx"] for n in self.nodes
                     if n.get("resource_id") == loc.get("resource_id")
                     and self._label_matches(n, loc.get("text"))]
        elif s == "L3":
            cands = [n["idx"] for n in self.nodes
                     if n.get("content_desc") == loc.get("content_desc")]
        elif s in ("L4", "L5"):
            cands = [n["idx"] for n in self.nodes if self._text_match(n, loc.get("text"))]
        elif s == "L6":
            cands = self._by_path(loc.get("path") or [])
        else:
            return None, 0
        if not cands:
            return None, 0
        anchor = cands[loc.get("index", 0)] if s == "L5" else cands[0]
        if anchor is None:
            return None, len(cands)

        rule = loc.get("target", "self")
        if rule == "self":
            tgt = anchor
        elif rule == "ancestor_clickable":
            tgt = self._climb(anchor)
        elif rule.startswith("descendant_class:"):
            base = anchor if self._interactive(self.nodes[anchor]) else self._climb(anchor)
            base = anchor if base is None else base
            tgt = self._descendant_class(base, rule.split(":", 1)[1])
        else:
            tgt = anchor
        # 兜底：爬不到用原候选，不返回失败
        return (anchor if tgt is None else tgt), len(cands)


# ---------------------------------------------------------------- 假 transport


class FakeTransport:
    """实现 Transport 的命令面。记录每次 act 的参数，供护栏断言使用。"""

    def __init__(self, nodes: list[dict] | None = None, primary_pkg="com.android.chrome",
                 secondary=6, pkg="com.android.settings"):
        self.nodes = copy.deepcopy(nodes if nodes is not None else settings_tree())
        self.secondary = secondary
        self.pkg = pkg
        self.activity = "com.android.settings.Settings$DisplaySettingsActivity"
        self.primary_pkg = primary_pkg
        self.acts: list[dict] = []
        self.last_request: dict | None = None
        self.last_response: dict | None = None
        self.restore_ok = True
        self.ime_present = False
        # 「哑节点」：performAction 返回 true 但界面毫无反应 —— 实测存在的失败形态之一
        self.dumb: set[int] = set()

    # ---- 内部 ----

    def _resolver(self) -> FakeResolver:
        return FakeResolver(self.nodes)

    def _hash(self) -> str:
        from harness.models import Node
        from harness.tree import local_tree_hash
        return local_tree_hash([Node.from_json(d) for d in self.nodes])

    def _node_state(self, idx: int | None, cands: int) -> dict:
        if idx is None:
            return {"found": False, "candidates": cands}
        n = self.nodes[idx]
        return {
            "found": True, "candidates": cands, "note": "ok",
            "class": n["class"], "resource_id": n["resource_id"],
            "text": None if n["hint_text"] else n["text"],
            "content_desc": n["content_desc"],
            "checkable": n["checkable"], "checked": n["checked"],
            "enabled": n["enabled"], "focused": n["focused"], "selected": False,
        }

    # ---- 命令 ----

    def state(self) -> dict:
        return {
            "displays": [
                {"id": 0, "windows": [{"pkg": self.primary_pkg, "focused": True}]},
                {"id": self.secondary, "windows": [{"pkg": self.pkg, "focused": True}]},
            ],
            "primary_focus": {"display": 0, "pkg": self.primary_pkg,
                              "node_class": "android.widget.EditText",
                              "resource_id": "com.android.chrome:id/url_bar",
                              "editable": True, "text_len": 42},
            "ime_present": self.ime_present,
            "ime_pkg": "com.google.android.inputmethod.latin" if self.ime_present else None,
        }

    def observe(self, display: int) -> dict:
        return {
            "display": display, "pkg": self.pkg, "activity": self.activity,
            "window_count": 1, "tree_hash": self._hash(), "truncated": False,
            "nodes": copy.deepcopy(self.nodes),
        }

    def act(self, display, locator, action, value=None, restore=True,
            verify_read=True) -> dict:
        loc = locator.to_json() if hasattr(locator, "to_json") else locator
        self.acts.append({"display": display, "locator": loc, "action": action,
                          "value": value, "restore": restore})
        self.last_request = {"cmd": "act", "args": {"display": display, "locator": loc,
                                                    "action": action, "value": value,
                                                    "restore": restore}}
        # locator 缺席 = 全局动作（BACK），设备侧不做解析
        idx, cands = (None, 0) if loc is None else self._resolver().resolve(loc)
        ok = False
        if action.upper() == "BACK":
            self.activity = "com.android.settings.Settings"
            ok = True
        elif idx in self.dumb:
            ok = True          # 工具说成功，界面没动
        elif idx is not None:
            n = self.nodes[idx]
            if action.upper() == "CLICK":
                if n["checkable"]:
                    n["checked"] = not n["checked"]
                elif n["clickable"]:
                    self.activity = "com.android.settings.SubSettings"
                ok = True
            elif action.upper() == "SET_TEXT" and n["editable"]:
                n["text"] = value
                n["hint_text"] = False
                ok = True
            elif action.upper().startswith("SCROLL"):
                ok = True
        resp = {
            "resolved": {"found": loc is None or idx is not None, "candidates": cands,
                         "class": self.nodes[idx]["class"] if idx is not None else None},
            "action_ok": ok,
            # focus_ms 是打扰窗口，verify_ms 是校验开销 —— 设备侧刻意分开上报，
            # 免得头条数字被自己的仪表拖大
            "restore": ({"attempted": True, "ok": self.restore_ok, "retried": False,
                         "focus_ms": 12, "verify_ms": 18, "total_ms": 30,
                         "holder_after": self.primary_pkg if self.restore_ok else self.pkg,
                         "expect_pkg": self.primary_pkg}
                        if restore else {"attempted": False, "reason": "restore=false"}),
            "post_state": self._node_state(idx, cands) if verify_read else {"found": False},
            "window_after": {"display": display, "pkg": self.pkg,
                             "activity": self.activity, "window_count": 1},
            "timing": {"action_ms": 56, "disturb_ms": 68, "restore_focus_ms": 12,
                       "restore_total_ms": 30, "total_ms": 95},
        }
        self.last_response = {"ok": True, "data": resp}
        return resp

    def probe(self, display, locator) -> dict:
        loc = locator.to_json() if hasattr(locator, "to_json") else locator
        idx, cands = self._resolver().resolve(loc)
        return self._node_state(idx, cands)
