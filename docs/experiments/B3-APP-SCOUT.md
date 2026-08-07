# B3 · 候选 app 的节点树体检

**日期** 2026-08-06 · **只做客观数据采集，不做选型建议**（选型由项目负责人判断）
**方法**：`uiautomator dump`（display 0 默认屏）→ `tools/scout_dump.py` 统计
**标签**：`[非root可复现]`（uid=2000 shell）· API 34 · google_apis 镜像

---

## 对照表

| App | 采集界面 | 总节点数 | `android.view.View` 占比 | 规范 resource-id | clickable=true | EditText | WebView / Flutter / RN / Compose |
|---|---|---|---|---|---|---|---|
| **AOSP Clock**（deskclock） | 新建闹钟页（Material 时间选择器） | 32 | 16%（5/32） | 16 | 19 | 0 | 无 |
| **AOSP Contacts** | 联系人主列表页 | 55 | 2%（1/55） | 40 | 9 | 1 | 无 |
| **AOSP Calendar** | 首次启动 onboarding → **登录墙**（月视图未达） | 20（onboarding）/ 40（登录页） | 40%（登录页 16/40） | 7（登录页） | 6（登录页） | 1（登录页） | **WebView ×2**（Google 账号登录页） |
| **Fossify Notes 1.7.0**（F-Droid APK 9.1MB） | 主界面即笔记编辑页 | 18 | 0% | 13 | 4 | 1 | 无（含混淆类名 `D2.o`） |
| **Thunderbird (K-9 Mail) 21.1**（GitHub APK 10.2MB） | 欢迎页（未配账号，写信界面不可达） | 24 | 46%（11/24） | **2** | 2 | 0 | **ComposeView**（Jetpack Compose 实现） |

补充对照（既有数据，非本次采集）：Chrome 信息流 601 节点 / View 占比 62%（E2）；
Settings 首页 65 节点 / View 占比 2%（B2 样本）。

---

## 各 app 明细

### AOSP Clock — 新建闹钟页（`tools/clock-alarm.xml`）

class 分布 top10：

```
14 android.widget.TextView      5 android.view.View      3 android.widget.LinearLayout
 3 android.view.ViewGroup       3 android.widget.Button  2 android.widget.FrameLayout
 2 android.widget.CompoundButton
```

resource-id 样例 5 条：

```
android:id/content
com.google.android.deskclock:id/header_title
com.google.android.deskclock:id/material_timepicker_view
com.google.android.deskclock:id/material_clock_display_and_toggle
com.google.android.deskclock:id/material_clock_display
```

备注：时间为 Material 选择器（非文本输入），EditText=0；19 个 clickable 全部带规范 id。
主屏（表盘，`tools/clock1.xml`）50 节点、View 占比 2%、规范 id 41。

### AOSP Contacts — 主列表页（`tools/contacts.xml`）

class 分布 top10：

```
18 android.widget.FrameLayout   9 android.view.ViewGroup  6 android.widget.LinearLayout
 5 android.widget.TextView      5 android.widget.ImageView  3 android.widget.Button
 2 android.widget.ImageButton   1 androidx.drawerlayout.widget.DrawerLayout
 1 androidx.slidingpanelayout.widget.SlidingPaneLayout    1 android.widget.EditText
```

resource-id 样例 5 条：

```
com.google.android.contacts:id/action_bar_root
android:id/content
com.google.android.contacts:id/drawer_layout
com.google.android.contacts:id/root
com.google.android.contacts:id/contacts_list_container
```

备注：首次启动弹通知权限窗，已用 `pm grant` 处理（环境设置，非 UI 动作）。
DrawerLayout + SlidingPaneLayout 双布局（手机/平板自适应），1 个搜索 EditText。

### AOSP Calendar — onboarding → 登录墙（`tools/calendar.xml` / `tools/cal5.xml`）

采集路径（如实记录）：

```
Calendar 首次启动 → 'Make the most of every day.'（20 节点，1 clickable）
  → 'Schedule View puts images and maps on your calendar.' + 'Got it'
  → 'Checking info…' → 'Sign in - Google Accounts'（com.google.android.gms WebView 登录页）
```

登录页 class 分布 top10（40 节点）：

```
16 android.view.View   8 android.widget.TextView   7 android.widget.FrameLayout
 4 android.widget.Button   2 android.widget.LinearLayout   2 android.webkit.WebView
 1 android.widget.EditText
```

resource-id 样例 5 条（登录页）：`android:id/content`、`com.google.android.gms:id/container`、
`com.google.android.gms:id/minute_maid`、`com.google.android.gms:id/suc_layout_status`、
`com.google.android.gms:id/sud_layout_template_content`

备注：**月视图未达** —— 继续会进入账号登录，按纪律「不配置任何账号」停止。
登录页是 gms 内嵌 WebView（2 个 WebView 节点、40% 无类型 View），与 E2 的 Chrome 结论同型。

### Fossify Notes 1.7.0 — 主界面即编辑页（`tools/notes.xml`）

class 分布 top10（18 节点）：

```
4 android.widget.FrameLayout   3 android.widget.LinearLayout  2 android.widget.ScrollView
2 android.widget.Button        2 android.widget.RelativeLayout
1 android.view.ViewGroup       1 androidx.appcompat.widget.LinearLayoutCompat
1 android.widget.ImageView     1 D2.o       1 android.widget.EditText
```

resource-id 样例 5 条：

```
org.fossify.notes:id/action_bar_root
android:id/content
org.fossify.notes:id/main_coordinator
org.fossify.notes:id/main_appbar
org.fossify.notes:id/main_toolbar
```

备注：主界面直接是笔记编辑页（`text_note_view` EditText，hint 'Insert text here'），
极干净：0 个无类型 View、全部节点可归因。`D2.o` 为 R8 混淆后的自定义类名
（出现在 class 分布中，不影响 id/text 定位）。

### Thunderbird (K-9 Mail) 21.1 — 欢迎页（`tools/k9.xml`）

class 分布 top10（24 节点）：

```
11 android.view.View   5 android.widget.TextView   4 android.widget.FrameLayout
 2 android.widget.Button   1 android.widget.LinearLayout
 1 androidx.compose.ui.platform.ComposeView
```

resource-id 样例 5 条（实际仅 2 个规范 id）：

```
com.fsck.k9:id/action_bar_root
android:id/content
```

备注：**写信界面未达** —— K-9 需要至少一个账号才能进入写信界面，配账号被纪律禁止。
欢迎页已显示显著的 Compose 特征：46% 无类型 `android.view.View`（Compose 内部语义节点）、
resource-id 仅 2 个、可点节点少。与 E2 的 WebView 结论不同源但同型：**自绘/声明式 UI 的
节点树同样不具备 id 语义**（此处为 Compose 而非 WebView，属同一类问题的另一实现）。

---

## 采集环境说明（如实记录）

- 三个系统 app 均来自 google_apis 镜像自带（deskclock 为 Google 版 DeskClock，与 AOSP 同源）。
- Fossify Notes 与 Thunderbird 均为 `adb install` sideload（F-Droid / GitHub releases，未配任何账号）。
- Calendar 的 onboarding 与登录墙、Thunderbird 的欢迎页均为可达界面的原始 dump；
  「未达界面」的条目已注明原因，未尝试绕过。
- 本表只回答「各 app 主界面的节点树长什么样」，不构成任务选型结论。
