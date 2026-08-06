"""判据推断与三态。重点：UNKNOWN 不等于失败，但必须说出来。"""

import unittest

from harness.compress import compress
from harness.models import ActionResult
from harness.tree import build_tree
from harness.verify import Snapshot, cross_check_post_state, infer_predicate, verify
from tests.fake_device import FakeTransport


def result(found=True, ok=True, **kw):
    return ActionResult(found=found, action_ok=ok, restore_attempted=True,
                        restore_ok=True, restore_ms=12, restore_retried=False,
                        holder_after="com.android.chrome",
                        post_state=kw.get("post_state", {}), window_after={},
                        timing={})


class TestPredicates(unittest.TestCase):
    def setUp(self):
        tp = FakeTransport()
        self.tree = build_tree(tp.observe(6))
        self.items = {(i.label, i.kind): i for i in compress(self.tree)}

    def snap(self, **kw):
        base = dict(found=True, checked=None, text=None, activity="A",
                    tree_hash="h1", window_count=1)
        base.update(kw)
        return Snapshot(**base)

    def test_infer(self):
        sw = self.items[("深色主题", "switch")]
        row = self.items[("深色主题", "button")]
        box = self.items[("搜索设置", "input")]
        self.assertEqual(infer_predicate(sw, "click"), "checked_flips")
        self.assertEqual(infer_predicate(box, "set_text"), "text_equals_value")
        self.assertEqual(infer_predicate(row, "click"), "activity_or_tree_changes")
        self.assertEqual(infer_predicate(row, "scroll_forward"), "tree_hash_changes")
        self.assertEqual(infer_predicate(row, "long_click"), "window_count_increases")

    def test_switch_flip_pass_and_fail(self):
        sw = self.items[("深色主题", "switch")]
        v = verify(sw, "click", self.snap(checked=True), self.snap(checked=False), result())
        self.assertEqual(v.result, "PASS")
        v = verify(sw, "click", self.snap(checked=True), self.snap(checked=True), result())
        self.assertEqual(v.result, "FAIL")

    def test_dumb_click_is_unknown_not_fail(self):
        """activity 与 hash 都没变 —— 分不出"哑动作"和"本来就没副作用"，
        必须记 UNKNOWN。记成 FAIL 会让 loop 误判卡死而提前中止。"""
        row = self.items[("深色主题", "button")]
        v = verify(row, "click", self.snap(), self.snap(), result())
        self.assertEqual(v.result, "UNKNOWN")
        self.assertTrue(v.ok)

    def test_unresolved_locator_is_fail(self):
        row = self.items[("深色主题", "button")]
        v = verify(row, "click", self.snap(), self.snap(), result(found=False))
        self.assertEqual(v.result, "FAIL")

    def test_set_text(self):
        box = self.items[("搜索设置", "input")]
        v = verify(box, "set_text", self.snap(), self.snap(text="wifi"), result(), "wifi")
        self.assertEqual(v.result, "PASS")
        v = verify(box, "set_text", self.snap(), self.snap(text=None), result(), "wifi")
        self.assertEqual(v.result, "FAIL")

    def test_scroll_boundary_is_fail_with_reason(self):
        lst = self.items[("（可滚动区域）", "list")]
        v = verify(lst, "scroll_forward", self.snap(tree_hash="h1"),
                   self.snap(tree_hash="h1"), result())
        self.assertEqual(v.result, "FAIL")
        self.assertIn("边界", v.detail)

    def test_cross_check_reports_disagreement(self):
        r = result(post_state={"found": True, "checked": True})
        self.assertIsNone(cross_check_post_state(r, {"found": True, "checked": True}))
        msg = cross_check_post_state(r, {"found": True, "checked": False})
        self.assertIn("不一致", msg)


if __name__ == "__main__":
    unittest.main()
