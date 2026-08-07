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
import random
import subprocess
import sys
import threading
import time

sys.path.insert(0, ".")
from harness.compress import compress                      # noqa: E402
from harness.observe import pick_secondary_display         # noqa: E402
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY = 0
MARK = "x"
# 软键盘上 'x' 键的坐标（1080×2400、Gboard 拼音布局）。布局一变就得重取，
# 所以先验里**必须**验证敲键器真的敲得进去 —— 敲不进去时读到的 0 毫无意义。
TAP_XY = (324, 2026)
DEL_XY = (994, 2026)   # 退格键，用来给 composing 缓冲封顶


def tap_once(xy: tuple[int, int]) -> None:
    """点一下软键盘。

    ⚠ 必须是 `input tap`（触摸事件进 IME 窗口，IME 再走 InputConnection），
    **不能**用 `input text` / `keyevent` —— 那是物理键盘语义，事件由 InputDispatcher
    直接投给焦点窗口，是 E7 里会污染的另一条链路，用它测软键盘等于测错了东西。
    用鼠标点 scrcpy 走的也是注入触摸，跟这里同源。
    坐标加抖动：同坐标快速重复可能被 IME 当成双击手势。
    """
    subprocess.run(["adb", "shell", "input", "-d", str(PRIMARY), "tap",
                    str(xy[0] + random.randint(-10, 10)),
                    str(xy[1] + random.randint(-6, 6))], capture_output=True)


class Tapper(threading.Thread):
    """后台连续敲键，代替人手。

    每 8 下插一次退格：拼音 composing 缓冲会一直堆积，实测堆到 800 多字时
    设备侧遍历超过 5s，`act` 直接 TIMEOUT。退格让缓冲维持在有界范围内，
    同时它本身也是击键，不影响"用户在打字"这个条件。
    """

    def __init__(self, xy: tuple[int, int], interval: float = 0.4):
        super().__init__(daemon=True)
        self.xy, self.interval, self.stop_evt, self.count = xy, interval, threading.Event(), 0

    def run(self) -> None:
        while not self.stop_evt.is_set():
            tap_once(DEL_XY if self.count % 8 == 7 else self.xy)
            self.count += 1
            self.stop_evt.wait(self.interval)

    def stop(self) -> None:
        self.stop_evt.set()


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


def primary_len(tp: Transport) -> int | None:
    """主屏**当前聚焦**输入框的字数（含未上屏的拼音）。读不到返回 None，不当成 0。

    走 `state().primary_focus.text_len` —— 设备侧对 `findFocus()` 拿到的那个节点现算。
    前面两版都错了，各错在不同地方，都值得记下来：

    ① 用 `observe` 读节点 text：**缓存陈旧**。实测连敲 5 下后 observe 仍报 1 字符，
       而屏幕上已有 18 个。没有 a11y 事件来打断缓存时它可以任意陈旧。
    ② 改用 probe 但**锁错了框**：composetest 有 3 个可编辑节点，
       `compress` 里第一个 input 是滚出视口的空框（bounds 在负 y）。
       于是敲键器敲了 160 下、真实聚焦框里已有 288 字，我却稳定读出 0，
       并据此把一次**命中了污染**的运行判成了作废。

    ③ 只看 `primary_focus.editable`：**Compose 应用里 `findFocus()` 返回的是
       `android.view.View` 包装节点、editable=false**，真正聚焦的 EditText 在树里。
       只信它会在 composetest 上时灵时不灵（同一个坑 manual_test_helper 里已经记过一次）。

    最终做法：state 能给就用 state；给不了就把主屏所有输入框逐个 probe，
    取 `focused=True` 的那个（probe 会 refresh，拿到的是新鲜值）。
    """
    try:
        pf = tp.state().get("primary_focus")
        if isinstance(pf, dict) and pf.get("editable") and isinstance(pf.get("text_len"), int):
            return pf["text_len"]
    except Exception:
        pass
    try:
        items = [i for i in compress(build_tree(tp.observe(PRIMARY))) if i.kind == "input"]
    except Exception:
        return None
    best = None
    for it in items:
        try:
            r = tp.probe(PRIMARY, it.locator)
        except Exception:
            continue
        if not r.get("found"):
            continue
        n = len(r.get("text") or "")
        if r.get("focused"):
            return n
        best = n if best is None else max(best, n)
    return best


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


