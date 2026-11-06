# -*- coding: utf-8 -*-
"""真机验证：开卷向导「故事类型 / 风格来源」——**界面说人话、后台存真值**。

用户：「把开卷的第二步 故事类型 风格来源里的 Auto 和 Plain 也都改成显示中文和英文的
正确描述，**只在后台保存真的值**。」

三部分：
  A. **选项本身**：键是落盘真值（`auto` / `plain` / 中文类型名），显示文字是人话且
     **两种语言下都不是裸变量值**；每个选项都得有 `content`
     （`DropdownM2` 只认 `key`，显示文字全靠 `content`，见 §22）。
  B. **真值真的存下来了**：手动指定类型 → 类型判定**跳过 LLM**（`理由=手动指定`）且
     项目文件里 `类型=` 记的是指定值；风格来源原样写进 `.nwsproj` 的 `风格=`。
  C. **真机 GUI**：切到第 2 步截图 → 下拉里显示的是人话（**像素量宽度**，
     裸 `auto` 只有 30 来 px，人话 9 个字 120px 起）→ 第 4 步摘要也不出现 `auto`/`plain`
     → 选完一路走完（同意门），读回 `.nwsproj` 确认落盘的是真值。

产出 `assets/screenshots/wizard_choices_*.png` + `wizard_choices_report.json`。

跑法：
    .venv/Scripts/python tools/verify_wizard_choices.py
    .venv/Scripts/python tools/verify_wizard_choices.py --logic-only

English:
Real-machine verification: opening wizard "Story Type / Style Source" -- **UI says
human-readable, backend stores true values**.
User: "Change the Auto and Plain in step two of the opening, Story Type and Style Source, to
display the Chinese and English
correct descriptions, **only store the true values in the backend**."
Three parts:
  A. **The option itself**: the key is the persisted true value (`auto` / `plain` / Chinese type name), the display text is human-readable and
     **neither is the bare variable value in either language**; every option must have a `content`
     (`DropdownM2` only recognizes `key`, the display text relies entirely on `content`, see §22).
  B. **The true value is really saved**: manually specify type -> type determination **skips the LLM** (`reason=manual`) and
     the project file records the specified value for `type=`; style source is written as-is into `style=` of `.nwsproj`.
  C. **Real-machine GUI**: switch to step 2 and screenshot -> the dropdown displays human-readable (measured by **pixel width**,
     bare `auto` is only ~30px, human-readable 9 characters starts at 120px) -> the step 4 summary also doesn't show `auto`/`plain`
     -> after choosing, walk all the way through (consent gate), read back `.nwsproj` to confirm what's persisted is the true value.
Produces `assets/screenshots/wizard_choices_*.png` + `wizard_choices_report.json`.
How to run:
    .venv/Scripts/python tools/verify_wizard_choices.py
    .venv/Scripts/python tools/verify_wizard_choices.py --logic-only
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                       # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'steps': [], 'produced': {}}

# 键就是落盘值。加/改选项时这两张表要一起动。
# [EN] The key is the persisted value. When adding/changing options these two tables must be updated
# [EN] together.
WANT_GENRE_KEYS = ['auto', '悬疑·单元', '玄幻修仙', '都市', '历史架空', '言情', '科幻']
WANT_STYLE_KEYS = ['auto', 'plain', '冷笔白描', '华丽辞藻']
BARE = ('auto', 'plain', 'custom')          # 不允许**整串**出现在用户眼前
# [EN] The **entire string** must not appear in front of the user


def rec(name: str, ok: bool, detail: str = '') -> bool:
    ok = bool(ok)
    report['steps'].append({'name': name, 'ok': ok, 'detail': str(detail)[:220]})
    print(f'  [{"OK" if ok else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return ok


def _fixture(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n起：雨夜来客。\n承：旧事翻出。\n', encoding='utf-8')
    (src / '人物设定.md').write_text('# 人物\n## 主角\n掌柜。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦。\n\n「你今日话里有话。」\n\n' * 6, encoding='utf-8')
    return src


# ══════════════════════════════════════════════════════════════
#  A. 选项本身
# [EN] A. The option itself
# ══════════════════════════════════════════════════════════════
def test_options() -> bool:
    print('\n── A. 选项：键是真值、显示是人话 ──')
    import i18n
    from gui.app_flet import (genre_label, genre_options, mk_dropdown,
                              style_source_label, style_source_options)

    def _built(options, value: str):
        """拿到**建好的下拉框**里的选项。

        `content` 不是工厂加的 —— 它由 `mk_dropdown` 的 `_norm_options()` 统一补
        （一处修全部的修法）。所以要断言"屏幕上会不会显示成 key"，
        必须查真正拿去渲染的那份，而不是原始列表。
        
                English:
        Get the options inside the **built dropdown**.
                `content` is not added by the factory -- it's filled in uniformly by `_norm_options()` of `mk_dropdown`
                (one place fixes all). So to assert "will the key be displayed on screen",
                you must check the copy actually used for rendering, not the raw list.
        """
        row = mk_dropdown('占位', options, value)
        return list(row._field.options)

    ok = True
    for lang in ('zh', 'en'):
        i18n.set_lang(lang)
        g = _built(genre_options(), 'auto')
        s = _built(style_source_options(), 'auto')
        sc = _built(style_source_options(include_custom=True), 'auto')
        tag = '中文' if lang == 'zh' else 'English'

        ok &= rec(f'[{tag}] 故事类型：7 项、键 == 落盘真值',
                  [o.key for o in g] == WANT_GENRE_KEYS, str([o.key for o in g]))
        ok &= rec(f'[{tag}] 风格来源：4 项、键 == 落盘真值',
                  [o.key for o in s] == WANT_STYLE_KEYS, str([o.key for o in s]))
        ok &= rec(f'[{tag}] 书斋那份多一个 custom（+1 项）',
                  [o.key for o in sc] == WANT_STYLE_KEYS + ['custom'],
                  str([o.key for o in sc]))

        texts = [str(o.text or '') for o in g + sc]
        bare = [x for x in texts if x.strip().lower() in BARE]
        ok &= rec(f'[{tag}] **没有任何选项显示裸变量值**（auto / plain / custom）',
                  not bare, f'裸值={bare}')
        ok &= rec(f'[{tag}] 选项文字都非空', all(x.strip() for x in texts),
                  ' ｜ '.join(texts)[:140])
        ok &= rec(f'[{tag}] 每个选项都带 content（DropdownM2 靠它显示文字）',
                  all(getattr(o, 'content', None) is not None for o in g + sc))
        ok &= rec(f'[{tag}] content 的文字 == text（不会显示成 key）',
                  all(str(getattr(getattr(o, 'content', None), 'value', '')) == str(o.text)
                      for o in g + sc))
        report.setdefault('options', {})[lang] = {
            'genre': {o.key: o.text for o in g},
            'style': {o.key: o.text for o in s},
        }

    i18n.set_lang('zh')
    zh_g = {o.key: o.text for o in genre_options()}
    i18n.set_lang('en')
    en_g = {o.key: o.text for o in genre_options()}
    i18n.set_lang('zh')
    ok &= rec('两种语言下标签确实不同（真的翻了，不是同一串）',
              zh_g != en_g, f'zh={zh_g.get("auto")} ｜ en={en_g.get("auto")}')

    # 未知值原样返回，不炸（.nwsproj 里手改出来的怪值）
    # [EN] Unknown values are returned as-is, no explosion (weird values hand-edited in .nwsproj)
    ok &= rec('未知值原样返回（不崩、不乱猜）',
              genre_label('我自己编的类型') == '我自己编的类型'
              and style_source_label('weird') == 'weird',
              genre_label('我自己编的类型'))
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 真值真的被用上 / 存下来
# [EN] B. The true value is actually used / saved
# ══════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    print('\n── B. 手动指定真的生效、真的落盘 ──')
    from store.project import Project
    from ingest.pipeline import run_ingest

    ok = True
    tmp = Path(tempfile.mkdtemp(prefix='nws_wiz_'))
    try:
        # ① 手动指定类型 → 跳过 LLM 类型判定
        # [EN] ① Manually specify type -> skip LLM type determination
        src = _fixture(tmp / 'a')
        CFG.set('STORY_GENRE', '玄幻修仙')
        res = asyncio.run(run_ingest(src))
        g = res.genre
        ok &= rec('指定类型后：类型判定**没有调 LLM**（理由=手动指定）',
                  str(g.get('理由', '')) == '手动指定', str(g.get('理由')))
        ok &= rec('题型取到指定的那个值', str(g.get('主题材')) == '玄幻修仙',
                  str(g.get('主题材')))

        # ② 自动 → 仍走 AI
        # [EN] ② Auto -> still goes through AI
        src2 = _fixture(tmp / 'b')
        CFG.set('STORY_GENRE', 'auto')
        res2 = asyncio.run(run_ingest(src2))
        ok &= rec('选「自动判断」时仍由 AI 判定（理由 != 手动指定）',
                  str(res2.genre.get('理由', '')) != '手动指定',
                  str(res2.genre.get('理由')))

        # ③ 落盘：类型/风格写进 .nwsproj 的都是**真值**
        # [EN] ③ Persist: type/style written to .nwsproj are all **true values**
        proj_root = tmp / 'Projects'
        proj = Project.create_new(proj_root, '落盘验证',
                                  genre='玄幻修仙', style='plain',
                                  source_folder=str(src))
        txt = proj.nwsproj_path.read_text(encoding='utf-8')
        ok &= rec('.nwsproj 里 类型= 记的是真值（不是显示名）',
                  '玄幻修仙' in txt and '自动判断' not in txt,
                  next((l for l in txt.splitlines() if l.startswith('类型')), ''))
        ok &= rec('.nwsproj 里 风格= 记的是真值 plain（不是「朴素白描」）',
                  'plain' in txt, next((l for l in txt.splitlines()
                                        if l.startswith('风格')), ''))
        report['nwsproj_excerpt'] = [l for l in txt.splitlines()
                                     if l.startswith(('类型', '风格'))]
    finally:
        CFG.set('STORY_GENRE', 'auto')
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 真机
# [EN] C. Real machine
# ══════════════════════════════════════════════════════════════
async def _measure_shown_text(page, dlg, rows: list) -> list[dict]:
    """量每个下拉框**里显示的那串字**有多宽（像素）。

    做法：把外壳 `Container` 的底色临时涂成标记色 → 在屏幕上找到它的矩形 →
    量矩形里的墨迹宽度，**右侧 34px 排除掉**（那是下拉箭头）。
    裸 `auto` ≈ 30px，人话（9 个全角字）≈ 120px 起，一眼分得开。

    不按边框色找的原因：对话框是多层半透明，颜色会被合成掉（`UI_OPACITY` 一变就漂）。
    
        English:
    Measure how wide (in pixels) the **string displayed inside** each dropdown is.
        Method: temporarily paint the shell `Container`'s background a marker color -> find its rectangle on screen ->
        measure the ink width inside the rectangle, **excluding the right 34px** (that's the dropdown arrow).
        Bare `auto` ≈ 30px, human-readable (9 full-width characters) ≈ 120px and up, easy to tell apart at a glance.
        Why not find it by border color: the dialog is multi-layered and translucent, colors get composited away (`UI_OPACITY` shifting makes it drift).
    """
    from PIL import Image
    MARK = '#00ffff'
    shells = []
    for r in rows:
        if len(r.controls) > 1 and isinstance(r.controls[1], __import__('flet').Container):
            shells.append(r.controls[1])
    old = [s.bgcolor for s in shells]
    try:
        for s in shells:
            s.bgcolor = MARK
        page.update()
        await asyncio.sleep(0.5)
        shot = await page.take_screenshot()
    finally:
        for s, o in zip(shells, old):
            s.bgcolor = o
        page.update()

    png = OUT / 'wizard_choices_marker.png'
    png.write_bytes(shot)
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size

    def is_mark(c):
        r, g, b = c
        return g > 190 and b > 190 and r < 90

    # 标记块：按行找，再取每块的横向范围
    # [EN] Marker blocks: find by rows, then take the horizontal extent of each block
    rows_y = [y for y in range(H)
              if sum(1 for x in range(0, W, 2) if is_mark(px[x, y])) >= 60]
    segs: list[tuple[int, int]] = []
    st = prev = None
    for y in rows_y:
        if st is None:
            st = prev = y
        elif y - prev <= 4:
            prev = y
        else:
            segs.append((st, prev))
            st = prev = y
    if st is not None:
        segs.append((st, prev))

    out = []
    for (y0, y1) in segs:
        if y1 - y0 < 10:
            continue
        xs = [x for y in range(y0, y1 + 1) for x in range(W) if is_mark(px[x, y])]
        if not xs:
            continue
        x0, x1 = min(xs), max(xs)

        def lum(c):
            return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

        ink = [x for y in range(y0 + 2, y1 - 1)
               for x in range(x0 + 1, x1) if lum(px[x, y]) < 150]
        ink = sorted(set(ink))
        if not ink:
            out.append({'y': (y0, y1), 'x': (x0, x1), 'text_w': 0})
            continue
        groups, s0 = [], ink[0]
        pv = ink[0]
        for x in ink[1:]:
            if x - pv > 12:                 # 隔 12px 以上算另一团（文字 vs 箭头）
            # [EN] More than 12px apart counts as another cluster (text vs arrow)
                groups.append((s0, pv))
                s0 = x
            pv = x
        groups.append((s0, pv))
        groups = [g for g in groups if g[1] < x1 - 34]      # 排掉右侧箭头
        # [EN] Exclude the arrow on the right
        w = (groups[-1][1] - groups[0][0] + 1) if groups else 0
        out.append({'y': (y0, y1), 'x': (x0, x1), 'text_w': w,
                    'groups': groups})
    return out


async def test_gui(page) -> bool:
    import flet as ft

    import verify_ui_common as VU
    ok = True
    tmpdirs = [Path(tempfile.mkdtemp(prefix='nws_wiz_gui_'))]
    try:
        proj_root = tmpdirs[0] / 'projects'
        proj_root.mkdir(parents=True, exist_ok=True)
        VU.isolate_projects_dir(proj_root)
        from gui.app_flet import NovelWorldApp
        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        src = _fixture(tmpdirs[0] / 'src')
        app._wizard_path = str(src)
        app._wizard_name = '选项验证'
        app._wizard_opts['ai_optimize'] = False
        dlg = app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)

        def nodes_of(ctrl) -> list:
            out: list = []

            def walk(c, d=0):
                if c is None or d > 40:
                    return
                out.append(c)
                for a in ('controls', 'content', 'actions', 'title'):
                    v = getattr(c, a, None)
                    if isinstance(v, list):
                        for x in v:
                            walk(x, d + 1)
                    elif v is not None and hasattr(v, '__class__'):
                        walk(v, d + 1)
            walk(ctrl)
            return out

        # 第 2 步的内容对象在 steps 里，直接调一次拿到控件（不依赖点按钮）
        # 「下一步」按钮的走法要点两次；这里直接取第 2 步的内容渲染出来，
        # 测的是**控件本身**（下拉显示什么），不掺步骤切换的干扰。
        # [EN] The content object of step 2 is in steps, call it once directly to get the control (no need to
        # [EN] click buttons)
        # [EN] "Next" button requires two clicks to advance; here directly take the content of step 2 and
        # [EN] render it,
        # [EN] what's tested is the **control itself** (what the dropdown displays), without the interference
        # [EN] of step switching.
        s2 = app._wizard_step2_settings(page)
        dlg.content = ft.Container(
            content=ft.Column(s2['content'], spacing=12, scroll=ft.ScrollMode.AUTO),
            width=690, height=560)
        page.update()
        await asyncio.sleep(0.8)

        ns = nodes_of(dlg.content)
        dds = [c for c in ns if isinstance(c, ft.DropdownM2)]
        boxes = [c for c in ns if isinstance(c, ft.Checkbox)]
        report['gui_dropdowns'] = [{'value': d.value,
                                    'options': [{'key': o.key, 'text': o.text}
                                                for o in (d.options or [])]}
                                   for d in dds]
        # 2026-10-06 起第 2 步是**三个**下拉：多了「输出语言」（项目级，见 `util/outlang`）
        # [EN] As of 2026-10-06 step 2 has **three** dropdowns: an extra "Output Language" (project-level, see
        # [EN] `util/outlang`)
        ok &= rec('第 2 步渲染出 3 个下拉框（故事类型 / 风格来源 / 输出语言）',
                  len(dds) == 3, f'{len(dds)} 个')
        all_texts = [str(o.text or '') for d in dds for o in (d.options or [])]
        all_keys = [str(o.key or '') for d in dds for o in (d.options or [])]
        ok &= rec('真机里也没有裸变量值当显示文字',
                  not [x for x in all_texts if x.strip().lower() in BARE],
                  ' ｜ '.join(all_texts)[:140])
        ok &= rec('真机里键仍是真值（含 auto / plain）',
                  'auto' in all_keys and 'plain' in all_keys, str(all_keys[:6]))
        ok &= rec('每个选项都有 content（否则会显示成 key）',
                  all(getattr(o, 'content', None) is not None
                      for d in dds for o in (d.options or [])))

        page.update()
        await asyncio.sleep(0.4)
        png = OUT / 'wizard_choices_step2.png'
        png.write_bytes(await page.take_screenshot())
        report['produced']['step2'] = str(png)
        rows = [c for c in ns if isinstance(c, ft.Row)
                and getattr(c, '_field', None) in dds]
        widths = await _measure_shown_text(page, dlg, rows)
        report['produced']['dropdown_boxes'] = widths
        ws = [w['text_w'] for w in widths if w.get('text_w')]
        # ⚠ 阈值从 100 放到 60：第 2 步第三个下拉（输出语言）的默认值是「跟随界面语言」，
        #   6 个字 ≈ 88px —— 它**也是人话**，只是比「自动判断（由 AI 读正文后决定）」短。
        #   60 仍然远大于裸值（`auto` ≈ 30px、`en` ≈ 20px），所以这条判据的**本意没变**：
        #   "屏幕上画的是人话，不是变量值"。实测 204 / 182 / 88。
        # [EN] ⚠ Threshold lowered from 100 to 60: the default value of the third dropdown (output language) in
        # [EN] step 2 is "Follow UI Language",
        # [EN] 6 characters ≈ 88px -- it is **also human-readable**, just shorter than "Auto-detect (decided by
        # [EN] AI after reading the body)".
        # [EN] 60 is still far larger than the bare value (`auto` ≈ 30px, `en` ≈ 20px), so the **intent of this
        # [EN] criterion is unchanged**:
        # [EN] "What's drawn on screen is human-readable, not the variable value". Measured 204 / 182 / 88.
        ok &= rec('**像素**：三个下拉框里显示的都是人话（≥60px），不是 30px 的 auto',
                  len(ws) >= 3 and min(ws) >= 60,
                  f'实测文字宽 {ws}（裸 auto ≈ 30px）')

        # ── 第 4 步摘要：不许出现 auto / plain ──
        # [EN] ── Step 4 summary: auto / plain must not appear ──
        app._wizard_genre = '玄幻修仙'
        app._wizard_style = 'plain'
        s4 = app._wizard_step4_confirm(page)
        dlg.content = ft.Container(
            content=ft.Column(s4['content'], spacing=12, scroll=ft.ScrollMode.AUTO),
            width=690, height=560)
        page.update()
        await asyncio.sleep(0.5)
        texts = [str(getattr(c, 'value', '') or '')
                 for c in nodes_of(dlg.content) if isinstance(c, ft.Text)]
        summary = next((x for x in texts if '故事类型' in x), '')
        report['produced']['summary'] = summary
        ok &= rec('第 4 步摘要里出现「故事类型 / 风格来源」两行',
                  '故事类型' in summary and '风格来源' in summary, summary.replace('\n', ' ｜ ')[:150])
        ok &= rec('摘要里**没有** auto / plain 这类裸值',
                  not any(x in summary for x in ('auto', 'plain')), summary.replace('\n', ' | ')[:150])
        ok &= rec('摘要显示的是人话（类型=玄幻修仙 / 风格=朴素白描…）',
                  '玄幻修仙' in summary and '朴素白描' in summary,
                  summary.replace('\n', ' ｜ ')[:150])

        # ── 一路走完：确认落盘的是真值 ──
        # [EN] ── Walk all the way through: confirm what's persisted is the true value ──
        page.update()
        await asyncio.sleep(0.3)
        app._wizard_opts['repair_source'] = False    # 这一步会停下等确认，脚本里跳过
        # [EN] This step stops and waits for confirmation, skip it in the script
        app._do_import(page)
        st = app._ingest_state
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            if ui.get('consent_panel') is not None and ui['consent_panel'].visible:
                break
        ui = st.get('ui') or {}
        for b in list(ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        if ui.get('consent'):
            ui['consent'](True)
        for _ in range(200):
            await asyncio.sleep(0.1)
            if not st.get('running'):
                break
        proj = app.current_project
        ok &= rec('走完开卷后拿到了项目', proj is not None,
                  proj.name if proj else 'None')
        if proj is not None:
            txt = proj.nwsproj_path.read_text(encoding='utf-8')
            lines = {l.split('=', 1)[0].strip(): l.split('=', 1)[1].strip()
                     for l in txt.splitlines() if '=' in l}
            report['produced']['nwsproj'] = {k: v for k, v in lines.items()
                                             if k in ('类型', '风格')}
            ok &= rec('落盘的 类型 = 手动指定值「玄幻修仙」',
                      lines.get('类型') == '玄幻修仙', str(lines.get('类型')))
            ok &= rec('落盘的 风格 = 真值 plain（不是「朴素白描」）',
                      lines.get('风格') == 'plain', str(lines.get('风格')))
        report['ok'] = bool(ok)
    except Exception:                                          # noqa: BLE001
        report['ok'] = False
        report['error'] = traceback.format_exc()[-1800:]
        print(report['error'])
    finally:
        import verify_ui_common as VU2
        for d in tmpdirs:
            VU2.safe_rmtree(d, ignore_errors=True)
        # ⚠ **收尾必须自己关窗口**（技能 §6.2「退出三件套」）：
        # `ft.run()` 是**阻塞**的，它会一直等到客户端窗口退出才返回；
        # 不关窗口的话脚本会永远挂在这里 —— 报告写不出来、进程也不退
        # （本脚本以前就是这么挂住的：跑完所有断言后卡死，只能被超时杀掉）。
        # [EN] ⚠ **The teardown must close the window itself** (skill §6.2 "Exit trio"):
        # [EN] `ft.run()` is **blocking**, it won't return until the client window exits;
        # [EN] if the window isn't closed the script hangs here forever -- no report written, process won't
        # [EN] exit either
        # [EN] (This script used to hang exactly like this: deadlocked after running all assertions, could only
        # [EN] be killed by timeout).
        try:
            report['ok'] = bool(report.get('ok'))
            (OUT / 'wizard_choices_report.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            n_ok = sum(1 for s in report['steps'] if s['ok'])
            print(f'\n真机验证：{n_ok}/{len(report["steps"])} 项通过')
            print('→', '全部通过' if report.get('ok') else '有失败')
        except Exception:                                   # noqa: BLE001
            traceback.print_exc()
        from util.flet_shutdown import shutdown, exit_now
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be committed **before closing the window**: `page.window.destroy()` will
        # [EN] raise CancelledError
        # [EN] cancelling this coroutine, so the `exit_now(...)` on the line after `await shutdown(page)`
        # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)
    return bool(report.get('ok'))


if __name__ == '__main__':
    logic_only = '--logic-only' in sys.argv
    logic_ok = test_options() and test_wiring()
    report['logic_ok'] = logic_ok
    if logic_only:
        report['ok'] = logic_ok
        (OUT / 'wizard_choices_report_logic.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        n_ok = sum(1 for s in report['steps'] if s['ok'])
        print(f'\n逻辑验证：{n_ok}/{len(report["steps"])} 项通过')
        sys.exit(0 if logic_ok else 1)

    import flet as ft
    # 报告与退出都在 `test_gui` 的 finally 里做（它必须自己把窗口关掉，
    # 否则 `ft.run` 不返回 —— 见那里的注释）。
    # [EN] Report and exit are both done in the finally of `test_gui` (which must close the window itself,
    # [EN] otherwise `ft.run` won't return -- see the comments there).
    ft.run(test_gui)
