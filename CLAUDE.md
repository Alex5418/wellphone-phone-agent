# CLAUDE.md

副屏 Android Agent。验收标准只有一条：**用户当前正在进行的交互不被中断。**
这是一份 take-home，交付物是公开仓库 + 演示视频。

**先读 `README.md`（一页），再读 `docs/README.md`（索引）。** 本文件只放
「读文档读不到、但踩过坑」的东西，不复述设计。

---

## 一、这个项目的工作方式（比代码更重要）

这些是用户明确立过的规矩，违反了要被指出来：

1. **所有仪表都是三值的**：成立 / 不成立 / **读不到**。
   「读不到」绝不能折成「不成立」。已实测五种「工具会撒谎」的形态，见 ARCHITECTURE §3。
2. **先验证仪表，再相信读数。** 用已知的阳性/阴性状态标定它。
   最危险的不是读数错，是**读数看着合理且正好支持你预期的结论**。
3. **阴性结论必须有阳性对照。** 没有对照的「没打扰」什么都不证明。
   阳性命中不需要有效性判据（标记字符只可能来自注入器），阴性才需要。
4. **护栏不随模型能力/环境浮动。** 能被关掉的护栏不是护栏；
   `loop.py` 里 `restore=True` 是硬编码，没有开关。可浮动的只有策略层。
5. **改护栏要有比现有更硬的证据。** 即使已知某个阈值的立论依据被推翻，
   也先如实改注释，不擅自改值。
6. **失败原样记录，不许自己"修好"再报成功。** 结论错了就在文档里更正，
   并写明是被什么推翻的 —— 仓库里有多处这样的更正史（E9→E10、E8→E15、E13→E17）。
7. **n=1 不是结论。** 本 session 有过一次 n=1 写了三条结论、n=3 全部推翻的教训（E17 §5）。

---

## 二、环境（每次开工都要重建，别信上次的状态）

```bash
# 模拟器
"$LOCALAPPDATA/Android/Sdk/emulator/emulator.exe" -avd wellphone_a14 -no-snapshot-load &
adb shell settings put system screen_off_timeout 1800000   # 别让屏幕睡

# 副屏（scrcpy 4.1 在 ~/Desktop/Work/whaletech/scrcpy-win64-v4.1/）
./scrcpy.exe --new-display=1280x720 --no-clipboard-autosync &

# ⚠ 端口：8760 在本机被 Hyper-V 保留段占了（报 10013），必须用 18760
adb forward tcp:18760 localabstract:phoneagent
export PHONEAGENT_PORT=18760
```

### 反复踩过的坑

| 坑 | 说明 |
|---|---|
| **display id 每次都变** | 见过 2/3/4/6。任何硬编码都是 bug；`dumpsys` 的输出顺序也不稳定 |
| **`--pkg` 必须放在子命令前** | `cli.py --pkg X run "任务"`，放 `run` 后面报 `unrecognized arguments` |
| **`PHONEAGENT_MAX_TOKENS=16384`** | 4096 时推理模型的思考过程占满预算、`content` 为空 |
| **gradle 要加 `--rerun-tasks`** | 否则命中缓存，`BUILD SUCCESSFUL` 但一条测试都没跑 |
| **改过 Android 代码要关掉再打开无障碍服务** | 否则跑的是旧实例 |
| **`observe` 的节点文字是缓存的** | 敲 5 下后仍报旧值。要新鲜值用 `probe`（内部 `refresh()`）或 `state().primary_focus` |
| **Compose 应用里 `primary_focus.editable=false`** | `findFocus()` 返回 `android.view.View` 包装节点，真 EditText 在树里 |
| **`BACK` 在副屏是空转** | 三次实证，`loop.py` 里标了「跨屏语义未验证」（行号会漂，grep 那句中文）。**副屏没有可靠的"返回"**，用页面上的 `Navigate up` |
| **主屏 composing 缓冲会撑爆** | 拼音堆到 800+ 字时设备侧遍历超 5s → `act` TIMEOUT → SystemUI 两屏 ANR |

### Bash 工具的两个雷（今天各踩了两次以上）

- **heredoc 会吞反斜杠**：`\n`、`\x1f` 在引号 heredoc 里会被吃掉，写 Python 脚本时用
  `chr(10)`/`chr(92)`，或者干脆用 Write 工具写文件。
- **管道里的 `grep` 会缓冲**：不加 `--line-buffered` 时日志迟迟不刷新，
  会让你误判"进程死了"。今天因此误杀过一个正常运行的任务。

---

## 三、当前状态

`main` 已推送到 `github.com/Alex5418/wellphone-phone-agent`（PUBLIC）。

- 测试：**Python 79 条**（`python -m unittest discover -s tests -q`）
  + **Kotlin 15 条**（`cd android && ./gradlew :app:testDebugUnitTest --rerun-tasks`）
  —— Kotlin 那 15 条里只有 13 条有覆盖意义（`LocatorResolver` 8 + `treeHash` 5），
  另两条是 mock 探路与模板 stub。**被问到时报 13，别拿总数充数。**
- 演示视频 `docs/media/demo.mp4`，对应 trajectory `runs/2026-08-07T05-52-07/`
- 实验记录 B1–E17 在 `docs/experiments/`，索引在 `docs/README.md`

### 三条已知但未修的缺陷（面试会被问）

1. **软键盘击键会落进副屏输入框**（E15/E16）。条件：agent 的动作**重建了副屏 Activity**。
   `restore=true` 挡不住 —— 归还的是 window 焦点，撤销不了 IME 输入连接的改绑。
   **根因是架构级的**：一个 user 只有一套 IME 连接（`dumpsys input_method` 的 `mCurClient` 是单数），
   换 UIAutomator/root 都绕不过去。见 ARCHITECTURE §8.1–8.2。
2. **`DISTURB_BUDGET_MS = 500` 的立论依据已被 E16 证伪**（「12ms 与 2526ms 之间没有灰色地带」）。
   九次污染全在 272–431ms，该阈值一次没拦住。**值保留不动**，注释已改。
3. **`BACK` 在副屏不生效**，agent 没有可靠的返回动作。

### 还开着的

见 `ARCHITECTURE.md §9`。要紧的两条：**外部效度**（全部结论只来自 Settings/Gmail/composetest
三个 app，E15 那条最重要的发现只有 Gmail 一个样本点）、**设备侧覆盖率**
（`AgentCommands`/`AgentServer` 仍无测试）。

---

## 四、外包给本地/廉价模型

`docs/briefs/` 下有五份任务包模板（E11/E16/T1/K1/M1），照着写。**两条实测教训**：

- **子 agent 不会自己 commit。** 三次全是把文件留在工作区。
  brief 里要把 `git add -A && git commit` 写成显式步骤，不能只放在完成标准里。
- **复核别人未提交的工作前，先替它提交。** 我用 `git checkout --` 做破坏性验证时
  删掉过 M1 未提交的实现，只能从它留下的测试契约重建。

并行跑用 `git worktree` 隔离，否则会抢同一个工作目录的 checkout。

本地模型走 ollama（`qwen3.5:9b` / `gemma4:26b` 已装）：

```bash
OPENAI_API_KEY=ollama PHONEAGENT_BASE_URL=http://localhost:11434 \
PHONEAGENT_LLM_PROVIDER=openai PHONEAGENT_MODEL=qwen3.5:9b python -m harness.cli run ...
```

`tools/replay_observation.py` 能把历史 observation 回放给任意模型 —— 不占设备、可复现，
用来测策略层换模型后还成不成立。

---

## 五、语言

用户用中文交流，**文档与注释一律中文**，commit message 用英文。
