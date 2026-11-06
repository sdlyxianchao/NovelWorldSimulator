package main

// ══════════════════════════════════════════════════════════════════
//  外部创作服务：一张表，三个启动器共用
// [EN] External creation services: one table, shared by the three launchers
// ══════════════════════════════════════════════════════════════════
//
// 为什么是一张表
// ---------------
// 项目旁挂着三个外部服务（都是**增强项**，不在也不该让启动器报错）：
// MuMuAINovel（写小说）、PenShot（分镜）、PlotPilot（编剧）。
// 三个启动器都要在不同时刻跟它们打交道：
//
//	setup     → 备好各自的运行环境（建 venv、装依赖）
//	start     → 主窗口退出时按 `*_FOLLOW_APP` 逐个停掉
//	uninstall → 删快捷方式之前逐个停掉
//
// 而"怎么跟某个服务打交道"**只有一份答案**：跑它自己的脚本（MuMu，
// 见 `novelservices/MuMuAINovel/backend/novelservice.py`，里面全是
// 版本牢笼 / 建表 / 端口反查这类踩过坑的逻辑，启动器不重写），
// 或者走统一控制器（两个新服务，见 `novelservices/service_ctl.py`，
// 它再去委托服务自己的桥 —— 桥里才有 pid 文件 / 健康检查那套）。
//
// ★ 为什么 MuMu 不并进统一控制器（2026-10-17）：
//   `novelservice.py` 自己挑解释器、自己建 venv、自己有版本牢笼。
//   让启动器改走控制器，就要在 Go 或控制器里**第二份**实现"挑哪个解释器"，
//   而两处实现同一件事正是这条产品线反复吃的亏。所以：
//   MuMu 保持"启动器直跑它的脚本"（测试钩子 `NWS_TEST_SERVICE_DIR`
//   的夹具机制完全不动），两个新服务走控制器。
//
// English:
// Why one table
// --------------
// Three external services hang off the project (all **enhancements**: their
// absence must never make the launcher error): MuMuAINovel (novel writing),
// PenShot (storyboard), PlotPilot (screenwriting). The three launchers deal
// with them at different moments:
//
//	setup     → prepare each one's runtime (venv + deps)
//	start     → when the main window exits, stop each per its `*_FOLLOW_APP`
//	uninstall → stop each before removing the shortcuts
//
// And "how to talk to a service" has **exactly one answer**: run its own
// script (MuMu -- see `novelservices/MuMuAINovel/backend/novelservice.py`,
// full of pitfall-specific logic like the Python-version cage, schema init
// and port reverse lookup; the launcher does not re-implement it), or go
// through the unified controller (the two new services -- see
// `novelservices/service_ctl.py`, which delegates to each service's own
// bridge, where the pid-file / health-check machinery lives).
//
// ★ Why MuMu is not folded into the unified controller (2026-10-17):
//   `novelservice.py` picks its own interpreter, builds its own venv and
//   keeps its own version cage. Routing it through the controller would mean a
//   **second** implementation of "which interpreter", and two implementations
//   of one thing is a recurring loss on this product line. So: MuMu keeps
//   "the launcher runs its script directly" (the `NWS_TEST_SERVICE_DIR`
//   fixture mechanism stays untouched), the two new services go through the
//   controller.

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// extSvc：一个外部服务的全部"启动器需要知道的事"。
//
// 字段名就是注释，不逐条译英文了 —— 这张表的用法在上面那段说明里。
// [EN] One external service, everything "the launcher needs to know".
// [EN] The field names are the comments; the usage is in the note above.
type extSvc struct {
	id        string //: 稳定标识（mumu / penshot / plotpilot），判据与测试钩子都认它
	zh        string //: 日志里的中文名
	dirRel    string //: 服务目录（相对程序根目录）
	dirHook   string //: 覆盖目录的测试钩子（环境变量名）
	script    string //: 服务自己的脚本名（ctl 服务留空 —— 它们没有自己的脚本）
	ctl       bool   //: true = 走 `novelservices/service_ctl.py`（两个新服务）
	prepLabel string //: setup 步骤标签（bi() 拼的双语）
	stopLabel string //: 停止步骤标签（bi() 拼的双语）
	followKey string //: 主程序 `.env` 里"跟随退出"的键（`*_FOLLOW_APP`）
	followHook string //: 覆盖 follow 决策的测试钩子（逐服务，优先于全局那个）
	portKey   string //: 端口键
	portHook  string //: 覆盖端口的测试钩子（空 = 不提供）
	portInSvc bool   //: true = 端口在服务**自己的** `.env`（MuMu 的 APP_PORT）
	defPort   int    //: 端口默认值（与桥/脚本里的默认值一致）
	healthPath string //: 健康检查路径（PenShot 是 `/api/v1/health`，另两个是 `/health`）
}

