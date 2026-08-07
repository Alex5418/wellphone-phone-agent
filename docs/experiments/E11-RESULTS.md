# E11 · 中文 composing 打断的 2×2 矩阵重跑

**日期** 2026-08-06 · **标签** `[非root可复现]` · API 34 · 模拟器 · scrcpy VirtualDisplay · Gboard 拼音
**脚本** `tools/exp_composing_matrix.py` · **原始数据** `docs/experiments/E11-raw.jsonl`（125 行）
**分支** `exp/e11-composing-matrix`

E10 的四格结论每格只有 1–4 次样本、且约一半 run 因起点丢字作废。本任务把四格重跑
到每格 ≥20 次**有效**运行，并把起点丢字问题修掉（就绪校验）。只补数据，不做因果解释。

---

## 0 · 测量工具验证（起点丢字修复）

按 SUBTASK-E11 陷阱 1：清场 → 点 Body → 就绪校验（IME 弹着 → 打 `a` 落 1 字 →
退格清 0）→ 正式打 `zhonghuaren`。连续 10 次全部得到 `zhong hua ren`：

```
[1] 'zhong hua ren'  OK
[2] 'zhong hua ren'  OK
[3] 'zhong hua ren'  OK
[4] 'zhong hua ren'  OK
[5] 'zhong hua ren'  OK
[6] 'zhong hua ren'  OK
[7] 'zhong hua ren'  OK
[8] 'zhong hua ren'  OK
[9] 'zhong hua ren'  OK
[10] 'zhong hua ren'  OK
10/10 全部得到 zhong hua ren
```

## 1 · 阳性对照（nav × restore=false，前 5 次有效）

| n | before | after | 打断 |
|---|---|---|---|
| 2 | `zhong hua ren` | `zhonghuarenmin` | ✓ |
| 3 | `zhong hua ren` | `zhonghuarenmin` | ✓ |
| 4 | `zhong hua ren` | `zhonghuarenmin` | ✓ |
| 16 | `zhong hua ren` | `zhong hua ren min gu` | ✗ |
| 19 | `zhong hua ren` | `zhong hua ren min gu` | ✗ |

**3/5 打断 ≥ 3/5 → 测试台是活的，继续跑完整矩阵。**

---

## 2 · 主表（每格 ≥20 次有效运行）

| 副屏动作 | restore | 有效运行数 | 打断次数 | 打断率 | 作废次数 | 作废原因 |
|---|---|---|---|---|---|---|
| scroll | false | 20 | 0 | **0%** | 14 | 就绪失败 点 Body 后无焦点 ×14 |
| scroll | true | 20 | 0 | **0%** | 0 | — |
| nav | false | 20 | 10 | **50%** | 12 | 就绪失败 ×7；TransportError NO_DISPLAY ×5 |
| nav | true | 20 | 0 | **0%** | 9 | 就绪失败 ×5；TransportError（TIMEOUT/EMPTY）×4 |

**打扰窗口（每次 act 的 `disturb_ms` 逐次记录，有效运行内全部动作）**：

| 副屏动作 | restore | 中位数 | 最小 | 最大 | n |
|---|---|---|---|---|---|
| scroll | false | 4 ms | 1 | 59 | 60 |
| scroll | true | 101 ms | 13 | 2120 | 60 |
| nav | false | 12 ms | 3 | 32 | 59 |
| nav | true | 130 ms | 28 | 1255 | 56 |

> `restore=true` 的 disturb_ms 含归还焦点的时间，量级显著大于 `restore=false`，与 E9/E10 一致。

---

## 3 · 四格分节

### 3.1 scroll × restore=false · 打断 0/20

```json
{"n":3,"action":"scroll","restore":false,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[7,41,3],"valid":true}
{"n":19,"action":"scroll","restore":false,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[15,4,1],"valid":true}
{"n":35,"action":"scroll","restore":false,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[6,59,2],"valid":true}
```

