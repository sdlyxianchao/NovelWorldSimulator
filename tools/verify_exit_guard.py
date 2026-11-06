# -*- coding: utf-8 -*-
"""判据：**关窗之后进程必须真的退出**（用户报的"控制台窗口关不掉"）。

来历（2026-10-10 用户原话）
---------------------------
「我退出程序之后 **总是有一个控制台窗口在而且不退出** 你看下怎么回事」。

查出来的机制（**不是猜的，B 组会当场把它跑出来**）：

  `asyncio.to_thread(...)` 走的是**默认线程池** `ThreadPoolExecutor`，
  它的工作线程是**非守护**的，而且解释器退出时会 `join` 它们
  （`concurrent.futures.thread._python_exit`）。
  ⇒ 只要有一个后台调用还没回来，`python.exe` 就**一直不退出**。

  用户看到的现象就不是"程序没关"，而是**那个命令行窗口留着** ——
  因为旧 `start.bat` 里 `"%VENV_PY%" "%APP%"` 那句**还没返回**，cmd 只能等。
  （2026-10-10 起启动器是无控制台的 `start.exe`，没有 cmd 可等了 ——
   但"后台线程没回来 ⇒ 进程不退出"这件事本身还在，所以这条判据照旧要守。）

  本程序里最典型的一个卡点：「自动拉起创作服务」那次
  `BR.start_service(timeout=600)`（`_maybe_autostart_service`）：
  首次启动要下约 470MB 的 embedding 模型；端口被占时更是一直等到超时。
  **十分钟**里用户以为程序关不掉。

修法：`util.flet_shutdown.arm_exit_watchdog()` —— 关窗那一刻起一个
**daemon 线程**，睡 `EXIT_GRACE_SECONDS` 秒后 `os._exit(0)`。
正常收尾几毫秒就走完，看门狗跟着进程消失；卡住时它就是最后那道闸。

覆盖
----
  A. 看门狗本体 —— 真的会触发、**是 daemon**、`delay` 真的被尊重
  B. 机制实测（**在子进程里真跑**）—— 有未完成的 to_thread ⇒ 不退；
     没有 ⇒ 秒退；**上了闸 ⇒ 到点必退**（三组对照，缺一组都说明不了问题）
  C. 接线 —— 两条退出路径都上了闸，且 `import` 到了；MCP 子进程不带黑窗
  D. 扫描器自检 —— 这一支大量用"在某个块里找"，必须证明它不是恒真

跑法：`.venv/Scripts/python.exe tools/verify_exit_guard.py`
报告：`assets/screenshots/exit_guard_report.json`

English:
Criterion: **after closing the window the process must really exit** (the user-reported "console
window won't close").
Origin (2026-10-10, user's exact words)
---------------------------
"After I exit the program **there is always a console window there and it won't exit** take a
look at what's going on".
The mechanism found (**not a guess, group B runs it live on the spot**):
  `asyncio.to_thread(...)` goes through the **default thread pool** `ThreadPoolExecutor`,
  its worker threads are **non-daemon**, and the interpreter `join`s them on exit
  (`concurrent.futures.thread._python_exit`).
  => as long as one background call hasn't returned, `python.exe` **never exits**.
  What the user sees is not "the program didn't close" but **that command-line window staying there** --
  because in the old `start.bat` the line `"%VENV_PY%" "%APP%"` **hadn't returned yet**, so cmd could only wait.
  (since 2026-10-10 the launcher is the console-less `start.exe`, there's no cmd left to wait --
   but "a background thread hasn't returned => the process won't exit" itself is still there, so this criterion must still be upheld.)
  The most typical stall point in this program: that "auto-start the creation service" instance
  `BR.start_service(timeout=600)` (`_maybe_autostart_service`):
  the first start has to download about a 470MB embedding model; and when the port is taken it waits until timeout.
  For **ten minutes** the user thought the program couldn't be closed.
Fix: `util.flet_shutdown.arm_exit_watchdog()` -- at the moment the window closes, start a
**daemon thread**, which sleeps `EXIT_GRACE_SECONDS` seconds then calls `os._exit(0)`.
Normal teardown finishes in a few milliseconds, the watchdog disappears with the process; when
stalled, it's the final gate.
Coverage
----
  A. The watchdog itself -- really fires, **is a daemon**, `delay` really respected
  B. Mechanism measured live (**really run in a subprocess**) -- with an unfinished to_thread => won't exit;
     without => exits instantly; **with the gate engaged => exits at deadline** (three control groups; missing one group proves nothing)
  C. Wiring -- both exit paths have the gate engaged, and `import` reaches them; MCP subprocess carries no black window
  D. Scanner self-check -- this branch heavily uses "find inside some block", so it must be proven not to be vacuously true
How to run: `.venv/Scripts/python.exe tools/verify_exit_guard.py`
Report: `assets/screenshots/exit_guard_report.json`
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

PY = Path(sys.executable)
REPORT: dict = {'checks': [], 'notes': []}
GUI = APP / 'gui' / 'app_flet.py'


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def between(text: str, start: str, end: str = '') -> str:
    """取 `start` 之后到 `end` 之前的那一段（**用来把断言钉在一个块里**）。
        English:
    Take the segment from after `start` to before `end` (**used to pin assertions inside a single
    block**).
    """
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def code_only(block: str) -> str:
    """把整行注释剥掉再找 —— 否则"某个写法出现过"会被注释里的说明骗过。

    这是本项目反复踩过的一条（2026-10-10 一轮里栽了三次）。
    
        English:
    Strip the whole-line comments first, then search -- otherwise "some pattern appeared" gets
    fooled by the explanations in comments.
        This is one thing this project has tripped on repeatedly (fell for it three times in the 2026-10-10 round).
    """
    return '\n'.join(ln for ln in block.splitlines()
                     if not ln.strip().startswith('#'))


def run_child(code: str, wait: float) -> tuple[bool, float]:
    """跑一段子进程代码，看它在 `wait` 秒内退没退。

    返回 `(还活着?, 实际等了多久)`。**还活着就杀掉**（否则判据自己会漏进程）。
    
        English:
    Run a piece of subprocess code, see whether it exited within `wait` seconds.
        Returns `(still alive?, how long it actually waited)`. **If still alive, kill it** (otherwise the criterion itself leaks processes).
    """
    p = subprocess.Popen([str(PY), '-c', code], cwd=str(APP),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < wait and p.poll() is None:
        time.sleep(0.1)
    el = time.time() - t0
    alive = p.poll() is None
    if alive:
        p.kill()
        try:
            p.wait(timeout=5)
        except Exception:                                       # noqa: BLE001
            pass
    return alive, el


# ══════════════════════════════════════════════════════════════
#  A. 看门狗本体
# [EN] A. The watchdog itself
# ══════════════════════════════════════════════════════════════
def test_watchdog() -> None:
    from util.flet_shutdown import EXIT_GRACE_SECONDS, arm_exit_watchdog

    # A1 真的会触发（用**假的 exit_fn**，绝不杀测试进程自己）
    # [EN] A1 It really fires (using a **fake exit_fn**, never kill the test process itself)
    got: list = []
    t = arm_exit_watchdog(0.05, exit_fn=lambda code: got.append(code))
    time.sleep(0.5)
    ok('A1 ★★★ `arm_exit_watchdog` 到点**真的会调 `exit_fn`**（否则它就是一块'
       '写着"能保命"的装饰牌）',
       got == [0], f'exit_fn 收到 {got}')

    # A2 必须是 daemon —— 否则看门狗自己就成了新的"拖住退出的非守护线程"
    # [EN] A2 It must be a daemon -- otherwise the watchdog itself becomes a new "non-daemon thread that
    # [EN] holds up exit"
    ok('A2 ★★★ 看门狗线程是 **daemon** —— 不然它自己就是那个"关不掉的东西"，'
       '（为了修 bug 又加一个同类 bug，本项目栽过）',
       bool(getattr(t, 'daemon', False)), f'daemon={getattr(t, "daemon", None)}')

    # A3 delay 真的被尊重：给长的，短时间内不许触发
    #    （反例：把 `max(0.1, float(delay))` 写成 0，长 delay 也会立刻开火）
    # [EN] A3 delay is really respected: give it a long one, it must not fire within a short time
    # [EN] (Counterexample: write `max(0.1, float(delay))` as 0, and even a long delay fires immediately)
    got2: list = []
    arm_exit_watchdog(0.8, exit_fn=lambda code: got2.append(code))
    time.sleep(0.25)
    ok('A3 ★★ `delay` 真的被尊重：给 0.8 秒时，0.25 秒内**不许**开火'
       '（写死成 0 的话，用户勾了"别急着杀"也照样秒杀）',
       got2 == [], f'0.25 秒时已收到 {got2}')
    time.sleep(0.9)
    ok('A3b ★ 而且到了 0.8 秒它确实开了火（否则 A3 只是"它从来不工作"）',
       got2 == [0], f'{got2}')

    # A4 宽限期是个像样的正数
    # [EN] A4 The grace period is a decent positive number
    ok('A4 ★ 宽限期是**合理正数**（0 < 值 ≤ 30）—— 太小会打断正当收尾，'
       '太大等于没有这道闸',
       0 < float(EXIT_GRACE_SECONDS) <= 30, f'{EXIT_GRACE_SECONDS}')


# ══════════════════════════════════════════════════════════════
#  B. 机制实测（三组对照）
# [EN] B. Mechanism measured live (three control groups)
# ══════════════════════════════════════════════════════════════
#: 有未完成的 `to_thread` 调用 —— 复现"解释器不退"。
# [EN] : has an unfinished `to_thread` call -- reproduce "interpreter won't exit".
_BLOCKED = (
    'import asyncio, time\n'
    'async def main():\n'
    '    asyncio.get_running_loop().run_in_executor(None, time.sleep, 8)\n'
    'asyncio.run(main())\n'
)
#: 对照组：结构一样，只是**没有**那个没回来的调用。
# [EN] : control group: same structure, just **without** that call that never returns.
_FREE = (
    'import asyncio\n'
    'async def main():\n'
    '    await asyncio.sleep(0)\n'
    'asyncio.run(main())\n'
)


def test_mechanism() -> None:
    wait = 3.0
    # B1 对照组：没有未完成的调用 → **秒退**
    # [EN] B1 Control group: no unfinished call -> **exits instantly**
    alive, el = run_child(_FREE, wait)
    ok(f'B1 ★★ 对照：没有未完成的 `to_thread` 调用时，子进程**秒退**'
       f'（{el:.1f}s）—— 这一条是下面两条的基准，缺了它"卡住"就说明不了问题',
       not alive, f'{el:.1f}s 后 {"仍在跑" if alive else "已退出"}')

    # B2 复现：有未完成的调用 → **不退**
    # [EN] B2 Reproduction: has an unfinished call -> **won't exit**
    alive2, el2 = run_child(_BLOCKED, wait)
    ok('B2 ★★★ 复现用户报的现象：有一个 `to_thread` 调用还没回来时，'
       '`python.exe` **在 3 秒内不退出**（这就是"控制台窗口留着"的机制）',
       alive2, f'{el2:.1f}s 后 {"仍在跑" if alive2 else "已退出"}')

    # B3 上了闸 → 到点必退（同一段"会卡住"的代码 + 看门狗）
    # [EN] B3 With the gate engaged -> exits at deadline (same "would-hang" code + watchdog)
    armed = (
        'import asyncio, time, sys\n'
        'sys.path.insert(0, r"' + str(APP).replace('\\', '\\\\') + '")\n'
        'from util.flet_shutdown import arm_exit_watchdog\n'
        'async def main():\n'
        '    asyncio.get_running_loop().run_in_executor(None, time.sleep, 30)\n'
        '    arm_exit_watchdog(0.6)\n'
        'asyncio.run(main())\n'
    )
    alive3, el3 = run_child(armed, wait)
    ok('B3 ★★★ **上了闸之后，同一段会卡住的代码到点就退了**'
       '（0.6 秒宽限 + 3 秒观察窗内必须已经退出）—— 这条才是"修好了"的证据',
       not alive3 and el3 <= wait,
       f'{el3:.1f}s 后 {"仍在跑" if alive3 else "已退出"}')


# ══════════════════════════════════════════════════════════════
#  C. 接线
# [EN] C. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> None:
    src = read('gui/app_flet.py')

    ok('C1 ★★ `arm_exit_watchdog` **被 import 进来**（没 import 的调用会'
       '当场 NameError，而且只在关窗那一刻才炸 —— 最难查的一种）',
       'from util.flet_shutdown import arm_exit_watchdog' in src, '')

    # ⚠ 一律在**块里**查（"整个文件里出现过"这种写法会被注释与别处骗过）
    # [EN] ⚠ Always check **inside the block** (the "appeared anywhere in the whole file" style gets fooled
    # [EN] by comments and elsewhere)
    disc = code_only(between(src, 'def on_disconnect(e=None):',
                             'page.on_disconnect = on_disconnect'))
    ok('C2 ★★★ **点窗口 ×**（`on_disconnect`）这条路上上了闸 —— 在'
       '`on_disconnect` 那个块里查，且剥掉注释',
       'arm_exit_watchdog(' in disc, disc[-160:].replace('\n', ' '))

    ex = code_only(between(src, 'async def _on_exit(self, e):',
                           'def _refresh_view(self'))
    ok('C3 ★★★ **菜单里的「归去」**（`_on_exit`）这条路上也上了闸',
       'arm_exit_watchdog(' in ex, ex[:160].replace('\n', ' '))
    ok('C3b ★★ 顺序对：**先上闸、再 `window.destroy()`** —— 反过来的话，'
       '`destroy()` 抛的 `CancelledError`（是 `BaseException`）会把后面'
       '那句吃掉，闸就永远上不了',
       ('arm_exit_watchdog(' in ex and 'await self.page.window.destroy()' in ex
        and ex.find('arm_exit_watchdog(') < ex.find('await self.page.window.destroy()')),
       f'闸在 {ex.find("arm_exit_watchdog(")}，destroy 在 '
       f'{ex.find("await self.page.window.destroy()")}')
    ok('C3c ★ 落盘也在 `destroy()` **前面**（先落盘、再上闸、最后关窗 —— '
       '反过来就成了"先杀进程、后落盘"，当天演的东西白跑）',
       'self._stop_autosave()' in ex
       and ex.find('self._stop_autosave()') < ex.find('await self.page.window.destroy()'),
       '')

    # MCP 子进程不许开黑窗
    # [EN] MCP subprocess must not open a black window
    mcp = read('mcp/client.py')
    # ⚠ 判**代码里那一行**，不判"文件里出现过 CREATE_NO_WINDOW 这几个字" ——
    #   上面那段注释里就写着这几个字，第一版就是这么被它骗过去的
    #   （变异把赋值删掉，判据照样绿）。所以先剥注释再找那个十六进制值。
    # [EN] ⚠ Judge **that line in the code**, not "the words CREATE_NO_WINDOW appeared in the file" --
    # [EN] those very words are written in the comment section above; the first version was fooled by it
    # [EN] exactly this way
    # [EN] (a mutation deletes the assignment, and the criterion still passes green). So strip comments
    # [EN] first, then look for that hex value.
    ok('C4 ★★★ MCP 服务器子进程的创建标志里带了 `CREATE_NO_WINDOW`'
       '（`0x08000000`）—— 宿主没有控制台时（`pythonw` / 快捷方式），'
       'Windows 会给每个控制台子进程**新分配一个控制台**，于是每拉起一个 '
       'MCP 就多一个黑窗。判的是**代码里那一行**，不是注释里那几个字',
       '0x08000000' in code_only(mcp), '')
    ok('C4b ★ 而且是真的**传给了** `create_subprocess_exec`（常量写了不传，'
       '等于没写）—— 从调用起点往后取一段查 `**_kw`，不钉字面量排版',
       (lambda i: i >= 0 and '**_kw' in mcp[i:i + 400])(
           mcp.find('self.proc = await asyncio.create_subprocess_exec(')),
       '')


# ══════════════════════════════════════════════════════════════
#  D. 扫描器自检
# [EN] D. Scanner self-check
# ══════════════════════════════════════════════════════════════
def test_scanner() -> None:
    src = read('gui/app_flet.py')
    ok('D1 ★★ 扫描器自检：用一个**根本不存在的名字**去块里找，必须找不到'
       '（找得到就说明 `between()` 取错了范围，"在里面找"这件事全是假绿）',
       'arm_exit_watchdog(' not in code_only(
           between(src, 'def on_disconnect(e=None):', 'page.on_disconnect = '
                   'on_disconnect')).replace('arm_exit_watchdog(', ''), '')
    ok('D1b ★★ 而且那个块**确实取到了**（空字符串会让上面一条恒真）',
       len(between(src, 'def on_disconnect(e=None):',
                   'page.on_disconnect = on_disconnect')) > 50,
       f'{len(between(src, "def on_disconnect(e=None):", "page.on_disconnect = on_disconnect"))} 字符')


def main() -> int:
    for name, fn in (('看门狗本体', test_watchdog), ('机制实测', test_mechanism),
                     ('接线', test_wiring), ('扫描器自检', test_scanner)):
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    out = APP / 'assets' / 'screenshots' / 'exit_guard_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n退出看门狗验证：{n - len(bad)}/{n}')
    for c in REPORT['checks']:
        print(f'  {"✓" if c["ok"] else "✗"} {c["name"]}'
              + (f' | {c["detail"][:120]}' if c['detail'] else ''))
    print('报告 ->', out.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
