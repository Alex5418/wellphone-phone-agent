# E19 · 软键盘消失的归因（高频轮询 + 单动作）

**日期** 2026-08-09 · **分支** `exp/e19-ime-dismissal` · 脚本 `tools/exp_ime_dismissal.py`
**环境** 模拟器 `wellphone_a14`（boot=1），scrcpy 副屏 display=3，Gmail 撰写页；主屏 composetest 输入框聚焦。
**数据** `docs/experiments/data/e19-*.csv`（原样提交）

---

## 1 · 要回答的问题

E18 判定「现有仪表在结构上抓不到消失」：`act` 里的 `ime.dismissed` 只在单次 `act` 内采两点，
采样间隔是 LLM 延迟（1.5–149 s），四次可定位的消失没有一次落在窗口里。

E19 换形态：后台线程每 ~50 ms 轮询 display 0 的 `ime_present`（a11y 链路），
每轮**只下发一个动作**，观察动作后 3 s 内键盘是否消失。回答两件事：
键盘是被**哪一类动作**抢走的，以及**它是不是根本不需要动作就会消失**（后者由 `control` 组回答）。

## 2 · 环境与仪表标定

开工状态按 brief §0.5 确认，未重建：

```
adb devices → emulator-5554 device
getprop sys.boot_completed → 1
dumpsys window displays → mDisplayId=3, mDisplayId=0   （副屏在，display=3，现读未硬编码）
settings get secure enabled_accessibility_services → com.example.phoneagent/com.example.phoneagent.AgentAccessibilityService
adb forward --list → tcp:18760 localabstract:phoneagent   （8760 是 Hyper-V 保留段，不用）
```

标定输出（本次开工跑了一次，`--port 18760`）：

```
副屏 display=3  轮询间隔目标=50ms
① 采样率
   样本 36 个，中位间隔 50 ms，p95 77 ms
② 已知阳性：点主屏输入框，键盘应弹起
   读到 True: ✓
③ 已知阴性：发 BACK 收起键盘
   读到 False: ✓

✓ 仪表可用（判据：阳性 ✓ + 阴性 ✓ + 中位间隔 < 200ms）
```

## 3 · 测试矩阵（brief §3）

每轮只下发一个动作；`control` 只等同样长时间不发动作。n=20/组。
`--check` 用 BACK 收起键盘后，正式组由脚本每次先点主屏输入框拉起键盘。

| 组 | `--arm` | 副屏动作 | 目标 n | 实际有效 n | 消失次数 | 消失延迟中位 | 备注 |
|---|---|---|---|---|---|---|---|
| 对照 | `control` | 不发任何动作，只等同样长时间 | 20 | 20 | 0 | — | 前一轮已完成并提交 |
| E | `rebuild` | Navigate up → Compose（重建 Activity） | 20 | 20 | 10 | 49 ms | 复现 10 轮另见 §5 |
| B | `click_edit` | CLICK 一个输入框 | 20 | 20 | 0 | — | |
| C | `focus_edit` | FOCUS 一个输入框 | 20 | 20 | 0 | — | |
| D | `set_text_edit` | SET_TEXT 一个输入框 | 20 | 20 | 1 | 603 ms | 唯一命中，单点，603ms |
| A | `click_button` | CLICK 一个按钮 | 20 | 20 | 0 | — | |

跑的顺序按 brief：`control`（已由上一轮跑完）→ `rebuild` → `click_edit` → `focus_edit` → `set_text_edit` → `click_button`。

### 每轮明细

- `control`：20/20 有效，0 消失。CSV 行 `docs/experiments/data/e19-control.csv`。
- `rebuild`：20/20 有效，10 消失。消失延迟（ms）：52, 45, 52, 47, 53, 55, 50, 48, 44, 45，
  中位 49，范围 44–55。`disturb_ms` 各轮均有值（134–435，与消失与否无关）。
