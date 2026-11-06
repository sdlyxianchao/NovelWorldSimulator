# -*- coding: utf-8 -*-
"""真机验证：帮助面板 + 书斋「故事类型 / 场景名称」（2026-10-05 用户报的三件事）。

三件事：
  ① 运行界面右上角的「❓ 帮助」点了没反应（按钮是 `disabled=True`，面板压根没实现）；
  ② 书斋里的「故事类型」是个**空框**（项目存的是自由文本「玄幻」，
     而选项表的键是「玄幻修仙」，对不上 → `DropdownM2` 什么都不画）；
  ③ 「场景名称」是个写死 "auto" 的输入框，没人读也没人存，
     界面显示的是变量值而不是「自动」。

②③ 正是"控件树里对、屏幕上看不见"那一类：老实现里 `_field.value` 明明是
"玄幻"/"auto"，屏幕上却是空的/变量值。所以判据里**必须有像素**。

跑法：
    .venv\\Scripts\\python.exe tools/verify_help_book.py
产出：
    assets/screenshots/help_book_shuzhai.png / help_book_help.png
    assets/screenshots/help_book_report.json

English:
On-device verification: help panel + study "story type / scene name" (the three things the user
reported on 2026-10-05).
Three things:
  ① Clicking "❓ Help" at the top right of the running UI does nothing (the button is `disabled=True`, and the panel was never implemented);
  ② "Story type" in the study is an **empty box** (the project stores free text "玄幻",
     but the option table's key is "玄幻修仙", which doesn't match → `DropdownM2` draws nothing);
  ③ "Scene name" is an input box hardcoded to "auto"; nobody reads it and nobody saves it,
     and the UI shows a variable value instead of "自动".
②③ are exactly the "right in the widget tree, invisible on screen" category: in the old
implementation `_field.value` was obviously
"玄幻"/"auto", but on screen it was empty / a variable value. So the criterion **must have
pixels**.
How to run:
    .venv\\Scripts\\python.exe tools/verify_help_book.py
Output:
    assets/screenshots/help_book_shuzhai.png / help_book_help.png
    assets/screenshots/help_book_report.json
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
from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from PIL import Image  # noqa: E402

from config import CFG  # noqa: E402
# ⚠⚠ **这一句必须有**（2026-10-11 补）：本脚本会点书斋里的控件、触发 `CFG.save()`，
#   而它设的测试值（`MOCK_LLM=true`）**不能进用户的 `.env`**。
#   2026-10-11 实测踩到：**手工单跑**这一支时（不走回归器、没人给 `NWS_ENV_SINK`）
#   把 `MOCK_LLM=true` 和 `DEFAULT_PROJECTS_DIR=<临时目录>` 写进了用户的真实 `.env`。
#   现在 `config.env_sink_path()` 里还有一道"进程自己认得出是验证脚本"的兜底
#   （见那边的长注释），但**这里也显式调一次** —— 两道是互补的：
#   兜底靠"文件名前缀"，改个名就失效；这一句靠"脚本自己声明"，改不了名。
# [EN] ⚠⚠ **This line is required** (added 2026-10-11): this script clicks controls in the study and
# [EN] triggers `CFG.save()`, and the test values it sets (`MOCK_LLM=true`) **must not enter the user's
# [EN] `.env`**.
# [EN] Measured 2026-10-11: running this one **standalone by hand** (not via the regressor, with nobody
# [EN] providing `NWS_ENV_SINK`) wrote `MOCK_LLM=true` and `DEFAULT_PROJECTS_DIR=<temp dir>` into the
# [EN] user's real `.env`.
# [EN] `config.env_sink_path()` now has a fallback where "the process recognizes it is a verification
# [EN] script" (see the long note there), but **this call is made explicitly here too** -- the two are
# [EN] complementary: the fallback relies on the filename prefix (renaming defeats it), while this line
# [EN] relies on the script declaring it itself (renaming cannot defeat it).
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

from gui.app_flet import (NovelWorldApp, read_manual, genre_options,  # noqa: E402
                          scene_name_label, HELP_TOC_W)
from store.project import Project  # noqa: E402
from i18n import set_lang, t  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# 输入框底色比对话框纸面亮得多（实测 251,248,241 vs 229,224,213），
# 所以**按亮度找**而不是按颜色：按颜色得先把半透明合成算准，而纸面本身还是个
# 渐变，第一版按 `#fffdf7` 硬比就一个框都没量到（boxes=0）。
# [EN] The input box background is much brighter than the dialog paper surface (measured 251,248,241 vs
# [EN] 229,224,213),
# [EN] so **match by brightness** rather than by color: matching by color requires first accurately
# [EN] computing the semi-transparent compositing, and the paper surface itself is a
# [EN] gradient; the first version hard-compared against `#fffdf7` and matched zero boxes (boxes=0).
BOX_LIGHT = 690
ARROW_W = 40          # 框最右侧给下拉箭头留的宽度（那也算深色）
# [EN] The width reserved at the rightmost edge of the box for the dropdown arrow (that also counts as
# [EN] dark)


# 控件树小工具与像素量测都在 `verify_ui_common` 里（多个验证脚本共用一份）：
# [EN] Both the widget tree utility and the pixel measurement live in `verify_ui_common` (shared by
# [EN] multiple verification scripts):
#   VU.walk / VU.text_of / VU.all_texts / VU.labelled_fields / VU.open_dialogs
#   VU.opt_label / VU.measure_input_boxes
walk, text_of = VU.walk, VU.text_of
all_texts, labelled_fields = VU.all_texts, VU.labelled_fields


# ══════════════════════ 主流程 ══════════════════════
# [EN] ══════════════════════ Main flow ══════════════════════
async def main(page: ft.Page):
    # **必须在建界面之前**：换成纯色背景，界面颜色才是确定的（见技能 §6.3）。
    # [EN] **Must be done before building the UI**: switch to a solid background so the UI colors are
    # [EN] deterministic (see skill §6.3).
    VU.patch_flat_background()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_hb_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    items: list = []

    def ok(name: str, cond, detail: str = '') -> bool:
        items.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    async def shot(fname: str) -> Path:
        page.update()
        await asyncio.sleep(0.6)
        p = OUT / fname
        p.write_bytes(await page.take_screenshot())
        return p

    report: dict = {}
    try:
        # ── 夹具：一个项目，类型是**自由文本**（AI 判定给的就是这种值），
        #    设定里放两个地点，供「场景名称」列出候选。
        # [EN] ── Fixture: one project, type is **free text** (this is the kind of value the AI determines),
        # [EN] put two locations in the settings, so "scene name" can list candidates.
        proj = Project.create_new(CFG.projects_dir(), '帮助书斋验证', genre='玄幻')
        proj.settings_dir.mkdir(parents=True, exist_ok=True)
        (proj.settings_dir / '地点.yaml').write_text(
            '- 名称: 临河茶肆\n  说明: 城南临河，入夜点灯。\n'
            '- 名称: 城隍庙\n  说明: 香火冷清。\n', encoding='utf-8')
        (proj.settings_dir / '人物.yaml').write_text(
            '- 姓名: 主角\n  身份: 茶肆掌柜\n', encoding='utf-8')
        app._activate_project(proj)

        # ── ① 选项表：表外的类型值必须能显示出来（下面那条空框的成因）──
        # [EN] ── ① Option table: type values outside the table must be displayable (which is the cause of the
        # [EN] empty box below) ──
        keys_plain = [getattr(o, 'key', None) for o in genre_options()]
        keys_extra = [getattr(o, 'key', None) for o in genre_options('玄幻')]
        ok('项目类型「玄幻」不在标准选项表里（问题的成因）',
           '玄幻' not in keys_plain, str(keys_plain))
        ok('genre_options(extra) 把表外的值补成一项', '玄幻' in keys_extra)
        lab = [VU.opt_label(o) for o in genre_options('玄幻')
               if getattr(o, 'key', None) == '玄幻']
        ok('补的那一项有可读的显示名（玄幻（AI 判定））',
           bool(lab) and 'AI' in lab[0], str(lab))
        ok('auto 不会被当成"表外值"重复补一项', keys_extra.count('auto') == 1)

        # ── ② 书斋对话框 ──
        # [EN] ── ② Study dialog ──
        dlg = app.show_project_settings()
        page.update()
        await asyncio.sleep(0.7)
        ok('书斋对话框真的打开了',
           dlg is not None and bool(getattr(dlg, 'open', False)))
        fields = labelled_fields(dlg)
        ok('按标签找到了书斋里的字段行',
           {'故事类型', '风格来源', '场景名称'} <= set(fields),
           str(sorted(fields)))

        g_field = getattr(fields.get('故事类型'), '_field', None)
        ok('故事类型的控件值 = 项目里存的真值「玄幻」',
           str(getattr(g_field, 'value', '')) == '玄幻',
           str(getattr(g_field, 'value', '')))
        ok('故事类型的下拉里有 value 对应的那一项',
           '玄幻' in [getattr(o, 'key', None)
                      for o in (getattr(g_field, 'options', None) or [])])
        ok('故事类型补的那项在渲染时也有显示文字（走 _norm_options）',
           any('玄幻' in VU.opt_label(o) and VU.opt_label(o) != '玄幻'
               for o in (getattr(g_field, 'options', None) or [])),
           str([VU.opt_label(o) for o in (getattr(g_field, 'options', None) or [])]))

        s_field = getattr(fields.get('场景名称'), '_field', None)
        ok('场景名称是下拉框（不是写死的输入框）',
           s_field is not None and type(s_field).__name__ == 'DropdownM2',
           type(s_field).__name__ if s_field is not None else 'None')
        ok('场景名称的落盘值 = auto',
           str(getattr(s_field, 'value', '')) == 'auto',
           str(getattr(s_field, 'value', '')))
        s_lab = [VU.opt_label(o) for o in (getattr(s_field, 'options', None) or [])]
        ok('场景名称显示人话「自动…」而不是变量值',
           bool(s_lab) and '自动' in s_lab[0] and s_lab[0].strip() != 'auto',
           str(s_lab))
        ok('场景名称把设定里的地点列成了候选',
           any('临河茶肆' in x for x in s_lab) and any('城隍庙' in x for x in s_lab),
           str(s_lab))
        ok('scene_name_label(auto) 是人话', '自动' in scene_name_label('auto'),
           scene_name_label('auto'))

        png = await shot('help_book_shuzhai.png')
        # ★★★ 2026-10-31：换尺 —— 亮度阈值量不了提亮后的宣纸（详见
        #   `VU.measure_boxes_by_border` 头注释：纸面渐变 713~754 与输入框 755
        #   区间重叠，690 的老阈值把整页量成一个巨框，跟字段宽窄无关）。
        #   框改按**边框色带**找。
        #   ⚠ 旧写法还按**位置**取 boxes[0..2] 当作 故事类型/风格来源/场景名称 ——
        #     那是布局一变就断的锚（「运行」页一加就断）。改成按**带字的框数**；
        #     逐格的断言在控件层（上面：值 / 选项表 / 显示名），那里不怕布局变。
        # [EN] ★★★ 2026-10-31: switched measures -- brightness thresholds cannot separate
        #   boxes from the brightened paper (see VU.measure_boxes_by_border's header).
        #   Boxes are found by their **border colour band**. The old code also anchored
        #   boxes[0..2] **by position** (an anchor that dies with any layout change -- the new
        #   运行 tab broke it); count inked boxes instead. Per-field assertions live above at
        #   the control level, which is layout-independent.
        boxes = VU.measure_boxes_by_border(png)
        report['boxes_shuzhai'] = boxes
        _inked = [b for b in boxes if b['ink_w'] > 20]
        ok('截图里量到了书斋的字段框（≥4 个）', len(boxes) >= 4,
           f'框 {len(boxes)} 个 · 带字 {len(_inked)} 个')
        # ⚠ 关键像素判据：老实现里下拉格**只有右边的箭头**（ink 宽度 0）。
        # [EN] ⚠ Key pixel criterion: in the old implementation this cell had **only the right
        # [EN] arrow** (ink width 0).
        ok('像素：字段框大多带字（空框病回来了带字的会骤减）',
           len(_inked) >= 4, f'带字 {len(_inked)} / {len(boxes)}'
           + (f' · 空框 y={[(b["y0"]) for b in boxes if b["ink_w"] == 0]}'
              if len(_inked) < len(boxes) else ''))

        # ── ③ 保存：真落盘（.nwsproj）──
        # [EN] ── ③ Save: actually persist to disk (.nwsproj) ──
        dlg.actions[0].on_click(None)
        page.update()
        await asyncio.sleep(0.5)
        back = Project.from_nwsproj(proj.nwsproj_path)
        ok('保存后 .nwsproj 里有 场景名称=auto',
           '场景名称=auto' in proj.nwsproj_path.read_text(encoding='utf-8'))
        ok('读回的项目 scene_name = auto', back.scene_name == 'auto', back.scene_name)

        dlg2 = app.show_project_settings()
        page.update()
        await asyncio.sleep(0.5)
        getattr(labelled_fields(dlg2)['场景名称'], '_field').value = '临河茶肆'
        dlg2.actions[0].on_click(None)
        page.update()
        await asyncio.sleep(0.5)
        back2 = Project.from_nwsproj(proj.nwsproj_path)
        ok('改选地点后 .nwsproj 存的是地点名', back2.scene_name == '临河茶肆',
           back2.scene_name)

        # ── ④ 场景名真的进到世界里（不是只躺在文件里）──
        # [EN] ── ④ The scene name really gets into the world (not just lying in the file) ──
        from sim.setup import load_settings, build_world
        settings = load_settings(proj.settings_dir)
        w1 = build_world(settings, scene='城隍庙')
        ok('build_world(scene=地点) 用项目里的地点开场', w1.scene == '城隍庙', w1.scene)
        w2 = build_world(settings, scene='auto')
        ok('scene=auto 时回落到设定里的第一个地点', w2.scene == '临河茶肆', w2.scene)

        # ── ⑤ 帮助面板 ──
        # [EN] ── ⑤ Help panel ──
        intro, secs = read_manual(APP_DIR / '使用说明.md')
        ok('读得到《使用说明》并按二级标题切出章节', len(secs) >= 10, str(len(secs)))
        ok('章节标题是人读的', bool(secs and secs[0][0]), secs[0][0] if secs else '')
        ok('说明书章节正文够长（不是空壳）',
           bool(secs) and max(len(b) for _t, b in secs) > 1000,
           str(max((len(b) for _t, b in secs), default=0)))
        empty_intro, empty_secs = read_manual(tmp / '不存在.md')
        ok('找不到说明书时返回空（调用方给提示，不弹空白框）',
           empty_intro == '' and empty_secs == [])
        set_lang('en')
        ok('英文界面读 User_Manual.md 也有章节',
           len(read_manual(APP_DIR / 'User_Manual.md')[1]) >= 10)
        set_lang('zh')

        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.0)
        btns = [c for c in walk(app.page)
                if type(c).__name__ == 'FilledButton' and '帮助' in text_of(c)]
        ok('运行界面右上角的「帮助」按钮存在', bool(btns), str(len(btns)))
        if btns:
            ok('「帮助」不是禁用状态', not bool(getattr(btns[0], 'disabled', False)))
            ok('「帮助」接了回调', callable(getattr(btns[0], 'on_click', None)))

        btns[0].on_click(None)
        page.update()
        await asyncio.sleep(0.9)
        hd = [d for d in VU.open_dialogs(page) if any('帮 助' in x for x in all_texts(d))]
        ok('点了「帮助」真的弹出帮助框', bool(hd), str(len(VU.open_dialogs(page))))
        hdlg = hd[-1] if hd else None
        ok('帮助框处于打开状态', hdlg is not None)

        texts = all_texts(hdlg) if hdlg else []
        mds = [c for c in walk(hdlg) if isinstance(c, ft.Markdown)] if hdlg else []
        ok('帮助框里渲染了说明书正文', bool(mds) and len(mds[0].value or '') > 100,
           str(len(mds[0].value or '') if mds else 0))
        # ⚠ **别按"写死的宽度"找目录行**（原来是 `c.width == HELP_TOC_W - 14`）：
        #   目录行改由 `ListView` 紧约束撑满之后，它的 `width` 属性是 `None`，
        #   按宽度找**恒 0 条** —— 那是判据自己的前提错了，不是产品坏了
        #   （2026-10-06 修）。改成认**构造特征**（照抄 `_rebuild()` 里那几个属性）。
        #   ⚠ 光用 `border_radius == 4` **不够**：帮助页里别的容器也有 4，
        #     会把非目录控件算进来 —— 于是 `tocs[1]` 点了个不相干的东西，
        #     「点目录能切章」就假红。`padding(6,4,6,4)` 一起判才准。
        # [EN] ⚠ **Don't look for the TOC row by "hardcoded width"** (originally `c.width == HELP_TOC_W - 14`):
        # [EN] after the TOC row is constrained to fill by `ListView`, its `width` property is `None`,
        # [EN] searching by width yields **always 0 rows** —— that's the criterion's own premise being wrong,
        # [EN] not the product being broken
        # [EN] (fixed 2026-10-06). Change to recognizing **structural features** (copy those properties from
        # [EN] `_rebuild()`).
        # [EN] ⚠ Using only `border_radius == 4` is **not enough**: other containers in the help page also have
        # [EN] 4,
        # [EN] which would count non-TOC controls —— so `tocs[1]` clicks something irrelevant,
        # [EN] "clicking the TOC switches chapters" gives a false red. Only judging together with
        # [EN] `padding(6,4,6,4)` is accurate.
        def _is_toc(c):
            if not (isinstance(c, ft.Container) and c.on_click is not None
                    and c.border_radius == 4):
                return False
            pad = getattr(c, 'padding', None)
            return (getattr(pad, 'left', None) == 6
                    and getattr(pad, 'top', None) == 4)
        tocs = [c for c in walk(hdlg) if _is_toc(c)] if hdlg else []
        ok('左栏目录项 ≥ 10 条（说明书章节）', len(tocs) >= 10, str(len(tocs)))
        if len(tocs) >= 2 and mds:
            first_md = mds[0].value
            tocs[1].on_click(None)
            page.update()
            await asyncio.sleep(0.5)
            mds2 = [c for c in walk(hdlg) if isinstance(c, ft.Markdown)]
            ok('点目录能切章（正文换成那一节）',
               bool(mds2) and mds2[0].value != first_md
               and mds2[0].value == (secs[0][1] if secs else ''),
               f'len {len(first_md)} → {len(mds2[0].value) if mds2 else 0}')

        hpng = await shot('help_book_help.png')
        h_im = Image.open(hpng).convert('RGB')
        hp = h_im.load()
        dark = sum(1 for y in range(0, h_im.size[1], 3)
                   for x in range(0, h_im.size[0], 3) if sum(hp[x, y]) < 430)
        ok('像素：帮助框里有大量文字墨迹', dark > 400, str(dark))
        # ★ 2026-10-31：「左栏目录 + 右栏正文两块纸面」改按**墨迹列**量。
        #   亮度尺废了（提亮后的纸面 713~754 全高于老阈值 690，量出来是整窗一个巨框，
        #   旧的 `measure_input_boxes(hpng, min_run=60)` 长期红）。墨迹跟配色无关：
        #   抠掉窗口深色边框后，帮助页必须聚出 **≥2 条有内容的竖条**（左目录、右正文）。
        # [EN] ★ 2026-10-31: "left TOC + right body" is now measured via **ink columns**
        #   (brightness is dead: the brightened paper is all above the old threshold, so the
        #   old measure returned one window-sized giant box and stayed red). Ink is palette
        #   independent: with the window frame trimmed, the help page must cluster into
        #   **>=2 content strips** (left TOC, right body).
        _cols = VU.measure_ink_columns(hpng)
        report['ink_columns_help'] = _cols
        ok('像素：帮助页量出左右两栏内容（目录 + 正文）',
           len(_cols) >= 2, f'墨迹列段 {len(_cols)} 条 {list(_cols)[:4]}')
        report['help_texts'] = texts[:10]

        # ── ⑥ 运行窗口底部现在是 **AI 对话输入框**（协调引擎入口），不再是命令框 ──
        # [EN] ── ⑥ The run window's bottom is now an **AI conversation input box** (Coordinator entry),
        # [EN] no longer a command box ──
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.4)
        cmd = app._ui_run.get('cmd_input')
        ok('运行界面的 AI 输入框接了 on_submit（接的是协调引擎，不是旧命令）',
           callable(getattr(cmd, 'on_submit', None)))
        ok('AI 输入框的提示语不再写"输入命令"（已是自然语言下指令）',
           '输入命令' not in (getattr(cmd, 'hint_text', '') or ''),
           getattr(cmd, 'hint_text', '') or '')
        ok('旧命令框 run_command 已移除（输入框改为 AI 对话）',
           not hasattr(app, 'run_command'))

        # ── 收尾 ──
        # [EN] ── Wrap-up ──
        set_lang('en')
        en_label = t('自动（按设定里的地点推断）')
        set_lang('zh')
        ok('英文界面下新文案有译文（不是原样返回）',
           en_label != '自动（按设定里的地点推断）', en_label)

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'help_book_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for it in items:
            print(f"{'OK  ' if it['ok'] else 'FAIL'}  {it['name']}"
                  + (f"   [{it['detail']}]" if it['detail'] else ''))
        print(f"\n帮助/书斋验证：{report['n_ok']}/{report['n_all']}")
        if report.get('fatal'):
            print(report['fatal'])
        try:
            VU.safe_rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] cancel this coroutine, and the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **never runs** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    ft.run(main)
