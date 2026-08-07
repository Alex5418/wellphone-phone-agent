#!/usr/bin/env python3
"""E11 · 中文 composing 打断的 2×2 矩阵重跑（每格 ≥20 次有效运行）。

副屏动作（action: scroll|nav）与归还开关（restore: true|false）的四个组合
各跑 ≥20 次有效运行，判定主屏 IME 的 composing（拼音分段空格）有没有被打断。

单次运行固定流程（SUBTASK-E11）：
  1. 清场：force-stop composetest → 重启 → 点 Body 输入框
  2. 就绪校验（防起点丢字：IME 弹着 → 打 a 落 1 字 → 退格清 0）
  3. 逐键点软键盘打 zhonghuaren（0.3s/键）
  4. 记 before；!= "zhong hua ren" → 本次作废
  5. 后台线程续打 mingu（0.45s/键）
  6. 主线程按格子做 3 次副屏动作（1.2s 间隔），restore 按格子
  7. 等打字线程结束 + 1.5s，记 after
  8. 判定：before 空格 ≥2 且 after 空格 < before → 打断

用法
  python tools/exp_composing_matrix.py --verify-readiness        # 10 次清场打字验证
  python tools/exp_composing_matrix.py --positive-control        # nav×false 前 5 次
  python tools/exp_composing_matrix.py --cell nav --restore false --n 20
  python tools/exp_composing_matrix.py --cell scroll --restore true --n 20
  python tools/exp_composing_matrix.py --e11-2 --n 10            # 打断后点回能否恢复

所有运行逐条追加 docs/experiments/E11-raw.jsonl（含作废，标 valid:false）。
已跑过的格子从 jsonl 续跑，不会重复。
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, ".")
from harness.compress import compress                      # noqa: E402
from harness.observe import pick_secondary_display         # noqa: E402
from harness.transport import Transport, TransportError, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

PRIMARY = 0
COMPOSETEST = "com.example.composetest"

RAW = os.path.join("docs", "experiments", "E11-raw.jsonl")
PROGRESS = os.path.join("docs", "experiments", "E11-PROGRESS.md")

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
BACKSPACE = (994, 2024)

GAP_BEFORE = 0.3      # zhonghuaren 逐键间隔
GAP_CONT = 0.45       # 续打 mingu 逐键间隔


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", *args], capture_output=True)


def observe_retry(tp: Transport, display: int, tries: int = 6, delay: float = 0.6) -> dict:
    last = None
    for _ in range(tries):
        try:
            return tp.observe(display)
        except TransportError as e:
            last = e
            time.sleep(delay)
    raise last


def tap(x: int, y: int) -> None:
    sh("shell", "input", "-d", "0", "tap", str(x), str(y))


def _area(b) -> int:
    return (b[2] - b[0]) * (b[3] - b[1]) if b else 0


def _center(b) -> tuple[int, int]:
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def type_pinyin(s: str, gap: float) -> None:
    for ch in s:
        if ch in KEYS:
            tap(*KEYS[ch])
            time.sleep(gap)


def field_node(tp: Transport):
    tree = build_tree(observe_retry(tp, PRIMARY))
    eds = [n for n in tree.nodes if n.editable and n.visible]
    if not eds:
        return None
    n = next((x for x in eds if x.focused and x.effective_text), None)
    if n:
        return n
    n = next((x for x in eds if x.focused), None)
    if n:
        return n
    n = next((x for x in eds if x.effective_text), None)
    if n:
        return n
    return max(eds, key=lambda x: _area(x.bounds))


def read_text(tp: Transport) -> str:
    n = field_node(tp)
    return (n.effective_text or "") if n else ""


def focus_body(tp: Transport) -> bool:
    for _ in range(5):
        tree = build_tree(observe_retry(tp, PRIMARY))
        eds = [n for n in tree.nodes if n.editable and n.visible]
        if not eds:
            time.sleep(0.4)
            continue
        body = max(eds, key=lambda x: _area(x.bounds))
        if body.focused:
            return True
        tap(*_center(body.bounds))
        time.sleep(0.5)
    return False


def readiness(tp: Transport) -> tuple[bool, str]:
    t0 = time.time()
    while time.time() - t0 < 5.0:
        st = tp.state()
        if st.get("ime_present"):
            break
        time.sleep(0.3)
    else:
        return False, "IME 5s 未弹起"
    t0 = time.time()
    txt = ""
    while time.time() - t0 < 3.0:
        tap(*KEYS["a"])
        time.sleep(0.4)
        txt = read_text(tp)
        if len(txt) >= 1:
            break
    else:
        return False, f"打 a 未落地 text={txt!r}"
    t0 = time.time()
    while time.time() - t0 < 3.0:
        tap(*BACKSPACE)
        time.sleep(0.4)
        txt = read_text(tp)
        if len(txt) == 0:
            break
    else:
        return False, f"退格未清空 text={txt!r}"
    return True, "ok"


def keep_awake() -> None:
    sh("shell", "settings", "put", "system", "screen_off_timeout", "1800000")
    sh("shell", "input", "keyevent", "KEYCODE_WAKEUP")


def clear_and_ready(tp: Transport) -> tuple[bool, str]:
    keep_awake()
    sh("shell", "am", "force-stop", COMPOSETEST)
    time.sleep(0.6)
    sh("shell", "am", "start", "-n", f"{COMPOSETEST}/.MainActivity")
    t0 = time.time()
    while time.time() - t0 < 10.0:
        try:
            tree = build_tree(observe_retry(tp, PRIMARY, tries=2, delay=0.4))
        except TransportError:
            time.sleep(0.4)
            continue
        if any(n.editable and n.visible for n in tree.nodes):
            break
        time.sleep(0.4)
    time.sleep(0.6)
    if not focus_body(tp):
        return False, "点 Body 后无焦点"
    time.sleep(0.4)
    return readiness(tp)


def find_item(tp: Transport, sec: int, label: str):
    items = compress(build_tree(observe_retry(tp, sec)))
    return next((i for i in items if i.label == label and not i.blocked), None)


def ensure_display_settings(tp: Transport, sec: int) -> None:
    tree = build_tree(observe_retry(tp, sec))
    if tree.activity and "DisplaySettings" in tree.activity:
        return
    sh("shell", "am", "start", "--display", str(sec),
       "-a", "android.settings.DISPLAY_SETTINGS")
    time.sleep(1.5)


def scroll_action(tp: Transport, sec: int, restore: bool, log: list) -> None:
    for _ in range(3):
        items = compress(build_tree(observe_retry(tp, sec)))
        it = next((i for i in items if i.kind == "list" and not i.blocked), None)
        if it is None:
            log.append(None)
            print("   ⚠ 找不到可滚动区域，跳过", flush=True)
            continue
        resp = tp.act(sec, it.locator, "SCROLL_FORWARD", restore=restore, verify_read=False)
        ms = resp["timing"].get("disturb_ms")
        log.append(ms)
        print(f"   · scroll  打扰窗口 {ms} ms", flush=True)
        time.sleep(1.2)


def nav_action(tp: Transport, sec: int, restore: bool, log: list) -> None:
    ensure_display_settings(tp, sec)
    for want in ("Screen timeout", "30 seconds", "Navigate up"):
        keep_awake()
        it = find_item(tp, sec, want)
        if it is None:
            log.append(None)
            print(f"   ⚠ 找不到 {want}，跳过", flush=True)
            continue
        resp = tp.act(sec, it.locator, "CLICK", restore=restore, verify_read=False)
        ms = resp["timing"].get("disturb_ms")
        log.append(ms)
        print(f"   · {want}  打扰窗口 {ms} ms", flush=True)
        time.sleep(1.2)


def load_rows() -> list[dict]:
    rows: list[dict] = []
    if os.path.exists(RAW):
        with open(RAW, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    rows.append(json.loads(ln))
    return rows


def append_row(row: dict) -> None:
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    with open(RAW, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def progress(line: str) -> None:
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"[PROGRESS] {line}", flush=True)


def resume_cell(rows: list[dict], action: str, restore: bool) -> tuple[int, int]:
    runs = [r for r in rows if r.get("action") == action and r.get("restore") is restore]
    valid = sum(1 for r in runs if r.get("valid"))
    next_n = max([r.get("n", 0) for r in runs], default=0) + 1
    return valid, next_n


def run_once(tp: Transport, sec: int, action: str, restore: bool, n: int) -> dict:
    base = {"n": n, "action": action, "restore": restore}
    ok, msg = clear_and_ready(tp)
    if not ok:
        row = dict(base, before=None, after=None, sp_before=None, sp_after=None,
                   broke=None, disturb_ms=[], valid=False, reason=f"就绪失败 {msg}")
        return row
    type_pinyin("zhonghuaren", GAP_BEFORE)
    time.sleep(0.8)
    before = read_text(tp)
    if before != "zhong hua ren":
        return dict(base, before=before, after=None, sp_before=before.count(" "),
                    sp_after=None, broke=None, disturb_ms=[], valid=False,
                    reason=f"起点丢字 before={before!r}")
    t = threading.Thread(target=type_pinyin, args=("mingu", GAP_CONT), daemon=True)
    t.start()
    time.sleep(0.6)
    log: list = []
    if action == "nav":
        nav_action(tp, sec, restore, log)
    else:
        scroll_action(tp, sec, restore, log)
    t.join(timeout=30)
    time.sleep(1.5)
    after = read_text(tp)
    sp_b, sp_a = before.count(" "), after.count(" ")
    broke = sp_b >= 2 and sp_a < sp_b
    valid = len(after) > len(before)
    return dict(base, before=before, after=after, sp_before=sp_b, sp_after=sp_a,
                broke=broke, disturb_ms=log, valid=valid)


def run_cell(tp: Transport, sec: int, action: str, restore: bool, target_n: int,
             positive_gate: bool = False) -> None:
    rows = load_rows()
    done, n = resume_cell(rows, action, restore)
    need = target_n - done
    print(f"===== 格子 {action} × restore={restore}  已有效 {done}/{target_n}，"
          f"本次再跑 {need} =====", flush=True)
    invalid_streak = 0
    while need > 0:
        n += 1
        try:
            row = run_once(tp, sec, action, restore, n)
        except TransportError as e:
            print(f"  [run {n}] 动作中断 ({e.code})，重试一次", flush=True)
            try:
                row = run_once(tp, sec, action, restore, n)
            except TransportError as e2:
                row = dict(n=n, action=action, restore=restore, before=None, after=None,
                           sp_before=None, sp_after=None, broke=None, disturb_ms=[],
                           valid=False, reason=f"TransportError {e2.code}")
        append_row(row)
        print(f"  [run {n}] before={row.get('before')!r} after={row.get('after')!r} "
              f"sp {row.get('sp_before')}→{row.get('sp_after')} "
              f"broke={row.get('broke')} valid={row.get('valid')} "
              f"disturb={row.get('disturb_ms')}"
              + (f"  ⚠ {row.get('reason')}" if not row.get("valid") else ""), flush=True)
        if row.get("valid"):
            invalid_streak = 0
            need -= 1
            done += 1
        else:
            invalid_streak += 1
            if invalid_streak >= 5:
                print(f"!! 连续 {invalid_streak} 次作废，停跑。"
                      f"已有效 {done}/{target_n}。修就绪问题后再续跑。", flush=True)
                progress(f"格子 {action}×restore={restore} | 停跑 "
                         f"（连续作废 {invalid_streak}）已有效 {done}/{target_n}")
                return
        if positive_gate and done == 5:
            five = [r for r in load_rows()
                    if r.get("action") == action and r.get("restore") is restore and r.get("valid")]
            broke5 = sum(1 for r in five if r.get("broke"))
            print(f"---- 阳性对照（前 5 次有效）: 打断 {broke5}/5 ----", flush=True)
            if broke5 == 0:
                print("!! 阳性对照未复现（0/5），测试台状态存疑。停止矩阵。", flush=True)
                progress(f"阳性对照 nav×false 5 次 | FAIL 打断 0/5，测试台状态存疑，停止")
                return
            positive_gate = False
    progress(f"格子 {action}×restore={restore} | OK 有效 {done}/{target_n}")


def verify_readiness(tp: Transport) -> int:
    print("===== 就绪验证：10 次连续清场 + 打 zhonghuaren =====", flush=True)
    fails = []
    for i in range(1, 11):
        ok, msg = clear_and_ready(tp)
        if not ok:
            fails.append((i, f"就绪失败 {msg}"))
            print(f"[{i}] 就绪失败: {msg}", flush=True)
            continue
        type_pinyin("zhonghuaren", GAP_BEFORE)
        time.sleep(0.8)
        txt = read_text(tp)
        ok = txt == "zhong hua ren"
        print(f"[{i}] {txt!r}  {'OK' if ok else 'FAIL'}", flush=True)
        if not ok:
            fails.append((i, txt))
    if fails:
        print(f"!! 验证失败 {len(fails)}/10: {fails}", flush=True)
        progress(f"就绪验证 | FAIL {len(fails)}/10 {fails}")
        return 1
    print("10/10 全部得到 zhong hua ren", flush=True)
    progress("就绪验证 | OK 10/10 得到 zhong hua ren")
    return 0


def run_e11_2(tp: Transport, sec: int, target_n: int) -> None:
    print("===== E11-2 · 打断后点回输入框能否恢复 =====", flush=True)
    rows = load_rows()
    done = sum(1 for r in rows if r.get("tag") == "e11-2")
    n = max([r.get("n", 0) for r in rows if r.get("tag") == "e11-2"], default=0)
    need = target_n - done
    while need > 0:
        n += 1
        try:
            ok, msg = clear_and_ready(tp)
            if not ok:
                print(f"  [run {n}] 就绪失败 {msg}", flush=True)
                time.sleep(1)
                continue
            type_pinyin("zhonghuaren", GAP_BEFORE)
            time.sleep(0.8)
            before = read_text(tp)
            t = threading.Thread(target=type_pinyin, args=("mingu", GAP_CONT), daemon=True)
            t.start()
            time.sleep(0.6)
            log: list = []
            nav_action(tp, sec, False, log)
            t.join(timeout=30)
            time.sleep(1.5)
            after_break = read_text(tp)
            broke = before.count(" ") >= 2 and after_break.count(" ") < before.count(" ")
            base_len = len(after_break)
            tapped = focus_body(tp)
            time.sleep(0.5)
            t0 = time.time()
            ime_back = False
            while time.time() - t0 < 4.0:
                if tp.state().get("ime_present"):
                    ime_back = True
                    break
                time.sleep(0.3)
            guo_landed = False
            final = after_break
            if tapped and ime_back:
                for _ in range(3):
                    tap(*KEYS["g"])
                    time.sleep(0.4)
                    if len(read_text(tp)) > base_len:
                        guo_landed = True
                        break
                if guo_landed:
                    for ch in "uo":
                        tap(*KEYS[ch])
                        time.sleep(GAP_CONT)
                    time.sleep(1.0)
                    final = read_text(tp)
            row = {"n": n, "tag": "e11-2", "before": before, "after_break": after_break,
                   "final": final, "sp_before": before.count(" "),
                   "sp_break": after_break.count(" "), "sp_final": final.count(" "),
                   "broke": broke, "tapped": tapped, "ime_back": ime_back,
                   "guo_landed": guo_landed, "disturb_ms": log}
            append_row(row)
            print(f"  [run {n}] 断={broke} 点回={tapped} IME回={ime_back} guo落={guo_landed} "
                  f"before={before!r} 断后={after_break!r} 补救后={final!r} "
                  f"sp {row['sp_before']}→{row['sp_break']}→{row['sp_final']}", flush=True)
            done += 1
            need -= 1
        except TransportError as e:
            print(f"  [run {n}] 动作中断 ({e.code})，重试一次", flush=True)
            time.sleep(1)
    progress(f"E11-2 点回恢复 | OK {done}/{target_n}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify-readiness", action="store_true")
    ap.add_argument("--positive-control", action="store_true")
    ap.add_argument("--cell", choices=["nav", "scroll"])
    ap.add_argument("--restore", choices=["true", "false"])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--e11-2", action="store_true", dest="e11_2")
    args = ap.parse_args()

    if not (args.verify_readiness or args.positive_control or args.cell or args.e11_2):
        ap.error("需要 --verify-readiness / --positive-control / --cell / --e11-2")

    ensure_forward()
    tp = Transport()
    st = tp.state()
    sec = pick_secondary_display(st)
    if sec is None:
        print("没找到副屏。scrcpy 起了吗？")
        return 1
    print(f"副屏 display {sec}", flush=True)

    if args.verify_readiness:
        return verify_readiness(tp)
    if args.positive_control:
        run_cell(tp, sec, "nav", False, 5, positive_gate=True)
        return 0
    if args.cell:
        restore = args.restore == "true"
        run_cell(tp, sec, args.cell, restore, args.n)
        return 0
    if args.e11_2:
        run_e11_2(tp, sec, args.n)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
