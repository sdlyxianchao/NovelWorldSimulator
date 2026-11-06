#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""界面自由度验证：**界面上写的，跟代码真的干的一样**。

★★★ 这一支守的是什么（2026-10-19 用户：「要在界面说清楚不同设置值的作用」）
--------------------------------------------------------------------------
"在界面说清楚"听起来是文案问题，其实是**一致性**问题。三处真相必须相同：

    ① `agent/freedom.py` 的阈值常量（真正决定行为的）
    ② `config.py` 的 `desc`（设置页里显示的那句）
    ③ `gui/app_flet.py` 的 `freedom_note_text()`（起笔对话框里随值变化的那段）

只要错一处，用户看到的就是**假说明**：拉到 50 以为"只少几个禁词"，
实际连思维链都少了一半（这个错 2026-10-19 真发生过，被 `verify_agent_freedom` 的 B2 抓到）。

所以这一支的核心不是"文案里有没有这个词"，而是：
  **拿 `freedom.py` 真跑一遍，看它在每个值上到底落在哪一档，
    再拿界面文案说的事去对。** 对不上就红。

⚠ 这也是为什么 `freedom_note_text` 必须是**模块级纯函数**：
  写在对话框的闭包里，判据调不到，只能退化成"源码里有没有这句话"——
  而那正是本项目明令禁止的判法（注释、`if False` 都能骗过）。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

_n = _bad = 0


def ok(desc: str, cond: bool, detail: str = '') -> None:
    global _n, _bad
    _n += 1
    if not cond:
        _bad += 1
    print(f"  {'✓' if cond else '✗'} {desc}" + (f"  — {detail}" if detail else ''))


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _at(task: float | None = None, style: float | None = None):
    from agent import freedom as F

    ot, os_ = F.task_level, F.style_level
    if task is not None:
        F.task_level = lambda: task
    if style is not None:
        F.style_level = lambda: style

    def restore() -> None:
        F.task_level, F.style_level = ot, os_

    return restore


# ══════════════════════════════════════════════════════════════
#  A. 三处真相一致（阈值常量）
# [EN] A. Three sources of truth agree (the constants)
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    from agent import freedom as F
    from gui.app_flet import FREEDOM_BAND_HIGH, FREEDOM_BAND_LOW

    ok('A1 ★★★ 界面的档位分界（35 / 65）与 `freedom.py` 的常量**完全一致**'
       '（不一致 = 界面写着一档、代码跑着另一档）',
       FREEDOM_BAND_LOW == round(F.TASK_AGENDA * 100)
       == round(F.STYLE_STRICT * 100)
       and FREEDOM_BAND_HIGH == round(F.TASK_BRIEF * 100) == round(F.STYLE_LOOSE * 100),
       f'界面 {FREEDOM_BAND_LOW}/{FREEDOM_BAND_HIGH} · '
       f'任务 {F.TASK_AGENDA * 100:.0f}/{F.TASK_BRIEF * 100:.0f} · '
       f'文笔 {F.STYLE_STRICT * 100:.0f}/{F.STYLE_LOOSE * 100:.0f}')

    cfg = _read('config.py')
    ok('A2 ★★ `config.py` 的两条 desc 都写明了三档（设置页里也能看懂）',
       cfg.count('低＝') >= 2 and '中＝' in cfg and '高＝' in cfg, '')
    ok('A3 ★★★ 而且旧键 `AGENT_FREEDOM` **不在 desc 里也不再是配置项**'
       '（留着它，用户会在设置页里调到一根断了的线）',
       '"AGENT_FREEDOM"' not in cfg, '')


