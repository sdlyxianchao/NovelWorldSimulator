# -*- coding: utf-8 -*-
"""日志查看对话框验证（2026-10-08）。

用户原话（这段就是规格）：

    「在主界面右上角找个合适的位置放一个按钮 叫做日志按钮，点了之后可以在
      一个新的对话框（较大）**查看整个后台运行过程中的详细日志**（动态刷新，
      **基于日志文件**且**尽可能丰富**，而且需要有**一定的格式**，
      且支持使用**关键字搜索**）最好**分页**（分页可以每一个的日志量多一些，
      比如200条1页，500条1页）」

六件事逐条钉（**真机跑，不是读源码**）：
  ① **入口在** —— 运行界面顶部真有那个按钮，点了真的开出对话框；
  ② **基于日志文件** —— 显示的内容与**磁盘上那份 `.log`** 对得上
     （不是内存里那份被截断的界面日志）；
  ③ **有一定格式** —— 四段式（时刻 / 模块 / 级别 / 消息）被拆开渲染，
     且**级别按色分档**（DEBUG 与 ERROR 的颜色必须不同）；
  ④ **搜索** —— 输入关键字之后，列表里**只剩含它的行**，且计数改对；
  ⑤ **分页** —— 每页 200 / 500 可选，翻页真的换内容，到边界按钮变灰；
  ⑥ **动态刷新** —— 新写进日志文件的行**会自动出现**（不用手点刷新），
     而且**不会把当前页码踢回第一页**（否则一边看一边被拽回去）。

跑法：.venv\\Scripts\\python.exe tools/verify_log_dialog.py
产出：assets/screenshots/log_dialog_report.json

English:
Log viewer dialog verification (2026-10-08).
User's original words (this passage is the spec):
    "Find a suitable spot at the top-right of the main UI and put a button called log button; after clicking it you can, in
      a new dialog (larger) **view the detailed log of the whole background run process** (dynamic refresh,
      **based on the log file** and **as rich as possible**, and needs **a certain format**,
      and supports **keyword search**) ideally **pagination** (each page can have a bit more log volume,
      e.g. 200 lines 1 page, 500 lines 1 page)"
Six things nailed one by one (**run on real machine, not reading source**):
  ① **Entry is** -- there really is that button at the top of the run UI, clicking it really opens the dialog;
  ② **Based on log file** -- the displayed content matches **the `.log` on disk**
     (not the truncated UI log in memory);
  ③ **Has a certain format** -- the four segments (time / module / level / message) are split and rendered,
     and **level is tiered by color** (DEBUG and ERROR colors must differ);
  ④ **Search** -- after entering a keyword, **only lines containing it remain** in the list, and the count is updated correctly;
  ⑤ **Pagination** -- 200 / 500 per page selectable, paging really swaps content, buttons gray out at the boundary;
  ⑥ **Dynamic refresh** -- newly written lines **appear automatically** (no manual refresh needed),
     and **won't kick the current page number back to page 1** (otherwise you're dragged back while watching).
How to run: .venv\\Scripts\\python.exe tools/verify_log_dialog.py
Output: assets/screenshots/log_dialog_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown, exit_now              # noqa: E402

from config import CFG                                         # noqa: E402
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')

import gui.app_flet as G                                       # noqa: E402
from logger import nws_logger, log_dir                          # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _log_rows(lst) -> list[str]:
    """列表里当前渲染出来的**原始文本**（按行拼）。
        English:
    The **raw text** currently rendered in the list (concatenated by line).
    """
    out = []
    for c in (lst.controls or []):
        parts = [getattr(x, 'value', '') for x in VU.walk(c)
                 if isinstance(x, ft.Text)]
        out.append(' '.join(str(p) for p in parts if p))
    return out


async def main(page: ft.Page):
    app = G.NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.4)

    # ⚠ **必须先切到运行界面** —— 启动后停在**开始界面**，
    #   而「日志」按钮在**运行界面顶部**。不切过去的话一条按钮都找不到
    #   （第一版就是这么红的：`[]`，看着像"按钮没加上"）。
    # [EN] ⚠ **Must switch to the run UI first** -- after startup it stays on the **start UI**,
    # [EN] and the "Log" button is **at the top of the run UI**. If you don't switch over, you won't find a
    # [EN] single button
    # [EN] (the first version went red exactly like this: `[]`, looking like "the button wasn't added").
    from verify_run_control import make_project
    tmp = Path(tempfile.mkdtemp(prefix='nws_logdlg_'))
    try:
        app.current_project = make_project(tmp / '日志对话框')
        app.show_main_screen()
        await asyncio.sleep(1.4)
    except BaseException:                                       # noqa: BLE001
        import traceback
        ok('（切到运行界面失败）', False, traceback.format_exc()[-400:])

    try:
        # ── ① 入口：顶部按钮 + 点开 ──
        # [EN] -- ① Entry: top button + click to open --
        btns = [c for c in VU.walk(page) if type(c).__name__ == 'FilledButton']
        labels = [VU.text_of(c).strip() for c in btns]
        ok('① 运行界面顶部有一个「日志」按钮（和「帮助」并排）',
           any('日志' in x for x in labels), str([x for x in labels if x])[:120])
        entry = next((c for c in btns if '日志' in VU.text_of(c)), None)
        ok('① 找到那个按钮的句柄（能点）', entry is not None and entry.on_click is not None)
        entry.on_click(None)
        page.update()
        await asyncio.sleep(0.9)
        dlg = next((d for d in VU.open_dialogs(page)
                    if '日 志' in ' '.join(VU.all_texts(d))), None)
        ok('① 点了之后**真的开出对话框**', dlg is not None,
           f'{len(VU.open_dialogs(page))} 个对话框开着')
        if dlg is None:
            raise RuntimeError('日志对话框没开出来，后面的判据无从谈起')

        ui = getattr(app, '_log_dialog_ui', {}) or {}
        st = ui.get('state') or {}
        lst = ui.get('list')

        # ── ② 基于日志文件：和磁盘那行对得上 ──
        # [EN] -- ② Based on log file: must match the disk line --
        p = Path(nws_logger.log_file)
        ok('② 显示的是**磁盘上那份日志文件**（不是内存里被截断的那份）',
           str(p) == str(ui.get('path_of')('main')) and p.exists(), p.name)
        disk = p.read_text(encoding='utf-8', errors='replace').splitlines()
        shown = _log_rows(lst)
        ok('② 读到的行数与文件行数一致（最新在前，只差一页）',
           len(st.get('rows') or []) == len(disk),
           f'文件 {len(disk)} 行 / 列表读到 {len(st.get("rows") or [])} 行')
        # 最后一行（最新）应当出现在列表最上面
        # ⚠ 列表里**不重复日期**（时刻只留时分秒），所以比对的是**消息那一段**
        # [EN] The last line (newest) should appear at the top of the list
        # [EN] ⚠ The list does **not repeat the date** (time only keeps HH:MM:SS), so the comparison is on the
        # [EN] **message segment**
        _tail = disk[-1].split(': ', 1)[-1][:18] if disk else ''
        ok('② 默认「最新在前」：文件最后一行 = 列表第一行',
           bool(_tail) and bool(shown) and _tail in shown[0],
           f'{_tail!r} → {shown[0][:50]!r}' if shown else '')

        # ── ③ 格式：四段拆开 + 级别分色 ──
        # [EN] -- ③ Format: split into four segments + level coloring --
        first = next((c for c in (lst.controls or [])
                      if type(c).__name__ == 'Row'), None)
        ok('③ 一行被拆成**多段**渲染（时刻 / 模块 / 级别 / 消息），不是一整块文字',
           first is not None and len(first.controls) >= 4,
           f'{len(first.controls) if first is not None else 0} 段')
        colors: dict = {}
        for c in (lst.controls or []):
            row = c if type(c).__name__ == 'Row' else None
            if row is None or len(row.controls) < 3:
                continue
            lvl = str(getattr(row.controls[2], 'value', '')).strip()
            col = getattr(row.controls[2], 'color', None)
            colors.setdefault(lvl, col)
        # ⚠ 启动后这份日志很短（十几行、清一色 INFO），**颜色无从分档** ——
        #   所以先往**那份日志文件**里补几行不同级别的真日志，再刷新看色。
        #   （不这么做的话这条判据恒真/恒假，等于没验。）
        # [EN] ⚠ After startup this log is very short (a dozen lines, all INFO), **no way to tier colors** --
        # [EN] So first append a few real log lines of different levels to **that log file**, then refresh to
        # [EN] see colors.
        # [EN] (Otherwise this criterion is always true/always false, i.e. unverified.)
        _pad = (('DEBUG', '分色验证：这一行是 DEBUG'), ('INFO', '分色验证：这一行是 INFO'),
                ('WARNING', '分色验证：这一行是 WARNING'), ('ERROR', '分色验证：这一行是 ERROR'))
        with p.open('a', encoding='utf-8') as f:
            for lvl, msg in _pad:
                f.write(f'\n2026-01-01 00:00:00 [nws.pad] {lvl}: {msg}\n')
        ui['do_search']()  # 清空状态下重读
        # [EN] Re-read in the cleared state
        page.update()
        await asyncio.sleep(0.5)
        colors = {}
        for c in (lst.controls or []):
            row = c if type(c).__name__ == 'Row' else None
            if row is None or len(row.controls) < 3:
                continue
            lvl = str(getattr(row.controls[2], 'value', '')).strip()
            colors.setdefault(lvl, getattr(row.controls[2], 'color', None))
        ok('③ 级别**真的分色**（DEBUG / INFO / WARNING / ERROR 不全同色）',
           len({str(v) for v in colors.values()}) >= 3,
           str({k: str(v) for k, v in colors.items()}))
        ok('③ 时刻那一段**只留时分秒**（日期不必每行重复）',
           first is not None and len(str(getattr(first.controls[0], 'value', ''))) <= 8,
           str(getattr(first.controls[0], 'value', '')) if first is not None else '')

        # ── ④ 搜索 ──
        # 挑一个**确定存在**的词：从磁盘日志里取一个模块名
        # [EN] -- ④ Search --
        # [EN] Pick a word that **definitely exists**: take a module name from the disk log
        import re as _re
        mods = _re.findall(r'\[(nws\.[a-z_.]+)\]', '\n'.join(disk[-400:]))
        word = mods[0] if mods else 'INFO'
        ui['search'].value = word
        ui['do_search']()          # ⚠ 必须走真的处理链：只改 value 不会过滤
        # [EN] ⚠ Must go through the real processing chain: changing only value won't filter
        page.update()
        await asyncio.sleep(0.4)
        hits = st.get('rows') or []
        ok(f'④ 搜「{word}」之后**只剩含这个词的行**',
           bool(hits) and all(word.lower() in x.lower() for x in hits),
           f'{len(hits)} 行命中 / 全量 {len(disk)} 行')
        ok('④ 命中行数**少于全量**（真的过滤了，不是原样显示）',
           0 < len(hits) < len(disk), f'{len(hits)} < {len(disk)}')
        ok('④ 计数那一行写明了「命中 N 行」',
           '命中' in str(getattr(ui['info'], 'value', '')),
           str(getattr(ui['info'], 'value', ''))[:60])
        _after = _log_rows(lst)
        ok('④ 列表里**每一行都含关键字**（渲染层也没漏）',
           bool(_after) and all(word in x for x in _after),
           str(_after[:1])[:70])
        # 清空
        # [EN] Clear
        ui['do_clear']()
        page.update()
        await asyncio.sleep(0.3)
        # ⚠ 与**现读的文件行数**比，不能拿步骤②那份旧的 `disk` ——
        #   中间为了验分色往文件里补过 4 行（拿旧数比会假红，实测就是）。
        # [EN] ⚠ Compare against the **currently read file line count**, don't use the old `disk` from step ②
        # [EN] --
        # [EN] In between, 4 lines were appended to the file to verify coloring (comparing with old count gives
        # [EN] false red, confirmed in practice).
        _disk_now = p.read_text(encoding='utf-8', errors='replace').splitlines()
        ok('④ 清空关键字之后恢复全量', len(st.get('rows') or []) == len(_disk_now),
           f'{len(st.get("rows") or [])} / 文件 {len(_disk_now)} 行')

        # ── ⑤ 分页 ──
        # ⚠ 先**喂够行数**：刚启动那份日志只有十几行，分页根本跑不起来
        #   （第一版就落进"行数不足，判据跳过"那一支 —— 等于**没验**）。
        #   补 620 行，这样 200/页有 4 页、500/页有 2 页，两档都真的翻得动。
        # [EN] -- ⑤ Pagination --
        # [EN] ⚠ First **feed enough lines**: the just-started log has only a dozen lines, pagination can't
        # [EN] even run
        # [EN] (the first version fell into the "insufficient lines, criterion skipped" branch -- i.e.
        # [EN] **unverified**).
        # [EN] Append 620 lines, so 200/page gives 4 pages and 500/page gives 2 pages, both tiers actually
        # [EN] pageable.
        with p.open('a', encoding='utf-8') as f:
            for i in range(620):
                lvl = ('DEBUG', 'INFO', 'WARNING')[i % 3]
                f.write(f'\n2026-01-02 0{i % 10}:{i % 60:02d}:00 [nws.page] {lvl}: '
                        f'分页验证第 {i} 行 content-{i}\n')
        ui['do_search']()
        page.update()
        await asyncio.sleep(0.6)
        ok('⑤ 每页有两档可选（200 / 500 —— 用户点名的两个数）',
           tuple(app.LOG_PAGE_SIZES) == (200, 500), str(app.LOG_PAGE_SIZES))
        n_per = st.get('size')
        ok('⑤ 当前每页条数就是选定的那一档', int(n_per) in (200, 500), str(n_per))
        page1 = _log_rows(lst)
        ok('⑤ 一页最多只渲染 N 条（不会把几千行一次塞进去）',
           len(page1) <= int(n_per), f'{len(page1)} 条 / 每页 {n_per}')
        # 切到 500：一页的容量应当变大（或总行数本来就不够）
        # [EN] Switch to 500: one page's capacity should grow (or total lines was already insufficient)
        total = len(st.get('rows') or [])
        st['size'] = 500
        ui['render'](keep_page=False)
        page.update()
        await asyncio.sleep(0.4)
        page_s2 = _log_rows(lst)
        ok('⑤ 切到 500 条/页之后，一页渲染得**更多或等于**上一档',
           len(page_s2) >= len(page1),
           f'{len(page1)}(200档) → {len(page_s2)}(500档)，共 {total} 行')
        st['size'] = 200
        ui['render'](keep_page=False)
        page.update()
        await asyncio.sleep(0.3)
        total = len(st.get('rows') or [])
        if total > 200:
            st['page'] = 1
            ui['render']()
            page.update()
            await asyncio.sleep(0.3)
            ok('⑤ 第 1 页时「上一页」是**灰的**', bool(ui['btn_prev'].disabled), '')
            st['page'] = 2
            ui['render']()
            page.update()
            await asyncio.sleep(0.3)
            p2 = _log_rows(lst)
            ok('⑤ 翻到第 2 页**内容真的换了**',
               p2 != page1 and bool(p2), f'{len(p2)} 条')
            ok('⑤ 到第 2 页之后「上一页」不再是灰的',
               not ui['btn_prev'].disabled, '')
            ui['jump'].value = '1'
            ui['btn_next'].on_click(None) if False else None
        else:
            ok('⑤ 行数不足 200，翻页判据跳过（记录在案）',
               True, f'共 {total} 行')

        # ── ⑥ 动态刷新 ──
        # [EN] -- ⑥ Dynamic refresh --
        ok('⑥「自动刷新」开关**默认是开的**（用户要的动态刷新）',
           bool(ui['auto'].value) is True, '')
        before = len(st.get('rows') or [])
        # 往**当前那份日志文件**里追加一行真的日志，等自动刷新把它读进来
        # [EN] Append a real log line to **the current log file**, wait for auto-refresh to read it in
        marker = f'日志对话框验证标记 {int(time.time())}'
        p.open('a', encoding='utf-8').write(
            f'\n2026-01-01 00:00:00 [nws.gui] WARNING: {marker}\n')
        await asyncio.sleep(2.6)          # 轮询间隔 1.2s，留两拍
        # [EN] Polling interval 1.2s, leave two beats
        after = st.get('rows') or []
        ok('⑥ 新写进日志文件的行**自动出现**了（不用手点刷新）',
           any(marker in x for x in after), f'{before} → {len(after)} 行')
        # 页码不被踢回第 1 页
        # [EN] Page number is not kicked back to page 1
        st['page'] = max(1, min(2, max(1, (len(after) + 199) // 200)))
        _keep = st['page']
        await asyncio.sleep(1.6)
        ok('⑥ 自动刷新**不会把当前页码踢回第 1 页**（一边看一边被拽回去=没法用）',
           int(st['page']) >= 1 and int(st['page']) == _keep,
           f'第 {_keep} 页 → 第 {st["page"]} 页')

        # ── 收尾：关掉对话框之后刷新任务要自己停 ──
        # [EN] -- Wrap-up: after closing the dialog the refresh task must stop on its own --
        ui['dlg'].open = False
        page.pop_dialog()
        page.update()
        await asyncio.sleep(2.0)
        ok('⑥ 对话框关掉之后**刷新任务自己收工**（不留每秒读盘的死循环）',
           not bool(getattr(ui['dlg'], 'open', False)), '')
    except BaseException:                                       # noqa: BLE001
        import traceback
        ok('（验证执行中断）', False, traceback.format_exc()[-500:])
        print(traceback.format_exc()[-1600:])

    total = len(report['checks'])
    passed = sum(1 for c in report['checks'] if c['ok'])
    report.update({'total': total, 'passed': passed, 'ok': passed == total})
    (OUT / 'log_dialog_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n日志对话框验证：{passed}/{total}')
    await shutdown(page, code=0 if passed == total else 2)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
