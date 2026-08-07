# T1-RESULTS · 验证层离线单测

## 第 2 节：用例表

| # | 用例 | 构造 | 期望 verdict | 状态 |
|---|---|---|---|---|
| 1 | set_text 后 locator 解析不到，树里**有**写入值 | `probe.found=False`，post_tree 含 `effective_text==value` 的节点 | **PASS** | ✅ 实现 |
| 2 | set_text 后 locator 解析不到，树里**没有**写入值 | 同上但树里没有 | **UNKNOWN** | ✅ 实现 |
| 3 | set_text 后 locator 解析不到，且拿不到 post_tree | `post_tree=None` | **UNKNOWN** | ✅ 实现 |
| 4 | set_text 成功且 locator 仍在，读到新值 | `probe.found=True, text==value` | **PASS** | ✅ 实现 |
| 5 | set_text 后读到的仍是写入前的值 | `probe.found=True, text==pre.text` | **UNKNOWN** | ✅ 实现 |
| 6 | set_text 后读到**第三个**值（既不是新值也不是旧值） | `probe.found=True`，text 是别的 | **FAIL** | ✅ 实现 |
| 7 | **非** set_text 动作（如 click）下 locator 解析不到 | click + `probe.found=False` | 不得是 PASS（UNKNOWN） | ✅ 实现 |
| 8 | 树里有写入值，但动作是 click 不是 set_text | 修复二不该生效 | 不得因此变 PASS（UNKNOWN） | ✅ 实现 |

## 第 3 节：全量通过

```bash
$ python -m unittest discover -s tests -q
----------------------------------------------------------------------
Ran 74 tests in 0.139s

OK
```

（66 现有 + 8 新增 = 74 全部通过）

## 第 3 节：能失败的验证

### 临时注释 `verify.py` 中 `if not post.found:` 分支后：

```bash
$ python -m unittest discover -s tests -q
======================================================================
FAIL: test_case1_locator_lost_found_in_tree (test_verify_locator_lost.TestFix2Judge.test_case1_locator_lost_found_in_tree)
----------------------------------------------------------------------
AssertionError: 'FAIL' != 'PASS'

======================================================================
FAIL: test_case2_locator_lost_not_in_tree (test_verify_locator_lost.TestFix2Judge.test_case2_locator_lost_not_in_tree)
----------------------------------------------------------------------
AssertionError: 'FAIL' != 'UNKNOWN'

======================================================================
FAIL: test_case3_locator_lost_no_post_tree (test_verify_locator_lost.TestFix2Judge.test_case3_locator_lost_no_post_tree)
----------------------------------------------------------------------
AssertionError: 'FAIL' != 'UNKNOWN'

----------------------------------------------------------------------
Ran 74 tests in 0.169s

FAILED (failures=3)
```

用例 1/2/3 全部变红：缺少修复一的保护时，`post.text=None` 落入 `text_equals_value` 的 FAIL 路径（`期望 'HelloWorld'，实际 None`），正是原始缺陷的精确复现。

**已确认恢复**：验证后 `if not post.found:` 分支已完整恢复，全量 74 测试再次通过。

## 第 8 节：完成标准自查

- [x] 8 个用例都实现了
- [x] `python -m unittest discover -s tests -q` 全绿（74/74）
- [x] 贴了"临时破坏修复后测试变红"的输出，并已确认恢复
- [x] 第 2 节表格填满
- [x] `PROGRESS.md` / `SUMMARY.md` 都写了
- [x] 全部提交在 `exp/t1-verify-tests`，没有 push
- [x] `git diff main -- harness/` 是**空的**
