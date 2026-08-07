# SUBTASK-K1 · 给设备侧补 JVM 单测（LocatorResolver / treeHash）

**分支** `exp/k1-kotlin-tests`（已建，直接用，不要再建）
**性质** 写代码。**产出是能跑的测试，不是意见。**
**不需要设备、不需要模拟器。** 全程 `./gradlew :app:testDebugUnitTest`。
**禁止** 改 `android/app/src/main/` 下的任何**逻辑**（只允许在 `src/test/` 下加文件）。

---

## 0 · 为什么这件事一直没做，以及路已经被我趟通了

设备侧 1813 行 Kotlin，测试只有模板生成的 `assertEquals(4, 2 + 2)`。
不是疏忽 —— **有一个真实障碍**：`Snapshot.Flat` 持有一个非空的
`AccessibilityNodeInfo`，那是框架类，JVM 单测里造不出来。
于是 `LocatorResolver` 和 `treeHash` 全都够不着。

**这个障碍已经在 `eb13d34` 里解决了**，你不需要再趟：

- `libs.versions.toml` / `app/build.gradle.kts` 已加 `mockito-core 5.14.2`
- `app/src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker`
  内容是 `mock-maker-subclass`

  ⚠ **这个文件不能删也不能改。** mockito 5 默认的 **inline** mock maker 在本机 JDK 25 上
  会失败：`Could not modify all classes [AccessibilityNodeInfo, Object, Parcelable]`。
  换成 subclass mock maker 才能 mock 框架类。
- `ProbeMockTest.kt` 是探路用例，**已通过**：mock 一个节点，经
  `Snapshot.cls` / `Snapshot.text` 读回来。照着它的写法造节点。

先跑一次确认基线是绿的：

```bash
cd android && ./gradlew :app:testDebugUnitTest --rerun-tasks
```

结果在 `app/build/test-results/testDebugUnitTest/TEST-*.xml`。
⚠ **不加 `--rerun-tasks` 会命中缓存报 UP-TO-DATE，看起来跑了其实没跑。**

---

## 1 · 要覆盖什么

先读 `android/app/src/main/java/com/example/phoneagent/LocatorResolver.kt`
与 `Snapshot.kt`，以及 `docs/HARNESS-SPEC.md` 里 locator 的分层定义。

### A · `Snapshot.treeHash`（新文件 `TreeHashTest.kt`）

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| A1 | 同一棵树算两次 | 哈希相同 | |
| A2 | 改一个节点的 `text` | 哈希改变 | |
| A3 | 改一个节点的 `isClickable` | 哈希改变 | |
| A4 | 节点**顺序**不同、内容相同 | 哈希**改变**（顺序是语义的一部分） | |
| A5 | 两个节点的字段跨字段拼接歧义<br>（如 `text="a"` `desc="b"` vs `text="ab"` `desc=""`） | 哈希**不同** —— 这正是 SEP/REC 分隔符存在的理由 | |

**A5 是关键用例。** `treeHash` 用 `SEP`/`REC` 两个控制字符分隔字段与记录，
就是为了防止拼接歧义。没有这条，分隔符被人删掉也不会有测试变红。

### B · `LocatorResolver.resolve` 的分层降级（新文件 `LocatorResolverTest.kt`）

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| B1 | L1：`resource-id` 唯一命中 | 命中该节点，`candidates=1` | |
| B2 | L1：`resource-id` 命中多个 | 按分层定义处理（读代码确认，别猜） | |
| B3 | L4：文字锚点命中 | 命中 | |
| B4 | L4：文字**匹配 contentDescription** 而非 text | 也命中 —— C3 的实测发现，`findByText` 的全集是 text ∪ contentDescription | |
| B5 | L6：结构路径 `[0,1,0]` | 命中路径末端的节点 | |
| B6 | L6：路径越界 / 中途缺子节点 | `found=false`，**不得抛异常** | |
| B7 | 任何层都解析不到 | `found=false, candidates=0`，`note` 非空 | |
| B8 | `climbToExecutable`：命中的是不可交互的文字节点 | 向上爬到可交互容器 | |

**每格必须填。** 做不到的写「未实现 + 原因」，不要删行。

B6、B7 是反向守卫：解析失败必须是**干净的 false**，不是崩溃 ——
上层 `verify.py` 依赖「解析不到 → UNKNOWN」这条，它崩了整条链路就断了。

---

## 2 · 判据

```bash
cd android && ./gradlew :app:testDebugUnitTest --rerun-tasks
```

- 必须全绿，且新增用例数 ≥ 12
- **必须验证测试能失败**：随便挑一条，临时改坏 `main/` 里对应的实现
  （例如把 `treeHash` 里的 `SEP` 换成空串），确认对应用例变红，**然后恢复**。
  这一步的输出要贴进报告。**不能失败的测试等于没有测试。**
- 结束时 `git diff main -- android/app/src/main/` 必须为**空**

---

## 3 · ⚠️ 陷阱

1. **`--rerun-tasks`**：不加会命中缓存，BUILD SUCCESSFUL 但一个测试都没跑
2. **不要删 `mockito-extensions/org.mockito.plugins.MockMaker`**（见 §0）
3. **`Flat` 的构造签名**是 `Flat(idx, parent, depth, node, rootOrdinal, childIndex)`，
   `parent = -1` 表示根。`FlatTree(nodes, truncated, roots)`。照 `ProbeMockTest.kt` 造
4. mock 的节点默认所有属性返回 null/false，**要什么就 `when(...)` 什么**。
   别假设默认值符合直觉
5. `Snapshot.effectiveText` 会把 hint 当成 null —— 造用例时注意区分 `text` 与 hint
6. 断言用 `assertEquals(expected, actual)`，不要 `assertTrue(a == b)`（失败时看不见实际值）

---

## 4 · 交付物

1. `android/app/src/test/java/com/example/phoneagent/TreeHashTest.kt`
2. `android/app/src/test/java/com/example/phoneagent/LocatorResolverTest.kt`
3. `docs/briefs/K1-RESULTS.md` —— §1 两张表填满 + §2「能失败」的验证输出
4. `docs/briefs/K1-PROGRESS.md` —— 逐步记录（**不要放仓库根目录**）

---

## 5 · ❌ 不要做

- ❌ 不要改 `android/app/src/main/` 下任何文件的逻辑
- ❌ 不要改 Python 侧任何东西
- ❌ 不要为了让测试通过而放宽断言
- ❌ 不要引入 Robolectric（subclass mock maker 已经够用，别把构建搞重）
- ❌ 不要 push；不要动 `main`

做不到的项：**记录「未实现 + 原因」，继续下一项。**
必须偏离本 brief 才能推进时：**照做，但在报告里写明偏离了什么、为什么。**

---

## 6 · 卡住了怎么办

写下：想做什么、执行了什么命令、实际输出、你的判断。**不要藏失败，也不要自己"修好"再报成功。**

---

## 7 · 完成标准（自查）

- [ ] 两张表每格都填了（含"未实现 + 原因"）
- [ ] `./gradlew :app:testDebugUnitTest --rerun-tasks` 全绿，新增 ≥12 条
- [ ] 贴了"临时改坏实现 → 用例变红 → 已恢复"的输出
- [ ] `git diff main -- android/app/src/main/` 为空
- [ ] 报告与 PROGRESS 都在 `docs/briefs/` 下
- [ ] 全部提交在 `exp/k1-kotlin-tests`，没有 push
