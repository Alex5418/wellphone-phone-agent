# SUBTASK-E16 · 污染率 vs 打扰窗口的剂量反应

**分支** `exp/e16-dose-response`（从 `main` 建）
**性质** 采数任务。**产出是 CSV 与表格，不是意见。**
**纪律** 失败原样记录，不要自行"修好"再报成功。失败本身就是产出。
**禁止** 改 `harness/` 下任何文件；改 `DISTURB_BUDGET_MS`；改判据阈值。

---

## 0 · 开工前必读（不读会重复踩坑）

先读这两份，**必读**，它们是本任务的全部前提：

- `docs/experiments/E15-SECONDARY-FIELD-CONTAMINATION.md` —— 结论与全部分组
- `tools/exp_secondary_contamination.py` 的模块 docstring 与 `primary_len()` 的注释

E15 已经确认：**agent 重建副屏 Activity 时，用户的软键盘击键会落进副屏输入框，
`restore=true` 挡不住。** 不重建 70 次 0 命中，重建 30 次 5 命中。

**E15 唯一没回答的是本任务要回答的**：命中和打扰窗口长度有没有关系。
现有线索只有一条，很弱：E 组两次命中恰好是十次里窗口最大的两个
（500ms / 441ms，其余 45–302ms），n 太小，只能算提示。

### 为什么这件事值钱

`DISTURB_BUDGET_MS = 500` 是按 **Settings** 标定的（滚动 12ms / 全局配置变更 2526ms）。
但 Gmail 上实测 Compose 871ms、Send 2322ms —— 预算在这里可能既拦不住该拦的，
又拦了不该拦的。**有了剂量反应曲线，这个阈值才有依据，否则它只是个拍出来的数。**

---

## 1 · 环境重建（每次开工，不可跳过）

不要相信上一次的状态。**下面每一步都要贴出实际输出。**

```bash
# ① 模拟器（若没跑）
"$LOCALAPPDATA/Android/Sdk/emulator/emulator.exe" -avd wellphone_a14 -no-snapshot-load &
adb wait-for-device
# 等 sys.boot_completed == 1 再往下

# ② 屏幕别睡（半夜挂在这上面最冤）
adb shell settings put system screen_off_timeout 1800000

# ③ 无障碍服务
adb shell settings get secure enabled_accessibility_services
#   应回显 com.example.phoneagent/com.example.phoneagent.AgentAccessibilityService

# ④ 副屏（scrcpy 4.1 在 ~/Desktop/Work/whaletech/scrcpy-win64-v4.1/）
cd ~/Desktop/Work/whaletech/scrcpy-win64-v4.1 && ./scrcpy --new-display=1280x720 --no-clipboard-autosync &
#   ⚠ display id 每次重开都变（本项目见过 2/3/4/6）。**任何硬编码都是 bug。**
adb shell dumpsys window displays | grep mDisplayId

# ⑤ 通道。8760 在本机被 Hyper-V 保留段占了，必须用 18760
adb forward tcp:18760 localabstract:phoneagent
export PHONEAGENT_PORT=18760

# ⑥ 副屏放 Gmail 撰写页
adb shell am start --display <SEC> -n com.google.android.gm/.ConversationListActivityGmail
#   然后点 Compose 进撰写页。若 Gmail 停在某封已打开的邮件里，
#   先点 "Navigate up" 回收件箱再点 Compose（实测需要这一步）。

# ⑦ 主屏 composetest 并聚焦输入框
adb shell am start -n com.example.composetest/.MainActivity
adb shell input -d 0 tap 540 800

# ⑧ 先验，五项必须全 ✓ 才能开跑
python tools/exp_secondary_contamination.py --check --auto
```

先验长这样才算过：

```
  ✓ 副屏有输入框   ✓ 副屏有按钮   ✓ 读取通道有效
  ✓ 主屏有聚焦输入框   ✓ 敲键器有效   敲 5 下，主屏 82 → 91 字
  → 可以开始
```

**先验没过就不要跑正式组。** 先验不过时拿到的 0 没有意义。

---

## 2 · 目标：一条剂量反应曲线

