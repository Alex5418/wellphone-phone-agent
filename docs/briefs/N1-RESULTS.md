# N1 · 全仓库数字审计结果

**分支** `audit/n1-numbers` · **性质** 核对任务 · **方法** 每条量化断言追到出处（实验报告 / runs / 测试实际输出），追不到标「⚠ 找不到出处」，不猜。

**基线**：`python -m unittest discover -s tests -q` → `Ran 79 tests ... OK`（见文末）。Kotlin 15 条经 `./gradlew :app:testDebugUnitTest --rerun-tasks` 实际跑过（BUILD SUCCESSFUL，测试 XML：Example 1 + LocatorResolver 8 + ProbeMock 1 + TreeHash 5 = 15）。

---

## 汇总

| 指标 | 值 |
|---|---|
| 审了（表行） | **102** |
| ✓ 一致 | **93** |
| ✗ 不一致（已改） | **4**（其中 2 处已直接改，2 处涉及重述结论 → 列入需人工决定） |
| ⚠ 找不到出处 / 需人工决定 | **5** |
| 已改动的文件 | 2（`harness/adbutil.py`、`docs/ARCHITECTURE.md`） |

按 brief §7 的优先级，**全部六类文件都已审完**（harness/*.py、*.kt、README、CLAUDE、ARCHITECTURE、HARNESS-SPEC + DEMO + harness/README + docs/README），没有未审的文件。

---

## §4 主表

> 出处列给出 `file:行` + 原文摘录。结论列三值：✓ / ✗ / ⚠。

### 批次 1 · harness/*.py 注释与 docstring

| # | 文件:行 | 断言原文 | 出处（file:行 + 原文引用） | 结论 |
|---|---|---|---|---|
| 1 | `harness/config.py:31` | `D1 实测滚动 12ms、全局配置变更 2526ms` | `docs/experiments/D1-FIRST-REAL-RUN.md:18` `scroll_forward 12 ms`；`:19` `click Dark theme 开关 2526 ms` | ✓ 一致 |
| 2 | `harness/config.py:37-38` | `E14：主屏 mCurrentFocus=null 持续存在时视频照播，0 暂停 0 冻结` | `E14-VIDEO-DISTURBANCE.md:50` `A 对照 … PAUSED 0 … 最长画面冻结 0.0s`；`:51` B 组 0；`:52` C 组 0 | ✓ 一致 |
| 3 | `harness/config.py:39` | `E15：不重建 0/70，重建 5/30` | `E15-SECONDARY-FIELD-CONTAMINATION.md:47` `**无重建 70 次 → 0 命中；有重建 30 次 → 5 命中**` | ✓ 一致 |
| 4 | `harness/config.py:40` | `E16：<200ms 0/67，300–500ms 47%` | `E16-DOSE-RESPONSE.md:31` `0–200 ms 67 0 0.0 %`；`:33` `300–500 ms 17 8 47.1 %` | ✓ 一致 |
| 5 | `harness/config.py:43` | `E16 里 9 次污染全部落在 500 以下（272–431ms）` | `E16-DOSE-RESPONSE.md:36` `九次命中的窗口：272 / 314 / 337 / 364 / 375 / 383 / 389 / 397 / 431 ms` | ✓ 一致 |
| 6 | `harness/config.py:44` | `Gmail 上它把 Compose(871ms) / Send(2322ms) / 正文框(1052ms) 全拉黑了` | `E16-DOSE-RESPONSE.md:71` `把 Compose(871 ms) / Send(2322 ms) / 正文框(1052 ms) 全拉黑` | ✓ 一致 |
| 7 | `harness/config.py:71-72` | `1024 时 deepseek-v4-flash 的 content 直接是空的` | `D2-LLM-REAL-RUN.md:75` `1024 时 content 直接是空字符串` | ✓ 一致 |
| 8 | `harness/config.py:73-74` | `60s 对推理模型 + 长 observation 偏紧（实测在关键一步读超时，整个 run 被判死）` | `E13-OBSERVATION-NOT-MODEL.md:119` `一次 LLM 调用失败: read timed out 导致一轮作废，已把 LLM_TIMEOUT_S 从 60s 放宽到 150s` | ✓ 一致 |
| 9 | `harness/policy.py:5-8` | `D1 实测：scroll 打扰窗口 12 ms / 切换深色主题（全局配置）打扰窗口 2526 ms ← 差 200 倍` | `D1-FIRST-REAL-RUN.md:18-21` 同上表；`相差 200 倍` 见 `:21` | ✓ 一致 |
| 10 | `harness/policy.py:52` | `D2 实跑就是这么漏过去的（先付了 1533ms 才被实测预算兜住）` | `D2-LLM-REAL-RUN.md:55` `实测预算兜住了它（1533 ms > 500 ms 预算）` | ✓ 一致 |
| 11 | `harness/policy.py:58` | `EXCLUDED_REASON = "…实测打扰窗口 ~3s"` | `D1-FIRST-REAL-RUN.md:37` `打扰窗口从 12 ms 涨到 ~3 s` | ✓ 一致 |
| 12 | `harness/loop.py:274-275` | `实测：set_text 后立刻读 = 旧值；做一次 FOCUS 再读 = 新值。` | `E12-GMAIL-DEMO.md:128` `写入后立刻读 = 旧值；等 350ms 复读 = 仍是旧值；做一次 FOCUS 再读 = 新值` | ✓ 一致 |
| 13 | `harness/loop.py:276` | `E15 已量化过这一动作类别（B/C 两组各 8 次，0 污染）` | `E15-SECONDARY-FIELD-CONTAMINATION.md:38` `B FOCUS To 框 1 ✗ true — 8 0`；`:39` `C FOCUS To 框 1 ✗ false — 8 0` | ✓ 一致 |
| 14 | `harness/adbutil.py:8-9` | `实测 dumpsys window displays 的输出里每块屏各有一行 mCurrentFocus，而且副屏排在前面` | `D1-FIRST-REAL-RUN.md:73-74` `⚠ 更正：本文初稿写的是"副屏排在前面所以要分段"—— 那是从一个样本推出来的结论，不成立。正确的理由是顺序未定义`。同文 `:60` `哪块屏排在前面是不定的 … 0→2、2→0、0→4、6→0 都出现过` | ✗ 不一致（已改） |
| 15 | `harness/observe.py:31` | `display id 每次都变（实测 2/4/5/6）` | `EXPERIMENTS.md:250` `每次重启 scrcpy 都会变：实测出现过 2 / 4 / 5 / 6`；`:1078` `实测 2 / 4 / 5 / 6`；`HARNESS-SPEC.md:16` 同 | ✓ 一致 |
| 16 | `harness/observe.py:91` | `实测 window_count 仍为 1`（浮层不产生新窗口） | `E13-OBSERVATION-NOT-MODEL.md:44` `window_count = 1 根节点数 = 1` | ✓ 一致 |
| 17 | `harness/verify.py:10` | `实测过三种"工具会撒谎"的形态` | ARCHITECTURE 自陈 `已实测五种`（`ARCHITECTURE.md:268` 起编号 1–5）；但 E12 又称 `第八种形态`（`E12-GMAIL-DEMO.md:149`），E14 称 `第 10、11 例`（`E14-VIDEO-DISTURBANCE.md:34`）。verify.py 的「三种」是 D1 早期版本残留下来的计数，与后续文档的「五种 / 第八种 / 10–11 例」口径不一 | ⚠ 出处自相矛盾：三种（verify.py 遗留）vs 五种（ARCHITECTURE）vs 第八种（E12）vs 10–11 例（E14）。**不擅改**，列两处出处 |
| 18 | `harness/verify.py:98-99` | `实测：runs/2026-08-07T05-52-07/step-05，正文写入完全正确，locator 是 L4(text="Compose email")，probe found=False，判了 FAIL` | 逐文件核对 `runs/2026-08-07T05-52-07/step-05/act_req.json`（locator strategy=L4 text=Compose email）+ `probe.json`（`found=false candidates=0`）+ `verdict.json`（`result=FAIL detail=期望…实际 None`） | ✓ 一致 |
| 19 | `harness/verify.py:100-101` | `上一轮（05-42-53）模型正是因为连续收到这种假失败而反复重写，直到卡死中止` | `E12-GMAIL-DEMO.md:131` `见 runs/2026-08-07T05-42-53，第 7–10 步连写四次同一个值`；逐文件核对 `runs/2026-08-07T05-42-53` step-07..10 verdict 均为 UNKNOWN text_equals_value、status=aborted | ✓ 一致 |
| 20 | `harness/verify.py:107-108` | `实测：Gmail 撰写页正文 4/4 属后者（判 FAIL，但收到的邮件正文完全正确）` | 提交 `2f60f07` message：`实测 4/4：Gmail 撰写页正文 set_text 判 FAIL，而收到的邮件正文完全正确`。落盘可数到的最早四例：`16-10-17/step-09`、`16-51-30/step-08`、`23-21-54/step-06`、`23-32-27/step-06`（text_equals_value FAIL 且写入值为正文）。其中 E12（16-51-30）邮件正文人工确认为正确 | ✓ 一致（四例可数；对「收到的邮件正文完全正确」只有 E12 有人工确认，见需人工决定 #8） |
| 21 | `harness/compress.py:138` | `同一个 id 在列表里出现 20 次是常态` | 翻遍实验报告与 runs 原始节点数据：样本里 id 最大重复数是 10（`settings-display.xml` 的 `android:id/title`）、Chrome NTP 8 次、Clock 5 次；**没有任何一处实测过 20 次**。与 `HARNESS-SPEC.md:395` 同句 | ⚠ 找不到出处（「20 次」无实测依据；两个文件同句互相引用，都无源头） |
| 22 | `harness/compress.py:171` | `findByText 宇宙 = text ∪ content_desc（C3 实测，执行侧同规则）` | `C3-EXECUTION.md:78` `raw=2 证明 findAccessibilityNodeInfosByText 同时匹配 text 与 contentDescription` | ✓ 一致 |
| 23 | `harness/planner.py:131-133` | `曾经因此让一次 flash 的 run 在 meta.json 里被记成 claude-sonnet-4-5` | `E13-OBSERVATION-NOT-MODEL.md:114` `runs/2026-08-06T23-32-27/meta.json 里 config.model 写的是 claude-sonnet-4-5，但那一轮实际跑的是 flash` | ✓ 一致 |
| 24 | `harness/models.py:131` | `flash 实测栽在这里：补全把 Subject 顶掉` | `E13-OBSERVATION-NOT-MODEL.md:35` `Gmail 的自动补全列表出现时会把 Subject 行顶掉`；E12 §6 同 | ✓ 一致 |
| 25 | `harness/models.py:129-130` | `实测 window_count 仍为 1` | `E13-OBSERVATION-NOT-MODEL.md:44` 同 #16 | ✓ 一致 |
| 26 | `harness/AgentServer.kt:18`（注释） | `PC 侧：adb forward tcp:8760 … 短连接` | `HARNESS-SPEC.md:49` `adb forward tcp:8760`；`:52` `一次请求一次连接（短连接）` | ✓ 一致 |
| 27 | `harness/AgentCommands.kt:359-360` | `dumpsys window displays … 但那要 200-400ms` | `E10-COMPOSING-BREAK-CAUSE.md:59` `唯一能看见的是 dumpsys window displays，但一次往返 200–400 ms` | ✓ 一致 |
| 28 | `harness/AgentCommands.kt:406` | `focus_ms: 真正的打扰窗口（重解析 + ACTION_FOCUS），与 E6 的 10–15ms 可比` | `EXPERIMENTS.md:885` `可在 10–15 ms 内把 window 焦点拉回 display 0` | ✓ 一致 |
| 29 | `harness/AgentCommands.kt:491-492` | `实测主题切换那一步打扰窗口是 2526ms（滚动只有 12ms）` | `D1-FIRST-REAL-RUN.md:18-19` 同 #1 | ✓ 一致 |
| 30 | `android/…/Snapshot.kt:20-21` | `与 HARNESS-SPEC §2.2 的深度上限一致`（DEPTH_LIMIT=25） | `HARNESS-SPEC.md:157` `深度上限 25`；`config.py` `TREE_DEPTH_LIMIT = 25` | ✓ 一致 |

### 批次 2 · README.md + CLAUDE.md

| # | 文件:行 | 断言原文 | 出处 | 结论 |
|---|---|---|---|---|
| 31 | `README.md:9` | `演示视频（约 100s）` | 对应 trajectory `runs/2026-08-07T05-52-07`，`meta.json elapsed_s = 89.06` | ✓ 一致（约数） |
| 32 | `README.md:12` | `7 步：Compose → 收件人 → 主题 → 正文 → Send` | `runs/2026-08-07T05-52-07/` 共 7 个 step 目录（step-01..07，06 为动作、07 为 finish）；E12 该任务为 12 步含 3 次 wait，步数口径不同（见需人工决定 #3） | ✓ 一致（该 trajectory 7 步） |
| 33 | `README.md:49` | `JDK 17+、Python 3.10+、scrcpy ≥ 3.0、minSdk 30` | `android/app/build.gradle.kts` `minSdk = 30` ✓；scrcpy ≥ 3.0 为外部工具版本要求（仓库内无实验证据） | ⚠ 部分找不到出处（minSdk 30 有出处；scrcpy ≥ 3.0 仓库内无法定） |
| 34 | `README.md:59` | `离线自测，79 条` | 实际跑：`Ran 79 tests ... OK` | ✓ 一致（实测） |
| 35 | `README.md:93` | `软键盘打字 · agent 不重建副屏 Activity` → `污染 0 / 污染 0`，`E8 8 组 + E15 70 次` | `E8-SOFT-KEYBOARD.md:32-35` 软键盘 4 组 0 污染；`E15-SECONDARY-FIELD-CONTAMINATION.md:47` 无重建 70 次 0 命中 | ✓ 一致 |
| 36 | `README.md:94` | `污染 5/30，护栏挡不住` | `E15-SECONDARY-FIELD-CONTAMINATION.md:47` 有重建 30 次 5 命中 | ✓ 一致 |
| 37 | `README.md:95` | `120 键中 56 键灌进副屏，且无上界` / `降到 6 键` | `E7-KEYSTROKE-LANDING.md:32` B 组 `120 64 56 0 5 ms`；`:33-35` C 组 6/21/6 | ✓ 一致（降到 6 键取三次中的最小值，E7 同文即如此表述） |
| 38 | `README.md:96` | `中文输入法连打 · 导航类动作` → `10/20 打断` / `0/20` | `E11-RESULTS.md:51-52` `nav false 20 10 50%`；`nav true 20 0 0%` | ✓ 一致 |
| 39 | `README.md:97` | 滚动类动作 `0/20` / `0/20` | `E11-RESULTS.md:49-50` scroll 两格 0% | ✓ 一致 |
| 40 | `README.md:98` | 看视频 `0 暂停 0 冻结` | `E14-VIDEO-DISTURBANCE.md:50-52` 三组 PAUSED 0、冻结 0.0s | ✓ 一致 |
| 41 | `README.md:106-107` | `E12：焦点 8/8 归还成功` | `E12-GMAIL-DEMO.md:19` `焦点归还 8/8 成功` | ✓ 一致 |
| 42 | `README.md:113-114` | `稳态下（不重建）70 次 0 污染，重建后 30 次 5 次污染；0/10 vs 3/20` | `E15-SECONDARY-FIELD-CONTAMINATION.md:47` 同 #36；`:53` `D 0/10，F 3/20` | ✓ 一致 |
| 43 | `README.md:116` | `焦点归还耗时实测 12ms（滚动）到约 1.5s` | `D1-FIRST-REAL-RUN.md:18` 12ms；`E14-VIDEO-DISTURBANCE.md:51` B 组 `489–1481ms` | ✓ 一致（12ms 滚动 / ~1.5s 为副屏重节点场景） |
| 44 | `README.md:117` | `全局配置类动作实测 2.5s` | `D1-FIRST-REAL-RUN.md:19` 2526 ms | ✓ 一致 |
| 45 | `README.md:121` | `焦点 8/8 归还（E12）` | 同 #41 | ✓ 一致 |
| 46 | `README.md:122-123` | `弱模型 8 步独立完成，比强模型步数更少、LLM 延迟从 65.6s 降到 10.9s` | `E13-OBSERVATION-NOT-MODEL.md:21` ③ 补观测后 flash 8 步；`:20` ① 65.6s；`:21` ③ 10.9s；`:24` 比 pro 还少 | ✓ 一致 |
| 47 | `README.md:134-135` | `79 条离线测试` + `15 条 JVM 单测` | Python 实测 79；Kotlin 实测 15（本例 1+8+1+5） | ✓ 一致（实测） |
| 48 | `README.md:137-138` | `15 条里有覆盖意义的是 13 条（LocatorResolver 8 + treeHash 5）` | 实测：LocatorResolverTest 8、TreeHashTest 5；ExampleUnitTest 与 ProbeMockTest 为 stub/探路 | ✓ 一致 |
| 49 | `README.md:143` | `仅在模拟器 API 34 上验证` | 各实验头均标 API 34 / 模拟器 | ✓ 一致 |
| 50 | `README.md:145` | `ime.dismissed 45 步 0 次为真` | `E18-IME-DISMISSAL-ATTRIBUTION.md:27` `带 ime 字段的 45；ime.dismissed=true 的步数 0` | ✓ 一致 |
| 51 | `README.md:146` | `四次可定位的消失一次都不在那个窗口里` | `E18-IME-DISMISSAL-ATTRIBUTION.md:58` `四次可定位的，落在 ① 的是 0 次` | ✓ 一致 |
| 52 | `README.md:152` | `中文 composing 矩阵做到每格 n≥20` | `E11-RESULTS.md:45` `主表（每格 ≥20 次有效运行）`；`:49-52` 各 20 | ✓ 一致 |
| 53 | `README.md:154-156` | `读回时多出 2 个字符（…@gmail.com → …@gmail.comge），E15 用 6 组条件共 50 次未能复现` | `E15-SECONDARY-FIELD-CONTAMINATION.md:27` `alexw769829@gmail.com … …comge`；`:110` `第一版收尾是「50 次未能复现」` | ✓ 一致 |
| 54 | `CLAUDE.md:50` | `display id 每次都变 | 见过 2/3/4/6` | `EXPERIMENTS.md:250` `实测出现过 2 / 4 / 5 / 6`；observe.py/HARNESS-SPEC 均 2/4/5/6 | ✗ 不一致（已改到 observe.py 一侧的出处是 2/4/5/6；CLAUDE.md 的「2/3/4/6」多 3 少 5。3 有 E14 实例：`E14-VIDEO-DISTURBANCE.md:4` 副屏 display 3；5 无。**CLAUDE.md 该行未改**，见需人工决定 #7） |
| 55 | `CLAUDE.md:52` | `PHONEAGENT_MAX_TOKENS=16384` 时思考占满预算、content 为空 | `E13-OBSERVATION-NOT-MODEL.md:19` ① flash 16384 仍卡死（同处）；`E17-LOCAL-MODEL-REPLAY.md:63` `4096 时 qwen 出现过一次截断` | ✓ 一致（这是给执行者的推荐值，出处成立） |
| 56 | `CLAUDE.md:57` | `BACK 在副屏是空转 | 三次实证` | `ARCHITECTURE.md:545` `已有三次实证（runs/2026-08-07T05-42-53/step-02 等）` | ✓ 一致 |
| 57 | `CLAUDE.md:58` | `拼音堆到 800+ 字时设备侧遍历超 5s → act TIMEOUT → SystemUI 两屏 ANR` | `E15-SECONDARY-FIELD-CONTAMINATION.md:88-89` `拼音 composing 缓冲不封顶时会堆到 800+ 字，设备侧遍历超过 5s → act TIMEOUT → SystemUI 在两个屏上一起 ANR` | ✓ 一致 |
| 58 | `CLAUDE.md:73-76` | `Python 79 条` + `Kotlin 15 条`，其中 13 条有覆盖意义 | 实测（同 #47/#48） | ✓ 一致 |
| 59 | `CLAUDE.md:86-87` | `DISTURB_BUDGET_MS=500 立论依据已被 E16 证伪 … 九次污染全在 272–431ms` | `E16-DOSE-RESPONSE.md:40` `九次污染没有一次超过 500 ms`；`:36` 窗口列表 | ✓ 一致 |

### 批次 3 · docs/ARCHITECTURE.md

| # | 文件:行 | 断言原文 | 出处 | 结论 |
|---|---|---|---|---|
| 60 | `docs/ARCHITECTURE.md:19` | `实测覆盖 6 个动作类型` | `SUBTASK-A-RESULTS.md:11` `在 6 个可测动作中（含后补的 SET_TEXT）` | ✓ 一致 |
| 61 | `docs/ARCHITECTURE.md:27` | `E7 定量：不归还时 120 字里 56 个，且无上界` | `E7-KEYSTROKE-LANDING.md:32` 同 #37 | ✓ 一致 |
| 62 | `docs/ARCHITECTURE.md:49` | `焦点短暂丢失（10–15 ms）` | `EXPERIMENTS.md:885` `10–15 ms`（E6） | ✓ 一致 |
| 63 | `docs/ARCHITECTURE.md:65` | `实测单步 1.5–149 s`（LLM 延迟） | `E18-IME-DISMISSAL-ATTRIBUTION.md:86` `单步 llm_ms 从 1.5 s 到 149 s` | ✓ 一致 |
| 64 | `docs/ARCHITECTURE.md:73-75` | 物理键盘：不归还 56/120；归还 6–21/120；无焦点 120/120 | `E7-KEYSTROKE-LANDING.md:32-37` | ✓ 一致 |
| 65 | `docs/ARCHITECTURE.md:77` | 软键盘全局配置变更（窗口 1364 ms）6/15 | `E8-SOFT-KEYBOARD.md:36` `15 9 0 6 1364 ms` | ✓ 一致 |
| 66 | `docs/ARCHITECTURE.md:89-92` | `nav × restore=true 打断 0/20，阳性对照 nav × restore=false 为 10/20（50%）` | `E11-RESULTS.md:51-52` 同 #38；`E11-SUMMARY.md:5` `nav×false 10/20（50%）；nav×true 0/20（0%）` | ✓ 一致 |
| 67 | `docs/ARCHITECTURE.md:104` | `导航点击的打扰窗口只有 8–20 ms` | `E10-COMPOSING-BREAK-CAUSE.md:70,81` `导航点击的窗口只有 8–20 ms` | ✓ 一致 |
| 68 | `docs/ARCHITECTURE.md:153` | `同一个弱模型 8 步完成（比强模型还少），LLM 延迟从 65.6s 降到 10.9s` | `E13-OBSERVATION-NOT-MODEL.md:21,24` 同 #46 | ✓ 一致 |
| 69 | `docs/ARCHITECTURE.md:268` | `已实测五种"工具会撒谎"的形态` | 自枚举 1–5（`ARCHITECTURE.md:270-276`） | ✓ 一致（但见 #17 的口径问题） |
| 70 | `docs/ARCHITECTURE.md:276` | `media_session 的 position … 走 89ms 就冻住不动` | `E14-VIDEO-DISTURBANCE.md:23` `position 走了 89ms 就冻在 346383 不动` | ✓ 一致 |
| 71 | `docs/ARCHITECTURE.md:365-366` | `scroll 12 ms / 切换深色主题（全局配置变更）2526 ms` | `D1-FIRST-REAL-RUN.md:18-19` | ✓ 一致 |
| 72 | `docs/ARCHITECTURE.md:370-372` | 单步重跑：重解析 2962 ms / ACTION_FOCUS 225 ms | `D1-FIRST-REAL-RUN.md:29-31` `reResolvePrimary … 2962 ms`；`performAction … 225 ms` | ✓ 一致（且 `:369` 已注明两数不构成同一次分解，与 D1 一致） |
| 73 | `docs/ARCHITECTURE.md:385` | `DISTURB_BUDGET_MS（500 ms）` | `harness/config.py:49` `DISTURB_BUDGET_MS = 500` | ✓ 一致 |
| 74 | `docs/ARCHITECTURE.md:459` | `Android（Kotlin，~400 行）` | 实测 5 个主源文件共 **1557 行**（AgentAccessibilityService 535 + AgentCommands 554 + AgentServer 113 + LocatorResolver 170 + Snapshot 185）；归档提交 `4cffbe3` 时即已 1434 行，从无 ~400 的阶段 | ✗ 不一致（已改） |
| 75 | `docs/ARCHITECTURE.md:487` | `归还与动作原子绑定，实测 12–300 ms` | `D1-FIRST-REAL-RUN.md:18` 12ms；`D2-LLM-REAL-RUN.md:40` `composetest 313 ms`；E14 §2 489–1481ms 为 launcher 场景 | ✓ 一致（Settings 场景 12–313ms） |
| 76 | `docs/ARCHITECTURE.md:500` | `重建副屏 Activity 时 9/79 命中` | 可推导出处：`E16-DOSE-RESPONSE.md:50-51` 分组表 S 组 40 次命中 5 + M 组 39 次命中 4 = **79 次 9 命中**（L 组 20 次 0 命中因自变量操纵失败被排除）。但该行**引用标注是 E15**，而 E15 正文是 `重建 30 次 5 命中`（`E15-SECONDARY-FIELD-CONTAMINATION.md:47`），不是 9/79。数字能对上 E16 的 S+M 组合，引用标注却指向 E15 | ⚠ 出处需推导/标注错位：9/79 来自 E16 分组 S+M（79 次 9 命中），但行内引用写的是 E15（其数为 5/30）。**需人工决定：确认引用该指 E16，或改为 E16 的 9/99** |
| 77 | `docs/ARCHITECTURE.md:542` | `runs/2026-08-07T05-52-07/（7 步发出一封 Gmail）` | 该 trajectory 7 个 step 目录 | ✓ 一致 |
| 78 | `docs/ARCHITECTURE.md:548` | `JVM 单测 15 条只覆盖 treeHash 与 LocatorResolver` | 实测 15 条，覆盖 LocatorResolver 8 + treeHash 5；`AgentCommands/AgentServer 仍无测试` 为真 | ✓ 一致 |
| 79 | `docs/ARCHITECTURE.md:550` | `全部结论只来自 3 个 app（Settings / Gmail / composetest）` | 实验头逐一核对：E7-E11 Settings/composetest、E12-E16 Gmail/composetest | ✓ 一致 |

### 批次 4 · HARNESS-SPEC + DEMO + harness/README + docs/README

| # | 文件:行 | 断言原文 | 出处 | 结论 |
|---|---|---|---|---|
| 80 | `docs/HARNESS-SPEC.md:16` | `display id 每次都变（2/4/5/6）` | `EXPERIMENTS.md:250` 同 #15 | ✓ 一致 |
| 81 | `docs/HARNESS-SPEC.md:157` | `深度上限 25` | `Snapshot.kt DEPTH_LIMIT = 25`；`config.py TREE_DEPTH_LIMIT = 25` | ✓ 一致 |
| 82 | `docs/HARNESS-SPEC.md:158` | `单次响应超过 512 KB 时降级` | `AgentCommands.kt MAX_RESPONSE_BYTES = 512 * 1024` | ✓ 一致 |
| 83 | `docs/HARNESS-SPEC.md:395` | `同一个 id 在列表里出现 20 次是常态` | 同 #21 | ⚠ 找不到出处 |
| 84 | `docs/HARNESS-SPEC.md:466` | `E7 实测此状态下击键 100% 落入 agent 工作区` | `E7-KEYSTROKE-LANDING.md:37` E 组 `120 0 120 0 9 ms`（100%） | ✓ 一致 |
| 85 | `docs/HARNESS-SPEC.md:502` | `超过 40 条时裁剪` | `config.py MAX_ITEMS_SHOWN = 40` | ✓ 一致 |
| 86 | `docs/HARNESS-SPEC.md:545` | `max_steps: int = 25` | `config.py MAX_STEPS = 25` | ✓ 一致 |
| 87 | `docs/HARNESS-SPEC.md:663-664` | `display id 每次都变（2/4/5/6）… 哪块屏排在前面是不定的（0→2、2→0、0→4、6→0）` | `EXPERIMENTS.md:250`；`D1-FIRST-REAL-RUN.md:60` `0→2、2→0、0→4、6→0 都出现过` | ✓ 一致 |
| 88 | `docs/HARNESS-SPEC.md:678` | `等 300ms 复读一次` | `config.py RECHECK_DELAY_MS = 300` | ✓ 一致 |
| 89 | `docs/DEMO.md:112` | `上次成功用了 115 秒 / 8 步，disturb_ms 每步 31–458ms` | `runs/2026-08-06T23-32-27` meta `elapsed_s=115.41`、disturb 范围 31–458（metrics 逐条） | ✓ 一致 |
| 90 | `docs/DEMO.md:139` | `输出被 max_tokens=4096 截断 … content 为空` | `E17-LOCAL-MODEL-REPLAY.md:63` `4096 时 qwen 出现过一次截断` | ✓ 一致 |
| 91 | `docs/DEMO.md:142` | `主屏 composing 缓冲堆太大（800+ 字）` | `E15-SECONDARY-FIELD-CONTAMINATION.md:88` 同 #57 | ✓ 一致 |
| 92 | `docs/DEMO.md:155` | `实测 Compose 871ms、Send 2322ms` | `E16-DOSE-RESPONSE.md:71` 同 #6 | ✓ 一致 |
| 93 | `harness/README.md:35` | `selftest … 79 条` | 实测 79 | ✓ 一致 |
| 94 | `harness/README.md:94-97` | `15 条 JVM 单测 … 有覆盖意义的是 13 条：LocatorResolver 8 + Snapshot.treeHash 5` | 实测 | ✓ 一致 |
| 95 | `docs/README.md:36` | `D1 … 滚动 12 ms，全局配置变更 2526 ms … 重解析（2962 ms），归还原语本身只要 225 ms —— 两个数出自两次 run，不构成同一次的分解` | `D1-FIRST-REAL-RUN.md:18-31`；`b0c460b` commit 已修正「两个数不构成分解」 | ✓ 一致 |
| 96 | `docs/README.md:38` | `E7 … 120 字里 56 个 … 压到 6 个 … 129/200` | `E7-KEYSTROKE-LANDING.md:32,33,36` | ✓ 一致 |
| 97 | `docs/README.md:39` | `E8 … 丢 40% 击键` | `E8-SOFT-KEYBOARD.md:66` `15 下丢 6 下（40%）` | ✓ 一致 |
| 98 | `docs/README.md:40` | `E9 … 丢 7 个字母` | `E9-PINYIN-COMPOSING.md:41` `丢字 7 个` | ✓ 一致 |
| 99 | `docs/README.md:41` | `E10 … 导航点击会打断，归还只降概率不消除` | E10 正文：`:21` `归还能降低概率，但不是可靠保护（3 次里仍破了 1 次）`。**但 E10 已被 E11 更正**：`E10-COMPOSING-BREAK-CAUSE.md:7-9` `「归还只能降低概率、不能消除」不成立 … E11 实测 nav × restore=true 0/20`。docs/README 的 E10 行仍写「只降概率不消除」，与 E11 的 0/20 相悖 | ✗ 不一致（被更正史里的旧结论）。docs/README 属索引、E10 行是摘要，改动需重述结论 → **需人工决定 #4** |
| 100 | `docs/README.md:46` | `E16 … 九次污染全在 272–431ms，DISTURB_BUDGET_MS=500 一次没拦住。0/67、47%` | `E16-DOSE-RESPONSE.md:36,31,33` | ✓ 一致 |
| 101 | `docs/README.md:48` | `E18 … 仪表 45 步 dismissed 0 次 … 采样间隔＝LLM 延迟（1.5–149 s）` | `E18-IME-DISMISSAL-ATTRIBUTION.md:27,86` | ✓ 一致 |
| 102 | `docs/README.md:47` | `E17 … 30/30 可解析、30/30 从不选中 ⛔ … 6/6 全无视` | `E17-LOCAL-MODEL-REPLAY.md:57,72` | ✓ 一致 |

---

## 已改动清单

| # | 文件:行 | 原来 | 改成 | 出处 |
|---|---|---|---|---|
| 1 | `harness/adbutil.py:8-9` | `而且副屏排在前面` | `而且**哪块屏排在前面是不定的**（…D1 §2 已更正初稿「副屏排在前面」的错误结论）` | `D1-FIRST-REAL-RUN.md:73-74` `⚠ 更正：…那是从一个样本推出来的结论，不成立` |
| 2 | `docs/ARCHITECTURE.md:459` | `Android（Kotlin，~400 行）` | `Android（Kotlin，约 1557 行）` | 实测 5 个 .kt 文件 1557 行（含 `b7e47f0` 起每一历史版本都远超 400） |

两处都只改数字/事实，未动任何可执行代码与实验报告正文。

---

## 需人工决定清单

1. **verify.py:10 「三种」工具会撒谎的形态**（#17）—— 与 ARCHITECTURE「五种」、E12「第八种」、E14「第 10、11 例」口径不一。这是同一种计数的口径漂移，不是单一出处。建议统一计数口径后改，**我没有改**。
2. **ARCHITECTURE.md:500 「9/79 命中」**（#76）—— 9/79 可推导自 E16 分组表（S+M=79 次 9 命中），但行内引用标注的是 E15（其数为 5/30）。**未改**，需要作者确认引用该指向 E16。
3. **README.md:12 「7 步」** 与 E12 的「12 步（含 3 次 wait）」步数口径不同 —— 一个数 step 目录、一个数含 wait 的规划步。README 引用的 trajectory 确实是 7 步，不算错，但读者对比 E12 时会对不上。
4. **docs/README.md:41 E10 行**仍写「归还只降概率不消除」，与 E11 的 0/20 相悖（#99）—— 改索引需要重述摘要结论，超出「只换数字」范围，留人工决定。
5. **CLAUDE.md:50 「见过 2/3/4/6」**（#54）—— 与 EXPERIMENTS/observe/HARNESS-SPEC 的「2/4/5/6」不一致。3 有 E14 实例、5 无；若以文档族多数为准应是 2/4/5/6。**未改**（CLAUDE 里 3 也有出处），留给作者定。
6. **compress.py:138 / HARNESS-SPEC:395 「20 次是常态」**（#21）—— 无任何实测依据，样本最大重复 10。若保留应补一句「经验值非实测」，或改成实测过的数字。**未改**。
7. **README.md:49 「scrcpy ≥ 3.0」**（#33）—— 外部工具版本要求，仓库内无证据，也不该有（这是安装要求）。保留合理。
8. **verify.py:107-108 「4/4 邮件正文完全正确」**（#20）—— 四例判 FAIL 可数到，但「邮件正文完全正确」只有 E12（16-51-30）有人工确认；其余三例（16-10-17/23-21-54/23-32-27）无独立收件箱验证。**这句的强度和证据不匹配，建议收紧或补充。**

---

## 限度

- **没有**删减优先级的让步：六类文件（harness/*.py、*.kt、README、CLAUDE、ARCHITECTURE、HARNESS-SPEC+DEMO+harness/README+docs/README）全部审完。
- **runs/** 只读了 2026-08-06T16-10-17 / 16-51-30 / 23-21-54 / 23-32-27 / 2026-08-07T03-52-37 / 04-37-08 / 05-42-53 / 05-52-07 / 2026-08-05T23-* 用于核 verify.py 与 DEMO 的断言；其余早期 trajectory 未逐一核对（那些不是文档引用的出处）。
- `docs/随手记.md` 按 brief §6 #4 未审、未引。
- Kotlin 侧 15 条测试实际跑过（`--rerun-tasks`，BUILD SUCCESSFUL）；Python 79 条实际跑过（OK）。两处输出见文末。
- 单条超过 15 分钟即放弃的规则未触发（每处都可定位或可明确说「找不到」）。

---

## 测试输出

```
$ python -m unittest discover -s tests -q
----------------------------------------------------------------------
Ran 79 tests in 0.385s

OK
```

```
$ cd android && ./gradlew :app:testDebugUnitTest --rerun-tasks
BUILD SUCCESSFUL in 12s
# 测试 XML：tests=1 (ExampleUnitTest) + 8 (LocatorResolverTest) + 1 (ProbeMockTest) + 5 (TreeHashTest) = 15，failures=0 errors=0
```
