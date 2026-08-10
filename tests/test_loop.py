"""端到端（离线）：编排、护栏、落盘。

这里最重要的两条断言不是"任务完成了"，而是：
  · 每一次 act 都带着 restore=True —— 护栏不可被策略层绕开
  · 归还失败必须出现在 observation 里 —— 不得静默
"""

import json
import os
import tempfile
import unittest

from harness import config
from harness.compress import compress
from harness.loop import Loop
from harness.models import Plan
from harness.observe import build_observation, self_check
from harness.planner import Planner
from harness.trace import Trace
from harness.tree import build_tree
from tests.fake_device import FakeTransport


class RawPlanner:
    """绕开 parse_plan，把 Plan 直接交给 loop。

    用来验证「loop 里那道护栏本身」而不是解析层 —— 只写在 prompt 或只挡在解析层的
    不算护栏，换个 planner 实现就绕过去了。这个类扮演的就是那个"换掉的实现"。
    """

    politeness = "off"

    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0
        self.last_latency_ms = 0
        self.last_meta = None

    def describe(self):
        return {"provider": "raw", "model": None, "endpoint": None}

    def decide(self, observation, items):
        self.calls += 1
        if not self.plans:
            return Plan("", "finish", None, None, True), ["(raw)"]
        return self.plans.pop(0), ["(raw)"]


class Script:
    def __init__(self, plans):
        self.plans = list(plans)
        self.prompts: list[str] = []      # 记下每次喂给"模型"的正文，供回灌断言用

    def complete(self, system, user):
        self.prompts.append(user)
        if not self.plans:
            return json.dumps({"action": "finish", "done": True})
        return json.dumps(self.plans.pop(0), ensure_ascii=False)


def sid_of(tp, label, kind):
    items = compress(build_tree(tp.observe(tp.secondary)))
    return next(i.sid for i in items if i.label == label and i.kind == kind)


