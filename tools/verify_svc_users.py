# -*- coding: utf-8 -*-
"""验证：多实例共享一组创作服务时的**收尸归属**（2026-10-28）。

背景（这条判据为什么存在）
--------------------------
三座创作服务都**绑固定端口**（端口写在同一份 `.env` 里）⇒ 第二个实例只会收到
一句「已经在运行，不重复启动」⇒ **全程只有一组服务在跑**（实测过：`novelservice.py
start` 在端口上已有健康服务时 0.1 秒返回、不拉第二组）。

于是「主窗口退出 ⇒ 服务跟着退出」这条硬要求（用户 2026-10-10 的原话）在多实例下
必须换成：**最后一个关的人负责收尸**。

⚠ 换掉的那套（`logs/launcher.pid`，比"文件里那个 pid 是不是我"）只防住了
  **先关的**那个，没防住**后关的**那个 —— 而人总是先关掉刚开的那一个、回头继续用
  先前那个 ⇒ 那一次正好把**正在用**的服务掐掉。本判据的 C 组就是钉这件事。

四组
----
  A 登记表的基本行为（真调 `util.svc_users`，用临时目录）
  B 探活的准确性（**不许用 `os.kill(pid,0)`**、**光能把进程打开不算活着**）
  C 关窗口那一刻的收尸决策（真调 `gui.app_flet._stop_services_if_last`）
  S 源码结构 + 两边硬编码的目录串一致（**AST，不用 grep**）

★ 不开窗口、**不真起服务、不真停服务**（三家桥全部打桩）。
★ `--selftest` 把「退出码判活」那道闸拆掉再跑一遍，证明 B4 真的在测它。

    English:
Verification: **who reaps the services** when several instances share one set
(2026-10-28).
Background (why this criterion exists)
--------------------------
All three creation services **bind a fixed port** (written in one shared `.env`)
=> a second instance only gets "already running, not starting again" => **only one
set of services ever runs** (measured: with a healthy service already on the port,
`novelservice.py start` returns in 0.1 s and pulls up no second set).
So the hard requirement "main window exits => services exit with it" (user's words,
2026-10-10) has to become, for multiple instances: **whoever closes last reaps**.
⚠ What it replaces (`logs/launcher.pid`, comparing "is the pid in the file me")
guarded **the one that closes first** but not **the one that closes last** -- and
people close the window they just opened and go back to the earlier one => that is
exactly when the **in-use** service gets cut off. Group C here pins that.
Four groups
----
  A Registry basics (really calls `util.svc_users`, in a temp dir)
  B Liveness accuracy (**never `os.kill(pid,0)`**, **being able to open it isn't alive**)
  C The shutdown decision at window-close (really calls `gui.app_flet._stop_services_if_last`)
  S Source structure + the directory string hard-coded on both sides (**AST, not grep**)
★ No window, **no real service started, none really stopped** (all three bridges
★ are stubbed).
★ `--selftest` removes the "exit code decides aliveness" gate and re-runs, proving
★ B4 really tests it.
"""
from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

OUT = APP / 'assets' / 'screenshots'
SVCPATH = APP / 'util' / 'svc_users.py'
AFPATH = APP / 'gui' / 'app_flet.py'
GOSVC = APP / 'launchers' / 'services.go'

CHECKS: list[dict] = []
FAILED: list[str] = []


def ok(name: str, cond, detail='') -> bool:
    """记一条检查。**红的必须让退出码非 0** —— 回归器只看退出码。

    ⚠ 只把结果记进列表、退出码恒 0 ⇒ 这支判据在回归里**永远绿**
      （"红灯打出来也没人看得见"）。⇒ 红的在这里就登记。
    [EN] A red check **must** make the exit code non-zero -- the harness only looks
    [EN] at the exit code. Recording without that makes this criterion **always
    green** in the regression.
    """
    good = bool(cond)
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    if not good:
        FAILED.append(name)
    print(('  ✓ ' if good else '  ✗ ') + name
          + (f'   [{detail}]' if detail else ''), flush=True)
    return good


def head(title: str) -> None:
    print(f'\n── {title} ──', flush=True)


