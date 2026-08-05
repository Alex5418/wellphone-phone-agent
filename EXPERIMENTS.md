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
| **R1** | 能创建用户看不见的屏，并在上面启动 app | ✅ 通过 | 两条路线均可建屏；display id 每次不同，禁止硬编码 |
| **R4** | 目标 app 节点树质量够用（有 text/id，且 action 不哑） | ⚠️ 条件通过 | 原生 View app 可用；WebView / 自绘 UI 不可用 |
| **R2** | 无障碍服务能读到副屏节点树 | ✅ 通过 | 仅 scrcpy VirtualDisplay 可读；overlay display 不可读 |
| **R3** | `ACTION_CLICK` / `SET_TEXT` 不抢主屏焦点和键盘 | ❌ **失败** | **生死线未通过**，a11y 动作模型本身绑定单焦点 |
| **R5** | LLM 能基于压缩后的节点树做出靠谱规划 | ⬜ 未开始 | 待 S2 方向确定后再启动 |

状态图例：⬜ 未开始 · 🟡 进行中 · ✅ 通过 · ⚠️ 部分通过（有绕过方案） · ❌ 失败（已换路线）

**当前阶段结论：主线方案「虚拟屏隔离 + a11y node action」在「不打扰」硬指标上不成立。**
详见 [S1 阶段总结](#s1-阶段总结)。

---

## E0 — 环境搭建

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
| scrcpy | v4.1 (win64) |
| Shell | Git Bash (MINGW64) |

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
从不写系统 PATH。要大量敲 `adb shell dumpsys`，必须先配上。

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

**环境自检四连**：

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

→ **启动时有且仅有 display 0。** 后续任何新 display id 的出现都可归因于我方操作。

### 遇到的问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `sdkmanager` 不存在 | Android Studio 默认不装 `cmdline-tools` | 从 dl.google.com 手动下载解压 |
| 装 `platforms;android-34` 报 `stat_sys_phone_call.png: 文件被另一进程占用` | Android Studio 正在后台索引 SDK 目录，锁住了解压中的文件 | 清掉 `$SDK\.temp\PackageOperation01` 与半成品 `platforms\android-34` 后重跑 |
| `avdmanager create avd` 打印 `Error: Could not load devices from ...\x86_64\devices.xml` | 该镜像本就不带 per-image `devices.xml`，属良性告警 | 忽略；AVD 已正常创建 |
| Git Bash 下 `adb shell uiautomator dump /sdcard/d0.xml` 写到了 `C:/Program Files/Git/sdcard/` | MSYS 路径自动转换，把设备路径当成 Windows 路径 | `export MSYS_NO_PATHCONV=1`，或写 `//sdcard/...` |
| `adb shell settings put global overlay_display_devices ""` 报 bad argument | 空引号在本地 shell 就被吃掉，参数没传到设备 | 改用 `settings delete global overlay_display_devices` |

### 结论

✅ **实验台就绪**：Android 14 · userdebug · root 可用 · 多屏热插拔已开 · 宿主键盘直连主屏。
R1–R5 全部具备开跑条件。

---

## E1 — R1：能否创建用户看不见的屏并在其上启动 app

**状态**：✅ **通过** [非root可复现 · API 34]
**验证成本**：实际约 20 min
**塌了的后果**：隔离思路作废 → 转 scrcpy `app_process` 提权 / 工作资料 / 多用户

### 路线 A：overlay_display_devices

```bash
$ adb shell settings put global overlay_display_devices "1280x720/320"
$ adb shell dumpsys display | grep mDisplayId
# → 出现新的 display，实际 id 为 2（不是预期的 1）

$ adb shell am start --display 2 -n com.android.settings/.Settings
Starting: Intent { cmp=com.android.settings/.Settings }
```

**焦点归属确认（关键证据）**：

```
$ grep -n -E "Display: mDisplayId|mCurrentFocus|mFocusedApp" focus_probe.txt
2:  Display: mDisplayId=2 (organized)
10:  mCurrentFocus=null
11:  mFocusedApp=ActivityRecord{a3436a u0 com.android.settings/.Settings t10}
126:  Display: mDisplayId=0 (organized)
134:  mCurrentFocus=Window{eba599a u0 com.android.chrome/...Main}
135:  mFocusedApp=ActivityRecord{366264a u0 com.android.chrome/...Main t9}
245:    mFocusedWindow=Window{eba599a u0 com.android.chrome/...Main}
```

→ 两块屏各自的 `mFocusedApp` 都有值（两个 app 都在各自屏上顶层运行），
但 `mCurrentFocus` **只有一块屏有值，另一块是 `null`**，全局 `mFocusedWindow` 唯一。

**这是 `config_perDisplayFocusEnabled = false` 的直接实证**：
全系统只有一个窗口能持有输入焦点，抢到的那块屏有值，没抢到的就是 null。

### 路线 B：scrcpy --new-display

```bash
$ ./scrcpy --new-display=1280x720 --no-clipboard-autosync
$ adb shell dumpsys display | grep -E "^  mDisplayId"
  mDisplayId=0
  mDisplayId=4        # 每次重启 scrcpy 都会变：实测出现过 2 / 4 / 5 / 6

$ adb shell am start --display 4 -n com.android.settings/.Settings
$ adb shell dumpsys window displays | grep -E "mDisplayId=|mFocusedApp"
  Display: mDisplayId=0 (organized)
  mFocusedApp=...nexuslauncher/.NexusLauncherActivity
  Display: mDisplayId=4 (organized)
  mFocusedApp=...com.android.settings/.Settings
```

### 结论

✅ **R1 通过**，两条路线都能建屏并在其上独立运行 app。

**⚠️ 工程约束（必须写进代码）**：display id **每次都不同**，实测序列 2 → 4 → 5 → 6。
代码中**绝对不能硬编码 display id**，必须从 `dumpsys display` 或
`DisplayManager.getDisplays()` 动态解析。

**路线取舍**：overlay 屏是**浮在主屏上的可见浮层**，且空闲时**镜像主屏内容**——
本质是"模拟的外接显示器"，为开发者预览多屏布局而设计，不是为隔离设计的。
最终方案应使用 scrcpy 的 VirtualDisplay（另见 E3，overlay 屏在无障碍层完全不可见）。

---

## E1b — R3-a：副屏启动 app 是否抢主屏焦点

**状态**：❌ **不通过** [非root可复现 · API 34]

### 复现方法

单人操作两件事的解法：**观察自动化 + 动作定时触发 + 手只负责打字**。

```bash
# 终端 A：焦点监视
while true; do
  printf "%s  " "$(date +%T.%3N)"
  adb shell dumpsys window | grep -m1 "mCurrentFocus"
  sleep 0.5
done | tee focus.log

# 终端 B：延时触发（留 10 秒切窗口 + 起手打字）
sleep 10 && date +%T.%3N && adb shell am start --display 2 -n com.android.settings/.Settings
```

主屏打开输入框，连续打 `1234567890` 循环（**内容要可校验**，随机字符看不出丢字）。

### 原始现象

```
$ adb shell dumpsys window displays | grep -E "mDisplayId=|mCurrentFocus|mFocusedApp"
  Display: mDisplayId=0 (organized)
  mCurrentFocus=null
  mFocusedApp=ActivityRecord{366264a u0 com.android.chrome/...Main t9}
  Display: mDisplayId=2 (organized)
  mCurrentFocus=Window{3797b83 u0 com.android.settings/...Settings}
  mFocusedApp=ActivityRecord{a3436a u0 com.android.settings/.Settings t10}
```

**肉眼观察**：主屏软键盘收起，必须手动重新唤起才能继续输入。

### 结论

```
[R3-a] ❌ 不通过 [非root可复现 · API 34]
在副屏执行 am start 会导致主屏 IME 收起，用户必须手动重新唤起键盘。

链路: am start → 副屏窗口获得焦点 → perDisplayFocus=false →
      主屏 mCurrentFocus=null → 宿主窗口 onWindowFocusChanged(false) → IME 收起

注: Chrome 的 mFocusedApp 保持不变（未被切后台），
    打断发生在 window / IME 层，不在 Activity 层。
```

**三个层级必须分开看**，混为一谈会得出错误结论：

| 层级 | 字段 | 范围 | 本次表现 |
|---|---|---|---|
| Activity 生命周期 | `mFocusedApp` | 每屏一个 | Chrome 仍 RESUMED，未被打断 |
| Window 输入焦点 | `mCurrentFocus` | **全系统一个** | 主屏变 null |
| 用户实际体验 | —— | —— | **键盘收起，输入中断** |

**架构影响**：Agent 在任务期间不能触发任何窗口激活 → 推导出
「**部署期 / 运行期分离**」：部署期一次性把目标 app 拉到副屏常驻（允许一次焦点交接），
运行期只用 node action，不再触发激活。

> 注：另有一次观察到 scrcpy VirtualDisplay 上**两块屏同时持有 `mCurrentFocus`**
> （display 0 = chrome，display 6 = settings）。这与 overlay 屏的表现不同，
> 疑似 scrcpy 创建虚拟屏时带了不同的 flag。**未深入验证，属开放问题**，
> 且不影响 E4 的最终结论（动作发出后焦点仍被夺走）。

---

## E2 — R4：目标 app 节点树质量

**状态**：⚠️ **条件通过** [非root可复现 · API 34]

> ⚠️ 两个独立的坑，别混为一谈：
> - **坑 1**：节点树本身没有 text/id（自绘 UI、Flutter、RN 常见）→ dump 出来就是空的
> - **坑 2**：树是好的，但**动作是哑的** —— 控件在 touch listener 里处理点击，
>   `performAction(ACTION_CLICK)` **返回 true 但界面没反应**
>
> 所以探测**不能只看 dump 结果，必须真点一下确认生效**。（坑 2 在 E4 中已验证不存在于
> Settings：`performAction` 返回 true 且 dark mode 真的生效。）

### 样本 A：Chrome 新标签页（WebView 信息流）

```
$ adb shell uiautomator dump /sdcard/d0.xml && adb pull /sdcard/d0.xml .
$ grep -o "<node" d0.xml | wc -l
601

$ grep -o 'class="[^"]*"' d0.xml | sort | uniq -c | sort -rn | head -12
    376 class="android.view.View"
    129 class="android.widget.TextView"
     38 class="android.widget.Image"
     13 class="android.widget.FrameLayout"
     13 class="android.widget.Button"
      9 class="android.widget.ListView"
      7 class="android.widget.LinearLayout"
      6 class="android.widget.ImageButton"
      4 class="android.widget.ImageView"
      2 class="android.widget.EditText"

$ grep -o 'resource-id="[^"]*"' d0.xml | sort -u | head
resource-id=""
resource-id="CardInstance-r0ONi-k6ut7x3XXvnapiw"
resource-id="CardInstance1k3pAG94sfNntdvuu5PfFg"
resource-id="CardInstance603pwsiZe70ZYBLzQ85Rfg"
...
```

`CardInstance` + 22 位 base64 随机串 = **卡片实例化时动态生成，刷新页面即失效**。
这比空 id 更危险：看起来可用，实际一次性有效。

### 样本 B：Settings（原生 View）

```
$ adb shell uiautomator dump /sdcard/s.xml && adb pull /sdcard/s.xml .
$ grep -o "<node" s.xml | wc -l
53

$ grep -o 'class="[^"]*"' s.xml | sort | uniq -c | sort -rn | head -10
     16 class="android.widget.TextView"
     15 class="android.widget.LinearLayout"
     11 class="android.widget.RelativeLayout"
      6 class="android.widget.FrameLayout"
      1 class="androidx.recyclerview.widget.RecyclerView"
      1 class="android.widget.ScrollView"
      1 class="android.widget.ImageButton"
      1 class="android.view.ViewGroup"
      1 class="android.view.View"

$ grep -o 'resource-id="com[^"]*"' s.xml | sort -u
resource-id="com.android.settings:id/action_bar"
resource-id="com.android.settings:id/app_bar"
resource-id="com.android.settings:id/collapsing_toolbar"
resource-id="com.android.settings:id/container_material"
resource-id="com.android.settings:id/content_frame"
resource-id="com.android.settings:id/content_parent"
resource-id="com.android.settings:id/main_content"
resource-id="com.android.settings:id/recycler_view"
```

### 对照

| | Chrome 信息流 | Settings |
|---|---|---|
| 节点数 | **601** | **53** |
| 文件大小 | 203 KB | 18 KB |
| `android.view.View` 占比 | 376/601 = **62%** | 1/53 = **2%** |
| `resource-id` 格式 | `CardInstance-r0ONi...`（运行时随机） | `com.android.settings:id/xxx`（编译期固定） |
| 语义类型 | 大量无类型 View | 全部明确 |

**同一 API、同一设备、同一方法，树的质量差一个数量级。**

### 结论

```
[R4] ⚠️ 条件通过 [非root可复现 · API 34]
原生 View 实现的 app（Settings）: 53 节点，resource-id 稳定规范，
  语义类型完整 → 节点树可直接作为 Agent 感知通道
WebView / 自绘 UI（Chrome 信息流）: 601 节点，62% 为无类型 View，
  resource-id 运行时随机生成 → 不可用

决策: 目标 app 必须为原生 View 实现。这是任务选型的第一道筛选条件。
```

R4 不是 yes/no 问题，而是**选型约束**。

**顺带**：601 节点若原样喂 LLM 既贵又乱，压缩器是必需品；但 53 节点几乎无需压缩。
选对目标 app，等于消掉了 R5 的大半风险。

### 附带发现：`resource-id` 的本质

`com.android.settings:id/switchWidget` 不是文件路径，是**运行时资源标识符**：
`包名 : id / 名称`。开发者在 XML 写 `@+id/switchWidget`，编译期分配整数 ID 存入资源表，
运行时由 `getViewIdResourceName()` 反查回可读字符串。
它编译期固定、不随语言与文案变化，**比 text 定位可靠得多**。

前提是服务配置里有 `flagReportViewIds`，否则 `id=null`。

---

## E3 — R2：无障碍服务能否读到副屏节点树

**状态**：✅ **通过（仅限 scrcpy VirtualDisplay）** [非root可复现 · API 34 · scrcpy 4.1]

### 预探：uiautomator 的 --display 参数是假的

```
$ adb shell uiautomator dump --display 2 /sdcard/d2.xml
UI hierchary dumped to: /sdcard/d2.xml        # 无报错

$ adb pull /sdcard/d2.xml .
/sdcard/d2.xml: 1 file pulled ... (203589 bytes)   # 与 d0.xml 字节数完全相同

$ grep -o 'package="[^"]*"' d2.xml | sort -u
package="com.android.chrome"                   # 只有主屏的 Chrome，无 Settings

$ echo "d0:" $(grep -o "<node" d0.xml | wc -l); echo "d2:" $(grep -o "<node" d2.xml | wc -l)
d0: 601
d2: 601
```

```
[R2-预探] ❌ uiautomator dump --display N 静默失败
参数被忽略且不报错 —— 最危险的失败形态。
若不做包名验证，会带着错误结论继续往下走。
推论: 命令行工具链无法感知副屏，必须自行实现 AccessibilityService
      并使用 getWindowsOnAllDisplays()。
```

### 自建 AccessibilityService

关键配置（`res/xml/accessibility_service_config.xml`）：

```xml
android:accessibilityFlags="flagRetrieveInteractiveWindows|flagIncludeNotImportantViews|flagReportViewIds"
android:canRetrieveWindowContent="true"
```

`flagRetrieveInteractiveWindows` 是命脉 —— 没有它只能看到当前有焦点的窗口，
而副屏永远没焦点。**这正是 uiautomator 那条路没给你的配置机会。**

### 测试 A：overlay display

系统视角（`dumpsys`）确认状态正确：

```
$ adb shell dumpsys window displays | grep -E "mDisplayId=|mFocusedApp"
  Display: mDisplayId=2 (organized)
  mFocusedApp=ActivityRecord{ca8ef4e u0 com.android.settings/.Settings t15}
  Display: mDisplayId=0 (organized)
  mFocusedApp=ActivityRecord{5eebaf3 u0 ...nexuslauncher/.NexusLauncherActivity t7}
```

无障碍视角：

```
I PHONEAGENT: ########## displays found: 1 ##########
I PHONEAGENT: >>> display=0  windows=2
I PHONEAGENT:     win pkg=com.android.systemui focused=false active=false
I PHONEAGENT:     nodes=27
I PHONEAGENT:     win pkg=com.google.android.apps.nexuslauncher focused=true active=true
I PHONEAGENT:     nodes=34
```

```
[R2-overlay] ❌ 不通过
系统明确知道 display 2 上跑着 Settings，但无障碍服务完全看不到它。
排除项: flagRetrieveInteractiveWindows 已生效
        （证据: systemui 窗口 focused=false 仍被读到 27 节点
          → 服务能读非焦点窗口，只是读不到非默认 display）
推断: overlay_display_devices 创建的 simulated display 未被标记为无障碍可访问。
```

### 测试 B：scrcpy VirtualDisplay

```
$ adb shell settings delete global overlay_display_devices
$ ./scrcpy --new-display=1280x720 --no-clipboard-autosync
$ adb shell am start --display 6 -n com.android.settings/.Settings
$ adb shell dumpsys window displays | grep -E "mDisplayId=|mFocusedApp"
  Display: mDisplayId=0 (organized)
  mFocusedApp=...nexuslauncher/.NexusLauncherActivity
  Display: mDisplayId=6 (organized)
  mFocusedApp=...com.android.settings/.Settings
```

```
I PHONEAGENT: ########## displays found: 2 ##########
I PHONEAGENT: >>> display=0  windows=3
I PHONEAGENT:     win pkg=com.android.systemui focused=false active=false
I PHONEAGENT:     nodes=27
I PHONEAGENT:     win pkg=com.google.android.inputmethod.latin focused=false active=false
I PHONEAGENT:     nodes=163
I PHONEAGENT:     win pkg=com.android.chrome focused=true active=true
I PHONEAGENT:     nodes=599
I PHONEAGENT: >>> display=6  windows=1
I PHONEAGENT:     win pkg=com.android.settings focused=true active=true
I PHONEAGENT:     nodes=135
```

**节点树可完整读取**（`printTree` 输出，depth ≤ 12）：

```
I PHONEAGENT: [FrameLayout] 'Display' click=false id=com.android.settings:id/collapsing_toolbar
I PHONEAGENT:   [ImageButton] 'Navigate up' click=true id=null
I PHONEAGENT:   [TextView] 'Display' click=false id=null
I PHONEAGENT:     [LinearLayout] '' click=true id=null
I PHONEAGENT:       [TextView] 'Brightness level' click=false id=android:id/title
I PHONEAGENT:       [TextView] '0%' click=false id=android:id/summary
...
I PHONEAGENT:     [LinearLayout] '' click=true id=null
I PHONEAGENT:       [TextView] 'Dark theme' click=false id=android:id/title
I PHONEAGENT:       [TextView] 'Will never turn on automatically' click=false id=android:id/summary
I PHONEAGENT:       [Switch] 'Dark theme' click=true id=com.android.settings:id/switchWidget
```

### 结论

```
[R2] ✅ 通过 [非root可复现 · API 34 · scrcpy 4.1]
scrcpy --new-display 创建的 VirtualDisplay 可被 windowsOnAllDisplays() 完整读取
  display 6: com.android.settings, 135 nodes, 节点树含 text / resource-id / clickable

对照: overlay_display_devices 的 simulated display 完全不可见
      （同一服务、同一 flag、同一次运行）

结论: 两种虚拟屏在无障碍框架中待遇不同，创建方式决定可访问性。
      这一差异未见于官方文档，是本项目的实测发现。
```

**交叉验证**：无障碍服务读到 Chrome 599 节点，`uiautomator dump` 读到 601 节点
（差 2 为根节点计法不同）→ 两条独立路径读出同一棵树，**读取完整可信**。

Settings 135（a11y）vs 53（uiautomator）的差异来自 `flagIncludeNotImportantViews`。

### 附带发现 1：IME 窗口可被读取

```
win pkg=com.google.android.inputmethod.latin focused=false  nodes=163
```

软键盘作为**独立窗口出现在 display 0 的窗口列表中，且内容可读**。

**这可能是「调度规避」方案的关键信号**：Agent 可以检测"用户此刻是否正在输入"，
从而避开该时间窗口再执行动作。不是硬扛冲突，而是绕过冲突。
（键盘收起时该窗口应消失 → `windows=3` 变 `windows=2`，可作为布尔信号。待验证。）

### 附带发现 2：`isFocused()` ≠ `mCurrentFocus`

```
[注意] AccessibilityWindowInfo.isFocused() 是 per-display 语义
       （这块屏上是不是最上层活跃窗口），
       与 WindowManager 的 mCurrentFocus（全局唯一，谁能收键盘）不同。

实测同一次 dump 中 display 0 的 chrome 和 display 6 的 settings
都报 focused=true —— 但 mCurrentFocus 全系统只能有一个。

判断"是否抢焦点"必须用 dumpsys window 的 mCurrentFocus，
不能用无障碍 API 的字段。
```

### 附带发现 3：文字锚点与可点容器分离

节点树中反复出现这个模式：

```
[LinearLayout] ''  click=true   id=null          ← 可点，但无文字无 id
    [TextView] 'Magnification'  click=false      ← 有文字，但不可点
```

**含义**：
- `findAccessibilityNodeInfosByText()` 找到的是 TextView，必须向上爬找可点父节点
- **但"向上找第一个 clickable"是错的**（见 E4 无效测试 2）
- 压缩后喂给 LLM 的节点树必须把「文字锚点」和「实际动作目标」**合并为一个逻辑条目**，
  否则 LLM 会选中不可点的 TextView，或选中错误的容器

---

## E4 — R3-b：`performAction` 是否抢主屏焦点与键盘 ⚠️ 生死线

**状态**：❌ **不通过 · 决定性结论** [非root可复现 · API 34 · scrcpy VirtualDisplay]

### 三个必须同时记录的观察点

| # | 观察点 | 怎么看 |
|---|---|---|
| ① | 主屏 `mCurrentFocus` 是否变化 | `dumpsys window displays`，操作前后对比 |
| ② | 主屏输入光标 / 键盘是否被打断 | 主屏持续打字，肉眼 + 录屏 |
| ③ | `performAction` 返回 true 时副屏**是否真有反应** | 对应坑 2，返回值不可信 |

### 测试 1：点击跳转型条目（有效，但不足以定论）

```
$ sleep 10 && adb shell am broadcast -a com.example.phoneagent.CLICK \
    -p com.example.phoneagent --ei display 6 --es text "Network"

I PHONEAGENT: CLICK display=6 text='Network' result=true node=android.widget.LinearLayout

$ adb shell dumpsys window displays | grep -E "mDisplayId=|mCurrentFocus"
  Display: mDisplayId=0 (organized)
  mCurrentFocus=null
  Display: mDisplayId=6 (organized)
  mCurrentFocus=Window{d095f7b u0 com.android.settings/com.android.settings.SubSettings}
```

- 副屏 Settings → SubSettings 跳转成功（**动作真实生效，非哑动作** → 坑 2 不存在）
- 主屏 `mCurrentFocus` → null，**软键盘收起，数字序列中断**

**但此时无法归因**：可能是 `performAction` 本身抢焦点，也可能是它触发的
Activity 跳转（新窗口创建时申请焦点）抢焦点。需要进一步排除。

### 无效测试 1：目标不存在

```
I PHONEAGENT: CLICK display=6 text='Airplane' NOT FOUND
```

副屏当时停在 SubSettings，页面上没有该文字。**"没被打断"的观察因此作废** ——
动作根本没执行。

> **教训**：判断广播是否成功，不能看终端的 `Broadcast completed: result=0`
> （那只是 `RESULT_CANCELED` 默认值，与送达无关），**必须看 logcat 有无新日志**。

### 无效测试 2：选错节点

```
$ ... --es text "Dark theme"
I PHONEAGENT: CLICK display=6 text='Dark' result=true node=android.widget.LinearLayout
  mCurrentFocus=Window{...SubSettings}     # 又跳页了
```

`findAccessibilityNodeInfosByText("Dark theme")` 匹配到**两个**节点（TextView 与 Switch），
代码取 `hits[0]` = TextView，向上爬到整行 LinearLayout ——
**点整行 = 进入子页面，点 Switch = 原地翻转**，行为完全不同。

```
[设计约束] Agent 的节点选择策略必须区分"文字锚点"与"实际动作目标"，
          不能简单向上找第一个 clickable。
```

→ 为此新增 `CLICK_ID` 指令，用 `findAccessibilityNodeInfosByViewId()` 精确定位。

### 测试 2：点击非跳转型控件（决定性）

目标：`com.android.settings:id/switchWidget`（Dark theme 开关，原地翻转不跳页）

```
$ sleep 10 && adb shell am broadcast -a com.example.phoneagent.CLICKID \
    -p com.example.phoneagent --ei display 2 \
    --es vid "com.android.settings:id/switchWidget"

I PHONEAGENT: CLICK_ID display=2 id='com.android.settings:id/switchWidget'
              result=true node=android.widget.Switch

$ adb shell dumpsys window displays | grep -E "mDisplayId=|mCurrentFocus"
  Display: mDisplayId=0 (organized)
  mCurrentFocus=null
  Display: mDisplayId=2 (organized)
  mCurrentFocus=Window{ff30600 u0 com.android.settings/
                       com.android.settings.Settings$DisplaySettingsActivity}
```

**肉眼确认**：
- 副屏设备**真的切换为 dark mode**（动作生效）
- `mCurrentFocus` 仍是 `DisplaySettingsActivity`，**无 Activity 跳转、无新窗口创建**
- 主屏**软键盘仍然收起，输入中断**

### 结论

```
[R3-b] ❌ 不通过 · 决定性结论 [非root可复现 · API 34 · scrcpy VirtualDisplay]

动作: performAction(ACTION_CLICK) on android.widget.Switch, display 2
效果: result=true，dark mode 生效
窗口: 无 Activity 跳转（mCurrentFocus 仍为 DisplaySettingsActivity）
代价: 主屏 mCurrentFocus → null，软键盘收起，用户输入中断

关键: 排除了"Activity 跳转导致抢焦点"的假设。
      即使是同窗口内的纯状态变更，焦点仍被夺走。
      → 抢焦点的是 performAction 本身，不是它引发的后果。
```

**机制解释（推断）**：`performAction` 在框架层不只是调 view 的 `performClick()`，
它会走完整的无障碍动作分发，其中包含**让目标窗口成为 active window** 的语义。
这是无障碍框架的设计意图 —— 读屏软件点了什么，焦点就该跟到哪，方便盲人用户继续操作。
**这个设计对读屏是对的，对本题是致命的。**

### 已排除的绕法

| 绕法 | 结果 |
|---|---|
| 换 display 类型（overlay → scrcpy VirtualDisplay） | 焦点照样被抢 |
| 换动作类型（跳转型 → 非跳转型状态变更） | 焦点照样被抢 |
| 换定位方式（text → resource-id 精确命中 Switch） | 焦点照样被抢 |

**三条独立路径结论一致** → 这是框架层语义，不是权限问题、配置问题或 display 类型问题。

---

## E5 — R5：LLM 基于压缩节点树的规划质量

**状态**：⬜ 未开始 —— **等 S2 方向确定后再启动**

R5 风险最低，绝不能从这里开始做（那是在拖延真正的问题）。当前 R3 已失败，
在动作层方向未定之前投入规划层是浪费。

### 已可确定的两件事（不依赖 S2 结论）

1. **原子动作 schema**：
   `click(node_id)` / `set_text(node_id, text)` / `scroll(node_id, direction)` /
   `back()` / `wait_for(condition, timeout)`
   —— 任务换了，动作层不变，只换 prompt。这是"架构撑得起更复杂任务"的直接证据。

2. **节点树压缩策略**：只保留可见 + 可交互（clickable / editable / scrollable）
   节点 + 文本锚点 → **合并文字锚点与可点容器**（见 E3 附带发现 3）→
   分配短 ID → 层级缩进呈现。
   实测参考：Settings 页 47–135 节点，压缩后预计 10–20 个逻辑条目。

### Agent 循环（设计草案）

```
dump 节点树 → 状态自检 → LLM 选择目标 → 执行动作 → 重新 dump 验证 → 下一步
```

**状态自检是必需环节**，不是可选优化。本次实验中人工反复踩到同一类坑：
以为 app 在副屏，实际已被系统回收 / 已跳到别的页面 / dump 的是陈旧数据。
**Agent 会踩一模一样的坑。** 每次 dump 需带变化标记（根节点 hash 或时间戳），
让规划层能判断"这棵树是不是新的"。

---

## E6 — 焦点归还：把"抢焦点"从故障变成手段 ✅ 转折点

**状态**：✅ **A 档通过** [非root可复现 · API 34 · scrcpy VirtualDisplay]
**日期**：2026-08-05
**性质**：转折点实验。E4 判定 GUI 路线在"不打扰"上不成立，E6 推翻该判定的适用范围。

### 假设

E4 已证：抢焦点发生在**动作分发路径**，与动作是否生效无关。
既然任何 a11y 动作都会把 window 焦点拽到目标所在的 display，
那么**对主屏节点再发一个 a11y 动作，就能把焦点拽回来**。

> 之前所有实验里焦点被夺走后一直没人还 —— 因为没人想过要还。

### 环境

| 项 | 值 |
|---|---|
| 设备 | `wellphone_a14` AVD，Android 14 / API 34 |
| 权限 | `adb unroot`，`uid=2000(shell)` 全程 |
| 副屏 | scrcpy `--new-display`，**display 2** |
| 副屏 app | `com.android.settings` / `DisplaySettingsActivity` |
| 主屏 app | `com.google.android.dialer` 搜索框 `open_search_view_edit_text` |
| 副屏动作 | `ACTION_SCROLL_FORWARD` on `com.android.settings:id/recycler_view` |
| 归还动作 | `ACTION_FOCUS` on 主屏输入焦点节点 |
| 打字方式 | **真实键盘手打** `1234567890` 循环（非 `input text` 注入） |

主屏刻意避开 Chrome（E2 已证其节点树不可用），也避开 Settings
（与副屏同包会让 `dumpsys window` 的两个 display 显示同一包名，无法判读）。

### 实现

新增 `ACTION_DO_RESTORE` 指令：**动作前**缓存主屏输入焦点节点 → 执行副屏动作 →
**立即**对缓存节点发 `ACTION_FOCUS`。节点必须在动作前抓，
因为 `AccessibilityNodeInfo` 是快照，动作后窗口已变会 stale。

### 四轮对照数据

| Run | 归还 | 副屏动作 | display 0 `mCurrentFocus` | 触发后字段 Δ | 往返耗时 |
|---|---|---|---|---|---|
| 1 基线 | ✗ | `ok=true` 真滚 | **null** | **0** | — |
| 2 核心 | ✓ | `ok=true` 真滚 | Dialer（+1s/+3s/末尾） | **42** | **10 ms** |
| 2b 对照 | ✗ | `ok=false` 未滚 | **null** | **0** | — |
| 3 复现 | ✓ | `ok=true` 真滚 | Dialer（+1s/+3s/末尾） | **62** | **15 ms** |

**Run 1 与 Run 2 是严格对照**：副屏动作完全相同且都真实生效，唯一变量是归还。

原始日志：

```
# Run 1 [restore=false] —— 基线，复现已知失败
I PHONEAGENT: RESTORE primary=android.widget.EditText
              id=com.google.android.dialer:id/open_search_view_edit_text len=40 sel=40..40
I PHONEAGENT: RESTORE act=SCROLL_FORWARD ok=true restored=SKIPPED(restore=false) action=8ms
  FIELD T0=7  触发瞬间=40  T2(+15s)=40        ← 冻结
  mCurrentFocus(display 0) = null
  mInputShown = false，mServedView 由 EditText 变为 LinearLayout

# Run 2 [restore=true] —— 核心
I PHONEAGENT: RESTORE primary=android.widget.EditText
              id=com.google.android.dialer:id/open_search_view_edit_text len=86 sel=86..86
I PHONEAGENT: RESTORE act=SCROLL_FORWARD ok=true via=FOCUS delay=0
              refresh=true focusOk=false clickOk=null isFocused=true sel=86..86
              action=3ms restore=7ms total=10ms
  FIELD T0=47  触发瞬间=86  T2(+16.5s)=128
  mCurrentFocus(display 0): FIRE+1s=Dialer  FIRE+3s=Dialer  末尾=Dialer
  mInputShown 全程 true，mServedView 始终为该 EditText

# Run 2b [restore=false] —— 同状态对照，本文档新增，md 协议中没有
I PHONEAGENT: RESTORE act=SCROLL_FORWARD ok=false restored=SKIPPED action=6ms
  FIELD T0=38  触发瞬间=80  T2(+16s)=80       ← 冻结
  mCurrentFocus(display 0) = null
  mInputShown = true（键盘没收起，字仍然打不进去）

# Run 3 [restore=true] —— 复现验证
I PHONEAGENT: RESTORE act=SCROLL_FORWARD ok=true via=FOCUS delay=0
              refresh=true focusOk=false clickOk=null isFocused=true sel=8..8
              action=5ms restore=10ms total=15ms
  FIELD 触发瞬间=8  T2(+16.5s)=70
  mCurrentFocus(display 0): FIRE+1s=Dialer  FIRE+3s=Dialer  末尾=Dialer
```

**肉眼确认**（§4.4 规定主判据）：

- Run 1 / 2b：字在触发瞬间断掉，**不手动点输入框完全打不进去**
- Run 2 / 3：**字全程连续，无需触碰输入框**，副屏动作同时真实生效

### 三个指标

| # | 指标 | 及格线 | 实测 |
|---|---|---|---|
| ① | 往返耗时 | < 100 ms | **10 / 15 ms** ✅ |
| ② | IME 是否自动重新绑定 | 必须成立 | **未发生断开，无需重绑** ✅ 见下 |
| ③ | 窗口期内丢字数 | ≤ 2 字符 | **0** ✅ |

### 结论

```
[E6 · 焦点归还] ✅ 通过 · A 档 [非root可复现 · API 34 · scrcpy VirtualDisplay]

副屏动作执行后立即对主屏输入焦点节点发 ACTION_FOCUS，
可在 10–15 ms 内把 window 焦点拉回 display 0。
用户打字全程无中断、无丢字、无需触碰输入框。

对照四轮，归还与否 = 焦点存活与否，无例外。
```

### 机制：焦点不是被"还"回来的，是被"再抢"回来的

最关键的一条观测：**`ACTION_FOCUS` 返回 `focusOk=false`，归还却成功了。**

原因链：

1. 主屏 EditText 的 **view 焦点从未丢失** —— 焦点被夺走后 `isFocused` 仍为 `true`
   （Run 1 触发后的 FIELD 日志可证）。丢的只有 **window 焦点**。
2. 因此对一个已聚焦节点再发 `ACTION_FOCUS` 是空操作，返回 `false`。
3. 但按 E4 结论，**抢焦点发生在动作分发路径，与动作是否生效无关**。
   这次分发的目标是一个 display 0 的节点 → window 焦点被拽回 display 0。

于是 E4 那条致命结论在 E6 里被反向使用：

> **E4：任何 a11y 动作都会把焦点带到目标窗口 —— 这是故障。**
> **E6：任何 a11y 动作都会把焦点带到目标窗口 —— 这是手段。**

Run 2b 独立复现了这条机制的另一面：该轮 `ok=false`（列表在底部，滚动未生效），
**焦点照样被夺走**，与 E4「连 `result=false` 也照夺」完全一致。

**推论：`ACTION_FOCUS` 是此处的最优归还手段，恰恰因为它什么都不做。**
它返回 `false`、不改变任何 UI 状态、不移动光标（`sel` 前后一致 `86..86` / `8..8`），
却能把 window 焦点拉回来 —— 一个零副作用的纯焦点拉取原语。
原计划的 `ACTION_CLICK` 备选（有移动光标风险）不需要了。

### 关于指标 ②：比预期更强，但也留下未验证的空白

md 原假设是「焦点断过一次后 IME 需要重新绑定，能否自动重连是最大不确定性」。
**实测中 IME 根本没断开**：`mServedView` 全程指向该 EditText，
`mServedInputConnection` 未失效，`mInputShown` 全程 `true`。

这比预设的成功形态更强 —— 但也意味着**「IME 断开后能否自动重连」这个问题本实验没有回答**。
若将来出现真正导致 IME 断开的场景（例如副屏动作引发 Activity 跳转），
该问题仍是未知，不能用 E6 的结论覆盖。

另一条独立佐证：Run 2b 中 `mInputShown` **全程为 true**，键盘没收起、
`InputConnection` 还连着，但字就是打不进去 ——
再次复现「IME 收起与输入中断解耦，根因是 window 焦点为 null」。

### 适用边界（**未验证的部分，勿外推**）

本结论目前只覆盖：

- 1 台模拟器（API 34），未在真机验证
- 1 个动作类型：`SCROLL_FORWARD`。**`CLICK` / `SET_TEXT` / `LONG_CLICK` 未测**
- 副屏动作**未引发 Activity 跳转**的场景。E4 测试 1 那种跳转型点击是否仍能归还，未知
- 单次动作。连续动作、高频动作下的表现未测
- 归还目标是**主屏当前已有输入焦点的节点**。若用户此刻没在输入，行为未定义

**最大的遗留风险**：E4 证明所有动作都抢焦点，但 E6 只证明了归还对其中一个动作有效。
把归还做进原子封装之前，必须先补齐动作维度的覆盖。

### 附带发现（均为静默失效，实验中差点导致结论反向）

1. **`findFocus(FOCUS_INPUT)` 会命中 IME 窗口内的节点。**
   软键盘弹起后 Gboard 自身也是 display 0 上的一个窗口，遍历时先到先得
   会拿到 `com.google.android.inputmethod.latin:id/key_pos_header_...` 这样的**键盘按键**，
   而不是用户的输入框。
   → 必须跳过 `AccessibilityWindowInfo.TYPE_INPUT_METHOD`，并优先取 `isEditable` 节点。
   → 不修的话，归还会打在键盘按键上，得出「跨 display 焦点不联动」的**假 C 档结论**。

2. **"取文本最长的 EditText"是错误的字段选择策略。**
   Dialer 搜索栏容器 `open_search_bar` 的文本是提示语 `Search contacts & places`（24 字符），
   比用户实际输入的内容还长，纯比长度会稳定选中它 ——
   而提示语是常量 → **Δ 恒为 0 → 得出「一个字没丢」的假结论**。
   → 必须优先取 `isFocused` 的节点，长度仅作兜底。

3. **空 `EditText` 的 `getText()` 返回 hint 而非空串。**
   清空输入框后计数器读出 `len=24 text='Search contacts & places' sel=-1..-1`。
   → 自动化判空不能用 `text.isEmpty()`，需结合 `textSelectionStart == -1` 或 `hintText` 比对。

4. **`actionList` 不登记某动作 ≠ 该动作不可用。**
   `recycler_view` 的 `actionList` 中没有滚动动作，
   已有 `DO` 指令"向上爬到支持该动作的父节点"的逻辑会一路爬到 `null` 并静默不发
   （日志 `result=null node=null`）。
   但直接对该节点 `performAction(SCROLL_FORWARD)` 返回 `true` 且真实生效。
   → 定位逻辑需保留"爬不到就用原节点"的兜底。

5. **`scroll=true` 只表示该节点声明可滚动，不代表此刻有滚动余量。**
   Display Settings 是"折叠工具栏 + 列表"双层结构，真正滚动的是外层
   `ScrollView(content_parent)`，内层 `recycler_view` 内容装得下、自身无滚动余量。
   两个容器两个方向全部返回 `false`，与列表是否在底部无关。
   → 副屏状态重置应直接 `am force-stop` + 重启 Activity，比猜滚动容器可靠。

---

## S1 阶段总结

> ⚠️ **本节写于 E6 之前。核心结论已被 E6 部分推翻，见下方修订说明。**

### 已完成的验证

| 项 | 结论 | 标签 |
|---|---|---|
| R1 | ✅ 虚拟屏可建（两种路线），app 可独立运行 | 非root可复现 |
| 单焦点机制 | ✅ 实证 `mCurrentFocus` 全系统唯一 | 非root可复现 |
| R2 | ✅ scrcpy VirtualDisplay 可被 a11y 完整读写 | 非root可复现 |
| R2-overlay | ❌ overlay display 对 a11y 完全不可见 | 非root可复现 |
| R2-预探 | ❌ `uiautomator dump --display` 静默失败 | 非root可复现 |
| R4 | ⚠️ 条件通过：原生 View app 可用，WebView 不可用 | 非root可复现 |
| R3-a | ❌ `am start` 抢焦点收键盘 | 非root可复现 |
| **R3-b** | ❌ **`performAction` 本身抢焦点收键盘** | 非root可复现 |

**全部结论均在 `adb unroot`（uid 2000 shell）条件下取得或复验，可在真机复现。**
root 仅用于探索能力上界，**未进入任何架构决策**。

### 核心结论

> **Android 的无障碍框架不只是"单屏感知"，它的动作模型本身就绑定了单焦点假设。
> 任何通过 a11y 发出的交互，都会把焦点带到目标窗口。**

因此主线方案「虚拟屏隔离 + a11y node action」**在"不打扰"这一硬指标上不成立**。
这不是工程量问题，是机制问题。

> **[2026-08-05 修订 · 见 E6]** 上述机制描述**仍然成立**，但由它推出的方案判定**不再成立**。
> E6 证明：正因为"任何 a11y 动作都会把焦点带到目标窗口"，
> 对主屏节点补发一个动作就能把焦点拽回来，往返 10–15 ms，用户无感。
> **冲突没有被消除，而是被压缩到了用户感知阈值以下。**
> 主线方案在"不打扰"上**条件性成立** —— 条件是动作维度的覆盖需补齐，见 E6 适用边界。

### S2 候选方向（待选型）

| # | 方向 | 评估 |
|---|---|---|
| ① | **调度规避**：检测 IME 窗口存在性，用户输入时暂停 Agent | 最现实。已有信号（E3 附带发现 1）。诚实可讲、能演示。代价：牺牲部分"同时性" |
| ② | **焦点归还**：动作后立即把焦点还给主屏 | ✅ **已实测通过，见 E6**。往返 10–15 ms，丢字 0，IME 未断开。归还手段本身不构成二次打扰（`ACTION_FOCUS` 零副作用、不移动光标）。**升为主线方向** |
| ③ | **方案 E：完全绕开 GUI**（deep link / Intent / ContentProvider / shell） | 不碰 a11y 就不碰焦点，"不打扰"是结构性保证。代价：任务范围受限 |
| ④ | **换隔离层**：多用户 / Work Profile | 唯一可能真正解决问题的方向（绕开同一 WindowManager 实例的前提）。复杂度高，非 root 可行性存疑 |

**倾向：③ + ① 组合** —— 主线用非 GUI 手段完成任务，GUI 操作作为兜底且受调度约束。
这样"不打扰"由架构保证，而非靠运气。

### 下一步（S2 入口）

- [x] ~~实测方向②的时间窗口~~ → **E6 完成**，往返 10–15 ms
- [ ] **补齐 E6 的动作维度覆盖**：`CLICK` / `SET_TEXT` / `LONG_CLICK` 归还是否同样有效
      ← **最高优先级**，E6 只测了 `SCROLL_FORWARD`，这是当前最大的未验证风险
- [ ] 测试副屏动作**引发 Activity 跳转**时归还是否仍有效（E4 测试 1 那种场景）
- [ ] 测试连续 / 高频动作下的归还表现
- [ ] 把归还做进每个动作的原子封装，让"动作 + 归还"成为不可分割的一步
- [ ] 真机复现 E6（目前仅模拟器 API 34）
- [ ] 验证 IME 窗口存在性能否作为可靠的"用户正在输入"布尔信号
- [ ] 盘点方案 E 的可用手段范围（哪些任务能纯靠 Intent / deep link 完成）

---

## 附：共享资源冲突清单（加分项，边做边验）

| 资源 | 风险 | 对策 | 实测状态 |
|---|---|---|---|
| **焦点** | Agent 一操作就抢走用户焦点 | ~~原设想 `performAction` 不需焦点~~ → **动作后立即对主屏节点补发 `ACTION_FOCUS` 抢回来** | ❌ 原假设被证伪（E4）→ ✅ **对策成立，见 E6**（10–15 ms，丢字 0） |
| **IME** | 同一时刻只有一个 IME 实例 | 原设想 `SET_TEXT` 不走 IME | ❌ 焦点丢失即导致 IME 收起 → ⚠️ 但 E6 证明**焦点及时归还时 IME 根本不会断开**；且 E4/E6 均实测「键盘未收起时输入照样中断」，根因始终是 window 焦点 |
| 画面 | `am start` 把已有实例"搬"到副屏 | 部署期一次性拉起，运行期不再激活 | ⚠️ 见 E1b |
| **剪贴板** | `SET_TEXT` 被拒时的 fallback 是剪贴板 + `ACTION_PASTE`，但剪贴板**全局共享** | 备份 → 写入 → 粘贴 → 恢复 四步走 | ⬜ 未实测 |
| 系统弹窗 / Toast | 运行时权限弹窗、崩溃对话框**永远弹在 display 0** | 流程中绝不触发运行时权限请求；副屏 Toast 是否漏到主屏需实测 | ⬜ |
| 通知 / 声音 | Agent 操作的 app 发通知、出提示音，也算打扰 | 选任务时规避。注意：若外部验证恰依赖主屏通知，属"预期结果"而非打扰 | ⬜ |

> **剪贴板这一条的由来**：开发过程中被 scrcpy 的双向剪贴板同步反复打断
> （每次复制命令都推送到设备）。scrcpy 在此扮演了"另一个使用者"的角色，
> 与我抢同一个剪贴板 —— 这正是 Agent 未来会造成的那种打扰的现场演示。
> 处理：`--no-clipboard-autosync`。

---

## 附：踩坑速查

**环境 / 工具链**

- Git Bash 会把 `/sdcard/...` 当 Windows 路径转换 → `export MSYS_NO_PATHCONV=1`
- `settings put global xxx ""` 空引号被本地 shell 吃掉 → 用 `settings delete global xxx`
- PowerShell 不从当前目录执行程序 → `.\scrcpy`，且提示语里的句号不是语法
- 参数含空格 / 引号 / `$` / `*` 时，把整条命令用引号包给 `adb shell`，让设备端解析

**adb / 调试**

- `grep -c "<node"` 返回 1 是假象 —— uiautomator XML 是**单行文件**，用 `grep -o ... | wc -l`
- `adb logcat -c` 会清空缓冲区 → **先挂 logcat 再触发**，否则日志被自己擦掉
- 单终端方案：触发后 `sleep 1 && adb logcat -d TAG:I *:S | tail -40`（不加 `-c`）
- `Broadcast completed: result=0` **不代表送达**，只是默认返回码 → 看 logcat
- 包名打错（如少一个字母）与 IntentFilter 漏注册**症状完全相同**：日志一片安静

**Android / 无障碍**

- 无障碍服务改配置或改代码后，**必须去设置里关掉再打开**才生效
- `IntentFilter` 漏 `addAction()` **编译器不报错**，是唯一需要靠眼睛检查的地方
- `printTree` 的 maxDepth 设小了会什么都看不到 —— Settings 的可点条目在第 4–6 层
- `uiautomator dump` 与无障碍服务看到的节点树**不完全一样**（flag 不同），别混用
- **display id 每次都变**（实测 2 / 4 / 5 / 6），必须动态解析
- overlay display 空闲时**镜像主屏**，它是"模拟外接显示器"，不是隔离容器
- scrcpy 创建的虚拟屏**随 scrcpy 进程消亡**，Agent 生命周期需与之绑定或做重连
- 模拟器重启后 `overlay_display_devices` 失效、副屏上的 app 回到主屏 ——
  **每次测试前先跑一次状态确认，不要相信上一次的状态**
- **`findFocus(FOCUS_INPUT)` 会命中 IME 窗口里的按键节点** —— 软键盘也是 display 0 上的一个窗口，
  遍历先到先得会拿到 Gboard 的键。必须跳过 `AccessibilityWindowInfo.TYPE_INPUT_METHOD`（见 E6）
- **空 `EditText` 的 `getText()` 返回 hint 而不是空串** —— 判空需看 `textSelectionStart == -1`
- **`actionList` 里没有某动作 ≠ 该动作不可用** —— `recycler_view` 未登记滚动动作，
  但 `performAction(SCROLL_FORWARD)` 返回 `true` 且真实生效。"向上爬找支持该动作的父节点"
  必须带"爬不到就用原节点"的兜底，否则静默不发（日志 `result=null node=null`）
- **`scroll=true` 不代表此刻有滚动余量** —— 折叠工具栏页面真正滚动的是外层 `ScrollView`，
  内层 `RecyclerView` 可能完全没有滚动范围。重置副屏状态用 `am force-stop` + 重启，别猜容器
- **一个 EditText 的 `isFocused` 为 true，不代表它所在窗口持有 window 焦点** ——
  焦点被别的 display 夺走后 `isFocused` 照样是 `true`（见 E6）。这是 E3 附带发现 2 的延伸

**方法论**

- 命令返回成功 ≠ 结果正确。`uiautomator --display` 静默失败、本地 XML 文件未刷新
  都属此类 → **每个"成功"都要做结果验证**
- 单点测试给虚假安全感 → 验证要跑完整序列（建屏 → 启动 → 多次动作 → 提交）
- **基线与实验轮之间的环境漂移会伪造因果** —— E6 中基线 Run 1 跑完后副屏列表已被滚到底，
  Run 2 的成功一度无法排除"这次动作本来就没夺焦点"。补一轮**同状态、只翻转唯一变量**的
  对照（Run 2b）才把因果钉死。**对照要和实验轮同状态，不是同协议**
- **测量工具本身要先验证** —— E6 的字段计数器一开始锁在提示语常量上，
  若不先验证，会稳定输出"丢字 0"这个正确答案，而它测的根本不是那个框
- 单人操作两件事：**观察自动化 + 动作定时触发（`sleep N &&`）+ 手只负责打字**
- 打字内容用 `1234567890` 循环，丢字 / 乱序一眼可见；随机字符看不出问题
