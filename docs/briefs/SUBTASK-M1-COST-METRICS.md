# SUBTASK-M1 · 把 token 用量汇总进 trajectory

**分支** `exp/m1-cost-metrics`（已建，直接用）
**性质** 小改动 + 补测试。**不需要设备、不需要网络。**
**禁止** 改动任何护栏逻辑（`policy.py` / `verify.py` 的判据、`restore` 相关）。

---

## 0 · 背景：数据已经在了，只差汇总

`ARCHITECTURE.md §9 待补` 第一条是「单步规划的实测延迟与 token 成本」。
**延迟有了**（`metrics.jsonl` 里的 `llm_ms`），**token 没有** —— 但它其实已经被解析出来了：

```
harness/planner.py:202-209   解析 usage → last_meta
                             {finish_reason, prompt_tokens, completion_tokens, reasoning_tokens}
harness/loop.py:183-184      逐步落盘到 step-NN/llm_meta.json
```

**断在最后一步**：`metrics.jsonl` 那一行只有

```
['action','action_ms','disturb_ms','llm_ms','restore_focus_ms',
 'restore_ok','restore_total_ms','step','target','total_ms','verdict']
```

所以「一个任务花了多少 token」现在要手动翻每个 step 的 `llm_meta.json` 才能算。

---

## 1 · 要做什么

### ① 每步的 token 进 `metrics.jsonl`

`harness/loop.py` 里记 metrics 的地方（搜 `llm_ms=`）已经能拿到
`self.planner.last_meta`。把其中的 token 字段一并写进去。

**三值原则**：读不到就是 `None`，**不要填 0**。
`scripted` / `rule` 这两个 provider 根本没有 token 概念，它们必须是 `None`
而不是 0 —— 0 会被当成"这一步免费"，那是编造。

### ② run 级汇总进 `meta.json`

`harness/trace.py` 的 `finish()` 里加一个 `totals` 块：

| 字段 | 含义 | 读不到时 |
|---|---|---|
| `steps` | 总步数 | 必有 |
| `llm_calls` | LLM 调用次数（含解析失败重试） | 必有 |
| `llm_ms_total` / `llm_ms_median` | 延迟合计 / 中位数 | 必有 |
| `prompt_tokens` / `completion_tokens` / `reasoning_tokens` | 各自求和 | **`None`**，不是 0 |
| `disturb_ms_total` / `disturb_ms_max` | 打扰窗口合计 / 最大 | 必有 |

**只对拿得到的步求和**，并额外给一个 `token_steps`（有 token 数据的步数），
这样读的人能看出「合计 1234 tokens」是基于 8 步还是 3 步。
**缺失步数不写出来，合计就是误导。**

### ③ 补离线测试

新文件 `tests/test_cost_metrics.py`：

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| 1 | 各步都有 token | `totals` 求和正确，`token_steps` 等于步数 | |
| 2 | **部分步没有 token** | 合计只算有的，`token_steps` < 步数 | |
| 3 | **一步都没有 token**（scripted） | 三个 token 字段都是 `None`，**不是 0** | |
| 4 | `llm_ms_median` 偶数个样本 | 按实现定义断言（读代码，别猜） | |
| 5 | `disturb_ms` 有 None 混入 | 求和跳过 None，不崩 | |

**每格必须填。**

---

## 2 · 判据

```bash
python -m unittest discover -s tests -q     # 必须 79 通过 0 失败（现有 74 + 新增 5）
```

**必须验证测试能失败**：把 ③ 里的 `None` 临时改成 `0`，用例 3 应当变红，然后恢复。
输出贴进报告。

再跑一次离线端到端确认没把 trajectory 写坏：

```bash
PHONEAGENT_RUNS_DIR=/tmp/m1 python -m harness.cli run "x" --provider scripted --script '[]'
python -c "import json;print(json.load(open('/tmp/m1/<最新>/meta.json',encoding='utf-8'))['totals'])"
```

（会因为没有设备而 abort，那是**预期**的 —— 我们只看 `meta.json` 里 `totals` 的形状对不对。）

---

## 3 · ⚠️ 陷阱

1. **不要把 `None` 写成 0。** 这是本任务的核心，也是唯一一条不能妥协的
2. `last_meta` 可能是 `None`（`scripted`/`rule` 后端根本不设它）
3. `trace.finish()` 里 `config` 那个块已经踩过一次坑：字典展开后又被后面的键覆盖，
   把实参写成了默认值。**加字段时注意别重蹈覆辙**（见 `aa1b2ae`）
4. 解析失败重试时 `planner.calls` 会 +1 但那一步没有 metrics 行 ——
   `llm_calls` 与 `steps` 本来就不相等，**这是对的，别"修"它**
5. 测试用 `tests/fake_device.py`，照 `tests/test_loop.py` 的写法造 Loop

---

## 4 · 交付物

1. `harness/loop.py` / `harness/trace.py` 的改动
2. `tests/test_cost_metrics.py`
3. `docs/briefs/M1-RESULTS.md` —— §1③ 表格填满 + 「能失败」验证输出 + 一份真实 `totals` 样例
4. `docs/briefs/M1-PROGRESS.md`
5. 把 `ARCHITECTURE.md §9` 待补里「单步规划的实测延迟与 token 成本」那条**勾掉或删掉**

---

## 5 · ❌ 不要做

- ❌ 不要改任何护栏逻辑（判据、阈值、restore）
- ❌ 不要改 `planner.py` 里已有的 usage 解析
- ❌ 不要为了让数字好看而估算/推算 token
- ❌ 不要 push；不要动 `main`

---

## 6 · 完成标准（自查）

- [ ] `metrics.jsonl` 每行有 token 字段（拿不到时为 `None`）
- [ ] `meta.json` 有 `totals`，含 `token_steps`
- [ ] 5 个用例都实现，`unittest` 79 通过
- [ ] 贴了「`None` 改成 0 → 用例 3 变红 → 已恢复」的输出
- [ ] 贴了一份真实的 `totals` 输出
- [ ] `ARCHITECTURE §9` 那条已处理
- [ ] 全部提交在 `exp/m1-cost-metrics`，没有 push
