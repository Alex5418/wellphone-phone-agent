"""每步 trajectory 落盘（HARNESS-SPEC §11）。

    runs/2026-08-06T14-22-01/
      meta.json          任务、配置、模型、结束原因
      step-01/
        observation.txt  喂给 LLM 的全文
        llm_raw.txt      LLM 原始输出
        act_req.json / act_resp.json / probe.json / verdict.json

**这个目录就是答辩材料**：一次完整 trajectory 比任何架构图都能说明 loop 在干什么。
"""

from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime

from . import config


class Trace:
    def __init__(self, task: str, root: str = config.RUNS_DIR, enabled: bool = True):
        self.enabled = enabled
        self.task = task
        self.t0 = time.time()
        self.metrics: list[dict] = []
        self.max_step = 0   # 见过的最大步号（含不落 metrics 的 finish 步）
        # 由 Loop 填入 planner.describe()，即实际生效的 provider/model/endpoint
        self.planner_info: dict | None = None
        self.dir = ""
        if not enabled:
            return
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.dir = os.path.join(root, stamp)
        os.makedirs(self.dir, exist_ok=True)

    # ---- 写入 ----

    def _step_dir(self, n: int) -> str:
        self.max_step = max(self.max_step, n)
        d = os.path.join(self.dir, f"step-{n:02d}")
        os.makedirs(d, exist_ok=True)
        return d

    def text(self, n: int, name: str, content: str) -> None:
        if not self.enabled:
            return
        with open(os.path.join(self._step_dir(n), name), "w", encoding="utf-8") as f:
            f.write(content)

    def json(self, n: int, name: str, obj) -> None:
        if not self.enabled:
            return
        with open(os.path.join(self._step_dir(n), name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def metric(self, n: int, **kw) -> None:
        """关键指标每步记录：打扰窗口 / 归还耗时 / LLM 延迟 / verdict。

        disturb_ms 是对外要报的那个数（动作 + 归还，不含任何校验读取）；
        restore_total_ms 含校验开销，只用来看仪表本身有多贵。
        """
        self.max_step = max(self.max_step, n)
        row = {"step": n, **kw}
        self.metrics.append(row)
        if self.enabled:
            with open(os.path.join(self.dir, "metrics.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _totals(self) -> dict:
        """run 级汇总。

        ⚠ **拿不到的量一律 None，不许写 0。** `scripted` / `rule` 后端根本没有
        token 概念，写 0 会被读成"这一步免费"，那是编造出来的数字。
        同理另给 `token_steps`：读的人要能看出「合计 1234 tokens」是基于 8 步还是 3 步 ——
        不写出缺失步数，合计本身就是误导。
        """
        # steps 是**规划步数**，不是 metrics 行数：最后那步 finish 会终止 loop，
        # 不产生 metrics 行，但它确实是一步（也写了 observation）。
        # 用 Trace 见过的最大步号，两者相差的就是不落 metrics 的那些步。
        totals: dict = {"steps": max(self.max_step, len(self.metrics))}
        totals["llm_calls"] = sum(1 for r in self.metrics if r.get("llm_ms") is not None)

        llm_times = [r["llm_ms"] for r in self.metrics if r.get("llm_ms") is not None]
        totals["llm_ms_total"] = sum(llm_times)
        totals["llm_ms_median"] = statistics.median(llm_times) if llm_times else None

        prompt = [r["prompt_tokens"] for r in self.metrics
                  if r.get("prompt_tokens") is not None]
        completion = [r["completion_tokens"] for r in self.metrics
                      if r.get("completion_tokens") is not None]
        reasoning = [r["reasoning_tokens"] for r in self.metrics
                     if r.get("reasoning_tokens") is not None]
        token_steps = sum(1 for r in self.metrics
                          if r.get("prompt_tokens") is not None
                          or r.get("completion_tokens") is not None
                          or r.get("reasoning_tokens") is not None)
        totals["prompt_tokens"] = sum(prompt) if prompt else None
        totals["completion_tokens"] = sum(completion) if completion else None
        totals["reasoning_tokens"] = sum(reasoning) if reasoning else None
        totals["token_steps"] = token_steps

        disturb = [r["disturb_ms"] for r in self.metrics if r.get("disturb_ms") is not None]
        totals["disturb_ms_total"] = sum(disturb)
        totals["disturb_ms_max"] = max(disturb) if disturb else 0
        return totals

    def finish(self, status: str, reason: str, extra: dict | None = None) -> None:
        if not self.enabled:
            return
        meta = {
            "task": self.task,
            "status": status,
            "reason": reason,
            "elapsed_s": round(time.time() - self.t0, 2),
            # planner_info 是**实际**生效的后端（见 Backend.describe）。
            # 回退到 config.* 只在没人设置它时发生，并显式标注 source，
            # 免得又出现「meta 记的是默认值、跑的是另一个模型」那种假出处。
            "config": {
                **(self.planner_info or {"model": config.MODEL,
                                         "provider": config.LLM_PROVIDER,
                                         "politeness": config.POLITENESS,
                                         "source": "config 默认值（未由 planner 上报）"}),
                "target_pkg": config.TARGET_PKG,
                "max_steps": config.MAX_STEPS,
                "restore": "always (硬编码，无开关)",
            },
            "totals": self._totals(),
            "metrics": self.metrics,
        }
        if extra:
            meta.update(extra)
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
