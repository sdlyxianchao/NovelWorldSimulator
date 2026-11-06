package main

import (
	"bytes"
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"
)

// ══════════════════════════════════════════════════════════════════
//  起进程：**一律静默**
// ══════════════════════════════════════════════════════════════════

// ★★★ 2026-10-25（用户报"启动界面出现乱码"）：**所有子进程一律 UTF-8 输出**。
//
// 现象：启动窗口里出现 `PenShot �־����� �� ֹͣ` / `[ok] ��ֹ��pid=10184��`。
// 根因：本启动器把子进程 stdout **字节直通**写进 `logs/launcher.log`（`runWait` 里
//   `cmd.Stdout = f`），而它自己 `lg.printf` 写的是 UTF-8。子进程是 Python，
//   stdout 被重定向成管道时 Python 会退回**系统 locale 编码**，中文 Windows 上是
//   cp936(GBK) ⇒ **同一个日志文件里两种编码**，启动窗口按 UTF-8 读，GBK 那几行全乱。
//   实测：`'停止'.encode('gbk')` = `cd a3 d6 b9`，按 UTF-8 解码正是 `ֹͣ`，
//   与用户看到的完全一致。
// 为什么在这里治（而不是只在每个 Python 脚本里加 `reconfigure`）：
//   Python 侧的修法是"每个被调起的脚本都得记得加"，漏一个就复发；而这里是**唯一的**
//   起子进程的入口，一处设上，以后新加脚本自动继承。Python 侧的 `reconfigure`
//   仍然保留 —— 那是给"不经启动器、直接跑脚本"和"用户手上还是旧启动器"兜的。
// ⚠ **不是"用户设过就不管"，而是"永远按 UTF-8 给"**。
//   第一版写的是"环境里已有 `PYTHONIOENCODING`/`PYTHONUTF8` 就 `return nil` 不插手"，
//   那是错的：值可能是 `PYTHONIOENCODING=gbk`（或 `PYTHONUTF8=0`），此时"尊重用户"等于
//   **把乱码原样放过**。而这两个变量只作用于**我们自己起的子进程**，不是全局偏好 ——
//   日志编码是我们自己的契约，不该被外部环境改掉。
// ⚠ 其余变量必须**原样继承**（`PATH` 丢了连 Python 都找不到）。
// [EN] ⚠ **Not "if the user set it, leave it alone" but "always hand it UTF-8"**. The first version
// [EN] returned nil when either variable already existed -- wrong, because the value could be
// [EN] `PYTHONIOENCODING=gbk` (or `PYTHONUTF8=0`), and "respecting the user" then means **letting the
// [EN] mojibake through**. These variables only affect **the children we spawn**, not a global
// [EN] preference -- the log encoding is our own contract.
// [EN] ⚠ Every other variable must be **inherited as-is** (drop `PATH` and Python cannot be found).
func childEnv() []string {
	want := map[string]string{"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
	old := os.Environ()
	env := make([]string, 0, len(old)+len(want))
	for _, kv := range old {
		name := kv
		if i := strings.IndexByte(kv, '='); i >= 0 {
			name = kv[:i]
		}
		if _, dup := want[strings.ToUpper(name)]; dup {
			continue // 丢掉旧的（可能值是 gbk），下面按我们的值补回来
		}
		env = append(env, kv)
	}
	for k, v := range want {
		env = append(env, k+"="+v)
	}
	return env
}

// quietCommand：构造一个**不会冒出控制台窗口**的命令。
//
// ★ 这是全项目的"无控制台"落点。上一轮查用户报的"关不掉的黑色控制台"，
//   最后查实的根因是：venv 的 `Scripts/python.exe` 是 **launcher**，
//   它会再 exec 一次真解释器，而 **CREATE_NO_WINDOW 不会传下去** ——
//   父进程没有控制台、子进程是 console 子系统又没得继承，
//   Windows 就**给它新分配一个控制台**。
//   ⇒ 两条一起：① 显式 `CREATE_NO_WINDOW`（见 `quietSysProcAttr`）；
//     ② 能用 `pythonw.exe` 就用它（`windowedPython` / `venvPython` 负责挑）。
func quietCommand(exe string, args []string, dir string) *exec.Cmd {
	cmd := exec.Command(exe, args...)
	if dir != "" {
		cmd.Dir = dir
	}
	cmd.SysProcAttr = quietSysProcAttr()
	// 输出编码：见 `childEnv` 的说明（2026-10-25 启动界面乱码）。
	// [EN] Output encoding: see `childEnv` (2026-10-25 splash mojibake).
	if env := childEnv(); env != nil {
		cmd.Env = env
	}
	return cmd
}

// runCapture：跑完并收集**合并的** stdout+stderr，返回 (输出, 退出码)。
//
// 合并而不是分开：这里只用来问"Python 在哪儿""依赖装齐了没"，
// 出错时 stderr 的那句话比 stdout 有用得多，分开还得调用方自己拼。
func runCapture(exe string, args []string, dir string, timeoutMs int) (string, int) {
	ctx, cancel := context.WithTimeout(context.Background(),
		time.Duration(timeoutMs)*time.Millisecond)
	defer cancel()
	// 直接建带 context 的命令（超时真的会杀掉子进程），再套上"静默"那一套属性。
	cmd := exec.CommandContext(ctx, exe, args...)
	if dir != "" {
		cmd.Dir = dir
	}
	cmd.SysProcAttr = quietSysProcAttr()
	// ★ 这里也要设：`runCapture` 会把输出**当字符串读回来**（`firstLine` / `pyVersion`），
	//   若子进程按 GBK 吐中文，Go 侧拿到的就是坏字节。见 `childEnv`。
	// [EN] Set it here too: `runCapture` reads the output back **as a string** (`firstLine` /
	// [EN] `pyVersion`), so GBK output from the child arrives as broken bytes. See `childEnv`.
	if env := childEnv(); env != nil {
		cmd.Env = env
	}
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	err := cmd.Run()
	if err == nil {
		return buf.String(), 0
	}
	if ee, ok := err.(*exec.ExitError); ok {
		return buf.String(), ee.ExitCode()
	}
	return buf.String(), -1
}

// runWait：起一个进程并**等它结束**，输出追加到 `logPath`。
func runWait(exe string, args []string, dir, logPath string) int {
	cmd := quietCommand(exe, args, dir)
	if logPath != "" {
		_ = os.MkdirAll(filepath.Dir(logPath), 0o755)
		if f, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644); err == nil {
			defer func() { _ = f.Close() }()
			cmd.Stdout = f
			cmd.Stderr = f
		}
	}
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			return ee.ExitCode()
		}
		return 1
	}
	return 0
}

