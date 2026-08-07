#!/usr/bin/env python3
"""E9 · 中文输入法连打长词组时，后台 agent 跑任务会发生什么。

E8 说明软键盘路径不会污染 agent 工作区。但那测的是**英文逐字提交**。
中文拼音不一样：一串拼音在提交之前一直处于 **composing 态** ——
未上屏的拼音串、候选条、光标位置，全是 IME 维持的中间状态。
中间状态比已提交的文字脆弱得多，这才是软键盘场景下真正该测的东西。

四条判据（动作前 / 后各测一次）：
    1. 键盘还在不在        display 0 上是否存在 TYPE_INPUT_METHOD 窗口
    2. 候选条有没有被清    IME 窗口里候选节点的文字列表
    3. 光标有没有跳        目标节点的 textSelectionStart/End
    4. 字有没有乱序        composing 串的内容与继续输入后的拼接结果

用法
    python tools/exp_pinyin_composing.py --restore true|false [--phrase zhonghuarenmingongheguo]
"""

import argparse
import json
import subprocess
import sys
import time

sys.path.insert(0, ".")
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY, SECONDARY = 0, 2

# Gboard QWERTY 键位中心（1080x2400，取自截图）
KEYS = {
    "q": (58, 1716), "w": (164, 1716), "e": (271, 1716), "r": (379, 1716),
    "t": (486, 1716), "y": (593, 1716), "u": (700, 1716), "i": (806, 1716),
    "o": (913, 1716), "p": (1020, 1716),
    "a": (112, 1870), "s": (218, 1870), "d": (325, 1870), "f": (432, 1870),
    "g": (538, 1870), "h": (644, 1870), "j": (752, 1870), "k": (859, 1870),
    "l": (966, 1870),
    "z": (218, 2024), "x": (325, 2024), "c": (432, 2024), "v": (539, 2024),
    "b": (646, 2024), "n": (752, 2024), "m": (859, 2024),
}
GLOBE = (324, 2180)     # 地球键：切换输入语言


def tap(x: int, y: int) -> None:
    subprocess.run(["adb", "shell", "input", "-d", "0", "tap", str(x), str(y)],
                   capture_output=True)


def type_pinyin(s: str, gap: float = 0.18) -> None:
    """一个字母一个字母地点屏幕 —— 真实软键盘输入，不走 input text。"""
    for ch in s:
        if ch in KEYS:
            tap(*KEYS[ch])
            time.sleep(gap)


def ime_state() -> dict:
    """键盘在不在 + 候选条内容。走广播 DUMP 读 IME 窗口（observe 刻意排除了它）。"""
    subprocess.run(["adb", "logcat", "-c"], capture_output=True)
    subprocess.run(["adb", "shell", "am", "broadcast", "-a",
                    "com.example.phoneagent.DUMP"], capture_output=True)
    time.sleep(1.5)
    out = subprocess.run(["adb", "logcat", "-d", "-s", "PHONEAGENT"],
                         capture_output=True, text=True).stdout
    ime_lines = [ln for ln in out.splitlines() if "inputmethod.latin" in ln]
    present = any("win pkg=com.google.android.inputmethod.latin" in ln for ln in ime_lines)
    # 候选条：IME 窗口里带文字、且可点的节点
    cands = []
    for ln in ime_lines:
        if "click=true" not in ln:
            continue
        if "'" not in ln:
            continue
        label = ln.split("'")[1]
        if label and label not in ("", "More features"):
            cands.append(label)
    # ⚠ candidates 恒为空：Gboard 把候选画在 canvas 上，a11y 树里没有节点。
    # 保留字段只为记录"确实读不到"，判据以截图为准。
    return {"keyboard_present": present, "candidates": cands[:12],
            "candidate_count": len(cands),
            "candidates_readable": False}


def field_state(tp: Transport) -> dict:
    """主屏目标输入框：文字 + 光标位置。"""
    tree = build_tree(tp.observe(PRIMARY))
    focused = [n for n in tree.nodes if n.editable and n.focused]
    n = focused[0] if focused else next((x for x in tree.nodes if x.editable), None)
    if n is None:
        return {"found": False}
    return {"found": True, "text": n.text, "len": len(n.text or ""),
            "sel": [n.sel_start, n.sel_end]}


