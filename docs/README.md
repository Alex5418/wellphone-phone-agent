# 文档索引

```
docs/
  ARCHITECTURE.md      设计决策与理由 —— 为什么这么做
  HARNESS-SPEC.md      实现规格 —— 怎么做（冲突处以 ARCHITECTURE 为准）
  随手记.md             原始草稿，未整理
  experiments/         实测记录 —— 凭什么这么说
```

三份文件各管一件事，不互相复述：
**ARCHITECTURE 讲理由 → HARNESS-SPEC 讲实现 → experiments/ 提供依据。**
代码的使用说明在 [`../harness/README.md`](../harness/README.md)（放在模块旁边，改代码时不容易忘记同步）。

## 设计

| 文件 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 问题的特殊性（a11y 动作绑定单焦点语义）、验收标准、护栏/策略分层、执行循环、locator 抽象、部署形态、适用边界 |
| [HARNESS-SPEC.md](HARNESS-SPEC.md) | 传输层协议、Android 命令契约（state/observe/act/probe）、模块划分、数据结构、验证判据、实现顺序、已知坑 |

## 实验记录

按时间顺序，后面的建立在前面的结论上。

| 文件 | 问题 | 结论 |
|---|---|---|
| [EXPERIMENTS.md](experiments/EXPERIMENTS.md) | R1–R5 假设验证的**原始记录** | 命令、原始输出、结论按时间堆积。答辩时开着这份讲 |
| [SUBTASK-A-RESULTS.md](experiments/SUBTASK-A-RESULTS.md) | 哪些动作会夺焦点 | 动作类型 × 焦点影响矩阵；`result=false` 时同样夺焦点 |
| [REPORT-E6-FOCUS-RESTORE.md](experiments/REPORT-E6-FOCUS-RESTORE.md) | 焦点能不能还回去 | 能。`ACTION_FOCUS` 是最优归还原语 —— 正因为它什么都不做 |
| [B1-RESULTS.md](experiments/B1-RESULTS.md) | 归还对所有动作都有效吗 | 覆盖 CLICK/SET_TEXT/LONG_CLICK/SCROLL/FOCUS；例外是触发全局配置变更的动作（Activity 重建，快照失效） |
| [B2-COMPRESSION.md](experiments/B2-COMPRESSION.md) | 节点树怎么压给 LLM | 锚点合并 + 去重 + 短 ID；压缩前后对比 |
| [B3-APP-SCOUT.md](experiments/B3-APP-SCOUT.md) | 拿哪个 app 做演示 | 5 个候选 app 的节点树体检数据（只采数据，不作选型建议） |
| [C2-RELIABILITY.md](experiments/C2-RELIABILITY.md) | 节点树可用性怎么量 | **弃用**「规范 resource-id 覆盖率」，改用「可交互节点中能被唯一指认的比例」 |
| [C3-EXECUTION.md](experiments/C3-EXECUTION.md) | locator 在执行侧管不管用 | L3/L4/L5 在 Settings 上验证通过；发现 `findByText` 同时匹配 `contentDescription` |
| [D1-FIRST-REAL-RUN.md](experiments/D1-FIRST-REAL-RUN.md) | harness 端到端跑得起来吗 | 跑通。**打扰窗口不是一个数**：滚动 12 ms，全局配置变更 2526 ms（其中 2962 ms 是重解析阻塞） |
| [D2-LLM-REAL-RUN.md](experiments/D2-LLM-REAL-RUN.md) | 换成真实模型护栏还成立吗 | 成立，护栏一行没改。deepseek-v4-flash 3 步完成任务并独立验证；模型自己选择 wait 让路；撞上 ⛔ 时一步收尾报 impossible |
| [E7-KEYSTROKE-LANDING.md](experiments/E7-KEYSTROKE-LANDING.md) | 打扰窗口里用户敲的字去了哪 | **bug 是真的**：不归还时 120 字里 56 个进 agent 工作区且无上界；归还后压到 6 个（≈ 窗口÷打字速率），**有界但不为零**；最坏情况丢 129/200 |

完整 trajectory 在 [`experiments/trajectories/`](experiments/trajectories/) —— 一次完整的
observation / LLM 输出 / act 请求响应 / 独立 probe / verdict，逐步落盘。

## 实现

代码分两侧，接口是 `HARNESS-SPEC.md` §1–2 的 JSON 协议：

- `android/` —— AccessibilityService，只做感知与执行
- `harness/` —— PC 侧，规划 / 树压缩 / locator 生成 / 验证判据 / 编排
- `tools/` —— 离线小工具（`compress_tree.py` 是 B2/C1/C2 的产物，走 uiautomator XML，与 harness 独立）
- `tests/` —— 离线测试，不需要设备
