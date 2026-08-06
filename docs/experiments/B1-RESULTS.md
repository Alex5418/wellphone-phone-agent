# B1 · 焦点归还的动作维度覆盖 — 结果

**日期** 2026-08-06 · **标签** `[非root可复现]`（全程 `adb unroot`，uid=2000(shell)）· API 34 · scrcpy VirtualDisplay
**上游** E6 焦点归还（`EXPERIMENTS.md` E6 章节）· 本任务把归还从 SCROLL_FORWARD 扩展到全部动作

---

## 一句话结论

**归还对 CLICK / SET_TEXT / LONG_CLICK / SCROLL_BACKWARD / FOCUS 全部有效**，唯一例外是
CLICK 的一个特殊副作用场景（见「★ 唯一失败案例」）。同时发现一个 E6 未覆盖的新行为：
**归还关闭时，被夺走的击键不一定消失——它们会流入副屏上此刻有焦点的输入框。**

---

## 环境与方法

| 项 | 值 |
|---|---|
| 设备 | `wellphone_a14` AVD（Android 14 / API 34，`userdebug` 但全程 unroot） |
| 副屏 | scrcpy `--new-display=1280x720`，display id 每轮动态解析（本次序列 2） |
| 主屏 | Dialer 搜索框 `open_search_view_edit_text`（E6 同款） |
| 归还 | DORESTORE 指令，`restoreAct=FOCUS`（E6 的零副作用归还原语） |
| 打字 | **硬件键盘事件注入**（`adb emu event text "1234567890"`，500ms/10字符循环 ≈ 20 字符/秒） |
| 计数 | FIELD 广播（isFocused 优先，见下方验证） |

> **打字方式的替换说明（诚实披露）**：任务要求"真实键盘手打"。本人在模拟器窗口焦点与
> console `event send` 两条路径均无法产生击键（前者因非交互会话的窗口无法取得输入焦点，
> 后者事件根本不进 guest），最终用 `adb emu event text` 走**模拟器虚拟键盘（qwerty2 设备）的
> 硬件事件路径**注入——与宿主键盘同一条 kernel→InputDispatcher→IME 链路，区别于被任务
> 禁止的 `adb shell input text`（软件注入）。速率约为人手 4 倍，判据只会更严。
>
> **环境事件**：R1–R2rep 在第一个模拟器实例上完成；随后模拟器 guest 冻结（adb/console 双通道
> 无响应，与负载无关的 WHPX 偶发），重启后完成 R3–R11。所有轮次的测量方法、计数器、打字
> 链路均相同，数据跨实例可并表。

### 代码改动（最小化，不动归还逻辑）

1. `DORESTORE` 的 `act` 分支补齐 `FOCUS`（矩阵要求；原实现只有 CLICK/SCROLL_* /LONG_CLICK/SET_TEXT）。
2. `DORESTORE` 增加可选 `text` 锚点：About 页 "Device name" 行 `id=null`，按任务"换目标"规则
   不成立（目标本来就是任务指定的该行），故参照 DO 指令既有逻辑加了 text 查找，归还逻辑零改动。

---

## 计数器验证（开工第一件事）

```
$ adb emu event text "1234567890"        # 硬件路径打 10 个字符
FIELD display=0 id=com.google.android.dialer:id/open_search_view_edit_text
      len=15 tail='hello1234567890' focused=true sel=15..15 pickedBy=FOCUSED cands=2
                                        # len 5 → 15，+10 精确 ✓
```

- 选择规则生效：`pickedBy=FOCUSED`（优先 isFocused 节点，非"文本最长"），
  `open_search_bar` 提示语容器（len=24 常量）未被误选。
- 空框行为与 E6 一致：`getText()` 返回 hint（`len=24 tail='ch contacts & places' sel=-1..-1`）。

---

## 结果矩阵

> Δ = T2 − 触发瞬间（触发后 15 秒内主屏计数器增量）。基线轮触发后击键应 ≈0
> （+1/+2 为快照读取到焦点被夺之间 ~50ms 窗口的滞留字符，如实记录）。

