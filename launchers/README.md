# launchers —— 三个启动器（setup / start / uninstall）

2026-10-10 起，原来那 9 个 `.bat` / `.sh` / `.command` 启动脚本**已经删掉**，
换成这里的 Go 源码编出来的**原生可执行文件**。用户当时的四条要求：

1. 用**跨操作系统的语言**写，分别编译出各平台的可执行文件；
2. **执行之后不要有任何控制台窗口出现**；
3. `novelservices` 也是 Python 起的，**也不能有控制台**；
4. **主窗口退出时，后台服务必须跟着退出**。

## 这份源码不等于发布内容

- **工程根目录**的 `setup.exe` / `start.exe` / `uninstall.exe` 就是本目录编出来的
  （本机平台那一套），**用户双击的就是它们**，也是发布包的直接来源。
- `dist/` 是四个平台的交叉编译产物（12 个文件，约 42MB）——
  发布打包时**整个 `launchers/` 都会被排除**（见 `tools/make_release.py`），
  因为它和 `developers/` 同类：**开发期为产品服务，本身不是产品**。
  ⚠ 而且它**必须排除**：`build.py` 里写着本机 Go 工具链的绝对路径，
  发布自检会当场把它判成"本机路径残留"。

## 怎么编

```bash
.venv/Scripts/python.exe launchers/build.py                  # 四个平台全编 + 本机那套复制到根目录
.venv/Scripts/python.exe launchers/build.py --only linux/amd64
.venv/Scripts/python.exe launchers/build.py --no-root        # 不往根目录复制
```

需要 Go 工具链。默认去 `C:\Users\chao\.workbuddy\binaries\go\1.27.2\go` 找；
换地方就设环境变量 `NWS_GO`。

| 目标 | 产物 | 发布包里的落点 |
|---|---|---|
| `windows-amd64` | `setup.exe` / `start.exe` / `uninstall.exe` | 根目录（打包机是 Windows 时） |
| `linux-amd64` | `setup` / `start` / `uninstall` | `启动器/其他平台/linux/` |
| `darwin-arm64`（Apple Silicon） | 同上 | `启动器/其他平台/macos/` |
| `darwin-amd64`（Intel Mac） | 同上 | `启动器/其他平台/macos-intel/` |

## ★★ 四套产物 → 一个发布包（2026-10-22 改判）

**一个发布包带四个平台的启动器。** 打包不需要再指定平台：

```bash
python tools/make_release.py            # → 发布版本/<config.VERSION>/
```

根目录放**打包机那一套**（本机双击就能用），其余三套进
`启动器/其他平台/<平台>/`。用户换系统时把对应目录那三个文件拷到包根目录即可 ——
`平台说明.md` 会写清楚。

★ 为什么必须"全带"：`launchers/` 整个目录是**按路径排除**的（它是构建工具链，
`build.py` 里写着本机 Go 路径）。只留打包机那套的话，Mac / Linux 用户拿到的包
**根目录三个文件双击没有任何反应，也没有第二个来源** —— 那不是"少个便利"，是"那个平台用不了"。

三个坑（都已经踩过，判据也补齐了）：

1. **`--packages all` 曾经不等于"全平台"** —— 旧语义是"**不换启动器**"，
   根目录留的是打包机那一套。2026-10-11 用户问的「start/setup/uninstall 为何没有其他
   平台的版本」成因就是这个；2026-10-22 起该参数**已删除**，四套无条件全带，
   `tools/verify_release_platforms.py` 的 A3 就钉着"源码里没有 `--packages`"。
2. **同名 ≠ 同平台**：Linux 与 macOS 的启动器都叫 `setup`/`start`/`uninstall`，
   **文件名一个字都证明不了**。`make_release.py` 现在读**魔数**核对
   （Windows `MZ` / Linux `ELF` / macOS Mach-O + cputype），
   四套的落点写进 `.release_manifest.json` 的 `launcher_sets`。
   反例法（`developers/mutate_release_platforms.py`）里有**故意漏放一套**的用例，
   确认自检当场报缺。
3. **两个 macOS 平台不能共用一个目录**（同名不同内容 ⇒ 互相覆盖）。
   所以 `darwin-arm64` 与 `darwin-amd64` 在 `启动器/其他平台/` 下**各占一个子目录**。

