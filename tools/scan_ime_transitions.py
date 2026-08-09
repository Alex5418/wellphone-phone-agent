"""扫描 runs/ 下所有 trajectory，定位「主屏软键盘消失」发生在哪个区间（E18）。

不需要设备 —— 只读已落盘的数据，因此可反复复算。

两个采样源，粒度不同：

  env.json      每步**开头**采一次（loop 调 state() 时），字段 ime_present
  act_resp.json 每次 act **前后**各采一次，字段 ime.before / ime.after

于是一次「键盘消失」可以被夹在三种区间里：

  ① 某次 act 之内          ime.before=True 且 ime.after=False —— 仪表本该抓到
  ② 两次 act 之间          前一步 after=True，后一步 before=False
  ③ act 之外的观测/LLM 期间 env 说 True，同一步的 act 说 before=False
                           —— 这段时间里 agent 一个动作都没下发

用法：
    python tools/scan_ime_transitions.py            # 全部 run
    python tools/scan_ime_transitions.py <run 名>   # 单个 run 的逐步明细
"""

from __future__ import annotations

import glob
import json
import os
import sys


def load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def step_dirs(runs_dir: str = "runs") -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    pattern = os.path.join(runs_dir, "*", "step-*", "env.json")
    for path in sorted(glob.glob(pattern)):
        d = os.path.dirname(path)
        out.setdefault(os.path.basename(os.path.dirname(d)), []).append(d)
    for run in out:
        out[run].sort()
    return out


def read_step(d: str) -> dict:
    env = load(os.path.join(d, "env.json")) or {}
    req = load(os.path.join(d, "act_req.json")) or {}
    resp = load(os.path.join(d, "act_resp.json")) or {}
    args = req.get("args") or {}
    loc = args.get("locator") or {}
    return {
        "name": os.path.basename(d),
        "env_ime": env.get("ime_present"),
        "act_ime": resp.get("ime"),
        "action": args.get("action"),
        "cls": (loc.get("cls") or "").rsplit(".", 1)[-1] or None,
        "disturb_ms": (resp.get("timing") or {}).get("disturb_ms"),
    }


def classify(prev: dict, cur: dict) -> str:
    """键盘在 prev→cur 之间消失，落在哪个区间。

    顺序不能换：越靠前的分支证据越强。特别是 ③ 要在 ② 之前判 ——
    「前一步 act 时就已经是 False」比「后一步 act 时是 False」把区间夹得更窄。
    """
    p, c = prev["act_ime"], cur["act_ime"]

    # ① 仪表本该抓到的那一格：动作前有、动作后没了
    if p and p.get("before") is True and p.get("after") is False:
        return "① 该动作的 act 之内（dismissed 本该为 true）"

    # ④ 先判振荡：env 读到 False，可下一次 act 时又是 True —— 它自己回来了
    if c and c.get("before") is True:
        return "④ 消失后又自行恢复（env 读到 False，下次 act 时已回来）"

    # ③ 前一步 act 时就已经没了 → 消失落在该步 state() 与 act 之间，其间无动作
    if p and p.get("before") is False:
        return "③ act 之前 —— 该步观测/LLM 期间，其间无任何动作下发"

    # ③′ 前一步压根没有动作（wait / 解析失败步）
    if p is None and prev["action"] is None and c is not None:
        return "③ act 之外 —— 且前一步根本没有动作"

    if p is None or c is None:
        return "— 无法定位（该 run 早于仪表，或后续步无 act）"

    # ② 前一步 act 后还在，后一步 act 前没了：夹在两次 act 之间
    return "② 两次 act 之间（含前一步的验证重读与后一步的观测/LLM）"


def main(argv: list[str]) -> int:
    runs = step_dirs()
    if argv:
        want = argv[0]
        for d in runs.get(want, []):
            s = read_step(d)
            print(f"  {s['name']}  env_ime={s['env_ime']}  act_ime={s['act_ime']}  "
                  f"action={s['action']} cls={s['cls']} disturb={s['disturb_ms']}ms")
        return 0

    total_steps = fired = with_field = 0
    transitions = []
    for run, dirs in sorted(runs.items()):
        steps = [read_step(d) for d in dirs]
        for s in steps:
            total_steps += 1
            if s["act_ime"] is not None:
                with_field += 1
                if s["act_ime"].get("dismissed"):
                    fired += 1
        for prev, cur in zip(steps, steps[1:]):
            if prev["env_ime"] is True and cur["env_ime"] is False:
                transitions.append((run, prev, cur, classify(prev, cur)))

    print(f"步数合计 {total_steps}；带 ime 字段的 {with_field}；"
          f"**ime.dismissed=true 的步数 {fired}**")
    print(f"env 层 True->False 转换 {len(transitions)} 次\n")
    for run, prev, cur, verdict in transitions:
        print(f"{run}  {prev['name']} -> {cur['name']}")
        print(f"   前一步动作 = {prev['action']}  目标cls = {prev['cls']}  "
              f"disturb = {prev['disturb_ms']}ms")
        print(f"   前一步 act ime = {prev['act_ime']}")
        print(f"   后一步 act ime = {cur['act_ime']}")
        print(f"   -> {verdict}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