// services：服务表。**顺序即 setup/uninstall 里的处理顺序**。
// [EN] services: the table. **The order is the processing order** in setup/uninstall.
var services = []extSvc{
	{
		id:         "mumu",
		zh:         "MuMuAINovel 写小说服务",
		dirRel:     "novelservices/MuMuAINovel/backend",
		dirHook:    envTestSvcDir, // NWS_TEST_SERVICE_DIR（既有的钩子，语义不变）
		script:     "novelservice.py",
		prepLabel:  bi("准备创作服务运行环境（MuMuAINovel）",
			"Preparing the writing-service runtime (MuMuAINovel)"),
		stopLabel:  bi("停止创作服务", "Stopping the writing service"),
		followKey:  "MUMU_FOLLOW_APP",
		followHook: "NWS_TEST_FOLLOW_MUMU",
		portKey:    "APP_PORT",
		portHook:   envTestSvcPort, // NWS_TEST_SERVICE_PORT（既有的钩子）
		portInSvc:  true,           // APP_PORT 在 backend 自己的 .env 里
		defPort:    8001,
		healthPath: "/health",
	},
	{
		id:      "penshot",
		zh:      "PenShot 分镜服务",
		dirRel:  "novelservices/PenShot",
		dirHook: "NWS_TEST_PENSHOT_DIR",
		ctl:     true,
		prepLabel: bi("准备分镜服务运行环境（PenShot）",
			"Preparing the storyboard-service runtime (PenShot)"),
		stopLabel: bi("停止分镜服务（PenShot）",
			"Stopping the storyboard service (PenShot)"),
		followKey:   "PENSHOT_FOLLOW_APP",
		followHook:  "NWS_TEST_FOLLOW_PENSHOT",
		portKey:     "PENSHOT_PORT",
		portInSvc:   false, // 端口在主程序 .env（桥的 _config() 也读那儿）
		defPort:     8000,
		healthPath:  "/api/v1/health", // 与 penshot_bridge.service_status 探的同一条
	},
	{
		id:      "plotpilot",
		zh:      "PlotPilot 编剧服务",
		dirRel:  "novelservices/PlotPilot",
		dirHook: "NWS_TEST_PLOTPILOT_DIR",
		ctl:     true,
		prepLabel: bi("准备编剧服务运行环境（PlotPilot）",
			"Preparing the screenwriting-service runtime (PlotPilot)"),
		stopLabel: bi("停止编剧服务（PlotPilot）",
			"Stopping the screenwriting service (PlotPilot)"),
		followKey:  "PLOTPILOT_FOLLOW_APP",
		followHook: "NWS_TEST_FOLLOW_PLOTPILOT",
		portKey:    "PLOTPILOT_PORT",
		portInSvc:  false,
		defPort:    8005,
		healthPath: "/health",
	},
}

//: 统一控制器的位置（相对程序根目录）。
// [EN] : Where the unified controller lives (relative to the app root).
const svcCtlRel = "novelservices/service_ctl.py"

// ctlPath：统一控制器脚本（`NWS_TEST_SERVICE_CTL` 可覆盖 —— 判据用它换成夹具，
// 否则每验一次"停了几个服务"都要真起真停一遍）。
// [EN] ctlPath: the unified controller script (`NWS_TEST_SERVICE_CTL` overrides
// [EN] it -- the assertions use this to swap in a fixture, otherwise verifying
// [EN] "which services got stopped" would really start and stop them each time).
func ctlPath(appDir string) string {
	return envOr(envTestCtl, filepath.Join(appDir, filepath.FromSlash(svcCtlRel)))
}

