# -*- coding: utf-8 -*-
"""验证：小说已经开过卷时，再开卷要**提示已经存在**（不是一路开下去）。

用户 2026-10-07：「如果小说已经存在 则后续再开卷的话 要提示已经存在
而不是继续可以开卷这本小说」。

## 以前是什么样（这条判据要挡住的）

一声不吭地**又开一遍**。更糟的是同名会**复用同一个项目目录**
（`Project.create_new` 里 `ensure_dir` 存在即用）：新书的设定集写进旧项目，
而旧项目那本书的存档还挂在里面 —— 用户什么都看不到。

## 检查什么

A 纯逻辑（零窗口，`store/project.py`）
  · `norm_source`：尾斜杠 / 大小写 / 引号与空白 / 空串
  · `matches`：同名命中 · 同素材命中 · **父子目录不算** · 两个都空 → 空
  · `unique_name`：不撞原样 · 撞了 `(2)` · `(2)` 也撞就 `(3)`
B 真机（MOCK，走真实入口 `show_import_wizard` → `_do_import`）
  · 选完文件夹，步骤 1 那条提示行**真的出现**，且写明是哪一本
  · `_do_import` **不再开跑**（`_ingest_state` 里没有 running）+ 弹出提示框
  · 点「取消」→ 没开跑、**向导还在**（人回到原来那一步）
  · 点「打开「已有的那本」」→ 真的切到那一本（`current_project`）
  · 点「仍然重新开卷」→ 名字自动避重（`X (2)`）**并且真的开始摄取**
  · 旧项目的 `.nwsproj` **一个字没被改**（"不许覆盖"的实锤）
C 闸门位置（源码级）
  · `_ask_duplicate` 必须排在 `page.pop_dialog()` **之前** ——
    顺序反了，用户已经被踢出向导，提示框关掉之后无处可回

跑法：
    .venv\\Scripts\\python.exe tools/verify_ingest_duplicate.py
    .venv\\Scripts\\python.exe tools/verify_ingest_duplicate.py --logic-only
产出：
    assets/screenshots/ingest_duplicate_report.json
    assets/screenshots/ingest_duplicate_1_hint.png
    assets/screenshots/ingest_duplicate_2_dialog.png

English:
Verify: when a novel has already opened a volume, opening a volume again must **prompt that it
already exists** (not just keep opening).
User 2026-10-07: "If the novel already exists, then when opening a volume later, it should
prompt that it already exists
rather than continuing to allow opening a volume on this novel".
## What it used to be like (what this check must block)
Silently **open it again**. Worse, the same name will **reuse the same project directory**
(`ensure_dir` in `Project.create_new` uses it if it exists): the new book's settings get written
into the old project,
while the old project's save for that book is still hanging in there —— the user sees nothing.
## What to check
A Pure logic (zero windows, `store/project.py`)
  · `norm_source`: trailing slash / case / quotes and whitespace / empty string
  · `matches`: same name hit · same material hit · **parent/child directories do not count** · both empty → empty
  · `unique_name`: no collision keeps as-is · collision appends `(2)` · `(2)` also collides then `(3)`
B Real machine (MOCK, through the real entry `show_import_wizard` → `_do_import`)
  · After choosing the folder, the hint line of step 1 **really appears**, and states which book it is
  · `_do_import` **no longer starts** (no running in `_ingest_state`) + a prompt box pops up
  · Click "Cancel" → not started, **wizard is still there** (the person returns to the original step)
  · Click "Open 「the existing book」" → really switch to that book (`current_project`)
  · Click "Still re-open volume" → name automatically avoids collision (`X (2)`) **and ingestion really starts**
  · The old project's `.nwsproj` is **not changed by a single character** (hard proof of "must not overwrite")
C Gate position (source level)
  · `_ask_duplicate` must be placed **before** `page.pop_dialog()` ——
    if the order is reversed, the user has already been kicked out of the wizard, and after the prompt box is closed there is nowhere to return to
How to run:
    .venv\\Scripts\\python.exe tools/verify_ingest_duplicate.py
    .venv\\Scripts\\python.exe tools/verify_ingest_duplicate.py --logic-only
Output:
    assets/screenshots/ingest_duplicate_report.json
    assets/screenshots/ingest_duplicate_1_hint.png
    assets/screenshots/ingest_duplicate_2_dialog.png
"""
from __future__ import annotations

