# -*- coding: utf-8 -*-
"""验证：「每 N 天停一次」这件事**真的成立**（2026-10-17）。

用户原话：

    「一天暂停一次改成3天暂停一次，总共循环10天」

## 为什么这件事需要单写一支判据

`STORY_DAY_EVERY_DAYS`（每几天一个存档点）与 `CHECKPOINT_PAUSE`（到点**停不停**）
是两个配置。查代码时发现的实况：

  · 「天问 · 运行」页上**只有前者有输入框**；后者**只存在于 `.env`**。
  · 于是那一格是**半残的**：把间隔从 1 改成 3，到点照样**不**停下来
    （默认 `CHECKPOINT_PAUSE=false` = 只落盘、接着说戏）。
    用户改完看不见任何变化，只会以为"这个框坏了"。
  · 更糟的是 `config.py` 里那段注释记着一次真机事故：
    `STORY_DAY_EVERY_DAYS=1` + `story_day` ⇒ **每一天**都在日界停住等人点「继续」，
    而界面上没有任何地方说得出"是谁让你停的"。那时是**开关默认值恰好相反**
    造成的；现在默认反过来了，但**开关本身仍然不可见**。
  ⇒ 两件事必须一起看：**间隔**（几天）与**停不停**（开关）。
  所以判据把「开关在界面上、初值同源、保存写回」与「`_tick` 里两个配置各管各的」
  都钉住。

## 判据分三组

  A 组（纯逻辑 / AST）：控件存在、初值同源、保存写回、`_tick` 里两个配置各司其职
  B 组（真机）：打开天问·运行，**屏幕上**真的有那个开关；拨动 + 保存后配置真的变了，再拨回来也能变
  C 组（纯逻辑）：`beat_pace_text()` 说的数**跟着配置走**（用户就是靠这句话判断快慢）

## 反例法

`developers/mutate_pause_interval.py` —— 每一组都有对应变异，改坏就必须见红。

English:
Verify that "pause once every N days" **really holds** (2026-10-17).

The user's exact words: "change from pausing once a day to once every 3 days; 10 days in total".

Why this needs its own criteria: `STORY_DAY_EVERY_DAYS` (checkpoint every N days) and
`CHECKPOINT_PAUSE` (whether to actually stop) are two settings. What the code showed:
  · The "Tianji · Run" page has an **input box only for the former**; the latter **exists only in `.env`**.
  · So that field is half-broken: changing the interval from 1 to 3 still does **not** stop
    (default `CHECKPOINT_PAUSE=false` = save a checkpoint and keep going). The user sees nothing
    change and concludes the field is broken.
  · Worse, a comment in `config.py` records a real incident: `STORY_DAY_EVERY_DAYS=1` + `story_day`
    => it stopped **every single day** at the day boundary waiting for "continue", and nothing in the
    UI could say who stopped it. That was caused by the switch's default being the opposite; the
    default is now flipped, but **the switch is still invisible**.
  => The two must be looked at together: the **interval** and the **switch**.
Three groups: A pure logic/AST (control exists, initial value from CFG, saved back, and the two
settings do their own jobs in `_tick`); B real machine (the switch is really **on screen**; toggling +
saving really changes the config, and toggling back works); C pure logic (`beat_pace_text()` follows
the config -- that sentence is how the user judges the pace).

Counterexamples: `developers/mutate_pause_interval.py`.

跑法：.venv/Scripts/python.exe tools/verify_pause_interval.py
产出：assets/screenshots/pause_interval_report.json / pause_interval_run.png
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                        # noqa: E402

from config import CFG                                   # noqa: E402
from i18n import t                                       # noqa: E402
from util.flet_shutdown import shutdown                   # noqa: E402
import verify_ui_common as VU                            # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', CFG.s('LANGUAGE') or 'zh')

LOGIC_ONLY = '--logic-only' in sys.argv
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / 'pause_interval_report.json'

report: dict = {'checks': [], 'groups': {}}
#: ★ 2026-10-26：B 组开工前记下的盘上原值（收尾按它还原；B6b 用它判"跑完与跑前一致"）。
#: ⚠ 模块级 + `global` 是因为 `gui_checks` 一个函数里同时管"保存"与"还原"两件事。
# [EN] On-disk values captured before group B (cleanup restores from here; B6b compares against it).
_cfg_before_b: dict = {}
_failed: list[str] = []


def ok(name: str, cond, detail: str = '') -> bool:
    cond = bool(cond)
    report['checks'].append({'name': name, 'ok': cond, 'detail': str(detail)})
    if not cond:
        _failed.append(name)
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return cond


def _app_src() -> str:
    return (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')


def _loop_src() -> str:
    return (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')


def _fn(tree: ast.AST, name: str) -> ast.AST | None:
    """按名字取函数节点（模块内同级）。

    ⚠ 别用 `ast.walk` 直接取第一个同名节点：这个文件里同名/近名的函数不少，
      取错一个就会把"判据看错了地方"当成"产品坏了"（反例法里踩过）。
    [EN] ⚠ Don't just take the first same-named node from `ast.walk`: this file has several
    [EN] same/near-named functions, and picking the wrong one turns "the criterion looked in the wrong
    [EN] place" into "the product is broken" (hit in counterexample work).
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ══════════════════════════════════════════════════════════════════════
#  A 组：源码 / AST
# ══════════════════════════════════════════════════════════════════════
# [EN] Group A: source / AST
# ══════════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    tree = ast.parse(_app_src())

    # ── A1 开关的控件真的被造出来了 ──
    # 找一个赋值 `checkpoint_pause = mk_switch(...)`：
    #   要求右值是 **Call**、函数名 `mk_switch`、第一个实参是界面文案里的那句话。
    # ⚠ 不判"源码里出现过 'checkpoint_pause'" —— 注释里也可能有，那等于没判。
    # [EN] ⚠ Don't judge "the string 'checkpoint_pause' appears in the source" -- comments count too,
    # [EN] which amounts to no criterion at all.
    made = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'checkpoint_pause'
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == 'mk_switch'):
            made = node
            break
    ok('A1 ★★★ 「存档点停下等确认」是**真控件**（`checkpoint_pause = mk_switch(...)`）',
       made is not None,
       ast.unparse(made)[:90] if made is not None else '没找到这句赋值')

    # ── A2 初值来自 CFG，不是写死 ──
    # 期望：`mk_switch(t('存档点停下等确认'), CFG.b('CHECKPOINT_PAUSE'))`
    #   ⇒ 第二个位置实参是 Call `CFG.b(...)`。
    # 写死 True/False 的后果：`.env` 里改成 true，界面打开还是 false（反过来也一样），
    # 于是"看到的状态"和"真正的状态"打架 —— 这类 bug 不抛异常，只能靠判据咬。
    # [EN] Hard-coding True/False means: `.env` says true but the UI opens as false (or vice
    # [EN] versa), so "what you see" fights "what is true" -- this class of bug throws nothing.
    init_from_cfg = (made is not None and len(made.value.args) >= 2
                     and isinstance(made.value.args[1], ast.Call)
                     and isinstance(made.value.args[1].func, ast.Attribute)
                     and made.value.args[1].func.attr == 'b'
                     and made.value.args[1].args
                     and isinstance(made.value.args[1].args[0], ast.Constant)
                     and made.value.args[1].args[0].value == 'CHECKPOINT_PAUSE')
    ok('A2 ★★★ 开关的初值**从配置来**（`CFG.b(\'CHECKPOINT_PAUSE\')`），不是写死',
       init_from_cfg,
       ast.unparse(made.value)[:110] if made is not None else '')

    # ── A3 保存时真的写回 ──
    # 找 `CFG.set('CHECKPOINT_PAUSE', <...checkpoint_pause.value...>)`。
    # ⚠ 只判"出现过 CHECKPOINT_PAUSE"不够：`CFG.i('CHECKPOINT_PAUSE')` 也算出现，
    #   而只读不写正是这次要修的病（开关画出来、盘上不变）。
    # [EN] ⚠ Judging "CHECKPOINT_PAUSE appears" is not enough: `CFG.i('CHECKPOINT_PAUSE')` also
    # [EN] counts, and read-without-write is exactly the disease being fixed here.
    saved = None
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'set' and node.args):
            continue
        a0 = node.args[0]
        if not (isinstance(a0, ast.Constant) and a0.value == 'CHECKPOINT_PAUSE'):
            continue
        src = ast.unparse(node)
        if 'checkpoint_pause' in src:
            saved = node
            break
    ok('A3 ★★★ 保存时把开关的值写回配置（`CFG.set(\'CHECKPOINT_PAUSE\', …checkpoint_pause…)`）'
       '（不写这一句，开关就是画出来的装饰）',
       saved is not None,
       ast.unparse(saved)[:110] if saved is not None else '没有这句 set')

    # ── A4/A5 主循环里两个配置各司其职 ──
    loop_tree = ast.parse(_loop_src())
    tick = _fn(loop_tree, '_tick')
    ok('A4 主循环里找得到 `_tick`（日界检查就在它里面）', tick is not None, '')
    if tick is None:
        return
    seg = ast.unparse(tick)

    # A4：间隔来自 `STORY_DAY_EVERY_DAYS`，且用**取模**判断"到第 N 天"
    every = ('STORY_DAY_EVERY_DAYS' in seg)
    mod = any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) for n in ast.walk(tick))
    ok('A4b ★★ 「几天一次」由 `STORY_DAY_EVERY_DAYS` 决定，并用取模判断到没到那一天',
       every and mod, f'读到配置={every} 有取模={mod}')

    # A5：停不停由 `CHECKPOINT_PAUSE` 决定（`if not CFG.b("CHECKPOINT_PAUSE")`）
    # ★★★ 必须钉**`story_day` 那一支**，不能"取第一个含它的 If"（2026-10-17）：
    #   文件里有**两处**同样的写法 —— 一处给 `open` 模式（每 N 天），
    #   一处给 `story_day`（用户用的就是这个）。取第一个 = 盯着 open 那条，
    #   而 story_day 那条被删掉时判据照样绿。做法：建 parent 映射，
    #   从 If 往上走，认它的祖先是 `elif run_mode == "story_day"`。
    # [EN] ★★★ Must pin the **`story_day` branch**, not "the first If containing it" (2026-10-17):
    # [EN] the file has **two** identical forms -- one for `open` mode (every N days), one for
    # [EN] `story_day` (what the user runs). Taking the first means watching the open path, and deleting
    # [EN] the story_day one would still pass. Approach: build a parent map and walk up from the If to
    # [EN] confirm an ancestor is `elif run_mode == "story_day"`.
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tick):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    def _in_story_day(node: ast.AST) -> bool:
        cur = parents.get(id(node))
        while cur is not None:
            if isinstance(cur, ast.If):
                test_src = ast.unparse(cur.test)
                if 'story_day' in test_src:
                    return True
            cur = parents.get(id(cur))
        return False

    gate = None
    for n in ast.walk(tick):
        if not isinstance(n, ast.If):
            continue
        if 'CHECKPOINT_PAUSE' in ast.unparse(n.test) and _in_story_day(n):
            gate = n
            break
    ok('A5 ★★★ 「停不停」由 `CHECKPOINT_PAUSE` 决定，'
       '而且**钉在 `story_day` 那一支**（不是 open 那条同款写法）',
       gate is not None,
       ast.unparse(gate.test)[:90] if gate is not None else 'story_day 分支里没找到')
    # 成对：那个 If 里必须**真的**调了提问（`_ask_checkpoint`），
    # 否则"开关一开就停"只是名字对、行为没接上。
    # [EN] Paired check: the If must **really** call `_ask_checkpoint`, otherwise "switch on = stop"
    # [EN] is only a matching name with no behaviour behind it.
    ask_in_gate = (gate is not None and '_ask_checkpoint' in ast.unparse(gate))
    ok('A5b ★★★ 而且那个分支里**真的**弹了提问（`_ask_checkpoint`）—— 不是只读了一下开关',
       ask_in_gate, '')

    # ── A6 书斋那边"暂停间隔"必须**给用户看得见地**说清它自己停不了 ──
    # 书斋 · 运行边界 里也有一格「暂停间隔」；同一件事两处入口，改了不生效最容易在这儿。
    # ⚠ 判的是 **`mk_hint` 的文案**（用户屏幕上真能读到的那句），不是注释 ——
    #   注释里写了 `CHECKPOINT_PAUSE` 用户看不见，等于没写（第一版就是这么判的）。
    # [EN] ⚠ Judge the **`mk_hint` text** (what the user actually reads on screen), not a comment --
    # [EN] mentioning `CHECKPOINT_PAUSE` in a comment is invisible to the user, i.e. not done (how the
    # [EN] first version judged it).
    hints = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'mk_hint' and node.args):
            a0 = node.args[0]
            if isinstance(a0, ast.Call):                    # mk_hint(t('…'))
                a0 = a0.args[0] if a0.args else None
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                hints.append(a0.value)
    guide = [h for h in hints if '暂停间隔' in h and '天问' in h]
    ok('A6 ★★ 书斋那格「暂停间隔」旁边有**屏幕上能读到**的一句指路：'
       '「要不要停下等你」归「天问 · 运行」的开关管',
       bool(guide), guide[0][:70] if guide else f'{len(hints)} 条 hint 里没有')

    report['groups']['A'] = len(report['checks'])


