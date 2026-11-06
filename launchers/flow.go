package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// ══════════════════════════════════════════════════════════════════
//  三个入口
// ══════════════════════════════════════════════════════════════════

// runStart：启动（等价于旧的 start.bat / start.sh）
//
// 顺序与旧脚本**只有一处实质差别**：旧脚本在起主程序之前**同步**把创作服务
// 拉起来（`novelservice.py start --timeout 600`，首次要下 470MB 模型）；
// 现在**不在启动器里拉服务**，交给主程序自己那条已经跑熟的路
// （`gui/app_flet.py` 的 `_maybe_autostart_service` → `BR.start_service`，
// 受 `MUMU_AUTOSTART` 控制、失败只提示不拦）。
//
// ★ 为什么这么改（2026-10-17）：现在"服务跟着主窗口一起退出"，
//   意味着**每次启动都是冷启动**。若启动器还在前面同步等它起来，
//   启动器就要自己实现一遍"挑解释器 / 建 venv / 等健康检查"，
//   而那份逻辑已经在桥里（且带 pid 文件、端口反查这些踩过坑的细节）。
//   交给主程序，两者只维护一份。
//
// ★★ 2026-10-23（用户：「我希望在启动界面把这几个服务都拉起来成功之后再进入
//   开始界面」）—— **同一句话的落点换了，启动器仍然不需要动**：
//   拉起服务的还是主程序，只是主程序现在**等服务有结论之后才写 `ready`**，
//   于是 splash 一直亮着、把进度说出来（`→ 正在拉起 PlotPilot（2/3）…`、
//   `→ PlotPilot 已就绪（2/3）`，带一个每秒在走的秒数），
//   都处理完才放人进开始界面。
//   ⚠ 这个"放行"由界面写（`NWS_SPLASH_READY`），启动器只负责等文件出现 ——
//     谁真的知道"好了"，就由谁来说，这一点从 2026-10-17 起没变。
//   ⚠ 有上界（`_SPLASH_SVC_BUDGET`，10 分钟）：超时后主程序照样放行，
//     服务在后台继续拉。所以**启动器这边不需要再加超时**，
//     `waitSplash` 那 180 秒只在失败路径上用到。
//
// [EN] ── The launcher still does **not** start the services itself; the point of contact
// [EN] moved, though (2026-10-23, user: "pull these services up in the splash, then enter the
// [EN] start screen"): the main program now writes `ready` only after every service has a
// [EN] verdict, so the splash stays up and narrates it. The launcher only waits for that file --
// [EN] whoever truly knows "it is ready" gets to say so, unchanged since 2026-10-17.
// [EN] ⚠ The wait is bounded on the UI side (`_SPLASH_SVC_BUDGET`, 10 min); on timeout the UI
// [EN] releases anyway and the services keep coming up, so no extra timeout is needed here
// [EN] (`waitSplash`'s 180s is only on the failure path).
func runStart(appDir string, lg *logger, args []string) int {
	reinstall := hasFlag(args, "--reinstall")
	pass := stripFlag(args, "--reinstall")

	py, ok := findPython(lg)
	if !ok {
		return noPythonDlg()
	}
	lg.printf("Python：%s（窗口版 %s）", py.exe, py.win)

	// ── ① 启动窗口（splash）：没有控制台，但启动过程的每一步都在里面 ──
	//    用户 2026-10-17：「虽然没命令行，但要有一个类似 splash 的窗口，把启动过程中的
	//    信息都显示出来，某个步骤出问题能直接看到且启动失败」。它从 `logs/launcher.log`
	//    的**末尾**开始 tail ⇒ 本函数下面每一句 `lg.printf` 都会出现在窗口里。
	// [EN] ① Splash: no console, but every startup step is visible in it. It tails
	// [EN] `logs/launcher.log` **from the end** ⇒ every `lg.printf` below shows up there.
	splash, readyPath, failPath := startSplash(appDir, lg, py)
	defer stopSplash(splash, failPath)

	// ── ② 运行环境（步骤在 splash 里逐行显示，不再另弹进度窗）──
	// [EN] ② Runtime steps stream into the splash instead of a separate progress window
	plan := planAppEnv(appDir, py, reinstall, false)
	if len(plan.Steps) > 0 {
		code := runStepsAll(appDir, lg, plan.Steps)
		if code != 0 {
			failSplash(lg, failPath, fmt.Sprintf("准备运行环境失败（退出码 %d）", code))
			waitSplash(splash, 180*time.Second)
			return code
		}
		if plan.NeedInstall {
			// 与旧脚本同一个约定：`.venv/.deps-ok` 在，以后就跳过"试导入"。
			_ = os.WriteFile(filepath.Join(appDir, venvRel, depsMarkerRel),
				[]byte("ok\n"), 0o644)
		}
	} else {
		lg.printf("运行环境已就绪，跳过安装")
	}

	_, venvWin, ok2 := venvPython(appDir)
	if !ok2 {
		failSplash(lg, failPath, "运行环境没准备好（找不到 .venv）")
		waitSplash(splash, 180*time.Second)
		notify(zhApp, enApp,
			"运行环境没准备好（找不到 .venv）。\n\n请先运行 setup，或加 --reinstall 重装依赖。",
			"The runtime is not ready (.venv not found).\n\n"+
				"Run setup first, or pass --reinstall to reinstall the dependencies.", true)
		return 1
	}

	entry := appEntryPath(appDir)
	if !isFile(entry) {
		failSplash(lg, failPath, "找不到主程序："+entry)
		waitSplash(splash, 180*time.Second)
		notify(zhApp, enApp, "找不到主程序：\n"+entry,
			"Main program not found:\n"+entry, true)
		return 1
	}

	// ── ② 收尸归属：**不再**由启动器自己登记 ──
	//   2026-10-28 起交给主程序的登记表（`logs/service_users/`，见
	//   `services.go:anyUserAlive` 与 Python 侧 `util/svc_users.py`）。
	//   ⚠ 换掉的是 `launcher.pid`（比"文件里那个 pid 是不是我"）：它只防住了
	//     **先关的**那个，没防住**后关的**那个 —— 而人总是先关掉刚开的那一个、
	//     回头继续用先前那个 ⇒ 那一次正好把**正在用**的服务掐掉。
	// [EN] ── ② Who reaps the services: **no longer** registered by the launcher ──
	// [EN] Since 2026-10-28 this belongs to the app's registry (`logs/service_users/`,
	// [EN] see `services.go:anyUserAlive` and the Python side `util/svc_users.py`).
	// [EN] ⚠ Replacing `launcher.pid` ("is the pid in the file mine"): it guarded
	// [EN] **the one that closes first** but not **the one that closes last** -- and
	// [EN] people close the window they just opened and go back to the earlier one
	// [EN] => that is exactly when the **in-use** service gets cut off.

	// ── ③ 主程序：**挂在这儿等它退出** ──
	// 启动器自己是 GUI 子系统进程（没有窗口），挂着不占任何界面。
	lg.printf("启动主程序：%s %s", venvWin, strings.Join(append([]string{entry}, pass...), " "))
	code := runWait(venvWin, append([]string{entry}, pass...), appDir,
		filepath.Join(appDir, "logs", "launcher_gui.log"))
	lg.printf("主程序已退出，退出码 %d", code)

	// ── ③.5 主程序退出时 splash 还没被"就绪"关掉 ──
	//    ⚠ 只有**非 0 退出**才算失败。退出码 0 却没等到 ready，最常见的是
	//      "用户自己把窗口关了 / 启动中途就退出"—— 那不是错误，不该弹红条
	//      （2026-10-17 实测踩过：正常退出也被判成"启动失败"）。
	// [EN] ── ③.5 The splash was never closed by "ready" ──
	// [EN] ⚠ Only a **non-zero exit** is a failure. Exit 0 without ready is most often
	// [EN] "the user closed the window / quit during startup" -- not an error, and it must
	// [EN] not raise a red bar (hit on 2026-10-17: a normal exit was judged as "failed").
	if readyPath != "" && !isFile(readyPath) {
		if code != 0 {
			failSplash(lg, failPath, fmt.Sprintf("主程序在显示窗口之前就退出了（退出码 %d）", code))
			waitSplash(splash, 180*time.Second)
		} else {
			lg.printf("主程序已退出（没有收到『窗口已显示』的信号 —— 多半是启动中途被关掉了）")
		}
	}

	// ── ④ 主窗口退出 ⇒ 后台服务一并退出（用户 2026-10-10 的硬要求）──
	//    逐个服务来：各自的 `*_FOLLOW_APP` 各自算（见 `followFor`），
	//    互不影响 —— 用户完全可能"留着编剧服务、关掉分镜服务"。
	// [EN] ── ④ The main window exited ⇒ the background services exit with it
	// [EN]    (a hard requirement from the user, 2026-10-10) ──
	// [EN]    Service by service: each `*_FOLLOW_APP` decides on its own (see
	// [EN]    `followFor`) -- "keep the screenwriter, drop the storyboard
	// [EN]    service" is a perfectly reasonable configuration.
	if anyUserAlive(appDir) {
		lg.printf("还有别的实例在用创作服务 ⇒ 交给最后关的那个收，本次不动")
		return code
	}
	for _, s := range services {
		if !followFor(appDir, s) {
			lg.printf("%s = false：%s 保持常驻（下次启动更快）", s.followKey, s.zh)
			continue
		}
		step, ok := stopStep(appDir, py, s)
		if !ok {
			lg.printf("%s 不在（目录或运行环境缺失），不用停", s.zh)
			continue
		}
		lg.printf("主程序已退出 ⇒ 停掉%s", s.zh)
		if c := runStepNow(lg, step, 90000); c != 0 {
			// 停失败**不改变**主程序的退出码 —— 服务是增强项，
			// 它的收尾成败不该让主程序"看起来像崩了"。
			// [EN] A stop failure **does not change** the main program's exit
			// [EN] code -- services are enhancements; their cleanup outcome
			// [EN] must not make the main program look like it crashed.
			lg.printf("停%s：退出码 %d（不影响主程序退出码）", s.zh, c)
		}
	}
	return code
}

