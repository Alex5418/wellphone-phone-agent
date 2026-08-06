# B2 · 节点树压缩器 — 压缩前后对比

**日期** 2026-08-06 · **离线任务**（不连设备、不接 LLM）· 交付：`tools/compress_tree.py`

---

## 用法

```bash
python tools/compress_tree.py <dump.xml> [--max-depth 3] [--show-dropped]
python tools/compress_tree.py --self-test     # 内置自测（合成 XML）
```

无第三方依赖（仅标准库 `xml.etree` / `re` / `argparse`）。

## 自测

内置合成 XML 覆盖四个核心规则，`--self-test` 直接断言：

```
[0] Magnification | clickable | android.widget.LinearLayout   ← 文字锚点合并（任务示例）
  [1] Nested row | clickable | android.widget.LinearLayout    ← 双层可点包装去重（只留最外层）
  [2] Search settings | clickable | android.widget.TextView id=...  ← 自带文字
  [3] Search box | editable | android.widget.EditText         ← content-desc 兜底
self-test PASS: merge / wrapper-dedup / zero-bounds / cd-fallback 全部符合预期
```

## 验收指标

| 样本 | 原始节点数 | 压缩后 | 目标 | 说明 |
|---|---|---|---|---|
| `s.xml`（Settings 首页，本次新 dump） | **65** | **10 条** | ≤ 15 | ✅ 达标（E2 历史样本 53 节点同页，本次 dump 为 65） |
| `d0.xml`（Chrome WebView，Amazon 页） | **557** | **37 条** | 记录实际值 | ✅ 不崩。id 运行时随机（`singleVideoCard-<uuid>`）、62%+ 无类型 View |

## s.xml（Settings 首页）压缩后完整输出

```
# tools\s.xml: total=65 kept=10 (dropped: bounds=2 noflags=52 wrapper=1) merged_anchors=8 flattened=0
[0] (no text) | scrollable | android.widget.ScrollView id=com.android.settings:id/settings_homepage_container
  [1] Profile picture, double tap to open Google Account | clickable | android.widget.ImageView id=com.android.settings:id/account_avatar
  [2] Search settings | clickable | android.view.ViewGroup id=com.android.settings:id/search_action_bar
  [3] Network & internet | clickable | android.widget.LinearLayout
  [4] Connected devices | clickable | android.widget.LinearLayout
  [5] Apps | clickable | android.widget.LinearLayout
  [6] Notifications | clickable | android.widget.LinearLayout
  [7] Battery | clickable | android.widget.LinearLayout
  [8] Storage | clickable | android.widget.LinearLayout
  [9] Sound & vibration | clickable | android.widget.LinearLayout

--- reverse lookup: short ID -> real node ---
[0] rid=com.android.settings:id/settings_homepage_container text='' class=android.widget.ScrollView anchor_class=-
[1] rid=com.android.settings:id/account_avatar text='Profile picture, double tap to open Google Account' class=android.widget.ImageView anchor_class=-
[2] rid=com.android.settings:id/search_action_bar text='Search settings' class=android.view.ViewGroup anchor_class=android.widget.TextView
[3] rid=null text='Network & internet' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[4] rid=null text='Connected devices' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[5] rid=null text='Apps' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[6] rid=null text='Notifications' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[7] rid=null text='Battery' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[8] rid=null text='Storage' class=android.widget.LinearLayout anchor_class=android.widget.TextView
[9] rid=null text='Sound & vibration' class=android.widget.LinearLayout anchor_class=android.widget.TextView
```

压缩率：65 → 10（**−85%**）。8 处文字锚点合并（搜索栏 + 7 行条目），52 个纯布局/纯文字节点
被丢弃，1 处嵌套包装去重。每行条目同时给出 anchor 的 class，执行层可
`findAccessibilityNodeInfosByText(anchor) → 向上爬可点祖先` 定位（E3 附带发现 3 的落地）。

## d0.xml（Chrome WebView / Amazon 页）压缩后完整输出

