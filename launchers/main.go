// 小说世界AI模拟 · 跨平台启动器（setup / start / uninstall）
//
// 为什么是 Go
// -----------
// 需求是「一份源码、编出三个平台的原生可执行文件、跑起来**不出现任何控制台窗口**」。
// 三条硬指标只有 Go 能同时满足：
//   - 交叉编译：`GOOS=windows|linux|darwin` 一个环境变量的事（纯标准库、不用 CGO）；
//   - 无控制台：Windows 上加 `-H windowsgui`（PE 子系统 = 2）就是 GUI 程序，
//     双击**不会分配控制台**；
//   - 单文件无运行时：2-3 MB 静态链接，不拖 Python / Node 运行时进来。
//
// Rust 出局：在 Windows 上编 macOS 需要 Apple SDK（osxcross），走不通。
// Python + PyInstaller 出局：**根本不能交叉编译**，必须在三个系统各构建一次。
//
// ★★ 一个实测到的坑：`-H windowsgui` 只能给 windows 目标加（2026-10-10）
// ---------------------------------------------------------------------
//
//	GOOS=linux go build -ldflags "-H windowsgui"   → rc=0、**不报错、不警告**，
//	                                                 但产出的是个 Windows PE（头 4 字节 4d5a）！
//	                                                 丢到 Linux 上根本跑不起来。
//	GOOS=linux go build -ldflags "-s -w"           → 正常 ELF（7f454c46）✓
//	GOOS=windows go build -ldflags "-H windowsgui" → PE 子系统 = 2（GUI，无控制台）✓
//
// 这正是本项目反复记的那类**"不报错、但给你错结果"**的坑。构建脚本
// `launchers/build.py` 按平台分支加这个标志，一个字都不能省；`tools/verify_launchers.py`
// 会**逐个读产物头 4 字节**把它钉住。
//
// 三个入口
// --------
//   同一份源码编三次，`-X main.mode=setup|start|uninstall` 决定行为。
//   为什么不做成一个 exe 加子命令：用户拿到的是"双击某个文件"，
//   三个名字对应三个动作比"记参数"可靠得多；而三种模式共用同一份代码，
//   也就不会出现"三个脚本各改各的、越改越不像"。
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// mode 由编译期注入：`-X main.mode=setup`。默认 start。
var mode = "start"

// version 由编译期注入（构建脚本写"日期+源文件哈希"）。
var version = "dev"

// 相对工程根目录的固定路径（与三个旧脚本 .bat/.sh 里的完全一致）。
const (
	appEntryRel   = "main_gui.py"
	venvRel       = ".venv"
	depsMarkerRel = ".deps-ok"
	reqRel        = "requirements.txt"
	pipMirror     = "https://mirrors.aliyun.com/pypi/simple"
	//: venv 里"依赖齐了吗"的探针，与旧 start.bat 的 IMPORT_CHECK 一致。
	importCheck = "import flet, yaml, docx, httpx, PIL, chardet"
	//: 装机脚本（创建桌面图标 / 开始菜单），仍然是 Python —— 它是纯逻辑，
	//  没有"要有窗口"的需求，重写成 Go 只会白白多一份要维护的分支。
	installerRel = "tools/platform_install.py"
	//: 进度窗（tkinter）。只在真的要装东西、或要跑几分钟的时候才用得上。
	progressRel = "tools/launcher_progress.py"
	//: 外部创作服务的路径/开关/端口不在这里写死 —— 它们在 `services.go`
	//  的服务表里（三个服务各一行，新增服务只加一行）。
	// [EN] : The external services' paths / switches / ports are NOT hardcoded
	// [EN] here -- they live in the service table in `services.go` (one row per
	// [EN] service; adding a service adds one row).
)

