"""动作空间的排除（护栏）。

验收标准是「用户当前正在进行的交互不被中断」。D1 实测全局配置变更类目标的
打扰窗口是 2526 ms，滚动是 12 ms —— 差两个数量级。3 秒按这个标准是硬失败，
所以这一族目标排除出动作空间，而不是标个"谨慎使用"。
"""

import json
import unittest

from harness import config
from harness.compress import compress
from harness.loop import Loop
from harness.models import Item, Locator
from harness.observe import build_observation, self_check
from harness.planner import Planner
from harness.policy import ActionPolicy, matches_global_config
from harness.tree import build_tree
from tests.fake_device import FakeTransport
from tests.test_loop import Script, sid_of


# checked=None 表示"这不是个可勾选控件"—— 与 compress 的语义一致
def item(label, kind="switch", checked=None, state=None, res_id=None):
    return Item(sid=0, label=label, kind=kind, state=state,
                locator=Locator("L1", resource_id="x"), anchor_idx=0, target_idx=0,
                checked=checked, res_id=res_id)


class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.p = ActionPolicy(config.DISTURB_BUDGET_MS)

    def test_global_config_switches_are_excluded(self):
        for label in ("Dark theme", "深色主题", "Night mode", "字体大小",
                      "Auto-rotate screen", "自动旋转", "Font size", "语言"):
            self.assertTrue(matches_global_config(label), label)
            self.assertIsNotNone(self.p.block_reason(item(label)), label)

    def test_navigation_into_those_pages_is_still_allowed(self):
        """点进「语言」页面只是导航，不改配置 —— 拦它是过度拦截。"""
        self.assertIsNone(self.p.block_reason(item("语言", kind="button")))
        self.assertIsNone(self.p.block_reason(item("Dark theme", kind="button")))

    def test_main_switch_bar_is_caught_by_id(self):
        """Settings 子页面顶部的主开关条：kind=button、无 On/Off 状态 ——
        只看 kind 拦不住。D2 实跑就是这么漏过去的，先付了 1533ms 才被实测预算兜住。"""
        it = item("Use Dark theme", kind="button",
                  res_id="com.android.settings:id/settingslib_main_switch_bar")
        self.assertIsNotNone(self.p.block_reason(it))

    def test_toggle_detected_by_on_off_state(self):
        it = item("Auto-rotate screen", kind="button", state="On")
        self.assertIsNotNone(self.p.block_reason(it))

    def test_page_title_is_not_a_toggle(self):
        """子页面的标题栏也叫 Dark theme，但它不是开关，拦它是过度拦截。"""
        it = item("Dark theme", kind="button",
                  res_id="com.android.settings:id/collapsing_toolbar")
        self.assertIsNone(self.p.block_reason(it))

    def test_ordinary_switches_untouched(self):
        for label in ("自动亮度", "Wi-Fi", "蓝牙", "Adaptive brightness"):
            self.assertIsNone(self.p.block_reason(item(label)), label)

    def test_measured_budget_catches_what_the_wordlist_misses(self):
        """静态名单靠文字匹配，必然漏。实测预算是与语言、与 app 都无关的兜底。"""
        it = item("Ein völlig unbekannter Schalter")
        self.assertIsNone(self.p.block_reason(it))
        warn = self.p.record_disturbance(it, 2526)
        self.assertIn("2526", warn)
        self.assertIn("排除出动作空间", warn)
        self.assertIsNotNone(self.p.block_reason(it))

    def test_within_budget_is_not_blocked(self):
        it = item("正常开关")
        self.assertIsNone(self.p.record_disturbance(it, 12))
        self.assertIsNone(self.p.block_reason(it))


class TestExclusionIsEnforced(unittest.TestCase):
    def test_loop_refuses_and_sends_nothing(self):
        tp = FakeTransport()
        sid = sid_of(tp, "深色主题", "switch")
        planner = Planner(Script([{"action": "click", "target": sid},
                                  {"action": "finish", "done": True}]))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("关深色主题")

        self.assertEqual(tp.acts, [])                     # 一个动作都没发出去
        self.assertTrue(tp.nodes[10]["checked"])          # 开关原封不动
        self.assertIn("⛔ 拒绝执行", res.steps[0].note)

    def test_repeatedly_picking_a_blocked_item_aborts(self):
        tp = FakeTransport()
        sid = sid_of(tp, "深色主题", "switch")
        planner = Planner(Script([{"action": "click", "target": sid}] * 10))
        res = Loop(tp, planner, trace=None, cross_check=False, recheck_ms=0).run("关深色主题")
        self.assertEqual(res.status, "aborted")
        self.assertEqual(tp.acts, [])

    def test_llm_sees_the_reason_not_just_a_missing_item(self):
        """排除的条目仍然呈现，只是标了 ⛔ —— 藏起来 LLM 只会一直找它。"""
        tp = FakeTransport()
        items = ActionPolicy(config.DISTURB_BUDGET_MS).annotate(
            compress(build_tree(tp.observe(tp.secondary))))
        obs = build_observation("关深色主题", self_check(tp.state(), "com.android.settings", None),
                                items, [])
        self.assertIn("⛔ 不可操作", obs)
        self.assertIn("打扰窗口", obs)
        # 整行的 button 没被误伤：进子页面不改配置
        row = next(i for i in items if i.label == "深色主题" and i.kind == "button")
        self.assertIsNone(row.blocked)


if __name__ == "__main__":
    unittest.main()
