#!/usr/bin/env python3
"""E15 · 软键盘的击键会不会落进**副屏的输入框**。

## 为什么要重做这件事

E8 测过软键盘路径，八组里污染全是 0，并给出了机制解释：
「IME 连接绑在主屏编辑器上，失焦时解绑，不会转投到副屏；副屏带 FLAG_OWN_FOCUS
自成 display group，主屏 IME 本来也够不到它。」

**那八组的副屏跑的是 Settings —— 那一页根本没有输入框。**
E7 §4 早就写下了伏笔：「没有污染是因为副屏那一页没有输入框 —— 若有，
这 129 个就会变成污染。」E8 却把一个条件结论当成了全称结论。

2026-08-07 的一次真实 run 撞上了那个没测过的格子：agent 往 Gmail 的 To 字段
`SET_TEXT "alexw769829@gmail.com"`，独立 probe 读回
`alexw769829@gmail.comge` —— 多出的 `ge` 是用户当时正在打的拼音片段，
而用户用的是**鼠标点软键盘**。见 runs/2026-08-07T03-52-37/step-03/。

那次是 n=1、且"ge 来自用户"只是最省事的解释，没有直接证据。本实验来定这件事。

## 变量隔离

两组都停在**同一个 Gmail 撰写页**，同一动作类型（FOCUS）、同一 restore 设置。
唯一的差别是 agent 聚焦的目标是不是编辑器：

    A 对照     agent 聚焦一个**按钮**（非编辑器）      ← 相当于 E8 的条件
    B 待测     agent 聚焦 **To 输入框**（编辑器）      ← E8 漏掉的格子
    C 阳性对照 同 B，但 restore=false

不换 app、不换动作，所以任何差异只能来自"副屏被聚焦的是不是输入框"。

## 判定与有效性

标记字符默认 `x` —— 任务文本、邮箱地址、界面文案里都不出现它，出现即外来。

**没有下面三条，本次运行作废**（不允许静默产出一句"污染 0"）：

1. **读取通道有效** —— 先验里往副屏输入框写一个已知串再读回。
   读不回来就说明"读到 0 个 x"根本不能说明问题。
2. **你在动作期间一直在打字** —— 不是"变化过"就行。
   第一版判据只要求末值 ≠ 起始值，你在开头敲一串然后停手它照样判有效；
   而窗口里没有击键时读到 0 是必然的。改成看**相邻采样之间主屏文本长度有没有增长**，
   多数间隔都在增长才算数。
3. **确实制造了打扰** —— 每次动作都要有 disturb_ms。

## 动作类型（默认 set_text，不是 focus）

首次观测到污染是在 `SET_TEXT` 上、`disturb_ms=788`。
用 `FOCUS` 复跑时窗口只有 3–33ms，**小了一个数量级**，三组全 0 —— 那是条件没对上，
不能当成阴性结论。所以默认用 set_text 贴近原始条件；`--action focus` 保留作对照。

set_text 组的检出方式也更灵敏：写入一个已知串再读回，
**多出来的字符就是污染**（这正是首次观测的形态：写 `…@gmail.com`，读回 `…@gmail.comge`）。

用法
    python tools/exp_secondary_contamination.py --check
    python tools/exp_secondary_contamination.py --arm A
    python tools/exp_secondary_contamination.py --arm B
    python tools/exp_secondary_contamination.py --arm C
"""

import argparse
import sys
import time

sys.path.insert(0, ".")
from harness.compress import compress                      # noqa: E402
from harness.observe import pick_secondary_display         # noqa: E402
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY = 0
MARK = "x"


def fields(tp: Transport, display: int) -> list[tuple[int, str, bool]]:
    """该屏上所有可编辑节点的 (idx, 文字, 是否聚焦)。

    用 effective_text：空 EditText 的 text 其实是 hint，当成内容会凭空多出字符。
    """
    try:
        tree = build_tree(tp.observe(display))
    except Exception:
        return []
    return [(n.idx, n.effective_text or "", n.focused)
            for n in tree.nodes if n.editable]


def primary_text(tp: Transport) -> str | None:
    """主屏聚焦输入框的文字（含未上屏的拼音）。读不到返回 None，不当成空串。"""
    fs = fields(tp, PRIMARY)
    if not fs:
        return None
    foc = [t for _, t, f in fs if f]
    return foc[0] if foc else fs[0][1]


