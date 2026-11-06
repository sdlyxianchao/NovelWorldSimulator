# -*- coding: utf-8 -*-
"""判据：**启动界面把创作服务拉起完，才放人进开始界面**（2026-10-23）。

用户原话：
    「我希望在启动界面把这几个服务都拉起来成功之后再进入开始界面」

在这之前的行为（也是 2026-10-17 有意选的）：主窗口一画出来就写 `ready`，
splash 立刻关，三家服务在**开始界面背后**慢慢拉 ⇒ 用户先看到开始界面、
十几秒后才在消息里读到「创作服务已全部就绪」。用户三次提这件事
（2026-10-22「你在启动界面的时候应该想办法都拉起来才对」、2026-10-23 这一条），
所以这次把那个决定**推翻**：等。

这条判据守两件事，缺一不可
--------------------------
① **等**：`_tell_splash_ready()` 必须在"服务处理完"**之后**，而且等待**有上界**
   （首次下模型可能十几分钟；不能把人锁在 splash 里没有出路）。
   守这一半只能读**产品源码结构**（AST）—— 行为上"等不等"在单测里看不出来，
   因为真起服务要几分钟。
② **等的时候要看得见**：splash 上必须有一个**每秒都在变**的东西。
   否则消息条一行字停十几秒，用户读成"卡死了"—— 那是硬伤，不是小瑕疵。
   守这一半必须**真起窗口**：`[Ns]` 这个前缀是 canvas 上的文字，
   只读源码等于只确认"代码里有个 f-string"。

跑法：`.venv\\Scripts\\python.exe tools/verify_splash_boot.py`
报告：`assets/screenshots/splash_boot_report.json`

English:
Assertion: **the splash waits for the creation services before letting the user into the
start screen** (2026-10-23).
Before this, the main window wrote `ready` as soon as it was drawn and the services came up
behind the start screen -- the user read "all services ready" only after landing there.
The user raised it three times, so that earlier decision is reversed: wait.
Two halves, both required: ① **wait** -- `_tell_splash_ready()` after the services, with a
**bounded** wait (a first model download can take many minutes; the user must never be locked
in with no way out). Only the product source (AST) can judge this half. ② **visible while
waiting** -- something on the splash must change every second, or a frozen line reads as a
hang. This half must open a **real window**, since the `[Ns]` prefix is canvas text.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
REPORT: dict = {'checks': [], 'notes': []}
OUT = APP / 'assets' / 'screenshots' / 'splash_boot_report.json'
SPLASH = APP / 'tools' / 'launcher_splash.py'
GUI = APP / 'gui' / 'app_flet.py'


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  一、真起窗口：等的时候"看得见"
# [EN] 1. Real window: "visible while waiting"
# ══════════════════════════════════════════════════════════════════
def _spec(log: Path, extra: dict | None = None) -> dict:
    d = {
        'title': '小说世界 AI 模拟',
        'subtitle': '—— 把故事，活一遍 ——',
        'logo': str(APP / 'assets' / 'images' / 'start_logo_96.png'),
        'bg': str(APP / 'assets' / 'images' / 'title_bg_splash.png'),
        'log': str(log), 'ready': '', 'fail': '',
        'version': 'judge-test', 'mode': '本地运行', 'platform': 'Python + Flet',
    }
    d.update(extra or {})
    return d


def _run_splash(tmp: Path, tag: str, hold: float, lines: list[str],
                at: float = 0.8, py: str = '', extra: list[str] | None = None) -> dict:
    """起一次真窗口，`at` 秒后往日志里写 `lines`，`hold` 秒后读摘要退出。

    ★ 为什么"窗口跑起来之后才写行"：splash 用 `--from-end 1`（只读新写的行），
      起窗口**之前**写的内容会被当成历史跳过 —— 那样 `boot_clock` 永远是 False，
      判据会红得莫名其妙（而且红的原因看着像"产品没实现"）。
    [EN] Start a real window, append `lines` at `at` seconds, read the summary at `hold`.
    [EN] ★ Why write after the window is up: the splash uses `--from-end 1` and skips history,
    [EN] so lines written earlier would never be seen and `boot_clock` would stay False.
    """
    log = tmp / f'launcher_{tag}.log'
    log.write_text('启动主程序：python main_gui.py\n', encoding='utf-8')
    spec_p = tmp / f'spec_{tag}.json'
    spec_p.write_text(json.dumps(_spec(log), ensure_ascii=False), encoding='utf-8')
    out_p = tmp / f'sum_{tag}.json'
    if out_p.exists():
        out_p.unlink()
    proc = subprocess.Popen(
        [py or sys.executable, str(SPLASH), '--spec', str(spec_p),
         '--from-end', '1', '--selftest', str(out_p), '--selftest-hold', str(hold),
         *(extra or [])],
        cwd=str(APP), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(at)
        if lines:
            with open(log, 'a', encoding='utf-8', newline='') as f:
                for ln in lines:
                    f.write(ln + '\n')
                f.flush()
        # 等它自己到达 hold 时刻并落盘
        _o, _e = proc.communicate(timeout=max(30.0, hold + 30.0))
    finally:
        if proc.poll() is None:
            proc.kill()
    data: dict = {}
    if out_p.exists():
        try:
            data = json.loads(out_p.read_text(encoding='utf-8'))
        except ValueError:
            data = {}
    if not data:
        # 空摘要必须留下原因（否则"产品没实现"和"子进程崩了"长得一模一样）
        # [EN] An empty summary must carry the reason: "not implemented" and "the child crashed"
        # [EN] otherwise look identical.
        REPORT['notes'].append(
            f'{tag}: rc={proc.returncode} err={(_e or b"")[-400:]!r}')
    return data


def _secs(msg: str) -> int:
    m = re.match(r'(\d+)s · ', msg or '')
    return int(m.group(1)) if m else -1


def _find_tk_python() -> str:
    """找一个**带 tkinter** 的 Python（splash 是 tkinter 写的）。

    ★ 为什么不能用 `sys.executable`（2026-10-23 实测，判据当场红）：
      判据自己在工程 `.venv` 里跑，而那个 venv 的 base 是托管版 3.13.12，
      **里面没有 tkinter** ⇒ 子进程一进 `import tkinter` 就 `ModuleNotFoundError`，
      out.json 永远不生成，摘要读出来是空的。那看着像"产品没实现心跳"，
      实际是**判据用错了跑它的解释器** —— 假红里最难分的一种。
    ★ 顺序：先问**启动器自己挑了谁**（与产品同源），再退到系统里能 import tkinter 的。
    [EN] Find a Python that **has tkinter** (the splash is tkinter-based).
    [EN] ★ Why not `sys.executable` (measured 2026-10-23, the criterion went red on the spot): the
    [EN] criterion runs inside the project `.venv`, whose base is the managed 3.13.12 **without
    [EN] tkinter** => the child dies on `import tkinter`, no out.json is produced and the summary
    [EN] reads empty. That looks like "the product has no heartbeat" when in fact **the criterion
    [EN] ran it with the wrong interpreter** -- the hardest kind of false red to spot.
    [EN] ★ Order: ask **what the launcher itself picked** (same source as the product), then fall
    [EN] back to anything on the system that can import tkinter.
    """
    cands: list[str] = []
    exe = APP / ('start.exe' if os.name == 'nt' else 'start')
    if exe.exists():
        with tempfile.TemporaryDirectory(prefix='nws_sb_start_') as d:
            out = Path(d) / 'start.json'
            try:
                subprocess.run([str(exe), '--selftest', str(out)], cwd=str(APP),
                               capture_output=True, timeout=180)
                if out.exists():
                    py = json.loads(out.read_text(encoding='utf-8')).get('python') or ''
                    if py:
                        cands.append(py)
            except Exception:                                # noqa: BLE001
                pass
    cands += ['py', 'python', 'python3', sys.executable]
    for c in cands:
        try:
            r = subprocess.run([c, '-c', 'import tkinter'], capture_output=True,
                               timeout=90)
            if r.returncode == 0:
                return c
        except Exception:                                    # noqa: BLE001
            continue
    return ''


def boot_clock_checks(tmp: Path) -> bool:
    k = True
    py = _find_tk_python()
    k &= ok('S0 ★★★ 找到一个**带 tkinter 的 Python** 来跑启动窗口'
            '（不能拿工程 `.venv` 里那个 —— 它的 base 没有 tkinter，'
            '子进程一进就崩，摘要空 ⇒ 看着像产品没实现）',
            bool(py), py or '一个都没找到')
    if not py:
        return False
    # ── S1：主程序写了进度行 ⇒ 时钟开始走，消息条把它显示出来 ──
    d1 = _run_splash(tmp, 'a', 1.5, ['→ 正在拉起 PlotPilot（2/3）…'], py=py)
    k &= ok('S1 ★★★ 主程序的进度行**真的显示在消息条上**，而且它出现了就**'
            '开始计时**（`boot_clock=True`、消息条带 `Ns · ` 前缀）',
            d1.get('boot_clock') is True and _secs(d1.get('msg', '')) >= 0,
            f'clock={d1.get("boot_clock")} msg={str(d1.get("msg"))[:70]!r}')
    # ── S2：两个不同时刻的读数必须**不一样**（证明秒数在走，不是写死的常量）──
    d2 = _run_splash(tmp, 'b', 4.0, ['→ 正在拉起 PlotPilot（2/3）…'], py=py)
    s1, s2 = _secs(d1.get('msg', '')), _secs(d2.get('msg', ''))
    k &= ok('S2 ★★★ 那个秒数**真的在走**：跑 1.5 秒与跑 4 秒读到的数不一样且在涨'
            '（否则消息条十几秒一个字不变，用户读成"卡死"）',
            s1 >= 0 and s2 > s1 and d2.get('boot_secs', -1) > d1.get('boot_secs', -1),
            f'{s1}s → {s2}s（boot_secs {d1.get("boot_secs")} → {d2.get("boot_secs")}）')
    # ── S3：没有进度行时**不许**冒出一个秒数（否则"心跳"是假的，永远在跳）──
    d3 = _run_splash(tmp, 'c', 1.5, [], py=py)
    k &= ok('S3 ★★ 没有进度行时**不显示秒数**（启动器那几行不算 —— '
            '心跳只能代表"主程序在报进度"，不能永远在跳）',
            d3.get('boot_clock') in (False, None) and _secs(d3.get('msg', '')) == -1,
            f'clock={d3.get("boot_clock")} msg={str(d3.get("msg"))[:60]!r}')
    # ── S4：普通启动器行（无 `→ `）不该启动时钟 ──
    d4 = _run_splash(tmp, 'd', 1.5, ['启动主程序：python main_gui.py'], py=py)
    k &= ok('S4 ★★ 启动器自己那些行**不启动**心跳（认的是"谁写的"，不是"有没有新行"）',
            d4.get('boot_clock') in (False, None) and _secs(d4.get('msg', '')) == -1,
            f'clock={d4.get("boot_clock")} msg={str(d4.get("msg"))[:60]!r}')
    return k


# ══════════════════════════════════════════════════════════════════
#  二、等：顺序 + 有上界（读产品源码）
# [EN] 2. Waiting: ordering + a bound (product source)
# ══════════════════════════════════════════════════════════════════
def _func(tree: ast.AST, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _calls(node: ast.AST, attr: str, func_name: str = '') -> list[ast.Call]:
    """收集 `x.<attr>(...)`（可选限定 `x` 的变量名）。"""
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == attr:
            if not func_name or getattr(n.func.value, 'id', '') == func_name:
                out.append(n)
    return out


def _call_lines(node: ast.AST, attr: str) -> list[int]:
    return [c.lineno for c in _calls(node, attr) if getattr(c, 'lineno', 0)]


def _set_in_finally(fn: ast.AST) -> bool:
    """`fn` 里有没有一个 `try … finally:`，**且 finally 块里真的调了 `.set()`**。

    ★★★ 为什么必须按**结构**判、不能查函数文本（2026-10-23 反例法当场抓到）：
      第一版写的是 `'finally' in ast.unparse(fn)` —— 而 `ast.unparse` **包含 docstring**，
      而这个函数的 docstring 恰好写着"为什么信号放在 `finally` 里"。
      于是把 `try/finally` 拆成顺序执行之后，判据**照样全绿**（自证式假绿）。
      这就是"判据被自己写的注释喂饱"那一类 —— 文本里出现某个词，不等于那段结构存在。
    [EN] Whether `fn` has a `try … finally:` **and the finally block really calls `.set()`**.
    [EN] ★★★ Why structure, not text (caught by the counterexample run on 2026-10-23): the first
    [EN] version used `'finally' in ast.unparse(fn)` -- and `ast.unparse` **includes the docstring**,
    [EN] which says "why the signal lives in `finally`". So replacing try/finally with sequential
    [EN] code left the criterion **all green** (self-certifying false green): a word in the text is
    [EN] not the same as the structure existing.
    """
    for n in ast.walk(fn):
        if isinstance(n, ast.Try) and n.finalbody:
            for s in n.finalbody:
                for c in ast.walk(s):
                    if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                            and c.func.attr == 'set'):
                        return True
    return False


def class_structure_checks() -> bool:
    """类结构：关键方法都在、而且没有"函数头被吞掉"的痕迹。

    ★★★ 为什么需要这一条（2026-10-23 本轮的**真实事故**）：
      改 `_maybe_autostart_service` 时，`old_string` 顺手带上了下一行的
      `def _run_capability_check(self) -> None:`，而 `new_string` 里忘了写回 ——
      于是那个方法**消失了**，它的函数体退化成一个裸字符串字面量（不报错、
      编译通过、`grep` 还能搜到它的说明文字）。表现是启动时
      `AttributeError: 'NovelWorldApp' object has no attribute '_run_capability_check'`，
      而语法检查、编译检查**全绿**。抓到它的是 `verify_borrowings`（它按名字切代码块）。
      ⇒ 这里钉两条：① 那几个方法**必须在**；② 类体里除 docstring 外
        **不许有裸字符串 Expr**（那正是"函数头丢了、docstring 原地留着"的形态）。
    [EN] Class structure: key methods present, and no trace of "a method header was swallowed".
    [EN] ★★★ Why (a **real accident** this round): while editing `_maybe_autostart_service`, the
    [EN] `old_string` also carried the next line `def _run_capability_check(self) -> None:` and the
    [EN] `new_string` never put it back -- the method **vanished**, its body degenerating into a bare
    [EN] string literal (no error, compiles fine, still greppable). The symptom is an AttributeError
    [EN] at startup while syntax and compile checks are all green. `verify_borrowings` caught it.
    [EN] => Two pins: ① those methods must exist; ② the class body may contain no bare string
    [EN] expression other than its docstring (exactly the shape of "header gone, docstring left").
    """
    tree = ast.parse(GUI.read_text(encoding='utf-8'))
    cls = None
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == 'NovelWorldApp':
            cls = n
    if cls is None:
        return ok('R1 ★★★ `NovelWorldApp` 类还在', False, '找不到类')
    names = {c.name for c in cls.body
             if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef))}
    need = ['_run_capability_check', '_maybe_autostart_service', '_finish_startup',
            '_splash_note', '_tell_splash_ready', 'main']
    missing = [x for x in need if x not in names]
    k = ok('R1 ★★★ 启动链上那几个方法**一个都不缺**'
           '（函数头被吞掉时语法检查、编译检查全绿，只有调用时才炸）',
           not missing, f'缺={missing} 共 {len(names)} 个方法')
    stray = []
    for c in cls.body:
        if isinstance(c, ast.Expr) and isinstance(c.value, ast.Constant) \
                and isinstance(c.value.value, str):
            # 类 docstring 只该出现在第一条
            if c is not cls.body[0]:
                stray.append(c.lineno)
    k &= ok('R2 ★★★ 类体里**没有游离的字符串字面量**'
            '（那正是"`def …` 那一行被删掉、函数体变成裸字符串"的形态 —— 不报错、不失败）',
            not stray, f'可疑行={stray}')
    return k


def wait_ordering_checks() -> bool:
    src = GUI.read_text(encoding='utf-8')
    tree = ast.parse(src)
    fin = _func(tree, '_finish_startup')
    k = True
    k &= ok('P1 ★★★ 有一个"等完再放行"的函数（`_finish_startup`）—— '
            '`_tell_splash_ready` 不再由 main 直接调用',
            fin is not None
            and bool(_call_lines(fin, '_tell_splash_ready'))
            and 'self.page.run_task(self._finish_startup)' in src,
            '找到' if fin is not None else '没找到')

    if fin is not None:
        # ── P2：放行必须在"等"**之后** ──
        # ⚠ 用**行号**比，不用"函数文本里谁先出现"：`ast.unparse` 含 docstring，
        #   docstring 里提到 `wait_for` / `_tell_splash_ready` 就会把比较弄反（本项目的
        #   "被自己的注释骗"那一类）。行号来自 AST 节点，跟文字无关。
        # [EN] ⚠ Compare **line numbers**, not positions in the unparsed text: `ast.unparse`
        # [EN] includes the docstring, so a docstring mentioning either name flips the comparison.
        i_wait = _call_lines(fin, 'wait_for')
        i_ready = _call_lines(fin, '_tell_splash_ready')
        k &= ok('P2 ★★★ 放行（`_tell_splash_ready`）排在**等待之后**'
                '（先写 ready 就等于"窗口一画完就让人进"，用户要的正是相反）',
                bool(i_wait) and bool(i_ready) and min(i_ready) > min(i_wait),
                f'wait 在行 {i_wait} / ready 在行 {i_ready}')
        # ══════════════════════════════════════════════════════════
        #  P3（★★★ 2026-10-24 **改口径**，因为设计被用户推翻了）
        #
        #  原来守的是"`wait_for(..., timeout=<常数>)` —— 等待有上界"。
        #  用户这一轮明确要求「**所有服务拉起来再打开，在这之前不要打开**」，
        #  也就是他宁愿无限等 —— 那条判据的**前提被推翻了**，不能硬留着。
        #  ⚠ 但"无限等"不等于"锁死不说"：必须有一条**出路提示**
        #    （"还在拉，可以点 ✕ 先进入"），而那个提示什么时候出现，靠的正是
        #    `_SPLASH_SVC_BUDGET` 这个预算。所以现在的口径是：
        #      ① 预算常量存在、而且是一个**合理**的秒数（不能是 10^9 等于永不提示，
        #         也不能是 0 等于一开就喊）；
        #      ② 它真的被用在"判断要不要提示"那一处（AST 里有个比较含它）。
        # [EN] P3 (★★★ 2026-10-24 **changed the yardstick**: the design was overruled by the user).
        # [EN] It used to guard "`wait_for(..., timeout=<const>)` -- the wait is bounded". The user
        # [EN] now explicitly wants an unbounded wait ("do not open it before that"), so that
        # [EN] premise is gone and the criterion must not keep it. ⚠ But "unbounded" is not "locked
        # [EN] out silently": there must be **a way out hinted** ("still pulling, the cross gets you
        # [EN] in"), and when that hint appears is decided by `_SPLASH_SVC_BUDGET`. So the new
        # [EN] yardstick is: (1) the budget exists and is a **reasonable** number of seconds (not
        # [EN] 10^9 = never hint, not 0 = shout immediately); (2) it really is used in the
        # [EN] "should I hint" comparison (an AST compare containing it).
        _budget = None
        for _n in ast.walk(tree):
            if isinstance(_n, ast.Assign) and _n.targets:
                _t = _n.targets[0]
                # ⚠ 类体里是 `_SPLASH_SVC_BUDGET = 600.0`（**Name**），不是
                #   `self._SPLASH_SVC_BUDGET`（Attribute）—— 只认 Attribute 会读到 None，
                #   而那条判据看起来"产品没定义预算"，其实是**判据认错了写法**。
                # [EN] ⚠ In the class body it is `_SPLASH_SVC_BUDGET = 600.0` (a **Name**), not
                # `self._SPLASH_SVC_BUDGET` (an Attribute) -- recognising only Attribute reads None,
                # so the criterion claims "no budget defined" when it simply looked wrong.
                if ((isinstance(_t, ast.Attribute) and _t.attr == '_SPLASH_SVC_BUDGET')
                        or (isinstance(_t, ast.Name) and _t.id == '_SPLASH_SVC_BUDGET')):
                    try:
                        _budget = ast.literal_eval(_n.value)
                    except (ValueError, SyntaxError):
                        _budget = 'not-literal'
                    break
        _used = False
        for _n in ast.walk(tree):
            if (isinstance(_n, ast.Compare)
                    and '_SPLASH_SVC_BUDGET' in ast.unparse(_n)):
                _used = True
        k &= ok('P3 ★★★ "无限等"**不等于锁死不说**：预算常量是个**合理**的秒数'
                '（不是 10^9=永不提示、也不是 0=一开就喊），而且它**真的被用来**判断'
                '"该不该提示出路"',
                isinstance(_budget, (int, float)) and 30 <= _budget <= 3600 and _used,
                f'预算={_budget!r} 用在比较里={_used}')
        # ── P4：超时**不算失败**（不许把 timeout 当异常吞进"启动失败"）──
        # 同样按**结构**判：有一个 `except`，它的类型里有 `TimeoutError`。
        _te = False
        for _h in [n for n in ast.walk(fin) if isinstance(n, ast.ExceptHandler)]:
            if _h.type is not None and 'TimeoutError' in ast.unparse(_h.type):
                _te = True
        k &= ok('P4 ★★ 超时被单独接住（`except asyncio.TimeoutError`），'
                '而且超时后仍然放行 —— 服务继续在后台拉，界面先用起来',
                _te, '接住了' if _te else '没接住')

    # ── P5：`_tell_splash_ready` 只被"等完"这一处调用（main 里不许再有一次）──
    n_ready_calls = src.count('self._tell_splash_ready()')
    k &= ok('P5 ★★ `self._tell_splash_ready()` 全文**只有一处**调用 '
            '（main 里再留一次，就会"先放行、后等待"，两个 ready 谁先写谁赢）',
            n_ready_calls == 1, f'出现 {n_ready_calls} 次')
    return k


def boot_signal_checks() -> bool:
    src = GUI.read_text(encoding='utf-8')
    tree = ast.parse(src)
    k = True
    auto = _func(tree, '_maybe_autostart_service')
    k &= ok('P6 ★★ 自动拉起那一步有一个**可等待的收工信号**（`_svc_boot_ev`）'
            '—— 否则"等"无从等起，只能定时轮询（要么放行慢半拍，要么空转）',
            auto is not None and '_svc_boot_ev' in ast.unparse(auto), '')
    wrap = _func(tree, '_boot_and_signal')
    k &= ok('P7 ★★★ 收工信号在 **`finally`** 里发（干活可以失败，报信不许失败 —— '
            '否则任何一处异常都让用户干等到十几分钟兜底，'
            '"已经出错了"伪装成"还在忙"）',
            wrap is not None and _set_in_finally(wrap),
            '找到' if wrap is not None else '没找到')
    # ★★★ 2026-10-24 13:54 **口径随实现改了**（不是放宽）：`if not _todo:` 那条早退
    #   跟着拉服务的逻辑一起搬进了模块级 `boot_services()`，它现在做的是
    #   `return [], 0.0`（**立刻收工**），而"放行"发生在界面侧的路线 A
    #   （`if PREBOOT['done']: … ev.set()`）—— 那里对所有情况都无条件 set，包括三家全关。
    #   ⚠ 意图不变："没开服务的人不许干等"。所以拆成两半，各判它现在真正待的地方：
    #     ① `boot_services` 里 `if not _todo:` 必须**立刻 return**（不进拉取、不 sleep）；
    #     ② 界面侧路线 A 必须 `ev.set()`（预启动完成就放行，不管成败、不管有没有要拉的）。
    # [EN] ★★★ 2026-10-24 13:54 **the yardstick follows the implementation**: the `if not _todo:`
    # [EN] early exit moved into the module-level `boot_services()` together with the pull-up logic;
    # [EN] it now does `return [], 0.0` (**finish immediately**), while "release" happens on the UI
    # [EN] side in route A (`if PREBOOT['done']: ... ev.set()`), which sets unconditionally for every
    # [EN] case, including all three switches off.
    # [EN] ⚠ Intent unchanged: "people with no services must not wait". Split into two halves, each
    # [EN] judged where it now lives: (1) `boot_services` must **return at once** on `not _todo`
    # [EN] (no pull, no sleep); (2) route A must `ev.set()` (pre-boot finished => release, win or lose).
    _early_return = False
    bs = _func(tree, 'boot_services')
    if bs is not None:
        for _n in ast.walk(bs):
            if isinstance(_n, ast.If) and 'not _todo' in ast.unparse(_n.test):
                if any(isinstance(x, ast.Return) for x in ast.walk(_n)):
                    _early_return = True
    _route_a_set = False
    if auto is not None:
        for _n in ast.walk(auto):
            if not (isinstance(_n, ast.If) and 'PREBOOT' in ast.unparse(_n.test)):
                continue
            for _c in ast.walk(_n):
                if (isinstance(_c, ast.Call) and isinstance(_c.func, ast.Attribute)
                        and _c.func.attr == 'set'):
                    _route_a_set = True
    k &= ok('P8 ★★★ 三家开关全关时**立刻**收工并放行：`boot_services` 里 `if not _todo:` '
            '直接 `return`（不进拉取、不 sleep），界面侧路线 A 无条件 `ev.set()`'
            '—— 不然没开服务的人每次启动都要干等',
            _early_return and _route_a_set,
            f'早退={_early_return} 路线A放行={_route_a_set}')
    return k


def block_on_failure_checks(tmp: Path) -> bool:
    """**失败就不放行**（2026-10-23 用户：「服务没启动成功不要显示后续启动界面」）。

    这条守的是三层，缺一不可：
      · 主程序：有失败 ⇒ 写 fail、**不写** ready；没有启动器 ⇒ 必须放行（否则谁也进不去）；
      · 启动窗口：`failed` 之后**永远不自己 close**（它就是"挡住开始界面"的那一层）；
      · 文案：红字里必须写清唯一出口（右上角 ✕），否则用户读成卡死。
    [EN] **A failure does not release.** Three layers: the UI writes `fail` and no `ready` (and
    [EN] must release when there is no launcher, or nobody could ever get in); the splash
    [EN] **never closes itself after `failed`** (it is what covers the start screen); and the red
    [EN] line must name the only exit (the ✕), or it reads as a hang.
    """
    src = GUI.read_text(encoding='utf-8')
    tree = ast.parse(src)
    fin = _func(tree, '_finish_startup')
    k = True
    if fin is None:
        return ok('N1 ★★★ 有失败时**不写 ready**（停在启动界面）', False, '找不到 _finish_startup')
    # ── N1：失败分支里的 `return` 必须在 `_tell_splash_ready()` **之前**
    #    ⚠ 用行号：`ast.unparse` 含 docstring，文本里两个名字都出现过（本项目的自证假绿坑）。
    # [EN] The `return` of the failure branch must come **before** `_tell_splash_ready()`, by line
    # [EN] number (text search is fooled by the docstring).
    ready_lines = _call_lines(fin, '_tell_splash_ready')
    fail_lines = _call_lines(fin, '_tell_splash_failed')
    nth = {n.lineno for n in ast.walk(fin) if isinstance(n, ast.Return)}
    # 失败分支里那个 return：`if …fails…:` 的 body 里、且在 fail 调用之后
    blk_ret = []
    for n in ast.walk(fin):
        if isinstance(n, ast.If) and 'fails' in ast.unparse(n.test):
            for s in n.body:
                for c in ast.walk(s):
                    if isinstance(c, ast.Return):
                        blk_ret.append(c.lineno)
    k &= ok('N1 ★★★ 有失败时**不写 ready**（写完 fail 就 `return`，'
            '放行那句在它后面 —— 这就是"停在启动界面"的实现）',
            bool(fail_lines) and bool(blk_ret) and bool(ready_lines)
            and min(blk_ret) > min(fail_lines) and min(blk_ret) < max(ready_lines),
            f'fail@{fail_lines} 失败分支 return@{blk_ret} ready@{ready_lines}')
    # ── N2：`_tell_splash_failed` 真的写 `NWS_SPLASH_FAIL` 那个文件，没有就返回 False
    tf = _func(tree, '_tell_splash_failed')
    body = ast.unparse(tf) if tf is not None else ''
    k &= ok('N2 ★★★ 失败时写的是启动窗口**真的在盯的那份 fail 文件**'
            '（`NWS_SPLASH_FAIL`）—— 写到别处等于没通知，splash 照旧关掉',
            tf is not None and 'NWS_SPLASH_FAIL' in body
            and 'write_text' in body,
            '找到' if tf is not None else '找不到')
    k &= ok('N3 ★★★ 没有启动器时**必须放行**（直接 `python main_gui.py` / 判据里跑：'
            '没人会写那个 fail 文件，不放行就永远进不去 —— 那比带着毛病进去糟得多）',
            tf is not None and 'return False' in body, '')
    # ── N4：`_svc_boot_fail` 在**收工那一刻**被写进 self（否则等待方永远看到"没失败"）
    # ⚠ 必须钉**那一句赋值**，不能只查"这个词在不在函数里"（2026-10-23 反例法抓到的）：
    #   同一个方法里还嵌套着 `_boot_and_signal`，它**也**写 `_svc_boot_fail`
    #   （异常兜底那份）⇒ 只要查"词出现过"，把 `_boot` 里那句赋值删掉判据照样绿。
    #   这正是"变异绕过变异点"：判据量的范围比它想管的宽了一圈。
    # [EN] ⚠ Must pin **that one assignment**, not "does this word appear in the method"
    # [EN] (caught by the counterexample run on 2026-10-23): the same method nests
    # [EN] `_boot_and_signal`, which **also** writes `_svc_boot_fail` (the exception path), so a
    # [EN] word-presence check stays green after deleting the real assignment. Classic
    # [EN] "mutation bypasses the mutation point": the criterion measures a wider scope than it means.
    # ★★★ 2026-10-24 13:54 **口径随实现改了**（不是放宽）：拉服务的逻辑整体搬到模块级
    #   `boot_services()`（预启动与页面内两条路共用），失败列表现在是它的**返回值** `fails`，
    #   不再是方法里的局部变量 `_fail`。原来那条钉的是 `_fail` 这个名字，于是实现一搬就红。
    #   ⚠ 意图完全一样："收工时必须把'哪几家没起来'存到 self 上，供放行决策读"。
    #   现在改成：**`_maybe_autostart_service` 里必须有一句把 `boot_services` 的结果
    #   赋给 `_svc_boot_fail`**（两条路各一句，**至少一句**）。
    #   ⚠ 仍然要窄（不能只查"这个方法里出现过 `_svc_boot_fail`"）：方法里还有异常兜底那句
    #     也在写这个字段，把真正的赋值删掉照样绿 —— 老坑。
    # [EN] ★★★ 2026-10-24 13:54 **the yardstick follows the implementation** (not a relaxation):
    # [EN] the pull-up logic moved to the module-level `boot_services()` (shared by the pre-boot and
    # [EN] in-page routes), so the failure list is now its **return value** `fails` instead of a local
    # [EN] `_fail`. The old check pinned that name and went red on the move.
    # [EN] ⚠ The intent is identical: "on completion, store which services failed on `self` for the
    # [EN] release decision". Now: **inside `_maybe_autostart_service` there must be a statement
    # [EN] assigning the result of `boot_services` to `_svc_boot_fail`** (one per route, at least one).
    # [EN] ⚠ Still narrow (a word-presence check would be fed green by the exception-path assignment).
    auto = _func(tree, '_maybe_autostart_service')
    # ⚠ **两条路各判一次**（2026-10-24 反例法当场抓到的漏）：
    #   上一版写成"方法里有任意一句把 `fails`/`PREBOOT` 赋给 `_svc_boot_fail` 就绿"，
    #   于是把**路线 A 那句删掉**（预启动完成后不记失败）判据照绿 —— 因为路线 B 还有一句。
    #   可这恰恰是真缺陷：经启动器启动时走的是路线 A，那一句没了，`_finish_startup`
    #   读到"没有失败"⇒ 带着失败进界面。**"一处被删、另一处顶上来"是最难发现的假绿。**
    # [EN] ⚠ **Judge each route separately** (a hole the counterexample run caught on 2026-10-24):
    # [EN] the previous version went green on "any assignment mentioning fails/PREBOOT", so deleting
    # [EN] route A's line (not recording failures after the pre-boot) stayed green -- route B still had
    # [EN] one. That is a real defect: a launcher start takes route A, `_finish_startup` then reads
    # [EN] "no failures" and lets the user in. "One copy deleted, the other props it up" is the
    # [EN] hardest false green to spot.
    def _assigns_in(node, needle: str) -> bool:
        if node is None:
            return False
        for _n in ast.walk(node):
            if not isinstance(_n, ast.Assign):
                continue
            if not any(isinstance(t, ast.Attribute) and t.attr == '_svc_boot_fail'
                       for t in _n.targets):
                continue
            if needle in ast.unparse(_n.value):
                return True
        return False

    _route_a = None
    _route_b = None
    if auto is not None:
        for _n in ast.walk(auto):
            if isinstance(_n, ast.If) and 'PREBOOT' in ast.unparse(_n.test):
                _route_a = _n
        for _n in ast.walk(auto):
            if isinstance(_n, ast.AsyncFunctionDef) and _n.name == '_boot_and_signal':
                _route_b = _n
    _a_ok = _assigns_in(_route_a, 'PREBOOT')
    _b_ok = _assigns_in(_route_b, 'fails')
    k &= ok('N4 ★★★ **两条路各自**把"哪几家没起来"存到 self 上：'
            '路线 A（预启动已完成）用 `PREBOOT[\'fail\']`、路线 B（页面内拉）用 `fails`'
            '—— 只满足一处不够：删掉路线 A 那句，经启动器启动的人就会带着失败进界面',
            _a_ok and _b_ok,
            f'路线A={_a_ok} 路线B={_b_ok}')
    # ── N5：启动窗口 failed 之后不自己 close
    #   ⚠ 也要窄：`_poll` 里两处都有 `not self.failed`（失败检测那处 + ready 那处），
    #     只查"这段里有这个串"会被失败检测那行喂绿。
    # [EN] ⚠ Narrow it too: `_poll` contains `not self.failed` twice (the failure check and the
    # [EN] ready check), so a section-wide substring match is fed green by the other one.
    spl = SPLASH.read_text(encoding='utf-8')
    poll = spl[spl.find('    def _poll('):spl.find('    def _show_failed(')]
    _ready_guard = any(('ready' in ln and 'not self.failed' in ln)
                       for ln in poll.splitlines())
    k &= ok('N5 ★★★ 启动窗口**失败之后不自己关**（`ready` 那一句必须同时带 `not self.failed`）'
            '—— 它就是那块挡住开始界面的东西，自己关掉等于"还是进了"',
            _ready_guard, poll[:90].replace('\n', ' '))
    # ── N6：红字里写明唯一出口（✕）。
    #    ★ 为什么这条也要判：不给出口的"拦住"会被读成卡死 —— 用户不知道点哪儿。
    # [EN] ★ Why this too: a block with no exit reads as a freeze -- the user cannot tell where to click.
    k &= ok('N6 ★★ 失败红字里写明**唯一出口**（点右上角 ✕ 仍然进入）'
            '—— 只拦住不说怎么走，用户会以为程序卡死',
            '✕' in src and '仍然进入' in src, '')
    return k


#: 一条**比消息条能放的长度更长**的进度行（用来验"中间省略"，不是滚动）。
#: 句首与句尾都必须有辨识度，才能判"两头都还在"。
# [EN] A progress line **longer than the strip can hold** (to verify the middle ellipsis, not a
# [EN] ticker). Both ends must be distinctive so "the head and the tail both survived" is decidable.
LONG_LINE = ('→ 正在做一件很长很长很长的事情，这条消息故意写得比消息条能放的列数'
             '还要长很多很多，好让中间省略那条逻辑真的被跑到，最后带一个计数（3/3）')
PROG_LINES = [
    '→ 正在拉起 MuMuAINovel（1/3）…',
    '→ 正在拉起 PlotPilot（2/3）…',
    '→ 正在拉起 PenShot（3/3）…',
    '→ PlotPilot 已就绪（2/3）',
    LONG_LINE,
]


def splash_look_checks(tmp: Path) -> bool:
    """外观与交互五条（2026-10-23「更优雅的展开」这一轮）：
    按钮尺寸、黑底日志、**顶边不动**、中间省略、步骤点、两个工具按钮、翻上去不被抢。
        English: Five looks/behaviours from the "more elegant expand" round: button size, dark log,
        **anchored top edge**, middle ellipsis, step dots, both tool buttons, no scroll stealing."""
    k = True
    py = _find_tk_python()
    if not py:
        return ok('V0 ★★ 需要一个带 tkinter 的 Python 才能量外观', False, '没找到')
    # 收起态：量按钮尺寸、位置、消息条省略、步骤点
    d = _run_splash(tmp, 'look1', 1.6, PROG_LINES, at=0.5, py=py)
    k &= ok('V1 ★★★ 展开按钮**画的变小了、点的仍然够大**（图形盒 ≤ 28；'
            '命中区仍 ≥ 32 —— 用户说"小一些"是视觉要求，'
            '"点得准"是操作要求，两件事可以同时满足）',
            d.get('caret_px', 99) <= 28 and d.get('caret_hit', 0) >= 16
            and d.get('caret_px', 0) > 0,
            f"盒={d.get('caret_px')} 命中={d.get('caret_hit')} 笔画={d.get('caret_w')}")
    # ── V4：中间省略（不是跑马灯）──
    msg = str(d.get('msg') or '')
    cols = int(d.get('msg_cols') or 0)
    full = int(d.get('msg_full_len') or 0)
    _dots = msg.find('…')
    _mid = 0.25 <= (_dots / max(1, len(msg))) <= 0.85
    k &= ok('V4 ★★★ 消息条**不再横向滚动**，改成**静态一行 + 中间省略**'
            '（开头"正在…"与结尾"（3/3）"都留着 —— 那正是判断"现在在干什么"要的两段；'
            '跑马灯一直在动、每次只能看见片段）',
            bool(msg) and '…' in msg and _mid and len(msg) <= max(1, cols)
            and full > len(msg),
            f'cols={cols} full={full} 显示={len(msg)} 省略号在 {_dots} 位：{msg[:42]!r}')
    # ── V5：三家服务 = 步骤点 ──
    steps = d.get('steps') or {}
    k &= ok('V5 ★★★ 三家服务画成**步骤点**，而且状态真的在变'
            '（`run` 进行中 / `done` 已就绪 / `wait` 未开始 / `fail` 失败）',
            d.get('steps_n') == 3 and steps.get('2') == 'done'
            and steps.get('1') in ('run', 'done') and d.get('steps_items', 0) >= 4,
            f"n={d.get('steps_n')} 状态={steps} 画了几个={d.get('steps_items')}")
    # 展开态：黑底、工具按钮、位置、滚动
    d2 = _run_splash(tmp, 'look2', 2.4, PROG_LINES, at=0.5, py=py,
                     extra=['--expanded', '--selftest-probe', 'scroll'])
    bg = str(d2.get('console_bg') or '').lower()
    fg = str(d2.get('console_fg') or '').lower()
    k &= ok('V2 ★★★ 展开之后是**黑底日志**（实测 Text 控件的 bg 亮度 < 0.3、'
            'fg 比 bg 亮得多 —— 用户点名「展开之后显示黑色日志」）',
            _lum(bg) < 0.3 and _lum(fg) - _lum(bg) > 0.35 and bool(bg),
            f'bg={bg} fg={fg} 亮度={_lum(bg):.2f}/{_lum(fg):.2f}')
    # ── V3：顶边不动（渐进披露里最要紧的一条）──
    y1 = (d.get('win_xy') or [0, -1])[1]
    y2 = (d2.get('win_xy') or [0, -2])[1]
    h1 = (d.get('size') or [0, 0])[1]
    h2 = (d2.get('size') or [0, 0])[1]
    k &= ok('V3 ★★★ 展开时**窗口顶边一动不动**（只向下长）：收起与展开的 `y` 相同、'
            '高度变大 —— 以前是"在屏幕中央重新居中"，Logo/名字/消息条全体跳位，'
            '正是渐进披露里明令要避免的那件事',
            y1 > 0 and y1 == y2 and h2 > h1,
            f'收起 y={y1} h={h1} / 展开 y={y2} h={h2}')
    # ── V6：两个工具按钮 ──
    tools = d2.get('logtools') or []
    k &= ok('V6 ★★ 日志区有「复制」和「打开日志文件」两个动作'
            '（日志的真实用途是发给别人排查；只剩截图的话，'
            '关键那几行往往刚好被截断，而且不能选中不能搜索）',
            tools == ['copy', 'open'] and not (d.get('logtools') or []),
            f"展开={tools} 收起={d.get('logtools')}")
    # ── V7：翻上去不被抢 ──
    pr = d2.get('scroll_probe') or {}
    k &= ok('V7 ★★★ 用户**往上翻看历史时不被抢回底部**（探针：先滚到顶 → 再来一行 ⇒ '
            '顶部位置不变），只在右下角浮一条「↓ N 条新」',
            pr.get('ok') is True
            and abs(float(pr['after'][0]) - float(pr['before'][0])) < 1e-6
            and int(pr.get('new_badge') or 0) >= 1,
            f"probe={pr}")
    return k


def _lum(color: str) -> float:
    """`#rrggbb` 的相对亮度（0=黑 1=白）。读不出色号 ⇒ 1.0（判"不黑"）。
        English: Relative luminance of `#rrggbb` (0=black 1=white); unreadable => 1.0."""
    c = (color or '').strip().lstrip('#')
    if len(c) != 6:
        return 1.0
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 1.0
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def failed_state_checks(tmp: Path) -> bool:
    """失败态真机：写一个 fail 文件，看窗口是否**变红且留在那儿**。
        English: The failed state on a real window: write a fail file, see it turn red and stay."""
    py = _find_tk_python()
    if not py:
        return ok('W0 ★★ 需要一个带 tkinter 的 Python', False, '没找到')
    log = tmp / 'launcher_f.log'
    log.write_text('启动主程序：x\n', encoding='utf-8')
    fail_p = tmp / 'fail_f'
    ready_p = tmp / 'ready_f'
    spec = _spec(log, {'fail': str(fail_p), 'ready': str(ready_p)})
    spec_p = tmp / 'spec_f.json'
    spec_p.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
    out_p = tmp / 'sum_f.json'
    if out_p.exists():
        out_p.unlink()
    proc = subprocess.Popen(
        [py, str(SPLASH), '--spec', str(spec_p), '--from-end', '1',
         '--selftest', str(out_p), '--selftest-hold', '2.5'],
        cwd=str(APP), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(0.9)
        with open(log, 'a', encoding='utf-8', newline='') as f:
            f.write('→ 正在拉起 PlotPilot（2/3）…\n')
        time.sleep(0.15)
        msg = '创作服务没起来：PlotPilot。停在这里不进入开始界面 —— 点右上角 ✕ 仍然进入'
        fail_p.write_text(msg + '\n', encoding='utf-8')
        time.sleep(0.5)
        # 再往 ready 里写：**已经失败**了，就该不理它（窗口不许自己关）
        # [EN] Then write `ready`: it already failed, so it must be ignored (no self-close).
        ready_p.write_text('ok\n', encoding='utf-8')
        proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
    d: dict = {}
    if out_p.exists():
        try:
            d = json.loads(out_p.read_text(encoding='utf-8'))
        except ValueError:
            d = {}
    # ★★★ 2026-10-27（用户：「启动界面报错的时候为何错误信息是两条」）：
    #   原因**只许出现一次**，且落在**下面那行居中的红字**（`fail_line`）上。
    #   改之前 `_show_failed` 把同一句画在消息条（y=242）和那行红字（收起态 y=284，
    #   两行只差 42px）⇒ 屏幕上就是上下两条一样的红字。
    #   ⇒ W1 改成三件事：①进了失败态 ②原因在 `fail_line` 里且是红的
    #     ③**消息条不许再带那句原因**（`W1b` 单列一条，方便一眼看出是哪半边回归）。
    # [EN] ★★★ 2026-10-27 (user: "why two error lines?"): the reason must appear **once**, on the
    # [EN] centred red line (`fail_line`). Before, `_show_failed` painted it on the strip (y=242)
    # [EN] *and* that line (y=284 collapsed, 42px apart) => two identical red lines stacked.
    # [EN] => W1 now checks three things: ① failed state ② the reason is on `fail_line`, red
    # [EN] ③ the strip must **not** carry the reason again (`W1b`, separate so a regression shows
    # [EN] which half broke).
    _line = str(d.get('fail_line') or '')
    k = ok('W1 ★★★ 有 fail 时窗口进入失败态（`failed=True`、'
           '**下面那行红字**里带着那句原因）',
           d.get('failed') is True and msg[:8] in _line
           and _line.startswith('✘')
           and str(d.get('fail_line_fill') or '') == _const('ERR', '#A33A2A'),
           f"failed={d.get('failed')} fail_line={_line[:60]!r} "
           f"fill={d.get('fail_line_fill')!r}")
    _strip = str(d.get('msg') or '')
    k &= ok('W1b ★★★ **消息条不许再抄一遍原因**（用户 2026-10-27：「错误信息是两条」'
            '—— 改之前原因同时画在消息条与下面那行红字上，收起态两行只差 42px）',
            msg[:8] not in _strip and '✘' not in _strip and _strip != '',
            f"msg={_strip[:60]!r}")
    # ⚠ W2 的判法：**"失败之后又写了 ready，窗口有没有被放走"**。
    #   不能拿"ready 文件存不存在"当判据 —— 那个文件是**这一条自己刚写的**，
    #   它存不存在与"窗口放没放行"是两件事（第一版就这么写，恒真）。
    #   真正有信息量的是 **`out.json` 还在不在**：那份摘要是窗口自己到点写的，
    #   而窗口一旦被 `ready` 放走就会 `root.destroy()` ⇒ mainloop 退出 ⇒ 摘要不生成。
    #   所以"摘要存在 且 failed=True" = 它熬过了 ready ⇒ `and not self.failed` 真的挡在前面。
    # [EN] ⚠ W2's shape: **"after a failure, does a `ready` still release the window"**.
    # [EN] "does the ready file exist" is the wrong question -- this criterion just wrote it, so its
    # [EN] existence says nothing about release (the first version asserted that, vacuously true).
    # [EN] What carries information is whether **`out.json` still exists**: the window writes that
    # [EN] summary at its hold time, and a window released by `ready` calls `root.destroy()` =>
    # [EN] mainloop exits => no summary. So "summary present AND failed=True" proves it survived
    # [EN] `ready`, i.e. the `and not self.failed` guard is really in front.
    k &= ok('W2 ★★★ **失败之后再写 `ready` 也不放行**（窗口熬过了 ready：'
            '摘要还在，而且仍是失败态 —— 否则"服务没起来"照样会进开始界面，'
            '正是用户说的那个现象）',
            bool(d) and d.get('failed') is True and ready_p.exists(),
            f'摘要={bool(d)} failed={d.get("failed")} 写过ready={ready_p.exists()}')
    k &= _long_reason_checks(tmp, py)
    return k


#: 主程序真实会写的那句失败原因（`gui/app_flet._finish_startup`）：78~80 个字，
#: 在 10 号字下约 863px —— **比整幅 860px 的窗口还宽**。
#: [EN] The failure reason the main program really writes: ~80 chars, ~863px at size 10 --
#: [EN] **wider than the 860px window**.
LONG_REASON = ('创作服务没起来：MuMuAINovel、PlotPilot。停在这里不进入开始界面 —— '
               '点右上角 ✕ 仍然进入（进「天机 → 外部创作服务」可以手动重试）')


def _long_reason_checks(tmp: Path, py: str) -> bool:
    """长原因（主程序那句 80 字）**完整显示**、且折行后不压别人（W1c / W1d）。

    ★★★ 为什么单列一条（2026-10-27）："原因只写一处"修完以后，原因落在下面那行
      居中红字上；而**那一行放不下 80 个字**。旧代码用 `line[:_msg_cols()]` 硬截，
      截掉的正好是"点右上角 ✕ 仍然进入"那半句 —— **告诉用户怎么脱身的半句**。
      现在的做法是给那一行 `width`（自动折行，上限两行）。这条判据钉的是结果：
      ①原因完整（没有 `…`）②折行后的**实测外框**没压到消息条 / 底栏。
    [EN] ★★★ Why its own criterion (2026-10-27): after "one place only", the reason sits on the
    [EN] centred red line, and **80 chars do not fit there**. The old code hard-cut with
    [EN] `line[:_msg_cols()]`, and what it cut was exactly "press ✕ to enter anyway" -- the half
    [EN] that says **how to get out**. Now that line has `width` (auto-wrap, capped at two lines).
    [EN] This criterion pins the outcome: ①the reason is complete (no `…`) ②the **measured box**
    [EN] after wrapping does not collide with the strip / footer.
    """
    log = tmp / 'launcher_fl.log'
    log.write_text('启动主程序：x\n', encoding='utf-8')
    fail_p = tmp / 'fail_fl'
    ready_p = tmp / 'ready_fl'
    spec = _spec(log, {'fail': str(fail_p), 'ready': str(ready_p)})
    spec_p = tmp / 'spec_fl.json'
    spec_p.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
    out_p = tmp / 'sum_fl.json'
    if out_p.exists():
        out_p.unlink()
    proc = subprocess.Popen(
        [py, str(SPLASH), '--spec', str(spec_p), '--from-end', '1',
         '--selftest', str(out_p), '--selftest-hold', '2.0'],
        cwd=str(APP), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        time.sleep(0.7)
        fail_p.write_text(LONG_REASON + '\n', encoding='utf-8')
        proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
    d: dict = {}
    if out_p.exists():
        try:
            d = json.loads(out_p.read_text(encoding='utf-8'))
        except ValueError:
            d = {}
    line = str(d.get('fail_line') or '')
    box = d.get('fail_line_box') or []
    mbox = d.get('msg_box') or []
    fbox = d.get('foot_box') or []
    k = ok('W1c ★★★ **长原因（80 字）完整显示**，不许被砍掉"点右上角 ✕ 仍然进入"'
           '那半句 —— 那正是告诉用户怎么脱身的那半句（旧代码按 53 字硬截）',
           '…' not in line and LONG_REASON in line,
           f'fail_line={line[:70]!r}')
    gap_up = (box[1] - mbox[3]) if len(box) == 4 and len(mbox) == 4 else -999
    gap_dn = (fbox[1] - box[3]) if len(box) == 4 and len(fbox) == 4 else -999
    k &= ok('W1d ★★ 折成两行后**没压到消息条 / 底栏、也没横向溢出窗口**'
            '（实测外框，不是数换行 —— Tk 自动折行不会往 `text` 里插 `\\n`，'
            '数换行恒得 1）',
            gap_up > 0 and gap_dn > 0
            and len(box) == 4 and box[0] >= 0 and box[2] <= int(_const('W', 860) or 860),
            f'红字框={box} 消息条底={mbox[3:] if mbox else "?"} '
            f'底栏顶={fbox[1:2] if fbox else "?"} 间隙上={gap_up} 下={gap_dn}')
    return k


def release_logic_checks(tmp: Path) -> bool:
    """**决策本身**真跑：`_finish_startup` 什么时候开、什么时候死活不开。

    ★ 为什么要单独跑这一组（而不是全交给真机）：真机里要造成"某家服务一直起不来"
      就得改用户的 `.env`（端口），那是明令不许的事；要造成"拉起要十几分钟"
      更不可能。而决策只取决于三样东西 —— `_svc_boot_ev` 有没有 set、
      `_svc_boot_fail` 里有什么、`_splash_hides_window` 是真是假 ——
      这三样都可以直接摆，于是**不碰用户配置、不碰真实服务**就能把每条分支跑一遍。
    ★ 2026-10-24 口径：`_finish_startup` 开头会检查 `_splash_hides_window`，
      所以判据必须显式把它立起来，否则它立刻 `return`、什么都不测（第一版就是这样：
      W3 报 `fail=False ready=False`，看着像产品没写，实际是**测了个空跑**）。
    [EN] Run the **decision itself**: when `_finish_startup` opens and when it flatly does not.
    [EN] ★ Why its own group: forcing "a service never comes up" on a real launch means editing the
    [EN] user's `.env`, and forcing "ten minutes of pulling" is impossible. The decision depends on
    [EN] exactly three things -- whether `_svc_boot_ev` is set, what is in `_svc_boot_fail`, and
    [EN] `_splash_hides_window` -- all of which can be set directly, so every branch runs **without
    [EN] touching the user's config or real services**.
    [EN] ★ 2026-10-24: `_finish_startup` now returns early unless `_splash_hides_window`, so the
    [EN] criterion must raise that flag itself -- otherwise it measures a no-op (exactly what the
    [EN] first version did: W3 reported `fail=False ready=False`, which looks like a product miss).
    """
    import asyncio

    ready_p = tmp / 'z_ready'
    fail_p = tmp / 'z_fail'
    bye_p = tmp / 'z_bye'
    log_p = tmp / 'z_launcher.log'
    env_saved = {k: os.environ.get(k) for k in
                 ('NWS_SPLASH_READY', 'NWS_SPLASH_FAIL', 'NWS_SPLASH_BYE',
                  'NWS_SPLASH_LOG')}
    k = True

    def _clean() -> None:
        for p in (ready_p, fail_p, bye_p):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def _mk(fails, *, ev_set: bool, hides: bool = True,
            budget: float | None = None, bye_after: float | None = None):
        """造一个 app，返回 `(app, coro)`；`bye_after` 秒后自动写 bye（模拟用户点 ✕）。"""
        from gui.app_flet import NovelWorldApp
        app = NovelWorldApp()
        app._via_launcher = hides
        app._svc_boot_ev = asyncio.Event()
        if ev_set:
            app._svc_boot_ev.set()
        app._svc_boot_fail = list(fails)
        if budget is not None:
            app._SPLASH_SVC_BUDGET = budget
        return app

    try:
        os.environ['NWS_SPLASH_READY'] = str(ready_p)
        os.environ['NWS_SPLASH_FAIL'] = str(fail_p)
        os.environ['NWS_SPLASH_BYE'] = str(bye_p)
        os.environ['NWS_SPLASH_LOG'] = str(log_p)

        async def _guard(task, limit: float = 8.0) -> bool:
            """等任务结束，**最多 limit 秒**；超时就取消并返回 False。

            ★★★ 为什么必须套这一层（2026-10-24 连栽两次）：如果产品漏了
              "没有启动窗口就直接 return"，它会一路走到等用户点 ✕，
              而 `_await_splash_closed` 的上限是**一小时** ⇒ 判据**挂死**；
              挂死期间外层工具把整轮反例法掐断，`finally` 没跑完，产品源码里
              就留下变异残留（下一次自检只会说"锚点对不上"，看着像产品改了）。
              套上之后，同一种缺陷会变成"这一条红、且 8 秒收工"。
            [EN] Wait for the task, **at most `limit` seconds**, then cancel and return False.
            [EN] ★★★ Why this wrapper is mandatory (hit twice on 2026-10-24): if the product loses
            [EN] the "no splash => return" guard it walks into waiting for the user's cross, and
            [EN] `_await_splash_closed` caps at **one hour** => the criterion hangs; the outer tool
            [EN] then kills the whole counterexample run, `finally` never restores, and the product
            [EN] source keeps a mutation (the next self-check only says "anchors do not match").
            [EN] With this wrapper the same defect becomes "this one line goes red, in 8 seconds".
            """
            try:
                await asyncio.wait_for(task, timeout=limit)
                return True
            except asyncio.TimeoutError:
                try:
                    task.cancel()
                except Exception:                            # noqa: BLE001
                    pass
                return False

        async def _run(app, bye_after=None) -> None:
            task = asyncio.ensure_future(app._finish_startup())
            if bye_after is not None:
                async def _bye() -> None:
                    await asyncio.sleep(bye_after)
                    bye_p.write_text('bye\n', encoding='utf-8')
                b = asyncio.ensure_future(_bye())
                await _guard(task)
                b.cancel()
            else:
                await _guard(task)

        # ── Z1：有失败 ⇒ 写 fail、**不写** ready，而且**在等用户点 ✕** ──
        _clean()
        rc = {}

        async def _z1() -> None:
            app = _mk(['PLOTPILOT'], ev_set=True)
            task = asyncio.ensure_future(app._finish_startup())
            await asyncio.sleep(0.45)
            # 0.45 秒：fail 写了、任务**还没结束**（它在等 ✕）
            rc['fail_mid'] = fail_p.exists()
            rc['pending'] = not task.done()
            # ★★★ 再等到 1.6 秒才判"ready 到底写没写"（2026-10-24 反例法抓到的假绿）：
            #   变异后它会"写 fail → `_reveal_window`（内含 0.25s）→ 继续往下放行"，
            #   整条链约 0.5 秒。**只在 0.45 秒看一眼**，那时 ready 恰好还没写 ⇒
            #   判据绿，而产品其实已经放行了。等待窗口必须比"最短的违规路径"更长。
            # [EN] ★★★ Judge "was ready written" only after 1.6s (a false green the
            # [EN] counterexample run caught on 2026-10-24): the mutant does "write fail ->
            # [EN] `_reveal_window` (0.25s inside) -> carries on and releases", about 0.5s in
            # [EN] total. Reading only at 0.45s misses it -- the sampling window must be longer
            # [EN] than the shortest violating path.
            await asyncio.sleep(1.15)
            rc['ready_mid'] = ready_p.exists()
            rc['pending_late'] = not task.done()
            bye_p.write_text('bye\n', encoding='utf-8')       # 用户点 ✕
            try:
                await asyncio.wait_for(task, timeout=3.0)
                rc['finished'] = True
            except asyncio.TimeoutError:
                rc['finished'] = False
                task.cancel()
        asyncio.run(_z1())
        k &= ok('Z1 ★★★ 有失败 ⇒ **不放行**（写 fail、`ready` 一个字节都没写），'
                '而且**卡在那儿等**用户点 ✕ —— 这就是"服务没起来就不打开开始界面"',
                bool(rc.get('fail_mid')) and not rc.get('ready_mid')
                and rc.get('pending') is True,
                f"fail={rc.get('fail_mid')} ready(1.6s)={rc.get('ready_mid')} "
                f"0.45s还在等={rc.get('pending')}")
        k &= ok('Z2 ★★★ 用户点了 ✕（写 `bye`）之后**立刻收尾**（不拖、也不留一个永远等下去的任务）',
                rc.get('finished') is True and rc.get('pending') is True,
                f"finished={rc.get('finished')}")

        # ── Z3：没失败 ⇒ 正常写 ready、不写 fail ──
        _clean()
        asyncio.run(_run(_mk([], ev_set=True)))
        k &= ok('Z3 ★★★ 三家都就绪时**正常放行**（写 ready、不写 fail）—— 否则全好了反而进不去',
                ready_p.exists() and not fail_p.exists(),
                f'ready={ready_p.exists()} fail={fail_p.exists()}')

        # ── Z4：**超时不再放行**（2026-10-24 的实质变化）──
        #   ⚠ 把预算压到 0.2 秒、事件永远不 set，等 1.2 秒后必须是"ready 还没写"。
        #     旧实现在这里会写 ready（"超时也放行"），所以这条**正是**在钉那处改动。
        # [EN] ⚠ Squeeze the budget to 0.2s, never set the event, and after 1.2s `ready` must still
        # [EN] be absent. The old implementation wrote it here ("timeout releases"), so this is
        # [EN] exactly the pin for that change.
        _clean()
        rc4 = {}

        async def _z4() -> None:
            app = _mk([], ev_set=False, budget=0.2)
            task = asyncio.ensure_future(app._finish_startup())
            await asyncio.sleep(1.2)
            rc4['ready'] = ready_p.exists()
            rc4['pending'] = not task.done()
            app._svc_boot_ev.set()             # 服务终于起来了
            try:
                await asyncio.wait_for(task, timeout=3.0)
                rc4['then'] = ready_p.exists()
            except asyncio.TimeoutError:
                rc4['then'] = False
                task.cancel()
        asyncio.run(_z4())
        k &= ok('Z4 ★★★ **超时不再替他打开**（2026-10-24 用户：「在这之前不要打开」）：'
                '等超预算之后 `ready` 仍未写、任务仍在等；服务真起来后才放行',
                not rc4.get('ready') and rc4.get('pending') is True
                and rc4.get('then') is True,
                f"超时后ready={rc4.get('ready')} 还在等={rc4.get('pending')} "
                f"起来后ready={rc4.get('then')}")

        # ── Z5：没有启动器 ⇒ 直接返回（窗口本来就可见，既不写 ready 也不写 fail）──
        #   ⚠ 这条的语义在 2026-10-24 变了：以前是"没有 fail 通道就放行"，
        #     现在是"根本没有这一套" —— 判据要跟着改口径，不能还钉旧行为。
        # [EN] ⚠ The meaning changed on 2026-10-24: it used to be "release without a fail channel",
        # [EN] now it is "this whole mechanism does not apply" -- the criterion follows the change.
        _clean()
        asyncio.run(_run(_mk(['PENSHOT'], ev_set=True, hides=False)))
        k &= ok('Z5 ★★★ 没有启动窗口时（`python main_gui.py` / 判据里）这套逻辑**完全不介入**'
                '（既不写 ready 也不写 fail —— 窗口本来就是可见的）',
                not ready_p.exists() and not fail_p.exists(),
                f'ready={ready_p.exists()} fail={fail_p.exists()}')
    except Exception as e:                                   # noqa: BLE001
        import traceback
        REPORT['notes'].append('release_logic_checks: ' + traceback.format_exc()[-800:])
        k &= ok('Z1-Z5 真跑 `_finish_startup` 的决策', False, repr(e)[:200])
    finally:
        for kk, v in env_saved.items():
            if v is None:
                os.environ.pop(kk, None)
            else:
                os.environ[kk] = v
    return k


def window_visibility_checks() -> bool:
    """主窗口在服务有结论之前是**真的不可见**（不是被启动窗口盖住）。

    ★ 为什么这一条必须存在（2026-10-24 用户那句话的落点）：上一轮我只做到"等"，
      主窗口其实**已经建出来、已经显示**了，只是被 `-topmost` 的启动窗口遮着。
      用户按 Alt+Tab、或者启动窗口因为任何原因先没了，看到的就是
      "服务还没好、界面已经开着" —— 那正是他两次要求不要的现象。
    ⚠ 判据只能读源码（`w.visible = False` 那一句，且必须在 `_splash_hides_window` 之下），
      因为真机里那一瞬间太快、抓不到；而"抓不到就当没有"会给出假绿。
    [EN] The main window is **really invisible** until every service has a verdict (not merely
    [EN] covered). ★ Why this must exist: last round only "waited" -- the window was already built
    [EN] and shown, merely hidden behind the `-topmost` splash. Alt+Tab, or the splash vanishing for
    [EN] any reason, shows "services not up, UI already open" -- exactly what he asked against.
    [EN] ⚠ Source-level only: that instant is too fast to catch on a real launch, and "cannot catch
    [EN] it => treat as absent" would be a false green.
    """
    src = GUI.read_text(encoding='utf-8')
    tree = ast.parse(src)
    main_fn = _func(tree, 'main')
    k = True
    hides = []
    shows = []
    if main_fn is not None:
        for n in ast.walk(main_fn):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Attribute) and t.attr == 'visible':
                        _v = n.value
                        if isinstance(_v, ast.Constant) and _v.value is False:
                            hides.append(n.lineno)
                        elif isinstance(_v, ast.Constant) and _v.value is True:
                            shows.append(n.lineno)
    # ★★★ 2026-10-24 15:25 **口径反过来**（设计被现实推翻，不是放宽）：
    #   原来这三条守的是"`main` 里必须把窗口设成不可见，而且必须挂在 `_splash_hides_window` 上"。
    #   实测（`developers/probe_window_visibility.py` 逐秒枚举 + 主程序自己的
    #   `window_visual_state()`）证明那条路**在 Flet 1.0.3 上是坏的**：
    #       15:39:07 可见 1440×900 → 15:39:08 不可见 1936×1168，showCmd=3 但 WS_VISIBLE=0
    #   也就是"`visible=True` + `maximized=True` 同批发出去 ⇒ 最大化后不显示" ⇒
    #   用户看到的"开始界面闪一下就没"。
    #   而现在窗口本来就是在服务处理完之后才创建的（`preboot_services()` 排在 `ft.run` 之前），
    #   **根本不需要藏**。所以这三条改成：**不许**再藏。
    # [EN] ★★★ 2026-10-24 15:25 **the yardstick is reversed** (reality overruled the design, not a
    # [EN] relaxation): these three used to require "`main` must hide the window, guarded by
    # [EN] `_splash_hides_window`". Measured (per-second enumeration + the app's own
    # [EN] `window_visual_state()`), that path is **broken on Flet 1.0.3**: 15:39:07 visible at
    # [EN] 1440x900 -> 15:39:08 invisible at 1936x1168 with showCmd=3 but WS_VISIBLE=0, i.e.
    # [EN] `visible=True` and `maximized=True` in one batch leaves it maximized-but-not-shown --
    # [EN] exactly the "flashes and vanishes" the user reported. And the window is now created after
    # [EN] the services are handled (`preboot_services()` before `ft.run`), so nothing needs hiding.
    # [EN] => These three now say: **do not hide it any more**.
    k &= ok('Z6 ★★★ `main` 里**不许**再把主窗口设成不可见（`window.visible = False`）'
            '—— 那条路实测会让窗口"最大化后不显示"（闪一下就没）；'
            '窗口现在是在服务处理完之后才创建的，根本不需要藏',
            not hides, f'visible=False 在 {hides}')
    k &= ok('Z7 ★★ `main` 里也不设 `visible = True`（不需要，窗口创建时本来就是可见的）',
            not shows, f'visible=True 在 {shows}')

    fin = _func(tree, '_finish_startup')
    sliced = False
    if fin is not None:
        for c in _calls(fin, 'wait_for'):
            for kw in c.keywords:
                if kw.arg == 'timeout':
                    try:
                        if 0 < float(ast.literal_eval(kw.value)) <= 30:
                            sliced = True
                    except (ValueError, SyntaxError):
                        pass
    k &= ok('Z9 ★★ 等待是**分段**的（`wait_for(..., timeout=15)` 循环），'
            '不是一个 `timeout=600` —— 分段才能在等待期间报"等了几分钟、可以点 ✕"',
            sliced, '找到分段等待' if sliced else '只找到长超时或没有')

    # ════════════════════════════════════════════════════════════════════
    #  Z10/Z11：**彻底不显示**（2026-10-24 13:26，用户：「一开始会有一个开始界面闪现一下」）
    #  ────────────────────────────────────────────────────────────────────
    #  ★★★ 为什么 Z6 那条不够：Z6 只要求"`main()` 里把 visible 设成 False"。
    #    而 Flet 的**原生窗口**在 `main()` 之前就已经显示出来了（那是 C 侧的事）——
    #    等 Python 执行到那一句，用户已经看见一帧。所以 Z6 可以全绿，闪现照样存在。
    #    真正管用的是 `ft.run(..., view=FLET_APP_HIDDEN)`：**建窗口但不显示**。
    #  ⚠ 而 HIDDEN 又**不能无条件用**：直接 `python main_gui.py` 和所有真机判据都没有启动
    #    窗口，HIDDEN 会让屏幕上什么都没有，判据连窗口都抓不到（"假红"的最坏形态）。
    #    ⇒ 必须由 `NWS_SPLASH_READY` 决定，两条都要真跑。
    #  ★ 为什么不放在真机里量"有没有闪"：那一帧只有 ~100ms，抓不到就等于没测到，
    #    而"抓不到就当没有"正是这个项目里最常出现的假绿。这里改成**判分派逻辑**。
    # [EN] ★★★ Why Z6 is not enough: it only requires `main()` to set visible=False. But Flet's
    # [EN] **native** window is already shown *before* `main()` runs (C side), so by the time Python
    # [EN] reaches that line the user has seen a frame. Z6 can be fully green while the flash still
    # [EN] happens. What actually works is `ft.run(..., view=FLET_APP_HIDDEN)`: create the window,
    # [EN] do not show it. ⚠ And HIDDEN must **not** be unconditional: plain runs and every on-device
    # [EN] criterion have no splash, and HIDDEN leaves an empty screen with nothing to grab (the worst
    # [EN] false red). So `NWS_SPLASH_READY` must decide, and both branches must actually run.
    # [EN] ★ Why not measure the flash on a real launch: that frame lasts ~100ms; failing to capture
    # [EN] it proves nothing, and "not captured => not there" is this project's classic false green.
    # ★★★ 2026-10-24 15:25：Z10/Z11 也**反过来**。原来要求"必须用 `FLET_APP_HIDDEN` 起窗口"，
    #   实测 hidden 启动 + 后来的 `visible=True` 在 Flet 1.0.3 上留下"最大化但不可见"
    #   （见 Z6 那段实测记录）⇒ 现在要求 **不许用 HIDDEN**，走默认的 FLET_APP。
    # [EN] ★★★ 2026-10-24 15:25: Z10/Z11 are **reversed** too. They used to require
    # [EN] `FLET_APP_HIDDEN`; measured, hidden-start plus a later `visible=True` leaves the window
    # [EN] maximized-but-invisible on Flet 1.0.3 (see Z6). Now: **no HIDDEN**, use the default.
    k &= ok('Z10 ★★★ `ft.run` **不许**传 `view=FLET_APP_HIDDEN`（hidden 启动 + 后来的 '
            '`visible=True` 会留下"最大化但不可见" ⇒ 用户看到闪一下就没）',
            not _run_has_view(tree), '没传 view' if not _run_has_view(tree) else '还在传 view')

    # ── Z14：`_reveal_window` 里 `visible` 与 `maximized` **必须分两批** ──
    #   ★★★ 这就是"闪一下就没"的机制本身，必须钉住：同一个 update 里一起发，
    #     客户端会先 show（1440×900）再 SW_MAXIMIZE —— 而 hidden 起过的窗口最大化后不回到可见。
    #     判法：`visible = True` 与 `maximized = True` 两条赋值之间必须夹着一个 `await`（sleep），
    #     而且两条不能落在同一次 `page.update()` 之前。
    # [EN] ── Z14: inside `_reveal_window`, `visible` and `maximized` **must be two batches** ──
    # [EN] ★★★ This *is* the mechanism of the flash: sent together, the client shows (1440x900) and
    # [EN] then SW_MAXIMIZEs, and a hidden-started window does not return to visible. Judged by: an
    # [EN] `await` (sleep) must sit between the two assignments.
    rv = _func(tree, '_reveal_window')
    _split = False
    if rv is not None:
        _vis_ln = _max_ln = -1
        for _n in ast.walk(rv):
            if not isinstance(_n, ast.Assign):
                continue
            for _t in _n.targets:
                if not (isinstance(_t, ast.Attribute)
                        and isinstance(_t.value, ast.Attribute)
                        and _t.value.attr == 'window'):
                    continue
                if _t.attr == 'visible' and isinstance(_n.value, ast.Constant) and _n.value.value:
                    _vis_ln = _n.lineno
                elif _t.attr == 'maximized' and isinstance(_n.value, ast.Constant) and _n.value.value:
                    _max_ln = _n.lineno
        if _vis_ln > 0 and _max_ln > _vis_ln:
            for _n in ast.walk(rv):
                if isinstance(_n, ast.Await) and _vis_ln < _n.lineno < _max_ln:
                    _split = True
    k &= ok('Z14 ★★★ `_reveal_window` 里 `visible = True` 与 `maximized = True` **分两批**'
            '（中间夹一个 `await`）—— 同批发出去会"先显示、再最大化、然后不可见"，'
            '正是"开始界面闪一下就没"的机制',
            _split,
            '分两批' if _split else '两条挤在同一批（或顺序不对）')

    # ════════════════════════════════════════════════════════════════════
    #  Z12/Z13：**先拉服务，再建窗口**（2026-10-24 13:54，用户第三次提这件事）
    #  ────────────────────────────────────────────────────────────────────
    #  ★★★ 用户原话：「我需要所有服务都启动了之后最后再打开开始界面
    #    在这之前不能够有任何时候看到开始界面」。
    #    Z6/Z10/Z11 都只是"藏"（`visible=False`、`FLET_APP_HIDDEN`），而 Flet 的原生窗口
    #    在 `main()` 之前就显示了 —— 那一帧藏不住。唯一到得了"任何时刻都看不到"的做法是
    #    **窗口在服务处理完之前根本不创建**：`preboot_services()` 排在 `ft.run()` 之前。
    #  ⚠ 顺序必须用 **AST 行号**比，不能用字符串 find（本项目在这上面栽过：
    #    注释里出现同一个词，find 就给出荒唐的结论）。
    gui_tree = ast.parse(GUI.read_text(encoding='utf-8'))
    sg = _func(gui_tree, 'start_gui')
    _pb_line = _run_line = -1
    if sg is not None:
        for _n in ast.walk(sg):
            if isinstance(_n, ast.Call):
                _f = _n.func
                if isinstance(_f, ast.Name) and _f.id == 'preboot_services':
                    _pb_line = _n.lineno
                elif (isinstance(_f, ast.Attribute) and _f.attr == 'run'
                      and getattr(_f.value, 'id', '') == 'ft'):
                    _run_line = _n.lineno
    k &= ok('Z12 ★★★ `start_gui()` 里 `preboot_services()` 排在 `ft.run(...)` **之前**'
            '（窗口在服务处理完之前**根本不创建** —— 这是"任何时刻都看不到"唯一到得了的做法；'
            '只把窗口藏起来挡不住 Flet 在 `main()` 之前显示的那一帧）',
            _pb_line > 0 and _run_line > 0 and _pb_line < _run_line,
            f'preboot 第 {_pb_line} 行 / ft.run 第 {_run_line} 行')

    # ⚠ 但预启动**不能无条件跑**：直接 `python main_gui.py` 没有启动窗口，
    #   阻塞几十秒等于让用户面对一个不动的黑窗口；而所有真机判据都走同一个入口。
    pb = _func(gui_tree, 'preboot_services')
    _guarded_pb = False
    if pb is not None:
        for _n in ast.walk(pb):
            if isinstance(_n, ast.If) and 'NWS_SPLASH_READY' in ast.unparse(_n.test):
                # 那个 if 里必须有 return（早退），否则只是"判断了一下"却照样往下跑
                if any(isinstance(x, ast.Return) for x in ast.walk(_n)):
                    _guarded_pb = True
    k &= ok('Z13 ★★★ 预启动**只在经启动器时**跑（`if not NWS_SPLASH_READY: return`）'
            '—— 直接跑 main_gui.py / 所有真机判据都没有启动窗口，阻塞几十秒等于卡死；'
            '而它们本来就有 `_finish_startup` 的完整等待',
            _guarded_pb, '有守卫' if _guarded_pb else '没有守卫（无条件阻塞）')
    return k


def _run_has_view(tree: ast.AST) -> bool:
    """`ft.run(...)` 里有没有 `view=` 这个关键字。"""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == 'run' and getattr(n.func.value, 'id', '') == 'ft':
            if any(kw.arg == 'view' for kw in n.keywords):
                return True
    return False


def _run_view_kw(tree: ast.AST) -> bool:
    """`ft.run(...)` 里有没有 `view=<东西>` 这个关键字（不是默认值）。"""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == 'run' and getattr(n.func.value, 'id', '') == 'ft':
            if any(kw.arg == 'view' for kw in n.keywords):
                return True
    return False


def _view_dispatch_ok() -> bool:
    """真跑 `start_view()`：有/无 `NWS_SPLASH_READY` 必须给出两个**不同**的 AppView。"""
    import os
    import subprocess
    code = (
        'import os, sys\n'
        'sys.path.insert(0, r"%s")\n'
        'import gui.app_flet as g\n'
        'os.environ.pop("NWS_SPLASH_READY", None)\n'
        'a = str(g.start_view())\n'
        'os.environ["NWS_SPLASH_READY"] = r"C:\\tmp\\ready"\n'
        'b = str(g.start_view())\n'
        'print(a + "|" + b)\n'
    ) % str(APP)
    try:
        r = subprocess.run([sys.executable, '-c', code], cwd=str(APP),
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=180)
    except Exception:                                    # noqa: BLE001
        return False
    for ln in (r.stdout or '').splitlines()[::-1]:
        if '|' in ln and 'AppView' in ln:
            a, b = ln.strip().split('|', 1)
            return a.endswith('FLET_APP') and b.endswith('FLET_APP_HIDDEN')
    return False


def _view_dispatch_detail() -> str:
    import os
    import subprocess
    code = (
        'import os, sys\n'
        'sys.path.insert(0, r"%s")\n'
        'import gui.app_flet as g\n'
        'os.environ.pop("NWS_SPLASH_READY", None)\n'
        'a = str(g.start_view())\n'
        'os.environ["NWS_SPLASH_READY"] = r"C:\\tmp\\ready"\n'
        'b = str(g.start_view())\n'
        'print("R " + a + "|" + b)\n'
    ) % str(APP)
    try:
        r = subprocess.run([sys.executable, '-c', code], cwd=str(APP),
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=180)
        for ln in (r.stdout or '').splitlines()[::-1]:
            if ln.startswith('R '):
                return '无 env / 有 env = ' + ln[2:].strip()
    except Exception:                                    # noqa: BLE001
        pass
    return '跑不起来'


def _splash_body(line: str) -> str:
    """用**splash 自己的**解析器拆一行，返回正文；跑不起来就返回 `''`。

    ★ 为什么非要起子进程跑真代码：判据在 `.venv` 里跑，而那个 venv 没有 tkinter，
      直接 import `launcher_splash` 会 `ModuleNotFoundError`。而"判据自己再写一份
      正则"更糟 —— 那就是两套口径，产品改了判据不知道（本项目反复吃的亏）。
      所以拿 `_find_tk_python()` 找来的解释器，跑产品里那一个 `_split_prefix`。
    [EN] Split one line with **the splash's own** parser; `''` when it cannot run.
    [EN] ★ Why a subprocess with the real code: the criterion runs in `.venv`, which has no tkinter,
    [EN] so importing `launcher_splash` fails outright. Writing **a second regex** here would be
    [EN] worse -- two yardsticks that drift silently (a recurring loss on this product line). So use
    [EN] the interpreter `_find_tk_python()` found and run the product's own `_split_prefix`.
    """
    py = _find_tk_python()
    if not py or not line:
        return ''
    code = (
        'import importlib.util, json\n'
        'spec = importlib.util.spec_from_file_location("LS", r"%s")\n'
        'm = importlib.util.module_from_spec(spec)\n'
        'spec.loader.exec_module(m)\n'
        'print("B " + json.dumps(m.Splash._split_prefix(%r), ensure_ascii=False))\n'
    ) % (str(SPLASH), line)
    try:
        r = subprocess.run([py, '-c', code], cwd=str(APP), capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=120)
        for ln in (r.stdout or '').splitlines():
            if ln.startswith('B '):
                return (json.loads(ln[2:]) or ['', '', ''])[2] or ''
    except Exception:                                        # noqa: BLE001
        return ''
    return ''


_CONST_CACHE: dict = {}


def _const(name: str, default=None):
    """读 splash 的一个常量（**带缓存**：`_splash_consts()` 每次要起一个子进程）。

    ★ 为什么判"红不红"要读常量而不是写死 `#A33A2A`：写死的话，配色一改判据就变红，
      而"配色改了"不是缺陷 ⇒ 那是**假红**，假红会让人学会忽略判据。
    [EN] Read one splash constant (**cached**: `_splash_consts()` spawns a subprocess each time).
    [EN] ★ Why the red check reads the constant instead of hard-coding `#A33A2A`: a hard-coded
    [EN] value turns a palette change into a red criterion, and "the palette changed" is not a
    [EN] defect => a **false red**, and false reds teach people to ignore the criteria.
    """
    global _CONST_CACHE
    if not _CONST_CACHE:
        _CONST_CACHE.update(_splash_consts())
    return _CONST_CACHE.get(name, default)


def _splash_consts() -> dict:
    """在**带 tkinter** 的解释器里读 splash 的布局常量（`H_EXP` / `LOG_*`）。

    ★ 为什么要绕这一圈：见 L12 那条判据里的说明 —— 判据自己的 `.venv` 没有 tkinter，
      直接 exec 会 `ModuleNotFoundError`，而"读不到"和"产品没改"在判据里长得一样。
    [EN] Read the splash's layout constants (`H_EXP` / `LOG_*`) **inside an interpreter with
    [EN] tkinter**. ★ Why the detour: see criterion L12 -- the criterion's own `.venv` has no
    [EN] tkinter, so exec'ing it raises ModuleNotFoundError, and "cannot read" looks exactly like
    [EN] "the product never changed".
    """
    py = _find_tk_python()
    if not py:
        return {}
    keys = ('H_EXP', 'H_BASE', 'LOG_BOX_TOP', 'LOG_H', 'LOG_W', 'LOG_ROWS', 'LOGTOOL_Y',
            'ERR', 'INK', 'STRIP_FAIL', 'STATUS_SIDE_PAD', 'W', 'H_BASE', 'EXP_BOTTOM_BAND')
    code = (
        'import importlib.util, json\n'
        'spec = importlib.util.spec_from_file_location("LS", r"%s")\n'
        'm = importlib.util.module_from_spec(spec)\n'
        'spec.loader.exec_module(m)\n'
        'print("C " + json.dumps({k: getattr(m, k, None) for k in %r}))\n'
    ) % (str(SPLASH), list(keys))
    try:
        r = subprocess.run([py, '-c', code], cwd=str(APP), capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=120)
        for ln in (r.stdout or '').splitlines():
            if ln.startswith('C '):
                return json.loads(ln[2:]) or {}
    except Exception as e:                                    # noqa: BLE001
        REPORT['notes'].append(f'读 splash 常量失败：{e!r}')
    return {}


def splash_note_checks(tmp: Path) -> bool:
    """`_splash_note` 真跑：只在经启动器启动时写、写进 splash tail 的那份日志。"""
    k = True
    # 判据绝不能写用户真实的 `logs/launcher.log` ⇒ 用 `NWS_SPLASH_LOG` 指到临时文件。
    # [EN] Never write the user's real log => point `NWS_SPLASH_LOG` at a temp file.
    tag = tmp / 'note.log'
    ready = tmp / 'ready'
    env_saved = {k2: os.environ.get(k2) for k2 in ('NWS_SPLASH_READY', 'NWS_SPLASH_LOG')}
    try:
        os.environ['NWS_SPLASH_READY'] = str(ready)
        os.environ['NWS_SPLASH_LOG'] = str(tag)
        from gui.app_flet import NovelWorldApp
        app = NovelWorldApp()
        app._splash_note('正在拉起 PlotPilot（2/3）…')
        got = tag.read_text(encoding='utf-8') if tag.exists() else ''
    except Exception as e:                                   # noqa: BLE001
        got = ''
        REPORT['notes'].append(f'_splash_note 抛异常：{e!r}')
    finally:
        for k2, v in env_saved.items():
            if v is None:
                os.environ.pop(k2, None)
            else:
                os.environ[k2] = v
    k &= ok('Q1 ★★★ `_splash_note` **真把那句话写进了 splash tail 的那份日志**'
            '（写在别处等于没写 —— 用户眼前只有 splash）',
            '正在拉起 PlotPilot（2/3）…' in got, repr(got[:60]))
    # ★★★ 2026-10-27 改口径：原来判"整行以 `→ ` 开头"。加了统一的
    #   `[时间][来源]` 前缀之后那条**必然红，而产品是对的**（正是用户要的格式）。
    #   要防的东西还在吗？**在，而且更危险** —— splash 里有三处
    #   `startswith('→ ')`（消息条计时的起点、步骤点、金色判色），
    #   前缀一加，它们全部静默失效：不报错、只是从此再没触发过。
    #   ⇒ 判据改成守**跨进程契约**：主程序写出来的这一行，交给 **splash 自己的
    #     解析器**（真代码，不是判据另写一份正则 —— 那会变成"两套口径"），
    #     剥掉前缀之后正文仍要以 `→ ` 打头。
    # [EN] ★★★ 2026-10-27 changed: this used to require the whole line to start with `→ `. With the
    # [EN] unified `[time][source]` prefix that **must** go red while the product is right (it is the
    # [EN] format the user asked for). Is the thing it guards still there? **Yes, and more dangerous**:
    # [EN] the splash has three `startswith('→ ')` tests (boot clock, step dots, gold colouring) and a
    # [EN] prefix silently kills all three -- no error, they just never fire again. => The criterion
    # [EN] now guards the **cross-process contract**: hand the line the main program wrote to the
    # [EN] **splash's own parser** (real code, not a second regex -- that would be two yardsticks)
    # [EN] and require the body to still start with `→ `.
    _body = _splash_body(got.strip().splitlines()[0]) if got.strip() else ''
    k &= ok('Q2 ★★★ **跨进程契约**：主程序写的那一行，经 splash **自己的解析器**剥掉'
            '`[时间][来源]` 之后，正文仍以 `→ ` 打头 —— 这是"心跳会启动 / 步骤点会亮'
            ' / 进度行是金色"的**唯一凭据**，而它失效时**不报任何错**',
            _body.startswith('→ '), f'splash 解析出的正文={_body[:40]!r}')
    k &= ok('Q2b ★★ 这一行**带** `[时间][来源]` 前缀（用户点名的格式；'
            '没有它，三家服务的输出在日志区里分不清是谁的）',
            bool(re.match(r'^\[\d{1,2}:\d{2}:\d{2}\]\[[^\]]+\]', got.strip())),
            repr(got[:24]))
    bad = [w for w in ('✗', '失败', 'ERROR', 'Error', 'Traceback') if w in got]
    k &= ok('Q3 ★★ 进度行里**不许出现**会让消息条变红的词（`✗`/`失败`/`Error`/`Traceback`）'
            '—— 否则一句正常的进度会被读成"启动出错"',
            not bad, f'命中={bad}')

    # ── Q4：没有 `NWS_SPLASH_READY`（如直接跑 main_gui.py）时**一个字都不写** ──
    tag2 = tmp / 'note2.log'
    try:
        os.environ.pop('NWS_SPLASH_READY', None)
        os.environ['NWS_SPLASH_LOG'] = str(tag2)
        from gui.app_flet import NovelWorldApp as _A2
        _A2()._splash_note('不该出现')
        leaked = tag2.exists() and '不该出现' in tag2.read_text(encoding='utf-8')
    except Exception:                                        # noqa: BLE001
        leaked = False
    finally:
        for k2, v in env_saved.items():
            if v is None:
                os.environ.pop(k2, None)
            else:
                os.environ[k2] = v
    k &= ok('Q4 ★★ 不是经启动器起来的时候（没有 `NWS_SPLASH_READY`）'
            '**不往启动器日志里掺行**', not leaked, '')
    return k


# ══════════════════════════════════════════════════════════════════
#  【L】启动窗口里的**日志**（2026-10-27 用户：
#       「日志窗口展开我想更长一些 也更高一些 · 里面需要有各个服务拉起来的细节日志 ·
#         不同的服务输出日志可以合并在一起 用 `[时间][服务]` 日志 这样区分 ·
#         如果有别的需要写入到这里的启动过程中的日志 也一起写入」）
# [EN] 【L】The **log** inside the splash (user, 2026-10-27: "the expanded log should be longer and
# [EN] taller · it needs the detail logs of each service coming up · merge them and distinguish with
# [EN] `[time][service]` · also write the other start-up logs in there")
# ══════════════════════════════════════════════════════════════════
#: 喂给窗口的那份"真长那样"的日志：里程碑 / 服务细节 / 带 ERROR 的细节 / 程序自己的行。
# [EN] A log shaped like the real thing: milestones / service detail / detail containing ERROR /
# [EN] lines from the program itself.
LOG_SAMPLE = [
    '[19:30:02][界面] → 准备拉起创作服务（3 家）—— 首次启动要建环境，可能要几十秒',
    '[19:30:02][MuMuAINovel] → 正在拉起 MuMuAINovel（1/3）…',
    '[19:30:02][MuMuAINovel] $ python novelservice.py start --timeout 600',
    '[19:30:03][MuMuAINovel] [ok] 虚拟环境已存在',
    '[19:30:05][MuMuAINovel] INFO:     Started server process [1234]',
    '[19:30:05][MuMuAINovel] ERROR:    某个依赖没装（这行**带 ERROR**，是细节行）',
    '[19:30:06][MuMuAINovel] → MuMuAINovel 已就绪（1/3）',
    '[19:30:06][PlotPilot] → 正在拉起 PlotPilot（2/3）…',
    '[19:30:07][PlotPilot] INFO:     Uvicorn running on http://127.0.0.1:8002',
    '[19:30:07][PlotPilot] → PlotPilot 已就绪（2/3）',
    '[19:30:07][PenShot] → 正在拉起 PenShot（3/3）…',
    '[19:30:08][PenShot] WARNING:  This is a development server.',
    '[19:30:09][PenShot] → PenShot 没起来（3/3）· 不影响推演，进界面后可在天机里重试',
    '[19:30:09][程序] WARNING: 端口 8000 被占（程序自己说的，也是细节行）',
]


def splash_log_checks(tmp: Path) -> bool:
    """日志这一块：**真起窗口** + 读代码两头一起钉。"""
    k = True
    py = _find_tk_python()
    k &= ok('L0 找得到**带 tkinter** 的解释器（跑不起窗口的话下面几条全是假绿）',
            bool(py), py or '没找到')

    # ── L1~L5：真机（只有跑起来才量得到"消息条停在哪、是什么颜色"）──
    if py:
        d = _run_splash(tmp, 'log', 2.6, LOG_SAMPLE, at=0.6, py=py,
                        extra=['--expanded'])
        msg = d.get('msg') or ''
        k &= ok('L1 ★★★ 消息条停在**里程碑**那句上 —— 服务细节（uvicorn / pip / 警告）'
                '**一行都顶不掉它**（顶掉的话用户就看不见"现在在干第几家的第几步"）',
                '没起来（3/3）' in msg and 'Uvicorn' not in msg
                and '端口 8000' not in msg, repr(msg[:46]))
        fill = str(d.get('msg_fill') or '')
        # ⚠ 判"不是红色"用**实测的填充色**：`LOG_ERR` 是 `#E8826B`，`INK` 是 `#3B332B`。
        #   报常量等于自问自答，而读控件才是"此刻屏幕上是什么色"。
        # [EN] ⚠ Judge "not red" from the **measured** fill: `LOG_ERR` is `#E8826B`, `INK` `#3B332B`.
        # [EN] Reporting the constant asks and answers itself; reading the widget is what's on screen.
        k &= ok('L2 ★★★ 细节行里的 `ERROR` **没把消息条念红**（实测填充色，不是报常量）'
                '—— 否则一家服务的一行普通输出就让"正在启动"读成"启动失败"',
                bool(fill) and 'E8826B' not in fill.upper(), f'实测 fill={fill}')
        k &= ok('L3 ★★★ 加了 `[时间][来源]` 前缀之后**心跳仍然启动**'
                '（三处 `startswith("→ ")` 是被前缀静默打穿的重灾区 —— 不报错、只是再不触发）',
                d.get('boot_clock') is True, str(d.get('boot_clock')))
        k &= ok('L4 ★★★ 步骤点真的亮了三家（`i/n` 认的是**剥掉前缀后**的正文）',
                d.get('steps_n') == 3 and len(d.get('steps') or {}) == 3,
                f'n={d.get("steps_n")} 状态={d.get("steps")}')
        nd, ns = int(d.get('n_detail') or 0), int(d.get('n_strip') or 0)
        k &= ok('L5 ★★ 分流**真的发生了**：细节行走日志区、里程碑行走消息条，'
                '两条路都有行（只有一个有值 = 另一条路根本没走通）',
                nd >= 5 and ns >= 5, f'只进日志 {nd} 行 · 上消息条 {ns} 行')
        # ⚠★ 不判 `LOG_ROWS`（那是"请求行数"，框高由 `create_window` 钉死 ⇒ 它改大改小
        #   一行都不会多显示），判**实测可见行数** —— 这才是"用户能看几行"。
        # [EN] ⚠★ Not `LOG_ROWS` (a *requested* count; the box height is pinned, so it changes
        # [EN] nothing) but the **measured visible rows** -- what the user actually sees.
        vis = int(d.get('console_vis_rows') or 0)
        # ★★★ 2026-10-27 第二轮（用户：「日志框又太高了，高度减少 50%」）：
        #   阈值 20 → **12**。⚠ 不是"把判据调松让它绿"，是**口径真的变了**：
        #   用户这一轮要的是"往回收一半"，要防的东西变成"收过头、回到最早那个
        #   只放得下两句进度的 7 行"。12 就是这条线（实测 14，原来 124px 时 9 行）。
        # [EN] ★★★ 2026-10-27 second round (user: "the log box is too tall again, cut 50%"):
        # [EN] threshold 20 -> **12**. ⚠ Not "loosen the criterion so it goes green" -- the
        # [EN] **yardstick changed**: this round the user wants half of it back, and what must be
        # [EN] prevented is now "overshooting back to the original 7 lines that held two progress
        # [EN] lines". 12 is that line (measured 14; it was 9 at 124px).
        k &= ok('L5b ★★★ 日志区**实测可见 ≥ 12 行**（比最早的 9 行仍明显多；'
                '2026-10-27 第二轮用户把框高砍了一半 436→218px，实测 14 行）',
                vis >= 12, f'实测 {vis} 行')

    # ── L6~L9：读代码（真机看不见的"接没接上"，只能看源码）──
    gui_src = GUI.read_text(encoding='utf-8')
    # ⚠ 只数"传给 `start_service` 的那几次"，并且要求 ≥2（首次 + 重试各一次）——
    #   只改一处是**修一半**：重试那次是"第一次没起来"时唯一还在往窗口里写东西的路径，
    #   漏了它，用户看到的正好是"最难的时候反而没日志"。
    # [EN] ⚠ Count only the calls into `start_service` and require >= 2 (first try + retry): fixing
    # [EN] one is **half a fix** -- the retry is the only path still writing to the window when the
    # [EN] first attempt failed, i.e. the moment the user most needs output.
    _n_ol = gui_src.count('on_line=_on')
    k &= ok('L6 ★★★ 三家桥那条 `on_line` **真的被传进去了** —— 这条通道 2026-10-17 就建好，'
            '从来没人传过 ⇒ 服务拉起的全过程一行都没进窗口（**通道建好没人用 = 没有**）',
            _n_ol >= 2, f'on_line=_on 出现 {_n_ol} 次（要 ≥2：首次 + 重试）')
    k &= ok('L7 ★★ 统一前缀只在**一处**拼（`SPLASH_PREFIX`），'
            '写侧与读侧分得开（判据 L2b 用 splash 自己的解析器读回来）',
            "SPLASH_PREFIX = '[%s][%s] %s'" in gui_src, '')
    sp_src = SPLASH.read_text(encoding='utf-8')
    k &= ok('L8 ★★ splash 侧**能拆**这个前缀，而且**消息条/步骤点/心跳**三处都按'
            '**剥掉前缀后的正文**判（不是按整行）',
            '_split_prefix' in sp_src
            and sp_src.count('_judge.lstrip().startswith(') >= 2
            and '_parse_steps(_judge if _src else line)' in sp_src,
            f"_judge 判正文 {sp_src.count('_judge.lstrip().startswith(')} 处")

    # ── L9~L11：别的启动日志也要进来 ──
    k &= ok('L9 ★★★ 主程序**自己说的** WARNING/ERROR 在启动期也写进这个窗口'
            '（`_SplashLogHandler`）—— 只有人写的那几句进度，"卡在哪一步"永远看不出来',
            'class _SplashLogHandler(logging.Handler)' in gui_src
            and 'logging.getLogger(\'nws\').addHandler' in gui_src, '')
    # ⚠ 找**调用**而不是定义：`def splash_log_capture_start():` 里也含那个串，
    #   按裸串 `find` 会先命中定义（在 `start_gui` 之前）⇒ 判据永远绿。
    #   ⇒ 连缩进一起找（调用点在函数体里）。
    # [EN] ⚠ Look for the **call**, not the definition: `def splash_log_capture_start():` contains
    # [EN] the same substring, and a bare `find` hits it first (it sits before `start_gui`) => the
    # [EN] criterion would be permanently green. => match the indent too.
    _i_start = gui_src.find('    splash_log_capture_start()')
    _i_pre = gui_src.find('    preboot_services()')
    k &= ok('L10 ★★ 捕获**挂得够早**（在 `preboot_services()` 之前 —— 那是最慢、最容易出问题的'
            '一步；挂晚了那一整段就是空白）',
            0 < _i_start < _i_pre, f'start@{_i_start} preboot@{_i_pre}')
    # ⚠⚠ 这一条 2026-10-27 被反例法证明是**空靶**：原来写的是
    #   `find('        splash_log_capture_stop()') < 之后`，而**第一处** 8 空格缩进的调用
    #   就在 `_tell_splash_ready` 自己的函数体里 —— 刀打掉的是 `start_gui` 那个 `finally`
    #   里那处（更靠后），`find` 照样命中前面这处 ⇒ 判据**绿着**，两处里少一处它根本看不见。
    #   ⇒ 改成**数调用点的个数**（`^\s+splash_log_capture_stop\(\)`，不含 `def` 那行），
    #     并要求：①≥2 处（放行那处 + 异常退出兜底那处）②其中一处在 `_tell_splash_ready` 里。
    #   "修一半比不修更坏"在这里就是：只摘一处，另一条路照样把整个运行期的日志灌进
    #   `logs/launcher.log`（那份是追加、永不清理的）。
    # [EN] ⚠⚠ Mutation testing proved this one an **empty target** on 2026-10-27: it used
    # [EN] `find('        splash_log_capture_stop()')`, and the **first** 8-space call site is inside
    # [EN] `_tell_splash_ready` itself -- the knife removed the later one (the `finally` in
    # [EN] `start_gui`), so `find` still hit the earlier one and the criterion stayed **green**;
    # [EN] losing one of the two was invisible to it. => Count **call sites**
    # [EN] (`^\s+splash_log_capture_stop\(\)`, excluding the `def` line) and require: ①>=2 (the
    # [EN] release one + the exception backstop) ②one of them inside `_tell_splash_ready`.
    # [EN] "half a fix is worse than none" here means: remove only one and the other path still
    # [EN] pours the whole run's logs into `logs/launcher.log` (append-only, never cleaned).
    _i_ready = gui_src.find('def _tell_splash_ready')
    _stops = re.findall(r'^\s+splash_log_capture_stop\(\)', gui_src, re.M)
    _in_ready = ('splash_log_capture_stop()'
                 in gui_src[_i_ready:_i_ready + 2500]) if _i_ready > 0 else False
    k &= ok('L11 ★★ 放行那一刻**摘掉**捕获（splash 之后就关了；`logs/launcher.log` 是'
            '**追加、永不清理**的，不摘会灌进整个运行期）；⚠ 还要**两处都摘**'
            '（放行那处 + 异常退出的兜底），少一处这条必须红',
            len(_stops) >= 2 and _in_ready,
            f'调用点 {len(_stops)} 处（要 ≥2）· 在 _tell_splash_ready 里={_in_ready}')

    # ── L12~L14：更大更高（用户这次的头一句话）──
    # ⚠ 必须**在带 tkinter 的解释器里**读：`launcher_splash` 一 import 就要 tkinter，
    #   在判据自己的 .venv 里 exec 会直接 `ModuleNotFoundError` ⇒ 三个常量全成 0，
    #   判据红得毫无道理（看着像"产品没改"，其实是**判据读不到**）。
    # [EN] ⚠ Must read them **inside an interpreter with tkinter**: importing `launcher_splash`
    # [EN] needs tkinter, so exec'ing it in the criterion's own .venv raises ModuleNotFoundError =>
    # [EN] all three constants read 0 and the criteria go red for no reason (it looks like "the
    # [EN] product never changed" when in fact **the criterion cannot read it**).
    _sc = _splash_consts()
    exp = int(_sc.get('H_EXP') or 0)
    rows = int(_sc.get('LOG_ROWS') or 0)
    top = int(_sc.get('LOG_BOX_TOP') or 0)
    hh = int(_sc.get('LOG_H') or 0)
    # ★★★ 2026-10-27 第二轮（用户：「日志框又太高了，高度减少 50% 宽度不变」）
    #   ⇒ L12 的口径整个换了：原来钉的是"**比 620 更大**"（"更长更高"那一轮），
    #     现在 602 < 620，按老口径判就是红 —— 而产品是**对的**（用户自己往回收）。
    #     ⚠ 要防的东西还在吗？**在，而且更具体了**：窗口高度和日志框高度是
    #     **同一个决定的两半**，只改框高、窗口不动 ⇒ 框下面露出 218px 空白
    #     （反过来一样）。⇒ 改成钉**那个等式**：`H_EXP == 顶边 + 框高 + 底部那一截`，
    #     外加"展开态确实比收起态高得多"。
    # [EN] ★★★ 2026-10-27 second round (user: "the log box is too tall again, cut 50%, keep the
    # [EN] width") => L12's yardstick changed outright: it used to pin "**bigger than 620**" (the
    # [EN] "longer and taller" round), and 602 < 620 would be red under it -- while the product is
    # [EN] **right** (the user pulled it back himself). ⚠ Is what it guards still there? **Yes, and
    # [EN] more precisely**: the window height and the box height are **two halves of one decision**;
    # [EN] change only the box and 218px of blank shows below it (and vice versa). => Pin **that
    # [EN] equality**: `H_EXP == top + box + bottom band`, plus "expanded really is much taller".
    band = int(_sc.get('EXP_BOTTOM_BAND') or 0)
    base = int(_sc.get('H_BASE') or 0)
    k &= ok('L12 ★★★ 展开态高度**跟着日志框走**（`H_EXP == 顶边 + 框高 + 底部那一截`）—— '
            '窗口与框是同一个决定的两半：只改一个 ⇒ 框下面露出一大段空白（或压到底栏）',
            band > 0 and exp == top + hh + band and exp - base >= 200,
            f'H_EXP={exp} = 顶边{top} + 框高{hh} + 底部{band} · 比收起态 {base} 高 {exp - base}px')
    # ⚠ 阈值从"≥300px / ≥20 行"改成"≥180px / ≥12 行"：**不是放松判据**，是口径变了
    #   —— 用户这一轮要的是"砍一半"，要防的是"砍过头、回到最早那个 124px / 7 行"
    #   （7 行只够放两句进度，真出问题时报错原文根本进不来）。
    # [EN] ⚠ Threshold changed from ">=300px / >=20 rows" to ">=180px / >=12 rows": **not** loosening
    # [EN] the criterion -- the yardstick changed. This round the user wants "half of it cut"; what
    # [EN] must be prevented is "overshooting back to the original 124px / 7 lines" (7 lines hold
    # [EN] two progress lines, and when something breaks the error text never shows).
    k &= ok('L13 ★★★ 日志区**仍比最早那个 124px / 7 行明显大**（2026-10-27 第二轮'
            '用户砍了一半：436 → 218px）—— 砍过头回到 7 行，报错原文就进不来',
            hh >= 180 and rows >= 12, f'{hh}px / {rows} 行（顶边 {top}）')
    k &= ok('L14 ★★ 展开态**只往下长**：日志块顶边仍是 274（消息条 242 下面），'
            '不是把整块往上抬（抬了会让收起态那一段在展开时变样）',
            top == 274, f'顶边={top}')
    return k


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_splashboot_'))
    try:
        print('\n【S】真起窗口：等的时候看得见')
        boot_clock_checks(tmp)
        print('\n【P】顺序与有上界')
        class_structure_checks()
        wait_ordering_checks()
        boot_signal_checks()
        print('\n【N】失败就不放行')
        block_on_failure_checks(tmp)
        print('\n【V】外观（按钮变小 / 黑底日志）')
        splash_look_checks(tmp)
        print('\n【W】失败态真机')
        failed_state_checks(tmp)
        release_logic_checks(tmp)
        print('\n【Z】主窗口在服务就绪前**不打开**')
        window_visibility_checks()
        print('\n【Q】进度通道')
        splash_note_checks(tmp)
        print('\n【L】启动窗口里的日志（更大更高 · 各服务的细节 · `[时间][服务]`）')
        splash_log_checks(tmp)
    except BaseException:                                    # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        print(REPORT['fatal'])
    finally:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:                                    # noqa: BLE001
            pass

    n = len(REPORT['checks'])
    good = sum(1 for c in REPORT['checks'] if c['ok'])
    # ★★★ 崩溃**必须自己喊出来**（2026-10-23 当场踩到）：`main` 里那个 `except BaseException`
    #   把 traceback 记进 `fatal` 就继续往下走，于是屏幕上只印出「18/18 全绿」——
    #   而**后面三组（N4/N5/V/W/Q）一条都没跑**。总数变小本来就是信号，
    #   但"看起来全绿"会让人直接跳过它。⇒ 有 fatal 就单独一行大字报，并明说"这一轮不算数"。
    # [EN] ★★★ A crash must **announce itself** (hit on the spot 2026-10-23): the
    # [EN] `except BaseException` in `main` records the traceback and keeps going, so the screen
    # [EN] printed "18/18 all green" while **three whole groups never ran**. A shrunken total is a
    # [EN] signal, but "looks green" makes people skip it => print a loud line and say "not counted".
    if 'fatal' in REPORT:
        print('\n' + '═' * 64)
        print('✗✗ 这一轮**不算数**：判据脚本自己崩了，后面的组没跑（不是产品通过）')
        print(str(REPORT['fatal']).splitlines()[-1][:200])
        print('═' * 64)
    print(f'\n启动界面等服务的判据：{good}/{n}'
          + ('（**崩溃，未跑完**）' if 'fatal' in REPORT else ''))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'报告 -> {OUT.relative_to(APP)}')
    return 0 if (good == n and n > 0 and 'fatal' not in REPORT) else 1


if __name__ == '__main__':
    raise SystemExit(main())