# ══════════════════════════════════════════════════════════════════
#  A 组：登记表的基本行为
# [EN] Group A: registry basics
# ══════════════════════════════════════════════════════════════════
def test_registry() -> None:
    head('A · 登记表：登记 / 判空 / 僵尸自愈')
    import util.svc_users as SU

    tmp = tempfile.mkdtemp(prefix='nws_svc_users_')
    os.environ['NWS_SVC_USERS_DIR'] = tmp

    ok('A1 ★★ 登记之后表上有我，且"除我之外没人" ⇒ 可以停',
       (SU.claim() is not None and os.getpid() in SU.alive_pids()
        and SU.any_other_alive() is False),
       f'registered={SU.registered_pids()}')

    # 第二个实例：一个**活着**的别的 pid
    other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
    try:
        SU.claim(other.pid)
        ok('A2 ★★★ 还有别的实例活着 ⇒ **不许停**',
           SU.any_other_alive() is True,
           f'others={SU.alive_others()}')

        # ★ 僵尸自愈：第二个实例被强杀（**不 release**），文件还留着
        other.kill()
        other.wait()
        ok('A3 ★★★ 别的实例被强杀（没撤销登记）⇒ 判活过不了 ⇒ **自愈**',
           (other.pid in SU.registered_pids()
            and SU.any_other_alive() is False),
           f'registered={SU.registered_pids()} alive={SU.alive_pids()}')
    finally:
        if other.poll() is None:
            other.kill()
            other.wait()

    ok('A4 ★ 撤销之后表上没有我',
       (SU.release() is True and os.getpid() not in SU.registered_pids()),
       f'registered={SU.registered_pids()}')

    ok('A5 ★ 表上只有死 pid ⇒ 判空（僵尸不算数）',
       SU.any_other_alive() is False)

    ok('A6 ★ clear_dead 清得掉僵尸文件',
       SU.clear_dead() >= 1 and not SU.registered_pids(),
       f'registered={SU.registered_pids()}')


# ══════════════════════════════════════════════════════════════════
#  B 组：探活的准确性（**这条最容易被写错**）
# [EN] Group B: liveness accuracy (the easiest thing to get wrong)
# ══════════════════════════════════════════════════════════════════
def test_liveness() -> None:
    head('B · 探活：不许杀人、杀了要判死')
    import util.svc_users as SU

    ok('B1 ★ 自己活着', SU.pid_alive(os.getpid()) is True)
    ok('B2 ★ 不存在的 pid 判死', SU.pid_alive(999983) is False)
    ok('B3 ★ pid <= 0 一律判死（0 是"没给"，不是"第 0 号进程"）',
       SU.pid_alive(0) is False and SU.pid_alive(-1) is False)

    # ★★ 探活不许把人杀掉 —— Windows 的 `os.kill(pid, 0)` 会变成"以退出码 0 终止"
    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
    try:
        alive = SU.pid_alive(p.pid)
        still = p.poll() is None
        ok('B4 ★★★ **探活不杀人**（Windows 上 `os.kill(pid,0)` 会真的终止进程）',
           alive is True and still is True,
           f'alive={alive} 进程还在={still}')

        p.kill()
        p.wait()
        # ★★ 光能把进程打开**不算活着**（父进程还攥着句柄时 OpenProcess 照样成功）
        ok('B5 ★★★ 进程已死 ⇒ 判死（**不能只看"打不打得开"**）',
           SU.pid_alive(p.pid) is False,
           '杀掉之后仍判活 ⇒ 又退化成"僵尸永远自愈不了"')
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


# ══════════════════════════════════════════════════════════════════
#  C 组：关窗口那一刻的收尸决策
# [EN] Group C: the shutdown decision at window-close
# ══════════════════════════════════════════════════════════════════
class _StubBridge:
    """假的桥：只记"我被叫了"，**绝不真的去停服务**。
    [EN] Fake bridge: only records "I was called", **never** really stops anything."""

    def __init__(self, name: str, sink: list):
        self._name = name
        self._sink = sink

    def stop_service_detached(self) -> bool:
        self._sink.append(self._name)
        return True


class _FakeCfg:
    """只回答 `b()` 的假配置（用来摆布三个 `*_FOLLOW_APP`）。
    [EN] A config stand-in answering only `b()` (to pose the three `*_FOLLOW_APP`)."""

    def __init__(self, mapping: dict):
        self._m = mapping

    def b(self, key: str) -> bool:
        return bool(self._m.get(key, False))


