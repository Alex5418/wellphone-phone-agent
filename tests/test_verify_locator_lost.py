"""离线测试：验证层两处修复 —— 定位器解析不到判 UNKNOWN / 树搜索收敛 UNKNOWN 为 PASS。

修复背景：Gmail 撰写页正文框没有 resource-id，locator 降级到 L4（文字锚点），
锚的就是占位符。set_text 一旦写成功，那段文字不复存在 → 重解析 0 候选 →
拿 None 比对期望值 → 判 FAIL。写对了却报失败。
"""

import unittest

from harness.compress import compress
from harness.loop import Loop
from harness.models import ActionResult, Item, Locator, Node, Plan, Verdict
from harness.planner import Planner
from harness.tree import Tree, build_tree
from harness.verify import Snapshot, verify
from tests.fake_device import FakeTransport, node, settings_tree
from tests.test_loop import Script


def make_result(found=True, action_ok=True, **kw):
    return ActionResult(
        found=found, action_ok=action_ok, restore_attempted=True,
        restore_ok=True, restore_focus_ms=12, restore_total_ms=30,
        restore_retried=False,
        holder_after="com.android.chrome",
        post_state=kw.get("post_state", {}), window_after={},
        timing={},
    )


def _make_item(kind="input", label="测试输入框", text_value="旧占位符",
               resource_id="test:id"):
    return Item(
        sid=0, label=label, kind=kind,
        state=None,
        locator=Locator(strategy="L1", resource_id=resource_id),
        anchor_idx=0, target_idx=0,
        text_value=text_value,
    )


def _make_tree(texts: list[str | None], activity="Settings",
               tree_hash="h1") -> Tree:
    """造一棵最小树，每个 text 一个节点。"""
    nodes = []
    for i, t in enumerate(texts):
        n = Node(i, None if i == 0 else 0, 1 if i > 0 else 0,
                 "android.widget.TextView", None, t, None,
                 False, False, False, False, False, False, False,
                 True, True, None, [], False)
        nodes.append(n)
    return Tree(6, "com.android.settings", activity, tree_hash, nodes,
                1, False, False)


# ============================================================================
# 修复一：verify() 层 —— post.found 为假时判 UNKNOWN
# ============================================================================


class TestFix1Verifier(unittest.TestCase):
    """测试 verify() 中 text_equals_value 分支的修复（harness/verify.py）。"""

    def setUp(self):
        tp = FakeTransport()
        self.tree = build_tree(tp.observe(6))
        self.items = {(i.label, i.kind): i for i in compress(self.tree)}

    def snap(self, **kw):
        base = dict(found=True, checked=None, text=None, activity="A",
                    tree_hash="h1", window_count=1)
        base.update(kw)
        return Snapshot(**base)

    # ---- 用例 4：set_text 成功且 locator 仍在，读到新值 → PASS ----

    def test_case4_set_text_success_locator_still_present(self):
        box = self.items[("搜索设置", "input")]
        v = verify(box, "set_text", self.snap(text=None), self.snap(text="WiFi"),
                   make_result(), "WiFi")
        self.assertEqual(v.result, "PASS")

    # ---- 用例 5：set_text 后读到的仍是写入前的值 → UNKNOWN ----

    def test_case5_set_text_unchanged_read_is_unknown(self):
        box = self.items[("搜索设置", "input")]
        v = verify(box, "set_text", self.snap(text="旧值"), self.snap(text="旧值"),
                   make_result(), "新值")
        self.assertEqual(v.result, "UNKNOWN")

    # ---- 用例 6：set_text 后读到第三个值 → FAIL ----

    def test_case6_set_text_wrong_value_is_fail(self):
        box = self.items[("搜索设置", "input")]
        v = verify(box, "set_text", self.snap(text="旧值"), self.snap(text="别的东西"),
                   make_result(), "新值")
        self.assertEqual(v.result, "FAIL")


