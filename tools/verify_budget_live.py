# -*- coding: utf-8 -*-
"""验证：左下角「系统」面板里的 token 用量是**活的**，且「导演 · 未启动」这一行去掉了。

用户 2026-10-12 原话
--------------------
「左下角的系统的Token预算左侧的数字要实时更新 然后导演这一样可以先去掉
  没有特别的意义」

两件事各自的坑
--------------
① **「Token 预算」那一行**以前写的是 `f"0 / {feat['budget']}"` —— 那个 `0` 是
   **硬编码**的，从建出来到关窗口一动不动，用户看到的就是永远
   「0 / 500000」，哪怕这一轮已经烧掉一半预算。所以判据要钉三件：
     · 数**从哪儿来**：`llm.ledger.today_tokens` —— 与「预算耗尽」的判定
       （`LLM.budget_exceeded()`）**同源**。两边各取一处就会出现
       "屏幕上显示已经超了、程序却照跑"（全局台账库里的量含别的进程）。
     · 数**会变**：账本涨了，屏幕上那一格跟着变。
     · 那个 `0` **不许回来**：AST 判"没有 `f"0 / …"` 这种硬编码"。
② **「导演 · 未启动」**：它只在"导演开着"时出现，而那正是**默认状态**；
   它既不说明导演在干什么，也不随推演变化 —— 白占一行（用户点名去掉）。
   ⚠ 导演**关掉**时那行「已关闭：导演」**留着** —— 那是在告诉用户
     "是你自己关的"，和这一行不是一回事。判据顺手钉住它，免得后人
     把两行一起删（真删了用户就"不知道自己关过什么"）。

判据分四组
----------
  A 数据层（纯逻辑，秒级）：显示串格式 / 只算今天 / 配色分档 / 拿不到账本不抛
  B 接线（AST，防退化）：没有硬编码 0；刷新函数真改控件；挂在 0.5 秒秒表上；
    句柄进了 `_ui_run['budget_text']`；「导演 · 未启动」在源码与词表里都消失
  C 真机（起窗口）：面板上显示的**真的是账本里的数**，且账本一变它就变
  D 判据自检：把显示串改回固定的 `0 / …`，C 组**必须红**（证明 C 不是形式）

跑法：
    .venv\\Scripts\\python.exe tools/verify_budget_live.py                # 全部
    .venv\\Scripts\\python.exe tools/verify_budget_live.py --logic-only   # 只跑 A/B
产出：assets/screenshots/budget_live_report.json（+ _logic_ 一份、截图两张）

English:
Verification: the token usage in the bottom-left "System" panel is **live**, and the row
"导演 · 未启动" is gone.
The user's words on 2026-10-12
--------------------
"the number to the left of Token budget in the bottom-left system panel must update in real time;
and the director row can go for now, it has no particular meaning"
The pitfall behind each of the two things
--------------
① **The "Token budget" row** used to read `f"0 / {feat['budget']}"` -- that `0` was
   **hardcoded**, motionless from creation to window close, so the user saw a permanent
   "0 / 500000" even after burning half the budget this round. So the criteria pin three things:
     · **Where the number comes from**: `llm.ledger.today_tokens` -- the **same source** as the
       "budget exhausted" decision (`LLM.budget_exceeded()`). Reading from two different places
       produces "the screen says already over while the program keeps running" (the global
       ledger DB also contains other processes' usage).
     · The number **actually changes**: when the ledger grows, that cell follows.
     · That `0` **must not come back**: an AST check that no hardcoded `f"0 / …"` remains.
② **"导演 · 未启动"**: it only appeared when the director was on, which is the **default** state;
   it said nothing about what the director was doing and never changed during a run -- a wasted
   row (the user named it for removal).
   ⚠ When the director is **off**, the row "已关闭：导演" **stays** -- that one tells the user
     "you turned it off yourself", a different thing from that row. The criteria pin it too, so
     that later edits don't delete both rows together (which would leave the user not knowing
     what they had turned off).
Criteria are in four groups
----------
  A data layer (pure logic, seconds): display string format / today only / color tiers / no throw
    when the ledger is unavailable
  B wiring (AST, against regressions): no hardcoded 0; the refresh really writes the control; it
    rides the 0.5-second stopwatch; the handle goes into `_ui_run['budget_text']`; "导演 · 未启动"
    is gone from both the source and the i18n table
  C real machine (window): the panel really shows **the ledger's number**, and it follows when
    the ledger changes
  D criterion self-check: put the display string back to a fixed `0 / …` and group C **must go
    red** (proving C is not a formality)
Usage:
    .venv\\Scripts\\python.exe tools/verify_budget_live.py                # everything
    .venv\\Scripts\\python.exe tools/verify_budget_live.py --logic-only   # A/B only
Output: assets/screenshots/budget_live_report.json (+ a _logic_ copy, two screenshots)
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                       # noqa: E402
import verify_ui_common as VU                           # noqa: E402
VU.redirect_env_writes()

from config import CFG                                  # noqa: E402
CFG.set('MOCK_LLM', 'true')
# 预算固定成一个整数：判据里的分母才确定（不然跟着用户 `.env` 变，
# 「期望值」每次都得重算，判据自己就成了漂的那一头）。
# [EN] Pin the budget to a fixed integer: the criterion's denominator is then determinate
# [EN] (otherwise it follows the user's `.env`, the expected value has to be recomputed every time,
# [EN] and the criterion itself becomes the drifting side).
CFG.set('TOKEN_BUDGET_PER_DAY', '500000')
VU.patch_flat_background()

from gui.app_flet import NovelWorldApp, C               # noqa: E402
from i18n import set_lang, t                            # noqa: E402
from llm.router import llm, UsageRecord                 # noqa: E402
from util.flet_shutdown import shutdown, exit_now       # noqa: E402

set_lang('zh')
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
LOGIC_ONLY = '--logic-only' in sys.argv
CAP = 500_000
report: dict = {'checks': []}
_checks: list[tuple[str, bool, str]] = []


def ok(name: str, cond, detail='') -> bool:
    _checks.append((name, bool(cond), str(detail)))
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _new_app() -> NovelWorldApp:
    """不起界面的**空壳实例**：这几个方法只读配置与账本，用不着 page。
    [EN] A **shell instance** that builds no UI: these methods only read config and the ledger,
    they don't need a page."""
    return NovelWorldApp.__new__(NovelWorldApp)