| 动作 | restore | ok | restored | total ms | 副屏生效 | mCurrentFocus 保住 | 丢字 Δ | 标签 |
|---|---|---|---|---|---|---|---|---|
| CLICK (switchWidget) | false | true | SKIPPED | — | ✅ ui_night_mode 2→1 | ❌ null | 0 | [非root可复现] |
| CLICK (switchWidget) | true | true | **refresh=false** | 798 | ✅ ui_night_mode 1→2 | ❌ null | 1 | ★ 失败，复现×2 |
| CLICK (switch_bar)※ | true | true | FOCUS 142ms | 164 | ✅ bluetooth_on 1→0 | ✅ Dialer | +311 | [非root可复现] |
| SET_TEXT | false | true | SKIPPED | — | ✅ 副屏输入框 = 值 | ❌ null | 0（主屏冻结） | ⚠️ 击键泄漏 +330 |
| SET_TEXT | true | true | FOCUS 14ms | 25 | ✅ 副屏输入框 = 值 | ✅ Dialer | +310 | [非root可复现] |
| LONG_CLICK | false | true | SKIPPED | — | ✅ AtchDlg 弹出 | ❌ null | 2 | [非root可复现] |
| LONG_CLICK | true | true | FOCUS 37ms | 60 | ✅ AtchDlg 弹出 | ✅ Dialer | +316 | [非root可复现] |
| SCROLL_BACKWARD | false | true | SKIPPED | — | ✅ 列表上滚 | ❌ null | 1 | [非root可复现] |
| SCROLL_BACKWARD | true | true | FOCUS 9ms | 14 | ✅ 列表上滚 | ✅ Dialer | +310 | [非root可复现] |
| FOCUS | false | true | SKIPPED | — | ✅ switch focused=true | ❌ null | 1 | [非root可复现] |
| FOCUS | true | **false** | FOCUS 31ms | 45 | ⚠️ 已聚焦，动作 no-op | ✅ Dialer | +301 | [非root可复现] |

※ 换目标：见 ★ 唯一失败案例一节（按"换目标规则"第 3 条记录）。

---

## 逐动作原始记录

### CLICK → switchWidget（Dark theme 开关）

```logcat
# R1 restore=false —— 基线（复现 E6 失败形态）
RESTORE act=CLICK ok=true restored=SKIPPED(restore=false primary=true) action=91ms
FIELD 触发瞬间 len=365   T2(+15s) len=365   → Δ=0
POST-FOCUS: Display 0 mCurrentFocus=null     Display 2 SubSettings
POST-NIGHT: ui_night_mode 1                  ← 副屏开关真实翻转
肉眼观察：Dark theme 生效；主屏光标冻结，字打不进去。

# R2 restore=true —— ★ 归还失败（详见失败案例一节）
RESTORE act=CLICK ok=true via=FOCUS delay=0 refresh=false focusOk=false
         isFocused=true sel=571..571 action=56ms restore=742ms total=798ms
FIELD 触发瞬间 len=571   T2(+15s) len=572   → Δ=1
POST-FOCUS: Display 0 mCurrentFocus=null     Display 2 SubSettings(42efe58)
```

### CLICK → switch_bar（Bluetooth 开关，换目标后）

```logcat
# R3 restore=true
RESTORE act=CLICK ok=true via=FOCUS delay=0 refresh=true focusOk=false clickOk=null
         isFocused=true sel=976..976 action=56ms restore=108ms total=164ms
FIELD 触发瞬间 len=975   T2(+15s) len=1286   → Δ=+311
POST-FOCUS: Display 0 mCurrentFocus=Dialer(548cfe)   ← 窗口 token 未变，无重建
POST-IME:   mServedView=dialer open_search_view_edit_text
POST-NIGHT: bluetooth_on 0                          ← 开关真实生效（事前为 1）
肉眼观察：主屏打字全程连续，无需触碰输入框。
```

### SET_TEXT → Settings 搜索框 `open_search_view_edit_text`（val=`1234567890`）

