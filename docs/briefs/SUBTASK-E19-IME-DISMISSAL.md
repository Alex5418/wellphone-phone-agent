# SUBTASK-E19 · 软键盘消失的归因（高频轮询 + 单动作）

**分支** `exp/e19-ime-dismissal`（从 `main` 建）
**性质** 采数任务。**产出是 CSV 与表格，不是意见。**
**纪律** 失败原样记录，不要自行"修好"再报成功。失败本身就是产出。
**禁止** 改 `harness/` 下任何文件；改 `tools/exp_ime_dismissal.py` 的判据逻辑；
改 `DISTURB_BUDGET_MS`。
**预计** 3–4 小时。超时按 §7 降级，不要为了凑满 n 而糊弄。

---

## 0 · 开工前必读（不读会重复踩坑）

**必读，它们是本任务的全部前提：**

- `docs/experiments/E18-IME-DISMISSAL-ATTRIBUTION.md` —— 全文，尤其 §4 和 §6
- `tools/exp_ime_dismissal.py` 的模块 docstring 与 `ImePoller` 的类注释

E18 已经确认的事：

> `act` 响应里的 `ime.dismissed` 字段，**45 步 0 次为真** —— 而收起确实发生过
> （E12 是用户本人在录制现场报的）。原因不是没触发，是**采样点选错了位置**：
> 它只在单次 `act` 内采两点，而四次能定位的消失**没有一次落在那个窗口里**。
> 采样间隔就是 LLM 延迟（实测 1.5–149 s）。

**本任务要回答 E18 回答不了的那个问题**：把采样率提高三个数量级、每轮只发一个动作之后，
**键盘消失能不能归因到某一类动作？**

### ⚠ 本任务最容易出的那个错

**一串全 0 什么都不证明。** 如果轮询器根本读不到键盘，每一组都会是"没消失"，
看起来像个干净的阴性结论 —— 而它只是仪表死了。E18 里 `dismissed` 恒为 0 就是这么来的。

所以 §2 的标定**不可跳过**，而且每次环境重建后都要重做。

---

## 0.5 · 本轮开工状态（外部已完成，**先读这段再动手**）

环境**已经由操作者铺好并验证过**，`§1` 你只需要**确认**，不要重建：

```
模拟器 boot_completed=1 · 无障碍服务已启用
scrcpy 副屏在跑 → 本次 display=3（仍要现读，不要硬编码）
adb forward tcp:18760 已建 · export PHONEAGENT_PORT=18760
副屏 = Gmail 收件箱 · 主屏 = composetest（输入框已聚焦）
```

仪表标定已通过一次：`样本 34，中位间隔 53 ms，阳性 ✓，阴性 ✓`。
**你仍要自己再跑一次 `--check` 并把输出贴进报告**（每次开工都要）。

### 已完成的部分（不要重做）

| 组 | 状态 |
|---|---|
| `control` | ✅ **已完成并提交**：20/20 有效，**0 次消失**。CSV 已在 `docs/experiments/data/e19-control.csv` |
| `rebuild` | ⬜ 待跑。脚本 bug 已修（commit `a5f21af`），冒烟 3 轮出 1 次消失、延迟 47 ms |
| `click_edit` / `focus_edit` / `set_text_edit` / `click_button` | ⬜ 待跑 |

**你的任务就是把剩下五组各跑满 20 轮，然后写报告。**

### 两条会让你白干的硬约束

- **绝不要启动 scrcpy** —— 它在沙箱外，`auto-reject`，上一轮就死在这里
- **绝不要重启模拟器** —— 会连带杀死副屏，而你恢复不了

只看到 `mDisplayId=0` 一块屏 = 副屏没了 → **立刻停下写报告**，这是认可的正常结束。

---

## 1 · 环境重建（每次开工，不可跳过）

不要相信上一次的状态。**下面每一步都要贴出实际输出。**

