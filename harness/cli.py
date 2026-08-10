"""入口。

分阶段自验（HARNESS-SPEC §10），每个子命令对应一个可独立验证的阶段：

    python -m harness.cli state                     # 阶段 1
    python -m harness.cli observe                   # 阶段 2/3
    python -m harness.cli act --sid 4 --action click  # 阶段 4/5（不经过 LLM）
    python -m harness.cli run "在设置里关闭深色主题"   # 阶段 8
    python -m harness.cli selftest                  # 离线，不需要设备
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import config
from .compress import compress
from .models import Item
from .observe import pick_secondary_display, self_check
from .planner import make_planner
from .trace import Trace
from .transport import Transport, TransportError, ensure_forward
from .tree import build_tree
from .verify import Snapshot, verify


def _tp(args) -> Transport:
    ensure_forward(args.port)
    return Transport(port=args.port)


def _secondary(tp: Transport, override: int | None) -> int:
    if override is not None:
        return override
    state = tp.state()
    sec = pick_secondary_display(state)
    if sec is None:
        raise SystemExit("没找到副屏。scrcpy --new-display 起了吗？"
                         "（虚拟屏随 scrcpy 进程消亡）")
    return sec


def cmd_state(args) -> int:
    tp = _tp(args)
    state = tp.state()
    print(json.dumps(state, ensure_ascii=False, indent=2))
    env = self_check(state, args.pkg, None)
    print(f"\n副屏推断: display {env.secondary_display} · {env.secondary_pkg}")
    print(f"主屏焦点: {env.primary_focus_pkg} · IME {'在' if env.ime_present else '不在'}")
    if env.anomalies:
        print("异常: " + "；".join(env.anomalies))
    return 0


def cmd_observe(args) -> int:
    tp = _tp(args)
    sec = _secondary(tp, args.display)
    tree = build_tree(tp.observe(sec))
    items = compress(tree)
    print(f"# display {sec} · {tree.pkg} · {tree.activity}")
    print(f"# nodes={len(tree.nodes)} items={len(items)} hash={tree.tree_hash} "
          f"mismatch={tree.hash_mismatch} truncated={tree.truncated}")
    for it in items:
        print(it.render())
        if args.locators:
            print(f"      locator: {it.locator.describe()}  "
                  f"(anchor={it.anchor_idx} target={it.target_idx})")
    if args.raw:
        print(json.dumps(tp.last_response, ensure_ascii=False, indent=2))
    return 0


def cmd_act(args) -> int:
    """不经过 LLM 的单步执行 —— locator 的解析要单独测，别跟 loop 一起调（§10 风险点）。"""
    tp = _tp(args)
    sec = _secondary(tp, args.display)
    tree = build_tree(tp.observe(sec))
    items = compress(tree)
    item: Item | None = next((i for i in items if i.sid == args.sid), None)
    if item is None:
        raise SystemExit(f"sid {args.sid} 不存在（本轮共 {len(items)} 条）")
    print(f"目标: {item.render()}")
    print(f"locator: {item.locator.describe()}")

    pre = Snapshot.from_item(item, tree.activity, tree.tree_hash, tree.window_count)
    resp = tp.act(sec, item.locator, args.action, args.value, restore=True)
    print(json.dumps(resp, ensure_ascii=False, indent=2))

    time.sleep(config.RECHECK_DELAY_MS / 1000.0)   # 单步调试直接等一次，够用
    probe = tp.probe(sec, item.locator)
    post_tree = build_tree(tp.observe(sec))
    post = Snapshot.from_probe(probe, post_tree.activity, post_tree.tree_hash,
                               post_tree.window_count)
    from .models import ActionResult
    v = verify(item, args.action, pre, post, ActionResult.from_json(resp), args.value)
    print(f"\nverdict: {v.result} · {v.predicate} · {v.detail}")
    return 0 if v.result != "FAIL" else 1


def cmd_run(args) -> int:
    from .loop import Loop
    tp = _tp(args)
    script = json.loads(args.script) if args.script else None
    if args.base_url:
        config.LLM_BASE_URL = args.base_url
    planner = make_planner(args.provider, args.model, script=script,
                           politeness=args.politeness)
    trace = Trace(args.task, enabled=not args.no_trace)

    def on_event(kind: str, msg: str) -> None:
        if kind == "observation" and not args.verbose:
            return
        print(f"[{kind}] {msg}", flush=True)

    loop = Loop(tp, planner, target_pkg=args.pkg, max_steps=args.max_steps,
                trace=trace, cross_check=not args.no_cross_check,
                free_app=args.free_app, on_event=on_event)
    res = loop.run(args.task)
    print(f"\n=== {res.status}: {res.reason} ===")
    for s in res.steps:
        print(" " + s.summarize())
    if res.run_dir:
        print(f"trajectory: {res.run_dir}")
    return 0 if res.status == "done" else 1


def cmd_selftest(args) -> int:
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py", top_level_dir=".")
    r = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if r.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="harness", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=config.ADB_FORWARD_PORT)
    p.add_argument("--pkg", default=config.TARGET_PKG)
    p.add_argument("--display", type=int, default=None, help="副屏 id（默认自动探测）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state").set_defaults(func=cmd_state)

    o = sub.add_parser("observe")
    o.add_argument("--locators", action="store_true", help="同时打印每条的 locator")
    o.add_argument("--raw", action="store_true", help="打印设备原始响应")
    o.set_defaults(func=cmd_observe)

    a = sub.add_parser("act")
    a.add_argument("--sid", type=int, required=True)
    a.add_argument("--action", default="click")
    a.add_argument("--value", default=None)
    a.set_defaults(func=cmd_act)

    r = sub.add_parser("run")
    r.add_argument("task")
    r.add_argument("--max-steps", type=int, default=config.MAX_STEPS)
    r.add_argument("--provider", default=config.LLM_PROVIDER)
    r.add_argument("--model", default=config.MODEL)
    r.add_argument("--base-url", default=config.LLM_BASE_URL,
                   help="OpenAI 兼容端点，如 https://api.deepseek.com。"
                        "不设会把 key 发给 api.openai.com 然后 401")
    r.add_argument("--politeness", default=config.POLITENESS,
                   choices=["off", "normal", "patient"])
    r.add_argument("--script", default=None,
                   help='provider=scripted 时的动作序列 JSON，如 \'[{"action":"click","target":2}]\'')
    r.add_argument("--no-trace", action="store_true")
    r.add_argument("--no-cross-check", action="store_true",
                   help="关掉 dumpsys 交叉校验（只在没有 adb shell 权限时用）")
    r.add_argument("--free-app", action="store_true",
                   help="不锁定目标包：启用 launch 动作，且副屏上不是目标 app 不再致命")
    r.add_argument("--verbose", action="store_true", help="打印每轮 observation 全文")
    r.set_defaults(func=cmd_run)

    sub.add_parser("selftest").set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except TransportError as e:
        print(f"传输失败: {e}", file=sys.stderr)
        print("检查：① 无障碍服务开着吗（改完代码要关掉再打开）"
              " ② adb forward 还在吗（设备重连会失效）", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
