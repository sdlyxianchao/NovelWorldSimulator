# -*- coding: utf-8 -*-
"""真机验证：起笔的**启动守卫**（2026-10-12）。

用户原话（同一轮报了两件事）：
> 「我连续点了两次起笔，结果就同时有两个推演过程在进行，这是不对的，同时应该只有一个。
>   同时，我点了起笔之后，感觉没反应了一段时间才开始推演，这也是为什么我会点两次的原因。
>   …一定要尽全力避免假死和真死机，即启动起笔失败但是界面看不到，或者成功了界面看不到，
>   引入超时机制，如果后台没成功，界面可以主动停止等待。但同时如果已经再次启动了另外一个
>   结果之前假死的启动成功了，也必须从中选择一个，停止另外一个，而不是两个都用」

所以这里验的不是"按钮变灰了"，而是**四件行为**：
  A. 逻辑：闸门真的在（`launch_busy` / `_launch_arm`）、令牌校验真的在（两处）、
     装配真的在**线程**里（界面不冻）、超时真的会放手、失败路径**上屏**、
     `finally` 真的会放开（否则永远起不来）。
  B. 真机：点「开始推演」**同一帧**就已经在启动态（切了运行页 + 中栏有字 +
     状态行写着「正在启动」），装配完自己转成运行中。
  C. 真机：**连点两次只会有一轮**（第二次被拒，项目里只多出一个运行文件夹）。
  D. 真机：**超时**之后界面主动停止等待；而且后台那一趟后来装好了也**不接管**
     （这就是用户要的"两个里只留一个"）。
  E. 真机：装配**失败**时中栏看得见（"界面看不到"是用户点名的假死之一）。

产出 `assets/screenshots/start_guard_report.json`。

跑法：
    .venv/Scripts/python tools/verify_start_guard.py
    .venv/Scripts/python tools/verify_start_guard.py --logic-only

English:
Real-machine verification: the **launch guard** for start-writing (2026-10-12).
The user's exact words (two things in one report): "I clicked start-writing twice in a row and two
simulations ended up running at the same time; there should only ever be one. Also, after clicking
start-writing nothing happened for a while before it started, which is why I clicked twice. ...
do your utmost to avoid fake hangs and real hangs: the launch failing while the UI shows nothing,
or succeeding while the UI shows nothing. Introduce a timeout mechanism so the UI can stop waiting
on its own if the background never succeeds. But if another one has already been started and the
earlier 'hung' launch then succeeds, one must be chosen and the other stopped -- not both."
So this verifies four **behaviours**, not "the button is greyed":
  A. Logic: the gate really exists (`launch_busy` / `_launch_arm`), the token checks really exist
     (two places), assembly really runs on a **thread** (the UI does not freeze), the timeout really
     lets go, failure paths **reach the screen**, and the `finally` really releases (otherwise
     starting would be impossible forever).
  B. Real machine: clicking "Start" is already in the starting state **on the same frame**
     (switched to the run screen + a line in the middle column + the status line says "starting"),
     and it flips to running by itself when assembly finishes.
  C. Real machine: **clicking twice yields only one round** (the second is refused, and only one run
     folder appears in the project).
  D. Real machine: after the **timeout** the UI stops waiting on its own; and the background pass
     **does not take over** even if it later assembles successfully (this is the "keep one of the
     two" the user asked for).
  E. Real machine: when assembly **fails**, the middle column shows it ("the UI shows nothing" is one
     of the fake hangs the user named).
Produces `assets/screenshots/start_guard_report.json`.
How to run:
    .venv/Scripts/python tools/verify_start_guard.py
    .venv/Scripts/python tools/verify_start_guard.py --logic-only
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import sys
import tempfile
import textwrap
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                     # noqa: E402
from util.flet_shutdown import shutdown               # noqa: E402

from config import CFG                                 # noqa: E402
CFG.set('MOCK_LLM', 'true')
# 开场那张卡（§3.6.1）会等一次模型调用 —— 这里验的是**启动守卫**，
# 关掉它让"装配 → 接管"这条链短一点、结论干净一点。
# [EN] The opening card (§3.6.1) waits for a model call -- what is verified here is the **launch
# [EN] guard**, so
# [EN] turning it off shortens the "assemble -> take over" chain and keeps the conclusion clean.
CFG.set('SHOW_OPENING', 'false')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

import verify_ui_common as VU                          # noqa: E402
import verify_run_control as VRC                       # noqa: E402
from store.project import Project                      # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
LOGIC_ONLY = '--logic-only' in sys.argv

_checks: list[tuple[str, bool, str]] = []
report: dict = {}


def ok(name: str, passed: bool, detail: str = '') -> bool:
    """记一条结论（`detail` 只在失败时打印，成功时也不丢 —— 进报告）。
        English:
    Record one conclusion (`detail` is printed only on failure, but never lost -- it goes to the
    report).
    """
    _checks.append((name, bool(passed), str(detail)))
    print(f"  {'✓' if passed else '✗'} {name}" + (f"   {detail}" if not passed else ''))
    return bool(passed)


def rec(name: str, passed: bool, detail: str = '') -> bool:
    return ok(name, passed, detail)


# ── AST 小工具（只看"调了什么"，不看字符串形状）──
# [EN] -- Small AST helpers (only "what is called", not string shapes) --
def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _tree(fn):
    return ast.parse(_src(fn))


def _calls(node, name: str) -> list:
    """所有 `xxx.name(...)` / `name(...)` 调用点。
        English:
    All call sites of `xxx.name(...)` / `name(...)`.
    """
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr == name:
            out.append(n)
        elif isinstance(f, ast.Name) and f.id == name:
            out.append(n)
    return out


def _names(node) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            out.add(f'{n.value.id}.{n.attr}')
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Name):
            out.add(n.id)
    return out


def all_texts(ctrl) -> list[str]:
    return [str(x) for x in VU.all_texts(ctrl)]


def find_btn(root, needle: str):
    """按文字找按钮（**不挑控件类名**：对话框里那几个按钮的类名不一定统一）。
        English:
    Find a button by text (**without matching the control class name**: the buttons inside the dialog
    are not necessarily of one class).
    """
    for c in VU.walk(root):
        if not (hasattr(c, 'on_click') and c.on_click):
            continue
        v = getattr(c, 'content', '')
        v = v if isinstance(v, str) else getattr(v, 'value', '')
        if needle in str(v):
            return c
    return None


def dialog_texts(page) -> list[str]:
    """当前**开着**的对话框里所有文字（用来判"那个框到底弹没弹"）。
        English:
    All text inside the currently **open** dialogs (used to judge "did that dialog actually pop up").
    """
    out: list[str] = []
    for d in VU.open_dialogs(page):
        out += all_texts(d)
    return out


def trash_snapshot(projects_root) -> set:
    """「已删除备份」当前有哪些条目（用来判"这一趟被搬进去了没有"）。

    ⚠ 必须**前后取两次差**：`%TEMP%\已删除备份` 是跨运行累积的，
      直接看"里面有东西"会把上一轮留下的当成这一轮的证据。
    [EN] Which entries the "Deleted Backup" currently holds (used to judge "was this pass moved in").
    [EN] ⚠ Must take the **difference between two snapshots**: `%TEMP%\已删除备份` accumulates across
      runs, so just "there is something in it" would treat the previous run's leftovers as this run's
      evidence.
    """
    try:
        from store.project import trash_dir_for
        d = trash_dir_for(Path(projects_root))
        return {p.name for p in d.iterdir()} if d.is_dir() else set()
    except Exception:                                        # noqa: BLE001
        return set()


def discarded_ok(proj_root, before_runs: list[str], before_trash: set,
                 projects_root) -> tuple[bool, str]:
    """作废掉的那一趟**要么被搬进「已删除备份」、要么留了一张「已作废.md」**。

    ⚠ 为什么不能只断"文件夹没了"：Windows 上只要目录里有文件被占着
      （杀软正在扫刚写出来的 `state.db`），`os.rename` 会 `WinError 5` 重试三次
      都失败 —— 那是**操作系统的事**，不是判据该时红时绿的地方（实测：
      同一条判据在不同轮次里红过也绿过）。所以口径是"**要么搬走、要么明确
      标出来它是个空壳**"，两条都能证明"这一趟真的被作废收拾过"。
    [EN] The voided pass is **either moved into "Deleted Backup" or marked with 「已作废.md」**.
    [EN] ⚠ Why not just assert "the folder is gone": on Windows, if any file in the directory is held
      (antivirus scanning the freshly written `state.db`), `os.rename` raises `WinError 5` and all three
      retries fail -- that is **the operating system's business**, not something a criterion should go red
      and green about (measured: the same assertion was red in one run and green in another). So the
      convention is "**either moved away, or clearly marked as an empty shell**"; either one proves the
      pass really was voided and tidied up.
    """
    after_runs = sorted(p.name for p in proj_root.glob('第*模拟*') if p.is_dir())
    extra = [n for n in after_runs if n not in before_runs]
    if not extra:
        # 没多出文件夹 ⇒ 它被搬走了（或压根没建过）—— 去备份里找**新出现的那一份**
        # [EN] No extra folder ⇒ it was moved away (or never created) -- look for the **new** entry in
        # [EN] the backup directory
        new_trash = sorted(trash_snapshot(projects_root) - before_trash)
        if new_trash:
            return True, f'已搬进「已删除备份」：{new_trash[-1]}'
        return False, f'运行文件夹没多出、备份里也没有新的（{after_runs}）'
    marked = [n for n in extra if (proj_root / n / '已作废.md').exists()]
    if marked:
        return True, f'留了「已作废.md」：{marked}'
    return False, f'{extra} 既没搬走、也没留说明'


def narr_all(app) -> str:
    """中栏**全部**文字（断言一律用这个）。
    ⚠ 别拿报告里那份 `[:200]` 的截断串去断言 —— 中栏上面还挂着续跑的上一轮正文，
      截断之后要判的那一句正好被切掉（第一版 D4/D12 就是这么假红的）。
        English:
    **All** text of the middle column (use this for every assertion).
        ⚠ Never assert on the truncated `[:200]` string kept in the report -- the previous round's script
          is still parked at the top of the middle column, and truncation cuts off exactly the line being
          judged (that is how the first version's D4/D12 went falsely red).
    """
    return ' '.join(all_texts((app._ui_run or {}).get('narrative')))


def newest_msg(app) -> str:
    try:
        return str((app._messages or [{}])[-1].get('text', ''))
    except Exception:                                       # noqa: BLE001
        return ''


# ══════════════════════════════════════════════════════════════
#  A. 逻辑（AST + 纯函数）
# [EN] A. Logic (AST + pure functions)
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    print('\n── A 组：逻辑（闸门 / 令牌 / 线程 / 超时 / 失败上屏）──')
    from gui.app_flet import NovelWorldApp as APP
    import gui.app_flet as G

    # A1：两个入口都问过闸门（少一个就会从那条路漏进第二轮）
    # [EN] A1: both entry points ask the gate (miss one and the second round leaks in through it)
    nr = _tree(APP._on_new_round)
    ok('A1 ★★ 「起笔」入口先问闸门（`launch_busy()`）—— 只看 `self.session` 就是用户报的那个漏',
       any(_calls(nr, 'launch_busy')), _src(APP._on_new_round)[:120])
    # ⚠⚠ **数"调用"，不是数字符串**（2026-10-12 实测踩到）：这段源码的**注释里**
    #   就写着 `_launch_arm()` / `launch_busy()`，按 `str.count` 数的话，
    #   把两个闸门**全删了**这条判据照样绿 —— 反例法 M2 当场揭穿。
    # [EN] ⚠⚠ **Count calls, not strings** (measured 2026-10-12): the **comments** in this source
    # [EN] mention `_launch_arm()` / `launch_busy()`, so counting with `str.count` keeps this criterion
    # [EN] green even after **both gates are deleted** -- counter-example M2 exposed it on the spot.
    begin_tree = _tree(APP.show_start_story_dialog)
    n_gate = len(_calls(begin_tree, 'launch_busy')) + len(_calls(begin_tree, '_launch_arm'))
    ok('A2 ★★ 「开始推演」那条路上有两处闸门（点下就问一次 + 排任务前再问一次）',
       n_gate >= 2, f'只数到 {n_gate} 处调用')

    # A3：闸门本体 —— `_launch_arm` 先问 `launch_busy()`，不能起就 None
    # [EN] A3: the gate itself -- `_launch_arm` asks `launch_busy()` first and returns None if it
    # [EN] cannot start
    arm = _tree(APP._launch_arm)
    ok('A3 ★★★ `_launch_arm()` 是唯一闸门：先问 `launch_busy()`，不能起返回 `None`',
       any(_calls(arm, 'launch_busy')) and 'None' in _src(APP._launch_arm),
       _src(APP._launch_arm)[:160])
    busy = _src(APP.launch_busy)
    ok('A4 ★★★ `launch_busy()` 同时看**启动态**与**活的会话**（只看一个都漏）',
       'LAUNCH_STARTING' in busy and 'is_alive' in busy, busy[:160])

    # A5：`_start_round` 里两处令牌校验（开工前 + 接管前），接管前那处要作废文件夹
    # [EN] A5: two token checks inside `_start_round` (before starting + before taking over), and the
    # [EN] one before taking over must discard the folder
    st = _src(APP._start_round)
    n_tok = st.count('self._launch_token')
    ok('A5 ★★★ `_start_round` 里**两处**令牌校验（开工前 + 接管界面前）',
       n_tok >= 2, f'出现 {n_tok} 次')
    ok('A6 ★★★ 接管前对不上号时**连运行文件夹也搬走**（不留空壳档案）',
       '_launch_discard_run' in st, '')

    # A7：`_begin_run` 接管前也对一次号（开场那一步可能等模型）
    # [EN] A7: `_begin_run` also re-checks the token before taking over (the opening step may wait for
    # [EN] a model call)
    br = _src(APP._begin_run)
    ok('A7 ★★ `_begin_run` 接管前也对号 —— 开场那一步可能等模型，这期间用户会点第二次',
       '_launch_token' in br and '_round_tok' in br, br[:160])

    # A8：装配在线程里（不冻界面），否则超时看门狗根本没机会跑
    # [EN] A8: assembly runs on a thread (the UI does not freeze), otherwise the timeout watchdog would
    # [EN] never get a chance to run
    ok('A8 ★★★ 装配走 `asyncio.to_thread` —— 在事件循环里直呼会把界面和看门狗一起冻住',
       any(_calls(ast.parse(st), 'to_thread')), '')

    # A9：超时机制 —— 看门狗读旋钮、到点走 `_launch_timeout_hit`
    # [EN] A9: the timeout mechanism -- the watchdog reads the knob and calls `_launch_timeout_hit`
    # [EN] when the time is up
    w = ast.parse(_src(APP._launch_watch))
    ok('A9 ★★★ 看门狗 `_launch_watch()`：读 `launch_timeout()` 且到点调 `_launch_timeout_hit()`',
       any(_calls(w, 'launch_timeout')) and any(_calls(w, '_launch_timeout_hit')), '')
    hit = _src(APP._launch_timeout_hit)
    # ⚠ 判"有没有硬杀"要用**调用**，不能拿字符串找 `cancel` ——
    #   它自己那一行 `_launch_cancel(...)` 里就有这四个字母（第一版就是这么假红的）。
    # [EN] ⚠ "Does it hard-kill" must be judged on **calls**, not by searching the string `cancel` --
    # [EN] its own line `_launch_cancel(...)` contains those four letters (that is how the first version
    # [EN] went falsely red).
    ok('A10 ★★ 超时**不硬杀后台**（没有 `cancel()` 调用），只作废令牌'
       '（硬杀杀不掉，还会留下写了一半的产物）',
       not _calls(ast.parse(hit), 'cancel')
       and '_launch_token += 1' in _src(APP._launch_cancel), '')

    # A11：放开启动态挂在 finally 上（否则 `launch_busy()` 恒真 = 永远起不来）
    # [EN] A11: releasing the starting state hangs on a `finally` (otherwise `launch_busy()` is always
    # [EN] true = starting is impossible forever)
    ls = _src(APP._launch_and_start)
    ok('A11 ★★★ 放开"正在启动"挂在 `finally` 里（散在各个 return 前就会漏一处、永远起不来）',
       'finally:' in ls and '_launch_release' in ls, ls[:200])
    ok('A12 ★★ `_launch_release` 只在令牌对得上时放开（不能把别人那一趟的态清掉）',
       'tok != self._launch_token' in _src(APP._launch_release), '')

    # ⚠⚠ **一条都不能少，所以逐条点名**（2026-10-12 实测踩到）：这段里有 **6** 处
    #   `_launch_fail(`，只数"`>= 3`"的话，把其中一条改回裸 SnackBar 照样绿
    #   —— 反例法 M11 当场揭穿。改成"这三条失败的文案必须**出现在
    #   `_launch_fail()` 的实参里**"（文案搬回 `_show_snack` 就红）。
    # [EN] ⚠⚠ **Not one may be missing, so each is named** (measured 2026-10-12): there are **6**
    # [EN] `_launch_fail(` occurrences here, and counting "`>= 3`" alone stays green even after one is
    # [EN] reverted to a bare SnackBar -- counter-example M11 exposed it. Changed to "these three failure
    # [EN] messages must **appear as arguments of `_launch_fail()`**" (moving one back to `_show_snack`
    # [EN] goes red).
    _st_tree = ast.parse(st)
    _fail_args = ' '.join(ast.unparse(c) for c in _calls(_st_tree, '_launch_fail'))
    _three = ('创建运行文件夹失败', '初始化模型客户端失败', '装配世界失败')
    ok('A13 ★★★ 三条启动失败路径**都**走 `_launch_fail()`'
       '（= SnackBar + **中栏留一条**，SnackBar 会没）',
       all(k in _fail_args for k in _three), _fail_args[:220])
    ok('A14 ★★ 失败/超时/取消**同一个出口** `_launch_cancel()`（三处各写一遍迟早漏两处）',
       '_launch_cancel(' in _src(APP._launch_fail)
       and '_launch_cancel(' in hit, '')

    # A15：状态行两条口径都要认"正在启动"
    # [EN] A15: both status-line conventions must recognise "starting"
    ok('A15 ★★★ 状态文字认启动态（`_status_view` 与 `_run_status_text` 各一条分支）'
       '—— 否则屏幕上写着「未运行」，用户就又点一次',
       'LAUNCH_STARTING' in _src(APP._status_view)
       and 'LAUNCH_STARTING' in _src(APP._run_status_text), '')
    sms = _src(APP.show_main_screen)
    ok('A16 ★★ 中栏把启动态算进 `live`（不然会回落到上一轮落盘正文，把"正在装配"挤掉）',
       'LAUNCH_STARTING' in sms and 'live =' in sms, '')

    # A17：旋钮真的被产品源码读（防假旋钮）
    # [EN] A17: the knob is really read by the product source (guards against a fake knob)
    src_all = ''
    for p in (APP_DIR / 'gui').rglob('*.py'):
        src_all += p.read_text(encoding='utf-8', errors='ignore')
    ok('A17 ★★ `LAUNCH_TIMEOUT_S` 是**真旋钮**（产品源码里读得到）且带下限保护',
       "'LAUNCH_TIMEOUT_S'" in src_all and 'LAUNCH_TIMEOUT_FALLBACK' in _src(APP.launch_timeout),
       '')
    ok('A18 ★ 心跳间隔是常量（装配期间状态条靠它自己走 —— "没死"的证据）',
       isinstance(G.LAUNCH_HEARTBEAT_S, float) and G.LAUNCH_HEARTBEAT_S <= 2.0,
       str(getattr(G, 'LAUNCH_HEARTBEAT_S', None)))

    # A19：运行界面那颗「停止」在启动中要变成「取消启动」（手动出口）
    # [EN] A19: on the run screen that "Stop" button must become "Cancel launch" while starting (the
    # [EN] manual outlet)
    ok('A19 ★★ 启动中那颗按钮变成「取消启动」（手动出口；超时上限几分钟，等不了的人自己按）',
       '⏹ 取消启动' in _src(APP._refresh_run_controls), '')
    ok('A20 ★★ 按「取消启动」走的是同一个出口（不是"这一轮已经停了"那句 —— 那时候说它是错的）',
       '_launch_cancel(' in _src(APP._on_stop_run), '')
    # ⚠ 下面两条是"收拾作废那一趟"的两半：**先关库**（不然搬不动）+
    #   **搬不动就留说明**（不然空壳冒充正常存档）。两句都只在源码里留痕，
    #   但它们各自对应一个真实现场（WinError 5 / 回卷里多一个空档）。
    # [EN] ⚠ The next two are the two halves of "tidying up the voided pass": **close the DB first**
    # [EN] (otherwise it cannot be moved) + **leave a note when the move fails** (otherwise the empty
    # [EN] shell masquerades as a normal save). Both only leave traces in the source, but each
    # [EN] corresponds to a real on-site symptom (WinError 5 / one extra empty save in the resume list).
    _dis = _src(APP._launch_discard_run)
    ok('A25 ★★ 搬不动时留一张「已作废.md」'
       '（Windows 上目录被占是常事 —— 别让空壳冒充一次正常的存档）',
       '已作废.md' in _dis, '')
    # ⚠ **按 AST 的行号比，不要 `str.find`**：这段 docstring 里就写着
    #   `store.project.archive_run_dir()`，`find` 会先命中那句说明，
    #   于是"先关库再搬"恒为假 —— 第一版就是这么**从出生起就是红的**
    #   （反例法当时还"按预期变红"了，因为它本来就没绿过）。
    # [EN] ⚠ **Compare line numbers via AST, not `str.find`**: this docstring itself mentions
    # [EN] `store.project.archive_run_dir()`, so `find` hits that description first and "close the DB,
    # [EN] then move" is forever false -- the first version was **red from birth** (and the
    # [EN] counter-example method still reported "reddened as expected", because it had never been
    # [EN] green).
    _dis_lines: dict = {}
    for _n in ast.walk(ast.parse(_dis)):
        if not isinstance(_n, ast.Call):
            continue
        _attr = getattr(_n.func, 'attr', None)
        if _attr == 'close' and getattr(getattr(_n.func, 'value', None), 'id', '') == 'db':
            _dis_lines['close'] = _n.lineno
        elif _attr == 'archive_run_dir':
            _dis_lines['move'] = _n.lineno
    # ⚠ **还要看那道 `if db is not None:` 的守卫在不在**：只看"`db.close()` 在
    #   `archive_run_dir` 之前"的话，把守卫改成 `if False:`（等于根本没关）照样绿
    #   —— 反例法 M17 当场揭穿（那条变异第一次"变红"只是因为 A26 当时自己坏着，
    #   修好之后立刻暴露成"没抓到"）。
    # [EN] ⚠ **Also check that the `if db is not None:` guard is still there**: judging only by
    # [EN] "`db.close()` comes before `archive_run_dir`" stays green even after the guard becomes
    # [EN] `if False:` (i.e. never closes) -- counter-example M17 exposed it on the spot (that mutation
    # [EN] "reddened" the first time only because A26 was broken itself; once fixed it immediately showed
    # [EN] as "not caught").
    ok('A26 ★★ 搬之前**先关这一轮的数据库**（不关就搬不动 —— 实测 WinError 5 三次全败）',
       bool(_dis_lines.get('close'))
       and _dis_lines['close'] < (_dis_lines.get('move') or 10 ** 6)
       and 'if db is not None:' in _dis,
       f"{_dis_lines} · guard={'if db is not None:' in _dis}")


def group_a_logic() -> None:
    """纯函数：超时的下限保护（不依赖真实界面）。
        English:
    Pure functions: the timeout's lower-bound protection (no real UI needed).
    """
    print('\n── A′ 组：纯逻辑（超时读法）──')
    from gui.app_flet import NovelWorldApp as APP
    import gui.app_flet as G
    app = APP()
    old = CFG.s('LAUNCH_TIMEOUT_S')
    try:
        CFG.set('LAUNCH_TIMEOUT_S', '25')
        ok('A21 ★★ 旋钮说了 25 秒就等 25 秒（现读，不用重启）',
           app.launch_timeout() == 25.0, str(app.launch_timeout()))
        CFG.set('LAUNCH_TIMEOUT_S', '1')          # 低于下限 ⇒ 夹紧到 20
        # [EN] Below the floor ⇒ clamped to 20
        # ⚠ 两道都要看：**旋钮自己那层下限**（SPEC 的 `min`）+ **代码里那层兜底**
        #   （`>= 10` 就照用、否则退回 180）。只看行为的话，把 SPEC 的 `min` 去掉
        #   仍然会被代码兜底救成 180 ⇒ 照样绿 —— 反例法 M20 当场揭穿。
        # [EN] ⚠ Both layers must be checked: **the knob's own floor** (SPEC's `min`) + **the code's
        # [EN] fallback** (use it when `>= 10`, otherwise fall back to 180). Judging by behaviour alone
        # [EN] stays green after SPEC's `min` is removed, because the code fallback still rescues it to
        # [EN] 180 -- counter-example M20 exposed it on the spot.
        from config import SPEC as _SPEC
        ok('A22 ★★ 填得太小时**不会退化成"等 1 秒就超时"**'
           '（SPEC 的下限 + 代码里的兜底，两道都在）',
           int(_SPEC['LAUNCH_TIMEOUT_S'].get('min') or 0) >= 10
           and app.launch_timeout() >= 20,
           f"SPEC.min={_SPEC['LAUNCH_TIMEOUT_S'].get('min')} · "
           f"launch_timeout()={app.launch_timeout()}")
        CFG.set('LAUNCH_TIMEOUT_S', '')
        ok('A23 ★ 空值走兜底值（不是 0 —— 0 会让每一趟都"瞬间超时"）',
           app.launch_timeout() == float(G.LAUNCH_TIMEOUT_FALLBACK),
           str(app.launch_timeout()))
    finally:
        CFG.set('LAUNCH_TIMEOUT_S', old)
    ok('A24 ★ 没在启动时 `launch_elapsed()` 是 0（状态条上那个秒表不会凭空跳）',
       app.launch_elapsed() == 0.0 and app.launch_busy() is False, '')


# ══════════════════════════════════════════════════════════════
#  B/C/D/E. 真机
# [EN] B/C/D/E. Real machine
# ══════════════════════════════════════════════════════════════
async def _wait(pred, timeout: float = 30.0, step: float = 0.1) -> bool:
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    while loop.time() - t0 < timeout:
        try:
            if pred():
                return True
        except Exception:                                   # noqa: BLE001
            pass
        await asyncio.sleep(step)
    return False


async def main(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    import gui.app_flet as G
    import sim.setup as SIM_SETUP
    from i18n import set_lang
    set_lang(_lang)

    env_path = Path(APP_DIR / '.env')
    env_backup = env_path.read_text(encoding='utf-8') if env_path.exists() else None

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp_projects = Path(tempfile.mkdtemp(prefix='nws_startguard_proj_'))
    old_projects = CFG.s('DEFAULT_PROJECTS_DIR')
    CFG.set('DEFAULT_PROJECTS_DIR', str(tmp_projects))
    proj_root = tmp_projects / '启动守卫验证'
    real_assemble = SIM_SETUP.assemble
    tries: dict = {}
    try:
        proj_root.mkdir(parents=True, exist_ok=True)
        proj = VRC.make_project(proj_root, chars=3, nodes=0)
        proj.write_nwsproj()
        app.current_project = proj

        # ── B. 点完**同一帧**就在启动态 ──
        # [EN] -- B. On the same frame as the click, it is already starting --
        print('\n── B 组：点完立刻进状态 ──')
        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.6)
        ok('B0 没在启动时 `launch_busy()` 是 False（未运行时起笔按钮该是亮的）',
           app.launch_busy() is False, str(app.launch_busy()))

        # 让装配慢一点，好让"启动态"这一帧真的可观察（不慢的话 MOCK 下瞬间就跑完了）
        # [EN] Slow assembly down a little so the "starting" frame is genuinely observable
        # [EN] (otherwise under MOCK it finishes instantly)
        SLEEP_C = 2.0

        def _slow_assemble(*a, **kw):
            time.sleep(SLEEP_C)
            return real_assemble(*a, **kw)

        SIM_SETUP.assemble = _slow_assemble
        dlg = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.5)
        btn = find_btn(dlg, '开始推演') if dlg is not None else None
        ok('B1 找得到「开始推演」按钮', btn is not None, '')
        btn.on_click(None)                       # 同步：这一句返回时就该在启动态了
        # [EN] Synchronous: by the time this call returns it must already be in the starting state
        ph = app._launch_phase
        ui = app._ui_run or {}
        st_txt = str(getattr(ui.get('status'), 'value', '') or '')
        narr = narr_all(app)
        report['b_immediate'] = {'phase': ph, 'view': getattr(app, '_view', ''),
                                 'status': st_txt, 'narr': narr[:120]}
        ok('B2 ★★★ 点「开始推演」**返回这一帧**就已是启动态（不等装配）',
           ph == G.LAUNCH_STARTING, f'phase={ph}')
        ok('B3 ★★★ 同一帧已经**切到运行页**了（不再让用户对着开始菜单发呆）',
           app._view == 'main' and bool(ui), str(app._view))
        ok('B4 ★★★ 中栏当场写着「正在装配」（"确实开始了"最直接的证据）',
           '正在装配' in narr, narr[:100])
        ok('B5 ★★★ 状态行当场写着「正在启动」（不是「未运行」—— 那正是用户又点一次的原因）',
           '正在启动' in st_txt, st_txt)
        ok('B6 ★★ 启动中「起笔」按不动了（可见的那一半；真闸门在 `_launch_arm`）',
           ui.get('btn_start') is not None and ui['btn_start'].disabled is True,
           str(getattr(ui.get('btn_start'), 'disabled', None)))
        stop_txt = str(getattr(getattr(ui.get('btn_stop'), 'content', ''), 'value',
                               getattr(ui.get('btn_stop'), 'content', '')))
        ok('B7 ★★ 启动中那颗按钮写着「取消启动」且可点（手动出口）',
           '取消启动' in stop_txt and ui['btn_stop'].disabled is False, stop_txt)
        await asyncio.sleep(0.6)                 # 再看一帧（确认不是"只在同步那一瞬"）
        # [EN] Look at one more frame (to confirm it is not "only for that synchronous instant")
        ok('B8 ★★ 过了几帧还在启动态（界面没被冻住 —— 装配在线程里）',
           app._launch_phase == G.LAUNCH_STARTING and app.session is None,
           f'phase={app._launch_phase}')
        shot = await page.take_screenshot()
        if shot:
            (OUT / f'start_guard_starting{SUFFIX}.png').write_bytes(shot)

        # ── C. 连点两次只会有一轮 ──
        # [EN] -- C. Clicking twice yields only one round --
        print('\n── C 组：连点两次 → 只有一轮 ──')
        # 第二次：趁第一趟还在装配，**从**菜单**入口再点一次（用户真实的动作）
        # [EN] Second click: while the first is still assembling, click again **from the menu entry**
        # [EN] (what the user actually did)
        # ⚠ `n_before` 是**第一趟已经建好文件夹之后**取的（B 组的点击就建了一个）——
        #   所以这里要断的是"**不再涨**"，而不是"变成 n_before+1"（第一版就是这么假红的）。
        # [EN] ⚠ `n_before` is taken **after the first launch already created its folder** (group B's
        # [EN] click made one) -- so this must assert "**it does not grow**", not "it becomes n_before+1"
        # [EN] (that is how the first version went falsely red).
        n_before = len(list(proj_root.glob('第*模拟*')))
        app._on_new_round()
        await asyncio.sleep(0.3)
        dlgs = dialog_texts(page)
        report['c_second'] = {'msg': newest_msg(app), 'dialogs': dlgs[:3],
                              'token': app._launch_token}
        ok('C1 ★★★ 装配中再点「起笔」**不弹对话框**（被拦住了）',
           not any('启动故事' in x for x in dlgs), str(dlgs)[:120])
        ok('C2 ★★★ 而且**当场说清为什么**（"上一趟还在装配 · 不会同时开两轮"）',
           '装配' in newest_msg(app) or '同时' in newest_msg(app), newest_msg(app))
        # 再直接点一次对话框里的按钮那条路（同一个 `_begin`）
        # [EN] And click the dialog's own button path once more (the same `_begin`)
        try:
            btn.on_click(None)
        except Exception:                                   # noqa: BLE001
            pass
        SIM_SETUP.assemble = real_assemble       # 这条跑通的装配要真的
        # [EN] This pass, which is meant to run through, needs the real assembly
        got = await _wait(lambda: app.session is not None and app.session.is_alive, 60)
        ok('C3 ★★ 第一趟照常跑起来了（拦第二次**没有把它一起挡住**）', got,
           f'phase={app._launch_phase}')
        runs = sorted(p.name for p in proj_root.glob('第*模拟*'))
        report['c_runs'] = runs
        ok('C4 ★★★ 项目里**只有一个**运行文件夹（连点两次不会开出第二个）',
           len(runs) == n_before == 1, str(runs))
        ok('C5 ★★★ 只有**一个**会话（`self.session` 不是两套）',
           app.session is not None and app.session.is_alive,
           str(getattr(app.session, 'status', None)))
        ok('C6 ★★ 跑起来之后启动态已经放开（`_launch_phase` 回到 idle）',
           app._launch_phase == G.LAUNCH_IDLE, app._launch_phase)

        # ── B′. 运行中再点「起笔」也被拦；停止后可以再来 ──
        # [EN] -- B'. While running, start-writing is refused too; after stopping it is allowed --
        print('\n── B′ 组：运行中不许再开一轮 ──')
        app._on_new_round()
        await asyncio.sleep(0.2)
        ok('B9 ★★★ 运行中再点「起笔」被拦住（不弹对话框）',
           not any('启动故事' in x for x in dialog_texts(page)),
           str(dialog_texts(page))[:100])
        ok('B10 ★★ 并且说了为什么（"这一轮还在跑"）',
           '跑' in newest_msg(app) or '停止' in newest_msg(app), newest_msg(app))

        app._on_stop_run()
        await _wait(lambda: app.session is not None
                    and app.session.status == 'stopped', 90)
        ok('B11 ★★ 停掉之后 `launch_busy()` 回到 False（可以重新起笔）',
           app.launch_busy() is False, str(app.launch_busy()))
        runs_before_d = sorted(p.name for p in proj_root.glob('第*模拟*'))
        trash_before_d = trash_snapshot(tmp_projects)

        # ── D. 超时：界面主动停止等待 + 后台那一趟不接管 ──
        # [EN] -- D. Timeout: the UI stops waiting + the background pass does not take over --
        print('\n── D 组：超时（界面主动停止等待）──')
        app.launch_timeout = lambda: 1.5          # 测速用：真值由 A21 钉
        # [EN] For test speed: the real value is pinned by A21
        G.LAUNCH_HEARTBEAT_S = 0.2
        SLEEP_D = 5.0

        def _stuck_assemble(*a, **kw):
            time.sleep(SLEEP_D)                   # 模拟"卡住的装配"
            # [EN] Simulate a "stuck assembly"
            return real_assemble(*a, **kw)

        SIM_SETUP.assemble = _stuck_assemble
        dlg2 = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.4)
        btn2 = find_btn(dlg2, '开始推演')
        # 「开始推演」那句要重新绑（对话框是新弹的一个）
        # [EN] The "Start" handler has to be clicked on the fresh dialog
        ok('D1 第二趟也拿到了启动态', btn2 is not None and app.launch_busy() is False, '')
        btn2.on_click(None)
        ok('D2 点完在启动态', app._launch_phase == G.LAUNCH_STARTING,
           app._launch_phase)
        # 等超时（1.5 秒 + 看门狗 0.2 秒一格）
        # [EN] Wait out the timeout (1.5 s + a 0.2 s watchdog tick)
        hit = await _wait(lambda: app._launch_phase == G.LAUNCH_IDLE, 12)
        waits = app.launch_elapsed()
        report['d_timeout'] = {'hit': hit, 'elapsed': waits,
                               'msg': newest_msg(app),
                               'narr': narr_all(app)[:200]}
        ok('D3 ★★★ 超时之后界面**自己停止等待**（启动态放开）', hit,
           f'phase={app._launch_phase}')
        ok('D4 ★★★ 并且说清了"超时"这件事（SnackBar + 中栏各一条）',
           '超时' in newest_msg(app) and '超时' in narr_all(app),
           f"{report['d_timeout']['msg']} | {narr_all(app)[-160:]}")
        ok('D5 ★★★ 状态条不再是"正在启动"（回到可以重来的样子）',
           '正在启动' not in str(getattr(((app._ui_run or {}).get('status')),
                                          'value', '') or ''),
           str(getattr((app._ui_run or {}).get('status'), 'value', '')))
        ok('D6 ★★ 此时可以马上重来（`launch_busy()` 已是 False）',
           app.launch_busy() is False, str(app.launch_busy()))
        # 现在等**那一趟卡住的后台**醒过来（5 秒）——它绝不能接管界面
        # [EN] Now wait for the **stuck background pass** to wake up (5 s) -- it must not take over
        await asyncio.sleep(SLEEP_D + 2.5)
        runs_after_d = sorted(p.name for p in proj_root.glob('第*模拟*'))
        report['d_runs'] = {'before': runs_before_d, 'after': runs_after_d}
        ok('D7 ★★★ 后台那一趟后来装好了**也没有接管界面**（`self.session` 仍是停掉时的那个）',
           app.session is None or app.session.status == 'stopped',
           str(getattr(app.session, 'status', None)))
        _d_ok, _d_why = discarded_ok(proj_root, runs_before_d, trash_before_d,
                                     tmp_projects)
        ok('D8 ★★★ 它刚建的那个运行文件夹被**收拾掉了**（搬走 / 或留了「已作废.md」标记）—— '
           '不让它在「回卷」里冒充一次正常的存档',
           _d_ok, f'{runs_before_d} → {runs_after_d}｜{_d_why}')
        ok('D9 ★★ 中栏也没有被它偷改（还写着这一趟作废/超时那件事）',
           '超时' in narr_all(app), '')

        # ── D′. 手动「取消启动」（与超时同一个出口）──
        # [EN] -- D'. Manual "cancel launch" (the same outlet as the timeout) --
        print('\n── D′ 组：手动取消启动 ──')
        SLEEP_CANCEL = 4.0

        def _stuck2(*a, **kw):
            time.sleep(SLEEP_CANCEL)
            return real_assemble(*a, **kw)

        SIM_SETUP.assemble = _stuck2
        runs_before_e = sorted(p.name for p in proj_root.glob('第*模拟*'))
        trash_before_e = trash_snapshot(tmp_projects)
        dlg4 = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.4)
        find_btn(dlg4, '开始推演').on_click(None)
        ok('D10 又进了启动态', app._launch_phase == G.LAUNCH_STARTING,
           app._launch_phase)
        # ⚠⚠ **先让这一趟真的开跑，再取消**（2026-10-12 实测踩到）：测试代码从
        #   `on_click` 到 `_on_stop_run()` 之间**一个 `await` 都没有**，事件循环
        #   根本没机会跑那个启动任务 —— 于是"点了立刻取消"变成了"这一趟压根没开始"
        #   （没有文件夹可收拾，D14 因此假红）。真实用户不可能在同一个事件循环
        #   tick 里取消；加这一句之后它和"人手点两下"是同一件事。
        # [EN] ⚠⚠ **Let the launch really start before cancelling** (measured 2026-10-12): there is
        # [EN] **not a single `await`** between `on_click` and `_on_stop_run()` in the test code, so the
        # [EN] event loop never gets a chance to run the launch task -- "click then immediately cancel"
        # [EN] became "this pass never started" (no folder to tidy, hence D14 falsely red). A real user
        # [EN] cannot cancel within the same event-loop tick; with this line it becomes the same thing as
        # [EN] "a person clicking twice".
        await asyncio.sleep(0.8)
        ok('D10b ★★ 取消之前它**真的在装配**（运行文件夹已经建出来了 —— '
           '不然后面收拾的就是空气）',
           app._launch_phase == G.LAUNCH_STARTING
           and len(list(proj_root.glob('第*模拟*'))) > len(runs_before_e),
           f"phase={app._launch_phase} · {sorted(p.name for p in proj_root.glob('第*模拟*'))}")
        app._on_stop_run()                       # 启动中 ⇒ 这颗按钮就是「取消启动」
        # [EN] While starting, that button is exactly "Cancel launch"
        await asyncio.sleep(0.3)
        report['d_cancel'] = {'phase': app._launch_phase, 'msg': newest_msg(app),
                              'narr': narr_all(app)[:160]}
        ok('D11 ★★★ 按「取消启动」立刻停止等待（启动态放开、不用等到超时）',
           app._launch_phase == G.LAUNCH_IDLE, app._launch_phase)
        ok('D12 ★★★ 并且说的是"取消"这件事，不是"这一轮已经停了"（那时候那句是错的）',
           '取消' in narr_all(app), narr_all(app)[-160:])
        await asyncio.sleep(SLEEP_CANCEL + 3.0)
        runs_after_e = sorted(p.name for p in proj_root.glob('第*模拟*'))
        # 诊断：把"这一刻到底有什么"记进报告（口径可疑时先看它，别猜）
        # [EN] Diagnostic: record "what is actually there at this moment" in the report (look at it
        # [EN] first when a convention looks suspicious, don't guess)
        report['d_runs2'] = {
            'before': runs_before_e, 'after': runs_after_e,
            'listing': sorted(p.name for p in proj_root.iterdir()),
            'trash_new': sorted(trash_snapshot(tmp_projects) - trash_before_e),
            'phase': app._launch_phase, 'token': app._launch_token,
        }
        ok('D13 ★★★ 被取消的那一趟装好了也不接管（`self.session` 仍是停掉时的那个）',
           app.session is None or app.session.status == 'stopped',
           str(getattr(app.session, 'status', None)))
        _e_ok, _e_why = discarded_ok(proj_root, runs_before_e, trash_before_e,
                                     tmp_projects)
        ok('D14 ★★★ 被取消的那一趟同样被收拾掉了（搬走 / 或留了「已作废.md」）',
           _e_ok, f'{runs_before_e} → {runs_after_e}｜{_e_why}')

        # ── E. 失败可见 ──
        # [EN] -- E. Failures are visible --
        print('\n── E 组：装配失败要看得见 ──')
        SIM_SETUP.assemble = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError('装配故意失败（验证用）'))
        dlg3 = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.4)
        btn3 = find_btn(dlg3, '开始推演')
        btn3.on_click(None)
        failed = await _wait(lambda: app._launch_phase == G.LAUNCH_IDLE, 20)
        narr3 = narr_all(app)
        report['e_fail'] = {'narr': narr3[:200], 'msg': newest_msg(app)}
        ok('E1 ★★★ 装配失败后启动态也放开了（不会永远卡在"正在启动"）', failed,
           app._launch_phase)
        ok('E2 ★★★ 失败**留在了中栏**（"启动起笔失败但是界面看不到"是用户点名的假死）',
           '装配世界失败' in narr3 or '装配世界失败' in newest_msg(app), narr3[:120])
        ok('E3 ★★ 失败之后马上可以重来（可以再点「起笔」）',
           app.launch_busy() is False, str(app.launch_busy()))
        SIM_SETUP.assemble = real_assemble

        shot = await page.take_screenshot()
        if shot:
            (OUT / f'start_guard_timeout{SUFFIX}.png').write_bytes(shot)
        report['ok'] = all(o for _, o, _ in _checks)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        SIM_SETUP.assemble = real_assemble
        try:
            CFG.set('DEFAULT_PROJECTS_DIR', old_projects)
            if env_backup is not None:
                env_path.write_text(env_backup, encoding='utf-8')
                report['env_restored'] = True
        except Exception as e:                              # noqa: BLE001
            report['env_restore_error'] = str(e)
        try:
            VU.safe_rmtree(tmp_projects)
            report['cleaned'] = str(tmp_projects)
        except BaseException as e:                          # noqa: BLE001
            report['cleanup_error'] = str(e)
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUT / f'start_guard_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'起笔启动守卫验证：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        for n in failed:
            print('   ✗', n)
        print('=' * 62)
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    group_a()
    group_a_logic()
    if LOGIC_ONLY:
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUT / f'start_guard_logic_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'起笔启动守卫验证（仅逻辑）：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        for n in failed:
            print('   ✗', n)
        print('=' * 62)
        sys.exit(0 if not failed else 2)
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
