"""E19 · 主屏软键盘消失的归因 —— 高频轮询 + 每轮只下发一个动作。

## 为什么要有这个脚本

E18 复算了全部落盘 trajectory：`act` 响应里的 `ime.dismissed` 45 步 0 次为真，
而收起确实发生过。原因不是没触发，是**采样点选错了位置** ——
它只在单次 `act` 内采两点，而四次可定位的消失没有一次落在那个窗口里。
采样间隔就是 LLM 延迟（实测 1.5–149 s）。

本脚本做两件 E18 做不到的事：
  ① 把采样率提高三个数量级（目标 <200 ms，实测值会如实报出来）
  ② 每轮**只下发一个动作**，让「消失」能被归因到具体动作类型

## ⚠ 仪表必须先标定

`--check` 用已知的阳性/阴性状态标定轮询器：弹出键盘必须读到 True，
收起键盘必须读到 False。**两个都读到，这个轮询器才算活着。**
没标定过的一串 False 什么都不证明 —— 那正是 E18 里 `dismissed` 恒为 0 的教训。

## 用法

    python tools/exp_ime_dismissal.py --check
    python tools/exp_ime_dismissal.py --arm control   --times 20 --csv data/e19-control.csv
    python tools/exp_ime_dismissal.py --arm click_edit --times 20 --csv data/e19-click_edit.csv

环境同 E16：`PHONEAGENT_PORT=18760`，副屏跑 Gmail 撰写页，主屏 composetest 且输入框已聚焦。
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import config                      # noqa: E402
from harness.compress import compress           # noqa: E402
from harness.observe import pick_secondary_display  # noqa: E402
from harness.transport import Transport, TransportError, ensure_forward  # noqa: E402
from harness.tree import build_tree             # noqa: E402

ARMS = ("control", "click_button", "click_edit", "focus_edit", "set_text_edit", "rebuild")
WATCH_MS = 3000        # 动作后观察多久
SETTLE_MS = 800        # 确认键盘弹起后、下发动作前的静置
WRITE_VALUE = "READY"  # 不含标记字符，与 E15/E16 同惯例


def sh(*args: str, timeout: int = 15) -> str:
    try:
        p = subprocess.run(["adb", "shell", *args], capture_output=True,
                           text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


class ImePoller(threading.Thread):
    """后台轮询 display 0 的 IME 存在性。

    走 harness 的 `state()`（a11y 链路）而不是 `dumpsys input_method` ——
    后者实测单次 200–400 ms，做不到本实验需要的采样率。
    代价是它和被测对象共用一条链路，所以 `--check` 的标定不可跳过。
    """

    def __init__(self, port: int, interval_s: float = 0.05):
        super().__init__(daemon=True)
        self.tp = Transport(port=port)
        self.interval = interval_s
        self.samples: list[tuple[float, bool | None]] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def run(self) -> None:
        while not self._stop.is_set():
            t = time.time()
            try:
                v = self.tp.state().get("ime_present")
            except (TransportError, OSError, ValueError):
                v = None
            with self._lock:
                self.samples.append((t, v))
            time.sleep(max(0.0, self.interval - (time.time() - t)))

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=5)

    def snapshot(self) -> list[tuple[float, bool | None]]:
        with self._lock:
            return list(self.samples)

    def intervals_ms(self) -> list[float]:
        s = self.snapshot()
        return [(b[0] - a[0]) * 1000 for a, b in zip(s, s[1:])]

    def latest(self) -> bool | None:
        s = self.snapshot()
        return s[-1][1] if s else None

    def wait_for(self, want: bool, timeout_s: float) -> bool:
        end = time.time() + timeout_s
        while time.time() < end:
            if self.latest() is want:
                return True
            time.sleep(0.03)
        return False

    def first_after(self, t0: float, want: bool) -> float | None:
        """t0 之后第一次读到 want 的时刻。"""
        for t, v in self.snapshot():
            if t >= t0 and v is want:
                return t
        return None


def primary_tap(x: int = 540, y: int = 800) -> None:
    sh("input", "-d", "0", "tap", str(x), str(y))


def primary_hide_ime() -> None:
    sh("input", "-d", "0", "keyevent", "4")


def pick_items(tp: Transport, sec: int):
    tree = build_tree(tp.observe(sec))
    return tree, compress(tree)


def choose_target(items, arm: str):
    """按 arm 选一个目标条目。选不到返回 None —— 不要退而求其次换 app。"""
    if arm == "click_button":
        return next((i for i in items if i.kind == "button" and i.label), None)
    if arm in ("click_edit", "focus_edit", "set_text_edit"):
        return next((i for i in items if i.kind == "input"), None)
    return None


def run_arm(tp: Transport, poller: ImePoller, sec: int, arm: str, times: int,
            writer: csv.writer) -> list[dict]:
    rows = []
    for it in range(1, times + 1):
        # ① 把主屏键盘弄起来，并确认轮询器确实读到了 True
        primary_tap()
        if not poller.wait_for(True, 5.0):
            rows.append({"arm": arm, "iter": it, "ime_before": False,
                         "disappeared": "", "latency_ms": "", "disturb_ms": "",
                         "note": "SKIP 键盘没弹起来，本轮作废"})
            writer.writerow(rows[-1].values())
            continue
        time.sleep(SETTLE_MS / 1000.0)
        if poller.latest() is not True:
            rows.append({"arm": arm, "iter": it, "ime_before": False,
                         "disappeared": "", "latency_ms": "", "disturb_ms": "",
                         "note": "SKIP 静置后键盘已不在，本轮作废"})
            writer.writerow(rows[-1].values())
            continue

        # ② 下发恰好一个动作（control 组什么都不发）
        disturb = ""
        note = "ok"
        t0 = time.time()
        try:
            if arm == "control":
                pass
            elif arm == "rebuild":
                tree, items = pick_items(tp, sec)
                up = next((i for i in items if "Navigate up" in (i.label or "")), None)
                comp = next((i for i in items if "Compose" in (i.label or "")
                             and i.kind == "button"), None)
                if not (up and comp):
                    note = "SKIP 找不到 Navigate up / Compose"
                else:
                    t0 = time.time()
                    tp.act(sec, up.locator, "CLICK", restore=True, verify_read=False)
                    r = tp.act(sec, comp.locator, "CLICK", restore=True, verify_read=False)
                    disturb = (r.get("timing") or {}).get("disturb_ms", "")
            else:
                tree, items = pick_items(tp, sec)
                item = choose_target(items, arm)
                if item is None:
                    note = f"SKIP 副屏找不到 {arm} 需要的目标"
                else:
                    action = {"click_button": "CLICK", "click_edit": "CLICK",
                              "focus_edit": "FOCUS", "set_text_edit": "SET_TEXT"}[arm]
                    val = WRITE_VALUE if action == "SET_TEXT" else None
                    t0 = time.time()
                    r = tp.act(sec, item.locator, action, val,
                               restore=True, verify_read=False)
                    disturb = (r.get("timing") or {}).get("disturb_ms", "")
        except TransportError as e:
            note = f"TransportError {e}"

        # ③ 观察 WATCH_MS
        time.sleep(WATCH_MS / 1000.0)
        gone_at = poller.first_after(t0, False)
        row = {
            "arm": arm, "iter": it, "ime_before": True,
            "disappeared": 1 if gone_at else 0,
            "latency_ms": round((gone_at - t0) * 1000) if gone_at else "",
            "disturb_ms": disturb, "note": note,
        }
        rows.append(row)
        writer.writerow(row.values())
        print(f"  [{arm} {it}/{times}] 消失={row['disappeared']} "
              f"延迟={row['latency_ms']}ms disturb={disturb} {note}", flush=True)
    return rows


def cmd_check(tp: Transport, poller: ImePoller) -> int:
    """标定轮询器：必须同时读到已知阳性与已知阴性。"""
    print("① 采样率")
    time.sleep(2.0)
    iv = poller.intervals_ms()
    med = statistics.median(iv) if iv else float("inf")
    p95 = sorted(iv)[int(len(iv) * 0.95)] if len(iv) > 20 else float("inf")
    print(f"   样本 {len(iv)+1} 个，中位间隔 {med:.0f} ms，p95 {p95:.0f} ms")

    print("② 已知阳性：点主屏输入框，键盘应弹起")
    primary_tap()
    pos = poller.wait_for(True, 5.0)
    print(f"   读到 True: {'✓' if pos else '✗'}")

    print("③ 已知阴性：发 BACK 收起键盘")
    primary_hide_ime()
    neg = poller.wait_for(False, 5.0)
    print(f"   读到 False: {'✓' if neg else '✗'}")

    ok = pos and neg and med < 200
    print(f"\n{'✓ 仪表可用' if ok else '✗ 仪表不可用 —— 不要开跑正式组'}"
          f"（判据：阳性 ✓ + 阴性 ✓ + 中位间隔 < 200ms）")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="标定仪表，不跑正式组")
    ap.add_argument("--arm", choices=ARMS)
    ap.add_argument("--times", type=int, default=20)
    ap.add_argument("--csv", default=None)
    ap.add_argument("--port", type=int, default=config.ADB_FORWARD_PORT)
    ap.add_argument("--interval-ms", type=int, default=50)
    ap.add_argument("--display", type=int, default=None)
    a = ap.parse_args()

    ensure_forward(a.port)
    tp = Transport(port=a.port)
    sec = a.display if a.display is not None else pick_secondary_display(tp.state())
    if sec is None:
        print("没找到副屏。scrcpy --new-display 起了吗？", file=sys.stderr)
        return 2
    print(f"副屏 display={sec}  轮询间隔目标={a.interval_ms}ms")

    poller = ImePoller(a.port, a.interval_ms / 1000.0)
    poller.start()
    try:
        if a.check:
            return cmd_check(tp, poller)
        if not a.arm:
            print("要么 --check，要么 --arm", file=sys.stderr)
            return 2
        path = a.csv or f"e19-{a.arm}.csv"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["arm", "iter", "ime_before", "disappeared",
                            "latency_ms", "disturb_ms", "note"])
            rows = run_arm(tp, poller, sec, a.arm, a.times, w)
        valid = [r for r in rows if r["ime_before"]]
        hit = [r for r in valid if r["disappeared"] == 1]
        print(f"\n{a.arm}: 有效 {len(valid)}/{len(rows)}，消失 {len(hit)}")
        if hit:
            lat = [r["latency_ms"] for r in hit if r["latency_ms"] != ""]
            if lat:
                print(f"  消失延迟 中位 {statistics.median(lat):.0f}ms  范围 {min(lat)}–{max(lat)}ms")
        iv = poller.intervals_ms()
        if iv:
            print(f"  实际轮询中位间隔 {statistics.median(iv):.0f} ms")
        return 0
    finally:
        poller.stop()


if __name__ == "__main__":
    raise SystemExit(main())
