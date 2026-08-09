# PROGRESS · E19 软键盘消失归因

时间 / 做了什么 / 结果。每完成一步追加一行。

```
2026-08-09 (session)  环境确认：boot=1，副屏 display=3 在 Gmail，主屏 composetest 聚焦，
                      forward tcp:18760 在，PHONEAGENT_PORT=18760
2026-08-09 (session)  标定 --check：中位间隔 50ms / p95 83ms / 阳性✓ / 阴性✓ → 仪表可用
2026-08-09 (session)  control 组 20/20 有效，消失 0，实际轮询中位 51ms → CSV 已落盘
2026-08-09 (session)  开工确认：boot=1，双屏 display=0/3，a11y 服务在，forward tcp:18760 在
2026-08-09 (session)  标定 --check：样本 36，中位 50ms / p95 77ms / 阳性✓ / 阴性✓ → 仪表可用
2026-08-09 (session)  先提交了上一轮遗留的 e19-rebuild.csv 冒烟 5 行（有效数据，防丢失）
2026-08-09 (session)  rebuild 组补 15 轮 → 20/20 有效，消失 10（率 50%，延迟中位 49ms 44–55）
2026-08-09 (session)  click_edit 组 20/20 有效，消失 0 → 已提交
2026-08-09 (session)  focus_edit 组 20/20 有效，消失 0 → 已提交
2026-08-09 (session)  set_text_edit 组 20/20 有效，消失 1（603ms，iter 1）→ 已提交
2026-08-09 (session)  click_button 组 20/20 有效，消失 0 → 已提交
2026-08-09 (session)  rebuild 复现 10 轮：10/10 有效，消失 3（30%，延迟 46–54ms）→ 独立 CSV 已提交
2026-08-09 (session)  六组全跑完，100/100 有效，无 SKIP 行 → 写 E19 报告 + SUMMARY
```