# ══════════════════════════════════════════════════════════════
#  B. ★★★ 文案与**真实行为**对得上（真跑 freedom.py 去核）
# [EN] B. ★★★ The text matches **real behavior** (run freedom.py and compare)
# ══════════════════════════════════════════════════════════════
def group_b() -> None:
    from gui.app_flet import freedom_note_text

    def say(kind: str, v: int) -> str:
        return freedom_note_text(kind, v, tr=lambda s: s)

    # 三档取值：低 20 / 中 50 / 高 90
    lo_t, mid_t, hi_t = say('task', 20), say('task', 50), say('task', 90)
    ok('B1 ★★★ 任务三档的说明**互不相同**（三档写一样 = 等于没说明）',
       len({lo_t, mid_t, hi_t}) == 3, '')

    # ★ 核心：文案说的档位，必须等于 `freedom.py` 真跑出来的档位
    r = _at(task=0.20)
    try:
        scope_lo = F_scope = __import__('agent.freedom', fromlist=['x']).frame_scope()
    finally:
        r()
    r = _at(task=0.50)
    try:
        scope_mid = __import__('agent.freedom', fromlist=['x']).frame_scope()
    finally:
        r()
    r = _at(task=0.90)
    try:
        scope_hi = __import__('agent.freedom', fromlist=['x']).frame_scope()
    finally:
        r()

    ok('B2 ★★★ **低档文案说的正是代码真跑的档**（说"照剧本演"，代码就得是 full + 给分拍表）',
       '照剧本演' in lo_t and scope_lo == 'full', f'文案低档 / 代码 {scope_lo}')
    ok('B3 ★★★ **中档**：文案说"不给分拍表"，代码就得是 agenda（不是 full）',
       '不给分拍表' in mid_t and scope_mid == 'agenda', f'代码 {scope_mid}')
    ok('B4 ★★★ **高档**：文案说"连今天要演什么都不说"，代码就得是 brief',
       '只给议程' in hi_t and scope_hi == 'brief', f'代码 {scope_hi}')

    # 文笔三档
    lo_s, mid_s, hi_s = say('style', 20), say('style', 50), say('style', 90)
    ok('B5 ★★★ 文笔三档的说明**互不相同**', len({lo_s, mid_s, hi_s}) == 3, '')

    from agent import freedom as F

    def style_state(v: float) -> tuple[int, bool, bool, bool]:
        r2 = _at(style=v)
        try:
            return F.deai_items(8), F.distance_forced(), F.cot_full(), F.tic_quota()
        finally:
            r2()

    d_lo, d_mid, d_hi = style_state(0.2), style_state(0.5), style_state(0.9)
    ok('B6 ★★★ 文笔低档文案说"禁词全列"，代码就得真的是 base 条数',
       '禁词全列' in lo_s and d_lo[0] == 8, f'代码 {d_lo[0]} 条')
    ok('B7 ★★★ 文笔中档文案说"少列约四分之一"，代码就得真的少（但比松档多）',
       '少列约四分之一' in mid_s and d_lo[0] > d_mid[0] > d_hi[0],
       f'{d_lo[0]}/{d_mid[0]}/{d_hi[0]}')
    ok('B8 ★★★ 文笔松档文案说"距离由人物自己选 / 思维链只留一问 / 口癖配额关掉"，'
       '代码就必须三项都真的关掉',
       ('距离由人物自己选' in hi_s and '思维链只留一问' in hi_s and '口癖配额关掉' in hi_s)
       and (not d_hi[1] and not d_hi[2] and not d_hi[3]),
       f'距离{d_hi[1]} 思维链{d_hi[2]} 口癖{d_hi[3]}')


# ══════════════════════════════════════════════════════════════
#  C. 文案要说**后果**，并且把代价说出来
# [EN] C. The text states **consequences**, and names the cost
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    from gui.app_flet import freedom_note_text

    def say(kind: str, v: int) -> str:
        return freedom_note_text(kind, v, tr=lambda s: s)

    # 每一档都要说清"代价"——只说"更自由"不说"也会更散"就是骗人
    # [EN] Every band must state its **cost**; saying only "freer" is dishonest.
    ok('C1 ★★★ 任务低档说清代价（最稳，但"最不像他自己决定"）',
       '最稳' in say('task', 20), '')
    ok('C2 ★★★ 任务高档说清代价（"也最容易跑题或空转"）',
       '跑题' in say('task', 90) and '空转' in say('task', 90), '')
    ok('C3 ★★★ 文笔低档说清代价（"最容易写得**太规矩**"）',
       '太规矩' in say('style', 20), '')
    ok('C4 ★★★ 文笔松档说清代价（"也可能出现难看的句子"）',
       '难看' in say('style', 90), '')

    # 文案不许只说名字（"任务规训"这种），必须点到**具体机制**。
    # ⚠ 第一版判"每段都含'给'字" —— 太死：中档那句"禁词少列约四分之一"是完全合格的
    #   说明，只是没写"给"。改成"每段至少点到一件具体的东西"。
    # [EN] The text must name **concrete mechanisms**, not just the knob. ⚠ The first version
    # [EN] required the character "给" in every band -- too rigid: "banned words cut by a quarter"
    # [EN] is a perfectly good description without it. Now each band must name at least one
    # [EN] concrete thing.
    _concrete = ('剧本', '分拍表', '议程', '禁词', '距离', '思维链', '口癖')
    _bands = [(k, v) for k in ('task', 'style') for v in (20, 50, 90)]
    _bad = [(k, v) for k, v in _bands if not any(w in say(k, v) for w in _concrete)]
    ok('C5 ★★★ 六段文案**每段都点到具体机制**（剧本/分拍表/禁词/距离/思维链/口癖）'
       '—— 只重复旋钮名字等于没说明',
       not _bad, str(_bad) if _bad else '六段都具体')