// runSetup：安装（等价于旧的 setup.bat / setup.sh）
func runSetup(appDir string, lg *logger, args []string) int {
	skipSvc := hasFlag(args, "--skip-service")
	pass := stripFlag(args, "--skip-service")

	py, ok := findPython(lg)
	if !ok {
		return noPythonDlg()
	}

	installer := filepath.Join(appDir, filepath.FromSlash(installerRel))
	if !isFile(installer) {
		notify(zhApp+" · 安装", enApp+" · Setup",
			"找不到装机脚本：\n"+installer,
			"Installer script not found:\n"+installer, true)
		return 1
	}

	var steps []jobStep
	// ① 端口体检（用户 2026-10-17：「机器上有 Docker，3 个外部服务别跟现有端口冲突，
	//    在 setup 初始化配置的时候检查并配好」）。
	//    必须在**备环境之前**：`.env` 里的端口一旦定下来，后面的 prepare 与
	//    服务启动都读它。`--skip-service` 的语义是"别碰外部服务" ⇒ 这一步也跳过。
	// [EN] ① Port check (user, 2026-10-17: "there's Docker on the machine; the three
	// [EN] external services must not collide with ports in use -- check and configure
	// [EN] them in setup when initializing"). It must run **before** preparing the
	// [EN] runtime: once the port in `.env` is settled, prepare and starting read it.
	// [EN] `--skip-service` means "don't touch external services" ⇒ this step is skipped too.
	if !skipSvc {
		ensureAllServicePorts(appDir, lg)
	}
	// ② 再准备外部服务的运行环境（三个服务逐个来，表在 `services.go`）。
	//    放在**安装阶段**的用意与旧脚本一致：让**第一次启动**不必卡几分钟建环境。
	//    这一步幂等，齐了就秒过；失败不拦主程序（服务是增强项）。
	// [EN] ① First prepare the external services' runtime (all three, one by
	// [EN] one; the table is in `services.go`). Doing this at **install time**
	// [EN] matches the old scripts: the **first start** then doesn't stall for
	// [EN] minutes building environments. Idempotent -- a complete one passes
	// [EN] in seconds; failure does not block the main program (services are
	// [EN] enhancements).
	steps = append(steps, servicePrepareSteps(appDir, lg, py, skipSvc)...)
	// ② 建快捷方式
	steps = append(steps, jobStep{
		Label: bi("创建桌面图标 / 开始菜单", "Creating desktop icon / Start Menu entry"),
		Argv:  append([]string{py.exe, installer, "install"}, pass...),
		Cwd:   appDir,
	})
	return runJob(appDir, lg, py,
		bi("安装", "Setup"),
		bi("正在安装「小说世界AI模拟」…（首次会装依赖，可能要几分钟）",
			"Installing Novel World AI Simulator… (the first run installs dependencies and may take a few minutes)"),
		steps)
}

