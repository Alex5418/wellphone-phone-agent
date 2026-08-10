# HARNESS-SPEC.md · 实现规格

> 配套文档：`ARCHITECTURE.md`（设计决策与理由）、`experiments/EXPERIMENTS.md`（实测依据）
> 本文件只讲**怎么实现**。所有"为什么"见 ARCHITECTURE。
>
> 目标读者：实现者（含 coding agent）。**遇到与 ARCHITECTURE 冲突处，以 ARCHITECTURE 为准。**

---

## 0 · 总体约束

| 约束 | 说明 |
|---|---|
| Android 侧只做感知与执行 | 不规划、不管状态、不调 LLM。目标 ≤ 500 行 Kotlin |
| 动作与归还原子绑定 | **必须在 Android 侧同一次调用内完成**，不可跨传输层拆分 |
| display id 动态解析 | 实测每次都变（2/4/5/6），任何硬编码都是 bug |
| 工具返回值不可信 | 每个动作后独立重新观测目标节点，不采信 `performAction` 的返回值 |
| 短 ID 是临时的 | 每次 observe 重新分配，**跨轮次无效** |

---

## 1 · 传输层

### 1.1 现状与目标

当前使用 `am broadcast` 触发 + logcat 读取。**这条链路不适合作为 harness 的传输层**：

- 单向，无请求-响应配对
- 结构化数据要靠解析日志文本
- logcat 缓冲区会截断长内容（完整节点树轻易超限）

**目标形态**：Android 侧起 `LocalServerSocket`，PC 侧通过 `adb forward` 连接，JSON 请求-响应。

### 1.2 建立通道

Android 侧（在 `onServiceConnected` 中启动一个后台线程）：

```kotlin
val server = LocalServerSocket("phoneagent")
while (true) {
    val client = server.accept()
    // 每个连接：读一行 JSON 请求 → 处理 → 写一行 JSON 响应 → 关闭
}
```

PC 侧：

```bash
adb forward tcp:8760 localabstract:phoneagent
```

Python 侧连 `127.0.0.1:8760`，**一次请求一次连接**（短连接，避免状态管理）。

### 1.3 协议

单行 JSON，`\n` 结尾。请求：

```json
{"cmd": "observe", "req_id": "uuid", "args": {...}}
```

响应：

```json
{"req_id": "uuid", "ok": true, "data": {...}}
{"req_id": "uuid", "ok": false, "error": {"code": "...", "msg": "..."}}
```

**超时**：Python 侧统一 10 秒；Android 侧任何单次操作超过 5 秒应主动返回 `TIMEOUT` 而非阻塞。

### 1.4 迁移期的兼容

保留现有 `DUMP` / `CLICK` / `CLICKID` / `DORESTORE` 广播指令，方便手工调试。
**新增 socket 通道，不删旧指令。**

---

## 2 · Android 侧命令契约

### 2.1 `state` — 环境自检

请求：`{"cmd": "state"}`

响应 `data`：

```json
{
  "displays": [
    {"id": 0, "windows": [{"pkg": "com.android.chrome", "focused": true}]},
    {"id": 6, "windows": [{"pkg": "com.android.settings", "focused": true}]}
  ],
  "primary_focus": {
    "display": 0,
    "pkg": "com.android.chrome",
    "node_class": "android.widget.EditText",
    "resource_id": "com.android.chrome:id/url_bar",
    "text_len": 42
  },
  "ime_present": true,
  "ime_pkg": "com.google.android.inputmethod.latin"
}
```

**实现要点**：

- `primary_focus` 用 `root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)`
- ⚠️ **必须排除 IME 窗口**。实测 `findFocus` 会命中软键盘内的按键节点，
  不排除会导致归还打在键盘按键上，进而得出"跨屏焦点不联动"的假结论
- `ime_present` 判据：display 0 的窗口列表中是否存在输入法包名的窗口
- 不要用 `AccessibilityWindowInfo.isFocused()` 判断全局焦点 ——
  它是 per-display 语义，与 `mCurrentFocus` 不同（实测两块屏可同时报 `focused=true`）

### 2.2 `observe` — 读取节点树

请求：`{"cmd": "observe", "args": {"display": 6}}`