肉眼观察：滚动从不打断 —— 20 次里 `after` 全是 `zhong hua ren min gu`（空格 2→4，
续打的 `mingu` 也完整进入同一 composing 段）。

### 3.2 scroll × restore=true · 打断 0/20

```json
{"n":2,"action":"scroll","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[20,60,292],"valid":true}
{"n":12,"action":"scroll","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[168,388,112],"valid":true}
{"n":21,"action":"scroll","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[588,472,41],"valid":true}
```

肉眼观察：同 3.1，`restore` 是否归还对滚动结果无影响，20/20 全程 composing。

### 3.3 nav × restore=false · 打断 10/20（50%）

```json
{"n":2,"action":"nav","restore":false,"before":"zhong hua ren","after":"zhonghuarenmin","sp_before":2,"sp_after":0,"broke":true,"disturb_ms":[18,23,11],"valid":true}
{"n":26,"action":"nav","restore":false,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[18,22,7],"valid":true}
{"n":36,"action":"nav","restore":false,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[19,7,8],"valid":true}
```

肉眼观察：打断时 `after` 里分段空格全消失（sp 2→0），且末尾多出一个新的 composing
段；未打断时空格保留（2→4）。**同一组里两种情况都出现，不是全部必断。**

> ⚠ 与 E10「nav×false 3/3 必断」不一致：本次 n=20 测得 50%（10/20）。
> 方向（nav 会打断）仍在，但概率远低于 E10 小样本给出的印象。不加解释，如实记录。

### 3.4 nav × restore=true · 打断 0/20

```json
{"n":2,"action":"nav","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[None,40,207],"valid":true}
{"n":12,"action":"nav","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[122,145,262],"valid":true}
{"n":31,"action":"nav","restore":true,"before":"zhong hua ren","after":"zhong hua ren min gu","sp_before":2,"sp_after":4,"broke":false,"disturb_ms":[1255,None,164],"valid":true}
```

肉眼观察：20/20 全程 composing 完好，`after` 全是 `zhong hua ren min gu`。

> **特别标注（SUBTASK-E11 规则）**：nav×restore=true 打断率 **0/20 = 0%**，
> **不在 20%–80% 区间**，按任务规则**不补跑额外 10 次**。0/20 与 E10 的 1/3 不一致
> （E10 该格自己标注过"最不准"）。这一格的结论是：本环境、本样本量下归还**一次都没破**，
> 与 nav×false 的 10/20 形成明显分界。不做因果解释。

### 3.5 方向相反检查

四格均未出现与 E10 方向相反的结果（scroll 两格仍 0/20 不打断；nav 仍会打断）。
nav×false 从 E10 的 3/3 变成 50% 属于**概率下移**而非方向反转，不触发复现验证，
已在 3.3 单独标注。

---

## 4 · E11-2 · 打断后点回输入框能否恢复

**做法**：nav × restore=false 条件下制造打断 → 点一下主屏输入框（模拟用户补救）→
打 `guo` → 记录最终文字与分段空格数。跑 10 次。

**结果**：10 次里 5 次确实打断了（`断=True`）。**无论断没断，点回输入框后
IME 都没有再弹出来（`ime_back=false`），`guo` 一个字母都没落进去（`guo_landed=false`）**：