// 测试钩子：只在**环境变量**里生效，正常运行路径不可能被误触发。
// 判据（`tools/verify_launchers.py`）靠它们把"停服务"这件事换成夹具，
// 否则每验一次都要真起一遍创作服务（首次要下 470MB 模型）。
// 逐服务的钩子（目录 / follow）在 `services.go` 的表里，按 id 各一份。
const (
	envTestApp     = "NWS_TEST_APP"        // 覆盖主程序入口（指向一个 stub）
	envTestSvcDir  = "NWS_TEST_SERVICE_DIR" // 覆盖 MuMu 服务目录（既有的钩子）
	envTestSvcPy   = "NWS_TEST_SERVICE_PY"  // 覆盖跑 novelservice.py 的解释器
	envTestSvcPort = "NWS_TEST_SERVICE_PORT"
	envTestFollow  = "NWS_TEST_FOLLOW_APP" // 覆盖"关程序时要不要停服务"那条决策（全局）
	envTestCtl     = "NWS_TEST_SERVICE_CTL" // 覆盖统一控制器（指向夹具）
)

func main() {
	os.Exit(run())
}

//: 给用户看的双语文案（见 `bi`）。
const (
	zhApp = "小说世界AI模拟"
	enApp = "Novel World AI Simulator"
)

// bi：一段"中文 + 英文"的文案（中文在前、英文在后，各占一行）。
//
// 本项目的既有约定是"任何给用户看的文案都中英都写"：旧的三对 `.bat`/`.sh`
// 就是这么写的，`tools/verify_script_bilingual.py` 也一直守着它 ——
// 换成启动器之后，那条判据改成守这里（B 组）。
// 为什么不让启动器按系统语言挑一种：**挑错的那一半人就只剩外语可看**；
// 而这些都是低频、一次性的提示，两种都写最省事、也最不会出错。
//
// 步骤标签、进度窗的标题/说明都用它。判据要求每一处**两个参数都给全**、
// 并且**英文那一半里不许出现中文** —— 于是"漏译一半"在源码层面就被挡住了。
func bi(zh, en string) string { return zh + "\n" + en }

func run() (code int) {
	defer func() {
		// 启动器自己崩了也要让人看见 —— 无控制台的进程"默默死掉"是最难查的。
		if r := recover(); r != nil {
			notify(zhApp+" · 启动器出错", enApp+" · Launcher error",
				fmt.Sprintf("启动器内部错误：%v\n\n模式：%s", r, mode),
				fmt.Sprintf("Internal launcher error: %v\n\nMode: %s", r, mode), true)
			code = 9
		}
	}()

	appDir, err := exeDir()
	if err != nil {
		notify(zhApp, enApp, "拿不到程序所在目录："+err.Error(),
			"Cannot locate the program folder: "+err.Error(), true)
		return 9
	}
	// 与旧脚本的 `cd /d "%~dp0"` 同义：所有相对路径都以**程序所在目录**为基准，
	// 而不是"用户从哪儿双击的"。
	if err := os.Chdir(appDir); err != nil {
		notify(zhApp, enApp, "切换工作目录失败："+err.Error(),
			"Cannot switch the working directory: "+err.Error(), true)
		return 9
	}

	lg := openLog(appDir)
	lg.printf("══ 启动器 %s · 模式 %s · %s/%s ══", version, mode, runtime.GOOS, runtime.GOARCH)
	lg.printf("程序目录：%s", appDir)

	args := os.Args[1:]

	// ── 判据用的只读 / 半只读入口（正常用户不会碰到）──
	if out, ok := flagValue(args, "--selftest"); ok {
		return selftest(appDir, lg, out)
	}
	if secs, ok := flagValue(args, "--spawn-hold"); ok {
		out, _ := flagValue(args, "--out")
		return spawnHold(appDir, lg, secs, out)
	}

	switch mode {
	case "setup":
		return runSetup(appDir, lg, args)
	case "uninstall":
		return runUninstall(appDir, lg, args)
	default:
		return runStart(appDir, lg, args)
	}
}

// ══════════════════════════════════════════════════════════════════
//  小工具
// ══════════════════════════════════════════════════════════════════

// exeDir：**可执行文件**所在目录（不是"当前目录"）。
//
// 先 `EvalSymlinks`：用户可能从"桌面快捷方式 / 开始菜单"启动，
// 而快捷方式的目标就是真实路径，解一次符号链接保证拿到的是真身那一层。
func exeDir() (string, error) {
	p, err := os.Executable()
	if err != nil {
		return "", err
	}
	if r, err := filepath.EvalSymlinks(p); err == nil {
		p = r
	}
	return filepath.Dir(p), nil
}