```bash
# ① 模拟器
#   ⚠ 本 brief 交给你之前，模拟器刚被冷重启过（原因：SystemUI 两屏 ANR，
#     adb devices 显示 device 但 adb shell 全部空返回）。**它很可能还在启动中。**
#     `adb devices` 显示 device ≠ 系统起来了 —— 必须等 boot_completed。
adb devices

# 先等最多 5 分钟，不要一看到空返回就重启一个正在启动的模拟器
for i in $(seq 1 60); do
  b=$(timeout 10 adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  echo "[$i] boot_completed='$b'"
  [ "$b" = "1" ] && break
  sleep 5
done

#   等满 5 分钟仍不是 1 → 才判定为挂了，冷重启：
#   adb emu kill; sleep 10
#   "$LOCALAPPDATA/Android/Sdk/emulator/emulator.exe" -avd wellphone_a14 -no-snapshot-load &
#   然后再跑一遍上面的等待循环

# ② 屏幕别睡（半夜挂在这上面最冤）
adb shell settings put system screen_off_timeout 1800000

# ③ 无障碍服务
adb shell settings get secure enabled_accessibility_services
#   应回显 com.example.phoneagent/com.example.phoneagent.AgentAccessibilityService
#   空的话去「设置 → 无障碍」打开；改过代码要关掉再打开，否则跑的是旧实例

# ④ 副屏 —— ⚠⚠ 已经由外部起好了，**你不要去启动它，你也启动不了** ⚠⚠
#
#   scrcpy 装在 ~/Desktop/Work/whaletech/scrcpy-win64-v4.1/，那是本任务 --dir 之外的目录，
#   你的沙箱会 auto-reject（上一轮就是死在这一步：
#   "permission requested: external_directory (...scrcpy-win64-v4.1\*); auto-rejecting"）。
#   **不要重试、不要找变通、不要 cd 过去。**
#
#   你只需要确认它在：
adb shell dumpsys window displays | grep mDisplayId
#   应该看到两块屏：mDisplayId=0（主屏）和另一块（副屏）。
#   ⚠ display id 每次重开都变（见过 2/3/4/6，本次起来时是 3）。任何硬编码都是 bug，
#     每次都要现读。
#
#   **只看到 display 0 = 副屏没了。这时候立刻停下**，在 PROGRESS.md 和 SUMMARY.md 里
#   写明「副屏丢失，无法自行恢复（scrcpy 在沙箱外），已停止」，然后结束。
#   不要试图绕过，不要继续跑没有副屏的组 —— 那些数据没有意义。

# ⑤ 通道。8760 在本机被 Hyper-V 保留段占了，必须 18760
adb forward tcp:18760 localabstract:phoneagent
export PHONEAGENT_PORT=18760

# ⑥ 副屏放 Gmail 撰写页
adb shell am start --display <SEC> -n com.google.android.gm/.ConversationListActivityGmail
#   Gmail 若停在某封已打开的邮件里，先点 Navigate up 回收件箱，再点 Compose

# ⑦ 主屏 composetest 并点一下输入框
adb shell am start -n com.example.composetest/.MainActivity
adb shell input -d 0 tap 540 800
```

---

## 2 · 仪表标定（每次环境重建后都要做，**不可跳过**）

```bash
python tools/exp_ime_dismissal.py --check
```

必须长这样才算过：

```
① 采样率
   样本 N 个，中位间隔 XX ms，p95 XX ms
② 已知阳性：点主屏输入框，键盘应弹起
   读到 True: ✓
③ 已知阴性：发 BACK 收起键盘
   读到 False: ✓

✓ 仪表可用（判据：阳性 ✓ + 阴性 ✓ + 中位间隔 < 200ms）
```

**打印 ✗ 就不要开跑正式组。** 把 `--check` 的完整输出贴进报告，每次重建各贴一次。

若中位间隔 > 200 ms：如实记录实际值，**照跑**，但要在报告的「限度」里写明
本次实际采样率是多少 —— 结论的时间分辨率被它限死。

---

## 3 · 测试矩阵（优先级 1）

每组 n=20，**每轮只下发一个动作**。命令：

```bash
python tools/exp_ime_dismissal.py --arm <ARM> --times 20 --csv docs/experiments/data/e19-<ARM>.csv
```

| 组 | `--arm` | 副屏动作 | 目标 n | 实际有效 n | 消失次数 | 消失延迟中位 | 备注 |
|---|---|---|---|---|---|---|---|
| **对照** | `control` | **不发任何动作，只等同样长时间** | 20 | | | | |
| A | `click_button` | CLICK 一个按钮 | 20 | | | | |
| B | `click_edit` | CLICK 一个输入框 | 20 | | | | |
| C | `focus_edit` | FOCUS 一个输入框 | 20 | | | | |
| D | `set_text_edit` | SET_TEXT 一个输入框 | 20 | | | | |
| E | `rebuild` | Navigate up → Compose（重建 Activity） | 20 | | | | |