def test_stop_decision() -> None:
    head('C · 关窗口那一刻：谁最后关谁收尸')
    import util.svc_users as SU
    try:
        import gui.app_flet as AF
    except Exception as ex:                                 # noqa: BLE001
        ok('C0 ★ 能 import 主程序模块', False, f'{type(ex).__name__}: {ex}')
        return

    tmp = tempfile.mkdtemp(prefix='nws_svc_users_')
    os.environ['NWS_SVC_USERS_DIR'] = tmp

    called: list[str] = []
    _orig_import = importlib.import_module

    def _fake_import(name, *a, **k):
        if name.startswith('novelservices.'):
            return _StubBridge(name.split('.')[-1], called)
        return _orig_import(name, *a, **k)

    importlib.import_module = _fake_import
    real_cfg = AF.CFG
    try:
        # ── C1 还有别的实例活着 ⇒ 一家都不许停 ──
        SU.claim()
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'])
        SU.claim(other.pid)
        called.clear()
        AF._stop_services_if_last()
        ok('C1 ★★★ 还有别的实例在用 ⇒ **一家都不停**（这就是"后关的掐掉先开的"那个 bug）',
           not called, f'被叫了 {called}')
        other.kill()
        other.wait()

        # ── C2 我是最后一个 ⇒ 三家都停 ──
        SU.claim()
        called.clear()
        AF._stop_services_if_last()
        ok('C2 ★★★ 我是最后一个 ⇒ **三家都停**（不能只停 MuMu）',
           set(called) == {'mumu_bridge', 'plotpilot_bridge', 'penshot_bridge'},
           f'被叫了 {sorted(called)}')

        # ── C3 开关关掉的那家不许碰 ──
        AF.CFG = _FakeCfg({'MUMU_FOLLOW_APP': True,
                           'PLOTPILOT_FOLLOW_APP': True,
                           'PENSHOT_FOLLOW_APP': False})
        SU.claim()
        called.clear()
        AF._stop_services_if_last()
        ok('C3 ★★ `PENSHOT_FOLLOW_APP=false` 的那家**不许碰**（三家各自算）',
           'penshot_bridge' not in called
           and {'mumu_bridge', 'plotpilot_bridge'} <= set(called),
           f'被叫了 {sorted(called)}')

        # ── C4 判不出来 ⇒ 一家都不停（宁可留着，不可掐掉）──
        AF.CFG = _FakeCfg({'MUMU_FOLLOW_APP': True,
                           'PLOTPILOT_FOLLOW_APP': True,
                           'PENSHOT_FOLLOW_APP': True})
        _orig_any = SU.any_other_alive
        SU.any_other_alive = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom'))
        try:
            SU.claim()
            called.clear()
            AF._stop_services_if_last()
            ok('C4 ★★★ 判空出错 ⇒ **一家都不停**（保守方向：宁可留着）',
               not called, f'被叫了 {called}')
        finally:
            SU.any_other_alive = _orig_any
    finally:
        importlib.import_module = _orig_import
        AF.CFG = real_cfg


