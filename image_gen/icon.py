# -*- coding: utf-8 -*-
"""应用图标：**狐狸正脸 + 月白（带青）底 + 火红记号**（`qinghuo`）。

当前默认（`qinghuo`，2026-10-07 换的）
------------------------------------
用户原话：「软件的 Logo 看起来像是 UC 浏览器的 Logo 你把狐狸从侧影改成狐狸脸的
正脸而且要明显看出狐狸的特色 然后图标颜色改成中国色的青色 狐狸颜色变成火红色」。

撞车是真的：上一版是**橙底 + 白色侧影剪影**，和 UC 那个「橙底 + 白松鼠剪影」
在缩略图尺寸下几乎是同一种观感。所以这次三件事一起换：
**侧影 → 正脸**、**橙底 → 月白（带一点青）**、**白狐 → 火红狐**。

底色中间试过一版**深石青**（"青"放在底上、色重），用户看过之后改成
**月白带一点青** —— 观感更接近**宣纸底 + 朱红印**，而且对比从
"靠色相勉强够"变成"亮度与色相两路都拉开了"。

★ 正脸的几何是**画出来的**（上一版侧影是**量出来的**）：
  侧影来自用户当年在 AI 候选里挑中的那一张（`FOX_PATH`，92 个控制点经
  高斯平滑 → RDP 简化 → 闭 Catmull-Rom）。正脸没有那张图可依，改用
  **分段的开放 Catmull-Rom** 构造：段内平滑、段间**断开** ——
  那条缝正好留给**耳尖**（闭合样条处处切线连续，会把耳朵磨圆，
  一眼就看不出是狐狸）。只写**右半边**再镜像，左右对称是几何保证的。

狐狸怎么才"一眼认出"
--------------------
1. **大而饱满的尖耳**（占记号高度约 40%），耳外缘是全轮廓**最宽**处；
2. **上宽下尖的倒三角脸**，收成一个尖下巴（圆脸会读成猫/熊）；
3. **一对上挑的杏仁眼**，是**挖空**的（透出底色）——
   小尺寸下一糊就成了两点眼睛，比"画两个白点"稳。

配色管径
--------
每套配色自带 **`hue_range`**，`tools/verify_icon.py` 按它判"主色对不对"，
而不是把某个区间写死在断言里 —— 这样换配色时只改数据、不改判据
（早前吃过的教训：口径一变，写死的断言就从"保护"变成"噪音"）。

其它配色都还完整可用
--------------------
`zhusha`（朱砂橙底 + 象牙白狐：上一版的配色，形状同样是正脸）·
`zhuye` / `qingci`（更早一版"一丛竹子"：三竿同根散开、竹节是**加**上去的
短横箍、青绿~青蓝清新配色）。它们现在只是备选，不再是默认。

English:
App icon: **fox front face + moon-white (tinged cyan) background + fire-red mark** (`qinghuo`).
Current default (`qinghuo`, swapped on 2026-10-07)
------------------------------------
User's exact words: "The software Logo looks like the UC Browser logo, change the fox from a
side profile to a fox face
front face and make the fox's characteristics clearly visible, then change the icon color to a
Chinese-style cyan and the fox color to fire red".
The clash is real: the previous version was **orange background + white side-profile
silhouette**, and UC's "orange background + white squirrel silhouette"
looks almost the same at thumbnail size. So this time three things change together:
**side profile → front face**, **orange background → moon white (with a bit of cyan)**, **white
fox → fire-red fox**.
For the background, a version with **dark azurite** was tried at one point ("azurite" placed on
the background, heavy in color); after the user looked at it, it was changed to
**moon-white with a hint of azurite** — the look is closer to **xuan paper background +
vermilion seal**, and the contrast went from
"barely enough by hue alone" to "both luminance and hue are pulled apart".
★ The front-face geometry is **drawn** (the previous version's profile was **measured**):
  the profile comes from the one the user picked back then among AI candidates (`FOX_PATH`, 92 control points put through
  Gaussian smoothing → RDP simplification → closed Catmull-Rom). The front face has no such image to rely on, so instead it uses
  a **segmented open Catmull-Rom** construction: smooth within segments, **broken** between segments —
  that seam is exactly what's left for the **ear tips** (a closed spline is tangent-continuous everywhere, which rounds the ears off,
  and at a glance you can no longer tell it's a fox). Only the **right half** is written, then mirrored; left-right symmetry is geometrically guaranteed.
How to make a fox "recognizable at a glance"
--------------------
1. **Large, full pointed ears** (about 40% of the mark's height), the outer edge of the ear is the **widest** point of the whole outline;
2. **An inverted-triangle face, wide on top and pointed at the bottom**, tapering to a pointed chin (a round face reads as a cat/bear);
3. **A pair of upturned almond eyes**, which are **cut out** (letting the background show through) ——
   at small sizes a blur turns them into two dots, which is more reliable than "drawing two white dots".
Color scheme aperture
--------
Each color scheme carries its own **`hue_range`**, and `tools/verify_icon.py` uses it to judge
"whether the main color is right",
rather than hardcoding some interval into the assertions — this way, swapping color schemes only
changes the data, not the criteria
(a lesson learned earlier: once the standard changes, hardcoded assertions go from "protection"
to "noise").
The other color schemes are all still fully usable
--------------------
`zhusha` (vermilion orange background + ivory-white fox: the previous version's color scheme,
the shape is also a front face) ·
`zhuye` / `qingci` (an earlier version's "a clump of bamboo": three stalks spreading from the
same root, the bamboo nodes are **added**
short horizontal bands, fresh cyan-green ~ cyan-blue color scheme). They are now just
alternatives, no longer the default.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# ══════════════════════════════════════════════════════════════
#  配色方案
# [EN] Color scheme
# ══════════════════════════════════════════════════════════════
SCHEMES: dict[str, dict] = {
    # ── 当前默认：**月白（带一点青）+ 火红狐狸**（用户 2026-10-07 定的）──
    # [EN] ── Current default: **moon white (with a hint of cyan) + fire red fox** (decided by user
    # [EN] 2026-10-07) ──
    #
    # 「青」这条路先走过一版**深石青**底，用户看过之后改成**月白带一点青**
    # —— 也就是把"青"放在**底色**上、但压到很淡（月白本身就是中国色：
    # 冷白里透一点蓝青）。这反倒更像老样子：**宣纸底 + 朱红印**。
    # [EN] The "cyan" route first went through a version with a **deep stone cyan** base; after the user
    # [EN] saw it, it was changed to **moon white with a hint of cyan**
    # [EN] —— that is, put the "cyan" on the **base color**, but press it very faint (moon white itself is
    # [EN] a Chinese color:
    # [EN] a cool white with a trace of blue-cyan showing through). This actually looks more like the old
    # [EN] style: **xuan paper base + vermilion seal**.
    #
    # ★ 底色一浅，"对比靠什么支撑"就整个反了过来：
    #   深底亮记号那版是靠**色相**（亮度差只有 3.2:1，刚够线）；
    #   月白底深记号这版**亮度与色相两路都拉得很开**（≈3.5:1 / ≈189°），
    #   反而是更稳的一种配法 —— 明度差是给色觉障碍用户的那条退路
    #   （`verify_icon` 的「亮度对比 ≥ 3:1」钉的就是它）。
    # [EN] ★ Once the base is light, "what does contrast rely on" flips entirely:
    # [EN] The dark-base bright-mark version relied on **hue** (luminance difference was only 3.2:1, just
    # [EN] barely passing);
    # [EN] The moon-white-base dark-mark version **pulls both luminance and hue far apart** (≈3.5:1 /
    # [EN] ≈189°),
    # [EN] which is actually a more stable pairing —— the brightness difference is the fallback for users
    # [EN] with color vision deficiency
    # [EN] (this is exactly what `verify_icon`'s "luminance contrast ≥ 3:1" pins down).
    #
    # ★ 底浅了，**外圈描边就不能也浅**：它得把圆角方块从浅色桌面/浅色任务栏里
    #   勾出来。取中深的青灰（不是深青，深青配月白会显重）。
    # [EN] ★ With a light base, **the outer stroke can't be light too**: it has to pull the rounded square
    # [EN] out
    # [EN] from a light desktop/light taskbar. Use a medium-deep cyan-gray (not deep cyan; deep cyan with
    # [EN] moon white looks heavy).
    #
    # ★ 这套色值是**按实测反推出来的，不是按色值手算的**（差得很远）：
    #   第一版月白 (235,245,250)/(206,226,235) 手算对比 3.42:1，实测量到
    #   **2.62:1**（当场红）。原因是 `_paint_mark` 的上淡下深渐变、边圈的
    #   `_inset_shadow` 青灰渐晕、以及 4.5% 的纸纹混合**都会把底色质心往下拉**
    #   —— `verify_icon` 量的是 k-means 聚出来的**实际质心**，不是声明的色值。
    #   所以这里的数：底色再提亮一档、火红压到印泥那个深度（仍是正火红），
    #   实测 ≈3.5:1，留足余量。**改配色时别照色值估，跑一遍看数。**
    # [EN] ★ This set of color values is **back-derived from actual measurements, not hand-computed from
    # [EN] the color values** (they differ a lot):
    # [EN] The first moon white version (235,245,250)/(206,226,235) had a hand-computed contrast of 3.42:1,
    # [EN] but measurement gave
    # [EN] **2.62:1** (immediate red flag). The reason is that `_paint_mark`'s light-top/dark-bottom
    # [EN] gradient, the rim's
    # [EN] `_inset_shadow` cyan-gray vignette, and the 4.5% paper texture blend **all drag the base color's
    # [EN] centroid downward**
    # [EN] —— `verify_icon` measures the **actual centroid** from k-means clustering, not the declared
    # [EN] color values.
    # [EN] So the numbers here: raise the base one notch brighter, press the fire red down to the ink-paste
    # [EN] depth (still a true fire red),
    # [EN] measured ≈3.5:1, leaving ample margin. **When changing the palette, don't estimate from color
    # [EN] values; run it and look at the numbers.**
    'qinghuo': {
        'name': '月白 · 火狐',
        'mark_shape':  'fox',
        'hue_range':   (165, 215),          # 青（蓝绿之间；月白底色 ≈ 198°）
        # ★ 这一组值**是用户在候选图里挑的**（2026-10-07 第二版）：
        #   他原话是「亮度 3.14:1 色相差 173° 底色 198° 勾边 3.04:1 那个」——
        #   对应候选表里的「月白略深一档（勾边更稳）」。所以这四个数就是**验收标准**，
        #   改配色时把 `developers/make_icon_candidates.py` 跑一遍，
        #   量出来的值要能对上（尤其**勾边 3.04:1**：它比上一版 2.54:1 明显更稳，
        #   浅底图标放在浅色桌面/浅色任务栏上就靠这圈描边勾出轮廓）。
        'ground_top':    (232, 242, 247),   # 月白（上，最亮）
        'ground_bottom': (203, 224, 233),   # 月白（下，略沉 —— 竖渐变留住"纸"的层次）
        'ground_edge':   (100, 146, 162),   # 外圈细描边（中深青灰，负责勾边）
        # [EN] Cyan (between blue and green; moon white base ≈ 198°)
        # [EN] ★ This set of values **was chosen by the user from candidate images** (2026-10-07 second
        # [EN] version):
        # [EN] His exact words were "the one with luminance 3.14:1, hue difference 173°, base 198°, outline
        # [EN] 3.04:1" ——
        # [EN] corresponding to "moon white one notch deeper (outline more stable)" in the candidate table. So
        # [EN] these four numbers are the **acceptance criteria**;
        # [EN] when changing the palette, run `developers/make_icon_candidates.py` once,
        # [EN] and the measured values must match (especially **outline 3.04:1**: it's clearly more stable than
        # [EN] the previous version's 2.54:1,
        # [EN] the light-base icon on a light desktop/light taskbar relies on this stroke to define its
        # [EN] outline).
        # [EN] Moon white (top, brightest)
        # [EN] Moon white (bottom, slightly deeper —— the vertical gradient preserves the "paper" layering)
        # [EN] Outer thin stroke (medium-deep cyan-gray, handles the outline)
        'ground_gloss':  (255, 255, 255),
        'mark':          (203, 56, 28),     # 火红（记号；压到印泥那个深度）
        'mark_soft':     (232, 90, 52),     # 火红（上淡下深用）
        # [EN] Fire red (mark; pressed to the ink-paste depth)
        # [EN] Fire red (for light-top/dark-bottom)
    },
    # ── 上一版的配色（备选）：朱砂橙底 + 象牙白狐。形状同样是正脸 ──
    #   ⚠ 别再拿它当默认：就是它跟 UC 浏览器撞了观感（用户 2026-10-07 报的）。
    # [EN] ── Previous version's palette (alternative): cinnabar orange base + ivory white fox. The shape
    # [EN] is also a front-facing head ──
    # [EN] ⚠ Don't use it as the default again: it's the one that clashed in feel with the UC browser
    # [EN] (reported by user 2026-10-07).
    'zhusha': {
        'name': '朱砂 · 狐印',
        'mark_shape':  'fox',
        'hue_range':   (10, 45),            # 暖橙（当年选定的亮橙 #e2601f 一族）
        'ground_top':    (233, 110, 48),    # 亮橙（上）
        'ground_bottom': (196, 74, 20),     # 沉橙（下）
        'ground_edge':   (150, 56, 14),     # 外圈细描边
        # [EN] Warm orange (the bright orange #e2601f family chosen back then)
        # [EN] Bright orange (top)
        # [EN] Deep orange (bottom)
        # [EN] Outer thin stroke
        'ground_gloss':  (255, 255, 255),
        'mark':          (255, 255, 255),   # 象牙白（记号）
        'mark_soft':     (255, 250, 243),   # 略暖的白（上淡下深用）
        # [EN] Ivory white (mark)
        # [EN] Slightly warm white (for light-top/dark-bottom)
    },
    'zhuye': {
        'name': '竹青 · 新绿',
        'mark_shape':  'bamboo',
        'hue_range':   (90, 200),
        'ground_top':    (236, 245, 238),   # 淡青瓷（上）
        'ground_bottom': (205, 227, 211),   # 淡青瓷（下）
        'ground_edge':   (108, 152, 120),   # 外圈细描边
        # [EN] Pale celadon (top)
        # [EN] Pale celadon (bottom)
        # [EN] Outer thin stroke
        'ground_gloss':  (255, 255, 255),
        'mark':          (44, 92, 68),      # 竹青墨绿（主记号）
        'mark_soft':     (74, 130, 96),     # 梢头略亮（竿身上淡下深）
        # [EN] Bamboo green ink green (primary mark)
        # [EN] Slightly brighter at the tip (stalk is light-top/dark-bottom)
    },
    'qingci': {
        'name': '青瓷 · 竹墨',
        'mark_shape':  'bamboo',
        'hue_range':   (90, 200),
        'ground_top':    (233, 242, 243),
        'ground_bottom': (203, 224, 227),
        'ground_edge':   (104, 144, 150),
        'ground_gloss':  (255, 255, 255),
        'mark':          (34, 84, 89),
        'mark_soft':     (62, 122, 128),
    },
}

DEFAULT_SCHEME = 'qinghuo'

# ══════════════════════════════════════════════════════════════
#  狐狸正脸（**画出来的**；2026-10-07 换掉上一版的侧影）
# [EN] Fox front-facing head (**drawn**; replaced the previous version's side profile on 2026-10-07)
#
#  ★ 归一化：y ∈ [0, 1]（0 = 耳尖，1 = 下巴尖），x ∈ [0, FACE_W]，
#    镜像轴在 FACE_W / 2。**只写右半边** —— 左右对称是几何保证的，
#    不靠眼睛比对（上一版是量出来的单条曲线，没有对称性可言）。
#  ★ 三段之间的**缝**就是耳尖的硬角，见 `_catmull_open()` 的说明。
# [EN] ★ Normalization: y ∈ [0, 1] (0 = ear tip, 1 = chin tip), x ∈ [0, FACE_W],
# [EN] mirror axis at FACE_W / 2. **Only write the right half** —— left-right symmetry is guaranteed
# [EN] geometrically,
# [EN] not verified by eye (the previous version was a single measured curve, with no symmetry to speak
# [EN] of).
# [EN] ★ The **seam** between the three segments is the hard angle at the ear tip; see the notes on
# [EN] `_catmull_open()`.
# ══════════════════════════════════════════════════════════════
FACE_W = 0.930           # 记号的宽（高恒为 1）→ 宽高比就是它
# [EN] Width of the mark (height is always 1) → the aspect ratio is it
FACE_CX = FACE_W / 2.0

#  ⚠ 别在颊部加"颊毛尖"之类的刺当特征：试过一版，最宽处当场掉到 65% 高度，
#    脸变成**下宽上窄**的水母（ASCII 里一眼看出）—— 狐狸正脸是**上宽下尖**，
#    最宽必须留在耳外缘那一带。判据「最宽的一行落在中段」就是钉这个的。
# [EN] ⚠ Don't add spikes like "cheek fur tips" on the cheeks as features: one version was tried, and
# [EN] the widest point immediately dropped to 65% height,
# [EN] turning the face into a **wide-bottom, narrow-top** jellyfish (obvious at a glance in ASCII) ——
# [EN] the fox's front face is **wide-top, narrow-bottom**;
# [EN] the widest point must stay around the outer edge of the ears. The criterion "the widest row
# [EN] falls in the middle section" pins exactly this.
#
#  ★ **只分两段**（下巴→脸颊→耳外缘→耳尖 / 耳尖→耳内缘→头顶）。
#    原来分三段（下巴→颊 / 颊→耳 / 耳内→头顶），段与段之间不插值，
#    可下巴→颊→耳那两段被切在了**脸颊中间** —— 于是脸颊上多出一个角。
#    用户 2026-10-07 说"曲线稍微圆润一些"，`probe_fox_roundness.py` 一量
#    就看见了：那处折痕。**合并成一段，折痕就没了。**
# [EN] ★ **Only two segments** (chin→cheek→ear outer edge→ear tip / ear tip→ear inner edge→top of
# [EN] head).
# [EN] Originally there were three segments (chin→cheek / cheek→ear / ear inner→top of head), with no
# [EN] interpolation between segments,
# [EN] but the chin→cheek→ear segments were cut in the **middle of the cheek** —— so an extra corner
# [EN] appeared on the cheek.
# [EN] The user said on 2026-10-07 "make the curve a bit rounder", and measuring with
# [EN] `probe_fox_roundness.py`
# [EN] revealed it: that crease. **Merging into one segment removes the crease.**
#
#  ★ **下巴的圆润靠"切线水平"**，不是靠把下巴抬高。轮廓在镜像轴上必然有个
#    顶点（左右两半在那里接上），那个顶点的**转角由到达时的切线方向决定**：
#    切线水平 → 左右两半接得平顺（转角≈0）；切线斜 → 就是一个尖角。
#    所以第一段第一个控制点给 `(CX, 1.000)`、**第二个给 `(0.520, 1.000)`**
#    （同一个 y）—— 下巴于是收成一个小圆头，而不是一根针。
#    实测：下巴从"一根针"（124°）变成小圆头；全轮廓最尖的两处终于是**耳尖**了。
#    头顶那个凹同理（末两点共 y）—— 否则它在镜像轴上又是个 45.8° 的角。
# [EN] ★ **The chin's roundness relies on "horizontal tangent"**, not on raising the chin. The contour
# [EN] must have an apex on the mirror axis
# [EN] (where the left and right halves meet), and that apex's **corner angle is determined by the
# [EN] tangent direction on arrival**:
# [EN] horizontal tangent → the two halves join smoothly (corner angle ≈ 0); slanted tangent → it's a
# [EN] sharp corner.
# [EN] So the first segment's first control point is `(CX, 1.000)`, and the **second is `(0.520,
# [EN] 1.000)`**
# [EN] (same y) —— the chin thus closes into a small round head instead of a needle.
# [EN] Measured: the chin went from "a needle" (124°) to a small round head; the two sharpest points on
# [EN] the whole contour are finally the **ear tips**.
# [EN] The dip at the top of the head is the same (last two points share y) —— otherwise it's another
# [EN] 45.8° corner on the mirror axis.
FACE_SEGS: tuple[tuple[tuple[float, float], ...], ...] = (
    # 1 下巴（小圆头）→ 下颌 → 脸颊 → 耳外缘（**全轮廓最宽处**）→ 耳尖
    # [EN] 1 Chin (small round head) → jaw → cheek → ear outer edge (**widest point of the whole contour**)
    # [EN] → ear tip
    ((FACE_CX, 1.000), (0.520, 1.000), (0.650, 0.900), (0.775, 0.755),
     (0.880, 0.596), (0.925, 0.430), (0.905, 0.190), (0.852, 0.010)),
    # 2 耳尖 → 耳内缘 → 耳根 → 头顶凹（U 形，不是尖 V）
    #   末两点**共用 y=0.402** → 到镜像轴时切线水平 → 那个凹是个圆滑的谷底，
    #   不是一个角（改之前量出来是 -45.8° 的角，`probe_fox_roundness.py` 看的）。
    # [EN] 2 Ear tip → ear inner edge → ear base → top-of-head dip (U shape, not a sharp V)
    # [EN] The last two points **share y=0.402** → the tangent is horizontal when reaching the mirror axis
    # [EN] → that dip is a smooth valley floor,
    # [EN] not a corner (before the change it measured as a -45.8° corner, as seen by
    # [EN] `probe_fox_roundness.py`).
    ((0.852, 0.010), (0.745, 0.140), (0.640, 0.272), (0.552, 0.372),
     (0.508, 0.402), (FACE_CX, 0.402)),
)

#: 眼睛（**镂空**）：一对上挑的杏仁，外眼角高、内眼角低 —— 狐狸的"狡黠"靠它。
#: `cx/cy` 是眼心（相对中轴 / 相对高度），`a/b` 是半长轴/半宽轴，`tilt` 是上挑角。
#: ⚠ 位置偏高（0.545）：往下压会读成"熊"。
# [EN] : Eyes (**hollowed out**): a pair of upturned almonds, outer corners high, inner corners low ——
# [EN] the fox's "cunning" comes from this.
# [EN] : `cx/cy` is the eye center (relative to the central axis / relative to height), `a/b` are the
# [EN] semi-major/semi-minor axes, `tilt` is the upward tilt angle.
# [EN] ⚠ Position is too high (0.545): pressing it down would read as a "bear".
FACE_EYE = {'cx': 0.118, 'cy': 0.545, 'a': 0.076, 'b': 0.031, 'tilt': 17.0}

FOX_ASPECT = FACE_W      # 宽 / 高（`verify_icon` 拿它判"没被拉伸"）
FOX_GLYPH = 0.70         # 记号高度占图标边长的比例。
                         # 起先是 0.78（对齐用户认可的 P3 观感），用户 2026-10-07
                         # 看过正脸之后要求"**不要全占满，周围留一点边**" → 收到 0.70
                         # （四周留白 15% of 边长；实测四边留白 ≈ 40px @256）。
                         # 判据「在框内留白充足」要求的是 ≥4%，这里给了 3 倍余量。
# [EN] Width / height (`verify_icon` uses it to check "not stretched")
# [EN] Ratio of the mark height to the icon's side length.
# [EN] Initially 0.78 (matching the user-approved P3 look), user on 2026-10-07
# [EN] after seeing the front face asked to "**not fill it completely, leave a bit of margin around
# [EN] it**" → changed to 0.70
# [EN] (margin of 15% of side length all around; measured margin on all four sides ≈ 40px @256).
# [EN] The criterion "sufficient margin inside the frame" requires ≥4%, here we give 3x the margin.


# ── 竹子几何（全部是相对 S 的比例，改一个数就能整体调形）──
# [EN] ── Bamboo geometry (all are ratios relative to S, change one number to adjust the whole shape)
# [EN] ──
#
# **三竿的根点挨得很近（间距 < 竿宽），所以根部天然叠在一起 → 剪影是一整块**，
# 这就是竹子"丛生"的长法（连通性断言靠这个成立，别把根点拉开）。
# 竿身各自略斜、高度错开，读起来才像一丛竹子而不是栅栏。
#      根点 x   根点 y   倾角(°)  竿宽    顶端 y（越小越高）
# [EN] **The root points of the three stalks are very close together (spacing < stalk width), so the
# [EN] roots naturally overlap → the silhouette is one solid block**,
# [EN] this is how bamboo's "clumping" growth looks (the connectivity assertion relies on this, don't
# [EN] spread the root points apart).
# [EN] The stalks are each slightly slanted with staggered heights, so it reads as a clump of bamboo
# [EN] rather than a fence.
# [EN] root x   root y   tilt(°)  stalk width    tip y (smaller = taller)
#
# 倾角给得大（±15°）：根部挨着、越往上分得越开 —— 才有"丛"的样子。
# 倾角小的话三竿全程平行，图标尺寸下就是一块带几道缝的绿板子，不成竹。
# [EN] Large tilt ( ±15°): roots are close together, and they spread further apart toward the top —
# [EN] that's what gives the "clump" look.
# [EN] With small tilt the three stalks stay parallel the whole way, and at icon size it's just a green
# [EN] board with a few slits, not bamboo.
STALKS = [
    (0.440,  0.859,  -17.0,   0.066,  0.330),
    (0.500,  0.835,    0.0,   0.082,  0.150),
    (0.558,  0.863,   18.0,   0.064,  0.360),
]
NODE_T = (0.26, 0.48, 0.70)   # 竹节在竿上的位置（0=根，1=梢）
NODE_H = 0.017                # 竹节厚度
NODE_W = 1.36                 # 竹节宽度 = 竿宽 × 这个倍数（略宽才看得出"箍"）
#                              ⚠ 别给太大（1.7 试过）：箍一宽就跟邻竿的叶子糊在一起，
#                              小尺寸下整丛变成一团绿，反而看不出是竹子。
# [EN] Position of the bamboo node on the stalk (0=root, 1=tip)
# [EN] Bamboo node thickness
# [EN] Bamboo node width = stalk width × this multiplier (slightly wider so the "band" is visible)
# [EN] ⚠ Don't make it too big (1.7 was tried): once the band is wide it smears together with the
# [EN] neighboring stalk's leaves,
# [EN] and at small sizes the whole clump becomes a green blob, no longer recognizable as bamboo.

# 叶子：(哪一竿, 竿上的位置 0~1, **方向角°**, 长, 宽)
# [EN] Leaves: (which stalk, position on stalk 0~1, **direction angle°**, length, width)
#
# ⚠ 方向角是**绝对角**（0° = 向右，-90° = 向上），不是"相对竿轴"。
# 第一版按"相对竿轴 ±50°"写，结果叶子全朝**下**摊开、糊成一团黑色 ——
# 竹子叶是往上斜着挑出去的，所以用的是 -40°（右上）和 -145°（左上）这一组。
# 位置都靠梢（t ≥ 0.84）：那里三竿分得最开，叶子才不会跟邻竿黏成一片。
# [EN] ⚠ The direction angle is an **absolute angle** (0° = right, -90° = up), not "relative to the
# [EN] stalk axis".
# [EN] The first version was written as "relative to the stalk axis ±50°", and the leaves all splayed
# [EN] **downward** into a black smear —
# [EN] bamboo leaves point diagonally upward, so this set uses -40° (upper right) and -145° (upper
# [EN] left).
# [EN] The positions are all near the tip (t ≥ 0.84): that's where the three stalks are most spread
# [EN] apart, so the leaves won't stick to the neighboring stalk.
LEAVES = [
    (1, 0.90,  -38, 0.135, 0.034),   # 中竿 · 右上
    (1, 0.99, -140, 0.120, 0.030),   # 中竿 · 左上
    (0, 0.86, -152, 0.135, 0.034),   # 左竿 · 左上（外）
    (0, 0.97,  -32, 0.100, 0.026),   # 左竿 · 右上（内，短）
    (2, 0.87,  -26, 0.130, 0.032),   # 右竿 · 右上（外）
    (2, 0.98, -148, 0.100, 0.026),   # 右竿 · 左上（内，短）
    # [EN] Middle stalk · upper right
    # [EN] Middle stalk · upper left
    # [EN] Left stalk · upper left (outer)
    # [EN] Left stalk · upper right (inner, short)
    # [EN] Right stalk · upper right (outer)
    # [EN] Right stalk · upper left (inner, short)
]

SS = 4            # 超采样倍数
_BOX = Image.Resampling.BOX    # **别用 LANCZOS**：斜边上会振铃，阈值一切出麻点
# [EN] Supersampling factor
# [EN] **Don't use LANCZOS**: it rings on slanted edges, and thresholding produces speckles


def scheme_names() -> list[str]:
    return list(SCHEMES)


def _catmull_open(pts, per_seg: int = 12):
    """**开放** Catmull-Rom：过所有控制点，两端拿端点自身当"虚拟邻居"。

    为什么不复用闭合版（上一版给侧影用的那个）：闭合样条是**处处切线连续**的
    —— 那正是侧影要的"没有硬角"，但在正脸上会把两只耳朵磨圆。
    正脸的耳尖靠**段与段之间不插值**来保住硬角：本函数只负责段内插值。
    
        English:
    **Open** Catmull-Rom: passes through all control points, and the two ends use the endpoints
    themselves as "virtual neighbors".
        Why not reuse the closed version (the one used for the profile in the previous version): a closed spline is **tangent-continuous everywhere**
        —— that is exactly the "no hard corners" the profile wanted, but on the front face it would round off the two ears.
        The front face's ear tips rely on **not interpolating between segments** to preserve hard corners: this function only handles interpolation within segments.
    """
    n = len(pts)
    if n < 3:
        return list(pts)
    ext = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, n):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t
                       + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                       + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3)
                for j in range(2)))
    out.append(pts[-1])
    return out


def face_outline() -> list[tuple[float, float]]:
    """狐狸正脸的**闭合轮廓**（归一化坐标）：右半边 → 镜像成左半边。

    段间不插值 → 耳尖是硬角；镜像 → 左右严格对称。
    
        English:
    The fox front face's **closed outline** (normalized coordinates): right half → mirror into the
    left half.
        No interpolation between segments → ear tips are hard corners; mirroring → strictly left-right symmetric.
    """
    right: list[tuple[float, float]] = []
    for seg in FACE_SEGS:
        pts = _catmull_open(seg)
        if right and pts and right[-1] == pts[0]:
            pts = pts[1:]                       # 接缝不重复
            # [EN] Seam does not repeat
        right += pts
    left = [(FACE_W - x, y) for x, y in reversed(right)][1:-1]
    return right + left


def _face_origin(W: int) -> tuple[float, float, float]:
    """`(缩放系数 k, 左上 x, 左上 y)` —— 等比居中，含 `FOX_GLYPH` 安全边距。
        English:
    `(scale factor k, top-left x, top-left y)` —— proportional centering, including the `FOX_GLYPH`
    safe margin.
    """
    k = W * FOX_GLYPH
    gw, gh = k * FACE_W, k
    return k, (W - gw) / 2.0, (W - gh) / 2.0


def fox_points(W: int) -> list[tuple[float, float]]:
    """正脸轮廓 → 画布像素坐标（等比居中）。

    ★ 缩放只能用 **一个** 系数 `k = W * FOX_GLYPH`：轮廓的 x 已经归一化到
      `0..FACE_W`（含宽高比），所以 `x_px = ox + x * k` 自动得到
      `gw = k * FACE_W` 的宽度。
      （上一版侧影在这里把长宽比乘了两次 —— 狐狸被纵向拉伸 1.26 倍，
      判据「宽高比与 FOX_ASPECT 一致」就是为它立的，留着别删。）
    
        English:
    Front-face outline → canvas pixel coordinates (proportional centering).
        ★ Scaling can only use **one** factor `k = W * FOX_GLYPH`: the outline's x is already normalized to
          `0..FACE_W` (including aspect ratio), so `x_px = ox + x * k` automatically yields
          a width of `gw = k * FACE_W`.
          (In the previous version's profile, the aspect ratio was multiplied twice here —— the fox got vertically stretched by 1.26x,
          and the criterion "aspect ratio matches FOX_ASPECT" was established for exactly this, keep it, don't delete it.)
    """
    k, ox, oy = _face_origin(W)
    return [(ox + x * k, oy + y * k) for x, y in face_outline()]


def fox_eye_rings(W: int) -> list[list[tuple[float, float]]]:
    """两只眼睛的像素多边形（`_fox_mask` 拿它**挖洞**）。
        English:
    Pixel polygons of the two eyes (`_fox_mask` uses them to **cut holes**).
    """
    k, ox, oy = _face_origin(W)
    out: list[list[tuple[float, float]]] = []
    for sx in (-1, 1):
        ecx = ox + (FACE_CX + sx * FACE_EYE['cx']) * k
        ecy = oy + FACE_EYE['cy'] * k
        ang = math.radians(-sx * FACE_EYE['tilt'])   # 外眼角上挑（y 向下 → 取负）
        # [EN] Outer eye corner tilts up (y is downward → take negative)
        ca, sa = math.cos(ang), math.sin(ang)
        ring = []
        n = 40
        for i in range(n):
            t = 2 * math.pi * i / n
            x, y = FACE_EYE['a'] * k * math.cos(t), FACE_EYE['b'] * k * math.sin(t)
            ring.append((ecx + x * ca - y * sa, ecy + x * sa + y * ca))
        out.append(ring)
    return out


# ══════════════════════════════════════════════════════════════
#  基础工具
# [EN] Basic utilities
# ══════════════════════════════════════════════════════════════
def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new('L', (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=radius, fill=255)
    return m


def _vgradient(size: int, top: tuple, bottom: tuple) -> Image.Image:
    strip = Image.new('RGB', (1, size))
    px = strip.load()
    for y in range(size):
        t = (y / max(1, size - 1)) ** 0.9
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return strip.resize((size, size), Image.Resampling.BILINEAR)


def _grain(size: int, seed: int = 17) -> Image.Image:
    import random
    rnd = random.Random(seed)
    sw = max(2, size // 4)
    noise = Image.new('L', (sw, sw))
    p = noise.load()
    for y in range(sw):
        for x in range(sw):
            p[x, y] = 128 + rnd.randint(-11, 11)
    noise = noise.resize((size, size), Image.Resampling.BICUBIC)
    return noise.filter(ImageFilter.GaussianBlur(max(0.4, size / 420.0)))


def _inset_shadow(size: int, radius: int, depth: int, color: tuple,
                  darkness: int = 90) -> Image.Image:
    outer = _rounded_mask(size, radius)
    inner = Image.new('L', (size, size), 0)
    ImageDraw.Draw(inner).rounded_rectangle(
        [depth, depth, size - 1 - depth, size - 1 - depth],
        radius=max(2, radius - depth), fill=255)
    ring = ImageChops.subtract(outer, inner).filter(
        ImageFilter.GaussianBlur(max(1.0, depth * 0.9)))
    layer = Image.new('RGBA', (size, size), color + (0,))
    layer.putalpha(ring.point(lambda v: int(v * darkness / 255)))
    return layer


def _rot(cx: float, cy: float, x: float, y: float, ang: float) -> tuple:
    """把相对 (cx, cy) 的点 (x, y) 绕 (cx, cy) 旋转 ang 弧度。
        English:
    Rotate the point (x, y) relative to (cx, cy) around (cx, cy) by ang radians.
    """
    ca, sa = math.cos(ang), math.sin(ang)
    return (cx + x * ca - y * sa, cy + x * sa + y * ca)


def _stalk_frame(i: int, W: int) -> tuple:
    """第 i 竿的根点、倾角（弧度）、竿宽、梢端 y。
        English:
    The i-th stalk's root point, tilt angle (radians), stalk width, tip y.
    """
    bx, by, ang_deg, w_ratio, top_ratio = STALKS[i]
    return (bx * W, by * W, math.radians(ang_deg),
            w_ratio * W, top_ratio * W)


def _rot_rect(d: ImageDraw.ImageDraw, bx: float, by: float, ang: float,
              half_w: float, y0: float, y1: float, round_end: bool = False) -> None:
    """画一根（可选圆头的）矩形杆：以 (bx, by) 为根，沿 ang 方向从 y0 到 y1。

    y0 > y1（因为根在下、梢在上，屏幕坐标 y 向下）。
    
        English:
    Draw a (optionally round-capped) rectangular rod: rooted at (bx, by), along the ang direction
    from y0 to y1.
        y0 > y1 (because the root is at the bottom and the tip is at the top, and screen coordinates have y pointing down).
    """
    pts = [(-half_w, y0), (half_w, y0), (half_w, y1), (-half_w, y1)]
    poly = [_rot(bx, by, x, y, ang) for x, y in pts]
    d.polygon(poly, fill=255)
    if round_end:
        cx, cy = _rot(bx, by, 0.0, y1, ang)
        d.ellipse([cx - half_w, cy - half_w, cx + half_w, cy + half_w], fill=255)
    # 根部也圆一点，免得三条竿交汇处出尖角
    # [EN] Make the root rounder too, to avoid a sharp corner where the three stalks meet
    cx, cy = _rot(bx, by, 0.0, y0, ang)
    d.ellipse([cx - half_w, cy - half_w, cx + half_w, cy + half_w], fill=255)


def _leaf(d: ImageDraw.ImageDraw, cx: float, cy: float, ang: float,
          length: float, width: float) -> None:
    """一片叶子：细长椭圆，一端扎在 (cx, cy)。
        English:
    A leaf: a slender ellipse, one end anchored at (cx, cy).
    """
    pts = []
    n = 28
    for i in range(n):
        t = 2 * math.pi * i / n
        # 椭圆的一端收在原点：把椭圆中心推到 length/2 处
        # [EN] One end of the ellipse is anchored at the origin: push the ellipse center to length/2
        x = length / 2 + (length / 2) * math.cos(t)
        y = (width / 2) * math.sin(t)
        pts.append(_rot(cx, cy, x, y, ang))
    d.polygon(pts, fill=255)


# ══════════════════════════════════════════════════════════════
#  记号剪影（**公开**：验证脚本按它判"是不是一整块""是不是竖的"）
# [EN] Mark silhouette (**public**: the verification script uses it to judge "is it one solid block"
# [EN] and "is it vertical")
# ══════════════════════════════════════════════════════════════
def mark_mask(size: int = 256, scheme: str = None) -> Image.Image:
    """记号剪影（L 模式）。超采样 + BOX 降采样得到抗锯齿的边。

    `scheme` 决定画哪个形状（看配色的 `mark_shape`）：
    `'fox'` = **狐狸正脸** / `'bamboo'` = 一丛竹子。
    缺省 = `DEFAULT_SCHEME`（也就是当前图标在用的那个），所以
    `verify_icon.check_silhouette()` 直接 `mark_mask(256)` 量的就是"当前图标"。
    
        English:
    Mark silhouette (L mode). Supersampling + BOX downsampling gives antialiased edges.
        `scheme` decides which shape to draw (see the color scheme's `mark_shape`):
        `'fox'` = **fox front face** / `'bamboo'` = a clump of bamboo.
        Default = `DEFAULT_SCHEME` (that is, the one the current icon uses), so
        `verify_icon.check_silhouette()` directly calling `mark_mask(256)` measures "the current icon".
    """
    S = int(size)
    sc = SCHEMES.get(scheme or DEFAULT_SCHEME) or SCHEMES[DEFAULT_SCHEME]
    if sc.get('mark_shape') == 'fox':
        return _fox_mask(S)
    return _bamboo_mask(S)


def _fox_mask(size: int) -> Image.Image:
    """狐狸**正脸**剪影：闭合多边形 + **挖掉两只眼睛**。

    ★ 眼睛为什么是"挖空"而不是"画上去"：挖空后透出的是**底色**，
      形状跟着记号走 —— 缩到 16px 时它糊成两个点，恰好还是"两只眼睛"；
      而"画两个白点"在小尺寸下会糊成一坨脏斑（边缘与底混色）。
      挖空还让记号天然带上一层"这是只动物"的信息量。
    
        English:
    Fox **front-face** silhouette: closed polygon + **the two eyes cut out**.
        ★ Why the eyes are "cut out" rather than "drawn on": after cutting out, what shows through is the **background color**,
          and the shape follows the mark —— when shrunk to 16px it blurs into two dots, which happen to still be "two eyes";
          whereas "drawing two white dots" at small sizes blurs into a dirty blob (edges blending with the background).
          Cutting out also gives the mark a natural layer of information value of "this is an animal".
    """
    S = int(size)
    W = S * SS
    m = Image.new('L', (W, W), 0)
    d = ImageDraw.Draw(m)
    d.polygon(fox_points(W), fill=255)
    for ring in fox_eye_rings(W):
        d.polygon(ring, fill=0)
    return m.resize((S, S), _BOX)


def _bamboo_mask(size: int) -> Image.Image:
    """竹子剪影（一丛三竿 + 竹节 + 叶）。
        English:
    Bamboo silhouette (one clump of three stalks + bamboo nodes + leaves).
    """
    S = int(size)
    W = S * SS
    m = Image.new('L', (W, W), 0)
    d = ImageDraw.Draw(m)

    for i in range(len(STALKS)):
        bx, by, ang, sw, top = _stalk_frame(i, W)
        half = sw / 2.0
        y_root = 0.0
        y_tip = -(by - top)                      # 相对根点向上
        # [EN] Upward relative to the root point
        _rot_rect(d, bx, by, ang, half, y_root, y_tip, round_end=True)
        # 竹节：比竿略宽的短横箍（**加**出来的，不切断竿 → 不破坏连通性）
        # [EN] Bamboo node: a short band slightly wider than the stalk (**added**, not cutting the stalk →
        # [EN] doesn't break connectivity)
        for t in NODE_T:
            ny = y_tip * t
            ncx, ncy = _rot(bx, by, 0.0, ny, ang)
            _rot_rect(d, ncx, ncy, ang, half * NODE_W, -NODE_H * W / 2.0,
                      NODE_H * W / 2.0)

    # 叶子：根部扎进竿里（保证连通）
    # [EN] Leaves: the base is inserted into the stalk (guarantees connectivity)
    for i, t, off, ln, wd in LEAVES:
        bx, by, ang, sw, top = _stalk_frame(i, W)
        y = -(by - top) * t
        lx, ly = _rot(bx, by, 0.0, y, ang)
        # 往竿轴里退一点，让叶柄与竿实实在在地叠上
        # [EN] Back off a bit into the stalk axis, so the petiole and the stalk truly overlap
        lx, ly = _rot(lx, ly, -sw * 0.25, 0.0, ang)
        _leaf(d, lx, ly, ang + math.radians(off), ln * W, wd * W)

    return m.resize((S, S), _BOX)


def _paint_mark(size: int, mask: Image.Image, sc: dict) -> Image.Image:
    """给剪影上色：上淡下深的竖向渐变（清新、又不失"剪影"的整体感）。
        English:
    Colorize the silhouette: vertical gradient from light at top to dark at bottom (fresh, while
    still keeping the overall "silhouette" feel).
    """
    S = int(size)
    grad = _vgradient(S, sc['mark_soft'], sc['mark']).convert('RGBA')
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    return Image.composite(grad, out, mask)


def generate_icon(size: int = 512, scheme: str = DEFAULT_SCHEME) -> Image.Image:
    """生成应用图标（RGBA）。
        English:
    Generate the app icon (RGBA).
    """
    S = int(size)
    # ★ 有源图就**一律走源图**：换 Logo 只换 `assets/images/icon_source.png`，
    #   五份产物 + 窗口 + 任务栏全部跟着走，不需要改这里的绘制代码。
    # [EN] ★ If a source image exists, **always use it**: swapping the logo only means replacing
    # [EN] `assets/images/icon_source.png`; all five artifacts + window + taskbar follow along,
    # [EN] and there's no need to touch the drawing code here.
    src = source_image()
    if src is not None:
        return icon_from_source(S, src)

    sc = SCHEMES.get(scheme) or SCHEMES[DEFAULT_SCHEME]
    radius = int(S * 0.22)
    margin = max(0, int(S * 0.02))

    # 淡青底：竖向渐变
    # [EN] Pale cyan background: vertical gradient
    img = _vgradient(S, sc['ground_top'], sc['ground_bottom']).convert('RGBA')

    # 顶部高光（很淡 —— 清新风靠留白，不靠厚涂）
    # [EN] Top highlight (very faint — the fresh style relies on whitespace, not thick painting)
    gloss = Image.new('L', (S, S), 0)
    gd = ImageDraw.Draw(gloss)
    h = int(S * 0.38)
    for y in range(h):
        t = y / max(1, h - 1)
        gd.line([(0, y), (S, y)], fill=int(40 * (1 - t) ** 1.7))
    gloss = gloss.filter(ImageFilter.GaussianBlur(max(1.0, S / 60.0)))
    layer = Image.new('RGBA', (S, S), sc['ground_gloss'] + (0,))
    layer.putalpha(gloss)
    img = Image.alpha_composite(img, layer)

    # 极轻的纸纹
    # [EN] Very light paper texture
    g = _grain(S)
    img = ImageChops.blend(img.convert('RGB'),
                           Image.merge('RGB', (g, g, g)), 0.045).convert('RGBA')

    # 记号（狐狸正脸 / 一丛竹子 —— 由配色的 `mark_shape` 决定）
    # [EN] Mark (fox front face / a clump of bamboo — determined by the palette's `mark_shape`)
    img = Image.alpha_composite(img, _paint_mark(S, mark_mask(S), sc))

    # 边缘内阴影
    # [EN] Inner shadow on edges
    img = Image.alpha_composite(img, _inset_shadow(S, radius,
                                                   max(1, int(S * 0.028)),
                                                   sc['ground_edge'], 96))
    # 圆角 + 细描边
    # [EN] Rounded corners + thin stroke
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), _rounded_mask(S, radius))
    rim = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle(
        [margin, margin, S - 1 - margin, S - 1 - margin],
        radius=max(2, radius - margin),
        outline=sc['ground_edge'] + (150,), width=max(1, int(S * 0.007)))
    out = Image.alpha_composite(out, rim)
    return out


APP_ROOT = Path(__file__).resolve().parent.parent

# 全套产物（**五份**，缺一不可）：
#   assets/images/icon.png      512 母版（备份 / 文档用）
#   assets/images/icon_256.png  256（预览、对比用）
#   assets/images/icon.ico      多尺寸（打包/安装程序用）
#   assets/app_icon.png         256（Flet `window.icon`，路径要相对 assets）
#   assets/app_icon.ico         多尺寸（Win32 `WM_SETICON` 设**任务栏**图标）
# [EN] Full set of outputs (**five**, none may be missing):
# [EN] assets/images/icon.png      512 master (for backup / documentation)
# [EN] assets/images/icon_256.png  256 (for preview, comparison)
# [EN] assets/images/icon.ico      multi-size (for packaging/installer)
# [EN] assets/app_icon.png         256 (Flet `window.icon`, path must be relative to assets)
# [EN] assets/app_icon.ico         multi-size (Win32 `WM_SETICON` sets the **taskbar** icon)
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

#: ★ 图标**源图**（成品图，1024×1024）。**有它就用它**，没有才退回程序绘制。
#: 换 Logo 的正确姿势 = 换这张图：五份产物、窗口图标、任务栏图标会一起跟着走，
#: 不用再手工去覆盖 `app_icon.*`（覆盖了也会被判据判"和当前方案不一致"）。
# [EN] ★ Icon **source image** (finished artwork, 1024x1024). **If it exists, it is used**;
# [EN] only when it's missing do we fall back to programmatic drawing.
# [EN] The correct way to swap the logo = swap this image: the five artifacts, the window icon
# [EN] and the taskbar icon all follow along; you no longer hand-overwrite `app_icon.*`
# [EN] (overwriting would be judged "inconsistent with the current scheme" by the verification).
ICON_SOURCE = APP_ROOT / 'assets' / 'images' / 'icon_source.png'

#: 源图模式下仍保留的圆角比例（与程序绘制时一致，保证形状不跳变）
# [EN] Corner radius kept in source mode (same as programmatic drawing, so the shape doesn't jump)
SRC_RADIUS = 0.22


def source_image() -> 'Image.Image | None':
    """读源图（RGBA）；没配源图就返回 `None`（走程序绘制那条老路）。
        English:
    Read the source image (RGBA); returns `None` if no source image is configured
    (falls back to the old programmatic drawing path).
    """
    try:
        if ICON_SOURCE.exists():
            im = Image.open(ICON_SOURCE)
            im.load()
            return im.convert('RGBA')
    except Exception:
        return None
    return None


def icon_from_source(size: int, src: 'Image.Image') -> 'Image.Image':
    """用源图出图标：`size` 见方，圆角裁切。

    ★ 为什么**逐级降采样**而不是一步缩到 16：一步缩会让细尾巴在 16px 上断成
      几截（LANCZOS 的采样窗盖不住那么大的倍率），逐级（512→256→128→…）每一级
      都还在"看得清"的范围内，最后那张 16px 才保得住狐狸的整体形状。
      
        English:
    Build the icon from the source image: `size` square, with rounded corners.
        ★ Why **downscale step by step** instead of shrinking straight to 16: one step makes the thin
          tail break into pieces at 16px (LANCZOS's sampling window can't cover such a large ratio),
          while going step by step (512→256→128→...) keeps every level within the "still legible"
          range, so the final 16px image preserves the fox's overall shape.
    """
    S = int(size)
    cur = src
    # 先压到 512（源图是 1024，母版用不到更大）
    # [EN] First squeeze to 512 (the source is 1024; the master doesn't need larger)
    if cur.width > 512:
        cur = cur.resize((512, 512), Image.Resampling.LANCZOS)
    while cur.width > S and cur.width > 8:
        nxt = max(S, cur.width // 2)
        cur = cur.resize((nxt, nxt), Image.Resampling.LANCZOS)
    if cur.width != S:
        cur = cur.resize((S, S), Image.Resampling.LANCZOS)

    radius = int(S * SRC_RADIUS)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(cur, (0, 0), _rounded_mask(S, radius) if S >= 8 else None)
    return out


def _ico_frames(size: int) -> list:
    """给 `.ico` 备好每一档的图（**逐级降采样**，别让 Pillow 一步缩到底）。
        English:
    Prepare the image for every `.ico` step (**downscale progressively**, don't let Pillow
    shrink to the bottom in one go).
    """
    src = source_image()
    frames = []
    for s in ICO_SIZES:
        w = min(s[0], size)
        if src is not None:
            frames.append(icon_from_source(w, src))
        else:
            sc = SCHEMES.get(DEFAULT_SCHEME) or SCHEMES[DEFAULT_SCHEME]
            frames.append(generate_icon(w, DEFAULT_SCHEME) if w > 256 else
                          _downscale(generate_icon(256, DEFAULT_SCHEME), w))
    return frames


def _save_ico(master: 'Image.Image', path: 'Path', size: int) -> None:
    """存多尺寸 `.ico`：每一档都用**逐级降采样**出来的图，不让 Pillow 一步缩到底。

    ★ 顺序按尺寸**降序**给（第一档 256 = 主图，其余走 `append_images`）：
      Pillow 的 ico 保存是"主图 → `sizes[0]`、其余按 `append_images` 顺序"，
      顺序给错就会拿 512 母版一步缩成 16 —— 那正是小尺寸糊掉的原因。
      
        English:
    Save a multi-size `.ico`: every step uses an image produced by **progressive downscaling**, never
    letting Pillow shrink all the way in one step.
        ★ The order is given by size **descending** (first step 256 = master, the rest go through
          `append_images`): Pillow's ico saving is "master → `sizes[0]`, the rest in `append_images`
          order"; giving the wrong order makes it shrink the 512 master straight to 16 -- exactly why
          small sizes turn to mush.
    """
    frames = _ico_frames(size)
    by_w = {f.width: f for f in frames}
    order = sorted({min(s[0], int(size)) for s in ICO_SIZES}, reverse=True)
    main = by_w.get(order[0]) or master
    rest = [by_w[s] for s in order[1:] if s in by_w]
    main.save(path, sizes=[(s, s) for s in order], append_images=rest)


def _downscale(im: 'Image.Image', size: int) -> 'Image.Image':
    """逐级降采样到 `size`（程序绘制那条路也用它，保证小尺寸不糊）。
        English:
    Progressively downscale to `size` (the programmatic path uses it too, so small sizes stay sharp).
    """
    cur = im
    while cur.width > max(8, size) and cur.width > 8:
        nxt = max(size, cur.width // 2)
        cur = cur.resize((nxt, nxt), Image.Resampling.LANCZOS)
    if cur.width != size:
        cur = cur.resize((size, size), Image.Resampling.LANCZOS)
    return cur


def icon_signature() -> str:
    """图标代码的指纹（源码 + 当前配色）。

    **为什么需要它**：光判\"文件存不存在\"是不够的 —— 换了图标之后旧文件还在，
    界面、窗口、任务栏三处就都还是旧图（用户提过：
    「换图标的时候记得任务栏图标也换掉」）。
    指纹一变就重做全套产物，换图标这件事就不再有\"忘了哪一份\"的余地。
    
        English:
    Fingerprint of the icon code (source + current colors).
        **Why it's needed**: just checking "whether the file exists" isn't enough -- after swapping the icon the old file is still there,
        and all three places (UI, window, taskbar) still show the old image (the user mentioned:
        "when you change the icon, remember to change the taskbar icon too").
        Once the fingerprint changes, the full set of artifacts is regenerated, so changing the icon no longer leaves any room for "forgetting which one".
    """
    import hashlib
    h = hashlib.sha1(
        Path(__file__).read_bytes() + DEFAULT_SCHEME.encode('utf-8')
    )
    # ★ 源图也要进指纹：**换图 = 换指纹** ⇒ 产物重做、快捷方式那份带指纹的
    #   副本路径也变，任务栏就不会继续画缓存里的旧图标。
    # [EN] ★ The source image must be part of the fingerprint too: **swapping the image = swapping the
    # [EN] fingerprint** ⇒ the artifacts are regenerated and the fingerprinted copy used by the
    # [EN] shortcut changes path, so the taskbar won't keep drawing the stale icon from its cache.
    try:
        if ICON_SOURCE.exists():
            h.update(b'|src|' + ICON_SOURCE.read_bytes())
    except Exception:
        pass
    return h.hexdigest()[:16]


def save_icons(out_dir: Path | str = None, size: int = 512,
               scheme: str = DEFAULT_SCHEME,
               app_dir: Path | str = None) -> dict:
    """生成并保存**全套**图标产物（界面三份 + 窗口/任务栏两份）。

    返回 `{'png','png256','ico','app_png','app_ico'}` —— 键名保持旧接口不变
    （`make_art.py` / `tools/verify_icon.py` 都在用），后面两个是新增的。
    
        English:
    Generate and save the **full set** of icon artifacts (three for the UI + two for
    window/taskbar).
        Returns `{'png','png256','ico','app_png','app_ico'}` -- key names keep the old interface unchanged
        (`make_art.py` / `tools/verify_icon.py` are both using it); the last two are newly added.
    """
    out_dir = Path(out_dir) if out_dir else APP_ROOT / 'assets' / 'images'
    out_dir.mkdir(parents=True, exist_ok=True)
    app_dir = Path(app_dir) if app_dir else APP_ROOT / 'assets'
    app_dir.mkdir(parents=True, exist_ok=True)

    icon = generate_icon(size, scheme)
    png_path = out_dir / 'icon.png'
    icon.save(png_path)

    small = generate_icon(256, scheme)
    p256 = out_dir / 'icon_256.png'
    small.save(p256)

    ico_path = out_dir / 'icon.ico'
    _save_ico(icon, ico_path, size)

    # 窗口 / 任务栏用的两份：**和上面同一张图**，不能各画各的。
    # [EN] The two for window / taskbar: **the same image as above**, they must not be drawn separately.
    app_png = app_dir / 'app_icon.png'
    small.save(app_png)
    app_ico = app_dir / 'app_icon.ico'
    _save_ico(small, app_ico, 256)

    return {'png': png_path, 'png256': p256, 'ico': ico_path,
            'app_png': app_png, 'app_ico': app_ico}


#: 图标产物的指纹戳（内容 = `icon_signature()`）
# [EN] : fingerprint stamp of the icon outputs (content = `icon_signature()`)
ICON_STAMP = APP_ROOT / 'assets' / '.icon_stamp'

#: 五份产物的固定路径（**不要改名**：界面 / 窗口 / 任务栏都按这些名字取）
# [EN] : fixed paths of the five outputs (**don't rename**: UI / window / taskbar all fetch them by
# [EN] these names)
ICON_PATHS: dict[str, tuple[str, str]] = {
    'png':     ('assets/images', 'icon.png'),
    'png256':  ('assets/images', 'icon_256.png'),
    'ico':     ('assets/images', 'icon.ico'),
    'app_png': ('assets',        'app_icon.png'),
    'app_ico': ('assets',        'app_icon.ico'),
}


def asset_paths() -> dict[str, Path]:
    """五份产物的绝对路径。

    ⚠ 路径从 **`APP_ROOT`**（= 本文件的上上层）推，**不接参数**：
    在发布包里 `__file__` 就是发布包那份 `icon.py`，`APP_ROOT` 自动指向发布包根，
    所以同一份代码在工程里和发布包里都对 —— 不需要调用方传根目录
    （传了反而多一个"传错了"的机会）。
    
        English:
    Absolute paths of the five artifacts.
        ⚠ The path is derived from **`APP_ROOT`** (= the parent of the parent of this file), **no arguments accepted** :
        in the release package `__file__` is the `icon.py` in the release package, and `APP_ROOT` automatically points to the release package root,
        so the same code works both in the project and in the release package -- the caller doesn't need to pass the root directory
        (passing it just adds one more chance to "pass it wrong").
    """
    return {k: APP_ROOT / d / n for k, (d, n) in ICON_PATHS.items()}


def assets_up_to_date() -> bool:
    """产物是不是**当前这版图标**画出来的（比"文件在不在"严一层）。
        English:
    Whether the artifacts were drawn from **the current version of the icon** (stricter than "is the
    file there").
    """
    stamp = ICON_STAMP
    try:
        sig = icon_signature()
    except Exception:                                            # noqa: BLE001
        return False
    if not sig or not stamp.exists():
        return False
    try:
        if stamp.read_text(encoding='utf-8').strip() != sig:
            return False
    except OSError:
        return False
    return all(p.exists() for p in asset_paths().values())


def ensure_assets(force: bool = False, *, log=None) -> dict:
    """把**全套**图标产物对齐到当前图标代码，返回各文件路径。

    **为什么不能只看"文件在不在"**：先前三处（界面图标 / 窗口图标 / 任务栏图标）
    各自写着「不存在才生成」，结果是**换了图标之后旧文件还在、谁也没去重做** ——
    界面、窗口、任务栏三处继续用旧图。用户当时的原话是
    「换图标的时候记得任务栏图标也换掉」。
    现在按 `icon_signature()`（`icon.py` 源码 + 当前配色的指纹）判定：
    对不上就重做全套五份。

    ★ **为什么它是公开函数、而且住在 `image_gen/` 里**（2026-10-07 从
      `gui/app_flet.py` 搬来的）：**安装器也要用它**。
      用户报「setup 跑完桌面图标还是老图标」—— 因为 `platform_install.py`
      只**读**现成的 `assets/app_icon.ico`，而产物的刷新一直只发生在
      **启动程序**时。于是"改图标 → 直接跑 setup（没先启动程序）"装的就是旧图。
      可安装器不能 `import gui.app_flet`（那会把整个 Flet 界面拉起来），
      所以这段逻辑必须住在**双方都能用、又都不依赖界面**的地方 —— 就是这里。

    `log` 是可选回调（收一行字符串）；不传就什么都不说（安装器按自己的口径打）。
    
        English:
    Align the **full set** of icon artifacts to the current icon code, return each file path.
        **Why we can't just look at "is the file there"**: previously the three places (UI icon / window icon / taskbar icon)
        each had their own "generate only if it doesn't exist", so the result was **after swapping the icon the old files are still there and nobody regenerated them** --
        the UI, window, and taskbar kept using the old images. The user's exact words at the time were
        "when you change the icon, remember to change the taskbar icon too".
        Now it's judged by `icon_signature()` (fingerprint of `icon.py` source + current colors):
        if it doesn't match, regenerate the full set of five.
        ★ **Why it's a public function and lives in `image_gen/`** (moved from
          `gui/app_flet.py` on 2026-10-07): **the installer needs it too**.
          A user reported "after setup runs the desktop icon is still the old icon" -- because `platform_install.py`
          only **reads** the existing `assets/app_icon.ico`, and refreshing the artifacts has only ever happened when
          **the program starts**. So "change icon -> run setup directly (without starting the program first)" installs the old image.
          But the installer can't `import gui.app_flet` (that would bring up the whole Flet UI),
          so this logic must live in a place **that both sides can use and that doesn't depend on the UI** -- which is here.
        `log` is an optional callback (receives one string line); if not passed it says nothing (the installer logs in its own way).
    """
    paths = asset_paths()
    try:
        sig = icon_signature()
    except Exception as e:                                       # noqa: BLE001
        if log:
            log(f'图标指纹算不出来（{e}）—— 沿用现有产物')
        return paths

    fresh = assets_up_to_date()
    if not force and fresh:
        return paths

    try:
        res = save_icons(paths['png'].parent, app_dir=APP_ROOT / 'assets')
    except Exception as e:                                       # noqa: BLE001
        if log:
            log(f'图标生成失败（{e}）—— 沿用现有产物')
        return paths
    try:
        ICON_STAMP.parent.mkdir(parents=True, exist_ok=True)
        ICON_STAMP.write_text(sig or 'unknown', encoding='utf-8')
    except OSError:
        pass
    if log:
        log('图标产物已按当前设计重做' if not fresh else '图标产物已强制重做')
    return res


def versioned_ico(*, copy: bool = True) -> Path | None:
    """**给快捷方式用的** .ico：把当前那份复制成带指纹的名字，返回它。

    为什么非要换个名字（2026-10-07，用户报「setup 跑完桌面图标还是老图标」）：
    ----------------------------------------------------------------
    Windows 的图标缓存**是按路径认的**。`.lnk` 里的 `IconLocation` 一直是
    `assets\app_icon.ico`，路径没变 —— 哪怕文件内容已经换成新图标，
    资源管理器照样拿缓存里那张旧图来画。用户看到的就正是"图标还是老的"。

    把给快捷方式用的那份复制成 `app_icon.<指纹前8位>.ico`：
    **路径变了 → 缓存必然 miss → 桌面一定重读**。换一次图标换一个文件名，
    这件事从机制上就不会再发生（不是靠清缓存撞运气）。

    ⚠ 只复制**给快捷方式的副本**；`assets/app_icon.ico` 仍是原名 ——
      窗口与任务栏（Flet / Win32 `WM_SETICON`）按那个固定名取，不能动。
    ⚠ 卸载**不删**这个副本：它是程序自己的资源（在 `assets/` 里），
      不是安装产物（见 `platform_install` 的 manifest 说明）。
    
        English:
    **For the shortcut** .ico: copy the current one to a fingerprint-named file, return it.
        Why we must change the name (2026-10-07, user reported "after setup runs the desktop icon is still the old icon"):
        ----------------------------------------------------------------
        Windows icon cache **identifies by path**. The `IconLocation` in the `.lnk` has always been
        `assetspp_icon.ico`, the path hasn't changed -- even if the file contents have been replaced with the new icon,
        Explorer still draws the old cached image. What the user sees is exactly "the icon is still old".
        Copy the one used for the shortcut to `app_icon.<first 8 chars of fingerprint>.ico`:
        **path changed -> cache必然 miss -> desktop必然会 re-read**. Change the icon once and the filename changes,
        so this can no longer happen by mechanism (not by luck of clearing the cache).
        ⚠ Only copy **the shortcut's copy**; `assets/app_icon.ico` keeps its original name --
          the window and taskbar (Flet / Win32 `WM_SETICON`) fetch by that fixed name and it mustn't be touched.
        ⚠ Uninstall **does not delete** this copy: it's the program's own resource (in `assets/`),
          not an install artifact (see the manifest notes in `platform_install`).
    """
    src = APP_ROOT / 'assets' / 'app_icon.ico'
    if not src.exists():
        alt = APP_ROOT / 'assets' / 'images' / 'icon.ico'
        src = alt if alt.exists() else None
        if src is None:
            return None
    try:
        sig = icon_signature()[:8]
    except Exception:                                            # noqa: BLE001
        sig = ''
    if not sig:
        return src
    dst = src.with_name(f'{src.stem}.{sig}.ico')
    if copy:
        try:
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                dst.write_bytes(src.read_bytes())
            _prune_versioned(src, keep=dst)
        except OSError:
            return src
    return dst if dst.exists() else src


def _prune_versioned(src: Path, *, keep: Path) -> None:
    """清掉过期的 `app_icon.<旧指纹>.ico`（只留当前那份，别把目录堆满）。
        English:
    Clean up stale `app_icon.<old fingerprint>.ico` (keep only the current one, don't pile up the
    directory).
    """
    for old in src.parent.glob(f'{src.stem}.*.ico'):
        if old == keep:
            continue
        # 只删"看起来像指纹"的（8 位十六进制），别误删别的东西
        # [EN] Only delete things that "look like a fingerprint" (8-digit hex), don't accidentally delete
        # [EN] anything else
        mid = old.name[len(src.stem) + 1:-4]
        if len(mid) == 8 and all(c in '0123456789abcdef' for c in mid):
            try:
                old.unlink()
            except OSError:
                pass


def debug_ascii(size: int = 72) -> str:
    """把剪影打成字符画（改几何时用，肉眼校形）。

    本机模型**读不了图片**（`Read` 一个 .png 会直接报不支持），
    所以改形状时这是唯一能"看见"它的手段 —— 上一版的"被纵向拉伸 1.26 倍"
    就是这么发现的。
    
        English:
    Render the silhouette as ASCII art (used when editing geometry, to eyeball-check the shape).
        The local model **can't read images** (`Read` on a .png directly reports unsupported),
        so this is the only way to "see" it when editing the shape -- the previous version's "stretched vertically by 1.26x"
        was discovered exactly this way.
    """
    m = mark_mask(size)
    px = m.load()
    step = max(1, size // 60)
    return '\n'.join(''.join('#' if px[x, y] > 127 else '.' for x in range(0, size, step))
                     for y in range(0, size, step))


if __name__ == '__main__':
    import sys
    if '--ascii' in sys.argv:
        print(debug_ascii(80))
    else:
        sch = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCHEME
        for k, v in save_icons(scheme=sch).items():
            print(f'{k}: {v}')