// svcDir：服务的目录（测试钩子可覆盖，语义与既有的 `NWS_TEST_SERVICE_DIR` 一致）。
// [EN] svcDir: the service's directory (the test hook overrides it, same
// [EN] semantics as the existing `NWS_TEST_SERVICE_DIR`).
func svcDir(appDir string, s extSvc) string {
	if s.dirHook != "" {
		if v := strings.TrimSpace(os.Getenv(s.dirHook)); v != "" {
			return v
		}
	}
	return filepath.Join(appDir, filepath.FromSlash(s.dirRel))
}

// svcPresent：这个服务在不在（= "要不要碰它"）。
//
// 发布包把整个 `novelservices/` 排掉了 ⇒ 用户机上三个都是 false，
// 于是 setup / uninstall / start 一条服务步骤都不会有 —— 服务是增强项，
// 不在是本该支持的常态，不是错误。
// [EN] svcPresent: is this service here (= "should we touch it"). The release
// [EN] bundle drops all of `novelservices/`, so on user machines all three are
// [EN] false and no service step appears anywhere -- services are enhancements;
// [EN] their absence is a supported normal state, not an error.
func svcPresent(appDir string, s extSvc) bool {
	dir := svcDir(appDir, s)
	if s.ctl {
		// 走控制器的服务：目录在**且**控制器在（缺一个都没法干活）。
		// [EN] Controller-routed services: the directory is there **and** so is
		// [EN] the controller (missing either means we can't do the job).
		return isDir(dir) && isFile(ctlPath(appDir))
	}
	return isFile(filepath.Join(dir, s.script))
}

// svcPort：服务的端口（默认值 → `.env`；测试钩子优先）。
// [EN] svcPort: the service's port (default → `.env`; the test hook wins).
func svcPort(appDir string, s extSvc) int {
	if s.portHook != "" {
		if v := strings.TrimSpace(os.Getenv(s.portHook)); v != "" {
			return atoiOr(v, s.defPort)
		}
	}
	envFile := filepath.Join(appDir, ".env")
	if s.portInSvc {
		// MuMu 的 APP_PORT 在它**自己**的 .env 里（`novelservice.py` 也读那儿）。
		// [EN] MuMu's APP_PORT lives in **its own** .env (`novelservice.py`
		// [EN] reads it there too).
		envFile = filepath.Join(svcDir(appDir, s), ".env")
	}
	return atoiOr(readEnvFile(envFile)[s.portKey], s.defPort)
}

// followFor：关主程序时要不要停这个服务。
//
// 决策顺序（从尖到宽）：逐服务测试钩子 → 全局测试钩子 → `.env` 里的
// `*_FOLLOW_APP`。默认 **true**（与 `config.py` 里那些 SPEC 的 default 一致）——
// 不然"程序里显示的"和"启动器实际做的"会不一样，那是最难查的一类不一致。
// [EN] followFor: should this service be stopped when the main program closes.
// [EN] Order (narrow to wide): per-service test hook → global test hook →
// [EN] `*_FOLLOW_APP` in `.env`. Default **true** (matching those SPEC defaults
// [EN] in `config.py`) -- otherwise "what the program shows" and "what the
// [EN] launcher does" diverge, the hardest kind of inconsistency to find.
func followFor(appDir string, s extSvc) bool {
	if s.followHook != "" {
		if v := strings.TrimSpace(os.Getenv(s.followHook)); v != "" {
			return truthy(v)
		}
	}
	if v := strings.TrimSpace(os.Getenv(envTestFollow)); v != "" {
		// 判据用它把"开/关"两条分支都走一遍（真实 `.env` 里那条不一定是哪个值，
		// 而这条决策必须有判据守；否则"关掉程序服务还在跑"只能靠用户报）。
		// [EN] The assertions use this to walk both branches (the real `.env`
		// [EN] value may be either, and this decision must be guarded;
		// [EN] otherwise "closed the program but the service kept running"
		// [EN] could only ever be reported by users).
		return truthy(v)
	}
	return truthy(readEnvFile(filepath.Join(appDir, ".env"))[s.followKey])
}

