# WellPhone · 手机 Agent

在**副屏**上自主操作 Android 应用的 Agent。验收标准只有一条：

> **用户当前正在进行的交互不被中断。**

以「用户在主屏用中文输入法连续打字」作为最严苛的验证场景 —— 它对焦点的依赖最强。

## 为什么这不是一个普通的 GUI Agent

Android 的无障碍框架在**动作分发路径**上绑定了单焦点语义：任何经 a11y 发出的动作，
都会把全系统唯一的 window 焦点夺到目标窗口 —— 与 `performAction` 的返回值无关。
所以 Agent 的每个动作有三重后果：改变目标状态（正常）、打断用户输入（打扰）、
**用户的击键灌进 Agent 的工作区**（正确性故障）。

因此 loop 里有两个常规 Agent 没有的环节：**补偿**（焦点归还，与动作原子绑定）
与**再观测**（不信任动作前的世界模型，也不信任工具的返回值）。

## 架构

```
 display 0  用户主屏（只读，从不下发动作）      display N  scrcpy --new-display（Agent 工作区）
 ─────────────────────────────────────────────────────────────────────────────────────

┌─ PC · harness/ (Python, 零第三方依赖) ─┐             ┌─ Android · AccessibilityService ─┐
│                                        │             │   只做感知与执行，不做决策         │
│   observe → compress → planner (LLM)   │  行协议 JSON │                                  │
│      ↑                      │          │   短连接     │  state    各屏 / 焦点 / 前台包    │
│      │                      ↓          │ ←─────────→ │  observe  节点树 + tree_hash     │
│   verify  ←──  act  ←──  policy 护栏    │             │  act      动作 ⊕ 焦点归还（原子） │
│      │                                 │             │  probe    独立重读（验证专用）    │
│      └─ adbutil ── dumpsys ────────────┼─────────────┼→ 第二条链路，刻意不复用 a11y 结论 │
└────────────────────────────────────────┘             └──────────────────────────────────┘
                    adb forward tcp:$PHONEAGENT_PORT → localabstract:phoneagent
```

**护栏在代码里写死，不是配置项** —— `loop.py` 中 `restore=True` 硬编码，无开关。
能被关掉的护栏不是护栏。可配置的只有策略层（模型、礼貌度、目标包）。

## 跑起来

需要 `adb`、JDK 17+、Python 3.10+、`scrcpy ≥ 3.0`（`--new-display` 从 3.0 开始有）。
设备 Android 11+（`minSdk 30`，实测于模拟器 API 34）。

```bash
scrcpy --new-display                              # 1. 建副屏，别关这个窗口（虚拟屏随进程消亡）
cd android && ./gradlew :app:installDebug         # 2. 装服务
                                                  #    再去「设置 → 无障碍」打开 Phone Agent
                                                  #    ⚠ 改过代码必须关掉再打开，否则跑的是旧实例
adb forward tcp:8760 localabstract:phoneagent     # 3. 通道（设备重连后失效；cli 会自动补一次）

python -m harness.cli selftest                    # 4. 离线自测，66 条，不需要设备
python -m harness.cli run "在设置中关闭深色主题"     # 5. 端到端
```

> Windows 上第 3 步若报 `cannot bind to 127.0.0.1:8760 … (10013)`，是端口落进了
> Hyper-V 保留段。换端口即可：`adb forward tcp:18760 …` 配 `PHONEAGENT_PORT=18760`。

分阶段自验（state → observe → act 单步 → loop）、LLM 后端切换、
以及不经过 LLM 单独调 locator 的办法，见 [`harness/README.md`](harness/README.md)。

## 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `PHONEAGENT_PORT` | `8760` | adb forward 端口 |
| `PHONEAGENT_TARGET_PKG` | `com.android.settings` | 副屏目标应用 |
| `PHONEAGENT_LLM_PROVIDER` | `anthropic` | `anthropic` / `openai` / `rule` / `scripted` |
| `PHONEAGENT_MODEL` | `claude-sonnet-4-5` | 模型名 |
| `PHONEAGENT_BASE_URL` | — | OpenAI 兼容端点。**用 `openai` 时不传会把 key 发去 api.openai.com 然后 401** |
| `PHONEAGENT_MAX_TOKENS` | `4096` | 推理模型的思考过程也吃这个预算 |
| `PHONEAGENT_LLM_TIMEOUT` | `150` | 秒。60s 对推理模型 + 长 observation 偏紧 |
| `PHONEAGENT_POLITENESS` | `normal` | `off`/`normal`/`patient`，只决定 LLM 能否用 `wait`，**不影响归还行为** |
| `PHONEAGENT_RUNS_DIR` | `runs` | trajectory 落盘目录 |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | — | 按 provider 取 |

