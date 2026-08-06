"""独立于 a11y 链路的交叉校验（走 adb shell dumpsys）。

存在的理由是 ARCHITECTURE §3.4：**验证不能复用产生该结果的同一条链路**。
设备侧报的 holder_after 是从 AccessibilityWindowInfo 读的，而它的 isFocused 是
per-display 语义（实测两块屏可同时为 true），拿它当"全局焦点持有者"会得出假结论。
真正的全局持有者只有 window manager 知道，只能从 dumpsys 读。

⚠ **必须按 display 分段解析**。实测 `dumpsys window displays` 的输出里每块屏各有
一行 mCurrentFocus，而且副屏排在前面：

    Display: mDisplayId=2 (organized)
      mCurrentFocus=Window{... com.android.settings/...SubSettings}
    Display: mDisplayId=0 (organized)
      mCurrentFocus=Window{... com.android.chrome/...Main}

"取第一个 mCurrentFocus" 会拿到副屏的持有者，然后得出"主屏焦点被夺走了"的假警报 ——
第一次真机跑就踩到了这个（那一版还因为 grep 不到而静默返回 None）。

任何一个函数拿不到结果都返回 None —— 交叉校验缺席应记为 UNKNOWN，不能记为通过。
"""

from __future__ import annotations

import re
import subprocess

_DISPLAY_RE = re.compile(r"Display:\s*mDisplayId=(\d+)")
_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*?\s(\S+)\}")


def _sh(*args: str) -> str | None:
    try:
        p = subprocess.run(["adb", "shell", *args], capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def focus_by_display() -> dict[int, str]:
    """{display_id: 'pkg/activity'}。读不到返回空 dict。"""
    out = _sh("dumpsys", "window", "displays") or _sh("dumpsys", "window")
    if not out:
        return {}
    result: dict[int, str] = {}
    current: int | None = None
    for line in out.splitlines():
        m = _DISPLAY_RE.search(line)
        if m:
            current = int(m.group(1))
            continue
        if current is None or "mCurrentFocus=" not in line:
            continue
        f = _FOCUS_RE.search(line)
        if f and f.group(1) not in ("null", "Window{null"):
            result.setdefault(current, f.group(1))
    return result


def current_focus(display: int = 0) -> str | None:
    """指定 display 的 mCurrentFocus 窗口名（'pkg/activity'）。"""
    return focus_by_display().get(display)


def focus_holder_pkg(display: int = 0) -> str | None:
    """指定 display 上全局焦点持有者的包名。拿不到返回 None（记 UNKNOWN，不记通过）。"""
    win = current_focus(display)
    if not win:
        return None
    return win.split("/", 1)[0]
