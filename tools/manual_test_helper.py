#!/usr/bin/env python3
"""人工测试的陪跑工具：先验环境 → 倒计时 → 每次打扰都留证据 → 判定本次是否有效。

给「人在主屏打字、agent 在副屏干活」这个人工测试用。
你两只手在打字没法同时敲命令，所以先倒计时让你把手放上去。

**为什么要有先验与逐次取证**：
"我没感觉到打扰" 有三种可能 —— 护栏有效 / 动作压根没夺走焦点 / 那一刻你没在打字。
主观感受分不开这三者，所以这个工具不允许自己静默产出一个"一切正常"：

  · 跑之前先验四项，任一不满足就拒绝启动
  · **每次打扰都记 display 0 的焦点前后**——焦点没动 = 这次没制造打扰，不算数
  · **每次打扰都记输入框内容前后**——内容没动 = 那一刻你没在打字，不算数
  · 末尾按上面两项判定本次测试是否有效

    python tools/manual_test_helper.py --check            # 只先验
    python tools/manual_test_helper.py --restore true     # 护栏开（产品行为）
    python tools/manual_test_helper.py --restore false    # 阳性对照
"""

import argparse
import subprocess
import sys
import time

sys.path.insert(0, ".")
from harness import adbutil                                # noqa: E402
from harness.compress import compress                      # noqa: E402
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY = 0


def sh(*args: str) -> str:
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout


def focus0() -> str | None:
    return adbutil.focus_by_display().get(PRIMARY)


def field(tp: Transport):
    """主屏聚焦输入框：(有没有, 文字, 光标)。文字含未上屏的拼音（composing 串）。"""
    try:
        tree = build_tree(tp.observe(PRIMARY))
    except Exception:
        return False, None, None
    eds = [n for n in tree.nodes if n.editable]
    if not eds:
        return False, None, None
    n = next((x for x in eds if x.focused), eds[0])
    return bool(n.focused), (n.text or ""), [n.sel_start, n.sel_end]


def preflight(tp: Transport, display: int) -> bool:
    ok = True
    print("先验：")
    awake = "mWakefulness=Awake" in sh("shell", "dumpsys", "power")
    print(f"  {'✓' if awake else '✗'} 主屏醒着" + ("" if awake else "   ← 屏幕睡了，点击不会进输入框"))
    ok &= awake

    st = tp.state()
    pf = st.get("primary_focus") or {}
    # ⚠ 不能只看 primary_focus.editable：Compose 应用里 findFocus 返回的是
    # android.view.View 包装节点、editable=false，而真正聚焦的 EditText 在树里。
    # 只看它会把"环境明明是好的"误判成没准备好（实测 composetest 就是这样）。
    focused_edit, _, _ = field(tp)
    has = focused_edit or bool(pf.get("editable"))
    print(f"  {'✓' if has else '✗'} 主屏有聚焦的输入框   ({pf.get('pkg')})"
          + ("" if has else "   ← 点一下主屏输入框"))
    ok &= bool(has)

    ime = st.get("ime_present")
    print(f"  {'✓' if ime else '✗'} 输入法弹着" + ("" if ime else "   ← 把键盘调出来"))
    ok &= bool(ime)

    try:
        tgt = next((i for i in compress(build_tree(tp.observe(display))) if not i.blocked), None)
    except Exception as e:
        tgt = None
        print(f"  ✗ 副屏读不到：{e}")
    print(f"  {'✓' if tgt else '✗'} 副屏有可用目标" + (f"   ({tgt.label})" if tgt else ""))
    ok &= tgt is not None

    print("  " + ("→ 可以开始" if ok else "→ 先修上面 ✗ 的项"))
    return ok