def by_label(tp: Transport, display: int, label: str):
    """按标签找一个可用条目；找不到返回 None（不抛，调用方自己决定怎么办）。"""
    try:
        items = compress(build_tree(tp.observe(display)))
    except Exception:
        return None
    return next((i for i in items if label in i.label and not i.blocked), None)


def preflight(tp: Transport, display: int, auto: bool = False) -> bool:
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

    pt = primary_len(tp)
    print(f"  {'✓' if pt is not None else '✗'} 主屏有聚焦输入框"
          + (f"   当前 {pt} 字" if pt is not None else "   ← 点一下主屏输入框"))
    ok &= pt is not None

    if auto and pt is not None:
        # 敲键器必须先自证敲得进去。敲不进去时整场实验读到的 0 都没有意义 ——
        # 这正是「丢字计数器锁在常量上、稳定输出正确答案」那一类错误。
        before = pt
        for _ in range(5):
            tap_once(TAP_XY)
            time.sleep(0.4)
        time.sleep(0.6)
        after = primary_len(tp) or 0
        landed = after > before
        print(f"  {'✓' if landed else '✗'} 敲键器有效   敲 5 下，主屏 {before} → {after} 字"
              + ("" if landed else f"   ← 坐标 {TAP_XY} 没敲中，重新截图取 '{MARK}' 键位置"))
        ok &= landed

    print("  " + ("→ 可以开始" if ok else "→ 先修上面 ✗ 的项"))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["A", "B", "C", "D", "E"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--times", type=int, default=8)
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--countdown", type=int, default=8)
    # 默认 set_text：首次观测到的污染就发生在它上面，且窗口大一个数量级。
    # focus 保留作对照，但它的窗口只有 3–33ms，单用它得到的 0 说明不了问题。
    ap.add_argument("--action", choices=["set_text", "focus"], default="set_text")
    # 用来拆开 E 组里被我搅在一起的两个变量：Activity 重建 与 写入值。
    # E 组同时改了这两样，因此不能把结果归因给其中任何一个。
    ap.add_argument("--write", default=None, help="覆盖写入值（不含 x，否则与标记混淆）")
    ap.add_argument("--auto", action="store_true",
                    help="用 input tap 自动敲软键盘，代替人手（可无人值守跑大 n）")
    args = ap.parse_args()

    ensure_forward()
    tp = Transport()
    display = pick_secondary_display(tp.state())
    if display is None:
        print("没找到副屏")
        return 1

    if args.check:
        return 0 if preflight(tp, display, args.auto) else 1
    if not args.arm:
        ap.error("需要 --arm A|B|C（或 --check）")
    if not preflight(tp, display, args.auto):
        return 1

    want_editor = args.arm in ("B", "C", "D", "E")
    restore = args.arm != "C"
    desc = {"A": "对照：agent 聚焦按钮（非编辑器）· restore=true",
            "B": "待测：agent 聚焦 To 输入框（编辑器）· restore=true",
            "C": "阳性对照：agent 聚焦 To 输入框 · restore=false",
            "D": "瞬态：每轮让编辑器**重新获得**焦点，再 set_text · restore=true",
            "E": "重建：每轮**新建一个 ComposeActivity**，再对全新的 To 框首次写入"}[args.arm]
    print(f"\n===== 分组 {args.arm} · {desc} =====")
    print(f"副屏 display {display} · 动作 {args.times} 次，每 {args.every}s 一次\n")
    tapper = None
    if args.auto:
        tapper = Tapper(TAP_XY, interval=0.4)
        tapper.start()
        print(f"敲键器已启动（每 0.4s 点一次 '{MARK}' 键），无人值守。")
        time.sleep(1.5)
    else:
        # 倒计时的用途是让你先把手放上去：「开始！」的下一行就发第一个动作，
        # 那一刻必须已经在敲，否则第一个窗口是空的。
        print(f"**看到下面的数字就立刻开始点**软键盘上的 '{MARK}' 键（别等数到 1），")
        print("一直点到脚本打完结果为止。中途停手会被判作废。")
        for i in range(args.countdown, 0, -1):
            print(f"  {i} …", end="\r", flush=True)
            time.sleep(1)
        print("  开始！        ")

    # E 组照抄两次真实观测的写入值：真实邮箱地址会触发 Gmail 的联系人补全浮层，
    # 而 "READY" 不会 —— 这也是 A–D 与真实流程的差异之一。
    WRITE = args.write or ("alexw769829@gmail.com" if args.arm == "E" else "READY")
    if MARK in WRITE:
        print(f"写入值里含标记字符 '{MARK}'，会与污染混淆。换一个。")
        return 1
    base_sec = fields(tp, display)
    prim_len = [primary_len(tp) or 0]
    disturb: list[int] = []
    extras: list[str] = []   # 每次读回时超出写入值的部分

    for k in range(args.times):
        if args.arm == "E":
            # 两次真实观测的共同点：**刚创建出来的 ComposeActivity**，
            # 对一个全新的 To 框做第一次写入。A–D 全是在一个开了很久的撰写页上
            # 对同一个长期存在的框反复写 —— 那是稳态，没有 Activity 重建。
            # 用页面上的 Navigate up / Compose 两个按钮重建，不用 BACK
            # （BACK 走 performGlobalAction，跨屏语义未验证，见 loop.py:364）。
            if not by_label(tp, display, "Compose"):
                up = by_label(tp, display, "Navigate up")
                if up is not None:
                    tp.act(display, up.locator, "CLICK", restore=True, verify_read=False)
                    time.sleep(1.2)
            comp = by_label(tp, display, "Compose")
            if comp is None:
                print(f"  [{k+1}] 回不到收件箱，跳过")
                time.sleep(args.every)
                continue
            tp.act(display, comp.locator, "CLICK", restore=True, verify_read=False)
            time.sleep(1.5)

        tgt = pick(tp, display, want_editor)
        if tgt is None:
            print(f"  [{k+1}] 找不到目标，跳过")
            time.sleep(args.every)
            continue
        if args.arm == "E":
            r = tp.act(display, tgt.locator, "SET_TEXT", value=WRITE,
                       restore=True, verify_read=False)
        elif args.arm == "D":
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
        pt = primary_len(tp) or 0
        prim_len.append(pt)
        if args.action == "set_text":
            # 找那个我们刚写过的框：以 WRITE 开头的；多出来的部分即污染
            got = next((t for _, t, _ in fs if t.startswith(WRITE)), None)
            extra = got[len(WRITE):] if got else ""
            extras.append(extra)
            shown = f"读回 {got!r}" + (f"  ❗多出 {extra!r}" if extra else "")
        else:
            shown = f"副屏'{MARK}'累计 {marks(fs)}"
        print(f"  [{k+1}] {args.action} on {tgt.label[:18]:18} 打扰 {d}ms  {shown}  "
              f"主屏 {pt} 字")

    if tapper is not None:
        tapper.stop()
        print(f"\n敲键器共敲了 {tapper.count} 下")

    print()
    # 有效性②：**动作期间一直在打字**。看相邻采样的主屏长度增量，
    # 而不是"末值≠起始值"—— 后者在你开头敲一串然后停手时也会通过。
    grow = [b - a for a, b in zip(prim_len, prim_len[1:])]
    # 看**有没有变化**，不是"有没有增长"：拼音上屏提交时 `x x x x` 变成汉字，
    # 字数会减少。第一版把负增量算成"没在打字"，于是把一次命中污染的有效运行判成了作废。
    # 减少是提交，提交是打字的结果 —— 它是证据，不是反证。
    typing = sum(1 for g in grow if g != 0)
    typing_ok = typing >= max(1, len(grow) - 2)

    print("有效性：")
    print(f"  {'✓' if typing_ok else '✗'} 动作期间一直在打字   {len(grow)} 个间隔里 "
          f"{typing} 个主屏文本有变动   增量 {grow}"
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
