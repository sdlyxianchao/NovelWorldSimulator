# -*- coding: utf-8 -*-
"""真机验证：开始界面菜单 —— 「回　卷」的位置与灰化、每项下面那行小字、八项图标。

校验六件事：
  1. 无项目时「回　卷」**灰掉不可点**，并给出可读的原因（不是空着）
  2. 有项目时同一项变成可用
  3. 点它 → 真的切到运行界面（app._view == 'main'）
  4. **说明文字是人话**：每项都有说明、够短（不折行）、不出现「调天地之序」这类
     半文半白的旧词（用户原话："直白一些，不然大家看不懂什么意思"）
  5. **八项都挂着彩色图标**，且**不可点的那几项挂的是褪色版**（图标与标题一起灰）
  6. ★ **像素级**：那八张图**真的画到了屏幕上**（数两张截图的彩色像素差）——
     前五条读的都是控件属性，"src 对、画出来是个破图"它们一个都看不见

⚠ 第 5 条只管"界面挂对了没有"。素材本身（在不在、是不是彩色的、灰化版真的灰吗）
  由 `tools/verify_menu_icons.py` 单独管 —— 那支不用起界面，跑得快。

产出：assets/screenshots/menu_resume_1_disabled.png / menu_resume_2_enabled.png
      assets/screenshots/menu_resume_report.json

English:
Real-machine verification: start screen menu -- the position and dimming of 「回 卷」, the small
text under each item, the eight icons.
Verify six things:
  1. When there are no projects, 「回　卷」 is **dimmed and non-clickable**, and gives a readable reason (not empty)
  2. When projects exist, the same item becomes available
  3. Click it -> actually switches to the run view (app._view == 'main')
  4. **Description text is plain speech**: every item has a description, short enough (doesn't wrap), and doesn't show old half-classical phrases like 「调天地之序」
     (user's own words: "make it direct, otherwise nobody understands what it means")
  5. **All eight items have colored icons attached**, and **the non-clickable ones have the faded version** (icon dimmed together with the title)
  6. ★ **Pixel-level**: those eight images are **actually drawn on the screen** (count the colored-pixel difference between the two screenshots) --
     the first five read widget properties, "src is right but it renders as a broken image" -- none of them can see that
⚠ Item 5 only covers "is the UI hooked up right". The asset itself (present or not, colored or
not, is the dimmed version really dim)
  is handled separately by `tools/verify_menu_icons.py` -- that one doesn't need to bring up the UI, so it runs fast.
Output: assets/screenshots/menu_resume_1_disabled.png / menu_resume_2_enabled.png
      assets/screenshots/menu_resume_report.json
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
from PIL import Image, ImageChops  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from gui.app_flet import NovelWorldApp  # noqa: E402
from store.project import Project  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

ORDER = ['开　卷', '拾　卷', '起　笔', '拆　书', '天　机', '书　斋',
         '回　卷', '归　去']
# ★ 2026-10-10 补上「拆　书」：它 2026-10-07 加进菜单时**没进这张表**，
#   而 `find_menu_items` 只收"值在这张表里"的 Text ⇒ 那一项**从来没被这一支
#   查过**（顺序、说明长度、灰化规则全都没覆盖）。补进来才叫"逐项都测到"。
# [EN] ★ 2026-10-10 Added "拆书": when it was added to the menu on 2026-10-07, it **did not enter this
# [EN] table**,
# [EN] and `find_menu_items` only accepts Text whose "value is in this table" ⇒ that entry was **never
# [EN] by this branch
# [EN] checked** (order, description length, dimming rules were all uncovered). Only after adding it
# [EN] can we claim "every entry is tested."

#: 菜单图标（**每一轮换图标，这张表就是那一轮的落点**）。
#: ★ 钉的是**渲染出来的 `ft.Image.src`**（取文件名），不是源码里的字符串 ——
#:   源码写对名字、运行时却挂不上去（文件不在 → `mk_menu_icon` 降级成"破图"图标），
#:   只有真机取得到。素材本身对不对由 `tools/verify_menu_icons.py` 单独管。
# [EN] : menu icons (**the icon is changed every round; this table is that round's landing point**).
# [EN] : ★ What is pinned is the **rendered `ft.Image.src`** (take the filename), not the string in the
# [EN] source code --
# [EN] : source code has the right name, but at runtime it can't be attached (file missing →
# [EN] `mk_menu_icon` degrades to the "broken image" icon),
# [EN] : only a real machine can retrieve it. Whether the asset itself is correct is managed separately
# [EN] by `tools/verify_menu_icons.py`.
EXPECT_ICON = {
    '开　卷': 'open_book',
    '拾　卷': 'books',
    '起　笔': 'play',
    # 用户 2026-10-10：「初始界面的拆书 …… 图标改成拼图图标」
    # [EN] User 2026-10-10: "The 拆书 on the initial screen ... change the icon to a puzzle icon"
    '拆　书': 'puzzle',
    # 用户 2026-10-10：「天机 按照全局设置的意思找一个图标」
    # [EN] User 2026-10-10: "For 天机, find an icon according to the meaning of global settings"
    '天　机': 'gear',
    '书　斋': 'brush',
    # 用户 2026-10-10：「Resume 的图标改成一个横线在下面，
    #                   箭头在上面往左的逆时针箭头」
    # ⚠ 那个字形 emoji 里没有（见 assets/images/menu_icons/README.md），
    #   现在挂的是语义最贴的「倒回」；换候选要同时改这里与生成脚本。
    # [EN] User 2026-10-10: "Change the Resume icon to a horizontal line below,
    # [EN] with an arrow above pointing left, a counterclockwise arrow"
    # [EN] ⚠ That glyph is not in the emoji set (see assets/images/menu_icons/README.md),
    # [EN] currently the semantically closest "rewind" is attached; to change the candidate, both here and
    # [EN] the generation script must be modified.
    '回　卷': 'rewind',
    # 用户 2026-10-10：「归去的图标 强化一下门和从门里离开的意思」
    # [EN] User 2026-10-10: "For the 归去 icon, strengthen the meaning of a door and leaving through the
    # [EN] door"
    '归　去': 'door',
}
#: **不可点**的那几项挂的该是褪色版（`<槽位>_dim.png`）—— 图标与标题一起灰
# [EN] : The **non-clickable** entries should have the faded version attached (`<slot>_dim.png`) --
# [EN] icon and title grayed together
DIM_SUFFIX = '_dim.png'
#: 素材目录（与 `gui/app_flet.py` 的 `MENU_ICON_DIR` 同源）
# [EN] : Asset directory (same source as `MENU_ICON_DIR` in `gui/app_flet.py`)
ICON_DIR = APP_DIR / 'assets' / 'images' / 'menu_icons'
#: 菜单**该有几项**（`ORDER` 的长度就是它；单列一个常量只为让报错能说人话）
# [EN] : How many entries the menu **should have** (`ORDER`'s length is it; a separate constant is only
# [EN] so errors can be human-readable)
N_ITEMS = len(ORDER)

# 说明文字的可读性口径。**短是硬要求**（用户："太长了，简单明了就行"）：
# 一条说明就该扫一眼看完，超过 14 字必然折行，菜单也跟着高低不齐。
# [EN] Readability criteria for description text. **Short is a hard requirement** (user: "too long,
# [EN] simple and clear is enough"):
# [EN] one description should be finished in one glance; over 14 characters will necessarily wrap, and
# [EN] the menu will be uneven in height.
DESC_MAX = 14
# 「看不懂」的旧词：半文半白，第一次打开的人猜不出要干什么
# [EN] Old words that are "incomprehensible": half classical, half vernacular, a first-time opener
# [EN] cannot guess what to do
DESC_BANNED = ['天地之序', '一卷之规', '归去来兮', '拾起旧卷', '展开的一卷']
# 可点项的说明里至少要出现的「人话关键词」——防止文案又漂回雅而无用
# [EN] "Plain-language keywords" that must appear in descriptions of clickable entries -- to prevent
# [EN] copy from drifting back to elegant-but-useless
DESC_NEED = {'开　卷': '导入', '拾　卷': '故事', '天　机': '设置',
             '书　斋': '设置', '归　去': '退出'}
# 灰掉项的说明该说什么：**不能只写"不可用"**，要指出下一步（用户看不到按钮，
# 得从小字里知道该干什么）。所以灰掉的那几项单独要求「点出前置动作」。
# 拾卷例外：它的文案是说清「为什么没有」（还没有做过的故事），指向的是"故事"这件事。
# [EN] What the description of a grayed-out entry should say: **must not only write "unavailable"**,
# [EN] must point out the next step (users cannot see the button,
# [EN] they must know from the small text what to do). So the grayed-out entries separately require
# [EN] "point out the prerequisite action."
# [EN] 拾卷 is an exception: its copy is about explaining "why there isn't one" (no story has been made
# [EN] yet), pointing at the matter of "story."
# ★ 2026-10-28：值改成**一组可接受的措辞，任一命中即可**。
#   起因：回卷的项目名/说明并进了 `_book_desc`（跟起笔、书斋同一套三档），
#   没有书时它写的是「先开卷导入小说」——**它直接指出了下一步**，比原来的
#   「没有在推演的故事」更该被夸。旧规则写死"没有"两个字，把更好的文案判成红的。
#   ⚠ 这条规则要防的东西没变（"灰可以，但不能哑"），所以改的是**怎么判**，
#     不是把这条判据删掉。
# [EN] ★ 2026-10-28: values are now **a set of acceptable phrasings, any one of them passes**.
# [EN] Reason: 回卷's description went through `_book_desc` (the same three-state copy as 起笔 and
# [EN] 书斋); with no book at all it says "open a volume first" -- **it literally points at the next
# [EN] step**, which is better than the old "nothing is running". The old rule hard-coded "没有"
# [EN] and flagged the better copy as a failure.
# [EN] ⚠ What this rule guards has not changed ("greyed out is fine, silent is not"), so we changed
# [EN] **how it judges**, not the rule itself.
DISABLED_NEED = {'起　笔': ('开卷',), '拾　卷': ('故事',), '书　斋': ('开卷',),
                 '回　卷': ('没有', '开卷', '选')}


def walk(ctrl, out: list):
    """深度遍历控件树，收集所有控件。
        English:
    Depth-first traversal of the control tree, collecting all controls.
    """
    if ctrl is None:
        return
    out.append(ctrl)
    for attr in ('controls', 'content', 'actions', 'title'):
        v = getattr(ctrl, attr, None)
        if isinstance(v, list):
            for c in v:
                walk(c, out)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out)


def collect_texts(page) -> list[str]:
    out: list = []
    for c in page.controls:
        walk(c, out)
    texts = []
    for c in out:
        if isinstance(c, ft.Text) and c.value:
            texts.append(c.value)
    return texts


def find_menu_items(page) -> list[tuple[str, str, bool]]:
    """按 `ORDER` 的顺序返回 `[(标题, 说明, 是否可点)]`。

    标题与说明是同一个 `Column` 里紧挨着的两个 `Text`（标题/说明），
    所以摊平后「标题后面第一个不是菜单标题的 Text」就是它的说明。
    「是否可点」看同层那个带 `on_click` 的 `Container` 里有没有这个标题。
    
        English:
    Return `[(title, description, clickable)]` in the order of `ORDER`.
        The title and description are two adjacent `Text` widgets in the same `Column` (title/description),
        so after flattening, "the first Text after the title that is not a menu title" is its description.
        "Clickable" is determined by whether this title exists in the same-level `Container` that has `on_click`.
    """
    out: list = []
    for c in page.controls:
        walk(c, out)

    clickable_titles: set[str] = set()
    for c in out:
        if isinstance(c, ft.Container) and c.on_click is not None:
            inner = getattr(c, 'content', None)
            if inner is None:
                continue
            tmp: list = []
            walk(inner, tmp)
            clickable_titles.update(x.value for x in tmp
                                    if isinstance(x, ft.Text) and x.value in ORDER)

    items = []
    for i, c in enumerate(out):
        if isinstance(c, ft.Text) and c.value in ORDER:
            desc = ''
            for nxt in out[i + 1: i + 4]:
                if isinstance(nxt, ft.Text) and nxt.value and nxt.value not in ORDER:
                    desc = nxt.value
                    break
            items.append((c.value, desc, c.value in clickable_titles))
    # 按菜单实际顺序排（DFS 顺序一般就是，但显式排一下更稳）
    # [EN] Arrange by the menu's actual order (DFS order is usually it, but explicitly arranging is more
    # [EN] stable)
    items.sort(key=lambda it: ORDER.index(it[0]))
    return items


def find_menu_icons(page) -> dict[str, str]:
    """`{菜单标题: 图标文件名}` —— 从**渲染出来的控件树**里取，不看源码。

    ★ 为什么要真机取而不是 grep 源码：源码里写对槽位、运行时却挂不上
      （文件不在时 `mk_menu_icon` 会降级成"破图"矢量图标）—— 那种情况
      源码级判据是绿的。这里取的是 `ft.Image.src` 的**文件名**
      （`open_book.png` / `puzzle_dim.png` 这样），降级成矢量图标的项
      根本不会出现在结果里，于是"八项都必须有图"这条会当场红。

    控件树里那一行的形状是
    `Container[Row[Container[Image], Column[Text(标题), Text(说明)]]]`，
    摊平之后每个 `Image` 后面紧跟的几个控件里，第一个"值在 `ORDER` 里的 Text"
    就是它那一项 —— 与 `find_menu_items` 找说明用的是同一个办法。

    ⚠ 上一版收的是 `ft.Icon.icon.name`（单色矢量图标那一轮）。**换成位图之后
      这条判据必须一起改**：不改的话它收不到任何东西，"八项都有图标"会红，
      而人容易误判成"界面坏了"。
    
        English:
    `{menu title: icon filename}` -- taken from the **rendered control tree**, not from source code.
        ★ Why take it from the real runtime instead of grepping source: source may write the correct slot but fail to mount at runtime
          (when the file is missing, `mk_menu_icon` degrades to a "broken image" vector icon) -- in that case
          the source-level criterion is green. What is taken here is the **filename** of `ft.Image.src`
          (like `open_book.png` / `puzzle_dim.png`); items degraded to vector icons
          simply won't appear in the result, so "all eight items must have icons" will turn red on the spot.
        The shape of that row in the control tree is
        `Container[Row[Container[Image], Column[Text(title), Text(description)]]]`,
        after flattening, among the few controls immediately following each `Image`, the first "Text whose value is in `ORDER`"
        is its item -- the same method used by `find_menu_items` to find descriptions.
        ⚠ The previous version collected `ft.Icon.icon.name` (the monochrome vector icon round). **After switching to bitmaps,
          this criterion must be changed along with it**: if not changed, it collects nothing, "all eight items have icons" turns red,
          and people easily misjudge it as "the UI is broken".
    """
    out: list = []
    for c in page.controls:
        walk(c, out)
    got: dict[str, str] = {}
    for i, c in enumerate(out):
        if not isinstance(c, ft.Image):
            continue
        nm = Path(str(getattr(c, 'src', '') or '')).name
        if not nm:
            continue
        for nxt in out[i + 1: i + 6]:
            if isinstance(nxt, ft.Text) and nxt.value in ORDER:
                got[nxt.value] = nm
                break
    return got


def count_colored(path: Path, thr: int = 60) -> int:
    """一张截图里**明显有色**的像素数（`max-min >= thr`）。

    ★★ 为什么要量这个：控件属性对 ≠ **屏幕上画出来了**。`ft.Image` 完全可以
      "src 挂着对的路径、实际渲染成一个破图占位"（路径写错、assets 目录挪了、
      相对/绝对路径搞混）—— 那种情况上面那些读属性的断言**全绿**。
      所以再加一道**像素级**的：同一次运行里拍两张（无项目 = 四项灰 / 有项目 =
      八项全彩），背景与文字几乎一样，**差出来的那些彩色像素只可能来自图标**。
      实测基线（2026-10-10，1920×1129）：灰那态 3305、全彩那态 7302，差 **3997**
      ≈ 4 个图标的量（38×38 的框，去掉透明边约 1000/个）⇒ 阈值取 2000，留一倍余量。
    ⚠ 只用**差值**、不用绝对值：背景是水墨画，本身就有彩色像素，绝对值不稳。
    ⚠ 用 `ImageChops` 走 C 实现，别在 Python 里逐像素循环（1920×1129 两张要好几秒）。
    
        English:
    The number of **clearly colored** pixels in a screenshot (`max-min >= thr`).
        ★★ Why measure this: control properties being correct ≠ **it is drawn on screen**. `ft.Image` can perfectly well
          "have the correct path on src, but actually render as a broken-image placeholder" (wrong path, assets dir moved,
          relative/absolute path confusion) -- in that case all the above property-reading assertions are **all green**.
          So add one more **pixel-level** check: take two shots in the same run (no project = four gray / with project =
          all eight full color), the background and text are nearly identical, **the colored pixels that differ can only come from icons**.
          Measured baseline (2026-10-10, 1920×1129): gray state 3305, full-color state 7302, difference **3997**
          ≈ the amount of 4 icons (38×38 box, minus transparent edges about 1000 each) ⇒ threshold set to 2000, leaving double the margin.
        ⚠ Use only the **difference**, not absolute values: the background is an ink painting, which itself has colored pixels, so absolute values are unstable.
        ⚠ Use `ImageChops` to go through the C implementation, don't loop pixel-by-pixel in Python (1920×1129 two images takes several seconds).
    """
    im = Image.open(path).convert('RGB')
    r, g, b = im.split()
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    hist = ImageChops.subtract(mx, mn).histogram()
    return sum(hist[thr:])


def slot_of(fname: str) -> str:
    """`puzzle_dim.png` / `puzzle.png` → `puzzle`（去掉后缀，认出同一个槽位）。

    ⚠ 第一版忘了这一步：直接拿"期望的槽位 + `.png`"去比，于是
      **四个不可点的项**（挂的是 `_dim`）全被报成"图不对"—— 判据自己错了，
      而它报出来的现象（"八项的图标与约定一一对应"红）看着像界面的错。
      **"失效状态"是这张表的一部分，比对时必须把褪色后缀算作同一个槽位。**
    
        English:
    `puzzle_dim.png` / `puzzle.png` → `puzzle` (strip the suffix, recognize the same slot).
        ⚠ The first version forgot this step: it directly compared "expected slot + `.png`", so
          **the four non-clickable items** (which mount `_dim`) were all reported as "wrong image" -- the criterion itself was wrong,
          yet the phenomenon it reported ("the eight items' icons correspond one-to-one with the convention" red) looked like a UI error.
          **"Disabled state" is part of this table; when comparing, the faded suffix must be counted as the same slot.**
    """
    nm = str(fname or '')
    return nm[:-4].removesuffix('_dim') if nm.endswith('.png') else nm


def resume_item_state(page) -> dict:
    """找到「回　卷」那一项的标题/说明 Text 控件，回报颜色与可点状态。
        English:
    Find the title/description Text controls of the "回 卷" item, and report the color and clickable
    state.
    """
    out: list = []
    for c in page.controls:
        walk(c, out)
    res = {'title_color': None, 'desc_color': None, 'clickable': None, 'desc': ''}
    for i, c in enumerate(out):
        if isinstance(c, ft.Text) and c.value == '回　卷':
            res['title_color'] = getattr(c, 'color', None)
            desc = next((t for t in out[i:i + 4]
                         if isinstance(t, ft.Text) and t.value and t.value != '回　卷'), None)
            if desc:
                res['desc'] = desc.value
                res['desc_color'] = getattr(desc, 'color', None)
            break
    # 同层的 Container（带 on_click）→ 是否可点
    # [EN] Container at the same level (with on_click) → whether clickable
    for c in out:
        if isinstance(c, ft.Container) and c.on_click is not None:
            inner = getattr(c, 'content', None)
            vals = []
            if inner is not None:
                tmp: list = []
                walk(inner, tmp)
                vals = [t.value for t in tmp if isinstance(t, ft.Text)]
            if '回　卷' in vals:
                res['clickable'] = True
                break
    if res['clickable'] is None:
        res['clickable'] = False
    return res


async def main(page: ft.Page):
    # ★ **先隔离项目根，再开界面** —— 必须赶在「场景 1：没有项目」之前。
    #   `scan_projects()` 读的就是 `CFG.projects_dir()`；不隔离的话，
    #   用户自己建过项目（或上次夹具没清干净）时，菜单里「拾卷」不会是灰的，
    #   于是「没项目时该灰掉」这条断言**假失败** —— 本机就是这么挂过一次。
    #   隔离目录还要**先清一次**：上次跑剩的夹具就落在这里面（踩过：
    #   残留的 `回卷测试项目/回卷测试项目` 让这一条又挂了一次）。
    # ★★★ 用**自己的**临时目录（2026-10-08 改，断根而不再"清场地"）。
    #   原来借用 `assets/screenshots/_proj` —— 那是**几个脚本共用**的一层
    #   （`verify_opacity` / `verify_run_modes` 的夹具也在它下面）。
    #   两个后果都实测到了：
    #     · 本脚本一上来要**清整层** `_proj` → 与并行跑的那些天生冲突
    #       （清的时候别人正在用），所以它被挪进了 `ALONE`；
    #     · 即便独占，**清也清不掉**：并行阶段那些脚本的进程还可能占着文件，
    #       `safe_rmtree` 的"删不掉就算了"把失败吞了 → 残留 → `scan_projects`
    #       扫到 → 「没项目时拾卷该灰掉」假红（2026-10-08 回归里连红两次，
    #       是**这次新加的环境自检**把残留名字报出来的：
    #       `['回卷测试项目', '模式标签验证', '透明度验证']`）。
    #   改成私有目录之后：**场地是自己的、全新的**，不受别人影响，
    #   也不需要再清任何共享的东西。
    # [EN] ★ **Isolate the project root first, then open the UI** -- must happen before "Scenario 1: no
    # [EN] project."
    # [EN] `scan_projects()` reads exactly `CFG.projects_dir()`; without isolation,
    # [EN] when the user has created a project themselves (or last time's fixture wasn't cleaned up), "拾卷"
    # [EN] in the menu will not be gray,
    # [EN] so the assertion "should be gray when there is no project" **falsely fails** -- this machine has
    # [EN] hung exactly this way once.
    # [EN] The isolated directory must also be **cleaned once first**: last run's leftover fixtures land in
    # [EN] it (hit before:
    # [EN] ★★★ Use **your own** temp directory (changed 2026-10-08, cutting the root instead of "clearing
    # [EN] the field").
    # [EN] Originally it borrowed `assets/screenshots/_proj` -- that is a layer **shared by several
    # [EN] scripts**
    # [EN] (`verify_opacity` / `verify_run_modes` fixtures are also under it).
    # [EN] Both consequences were actually observed:
    # [EN] · This script, on startup, must **clear the whole layer** `_proj` → inherently conflicts with
    # [EN] those running in parallel
    # [EN] (while clearing, others are using it), so it was moved into `ALONE`;
    # [EN] · Even if exclusive, **clearing may not succeed**: during the parallel phase, those scripts'
    # [EN] processes may still hold the files,
    # [EN] `safe_rmtree`'s "if it can't be deleted, forget it" swallowed the failure → residue →
    # [EN] `scan_projects`
    # [EN] scans it → "拾卷 should be gray when there is no project" falsely red (2026-10-08 regression went
    # [EN] red twice in a row,
    # [EN] it was **this newly added environment self-check** that reported the residual names:
    # [EN] After switching to a private directory: **the field is your own, brand new**, unaffected by
    # [EN] others,
    # [EN] and there is no need to clear anything shared.
    _iso = Path(tempfile.mkdtemp(prefix='nws_resumemenu_'))
    VU.isolate_projects_dir(_iso)
    # ★★ **隔离后自检**（2026-10-08 加）：`_proj` 是**几个脚本共用**的一层
    #   （`verify_opacity` / `verify_run_modes` 的夹具也在这下面），
    #   所以"清干净了吗"不能想当然。之前踩过两次：清理留下空壳目录 →
    #   `scan_projects` 扫到它 → 「没项目时拾卷该灰掉」假红，
    #   **而报告里只写"拾卷该灰掉"这一条**，看不出是环境脏 ——
    #   查了半天（那一趟它已经在 ALONE 组里、单跑还连过五次）。
    #   现在把"环境到底干不干净"单独报出来：脏就明说是脏，
    #   别让后面的断言替它背锅。
    #   ⚠ 这里只**算**，不写 `report` —— `report` 要到下面才定义
    #     （第一版直接写进去 → `UnboundLocalError`，`main()` 当场抛，
    #      窗口不关、脚本挂到超时；报错信息在 stdout，很容易漏看）。
    # [EN] ★★ **Self-check after isolation** (added 2026-10-08): `_proj` is a layer **shared by several
    # [EN] scripts**
    # [EN] (`verify_opacity` / `verify_run_modes` fixtures are also under it),
    # [EN] so "is it cleaned" cannot be taken for granted. Two hits before: cleanup left an empty shell
    # [EN] directory →
    # [EN] `scan_projects` scans it → "拾卷 should be gray when there is no project" falsely red,
    # [EN] **and the report only wrote the "拾卷 should be gray" item**, you couldn't tell the environment
    # [EN] was dirty --
    # [EN] spent a long time investigating (that round it was already in the ALONE group, and a solo run
    # [EN] still passed five times in a row).
    # [EN] Now "is the environment actually clean" is reported separately: if dirty, say plainly it is
    # [EN] dirty,
    # [EN] don't let later assertions take the blame for it.
    # [EN] ⚠ Here only **compute**, do not write to `report` -- `report` is not defined until below
    # [EN] (the first version wrote directly into it → `UnboundLocalError`, `main()` threw on the spot,
    # [EN] the window did not close, the script hung until timeout; the error message was in stdout, very
    # [EN] easy to miss).
    _left = [x.name for x in _iso.iterdir()] if _iso.exists() else []

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    report: dict = {}
    report['iso_clean'] = {'ok': not _left, 'left': _left}

    async def shot(name: str):
        page.update()
        await asyncio.sleep(0.4)
        page_shot = OUT / name
        page_shot.write_bytes(await page.take_screenshot())

    # ── 场景 1：没有项目 ──
    # [EN] ── Scenario 1: no project ──
    app.current_project = None
    app.show_start_screen()
    page.update()
    await asyncio.sleep(0.8)
    st1 = resume_item_state(page)
    texts1 = collect_texts(page)
    report['no_project'] = {
        'has_resume_item': '回　卷' in texts1,
        'hint': st1['desc'],
        'title_color': st1['title_color'],
        'clickable': st1['clickable'],
        'greyed_out': st1['title_color'] not in (None, '#26292d') and not st1['clickable'],
        # 没有项目时，项目名条位置要给出「尚未开卷」的提示，而不是留一片空
        # [EN] When there is no project, the project name bar position should show the "not yet opened" hint,
        # [EN] rather than leaving a blank
        'has_empty_hint': any('尚未开卷' in t for t in texts1),
        'no_chip': not any(t.startswith('【') and t.endswith('】') for t in texts1),
    }
    await shot('menu_resume_1_disabled.png')

    # ── 说明文字：能看懂，而且要短（用户："直白一些…太长了，简单明了就行"）──
    # 口径写死在这儿，防止文案又漂回「调天地之序」那种半文半白、或者写成长句：
    #   ① 七项一项不少，且**每项都有说明**（不能只有个雅致的标题）
    #   ② **说明要短**：≤ DESC_MAX 字（超了会折行，菜单高低不齐）
    #   ③ 不出现已知看不懂的旧词
    #   ④ **可点的项**要出现"人话关键词"（开卷→导入、天机/书斋→设置、归去→退出）；
    #      **灰掉的项**要指出前置动作（见 DISABLED_NEED）—— 灰可以，但不能哑
    # [EN] ── Description text: understandable, and short (user: "more straightforward... too long, simple
    # [EN] and clear is enough") ──
    # [EN] The criteria are hard-coded here, to prevent copy from drifting back to half classical half
    # [EN] vernacular like "tune the order of heaven and earth," or into long sentences:
    # [EN] ① All seven entries, not one missing, and **each has a description** (cannot have only an
    # [EN] elegant title)
    # [EN] ② **Descriptions must be short**: ≤ DESC_MAX characters (over will wrap, menu heights uneven)
    # [EN] ③ No known incomprehensible old words appear
    # [EN] **grayed-out entries** must point out the prerequisite action (see DISABLED_NEED) -- gray is
    # [EN] fine, but not mute
    items1 = find_menu_items(page)
    icons1 = find_menu_icons(page)
    report['menu_items'] = [{'title': a, 'desc': b, 'clickable': c}
                            for a, b, c in items1]
    report['menu_icons'] = icons1
    report['icon_check'] = {
        'icons': icons1,
        # 八项**每一项**都要挂上彩色位图（挂不上、降级成破图图标的项
        # 根本不会出现在 icons1 里）
        # [EN] All **eight entries** must have a colored bitmap attached (entries that fail to attach, degrade
        # [EN] to broken image icon,
        # [EN] will not appear in icons1 at all)
        'missing': [k for k in ORDER if k not in icons1],
        # 每一项的图必须**正是**约定的那一张（比的是**槽位**，不含 `_dim` 后缀 ——
        # 不可点的项本来就该挂褪色版，那是下面那条单独管的）
        # [EN] Each entry's image must be **exactly** the agreed one (what is compared is the **slot**,
        # [EN] excluding the `_dim` suffix --
        # [EN] non-clickable entries should inherently have the faded version, and that is handled separately
        # [EN] by the item below)
        'wrong': {k: icons1.get(k) for k, want in EXPECT_ICON.items()
                  if slot_of(icons1.get(k, '')) != want},
        # 图上标的文件必须真的在磁盘上（槽位名写错时指向不存在的文件）
        # [EN] The file indicated on the image must actually be on disk (when the slot name is misspelled, it
        # [EN] points to a nonexistent file)
        'absent': sorted({f for f in icons1.values() if not (ICON_DIR / f).exists()}),
        # ★ 图标跟标题一起灰：**不可点**的项挂 `<槽位>_dim.png`，
        #   **可点**的项挂彩色版。两边都查 —— 只查"灰的有没有灰"会漏掉
        #   "能点的项被灰了"（那是反向错，一眼看不出来）。
        #   判据直接拿 `clickable` 与"是不是 _dim"对表，省得各写一遍。
        # [EN] ★ Icon is dimmed together with the title: **non-clickable** items get `<slot>_dim.png`,
        # [EN] **clickable** items get the colored version. Check both sides -- only checking "does the dim one
        # [EN] have a dim version" will miss
        # [EN] "a clickable item got dimmed" (that's a reverse error, not visible at a glance).
        # [EN] The criterion directly compares `clickable` against "is it _dim", so we don't have to write it
        # [EN] out twice.
        'dim_mismatch': [(a, icons1.get(a, '（没有图）')) for a, _b, c in items1
                         if icons1.get(a, '').endswith(DIM_SUFFIX) == c],
    }
    titles1 = [a for a, _b, _c in items1]
    ok_items = titles1 == ORDER
    ok_hasdesc = all(b.strip() for _a, b, _c in items1)
    long_ones = [(a, b) for a, b, _c in items1 if len(b) > DESC_MAX]
    banned_hit = [(a, b) for a, b, _c in items1
                  if any(w in b for w in DESC_BANNED)]
    # 可点项查关键词；灰的项不查（它换的是"为什么点不了"那套文案）
    # [EN] Clickable items check keywords; dim ones don't (they swap in the "why can't I click this" copy).
    need_miss = [(a, w) for a, b, c in items1 if c
                 for t, w in DESC_NEED.items() if t == a and w not in b]
    # 灰掉项查"有没有指出下一步"（措辞是一组，任一命中即可 —— 见 `DISABLED_NEED`）
    # [EN] Dimmed items check "does it point out the next step" (a set of phrasings, any one passes).
    disabled_miss = [(a, '|'.join(ws)) for a, b, c in items1 if not c
                     for t, ws in DISABLED_NEED.items()
                     if t == a and not any(w in b for w in ws)]
    disabled_with_desc = [(a, b) for a, b, c in items1 if not c and not b.strip()]
    report['desc_check'] = {
        'items_match': ok_items, 'titles': titles1,
        'all_have_desc': ok_hasdesc,
        'too_long': long_ones, 'banned': banned_hit, 'need_missing': need_miss,
        'disabled_need_missing': disabled_miss,
        'disabled_without_desc': disabled_with_desc,
    }
    # 无项目时：两项不可点的，必须**解释为什么点不了**，而不是留空或只写"不可用"
    # [EN] When there are no projects: the two non-clickable items must **explain why they can't be
    # [EN] clicked**, not be left empty or just say "unavailable".
    d1 = {a: b for a, b, _c in items1}
    c1 = {a: c for a, _b, c in items1}
    report['disabled_hint'] = {
        'new_round_desc': d1.get('起　笔', ''),
        'resume_desc': d1.get('回　卷', ''),
        'project_settings_desc': d1.get('书　斋', ''),
        'new_round_points_to_import': '开卷' in d1.get('起　笔', ''),
        'resume_says_none_running': bool(d1.get('回　卷', '').strip()),
        # 灰化规则要一致：同样"没东西"，不能一个灰一个能点。
        # 无项目时「起　笔」「拾　卷」「书　斋」「回　卷」都该灰
        # （书斋是**本书**设置，没有书就没有可设的；拾卷点开是空列表）
        # [EN] Dimming rules must be consistent: for the same "nothing there", you can't have one dim and one
        # [EN] clickable.
        # [EN] (书斋 is the **this book** setting; with no book there's nothing to set; 拾卷 opens to an empty
        # [EN] list)
        'new_round_disabled': not c1.get('起　笔', True),
        'open_story_disabled': not c1.get('拾　卷', True),
        'project_settings_disabled': not c1.get('书　斋', True),
        'resume_disabled': not c1.get('回　卷', True),
        # 但「开卷」「天机」「归去」任何时候都能点 —— **天机是程序设置，
        # 与有没有项目无关**，不能跟着书斋一起灰（这两个最容易混淆）
        # [EN] unrelated to whether projects exist**, and must not be dimmed along with 书斋 (these two are the
        # [EN] easiest to confuse)
        'import_always_clickable': bool(c1.get('开　卷', False)),
        'global_settings_always_clickable': bool(c1.get('天　机', False)),
    }

    # ── 场景 2：有项目（拾卷打开后回到菜单，应显示可用）──
    # 项目根已在 `main()` 开头隔离到临时目录（见那里的注释）
    # [EN] ── Scenario 2: has projects (after opening 拾卷 and returning to the menu, should show as
    # [EN] available) ──
    # [EN] The project root is already isolated to a temp directory at the start of `main()` (see the
    # [EN] comment there)
    proj_root = Path(CFG.projects_dir()) / '回卷测试项目'
    proj_root.mkdir(parents=True, exist_ok=True)
    (proj_root / '设定集').mkdir(exist_ok=True)
    # ★ 必须写 `.nwsproj`：菜单里的项目数是 `scan_projects()` 扫出来的，
    #   光建目录不写身份证文件，扫描找不到 → 计数为 0 → 拾卷仍是灰的
    #   （踩过：这条断言一开始"失败"，其实是夹具没建全，不是代码问题）。
    # [EN] ★ Must write `.nwsproj`: the project count in the menu comes from what `scan_projects()` scans
    # [EN] out,
    # [EN] just creating the directory without writing the ID file means the scan can't find it -> count is
    # [EN] 0 -> 拾卷 is still dim
    # [EN] (Been burned: this assertion "failed" at first; it was actually the fixture that wasn't fully
    # [EN] built, not a code problem).
    proj = Project(proj_root, '回卷测试项目')
    proj.write_nwsproj()
    app.current_project = proj
    app.show_start_screen()
    page.update()
    await asyncio.sleep(0.8)
    texts = collect_texts(page)
    st2 = resume_item_state(page)
    chip = next((t for t in texts if t.startswith('【') and t.endswith('】')), '')
    report['with_project'] = {
        'has_resume_item': '回　卷' in texts,
        'desc': st2['desc'],
        'title_color': st2['title_color'],
        'clickable': st2['clickable'],
        # 回到开始界面第一眼要能确认自己在哪个项目里（用户明确提过）
        # [EN] On returning to the start screen, the first glance must confirm which project you're in (the
        # [EN] user explicitly mentioned this)
        'project_chip': chip,
        'has_project_chip': chip == '【回卷测试项目】',
        # 窗口标题也带项目名（多开时任务栏可辨，设计稿 §11.1）
        # [EN] The window title also carries the project name (distinguishable in the taskbar when multiple are
        # [EN] open, design doc §11.1)
        'window_title': getattr(page, 'title', ''),
        'title_has_name': '回卷测试项目' in (getattr(page, 'title', '') or ''),
    }
    await shot('menu_resume_2_enabled.png')

    # ── 像素级：图标**真的画出来了**吗（不只是控件属性对）──
    #   两张截图的背景/版式几乎一样，差别只有"四项灰 ↔ 八项全彩"，
    #   所以**多出来的彩色像素只可能来自图标**。见 `count_colored` 的注释。
    # [EN] ── Pixel-level: are the icons **actually drawn** (not just the widget properties being right) ──
    # [EN] The two screenshots have almost identical background/layout; the only difference is "four items
    # [EN] dim <-> eight items full color",
    # [EN] so the **extra colored pixels can only come from the icons**. See the comment in
    # [EN] `count_colored`.
    try:
        c1 = count_colored(OUT / 'menu_resume_1_disabled.png')
        c2 = count_colored(OUT / 'menu_resume_2_enabled.png')
        report['pixels'] = {'colored_disabled': c1, 'colored_enabled': c2,
                            'delta': c2 - c1}
    except Exception as e:                                      # noqa: BLE001
        report['pixels'] = {'error': repr(e)}

    # 有项目时的文案也要短（起　笔/拾卷在这一态换的是另一套文案，
    # 只检查无项目那一态会漏掉它们）
    # [EN] The copy when projects exist must also be short (起 笔/拾卷 swap in a different set of copy in this
    # [EN] state,
    # [EN] checking only the no-project state will miss them)
    items2 = find_menu_items(page)
    d2 = {a: b for a, b, _c in items2}
    c2 = {a: c for a, _b, c in items2}
    report['desc_check2'] = {
        'descs': d2,
        'too_long': [(a, b) for a, b, _c in items2 if len(b) > DESC_MAX],
        'banned': [(a, b) for a, b, _c in items2
                   if any(w in b for w in DESC_BANNED)],
        # 有项目时这两项要恢复可点（无项目时是灰的）
        # [EN] When projects exist these two items must become clickable again (they're dim when there are no
        # [EN] projects)
        'new_round_clickable': bool(c2.get('起　笔', False)),
        'open_story_clickable': bool(c2.get('拾　卷', False)),
        # 书斋同理：有书了才可点，且说明要回到「本书设置」
        # [EN] Same for 书斋: only clickable once there's a book, and the description must go back to 「本书设置」
        'project_settings_clickable': bool(c2.get('书　斋', False)),
        'project_settings_desc': d2.get('书　斋', ''),
        'project_settings_desc_has_setting': '设置' in d2.get('书　斋', ''),
        # ★ 2026-10-07 翻面：小字里**不再有**「（N 个）」那种计数。
        #   用户：「2个小说 我删除一个之后 初始界面的拾卷下面的小字部分的数字
        #   不变（你把这个数字去掉算了，没有用处）」—— 那是**构建时**算好的，
        #   删掉一本之后不重画就还是旧的；计数本身也没人用。
        # [EN] ★ 2026-10-07 flip: the small text **no longer has** the 「(N 个)」 style count.
        # [EN] User: "2 novels, after I delete one, the number in the small text under 拾卷 on the initial screen
        # [EN] doesn't change (just remove this number, it's useless)" -- that was computed at **build time**,
        # [EN] after deleting a book it stays stale unless redrawn; and nobody uses the count anyway.
        'open_story_desc_no_count': not any(
            x in d2.get('拾　卷', '') for x in ('个', '（', '(')),
        'open_story_desc_text': d2.get('拾　卷', ''),
    }

    # ── 菜单顺序核对（遍历时按出现顺序）──
    # [EN] ── Menu order check (in order of appearance during traversal) ──
    seq = [t for t in texts if t in ORDER]
    report['menu_order'] = seq
    report['order_ok'] = seq == ORDER
    report['resume_before_quit'] = (seq.index('回　卷') < seq.index('归　去')) if (
        '回　卷' in seq and '归　去' in seq) else False

    # ── 点击 → 进入运行界面 ──
    # [EN] ── Click -> enter the run view ──
    app._on_resume_story(None)
    await asyncio.sleep(0.8)
    report['view_after_click'] = app._view

    # 清理
    # [EN] Cleanup
    try:
        import shutil
        VU.safe_rmtree(proj_root, ignore_errors=True)
        report['cleaned'] = str(proj_root)
    except Exception as e:
        report['cleanup_error'] = str(e)

    # ── 汇总：把原来那一大串 `and` 拆成**带名字**的清单 ──
    # ⚠ 2026-10-08 改这一段的理由（吃过一次亏）：
    #   以前是 `report['ok'] = bool(A and B and C …)`，**失败时只知道 exit=2**，
    #   不知道是哪一条不成立。而回归器每个脚本只留一行结论，
    #   这里又只 `print` 一坨 JSON（JSON 里没有"结论行"）——
    #   于是那一趟"独占组也红、单跑连过五次"只能靠猜。
    #   现在逐条留名：谁不成立就写谁，回归器那一行直接看得到。
    # [EN] ── Summary: split that big old `and` chain into a **named** list ──
    # [EN] ⚠ 2026-10-08 reason for changing this section (got burned once):
    # [EN] It used to be `report['ok'] = bool(A and B and C …)`, **on failure you only knew exit=2**,
    # [EN] you didn't know which condition failed. And the regression harness keeps only one summary line
    # [EN] per script,
    # [EN] and here we just `print` a blob of JSON (there's no "summary line" in the JSON) --
    # [EN] so that run of "the exclusive group also red, standalone passes five times in a row" could only
    # [EN] be guessed at.
    # [EN] Now each condition is named: whichever fails gets written, and the harness line can see it
    # [EN] directly.
    _np = report['no_project']
    _wp = report['with_project']
    _d1 = report['desc_check']
    _d2 = report['desc_check2']
    _dh = report['disabled_hint']
    checks: list[tuple[str, object]] = [
        # ★ 环境自检放第一条：它不成立时，下面关于"没项目时该灰掉"的判断
        #   全都不可信（而且那条最容易替它背锅）。
        # [EN] ★ Environment self-check goes first: when it fails, the judgements below about "should be dim
        # [EN] when there's no project"
        # [EN] are all untrustworthy (and that one is the easiest to scapegoat for it).
        (f'前置环境干净（隔离目录 `_proj` 清空后不留残留；'
         f'残留={report["iso_clean"]["left"]}）', report['iso_clean']['ok']),
        ('菜单顺序对', report.get('order_ok')),
        ('「回卷」排在「归去」前面', report.get('resume_before_quit')),
        ('点「回卷」进的是运行界面', report.get('view_after_click') == 'main'),
        ('没项目时有「回　卷」这一项', _np['has_resume_item']),
        ('没项目时它是灰的', _np['greyed_out']),
        ('没项目时给出「尚未开卷」提示', _np['has_empty_hint']),
        ('没项目时不显示项目名条', _np['no_chip']),
        ('有项目时有「回　卷」这一项', _wp['has_resume_item']),
        ('有项目时它是可点的', _wp['clickable']),
        ('有项目时小字有说明', _wp['desc']),
        ('有项目时显示项目名条', _wp['has_project_chip']),
        ('窗口标题带项目名', _wp['title_has_name']),
        (f'{N_ITEMS} 项一项不少，且顺序一致', _d1['items_match']),
        # ★ 图标（2026-10-10）：八项都得挂上**彩色位图**，而且每一项的图
        #   正是约定的那一张（素材本身对不对由 verify_menu_icons.py 管）
        # [EN] ★ Icons (2026-10-10): all eight items must have a **colored bitmap** attached, and each item's
        # [EN] image
        # [EN] must be exactly the agreed one (whether the asset itself is right is handled by
        # [EN] verify_menu_icons.py)
        ('八个菜单项都挂上了彩色图标', not report['icon_check']['missing']),
        ('八项的图标与约定一一对应', not report['icon_check']['wrong']),
        ('图标文件都真的在（槽位名没写错）', not report['icon_check']['absent']),
        ('不可点的项挂褪色版、可点的挂彩色版', not report['icon_check']['dim_mismatch']),
        # ★★ 像素级（最后一关）：上面那些读的都是**控件属性**，
        #    "src 对、画出来是个破图"它们一个都看不见。这条直接数屏幕上的彩色像素。
        # [EN] ★★ Pixel-level (final gate): everything above reads **widget properties**,
        # [EN] "src is right but it renders as a broken image" -- none of them can see that. This one directly
        # [EN] counts colored pixels on the screen.
        ('彩色图标真的画到了屏幕上（四灰→八彩，彩色像素至少多 2000）',
         (report.get('pixels', {}).get('delta') or 0) >= 2000),
        ('每项都有说明', _d1['all_have_desc']),
        ('说明都不超长', not _d1['too_long']),
        ('说明里没有看不懂的旧词', not _d1['banned']),
        ('可点的项都出现了人话关键词', not _d1['need_missing']),
        ('灰掉的项都指出了下一步', not _d1['disabled_need_missing']),
        ('灰掉的项不能空着不解释', not _d1['disabled_without_desc']),
        ('无项目时「开卷」的说明指向导入', _dh['new_round_points_to_import']),
        ('无项目时「回卷」说明"没在跑"', _dh['resume_says_none_running']),
        ('无项目时「开卷」灰掉', _dh['new_round_disabled']),
        ('无项目时「拾卷」灰掉', _dh['open_story_disabled']),
        ('无项目时「书斋」灰掉', _dh['project_settings_disabled']),
        ('无项目时「回卷」灰掉', _dh['resume_disabled']),
        ('「开卷」任何时候都可点', _dh['import_always_clickable']),
        ('「天机」任何时候都可点', _dh['global_settings_always_clickable']),
        ('有项目时说明也不超长', not _d2['too_long']),
        ('有项目时说明里也没有旧词', not _d2['banned']),
        ('有项目时「开卷」可点', _d2['new_round_clickable']),
        ('有项目时「拾卷」可点', _d2['open_story_clickable']),
        ('有项目时「书斋」可点', _d2['project_settings_clickable']),
        ('书斋说明回到「本书设置」', _d2['project_settings_desc_has_setting']),
        ('拾卷说明里不再有计数', _d2['open_story_desc_no_count']),
    ]
    report['failed'] = [n for n, c in checks if not c]
    report['ok'] = bool(not report['failed'])

    (OUT / 'menu_resume_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # ★ 结论行 + **逐条失败名**：回归器只留一行结论，所以失败原因必须打在
    #   stdout 上（只 dump JSON 的话，JSON 里没有"结论行"，
    #   回归报告里就只剩一行任务栏图标日志 —— 那一趟就是这么瞎的）。
    # [EN] ★ Summary line + **per-condition failure names**: the harness keeps only one summary line, so
    # [EN] the failure cause must be printed
    # [EN] to stdout (if you only dump JSON, there's no "summary line" in the JSON,
    # [EN] and the regression report is left with just one line of taskbar icon log -- that run was exactly
    # [EN] that blind).
    print(f"\n拾卷菜单验证：{len(checks) - len(report['failed'])}/{len(checks)}")
    for n, c in checks:
        if not c:
            print('  ✗', n)
    if report.get('failed'):
        print('  （完整报告见 assets/screenshots/menu_resume_report.json）')
    # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
    #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
    #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
    # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will raise
    # [EN] CancelledError
    # [EN] and cancel this coroutine; the `exit_now(...)` on the line after `await shutdown(page)`
    # [EN] has **never actually executed** (exit code always 0 = false green). See
    # [EN] `util/flet_shutdown.shutdown()`.
    await shutdown(page, code=0 if report['ok'] else 2)


ft.run(main)