// ══════════════════════════════════════════════════════════════════
//  Python
// ══════════════════════════════════════════════════════════════════

type pyInfo struct {
	//: 控制台版解释器（跑 pip / venv / 装机脚本）。永远是**解析出来的绝对路径**。
	exe string
	//: 窗口版（Windows 的 `pythonw.exe`）；Unix 上就是 `exe` 本身。
	win string
}

// findPython：按与旧脚本相同的顺序找 Python，并且**解析成绝对路径**。
//
// ★ 为什么要多跑一次 `-c "print(sys.executable)"` 而不是直接用 `python`：
//   ① `py -3` 这种是启动器，直接拿它当 argv[0] 的话每个调用点都要记得带上 `-3`，
//      迟早漏一个；
//   ② 我们要从"找到了哪个 python"**推出** `pythonw.exe` 在哪儿（同一目录），
//      没有绝对路径推不出来。
//   代价是一次 ~200ms 的子进程，只在启动时一次。
func findPython(lg *logger) (pyInfo, bool) {
	type cand struct {
		prog  string
		extra []string
	}
	var cands []cand
	if runtime.GOOS == "windows" {
		// `py -3` 优先：Windows 官方安装器的 launcher，能绕开 PATH 里
		// Microsoft Store 那个 python.exe 替身（它会弹商店页面）。
		cands = []cand{{"py", []string{"-3"}}, {"python", nil}, {"python3", nil}}
	} else {
		cands = []cand{{"python3", nil}, {"python", nil}}
	}
	for _, c := range cands {
		if _, err := exec.LookPath(c.prog); err != nil {
			continue
		}
		args := append(append([]string{}, c.extra...), "-c", "import sys;print(sys.executable)")
		out, code := runCapture(c.prog, args, "", 30000)
		if code != 0 {
			lg.printf("找 Python：`%s` 退出码 %d", c.prog, code)
			continue
		}
		p := firstLine(out)
		if p == "" || !isFile(p) {
			continue
		}
		return pyInfo{exe: p, win: windowedPython(p)}, true
	}
	return pyInfo{}, false
}

func firstLine(s string) string {
	s = strings.TrimSpace(strings.ReplaceAll(s, "\r\n", "\n"))
	if i := strings.Index(s, "\n"); i >= 0 {
		s = s[:i]
	}
	return strings.TrimSpace(s)
}

