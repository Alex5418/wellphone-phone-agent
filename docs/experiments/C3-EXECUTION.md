# C3 · locator 执行侧验证

**日期** 2026-08-06 · **标签** `[非root可复现]`（uid=2000 shell）· API 34 · scrcpy VirtualDisplay
**代码**：`AgentAccessibilityService.kt` 新增 `LOCATE` 广播指令（L1–L6 定位 + 动作执行）
**约束**：未改动 DORESTORE 归还逻辑（新增独立指令，与归还无关）

---

## 指令设计

```
am broadcast -a com.example.phoneagent.LOCATE -p com.example.phoneagent \
  --ei display 2 --es strategy L4 --es text 'Screen timeout' --es act CLICK
```

| 参数 | 含义 |
|---|---|
| strategy | L1/L2（viewId）/ L3（content-desc）/ L4/L5（text） |
| text / cd / ordinal | 对应 locator 信号字段 |
| act | CLICK / LONG_CLICK / SET_TEXT / SCROLL_* / FOCUS |

执行流程（与 `compress_tree.py` 的 locator resolve 一一对应）：

1. 按策略取原始命中：L1/L2 `findAccessibilityNodeInfosByViewId`；L3 遍历树匹配
   `contentDescription`（**API 没有 findByContentDescription，需自己走树**）；
   L4/L5 `findAccessibilityNodeInfosByText`。
2. **精确匹配过滤**：L4/L5 按 text ∪ contentDescription 精确等于查询串
   （findByText 是子串匹配且同时匹配两者 —— 本实验实测，见下）。
3. 按 ordinal（L5）/ 锚点文字（L2）选取锚点。
4. **锚点向上爬第一个支持该动作的节点；爬不到用原节点兜底**（B1/E6 教训 4）。
5. 执行动作；SET_TEXT 走 Bundle 参数。

---

## 三策略验证结果（Settings 副屏 display 2，全程 logcat 原始行）

### L4 —— 唯一 text 锚点（'Screen timeout' 行 → 跳转子页）

```
I PHONEAGENT: LOCATE strategy=L4 text='Screen timeout' cd='null' ordinal=0 act=CLICK
              hit=android.widget.TextView target=android.widget.LinearLayout ok=true
```

- `hit=TextView`（锚点）、`target=LinearLayout`（向上爬到的可点行）→ 锚点合并语义落地。
- **副屏生效验证**（坑 2 判据，非仅 ok=true）：随后 dump 显示 display 2 顶部变为
  `collapsing_toolbar 'Screen timeout'`（子页打开），`mCurrentFocus` 为新的 SubSettings。

### L3 —— content-desc 锚点（'Navigate up' 返回键）

```
I PHONEAGENT: LOCATE strategy=L3 text='null' cd='Navigate up' ordinal=0 act=CLICK
              hit=android.widget.ImageButton target=android.widget.ImageButton ok=true
```

- 独立跑了两次（子页返回 + 再次验证），两次均 ok=true。
- **副屏生效验证**：dump 显示页面从 Screen timeout 子页回到 Display 页
  （'Dark theme' 行与 switchWidget 重新可见）。

### L5 —— 重复 text + ordinal（'Dark theme' 第 1 个 = Switch）

```
I PHONEAGENT: LOCATE strategy=L5 text='Dark theme' cd='null' ordinal=1 act=CLICK
              hit=android.widget.Switch target=android.widget.Switch ok=true
```

- **hit=android.widget.Switch** —— ordinal=1 精确选中 Switch（ordinal=0 是 title TextView）。
- **副屏生效验证（独立于 a11y）**：`settings get secure ui_night_mode` **1 → 2**，
  dark mode 真实翻转。

### 关键发现（顺带钉死了 C2 的指标模型）

L5 第一次执行失败：

```
I PHONEAGENT: LOCATE strategy=L5 text='Dark theme' cd='null' ordinal=1 FILTERED EMPTY (raw=2)
```

`raw=2` 证明 **findAccessibilityNodeInfosByText 同时匹配 text 与 contentDescription**
（Switch 的 text 为空、cd='Dark theme' 仍被命中）。压缩器与执行器因此统一改为
「findByText 宇宙 = text ∪ cd」计数（见 C2-RELIABILITY.md 修正记录）。

---

## 完成标准对照

- [x] 新增按 locator 定位的指令（L1/L2/L3/L4/L5 均已实现）
- [x] L3 / L4 / L5 各成功执行一次动作，且均有独立的副屏生效验证
- [x] 未改动 DORESTORE 归还逻辑（git diff 可证：本次仅新增 LOCATE 相关代码）
- [x] 全程 `adb unroot`（uid=2000 shell）

> 注：L1/L2 与既有 CLICKID/DO 指令同一代码路径（viewId 定位），B1 中已大量实测。
