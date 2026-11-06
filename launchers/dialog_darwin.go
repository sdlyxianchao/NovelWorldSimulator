//go:build darwin

package main

import (
	"fmt"
	"os/exec"
	"strings"
)

// notify：macOS 上用 `osascript` 弹原生对话框。中英各给一份。
//
// 为什么不用别的：macOS 上没有"随便就能调"的跨进程消息框 API，
// 而 `osascript -e 'display dialog …'` 是系统自带、无需任何依赖的正规做法。
// 只在**致命错误**时才调用，所以这点开销无所谓。
func notify(zhTitle, enTitle, zhBody, enBody string, isErr bool) {
	if handled, _ := dialogStub("notify", zhTitle, zhBody); handled {
		return
	}
	icon := "note"
	if isErr {
		icon = "caution"
	}
	title := zhTitle + " / " + enTitle
	text := zhBody + "\n\n" + enBody
	script := fmt.Sprintf(
		"display dialog %s with title %s buttons {\"好 / OK\"} default button 1 with icon %s",
		asQuote(text), asQuote(title), icon)
	// ⚠ AppleScript 里 `"` 和 `\` 都要转义，否则一句带引号的报错就能让脚本语法出错、
	//   于是**该弹的框弹不出来**（而那正是最需要看到框的时候）。
	_ = exec.Command("osascript", "-e", script).Run()
}

// confirm：**原生二选一框**，返回 true = 用户点了「确定」。
//
// ★ 为什么卸载的"确认"必须由启动器问，而不是交给 `platform_install.py`
//   自己的 `input()`：那个子进程**没有终端**，`input()` 立刻 EOF ⇒ 当成"取消"
//   ⇒ 卸载永远失败。详见 `dialog_windows.go` 里同一段说明。
//
// ★ 默认按钮是「取消」：卸载是破坏性的，敲一下回车不该把它确认掉。
func confirm(zhTitle, enTitle, zhBody, enBody string) bool {
	if handled, ans := dialogStub("confirm", zhTitle, zhBody); handled {
		return ans
	}
	yes := "确定 / OK"
	no := "取消 / Cancel"
	script := fmt.Sprintf(
		"display dialog %s with title %s buttons {%s, %s} default button %s with icon caution",
		asQuote(zhBody+"\n\n"+enBody), asQuote(zhTitle+" / "+enTitle),
		asQuote(no), asQuote(yes), asQuote(no))
	// 点「取消」时 osascript 以非 0 退出；点「确定」才把 `button returned:…`
	// 打到 stdout。两个条件都认一下 —— 万一以后有人把按钮文字改了，
	// 这里也不会变成"点了确定却什么都不做"。
	out, err := exec.Command("osascript", "-e", script).Output()
	return err == nil && strings.Contains(string(out), yes)
}

// asQuote：把一个 Go 字符串变成 AppleScript 里的带引号字符串字面量。
func asQuote(s string) string {
	s = strings.ReplaceAll(s, `\`, `\\`)
	s = strings.ReplaceAll(s, `"`, `\"`)
	s = strings.ReplaceAll(s, "\n", `\n`)
	return `"` + s + `"`
}
