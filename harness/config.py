"""配置常量（HARNESS-SPEC §9）。

除 MODEL / API key 外一律写死在这里：能被配置关掉的护栏不是护栏。
特别地 —— **restore 没有开关**，见 loop.py。
"""

import os

# ---- 传输 ----
ADB_FORWARD_PORT = int(os.environ.get("PHONEAGENT_PORT", "8760"))
SOCKET_NAME = "phoneagent"
REQUEST_TIMEOUT_S = 10.0
CONNECT_RETRY = 2  # 连接失败时重建 adb forward 并重试的次数

# ---- loop ----
MAX_STEPS = 25
WAIT_INTERVAL_S = 1.5
MAX_ITEMS_SHOWN = 40
# 验证读取的复读延时。**不是**每步都等 ——
# 先无延时读一次，PASS 就走快路径（零成本）；只有没看到预期变化时才等这么久再读一次。
# 「复读一次仍未变」比「等固定时长后读一次」是更强的证据，而且快动作不用付延时税。
RECHECK_DELAY_MS = 300

# 窗口切换的瞬间副屏可能一个窗口都没有。那是过渡态，不是"副屏消失"——
# 重试这么多次仍为空才当真（scrcpy 被关掉那种）。
OBSERVE_RETRY = 3
OBSERVE_RETRY_DELAY_MS = 250

# 打扰窗口预算（ms）。超过即认为"用户交互被中断"，该目标本轮拉黑并上报。
#
# 原依据：D1 实测滚动 12ms、全局配置变更 2526ms —— "中间没有灰色地带"。
# ⚠ **那句话已被 E16 证伪，本阈值的立论依据不再成立。** 保留原值是因为改护栏
#    需要比现有更硬的证据（ARCHITECTURE §2：护栏不随环境浮动），不是因为它是对的。
#
# 实际情况是三个因素共同决定伤害，而本参数只捕捉了其中最弱、且条件依赖的一个：
#
#   ① 用户当时在干什么   E14：主屏 mCurrentFocus=null 持续存在时视频照播，
#                        0 暂停 0 冻结 —— 看视频时窗口再长也无害
#   ② 动作有没有重建副屏编辑器  E15：不重建 0/70，重建 5/30。**这是因果判据**
#   ③ 窗口时长（← 本参数）  E16：<200ms 0/67，300–500ms 47%
#                        但只在 ①② 都成立时才起作用
#
# 于是它两头都不准：E16 里 9 次污染**全部落在 500 以下**（272–431ms），一次没抓到；
# 而 Gmail 上它把 Compose(871ms) / Send(2322ms) / 正文框(1052ms) 全拉黑了 ——
# 那是任务必需的三个动作。**漏掉真阳性，同时拦住必需动作。**
#
# 重设计方向（设计建议，非实测）：判据从"窗口时长"换成"副屏 Activity 是否重建"
# —— 后者是因果的，且我们每步本来就在记 activity 与 tree_hash。
DISTURB_BUDGET_MS = 500
TREE_DEPTH_LIMIT = 25
MAX_CONSECUTIVE_FAIL = 3      # 连续 FAIL 达此数则中止（疑似卡死）
# 连续「环境毫无变化」达此数则中止。与上面那条是两个不同的判据：
# FAIL 依赖判据推断准不准，这一条只看 tree_hash 与 activity 有没有动 ——
# LLM 反复点一个什么都不做的东西时，每步都是 UNKNOWN，FAIL 计数永远是 0。
MAX_CONSECUTIVE_STALL = 4
MAX_PARSE_FAIL = 2            # LLM 输出连续解析失败达此数则中止

# ---- 目标 ----
TARGET_PKG = os.environ.get("PHONEAGENT_TARGET_PKG", "com.android.settings")
PRIMARY_DISPLAY = 0

# ---- 策略层 ----
# off | normal | patient —— 决定 LLM 是否可用 wait。不影响归还行为。
POLITENESS = os.environ.get("PHONEAGENT_POLITENESS", "normal")

# ---- LLM ----
# provider: anthropic | openai | scripted | rule
LLM_PROVIDER = os.environ.get("PHONEAGENT_LLM_PROVIDER", "anthropic")
MODEL = os.environ.get("PHONEAGENT_MODEL", "claude-sonnet-4-5")
LLM_BASE_URL = os.environ.get("PHONEAGENT_BASE_URL", "")  # OpenAI 兼容端点（DeepSeek 等）
# 推理模型的思考过程也吃这个预算：1024 时 deepseek-v4-flash 的 content 直接是空的
LLM_MAX_TOKENS = int(os.environ.get("PHONEAGENT_MAX_TOKENS", "4096"))
# 60s 对推理模型 + 长 observation 偏紧（实测在关键一步读超时，整个 run 被判死）
LLM_TIMEOUT_S = float(os.environ.get("PHONEAGENT_LLM_TIMEOUT", "150"))

# ---- 落盘 ----
RUNS_DIR = os.environ.get("PHONEAGENT_RUNS_DIR", "runs")

# ---- 压缩 ----
ANCHOR_LOOKAHEAD = 3   # 找文字锚点时向后代搜索的最大深度（HARNESS-SPEC §4.2 第 2 步）