响应 `data`：

```json
{
  "display": 6,
  "pkg": "com.android.settings",
  "activity": "com.android.settings.Settings$DisplaySettingsActivity",
  "tree_hash": "a3f2...",
  "nodes": [
    {
      "idx": 0,
      "parent": null,
      "depth": 0,
      "class": "android.widget.FrameLayout",
      "resource_id": "com.android.settings:id/content",
      "text": null,
      "content_desc": null,
      "clickable": false,
      "long_clickable": false,
      "scrollable": false,
      "editable": false,
      "checkable": false,
      "checked": false,
      "focused": false,
      "enabled": true,
      "visible": true,
      "bounds": [0, 0, 1280, 720],
      "actions": ["ACTION_ACCESSIBILITY_FOCUS", "ACTION_CLICK"]
    }
  ]
}
```

**实现要点**：

- 输出**扁平数组 + parent 索引**，不是嵌套 JSON。Python 侧自行重建树，方便做祖先/后代查找
- `tree_hash`：对所有节点的 `(class, resource_id, text, content_desc, clickable, checked)`
  按 idx 顺序拼接后取 SHA1 前 16 位。用于判断树是否更新
- `actions` 直接来自 `node.actionList`。
  ⚠️ **`actionList` 未登记某动作 ≠ 该动作不可用**，Python 侧不得据此丢弃节点
- 深度上限 25，超出则截断并在 `data` 中标 `truncated: true`
- 单次响应超过 512 KB 时，丢弃 `bounds` 与不可交互的纯布局节点后重试一次

### 2.3 `act` — 动作 + 归还（原子）

请求：

```json
{
  "cmd": "act",
  "args": {
    "display": 6,
    "locator": { ...见 §4.3... },
    "action": "CLICK",
    "value": null,
    "restore": true,
    "verify_read": true
  }
}
```

响应 `data`：

```json
{
  "resolved": {
    "found": true,
    "class": "android.widget.Switch",
    "resource_id": "com.android.settings:id/switchWidget",
    "candidates": 1
  },
  "action_ok": true,
  "restore": {
    "attempted": true,
    "ok": true,
    "retried": false,
    "ms": 12,
    "holder_after": "com.android.chrome"
  },
  "post_state": {
    "found": true,
    "text": null,
    "checked": true,
    "class": "android.widget.Switch"
  },
  "window_after": {
    "display": 6,
    "pkg": "com.android.settings",
    "activity": "...DisplaySettingsActivity",
    "window_count": 1
  },
  "timing": {"action_ms": 56, "restore_ms": 12, "total_ms": 68}
}
```

**执行顺序（不可调换）**：

```
1. 解析 locator → 副屏目标节点。失败则直接返回 found=false，不执行任何动作
2. 记录主屏输入焦点节点的【定位信息】—— resource_id / class / pkg，
   不是 AccessibilityNodeInfo 对象
3. t0 = elapsedRealtime()
4. 执行动作
5. t1
6. 若 restore=true：用第 2 步的定位信息【重新解析】主屏节点 → performAction(ACTION_FOCUS)
7. 校验 dumpsys 层面的持有者：读 display 0 的 focused window pkg 填入 holder_after
8. 若 holder_after 不是预期的主屏包名 → 重解析 + 再试一次，retried=true
9. t2
10. verify_read=true 时：重新读取目标节点，填 post_state
11. 填 window_after
```

**第 2 步与第 6 步是关键。** 不能复用动作前的节点对象 ——
实测触发全局配置变更的动作会导致所有 Activity 重建，动作前的快照 `refresh()` 返回 false，
`performAction` 无从分发，归还失效。

**归还原语固定为 `ACTION_FOCUS`**，不要换成 CLICK 或其他动作：它零 UI 副作用、不移动光标。
注意它在已聚焦节点上会返回 `false` —— **这是正常的**，归还是否成功以 `holder_after` 为准，
不以 `performAction` 的返回值为准。

**支持的 action 取值**：
`CLICK` / `LONG_CLICK` / `SET_TEXT` / `SCROLL_FORWARD` / `SCROLL_BACKWARD` / `FOCUS` / `BACK`

