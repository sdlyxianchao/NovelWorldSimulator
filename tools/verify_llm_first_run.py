# -*- coding: utf-8 -*-
"""验证：**第一次跑、没配 LLM 时的引导**（用户 2026-10-06 要的）。

用户原话：「一开始如果一个完全空的软件，用户第一次跑，没配置 LLM，
程序会弹出一个提示信息，告诉用户 LLM 还没配，无法进行有效推演，
告诉用户去使用说明里找如何申请 LLM API Key……同时对话框有一个按钮
是否开始配置，点了就会打开天机的 LLM 接入对话框，
点击取消或者关闭对话框则后续再回来。」

判据分层（每层都要能红，见 `developers/mutate_llm_first_run.py`）：
  A **该不该弹**：没配 → 弹；配好了 → 不弹；**用户自己开演示模式 → 不弹**
     （那是他的明确选择，不是"没配"）；程序替他开的演示模式 → 仍然弹。
  B **两个按钮**：「去配置」→ 关掉自己 + 打开天机（**落在 LLM 接入那一页**）；
     「以后再说」→ 只关掉自己，不开设置。
  C **天机的落点**：`show_global_settings(tab=N)` 的 `selected_index`
     夹在 `[1, tab_defs 数]`（越界 Flet 会抛）。
  D **常驻消息**：光弹一下不够，关掉之后「消息」里还要有一条 warn（别让提示消失得无影无踪）。
  E **文案要真的指路**：必须点到「使用说明」与「API Key」（用户原话的要求）。
  F **真机 + 像素取证**：对话框真的画在屏幕上、两个按钮都在；反例（清空文字）像素归零。
  G **手册**：`使用说明.md` 的 2.4 覆盖用户点名的那几家；3.4 那一节存在、
     且讲了「天机」与「测试」；英文版 `User_Manual.md` 同步。

用法：.venv\\Scripts\\python.exe tools/verify_llm_first_run.py
产出：assets/screenshots/llm_first_run_report.json

English:
Verification: **the guidance on the first run when no LLM is configured** (requested by the user
on 2026-10-06).
User's exact words: "At the beginning, if the software is completely empty and the user runs it
for the first time without an LLM configured,
the program should pop up a prompt telling the user that the LLM is not configured yet and
effective reasoning cannot be performed,
telling the user to look in the instructions for how to apply for an LLM API Key... At the same
time the dialog has a button
for whether to start configuration; clicking it opens Tianji's LLM access dialog,
and clicking cancel or closing the dialog means coming back later."
Layered criteria (every layer must be able to go red, see `developers/mutate_llm_first_run.py`):
  A **whether it should pop up**: not configured -> pop up; configured -> do not pop up; **user opened demo mode himself -> do not pop up**
     (that is his explicit choice, not "not configured"); demo mode opened by the program on his behalf -> still pop up.
  B **two buttons**: "Go configure" -> close itself + open Tianji (**landing on the LLM access page**);
     "Later" -> only close itself, do not open settings.
  C **Tianji's landing point**: `show_global_settings(tab=N)`'s `selected_index`
     is clamped to `[1, number of tab_defs]` (out of range makes Flet throw).
  D **persistent message**: just popping up is not enough; after closing there must still be a warn in "Messages" (do not let the prompt vanish without a trace).
  E **the copy must actually give directions**: it must mention "Instructions" and "API Key" (the user's explicit requirement).
  F **real machine + pixel evidence**: the dialog is actually drawn on screen, both buttons are present; negative case (cleared text) pixels go to zero.
  G **manual**: section 2.4 of `使用说明.md` covers the providers the user named; section 3.4 exists
     and talks about "Tianji" and "Testing"; the English version `User_Manual.md` is kept in sync.
Usage: .venv\\Scripts\\python.exe tools/verify_llm_first_run.py
Output: assets/screenshots/llm_first_run_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
# ⚠ 不点任何会 `CFG.save()` 的按钮；GUI 段仍然整段套 `VU.env_guard()`。
# [EN] ⚠ Do not click any button that calls `CFG.save()`; the GUI section still wraps the whole section
# [EN] in `VU.env_guard()`.
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def rec(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════
#  A-D. 逻辑（不开界面）
# [EN] A-D. Logic (without opening the UI)
# ══════════════════════════════════════════════════════════════
def _mk_app():
    """造一个**不挂页面**的 app 实例，只为调那几个方法。

    用 `__new__` 而不是构造器：构造器会读 .env、建控件树，
    这一段要验的是"该不该弹 / 点了干什么"，跟界面无关。
    
        English:
    Create an app instance that **mounts no page**, just to call those few methods.
        Use `__new__` instead of the constructor: the constructor reads .env and builds the widget tree,
        whereas what this section verifies is "whether it should pop up / what happens on click", unrelated to the UI.
    """
    from gui.app_flet import NovelWorldApp
    app = NovelWorldApp.__new__(NovelWorldApp)
    app._messages = []
    app._ui_msg = {}
    app._msg_unread = 0
    app._mock_auto_on = False
    shown: list = []
    popped: list[int] = []
    opened: list[dict] = []

    class P:
        def show_dialog(self, d):
            shown.append(d)

        def pop_dialog(self):
            popped.append(1)

        def update(self):
            pass

    app.page = P()
    # ⚠ 默认值给的是**哨兵**（`None`），不是真方法现在的默认值（`TAB_GENERAL`）：
    #   照抄的话"没传 `tab=`"和"传了个等于默认值的数"记下来一模一样 ——
    #   那个变异永远抓不到。（2026-10-31 起真方法默认落在「常规」页。）
    # [EN] ⚠ The default here is a **sentinel** (`None`), not the real method's current default
    # [EN] (`TAB_GENERAL`): copying it verbatim makes "didn't pass `tab=`" and "passed the default"
    # [EN] recorded identically -- that mutation can never be caught. (As of 2026-10-31 the real
    # [EN] method defaults to the "General" page.)
    # [EN] ⚠ Give the default value a **sentinel** (`None`) instead of 1: the real method's default is 1,
    # [EN] copying it verbatim makes "forgot to pass `tab=1`" and "passed `tab=1`" recorded identically --
    # [EN] that mutation can never be caught.
    app.show_global_settings = lambda tab=None: opened.append({'tab': tab})
    return app, shown, popped, opened


def test_should_pop() -> bool:
    ok = True
    saved = {k: CFG.raw(k) for k in
             ('LLM_BASE_URL', 'LLM_API_KEY', 'MODEL_FRONT', 'MODEL_DAILY',
              'MODEL_CHEAP', 'MOCK_LLM')}
    try:
        # ① 完全空 → 弹
        # [EN] ① Completely empty -> pop up
        for k in ('LLM_BASE_URL', 'LLM_API_KEY', 'MODEL_FRONT', 'MODEL_DAILY',
                  'MODEL_CHEAP'):
            CFG.set(k, '')
        CFG.set('MOCK_LLM', 'true')          # `_run_llm_readiness_check` 会这么开
        # [EN] `_run_llm_readiness_check` will start it this way
        app, shown, popped, opened = _mk_app()
        app._mock_auto_on = True             # 程序替他开的 → 算"没配"
        # [EN] the program turned it on for him -> counts as "not configured"
        app._maybe_show_llm_setup_dialog()
        ok &= rec('A1 ★★ 完全没配 → 真的弹出对话框',
                  len(shown) == 1, f'{len(shown)} 个')
        ok &= rec('A1 ★★ 弹之前先清旧帧（`pop_dialog`）—— 本项目的坑',
                  len(popped) >= 1, f'{len(popped)} 次')
        ok &= rec('A1 ★ 弹的**不是**天机本身（是引导框）',
                  opened == [], str(opened))

        # ② 配好了 → 不弹
        # [EN] ② Configured -> do not pop up
        CFG.set('LLM_BASE_URL', 'https://api.deepseek.com/v1')
        CFG.set('LLM_API_KEY', 'sk-not-a-real-key')
        CFG.set('MODEL_FRONT', 'deepseek-v4-pro')
        CFG.set('MODEL_DAILY', 'deepseek-flash')
        CFG.set('MODEL_CHEAP', 'deepseek-flash')
        app, shown, popped, opened = _mk_app()
        app._maybe_show_llm_setup_dialog()
        ok &= rec('A2 ★★ 配好了 → **不打扰**（一次都不弹）',
                  shown == [] and popped == [], f'{len(shown)} 个')

        # ③ 用户**自己**开着演示模式 → 不弹（那是他的选择）
        # [EN] ③ The user **himself** turned on demo mode -> do not pop up (that is his choice)
        CFG.set('LLM_BASE_URL', '')
        CFG.set('LLM_API_KEY', '')
        app, shown, popped, opened = _mk_app()
        app._mock_auto_on = False            # 不是程序开的 → 用户自己选的
        # [EN] Not turned on by the program -> the user chose it himself
        app._maybe_show_llm_setup_dialog()
        ok &= rec('A3 ★★ 用户自己开「演示模式」→ 不弹（别烦有主意的人）',
                  shown == [], f'{len(shown)} 个')
        # 反例：同一份配置，只是"程序替他开的" → 要弹
        # [EN] Counterexample: the same config, just "turned on by the program for him" -> should pop up
        app, shown, popped, opened = _mk_app()
        app._mock_auto_on = True
        app._maybe_show_llm_setup_dialog()
        ok &= rec('A3 ★ 反例：同样没配、但演示模式是**程序替他开的** → 仍然弹'
                  '（判据不是恒真）', len(shown) == 1, f'{len(shown)} 个')

        # ④ 只填了一半（有地址没 Key）→ 还是算没配
        # [EN] ④ Only half filled (has address but no Key) -> still counts as not configured
        CFG.set('LLM_BASE_URL', 'https://api.deepseek.com/v1')
        CFG.set('LLM_API_KEY', '')
        app, shown, popped, opened = _mk_app()
        app._mock_auto_on = True
        app._maybe_show_llm_setup_dialog()
        ok &= rec('A4 ★ 只填了地址没填 Key → 仍然算没配（要弹）',
                  len(shown) == 1, f'{len(shown)} 个')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


def test_buttons() -> bool:
    ok = True
    from gui.app_flet import NovelWorldApp      # 取 `TAB_LLM` 用（见 B2）
    # [EN] Fetch `TAB_LLM` to use (see B2)
    saved = {k: CFG.raw(k) for k in ('LLM_BASE_URL', 'LLM_API_KEY')}
    try:
        CFG.set('LLM_BASE_URL', '')
        CFG.set('LLM_API_KEY', '')
        CFG.set('MOCK_LLM', 'true')
        app, shown, popped, opened = _mk_app()
        app._mock_auto_on = True
        app._maybe_show_llm_setup_dialog()
        dlg = shown[0] if shown else None
        ok &= rec('B1 拿到了对话框对象', dlg is not None, '')
        if dlg is None:
            return False
        labels = []
        for act in (dlg.actions or []):
            ct = getattr(act, 'content', None)
            labels.append(str(getattr(ct, 'value', '') or ct or ''))
        ok &= rec('B1 ★★ 两个按钮：「去配置」+「以后再说」',
                  any('去配置' in x for x in labels)
                  and any('以后再说' in x for x in labels), str(labels))

        go = next(a for a in dlg.actions
                  if '去配置' in str(getattr(getattr(a, 'content', None), 'value', '')))
        later = next(a for a in dlg.actions
                     if '以后再说' in str(getattr(getattr(a, 'content', None), 'value', '')))

        # 「去配置」→ 关掉自己 + 打开天机（落在 LLM 接入）
        # [EN] "Go to config" -> close itself + open Tianji (land on LLM access)
        popped.clear(); opened.clear()
        go.on_click(None)
        ok &= rec('B2 ★★ 点「去配置」→ 关掉引导框', len(popped) == 1, f'{len(popped)} 次')
        # ⚠ 这里原来写死 `1`。2026-10-08 在「LLM 接入」左边加了「常规」页签，
        #   写死 `1` 就变成"落在「常规」页"—— 判据假红，而产品其实是对的
        #   （它两处都取 `TAB_LLM`）。改成取那个常量，页签顺序再变也不会假红；
        #   "常量本身指没指对"由下面 C1b 那条**照页签表核**来管。
        # [EN] ⚠ This used to be hardcoded to `1`. On 2026-10-08 a "General" tab was added to the left of "LLM
        # [EN] access",
        # [EN] hardcoding `1` then becomes "land on the 'General' page" -- the criterion falsely red, while the
        # [EN] product is actually correct
        # [EN] (it fetches `TAB_LLM` in both places). Change it to fetch that constant, so no matter how the
        # [EN] tab order changes it will not falsely go red;
        # [EN] whether "the constant itself points correctly" is governed by the C1b item below, **checked
        # [EN] against the tab table**.
        _want = NovelWorldApp.TAB_LLM
        ok &= rec(f'B2 ★★ 点「去配置」→ 打开天机，**且落在 LLM 接入那一页**'
                  f'（tab={{TAB_LLM}}={{_want}}）',
                  opened == [{'tab': _want}], str(opened))

        # 「以后再说」→ 只关掉自己，不开设置
        # [EN] "Later" -> only close itself, do not open settings
        popped.clear(); opened.clear()
        later.on_click(None)
        ok &= rec('B2 ★★ 点「以后再说」→ 关掉自己，**不打开设置**'
                  '（"后续再回来"= 下次启动还会提醒）',
                  len(popped) == 1 and opened == [], f'{popped} / {opened}')

        # D 常驻消息
        # ⚠ 存下来的只有 `{ts, text, level}` —— **没有 `keep` 这个键**
        #   （`keep` 是入参，决定它进不进这个列表）。第一版拿 `m.get('keep')`
        #   当判据 → 恒假红。
        # [EN] D Persistent message
        # [EN] ⚠ What is saved is only `{ts, text, level}` -- **there is no `keep` key**
        # [EN] (`keep` is an input param, deciding whether it goes into this list). The first version used
        # [EN] `m.get('keep')`
        # [EN] as the criterion -> permanently falsely red.
        ok &= rec('D1 ★★ 同时留一条常驻 warn 消息（对话框关掉后它还在，'
                  '`keep=True` 已让它进了列表）',
                  any(m.get('level') == 'warn'
                      and '还没有配置 LLM' in str(m.get('text', ''))
                      for m in app._messages),
                  str([(m.get('level'), m.get('text', '')[:34]) for m in app._messages]))
        # C 文案要指路
        # [EN] C The copy text should point the way
        body_texts = []

        def _walk(c, d=0):
            if c is None or d > 12:
                return
            v = getattr(c, 'value', None)
            if isinstance(v, str) and v.strip():
                body_texts.append(v)
            for a in ('content', 'controls', 'title'):
                x = getattr(c, a, None)
                if isinstance(x, list):
                    for y in x:
                        _walk(y, d + 1)
                elif x is not None and hasattr(x, '__class__'):
                    _walk(x, d + 1)

        _walk(dlg)
        blob = '\n'.join(body_texts)
        ok &= rec('E1 ★★ 文案点到了「使用说明」与「API Key 获取」'
                  '（用户原话：告诉他去使用说明里找怎么申请）',
                  '使用说明' in blob and 'API Key' in blob, blob[:160].replace('\n', ' | '))
        ok &= rec('E1 ★ 文案列了厂商（DeepSeek / OpenAI / Claude / Google / 微软 / '
                  'GLM / 通义千问 / MiniMax）',
                  all(x in blob for x in ('DeepSeek', 'OpenAI', 'Claude', 'Google',
                                          '微软', 'GLM', '通义千问', 'MiniMax')),
                  blob[-160:].replace('\n', ' | '))
        ok &= rec('E1 ★ 说了"下次启动还会提醒你"（点了以后再说不是永别）',
                  '下次启动还会提醒' in blob, '')
    finally:
        for k, v in saved.items():
            CFG.set(k, v)
    return ok


def test_main_wiring() -> bool:
    """★ `main()` 里**真的调了**那段引导 —— 不然用户第一次跑根本看不到它。

    这一条是**源码哨兵**（弱判据，见技能 §60）：`main()` 依赖整个 Flet 页面，
    在这个不开界面的脚本里跑不起来。真机那一段（`--gui`）另有一套行为判据，
    两边合起来才够。
    
        English:
    ★ `main()` **really calls** that guidance block -- otherwise the user will not see it at all on
    first run.
        This item is a **source-code sentinel** (weak criterion, see skill §60): `main()` depends on the entire Flet page,
        so it cannot run in this script that does not open a UI. The real-machine section (`--gui`) has its own set of behavioral criteria,
        and only both together are sufficient.
    """
    import inspect
    from gui.app_flet import NovelWorldApp
    src = inspect.getsource(NovelWorldApp.main)
    ok = rec('F0 ★★ `main()` 里真的调了 `_maybe_show_llm_setup_dialog()`'
             '（否则用户第一次跑看不到引导）',
             '_maybe_show_llm_setup_dialog()' in src,
             ' | '.join(l.strip() for l in src.split('\n')
                        if '_maybe_show_llm_setup_dialog' in l))
    ok &= rec('F0 ★ 而且排在 `show_start_screen()` **之后**'
              '（先有界面再弹框，别对着空屏弹）',
              src.find('show_start_screen()')
              < src.find('_maybe_show_llm_setup_dialog()'),
              f"{src.find('show_start_screen()')} < "
              f"{src.find('_maybe_show_llm_setup_dialog()')}")
    return ok


def test_tab_index() -> bool:
    """★ `show_global_settings(tab=N)` 的落点要夹在合理范围内（越界 Flet 会抛）。
        English:
    ★ `show_global_settings(tab=N)`'s landing point must be clamped to a reasonable range (out of
    range makes Flet throw).
    """
    ok = True
    import inspect
    from gui.app_flet import NovelWorldApp
    src = inspect.getsource(NovelWorldApp.show_global_settings)
    ok &= rec('C1 ★★ 天机的选项卡支持指定落点（`selected_index`）',
              'selected_index=' in src, '')
    # ⚠ 两边都要去空格再比：第一版只把源码 `replace(' ', '')`，针里还带着空格
    #   （`'max(1, min('`）→ 永远不命中，判据恒假红。
    # ★★★ 2026-10-09 改：夹取的**上界也错了**。原针是 `max(1,min(len(tab_defs)`，
    #   而 `selected_index` 是 **0 起算**（Flet 的 `Tabs.selected_index` 默认就是 0、
    #   文档写明 `-1` 指最后一个页签、校验式 `-length <= i < length`）——
    #   所以上界必须是 `len(tab_defs) - 1`，写成 `len(tab_defs)` 时
    #   **最后一个页签一选就抛** `IndexError: selected_index out of range`。
    # [EN] ⚠ Both sides must have whitespace stripped before comparing: the first version only did
    # [EN] `replace(' ', '')` on the source, while the needle still had spaces
    # [EN] (`'max(1, min('`) -> never matches, criterion permanently falsely red.
    # [EN] ★★★ Changed 2026-10-09: the **upper bound of the extraction was also wrong**. The original
    # [EN] needle was `max(1,min(len(tab_defs)`
    # [EN] while `selected_index` is **0-based** (Flet's `Tabs.selected_index` defaults to 0,
    # [EN] the docs state `-1` means the last tab, validation formula `-length <= i < length`) --
    # [EN] so the upper bound must be `len(tab_defs) - 1`; when written as `len(tab_defs)`
    # [EN] **selecting the last tab immediately throws** `IndexError: selected_index out of range`.
    ok &= rec('C1 ★★ 夹取，防越界（Flet 对越界不容错；`selected_index` 是 **0 起算**，'
              '上界 = 页签数 − 1）',
              'max(0,min(len(tab_defs)-1' in src.replace(' ', ''),
              [l.strip() for l in src.split('\n') if 'selected_index' in l][:1])
    # 行为：真造一次对话框，看它落在第几个
    # [EN] Behavior: actually build a dialog once, see which index it lands on
    from gui.app_flet import NovelWorldApp as A
    _default = inspect.signature(A.show_global_settings).parameters['tab'].default
    ok &= rec('C1 ★★ 默认值是 None（= 不指定 ⇒ 落 `TAB_GENERAL`「常规」，2026-10-31 口径）',
              _default is None, f'default={_default!r}')

    # ★★★ C1b：`TAB_LLM` **真的**指着「LLM 接入」那一页。
    #   这条才是防"页签顺序变了、常量没跟着改"的那把锁 ——
    #   光断言"常量等于 2"是没用的（那只是把字面量搬了个家）。
    #   做法：从 `show_global_settings` 的源码里把 `tab_defs` 的**页签顺序**
    #   解析出来（AST），再拿常量去索引。页面顺序是产品的事实，判据照它核。
    # [EN] ★★★ C1b: `TAB_LLM` **really** points to the "LLM access" page.
    # [EN] This one is the lock guarding against "tab order changed but the constant was not updated" --
    # [EN] merely asserting "the constant equals 2" is useless (that just moves the literal elsewhere).
    # [EN] Approach: from the source of `show_global_settings`, extract the **tab order** of `tab_defs`
    # [EN] by parsing it (AST), then index with the constant. The page order is a product fact; check the
    # [EN] criterion against it.
    import ast as _ast
    import textwrap as _tw
    # ⚠ `inspect.getsource` 给的是**带缩进**的方法源码（它是类的方法），
    #   直接 `ast.parse` 会 `IndentationError: unexpected indent`（实测踩到）。
    # [EN] ⚠ `inspect.getsource` gives the **indented** method source (it is a class method),
    # [EN] calling `ast.parse` directly will `IndentationError: unexpected indent` (encountered in
    # [EN] practice).
    _tree = _ast.parse(_tw.dedent(src))
    _titles: list = []
    for _n in _ast.walk(_tree):
        if isinstance(_n, _ast.Assign) and any(
                getattr(_t, 'id', None) == 'tab_defs' for _t in _n.targets):
            for _elt in _n.value.elts:
                _first = _elt.elts[0]
                _arg = (getattr(_first, 'args', None) or [None])[0]
                if isinstance(_arg, _ast.Constant):
                    _titles.append(_arg.value)
            break
    # ★★★ 2026-10-09：**下标口径**从"1 起算"改成 **0 起算**。
    #   老写法 `1 <= _i <= len(_titles) and _titles[_i - 1] == 'AI模型配置'`
    #   与 `TAB_LLM = 2` **一起错**：常量其实指着「界面外观」，
    #   而这条判据照样绿（它把错的口径又假设了一遍）。
    #   判据不许对被测对象的口径做二次换算 —— 直接比下标。
    # [EN] ★★★ 2026-10-09: **index convention** changed from "1-based" to **0-based**.
    # [EN] was wrong **together with** `TAB_LLM = 2`: the constant actually points to "UI appearance",
    # [EN] yet this criterion still went green (it assumed the wrong convention yet again).
    # [EN] The criterion must not perform a second conversion on the convention of the object under test --
    # [EN] compare indices directly.
    _i = A.TAB_LLM
    ok &= rec('C1b ★★★ `TAB_LLM` 真的指着「LLM 接入」那一页（**0 起算**，直接比下标）',
              bool(_titles) and 0 <= _i < len(_titles)
              and _titles[_i] == 'AI模型配置',
              f'TAB_LLM={_i}｜页签顺序={_titles}')
    ok &= rec('C1c ★★ 「常规」排在**第一**个（用户要求放在「LLM 接入」左边）',
              bool(_titles) and _titles[0] == '常规', str(_titles[:2]))
    return ok


# ══════════════════════════════════════════════════════════════
#  F. 真机 + 像素取证
# [EN] F. Real machine + pixel evidence
# ══════════════════════════════════════════════════════════════
def _count_magenta(png: bytes) -> int:
    """数"品红系"像素。半透明纸底上不能按原色匹配（见 `verify_model_probe`）。
        English:
    Count "magenta-family" pixels. On a semi-transparent paper background you cannot match by the
    original color (see `verify_model_probe`).
    """
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if r > 140 and b > 140 and g < r - 55 and g < b - 55:
                n += 1
    return n


async def test_gui(page) -> bool:
    with VU.env_guard():
        return await _test_gui(page)


async def _test_gui(page) -> bool:
    """★★ 铁律：新加的一块 UI，必须**像素确认它真的画出来了**。
        English:
    ★★ Iron rule: for any newly added piece of UI, you must **confirm by pixels that it is actually
    drawn**.
    """
    import flet as ft
    ok = True
    try:
        VU.isolate_projects_dir(Path(tempfile.mkdtemp(prefix='nws_llm_guide_')))
        from gui.app_flet import NovelWorldApp

        saved = {k: CFG.raw(k) for k in
                 ('LLM_BASE_URL', 'LLM_API_KEY', 'MOCK_LLM')}
        # 把 LLM 清空 → 走「没配」那条路（**在 app.main() 之前设**：
        # `main()` 里会读一次 `llm_ready()`，设晚了就来不及）。
        # ⚠ **`MOCK_LLM` 也要先关掉**：那段引导的判据是
        #   「没配好 **且** 演示模式不是用户自己开的」——
        #   要是这里先把 `MOCK_LLM` 设成 true，`_run_llm_readiness_check()`
        #   就会以为"用户早就选了演示模式"，于是**不置 `_mock_auto_on`**，
        #   引导框被合理地跳过（第一版就是这么"什么都没弹"的）。
        # [EN] Clear LLM -> go the "not configured" route (**set before app.main()**:
        # [EN] `main()` reads `llm_ready()` once; setting it later is too late).
        # [EN] ⚠ **`MOCK_LLM` must also be turned off first**: the criterion of that guide section is
        # [EN] "not configured **and** demo mode was not turned on by the user himself" --
        # [EN] if `MOCK_LLM` is set to true here first, `_run_llm_readiness_check()`
        # [EN] will think "the user already chose demo mode", so it **does not set `_mock_auto_on`**,
        # [EN] and the guide dialog is reasonably skipped (this is how the first version "popped up nothing").
        CFG.set('LLM_BASE_URL', '')
        CFG.set('LLM_API_KEY', '')
        CFG.set('MOCK_LLM', 'false')

        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.5)

        # `main()` 里已经调过一次 → 对话框应当在屏幕上。
        # ⚠ 用 `VU.open_dialogs(page)`：`page._dialogs` 是个 **`Dialogs` 对象**
        #   （不是 list，直接 `list(...)` 会 `TypeError: not iterable`），
        #   而且里面**还留着关掉的旧帧**，`open=True` 才是"此刻开着的"。
        # [EN] `main()` has already called it once -> the dialog should be on screen.
        # [EN] ⚠ Use `VU.open_dialogs(page)`: `page._dialogs` is a **`Dialogs` object**
        # [EN] (not a list, calling `list(...)` directly gives `TypeError: not iterable`),
        # [EN] and it **still retains old closed frames**; `open=True` is what is "currently open".
        dialogs = list(VU.open_dialogs(page))
        ok &= rec('F1 ★★ 启动后对话框真的开着（`open_dialogs` 非空）',
                  len(dialogs) >= 1, f'{len(dialogs)} 个')

        nodes: list = []

        def walk(c, d=0):
            if c is None or d > 30:
                return
            nodes.append(c)
            for a in ('content', 'controls', 'actions', 'title', 'label'):
                x = getattr(c, a, None)
                if isinstance(x, list):
                    for y in x:
                        walk(y, d + 1)
                elif x is not None and hasattr(x, '__class__'):
                    walk(x, d + 1)

        for d in dialogs:
            walk(d)
        blobs = [str(getattr(c, 'value', '') or '') for c in nodes]
        ok &= rec('F1 ★★ 标题「还没有配置 LLM」真的在控件树里',
                  any('还没有配置 LLM' == b for b in blobs),
                  str([b for b in blobs if 'LLM' in b][:3]))
        ok &= rec('F1 ★ 两个按钮都在控件树里',
                  any('去配置' == b for b in blobs) and any('以后再说' == b for b in blobs),
                  str([b for b in blobs if b in ('去配置', '以后再说')]))

        # ── 像素取证：把标题文字临时改成荧光品红（只动颜色不动几何）──
        # [EN] -- Pixel evidence: temporarily change the title text to fluorescent magenta (only color, not
        # [EN] geometry) --
        target = next((c for c in nodes if isinstance(c, ft.Text)
                       and str(getattr(c, 'value', '') or '') == '还没有配置 LLM'), None)
        ok &= rec('F2 找到了标题那个 Text 控件', target is not None, '')
        if target is not None:
            MAGENTA = '#ff00ff'
            keeper = target.color
            target.color = MAGENTA
            page.update()
            await asyncio.sleep(0.6)
            png = await page.take_screenshot()
            (OUT / 'llm_first_run_dialog.png').write_bytes(png)
            n = _count_magenta(png)
            ok &= rec('F2 ★★ 标题真的画在屏幕上（品红系像素 > 0）',
                      n > 0, f'{n} px')
            # 反例：清空文字再截一次，必须归零（否则判据恒真）
            # [EN] Counterexample: clear the text and capture again; it must go to zero (otherwise the criterion is
            # [EN] always true)
            keep_txt = target.value
            target.value = ''
            page.update()
            await asyncio.sleep(0.6)
            n2 = _count_magenta(await page.take_screenshot())
            ok &= rec('F2 ★★ 反例：清空文字后品红像素归零（判据不是恒真）',
                      n2 == 0, f'{n} → {n2} px')
            target.value = keep_txt
            target.color = keeper
            page.update()

        # ── 「以后再说」真的关掉对话框（端到端）──
        # [EN] -- "Later" really closes the dialog (end to end) --
        later = None
        for c in nodes:
            if getattr(c, 'on_click', None) and isinstance(getattr(c, 'content', None),
                                                           ft.Text):
                if str(c.content.value or '') == '以后再说':
                    later = c
        ok &= rec('F3 找到了「以后再说」按钮', later is not None, '')
        if later is not None:
            later.on_click(None)
            page.update()
            await asyncio.sleep(0.5)
            left = len(list(VU.open_dialogs(page)))
            ok &= rec('F3 ★★ 点「以后再说」→ 对话框真的关掉了',
                      left < len(dialogs), f'{len(dialogs)} → {left}')
            await page.take_screenshot()
            (OUT / 'llm_first_run_after_close.png').write_bytes(
                await page.take_screenshot())

        for k, v in saved.items():
            CFG.set(k, v)
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('真机段没有崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
    return ok


# ══════════════════════════════════════════════════════════════
#  G. 手册
# [EN] G. Manual
# ══════════════════════════════════════════════════════════════
def test_manual() -> bool:
    ok = True
    zh = (APP_DIR / '使用说明.md').read_text(encoding='utf-8')
    en = (APP_DIR / 'User_Manual.md').read_text(encoding='utf-8')
    ok &= rec('G1 ★★ 使用说明 2.4 覆盖用户点名的厂商',
              all(x in zh for x in ('DeepSeek', 'OpenAI', 'Claude', 'Google',
                                    '微软', 'GLM', '通义千问', 'MiniMax')),
              str([x for x in ('DeepSeek', 'OpenAI', 'Claude', 'Google', '微软',
                               'GLM', '通义千问', 'MiniMax') if x not in zh]))
    ok &= rec('G1 ★ 不止那几家（"包括且不限于"）：还列了 Kimi / 硅基流动 / '
              'OpenRouter / 本地',
              all(x in zh for x in ('Kimi', 'SiliconFlow', 'OpenRouter', 'Ollama')), '')
    # ★★ 判据钉在**每家的控制台网址**上，而不是"有没有出现 MiniMax 这个词"：
    #   厂商名在正文里还会再出现一次（"各家细节"的小标题），
    #   把表格那一行删掉时词还在 —— 那样的变异测不出来（反例法抓到的）。
    # [EN] ★★ The criterion is pinned on **each vendor's console URL**, not on "whether the word MiniMax
    # [EN] appears":
    # [EN] the vendor name also appears again in the body text (the "per-vendor details" subheading),
    # [EN] so when the table row is deleted the word is still there -- that mutation cannot be detected
    # [EN] (caught by the counterexample method).
    _consoles = ('platform.deepseek.com', 'platform.openai.com',
                 'console.anthropic.com', 'aistudio.google.com',
                 'portal.azure.com', 'open.bigmodel.cn',
                 'bailian.console.aliyun.com', 'platform.minimaxi.com')
    ok &= rec('G1 ★★ 八家的**控制台网址**都在（少一家就红）',
              all(u in zh for u in _consoles),
              str([u for u in _consoles if u not in zh]))
    ok &= rec('G1 ★ 每家都给了 **Base URL**（`https://` 出现次数够多）',
              zh.count('https://') >= 16, str(zh.count('https://')))
    ok &= rec('G1 ★ 讲清了这个程序只认 OpenAI 兼容协议（含 Claude 的例外）',
              'OpenAI 兼容' in zh and '不是** OpenAI 协议' in zh.replace('**', '**'), '')
    ok &= rec('G2 ★★ 有「3.4 怎么把 Key 配进来」这一节',
              '### 3.4 怎么把 Key 配进来' in zh, '')
    ok &= rec('G2 ★★ 那一节讲了界面三步（天机 → 拉取模型列表 → 测试 → 保存重启）',
              all(x in zh for x in ('天机', '拉取模型列表', '测试', '保存', '重启')),
              '')
    ok &= rec('G2 ★ 也给了直接改 `.env` 的写法', 'LLM_API_KEY=sk-你的key' in zh, '')
    ok &= rec('G2 ★ 说了"没配好会怎样"（自动降级 + 下次还提醒）',
              '把演示模式打开' in zh and '下次启动还会提醒' in zh, '')
    ok &= rec('G3 ★ 英文版同步（`User_Manual.md`）',
              all(x in en for x in ('### 3.4 How to Plug the Key In',
                                    'Anthropic (Claude)', 'MiniMax', 'Zhipu GLM')),
              '')
    return ok


def _finish(ok: bool) -> None:
    report['ok'] = bool(ok)
    (OUT / 'llm_first_run_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])


if __name__ == '__main__':
    print('「第一次跑还没配 LLM」的引导 —— 验证', flush=True)
    # ⚠ 这个脚本**两用**：不带参数 → 只跑逻辑段；
    #   由 `run_py_file` 以 `--gui` 起 Flet 时会进真机段（见下）。
    # [EN] ⚠ This script is **dual-purpose**: no args -> only run the logic section;
    # [EN] when started as Flet with `--gui` by `run_py_file`, it enters the real-machine section (see
    # [EN] below).
    want_gui = '--gui' in sys.argv
    ok = True
    try:
        if not want_gui:
            head('A. 该不该弹（没配 / 配好 / 用户自己开演示模式）')
            ok &= test_should_pop()
            head('B/D/E. 两个按钮 + 常驻消息 + 文案指路')
            ok &= test_buttons()
            head('C. 天机的落点（selected_index 夹取）')
            ok &= test_tab_index()
            head('F0. 主线接线（`main()` 真的调了它）')
            ok &= test_main_wiring()
            head('G. 手册（2.4 厂商清单 / 3.4 怎么配 / 英文版同步）')
            ok &= test_manual()
            _finish(ok)
            sys.exit(0 if report['ok'] else 2)
    except Exception:
        report['fatal'] = traceback.format_exc()
        rec('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        ok = False
        _finish(ok)
        sys.exit(2)

    # ── 真机段 ──
    # [EN] -- Real-machine section --
    import verify_ui_common as VU                               # noqa: E402
    import flet as ft                                          # noqa: E402

    async def _main(page):
        # ★★ 顺序是**硬约束**（`util/flet_shutdown` 的模块注释里记着这条）：
        #   ① 跑验证 → ② **写报告 / 打印** → ③ `await shutdown(...)` → ④ `exit_now()`。
        #   反过来的话报告永远写不出来：`page.window.destroy()` 会**取消当前协程**
        #   并抛 `asyncio.CancelledError`（`BaseException`，`except Exception` 抓不住），
        #   后面一行都不会执行（第一版就是这么"什么都没输出"的）。
        # [EN] ★★ The order is a **hard constraint** (recorded in the module comment of `util/flet_shutdown`):
        # [EN] ① run verification -> ② **write report / print** -> ③ `await shutdown(...)` -> ④ `exit_now()`.
        # [EN] In reverse the report can never be written: `page.window.destroy()` will **cancel the current
        # [EN] coroutine**
        # [EN] and raises `asyncio.CancelledError` (`BaseException`, `except Exception` cannot catch it),
        # [EN] none of the following lines will execute (that is exactly how the first version ended up
        # [EN] "outputting nothing").
        ok2 = await test_gui(page)
        report['ok'] = bool(ok2)
        passed = sum(1 for c in report['checks'] if c['ok'])
        failed = [c['name'] for c in report['checks'] if not c['ok']]
        (OUT / 'llm_first_run_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
              + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
              flush=True)
        if report.get('fatal'):
            print('\n⚠ 中途崩溃：\n' + report['fatal'][-1500:], flush=True)
        from util.flet_shutdown import exit_now, shutdown
        await shutdown(page, code=0 if report['ok'] else 2)
        exit_now(0 if report['ok'] else 2)

    ft.run(_main)