其余常量一律写死在 `harness/config.py`，且带了各自的实测依据。

## 实测结论

每一格都有阳性对照（关掉归还重跑一遍）—— 没有阳性对照的"没打扰"什么都不证明。

| 用户在主屏干什么 | 关掉归还 | **开启归还（护栏）** | 证据 |
|---|---|---|---|
| 软键盘打字 · 击键落点 | 污染 0 | 污染 0 | [E8](docs/experiments/E8-SOFT-KEYBOARD.md) ×4 复测 |
| 外接键盘打字 · 击键落点 | **120 键中 56 键灌进副屏，且无上界** | 降到 6 键 —— **有界但非零** | [E7](docs/experiments/E7-KEYSTROKE-LANDING.md) |
| 中文输入法连打 · 导航类动作 | **10/20 打断 composing** | **0/20** | [E11](docs/experiments/E11-RESULTS.md) |
| 中文输入法连打 · 滚动类动作 | 0/20 | 0/20 | 同上 |
| 看视频 | 0 暂停 0 冻结 | 0 暂停 0 冻结 | [E14](docs/experiments/E14-VIDEO-DISTURBANCE.md) |

两条输入链路的行为**完全不同**，不能混谈：物理键盘的事件由 InputDispatcher 直接投递到
全局焦点窗口，焦点一走就落到副屏；软键盘则是 IME 通过 `InputConnection` 写入它绑定的
编辑器，失焦时连接解绑，**而且"点屏幕"这个动作本身会把焦点带回来**。
所以外接键盘那一格是**正确性故障**（归还只能减轻，不能消除），软键盘那一格是无污染。

**唯一确认的用户可见代价：软键盘打字时键盘会被收起一次，需手动点一次恢复。**
（[E12](docs/experiments/E12-GMAIL-DEMO.md)：焦点 8/8 归还成功，用户仍需点一次 ——
**我们归还的是 window 焦点，用户需要的是"能继续打字"，两者不等价**。）

焦点归还耗时实测 12ms（滚动）到约 1.5s（副屏节点多时主屏重解析更慢）；
超出 `DISTURB_BUDGET_MS=500` 的目标会被本轮拉黑并上报 —— 全局配置类动作实测 2.5s，
不是"已知边界"而是**被排除出动作空间**。

端到端：主屏用户打字的同时，Agent 在副屏用真实 Gmail 账号发出一封邮件（收件人 / 主题 /
正文 / 发送），焦点 8/8 归还（[E12](docs/experiments/E12-GMAIL-DEMO.md)）。
补上「相比上一步的增删」这层观测后，**弱模型 `deepseek-v4-flash` 8 步独立完成**，
比强模型步数更少、LLM 延迟从 65.6s 降到 10.9s
（[E13](docs/experiments/E13-OBSERVATION-NOT-MODEL.md)）——
结论是 **harness 的质量应该由弱模型来检验**：强模型会用推理掩盖观测层的缺陷。

## 目录

```
docs/       设计（ARCHITECTURE / HARNESS-SPEC）与 B1–E14 的实测记录，先读 docs/README.md
android/    AccessibilityService —— 只做感知与执行
harness/    PC 侧 Agent —— 观测 / 压缩 / 定位 / 验证 / 编排 / 规划
tools/      离线小工具与实验脚本
tests/      66 条离线测试，不需要设备
```

## 状态与限度

- **仅在模拟器 API 34 上验证，未在真机复现**（无可用设备）。
- 软键盘的收起尚未定位到具体是哪个动作触发，也未做无副作用的恢复。
- E14 测的是"会不会暂停 / 长冻结"，不是"会不会掉一帧"—— 唯一能测微卡顿的帧级仪表读不到。
- 样本量不均：中文 composing 矩阵做到每格 n≥20，其余多数实验每组只有 1 次。
- 外接物理键盘场景**归还只能减轻污染、不能消除**；判定为 corner case，未继续投入。