// windowedPython：同一个 Python 的"无控制台版本"。
//
// Windows 上就是同目录的 `pythonw.exe`（官方安装器和 venv 都会同时装两个）。
//
// ⚠ 找不到时退回原解释器 —— 但要说清楚：**那条路并不保证没有控制台**。
//   实测过的机制是：venv 里的 `python.exe` 不是解释器本体，而是 `venvlauncher.exe`，
//   它启动时会**再 exec 一次真解释器**，而 `CREATE_NO_WINDOW` **不会传下去**；
//   子进程是 console 子系统又没得继承 ⇒ Windows 给它**新分配一个控制台**。
//   也就是说那一路上的 `CREATE_NO_WINDOW` 只是**减弱**、不是消除。
//   ⇒ 真正的保证是"用 pythonw.exe"。这里退回只是"总比起不来强"。
func windowedPython(exe string) string {
	if runtime.GOOS != "windows" {
		return exe
	}
	w := filepath.Join(filepath.Dir(exe), "pythonw.exe")
	if isFile(w) {
		return w
	}
	return exe
}

// venvPython：工程自带运行环境 `.venv` 里的解释器（控制台版 + 窗口版）。
func venvPython(appDir string) (string, string, bool) {
	if runtime.GOOS == "windows" {
		e := filepath.Join(appDir, venvRel, "Scripts", "python.exe")
		if !isFile(e) {
			return "", "", false
		}
		w := filepath.Join(appDir, venvRel, "Scripts", "pythonw.exe")
		if !isFile(w) {
			w = e
		}
		return e, w, true
	}
	e := filepath.Join(appDir, venvRel, "bin", "python")
	if !isFile(e) {
		return "", "", false
	}
	return e, e, true
}

// ══════════════════════════════════════════════════════════════════
//  服务的端口与健康检查（逐服务的"在不在、端口多少"在 `services.go` 的表里）
// [EN] Service ports and health checks (the per-service "is it here, what
// [EN] port" lives in the table in `services.go`)
// ══════════════════════════════════════════════════════════════════

func atoiOr(s string, def int) int {
	if n, err := strconv.Atoi(strings.TrimSpace(s)); err == nil && n > 0 {
		return n
	}
	return def
}

// healthOK：服务在跑吗（`path` 是各服务的健康检查路径，见 `services.go` 的表 ——
// PenShot 是 `/api/v1/health`，另两个是 `/health`，与各自桥探的同一条）。
//
// ★ 用**裸 TCP + 手写一行 HTTP/1.0 请求**，不引 `net/http`。
//   实测（2026-10-10，windows/amd64）：用 `net/http` 时每个可执行文件
//   **7,029,248 B**，换成裸 socket 之后 **3,549,696 B** —— 差的那 3.5 MB
//   全是 `net/http` 拽进来的 `crypto/tls` 那一整套（我们只访问
//   `http://127.0.0.1`，一个 TLS 字节都用不到）。
//   这个工程在 OneDrive 下，12 个产物乘以这个差值就是用户的同步成本，
//   而这里要的判断只有"回环上有没有人、它回的是不是 200"。
//
// ★ "说 200 才算活着"不是多余的严格：这台机器设了系统代理，
//   而 `novelservice.py` 那边的经验是"代理会把回环请求也接走 ——
//   服务活着返回 200、服务死了返回 502，两者都算'有响应'"，于是判断完全跟着代理走
//   （实测结果：**重复起了第二个服务进程**）。
//   裸 socket 连 `127.0.0.1` 本来就**不可能**经过代理，从结构上避开那一类坑；
//   再认一下状态码，就能把"端口被别的程序占着"也排除掉。
func healthOK(port int, path string) bool {
	addr := fmt.Sprintf("127.0.0.1:%d", port)
	c, err := net.DialTimeout("tcp", addr, 1200*time.Millisecond)
	if err != nil {
		return false
	}
	defer func() { _ = c.Close() }()
	_ = c.SetDeadline(time.Now().Add(1500 * time.Millisecond))
	req := fmt.Sprintf("GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n", path, addr)
	if _, err := c.Write([]byte(req)); err != nil {
		return false
	}
	buf := make([]byte, 64)
	n, _ := c.Read(buf)
	if n <= 0 {
		return false
	}
	head := string(buf[:n])
	return strings.HasPrefix(head, "HTTP/1.") && strings.Contains(head, " 200")
}
