# SUBTASK-A-RESULTS.md · 动作类型 × 焦点影响矩阵

> 实验日期：2026-08-04 · AVD wellphone_a14 (API 34, google_apis, userdebug) · scrcpy 4.1
> 全部结论在 `adb unroot`（uid=2000 shell）下取得，除非单独标注。
> 主屏输入模拟：`adb shell input text 1234567890` 循环注入（走 InputManager → IME，与真实键盘同链路）。

---

## 0 · 结论速览

**没有找到任何"不抢焦点"的动作类型。** 在 5 个可测动作中：

| 动作 | 是否执行成功 | 主屏 mCurrentFocus | 键盘 | 丢字 |
|---|---|---|---|---|
| SCROLL_FORWARD | ✅ result=true（run1）/ false（run2，已到列表底部） | Chrome → **null** | run1 收起 / run2 未收起 | **有**（两轮均冻结） |
| SCROLL_BACKWARD | ✅ result=true | Chrome → **null** | 未收起 | **有** |
| LONG_CLICK | ✅ result=true（弹出上下文菜单） | Chrome → **null** | 未收起 | **有** |
| FOCUS | ✅ result=true（view 焦点转移确认） | Chrome → **null** | **收起** | **有** |
| ACCESSIBILITY_FOCUS | ❌ result=false（动作被框架拒绝，未执行） | 未变 | 未收起 | 无（动作未执行，无效观察） |
| EXPAND / COLLAPSE | 未测 | —— | —— | ——（Settings 无 expandable 节点） |

**关键观察**：连 `result=false` 的 SCROLL_FORWARD（列表已到底，动作实际无效果）**仍然夺走了主屏焦点**。
→ 抢焦点发生在动作分发路径本身，与动作是否"真的做了什么"无关（与 E4 对 CLICK 的结论一致，且扩展到滚动/长按/焦点类动作）。

**例外现象（需谨慎解读）**：ACCESSIBILITY_FOCUS 返回 `false` 时**没有**夺焦点。
但这属于"动作未执行"（框架拒绝），不是"该动作类型不抢焦点"的证据 —— 按六条纪律第 6 条照实记录，
**不能**据此断定 ACCESSIBILITY_FOCUS 安全。需要找到一个让该动作成功执行的目标才能定论。

---

## 1 · 矩阵表

| 动作 | 目标节点 | result | 副屏生效 | 主屏 mCurrentFocus | 键盘收起 | 丢字 | 标签 |
|---|---|---|---|---|---|---|---|
| ACTION_SCROLL_FORWARD | `com.android.settings:id/recycler_view`（Display 页 RecyclerView，scrollable） | true（run1）/ false（run2） | ✅ 列表滚到下方（可见行从 Brightness 变为 Screen saver） | Chrome → **null** | run1 ✅ / run2 ❌ | ✅ run1/run2 均冻结 | [非root可复现] |
| ACTION_SCROLL_BACKWARD | 同上 | true | ✅ 列表向上滚回 | Chrome → **null** | ❌ | ✅ 冻结 | [非root可复现] |
| ACTION_LONG_CLICK | About 页 "Device name" 行（LinearLayout，longClickable） | true | ✅ 弹出文本选择对话框（AtchDlg） | Chrome → **null** | ❌ | ✅ 冻结 | [非root可复现] |
| ACTION_FOCUS | `com.android.settings:id/switchWidget`（Switch，focusable） | true | ✅ dump 显示 Switch focused=true | Chrome → **null** | ✅ | ✅ 冻结 | [非root可复现] |
| ACTION_ACCESSIBILITY_FOCUS | switchWidget / recycler_view / "SIM" 行（3 个目标均试） | **false**（框架拒绝） | ❌（a11yFocus 仍为 false） | 未变（Chrome 保持） | ❌ | ❌ | [非root可复现] · 动作未执行，观察无效 |
| ACTION_EXPAND / COLLAPSE | 无 | —— | —— | —— | —— | —— | **未测**：Settings 全部页面（home/display/about/apps/notifications/app-notification）无 expandable 节点 |

---

## 2 · 原始日志（每动作一节）

### A1 · ACTION_SCROLL_FORWARD

**目标**：`com.android.settings:id/recycler_view`（display 3，Display 设置页）

**状态确认（两次触发前均确认）**：
```
Display: mDisplayId=3 (organized)
  mCurrentFocus=Window{... com.android.settings/...DisplaySettingsActivity}
Display: mDisplayId=0 (organized)
  mCurrentFocus=Window{... com.android.chrome/...Main}      ← 主屏持有焦点
mInputShown=true                                            ← 键盘弹出
```

**Run 1（21:55）** —— 列表在顶部，动作真实生效：

