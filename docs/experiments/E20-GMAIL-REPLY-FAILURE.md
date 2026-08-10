# E20 · 一次真实任务失败的归因：整行被行内头像挤掉了

**日期** 2026-08-09 · **标签** `[真实任务]` · API 34 · 模拟器 · display 4 · Gmail
**任务** 「我的朋友 Yiduo 好像给我的 Gmail 发了封邮件，你能帮我回复他一下吗？」
**模型** `deepseek-v4-flash`
**trajectory** `runs/2026-08-09T18-36-02`（失败）· `18-51-51`（仍失败）· `18-58-14`（成功）

---

## 1 · 现象

任务失败，10 步后 agent 判 `impossible`。表面看是护栏太狠：9 步里 7 个目标被
打扰窗口预算拉黑，包括 `Compose` / `To` / `Navigate up` / 邮件本身。

**这个归因是错的。** 它是第二个问题，不是失败的原因。

## 2 · 真因：agent 从头到尾没打开过那封邮件

第一步 `click 邮件` 之后，新出现的条目是：

```
[8] Done  [9] Archive  [10] Delete  [11] Mark read  [12] More options
```

**那是 Gmail 的「选中模式」工具栏，不是阅读界面。** 阅读界面应该有正文、发件人、
`Reply` / `Forward`。而 step-02 点开的 `More options` 弹出的是
`Move to / Snooze / Change labels / Add star / Mute / Report spam` ——
**选中模式的溢出菜单，里面本来就没有回复入口。**

agent 此后一直在勾选与取消勾选之间打转，直到步数耗尽。

locator 说明了一切：

```
strategy: L4  text="Unread, , , Wang, Yiduo, …"  cls=android.view.ViewGroup
target:   descendant_class:android.widget.ImageView
resolved: com.google.android.gm:id/contact_image      ← 联系人头像
```

**点的是头像。Gmail 里点头像 = 勾选，点整行 = 打开邮件。**

## 3 · 为什么压缩层会选中头像

`compress.py` 第 ③ 步去重：共享同一锚点、且 `kind` 相同的候选只留一条，
旧规则是「留最内层（depth 最大）」。

这一行里：

| 节点 | 文字 | kind | 与锚点的关系 |
|---|---|---|---|
| 整行 `ViewGroup` | **自带** contentDescription | button | **主人** |
| 头像 `ImageView` | 无任何文字 | button | **借用**整行的锚点 |

同锚点、同 kind → 落进同一个槽 → 留最内层 → **整行被头像挤掉**。

写在注释里的那道防线（「kind 不同的一律都留」）挡住的是 Settings 那个坑
（整行 button vs 开关 switch，kind 不同）。**这一组 kind 相同，防线没覆盖。**

> 与 `ARCHITECTURE §4` 记的是同一类：**同一段文字，两种完全不同的行为。**
> 只是这次两者的 `kind` 恰好一样，于是漏了过去。

### 修法

去重时加一条**优先于 depth** 的判据：

> **锚点的主人优先于借用者。** 自己就带着那段文字的节点，才是这段文字描述的东西；
> 借用别人文字的节点只是它的一部分。双方都是借用者时，才比 depth 留最内层。

Settings 那行不受影响：它的文字在**不可交互的 TextView** 上，整行与外层包装
都是借用者，此时最内层才是真正能执行的那个。

## 4 · 三次跑的对照（这才是归因的依据）

两个修复分两次上，中间那次是关键 —— 它把两个问题**干净地分开了**。

| # | 打扰预算 | 压缩去重 | 步数 | 结果 |
|---|---|---|---|---|
| `18-36-02` | 旧（无条件拉黑） | 旧 | 10 | 拉黑 7 个目标 → `impossible` |
| `18-51-51` | **新**（仅在用户可能输入时拉黑） | 旧 | 20 | **零拉黑**，仍在勾选里打转 → `aborted: TIMEOUT` |
| `18-58-14` | 新 | **新** | **4 个动作** | **`done`** |

**中间那一行证明了预算不是真因**：动作空间完整保留、步数翻倍，失败照旧。

成功那次：

```
1. click ", , , Wang, Yiduo, …"  → 界面内容已变化        ← 真的打开了
2. click "Reply"                 → activity → FrameLayout
3. set_text 正文                 → PASS
4. click "Send"                  → activity → MailActivityGmail
5. finish → done
```

> **`Reply` 这个条目在之前所有 run 里从未出现过** —— 因为从来没有一次进到阅读界面。
> 它的出现本身就是「这次真的打开了邮件」的独立证据。

## 5 · 附带暴露的一条判据限度

`activity_or_tree_changes` 判据在 step-01 给的是 **PASS**（`activity → ViewGroup`）。
读数没错 —— 界面**确实**变了。它变成了选中模式。

> **这条判据证明的是「变了」，不是「变成了我要的那个」。**

这是它的固有限度，不是 bug：harness 不要求 LLM 声明预期，也就无从校验意图。
但它意味着**一串 PASS 不能用来证明任务在推进** —— 本次前 5 步全是 PASS，
而其中一步都没接近目标。已写进 `ARCHITECTURE §3.4`。

## 6 · 两条方法论教训

1. **证据当时就在 observation 里，被读过去了。** `Done / Archive / Delete / Mark read`
   五个按钮一起出现，是选中模式的明确指纹。看到 `PASS` 就认为"打开了"，
   正是这个仓库反复警告的那种错：**读数看着合理、且正好支持预期的结论。**
2. **弱模型没做错任何决策。** `deepseek-v4-flash` 每一步都在合理应对一个被观测层
   误导的世界。强模型可能靠常识猜到"要点行不要点头像"，从而**把这个 bug 一直盖着** ——
   又一次印证 E13 §6：harness 的质量应该由弱模型来检验。

## 7 · 限度

- 三次 run 各 n=1。三者条件（app / 任务 / 模型 / 主屏内容）一致，但不是重复实验。
- 只在 Gmail 会话列表这一种布局上验证。**「主人优先于借用者」这条规则在别的 app
  上会不会误伤，没有测过** —— 离线的 88 条测试只能证明它与现有契约自洽。
- 成功那次没有独立核对「邮件是否真的出现在收件人处」，只核到 `Send` 已生效、
  activity 回到收件箱。
