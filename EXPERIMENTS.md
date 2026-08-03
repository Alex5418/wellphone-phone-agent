# EXPERIMENTS.md

> 本文件是 R1–R5 假设验证的**原始记录**：命令、原始输出、结论，按时间顺序堆积。
> README 只引用不复述。答辩时直接开着这份文件讲。
>
> 记录原则：**失败也记，尤其记失败**。"我做了 A/B/C 三个实验，发现 B 不成立，所以选了 C"
> 比"我做出来了"更有说服力。搞不定的部分，记录尝试了什么、卡在哪里。

---

## 假设总表

| # | 假设 | 状态 | 结论摘要 |
|---|---|---|---|
| **R1** | 能创建用户看不见的屏，并在上面启动 app | ⬜ 未开始 | |
| **R4** | 目标 app 节点树质量够用（有 text/id，且 action 不哑） | ⬜ 未开始 | |
| **R2** | 无障碍服务能读到副屏节点树 | ⬜ 未开始 | |
| **R3** | `ACTION_CLICK` / `SET_TEXT` 不抢主屏焦点和键盘 | ⬜ 未开始 | **生死线** |
| **R5** | LLM 能基于压缩后的节点树做出靠谱规划 | ⬜ 未开始 | |

状态图例：⬜ 未开始 · 🟡 进行中 · ✅ 通过 · ⚠️ 部分通过（有绕过方案） · ❌ 失败（已换路线）

---

## E0 — 环境搭建（D1）

**日期**：2026-08-03
**目的**：拿到一台可 root、可多屏、Android 14 的设备，作为 R1–R5 的实验台。

### 约束回顾

无实体 Android 机（仅 iOS）→ 只能用 AVD。WSA 已于 2025-03-05 终止服务，不可用。
镜像必须是 **Google APIs 或 AOSP**，不能带 Play 商店 —— 生产签名镜像拿不到 `adb root`，
而 R1 的多个备选出路（改 system prop、`screencap` 指定 display）都依赖 root。

### 环境清单

| 项 | 值 |
|---|---|
| 宿主 | Windows 11 Pro 26200 · AMD Ryzen 5 5600X |
| 加速 | WHPX(10.0.26200) is installed and usable |
| SDK | `C:\Users\76982\AppData\Local\Android\Sdk` |
| 镜像 | `system-images;android-34;google_apis;x86_64` |
| AVD 名 | `wellphone_a14` |
| 设备档 | Pixel 6 · 1080×2400 · density 420 |

> 备注：Android Studio 初装只带了 `platforms;android-37.0`，**没有任何系统镜像，也没有
> `cmdline-tools`**（即没有 `sdkmanager` / `avdmanager`）。需手动补装。

### 关键 AVD 配置（`~/.android/avd/wellphone_a14.avd/config.ini`）

```ini
PlayStore.enabled=no          # 决定 adb root 能否成功
hw.keyboard=yes               # 宿主键盘直连主屏 —— 演示"用户持续打字光标不跳"的前提
hw.hotplug_multi_display=yes  # R1 需要运行时挂载副屏
hw.multi_display_window=yes   # 副屏独立开窗，一个镜头可同时拍主屏与 Agent 屏
hw.ramSize=4096
hw.cpu.ncore=4
hw.gpu.enabled=yes
hw.gpu.mode=host
showDeviceFrame=no
```

`hw.keyboard=yes` 是容易漏的一条：默认 `no` 时宿主键盘敲不进模拟器，
而"用户在主屏持续打字"正是本题验收 R3 的核心动作，没有它整个演示做不出来。

### 复现步骤

```powershell
# 1. 补装命令行工具（Android Studio 不带）
#    下载 https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip
#    解压后放到 $SDK\cmdline-tools\latest\

$env:JAVA_HOME  = "C:\Program Files\Android\Android Studio\jbr"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$sm = "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat"
$am = "$env:ANDROID_HOME\cmdline-tools\latest\bin\avdmanager.bat"

# 2. 装镜像与平台
& $sm --licenses            # 全部 y
& $sm "platform-tools" "platforms;android-34" "system-images;android-34;google_apis;x86_64"

# 3. 建 AVD
& $am create avd -n wellphone_a14 -k "system-images;android-34;google_apis;x86_64" -d pixel_6

# 4. 按上表改 config.ini

# 5. 启动
& "$env:ANDROID_HOME\emulator\emulator.exe" -avd wellphone_a14 -gpu host -writable-system
```