```
I PHONEAGENT: DO display=3 vid='com.android.settings:id/recycler_view' act=SCROLL_FORWARD result=true node=androidx.recyclerview.widget.RecyclerView

[AFTER] dumpsys window displays:
  Display: mDisplayId=0 (organized)
    mCurrentFocus=null                                        ← 主屏焦点被夺
  Display: mDisplayId=3 (organized)
    mCurrentFocus=Window{... DisplaySettingsActivity}
[AFTER] input_method: mInputShown=false                      ← 键盘收起
[AFTER] a11y: >>> display=0 windows=2                        ← IME 窗口消失（此前为 3）
```

**副屏生效验证（run1 之后 dump）**：可见行从 `Brightness / Brightness level / Lock display / Lock screen / Screen timeout / Appearance / Dark theme` 变为 `Screen saver / Display size and text / Navigation mode` —— **列表确实向下滚动**。

**Run 2（22:00）** —— 列表已在底部，动作返回 false：

```
[before] field nav-search-keywords len=1017                 ← 数字在流入
[mid]    field nav-search-keywords len=1427                 ← 触发前 10 秒 +410 字符，流量正常
I PHONEAGENT: DO display=3 vid='com.android.settings:id/recycler_view' act=SCROLL_FORWARD result=false node=androidx.recyclerview.widget.RecyclerView
[after]  dumpsys: Display 0 mCurrentFocus=null               ← 焦点仍被夺
[after]  input_method: mInputShown=true                      ← 键盘没收起（与 run1 不同）
[after]  field len=1427                                      ← 触发后 12 秒零增长，数字中断
```

> 肉眼观察（scrcpy 窗口）：两次列表均无滚动动画之外的异常；主屏键入在触发瞬间起不再出现在地址栏。
> 注意 run1/run2 键盘表现不同（收起/未收起），但 **mCurrentFocus 两轮都变 null、数字两轮都冻结** —— 焦点被夺是稳定的。

### A2 · ACTION_SCROLL_BACKWARD

**目标**：`com.android.settings:id/recycler_view`（同上）

```
[before] field len=1427
[mid]    field len=1847                                     ← 触发前 +420，正常
I PHONEAGENT: DO display=3 vid='com.android.settings:id/recycler_view' act=SCROLL_BACKWARD result=true node=androidx.recyclerview.widget.RecyclerView
[after]  dumpsys: Display 0 mCurrentFocus=null               ← 焦点被夺
[after]  input_method: mInputShown=true                      ← 键盘未收起（IME 窗口仍在，windows=3）
[after]  a11y: win pkg=com.android.chrome focused=false      ← Chrome 窗口失去焦点标志
[after]  field len=1847                                      ← 触发后零增长，数字中断
```

**副屏生效**：列表向上滚回（scrcpy 肉眼可见滚动）。**肉眼观察**：主屏地址栏字符流在触发后停滞。

### A3 · ACTION_LONG_CLICK

**目标**：About 页（MyDeviceInfoActivity）"Device name" 行，通过 text 定位锚点
（"Device name" 行的 summary 文本 `sdk_gphone64_x86_64`，长按目标是其父 LinearLayout）。
> 说明：Display/home/apps 页均无 longClickable=true 节点，换到 About 页才找到目标（按纪律第 6 条记录换目标原因）。

```
[before] field len=26（刚清空）; Chrome 焦点; mInputShown=true
[mid]    field len=320                                      ← 触发前 8 秒 +294，正常
I PHONEAGENT: DO received display=3 vid=null text=sdk_gphone64_x86_64 act=LONG_CLICK
I PHONEAGENT: DO display=3 vid='null' act=LONG_CLICK result=true node=android.widget.LinearLayout
[after]  dumpsys: Display 0 mCurrentFocus=null               ← 焦点被夺
[after]  dumpsys: Display 3 mCurrentFocus=Window{... AtchDlg:com.android.settings/...MyDeviceInfoActivity}  ← 副屏弹出长按菜单
[after]  input_method: mInputShown=true                      ← 键盘未收起
[after]  field len=320                                       ← 触发后零增长，数字中断
```

**副屏生效验证**：display 3 出现 `AtchDlg`（文本选择菜单：Copy 等项），长按确实弹出菜单。
**肉眼观察**：scrcpy 副屏弹出菜单；主屏地址栏字符流停滞。

### A4 · ACTION_FOCUS

**目标**：`com.android.settings:id/switchWidget`（Display 页 Dark theme 开关，focusable=true）

