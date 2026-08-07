"""树重建与本地 hash 复算 —— 「不信任工具返回值」的第一道关。"""

import unittest

from harness.models import Node
from harness.tree import build_tree, local_tree_hash, path_from_root
from tests.fake_device import FakeTransport, settings_tree


class TestTree(unittest.TestCase):
    def setUp(self):
        self.tp = FakeTransport()
        self.data = self.tp.observe(6)

    def test_parent_links_and_roots(self):
        t = build_tree(self.data)
        self.assertEqual(t.roots(), [0])
        self.assertEqual(t.by_idx(9).parent, 8)
        self.assertEqual(list(t.ancestors(9)), [8, 7, 3, 0])
        self.assertIn(10, list(t.descendants(7)))

    def test_hash_mismatch_is_detected(self):
        """设备给的 hash 和本地复算对不上 = 返回的节点数组不是算 hash 的那棵树。
        这正是「工具返回成功但参数被静默忽略」那类故障的信号。"""
        bad = dict(self.data)
        bad["tree_hash"] = "0" * 16
        self.assertTrue(build_tree(bad).hash_mismatch)
        self.assertFalse(build_tree(self.data).hash_mismatch)

    def test_hash_changes_with_checked_state(self):
        before = local_tree_hash([Node.from_json(d) for d in settings_tree()])
        nodes = settings_tree()
        nodes[10]["checked"] = False
        after = local_tree_hash([Node.from_json(d) for d in nodes])
        self.assertNotEqual(before, after)

    def test_broken_indexing_raises(self):
        bad = dict(self.data)
        bad["nodes"] = [dict(n) for n in self.data["nodes"]]
        bad["nodes"][3]["parent"] = 99
        with self.assertRaises(ValueError):
            build_tree(bad)

    def test_path_from_root_roundtrip(self):
        t = build_tree(self.data)
        # [根序号, 子序号...]；与 Kotlin 侧 rootOrdinal/childIndex 同源
        self.assertEqual(path_from_root(t, 0), [0])
        self.assertEqual(path_from_root(t, 9), [0, 2, 1, 0, 0])
        cur = t.roots()[path_from_root(t, 9)[0]]
        for step in path_from_root(t, 9)[1:]:
            cur = t.children(cur)[step]
        self.assertEqual(cur, 9)

    def test_hint_text_is_not_content(self):
        t = build_tree(self.data)
        box = t.by_idx(2)
        self.assertEqual(box.text, "搜索设置")
        self.assertIsNone(box.effective_text)   # 那是 hint，不是用户填的内容


if __name__ == "__main__":
    unittest.main()
