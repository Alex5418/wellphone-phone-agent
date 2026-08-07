# K1-PROGRESS · 逐步记录

---

## 步骤 1 · 阅读代码

- 阅读 `LocatorResolver.kt` (187 行)：理解 `resolve` 的分层策略、`textUniverseMatch`、`climbToExecutable`、`resolveByPath` 的逻辑
- 阅读 `Snapshot.kt` (207 行)：理解 `treeHash` 的 SHA-1 拼接格式（SEP/REC 分隔）、`Flat`/`FlatTree` 结构
- 阅读 `ProbeMockTest.kt`：确认 mock `AccessibilityNodeInfo` 的写法
- 阅读 `HARNESS-SPEC.md` §4.3：确认 locator 分层定义与 Android 侧对应的期望行为
- 确认 baseline 全绿：`./gradlew :app:testDebugUnitTest --rerun-tasks` → BUILD SUCCESSFUL (2 tests)

---

## 步骤 2 · 编写 TreeHashTest.kt

5 个用例，覆盖：
- A1 确定性
- A2 改 text 导致哈希变化
- A3 改 isClickable 导致哈希变化
- A4 顺序敏感性
- A5 SEP/REC 防拼接歧义（关键用例）

---

## 步骤 3 · 编写 LocatorResolverTest.kt

8 个用例，覆盖：
- B1 L1 唯一 resource-id 命中
- B2 L1 多命中（返回第一个 + candidates 计数）
- B3 L4 text 命中
- B4 L4 contentDescription 命中（textUniverseMatch 语义）
- B5 L6 路径命中
- B6 L6 越界 → 不崩溃、返回 found=false
- B7 无匹配 → found=false、candidates=0、note 非空
- B8 climbToExecutable 向上爬到可交互祖先

---

## 步骤 4 · 首次运行

```
BUILD SUCCESSFUL in 9s
24 actionable tasks: 24 executed
```

全部 15 条（2 existing + 13 new）通过。

---

## 步骤 5 · 失败验证

选择 A5 (separator collision) 作为破坏目标：
1. 将 `SEP` 替换为 `""` → A5 变红：`java.lang.AssertionError at TreeHashTest.kt:82`
2. 恢复 `SEP` → 全绿

---

## 步骤 6 · 最终验证

- `git diff main -- android/app/src/main/` → **空**（未修改 main 代码）
- 报告已写入 `docs/briefs/K1-RESULTS.md`