```logcat
# R4 restore=false —— 基线 + 新发现
RESTORE act=SET_TEXT ok=true restored=SKIPPED(restore=false primary=true) action=34ms
FIELD 触发瞬间 len=200   T2(+15s) len=200   → Δ=0（主屏冻结）
FIELD display=2 len=340                      ← 副屏搜索框从 hint(15) 涨到 340，+330 泄漏！
POST-FOCUS: Display 0 mCurrentFocus=null     Display 2 SearchActivity
肉眼观察：主屏字打不进去；**击键没有消失——全部灌进了副屏搜索框**（见"附带发现 A"）。

# R5 restore=true
RESTORE act=SET_TEXT ok=true via=FOCUS delay=0 refresh=true focusOk=false clickOk=null
         isFocused=true sel=400..400 action=11ms restore=14ms total=25ms
FIELD 触发瞬间 len=400   T2(+15s) len=710   → Δ=+310
FIELD display=2 len=10 tail='1234567890'    ← 副屏搜索框恰为 SET_TEXT 的值，零泄漏
POST-FOCUS: Display 0 mCurrentFocus=Dialer
肉眼观察：主屏打字全程连续；副屏搜索框内容与写入值逐字节一致。
```

### LONG_CLICK → About 页 "Device name" 行（text 锚点 `sdk_gphone64_x86_64`）

```logcat
# R6 restore=false —— 基线
RESTORE act=LONG_CLICK ok=true restored=SKIPPED(restore=false primary=true) action=44ms
FIELD 触发瞬间 len=932   T2(+15s) len=934   → Δ=2
POST-FOCUS: Display 0 mCurrentFocus=null
            Display 2 mCurrentFocus=AtchDlg:com.android.settings/...SubSettings
肉眼观察：副屏弹出文本选择菜单（AtchDlg）；主屏光标冻结。

# R7 restore=true
RESTORE act=LONG_CLICK ok=true via=FOCUS delay=0 refresh=true focusOk=false clickOk=null
         isFocused=true sel=1137..1137 action=23ms restore=37ms total=60ms
FIELD 触发瞬间 len=1136  T2(+15s) len=1452  → Δ=+316
POST-FOCUS: Display 0 mCurrentFocus=Dialer  ← 归还成功，尽管副屏还挂着 AtchDlg
肉眼观察：主屏打字全程连续；副屏长按菜单保持弹出（不干扰归还）。
```

### SCROLL_BACKWARD → `recycler_view`（Display 页，列表预滚到底）

```logcat
# R8 restore=false —— 基线
RESTORE act=SCROLL_BACKWARD ok=true restored=SKIPPED(restore=false primary=true) action=12ms
FIELD 触发瞬间 len=205   T2(+15s) len=206   → Δ=1
POST-FOCUS: Display 0 mCurrentFocus=null
dump 对比：可见行 Auto-rotate screen / Other display controls → Lock screen / Dark theme
肉眼观察：副屏列表上滚一屏；主屏光标冻结。

# R9 restore=true
RESTORE act=SCROLL_BACKWARD ok=true via=FOCUS delay=0 refresh=true focusOk=false clickOk=null
         isFocused=true sel=406..406 action=5ms restore=9ms total=14ms
FIELD 触发瞬间 len=406   T2(+15s) len=716   → Δ=+310
POST-FOCUS: Display 0 mCurrentFocus=Dialer
dump 对比：可见行同上（列表真的滚了）
肉眼观察：主屏打字全程连续。
```

### FOCUS → `switchWidget`

```logcat
# R10 restore=false —— 基线
RESTORE act=FOCUS ok=true restored=SKIPPED(restore=false primary=true) action=17ms
FIELD 触发瞬间 len=936   T2(+15s) len=937   → Δ=1
POST-FOCUS: Display 0 mCurrentFocus=null
POST-IME:   mServedView=android.widget.Switch{...switchWidget}  mInputShown=false
dump：switchWidget focused=true                               ← 动作真实生效
肉眼观察：副屏开关获得 view 焦点；主屏光标冻结。

# R11 restore=true —— 动作本身 ok=false（上轮已聚焦，no-op）
RESTORE act=FOCUS ok=false via=FOCUS delay=0 refresh=true focusOk=false clickOk=null
         isFocused=true sel=1140..1140 action=14ms restore=31ms total=45ms
FIELD 触发瞬间 len=1139  T2(+15s) len=1440  → Δ=+301
POST-FOCUS: Display 0 mCurrentFocus=Dialer
肉眼观察：主屏打字全程连续。
```

---

## ★ 唯一失败案例：CLICK（Dark theme 开关）归还失败 —— 已复现

**现象**（R2 与复现轮 R2rep 完全一致）：