// servicePrepareSteps：setup 要为外部服务备的几步（**只算不做**）。
//
// `skip=true`（`--skip-service`）时一步都没有 —— 那个开关的语义就是
// "别碰外部服务"，对三个服务一视同仁。
// [EN] servicePrepareSteps: the steps setup needs for the external services
// [EN] (**plans only, does not run**). `skip=true` (`--skip-service`) yields
// [EN] nothing -- that switch means "don't touch the external services",
// [EN] equally for all three.
func servicePrepareSteps(appDir string, lg *logger, py pyInfo, skip bool) []jobStep {
	if skip {
		lg.printf("--skip-service：跳过外部服务环境准备")
		return nil
	}
	var steps []jobStep
	for _, s := range services {
		if !svcPresent(appDir, s) {
			lg.printf("没找到 %s（%s），跳过环境准备", s.zh, s.dirRel)
			continue
		}
		if s.ctl {
			steps = append(steps, jobStep{
				Label: s.prepLabel,
				Argv:  []string{pyW(py), ctlPath(appDir), "prepare", s.id},
				Cwd:   appDir,
			})
			continue
		}
		// MuMu：照旧直跑它自己的脚本。⚠ 这里**允许**用系统 Python：
		// 服务自己的 venv 常常还没建，而 `prepare` 的活正是去建它。
		// [EN] MuMu: runs its own script directly, as before. ⚠ Using the
		// [EN] system Python here is **allowed**: the service's venv often
		// [EN] doesn't exist yet, and `prepare` is precisely the job of
		// [EN] building it.
		dir := svcDir(appDir, s)
		pyForSvc := servicePy(dir, py.exe, false)
		steps = append(steps, jobStep{
			Label: s.prepLabel,
			Argv:  []string{pyForSvc, filepath.Join(dir, s.script), "prepare"},
			Cwd:   dir,
		})
	}
	return steps
}

// stopStep：停一个服务的那一步。服务不在 ⇒ ok=false（调用方跳过）。
// [EN] stopStep: the step that stops one service. Not present ⇒ ok=false
// [EN] (callers skip it).
func stopStep(appDir string, py pyInfo, s extSvc) (jobStep, bool) {
	if !svcPresent(appDir, s) {
		return jobStep{}, false
	}
	if s.ctl {
		return jobStep{
			Label: s.stopLabel,
			Argv:  []string{pyW(py), ctlPath(appDir), "stop", s.id},
			Cwd:   appDir,
		}, true
	}
	dir := svcDir(appDir, s)
	// 与旧脚本的 `if exist %SVC_PY%` 双重守卫等价：**运行环境没准备好就不碰它**。
	// （`setup` 那条路不一样 —— 它正是去建这个环境的。）
	// [EN] Equivalent to the old scripts' `if exist %SVC_PY%` double guard:
	// [EN] **don't touch it unless the runtime is ready**. (`setup` is the
	// [EN] exception -- building that runtime is its whole job.)
	win := servicePy(dir, "", true)
	if win == "" {
		return jobStep{}, false
	}
	return jobStep{
		Label: s.stopLabel,
		Argv:  []string{win, filepath.Join(dir, s.script), "stop"},
		Cwd:   dir,
	}, true
}

// runStepNow：把一步**现在**跑掉（主窗口退出后停服务走这儿；进度窗那条路
// 不经手）。输出进日志，退出码交给调用方。
// [EN] runStepNow: run one step **right now** (used to stop services after the
// [EN] main window exits; the progress-window path doesn't come through here).
// [EN] Output goes to the log; the exit code goes to the caller.
func runStepNow(lg *logger, step jobStep, timeoutMs int) int {
	if len(step.Argv) == 0 {
		return 0
	}
	dir := step.Cwd
	out, code := runCapture(step.Argv[0], step.Argv[1:], dir, timeoutMs)
	if strings.TrimSpace(out) != "" {
		for _, ln := range tailLines(out, 6) {
			lg.printf("    %s", ln)
		}
	}
	return code
}

// pyW：窗口版解释器（`pythonw.exe`），找不到就退回控制台版。
// Windows 上"起子进程不冒控制台"靠的就是它（见 `quietCommand` 的注释）。
// [EN] pyW: the windowed interpreter (`pythonw.exe`), falling back to the
// [EN] console one. On Windows this is what keeps child processes console-less
// [EN] (see the note on `quietCommand`).
func pyW(py pyInfo) string {
	if py.win != "" {
		return py.win
	}
	return py.exe
}

