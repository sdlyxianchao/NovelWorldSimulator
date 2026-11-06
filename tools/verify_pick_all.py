# -*- coding: utf-8 -*-
"""判据：拾卷两栏（① 小说 / ② 存档）的**「全选」**（2026-10-31 用户）。

用户原话：「拾卷里 2个Tab的小说和存档都加上全选功能」。

★ 为什么要**真机**、不能只测数据层
  这个功能整条链都在回调里：点方框 → `_bulk_toggle` → 逐个走 `_run_toggle` 级联 →
  `_sel_refresh` 改按钮文字 → `_bulk_paint` 改三档图标。数据层（`sel` 那个字典）
  一条都不会动 —— 它只在点击的那一瞬间存在。**点一下、读回来**是唯一的判法。

★ 判的是**四件**不同的事，不是"点了没报错"
  ① **算数**：勾上 N 个，栏头必须写着 N（`删除选中（N）`）—— 抓"全选了但没刷新"；
  ② **三档**：空 / 部分 / 全选 三种图标和实际勾选数必须对得上 —— 抓"图标恒空"
     （那样用户会以为点了没生效）；
  ③ **级联**：存档栏全选之后，**子节点要跟着锁灰**。全选若绕过 `_run_toggle`
     直接 `force(True)`，图标看着对、字也对，但父节点一取消，子节点就留在半空；
  ④ **清空**：再点一次要回到「删除选中」并且**解锁** —— 抓 `_sel_clear` 只做一半
     （只 `force(False)` 不解锁 ⇒ 子节点永远点不亮，用户只能关掉对话框重开）。

★ 反例（`F` 组）：三档图标的判读函数自己先量一遍
  否则"图标 == CHECK_BOX"这类断言可能是**恒真**的（读到一个 None 也算不等）。
  这里是纯函数自检，不碰产品。

产出：assets/screenshots/pick_all_report.json
用法：.venv/Scripts/python.exe tools/verify_pick_all.py

English:
Criterion: the **"select all" box** in both columns of Pick-a-Volume (2026-10-31 user).
★ Why it must be a **real device** test: the whole chain lives in callbacks -- click the box ->
`_bulk_toggle` -> `_run_toggle` cascade per node -> `_sel_refresh` rewrites the button label ->
`_bulk_paint` repaints the three-state icon. Nothing in the data layer moves; the selection dict
only exists for the duration of a click. "Click it and read it back" is the only way.
★ Four separate things are judged: ① arithmetic (tick N => header reads N); ② three states
(empty/partial/all must match the real count); ③ cascade (children of a ticked parent must be
locked -- a bare `force(True)` looks right and reads right but leaves children floating);
④ clearing (the second click must reselect nothing **and unlock** -- a half-done `_sel_clear`
leaves children unclickable forever).
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))
sys.path.insert(0, str(APP / 'gui'))

import flet as ft                                      # noqa: E402

import verify_ui_common as VU                          # noqa: E402
from tools.verify_exit import finish                   # noqa: E402

OUT = Path('assets/screenshots')
OUT.mkdir(parents=True, exist_ok=True)

results: list[dict] = []
report: dict = {'checks': results}


def rec(name: str, ok_, detail='') -> None:
    results.append({'name': name, 'ok': bool(ok_), 'detail': str(detail)})
    print(('  ✓ ' if ok_ else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)


# ══════════════════════════════════════════════════════════
#  读控件（三档图标 / 按钮文字 / 方框状态）
# [EN] Reading the controls (three-state icon / button label / box state)
# ══════════════════════════════════════════════════════════
def _bulk_mode(box) -> str:
    """「全选」框现在是哪一档：`all` / `some` / `none`（读不出来时返回 `?<图标>`）。"""
    icon = getattr(getattr(box, 'content', None), 'icon', None)
    if icon == ft.Icons.CHECK_BOX:
        return 'all'
    if icon == ft.Icons.INDETERMINATE_CHECK_BOX:
        return 'some'
    if icon == ft.Icons.CHECK_BOX_OUTLINE_BLANK:
        return 'none'
    return f'?{icon}'


def _multi_label(box) -> str:
    """栏头那颗红按钮上的字（Flet 1.0 里在 `content` 那个 `Row` 的 `Text` 上）。"""
    row = getattr(box, 'content', None)
    for c in (getattr(row, 'controls', None) or []):
        if isinstance(c, ft.Text):
            return c.value or ''
    return ''


def _chk_on(chk) -> bool:
    """方框勾上没有（`mk_node_check` 把真相当在 `content` 那颗 `Icon` 的 `icon` 上）。"""
    return getattr(getattr(chk, 'content', None), 'icon', None) == ft.Icons.CHECK_BOX


def _chk_color(chk) -> str:
    return str(getattr(getattr(chk, 'content', None), 'color', ''))


# ══════════════════════════════════════════════════════════
#  夹具：两本书（甲：3 轮一条链；乙：2 轮两个根）
# [EN] Fixture: two books (A: a 3-run chain; B: two roots)
# ══════════════════════════════════════════════════════════
def _make(root: Path, name: str, n: int, *, chain: bool, tag: str):
    """造一本书 + `n` 轮存档，返回存档名清单（顺序 = 生成顺序）。

    ★ 甲书用**链**（1 → 2 → 3）：全选的级联只有"有父有子"时看得出来。
    ★ 乙书用**两个根**：只有多个根才可能点到「部分」那一档 —— 一条链上
      勾任何一个都会把整条链带上，永远看不到"some"。
    [EN] Book A is a **chain** (1 -> 2 -> 3): the cascade only shows up with real parents.
    [EN] Book B has **two roots**: "some" is unreachable on a chain (ticking any node drags the
    [EN] whole chain along).
    """
    from store import lineage as LG
    from store.project import Project

    proj = Project.create_new(root, name)
    names: list[str] = []
    prev = None
    for i in range(1, n + 1):
        nm = f'{tag}第{i}次模拟2026-10-0{i}-10-00'
        r = proj.root / nm
        (r / '每天的生活').mkdir(parents=True, exist_ok=True)
        (r / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n这是 {tag}{i} 的正文。院外土路车轱辘声一阵一阵。\n',
            encoding='utf-8')
        (r / 'state.db').write_text('', encoding='utf-8')
        parent = prev if chain else None
        LG.write_lineage(r, parent=parent, kind='resume' if parent else 'fresh')
        names.append(nm)
        prev = nm
    return proj, names


# ══════════════════════════════════════════════════════════
#  真机
# [EN] Real device
# ══════════════════════════════════════════════════════════
async def _render(page: ft.Page) -> None:
    import gui.app_flet as G

    def _scan(content):
        """收一遍控件树：两栏的全选框 / 红按钮 / 节点方框 / 小说卡。"""
        out = {'bulk': {}, 'multi': {}, 'chks': [], 'novels': []}

        def _walk(c, depth=0):
            if depth > 24 or c is None:
                return
            k = getattr(c, '_bulk_kind', None)
            if k:
                out['bulk'].setdefault(k, c)
            k = getattr(c, '_multi_kind', None)
            if k:
                out['multi'].setdefault(k, c)
            k = getattr(c, '_node_kind', None)
            if k:
                out['chks'].append((k, getattr(c, '_node_name', ''), c))
            if getattr(c, '_proj', None) is not None:
                out['novels'].append(c)
            v = getattr(c, 'controls', None)
            if isinstance(v, list):
                for x in v:
                    _walk(x, depth + 1)
            v = getattr(c, 'content', None)
            if v is not None and not isinstance(v, (str, int, float)):
                _walk(v, depth + 1)

        _walk(content)
        return out

    try:
        root = Path(G.CFG.projects_dir())
        _jia, JIA = _make(root, '甲书', 3, chain=True, tag='甲')
        _yi, YI = _make(root, '乙书', 2, chain=False, tag='乙')
        print(f'夹具：甲书 {len(JIA)} 轮（链）/ 乙书 {len(YI)} 轮（两个根）', flush=True)

        app = G.NovelWorldApp()
        app.main(page)
        # ★ 截图开关要在建完界面后**立刻**打开并 `update`（照 `verify_help_book` 的写法；
        #   开晚了 `take_screenshot()` 会静默失败 —— 第一次就是这么空手而归的）。
        # [EN] The screenshot switch must be turned on right after the UI is built, followed by
        # [EN] an `update` (per `verify_help_book`); set later it silently fails.
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.0)
        app.show_projects_dialog()
        await asyncio.sleep(0.8)
        page.update()

        # ★ 留一张图：这一行多了两个控件（全选 + 删除选中），而**被裁掉是不报错的** ——
        #   这个项目吃过太多次"控件撑爆、界面不响"的亏。断言管不了排版，图能管。
        # [EN] Leave a screenshot: this row gained two controls, and a **clipped control raises
        # [EN] nothing** -- this project has been burned by that repeatedly. Assertions cannot
        # [EN] judge layout; a picture can.
        try:
            page.update()
            await asyncio.sleep(0.6)
            (OUT / 'pick_all.png').write_bytes(await page.take_screenshot())
        except Exception as _e:                      # noqa: BLE001
            print(f'  (截图没拿到：{_e!r})', flush=True)

        dialogs = VU.open_dialogs(page)
        rec('拾卷打开了', bool(dialogs), f'{len(dialogs)} 层')
        if not dialogs:
            return
        content = getattr(dialogs[-1], 'content', None)
        content = getattr(content, 'content', content) or content

        s = _scan(content)

        # ── A 组：控件都在 ──
        # [EN] A: the controls exist
        rec('① 小说栏有「全选」框', 'novels' in s['bulk'], sorted(s['bulk']))
        rec('② 存档栏有「全选」框', 'runs' in s['bulk'], sorted(s['bulk']))
        rec('两栏的「删除选中」按钮都在', sorted(s['multi']) == ['novels', 'runs'],
            sorted(s['multi']))
        rec('初始两栏都显示「未选」档',
            _bulk_mode(s['bulk']['novels']) == 'none'
            and _bulk_mode(s['bulk']['runs']) == 'none',
            f"小说={_bulk_mode(s['bulk']['novels'])} 存档={_bulk_mode(s['bulk']['runs'])}")
        rec('小说栏装了 2 本书', len(s['novels']) == 2, len(s['novels']))
        if not (s['bulk'] and s['multi'] and len(s['novels']) == 2):
            return

        # ── B 组：小说栏 全选 ⇄ 全不选 ──
        # [EN] B: novels column, select all <-> none
        s['bulk']['novels'].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('小说栏点一下 → 栏头写「删除选中（2）」',
            _multi_label(s['multi']['novels']) == '删除选中（2）',
            repr(_multi_label(s['multi']['novels'])))
        rec('小说栏点一下 → 图标变「全选」档',
            _bulk_mode(s['bulk']['novels']) == 'all',
            _bulk_mode(s['bulk']['novels']))
        _nv = [c for k, _n, c in s['chks'] if k == 'novels']
        rec('小说栏点一下 → 两本书的方框都勾上',
            bool(_nv) and all(_chk_on(c) for c in _nv),
            f'{sum(1 for c in _nv if _chk_on(c))}/{len(_nv)}')

        s['bulk']['novels'].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('小说栏再点一下 → 回到「删除选中」',
            _multi_label(s['multi']['novels']) == '删除选中',
            repr(_multi_label(s['multi']['novels'])))
        rec('小说栏再点一下 → 图标回「未选」档',
            _bulk_mode(s['bulk']['novels']) == 'none',
            _bulk_mode(s['bulk']['novels']))
        rec('小说栏再点一下 → 两本书的方框都取消',
            not any(_chk_on(c) for c in _nv),
            f'{sum(1 for c in _nv if _chk_on(c))}/{len(_nv)}')

        # ── C 组：存档栏 全选（级联 + 锁灰）──
        # [EN] C: saves column, select all (cascade + lock)
        jia = next(c for c in s['novels'] if getattr(c._proj, 'name', '') == '甲书')
        jia.content.on_click(None)                  # = `_load_saves(甲)`，中间栏重建
        await asyncio.sleep(0.2)
        page.update()
        s = _scan(content)                          # 控件对象换了，必须重收
        runs = [(n, c) for k, n, c in s['chks'] if k == 'runs']
        rec('切到甲书 → 中间栏 3 个节点', len(runs) == 3, f'{len(runs)} 个')
        if len(runs) != 3:
            return
        by = dict(runs)

        s['bulk']['runs'].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('存档栏点一下 → 栏头写「删除选中（3）」',
            _multi_label(s['multi']['runs']) == '删除选中（3）',
            repr(_multi_label(s['multi']['runs'])))
        rec('存档栏点一下 → 图标变「全选」档',
            _bulk_mode(s['bulk']['runs']) == 'all',
            _bulk_mode(s['bulk']['runs']))
        rec('存档栏点一下 → 3 个节点的方框全勾上',
            all(_chk_on(c) for _n, c in runs),
            f'{sum(1 for _n, c in runs if _chk_on(c))}/3')
        # ★ 级联：链上第 2、3 轮是第 1 轮的后代 ⇒ 必须跟勾**并锁灰**。
        #   ⚠ 判"锁"看颜色而不是看有没有 `locked` 字段：真机里能读到的只有画出来的颜色，
        #     而"画成灰"正是用户看到的那件事。
        # [EN] Cascade: runs 2/3 are descendants of run 1 => ticked **and locked**.
        # [EN] ⚠ Judge the lock by the painted colour (the only thing a real device exposes,
        # [EN] and exactly what the user sees).
        rec('级联：后代也勾上了', _chk_on(by[JIA[1]]) and _chk_on(by[JIA[2]]),
            f'2={_chk_on(by[JIA[1]])} 3={_chk_on(by[JIA[2]])}')
        rec('级联：后代被锁灰（颜色与本轮根节点不同）',
            _chk_color(by[JIA[0]]) != _chk_color(by[JIA[1]]),
            f'根={_chk_color(by[JIA[0]])} 子={_chk_color(by[JIA[1]])}')

        s['bulk']['runs'].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('存档栏再点一下 → 回到「删除选中」',
            _multi_label(s['multi']['runs']) == '删除选中',
            repr(_multi_label(s['multi']['runs'])))
        rec('存档栏再点一下 → 3 个节点全取消',
            not any(_chk_on(c) for _n, c in runs),
            f'{sum(1 for _n, c in runs if _chk_on(c))}/3')
        # ★ 解锁：取消之后父子必须回到**同一个颜色**。只 `force(False)` 不解锁的话，
        #   子节点会留着一层比"未勾"更淡的灰，而且**点不动**（用户只能重开对话框）。
        # [EN] Unlock: after clearing, parent and child must paint the **same colour**. A
        # [EN] `force(False)` without `lock(False)` leaves a fainter grey and a dead box.
        rec('清空后子节点**解锁**（颜色与根节点一致）',
            _chk_color(by[JIA[0]]) == _chk_color(by[JIA[1]]),
            f'根={_chk_color(by[JIA[0]])} 子={_chk_color(by[JIA[1]])}')

        # ── D 组：换书必须清勾（勾存的是名字，跨书会删错东西）──
        # [EN] D: switching books must drop the ticks
        s['bulk']['runs'].on_click(None)            # 先在甲书全选
        await asyncio.sleep(0.05)
        rec('（前置）甲书全选成功', _multi_label(s['multi']['runs']) == '删除选中（3）',
            repr(_multi_label(s['multi']['runs'])))
        yi = next(c for c in s['novels'] if getattr(c._proj, 'name', '') == '乙书')
        yi.content.on_click(None)
        await asyncio.sleep(0.2)
        page.update()
        rec('换到乙书 → 栏头回到「删除选中」（勾被清掉）',
            _multi_label(s['multi']['runs']) == '删除选中',
            repr(_multi_label(s['multi']['runs'])))
        s = _scan(content)
        rec('换到乙书 → 它的节点一个都没勾',
            not any(_chk_on(c) for k, _n, c in s['chks'] if k == 'runs'))

        # ── E 组：三档（乙书两个根，才可能出现「部分」）──
        # [EN] E: the three states (only reachable with two roots)
        by2 = {n: c for k, n, c in s['chks'] if k == 'runs'}
        rec('乙书两个根都在', all(n in by2 for n in YI), sorted(by2))
        if not all(n in by2 for n in YI):
            return
        by2[YI[0]].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('单勾一个 → 全选框变「部分」档',
            _bulk_mode(s['bulk']['runs']) == 'some',
            _bulk_mode(s['bulk']['runs']))
        rec('单勾一个 → 栏头写「删除选中（1）」',
            _multi_label(s['multi']['runs']) == '删除选中（1）',
            repr(_multi_label(s['multi']['runs'])))
        by2[YI[1]].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('两个都勾上 → 全选框变「全选」档',
            _bulk_mode(s['bulk']['runs']) == 'all',
            _bulk_mode(s['bulk']['runs']))
        s['bulk']['runs'].on_click(None)
        await asyncio.sleep(0.05)
        page.update()
        rec('已经全勾时点全选 = 全不选',
            _multi_label(s['multi']['runs']) == '删除选中'
            and _bulk_mode(s['bulk']['runs']) == 'none',
            f"{_multi_label(s['multi']['runs'])!r} / {_bulk_mode(s['bulk']['runs'])}")

    except BaseException:                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'], flush=True)
    finally:
        # ── F 组：读控件的判法自己先量一遍（防"恒真"）──
        # [EN] F: the readers themselves are measured first (anti-tautology)
        try:
            rec('自检：三档图标判读不是恒真',
                _bulk_mode(ft.Container(content=ft.Icon(ft.Icons.CHECK_BOX))) == 'all'
                and _bulk_mode(ft.Container(
                    content=ft.Icon(ft.Icons.INDETERMINATE_CHECK_BOX))) == 'some'
                and _bulk_mode(ft.Container(
                    content=ft.Icon(ft.Icons.CHECK_BOX_OUTLINE_BLANK))) == 'none',
                'all/some/none')
        except Exception as _e:                      # noqa: BLE001
            rec('自检：三档图标判读不是恒真', False, repr(_e))

        while VU.open_dialogs(page):
            page.pop_dialog()
            await asyncio.sleep(0.05)

        # ★ 一条断言都没跑 = 不算通过（flet 会吞掉 `_render` 里的异常，
        #   只有这个计数能分辨"真的全绿"和"一条都没跑"）。
        # [EN] Zero assertions is not a pass.
        if not results:
            report['fatal'] = report.get('fatal') or '一条断言都没跑'
        code = finish(report, out_path=OUT / 'pick_all_report.json', label='断言')
        from util.flet_shutdown import shutdown
        await shutdown(page, code=code)


def main() -> int:
    # ★ 判据不许读用户的 `.env`：三个外部创作服务一律关掉（否则会被自动拉起，跑几分钟）。
    # [EN] Criteria must not read the user's `.env`; switch the three services off.
    from config import CFG
    for _k in ('MUMU_ENABLED', 'MUMU_AUTOSTART', 'PENSHOT_ENABLED', 'PENSHOT_AUTOSTART',
               'PLOTPILOT_ENABLED', 'PLOTPILOT_AUTOSTART'):
        CFG.set(_k, 'false')
    from i18n import set_lang
    set_lang('zh')

    with tempfile.TemporaryDirectory(prefix='nws_pick_all_') as tmp_s:
        tmp = Path(tmp_s)
        VU.isolate_projects_dir(tmp / 'Projects')
        try:
            from crew import catalog as CAT
            CAT.set_soft_dir(tmp / 'agents')
        except Exception:                            # noqa: BLE001
            pass
        print('起真机 …', flush=True)
        try:
            ft.run(_render)
        except Exception as ex:                      # noqa: BLE001
            print(f'真机跑挂了：{ex!r}')
            report['fatal'] = report.get('fatal') or repr(ex)

    if not results:
        report['fatal'] = report.get('fatal') or '一条断言都没跑'
    return finish(report, out_path=OUT / 'pick_all_report.json', label='断言')


if __name__ == '__main__':
    sys.exit(main())