**表格里的每一格都要填。** 没测到的写「未测 + 原因」，不要留空、不要删行。

### `control` 组是本实验的地基，**必须第一个跑**

E18 §4.2 发现：有一次消失时，**前一步压根没有动作**。所以「什么都不做也会消失」
是一个活的可能。若 `control` 组的消失率和某个动作组差不多，那个动作组的阳性就是假的。

**`control` 组跑不出来，整个实验作废。** 不要跳过它去跑"更有意思"的组。

### 跑的顺序

`control` → E（rebuild，先验假说里最可疑的） → B → C → D → A

这样即使只跑完前三组也有结论：**「重建类 vs 什么都不做」的对比是本实验的核心。**

---

## 4 · 判据

CSV 每行：`arm,iter,ime_before,disappeared,latency_ms,disturb_ms,note`

- `ime_before=False` 或 `note` 以 `SKIP` 开头的行 **作废，不计入统计**，
  但要在报告里列出来并注明作废原因
- 统计口径：`消失率 = disappeared 之和 / 有效行数`
- 每组还要给 `latency_ms` 的中位与范围 —— 延迟分布本身有信息量
  （紧跟动作 vs 拖很久，是两种不同的机制）

### 最终要给出的对比表

| 组 | 有效 n | 消失数 | 消失率 | 与 control 的差 |
|---|---|---|---|---|
| control | | | | — |
| ... | | | | |

**不要做统计检验，不要算 p 值。** n=20 支撑不了，给原始比例即可。

---

## 5 · ⚠️ 已知陷阱（全是本项目实际踩过的）

1. **display id 每次都变**（见过 2/3/4/6）。硬编码就是 bug。
2. **8760 端口在本机绑不了**（Hyper-V 保留段，报 10013）。必须 18760。
3. **`observe` 的节点文字是缓存的** —— 敲键后仍报旧值。**不要**自己写 `observe`
   去读主屏字数，脚本里已经用 `state()` 了，别改。
4. **`primary_focus.editable` 在 Compose 应用里是 false**（`findFocus()` 返回
   `android.view.View` 包装节点）。别用它判断"主屏有没有聚焦输入框"。
5. **`BACK` 在副屏是空转**（三次实证）。**但主屏的 BACK 有效** ——
   脚本用它收键盘做阴性标定，那是打在 display 0 上的，不要混淆。
6. **composing 缓冲堆到 800+ 字会 ANR**（设备侧遍历超 5s → `act` TIMEOUT →
   SystemUI 两屏一起 ANR）。本实验不堆文本，但若 `--check` 报主屏字数很大，
   先 `adb shell am force-stop com.example.composetest` 重来。
7. **Gmail 会停在已打开的邮件里**，这时找不到 Compose 按钮。先点 Navigate up。
8. **改过 Android 代码要关掉再打开无障碍服务** —— 本任务不该改它，
   但若你因为别的原因重装了 app，记得这一步。

---

## 6 · 模拟器挂了怎么办

> ⚠ **先读这一段再动手。** 重启模拟器会**连带杀掉副屏** —— scrcpy 的虚拟屏随
> 设备连接消亡，而 scrcpy 在你的沙箱之外，**你重启完就再也拿不回副屏了**。
>
> 所以：**模拟器挂了，优先选择停下报告，而不是重启。**
> 把已采到的数据整理提交，在 `SUMMARY.md` 写明「模拟器在 X 组第 N 轮挂掉，
> 因副屏无法自行恢复而停止」。**这是本 brief 认可的正常结束方式，不算失败。**

只有在**一组数据都还没采到**的情况下，才值得赌一次重启：

```bash
adb emu kill; sleep 10
"$LOCALAPPDATA/Android/Sdk/emulator/emulator.exe" -avd wellphone_a14 -no-snapshot-load &
# 然后重跑 §1 的等待循环 —— 但副屏大概率回不来，回不来就按上面停下报告
```

每次重启在 `PROGRESS.md` 追加一行：

```
2026-08-09 22:14  E 组第 7 轮时 SystemUI 两屏 ANR → 冷重启 → 标定通过 → 从 E 组第 1 轮重跑
```

**重启后必须重跑标定并贴输出。** 重启前后的数据在报告里分开列，不要混成一堆 ——
环境是否等价没人核对过。

**上限：重启 3 次。** 第 4 次挂就停下，把已有数据整理完，如实写明中断原因。

---

## 7 · 降级与放弃规则

