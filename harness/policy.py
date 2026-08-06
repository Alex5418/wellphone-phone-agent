"""动作空间的排除规则（护栏，不可配置关闭）。

## 为什么排除，而不是"已知边界，谨慎使用"

验收标准是「用户当前正在进行的交互不被中断」。D1 实测：

    scroll                 打扰窗口   12 ms
    切换深色主题（全局配置） 打扰窗口 2526 ms      ← 差 200 倍

3 秒按这个标准是**硬失败**，不是边界。而且这 3 秒里用户的击键会流向副屏当前
有焦点的输入框（B1 附带发现 A）—— 副屏那一页恰好停在输入框上时，就是数据污染，
属于正确性故障而非体验问题。

所以这一族目标直接排除出动作空间。排除本身是有依据的架构决策：
实测出某一族动作的打扰窗口比其他动作大两个数量级，因此不做它。

## 判据不是"动作名"，是"目标会不会触发全局配置变更"

两条判据并用：

1. **静态名单**（预防）：标签匹配 + 目标是开关类。
   这份名单靠文字匹配，**必然不完备** —— 换语言、换 app 就会漏。
   它减少已知伤害，不提供完备保证，别把它当成保证。

2. **实测预算**（检测）：任何一步实际打扰窗口超过 DISTURB_BUDGET_MS，
   就把那个条目在本轮 run 内拉黑并显式上报。
   这一条与语言、与 app 都无关 —— 它量的就是我们真正在乎的那个东西。

导航进入设置页（button）不算：进页面不改配置，页面里的那个开关才改。
"""

from __future__ import annotations

import re

from .models import Item

# 静态名单：中英文都列。只对**开关类**目标生效 —— 点进"语言"页面只是导航。
GLOBAL_CONFIG_PATTERNS = [
    r"dark\s*theme", r"深色主题", r"深色模式",
    r"night\s*mode", r"夜间模式",
    r"\blanguage\b", r"语言",
    r"font\s*size", r"字体大小", r"字号",
    r"display\s*size", r"显示大小",
    r"auto[-\s]?rotate", r"自动旋转", r"屏幕旋转", r"rotation",
    r"\btheme\b", r"主题",
]

# 「这东西是个开关吗」的 id 信号。Settings 的主开关条 id 是
# com.android.settings:id/settingslib_main_switch_bar —— 它在节点树里是个
# LinearLayout，kind 会被判成 button、没有 On/Off 状态，只看 kind 拦不住。
# D2 实跑就是这么漏过去的（先付了 1533ms 才被实测预算兜住）。
TOGGLE_ID_PATTERNS = [r"switch_bar", r"switch_widget", r"main_switch", r"toggle"]

_COMPILED = [re.compile(p, re.I) for p in GLOBAL_CONFIG_PATTERNS]
_TOGGLE_ID = [re.compile(p, re.I) for p in TOGGLE_ID_PATTERNS]

EXCLUDED_REASON = "会触发全局配置变更（所有 Activity 重建），实测打扰窗口 ~3s，已排除"
MEASURED_REASON = "上一次操作它的实际打扰窗口超预算，已在本轮排除"


def matches_global_config(label: str) -> bool:
    return any(p.search(label or "") for p in _COMPILED)


def is_toggle_like(item: Item) -> bool:
    """这条是"能改配置的开关"还是"只是进页面的导航行"。

    四个信号取并集：kind、是否可勾选、状态显示 On/Off、resource_id 像不像开关。
    只看 kind 会漏 Settings 的主开关条（它是 LinearLayout，kind=button）。
    """
    if item.kind == "switch" or item.checked is not None:
        return True
    if (item.state or "").strip() in ("On", "Off", "开", "关"):
        return True
    rid = item.res_id or ""
    return any(p.search(rid) for p in _TOGGLE_ID)


class ActionPolicy:
    """本轮 run 的动作空间策略。measured 名单随 run 累积，不跨 run 保留。"""

    def __init__(self, disturb_budget_ms: int):
        self.disturb_budget_ms = disturb_budget_ms
        self.measured_blocked: dict[str, int] = {}   # label -> 实测 disturb_ms

    def block_reason(self, item: Item) -> str | None:
        if item.label in self.measured_blocked:
            ms = self.measured_blocked[item.label]
            return f"{MEASURED_REASON}（实测 {ms} ms）"
        # 只拦开关类：导航进页面不改配置
        if is_toggle_like(item) and matches_global_config(item.label):
            return EXCLUDED_REASON
        return None

    def annotate(self, items: list[Item]) -> list[Item]:
        for it in items:
            it.blocked = self.block_reason(it)
        return items

    def record_disturbance(self, item: Item, disturb_ms: int | None) -> str | None:
        """动作后回填实测打扰窗口。超预算则拉黑并返回一条要上报的告警。"""
        if disturb_ms is None or disturb_ms <= self.disturb_budget_ms:
            return None
        self.measured_blocked[item.label] = disturb_ms
        return (f"⚠ 打扰窗口 {disturb_ms} ms 超出预算 {self.disturb_budget_ms} ms"
                f"（用户击键在这段时间里会落到副屏）—— 已把 \"{item.label}\" 排除出动作空间")