# ══════════════════════════════════════════════════════════════
#  D. 真的挂进了起笔对话框（AST 判 body 与保存）
# [EN] D. Really wired into the start dialog (AST on body and save)
# ══════════════════════════════════════════════════════════════
def _dialog_fn() -> ast.AST | None:
    try:
        tree = ast.parse(_read('gui/app_flet.py'))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == 'show_start_story_dialog':
            return node
    return None


def group_d() -> None:
    fn = _dialog_fn()
    ok('D1 ★★ 找到了起笔对话框那个函数（找不到的话下面几条没有意义）',
       fn is not None, '')

    src = ast.unparse(fn) if fn is not None else ''
    ok('D2 ★★★ 两个滑块**都进了 body**（构造了却没挂上 = 用户看不见）',
       'task_free_sl' in src and 'style_free_sl' in src, '')

    # 判"进了 body"而不是"出现过"：body 是 `ft.Column([...])`，要看它在那个列表里
    in_body = False
    if fn is not None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and node.args:
                f = node.func
                name = getattr(f, 'attr', getattr(f, 'id', ''))
                if name in ('Column', 'ListView'):
                    txt = ast.unparse(node.args[0])
                    if 'task_free_sl' in txt and 'style_free_sl' in txt:
                        in_body = True
                        break
    ok('D3 ★★★ 而且是在**滚动容器的那个列表**里（不是构造完就扔在一边）',
       in_body, '')

    ok('D4 ★★★ 保存时**真的写进了配置**（只是显示、不保存 = 下次起笔又回到 50）',
       "CFG.set('TASK_FREEDOM'" in src and "CFG.set('STYLE_FREEDOM'" in src, '')

    ok('D5 ★★★ 拖动时说明会**实时更新**（`on_change` 挂上了）'
       '—— 挂不上的话，用户拖到 100 而说明还写着"照剧本演"，那比没有说明更糟',
       'on_change' in src and 'freedom_note_text' in src, '')

    ok('D6 ★★★ 界面上**明写了两个旋钮互不影响**（这是拆分的核心，不写用户不会知道）',
       '互不影响' in src, '')

    # ★★★ **作用域检查**：body 里引用的旋钮变量，必须在这个函数里**定义过**。
    #
    #   2026-10-19 真踩过：天机的变量名（`task_free_field`）被误挂进了**书斋**的
    #   body —— 书斋里只有 `task_free_p`。语法检查全绿，`ast.parse` 也全绿
    #   （那是一个合法名字），一开界面就 NameError。
    #   ⇒ 这一条比"有没有进 body"更硬：它同时要求"名字在这个作用域里存在"。
    #   ⚠ 只查名字前缀，不做完整的作用域分析（不值得）：这两个旋钮的变量名是
    #     这一支自己的约定，前缀对得上就够了。
    # [EN] ★★★ **Scope check**: every knob variable used in `body` must be **defined** in this
    # [EN] function. This was actually hit on 2026-10-19: a Tianji variable (`task_free_field`) was
    # [EN] wired into **Study**'s body, where only `task_free_p` exists -- `ast.parse` is happy (a
    # [EN] legal name) and the UI crashes with NameError. This check is harder than "is it in body".
    _refs: set[str] = set()
    _defs: set[str] = set()
    if fn is not None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Load) and re.match(
                        r'^(task_free|style_free|free_hint)', node.id):
                    _refs.add(node.id)
                elif isinstance(node.ctx, ast.Store):
                    _defs.add(node.id)
    _undef = sorted(_refs - _defs)
    ok('D7 ★★★ body 里用到的旋钮变量**都在本函数里定义过**'
       '（把天机的变量名挂进书斋 = 语法全绿、一开界面就 NameError）',
       not _undef, str(_undef) if _undef else f'{len(_refs)} 个变量都有定义')

    # ── 三个入口各查一次（起笔 / 天机 / 书斋）──
    #
    # ⚠⚠ 第一版只查了「起笔」和「天机」，**漏了书斋** —— 于是刚才那个真实的错
    #   （天机变量挂进书斋）在这条判据上**完全不红**。这是"三个入口只查两个"，
    #   而用户的原话是「在**项目**和每次推演起笔的时候」，项目那一个正是书斋。
    # [EN] ⚠⚠ The first version checked the Start dialog and Tianji but **missed Study** -- so the
    # [EN] real mistake above (a Tianji variable wired into Study) stayed green. Three entry points,
    # [EN] only two checked; the user asked for "**project** and each round's start".
    def _scope_of(fn_name: str) -> tuple[set[str], set[str], bool]:
        node = None
        try:
            for _n in ast.walk(ast.parse(_read('gui/app_flet.py'))):
                if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name == fn_name:
                    node = _n
                    break
        except SyntaxError:
            return set(), set(), False
        refs2: set[str] = set()
        defs2: set[str] = set()
        if node is not None:
            for n in ast.walk(node):
                if isinstance(n, ast.Name):
                    if isinstance(n.ctx, ast.Load) and re.match(
                            r'^(task_free|style_free|free_hint)', n.id):
                        refs2.add(n.id)
                    elif isinstance(n.ctx, ast.Store):
                        defs2.add(n.id)
        return refs2, defs2, node is not None

    for tag, fname in (('天机（全局设置）', 'show_global_settings'),
                       ('书斋（项目设置）', 'show_project_settings')):
        r2, d2, found = _scope_of(fname)
        ok(f'D8 ★★★ **{tag}里也有**，且旋钮变量都在本函数内定义'
           f'（用户要求"项目和起笔都能配"）',
           found and bool(r2) and not (r2 - d2),
           (str(sorted(r2 - d2)) if r2 else '（这里没有旋钮）') if found else '（函数没找到）')