# ══════════════════════════════════════════════════════════════════
#  S 组：源码结构（AST，不用 grep —— 注释里也有那些词）
# [EN] Group S: source structure (AST, not grep -- those words are in comments too)
# ══════════════════════════════════════════════════════════════════
def _func(tree, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def test_structure() -> None:
    head('S · 源码结构：两边硬编码的目录串、三家接口、不许用 os.kill')
    svc_tree = ast.parse(SVCPATH.read_text(encoding='utf-8'))
    af_tree = ast.parse(AFPATH.read_text(encoding='utf-8'))

    # ── S1 Python 侧的目录串 ──
    got = None
    for n in ast.walk(svc_tree):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'DIR_REL':
            try:
                got = tuple(ast.literal_eval(v) for v in n.value.elts)
            except Exception:                               # noqa: BLE001
                got = None
    ok('S1 ★★ Python 侧 `DIR_REL` 是 `logs/service_users`',
       got == ('logs', 'service_users'), f'DIR_REL={got}')

    # ── S2 Go 侧写的是**同一串**（改名必须两边一起改）──
    #   ⚠ Go 源码**不能**用 Python 的 `ast` 解析 ⇒ 去掉行注释后按行找。
    # [EN] ⚠ Go source **cannot** be parsed by Python's `ast` => strip line
    # [EN] comments and look line by line.
    #   ⚠ 必须**先定位到 `svcUsersDir` 这个函数**：`services.go` 里还有别的
    #     `filepath.Join(appDir, …)`（比如控制器那条），抓第一行会抓错人。
    # [EN] ⚠ We must **first locate the `svcUsersDir` function**: `services.go`
    # [EN] has other `filepath.Join(appDir, …)` calls (the controller one, say) and
    # [EN] grabbing the first line would name the wrong one.
    lines = _strip_go_comments(GOSVC.read_text(encoding='utf-8')).splitlines()
    line = ''
    for i, ln in enumerate(lines):
        if ln.strip().startswith('func svcUsersDir'):
            for nxt in lines[i:i + 6]:
                if 'filepath.Join(appDir' in nxt:
                    line = nxt.strip()
                    break
            break
    ok('S2 ★★★ Go 侧 `svcUsersDir` 用的是**同一个目录串**',
       '"logs"' in line and '"service_users"' in line,
       line or '(没找到 svcUsersDir 里的 filepath.Join)')

    # ── S3 主程序退出时走 `_stop_services_if_last`（不是那三行只停 MuMu 的老代码）──
    has_call = False
    for n in ast.walk(af_tree):
        if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == '_stop_services_if_last':
            has_call = True
    ok('S3 ★★★ 关窗口那一刻调的是 `_stop_services_if_last`（带判空的那一个）',
       has_call)

    # ── S4 三家桥都有"甩出去不等"的停止接口 ──
    missing = []
    for name in ('mumu_bridge', 'penshot_bridge', 'plotpilot_bridge'):
        p = APP / 'novelservices' / f'{name}.py'
        t = ast.parse(p.read_text(encoding='utf-8'))
        if _func(t, 'stop_service_detached') is None:
            missing.append(name)
    ok('S4 ★★ 三家桥都有 `stop_service_detached`（关窗口那一刻不能同步等）',
       not missing, f'缺 {missing}' if missing else '三家都有')

    # ── S5 Windows 探活必须走退出码，且 `os.kill` 只在非 Windows 分支 ──
    pa = _func(svc_tree, 'pid_alive')
    win_first = False
    kill_after = False
    if pa is not None:
        for i, st in enumerate(pa.body):
            if isinstance(st, ast.If) and 'nt' in ast.dump(st.test) \
                    and '_win_alive' in ast.dump(st):
                win_first = True
            if win_first and 'kill' in ast.dump(st):
                kill_after = True
    wa = _func(svc_tree, '_win_alive')
    ok('S5 ★★★ Windows 分支先走 `_win_alive`，`os.kill` 只在别的分支',
       win_first and kill_after, f'win_first={win_first} kill_after={kill_after}')
    ok('S6 ★★★ `_win_alive` 用 `GetExitCodeProcess` 判死活（**不能只看打不打得开**）',
       wa is not None and 'GetExitCodeProcess' in ast.dump(wa))


def _strip_go_comments(src: str) -> str:
    """去掉 Go 的行注释（判据读的是源码，注释里也有那些串）。
    [EN] Strip Go line comments (the criterion reads source, and those strings
    [EN] appear in comments too)."""
    out = []
    for ln in src.splitlines():
        s = ln.strip()
        out.append('' if s.startswith('//') else ln)
    return '\n'.join(out)


# ══════════════════════════════════════════════════════════════════
#  自检：把「退出码判活」那道闸拆掉 ⇒ B5 那条必须失去作用
# [EN] Selftest: remove the "exit code decides aliveness" gate => B5 must lose its bite
# ══════════════════════════════════════════════════════════════════
def selftest() -> None:
    head('自检 · 拆掉「退出码判活」那道闸')
    src = SVCPATH.read_text(encoding='utf-8')
    old = 'code.value == _W_STILL_ACTIVE'
    if src.count(old) != 1:
        ok('S9 自检锚点唯一', False, f'出现 {src.count(old)} 次')
        return
    mod = types.ModuleType('broken_svc_users')
    exec(compile(src.replace(old, 'True'), 'broken_svc_users.py', 'exec'),
         mod.__dict__)
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    ok('S9 ★★ 拆掉那道闸 ⇒ 死进程被误判成活着（证明 B5 真的在测它）',
       mod.pid_alive(p.pid) is True,
       '拆掉后仍判死 ⇒ 说明 B5 红不红跟这道闸无关，B5 是摆设')


def main() -> int:
    from tools.verify_exit import finish
    print('多实例的收尸归属 —— 谁最后关，谁才收', flush=True)
    try:
        test_registry()
        test_liveness()
        test_stop_decision()
        test_structure()
        if '--selftest' in sys.argv:
            selftest()
    except Exception:                                       # noqa: BLE001
        import traceback
        return finish({'checks': CHECKS,
                       'fatal': traceback.format_exc()[-2000:]},
                      out_path=OUT / 'svc_users_report.json')
    return finish({'checks': CHECKS},
                  out_path=OUT / 'svc_users_report.json')


if __name__ == '__main__':
    sys.exit(main())
