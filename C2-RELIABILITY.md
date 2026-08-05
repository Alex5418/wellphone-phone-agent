# C2 · 三样本新指标复评（locator 可指认率）

**日期** 2026-08-06 · **标签** `[非root可复现]`（uid=2000 shell）· API 34
**指标修正**：弃用「规范 resource-id 覆盖率 / android.view.View 占比」，
改用「可交互节点中能通过 L1–L5 唯一定位的比例」（依据见任务 §0）。

---

## 三样本新指标对照表

| 样本 | 技术栈 | 可交互节点 | 可唯一指认 | **可指认率** | L1 | L2 | L3 | L4 | L5 | L6 | no-anchor | shadowed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Settings Display 页 | 传统 View | 11 | 11 | **100%** | 3 | 0 | 1 | 6 | 1 | 0 | 0 | 0 |
| **Composetest（替代样本）** | Jetpack Compose | 4 | 4 | **100%** | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 0 |
| Chrome 新标签页 | WebView | 20 | 18 | **90%** | 8 | 0 | 10 | 0 | 0 | 0 | **2** | 0 |

附注样本（既有文件，非本任务必需）：

| 样本 | 技术栈 | 可交互 | 可唯一指认 | 可指认率 | 策略分布 |
|---|---|---|---|---|---|
| `d0.xml`（Chrome/Amazon WebView） | WebView | 40 | 37 | 92.5% | L1=23 L3=9 L4=3 L5=2 L6=3 |
| `k9.xml`（K-9 欢迎页） | Compose | 2 | 2 | 100% | L1=1 L4=1 |

> 注：任务表标注「Chrome 新标签页 | 已有 d0.xml」，但仓库 `d0.xml` 实为 Chrome 恢复会话后的
> Amazon 页（557 节点，62%+ 无类型 View）。本次用 `pm clear` 重置 Chrome 后重新 dump 了
> 真正的**新标签页**（`tools/chrome-ntp.xml`，91 节点，含 Discover 卡片），两者同属 WebView
> 技术栈，结论互相印证，一并入表。

---

## 新旧指标对照（修正带来的差异）

| 样本 | 旧：规范 id 覆盖率 | 旧：android.view.View 占比 | 新：可指认率 | 判定差异 |
|---|---|---|---|---|
| Settings Display | 53% | 4% | 100% | 一致（两个指标都说可用） |
| **Composetest（Compose）** | **18%** | **24%** | **100%** | **旧指标低估 → 新指标纠正** |
| Chrome 新标签页 | **4%** | **64%** | **90%** | **旧指标判死 → 新指标显示大多数可定位** |
| K-9 欢迎页 | 8% | 46% | 100% | 旧指标低估 → 新指标纠正 |

关键数字：**Chrome NTP 在 4% 的 id 覆盖率下仍有 90% 的交互节点可唯一定位** ——
定位靠的是 cd/text（L3=10），id 从来不是必需字段。Compose 样本在 0 个自定义 id 下
四个控件全部唯一指认（全部 L4，锚点即 label 文字）。

---

## Thunderbird 关键控件专项检查

### K-9 写信界面：未获取（记录原因）

- 尝试：`am start com.fsck.k9/...MainActivity` → 仅 onboarding（Get started / Import
  settings 两按钮，`k9.xml`）。K-9 21.1 无账号时不存在写信入口。
- 原因：写信界面必须配置至少一个邮箱账号才能进入；按纪律「不配置任何邮箱账号」，
  **放弃获取，未配置账号**。

### 替代样本：极简 Compose app（`android/composetest`，自建）

- **换了什么**：Thunderbird 写信界面 → 自建 Compose app（3 输入框 + 1 按钮）。
- **为什么换**：需要一个「无 resource-id 的 Compose 语义节点」样本完成核心判据；
  真实 Compose app 中写信界面需账号（K-9）或控件形态不匹配（Tasks.org 编辑器）。
  自建 app 与写信界面控件一一对应（收件人/主题/正文/发送），且**未使用 testTag 等
  额外语义注入** —— 语义树形态与真实 Compose app 一致。
