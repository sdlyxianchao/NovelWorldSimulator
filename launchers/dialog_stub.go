package main

// 判据用的**对话框替身**（三平台共用；没有 build tag，四个目标都会编进去）。
//
// ★★ 为什么必须有它（这不是"为了方便测试"）
// ------------------------------------------
// `notify` / `confirm` 是**阻塞**的 —— `MessageBoxW` / `osascript` / `zenity`
// 都会把人顶在那儿等点击。于是"从启动器双击一次卸载，到底会不会成功"这件事
// 在自动化判据里**根本跑不起来**，只能靠人肉点一遍。
//
// 而 2026-10-10 用户报的那个 bug（截图：`The step "Removing desktop icon /
// Start Menu entry" did not succeed.`）恰恰就长在这条路上 —— 恰恰是
// **没有判据守着**的那一段代码。这不是巧合：一段"只能人肉验"的代码，
// 出问题只是时间问题。
//
// 有了替身，"弹的是什么框、用户点了哪个键"就变成了可断言的事实；
// 于是"卸载必须先问、问完能真卸掉"这条链才第一次有了自动化的守卫。
// 见 `tools/verify_launchers.py` 的 F 组。

import (
	"encoding/json"
	"os"
	"strings"
)

// 测试钩子：与 `main.go` 里那几个同一个约定 —— **只在环境变量里生效**，
// 正常运行路径不可能被误触发。
const (
	//: 指向一个 JSONL 文件。设了它，`notify` / `confirm` 就不弹真框，改往这里追加一行。
	envTestDialogLog = "NWS_TEST_DIALOG_LOG"
	//: 替身里"用户点了哪个键"。不设 = 「确定」（这样没关心这条的判据不会被卡住）。
	envTestConfirmAnswer = "NWS_TEST_CONFIRM_ANSWER"
)

// dialogStub：把"弹框"换成"往 `NWS_TEST_DIALOG_LOG` 追加一行 JSON"。
//
// 返回 `(handled, answer)`：
//   - `handled == false` ⇒ 调用方走**真实**的弹框实现（正常路径）；
//   - `handled == true`  ⇒ 已经"弹"过了（记进了日志），`answer` 给 `confirm` 用。
//
// 记进日志的是 `{kind, title, body, answer}`。判据据此断言"卸载前确实问过"
// 以及"失败时到底补没补那个原生框"。
func dialogStub(kind, zhTitle, zhBody string) (bool, bool) {
	p := strings.TrimSpace(os.Getenv(envTestDialogLog))
	if p == "" {
		return false, false
	}
	yes := true
	if v := strings.TrimSpace(os.Getenv(envTestConfirmAnswer)); v != "" {
		yes = truthy(v)
	}
	line, _ := json.Marshal(map[string]any{
		"kind": kind, "title": zhTitle, "body": zhBody, "answer": yes,
	})
	if f, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644); err == nil {
		_, _ = f.WriteString(string(line) + "\n")
		_ = f.Close()
	}
	return true, yes
}