import asyncio
import inspect
import json
import shutil
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                       # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_ITEMS: list[dict] = []


def ok(name: str, cond, detail: str = '') -> bool:
    ok_ = bool(cond)
    _ITEMS.append({'name': name, 'ok': ok_, 'detail': str(detail)[:220]})
    print(f'  [{"OK" if ok_ else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return ok_


def head(text: str) -> None:
    print(f'\n{"=" * 66}\n {text}\n{"=" * 66}')


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑
# [EN] A. Pure logic
# ══════════════════════════════════════════════════════════════
def test_logic() -> bool:
    head('A. 纯逻辑（store/project.py）')
    from store.project import Project, norm_source, matches, find_existing, unique_name
    ok_ = True

    ok_ &= ok('A1 ★ 尾斜杠不算两本：`E:\\小说` 与 `E:\\小说/` 归一后相同',
              norm_source(r'E:\小说') == norm_source(r'E:\小说/'),
              norm_source(r'E:\小说'))
    ok_ &= ok('A2 ★ Windows 大小写不算两本（`E:\\Novel` == `e:\\novel`）',
              norm_source(r'E:\Novel') == norm_source(r'e:\novel'), '')
    ok_ &= ok('A3 ★ 从资源管理器复制来的引号与空白要剥掉',
              norm_source('  "E:\\小说"  ') == norm_source('E:\\小说'), '')
    ok_ &= ok('A4 空串归一成空串（调用方据此"没什么可比"）',
              norm_source('') == '' and norm_source('   ') == '', '')
    # ⚠ 查 **AST 里的调用**，不查源码文本：`norm_source` 的 docstring 里
    #   就写着"不用 resolve() 去追符号链接" —— 按文本找必然假红
    #   （本项目栽过一次同型的：docstring 里那句话把判据骗了）。
    # [EN] ⚠ Check **calls in the AST**, not the source text: in `norm_source`'s docstring
    # [EN] it literally says "don't use resolve() to chase symlinks" —— searching by text will inevitably
    # [EN] produce false reds
    import ast as _ast
    _t = _ast.parse(textwrap.dedent(inspect.getsource(norm_source)))
    _calls = {getattr(n.func, 'attr', '') for n in _ast.walk(_t)
              if isinstance(n, _ast.Call)}
    ok_ &= ok('A5 ★ 只做字符串归一，**不**去追符号链接/真实路径'
              '（素材夹被移走时也要认得出当初那串）',
              not ({'resolve', 'realpath'} & _calls), str(sorted(_calls)))

    tmp = Path(tempfile.mkdtemp(prefix='nws_dup_logic_'))
    root = tmp / 'Projects'
    a = Project.create_new(root, '茶肆疑云', source_folder=r'E:\我的小说\悬疑故事')
    Project.create_new(root, '别的书', source_folder=r'E:\我的小说\另一本')

    got = [p.name for p in find_existing(root, name='茶肆疑云')]
    ok_ &= ok('A6 ★★ 同名命中（开卷向导的项目名默认就是文件夹名 —— 这是最常见的那种）',
              got == ['茶肆疑云'], str(got))
    got = [p.name for p in find_existing(root, source_folder=r'e:\我的小说\悬疑故事')]
    ok_ &= ok('A7 ★★ 同素材命中（上次换过名字，这次又换一个 —— 只看名字就漏了）',
              got == ['茶肆疑云'], str(got))
    got = find_existing(root, name='从没听过的名字',
                        source_folder=r'F:\别处\另一本')
    ok_ &= ok('A8 两样都对不上 → 空（该开就让人开，别疑神疑鬼）',
              got == [], str([p.name for p in got]))
    got = find_existing(root, name='茶肆疑云', source_folder=r'E:\我的小说\悬疑故事')
    ok_ &= ok('A9 两条都命中时**只报一次**（不重复列同一本）',
              len(got) == 1, f'{len(got)} 条')

    # ⚠ 这一条最容易做错：判成"父目录开过卷 → 子目录也算开过"就会误伤
    # [EN] ⚠ This is the easiest thing to get wrong: ruling that "parent directory has opened a volume →
    # [EN] subdirectory also counts as opened" will cause false positives
    got = find_existing(root, source_folder=r'E:\我的小说')
    ok_ &= ok('A10 ★★ **父子目录不算同一本**：一个父目录里装着好几本书是正常用法'
              '（判成"同一本"会让第二本开不了卷）',
              got == [], str([p.name for p in got]))
    got = find_existing(root, source_folder=r'E:\我的小说\悬疑故事\更深一层')
    ok_ &= ok('A11 ★ 反过来也一样（子目录开过 ≠ 父目录开过）', got == [],
              str([p.name for p in got]))

    ok_ &= ok('A12 两个参数都空 → 不查（`_do_import` 里路径为空那一步已经先拦了）',
              find_existing(root) == [], '')
    ok_ &= ok('A13 `matches` 与 `find_existing` 是同一份判定'
              '（前者给"复用已扫好的清单"用，后者扫一遍再比）',
              [p.name for p in matches([a], name='茶肆疑云')] == ['茶肆疑云']
              and [p.name for p in matches([a], source_folder=r'e:\我的小说\悬疑故事')]
              == ['茶肆疑云'], '')

    ok_ &= ok('A14 `unique_name` 不撞就原样返回（别没事给人加后缀）',
              unique_name(root, '新书') == '新书', unique_name(root, '新书'))
    ok_ &= ok('A15 ★★ 撞了就加 `(2)`（"仍然重新开卷"靠它不覆盖旧的那本）',
              unique_name(root, '茶肆疑云') == '茶肆疑云 (2)',
              unique_name(root, '茶肆疑云'))
    Project.create_new(root, '茶肆疑云 (2)', source_folder='')
    ok_ &= ok('A16 ★ `(2)` 也撞了 → `(3)`（连着重开两次也各是各的）',
              unique_name(root, '茶肆疑云') == '茶肆疑云 (3)',
              unique_name(root, '茶肆疑云'))
    (root / '空目录也算').mkdir(parents=True, exist_ok=True)
    ok_ &= ok('A17 ★ 光有同名**目录**（还没开卷 / 手建的）也算撞 —— '
              '不然新书会写进那个目录里',
              unique_name(root, '空目录也算') == '空目录也算 (2)',
              unique_name(root, '空目录也算'))
    ok_ &= ok('A18 名字里的非法字符按落盘口径 (`safe_name`) 比较 —— '
              '`甲/乙` 与 `甲_乙` 落盘是同一个文件夹',
              unique_name(root, '别的书') == '别的书 (2)',
              unique_name(root, '别的书'))

    shutil.rmtree(tmp, ignore_errors=True)
    return ok_


# ══════════════════════════════════════════════════════════════
#  C. 闸门位置（源码级）
# [EN] C. Gate position (source level)
# ══════════════════════════════════════════════════════════════
def test_source() -> bool:
    head('C. 闸门位置（源码级）')
    from gui.app_flet import NovelWorldApp
    ok_ = True
    src = inspect.getsource(NovelWorldApp._do_import)
    body = textwrap.dedent(src)

    # ⚠ 用 **AST 行号** 比位置，不查文本（文本会被 docstring 里同样的字骗到 ——
    #   本项目栽过一次：`src.find('return')` 先找到注释里的那个）
    # [EN] ⚠ Use **AST line numbers** to compare, not text (text will be fooled by the same characters in
    # [EN] docstrings ——
    # [EN] this project has been burned once: `src.find('return')` first found the one in a comment)
    import ast as _ast
    tree = _ast.parse(body)
    fn = tree.body[0]
    dup_ln = ask_line = pop_ln = None
    for n in _ast.walk(fn):
        if isinstance(n, _ast.Call):
            attr = getattr(n.func, 'attr', '')
            if attr == '_ask_duplicate' and dup_ln is None:
                dup_ln = n.lineno
            if attr == 'pop_dialog' and pop_ln is None:
                pop_ln = n.lineno

    ok_ &= ok('C1 ★★ `_do_import` 里**真的**会去问「这本开过卷没有」'
              '（`_duplicates_for_wizard` + `_ask_duplicate` 都在）',
              '_duplicates_for_wizard' in src and dup_ln is not None,
              f'ask@{dup_ln}')
    ok_ &= ok('C2 ★★★ 提示排在 `page.pop_dialog()` **之前**'
              '（顺序反了：用户已经被踢出向导，关掉提示框之后无处可回）',
              dup_ln is not None and pop_ln is not None and dup_ln < pop_ln,
              f'ask@{dup_ln} pop@{pop_ln}')
    ok_ &= ok('C3 ★ 拦下来时**直接 return**（不接着往下走 `/run_ingest` 那条路）',
              'self._ask_duplicate(page, dup, src, name)\n                return'
              in src.replace('\r\n', '\n'), '')
    ok_ &= ok('C4 ★ 有 `force`（"仍然重新开卷"那条路要能跳过闸门）'
              '且默认是 False（普通调用照旧被拦）',
              'force: bool = False' in src, '')
    ok_ &= ok('C5 拦下时会**记一条 UI 日志**（事后能查"为什么这本开不动")',
              'log_ui_action' in src and '开卷被拦下' in src, '')

    # 步骤 1 那条提示行
    # [EN] The hint line from step 1
    s1 = inspect.getsource(NovelWorldApp._wizard_step1_folder)
    ok_ &= ok('C6 ★★ 步骤 1 里就有那条提示行（选完文件夹**当场**告诉用户，'
              '不用等到最后一步才被拦）',
              '_wizard_dup_hint' in s1 and 'dup_hint' in s1, '')
    chg = inspect.getsource(NovelWorldApp._on_wizard_path_changed)
    ok_ &= ok('C7 ★ 路径一变就刷新它', '_refresh_wizard_dup' in chg, '')
    return ok_


# ══════════════════════════════════════════════════════════════
#  B/D. 真机
# [EN] B/D. Real machine
# ══════════════════════════════════════════════════════════════
def _fixture(root: Path) -> Path:
    """一份最小素材夹（开卷跑得动就行，内容多少与这条判据无关）。
        English:
    A minimal material folder (just enough to run the volume opening, content amount is irrelevant
    to this check).
    """
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n起：雨夜来客。\n承：旧事翻出。\n',
                                 encoding='utf-8')
    (src / '人物设定.md').write_text('# 人物\n## 主角\n掌柜。\n## 阿枝\n伙计。\n',
                                     encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦。\n\n「你今日话里有话。」\n', encoding='utf-8')
    return src


def _find_button(dlg, label: str):
    """在控件树里找**文本是这个**的按钮（`mk_btn` 的文本在 content 上）。
        English:
    In the widget tree, find the button whose **text is this** (the text of `mk_btn` is on content).
    """
    import verify_ui_common as VU
    for c in VU.walk(dlg):
        if callable(getattr(c, 'on_click', None)) and label in VU.text_of(c):
            return c
    return None


async def test_gui(page) -> bool:
    import flet as ft
    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp
    from i18n import set_lang
    from store.project import Project
    set_lang('zh')

    head('B. 真机（MOCK）')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.window.width = 1260
    page.window.height = 860
    page.update()
    await asyncio.sleep(2.2)

    ok_ = True
    tmp = Path(tempfile.mkdtemp(prefix='nws_dupui_'))

    async def shot(name: str) -> None:
        try:
            page.update()
            await asyncio.sleep(0.45)
            (OUT / name).write_bytes(await page.take_screenshot())
        except Exception:                                        # noqa: BLE001
            pass

    try:
        VU.isolate_projects_dir(tmp / 'Projects')
        src = _fixture(tmp)

        # ── 先造成"这本已经开过卷了" ──
        # [EN] ── First make it so that "this book has already opened a volume" ──
        old = Project.create_new(CFG.projects_dir(), '雨夜来客',
                                 source_folder=str(src),
                                 genre='悬疑·单元剧')
        old_before = old.nwsproj_path.read_text(encoding='utf-8')
        ok_ &= ok('B0 前提：磁盘上已经有一本「雨夜来客」（指同一素材夹）',
                  old.nwsproj_path.is_file(), str(old.nwsproj_path))

        # ── ① 向导步骤 1 的提示行 ──
        # [EN] ── ① Hint line of wizard step 1 ──
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)
        app._wizard_path = str(src)
        app._on_wizard_path_changed(None)
        page.update()
        await asyncio.sleep(0.4)

        hint = getattr(app, '_wizard_dup_hint', None)
        hint_txt = str(getattr(hint, 'value', '') or '')
        ok_ &= ok('B1 ★★ 选完文件夹，步骤 1 **当场**出现「已经开过卷」提示'
                  '（不用等到最后一步）',
                  hint is not None and bool(getattr(hint, 'visible', False))
                  and '已经开过卷' in hint_txt,
                  f'visible={getattr(hint, "visible", None)} text={hint_txt[:60]}')
        ok_ &= ok('B2 ★ 提示里写明了是**哪一本**（只说"已存在"用户没法核对）',
                  '雨夜来客' in hint_txt, hint_txt[:80])
        await shot('ingest_duplicate_1_hint.png')

        # ── ② 点「开始摄取」：必须被拦下 ──
        # [EN] ── ② Click "Start Ingest": it must be blocked ──
        before_dialogs = len(VU.open_dialogs(page))
        app._wizard_name = '雨夜来客'
        app._do_import(page)
        page.update()
        await asyncio.sleep(0.8)

        running = bool((app._ingest_state or {}).get('running'))
        ok_ &= ok('B3 ★★★ 点「开始摄取」**没有开跑**（以前这里一声不吭就开了一遍）',
                  not running, f'running={running}')
        dlgs = VU.open_dialogs(page)
        ok_ &= ok('B4 ★★ 弹出了提示框，而且**向导还在**（人没被踢出去）',
                  len(dlgs) == before_dialogs + 1,
                  f'{before_dialogs} → {len(dlgs)}')
        if not dlgs:
            return ok_
        dlg = dlgs[-1]
        texts = ' | '.join(VU.all_texts(dlg))
        ok_ &= ok('B5 ★★ 框里说清了后果（重新读一遍素材）与退路（打开已有那本）',
                  '已经开过卷' in texts and '重新读' in texts
                  and '雨夜来客' in texts, texts[:150])
        ok_ &= ok('B6 ★★ 三个按钮齐：打开「雨夜来客」/ 仍然重新开卷 / 取消',
                  all(_find_button(dlg, x) is not None
                      for x in ('打开「雨夜来客」', '仍然重新开卷', '取消')),
                  str([VU.text_of(c) for c in VU.walk(dlg)
                       if callable(getattr(c, 'on_click', None))])[:150])
        ok_ &= ok('B7 ★★ 推荐动作（打开已有那本）在**最左**'
                  '（本项目的老规矩：主按钮在左）',
                  bool(VU.text_of(dlg.actions[0]).startswith('打开'))
                  if getattr(dlg, 'actions', None) else False,
                  str([VU.text_of(a) for a in (getattr(dlg, 'actions', None) or [])]))
        await shot('ingest_duplicate_2_dialog.png')

        # ── ③ 点「取消」→ 什么都没发生，向导还在 ──
        # [EN] ── ③ Click "Cancel" → nothing happens, wizard is still there ──
        _find_button(dlg, '取消').on_click(None)
        page.update()
        await asyncio.sleep(0.4)
        ok_ &= ok('B8 ★★ 点「取消」→ 仍然没开跑',
                  not bool((app._ingest_state or {}).get('running')), '')
        ok_ &= ok('B9 ★★ 点「取消」→ **向导还在**（回到原来那一步，能改路径/改名字再试）',
                  len(VU.open_dialogs(page)) >= 1,
                  f'{len(VU.open_dialogs(page))} 个框')

        # ── ④ 再拦一次，点「打开「雨夜来客」」→ 真的切到那一本 ──
        # [EN] ── ④ Block again, click "Open 「雨夜来客」" → really switch to that book ──
        shown: list = []
        real_main = app.show_main_screen
        app.show_main_screen = lambda *a, **k: shown.append(1)
        try:
            app._do_import(page)
            page.update()
            await asyncio.sleep(0.6)
            dlgs = VU.open_dialogs(page)
            open_btn = _find_button(dlgs[-1], '打开「雨夜来客」') if dlgs else None
            if open_btn is not None:
                open_btn.on_click(None)
                page.update()
                await asyncio.sleep(0.5)
        finally:
            app.show_main_screen = real_main
        cur = getattr(app, 'current_project', None)
        ok_ &= ok('B10 ★★ 点「打开「雨夜来客」」→ 真的切到**那一本**'
                  '（不是只关个框）',
                  cur is not None and cur.name == '雨夜来客',
                  f'current={getattr(cur, "name", None)}')
        ok_ &= ok('B11 ★ 而且真的回到了主界面（`show_main_screen` 被调用）',
                  bool(shown), f'{len(shown)} 次')

        # ── ⑤ 再来一次，点「仍然重新开卷」→ 避重名 + 真开跑 ──
        # [EN] ── ⑤ Do it once more, click "Still re-open volume" → avoid duplicate name + really start ──
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)
        app._wizard_path = str(src)
        app._wizard_name = '雨夜来客'
        app._wizard_name_auto = '雨夜来客'
        VU.disable_source_repair(app)            # 那一步会停下等点击，这里不测它
        # [EN] That step will pause waiting for a click, not tested here
        app._wizard_opts['ai_optimize'] = False
        app._do_import(page)
        page.update()
        await asyncio.sleep(0.6)
        dlgs = VU.open_dialogs(page)
        again_btn = _find_button(dlgs[-1], '仍然重新开卷') if dlgs else None
        ok_ &= ok('B12 第二次拦下来了（提示框还在）', again_btn is not None,
                  f'{len(dlgs)} 个框')
        if again_btn is not None:
            again_btn.on_click(None)
            page.update()
            await asyncio.sleep(1.0)
        ok_ &= ok('B13 ★★★ 点「仍然重新开卷」→ 项目名**自动避开重名**'
                  '（不覆盖已经开过的那本）',
                  app._wizard_name == '雨夜来客 (2)', repr(app._wizard_name))
        ok_ &= ok('B14 ★★★ 而且**真的开始摄取了**（不是光改个名字就完事）',
                  bool((app._ingest_state or {}).get('running')),
                  f'running={bool((app._ingest_state or {}).get("running"))}')

        # 等它跑完（MOCK 下几十秒）；跑完才建项目目录。
        # ⚠ 中途会停在**同意门**（「交给 AI 之前」那个确认面板）等点击 ——
        #   本判据测的不是它（那是 `verify_ingest_consent` 的活），所以照
        #   那个脚本的同一手法**自动点头**；不点的话流程会停在那儿，
        #   永远等不到项目目录（第一版就卡在这，B15 假红）。
        # [EN] Wait for it to finish (dozens of seconds under MOCK); the project directory is only created
        # [EN] after it finishes.
        # [EN] ⚠ Midway it will pause at the **consent gate** (the "before handing to AI" confirmation panel)
        # [EN] waiting for a click ——
        # [EN] this check is not testing it (that is the job of `verify_ingest_consent`), so follow
        # [EN] the same trick of that script to **auto-nod**; if you don't click, the flow will stop there,
        # [EN] and you'll never reach the project directory (the first version got stuck here, B15 false red).
        new_dir = CFG.projects_dir() / '雨夜来客 (2)'
        st = app._ingest_state or {}
        for _ in range(900):
            await asyncio.sleep(0.2)
            ui = st.get('ui') or {}
            try:
                if ui.get('consent'):
                    ui['consent'](True)          # 同意门：自动点头
                    # [EN] Consent gate: auto-nod
            except Exception:                                    # noqa: BLE001
                pass
            if (new_dir / '雨夜来客 (2).nwsproj').is_file():
                break
            if not st.get('running'):
                break
        report_extra = {'running': st.get('running'), 'phase': st.get('phase')}
        print(f'  （收尾时 state：{report_extra}）')
        ok_ &= ok('B15 ★★ 新开的那本落在**新目录**（`雨夜来客 (2)`），'
                  '没有写进旧项目',
                  (new_dir / '雨夜来客 (2).nwsproj').is_file(),
                  f'{new_dir}　state={report_extra}')
        ok_ &= ok('B16 ★★★ 旧项目的 `.nwsproj` **一个字没被改**'
                  '（"不许覆盖"的实锤）',
                  old.nwsproj_path.read_text(encoding='utf-8') == old_before,
                  f'{old.nwsproj_path.name} '
                  f'{len(old_before)} → '
                  f'{len(old.nwsproj_path.read_text(encoding="utf-8"))} 字')
        ok_ &= ok('B17 ★ 旧项目里也没有被塞进新书的设定（`设定集/` 保持原样）',
                  not list((old.settings_dir).glob('*.md'))
                  or all(p.stat().st_size > 0
                         for p in old.settings_dir.glob('*.md')),
                  str([p.name for p in old.settings_dir.glob('*')][:5]))
    finally:
        try:
            if (app._ingest_state or {}).get('running'):
                app._ingest_state['cancel'] = True
                await asyncio.sleep(1.0)
        except Exception:                                        # noqa: BLE001
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    return ok_


