# D2 · 真实 LLM 端到端运行（deepseek-v4-flash）

**日期** 2026-08-06 · **标签** `[非root可复现]` · API 34 · scrcpy VirtualDisplay
**模型** `deepseek-v4-flash`（OpenAI 兼容端点，urllib 直连，零 SDK 依赖）
**副屏** display 2 · com.android.settings · **主屏** display 0 · Chrome / composetest
**trajectory** `trajectories/D2-llm-screen-timeout/`、`D2-llm-wait-then-act/`、`D2-llm-blocked-target/`

D1 的策略层是规则脚本；这次换成真实模型，护栏一行没改
（ARCHITECTURE §2「换模型只改缝的位置，不改护栏」的一次实证）。

---

## 1 · 三个任务的结果

| 任务 | 结果 | 步数 | 独立验证 |
|---|---|---|---|
| 把屏幕超时时间设置为 30 秒 | ✅ done | 3 | `settings get system screen_off_timeout` = **30000** |
| 把屏幕超时时间改成 1 分钟 | ✅ done | 3（含 1 步 wait） | = **60000** |
| 关闭深色主题 | ⛔ impossible | 1 | 开关未被触碰 |

验证一律用 `adb shell settings get` 独立读取，不采信 loop 自己的判定。

## 2 · 礼貌层：模型自己选择了让路

第二个任务开始时主屏 composetest 持有输入焦点、软键盘弹起，
observation 里是 `- 用户输入中: 是`。模型第一步输出：

```json
{"thought": "用户正在输入，先等待让路，避免干扰", "action": "wait", "target": null}
```

`wait` 是**策略层**能力（`POLITENESS` 可配置关闭），归还护栏与它无关 ——
两层的分工在真实模型上按设计跑出来了。

## 3 · 归还：第三个数据点（Compose 主屏）

| 场景 | 打扰窗口 | 重解析 | ACTION_FOCUS |
|---|---|---|---|
| 主屏 Chrome（有 resource-id） | 12 ms | — | — |
| 主屏 composetest（**Compose，无 id**） | **313 ms** | 286 ms | 27 ms |
| 全局配置变更（Activity 重建） | 2526–3191 ms | 2962 ms | 225 ms |

新发现：**打扰窗口还取决于主屏焦点节点能不能被 id 直接定位。**
Compose 应用没有 resource-id，归还只能走「按 class 扫树 + findFocus 兜底」，
比 id 路径贵一个数量级（286 ms vs ~10 ms），但仍在 500 ms 预算内，未触发排除。

这给 C2 的结论补了一面：Compose 的可指认率不成问题，**但归还路径要为"没有 id"付钱**。

归还结论由设备与 dumpsys 双链路一致确认（`confirmed_by: device`，dumpsys 复核相同）。

## 4 · 护栏拦住模型的完整过程

第一次跑「关闭深色主题」时静态名单**漏了**：子页面顶部的主开关条标签是
`Use Dark theme`，节点是 `LinearLayout`、`kind=button`、没有 On/Off 状态 ——
只看 kind 拦不住。实测预算兜住了它（1533 ms > 500 ms 预算），但代价是先付了一次。

收紧后（`policy.is_toggle_like` 增加 resource-id 与 On/Off 状态两个信号，
`settingslib_main_switch_bar` 这类 id 直接判定为开关），模型的反应是：

```
[plan] finish :: 关闭深色主题的唯一控件是 Use Dark theme 开关，但它被标记为不可操作
                 且会触发全局配置变更，没有其他可用的替代入口，因此任务无法完成。
=== impossible ===
```

一步收尾，理由准确。这印证了「排除项要**呈现**给 LLM 而不是藏起来」——
藏起来它只会一直找；给出理由，它能据此判定任务不可行。

## 5 · 顺手修掉的四个问题（都是真机才暴露的）

| 现象 | 根因 | 处置 |
|---|---|---|
| 点进子页面的瞬间整个 run 被判「副屏消失」而中止 | 窗口切换的过渡态里 display 上一个窗口都没有，被当成"副屏没了" | observe 带重试（3×250 ms），重试后仍空才当真 |
| 解析失败那一步 trace 里连 `llm_raw.txt` 都没有 | 只在成功路径落盘 | `PlannerError` 携带原始输出；失败步同样落盘，并记进 history 让下一轮模型知道 |
| 报「输出里找不到 JSON 对象」，实际是被截断 | 推理模型的思考过程走 `reasoning_content`，**同样吃 max_tokens**；1024 时 `content` 直接是空字符串 | 识别 `finish_reason=length` 并如实报「被 max_tokens 截断」；预算提到 4096/8192 |
| 任务做不成也报 `status=done` | 收尾被等同于成功 | 输出增加 `outcome: achieved / impossible`，run 状态区分 `done` 与 `impossible` |

第三条又是同一个模式：**仪表的失败被说成了被测对象的失败** ——
报「模型格式不对」会让人去改提示词，而真正的问题在 token 预算。
（通则见 ARCHITECTURE §3.4「所有仪表都是三值的」。）

## 6 · 成本

| 指标 | 值 |
|---|---|
| LLM 单步延迟 | 1.7–3.3 s |
| 单步 completion tokens | 239（其中 reasoning 175） |
| 一个 3 步任务 | 约 3 次调用 |

打扰窗口（12–313 ms）比 LLM 延迟（约 2 s）小一到两个数量级 ——
**用户感知到的中断由归还决定，不由模型快慢决定。** 这也是护栏与策略分层的实际收益：
策略层再慢，也不会因此多打扰用户一分。

## 7 · 仍未验证

- 打扰窗口期间**真实击键的落点**（两次运行主屏都没有持续输入，仍未实测丢字）
- `observe` 的 512 KB 降级路径
- `BACK` 的跨屏语义
- 真机（非模拟器）