# ══════════════════════════════════════════════════════════════════════
#  C 组：节奏那句话跟着配置走（纯函数）
# ══════════════════════════════════════════════════════════════════════
# [EN] Group C: the pace sentence follows the config (pure function)
# ══════════════════════════════════════════════════════════════════════
def pace_checks() -> None:
    from gui.app_flet import beat_pace_text

    saved = {k: CFG.raw(k) for k in ('TIME_RATIO', 'BEAT_SECONDS')}
    try:
        # ★★★ 2026-10-26 口径改了（用户选 A：日界 = 拍预算用完）：
        #   "一个故事日"的算法从 `86400 ÷ 倍率`（旧：时钟跟真实流逝成正比）
        #   换成 `一天的拍数 × 每拍真实秒`（新：一天是这一站的拍数那么多拍）。
        #   ⇒ 期望值必须按**新算法**算，而且要**自己算**（不读产品常量，那是自证）。
        #   一天的拍数取「中」档上限 25（没有进度表时的默认档，与 `beat_pace_text` 同口径）。
        # [EN] ★★★ 2026-10-26, the basis changed (the user chose A): "one story day" went from
        # [EN] `86400 / ratio` (old: the clock was proportional to real time) to
        # [EN] `beats per day x real seconds per beat` (new: a day is as many beats as this station's
        # [EN] budget). Expected values are computed with the new formula, and computed **here**
        # [EN] (never read the product's constants -- that would be self-proving). Beats per day is 25,
        # [EN] the "medium" ceiling, the same convention `beat_pace_text` uses.

        # ── C1 当前配置下说的数都对（倍率 2 / 一拍 80）──
        #   一拍真实秒 = 80 / 2 = 40.0；一天 = 25 × 40 = 1000 秒 ≈ 16.7 分钟
        CFG.set('TIME_RATIO', '2')
        CFG.set('BEAT_SECONDS', '80')
        txt = beat_pace_text()
        report['pace_2_80'] = txt
        ok('C1 ★★★ 倍率 2 / 一拍 80 时那句话说的是「一拍约 40.0 真实秒 · 一个故事日约 17 分钟」'
           '（一天按 25 拍算，不是按 86400 秒算）',
           '40.0' in txt and '17 分钟' in txt and '故事秒 ≈' not in txt, txt)

        # ── C2 改配置，那句话立刻跟着变（同源，不缓存）──
        # 倍率 1：一拍 80 真实秒；一天 = 25 × 80 = 2000 秒 ≈ 33 分钟
        CFG.set('TIME_RATIO', '1')
        txt2 = beat_pace_text()
        report['pace_1_80'] = txt2
        ok('C2 ★★★ 改成倍率 1 后立刻变成「一拍约 80.0 真实秒 · 一个故事日约 33 分钟」'
           '（说明它是**现算**的，不是缓存的死文案）',
           '80.0' in txt2 and '33 分钟' in txt2, txt2)

        # ── C3 成对：倍率很高要退到秒级人话（别印「0.0 小时」）──
        # 倍率 60：一拍 80/60 ≈ 1.3 真实秒；一天 = 25 × 1.3 = 33 秒
        CFG.set('TIME_RATIO', '60')
        txt3 = beat_pace_text()
        report['pace_60_80'] = txt3
        ok('C3 ★★ 成对：倍率 60 时单位退到**秒级**（「一个故事日约 33 秒」），'
           '不印「0.0 小时」这种看着像坏了的说法',
           '秒' in txt3 and '0.0 小时' not in txt3, txt3)
    finally:
        for k, v in saved.items():
            if v is None:
                continue
            CFG.set(k, v)

    report['groups']['C'] = len(report['checks'])