# ══════════════════════════════════════════════════════════════
#  E. 文档：帮助与 README 都更新了
# [EN] E. Docs: help and README updated
# ══════════════════════════════════════════════════════════════
def group_e() -> None:
    manual = _read('使用说明.md')
    readme = _read('README.md')

    ok('E1 ★★★ 使用说明里有两个旋钮（用户真正会去查的地方）',
       'TASK_FREEDOM' in manual and 'STYLE_FREEDOM' in manual, '')
    ok('E2 ★★★ README 里也有（仓库首页看得到）',
       'TASK_FREEDOM' in readme or '任务规训' in readme, '')
    ok('E3 ★★★ 文档里**没有留下旧的 `AGENT_FREEDOM` 当主用法**'
       '（旧名字只在"已拆分"的说明里出现一次）',
       manual.count('AGENT_FREEDOM') <= 1, f"出现 {manual.count('AGENT_FREEDOM')} 次")
    ok('E4 ★★ 文档里写了世界法则（导演怎么定事件类型）',
       '世界法则' in manual or '压力' in manual, '')


def main() -> int:
    print('═' * 62)
    print('  界面自由度验证 · 界面上写的，跟代码真的干的一样')
    print('═' * 62)
    print('\n【A】三处真相一致')
    group_a()
    print('\n【B】★★★ 文案与真实行为对得上')
    group_b()
    print('\n【C】文案说后果，也说代价')
    group_c()
    print('\n【D】真的挂进了起笔对话框')
    group_d()
    print('\n【E】文档')
    group_e()
    print()
    print('═' * 62)
    print(f'界面自由度验证：{_n - _bad}/{_n} 通过')
    print('═' * 62)
    return 0 if _bad == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