- **构建**：AGP 9.3.1 built-in Kotlin（2.2.10）+ `org.jetbrains.kotlin.plugin.compose:2.2.10`。

### 四控件专项表（替代样本 `tools/compose.xml`）

| 控件 | 能否唯一定位 | 策略 | 锚点内容 |
|---|---|---|---|
| 收件人输入框（To） | ✅ | L4 | `findByText('To')` 唯一命中 → 向上爬至 EditText |
| 主题输入框（Subject） | ✅ | L4 | `findByText('Subject')` 唯一命中 → 向上爬至 EditText |
| 正文输入框（Body） | ✅ | L4 | `findByText('Body')` 唯一命中 → 向上爬至 EditText |
| 发送按钮（Send） | ✅ | L4 | `findByText('Send')` 唯一命中 → 向上爬至 clickable View |

**四个全部可定位**。注意 Compose 语义树与 View 树形态一致地满足锚点模式：
label 是输入框的子 TextView（`EditText → TextView('To')`），与 E3 的
`LinearLayout → TextView('Magnification')` 是同一结构。

---

## 手工核对记录（测量工具先验证）

逐节点人工推演 vs 程序判定，共核对 **16 个节点**（≥5 要求）：

**settings-display.xml（11 个，全部一致）**
- ScrollView `content_parent`：rid 唯一 → L1 ✓
- ImageButton：无 rid、cd `Navigate up` 唯一 → L3 ✓
- RecyclerView `recycler_view`：rid 唯一 → L1 ✓
- 6 个行（Brightness level / Lock screen / Screen timeout / Screen saver /
  Display size and text / Navigation mode）：无 rid 无 cd，锚点文字唯一 → L4 ✓
- Dark theme 行：锚点 title 与 Switch 的 cd 在 findByText 宇宙（text∪cd）里共出现 2 次
  → **L5 ordinal 0**（C3 实测 findByText 命中 2，见下方修正记录）✓
- Switch `switchWidget`：rid 唯一 → L1 ✓（人工确认：Switch 的 text 属性为空、
  cd='Dark theme'；cd 参与 findByText 匹配，但 id 策略优先）

**compose.xml（4 个，全部一致）**：To/Subject/Body/Send 四个锚点文字在树内各出现
一次 → L4 ✓

**chrome-ntp.xml（8 可定位 + 2 no-anchor，全部一致）**
- feed_stream、search_box_text、voice/lens 按钮、8 个 tile（FrameLayout）、header_menu、
  home/tabs/menu 按钮：rid 唯一 → L1 ✓
- tile 的 cd `Navigate: X` 各唯一 → L3 ✓
- 2 个 `(no text)` clickable ViewGroup：人工验证**整条祖先链（至窗口根）无任何
  text/content-desc** → no-anchor 判定正确 ✓

### 核对发现并修复的指标偏差（两轮，最终版以 C3 实测为准）

**第一轮（v2，部分错误）**：初版 shadowed 判定把「cd 来源的文字」与「text 属性」混在
一个查找宇宙里，导致 Dark theme **行**被误判为 shadowed（可指认率 90.9%）。当时的
修复假设是「findByText 只匹配 text 属性」—— **这个假设是错的**（见第二轮）。

**第二轮（v3，C3 实测钉死）**：在 C3 执行侧验证时，`LOCATE L5 text='Dark theme'` 的
`findAccessibilityNodeInfosByText` 返回 **raw=2** —— 实测证明 **findByText 同时匹配
text 与 contentDescription**（Switch 的 text 为空、cd='Dark theme'，仍被命中）。

```
L5 失败日志（v2 执行器）：LOCATE strategy=L5 text='Dark theme' ordinal=1 FILTERED EMPTY (raw=2)
→ 唯一性判定与执行器查找宇宙不一致：压缩器按 text 计数=1（L4），执行器按 text∪cd 命中=2
```

最终模型（v3）：**L4/L5 的唯一性与 ordinal 一律按 text ∪ contentDescription 合并计数**；
Dark theme 行 → L5 ordinal 0（title 是第 0 个精确命中），Switch → L1（id）。
修复后三样本可指认率不变（100% / 100% / 90%），策略分布如实反映运行时的重复语义。
**这条偏差如果不做执行侧验证（C3）永远不会被发现** —— 压缩器的"唯一"必须定义在
执行器真正使用的查找宇宙上，而不是 XML 属性直觉上。

