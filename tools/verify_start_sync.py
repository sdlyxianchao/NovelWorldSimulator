# -*- coding: utf-8 -*-
"""真机验证：**开始界面的菜单状态跟着盘面走** + 状态栏只留要紧的消息（v1.38）。

用户原话（2026-10-06）：
「我删除了所有小说之后 初始画面的拾卷菜单的小字部分是数字不对 它自己的状态也不对
没有小说了应该是不可用才对 我清空所有小说 初始画面的各个菜单状态要进行同步更新；
还有初始菜单的状态栏 和运行页面的状态栏 不需要所有的事情都发消息 重要的事情才发；
而且有项目的时候 初始画面的项目名字那个栏 我也不想要背景图 直接显示就行。」

三组判据：

**A 纯逻辑**（不起界面）
  · `_post_message` 的分级：info **不进**状态栏（只进日志）、ok / warn / error 进、
    `keep=True` 强行进；
  · 降噪**不能连即时反馈一起砍掉**：info + `snack=True` 仍然弹提示条。

**B 真机 · 删光小说 → 开始界面同步**（走真实链路，不是直接调内部函数）
  · 开「拾　卷」→ 点 🗑 → 手打书名 → 确认，把两本依次删掉；
  · 删掉最后一本 → 自动回到开始界面，而且**是重建过的**：
      拾卷小字 == 「还没有做过的故事」（**没有数字、没有"个"**）、
      拾卷 / 书斋 / 回卷 / 起　笔 **四项全不可点**，
      开卷 / 天机 / 归去 仍可点，项目名条消失（回到「尚未开卷」）；
  · 删的若是"当前这本"但还剩别的书 → 标题里的【书名】和书斋/回卷跟着熄火。
  · ★ 2026-10-07 加：**删掉一本不是当前的小说之后**，那块界面也必须
    跟着重画（用户报的正是"数字不变"）。现在小字里干脆没有计数了
    （「打开以前的故事」），但"有项目 ↛ 没有项目"这条边仍要当场反映出来。

**C 真机 · 项目名条没有背景**
  · 结构判据：**没有任何「带底色或边框」的 Container 包着「当前项目」那行字**。
    这是唯一能在背景图上画出一个盒子的东西 —— 树里没有，屏幕上就不会有。
  · 像素判据：换**纯色背景**（`VU.patch_flat_background()`）后全图扫一遍，
    「底色应有的那个合成色」的像素数必须**接近 0**（只有字形落下几粒抗锯齿）。
    正对照实测（2026-10-06，把旧版那个盒子加回去跑一遍）：
    **72884** 个像素命中 vs 修好之后 **4** 个（只剩字形边缘几粒抗锯齿）。
    所以阈值 60 是"真没有"和"真有"之间一道很宽的沟，不是拍脑袋定的数。
    ⚠ 别用"新旧两版截图做差"来判这条：把这行包进 Container 会让内容块整体重排
    （它垂直居中，多一层就整页位移），做差会全屏飘红，什么也说明不了
    —— 见 `probe_chip_box.py` 顶上那段踩坑记录。

跑法：
    .venv\\Scripts\\python.exe tools/verify_start_sync.py
产出：
    assets/screenshots/start_sync_*.png
    assets/screenshots/start_sync_report.json

English:
Real machine verification: **the start screen's menu state follows the disk** + the status bar
keeps only essential messages (v1.38).
User's exact words (2026-10-06):
"After I delete all novels, the number in the small text part of the Shijuan menu on the initial
screen is wrong, and its own state is also wrong
with no novels it should be unavailable. When I clear all novels, the states of the various
menus on the initial screen must be synchronized;
also the status bar of the initial menu and the status bar of the running page don't need to
send a message for everything, only important things;
and when there is a project, I don't want a background image for the project name bar on the
initial screen either, just display it directly."
Three groups of criteria:
**A Pure logic** (no UI started)
  · `_post_message` grading: info does **not** go to the status bar (log only), ok / warn / error do,
    `keep=True` forces it in;
  · noise reduction **must not cut off immediate feedback along with it**: info + `snack=True` still pops the snackbar.
**B Real machine · Delete all novels → start screen sync** (through the real path, not by
calling internal functions directly)
  · Open "Shijuan" → click 🗑 → type the book name → confirm, delete the two one after another;
  · After deleting the last one → automatically return to the start screen, and **it has been rebuilt**:
      Shijuan small text == "No story done yet" (**no number, no "count"**),
      Shijuan / Shuzhai / Huijuan / Qibi **all four not clickable**,
      Open / Tianji / Return still clickable, project name bar disappears (back to "Not yet opened");
  · If the deleted one is "the current book" but other books remain → the 【book name】 in the title and Shuzhai/Huijuan go dark accordingly.
  · ★ Added 2026-10-07: **after deleting a novel that is not the current one**, that interface must also
    be redrawn accordingly (what the user reported is exactly "the number doesn't change"). Now the small text simply has no count
    ("Open an old story"), but the edge "has project ↛ no project" must still be reflected on the spot.
**C Real machine · Project name bar has no background**
  · Structural criterion: **no Container "with a base color or border" wraps the line of text "current project"**.
    This is the only thing that can draw a box on the background image — if it's not in the tree, it won't be on screen.
  · Pixel criterion: after switching to a **solid background** (`VU.patch_flat_background()`), scan the whole image,
    the pixel count of "the composited color the base color should have" must be **close to 0** (only a few anti-aliasing specks from glyphs).
    Positive control measured (2026-10-06, running once with the old box added back):
    **72884** pixels hit vs **4** after the fix (only a few anti-aliasing specks at glyph edges).
    So the threshold 60 is a very wide gap between "really none" and "really there", not a number picked out of thin air.
    ⚠ Don't judge this by "diffing old vs new screenshots": wrapping this line in a Container will reflow the content block entirely
    (it's vertically centered, so one extra layer shifts the whole page), and the diff will light up the entire screen red, proving nothing
    -- see the pitfall notes at the top of `probe_chip_box.py`.
How to run:
    .venv\\Scripts\\python.exe tools/verify_start_sync.py
Output:
    assets/screenshots/start_sync_*.png
    assets/screenshots/start_sync_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from typing import Any
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from PIL import Image  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

from gui.app_flet import (NovelWorldApp, C, panel_alpha,  # noqa: E402
                          with_alpha)
from i18n import set_lang, t  # noqa: E402
from store.project import Project, trash_dir_for  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

ORDER = ['开　卷', '拾　卷', '起　笔', '天　机', '书　斋', '回　卷', '归　去']
# 没有项目时**必须灰掉**的四项（开卷 / 天机 / 归去 任何时候都能点）
# [EN] The four items that **must be grayed out** when there is no project (Open / Tianji / Return can
# [EN] be clicked at any time)
MUST_DISABLE = ['起　笔', '拾　卷', '书　斋', '回　卷']
MUST_ENABLE = ['开　卷', '天　机', '归　去']
# 拾卷在"什么都没做过"时那句小字（i18n key）
# [EN] The small text shown by Shijuan when "nothing has been done yet" (i18n key)
PICK_EMPTY = '还没有做过的故事'


def find_menu_items(page) -> list[tuple[str, str, bool]]:
    """按菜单顺序返回 `[(标题, 说明, 是否可点)]`。

    标题与说明是同一个 `Column` 里紧挨着的两个 `Text`，所以摊平后「标题后面第一个
    不是菜单标题的 Text」就是它的说明。「可点」看同层那个带 `on_click` 的 Container。
    （口径与 `verify_resume_menu.py` 一致，复制一份免得两个脚本互相 import 出岔子。）
    
        English:
    Return `[(title, description, clickable)]` in menu order.
        The title and description are two adjacent `Text` widgets in the same `Column`, so after flattening, "the first
        Text after the title that is not a menu title" is its description. "Clickable" is determined by the sibling Container with `on_click`.
        (Same criteria as `verify_resume_menu.py`, duplicated to avoid the two scripts importing each other and causing trouble.)
    """
    out = list(VU.walk(page))
    clickable: set[str] = set()
    for c in out:
        if isinstance(c, ft.Container) and c.on_click is not None:
            inner = getattr(c, 'content', None)
            if inner is None:
                continue
            vals = [x.value for x in VU.walk(inner) if isinstance(x, ft.Text)]
            clickable.update(v for v in vals if v in ORDER)
    items = []
    for i, c in enumerate(out):
        if isinstance(c, ft.Text) and c.value in ORDER:
            desc = ''
            for nxt in out[i + 1: i + 4]:
                if isinstance(nxt, ft.Text) and nxt.value and nxt.value not in ORDER:
                    desc = nxt.value
                    break
            items.append((c.value, desc, c.value in clickable))
    items.sort(key=lambda it: ORDER.index(it[0]))
    return items


def chip_boxed(page) -> list:
    """开始界面里**包着「当前项目」那行字**、而且**带底色或边框**的容器。

    「带底色」= `bgcolor` 不是 None / 'transparent'。用户要的正是"不要这个盒子"。
    
        English:
    On the start screen, the container that **wraps the "current project" text** and **has a
    background color or border**.
        "Has a background color" = `bgcolor` is not None / 'transparent'. What the user wants is exactly "not this box".
    """
    bad = []
    for c in VU.walk(page):
        if not isinstance(c, ft.Container):
            continue
        inner = list(VU.walk(c))[1:]          # 跳过自己
        # [EN] Skip self
        if not any(isinstance(x, ft.Text) and x.value == t('当前项目')
                   for x in inner):
            continue
        bg = getattr(c, 'bgcolor', None)
        if (bg not in (None, '', 'transparent')) or getattr(c, 'border', None):
            bad.append(c)
    return bad


def _trash_of(card):
    """卡片里那个**删除**图标按钮。

    ⚠ 2026-10-08 改：小说卡上多了「打开文件夹」按钮（用户要求，排在删除上面），
    而且**两个图标按钮都装进了"点整行切选中"的正文容器里**。
    原来这条判法是"第一个可点、且里面有 `ft.Icon` 的控件" ——
    现在它会先撞上**正文容器**（它含图标、也可点），于是判据"点删除"
    实际点到正文上（只切换选中，**永远不会弹删除确认框**），
    表现是 `open_dialogs` 为空、`cd[-1]` 越界崩掉。
    改成：**按图标名找，并取子树最小的那个**（按钮的子树很小）。
    
        English:
    The **delete** icon button inside the card.
        ⚠ Changed 2026-10-08: the novel card now has an "open folder" button (user request, placed above delete),
        and **both icon buttons are packed into the body container that handles "click anywhere on the row to toggle selection"**.
        The old criterion was "the first clickable widget that contains an `ft.Icon`" --
        now it hits the **body container** first (it contains icons and is clickable), so the "click delete" criterion
        actually clicks the body (only toggles selection, **never pops the delete confirmation dialog**),
        manifesting as `open_dialogs` being empty and `cd[-1]` crashing with index out of range.
        Changed to: **find by icon name, and take the one with the smallest subtree** (the button's subtree is very small).
    """
    cands: list[tuple[int, Any]] = []
    for c in VU.walk(card):
        if getattr(c, 'on_click', None) is None:
            continue
        sub = list(VU.walk(c))
        # ⚠ 取 `x.icon`（枚举值）：Flet 1.0 的 `ft.Icon` **没有** `.name`
        # [EN] ⚠ Take `x.icon` (enum value): Flet 1.0's `ft.Icon` does **not** have `.name`
        if any(isinstance(x, ft.Icon)
               and getattr(x, 'icon', None) == ft.Icons.DELETE_OUTLINE
               for x in sub):
            cands.append((len(sub), c))
    return min(cands, key=lambda t: t[0])[1] if cands else None


def _novel_cards(dlg):
    return [c for c in VU.walk(dlg)
            if isinstance(c, ft.Container) and hasattr(c, '_proj')]


def _dlgs(page) -> list:
    """当前开着的**对话框**（**不含 SnackBar**）。

    ⚠ `VU.open_dialogs()` 会把提示条也算进来 —— `_snack_raw` 走的就是
    `page.show_dialog(SnackBar)`，而 SnackBar 的 `open` 也是 True。
    这里要判的是"有没有多开一个真对话框"，所以把 SnackBar 滤掉。
    
        English:
    The currently open **dialogs** (**excluding SnackBar**).
        ⚠ `VU.open_dialogs()` also counts toast bars -- `_snack_raw` goes through
        `page.show_dialog(SnackBar)`, and SnackBar's `open` is also True.
        What we need to check here is "is there an extra real dialog open", so filter out SnackBar.
    """
    return [d for d in VU.open_dialogs(page) if not isinstance(d, ft.SnackBar)]


# 项目名条旧版那个盒子该有的底色（`with_alpha(C['hover'], panel_alpha())`
# 合成到纯色背景上的颜色）。像素判据就是数"屏幕上有多少个像素是它"。
# [EN] The base color the old box of the project name bar should have (`with_alpha(C['hover'],
# [EN] panel_alpha())`
# [EN] Color composited onto a solid background). The pixel criterion is simply counting "how many
# [EN] pixels on screen are it".
CHIP_FILL = VU.composite(with_alpha(C['hover'], panel_alpha()))


def count_fill(png: Path, rgb, tol: int = 6, step: int = 1) -> int:
    """全图有多少像素是 `rgb`（判"那个盒子在不在屏幕上"）。
        English:
    How many pixels in the whole image are `rgb` (to determine "is that box on screen").
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    n = 0
    for y in range(0, H, step):
        for x in range(0, W, step):
            c = px[x, y]
            if all(abs(c[i] - rgb[i]) <= tol for i in range(3)):
                n += 1
    return n


async def main(page: ft.Page):
    # 开始界面换成**纯色背景**：C 组的像素判据要按底色找"那个盒子"，
    # 淡彩水彩底做这个非常不稳（见文件头）。必须在建界面之前换。
    # [EN] Switch the start screen to a **solid background**: group C's pixel criterion must find "that
    # [EN] box" by its base color,
    # [EN] A pale watercolor background is very unstable for this (see file header). Must switch before
    # [EN] building the interface.
    VU.patch_flat_background()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_sync_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    items: list = []
    report: dict = {}

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

    try:
        # ══════════ A. 消息降噪：哪些进状态栏、哪些只进日志 ══════════
        # [EN] ══════════ A. Message noise reduction: which go to the status bar, which only go to the log
        # [EN] ══════════
        set_lang('zh')
        snacks: list = []
        real_snack = app._snack_raw
        app._snack_raw = lambda text, error=False: snacks.append((text, error))

        def fresh() -> None:
            app._messages.clear()
            snacks.clear()

        fresh()
        app._post_message('已打开帮助')                       # info（msg_level_of）
        ok('A：info 不进状态栏（过程播报只进日志）', len(app._messages) == 0,
           f'{len(app._messages)} 条')
        fresh()
        app._post_message('随便一句播报', keep=True)          # 强行留
        # [EN] Force keep
        ok('A：keep=True 的 info 能强行留在状态栏',
           len(app._messages) == 1 and app._messages[0]['level'] == 'info',
           str(app._messages[-1:]))
        fresh()
        app._post_message('✅ 配置已保存', level='ok')
        ok('A：ok 级进状态栏（动作收尾的回执）',
           len(app._messages) == 1 and app._messages[0]['level'] == 'ok', '')
        fresh()
        app._post_message('⚠ 需要重启才生效', level='warn')
        ok('A：warn 级进状态栏',
           len(app._messages) == 1 and app._messages[0]['level'] == 'warn', '')
        fresh()
        app._post_message('❌ 保存失败', snack=True)          # 前缀猜出 error
        # [EN] Infer error from the prefix
        ok('A：error 级进状态栏，且仍弹提示条',
           len(app._messages) == 1 and app._messages[0]['level'] == 'error'
           and len(snacks) == 1, f'{app._messages[-1:]} / {snacks}')
        fresh()
        app._show_snack('已开始新一轮 · 第 1 次模拟')          # info + snack
        ok('A：info 的即时反馈**没有**被一起砍掉（提示条照弹，只是不进列表）',
           len(app._messages) == 0 and len(snacks) == 1,
           f'列表 {len(app._messages)} 条 / 提示条 {len(snacks)} 次')
        fresh()
        app._show_snack('先开一卷，才能开始推演', error=True)
        ok('A：error 的即时反馈两边都有',
           len(app._messages) == 1 and len(snacks) == 1, '')
        app._snack_raw = real_snack

        # ══════════ B. 造两本书，走真实删除链路 ══════════
        # [EN] ══════════ B. Create two books, go through the real deletion path ══════════
        roots = CFG.projects_dir()
        proj_a = Project.create_new(roots, '同步验证甲')
        proj_b = Project.create_new(roots, '同步验证乙')
        report['roots'] = str(roots)

        # 先让界面处于「有项目」那一态（有项目名条、拾卷可点）
        # [EN] First put the interface in the "has project" state (project name bar present, Shijuan clickable)
        app.current_project = proj_a
        app._view = 'start'
        app.show_start_screen()
        page.update()
        await asyncio.sleep(0.8)

        items1 = find_menu_items(page)
        d1 = {a: b for a, b, _c in items1}
        c1 = {a: c for a, _b, c in items1}
        report['before'] = {'descs': d1, 'clickable': c1}
        ok('B：起点是「有项目」态：拾卷小字写成「打开以前的故事」、且可点',
           d1.get('拾　卷') == t('打开以前的故事') and c1.get('拾　卷') is True,
           repr(d1.get('拾　卷')))
        # ★ 2026-10-07 翻面：以前这里要求小字**带个数**（「（1 个）」）。
        #   用户：「2个小说 我删除一个之后 初始界面的拾卷下面的小字部分的数字
        #   不变（你把这个数字去掉算了，没有用处）」—— 那个数字是**构建时**
        #   算好的，删掉一本之后不重画就还是旧的。计数本身没人用，去掉最省事。
        # [EN] ★ 2026-10-07 flip: previously this required the small text to **carry a count** ("(1)").
        # [EN] User: "2 novels, after I delete one, the number in the small text below Shijuan on the initial
        # [EN] screen
        # [EN] doesn't change (just remove this number, it's useless)" — that number was computed at **build
        # [EN] time**
        # [EN] and after deleting a book it stays stale unless redrawn. Nobody uses the count itself, removing
        # [EN] it is simplest.
        ok('B：★ 拾卷小字里**不再有**个数（构建时算的计数留不住，会显示成旧值）',
           '个' not in d1.get('拾　卷', '') and '(' not in d1.get('拾　卷', '')
           and '（' not in d1.get('拾　卷', ''), repr(d1.get('拾　卷')))
        ok('B：有项目时项目名条在（【书名】）',
           any(x == '【同步验证甲】' for x in VU.all_texts(page)),
           str([x for x in VU.all_texts(page) if x.startswith('【')]))
        png_before = await shot('start_sync_1_before.png')

        # ══════════ C. 项目名条没有背景（结构判据 + 像素判据）══════════
        # [EN] ══════════ C. Project name bar has no background (structural criterion + pixel criterion)
        # [EN] ══════════
        boxes = chip_boxed(page)
        ok('C：项目名条**没有**带底色/边框的容器包着（用户："不想要背景图"）',
           not boxes, f'{len(boxes)} 个盒子')
        ok('C：项目名还是直接显示出来的（没顺手把字也删了）',
           any('当前项目' == x for x in VU.all_texts(page))
           and any('【同步验证甲】' == x for x in VU.all_texts(page)), '')
        n_fill = count_fill(png_before, CHIP_FILL)
        report['chip_fill_px'] = n_fill
        report['chip_fill_rgb'] = list(CHIP_FILL)
        ok('C：屏幕上真的找不到那个盒子的底色（全图扫一遍）',
           n_fill <= 60, f'{n_fill} 个像素命中 {CHIP_FILL}')

        # ── 开拾卷，删掉「同步验证乙」（不是当前这本）──
        # [EN] ── Open Shijuan, delete "Sync Verify B" (not the current one) ──
        dlg = app.show_projects_dialog()
        page.update()
        await asyncio.sleep(0.9)
        cards = _novel_cards(dlg)
        ok('B：拾卷打开，① 栏两本书', len(cards) == 2, f'{len(cards)} 张')

        async def delete_novel(name: str) -> None:
            """点 🗑 → 手打书名 → 确认（用户定的规矩：删整本要手打一次）。
                        English:
            Click 🗑 → type the book title by hand → confirm (the rule the user set: deleting an entire book
            requires typing it once by hand).
            """
            card = next(c for c in _novel_cards(dlg)
                        if getattr(c, '_proj', None) is not None
                        and c._proj.name == name)
            _trash_of(card).on_click(None)
            page.update()
            await asyncio.sleep(0.6)
            cd = [d for d in VU.open_dialogs(page)
                  if any('删掉整本小说？' in x for x in VU.all_texts(d))]
            tf = next((c for c in VU.walk(cd[-1]) if isinstance(c, ft.TextField)),
                      None)
            btn = next(c for c in VU.walk(cd[-1])
                       if type(c).__name__ == 'FilledButton'
                       and VU.text_of(c).strip() == '确认删除')
            tf.value = name
            tf.on_change(type('E', (), {'control': tf})())
            page.update()
            await asyncio.sleep(0.25)
            btn.on_click(None)
            page.update()
            await asyncio.sleep(1.1)

        # 数一数"开始界面被重画过几次"——用户报的现象就是**它没被重画**
        # （删掉一本之后，那块界面还是删之前建的）。（白盒但必要：那条小字
        # 现在没有计数了，"数值陈旧"这件事不再看得见，只能钉住"有没有重画"。）
        # [EN] Count "how many times the start screen has been redrawn" — the phenomenon the user reported is
        # [EN] exactly that **it was not redrawn**
        # [EN] (after deleting a book, that interface is still the one built before deletion). (White-box but
        # [EN] necessary: that small text
        # [EN] no longer has a count now, so "stale value" is no longer visible; we can only pin down "whether
        # [EN] it was redrawn".)
        refresh_calls = {'n': 0}
        _real_refresh = app._refresh_start_screen

        def _spy_refresh() -> bool:
            refresh_calls['n'] += 1
            return _real_refresh()

        app._refresh_start_screen = _spy_refresh

        await delete_novel('同步验证乙')
        ok('B：删掉非当前那本之后，盘面只剩一本',
           len(scan()) == 1, str([p.name for p in scan()]))
        ok('B：还剩别的书时，对话框**不关**（三栏就地刷新）',
           len(VU.open_dialogs(page)) == 1 and len(_novel_cards(dlg)) == 1,
           f'{len(VU.open_dialogs(page))} 个对话框 / '
           f'{len(_novel_cards(dlg))} 张卡')
        # ★ 2026-10-07：以前只在"删的是当前这本"或"删光了"时才重画 ——
        #   删掉一本**不是当前**的小说时那块界面就是旧的（用户报的数字不变
        #   就是这么来的）。现在**无条件问一遍**（非开始界面时它是空操作）。
        # [EN] ★ 2026-10-07: previously it only redrew when "the deleted one was the current book" or "all were
        # [EN] deleted" ——
        # [EN] when deleting a novel that is **not the current** one, that interface stays old (the user's
        # [EN] reported unchanged number
        # [EN] comes from exactly this). Now we **unconditionally ask once** (it is a no-op when not on the
        # [EN] start screen).
        ok('B：★ 删掉非当前那本之后，开始界面也**重画过一遍**'
           '（用户报的正是它没重画）',
           refresh_calls['n'] >= 1, f'_refresh_start_screen 调了 {refresh_calls["n"]} 次')

        # ── 再删掉「同步验证甲」——它是**当前这本**，删完就一本不剩 ──
        # [EN] ── Then delete "Sync Verify A" — it is **the current book**, after deletion not a single one
        # [EN] remains ──
        await delete_novel('同步验证甲')
        ok('B：两本都删掉了（磁盘上扫不到任何项目）', not scan(),
           str([p.name for p in scan()]))
        ok('B：删光之后自动回到开始界面（对话框已收）',
           app._view == 'start' and not VU.open_dialogs(page),
           f"_view={app._view} / {len(VU.open_dialogs(page))} 个对话框")
        ok('B：`current_project` 被清掉（不许指着已经不存在的目录）',
           app.current_project is None, str(app.current_project))

        items2 = find_menu_items(page)
        d2 = {a: b for a, b, _c in items2}
        c2 = {a: c for a, _b, c in items2}
        report['after'] = {'descs': d2, 'clickable': c2,
                           'texts_has_empty_hint': any('尚未开卷' in x
                                                       for x in VU.all_texts(page))}
        ok('B：★ 拾卷小字变回「还没有做过的故事」——**不再有数字**',
           d2.get('拾　卷') == t(PICK_EMPTY), repr(d2.get('拾　卷')))
        ok('B：★ 拾卷小字里没有"个"（旧界面残留的计数）',
           '个' not in d2.get('拾　卷', ''), repr(d2.get('拾　卷')))
        ok('B：★ 拾卷真的灰了（没有小说就该不可用）',
           c2.get('拾　卷') is False, repr(c2.get('拾　卷')))
        ok('B：起　笔 / 书斋 / 回卷 也一并灰掉',
           all(c2.get(k) is False for k in MUST_DISABLE),
           str({k: c2.get(k) for k in MUST_DISABLE}))
        ok('B：开卷 / 天机 / 归去 任何时候都能点（天机是程序设置，不跟着灰）',
           all(c2.get(k) is True for k in MUST_ENABLE),
           str({k: c2.get(k) for k in MUST_ENABLE}))
        ok('B：项目名条跟着消失，换成「尚未开卷」那行小字',
           not any(x == '【同步验证甲】' for x in VU.all_texts(page))
           and any('尚未开卷' in x for x in VU.all_texts(page)), '')
        # 菜单顺序不许被重排
        # [EN] The menu order must not be rearranged
        seq = [x for x in VU.all_texts(page) if x in ORDER]
        report['menu_order'] = seq
        ok('B：重建之后菜单顺序不变', seq == ORDER, str(seq))
        # 状态栏里有那条 warn 回执（说明"已随之置灰"+ 备份在哪）
        # [EN] The status bar has that warn receipt (indicating "has been grayed out accordingly" + where the
        # [EN] backup is)
        msgs = [m for m in app._messages if m['level'] == 'warn']
        report['warn_msgs'] = [m['text'] for m in msgs][-2:]
        ok('B：状态栏留了一条 warn 回执，写明备份目录',
           any('备份在' in m['text'] for m in msgs),
           str(report['warn_msgs']))
        ok('B：删掉的确实躺在「已删除备份」里（不是被抹掉）',
           len(list(trash_dir_for(roots).glob('*_小说_同步验证*'))) == 2,
           str([p.name for p in trash_dir_for(roots).glob('*')][:4]))
        await shot('start_sync_2_after_clear.png')

        # ══════════ B2. 拾卷在"菜单还亮着但盘面空了"时要能自愈 ══════════
        # 伪造一次"没重建"的旧界面：把 current_project 塞回去、菜单按有项目的版本画出来
        # [EN] ══════════ B2. Shijuan must be able to self-heal when "the menu is still lit but the disk is
        # [EN] empty" ══════════
        # [EN] Forge a stale interface that was "not rebuilt": stuff current_project back, draw the menu in the
        # [EN] has-project version
        stale = Project.create_new(roots, '旧界面留下的书')
        app.current_project = stale
        app.show_start_screen()
        page.update()
        await asyncio.sleep(0.6)
        # 磁盘上悄悄清掉（模拟"在别处被删了"），但界面还是旧的
        # [EN] Quietly clear it on disk (simulating "deleted elsewhere"), but the interface is still old
        import shutil as _sh
        _sh.rmtree(stale.root, ignore_errors=True)
        app.current_project = None
        before_click = {a: c for a, _b, c in find_menu_items(page)}
        ok('B2：旧界面这里确实是"亮着的"（前提成立，否则这条断言没意义）',
           before_click.get('拾　卷') is True, str(before_click.get('拾　卷')))
        app._on_old_story(None)                 # 点那个还亮着的「拾　卷」
        # [EN] Click the still-lit "Shijuan"
        page.update()
        await asyncio.sleep(0.7)
        after_click = {a: c for a, _b, c in find_menu_items(page)}
        report['selfheal_clickable'] = after_click
        ok('B2：点它就自愈 —— 界面重画、拾卷当场熄火（不给假入口）',
           after_click.get('拾　卷') is False
           and {a: b for a, b, _c in find_menu_items(page)}.get('拾　卷')
           == t(PICK_EMPTY), str(after_click.get('拾　卷')))
        ok('B2：自愈之后没有多开对话框（只是重画页面）',
           not _dlgs(page), f'{len(_dlgs(page))} 个')

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        # 清场：夹具与备份都不给下一轮留尾巴
        # [EN] Cleanup: leave no tail for the next round from either fixtures or backups
        try:
            import shutil as _sh2  # noqa: PLC0415
            _sh2.rmtree(tmp, ignore_errors=True)
        except Exception:                                   # noqa: BLE001
            pass
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'start_sync_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n开始界面同步验证：{report['n_ok']}/{report['n_all']}")
        for i in items:
            if not i['ok']:
                print(f"  ✗ {i['name']}  [{i['detail']}]")
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be settled **before closing the window**: `page.window.destroy()` throws
        # [EN] CancelledError
        # [EN] cancels this coroutine, and the line `exit_now(...)` after `await shutdown(page)`
        # [EN] **never executes** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report['ok'] else 2)


def scan():
    from store.project import scan_projects
    return scan_projects(CFG.projects_dir())


if __name__ == '__main__':
    ft.run(main)
