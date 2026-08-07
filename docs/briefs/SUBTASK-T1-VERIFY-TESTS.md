# SUBTASK-T1 · 给两个验证层修复补离线单测

**分支** `exp/t1-verify-tests`（从 `main` 建）
**性质** 写代码。**产出是能跑的测试，不是意见。**
**不需要设备、不需要模拟器、不需要网络。** 全程 `python -m unittest`。
**禁止** 改 `harness/` 下的任何**逻辑**（只允许在 `tests/` 下加文件）。

---

## 0 · 开工前必读

```bash
git log -1 --stat b0fcae7      # 修复一：读缓存
git log -1 --stat f0edf0a      # 修复二：假 FAIL
cat tests/fake_device.py       # 离线测试的假设备，全部测试都建在它上面
cat tests/test_verify.py       # 现有验证测试的写法，照着来
```

今天有两个真实缺陷被修掉，**但都没有测试守着**。它们都来自同一次 Gmail 实跑
（`runs/2026-08-07T05-42-53`，模型把同一个值重写四次直到卡死中止）。
**没有测试的修复，下次重构就会静静地退回去。**

---

## 1 · 要覆盖的两条路径

### 修复一：定位器解析不到 → 必须 UNKNOWN，不许 FAIL

`harness/verify.py` 的 `text_equals_value` 分支。

**背景**：Gmail 正文框没有 resource-id，locator 降级到 **L4（文字锚点）**，
锚的就是占位符 `Compose email`。`set_text` 一旦写成功，那段文字不复存在
→ 重解析 0 候选 → `post.text is None` → 拿 None 去比对期望值 → 判 FAIL。
**写对了却报失败。** 定位器被自己的成功摧毁了。

修法：`post.found` 为假时一律 `UNKNOWN`。读不到 ≠ 不成立。

### 修复二：UNKNOWN 时去整棵树里找写入值 → PASS

`harness/loop.py` 的 `_judge`。

probe 解析不到节点，但**观测层其实看得见**那段文字 ——
独立重读的整棵树里就有一个节点的文字正好等于写入值。用它把 UNKNOWN 收敛成 PASS。

---

## 2 · 预填的用例表（每格都要填）

在 `tests/test_verify_locator_lost.py`（新文件）里实现。

| # | 用例 | 构造 | 期望 verdict | 状态 |
|---|---|---|---|---|
| 1 | set_text 后 locator 解析不到，树里**有**写入值 | `probe.found=False`，post_tree 含 text==value 的节点 | **PASS** | |
| 2 | set_text 后 locator 解析不到，树里**没有**写入值 | 同上但树里没有 | **UNKNOWN** | |
| 3 | set_text 后 locator 解析不到，且拿不到 post_tree | `post_tree=None` | **UNKNOWN** | |
| 4 | set_text 成功且 locator 仍在，读到新值 | `probe.found=True, text==value` | **PASS** | |
| 5 | set_text 后读到的仍是写入前的值 | `probe.found=True, text==pre.text` | **UNKNOWN**（读取滞后与没写进去分不开） | |
| 6 | set_text 后读到**第三个**值（既不是新值也不是旧值） | `probe.found=True`，text 是别的 | **FAIL** | |
| 7 | **非** set_text 动作（如 click）下 locator 解析不到 | click + `probe.found=False` | 不得是 PASS —— 写明实际值 | |
| 8 | 树里有写入值，但动作是 click 不是 set_text | 修复二不该生效 | 不得因此变 PASS | |

**每格必须填**。做不到的写「未实现 + 原因」，不要删行。

用例 6 是关键的**反向守卫**：修复不能把真失败也变成 UNKNOWN。
用例 7、8 守住修复二不越界 —— 它只该对 `set_text` 生效。

---

## 3 · 判据

```bash
python -m unittest discover -s tests -q
```

- 必须 **74 通过 0 失败**（现有 66 + 新增 8）
- 新增测试必须**能失败**：把 `verify.py` 里 `if not post.found:` 那段临时注释掉，
  用例 1/2/3 应当红。**验证完把注释恢复。**
  这一步的输出要贴进报告 —— 不能失败的测试等于没有测试。

---

## 4 · ⚠️ 陷阱

1. **不要改 `harness/` 的逻辑。** 只在 `tests/` 下加文件。
   若你认为 `harness/` 有 bug，**记录下来，不要动手**。
2. `_judge` 是 `Loop` 的方法，需要构造 `Loop` 实例。
   看 `tests/test_loop.py` 怎么造的 —— 它注入了鸭子类型的假 backend，
   **不继承 `Backend`**。照抄那个写法，别自己发明。
3. 构造 `Tree` / `Node` 时注意 `effective_text`：
   `hint_text=True` 的节点 `effective_text` 是 `None` 而不是 `text`。
   修复二比对的是 `effective_text`，别用 `text`。
4. `Verdict` 是三值的：`PASS` / `FAIL` / `UNKNOWN`。断言要断 `.result`。
5. 别用 `assertTrue(x == y)`，用 `assertEqual` —— 失败时能看见实际值。

---

## 5 · 交付物

1. `tests/test_verify_locator_lost.py` —— 8 个用例
2. `docs/briefs/T1-RESULTS.md` —— 第 2 节那张表（填满）+ 第 3 节"能失败"的验证输出
3. `PROGRESS.md`（仓库根）—— 逐步记录
4. `SUMMARY.md`（仓库根）—— 一行 STATUS

---

## 6 · ❌ 不要做

- ❌ 不要改 `harness/` 下任何文件的逻辑
- ❌ 不要改现有测试
- ❌ 不要为了让测试通过而放宽断言
- ❌ 不要给重构建议
- ❌ 不要 push；不要动 `main`

---

## 7 · 卡住了怎么办

写下：想做什么、执行了什么、实际输出、你的判断。**不要藏失败。**
某个用例构造不出来就写「未实现 + 原因」，然后做下一个。

---

## 8 · 完成标准（自查）

- [ ] 8 个用例都实现了（或写明"未实现 + 原因"）
- [ ] `python -m unittest discover -s tests -q` 全绿
- [ ] 贴了"临时破坏修复后测试变红"的输出，并确认已恢复
- [ ] 第 2 节表格填满
- [ ] `PROGRESS.md` / `SUMMARY.md` 都写了
- [ ] 全部提交在 `exp/t1-verify-tests`，没有 push
- [ ] `git diff main -- harness/` 是**空的**