def _fake_tokens(n: int, *, ts: float | None = None) -> None:
    """往账本里塞一笔**假账** —— 只为看界面跟不跟。

    ⚠ **不要**用 `ledger.add()`：那个会**落进全局台账库**（`llm/usage.record`），
      判据的假账就变成用户账本里的脏数据。这里只 append 内存列表，
      进程一退就没了。
    [EN] Push one **fake entry** into the ledger -- only to watch whether the UI follows.
    [EN] ⚠ **Do not** use `ledger.add()`: that **writes into the global ledger DB**
    [EN] (`llm/usage.record`), turning the criterion's fake entry into dirty data in the user's
    [EN] ledger. Here we only append to the in-memory list, which disappears when the process exits.
    """
    llm.ledger.records.append(UsageRecord(
        ts=float(ts if ts is not None else time.time()), tier='front',
        model='verify_budget_live', purpose='verify', in_tok=int(n), out_tok=0,
        cost=0.0, latency_ms=1))


# ══════════════════════════════════════════════════════════════════════
#  A 数据层（纯逻辑）
# [EN] A Data layer (pure logic)
# ══════════════════════════════════════════════════════════════════════
def test_data() -> None:
    app = _new_app()
    base = app._budget_used()

    _fake_tokens(1234)
    ok('A1 ★★ 这一行写的是「**今天已用** / 每日上限」，已用跟着账本走',
       app._budget_line() == f'{base + 1234} / {CAP}',
       f'显示「{app._budget_line()}」，期望「{base + 1234} / {CAP}」')

    _fake_tokens(999999, ts=time.time() - 86400 * 3)
    ok('A2 ★ 只算**今天**（前天的账不进这个数 —— 它是"每日"预算）',
       app._budget_used() == base + 1234,
       f'{app._budget_used()}（期望 {base + 1234}）')

    need = max(0, CAP - app._budget_used())
    _fake_tokens(int(need * 0.9))
    ok('A3 ★ 过警告线（`TOKEN_WARN_AT`）转赭金 —— 与 `LLM._maybe_warn` 同一条线，'
       '不另立一个数',
       app._budget_color() == C['gold'], app._budget_color())
    _fake_tokens(need)
    ok('A4 ★★ 用满（≥ 上限）转朱砂', app._budget_color() == C['seal'],
       app._budget_color())

    real_cap = CFG.i('TOKEN_BUDGET_PER_DAY')
    try:
        CFG.set('TOKEN_BUDGET_PER_DAY', '0')
        got = app._budget_color()
    finally:
        CFG.set('TOKEN_BUDGET_PER_DAY', str(real_cap))
    ok('A5 上限为 0（没开预算）时不硬凑颜色（那一行本来就不出现）',
       got == C['text'], got)

    # 拿不到账本（替身 / 导入失败）时返回 0 且**不抛** —— 界面不该因为记账问题崩掉
    # [EN] When the ledger is unavailable (stand-in / import failure) return 0 and **do not
    # [EN] throw** -- the UI must not crash over bookkeeping.
    import gui.app_flet as AF
    real_llm = AF.llm
    try:
        # 替身：一个**没有 `.ledger`** 的对象
        # [EN] Stand-in: an object **without `.ledger`**
        AF.llm = object()
        got2 = app._budget_used()
    except Exception as e:                                   # noqa: BLE001
        got2 = f'抛了 {e!r}'
    finally:
        AF.llm = real_llm
    ok('A6 ★ 拿不到账本时返回 0 且不抛（"失败只记日志"，与 `llm/usage.record` 同一个道理）',
       got2 == 0, str(got2))