- `SET_TEXT` 是唯一需要 `Bundle` 参数的动作
  （`ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE`），其余无参
- `BACK` 走 `performGlobalAction(GLOBAL_ACTION_BACK)`，作用于**当前有焦点的 display**。
  ⚠️ **设备侧保留此命令（手工调试用），但它已被排除出 agent 的动作空间** ——
  归还护栏保证了派发时焦点在主屏，于是它必然退掉用户的页面。见 ARCHITECTURE §5

### 2.4 `probe` — 只读单节点

请求：`{"cmd": "probe", "args": {"display": 6, "locator": {...}}}`

用于验证环节的独立重读，不执行任何动作。响应结构同 `act` 的 `post_state`。

---

## 3 · Python 侧模块划分

```
harness/
  config.py        配置常量
  transport.py     socket 客户端
  models.py        数据类
  tree.py          节点树重建、祖先/后代查找、hash
  compress.py      锚点合并 + locator 生成
  verify.py        判据推断与比对
  observe.py       Observation 文本组装
  planner.py       LLM 调用与输出解析
  loop.py          编排
  cli.py           入口
```

依赖方向严格自下而上，`loop.py` 依赖全部，`models.py` 不依赖任何本地模块。

---

## 4 · 数据结构

### 4.1 `models.py`

```python
@dataclass
class Node:
    idx: int
    parent: int | None
    depth: int
    cls: str
    resource_id: str | None
    text: str | None
    content_desc: str | None
    clickable: bool
    long_clickable: bool
    scrollable: bool
    editable: bool
    checkable: bool
    checked: bool
    focused: bool
    enabled: bool
    visible: bool
    bounds: tuple[int, int, int, int]
    actions: list[str]

@dataclass
class Locator:
    strategy: str            # "L1".."L6"
    resource_id: str | None = None
    text: str | None = None
    content_desc: str | None = None
    cls: str | None = None
    index: int = 0           # L5：同类候选中的第几个
    target: str = "self"     # "self" | "ancestor_clickable" | "descendant_class:<n>"
    path: list[int] | None = None   # L6：从根开始的子节点序号路径

@dataclass
class Item:
    """压缩后的逻辑条目，喂给 LLM 的最小单位"""
    sid: int                 # 短 ID，仅本轮 observation 有效
    label: str               # 显示给 LLM 的文字
    kind: str                # "button"|"switch"|"input"|"list"|"text"|"other"
    state: str | None        # "On"/"Off"/已填文本等
    locator: Locator
    anchor_idx: int          # 文字锚点的节点 idx（调试用）
    target_idx: int          # 实际动作目标的节点 idx（调试用）

@dataclass
class EnvState:
    secondary_display: int | None
    secondary_pkg: str | None
    primary_focus_pkg: str | None
    ime_present: bool
    tree_hash: str
    anomalies: list[str]     # 自检发现的问题

@dataclass
class ActionResult:
    found: bool
    action_ok: bool
    restore_ok: bool | None
    restore_ms: int | None
    restore_retried: bool
    post_state: dict
    window_changed: bool
    timing: dict
    error: str | None = None
```

---

## 4.2 `compress.py` — 锚点合并

### 输入
`list[Node]`（已重建父子关系）

### 算法

```
1. 候选集 = 所有 (clickable or long_clickable or scrollable or editable) 且 visible 且 enabled 的节点
2. 对每个候选 t：
     label = t.text or t.content_desc
     if label 为空:
         在 t 的【后代】中查找第一个有 text 的节点 a（BFS，深度 ≤ 3）
         label = a.text；anchor_idx = a.idx
     else:
         anchor_idx = t.idx
     if label 仍为空: 尝试 t 的 content_desc；再无则标记为无锚点，进 L6
3. 去重：若两个候选共享同一个 anchor（父子嵌套的可点容器），
   保留【最内层的可执行节点】—— 即 depth 最大的那个
4. state 提取：
     checkable → "On"/"Off"（按 checked）
     editable  → 当前 text（空则 "(空)"）
     其他      → 同一父节点下 resource_id 以 ":id/summary" 结尾的兄弟节点的 text
5. kind 推断：
     class 含 Switch/CheckBox/ToggleButton → "switch"
     editable 或 class 含 EditText          → "input"
     scrollable                             → "list"
     clickable                              → "button"
     其余                                   → "other"
```

