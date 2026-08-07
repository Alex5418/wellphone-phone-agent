"""数据类（HARNESS-SPEC §4.1）。不依赖任何本地模块。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    idx: int
    parent: int | None
    depth: int
    cls: str
    resource_id: str | None
    text: str | None
    content_desc: str | None
    clickable: bool
    long_clickable: bool
    scrollable: bool
    editable: bool
    checkable: bool
    checked: bool
    focused: bool
    enabled: bool
    visible: bool
    bounds: tuple[int, int, int, int] | None
    actions: list[str]
    hint_text: bool = False   # text 其实是 hint（空 EditText 的已知坑）
    sel_start: int = -1       # 光标/选区，用于判断光标有没有跳
    sel_end: int = -1

    @property
    def interactive(self) -> bool:
        return self.clickable or self.long_clickable or self.scrollable or self.editable

    @property
    def effective_text(self) -> str | None:
        """真正填进去的文字。hint 不算。"""
        return None if self.hint_text else self.text

    @staticmethod
    def from_json(d: dict) -> "Node":
        b = d.get("bounds")
        return Node(
            idx=d["idx"],
            parent=d.get("parent"),
            depth=d.get("depth", 0),
            cls=d.get("class") or "",
            resource_id=d.get("resource_id"),
            text=d.get("text"),
            content_desc=d.get("content_desc"),
            clickable=bool(d.get("clickable")),
            long_clickable=bool(d.get("long_clickable")),
            scrollable=bool(d.get("scrollable")),
            editable=bool(d.get("editable")),
            checkable=bool(d.get("checkable")),
            checked=bool(d.get("checked")),
            focused=bool(d.get("focused")),
            enabled=bool(d.get("enabled", True)),
            visible=bool(d.get("visible", True)),
            bounds=tuple(b) if b else None,   # type: ignore[arg-type]
            actions=list(d.get("actions") or []),
            hint_text=bool(d.get("hint_text")),
            sel_start=int(d.get("sel_start", -1) or -1),
            sel_end=int(d.get("sel_end", -1) or -1),
        )


@dataclass
class Locator:
    """LLM 永远看不到这个对象 —— 它只跟短 ID 打交道（ARCHITECTURE §4）。"""

    strategy: str                    # "L1".."L6"
    resource_id: str | None = None
    text: str | None = None
    content_desc: str | None = None
    cls: str | None = None
    index: int = 0                   # L5：同类候选中的第几个（按 observe 的 idx 序）
    target: str = "self"             # "self" | "ancestor_clickable" | "descendant_class:<n>"
    path: list[int] | None = None    # L6：[根序号, 子序号, ...]

    def to_json(self) -> dict:
        d: dict[str, Any] = {"strategy": self.strategy, "target": self.target}
        if self.resource_id is not None:
            d["resource_id"] = self.resource_id
        if self.text is not None:
            d["text"] = self.text
        if self.content_desc is not None:
            d["content_desc"] = self.content_desc
        if self.cls is not None:
            d["cls"] = self.cls
        if self.strategy == "L5":
            d["index"] = self.index
        if self.path is not None:
            d["path"] = self.path
        return d

    def describe(self) -> str:
        parts = [self.strategy]
        for k in ("resource_id", "content_desc", "text", "cls"):
            v = getattr(self, k)
            if v:
                parts.append(f"{k}={v!r}")
        if self.strategy == "L5":
            parts.append(f"index={self.index}")
        if self.path:
            parts.append(f"path={self.path}")
        if self.target != "self":
            parts.append(f"target={self.target}")
        return " ".join(parts)


@dataclass
class Item:
    """压缩后的逻辑条目，喂给 LLM 的最小单位。sid 每轮重新分配，跨轮次无效。"""

    sid: int
    label: str
    kind: str                # button|switch|input|list|text|other
    state: str | None
    locator: Locator
    anchor_idx: int
    target_idx: int
    onscreen: bool = True
    checked: bool | None = None
    text_value: str | None = None
    res_id: str | None = None
    # 相比上一轮观测是否新出现。浮层/下拉/自动补全建议在节点树里**不是新窗口**
    # （实测 window_count 仍为 1），拍平成条目后与页面原有内容长得一模一样 ——
    # flash 实测栽在这里：补全把 Subject 顶掉，它以为没滚到，反复滚动去找。
    is_new: bool = False
    # 非 None = 被排除出动作空间，值是原因。护栏判定，LLM 不能推翻
    blocked: str | None = None

    def render(self) -> str:
        line = f"[{self.sid}] {self.label or '(无文字)'} | {self.kind}"
        if self.state:
            line += f" | {self.state}"
        if self.is_new:
            line += " | ✦上一步之后新出现"
        if self.blocked:
            line += f" | ⛔ 不可操作：{self.blocked}"
        return line


@dataclass
class Tree:
    display: int
    pkg: str | None
    activity: str | None
    tree_hash: str
    nodes: list[Node]
    window_count: int = 1
    truncated: bool = False
    reduced: bool = False
    # 三值：True=对不上，False=对得上，None=设备没给 hash，无从比对。
    # 不许折叠成布尔 —— 「读不到」不是「没问题」。
    hash_mismatch: bool | None = None

    def __post_init__(self) -> None:
        self._children: dict[int, list[int]] = {}
        for n in self.nodes:
            if n.parent is not None:
                self._children.setdefault(n.parent, []).append(n.idx)

    def by_idx(self, idx: int) -> Node:
        return self.nodes[idx]

    def children(self, idx: int) -> list[int]:
        return self._children.get(idx, [])

    def roots(self) -> list[int]:
        return [n.idx for n in self.nodes if n.parent is None]

    def ancestors(self, idx: int):
        cur = self.nodes[idx].parent
        while cur is not None:
            yield cur
            cur = self.nodes[cur].parent

    def descendants(self, idx: int, max_depth: int = 99):
        frontier, d = self.children(idx), 1
        while frontier and d <= max_depth:
            for i in frontier:
                yield i
            frontier = [c for i in frontier for c in self.children(i)]
            d += 1


@dataclass
class EnvState:
    secondary_display: int | None
    secondary_pkg: str | None
    primary_focus_pkg: str | None
    ime_present: bool | None   # None = 读不到 display 0 的窗口，无从判断
    tree_hash: str
    anomalies: list[str] = field(default_factory=list)
    fatal: bool = False
    displays: list[int] = field(default_factory=list)


@dataclass
class ActionResult:
    found: bool
    action_ok: bool
    restore_attempted: bool
    restore_ok: bool | None
    # 打扰窗口（重解析 + ACTION_FOCUS），与 E6 的纯 ACTION_FOCUS 耗时可比。
    # **不含**校验窗口持有者的开销 —— 那部分发生在焦点已经还回去之后。
    restore_focus_ms: int | None
    restore_total_ms: int | None
    restore_retried: bool
    holder_after: str | None
    post_state: dict
    window_after: dict
    timing: dict
    candidates: int = 0
    restore_expect_pkg: str | None = None
    # 归还结论由谁给出：device（a11y 自报）/ dumpsys（PC 侧交叉校验）/ None（无法确认）
    restore_confirmed_by: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)

    @staticmethod
    def from_json(d: dict) -> "ActionResult":
        r = d.get("restore") or {}
        res = d.get("resolved") or {}
        return ActionResult(
            found=bool(res.get("found")),
            action_ok=bool(d.get("action_ok")),
            restore_attempted=bool(r.get("attempted")),
            restore_ok=r.get("ok") if r.get("attempted") else None,
            restore_focus_ms=r.get("focus_ms"),
            restore_total_ms=r.get("total_ms"),
            restore_retried=bool(r.get("retried")),
            holder_after=r.get("holder_after"),
            restore_expect_pkg=r.get("expect_pkg"),
            restore_confirmed_by="device" if r.get("ok") is not None else None,
            post_state=d.get("post_state") or {},
            window_after=d.get("window_after") or {},
            timing=d.get("timing") or {},
            candidates=int(res.get("candidates") or 0),
            raw=d,
        )


@dataclass
class Plan:
    thought: str
    action: str
    target: int | None
    value: str | None
    done: bool
    # "achieved" | "impossible"。收尾不等于成功 —— 任务做不成也要收尾，
    # 把两者都记成 done 是在把结果报得比实际好
    outcome: str = "achieved"
    raw: str = ""


@dataclass
class Verdict:
    result: str          # PASS | FAIL | UNKNOWN
    predicate: str       # 人类可读的判据描述
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.result != "FAIL"


@dataclass
class Step:
    n: int
    plan: Plan
    item: Item | None
    result: ActionResult | None
    verdict: Verdict | None
    note: str = ""

    def summarize(self) -> str:
        """写进 observation 的「已执行」—— 结构化文字摘要，不含历史节点树。"""
        label = f'"{self.item.label}"' if self.item else ""
        head = f"{self.n}. {self.plan.action} {label}".rstrip()
        if self.result is None:
            return f"{head} → {self.note or '未执行'}"
        bits = []
        if self.verdict:
            bits.append({"PASS": "已生效", "FAIL": "未生效",
                         "UNKNOWN": "结果未知"}[self.verdict.result])
            # 只写判据的实际观测（"checked True → False" / "activity → SubSettings"），
            # 不无条件复述当前 activity —— 没变化的东西不该占 observation 的篇幅
            if self.verdict.detail:
                bits.append(self.verdict.detail)
        # 报告偏离：归还成功不写，失败必须写
        if self.result.restore_attempted and self.result.restore_ok is False:
            bits.append("⚠ 焦点归还失败")
        if self.note:
            bits.append(self.note)
        return f"{head} → " + "，".join(bits)


@dataclass
class RunResult:
    task: str
    status: str          # done | exhausted | aborted | error
    reason: str
    steps: list[Step]
    run_dir: str | None = None