// runUninstall：卸载（等价于旧的 uninstall.bat / uninstall.sh）
//
// ★★ 确认这一步的位置是这一版最要紧的改动（2026-10-10 用户报的 bug）
// -------------------------------------------------------------------
// 原来这里是"直接把 `platform_install.py uninstall` 跑起来"，而那个脚本自己
// 有一道 `input('确认卸载？[y/N]')`。但启动器起的子进程**没有终端**
// （启动器是 GUI 子系统的、进度窗又用 `stdin=DEVNULL`）⇒ `input()` 立刻 EOF
// ⇒ 当成 "N" ⇒ 每次都"已取消"、退出码 1 ⇒ 用户看到
// 「The step "Removing desktop icon / Start Menu entry" did not succeed.」
//
// 实测（`platform_install.py uninstall < /dev/null`）：稳定 `EXIT=1`。
// 也就是说**双击卸载从来就没成功过**，而且报的还是"这一步没成功"这种
// 指不到根因的话。
//
// ⇒ 谁有窗口谁负责问：**启动器问**（`confirm` 弹原生框），问完了把 `--yes`
//   传给子进程让那道交互提示跳过。`--yes` 是**必须**加的，不是可选优化。
func runUninstall(appDir string, lg *logger, args []string) int {
	py, ok := findPython(lg)
	if !ok {
		return noPythonDlg()
	}
	installer := filepath.Join(appDir, filepath.FromSlash(installerRel))
	if !isFile(installer) {
		notify(zhApp+" · 卸载", enApp+" · Uninstall",
			"找不到装机脚本：\n"+installer,
			"Installer script not found:\n"+installer, true)
		return 1
	}

	// ── ① 先问。放在**动任何东西之前**（含"停服务"）：说"取消"就得真的什么都没发生。──
	// `--dry-run` 不问：那一条**一个文件都不写**（`uninstall()` 里在动手之前就
	// 提前返回了），而说明书写的是"先跑 `--dry-run` 再决定" —— 让预览也弹一次
	// 确认框，等于劝退那个最该用的习惯。
	if !hasFlag(args, "--yes") && !hasFlag(args, "--dry-run") {
		if !confirm(zhApp+" · 卸载", enApp+" · Uninstall",
			"将删除桌面图标和「开始菜单」里的快捷方式。\n\n"+
				"你写的小说数据（项目文件夹）始终保留，不会被删。\n\n"+
				"确定要卸载吗？",
			"This removes the Desktop icon and the Start Menu shortcuts.\n\n"+
				"Your novel projects are always kept and will NOT be deleted.\n\n"+
				"Uninstall now?") {
			lg.printf("卸载：用户在确认框里选了「取消」⇒ 什么都不做")
			return 0
		}
	}

	var steps []jobStep
	// 先停服务：它们是后台常驻进程，不停会一直占着端口（旧脚本也是先停再卸）。
	// 逐个服务来（表在 `services.go`）—— 不在的（发布包常态）自然跳过。
	// [EN] Stop the services first: they are background-resident processes that
	// [EN] keep holding their ports (the old scripts also stopped before
	// [EN] uninstalling). Service by service (table in `services.go`) -- absent
	// [EN] ones (normal in a release bundle) are skipped.
	for _, s := range services {
		if step, ok := stopStep(appDir, py, s); ok {
			steps = append(steps, step)
		}
	}
	steps = append(steps, jobStep{
		Label: bi("删除桌面图标 / 开始菜单", "Removing desktop icon / Start Menu entry"),
		// ⚠ `--yes` 一个字都不能少：上面那个确认框已经问过了，而子进程**没有终端**，
		//   它自己那道 `input()` 只会得到 EOF（= "取消"）。
		Argv: append([]string{py.exe, installer, "uninstall", "--yes"}, args...),
		Cwd:  appDir,
	})
	return runJob(appDir, lg, py,
		bi("卸载", "Uninstall"),
		bi("正在卸载「小说世界AI模拟」…", "Uninstalling Novel World AI Simulator…"),
		steps)
}

// ══════════════════════════════════════════════════════════════════
//  运行环境：要做什么
// ══════════════════════════════════════════════════════════════════

type envPlan struct {
	Steps       []jobStep
	NeedInstall bool
}

