# -*- coding: utf-8 -*-
"""启动 splash：`start` 期间那一块"书封"窗口（无控制台，但**什么都能看见**）。

用户 2026-10-17（附了开始界面截图）：
「start 的时候虽然没有命令行 但是有一个类似 splash 的窗口，带有下面这部分内容
（Logo、名字、『把故事，活一遍』主题语）……消息框改成滚动显示的消息条，且可以展开为
包含更新信息的命令行输出……最后是版本、是否本地运行、以及技术平台，背景用目前背景图的缩略版本。」
随后又点名：**「Logo 名字和标语 按照开始窗口的样式设置；消息框不要带边框；下面展开的
消息框小一些；整个背景图放到后面……而不是前面有大量的纯色块承载各个组件」**。

所以这块窗口**不是一张卡片**：**整张背景图铺底**，Logo / 名字 / 标语 / 消息条 / 底栏
**直接画在图上**（canvas 文字，没有 Panel、没有边框）—— 与开始界面是同一个视觉。

它怎么拿到消息
--------------
启动器（`start.exe`）把**自己正在写的日志**路径写进 spec，本窗口从**文件末尾**开始 tail：
启动器的每一步（`lg.printf`）都会落到那一份日志里 ⇒ 这里自然"全都有"。
  · 消息条：永远显示**最后一条**，长了就横向滚动；**默认收起**（失败也不自动展开）；
  · 「详情 ▾」：展开**一小块**命令行输出（等宽、按行滚动、错误行标红），再点收起；
  · 失败：启动器往 `fail` 文件里写一句原因 ⇒ 本窗口收住不关，红字 + 消息条变红；
  · 成功：主程序（Flet）把窗口显示出来后写 `ready` 文件 ⇒ 本窗口自己消失；
  · 右上角「✕」随时可关（无边框窗口没有系统按钮）。

参数：`--spec <json>`（启动器写的），`--from-end 1`（只看新写的行），`--expanded`（测试用）。
自检：`--selftest <out.json>` —— 把窗口建出来、记下控件摘要、立刻退出（给判据用）。

English:
The "book cover" splash shown while `start` runs (no console, but **everything is visible**).
It is **not a card**: the whole background image is the canvas, and logo / name / tagline /
message strip / footer are **drawn straight onto it** (canvas text -- no panels, no borders),
matching the start screen's look.
How it gets messages: the launcher writes the path of **the log it is writing** into the spec and
this window tails it **from the end**; every step lands there.
  · Message strip: always the **latest** line, scrolling horizontally when long; **collapsed by
    default** (no auto-expand even on failure);
  · "Details": expands a **small** command-line output box (monospace, errors in red);
  · Failure: the launcher writes a reason into the `fail` file ⇒ red text, strip turns red, stays open;
  · Success: the main program writes `ready` once its window is up ⇒ this window closes itself;
  · "✕" at the top right closes it at any time.
Args: `--spec <json>`, `--from-end 1`, `--expanded` (testing).
Self-test: `--selftest <out.json>` -- build, record a widget summary, exit (for judges).
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

#: 纸色 / 墨色（与主程序「古朴纸册」同一套）
PAPER = '#F7F1E5'
PAPER_LO = '#FBF7EE'
INK = '#3B332B'
MUTED = '#6E6252'
GOLD = '#A8874F'
#: 展开按钮**悬停**时用的深金（比常态更深一档）。
#: ★ 为什么用"加深颜色 + 加粗笔画"而不是"加一个圆角底色"：
#:   用户 2026-10-17 三轮明确说过不要色块/边框（"消息栏和版本号的边框也去掉"），
#:   而判据 `E5f` 还钉着**矩形数必须是 0** —— 加底色会当场把它判红。
#:   现代 UI 里的 ghost icon button 常态本来就是纯图标，**悬停只变前景色**，
#:   所以这不是妥协，是那种按钮本来的画法。
# [EN] Deep gold for the expand button's **hover** state (one notch darker than normal).
# [EN] ★ Why "darker + thicker" rather than "add a rounded background": the user said three times
# [EN] on 2026-10-17 that they want no colour patches or borders ("drop the border from the strip
# [EN] and the version line too"), and criterion `E5f` pins **rectangle count == 0** -- a background
# [EN] would turn it red on the spot. Ghost icon buttons in modern UI are just an icon at rest and
# [EN] **change their foreground on hover**, so this is how that button is drawn, not a compromise.
GOLD_DEEP = '#7E6130'
ERR = '#A33A2A'

#: 展开后那块命令行输出的配色（**深色终端**，2026-10-23 用户点名）。
#:
#: ★ 为什么改成黑色而不是继续用浅纸底：用户原话「**展开之后显示黑色日志**」。
#:   浅纸底 + 深墨字的日志区，和它上面的书封是同一个平面，看起来像"页面里又写了一小段字"，
#:   而日志在用户心里是**另一个东西**（终端输出、要扫、要找报错）。
#:   深底是这块区域"我不是正文"的最短信号 —— 也给了一个稳定的对比度让红字真的跳出来
#:   （`#A33A2A` 在浅纸上的对比度约 4.6:1，压在深底上只有 2.1:1，根本读不出来）。
#: ⚠ 这是**唯一**一处深色块。上面那条消息条与底栏仍然一个矩形都没有（判据 `E5f` 钉着
#:   矩形数 = 0）—— 那是"书封"的规矩，日志区是嵌进图里的一块窗口，不是书封的一部分。
#: [EN] Colours for the expanded output box (**dark terminal**, named by the user 2026-10-23).
#: [EN] ★ Why black instead of pale paper: the user's words were "**show a black log when
#: [EN] expanded**". A pale box with dark ink reads as "a paragraph written on the page" and is
#: [EN] coplanar with the book cover, while a log is **something else** to the user (terminal
#: [EN] output to scan and to find errors in). A dark ground is the shortest signal for "this is
#: [EN] not body text", and it gives the error red a contrast that actually reads
#: [EN] (`#A33A2A` is ~4.6:1 on paper but only 2.1:1 on a dark ground).
#: [EN] ⚠ This is the **only** dark patch. The strip and the footer still have no rectangles at
#: [EN] all (criterion `E5f` pins rectangle count == 0) -- that rule is about the *book cover*;
#: [EN] the log is a small window embedded in it, not part of the cover.
LOG_BG = '#17150F'          # 近黑，偏暖一点点（纯黑压在暖纸色旁会发蓝、发脏）
LOG_FG = '#D9D3C4'          # 主字色：比纯白柔和，长时间看不刺眼
LOG_EDGE = '#4A4034'        # 细边：深一点的暖灰，让这块区域有边界但不抢眼
LOG_ERR = '#E8826B'         # 报错行（深底上要**提亮**，不能再沿用纸上的暗红）
LOG_NOTE = '#C9A96A'        # 主程序的进度行（`→ …`）：淡金，与书封的金色同族
LOG_SRC = '#8B8175'         # `[时间][来源]` 那一格（2026-10-27）：退后的暖灰，不抢正文
LOG_SEL = '#3D4A55'         # 选中底色
LOG_SB_BG = '#2A251D'       # 滚动条

W = 860
#: 收起时的高度。
#:
#: ★★★ 2026-10-23（用户：「**不展开的时候，启动界面应该更小一些才对**」）：480 → 350。
#:   480 是照着背景图 `title_bg_splash.png` 的原尺寸定的，而不是照着**内容**定的 ——
#:   内容到 y=242（消息条）就结束了，下面 238px 全是空纸。实测那 238px 的
#:   逐行细节量只有 6~9（`title_bg_splash.png` 整张就是均质纸纹，detail 全部低于 10），
#:   没有任何需要保留的构图 ⇒ **能裁**，而且裁掉的正好是"什么都没画"的那一段。
#:   350 = 消息条 242 + 半个字高 + 一行失败提示（284）+ 底栏（323）+ 底边距（27）。
#:   ⚠ 展开态那一截必须留着（2026-10-27 起，见 `H_EXP`）：那张
#:     `title_bg_splash_tall.png` 的**下半部分（y>480）细节量 26~67**，是真有东西的
#:     （画本身），所以展开时那一截要一直留着 —— 用户说的也是"不展开时更小"。
# [EN] Collapsed height. ★★★ 2026-10-23 (user: "**when it's not expanded the splash should be
# [EN] smaller**"): 480 -> 350. 480 came from the background image's own size, not from the
# [EN] **content**: the content ends at y=242 (message strip) and the 238px below were blank paper.
# [EN] Measured: per-row detail in that range is only 6~9 (`title_bg_splash.png` is uniform paper
# [EN] texture throughout, detail below 10), so there is no composition to preserve => it can be cut,
# [EN] and what gets cut is exactly the part with nothing drawn on it.
# [EN] 350 = strip 242 + half a line + failure line (284) + footer (323) + bottom margin (27).
# [EN] ⚠ The expanded band must stay (from 2026-10-27, see `H_EXP`): the lower half of
# [EN] `title_bg_splash_tall.png` (y>480) has detail 26~67 -- there is real artwork there. The user
# [EN] asked for "smaller when not expanded" precisely.
H_BASE = 350              #: 收起时的高度
#: ★★★ 2026-10-27（用户：「启动界面的日志窗口展开我想**更长一些 也更高一些**，
#:   里面需要有各个服务拉起来的细节日志」）：620 → 820。
#:   ★★★ 同一天**第二轮**用户又说「日志框**又太高了**，高度减少 50%、宽度不变」
#:   ⇒ 日志框 436 → **218**，展开态跟着变成 **602**（现在是**算式**，见下面 `H_EXP`：
#:     顶边 + 框高 + 底部那一截 —— 窗口与框是同一个决定的两半，不许一个改一个不改）。
#:   ⚠ 与 `tools/make_splash_art.py::H_TALL` 是同一个数写在两处
#:   （底图要正好铺满展开态）—— 判据 `E5i` 钉着两者相等。
#:   ⚠ 收起态 350 **不动**：那是 2026-10-23 用户点名要的"不展开的时候更小"。
# [EN] ★★★ 2026-10-27 (user: "the expanded log window should be **longer and taller**, and it needs
# [EN] the detail logs of each service coming up"): 620 -> 820. ★★★ **Second round the same day**
# [EN] the user said "the log box is **too tall again**, cut its height by 50%, keep the width"
# [EN] => box 436 -> **218**, expanded becomes **602** (now an **expression**, see `H_EXP` below:
# [EN] top + box + bottom band -- window and box are two halves of one decision and must not drift).
# [EN] ⚠ Same number as `tools/make_splash_art.py::H_TALL` in two places (the backdrop must fill the
# [EN] expanded state exactly) -- criterion `E5i` pins them equal. ⚠ The collapsed 350 does **not**
# [EN] move: that is the "smaller when not expanded" the user asked for on 2026-10-23.
TICK_MS = 140             #: 消息条滚动间隔
POLL_MS = 250             #: 日志/ready/fail 轮询间隔
MSG_CHARS = 74            #: 消息条一行最多几个字（**兜底值**；真值按像素实测，见 `_msg_cols`）
MSG_LEFT = 82             #: 消息条左端（与标题/Logo 同一列）
MSG_RIGHT_PAD = 72        #: 消息条右端距窗口右边多少像素（要给展开按钮让出位置）
#: 失败那一行（居中）左右各留多少像素。比消息条窄得多 —— 它不用给按钮让位。
#: [EN] Side padding of the centred failure line. Much smaller than the strip's: no button to
#: [EN] make room for.
STATUS_SIDE_PAD = 26
#: ★★★ 2026-10-27：失败时消息条写的那句（**不许**把原因再抄一遍 —— 用户 2026-10-27
#:   报「报错的时候错误信息是两条」，就是因为原因同时画在消息条和下面那行红字上）。
#:   消息条是"进度行"，失败态它只说"没成"；**原因只有一处**：下面那行居中的红字。
#: [EN] ★★★ 2026-10-27: what the strip says on failure (the reason must **not** be copied here --
#: [EN] the user reported "the error message is two lines" because the reason was painted on both
#: [EN] the strip and the red line below). The strip is the *progress* line; on failure it only
#: [EN] says "did not make it". The reason lives in **one** place: the centred red line below.
STRIP_FAIL = '启动没成功'
#: 失败那一行在原因缺失时的兜底文案。
#: [EN] Fallback text for the failure line when no reason was supplied.
STATUS_FAIL_FALLBACK = '✘ 启动失败（点那个 chevron 看完整输出）'
#: 三家服务那一排步骤点的纵向位置（标语 190 / 消息条 242 之间）。
#: ★ 2026-10-23：用户要"三家服务画成步骤点"。放在这一条细带上：
#:   它离消息条 21px、离标语 31px，两边都不挤；**收起态也有**，不占额外高度。
# [EN] Vertical position of the service step-dots (between the tagline at 190 and the strip at 242).
# [EN] ★ 2026-10-23: the user asked for the three services as step dots. This thin band sits 21px
# [EN] above the strip and 31px below the tagline -- tight on neither -- and it is present in the
# [EN] **collapsed** state too, so it costs no extra height.
STEPS_Y = 221
#: 展开态日志块：顶边 / 高 / 宽（`create_window` 吃的是**中心**，所以中心 y 另算）。
#:
#: ★★★ 2026-10-27（用户：「日志窗口展开我想更长一些 也更高一些」）：124 → **374**，
#:   窗口 620 → 820。日志是这块窗口存在的理由（用户要在里面看见服务拉起来的全过程），
#:   7 行只够"正在拉起 X（1/3）"那两句 —— 真出问题时，报错原文根本进不来。
#:   ⚠ 顶边 **不许动**（一直都是 274，即消息条 242 下面 32px）：判据 `shoot_splash` ④
#:     钉着"展开态只往下长"（控制台顶边以上与收起态**逐像素一致**），
#:     顶边一动，收起态那一段就会在展开时变样 —— 用户看到的是"上面的字跳了一下"。
#:     ⇒ 要更高就**只加 `LOG_H`**，别去抬 `LOG_BOX_TOP`。
# [EN] Expanded log box: top edge / height / width (note `create_window` takes the **centre**).
# [EN] ★★★ 2026-10-27 (user: "the expanded log window should be longer and taller"): 124 -> **374**,
# [EN] window 620 -> 820. The log is the reason this window exists, and 7 lines only fit the two
# [EN] "starting X (1/3)" lines -- when something actually breaks, the error text never shows.
# [EN] ⚠ The top edge **must not move** (always 274, i.e. 32px under the strip at 242): criterion
# [EN] `shoot_splash` ④ pins "expanded grows downward only" (everything above the console top is
# [EN] **pixel-identical** to the collapsed state). Move it and that band changes when expanding --
# [EN] the user sees "the text above jumped". => To get taller, grow `LOG_H` only.
LOG_BOX_TOP = 274
#: ★★★ 2026-10-27（**第二轮**，用户：「日志框又太高了 请比现在高度减少百分之50 宽度不变」）：
#:   436 → **218**（正好一半）。⚠ **只有高变**，宽 `LOG_W` 一个像素都不动。
#:   上一轮 124 → 436 是"要更长更高"，这一轮用户自己往回收 —— **用户的手感是唯一口径**，
#:   不替他判断"多少才对"。
#: [EN] ★★★ 2026-10-27 (**second round**, user: "the log box is too tall again, cut its height by
#: [EN] 50%, keep the width"): 436 -> **218** (exactly half). ⚠ Only the height changes; `LOG_W`
#: [EN] does not move a pixel. The previous round went 124 -> 436 for "longer and taller"; now the
#: [EN] user pulls it back himself -- **his feel is the only yardstick**, do not second-guess it.
LOG_H = 218
LOG_W = W - 150
#: ★★★ 展开态窗口**跟着日志框走**：`H_EXP = 顶边 + 框高 + 底部那一截`。
#:   ⚠ 为什么不再把 820 写死：窗口高度与框高是**同一个决定的两半** ——
#:     只改框高、窗口不动 ⇒ 框下面露出 218px 空白；只改窗口、框不动 ⇒ 同样是空白。
#:     写成算式，两个就改不成一个跑另一个不跑（判据 L12 钉的就是这个等式）。
#:   底部那一截 = 日志框下面到窗口底边：工具行（框下 20）+ 状态行 + 底栏那一叠。
#: ⚠ 与 `tools/make_splash_art.py::H_TALL` 是同一个数写在两处（底图要铺满展开态）
#:   —— 判据 `E5i` 钉着三者相等。⚠ 收起态 350 **不动**。
#: [EN] ★★★ The expanded window **follows the log box**: `H_EXP = top + box + bottom band`.
#: [EN] ⚠ Why 820 is no longer hard-coded: the window height and the box height are **two halves of
#: [EN] one decision** -- change only the box and 218px of blank shows below it; change only the
#: [EN] window and it is blank just the same. As an expression, one cannot move without the other
#: [EN] (criterion L12 pins exactly this equality). The bottom band is what sits below the box: the
#: [EN] action row (20 under the box) + status line + footer stack.
#: [EN] ⚠ Same number as `tools/make_splash_art.py::H_TALL` in two places (the backdrop must fill
#: [EN] the expanded state) -- criterion `E5i` pins all three equal. ⚠ The collapsed 350 does not move.
EXP_BOTTOM_BAND = 110
H_EXP = LOG_BOX_TOP + LOG_H + EXP_BOTTOM_BAND     # = 274 + 218 + 110 = 602
#: 日志区内最多几行（给 `tk.Text` 的 `height`，真高由 `LOG_H` 定 —— 两者要一致，
#:   否则滚动条的行高与框内高度对不上）。
#: ★ 2026-10-27 第二轮：24 → **14**（跟着 `LOG_H` 一起减半：框只有 218px 了，
#:   还按 24 行去申请，滚动条的"一屏"会比框高一倍，滚一下跳两屏）。
#: [EN] Max lines shown in the log area (the `height` given to `tk.Text`; the real height comes from
# [EN] `LOG_H` -- the two must agree or the scrollbar's line height won't match the box).
# [EN] ★ 2026-10-27 second round: 24 -> **14** (halved along with `LOG_H`: the box is only 218px
# [EN] now, and asking for 24 lines makes the scrollbar's "one screen" twice the box).
LOG_ROWS = 14
#: 展开态那条工具行（复制 / 打开文件）的纵向位置 —— **从日志块倒推**，不写死：
#:   它在日志块之下、"失败那一行"（`H_EXP - 66`）之上，窗口一改高三处就得一起走。
# [EN] Vertical position of the action row (copy / reveal) in the expanded state, **derived from the
# [EN] log box** rather than hard-coded: below the box, above the failure line (`H_EXP - 66`), so all
# [EN] three move together when the window grows.
LOGTOOL_Y = LOG_BOX_TOP + LOG_H + 20


def _dpi_aware() -> None:
    """Windows 上声明 DPI 感知 —— 否则高分屏上整块字都是糊的。
        English: Declare DPI awareness on Windows -- otherwise text is blurry on HiDPI."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # PROCESS_SYSTEM_DPI_AWARE
    except Exception:                                    # noqa: BLE001
        pass


