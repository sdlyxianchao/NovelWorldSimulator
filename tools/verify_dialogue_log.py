# -*- coding: utf-8 -*-
"""真机验证：**每一次 LLM 对话都落到日志文件里**（而且是全文，不截断）。

背景（用户 2026-10-05）：「所有的对话也需要放到日志里」。
改之前的状态：
  · 请求/响应只有在 `DEBUG_MODE` 打开时才进主日志，而且**截断**（请求 200 字 / 响应 500 字）；
  · 界面上那几行（`_add_log`）只活在内存里，还被 `_clip(700/1200)` 切过；
  · AI 在「优化对话」里的回复**只在气泡里**，连界面日志都没有。

判据分三段：
  A. **纯路由器**（不开界面）：发一条 3000 字的提示词，断言对话日志里能读到**整段**；
  B. **真机摄取**（MOCK）：作者发一条 1000 字的指令，断言作者的话、**AI 的回复**、
     摄取阶段的行都在文件里；再用监听器数请求次数，断言"发生过的每一次"都落了盘。
  C. **日志改名**（2026-10-07 新增）：开卷之后日志文件名要**带上书名**
     （`nws_临河茶肆_2026_10_07_01_23_11.log`），而且是**改名**不是另起新文件
     —— A 段写进去的那些内容，改名后必须还在同一个文件里。

     ⚠ 这一组是**这个脚本必然要加**的，因为它自己就是最大的"受害者"：
     A 段把 `dialogue_logger().path` 存进 `dpath`，后面一直拿它读日志。
     改名一生效，那个路径就成了**已不存在的旧名**，`read_log()` 返回空串，
     B 组会**集体假红**（"作者的话没落盘""AI 回复没落盘"…）。
     所以改名之后取路径必须**现取**（`dialogue_logger().path`），
     而不是沿用启动时抓的那份。

跑法：.venv/Scripts/python.exe tools/verify_dialogue_log.py
产出：assets/screenshots/dialogue_log_report.json

English:
Real-machine verification: **every LLM conversation lands in the log file** (and it's full text,
not truncated).
Background (user 2026-10-05): "all conversations also need to go into the log".
State before the change:
  · Request/response only enter the main log when `DEBUG_MODE` is on, and are **truncated** (request 200 chars / response 500 chars);
  · Those UI lines (`_add_log`) only live in memory, and are also cut by `_clip(700/1200)`;
  · The AI's replies in "optimize conversation" are **only in the bubble**, not even in the UI log.
Criteria are in three sections:
  A. **Pure router** (no UI): send a 3000-character prompt, assert the **entire** text can be read from the conversation log;
  B. **Real-machine ingestion** (MOCK): the author sends a 1000-character instruction, assert the author's words, **the AI's reply**,
     and the ingestion-stage lines are all in the file; then use a listener to count requests, asserting that "every occurrence" was written to disk.
  C. **Log renaming** (new 2026-10-07): after opening a book the log filename must **include the book title**
     (`nws_临河茶肆_2026_10_07_01_23_11.log`), and it's a **rename** not a new file
     —— the content written in section A must still be in the same file after renaming.
     ⚠ This group is **something this script must add**, because it is itself the biggest "victim":
     Section A stores `dialogue_logger().path` into `dpath`, and keeps using it to read the log afterwards.
     Once the rename takes effect, that path becomes a **nonexistent old name**, `read_log()` returns an empty string,
     and group B will **all go fake red** ("author's words not written to disk", "AI reply not written to disk"...).
     So after renaming, the path must be fetched **fresh** (`dialogue_logger().path`),
     not the one captured at startup.
How to run: .venv/Scripts/python.exe tools/verify_dialogue_log.py
Output: assets/screenshots/dialogue_log_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

import logger as LG  # noqa: E402
from logger import dialogue_logger, log_dir, nws_logger  # noqa: E402
from llm.router import llm  # noqa: E402
from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {}
ITEMS: list = []

LONG = 3000        # 远超所有旧截断阈值（200 / 500 / 700 / 1200）
# [EN] Far exceeds all old truncation thresholds (200 / 500 / 700 / 1200)
MARK = 'ZZMARK' * (LONG // 6)


def ok(name: str, cond: bool, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:160]})
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f' — {detail}' if detail else ''))
    return bool(cond)


def read_log(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def dlg_now() -> Path:
    """对话日志**当前**路径。

    ⚠ 必须现取，不能沿用启动时抓的那份：开卷后日志会**改名**带上书名
    （`logger.set_project()`），旧路径指向的文件已经不在了 ——
    拿旧路径读会返回空串，然后把 B 组整片判成"没落盘"（**假红**）。
    
        English:
    Conversation log's **current** path.
        ⚠ Must be fetched fresh, cannot reuse the one captured at startup: after opening a book the log gets **renamed** to include the book title
        (`logger.set_project()`), the file pointed to by the old path no longer exists ——
        reading with the old path returns an empty string, then group B is judged entirely as "not written to disk" (**fake red**).
    """
    return dialogue_logger().path


def main_now() -> Path:
    """主日志**当前**路径（同上：开卷后会改名）。
        English:
    Main log's **current** path (same as above: renamed after opening a book).
    """
    return nws_logger.log_file


def make_source(root: Path) -> Path:
    src = root / '对话日志夹具'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n\n起：雨夜来客。\n承：旧事被翻出。\n',
                                 encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦。\n\n「你今日话里有话。」\n' * 10, encoding='utf-8')
    return src


async def main(page: ft.Page):
    # ══════════ A. 纯路由器：不开界面也要留档，且是全文 ══════════
    # [EN] ══════════ A. Pure router: leave a record even without opening the UI, and it must be full text
    # [EN] ══════════
    try:
        await llm.ensure_started(log_dir())
        dpath = dialogue_logger().path
        # ★ 启动时的两个名字（还没有书名）。改名之后要用它们来断言"搬走了、没残留"。
        # [EN] ★ The two names at startup (no book title yet). After renaming, use them to assert "moved out,
        # [EN] no residue".
        start_main = nws_logger.log_file
        start_dlg = dpath
        REPORT['dialogue_file'] = str(dpath)
        REPORT['main_file'] = str(nws_logger.log_file)
        ok('对话日志与主日志是**两个文件**',
           dpath != nws_logger.log_file and dpath.parent == nws_logger.log_file.parent,
           f'{dpath.name} / {nws_logger.log_file.name}')
        ok('C0 启动时文件名是「nws_<时间戳>」（那会儿还没开卷，没有书名那一段）',
           start_main.name.startswith('nws_') and '_dialogue_' not in start_main.name
           and '_' in start_main.stem[len('nws_'):],
           f'{start_main.name} / {start_dlg.name}')
        ok('主日志启动时写明了对话日志的路径（免得找不着）',
           '对话日志' in read_log(nws_logger.log_file))

        seen: list = []
        llm.add_listener(lambda ev: seen.append(ev.get('type')))
        before = read_log(dpath)
        reply = await llm.chat(messages=[{'role': 'system', 'content': '你是校对员。'},
                                        {'role': 'user', 'content': MARK}],
                               purpose='verify_dialogue', tier='cheap', max_tokens=64)
        text = read_log(dpath)
        REPORT['A_bytes'] = len(text)
        ok('A：呼一次 LLM 之后对话日志就出现了内容', len(text) > len(before))
        ok('A：请求写了「LLM 请求」小节', 'LLM 请求' in text)
        ok(f'A：{LONG} 字的提示词**一字不少**地落盘（旧实现只存前 200 字）',
           MARK in text, f'标记出现 {text.count(MARK)} 次')
        ok('A：小节头写了 tier / model / purpose',
           all(k in text for k in ('tier=', 'model=', 'purpose=verify_dialogue')))
        # ⚠ 判据要拿**返回的原文**去比对。第一版写的是
        # `text.rstrip().endswith('\n')` —— rstrip 之后永远不可能以换行结尾，
        # 这条断言**恒为假**，报红还以为是代码坏了，其实是判据本身没意义。
        # [EN] ⚠ The criterion must compare against the **returned original text**. The first version wrote
        # [EN] `text.rstrip().endswith('\n')` —— after rstrip it can never end with a newline,
        # [EN] this assertion is **always false**, and when it goes red you'd think the code is broken, but
        # [EN] actually the criterion itself is meaningless.
        ok('A：响应正文也落了盘（把 chat() 返回的原文拿去日志里找）',
           'LLM 响应' in text and bool(str(reply).strip())
           and str(reply).strip() in text, f'响应 {len(str(reply))} 字')
        REPORT['A_events'] = seen

        # ══════════ B. 真机摄取：界面对话 + 摄取过程 ══════════
        # [EN] ══════════ B. Real-machine ingestion: UI dialogue + ingestion process ══════════
        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.4)

        tmp = Path(tempfile.mkdtemp(prefix='nws_dlog_'))
        VU.isolate_projects_dir(tmp / 'Projects')
        src = make_source(tmp)

        n_req_before = read_log(dlg_now()).count('LLM 请求')
        ev_reqs: list = []
        llm.add_listener(lambda ev: ev_reqs.append(1) if ev.get('type') == 'request'
                         else None)

        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)
        app._wizard_path = str(src)
        app._wizard_name = '对话日志夹具'
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = False    # 这一步会停下等确认，脚本里跳过
        # [EN] This step stops to wait for confirmation, skipped in the script
        app._do_import(page)
        st = app._ingest_state

        for _ in range(200):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            p = ui.get('consent_panel')
            if p is not None and p.visible:
                break
        ui = st.get('ui') or {}
        for b in list(ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        page.update()
        if ui.get('consent'):
            ui['consent'](True)

        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(1.0)

        # 作者发一条 1000 字的指令（超过界面的 700 字截断）
        # [EN] The author sends a 1000-character instruction (exceeds the UI's 700-character truncation)
        long_msg = ('把主角的秘密改成和那口井有关，' + '再补两条伏笔，' * 80)
        REPORT['author_msg_len'] = len(long_msg)
        ui = st.get('ui') or {}
        if ui.get('chat_input'):
            ui['chat_input'].value = long_msg
            ui['send'](None)
        for _ in range(400):
            await asyncio.sleep(0.1)
            cl = (st.get('ui') or {}).get('chat_list')
            if cl is not None and len(cl.controls) >= 4:
                break
        await asyncio.sleep(0.8)

        # AI 的回复原文（从气泡里取，再去日志里找）
        # [EN] The AI's reply raw text (taken from the bubble, then found in the log)
        cl = (st.get('ui') or {}).get('chat_list')
        bubbles: list = []
        for col in (cl.controls if cl else []):
            for c in VU.walk(col):
                if isinstance(c, ft.Text) and c.value:
                    bubbles.append(str(c.value))
        ai_text = next((b for b in bubbles
                        if b and b != long_msg and len(b) > 12), '')
        REPORT['ai_reply_len'] = len(ai_text)
        REPORT['bubbles'] = len(bubbles)

        # 收尾：完成优化 → 关框
        # [EN] Wrap-up: complete optimization → close the box
        try:
            if ui.get('finish'):
                # ⚠ 以前写 `finish(None)` —— 而 `_finish` 不接参数，
                #   外面又套着 `except Exception: pass`，于是**静默没生效**
                #   （对话框一直不关、下面那个等待循环白等 20 秒）。现在两边都宽松了。
                # [EN] ⚠ Previously wrote `finish(None)` —— but `_finish` takes no arguments,
                # [EN] and was wrapped outside in `except Exception: pass`, so it **silently had no effect**
                # [EN] (the dialog never closed, and the wait loop below waited 20 seconds in vain). Now both sides are
                # [EN] lenient.
                ui['finish']()
                for _ in range(200):
                    await asyncio.sleep(0.1)
                    if not VU.open_dialogs(page):
                        break
        except Exception:                                   # noqa: BLE001
            pass

        text2 = read_log(dlg_now())      # 现取（这会儿可能已经改名了）
        # [EN] Fetch fresh (it may have been renamed by now)
        REPORT['B_bytes'] = len(text2)
        n_req_after = text2.count('LLM 请求')
        REPORT['req_sections'] = [n_req_before, n_req_after]
        REPORT['req_events'] = len(ev_reqs)

        ok('B：作者那条 1000 字的指令**整段**在日志里（界面只显示前 700 字）',
           long_msg in text2)
        ok('B：**AI 的回复**也在日志里（此前只在气泡里，关窗就没了）',
           bool(ai_text) and ai_text in text2,
           f'AI 回复 {len(ai_text)} 字 · {"找到" if ai_text in text2 else "没找到"}')
        ok('B：作者的话被标成「作者 → AI」',
           '作者 → AI' in text2 and 'AI → 作者' in text2)
        # 界面日志那几行是**带 `▶` 的阶段行**，现在原样落盘（不再套小节框）
        # [EN] Those UI log lines are **stage lines with `▶`**, now written to disk as-is (no longer wrapped in
        # [EN] section boxes)
        ok('B：摄取阶段的行也留了档（▶ 一行一件事）',
           any(mark in text2 for mark in ('▶ 读取与分章', '▶ 扫描文件夹'))
           and '摄取完成' in text2)
        # **每一次**都落盘：日志里的小节数 == 监听器数到的请求数
        # [EN] Write to disk on **every** occurrence: number of sections in the log == number of requests
        # [EN] counted by the listener
        ok('B：发生过的每一次 LLM 请求都落了盘（对数）',
           n_req_after - n_req_before == len(ev_reqs),
           f'日志 +{n_req_after - n_req_before} / 实际 {len(ev_reqs)}')
        ok('B：对话日志明显比"只记摘要"大（这次跑 > 8KB）',
           len(text2.encode()) > 8192, f'{len(text2.encode())} 字节')
        REPORT['exists'] = dlg_now().exists()

        # ══════════ C. 开卷后日志改名（带书名）══════════
        #   用户 2026-10-07：「在 nws 后面加 `_` 然后项目名然后 `_` 接原来的日志名字」。
        #   这里测的是**真机链路**：摄取跑完 → `_activate_project()` → 日志改名。
        # [EN] ══════════ C. Log renaming after opening a book (with book title) ══════════
        # [EN] User 2026-10-07: "after nws add `_` then the project name then `_` then the original log name".
        # [EN] What's tested here is the **real-machine pipeline**: ingestion finishes → `_activate_project()`
        # [EN] → log renamed.
        proj = app.current_project
        if proj is None:
            # 摄取还没走到"开卷完成"那一步 —— 那就自己走一遍**真实入口**
            #   （`_activate_project` 就是开卷完成与拾卷打开共用的那个函数），
            #   否则这一组会因为"流程没跑到"而永远测不到。
            # `projects_dir()` 是"当前生效的项目根"（`VU.isolate_projects_dir()`
            # 刚把它指到临时目录），别自己拼路径 —— 判据要跟着产品走。
            # [EN] Ingestion hasn't yet reached the "book-open complete" step —— so walk through the **real entry
            # [EN] point** yourself
            # [EN] (`_activate_project` is the function shared by book-open complete and pick-up-book open),
            # [EN] otherwise this group will never be tested because "the flow didn't reach it".
            # [EN] `projects_dir()` is "the currently effective project root" (`VU.isolate_projects_dir()`
            # [EN] just pointed it at a temp dir), don't assemble paths yourself —— the criterion must follow the
            # [EN] product.
            from store.project import scan_projects
            cands = scan_projects(CFG.projects_dir())
            if cands:
                app._activate_project(cands[0])
                proj = app.current_project
        book = getattr(proj, 'name', '') if proj is not None else ''
        REPORT['C_book'] = book
        ok('C1 摄取完成 → 当前项目已就位（这一组才有意义）',
           proj is not None and bool(book), f'书名={book!r}')

        cur_main, cur_dlg = main_now(), dlg_now()
        stamp = nws_logger.stamp
        token = LG.safe_filename_token(book)
        REPORT['C_main'] = cur_main.name
        REPORT['C_dialogue'] = cur_dlg.name
        ok('C2 ★ 主日志名 = `nws_<书名>_<时间戳>.log`',
           bool(token) and cur_main.name == f'nws_{token}_{stamp}.log',
           f'{cur_main.name}（期望 nws_{token}_{stamp}.log）')
        ok('C3 ★ 对话日志名 = `nws_<书名>_dialogue_<时间戳>.log`',
           bool(token) and cur_dlg.name == f'nws_{token}_dialogue_{stamp}.log',
           f'{cur_dlg.name}')
        ok('C4 启动时那两个**无名**文件已经不在了（是改名，不是另起新文件）',
           not start_main.exists() and not start_dlg.exists(),
           f'残留：{[p.name for p in (start_main, start_dlg) if p.exists()]}')
        # 内容必须跟着走：A 段那 3000 字的标记，改名后还得在**同一个**文件里
        # [EN] Content must follow along: the 3000-character marker from section A must still be in the
        # [EN] **same** file after renaming
        kept = read_log(cur_dlg)
        ok('C5 ★ 改名是"搬走"：A 段写进去的 3000 字**还在**（不是新建的空文件）',
           MARK in kept, f'{len(kept.encode())} 字节')
        # 改名之后处理器得真的指到新文件（不然日志会静悄悄停在旧文件里）
        # [EN] After renaming, the handler must actually point to the new file (otherwise the log will sit
        # [EN] silently in the old file)
        LG.log_dialogue_line('改名之后的探针行 [after-rename-probe]')
        ok('C6 改名后对话日志**还能写**（处理器跟着换了）',
           '[after-rename-probe]' in read_log(cur_dlg))
        # C7：GUI 那一端的接线证据（真机跑的是"结果"，这条钉的是"谁调的"）
        # [EN] C7: wiring evidence on the GUI side (the real machine runs the "result", this one pins down "who
        # [EN] called it")
        import ast as _ast
        import inspect as _inspect
        import textwrap as _tw
        src = _inspect.getsource(NovelWorldApp._activate_project)
        called = any(isinstance(n, _ast.Call) and _ast.unparse(n.func).endswith(
            'set_project_log') for n in _ast.walk(_ast.parse(_tw.dedent(src))))
        ok('C7 ★★ `_activate_project()` 里真的调了 `set_project_log()`'
           '（开卷那一刻改名，接线有据）', called, 'AST 里找到调用' if called else '没找到')
        ok('C8 纯函数：非法字符不进文件名（`/` `:` `*` `..` 都被清掉）',
           LG.safe_filename_token('临河茶肆/第:二*部<>"') == '临河茶肆第二部'
           and LG.safe_filename_token('..') == ''
           and LG.safe_filename_token('   ') == '',
           repr(LG.safe_filename_token('临河茶肆/第:二*部<>"')))
        ok('C9 纯函数：超长书名被截断（别把路径顶到 Windows 260 上限）',
           len(LG.safe_filename_token('书' * 200)) == LG.MAX_NAME_CHARS,
           f'{len(LG.safe_filename_token("书" * 200))} 字')

        VU.safe_rmtree(tmp, ignore_errors=True)
    except Exception:                                           # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        n_ok = sum(1 for i in ITEMS if i['ok'])
        REPORT['items'] = ITEMS
        REPORT['n_ok'], REPORT['n_all'] = n_ok, len(ITEMS)
        # ⚠ **崩过就不算通过**，哪怕已经跑过的那些全绿：
        #   `main()` 外面套着 `except Exception`，异常一吞，后面几条判据**一条都没跑**，
        #   而汇总只数 `ITEMS` —— 于是"20/20 全部通过"照样印出来（2026-10-07 实测）。
        #   **没跑到的判据不能算通过**，这是这个脚本自己的老毛病，钉在这儿。
        # [EN] ⚠ **A crash means it doesn't count as passing**, even if all the ones that ran are green:
        # [EN] `main()` is wrapped in `except Exception`, once the exception is swallowed, the following
        # [EN] criteria **don't run at all**,
        # [EN] and the summary only counts `ITEMS` —— so "20/20 all passed" still gets printed (observed
        # [EN] 2026-10-07).
        # [EN] **Criteria that didn't run can't count as passing**, this is this script's own old bug, pinned
        # [EN] here.
        REPORT['ok'] = n_ok == len(ITEMS) and not REPORT.get('fatal')
        (OUT / 'dialogue_log_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n对话日志验证：{n_ok}/{len(ITEMS)}')
        if REPORT.get('fatal'):
            print('   ⚠ 中途抛过异常 —— 后面的判据**没跑到**，结果不可信（见 report 的 fatal）')
        print('对话日志文件：', REPORT.get('dialogue_file'))
        print('运行结束后的文件名：', REPORT.get('C_main'))
        print('→', '全部通过' if REPORT['ok'] else '有失败')
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] cancelling this coroutine, written on the line `exit_now(...)` after `await shutdown(page)`
        # [EN] **never actually executed** (exit code always 0 = fake green). See
        # [EN] `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if REPORT['ok'] else 2)


ft.run(main)
