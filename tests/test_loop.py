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
from harness.observe import build_observation, self_check
from harness.planner import Planner
from harness.trace import Trace
from harness.tree import build_tree
from tests.fake_device import FakeTransport


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

    def test_back_needs_no_target(self):
        """BACK 走 performGlobalAction，没有目标节点 —— locator 必须允许缺席。

        早先这里借了 items[0] 的 locator 充数：界面上一条可交互条目都没有时会崩，
        而设备侧"解析不到就不执行"的护栏会把 BACK 一起挡掉，表现为 BACK 永远不生效。
        """
        tp = FakeTransport()
        planner = Planner(Script([{"action": "back"},
                                  {"action": "finish", "done": True}]))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("退回上一页")
        self.assertEqual(res.status, "done")
        self.assertEqual(len(tp.acts), 1)
        self.assertIsNone(tp.acts[0]["locator"])
        self.assertTrue(tp.acts[0]["restore"])        # 护栏对全局动作同样生效
        self.assertEqual(res.steps[0].verdict.result, "PASS")

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
