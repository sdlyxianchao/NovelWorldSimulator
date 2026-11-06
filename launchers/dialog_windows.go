//go:build windows

package main

import (
	"syscall"
	"unsafe"
)

// MessageBoxW 的按钮/图标常量。
const (
	mbOK            = 0x00000000
	mbYesNo         = 0x00000004
	mbIconError     = 0x00000010
	mbIconQuestion  = 0x00000020
	mbDefButton2    = 0x00000100
	mbIconInfo      = 0x00000040
	mbSetForeground = 0x00010000
	mbTopMost       = 0x00040000
	//: `MessageBoxW` 点了「是」的返回值（IDYES）。
	idYes = 6
)

var (
	_user32     = syscall.NewLazyDLL("user32.dll")
	_messageBox = _user32.NewProc("MessageBoxW")
)

// notify：**原生消息框**。中英各给一份。
//
// ★ 为什么非得走原生 API：本程序用 `-H windowsgui` 编译（子系统=GUI），
//   也就是说它**没有控制台**，`fmt.Println` 打给谁看都不知道（stdout 句柄是无效的）。
//   而"没找到 Python"这种致命错误必须让人看见 —— 否则双击之后就是"什么也没发生"，
//   那是用户最没法自己诊断的一类故障。
//   `hwnd=0` + `MB_TOPMOST`：即使主窗口已经关掉，框也会浮在最前面。
//
// ⚠ 开头那三行是**判据的替身**（`dialog_test.go`）：设了 `NWS_TEST_DIALOG_LOG`
//   就把"弹框"换成"记一行日志"。没有它，"卸载前问没问、失败时补没补框"
//   这两件事只能靠人肉点一遍 —— 而用户报的那个 bug 正好就长在这条路上。
func notify(zhTitle, enTitle, zhBody, enBody string, isErr bool) {
	if handled, _ := dialogStub("notify", zhTitle, zhBody); handled {
		return
	}
	title := zhTitle + " / " + enTitle
	text := zhBody + "\n\n" + enBody
	t, err1 := syscall.UTF16PtrFromString(text)
	c, err2 := syscall.UTF16PtrFromString(title)
	if err1 != nil || err2 != nil {
		return
	}
	flags := uintptr(mbOK | mbSetForeground | mbTopMost)
	if isErr {
		flags |= mbIconError
	} else {
		flags |= mbIconInfo
	}
	// 返回值忽略：用户点了"确定"就继续；点不到也不该把启动器卡死。
	_, _, _ = _messageBox.Call(0,
		uintptr(unsafe.Pointer(t)),
		uintptr(unsafe.Pointer(c)),
		flags)
}

// confirm：**原生二选一框**，返回 true = 用户点了「是」。
//
// ★ 这个框在第一版里根本不存在，而它就是 2026-10-10 用户报的那个 bug 的正解。
//
//	卸载原来是"启动器直接把 `platform_install.py uninstall` 跑起来"，而那个脚本
//	自己会问 `确认卸载？[y/N]`。可启动器起的子进程**没有终端**
//	（启动器是 GUI 子系统的，进度窗又用 `stdin=DEVNULL`）⇒ `input()` 立刻 EOF
//	⇒ 当成 "N" ⇒ 每次都"已取消"、退出码 1
//	⇒ 用户看到的就是「删除桌面图标 / 开始菜单 这一步没成功」。
//	实测（`platform_install.py uninstall < /dev/null`）：稳定 `EXIT=1`。
//
//	⇒ 谁有窗口谁负责问：**启动器问**（这个框），问完把 `--yes` 传给子进程。
//
// ★ 默认按钮是「否」（`MB_DEFBUTTON2`）：卸载是破坏性的，敲一下回车不该把它确认掉。
func confirm(zhTitle, enTitle, zhBody, enBody string) bool {
	if handled, ans := dialogStub("confirm", zhTitle, zhBody); handled {
		return ans
	}
	title := zhTitle + " / " + enTitle
	text := zhBody + "\n\n" + enBody
	t, err1 := syscall.UTF16PtrFromString(text)
	c, err2 := syscall.UTF16PtrFromString(title)
	if err1 != nil || err2 != nil {
		// 连字符串都构造不出来 ⇒ 问不出来 ⇒ 按"不干"处理（卸载宁可不动）。
		return false
	}
	flags := uintptr(mbYesNo | mbDefButton2 | mbIconQuestion |
		mbSetForeground | mbTopMost)
	r, _, _ := _messageBox.Call(0,
		uintptr(unsafe.Pointer(t)),
		uintptr(unsafe.Pointer(c)),
		flags)
	return int(r) == idYes
}
