"""观测层的「相比上一步」标记。

由 flash 实测失败反推出来的：自动补全把 Subject 顶掉、多出一条 `Alex`，
拍平的条目列表里两者与页面原有内容毫无区别，弱模型只能靠猜 ——
而需要靠猜本身就是观测层的缺陷（观测与护栏不随模型能力浮动，ARCHITECTURE §2）。
"""

import unittest

from harness.models import Item, Locator
from harness.observe import mark_changes


def it(sid, label, kind="button"):
    return Item(sid=sid, label=label, kind=kind, state=None,
                locator=Locator("L1"), anchor_idx=0, target_idx=0)


class TestMarkChanges(unittest.TestCase):
    def test_marks_new_and_reports_gone(self):
        """真实场景：填完收件人后 Subject 消失、补全建议 Alex 出现。"""
        prev = [it(0, "Send"), it(1, "To"), it(2, "Subject", "input"),
                it(3, "Compose email", "input")]
        cur = [it(0, "Send"), it(1, "To"), it(2, "Alex"),
               it(3, "Compose email", "input")]
        gone = mark_changes(cur, prev)
        self.assertEqual(gone, ["Subject | input"])
        self.assertTrue(next(i for i in cur if i.label == "Alex").is_new)
        self.assertFalse(next(i for i in cur if i.label == "Send").is_new)
        self.assertIn("✦上一步之后新出现", next(i for i in cur if i.label == "Alex").render())

    def test_first_observation_marks_nothing(self):
        cur = [it(0, "A"), it(1, "B")]
        self.assertEqual(mark_changes(cur, None), [])
        self.assertFalse(any(i.is_new for i in cur))

    def test_full_page_change_is_not_reported(self):
        """整页换掉时"全是新的"没有信息量，报了只会变成噪声。"""
        prev = [it(0, "A"), it(1, "B"), it(2, "C"), it(3, "D")]
        cur = [it(0, "X"), it(1, "Y"), it(2, "Z")]
        self.assertEqual(mark_changes(cur, prev), [])
        self.assertFalse(any(i.is_new for i in cur))
