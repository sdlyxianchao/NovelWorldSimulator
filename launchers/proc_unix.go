//go:build !windows

package main

import "syscall"

// quietSysProcAttr：Unix 上没有"控制台窗口"这个概念 —— 从文件管理器双击
// 启动一个可执行文件不会弹出终端（Linux 桌面项要显式写 `Terminal=true` 才会）。
// 所以这里**故意什么都不设**：设了反而会把子进程从终端会话里摘出去，
// 让用户在终端里跑的时候看不到输出。
func quietSysProcAttr() *syscall.SysProcAttr {
	return &syscall.SysProcAttr{}
}

// hasConsole：Unix 上恒为 false（没有"控制台窗口"这件事）。
// 见 `proc_windows.go` 的说明 —— 这个字段只在 Windows 上有意义。
func hasConsole() bool { return false }

// pidAlive：这个 pid 现在还活着吗（**信号 0 = 探活不送信**）。
//
// 与 `proc_windows.go` 那个版本**同一个语义、两条实现**（build tag 分开）——
// 判据 `tools/verify_launchers.py` 的 C 组与 `tools/verify_svc_users.py` 的
// S 组分别钉着两边，别让它们各说各话。
//
// ⚠ `EPERM`（存在但不归我管）算**活着**：判成"死了"就会误停服务。
//
// [EN] pidAlive: is this pid alive right now (**signal 0 = probe, send nothing**).
// [EN] Same semantics as the `proc_windows.go` version, two implementations
// [EN] (split by build tag) -- group C of `tools/verify_launchers.py` and group S
// [EN] of `tools/verify_svc_users.py` pin the two sides respectively; don't let
// [EN] them disagree.
// [EN] ⚠ `EPERM` (exists but not mine) counts as **alive**: calling it dead would
// [EN] stop the service by mistake.
func pidAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	err := syscall.Kill(pid, syscall.Signal(0))
	return err == nil || err == syscall.EPERM
}