// planAppEnv：算出"把运行环境弄好"需要哪几步（**只算不做**）。
//
// 只算不做这件事有两个用处：`--selftest` 能报告"缺什么就会补什么"（判据据此
// 检查决策逻辑，不用真装一遍依赖）；调用方也能在步骤为空时**完全不弹窗**
// （已经装好的机器每次启动都是安静的一条路径）。
//
// `commit=false` 时连"试导入成功后补标记"这个副作也不做（selftest 要只读）。
func planAppEnv(appDir string, py pyInfo, reinstall, commit bool) envPlan {
	var p envPlan
	_, _, haveVenv := venvPython(appDir)
	if !haveVenv {
		p.Steps = append(p.Steps, jobStep{
			Label: bi("创建独立运行环境（.venv）", "Creating the isolated runtime (.venv)"),
			Argv:  []string{py.exe, "-m", "venv", venvRel},
			Cwd:   appDir,
		})
	}
	depsOK := haveVenv && !reinstall
	if depsOK {
		if isFile(filepath.Join(appDir, venvRel, depsMarkerRel)) {
			return p // 有标记 ⇒ 一步都不用做
		}
		// 没有标记时**先试导入**（旧脚本同款做法）：装过的人不用再等一次 pip。
		vp, _, _ := venvPython(appDir)
		if _, code := runCapture(vp, []string{"-c", importCheck}, appDir, 120000); code == 0 {
			if commit {
				_ = os.WriteFile(filepath.Join(appDir, venvRel, depsMarkerRel),
					[]byte("ok\n"), 0o644)
			}
			return p
		}
	}
	vp, _, ok := venvPython(appDir)
	if !ok {
		vp = py.exe // venv 刚建好/正要建：用系统 Python 去 pip 装（venv 建完就有自己的了）
	}
	if !haveVenv {
		// venv 还没建，pip 得等它建完才存在 —— 这一步只能由"建完之后的解释器"跑，
		// 而进度窗是**串行**执行步骤的，所以这里直接写成 venv 里的解释器路径。
		if e, _, ok2 := venvVenvExe(appDir); ok2 {
			vp = e
		}
	}
	p.Steps = append(p.Steps,
		jobStep{Label: bi("升级 pip", "Upgrading pip"),
			Argv: []string{vp, "-m", "pip", "install", "--upgrade", "pip", "-i", pipMirror},
			Cwd:  appDir},
		jobStep{Label: bi("安装依赖（首次约 1-3 分钟）",
			"Installing dependencies (about 1-3 minutes on first run)"),
			Argv: []string{vp, "-m", "pip", "install", "-r", reqRel, "-i", pipMirror},
			Cwd:  appDir},
	)
	p.NeedInstall = true
	return p
}

// venvVenvExe：**假定 .venv 已建好**时它里面的解释器路径（不检查是否存在）。
func venvVenvExe(appDir string) (string, string, bool) {
	if runtime.GOOS == "windows" {
		e := filepath.Join(appDir, venvRel, "Scripts", "python.exe")
		w := filepath.Join(appDir, venvRel, "Scripts", "pythonw.exe")
		return e, w, true
	}
	e := filepath.Join(appDir, venvRel, "bin", "python")
	return e, e, true
}

// appEntryPath：主程序入口（`NWS_TEST_APP` 可覆盖，判据用它换成一个 stub）。
func appEntryPath(appDir string) string {
	if p := strings.TrimSpace(os.Getenv(envTestApp)); p != "" {
		if filepath.IsAbs(p) {
			return p
		}
		return filepath.Join(appDir, filepath.FromSlash(p))
	}
	return filepath.Join(appDir, appEntryRel)
}

// （2026-10-28 删掉了这里的 `claimLock` —— 它写 `logs/launcher.pid`，
//  只防住"先关的那个"；收尸归属现在由主程序的登记表决定，
//  见 `services.go:anyUserAlive`。留着就是没人用的一份第二实现。）
// [EN] (2026-10-28: `claimLock` was removed from here -- it wrote
// [EN] `logs/launcher.pid` and only guarded "the one that closes first"; who
// [EN] reaps is now decided by the app's registry, see `services.go:anyUserAlive`.
// [EN] Keeping it would be an unused second implementation.)

// ══════════════════════════════════════════════════════════════════
//  跑服务脚本的解释器（服务目录本身在 `services.go` 的表里）
// [EN] Interpreter for running service scripts (the directories themselves
// [EN] are in the table in `services.go`)
// ══════════════════════════════════════════════════════════════════

// servicePy：跑 `novelservice.py` 用哪个解释器。
//
// `windowed=true` 时**优先 pythonw.exe** —— 这是"服务端也不留控制台"的落点，
// 理由见 `quietCommand` 的注释（venv 的 python.exe 是 launcher，会把
// CREATE_NO_WINDOW 丢掉）。
// 找不到就退回 `fallback`（`""` 表示调用方要求"必须有"，那就由调用方判断）。
func servicePy(dir, fallback string, windowed bool) string {
	if p := strings.TrimSpace(os.Getenv(envTestSvcPy)); p != "" {
		return p
	}
	var cands []string
	if runtime.GOOS == "windows" {
		if windowed {
			cands = []string{
				filepath.Join(dir, ".venv", "Scripts", "pythonw.exe"),
				filepath.Join(dir, ".venv", "Scripts", "python.exe"),
			}
		} else {
			cands = []string{
				filepath.Join(dir, ".venv", "Scripts", "python.exe"),
				filepath.Join(dir, ".venv", "Scripts", "pythonw.exe"),
			}
		}
	} else {
		cands = []string{filepath.Join(dir, ".venv", "bin", "python")}
	}
	for _, c := range cands {
		if isFile(c) {
			return c
		}
	}
	return fallback
}

// ══════════════════════════════════════════════════════════════════
//  进度窗（把活儿交给 tools/launcher_progress.py 跑）
// ══════════════════════════════════════════════════════════════════

type jobStep struct {
	Label string   `json:"label"`
	Argv  []string `json:"argv"`
	Cwd   string   `json:"cwd"`
}

type jobSpec struct {
	Title string    `json:"title"`
	Intro string    `json:"intro"`
	Steps []jobStep `json:"steps"`
	Log   string    `json:"log"`
}

type jobResult struct {
	GUI        bool   `json:"gui"`
	Code       int    `json:"code"`
	FailedStep string `json:"failed_step"`
	Log        string `json:"log"`
	Err        string `json:"err"`
	//: 进度窗**还在跑**（它一开工就先落一份 `running:true`）。
	//  用来看"它是崩了"还是"它压根没起来"，也是下面那道保险的判据。
	Running bool `json:"running"`
	//: 进度窗的**窗口已经关掉**了（`mainloop()` 返回之后落的盘）。
	//  ★ 这一条是 `waitProgress` 能分清下面这件事的唯一依据：
	//    "失败时用户还开着窗口在读日志"（不能收尸）vs
	//    "窗口已经没了、进程却卡在退出上"（该收尸）。
	//  没有它就只能拿"等了多久"当判据，而那个判据会把用户正在看的窗口杀掉。
	Closed bool `json:"closed"`
}

