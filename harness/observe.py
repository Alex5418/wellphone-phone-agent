"""状态自检 + Observation 文本组装（HARNESS-SPEC §6）。

三条规则：
1. 归还成功只留一行摘要，失败必须显式标 ⚠ 并写进「已执行」
2. 历史是结构化文字摘要，不含历史节点树
3. **报告偏离，不报告正常** —— 弱模型不被噪声淹没，强模型出事时拿得到线索
"""

from __future__ import annotations

from . import config
from .compress import trim_for_display
from .models import EnvState, Item, Step, Tree

FATAL_ANOMALIES = ("secondary_display_missing", "target_app_not_on_secondary")

_ANOMALY_TEXT = {
    "secondary_display_missing": "副屏不存在（scrcpy 虚拟屏可能已随进程消亡）",
    "target_app_not_on_secondary": "副屏上不是目标 app",
    "tree_unchanged_after_action": "上一步动作声称成功，但界面没有任何变化",
    "primary_focus_lost": "主屏当前没有输入焦点持有者",
    "tree_hash_mismatch": "设备返回的 tree_hash 与本地复算不一致（节点数组可能被截断）",
    "tree_hash_uncomparable": "设备没给 tree_hash，本地复算无从比对（记为未知，不当作正常）",
    "tree_truncated": "节点树超过深度上限被截断",
    "focus_holder_mismatch": "dumpsys 层面的焦点持有者与设备自报的不一致",
    "restore_unverified": "无法从 dumpsys 交叉校验焦点归还（记为未知，不当作成功）",
}


def pick_secondary_display(state: dict, primary: int = config.PRIMARY_DISPLAY) -> int | None:
    """display id 每次都变（实测 2/4/5/6），任何硬编码都是 bug。"""
    ids = [d.get("id") for d in state.get("displays", []) if d.get("id") != primary]
    return max(ids) if ids else None


def self_check(state: dict, expected_pkg: str, last_hash: str | None,
               tree: Tree | None = None, last_action_claimed_ok: bool = False,
               secondary: int | None = None) -> EnvState:
    anomalies: list[str] = []
    displays = [d.get("id") for d in state.get("displays", [])]
    sec = secondary if secondary is not None else pick_secondary_display(state)

    sec_pkg = None
    if sec is None:
        anomalies.append("secondary_display_missing")
    else:
        for d in state.get("displays", []):
            if d.get("id") != sec:
                continue
            wins = d.get("windows") or []
            sec_pkg = next((w.get("pkg") for w in wins if w.get("pkg")), None)
        if tree is not None and tree.pkg:
            sec_pkg = tree.pkg
        if expected_pkg and sec_pkg and expected_pkg not in sec_pkg:
            anomalies.append("target_app_not_on_secondary")

    pf = state.get("primary_focus")
    primary_pkg = pf.get("pkg") if isinstance(pf, dict) else None
    if not primary_pkg:
        anomalies.append("primary_focus_lost")

    tree_hash = tree.tree_hash if tree else ""
    if tree is not None:
        # hash_mismatch 是三值的：True 对不上 / False 对得上 / None 无从比对
        if tree.hash_mismatch is True:
            anomalies.append("tree_hash_mismatch")
        elif tree.hash_mismatch is None and tree.tree_hash:
            anomalies.append("tree_hash_uncomparable")
        if tree.truncated:
            anomalies.append("tree_truncated")
        if last_hash and tree_hash == last_hash and last_action_claimed_ok:
            anomalies.append("tree_unchanged_after_action")

    return EnvState(
        secondary_display=sec,
        secondary_pkg=sec_pkg,
        primary_focus_pkg=primary_pkg,
        # 三值透传：设备报 null 表示它自己也不知道
        ime_present=state.get("ime_present"),
        tree_hash=tree_hash,
        anomalies=anomalies,
        fatal=any(a in FATAL_ANOMALIES for a in anomalies),
        displays=[d for d in displays if d is not None],
    )


def mark_changes(items, prev):
    """标记新出现的条目，并返回"上一步之后消失的"清单。

    为什么需要：浮层 / 下拉 / 自动补全建议在节点树里**不是新窗口**
    （实测 window_count 仍为 1），拍平成条目后与页面原有内容毫无区别。
    真正发生的是"某些条目消失、某些条目出现"，而观测层原本一个字都没表达 ——
    弱模型只能靠猜，而**需要靠猜本身就是观测层的缺陷**：
    能随模型能力浮动的是策略层，观测与护栏不行（ARCHITECTURE §2）。

    整页换掉时不报增删（那时"全是新的"没有信息量），只在页面大体未变时报。
    """
    if not prev:
        return []
    def key(i):
        return (i.label, i.kind)
    prev_keys = {key(i) for i in prev}
    cur_keys = {key(i) for i in items}
    if not prev_keys or len(prev_keys & cur_keys) / len(prev_keys) < 0.5:
        return []
    for i in items:
        i.is_new = key(i) not in prev_keys
    return [f"{lb} | {kd}" for (lb, kd) in sorted(prev_keys - cur_keys)]


def build_observation(task: str, env: EnvState, items: list[Item],
                      history: list[Step], politeness: str = config.POLITENESS,
                      max_items: int = config.MAX_ITEMS_SHOWN,
                      prev_items=None) -> str:
    out: list[str] = ["## 任务", task, "", "## 环境状态"]

    out.append(f"- 副屏: display {env.secondary_display} · {env.secondary_pkg or '未知'}"
               + (" ✓" if not env.fatal else " ✗"))

    last = history[-1] if history else None
    focus_line = f"- 主屏焦点: {env.primary_focus_pkg or '无'}"
    if last and last.result and last.result.restore_attempted:
        if last.result.restore_ok:
            focus_line += f" · 已归还 ({last.result.restore_focus_ms} ms)"
        else:
            focus_line += " · ⚠ 归还失败"
    out.append(focus_line)
    out.append("- 用户输入中: "
               + ("未知（读不到主屏窗口）" if env.ime_present is None
                  else ("是" if env.ime_present else "否")))

    if last:
        summary = last.summarize()
        out.append("- 上一步: " + summary.split(". ", 1)[-1])

    # 报告偏离：无异常时整节省略
    extra = [a for a in env.anomalies if a not in ("target_app_not_on_secondary",)]
    if extra:
        out.append("- ⚠ 环境异常: " + "；".join(_ANOMALY_TEXT.get(a, a) for a in extra))

    gone = mark_changes(items, prev_items)
    shown, hidden = trim_for_display(items, max_items)
    out += ["", "## 当前界面"]
    if not shown:
        out.append("（没有可交互的条目 —— 可能页面还在加载，或该屏内容不由无障碍树暴露）")
    for it in shown:
        out.append(it.render())
    if hidden:
        out.append(f"（另有 {hidden} 项未显示，可滚动查看）")
    if gone:
        out.append("")
        out.append("上一步之后**消失**的条目：" + "；".join(gone))
        out.append("（消失多半是被浮层顶掉或页面局部替换，不是需要滚动去找）")

    if history:
        out += ["", "## 已执行"]
        for s in history:
            out.append(s.summarize())

    if politeness != "off" and env.ime_present:
        out += ["", "（用户正在输入。若本步不紧急，可以输出 wait 让路。）"]

    return "\n".join(out)
