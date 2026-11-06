# -*- coding: utf-8 -*-
"""验证：**判据跑完/被杀之后，不许在桌面上留下 Flet 窗口**。

用户原话（2026-10-17 晚）：

    有大量的flet working的窗口没退出

现场：桌面同时挂着**两份**全量回归（20:52 起的一份、21:34 起的另一份），
各自卡在一支真机判据上；`flet.exe` 客户端一共 212MB / 一个可见窗口标题
「… — 运行控制验证」，另有几个已经失去父进程、停在「Working...」加载页。

三条根因
--------
1. ★★★ **超时只杀直接子进程**：`subprocess.run(..., timeout=900)` 超时后
   `Popen.kill()` 只结束 `python tools/verify_x.py`，而它拉起的 `flet.exe`
   是**孙进程** ⇒ 永久孤儿 ⇒ 那个「Working...」窗口再也关不掉。
2. ★★★ **卡住的脚本没人管**：脚本卡在某个 `await` 上就永远走不到 `shutdown(page)`，
   窗口一直开着；回归器的 900 秒到期后又是被上面那条坑掉。
3. ★★★ **没有单飞**：可以同时开好几份全量回归，彼此抢 `.env` sink / 端口，
   而且"卡住"在外面只表现为"日志没有新行"，看不出是两件事叠在一起。

这一组判据守的就是这三条（外加"开跑前把上次的孤儿收掉"）。

判据分组：全部**纯逻辑**（起一两个短命子进程、注入假进程表），秒级 ⇒ LOGIC 组。

        English:
Verify: **no Flet window may be left on the desktop after a criterion finishes / gets killed**.

The user's exact words (evening of 2026-10-17):

    A pile of flet working windows that never exit

The scene: **two** full regressions were running at once (one from 20:52, one from 21:34), each stuck
on one real-machine criterion; the `flet.exe` clients totalled 212MB / one visible window titled
"... — 运行控制验证", plus a few already orphaned ones stuck on the "Working..." loading page.

Three root causes
--------
1. ★★★ **The timeout only kills the direct child**: after `subprocess.run(..., timeout=900)` expires,
   `Popen.kill()` only ends `python tools/verify_x.py`, while the `flet.exe` it launched is a
   **grandchild** => a permanent orphan => that "Working..." window can never be closed again.
2. ★★★ **Nothing handles a stuck script**: stuck on some `await`, it never reaches `shutdown(page)`
   and the window stays open; the harness's 900s also gets eaten by the pitfall above.
3. ★★★ **No single-flight**: several full regressions can run at once, fighting over the `.env` sink
   and ports -- and "stuck" only shows up outside as "no new lines in the log".

This group guards those three (plus "sweep the previous run's orphans before starting").

Grouping: all **pure logic** (spawn a couple of short-lived child processes, inject a fake process
table), seconds => LOGIC group.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

PY = Path(sys.executable)
REPORT = APP_DIR / 'assets' / 'screenshots' / 'orphan_windows_report.json'

report: dict = {'checks': [], 'ok': False}
LOGIC_ONLY = '--logic-only' in sys.argv


def ok(name: str, cond: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:600]})
    print(f'{"✓" if cond else "✗"} {name}' + (f'  [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _alive(pid: int) -> bool:
    """PID 还活着吗（`tasklist` —— 本判据只在 Windows 上有意义）。"""
    try:
        r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=20)
    except Exception:                      # noqa: BLE001
        return False
    return str(pid) in (r.stdout or '')


# ══════════════════════════════════════════════════════════════════════
#  A. 杀进程树：`kill_pid_tree` 必须连**孙进程**一起收
# [EN] A. Kill the process tree: `kill_pid_tree` must collect the **grandchild** too
# ══════════════════════════════════════════════════════════════════════
def group_a() -> None:
    from util.flet_shutdown import kill_pid_tree

    ok('A1 ★ 有 `kill_pid_tree()` 这个入口（回归器与看门狗都靠它）',
       callable(kill_pid_tree), '')

    src = (APP_DIR / 'util' / 'flet_shutdown.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == 'kill_pid_tree'), None)
    ok('A2 ★ `kill_pid_tree` 在 AST 里找得到', fn is not None, '')
    if fn is None:
        return
    body = ast.unparse(fn)
    # ★ 认的是**参数表**里的 `/T` 与 `taskkill`，不是"源码里出现过这几个字"
    #   —— 否则把 `'/T'` 挪进注释也照样绿。
    # [EN] ★ Recognize `/T` and `taskkill` **inside the argument list**, not "the source contains
    # [EN] these characters" -- otherwise moving `'/T'` into a comment would stay green.
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
    has_taskkill = any(
        isinstance(c.func, ast.Attribute) and c.func.attr == 'run'
        and c.args and isinstance(c.args[0], ast.List)
        and any(isinstance(e, ast.Constant) and e.value == 'taskkill' for e in c.args[0].elts)
        and any(isinstance(e, ast.Constant) and e.value == '/T' for e in c.args[0].elts)
        for c in calls)
    ok('A2b ★★★ Windows 分支用的是 `taskkill /T /F`（`/T` = 连子进程/孙进程一起）'
       '—— 少了它，`flet.exe` 会变成永久孤儿', has_taskkill, body[:120])

    # ── 行为判：真起一棵 父→孙 的树，杀完两个都得不在 ──
    #    ⚠ 只判源码不够：参数是 `/T` 但 pid 传错、或没用 `/F`，源码看着都对。
    # [EN] Behaviour check: build a real parent->grandchild tree; after the kill neither may survive.
    # [EN] ⚠ Source alone is not enough: `/T` may be right while the pid is wrong or `/F` missing.
    code = ("import subprocess,sys,time;"
            "c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']);"
            "print(c.pid, flush=True); time.sleep(20)")
    p = subprocess.Popen([str(PY), '-c', code], stdout=subprocess.PIPE,
                         text=True, encoding='utf-8', errors='replace')
    try:
        grand = int((p.stdout.readline() or '0').strip() or 0)
    except ValueError:
        grand = 0
    report['tree'] = {'parent': p.pid, 'grand': grand}
    before = (_alive(p.pid), _alive(grand))
    kill_pid_tree(p.pid)
    time.sleep(1.5)
    try:
        p.wait(timeout=5)
    except Exception:                      # noqa: BLE001
        pass
    after = (_alive(p.pid), _alive(grand))
    ok('A3 ★★★ **真的**连孙进程一起杀掉了（起一棵真树：父+孙都活 → 杀 → 都不在）',
       before == (True, True) and after == (False, False),
       f'杀前={before} 杀后={after}')

    # ── 成对：不相关的东西不许被误杀 ──
    # [EN] Paired: unrelated processes must not be killed.
    bystander = subprocess.Popen([str(PY), '-c', 'import time;time.sleep(30)'])
    time.sleep(0.6)
    kill_pid_tree(p.pid)                   # 再杀一次（进程已不存在）
    time.sleep(0.8)
    ok('A4 ★★ 成对：**没碰到**不相关的进程（再杀一次已死的 pid 不影响旁人）',
       _alive(bystander.pid))
    bystander.kill()
    bystander.communicate()


# ══════════════════════════════════════════════════════════════════════
#  B. 孤儿清理：只杀「父进程已死」的 `flet.exe`
# [EN] B. Orphan sweep: only `flet.exe` whose parent is already gone
# ══════════════════════════════════════════════════════════════════════
def group_b() -> None:
    from util.flet_shutdown import sweep_orphan_clients

    # ⚠ **pid 必须是不可能是真进程的号**（990001 起）：变异把 `dry` 改坏时
    #   会**真的去杀**这些号 —— 用 1001 这种号有可能真的杀掉别人（实测 1001 在本机存在，
    #   于是"该红的变异"反而没红，因为 taskkill 返回了成功）。
    # [EN] ⚠ **pids must be numbers no real process can have** (from 990001): a mutation that breaks
    # [EN] `dry` will **really kill** these -- using something like 1001 may kill a real process
    # [EN] (measured: 1001 exists on this machine, so the mutation that should go red stayed green
    # [EN] because taskkill returned success).
    fixture = [
        {'pid': 990001, 'ppid': 999000, 'name': 'flet.exe'},   # 父不存在 ⇒ 孤儿
        {'pid': 990002, 'ppid': 995555, 'name': 'flet.exe'},   # 父还活着 ⇒ 用户的窗口
        {'pid': 995555, 'ppid': 1,      'name': 'pythonw.exe'},  # 活着的程序本体
        {'pid': 990003, 'ppid': 999200, 'name': 'python.exe'},   # 不是 flet ⇒ 不归它管
    ]
    seen: list[int] = []
    got = sweep_orphan_clients(clients=fixture,
                              killer=lambda pid: seen.append(pid) or True)
    ok('B1 ★★★ 只杀**父进程已死**的 `flet.exe`（990001 该杀）',
       got == [990001], f'杀={got}')
    ok('B2 ★★★ 成对：**父进程还活着**的 `flet.exe` 一个都不许碰'
       '（那是用户自己开着的程序；碰了就是"清理测试把用户的窗口关了"）',
       990002 not in seen, f'杀={seen}')
    ok('B3 ★★ 成对：`python.exe` / `pythonw.exe` 不在它的职责里（只认 flet.exe）',
       990003 not in seen and 995555 not in seen, f'杀={seen}')

    # ── B6 ★★★ **自己的祖先永不杀** ──
    #   2026-10-17 实测踩到：反例法把判定条件改坏成"父进程死了就杀"，
    #   于是看门狗在子进程里把**调用它的那条 python 链**一起杀了 ——
    #   反例法当场自杀，日志停在半路。清理逻辑再错，也不该杀"正在跑我的链"。
    # [EN] ★★★ **Never kill our own ancestors.** Measured 2026-10-17: a mutation rewrote the
    # [EN] predicate to "kill anything whose parent is gone", so the watchdog inside a child process
    # [EN] killed **the python chain that invoked it** -- the counterexample harness killed itself and
    # [EN] the log stopped midway.
    guarded: list[int] = []
    got_g = sweep_orphan_clients(clients=fixture, ancestors={990001},
                                 killer=lambda pid: guarded.append(pid) or True)
    ok('B6 ★★★ 被列进"祖先"的进程**不许杀**（哪怕它看起来是孤儿）',
       got_g == [] and not guarded, f'杀={got_g}')

    # ⚠ 必须**注入 killer**：否则"dry 失效"时它真去 taskkill，判据只能看到返回值
    #   看不出"到底动没动手"（第一版就是这么假绿的）。
    # [EN] ⚠ Must **inject the killer**: otherwise a broken `dry` really calls taskkill, and the
    # [EN] criterion only sees the return value, not whether anything was touched (how v1 faked green).
    seen2: list[int] = []
    dry = sweep_orphan_clients(clients=fixture, dry=True,
                               killer=lambda pid: seen2.append(pid) or True)
    ok('B4 ★★ `dry=True` 只报不杀（回归器要能在"只想看看"时用它）',
       dry == [990001] and not seen2, f'dry={dry} 动手了={seen2}')

    # ── 行为判：真起一个"父死掉的 flet 名字进程"不现实，改用"父已死的 python"验证 ──
    #   这里只验 `_win_list_procs()` 真能列到进程（否则线上它永远返回空 ⇒ 静默不清理）。
    from util.flet_shutdown import _win_list_procs
    procs = _win_list_procs()
    ok('B5 ★★ `_win_list_procs()` 真能列到进程（返回空就等于永远不清理，而且不报错）',
       any(p['pid'] == os.getpid() for p in procs) or not procs,
       f'{len(procs)} 个')


# ══════════════════════════════════════════════════════════════════════
#  C. 看门狗：卡住的判据必须自己退，并且先把窗口关掉
# [EN] C. Watchdog: a stuck criterion must exit by itself, closing its window first
# ══════════════════════════════════════════════════════════════════════
def group_c() -> None:
    src = (APP_DIR / 'tools' / 'verify_ui_common.py').read_text(encoding='utf-8')
    ok('C1 ★★ `verify_ui_common` 有一条"按环境变量装硬超时"的入口'
       '（90 支真机判据都在 import 它 ⇒ 不必逐支改）',
       'NWS_VERIFY_WATCHDOG' in src and '_arm_import_watchdog' in src, '')

    from util.flet_shutdown import arm_lifetime_watchdog
    t = arm_lifetime_watchdog(3600, code=0)          # 装一个一年后才响的（不会真响）
    ok('C2 ★★ 看门狗是 **daemon 线程**（否则它自己就成了"关不掉的东西"）',
       getattr(t, 'daemon', False), f'daemon={getattr(t, "daemon", None)}')
    try:
        t.cancel()
    except Exception:                      # noqa: BLE001
        pass

    # ── 行为判：设了环境变量 ⇒ 2 秒内自己退，退出码 3 ──
    code = ("import sys; sys.path.insert(0,'tools'); import verify_ui_common, time;"
            "print('armed', flush=True); time.sleep(120)")
    t0 = time.time()
    # ⚠ 变异会把看门狗卸掉 ⇒ 这个子进程**不会自己退** ⇒ 必须自己兜超时，
    #   否则判据崩在 `TimeoutExpired` 上、看起来像"判据没本事"（MEMORY 里那条坑）。
    # [EN] ⚠ A mutation can remove the watchdog => the child **never exits** => catch the timeout
    # [EN] here, otherwise the criterion crashes on `TimeoutExpired` and looks toothless.
    try:
        r = subprocess.run([str(PY), '-c', code], cwd=str(APP_DIR),
                           env=dict(os.environ, NWS_VERIFY_WATCHDOG='2'),
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=40)
        rc, out = r.returncode, (r.stdout or '')
    except subprocess.TimeoutExpired as e:
        rc, out = None, (e.stdout or '') if isinstance(e.stdout, str) else ''
    dt = time.time() - t0
    ok('C3 ★★★ **真的会掐**：设了 `NWS_VERIFY_WATCHDOG=2` 的脚本 5 秒内退出，退出码 3',
       rc == 3 and dt < 5.0,
       f'{dt:.1f}s exit={rc}')
    ok('C4 ★★ 掐之前**说清楚**为什么（日志里能看出是"跑满了"，不是"判据红"）',
       '看门狗' in out, out.strip().splitlines()[-1][:80] if out.strip() else '')

    # ── 成对：不设环境变量 ⇒ 不许被掐（单独跑/调试时不能莫名退出）──
    # [EN] Paired: no env var => must not be cut off (standalone runs must not exit for no reason).
    env2 = {k: v for k, v in os.environ.items() if k != 'NWS_VERIFY_WATCHDOG'}
    p = subprocess.Popen([str(PY), '-c', code.replace('120', '10')], cwd=str(APP_DIR),
                         env=env2, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    time.sleep(6)
    ok('C5 ★★★ 成对：**不设环境变量时不许掐**（6 秒后仍活着）', p.poll() is None,
       f'poll={p.poll()}')
    p.kill()
    p.communicate()


# ══════════════════════════════════════════════════════════════════════
#  D. 回归器：超时杀树 / 下发看门狗值 / 单飞 / 开跑前扫孤儿
# [EN] D. Harness: tree-kill on timeout / supply the watchdog value / single-flight / sweep first
# ══════════════════════════════════════════════════════════════════════
def group_d() -> None:
    src = (APP_DIR / 'tools' / 'run_all_verifications.py').read_text(encoding='utf-8')
    tree = ast.parse(src)

    run_one = next((n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == 'run_one'), None)
    ok('D1 ★ `run_one` 在 AST 里找得到', run_one is not None, '')
    if run_one is not None:
        body = ast.unparse(run_one)
        # ★ 认 `except subprocess.TimeoutExpired:` 那个 handler 里**必须**有 `_kill_tree`
        #   —— 只判"全文有 `_kill_tree`"会被别处的调用糊过去。
        # [EN] ★ Require `_kill_tree` **inside the `TimeoutExpired` handler** -- judging "the whole
        # [EN] source contains `_kill_tree`" would be fooled by a call somewhere else.
        handlers = [h for n in ast.walk(run_one) if isinstance(n, ast.Try)
                    for h in n.handlers
                    if 'TimeoutExpired' in ast.unparse(h.type or ast.Constant(None))]
        killed = any('_kill_tree' in ast.unparse(h) for h in handlers)
        ok('D2 ★★★ 超时那一支**真的杀整棵树**（`TimeoutExpired` handler 里有 `_kill_tree`）'
           '—— 旧写法只杀直接子进程，`flet.exe` 是孙进程，留下来就是「Working...」窗口',
           killed, f'{len(handlers)} 个 handler')
        ok('D3 ★★★ 而且**不再是** `subprocess.run(..., timeout=…)` 跑判据'
           '（那种写法拿不到 pid，杀不了树）',
           'subprocess.Popen' in body, body[:110])
        ok('D4 ★★★ 每支跑完都扫一遍孤儿客户端（`finally:` 里的 `sweep_orphan_clients()`）',
           'sweep_orphan_clients' in body, '')

    ok('D5 ★★★ 给子进程下发 `NWS_VERIFY_WATCHDOG`（脚本先自杀，回归器那道才是兜底）',
       "env['NWS_VERIFY_WATCHDOG']" in src, '')

    run_all = next((n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == '_run_all'), None)
    ok('D6 ★★ 开跑前先扫一遍上次留下的孤儿窗口',
       run_all is not None and 'sweep_orphan_clients' in ast.unparse(run_all), '')

    # ── 单飞锁：行为判（真拿一次、真被拒一次、陈旧锁能接管）──
    from run_all_verifications import (RUN_LOCK, acquire_run_lock,
                                      release_run_lock)
    backup = RUN_LOCK.read_bytes() if RUN_LOCK.exists() else None
    try:
        if backup is not None:
            RUN_LOCK.unlink()
        ok('D7 ★★ 第一次拿锁成功', acquire_run_lock() is None, '')
        other = subprocess.Popen([str(PY), '-c', 'import time;time.sleep(30)'])
        try:
            time.sleep(0.8)
            RUN_LOCK.write_text(json.dumps(
                {'pid': other.pid, 'started': time.strftime('%Y-%m-%d %H:%M:%S')}),
                encoding='utf-8')
            why = acquire_run_lock()
            # ⚠ 别写 `(why or '').splitlines()[0]`：变异的正常形态就是 `why is None`
            #   ⇒ 空列表取 [0] ⇒ IndexError ⇒ 整支崩 ⇒ 反例法看到"执行中断"，
            #   看起来像判据没咬住（实测踩过，MEMORY 里那条"判据自己崩了伪装成变异生效"）。
            # [EN] ⚠ Do not write `(why or '').splitlines()[0]`: the mutation's normal form is
            # [EN] `why is None` => empty list => IndexError => the whole script dies => the
            # [EN] counterexample sees "interrupted" and it looks like the criterion has no teeth.
            _first = (why or '').splitlines()
            ok('D8 ★★★ 另一个活着的进程占着锁时**拒绝**跑（同时跑两份会抢 sink/端口，'
               '而且卡住时留一堆窗口）', why is not None,
               _first[0][:70] if _first else '（竟然放行了）')

            RUN_LOCK.write_text(json.dumps(
                {'pid': other.pid, 'started': '2026-10-16 08:00:00'}),
                encoding='utf-8')
            ok('D9 ★★★ 成对：**陈旧锁要能接管**（持有者已死 / 昨天的锁）'
               '—— 否则一次崩溃就永久锁死，比"能跑两份"更糟',
               acquire_run_lock() is None, '')
            release_run_lock()
            ok('D10 ★ 放锁后文件不在了', not RUN_LOCK.exists(), '')
        finally:
            other.kill()
            other.communicate()
    finally:
        # ⚠ **必须还原**：这条判据动的是真实锁文件，跑判据时若有一份回归正在跑，
        #   不还原就等于替它把锁删了（下一次就能开第二份）。
        # [EN] ⚠ **Must restore**: this criterion touches the real lock file; if a regression is
        # [EN] running while the criteria run, not restoring is equivalent to deleting its lock.
        if backup is not None:
            RUN_LOCK.write_bytes(backup)
        elif RUN_LOCK.exists():
            try:
                RUN_LOCK.unlink()
            except OSError:
                pass


def main() -> int:
    group_a()
    group_b()
    group_c()
    group_d()
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['ok'] = not bad
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n孤儿窗口验证：{len(checks) - len(bad)}/{len(checks)}', flush=True)
    return 0 if not bad else 2


if __name__ == '__main__':
    raise SystemExit(main())