// runJob：把若干步骤交给**进度窗**执行，返回总退出码。
//
// ★ 为什么是 Python 在干活、Go 只当调度：pip / venv / 装机脚本本来就要跑成
//   子进程，而"把子进程的输出实时滚进一个窗口"这件事在 Go 里要自己搭 GUI
//   （三个平台各一套）。项目里本来就依赖 Python，tkinter 又是标准库 ——
//   于是：**Go 负责"起得干净（无控制台）"，Python 负责"看得见"**。
//
// 没有窗口可用时（Linux 上没装 python3-tk 之类）**不影响功能**：
// 退回静默执行，再用原生消息框报结果 —— 干活的能力不能依赖于有没有 GUI。
func runJob(appDir string, lg *logger, py pyInfo, title, intro string, steps []jobStep) int {
	if len(steps) == 0 {
		return 0
	}
	script := filepath.Join(appDir, filepath.FromSlash(progressRel))
	if !isFile(script) {
		lg.printf("找不到 %s ⇒ 静默执行", progressRel)
		return runStepsQuiet(appDir, lg, steps)
	}
	base := filepath.Join(os.TempDir(),
		fmt.Sprintf("nws-job-%d-%d", os.Getpid(), time.Now().UnixNano()))
	specPath, resPath := base+".json", base+".result.json"
	defer func() {
		_ = os.Remove(specPath)
		_ = os.Remove(resPath)
	}()

	spec := jobSpec{Title: title, Intro: intro, Steps: steps,
		Log: filepath.Join(appDir, "logs", "launcher_job.log")}
	b, _ := json.MarshalIndent(spec, "", "  ")
	if err := os.WriteFile(specPath, b, 0o644); err != nil {
		lg.printf("写 job 文件失败：%v ⇒ 静默执行", err)
		return runStepsQuiet(appDir, lg, steps)
	}

	prog := py.win
	if prog == "" {
		prog = py.exe
	}
	lg.printf("进度窗：%s %s", prog, script)
	cmd := quietCommand(prog,
		[]string{script, "--job", specPath, "--result", resPath}, appDir)
	if err := cmd.Start(); err != nil {
		lg.printf("进度窗起不来（%v）⇒ 静默执行", err)
		code := runStepsQuiet(appDir, lg, steps)
		reportQuiet(title, code, lg)
		return code
	}
	killed := waitProgress(appDir, lg, cmd, resPath)

	res, got := readJobResult(resPath)
	if !got {
		lg.printf("进度窗没留下结果 ⇒ 静默执行一遍（保证活儿一定干了）")
		code := runStepsQuiet(appDir, lg, steps)
		reportQuiet(title, code, lg)
		return code
	}
	if !res.GUI {
		lg.printf("进度窗不可用（%s）⇒ 静默执行", res.Err)
		code := runStepsQuiet(appDir, lg, steps)
		reportQuiet(title, code, lg)
		return code
	}
	// 窗口已经在用户眼前显示了成败；只在**下面两种情况**才再补一个"走开了也能看见"
	// 的原生框：
	//   ① 进度窗压根没弹出来（`!res.GUI`，上面那条已经处理了）；
	//   ② 它写完结论却没退、被我们替它收掉了（`killed`）—— 那就等于用户可能没看清。
	//
	// ★ 正常失败**不补框**。失败时那个窗口是**故意**留着的（等用户看完日志点
	//   「关闭」），再弹一个是同一条消息看两遍；而第一版正是这么做的：窗口 6 秒后
	//   被杀掉、然后才弹框，用户眼前是"窗口一闪就没了，日志区也先没了"。
	if res.Code != 0 && killed {
		notify(zhApp+" · "+titleZh(title), enApp+" · "+titleEn(title),
			fmt.Sprintf("「%s」这一步没成功。\n\n日志：\n%s",
				failedZh(res.FailedStep), orDefault(res.Log, lg.path)),
			fmt.Sprintf("The step \"%s\" did not succeed.\n\nLog:\n%s",
				failedEn(res.FailedStep), orDefault(res.Log, lg.path)), true)
	}
	return res.Code
}

// titleZh / titleEn / failedZh / failedEn：进度窗的标题与失败步骤名是**双语文案**
// （`bi()` 拼出来的 "中文\n英文"），弹原生框时要拆回单语，否则框里会中英混排两次。
// 拆不开就原样返回 —— 宁可显示两行，也不要显示空白。
func splitBi(s string) (string, string) {
	i := strings.Index(s, "\n")
	if i < 0 {
		return s, s
	}
	return strings.TrimSpace(s[:i]), strings.TrimSpace(s[i+1:])
}

func titleZh(s string) string  { a, _ := splitBi(s); return a }
func titleEn(s string) string  { _, b := splitBi(s); return b }
func failedZh(s string) string { return titleZh(s) }
func failedEn(s string) string { return titleEn(s) }

