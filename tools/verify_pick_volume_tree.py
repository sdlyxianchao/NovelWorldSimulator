# -*- coding: utf-8 -*-
"""拾卷中间那一列：**树状图**是不是真的建起来了（2026-10-21 用户点名）。

用户原话：「节点设计从现在的卡片改成可以展开和缩起来的卡片，默认缩起来，只有一行，
从左到右分别是 标题 生成时间 删除按钮 展开和缩起来按钮（三角号的那种）；展开之后是
现在显示的内容。整体是树状图，跟 Windows 资源管理器左侧树状图的那样。默认节点是
根节点，所有从某个节点开始的推演都是这个节点的子节点，这些节点之间是兄弟节点。
这个节允许有左右滚动条。」另有：「整个拾卷对话框扩大百分之 30，放大的宽度都加到
中间这一列」与「把中间那一列的按时间排序 4 个先隐藏掉，代码先不要删除」。

★ 为什么必须**真机**、不能只测数据层
  数据层（`store/lineage`）全绿也不代表用户能看见树 —— 断在界面那一段的可能性
  这个项目已经踩过好几次（"配置写了没生效""yaml 搬字段漏了两个"）。
  所以这里真起 flet、真开拾卷、真数控件，并且**两个层都报**：
  数据层证明"树建对了"，界面层证明"树画出来了"。

★ 为什么用**复杂树**（14 轮 / 5 层 / 分叉 / 孤儿 / 环 / 自父 / 旧存档）
  用户报过一次「看不到树，条目数量少了些」—— 而当时的数据是"每条都是根"
  （旧存档没有 `来源.json`）。只测一条直线的树，永远发现不了"条目变少"
  （那是 `build_tree` 丢条目的典型症状）。所以夹具里**故意**放了这几种坏数据：
  父被删、互相指认成环、自己当自己的父、以及没有记录的旧存档。

产出：assets/screenshots/pick_volume_tree_report.json
用法：.venv/Scripts/python.exe tools/verify_pick_volume_tree.py

English:
The middle column of Pick-a-Volume: does the **tree** really get built (named by the user 2026-10-21)?
User's words: "change the nodes from cards to expandable/collapsible cards, collapsed by default, one
row, left to right: title, generation time, delete button, expand/collapse button (the triangle kind);
expanding shows what is currently displayed. The whole thing is a tree, like the tree on the left of
Windows File Explorer. The default node is a root; every derivation starting from a node is its child;
those nodes are siblings. This section allows left/right scrollbars." Plus: "enlarge the whole dialog by
30%, put all the added width into the middle column" and "hide the four time-sort options in the middle
column for now, don't delete the code".
★ Why it must be a **real device** test and not just the data layer: a green data layer does not mean
  the user can see the tree -- "breaks between data and UI" has happened repeatedly in this project.
  So this really starts flet, really opens Pick-a-Volume, really counts controls, and reports **both**
  layers: data proves "the tree is right", UI proves "the tree is drawn".
★ Why a **complex tree** (14 rounds / 5 levels / fork / orphan / cycle / self-parent / legacy saves):
  the user once reported "I can't see the tree, and some entries are missing", when every item was a
  root (legacy saves had no `来源.json`). A single straight line can never reveal "entries went
  missing" (the classic symptom of `build_tree` dropping items), so the fixture **deliberately**
  contains those bad cases: deleted parent, mutual cycle, self-parent, and unrecorded legacy saves.
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '.')
sys.path.insert(0, 'tools')

import flet as ft
import verify_ui_common as VU
from store import lineage as LG
from store.project import Project, scan_projects

OUT = Path('assets/screenshots')
OUT.mkdir(parents=True, exist_ok=True)
results: list[dict] = []


def rec(name, ok_, detail=''):
    results.append({'name': name, 'ok': bool(ok_), 'detail': str(detail)})
    print(('  ✓ ' if ok_ else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)


# (key, 父key, 有没有来源记录)
TREE = [
    ('R1', None, True),
    ('R2', 'R1', True), ('R3', 'R1', True), ('R6', 'R1', True),
    ('R4', 'R2', True), ('R5', 'R2', True),
    ('R9', 'R4', True),
    ('R10', 'R9', True),
    ('O1', '不存在的父', True),
    ('C1', 'C2', True), ('C2', 'C1', True),
    ('S1', 'S1', True),
    ('OLD1', None, False), ('OLD2', None, False),
]
NAMES = {k: f'第{i}次模拟2026-10-{i:02d}-10-00'
         for i, (k, _, _) in enumerate(TREE, start=1)}


def _make_book(root: Path):
    proj = Project.create_new(root, '复杂树验证书')
    for key, par, recorded in TREE:
        r = proj.root / NAMES[key]
        (r / '每天的生活').mkdir(parents=True, exist_ok=True)
        (r / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n这是 {key} 的正文。院外土路车轱辘声一阵一阵。\n', encoding='utf-8')
        (r / 'state.db').write_text('', encoding='utf-8')
        if recorded:
            real_par = None if par in (None, '不存在的父') else NAMES.get(par)
            LG.write_lineage(r, parent=real_par, kind='resume' if real_par else 'fresh')
    return proj.root


async def main(page: ft.Page) -> None:
    import gui.app_flet as G

    tmp = Path(tempfile.mkdtemp())
    VU.isolate_projects_dir(tmp / 'Projects')
    _make_book(Path(G.CFG.projects_dir()))
    print(f'造了 {len(TREE)} 轮（其中 2 轮是没有来源记录的旧存档）', flush=True)

    proj = next(p for p in scan_projects(Path(G.CFG.projects_dir()))
                if p.name == '复杂树验证书')
    runs = proj.list_runs()
    parents = LG.parents_of(runs, infer_missing=True)
    tree = LG.build_tree(runs, parents)
    print('  推断后的树：', flush=True)
    for p, dep, has in tree:
        print('    ' + '  ' * dep + ('├ ' if has else '· ') + p.name, flush=True)
    rec(f'一条不丢：{len(tree)} == {len(runs)}', len(tree) == len(runs),
        f'{len(tree)}/{len(runs)}')
    maxd = max(d for _, d, _ in tree)
    rec('层数够深（≥4 层）', maxd >= 4, f'最大深度 {maxd}')
    # ⚠ 这条**必须钉具体的两条**，不能只看"根节点变少" ——
    #   第一版就是那么写的，而反例法把它戳穿了：把 `parents_of` 的推断整个关掉，
    #   根节点数也才 4 个（本来就有孤儿/环/明确 fresh 的根）⇒ 判据照样绿。
    #   "根变少了" ≠ "旧存档被接上了"。现在直接查那两条的父是谁。
    # [EN] ⚠ This must pin **the two specific entries**, not just "fewer roots" -- the first version
    # [EN] did the latter and the counterexample method exposed it: turning inference off entirely
    # [EN] still left only 4 roots (orphans/cycles/explicit-fresh are roots anyway) => green as usual.
    # [EN] "fewer roots" is not "legacy saves got attached". Now it checks who those two parents are.
    rec('旧存档（无记录）**被推断出父节点**（不是根）',
        parents.get(NAMES['OLD1']) is not None
        and parents.get(NAMES['OLD2']) == NAMES['OLD1'],
        f"OLD1→{parents.get(NAMES['OLD1'])} / OLD2→{parents.get(NAMES['OLD2'])}")
    rec('孤儿当根', any(p.name == NAMES['O1'] and d == 0 for p, d, _ in tree), '')
    rec('环里两条都在', {p.name for p, _, _ in tree} >= {NAMES['C1'], NAMES['C2']}, '')
    rec('自父只出现一次', sum(1 for p, _, _ in tree if p.name == NAMES['S1']) == 1, '')

    # ── 树线（`│ ├ └`）的形状 ──
    # [EN] -- The shape of the rails (`│ ├ └`) --
    # ★★★ 用户第二批要求：「有办法在不同条目之间拉上线来明确的表现树的形状吗」。
    #   这里钉**三个具体位置**，不是"根数变少"那类软判据：
    #     ① 每行的格子数 == 它的层数（线跟缩进一一对应，多一格/少一格都错位）；
    #     ② `第2次`（下面挂着 5/6/7/8，后面还有兄弟 3/4）必须是 `├` 不能是 `└` ——
    #        这条专抓"拿下一行判断还有没有兄弟"那个典型写法（下一行是它自己的孩子，
    #        于是所有当爹的都被画成"最后一个"，它的孩子那一列就断在半空）；
    #     ③ `第8次`（最深那条，五层）必须是 `││ └` —— 祖先那两格要**接着往下**（`│`），
    #        而"唯一的爹没有兄弟"那一格必须是空格。这一条同时验证"连续"和"断口"两件事。
    # [EN] ★★★ Second-round request: "can we draw lines between entries to make the tree shape
    # [EN] explicit?" Three **concrete positions** are pinned here, not soft "fewer roots"-style checks:
    # [EN] ① cells per row == its depth (the rail must line up with the indent); ② `第2次` (which has
    # [EN] 5/6/7/8 under it and siblings 3/4 after it) must be `├`, never `└` -- this catches the
    # [EN] classic "look at the next row to decide siblings" bug (the next row is its own child, so
    # [EN] every parent becomes "last" and its children's column snaps in mid-air); ③ `第8次` (the
    # [EN] deepest, five levels) must be `││ └`.
    guides = LG.tree_guides(tree)
    by_name = {p.name: (d, g) for (p, d, _), g in zip(tree, guides)}
    rec('树线与 `tree` **逐行对齐**（条数一致）', len(guides) == len(tree),
        f'{len(guides)}/{len(tree)}')
    rec('每行格子数 == 层数', all(len(g) == d for (_p, d, _h), g in zip(tree, guides)),
        str(sorted({len(g) for g in guides})))
    rec('根节点不画线（空串）',
        all(g == '' for (p, d, _), g in zip(tree, guides) if d == 0), '')
    _g2 = by_name[NAMES['R2']][1] if 'R2' in NAMES else ''
    rec('有后续兄弟的父节点画 `├` 而不是 `└`（抓"看下一行"的错法）',
        _g2 == '├', f'第2次 = {_g2!r}')
    rec('第五层那条 = `││ └`（祖先线连续 + 断口正确）',
        by_name[NAMES['R10']][1] == '││ └',
        f'第8次 = {by_name[NAMES["R10"]][1]!r}')

    app = G.NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(0.5)
    app.show_projects_dialog()
    await asyncio.sleep(0.8)
    page.update()

    dialogs = VU.open_dialogs(page)
    rec('拾卷打开了', bool(dialogs), f'{len(dialogs)} 层')
    if not dialogs:
        _finish()
        return
    content = dialogs[-1].content
    content = getattr(content, 'content', content) or content

    lvs, cards = [], []
    rows = []                                  # 存档列表里的"一整行"（Stack，装着树线）

    def _walk(c, depth=0):
        if depth > 18 or c is None:
            return
        if isinstance(c, ft.ListView):
            lvs.append(c)
        if getattr(c, '_depth', None) is not None:
            cards.append(c)
        if getattr(c, '_card', None) is not None:
            rows.append(c)
        for attr in ('controls', 'content'):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    _walk(x, depth + 1)
            elif v is not None and not isinstance(v, (str, int, float)):
                _walk(v, depth + 1)

    _walk(content)
    counts = [len(getattr(lv, 'controls', []) or []) for lv in lvs]
    print('  三栏 ListView 条数：', counts, '| 节点数：', len(cards), flush=True)
    rec('中间列**每一轮一个节点**', len(cards) == len(runs), f'{len(cards)}/{len(runs)}')
    depths = [c._depth for c in cards]
    rec('节点带层级（0..N）', bool(depths) and max(depths) >= 4, f'{sorted(set(depths))}')
    rec('默认收起', _all_collapsed(content), '')
    # ★ 数据对了 ≠ 界面画了。这个项目"配置写了没生效""字段搬漏一个"踩过太多次，
    #   树线尤其危险：`tree_guides` 全绿而界面一个格子都没画，是完全可能的
    #   （定位层写错、颜色透明、格子被裁掉 —— 三种都见过）。
    # [EN] ★ Correct data does not mean the UI drew it. This project has been bitten repeatedly by
    # [EN] "configured but not in effect"; rails are especially risky: `tree_guides` can be all green
    # [EN] while the UI draws zero cells (wrong positioned layer, transparent colour, clipped cell).
    _railed = [r for r in rows if getattr(getattr(r, '_card', None), '_depth', 0) > 0]
    _bad = []
    for _r in _railed:
        _d = getattr(_r._card, '_depth', 0)
        _cells = [c for c in (getattr(_r, 'controls', None) or [])
                  if getattr(c, 'left', None) is not None]
        if len(_cells) != _d:
            _bad.append(f'depth{_d} 定位格{len(_cells)}')
    rec('界面真画了树线：**每深一层一个定位格**',
        bool(_railed) and not _bad,
        f'{len(_railed)} 个非根节点，异常 {_bad[:3] if _bad else "无"}')
    rec('树线是**实心的**（不是透明/空的格子）',
        bool(_railed) and all(_has_ink(r) for r in _railed),
        f'{sum(1 for r in _railed if _has_ink(r))}/{len(_railed)} 有实心线段')
    # ══════════════════════════════════════════════════════════
    #  ★★★ 同一层（根之间 / 同一父的子节点之间）按**生成时间正序**
    #  （2026-10-22 用户：「拾卷页面的存档同一级别（即所有根节点以及所有从某个节点
    #   推演出来的子节点）默认按照从时间顺序排列 回收站也是这样」）
    #
    #  ★ 为什么在**界面**这一层再判一次：数据层（`verify_recycle_bin` 的排序组）证明
    #    `forest()` 的 `rows` 是正序；但那不等于**屏幕上**的顺序是正序 —— 这一段
    #    完全可能在遍历时又按别的顺序摆（比如按 `save_cards` 的某个索引重排）。
    #    这里判的是**控件在列表里的先后**，即用户眼睛看到的那个顺序。
    #  ⚠ 判**兄弟组**，不判"整行是不是字典序"：树是前序，父亲后面紧跟孩子，
    #    整行本来就不是单调的 —— 那样判必然假红。
    # [EN] ★★★ Per-level order (roots / siblings) must be **generation time ascending**.
    # [EN] ★ Why judge it again on the **UI** layer: the data layer proves `forest().rows` is in order,
    # [EN] which is not the same as **what is on screen** -- the loop could reorder while building.
    # [EN] This judges the order of the controls in the list, i.e. what the user's eye sees.
    # [EN] ⚠ Judge **sibling groups**, not "the whole column is lexicographic": it is a pre-order, a
    # [EN] parent is immediately followed by its children, so a monotone check would be a false red.
    _order_err = _sibling_order_check(cards)
    rec('同一层**按生成时间正序**（根之间 / 同一父的子节点之间）—— 判的是屏幕上'
        '控件的先后，不是数据层的 `rows`', _order_err == '', _order_err)
    # ★★★ 2026-10-21（用户：「为何卡片无法展开」）—— **原来这里只有"默认收起"**，
    #   也就是只证明了"开不出来"是对的，没证明"点得开"。于是三角点了没反应
    #   （父级抢点击 / `ink` 需要 Material 祖先 / 刷新异常被 `except: pass` 吃掉）
    #   一路绿灯放了出去。现在真去点那一下，并检查三件事：
    #     ① 展开区真的可见了；② 箭头真的翻过来了；③ **选中没被抢走**
    #     （点三角只该开合，不该让右栏跳走 —— 那是用户点标题才该发生的事）。
    # [EN] ★★★ 2026-10-21 (user: "why won't the card expand?"): **this used to check only "collapsed
    # [EN] by default"**, i.e. it proved that *not* opening was right but never that clicking opens.
    # [EN] So a caret that did nothing (parent stealing the tap / `ink` needing a Material ancestor /
    # [EN] a refresh exception swallowed by `except: pass`) shipped all-green. Now it actually taps and
    # [EN] checks three things: ① the panel really became visible; ② the caret really flipped;
    # [EN] ③ **the selection was not stolen** (toggling must not move the detail panel).
    _expand_check = _tap_caret_and_check(content, cards)
    rec('点三角**真能展开**（面板可见 + 箭头翻转 + 不抢选中）', _expand_check['ok'],
        _expand_check['detail'])
    rec('再点一下**能收起**', _expand_check['ok'] and _expand_check['reclosed'],
        _expand_check['detail']) 
    # ★ 截图给用户看实际效果（本机模型读不了图，所以图是**给人**看的）
    try:
        # ⚠ 截图前要多等一会儿并 `page.update()`：直接抓会拿到 `None`
        #   （`take_screenshot` 返回 None ⇒ `write_bytes` 报 memoryview 错）。
        page.update()
        await asyncio.sleep(1.2)
        png = await page.take_screenshot()
        shot = OUT / 'pick_volume_tree.png'
        if png:
            shot.write_bytes(png)
            print(f'  截图：{shot}', flush=True)
        else:
            print('  截图返回 None（跳过）', flush=True)
    except Exception as _e:                                      # noqa: BLE001
        print(f'  截图失败：{_e!r}', flush=True)

    rec('排序框已隐藏，但单选框还在控件树里',
        _n(content, ft.Radio) >= 4 and _visible_radiogroup(content) is None,
        f'Radio {_n(content, ft.Radio)} 个 / 可见 RadioGroup '
        f'{"有" if _visible_radiogroup(content) else "无"}')
    _finish()


def _n(c, cls, depth=0):
    if depth > 18 or c is None:
        return 0
    n = 1 if isinstance(c, cls) else 0
    for attr in ('controls', 'content'):
        v = getattr(c, attr, None)
        if isinstance(v, list):
            for x in v:
                n += _n(x, cls, depth + 1)
        elif v is not None and not isinstance(v, (str, int, float)):
            n += _n(v, cls, depth + 1)
    return n


def _visible_radiogroup(c, vis=True, depth=0):
    if depth > 18 or c is None:
        return None
    v = vis and bool(getattr(c, 'visible', True))
    if isinstance(c, ft.RadioGroup) and v:
        return c
    for attr in ('controls', 'content'):
        x = getattr(c, attr, None)
        if isinstance(x, list):
            for y in x:
                got = _visible_radiogroup(y, v, depth + 1)
                if got is not None:
                    return got
        elif x is not None and not isinstance(x, (str, int, float)):
            got = _visible_radiogroup(x, v, depth + 1)
            if got is not None:
                return got
    return None


def _sibling_order_check(cards) -> str:
    """同一层（根之间 / 同一父的子节点之间）是不是**按生成时间正序**。返回 `''` = 对。

    ★ 用**屏幕上卡片的先后 + `_depth`** 还原兄弟组：层数 d 的那张卡，它的父就是
      前面最近一张层数更小的卡。这样判的是"用户眼睛看到的顺序"，
      而不是回头去读 `forest().rows`（那是数据层的事，另一条判据在管）。
    ★ 时间由**判据自己**从名字里解析（名字里最后一个 `年-月-日-时-分`），
      不调 `store.lineage.run_time` —— 否则被测函数算错了，两边一起错，判据照样绿。
    """
    import re as _re

    def _name_of(card) -> str:
        for s in VU.all_texts(card):
            if s.startswith('第') and '次模拟' in s:
                return s
        return ''

    def _t(nm: str):
        found = _re.findall(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', nm or '')
        return tuple(int(x) for x in found[-1]) if found else None

    groups: dict = {}
    stack: list = []
    for c in cards:
        d = int(getattr(c, '_depth', 0) or 0)
        while len(stack) > d:
            stack.pop()
        parent = stack[d - 1] if (d > 0 and len(stack) >= d) else None
        groups.setdefault(parent, []).append(_name_of(c))
        stack.append(_name_of(c))
    bad = []
    for parent, kids in groups.items():
        times = [_t(k) for k in kids]
        if any(t is None for t in times):
            bad.append(f'{parent or "根"}：有认不出时间的条目 {[k[:6] for k in kids]}')
        elif times != sorted(times):
            bad.append(f'{parent or "根"}：{[k[:6] for k in kids]}')
    return '；'.join(bad[:3]) if bad else ''


def _has_ink(row) -> bool:
    """这一行的树线里**至少有一段是实心的**（`bgcolor` 不是 None / 不是全透明）。

    为什么单独一条：定位格的数量对，不代表里面有东西 —— 颜色写成透明、
    `bgcolor` 忘了给、或者高度算成 0，都会是"格子在那儿、线看不见"。
    面板可见 ≠ 内容可见，这个项目栽过。

        English:
    At least one segment of this row's rail is **solid** (`bgcolor` is neither None nor fully
    transparent). Separate check because the right number of cells does not mean there is anything in
    them: a transparent colour, a missing `bgcolor`, or a zero height all give "cells are there, line
    is invisible". "Panel visible" is not "content visible" -- this project has been bitten.
    ⚠ **只查定位格，不查整行**：整行里还有卡片，卡片自己就有 `bgcolor`
      （`C['panel']`）—— 从整行往下找"有没有带颜色的控件"永远为真，那是假判据。
      树线是定位层里那几个格子，必须只在那里面找。

        English:
    ⚠ **Only the positioned cells, never the whole row**: the row also contains the card, which has
      its own `bgcolor` (`C['panel']`) -- searching the whole row for "any coloured control" is always
      true, i.e. a fake criterion. The rails are the cells in the positioned layer; look only there.
    """
    cells = [c for c in (getattr(row, 'controls', None) or [])
             if getattr(c, 'left', None) is not None]
    hit = [False]

    def _walk(c, depth=0):
        if depth > 14 or c is None or hit[0]:
            return
        bg = getattr(c, 'bgcolor', None)
        if isinstance(bg, str) and bg.strip():
            # `#00RRGGBB`（alpha=0）等于没有
            # [EN] `#00RRGGBB` (alpha=0) counts as nothing
            if not (len(bg) == 9 and bg[1:3].upper() == '00'):
                hit[0] = True
                return
        kids = getattr(c, 'controls', None)
        if isinstance(kids, list):
            for x in kids:
                _walk(x, depth + 1)
        v = getattr(c, 'content', None)
        if v is not None and not isinstance(v, (str, int, float)):
            _walk(v, depth + 1)

    for _cell in cells:
        _walk(_cell)
        if hit[0]:
            return True
    return False


def _all_collapsed(content) -> bool:
    """每一张节点卡的展开区都是收起的（`visible is False`）。

    ⚠ 判据要**按卡片算**、不能只看"找到了至少一个收起区"：只有一张卡收起、
    其余九张全展开，也会返回 True。所以这里数"卡片数"和"收起区数"是否相等。

        English:
    Every node card's detail area is collapsed (`visible is False`).
    ⚠ This must be **per card**, not "at least one collapsed area exists": one collapsed card with
    nine expanded ones would still return True. So it compares the card count with the collapsed count.
    """
    cards, collapsed = [0], [0]

    def _walk(c, depth=0):
        if depth > 18 or c is None:
            return
        if getattr(c, '_depth', None) is not None:
            cards[0] += 1
            box = _detail_box_of(c)
            if box is not None and getattr(box, 'visible', True) is False:
                collapsed[0] += 1
        kids = getattr(c, 'controls', None)
        if isinstance(kids, list):
            for x in kids:
                _walk(x, depth + 1)
        v = getattr(c, 'content', None)
        if v is not None and not isinstance(v, (str, int, float)):
            _walk(v, depth + 1)

    _walk(content)
    return cards[0] > 0 and collapsed[0] == cards[0]


def _detail_box_of(card):
    """卡片里那个"展开区"容器（`visible` 会被翻转的那只）。

    认定方式：卡片第一层子 Column 的**第二个**孩子（第一个是标题行）。
    刻意按**结构**取，而不是"找第一个 visible=False 的容器" —— 后者会在
    别处出现一个隐藏容器时抓错人，而判据要钉的是**产品的那一个**。

        English:
    The "detail area" container inside the card (the one whose `visible` gets flipped).
    Identified **structurally** as the second child of the card's first-level Column. Deliberately not
    "the first container with visible=False" -- that would grab the wrong one as soon as some other
    hidden container appears, while the criterion must pin **the product's own** box.
    """
    col = getattr(card, 'content', None)
    kids = getattr(col, 'controls', None) if col is not None else None
    if not isinstance(kids, list) or len(kids) < 2:
        return None
    inner = kids[1]
    return getattr(inner, 'content', None) or inner


def _caret_of(card):
    """卡片里的**展开三角**（那个 `on_click` 只开合、不改选中的容器）。

    认定方式：`content` 是 `ft.Icon` 且图标的 `name` 是右/下箭头。
        English:
    The **expand caret** inside the card (the container whose `on_click` only toggles). Identified as:
    `content` is an `ft.Icon` whose `name` is the right/down arrow.
    """
    hit = [None]

    def _walk(c, depth=0):
        if depth > 20 or c is None or hit[0] is not None:
            return
        inner = getattr(c, 'content', None)
        # ⚠ `ft.Icon` 的字段是 **`icon`**，不是 `name`（Flet 1.0 改名，产品代码
        #   正是因为写了 `.name` 才"点了打不开"）。判据这里也必须读 `icon`，
        #   否则判据自己先崩 —— 那就成了"判据抛异常，后面几条根本没跑"。
        # [EN] ⚠ `ft.Icon`'s field is **`icon`**, not `name` (renamed in Flet 1.0 -- the product
        # [EN] code failed to expand precisely because it wrote `.name`). The criterion must read
        # [EN] `icon` too, otherwise the criterion itself crashes first.
        if isinstance(inner, ft.Icon) and getattr(inner, 'icon', None) in (
                ft.Icons.KEYBOARD_ARROW_RIGHT, ft.Icons.KEYBOARD_ARROW_DOWN):
            if getattr(c, 'on_click', None) is not None:
                hit[0] = c
                return
        kids = getattr(c, 'controls', None)
        if isinstance(kids, list):
            for x in kids:
                _walk(x, depth + 1)
        if inner is not None and not isinstance(inner, (str, int, float)):
            _walk(inner, depth + 1)

    _walk(card)
    return hit[0]


def _tap_caret_and_check(content, cards) -> dict:
    """**真去点一下三角**，看面板是否真的展开、箭头是否真的翻转、选中是否没被抢走。

    ★ 为什么必须点（用户「为何卡片无法展开」）：这一整条路径以前没有任何判据 ——
      `rec('默认收起')` 只能证明"开不出来"，证明不了"点得开"。而失败的三种方式
      （父级抢点击 / `ink` 缺 Material 祖先 / 刷新异常被 `except: pass` 吃掉）
      **全都不改任何数据结构** —— 状态翻了、控件也翻了，只是没生效；
      所以只有"点一下再看结果"能抓到它。

    ★ 为什么还要查"选中没被抢走"：点三角只该开合。如果父级 on_click 抢到了，
      表现是"右栏跳到了另一条"—— 用户会以为自己在选存档，而不是展开。

        English:
    **Actually tap the caret** and see whether the panel opens, the caret flips, and the selection is
    not stolen.
    ★ Why a real tap (user: "why won't the card expand?"): this path previously had no criterion at
      all -- `rec('默认收起')` only proves "it does not open", never "it opens". All three failure
      modes (parent stealing the tap / `ink` without a Material ancestor / refresh exception eaten by
      `except: pass`) **change no data structure** -- state flipped, control flipped, just no effect;
      only "tap and look" catches it.
    ★ Why also check the selection: toggling must only open/close. A stolen tap shows up as "the right
      panel jumped to another round", which reads as "I selected a save" rather than "I expanded it".
    """
    out = {'ok': False, 'reclosed': False, 'detail': '没找到卡片/三角'}
    if not cards:
        return out
    card = cards[0]
    caret = _caret_of(card)
    box = _detail_box_of(card)
    if caret is None or box is None:
        out['detail'] = f'caret={"有" if caret else "无"} / box={"有" if box else "无"}'
        return out
    # 右栏（第三个 ListView）在点之前的身份，用来判"选中没被抢走"
    # [EN] The right column (third ListView) identity before the tap, to prove the selection is intact
    lvs = []

    def _walk_lv(c, depth=0):
        if depth > 18 or c is None:
            return
        if isinstance(c, ft.ListView):
            lvs.append(c)
        kids = getattr(c, 'controls', None)
        if isinstance(kids, list):
            for x in kids:
                _walk_lv(x, depth + 1)
        v = getattr(c, 'content', None)
        if v is not None and not isinstance(v, (str, int, float)):
            _walk_lv(v, depth + 1)

    _walk_lv(content)
    before = tuple(id(x) for x in lvs[2].controls) if len(lvs) >= 3 else ()

    err = ''
    try:
        caret.on_click(None)
    except Exception as _e:                                      # noqa: BLE001
        err = repr(_e)
    opened = bool(getattr(box, 'visible', False))
    flipped = (getattr(getattr(caret, 'content', None), 'icon', None)
               == ft.Icons.KEYBOARD_ARROW_DOWN)
    after = tuple(id(x) for x in lvs[2].controls) if len(lvs) >= 3 else ()
    kept = before == after
    # 再点一次：必须能收回去（否则就是"只能开不能关"）
    # [EN] Tap again: it must close (otherwise it only opens, never closes)
    try:
        caret.on_click(None)
    except Exception as _e:                                      # noqa: BLE001
        err = err or repr(_e)
    reclosed = (getattr(box, 'visible', True) is False
                and getattr(getattr(caret, 'content', None), 'icon', None)
                == ft.Icons.KEYBOARD_ARROW_RIGHT)
    out['ok'] = bool(opened and flipped and kept and not err)
    out['reclosed'] = bool(reclosed and not err)
    out['detail'] = (f'展开={opened} 箭头翻转={flipped} 选中未变={kept} '
                     f'再点收起={reclosed}' + (f' 异常={err}' if err else ''))
    return out


def _finish():
    ok_all = all(r['ok'] for r in results)
    print(f"\n=== {sum(1 for r in results if r['ok'])}/{len(results)} 通过 ===", flush=True)
    (OUT / 'pick_volume_tree_report.json').write_text(
        json.dumps({'ok': ok_all, 'checks': results}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    import os
    os._exit(0 if ok_all else 2)


ft.run(main)