def _register_bundled_fonts(spec: dict) -> None:
    """把 `assets/fonts/` 里的随附字体**临时注册**到本进程（FR_PRIVATE）。

    ★ 为什么要这一步：开始界面的标题用的是随附的 **NWS Noto Serif SC**
      （`app_flet.UI_FONT`，来自 `assets/fonts/NotoSerifSC-Regular.otf`）。
      用户 2026-10-17：「标题的字体你跟开始界面要一样」—— 系统里通常没装这个字体，
      不注册的话 tkinter 只能退回宋体/黑体，一眼就看得出不是同一个。

        English:
    Register the bundled fonts in `assets/fonts/` **for this process only** (FR_PRIVATE).

    ★ Why: the start screen's title uses the bundled **NWS Noto Serif SC**
      (`app_flet.UI_FONT`, from `assets/fonts/NotoSerifSC-Regular.otf`).
      User, 2026-10-17: "make the title font the same as the start screen" -- the font is usually
      not installed system-wide, and without registering it tkinter falls back to SimSun/Hei and
      it's visibly a different typeface.
    """
    if os.name != 'nt':
        return
    logo = spec.get('logo') or ''
    try:
        fonts = Path(logo).parent.parent / 'fonts'
    except Exception:                                    # noqa: BLE001
        return
    if not fonts.is_dir():
        return
    try:
        import ctypes
        gdi = ctypes.windll.gdi32
        for f in sorted(fonts.glob('*.*')):
            if f.suffix.lower() in ('.ttf', '.otf'):
                # FR_PRIVATE(0x10)：只对本进程可见，不改系统字体表
                gdi.AddFontResourceExW(str(f), 0x10, 0)
    except Exception:                                    # noqa: BLE001
        pass


def _pick_font(root: tk.Misc, prefer: tuple[str, ...], size: int = 10,
               weight: str = 'normal') -> tkfont.Font:
    """挑一个装得上的字体（优先中文黑体，最后退回 Tk 默认）。
        English: Pick an installed font (Chinese UI faces first, Tk default last)."""
    have = set(tkfont.families(root))
    for name in prefer:
        if name in have:
            return tkfont.Font(root=root, family=name, size=size, weight=weight)
    return tkfont.Font(root=root, size=size, weight=weight)


def _decode_log(data: bytes) -> str:
    """把日志的**一块新字节**解成文本：先按行试 UTF-8，解不动的行再试 GBK。

    ★★★ 为什么不能一句 `data.decode('utf-8','replace')`（2026-10-25 用户报"启动界面乱码"）：
      这份 `logs/launcher.log` 是**两个进程混着写**的 —— Go 启动器写的行是 UTF-8，
      而它起的 Python 子进程（`service_ctl.py` / `platform_install.py`）在 Windows 上
      被重定向时按 **cp936(GBK)** 输出（管道 ⇒ Python 退回系统 locale）。
      整块硬解 UTF-8 会让 GBK 那些行变成 `PenShot �� ֹͣ` 这类垃圾。
    ★ 按**行**分别判断（不是整块）：一行必然来自同一个进程，所以"解不动再换 GBK"
      是安全的；整块混判会把没问题的 UTF-8 行也拖下水。
    ★ 这是**兜底**，不是主修：主修是让那三个脚本自己输出 UTF-8
      （见 `novelservices/service_ctl.py` 里的说明）。这里兜的是
      "以后又冒出一个没改的 Python 子进程"和"用户手上还是旧启动器"。
    ⚠ 最后仍然 `errors='replace'`：真遇到非中英日韩的编码（比如俄文）宁可显示问号，
      也不能让整个启动窗口因为一行日志而崩掉。
    [EN] Decode one **chunk** of new log bytes: try UTF-8 **per line**, then GBK for the lines it
    [EN] cannot decode. Why not a single `decode('utf-8','replace')` (user-reported mojibake,
    [EN] 2026-10-25): this log is written by **two processes** -- the Go launcher writes UTF-8, while
    [EN] the Python children it spawns emit **cp936/GBK** on Windows when redirected (pipe => Python
    [EN] falls back to the system locale). Per-line is safe because a line comes from one process;
    [EN] deciding per chunk would drag good UTF-8 lines down with the bad ones.
    [EN] This is a **fallback**, not the main fix (the three scripts now force UTF-8 themselves).
    [EN] It covers "some future Python child forgets" and "the user still has an older launcher".
    """
    out = []
    for raw in data.split(b'\n'):
        if not raw:
            out.append('')
            continue
        try:
            out.append(raw.decode('utf-8'))
        except UnicodeDecodeError:
            try:
                out.append(raw.decode('gbk'))
            except UnicodeDecodeError:
                out.append(raw.decode('utf-8', 'replace'))
    return '\n'.join(out)


#: 启动日志的统一前缀：`[HH:MM:SS][来源] 正文`（2026-10-27 用户点名）。
#: ⚠ 与 `gui/app_flet.py::SPLASH_PREFIX` 是同一个格式写在两处（一个写、一个读）：
#:   判据 `verify_splash_boot` 拿两边各造一行、互相能认，才算配套。
# [EN] The unified start-up log prefix: `[HH:MM:SS][source] body` (named by the user, 2026-10-27).
# [EN] ⚠ Same format as `gui/app_flet.py::SPLASH_PREFIX`, written in two places (one writes, one
# [EN] reads): criterion `verify_splash_boot` builds a line on each side and checks they recognise
# [EN] each other.
_LOG_PREFIX_RE = re.compile(r'^\[(\d{1,2}:\d{2}:\d{2})\]\[([^\]]*)\]\s*(.*)$')