// waitProgress：等进度窗结束，**并且不把所有希望押在"它会自己退"上**。
// 返回值 `killed` = 我们替它收了尸（调用方据此决定要不要再补一个原生框）。
//
// ★ 为什么要多这一手（2026-10-10 实测出来的）：这台机器上，一个显示过窗口的
//   tkinter 进程**退出时会卡在 `ExitProcess` 的 DLL 卸载**里（`os._exit` 都退不掉，
//   详见 `tools/launcher_progress.py` 的 `_hard_exit`）。那边已经改成
//   `TerminateProcess` 绕开它，但这类"子进程写完结论却不退"的故障**表现极恶**：
//   用户眼里就是"装到一半卡死"，而且不会有人来报 —— 只会说"它没反应"。
//
// ★★ 判据是"**窗口还在不在**"，不是"等了几秒"（这一版改对的地方）
// ----------------------------------------------------------------
// 第一版只看"结论文件写了没有"，于是一旦写完就再给 6 秒、还不退就替它收掉。
// 这在**失败**那一路上是错的：失败时窗口本来就**故意**留着等用户看完日志
// 再点「关闭」。结果是"用户刚看到失败，窗口 6 秒后就被杀了"，然后才弹原生框 ——
// 同一条消息看两遍，日志区还先没了。用户报的那张截图后面就跟着两行
// 「进度窗写完结论后仍未退出 ⇒ 代为结束」。
//
// 现在分四档，`closed`（窗口已关）这一条由 `launcher_progress.py` 在
// `mainloop()` 返回之后落盘 —— 它是唯一能把"用户还开着窗口在看"和
// "窗口关了、进程却卡在退出上"分开的东西：
//
//	还在跑（`running:true`）        → 不打扰（pip 装十分钟是正常的）；
//	成功（`code == 0`）            → 窗口本来就该 3 秒后自己关 ⇒ 给 6 秒宽限，再收尸；
//	失败且 `closed:false`          → **窗口开着等用户** ⇒ 一直等，不收尸；
//	`closed:true` 却没退            → 屏幕上已经什么都没有了 ⇒ 给它宽限，然后收尸。
//
// 最后那一档是防"窗口关了但进程卡住"：那种情况下启动器自己**没有窗口**，
// 用户只会觉得"点了卸载什么都没发生"。
func waitProgress(appDir string, lg *logger, cmd *exec.Cmd, resPath string) (killed bool) {
	exited := make(chan struct{})
	go func() { _ = cmd.Wait(); close(exited) }()
	var grace time.Time
waitLoop:
	for {
		select {
		case <-exited:
			break waitLoop
		case <-time.After(400 * time.Millisecond):
			r, ok := readJobResult(resPath)
			if !ok || r.Running {
				continue // 还在跑（或者还没开始写）—— 不打扰它
			}
			if !r.Closed && r.Code != 0 {
				continue // ★ 失败：窗口开着给用户看日志，等他自己点「关闭」
			}
			if grace.IsZero() {
				grace = time.Now().Add(6 * time.Second)
				continue
			}
			if time.Now().After(grace) {
				pid := 0
				if cmd.Process != nil {
					pid = cmd.Process.Pid
				}
				lg.printf("进度窗的窗口已经关了、进程却没退 ⇒ 代为结束（pid=%d）", pid)
				killTree(cmd, lg)
				killed = true
				<-exited
			}
		}
	}
	_ = appDir
	return killed
}

// killTree：收掉进度窗那条子进程链。
func killTree(cmd *exec.Cmd, lg *logger) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	if runtime.GOOS == "windows" {
		// `/T` 连它拉起的子进程（pip 之类）一起收，`/F` 强杀。
		out, code := runCapture("taskkill",
			[]string{"/F", "/T", "/PID", strconv.Itoa(cmd.Process.Pid)}, "", 30000)
		if code != 0 {
			lg.printf("taskkill 退出码 %d %s", code, firstLine(out))
		}
		return
	}
	_ = cmd.Process.Kill()
}

func reportQuiet(title string, code int, lg *logger) {
	tz, te := splitBi(title)
	if code == 0 {
		notify(zhApp+" · "+tz, enApp+" · "+te, "已完成。", "Done.", false)
		return
	}
	notify(zhApp+" · "+tz, enApp+" · "+te,
		fmt.Sprintf("没能完成（退出码 %d）。\n\n日志：\n%s", code, lg.path),
		fmt.Sprintf("Could not finish (exit code %d).\n\nLog:\n%s", code, lg.path), true)
}

func orDefault(s, def string) string {
	if strings.TrimSpace(s) == "" {
		return def
	}
	return s
}

func readJobResult(p string) (jobResult, bool) {
	var r jobResult
	b, err := os.ReadFile(p)
	if err != nil {
		return r, false
	}
	if err := json.Unmarshal(b, &r); err != nil {
		return r, false
	}
	return r, true
}

// runStepsQuiet：没有窗口可用时，自己按顺序跑完（输出全进日志）。
func runStepsQuiet(appDir string, lg *logger, steps []jobStep) int {
	for _, s := range steps {
		if len(s.Argv) == 0 {
			continue
		}
		dir := s.Cwd
		if dir == "" {
			dir = appDir
		}
		lg.printf("静默执行：%s", s.Label)
		out, code := runCapture(s.Argv[0], s.Argv[1:], dir, 3600000)
		if strings.TrimSpace(out) != "" {
			for _, ln := range tailLines(out, 6) {
				lg.printf("    %s", ln)
			}
		}
		if code != 0 {
			lg.printf("  ✗ %s（退出码 %d）", s.Label, code)
			return code
		}
	}
	return 0
}

func tailLines(s string, n int) []string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	ls := strings.Split(strings.TrimRight(s, "\n"), "\n")
	if len(ls) > n {
		ls = ls[len(ls)-n:]
	}
	out := make([]string, 0, len(ls))
	for _, l := range ls {
		if strings.TrimSpace(l) != "" {
			out = append(out, strings.TrimSpace(l))
		}
	}
	return out
}

// ══════════════════════════════════════════════════════════════════
//  启动 splash（2026-10-17 用户要求）
// [EN] Startup splash (user request, 2026-10-17)
// ══════════════════════════════════════════════════════════════════
//
// 「虽然没命令行，但要有一个类似 splash 的窗口」——它做什么、怎么拿到消息，见
// `tools/launcher_splash.py` 的文档串。这里只负责三件事：
//   ① 把 spec（版本 / 本地运行 / 技术平台 / 背景 / 日志 / ready / fail）写成 JSON 并起窗口；
//   ② 失败时写 `fail` 文件（窗口据此显示红条并**留着不关**）；
//   ③ 退出时收拾（还活着就杀掉）。
//
// ★ `NWS_SPLASH_READY`：主程序（Flet）窗口一显示就写这个文件，splash 看到就自己关。
//   把"什么时候算起来了"交给真正知道的那一方（界面），而不是让启动器猜时间。

