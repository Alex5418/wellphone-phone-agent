"""LLM 输出解析。约束是强的：解析不出来宁可失败，也不猜。"""

import json
import unittest

from harness.compress import compress
from harness.planner import Planner, PlannerError, parse_plan
from harness.tree import build_tree
from tests.fake_device import FakeTransport


class Flaky:
    """先吐一段不能解析的，再吐一段合法的 —— 用来验证"回灌错误再试一次"。"""

    def __init__(self, outs):
        self.outs = list(outs)
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.outs.pop(0)


class TestParse(unittest.TestCase):
    def setUp(self):
        tp = FakeTransport()
        self.items = compress(build_tree(tp.observe(6)))

    def test_plain(self):
        p = parse_plan('{"thought":"t","action":"click","target":0,"value":null,"done":false}',
                       self.items)
        self.assertEqual((p.action, p.target, p.done), ("click", 0, False))

    def test_strips_markdown_fence(self):
        raw = '```json\n{"action":"click","target":1}\n```'
        self.assertEqual(parse_plan(raw, self.items).target, 1)

    def test_extracts_json_from_prose(self):
        raw = '我先点这个。\n{"action":"click","target":2}\n希望有用。'
        self.assertEqual(parse_plan(raw, self.items).target, 2)

    def test_rejects_unknown_sid(self):
        with self.assertRaises(PlannerError):
            parse_plan('{"action":"click","target":999}', self.items)

    def test_rejects_unknown_action(self):
        with self.assertRaises(PlannerError):
            parse_plan('{"action":"swipe","target":0}', self.items)

    def test_rejects_set_text_without_value(self):
        with self.assertRaises(PlannerError):
            parse_plan('{"action":"set_text","target":1}', self.items)

    def test_finish_needs_no_target(self):
        p = parse_plan('{"action":"finish","done":true}', self.items)
        self.assertTrue(p.done)
        self.assertIsNone(p.target)

    def test_retry_feeds_error_back(self):
        b = Flaky(["不好意思我忘了格式", '{"action":"click","target":0}'])
        plan, raws = Planner(b).decide("OBS", self.items)
        self.assertEqual(plan.target, 0)
        self.assertEqual(len(raws), 2)
        self.assertIn("无法解析", b.prompts[1])

    def test_two_failures_abort(self):
        b = Flaky(["nope", "still nope"])
        with self.assertRaises(PlannerError):
            Planner(b).decide("OBS", self.items)

    def test_system_prompt_hides_implementation_details(self):
        """LLM 不该看到 resource-id / 坐标，也不该看到归还机制 —— 那是护栏不是它的职责。"""
        sp = Planner(Flaky([])).system_prompt
        self.assertIn("短 ID", sp)
        for forbidden in ("归还", "ACTION_FOCUS", "locator", "display"):
            self.assertNotIn(forbidden, sp)

    def test_wait_clause_toggled_by_politeness(self):
        self.assertIn("wait", Planner(Flaky([]), politeness="normal").system_prompt)
        self.assertNotIn('{"action": "wait"}',
                         Planner(Flaky([]), politeness="off").system_prompt)


if __name__ == "__main__":
    unittest.main()