class LogTail:
    """从文件末尾开始读**新写进来的行**（跨平台、UTF-8 容错、半行留到下次）。

        English: Read **newly written lines** from the end of a file (UTF-8 tolerant,
        keeps a partial line for the next poll)."""

    def __init__(self, path: str, from_end: bool = True) -> None:
        self.path = path
        self.pos = 0
        self.buf = ''
        try:
            st = os.stat(path)
            self.pos = st.st_size if from_end else 0
        except OSError:
            self.pos = 0

    def read(self) -> list[str]:
        try:
            with open(self.path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size <= self.pos:
                    self.pos = size if size < self.pos else self.pos
                    return []
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return []
        self.pos += len(data)
        text = self.buf + _decode_log(data)
        lines = text.split('\n')
        self.buf = lines.pop()          # 最后一段可能是半行
        out = []
        for ln in lines:
            ln = ln.rstrip('\r')
            if ln.strip():
                out.append(ln)
        return out


class Splash:
    def __init__(self, root: tk.Tk, spec: dict, from_end: bool = True) -> None:
        self.root = root
        self.spec = spec
        self.from_end = from_end
        self.expanded = False
        self.lines: list[str] = []
        self.ticker = ''
        self.tick_pos = 0
        self.failed = False
        self.closed = False
        self._fail_reason = ''
        self.tail = LogTail(spec.get('log') or '', from_end=from_end)
        # ★★★ 2026-10-23（用户：「我希望在启动界面把这几个服务都拉起来成功之后再进入
        #   开始界面」）：主程序现在会**真的等**三家创作服务拉起完才写 `ready`，
        #   于是这块窗口可能要亮十几秒到几分钟。
        #   如果消息条上的字一直不变，用户会读成"卡死了"（本项目的硬伤之一）。
        #   ⇒ `boot_t0` = 收到第一条"界面/服务正在……"的进度行那一刻；
        #     `_tick` 在消息条前面加一个**每秒都在变**的 `12s ·`。
        #   ⚠ 计时起点必须是"主程序开始说话"那一刻，不是窗口创建那一刻：
        #     窗口建完到主程序起来之间还隔着 Flet 启动，那段不该算进"等服务的时长"。
        # [EN] ★★★ 2026-10-23 (user: "pull these services up in the splash, then enter the start
        # [EN] screen"): the main program now **waits** for the three services before writing `ready`,
        # [EN] so this window may stay up from ten seconds to several minutes. A strip whose text
        # [EN] never changes reads as "frozen" (a hard defect here). ⇒ `boot_t0` is the moment the
        # [EN] first progress line arrives; `_tick` prefixes a `12s ·` that changes every second.
        # [EN] ⚠ The clock starts when the main program first speaks, not at window creation: Flet
        # [EN] start-up happens in between and must not count as "waiting for services".
        self.boot_t0: float | None = None
        #: 三家服务各自到哪一步了：`{序号: 'wait'|'run'|'done'|'fail'}`，`_steps_n` = 共几家。
        #: ★ 只认主程序那几行 `→ …（2/3）` 里的**序号**，不认名字（名字以后可能改）。
        # [EN] Per-service state: `{index: 'wait'|'run'|'done'|'fail'}`, `_steps_n` = how many.
        # [EN] Keyed by the **index** in `→ …（2/3）`, not by name (names may change later).
        self._steps: dict = {}
        self._steps_n = 0
        #: 用户翻上去之后又来了几条（`↓ N 条新` 那个数字）。
        # [EN] How many lines arrived while the user was scrolled up (`↓ N new`).
        self._new_lines = 0
        #: ★ 2026-10-27：分流计数器 —— **只进日志区**的行数 / **顶到消息条**的行数。
        #:   判据靠这两个数证明"服务细节真的没有顶掉进度行"，而不只是"看起来没顶掉"。
        # [EN] ★ 2026-10-27: split counters -- lines that went **to the log only** / lines that
        # [EN] **took the strip**. The criteria use them to prove service detail really did not
        # [EN] push the progress lines off, not merely that it "looks like" it didn't.
        self._n_detail = 0
        self._n_strip = 0
        #: 底栏原文（`_flash_footer` 临时改字之后要还回去）。
        # [EN] The footer's original text (restored after `_flash_footer`).
        self._foot_text = ''
        #: 最近一次读到的日志滚动位置 `(顶, 底)`（判据靠它判"翻上去有没有被抢"）。
        #: [EN] The last observed log scroll position (top, bottom); judges read it to tell
        #: whether scrolling up got stolen.
        self._last_yview: list = []
        #: `--selftest-probe scroll` 的结果（判据读它；不是探针模式时是 None）。
        #: [EN] Result of `--selftest-probe scroll` (read by judges; None otherwise).
        self._probe = None

        # 字号与字体照**开始界面**：标题用随附的宋体（NWS Noto Serif SC）+ 字距拉开，
        # 标语同样；两者都带**白色描边**（`ink_text` 的 stroke 做法，这里用偏移重绘模拟）。
        # [EN] Fonts/sizes follow the **start screen**: the bundled serif for the title with widened
        # [EN] letter-spacing, same for the tagline; both get a **white outline** (the `ink_text`
        # [EN] stroke trick, simulated here by drawing offset copies).
        serif = ('NWS Noto Serif SC', 'Noto Serif SC', '思源宋体', 'SimSun')
        self.f_title = _pick_font(root, serif, size=26, weight='bold')
        self.f_tag = _pick_font(root, serif, size=12)
        family = ('Microsoft YaHei UI', '微软雅黑', 'Noto Sans SC')
        self.f_msg = _pick_font(root, family, size=10)
        self.f_foot = _pick_font(root, family, size=9)
        self.f_close = _pick_font(root, family, size=13)
        self.f_mono = _pick_font(root, ('Cascadia Mono', 'Consolas', 'Courier New'), size=8)

        self.bg_img = None
        self.bg_tall = None
        self.logo_img = None
        self.console = None
        #: 展开按钮是否处于悬停态（`_caret_hover` 只在状态变化时改控件，
        #: 所以这里必须有个初值 —— 否则第一帧悬停会被判成"已经悬停"、什么都不做）。
        # [EN] Whether the expand button is hovered (`_caret_hover` only touches widgets on a state
        # [EN] *change*, so this needs an initial value -- otherwise the first hover looks like
        # [EN] "already hovered" and does nothing).
        self._caret_on = False
        # 标题/标语用 **Pillow 按字体文件**渲染成图片再贴上来（见 `_ink_image`）；
        # 这些 PhotoImage 必须一直有人引用，否则被回收 ⇒ 什么都不显示。
        # [EN] Title/tagline are rendered by **Pillow from the font file** into images (see
        # [EN] `_ink_image`); these PhotoImages must stay referenced or they are garbage-collected
        # [EN] and nothing shows up.
        self._imgs: list = []
        self._font_file = self._ui_font_file()
        self._title_mode = 'family'
        self._build()
        self._poll()
        self._tick()

    # ── 界面（全部画在背景图上：没有卡片、没有边框）─────────────────
    def _load_images(self) -> None:
        """背景与 Logo 只读一次（切换展开/收起时不重复解码 2MB PNG）。
            English: Load background & logo once (don't re-decode 2MB PNGs on each toggle)."""
        if self.bg_img is not None:
            return
        imgs = Path(self.spec.get('bg') or '').parent
        bg = self.spec.get('bg') or ''
        tall = str(imgs / 'title_bg_splash_tall.png')
        try:
            if bg and os.path.exists(bg):
                self.bg_img = tk.PhotoImage(file=bg)
            if os.path.exists(tall):
                self.bg_tall = tk.PhotoImage(file=tall)
        except Exception:                                # noqa: BLE001
            pass
        logo = self.spec.get('logo') or ''
        try:
            if logo and os.path.exists(logo):
                self.logo_img = tk.PhotoImage(file=logo)
        except Exception:                                # noqa: BLE001
            self.logo_img = None

    @staticmethod
    def _ui_font_file():
        """开始界面**当前用的那份字体文件**（`ui_fonts.ui_font_file()`，与 Flet 注册的是同一份）。

        ⚠ 拿不到就返回 `None` —— 调用方退回按族名找系统字体，**窗口照常出现**。

            English:
        The font file the start screen currently uses (`ui_fonts.ui_font_file()` -- the very file
        Flet registers). ⚠ `None` when unavailable; callers fall back to a family name and the
        window still shows up.
        """
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from ui_fonts import ui_font_file
            return ui_font_file()
        except Exception:                                # noqa: BLE001
            return None

    def _ink_image(self, text: str, size: int, fill: str, stroke: int,
                   bold: bool = False):
        """用**开始界面同一份字体文件**把一行字渲染成图片（Pillow 按文件加载）。

        ★ 为什么不再直接用 canvas 文字（用户 2026-10-17：「标题的字体不对」）：
          开始界面的标题是 Flet 用 `page.fonts` **按文件**注册的那份随附 OTF 画的；
          而 tkinter 只能按**族名**到系统里找 —— 用户机器上若装了思源宋体整族，
          `weight='bold'` 会挑到 **Black**，跟开始界面（随附 Regular + 合成粗体）
          根本不是同一张脸。**按文件加载才锁得死两边同源。**

        ⚠ Pillow 不在 / 字体文件不在 ⇒ 返回 `None`，调用方退回 `_outlined()`
          （窗口照常出现，只是字形回落到系统族）。

            English:
        Render a line with the **same font file the start screen uses** (Pillow loads it by file).
        ★ Why not plain canvas text any more (user, 2026-10-17: "the title font is wrong"): the
        start screen draws its title with the bundled OTF that Flet registers **by file**, while
        tkinter can only look up a **family name** in the system -- and if the whole Noto Serif SC
        family is installed, `weight='bold'` picks **Black**, a different face from the start
        screen's bundled Regular + synthetic bold. **Loading by file is the only way to pin both
        sides to the same glyphs.**
        ⚠ Returns `None` when Pillow or the font file is missing; the caller falls back to
        `_outlined()` (the window still appears, just with a system face).
        """
        if not self._font_file:
            return None
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            font = ImageFont.truetype(str(self._font_file), size)
            pad = stroke + 6
            probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
            l, t, r, b = probe.textbbox((0, 0), text, font=font, stroke_width=stroke)
            img = Image.new('RGBA', (max(1, r - l) + pad * 2,
                                     max(1, b - t) + pad * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            pos = (pad - l, pad - t)
            # ① 白色描边垫底（= 开始界面 `ink_text(stroke=N)` 的白色那一层）
            # [EN] ① white stroke underneath (the white layer of the start screen's
            # [EN] `ink_text(stroke=N)`)
            d.text(pos, text, font=font, fill=fill,
                   stroke_width=stroke, stroke_fill='#FFFFFF')
            if bold:
                # ② 合成粗体：开始界面是 `FontWeight.BOLD`，而随附的只有 Regular
                #    ⇒ 再描一圈本色，跟 Flutter 的合成粗体同一路数。
                # [EN] ② synthetic bold: the start screen asks for `FontWeight.BOLD` while only
                # [EN] Regular ships, so trace another pass in ink -- same idea as Flutter's
                # [EN] synthetic bold.
                d.text(pos, text, font=font, fill=fill, stroke_width=1, stroke_fill=fill)
            photo = ImageTk.PhotoImage(img)
            self._imgs.append(photo)          # ★ 留住引用，否则被回收
            return photo
        except Exception:                                # noqa: BLE001
            return None

    def _build(self) -> None:
        H = H_EXP if self.expanded else H_BASE
        self.root.geometry(f'{W}x{H}+{self._cx()}+{self._cy(H)}')
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=PAPER,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill='both', expand=True)
        self._load_images()
        img = (self.bg_tall if self.expanded else self.bg_img)
        if img is not None:
            self.canvas.create_image(0, 0, image=img, anchor='nw')

        # ① Logo（居中）—— 与开始界面同一个 logo、同样的"压在图上的"做法
        if self.logo_img is not None:
            self.canvas.create_image(W // 2, 74, image=self.logo_img, anchor='center')

        # ② 名字 + 主题语（**逐字与开始界面一致**：字距拉开 + 白色描边）
        # [EN] Name + tagline (**character-for-character as on the start screen**:
        # [EN] widened spacing + a white outline)
        title = self.spec.get('title') or ''
        title = ('小 说 世 界 A I 模 拟' if '小说世界' in title
                 else title)
        sub = self.spec.get('subtitle') or ''
        sub = ('── 把 故 事 ， 活 一 遍 ──' if '把故事' in sub else sub)
        # 优先**按字体文件**渲染（与开始界面同一份字形）；拿不到才回落到系统族名。
        # [EN] Prefer rendering **from the font file** (same glyphs as the start screen); fall back
        # [EN] to the system family name only if that fails.
        img_t = self._ink_image(title, 26, INK, stroke=3, bold=True)
        self._title_mode = 'file' if img_t is not None else 'family'
        if img_t is not None:
            self.canvas.create_image(W // 2, 152, image=img_t, anchor='center')
        else:
            self._outlined(W // 2, 152, title, self.f_title, INK, r=2)
        img_s = self._ink_image(sub, 12, '#5B5145', stroke=2, bold=False)
        if img_s is not None:
            self.canvas.create_image(W // 2, 190, image=img_s, anchor='center')
        else:
            self._outlined(W // 2, 190, sub, self.f_tag, '#5B5145', r=1)

        # ③ 消息条：**干干净净一行字**，没有色块也没有边框
        #    （三轮迭代的落点：先"加边框，否则压在背景上看不出来" → 底图变淡后
        #     "去掉背景颜色" → 现在"边框也去掉"）。
        # [EN] Message strip: **just a line of text** -- no fill, no border (three rounds: first
        # [EN] "add a border, it's invisible over the picture", then "drop the background colour"
        # [EN] once the backdrop got pale, and now "drop the border too").
        self._msg_id = self.canvas.create_text(
            MSG_LEFT, 242, text='准备中…', font=self.f_msg, fill=INK, anchor='w')
        # ★★★ 2026-10-21（用户：「启动画面的展开按钮 也改成三角形的按钮 正常是向右
        #   展开头向下」）—— 原来这里是**文字按钮**「详情 ▾ / 收起 ▴」，改成**三角按钮**。
        #   画法、理由、命中区为什么不画矩形：见 `_mk_detail_btn`。
        # [EN] ★★★ 2026-10-21 (user: "the splash's expand button should also be a triangle
        # [EN] button -- pointing right normally, head down when expanded"): this used to be a
        # [EN] **text button** ("详情 ▾ / 收起 ▴") and is now a **triangle button**. See
        # [EN] `_mk_detail_btn` for how it is drawn and why the hit area is not a rectangle.
        self._mk_detail_btn()

        # ④ 右上角 ✕
        self._close_id = self.canvas.create_text(
            W - 30, 26, text='✕', font=self.f_close, fill=MUTED,
            anchor='center', tags=('close',))
        self.canvas.tag_bind('close', '<Button-1>', lambda e: self.close())

        # ⑤ 展开：**一块够大的**命令行输出 —— **深色终端**（2026-10-23 用户点名：
        #    「展开之后显示黑色日志」）。配色理由见 `LOG_BG` 那一段。
        #    ★ 2026-10-27：7 行 → `LOG_ROWS`（24 行）。尺寸全走常量，不在这里写死。
        # [EN] Expanded: a **generously sized** output box -- **dark terminal** (named by the user
        # [EN] 2026-10-23: "show a black log when expanded"). See `LOG_BG` for the reasoning.
        # [EN] ★ 2026-10-27: 7 lines -> `LOG_ROWS` (24). Sizes come from constants, not literals.
        if self.expanded:
            frame = tk.Frame(self.canvas, bg=LOG_BG, bd=0,
                             highlightthickness=1, highlightbackground=LOG_EDGE)
            self.console = tk.Text(
                frame, height=LOG_ROWS, bg=LOG_BG, fg=LOG_FG,
                insertbackground=LOG_FG, selectbackground=LOG_SEL,
                selectforeground='#FFFFFF',
                font=self.f_mono, bd=0, highlightthickness=0, wrap='none')
            # ★ 滚动条也要跟着变深：Windows 上留一条浅色滚动条压在深底旁边，
            #   像"忘了改的一截"（同一块区域里两种主题是最扎眼的拼接）。
            # [EN] The scrollbar must darken too: a pale bar beside a dark ground looks like
            # [EN] "a part that was forgotten" -- two themes in one region is the loudest seam.
            sb = tk.Scrollbar(frame, command=self.console.yview, width=10,
                              bg=LOG_SB_BG, troughcolor=LOG_BG,
                              activebackground=LOG_EDGE, bd=0,
                              highlightthickness=0, relief='flat',
                              elementborderwidth=0)
            self.console.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
            self.console.pack(side='left', fill='both', expand=True)
            # `create_window` 吃的是**中心**：顶边 = 中心 - 高/2 ⇒ 中心由 `LOG_BOX_TOP` 算出，
            #   别把 336 直接写在这儿（那是顶边，写上去整块会往上跑 187px）。
            # [EN] `create_window` takes the **centre**: top = centre - height/2, so the centre is
            # [EN] derived from `LOG_BOX_TOP`. Never write 336 here -- that is the top edge, and the
            # [EN] whole box would jump 187px upwards.
            self.canvas.create_window(W // 2, LOG_BOX_TOP + LOG_H // 2,
                                      window=frame, width=LOG_W, height=LOG_H)
            # ★ 滚轮：`tk.Text` 自己会滚，但鼠标要**先落到它上面**。日志区只有那么高，
            #   用户往往在它下面那截空白里滚滚轮 —— 那时事件落在 canvas 上、什么都不动，
            #   读作"滚不动"。⇒ 窗内任何位置滚轮都转给日志（日志是本窗口唯一可滚的东西）。
            # [EN] Wheel: `tk.Text` scrolls itself, but only when the pointer is **over it**. The box
            # [EN] is 124px tall and users often wheel over the blank area below -- that lands on the
            # [EN] canvas, nothing moves, and it reads as "cannot scroll". So route the wheel from
            # [EN] anywhere in the window to the log (the only scrollable thing here).
            for _seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                self.canvas.bind(_seq, self._on_wheel, add='+')
                self.console.bind(_seq, self._on_wheel, add='+')
            # 工具行（复制 / 打开文件）—— 只在展开态出现，放在日志块**下面**
            # （上面 242 处是消息条，挤不进第二行字；下面这块展开态本来是空的）。
            # [EN] Action row (copy / reveal), expanded state only, **below** the log box: there is
            # [EN] no room above it (the strip sits at 242) and this band is empty when expanded.
            self._mk_log_tools()
            for ln in self.lines:
                self._console_write(ln)
            self.console.see('end')

        # ⑥ 失败那一行 + 底栏（**只有字**，与开始界面同一格式：连金边都不画了）
        # [EN] Failure line + footer (**text only**, same format as the start screen: no outline
        # [EN] either)
        self._status_id = self.canvas.create_text(
            W // 2, H - 66, text='', font=self.f_msg, fill=ERR, anchor='center',
            # ★★★ 2026-10-27：`width` + `justify` 让长原因**折成两行**而不是被砍掉。
            #   原因由**写入方**给（`fail` 文件），主程序那句有 80 个字 —— 在 10 号字下
            #   约 863px，**比整幅窗口还宽**。改成"整幅宽"也只有 62 字（`_status_cols`
            #   实测），中间省略会正好吃掉"点右上角 ✕ 仍然进入"那半句 —— 也就是
            #   **告诉用户怎么脱身的那半句**。⇒ 允许折行，字数上限 = 两行。
            # [EN] ★★★ 2026-10-27: `width` + `justify` let a long reason **wrap to two lines**
            # [EN] instead of being cut. The reason comes from the **writer** (the `fail` file) and
            # [EN] the UI's sentence is 80 chars -- ~863px at size 10, **wider than the whole
            # [EN] window**. Even spanning the full width that is only 62 chars (measured by
            # [EN] `_status_cols`), and the middle ellipsis would eat exactly "press ✕ to enter
            # anyway" -- the half that says **how to get out**. => Allow wrapping, capped at 2 lines.
            width=(W - 2 * STATUS_SIDE_PAD), justify='center')
        ver = str(self.spec.get('version') or '').lstrip('vV')
        foot = ' · '.join(x for x in (
            f'v{ver}' if ver else '',
            str(self.spec.get('mode') or '本地运行'),
            str(self.spec.get('platform') or 'Python + Flet'),
        ) if x)
        self._foot_text = foot                    # `_flash_footer` 临时改字之后要还回去
        self._foot_id = self.canvas.create_text(
            W // 2, H - 27, text=foot, font=self.f_foot, fill=MUTED, anchor='center')

        # ⑦ 三家服务的步骤点（2026-10-23 用户要求）+ 展开态右下角那条 `↓ N 条新`
        # [EN] ⑦ Service step-dots (requested 2026-10-23) + the `↓ N new` badge (expanded only)
        self._paint_steps()
        self._paint_new_badge()

    def _mk_log_tools(self) -> None:
        """展开态日志块下面那一行：`打开日志文件   复制全部`（右对齐）。

        ★ 为什么不画成有底色的按钮：这个窗口从上到下**没有一块色块**（判据 `E5f`
          钉着矩形数 = 0），做成胶囊按钮会凭空多出两块填充。
          这类"次要动作"在现代 UI 里就是一行小字（ghost link），悬停时颜色加深即可 ——
          与那颗 chevron 的处理完全一致（同一套视觉语言，不是两套）。
        [EN] The row under the expanded log box: `打开日志文件   复制全部`, right aligned.
        [EN] ★ Why not filled buttons: this window has **no colour patches** top to bottom
        [EN] (criterion `E5f` pins rectangle count == 0), and pills would add two fills out of nowhere.
        [EN] Secondary actions like these are plain links in modern UI, darkening on hover -- the same
        [EN] treatment as the chevron above (one visual language, not two).
        """
        items = [('open', '打开日志文件', self._do_open_log),
                 ('copy', '复制全部', self._do_copy)]
        x = W - 78                                  # 右端与日志块的右边缘对齐
        for tag, label, fn in reversed(items):
            try:
                tid = self.canvas.create_text(
                    x, LOGTOOL_Y, text=label, anchor='e', font=self.f_foot,
                    fill=GOLD_DEEP, tags=('logtool', tag))
                self.canvas.tag_bind(tag, '<Button-1>',
                                     lambda e, f=fn: f(), add='+')
                self.canvas.tag_bind(
                    tag, '<Enter>',
                    lambda e, t=tid: self.canvas.itemconfigure(t, fill=INK), add='+')
                self.canvas.tag_bind(
                    tag, '<Leave>',
                    lambda e, t=tid: self.canvas.itemconfigure(t, fill=GOLD_DEEP), add='+')
                x -= int(self.f_foot.measure(label)) + 22
            except Exception:                        # noqa: BLE001
                continue

    def _on_wheel(self, e) -> None:
        """滚轮：任何位置都转给日志区（见 `_build` 里那段说明）。
            English: Wheel anywhere scrolls the log (see the note in `_build`)."""
        if self.console is None:
            return
        try:
            delta = -1 if getattr(e, 'num', 0) == 4 else (
                1 if getattr(e, 'num', 0) == 5 else
                (-1 if getattr(e, 'delta', 0) > 0 else 1))
            self.console.yview_scroll(delta * 3, 'units')
            self._paint_new_badge()             # 跳回底部就把提示清掉
        except Exception:                        # noqa: BLE001
            pass

    def _chevron_image(self, deg: float, color: str, *, width: float = 1.6,
                       box: int = 26):
        """把 chevron **用 Pillow 超采样**渲染成一张抗锯齿的小图（拿不到 Pillow 就 `None`）。

        ## 为什么必须走这条路（2026-10-23 实测出来的）

        第一版用的是 `canvas.create_line`。形状是对的（截图字符画确认是 `>` 和 `v`），
        但把按钮区放大成字符画一看，笔画宽度在 **2~4px 之间逐行跳**：

        ```
        -6 |...............##.......................|
        -5 |...............####.....................|
        -4 |................####....................|
        -3 |..................###...................|
        ```

        原因是 tkinter 的 canvas **完全不抗锯齿** —— 斜线只能落在整数像素上，
        2px 的斜线每一行覆盖量都不同。实心三角看不出这个问题（大面积填充，
        边缘那点台阶被淹没了），而细描边恰好把它放大成"毛糙"。

        ⇒ 用户说的"不好看"，有一半是这个：**一条 2px 的斜线在浅纸上是毛的**。

        做法与标题同一套（`_ink_image` 就是 Pillow 按文件渲染）：
        **4 倍超采样**画好，再 `LANCZOS` 缩回目标尺寸 —— 边缘变成半透明的灰阶过渡，
        视觉上就是抗锯齿。圆头端点用两个小圆补（Pillow 的 `line` 没有 capstyle）。

        ⚠ 拿不到 Pillow / `ImageTk` 时返回 `None`，调用方**退回 canvas 线条**
          —— 界面照常出现，只是回到"毛边"那一版。宁可毛糙，不能白屏。

            English:
        Render the chevron into a small **anti-aliased** image via Pillow supersampling
        (`None` when Pillow is unavailable).
        Why this route (measured 2026-10-23): v1 used `canvas.create_line`. The shape was right
        (the character-art dump confirms `>` and `v`) but the stroke width **jumped between 2 and
        4px row by row**, because tkinter's canvas **does not anti-alias at all** -- a slanted line
        can only land on integer pixels. A solid triangle hid this (large fill; the edge stair-steps
        drown), while a thin stroke magnifies it into "rough". So half of the user's "ugly" is this:
        **a 2px slanted line on pale paper is fuzzy.**
        Same technique as the title (`_ink_image` already renders with Pillow): draw at **4x** and
        `LANCZOS` back down, turning the edge into semi-transparent grey levels. Round caps are two
        small circles (Pillow's `line` has no capstyle).
        ⚠ Returns `None` without Pillow/`ImageTk`; the caller **falls back to canvas lines** -- the
        window still appears, just back to the fuzzy version. Rough beats blank.
        """
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:                                # noqa: BLE001
            return None
        ss = 4                                            # 超采样倍数
        S = box * ss
        try:
            im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            # 点坐标与 `_chevron_pts` **同一套**：`k` 把"34px 盒基准的 6.0/5.4"
            # 换算到超采样画布上，缩回 `box` 之后实际笔画是 `6*box/34 × 5.4*box/34`
            # —— 所以盒子变小，笔画**自动等比**变小，两边不会再各写一份数字。
            # [EN] Same geometry as `_chevron_pts`: `k` maps the 34px-box baseline onto the
            # [EN] supersampled canvas, so after downscaling the strokes are `6*box/34 x
            # [EN] 5.4*box/34` -- shrinking the box scales them too, no second copy of the numbers.
            c = S / 2.0
            k = S / 34.0
            pts = self._chevron_pts(c, c, deg, half=6.0 * k, drop=5.4 * k)
            xy = list(zip(pts[0::2], pts[1::2]))
            lw = max(1, int(round(width * ss)))
            d.line(xy, fill=color, width=lw, joint='curve')
            # 圆头：两端各补一个半径为半线宽的小圆（Pillow 的 line 只能方头/斜接）
            # [EN] Round caps: a small circle at each end (Pillow's line has no capstyle)
            r = lw / 2.0
            for px, py in (xy[0], xy[-1]):
                d.ellipse((px - r, py - r, px + r, py + r), fill=color)
            im = im.resize((box, box), Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            self._imgs.append(photo)          # ★ 留住引用，否则被回收
            return photo
        except Exception:                                # noqa: BLE001
            return None

    def _mk_detail_btn(self) -> None:
        """消息条右侧那个**展开按钮**（2026-10-23 重画：实心三角 → 描边 chevron）。

        ## 用户这次的话

        「启动界面的三角号下拉按钮我还是觉得不好看，你**调研一般我们启动界面用什么按钮
          展开详细日志**，然后给我优化下这个按钮，让他更好看」

        ## 调研结论（这部分是本方法每条设计的依据，不是我的口味）

        微软的 *Progressive Disclosure Controls* 指南把这类控件分成两种，并给出选择原则：
        **"用户应当仅凭外观就能正确预测控件的行为"**（predict by inspection alone）。
          · **Rotating triangles**（实心旋转三角）—— 用于"就地展开一条消息的详情"，
            指向**已经发生**的方向（收起指右、展开指下）；
          · **Chevrons**（描边折线）—— 同样用于就地展开，但指向**将要发生**的方向。

        而 `vocab.design` 对这两个符号的来源说得很直接：
        **实心三角（disclosure triangle）是文件树 / macOS outline view 的语言，
        比 chevron 更老，也仍是 macOS 的原生默认**；现代 UI 用的是 chevron，并且
        **"展开时字形是**转过去**而不是换一个"**——
        「chevron 会报告状态；它不持有状态」，**旋转本身就读作状态变化**。

        ⇒ 用户觉得"实心三角不好看"，正好命中业界早就走完的那一步：
          我们原来画的是 1980 年代 Finder 的实心 disclosure triangle，
          在一块**浅纸色、无边框**的书封上，那块 14px 实心金色是整屏**唯一的高饱和实心块**，
          视觉重量远大于它的功能。换成**两笔 2px 的圆头 chevron**之后：
          笔画面积约为原来的三分之一，读起来是"一个图标"，而不是"一块颜色"。

        ## 具体五处改动

        1. **形状**：实心多边形 → `create_line` 两笔画，`capstyle=round` + `joinstyle=round`，
           线宽 2。圆头是关键细节：方头会在尖锐转角留下"缺口"，圆头才像现代图标。
        2. **旋转而不是换形状**（调研里最强调的一条）：同一个 chevron，收起 **-90°（指右）**，
           展开 **0°（指下）**。切换时**真的转过去**（4 帧缓出），不是硬切 ——
           这样"转动"本身就在告诉用户状态变了。
        3. **悬停只变前景**：`GOLD → GOLD_DEEP` + 线宽 2→3。
           ★ 不加圆角底色 —— 用户三轮说过不要色块，判据 `E5f` 也钉着矩形数必须是 0。
           现代 ghost icon button 常态就是纯图标、悬停变前景色，这不是妥协。
        4. **悬停区 = 点击区**（都是 32×32）：原来是 **tag 绑定** `<Enter>`，
           只有真碰到 14px 三角才变色 —— 而点击走的是 canvas 级距离判断 28×28。
           两个区不一样大，用户会觉得"手型光标一闪一闪的"。现在两者都走
           canvas 级 `<Motion>` + 同一个距离判断。
        5. **位置**：`W-88` → `W-46`（原来的位置离右边缘太远，中间空了一截，
           看着像"浮动在消息条中间"）。同时消息条的可用宽度跟着收到 `W-72`，
           **不再压到按钮底下**（见 `_msg_cols`）。

        ## 保留不变的东西

        · `_detail_glyph` 仍是 `'right'` / `'down'` —— 用户 2026-10-21 点名的行为没变，
          判据 `E5e` 照旧读它。
        · 命中区仍然是**距离判断**而不是透明矩形：tkinter 的 canvas 命中测试只认画出来的
          东西，`fill=''`+`outline=''` 的矩形收不到点击（会变成死块）。
        · canvas 级 `<Button-1>` 会叠在其它 tag 绑定上（点右上角 ✕ 时也会跑），
          所以这里只做距离判断，绝不无条件 `toggle()`。
        · `add='+'` 不能省，否则会替换掉已有绑定。

            English:
        The **expand button** at the right of the message strip (redrawn 2026-10-23: solid
        triangle -> stroked chevron).
        User: "I still find the triangle disclosure button on the splash ugly; **research what
        buttons splash screens normally use to expand the detailed log**, then improve this one".
        Research (the basis for each design choice here):
          · Microsoft's *Progressive Disclosure Controls* guide splits these into **rotating
            triangles** (solid, point at the state that **already happened**) and **chevrons**
            (stroked, point at what **will happen**), with the principle "users should be able to
            predict the control's behaviour by inspection alone".
          · `vocab.design` on the two glyphs: **the solid disclosure triangle is the file-tree /
            macOS outline-view language -- older than the chevron and still the macOS default**;
            modern UI uses a chevron and, in a disclosure, "the glyph **turns** rather than being
            swapped ... the rotation itself reads as the change of state".
        => The user's "ugly" hits exactly the step the industry already took: we were drawing the
           1980s Finder disclosure triangle, and on a pale, borderless book cover that 14px solid
           gold block was the only saturated solid shape on screen -- far heavier than its job.
           Two 2px round-capped strokes are about a third of the area and read as "an icon"
           instead of "a patch of colour".
        Five concrete changes: (1) shape -> two-line chevron, round cap/join, width 2; (2) **turn,
        don't swap** -- same glyph, -90 deg (right) collapsed / 0 deg (down) expanded, animated over
        4 eased frames; (3) hover only changes the foreground (GOLD -> GOLD_DEEP, width 2 -> 3) --
        ★ no rounded background: the user asked three times for no colour patches and criterion
        `E5f` pins rectangle count == 0; (4) **hover area == click area** (32x32) via one canvas
        `<Motion>` + the same distance test -- it used to be a 14px tag binding for hover and 28x28
        for clicks, which made the cursor flicker; (5) position `W-88` -> `W-46`, and the strip's
        usable width is clamped to `W-72` so text no longer runs under the button.
        Unchanged: `_detail_glyph` still reports `'right'` / `'down'` (criterion `E5e` reads it);
        the hit area is still distance-based (tkinter only hit-tests drawn items); the canvas-level
        click never calls `toggle()` unconditionally; `add='+'` is still mandatory.
        """
        # 位置：离右边缘 46px（原 88 —— 太靠里，看着像浮在消息条中间）
        # [EN] Position: 46px from the right edge (was 88 -- too far in, looked like it floated
        # [EN] in the middle of the strip)
        cx, cy = W - 46, 242
        self._caret_xy = (cx, cy)
        # ★★★ 2026-10-23（用户：「**展开按钮小一些**」）：**画的**从 34 缩到 26，
        #   **点的**保持 32×32（半径 16）。
        #   ★ 为什么两者不再一样大（上一轮才统一过，这里是有意改回来）：
        #     "图标小一些"是视觉要求，"点得准"是操作要求，两件事可以同时满足 ——
        #     桌面 UI 的常规做法就是**热区比图形大一圈**（Fitts 定律：目标越大越快命中），
        #     32×32 是这条产品线早就定下的下限（判据 `E5g` 钉着）。
        #     ⚠ 上一轮统一两者，是为了修"悬停 14px / 点击 28px 两个区不一样大、
        #       光标一闪一闪"那个毛病。所以要守的是 **悬停区 == 点击区**，不是"等于图形"。
        #       这里两个都是 32×32，那条规矩照样成立。
        # [EN] ★★★ 2026-10-23 (user: "**make the expand button smaller**"): what is **drawn**
        # [EN] shrinks 34 -> 26, what is **clicked** stays 32x32 (radius 16).
        # [EN] ★ Why they are no longer the same size (they were unified the round before -- this is
        # [EN] deliberate): "smaller icon" is visual, "easy to hit" is motor, and both can hold --
        # [EN] desktop UI routinely makes the hot area larger than the graphic (Fitts's law), and
        # [EN] 32x32 is the floor this product line already fixed (criterion `E5g` pins it).
        # [EN] ⚠ The earlier unification fixed "hover 14px / click 28px make the cursor flicker".
        # [EN] The rule to keep is **hover area == click area**, not "equal to the graphic";
        # [EN] both are 32x32 here, so that rule still holds.
        self._caret_hit = 16                    #: 命中/悬停区半径（32×32，与图形大小无关）
        self._caret_deg = self._caret_target_deg()
        self._detail_glyph = 'down' if self.expanded else 'right'
        # ★★ 设计语义（`chevron` = 描边折线 / `solid` = 实心三角）。
        #   判据 E5f 守的是**这个**，不是"用 canvas 画还是用 Pillow 画" ——
        #   后者是实现细节，改实现不该让判据变红（那是"锚点过期"以外的另一种假红）。
        # [EN] ★★ Design semantics (`chevron` = stroked polyline / `solid` = filled triangle).
        # [EN] E5f guards **this**, not "canvas vs Pillow" -- the latter is an implementation detail
        # [EN] and a criterion that reddens on it would be a different kind of false red.
        self._detail_style = 'chevron'
        self._detail_px = 26                    #: 渲染盒边长（内含 9.2×8.2 的笔画）
        #: 常态笔画宽度（悬停时 ×1.3）。**只此一处定义** —— 位图路、线条兜底路、
        #: 悬停重画三处都读它（上一版把 2.0 写在三个地方，改小的时候漏一个就一大一小）。
        #: [EN] Resting stroke width (hover = x1.3). **Defined once** -- the bitmap path, the
        #: [EN] canvas fallback and the hover repaint all read it (the previous version hard-coded
        #: [EN] 2.0 in three places, so shrinking it left one of them wrong).
        self._caret_w = 1.6
        # 优先用**抗锯齿的位图**（Pillow 4× 超采样）；拿不到就退回 canvas 线条。
        # [EN] Prefer the **anti-aliased bitmap** (Pillow 4x supersampling); fall back to canvas
        # [EN] lines when unavailable.
        img = self._chevron_image(self._caret_deg, GOLD, width=self._caret_w, box=self._detail_px)
        if img is not None:
            self._detail_id = self.canvas.create_image(
                cx, cy, image=img, tags=('detail',))
            self._detail_kind = 'image'
        else:
            self._detail_id = self.canvas.create_line(
                *self._chevron_pts(cx, cy, self._caret_deg),
                fill=GOLD, width=max(1, int(round(self._caret_w))),
                capstyle='round', joinstyle='round',
                tags=('detail',))
            self._detail_kind = 'line'
        # 悬停与点击都走 canvas 级 + 同一个距离判断（理由见方法说明第 4 条）
        # [EN] Both hover and click go through canvas-level handlers + the same distance test
        # [EN] (reason 4 in the docstring)
        self.canvas.bind('<Motion>', self._on_canvas_motion, add='+')
        self.canvas.bind('<Button-1>', self._on_canvas_click, add='+')
        self.canvas.bind('<Leave>', lambda e: self._caret_hover(False), add='+')

    # ── chevron 的几何 ─────────────────────────────────────────────
    @staticmethod
    def _chevron_pts(cx: float, cy: float, deg: float,
                     half: float = 4.6, drop: float = 4.1) -> tuple:
        """一个**指向下**的圆头 chevron（`⌄`）绕 (cx, cy) 旋转 `deg` 度后的三个点。

        基准形状（deg=0，指向下）：左翼 `(-half, -drop)` → 尖 `(0, +drop*0.55)` → 右翼 `(+half, -drop)`。
          · `deg=0`   ⇒ `⌄` 指向下 —— **展开态**
          · `deg=-90` ⇒ `›` 指向右 —— **收起态**（逆时针 90°）

        ⚠ 屏幕坐标 y 向下，所以标准旋转矩阵直接可用，不用反号。
        ⚠ 尖点比两翼低一点（`drop*0.55` 而不是 `drop`）—— 这是 chevron 与"两个 V 拼起来"的
          区别所在：三段等长时转角显得钝，尖多探出一点才有"折"的感觉。

            English:
        A **downward-pointing** round-capped chevron rotated by `deg` degrees about (cx, cy).
        Base shape (deg=0, pointing down): left wing -> tip -> right wing.
        `deg=0` => down (**expanded**); `deg=-90` => right (**collapsed**).
        ⚠ Screen y grows downwards, so the standard rotation matrix applies unchanged.
        ⚠ The tip dips a little further than the wings (`drop*0.55` vs `drop`): that is what
        separates a chevron from "two V's"; equal segments read as a blunt corner.
        """
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)
        out: list[float] = []
        for x, y in ((-half, -drop), (0.0, drop * 0.55), (half, -drop)):
            out += [cx + x * ca - y * sa, cy + x * sa + y * ca]
        return tuple(out)

    def _caret_target_deg(self) -> float:
        """当前**应该**朝向的角度：收起 -90（指右）/ 展开 0（指下）。
            English: The angle it **should** face: collapsed -90 (right) / expanded 0 (down)."""
        return 0.0 if self.expanded else -90.0

    def _caret_paint(self, deg: float | None = None, *, on: bool | None = None) -> None:
        """按当前角度/悬停态**重画**按钮（位图与线条两条路都在这里）。

        ★ 为什么要一个统一入口：抗锯齿版是**换图**、兜底版是**改坐标**，
          两套写法各出现在悬停、旋转、重建三处的话，迟早有一处漏改
          （"一件事两处实现"是本项目的头号毛病）。
        [EN] Repaint the button for the current angle/hover state (handles both bitmaps and lines).
        ★ Why one entry point: the anti-aliased version **swaps the image** while the fallback
        **moves coordinates**. If each appeared separately in hover, tween and rebuild, one would
        eventually be missed ("two implementations of one thing" is this project's #1 sin).
        """
        if deg is not None:
            self._caret_deg = deg
        if on is None:
            on = bool(getattr(self, '_caret_on', False))
        color = GOLD_DEEP if on else GOLD
        # 笔画宽度跟着盒子一起收（34→26 时 2.0→1.6）：盒子小了、笔画不变，读起来是"糊成一团"。
        # 悬停仍然**只加粗**（不添色块），比例维持 2:3。
        # [EN] Stroke width shrinks with the box (34->26: 2.0->1.6); keeping it would read as a blob.
        # [EN] Hover still only **thickens** (no patch), keeping the 2:3 ratio.
        width = (self._caret_w * 1.3) if on else self._caret_w
        try:
            if getattr(self, '_detail_kind', '') == 'image':
                img = self._chevron_image(self._caret_deg, color, width=width,
                                          box=self._detail_px)
                if img is not None:
                    self.canvas.itemconfigure(self._detail_id, image=img)
            else:
                self.canvas.coords(
                    self._detail_id,
                    *self._chevron_pts(*self._caret_xy, self._caret_deg))
                self.canvas.itemconfigure(self._detail_id, fill=color, width=int(width))
        except Exception:                                # noqa: BLE001
            pass

    def _caret_hover(self, on: bool) -> None:
        """悬停反馈：**只变前景**（颜色加深 + 笔画加粗），一个色块都不画。
            English: Hover feedback: **foreground only** (deeper colour + thicker strokes), no patch."""
        if getattr(self, '_caret_on', False) == on:
            return
        self._caret_on = on
        self._caret_paint(on=on)
        try:
            self.canvas.configure(cursor=('hand2' if on else ''))
        except Exception:                                # noqa: BLE001
            pass

    def _on_canvas_motion(self, e) -> None:
        """鼠标在 canvas 上移动：落在按钮命中区内就算悬停（与点击**同一套判断**）。
            English: Mouse moves over the canvas; inside the hit box counts as hover (the **same
            test** as clicking)."""
        try:
            cx, cy = self._caret_xy
            hit = self._caret_hit
        except AttributeError:
            return
        self._caret_hover(abs(int(e.x) - cx) <= hit and abs(int(e.y) - cy) <= hit)

    def _tween_caret(self, from_deg: float, to_deg: float, steps: int = 4) -> None:
        """把 chevron 从 `from_deg` **转**到 `to_deg`（缓出，4 帧）。

        ★ 为什么要动画而不是直接画成新角度（调研里最强调的一条）：
          "the glyph turns rather than being swapped ... **the rotation itself reads as the
          change of state**"。窗口高度是瞬间变的（tkinter 无法平滑改窗口尺寸），
          图标这一下旋转就是这个切换唯一的"过渡"，没有它整个动作是硬切。

        ⚠ 帧间不做事就返回（窗口可能已经被关了 / 被重建了）——
          `itemconfigure` 打在已销毁的 item 上会抛，而这里**绝不能**把异常漏出去。
        [EN] Animate the chevron from one angle to the other (eased, 4 frames).
        [EN] ★ Why animate instead of drawing the new angle: "the glyph turns rather than being
        [EN] swapped ... the rotation itself reads as the change of state". The window height jumps
        [EN] instantly (tkinter cannot resize smoothly), so this rotation is the only transition the
        [EN] toggle has; without it the whole action is a hard cut.
        [EN] ⚠ Bail out between frames if the window is gone/rebuilt -- `itemconfigure` on a
        [EN] destroyed item throws, and that must never escape here.
        """
        if abs(to_deg - from_deg) < 1 or steps <= 0:
            self._caret_deg = to_deg
            return

        def frame(i: int) -> None:
            if self.closed:
                return
            t = i / float(steps)
            eased = 1 - (1 - t) ** 2                 # 缓出：先快后慢，像"甩"过去
            # [EN] ease-out: fast then slow, like flicking over
            # ★ 走统一入口：抗锯齿版换图、兜底版改坐标（见 `_caret_paint`）
            # [EN] ★ Through the single entry point: bitmaps swap, lines move (see `_caret_paint`)
            self._caret_paint(from_deg + (to_deg - from_deg) * eased)
            if i < steps:
                try:
                    self.root.after(14, frame, i + 1)
                except Exception:                    # noqa: BLE001
                    return

        frame(1)

    def _status_cols(self) -> int:
        """失败那一行（居中、整幅宽）最多能放几个字 —— 同样是**像素实测**。

        为什么它和 `_msg_cols` 不是同一个数：消息条左边从 `MSG_LEFT` 起、右边要给
        展开按钮留位（实测 53 字），而这一行是**居中铺满整幅**的，宽度大得多。
        ⇒ 原因必须落在这里：主程序写的那句（"创作服务没起来：……点右上角 ✕ 仍然进入
        （进「天机 → 外部创作服务」可以手动重试）"）80 个字，放在消息条上要被砍掉
        27 个字，而砍掉的正好是**告诉用户怎么脱身的那半句**。
        [EN] How many characters fit on the failure line (centred, full width) -- measured in
        [EN] pixels too. Not the same number as `_msg_cols`: the strip starts at `MSG_LEFT` and
        reserves room for the chevron (53 chars measured), while this line is **centred across the
        full width**. => This is where the reason must live: the sentence the main program writes
        is 80 chars, and on the strip 27 of them -- exactly the half that says how to get out --
        would be cut.
        """
        try:
            avail = W - 2 * STATUS_SIDE_PAD
            unit = max(1, self.f_msg.measure('测'), self.f_msg.measure('W'))
            return max(24, int(avail // unit))
        except Exception:                                # noqa: BLE001
            return MSG_CHARS

    def _msg_cols(self) -> int:
        """消息条一行最多能放几个字 —— **按像素实测**，不是估的。

        ★★★ 顺手修掉一个真 bug（2026-10-23 重画按钮时才发现的）：
          原来这里写死 `MSG_CHARS = 74`，而 74 个中文字符在这种字号下约 960px，
          从 x=82 画起 ⇒ **一直画到按钮底下、再伸出窗口右边**。
          canvas 文字不会被裁切，只会"看不见" —— 症状是"消息条怎么少了一截话"，
          而且那 20 来个字本来就在滚动窗口里，占着滚动周期却永远不可见。
          ⇒ 改成用 `tkfont.Font.measure()` 实测：可用宽度 ÷ 最宽字符宽度。

        ⚠ 取 `max(中文, 拉丁大写)` 而不是平均值：混排时按平均值算会溢出，
          而溢出这一侧（字被画到看不见的地方）比"滚动窗口小一点"坏得多。
        [EN] How many characters fit on one strip line -- **measured in pixels**, not estimated.
        [EN] ★★★ A real bug fixed while redrawing the button (2026-10-23): `MSG_CHARS = 74` was
        [EN] hard-coded, but 74 CJK glyphs at this size are ~960px, drawn from x=82 => it ran under
        [EN] the button and off the right edge. Canvas text is never clipped, just invisible, so the
        [EN] symptom is "the strip is missing a chunk of words" -- and those ~20 characters stay in
        [EN] the scroll window, consuming cycle time while never being visible.
        [EN] => Measure with `tkfont.Font.measure()`: usable width / widest glyph.
        [EN] ⚠ Take `max(CJK, Latin capital)` rather than an average: an average overflows for mixed
        [EN] text, and that side (text drawn where it cannot be seen) is far worse than a slightly
        [EN] smaller scroll window.
        """
        try:
            avail = (W - MSG_RIGHT_PAD) - MSG_LEFT - 8
            unit = max(1, self.f_msg.measure('测'), self.f_msg.measure('W'))
            return max(24, int(avail // unit))
        except Exception:                                # noqa: BLE001
            return MSG_CHARS

    def _on_canvas_click(self, e) -> None:
        """canvas 上的点击：**只有落在按钮命中区内才算点它**（理由见 `_mk_detail_btn`）。"""
        try:
            cx, cy = self._caret_xy
            hit = self._caret_hit
        except AttributeError:
            return
        if abs(int(e.x) - cx) <= hit and abs(int(e.y) - cy) <= hit:
            self.toggle()

    def _outlined(self, x: int, y: int, text: str, font, fill: str,
                  halo: str = '#FFFFFF', r: int = 2, anchor: str = 'center'):
        """写一行"带白描边"的字：先在四周画几层白字，再把本色字压上去。

        对应开始界面 `ink_text(..., stroke=N)` 的做法（Flet 用它给墨字加护边）；
        tkinter 没有 stroke，只能用"偏移重绘"模拟 —— 半径别太大，否则字会发胖。

            English:
        Draw a line of "white-outlined" text: a few offset white copies first, then the ink text
        on top. Mirrors the start screen's `ink_text(..., stroke=N)`; tkinter has no stroke, so
        offset redraws are the way -- keep the radius small or glyphs get fat.
        """
        for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r),
                       (-r, -r), (r, -r), (-r, r), (r, r)):
            self.canvas.create_text(x + dx, y + dy, text=text, font=font,
                                    fill=halo, anchor=anchor)
        return self.canvas.create_text(x, y, text=text, font=font,
                                       fill=fill, anchor=anchor)

    def _cx(self) -> int:
        return self._pos()[0]

    def _pos(self) -> tuple:
        """窗口左上角 —— **只算一次，之后永远不动**。

        ★★★ 2026-10-23（用户：「有没有更优雅的显示方式」→ 选了方案 A）：
          以前 `_build` 每次都用 `_cy(当前高度)` 重新居中，于是**展开时整个窗口
          在屏幕中央重新摆位**：顶边被往上推、Logo / 名字 / 消息条全体跳位。
          这正是渐进披露里明令要避免的那种交互 ——
          GitHub Primer：*refrain from creating interactions that drastically disorient the
          user's initial point of focus*；Stellae 的常见错误清单：展开详情时，
          **触发它的那句摘要必须留在视野里**。
          ⇒ 锚点只按**收起态**算一次（用户第一眼看到的位置），展开时只向下长。
          视觉上就是从下面把一块抽屉抽出来，上面那张书封一动不动。
        ★ 机制要说清（写错了注释比没注释更糟）：**真正让它不动的是"锚点一律按
          `H_BASE` 算"**，与传进来的高度无关；`_origin` 缓存只是省两次
          `winfo_screen*()` 调用。反例法第一次打错了地方（去改缓存判空）——
          因为那不是让它不动的那个东西。
        [EN] The window's top-left corner -- computed once, never again.
        [EN] ★★★ 2026-10-23 (user: "is there a more elegant way" -> picked layout A): `_build`
        [EN] used to re-centre with `_cy(current height)` every time, so **expanding re-placed the
        [EN] whole window mid-screen**: the top edge got pushed up and logo / name / strip all
        [EN] jumped. That is exactly what progressive disclosure says to avoid -- GitHub Primer:
        [EN] *refrain from creating interactions that drastically disorient the user's initial point
        [EN] of focus*; Stellae's common-mistakes list: when a details panel opens, **the summary
        [EN] that triggered it must stay visible**. => Anchor once from the **collapsed** height and
        [EN] only grow downwards: a drawer pulled out from the bottom while the cover stays put.
        [EN] ★ Be precise (a wrong comment is worse than none): **what keeps it still is that the
        [EN] anchor is always computed from `H_BASE`**, independent of the height passed in; the
        [EN] `_origin` cache only saves two `winfo_screen*()` calls. The counterexample harness first
        [EN] poked the cache check -- because that is not the thing that holds it still.
        """
        if getattr(self, '_origin', None) is None:
            try:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
            except Exception:                            # noqa: BLE001
                sw, sh = 1920, 1080
            self._origin = (max(0, (sw - W) // 2),
                            max(0, (sh - H_BASE) // 2 - 40))
        return self._origin

    def _cy(self, h: int) -> int:
        return self._pos()[1]

    def toggle(self, animate: bool = True) -> None:
        """展开 / 收起。

        ★ 2026-10-23：`_build()` 重建 canvas 后，chevron 从**旧角度转**到新角度
          （见 `_tween_caret`）。窗口高度是瞬间变的，这一下旋转就是这个动作
          唯一的过渡 —— 没有它，整个切换是硬切。

        ⚠ `animate=False` 是给 `--selftest --expanded` 用的：自检建完窗口**立刻**读摘要，
          解析动画的 `after` 回调还在队列里 ⇒ 摘要抓到的是**中间帧**（实测 -50.6°），
          于是"方向对不对"这条判据会时红时绿（flaky）。初次构建本来也没有"从哪来"，
          不该播动画。

            English:
        Expand / collapse.
        ★ 2026-10-23: after `_build()` recreates the canvas, the chevron **turns** from the old
        angle to the new one (see `_tween_caret`). The window height jumps instantly; this turn is
        the only transition the action has -- without it it is a hard cut.
        ⚠ `animate=False` is for `--selftest --expanded`: the self-test reads the summary
        **immediately** after building while the tween's `after` callbacks are still queued, so it
        captured a **mid-frame** angle (measured -50.6) and the direction criterion went
        red/green at random (flaky). The initial build has no "where it came from" anyway.
        """
        from_deg = float(getattr(self, '_caret_deg', 0.0))
        self.expanded = not self.expanded
        self.console = None
        # 悬停态要跟着重建归零（旧 canvas 已销毁，`_caret_on` 留着会挡住新的悬停反馈）
        # [EN] Reset the hover flag with the rebuild (the old canvas is gone; a stale `_caret_on`
        # [EN] would block the new hover feedback)
        self._caret_on = False
        self.canvas.destroy()
        self._build()
        if self.failed:
            self._show_failed(self._fail_reason)
        if animate:
            self._tween_caret(from_deg, self._caret_target_deg())
        else:
            self._caret_deg = self._caret_target_deg()

    # ── 输出 ──────────────────────────────────────────────────────
    @staticmethod
    def _split_prefix(line: str) -> tuple[str, str, str]:
        """拆 `[HH:MM:SS][来源] 正文`，返回 `(时间, 来源, 正文)`；不是这个格式就 `('', '', 原行)`。

        ★★★ 2026-10-27（用户：「不同的服务输出日志可以合并在一起 用 `[时间][服务]` 日志
          这样区分」）：主程序把所有启动日志统一成这个前缀（见
          `gui/app_flet.py::splash_log`）。**拆开是必须的**，不是装饰：
            · 消息条只认**剥掉前缀后**以 `→ ` 开头的行（进度里程碑）；
            · 步骤点、计时起点也都按"剥掉前缀后的正文"判 —— 前缀一加，
              原来那三处 `startswith('→ ')` **全部失效**（行以 `[` 开头了）。
          ⚠ 这是"判据/解析被新格式静默打穿"的典型：不报错、只是从此再没触发过。
        [EN] Split `[HH:MM:SS][source] body` -> `(time, source, body)`; anything else gives
        [EN] `('', '', line)`. ★★★ 2026-10-27 (user: "merge the services' output, distinguish with
        [EN] `[time][service]`"): the main program now writes every start-up line with that prefix
        [EN] (`gui/app_flet.py::splash_log`). Splitting is **required**, not cosmetics: the strip
        [EN] accepts only lines whose **body** (prefix removed) starts with `→ `, and the step dots
        [EN] and boot clock judge the body too -- with a prefix in front, all three
        [EN] `startswith('→ ')` tests **silently stop firing** (the line now starts with `[`).
        [EN] ⚠ Textbook "a new format quietly punches through the parser": no error, it just never
        [EN] triggers again.
        """
        m = _LOG_PREFIX_RE.match(line or '')
        if not m:
            return '', '', (line or '')
        return m.group(1), (m.group(2) or '').strip(), (m.group(3) or '')

    def _console_write(self, line: str) -> None:
        if self.console is None:
            return
        _tm, _src, body = self._split_prefix(line)
        # ★ 判"出错"只看**正文**：`[18:52:03][PenShot] [ok] 停止…` 这种行里，
        #   前缀本身不含错词，但反过来 —— 服务名字段将来若带这类字，
        #   整行会被念成红字，而它其实是普普通通的一行。
        # [EN] Judge "is it an error" on the **body** only.
        _judge = body or line
        bad = any(k in _judge for k in ('✗', '失败', 'ERROR', 'Error', 'Traceback', '[FAIL]'))
        # ★ 第三种：主程序的进度行（`→ …`）。深底上如果全是一个色，那几行
        #   "正在拉起 X（2/3）"会和启动器的时间戳行糊成一片 —— 而它们正是
        #   用户等待期间唯一在动的东西，值得一个自己的颜色（淡金，与书封同族）。
        #   ⚠ 用**剥掉前缀的正文**判：加了 `[时间][来源]` 之后行以 `[` 开头，
        #      直接判整行会让所有进度行都丢掉金色（静默失效，不报错）。
        # [EN] A third class: the main program's progress lines (`→ …`). On a dark ground a single
        # [EN] colour would blend those "starting X (2/3)" lines into the launcher's timestamped
        # [EN] ones -- and they are the only thing moving while the user waits.
        # [EN] ⚠ Judged on the **body with the prefix stripped**: lines now start with `[`, so
        # [EN] testing the whole line drops the gold from every progress line (silently, no error).
        note = (not bad) and _judge.lstrip().startswith('→ ')
        tag = 'err' if bad else ('note' if note else 'ok')
        if 'err' not in self.console.tag_names():
            self.console.tag_config('err', foreground=LOG_ERR)
            self.console.tag_config('ok', foreground=LOG_FG)
            self.console.tag_config('note', foreground=LOG_NOTE)
            # ★ 2026-10-27：`[时间][来源]` 那一格用**退后的暖灰** —— 它每格都一样长、
            #   信息量最低（"谁说的、几点"扫一眼就够），正文才是要读的东西。
            #   让前缀抢色的话，一屏细节行会变成一列灰白的方括号，正文反而沉下去。
            # [EN] The `[time][source]` cell uses a **receding warm grey**: it is the same length
            # [EN] every time and carries the least information; the body is what gets read.
            self.console.tag_config('src', foreground=LOG_SRC)
        # ★★★ 2026-10-23（用户：「翻上去的时候不要抢滚动位置」）：
        #   写入**之前**先看用户是不是还在底部（`yview()[1] >= 0.999`）。
        #   在底部 ⇒ 跟着滚（这是大家期待的"跟着走"）；
        #   翻上去了 ⇒ **一点都不滚**，只在右下角浮一条 `↓ N 条新`，点它才跳到底。
        #   ⚠ 判定必须在 `insert` **之前**：插入会让内容变长，`yview` 的分母跟着变，
        #     之后再也分不清"用户刚才在不在底部"（这就是"量错了对象"）。
        # [EN] ★★★ 2026-10-23 (user: "don't steal the scroll position when I scroll up"): check
        # [EN] whether the view is still at the bottom (`yview()[1] >= 0.999`) **before** inserting.
        # [EN] At the bottom => follow (what everyone expects); scrolled up => do **not** scroll at
        # [EN] all, just float a `↓ N new` in the corner that jumps to the end when clicked.
        # [EN] ⚠ Must be measured **before** `insert`: inserting changes the denominator, and then
        # [EN] you can no longer tell where the user was -- a textbook "measured the wrong object".
        was_bottom = True
        try:
            _yv = self.console.yview()
            self._last_yview = [round(float(_yv[0]), 4), round(float(_yv[1]), 4)]
            was_bottom = _yv[1] >= 0.999
        except Exception:                                # noqa: BLE001
            pass
        if _src:
            # 前缀与正文**分两次插**：只有这样才能给两格不同颜色（一次插只能带一个 tag）。
            # [EN] Insert the prefix and the body in **two calls**: that is the only way to colour
            # [EN] the two parts differently (one insert carries a single tag).
            self.console.insert('end', f'[{_tm}][{_src}] ', ('src',))
            self.console.insert('end', body + '\n', (tag,))
        else:
            self.console.insert('end', line + '\n', (tag,))
        if was_bottom:
            self.console.see('end')
        else:
            self._new_lines += 1
            self._paint_new_badge()

    def _paint_new_badge(self) -> None:
        """右下角那条 `↓ N 条新`（点一下跳到底部）。
            English: The `↓ N new` badge at the bottom right (click to jump to the end)."""
        try:
            self.canvas.delete('newbadge')
            if self._new_lines <= 0 or not self.expanded:
                return
            # 浮在**日志块内侧的右下角**（跟着 `LOG_H` 走；原来写死 412，窗口一改高
            #   它就掉到日志块外面、和工具行撞在一起）。
            # [EN] Floats at the **inside bottom-right of the log box** (follows `LOG_H`; the old
            # [EN] hard-coded 412 fell outside the box and collided with the action row).
            x, y = W - 118, LOG_BOX_TOP + LOG_H - 34
            self.canvas.create_text(
                x, y, text=f'↓ {self._new_lines} 条新', anchor='e',
                font=self.f_foot, fill=LOG_NOTE, tags=('newbadge',))
            self.canvas.tag_bind('newbadge', '<Button-1>', lambda e: self._jump_end())
        except Exception:                                # noqa: BLE001
            pass

    def _jump_end(self) -> None:
        """跳到日志末尾，并清掉那条提示。
            English: Jump to the end of the log and clear the badge."""
        self._new_lines = 0
        try:
            if self.console is not None:
                self.console.see('end')
        except Exception:                                # noqa: BLE001
            pass
        self._paint_new_badge()

    def _probe_scroll(self) -> None:
        """给判据用的探针：**先把用户"翻上去"，再写一行，看滚动位置有没有被抢**。

        ★ 为什么必须有这个探针：跨进程没法操作 tk 控件，而"翻上去有没有被抢"
          只能由**窗口自己**在那一瞬间量。写在 `--selftest-probe scroll` 里，
          判据读 `summary()['scroll_probe']` 就行。
        ⚠ 用 `_console_write`（不走 `_push`）：不污染消息条与步骤点，
          只走"写入 → 判定在不在底部 → 要不要 see('end')"这条路，正是要测的那段。
        [EN] A probe for the judges: **scroll the user up**, write a line, see whether the view got
        [EN] stolen. ★ Needed because a separate process cannot drive tk widgets, so only the window
        [EN] itself can measure that instant. Written for `--selftest-probe scroll`; the criterion
        [EN] just reads `summary()['scroll_probe']`.
        [EN] ⚠ Uses `_console_write` (not `_push`) so the strip and dots are untouched: it exercises
        [EN] exactly the path under test (write -> was it at the bottom -> see('end') or not).
        """
        if self.console is None:
            self._probe = {'ok': False, 'why': 'not expanded'}
            return
        for i in range(80):
            self._console_write(f'probe line {i:02d} ' + 'x' * 40)
        try:
            self.console.see('end')
            self.console.yview_moveto(0.0)
            _b = list(self.console.yview())
            self._new_lines = 0
            self._console_write('probe: brand new line')
            _a = list(self.console.yview())
            self._probe = {'ok': True,
                           'before': [round(float(_b[0]), 4), round(float(_b[1]), 4)],
                           'after': [round(float(_a[0]), 4), round(float(_a[1]), 4)],
                           'new_badge': int(self._new_lines)}
        except Exception as e:                           # noqa: BLE001
            self._probe = {'ok': False, 'why': repr(e)[:120]}

    def _push(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) > 5000:
            del self.lines[:-5000]
        # ★ 失败之后消息条**钉住那条原因**：它比后续输出重要得多，而日志还在滚，
        #   不钉住的话下一行（比如收尾那几句）就会把红字换成一行平淡的黑字 ——
        #   用户刚看到"没起来"，一秒钟后屏幕上就没有那句话了。
        #   后续输出照样进详情区（`_console_write`），一个字都不丢。
        # [EN] After a failure the strip **pins the reason**: later lines keep arriving and would
        # [EN] otherwise replace the red text with an ordinary line a second later -- the user sees
        # [EN] "it failed" and then it is gone. Later output still goes to the detail box.
        if self.failed:
            self._console_write(line)
            return
        _tm, _src, body = self._split_prefix(line)
        _judge = body or line
        # ★★★ 2026-10-27：**带前缀、且正文不是里程碑的行只进日志区，不碰消息条。**
        #   服务拉起的细节（uvicorn 的 INFO、pip 的 Downloading、健康检查的重试）
        #   一行接一行地来 —— 若照样顶到消息条上，"正在拉起 PenShot（2/3）"会被
        #   后面某句 `INFO: 127.0.0.1:54321 - "GET /health"` 顶掉；
        #   而这些输出里常带 `ERROR` / `Traceback`，消息条还会被**念成红字**，
        #   明明在顺利启动，屏幕上却写着失败。
        #   ⇒ 消息条只留"人该知道的那几句"（正文以 `→ ` 打头的里程碑）。
        #   ⚠ 没有前缀的行（Go 启动器写的那批）**照旧上消息条** —— 那是老格式，
        #     里面全是"版本 / 技术平台 / 开始准备运行环境"这类一句话一步的行。
        # [EN] ★★★ 2026-10-27: **prefixed lines whose body is not a milestone go to the log only.**
        # [EN] Service bring-up detail (uvicorn INFO, pip "Downloading", health-check retries) arrives
        # [EN] line after line; putting those on the strip would push "starting PenShot (2/3)" away
        # [EN] with `INFO: 127.0.0.1 - "GET /health"`, and since such output often contains
        # [EN] `ERROR` / `Traceback` the strip would also turn **red** -- a smooth start-up reading as
        # [EN] a failure. => The strip keeps only what a human should know (bodies starting `→ `).
        # [EN] ⚠ Lines **without** the prefix (the Go launcher's) still take the strip: old format,
        # [EN] one line per step ("version / platform / preparing runtime").
        if _src and not _judge.lstrip().startswith('→ '):
            self._console_write(line)
            self._n_detail += 1
            return
        self._n_strip += 1
        self.ticker = _judge if _src else line
        self.tick_pos = 0
        # ★ 主程序的进度行（`→ …`，见 `app_flet._splash_note`）一出现就开始计时。
        #   不按"某一句话"匹配（文案以后会改），按**是谁写的** —— 启动器自己的行
        #   都以时间戳 / 中文动词开头，只有主程序那一路统一以 `→ ` 打头。
        # [EN] Start the clock as soon as the main program's progress line (`→ …`, see
        # [EN] `app_flet._splash_note`) shows up. Match by **who wrote it**, not by a sentence:
        # [EN] launcher lines start with a timestamp / a verb, only the main program uses `→ `.
        # ⚠ 判**剥掉前缀的正文**：带上 `[时间][来源]` 之后 `startswith('→ ')` 永远为假，
        #   计时器就再也不启动 —— 消息条前面那个"12s ·"从此消失，而没有任何报错。
        # [EN] ⚠ Judge the **body**: with `[time][source]` in front, `startswith('→ ')` is always
        # [EN] false and the clock never starts -- the "12s ·" prefix vanishes without any error.
        if self.boot_t0 is None and _judge.lstrip().startswith('→ '):
            self.boot_t0 = time.time()
        self._parse_steps(_judge if _src else line)
        self._console_write(line)
        bad = any(k in _judge for k in ('✗', '失败', 'ERROR', 'Error', 'Traceback'))
        try:
            self.canvas.itemconfigure(self._msg_id, fill=(ERR if bad else INK))
        except Exception:                                # noqa: BLE001
            pass

    @staticmethod
    def _ellipsize(txt: str, cols: int) -> str:
        """把一行压到 `cols` 个字以内：**中间省略**（`前面…后面`），不是滚动。

        ★★★ 2026-10-23（用户：「有没有更优雅的显示方式」）：原来这里是**横向跑马灯** ——
          文字逐字左移、循环播放。那条路有三个毛病：
            ① 它一直在动，**眼睛会被它勾住**（读的人没法看别的）；
            ② 一句话被切成两半从右往左爬，**每次只能看见片段**；
            ③ 想读清一个字要等一整圈，是 1990 年代状态栏的做法。
          现代做法是**静态一行 + 中间省略**：开头（"正在拉起…"）和结尾（"（2/3）"）
          都在，正是判断当前在干什么时最需要的两段；完整内容用户点开日志就能看到。
        ⚠ 省略号占一个位置，所以"前面"多留一点（3/5）：句首通常比句尾更有信息量。
        [EN] Compress a line into `cols` characters with a **middle ellipsis**, never a ticker.
        [EN] ★★★ 2026-10-23 (user: "is there a more elegant way"): this used to be a **horizontal
        [EN] ticker** -- text crawling left on a loop. Three problems: ① it never stops moving and
        [EN] **captures the eye**; ② a sentence is cut in half and keeps climbing, so only fragments
        [EN] are ever visible; ③ reading one character takes a full cycle. Modern practice is a
        [EN] **static line with a middle ellipsis**: the head ("starting…") and the tail ("(2/3)")
        [EN] both survive -- the two parts that matter for "what is it doing now" -- and the full
        [EN] text is one click away in the log.
        [EN] ⚠ The ellipsis costs one slot, so give the head more (3/5): sentence starts carry more.
        """
        if cols <= 0:
            return ''
        if len(txt) <= cols:
            return txt
        if cols <= 4:
            return txt[:cols]
        head = (cols - 1) * 3 // 5
        tail = cols - 1 - head
        return txt[:head] + '…' + (txt[-tail:] if tail > 0 else '')

    def _tick(self) -> None:
        if self.closed:
            return
        try:
            txt = self.ticker or '准备中…'
            # ★ 等待期间在**最前面**加一个每秒都在走的秒数（`12s · …`）。
            #   这是全窗口唯一"在动"的东西 —— 一行字十几秒不变会被读成卡死。
            # [EN] While waiting, prefix a seconds counter that moves every second (`12s · …`).
            # [EN] This is the only moving thing on the window -- a line frozen for ten seconds
            # [EN] reads as a hang.
            if self.boot_t0 is not None and not self.failed:
                txt = f'{int(time.time() - self.boot_t0)}s · ' + txt
            cols = self._msg_cols()          # ★ 按像素实测（见 `_msg_cols`），不再用常量
            # [EN] ★ measured in pixels (see `_msg_cols`), not the constant any more
            self.canvas.itemconfigure(self._msg_id, text=self._ellipsize(txt, cols))
        except Exception:                                # noqa: BLE001
            return
        self.root.after(TICK_MS, self._tick)

    # ── 三家服务的步骤点（2026-10-23 用户：「三家服务画成步骤点」）────────
    def _parse_steps(self, line: str) -> None:
        """从主程序的进度行里认出"第几家、什么状态"，只认 `→ ` 打头的行。

        三种句式（`gui/app_flet.py` 的 `_one` 里写的，**改文案要同步改这里**）：
          · `正在拉起 PlotPilot（2/3）…`  ⇒ 第 2 家**进行中**
          · `PlotPilot 已就绪（2/3）`      ⇒ 第 2 家**就绪**
          · `PlotPilot 没起来（2/3）`      ⇒ 第 2 家**失败**
        ⚠ 只按 `（i/n）` 里的数字定位，**不按名字**：名字以后可能改，
          而 `i/n` 是双方约定的"第几家"。名字变了这条照样工作。
        ⚠ 认不出就**什么都不做**（不猜）—— 猜错会把一步点错色，比没有更误导。
        [EN] Recognise "which service, what state" from the main program's progress line (only
        [EN] lines starting with `→ `). Three shapes, written in `gui/app_flet.py::_one`
        [EN] (**change this parser when that copy changes**). ⚠ Located by the `(i/n)` number, not
        [EN] by name: names may change, `i/n` is the agreed "which one". ⚠ When it cannot tell, it
        [EN] does **nothing** -- a wrong colour is worse than no colour.
        """
        # ⚠ 先剥 `[时间][来源]` 前缀：加了统一前缀之后行以 `[` 开头，
        #   直接判会让步骤点**一个都不亮**（三家永远都是"等待中"），而不报任何错。
        # [EN] ⚠ Strip the `[time][source]` prefix first: the line now starts with `[`, and testing
        # [EN] it raw leaves **every dot dark** (all three stuck on "waiting") with no error.
        s = (self._split_prefix(line)[2] or line).lstrip()
        if not s.startswith('→ '):
            return
        m = re.search(r'（(\d+)/(\d+)）', s)
        if not m:
            return
        i, n = int(m.group(1)), int(m.group(2))
        if not (1 <= i <= max(1, n)) or n > 12:            # 明显不是我们那种行，别记
            return
        self._steps_n = n
        if '已就绪' in s:
            self._steps[i] = 'done'
        elif '没起来' in s:
            self._steps[i] = 'fail'
        elif '正在拉起' in s:
            self._steps.setdefault(i, 'run')
        else:
            return
        self._paint_steps()

    def _msg_fill(self) -> str:
        """消息条**此刻的填充色**（从控件读回，不是报常量）。
            English: The strip's **current fill**, read back from the widget (not the constant)."""
        try:
            return str(self.canvas.itemcget(self._msg_id, 'fill') or '')
        except Exception:                                # noqa: BLE001
            return ''

    def _console_vis_rows(self) -> int:
        """日志区**实测能看见几行**（`⚠` 不是 `LOG_ROWS`）。

        ★★★ `LOG_ROWS` 只是"向控件申请几行"，**窗口高度由 `create_window` 钉死**，
        所以"用户真的看见几行"只能量：控件实际高度 ÷ 一行字的行距。
        判据 `L5b` 靠这个数判"更高"到底兑现了没有 —— 报 `LOG_ROWS` 是自问自答
        （把 `LOG_H` 改回 124 而 `LOG_ROWS` 不动，报常量那条判据照样绿）。

        [EN] ★★★ `LOG_ROWS` is only a **request**; the box height is pinned by `create_window`,
        [EN] so "how many rows the user actually sees" must be measured: widget height / line
        spacing. Criterion `L5b` uses this to check that "taller" really happened -- reporting
        `LOG_ROWS` would be asking and answering itself (shrink `LOG_H` back to 124 while leaving
        `LOG_ROWS` alone and the constant-based criterion stays green).
        """
        try:
            if self.console is None:
                return 0
            h = int(self.console.winfo_height() or 0)
            # ⚠ `self.f_mono` 是 `tkfont.Font` 对象 ⇒ 用它的 `metrics()`，
            #   别拿它当字体名去调 `tk.call('font','metrics',...)`（那要的是名字/描述串）。
            # [EN] ⚠ `self.f_mono` is a `tkfont.Font` object -- use its `metrics()`; do not pass it
            # [EN] as a font name to `tk.call('font','metrics',...)`, which wants a name/description.
            lh = int(self.f_mono.metrics('linespace') or 1)
            return max(0, int(h / max(1, lh)))
        except Exception:                                # noqa: BLE001
            return 0

    def _paint_steps(self) -> None:
        """按 `_steps` 重画那一排点（**唯一一处**决定它长什么样）。

        状态 → 画法：
          · 未开始 `○` 中灰空心
          · 进行中 `◍` 金色空心 + 中心一个小实心点（像 iOS 的"正在做"）
          · 就绪   `●` 金色实心
          · 失败   `●` 红实心
        ⚠ 空心与实心必须**同半径**：换半径会让那一排点上下跳一行像素，
          而"跳一下"在静止的画面上非常显眼（比颜色差更显眼）。
        [EN] Redraw the row of dots from `_steps` (**the only place** that decides how it looks).
        [EN] Hollow and solid dots must share a **radius**: changing it makes the row jump a pixel,
        [EN] and a jump is more noticeable than a colour difference on a still image.
        """
        try:
            self.canvas.delete('steps')
        except Exception:                                # noqa: BLE001
            return
        if not self._steps:
            return
        r = 4.0
        gap = 12.0
        x = MSG_LEFT + r
        y = STEPS_Y
        for i in range(1, self._steps_n + 1):
            stt = self._steps.get(i, 'wait')
            try:
                if stt == 'done':
                    self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=GOLD,
                                            outline=GOLD, tags=('steps',))
                elif stt == 'fail':
                    self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=ERR,
                                            outline=ERR, tags=('steps',))
                elif stt == 'run':
                    self.canvas.create_oval(x - r, y - r, x + r, y + r, fill='',
                                            outline=GOLD, width=1.4, tags=('steps',))
                    # 中心小点：半径 1.6（约 40%），读作"进行中"而不是"空的"
                    self.canvas.create_oval(x - 1.6, y - 1.6, x + 1.6, y + 1.6,
                                            fill=GOLD, outline='', tags=('steps',))
                else:
                    self.canvas.create_oval(x - r, y - r, x + r, y + r, fill='',
                                            outline=MUTED, width=1.0, tags=('steps',))
            except Exception:                            # noqa: BLE001
                return
            x += gap * 2
        # 右侧跟一个 `2/3` 小字（比"猜哪个点是谁"有用：用户只需要知道还剩几家）
        # [EN] A small `2/3` after the row -- more useful than guessing which dot is whose.
        done = sum(1 for i in range(1, self._steps_n + 1)
                   if self._steps.get(i) in ('done', 'fail'))
        try:
            self.canvas.create_text(x + 2, y, text=f'{done}/{self._steps_n}',
                                    font=self.f_foot, fill=MUTED, anchor='w',
                                    tags=('steps',))
        except Exception:                                # noqa: BLE001
            pass

    # ── 日志区的两个动作（复制 / 打开文件）─────────────────────────
    def _log_text(self) -> str:
        """日志区里的全部文字（没有控件时退回 `self.lines`）。
            English: All text in the log box (falls back to `self.lines` when there is no widget)."""
        if self.console is not None:
            try:
                return str(self.console.get('1.0', 'end-1c'))
            except Exception:                            # noqa: BLE001
                pass
        return '\n'.join(self.lines)

    def _do_copy(self) -> None:
        """把全部输出复制到剪贴板，并在底栏位置给一句"已复制"的反馈。

        ★ 为什么必须有这个动作：日志的真实用途是**发给别人排查**。
          没有它，用户只能截图 —— 截图里既不能选中也不能搜索，
          而报错的关键那几行往往刚好被截断。
        ⚠ 复制成功/失败都要说一声（剪贴板在个别远程桌面下会失败），
          静默复制等于没复制。
        [EN] Copy all output to the clipboard and confirm at the footer.
        [EN] ★ Why it must exist: a log exists to be **sent to someone else**. Without this the user
        [EN] can only screenshot -- where nothing can be selected or searched, and the one line that
        [EN] matters is often just off the edge. ⚠ Report success and failure: on some remote-desktop
        [EN] setups the clipboard fails, and a silent copy is no copy.
        """
        txt = self._log_text()
        okk = True
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
            self.root.update_idletasks()
        except Exception:                                # noqa: BLE001
            okk = False
        self._flash_footer('已复制全部日志（%d 行）' % len(self.lines) if okk
                           else '复制失败（剪贴板不可用）')

    def _do_open_log(self) -> None:
        """在资源管理器里**定位**到日志文件（不是"打开"—— .log 会被记事本吃掉）。

        ⚠ 用 `explorer /select,` 而不是 `os.startfile(log)`：后者会启动记事本并**锁住**文件，
          而这份文件启动器此刻还在往里写 —— 打开它会让启动器写不进去（Windows 允许共享读，
          但记事本的编码探测会读出一堆替换字符）。定位到文件夹是最不打扰的做法。
        [EN] **Reveal** the log file in Explorer (not "open" it -- .log gets eaten by Notepad).
        [EN] ⚠ `explorer /select,` instead of `os.startfile`: the latter launches Notepad and locks
        [EN] the file, while the launcher is still writing to it. Revealing the folder is the least
        [EN] intrusive option.
        """
        p = str(Path(self.spec.get('log') or '').resolve())
        try:
            if os.name == 'nt':
                subprocess.Popen(['explorer', '/select,', p])
            else:
                subprocess.Popen(['xdg-open', str(Path(p).parent)])
            self._flash_footer('已定位日志文件')
        except Exception as e:                           # noqa: BLE001
            self._flash_footer(f'打不开（{type(e).__name__}）')

    def _flash_footer(self, msg: str, ms: int = 2200) -> None:
        """在底栏位置临时说一句（`ms` 毫秒后恢复原底栏）。
            English: Say one thing at the footer for `ms`, then restore it."""
        try:
            orig = self._foot_text
            self.canvas.itemconfigure(self._foot_id, text=msg, fill=GOLD_DEEP)
        except Exception:                                # noqa: BLE001
            return

        def _back() -> None:
            try:
                self.canvas.itemconfigure(self._foot_id, text=orig, fill=MUTED)
            except Exception:                            # noqa: BLE001
                pass
        try:
            self.root.after(ms, _back)
        except Exception:                                # noqa: BLE001
            pass

    # ── 轮询日志 / ready / fail ──────────────────────────────────
    def _poll(self) -> None:
        if self.closed:
            return
        for ln in self.tail.read():
            self._push(ln)
        fail = self.spec.get('fail') or ''
        if fail and os.path.exists(fail) and not self.failed:
            self.failed = True
            try:
                why = Path(fail).read_text(encoding='utf-8', errors='replace').strip()
            except OSError:
                why = ''
            self._show_failed(why)
        ready = self.spec.get('ready') or ''
        if ready and os.path.exists(ready) and not self.failed:
            self.close()
            return
        self.root.after(POLL_MS, self._poll)

    def _show_failed(self, why: str = '') -> None:
        """进入失败态：**下面那行居中的红字**写原因，**窗口留着不关**，等用户按 ✕。

        ★★★ 2026-10-23（用户：「服务没启动成功不要显示后续启动界面」）：
          这句话在这一侧的实现就是 **`failed` 之后永远不 `close()`** ——
          主程序那边配套"有失败就不写 `ready`"，于是这块窗口一直挡在最上层，
          开始界面看不见。用户要进就走**唯一的出口**：右上角 ✕
          （原因里会明说，否则他只会以为程序卡死了）。
        ★ 文案由**写入方**给完整句子（`fail` 文件的内容）。以前这里硬拼
          `'✘ 启动失败：' + why`，于是主程序想写"创作服务没起来……"时前面会多一截
          跟它对不上的"启动失败"。现在只补一个 `✘`。

        ────────────────────────────────────────────────────────────
        ★★★ 2026-10-27（用户：「启动界面报错的时候为何错误信息是两条」）
        ────────────────────────────────────────────────────────────
          原因**只许出现一次**。改之前这里把同一句话画在**两个** item 上：
            · 消息条（`y=242`）
            · 下面那行红字（`y=H-66`，收起态 `284`）
          收起态这两行只差 42px，上下并排、都是红字、内容一模一样
          ⇒ 用户数出来的就是"两条错误信息"。
          而 Go 启动器那条路更热闹：`failSplash` **既**往日志写 `✗ 原因`
          （进日志区、也顶到消息条）**又**写 `fail` 文件（再到这两处）——
          同一句话最多能出现三个地方。
          ⇒ 现在：消息条只说"启动没成功"（中性色，一句短的，见 `STRIP_FAIL`），
            原因只落在下面那行居中的红字上 —— 那一行**整幅宽**（`_status_cols`
            实测约 74 字），而消息条只有 53 字，长原因放那儿会被砍掉"怎么脱身"
            那半句。
        ⚠ **不自动展开**（用户 2026-10-17：「下面消息框默认收起」）——
          要看全套输出点那个 chevron。
        [EN] Enter the failed state: the **centred red line below** carries the reason, the window
        [EN] **stays open** until the user presses ✕. ★★★ 2026-10-23 (user: "if the services did
        [EN] not start, do not show the following start screen"): on this side that means **never
        [EN] `close()` after `failed`** -- the UI never writes `ready` when something failed, so
        [EN] this window keeps sitting on top and the start screen stays hidden. The single way in
        [EN] is the ✕ (the reason spells it out, or the user would read it as a hang).
        [EN] ★ The text is a **complete sentence supplied by the writer** (the `fail` file). This
        [EN] used to hard-prefix "✘ 启动失败：" so a custom message got a mismatched lead-in.
        [EN] ──────────────────────────────────────────────────────────
        [EN] ★★★ 2026-10-27 (user: "why is the error message two lines when the splash fails?")
        [EN] ──────────────────────────────────────────────────────────
        [EN] The reason must appear **once**. Before, the same sentence was painted on **two**
        [EN] items: the strip (`y=242`) and the red line below (`y=H-66`, i.e. `284` collapsed).
        [EN] Collapsed those are 42px apart, stacked, both red, identical -- which is what the
        [EN] user counted as "two error messages". The Go launcher's path was worse: `failSplash`
        [EN] writes `✗ reason` to the log (log box *and* strip) **and** the `fail` file (both lines
        [EN] again) -- one sentence in up to three places.
        [EN] => Now: the strip only says "启动没成功" (neutral colour, short, see `STRIP_FAIL`),
        [EN] and the reason lives solely on the centred red line -- that line spans the **full
        [EN] width** (~74 chars measured by `_status_cols`) while the strip holds only 53, where a
        [EN] long reason lost exactly the half that explains how to get out.
        [EN] ⚠ **No auto-expand** (user, 2026-10-17) -- use the chevron for the full output.
        """
        self._fail_reason = why
        line = why.strip()
        if line and not line.startswith('✘'):
            line = '✘ ' + line
        try:
            # ① 原因：**唯一一处** —— 下面那行居中的红字（整幅宽，中间省略兜底）。
            # [EN] ① The reason: the **only** place -- the centred red line (full width, middle
            # [EN] ellipsis as the backstop).
            self.canvas.itemconfigure(
                self._status_id,
                # ⚠ 上限取**两行**（`2 × _status_cols`）：一行放不下就折行，
                #   再长才用中间省略（那时它是"超长异常文本"，折三行会压到底栏）。
                # [EN] ⚠ The cap is **two lines** (`2 x _status_cols`): wrap when one line is not
                # [EN] enough, and only fall back to a middle ellipsis beyond that (by then it is
                # [EN] "pathologically long", and three lines would reach the footer).
                text=self._ellipsize(line or STATUS_FAIL_FALLBACK,
                                     self._status_cols() * 2))
            # ② 消息条：只说"没成"，**不抄原因**（抄了就是用户报的那两条）。
            #   ⚠ 必须**显式**写：Go 那条路已经把 `✗ 原因` 写进过日志，消息条上
            #     此刻正是那句话 —— 只"不写"并不会把它换掉。
            #   ⚠ 颜色回到中性（`INK`）：屏幕上只留**一条**红字。
            # [EN] ② The strip: only "did not make it", **no copy of the reason** (copying it is
            # [EN] exactly the two lines the user reported). ⚠ It must be written **explicitly**:
            # [EN] on the Go path `✗ reason` already went through the log, and that is what the
            # [EN] strip is showing right now -- merely "not writing" would leave it there.
            # [EN] ⚠ Colour back to neutral (`INK`): only **one** red line on the screen.
            self.ticker = STRIP_FAIL
            self.tick_pos = 0
            self.canvas.itemconfigure(self._msg_id, fill=INK)
            self.canvas.itemconfigure(
                self._msg_id, text=self._ellipsize(STRIP_FAIL, self._msg_cols()))
        except Exception:                                # noqa: BLE001
            pass

    def close(self) -> None:
        """关掉窗口，并**留个记号**（`spec['bye']`）告诉主程序"我走了"。

        ★★★ 2026-10-24（用户：「所有服务拉起来再打开开始界面，在这之前不要打开」）：
          主窗口现在在服务就绪前是**真的不可见**的（不是被盖住）。于是"失败时用户
          点 ✕"这条路必须有人通知主程序 —— 否则 splash 一关，屏幕上什么都没有，
          用户只会以为程序崩了。**这个文件就是那个通知**。
        ⚠ 写失败也算关掉了（`close()` 绝不能因为写不了文件而卡住窗口）：
          主程序那边有 1 小时的兜底上限，且拿不到路径时立刻自己放行。
        [EN] Close the window and **leave a mark** (`spec['bye']`) so the main program knows.
        [EN] ★★★ 2026-10-24: the main window is now **really invisible** until the services are
        [EN] ready (not merely covered), so the "user presses the cross on failure" path needs
        [EN] someone to tell the UI -- otherwise closing the splash leaves an empty screen and the
        [EN] user reads it as a crash. **This file is that notice.**
        [EN] ⚠ A failed write still closes (never hang the window over a file): the UI side has a
        [EN] one-hour backstop and releases itself immediately when the path is absent.
        """
        self.closed = True
        bye = (self.spec.get('bye') or '').strip()
        if bye:
            try:
                p = Path(bye)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('bye\n', encoding='utf-8')
            except OSError:
                pass
        try:
            self.root.destroy()
        except Exception:                                # noqa: BLE001
            pass

    # ── 自检（给判据用）──────────────────────────────────────────
    def _txt(self, item) -> str:
        """安全地取一个 canvas 文字项的文本（项不存在 / 已被销毁 ⇒ 空串）。

        ★ 为什么要单独包一层：底栏与消息条是**两个**独立的事实，
          其中一个取不到不能把另一个也带成空 —— 判据要能分清"哪个没了"。

            English:
        Safely read a canvas text item (empty string when the item is gone).
        ★ Why wrap it: the footer and the strip are **two** separate facts; one of them failing
        must not blank the other -- the judges need to tell which one is missing.
        """
        try:
            return str(self.canvas.itemcget(item, 'text') or '')
        except Exception:                                # noqa: BLE001
            return ''

    def summary(self) -> dict:
        """把"窗口里有什么"记成可断言的事实（判据不读图）。
            English: Record "what the window contains" as assertable facts (judges don't read images)."""
        try:
            has_close = bool(self.canvas.find_withtag('close'))
            has_detail = bool(self.canvas.find_withtag('detail'))
            foot = self._txt(self._foot_id)
            msg = self._txt(self._msg_id)
            # ★★★ 2026-10-27：失败那一行（`_status_id`）的**实测文字**也要报出来 ——
            #   "原因只出现一次"这条判据必须能同时读到**消息条**和**那行红字**，
            #   只报 `msg` 的话，"把原因抄到消息条上"这个回归根本测不出来。
            # [EN] ★★★ 2026-10-27: the failure line's **measured text** must be reported too --
            # [EN] the criterion "the reason appears once" has to read both the strip and that red
            # [EN] line; reporting only `msg` would make a regression that copies the reason onto
            # [EN] the strip undetectable.
            fail_line = self._txt(self._status_id)
            fail_line_fill = ''
            try:
                fail_line_fill = str(self.canvas.itemcget(self._status_id, 'fill') or '')
            except Exception:                            # noqa: BLE001
                pass
            # ⚠ 三个**实测外框**（`canvas.bbox`，含折行后的真实高度）：
            #   "长原因折两行会不会压到消息条 / 底栏"只有量这个才判得出 ——
            #   报"折了几行"是自问自答（数 `text` 里的换行对**自动折行**无效：
            #   Tk 折行不会往 `text` 里插 `\n`）。
            # [EN] ⚠ Three **measured boxes** (`canvas.bbox`, including the real height after
            # [EN] wrapping): "does a two-line reason collide with the strip / footer" can only be
            # [EN] judged from these -- reporting "how many lines" would be circular (counting `\n`
            # in `text` does not work: Tk's wrapping inserts no newline into `text`).
            def _box(item):
                try:
                    return [int(round(v)) for v in self.canvas.bbox(item)]
                except Exception:                        # noqa: BLE001
                    return []
            fail_line_box = _box(self._status_id)
            msg_box = _box(self._msg_id)
            foot_box = _box(self._foot_id)
            # 用户 2026-10-17 来回三轮：先「消息部分还是加上边框吧，否则看不出来」→
            # 「可以去掉消息框的背景颜色了」→ **「消息栏和版本号把边框去掉」**。
            # ⇒ 现在的正确形态是**一个矩形都没有**（消息条与底栏都是干干净净一行字），
            #   这里把矩形数与它们的填充/描边一起报出来给判据看。
            # [EN] The user went back and forth three times on 2026-10-17: first "put a border on
            # [EN] the message strip, it's invisible otherwise", then "the strip's background
            # [EN] colour can go", then **"drop the border from the strip and the version line"**.
            # ⇒ The correct shape now is **no rectangles at all** (strip and footer are just text);
            # [EN] report the rectangle count plus their fills/outlines for the judges.
            rects = [i for i in self.canvas.find_all()
                     if self.canvas.type(i) == 'rectangle']
            borders = len(rects)
            # 矩形的**填充色**（用户 2026-10-17：「可以去掉消息框的背景颜色了 …
            # 下面的版本信息颜色也可以去掉了」⇒ 这里必须全是空的）。
            # [EN] The rectangles' **fill colour** (user, 2026-10-17: "the strip's background
            # [EN] colour can go ... the version line's too" ⇒ all of these must be empty).
            fills = [str(self.canvas.itemcget(i, 'fill') or '') for i in rects]
            # 描边颜色（"去掉背景色"≠"连边框一起去掉" ⇒ 两半都要报出来给判据看）。
            # [EN] Outline colour ("drop the background" ≠ "drop the border too" ⇒ both halves get
            # [EN] reported).
            strokes = [str(self.canvas.itemcget(i, 'outline') or '') for i in rects]
            # 展开按钮的**形状与笔画宽度**（2026-10-23：实心多边形 → 描边 chevron）。
            # ★ 判据不能读图，所以这里必须把"是线还是多边形"如实报出来 ——
            #   否则"又改回实心三角"这件事在摘要里完全看不见。
            # [EN] The expand button's **shape and stroke width** (2026-10-23: filled polygon ->
            # [EN] stroked chevron). ★ Judges cannot read images, so "line or polygon" must be
            # [EN] reported verbatim -- otherwise "reverted to a solid triangle" is invisible here.
            _det = self.canvas.find_withtag('detail')
            _shape = str(self.canvas.type(_det[0])) if _det else ''
            try:
                _dwidth = float(self.canvas.itemcget(_det[0], 'width')) if _det else 0.0
            except Exception:                            # noqa: BLE001
                # 位图版没有 `width` 这一项 ⇒ 报**设计**上的线宽（2.0），而不是 0。
                # ⚠ 报 0 会让判据以为"线宽不对"，那是**测量失真**，不是产品坏。
                # [EN] Bitmaps have no `width` item option => report the **design** stroke width
                # [EN] (2.0) rather than 0. ⚠ Reporting 0 makes the criterion think the width is
                # [EN] wrong, which is a **measurement artefact**, not a product defect.
                _dwidth = 2.0
        except Exception:                                # noqa: BLE001
            has_close = has_detail = False
            foot = msg = ''
            fail_line = fail_line_fill = ''
            fail_line_box = msg_box = foot_box = []
            borders = 0
            fills = []
            strokes = []
            _shape = ''
            _dwidth = 0.0
        return {
            'title': self.spec.get('title'),
            'subtitle': self.spec.get('subtitle'),
            'bg_loaded': self.bg_img is not None,
            'logo_loaded': self.logo_img is not None,
            # 成对用：框可以没有，**字不能没有**（`msg` = 消息条那一行）。
            # [EN] For the paired criterion: the frame may go, the **text must not** (`msg` = the
            # [EN] strip's line).
            'msg': msg,
            # 标题是**按哪份字体文件**画的（'' = 回落到系统族名）—— 必须与开始界面同一份。
            # [EN] **Which font file** the title was drawn from ('' = fell back to a family name) --
            # [EN] it must be the same file the start screen uses.
            'title_font': str(self._font_file or ''),
            'title_mode': self._title_mode,
            'footer': foot,
            'has_console': self.console is not None,
            'has_close': has_close,
            'has_detail': has_detail,
            # 三角**朝哪边**（`right` = 收起 / `down` = 展开）。
            # ★ 2026-10-21 用户点名要的行为，必须能被判据读到 —— 否则"三角画反了"
            #   （收起画成向下）在界面上看不出来，只有用户会觉得别扭。
            # [EN] Which way the triangle points (`right` = collapsed / `down` = expanded).
            # [EN] A behaviour the user named, so a judge must be able to read it -- otherwise a
            # [EN] flipped triangle (down while collapsed) ships unnoticed.
            'detail_glyph': getattr(self, '_detail_glyph', ''),
            # ── 2026-10-23：展开按钮"长什么样"也要能被判据读到 ──
            #   用户这次只说"不好看"，而"好看"没法直接量 ⇒ 把它拆成**能数的性质**：
            #   形状（线 / 填充多边形）、笔画宽度、悬停时的颜色、命中区大小。
            #   判据据此钉住"是描边 chevron、不是实心三角"与"悬停只变前景、不添色块"。
            # [EN] ── 2026-10-23: what the expand button **looks like** must be readable too ──
            # [EN] The user only said "ugly", and "good-looking" cannot be measured directly, so it
            # [EN] is broken into **countable properties**: shape (line / filled polygon), stroke
            # [EN] width, hover colour, hit-box size. The criteria pin "stroked chevron, not a solid
            # [EN] triangle" and "hover changes the foreground only, no added patch".
            'detail_shape': _shape,
            # ★ 设计语义 vs 实现方式，**必须分开报**：
            #   `detail_style` = 'chevron'（描边折线）/ 'solid'（实心三角）—— **判据守这个**；
            #   `detail_shape` = 'image' / 'line' / 'polygon' —— 只是"怎么画出来的"。
            #   把两者合成一个字段，就会让"换成抗锯齿位图"这种纯改善也把判据判红。
            # [EN] ★ Design semantics vs implementation, **reported separately**:
            # [EN] `detail_style` = 'chevron' (stroked polyline) / 'solid' (filled triangle) --
            # [EN] **this is what the criterion guards**; `detail_shape` = 'image' / 'line' /
            # [EN] 'polygon' is merely "how it was drawn". Merging them would make a pure improvement
            # [EN] (switching to anti-aliased bitmaps) turn the criterion red.
            'detail_style': str(getattr(self, '_detail_style', '')),
            'detail_width': _dwidth,
            'detail_hit': int(getattr(self, '_caret_hit', 0) or 0),
            # ⚠ 报**目标角**而不是"此刻的角"：后者在切换时是个中间帧（动画中途），
            #   拿它做断言会 flaky。方向本身由 `detail_glyph` 表达，这里给角度是为了
            #   让"真的是转过去的（同一形状 -90°→0°）"这件事能被数出来。
            # [EN] ⚠ Report the **target** angle, not "the angle right now": the latter is a
            # [EN] mid-frame during the tween and asserting on it is flaky. Direction is expressed
            # [EN] by `detail_glyph`; the angle is here so that "it really turned (same shape,
            # [EN] -90 -> 0)" is countable.
            'detail_deg_target': round(self._caret_target_deg(), 1),
            'detail_deg_now': round(float(getattr(self, '_caret_deg', 0.0)), 1),
            'detail_hover_fill': GOLD_DEEP,
            'detail_rest_fill': GOLD,
            # 消息条一行实测能放几个字（写死的 74 会让文字画到按钮底下并伸出窗口）
            # [EN] How many characters actually fit on the strip line (a hard-coded 74 ran the text
            # [EN] under the button and off the window)
            'msg_cols': self._msg_cols(),
            'borders': borders,
            'fills': fills,
            'strokes': strokes,
            'size': [W, H_EXP if self.expanded else H_BASE],
            'lines': len(self.lines),
            # ── 2026-10-23：等创作服务期间那个"秒数心跳" ──
            #   ★ 报**两样**：有没有开始计时（`boot_clock`）、此刻的消息条文字（`msg` 已在上）。
            #     判据靠"两次不同时长读到的 `msg` 秒数不一样且在涨"来判"真的在走"，
            #     只判"文字里有个数字"会被写死的 `0s` 骗过。
            # [EN] ── 2026-10-23: the seconds heartbeat while waiting for the services ──
            # [EN] ★ Report both: whether the clock started (`boot_clock`) and the strip's current
            # [EN] text (`msg`, above). The criterion compares two reads at different holds and
            # [EN] requires the seconds to differ and grow -- "there is a digit" would be fooled by
            # [EN] a hard-coded `0s`.
            'boot_clock': self.boot_t0 is not None,
            'boot_secs': (int(time.time() - self.boot_t0)
                          if self.boot_t0 is not None else -1),
            # ── 2026-10-23：失败态与"深色日志"也要能被判据读到 ──
            #   ⚠ 判据不能读图，所以"日志区是不是黑的"必须汇报**实测颜色**
            #     （从 `tk.Text` 读回 `bg`/`fg`，而不是报常量 —— 报常量等于自问自答）。
            # [EN] ── 2026-10-23: the failed state and the "dark log" must be readable by judges ──
            # [EN] ⚠ Judges cannot read images, so "is the log dark" reports the **measured**
            # [EN] colours read back from the `tk.Text` widget (not the constants -- that would be
            # [EN] asking and answering itself).
            'failed': bool(self.failed),
            'fail_reason': self._fail_reason,
            # 失败那一行（居中红字）的实测文字与颜色 —— 判"原因只有一处"要用。
            # [EN] The failure line's measured text and colour -- needed to judge "one place only".
            'fail_line': fail_line,
            'fail_line_fill': fail_line_fill,
            'fail_line_box': fail_line_box,
            'msg_box': msg_box,
            'foot_box': foot_box,
            'console_bg': self._console_opt('bg'),
            'console_fg': self._console_opt('fg'),
            'caret_px': int(getattr(self, '_detail_px', 0) or 0),
            'caret_hit': int(getattr(self, '_caret_hit', 0) or 0),
            'caret_w': float(getattr(self, '_caret_w', 0.0) or 0.0),
            # ── 2026-10-23 晚（"更优雅的展开"这一轮）──────────────────
            #   ★ 位置与"翻上去有没有被抢"这两件事，只有**读窗口本身**才量得到：
            #     窗口在哪由 `winfo_rootx/y` 说，滚到哪由 `yview()` 说。
            # [EN] ── 2026-10-23 evening ("a more elegant expand") ──
            # [EN] ★ Position and "did scrolling get stolen" can only be measured by reading the
            # [EN] window itself: `winfo_rootx/y` for where it is, `yview()` for where it is scrolled.
            'win_xy': self._win_xy(),
            'msg_full_len': len(self.ticker or ''),
            'steps': dict(self._steps),
            'steps_n': int(self._steps_n),
            'steps_items': len(self.canvas.find_withtag('steps')),
            # ── 2026-10-27：日志分流（服务细节 vs 进度行）──
            #   ⚠ 报**实测**的：消息条的**当前填充色**（判据靠它判"细节行里的
            #     `ERROR` 有没有把消息条念红"），以及两个计数器。
            #     报常量等于自问自答（上一轮 `console_bg` 就吃过这个亏）。
            # [EN] ── 2026-10-27: the log split (service detail vs progress) ──
            # [EN] ⚠ Report what was **measured**: the strip's **current fill** (so a judge can tell
            # [EN] whether an `ERROR` inside a detail line turned it red), plus the two counters.
            # [EN] Reporting the constant would be asking and answering itself (the `console_bg`
            # [EN] lesson from the previous round).
            'msg_fill': self._msg_fill(),
            'n_detail': int(self._n_detail),
            'n_strip': int(self._n_strip),
            'console_rows': int(LOG_ROWS),
            'console_box': [LOG_BOX_TOP, LOG_H],
            # ⚠ 同上：报**实测**的可见行数（`_console_vis_rows` 从控件量），
            #   不是把 `LOG_ROWS` 再报一遍。
            # [EN] ⚠ Same again: report the **measured** visible rows (measured off the widget by
            # [EN] `_console_vis_rows`), not `LOG_ROWS` a second time.
            'console_vis_rows': self._console_vis_rows(),
            # ⚠ 不能用 `canvas.gettags('logtool')`：那个参数要的是 **item id**，
            #   传标签名返回的东西没有定义（第一次就只拿到 'copy' 一个，看着像
            #   "打开文件的按钮没画出来"—— 实际是两个都画了）。必须先 `find_withtag`。
            # [EN] ⚠ `canvas.gettags('logtool')` is wrong: its argument is an **item id**, and
            # passing a tag name returns something undefined (the first run only reported 'copy',
            # which looks like "the reveal button was never drawn"). Go through `find_withtag`.
            'logtools': sorted({t for _i in self.canvas.find_withtag('logtool')
                                for t in self.canvas.gettags(_i)
                                if t in ('copy', 'open')}) if self.expanded else [],
            'console_last_yview': self._last_yview,
            'new_badge': self._new_lines,
            'origin': list(self._pos()),
            'scroll_probe': self._probe,
        }

    def _win_xy(self) -> list:
        """窗口此刻的屏幕坐标（读不到就 `[]`）。
            English: The window's current screen position (`[]` when unreadable)."""
        try:
            self.root.update_idletasks()
            return [int(self.root.winfo_rootx()), int(self.root.winfo_rooty())]
        except Exception:                                # noqa: BLE001
            return []

    def _console_opt(self, name: str) -> str:
        """从真控件读回一个颜色（没有控件 / 读不到 ⇒ 空串）。
            English: Read one colour back from the real widget (empty when absent/unreadable)."""
        if self.console is None:
            return ''
        try:
            return str(self.console.cget(name) or '')
        except Exception:                                # noqa: BLE001
            return ''


def main(argv: list[str]) -> int:
    spec_path = ''
    out_path = ''
    from_end = True
    expanded = False
    #: `--selftest-hold <秒>`：自检时**先让窗口真的跑这么久**再读摘要。
    #:
    #: ★ 为什么需要它（2026-10-23）：要验的是"等待期间那个秒数真的在走"，
    #:   而"走没走"只能靠**两个不同时刻**的读数比出来。建完窗口立刻读，
    #:   读到的永远是 `0s` —— 那种判据写死的常量也能过（假绿）。
    # [EN] `--selftest-hold <sec>`: let the window actually run that long before reading the
    # [EN] summary. ★ Why: "the seconds counter really ticks" can only be proven by comparing two
    # [EN] reads at different moments; reading immediately always yields `0s`, which a hard-coded
    # [EN] constant would also satisfy (a false green).
    hold = 0.0
    #: `--selftest-probe scroll`：在读摘要之前跑一次"滚动探针"（见 `Splash._probe_scroll`）。
    #: [EN] `--selftest-probe scroll`: run the scroll probe right before reading the summary.
    probe = ''
    for i, a in enumerate(argv):
        if a == '--spec' and i + 1 < len(argv):
            spec_path = argv[i + 1]
        elif a == '--selftest' and i + 1 < len(argv):
            out_path = argv[i + 1]
        elif a == '--selftest-probe' and i + 1 < len(argv):
            probe = argv[i + 1]
        elif a == '--selftest-hold' and i + 1 < len(argv):
            try:
                hold = max(0.0, min(60.0, float(argv[i + 1])))
            except (TypeError, ValueError):
                hold = 0.0
        elif a == '--from-end' and i + 1 < len(argv):
            from_end = argv[i + 1] not in ('0', 'false', 'no')
        elif a == '--expanded':
            expanded = True
    if not spec_path:
        print('缺少 --spec', file=sys.stderr)
        return 2
    try:
        spec = json.loads(Path(spec_path).read_text(encoding='utf-8'))
    except Exception as e:                               # noqa: BLE001
        print(f'读不了 spec：{e!r}', file=sys.stderr)
        return 2

    _dpi_aware()
    _register_bundled_fonts(spec)
    root = tk.Tk()
    root.title(spec.get('title') or '小说世界 AI 模拟')
    root.overrideredirect(True)          # 无边框：像 splash，不像"又一个窗口"
    root.attributes('-topmost', True)
    root.configure(bg=PAPER)
    splash = Splash(root, spec, from_end=from_end)
    if expanded:
        # 仅测试/截图用；正常启动是收起的。
        # ⚠ `animate=False`：自检紧接着就读摘要，动画会留下中间帧（见 `toggle`）。
        # [EN] Test/screenshot only; a real launch starts collapsed.
        # [EN] ⚠ `animate=False`: the self-test reads the summary immediately and the tween would
        # [EN] leave a mid-frame behind (see `toggle`).
        splash.toggle(animate=False)

    if out_path:                          # 自检：建完就记摘要、退出（不挡判据）
        def _dump() -> None:
            try:
                data = splash.summary()
                Path(out_path).write_text(
                    json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
            finally:
                splash.close()
                try:
                    root.quit()
                except Exception:                        # noqa: BLE001
                    pass

        if hold > 0:
            # ★ 让窗口**真的跑** `hold` 秒：`after` 的轮询、`_tick` 全在跑，
            #   外部脚本可以在这段时间里往日志里写进度行。
            # [EN] Let the window **actually run** for `hold` seconds: `after` polling and
            # [EN] `_tick` are live, so an external script can append progress lines meanwhile.
            if probe == 'scroll':
                # 探针在**读摘要之前**跑（`hold` 到期前 0.4 秒），这样它的结果已经写好了。
                # [EN] The probe runs **before** the summary is read (0.4s before `hold` expires),
                # [EN] so its result is already in place.
                root.after(max(1, int(hold * 1000) - 400), splash._probe_scroll)
            root.after(int(hold * 1000), _dump)
            root.mainloop()
        else:
            if probe == 'scroll':
                splash._probe_scroll()
            _dump()
        return 0

    root.bind('<Escape>', lambda e: splash.close())
    root.lift()
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
