# M1 Progress

**分支**: `exp/m1-cost-metrics`  
**状态**: ✅ 完成  

### 完成内容

- [x] `metrics.jsonl` 每行有 token 字段（拿不到时为 `None`）
- [x] `meta.json` 有 `totals`，含 `token_steps`
- [x] 5 个用例都实现，`unittest` 79 通过
- [x] 「`None` 改成 0 → 用例 3 变红 → 已恢复」已验证
- [x] 真实 `totals` 输出（scripted 后端 offline abort）
- [x] `ARCHITECTURE §9` 第一条已勾掉
