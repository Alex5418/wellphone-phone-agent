#!/usr/bin/env python3
"""E7 · 打扰窗口期间用户击键的落点。

这是唯一直接对应验收标准（用户当前正在进行的交互不被中断）的实验：
前面测的都是"焦点在谁手里"，这里测的是**用户敲的字最后进了哪个输入框**。

场景
    主屏 display 0  composetest（Compose 写信界面，Body 输入框聚焦，IME 弹起）
    副屏 display 2  Settings 搜索页（搜索框聚焦）—— 即 agent 的工作区
    击键注入        adb shell input text，不带 -d：走**全局焦点**，
                    与物理键盘同语义（键盘没有屏幕归属）

四个分组
    A 对照     只打字，agent 不动     —— 验证计数器本身（这一组污染必须为 0）
    B 阳性对照 动作 + restore=false   —— 若污染是真的，这里必须复现
    C 护栏     动作 + restore=true    —— 要回答的问题
    D 最坏情况 全局配置变更 + restore  —— 3 秒打扰窗口

    B 不可省。只跑 C 看到"没有污染"什么也证明不了 ——
    可能是护栏有效，也可能是这套测法根本测不出污染（丢字计数器锁在常量上的教训）。

用法
    python tools/exp_keystroke_landing.py --arm A|B|C --chars 200
    python tools/exp_keystroke_landing.py --all
"""

import argparse
import json
import subprocess
import sys
import time

sys.path.insert(0, ".")
from harness.compress import compress                      # noqa: E402
from harness.models import Locator                         # noqa: E402
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY, SECONDARY = 0, 2
TYPE_CHAR = "x"
MS_PER_CHAR = 39.0          # 实测：单次 input text 调用内约 39ms/字符


def editable_lengths(tp: Transport, display: int) -> dict[int, int]:
    """该屏上所有可编辑节点的文本长度。hint 不算内容。"""
    tree = build_tree(tp.observe(display))
    return {n.idx: len(n.effective_text or "") for n in tree.nodes if n.editable}


def total(d: dict[int, int]) -> int:
    return sum(d.values())


def find_probe_action(tp: Transport, display: int) -> tuple[Locator, str, str] | None:
    """挑一个**无副作用**的动作来制造打扰：优先滚动，其次对输入框发 FOCUS。

    重点不是动作做了什么，而是"任何 a11y 动作都会夺焦点"（E4）。
    所以要挑一个不改变副屏状态的 —— 否则分组之间起点就不一样了。
    """
    items = compress(build_tree(tp.observe(display)))
    for it in items:
        if it.kind == "list":
            return it.locator, "SCROLL_FORWARD", it.label
    for it in items:
        if it.kind == "input":
            return it.locator, "FOCUS", it.label
    return None


def type_async(n: int) -> subprocess.Popen:
    """后台连续注入 n 个字符。不带 -d：走全局焦点，与物理键盘同语义。"""
    return subprocess.Popen(["adb", "shell", "input", "text", TYPE_CHAR * n],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_arm(arm: str, chars: int, fire_after_s: float) -> dict:
    ensure_forward()
    tp = Transport()

    pre_p = editable_lengths(tp, PRIMARY)
    pre_s = editable_lengths(tp, SECONDARY)
    probe = find_probe_action(tp, SECONDARY)

    proc = type_async(chars)
    time.sleep(fire_after_s)          # 让打字先跑起来，动作落在字符流中间

    action_info: dict = {"fired": False}
    t0 = time.time()
    if arm in ("B", "C"):
        if probe is None:
            proc.wait()
            raise SystemExit("副屏上找不到可用来制造打扰的无副作用目标")
        loc, act, label = probe
        resp = tp.act(SECONDARY, loc, act, restore=(arm == "C"), verify_read=False)
        action_info = {"fired": True, "restore": arm == "C", "action": act, "target": label,
                       "timing": resp.get("timing"), "restore_detail": resp.get("restore")}
    elif arm == "D":
        items = compress(build_tree(tp.observe(SECONDARY)))
        # 必须挑真正的开关，不能挑同名的标题栏 —— 标题点了什么都不会发生，
        # 那样量到的就不是"全局配置变更"的窗口
        from harness.policy import is_toggle_like, matches_global_config
        tgt = next((i for i in items
                    if matches_global_config(i.label) and is_toggle_like(i)), None)
        if tgt is None:
            proc.wait()
            raise SystemExit("副屏当前页面上没有深色主题开关，先把副屏切到显示设置页")
        resp = tp.act(SECONDARY, tgt.locator, "CLICK", restore=True, verify_read=False)
        action_info = {"fired": True, "restore": True, "target": tgt.label,
                       "timing": resp.get("timing"), "restore_detail": resp.get("restore")}
    fire_ms = int((time.time() - t0) * 1000)

    proc.wait()
    time.sleep(1.0)                   # 等最后几个字符落地

    post_p = editable_lengths(tp, PRIMARY)
    post_s = editable_lengths(tp, SECONDARY)
    landed_p = total(post_p) - total(pre_p)
    landed_s = total(post_s) - total(pre_s)

    return {
        "arm": arm,
        "chars_sent": chars,
        "landed_primary": landed_p,
        "landed_secondary_agent_workspace": landed_s,
        "lost": chars - landed_p - landed_s,
        "action": action_info,
        "action_call_ms": fire_ms,
        "disturb_ms": (action_info.get("timing") or {}).get("disturb_ms"),
        "expected_chars_at_risk": round(
            ((action_info.get("timing") or {}).get("disturb_ms") or 0) / MS_PER_CHAR, 1),
    }


ARM_DESC = {
    "A": "对照：只打字，agent 不动（验证计数器：污染必须为 0）",
    "B": "阳性对照：动作 + restore=false（污染若真实，必须在这里复现）",
    "C": "护栏：动作 + restore=true",
    "D": "最坏情况：全局配置变更 + restore=true（~3s 打扰窗口）",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=list(ARM_DESC))
    ap.add_argument("--all", action="store_true", help="按 A→B→C 顺序各跑一次")
    ap.add_argument("--chars", type=int, default=200)
    ap.add_argument("--fire-after", type=float, default=2.0)
    args = ap.parse_args()

    arms = ["A", "B", "C"] if args.all else [args.arm]
    if not arms or arms == [None]:
        ap.error("需要 --arm 或 --all")

    results = []
    for a in arms:
        print(f"\n===== 分组 {a} · {ARM_DESC[a]} =====", flush=True)
        r = run_arm(a, args.chars, args.fire_after)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)
        print(f"→ 发出 {r['chars_sent']} · 主屏 {r['landed_primary']} · "
              f"副屏(agent 工作区) {r['landed_secondary_agent_workspace']} · "
              f"丢失 {r['lost']}", flush=True)
        time.sleep(2)

    if len(results) > 1:
        print("\n===== 汇总 =====")
        print(f"{'分组':<4}{'发出':>6}{'主屏':>8}{'副屏(污染)':>12}{'丢失':>8}{'打扰窗口':>10}")
        for r in results:
            print(f"{r['arm']:<4}{r['chars_sent']:>6}{r['landed_primary']:>8}"
                  f"{r['landed_secondary_agent_workspace']:>12}{r['lost']:>8}"
                  f"{str(r['disturb_ms'] or '-'):>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