// logger：无控制台也能留痕。写 `logs/launcher.log`，同时尽量写 stderr
// （从终端跑时能就地看见；没有终端时写失败，忽略）。
type logger struct {
	f    *os.File
	path string
}

func openLog(appDir string) *logger {
	dir := filepath.Join(appDir, "logs")
	_ = os.MkdirAll(dir, 0o755)
	p := filepath.Join(dir, "launcher.log")
	f, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return &logger{path: p}
	}
	return &logger{f: f, path: p}
}

func (l *logger) printf(format string, a ...any) {
	line := time.Now().Format("2006-01-02 15:04:05") + "  " + fmt.Sprintf(format, a...) + "\n"
	if l != nil && l.f != nil {
		_, _ = l.f.WriteString(line)
		_ = l.f.Sync()
	}
	if l != nil {
		_, _ = os.Stderr.WriteString(line)
	}
}

func (l *logger) close() {
	if l != nil && l.f != nil {
		_ = l.f.Close()
	}
}

func isFile(p string) bool {
	st, err := os.Stat(p)
	return err == nil && !st.IsDir()
}

func isDir(p string) bool {
	st, err := os.Stat(p)
	return err == nil && st.IsDir()
}

// flagValue：取 `--name 值` 或 `--name=值`。
func flagValue(args []string, name string) (string, bool) {
	for i, a := range args {
		if a == name {
			if i+1 < len(args) {
				return args[i+1], true
			}
			return "", false
		}
		if strings.HasPrefix(a, name+"=") {
			return a[len(name)+1:], true
		}
	}
	return "", false
}

func hasFlag(args []string, name string) bool {
	for _, a := range args {
		if a == name || strings.HasPrefix(a, name+"=") {
			return true
		}
	}
	return false
}

func stripFlag(args []string, name string) []string {
	out := make([]string, 0, len(args))
	for _, a := range args {
		if a == name || strings.HasPrefix(a, name+"=") {
			continue
		}
		out = append(out, a)
	}
	return out
}