// ══════════════════════════════════════════════════════════════════
//  端口体检：setup 时把每个服务的端口落到一个**能用**的值
// [EN] Port check: settle each service's port to a **usable** value at setup time
// ══════════════════════════════════════════════════════════════════
//
// 2026-10-17 用户：「我在机器上有 Docker，3 个外部服务最后不要跟现有的在使用的
// 端口冲突。具体的端口，请在 setup 程序中初始化配置相关服务的时候检查本地端口
// 情况并配置好」。
//
// 要点（顺序不能反）：
//   · 端口**绑得上**才算可用 —— 用 Listen 而不是 Dial：Docker / Hyper-V 占着的
//     端口有时"连得上"、有时连不上，但**绑不上**是确定的；
//   · 绑不上时先问一句"占它的是不是**本服务自己**"（健康检查通 ⇒ 是）——
//     是就**不许改**（MuMu 正在 8001 上跑，改端口等于把它甩掉）；
//   · 要改就**从当前端口往上找**（+1 … +80），找到就**写回服务该读的那份 `.env`**
//     （MuMu 写它自己的 backend/.env；两个新服务写主程序根 .env —— 与
//     `envFileFor` / 桥的 `_config()` 同一个来源）；
//   · 写不进去就**保持原样并说清**，绝不"改了个数但没人读"。
//
// English:
// 2026-10-17 user: "I have Docker on this machine; the three external services must
// not collide with ports already in use. For the actual ports, check the local port
// situation in setup when initializing the related services and configure them."
//   · A port counts as usable only if we can **bind** it (Listen, not Dial: Docker /
//     Hyper-V ports may or may not accept a connection, but "cannot bind" is definite);
//   · When binding fails, first ask "is the occupant **this service itself**"
//     (health check passes ⇒ yes) -- if so, **never change it** (MuMu is running on
//     8001; changing the port would orphan it);
//   · To change, scan **upward** from the current port (+1 … +80), then write it back
//     into the `.env` **that this service reads** (MuMu: its own backend/.env; the two
//     new services: the app root .env -- same source as `envFileFor` / the bridge's
//     `_config()`);
//   · If the write fails, **keep the old value and say so** -- never "change a number
//     nobody reads".

//: 端口被占时最多往上找多少个（80 够绕过 Docker 常占的那一串默认端口）。
const portScanSpan = 80

// portUsable：这个端口**现在能不能由我们绑上**。
// [EN] portUsable: can **we bind** this port right now.
func portUsable(port int) bool {
	if port <= 0 || port > 65535 {
		return false
	}
	ln, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
	if err != nil {
		return false
	}
	_ = ln.Close()
	return true
}

// envFileFor：这个服务的端口写在哪一份 `.env`。
// [EN] envFileFor: which `.env` this service's port is written into.
func envFileFor(appDir string, s extSvc) string {
	if s.portInSvc {
		return filepath.Join(svcDir(appDir, s), ".env")
	}
	return filepath.Join(appDir, ".env")
}

// writeEnvKey：把 `KEY=val` 写进 `.env`（已有的行**就地替换**，没有就追加）。
//
// ⚠ 保留其它行与原有换行风格（CRLF 的文件仍写 CRLF）—— 直接整份重写会把
//   用户手写的注释/顺序冲掉，那是最招人烦的一种"帮忙"。
// [EN] writeEnvKey: write `KEY=val` into `.env` (**replace in place**, append if absent).
// [EN] ⚠ Keep the other lines and the original line-ending style (a CRLF file stays CRLF) --
// [EN] rewriting the whole file would wipe the user's comments/order, the most annoying
// [EN] kind of "help".
func writeEnvKey(path, key string, val int) error {
	raw, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	text := string(raw)
	crlf := strings.Contains(text, "\r\n")
	eol := ""
	if crlf {
		eol = "\r"
	}
	lines := strings.Split(text, "\n")
	done := false
	for i, ln := range lines {
		if strings.HasPrefix(strings.TrimSpace(strings.TrimRight(ln, "\r")), key+"=") {
			lines[i] = key + "=" + strconv.Itoa(val) + eol
			done = true
			break
		}
	}
	if !done {
		lines = append(lines, key+"="+strconv.Itoa(val))
	}
	out := strings.Join(lines, "\n")
	if !strings.HasSuffix(out, "\n") {
		out += "\n"
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(out), 0o644)
}