另外打包时会自动写一份 **`平台说明.md`** 到包根目录（并在包内 README 顶上插一行横幅）：
包里四个平台都有，但根目录只能是**一个**平台的二进制 —— 不讲清楚，
Mac 用户会以为包坏了。

## 三个入口是同一份源码

`main.go` 里 `var mode` 由编译期注入（`-X main.mode=setup|start|uninstall`），
所以三个 exe 是**同一份逻辑编三次**，行为靠**文件名**分工 ——
写错一个名字，"装"会变成"启动"。有判据钉这一点（`verify_installer` 第 1 节）。

## 每个平台一份，各编各的

- **Windows**：`-ldflags "-H windowsgui"` ⇒ PE 子系统 = **2（GUI）** ⇒ 双击**不分配控制台**。
- **Linux / macOS**：不加那个标志（加了反而坏事，见下）。

## ★★★ 六个"不报错但给你错结果"的坑（都踩过、都写在代码里了）

1. **`-H windowsgui` 只能给 windows 目标加。**
   `GOOS=linux go build -ldflags "-H windowsgui"` → **rc=0、不报错、不警告**，
   产出却是 **Windows PE**（头 4 字节 `4d5a`），丢到 Linux 上根本跑不起来。
   ⇒ `build.py` 按平台分支加，并且**逐个读产物头 4 字节**自检
   （`verify_launchers` 的 A2）；Windows 还多查一条 PE 子系统 = 2（A3）。

2. **顶层没有控制台，不会自动传给子进程。**
   无控制台的父进程起 `python.exe` → Windows **给它新分配一个并显示出来**。
   ⇒ 从这个启动器往下，**每一层**起 console 子进程的地方都要自己声明：
   `tools/launcher_progress.py`（跑 pip）、`tools/platform_install.py`
   （PowerShell / sips / iconutil）、`novelservice.py`（pip / alembic）。

3. **"进程树里有 conhost" ≠ "屏幕上有黑窗"。** `CREATE_NO_WINDOW` 就是
   "有控制台对象、但不显示窗口"。⇒ 判据量的是**桌面上可见的顶层窗口**，
   而且**每次跑都带一个对照组**（故意不带标志起一个，它必须抓到窗口）。

4. **`CREATE_NO_WINDOW` 与 `HideWindow` 都不是冗余的。** 实测：只去掉前一个、
   留着 `HideWindow`，子进程仍然拿得到控制台但不显示窗口；**两个都去掉**才会冒出黑窗。

5. **`os._exit()` 在用过 tkinter 的进程里退不掉。** `ExitProcess` 要跑 DLL 的
   `DllMain(PROCESS_DETACH)`，加载过 Tk 之后**死在那儿**（窗口显示过才算触发）。
   ⇒ `tools/launcher_progress.py` 用 **`TerminateProcess(GetCurrentProcess(), code)`**。
   ⚠ 调它必须给 ctypes 类型：`GetCurrentProcess()` 是 64 位伪句柄，
   默认按 `c_int` 收会**截断成无效句柄**、静默失败。
   （Go 侧还有一道保险：进度窗写完结论 6 秒还不退，就替它收掉。）

6. **Windows 的 `CreateProcess` 不认我们传进去的 `env["PATH"]`**（只看父进程的 PATH）
   ⇒ 从 Python 调 `go` 必须写**绝对路径**（`build.py` 里就是这么做的）。

7. **`*_test.go` 是 Go 的测试专用后缀，正常构建会跳过它。** 三平台共用的那份
   对话框替身不能叫 `dialog_test.go`（第一版就叫这个，症状是
   `undefined: dialogStub`）。现在叫 `dialog_stub.go`。

8. **应用正在运行时 `start.exe` 覆盖不了**（Windows 不让覆盖运行中的映像）。
   `build.py` 因此只拷**这次真编出来的**那几个（照 `made[host]`，不是照 `MODES`——
   否则某个模式编失败时，根目录会变成"新的 setup + 旧的 start"**混搭**，而
   A5「根目录与 dist 逐字节一致」两边都被污染反而看不出来）；拷不动就**说清**
   "关掉应用窗口再重跑一次"并返回非 0。