| n | 断 | 点回 | IME 弹回 | guo 落地 | before | 断后 | 补救后 |
|---|---|---|---|---|---|---|---|
| 3 | ✓ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhonghuarenmingu` | `zhonghuarenmingu` |
| 11 | ✓ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhonghuarenmingu` | `zhonghuarenmingu` |
| 12 | ✓ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhonghuarenmingu` | `zhonghuarenmingu` |
| 13 | ✓ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhonghuarenmingu` | `zhonghuarenmingu` |
| 14 | ✓ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhonghuarenmingu` | `zhonghuarenmingu` |
| 2 | ✗ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhong hua ren min gu` | `zhong hua ren min gu` |
| 15 | ✗ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhong hua ren min gu` | `zhong hua ren min gu` |
| 16 | ✗ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhong hua ren min gu` | `zhong hua ren min gu` |
| 18 | ✗ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhong hua ren min gu` | `zhong hua ren min gu` |
| 19 | ✗ | ✓ | ✗ | ✗ | `zhong hua ren` | `zhong hua ren min gu` | `zhong hua ren min gu` |

原始数据（10 行，逐条）：
```json
{"n": 2, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhong hua ren min gu", "final": "zhong hua ren min gu", "sp_before": 2, "sp_break": 4, "sp_final": 4, "broke": false, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [null, 9, 8]}
{"n": 3, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhonghuarenmingu", "final": "zhonghuarenmingu", "sp_before": 2, "sp_break": 0, "sp_final": 0, "broke": true, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [36, null, 7]}
{"n": 11, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhonghuarenmingu", "final": "zhonghuarenmingu", "sp_before": 2, "sp_break": 0, "sp_final": 0, "broke": true, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [20, 16, 10]}
{"n": 12, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhonghuarenmingu", "final": "zhonghuarenmingu", "sp_before": 2, "sp_break": 0, "sp_final": 0, "broke": true, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [21, null, 9]}
{"n": 13, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhonghuarenmingu", "final": "zhonghuarenmingu", "sp_before": 2, "sp_break": 0, "sp_final": 0, "broke": true, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [31, 9, 14]}
{"n": 14, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhonghuarenmingu", "final": "zhonghuarenmingu", "sp_before": 2, "sp_break": 0, "sp_final": 0, "broke": true, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [44, null, 11]}
{"n": 15, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhong hua ren min gu", "final": "zhong hua ren min gu", "sp_before": 2, "sp_break": 4, "sp_final": 4, "broke": false, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [27, null, 3]}
{"n": 16, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhong hua ren min gu", "final": "zhong hua ren min gu", "sp_before": 2, "sp_break": 4, "sp_final": 4, "broke": false, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [null, 10, 9]}
{"n": 18, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhong hua ren min gu", "final": "zhong hua ren min gu", "sp_before": 2, "sp_break": 4, "sp_final": 4, "broke": false, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [null, 8, 18]}
{"n": 19, "tag": "e11-2", "before": "zhong hua ren", "after_break": "zhong hua ren min gu", "final": "zhong hua ren min gu", "sp_before": 2, "sp_break": 4, "sp_final": 4, "broke": false, "tapped": true, "ime_back": false, "guo_landed": false, "disturb_ms": [null, 9, 40]}
```

**现象（只记录，不解释）**：
1. 打断后点回输入框，IME 在 4 秒轮询内没有再弹出来，`guo` 无法输入 —— **无法恢复**。
2. 连**没打断**的 run（composing 完好）点回后 IME 同样不弹回来 ——
   说明 `restore=false` 的导航动作之后，主屏输入会话在本环境下整体终结，
   点回输入框不足以恢复 IME。这一格与 E9「按机制推断不能恢复」方向一致，但观测到的
   现象更彻底（连键盘都回不来）。**未做任何"修复"，按现象记录。**

---

## 5 · 数据质量与作废

- 作废集中在两类：① 就绪失败（`点 Body 后无焦点`）—— 中途修过一次渲染等待
  （等输入框出现再点），scroll×true 那一格修好后 0 作废；② `TransportError
  NO_DISPLAY / TIMEOUT / EMPTY` —— 副屏窗口切换竞态与一次 system_server 重启
  （14:35 `DeadSystemException`，已按环境重建步骤恢复）。
- 所有作废 run 都写入 `E11-raw.jsonl` 并标 `valid:false`，未丢弃。
- 判定打断只用**拼音分段空格数**（`sp_before`/`sp_after`），未用截图/候选条/a11y 焦点。

## 6 · 适用条件

`[非root可复现]` · API 34 · 模拟器（emulator-5554）· Gboard 拼音 · scrcpy VirtualDisplay
（本次 display 3 → system_server 重启后变 2）· composetest 应用。