# ══════════════════════════════════════════════════════════════════════
#  B 接线（AST，防退化）
# [EN] B Wiring (AST, against regressions)
# ══════════════════════════════════════════════════════════════════════
def _methods(tree: ast.AST, cls_name: str) -> dict:
    """`{方法名: 节点}` —— 只看某个类**自己**的方法（不递归进别的类）。
    [EN] `{method name: node}` -- only a class's **own** methods (no recursion into other
    classes)."""
    out: dict = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[sub.name] = sub
    return out


def _str_hits(tree: ast.AST, needle: str) -> list[int]:
    """源码里所有**字符串常量**包含 `needle` 的行号（注释不算 —— 注释不在常量表里）。
    [EN] Line numbers of all **string constants** containing `needle` (comments don't count --
    they aren't in the constant table)."""
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and needle in n.value]


def test_wiring() -> None:
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = ast.parse(src)

    # ① 那个 `0` 不许回来：`f"0 / {…}"` 的特征 = JoinedStr 的第一段是以 `0 /` 开头的常量
    # [EN] ① That `0` must not come back: the signature of `f"0 / {…}"` is a JoinedStr whose
    # [EN] first piece is a constant starting with `0 /`
    hard = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.JoinedStr) and n.values
            and isinstance(n.values[0], ast.Constant)
            and isinstance(n.values[0].value, str)
            and n.values[0].value.strip().startswith('0 /')]
    ok('B1 ★★ 「Token 预算」不再写成硬编码的 `0 / …`（那个 0 就是"永远不动"的根源）',
       not hard, f'还在第 {hard} 行' if hard else '没有硬编码的 0')

    m = _methods(tree, 'NovelWorldApp')
    tick, ref = m.get('_start_status_ticker'), m.get('_refresh_sys_panel')
    ok('B2 找得到 `_refresh_sys_panel` 与 `_start_status_ticker`（判据不是空转）',
       ref is not None and tick is not None,
       f'刷新={"有" if ref is not None else "缺"}、秒表={"有" if tick is not None else "缺"}')
    if ref is None or tick is None:
        return

    # ⚠★ B3 要分清**稳态那一支**和**收工那一帧**：秒表里其实有两处调用 ——
    #   一处是每 0.5 秒的**稳态**（这一处才是"实时"），另一处在
    #   `if not (...is_alive):` 里，是**收工时补刷最后一帧**。
    #   只判"函数体里有没有这个词"的话，把稳态那一处删掉、留着收工那一处，
    #   判据照样绿 —— 而用户看到的正是"跑起来数字不动"。
    #   （第一版就是这么写的，反例法当场抓出来一条"漏掉"。）
    # [EN] ⚠★ B3 must separate the **steady-state branch** from the **wrap-up frame**: the stopwatch
    # [EN] actually has two calls --
    # [EN] one is the 0.5-second **steady state** (that one is what "real time" means), the other is
    # [EN] inside `if not (...is_alive):`, flushing the final frame **at wrap-up**.
    # [EN] Checking only "does this word appear in the function body" stays green when the
    # [EN] steady-state call is deleted and the wrap-up one remains -- and what the user sees is
    # [EN] exactly "the number doesn't move once it's running".
    # [EN] (The first version was written that way, and the counterexample method immediately caught
    # [EN] one "missed" case.)
    def _calls_in(node) -> list[int]:
        return [c.lineno for c in ast.walk(node)
                if isinstance(c, ast.Attribute) and c.attr == '_refresh_sys_panel']

    steady = _calls_in(tick)
    # 收工那一支：`if not (self.session and self.session.is_alive):`
    # [EN] The wrap-up branch: `if not (self.session and self.session.is_alive):`
    done_spans: list[tuple[int, int]] = []
    for n in ast.walk(tick):
        if isinstance(n, ast.If):
            tst = ast.unparse(n.test) if hasattr(ast, 'unparse') else ''
            if 'is_alive' in tst and 'not' in tst:
                lo = min(getattr(b, 'lineno', 10 ** 9) for b in n.body)
                hi = max(getattr(x, 'lineno', 0) for b in n.body for x in ast.walk(b))
                done_spans.append((lo, hi))
    wrap = [ln for ln in steady if any(lo <= ln <= hi for lo, hi in done_spans)]
    live = [ln for ln in steady if ln not in wrap]
    ok('B3 ★★ 刷新挂在 **0.5 秒的秒表**的**稳态那一支**上（`_start_status_ticker` 里调它）'
       '——数字要自己走，不能只在建界面时读一次',
       bool(live), f'稳态第 {live} 行；收工那一帧第 {wrap} 行' if live
       else f'只在收工那一帧刷（第 {wrap} 行）—— 跑起来数字照样不动')

    seg = ast.get_source_segment(src, ref) or ''
    ok('B4 ★★ 刷新函数真的**改控件**（`value` 与 `color` 都写）——'
       '防"函数写了、挂在秒表上了，却什么都不干"',
       'ctrl.value =' in seg and 'ctrl.color =' in seg,
       f'value={"ctrl.value =" in seg} color={"ctrl.color =" in seg}')

    assigns = [n.lineno for n in ast.walk(tree)
               if isinstance(n, ast.Assign)
               for tg in n.targets
               if isinstance(tg, ast.Subscript)
               and isinstance(tg.value, ast.Attribute) and tg.value.attr == '_ui_run'
               and isinstance(tg.slice, ast.Constant) and tg.slice.value == 'budget_text']
    ok('B5 ★ 面板建出来时把控件句柄存进 `_ui_run[\'budget_text\']`（不存就刷不到它）',
       bool(assigns), f'第 {assigns} 行' if assigns else '没存句柄')

    gui_hits = _str_hits(tree, '导演 · 未启动')
    i18n_tree = ast.parse((APP_DIR / 'i18n.py').read_text(encoding='utf-8'))
    i18n_hits = _str_hits(i18n_tree, '导演 · 未启动')
    ok('B6 ★★ 「导演 · 未启动」从界面代码与 i18n 词表里都**清掉了**'
       '（用户点名："没有特别的意义"）',
       not gui_hits and not i18n_hits, f'gui={gui_hits} i18n={i18n_hits}')

    # ⚠ 导演**关掉**那行是另一件事，不许跟着一起删
    # [EN] ⚠ The director-**off** row is a different thing and must not be deleted along with it
    keeps = False
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'append' and isinstance(n.func.value, ast.Name)
                and n.func.value.id == 'off' and n.args):
            a0 = n.args[0]
            if (isinstance(a0, ast.Call) and a0.args
                    and isinstance(a0.args[0], ast.Constant)
                    and a0.args[0].value == '导演'):
                keeps = True
    ok('B7 ★ 但**导演关掉**时那行「已关闭：导演」留着'
       '（那是在告诉用户"是你自己关的"，与上面那一行不是一回事）', keeps,
       '' if keeps else '`off.append(t(\'导演\'))` 不见了')


