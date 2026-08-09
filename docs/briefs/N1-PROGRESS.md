# N1 · 进度记录

| 时间 | 文件 | 审了几条 | 发现 |
|---|---|---|---|
| 2026-08-09 | 基线：`python -m unittest discover -s tests -q` | — | Ran 79 / OK（与 brief 预期一致） |
| 2026-08-09 | 基线：`./gradlew :app:testDebugUnitTest --rerun-tasks` | — | BUILD SUCCESSFUL；测试 XML 核对 15 条（Example 1 + LocatorResolver 8 + ProbeMock 1 + TreeHash 5），与 CLAUDE/README/harness-README 一致 |
| 2026-08-09 | `harness/config.py` 注释 | 8 | 全部 ✓（D1 12/2526ms、E14 0/0、E15 0/70 与 5/30、E16 0/67 与 47%、九次 272–431ms、Gmail 871/2322/1052、1024 截断、60s→150s） |
| 2026-08-09 | `harness/policy.py` 注释 | 4 | 全部 ✓（12/2526ms、200 倍、1533ms、~3s） |
| 2026-08-09 | `harness/loop.py` 注释 | 2 | 全部 ✓（FOCUS 刷新、E15 B/C 各 8 次 0 污染） |
| 2026-08-09 | `harness/adbutil.py` 注释 | 1 | **1 处 ✗**：「副屏排在前面」与 D1 §2 更正（顺序未定义）冲突 → 已改 |
| 2026-08-09 | `harness/observe.py` 注释 | 2 | 全部 ✓（2/4/5/6、window_count=1） |
| 2026-08-09 | `harness/verify.py` 注释/docstring | 4 | 2 ✓（step-05、05-42-53 均有 run 数据支撑）；「三种」口径漂移（vs 五种/第八种/10–11 例）⚠；「4/4 邮件正确」强度超证据 ⚠ |
| 2026-08-09 | `harness/compress.py` 注释 | 2 | 「20 次是常态」⚠ 找不到出处；findByText 宇宙 ✓（C3） |
| 2026-08-09 | `harness/planner.py` / `models.py` / `trace.py` / `tree.py` / `transport.py` / `cli.py` 注释 | 4 | planner meta 记错 model ✓（E13）；models flash 顶掉 Subject ✓；其余无量化断言 |
| 2026-08-09 | `android/…/*.kt` 注释与 KDoc | 4 | 全部 ✓（E6 10–15ms、200–400ms dumpsys 往返、2526/12ms、DEPTH 25）；另实测 Kotlin 15 条测试 |
| 2026-08-09 | `README.md` | 23 | 全部 ✓ 或可追踪；「7 步」与 E12 步数口径不同 ⚠（需人工决定）；scrcpy ≥ 3.0 无仓库内出处 ⚠ |
| 2026-08-09 | `CLAUDE.md` | 9 | 多数 ✓；「见过 2/3/4/6」与 EXPERIMENTS 的 2/4/5/6 不一致 ⚠（需人工决定） |
| 2026-08-09 | `docs/ARCHITECTURE.md` | 20 | 2 处 ✗：`~400 行 Kotlin`（实测 1557，已改）；`9/79 命中`（可推导 E16 S+M=79/9，但引用标注 E15，⚠ 需人工决定） |
| 2026-08-09 | `docs/HARNESS-SPEC.md` | 9 | 除「20 次是常态」⚠（同 compress.py）外全部 ✓ |
| 2026-08-09 | `docs/DEMO.md` | 5 | 全部 ✓（115s/8 步/31–458ms 对应 runs 23-32-27；4096 截断；800+ 字；871/2322ms） |
| 2026-08-09 | `harness/README.md` | 3 | 全部 ✓（79 条、15 条、13 条拆分） |
| 2026-08-09 | `docs/README.md`（索引） | 7 | 1 处 ✗：E10 行「归还只降概率不消除」与 E11 的 0/20 相悖，且索引缺 E11 条目 → 需人工决定 |
| 2026-08-09 | 改注释后重跑 Python 测试 | — | Ran 79 / OK |

合计：**102 条**（✓ 93 / ✗ 4 / ⚠ 5），已改 2 处，需人工决定 8 项。