# ============================================================================
# 修复二：_judge() 层 —— UNKNOWN 时在整棵树里找写入值
# ============================================================================


class TestFix2Judge(unittest.TestCase):
    """测试 _judge() 中树搜索收敛 UNKNOWN 为 PASS 的修复（harness/loop.py）。"""

    def setUp(self):
        self.tp = FakeTransport()
        self.planner = Planner(Script([]))

    def _loop(self):
        return Loop(self.tp, self.planner, trace=None, cross_check=False,
                    recheck_ms=0)

    def _pre_snap(self, item):
        return Snapshot.from_item(item, self.tp.activity,
                                  self.tp._hash(), 1)

    # ---- 用例 1：set_text 后 locator 解析不到，树里有写入值 → PASS ----

    def test_case1_locator_lost_found_in_tree(self):
        item = _make_item(text_value="旧占位符")
        probe = {"found": False, "candidates": 0}
        post_tree = _make_tree([None, "HelloWorld"])
        pre = self._pre_snap(item)
        plan = Plan("test", "set_text", item.sid, "HelloWorld", False)
        result = make_result(found=True)

        v = self._loop()._judge(item, plan, pre, probe, post_tree, result)
        self.assertEqual(v.result, "PASS")

    # ---- 用例 2：set_text 后 locator 解析不到，树里没有写入值 → UNKNOWN ----

    def test_case2_locator_lost_not_in_tree(self):
        item = _make_item(text_value="旧占位符")
        probe = {"found": False, "candidates": 0}
        post_tree = _make_tree([None, "SomethingElse"])
        pre = self._pre_snap(item)
        plan = Plan("test", "set_text", item.sid, "HelloWorld", False)
        result = make_result(found=True)

        v = self._loop()._judge(item, plan, pre, probe, post_tree, result)
        self.assertEqual(v.result, "UNKNOWN")

    # ---- 用例 3：set_text 后 locator 解析不到，且拿不到 post_tree → UNKNOWN ----

    def test_case3_locator_lost_no_post_tree(self):
        item = _make_item(text_value="旧占位符")
        probe = {"found": False, "candidates": 0}
        pre = self._pre_snap(item)
        plan = Plan("test", "set_text", item.sid, "HelloWorld", False)
        result = make_result(found=True)

        v = self._loop()._judge(item, plan, pre, probe, None, result)
        self.assertEqual(v.result, "UNKNOWN")

    # ---- 用例 7：非 set_text 动作（click）下 locator 解析不到 → 不得是 PASS ----

    def test_case7_click_locator_lost_not_pass(self):
        item = _make_item(kind="button", label="某个按钮",
                          resource_id="test:btn")
        probe = {"found": False, "candidates": 0}
        post_tree = _make_tree([None, "某个按钮"],
                               activity=self.tp.activity,
                               tree_hash=self.tp._hash())
        pre = self._pre_snap(item)
        plan = Plan("test", "click", item.sid, None, False)
        result = make_result(found=True)

        v = self._loop()._judge(item, plan, pre, probe, post_tree, result)
        self.assertNotEqual(v.result, "PASS")
        self.assertEqual(v.result, "UNKNOWN")

    # ---- 用例 8：树里有写入值，但动作是 click 不是 set_text → 不得因此变 PASS ----

    def test_case8_click_with_value_in_tree_not_pass(self):
        item = _make_item(kind="button", label="某个按钮",
                          resource_id="test:btn")
        probe = {"found": False, "candidates": 0}
        post_tree = _make_tree([None, "HelloWorld"],
                               activity=self.tp.activity,
                               tree_hash=self.tp._hash())
        pre = self._pre_snap(item)
        plan = Plan("test", "click", item.sid, None, False)
        result = make_result(found=True)

        v = self._loop()._judge(item, plan, pre, probe, post_tree, result)
        self.assertNotEqual(v.result, "PASS")
        self.assertEqual(v.result, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
