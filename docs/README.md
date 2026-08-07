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
| [EXPERIMENTS.md](experiments/EXPERIMENTS.md) | R1–R5 假设验证的**原始记录** | 命令、原始输出、结论按时间堆积。 |
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
| [E8-SOFT-KEYBOARD.md](experiments/E8-SOFT-KEYBOARD.md) | 软键盘下还会污染吗 | **不会，一次都没有**。点屏幕这一下自己把焦点带回来，`restore=false` 也无损。E7 的污染结论**限外接键盘**；软键盘的现实风险是全局配置变更下丢 40% 击键 |
| [E9-PINYIN-COMPOSING.md](experiments/E9-PINYIN-COMPOSING.md) | 中文拼音连打时后台跑 agent | **归还与否是质变**：不归还时未上屏的拼音被强制提交、候选上下文清零、丢 7 个字母；归还时整串 composing 完好、候选长到「中中华人民共和国」。且破坏程度**与窗口长短无关** |
| [E10-COMPOSING-BREAK-CAUSE.md](experiments/E10-COMPOSING-BREAK-CAUSE.md) | 打断中文输入的到底是什么 | **更正 E9**：决定因素是**动作类型**（副屏有无窗口/Activity 变更），不是归还开关。滚动类从不打断；导航点击会打断，归还只降概率不消除。打扰窗口预算管不住这一类 |
| [E12-GMAIL-DEMO.md](experiments/E12-GMAIL-DEMO.md) | 真实任务端到端（用户打中文 + agent 发邮件） | 任务成功、邮件正文正确、焦点 8/8 归还；**但用户仍需手动点回软键盘 —— 验收标准没干净通过**。核心发现：**归还的是 window 焦点，用户需要的是能继续打字，两者不等价** |

| [E13-OBSERVATION-NOT-MODEL.md](experiments/E13-OBSERVATION-NOT-MODEL.md) | 弱模型失败是观测缺陷还是能力不足 | **观测缺陷**。同预算重跑 flash 仍在同一处卡死；补上「相比上一步的增删」后 flash **8 步完成**（比 pro 还少），LLM 延迟从 65.6s 降到 10.9s。**harness 的质量应由弱模型检验** |

完整 trajectory 在 [`experiments/trajectories/`](experiments/trajectories/) —— 一次完整的
observation / LLM 输出 / act 请求响应 / 独立 probe / verdict，逐步落盘。

## 实现

代码分两侧，接口是 `HARNESS-SPEC.md` §1–2 的 JSON 协议：

- `android/` —— AccessibilityService，只做感知与执行
- `harness/` —— PC 侧，规划 / 树压缩 / locator 生成 / 验证判据 / 编排
- `tools/` —— 离线小工具（`compress_tree.py` 是 B2/C1/C2 的产物，走 uiautomator XML，与 harness 独立）
- `tests/` —— 离线测试，不需要设备
