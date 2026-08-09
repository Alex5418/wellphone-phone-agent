"""trajectory 的成本记账（M1）。

注：这些用例里的 `click target=13`（FakeTransport 的「自动亮度」开关）只是
**一个能产出 metrics 行的普通动作**，不是被测对象 —— 被测的是 token 与耗时的汇总口径。
原先用的是 `back`，它已被排除出动作空间（结构上必然打在用户屏上，见 planner.ACTIONS）。
"""

import json
import os
import tempfile
import unittest

from harness.loop import Loop
from harness.planner import Planner, ScriptedBackend
from harness.trace import Trace
from tests.fake_device import FakeTransport


class MetaBackend:
    def __init__(self, steps):
        self.steps = list(steps)
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        if not self.steps:
            return json.dumps({"action": "finish", "done": True})
        step = self.steps.pop(0)
        self.last_meta = step.get("last_meta")
        return json.dumps(step["plan"], ensure_ascii=False)


class DisturbTransport(FakeTransport):
    def __init__(self, *args, disturb_none_steps=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._disturb_none_steps = set(disturb_none_steps or [])
        self._act_n = 0

    def act(self, display, locator, action, value=None, restore=True,
            verify_read=True):
        self._act_n += 1
        resp = super().act(display, locator, action, value, restore, verify_read)
        if self._act_n in self._disturb_none_steps:
            resp["timing"] = {k: v for k, v in resp["timing"].items()
                              if k != "disturb_ms"}
        return resp


class TestCostMetrics(unittest.TestCase):

    def test_all_steps_have_tokens(self):
        tp = FakeTransport()
        steps = [
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 100, "completion_tokens": 50,
                           "reasoning_tokens": 20}},
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 80, "completion_tokens": 40,
                           "reasoning_tokens": 15}},
        ]
        planner = Planner(MetaBackend(steps))
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("t", root=d)
            Loop(tp, planner, trace=trace, cross_check=False,
                 recheck_ms=0, max_steps=2).run("test")

            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            totals = meta["totals"]
            self.assertEqual(totals["steps"], 2)
            self.assertEqual(totals["prompt_tokens"], 180)
            self.assertEqual(totals["completion_tokens"], 90)
            self.assertEqual(totals["reasoning_tokens"], 35)
            self.assertEqual(totals["token_steps"], totals["steps"])

            with open(os.path.join(trace.dir, "metrics.jsonl"), encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            self.assertEqual(len(lines), 2)
            for line in lines:
                row = json.loads(line)
                self.assertIn("prompt_tokens", row)
                self.assertIn("completion_tokens", row)
                self.assertIn("reasoning_tokens", row)

    def test_partial_tokens(self):
        tp = FakeTransport()
        steps = [
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 100, "completion_tokens": 50,
                           "reasoning_tokens": 20}},
            {"plan": {"action": "click", "target": 13}},
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 80}},
            {"plan": {"action": "finish", "done": True}},
        ]
        planner = Planner(MetaBackend(steps))
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("t", root=d)
            Loop(tp, planner, trace=trace, cross_check=False,
                 recheck_ms=0).run("test")

            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            totals = meta["totals"]
            self.assertEqual(totals["steps"], 4)
            self.assertEqual(totals["prompt_tokens"], 180)
            self.assertEqual(totals["completion_tokens"], 50)
            self.assertEqual(totals["reasoning_tokens"], 20)
            self.assertLess(totals["token_steps"], totals["steps"])

    def test_no_tokens_scripted(self):
        tp = FakeTransport()
        planner = Planner(ScriptedBackend([
            {"action": "click", "target": 13},
            {"action": "click", "target": 13},
            {"action": "finish", "done": True},
        ]))
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("t", root=d)
            Loop(tp, planner, trace=trace, cross_check=False,
                 recheck_ms=0).run("test")

            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            totals = meta["totals"]
            self.assertIsNone(totals["prompt_tokens"])
            self.assertIsNone(totals["completion_tokens"])
            self.assertIsNone(totals["reasoning_tokens"])
            self.assertEqual(totals["token_steps"], 0)

    def test_median_even_samples(self):
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("test", root=d)
            trace.metric(1, llm_ms=100, prompt_tokens=None,
                         completion_tokens=None, reasoning_tokens=None,
                         disturb_ms=None)
            trace.metric(2, llm_ms=200, prompt_tokens=None,
                         completion_tokens=None, reasoning_tokens=None,
                         disturb_ms=None)
            trace.metric(3, llm_ms=300, prompt_tokens=None,
                         completion_tokens=None, reasoning_tokens=None,
                         disturb_ms=None)
            trace.metric(4, llm_ms=400, prompt_tokens=None,
                         completion_tokens=None, reasoning_tokens=None,
                         disturb_ms=None)
            trace.finish("done", "ok",
                         extra={"llm_calls": 4, "steps": 4})

            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            totals = meta["totals"]
            self.assertEqual(totals["llm_ms_median"], 250.0)
            self.assertEqual(totals["llm_ms_total"], 1000)

    def test_disturb_ms_none(self):
        tp = DisturbTransport(disturb_none_steps={2})
        steps = [
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 10, "completion_tokens": 5}},
            {"plan": {"action": "click", "target": 13},
             "last_meta": {"prompt_tokens": 10, "completion_tokens": 5}},
            {"plan": {"action": "finish", "done": True}},
        ]
        planner = Planner(MetaBackend(steps))
        with tempfile.TemporaryDirectory() as d:
            trace = Trace("t", root=d)
            Loop(tp, planner, trace=trace, cross_check=False,
                 recheck_ms=0).run("test")

            with open(os.path.join(trace.dir, "meta.json"), encoding="utf-8") as f:
                meta = json.load(f)
            totals = meta["totals"]
            self.assertEqual(totals["disturb_ms_total"], 68)
            self.assertEqual(totals["disturb_ms_max"], 68)


if __name__ == "__main__":
    unittest.main()