// ensureServicePort：setup 时为**一个**服务把端口定下来。
// 返回 (最终端口, 是不是改过)。
//
// `taken`：**其它**在场服务正在用的端口 —— 扫描时必须跳过。
// ★ 为什么必须有它（2026-10-17 实测想到的坑）：8000 被 Docker 占着时，
//   "往上找第一个能绑的"正好是 8001 —— 而 8001 是 MuMu 的端口。
//   两个服务抢同一个端口，表现是"后起的那个起不来"，日志里却全是"成功"。
// [EN] ensureServicePort: settle **one** service's port at setup time.
// [EN] Returns (final port, whether it was changed).
// [EN] `taken`: ports **other** present services are using -- must be skipped.
// [EN] ★ Why it's required (a pitfall spotted on 2026-10-17): with 8000 held by
// [EN] Docker, "scan up to the first bindable port" lands exactly on 8001 --
// [EN] MuMu's port. Two services fighting over one port shows up as "the second
// [EN] one won't start" while the log says everything succeeded.
func ensureServicePort(appDir string, lg *logger, s extSvc, taken map[int]bool) (int, bool) {
	cur := svcPort(appDir, s)
	if portUsable(cur) {
		return cur, false
	}
	// 绑不上：先看是不是**服务自己**正占着（MuMu 常驻 8001 就是这种情况）。
	// [EN] Cannot bind: first check whether **the service itself** holds it
	// [EN] (MuMu resident on 8001 is exactly this case).
	if healthOK(cur, s.healthPath) {
		lg.printf("%s 的端口 %d 被**它自己**占着（健康检查通）⇒ 保持不动", s.zh, cur)
		return cur, false
	}
	for p := cur + 1; p <= cur+portScanSpan && p <= 65535; p++ {
		if taken[p] || !portUsable(p) {
			continue
		}
		if err := writeEnvKey(envFileFor(appDir, s), s.portKey, p); err != nil {
			lg.printf("⚠ %s 的端口 %d 被别的程序占着，本想改用 %d，但写 %s 失败：%v ⇒ 保持原样",
				s.zh, cur, p, envFileFor(appDir, s), err)
			return cur, false
		}
		lg.printf("%s 的端口 %d 被别的程序占着 ⇒ 已改用 %d（写进 %s）",
			s.zh, cur, p, envFileFor(appDir, s))
		return p, true
	}
	lg.printf("⚠ %s 的端口 %d 被占，往上 %d 个端口也都不空闲 ⇒ 保持原样（服务可能起不来）",
		s.zh, cur, portScanSpan)
	return cur, false
}

// ensureAllServicePorts：setup 的入口 —— 把**在场**的服务逐个过一遍。
// 不在场的（发布包常态）自然跳过；`--skip-service` 时调用方根本不会进来。
//
// ★ 无论改没改，最后都打一行汇总 —— 否则"体检过了"在日志里看不出来，
//   用户（和排查的人）没法确认这一步到底跑没跑。
// [EN] ensureAllServicePorts: the setup entry -- walk every **present** service.
// [EN] Absent ones (normal in a release bundle) are skipped; with `--skip-service`
// [EN] the caller never gets here.
// [EN] ★ Whether or not anything changed, log one summary line at the end --
// [EN] otherwise "the check ran" is invisible in the log, and neither the user
// [EN] nor whoever debugs it can confirm this step happened at all.
func ensureAllServicePorts(appDir string, lg *logger) {
	// 先收"别的服务正在用的端口"，扫描时跳过（见 `ensureServicePort` 的 taken 说明）。
	// [EN] Collect "ports other services are using" first and skip them while
	// [EN] scanning (see the `taken` note on `ensureServicePort`).
	taken := map[int]bool{}
	for _, s := range services {
		if svcPresent(appDir, s) {
			taken[svcPort(appDir, s)] = true
		}
	}
	var parts []string
	for _, s := range services {
		if !svcPresent(appDir, s) {
			continue
		}
		cur := svcPort(appDir, s)
		delete(taken, cur)             // 本服务自己的端口不算"被别人占"
		p, changed := ensureServicePort(appDir, lg, s, taken)
		taken[p] = true
		mark := ""
		if changed {
			mark = "（已改）"
		}
		parts = append(parts, fmt.Sprintf("%s=%d%s", s.id, p, mark))
	}
	if len(parts) > 0 {
		lg.printf("端口体检：%s", strings.Join(parts, "，"))
	}
}