def snapshot(tp: Transport, tag: str) -> dict:
    st = {"tag": tag, "field": field_state(tp), "ime": ime_state()}
    print(f"  [{tag}] 键盘={st['ime']['keyboard_present']} "
          f"候选={st['ime']['candidate_count']}个{st['ime']['candidates'][:5]} "
          f"文字={st['field'].get('text')!r} 光标={st['field'].get('sel')}", flush=True)
    return st


def screenshot(path: str) -> None:
    with open(path, "wb") as f:
        subprocess.run(["adb", "exec-out", "screencap", "-p"], stdout=f)


def three_step_task(tp: Transport, restore: bool, log: list) -> None:
    """副屏跑三步（screen timeout 那条已跑通的路径）。

    这里逐个下发 act 而不是走 loop：loop 里 restore=True 是写死的护栏，没有开关，
    而阳性对照必须能把它关掉。下发的是**和 loop 完全相同的设备侧调用**，
    两组之间只有 restore 一个变量不同。
    """
    from harness.compress import compress
    steps = ["Screen timeout", "30 seconds", "Navigate up"]
    for want in steps:
        items = compress(build_tree(tp.observe(SECONDARY)))
        it = next((i for i in items if i.label.startswith(want) and not i.blocked), None)
        if it is None:
            it = next((i for i in items if i.kind == "list"), None)
            if it is None:
                continue
            resp = tp.act(SECONDARY, it.locator, "SCROLL_FORWARD",
                          restore=restore, verify_read=False)
            log.append({"step": f"scroll(找不到 {want})",
                        "disturb_ms": resp["timing"].get("disturb_ms")})
        else:
            resp = tp.act(SECONDARY, it.locator, "CLICK", restore=restore, verify_read=False)
            log.append({"step": it.label, "disturb_ms": resp["timing"].get("disturb_ms"),
                        "restore_ok": (resp.get("restore") or {}).get("ok")})
        print(f"   · {log[-1]['step']}  打扰窗口 {log[-1]['disturb_ms']} ms", flush=True)
        time.sleep(1.2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--restore", choices=["true", "false"], required=True)
    ap.add_argument("--phrase", default="zhonghuarenmingongheguo")
    ap.add_argument("--gap", type=float, default=0.45, help="按键间隔秒（模拟真人连打）")
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()
    restore = args.restore == "true"

    ensure_forward()
    tp = Transport()
    result = {"restore": restore, "phrase": args.phrase}

    print(f"① 先打前半段，进入 composing 态")
    half = len(args.phrase) // 2
    type_pinyin(args.phrase[:half], args.gap)
    time.sleep(0.8)
    before = snapshot(tp, "动作前")
    if args.shots:
        screenshot(f"{args.shots}-before.png")

    print(chr(10) + f"② 一边继续打后半段，一边让副屏跑三步（restore={restore}）")
    import threading
    tail = args.phrase[half:]
    t = threading.Thread(target=type_pinyin, args=(tail, args.gap), daemon=True)
    t.start()
    time.sleep(0.6)          # 让打字先跑起来，动作落在击键流中间
    log: list = []
    three_step_task(tp, restore, log)
    t.join(timeout=30)
    time.sleep(1.2)
    result["actions"] = log

    after = snapshot(tp, "三步跑完")
    if args.shots:
        screenshot(f"{args.shots}-after.png")
    result["before"], result["after"] = before, after

    print(chr(10) + "===== 四条判据 =====")
    kb = "✓ 在" if after["ime"]["keyboard_present"] else "✗ 没了"
    print(f"1. 键盘还在不在      {kb}")
    # ⚠ 候选条读不到：Gboard 的候选是画在 canvas 上的，a11y 树里没有对应节点，
    # 这个计数器前后恒为 0 —— 它不是"候选条没变"，是**根本没测到**。
    # 不许拿一个恒为 0 的计数器下结论（丢字计数器锁常量的教训），改以截图为准。
    print("2. 候选条有没有被清   ⚠ a11y 读不到（Gboard 候选画在 canvas 上），"
          "以截图为准：见 *-before.png / *-after.png")
    print(f"3. 光标有没有跳      {before['field'].get('sel')} → {after['field'].get('sel')}")
    print(f"4. 字有没有乱序      期望 {args.phrase!r}")
    print(f"                     实际 {after['field'].get('text')!r}"
          f"   {'✓ 一致' if (after['field'].get('text') or '') == args.phrase else '✗ 不一致'}")
    if args.shots:
        with open(f"{args.shots}-result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