## 卸载：确认框由**启动器**问，`--yes` 一个都不能少

2026-10-10 用户报的 bug（截图 + `logs/launcher.log`）：
双击 `uninstall.exe` → 「The step "Removing desktop icon / Start Menu entry" did not succeed.」

**根因**：启动器原来是"直接把 `tools/platform_install.py uninstall` 跑起来"，
而那个脚本自己会问 `确认卸载？[y/N]` —— 可启动器起的子进程**没有终端**
（启动器是 GUI 子系统的、进度窗又用 `stdin=DEVNULL`）⇒ `input()` 立刻 EOF
⇒ 当成 "N" ⇒ "已取消"、返回 False ⇒ 退出码 1。
也就是说**双击卸载从来就没成功过**（实测 `platform_install.py uninstall < /dev/null`
稳定 `EXIT=1`）。

**修法**：**谁有窗口谁负责问** —— 启动器弹一个**原生确认框**
（`dialog_windows.go` / `dialog_darwin.go` / `dialog_linux.go` 各一份 `confirm()`，
默认按钮是「否/取消」），问完再带 **`--yes`** 去调子进程。
`--dry-run` 不问（它一个文件都不写，而说明书写的是"先跑预览再决定"）。

`platform_install.py` 那边也补了一刀：**问不出来就明说**
（`没有可以询问的终端 ⇒ 请加 --yes`）—— 不许再把"问不出来"伪装成"用户答了 N"。
⚠ 判"能不能问"**不能只看 `sys.stdin.isatty()`**：Windows 的 `nul` 是**字符设备**，
`_isatty()` 判的就是"是不是字符设备"⇒ `< NUL`、`subprocess.DEVNULL`、
Git-Bash 的 `< /dev/null` **全都报 `isatty()==True`**，可一读就 EOF。
⇒ 只能**真去读一次**，把 EOF 收成 `None`。

## 判据用的**对话框替身**（`dialog_stub.go`）

`notify()` / `confirm()` 是**阻塞**的（`MessageBoxW` / `osascript` / `zenity` 都会
把人顶在那儿等点击）⇒ "从启动器双击一次卸载到底会不会成功"这件事**没法自动跑**，
只能人肉点一遍 —— 而上面那个 bug 正好就长在这条路上。

设了 `NWS_TEST_DIALOG_LOG` 就把"弹框"换成"往那个 JSONL 追加一行
`{kind,title,body,answer}`"；`NWS_TEST_CONFIRM_ANSWER` 决定"用户点了哪个键"
（不设 = 确定）。于是"问没问、点了什么、失败时补没补框"都成了**可断言的事实**。
⇒ 这是让"只能人肉点"的路径第一次有守卫的办法，比"我看过源码，应该没问题"强得多。

## 服务生命周期（三服务表）

项目旁挂着**三座外部创作服务**（都是**增强项**，不在也是被支持的常态）：
MuMuAINovel（写小说）、PenShot（分镜）、PlotPilot（编剧）。三个启动器在不同时刻跟它们打交道，
而"怎么打交道"**只有一份答案**，写在 `services.go` 的那张表里：

| 服务 | 怎么打交道 | 端口读哪 | 跟随退出键 |
|---|---|---|---|
| MuMuAINovel | **直跑**它自己的 `backend/novelservice.py` | `APP_PORT`（**服务自己**的 `.env`） | `MUMU_FOLLOW_APP` |
| PenShot | 走**统一控制器** `novelservices/service_ctl.py` | `PENSHOT_PORT`（**主程序根** `.env`） | `PENSHOT_FOLLOW_APP` |
| PlotPilot | 走**统一控制器** | `PLOTPILOT_PORT`（主程序根 `.env`） | `PLOTPILOT_FOLLOW_APP` |

- **为啥 MuMu 不并进统一控制器**：`novelservice.py` 自己挑解释器、自己建 venv、自己有版本牢笼；
  改走控制器就要在 Go 或控制器里**第二份**实现"挑哪个解释器" —— 两处实现同一件事是这条产品线
  反复吃的亏。所以 MuMu 保持直跑脚本，两个新服务走控制器（控制器再委托各自的桥）。
