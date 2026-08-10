# SUBTASK-F1 · 让 agent 自己启动副屏上的 app

**分支** `feat/agent-launches-app`（已建好，你就在上面，**不要再建分支**）
**性质** 实现任务。设计已定，**你按规格实现，不要重新设计、不要提改进建议。**
**纪律** 失败原样记录，不要自行"修好"再报成功。跑不通就写下卡在哪。
**不需要设备。** 全程离线，靠单元测试验收。设备验证由我事后做。
**预计** 1–1.5 小时。

---

## 0 · 开工前必读

**必读，都在本仓库内：**

- `docs/ARCHITECTURE.md` §2（护栏与策略分层）、§5（动作空间与 ⛔ 排除）
- `harness/policy.py` 全文 —— 特别是 `record_disturbance` 的注释
- `harness/loop.py` 的 `run()`，看清 `wait` / `back` / `blocked` 三条 `continue` 分支怎么写的
- `harness/observe.py` 的 `self_check` 与 `build_observation`

### 这个项目的两条铁律（违反了整个改动作废）

1. **护栏写死在代码里，不接受配置关闭。** `loop.py` 里 `restore=True` 是硬编码。
2. **三值，不许折叠成布尔。** `ime_present` 是 `True / False / None`，
   **`None` 是「读不到」，绝不能当成 `False`（用户没在输入）**。

---

## 1 · 要做什么

现在必须由人先把 app 放到副屏（`adb shell am start --display N ...`），
否则 `self_check` 报 `target_app_not_on_secondary`，**致命异常，直接中止**。

目标：**让 agent 自己启动 app**，从而能处理跨 app 任务。

### ⚠ 这条路径不受护栏保护（本任务的核心约束）

启动走 **PC 侧 `adb`**，不经过 `act`，**因此没有焦点归还**。这不是疏忽，是有意的
时间取舍，但**必须在两处显式暴露出来**，见 §4。

实测证据（就在刚才，一条命令复现）：

```
启动前  display 0: mCurrentFocus=Window{... com.android.chrome ...}
启动后  display 0: mCurrentFocus=null            ← 主屏焦点被夺走，无人归还
        display 4: mCurrentFocus=Window{... com.google.android.calendar ...}
```

主屏 `mCurrentFocus=null` 正是 E7 测出「120/120 击键全部落进 agent 工作区
（无还可归）」的那个状态。**所以 §3 的护栏不能省。**

---

## 2 · 已经替你验过的命令（原样用，不要自己换写法）

三条都在本机 API 34 模拟器上实跑过：

```bash
# ① 列出可启动应用 —— 本机得到 20 个去重包名
adb shell cmd package query-activities -a android.intent.action.MAIN \
    -c android.intent.category.LAUNCHER
#   输出里抓 `packageName=xxx`，去重后排序

# ② 包名 → 可启动组件（最后一行就是 pkg/activity）
adb shell cmd package resolve-activity --brief com.google.android.calendar
#   → com.google.android.calendar/com.android.calendar.AllInOneActivity

# ③ 在指定 display 上启动
adb shell am start --display 4 -n com.google.android.calendar/com.android.calendar.AllInOneActivity
#   → Starting: Intent { cmp=... }
```

⚠ **`resolve-activity` 的输出最后一行才是组件**，前面还有 `priority=0 …` 那种行，
不要取第一行。

⚠ **拿不到人类可读的应用名**（"Gmail"），shell 层只有包名。那要设备侧
`PackageManager.getApplicationLabel`，**本任务不做**。LLM 看到的就是包名。
这是本方案已知的代价，记进文档即可，不要试图补。

---

## 3 · 实现规格（照做，逐条）

### 3.1 `harness/adbutil.py` —— 加两个函数

```python
def launchable_apps() -> list[str]:
    """可启动应用的包名，去重升序。读不到返回 []（不是 None，调用方按空列表处理）。"""

def resolve_launch_component(pkg: str) -> str | None:
    """包名 → 'pkg/activity'。解析不到返回 None。"""

def launch_app(pkg: str, display: int) -> bool:
    """在 display 上启动 pkg。成功返回 True。

    ⚠ 走 adb，**不经过 act，没有焦点归还**。调用方必须把这一点上报给用户。
    """
```