```
# tools\d0.xml: total=557 kept=37 (dropped: bounds=399 noflags=118 wrapper=3) merged_anchors=0 flattened=0
[0] Amazon.com. Spend less. Smile more. | scrollable | android.webkit.WebView
  [1] Open All Categories Menu | clickable | android.widget.Button id=nav-hamburger-menu
  [2] Amazon | clickable | android.view.View id=nav-logo-sprites
  [3] Sign in › | clickable | android.view.View id=nav-logobar-greeting
  [4] your account | clickable | android.view.View id=nav-button-avatar
  [5] Cart | clickable | android.view.View id=nav-button-cart
  [6] (no text) | clickable|editable | android.widget.EditText id=nav-search-keywords
  [7] Clear search keywords | clickable | android.view.View
  [8] Go | clickable | android.widget.Button
  [9] (no text) | scrollable | android.view.View id=nav-disco-bar
    [10] Health AI | clickable | android.view.View
    [11] Haul | clickable | android.view.View
    [12] Medical Care | clickable | android.view.View
    [13] Luxury | clickable | android.view.View
    [14] Amazon Basics | clickable | android.view.View
  [15] Join Prime | clickable | android.widget.Button
  [16] (no text) | clickable | android.view.View id=gwm-Deck
    [17] $2 flash deals just landed | clickable | android.view.View
    [18] Video Player | clickable | android.view.View id=singleVideoCard-35318493-d43f-4a2d-a742-ba6921ca5e60
      [19] (no text) | clickable | android.view.View id=singleVideoCard-35318493-d43f-4a2d-a742-ba6921ca5e60_html5_api
    [20] Shop retro fitness favorites | clickable | android.view.View
    [21] Video Player | clickable | android.view.View id=singleVideoCard-4a667c8c-d233-42f8-8ba3-bf7fb1c3602a
      [22] (no text) | clickable | android.view.View id=singleVideoCard-4a667c8c-d233-42f8-8ba3-bf7fb1c3602a_html5_api
      [23] Pause | clickable | android.widget.Button
    [24] Trending now: lavender hues | clickable | android.view.View
    [25] Video Player | clickable | android.view.View id=singleVideoCard-a2baa99f-fc51-48e3-9f18-785abb354f09
      [26] (no text) | clickable | android.view.View id=singleVideoCard-a2baa99f-fc51-48e3-9f18-785abb354f09_html5_api
      [27] (no text) | clickable | android.widget.TextView
      [28] Play | clickable | android.widget.Button
    [29] (no text) | scrollable | android.view.View
      [30] Click to navigate to product detail page | clickable | android.view.View id=adLink
    [31] Leave feedback on Sponsored ad | clickable | android.widget.Button id=af-label-primary-link-c9f73376d26a483380b97b6681a1404e
[32] Home | clickable|long-clickable | android.widget.ImageButton id=com.android.chrome:id/home_button
[33] (no text) | clickable|long-clickable | android.widget.LinearLayout id=com.android.chrome:id/location_bar_status
[34] amazon.com | clickable|long-clickable|editable | android.widget.EditText id=com.android.chrome:id/url_bar
[35] Switch or close tabs | clickable|long-clickable | android.widget.ImageButton id=com.android.chrome:id/tab_switcher_button
[36] Update available. More options | clickable | android.widget.ImageButton id=com.android.chrome:id/menu_button

--- reverse lookup: short ID -> real node ---
[0] rid=null text='Amazon.com. Spend less. Smile more.' class=android.webkit.WebView anchor_class=-
[1] rid=nav-hamburger-menu text='Open All Categories Menu' class=android.widget.Button anchor_class=-
[2] rid=nav-logo-sprites text='Amazon' class=android.view.View anchor_class=-
[3] rid=nav-logobar-greeting text='Sign in ›' class=android.view.View anchor_class=-
[4] rid=nav-button-avatar text='your account' class=android.view.View anchor_class=-
[5] rid=nav-button-cart text='Cart' class=android.view.View anchor_class=-
[6] rid=nav-search-keywords text='' class=android.widget.EditText anchor_class=-
[7] rid=null text='Clear search keywords' class=android.view.View anchor_class=-
[8] rid=null text='Go' class=android.widget.Button anchor_class=-
[9] rid=nav-disco-bar text='' class=android.view.View anchor_class=-
[10] rid=null text='Health AI' class=android.view.View anchor_class=-
[11] rid=null text='Haul' class=android.view.View anchor_class=-
[12] rid=null text='Medical Care' class=android.view.View anchor_class=-
[13] rid=null text='Luxury' class=android.view.View anchor_class=-
[14] rid=null text='Amazon Basics' class=android.view.View anchor_class=-
[15] rid=null text='Join Prime' class=android.widget.Button anchor_class=-
[16] rid=gwm-Deck text='' class=android.view.View anchor_class=-
[17] rid=null text='$2 flash deals just landed' class=android.view.View anchor_class=-
[18] rid=singleVideoCard-35318493-d43f-4a2d-a742-ba6921ca5e60 text='Video Player' class=android.view.View anchor_class=-
[19] rid=singleVideoCard-35318493-d43f-4a2d-a742-ba6921ca5e60_html5_api text='' class=android.view.View anchor_class=-
[20] rid=null text='Shop retro fitness favorites' class=android.view.View anchor_class=-
[21] rid=singleVideoCard-4a667c8c-d233-42f8-8ba3-bf7fb1c3602a text='Video Player' class=android.view.View anchor_class=-
[22] rid=singleVideoCard-4a667c8c-d233-42f8-8ba3-bf7fb1c3602a_html5_api text='' class=android.view.View anchor_class=-
[23] rid=null text='Pause' class=android.widget.Button anchor_class=-
[24] rid=null text='Trending now: lavender hues' class=android.view.View anchor_class=-
[25] rid=singleVideoCard-a2baa99f-fc51-48e3-9f18-785abb354f09 text='Video Player' class=android.view.View anchor_class=-
[26] rid=singleVideoCard-a2baa99f-fc51-48e3-9f18-785abb354f09_html5_api text='' class=android.view.View anchor_class=-
[27] rid=null text='' class=android.widget.TextView anchor_class=-
[28] rid=null text='Play' class=android.widget.Button anchor_class=-
[29] rid=null text='' class=android.view.View anchor_class=-
[30] rid=adLink text='Click to navigate to product detail page' class=android.view.View anchor_class=-
[31] rid=af-label-primary-link-c9f73376d26a483380b97b6681a1404e text='Leave feedback on Sponsored ad' class=android.widget.Button anchor_class=-
[32] rid=com.android.chrome:id/home_button text='Home' class=android.widget.ImageButton anchor_class=-
[33] rid=com.android.chrome:id/location_bar_status text='' class=android.widget.LinearLayout anchor_class=-
[34] rid=com.android.chrome:id/url_bar text='amazon.com' class=android.widget.EditText anchor_class=-
[35] rid=com.android.chrome:id/tab_switcher_button text='Switch or close tabs' class=android.widget.ImageButton anchor_class=-
[36] rid=com.android.chrome:id/menu_button text='Update available. More options' class=android.widget.ImageButton anchor_class=-
```

