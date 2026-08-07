# K1-RESULTS · 设备侧 JVM 单测结果

**分支**: `exp/k1-kotlin-tests`
**日期**: 2026-08-07
**结论**: 全部通过，新增 13 条用例

---

## A · `Snapshot.treeHash` (TreeHashTest.kt)

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| A1 | 同一棵树算两次 | 哈希相同 | ✅ 通过 |
| A2 | 改一个节点的 `text` | 哈希改变 | ✅ 通过 |
| A3 | 改一个节点的 `isClickable` | 哈希改变 | ✅ 通过 |
| A4 | 节点**顺序**不同、内容相同 | 哈希**改变**（顺序是语义的一部分） | ✅ 通过 |
| A5 | 两个节点的字段跨字段拼接歧义<br>（如 `text="a"` `desc="b"` vs `text="ab"` `desc=""`） | 哈希**不同** —— 这正是 SEP/REC 分隔符存在的理由 | ✅ 通过 |

## B · `LocatorResolver.resolve` 的分层降级 (LocatorResolverTest.kt)

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| B1 | L1：`resource-id` 唯一命中 | 命中该节点，`candidates=1` | ✅ 通过 |
| B2 | L1：`resource-id` 命中多个 | 返回 DFS 序第一个命中节点（`cands[0]`），`candidates=2` | ✅ 通过 |
| B3 | L4：文字锚点命中 | 命中 | ✅ 通过 |
| B4 | L4：文字**匹配 contentDescription** 而非 text | 也命中 —— C3 的实测发现，`findByText` 的全集是 text ∪ contentDescription | ✅ 通过 |
| B5 | L6：结构路径 `[0,1,0]` | 命中路径末端的节点 | ✅ 通过 |
| B6 | L6：路径越界 / 中途缺子节点 | `found=false`，**不得抛异常** | ✅ 通过 |
| B7 | 任何层都解析不到 | `found=false, candidates=0`，`note` 非空 | ✅ 通过 |
| B8 | `climbToExecutable`：命中的是不可交互的文字节点 | 向上爬到可交互容器 | ✅ 通过 |

---

## §2 · "能失败" 验证

**选择破坏的用例**: A5 `separatorPreventsConcatenationCollision`

**破坏方式**: 将 `treeHash` 中的 `SEP` 替换为空串 `""`，消除字段分隔符

**结果**:

```
TreeHashTest > a5_separatorPreventsConcatenationCollision FAILED
    java.lang.AssertionError at TreeHashTest.kt:82

1 test completed, 1 failed
```

**已恢复** SEP 并确认全绿。破坏性修改已撤销。

---

## 交付物清单

- [x] `android/app/src/test/java/com/example/phoneagent/TreeHashTest.kt`
- [x] `android/app/src/test/java/com/example/phoneagent/LocatorResolverTest.kt`
- [x] `docs/briefs/K1-RESULTS.md`
- [x] `docs/briefs/K1-PROGRESS.md`

## 自查

- [x] 两张表每格都填了
- [x] `./gradlew :app:testDebugUnitTest --rerun-tasks` 全绿，新增 13 条（≥12）
- [x] 贴了"临时改坏实现 → 用例变红 → 已恢复"的输出
- [x] `git diff main -- android/app/src/main/` 为空
- [x] 报告与 PROGRESS 都在 `docs/briefs/` 下
- [x] 全部在 `exp/k1-kotlin-tests`，没有 push
