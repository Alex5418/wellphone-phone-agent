# D1 · harness 首次真机端到端运行

**日期** 2026-08-05 · **标签** `[非root可复现]`（uid=2000 shell）· API 34 · scrcpy 4.1 VirtualDisplay
**环境** 副屏 display 2 · com.android.settings（Display 设置页）· 主屏 display 0 · com.android.chrome
**策略层** 规则脚本（无 API key，`--provider rule`）—— 护栏与观测链路是完整的真实路径
**trajectory** `trajectories/D1-3step-dark-theme/`、`trajectories/D1-restore-timing-breakdown/`

任务：`在设置里关闭深色主题`，三步（scroll → click switch → finish），两步判据均为 PASS。

---

## 1 · 头条结果：打扰窗口不是一个数，是两个数

把「归还耗时」从「校验开销」里拆出来之后（此前二者混在同一个 `restore_ms` 里）：

| 步骤 | 动作 | 打扰窗口 `focus_ms` | 备注 |
|---|---|---|---|
| 1 | `scroll_forward` | **12 ms** | 与 E6 的 10–15 ms 一致 |
| 2 | `click` Dark theme 开关 | **2526 ms** | 触发全局配置变更 → 所有 Activity 重建 |

**相差 200 倍。** 用同一个"平均归还耗时"描述这套 harness 是没有意义的。

### 2.5 秒花在哪

补了子时间戳后重跑单步（`trajectories/D1-restore-timing-breakdown/`）：

| 分项 | 耗时 |
|---|---|
| `reResolvePrimary`（重新找到主屏焦点节点） | **2962 ms** |
| `performAction(ACTION_FOCUS)`（真正的归还动作） | 225 ms |
| 校验持有者 `verify_ms` | 116 ms |

**瓶颈不在归还原语，在重解析。** 主题切换期间 Chrome 自己也在重建，
对它的窗口发 `findAccessibilityNodeInfosByViewId` 是跨进程查询，会一直阻塞到对端能应答。

这与 B1 的结论一致但更精确：B1 说这类动作「归还快照失效、归还失效」；
改成动作后**重新解析**之后归还其实**会成功**，代价是打扰窗口从 12 ms 涨到 ~3 s。
所以 ARCHITECTURE §5 的「已知边界」应改写为：

> 触发全局配置变更（主题 / 语言 / 字体 / 旋转）的动作 —— 归还成功，但打扰窗口 ~3 s，
> 期间用户击键仍会落到错误位置。不是"归还失败"，是"归还很慢"。

未验证：这 3 s 是否可优化。可能的方向是给重解析设一个截止时间并先发一次
盲 `ACTION_FOCUS`，但那会牺牲"归还目标必须重新解析"的正确性前提，需要单独实验。

---

## 2 · 仪表自己会撒谎（第 4 种形态）

设备侧一度把这一步报成 `restore.ok = false`。实际没失败 —— `focusedPkgOnPrimary()`
返回 null，因为 **display 0 上没有任何窗口自报 `isFocused` / `isActive`**，
a11y 侧根本读不到持有者，而当时的代码把"读不到"直接当成了"不相等"。

同一时刻 `dumpsys window displays` 明确显示主屏焦点仍在 Chrome。

修正后：读不到 → 报 `ok = null`（UNKNOWN），由 PC 侧 dumpsys 定论。
**没有证据说明失败时，不许报失败。**

顺带一个真会咬人的解析坑：`dumpsys window displays` 里**每块屏各有一行 `mCurrentFocus`，
且副屏排在前面**：

```
Display: mDisplayId=2 (organized)
  mCurrentFocus=Window{... com.android.settings/...SubSettings}
Display: mDisplayId=0 (organized)
  mCurrentFocus=Window{... com.android.chrome/...Main}
```

"取第一个 mCurrentFocus" 会拿到**副屏**的持有者，从而报出"主屏焦点被夺走"的假警报。
必须按 display 分段解析。

---

## 3 · 读得太早 = 把成功读成失败

首轮 `scroll_forward` 判成 FAIL（`tree_hash` 未变化），但下一轮观测里列表明明已经滚过去了。
原因是验证读取紧跟在动作之后，读到的是动画中间帧。

加了 400 ms 稳定延时后同一步判 PASS。判据一个字没改 —— 只是把读取放到了正确的时刻。

同源现象：`act` 自报的 `post_state` 与独立 `probe` 在主题切换那一步不一致
（`found: act=False probe=True`）。act 的内部重读发生在 Activity 重建当中，
locator 一时解析不到；400 ms 后的独立 probe 解析得到。
**这正是交叉校验要抓的东西，保留不修** —— 权威结论以独立 probe 为准。

---

## 4 · 观测质量：真实节点树上暴露的两处

- **滚动容器会认领后代文字**。RecyclerView 把第一个分组标题认成自己的名字，
  条目显示为 `[2] Brightness | list` —— 读起来像个亮度控件。
- **一页上有两个可滚动区域**（外层 ScrollView + 内层 RecyclerView）。
  统一叫「（可滚动区域）」时两条同名，规则脚本选中了外层那个 —— 它滚不动，于是 FAIL。

现改为 `（可滚动区域：Brightness…）`：前缀点明它是区域，后缀用于区分。修正后首选即命中。

---

## 5 · 顺带确认的几件事

- `observe` 46 节点 → 6–10 条 Item；**Python 侧复算的 tree_hash 与设备侧一致**
  （`mismatch=False`），两侧的哈希规则在真实数据上对得上
- locator 在真实 Settings 上的分布：L1（唯一 id）、L3（`Navigate up` 的 contentDescription）、
  L4 + `ancestor_clickable`（Preference 行，文字在子 TextView）均一次命中
- 「整行 button + 行内 switch」在真机上确实是两条：
  `[5] Dark theme | button` 与 `[6] Dark theme | switch | On` —— 点前者进子页面，点后者原地翻转
- `activity` 字段在服务刚连上时为 null（只能从 `TYPE_WINDOW_STATE_CHANGED` 事件累积），
  首次导航之后才有值。判据会退回 `tree_hash` 比对，不影响正确性

---

## 6 · 仍未验证

- `observe` 的 512 KB 降级路径（本页仅 46 节点，远未触发）
- `BACK` 的跨屏语义
- 打扰窗口 ~3 s 期间**真实用户击键**的落点（本次运行主屏无 IME，没有实测丢字）
- 真机（非模拟器）