class TestLoop(unittest.TestCase):
    def test_switch_task_end_to_end(self):
        tp = FakeTransport()
        sid = sid_of(tp, "自动亮度", "switch")
        planner = Planner(Script([
            {"thought": "打开自动亮度", "action": "click", "target": sid},
            {"thought": "已经是 On 了", "action": "finish", "done": True},
        ]))
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("打开自动亮度", root=d)
            res = Loop(tp, planner, trace=trace, cross_check=False, recheck_ms=0).run("打开自动亮度")

            self.assertEqual(res.status, "done", res.reason)
            # 开关真的翻转了，且判据是 PASS
            self.assertTrue(tp.nodes[23]["checked"])
            self.assertEqual(res.steps[0].verdict.result, "PASS")

            # 护栏：每次 act 都带 restore=True
            self.assertTrue(tp.acts)
            self.assertTrue(all(a["restore"] is True for a in tp.acts))

            # 落盘：answer 材料齐全
            step_dir = os.path.join(trace.dir, "step-01")
            for f in ("observation.txt", "llm_raw.txt", "act_req.json",
                      "act_resp.json", "probe.json", "verdict.json"):
                self.assertTrue(os.path.exists(os.path.join(step_dir, f)), f)
            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            self.assertEqual(meta["status"], "done")
            self.assertEqual(meta["config"]["restore"], "always (硬编码，无开关)")
            self.assertEqual(meta["metrics"][0]["verdict"], "PASS")

    def test_restore_failure_is_surfaced_not_swallowed(self):
        tp = FakeTransport()
        tp.restore_ok = False
        sid = sid_of(tp, "自动亮度", "switch")
        planner = Planner(Script([{"action": "click", "target": sid}]))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("打开自动亮度")
        step = res.steps[0]
        self.assertFalse(step.result.restore_ok)
        self.assertIn("归还失败", step.summarize())

        # 下一轮的 observation 必须显式标出来
        env = self_check(tp.state(), "com.android.settings", None)
        obs = build_observation("打开自动亮度", env, [], [step])
        self.assertIn("⚠ 归还失败", obs)

    def test_consecutive_failures_abort(self):
        """连续 3 步动作未生效 → 中止（疑似卡死），而不是把 25 步跑完。

        用「哑节点」建模：performAction 返回 true，但 checked 一动不动。
        工具说成功不算数，判据说了算。
        """
        tp = FakeTransport()
        tp.dumb = {23}
        sid = sid_of(tp, "自动亮度", "switch")
        planner = Planner(Script([{"action": "click", "target": sid}] * 6))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("点一个哑开关")
        self.assertEqual(res.status, "aborted")
        self.assertIn("卡死", res.reason)
        self.assertEqual(len(res.steps), 3)
        self.assertTrue(all(s.verdict.result == "FAIL" for s in res.steps))

    def test_stall_aborts_even_when_every_verdict_is_unknown(self):
        """最可能的卡死形态：LLM 反复点一个什么都不做的东西。

        这种情况下判据返回的是 UNKNOWN（正确 —— 分不出哑动作与本来就无副作用），
        所以 FAIL 计数永远是 0。必须有一条只看环境的独立判据兜住，
        否则就是安安静静跑满 max_steps。
        """
        tp = FakeTransport()
        sid = sid_of(tp, "网络和互联网", "button")
        tp.dumb = {4}                       # 点了没反应，且 activity 不变
        tp.activity = "com.android.settings.Settings"
        planner = Planner(Script([{"action": "click", "target": sid}] * 10))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("点一个不动的东西")

        self.assertEqual(res.status, "aborted")
        self.assertIn("界面毫无变化", res.reason)
        self.assertEqual(len(res.steps), config.MAX_CONSECUTIVE_STALL)
        # 关键：没有任何一步是 FAIL —— 老的计数器根本不会触发
        self.assertTrue(all(s.verdict.result == "UNKNOWN" for s in res.steps),
                        [s.verdict.result for s in res.steps])

    def test_wait_does_not_count_as_stall(self):
        """用户正在输入时界面不变是预期的，让路不该被算成卡死。"""
        tp = FakeTransport()
        tp.ime_present = True
        planner = Planner(Script([{"action": "wait"}] * 10))
        import harness.loop as loopmod
        orig, loopmod.time.sleep = loopmod.time.sleep, lambda s: None
        try:
            res = Loop(tp, planner, trace=None, max_steps=8, cross_check=False, recheck_ms=0).run("等")
        finally:
            loopmod.time.sleep = orig
        self.assertEqual(res.status, "exhausted")     # 跑满，而不是被判卡死
        self.assertNotIn("卡死", res.reason)

    def test_unknown_sid_tells_llm_the_valid_range(self):
        """短 ID 不存在时，回灌给 LLM 的错误必须带上有效范围。

        只说"不存在"，它下一轮还是在猜。这条错在解析层就被挡下了
        （loop 里的同名兜底因此基本走不到），所以范围要写在解析器的报错里。
        """
        tp = FakeTransport()
        items = compress(build_tree(tp.observe(tp.secondary)))
        script = Script([{"action": "click", "target": 99},
                         {"action": "click", "target": 0},
                         {"action": "finish", "done": True}])
        planner = Planner(script)
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("点不存在的 ID")

        self.assertEqual(res.status, "done")
        # 第二次尝试用的提示里带了范围
        retry_prompt = script.prompts[1]
        self.assertIn("99 不在本轮", retry_prompt)
        self.assertIn(f"有效范围 0–{items[-1].sid}", retry_prompt)
        # 纠正后正常下发，没有把错误的 ID 发到设备上
        self.assertEqual(len(tp.acts), 1)

    def test_back_never_reaches_the_device_through_a_normal_planner(self):
        """第一道：解析层拒绝 back，设备侧一个动作都收不到。"""
        tp = FakeTransport()
        planner = Planner(Script([{"action": "back"},
                                  {"action": "finish", "done": True}]))
        Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("退回上一页")
        self.assertEqual(tp.acts, [])

    def test_back_is_refused_by_the_loop_even_bypassing_the_parser(self):
        """back 已被排除出动作空间 —— 一个动作都不许发。

        它不是"跨屏语义未验证"，是结构上必然打错屏：每次 act 的顺序是
        「执行动作 → 归还焦点」，所以下一步派发时焦点已经在主屏上，而
        `performGlobalAction(GLOBAL_ACTION_BACK)` 作用于**当前有焦点的 display**。
        **归还越好使，BACK 越必然退掉用户自己的页面。**
        实测 `runs/2026-08-09T18-36-02/step-03`：holder_before=com.android.chrome、
        副屏 window_after 无变化 —— 用户的浏览器被退了一页。

        护栏在两处：parse_plan 不接受 back（下面单测），loop 再拒一次（本测）。
        只写在 prompt 里的不算护栏 —— 换个 planner 实现就绕过去了。
        """
        tp = FakeTransport()
        res = Loop(tp, RawPlanner([Plan("", "back", None, None, False)]),
                   trace=None, cross_check=False, recheck_ms=0).run("退回上一页")
        self.assertEqual(tp.acts, [])                       # 设备侧一个动作都没收到
        self.assertIn("⛔ 拒绝执行 back", res.steps[0].note)
        self.assertIsNone(res.steps[0].result)

    def test_back_is_not_a_parseable_action(self):
        from harness.planner import PlannerError, parse_plan
        with self.assertRaises(PlannerError) as cm:
            parse_plan('{"action": "back"}', [])
        self.assertIn("back", str(cm.exception))

    def test_repeatedly_choosing_back_aborts(self):
        """反复选已排除的动作要中止，不能一路空转到步数上限。"""
        tp = FakeTransport()
        res = Loop(tp, RawPlanner([Plan("", "back", None, None, False)] * 10),
                   trace=None, cross_check=False, recheck_ms=0).run("t")
        self.assertEqual(res.status, "aborted")
        self.assertEqual(tp.acts, [])

    def test_fatal_anomaly_aborts_immediately(self):
        tp = FakeTransport(secondary=6)
        tp.pkg = "com.android.chrome"      # 副屏上不是目标 app
        planner = Planner(Script([{"action": "click", "target": 0}]))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("t")
        self.assertEqual(res.status, "aborted")
        self.assertIn("target_app_not_on_secondary", res.reason)
        self.assertEqual(tp.acts, [])      # 一个动作都不许发

    def test_wait_does_not_touch_device(self):
        import harness.loop as loopmod
        tp = FakeTransport()
        tp.ime_present = True
        planner = Planner(Script([{"action": "wait"}, {"action": "finish", "done": True}]))
        orig, loopmod.time.sleep = loopmod.time.sleep, lambda s: None
        try:
            res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("等一下")
        finally:
            loopmod.time.sleep = orig
        self.assertEqual(res.status, "done")
        self.assertEqual(tp.acts, [])

    # ---------------- F1 · agent 自己启动 app ----------------

    def test_default_free_app_keeps_target_app_anomaly_fatal(self):
        """free_app 默认 False：副屏上不是目标 app 仍然致命，行为与改动前一致。"""
        tp = FakeTransport(secondary=6)
        tp.pkg = "com.android.chrome"
        env = self_check(tp.state(), "com.android.settings", None)
        self.assertTrue(env.fatal)
        self.assertIn("target_app_not_on_secondary", env.anomalies)

    def test_free_app_makes_target_app_anomaly_non_fatal(self):
        """free_app=True：同样的状态只是普通异常，loop 继续跑而不是中止。"""
        tp = FakeTransport(secondary=6)
        tp.pkg = "com.android.chrome"
        env = self_check(tp.state(), "com.android.settings", None, free_app=True)
        self.assertFalse(env.fatal)
        self.assertIn("target_app_not_on_secondary", env.anomalies)

        import harness.loop as loopmod
        orig = loopmod.adbutil.launchable_apps
        loopmod.adbutil.launchable_apps = lambda: []     # 测试不许碰真实 adb
        try:
            planner = RawPlanner([Plan("", "finish", None, None, True)])
            res = Loop(tp, planner, free_app=True, trace=None, cross_check=False,
                       recheck_ms=0).run("t")
        finally:
            loopmod.adbutil.launchable_apps = orig
        self.assertEqual(res.status, "done")

    def test_launch_refused_when_free_app_off(self):
        """free_app 默认关：LLM 输出 launch 被拒，adbutil.launch_app 一次都不许调。"""
        import harness.loop as loopmod
        calls = {"n": 0}
        orig = loopmod.adbutil.launch_app
        def counting(pkg, display):
            calls["n"] += 1
            return True
        loopmod.adbutil.launch_app = counting
        try:
            tp = FakeTransport()
            planner = RawPlanner([Plan("", "launch", 0, None, False),
                                  Plan("", "finish", None, None, True)])
            res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("启动 app")
        finally:
            loopmod.adbutil.launch_app = orig
        self.assertEqual(calls["n"], 0)
        self.assertIn("未启用 --free-app", res.steps[0].note)
        self.assertEqual(res.status, "done")

    def test_launch_refused_while_user_is_typing(self):
        """free_app=True 但 ime_present=True：launch 被拒，一次都不许调 adb。"""
        import harness.loop as loopmod
        calls = {"n": 0}
        orig_app, orig_apps = loopmod.adbutil.launch_app, loopmod.adbutil.launchable_apps
        def counting(pkg, display):
            calls["n"] += 1
            return True
        loopmod.adbutil.launch_app = counting
        loopmod.adbutil.launchable_apps = lambda: ["com.google.android.calendar"]
        try:
            tp = FakeTransport()
            tp.ime_present = True
            planner = RawPlanner([Plan("", "launch", 0, None, False),
                                  Plan("", "finish", None, None, True)])
            res = Loop(tp, planner, free_app=True, trace=None, cross_check=False,
                       recheck_ms=0).run("启动 app")
        finally:
            loopmod.adbutil.launch_app = orig_app
            loopmod.adbutil.launchable_apps = orig_apps
        self.assertEqual(calls["n"], 0)
        self.assertIn("⛔ 拒绝执行 launch", res.steps[0].note)
        self.assertEqual(res.status, "done")

    def test_launch_waits_until_the_secondary_actually_switches(self):
        """`am start` 立刻返回 ≠ 窗口起来了。

        实测 runs/2026-08-09T19-39-00：日历要 3–4 s 才可观测，loop 紧接着 observe
        读到的还是旧 app，agent 据此判了 impossible —— **启动其实成功了**。
        这里用「第 3 次查询才换过去」的假设备复现那个竞态。
        """
        import harness.loop as loopmod
        tp = FakeTransport()
        polls = {"n": 0}
        orig_state = tp.state

        def slow_state():
            polls["n"] += 1
            st = orig_state()
            if polls["n"] >= 3:            # 前两次还是旧 app，第三次才换过去
                st["displays"] = [dict(d, windows=[{"pkg": "com.google.android.calendar"}])
                                  if d.get("id") == tp.secondary else d
                                  for d in st["displays"]]
            return st

        tp.state = slow_state
        orig_launch, orig_apps = loopmod.adbutil.launch_app, loopmod.adbutil.launchable_apps
        loopmod.adbutil.launch_app = lambda pkg, display: True
        loopmod.adbutil.launchable_apps = lambda: ["com.google.android.calendar"]
        orig_sleep, loopmod.time.sleep = loopmod.time.sleep, lambda s: None
        app_sid = compress(build_tree(tp.observe(tp.secondary)))[-1].sid + 1
        try:
            planner = RawPlanner([Plan("", "launch", app_sid, None, False),
                                  Plan("", "finish", None, None, True)])
            res = Loop(tp, planner, free_app=True, trace=None, cross_check=False,
                       recheck_ms=0).run("打开日历")
        finally:
            loopmod.adbutil.launch_app = orig_launch
            loopmod.adbutil.launchable_apps = orig_apps
            loopmod.time.sleep = orig_sleep
        note = res.steps[0].note
        self.assertIn("副屏", note)
        self.assertIn("变为 com.google.android.calendar", note)
        self.assertNotIn("未确认", note)

    def test_launch_that_never_settles_is_unconfirmed_not_success(self):
        """等不到不许折成成功，也不许折成失败 —— 三值里的"未确认"。"""
        import harness.loop as loopmod
        tp = FakeTransport()
        orig_launch, orig_apps = loopmod.adbutil.launch_app, loopmod.adbutil.launchable_apps
        loopmod.adbutil.launch_app = lambda pkg, display: True
        loopmod.adbutil.launchable_apps = lambda: ["com.google.android.calendar"]
        orig_sleep, loopmod.time.sleep = loopmod.time.sleep, lambda s: None
        orig_to = config.LAUNCH_SETTLE_TIMEOUT_MS
        config.LAUNCH_SETTLE_TIMEOUT_MS = 30      # 别让离线测试真等 6 秒
        app_sid = compress(build_tree(tp.observe(tp.secondary)))[-1].sid + 1
        try:
            planner = RawPlanner([Plan("", "launch", app_sid, None, False),
                                  Plan("", "finish", None, None, True)])
            res = Loop(tp, planner, free_app=True, trace=None, cross_check=False,
                       recheck_ms=0).run("打开日历")
        finally:
            loopmod.adbutil.launch_app = orig_launch
            loopmod.adbutil.launchable_apps = orig_apps
            loopmod.time.sleep = orig_sleep
            config.LAUNCH_SETTLE_TIMEOUT_MS = orig_to
        self.assertIn("未确认", res.steps[0].note)
        self.assertNotIn("launch 成功", res.steps[0].note)

    def test_app_sids_follow_ui_items(self):
        """app 条目的 sid 接在界面条目最大 sid 之后，不重号。"""
        tp = FakeTransport()
        items = compress(build_tree(tp.observe(tp.secondary)))
        env = self_check(tp.state(), "com.android.settings", None)
        obs = build_observation("t", env, items, [],
                                apps=["com.android.settings", "com.google.android.calendar"])
        max_ui = items[-1].sid
        self.assertIn(f"## 可启动的应用（副屏当前：com.android.settings）", obs)
        self.assertIn(f"[{max_ui + 1}] com.android.settings", obs)
        self.assertIn(f"[{max_ui + 2}] com.google.android.calendar", obs)
        self.assertNotIn(f"[{max_ui + 1}] com.android.settings |", obs)   # app 条目没有 kind 后缀
        self.assertIn("不经过焦点归还护栏", obs)

    def test_successful_launch_surfaces_unguarded_warning(self):
        """成功 launch 后：历史条目、observation、launch.json 三处都暴露「未经护栏」。"""
        import harness.loop as loopmod
        calls = []
        orig_app, orig_apps = loopmod.adbutil.launch_app, loopmod.adbutil.launchable_apps
        loopmod.adbutil.launchable_apps = lambda: ["com.google.android.calendar"]
        def fake_launch(pkg, display):
            calls.append((pkg, display))
            return True
        loopmod.adbutil.launch_app = fake_launch
        try:
            tp = FakeTransport()
            items = compress(build_tree(tp.observe(tp.secondary)))
            app_sid = items[-1].sid + 1
            with tempfile.TemporaryDirectory() as d:
                trace = Trace("启动日历", root=d)
                planner = RawPlanner([Plan("", "launch", app_sid, None, False),
                                      Plan("", "finish", None, None, True)])
                res = Loop(tp, planner, free_app=True, trace=trace, cross_check=False,
                           recheck_ms=0).run("启动日历")
                self.assertEqual(res.status, "done")
                step = res.steps[0]
                self.assertIn("未经护栏", step.summarize())
                self.assertEqual(calls, [("com.google.android.calendar", tp.secondary)])

                env = self_check(tp.state(), "com.android.settings", None, free_app=True)
                obs = build_observation("启动日历", env, items, res.steps[:1])
                self.assertIn("未经护栏", obs)

                with open(os.path.join(trace.dir, "step-01", "launch.json"),
                          encoding="utf-8") as f:
                    launch = json.load(f)
                self.assertEqual(launch["pkg"], "com.google.android.calendar")
                self.assertEqual(launch["display"], tp.secondary)
                self.assertTrue(launch["ok"])
                self.assertIsNone(launch["restore"])
                self.assertFalse(launch["guarded"])
        finally:
            loopmod.adbutil.launch_app = orig_app
            loopmod.adbutil.launchable_apps = orig_apps