- 单组 3 轮内拿不到有效运行 → 记录现象，跳到下一组
- **`control` + `rebuild` 两组完成即为有效交付**，其余组未完成如实写明
- 总耗时超过 4 小时 → 停下整理，不要为了凑满 n 而糊弄
- 若 §3 全部完成且还有余力 → 做 §8（优先级 2）；**没余力就不要开始**

---

## 8 · 优先级 2（有余力才做）：E11 矩阵的第三行

E11 测过 composing 打断 × {scroll, nav}，E15 测过击键落进副屏 × {输入类, 重建类}。
两个矩阵拼起来缺一格：**composing 打断 × 会重建 Activity 的动作类**。

做法：`tools/exp_composing_matrix.py` 加一个新 arm（**只能加不能改** ——
不要动现有 `nav` / `scroll` 的任何默认值和判据），动作序列用
Navigate up → Compose，其余流程与现有 `nav` arm 完全一致。

| 副屏动作 | restore | 目标 n | 实际有效 n | 打断次数 | 打断率 |
|---|---|---|---|---|---|
| rebuild | **false**（阳性对照） | 20 | | | |
| rebuild | true | 20 | | | |

判定打断**只用拼音分段空格数**（`sp_before` / `sp_after`），与 E11 同规则。
**阳性对照那组必须先跑** —— 没有对照的 0/20 什么都不证明。

结果写进 `docs/experiments/E11-RESULTS.md` 的新增一节（**不要改动原有小节**），
标题写明这是后补的第三行。

---

## 9 · 交付物

1. `docs/experiments/E19-IME-DISMISSAL.md` —— 主报告，必须包含：
   - §2 标定输出（每次环境重建各贴一次）
   - §3 那张矩阵表（每格填满）
   - §4 那张对比表
   - 作废行的清单与原因
   - **限度**一节：实际采样率、n 多少、哪些条件没覆盖、结论能说到什么程度
2. `docs/experiments/data/e19-*.csv` —— 原始 CSV，原样提交
3. `PROGRESS.md`（仓库根）—— 每完成一步追加一行（时间 / 做了什么 / 结果）
4. `SUMMARY.md`（仓库根）—— 一行 STATUS + 一句话 + 未完成项

### git（没人能在半夜回答这些）

```bash
git checkout -b exp/e19-ime-dismissal        # 分支已存在就直接切过去
# ... 干活 ...
git add -A && git commit -m "E19: ..."       # ← 显式步骤，不要只放在完成标准里
```

**每完成一组就提交一次**（CSV + PROGRESS 一起）。**不要 push，不要动 `main`。**

---

## 10 · ❌ 不要做

- ❌ 不要改 `harness/` 下任何文件
- ❌ 不要改 `tools/exp_ime_dismissal.py` 的判据逻辑或标定逻辑。
  **只能加不能改**：需要新参数就加新的，不要动现有默认值
- ❌ 不要跳过 `--check` 标定，也不要在标定 ✗ 时开跑正式组
- ❌ 不要跳过 `control` 组
- ❌ 不要因为结果"不好看"就换条件重跑到好看为止
- ❌ 不要做统计检验、不要算 p 值、不要给建议、不要做选型。**只给数据。**
- ❌ 不要 push；不要动 `main`

若某一项确实做不到：**记录"未测 + 原因"，然后继续下一项**。
若必须偏离本 brief 才能推进：**照做，但在报告里单独写明偏离了什么、为什么**。

---

## 11 · 卡住了怎么办

**失败也是产出。** 写下：你想做什么、执行了什么命令、实际输出是什么、你的判断是什么。
不要藏，不要自己"修好"再报成功。

某一组出现明显高于 `control` 的消失率时，**单独标出并加做一次复现验证**（同条件再跑 10 轮）。

---

## 12 · 完成标准（自查）

- [ ] §1 环境重建每一步都贴了实际输出
- [ ] §2 标定输出至少贴了一次，且判定为 ✓
- [ ] `control` 组跑完了
- [ ] §3 矩阵表每格都填了（含"未测 + 原因"）
- [ ] §4 对比表填了
- [ ] CSV 原样提交
- [ ] 作废行列出来了并注明原因
- [ ] 报告有「限度」一节，写明实际采样率
- [ ] `PROGRESS.md` 有逐步记录，含每次模拟器重启
- [ ] `SUMMARY.md` 一行结论
- [ ] 全部提交在 `exp/e19-ime-dismissal`，没有 push