# ══════════════════════════════════════════════════════════════════════
#  C/D 真机：面板上真的是账本里的数，且账本一变它就变
# [EN] C/D Real machine: the panel really shows the ledger's number, and it follows when the
# [EN] ledger changes
# ══════════════════════════════════════════════════════════════════════
def _find_budget_ctrl(root):
    """「Token 预算」那一行的**值控件**（`mk_kv` 建的行 = 标签 + 撑开的垫片 + 值）。
    [EN] The **value control** of the "Token budget" row (a row built by `mk_kv` = label +
    [EN] expanding spacer + value)."""
    want = t('Token 预算')
    for c in VU.walk(root):
        if not isinstance(c, ft.Row):
            continue
        kids = [x for x in c.controls if isinstance(x, ft.Text)]
        if len(kids) >= 2 and VU.ctrl_text(kids[0]) == want:
            return kids[-1]
    return None


async def main(page: ft.Page) -> None:
    from store.project import Project

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp = Path(tempfile.mkdtemp(prefix='nws_budget_proj_'))
    # 项目落在**系统临时区**：真机这一段会真建项目、真落盘，不能脏了用户的 Projects
    # [EN] The project lands in the **system temp area**: this real-machine section really creates
    # [EN] a project and persists to disk, and must not dirty the user's Projects
    CFG.set('DEFAULT_PROJECTS_DIR', str(tmp))
    try:
        CFG.set('DIRECTOR_ENABLED', 'true')
        CFG.set('COMPLIANCE_ENABLED', 'true')
        proj_root = tmp / '预算实时验证'
        (proj_root / '设定集').mkdir(parents=True, exist_ok=True)
        proj = Project(proj_root, '预算实时验证')
        proj.write_nwsproj()
        app.current_project = proj

        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.9)

        ctrl = _find_budget_ctrl(page)
        ok('C1 找得到「Token 预算」那一行（判据不是空转）', ctrl is not None,
           '' if ctrl is not None else '运行界面里没有这一行')
        # ⚠ 这里**不许 `return`**：中途退出就再也走不到收尾的 `shutdown()`，
        #   窗口不关、`ft.run` 不返回，脚本会一直挂到被杀（看着像"跑得慢"）。
        # [EN] ⚠ **No `return` here**: bailing out mid-way means never reaching the closing
        # [EN] `shutdown()`, the window never closes, `ft.run` never returns, and the script hangs
        # [EN] until killed (which looks like "it's just slow").
        if ctrl is not None:
            (OUT / 'budget_live_panel.png').write_bytes(await page.take_screenshot())

            base = app._budget_used()
            _fake_tokens(1234)
            app._refresh_sys_panel()
            page.update()
            await asyncio.sleep(0.3)
            want1 = f'{base + 1234} / {CAP}'
            ok('C2 ★★ 面板上写的是**账本里的真数**（不是建界面那一刻的 0）',
               VU.ctrl_text(ctrl) == want1,
               f'屏幕上「{VU.ctrl_text(ctrl)}」，期望「{want1}」')

            same = _find_budget_ctrl(page)
            _fake_tokens(4444)
            app._refresh_sys_panel()
            page.update()
            await asyncio.sleep(0.3)
            want2 = f'{base + 1234 + 4444} / {CAP}'
            ok('C3 ★★ 账本再涨一点，**同一个控件**跟着变（"实时"就是这个意思）',
               same is ctrl and VU.ctrl_text(ctrl) == want2,
               f'同一控件={same is ctrl}；屏幕上「{VU.ctrl_text(ctrl)}」，'
               f'期望「{want2}」')

            joined = '\n'.join(VU.all_texts(page))
            ok('C4 ★ 「导演 · 未启动」在界面上**没有了**',
               '导演 · 未启动' not in joined,
               '' if '导演 · 未启动' not in joined else '那一行还在')

            CFG.set('DIRECTOR_ENABLED', 'false')
            app.show_main_screen()
            page.update()
            await asyncio.sleep(0.8)
            joined2 = '\n'.join(VU.all_texts(page))
            ok('C5 ★ 导演**关掉**时仍出现「已关闭：导演」（没把两件事一起删掉）',
               '已关闭：导演' in joined2, '')

            # ── D 判据自检：把显示串换回固定的 `0 / 上限`（改之前那种写法），C 必须红 ──
            # [EN] -- D criterion self-check: put the display string back to a fixed `0 / cap`
            # [EN] (the form before the change); C must go red --
            real_line = NovelWorldApp._budget_line
            try:
                NovelWorldApp._budget_line = lambda self: f'0 / {CAP}'
                _fake_tokens(7777)
                app._refresh_sys_panel()
                page.update()
                followed = VU.ctrl_text(ctrl) == \
                    f'{base + 1234 + 4444 + 7777} / {CAP}'
            finally:
                NovelWorldApp._budget_line = real_line
            ok('D1 ★ 判据自检：把显示串换回硬编码的 `0 / …`，C 组**会红**'
               '（这条判据不是形式）',
               not followed, '换回硬编码后数字**不跟账本走**了（C2/C3 那种断言当场红）'
               if not followed else '⚠ 换了硬编码它居然还跟着变，说明 C 组断言没咬住')
            app._refresh_sys_panel()
            page.update()
            await asyncio.sleep(0.2)
            (OUT / 'budget_live_panel_live.png').write_bytes(
                await page.take_screenshot())
    except Exception:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)

    # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
    #   把本协程取消掉，写在 `await shutdown(page)` 后面那行是**死代码**（退出码恒 0）。
    # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()`
    # [EN] throws CancelledError and cancels this coroutine, so anything after
    # [EN] `await shutdown(page)` is **dead code** (exit code always 0).
    await shutdown(page, code=_dump('budget_live_report.json', '预算实时'))


