# -*- coding: utf-8 -*-
"""真机验证：**用量对话框的「×」与「删掉一个项目」**（用户 2026-10-10 的两条要求）。

用户原话
--------
「LLM用量对话框右上角加一个关闭按钮 最左边一列的内容允许删除」

为什么必须真机、而且必须**真点**
--------------------------------
这两件事全都是**控件树上的事实**：

  · 「右上角有没有一个关闭按钮」—— 静态查源码只能查到"定义过一个按钮"，
    查不出它有没有被拼进**标题那一行**、更查不出它点下去收的是**哪一层**对话框；
  · 「左栏那一项能不能删」—— 静态查只能看到"有个 `on_delete` 参数"，
    查不出「软件整体」那一条**没有**删除按钮（那正是最要紧的一半：
    汇总行给删等于把整本账的口子开了）。

所以这一支走真机 + 真调 `on_click`，并且**每一步都验数据**：
    点垃圾桶 ⇒ ①必须**先弹确认框**、②这时库里**一条都没少**（"先问再删"）
              ⇒ 点「取消」⇒ ③还是没少
              ⇒ 再点垃圾桶、点「确认删除」⇒ ④这个项目没了、另一个项目**一条不少**

★ 「先问再删」为什么值得单独一条：删台账是不可恢复的。一个"点了就删"的实现
  同样能让"能删掉"这条断言变绿 —— 所以**必须**把"还没确认时数据不许动"
  也断言出来，否则这条判据护不住最要紧的那件事。
★ 找控件一律按**用户看得见的东西**找（按钮上那个「确认删除」的字、
  垃圾桶上那句 tooltip），不按变量名 —— 按变量名找的判据，改个名字就失效，
  而"改个名字就不查了"和"本来就没问题"长得一模一样。

跑法：`.venv/Scripts/python.exe tools/verify_usage_delete.py`
产出：assets/screenshots/usage_delete_report.json

English:
Real-device verification: **the usage dialog's "×" and "delete a project"** (the user's two
requirements from 2026-10-10).
User's own words
--------
"Add a close button to the top-right of the LLM usage dialog; allow deleting items in the
leftmost column"
Why it must be on a real device, and must be **really clicked**
--------------------------------
Both of these are **facts about the widget tree**:
  · "Is there a close button in the top-right" -- statically inspecting the source can only find "a button was defined",
    it can't tell whether it got assembled into the **title row**, let alone which **layer** of dialog it closes when clicked;
  · "Can that item in the left column be deleted" -- statically inspecting only shows "there's an `on_delete` parameter",
    it can't tell that the "软件整体" row **has no** delete button (and that's the more important half:
    giving the summary row a delete is opening a hole in the entire ledger).
So this branch goes real-device + really calling `on_click`, and **verifies the data at every
step**:
    Click the trash can ⇒ ① must **pop a confirmation box first**, ② at this point not one entry fewer in the DB ("ask before delete")
              ⇒ click "Cancel" ⇒ ③ still not one fewer
              ⇒ click the trash can again, click "Confirm delete" ⇒ ④ this project is gone, the other project **not one entry fewer**
★ Why "ask before delete" deserves its own line: deleting ledger entries is irreversible. An
implementation that "deletes on click"
  would also make the "can be deleted" assertion green -- so it's **mandatory** to also assert that "while not yet confirmed, data must not move",
  otherwise this assertion doesn't protect the thing that matters most.
★ Always find widgets by **what the user can see** (the "确认删除" text on the button,
  the tooltip on the trash can), not by variable name -- an assertion that finds by variable name breaks when the name changes,
  and "doesn't check anymore because the name changed" looks exactly like "there was never a problem".
How to run: `.venv/Scripts/python.exe tools/verify_usage_delete.py`
Output: assets/screenshots/usage_delete_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
# ⚠ 起了界面的脚本**第一件事就是禁写真实 `.env``**（本项目的老教训）
# [EN] ⚠ The first thing a script that brings up the UI must do is **disable writing to the real
# [EN] `.env`** (a hard lesson from this project)
VU.redirect_env_writes()

from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang, t  # noqa: E402

#: 两个**中性**项目名（`verify_generic_project` 盯着：判据里不许出现真实书名）。
# [EN] : two **neutral** project names (`verify_generic_project` watches: no real book title may appear
# [EN] in the assertions).
PA, PB = '甲项目', '乙项目'

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'steps': []}


def rec(name: str, ok, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(f'  {"✓" if ok else "✗"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return bool(ok)


def _del_buttons(root) -> dict:
    """左栏里"可删的那一项" —— 按 `tooltip` 找（用户看得见的那句），
    再从按钮上的抓手 `_del_scope` 读它是哪个项目。

    ⚠ 两样都要：**按 tooltip 找**保证"它是个用户看得见的删除口子"，
    **读抓手**保证"这一条对应哪个项目"是确定的（靠文字反推是脆的）。
    
        English:
    The "deletable item" in the left column -- find it by `tooltip` (the phrase the user can see),
        then read from the button's handle `_del_scope` which project it is.
        ⚠ Both are needed: **finding by tooltip** guarantees "it's a user-visible delete entry point",
        **reading the handle** guarantees "which project this row corresponds to" is determinate (inferring from text is brittle).
    """
    out: dict = {}
    for c in VU.walk(root):
        tip = str(getattr(c, 'tooltip', '') or '')
        if tip and tip == t('删除这个项目的用量记录'):
            out[str(getattr(c, '_del_scope', '?'))] = c
    return out


def _close_buttons(root) -> list:
    """标题行里那个「×」：tooltip 是「关闭」、内容是一个 CLOSE 图标。

    ⚠ 图标名在 `ft.Icon.icon` 上 —— **不是 `.name`**（第一版按 `.name` 取，
      当场 `AttributeError`。`ft.Icon` 是 Flet 1.0 的控件，别照 Qt/其它库的习惯猜）。
    
        English:
    The "×" in the title row: the tooltip is "关闭" and the content is a CLOSE icon.
        ⚠ The icon name is on `ft.Icon.icon` -- **not `.name`** (the first version read `.name`,
          and got an `AttributeError` on the spot. `ft.Icon` is a Flet 1.0 widget, don't guess by Qt/other libraries' habits).
    """
    out = []
    for c in VU.walk(root):
        if str(getattr(c, 'tooltip', '') or '') != t('关闭'):
            continue
        icon = getattr(c, 'content', None)
        if isinstance(icon, ft.Icon) and getattr(icon, 'icon', None) == ft.Icons.CLOSE:
            out.append(c)
    return out


def _btn_by_text(root, text: str) -> list:
    """按**按钮上那几个字**找按钮（`content` 是 `ft.Text` 的那种）。
        English:
    Find the button by **the text on the button** (the kind where `content` is an `ft.Text`).
    """
    out = []
    for c in VU.walk(root):
        if isinstance(c, ft.Control) and getattr(c, 'on_click', None) is not None:
            label = VU.text_of(c)
            if label == text:
                out.append(c)
    return out


def _col4_title(root) -> str:
    """第 4 栏栏头那行小字（"现在看的是哪一块"）。

    ★ 2026-10-11 改过一次认法：这个标题原来在**内容区顶部**（这一窗里唯一
      `size=14` 的 Text，所以按字号认它），后来用户要求"筛选放到每个列的表头上"，
      它跟着**搬进了第 4 栏的栏头小字**（栏头钉住、内容滚走 —— 标题本来就不该跟着滚）。
      ⇒ 旧认法当场失效（这条判据假红了两项）。

    ★ 现在的认法挂在**栏号抓手** `_usage_pane` 上（`gui/usage_dialog._pane` 打的）：
      先找到第 4 栏，再取它栏头里的最后一行小字。这个抓手 `verify_usage_filters`
      也在用 —— **一处抓手、两支判据**，比按字号认结实得多（字号是审美，会变）。
    
        English:
    The small text on the 4th column's header row ("which block are we looking at now").
        ★ Changed the recognition method once on 2026-10-11: this title was originally at the **top of the content area** (the only
          Text with `size=14` in this window, so it was recognized by font size), later the user requested "put the filters on each column's header",
          so it **moved into the small text of the 4th column's header** (headers pin, content scrolls away -- a title shouldn't scroll along anyway).
          ⇒ The old recognition method immediately became invalid (this criterion falsely failed two items).
        ★ The current recognition method hangs on the **column-number handle** `_usage_pane` (set by `gui/usage_dialog._pane`):
          first find the 4th column, then take the last line of small text in its header. This handle `verify_usage_filters`
          is also using -- **one handle, two criteria**, far more robust than recognizing by font size (font size is aesthetics, it changes).
    """
    for c in VU.walk(root):
        if getattr(c, '_usage_pane', None) != 4:
            continue
        body = getattr(c, 'content', None)
        kids = list(getattr(body, 'controls', None) or [])
        if not kids:
            return ''
        texts = [x for x in VU.walk(kids[0]) if isinstance(x, ft.Text)]
        return str(texts[-1].value or '') if texts else ''
    return ''


async def _wait_layers(page, want: int, *, seconds: float = 6.0) -> int:
    """等对话框层数涨到 `want`（返回最终层数）。

    ★ 为什么不 `await asyncio.sleep(0.9)` 就断言（第一版就是这么写的，**真的偶发红过**）：
      Flet 的对话框是**异步刷**的，而这里的每一次"点击"都是**直接调回调**
      （不是走框架的事件循环）⇒ 弹框落在哪一帧**不确定**。
      固定 sleep 于是变成看运气：同一份代码连跑三次，有一次报
      「点垃圾桶**先弹确认框**」失败（层数还是 1）—— 而代码一点问题都没有。
      这类"偶发红"比假绿还坏：**看到的人会当成环境抖动，然后学会忽略它**。
      ⇒ 一律轮询到条件成立（最长 `seconds`），等不到才算真红。
    
        English:
    Wait until the dialog layer count rises to `want` (returns the final layer count).
        ★ Why not just `await asyncio.sleep(0.9)` then assert (the first version was written that way, and it **really did intermittently fail**):
          Flet's dialogs are **refreshed asynchronously**, and every "click" here is a **direct call to the callback**
          (not going through the framework's event loop) ⇒ which frame the popup lands on is **indeterminate**.
          A fixed sleep thus becomes a gamble: running the same code three times in a row, one time it reported
          "clicking the trash can **pops the confirmation dialog first**" as a failure (layer count still 1) -- yet the code had no problem at all.
          This kind of "intermittent failure" is worse than a false green: **people who see it treat it as environmental flakiness, then learn to ignore it**.
          ⇒ Always poll until the condition holds (up to `seconds`), and only count it as a real failure if it never holds.
    """
    deadline = seconds
    step = 0.15
    n = 0
    while deadline > 0:
        n = len(VU.open_dialogs(page))
        if n >= want:
            return n
        await asyncio.sleep(step)
        deadline -= step
    return len(VU.open_dialogs(page))


async def _click_until(page, click, want: int, *, tries: int = 2) -> int:
    """点一下、等层数涨上来；没涨就再点一次（再等）。返回最终层数。
        English:
    Click once, wait for the layer count to rise; if it didn't rise, click again (and wait again).
    Returns the final layer count.
    """
    n = 0
    for _ in range(max(1, tries)):
        click()
        page.update()
        n = await _wait_layers(page, want)
        if n >= want:
            return n
    return n


async def main(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_usgdel_'))
    VU.isolate_projects_dir(tmp / 'Projects')

    # ── 台账库指到临时文件，并塞两笔（**不许碰用户真正的 usage.db**）──
    # [EN] ── Point the ledger DB at a temp file and insert two entries (**must not touch the user's real
    # [EN] usage.db**) ──
    from llm import usage as U
    db = tmp / 'usage.db'
    U.db_path = lambda: db                     # 本次进程内改指向（判据专用）
    # [EN] Redirect within this process (for the assertions only)
    for p, c in ((PA, 0.20), (PB, 0.05)):
        assert U.record(model='deepseek-chat', purpose='crew_novelist',
                        in_tok=1000, out_tok=200, cost=c, module='NovelWorldSimulator',
                        project=p, run='第1次模拟', agent='小说作家', path=db)

    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(1.6)

    def _top():
        for d in reversed(VU.open_dialogs(page)):
            if isinstance(d, ft.AlertDialog):
                return d
        return None

    try:
        # ── 打开用量对话框 ──
        # [EN] ── Open the usage dialog ──
        app.show_usage_dialog()
        await asyncio.sleep(1.2)
        dlg = _top()
        if dlg is None:
            rec('用量对话框能打开', False, '没有对话框')
            raise RuntimeError('打不开')
        rec('用量对话框能打开', True, f'尺寸 {getattr(dlg.content, "width", None)}')

        # ── ① 关闭按钮 ──
        # [EN] ── ① Close button ──
        closes = _close_buttons(dlg)
        rec('★ 「×」在标题行里找得到（按 tooltip「关闭」+ CLOSE 图标找）',
            len(closes) == 1, f'找到 {len(closes)} 个')
        # 位置：它必须在**标题那一行**里，而不是被塞在工具栏中间
        # [EN] Location: it must be in the **title row**, not stuffed into the middle of the toolbar
        title_row = None
        for c in VU.walk(dlg):
            if isinstance(c, ft.Row) and any(cc in closes for cc in (c.controls or [])):
                title_row = c
                break
        title_txt = None
        if title_row is not None:
            for cc in title_row.controls:
                if isinstance(cc, ft.Text) and cc.value == t('LLM 用量'):
                    title_txt = cc
        rec('★★ 「×」与标题**同在一行**（所以它在对话框的右上/左上角，'
            '不是夹在工具栏中间）',
            title_row is not None and title_txt is not None,
            (f'那一行有 {len(title_row.controls)} 个控件、标题'
             f'{"在" if title_txt is not None else "**不在**"}里面'
             if title_row is not None else '**没找到挂着「×」的那一行**'))
        # 点它：应当**只收掉用量窗**（叠着确认框时收的是最上面那层）
        # [EN] Click it: it should **only close the usage window** (when a confirmation box is stacked on top,
        # [EN] it closes the topmost layer)
        closes[0].on_click(None)
        page.update()
        gone = 0.0
        while gone < 5.0 and _top() is not None:
            await asyncio.sleep(0.15)
            gone += 0.15
        rec('★★ 点「×」真的把窗口关掉了（对话框栈清空）',
            _top() is None, f'还剩 {len(VU.open_dialogs(page))} 层')

        # ── ② 左栏：哪些能删 ──
        # [EN] ── ② Left column: what can be deleted ──
        app.show_usage_dialog()
        await asyncio.sleep(1.0)
        dlg = _top()
        dels = _del_buttons(dlg)
        rec('★★ 左栏里**两个项目**各有一个删除按钮',
            {PA, PB} <= set(dels), f'找到 {sorted(dels)}')
        rec('★★★ 「软件整体」那一条**没有**删除按钮'
            '（它是汇总，不是一条可删的记录 —— 给了等于把整本账的口子开了）',
            t('软件整体') not in dels and '软件整体' not in dels
            and len(dels) == 2, f'可删的={sorted(dels)}')

        # ── ③ 点垃圾桶 ⇒ 先问，且**一条都没少** ──
        # [EN] ── ③ Click the trash can ⇒ ask first, and **not one entry fewer** ──
        before = U.totals(path=db)['calls']
        n_layer = await _click_until(page, lambda: dels[PA].on_click(None), 2)
        rec('★★★ 点垃圾桶**先弹确认框**（不是点一下就删）',
            n_layer >= 2 and _top() is not dlg,
            f'对话框层数 {n_layer}')
        confirm = _btn_by_text(_top(), t('确认删除')) if _top() else []
        rec('★ 确认框上有「确认删除」这个按钮（按界面上那几个字找）',
            len(confirm) == 1, f'找到 {len(confirm)} 个')
        rec('★★★ **还没确认的时候，库里一条都没少**'
            '（"能删掉"这条断言挡不住"点了就删"的实现，所以这条必须单独存在）',
            U.totals(path=db)['calls'] == before,
            f"{before} → {U.totals(path=db)['calls']}")

        # ── ④ 点「取消」⇒ 还是没少 ──
        # [EN] ── ④ Click "Cancel" ⇒ still not one fewer ──
        cancel = _btn_by_text(_top(), t('取消')) if _top() else []
        if cancel:
            cancel[0].on_click(None)
        else:
            page.pop_dialog()
        page.update()
        await _wait_layers(page, 1)          # 等确认框收掉
        # [EN] Wait for the confirmation box to close
        rec('★★ 确认框里点「取消」⇒ 什么都不会发生（数据一条不少）',
            U.totals(path=db)['calls'] == before
            and [x['name'] for x in U.projects(path=db)] == [PA, PB],
            f"现在 {U.totals(path=db)['calls']} 条，"
            f"项目={[x['name'] for x in U.projects(path=db)]}")

        # ── ⑤ 真确认 ⇒ 这个项目没了，另一个一条不少 ──
        # ⚠ 重新打开：取消那一步可能已经把窗口收掉了（`_confirm_danger` 是与用量窗
        #   **叠着**的，取消只收它自己；但不同实现可能整条关掉）。重开最稳。
        # [EN] ── ⑤ Really confirm ⇒ this project is gone, the other one not one entry fewer ──
        # [EN] ⚠ Reopen: the cancel step may already have closed the window (`_confirm_danger` is
        # [EN] **stacked on top of** the usage window, so cancel only closes itself; but other implementations
        # [EN] might close the whole thing). Reopening is the safest.
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()
        app.show_usage_dialog()
        await asyncio.sleep(1.0)
        dlg = _top()
        want_ab = U.totals(PA, path=db)['calls']
        n_layer = await _click_until(
            page, lambda: _del_buttons(dlg)[PA].on_click(None), 2)
        confirm = _btn_by_text(_top(), t('确认删除')) if _top() else []
        rec('★ 重新点开确认框（准备真删）', len(confirm) == 1,
            f'层数 {n_layer}')
        confirm[0].on_click(None)
        page.update()
        # 删是**同步 SQL**，但要等界面刷完再断言（别拿旧控件树去断"界面上没了"）
        # [EN] Deletion is **synchronous SQL**, but assert only after the UI has refreshed (don't use a stale
        # [EN] widget tree to assert "it's gone from the UI")
        for _ in range(20):
            if PA not in [x['name'] for x in U.projects(path=db)]:
                break
            await asyncio.sleep(0.15)
        await asyncio.sleep(0.3)
        left = [x['name'] for x in U.projects(path=db)]
        rec(f'★★★ 点「确认删除」之后，{PA} 的 {want_ab} 条记录真的没了',
            PA not in left, f'剩下的项目={left}')
        rec('★★★ 另一个项目**一条不少**（删的是那一个，不是"清一片"）',
            U.totals(PB, path=db)['calls'] == 1,
            f"乙项目 {U.totals(PB, path=db)['calls']} 条")
        dlg = _top()
        left_ui = _del_buttons(dlg) if dlg is not None else {}
        rec('★★ 界面上左栏也跟着没了（不是只删了库、界面还留着那一行）',
            PA not in left_ui, f'界面上可删的={sorted(left_ui)}')

        # ── ⑥ 删掉的正是当前选中项 ⇒ 退回「软件整体」，别停在空范围上 ──
        #   （上面删 PA 之前并没有选中它 —— 这里显式选一次再删，验那条退路。）
        # [EN] ── ⑥ The deleted item is exactly the currently selected one ⇒ fall back to "Software overall",
        # [EN] don't sit on an empty scope ──
        # [EN] (Before deleting PA above, it wasn't selected -- select it explicitly once here, then delete, to
        # [EN] verify that fallback.)
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()
        # 再造一个项目来删，免得把断言建立在"已经删过一次"的库上
        # [EN] Create another project to delete, so the assertion isn't built on a DB that has "already been
        # [EN] deleted from once"
        U.record(model='deepseek-chat', purpose='crew_novelist', in_tok=10,
                 out_tok=5, cost=0.01, module='NovelWorldSimulator', project='丙项目',
                 run='第1次模拟', agent='小说作家', path=db)
        app.show_usage_dialog()
        await asyncio.sleep(1.0)
        dlg = _top()
        rows = [c for c in VU.walk(dlg)
                if isinstance(c, ft.Text) and c.value == '丙项目']
        if not rows:
            rec('（再造一个项目来验"删掉当前选中项"这条退路）', False, '没找到丙项目那一行')
        else:
            # 选中它（那一行的可点主体就是它的父容器链上挂 on_click 的那个）
            # [EN] Select it (the clickable body of that row is whatever has on_click attached up its
            # [EN] parent-container chain)
            hit = None
            for c in VU.walk(dlg):
                if (getattr(c, 'on_click', None) is not None
                        and isinstance(getattr(c, 'content', None), ft.Column)
                        and any(isinstance(x, ft.Text) and x.value == '丙项目'
                                for x in VU.walk(c))):
                    hit = c
            if hit is not None:
                hit.on_click(None)
                page.update()
                await asyncio.sleep(0.5)
            # ★ 前提**必须在这里读**（删之前）。第一版读在了删除**之后** ——
            #   那时范围本来就该是「软件整体」，于是"前提"永远是错的
            #   （正确代码上反而红）。顺序错了的判据比没有判据更误导人。
            # [EN] ★ The precondition **must be read here** (before deletion). The first version read it **after**
            # [EN] deletion --
            # [EN] at which point the scope should already be "Software overall", so the "precondition" is always
            # [EN] wrong
            # [EN] (and it goes red on correct code instead). An assertion with the order wrong is more misleading
            # [EN] than no assertion at all.
            sel_title = _col4_title(_top() or dlg)
            rec('★ 前提：先把这个项目**选上**（不选中的话下面那条测不到东西）',
                sel_title == '丙项目', f'第 4 栏标题={sel_title!r}')
            await _click_until(
                page, lambda: _del_buttons(_top() or dlg)['丙项目'].on_click(None), 2)
            cs = _btn_by_text(_top(), t('确认删除')) if _top() else []
            if cs:
                cs[0].on_click(None)
                page.update()
                for _ in range(20):
                    if '丙项目' not in [x['name'] for x in U.projects(path=db)]:
                        break
                    await asyncio.sleep(0.15)
                await asyncio.sleep(0.3)
            after = _top() or page
            ui = VU.all_texts(after)
            # ★★ 真正能分辨的观测量：**界面上的字**。
            #    原来这条写的是「`t('软件整体')` 在不在界面文字里」——那是**装饰品**：
            #    「软件整体」是左栏的第一行、**任何时候都在**，所以它恒为真
            #    （反例法 U04 当场证明：把 `_pick_scope(None)` 换成 `refresh_all()`
            #     之后它照样绿）。改成"那个项目的名字在界面上还找不找得到"——
            #    不退回的话，第 4 栏标题**还挂着它的名字**（只有那一处会露出来）。
            # [EN] ★★ The observable that can actually distinguish: **the text on the UI**.
            # [EN] Originally this line read "is `t('软件整体')` present in the UI text" -- that's an **ornament**:
            # [EN] "软件整体" is the first row of the left column, **present at all times**, so it's always true
            # [EN] (the counterexample method U04 proved it on the spot: replace `_pick_scope(None)` with
            # [EN] `refresh_all()`
            # [EN] and it still goes green). Change it to "can that project's name still be found on the UI" --
            # [EN] if it doesn't fall back, column 4's title **still carries its name** (that's the only place it
            # [EN] shows).
            rec('★★★ 删掉的正是**当前选中**的项目时，范围退回「软件整体」'
                '（不退回的话第 4 栏标题还挂着那个已经不存在的项目名，'
                '四栏也会全空，看起来像坏了）',
                (sel_title == '丙项目')
                and _col4_title(after) == t('软件整体')
                and '丙项目' not in ui,
                f'第 4 栏标题={_col4_title(after)!r}；'
                f"界面上还提到「丙项目」={'丙项目' in ui}")
    except Exception as e:                                         # noqa: BLE001
        import traceback
        report['steps'].append({'name': '判据自己崩了（**算红**）', 'ok': False,
                                'detail': traceback.format_exc()[-900:]})
        print('  ✗ 判据自己崩了：', repr(e)[:200], flush=True)
    finally:
        while VU.open_dialogs(page):
            page.pop_dialog()

    bad = [s for s in report['steps'] if not s['ok']]
    report['ok'] = not bad
    (OUT / 'usage_delete_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n  用量「关闭 + 删除」验证：'
          f'{len(report["steps"]) - len(bad)}/{len(report["steps"])}')
    for s in bad:
        print(f'  ✗ {s["name"]}  {s["detail"]}')
    await shutdown(page, code=0 if not bad else 2)


if __name__ == '__main__':
    ft.run(main)