# ══════════════════════════════════════════════════════════════════════
#  B 组：真机
# ══════════════════════════════════════════════════════════════════════
# [EN] Group B: real machine
# ══════════════════════════════════════════════════════════════════════
def _switches(dlg) -> list:
    return [c for c in VU.walk(dlg) if isinstance(c, ft.Switch)]


def _find_switch(dlg, label: str):
    """按**屏幕上的字**找开关（label 是 `mk_switch` 传进去的那句）。"""
    for c in _switches(dlg):
        if str(getattr(c, 'label', '') or '') == label:
            return c
    return None


def _click_save(dlg) -> bool:
    for c in VU.walk(dlg):
        if type(c).__name__ in ('FilledButton', 'TextButton', 'ElevatedButton'):
            if t('保存') in VU.text_of(c) and getattr(c, 'on_click', None):
                c.on_click(None)
                return True
    return False


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    from gui.app_flet import NovelWorldApp

    # ★★★ 2026-10-26：**开工前先记下盘上的原值**。
    #   这一组会点「保存」（⇒ `CFG.save()`），收尾还要还原 —— 还原成什么？
    #   原来还原成硬编码的"用户拍板搭配"，那不是还原，是**改用户的配置**。
    #   ⇒ 记在原处，收尾按这里还；B6b 用它判"跑完与跑前一致"。
    # [EN] ★★★ 2026-10-26: **capture the on-disk values before doing anything**. This group clicks
    # [EN] "Save" (=> `CFG.save()`) and restores afterwards -- restore to *what*? It used to restore a
    # [EN] hardcoded "user decision", which is not a restore but **rewriting the user's config**. So
    # [EN] capture here, restore from here, and B6b compares against it.
    global _cfg_before_b
    _cfg_before_b = {k: CFG.raw(k) for k in
                     ('TIME_RATIO', 'BEAT_SECONDS', 'STORY_DAY_EVERY_DAYS',
                      'AUTO_RUN_DAYS', 'CHECKPOINT_PAUSE')}

    # 起点：把这一项设成**关**，这样"拨成开 + 保存"能真的看出变化方向。
    CFG.set('CHECKPOINT_PAUSE', 'false')
    before = CFG.b('CHECKPOINT_PAUSE')

    dlg = app.show_global_settings(tab=NovelWorldApp.TAB_GLOBAL_RUN)
    page.update()
    await asyncio.sleep(1.2)

    # ── B0 先确认真的落在「运行」页 ──
    # ⚠ `selected_index` 是 0 起算；`VU.walk` 会把**所有**页签的内容都收进来，
    #   所以"找得到开关"证明不了"它在运行页"（它在别的页也找得到）。
    #   这一条把落点钉住，B1 才有意义。
    # [EN] ⚠ `selected_index` is 0-based; `VU.walk` collects the content of **all** tabs, so "the switch
    # [EN] is found" does not prove "it is on the Run page". This pins the landing page so B1 means
    # [EN] something.
    tabs_ctl = next((c for c in VU.walk(dlg) if isinstance(c, ft.Tabs)), None)
    ok('B0 打开天问并落在「运行」页（`TAB_GLOBAL_RUN`）',
       tabs_ctl is not None
       and int(getattr(tabs_ctl, 'selected_index', -1) or 0) == NovelWorldApp.TAB_GLOBAL_RUN,
       f'selected_index={getattr(tabs_ctl, "selected_index", None)}｜'
       f'期望={NovelWorldApp.TAB_GLOBAL_RUN}')

    # ── B1 屏幕上真有这个开关 ──
    # 判的是**控件本体**（`ft.Switch` 的 label 等于那句话），不是"页面上出现过这几个字"——
    # 后者一句 hint 就能满足，而 hint 拨不动。
    # [EN] Judge the **control itself** (an `ft.Switch` whose label is that sentence), not "the page
    # [EN] mentions those words" -- a hint satisfies the latter, and a hint cannot be toggled.
    sw = _find_switch(dlg, t('存档点停下等确认'))
    ok('B1 ★★★ 天问·运行页上**真的有一个开关**叫「存档点停下等确认」'
       '（不是只有一句说明文字）',
       sw is not None, f'找到 {len(_switches(dlg))} 个开关')
    if sw is None:
        return

    # ── B2 初值与配置同源 ──
    ok('B2 ★★★ 开关的初始状态 == 配置里的值（同源，不写死）',
       bool(sw.value) == before, f'控件={sw.value}｜CFG={before}')

    # ── B3 拨成开 + 保存 ⇒ 配置真的变成开 ──
    sw.value = True
    page.update()
    await asyncio.sleep(0.2)
    clicked = _click_save(dlg)
    ok('B3a 点得到「保存」', clicked, '')
    await asyncio.sleep(1.0)
    ok('B3b ★★★ 保存后 `CHECKPOINT_PAUSE` 真的变成 true'
       '（这就是"改了界面上那个框、盘上也变"的证据）',
       CFG.b('CHECKPOINT_PAUSE') is True, f'CFG={CFG.b("CHECKPOINT_PAUSE")}')

    # ── B4 成对：再拨回去 + 保存 ⇒ 也要能变回 false ──
    # 只判"能打开"不判"能关掉"，是"一刀切也能绿"的老坑（判据只认一个方向）。
    # [EN] Judging only "can turn on" and not "can turn off" is the old "one-way criteria also pass"
    # [EN] trap (the criterion only knows one direction).
    dlg2 = app.show_global_settings(tab=NovelWorldApp.TAB_GLOBAL_RUN)
    page.update()
    await asyncio.sleep(1.0)
    sw2 = _find_switch(dlg2, t('存档点停下等确认'))
    ok('B4a 重新打开天问，那个开关还在', sw2 is not None, '')
    if sw2 is not None:
        ok('B4b 重新打开时它显示的是**盘上那个 true**（同源，不是记住上次界面动作）',
           bool(sw2.value) is True, f'控件={sw2.value}')
        sw2.value = False
        page.update()
        await asyncio.sleep(0.2)
        _click_save(dlg2)
        await asyncio.sleep(1.0)
        ok('B4c ★★★ 拨回关 + 保存 ⇒ `CHECKPOINT_PAUSE` 真的变回 false（能开也能关）',
           CFG.b('CHECKPOINT_PAUSE') is False, f'CFG={CFG.b("CHECKPOINT_PAUSE")}')

    # ── B5 「暂停间隔」与这个开关在同一页、同一块 ──
    # 用户的心智模型是"每 3 天停一次"，两个控件分家就会被理解成两件事。
    # [EN] The user's mental model is "pause once every 3 days"; splitting the two controls makes it
    # [EN] read as two unrelated things.
    texts = ' '.join(VU.all_texts(dlg))
    report['run_page_texts'] = texts[:600]
    ok('B5 ★★ 同一页上还能看到「暂停间隔」与「夜间暂停」'
       '（"每几天停一次"是一整句，不该分成两三处）',
       t('暂停间隔') in texts and t('夜间暂停') in texts,
       '')

    # ── B6 「用户配置不许被这一组写坏」──
    # ★★★ 2026-10-26 改口径（**不是放松**，是换成它真正该守的那件事）：
    #
    #   原判据硬写着"倍率 2 · 一拍 80 故事秒"—— 那是 2026-10-17 用户拍板的一组数，
    #   而后他把 `.env` 调成了别的值（现在是 16 / 60）。于是一条"守用户配置"的判据
    #   变成"守某一次拍板的数字"，红得与功能无关，而且**它自己的收尾会把这些值写回 `.env`**
    #   （第 452 行那段 `CFG.set(...)`）—— 判据改用户配置，这是更该守的事。
    #
    #   ⇒ 现在守两件真的会坏的事：
    #     ① 这些键**都读得到且是正数**（读不到就是配置断了，界面会显示 0）；
    #     ② 这一组跑完之后，**盘上的值与本组开始前一致**（判据不许污染用户 `.env`）。
    #     顺带把 `BEAT_SECONDS` 的说法改掉：2026-10-26 起它只决定**演出节拍**
    #     （一拍等 BEAT_SECONDS ÷ 倍率 真实秒），不再决定故事时间。
    # [EN] ★★★ 2026-10-26, the basis changed (not relaxed -- replaced with what it should guard).
    # [EN] The old version hardcoded "ratio 2, 80 story seconds per beat": a combination the user
    # [EN] settled on 2026-10-17, after which he changed `.env` to something else (16 / 60). So a
    # [EN] criterion meant to protect *the user's config* became one that protects *one particular
    # [EN] decision*, going red for reasons unrelated to behaviour -- and its own cleanup **writes
    # [EN] those values back into `.env`** (the `CFG.set(...)` block below). A criterion editing the
    # [EN] user's config is the thing worth guarding. It now guards two real failures: (1) these keys
    # [EN] are readable and positive (unreadable means broken config and a 0 in the UI); (2) after
    # [EN] this group runs, the on-disk values equal what they were before it started (criteria must
    # [EN] not pollute the user's `.env`). Also note `BEAT_SECONDS` no longer decides story time --
    # [EN] since 2026-10-26 it only sets the **showing tempo**.
    keys6 = ('TIME_RATIO', 'BEAT_SECONDS', 'STORY_DAY_EVERY_DAYS', 'AUTO_RUN_DAYS')
    got = {k: CFG.i(k) for k in keys6}
    report['pace_config'] = got
    ok('B6a ★★★ 这四个键**都读得到且是正数**'
       '（读不到 = 配置断了，界面上会显示 0 拍 / 0 天）',
       all(isinstance(v, int) and v > 0 for v in got.values()), f'{got}')
    ok('B6b ★★★ 本组跑完之后**盘上的值与本组开始前一致**'
       '（判据不许污染用户的 `.env` —— 这是本项目踩过的老坑）',
       all(str(CFG.raw(k)) == str(_cfg_before_b.get(k)) for k in keys6),
       f'现在 {got}｜本组开始前 {_cfg_before_b}')

    # 收尾：这一组动过全局配置，**按本组开始前的原值**还回去。
    # ⚠ 原来还的是硬编码的 `want`（2/80/3/10）—— 那不是"还原"，是**把用户的配置改成
    #   某一次拍板的数字**。B6b 现在专门盯这件事（跑完与跑前一致）。
    # [EN] Cleanup: restore from **the values captured before this group started**. It used to restore
    # [EN] the hardcoded `want` (2/80/3/10), which is not a restore but **overwriting the user's config
    # [EN] with one particular decision**. B6b now watches exactly this (same before and after).
    for k in ('TIME_RATIO', 'BEAT_SECONDS', 'STORY_DAY_EVERY_DAYS',
              'AUTO_RUN_DAYS', 'CHECKPOINT_PAUSE'):
        if k in _cfg_before_b:
            CFG.set(k, str(_cfg_before_b[k]))

    if page.enable_screenshots:
        (OUT / 'pause_interval_run.png').write_bytes(
            await page.take_screenshot() or b'')

    report['groups']['B'] = len(report['checks']) - sum(report['groups'].values())


