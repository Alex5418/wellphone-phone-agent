# WellPhone · 手机 Agent

在**副屏**上自主操作 Android 应用的 Agent。验收标准只有一条：**用户当前正在进行的交互不被中断。**

🎬 **[演示视频](docs/media/demo.mp4)**（约 100s，同屏三样：终端逐步打印 `disturb_ms`、主屏是用户自己的内容、
副屏由**弱模型** `deepseek-v4-flash` 独立发出一封 Gmail）· 复现见 [`docs/DEMO.md`](docs/DEMO.md) · trajectory [`DEMO-gmail-send-7steps/`](docs/experiments/trajectories/DEMO-gmail-send-7steps/)

**为什么不是普通 GUI Agent**：a11y 在**动作分发路径**上绑定单焦点语义 —— 任何经它发出的动作都会夺走
全系统唯一的 window 焦点，与 `performAction` 的返回值无关。于是每个动作有三重后果：改变目标状态、
打断用户输入、**用户的击键灌进 Agent 的工作区**（正确性故障）。因此 loop 多了两个环节：
**补偿**（焦点归还，与动作原子绑定）与**再观测**。

## 架构

```
 display 0  用户主屏（只读，从不下发动作）      display N  scrcpy --new-display（Agent 工作区）
 ─────────────────────────────────────────────────────────────────────────────────────
┌─ PC · harness/ (Python, 零第三方依赖) ─┐             ┌─ Android · AccessibilityService ─┐
│                                        │             │   只做感知与执行，不做决策         │
│   observe → compress → planner (LLM)   │  行协议 JSON │  state    各屏 / 焦点 / 前台包    │
│      ↑                      │          │   短连接     │  observe  节点树 + tree_hash     │
│      │                      ↓          │ ←─────────→ │  act      动作 ⊕ 焦点归还（原子） │
│   verify  ←──  act  ←──  policy 护栏    │             │  probe    独立重读（验证专用）    │
│      └─ adbutil ── dumpsys ────────────┼─────────────┼→ 第二条链路，刻意不复用 a11y 结论 │
└────────────────────────────────────────┘             └──────────────────────────────────┘
                    adb forward tcp:$PHONEAGENT_PORT → localabstract:phoneagent
```

**护栏写死在代码里，不是配置项** —— `loop.py` 中 `restore=True` 硬编码，无开关。
能被关掉的护栏不是护栏。可配置的只有策略层（模型、礼貌度、目标包）。

## 跑起来

需要 `adb`、JDK 17+、Python 3.10+、`scrcpy ≥ 3.0`、设备 Android 11+（实测模拟器 API 34）。

```bash
scrcpy --new-display                            # 1. 建副屏，别关（虚拟屏随进程消亡）
cd android && ./gradlew :app:installDebug       # 2. 装服务 →「设置 → 无障碍」打开 Phone Agent
                                                #    ⚠ 改过代码必须关掉再打开，否则跑旧实例
adb forward tcp:8760 localabstract:phoneagent   # 3. 通道（设备重连后失效）
python -m harness.cli selftest                  # 4. 离线自测 98 条，不需要设备
python -m harness.cli run "在设置中关闭深色主题"   # 5. 端到端
```

> Windows 上第 3 步报 `10013` 是端口落进 Hyper-V 保留段：换 `tcp:18760` 配 `PHONEAGENT_PORT=18760`。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `PHONEAGENT_PORT` | `8760` | adb forward 端口 |
| `PHONEAGENT_TARGET_PKG` | `com.android.settings` | 副屏目标应用 |
| `PHONEAGENT_LLM_PROVIDER` | `anthropic` | `anthropic`/`openai`/`rule`/`scripted` |
| `PHONEAGENT_MODEL` | `claude-sonnet-4-5` | 模型名 |
| `PHONEAGENT_BASE_URL` | — | OpenAI 兼容端点。**用 `openai` 时不传会把 key 发去 api.openai.com 然后 401** |
| `PHONEAGENT_MAX_TOKENS` | `4096` | 推理模型的思考过程也吃这个预算 |
| `PHONEAGENT_LLM_TIMEOUT` | `150` | 秒 |
| `PHONEAGENT_POLITENESS` | `normal` | 只决定 LLM 能否用 `wait`，**不影响归还** |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | — | 按 provider 取 |

其余常量写死在 `harness/config.py`，各带实测依据。

## 实测结论

把「不打扰」拆成可测的损伤，**每一格都有阴性对照** —— 没有对照的"没打扰"什么都不证明。

