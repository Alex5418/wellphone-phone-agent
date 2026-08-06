"""编排（HARNESS-SPEC §8）。

    观测 → 规划 → 执行 → 验证 →（回到观测）

四个环节里只有「规划」是策略层。其余三个是护栏，不接受配置关闭 ——
尤其是 restore：它在下面是写死的 True，没有开关。理由不是模型不够聪明，
而是失败模式的代价不对称（用户击键会灌进副屏工作区，那是正确性故障）。
"""

from __future__ import annotations

import time

from . import adbutil, config
from .compress import compress
from .models import ActionResult, Plan, RunResult, Step, Tree
from .observe import build_observation, self_check
from .planner import Planner, PlannerError
from .trace import Trace
from .transport import Transport, TransportError
from .tree import build_tree
from .verify import Snapshot, cross_check_post_state, verify


class Loop:
    def __init__(self, transport: Transport, planner: Planner,
                 target_pkg: str = config.TARGET_PKG,
                 max_steps: int = config.MAX_STEPS,
                 trace: Trace | None = None,
                 cross_check: bool = True,
                 on_event=None):
        self.tp = transport
        self.planner = planner
        self.target_pkg = target_pkg
        self.max_steps = max_steps
        self.trace = trace
        self.cross_check = cross_check
        self.on_event = on_event or (lambda *a, **k: None)

    def _emit(self, kind: str, msg: str) -> None:
        self.on_event(kind, msg)

    def run(self, task: str) -> RunResult:
        history: list[Step] = []
        last_hash: str | None = None
        last_claimed_ok = False
        consecutive_fail = 0
        parse_fail = 0
        secondary: int | None = None

        for step_n in range(1, self.max_steps + 1):
            # ---------- 观测（护栏） ----------
            try:
                state = self.tp.state()
                env = self_check(state, self.target_pkg, last_hash, None, last_claimed_ok,
                                 secondary)
                if env.fatal:
                    return self._abort(task, history, "环境自检失败: "
                                       + "；".join(env.anomalies))
                secondary = env.secondary_display
                tree: Tree = build_tree(self.tp.observe(secondary))
                env = self_check(state, self.target_pkg, last_hash, tree, last_claimed_ok,
                                 secondary)
                if env.fatal:
                    return self._abort(task, history, "环境自检失败: "
                                       + "；".join(env.anomalies))
            except (TransportError, ValueError) as e:
                return self._abort(task, history, f"观测失败: {e}")

            items = compress(tree)
            obs = build_observation(task, env, items, history,
                                    politeness=self.planner.politeness)
            if self.trace:
                self.trace.text(step_n, "observation.txt", obs)
                self.trace.json(step_n, "env.json", {
                    "anomalies": env.anomalies, "secondary": env.secondary_display,
                    "pkg": env.secondary_pkg, "ime_present": env.ime_present,
                    "tree_hash": tree.tree_hash, "hash_mismatch": tree.hash_mismatch,
                    "items": [{"sid": i.sid, "label": i.label, "kind": i.kind,
                               "state": i.state, "locator": i.locator.to_json()}
                              for i in items],
                })
            self._emit("observation", obs)

            # ---------- 规划（策略） ----------
            try:
                plan, raws = self.planner.decide(obs, items)
                parse_fail = 0
            except PlannerError as e:
                parse_fail += 1
                self._emit("error", f"LLM 输出解析失败: {e}")
                if parse_fail >= config.MAX_PARSE_FAIL:
                    return self._abort(task, history, f"LLM 输出连续解析失败: {e}")
                continue
            except Exception as e:  # 网络等
                return self._abort(task, history, f"LLM 调用失败: {e}")
            if self.trace:
                self.trace.text(step_n, "llm_raw.txt", "\n---\n".join(raws))
            self._emit("plan", f"{plan.action} target={plan.target} :: {plan.thought}")

            if plan.action == "finish" or plan.done:
                history.append(Step(step_n, plan, None, None, None, note="判定任务完成"))
                return self._finish(task, history, "done", plan.thought or "LLM 判定任务完成")

            if plan.action == "wait":
                history.append(Step(step_n, plan, None, None, None, note="让路等待用户输入"))
                last_claimed_ok = False
                time.sleep(config.WAIT_INTERVAL_S)
                continue

            item = next((i for i in items if i.sid == plan.target), None) if plan.target is not None else None
            if plan.action != "back" and item is None:
                history.append(Step(step_n, plan, None, None, None, note="短 ID 不存在"))
                continue

            # ---------- 执行（护栏：动作与归还原子绑定） ----------
            # BACK 没有目标节点，locator 传 None；设备侧走 performGlobalAction
            locator = item.locator if item else None
            pre = Snapshot.from_item(item, tree.activity, tree.tree_hash, tree.window_count) \
                if item else Snapshot(True, None, None, tree.activity, tree.tree_hash,
                                      tree.window_count)
            try:
                resp = self.tp.act(secondary, locator, plan.action, plan.value,
                                   restore=True,          # ← 护栏：写死，不接受配置关闭
                                   verify_read=True)
            except TransportError as e:
                return self._abort(task, history, f"动作下发失败: {e}")
            result = ActionResult.from_json(resp)
            if self.trace:
                self.trace.json(step_n, "act_req.json", self.tp.last_request)
                self.trace.json(step_n, "act_resp.json", resp)

            # ---------- 验证（护栏：独立重读，不复用 act 的判断） ----------
            if locator is None:
                probe = {"found": False, "skipped": "no locator (global action)"}
            else:
                try:
                    probe = self.tp.probe(secondary, locator)
                except TransportError as e:
                    probe = {"found": False, "error": str(e)}
            post_tree = None
            notes: list[str] = []
            try:
                post_tree = build_tree(self.tp.observe(secondary))
            except (TransportError, ValueError) as e:
                notes.append(f"复观测失败: {e}")

            post = Snapshot.from_probe(
                probe,
                activity=(post_tree.activity if post_tree else result.window_after.get("activity")),
                tree_hash=(post_tree.tree_hash if post_tree else None),
                window_count=(post_tree.window_count if post_tree
                              else result.window_after.get("window_count")),
            )
            verdict = verify(item, plan.action, pre, post, result, plan.value) if item else \
                verify_back(pre, post, result)

            mism = cross_check_post_state(result, probe)
            if mism:
                notes.append(mism)

            # 焦点归还的交叉校验：走 dumpsys，刻意不复用 a11y 那条链路
            if self.cross_check and result.restore_attempted:
                holder = adbutil.focus_holder_pkg()
                if holder is None:
                    notes.append("归还未能交叉校验（dumpsys 读不到）")
                elif result.holder_after and holder != result.holder_after:
                    notes.append(f"⚠ 焦点持有者不一致: 设备自报 {result.holder_after}，"
                                 f"dumpsys 为 {holder}")
                if self.trace:
                    self.trace.json(step_n, "focus_crosscheck.json", {
                        "device_reported": result.holder_after,
                        "dumpsys": holder,
                        "restore_ok": result.restore_ok,
                    })

            if self.trace:
                self.trace.json(step_n, "probe.json", probe)
                self.trace.json(step_n, "verdict.json", {
                    "result": verdict.result, "predicate": verdict.predicate,
                    "detail": verdict.detail, "notes": notes,
                })
                self.trace.metric(
                    step_n, action=plan.action, target=plan.target,
                    verdict=verdict.result,
                    restore_ok=result.restore_ok, restore_ms=result.restore_ms,
                    action_ms=result.timing.get("action_ms"),
                    total_ms=result.timing.get("total_ms"),
                    llm_ms=self.planner.last_latency_ms,
                )

            step = Step(step_n, plan, item, result, verdict, note="；".join(notes))
            history.append(step)
            self._emit("verdict", f"{verdict.result} · {verdict.detail}")

            # 基准是**动作前**那棵树（LLM 这一轮看到的那棵）。
            # 若拿动作后的复观测当基准，下一轮必然相同，"界面没变"就永远误报。
            last_hash = tree.tree_hash
            last_claimed_ok = result.action_ok
            consecutive_fail = consecutive_fail + 1 if verdict.result == "FAIL" else 0
            if consecutive_fail >= config.MAX_CONSECUTIVE_FAIL:
                return self._abort(task, history,
                                   f"连续 {consecutive_fail} 步动作未生效，疑似卡死")

        return self._finish(task, history, "exhausted", f"达到步数上限 {self.max_steps}")

    # ---------------------------------------------------------------- 收尾

    def _finish(self, task: str, history: list[Step], status: str, reason: str) -> RunResult:
        if self.trace:
            self.trace.finish(status, reason)
        return RunResult(task, status, reason, history,
                         self.trace.dir if self.trace else None)

    def _abort(self, task: str, history: list[Step], reason: str) -> RunResult:
        self._emit("error", reason)
        if self.trace:
            self.trace.finish("aborted", reason)
        return RunResult(task, "aborted", reason, history,
                         self.trace.dir if self.trace else None)


def verify_back(pre: Snapshot, post: Snapshot, result: ActionResult):
    from .models import Verdict
    if pre.activity and post.activity and pre.activity != post.activity:
        return Verdict("PASS", "activity_or_tree_changes",
                       f"activity → {post.activity.rsplit('.', 1)[-1]}")
    if pre.tree_hash and post.tree_hash and pre.tree_hash != post.tree_hash:
        return Verdict("PASS", "activity_or_tree_changes", "界面内容已变化")
    # BACK 走 performGlobalAction，作用于当前有焦点的 display —— 跨屏语义未验证。
    # 判不出来就说判不出来，不假装它落在副屏上。
    return Verdict("UNKNOWN", "activity_or_tree_changes",
                   "界面无变化；BACK 的跨屏语义未验证，可能作用在了主屏上")