// envOr：读环境变量，空则用默认值。
func envOr(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

// ══════════════════════════════════════════════════════════════════
//  .env 读取
// ══════════════════════════════════════════════════════════════════

// readEnvFile：极简 .env 解析（`KEY=VALUE`，支持引号，`#` 起始行算注释）。
//
// ⚠ 刻意**不**做变量插值、不 `export` 到本进程环境：这里只用来读两个值
// （跟随退出开关 / 服务端口）。做全了就要跟 `config.py` 的行为对齐，
// 而"两套 .env 解析"正是最容易悄悄不一致的那种东西。
func readEnvFile(path string) map[string]string {
	out := map[string]string{}
	b, err := os.ReadFile(path)
	if err != nil {
		return out
	}
	for _, raw := range strings.Split(string(b), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		i := strings.Index(line, "=")
		if i <= 0 {
			continue
		}
		k := strings.TrimSpace(line[:i])
		v := strings.TrimSpace(line[i+1:])
		if len(v) >= 2 {
			if (v[0] == '"' && v[len(v)-1] == '"') || (v[0] == '\'' && v[len(v)-1] == '\'') {
				v = v[1 : len(v)-1]
			}
		}
		out[k] = v
	}
	return out
}

// followService 已按服务表泛化成 `followFor(appDir, s)`（见 `services.go`）——
// "关主程序时要不要一并停掉创作服务"从此是**逐服务**的决策：
// 每个服务有自己的 `*_FOLLOW_APP` 键、自己的测试钩子。
// [EN] followService was generalized per the service table into
// [EN] `followFor(appDir, s)` (see `services.go`) -- "stop the services when
// [EN] the main program closes" is now a **per-service** decision: each service
// [EN] has its own `*_FOLLOW_APP` key and its own test hook.

// truthy：与 `config.py` 的 `b()` 同一套认法；**空 = 真**（那是 SPEC 的默认值）。
func truthy(v string) bool {
	switch strings.ToLower(v) {
	case "0", "false", "no", "off", "none":
		return false
	}
	return true
}

// ══════════════════════════════════════════════════════════════════
//  --selftest：判据用的只读体检（**不做任何改动**）
// ══════════════════════════════════════════════════════════════════

type selftestReport struct {
	Mode         string      `json:"mode"`
	Version      string      `json:"version"`
	GOOS         string      `json:"goos"`
	GOARCH       string      `json:"goarch"`
	AppDir       string      `json:"app_dir"`
	HasConsole   bool        `json:"has_console"`
	Python       string      `json:"python"`
	PythonW      string      `json:"pythonw"`
	PythonFound  bool        `json:"python_found"`
	VenvExe      string      `json:"venv_exe"`
	VenvOK       bool        `json:"venv_ok"`
	DepsMarker   bool        `json:"deps_marker"`
	ProgressOK   bool        `json:"progress_script"`
	InstallerOK  bool        `json:"installer_script"`
	AppEntry     string      `json:"app_entry"`
	AppEntryOK   bool        `json:"app_entry_ok"`
	//: 外部服务：**逐服务**一份（表在 `services.go`）。判据据此检查
	//  "目录不在就不碰它""端口读对了地方""follow 各自独立"这些决策。
	// [EN] : External services: **one entry per service** (table in
	// [EN] `services.go`). The assertions check "don't touch it when the
	// [EN] directory is absent", "the port is read from the right place" and
	// [EN] "each follow switch is independent" from this.
	Services     []svcReport `json:"services"`
	ControllerOK bool        `json:"controller_script"`
	ServiceSteps []string    `json:"service_steps"`
	AppEnvSteps  []string    `json:"app_env_steps"`
	TestHooks    []string    `json:"test_hooks"`
	Dir          string      `json:"cwd"`
}

// svcReport：一个外部服务在 selftest 时刻的状态（只读快照）。
// [EN] svcReport: one external service's state at selftest time (read-only
// [EN] snapshot).
type svcReport struct {
	ID         string `json:"id"`
	Dir        string `json:"dir"`
	Present    bool   `json:"present"`
	Controller bool   `json:"controller"` //: 走 service_ctl.py 的（两个新服务）
	Port       int    `json:"port"`
	PortBusy   bool   `json:"port_busy"` //: 端口**绑不上**（被占着 —— Docker/别的程序）
	Healthy    bool   `json:"healthy"`
	Follow     bool   `json:"follow"`
}

func selftest(appDir string, lg *logger, out string) int {
	rep := selftestReport{
		Mode: mode, Version: version, GOOS: runtime.GOOS, GOARCH: runtime.GOARCH,
		AppDir: appDir, HasConsole: hasConsole(),
		ProgressOK:  isFile(filepath.Join(appDir, filepath.FromSlash(progressRel))),
		InstallerOK: isFile(filepath.Join(appDir, filepath.FromSlash(installerRel))),
	}
	if wd, err := os.Getwd(); err == nil {
		rep.Dir = wd
	}
	if py, ok := findPython(lg); ok {
		rep.Python, rep.PythonW, rep.PythonFound = py.exe, py.win, true
	}
	if e, w, ok := venvPython(appDir); ok {
		rep.VenvExe, rep.VenvOK = e, true
		_ = w
		rep.DepsMarker = isFile(filepath.Join(appDir, venvRel, depsMarkerRel))
	}
	rep.AppEntry = appEntryPath(appDir)
	rep.AppEntryOK = isFile(rep.AppEntry)

	rep.ControllerOK = isFile(ctlPath(appDir))
	for _, s := range services {
		r := svcReport{ID: s.id, Controller: s.ctl}
		r.Dir = svcDir(appDir, s)
		r.Present = svcPresent(appDir, s)
		r.Port = svcPort(appDir, s)
		// 端口**绑不上** = 被占着（Docker / 别的程序 / 服务自己）。
		// 只读探一次，不改任何东西 —— selftest 是"体检"，不治病。
		// [EN] **Cannot bind** = occupied (Docker / another program / the service
		// [EN] itself). Read-only probe; selftest is a checkup, it doesn't treat.
		r.PortBusy = !portUsable(r.Port)
		r.Follow = followFor(appDir, s)
		if r.Present {
			r.Healthy = healthOK(r.Port, s.healthPath)
		}
		rep.Services = append(rep.Services, r)
	}

	// 计划出来的步骤（**不执行**）—— 判据靠它检查"缺什么就会补什么"。
	for _, s := range planAppEnv(appDir, pyInfoOrEmpty(lg), false, false).Steps {
		rep.AppEnvSteps = append(rep.AppEnvSteps, s.Label)
	}
	for _, s := range servicePrepareSteps(appDir, lg, pyInfoOrEmpty(lg), false) {
		rep.ServiceSteps = append(rep.ServiceSteps, s.Label)
	}

	hooks := []string{envTestApp, envTestSvcDir, envTestSvcPy,
		envTestSvcPort, envTestFollow, envTestCtl}
	for _, s := range services {
		hooks = append(hooks, s.followHook)
		if s.dirHook != "" && s.dirHook != envTestSvcDir {
			hooks = append(hooks, s.dirHook)
		}
		if s.portHook != "" && s.portHook != envTestSvcPort {
			hooks = append(hooks, s.portHook)
		}
	}
	for _, k := range hooks {
		if v := os.Getenv(k); v != "" {
			rep.TestHooks = append(rep.TestHooks, k+"="+v)
		}
	}

	b, _ := json.MarshalIndent(rep, "", "  ")
	if err := os.WriteFile(out, b, 0o644); err != nil {
		lg.printf("写 selftest 失败：%v", err)
		return 1
	}
	lg.printf("selftest → %s", out)
	return 0
}

func pyInfoOrEmpty(lg *logger) pyInfo {
	p, _ := findPython(lg)
	return p
}

// spawnHold：**真机**验证"起子进程不会冒出控制台窗口"。
//
// 判据这么用它：`start.exe --spawn-hold 8 --out x.json` —— 启动器用**和正常
// 路径完全一样的方式**起一个会睡 8 秒的子进程，把父子 pid 写进 x.json，
// 等子进程结束才退出。判据在有子进程活着的那段时间里枚举**后代进程**，
// 断言里面**没有 conhost.exe**。
//
// ★ 为什么必须这样测：`python.exe` 是控制台子系统程序，父进程没有控制台时
//   Windows 会**给它新分配一个**（2026-10-10 实测出来的根因，就是用户看到的
//   那个关不掉的黑窗）。这件事**只看源码看不出来、只看退出码更看不出来** ——
//   只有"后代里有没有 conhost"是硬证据。
func spawnHold(appDir string, lg *logger, secs, out string) int {
	py, ok := findPython(lg)
	if !ok {
		lg.printf("spawn-hold：没找到 Python")
		return 1
	}
	n := 8.0
	if f, err := strconv.ParseFloat(strings.TrimSpace(secs), 64); err == nil {
		n = f
	}
	exe := py.exe
	if py.win != "" {
		exe = py.win // 与 `runWait` 起主程序时同一条路径（pythonw 优先）
	}
	prog := fmt.Sprintf("import time;time.sleep(%.3f)", n)
	cmd := quietCommand(exe, []string{"-c", prog}, appDir)
	if err := cmd.Start(); err != nil {
		lg.printf("spawn-hold：起子进程失败 %v", err)
		return 1
	}
	child := 0
	if cmd.Process != nil {
		child = cmd.Process.Pid
	}
	lg.printf("spawn-hold：父=%d 子=%d 时长=%.1fs 解释器=%s", os.Getpid(), child, n, exe)
	if out != "" {
		b, _ := json.MarshalIndent(map[string]any{
			"launcher_pid": os.Getpid(), "child_pid": child,
			"seconds": n, "interpreter": exe, "mode": mode,
		}, "", "  ")
		_ = os.WriteFile(out, b, 0o644)
	}
	_ = cmd.Wait()
	lg.printf("spawn-hold：子进程已退出")
	return 0
}