沿用本文件既有风格：**任何一个函数拿不到结果都返回 None / []**，不许抛异常、
不许猜。`_sh()` 已经在文件里了，直接用。

### 3.2 `harness/models.py` —— `Item` 加一个字段

```python
kind: str   # 增加一个取值 "app"
```
不用改类定义，`kind` 本来就是 str。**但 `render()` 要能正确显示 app 条目**
（见 §3.4 的格式）。

### 3.3 `harness/cli.py` —— 加 `--free-app`

```python
r.add_argument("--free-app", action="store_true",
               help="不锁定目标包：启用 launch 动作，且副屏上不是目标 app 不再致命")
```
传给 `Loop(..., free_app=args.free_app)`。

**默认 False。默认路径的行为必须与今天逐字节一致** —— 这是本任务最重要的约束，
现有演示命令不能受任何影响。

### 3.4 `harness/observe.py` —— 两处

**(a) `self_check` 增加参数 `free_app: bool = False`。**
`free_app=True` 时，`target_app_not_on_secondary` **不进 `FATAL_ANOMALIES` 判定**
（仍然可以出现在 `anomalies` 里，只是不致命）。
`free_app=False` 时行为**完全不变**。

**(b) `build_observation` 增加参数 `apps: list[str] | None = None`。**
非空时，在「## 当前界面」之后加一节：

```
## 可启动的应用（副屏当前：com.google.android.gm）
[12] com.android.settings
[13] com.google.android.calendar
...
（用 launch 打开其中一个。⚠ 该动作不经过焦点归还护栏）
```

**sid 与界面条目共用同一个编号空间**，从界面条目的最大 sid + 1 开始往后排。
这样 `target` 仍然是整数，解析层一行都不用改。

### 3.5 `harness/planner.py`

- `ACTIONS` 增加 `"launch"`
- `SYSTEM_PROMPT` 增加说明：`launch` 用于打开「可启动的应用」那一节里的条目；
  **它不经过焦点归还，用户正在输入时会被拒绝**；不要用它打开当前已经在副屏上的 app
- `parse_plan`：`launch` **必须带整数 `target`**（与 click 同规则）

### 3.6 `harness/policy.py` —— 护栏

```python
def launch_block_reason(ime_present: bool | None) -> str | None:
    """用户可能正在输入时，拒绝 launch。

    依据：E19 —— 启动 app 是最彻底的一次 Activity 重建（重建组 13/30 抢走主屏键盘），
    而本动作又恰好没有焦点归还兜底。两者叠加 = 主动触发已知缺陷。
    三值：True 拒；None（读不到）**也拒**，保守处理；False 放行。
    """
```
返回非 None 时 loop 必须拒发，并把理由写进历史。

### 3.7 `harness/loop.py` —— 编排

- `Loop.__init__` 增加 `free_app: bool = False`
- 每轮：`free_app` 为真时取 `apps = adbutil.launchable_apps()`，传给 `self_check` 与
  `build_observation`；为假时 `apps=None`，**不调用 adb**
- `plan.action == "launch"` 分支，**照着现有 `blocked` 分支的写法**：
  1. `free_app` 为假 → 拒绝，note 写明「未启用 --free-app」，`continue`
  2. `launch_block_reason(env.ime_present)` 非 None → 拒绝并 `_emit("blocked", …)`，
     计入 `consecutive_stall`，`continue`
  3. target 不是 app 条目 → 拒绝，note 写明有效范围，`continue`
  4. 通过 → `adbutil.launch_app(pkg, secondary)`；成功与否都记进历史，
     note **必须包含** `⚠ 该动作未经护栏：无焦点归还、无 disturb_ms`
  5. `trace` 落一个 `launch.json`：
     `{"pkg":…, "display":…, "ok":…, "restore": null, "guarded": false,
       "note": "PC 侧 adb 启动，不经过 act 的原子归还"}`
  6. `last_claimed_ok = False`；**不产生 metrics 行**（没有 disturb_ms 可记）

---

## 4 · 这个洞必须暴露在两个地方

1. **observation 的「已执行」**：`launch com.google.android.calendar →
   ⚠ 该动作未经护栏：无焦点归还、无 disturb_ms`