- `click_edit`：20/20 有效，0 消失。`disturb_ms` 24–102。
- `focus_edit`：20/20 有效，0 消失。`disturb_ms` 23–87。
- `set_text_edit`：20/20 有效，1 消失。唯一一次命中在 iter 1，延迟 603 ms。
- `click_button`：20/20 有效，0 消失。`disturb_ms` 30–122。

### 作废行

**无。** 全部 100 轮 `ime_before=True` 且 `note=ok`，没有 `SKIP`、没有 `ime_before=False`。
（`rebuild` 组分两次调用完成 —— `--times 5` 后接 `--times 15`，故 CSV 的 `iter` 列是
`1–5` 再 `1–15`。同脚本同条件、同一次开工、追加到同一文件，合并计为 n=20。
**注意与操作者在修脚本后跑的那 3 轮冒烟区分**：那次写在 `/tmp`，未进本 CSV。）

## 4 · 对比表（brief §4）

| 组 | 有效 n | 消失数 | 消失率 | 与 control 的差 |
|---|---|---|---|---|
| control | 20 | 0 | 0% | — |
| rebuild | 20 | 10 | **50%** | **+50%** |
| click_edit | 20 | 0 | 0% | 0 |
| focus_edit | 20 | 0 | 0% | 0 |
| set_text_edit | 20 | 1 | 5% | +5% |
| click_button | 20 | 0 | 0% | 0 |

不做统计检验，给原始比例。

### 5 · rebuild 复现验证（brief §11）

rebuild 组 10/20 明显高于 control 的 0/20，按 brief §11 同条件加跑 10 轮复现
（写独立文件 `e19-rebuild-rep.csv`，未污染主 CSV）：

| 组 | 有效 n | 消失数 | 消失率 | 消失延迟中位 |
|---|---|---|---|---|
| rebuild 复现 | 10 | 3 | 30% | 48 ms（46–54） |

复现 10 轮内 3 次消失、延迟 46–54 ms，与主组同量级 —— 消失**可以复现**，比例低于主组
（3/10 vs 10/20），但远高于 control 的 0/20。消失延迟全部落在 44–55 ms
（只有 set_text_edit 那次 603 ms 例外）。

## 6 · 限度

- **采样率**：标定中位间隔 50 ms（p95 77 ms），正式组实测 51–55 ms，符合 <200 ms 目标。
  时间分辨率的极限 ~50 ms；消失延迟 44–55 ms 的读数可信到「~50 ms 内」这一档。
- **消失延迟的量级**：rebuild 类消失全在动作后 ~50 ms，紧跟动作；set_text_edit 那次 603 ms，
  是另一档 —— 但 n=1，不构成分布。
- **n 小**：每组 20，rebuild 复现 10。set_text_edit 的 1 次命中不足以归因。
- **仪表与被测共用 a11y 链路**：轮询走 `state()`，与 agent 的 `act` 共用一条链路，
  标定已覆盖阳性/阴性，但「轮询本身不夺焦点」没有单独验证。
- **只测了一种重建动作**（Navigate up → Compose）。其它会重建 Activity 的动作类未覆盖。
- **副屏动作目标**：`choose_target` 只取第一个命中类型的节点；Gmail 页面结构变化时
  目标可能不是「用户会点的那个」，但本实验不关心点了哪个，只关心动作类型。
- **主屏侧完全自动**：`input tap` 固定 (540, 800)，敲键内容固定，不代表真实打字节奏。
- **所有结论来自同一台模拟器、同一个 Gmail/composetest 组合**，外部效度同 E18。

## 7 · 结论（只陈述数据）

1. **重建 Activity 类动作（rebuild）与消失相关**：50%（20 轮中 10）消失，control 为 0/20，
   复现 3/10。消失延迟 44–55 ms，紧跟动作。
2. **单输入框动作（click/focus）无消失**：click_edit 0/20、focus_edit 0/20。
3. **set_text_edit 有 1 次命中（603 ms）**，n=1，不作归因。
4. **click_button 0/20。**
5. **「什么都不做也会消失」在 20 轮里没出现** —— control 0/20。
   E18 §4.2 观察到的「前一步无动作也消失」在本实验的 20 轮 wait 窗口里未复现。
