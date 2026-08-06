# WellPhone · 手机 Agent

在**副屏**上自主操作 Android 应用的 Agent，验收标准只有一条：

> **用户当前正在进行的交互不被中断。**

以「用户在主屏持续打字」作为最严苛的验证场景 —— 它对焦点的依赖最强。

## 为什么这不是一个普通的 GUI Agent

Android 的无障碍框架在**动作分发路径**上绑定了单焦点语义：任何通过 a11y 发出的动作，
都会把全系统唯一的 window 焦点夺到目标窗口。所以 Agent 的每个动作有三重后果 ——
改变目标状态（正常）、打断用户输入（打扰）、**用户的击键灌进 Agent 自己的工作区**（正确性故障）。

因此 loop 里有两个常规 Agent 没有的环节：**补偿**（焦点归还，与动作原子绑定）
与**再观测**（不信任动作前的世界模型，也不信任工具的返回值）。

## 目录

```
docs/       设计（ARCHITECTURE / HARNESS-SPEC）与实测记录
android/    AccessibilityService —— 只做感知与执行
harness/    PC 侧 Agent —— 规划 / 压缩 / 定位 / 验证 / 编排
tools/      离线小工具
tests/      离线测试，不需要设备
```

- 先读 [`docs/README.md`](docs/README.md) —— 文档索引与阅读顺序
- 想直接跑：[`harness/README.md`](harness/README.md)

```bash
python -m harness.cli selftest   # 离线自测，不需要设备
```

**状态**：仅在模拟器 API 34 上验证，未在真机复现。