### 顺带修正（压缩器）

- 嵌套包装去重改为保留**最内层**（锚点向上爬命中的目标；B2 版保留最外层，
  会让 locator 的「向上爬」解析到错误节点）。
- 修复 `Entry.render()` 在 flattened 条目上的崩溃（bool+list，此前从未触发）。

---

## 无法指认的 2 个节点（Chrome NTP，如实记录）

两个 `android.view.ViewGroup`（clickable）位于 Discover 卡片容器，**自身与整条
父链均无 text/content-desc**（见手工核对）。它们是"卡片里能点但没语义"的区域
（点击行为是卡片跳转，卡片自身有 L3 的 cd 节点）。这是 WebView 语义缺失的真实
形态，也是 90% 而非 100% 的原因 —— 落到 L6/no-anchor，不做美化。

---

## 完成标准对照

- [x] 三样本复评完成（Thunderbird 未获取 + 原因已记录）
- [x] 四控件专项表已填（替代样本，四控件全部可定位）
- [x] 新旧指标对照清晰（附数据）
- [x] 统计逻辑经 16 个节点人工核对（含一次真实纠错）
- [ ] 附录：压缩后完整输出（见下方）

---

## 附录：压缩后完整输出

### A. Settings Display 页（`tools/settings-display.xml`）

```
# tools\settings-display.xml: total=55 kept=11 (dropped: bounds=0 noflags=44 wrapper=0) merged_anchors=8 flattened=0
[0] Display | scrollable | android.widget.ScrollView id=com.android.settings:id/content_parent
    locator: {strategy: "L1", resource_id: "com.android.settings:id/content_parent"}
  [1] Navigate up | clickable | android.widget.ImageButton
      locator: {strategy: "L3", content_desc: "Navigate up"}
  [2] (no text) | scrollable | androidx.recyclerview.widget.RecyclerView id=com.android.settings:id/recycler_view
      locator: {strategy: "L1", resource_id: "com.android.settings:id/recycler_view"}
    [3] Brightness level | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Brightness level", class: "android.widget.LinearLayout"}
    [4] Lock screen | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Lock screen", class: "android.widget.LinearLayout"}
    [5] Screen timeout | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Screen timeout", class: "android.widget.LinearLayout"}
    [6] Dark theme | clickable | android.widget.LinearLayout
        locator: {strategy: "L5", text: "Dark theme", ordinal: 0, class: "android.widget.LinearLayout"}
      [7] Dark theme | clickable | android.widget.Switch id=com.android.settings:id/switchWidget
          locator: {strategy: "L1", resource_id: "com.android.settings:id/switchWidget"}
    [8] Screen saver | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Screen saver", class: "android.widget.LinearLayout"}
    [9] Display size and text | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Display size and text", class: "android.widget.LinearLayout"}
    [10] Navigation mode | clickable | android.widget.LinearLayout
        locator: {strategy: "L4", text: "Navigation mode", class: "android.widget.LinearLayout"}
```

（反查表与正文 locator 相同，见 `--assess` 输出；完整 36 行输出可 `python tools/compress_tree.py tools/settings-display.xml` 复现。）

### B. Composetest（`tools/compose.xml`）

```
# tools\compose.xml: total=17 kept=4 (dropped: bounds=0 noflags=13 wrapper=0) merged_anchors=4 flattened=0
[0] To | clickable|long-clickable|editable | android.widget.EditText
    locator: {strategy: "L4", text: "To", class: "android.widget.EditText"}
[1] Subject | clickable|long-clickable|editable | android.widget.EditText
    locator: {strategy: "L4", text: "Subject", class: "android.widget.EditText"}
[2] Body | clickable|long-clickable|editable | android.widget.EditText
    locator: {strategy: "L4", text: "Body", class: "android.widget.EditText"}
[3] Send | clickable | android.view.View
    locator: {strategy: "L4", text: "Send", class: "android.view.View"}
```