**唯一问题：命中率随打扰窗口长度怎么变？**

打扰窗口不能直接设定，但可以间接拉长 —— 主屏节点树越大，
`restore` 里重解析主屏越慢，窗口就越长。已实测：主屏 composing 缓冲堆到
288 字时窗口是 600–1500ms，几十字时是 40–300ms。

所以：**用主屏文本长度当自变量。**

### 测试矩阵（全部用 `--arm E`，即会重建 Activity 的那组）

| 组 | 主屏文本规模 | 命令 | 目标 n | 实际 n | 命中数 | 窗口中位 | 命中时窗口 |
|---|---|---|---|---|---|---|---|
| S（小） | 每轮前清空到 <50 字 | `--times 20 --auto --write READY --csv e16.csv` | 40 | | | | |
| M（中） | 不清空，自然堆积 | 同上 | 40 | | | | |
| L（大） | 开跑前先堆到 >250 字 | 同上 | 40 | | | | |

**表格里的每一格都要填。** 没测到的写「未测 + 原因」，不要留空、不要删行。

- S 组怎么清空：每轮之间不需要你手动做，`--times` 小一点分多次跑，
  每次跑之前 `adb shell am force-stop com.example.composetest` 再重启并点一下输入框。
- L 组怎么堆：开跑前让敲键器空跑 ——
  `python -c "import sys;sys.path.insert(0,'.');from tools.exp_secondary_contamination import Tapper;import time;t=Tapper((324,2026));t.start();time.sleep(120);t.stop()"`
  然后确认 `--check --auto` 里"主屏有聚焦输入框 当前 N 字"的 N > 250。

每组都追加到**同一个** `e16.csv`，`arm` 列会区分不了 S/M/L，
所以**每组用不同的 csv 文件名**：`e16-S.csv` / `e16-M.csv` / `e16-L.csv`。

---

## 3 · 判据

CSV 每行是 `arm,action,restore,iter,disturb_ms,hit,extra`。

最终要给出的表：

| 窗口分桶 | 迭代数 | 命中数 | 命中率 |
|---|---|---|---|
| 0–200 ms | | | |
| 200–500 ms | | | |
| 500–1000 ms | | | |
| >1000 ms | | | |

**分桶跨 S/M/L 合并**（自变量是窗口，不是分组；分组只是拉开窗口的手段）。

### 有效性（脚本会自己判，你要把结论抄进报告）

每次运行末尾会打印两项。**任一为 ✗ 的运行，其数据不计入统计**，
但要在报告里列出来并注明作废原因。

```
✓ 动作期间一直在打字   20 个间隔里 19 个主屏文本有变动
✓ 确实制造了打扰       20 次有 disturb_ms
```

**阳性结论不需要有效性判据**（副屏里出现 `x` 只可能来自敲键器），
**阴性结论需要**。所以：作废的运行里若有命中，命中照样计入；0 则丢弃。
这条容易搞反，写进报告时说清楚你怎么处理的。

---

## 4 · ⚠️ 已知陷阱（全是本项目实际踩过的）

1. **`observe` 的节点文字是陈旧的。** 实测连敲 5 下后它仍报 1 字符，
   而屏幕上已有 18 个。要读主屏字数**只用** `--check --auto` 打印的那个数，
   或 `state().primary_focus.text_len`，**不要**自己写 `observe` 去读。
2. **`primary_focus.editable` 在 Compose 应用里是 false**（`findFocus()` 返回
   `android.view.View` 包装节点）。别用它判断"主屏有没有聚焦输入框"。
3. **display id 每次都变。** 见过 2/3/4/6。硬编码就是 bug。
4. **8760 端口在本机绑不了**（Hyper-V 保留段，报 10013）。必须 18760。
5. **composing 缓冲不封顶会 ANR。** 堆到 800+ 字时设备侧遍历超 5s，
   `act` 报 TIMEOUT，然后 SystemUI 在两个屏上一起 ANR。
   脚本的敲键器每 8 下插一次退格来封顶 —— **不要改这个间隔**。
   L 组堆到 250–400 字即可，**不要堆到 600 以上**。