def marks(fs: list[tuple[int, str, bool]]) -> int:
    return sum(t.count(MARK) for _, t, _ in fs)


def pick(tp: Transport, display: int, want_editor: bool):
    """挑动作目标：want_editor 决定拿输入框还是按钮。"""
    items = compress(build_tree(tp.observe(display)))
    if want_editor:
        for it in items:
            if it.kind == "input" and not it.blocked:
                return it
        return None
    for it in items:
        if it.kind == "button" and not it.blocked and "Send" not in it.label \
                and "Navigate up" not in it.label:
            return it
    return None


def preflight(tp: Transport, display: int) -> bool:
    ok = True
    print("先验：")

    ed = pick(tp, display, want_editor=True)
    print(f"  {'✓' if ed else '✗'} 副屏有输入框" + (f"   ({ed.label[:30]})" if ed else
          "   ← 把 Gmail 停在撰写页（有 To / Subject 的那页）"))
    ok &= ed is not None

    btn = pick(tp, display, want_editor=False)
    print(f"  {'✓' if btn else '✗'} 副屏有按钮" + (f"   ({btn.label[:30]})" if btn else ""))
    ok &= btn is not None

    # 读取通道验证：写一个已知串再读回。读不回来 → "0 个 x" 毫无意义
    if ed is not None:
        probe_val = "READBACK" + MARK * 3
        tp.act(display, ed.locator, "SET_TEXT", value=probe_val,
               restore=True, verify_read=False)
        time.sleep(0.4)
        got = marks(fields(tp, display))
        readback = got >= 3
        print(f"  {'✓' if readback else '✗'} 读取通道有效   写入 3 个 '{MARK}'，读回 {got} 个"
              + ("" if readback else "   ← 读不到写进去的东西，本实验无法判定污染"))
        ok &= readback
        tp.act(display, ed.locator, "SET_TEXT", value="", restore=True, verify_read=False)

    pt = primary_text(tp)
    print(f"  {'✓' if pt is not None else '✗'} 主屏有聚焦输入框"
          + (f"   当前内容 {pt[-20:]!r}" if pt is not None else "   ← 点一下主屏输入框"))
    ok &= pt is not None

    print("  " + ("→ 可以开始" if ok else "→ 先修上面 ✗ 的项"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["A", "B", "C", "D"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--times", type=int, default=8)
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--countdown", type=int, default=8)
    # 默认 set_text：首次观测到的污染就发生在它上面，且窗口大一个数量级。
    # focus 保留作对照，但它的窗口只有 3–33ms，单用它得到的 0 说明不了问题。
    ap.add_argument("--action", choices=["set_text", "focus"], default="set_text")
    args = ap.parse_args()

    ensure_forward()
    tp = Transport()
    display = pick_secondary_display(tp.state())
    if display is None:
        print("没找到副屏")
        return 1

    if args.check:
        return 0 if preflight(tp, display) else 1
    if not args.arm:
        ap.error("需要 --arm A|B|C（或 --check）")
    if not preflight(tp, display):
        return 1

    want_editor = args.arm in ("B", "C", "D")
    restore = args.arm != "C"
    desc = {"A": "对照：agent 聚焦按钮（非编辑器）· restore=true",
            "B": "待测：agent 聚焦 To 输入框（编辑器）· restore=true",
            "C": "阳性对照：agent 聚焦 To 输入框 · restore=false",
            "D": "瞬态：每轮让编辑器**重新获得**焦点，再 set_text · restore=true"}[args.arm]
    print(f"\n===== 分组 {args.arm} · {desc} =====")
    print(f"副屏 display {display} · 动作 {args.times} 次，每 {args.every}s 一次\n")
    # 倒计时的用途是让你先把手放上去：「开始！」的下一行就发第一个动作，
    # 那一刻必须已经在敲，否则第一个窗口是空的。
    print(f"**看到下面的数字就立刻开始点**软键盘上的 '{MARK}' 键（别等数到 1），")
    print("一直点到脚本打完结果为止。中途停手会被判作废。")
    for i in range(args.countdown, 0, -1):
        print(f"  {i} …", end="\r", flush=True)
        time.sleep(1)
    print("  开始！        ")

    WRITE = "READY"          # 不含 MARK，方便识别多出来的字符
    base_sec = fields(tp, display)
    prim_len = [len(primary_text(tp) or "")]
    disturb: list[int] = []
    extras: list[str] = []   # 每次读回时超出写入值的部分

    for k in range(args.times):
        tgt = pick(tp, display, want_editor)
        if tgt is None:
            print(f"  [{k+1}] 找不到目标，跳过")
            time.sleep(args.every)
            continue
        if args.arm == "D":
            # 复现首次观测到污染的那个序列：编辑器先失焦，再重新获得焦点，然后写入。
            # B/C 是对着一个**已经聚焦**的框反复写 —— 那是稳态；
            # 若机制是「IME 的 InputConnection 在编辑器获得焦点那一刻改绑到副屏」，
            # 稳态里根本没有这个转换，测不到才是正常的。
            btn = pick(tp, display, want_editor=False)
            if btn is not None:
                tp.act(display, btn.locator, "FOCUS", restore=True, verify_read=False)
                time.sleep(0.6)
            tp.act(display, tgt.locator, "CLICK", restore=True, verify_read=False)
            time.sleep(0.6)
            r = tp.act(display, tgt.locator, "SET_TEXT", value=WRITE,
                       restore=True, verify_read=False)
        elif args.action == "set_text":
            r = tp.act(display, tgt.locator, "SET_TEXT", value=WRITE,
                       restore=restore, verify_read=False)
        else:
            r = tp.act(display, tgt.locator, "FOCUS", restore=restore, verify_read=False)
        d = (r.get("timing") or {}).get("disturb_ms")
        if isinstance(d, int):
            disturb.append(d)
        time.sleep(args.every)

        fs = fields(tp, display)
        pt = primary_text(tp) or ""
        prim_len.append(len(pt))
        if args.action == "set_text":
            # 找那个我们刚写过的框：以 WRITE 开头的；多出来的部分即污染
            got = next((t for _, t, _ in fs if t.startswith(WRITE)), None)
            extra = got[len(WRITE):] if got else ""
            extras.append(extra)
            shown = f"读回 {got!r}" + (f"  ❗多出 {extra!r}" if extra else "")
        else:
            shown = f"副屏'{MARK}'累计 {marks(fs)}"
        print(f"  [{k+1}] {args.action} on {tgt.label[:18]:18} 打扰 {d}ms  {shown}  "
              f"主屏 {len(pt)} 字")

    print()
    # 有效性②：**动作期间一直在打字**。看相邻采样的主屏长度增量，
    # 而不是"末值≠起始值"—— 后者在你开头敲一串然后停手时也会通过。
    grow = [b - a for a, b in zip(prim_len, prim_len[1:])]
    typing = sum(1 for g in grow if g > 0)
    typing_ok = typing >= max(1, len(grow) - 2)

    print("有效性：")
    print(f"  {'✓' if typing_ok else '✗'} 动作期间一直在打字   {len(grow)} 个间隔里 "
          f"{typing} 个主屏文本在增长   增量 {grow}"
          + ("" if typing_ok else "   ← 有窗口里你没在敲键，那时读到 0 是必然的"))
    print(f"  {'✓' if disturb else '✗'} 确实制造了打扰  {len(disturb)} 次有 disturb_ms"
          + (f"，中位 {sorted(disturb)[len(disturb)//2]}ms" if disturb else ""))
    if not (typing_ok and disturb):
        print("\n→ 本次运行作废，结果不作数。")
        return 1

    if args.action == "set_text":
        hits = [e for e in extras if e]
        print(f"\n结果：{len(extras)} 次写入里 **{len(hits)} 次读回有多余字符**")
        for e in hits:
            print(f"    多出 {e!r}")
        print("  " + ("❗污染成立 —— 用户的软键盘击键落进了副屏输入框"
                      if hits else "✓ 本组未观测到污染（前提：上面两条有效性都过了）"))
    else:
        base_m, total = marks(base_sec), marks(fields(tp, display))
        print(f"\n结果：副屏输入框里的 '{MARK}'   起始 {base_m} → 结束 {total}"
              f"   净增 **{total - base_m}**")
        print("  " + ("❗污染成立" if total - base_m > 0
                      else "✓ 本组未观测到污染（前提：上面两条有效性都过了）"))
    print("\nA/B/C 三组并排比。若 B、C 有污染而 A 没有，"
          "则决定因素是**副屏被聚焦的目标是不是编辑器**，E8 的全称结论要改成条件结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
