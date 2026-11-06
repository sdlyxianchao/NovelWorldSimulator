//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
)

// notify：Linux 上按顺序试常见的图形对话框程序，全都装不了才退回 stderr。
//
// ★ 为什么要有降级链而不是挑一个：Linux 上**没有**一个"到处都有"的对话框程序 ——
//   `zenity` 要看 GNOME 系、`kdialog` 是 KDE 系、`xmessage` 属 X11 老工具，
//   最小的容器/服务器发行版可能三个都没有。挑一个当硬依赖，等于在那些机器上
//   "报错弹不出来"；而弹不出来恰恰是用户最难自己查的一类故障。
//   最后退回 stderr：从终端启动时至少还看得见（从文件管理器双击时看不见，
//   但那种情况下用户本来也不该看到报错 —— 正常路径不会走到这里）。
func notify(zhTitle, enTitle, zhBody, enBody string, isErr bool) {
	if handled, _ := dialogStub("notify", zhTitle, zhBody); handled {
		return
	}
	title := zhTitle + " / " + enTitle
	text := zhBody + "\n\n" + enBody
	kind := "--info"
	if isErr {
		kind = "--error"
	}
	cands := [][]string{
		{"zenity", kind, "--title", title, "--text", text, "--width", "440"},
		{"kdialog", "--title", title, "--msgbox", text},
		{"xmessage", "-center", title + "\n\n" + text},
	}
	for _, c := range cands {
		if _, err := exec.LookPath(c[0]); err != nil {
			continue
		}
		if err := exec.Command(c[0], c[1:]...).Run(); err == nil {
			return
		}
	}
	fmt.Fprintf(os.Stderr, "\n%s\n%s\n", title, text)
}

// confirm：**原生二选一框**，返回 true = 用户点了「确定」。
//
// ★ 为什么卸载的"确认"必须由启动器问，而不是交给 `platform_install.py`
//   自己的 `input()`：那个子进程**没有终端**，`input()` 立刻 EOF ⇒ 当成"取消"
//   ⇒ 卸载永远失败。详见 `dialog_windows.go` 里同一段说明。
//
// ★ 默认按钮是「取消」（zenity `--default-cancel` / kdialog `--default no`）：
//   卸载是破坏性的，敲一下回车不该把它确认掉。
//
// ★ 三个对话框程序都没有时**返回 true**（= 继续卸载），并在 stderr 留一句。
//   取舍是这样的：卸载**只删快捷方式**，永远不碰用户的小说项目数据
//   （`platform_install.py` 里那句"小说项目数据始终保留"是硬约定）；
//   而被一个"问不出来的框"卡死，用户是**卸载不掉**的 —— 那比多删几个快捷方式糟。
//   注意这与 `notify` 的降级方向不同：那里是"弹不出来就算了"，这里是"问不了就放行"，
//   两边都不装作问过了。
func confirm(zhTitle, enTitle, zhBody, enBody string) bool {
	if handled, ans := dialogStub("confirm", zhTitle, zhBody); handled {
		return ans
	}
	title := zhTitle + " / " + enTitle
	text := zhBody + "\n\n" + enBody
	if _, err := exec.LookPath("zenity"); err == nil {
		return exec.Command("zenity", "--question", "--title", title,
			"--text", text, "--width", "440", "--default-cancel").Run() == nil
	}
	if _, err := exec.LookPath("kdialog"); err == nil {
		return exec.Command("kdialog", "--title", title, "--yesno", text,
			"--default", "no").Run() == nil
	}
	if _, err := exec.LookPath("xmessage"); err == nil {
		// xmessage 的退出码 = 被按下那个按钮的编号，所以把「确定」编成 0。
		return exec.Command("xmessage", "-center", "-buttons", "取消:1,确定:0",
			title+"\n\n"+text).Run() == nil
	}
	fmt.Fprintf(os.Stderr, "confirm: 没有可用的对话框程序"+
		"（zenity/kdialog/xmessage 都没有）⇒ 按「确定」继续\n")
	return true
}