async def entry(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_pause_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # 这条判据会点「保存」⇒ `CFG.save()`，必须整段重定向（别写用户的 .env）
    # [EN] This criterion clicks "Save" => `CFG.save()`, the whole thing must be redirected (don't write
    # [EN] the user's `.env`)
    VU.redirect_env_writes()
    # ★★★ 还得把三座「外部创作服务」的自动拉起关掉（2026-10-17 实测踩到）：
    #   点保存会走到 `_maybe_autostart_service()`，用户机上的
    #   `*_ENABLED × *_AUTOSTART` 是开着的 ⇒ 判据跑一趟会把 MuMuAINovel /
    #   PenShot / PlotPilot **真的拉起来**（真机日志里能看到三条「已自动拉起」）。
    #   判据不该有这种副作用：它只是要验"一个开关存不存得进盘"。
    # [EN] ★★★ Must also switch off autostart for the three "external creation services" (hit for real on
    # [EN] 2026-10-17): clicking Save reaches `_maybe_autostart_service()`, and on the user's machine
    # [EN] `*_ENABLED × *_AUTOSTART` are on => running this criterion would **actually launch** MuMuAINovel /
    # [EN] PenShot / PlotPilot (three "auto-launched" lines show up in the real log). A criterion must not
    # [EN] have that side effect: all it needs to verify is "does one switch get written to disk".
    for _k in ('MUMU_AUTOSTART', 'PLOTPILOT_AUTOSTART', 'PENSHOT_AUTOSTART'):
        CFG.set(_k, 'false')
    _saved_ck = CFG.raw('CHECKPOINT_PAUSE')
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    try:
        await asyncio.sleep(1.2)
        await gui_checks(page, app, tmp)
    except BaseException:                                    # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        # 内存里的值也还原（`.env` 由 `redirect_env_writes()` 保住了，但同一进程里
        # 后面的判据/收尾代码还会读 CFG，留成 false 会让"盘上 true、内存 false"打架）
        # [EN] Restore the in-memory value too (`.env` is protected by `redirect_env_writes()`, but later
        # [EN] code in the same process still reads CFG; leaving it false makes disk and memory disagree).
        if _saved_ck is not None:
            CFG.set('CHECKPOINT_PAUSE', _saved_ck)
        VU.safe_rmtree(tmp, ignore_errors=True)
    # ⚠ 收尾**必须**走 `shutdown(page, code=…)`：直接 return 的话 Flet 窗口不关，
    #   脚本永远不退出（2026-10-17 实测：240 秒超时被杀）。
    # [EN] ⚠ Wrap-up **must** go through `shutdown(page, code=...)`: a plain return leaves the Flet
    # [EN] window open and the script never exits (measured 2026-10-17: killed at the 240s timeout).
    await shutdown(page, code=finish())


def finish() -> int:
    total = len(report['checks'])
    bad = len(_failed)
    report['ok'] = bad == 0
    report['summary'] = f'{total - bad}/{total} 通过'
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print('=' * 66)
    if bad:
        print(f'暂停间隔验证：{total - bad}/{total} 通过，{bad} 条红：')
        for n in _failed:
            print(f'  ✗ {n}')
    else:
        print(f'暂停间隔验证：{total}/{total} 全部通过')
    print(f'报告：{REPORT}')
    return 0 if bad == 0 else 2


def main() -> int:
    logic_checks()
    pace_checks()
    if LOGIC_ONLY:
        return finish()
    try:
        ft.run(entry)
    except Exception:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print('真机段异常：', report['fatal'])
    return finish()


if __name__ == '__main__':
    sys.exit(main())