| 损伤 | 条件 | 关掉归还 | **开启归还** | 证据 |
|---|---|---|---|---|
| window 焦点被夺 | 6 种动作类型 | — | 归还 12ms–1.5s，8/8，dumpsys 交叉校验 | [B1](docs/experiments/B1-RESULTS.md) [E12](docs/experiments/E12-GMAIL-DEMO.md) |
| 中文 composing 被打断 | 导航点击（滚动两边均 0/20） | **10/20** | **0/20** | [E11](docs/experiments/E11-RESULTS.md) |
| 击键落进副屏输入框 | 不重建 Activity | 0/70 | 0/70 | [E8](docs/experiments/E8-SOFT-KEYBOARD.md) [E15](docs/experiments/E15-SECONDARY-FIELD-CONTAMINATION.md) |
| 击键落进副屏输入框 | **重建 Activity** | — | ❌ **5/30** | [E15](docs/experiments/E15-SECONDARY-FIELD-CONTAMINATION.md) |
| 主屏软键盘被收走 | 不重建 Activity | — | **1/100** | [E19](docs/experiments/E19-IME-DISMISSAL.md) |
| 主屏软键盘被收走 | **重建 Activity** | — | ❌ **13/30** | [E19](docs/experiments/E19-IME-DISMISSAL.md) |
| 外接物理键盘击键落点 | — | **56/120，无上界** | 6/120，**有界但非零** | [E7](docs/experiments/E7-KEYSTROKE-LANDING.md) |
| 看视频 | — | 0 暂停 0 冻结 | 0 暂停 0 冻结 | [E14](docs/experiments/E14-VIDEO-DISTURBANCE.md) |

**后两类损伤指向同一个变量：agent 的动作有没有重建副屏 Activity。**
不是"动作碰了输入框"—— 点副屏输入框 0/20、聚焦 0/20、写文字 1/20（E19）。

**换实现也绕不过去**：`dumpsys input_method` 里有 37 个 `ClientState`，`mCurClient` 只指向其中一个，
且与 `mCurFocusedWindow` 的 client 相同 —— 谁拿到输入焦点，IMMS 就把唯一的绑定移给谁。
所以**任何共用同一输入域的方案都一样**；出路是换**输入域**，见 [ARCHITECTURE §8](docs/ARCHITECTURE.md)。

## 状态与限度

- **仅在模拟器 API 34 验证，未在真机复现**；**外部效度是最大短板** —— 结论只来自三个 app。
- 软键盘收起**原有仪表定位不了**（`ime.dismissed` 45 步 0 次为真 —— 采样点选错位置），
  重做成 50ms 轮询才测出上表那行：[E18](docs/experiments/E18-IME-DISMISSAL-ATTRIBUTION.md) → [E19](docs/experiments/E19-IME-DISMISSAL.md)
- `DISTURB_BUDGET_MS=500` 的**立论依据已被 [E16](docs/experiments/E16-DOSE-RESPONSE.md) 证伪**（九次污染全在
  272–431ms，一次没拦住）。**值保留不动**，注释已改 —— 改护栏需要比现有更硬的证据。
- `back` **已排除**：不是"在副屏不生效"，是**必然生效在主屏上** —— 每步「动作 → 归还焦点」
  保证了下一步派发时焦点在主屏，而系统返回键作用于有焦点的 display。**归还越好使它越必然打错屏。**
  遗留缺口：副屏没有通用的「返回」（[E20](docs/experiments/E20-GMAIL-REPLY-FAILURE.md) 同一次 run 实证）。
- 打扰窗口预算**只在用户可能正在输入时才拉黑**（`ime_present` 三值）。无条件拉黑曾把一次真实任务
  逼成 `impossible`：9 步拉黑 7 个目标，而全程用户并未输入。
- ⚠ **`--free-app` 下的 `launch` 是唯一不受护栏保护的动作**（默认关闭，不带 flag 时行为不变）。
  它走 PC 侧 `adb am start`，不经过 `act`、**没有焦点归还** —— 实测启动后主屏 `mCurrentFocus=null`，
  正是 E7 量到「击键 120/120 落进 agent 工作区」的状态。代价在 observation 与 `launch.json`
  两处强制暴露，用户可能在输入时一律拒发。正确做法是搬进设备侧并入 `act`，**未做，时间原因**。
- ⚠ **一条未解释的异常**：一次真实 run 里 agent 写进副屏的文本被读回时多出 2 个字符
  （`…@gmail.com` → `…@gmail.comge`）。6 组共 50 次未能复现，也排除了自动补全与 SET_TEXT 本身。
  **判定为未知，不是不成立** —— 原始 trajectory 在 [`E15-unexplained-two-extra-chars/`](docs/experiments/trajectories/E15-unexplained-two-extra-chars/)。

---

`docs/` 设计与 B1–E20 实测记录（**先读 [docs/README.md](docs/README.md)**）· `android/` 只做感知与执行 ·
`harness/` PC 侧 agent（[说明](harness/README.md)）· `tools/` 实验脚本 ·
`tests/` 98 条离线测试，设备侧另有 15 条 JVM 单测
