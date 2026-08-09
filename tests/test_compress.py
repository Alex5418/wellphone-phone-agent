"""压缩与 locator 生成。核心断言是**闭环**：

    Python 生成的 locator  →  解析器  →  是不是回到了它想指的那个节点

locator 生成对了但解析不回去，等于没定位 —— 这两件事必须一起测。
"""

import unittest

from harness.compress import compress, trim_for_display
from harness.tree import build_tree
from tests.fake_device import FakeResolver, FakeTransport, settings_tree


def build():
    tp = FakeTransport()
    tree = build_tree(tp.observe(tp.secondary))
    return tree, compress(tree)


def gmail_row_tree():
    """Gmail 会话列表一行的真实形状（`runs/2026-08-09T18-36-02` 的节点树）。

    整行 ViewGroup **自带** contentDescription；行内的联系人头像 ImageView
    既可点、又没有任何文字。两者 kind 都是 button。
    点整行 = 打开邮件；点头像 = 勾选。**同一段文字，两种完全不同的行为。**
    """
    def n(idx, parent, depth, cls, **kw):
        d = {"idx": idx, "parent": parent, "depth": depth, "class": cls,
             "resource_id": None, "text": None, "content_desc": None,
             "clickable": False, "long_clickable": False, "scrollable": False,
             "editable": False, "checkable": False, "checked": False,
             "focused": False, "enabled": True, "visible": True,
             "bounds": [0, 0, 1280, 720], "actions": []}
        d.update(kw)
        return d

    desc = "Unread, , , Wang, Yiduo, , a test, hello alex, ,  at 6:30 PM"
    return [
        n(0, None, 0, "android.widget.FrameLayout"),
        n(1, 0, 1, "android.view.ViewGroup", content_desc=desc, clickable=True,
          bounds=[0, 100, 1280, 260]),
        n(2, 1, 2, "android.widget.ImageView", clickable=True,
          resource_id="com.google.android.gm:id/contact_image",
          bounds=[16, 116, 96, 196]),
        n(3, 1, 2, "android.widget.TextView", text="Wang, Yiduo",
          bounds=[112, 116, 600, 156]),
    ]


class TestGmailRowIsNotTheAvatar(unittest.TestCase):
    """整行不能被行内头像挤掉 —— 这条错过一次真实任务。

    旧的去重规则「同锚点同 kind 留最内层」把整行判没了，只留下头像。
    于是 agent 反复勾选/取消勾选，一次都没打开那封邮件，最后判 impossible。
    """

    def setUp(self):
        self.nodes = gmail_row_tree()
        self.tree = build_tree({
            "display": 4, "pkg": "com.google.android.gm",
            "activity": "com.google.android.gm.ui.MailActivityGmail",
            "tree_hash": "", "window_count": 1, "nodes": self.nodes,
        })
        self.items = compress(self.tree)

    def test_the_row_itself_survives(self):
        row = [i for i in self.items if i.target_idx == 1]
        self.assertEqual(len(row), 1,
                         f"整行不见了；产出的是 {[(i.target_idx, i.label) for i in self.items]}")

    def test_the_row_is_not_resolved_to_the_avatar(self):
        row = next(i for i in self.items if i.target_idx == 1)
        self.assertNotIn("contact_image", row.locator.describe())
        self.assertNotIn("ImageView", row.locator.target)

    def test_the_row_locator_round_trips_to_the_row(self):
        row = next(i for i in self.items if i.target_idx == 1)
        idx, _ = FakeResolver(self.nodes).resolve(row.locator.to_json())
        self.assertEqual(idx, 1)


class TestCompress(unittest.TestCase):
    def setUp(self):
        self.tree, self.items = build()
        self.by_label = {}
        for i in self.items:
            self.by_label.setdefault(i.label, []).append(i)

    def test_hash_roundtrip(self):
        # 设备给的 hash 与本地复算一致（假设备用的就是同一份规则）
        self.assertFalse(self.tree.hash_mismatch)

    def test_row_and_switch_both_kept(self):
        """整行(button) 与 行内开关(switch) 必须是两条 —— 行为完全不同。"""
        dark = self.by_label.get("深色主题", [])
        kinds = sorted(i.kind for i in dark)
        self.assertEqual(kinds, ["button", "switch"], [i.render() for i in dark])
        row = next(i for i in dark if i.kind == "button")
        sw = next(i for i in dark if i.kind == "switch")
        self.assertEqual(row.target_idx, 7)
        self.assertEqual(sw.target_idx, 10)
        self.assertEqual(sw.state, "On")           # checked=True
        self.assertTrue(sw.locator.target.startswith("descendant_class:"))

    def test_wrapper_dedup_keeps_innermost(self):
        # 行一只应产出一条（LinearLayout），文字节点不是候选
        rows = self.by_label.get("网络和互联网", [])
        self.assertEqual(len(rows), 1, [r.render() for r in rows])
        self.assertEqual(rows[0].target_idx, 4)

    def test_summary_as_state(self):
        row = self.by_label["网络和互联网"][0]
        self.assertEqual(row.state, "已连接 WLAN")

    def test_empty_edittext_shows_empty_not_hint(self):
        """空 EditText 的 getText 返回 hint —— 不能把提示语当成已填内容。"""
        box = next(i for i in self.items if i.kind == "input")
        self.assertEqual(box.state, "(空)")

    def test_strategies_cover_l1_to_l6(self):
        got = {i.locator.strategy for i in self.items}
        for s in ("L1", "L2", "L3", "L4", "L5", "L6"):
            self.assertIn(s, got, {i.render(): i.locator.describe() for i in self.items})

    def test_l5_index_is_dfs_ordinal(self):
        opens = sorted(self.by_label["打开"], key=lambda i: i.target_idx)
        self.assertEqual([i.locator.strategy for i in opens], ["L5", "L5"])
        self.assertEqual([i.locator.index for i in opens], [0, 1])

    def test_l2_disambiguated_by_label(self):
        install = self.by_label["安装"][0]
        self.assertEqual(install.locator.strategy, "L2")
        self.assertEqual(install.locator.resource_id, "com.android.settings:id/btn")

    def test_l3_content_desc(self):
        back = self.by_label["返回"][0]
        self.assertEqual(back.locator.strategy, "L3")
        self.assertEqual(back.locator.content_desc, "返回")

    def test_l6_path_for_anchorless_node(self):
        anchorless = next(i for i in self.items if i.target_idx == 19)
        self.assertEqual(anchorless.locator.strategy, "L6")
        self.assertEqual(anchorless.locator.target, "self")
        self.assertTrue(anchorless.locator.path)

    def test_every_locator_resolves_back_to_its_target(self):
        """闭环：每一条 locator 解析出来必须正好是它想指的那个节点。"""
        r = FakeResolver(settings_tree())
        for it in self.items:
            idx, cands = r.resolve(it.locator.to_json())
            self.assertEqual(
                idx, it.target_idx,
                f"[{it.sid}] {it.label} {it.kind}: locator {it.locator.describe()} "
                f"解析到 {idx}，期望 {it.target_idx}（候选 {cands} 个）")

    def test_offscreen_flagged(self):
        footer = next(i for i in self.items if i.label == "页脚")
        self.assertFalse(footer.onscreen)

    def test_trim_prefers_dropping_offscreen(self):
        shown, hidden = trim_for_display(self.items, limit=len(self.items) - 1)
        self.assertEqual(hidden, 1)
        self.assertLessEqual(len(shown), len(self.items) - 1)


if __name__ == "__main__":
    unittest.main()
