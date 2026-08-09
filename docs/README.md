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
| [D1-FIRST-REAL-RUN.md](experiments/D1-FIRST-REAL-RUN.md) | harness 端到端跑得起来吗 | 跑通。**打扰窗口不是一个数**：滚动 12 ms，全局配置变更 2526 ms。另一次补了子时间戳的单步重跑显示瓶颈在**重解析**（2962 ms），归还原语本身只要 225 ms —— 两个数出自两次 run，不构成同一次的分解 |
| [D2-LLM-REAL-RUN.md](experiments/D2-LLM-REAL-RUN.md) | 换成真实模型护栏还成立吗 | 成立，护栏一行没改。deepseek-v4-flash 3 步完成任务并独立验证；模型自己选择 wait 让路；撞上 ⛔ 时一步收尾报 impossible |
| [E7-KEYSTROKE-LANDING.md](experiments/E7-KEYSTROKE-LANDING.md) | 打扰窗口里用户敲的字去了哪 | **bug 是真的**：不归还时 120 字里 56 个进 agent 工作区且无上界；归还后压到 6 个（≈ 窗口÷打字速率），**有界但不为零**；最坏情况丢 129/200 |
| [E8-SOFT-KEYBOARD.md](experiments/E8-SOFT-KEYBOARD.md) | 软键盘下还会污染吗 | **不会，一次都没有**。点屏幕这一下自己把焦点带回来，`restore=false` 也无损。E7 的污染结论**限外接键盘**；软键盘的现实风险是全局配置变更下丢 40% 击键 |
| [E9-PINYIN-COMPOSING.md](experiments/E9-PINYIN-COMPOSING.md) | 中文拼音连打时后台跑 agent | **归还与否是质变**：不归还时未上屏的拼音被强制提交、候选上下文清零、丢 7 个字母；归还时整串 composing 完好、候选长到「中中华人民共和国」。且破坏程度**与窗口长短无关** |
| [E10-COMPOSING-BREAK-CAUSE.md](experiments/E10-COMPOSING-BREAK-CAUSE.md) | 打断中文输入的到底是什么 | **更正 E9**：决定因素是**动作类型**（副屏有无窗口/Activity 变更），不是归还开关。滚动类从不打断；导航点击会打断，归还只降概率不消除。打扰窗口预算管不住这一类 |
| [E12-GMAIL-DEMO.md](experiments/E12-GMAIL-DEMO.md) | 真实任务端到端（用户打中文 + agent 发邮件） | 任务成功、邮件正文正确、焦点 8/8 归还；**但用户仍需手动点回软键盘 —— 验收标准没干净通过**。核心发现：**归还的是 window 焦点，用户需要的是能继续打字，两者不等价** |
| [E13-OBSERVATION-NOT-MODEL.md](experiments/E13-OBSERVATION-NOT-MODEL.md) | 弱模型失败是观测缺陷还是能力不足 | **观测缺陷**。同预算重跑 flash 仍在同一处卡死；补上「相比上一步的增删」后 flash **8 步完成**（比 pro 还少），LLM 延迟从 65.6s 降到 10.9s。**harness 的质量应由弱模型检验** |
| [E14-VIDEO-DISTURBANCE.md](experiments/E14-VIDEO-DISTURBANCE.md) | 主屏看视频时夺焦点会不会打断播放 | **不会**。主屏 `mCurrentFocus=null` 持续存在时视频仍 PLAYING、画面持续更新；三组 0 次 PAUSED、0 冻结。四个候选仪表**证伪了三个**（`gfxinfo` 视频播放时恒读 0 帧、`SurfaceFlinger --latency` 读不到、`media_session` 的 `position` 懒更新） |
| [E15-SECONDARY-FIELD-CONTAMINATION.md](experiments/E15-SECONDARY-FIELD-CONTAMINATION.md) | 软键盘击键会不会落进副屏输入框（E8 漏测的那一格） | **会，且护栏挡不住** —— 条件是 agent 的动作**重建了副屏 Activity**：新编辑器获得焦点后 IME 输入连接改绑过去。不重建 70 次 0 命中，重建 30 次 5 命中；动作数/写入值/restore 全部对齐时 0/10 vs 3/20。**证伪 E8 §4.1**。打字侧已用 `input tap` 自动化（与鼠标点 scrcpy 同源）。附五个仪表缺陷的更正史 |
| [E16-DOSE-RESPONSE.md](experiments/E16-DOSE-RESPONSE.md) | 污染率随打扰窗口怎么变 | **九次污染全在 272–431ms，`DISTURB_BUDGET_MS=500` 一次没拦住**。<200ms 时 0/67，300–500ms 时 47%。该参数只捕捉了三因素里最弱的一个（另两个：用户在干什么、动作有没有重建副屏编辑器） |
| [E17-LOCAL-MODEL-REPLAY.md](experiments/E17-LOCAL-MODEL-REPLAY.md) | 换本地小模型，哪一层先塌 | **护栏层没塌**：30/30 可解析、30/30 从不选中 ⛔ 拉黑的目标。塌的是「从变化标记做跨轮推断」——E13 加的 `✦新出现`/`消失` 标记两个本地模型 6/6 全无视，说明**观测层的改进有能力门槛**。26B 并不比 9B 强，参数量不是分界线 |
| [E18-IME-DISMISSAL-ATTRIBUTION.md](experiments/E18-IME-DISMISSAL-ATTRIBUTION.md) | 软键盘收起是哪个动作干的 | **查不出来，而且知道为什么**。仪表 45 步 `dismissed` 0 次，而收起确实发生过 —— 它只在单次 `act` 内采两点，四次可定位的消失**没有一次落在那个窗口里**（含一次「前一步根本没有动作」和一次「消失后自行恢复」）。采样间隔＝LLM 延迟（1.5–149 s），该尺度下无法归因。附能定这件事的实验设计（50ms 轮询 + 单动作 + 阴性对照） |

完整 trajectory 在 [`experiments/trajectories/`](experiments/trajectories/) —— 一次完整的
observation / LLM 输出 / act 请求响应 / 独立 probe / verdict，逐步落盘。

## 实现

代码分两侧，接口是 `HARNESS-SPEC.md` §1–2 的 JSON 协议：

- `android/` —— AccessibilityService，只做感知与执行
- `harness/` —— PC 侧，规划 / 树压缩 / locator 生成 / 验证判据 / 编排
- `tools/` —— 离线小工具（`compress_tree.py` 是 B2/C1/C2 的产物，走 uiautomator XML，与 harness 独立；
  `replay_observation.py` 回放历史 observation 给任意模型，E17 用它；
  `scan_ime_transitions.py` 复算 E18 的键盘消失区间，只读 `runs/`）
- `tests/` —— 离线测试，不需要设备
