# SUBTASK-E11 · 中文 composing 打断的 2×2 矩阵重跑（每格 ≥20 次）

> **分支**：`exp/e11-composing-matrix`（若已存在则在其上继续，不要重建）
> **性质**：两个子任务，**按顺序做，做不完就停**。E11-1 做完就是有效交付。做完一个 commit 一个。
> **纪律**：见下方六条。核心一句 —— **你的产出是数据和代码，不是意见。**
> **禁止**：架构选型、方案推荐、对已有结论的重新解释、修改护栏逻辑。

**开工前必读**（按顺序，不可跳）：

1. `docs/experiments/E10-COMPOSING-BREAK-CAUSE.md` —— 本任务的直接上游。
   **§4「一个测不到的东西」和 §6「数据质量」尤其重要**：前者说明有一个看似合理的
   测量方式是**根本测不到**的（照抄会得到恒为 false 的假数据），后者说明上一轮
   为什么不能下结论（每格 1–4 次、约一半 run 作废）。
2. `docs/experiments/E9-PINYIN-COMPOSING.md` —— 注意顶部那条 ⛔ 更正：
   **E9 的因果归属是错的**（动作类型与归还开关同时变了）。不要复用它的结论。
3. `docs/HARNESS-SPEC.md` §12「已知坑」。

---

## 环境重建（每次开工，不可跳过）

```bash
cd <repo>

# 1. 模拟器（若未运行）
"$ANDROID_HOME/emulator/emulator" -avd wellphone_a14 -no-boot-anim &
until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 4; done

# 2. 屏幕别睡 —— 之前的 demo 任务把超时改成过 60 秒，半夜必挂
adb shell settings put system screen_off_timeout 1800000
adb shell svc power stayon true
adb shell input keyevent KEYCODE_WAKEUP

# 3. 无障碍服务（改过代码必须关掉再打开，否则跑的是旧实例）
cd android && ./gradlew :app:installDebug --offline && cd ..
adb shell settings put secure accessibility_enabled 0
sleep 1
adb shell settings put secure enabled_accessibility_services \
  com.example.phoneagent/com.example.phoneagent.AgentAccessibilityService
adb shell settings put secure accessibility_enabled 1
sleep 4

# 4. 副屏（scrcpy 4.1 在 ~/Downloads/scrcpy-win64-v4.1/）
#    ⚠ display id 每次重开都变（本项目见过 2/3/4/6），任何硬编码都是 bug
"$HOME/Downloads/scrcpy-win64-v4.1/scrcpy.exe" --new-display=1280x720 --no-audio &
sleep 12

# 5. 通道（设备重连后失效）
adb forward tcp:8760 localabstract:phoneagent
```

每轮测试前状态确认：

```bash
python tools/manual_test_helper.py --check
```

必须四项全 ✓（主屏醒着 / 主屏有聚焦输入框 / 输入法弹着 / 副屏有可用目标）。
**不满足先修状态，不要相信上一次的状态。**

副屏 id 用 `harness.observe.pick_secondary_display(tp.state())` 取，不要写死。

---

# E11-1 · 2×2 矩阵重跑（最高优先级，做完即为有效交付）

## 目标

把 E10 的四格结论从「1–4 次样本」做到**每格 ≥20 次有效运行**，给出可用的比例。

**已知**（E10，方向可信但样本太少）：

- 滚动类动作（不产生窗口/Activity 变更）：打断 0/4
- 导航点击（Activity 变更）+ `restore=false`：打断 3/3
- 导航点击 + `restore=true`：打断 1/3 ← **这一格最关键，也最不准**

**待测**：每格的打断比例（n≥20）。**不要重新解释因果，只补数据。**

## 前提 / 什么不许动

- 不要改 `harness/loop.py` 里的 `restore=True`（那是护栏，没有开关）
- 不要改 `AgentCommands.kt` 的归还逻辑
- 本任务只新增一个批量脚本 `tools/exp_composing_matrix.py`，其余代码不动

## 测试矩阵

四格，每格 **≥20 次有效运行**：

| 副屏动作 | `restore=false` | `restore=true` |
|---|---|---|
| **scroll**（对副屏可滚动区域发 `SCROLL_FORWARD`） | | |
| **nav**（依次点击 `Screen timeout` → `30 seconds` → `Navigate up`） | | |

单次运行的固定流程：

