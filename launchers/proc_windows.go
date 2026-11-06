//go:build windows

package main

import "syscall"

// Windows 进程创建标志（不引 `golang.org/x/sys/windows`，保持零依赖）。
const (
	// createNoWindow：**不为子进程分配控制台**。
	//   ★ 这一条是本项目 2026-10-10 查了一整轮的结论：venv 里的
	//     `Scripts/python.exe` 不是解释器本体，而是 `venvlauncher.exe` ——
	//     它启动时会**再 exec 一次真解释器**，而且**不把 CREATE_NO_WINDOW
	//     传下去**。父进程若没有控制台（比如被 pythonw / 快捷方式拉起），
	//     子进程是 console 子系统又没得继承 ⇒ Windows 给它**新分配一个控制台**，
	//     那个黑窗就一直挂着。
	//   ⇒ 两条一起才叫"结构上不可能弹窗"：① 子进程显式给 CREATE_NO_WINDOW；
	//     ② 能用 `pythonw.exe` 就用 `pythonw.exe`。
	createNoWindow = 0x08000000
)

// quietSysProcAttr：**静默**起子进程（无控制台、不显示窗口）。
//
// ★★ 两个字段各管一件事，**实测过它们不是冗余的**（2026-10-10，反例法逼出来的）：
//   · `CreationFlags = CREATE_NO_WINDOW` 管"**不给子进程分配控制台**"；
//   · `HideWindow = true`（`STARTF_USESHOWWINDOW` + `SW_HIDE`）管"**分配了也不显示**"。
//   实测：只去掉 `CREATE_NO_WINDOW`、留着 `HideWindow`，子进程仍然拿得到控制台
//   （有 conhost），但**屏幕上不出现窗口**；两个都去掉才会真的冒出黑窗。
//   ⇒ 所以两个都要在。哪天有人觉得"留一个就够"，先看这条实测再动手。
func quietSysProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{
		CreationFlags: createNoWindow,
		HideWindow:    true,
	}
}

// hasConsole：本进程**现在有没有**一个控制台窗口。
//
// 这是"编译出来的到底是 GUI 还是控制台程序"的**运行时**判据：
// 用 `-H windowsgui` 编出来的程序，双击 / 从 cmd 里跑，`GetConsoleWindow()`
// 都返回 0；而控制台子系统程序从 cmd 里跑必然返回非 0。
// （静态那边由 `tools/verify_launchers.py` 直接读 PE 头里的 Subsystem 字段，
//  =2 才是 GUI。两条一起看，静态一条防"编错了"，运行时一条防"编对了但被改回去"。）
func hasConsole() bool {
	k32 := syscall.NewLazyDLL("kernel32.dll")
	proc := k32.NewProc("GetConsoleWindow")
	h, _, _ := proc.Call()
	return h != 0
}

// stillActive 是 `STILL_ACTIVE`：`GetExitCodeProcess` 给回这个数 = 进程还在跑。
// 拿到任何别的数都表示"它已经退出了"（那个数就是它的退出码）。
//
// [EN] `stillActive` is `STILL_ACTIVE`: `GetExitCodeProcess` returning this means
// [EN] the process is still running. Any other value means "it already exited"
// [EN] (that value is its exit code).
const stillActive = 259

// pidAlive：这个 pid 现在还活着吗？
//
// ★★★ **光能把进程打开不算活着** —— 这条是 Python 侧实测踩出来的
//   （`util/svc_users.py:_win_alive` 有完整注释，两边必须同口径）：
//   把子进程杀掉之后，只要**还有人攥着它的句柄**，`OpenProcess` 照样成功
//   （Windows 要等最后一个句柄关掉才销毁进程对象）。
//   ⇒ "能打开 ⇒ 活着"会把**已经死了的**判成活的 ⇒ 僵尸登记永远自愈不了
//   ⇒ 服务再也不停（症状长得像"跟随退出失效"）。
//   ⇒ 必须再问一句 `GetExitCodeProcess`。
//
// 为什么不用 `os.FindProcess`：它在 Windows 上**从不报错**（只是造一个句柄
// 包装），判不出死活。
//
// [EN] pidAlive: is this pid alive right now?
// [EN] ★★★ **Being able to open the process does not mean it is alive** -- the
// [EN] Python side measured this the hard way (`util/svc_users.py:_win_alive` has
// [EN] the full note; both sides must agree): after killing a child, `OpenProcess`
// [EN] still succeeds **as long as someone holds a handle to it** (Windows
// [EN] destroys the process object only when the last handle closes).
// [EN] => "can open => alive" calls a **dead** process alive => zombie entries
// [EN] never heal => the service never stops (reads like "follow-exit broke").
// [EN] => We must also ask `GetExitCodeProcess`.
// [EN] Why not `os.FindProcess`: on Windows it **never errors** (it just wraps a
// [EN] handle), so it cannot tell alive from dead.
func pidAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	const queryLimitedInformation = 0x1000
	h, err := syscall.OpenProcess(queryLimitedInformation, false, uint32(pid))
	if err != nil {
		// ERROR_ACCESS_DENIED(5)：**打不开，但它存在**（别人的进程）。
		// 判成"死了"就会误停服务 —— 那才是要防的事。
		// [EN] ERROR_ACCESS_DENIED(5): **cannot open it, but it exists** (someone
		// [EN] else's process). Calling it dead would stop the service by mistake
		// [EN] -- exactly what we are guarding against.
		return err == syscall.Errno(5)
	}
	defer syscall.CloseHandle(h)
	var code uint32
	if err := syscall.GetExitCodeProcess(h, &code); err != nil {
		return true // 取不到退出码 ⇒ 保守当活着（宁可留着，不可掐掉）
	}
	return code == stillActive
}