压缩率：557 → 37（−93%）。**只测不优化**：id 运行时随机（`singleVideoCard-<uuid>`、
`af-label-...<uuid>` 均本次页面实例化生成，刷新即失效），37 个保留条目里 23 个是
`android.view.View`（62%，与 E2 原始树 376/601 占比一致）——结构可用但定位不可靠，与 E2/R4 结论一致。

---

## 设计决策（与任务的对应）

| 任务要求 | 实现 | 实测 |
|---|---|---|
| 1. 合并文字锚点与可点容器 | 交互节点无自身文字时，在 ≤2 条边内找第一个非交互文字节点做锚点（text 优先，content-desc 兜底）；条目输出锚点文字、容器 class 与 flags | s.xml 8 处；d0.xml 中 `Sign in ›` 等 |
| 2. 保留规则 | clickable / scrollable / long-clickable / EditText / editable | 与任务一致 |
| 3. 丢弃规则 | 纯布局（无 flags 无文字）；bounds 面积 ≤0 或与屏幕（根首子节点 bounds）无交集；同锚点嵌套包装层只留最外层 | s.xml 52+2+1；d0.xml 118+399+3 |
| 4. 短 ID + 反查表 | `[0]`…递增；表：ID → (resource-id, text, class, anchor_class)。定位优先 resource-id，无 id 用 text+class | 见上完整输出 |
| 5. 层级缩进，深度上限 3，超出拍平 | 按「最近已保留祖先」计深，`--max-depth` 可调，超出标 `flattened` | 本批样本均未触发拍平 |

## 已知边界（如实记录）

- **锚点取第一个**：可点容器内有多个文字（title+summary）时只取 DFS 首个（title），summary 不进条目。
- **同锚点去重保留最外层**：执行层若需要最内层可点节点，由 anchor 重新爬树获得（反查表给出 anchor class）。
- **屏幕范围**取根首子节点 bounds（window decor）；WebView 内部超出视口的节点会被丢弃——这是预期行为（不可见即不可点）。
- 本批 `s.xml` 为本次新 dump（Settings 首页，65 节点），非 E2 历史文件（53 节点）；页面同为 Settings 原生首页，结论可对照。