- **`setup`**：先做**端口体检**，再逐个备运行环境（建 venv / 装依赖），幂等；`--skip-service` 一步都没有。
  - 端口归 setup 配（用户 2026-10-17：「机器上有 Docker，3 个外部服务别跟现有端口冲突」）：
    默认端口**绑得上**就沿用；绑不上（Docker / 别的程序占着）就从原端口往上找一个**能用**的，
    写回**该服务读的那份 `.env`**（MuMu 写它自己的 `backend/.env`，两个新服务写主程序根 `.env`）；
    如果占着端口的是**服务自己**（健康检查通，MuMu 常驻 8001 就是），**不动它**。
    扫描会**跳过另外两个服务正在用的端口**（否则只是把冲突挪给邻居）。
  - 每次都会在日志里留一行 `端口体检：mumu=…，penshot=…，plotpilot=…`（改过的带「已改」）。
- **`start`**：主程序退出后**逐个**停 —— 每个服务各自的 `*_FOLLOW_APP` 各自算，
  **互不影响**（"留着编剧、关掉分镜"是合理配置）。停失败**不改变**主程序退出码。
  ⚠ **并且**要先过"**还有没有别的实例在用**"那道闸（见下面那条）——没人用了才停。
- **`uninstall`**：删快捷方式**之前**逐个停（它们是常驻进程，不停会一直占端口）。
- **服务不由启动器拉起**：交给主程序启动时那条已经跑熟的路
  （`gui/app_flet.py:_maybe_autostart_service`，按 `*_ENABLED × *_AUTOSTART` 三家并行）。
  理由：服务跟着主窗口退出 ⇒ **每次启动都是冷启动**；若启动器还在前面同步等它起来，
  用户每次双击都要先盯一个进度窗等几十秒到几分钟，界面才出来。
- 程序自己也补一刀（甩出去不等），管的是"不经启动器、直接跑 `main_gui.py`"的情形。两刀都是幂等的。
- ★★★ **多实例共享一组服务**（2026-10-28 改判）：三个服务都绑固定端口、端口写在
  同一份 `.env` ⇒ 第二个实例只会收到一句「已经在运行，不重复启动」⇒ **全程只有一组
  服务在跑**。于是"主窗口退出 ⇒ 服务跟着退出"在多实例下的正确说法是：
  **最后一个关的人负责收尸**。
  - 归属由 **`logs/service_users/` 登记表**（引用计数）决定：主程序**启动时登记**、
    **退出时撤销**；**判空**（一个活着的使用者都没有）才真的停。
  - ⚠ 换掉的是 `logs/launcher.pid`（比"文件里那个 pid 是不是我"）：它只防住了
    **先关的**那个，没防住**后关的**那个 —— 而人总是先关掉刚开的那一个、回头继续用
    先前那个 ⇒ 那一次正好把**正在用**的服务掐掉。
  - ★ 判空只看 **pid 死活**，不看"撤销成功没有" ⇒ 实例被强杀/崩溃留下的登记文件
    **自动不算数**（僵尸自愈，不需要清理工序）。
  - 两边各写死一份目录串：Python `util/svc_users.py:DIR_REL`、
    Go `launchers/services.go:svcUsersDir` —— 改名必须两边一起改
    （`tools/verify_svc_users.py` 的 S1/S2 钉着）。
  - ⚠ 判活**不能只看"打不打得开进程"**：父进程还攥着句柄时 `OpenProcess` 对已死的
    进程照样成功 ⇒ 必须再问 `GetExitCodeProcess`（退出码 != 259 就是死了）。
    两边同口径（`_win_alive` / `proc_windows.go:pidAlive`）。
  - ⚠ Windows 上**不许用 `os.kill(pid, 0)` 探活**：那里的 `os.kill` 走
    `TerminateProcess`，`sig=0` = **以退出码 0 终止它** —— 那是杀人。

`followFor` 的决策顺序（从尖到宽）：**逐服务测试钩子 → 全局测试钩子 → `.env` 的 `*_FOLLOW_APP`**，
默认 **true**（与 `config.py` 的 SPEC 一致 —— 不然"程序里显示的"和"启动器实际做的"会不一样）。