### 配 PATH（Android Studio 不会自动做）

装完 Android Studio 后在 cmd 里敲 `adb` 是**没反应**的 —— Studio 调用 SDK 工具走绝对路径，
从不写系统 PATH。D1–D3 要大量敲 `adb shell dumpsys`，必须先配上。

⚠️ **别用 `[Environment]::SetEnvironmentVariable('Path', ..., 'User')`**：
本机 user PATH 的注册表类型是 `REG_EXPAND_SZ` 且含 `%USERPROFILE%`，
该 API 读出来是**已展开**的值，写回时会把变量固化成绝对路径，类型也退化成 `REG_SZ`。
正确做法是直连注册表并显式保持 `ExpandString`：

```powershell
$reg = Get-Item 'HKCU:\Environment'
$raw = $reg.GetValue('Path','','DoNotExpandEnvironmentNames')   # 关键：不展开
# ... 备份 $raw ...
$add = @(
  '%LOCALAPPDATA%\Android\Sdk\platform-tools'
  '%LOCALAPPDATA%\Android\Sdk\emulator'
  '%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest\bin'
)
$new = (($raw -split ';' | Where-Object {$_ -ne ''}) + $add) -join ';'
Set-ItemProperty -Path 'HKCU:\Environment' -Name Path -Value $new -Type ExpandString
Set-ItemProperty -Path 'HKCU:\Environment' -Name ANDROID_HOME     -Value '%LOCALAPPDATA%\Android\Sdk' -Type ExpandString
Set-ItemProperty -Path 'HKCU:\Environment' -Name ANDROID_SDK_ROOT -Value '%LOCALAPPDATA%\Android\Sdk' -Type ExpandString
```

改完需广播 `WM_SETTINGCHANGE`（或直接新开窗口）才生效；**已经开着的窗口不会更新**。

```
$ where adb
C:\Users\76982\AppData\Local\Android\Sdk\platform-tools\adb.exe
$ adb version
Android Debug Bridge version 1.0.41 / Version 37.0.1-15733141
```

### 验证输出

**环境自检四连**（2026-08-03，`wellphone_a14` 已启动至桌面）：

```
$ adb devices
List of devices attached
emulator-5554   device

$ adb shell getprop ro.build.version.sdk      # 期望 >= 34
34

$ adb shell getprop ro.build.version.release
14

$ adb root
adbd is already running as root
```

> 关于 `adb root` 的输出：首次执行打印的是 `restarting adbd as root`，
> 本次因 adbd 已提权过，回的是 `adbd is already running as root` —— 两者都代表成功。
> 判断 root 是否真的到手，**不要看这行字，要看 `adb shell id`**：

```
$ adb shell id
uid=0(root) gid=0(root) groups=0(root),1004(input),1007(log),1011(adb),
1015(sdcard_rw),1028(sdcard_r),1078(ext_data_rw),1079(ext_obb_rw),
3001(net_bt_admin),3002(net_bt),3003(inet),3006(net_bw_stats),
3009(readproc),3011(uhid),3012(readtracefs) context=u:r:su:s0
```

→ `uid=0(root)` + `context=u:r:su:s0`，**root 确实到手**。
这一条是选 `google_apis` 而非 Play Store 镜像的直接回报：生产签名镜像在这里会卡死。

**补充自检**（ABI 与构建类型）：

```
$ adb shell "getprop ro.product.cpu.abi; getprop ro.build.type"
x86_64
userdebug
```

→ `userdebug` 而非 `user`，是 `adb root` 可用的根本原因。

**显示基线（R1 的对照组，必须先留档）**：

