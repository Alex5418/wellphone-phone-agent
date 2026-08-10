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
from .observe import app_items, build_observation, self_check
from .policy import ActionPolicy, launch_block_reason
from .planner import Planner, PlannerError
from .trace import Trace
from .transport import Transport, TransportError
from .tree import build_tree
from .verify import Snapshot, Verdict, cross_check_post_state, verify


SEP_RAW = chr(10) + "---" + chr(10)   # 多次尝试之间的分隔


class Loop:
    def __init__(self, transport: Transport, planner: Planner,
                 target_pkg: str = config.TARGET_PKG,
                 max_steps: int = config.MAX_STEPS,
                 trace: Trace | None = None,
                 cross_check: bool = True,
                 recheck_ms: int = config.RECHECK_DELAY_MS,
                 disturb_budget_ms: int = config.DISTURB_BUDGET_MS,
                 free_app: bool = False,
                 on_event=None):
        self.tp = transport
        self.planner = planner
        self.target_pkg = target_pkg
        self.free_app = free_app
        self.max_steps = max_steps
        self.trace = trace
        if trace is not None:
            # 让 trajectory 记下**实际**跑的后端，而不是 config 里的默认值
            trace.planner_info = planner.describe()
        self.cross_check = cross_check
        self.recheck_ms = recheck_ms    # 离线测试传 0，省得复读时空等
        self.policy = ActionPolicy(disturb_budget_ms)
        self.on_event = on_event or (lambda *a, **k: None)

    def _emit(self, kind: str, msg: str) -> None:
        self.on_event(kind, msg)

    def _observe(self, display):
        """带重试的 observe。

        窗口切换的瞬间 display 上可能一个窗口都没有 —— 设备侧如实报 NO_DISPLAY，
        但那是**过渡态**，不是"副屏没了"。D1 之后的 DeepSeek 实跑就栽在这里：
        点进子页面的那一瞬观测撞上空窗口期，整个 run 被判定为副屏消失而中止，
        而那一步其实是成功的。
        重试若干次仍为空，才是真的没了（比如 scrcpy 被关掉）。
        """
        last: Exception | None = None
        for attempt in range(config.OBSERVE_RETRY + 1):
            try:
                return build_tree(self.tp.observe(display))
            except TransportError as e:
                last = e
                if e.code != "NO_DISPLAY":
                    raise
                time.sleep(config.OBSERVE_RETRY_DELAY_MS / 1000.0)
        raise last  # type: ignore[misc]

    def _secondary_pkg(self, sec) -> str | None:
        """副屏当前的前台包名。读不到返回 None。"""
        try:
            state = self.tp.state()
        except (TransportError, ValueError):
            return None
        for d in state.get("displays", []):
            if d.get("id") == sec:
                wins = d.get("windows") or []
                return next((w.get("pkg") for w in wins if w.get("pkg")), None)
        return None

    def _await_launch(self, sec, pkg: str) -> tuple[bool, int]:
        """等副屏真的换成 pkg。返回 (确认到了吗, 等了多少 ms)。

        `am start` 立刻返回 —— 它只说明 intent 已下发，不说明窗口起来了。
        实测（`runs/2026-08-09T19-39-00`）日历要 3–4 s 才可观测，而 loop 紧接着
        就 observe，读到的还是旧 app，agent 因此判了 impossible —— 启动其实成功了。

        **等不到不许折成失败。** 返回 False 的含义是"未确认"，调用方要如实上报。
        """
        deadline = time.time() + config.LAUNCH_SETTLE_TIMEOUT_MS / 1000.0
        t0 = time.time()
        while time.time() < deadline:
            if (self._secondary_pkg(sec) or "") == pkg:
                return True, int((time.time() - t0) * 1000)
            time.sleep(config.LAUNCH_SETTLE_POLL_MS / 1000.0)
        return False, int((time.time() - t0) * 1000)

    def _read_post(self, display, locator):
        """独立重读一次：目标节点 + 整棵树。返回 (probe, tree|None, err|None)。"""
        if locator is None:
            probe = {"found": False, "skipped": "no locator (global action)"}
        else:
            try:
                probe = self.tp.probe(display, locator)
            except TransportError as e:
                probe = {"found": False, "error": str(e)}
        try:
            return probe, self._observe(display), None
        except (TransportError, ValueError) as e:
            return probe, None, f"复观测失败: {e}"

    def _judge(self, item, plan, pre, probe, post_tree, result):
        post = Snapshot.from_probe(
            probe,
            activity=(post_tree.activity if post_tree
                      else result.window_after.get("activity")),
            tree_hash=(post_tree.tree_hash if post_tree else None),
            window_count=(post_tree.window_count if post_tree
                          else result.window_after.get("window_count")),
        )
        if item is None:
            return verify_back(pre, post, result)
        v = verify(item, plan.action, pre, post, result, plan.value)

        # 文字锚点被成功的写入本身作废时（见 verify.py），probe 解析不到节点，
        # 只能判 UNKNOWN。但**观测层其实看得到那段文字** —— 重读的整棵树里
        # 就有一个节点的文字正好等于写入值。用它把 UNKNOWN 收敛成 PASS。
        # 这不是复用产生该结果的链路：树是独立重读的，与 act 的返回值无关。
        if (v.result == "UNKNOWN" and plan.action == "set_text" and plan.value
                and not post.found and post_tree is not None):
            if any((n.effective_text or "") == plan.value for n in post_tree.nodes):
                return Verdict("PASS", v.predicate,
                               f"定位器已被写入作废，但重读的树中存在文字为 "
                               f"{plan.value!r} 的节点")
        return v

    def run(self, task: str) -> RunResult:
        history: list[Step] = []
        last_hash: str | None = None
        last_claimed_ok = False
        consecutive_fail = 0
        consecutive_stall = 0
        parse_fail = 0
        secondary: int | None = None
        prev_items = None

        for step_n in range(1, self.max_steps + 1):
            # ---------- 观测（护栏） ----------
            # 可启动应用列表只有 free_app 模式才取 —— 默认路径一行 adb 都不许多调
            apps = adbutil.launchable_apps() if self.free_app else None
            try:
                state = self.tp.state()
                env = self_check(state, self.target_pkg, last_hash, None, last_claimed_ok,
                                 secondary, free_app=self.free_app)
                if env.fatal:
                    return self._abort(task, history, "环境自检失败: "
                                       + "；".join(env.anomalies))
                secondary = env.secondary_display
                tree: Tree = self._observe(secondary)
                env = self_check(state, self.target_pkg, last_hash, tree, last_claimed_ok,
                                 secondary, free_app=self.free_app)
                if env.fatal:
                    return self._abort(task, history, "环境自检失败: "
                                       + "；".join(env.anomalies))
            except (TransportError, ValueError) as e:
                return self._abort(task, history, f"观测失败: {e}")

            items = self.policy.annotate(compress(tree))
            obs = build_observation(task, env, items, history,
                                    politeness=self.planner.politeness,
                                    prev_items=prev_items, apps=apps)
            prev_items = items
            if self.trace:
                self.trace.text(step_n, "observation.txt", obs)
                self.trace.json(step_n, "env.json", {
                    "anomalies": env.anomalies, "secondary": env.secondary_display,
                    "pkg": env.secondary_pkg, "ime_present": env.ime_present,
                    "tree_hash": tree.tree_hash, "hash_mismatch": tree.hash_mismatch,
                    "items": [{"sid": i.sid, "label": i.label, "kind": i.kind,
                               "state": i.state, "blocked": i.blocked,
                               "locator": i.locator.to_json()}
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
                if self.trace:
                    # 失败这一步的原始输出照样落盘，否则事后没法判断模型输出了什么
                    self.trace.text(step_n, "llm_raw.txt",
                                    SEP_RAW.join(e.raws) or "(无输出)")
                    self.trace.json(step_n, "parse_error.json",
                                    {"error": str(e), "attempts": len(e.raws)})
                # 记进历史，让下一轮的 LLM 知道自己上一步输出没被接受
                history.append(Step(step_n, Plan("", "(解析失败)", None, None, False),
                                    None, None, None, note=f"输出无法解析：{e}"))
                if parse_fail >= config.MAX_PARSE_FAIL:
                    return self._abort(task, history, f"LLM 输出连续解析失败: {e}")
                continue
            except Exception as e:  # 网络等
                return self._abort(task, history, f"LLM 调用失败: {e}")
            if self.trace:
                self.trace.text(step_n, "llm_raw.txt", SEP_RAW.join(raws))
                if self.planner.last_meta:
                    self.trace.json(step_n, "llm_meta.json", self.planner.last_meta)
            self._emit("plan", f"{plan.action} target={plan.target} :: {plan.thought}")

            if plan.action == "finish" or plan.done:
                impossible = plan.outcome == "impossible"
                history.append(Step(step_n, plan, None, None, None,
                                    note="判定任务无法完成" if impossible else "判定任务完成"))
                return self._finish(task, history,
                                    "impossible" if impossible else "done",
                                    plan.thought or "LLM 判定收尾")

            if plan.action == "wait":
                # 这里直接 continue，**不碰 stall 计数**：用户正在输入时界面不变是预期的，
                # 让路等待不该被算成卡死
                history.append(Step(step_n, plan, None, None, None, note="让路等待用户输入"))
                last_claimed_ok = False
                time.sleep(config.WAIT_INTERVAL_S)
                continue

            # 护栏（不只写在 prompt 里）：back 结构上必然打在用户屏上，一律拒发。
            # parse_plan 已经不接受它了，这里是第二道 —— 换个 planner 实现也绕不过。
            if plan.action == "back":
                consecutive_stall += 1
                note = ("⛔ 拒绝执行 back：系统返回键作用于当前有焦点的 display，"
                        "而每步动作前焦点刚被归还到主屏，它必然退掉用户自己的页面")
                history.append(Step(step_n, plan, None, None, None, note=note))
                self._emit("blocked", note)
                if consecutive_stall >= config.MAX_CONSECUTIVE_STALL:
                    return self._abort(task, history, "反复选择已排除的动作")
                continue

            if plan.action == "launch":
                # launch 走 PC 侧 adb，不经过 act，因此没有焦点归还（F1 的核心约束）。
                # 它是唯一不受归还护栏保护的动作，必须在每一处拒绝/成功里写清楚。
                if not self.free_app:
                    history.append(Step(step_n, plan, None, None, None,
                                        note="⛔ 拒绝执行 launch：未启用 --free-app（默认关闭）"))
                    continue
                reason = launch_block_reason(env.ime_present)
                if reason is not None:
                    consecutive_stall += 1
                    note = f"⛔ 拒绝执行 launch：{reason}"
                    history.append(Step(step_n, plan, None, None, None, note=note))
                    self._emit("blocked", note)
                    if consecutive_stall >= config.MAX_CONSECUTIVE_STALL:
                        return self._abort(task, history, "反复选择已排除的动作")
                    continue
                app_entries = app_items(apps or [], items)
                entry = next((it for it in app_entries if it.sid == plan.target), None)
                if entry is None:
                    rng = (f"{app_entries[0].sid}–{app_entries[-1].sid}" if app_entries
                           else "本轮无可用应用条目")
                    history.append(Step(step_n, plan, None, None, None,
                                        note=f"launch target {plan.target} 不是可启动的应用"
                                             f"（有效范围 {rng}）"))
                    continue
                pkg = entry.label
                ok = adbutil.launch_app(pkg, secondary)
                # intent 下发 ≠ 窗口起来了。等副屏真的换过去再往下走，
                # 否则下一轮观测读到的还是旧 app（实测见 _await_launch 的注释）。
                settled, settle_ms = self._await_launch(secondary, pkg) if ok else (False, 0)
                if not ok:
                    note = "launch 失败：adb 未能下发"
                elif settled:
                    note = f"launch 成功，副屏 {settle_ms} ms 后变为 {pkg}"
                else:
                    # 三值：下发了但没确认。既不报成功也不报失败。
                    note = (f"⚠ launch 已下发，但 {settle_ms} ms 内副屏仍不是 {pkg} —— "
                            f"**未确认**，可能还在启动")
                note += "；⚠ 该动作未经护栏：无焦点归还、无 disturb_ms"
                history.append(Step(step_n, plan, entry, None, None, note=note))
                self._emit("launch", note)
                if self.trace:
                    self.trace.json(step_n, "launch.json", {
                        "pkg": pkg, "display": secondary, "ok": ok,
                        "settled": settled if ok else None, "settle_ms": settle_ms,
                        "restore": None, "guarded": False,
                        "note": "PC 侧 adb 启动，不经过 act 的原子归还",
                    })
                # launch 没有 disturb_ms 可记，也不更新卡死判据的环境基准
                last_claimed_ok = False
                continue

            item = next((i for i in items if i.sid == plan.target), None) \
                if plan.target is not None else None
            if item is None:
                # 把有效范围一起写进历史 —— 只说"不存在"，LLM 下一轮还是在猜
                rng = f"0–{items[-1].sid}" if items else "本轮无可用条目"
                history.append(Step(step_n, plan, None, None, None,
                                    note=f"短 ID {plan.target} 不存在（本轮有效范围 {rng}）"))
                continue

            # 护栏：被排除的目标一个动作都不许发。LLM 看得见排除理由，但推翻不了
            if item is not None and item.blocked:
                consecutive_stall += 1
                history.append(Step(step_n, plan, item, None, None,
                                    note=f"⛔ 拒绝执行：{item.blocked}"))
                self._emit("blocked", f"{item.label}: {item.blocked}")
                if consecutive_stall >= config.MAX_CONSECUTIVE_STALL:
                    return self._abort(task, history, "反复选择已排除的目标")
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

            notes: list[str] = []

            # 打扰窗口预算：与语言、与 app 都无关的实测判据。
            # 超预算的目标本轮拉黑 —— 静态名单必然漏，这一条兜住漏掉的。
            over = self.policy.record_disturbance(item, result.timing.get("disturb_ms"),
                                                  ime_present=env.ime_present) \
                if item else None
            if over:
                notes.append(over)
                self._emit("blocked", over)

            # ---------- 验证（护栏：独立重读，不复用 act 的判断） ----------
            # 先无延时读一次；没看到预期变化才等一下复读。
            # 快动作不付延时税，慢动作也不会被读成失败 ——
            # 而且「复读一次仍未变」比「等固定时长后读一次」是更强的证据。
            probe, post_tree, read_err = self._read_post(secondary, locator)
            if read_err:
                notes.append(read_err)
            verdict = self._judge(item, plan, pre, probe, post_tree, result)
            if verdict.result != "PASS":
                time.sleep(self.recheck_ms / 1000.0)
                probe2, post_tree2, err2 = self._read_post(secondary, locator)
                verdict2 = self._judge(item, plan, pre, probe2, post_tree2, result)
                if verdict2.result != verdict.result:
                    notes.append(f"首读 {verdict.result}（{verdict.detail}），"
                                 f"{self.recheck_ms}ms 后复读 {verdict2.result}")
                probe, verdict = probe2, verdict2
                if post_tree2 is not None:
                    post_tree = post_tree2

                # 第三次读：**用一次动作去撬开缓存**。
                # 有一类字段（实测 Gmail 撰写页正文）的无障碍读数**永远慢一个动作**：
                # 写入其实成功了，但 refresh() 无效、等多久都无效，
                # 必须在该节点上再发生一次 a11y 动作才会刷新出新值。
                # 上面那次复读等的是**时间**，对这类字段结构性地无效 ——
                # 于是每次都判 UNKNOWN，LLM 看到"没写进去"就反复重写，直到卡死中止。
                # 实测：set_text 后立刻读 = 旧值；做一次 FOCUS 再读 = 新值。
                # 选 FOCUS 是因为它作用在**副屏自己的**编辑器上，
                # 而 E15 已量化过这一动作类别（B/C 两组各 8 次，0 污染）。
                if verdict.result == "UNKNOWN" and locator is not None \
                        and plan.action == "set_text":
                    try:
                        self.tp.act(secondary, locator, "FOCUS",
                                    restore=True, verify_read=False)
                    except TransportError:
                        pass
                    else:
                        probe3, post_tree3, _ = self._read_post(secondary, locator)
                        verdict3 = self._judge(item, plan, pre, probe3, post_tree3, result)
                        if verdict3.result != "UNKNOWN":
                            notes.append(f"复读仍 UNKNOWN，聚焦刷新后读到 {verdict3.result}"
                                         "（该字段的无障碍读数慢一个动作）")
                            probe, verdict = probe3, verdict3
                            if post_tree3 is not None:
                                post_tree = post_tree3

            mism = cross_check_post_state(result, probe)
            if mism:
                notes.append(mism)

            # 焦点归还的交叉校验：走 dumpsys，刻意不复用 a11y 那条链路。
            #
            # 首次真机跑的结果说明了为什么要有这一条：display 0 上没有窗口自报
            # focused/active，设备侧 holder 恒为 null，自己判不了；而 dumpsys 明确
            # 显示主屏焦点仍在 Chrome —— 归还其实是成功的。两条链路合起来才有结论，
            # 而且**更可靠的那条赢**。
            if self.cross_check and result.restore_attempted:
                holder = adbutil.focus_holder_pkg(config.PRIMARY_DISPLAY)
                expect = result.restore_expect_pkg
                if holder is None:
                    notes.append("⚠ 归还无法确认（设备侧与 dumpsys 都读不到持有者）")
                elif result.restore_ok is None:
                    # 设备侧说不知道 —— 由 dumpsys 定论
                    result.restore_ok = bool(expect and holder == expect)
                    result.restore_confirmed_by = "dumpsys"
                    if not result.restore_ok:
                        notes.append(f"⚠ 归还失败：dumpsys 显示主屏焦点在 {holder}，"
                                     f"期望 {expect}")
                elif result.holder_after and holder != result.holder_after:
                    notes.append(f"⚠ 焦点持有者不一致: 设备自报 {result.holder_after}，"
                                 f"dumpsys 为 {holder}")
                if self.trace:
                    self.trace.json(step_n, "focus_crosscheck.json", {
                        "device_reported": result.holder_after,
                        "device_verdict": ("unknown" if result.restore_confirmed_by != "device"
                                           else result.restore_ok),
                        "dumpsys": holder,
                        "expect_pkg": expect,
                        "final_restore_ok": result.restore_ok,
                        "confirmed_by": result.restore_confirmed_by,
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
                    restore_ok=result.restore_ok,
                    restore_focus_ms=result.restore_focus_ms,
                    restore_total_ms=result.restore_total_ms,
                    disturb_ms=result.timing.get('disturb_ms'),
                    action_ms=result.timing.get("action_ms"),
                    total_ms=result.timing.get("total_ms"),
                    llm_ms=self.planner.last_latency_ms,
                    prompt_tokens=(self.planner.last_meta or {}).get("prompt_tokens"),
                    completion_tokens=(self.planner.last_meta or {}).get("completion_tokens"),
                    reasoning_tokens=(self.planner.last_meta or {}).get("reasoning_tokens"),
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

            # 独立的卡死判据：只看环境有没有动，不看 verdict。
            # 最常见的卡死形态是 LLM 反复点一个什么都不做的东西 —— 那种情况下
            # 「activity 与界面内容均无变化」返回的是 UNKNOWN（这是对的，分不出
            # 哑动作与本来就无副作用），于是 FAIL 计数永远是 0，一路跑到步数上限。
            # 这条判据不依赖判据推断准不准，因此比 FAIL 计数更可靠。
            stalled = (post_tree is not None
                       and post_tree.tree_hash == tree.tree_hash
                       and post_tree.activity == tree.activity)
            consecutive_stall = consecutive_stall + 1 if stalled else 0
            if consecutive_stall >= config.MAX_CONSECUTIVE_STALL:
                return self._abort(
                    task, history,
                    f"连续 {consecutive_stall} 步界面毫无变化（tree_hash 与 activity 均未动），"
                    "疑似卡死")

        return self._finish(task, history, "exhausted", f"达到步数上限 {self.max_steps}")

    # ---------------------------------------------------------------- 收尾

    def _finish(self, task: str, history: list[Step], status: str, reason: str) -> RunResult:
        if self.trace:
            self.trace.finish(status, reason,
                              extra={"llm_calls": self.planner.calls, "steps": len(history)})
        return RunResult(task, status, reason, history,
                         self.trace.dir if self.trace else None)

    def _abort(self, task: str, history: list[Step], reason: str) -> RunResult:
        self._emit("error", reason)
        if self.trace:
            self.trace.finish("aborted", reason,
                              extra={"llm_calls": self.planner.calls, "steps": len(history)})
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