```
R2   : RESTORE act=CLICK ok=true via=FOCUS delay=0 refresh=false focusOk=false ... restore=742ms total=798ms
R2rep: RESTORE act=CLICK ok=true via=FOCUS delay=0 refresh=false focusOk=false ... restore=629ms total=699ms
两轮 Δ 均 ≈0，POST-FOCUS display 0 均为 null。
```

**机制（证据链）**：

1. Dark theme 开关翻转的是**全局 uiMode**（`ui_night_mode` 1↔2 每轮翻转）。
2. 全局主题变化 → **所有 Activity 重建**。窗口 token 证据：
   - Settings SubSettings：`97feab3` → `42efe58` → `709078f`（每轮都变）
   - Dialer：R1 轮前 `3c7110e` → R2 轮前 `a89aefb` → R2rep 轮前 `b4d213d`（每轮都变）
3. 重建发生在动作返回后不久，把**归还目标的快照杀死**：`node.refresh() → false`。
   归还原语拿到的是一具死快照，`performAction(ACTION_FOCUS)` 无从分发 → 焦点留在副屏。
4. 对照：同是 CLICK，Bluetooth 开关（无全局副作用）`refresh=true`，归还成功（R3）。

**结论**：失败不是"CLICK 的归还无效"，而是**"动作的副作用销毁了归还目标的窗口"**。
这正是 E6 适用边界中"副屏动作引发 Activity 跳转时归还是否有效"的未验证项，
本实验给出了比跳转更强的实证：**任何导致目标窗口重建的动作，快照型归还都会失效**。

**工程含义（供后续阶段参考，非本任务结论）**：快照在动作前抓取、动作后使用，对
"动作引发窗口重建"这一族副作用无防护。原子封装若想覆盖此类动作，归还目标需要在
**动作后重新抓取**（e.g. 动作后按 id 重新 findFocus），而不是用动作前快照。

### 换目标记录（按任务"换目标规则"第 3 条）

- 换了什么：CLICK 的额外验证目标从 `switchWidget`（Dark theme）换成 `switch_bar`
  （Bluetooth 主开关，Settings → Connected devices → Bluetooth，同样原地翻转不跳页）。
- 为什么换：`switchWidget` 的副作用（全局主题翻转→Activity 重建）会必然杀死归还快照，
  用它无法回答"CLICK 这个动作类型的归还是否有效"。Bluetooth 开关无全局副作用，
  与 switchWidget 构成唯一变量对照，把因果钉死在"副作用"而非"CLICK"。
- 原矩阵的 switchWidget 两轮照常入表（false 基线 / true 失败+复现）。

---

## 附带发现 A（新）：归还关闭时击键的去向取决于副屏焦点窗口

R4（SET_TEXT, restore=false）中，主屏计数器冻结（Δ=0），但**击键没有消失**：
副屏 Settings 搜索框 15 → 340 字符（+330，全是 `1234567890` 循环）。

- E6 及本任务其他基线轮中击键被"丢弃"，是因为副屏焦点窗口（Settings 列表页）**没有输入框**。
- R4 的副屏窗口**恰有已聚焦的 EditText** → 击键全部灌入。
- 含义：归还不只是"保住主屏输入"，也是**防止用户击键污染副屏 app 状态**的护栏。

## 附带发现 B：FOCUS 动作本身在已聚焦目标上返回 ok=false

R11 的副屏动作 `FOCUS on switchWidget` 返回 `ok=false`（R10 已把焦点给它，动作是 no-op），
但**归还照样成功**——再次独立复现 E6 核心机制：抢焦点发生在动作分发路径，
与动作是否生效无关；归还同理。

## 附带发现 C：基线轮的 +1/+2 滞留字符

各基线轮触发后 Δ 为 0–2 字符，来源：FIELD 快照读取到焦点被夺之间存在 ~50ms 窗口，
其间击键仍落在主屏。与 E6 的"0 字符"同级（≤2 及格线内），不作为异常。

---

## 完成标准对照

- [x] 矩阵 10 行全部有结果（含换目标轮与复现轮，共 12 轮）
- [x] 计数器开工时验证（+10 精确）
- [x] 归还失败动作已单独标注并复现（R2 + R2rep 同条件）
- [x] 全部 `adb unroot`（uid=2000 shell）取得
- [x] 原始日志贴原文
- [ ] 提交（本文件随 B1 commit 提交，message 见 git log）