```
$ adb shell "dumpsys display | grep -E 'mDisplayId|uniqueId'"
mViewports=[DisplayViewport{type=INTERNAL, valid=true, isActive=true, displayId=0,
            uniqueId='local:4619827259835644672', physicalPort=0, orientation=0,
            logicalFrame=Rect(0, 0 - 1080, 2400), deviceWidth=1080, deviceHeight=2400}]
DisplayDeviceInfo{"Built-in Screen": uniqueId="local:4619827259835644672", 1080 x 2400,
                  ... density 420, ... type INTERNAL, ...
                  FLAG_ALLOWED_TO_BE_DEFAULT_DISPLAY, FLAG_ROTATES_WITH_CONTENT,
                  FLAG_SECURE, FLAG_SUPPORTS_PROTECTED_BUFFERS, FLAG_TRUSTED, ...}
mDisplayId=0
```

→ **启动时有且仅有 display 0。** 后续任何 `mDisplayId=1` 的出现都可归因于我方操作。

### 遇到的问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `sdkmanager` 不存在 | Android Studio 默认不装 `cmdline-tools` | 从 dl.google.com 手动下载解压 |
| 装 `platforms;android-34` 报 `stat_sys_phone_call.png: 文件被另一进程占用` | Android Studio 正在后台索引 SDK 目录，锁住了解压中的文件 | 清掉 `$SDK\.temp\PackageOperation01` 与半成品 `platforms\android-34` 后重跑 |
| `avdmanager create avd` 打印 `Error: Could not load devices from ...\x86_64\devices.xml` | 该镜像本就不带 per-image `devices.xml`，属良性告警 | 忽略；AVD 已正常创建 |

### 结论

✅ **实验台就绪**：Android 14 · userdebug · root 可用 · 多屏热插拔已开 · 宿主键盘直连主屏。
R1–R5 全部具备开跑条件。

### 待办（下一步 D1 收尾）

- [ ] 装 scrcpy（方案 A 的建屏路线 B 依赖 `--new-display`，Android 14+）
- [ ] R1 探针：`overlay_display_devices` 建屏 → `am start --display 1`
- [ ] 查 `per-display focus` 是否开启
- [ ] R4 探针：选定目标 app 后 `uiautomator dump` + **真点一下**

---

## E1 — R1：能否创建用户看不见的屏并在其上启动 app

**状态**：⬜ 未开始
**验证成本**：~10 min，纯命令行
**塌了的后果**：隔离思路作废 → 转 scrcpy `app_process` 提权 / 工作资料 / 多用户
**备选出路**：见需求梳理 v2 第五节方案 C / D

### 计划命令

```bash
# 路线 A：overlay（可见浮层，仅供调试，不是最终方案）
adb shell settings put global overlay_display_devices "1280x720/320"
adb shell dumpsys display | grep mDisplayId

# 分水岭
adb shell am start --display 1 -n com.android.settings/.Settings

# 路线 B：scrcpy 建虚拟屏（Android 14+，不依赖 overlay 设置项）
scrcpy --new-display=1280x720
adb shell dumpsys display | grep mDisplayId
```

### 原始输出

_（待填）_

### 结论

_（待填）_

---

## E2 — R4：目标 app 节点树质量

**状态**：⬜ 未开始
**验证成本**：~20 min
**候选目标**：Thunderbird for Android（原 K-9 Mail，首选）· Wikipedia app（Plan B）

> ⚠️ 两个独立的坑，别混为一谈：
> - **坑 1**：节点树本身没有 text/id（自绘 UI、Flutter、RN 常见）→ dump 出来就是空的
> - **坑 2**：树是好的，但**动作是哑的** —— 控件在 touch listener 里处理点击，
>   `performAction(ACTION_CLICK)` **返回 true 但界面没反应**
>
> 所以探测**不能只看 dump 结果，必须真点一下确认生效**。

### 原始输出

_（待填）_

### 结论

_（待填）_

---

## E3 — R2：无障碍服务能否读到副屏节点树

**状态**：⬜ 未开始
**验证成本**：半天，需写代码（`getWindowsOnAllDisplays()`，API 30+）
**塌了的后果**：感知层没了 → 退回截图（root 下 `screencap` 指定 display，绕开 MediaProjection）