**第 3 步是必需的**。实测 Preference 列表中整行 LinearLayout 与内层 Switch 都是 clickable，
点整行 = 进入子页面，点 Switch = 原地翻转 —— **必须区分，不能只留一个**。
若两者都保留，label 会重复，靠 `kind` 区分（`button` vs `switch`）。

---

## 4.3 `compress.py` — locator 生成

对每个 Item，按顺序尝试：

| 层 | 条件 | 生成 |
|---|---|---|
| L1 | `target.resource_id` 存在且在全树唯一 | `{strategy:"L1", resource_id, target:"self"}` |
| L2 | resource_id 存在但重复，且 label 在同 id 组内唯一 | `{strategy:"L2", resource_id, text:label, target:...}` |
| L3 | 无 id，`content_desc` 在全树唯一 | `{strategy:"L3", content_desc, target:...}` |
| L4 | `(label, target.cls)` 组合在全树唯一 | `{strategy:"L4", text:label, cls, target:...}` |
| L5 | 组合重复 | `{strategy:"L5", text:label, cls, index:n, target:...}` |
| L6 | 无任何锚点 | `{strategy:"L6", path:[...], target:"self"}` |

**唯一性判断的范围是当前这棵树**，不作全局假设。同一个 id 在列表里出现 20 次是常态。

**`target` 字段怎么填**：

- `anchor_idx == target_idx` → `"self"`
- anchor 是 target 的后代 → `"ancestor_clickable"`（Android 侧：找到 anchor 后向上找第一个可执行祖先）
- anchor 是 target 的祖先 → `"descendant_class:<target.cls>"`

### Android 侧的解析（对应实现）

```
1. 按 strategy 收集候选节点
2. L5 时取第 index 个（按 idx 升序稳定排序）
3. 应用 target：
     "self"                  → 候选本身
     "ancestor_clickable"    → 向上找第一个 clickable/long_clickable/scrollable/editable
     "descendant_class:X"    → BFS 找第一个 class == X 的后代
4. 兜底：若第 3 步爬不到，【用原候选节点】，不要返回失败
5. 返回 candidates 数量，供 Python 侧判断是否发生了歧义
```

第 4 步的兜底来自实测：`actionList` 未登记某动作不代表该动作不可用。

---

## 5 · `verify.py` — 验证

### 判据推断（不要求 LLM 声明预期）

```python
def infer_predicate(item: Item, action: str) -> Predicate
```

| 条件 | 判据 |
|---|---|
| `item.kind == "switch"` 且 action == CLICK | `post.checked != pre.checked` |
| `item.kind == "input"` 且 action == SET_TEXT | `post.text == value` |
| action ∈ {SCROLL_FORWARD, SCROLL_BACKWARD} | `tree_hash` 变化 |
| action == LONG_CLICK | `window_after.window_count` 增加 |
| 其他 CLICK | `window_after.activity` 变化 **或** `tree_hash` 变化 |

### 结果三态

- `PASS` —— 判据满足
- `FAIL` —— 判据明确不满足（动作是哑的）
- `UNKNOWN` —— 无法判断（如 CLICK 后 activity 与 hash 都没变，可能本来就无副作用）

`UNKNOWN` **不视为失败**，但要写进 observation 让 LLM 知道。

### 重要

验证读取必须**独立重新观测**，不能复用 `act` 响应里 Android 自己给的判断。
`post_state` 是数据，判断在 Python 侧做。

---

## 6 · `observe.py` — Observation 组装

### 状态自检（每轮，护栏）

```python
def self_check(state: dict, expected_pkg: str, last_hash: str) -> EnvState
```

检查项与对应 anomaly 字符串：

| 检查 | anomaly |
|---|---|
| 副屏是否存在 | `"secondary_display_missing"` |
| 副屏 pkg 是否为预期 app | `"target_app_not_on_secondary"` |
| tree_hash 与上轮相同 且 上一步动作声称成功 | `"tree_unchanged_after_action"` |
| 主屏无输入焦点持有者 | `"primary_focus_lost"` —— **E7 实测此状态下击键 100% 落入 agent 工作区**，建议升级为动作前的阻断条件（未实施） |

