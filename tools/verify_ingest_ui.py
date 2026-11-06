# -*- coding: utf-8 -*-
"""真机验证：开卷摄取对话框（进度条 / 日志 / AI 对话 / 完成后进入运行界面）。

不是内存构造控件的假测试——它**真的启动 Flet 窗口**、真的跑一遍摄取管线
（MOCK 模式，零网络），并在自动阶段 / AI 对话阶段 / 完成后各截一张图，
同时把进度条数值、日志条数、对话条数写成 JSON 报告，便于核对。

跑法：
    .venv\\Scripts\\python.exe tools/verify_ingest_ui.py
产出：
    assets/screenshots/ingest_1_auto.png
    assets/screenshots/ingest_2_chat.png
    assets/screenshots/ingest_3_main.png
    assets/screenshots/ingest_report.json

English:
Real-machine verification: open the ingest dialog (progress bar / log / AI conversation / enter
run UI when done).
Not a fake test that builds widgets in memory —— it **actually launches a Flet window**,
actually runs through the ingest pipeline
(MOCK mode, zero network), and takes one screenshot each at the automatic phase / AI
conversation phase / after completion,
while writing the progress bar value, log line count, and conversation line count into a JSON
report for easy checking.
How to run:
    .venv\\Scripts\\python.exe tools/verify_ingest_ui.py
Output:
    assets/screenshots/ingest_1_auto.png
    assets/screenshots/ingest_2_chat.png
    assets/screenshots/ingest_3_main.png
    assets/screenshots/ingest_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 演示模式：零网络、零成本、可复现
# [EN] Demo mode: zero network, zero cost, reproducible
import os                            # noqa: E402
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang(_lang)

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)


def make_fixture(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text(
        '# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n转：最可信的人露出破绽。\n合：有人离开。\n',
        encoding='utf-8')
    (src / '人物设定.md').write_text(
        '# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n\n'
        '「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n' * 8, encoding='utf-8')
    return src


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    report: dict = {'steps': []}
    tmp = Path(tempfile.mkdtemp(prefix='nws_uis_'))
    # 项目根**必须隔离**：摄取流程会真的建一个项目 + 运行文件夹，
    # 不隔离就等于往用户的「拾卷」列表里塞东西（本机的残留夹具就是这么来的）。
    # [EN] Project root **must be isolated**: the ingest flow will actually create a project + run folder,
    # [EN] not isolating means stuffing things into the user's "拾卷" list (that's where the leftover
    # [EN] fixtures on this machine came from).
    VU.isolate_projects_dir(tmp / 'Projects')

    def snap(name: str):
        return OUT / name

    suffix = '' if _lang == 'zh' else f'_{_lang}'

    async def shot(name: str, note: str):
        try:
            page.update()
            await asyncio.sleep(0.4)
            data = await page.take_screenshot()
            fname = name.replace('.png', f'{suffix}.png')
            snap(fname).write_bytes(data)
            report['steps'].append({'shot': fname, 'note': note, 'bytes': len(data)})
        except Exception as e:
            report['steps'].append({'shot': name, 'error': str(e)})

    try:
        src = make_fixture(tmp)
        # 走真实入口：先开向导，再点「开始摄取」
        # [EN] Go through the real entry point: first open the wizard, then click "Start Ingest"
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)

        app._wizard_path = str(src)
        app._wizard_name = '雨夜来客UI'
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = False    # 这一步会停下等确认，脚本里跳过
        # [EN] This step stops and waits for confirmation; skip it in the script
        app._do_import(page)

        # ── 自动阶段：等日志出现 ──
        # [EN] ── Automatic phase: wait for logs to appear ──
        st = app._ingest_state
        for _ in range(60):
            await asyncio.sleep(0.1)
            if st.get('ui') and len(st['ui']['log_list'].controls) >= 4:
                break
        ui = st.get('ui') or {}
        report['auto'] = {
            'progress': ui.get('prog').value if ui.get('prog') else None,
            'pct_text': ui.get('pct_text').value if ui.get('pct_text') else None,
            'stage': ui.get('stage_text').value if ui.get('stage_text') else None,
            'log_lines': len(ui.get('log_list').controls) if ui.get('log_list') else 0,
        }
        await shot('ingest_1_auto.png', '自动摄取阶段：进度条 + 实时日志')

        # ── 同意门：本地读完后会停住，等作者对「正文外发」表态 ──
        # 夹具里有正文，所以这里必然出现「含小说正文」那条警告 + 一个必勾框。
        # [EN] ── Consent gate: after local reading it stops, waiting for the author to weigh in on "sending
        # [EN] body text out" ──
        # [EN] The fixture contains body text, so the "contains novel body text" warning + a required checkbox
        # [EN] must appear here.
        consent = {}
        for _ in range(120):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            panel = ui.get('consent_panel')
            if panel is not None and panel.visible:
                break
        ui = st.get('ui') or {}
        boxes = list(ui.get('consent_boxes') or [])
        consent = {
            'panel_visible': bool(getattr(ui.get('consent_panel'), 'visible', False)),
            'panes_hidden': not bool(getattr(ui.get('panes'), 'visible', True)),
            'title': str(getattr(ui.get('consent_title'), 'value', '') or ''),
            'facts': [str(c.value) for c in (ui.get('consent_facts').controls
                                             if ui.get('consent_facts') else [])],
            'warns': [str(c.value) for c in (ui.get('warn_box').controls
                                             if ui.get('warn_box') else [])
                      if isinstance(c, ft.Text)],
            'box_labels': [str(b.label) for b in boxes],
            'agree_disabled_before': bool(getattr(ui.get('consent_agree'),
                                                  'disabled', False)),
        }
        await shot('ingest_1b_consent.png', '交给 AI 之前：概览 + 两条警告 + 勾选')

        # 勾上（真的改控件值并触发它的 on_change，再看按钮解锁没有）
        # [EN] Check it (actually change the control value and trigger its on_change, then see if the button
        # [EN] unlocks)
        for b in boxes:
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        consent['agree_disabled_after'] = bool(
            getattr(ui.get('consent_agree'), 'disabled', False))
        report['consent'] = consent
        (OUT / 'ingest_consent_snapshot.json').write_text(
            json.dumps(consent, ensure_ascii=False, indent=2), encoding='utf-8')

        if ui.get('consent'):
            ui['consent'](True)      # 同意 → 管线继续
            # [EN] Consent → pipeline continues
        await asyncio.sleep(0.5)

        # ── AI 对话阶段 ──
        # [EN] ── AI conversation phase ──
        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(0.8)
        ui = st.get('ui') or {}
        chat_n_before = len(ui['chat_list'].controls) if ui.get('chat_list') else 0
        report['chat_phase_entered'] = st.get('phase')
        report['chat_messages_after_review'] = chat_n_before
        report['chat_input_disabled'] = ui.get('chat_input').disabled if ui.get('chat_input') else None
        await shot('ingest_2_chat.png', 'AI 体检报告已到，输入框解锁')

        # ── 模拟作者打字：真的走发送逻辑 ──
        # 故意写长（>40 个全角字）：短消息即使气泡不换行也看不出毛病，
        # 只有长消息才会越过面板右边界 —— 也就是用户报的那个 bug。
        # [EN] ── Simulate author typing: actually go through the send logic ──
        # [EN] Deliberately write long (>40 full-width chars): short messages don't reveal defects even if the
        # [EN] bubble doesn't wrap,
        # [EN] only long messages cross the panel's right boundary —— which is exactly the bug the user
        # [EN] reported.
        if ui.get('chat_input'):
            ui['chat_input'].value = ('把主角的秘密改成和那口井有关，再补两条伏笔；'
                                      '另外主角的口癖我想改成偏冷的说法，'
                                      '世界观里那条忌讳也要写清楚它是谁定的、'
                                      '违了会怎么样，最后把回收节点落到具体章次上。')
            ui['send'](None)
            await asyncio.sleep(1.2)
        report['chat_messages_after_user_turn'] = len(ui['chat_list'].controls) if ui.get('chat_list') else 0
        report['log_lines_before_finish'] = len(ui['log_list'].controls) if ui.get('log_list') else 0
        # 文本证据：日志尾部 + 全部对话
        # [EN] Text evidence: log tail + full conversation
        #
        # ⚠ 日志列表里**不只有 `Text`**（v1.39 起阶段之间还插了"横线 + 空行"两个 `Container`），
        # 所以不能再无条件读 `.value`（以前这么写，改完当场 `AttributeError` 挂在这行，
        # 而且窗口还开着、脚本一直挂着）。
        # [EN] ⚠ The log list **is not only `Text`** (since v1.39 two `Container`s of "horizontal line + blank
        # [EN] line" are inserted between phases),
        # [EN] so `.value` can no longer be read unconditionally (written this way before, it crashed right
        # [EN] here with `AttributeError` immediately after the change,
        # [EN] and the window was still open, the script hung forever).
        if ui.get('log_list'):
            report['log_tail'] = VU.log_cells(ui['log_list'].controls[-16:])
            report['log_separators'] = VU.count_separators(ui['log_list'].controls)
        if ui.get('chat_list'):
            report['chat_texts'] = []
            for row in ui['chat_list'].controls:
                try:
                    bubbles = [c for c in row.controls if isinstance(c, ft.Container)]
                    if bubbles:
                        inner = bubbles[0].content
                        report['chat_texts'].append(str(getattr(inner, 'value', inner)))
                except Exception:
                    pass
        await shot('ingest_2b_after_reply.png', '作者下指令后 AI 的修改说明')

        # ── 「对话栏的文字有没有被右边缘吞掉」（用户 2026-10-05 报的 bug）──
        # 纯控件树看不出来：气泡在树里好好的，是**排版**把它撑出了面板。
        # 所以这里量像素：栏内墨迹最右 x 到面板右边界的"车道"，<6px 就是被裁。
        # [EN] ── "Is the conversation panel text being swallowed by the right edge" (bug reported by user
        # [EN] 2026-10-05) ──
        # [EN] Pure widget-tree inspection won't show it: the bubble looks fine in the tree; it's **layout**
        # [EN] that pushed it out of the panel.
        # [EN] So measure pixels here: the "lane" from the rightmost ink x in the panel to the panel's right
        # [EN] boundary, <6px means clipped.
        try:
            clip = VU.chat_pane_clip(OUT / f'ingest_2b_after_reply{suffix}.png')
            report['chat_bubble'] = clip
        except Exception as e:
            report['chat_bubble'] = {'error': str(e), 'verdict': 'CLIPPED'}

        # ── 完成 → 关框 → 运行界面 ──
        # [EN] ── Done → close dialog → run UI ──
        if ui.get('finish'):
            ui['finish']()
        for _ in range(150):
            await asyncio.sleep(0.1)
            if app._view == 'main':
                break
        await asyncio.sleep(1.0)
        report['final_view'] = app._view
        report['project'] = app.current_project.name if app.current_project else None
        report['project_settings_files'] = (
            sorted(p.name for p in app.current_project.settings_dir.iterdir())
            if app.current_project and app.current_project.settings_dir.exists() else [])
        report['dialog_stack_after'] = len(
            [d for d in (getattr(page, '_dialogs', None).controls if getattr(page, '_dialogs', None) else [])
             if getattr(d, 'open', False)])
        await shot('ingest_3_main.png', '完成后：对话框已关闭，进入运行界面')

        report['ok'] = (report.get('final_view') == 'main'
                        and report.get('chat_phase_entered') == 'chat'
                        and report.get('chat_messages_after_user_turn', 0) > chat_n_before
                        and (report.get('chat_bubble') or {}).get('verdict') == 'OK')
        # 清理本次验证创建的项目，避免污染「拾卷」列表
        # [EN] Clean up the project created by this verification to avoid polluting the "拾卷" list
        try:
            if app.current_project and app.current_project.root.exists():
                VU.safe_rmtree(app.current_project.root, ignore_errors=True)
                report['cleaned_project'] = str(app.current_project.root)
        except Exception as e:
            report['cleanup_error'] = str(e)
    except Exception as e:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        (OUT / f'ingest_report{suffix}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        VU.safe_rmtree(tmp, ignore_errors=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] cancels this coroutine; the line `exit_now(...)` after `await shutdown(page)`
        # [EN] **never executes** (exit code is always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


ft.run(main)