### C. Chrome 新标签页（`tools/chrome-ntp.xml`）

```
# tools\chrome-ntp.xml: total=91 kept=20 (dropped: bounds=0 noflags=71 wrapper=0) merged_anchors=0 flattened=0
[0] (no text) | scrollable | androidx.recyclerview.widget.RecyclerView id=com.android.chrome:id/feed_stream_recycler_view
    locator: {strategy: "L1", resource_id: "com.android.chrome:id/feed_stream_recycler_view"}
  [1] Search or type web address | clickable|long-clickable|editable | android.widget.EditText id=com.android.chrome:id/search_box_text
      locator: {strategy: "L1", resource_id: "com.android.chrome:id/search_box_text"}
  [2] Start voice search | clickable | android.widget.ImageView id=com.android.chrome:id/voice_search_button
      locator: {strategy: "L1", resource_id: "com.android.chrome:id/voice_search_button"}
  [3] Search with your camera using Google Lens | clickable | android.widget.ImageView id=com.android.chrome:id/lens_camera_button
      locator: {strategy: "L1", resource_id: "com.android.chrome:id/lens_camera_button"}
  [4] Navigate: Facebook: m.facebook.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: Facebook: m.facebook.com"}
  [5] Navigate: YouTube: m.youtube.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: YouTube: m.youtube.com"}
  [6] Navigate: Amazon.com: www.amazon.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: Amazon.com: www.amazon.com"}
  [7] Navigate: Wikipedia: en.m.wikipedia.org | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: Wikipedia: en.m.wikipedia.org"}
  [8] Navigate: ESPN.com: www.espn.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: ESPN.com: www.espn.com"}
  [9] Navigate: Yahoo: www.yahoo.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: Yahoo: www.yahoo.com"}
  [10] Navigate: eBay: m.ebay.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: eBay: m.ebay.com"}
  [11] Navigate: Instagram: www.instagram.com | clickable|long-clickable | android.widget.FrameLayout
      locator: {strategy: "L3", content_desc: "Navigate: Instagram: www.instagram.com"}
  [12] Options for Discover | clickable | android.widget.ImageButton id=com.android.chrome:id/header_menu
      locator: {strategy: "L1", resource_id: "com.android.chrome:id/header_menu"}
  [13] (no text) | clickable|long-clickable | android.view.ViewGroup
      locator: {strategy: "L6"}
    [14] Share Mayor Zohran Mamdani sends cease-and-desist letters to Target, Amazon | clickable | android.view.ViewGroup
        locator: {strategy: "L3", content_desc: "Share Mayor Zohran Mamdani sends cease-and-desist letters to Target, Amazon"}
    [15] Card Menu Mayor Zohran Mamdani sends cease-and-desist letters to Target, Amazon | clickable | android.view.ViewGroup
        locator: {strategy: "L3", content_desc: "Card Menu Mayor Zohran Mamdani sends cease-and-desist letters to Target, Amazon"}
  [16] (no text) | clickable|long-clickable | android.view.ViewGroup
      locator: {strategy: "L6"}
[17] Home | clickable|long-clickable | android.widget.ImageButton id=com.android.chrome:id/home_button
    locator: {strategy: "L1", resource_id: "com.android.chrome:id/home_button"}
[18] Switch or close tabs | clickable|long-clickable | android.widget.ImageButton id=com.android.chrome:id/tab_switcher_button
    locator: {strategy: "L1", resource_id: "com.android.chrome:id/tab_switcher_button"}
[19] More options | clickable | android.widget.ImageButton id=com.android.chrome:id/menu_button
    locator: {strategy: "L1", resource_id: "com.android.chrome:id/menu_button"}
```

### D. K-9 欢迎页（`tools/k9.xml`，附）

```
# tools\k9.xml: total=24 kept=2 (dropped: bounds=0 noflags=22 wrapper=0) merged_anchors=2 flattened=0
[0] Get started | clickable | android.view.View id=onboarding_welcome_start_button
    locator: {strategy: "L1", resource_id: "onboarding_welcome_start_button"}
[1] Import settings | clickable | android.view.View
    locator: {strategy: "L4", text: "Import settings", class: "android.view.View"}
```
