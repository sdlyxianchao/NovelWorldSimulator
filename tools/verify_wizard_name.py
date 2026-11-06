# -*- coding: utf-8 -*-
"""验证：开卷向导的「项目名称」默认用**所选文件夹的名字**填充，且不覆盖用户改过的。

用户 2026-10-06：「开卷的时候，项目名字默认用我打开的文件夹名字填充，
用户觉得不对再自己输入。」

## 这条最容易做错的地方不是"填"，是"**什么时候不填**"

"默认填一次"很简单，难的是**别把用户自己打的名字冲掉**。会出事的场景很具体：
用户在第 2 步把名字改成「我的新书」，发现文件夹选错了 → 回第 1 步换一个文件夹 →
如果实现是"每次路径变就填"，**他改好的名字当场被文件夹名覆盖**，
而且多半要走到最后一步才发现。

所以判据里**一半的条目在测"不覆盖"**，而且是在真机上走"改名字 → 回退 → 换文件夹"这条路径。

## 检查什么

A 纯逻辑（表驱动，零窗口）
  · `_folder_basename`：Windows 反斜杠 / 正斜杠 / 带尾斜杠 / POSIX / 盘根 / 空串
  · `_autofill_project_name` 的四种情形（空+空 / 空+有 / 等于上次自动值 / 别的值）
B 真机
  · 开向导 → 选文件夹 → **名字被填上**（状态 + 输入框的值都对）
  · **屏幕上真的画出了这个名字**：填着 / 清空各拍一张，做差只该是**一条窄横带**，
    且清空之后那一带墨迹明显变少（只在控件树里对、屏幕上空着，是这一行最容易骗过判据的地方）
  · 用户改成别的名字 → 回第 1 步换文件夹 → **名字一个字都没变**
  · 用户**主动清空**名字 → 再换文件夹 → 仍然不填（他说了不要）
  · 选了盘根之类的"取不出名字"的路径 → 不留半个像名字的东西

跑法：
    .venv\\Scripts\\python.exe tools/verify_wizard_name.py
产出：
    assets/screenshots/wizard_name_report.json
    assets/screenshots/wizard_name_1_filled.png
    assets/screenshots/wizard_name_2_cleared.png

English:
Verify: the book-opening wizard's "Project Name" defaults to the **name of the selected
folder**, and does not overwrite user edits.
User 2026-10-06: "When opening a book, the project name should default to the name of the folder
I opened,
and if the user thinks it's wrong they can type it themselves."
## The easiest thing to get wrong here isn't "filling", it's "**when not to fill**"
"Fill once by default" is simple; the hard part is **not wiping the name the user typed
themselves**. The failure scenarios are very concrete:
The user renames it to "我的新书" in step 2, realizes the folder is wrong → goes back to step 1 and
picks another folder →
if the implementation is "fill whenever the path changes", **his edited name is immediately
overwritten by the folder name**,
and he probably won't notice until the last step.
So **half the checks are testing "not overwriting"**, and on the real machine they follow the
path "rename → go back → switch folder".
## What to check
A pure logic (table-driven, zero windows)
  · `_folder_basename`: Windows backslash / forward slash / trailing slash / POSIX / drive root / empty string
  · `_autofill_project_name`'s four cases (empty+empty / empty+has / equals last auto value / other value)
B real machine
  · Open wizard → select folder → **name gets filled in** (both state and input box value are correct)
  · **The name is really drawn on screen**: take one shot filled and one cleared; the diff should only be **a narrow horizontal band**,
    and after clearing that band's ink noticeably decreases (matching only in the widget tree while the screen is blank is where this line most easily fools the check)
  · User changes to another name → back to step 1, switch folder → **not a single character of the name changes**
  · User **actively clears** the name → switch folder again → still not filled (he said he doesn't want it)
  · Selecting a path like a drive root where "no name can be obtained" → not half a name-like thing left behind
How to run:
    .venv\\Scripts\\python.exe tools/verify_wizard_name.py
Output:
    assets/screenshots/wizard_name_report.json
    assets/screenshots/wizard_name_1_filled.png
    assets/screenshots/wizard_name_2_cleared.png
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
from PIL import Image, ImageChops  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang, t  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

_ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    _ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


class _Ev:
    """最小事件替身：`_on_wizard_name_changed(e)` 只用到 `e.control.value`。
        English:
    Minimal event stand-in: `_on_wizard_name_changed(e)` only uses `e.control.value`.
    """

    def __init__(self, value):
        self.control = type('C', (), {'value': value})()


# ══════════════════════════════════════════════════════════════════════
#  A —— 纯逻辑
# [EN] A —— pure logic
# ══════════════════════════════════════════════════════════════════════
def test_logic(report: dict) -> None:
    base = NovelWorldApp._folder_basename

    cases = [
        (r'E:\我的小说\悬疑故事', '悬疑故事', 'Windows 反斜杠'),
        ('E:/我的小说/悬疑故事', '悬疑故事', '正斜杠'),
        ('E:/我的小说/悬疑故事/', '悬疑故事', '带尾斜杠（选文件夹器常带）'),
        ('/home/me/novels/mystery', 'mystery', 'POSIX（三平台都要能跑）'),
        (r'\\server\share\书稿', '书稿', 'UNC 路径'),
        ('  E:/a/我的新书  ', '我的新书', '首尾空格要去掉'),
        # ★ 取不出名字的：必须返回空，调用方才知道"别填"
        # [EN] ★ Unobtainable name: must return empty, so the caller knows "don't fill it"
        ('E:/', '', '盘根（取出来是空的）'),
        (r'E:\\', '', '盘根（反斜杠写法）'),
        ('', '', '空串'),
        ('   ', '', '纯空格'),
    ]
    bad = [(p, base(p), want, why) for p, want, why in cases if base(p) != want]
    report['basename'] = {p: base(p) for p, _w, _y in cases}
    ok('A：★ `_folder_basename` 各种路径都取对（含盘根/UNC/POSIX）',
       not bad, str(bad[:3]))

    # ── 自动填的四种情形（表驱动）──
    # [EN] ── The four auto-fill cases (table-driven) ──
    def run(path, name, auto):
        app = NovelWorldApp()
        app._wizard_name = name
        app._wizard_name_auto = auto
        app._autofill_project_name(path)
        return app

    a = run(r'E:\书稿\我的新书', '', '')
    ok('A：第一次（都空）→ **填**成文件夹名', a._wizard_name == '我的新书', a._wizard_name)

    a = run(r'E:\书稿\我的新书', '用户起的名', '')
    ok('A：★ 用户自己打了名字 → **一个字都不动**',
       a._wizard_name == '用户起的名', a._wizard_name)

    a = run(r'E:\书稿\另一个', '我的新书', '我的新书')
    ok('A：★ 还是上次自动填的（他没碰）→ **换成新文件夹的名字**',
       a._wizard_name == '另一个', a._wizard_name)

    a = run(r'E:\书稿\另一个', '', '我的新书')
    ok('A：★ 用户**主动清空**过 → 不再塞回去（他说了不要）',
       a._wizard_name == '', repr(a._wizard_name))

    a = run('E:/', '', '')
    ok('A：选到取不出名字的路径（盘根）→ 什么都不填',
       a._wizard_name == '', repr(a._wizard_name))

    a = run(r'E:\书稿\我的新书', '我的新书', '我的新书')
    ok('A：值已经对了 → 保持不变（且不白刷控件）',
       a._wizard_name == '我的新书' and a._wizard_name_auto == '我的新书', a._wizard_name)


# ══════════════════════════════════════════════════════════════════════
#  B —— 真机
# [EN] B —— real machine
# ══════════════════════════════════════════════════════════════════════
def make_fixture(root: Path) -> Path:
    """文件夹名就是断言要用的那个名字，别改。
        English:
    The folder name is exactly the name used in assertions, don't change it.
    """
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n\n起：雨夜来客打破平静。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text('# 第1章\n\n雨脚敲着檐瓦。\n' * 8, encoding='utf-8')
    return src


def ink_px(png: Path, box) -> int:
    """某个区域里"墨迹"像素数（比纸白明显深的算）。
        English:
    The count of "ink" pixels in a region (anything noticeably darker than paper white).
    """
    im = Image.open(png).convert('RGB')
    x0, y0, x1, y1 = [int(v) for v in box]
    x1, y1 = min(x1, im.width), min(y1, im.height)
    px = im.load()
    return sum(1 for y in range(y0, y1) for x in range(x0, x1)
               if sum(px[x, y]) < 620)


async def test_gui(page: ft.Page, report: dict) -> None:
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.window.width = 1260
    page.window.height = 860
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_wname_'))
    try:
        VU.isolate_projects_dir(tmp / 'Projects')
        src = make_fixture(tmp)
        other = tmp / '另一个文件夹'
        other.mkdir(parents=True, exist_ok=True)

        async def shot(name: str) -> Path:
            page.update()
            await asyncio.sleep(0.4)
            png = OUT / name
            png.write_bytes(await page.take_screenshot())
            return png

        dlg = app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.8)

        ok('B：向导打开了，且第 2 步的输入框句柄已拿到',
           dlg is not None and getattr(app, '_wizard_name_field', None) is not None,
           str(type(getattr(app, '_wizard_name_field', None))))

        # ── 走真实入口：选文件夹 ──
        # [EN] ── Go through the real entry point: select folder ──
        app._wizard_path = str(src)
        app._on_wizard_path_changed(None)
        page.update()
        fld = app._wizard_name_field._field
        report['after_pick'] = {'state': app._wizard_name, 'field': fld.value}
        ok('B：★ 选完文件夹，项目名称**自动填成文件夹名**',
           app._wizard_name == '雨夜来客', app._wizard_name)
        ok('B：★ 输入框里的值也跟着变了（用户一进来就看到）',
           fld.value == '雨夜来客', repr(fld.value))

        # ── 进第 2 步（走真实的「下一步」按钮，让 `on_enter` 也跑一遍）──
        # [EN] ── Enter step 2 (go through the real "Next" button so `on_enter` also runs) ──
        next_btn = dlg.actions[1]
        ok('B：选完文件夹后「下一步」可点', not next_btn.disabled, str(next_btn.disabled))
        next_btn.on_click(None)
        page.update()
        await asyncio.sleep(0.5)
        report['step2_field'] = app._wizard_name_field._field.value
        ok('B：进到第 2 步后，输入框里仍然是那个名字（`on_enter` 没把它清掉）',
           app._wizard_name_field._field.value == '雨夜来客',
           repr(app._wizard_name_field._field.value))
        png_filled = await shot('wizard_name_1_filled.png')

        # ── ★ 屏幕上真的画出来了？填着 / 清空 / 换个长名字，各拍一张做差 ──
        #    ⚠ "控件树里对 ≠ 屏幕上看得见"：输入框的 value 在树里好好的，
        #      但要是没真的画出来，用户看到的还是个空框。所以这里必须量像素。
        # [EN] ── ★ Is it really drawn on screen? Filled / cleared / a longer name, take one shot each and diff
        # [EN] ──
        # [EN] ⚠ "Matching in the widget tree ≠ visible on screen": the input box's value is fine in the tree,
        # [EN] but if it isn't actually drawn, the user still sees an empty box. So here we must measure
        # [EN] pixels.
        #
        #    ⚠ **两个坑（都踩过）**：
        #    ① 别用 `VU.dialog_bbox()` 去判"差异在不在对话框里" —— 向导是开在
        #       **开始界面（有背景图）之上的**，那支探针找的是描金边框，
        #       在这种半透明叠图上返回 `None`（实测），判据会假红。
        #    ② 别去猜"名字行"的坐标。**用长度对齐来证明"画的就是这串字"**：
        #       换一个明显更长的名字再拍一张，差异框必须跟着变宽 ——
        #       这是坐标无关的判据，比"在某个 y 区间内"结实得多。
        # [EN] ⚠ **Two pitfalls (both hit before)**:
        # [EN] ① Don't use `VU.dialog_bbox()` to decide "is the diff inside the dialog" —— the wizard opens
        # [EN] **on top of the start screen (which has a background image)**, and that probe looks for the
        # [EN] gilded border,
        # [EN] which on this semi-transparent overlay returns `None` (measured), so the check goes false-red.
        # [EN] ② Don't guess the coordinates of the "name row". **Use length alignment to prove "what's drawn
        # [EN] is this string"**:
        # [EN] switch to a noticeably longer name and take another shot; the diff box must widen accordingly ——
        # [EN] this is a coordinate-independent check, far more robust than "within some y interval".
        def type_name(v: str) -> None:
            """像真人一样改输入框：**先动控件的值，再发 on_change**。

            ⚠ 只调 `_on_wizard_name_changed()` 是**假的**：真实交互里控件的 value
            早就是用户打的字了，handler 只负责记状态。第一版就是这么写的，
            于是"输入框里也没被改掉"那条假红（字段值还停在我上一步清空的状态）。
            
                        English:
            Change the input box like a real person: **first change the widget's value, then fire
            on_change**.
                        ⚠ Calling only `_on_wizard_name_changed()` is **fake**: in real interaction the widget's value
                        is already what the user typed; the handler only records state. The first version was written this way,
                        so that false red for "the input box wasn't changed either" (the field value was still in the state I cleared in the previous step).
            """
            app._wizard_name_field._field.value = v
            app._on_wizard_name_changed(_Ev(v))

        app._wizard_name = ''
        app._wizard_name_field._field.value = ''
        page.update()
        png_cleared = await shot('wizard_name_2_cleared.png')

        type_name('我的新书')                       # 4 个字
        # [EN] 4 chars
        page.update()
        png_short = await shot('wizard_name_3_short.png')

        type_name('这是一个明显更长的项目名字')      # 12 个字
        # [EN] 12 chars
        page.update()
        png_long = await shot('wizard_name_4_long.png')

        def diff_bbox(a: Path, b: Path):
            d = ImageChops.difference(Image.open(a).convert('RGB'),
                                      Image.open(b).convert('RGB')).convert('L')
            return d.point(lambda v: 255 if v > 24 else 0).getbbox()

        bb_short = diff_bbox(png_cleared, png_short)
        bb_long = diff_bbox(png_cleared, png_long)
        report['name_diff_bbox'] = {'short': list(bb_short) if bb_short else None,
                                    'long': list(bb_long) if bb_long else None}
        if bb_short and bb_long:
            w_s = bb_short[2] - bb_short[0]
            w_l = bb_long[2] - bb_long[0]
            h_s = bb_short[3] - bb_short[1]
            h_l = bb_long[3] - bb_long[1]
            report['ink'] = {'cleared': ink_px(png_cleared, bb_short),
                             'short': ink_px(png_short, bb_short)}
            report['widths'] = {'short': w_s, 'long': w_l}
            ok('B：★ 名字**真的画在屏幕上**（填着与清空后那一带像素真的有差异）',
               w_s >= 40 and ink_px(png_short, bb_short) > 0,
               f'4 字差异框 {bb_short} 宽 {w_s}')
            ok('B：★ 差异只在**一行**里（是输入框里那串字，不是别处挪动）',
               h_s <= 40 and h_l <= 40, f'高 {h_s} / {h_l}')
            ok('B：★ 换成更长的名字，差异框**跟着变宽**'
               '（证明画的确实是"名字"这串字，而不是碰巧有一块在动）',
               w_l > w_s * 1.6, f'4 字 {w_s}px → 12 字 {w_l}px')
            ok('B：★ 清空之后那一带的墨迹归零（证明字确实画在那里）',
               ink_px(png_cleared, bb_short) == 0
               and ink_px(png_short, bb_short) > 40,
               f'{ink_px(png_cleared, bb_short)} → {ink_px(png_short, bb_short)}')
        else:
            ok('B：★ 名字真的画在屏幕上', False,
               f'差异框 短={bb_short} 长={bb_long} —— 字没被画出来？')

        # ── ★ 用户改过的名字不许被覆盖（这条是本次改动的重点）──
        type_name('我的新书')          # 用户自己改名（走真实入口）
        # [EN] ── ★ A user-modified name must not be overwritten (this is the focus of this change) ──
        # [EN] User renames it themselves (through the real entry point)
        page.update()
        app._wizard_path = str(other)          # 回头换一个文件夹
        # [EN] Go back and switch to another folder
        app._on_wizard_path_changed(None)
        page.update()
        report['after_user_edit'] = {'state': app._wizard_name,
                                     'field': app._wizard_name_field._field.value}
        ok('B：★★ 用户改成「我的新书」后换文件夹，名字**一个字都没变**'
           '（最容易破坏的那一半）',
           app._wizard_name == '我的新书', app._wizard_name)
        ok('B：★ 输入框里也没有被改掉（所见即所存）',
           app._wizard_name_field._field.value == '我的新书',
           repr(app._wizard_name_field._field.value))

        # 回到第 2 步再确认一次（来回切步骤也不许把它冲掉）
        dlg.actions[0].on_click(None)          # 上一步
        # [EN] Return to step 2 and confirm once more (switching steps back and forth must not wipe it)
        # [EN] Previous
        page.update()
        await asyncio.sleep(0.3)
        dlg.actions[1].on_click(None)          # 下一步
        # [EN] Next
        page.update()
        await asyncio.sleep(0.4)
        ok('B：来回切一次步骤，用户的名字依然在',
           app._wizard_name_field._field.value == '我的新书',
           repr(app._wizard_name_field._field.value))

        # ── `on_enter` 兜底：状态与控件不一致时，进出一次第 2 步必须自动对上 ──
        #    这个兜底存在的理由就是"屏幕上显示的"和"存下去用的"必须是同一个值，
        #    否则用户看到 A、开出来的项目叫 B。故意把两者弄成不一致来验它。
        app._wizard_name = '从别处改的名字'                 # 只动状态
        app._wizard_name_field._field.value = '这是过期的显示'   # 只动控件
        # [EN] ── `on_enter` fallback: when state and widget disagree, entering/leaving step 2 must
        # [EN] auto-reconcile ──
        # [EN] The reason this fallback exists is that "what's shown on screen" and "what's stored" must be the
        # [EN] same value,
        # [EN] otherwise the user sees A but the project opened is named B. Deliberately make the two
        # [EN] inconsistent to verify it.
        # [EN] Change state only
        # [EN] Change widget only
        dlg.actions[0].on_click(None)
        page.update()
        await asyncio.sleep(0.3)
        dlg.actions[1].on_click(None)
        page.update()
        await asyncio.sleep(0.4)
        report['on_enter_sync'] = app._wizard_name_field._field.value
        ok('B：★ 状态与控件不一致时，进出第 2 步会把输入框**对上状态**'
           '（所见即所存）',
           app._wizard_name_field._field.value == '从别处改的名字',
           repr(app._wizard_name_field._field.value))

        # ── 用户主动清空 → 不再自动填 ──
        type_name('')                # 用户把名字清空
        # [EN] ── User actively clears → no more auto-fill ──
        # [EN] User clears the name
        app._wizard_path = str(src)
        app._on_wizard_path_changed(None)
        page.update()
        ok('B：★ 用户主动清空后再换文件夹，**仍然不填**（他说了不要）',
           app._wizard_name == '', repr(app._wizard_name))
        report['ok'] = all(i['ok'] for i in _ITEMS)

        # 收尾：关掉向导（不真跑摄取）
        # [EN] Wrap up: close the wizard (don't actually run ingestion)
        try:
            page.pop_dialog()
        except Exception:                                         # noqa: BLE001
            pass
        page.update()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def main(page: ft.Page) -> None:
    report: dict = {}
    try:
        test_logic(report)
        await test_gui(page, report)
        report['ok'] = all(i['ok'] for i in _ITEMS)
    except BaseException:                                          # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()[-1800:]
        report['ok'] = False
        print(report['fatal'])
    finally:
        report['items'] = _ITEMS
        (OUT / 'wizard_name_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        n_ok = sum(1 for i in _ITEMS if i['ok'])
        print(f'向导项目名验证：{n_ok}/{len(_ITEMS)}')
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
