#!/usr/bin/env python3
"""E14 · 主屏在看视频时，副屏 agent 夺焦点会不会让播放暂停 / 卡住。

前面所有"打扰"实验测的都是**打字**场景（最严苛，强依赖焦点）。
题面还有一条「不抢画面 · 用户屏幕不卡不跳」，浏览 / 观看类场景一直只有推论没有实测。
推论是"没有键盘就没有键盘可收"，但有一个具体的反面依据：
**有些 app 在 onWindowFocusChanged(false) 时会暂停自身逻辑（视频 / 游戏类常见）。**
主屏失焦 12–300ms 时播放会不会停，只能实测。

## 仪表的选择（四选二，三个被证伪）

| 仪表 | 结论 | 为什么 |
|---|---|---|
| `dumpsys gfxinfo` | ❌ 不能用 | 硬件加速视频走 SurfaceFlinger 直接合成，不进 app 的 HWUI 管线。视频**正在播**时它恒为 0 帧 —— 用它会得到"0 掉帧 = 完全不卡"这种漂亮的假结论 |
| `SurfaceFlinger --latency` | ❌ 读不到 | 本机模拟器上拿不到有效帧时间戳。**读不到就不用，不硬凑** |
| `media_session` 的 `position` | ❌ 不能用 | 实测懒更新：`state=PLAYING speed=1.0` 时 position 走 89ms 就冻住不动。它是带 `updated=` 时间戳的快照，app 只在事件时推送 |
| `media_session` 的 `state` | ✅ 用 | 直接回答"有没有变成 PAUSED" |
| **屏幕截图哈希** | ✅ 用 | 在设备上算 md5，不传图。**已验证**：播放中 4 次采样 4 个不同哈希；暂停后 4 次采样哈希完全相同 |

后两个都不依赖模拟器的图形加速路径。

## 三个分组（阳性对照不可省）

    A 对照     只播放，agent 不动作
    B 护栏     agent 动作 + restore=true
    C 阳性对照 agent 动作 + restore=false

C 组不可省：若连"不归还焦点"都不让视频停，B 组的"没停"什么也证明不了。

用法
    python tools/exp_video_disturbance.py --check
    python tools/exp_video_disturbance.py --arm A --seconds 40
"""

import argparse
import re
import subprocess
import sys
import time

sys.path.insert(0, ".")
from harness.compress import compress                      # noqa: E402
from harness.observe import pick_secondary_display         # noqa: E402
from harness.transport import Transport, ensure_forward    # noqa: E402
from harness.tree import build_tree                        # noqa: E402

STATES = {0: "NONE", 1: "STOPPED", 2: "PAUSED", 3: "PLAYING", 6: "BUFFERING",
          7: "ERROR", 8: "CONNECTING"}
KEYCODE_MEDIA_PLAY = 126


def sh(*args: str) -> str:
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout


def media_state() -> str | None:
    """PLAYING / PAUSED / …；读不到返回 None —— 不折成布尔。

    只读 state，不读 position：position 已实测为懒更新（见模块 docstring）。
    """
    out = sh("shell", "dumpsys", "media_session")
    m = re.search(r"state=PlaybackState \{state=(\w+)\(\d+\)", out)
    if m:
        return m.group(1)
    m = re.search(r"state=PlaybackState \{state=(\d+),", out)
    return STATES.get(int(m.group(1)), m.group(1)) if m else None


def frame_hash() -> str | None:
    """主屏画面指纹。md5 在设备上算，避免每次传 1.4MB PNG。"""
    out = sh("shell", "screencap -p | md5sum").strip()
    m = re.match(r"([0-9a-f]{32})", out)
    return m.group(1)[:12] if m else None


def sample() -> tuple[str | None, str | None]:
    return media_state(), frame_hash()


def preflight(autoplay: bool = True) -> bool:
    print("先验（两项都必须过 —— 视频没真播时测出来的『没停』没有意义）：")
    st = media_state()
    if st != "PLAYING" and autoplay:
        print(f"  · 当前 {st}，发一次 MEDIA_PLAY（走 session 通道，不碰焦点）")
        sh("shell", "input", "keyevent", str(KEYCODE_MEDIA_PLAY))
        time.sleep(2)
        st = media_state()
    ok_state = st == "PLAYING"
    print(f"  {'✓' if ok_state else '✗'} 播放状态 = {st}"
          + ("" if ok_state else "   ← 手动点一下播放键"))

    hs = []
    for _ in range(4):
        hs.append(frame_hash())
        time.sleep(1.2)
    uniq = len(set(h for h in hs if h))
    ok_frame = uniq >= 3
    print(f"  {'✓' if ok_frame else '✗'} 画面在变    4 次采样 {uniq} 个不同指纹   {hs}"
          + ("" if ok_frame else "   ← 画面冻着，没在播"))
    ok = ok_state and ok_frame
    print("  " + ("→ 可以开始" if ok else "→ 先把视频播起来"))
    return ok