1. 清场：`am force-stop com.example.composetest` → 重启 → 点 Body 输入框
2. **就绪校验**（见下方「已知陷阱」第 1 条，必做）
3. 逐键点软键盘打 `zhonghuaren`（每键间隔 0.3s）
4. 记 `before` = 输入框文字。**若 `before != "zhong hua ren"` → 本次作废，重来，不进统计**
5. 起一个后台线程继续逐键打 `mingu`（每键间隔 0.45s）
6. 主线程按矩阵行做 3 次副屏动作（每次间隔 1.2s），`restore` 按矩阵列
7. 等打字线程结束 + 1.5s，记 `after` = 输入框文字
8. 判定打断：`before.count(" ") >= 2 and after.count(" ") < before.count(" ")`

## 判据

| # | 观察点 | 采集方式 |
|---|---|---|
| ① | composing 有没有被打断 | **拼音分段空格数**：Gboard 在 composing 态把音节用空格分开显示（`zhong hua ren`），被强制上屏时空格消失（`zhonghuaren`）。取动作前后的空格数比较 |
| ② | 本次运行是否有效 | `before == "zhong hua ren"` 且 `after` 长度 > `before` 长度（说明续打确实落地了） |
| ③ | 打扰窗口 | `act` 响应的 `timing.disturb_ms`，逐次记录 |

**不要用截图判定**（无人值守没人看图）。**不要用候选条判定**（见陷阱第 3 条）。

## ⚠️ 已知陷阱（全部是本项目实际踩过的）

**1. 起点丢字 —— 上一轮约一半 run 作废在这里。**
清场后立刻打字，前 2–3 个键会丢（实测得到 `ong hua ren` / `n g hua ren` 这类起点）。
原因是 app / IME 还没就绪。**开工第一件事就是修它**，建议做法：

```
点完输入框后：
  a. 轮询 tp.state()["ime_present"] == True（最多 5s）
  b. 打一个 'a'，轮询输入框长度变成 1（最多 3s）
  c. 按退格键（坐标 994, 2024）删掉它，轮询长度回到 0
  d. 这时才开始正式序列
```

修完必须**贴出证据**：连续 10 次清场+打 `zhonghuaren`，10 次都得到 `zhong hua ren`。
**做不到就不要开始跑矩阵** —— 起点不稳，四格数据全是噪声。

**2. 不要用 `adb shell input text` 打字。**
那是直接向焦点窗口注入按键，走的是**硬件键盘链路**，不经过 IME 的 composing。
本任务测的正是 composing，必须用 `adb shell input -d 0 tap <x> <y>` 点软键盘坐标。
键位坐标（1080×2400，已实测）：

```python
KEYS = {"q":(58,1716),"w":(164,1716),"e":(271,1716),"r":(379,1716),"t":(486,1716),
        "y":(593,1716),"u":(700,1716),"i":(806,1716),"o":(913,1716),"p":(1020,1716),
        "a":(112,1870),"s":(218,1870),"d":(325,1870),"f":(432,1870),"g":(538,1870),
        "h":(644,1870),"j":(752,1870),"k":(859,1870),"l":(966,1870),
        "z":(218,2024),"x":(325,2024),"c":(432,2024),"v":(539,2024),"b":(646,2024),
        "n":(752,2024),"m":(859,2024)}
BACKSPACE = (994, 2024)
```

**3. 不要用候选条判断有没有被打断。**
Gboard 的候选画在 canvas 上，无障碍树里**没有对应节点**。上一轮那个候选条计数器
前后恒为 0 —— 它不是"候选条没变"，是**根本没测到**。拿它下结论会得到全假的结果。

**4. 不要用 `focusedPkgOnPrimary()` / a11y 判断"这次有没有夺走焦点"。**
`AccessibilityWindowInfo.isFocused()` 是 **per-display** 语义，跨 display group 的
抢焦点它完全看不见（实测恒为 false，而同一时刻 `dumpsys` 显示 `mCurrentFocus` 已是 null）。
唯一能看见的是 `dumpsys window displays`，但一次往返 200–400 ms，**下一次点击已经把
焦点带回来了**，读到的永远是"焦点没动"。
→ **本任务不需要逐次判断夺焦点**，那已由 E10 单独确立。只测 composing 有没有断。

**5. 空 EditText 的 `getText()` 返回的是 hint 而非空串。**
判"填了没有"要看 `hint_text` 字段（`harness.models.Node.effective_text` 已处理）。

