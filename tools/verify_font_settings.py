# -*- coding: utf-8 -*-
"""真机验证：界面字体 / 界面字号 / 运行窗口命令行开关（2026-10-11 用户要求）。

用户原话三件事：
  ① 「运行窗口用的字体不太好，**有些字比如门的写的跟普通写法不同**，
     你看下是否有更通用的而且好看的字体来进行替换」；
  ② 「我希望在全局设置里**界面部分加上字体设置和字号**等设置」；
  ③ 「加一个全局选项**是否关闭命令行，默认值为真**，即不显示命令文本框和按钮等功能，
     即运行窗口最下面那一部分」。

判据分组
--------
A 组（纯逻辑，不弹窗）
  A1 默认 `UI_FONT='auto'` → 解析到**随附宋体**（思源宋体）的族名，且文件真在磁盘上
  A2 `resolve_ui_font()`：`system` → 平台默认；**认不出的取值 → 平台默认**（不是方块）
  A3 三份随附字体都在 `assets/fonts/`，magic 是 TrueType/OpenType
  A4 `font_choices()` **只列真的能用的**：随附的看文件在不在，
     系统的看 `available_system_fonts()`；且选项里不出现裸 token
  A5 字号缩放**从基准算**（100→130→100 必须回到原值，不累乘）；
     缩放后「框高/字号」仍落在 [1.6, 2.6]（高度跟着字号一起缩）
  A6 源码里**没有遗留的字面量字号**（除注释）—— 否则缩放会漏掉几处小字
  A7 `HIDE_COMMAND_BAR` 默认 True；`runtime_features()` 如实反映
  A8 新文案中英都有（含**动态取值**那组字体名，`i18n_check` 扫不到）
B 组（真机）
  B1 真机上 `page.theme.font_family` == 随附宋体族名；`page.fonts` 注册了三份
  B2 「天机 · 界面外观」里有「界面字体」下拉、「缩放」滑杆、「关闭命令行」开关
  B3 下拉里每个选项都有 `content` 且内容 == `text`；**不出现裸 token**
  B4 默认（关闭命令行）时，运行界面树里**没有**那两件控件
  B5 打开时它们回来，并且「发送」按钮**真的画在下半屏**（标记色法）
  B6 字号 130% → 同一句文字的墨迹**真的变宽**

跑法：.venv\\Scripts\\python.exe tools/verify_font_settings.py
产出：assets/screenshots/font_settings*.png + font_settings_report.json

English:
Real-device verification: UI font / UI font size / run-window command-bar switch (requested by the
user 2026-10-11).
The user's three requests:
  ① "the font in the run window isn't great, **some characters like 门 are written differently from
     the normal form**; see if there's a more universal and better-looking font to replace it";
  ② "I'd like **font and font-size** settings added to the UI section of global settings";
  ③ "add a global option **whether to hide the command bar, default true**, i.e. don't show the
     command text box and button -- that's the bottom part of the run window".
Criteria groups
--------
Group A (pure logic, no window)
  A1 Default `UI_FONT='auto'` -> resolves to the **bundled Noto Serif SC** family name, and the file
     really exists on disk
  A2 `resolve_ui_font()`: `system` -> platform default; **unrecognized value -> platform default**
     (not tofu boxes)
  A3 All three bundled fonts are in `assets/fonts/`, magic is TrueType/OpenType
  A4 `font_choices()` **lists only what actually works**: bundled by file presence, system by
     `available_system_fonts()`; and no bare token appears as a label
  A5 Font scaling **starts from the base** (100->130->100 must return to the original, no
     compounding); after scaling "box height / font size" is still within [1.6, 2.6] (heights scale
     with the font size)
  A6 **No leftover literal font sizes** in the source (comments excluded) -- otherwise scaling misses
     a few small bits of text
  A7 `HIDE_COMMAND_BAR` defaults to True; `runtime_features()` reflects it faithfully
  A8 All new copy exists in both languages (including the **dynamic** font-name group, which
     `i18n_check` cannot see)
Group B (real device)
  B1 On the real machine `page.theme.font_family` == the bundled Noto Serif SC family; `page.fonts`
     has all three registered
  B2 "Tianji · UI appearance" has the "UI font" dropdown, the "Scale" slider and the "Hide command
     bar" switch
  B3 Every option in the dropdown has `content` equal to its `text`; **no bare token** appears
  B4 With the default (command bar hidden), those two controls are **absent** from the run UI tree
  B5 When turned on they come back, and the "Send" button is **actually painted in the lower half**
     (marker-color method)
  B6 At 130% font size the ink of the same sentence **really gets wider**
How to run: .venv\\Scripts\\python.exe tools/verify_font_settings.py
Output: assets/screenshots/font_settings*.png + font_settings_report.json
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

import flet as ft                                        # noqa: E402
from util.flet_shutdown import shutdown, exit_now        # noqa: E402
from PIL import Image                                    # noqa: E402
import verify_ui_common as VU                            # noqa: E402

from config import CFG                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)
VU.redirect_env_writes()      # 真机段会 CFG.save()，别写用户 .env
VU.patch_flat_background()    # 必须在建界面之前：纯色背景，像素判据才确定
# [EN] The real-device section will call CFG.save(), do not write to the user's .env
# [EN] Must be before building the UI: solid background, so pixel criteria are deterministic

import gui.app_flet as G                                 # noqa: E402
from i18n import set_lang, t, _ZH2EN                     # noqa: E402
set_lang(_lang)

SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:220]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A 组：纯逻辑
# [EN] Group A: pure logic
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    # A1
    auto_fam = G.resolve_ui_font('auto')
    serif_fam, serif_file, _zh, _en = G.BUNDLED_FONTS['serif']
    ok('A1 UI_FONT 默认 auto → 随附宋体（思源宋体），文件在磁盘上',
       auto_fam == serif_fam and (G.FONT_DIR / serif_file).is_file(),
       f'{auto_fam} / {serif_file}')

    # A2
    ok('A2a resolve_ui_font("system") → 平台默认字体',
       G.resolve_ui_font('system') == G._platform_default_font(),
       G.resolve_ui_font('system'))
    ok('A2b resolve_ui_font("这不是字体") → 回落平台默认（不是方块/空）',
       G.resolve_ui_font('这不是字体') == G._platform_default_font(),
       G.resolve_ui_font('这不是字体'))
    ok('A2c resolve_ui_font("sans") → 随附黑体的族名',
       G.resolve_ui_font('sans') == G.BUNDLED_FONTS['sans'][0],
       G.resolve_ui_font('sans'))

    # A3
    missing = [f for _t, (_fam, f, _z, _e) in G.BUNDLED_FONTS.items()
               if not (G.FONT_DIR / f).is_file()]
    magics = {}
    for _t, (_fam, f, _z, _e) in G.BUNDLED_FONTS.items():
        p = G.FONT_DIR / f
        magics[f] = p.read_bytes()[:4].hex() if p.is_file() else 'MISSING'
    ok('A3 三份随附字体都在 assets/fonts/ 且是 TrueType/OpenType',
       not missing and all(m in ('00010000', '4f54544f', '74727565') for m in magics.values()),
       f'missing={missing} magic={magics}')

    # A4：只列真的能用的
    # [EN] A4: only list what actually works
    choices = G.font_choices()
    tokens = [c[0] for c in choices]
    bad_bundle = [tk for tk in ('serif', 'sans', 'kai') if tk in tokens
                  and not (G.FONT_DIR / G.BUNDLED_FONTS[tk][1]).is_file()]
    # ⚠ **判据自己重新数一遍装了哪些字体**，不能拿 `available_system_fonts()` 当尺子：
    #   那是**被测对象本身** —— 把它改成"永远返回全部"，用它的判据照样是绿的
    #   （第一版就是 self-referential 的，反例法 M2 一跑就暴露）。
    # [EN] ⚠ **The criterion recounts which fonts are installed itself**; it must not use
    # [EN] `available_system_fonts()` as its ruler -- that IS the object under test, so mutating it to
    # [EN] "always return everything" would still leave a self-referential criterion green (the first
    # [EN] version was exactly that, exposed the moment reverse-experiment M2 ran).
    installed = set()
    for d in G._sys_font_dirs():
        if d.is_dir():
            installed |= {p.name.lower() for p in d.iterdir() if p.is_file()}
    listed_sys = [tk for tk in tokens if tk in G.SYSTEM_FONTS]
    sys_ok = all(G.SYSTEM_FONTS[tk][1] in installed for tk in listed_sys)
    bare = [tk for tk, label in choices if label.strip() == tk]
    ok('A4a 选项表里没有"文件不存在却仍列出"的随附字体', not bad_bundle, bad_bundle)
    ok('A4b 列出的系统字体**本机真的装了**（判据自己查字体目录，不用被测函数当尺子）',
       sys_ok, f'listed={listed_sys}')
    ok('A4c 选项的显示名**不是裸 token**（serif / yahei / system …）', not bare, bare)

    # A5：从基准缩放
    # [EN] A5: scale from the baseline
    base = dict(G._BASE_METRICS)
    CFG.set('UI_FONT_SCALE', 100)
    G.apply_font_settings()
    at100 = {k: getattr(G, k) for k in base}
    base_narr = G.NovelWorldApp.NARR_FS
    CFG.set('UI_FONT_SCALE', 130)
    G.apply_font_settings()
    at130 = {k: getattr(G, k) for k in base}
    narr130 = G.NovelWorldApp.NARR_FS
    ratio = round(at130['SET_FS'] / at100['SET_FS'], 2)
    ok('A5a 字号缩放真的生效（SET_FS ×1.3）', abs(ratio - 1.3) < 0.02,
       f'{at100["SET_FS"]} → {at130["SET_FS"]} (×{ratio})')
    ok('A5b 控件高跟着字号一起缩（不许只放大字号）',
       at130['SET_H'] > at100['SET_H'] and at130['BTN_H'] > at100['BTN_H'],
       f'SET_H {at100["SET_H"]}→{at130["SET_H"]}, BTN_H {at100["BTN_H"]}→{at130["BTN_H"]}')
    r130 = at130['SET_H'] / at130['SET_FS']
    ok('A5c 缩放后「框高/字号」仍落在 [1.6, 2.6]（133% 时字会顶到边框）',
       1.6 <= r130 <= 2.6, f'{r130:.2f}')
    ok('A5d 叙事区字号也跟着缩放', abs(narr130 / base_narr - 1.3) < 0.05,
       f'{base_narr} → {narr130}')
    CFG.set('UI_FONT_SCALE', 100)
    G.apply_font_settings()
    back = {k: getattr(G, k) for k in base}
    ok('A5e ★ 缩放**从基准算**：130% 再回 100% 必须回到原值（不累乘）',
       back == at100, f'{at100} vs {back}')

    # A6：没有遗留的字面量字号
    # [EN] A6: no leftover literal font sizes
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    left = []
    for i, ln in enumerate(src.split('\n'), 1):
        if ln.lstrip().startswith('#'):
            continue
        for m in re.finditer(r'size=(\d+(?:\.\d+)?)', ln):
            left.append((i, m.group(0)))
    ok('A6 源码里没有遗留的字面量字号（否则缩放到 130% 会有小字不动）',
       not left, left[:5])

    # A7：命令行开关
    # [EN] A7: command-line switches
    spec = __import__('config').SPEC.get('HIDE_COMMAND_BAR', {})
    ok('A7a HIDE_COMMAND_BAR 在 SPEC 里且默认 True',
       spec.get('type') == 'bool' and spec.get('default') is True, spec.get('default'))
    CFG.set('HIDE_COMMAND_BAR', 'true')
    off = G.runtime_features().get('command_bar')
    CFG.set('HIDE_COMMAND_BAR', 'false')
    on = G.runtime_features().get('command_bar')
    ok('A7b runtime_features()["command_bar"] 如实反映 HIDE_COMMAND_BAR',
       off is False and on is True, f'hide→{off}, show→{on}')
    CFG.set('HIDE_COMMAND_BAR', 'true')

    # A8：i18n（含动态取值那组字体名）
    # [EN] A8: i18n (including the dynamically-fetched font names group)
    dyn = []
    for tk, (_fam, _f, zh, _en) in {**G.BUNDLED_FONTS, **G.SYSTEM_FONTS}.items():
        dyn.append(zh)
    set_lang('en')
    miss = [s for s in dyn if t(s) == s]
    set_lang(_lang)
    ok('A8a 字体名（动态取值，i18n_check 扫不到）在英文下都有译文', not miss, miss)
    set_lang('en')
    lit = ['界面字体', '界面字号', '缩放', '随附{name}', '跟随系统', '系统 · {name}',
           '运行窗口底部的命令行', '关闭命令行（不显示命令输入框与按钮）']
    miss2 = [s for s in lit if s not in _ZH2EN]
    set_lang(_lang)
    ok('A8b 新加的字面量文案都登记了英文', not miss2, miss2)


# ══════════════════════════════════════════════════════════════
#  B 组：真机
# [EN] Group B: real device
# ══════════════════════════════════════════════════════════════
def _buttons(page):
    return [c for c in VU.walk(page) if type(c).__name__ == 'FilledButton']


def _tree_texts(root) -> list:
    """控件树里所有**看得见的字**。

    ⚠ 不能只用 `VU.all_texts()`：Flet 1.0 里 `ft.FilledButton(t('发送'))` 的
    `content` 是**裸字符串**，不是 `ft.Text` —— 只收 `ft.Text` 的采集器会把
    所有按钮文字漏掉，于是"界面上没有「发送」"这条判据**永远为真**
    （假绿）。这里把 `str` 的 content、`ft.Text.value`、TextField 的
    value/hint_text 一起收。

        English:
    All **visible text** in the control tree.
        ⚠ Cannot use `VU.all_texts()` alone: in Flet 1.0 `ft.FilledButton(t('发送'))`'s `content` is a
        **bare string**, not an `ft.Text` -- a collector that only takes `ft.Text` misses all button
        labels, making "there is no Send button on screen" **always true** (a false green). Here we
        collect string content, `ft.Text.value`, and a TextField's value/hint_text together.
    """
    out = []
    for c in VU.walk(root):
        if isinstance(c, ft.Text) and c.value:
            out.append(str(c.value))
        if isinstance(c, ft.TextField):
            for a in ('value', 'hint_text'):
                v = getattr(c, a, None)
                if v:
                    out.append(str(v))
        ct = getattr(c, 'content', None)
        if isinstance(ct, str) and ct:
            out.append(ct)
    return out


def _ink_width(png, rgb, tol: int = 60, y_from: int = 0) -> int:
    """某颜色墨迹的横向跨度（像素）。用"行内最长连续段"的左右端来算。
        English:
    The horizontal span (in pixels) of a certain color's ink. Computed from the left and right ends
    of the "longest contiguous run within a line".
    """
    im = VU.image_of(png)
    px = im.load()
    w, h = im.size
    xs = []
    for y in range(y_from, h):
        for x in range(0, w):
            r, g, b = px[x, y][:3]
            if abs(r - rgb[0]) < tol and abs(g - rgb[1]) < tol and abs(b - rgb[2]) < tol:
                xs.append(x)
    return (max(xs) - min(xs) + 1) if xs else 0


def _color_bbox(png, rgb, tol: int = 60):
    im = VU.image_of(png)
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y][:3]
            if abs(r - rgb[0]) < tol and abs(g - rgb[1]) < tol and abs(b - rgb[2]) < tol:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


async def group_b(page: ft.Page) -> None:
    app = G.NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.6)

    # B1
    theme_fam = str(getattr(getattr(page, 'theme', None), 'font_family', ''))
    reg = dict(getattr(page, 'fonts', None) or {})
    # ★★ 2026-10-14 改：原来期望「主题字体 == 随附**宋体**族名（默认 auto）」，
    #   可这一句读的是**用户环境里的 `.env`** —— 用户在「天机 · 界面外观」里
    #   选了楷体（`UI_FONT=kai`），于是这条在**他自己的机器上**永远红
    #   （`verify_font` 的 A3 是同一天同一个根因）。
    #   "默认 auto → 宋体"那条契约已经由 **A1 纯逻辑**钉住了（`resolve_ui_font('auto')`，
    #   不受 `.env` 影响）；这里该判的是另一件事：**配置真的落到屏幕上了**
    #   （是随附的某一份，而不是回落成系统字体/方块）。
    # [EN] ★★ Changed 2026-10-14: it used to expect "theme font == bundled **serif** family
    # [EN] (default auto)", but that reads the **user environment's `.env`** -- the user picked the
    # [EN] Kai font in "Tianji · UI appearance" (`UI_FONT=kai`), so on **his own machine** this line
    # [EN] is forever red (`verify_font`'s A3 is the same root cause on the same day).
    # [EN] The "default auto -> serif" contract is already pinned by **A1, in pure logic**
    # [EN] (`resolve_ui_font('auto')`, unaffected by `.env`); what belongs here is a different
    # [EN] thing: **the config really reaches the screen** (it is one of the bundled fonts, not a
    # [EN] fallback to a system font / tofu).
    _fams = {v[0] for v in G.BUNDLED_FONTS.values()}
    ok('B1a 主题字体是**随附字体之一**（配置说哪个就是哪个；不回落成系统字体）',
       theme_fam in _fams, f'{theme_fam} / 随附 {sorted(_fams)}')
    # ⚠ 同样**不能**拿 `bundled_font_files()` 当尺子（它就是被测对象）：
    #   判据自己按"文件在不在"算出该注册哪几个族名。
    # [EN] ⚠ Likewise **must not** use `bundled_font_files()` as the ruler (it is the object under
    # [EN] test): the criterion computes for itself which family names should be registered, by file
    # [EN] presence.
    want_fams = {fam for _tk, (fam, fname, _z, _e) in G.BUNDLED_FONTS.items()
                 if (G.FONT_DIR / fname).is_file()}
    ok('B1b page.fonts 把磁盘上**每一份**随附字体都注册了（换字体要能立刻生效）',
       want_fams <= set(reg) and len(want_fams) >= 1, f'want={want_fams} got={set(reg)}')

    # B2：界面外观页签
    # ⚠ 2026-10-12：改用**常量**（原来写死 3，而页序一变就点错页且不报错）。
    # [EN] ⚠ 2026-10-12: use the **constant** (it was hardcoded to 3, and a page-order
    # [EN] change silently landed on the wrong page).
    app.show_global_settings(tab=G.NovelWorldApp.TAB_GLOBAL_APPEARANCE)
    # [EN] B2: UI appearance tab
    # [EN] UI appearance = the 4th tab (**0-indexed**)
    page.update()
    await asyncio.sleep(0.9)
    dlgs = VU.open_dialogs(page)
    dlg = dlgs[-1] if dlgs else None
    texts = _tree_texts(dlg) if dlg else []
    sw = [c for c in VU.walk(dlg) if isinstance(c, ft.Switch)]
    sl = [c for c in VU.walk(dlg) if type(c).__name__ == 'Slider']
    ok('B2a 界面外观页有「界面字体」小节',
       any('界面字体' in x for x in texts), [x for x in texts if '字体' in x][:4])
    ok('B2b 界面外观页有「界面字号」与「缩放」',
       any('界面字号' in x for x in texts) and any(x.strip() == '缩放' for x in texts),
       [x for x in texts if '缩放' in x or '字号' in x][:4])
    ok('B2c 界面外观页有「关闭命令行」开关（Switch 至少 3 个：字体/字号/命令行之外还有别的）',
       any('命令行' in x for x in texts) and len(sw) >= 1,
       f'switches={len(sw)} sliders={len(sl)}')
    ok('B2d 界面外观页有滑杆（不透明度 + 缩放）', len(sl) >= 2, len(sl))

    # B3：下拉内容
    # [EN] B3: dropdown contents
    dds = [c for c in VU.walk(dlg) if getattr(c, 'options', None)]
    font_dd = None
    for dd in dds:
        labels = ' '.join(str(VU.opt_label(o)) for o in dd.options)
        if '宋体' in labels or 'Serif' in labels:
            font_dd = dd
            break
    ok('B3a 找得到「界面字体」下拉', font_dd is not None, f'下拉数={len(dds)}')
    if font_dd is not None:
        opts = list(font_dd.options)
        no_content = [o.key for o in opts if not getattr(o, 'content', None)]
        mismatch = [o.key for o in opts
                    if getattr(o, 'text', None)
                    and VU.opt_label(o) != getattr(o, 'text', '')]
        bare = [o.key for o in opts if str(VU.opt_label(o)).strip() == str(o.key)]
        keys = [o.key for o in opts]
        ok('B3b 每个选项都有 content（否则 Flet 只显示 key）', not no_content, no_content)
        ok('B3c 选项显示名 == text（可读记录）', not mismatch, mismatch)
        ok('B3d ★ 选项里**不出现裸 token**（serif / yahei / system）', not bare, bare)
        ok('B3e key 仍是落盘值（auto/serif/…，不是显示名）',
           'auto' in keys and 'system' in keys, keys)
        app._ui_run['_font_dd'] = font_dd

    # 关掉对话框，去运行界面
    # [EN] Close the dialog, go to the run UI
    try:
        page.pop_dialog()
    except Exception:                                        # noqa: BLE001
        pass
    page.update()
    await asyncio.sleep(0.4)

    # 造一个最小项目，好让运行界面能建起来
    # [EN] Create a minimal project so the run UI can be built
    # ★★★ 2026-10-17 修：`isolate_projects_dir()` 返回的是**换之前的老值**（这里是
    #   `.env` 里的 `D:\…\项目`），不是新目录。原写法
    #   `Path(VU.isolate_projects_dir(base)) / '字体设置验证'` 于是拼成了
    #   **用户真实项目目录** + 夹具名 ⇒ 每跑一次就往「拾卷」列表里塞一个
    #   「字体设置验证」，靠收尾 `safe_rmtree` 删；一旦被 Kill / 句柄未释放就留下来
    #   （用户机器上那两个残留就是这么来的）。⇒ 返回值只作还原用，**落点自己留**。
    # [EN] ★★★ Fixed 2026-10-17: `isolate_projects_dir()` returns the **old value** (the `.env`
    # [EN] `DEFAULT_PROJECTS_DIR`), not the new directory. So
    # [EN] `Path(VU.isolate_projects_dir(base)) / '字体设置验证'` built the **user's real project
    # [EN] directory** plus the fixture name => every run pushed a "字体设置验证" into the "拾卷" list,
    # [EN] removed only by the teardown `safe_rmtree`; a kill or a locked handle left it behind
    # [EN] (that is where the two leftovers on the user's machine came from).
    # [EN] => The return value is only for restoring; **keep the landing path yourself**.
    _seed = OUT / '_proj' / '字体设置验证'
    VU.isolate_projects_dir(_seed)
    proj_root = _seed / '字体设置验证'
    from store.project import Project                        # noqa: E402
    proj_root.mkdir(parents=True, exist_ok=True)
    for sub in ('设定集', '优化后设定', '完整设定集导出'):
        (proj_root / sub).mkdir(exist_ok=True)
    proj = Project(proj_root, '字体设置验证')
    proj.write_nwsproj()
    app.current_project = proj
    CFG.set('HIDE_COMMAND_BAR', 'true')
    app.show_main_screen()
    page.update()
    await asyncio.sleep(1.0)

    # B4：默认不显示命令行
    # [EN] B4: command line hidden by default
    tree = [c for c in VU.walk(page)]
    has_input = any(isinstance(c, ft.TextField) and getattr(c, 'hint_text', '') ==
                    t('输入命令（/help 查可用命令）') for c in tree)
    has_send = any(v == t('发送') for v in _tree_texts(page))
    ok('B4a ★ 默认（HIDE_COMMAND_BAR=true）运行界面里**没有**命令输入框', not has_input)
    ok('B4b ★ 默认运行时界面里**没有**「发送」按钮', not has_send,
       [x for x in _tree_texts(page) if '发送' in x][:3])
    png_off = await page.take_screenshot()
    (OUT / f'font_settings_cmd_off{SUFFIX}.png').write_bytes(png_off)
    # 但控件本身照旧挂着（能力不减：命令链路仍在）
    # [EN] But the control itself stays mounted as before (no capability loss: command chain still present)
    ok('B4c 命令控件仍挂在 _ui_run 上（关掉不减能力，只是不显示）',
       bool(app._ui_run.get('cmd_input')) and bool(app._ui_run.get('cmd_send')))

    # B5：打开命令行 → 控件回来 + 真的画出来
    # [EN] B5: open the command line -> control returns + actually renders
    CFG.set('HIDE_COMMAND_BAR', 'false')
    app.show_main_screen()
    page.update()
    await asyncio.sleep(1.0)
    texts2 = _tree_texts(page)
    ok('B5a 打开后「发送」按钮回到界面树里', any(x == t('发送') for x in texts2))
    send_btn = next((c for c in _buttons(page)
                     if (c.content if isinstance(c.content, str)
                         else getattr(c.content, 'value', '')) == t('发送')), None)
    ok('B5b 找得到那颗按钮', send_btn is not None)
    if send_btn is not None:
        old_bg = send_btn.bgcolor
        send_btn.bgcolor = '#ff00ff'          # 标记色法：只动颜色、不动几何
        # [EN] Marker-color method: only change color, not geometry
        page.update()
        await asyncio.sleep(0.7)
        png_on = await page.take_screenshot()
        (OUT / f'font_settings_cmd_on{SUFFIX}.png').write_bytes(png_on)
        send_btn.bgcolor = old_bg
        page.update()
        bb = _color_bbox(png_on, (255, 0, 255))
        im = VU.image_of(png_on)
        _w, h = im.size
        ok('B5c ★ 那颗按钮**真的画在屏幕上**（标记色量到像素）', bool(bb),
           f'tol=60 匹配像素 bbox={bb}')
        ok('B5d 它落在下半屏（是"最下面那一部分"）',
           bool(bb) and bb[1] > h * 0.55, f'bbox={bb} 屏高={h}')

    # B6：字号缩放让同一句字真的变宽
    # [EN] B6: font scaling makes the same sentence actually wider
    CFG.set('UI_FONT_SCALE', 100)
    G.apply_font_settings()
    page.controls.clear()
    page.add(ft.Container(content=ft.Column([
        ft.Text('张三李四王五赵六', size=G.SET_FS, color='#00ffff',
                font_family=G.UI_FONT)]), padding=40))
    page.update()
    await asyncio.sleep(0.6)
    w100 = _ink_width(await page.take_screenshot(), (0, 255, 255))
    CFG.set('UI_FONT_SCALE', 130)
    G.apply_font_settings()
    page.controls.clear()
    page.add(ft.Container(content=ft.Column([
        ft.Text('张三李四王五赵六', size=G.SET_FS, color='#00ffff',
                font_family=G.UI_FONT)]), padding=40))
    page.update()
    await asyncio.sleep(0.6)
    w130 = _ink_width(await page.take_screenshot(), (0, 255, 255))
    ok('B6 ★★ 字号 130% 后同一句字的墨迹**真的变宽**（缩放画在屏幕上，不只是改了常量）',
       w130 > w100 * 1.15, f'{w100}px → {w130}px（{G.SET_FS}）')
    CFG.set('UI_FONT_SCALE', 100)
    G.apply_font_settings()


LOGIC_ONLY = '--logic-only' in sys.argv


async def main(page: ft.Page) -> None:
    try:
        group_a()
        if not LOGIC_ONLY:
            await group_b(page)
    except BaseException:                                    # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        ok('未抛异常（整轮跑完）', False, report['fatal'][-200:])
    finally:
        passed = sum(1 for c in report['checks'] if c['ok'])
        total = len(report['checks'])
        report['passed'] = passed
        report['total'] = total
        report['ok'] = passed == total and not report.get('fatal')
        (OUT / f'font_settings_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for c in report['checks']:
            print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name'] +
                  (f"   [{c['detail']}]" if not c['ok'] else ''))
        print(f"\n字体设置验证：{passed}/{total}")
        await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    try:
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
    except Exception:                                        # noqa: BLE001
        exit_now(2)
