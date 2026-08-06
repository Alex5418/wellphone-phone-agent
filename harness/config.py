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
# 动作到界面稳定之间隔着一段动画。首次真机跑就踩到：scroll 之后立刻读 tree_hash，
# 读到的还是滚动前那一帧 → 判成"没生效"，而下一轮观测里明明已经滚过去了。
# 读太早会把成功读成失败，所以验证前先等一小会儿。
# 这不是在放水：它只是把读取放在正确的时刻，判据本身一个字没松。
SETTLE_MS = 400
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
LLM_MAX_TOKENS = 1024
LLM_TIMEOUT_S = 60.0

# ---- 落盘 ----
RUNS_DIR = os.environ.get("PHONEAGENT_RUNS_DIR", "runs")

# ---- 压缩 ----
ANCHOR_LOOKAHEAD = 3   # 找文字锚点时向后代搜索的最大深度（HARNESS-SPEC §4.2 第 2 步）
