# -*- coding: utf-8 -*-
"""把一幅画（或一截长卷）做成启动窗口（splash）的底图。

三代做法的来龙去脉（别再把其中两代混着用）
==========================================
1. `make_splash_bg.py`（2026-10-17）：从母版 `title_bg.webp` 上滑窗挑"最平"的一块。
   对"别花"是对的，但代价是**画上什么都没有**。
2. 本文件的上一版（2026-10-24 上午）：拿一张 AI 生成的淡墨山水，**整张**缩放，
   只校色、只在字下兜下限。用户评价：「整幅画内容多一些」。
3. 本版（2026-10-24 中午）：「**用富春山居图核心部分**」。
   富春山居图是 33 × 636 cm 的手卷（长宽比 19:1），**没法整幅放进 860 宽的窗口** ——
   所以"取核心一段"不是妥协，是这个画种唯一能进窗口的方式。
   取段仍然要讲规矩，所以下面每一步都是**量出来的**，不是挑出来的：

   · **取哪一段**（横向）：在整卷上滑动窗口，按"边缘能量 + 墨迹覆盖"打分取最高的一段
     （`_pick_section`）。分数写进报告，删掉任何一条都能复现。
   · **留多少天**（纵向）：手卷的上半常是空天，直接放进来山脊会落在收起态窗口的 2/3 处
     —— 收起时看到的大半是空天。所以纵向也试 6 档（裁掉 0 / 6% / 12% / 18% / 24% / 30% 的天空），
     和横向一起按分数挑，**不单独解某一行**。
   · **裁掉扫描与装裱的边带**：这一卷的上下各有一条"压暗 + 平"的边（拍照产物），
     底部还有一条装裱的空白纸 —— 它们在窗口最下面就是一条浅色带。按"最后一行还有笔触"裁掉。
   · **怎么上色**：只校色。源图的纸（实测 rgb 203/189/180）映射到本项目的纸 `PAPER`，
     暗部过一条 gamma 曲线（源图最暗 59，直接搬过来是黑点）。
   · **怎么让字看得清**：只在 `TEXT_BANDS` 的**逐处横纵范围**里兜一个下限（羽化，不留矩形），
     遮罩外一个像素都不动。

三条硬约束（`measure()` 报出来，判据也读这份）
--------------------------------------------
1. **画是真的满**：可见区里"有墨"的像素占比 ≥ `INK_MIN`（这一条就是"内容多一些"的可数版本）。
2. **不影响组件**：每处文字带（自己的范围）最暗 ≥ `TEXT_MIN`、std ≤ `TEXT_STD_MAX`。
3. **收起态与展开态是同一张画**：下方补的纸 + 画的上下两截连着（`E5c-6` 另判）。

跑法：
    .venv\\Scripts\\python.exe tools\\make_splash_art.py --apply                 # 自动取段
    .venv\\Scripts\\python.exe tools\\make_splash_art.py --section 800            # 指定起点
    .venv\\Scripts\\python.exe tools\\make_splash_art.py --src <别的画>           # 换画

English:
Turn a painting (or a stretch of a handscroll) into the splash backdrop.
Three generations, do not mix them: (1) `make_splash_bg.py` slid a window over the master and picked
the *flattest* patch -- right for "not busy", but it ended as empty paper. (2) The morning version
of this file scaled an AI-generated pale landscape **whole**, matching tone only. The user's verdict:
"the whole picture should have more content". (3) This version: "**use the core section of Dwelling
in the Fuchun Mountains**". That painting is a 33 x 636 cm handscroll (aspect ~19:1) and **cannot be
shown whole in an 860px window** -- so taking the core stretch is not a compromise, it is the only way
a handscroll enters a window. The choice is still measured, not eyeballed: a 4x3 grid score
(mean + worst cell) sliding across the scroll at 1/5 size, trying six vertical trims
(0/6/12/18/24/30% of the sky) -- scoring at source resolution rewards fine strokes that vanish once
shrunk. The scan's edge falloff and the mounting's blank paper are trimmed too (they read as a light
band at the window edge), using "the last row that still has brushwork".
Tone is matched only (source paper rgb 203/189/180 -> PAPER) with a gamma shoulder. Text
stays readable through a per-region floor (feathered, no rectangles). Three hard constraints: the
picture is genuinely dense (ink coverage >= INK_MIN, the countable version of "more content"), the
text regions stay safe, and the collapsed/expanded states are the same painting.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / 'assets' / 'images'
#: 原图默认放这里（`developers/` **不进发布包**，所以 2MB 的原图不会带给用户）。
# [EN] Default source (`developers/` is **excluded from the release**, so the 2MB original never
# [EN] ships). Replace this file or point `--src` elsewhere to change the painting.
SRC_DEFAULT = ROOT / 'developers' / 'refs' / 'splash_art_classical_src.png'
OUT_TALL = IMG / 'title_bg_splash_tall.png'
OUT_BASE = IMG / 'title_bg_splash.png'
REPORT = ROOT / 'assets' / 'screenshots' / 'splash_art_report.json'

#: 取图方式：`whole` = **整张等比缩放**（不裁、不挑段、不搬东西）。
#:
#: ★★★ 2026-10-24 12:59，用户第三次把口径拧回来：「**就这个吧 不要用截取 用缩放
#:   缩放到启动界面大小作为背景图**」，并点名了那幅 AI 水墨山水原图的路径。
#:   前两轮我做的都是 `section`（从长卷滑窗取一段）—— 那是手卷能进窗口的唯一办法，
#:   但用户现在要的是"整张都在"，哪怕收起态只看得到上半截的天空。
#:   ⇒ `whole` 下**三件事全部不做**：不裁扫描边带（裁也是截取）、不挑段、不搬折枝。
#:     只做校色 + 等比缩放 + 下面补纸（纸是同一个纸色，接缝淡化 14 行）。
#: [EN] How the picture is taken: `whole` = **scale the entire image uniformly** (no crop, no
#: [EN] section picking, nothing relocated). ★★★ 2026-10-24 12:59, the user turned the yardstick
#: [EN] back for the third time: "just this one -- **do not crop, scale it**, scale it to the splash
#: [EN] size as the background", naming that AI ink landscape. The previous two rounds used
#: [EN] `section` (slide a window across the handscroll), the only way a scroll fits a window -- but
#: [EN] now he wants the whole picture there, even if the collapsed view only shows the upper half.
#: [EN] => Under `whole` three things are simply not done: no scan-edge trim (trimming is still
#: [EN] cropping), no section picking, no branch relocation. Only tone matching, uniform scaling, and
#: [EN] paper filled below (same paper colour, 14-row faded seam).
FIT = 'whole'
#: 要不要画那枚朱印。**False** = 不画（2026-10-24 用户认定它像"一个 AI 生成的字"）。
#: 见 `build()` 第 ⑦ 步那段注释：它是**唯一**能找到的那块孤立暗物。
# [EN] Whether to draw the vermilion seal. **False** = no seal (2026-10-24: the user identified it
# [EN] as "an AI-generated character"). See step 7 in `build()` -- it is the only isolated dark blob
# [EN] in the output.
SEAL = False
#: 缩放后的画高（`whole` 模式里由源图长宽比算出，见 `build`）。
# [EN] Height of the scaled picture (derived from the source aspect in `build`, `whole` mode only).
W = 860
#: ★★★ 2026-10-27（用户：「启动界面的日志窗口展开我想更长一些 也更高一些」）：620 → **820**。
#:   加高的这 200px **全是补纸**（画本身 487 高一格没动，见 `build` ③ 的 `whole` 等比缩放），
#:   而它在窗口里几乎全被那块**深色日志区**盖住 —— 用户要多看日志，不是要多看画。
#:   ★★★ 同一天**第二轮**，用户又说「日志框**又太高了**，高度减少 50% 宽度不变」
#:   ⇒ 820 → **602**（= 日志框顶边 274 + 框高 218 + 底部那一截 110，见 `H_EXP` 那个算式）。
#:   ⚠ `H_EXP`（`tools/launcher_splash.py`）必须跟着改，两边是同一个数写在两处
#:   （判据 `E5i` 钉着"底图高度 == 展开态窗口高度"，防止再漂）。
#:   ⚠ 画本身仍是 487 高（整幅等比缩放），602 - 487 = **115 行补的纸**。
# [EN] ★★★ 2026-10-27 (user: "the expanded log window should be longer and taller"): 620 -> **820**.
# [EN] The extra 200px is **all padding paper** (the picture stays 487 tall -- see `whole` uniform
# [EN] scaling in `build` ③), and it sits almost entirely under the **dark log box**: the user wants
# [EN] more log, not more painting. ★★★ **Second round the same day** the user said "the log box is
# [EN] **too tall again**, cut its height by 50%, keep the width" => 820 -> **602** (= box top 274 +
# [EN] box 218 + bottom band 110, see the `H_EXP` expression). ⚠ `H_EXP` in
# [EN] `tools/launcher_splash.py` must move with it -- one number written in two places (criterion
# [EN] `E5i` pins backdrop height == expanded height). ⚠ The painting is still 487 tall (whole-image
# [EN] uniform scaling), so 602 - 487 = **115 rows of padding paper**.
H_TALL = 602
H_BASE = 480              # 收起态**文件**高度（画布只有 350，下部被裁 —— 与老工具一致）
#: 画布收起时真正显示多少行 —— "山脊要落在可见高度的哪儿"要用它算，不能写死 480。
# [EN] How many rows the collapsed canvas actually shows; "where the ridge lands" is computed from
# [EN] it, never the hard-coded 480.
VIS_H = 350

#: 纸色：本项目所有纸面（开始界面 / splash）用的都是这一个暖纸色。
# [EN] Paper colour: the warm paper used by every paper surface in this project.
PAPER = (219, 211, 197)
PAPER_LUM = 0.299 * PAPER[0] + 0.587 * PAPER[1] + 0.114 * PAPER[2]      # 212.0

#: 明度：压缩比与"最暗的下限"。**这两个数决定"画有多暗"**，与"多彩"无关。
#:
#: ★★★ 2026-10-24 中午重构（原来只有一个 `GAMMA`）：逐通道做幂运算会**同时压扁色度**，
#:   于是"浓淡"旋钮是死的 —— 实测 `CHROMA_K` 从 0.42 调到 0.75，彩度几乎不动（21.9 → 22.0）。
#:   拆成"亮度分量 × `LUM_K`（并夹在 `MAX_DARK` 以内）+ 色度分量 × `CHROMA_K`"之后，
#:   两个旋钮各管一件事，才真的能调"有内容而不浓"。
#:   实测（按 `MAX_DARK` 扫）：52 ⇒ 最暗 p1 159（太浓）；44 ⇒ 167；38 ⇒ 173；
#:   **30 ⇒ 180**（定这个）；26 ⇒ 185（开始发灰）。用户要"有内容但不要太浓"，
#:   落点就是"最暗比纸暗 32 级"这一档。
# [EN] Lightness: compression ratio and the darkest floor. **These two decide how dark the picture
# [EN] is**; "how colourful" is a separate knob.
# [EN] ★★★ Refactored 2026-10-24 midday (it used to be a single `GAMMA`): a per-channel power curve
# [EN] also flattens chroma, so the "wash strength" knob was dead -- measured, `CHROMA_K` from 0.42
# [EN] to 0.75 left chroma at 21.9..22.0. Splitting into "lightness component x LUM_K clamped by
# [EN] MAX_DARK + chroma component x CHROMA_K" makes each knob do one thing, which is what
# [EN] "content without intensity" actually needs.
# [EN] Measured sweep: 52 -> p1 159 (too intense); 44 -> 167; 38 -> 173; **30 -> 180** (chosen);
# [EN] 26 -> 185 (going grey). "Content without intensity" lands at "darkest 32 levels below paper".
#: ★★★ 2026-10-24 12:59（`FIT='whole'` 之后重扫）：0.62/30 是给**青绿山水**定的，
#:   而这一幅是**淡墨**水墨 —— 同一套参数下它整幅只落在 7.4% 有墨、std 4.7，
#:   收起态基本就是一张纸。用户选的正是这一幅，所以按它重扫：
#:   `LUM_K` 1.10 ⇒ 收起有墨 21.4% · 1.35 ⇒ 28.7% · 1.60 ⇒ 35.5%（文字对比都是 6.3:1，
#:   `_apply_floor` 已经把字底下兜住了）；
#:   **1.25 / MAX_DARK 42** 取中间：有墨 ≈26%、最暗比纸暗 42 级，仍是"淡墨"，不是浓墨。
# [EN] ★★★ 2026-10-24 12:59 (re-swept after `FIT='whole'`): 0.62/30 was tuned for a **blue-green**
# [EN] landscape, and this one is an **ink wash** -- under those numbers it lands at 7.4% inked with
# [EN] std 4.7, i.e. a blank sheet in the collapsed state. The user chose this painting, so re-sweep
# [EN] for it: LUM_K 1.10 -> 21.4% inked, 1.35 -> 28.7%, 1.60 -> 35.5% (text contrast stays 6.3:1;
# [EN] `_apply_floor` protects under the text). **1.25 / MAX_DARK 42** sits in the middle: ~26%
# [EN] inked, darkest 42 levels below paper -- still a *pale wash*, not heavy ink.
LUM_K = 1.25
MAX_DARK = 42.0
#: 比纸亮的上限（级）。见 `_tone` 里那段注释。
# [EN] Cap on how much brighter than paper a pixel may get (see `_tone`).
MAX_LIGHT = 4.0

#: **淡彩强度**：把"源图相对纸色的偏差"按这个比例压缩（1.0 = 照搬，越小越淡）。
#:
#: ★ 为什么需要它（2026-10-24 中午，用户：「要求画面有内容 但是不要太浓」）：
#:   AI 生成的青绿山水彩度 53.9、灰度均值 156.7（比纸暗 55 级）；直接搬进窗口，
#:   一是浓得压不住字，二是跟这套暖纸界面完全是两种材质。
#:   压缩偏差比"整体降饱和"好：色相与明暗关系都保留，只是浓度变淡；
#:   而且 d=0 的地方自然落在 `PAPER` 上，纸色不用另调。
#:   实测（重构后）：K=0.52 时彩度 54 → 27，而明度由 `LUM_K` 单独决定。
# [EN] **Wash strength**: compress the source's deviation from its own paper tone by this factor
# [EN] (1.0 = as-is, smaller = paler).
# [EN] ★ Why it exists (2026-10-24 midday, user: "the picture should have content but **not be too
# [EN] intense**"): the generated blue-green landscape measures chroma 53.9 and mean grey 156.7
# [EN] (55 levels below paper). Pasted straight in, it is too intense for text and reads as a
# [EN] different material from this warm-paper UI. Compressing the deviation beats a global
# [EN] desaturation: hue and light-dark relations survive, only the strength drops, and d=0 lands
# [EN] on `PAPER` so the paper tone needs no separate correction.
# [EN] Measured: at K=0.42 chroma goes 54 -> 25 and grey 157 -> 196 (paper is 212).
CHROMA_K = 0.42

#: 画的下沿淡出多少行（把最后一条硬边化开，接上补的纸）。
# [EN] How many rows at the painting's bottom edge fade into the filled paper.
PAD_FADE = 14

#: 文字带里**允许的最暗**灰度，以及允许保留下多少"低于下限"的暗度。
#:
#: ★★★ 2026-10-24 中午：205 → **170**，因为 205 把富春洗成了一张纸。
#:   原来那个 205 是用**线性**公式算对比度的（`(bg+5)/(fg+5)`），得到"205 才够 4.5:1"；
#:   而 sRGB 的对比度是**相对亮度**之比：灰 170 与字 50 是 ≈5.7:1，灰 205 是 ≈8.7:1 ——
#:   两个都远超要求，205 只是白白把画面压平。文字带覆盖了可见区的 54%，
#:   压到 205 之后量出来"有墨覆盖率 28.5%"，正是用户说的"内容不够"。
#:   2026-10-24 中午 170 → **176**：青绿那张在"展开态状态行"的 std 是 16.42
#:   （阈 16），抬 6 级就够，不必去放宽阈值。
#:   `KEEP=0.35` 让笔触在字下还看得出起伏（不是一块灰）。
# [EN] Darkest grey allowed inside a text band, and how much of the excess darkness may remain.
# [EN] ★★★ 2026-10-24 midday: 205 -> **170**, because 205 washed the Fuchun scan back into paper.
# [EN] 205 came from a **linear** contrast formula ((bg+5)/(fg+5)), which says "205 for 4.5:1"; but
# [EN] sRGB contrast is a ratio of **relative luminance**: grey 170 vs text 50 is ~5.7:1 and 205 is
# [EN] ~8.7:1 -- both far above the requirement, and 205 just flattened the picture for nothing.
# [EN] Text bands cover 54% of the visible area, so flattening to 205 measured "ink coverage 28.5%",
# [EN] which is exactly the user's "not enough content". KEEP=0.35 keeps stroke modulation visible.
FLOOR = 176
KEEP = 0.25
#: ★ `KEEP` 不是随手给的：它必须满足 `FLOOR - (FLOOR - 最暗墨) * KEEP >= TEXT_MIN`。
#:   最暗墨约 96（gamma 0.62 之下的最浓笔触），FLOOR 170、TEXT_MIN 150 ⇒ KEEP ≤ 0.27。
#:   0.25 就是 0.27 留一点余量（实测最暗落在 151~152）。
#:   ⚠ 上一版 0.35 时实测 min=146 ⇒ 那条"最暗 ≥ 150"的判据会红，而**产品是好的** ——
#:     这是"两个常量之间没对上"，不是画面有问题。常量之间的关系要写成式子，不能各写一个数。
# [EN] ★ `KEEP` is not arbitrary: it must satisfy
# [EN] `FLOOR - (FLOOR - darkest ink) * KEEP >= TEXT_MIN`. The darkest ink is ~96 (the heaviest
# [EN] stroke under gamma 0.62), so with FLOOR 170 and TEXT_MIN 150 the bound is KEEP <= 0.27.
# [EN] 0.25 keeps a margin (measured min 151..152). ⚠ At 0.35 the measured min was 146, turning the
# [EN] "min >= 150" check red while the product was fine -- two constants that never met. Their
# [EN] relation must be written as a formula, not as two independent numbers.
#: 下限遮罩的羽化半径（像素）。硬边会露出来，羽化之后看不出"哪里被保护过"。
# [EN] Feather radius of the floor mask; a hard edge would show.
FEATHER = 11

#: 纸纹。扫描自带的颗粒缩放后会被抹平一部分，补一点点。
# [EN] A touch of grain: scaling flattens some of the scan's own texture.
GRAIN_STD = 1.2

# ★ 取段规则在 `_score_visible` / `_pick_section` 里（4×3 网格 + 6 档 trim）。
#   不再有"山脊线落在可见高度几分之几"那套 —— 它要先认出**一行**山脊，而一幅画的上半
#   常常本来就是密林（`_ridge_row` 会返回 0），参数一动就失效。
# [EN] The rules live in `_score_visible` / `_pick_section` (4x3 grid + 6 trim steps). The old
# [EN] "ridge line at a fraction of the visible height" scheme is gone -- it needed a single ridge
# [EN] row, and the top half of a painting is often dense forest already (`_ridge_row` returned 0).
#: 判"有墨"的门槛：比纸暗多少级（源图纸 192，天空最暗约 175）。
# [EN] What counts as ink: levels below the source paper.
INK_DELTA = 14

#: **青绿占比**的上下界：低于下界就不像"青绿山水"，高于上界就"太浓"。
#: 实测对照：上一张（褐色绢本，几乎没有青绿）0.4%；这一张 14.8%；
#: 如果整片上石青石绿会到 30%+ —— 那是"浓"，用户不要。
# [EN] Bounds on the blue-green share: below it does not read as a blue-green landscape, above it is
# [EN] "too intense". Measured: the previous sheet (brown silk, almost no colour) 0.4%; this one
# [EN] 14.8%; an all-over mineral wash would be 30%+, i.e. "intense", which the user does not want.
TEAL_MIN = 5.0
TEAL_MAX = 26.0
#: 源图的青绿占比到这个数，才认为"这是一幅彩色（青绿）画"，成品也必须保住颜色。
#: 实测：千里江山源图 14.8%、这幅淡墨 0.0% ⇒ 3% 能干净分开。
# [EN] If the source's blue-green share reaches this value it counts as a **colour** painting and the
# [EN] output must keep its colour. Measured: Thousand-Li source 14.8%, this ink wash 0.0% => 3%.
TEAL_SRC_MIN = 3.0

#: **不要太浓**的下限：可见区最暗的 1% 不能低于这个灰度（纸是 212）。
#: 176 ⇒ 最暗处只比纸暗 36 级 —— 是"看得见的淡彩"，不是"乌黑的浓彩"。
# [EN] The "not too intense" floor: the darkest 1% of the visible area may not go below this grey
# [EN] (paper is 212). 176 => at most 36 levels below paper -- a visible pale wash, not heavy colour.
#: 可见区最暗 1% 的下限（级）。纸是 212。
#:
#: ★ 口径：它守的是"**别交一张乌黑的图**"，不是"越淡越好"。
#:   千里江山那一轮定 176；换成这幅淡墨后 `MAX_DARK=42` 自然给出 p1=169 ——
#:   169 与 176 只差 7 级，属于"贴边"，所以下限重定为 **158**：
#:   离实测 6.5%、离"压黑"那一刀（80）很远。判据侧另有一条 ≥150，更宽。
# [EN] Floor for the darkest 1% of the visible area (paper is 212).
# [EN] ★ It guards "**do not ship a black picture**", not "the paler the better". It was 176 for the
# [EN] Thousand-Li scroll; with this ink wash `MAX_DARK=42` naturally yields p1=169, only 7 levels
# [EN] under 176 -- a knife-edge -- so the floor is re-set to **158**: 6.5% below the measured value
# [EN] and far above a "crushed black" mutation (80). The criterion side uses >=150, looser still.
DARK_MIN = 158

#: 判据口径（`measure()` 按这个报）
# [EN] Criterion thresholds (reported by `measure()`)
#: ⚠ std 上限 16：它守的是"字底下别太花"，而**真正的约束是对比度**（`TEXT_MIN`）。
#:   实测（富春这段）各带 min 146~175 ⇒ 与字 50 的 sRGB 对比 4.6~6.0:1，全在 4.5:1 之上；
#:   这时再要求 std ≤ 12 等于逼着把笔触压平 —— 正是用户这一轮否掉的那件事。
# [EN] ⚠ std <= 16 guards "not too busy under the text"; the **binding** constraint is contrast
# [EN] (`TEXT_MIN`). Measured on this Fuchun section: per-band min 146..175 => 4.6..6.0:1 against
# [EN] text at 50, all above 4.5:1. Demanding std <= 12 on top of that only forces the strokes flat,
# [EN] i.e. exactly what the user rejected this round.
TEXT_STD_MAX = 16.0
TEXT_MIN = 150                #: 灰 150 与字 50 仍 ≈4.7:1（sRGB 相对亮度），见 `FLOOR` 那段
PAPER_LUM_TOL = 8.0
#: 可见区里"有墨"像素必须占多少 —— 这是"画面到底有没有东西"的下限，不是"够不够满"。
#:
#: ★★★ 口径变过两次，记下来：① 富春/千里江山那两轮定的是 **45%**（用户当时要"内容多一些"）；
#:   ② 2026-10-24 12:59 用户改回这幅**淡墨水墨**并要求"整张不裁直接缩放"⇒ 45% 立刻不成立
#:   （这一幅整幅铺进 860×573 后是 ~26%，其中收起态那 350 行更少）。
#:   ⚠ 但**不能因为换图就把这条删掉**：它守的是"别交一张纸上来"。
#:   重定成 **12%**：空白纸 0%、这幅 26%、富春 72% —— 12 稳稳在"有画"那一侧、
#:   又比实测低一半，换一档色阶不会翻。
# [EN] Share of inked pixels in the visible area -- a **floor for "is there anything there"**, not
# [EN] "is it full enough". ★★★ The yardstick changed twice: (1) the Fuchun / Thousand-Li rounds set
# [EN] **45%** (the user wanted "more content" then); (2) 2026-10-24 12:59 he went back to this **pale
# [EN] ink wash** and asked for "the whole image, scaled, no crop" => 45% stops holding (this one
# [EN] lands at ~26% when the whole picture fills 860x573, and less in the 350 visible rows).
# [EN] ⚠ But the check must not be deleted just because the painting changed: it guards "do not ship a
# [EN] blank sheet". Re-set to **12%**: blank paper 0%, this one 26%, Fuchun 72% -- 12 is firmly on the
# [EN] "there is a picture" side and half the measured value, so a tone tweak will not flip it.
INK_MIN = 12.0

#: **画了字的区域**（y0, y1, x0, x1, 说明）。留 6px 余量：字有描边/降部，不会刚好卡在边界。
#:
#: ⚠ 这些数字来自 `launcher_splash.py` 的布局（Logo y=74 / 标题 152 / 标语 190 /
#:   步骤点 221 / 消息条 242 左起 x=82 / 底栏 H-27、状态 H-66、工具行 `LOGTOOL_Y`、
#:   日志块 `LOG_BOX_TOP`..`+LOG_H` = 336..710）。
#:   布局一改，这里必须跟着改 —— 否则"下限"会落在错的位置，而**看起来还挺正常**。
#: ⚠ 每一处必须写**自己的横向范围**：按整行保护会压掉两侧的画（2026-10-24 上午栽过）。
# [EN] **Text regions** (y0, y1, x0, x1, label) with 6px slack.
# [EN] ⚠ From the layout constants in `launcher_splash.py`; when the layout moves, this must move
# [EN] too. ⚠ Each region needs its **own x extent**: protecting whole rows erases the artwork at
# [EN] the sides (failed that way on the morning of 2026-10-24).
TEXT_BANDS = [
    (16, 130, 356, 504, 'Logo'),
    (134, 172, 176, 684, '名字'),
    (172, 208, 250, 610, '标语'),
    (208, 232, 70, 240, '步骤点'),
    (232, 258, 70, 802, '消息条'),
    # ★★★ 2026-10-27：原因现在**允许折两行**（`_show_failed` 给 `width`，
    #   上限 2 行）—— 实测两行占 y 265..303、x 91..770，比原来那一行各处多 5px 上下。
    #   带子不跟着放大的话，第二行会有一半落在**没有被兜下限的画上**（字发虚）。
    # [EN] ★★★ 2026-10-27: the reason may now **wrap to two lines** (`_show_failed` sets `width`,
    # [EN] capped at 2). Measured: two lines occupy y 265..303, x 91..770 -- ~5px more top and
    # [EN] bottom than the single line. Without widening, half of the second line would sit on
    # [EN] artwork with no floor beneath it (the glyphs go mushy).
    (262, 306, 88, 772, '失败那一行'),
    (306, 340, 220, 640, '底栏'),
    (400, 426, 520, 802, '日志工具行'),
    # ★★★ 2026-10-27（窗口 620 → 820 → **602**）：下面三处跟着 `H_EXP` 走 ——
    #   工具行 `LOGTOOL_Y`=512、状态行 `H_EXP-66`=536、底栏 `H_EXP-27`=575。
    #   ⚠ 布局一改这里不改，"兜下限"就落在没有字的地方 —— 而**报告照样全绿**
    #   （它量的是"那一块够不够平"，补的纸本来就平）—— 这正是最难发现的一类失效。
    # [EN] ★★★ 2026-10-27 (window 620 -> 820 -> **602**): these three follow `H_EXP` -- action row
    # [EN] `LOGTOOL_Y`=512, status `H_EXP-66`=536, footer `H_EXP-27`=575. ⚠ Move the layout without
    # [EN] moving these and the floor lands where no text is, **while the report stays green** (it
    # [EN] measures flatness, and padding paper is flat) -- the hardest kind of silent failure.
    (496, 528, 520, 802, '展开态工具行'),
    (514, 560, 96, 764, '展开态状态行'),
    (559, 595, 220, 640, '展开态底栏'),
]


def _teal_share(im: Image.Image) -> float:
    """青绿像素占比（`g-r>8` 或 `b-r>8`），在**缩到 200 宽**的图上量。

    ★ 为什么要缩：全尺寸会把抗锯齿的边缘像素算进去，同一幅画能差一倍。
    ★ 为什么不量"彩度"：暖纸本身彩度就有 20~58，会把读数抬起来，与"有没有上色"无关。
    [EN] Blue-green share (`g-r>8` or `b-r>8`), measured on a **200px-wide** copy.
    [EN] ★ Why downscale: full size counts anti-aliased fringes and can double the figure.
    [EN] ★ Why never "chroma": warm paper alone contributes 20..58, unrelated to "is it painted".
    """
    w = 200
    small = im.convert('RGB').resize((w, max(1, int(round(w * im.height / im.width)))),
                                     Image.LANCZOS)
    px = list(small.getdata())
    n = max(1, len(px))
    return sum(1 for r, g, b in px if (g - r > 8) or (b - r > 8)) / n * 100


def _paper_rgb(src: Image.Image) -> tuple[float, float, float]:
    """量源图的"纸色"：取最亮那 12% 像素的平均（避开高光噪点）。

    ★ 不能用整图均值当纸色：手卷里大半是山与水，均值会比纸暗二三十级，
      拿它去映射纸色，整幅画会一起变亮、山就没了。
    [EN] The source's paper colour: mean of the brightest 12% (skips specular noise).
    [EN] ★ Never the whole-image mean: most of a handscroll is mountain and water, tens of levels
    [EN] below the paper, so mapping with it would brighten everything and erase the mountains.
    """
    small = src.convert('RGB').resize((200, max(1, int(200 * src.height / src.width))),
                                      Image.LANCZOS)
    px = list(small.getdata())
    lum = [0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in px]
    cut = sorted(lum)[int(len(lum) * 0.88)]
    top = [p for p, l in zip(px, lum) if l >= cut]
    n = max(1, len(top))
    return (sum(p[0] for p in top) / n, sum(p[1] for p in top) / n,
            sum(p[2] for p in top) / n)


def _row_cover(g: Image.Image, paper_lum: float) -> list[float]:
    """逐行的"墨迹覆盖率"（0..1）：这一行里比纸暗 `INK_DELTA` 以上的像素占比。

    ★ 为什么用"逐行覆盖"而不是逐行均值：均值会被大片淡墨拉平，山脊线（实笔）
      和天空（留白）的均值差别不大；覆盖率是"这一行有多少地方真的落了笔"，信号干净。
    [EN] Per-row ink coverage (0..1): the share of pixels in that row darker than the paper by
    [EN] `INK_DELTA`. ★ Why coverage instead of the row mean: the mean is flattened by wide washes,
    [EN] so the ridge (real strokes) barely differs from the sky; coverage counts "how much of this
    [EN] row was actually painted", which is a clean signal.
    """
    w, h = g.size
    raw = g.tobytes()
    cut = paper_lum - INK_DELTA
    out = []
    for y in range(h):
        row = raw[y * w:(y + 1) * w]
        out.append(sum(1 for v in row if v < cut) / max(1, w))
    return out


def _score_visible(seg: Image.Image, scale: float) -> dict:
    """把候选段缩到"用户真的看到的尺寸"，按**网格分布**打分。

    ★★★ 为什么在**缩放之后**量（2026-10-24 中午，这一轮的教训）：
      第一版在源图分辨率（2740×1975）上量边缘能量与覆盖率，于是选出"细笔触最多"的那一段；
      可它在窗口里只有 0.31×，细笔触缩完就糊成纸 —— 量出来"有墨 47%"，看着仍像白纸。
      **分数要跟用户看到的那个尺寸对齐。**
    ★★ 为什么**不扣掉文字带**（第二版的错误）：扣掉之后只剩左右两条窄边，
      评分其实在优化"边缘那两条竖条"，选出来的窗口一个角很满、中间很空。
      而且下限只到 170（纸 212），字底下**画仍然看得见**（是压淡，不是擦掉），
      所以判"内容够不够"就该看整块可见区。
    ★ 为什么按 **4×3 网格**取"平均 + 最差一格"：只取整块均值时，一个角很满、
      中间空一半的窗口也能得高分；"最差那一格"把这种偏科压下去，正是用户说的
      "整幅画内容多一些"。
    [EN] Shrink the candidate to **the size the user actually sees** and score a **grid distribution**.
    [EN] ★★★ Why measure **after** scaling: scoring at source resolution picked the stretch with the
    [EN] most fine strokes, which blurs into paper at 0.31x -- "47% inked" that still looked blank.
    [EN] ★★ Why **not** exclude the text bands (the second version's error): what remains is only the
    [EN] two narrow side margins, so the metric was really optimising those strips and picked a window
    [EN] with one full corner and an empty middle. And the floor stops at 170 (paper 212), so the
    [EN] painting **still shows through under text** -- it is dimmed, not erased.
    [EN] ★ Why a **4x3 grid** (mean + worst cell): a plain mean still rewards "one corner full, half
    [EN] the middle empty"; the worst cell suppresses that skew, which is exactly "the whole picture
    [EN] should have more content".
    """
    tw, th = max(8, int(W * scale)), max(8, int(VIS_H * scale))
    vis = seg.resize((tw, th), Image.LANCZOS).convert('L')     # 只取可见那一段的比例
    cells = []
    for gy in range(3):
        for gx in range(4):
            box = (gx * tw // 4, gy * th // 3, (gx + 1) * tw // 4, (gy + 1) * th // 3)
            cells.append(ImageStat.Stat(vis.crop(box)).stddev[0])
    mean = sum(cells) / len(cells)
    worst = min(cells)
    cover = sum(1 for v in vis.tobytes() if v < PAPER_LUM - 10) / max(1, tw * th) * 100
    score = mean * 1.0 + worst * 0.6 + cover * 0.05
    return {'score': round(score, 2), 'std': round(mean, 1),
            'worst': round(worst, 1), 'cover': round(cover, 1)}


def _trim_scan_edges(g: Image.Image, paper_lum: float) -> tuple[int, int]:
    """裁掉扫描图上下那条**均匀的暗边**（拍照/扫描的边缘压暗，不是画）。

    判据是两件事**同时**成立：`std < 6`（没有笔触）且 `mean < 纸 - 10`（比纸暗）。
    ★ 只看"暗"会把山脊也裁掉（山脊又暗又有结构，std 高）；只看"平"会把天空裁掉
      （天空平但**比纸亮**）。两条一起才精确指向"边缘压暗带"。
    ⚠ 上限 4% 高度：万一一幅画真的上边也有一片暗而平的天空，也只裁一点点。
    [EN] Trim the **uniform dark band** along the scan's top/bottom edges (camera falloff, not art).
    [EN] Two conditions together: `std < 6` (no strokes) AND `mean < paper - 10` (darker than paper).
    [EN] ★ "dark" alone would cut the ridge (dark but structured); "flat" alone would cut the sky
    [EN] (flat but *brighter* than paper). Together they pinpoint the edge falloff.
    [EN] ⚠ Cap 4% of the height, in case some painting really has a dark flat sky at the top.
    """
    w, h = g.size
    cap = max(2, int(h * 0.04))

    def _flat_dark(y0: int, y1: int) -> bool:
        st = ImageStat.Stat(g.crop((int(w * 0.1), y0, int(w * 0.9), y1)))
        return st.stddev[0] < 6 and st.mean[0] < paper_lum - 10

    top = 0
    while top < cap and _flat_dark(top, top + 1):
        top += 1
    bot = 0
    while bot < cap and _flat_dark(h - bot - 1, h - bot):
        bot += 1
    # ★ 底部还有第二种东西：**装裱的空白纸 + 边缘阴影**（平、且接近纸色）。
    #   实测这一卷：画的最后一笔在 y≈1888，往下到 1968 全是平的（std ≈ 3），
    #   在窗口最下面就是一条 12~20px 的浅色带 —— 看起来就是"没铺满"。
    #   ⇒ 直接找到**最后一个有笔触的行**（行 std ≥ 8），把它以下全裁掉（上限 8% 高度）。
    #   ★ 为什么不用"比纸亮/比纸暗"判：装裱纸在**校色之后**与纸几乎同色，
    #     而画里的水面也平、也可能接近纸色 —— 亮度分不开，**结构（std）**才分得开。
    # [EN] The bottom has a second thing: the **mounting's blank paper plus edge shadow** (flat,
    # [EN] near paper tone). Measured on this scroll: the last brush stroke is at y ~1888 and
    # [EN] everything below to 1968 is flat (std ~3), i.e. a 12..20px light band at the window's
    # [EN] bottom that simply looks "not filled". So find the **last row with brushwork**
    # [EN] (row std >= 8) and cut everything below it (cap 8% of the height).
    # [EN] ★ Why not "brighter/darker than paper": after tone matching the mounting paper is
    # [EN] nearly the same colour as the paper, and water in the painting is flat and may be close
    # [EN] too -- brightness cannot separate them, **structure (std)** can.

    def _row_std(y0: int, y1: int) -> float:
        return ImageStat.Stat(g.crop((int(w * 0.08), y0, int(w * 0.92), y1))).stddev[0]

    cap2 = max(4, int(h * 0.08))
    busy = h - bot - 1
    limit = max(0, h - bot - cap2)
    while busy > limit and _row_std(busy - 1, busy) < 8.0:
        busy -= 1
    bot = h - busy
    return top, bot


def _pick_section(g: Image.Image, paper_lum: float) -> dict:
    """在整卷上滑窗，挑"**用户看到时**最饱满"的一段（横向 × 纵向都试）。

    评分（越大越好）= std * 1.0 + edge * 0.8 + cover * 0.10
      · `std`   明暗层次（有山、有水、有留白）；
      · `edge`  笔画密度；
      · `cover` 有墨面积。
    权重不追求"科学"，追求**在三张对照图上排序稳定**：空白段、全密段、这段山水，
    排出来的顺序必须是"山水 > 全密 > 空白"。纵向也试几档（0 / 8% / 16% / 24%），
    因为手卷上半常是空天，裁掉一点天空反而更饱满。
    [EN] Slide a window across the scroll and keep the stretch that is **fullest as the user sees
    [EN] it** -- both horizontally and vertically. score = std + 0.8*edge + 0.10*cover. The weights
    [EN] are not "scientific"; they are chosen so the ordering stays stable on three controls
    [EN] (blank / all-dense / this landscape must rank landscape > all-dense > blank). A few vertical
    [EN] offsets are tried too (0 / 8% / 16% / 24%), because the top of a handscroll is often empty
    [EN] sky and trimming a little makes the frame fuller.
    """
    sw, sh = g.size
    aspect = W / H_TALL
    scale = 0.20                       # 在 1/5 尺寸上评分（≈172×70，够判"哪块满"）
    best = None
    for trim in (0.00, 0.06, 0.12, 0.18, 0.24, 0.30):
        y0 = int(round(sh * trim))
        win_h = sh - y0
        win_w = max(64, int(round(win_h * aspect)))
        if win_w > sw:
            continue
        step = max(32, win_w // 14)
        for x0 in range(0, sw - win_w + 1, step):
            seg = g.crop((x0, y0, x0 + win_w, sh))
            m = _score_visible(seg, scale)
            if best is None or m['score'] > best['score']:
                best = {'x0': x0, 'y0': y0, 'width': win_w, 'height': win_h,
                        'trim': trim, **m}
    return best or {'x0': 0, 'y0': 0, 'width': sw, 'height': sh, 'score': 0.0,
                    'std': 0.0, 'edge': 0.0, 'cover': 0.0, 'trim': 0.0}


def _tone(src: Image.Image, paper: tuple[float, float, float]) -> Image.Image:
    """校色：**明度与色度分开压**，再以 `PAPER` 为纸。**只改色阶，不动构图。**

    见文件头 `LUM_K` / `MAX_DARK` / `CHROMA_K` 那三段：逐通道做幂运算会同时压扁色度，
    所以必须先把偏差拆成"亮度分量"和"色度分量"，各自乘各自的系数。

    ⚠ 这个函数对**已经缩放到目标尺寸**的图调用（`build` 里 resize 之后），
      而不是对原图：一是快（53 万 vs 157 万像素），二是缩放插值在校色前做与后做等价。
    [EN] Tone match: **lightness and chroma compressed separately**, paper set to `PAPER`.
    [EN] **Levels only, never geometry**: split the deviation into a lightness component and a
    [EN] chroma component and scale each by its own factor -- a per-channel power curve would
    [EN] flatten both at once (see `LUM_K` / `MAX_DARK` / `CHROMA_K`).
    [EN] ⚠ Called on the image **already resized** to target (in `build` after resize): faster (530k
    [EN] vs 1.57M pixels) and resampling before/after a monotone level map is equivalent.
    """
    src = src.convert('RGB')
    raw = src.tobytes()
    out = bytearray(len(raw))
    pr, pg, pb = paper
    dr_, dg_, db_ = PAPER
    for k in range(0, len(raw), 3):
        r = raw[k] - pr
        g = raw[k + 1] - pg
        b = raw[k + 2] - pb
        lum = 0.299 * r + 0.587 * g + 0.114 * b      # 亮度分量（负数 = 比纸暗）
        v = lum * LUM_K
        if v < -MAX_DARK:
            v = -MAX_DARK
        elif v > MAX_LIGHT:
            # ★ 比纸亮的部分也要夹：实测成品"最亮 5%"是 216.1，而 canvas 底色是 212
            #   —— 那 4 级色差会在窗口边缘露出来（画与纸不是同一种纸）。
            # [EN] Also clamp the brighter-than-paper side: the output's brightest 5% measured
            # [EN] 216.1 against a canvas bg of 212, and that 4-level gap shows at the window edge
            # [EN] (the picture and the paper are not the same paper).
            v = MAX_LIGHT
        # 色度 = 偏差 - 亮度分量（三分量），按 CHROMA_K 压缩；色相由它的方向决定，不变
        cr = (r - lum) * CHROMA_K
        cg = (g - lum) * CHROMA_K
        cb = (b - lum) * CHROMA_K
        out[k] = max(0, min(255, int(round(dr_ + v + cr))))
        out[k + 1] = max(0, min(255, int(round(dg_ + v + cg))))
        out[k + 2] = max(0, min(255, int(round(db_ + v + cb))))
    return Image.frombytes('RGB', src.size, bytes(out))


def _grain(size: tuple[int, int], std: float, seed: int = 7) -> Image.Image:
    """纸的颗粒：高频噪点 + 低频大块不匀（只有颗粒没有不匀，会像屏幕噪点而不像纸）。

    ★★★ `std` 是**最终颗粒的标准差**，就是灰度级的抖动。踩过坑：第一版写的是
      `gauss(0, std * 6)`，一个随手乘的系数，整张图 std 变成 6.8（原来那张底是 2.2），
      于是每一条文字带都"太花"。"参数看着差不多"和"量出来一样"是两件事。
    ★ 低频那一层必须**先在小尺寸上生成、模糊，再放大**。
    [EN] Paper grain: high-frequency noise **plus** low-frequency blotches.
    [EN] ★★★ `std` is the **final** sigma in grey levels. A pit: the first version used
    [EN] `gauss(0, std * 6)` and the whole image ended at std 6.8, so every text band looked busy.
    [EN] ★ The low band must be generated small, blurred, upscaled.
    """
    rnd = random.Random(seed)
    w, h = size
    hi = Image.new('L', (w, h))
    hi.putdata([max(0, min(255, 128 + int(rnd.gauss(0, std)))) for _ in range(w * h)])
    lw, lh = max(2, w // 24), max(2, h // 24)
    blot = Image.new('L', (lw, lh))
    blot.putdata([max(0, min(255, 128 + int(rnd.gauss(0, std * 1.6))))
                  for _ in range(lw * lh)])
    blot = blot.filter(ImageFilter.GaussianBlur(1.2)).resize((w, h), Image.BICUBIC)
    return Image.blend(hi, blot, 0.35)


def _floor_mask() -> Image.Image:
    """文字带的**下限遮罩**（255 = 完全保护），并按 `FEATHER` 羽化。

    ★ 羽化不是美化：不羽化的话，每一处文字的横向范围都会在画面上留下一个矩形 ——
      比"字压在墨上"更难看，而且一眼看出来是程序贴的。
    [EN] The floor mask over the text bands (255 = fully protected), feathered.
    [EN] ★ The feather is not cosmetic: without it every text region leaves a **rectangle**.
    """
    m = Image.new('L', (W, H_TALL), 0)
    d = ImageDraw.Draw(m)
    for y0, y1, x0, x1, _n in TEXT_BANDS:
        d.rectangle([x0, y0, x1, min(y1, H_TALL - 1)], fill=255)
    return m.filter(ImageFilter.GaussianBlur(FEATHER))


def _apply_floor(im: Image.Image, mask: Image.Image) -> Image.Image:
    """落在文字带里、比 `FLOOR` 更暗的像素，抬到 `FLOOR` 附近（保留 `KEEP` 比例的暗度）。

    ★★★ 下限从**纸**插值到 `FLOOR`，**不是从 255**：写成 `255 - (255-FLOOR)*m` 的话，
      羽化边缘的 `m` 小、`floor` 就接近 240 —— 而纸只有 212，于是**纸本身被判成
      "比下限还暗"**、被提亮到 235。症状是文字带周围一圈发亮的光晕，整张 std 从 1.2 涨到 9。
      "下限"的意思是"不许比这更暗"，它必须始终**不高于纸**。
    按亮度比例缩放三通道，所以色相不变（抬亮之后不会发灰发蓝）。
    [EN] Pixels darker than `FLOOR` inside a text band are lifted towards it, keeping `KEEP` of the
    [EN] excess; the scale is applied to all three channels so the hue is preserved.
    [EN] ★★★ The floor interpolates from the **paper**, not from 255: with `255 - (255-FLOOR)*m` a
    [EN] feathered `m` gives ~240 while the paper is 212, so **the paper counts as "too dark"** and
    [EN] gets lifted -- a bright halo around every band, whole-image std 1.2 -> 9. A floor means "no
    [EN] darker than this" and must never sit above the paper.
    """
    box = im.load()
    mk = mask.load()
    for y in range(H_TALL):
        for x in range(W):
            m = mk[x, y]
            if m <= 8:                       # 遮罩外：**一个像素都不动**
                continue
            r, g, b = box[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            floor = PAPER_LUM - (PAPER_LUM - FLOOR) * (m / 255.0)
            if lum >= floor:
                continue
            target = floor - (floor - lum) * KEEP
            k = target / max(1.0, lum)
            box[x, y] = (min(255, int(r * k)), min(255, int(g * k)),
                         min(255, int(b * k)))
    return im


def _seal(img: Image.Image, cx: int, cy: int, size: int = 24,
          alpha: int = 138) -> None:
    """右下角那枚小朱印（用代码画，不写在提示词里）。

    ★ 为什么自己画：图里的印章位置无法控制，而且 AI 写的印文必然是糊字；
      这里画一个**没有字的朱文方印**：双线边框 + 中心一道竖笔，远看是印、近看不是字。
    ★★★ `alpha` 必须是**半透明**：不透明朱红 (166,58,44) 的灰度只有 80，
      压在这张 210 的纸上就是**一个黑方块**。
    ⚠ 位置在**补的那条纸**上：那里没有画，也没有字（底栏文字只到 x≈640）。
    [EN] The small vermilion seal at the bottom right, drawn in code (never in a prompt).
    [EN] ★ Why: the model cannot place a seal and AI-written seal characters are mush; this is a
    [EN] **wordless** seal (double frame + one vertical stroke).
    [EN] ★★★ `alpha` must be semi-transparent: opaque vermilion is grey 80, i.e. a black square.
    [EN] ⚠ It sits on the filled paper strip: no artwork and no text there.
    """
    red = (156, 52, 40, alpha)
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0 = cx - size // 2, cy - size // 2
    x1, y1 = x0 + size, y0 + size
    d.rectangle([x0, y0, x1, y1], outline=red, width=2)
    d.rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], outline=red, width=1)
    d.line([(cx, y0 + 6), (cx, y1 - 6)], fill=red, width=2)
    layer = layer.filter(ImageFilter.GaussianBlur(0.5))
    if img.mode == 'RGBA':
        img.alpha_composite(layer)


def build(src: Path, apply: bool, section: int | None = None) -> dict:
    """源图 → (展开态, 收起态) 两张 PNG，并返回测量结果。
        English: Source -> (expanded, collapsed) PNGs, plus the measurements."""
    with Image.open(src) as im0:
        src_im = im0.convert('RGB')
    paper = _paper_rgb(src_im)
    paper_lum = 0.299 * paper[0] + 0.587 * paper[1] + 0.114 * paper[2]
    # ⓿ 先裁掉扫描的**边缘压暗带**（那条在窗口最下面会变成一条"发暗的边"）
    #    —— 它是照片的产物，不是画。裁完再取段，取段的比例才对得上窗口。
    # [EN] ⓿ First trim the scan's **edge falloff** (it shows up as a dark line at the window's
    # [EN] bottom edge) -- a photographic artifact, not art. Trim before picking, so the section
    # [EN] aspect matches the window.
    t_top = t_bot = 0
    if FIT == 'whole':
        # ★ `whole` 下**不裁边带**：哪怕上下有拍照压暗的边，也属于"这张图"的一部分，
        #   用户说的是"不要用截取"。裁掉 20 行也算截。
        # [EN] Under `whole` the **scan-edge trim is skipped**: even a dark photographic edge belongs
        # [EN] to "this image", and the user said do not crop -- 20 rows is still cropping.
        pass
    else:
        g0 = src_im.convert('L')
        t_top, t_bot = _trim_scan_edges(g0, paper_lum)
        if t_top or t_bot:
            src_im = src_im.crop((0, t_top, src_im.width, src_im.height - t_bot))
    sw, sh = src_im.size
    g = src_im.convert('L')

    # ① 取段：在整卷上滑窗，挑"**用户看到时**最饱满"的一段（横向 × 纵向都试）
    #    ⚠ 打印出来的 `score/std/edge/cover` 是**缩放之后**量的（见 `_score_visible`），
    #      不是源图分辨率上的数字 —— 后者会把"细笔触"当内容，而细笔触缩完就没了。
    # [EN] ① Pick the section: slide across the scroll and keep the stretch that is **fullest as the
    # [EN] user sees it** (both axes). ⚠ The reported score/std/edge/cover are measured **after**
    # [EN] scaling (see `_score_visible`), not at source resolution -- the latter counts fine strokes
    # [EN] as "content", and those vanish once shrunk.
    if FIT == 'whole':
        # ★ 整张：**一个像素都不裁**。缩放比取 `min(宽比, 高比)`（contain），
        #   所以画一定完整地落在窗口里，缺的那一条用同一个纸色补。
        #   实测 1536×1024 → k=0.560 → **860×573**，下面补 47 行纸。
        # [EN] The whole image: **not a single pixel cropped**. The scale factor is
        # [EN] `min(width ratio, height ratio)` (contain), so the picture always fits entirely and the
        # [EN] leftover strip is filled with the same paper colour.
        # [EN] Measured 1536x1024 -> k=0.560 -> **860x573**, with 47 rows of paper below.
        k = min(W / sw, H_TALL / sh)
        pic_w = max(1, int(round(sw * k)))
        pic_h = max(1, int(round(sh * k)))
        sec = {'x0': 0, 'y0': 0, 'width': sw, 'height': sh, 'picked': 'whole',
               'score': 0.0, 'std': 0.0, 'worst': 0.0, 'cover': 0.0, 'trim': 0.0,
               'scale': round(k, 3), 'pic_w': pic_w}
        box = (0, 0, sw, sh)
        pic = src_im
    else:
        sec = _pick_section(g, paper_lum)
        if section is not None:
            sec['x0'] = max(0, min(sw - sec['width'], int(section)))
            sec['picked'] = 'manual'
        else:
            sec['picked'] = 'auto'
        box = (sec['x0'], sec['y0'], sec['x0'] + sec['width'], sec['y0'] + sec['height'])
        pic = src_im.crop(box)
        pic_w = W
        # 取段的长宽比就是窗口比例，所以画能**正好铺满**（下面不再补纸；补纸逻辑留着给别的画）
        # [EN] The section's aspect is the window's, so the picture fills it exactly (no padding
        # [EN] below; the padding code stays for other paintings).
        pic_h = H_TALL

    # ③ 缩放 + 校色（**先缩后校**：`_tone` 是逐像素的单调映射，先缩快 3 倍且等价）
    #    缩完补一点锐化把笔触找回来
    # [EN] ③ Downscale, then tone match (**shrink first**: `_tone` is a per-pixel monotone map, so
    # [EN] this is 3x faster and equivalent); a light unsharp pass brings the strokes back.
    scaled = pic.resize((pic_w, pic_h), Image.LANCZOS)
    scaled = _tone(scaled, paper)
    scaled = scaled.filter(ImageFilter.UnsharpMask(radius=1.1, percent=55, threshold=2))

    # ④ 铺到纸上：画从 y=0 起；不够高就用同一种纸补，画的下沿淡出（不留硬边）
    # [EN] ④ Lay it on the paper: from y=0; if shorter than the window, fill with the same paper and
    # [EN] fade the picture's bottom edge so no hard seam appears.
    canvas = Image.new('RGB', (W, H_TALL), PAPER)
    fade = min(PAD_FADE, max(1, pic_h // 3)) if pic_h < H_TALL else 0
    m = Image.new('L', (pic_w, pic_h), 255)
    mp = m.load()
    for y in range(max(0, pic_h - fade), pic_h):
        v = int(255 * (1.0 - (y - (pic_h - fade)) / max(1, fade - 1)) ** 1.4)
        for x in range(pic_w):
            mp[x, y] = max(0, min(255, v))
    canvas.paste(scaled, ((W - pic_w) // 2, 0), m)

    # ⑤ 只在有字的地方兜下限（羽化，画面上不会出现矩形）
    canvas = _apply_floor(canvas, _floor_mask())

    # ⑥ 纸纹：三通道同量（保留色相，噪点不发花）
    grain = _grain((W, H_TALL), GRAIN_STD)
    g_px = list(grain.getdata())
    o_px = list(canvas.getdata())
    canvas.putdata([(
        max(0, min(255, c[0] + (g_px[i] - 128))),
        max(0, min(255, c[1] + (g_px[i] - 128))),
        max(0, min(255, c[2] + (g_px[i] - 128))),
    ) for i, c in enumerate(o_px)])

    # ⑦ 朱印：**默认不画**（2026-10-24 13:19 用户的判断胜过我的设计）。
    #
    #   ★★★ 用户当时说的是「**这张图里有一个 AI 生成的字，你把这部分截取掉**」，
    #     接着又说「**可以直接把下面这部分截取删除掉**」。
    #     我按"图里的字"在**源图**里找了六轮（孤立高细节块 / 短笔画聚集 / 横竖方向 /
    #     中性灰 / 轴对齐直段 / 双尺度细节比），全部落空 —— 因为那东西根本不在源图里：
    #     它是**我在这一步画上去的一枚无字朱印**（方框 + 一道竖笔，25×25，在半透明的
    #     朱红下远看就像一个汉字）。在成品图上量，它是下方**唯一**一块孤立暗块
    #     （y 576..606 / x 780..820，282 个朱红像素）—— 一量就现形。
    #   ⇒ 结论不是"再调参数"，而是**这个东西不该存在**：它是我加的装饰，
    #     用户要的是那张画本身，不需要我补一枚印。
    #   ⚠ `_seal()` 函数保留（连同那段"为什么自己画"的注释），把开关放成常量，
    #     以后真想要一枚印，改一行就能回来，不用重写。
    # [EN] ⑦ The seal is **off by default** (the user's judgement beat my design on 2026-10-24
    # [EN] 13:19). ★★★ He said "**there is an AI-generated character in this image, cut that part
    # [EN] out**", then "**you can just cut away this bottom part**". I searched the **source** for
    # [EN] that character through six rounds (isolated high-detail blocks / clustered short strokes /
    # [EN] horizontal-and-vertical / neutral grey / axis-aligned runs / two-scale detail ratio) and
    # [EN] found nothing -- because it is not in the source: it is **a wordless vermilion seal I drew
    # [EN] at this step** (a frame plus one vertical stroke, 25x25, which reads like a Chinese
    # [EN] character under the semi-transparent red). Measured on the output, it is the **only**
    # [EN] isolated dark blob in the lower half (y 576..606 / x 780..820, 282 red pixels).
    # [EN] => The conclusion is not "tune another parameter" but **this thing should not exist**:
    # [EN] it was my ornament, and the user wants the painting itself.
    # [EN] ⚠ `_seal()` stays (with its "why draw it myself" rationale) behind a constant, so
    # [EN] restoring a seal later is a one-line change, not a rewrite.
    if SEAL:
        rgba = canvas.convert('RGBA')
        _seal(rgba, W - 52, H_TALL - 26)
        canvas = rgba.convert('RGB')

    tall = canvas
    base = canvas.crop((0, 0, W, H_BASE))

    rep = measure(tall, base, src_im, pic_h)
    rep['src'] = str(src)
    rep['src_size'] = [sw, sh]
    rep['fit'] = FIT
    rep['section'] = {'box': list(box), 'picked': sec['picked'],
                      'score': sec['score'], 'std': sec['std'],
                      'worst_cell': sec['worst'], 'cover': sec['cover'],
                      'trim_sky': sec['trim'],
                      'scale': sec.get('scale') or round(W / sec['width'], 3),
                      'pic_w': pic_w, 'content_h': pic_h,
                      'pad_rows': H_TALL - pic_h,
                      'trim_scan': [t_top, t_bot]}
    if apply:
        tall.save(OUT_TALL, 'PNG', optimize=True)
        base.save(OUT_BASE, 'PNG', optimize=True)
        rep['written'] = [str(OUT_TALL.relative_to(ROOT)), str(OUT_BASE.relative_to(ROOT))]
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    return rep


def measure(tall: Image.Image, base: Image.Image,
            src_im: Image.Image | None = None,
            pic_h: int = 0) -> dict:
    """量三件事：纸色对不对、每条文字带安全不安全、画到底满不满。
        English: Paper tone, per-band safety, and whether the picture is actually dense."""
    g = tall.convert('L')
    out: dict = {'paper': {}, 'bands': [], 'art': {}, 'ink': {}, 'ok': True}

    # ① 纸色：取**可见区最亮 5%** 像素的均值 —— 画铺满之后没有任何一处是纯纸，
    #    固定取某一条（原来取 y 0..14）会量到天空里的墨气，误差随内容变，是"贴边通过"。
    # [EN] Paper tone: mean of the brightest 5% of the visible area -- with the picture filling the
    # [EN] window there is no bare-paper strip left, and a fixed strip (was y 0..14) samples ink-laden
    # [EN] sky instead, so the error drifts with the content: a knife-edge pass.
    vis0 = g.crop((0, 0, W, VIS_H))
    h0 = vis0.histogram()
    tot0 = sum(h0) or 1
    acc, cut = 0, 255
    for v in range(255, -1, -1):
        acc += h0[v]
        if acc >= tot0 * 0.05:
            cut = v
            break
    bright = [i * c for i, c in enumerate(h0) if i >= cut]
    cnt = sum(c for i, c in enumerate(h0) if i >= cut) or 1
    top_lum = sum(bright) / cnt
    out['paper'] = {'lum': round(top_lum, 1), 'p95_from': cut,
                    'target_lum': round(PAPER_LUM, 1), 'tol': PAPER_LUM_TOL}
    if abs(top_lum - PAPER_LUM) > PAPER_LUM_TOL:
        out['ok'] = False

    # ② 每条文字带：只量它自己的横纵范围（与下限遮罩一致）
    # [EN] ② Each text region over its own x/y extent (same extent the floor protects).
    for y0, y1, x0, x1, name in TEXT_BANDS:
        shot = base if y1 <= H_BASE else tall
        yb = min(y1, shot.height)
        if yb <= y0:
            continue
        stt = ImageStat.Stat(shot.crop((x0, y0, x1, yb)).convert('L'))
        rec = {'band': name, 'y': [y0, y1], 'x': [x0, x1],
               'lum': round(stt.mean[0], 1), 'std': round(stt.stddev[0], 2),
               'min': stt.extrema[0][0]}
        rec['ok'] = rec['std'] <= TEXT_STD_MAX and rec['min'] >= TEXT_MIN
        if not rec['ok']:
            out['ok'] = False
        out['bands'].append(rec)

    # ③ **画满不满**（"内容多一些"的可数版本）：可见区里"比纸暗 10 级"的像素占比。
    #    ⚠ 阈值取自实测对照：上一版 AI 山水 19%、纯纸 0%、富春这一段 ~72%。
    # [EN] ③ **Is the picture full** (the countable version of "more content"): share of pixels in
    # the visible area darker than the paper by 10 levels. ⚠ Controls measured: previous AI
    # landscape 19%, plain paper 0%, this Fuchun section ~72%.
    vis = base.crop((0, 0, W, VIS_H)).convert('L')
    hist = vis.histogram()
    tot = sum(hist) or 1
    ink = sum(hist[:int(round(PAPER_LUM - 10))]) / tot * 100
    ed = ImageStat.Stat(vis.filter(ImageFilter.FIND_EDGES)).mean[0]
    out['ink'] = {'cover': round(ink, 1), 'min': INK_MIN, 'edge': round(ed, 2),
                  'lum': round(ImageStat.Stat(vis).mean[0], 1)}
    if ink < INK_MIN:
        out['ok'] = False

    # ④ 画的下半截（展开时才看到）也得有东西，不能是补的一条纸
    #
    # ★★★ 2026-10-27 改口径：区间从 `[VIS_H, H_TALL]` 收成 `[VIS_H, pic_h]` ——
    #   窗口加高（620 → 820）之后，下面多出来的 200px **全是补纸**，把它算进分母，
    #   量的就是"窗口有多高"，不是"画有没有延伸下来"（**量错了对象**）。
    #   这一条要防的是"展开态下半截是一条空纸"，所以只量**画真正覆盖到的那一截**；
    #   收窄之后分母变小、画占比提高 ⇒ 判据**更严**，不是放松。
    # [EN] ④ The lower half (seen only when expanded) must carry artwork too, not just padding.
    # [EN] ★★★ 2026-10-27 changed range from `[VIS_H, H_TALL]` to `[VIS_H, pic_h]`: after the window
    # [EN] grew (620 -> 820) the extra 200px is **all padding**, so counting it in the denominator
    # [EN] measures "how tall the window is", not "does the painting reach down there" (**measured the
    # [EN] wrong object**). What this guards is "the expanded lower half is a blank strip of paper",
    # [EN] so measure only the rows the picture actually covers -- a smaller denominator raises the
    # [EN] picture's share, i.e. the criterion gets **stricter**, not looser.
    _lo_bot = int(pic_h) if pic_h and pic_h > VIS_H else H_TALL
    low = tall.crop((0, VIS_H, W, _lo_bot)).convert('L')
    h2 = low.histogram()
    t2 = sum(h2) or 1
    out['art']['lower'] = {
        'cover': round(sum(h2[:int(round(PAPER_LUM - 10))]) / t2 * 100, 1),
        'lum': round(ImageStat.Stat(low).mean[0], 1),
        'std': round(ImageStat.Stat(low).stddev[0], 2)}
    if out['art']['lower']['std'] < 3.0:
        out['ok'] = False

    # ⑤ **青绿**：`g` 或 `b` 明显高于 `r` 的像素占比 —— 这是"千里江山图"的可数特征。
    #    ⚠ 不要量"彩度"：这张源图的彩度 58 全部来自**纸色偏暖**（R 比 B 高 58），
    #      与青绿无关。上一版就是被那个数骗了：以为"太浓"，其实几乎没上色。
    #    ⚠ 也不能只看可见区：青绿主要在山体，集中在画面中部偏下。
    # [EN] ⑤ **Blue-green**: share of pixels where `g` or `b` clearly exceeds `r` -- the countable
    # [EN] signature of "A Thousand Li of Rivers and Mountains".
    # [EN] ⚠ Never measure "chroma": this source's chroma of 58 comes entirely from the **warm
    # [EN] paper** (R is 58 above B) and has nothing to do with blue-green. The previous version was
    # [EN] fooled by that number -- it read "too intense" when almost nothing was painted.
    vis_rgb = base.crop((0, 0, W, VIS_H)).convert('RGB')
    vp = list(vis_rgb.getdata())
    nv = max(1, len(vp))
    teal = sum(1 for r, g, b in vp if (g - r > 8) or (b - r > 8)) / nv * 100
    # ★★★ 2026-10-24 12:59：这条原来对**任何**图都要求 5%~26% 青绿 —— 那是给千里江山定的，
    #   换成淡墨水墨（`FIT='whole'` 这一幅）之后它必然红，而**成品是对的**。
    #   ⇒ 口径改成守**色相保真**：源图是彩色的（青绿 ≥ `TEAL_SRC_MIN`），成品就必须还是彩色的；
    #     源图本来是水墨，这条**不适用**，报告里明确写 `skipped`。
    #   ⚠ 不去掉它：它抓的是"校色把色度压没了"（`_tone` 重构前真的发生过，彩度 54→22）。
    # [EN] ★★★ 2026-10-24 12:59: this used to demand 5%..26% blue-green for **any** image -- tuned for
    # [EN] the Thousand-Li scroll, so on this pale ink wash it must go red while the output is right.
    # [EN] => it now guards **hue fidelity**: if the source is colourful (blue-green >= TEAL_SRC_MIN)
    # [EN] the output must still be colourful; an ink source is **not applicable** and the report says
    # [EN] `skipped` explicitly. ⚠ It is not removed: it catches "tone mapping killed the chroma",
    # [EN] which really happened before the `_tone` refactor (chroma 54 -> 22).
    src_teal = _teal_share(src_im) if src_im is not None else 0.0
    out['teal'] = {'share': round(teal, 1), 'src_share': round(src_teal, 1),
                   'min': TEAL_MIN, 'max': TEAL_MAX}
    if src_teal >= TEAL_SRC_MIN:
        out['teal']['gated'] = True
        if not (TEAL_MIN <= teal <= TEAL_MAX):
            out['ok'] = False
    else:
        out['teal']['gated'] = False
        out['teal']['skipped'] = '源图不是彩色（青绿 %.1f%% < %.1f%%）⇒ 本图为水墨，不适用' % (
            src_teal, TEAL_SRC_MIN)

    # ⑥ **不要太浓**：可见区的明度不能太暗，最暗的 1% 也不能太黑。
    #    浓的山水会有大片乌黑；这里的量法是"第 1 百分位不低于 `DARK_MIN`"。
    # [EN] ⑥ **Not too intense**: the visible area must not be too dark overall, and its darkest 1%
    # [EN] must stay above `DARK_MIN` -- an intense landscape has big black masses.
    vs = vis_rgb.convert('L')
    hh2 = vs.histogram()
    tt2 = sum(hh2) or 1
    p1 = 0
    acc2 = 0
    for v in range(256):
        acc2 += hh2[v]
        if acc2 >= tt2 * 0.01:
            p1 = v
            break
    out['wash'] = {'p1': p1, 'mean': round(ImageStat.Stat(vs).mean[0], 1),
                   'dark_min': DARK_MIN}
    if p1 < DARK_MIN:
        out['ok'] = False

    out['ok'] = bool(out['ok'])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='把一幅画/一截长卷做成 splash 底图')
    ap.add_argument('--src', default=str(SRC_DEFAULT),
                    help=f'原图（默认 {SRC_DEFAULT.name}）')
    ap.add_argument('--section', type=int, default=None,
                    help='横向取段起点（像素）；不给则按"内容最满"自动挑')
    ap.add_argument('--apply', action='store_true', help='真的写盘（否则只量）')
    args = ap.parse_args()
    rep = build(Path(args.src), args.apply, args.section)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print('\n=> ' + ('通过：画够满、纸色同调、文字带安全、上下两截都有画'
                     if rep['ok'] else '不通过（见上）'))
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
