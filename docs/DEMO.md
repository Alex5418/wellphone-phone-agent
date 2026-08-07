# 演示录制手册

目标：一段 1–2 分钟的视频，**同时证明两件事**——

1. 用户在主屏正常使用（打字 / 看视频），全程没有中断
2. Agent 在副屏独立完成了一个真实任务

**只拍到任务完成不构成证据。** 画面里必须同时有用户在动的主屏和在推进的副屏，
否则无法排除"任务是在用户没碰手机的时候跑的"。

---

## 0 · 取景

一个屏幕录制，画面里同时有三样东西：

```
┌──────────────┬──────────────┬────────────────────┐
│  scrcpy 主屏  │  scrcpy 副屏  │  终端               │
│  你在这里打字  │  Agent 在这里 │  [act] 逐步滚动      │
│              │  自己操作     │  disturb_ms 可见     │
└──────────────┴──────────────┴────────────────────┘
```

终端那一栏是关键：它把每步的 `disturb_ms` 和 `restore_ok` 打在屏幕上，
观众能看到打扰窗口的实际数值，而不是只听我们说"很快"。

---

## 1 · 开录前的准备（约 3 分钟）

```bash
# ① 副屏。别关这个窗口 —— 虚拟屏随 scrcpy 进程消亡
scrcpy --new-display

# ② 记下副屏 id（下面用 $SEC 代替）
#    ⚠ 每次 scrcpy 重开都可能变，dumpsys 的输出顺序也不稳定 ——
#    别记上次的数字，也别假设"副屏排在前面/后面"。每次现看
adb shell dumpsys window displays | grep mDisplayId

# ③ 通道。Windows 上 8760 若报 10013，换 18760 并加 PHONEAGENT_PORT
adb forward tcp:8760 localabstract:phoneagent

# ④ 确认无障碍服务是开的（应回显 com.example.phoneagent/...）
adb shell settings get secure enabled_accessibility_services
```

**⑤ 把目标 app 放到副屏。** 环境自检会拦住"副屏上不是目标 app"，不放会直接 abort：

```bash
# Gmail（推荐，见下）
adb shell am start --display $SEC -n com.google.android.gm/.ConversationListActivityGmail

# 或 Settings（备用方案）
adb shell am start --display $SEC -n com.android.settings/.Settings
```

**⑥ 主屏点一下输入框**，让主屏有焦点持有者 —— 否则自检会报 `primary_focus_lost`。

一次性预检（三项都过再开录）：

```bash
adb shell dumpsys window displays | grep -E "mDisplayId=|mCurrentFocus"
```

- 主屏 `display 0` 的 `mCurrentFocus` 不是 `null`
- 副屏 `display $SEC` 上是目标 app
- 服务已开

---

## 2 · 方案 A（推荐）：用户打中文 · Agent 发邮件

真实 Gmail 账号、真实收件箱可验证。E12/E13 已跑通。

### 要输入的命令

```bash
export ANTHROPIC_API_KEY=...        # 或用 DeepSeek，见下

python -m harness.cli --pkg com.google.android.gm \
  run "给 你的邮箱@gmail.com 发一封邮件，主题写「副屏 agent 演示」，正文写「发送这封邮件的整个过程中，用户正在主屏上用中文输入法打字。」" \
  --verbose
```

> ⚠ **`--pkg` 必须放在子命令 `run` 前面。** 它和 `--port` / `--display` 一样属于主解析器，
> 放到 `run` 后面会报 `unrecognized arguments: --pkg`。`--verbose` 属于 `run`，留在后面。
> 默认值是 `com.android.settings`，不改会被自检拦下。

**用弱模型跑（更有说服力，E13 证明了它能独立完成）：**

```bash
PHONEAGENT_LLM_PROVIDER=openai \
PHONEAGENT_MODEL=deepseek-chat \
PHONEAGENT_BASE_URL=https://api.deepseek.com \
DEEPSEEK_API_KEY=... \
python -m harness.cli --pkg com.google.android.gm run "同上那段任务描述" --verbose
```

### 你在镜头前做什么

1. 敲下回车，**立刻**把手放到主屏的输入框上开始打字
2. 用**中文输入法连续拼一个长词组**，比如 `zhonghuarenmingongheguo`，
   让候选条一直挂着 —— 这是最能体现"没被打断"的画面
3. 一直打到 Agent 那边发送完成
4. **软键盘会被收起一次**（唯一已知代价）。**别剪掉这段** ——
   照实拍下来，然后手动点一次恢复继续打。诚实展示限度比假装没有更可信
5. 最后切到 Gmail 收件箱，把那封邮件点开给镜头看

### 预期时长

上次成功用了 **115 秒 / 8 步**，`disturb_ms` 每步 31–458ms。

---

## 3 · 方案 B（备用）：Settings 三步任务

Gmail 的自动补全和网络都可能出岔子。如果连试两次不顺，切这个 —— 快、稳、不依赖网络。

```bash
python -m harness.cli run "在设置中把屏幕超时改成 30 秒" --verbose
```

（`--pkg` 用默认的 `com.android.settings`，不用改。）
主屏这时可以改成**播一个 YouTube 视频**，对应 E14 那条结论：视频全程不暂停。

---

## 4 · 出岔子时

| 现象 | 处理 |
|---|---|
| `环境自检失败: target_app_not_on_secondary` | 目标 app 不在副屏。回到 ①⑤ |
| `环境自检失败: ... primary_focus_lost` | 主屏没焦点。点一下主屏输入框 |
| `UNREACHABLE: cannot reach device` | 通道断了。重跑 `adb forward` |
| `cannot bind to 127.0.0.1:8760 … (10013)` | Windows 端口保留段。换 `adb forward tcp:18760 …` + `PHONEAGENT_PORT=18760` |
| `TransportError NO_DISPLAY` | scrcpy 窗口被关了。虚拟屏没了，重开 |
| 改过 Android 代码后行为不对 | 无障碍服务要**关掉再打开**，否则跑的是旧实例 |
| LLM 读超时 | 已放宽到 150s；再不行 `PHONEAGENT_LLM_TIMEOUT=300` |

**关于 Ctrl-C**：归还在设备侧与动作原子绑定，所以 PC 侧中断时上一步的焦点应该已经还回去了
——**这是设计推论，没有专门测过**。真卡住了手动点一下主屏即可。

---

## 5 · 录完之后

trajectory 已经自己落盘了，可以作为视频的补充证据：

```bash
ls runs/                                    # 最新那个目录
python -c "import json;d=json.load(open('runs/<最新>/meta.json',encoding='utf-8'));print(json.dumps(d['config'],ensure_ascii=False,indent=2))"
```

`config` 里会如实记下**实际**跑的 provider / model / endpoint，
`metrics` 里每步都有 `disturb_ms` / `restore_ok`。
视频负责证明"用户没被打断"，trajectory 负责证明"数值是多少"。