//: splash 脚本（与 progress 同目录）
// [EN] the splash script (same folder as progress)
const splashRel = "tools/launcher_splash.py"

// splashSpec：传给 `launcher_splash.py --spec` 的那份 JSON。
// [EN] the JSON handed to `launcher_splash.py --spec`.
type splashSpec struct {
	Title    string `json:"title"`
	Subtitle string `json:"subtitle"`
	Logo     string `json:"logo"`
	Bg       string `json:"bg"`
	Log      string `json:"log"`
	Ready    string `json:"ready"`
	Fail     string `json:"fail"`
	// Bye: 启动窗口**自己关掉**时写的记号（主程序据此把隐藏的主窗口放出来）。
	// ★ 2026-10-24：主窗口在服务就绪前是真的不可见，"用户点 ✕"这条路要靠它通知。
	// [EN] Bye: written when the splash **closes itself** (the UI uses it to reveal its hidden
	// [EN] main window). ★ 2026-10-24: the main window is really invisible until the services are
	// [EN] ready, so the "user presses the cross" path needs this notice.
	Bye      string `json:"bye"`
	Version  string `json:"version"`
	Mode     string `json:"mode"`
	Platform string `json:"platform"`
}

//: Python 版本号只问一次（每个进程一次 50ms，问三次没意义）
// [EN] ask for the Python version once per process
var pyVerCached = ""

func pyVersion(py pyInfo) string {
	if pyVerCached != "" {
		return pyVerCached
	}
	out, code := runCapture(py.exe, []string{
		"-c", "import sys;print('%d.%d.%d' % sys.version_info[:3])"}, "", 20000)
	if code == 0 && strings.TrimSpace(out) != "" {
		pyVerCached = tailLines(out, 1)[0]
	} else {
		pyVerCached = "?"
	}
	return pyVerCached
}

// readAppVersion：从 `config.py` 里读**产品版本号**（`VERSION = "0.3.2"`）。
//
// ★ 为什么不拿编译期的 `version`（那串日期+哈希）：用户要的是开始界面上那个
//   `v0.3.2` —— 它跟界面同源，写在 `config.py` 一处。这里只做一次正则式的读取，
//   不 import 那个模块（会连着加载 .env / 一堆依赖）。读不到就退回 `version`。
// [EN] Read the **product version** from `config.py` (`VERSION = "0.3.2"`).
// [EN] ★ Why not the build-time `version` (date+hash): the user wants the `v0.3.2` shown on
// [EN] the start screen -- same source as the UI, written in exactly one place. We do a
// [EN] simple read here, no import (that would load .env and a pile of dependencies).
// [EN] Falls back to the build version when unreadable.
func readAppVersion(appDir string) string {
	b, err := os.ReadFile(filepath.Join(appDir, "config.py"))
	if err != nil {
		return version
	}
	for _, ln := range strings.Split(string(b), "\n") {
		t := strings.TrimSpace(ln)
		if !strings.HasPrefix(t, "VERSION") || !strings.Contains(t, "=") {
			continue
		}
		v := strings.TrimSpace(strings.SplitN(t, "=", 2)[1])
		v = strings.Trim(v, `"'`+"` ")
		if v != "" {
			return v
		}
	}
	return version
}

