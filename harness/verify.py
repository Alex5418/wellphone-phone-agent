"""验证（HARNESS-SPEC §5 / ARCHITECTURE §3.4）。

两条不能让步的原则：

1. **判据由 harness 按节点类型推断，不要求 LLM 声明预期。**
   让 LLM 声明预期等于把「是否检查」交给概率性决策者。

2. **判断在 Python 侧做，用的是独立重读来的 probe 数据。**
   act 响应里的 post_state 只作对照 —— 用产生结果的同一条链路去验证结果，
   等于没验证（实测过三种"工具会撒谎"的形态，其中最危险的一种输出的是正确答案）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ActionResult, Item, Verdict


@dataclass
class Snapshot:
    """动作前后用于比对的最小状态。"""

    found: bool
    checked: bool | None
    text: str | None
    activity: str | None
    tree_hash: str | None
    window_count: int | None

    @staticmethod
    def from_probe(d: dict, activity: str | None = None,
                   tree_hash: str | None = None,
                   window_count: int | None = None) -> "Snapshot":
        return Snapshot(
            found=bool(d.get("found")),
            checked=d.get("checked") if d.get("checkable") else d.get("checked"),
            text=d.get("text"),
            activity=activity,
            tree_hash=tree_hash,
            window_count=window_count,
        )

    @staticmethod
    def from_item(item: Item, activity: str | None, tree_hash: str | None,
                  window_count: int | None) -> "Snapshot":
        return Snapshot(
            found=True,
            checked=item.checked,
            text=item.text_value,
            activity=activity,
            tree_hash=tree_hash,
            window_count=window_count,
        )


def infer_predicate(item: Item, action: str) -> str:
    a = action.upper()
    if item.kind == "switch" and a == "CLICK":
        return "checked_flips"
    if item.kind == "input" and a == "SET_TEXT":
        return "text_equals_value"
    if a in ("SCROLL_FORWARD", "SCROLL_BACKWARD"):
        return "tree_hash_changes"
    if a == "LONG_CLICK":
        return "window_count_increases"
    if a == "BACK":
        return "activity_or_tree_changes"
    if a == "CLICK":
        return "activity_or_tree_changes"
    return "none"


def verify(item: Item, action: str, pre: Snapshot, post: Snapshot,
           result: ActionResult, value: str | None = None) -> Verdict:
    pred = infer_predicate(item, action)

    if not result.found:
        return Verdict("FAIL", pred, "locator 没解析到节点，动作未执行")

    if pred == "checked_flips":
        if not post.found:
            return Verdict("UNKNOWN", pred, "动作后目标节点消失（可能是页面跳转）")
        if post.checked is None or pre.checked is None:
            return Verdict("UNKNOWN", pred, "checked 状态读不到")
        if post.checked != pre.checked:
            return Verdict("PASS", pred, f"checked {pre.checked} → {post.checked}")
        return Verdict("FAIL", pred, f"checked 仍为 {post.checked}")

    if pred == "text_equals_value":
        if post.text == value:
            return Verdict("PASS", pred, f"text = {value!r}")
        if post.text == pre.text:
            # 读到的仍是写入前的值 —— 分不出"没写进去"和"读取通道滞后"。
            # 实测：Gmail 撰写页正文 4/4 属后者（判 FAIL，但收到的邮件正文完全正确），
            # refresh() / 等 3-5 秒 / 发 FOCUS 都不能让它跟上（E12 §5、E13 §7）。
            # 按「没有证据说明失败时不许报失败」，这里只能是 UNKNOWN。
            # 真正的哑写入由 stall 判据兜底：界面连续不变照样会中止。
            return Verdict("UNKNOWN", pred,
                           f"读到的仍是写入前的值 {post.text!r} —— "
                           f"可能没写进去，也可能是读取通道滞后")
        return Verdict("FAIL", pred, f"期望 {value!r}，实际 {post.text!r}")

    if pred == "tree_hash_changes":
        if pre.tree_hash is None or post.tree_hash is None:
            return Verdict("UNKNOWN", pred, "缺少 tree_hash")
        if pre.tree_hash != post.tree_hash:
            return Verdict("PASS", pred, "界面内容已变化")
        # 滚到底了也是这个现象 —— 是"没动"，但不一定是"动作是哑的"
        return Verdict("FAIL", pred, "tree_hash 未变化（可能已到边界）")

    if pred == "window_count_increases":
        if pre.window_count is None or post.window_count is None:
            return Verdict("UNKNOWN", pred, "缺少窗口数")
        if post.window_count > pre.window_count:
            return Verdict("PASS", pred, f"窗口数 {pre.window_count} → {post.window_count}")
        return Verdict("FAIL", pred, "没有新窗口弹出")

    if pred == "activity_or_tree_changes":
        if pre.activity and post.activity and pre.activity != post.activity:
            return Verdict("PASS", pred, f"activity → {post.activity.rsplit('.', 1)[-1]}")
        if pre.tree_hash and post.tree_hash and pre.tree_hash != post.tree_hash:
            return Verdict("PASS", pred, "界面内容已变化")
        # activity 与 hash 都没变：可能这个控件本来就没有副作用，
        # 也可能动作是哑的 —— 分不出来就如实说分不出来，不当成失败
        return Verdict("UNKNOWN", pred, "activity 与界面内容均无变化，无法判定")

    return Verdict("UNKNOWN", pred, "该动作无自动判据")


def cross_check_post_state(result: ActionResult, probe: dict) -> str | None:
    """act 自报的 post_state 与独立 probe 不一致时返回描述（记进日志，不用于判定）。"""
    a, b = result.post_state or {}, probe or {}
    diffs = [k for k in ("found", "checked", "text")
             if k in a and k in b and a.get(k) != b.get(k)]
    if not diffs:
        return None
    return "post_state 与独立 probe 不一致: " + ", ".join(
        f"{k}: act={a.get(k)!r} probe={b.get(k)!r}" for k in diffs)
