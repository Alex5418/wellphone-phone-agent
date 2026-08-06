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
import time
from datetime import datetime

from . import config


class Trace:
    def __init__(self, task: str, root: str = config.RUNS_DIR, enabled: bool = True):
        self.enabled = enabled
        self.task = task
        self.t0 = time.time()
        self.metrics: list[dict] = []
        self.dir = ""
        if not enabled:
            return
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.dir = os.path.join(root, stamp)
        os.makedirs(self.dir, exist_ok=True)

    # ---- 写入 ----

    def _step_dir(self, n: int) -> str:
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
        """关键指标每步记录：restore_ms / total_ms / LLM 延迟 / verdict。"""
        row = {"step": n, **kw}
        self.metrics.append(row)
        if self.enabled:
            with open(os.path.join(self.dir, "metrics.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def finish(self, status: str, reason: str, extra: dict | None = None) -> None:
        if not self.enabled:
            return
        meta = {
            "task": self.task,
            "status": status,
            "reason": reason,
            "elapsed_s": round(time.time() - self.t0, 2),
            "config": {
                "model": config.MODEL,
                "provider": config.LLM_PROVIDER,
                "target_pkg": config.TARGET_PKG,
                "max_steps": config.MAX_STEPS,
                "politeness": config.POLITENESS,
                "restore": "always (硬编码，无开关)",
            },
            "metrics": self.metrics,
        }
        if extra:
            meta.update(extra)
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