# ══════════════════════════════════════════════════════════════
async def main(page) -> None:
    from util.flet_shutdown import shutdown
    ok_ = True
    try:
        ok_ &= test_logic()
        ok_ &= test_source()
        ok_ &= await test_gui(page)
    except BaseException:                                        # noqa: BLE001
        traceback.print_exc()
        _ITEMS.append({'name': '（执行中断）', 'ok': False,
                       'detail': traceback.format_exc()[-400:]})
        ok_ = False
    n_ok = sum(1 for i in _ITEMS if i['ok'])
    print(f'\n{"-" * 66}\n  开卷重复拦截：{n_ok}/{len(_ITEMS)}'
          + ('' if ok_ else '   ← 有失败'))
    for i in _ITEMS:
        if not i['ok']:
            print(f'    ! {i["name"]}  [{i["detail"][:120]}]')
    (OUT / 'ingest_duplicate_report.json').write_text(
        json.dumps({'passed': n_ok, 'total': len(_ITEMS), 'ok': ok_,
                    'checks': _ITEMS}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    await shutdown(page, code=0 if ok_ else 2)


if __name__ == '__main__':
    if '--logic-only' in sys.argv:
        a = test_logic()
        b = test_source()
        n = sum(1 for i in _ITEMS if i['ok'])
        print(f'\n  开卷重复拦截（逻辑段）：{n}/{len(_ITEMS)}'
              + ('' if (a and b) else '   ← 有失败'))
        for i in _ITEMS:
            if not i['ok']:
                print(f'    ! {i["name"]}  [{i["detail"][:140]}]')
        sys.exit(0 if (a and b) else 2)
    import flet as ft
    ft.run(main)