前两项为致命，应中止 loop 并报告；后两项写进 observation 交由 LLM 判断。

### 输出文本

```
## 任务
在设置中关闭深色主题

## 环境状态
- 副屏: display 6 · com.android.settings ✓
- 主屏焦点: com.android.chrome · 已归还 (12 ms)
- 用户输入中: 是
- 上一步: click "Wi-Fi" → 已生效

## 当前界面
[0] 返回 | button
[1] 亮度 | button | 0%
[2] 深色主题 | switch | On
[3] 屏幕保护 | button | On / 时钟

## 已执行
1. click "网络和互联网" → ok，进入 SubSettings
2. scroll down → ok
3. click "Wi-Fi" → ok，⚠ 归还失败（窗口重建）
```

**三条规则**：

1. `restore_ok=true` 时"环境状态"里只留一行摘要；`false` 时必须显式标 ⚠ 并写入"已执行"
2. 历史是**结构化文字摘要**，不含历史节点树
3. observation 报告**偏离**，不报告正常。无异常时"上一步异常"整行省略

### Item 列表的呈现上限

超过 40 条时，按以下顺序裁剪：
`other` → 无 state 的 `text` → 屏幕外（bounds 超出可视区）的条目。
裁剪后在末尾加一行 `（另有 N 项未显示，可滚动查看）`。

---

## 7 · `planner.py`

### 输入
observation 文本 + 任务目标 + 历史摘要

### 输出格式（强约束）

```json
{
  "thought": "深色主题当前是 On，需要点击开关关闭",
  "action": "click",
  "target": 2,
  "value": null,
  "done": false
}
```

`action` 取值：`click` / `long_click` / `set_text` / `scroll_forward` / `scroll_backward` / `wait` / `launch` / `finish`
（**没有 `back`** —— 见 ARCHITECTURE §5，解析层与 loop 两道都拒。
`launch` 只在 `--free-app` 下可用，且**不经过 `act`、没有焦点归还** —— 同见 §5）

### 解析要求

- 剥离 markdown 代码围栏后再 `json.loads`
- `target` 必须是本轮 observation 中存在的 sid，否则视为解析失败
- 解析失败重试一次（把错误信息回灌给 LLM），仍失败则中止

### System prompt 要点

- 说明 target 是短 ID，**不要输出 resource-id 或坐标**
- 说明短 ID 每轮重新分配，不要引用上一轮的编号
- 说明 `wait` 用于用户正在输入时主动让路（策略层，可通过配置关闭）
- 不提及焦点归还机制 —— 那是护栏，不是 LLM 的职责

---

## 8 · `loop.py` — 编排

```python
def run(task: str, max_steps: int = 25) -> RunResult:
    history = []
    last_hash = None
    for step in range(max_steps):
        state  = transport.state()
        env    = self_check(state, expected_pkg, last_hash)
        if env.fatal:
            return abort(env)

        tree   = transport.observe(env.secondary_display)
        items  = compress(tree)
        obs    = build_observation(task, env, items, history)

        plan   = planner.decide(obs)
        if plan.action == "finish" or plan.done:
            return finish(history)
        if plan.action == "wait":
            sleep(WAIT_INTERVAL); continue

        item   = items[plan.target]
        pre    = snapshot(item, tree)
        result = transport.act(env.secondary_display, item.locator,
                               plan.action, plan.value, restore=True)
        post   = transport.probe(env.secondary_display, item.locator)
        verdict = verify(item, plan.action, pre, post, result)

        history.append(Step(plan, result, verdict))
        last_hash = tree.tree_hash
    return exhausted(history)
```

### 关键点

- `probe` 是**独立的一次读取**，不复用 `act` 响应里的 `post_state`
  （`post_state` 仅用于对照，若两者不一致要记进日志）
- `restore=True` 永远硬编码，**不接受配置关闭**（护栏）
- 每步的完整 trajectory 落盘：observation 全文、LLM 原始输出、act 响应、verdict

### 中止条件