6. **标记字符不能出现在写入值里。** 默认 `x`，写入值用 `READY`（无 x），没问题。
   若你换写入值，先确认它不含 `x`，否则脚本会拒绝启动（这是对的，别绕过）。
7. **Gmail 会停在已打开的邮件里**，这时找不到 `Compose` 按钮。
   先点 `Navigate up` 回收件箱。
8. **`BACK` 在副屏上是空转**（已有三次实证）。不要用它导航。

---

## 5 · 模拟器挂了怎么办

**允许你自己重启并恢复，但必须留下记录。**

```bash
adb emu kill; sleep 10
# 然后重跑第 1 节的 ①–⑧
```

每次重启都要在 `PROGRESS.md` 追加一行：

```
2026-08-07 03:12  模拟器 ANR（SystemUI 两屏都弹）→ 冷重启 → 先验通过 → 继续 L 组第 2 轮
```

**重启后必须重跑先验并贴输出。** 重启前后的数据在报告里分开列，
不要混成一堆 —— 环境是否等价没人核对过。

**上限：重启 3 次。** 第 4 次挂就停下，把已有数据整理完，如实写明中断原因。

---

## 6 · 降级与放弃规则

- 单个分组 3 轮内拿不到有效运行 → 记录现象，跳到下一组
- L 组最难（窗口长、易 ANR）。**若只能完成 S+M，那也是有效交付** ——
  报告里写明 L 未完成及原因即可
- 总耗时超过 4 小时 → 停下整理，不要为了凑满 n 而糊弄

---

## 7 · 交付物

1. `docs/experiments/E16-DOSE-RESPONSE.md` —— 主报告，必须包含：
   - 第 2 节那张矩阵表（每格填满）
   - 第 3 节那张分桶表
   - 每次运行的有效性判定，作废的要列出来并注明原因
   - **限度**一节：n 多少、哪些条件没覆盖、结论能说到什么程度
2. `docs/experiments/data/e16-{S,M,L}.csv` —— 原始 CSV，原样提交
3. `PROGRESS.md`（仓库根）—— 每完成一步追加一行（时间 / 做了什么 / 结果）
4. `SUMMARY.md`（仓库根）—— 一行 STATUS + 一句话 + 未完成项

---

## 8 · ❌ 不要做

- ❌ 不要改 `harness/` 下任何文件
- ❌ 不要改 `DISTURB_BUDGET_MS` 或任何判据阈值
- ❌ 不要修改 `exp_secondary_contamination.py` 的判据逻辑。
  **只能加不能改**：需要新参数就加新的，不要动现有默认值
- ❌ 不要用 `input text` / `input keyevent` 制造击键 ——
  那是物理键盘语义，跟软键盘不同源，用它测出来的是另一个东西
- ❌ 不要因为结果"不好看"就换条件重跑到好看为止
- ❌ 不要给建议、不要做选型。**只给数据。**
- ❌ 不要 push；不要动 `main`。只在 `exp/e16-dose-response` 上提交

若某一项确实做不到：**记录"未测 + 原因"，然后继续下一项**。
若必须偏离本 brief 才能推进：**照做，但在报告里单独写明偏离了什么、为什么**。

---

## 9 · 卡住了怎么办

**失败也是产出。** 写下：你想做什么、执行了什么命令、实际输出是什么、
你的判断是什么。不要藏，不要自己"修好"再报成功。

出现命中（`hit=1`）时**单独标出，并加做一次复现验证**（同条件再跑一轮）。

---

## 10 · 完成标准（自查）

- [ ] 第 1 节环境重建的每一步都贴了实际输出
- [ ] 先验五项全 ✓ 的截图/文本至少贴一次
- [ ] 第 2 节矩阵表每格都填了（含"未测 + 原因"）
- [ ] 第 3 节分桶表填了
- [ ] 三个 CSV 原样提交
- [ ] 每次运行的有效性判定都记了，作废的列出来了
- [ ] 报告有「限度」一节
- [ ] `PROGRESS.md` 有逐步记录，含每次模拟器重启
- [ ] `SUMMARY.md` 一行结论
- [ ] 全部提交在 `exp/e16-dose-response`，没有 push
