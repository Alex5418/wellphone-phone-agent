"""独立于 a11y 链路的交叉校验（走 adb shell dumpsys）。

存在的理由是 ARCHITECTURE §3.4：**验证不能复用产生该结果的同一条链路**。
设备侧报的 holder_after 是从 AccessibilityWindowInfo 读的，而它的 isFocused 是
per-display 语义（实测两块屏可同时为 true），拿它当"全局焦点持有者"会得出假结论。
真正的全局持有者只有 window manager 知道，只能从 dumpsys 读。

任何一个函数拿不到结果都返回 None —— 交叉校验缺席应记为 UNKNOWN，不能记为通过。
"""

from __future__ import annotations

import re
import subprocess

_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*?\s+(?:d(\d+)\s+)?([^ }]+)\}")
_INPUT_RE = re.compile(r"mInputMethodTarget|mFocusedWindow")


def _sh(*args: str) -> str | None:
    try:
        p = subprocess.run(["adb", "shell", *args], capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def current_focus() -> str | None:
    """全局 mCurrentFocus 的窗口名（形如 'com.android.chrome/…Activity'）。"""
    out = _sh("dumpsys", "window", "windows")
    if out is None:
        out = _sh("dumpsys", "window")
    if not out:
        return None
    for line in out.splitlines():
        if "mCurrentFocus=" in line:
            m = _FOCUS_RE.search(line)
            if m:
                return m.group(2)
            return line.split("mCurrentFocus=", 1)[1].strip()
    return None


def focus_holder_pkg() -> str | None:
    """全局焦点持有者的包名。拿不到返回 None（记 UNKNOWN，不记通过）。"""
    win = current_focus()
    if not win or win in ("null", "Window{null}"):
        return None
    return win.split("/", 1)[0].split()[-1]
