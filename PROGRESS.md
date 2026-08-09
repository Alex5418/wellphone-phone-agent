# PROGRESS · E19 软键盘消失归因

时间 / 做了什么 / 结果。每完成一步追加一行。

```
2026-08-09 (session)  环境确认：boot=1，副屏 display=3 在 Gmail，主屏 composetest 聚焦，
                      forward tcp:18760 在，PHONEAGENT_PORT=18760
2026-08-09 (session)  标定 --check：中位间隔 50ms / p95 83ms / 阳性✓ / 阴性✓ → 仪表可用
2026-08-09 (session)  control 组 20/20 有效，消失 0，实际轮询中位 51ms → CSV 已落盘
```