# ══════════════════════════════════════════════════════════════════════
#  收尾
# [EN] Wrap-up
# ══════════════════════════════════════════════════════════════════════
def _dump(name: str, title: str) -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / name).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                            encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  {title}：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    tmpdir = Path(tempfile.mkdtemp(prefix='nws_budgetlive_tmp_'))
    try:
        print('═' * 62)
        print('  验证：左下角「系统」面板里 token 用量是活的 + 导演那一行去掉')
        print('═' * 62)
        print('\n【A】数据层（纯逻辑）')
        test_data()
        print('\n【B】接线（AST，防退化）')
        test_wiring()
    except BaseException:                                    # noqa: BLE001
        report['logic_fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)
    finally:
        VU.safe_rmtree(tmpdir, ignore_errors=True)

    if LOGIC_ONLY:
        # ⚠ 退出码必须在 ft.run 之外落实（见 `util.flet_shutdown.shutdown()`）
        # [EN] ⚠ The exit code must be set outside `ft.run` (see `util.flet_shutdown.shutdown()`)
        exit_now(_dump('budget_live_logic_report.json', '预算实时（仅逻辑）'))
    else:
        try:
            # 正常路径的退出码由 `main` 里的 `shutdown()` 落（见那边的注释）
            # [EN] On the normal path the exit code is set by `shutdown()` inside `main` (see the
            # [EN] comment over there)
            ft.run(main)
        except Exception:                                    # noqa: BLE001
            report['fatal'] = traceback.format_exc()
            print(traceback.format_exc(), flush=True)
            exit_now(_dump('budget_live_report.json', '预算实时'))
