# -*- coding: utf-8 -*-
"""界面字体的**唯一真相**（不依赖 Flet，纯标准库）。

★ 为什么要有这个文件：`gui/app_flet.py`（Flet 主程序）与 `tools/launcher_splash.py`
（启动窗口，tkinter、跑在**另一个进程**里）都要知道"随附字体是哪几份、当前选中的那份文件在哪"。
启动窗口**不能** import `app_flet`（那会拉起整个 Flet），所以这一块真相只能放在一个
两边都 import 得起的地方 —— 就是这里。

    · `BUNDLED_FONTS` 原来是 `app_flet` 里的一个模块级字典，现在搬到这里，
      `app_flet` 改成 `from ui_fonts import BUNDLED_FONTS`（名字与用法一字未变）；
    · `ui_font_file()` 把「配置里的 token → 磁盘上那份字体文件」这条链路收在这里，
      开始界面（走 Flet 的 `page.fonts` 注册别名）与启动窗口（走 Pillow 按文件加载）
      因此**必然落在同一份字形上** —— 这是用户 2026-10-17「标题的字体不对，
      要跟开始界面的标题字体一样」的根因修复。

⚠ 只在**随附字体**时有文件；用户在「天机 · 界面外观」里选了系统字体（如"微软雅黑"）
  时返回 `None` —— 调用方一律**退回系统族名**，绝不因为缺字体文件就崩。

English:
The **single source of truth** for UI fonts (no Flet dependency, standard library only).
★ Why this file exists: both `gui/app_flet.py` (the Flet program) and
`tools/launcher_splash.py` (the tkinter splash, a **separate process**) need to know which fonts
ship with the program and where the selected one lives on disk. The splash **cannot** import
`app_flet` (that would pull in all of Flet), so this shared truth has to live somewhere both can
import -- here.
  · `BUNDLED_FONTS` used to be a module-level dict inside `app_flet`; it moved here and
    `app_flet` now does `from ui_fonts import BUNDLED_FONTS` (same name, same usage);
  · `ui_font_file()` folds the "config token -> the font file on disk" chain into one place, so
    the start screen (Flet, registers the alias via `page.fonts`) and the splash (Pillow, loads
    the file) **land on the same glyphs** -- the root-cause fix for the user's 2026-10-17
    "the splash title font is wrong, make it the same as the start screen".
⚠ Returns `None` for system fonts (e.g. "Microsoft YaHei" picked in Tianji · UI appearance);
   callers fall back to the family name and must never crash over a missing font file.
"""
from __future__ import annotations

from pathlib import Path

#: 项目根（本文件就在根目录）⇒ `assets/fonts`
APP_DIR = Path(__file__).resolve().parent
FONT_DIR = APP_DIR / 'assets' / 'fonts'

#: 随附字体：`token -> (Flet 族名, 文件名, 中文名, 英文名)`
#:
#: ★ 这份字典是**唯一真相**：`gui/app_flet.py` 从这里 import，
#:   `tools/launcher_splash.py` 也从这里取"当前那份字体文件在哪"。
#:   ⚠ 两份字体各自的字形并不相同（比如「门」的第一笔）—— 所以"开始界面用哪份"
#:   与"启动窗口用哪份"**必须是同一份**，改这里两边一起变。
#:
#: English: Bundled fonts: `token -> (Flet family name, filename, Chinese label, English label)`
#: ★ This dict is the **single source of truth**: `gui/app_flet.py` imports it, and
#:   `tools/launcher_splash.py` reads it to find the current font file.
#:   ⚠ The faces are not interchangeable (e.g. the first stroke of 「门」) -- "which one the start
#:   screen uses" and "which one the splash uses" **must be the same one**; change it here and both
#:   follow.
BUNDLED_FONTS: dict = {
    'serif': ('NWS Noto Serif SC', 'NotoSerifSC-Regular.otf', '思源宋体', 'Noto Serif SC'),
    'sans': ('NWS Noto Sans SC', 'NotoSansSC-Regular.otf', '思源黑体', 'Noto Sans SC'),
    'kai': ('NWS LXGW WenKai', 'LXGWWenKai-Regular.ttf', '霞鹜文楷', 'LXGW WenKai'),
}

#: `UI_FONT` 的默认值口径（与 `app_flet.resolve_ui_font()` 一致）：
#: 空 / `auto` ⇒ 随附的**思源宋体**。
#: English: How the default `UI_FONT` resolves (same as `app_flet.resolve_ui_font()`):
#: empty / `auto` ⇒ the bundled **Noto Serif SC**.
DEFAULT_TOKEN = 'serif'


def bundled_font_file(token: str) -> Path | None:
    """`token` 对应的**字体文件**（磁盘上真的在才给，否则 `None`）。
    English: The **font file** for `token` (only if it really exists on disk, else `None`)."""
    v = (token or '').strip()
    if v in ('', 'auto'):
        v = DEFAULT_TOKEN
    item = BUNDLED_FONTS.get(v)
    if not item:
        return None                      # 系统字体：没有随附文件
    p = FONT_DIR / item[1]
    return p if p.exists() else None


def ui_font_file() -> Path | None:
    """**当前**界面字体对应的字体文件（读 `config.CFG.s('UI_FONT')`）。

    启动窗口用它按文件加载字体 —— 与开始界面（`page.fonts` 注册同一个文件）
    于是落在**同一份字形**上，不会出现"两边同族不同脸"（系统里装了整族思源宋体时，
    tkinter 的 `weight='bold'` 会挑到 Black，而开始界面用的是随附的 Regular + 合成粗体）。

        English:
    The font file for the **current** UI font (reads `config.CFG.s('UI_FONT')`).
    The splash loads the font by file with it -- the same file the start screen registers through
    `page.fonts` -- so both land on the **same face**. Otherwise they drift apart (when the whole
    Noto Serif SC family is installed, tkinter's `weight='bold'` picks Black, while the start
    screen uses the bundled Regular plus synthetic bold).
    """
    try:
        import config
        return bundled_font_file(config.CFG.s('UI_FONT'))
    except Exception:                                    # noqa: BLE001
        # ⚠ 配置读不出来也要能开窗口 ⇒ 退回"默认那份"
        # [EN] The window must still open if the config can't be read ⇒ fall back to the default
        return bundled_font_file(DEFAULT_TOKEN)
