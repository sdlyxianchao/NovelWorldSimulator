# -*- coding: utf-8 -*-
"""真机验证：说明书里的插图（`![](…)`）**真的存在、真的画得出来**。

为什么不能只查字符串
--------------------
说明书是在帮助面板里用 `ft.Markdown` 渲染的，插图**能不能显示**取决于两件与文字无关的事：
  ① 路径对不对 —— `ft.Markdown` **不认绝对路径、也不认 `file://`**，只认相对路径，
     基准是**进程工作目录**（`developers/probe_md_image.py` 实测四种写法）；
  ② 控件肯不肯画 —— 加载失败时只会静默显示 `image_error_content`
     （"图没能加载"），**文字层面一切正常**。
所以判据是**像素**：同一块区域，有插图的那一节颜色数应该比没插图的那节多一个量级
（真截图是照片级渐变，几千色；纸面 + 文字只有几十色）。

跑法：.venv/Scripts/python.exe tools/verify_manual_images.py
产出：assets/screenshots/manual_images_report.json + manual_images_help.png

English:
Real-machine verification: the illustrations in the manual (`![](…)`) **really exist and can
really be drawn**.
Why we cannot just check strings
--------------------
The manual is rendered in the help panel with `ft.Markdown`; whether an illustration **can be
displayed** depends on two things unrelated to the text:
  ① Whether the path is correct -- `ft.Markdown` **does not accept absolute paths, nor `file://`**, only relative paths,
     and the base is the **process working directory** (`developers/probe_md_image.py` tested four forms);
  ② Whether the widget is willing to draw it -- on load failure it only silently shows `image_error_content`
     ("image failed to load"), while **everything at the text level is normal**.
So the criterion is **pixels**: for the same region, the color count of the section with an
illustration should be an order of magnitude higher than the section without one
(a real screenshot is a photo-grade gradient, thousands of colors; paper + text has only dozens
of colors).
How to run: .venv/Scripts/python.exe tools/verify_manual_images.py
Output: assets/screenshots/manual_images_report.json + manual_images_help.png
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
from PIL import Image  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from gui.app_flet import NovelWorldApp, HELP_TOC_W, read_manual  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang(_lang)

OUT = APP_DIR / 'assets' / 'screenshots'
IMG_ROOT = APP_DIR / 'assets' / 'images' / 'manual'
BOX = set('│┌┐└┘├┤┬┴┼─┃━┏┓┗┛')
REPORT: dict = {'lang': _lang}
ITEMS: list = []


def ok(name: str, cond: bool, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:200]})
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f' — {detail}' if detail else ''))
    return bool(cond)


def static_checks(manual: Path, lang: str) -> None:
    text = manual.read_text(encoding='utf-8')
    refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text)

    ok(f'{manual.name}：插图引用 ≥ 15 个', len(refs) >= 15, str(len(refs)))
    missing = [p for p in refs if not (APP_DIR / p).exists()]
    ok(f'{manual.name}：每个插图都在磁盘上', not missing, str(missing[:3]))
    bad_lang = [p for p in refs if f'/manual/{lang}/' not in p]
    ok(f'{manual.name}：插图都取自 {lang}/ 目录', not bad_lang, str(bad_lang[:3]))
    abs_paths = [p for p in refs if p.startswith(('/', 'file:', 'C:', 'http'))]
    ok(f'{manual.name}：没有绝对路径 / file:// 写法（Markdown 认不出）',
       not abs_paths, str(abs_paths[:3]))

    # 文件本身合不合格
    # [EN] Whether the file itself is acceptable
    thin, short = [], []
    total = 0
    # ★★ 2026-10-14 口径修正：**按去重后的图片算体积**。
    #   改之前是"把每个引用都累加一遍"，而同一条说明里**同一张图会被好几章
    #   反复引用**（实测：64 个引用只对应 **32 张**图）⇒ 报出来的 35.6MB
    #   其实是"引用总和"，磁盘上只有 15.9MB。"总体积"这个指标的语义是
    #   **占多大地方**，同一张图引用两次并不会占两份 —— 重复计会让判据
    #   随着"文档多写几个插图"而虚涨，那不是它想守的东西。
    #   ⚠ 改口径**同时**把图真的压小了（15.9MB → 9.0MB，
    #     `developers/shrink_manual_pngs.py`）—— 不是靠改判据过关。
    # [EN] ★★ 2026-10-14 caliber fix: **measure the volume over de-duplicated images**.
    # [EN] It used to "add up every reference", and the same image is **referenced repeatedly by
    # [EN] several chapters** in one manual (measured: 64 references map to only **32** images) =>
    # [EN] the reported 35.6MB was really the "sum over references" while the disk held 15.9MB. The
    # [EN] metric "total size" means **how much space it takes**; referencing the same image twice
    # [EN] does not take two copies -- double counting makes the criterion inflate just because
    # [EN] "the doc showed the illustration a few more times", which is not what it guards.
    # [EN] ⚠ The caliber fix came **together with** genuinely shrinking the images (15.9MB ->
    # [EN] 9.0MB, `developers/shrink_manual_pngs.py`) -- it is not passing by moving the goalposts.
    for p in sorted(set(refs)):
        f = APP_DIR / p
        if not f.exists():
            continue
        total += f.stat().st_size
        try:
            with Image.open(f) as im:
                w, h = im.size
        except Exception as e:                              # noqa: BLE001
            thin.append(f'{p}: {e}')
            continue
        if w < 300 or h < 100:
            short.append(f'{p}:{w}x{h}')
    ok(f'{manual.name}：插图都是能打开的 PNG 且尺寸合理', not (thin or short),
       str((thin + short)[:3]))
    ok(f'{manual.name}：插图总体积 < 12MB', total < 12 * 1024 * 1024,
       f'{total / 1024 / 1024:.1f}MB / {len(refs)} 张')
    REPORT[f'{lang}_total_mb'] = round(total / 1024 / 1024, 2)

    # 目录里不该有没人引用的孤儿图
    # [EN] There should be no orphan images in the directory that nobody references
    used = {Path(p).name for p in refs}
    on_disk = {p.name for p in (IMG_ROOT / lang).glob('*.png')}
    ok(f'{manual.name}：没有孤儿插图（目录里的图都被引用）',
       not (on_disk - used), str(sorted(on_disk - used)[:5]))

    # 界面字符画应该已经清干净。
    # [EN] The UI ASCII art should already be cleaned up.
    #
    # ⚠ **目录树要放过**（`├──` / `└──` 那种）—— 用户 2026-10-06 明确要
    #   「说清楚放在哪里，**给出 ASCII 的文件夹 tree**」，§6.1 里那两棵树是**要留的**。
    #   老判据只按"框线字符数 > 40"一刀切，一棵 12 行的树就被判成"残留字符画"
    #   （实测 60 / 70 字符 → 两条红）。
    #   判法：**整块都是目录树**（有 ≥2 行以 `├──`/`└──`/`│` 开头，
    #   且没有 UI 里才有的角/交叉符号 `┌┐└┘┬┴┼╔╗╚╝`）→ 跳过；
    #   其余代码块照旧按框线字符数判。
    # [EN] ⚠ **The directory tree must be let through** (the `├──` / `└──` kind) -- the user explicitly
    # [EN] requested this on 2026-10-06
    # [EN] "State clearly where it is placed, **give the ASCII folder tree**"; the two trees in §6.1 are
    # [EN] **meant to stay**.
    # [EN] The old criterion just used a flat "box-drawing char count > 40", so a 12-line tree got flagged
    # [EN] as "leftover ASCII art"
    # [EN] (measured 60 / 70 chars -> two reds).
    # [EN] Criterion: **the whole block is a directory tree** (has ≥2 lines starting with `├──`/`└──`/`│`,
    # [EN] and no corner/cross symbols that only appear in UI: `┌┐└┘┬┴┼╔╗╚╝`) -> skip;
    # [EN] other code blocks are still judged by box-drawing char count as before.
    UI_CORNERS = set('┌┐┬┴┼╔╗╚╝╠╣╦╩╬')

    def _is_tree_block(lines: list) -> bool:
        branches = sum(1 for x in lines
                       if x.lstrip().startswith(('├──', '└──', '│')))
        corners = sum(1 for x in lines for c in x if c in UI_CORNERS)
        return branches >= 2 and corners == 0

    art = []
    inside, buf = False, []
    for ln in text.splitlines():
        if ln.strip().startswith('```'):
            if not inside:
                inside, buf = True, []
            else:
                inside = False
                if not _is_tree_block(buf):
                    n = sum(1 for c in '\n'.join(buf) if c in BOX)
                    if n > 40:
                        art.append(f'{n} 字符 @ {buf[0][:24] if buf else ""}')
            continue
        if inside:
            buf.append(ln)
    ok(f'{manual.name}：没有残留的界面字符画（目录树不算）', not art, str(art[:3]))


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.4)
    try:
        for manual, lang in ((APP_DIR / '使用说明.md', 'zh'),
                             (APP_DIR / 'User_Manual.md', 'en')):
            static_checks(manual, lang)

        # ── 真机：在帮助面板里把「有插图的一节」和「没插图的一节」各截一次 ──
        # [EN] ── Real machine: in the help panel, screenshot the "section with an illustration" and the
        # [EN] "section without an illustration" once each ──
        set_lang(_lang)
        intro, secs = read_manual(APP_DIR / '使用说明.md' if _lang == 'zh'
                                  else APP_DIR / 'User_Manual.md')
        ok('读得到说明书并按二级标题切节', len(secs) >= 10, str(len(secs)))

        def _img_offset(body: str) -> int:
            """该节里第一张插图离节首多远（字符数）。没图返回一个很大的数。
                        English:
            How far (in chars) the first illustration in this section is from the start of the section.
            Returns a very large number if there is no image.
            """
            i = body.find('![')
            return i if i >= 0 else 10 ** 9

        # ★ 要挑**第一张图最靠上**的那一节，不能取"第一个带图的节"。
        #   右栏是个不自动滚动的 ListView，`take_screenshot()` 只拍得到可见区；
        #   一节的图若在可视区下方（截图区域只覆盖对话框那么高），量到的就只是文字，
        #   颜色数当然上不去 —— 看着像"图没渲染"，其实是**图根本不在量测区里**。
        #   2026-10-06 往 §2 插图时踩到：§2 的图在节首往下 891 字符处（第 45 行之后），
        #   §2 又恰好成了"第一个带图的节"，于是像素断言两条都假红（652 色 vs 560 色）。
        #   各节插图位置实测：§2 偏移 891（出屏）· §4 偏移 14（在屏上）。
        # [EN] ★ Pick the section where the **first image is highest up**, not "the first section with an
        # [EN] image".
        # [EN] The right pane is a ListView that does not auto-scroll; `take_screenshot()` only captures the
        # [EN] visible area;
        # [EN] if a section's image is below the visible area (the screenshot region only covers as much as the
        # [EN] dialog box height), all you measure is text,
        # [EN] so of course the color count stays low -- it looks like "the image did not render", but actually
        # [EN] **the image is not in the measurement region at all**.
        # [EN] Hit this on 2026-10-06 while inserting an illustration into §2: §2's image is 891 chars below
        # [EN] the start of the section (after line 45),
        # [EN] and §2 happened to be "the first section with an image", so both pixel assertions were falsely
        # [EN] red (652 colors vs 560 colors).
        # [EN] Measured illustration positions per section: §2 offset 891 (off-screen) · §4 offset 14
        # [EN] (on-screen).
        img_secs = [i for i, (_t, b) in enumerate(secs) if '![' in b]
        with_img = min(img_secs, key=lambda i: _img_offset(secs[i][1])) if img_secs else None
        without = next((i for i, (_t, b) in enumerate(secs) if '![' not in b), None)
        ok('说明书里至少有一节带插图', with_img is not None,
           f'带图节 {img_secs}，选中 [{with_img}] {secs[with_img][0] if with_img is not None else ""}'
           f'（图在节首后 {_img_offset(secs[with_img][1]) if with_img is not None else "-"} 字符）')
        ok('也有一节不带插图（用来做对照）', without is not None, str(without))
        REPORT['sec_with_img'] = with_img
        REPORT['sec_without_img'] = without
        REPORT['secs_with_img'] = img_secs

        if with_img is not None and without is not None:
            app.show_help_dialog()
            page.update()
            await asyncio.sleep(1.0)
            dlgs = VU.open_dialogs(page)
            hdlg = dlgs[-1] if dlgs else None
            ok('帮助面板真的打开了', hdlg is not None)
            # ⚠ **别按"写死的宽度"找目录行**（原来是 `c.width == HELP_TOC_W - 14`）：
            #   目录行改由 `ListView` 紧约束撑满之后，它的 `width` 是 `None`，
            #   按宽度找**恒 0 条**（2026-10-06 修）。认构造特征才对：
            # [EN] ⚠ **Do not find directory lines by a "hard-coded width"** (it used to be `c.width == HELP_TOC_W
            # [EN] - 14`):
            # [EN] after the directory lines were changed to be stretched to full width by tight constraints in
            # [EN] `ListView`, their `width` is `None`,
            # [EN] so searching by width gives **always 0 matches** (fixed 2026-10-06). Match by construction
            # [EN] features instead:
            #   `Container` + `on_click` + `border_radius 4` + `padding(6,4,6,4)`。
            def _is_toc(c):
                if not (isinstance(c, ft.Container) and c.on_click is not None
                        and c.border_radius == 4):
                    return False
                pad = getattr(c, 'padding', None)
                return (getattr(pad, 'left', None) == 6
                        and getattr(pad, 'top', None) == 4)
            tocs = [c for c in VU.walk(hdlg) if _is_toc(c)] if hdlg else []
            ok('左栏目录项齐全（≥10 条）', len(tocs) >= 10, str(len(tocs)))

            def md_value() -> str:
                mds = [c for c in VU.walk(hdlg) if isinstance(c, ft.Markdown)]
                return mds[-1].value if mds else ''

            def body_text() -> str:
                """右栏**所有**正文块拼起来。

                ⚠ **别只看 `mds[-1].value`**（原来就是）—— 这一条是真正的病根：
                  `_help_reader_pane()` 把一节按小节**拆成多个 `ft.Markdown`**
                  （`_blocks_of(md)`，注释说为了让 `ListView` 算得准高度）。
                  实测 §2 被拆成 **4 块、共 6011 字**，`mds[-1]` 只是最后一块，
                  于是拿"整节首行"去比"最后一块"必然找不到 ——
                  2026-10-06 往 §2 插图、§2 成为"第一个带插图的节"时才暴露。
                ⚠ 也**不要**先把原文清洗成纯文本再比：`value` 里存的是**原始 Markdown
                  源码**（含 `###`、含 `[文字](锚点)` 原样），清洗过的形态
                  （如把链接压成文字）反而不在里面 —— 直接对不上，实测过。
                
                                English:
                All body blocks of the right pane concatenated.
                                ⚠ **Do not just look at `mds[-1].value`** (that is what it used to do) -- this is the real root cause:
                                  `_help_reader_pane()` splits a section into **multiple `ft.Markdown`** by subsection
                                  (`_blocks_of(md)`, the comment says this is so `ListView` computes accurate heights).
                                  Measured: §2 is split into **4 blocks, 6011 chars total**; `mds[-1]` is only the last block,
                                  so comparing "the section's first line" against "the last block" will of course fail to find it --
                                  this only surfaced on 2026-10-06 when an illustration was inserted into §2 and §2 became "the first section with an illustration".
                                ⚠ Also **do not** clean the original text into plain text before comparing: what is stored in `value` is the **raw Markdown
                                  source** (including `###`, including `[text](anchor)` as-is); the cleaned form
                                  (e.g. links flattened to text) is not in there -- so it directly fails to match; this has been measured.
                """
                parts = [c.value for c in VU.walk(hdlg)
                         if isinstance(c, ft.Markdown) and isinstance(c.value, str)]
                return '\n'.join(parts)

            async def shoot(idx: int, tag: str):
                """按**标题**点目录，并断言"真的切过去了"。

                ⚠ 别按下标点（第一版就是）：目录项比章节多一条（导言/目录本身也占一格），
                于是 `tocs[4]` 打开的是第 3 节 —— 量出来"带图的那节"其实没图，
                颜色数 192 vs 165，看着像"图没渲染"，实际是**量错了对象**。

                切没切过去靠"该节的正文行出现在右栏"来判：取正文里前几行非空原文，
                **命中任意一行**即算成功（比死盯第一行稳，某些节首行是空行/纯符号）。
                
                                English:
                Click the TOC by **heading**, and assert that "it really switched over".
                                ⚠ Do not click by index (the first version did): the TOC has one more entry than there are sections (the intro/TOC itself also takes a slot),
                                so `tocs[4]` opens section 3 -- and the "section with an image" that was measured actually had no image,
                                color count 192 vs 165, looking like "the image did not render", but actually **the wrong target was measured**.
                                Whether it switched over is judged by "the body lines of that section appear in the right pane": take the first few non-empty raw lines from the body,
                                **matching any one line** counts as success (more robust than fixating on the first line; in some sections the first line is empty or pure symbols).
                """
                title, body = secs[idx]
                entry = next((c for c in tocs
                              if any(title.strip() == str(x).strip()
                                     or title.strip() in str(x) for x in VU.all_texts(c))),
                             None)
                assert entry is not None, f'目录里找不到「{title}」'
                entry.on_click(None)
                page.update()
                await asyncio.sleep(1.2)
                got = body_text()

                cands = [l.strip() for l in body.splitlines() if l.strip()][:6]
                probes = [c[:16] for c in cands if len(c) >= 12]
                hit = next((p for p in probes if p in got), '')
                if not probes:
                    ok(f'（跳过）「{title}」取不到可比对的正文行', True, '该节太短')
                else:
                    assert hit, (
                        f'点了「{title}」但右栏没切过去'
                        f'（试了 {probes[:3]}，右栏 {len(got)} 字）')
                raw = await page.take_screenshot()
                p = OUT / f'manual_images_{tag}.png'
                p.write_bytes(raw)
                return p

            if tocs and with_img is not None and without is not None:
                p_img = await shoot(with_img, 'with')
                bb = VU.dialog_bbox(p_img)
                ok('截图里能量到帮助对话框的描金外框', bool(bb), str(bb))
                # 右栏（正文）区域：对话框左侧让出目录宽
                # [EN] Right pane (body) region: the left side of the dialog gives up the width for the TOC
                if bb:
                    px0, px1 = bb[0] + HELP_TOC_W + 10, bb[2] - 14
                    py0, py1 = bb[1] + 54, bb[3] - 16
                    n_img = VU.distinct_colors(p_img, px0, px1, py0, py1, step=2)
                    p_txt = await shoot(without, 'plain')
                    n_txt = VU.distinct_colors(p_txt, px0, px1, py0, py1, step=2)
                    REPORT['colors_with_img'] = n_img
                    REPORT['colors_plain'] = n_txt
                    REPORT['pane'] = [px0, py0, px1, py1]
                    # 真截图是照片级渐变：几千色 vs 纸面文字的几十色
                    # [EN] A real screenshot is a photo-grade gradient: thousands of colors vs the dozens of colors of text
                    # [EN] on paper
                    ok('像素：有插图那节的颜色数 ≫ 没插图那节（图真的画出来了）',
                       n_img > max(500, n_txt * 5),
                       f'带图 {n_img} 色 / 纯文字 {n_txt} 色')
                    ok('像素：有插图那节颜色数 > 1500（不是"图加载失败"的灰字）',
                       n_img > 1500, str(n_img))
                page.pop_dialog()
                page.update()
    except Exception:                                           # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        n_ok = sum(1 for i in ITEMS if i['ok'])
        REPORT['items'] = ITEMS
        REPORT['n_ok'], REPORT['n_all'] = n_ok, len(ITEMS)
        # ★★ 异常必须算失败 —— 否则是**假绿**：
        #    `ITEMS` 只装"已经跑到的断言"。一旦中途抛异常，崩溃点之后的断言
        #    （这里恰恰是整套像素检查：图到底画没画出来）就**一条都没进 ITEMS**，
        #    于是 `n_ok == len(ITEMS)` 照旧成立、报出"全部通过"。
        #    2026-10-06 实测：`[FAIL]` 与 traceback 都打出来了，最后一行仍是
        #    「说明书插图验证：21/21 → 全部通过」，而像素检查一次都没跑。
        # [EN] ★★ An exception must count as failure -- otherwise it is a **false green**:
        # [EN] `ITEMS` only holds "assertions that have already run". Once an exception is thrown midway, the
        # [EN] assertions after the crash point
        # [EN] (here that is exactly the entire pixel check: whether the image was actually drawn) **never make
        # [EN] it into ITEMS at all**,
        # [EN] so `n_ok == len(ITEMS)` still holds and it reports "all passed".
        # [EN] Measured on 2026-10-06: both `[FAIL]` and the traceback were printed, yet the last line was
        # [EN] still
        # [EN] "Manual illustration verification: 21/21 -> all passed", while the pixel check never ran once.
        fatal = bool(REPORT.get('fatal'))
        REPORT['ok'] = (n_ok == len(ITEMS)) and not fatal
        (OUT / 'manual_images_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n说明书插图验证：{n_ok}/{len(ITEMS)}')
        if fatal:
            print('★ 验证中途抛异常，结论无效（崩溃点之后的检查根本没执行）—— 按失败处理')
            print('  详见 assets/screenshots/manual_images_report.json 的 fatal 字段')
        else:
            print('→', '全部通过' if REPORT['ok'] else '有失败')
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be put in place **before closing the window**: `page.window.destroy()` will
        # [EN] throw CancelledError
        # [EN] and cancel this coroutine, so the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **has never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if REPORT['ok'] else 2)


ft.run(main)