## 启动窗口（splash，2026-10-17）

用户原话：「start 的时候虽然没有命令行，但是有一个类似 splash 的窗口，带有 Logo、名字、
『把故事，活一遍』主题语；消息框改成滚动显示的消息条，可以展开为命令行输出，把所有启动
过程中的信息都显示出来，某个步骤出问题能直接看到且启动失败；最后是版本、是否本地运行、
技术平台，背景用背景图的缩略版本。」

- **脚本**：`tools/launcher_splash.py`（tkinter，无边框、置顶）。**整张背景图铺底**，
  Logo/名字/标语/消息条/底栏都**直接压在图上**（不用色块卡片承载组件，也不描边框 ——
  三轮迭代的落点：加边框"否则看不出来" → 去掉底色 → **边框也去掉**）；
  展开的输出区 **14 行 / 218px**、**深色终端底**（2026-10-27 用户点名：「展开之后显示黑色日志」；
  同一天第二轮又点名「日志框又太高了，高度减少 50%、宽度不变」⇒ 436 → 218px）；
  右上角 ✕。
- **标题字体按文件加载**（用户 2026-10-17：「标题的字体不对，要跟开始界面一样」）：
  开始界面是 Flet 用 `page.fonts` **按文件**注册随附字体；tkinter 只能按**族名**找，
  本机装了思源宋体整族 ⇒ `bold` 会挑到 Black，**同一个族名、不同的脸**。
  ⇒ 这里改成用 Pillow 按 `ui_fonts.ui_font_file()`（**开始界面当前那份**）渲染成图片贴上，
  并照开始界面的做法加白色描边 + 合成粗体。Pillow/字体不在 ⇒ 退回按族名，窗口照常出现。
- **消息从哪来**：启动器把自己的日志（`logs/launcher.log`）路径写进 spec，窗口从**末尾**开始 tail ⇒
  下面每一句 `lg.printf` 都会出现在窗口里；`runStepsAll` 把步骤输出**整段**记进日志（最多 200 行），
  所以「详情」里看到的就是命令行的原样输出。
- **什么时候关**：主程序（Flet）把开始界面画出来后写 `NWS_SPLASH_READY` 指定的文件
  （`app_flet.NovelWorldApp._tell_splash_ready`）⇒ 窗口看到就自己关。
  **由界面说了算**，不是启动器掐秒 —— 掐秒要么让人干等、要么窗口先没、界面还没出来。
- **失败**：启动器写 `fail` 文件（`failSplash`）⇒ 窗口底栏上方出现红字、消息条变红、
  **不自动展开**（用户 2026-10-17：「下面消息框默认收起」），点「详情」才看全文；
  启动器**等用户关掉窗口**再退出（`waitSplash`，最多 180 秒）。
- **退出码 0 不算失败**：主程序正常退出但没等到 ready，最常见的是"用户自己关了窗口"——
  只 `lg.printf` 一句，不弹红条（2026-10-17 实测踩过：正常退出被判成启动失败）。
- 底栏与开始界面**同一格式**：`v0.3.1 · 本地运行 · Python + Flet`（版本号从 `config.py` 的
  `VERSION` 读，不另立一份）；右上角 ✕ 随时可关。

**底图 = 从母版裁一块「淡而不花」的**（`tools/make_splash_bg.py`，2026-10-17）。
用户：「现在好像有点花」——因为旧版是把整张 3840×2160 **缩**到 860px，全图的笔墨全挤在一起。
现在改成在母版上滑动窗口打分：亮度均值（高）/ 灰度标准差（低）/ 饱和度（低）/ Sobel 边缘能量（低），
**带朱红印章的窗口直接弃用**（印章跟 Logo 抢眼），收起态取同一块的**上半**（展开时只是"长"一截，
不跳图）。成品必须是 PNG（tkinter 的 `PhotoImage` 吃不下 WebP）。

| 指标 | 旧版（整图缩略） | 现在（裁一块） |
|---|---|---|
| 灰度均值（淡） | 186.5 | **210.7** |
| 灰度标准差（平） | 30.7 | **5.2** |
| 边缘能量（干净） | 29.9 | **4.2** |

