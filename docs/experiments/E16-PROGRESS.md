# E16 剂量反应实验 · 进度记录

2026-08-07 · 分支 exp/e16-dose-response · 端口 PHONEAGENT_PORT=18760

## 环境
- 模拟器 wellphone_a14, emulator-5554
- display 0 (主屏 composetest), display 2 (副屏 Gmail)
- scrcpy 副屏 on display 2
- ACCESSIBILITY: phoneagent enabled

## 运行记录

| 时间 | 内容 |
|------|------|
| 2026-08-07 | 环境重建，先验五项全 ✓ |
| 2026-08-07 | S组第1轮 20次 2命中（389ms/337ms） |
| 2026-08-07 | S组第2轮 20次 3命中（375ms/364ms/397ms） |
| 2026-08-07 | S组完成 40次 5命中 |
| 2026-08-07 | M组第1轮 20次 1命中（272ms） |
| 2026-08-07 | M组第2轮 20次 3命中（383ms/431ms/314ms），iter 20 主屏 670→0 |
| 2026-08-07 | M组完成 40次 4命中 |
| 2026-08-07 | 模拟器 ANR（SystemUI 两屏都弹）→ 冷重启，主屏 composetest 堆到 670+ 后崩 |

