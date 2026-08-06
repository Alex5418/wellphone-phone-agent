"""策略层：LLM 单步决策（HARNESS-SPEC §7）。

这是整套 harness 里**唯一**的策略层模块。换模型只换这里，护栏一行不动
（ARCHITECTURE §2「缝的位置随基座模型能力移动」）。

零第三方依赖：用 urllib 直接打 HTTP，省得为一次答辩装 SDK。
支持 anthropic / openai 兼容端点（DeepSeek、Qwen、本地 vLLM 都走这条），
外加 scripted / rule 两个离线后端 —— 没有 API key 也能把 loop 跑通。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import config
from .models import Item, Plan

ACTIONS = ("click", "long_click", "set_text", "scroll_forward", "scroll_backward",
           "back", "wait", "finish")

SYSTEM_PROMPT = """你在通过一个受控 harness 操作一台 Android 设备的副屏。

每轮你会看到当前界面被压缩后的条目列表，每条形如：
    [2] 深色主题 | switch | On
方括号里是**短 ID**。你只能用短 ID 指认目标。

规则：
- 只输出一个 JSON 对象，不要输出解释、不要用 markdown 代码围栏。
- 不要输出 resource-id、坐标、类名 —— 你看不到它们，harness 也不接受。
- 短 ID **每轮重新分配**，绝对不要引用上一轮的编号。
- 一次只做一个动作。做完会重新观测，你会看到结果。
- 同一句文字可能出现两条（如 `button` 与 `switch`）：点 button 通常是进入子页面，
  点 switch 是原地翻转开关。按你的意图选 kind。
- 目标已经达成时输出 {"action": "finish", "done": true}。

输出格式：
{"thought": "为什么这么做", "action": "click", "target": 2, "value": null, "done": false}

action 取值：click / long_click / set_text / scroll_forward / scroll_backward / back / wait / finish
set_text 必须带 value。其余 value 为 null。
"""

WAIT_CLAUSE = """- 用户正在输入时，如果本步不紧急，可以输出 {"action": "wait"} 让路。
"""


class PlannerError(RuntimeError):
    pass


# ---------------------------------------------------------------- 解析

def parse_plan(raw: str, items: list[Item]) -> Plan:
    """剥围栏 → json.loads → 校验 target 是本轮真实存在的 sid。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise PlannerError("输出里找不到 JSON 对象")
        text = m.group(0)
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        raise PlannerError(f"JSON 解析失败: {e}") from e
    if not isinstance(d, dict):
        raise PlannerError("顶层不是 JSON 对象")

    action = str(d.get("action") or "").strip().lower()
    if action not in ACTIONS:
        raise PlannerError(f"action '{action}' 不在允许集合 {ACTIONS} 内")

    target = d.get("target")
    done = bool(d.get("done"))
    if action in ("wait", "finish", "back"):
        target = None
    else:
        if not isinstance(target, int):
            raise PlannerError("target 必须是整数短 ID")
        if not any(i.sid == target for i in items):
            raise PlannerError(f"target {target} 不在本轮 observation 的短 ID 中")
    value = d.get("value")
    if action == "set_text" and not isinstance(value, str):
        raise PlannerError("set_text 必须带字符串 value")
    return Plan(thought=str(d.get("thought") or ""), action=action, target=target,
                value=value if isinstance(value, str) else None, done=done, raw=raw)


# ---------------------------------------------------------------- 后端

class Backend:
    name = "base"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError


class AnthropicBackend(Backend):
    name = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str | None = None, base_url: str = ""):
        self.model = model
        self.key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.url = (base_url or self.URL).rstrip("/")
        if base_url and not self.url.endswith("/messages"):
            self.url += "/v1/messages"
        if not self.key:
            raise PlannerError("缺少 ANTHROPIC_API_KEY")

    def complete(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": config.LLM_MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={
            "content-type": "application/json",
            "x-api-key": self.key,
            "anthropic-version": "2023-06-01",
        })
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_S) as r:
            d = json.loads(r.read().decode("utf-8"))
        parts = [c.get("text", "") for c in d.get("content", []) if c.get("type") == "text"]
        return "".join(parts)


class OpenAIBackend(Backend):
    """OpenAI 兼容端点：DeepSeek / Qwen / 本地 vLLM 都能用。"""

    name = "openai"

    def __init__(self, model: str, api_key: str | None = None, base_url: str = ""):
        self.model = model
        self.key = api_key or os.environ.get("OPENAI_API_KEY") or \
            os.environ.get("DEEPSEEK_API_KEY", "")
        base = (base_url or os.environ.get("PHONEAGENT_BASE_URL")
                or "https://api.openai.com").rstrip("/")
        self.url = base if base.endswith("/chat/completions") else base + "/v1/chat/completions"
        if not self.key:
            raise PlannerError("缺少 OPENAI_API_KEY / DEEPSEEK_API_KEY")

    def complete(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": config.LLM_MAX_TOKENS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, headers={
            "content-type": "application/json",
            "authorization": f"Bearer {self.key}",
        })
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_S) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d["choices"][0]["message"]["content"]


class ScriptedBackend(Backend):
    """离线：按预先写好的动作序列逐条吐出。用来在没有 API key 时验证 loop 与落盘。"""

    name = "scripted"

    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.i = 0

    def complete(self, system: str, user: str) -> str:
        if self.i >= len(self.script):
            return json.dumps({"thought": "脚本已跑完", "action": "finish", "done": True})
        d = self.script[self.i]
        self.i += 1
        return json.dumps(d, ensure_ascii=False)


class Planner:
    def __init__(self, backend: Backend, politeness: str = config.POLITENESS):
        self.backend = backend
        self.politeness = politeness
        self.calls = 0
        self.last_latency_ms = 0

    @property
    def system_prompt(self) -> str:
        # wait 是策略层能力，可以配置关掉；它跟归还护栏没有任何关系
        return SYSTEM_PROMPT + (WAIT_CLAUSE if self.politeness != "off" else "")

    def decide(self, observation: str, items: list[Item]) -> tuple[Plan, list[str]]:
        """返回 (plan, LLM 原始输出列表)。解析失败重试一次，把错误回灌给模型。"""
        raws: list[str] = []
        user = observation
        last_err: Exception | None = None
        for attempt in range(2):
            t0 = time.time()
            raw = self.backend.complete(self.system_prompt, user)
            self.last_latency_ms = int((time.time() - t0) * 1000)
            self.calls += 1
            raws.append(raw)
            try:
                return parse_plan(raw, items), raws
            except PlannerError as e:
                last_err = e
                user = (observation + "\n\n## 上一次输出无法解析\n"
                        f"错误：{e}\n你的输出是：\n{raw}\n\n"
                        "请只输出一个合法的 JSON 对象，不要任何其他内容。")
        raise PlannerError(f"连续两次解析失败: {last_err}")


def make_planner(provider: str = config.LLM_PROVIDER, model: str = config.MODEL,
                 script: list[dict] | None = None,
                 politeness: str = config.POLITENESS) -> Planner:
    if provider == "scripted":
        return Planner(ScriptedBackend(script or []), politeness)
    if provider == "anthropic":
        return Planner(AnthropicBackend(model, base_url=config.LLM_BASE_URL), politeness)
    if provider == "openai":
        return Planner(OpenAIBackend(model, base_url=config.LLM_BASE_URL), politeness)
    raise PlannerError(f"未知 provider '{provider}'")