def pick_target(tp: Transport, display: int):
    """副屏上挑个能动的目标。优先滚动列表（持续时间长，最像真实任务）。"""
    items = compress(build_tree(tp.observe(display)))
    for it in items:
        if it.kind == "list" and not it.blocked:
            return it, "SCROLL_FORWARD"
    for it in items:
        if not it.blocked:
            return it, "FOCUS"
    return None, None


def runs_of_frozen(samples: list[tuple[float, str | None, str | None]]) -> list[float]:
    """连续相同画面指纹的持续时长。播放中每次采样都该不同，长停顿 = 卡住。"""
    out, run = [], 0.0
    for (t1, _, h1), (t2, _, h2) in zip(samples, samples[1:]):
        if h1 is not None and h1 == h2:
            run += t2 - t1
        else:
            out.append(run)
            run = 0.0
    out.append(run)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", choices=["A", "B", "C"])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--every", type=float, default=5.0, help="B/C 组的动作间隔")
    args = ap.parse_args()

    if args.check:
        return 0 if preflight() else 1
    if not args.arm:
        ap.error("需要 --arm A|B|C（或 --check）")

    ensure_forward()
    tp = Transport()
    display = pick_secondary_display(tp.state())
    if display is None:
        print("没找到副屏")
        return 1
    if not preflight():
        print(chr(10) + "先验没过，拒绝启动。")
        return 1

    desc = {"A": "对照：只播放，agent 不动作",
            "B": "护栏：agent 动作 + restore=true",
            "C": "阳性对照：agent 动作 + restore=false"}[args.arm]
    print(chr(10) + f"===== 分组 {args.arm} · {desc} =====")
    print(f"副屏 display {display} · 观测 {args.seconds}s" + chr(10))

    samples: list[tuple[float, str | None, str | None]] = []
    acts: list[float] = []
    disturb: list[int] = []
    t0 = time.time()
    next_act = args.every if args.arm != "A" else 1e18
    while time.time() - t0 < args.seconds:
        st, h = sample()
        samples.append((time.time() - t0, st, h))
        if time.time() - t0 >= next_act:
            next_act += args.every
            tgt, action = pick_target(tp, display)
            if tgt is None:
                print("  · 副屏没有可动作目标，跳过这次")
            else:
                r = tp.act(display, tgt.locator, action,
                           restore=(args.arm == "B"), verify_read=False)
                d = (r.get("timing") or {}).get("disturb_ms")
                acts.append(time.time() - t0)
                if isinstance(d, int):
                    disturb.append(d)
                print(f"  [{len(acts)}] t={acts[-1]:.0f}s  {action} on "
                      f"{tgt.label[:22]}  打扰 {d}ms", flush=True)

    st, h = sample()
    samples.append((time.time() - t0, st, h))

    elapsed = time.time() - t0
    states = [s for _, s, _ in samples if s]
    bad = [t for t, s, _ in samples if s in ("PAUSED", "STOPPED")]
    frozen = runs_of_frozen(samples)
    ts = [t for t, _, _ in samples]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    interval = sum(gaps) / len(gaps) if gaps else 0.0

    print(chr(10) + f"经过 {elapsed:.1f}s · 采样 {len(samples)} 次"
          f"（平均间隔 {interval:.2f}s）· 动作 {len(acts)} 次"
          + (f" · 打扰合计 {sum(disturb)}ms（最大 {max(disturb)}ms）" if disturb else ""))
    print(f"  出现过的状态  {sorted(set(states)) or '读不到'}")
    print(f"  PAUSED/STOPPED  {len(bad)} 次采样"
          + (f"   ❗时刻 {[f'{t:.0f}s' for t in bad[:8]]}" if bad else "   ✓ 一次都没有"))
    thr = max(2.0, interval * 2.5)
    print(f"  最长画面冻结  {max(frozen):.1f}s   (阈值 {thr:.1f}s = 2.5×采样间隔)"
          + ("   ❗画面停过" if max(frozen) > thr else "   ✓ 画面一直在动"))
    print(chr(10) + "三组并排比。B/C 若出现 PAUSED，或冻结时长明显长于 A，"
          "说明夺焦点会打断播放。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