**6. `dumpsys window displays` 里每块屏各有一行 `mCurrentFocus`，顺序不定。**
本项目见过 `0→2`、`2→0`、`0→4`、`6→0`。任何"取第一个"的写法都是 bug。

**开工第一件事：验证测量工具本身。**
按陷阱 1 的方法修完就绪问题后，跑 10 次连续清场+打字，**贴出 10 行原始输出**，
10 次全部得到 `zhong hua ren` 才算通过。测量工具不可信则一切结论不可信。

## 阳性对照（必须先跑，不通过就停）

**先跑 `nav` × `restore=false` 这一格的前 5 次。** 按 E10，这一格**必须**看到打断。

- 5 次里 ≥3 次打断 → 测试台是活的，继续跑完整矩阵
- 5 次里 0 次打断 → **停下，不要继续跑另外三格**。写进 `PROGRESS.md` 和报告：
  "阳性对照未复现，测试台状态存疑"，并贴出这 5 次的原始输出。
  这种情况下另外三格的"没打断"没有任何意义。

## 交付：`docs/experiments/E11-RESULTS.md`

**主表（预填，每格必须有数字或"未测 + 原因"）**：

| 副屏动作 | restore | 有效运行数 | 打断次数 | 打断率 | 作废次数 | 作废原因 |
|---|---|---|---|---|---|---|
| scroll | false | | | | | |
| scroll | true | | | | | |
| nav | false | | | | | |
| nav | true | | | | | |

**打扰窗口（每格的 disturb_ms 分布）**：

| 副屏动作 | restore | 中位数 | 最小 | 最大 |
|---|---|---|---|---|
| scroll | false | | | |
| scroll | true | | | |
| nav | false | | | |
| nav | true | | | |

**原始数据**：全部运行逐条写入 `docs/experiments/E11-raw.jsonl`，每行一个 JSON：

```json
{"n":1,"action":"nav","restore":false,"before":"zhong hua ren","after":"zhonghuarenmin",
 "sp_before":2,"sp_after":0,"broke":true,"disturb_ms":[20,14,8],"valid":true}
```

表下按四格分节，每节**贴 3 条原始 jsonl 行 + 一句肉眼观察**（例如"打断时 after 里
空格全消失，且末尾多出一个新的 composing 段"）。

## 特别标注

**若 `nav` × `restore=true` 这一格的打断率落在 20%–80% 之间**（即既非"基本不断"
也非"基本必断"），立刻单独标出，并在该格补跑 10 次。
这一格是整个任务的重点 —— 它决定「归还到底算不算保护」，**比另外三格更需要精确**。

**若某一格出现与 E10 方向相反的结果**（例如 scroll 也开始打断），
单独标出并加做一次复现验证（同条件再跑 5 次）。**不要自行解释原因。**

## 换目标 / 降级的规则

- 副屏页面上找不到 `Screen timeout` / `30 seconds`：
  1. 先 `am start --display <id> -a android.settings.DISPLAY_SETTINGS` 回到显示设置页
  2. 仍找不到 → 换用任意两个**会导航**的条目（点进去 + Navigate up 回来），
     **并在报告里写清换成了什么、为什么换**
  3. 不要换成不导航的条目 —— 那会把 nav 格变成 scroll 格
- 单格连续 5 次都作废（起点不对）→ 停下修就绪问题，不要硬跑
- 时间/额度不够跑满 20 次 → **跑多少报多少，写清实际 n**，不要凑数

## 不要做

- ❌ 不要改 `harness/loop.py` 的 `restore=True` 硬编码
- ❌ 不要改 `AgentCommands.kt` 的归还逻辑或计时
- ❌ 不要用 `adb shell input text` 代替点击软键盘
- ❌ 不要用候选条 / 截图 / a11y 焦点判断打断
- ❌ 不要重新解释 E9 / E10 的因果，也不要提出新的机制假说
- ❌ 不要给架构建议（"建议增加 composing 检测"这类一律不要写）
- ❌ 不要为了让某一格"看起来一致"而丢弃不合口味的运行

---

# E11-2 · 打断之后能不能救回来（若 E11-1 做完还有余力）

## 目标

E9 §仍未验证里的一条：composing 被打断后，用户点回输入框能否恢复？
按机制推断不能（拼音已经上屏），**但没有实测**。

## 做法

在 `nav` × `restore=false` 条件下制造一次打断，然后：

1. 点一下主屏输入框（模拟用户补救）
2. 再打 `guo`
3. 记录最终文字与分段空格数

