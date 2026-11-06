# -*- coding: utf-8 -*-
"""起笔起点验证：**「起笔」知道这一轮从哪儿开始**（2026-10-08）。

⚠ 名字刻意叫 `start_point` 而不是 `resume` —— 工具里已有
  `verify_resume_manage`（拾卷的删档/渲染）与 `verify_resume_menu`
  （开始界面菜单），那两支测的是**历史轮次的管理**；
  这一支测的是「点起笔那一刻，这一轮该从哪天哪个时辰起」。

用户原话（这段就是全部规格）：

    「运行窗口**起笔** 加一个逻辑 点击之后如果检查发现**一天的时间还没结束**
      （之前在一天没结束的时候点的停止）则**提示从某一天某个时间继续**，
      如果一天已经结束了，则**开启新一天**」

三件事要证：
  ① **判得准** —— 停点写的是"这一天演完没有"，不是猜的（`每天的生活/第N天.md`
     在不在推不出来：收尾会补落当天）；
  ② **接得上** —— 续跑时时钟真的从第 D 天那个时辰起（不是又从第 1 天 08:00 来）；
  ③ **不丢稿子** —— 上一轮第 D 天那份半截稿要**接着写**，不能被新一轮覆盖掉。

跑法：.venv\\Scripts\\python.exe tools/verify_start_point.py
产出：assets/screenshots/start_point_report.json

English:
跑法：.venv\\Scripts\\python.exe tools/verify_start_point.py
产出：assets/screenshots/start_point_report.json
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from util.flet_shutdown import exit_now                        # noqa: E402
from util.timefmt import GameTime                              # noqa: E402
import gui.app_flet as G                                       # noqa: E402
import sim.resume as RESUME                                    # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _calls(fn) -> list[tuple[int, str]]:
    """AST 里这个函数**调**了什么（行号，被调用的写成字符串）。**不看注释。**
        English:
    What this function in the AST **calls** (line numbers, called names written as strings). **Don't
    look at comments.**
    """
    out: list[tuple[int, str]] = []
    for n in ast.walk(ast.parse(_src(fn))):
        if isinstance(n, ast.Call):
            out.append((int(getattr(n, 'lineno', 0)), ast.unparse(n.func)))
    return out


# ══════════════════════════════════════════════════════════════════════
#  A —— 接线（源码 / AST）
# [EN] A —— Wiring (source / AST)
# ══════════════════════════════════════════════════════════════════════
def wiring_checks() -> None:
    print('\n── A 接线（源码 / AST）──')
    from sim.loop import RunLoop
    from sim import setup as SETUP
    from display.scene_builder import SceneBuilder

    # ★★★ 2026-10-21：**收尾被拆成了两个函数** —— `_finish` 现在只负责把整段收尾
    #   包进「正在做什么」的登记（`_DOING.push/pop`），实际做事的搬到了 `_finish_steps`。
    #   而 A1/A1b 还在 `RunLoop._finish` 里找 `_write_stop_point` ⇒ 命中 0 次 ⇒
    #   报「停点@-1 落盘@-1」，读起来像"停点功能没了"，实际它就在 `_finish_steps` 里
    #   且顺序正确（2328 停点 / 2331 `_end_day`）。
    #   ⇒ 判据**两个函数都看**（将来再拆一次也不会假红）。
    #   ⚠ 这类"代码拆完、判据锚点没跟着搬"是本项目的老毛病，
    #     症状统一是"红的方向不对"——它红的是判据自己过期了。
    # [EN] ★★★ 2026-10-21: **wrap-up was split in two** -- `_finish` now only wraps the whole
    # [EN] wrap-up in the "what am I doing" registration (`_DOING.push/pop`) while the real work moved
    # [EN] to `_finish_steps`. A1/A1b still looked for `_write_stop_point` inside `RunLoop._finish`
    # [EN] => zero hits => "stop@-1 flush@-1", which reads like "the stop-point feature is gone" when
    # [EN] it is right there in `_finish_steps` and in the correct order (2328 stop / 2331 `_end_day`).
    # [EN] => The criteria now look at **both functions** (so another split won't false-red them).
    # [EN] ⚠ "Code split, criterion anchor not moved with it" is a chronic issue here; the symptom is
    # [EN] always "red in the wrong direction" -- what went red is the stale criterion itself.
    fin_candidates = [RunLoop._finish, RunLoop._finish_steps] \
        if hasattr(RunLoop, '_finish_steps') else [RunLoop._finish]
    ok('A1 ★★★ 收尾时**真的记停点**（`_write_stop_point`，按 AST 判不看注释；'
       '`_finish` 与 `_finish_steps` 任一处调用即可）',
       any('_write_stop_point' in f
           for fn in fin_candidates for _ln, f in _calls(fn)), '')
    # ★★ 顺序是这条功能成立的前提：`_end_day()` 会把 `_ticks_today` 清零，
    #    排在它后面就永远判成"这一天演完了"。
    # [EN] ★★ The order is the precondition for this feature to hold: `_end_day()` will clear
    # [EN] `_ticks_today`,
    # [EN] if placed after it, it will always be judged as "this day's performance is over".
    # ⚠ 行号必须在**同一个函数**里比：两个函数各自从 1 开始数，
    #   跨函数比行号会得出"停点在前面"这种毫无意义的结论。
    # [EN] ⚠ Line numbers must be compared **within one function**: each starts at 1, and comparing
    # [EN] across functions yields a meaningless "the stop point comes first".
    ln_sp = ln_ed = -1
    for fn in fin_candidates:
        tree = ast.parse(_src(fn))
        _sp = min((int(n.lineno) for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and '_write_stop_point' in ast.unparse(n.func)), default=-1)
        _ed = min((int(n.lineno) for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and '_end_day' in ast.unparse(n.func)), default=-1)
        if _sp > 0 and _ed > 0:
            ln_sp, ln_ed = _sp, _ed
            break
    ok('A1b ★★★ 而且**排在 `_end_day()` 之前**（那一步会把 `_ticks_today` 清零 —— '
       '顺序反了永远判成"这一天演完了"）',
       ln_sp > 0 and ln_ed > 0 and ln_sp < ln_ed, f'停点@{ln_sp} 落盘@{ln_ed}')

    sp = _src(RunLoop._write_stop_point)
    ok('A2 ★★★ `day_done` 判的是 **`_ticks_today`**（"这一天演了一半"的判据，'
       '不是猜文件名）',
       '_ticks_today' in sp and 'day_done' in sp, '')
    # ★★★ 2026-10-23 **改口径**（守的写法被合理改了，不是产品坏）：
    #
    #   原来判的是源码里出现 `_ticks_today <= 0` 这个字面比较。它的**意图**是：
    #   "`_ticks_today` 从 0 起算 ⇒ 0 必须算'还没开演'，边界别判反"。
    #
    #   这轮为了让**中途落盘**能给出更准的答案（`_ticks_today` 是拍末才 +1 的，
    #   "第一拍正在写"与"一拍还没跑"在它上面一样），`_write_stop_point` 多了
    #   一个 `started` 参数，判定变成：
    #       `_begun = (self._ticks_today > 0) if started is None else bool(started)`
    #       `day_done = (not _begun)`
    #   语义一个字没变（`<= 0` ⇔ `not (> 0)`），只是形态从"比较符号"变成"显式布尔"。
    #   ⇒ 判据改成守**语义**：① 有 `_ticks_today > 0` 这个**严格大于**（0 不算开演）；
    #     ② `day_done` 是它的取反（不许写成 `day_done = _begun` 那种反的）。
    #   ⚠ 这仍然抓得住它该抓的：把 `> 0` 改成 `>= 0`（0 被当成开演）会当场红。
    # [EN] ★★★ 2026-10-23 **re-specified** (the form changed for a good reason, the product is not
    # [EN] broken). It used to require the literal `_ticks_today <= 0`. Its **intent**: "`_ticks_today`
    # [EN] starts at 0, so 0 must mean 'not started yet'; don't flip the boundary".
    # [EN] This round `_write_stop_point` gained a `started` parameter so the mid-progress flush can be
    # [EN] more accurate (`_ticks_today` only increments at the end of a beat, so "first beat in
    # [EN] progress" and "no beat yet" look identical), and the decision became
    # [EN] `_begun = (self._ticks_today > 0) if started is None else bool(started)` /
    # [EN] `day_done = (not _begun)`. The meaning is identical (`<= 0` <=> `not (> 0)`), only the form
    # [EN] changed from a comparison to an explicit boolean.
    # [EN] => Judge the **meaning**: ① a **strict** `_ticks_today > 0` (0 does not count as started);
    # [EN] ② `day_done` is its negation (not `day_done = _begun`). ⚠ Still catches what it should:
    # [EN] changing `> 0` to `>= 0` goes red on the spot.
    # ⚠ 比字符串时**两边都要去空格**：源码是 `day_done=(not _begun),`，
    #   只给左边 `replace(' ','')` 就等于拿"去过空格的"去找"没去空格的" —— 永远找不到。
    #   （第一版就这么写，判据当场红，而产品其实是对的。）
    # [EN] ⚠ Normalize **both sides**: the source is `day_done=(not _begun),`, so stripping spaces
    # [EN] only from the haystack means searching with a spaced needle -- never found. (The first
    # [EN] version did exactly that; the criterion went red while the product was correct.)
    _sp_nows = sp.replace(' ', '')
    ok('A2b ★★ `_ticks_today` 的边界按 **严格大于 0** 算（0 = 还没开演），'
       '且 `day_done` 是它的取反',
       '_ticks_today>0' in _sp_nows and 'day_done=(not_begun)' in _sp_nows,
       f'严格大于={"_ticks_today>0" in _sp_nows} '
       f'day_done 取反={"day_done=(not_begun)" in _sp_nows}')
    ok('A2c ★★ 停点整段套在 try 里（写不出来最多下次当"第一次"，'
       '**不许影响收尾**）',
       'except' in sp and 'write_stop_point' in sp, '')

    # 起点真的被用上（不是只在签名里挂个参数）
    # [EN] The starting point is actually used (not just a parameter hanging in the signature)
    bw = _src(SETUP.build_world)
    ok('A3 ★★★ `build_world` 真的把 `start_clock` 用进 `WorldState(clock=…)`'
       '（只收不用 = 假开关）',
       'start_clock' in bw and 'clock=(start_clock' in bw.replace(' ', ''), '')
    asm = _src(SETUP.assemble)
    ok('A3b ★★ `assemble` 把 `start_clock` **透传**给 `build_world`',
       'start_clock=start_clock' in asm.replace(' ', ''), '')
    ok('A3c ★★ `assemble` 把 `resume_scenes` **透传**给 `RunLoop`',
       'resume_scenes=resume_scenes' in asm.replace(' ', ''), '')

    ini = _src(RunLoop.__init__)
    ok('A4 ★★ `RunLoop` 收 `resume_scenes` 并存在实例上',
       'resume_scenes' in ini and '_resume_scenes' in ini, '')
    eb = _src(RunLoop._ensure_builder)
    ok('A4b ★★★ `_ensure_builder` 把它交给 `SceneBuilder(initial_scenes=…)`'
       '（收了不用的话，续跑照样把半截稿覆盖掉）',
       'initial_scenes=seed' in eb.replace(' ', ''), '')
    ok('A4c ★★★ 而且**用掉就清**（不清的话跨天之后新的一天会把昨天那几幕又挂上去）',
       '_resume_scenes = []' in eb, '')

    sb = _src(SceneBuilder.__init__)
    ok('A5 ★★★ `SceneBuilder` 收 `initial_scenes` 并放进 `_scenes`',
       'initial_scenes' in sb and 'list(initial_scenes or [])' in sb.replace('  ', ' '),
       '')
    # ★★ 2026-10-18 晚：判据跟上了重构。原来判"函数体里出现 `_said`"，
    #   而 `_said.add(...)` 早已**收敛到唯一写入口** `_remember_line`（见
    #   `display/scene_builder` 里那段"各写一遍是万恶之源"的注释）——
    #   于是这条判据在重构之后就一直是红的，红的不是产品，是判据没跟上。
    #   ⚠ 守的事情没变：**续跑要把"这个人已经说过的话"学回来**。
    # [EN] ★★ 2026-10-18 evening: the criterion follows the refactor. It used to look for `_said` in
    # [EN] the body, but `_said.add(...)` was consolidated into the single writer `_remember_line`
    # [EN] (see the "one place or nothing" comment in `display/scene_builder`) -- so this check had
    # [EN] been red since the refactor, and what was red was the criterion, not the product.
    # [EN] ⚠ What it guards is unchanged: a resume must learn back "what this person already said".
    ok('A5b ★★ 而且会从旧幕里**学回** `_known_cast` / 已说过的台词'
       '（判 `_remember_line` —— 台词记忆的唯一写入口；不学的话每个人再"入画"'
       '介绍一遍、说过的台词护栏外再说一次）',
       '_learn_from' in sb
       and '_known_cast' in _src(SceneBuilder._learn_from)
       and '_remember_line' in _src(SceneBuilder._learn_from), '')

    # 界面：提示块 + 真传参
    # [EN] Interface: prompt block + actually passing the parameter
    ok('A6 ★★★ 起笔对话框里有那块提示（`_mk_resume_notice`，按 AST 判不看注释）',
       any('_mk_resume_notice' in f for _ln, f in _calls(type(G.NovelWorldApp).__dict__.get(
           'show_start_story_dialog', G.NovelWorldApp.show_start_story_dialog))), '')
    sr = _src(G.NovelWorldApp._start_round)
    ok('A6b ★★★ 开跑时**真的按停点起**（`start_clock_of` + `load_resume_scenes`，'
       '不是只在对话框上写一行好看的字）',
       'start_clock_of' in sr and 'load_resume_scenes' in sr, '')
    # ★★ 「算出来不传 = 白算」：这两样必须真的进 `assemble(...)` 的实参里
    #    （反例法㉑㉒就是打这一处 —— 只改"传下去"那两行时，`start_clock_of`
    #     还在源码里，所以只有这一条抓得住）。走 AST 看关键字实参。
    # [EN] ★★ "Computed but not passed = wasted": these two things must actually go into the arguments of
    # [EN] `assemble(...)`
    # [EN] (Counter-example methods ㉑㉒ are exactly hitting this spot —— when only changing the two lines
    # [EN] that "pass it down", `start_clock_of`
    # [EN] is still in the source code, so only this one can catch it). Go through AST to look at keyword
    # [EN] arguments.
    def _hands_assemble(call: ast.Call) -> bool:
        """这个调用是不是"**给 `assemble` 递参数**"的那个。

        ★ 2026-10-12：装配现在交给 `asyncio.to_thread(assemble, …)` 去后台线程跑
          （界面不冻、超时看门狗才有机会跑），于是这个调用有两种形状：
            · 直接 `assemble(…)`；
            · 把 `assemble` 当**第一个实参**交出去（`to_thread(assemble, …)`）。
        ⚠ 放宽的是**形状**，不是要求：关键字仍然必须出现在**同一个调用**里
          —— ㉑㉒ 两条变异（把那一行删掉）照样红。
        [EN] Is this the call that **supplies `assemble` with its arguments**?
        [EN] ★ 2026-10-12: assembly is now handed to `asyncio.to_thread(assemble, ...)` to run on a
        [EN] background thread (so the UI does not freeze and the timeout watchdog gets its chance), so
        [EN] the call has two shapes:
        [EN]   · a direct `assemble(...)`;
        [EN]   · passing `assemble` as the **first positional argument** (`to_thread(assemble, ...)`).
        [EN] ⚠ What is relaxed is the **shape**, not the requirement: the keywords must still appear in
        [EN] the **same call** -- mutations ㉑㉒ (deleting that line) still go red.
        """
        if 'assemble' in ast.unparse(call.func):
            return True
        return bool(call.args) and isinstance(call.args[0], ast.Name) \
            and call.args[0].id == 'assemble'

    _kws: set[str] = set()
    for nd in ast.walk(ast.parse(sr)):
        if isinstance(nd, ast.Call) and _hands_assemble(nd):
            _kws |= {k.arg for k in nd.keywords if k.arg}
    ok('A6d ★★★ 算出来的两样**真的传进了装配**（`start_clock=` / '
       '`resume_scenes=` 都在实参里 —— 算了不传等于白算）',
       {'start_clock', 'resume_scenes'} <= _kws, str(sorted(_kws)))
    ok('A6c ★★ 界面查停点失败时**退回从头开始**、不抛（起笔是主操作，'
       '查询失败不该让按钮点不动）',
       'except' in _src(G.NovelWorldApp._resume_plan)
       and 'fresh' in _src(G.NovelWorldApp._resume_plan), '')

    # ★ 那个坑：Path.root 会把运行文件夹吃掉（在 autosave 踩过一次，别再踩）
    # [EN] ★ That pitfall: Path.root will swallow the run folder (stepped on it once in autosave, don't
    # [EN] step on it again)
    #
    # ⚠ 这一条**必须走 AST**：我在那两处**注释里**正写了这个反例
    #   （`Path(getattr(run, "root", run))`），按文本查会命中注释 ——
    #   第一版就是这么假红的（"判据被注释骗过"这条老坑又踩了一次）。
    # [EN] ⚠ This one **must go through AST**: I am literally writing this counter-example in those two
    # [EN] **comments**
    # [EN] (`Path(getattr(run, "root", run))`), searching by text will hit the comment ——
    # [EN] the first version was a false red like this (stepped on the old pitfall "criteria fooled by
    # [EN] comments" once again).
    def _uses_root_getattr(fn) -> bool:
        for nd in ast.walk(ast.parse(_src(fn))):
            if isinstance(nd, ast.Call) and ast.unparse(nd.func) == 'getattr':
                if "'root'" in ast.unparse(nd) or '"root"' in ast.unparse(nd):
                    return True
        return False

    ok('A7 ★★★ `sim/resume.py` 读写停点**不许**再取 `.root` 属性'
       '（`Path` 自带 `.root`，会把路径吃掉、写到盘根 —— autosave 踩过一次；'
       '按 AST 判，不看注释）',
       not _uses_root_getattr(RESUME.write_stop_point)
       and not _uses_root_getattr(RESUME.read_stop_point)
       and any('run_root' in f for _ln, f in _calls(RESUME.write_stop_point)),
       '')
    # ★★ 反例法K抓出来的：`read_stop_point` 改成会抛之后，`plan()` 整个崩 ——
    #    说明查停点这一层也得自己兜住（一次坏文件不该让「起笔」点不动）。
    # [EN] ★★ Caught by counter-example method K: after `read_stop_point` was changed to throw, `plan()`
    # [EN] completely crashed ——
    # [EN] this shows the stop-point lookup layer must also catch it itself (one bad file shouldn't make
    # [EN] the "start writing" button unclickable).
    ok('A7c ★★★ 查停点整段套在 try 里（一次坏文件不该把「起笔」顶住）',
       'except' in _src(RESUME.plan) and 'latest_run' in _src(RESUME.plan), '')
    from util.runpath import run_root
    ok('A7b 公共实现 `util/runpath.run_root` 判的是**类型**（PathLike 当路本身）',
       run_root(Path('x/y')) == Path('x/y'), str(run_root(Path('x/y'))))


# ══════════════════════════════════════════════════════════════════════
#  B —— 行为（无界面）
# [EN] B —— Behavior (no interface)
# ══════════════════════════════════════════════════════════════════════
class _Proj:
    """够用的假项目：`plan()` 只用 `list_runs()`。
        English:
    A sufficient fake project: `plan()` only uses `list_runs()`.
    """

    def __init__(self, runs: list):
        self._runs = list(runs)

    def list_runs(self):
        return list(self._runs)


def behavior_checks() -> None:
    print('\n── B 判定与取数（无界面，真跑）──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_resume_'))
    run = tmp / '项目' / '第1次模拟2026-10-08-10-00'
    run.mkdir(parents=True)

    # ── B1 没有停点 = 第一次 ──
    # [EN] ── B1 No stop point = first time ──
    p0 = RESUME.plan(_Proj([run]))
    ok('B1 ★★ 没有上一轮（或上一轮没留停点）→ `fresh`，起点第 1 天 08:00',
       p0['kind'] == RESUME.FRESH and p0['day'] == 1 and p0['minutes'] == 480,
       str(p0))

    # ── B2 ★★★ `Path` 进来也要写到**那个路径里**（不是盘根）──
    #    这是 `Path.root` 陷阱的行为级守卫：写法一退回去，文件就跑到盘根去了。
    # [EN] ── B2 ★★★ When a `Path` comes in, it must also be written to **that path** (not the drive root)
    # [EN] ──
    # [EN] This is the behavior-level guard for the `Path.root` trap: if the implementation regresses, the
    # [EN] file runs off to the drive root.
    r = RESUME.write_stop_point(run, day=3, minutes=19 * 60 + 30, calendar='第3天·戌时', shichen='戌时',
                                day_done=False, ticks_today=27, scene='临河茶肆',
                                reason='手动停止', partial_day=3)
    ok('B2 ★★★ 运行文件夹传一个 **`Path`** 进来时，停点写在**它里面**'
       '（`Path.root` 陷阱一退回去就会写到盘根去）',
       r.get('ok') is True and (run / RESUME.FILE).is_file(), str(r)[:90])
    ok('B2b 盘根下**没有**多出停点（真正的失败形态就是这样悄无声息）',
       not (Path(Path(run.anchor if run.anchor else '/') / RESUME.FILE)).is_file(),
       str(run.anchor))

    # ── B3 演了一半 → resume ──
    # [EN] ── B3 Half-performed → resume ──
    p1 = RESUME.plan(_Proj([run]))
    ok('B3 ★★★ 停点说"这一天演了一半"（`day_done=False`）→ `resume`，'
       '而且从**那天那个时辰**起',
       p1['kind'] == RESUME.RESUME and p1['day'] == 3
       and p1['minutes'] == 19 * 60 + 30 and p1['partial_day'] == 3, str(p1)[:120])
    clk = RESUME.start_clock_of(p1)
    ok('B3b ★★★ 翻出来的 `GameTime` 就是那一刻（第 3 天 戌时）',
       isinstance(clk, GameTime) and clk.day == 3
       and clk.minutes == 19 * 60 + 30, str(clk))

    # ── B4 演完了 → 开新的一天 ──
    # [EN] ── B4 Performance finished → start a new day ──
    RESUME.write_stop_point(run, day=4, minutes=8 * 60,
                            calendar='第4天·辰时', shichen='辰时',
                            day_done=True, ticks_today=0, scene='临河茶肆',
                            reason='定期暂停')
    p2 = RESUME.plan(_Proj([run]))
    ok('B4 ★★★ 停点说"这一天演完了"（`day_done=True`）→ `next_day`，'
       '起点是**新的一天 08:00**（不是接着昨天的时辰）',
       p2['kind'] == RESUME.NEXT_DAY and p2['day'] == 4
       and p2['minutes'] == 8 * 60 and p2['partial_day'] is None, str(p2)[:120])
    ok('B4b ★★ `next_day` 不给起点时钟的偏移（`start_clock_of` 仍然给得出那一天）',
       RESUME.start_clock_of(p2).day == 4, str(RESUME.start_clock_of(p2)))

    # ── B5 三种 kind 的说法**互不相同**（含糊成一件事用户就不知道演完没有）──
    # [EN] ── B5 The wording of the three kinds is **mutually distinct** (if blurred into one thing, the
    # [EN] user won't know whether the performance is over) ──
    texts = [RESUME.describe(x)[0] for x in
             (RESUME.plan(_Proj([])), p1, p2)]
    ok('B5 ★★★ 三种情况的说法**互不相同**（"接着演 / 开新的一天 / 从头开始" '
       '是三件事，含糊成一件用户就不知道上次演完没有）',
       len(set(texts)) == 3, str(texts))
    ok('B5b ★★ "接着演"那句里带**天数**（用户要的"从某一天某个时间继续"）',
       '第 3 天' in texts[1] and '戌时' in texts[1], texts[1])

    # ★★★ 探针当场抓出来的一个**真问题**：停点里的 `calendar` 是
    #   `world.clock_display()` 的**原样整串**（`第3天·戌时`），
    #   而那句话是 `第 {n} 天 · {时辰}` 拼的 —— 直接用就会说成
    #   「第 3 天 · 第3天·戌时」（天数讲两遍）。
    # [EN] ★★★ A **real problem** caught on the spot by the probe: in the stop point, `calendar` is
    # [EN] the **verbatim full string** of `world.clock_display()` (`第3天·戌时`),
    # [EN] and that sentence is assembled from `第 {n} 天 · {时辰}` —— using it directly would say
    #
    # ⚠ 数的时候要**把空格去掉**：整串那个形态是 `第3天`（无空格），
    #   而拼出来的那句是 `第 3 天`（有空格）—— 带空格数就漏掉了重复。
    #   （第一版就是这么放过了变异⑫b。）
    # [EN] ⚠ When counting, **remove the spaces**: the full-string form is `第3天` (no spaces),
    # [EN] while the assembled sentence is `第 3 天` (with spaces) —— counting with spaces would miss the
    # [EN] duplication.
    # [EN] (The first version let mutation ⑫b slip through like this.)
    _flat = (texts[1] + ' | ' + RESUME.describe(p1)[1]).replace(' ', '')
    ok('B5c ★★★ 那句话里"第N天"**只讲一遍**（拼 `calendar` 整串会说成'
       '"第 3 天 · 第3天·戌时" —— 真机探针打出来过）',
       _flat.count('第3天') == 1 and '戌时' in _flat, _flat[:120])
    ok('B5d ★★ 停点里两个字段各司其职（`shichen` = 纯时辰给提示拼；'
       '`calendar` = 原样整串备查）',
       p1['calendar'] == '戌时'
       and str((p1.get('stop') or {}).get('calendar') or '').startswith('第'),
       f"plan.calendar={p1['calendar']!r} / stop.calendar="
       f"{(p1.get('stop') or {}).get('calendar')!r}")

    # ── B6 停点坏了 / 不是 JSON → 当没有（不崩、不猜）──
    # [EN] ── B6 Stop point broken / not JSON → treat as absent (don't crash, don't guess) ──
    (run / RESUME.FILE).write_text('{坏掉的 json', encoding='utf-8')
    ok('B6 ★★ 停点文件坏了 → 当"没有上一轮"（`fresh`），**不抛、不猜**',
       RESUME.plan(_Proj([run]))['kind'] == RESUME.FRESH, '')
    (run / RESUME.FILE).write_text('{"day": 0}', encoding='utf-8')
    ok('B6b 停点里天数是 0 → 同样当没有（不产出一个"第 0 天"）',
       RESUME.plan(_Proj([run]))['kind'] == RESUME.FRESH, '')

    # ── B7 续跑要把那天的半截稿读回来 ──
    # [EN] ── B7 Resuming must read back that day's partial draft ──
    from display import script as S
    from display import script_render as SR
    RESUME.write_stop_point(run, day=3, minutes=19 * 60 + 30,
                            calendar='第3天·戌时', shichen='戌时',
                            day_done=False, ticks_today=27, scene='临河茶肆',
                            partial_day=3)
    # ⚠ cast 里放一个**只在 cast 里、不出声**的人（`周奉`）：
    #   这样"从旧幕学人名"就只有 cast 那一处会填他 —— 判据与反例法
    #   都能精确打到那一处（`主角` 会说台词，说话人那处也会填他）。
    # [EN] ⚠ Put in the cast a person who is **only in the cast and makes no sound** (`周奉`):
    # [EN] this way "learning names from old scenes" has only the cast spot that would fill him in ——
    # [EN] criteria and counter-example methods
    # [EN] can both hit that exact spot (`主角` speaks lines, so the speaker spot would also fill him in).
    sc = S.SceneScript(time_label='戌时 19:30', place='临河茶肆',
                       cast=['主角', '周奉'])
    sc.add(S.dialogue('主角', '账上的七文，谁记的？'))
    sc.add(S.action('主角', '把账本合上。'))
    # ⚠ 用**产品自己的落盘接口**写（`.md` + `.json` 两个都要）：
    #   `read_daily_script` 是先找 `.md`、再读同名 `.json` 的边车 ——
    #   只手写一个 `.json` 它会当作"这天没有稿子"（第一版就这么读回 0 幕）。
    # [EN] ⚠ Use **the product's own persistence interface** to write (both `.md` + `.json` are needed):
    # [EN] `read_daily_script` looks for `.md` first, then reads the sidecar `.json` of the same name ——
    # [EN] if you only hand-write a `.json`, it will treat it as "no script for this day" (the first
    # [EN] version read back 0 scenes like this).
    from store.runfolder import RunFolder as _RF
    _RF(run.parent, run.name).flush_daily_script(
        3, [sc], calendar_str='戌时', weather='雨', cast=['主角'])
    p3 = RESUME.plan(_Proj([run]))
    got = RESUME.load_resume_scenes(p3)
    ok('B7 ★★★ 续跑时把那一天的**半截正文**读回来了（不读的话收工落盘会整个覆盖它）',
       len(got) == 1 and len(got[0].entries) == 2,
       f'{len(got)} 幕 / {sum(len(s.entries) for s in got)} 条')
    ok('B7b ★★ 不是续跑时**不读**（`next_day` 不能把上一天的幕挂到新一天上）',
       RESUME.load_resume_scenes(p2) == [], str(RESUME.load_resume_scenes(p2))[:60])

    # ── B8 `SceneBuilder(initial_scenes=)` 真的把旧幕放前面、并学回记性 ──
    # [EN] ── B8 `SceneBuilder(initial_scenes=)` really puts old scenes in front and learns back the memory
    # [EN] ──
    from display.scene_builder import SceneBuilder
    from world.state import WorldState, PersonState
    w = WorldState(scene='临河茶肆')
    w.add_person(PersonState('主角', identity='账房', personality='话少'))
    w.place_names = ['临河茶肆']
    b = SceneBuilder(w, day=3, initial_scenes=got)
    ok('B8 ★★★ 旧幕排在**新幕前面**（收工落盘出来的是完整这一天）',
       len(b.scenes) == 1, f'{len(b.scenes)} 幕')
    ok('B8b ★★★ 旧幕里说过的话进了去重护栏（不学的话那句会被当成新的、'
       '再说一遍）',
       b.already_said('主角', '账上的七文，谁记的？') is True, '')
    ok('B8c ★★★ 旧幕里出现过的人进了 `_known_cast`（不学的话续跑第一拍'
       '会把每个人再"入画"介绍一遍）',
       '主角' in b._known_cast and '周奉' in b._known_cast,
       str(sorted(b._known_cast)))

    # ── B9 `build_world(start_clock=)` 真的把时钟设成那一刻 ──
    # [EN] ── B9 `build_world(start_clock=)` really sets the clock to that moment ──
    from sim.setup import build_world, load_settings
    # ⚠ 设定集**自己写文件再 `load_settings`**，别手拼一个 dict ——
    #   `load_settings` 的产物有二十几个键（`foreshadows` / `detail` / `map` …），
    #   手拼必缺，`build_world` 到一半就 KeyError（第一版就是这么崩的）。
    # [EN] ⚠ The settings bundle **writes the file itself and then `load_settings`**, don't hand-assemble a
    # [EN] dict ——
    # [EN] the output of `load_settings` has twenty-something keys (`foreshadows` / `detail` / `map` …),
    # [EN] hand-assembling will definitely miss some, and `build_world` will KeyError halfway through (the
    # [EN] first version crashed like this).
    sd = tmp / '设定集'
    sd.mkdir(parents=True, exist_ok=True)
    nl = chr(10)          # ⚠ 拼换行**别在字面量里写转义**（写坏过产品源码）
    # [EN] ⚠ When assembling newlines **don't write escapes in the literal** (wrote broken product source
    # [EN] code before)
    (sd / '人物.yaml').write_text(f'- 名称: 主角{nl}  身份: 账房{nl}',
                                  encoding='utf-8')
    (sd / '地点.yaml').write_text(f'- 名称: 临河茶肆{nl}  说明: 靠河{nl}',
                                  encoding='utf-8')
    (sd / '世界观.md').write_text(f'# 世界观{nl}{nl}临河镇靠一条河吃饭。{nl}',
                                  encoding='utf-8')
    settings = load_settings(sd)
    w2 = build_world(settings, start_clock=GameTime(day=3, minutes=19 * 60 + 30))
    ok('B9 ★★★ `build_world(start_clock=…)` 真的把世界的时钟设成那一刻'
       '（接了但不用 = 假开关）',
       w2.clock.day == 3 and w2.clock.minutes == 19 * 60 + 30, str(w2.clock))
    w3 = build_world(settings)
    ok('B9b ★★ 不给 `start_clock` 时照旧（第 1 天，`GAME_START_TIME` 那条路）',
       w3.clock.day == 1, str(w3.clock))

    # ── B10 `_ensure_builder` 只吃一次 seed ──
    # [EN] ── B10 `_ensure_builder` only consumes the seed once ──
    from sim.loop import RunLoop
    lp = RunLoop.__new__(RunLoop)
    lp.world = w
    lp.image_hook = None
    lp._builder = None
    lp._current_day = 3
    lp._resume_scenes = list(got)
    lp._last_clock = None
    lp._last_place = ''
    b1 = lp._ensure_builder()
    ok('B10 ★★★ 当天第一幕**吃掉了**那份 seed',
       len(b1.scenes) == 1 and lp._resume_scenes == [], '')
    lp._builder = None          # 模拟"跨天/重起幕"
    # [EN] Simulate "crossing days / restarting scenes"
    b2 = lp._ensure_builder()
    ok('B10b ★★ 重起幕时**不会**又把旧幕挂上去（seed 用掉就清）',
       len(b2.scenes) == 0, f'{len(b2.scenes)} 幕')


# ══════════════════════════════════════════════════════════════════════
#  C —— 端到端：收尾真写停点（跑一个最小 RunLoop）
# [EN] C —— End-to-end: the finale really writes the stop point (run a minimal RunLoop)
# ══════════════════════════════════════════════════════════════════════
async def finish_checks() -> None:
    print('\n── C 收尾真写停点（跑一次 `_finish`）──')
    from sim.loop import RunLoop

    def _mk(ticks_today: int, day: int = 3, minutes: int = 19 * 60 + 30):
        from world.state import WorldState, PersonState
        w = WorldState(scene='临河茶肆')
        w.add_person(PersonState('主角', identity='账房', personality='话少'))
        lp = RunLoop.__new__(RunLoop)
        lp.world = w
        lp.world.clock = GameTime(day=day, minutes=minutes)
        lp.world.game_day = day
        lp.agents = []
        lp.db = None
        lp._current_day = day
        lp._ticks_today = ticks_today
        lp._tick_no = 10
        lp._daily_narrative = []
        lp._running = False
        lp._builder = None
        # ⚠ `_script_mode` 是**只读属性**（读 `OUTPUT_FORMAT`），不能赋值：
        #   `lp._script_mode = False` 会抛 `AttributeError: property has no setter`
        #   —— 要它走"非剧本"那条路就改配置（`CFG.set`）。
        # [EN] ⚠ `_script_mode` is a **read-only property** (reads `OUTPUT_FORMAT`), it cannot be assigned:
        # [EN] `lp._script_mode = False` will throw `AttributeError: property has no setter`
        # [EN] —— if you want it to take the "non-script" path, change the config (`CFG.set`).
        CFG.set('OUTPUT_FORMAT', 'text')
        lp._resume_scenes = []
        lp._last_clock = None
        lp._last_place = ''
        lp._pending_round = None
        lp._push_divider = lambda *a, **k: None
        lp._push_narrative = lambda *a, **k: None
        lp._status = lambda *a, **k: None
        lp._warn_once = lambda *a, **k: None
        lp._on_crew_note = None
        lp._on_stage = None
        lp._on_note = None
        lp._on_work = None
        lp._on_scene = None
        lp._on_divider = None
        lp._on_narrative = None
        lp._on_status = None
        lp._on_state = None
        lp._on_branch = None
        lp._on_rollback = None
        lp._clock_segment = lambda: '戌时'
        # 收尾里那些"与本组无关"的重活**打桩**：这里只验停点
        # [EN] **Stub out** those heavy tasks in the finale that are "unrelated to this group": here only the
        # [EN] stop point is verified
        async def _noop(*a, **k):
            return None
        lp._end_day = _noop
        lp._auto_export = _noop
        lp._write_ending = _noop
        lp._will_auto_export = lambda: False
        return lp

    d = Path(tempfile.mkdtemp(prefix='nws_fin_'))
    lp = _mk(ticks_today=27)
    lp.runfolder = d
    await lp._finish('手动停止')
    sp = RESUME.read_stop_point(d)
    ok('C1 ★★★ 收尾跑完 → 停点真的写下来了',
       sp is not None, str(sp)[:110])
    ok('C1b ★★★ `day_done=False`（这一天跑了 27 拍就被停 —— 用户点名的那种）',
       bool(sp) and sp.get('day_done') is False and sp.get('partial_day') == 3,
       str(sp)[:110])
    ok('C1c ★★ 记下了**天 + 时辰 + 地点 + 跑了几拍**（提示方块上要摊给用户核对）',
       bool(sp) and sp.get('day') == 3 and sp.get('shichen') == '戌时'
       and sp.get('scene') == '临河茶肆' and sp.get('ticks_today') == 27,
       str(sp)[:110])
    # ⚠ 两个都要：`shichen` 给提示拼「第 3 天 · 戌时」，
    #   `calendar` 留**原样的时钟显示**（`第3天·戌时`）备查。
    #   只留后者的话提示会变成「第 3 天 · 第3天·戌时」（天数重复一遍）。
    # [EN] ⚠ Both are needed: `shichen` is for the prompt to assemble "第 3 天 · 戌时",
    # [EN] `calendar` keeps the **verbatim clock display** (`第3天·戌时`) for reference.
    # [EN] If only the latter is kept, the prompt becomes "第 3 天 · 第3天·戌时" (the day count is repeated
    # [EN] once).
    ok('C1d ★★ 同时还留了一份**原样的时钟显示**（`第N天·X`）备查',
       bool(sp) and str(sp.get('calendar') or '').count('第') == 1
       and '戌时' in str(sp.get('calendar') or ''), str(sp.get('calendar')))

    d2 = Path(tempfile.mkdtemp(prefix='nws_fin2_'))
    lp2 = _mk(ticks_today=0, day=4, minutes=8 * 60)
    lp2.runfolder = d2
    await lp2._finish('定期暂停')
    sp2 = RESUME.read_stop_point(d2)
    ok('C2 ★★★ 这一天**一拍都没跑**（上一次跨天已经收工）→ `day_done=True`、'
       '`partial_day=None` → 下一轮"开新的一天（第 4 天）"',
       bool(sp2) and sp2.get('day_done') is True
       and sp2.get('partial_day') is None and sp2.get('day') == 4, str(sp2)[:110])

    # ── C3 停点写在 `_end_day` **之前**（行为级：那一刻 `_ticks_today` 还在）──
    # [EN] ── C3 The stop point is written **before** `_end_day` (behavior-level: at that moment
    # [EN] `_ticks_today` is still there) ──
    seen: list[int] = []

    async def _end_day_spy(*a, **k):
        seen.append(int(lp3._ticks_today))
    d3 = Path(tempfile.mkdtemp(prefix='nws_fin3_'))
    lp3 = _mk(ticks_today=9)
    lp3.runfolder = d3
    lp3._end_day = _end_day_spy
    await lp3._finish('手动停止')
    ok('C3 ★★★ 记停点发生在 `_end_day` **之前**（跑到 `_end_day` 时 `_ticks_today` '
       '还是有值的 9 —— 顺序反了它会已经是 0，"演了一半"就判不出来）',
       seen == [9], str(seen))


# ══════════════════════════════════════════════════════════════════════
#  D —— **续跑要带上"上一轮说了什么、演到哪儿"**（2026-10-11）
# [EN] D —— **Resuming must carry "what was said last round, and how far the performance got"**
# [EN] (2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
# 用户原话：
#   「我每次运行 即使我是打开的某个存档 再次点击起笔，前情提要都一样
#     是不是推演进度没有被记录」
#   「运行界面 对话显示窗口也应该带着之前的记录 继续输出
#     现在是会清空 然后重新开始的样子」
# [EN] User's exact words:
# [EN] "Every time I run it, even if I opened some save, when I click start writing again, the recap is
# [EN] the same
# [EN] is the simulation progress not being recorded?"
# [EN] "The run interface's dialogue display window should also carry the previous records and continue
# [EN] outputting
# [EN] right now it seems to clear and then start over"
#
# 查下来的实情：**进度是记着的**（B 组那批判据一直绿着 —— 停点里有
# `day/minutes/ticks_today`，续跑也确实从那一刻接上）。缺的是**屏幕上两块料**：
# [EN] What the investigation found: **progress is recorded** (that batch of criteria in group B has
# [EN] stayed green —— the stop point has
# [EN] `day/minutes/ticks_today`, and resuming really picks up from that moment). What's missing is
# [EN] **the two pieces of material on screen**:
#
#   ① 中栏：`_start_round` 里一句 `self._live_lines = []` 把屏幕清了；
#   ② 前情提要：本轮是**新开的一轮**、`state.db` 是新的空库 ⇒
#      `recap_text()` 三级全落空，退到设定集的开场白 ⇒ 每轮念同一句。
# [EN] ① Middle column: a line `self._live_lines = []` in `_start_round` clears the screen;
# [EN] ② Recap: this round is a **newly started round**, `state.db` is a new empty database ⇒
# [EN] all three levels of `recap_text()` fall through, falling back to the settings bundle's opening
# [EN] line ⇒ the same sentence is read every round.
#
# 这一组把这两条钉住。也顺便钉住"顺序"那个 bug ——
# 原来"这一轮从哪儿开始"那条说明**先推、紧接着被清**，
# 所以连它自己都没显示出来过。
# [EN] This group pins down these two items. Also pins down the "order" bug ——
# [EN] originally the note "where this round starts" was **pushed first, then immediately cleared**,
# [EN] so even it itself was never displayed.
def resume_payload_checks() -> None:
    print('\n── D 续跑要带上上一轮（正文 / 前情 / 顺序）──')
    import tempfile
    from sim.loop import RunLoop
    from sim import setup as SETUP

    tmp = Path(tempfile.mkdtemp(prefix='nws_resume_payload_'))
    run = tmp / '项目' / '第1次模拟2026-10-11-09-00'
    (run / '每天的生活').mkdir(parents=True)
    (run / '自动落盘').mkdir(parents=True)
    body = ('# 第 1 天 · 第1天·辰时 · 晴\n'
            '> 在场：主角、柳氏\n'
            '\n'
            '## 辰时 08:00\n'
            '**场景** 临河茶肆\n'
            '\n'
            '▸ 出场 主角（已在场）\n'
            '\n'
            '· 动作 柳氏：把茶盏搁下\n'
            '\n'
            '主角：账本在楼上。\n'
            '\n'
            '柳氏：我上去拿。\n')
    (run / '每天的生活' / '第001天.md').write_text(body, encoding='utf-8')
    (run / '自动落盘' / '进度.md').write_text(
        '# 中途稿\n\n- 今天已演：12 条\n\n（中途稿的最后一句）\n', encoding='utf-8')
    RESUME.write_stop_point(run, day=1, minutes=8 * 60 + 54,
                            calendar='第1天·辰时', shichen='辰时',
                            day_done=False, ticks_today=12, scene='临河茶肆',
                            reason='手动停止', partial_day=1)
    p1 = RESUME.plan(_Proj([run]))
    ok('D0 前置：这个夹具是"当天演了一半"（`resume`）',
       p1['kind'] == RESUME.RESUME and p1['day'] == 1, str(p1)[:90])

    # ── D1 读得到上一轮那一天的正文字 ──
    # [EN] ── D1 Can read the main text of that day from the previous round ──
    prose = RESUME.load_prev_prose(p1)
    ok('D1 ★★★ 读得到**上一轮那一章的正文**（中栏要拿它当"之前的记录"）',
       '主角：账本在楼上。' in prose and '柳氏：我上去拿。' in prose,
       prose[:80].replace('\n', ' | '))
    ok('D1b ★★ 正文优先取**正式稿**（`每天的生活/第NNN天.md`），'
       '不是中途稿',
       '中途稿的最后一句' not in prose, prose[-40:].replace('\n', ' | '))
    ok('D1c ★★ 取的是**末尾**（故事的"最近"在后面 —— 续跑的人要知道'
       '"刚才演到哪儿"）',
       '第 1 天 · 第1天·辰时' not in prose[-120:] or '我上去拿' in prose[-40:],
       prose[-60:].replace('\n', ' | '))

    # ── D2 「上一回说到」是给人读的一句话，不是把剧本标记倒出来 ──
    # [EN] ── D2 "Last time, the story got to" is a human-readable sentence, not dumping script markers ──
    recap = RESUME.resume_recap(p1)
    ok('D2 ★★★ 续跑的前情提要 = **上一回说到**（不是设定集开场白 —— '
       '本轮 db 是空库，退到设定集就会"每轮念同一句"）',
       '上一回演到' in recap and '说到' in recap, recap[:110])
    ok('D2b ★★★ 而且写了**位置**（第几天 + 时辰 + 地点）—— '
       '作者一眼知道上一轮停在哪',
       '第 1 天' in recap and '辰时' in recap and '临河茶肆' in recap, recap[:70])
    ok('D2c ★★★ **抹掉了剧本的结构标记**（`▸ 出场` / `· 动作` / `**场景**`）'
       '—— 前情提要是给人读的一句话，倒一堆标记出来就是坏的',
       ('▸' not in recap and '· 动作' not in recap and '**' not in recap),
       recap[:120])
    ok('D2d ★★ 正文真的进了 recap（不是只有位置那一句）',
       '账本在楼上' in recap or '我上去拿' in recap, recap[-70:])

    # ── D3 接进 RunLoop：本轮开头用它，**且只用一次** ──
    # [EN] ── D3 Wired into RunLoop: use it at the start of this round, **and only once** ──
    #
    # ⚠⚠ **这一段必须是行为判据，不能是"源码里有没有这个字符串"** ——
    #   我第一版写成 `'_resume_recap' in _src(...)` 比行号，结果
    #   `if False: return self._resume_recap`（变异）照样满足，
    #   于是**变异没被抓到**（30 条里漏了 6 条，全是这一类）。
    #   字符串判还会被**注释**骗：注释里提一句 `self._live_lines = []`
    #   就等于"判据以为它还在"。
    # [EN] ⚠⚠ **This section must be a behavioral criterion, not "whether this string exists in the
    # [EN] source"** --
    # [EN] My first version was written as `'_resume_recap' in _src(...)`, comparing line numbers, and the
    # [EN] result was
    # [EN] `if False: return self._resume_recap` (mutation) still satisfies it,
    # [EN] so **the mutation was not caught** (6 out of 30 were missed, all of this kind).
    # [EN] String checks also get fooled by **comments**: a mention of `self._live_lines = []` in a comment
    # [EN] is enough for "the criterion to think it's still there".
    from display import script as _S2
    pushed: list = []
    _loop = RunLoop.__new__(RunLoop)
    _loop.db = None
    _loop.world = None
    _loop._push_narrative = lambda *a, **k: pushed.append(a)
    _loop._resume_recap = '上一回演到 第 1 天 · 辰时，说到：账本在楼上。'
    got = _loop._recap_text()
    ok('D3 ★★★ 本轮开头**真的用**「上一回说到」—— 判的是**返回值**，'
       '不是"源码里有没有这个字符串"（那个连 `if False:` 都能满足）',
       got == _loop._resume_recap and '账本在楼上' in got, got[:70])
    _loop._push_recap()
    ok('D3b ★★★ 用完**立刻清**（不清的话每个日界又把"上一回说到…"念一遍）'
       '—— 判"清没清"这个事实',
       _loop._resume_recap == '' and len(pushed) == 1,
       f"残留={_loop._resume_recap!r} / 推了 {len(pushed)} 条")
    ok('D3b2 ★★ 清掉之后**不再返回它**（回落到老路 —— 也就是本轮的摘要/设定集）',
       _loop._recap_text() != got, _loop._recap_text()[:60])

    # `assemble` 有没有把它交给 RunLoop —— 用 **AST 查实参**，不查字符串
    # [EN] Whether `assemble` hands it to RunLoop -- use **AST to check the actual argument**, not a string
    # [EN] check
    _asm = ast.parse(_src(SETUP.assemble))
    _kw = {k.arg for n in ast.walk(_asm) if isinstance(n, ast.Call)
           for k in n.keywords if k.arg}
    ok('D3c ★★★ `assemble` 把 `resume_recap` **当实参**交给 `RunLoop`'
       '（挂个签名参数不算交 —— 算了不传等于白算）',
       'resume_recap' in _kw, str(sorted(_kw))[:110])

    # ── D4 界面：顺序（先清/设，再推说明）──
    # [EN] -- D4 UI: order (clear/set first, then push the description) --
    #
    # ⚠ 按 **AST** 判：`_src()` 会把注释一起带进来，而那段注释里
    #   恰好写着 `self._live_lines = []` —— 按 `str.find` 找，
    #   变异把它删掉之后**注释里的那一处还在**，于是判据以为它还在（漏抓）。
    # [EN] ⚠ Judge by **AST**: `_src()` brings comments along too, and in that comment
    # [EN] it happens to say `self._live_lines = []` -- if you search with `str.find`,
    # [EN] after the mutation deletes it, **the occurrence in the comment is still there**, so the
    # [EN] criterion thinks it's still there (missed catch).
    _st = ast.parse(_src(G.NovelWorldApp._start_round))

    def _ln_of(pred, *, last: bool = False) -> int:
        ls = [int(n.lineno) for n in ast.walk(_st) if pred(n)]
        return (max(ls) if last else min(ls)) if ls else -1

    _ln_clear = _ln_of(lambda n: isinstance(n, ast.Assign) and any(
        isinstance(x, ast.Attribute) and x.attr == '_live_lines'
        for x in n.targets))
    _ln_prev = _ln_of(lambda n: isinstance(n, ast.Assign) and any(
        isinstance(x, ast.Attribute) and x.attr == '_prev_scenes'
        for x in n.targets))
    # ⚠ `RESUME.describe` 在这一段里**出现两次**：一次是写 `任务介绍.md`
    #   的快照（在前），一次才是推中栏那条说明 —— 取**最后一次**。
    # [EN] ⚠ `RESUME.describe` **appears twice** in this section: once is the snapshot that writes
    # [EN] `任务介绍.md`,
    # [EN] which comes first, and the second is the description pushed to the middle column -- take the
    # [EN] **last** occurrence.
    _ln_note = _ln_of(lambda n: isinstance(n, ast.Call)
                      and 'describe' in ast.unparse(n.func), last=True)
    ok('D4 ★★★ `_start_round` 里**先清中栏、再推"从哪儿开始"那条说明** —— '
       '反了那条说明会在出生后一行之内被清掉（这正是"屏幕上看不出从哪儿开始"'
       '的原因）。⚠ 判的是**语句行号**，注释里写一句不算',
       _ln_clear > 0 and _ln_note > _ln_clear,
       f'清空@{_ln_clear} 说明@{_ln_note}')
    ok('D4b ★★ 中栏的历史也是**在推说明之前**设好的（同一处口径）',
       _ln_prev > 0 and _ln_prev < _ln_note, f'历史@{_ln_prev} 说明@{_ln_note}')

    # ── D5 界面：中栏真的会把历史画出来 ──
    # [EN] -- D5 UI: the middle column really does draw the history --
    #
    # ⚠ 这里判的是**那个 if 的条件真的提到 `_prev_scenes`**（AST），
    #   不是"源码里有 `_prev_scenes` 这四个字" —— 后者变异成 `if False:` 照样满足。
    # [EN] ⚠ What's judged here is that **that if's condition really mentions `_prev_scenes`** (AST),
    # [EN] not "the source contains the four characters `_prev_scenes`" -- the latter is still satisfied
    # [EN] when mutated to `if False:`.
    _ms = ast.parse(_src(G.NovelWorldApp.show_main_screen))
    _cond_txt = ' '.join(
        ast.unparse(n.test) for n in ast.walk(_ms)
        if isinstance(n, ast.If) and '_prev_scenes' in ast.unparse(n.test))
    ok('D5 ★★★ 运行中重建中栏时**先渲染上一轮那段**（`_prev_scenes`）—— '
       '判的是那个 `if` 的**条件**，不是"源码里有没有这几个字"',
       bool(_cond_txt) and 'False' not in _cond_txt, _cond_txt[:90])
    ok('D5b ★★ 那段历史**前后各有一条分界**（不划线，作者会以为上面那些字'
       '是这一轮写的）',
       '_hist_divider' in _src(G.NovelWorldApp.show_main_screen)
       and 'closed=True' in _src(G.NovelWorldApp.show_main_screen), '')
    ok('D5c ★★★ 只在**起笔那一天之内**显示（跨天之后那段已经滚远了，'
       '再挂顶上会和本轮第 1 天看着像两份）',
       '_prev_for_day' in _cond_txt, _cond_txt[:90])

    # ── D6 分界那句在两种语言下都有词条 ──
    # [EN] -- D6: the boundary line has entries in both languages --
    from i18n import _ZH2EN
    ok('D6 ★★ 分界文案的中英**都登记了**（没登记时英文界面会漏出中文）',
       all(k in _ZH2EN for k in
           ('—— 以下是上一次演到这儿 ——',
            '—— 以下是上一次演到这儿（第 {n} 天）——',
            '—— 以上是上一次的记录 ——')), '')


async def main() -> None:
    try:
        wiring_checks()
        behavior_checks()
        resume_payload_checks()
        await finish_checks()
    except BaseException:                                       # noqa: BLE001
        ok('（验证执行中断）', False, traceback.format_exc()[-600:])
        print(traceback.format_exc()[-1800:])
    total = len(report['checks'])
    passed = sum(1 for c in report['checks'] if c['ok'])
    report.update({'total': total, 'passed': passed, 'ok': passed == total})
    (OUT / 'start_point_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n起笔起点验证：{passed}/{total}')
    exit_now(0 if passed == total else 2)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