def pick_target(tp: Transport, display: int, kind: str = "nav"):
    """挑打扰用的目标。

    ⚠ 动作类型决定了会不会破坏用户输入（E10）：
      scroll —— 不产生窗口/Activity 变更，实测**从不**打断 IME composing
      nav    —— 会导航的点击，实测会把未上屏的拼音强制提交
    默认给 nav：拿 scroll 去做人工测试，只会得到一句"没感觉到"，什么也证明不了。
    """
    items = compress(build_tree(tp.observe(display)))
    if kind == "scroll":
        for it in items:
            if it.kind == "list" and not it.blocked:
                return it, "SCROLL_FORWARD"
    for it in items:
        if it.kind == "button" and not it.blocked and "Navigate up" not in it.label:
            return it, "CLICK"
    for it in items:
        if not it.blocked:
            return it, "FOCUS"
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--restore", choices=["true", "false"])
    ap.add_argument("--check", action="store_true", help="只先验，不跑")
    ap.add_argument("--countdown", type=int, default=8)
    ap.add_argument("--every", type=float, default=4.0)
    ap.add_argument("--times", type=int, default=6)
    ap.add_argument("--action", choices=["scroll", "nav"], default="nav",
                    help="scroll=滚动副屏（E10 实测不破坏输入）；"
                         "nav=导航点击（会破坏，默认用它，否则测不到东西）")
    ap.add_argument("--display", type=int, default=None,
                    help="副屏 id；默认自动探测（scrcpy 每次重开 id 都会变）")
    args = ap.parse_args()

    ensure_forward()
    tp = Transport()
    # display id 每次都变（本次重开 scrcpy 就从 2 变成了 3），硬编码一定出错
    from harness.observe import pick_secondary_display
    display = args.display if args.display is not None else pick_secondary_display(tp.state())
    if display is None:
        print("没找到副屏。scrcpy 起了吗？"); return 1

    if args.check:
        return 0 if preflight(tp, display) else 1
    if not args.restore:
        ap.error("需要 --restore true|false（或 --check）")
    restore = args.restore == "true"

    if not preflight(tp, display):
        print("\n先验没过，拒绝启动 —— 这种状态下测出的『没感觉到打扰』没有意义。")
        return 1

    tgt, action = pick_target(tp, display, args.action)
    print(f"\n副屏目标: {tgt.render()}   动作: {action}")
    print(f"护栏 restore={restore}   每 {args.every}s 打扰一次，共 {args.times} 次\n")
    for i in range(args.countdown, 0, -1):
        print(f"  {i} …", end="\r", flush=True)
        time.sleep(1)
    print("  ▶ 开始打字！（鼠标点屏幕上的软键盘，连打拼音别提交）      \n", flush=True)

    stole = typed_at = 0
    rows = []
    for n in range(1, args.times + 1):
        time.sleep(args.every)
        tgt, action = pick_target(tp, display, args.action)
        if tgt is None:
            print(f"[{n}] 副屏没有可用目标，跳过")
            continue
        t_before = field(tp)[1]
        f_before = focus0()
        resp = tp.act(display, tgt.locator, action, restore=restore, verify_read=False)
        f_after = focus0()
        t_after = field(tp)[1]

        r = resp.get("restore") or {}
        was_typing = t_after != t_before          # 内容动了 = 那一刻你在打字

        # 「这次打扰真的发生了吗」在两组里要用**不同**的证据：
        #   restore=false：焦点会停在副屏，事后读得到 → 比对前后焦点
        #   restore=true ：夺焦点与归还在**同一次调用内**完成，事后读到的必然是
        #                  "焦点没变" —— 拿它当判据，等于给"护栏工作得最好"的情况判无效
        #                  （第一次人工测试就是这么误判的）。这一组的活性证据是：
        #                  设备侧抓到了主屏焦点持有者、并成功还了回去。
        #                  "动作会夺焦点"本身由独立实验确立：连滚不动的空动作都会夺。
        fp = resp.get("focus_probe") or {}
        if fp:
            # 设备侧就地读的证据：动作刚落地那一刻主屏持有者变了没有
            live = bool(fp.get("stole"))
            live_txt = ("夺焦点=是" if live else "❗焦点没动")
        elif restore:
            live = bool(r.get("attempted")) and r.get("ok") is not False
            live_txt = f"归还={r.get('ok')}" if r.get("attempted") else "❗没有焦点可还"
        else:
            live = f_after != f_before
            live_txt = "夺焦点=是" if live else "❗焦点没动"
        stole += live
        typed_at += was_typing

        # composing 有没有被打断：拼音的分段空格是最灵敏的指标 ——
        # 被强制上屏时空格会消失（E9 实测），而字数未必变
        sp_b, sp_a = (t_before or "").count(" "), (t_after or "").count(" ")
        broke = sp_b >= 3 and sp_a < sp_b - 1
        rows.append((n, resp["timing"].get("disturb_ms"), live, was_typing,
                     t_before, t_after, broke))
        print(f"[{n}/{args.times}] 窗口 {resp['timing'].get('disturb_ms')}ms"
              f"  {live_txt}"
              f"  输入框 {len(t_before or '')}→{len(t_after or '')} 字"
              f"  分段 {sp_b}→{sp_a}"
              f"{'  ❗composing 被打断' if broke else ''}"
              f"{'' if was_typing else '  ❗那一刻输入框没变化'}", flush=True)

    print("\n===== 本次测试是否有效 =====")
    label = "每次都有主屏焦点可还（环境是活的）" if restore else "每次都真的夺走了焦点"
    print(f"  {'✓' if stole == len(rows) else '✗'} {label}   {stole}/{len(rows)}")
    print(f"  {'✓' if typed_at >= max(1, len(rows) // 2) else '✗'} 打扰时你确实在打字   "
          f"{typed_at}/{len(rows)} 次输入框有变化")
    valid = stole == len(rows) and typed_at >= max(1, len(rows) // 2)
    if not valid:
        print("\n❌ 本次无效：打扰没落到你正在进行的输入上，"
              "『没感觉到』不能解读为『护栏有效』。")
        return 1
    print("\n✅ 本次有效。最终输入框内容：")
    broke_n = sum(1 for x in rows if x[6])
    print(f"   composing 被打断 {broke_n}/{len(rows)} 次"
          f"   {'← 输入被破坏' if broke_n else '← 全程未被打断'}")
    print(f"   最终输入框（{len(rows[-1][5] or '')} 字）：{rows[-1][5]!r}")
    print("\n   现在看四条：键盘在不在 / 候选条有没有被清 / 光标有没有跳 / 字有没有乱序")
    if not restore:
        print("\n   ⚠ 阳性对照组。E9 实测该组会把未上屏的拼音强制提交、候选上下文清零。")
        print("     若这轮毫发无伤，说明打扰恰好都落在你两次击键之间的空隙里 ——")
        print("     把 --every 调小（比如 1.5）让它落进击键流中间再试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