> ⚠ 这块窗口是**体验**，不是前置条件：`launcher_splash.py` 不在 / 起不来，`start` 照常直接拉主程序。

## 判据

- `tools/verify_launchers.py` —— **61 项，六组**：
  A 产物格式/子系统 · B **真机无控制台**（带对照组）· C 服务跟随退出（用夹具，不真起服务）·
  D `--selftest` 的决策 · E 进度窗 + **启动窗口**（E5/E5b：真建一次，读它交出的摘要；
  **E5c…E5c-6**：量底图"淡而不花"——整张的亮/平/干净、**文字带单独再量**、与"整图缩略"的
  **行为对照**、**成对**（不是白板）、**没印章**、两张**同源**；
  **E5d**：标题按**哪份字体文件**画，须与 `UI_FONT` 解析出的一致；
  **E5e/E5e-2**：消息条与底栏"一个矩形都没有"＋ 成对"字还在"）·
  **F 卸载**（真跑 沙盒装→取消→卸；**失败时进度窗要留着**、不许替它收尸）。
  C/D 两组靠 `tests/launchers/fixture_ctl/`（**假统一控制器** + 两个**诱饵** `.env`）+
  `stub_app.py`（假主程序）+ `fixture_service/`（MuMu 夹具）摆布。
  ★ 其中 **D8/D8b** 是"**不给任何钩子**"跑真 `.env` 的（把启动器**拷到临时目录**、自制一份 `.env`）——
  真实用户机上没有测试钩子，`.env` 的 `*_FOLLOW_APP` 才是唯一决策来源，而 C 组全靠钩子摆布，
  少了这两条，"钩子之前的代码整个坏光"会一路全绿（反例法实测撞见过）。
  ★ **D9 / F7 / F7b / F7c** 守"**端口**"（用户 2026-10-17：「机器上有 Docker，3 个外部服务
  别跟现有端口冲突，端口在 setup 里检查并配好」）：D9 判"绑得上才算空闲"；F7 真跑 setup，
  证明**被占的端口会改**、**没被占的不许动**、**写到该服务读的那份 `.env`**、
  且**不许抢另外两个服务的端口**。
- `developers/mutate_launchers.py` —— 反例法 **27 组**，逐条把上面的守护点做坏，
  要求**那一条**真的变红（每条都要改源码 → 重编 → 跑 → 还原）。
  ★ 重编只在"**文件被占用**"时重试（C 组真起子进程，上一个没退干净时覆盖 `start.exe`
  会 `PermissionError` ⇒ 跑的是上一版 exe ⇒ 该红的不红，看着像判据没本事）。
  ★ ⑳ 组改的是**资源图**（不用重编）：⑳b（底图换成纯色纸）"淡"的三条照绿、只有**成对**的
  E5c-4 抓得住；⑳d（只有文字带那一截变花，且先把亮度平移到跟淡区一样 ⇒ 整图判据仍绿）
  只有 E5c-2 抓得住 —— 两条都要求**另一条仍然绿**，用来证明判据不是摆设。
  ★ **"编不出来"必须与"构建自检拦下了坏事"分开判**（`build_hard_error()`）——
  变异把源码写坏时判据跑的是**上一版 exe**，报出来的是"期望 F3 变红却没红"，
  一个**指错方向**的诊断（真踩过：替换串把字段分隔的逗号挤进了注释）。
  ★ 替换串**不许挂行尾注释**：被替换的那一段后面紧跟的 `; … {` / `,` 会被注释一起吃进去 ⇒ Go 直接编译失败。
- `tools/verify_external_services.py` + `developers/mutate_external_services.py` —— 两个新服务的
  **"配置"那半**（天机里的「外部创作服务」页签、`*_FOR_SCREENWRITER` / `*_FOR_DIRECTOR` 接管开关）。
- `developers/shoot_launcher_ui.py` —— 重拍说明书里那两张进度窗插图
  （`18_start.png` 已删：启动不再有控制台，那图没有对象了）。
  ⚠ 卸载那张必须带 `--yes`，否则会**停在确认框上**。
