# harness — Agent 侧实现

按 `../docs/HARNESS-SPEC.md` 实现；冲突处以 `../docs/ARCHITECTURE.md` 为准。

```
PC (Python)                                  Android (Kotlin)
harness/                                     app/src/main/java/com/example/phoneagent/
  config.py     常量（护栏项无开关）            AgentServer.kt      LocalServerSocket + 行协议
  models.py     数据类                         AgentCommands.kt    state/observe/act/probe
  transport.py  短连接 socket 客户端    <--->   Snapshot.kt         遍历/属性/tree_hash
  adbutil.py    dumpsys 交叉校验（另一条链路）   LocatorResolver.kt  L1–L6 解析 + target 规则
  tree.py       树重建 + hash 本地复算         AgentAccessibilityService.kt  服务 + 旧广播指令
  compress.py   锚点合并 + locator 生成
  verify.py     判据推断 + 三态
  observe.py    状态自检 + observation 组装
  planner.py    LLM（唯一的策略层模块）
  loop.py       编排
  cli.py        入口
```

## 跑起来

```bash
# 1. 副屏（虚拟屏随 scrcpy 进程消亡，别关这个窗口）
scrcpy --new-display

# 2. 装服务，然后去「设置 → 无障碍」把 Phone Agent 打开
#    ⚠ 改过代码就必须关掉再打开，否则跑的是旧实例
cd android && ./gradlew :app:installDebug

# 3. 通道（设备重连后失效，需重跑；cli 每次会自动补一次）
adb forward tcp:8760 localabstract:phoneagent

# 4. 分阶段自验（HARNESS-SPEC §10）
python -m harness.cli selftest                          # 离线，79 条，不需要设备
python -m harness.cli state                             # 阶段 1
python -m harness.cli observe --locators                # 阶段 2/3
python -m harness.cli act --sid 5 --action click        # 阶段 4/5，不经过 LLM
python -m harness.cli run "在设置中关闭深色主题" --verbose  # 阶段 8
```

**阶段 4 单独测**：locator 在设备侧的解析要和 loop 分开调，混在一起时失败原因会缠在一块。
`cli act` 就是为这个准备的 —— 它打印 locator、下发、独立重读、给出 verdict，全程不碰 LLM。

## LLM 后端

零第三方依赖（urllib 直连）。

| provider | 环境变量 | 说明 |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | 默认 |
| `openai` | `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` + `--base-url` | OpenAI 兼容端点（DeepSeek / Qwen / 本地 vLLM）。**不传 base-url 会把 key 发去 api.openai.com 然后 401** |
| `rule` | 无 | 按标签走的固定规则，sid 每轮现查（ARCHITECTURE §2「小参数量模型」那一档） |
| `scripted` | 无 | `--script '[{"action":"click","target":2}]'`，没有 key 也能跑通 loop 与落盘 |

```bash
PHONEAGENT_LLM_PROVIDER=openai PHONEAGENT_MODEL=deepseek-chat \
PHONEAGENT_BASE_URL=https://api.deepseek.com \
python -m harness.cli run "在设置中关闭深色主题"
```

## 护栏与策略的边界

护栏在代码里是**写死的**，不是配置项：

- `loop.py` 里 `restore=True` 硬编码 —— 能关掉的护栏不是护栏
- 每步都独立 `probe` 重读，不复用 `act` 响应里的 `post_state`（后者只用于对照，不一致会记进日志）
- 焦点归还额外走 `dumpsys` 交叉校验，刻意不复用产生该结果的 a11y 链路
- 归还失败必须出现在下一轮 observation 里（`⚠`），不得静默

策略层只有 `planner.py`：动作选择、绕路、礼貌等级（`POLITENESS`，决定 LLM 能不能用 `wait`）、
完成判定。换模型只改这里。

## 与 SPEC 的两处有意偏离

1. **设备侧不使用 framework 的 `find*` API**，改为在与 `observe` 同一次遍历上做精确匹配。
   `findAccessibilityNodeInfosByText` 是子串匹配、且同时命中 `contentDescription`，
   返回顺序也无文档保证；而 L5 的 `index` 是 PC 侧按 `observe` 的 idx 序算的。
   两侧必须同规则，否则 index 指向别的节点 —— 静默点错，最难查的那种。

2. **`descendant_class` 先归位到容器再向下找**。裸 Switch 的文字在兄弟 TextView 上，
   直接从文字节点向下 BFS 永远找不到它。锚点不可交互时先爬到最近的可交互祖先（整行），
   再从行里按 class 找。

## 已验证 / 未验证

离线（`selftest`，79 条）覆盖：locator 生成→解析的闭环（L1–L6 各一条以上）、
整行与开关必须分成两条、空 EditText 的 hint 不当作内容、判据三态（含
「哑动作」连续 FAIL 触发中止、「界面毫无变化」独立触发中止）、致命异常时一个动作都不发、
归还失败必须上报、LLM 输出解析与重试、trajectory 落盘完整性、
被成功的写入作废的定位器只能判 UNKNOWN（并从独立重读的树里找回写入值）、
条目增删标记（整页换掉时不报）、token 与延迟汇总缺失时记 None 不记 0。

设备侧另有 15 条 JVM 单测（`cd android && ./gradlew :app:testDebugUnitTest --rerun-tasks`，
⚠ 不加 `--rerun-tasks` 会命中缓存，`BUILD SUCCESSFUL` 但一条都没跑）。
其中真正有覆盖意义的是 13 条：`LocatorResolver` 8 条 + `Snapshot.treeHash` 5 条；
另两条是 `ProbeMockTest`（探路：能不能 mock `AccessibilityNodeInfo`）与模板自带的 `ExampleUnitTest`。
`AgentCommands` / `AgentServer` 仍无测试 —— 它们依赖真实 Service 生命周期。

**没有真机验证**：本机无设备。以下必须上机再确认 ——
`observe` 的 512 KB 降级路径、`act` 的 11 步时序在真实窗口重建下的表现、
`BACK` 的跨屏语义（代码里已标注为未验证）、`dumpsys` 焦点交叉校验的正则在目标
Android 版本上的匹配。设备侧的解析器是与 `tests/fake_device.py` 同语义的两份实现，
离线闭环只能证明规则自洽，证明不了真机行为。
