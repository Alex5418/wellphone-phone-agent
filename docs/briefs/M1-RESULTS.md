# M1-RESULTS · Token 用量汇总进 trajectory

## 测试结果

`python -m unittest discover -s tests -q` → **79 pass, 0 fail** (74 + 5)

### §1 ③ 测试表格

| # | 用例 | 期望 | 状态 |
|---|---|---|---|
| 1 | 各步都有 token | `totals` 求和正确，`token_steps` 等于步数 | ✅ |
| 2 | 部分步没有 token | 合计只算有的，`token_steps` < 步数 | ✅ |
| 3 | 一步都没有 token（scripted） | 三个 token 字段都是 `None`，不是 0 | ✅ |
| 4 | `llm_ms_median` 偶数个样本 | `statistics.median` 返回 (200+300)/2 = 250.0 | ✅ |
| 5 | `disturb_ms` 有 None 混入 | 求和跳过 None，不崩 | ✅ |

### "能失败" 验证

临时将 `trace.py` 中 `None` 改为 `0` 后运行 test 3：

```
AssertionError: 0 is not None
```

用例 3 变红。已恢复 `None`，全绿。

### 真实 `totals` 样例（scripted 后端，无设备 abort）

```json
{
  "totals": {
    "steps": 0,
    "llm_calls": 0,
    "llm_ms_total": 0,
    "llm_ms_median": null,
    "prompt_tokens": null,
    "completion_tokens": null,
    "reasoning_tokens": null,
    "token_steps": 0,
    "disturb_ms_total": 0,
    "disturb_ms_max": 0
  }
}
```

## 变更文件

- `harness/loop.py` — `metric()` 调用新增 `prompt_tokens`/`completion_tokens`/`reasoning_tokens` 字段；`_finish()`/`_abort()` 传递 `llm_calls`/`steps` 到 `trace.finish()`
- `harness/trace.py` — `finish()` 新增 `totals` 计算（token 聚合 / llm_ms 中位数 / disturb_ms / token_steps）
- `tests/test_cost_metrics.py` — 5 个用例
- `docs/ARCHITECTURE.md` — §9 第一条已勾掉