跑 10 次。判据：`guo` 是接在原拼音串上继续组词（恢复），还是开了一个新的
composing 段而前面的仍是裸字母（未恢复）。

交付：追加到 `E11-RESULTS.md` 的「E11-2」一节，表格 + 10 行原始数据。

## 不要做

- ❌ 不要试图"修复"这个问题，只测现象

---

# 通用纪律（六条）

1. **命令返回成功 ≠ 结果正确。** 每个"成功"都要独立验证。
   本项目实例：`uiautomator dump --display N` 返回成功但**静默忽略** `--display` 参数；
   `performAction` 返回 true 但界面无反应。
2. **不可信的信号**：a11y 的 `isFocused()`（per-display 语义）、Gboard 候选条
   （canvas 绘制，树里没有）、空 EditText 的 `getText()`（返回 hint）。
3. **每轮都会变、不可硬编码的东西**：display id（2/3/4/6 都见过）、短 ID（每次
   observe 重新分配）、`adb forward`（设备重连后失效）。
4. **每次测试前确认状态**（跑 `--check`），不信任上一次的状态。
5. **每条结论标注适用条件**：`[非root可复现]` / API 34 / 模拟器 / Gboard 拼音。
6. **失败原样记录，不要自行"修好"再报成功。** 失败本身就是产出。
   不要反复重跑同一格直到出现"好看"的比例 —— 那会掩盖真实的方差。

## 本轮特别注意

上一轮（E9→E10）的教训是：**两个变量同时变了，于是把结果归因给了错的那个。**
本任务的四格是为了把这两个变量拆开，所以 **`action` 和 `restore` 必须严格按矩阵组合，
不许"顺手改一下别的"**。

**测量工具本身要先验证。** 本项目吃过两次亏：丢字计数器锁在常量上，稳定输出"丢字 0"
这个**正确答案**；候选条计数器恒为 0，看上去像"候选条没变"。
—— **正确答案 + 错误来源，是最贵的那种错。**

---

# 卡住了怎么办

**先记录，再停下。** 记：跑了什么命令、期望什么、实际得到什么、原始报错。

不要做：

- 不要绕过问题去测别的（会打乱矩阵完整性）
- 不要重启模拟器/重装应用"碰运气"直到跑通（结论失去可复现性）；
  确需重建环境时，**记录重建前后的现象差异**
- 不要猜测原因并据此修改测试方案
- **单项超过 3 轮仍无稳定结果 → 记录现象，进入下一项**
  E11-1 做完就是有效交付，E11-2 未完成不算失败

---

# 完成标准

- [ ] 就绪问题已修，并贴出 10 次连续清场打字全部得到 `zhong hua ren` 的证据
- [ ] 阳性对照（nav × restore=false 前 5 次）已跑，结果已记录
- [ ] 主表四格每格都有数字或"未测 + 原因"
- [ ] `E11-raw.jsonl` 包含全部运行（含作废的，标 `valid:false`）
- [ ] 若 nav×true 落在 20%–80%，已补跑 10 次并单独标注
- [ ] 若出现与 E10 方向相反的结果，已复现验证并单独标注
- [ ] 原始日志贴原文，不是复述
- [ ] 每个子任务一个 commit，message 说清做了什么

---

# 无人值守追加

## 过程轨迹：`docs/experiments/E11-PROGRESS.md`

每完成一步**立即追加一行**（不要攒到最后写）：

```
2026-08-06 02:14 | 修就绪问题 | OK 10/10 得到 zhong hua ren
2026-08-06 02:31 | 阳性对照 nav×false 5 次 | OK 打断 5/5
2026-08-06 03:05 | scroll×false 20 次 | OK 打断 0/20，作废 3
```

中途挂掉时这是唯一能定位死在哪的东西。

## 顶层摘要：`docs/experiments/E11-SUMMARY.md`

| 任务 | STATUS | 一句话结论 | 未完成项 |
|---|---|---|---|
| E11-1 | OK / FAILED / PARTIAL / SKIPPED | | |
| E11-2 | OK / FAILED / PARTIAL / SKIPPED | | |

## git

- 分支 `exp/e11-composing-matrix`；**若已存在则在其上继续**，不要重建
- 每个子任务一个 commit
- **不要 push**，留在本地等人工验收
- 不要动 `exp/locator-rework` 分支上的任何已有文件（只新增 `tools/exp_composing_matrix.py`
  与 `docs/experiments/E11-*`）