### 原始输出

_（待填）_

### 结论

_（待填）_

---

## E4 — R3：`performAction` 是否抢主屏焦点与键盘 ⚠️ 生死线

**状态**：⬜ 未开始
**验证成本**：1 h，基于 R2
**塌了的后果**：**"不打扰"交付失败，题目直接不成立** → 转方案 E（完全不碰 GUI）
**目标**：D2 当晚就拿到结论，而不是拖到 D3

只需一个 ~100 行的最小无障碍服务：dump 窗口树 + 硬编码 `performAction` 点一个节点。

### 三个必须同时记录的观察点

| # | 观察点 | 怎么看 |
|---|---|---|
| ① | 主屏 `mCurrentFocus` 是否变化 | `adb shell dumpsys window \| grep -E "mCurrentFocus\|mFocusedApp\|mFocusedWindow"`，操作前后对比 |
| ② | 主屏输入光标是否跳走 | 主屏开一个输入框持续打字，肉眼 + 录屏 |
| ③ | `performAction` 返回 true 时副屏**是否真的有反应** | 对应方案 B 坑 2，返回值不可信 |

### 原始输出

_（待填）_

### 结论

_（待填）_

---

## E5 — R5：LLM 基于压缩节点树的规划质量

**状态**：⬜ 未开始
**风险最低 —— 绝不能从这里开始做**（那是在拖延真正的问题）

### 两件 D2 就要定死的事

1. **原子动作 schema**（五个够用）：
   `click(node_id)` / `set_text(node_id, text)` / `scroll(node_id, direction)` / `back()` / `wait_for(condition, timeout)`
   —— 这个 schema 本身就是"架构撑得起更复杂任务"这条加分项的**直接证据**：任务换了，动作层不变，只换 prompt。
2. **节点树压缩策略**：原始 dump 动辄几千节点，直接喂 LLM 又贵又乱。
   只保留**可见 + 可交互**（clickable / editable / scrollable）节点 + 少量文本锚点 → 分配短 ID → 层级缩进呈现。
   **这是决定 R5 成败的真正变量**，且完全在 Python 主场，可离线拿 `uiautomator dump` 的 XML 先写出来。

### 原始输出

_（待填）_

### 结论

_（待填）_

---

## 附：共享资源冲突清单（加分项，边做边验）

| 资源 | 风险 | 对策 | 实测状态 |
|---|---|---|---|
| 焦点 | Agent 一操作就抢走用户焦点 | `performAction` 不需要焦点 | 见 E4 ① |
| IME | 同一时刻只有一个 IME 实例 | `ACTION_SET_TEXT` 不走 IME | 见 E4 ② |
| 画面 | `am start` 把已有实例"搬"到副屏 | 选 Agent 专用 app / 工作资料隔离 | ⬜ |
| **剪贴板** | `SET_TEXT` 被拒时的 fallback 是剪贴板 + `ACTION_PASTE`，但剪贴板**全局共享**，会覆盖用户正要粘贴的内容 | 备份 → 写入 → 粘贴 → 恢复 四步走 | ⬜ |
| **系统弹窗 / Toast** | 运行时权限弹窗、崩溃对话框**永远弹在 display 0**，直接砸用户脸上 | 流程中绝不触发运行时权限请求（提前授好权）；副屏 Toast 是否漏到主屏需实测 | ⬜ |
| **通知 / 声音** | Agent 操作的 app 发通知、出提示音，也算打扰 | 选任务时规避，或演示前静音。注意：若外部验证恰恰依赖主屏通知，属"预期结果"而非打扰 | ⬜ |

---

## 附：踩坑速查

- 无障碍服务改配置后，**必须去设置里关掉再打开**才生效
- Logcat 刷屏严重，一开始就定一个独特 TAG
- AVD 冷启动很慢，**开着别关**
- `uiautomator dump` 与无障碍服务看到的节点树**不完全一样**，别混用作判断依据
- `overlay_display_devices` 创建的是**可见浮层**，便于调试但不是最终方案