| 条件 | 处理 |
|---|---|
| `plan.done == true` | 正常结束 |
| 步数达上限 | 结束并标记 `exhausted` |
| 致命 anomaly | 中止并报告 |
| 连续 3 步 verdict 为 FAIL | 中止（疑似卡死） |
| LLM 输出解析连续 2 次失败 | 中止 |

---

## 9 · `config.py`

```python
ADB_FORWARD_PORT   = 8760
SOCKET_NAME        = "phoneagent"
REQUEST_TIMEOUT_S  = 10
MAX_STEPS          = 25
WAIT_INTERVAL_S    = 1.5
MAX_ITEMS_SHOWN    = 40
TREE_DEPTH_LIMIT   = 25

TARGET_PKG         = "com.android.settings"   # 目标 app
POLITENESS         = "normal"                 # off | normal | patient
                                              # 决定 LLM 是否可用 wait
MODEL              = "..."
```

`POLITENESS` 是策略层配置，**不影响归还行为**。

---

## 10 · 实现顺序建议

分阶段，每阶段可独立验证：

| # | 内容 | 验证方式 |
|---|---|---|
| 1 | socket 通道 + `state` 命令 | Python 打印出正确的 display 列表与主屏焦点 |
| 2 | `observe` + `tree.py` | Python 能重建树，节点数与广播 DUMP 一致 |
| 3 | `compress.py` | 对 Settings 页输出 ≤ 15 条 Item，人工核对 5 条 |
| 4 | `act` + locator 解析 | 手工构造 locator，各层策略各成功一次 |
| 5 | `verify.py` | 故意点一个哑节点，确认返回 FAIL |
| 6 | `observe.py` 文本组装 | 肉眼检查格式 |
| 7 | `planner.py` | 单轮 LLM 调用，输出可解析 |
| 8 | `loop.py` | 端到端跑通 3 步任务 |

**第 4 阶段是风险点**，locator 在 Android 侧的解析要单独测，
不要和 loop 一起调试 —— 失败原因会混在一起。

---

## 11 · 日志与可观测性

每次 run 落一个目录：

```
runs/2026-08-06T14-22-01/
  meta.json          任务、配置、模型、结束原因
  step-01/
    observation.txt  喂给 LLM 的全文
    llm_raw.txt      LLM 原始输出
    act_req.json
    act_resp.json
    probe.json
    verdict.json
  step-02/
  ...
```

**这个目录就是答辩材料。** 一次完整 trajectory 比任何架构图都能说明 loop 在干什么。

关键指标每步记录：`restore_ms`、`total_ms`、LLM 延迟、token 数、verdict。

---

## 12 · 已知坑（实现时会遇到）

**通则：别对系统输出的顺序和编号做任何假设。**
display id 每次都变（2/4/5/6）是这条的一个实例；`dumpsys window displays` 里
每块屏各有一行 `mCurrentFocus`、**而且哪块屏排在前面是不定的**（翻实验日志：
0→2、2→0、0→4、6→0 都出现过）是另一个实例。任何"取第一个"「按顺序第 N 个」
的写法都是 bug —— 要按 id 分段解析，或按 id 查找。

- 无障碍服务改代码后**必须去设置里关掉再打开**，否则跑的是旧实例
- `IntentFilter` 漏 `addAction()` 编译器不报错，运行时静默失效
- `adb forward` 在设备重连后失效，需重新执行
- Git Bash 会转换 `/sdcard/...` 路径 → `export MSYS_NO_PATHCONV=1`
- `AccessibilityNodeInfo` 是快照，窗口变化后 `refresh()` 可能返回 false
- 空 EditText 的 `getText()` 返回 hint 而非空串 —— 判断"是否为空"要看 `isShowingHintText`
- scrcpy 创建的虚拟屏随 scrcpy 进程消亡，需要重连或绑定生命周期
- logcat 缓冲区会截断长内容，**这是必须改用 socket 的直接原因**
- 动作到界面稳定之间有动画，验证读得太早会把成功读成失败（D1：scroll 被判 FAIL，
  下一轮观测里明明已经滚过去了）。做法是**条件复读**而非固定延时：
  先无延时读一次，PASS 就走快路径；没看到预期变化才等 300ms 复读一次 ——
  「复读一次仍未变」比「等固定时长后读一次」是更强的证据，且快动作不付延时税