class TestObservation(unittest.TestCase):
    def test_reports_deviation_not_normality(self):
        tp = FakeTransport()
        items = compress(build_tree(tp.observe(6)))
        env = self_check(tp.state(), "com.android.settings", None)
        obs = build_observation("在设置中关闭深色主题", env, items, [])
        self.assertIn("## 任务", obs)
        self.assertIn("## 当前界面", obs)
        self.assertNotIn("⚠", obs)          # 一切正常时不该有告警噪声
        self.assertNotIn("## 已执行", obs)   # 没有历史就不写这一节
        # LLM 只该看到短 ID 与语义
        self.assertNotIn("resource_id", obs)
        self.assertNotIn("android.widget", obs)

    def test_secondary_display_is_discovered_not_hardcoded(self):
        for did in (2, 4, 5, 6):
            tp = FakeTransport(secondary=did)
            env = self_check(tp.state(), "com.android.settings", None)
            self.assertEqual(env.secondary_display, did)

    def test_missing_secondary_is_fatal(self):
        tp = FakeTransport()
        state = tp.state()
        state["displays"] = [state["displays"][0]]
        env = self_check(state, "com.android.settings", None)
        self.assertTrue(env.fatal)
        self.assertIn("secondary_display_missing", env.anomalies)

    def test_unchanged_tree_after_successful_action_is_flagged(self):
        tp = FakeTransport()
        tree = build_tree(tp.observe(6))
        env = self_check(tp.state(), "com.android.settings", tree.tree_hash, tree,
                         last_action_claimed_ok=True)
        self.assertIn("tree_unchanged_after_action", env.anomalies)
        obs = build_observation("t", env, [], [])
        self.assertIn("没有任何变化", obs)


if __name__ == "__main__":
    unittest.main()