// ══════════════════════════════════════════════════════════════════
//  多实例：谁在用服务（与 Python 侧 `util/svc_users.py` **同一张表**）
// [EN] Multiple instances: who is using the services (**the same table** as the
// [EN] Python side `util/svc_users.py`)
// ══════════════════════════════════════════════════════════════════
//
// ★★★ 2026-10-28：三个服务都**绑固定端口**，端口写在同一份 `.env` 里 ⇒
//   第二个实例只会收到一句"已经在运行，不重复启动" ⇒ **全程只有一组服务**。
//   于是"主窗口退出 ⇒ 服务跟着退出"这条硬要求（用户 2026-10-10 的原话）
//   在多实例下的正确说法是：**最后一个关的人负责收尸**。
//
//   ⚠ 这里换掉的是 `logs/launcher.pid` 那套（原 `claimLock`）：它比的是
//     "文件里那个 pid 是不是我"，只防住了**先关的**那个，没防住**后关的**
//     那个 —— 而人总是先关掉刚开的那一个、回头继续用先前那个，
//     ⇒ 那一次正好把**正在用**的服务掐掉。
//   ⇒ 判据换成**引用计数**：表上每一项是一个**活着**的主程序实例；
//     "判空" = 一个活着的都没有 ⇒ 那时才真的停。
//   ★ 判空**不看文件删没删**，只看 pid 死活 ⇒ 实例被强杀留下的文件自动不算数。
//
// ⚠⚠ 目录 `logs/service_users` 是**两边各写死的一份**：
//    Python 在 `util/svc_users.py` 的 `DIR_REL`，Go 在下面 `svcUsersDir`。
//    改名必须两边一起改 —— `tools/verify_svc_users.py` 的 S 组钉着这一条。
//
// [EN] ★★★ 2026-10-28: all three services **bind a fixed port** written in one
// [EN] shared `.env` => a second instance only gets "already running, not starting
// [EN] again" => **only one set of services ever runs**. So the hard requirement
// [EN] "main window exits => services exit with it" (user's words, 2026-10-10)
// [EN] must read, for multiple instances: **whoever closes last does the reaping**.
// [EN] ⚠ What this replaces is the `logs/launcher.pid` mechanism (the old
// [EN] `claimLock`): it compared "is the pid in the file mine" and guarded **the
// [EN] one that closes first** but not **the one that closes last** -- and people
// [EN] close the window they just opened and go back to the earlier one, so that
// [EN] is exactly when the **in-use** service gets cut off.
// [EN] => The yardstick becomes **reference counting**: each entry is a **live**
// [EN] main program instance; "empty" = not one alive => only then really stop.
// [EN] ★ "Empty" **ignores whether the file was deleted**, it only looks at pid
// [EN] liveness => files left behind by a killed instance stop counting by themselves.
// [EN] ⚠⚠ The directory `logs/service_users` is **hard-coded on both sides**:
// [EN] Python in `DIR_REL` of `util/svc_users.py`, Go in `svcUsersDir` below.
// [EN] Renaming must happen on both -- group S of `tools/verify_svc_users.py`
// [EN] pins this.

// svcUsersDir：登记表目录。见上面那句"两边各写死的一份"。
// [EN] svcUsersDir: the registry directory. See "hard-coded on both sides" above.
func svcUsersDir(appDir string) string {
	return filepath.Join(appDir, "logs", "service_users")
}

// anyUserAlive：还有**活着**的主程序实例在用服务吗？
//
// 目录读不出来（没建过 / 权限）⇒ 返回 false：那是"没人登记过"，
// 与 `util/svc_users.py` 的 `registered_pids()` 同口径。
//
// [EN] anyUserAlive: is there a **live** main program instance still using the
// services?
// [EN] If the directory can't be read (never created / permissions) => false:
// that means "nobody ever registered", same as `registered_pids()` in
// `util/svc_users.py`.
func anyUserAlive(appDir string) bool {
	entries, err := os.ReadDir(svcUsersDir(appDir))
	if err != nil {
		return false
	}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(strings.TrimSuffix(e.Name(), ".use"))
		if err != nil {
			continue
		}
		if pidAlive(pid) {
			return true
		}
	}
	return false
}