2. **trajectory**：`launch.json` 里 `guarded: false`、`restore: null`

**不许把它写成一次普通动作。** 这个仓库反复强调「仪表看不见的伤害等于没测」——
这一步的代价必须在 trajectory 里看得见。

---

## 5 · 测试（**每条都要写，跑通**）

加在 `tests/test_policy.py` 与 `tests/test_loop.py`，沿用现有写法
（`FakeTransport` / `Script` / `sid_of`）。

| # | 断言 | 放哪 |
|---|---|---|
| 1 | `free_app=False`（默认）时，`self_check` 对 `target_app_not_on_secondary` **仍然致命** | test_loop |
| 2 | `free_app=True` 时，同样的状态**不致命**，loop 继续 | test_loop |
| 3 | `free_app=False` 时 LLM 输出 `launch` 被拒，**`adbutil.launch_app` 一次都没被调用** | test_loop |
| 4 | `free_app=True` 且 `ime_present=True` 时 `launch` 被拒，**一次都没被调用** | test_loop |
| 5 | `ime_present=None` 时同样被拒（读不到按保守处理） | test_policy |
| 6 | `ime_present=False` 时 `launch_block_reason` 返回 None | test_policy |
| 7 | `build_observation` 给了 apps 时，app 条目的 sid **接在界面条目最大 sid 之后**，不重号 | test_loop |
| 8 | 成功 launch 后，历史条目里**含 `未经护栏` 字样** | test_loop |

**3 和 4 的断言方式**：monkeypatch `harness.loop.adbutil.launch_app` 成一个计数器，
断言计数为 0。**不要真的去调 adb** —— 测试不许碰设备。

---

## 6 · 验收命令（输出要贴进报告）

```bash
python -m unittest discover -s tests -q      # 现在是 88 条，你加完应该是 96 条左右
python -m harness.cli --help                 # 能看到 run 子命令
python -m harness.cli run --help             # 能看到 --free-app
```

**88 条现有测试一条都不许挂。** 挂了说明你改坏了默认路径 —— 那是本任务的红线。

---

## 7 · ❌ 不要做

- ❌ 不要改 `restore=True`、不要改 `DISTURB_BUDGET_MS`、不要改任何现有阈值
- ❌ 不要动设备侧 Kotlin（`android/` 整个目录不碰）
- ❌ 不要为了拿人类可读的应用名去加设备侧命令 —— 明确不在范围内
- ❌ 不要让 `--free-app` 默认为真
- ❌ 不要在测试里调用真实 `adb`
- ❌ 不要重新设计接口、不要提改进建议、不要顺手重构别的地方
- ❌ 不要 push；不要动 `main`

必须偏离本规格才能推进时：**照做，但在报告里单独写明偏离了什么、为什么。**

---

## 8 · 交付物

1. 代码改动，提交在 `feat/agent-launches-app` 上
2. `docs/briefs/F1-RESULTS.md`：
   - §5 那张表逐条打勾 + 每条对应的测试函数名
   - §6 三条命令的**实际输出**
   - 「偏离说明」（没有就写"无"）
   - 「限度」：你没做到的、不确定的
3. **git（显式步骤，不要只放在完成标准里）**：
   ```bash
   git add -A && git commit -m "F1: ..."
   ```
   分批提交更好（adbutil / observe / loop / tests 各一次）。**不要 push。**

---

## 9 · 卡住了怎么办

**失败也是产出。** 写下：你想做什么、执行了什么命令、实际输出是什么、你的判断。
不要藏，不要自己"修好"再报成功。

单点卡超过 20 分钟 → 记录现象，跳过该点继续做别的，最后在「限度」里列出来。

---

## 10 · 完成标准（自查）

- [ ] §3 七个小节都实现了
- [ ] §5 八条测试都写了且通过
- [ ] 现有 88 条一条没挂
- [ ] `--free-app` 默认关，关闭时行为与改动前一致
- [ ] `launch` 被拒的三种情形都不会真的调用 adb
- [ ] observation 与 `launch.json` 两处都暴露了「未经护栏」
- [ ] §6 命令的实际输出贴进了 `F1-RESULTS.md`
- [ ] 全部提交在 `feat/agent-launches-app`，没有 push