// startSplash：起那块"书封"窗口。返回 (进程, ready 文件, fail 文件)；
// 起不来就返回 nil（启动照旧继续 —— splash 是体验，不是前置条件）。
// [EN] Launch the splash. Returns (process, ready file, fail file); nil when it can't start
// [EN] (the app still launches -- the splash is UX, not a precondition).
func startSplash(appDir string, lg *logger, py pyInfo) (*exec.Cmd, string, string) {
	script := filepath.Join(appDir, filepath.FromSlash(splashRel))
	if !isFile(script) {
		lg.printf("没有 %s ⇒ 不显示启动窗口", splashRel)
		return nil, "", ""
	}
	dir := filepath.Join(os.TempDir(), fmt.Sprintf("nws-splash-%d", os.Getpid()))
	if err := os.MkdirAll(dir, 0o755); err != nil {
		lg.printf("建 splash 临时目录失败（%v）⇒ 不显示启动窗口", err)
		return nil, "", ""
	}
	ready := filepath.Join(dir, "ready")
	fail := filepath.Join(dir, "fail")
	bye := filepath.Join(dir, "bye")
	specPath := filepath.Join(dir, "spec.json")
	_ = os.Remove(ready)
	_ = os.Remove(fail)
	_ = os.Remove(bye)

	mode := "本地运行"
	for _, a := range os.Args[1:] {
		if a == "--mock" {
			mode = "演示模式（不联网）"
		}
	}
	spec := splashSpec{
		Title:    "小说世界 AI 模拟",
		Subtitle: "—— 把故事，活一遍 ——",
		Logo:     filepath.Join(appDir, "assets", "images", "start_logo_96.png"),
		Bg:       filepath.Join(appDir, "assets", "images", "title_bg_splash.png"),
		Log:      filepath.Join(appDir, "logs", "launcher.log"),
		Ready:    ready,
		Fail:     fail,
		Bye:      bye,
		Version:  readAppVersion(appDir),
		Mode:     mode,
		// 与开始界面底栏**一字不差**（`v0.3.1 · 本地运行 · Python + Flet`）
		// [EN] Character-for-character the same as the start screen footer.
		Platform: "Python + Flet",
	}
	b, _ := json.MarshalIndent(spec, "", "  ")
	if err := os.WriteFile(specPath, b, 0o644); err != nil {
		lg.printf("写 splash spec 失败（%v）⇒ 不显示启动窗口", err)
		return nil, "", ""
	}

	cmd := quietCommand(pyW(py), []string{script, "--spec", specPath, "--from-end", "1"}, appDir)
	if err := cmd.Start(); err != nil {
		lg.printf("splash 起不来（%v）⇒ 直接启动主程序", err)
		return nil, ready, fail
	}
	// 主程序（Flet）读这个环境变量：窗口一显示就写 ready ⇒ splash 自己关
	_ = os.Setenv("NWS_SPLASH_READY", ready)
	// ★★ 2026-10-23（用户：「服务没启动成功不要显示后续启动界面」）：
	//   主程序要能**主动让 splash 变红并留住**，否则它手里只有一个 ready 通道，
	//   遇到"服务没起来"只能二选一：要么装没事放人进去（用户不要），
	//   要么谁都不通知、干等着（用户会以为卡死）。
	//   所以再给它一条 fail 通道 —— 用的就是本函数已经建好的那个 fail 文件，
	//   主程序往里写一句，splash 负责变成红条并**不关自己**。
	// [EN] ★★ 2026-10-23 (user: "if the services did not start, do not show the following start
	// [EN] screen"): the UI must be able to **turn the splash red and keep it up**. With only the
	// [EN] `ready` channel it could either pretend everything is fine (the user said no) or notify
	// [EN] nobody and hang (which reads as a freeze). So hand it the fail file this function
	// [EN] already creates: the UI writes one line, the splash shows a red bar and stays open.
	_ = os.Setenv("NWS_SPLASH_FAIL", fail)
	// ★★ 2026-10-24（用户：「所有服务拉起来再打开开始界面，在这之前不要打开」）：
	//   主窗口现在在服务就绪前**真的不可见**。于是"失败了、用户点 ✕"这条路
	//   必须有人告诉主程序 —— 否则 splash 一关就剩一片桌面。
	//   这个文件由 splash 在 `close()` 时写，主程序在那儿等它。
	// [EN] ★★ 2026-10-24 (user: "open the start screen only after all services are up; do not open
	// [EN] it before that"): the main window is now **really invisible** until the services are
	// [EN] ready, so the "failed, user presses the cross" path needs a notice -- otherwise closing
	// [EN] the splash leaves a bare desktop. The splash writes this file from `close()`.
	_ = os.Setenv("NWS_SPLASH_BYE", bye)
	lg.printf("启动窗口：%s", splashRel)
	// 窗口从日志**末尾**开始 tail ⇒ 上面那几行（程序目录 / Python）它看不到，
	// 这里把"这一轮是谁、什么版本、跑在哪"再报一遍（也正是底栏要显示的东西）。
	// [EN] The window tails from the log's **end**, so the lines above (app dir / Python)
	// [EN] are invisible to it; restate "which run, which version, on what" here --
	// [EN] exactly what the footer shows.
	lg.printf("版本 %s · %s", version, mode)
	lg.printf("技术平台：%s（Python %s · %s）", spec.Platform, pyVersion(py), runtime.GOOS)
	lg.printf("主程序：%s", appEntryPath(appDir))
	lg.printf("开始准备运行环境…")
	return cmd, ready, fail
}

// failSplash：告诉 splash「这一步挂了」，并在日志里留一句（窗口会把它显示成红条）。
// [EN] Tell the splash "this step failed" and leave a line in the log (shown as a red bar).
func failSplash(lg *logger, failPath, reason string) {
	lg.printf("✗ %s", reason)
	if failPath == "" {
		return
	}
	_ = os.WriteFile(failPath, []byte(reason+"\n"), 0o644)
}

// waitSplash：等用户看完关掉（最多 `d`）；超时就替它收掉，别把启动器卡死。
// [EN] Wait for the user to close it (up to `d`); kill it afterwards so the launcher never hangs.
func waitSplash(cmd *exec.Cmd, d time.Duration) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	done := make(chan struct{})
	go func() {
		_, _ = cmd.Process.Wait()
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(d):
		_ = cmd.Process.Kill()
	}
}

// stopSplash：退出时收拾（还活着就杀掉）。
// [EN] Cleanup on exit (kill it if still alive).
func stopSplash(cmd *exec.Cmd, failPath string) {
	_ = failPath
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = cmd.Process.Kill()
}

// runStepsAll：跑步骤并把**全部**输出写进日志（splash 靠日志显示"全套命令行输出"）。
//
// 与 `runStepsQuiet` 只差"记多少行"：那边只留尾巴 6 行（够判成败、不刷屏），
// 这边留到 200 行 —— 用户要在这个窗口里看到报错原文，截断就没意义了。
// [EN] Run steps and log **all** output (the splash shows it). Differs from `runStepsQuiet`
// [EN] only in how many lines are kept: 6 there (enough to judge, no spam), 200 here --
// [EN] the user asked to see the error text in this window, truncating defeats that.
func runStepsAll(appDir string, lg *logger, steps []jobStep) int {
	for _, s := range steps {
		if len(s.Argv) == 0 {
			continue
		}
		dir := s.Cwd
		if dir == "" {
			dir = appDir
		}
		lg.printf("▶ %s", s.Label)
		out, code := runCapture(s.Argv[0], s.Argv[1:], dir, 3600000)
		lines := strings.Split(strings.ReplaceAll(out, "\r\n", "\n"), "\n")
		shown := 0
		for _, ln := range lines {
			ln = strings.TrimRight(ln, "\r")
			if strings.TrimSpace(ln) == "" {
				continue
			}
			if shown >= 200 {
				lg.printf("    …（还有 %d 行，见完整日志）", len(lines)-shown)
				break
			}
			lg.printf("    %s", ln)
			shown++
		}
		if code != 0 {
			lg.printf("  ✗ %s（退出码 %d）", s.Label, code)
			return code
		}
	}
	return 0
}

func noPythonDlg() int {
	notify(zhApp, enApp,
		"没有找到 Python。\n\n本程序需要 Python 3.10 或更高版本：\n"+
			"https://www.python.org/downloads/\n\n"+
			"安装时请勾选「Add Python to PATH」，然后重新运行。",
		"Python not found.\n\nThis app needs Python 3.10 or newer:\n"+
			"https://www.python.org/downloads/\n\n"+
			"Tick \"Add Python to PATH\" during setup, then run it again.", true)
	return 1
}