```
[before] field len=640; Chrome 焦点; mInputShown=true
[mid]    field len=960                                      ← 触发前 +320，正常
I PHONEAGENT: DO display=3 vid='com.android.settings:id/switchWidget' act=FOCUS result=true node=android.widget.Switch
[after]  dumpsys: Display 0 mCurrentFocus=null               ← 焦点被夺
[after]  input_method: mInputShown=false                     ← 键盘收起（本轮唯一收起）
[after]  field len=960                                       ← 触发后零增长，数字中断
```

**副屏生效验证**（FOCUS 后的 DUMP）：
```
[android.widget.Switch] 'Dark theme' click=true ... focus=true focused=true a11yFocus=false ...
```
→ view 焦点（focused=true）确实转移到了 Switch 上，动作真实生效。

> 注意：Switch 已被聚焦后再次 FOCUS 会返回 false（22:39:41 验证过一次 result=false），
> 但那次同样把主屏 mCurrentFocus 打成 null —— 与 SCROLL run2 的模式一致：无论 result 真假，焦点都被夺。

### A5 · ACTION_ACCESSIBILITY_FOCUS

**目标尝试了 3 个**：`switchWidget`、`recycler_view`、"SIM" 行 —— **全部 result=false**：

```
I PHONEAGENT: DO display=3 vid='com.android.settings:id/switchWidget' act=ACCESSIBILITY_FOCUS result=false node=android.widget.Switch
I PHONEAGENT: DO display=3 vid='com.android.settings:id/recycler_view' act=ACCESSIBILITY_FOCUS result=false node=androidx.recyclerview.widget.RecyclerView
I PHONEAGENT: DO display=3 vid='null' text=SIM act=ACCESSIBILITY_FOCUS result=false node=android.widget.TextView
```

**完整四判据记录（switchWidget 目标，22:40）**：
```
[before] field len=960; Chrome 焦点; mInputShown=true
[mid]    field len=1290                                     ← 触发前 +330，正常
I PHONEAGENT: DO display=3 vid='com.android.settings:id/switchWidget' act=ACCESSIBILITY_FOCUS result=false node=android.widget.Switch
[after]  dumpsys: Display 0 mCurrentFocus=Window{... Chrome Main}   ← 主屏焦点未变！
[after]  input_method: mInputShown=true                      ← 键盘未收起
[after]  field len=1760                                      ← 触发后继续增长，数字未中断
[after]  a11y: switchWidget a11yFocus=false                  ← 无绿框，动作确实没执行
```

**解读（纪律第 6 条）**：result=false = 动作被框架拒绝、未执行。因此"焦点未变、键盘未收、未丢字"
**不能**作为"ACCESSIBILITY_FOCUS 不抢焦点"的证据 —— 这是无效观察（对应 E4 无效测试 1 的模式：动作根本没跑）。
在 3 个不同目标上均返回 false，说明该环境下（无 TalkBack 的副屏窗口）该动作不可用。

### A6 · ACTION_EXPAND / COLLAPSE

**未测 + 原因**：Settings 应用全部检查过的页面（home、Display、About、Apps、Notifications、
app-level Notifications）节点树中**不存在任何 expandable 节点**（全部 expand=false），
无可用目标。未更换目标 app（纪律第 6 条）。

---

## 3 · 方法说明与已知限制

1. **输入模拟**：以 `input text 1234567890` 循环注入模拟"用户持续打字"。字段长度为客观计数器
   （FIELD 广播直读 a11y 树中最长 EditText），MID−BEFORE 验证触发前流量正常，AFTER−MID 衡量触发后是否中断。
2. **"副屏生效"判定**：a11y 树状态变化 + dumpsys 窗口变化（如 AtchDlg 出现、focused=true 转移、可见行变化）+ scrcpy 肉眼。
3. **键盘判定**：`dumpsys input_method mInputShown` + a11y 窗口列表中 IME 窗口（com.google.android.inputmethod.latin）存在性。
4. **已知环境问题**：
   - `uiautomator dump` 在本实验中被证实在焦点被夺后会 dump 另一块屏的窗口且内容缓存陈旧 —— 弃用，改用自己的 FIELD 广播。
   - 测试期间 Chrome 地址栏达到 ~5000 字符上限后停止增长（A3 前已清理字段）。
   - PowerShell 传参含空格会破坏设备端 am 解析（"Device name" 变成 text=Device、act=null）—— 全部改用无空格锚点。
5. 所有结论标签 `[非root可复现]`：全程 `adb unroot`（uid=2000 shell）。

---

## 4 · 一句话交付

**在 5 个可测动作中，没有任何一个动作类型能避免夺走主屏焦点；连"动作失败"（result=false）都夺。**
ACCESSIBILITY_FOCUS 的"不夺焦点"观察因动作未执行而无效，无法据此翻案。
主线的「a11y 动作不打扰」假设在动作类型维度上仍然不成立。
