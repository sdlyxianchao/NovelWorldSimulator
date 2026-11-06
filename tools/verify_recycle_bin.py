# -*- coding: utf-8 -*-
"""**回收站**（拾卷最左边那个 Tab）：功能是不是真的能用（2026-10-21 用户点名）。

用户原话：「拾卷里加一个总体的 Tab，放到最左边。现在的所有内容改成名字叫做拾卷的 tab，
然后新加的叫做回收站，放到拾卷 tab 的下面。回收站的 tab 内容跟拾卷的内容相同。
后续修改之后，拾卷里删除小说 不需要输入名字 会被提示 是否删除 并且告知会被移动到
回收站 删除存档也会同样的提示 说会被移动到回收站 回收站里删除小说则需要输入小说名字
且提示会被彻底删除 存档也是同样的提示 但是不会要求输入存档名字 回收站里的存档树状图
也是树状，不过肯定跟拾卷的有不同的地方。为了维持树的形态，会有一些作为父节点的节点也
显示在这里，但实际上没有被删除，对于这样的节点，请用一些办法标记出来，比如用虚线框起来。
然后在中间列的上面加上注释说明，比如实体框表示确实在回收站，虚线框表示这个只是作为树
节点使用，实际上没被删除。但是后续如果删除了，则这个节点变成实体框。另外，如果某个节点
包含子节点，则删除这个节点会提示删除这个节点会删除所有从这个节点衍生的子节点，问是否
删除，如果确定则所有子节点和这个节点都移动到回收站。回收站删除节点也是一样的逻辑，区别
在于提示词变成会被永久删除此节点和所有子节点。另外，所有树节点前面加复选框，可以选中多个
一起删除。小说那一列也是卡片前面加上复选框，可以选中多个删除。这种多个删除的按钮放到列
的列头上面。」

★ 为什么**数据层与界面层都要**（这个项目的老规矩：两层都报）：
  · 数据层证明"搬对了、认得回来、删得干净"；
  · 界面层证明"用户看得见、点得动"。**断在两层之间**是本项目最常见的故障
    （"配置写了没生效""字段搬漏一个"），而且两次都表现为"界面上什么都没有"。

★ 为什么必须**真机**（起 flet、真开拾卷、真点数）：
  上一次「卡片无法展开」就是数据层全对、界面点是死的（`ft.Icon` 写 `.name` 抛异常）。
  只查数据结构的判据对那类 bug 完全无感。

产出：assets/screenshots/recycle_bin_report.json
用法：.venv/Scripts/python.exe tools/verify_recycle_bin.py

English:
**Recycle bin** (the leftmost tab of Pick-a-Volume): does it actually work (named by the user
2026-10-21)? The user's words are quoted above.
★ Why **both layers**: the data layer proves "moved correctly / recognised back / purged clean"; the
  UI layer proves "the user can see it and click it". A break **between** the two is this project's
  most common failure mode.
★ Why a **real device** run: the previous "the card won't expand" bug had a perfectly correct data
  layer while the UI was dead. Criteria that only inspect state cannot see that class of bug.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '.')
sys.path.insert(0, 'tools')

import flet as ft
import verify_ui_common as VU
from store import lineage as LG
from store import trash as TR
from store.project import Project, scan_projects, trash_dir_for

OUT = Path('assets/screenshots')
OUT.mkdir(parents=True, exist_ok=True)
results: list[dict] = []
#: 界面层当前那本夹具书（`_restore_click_check` 要去磁盘上核对"恢复回去了没有"）。
# [EN] The fixture book of the UI layer (the restore check verifies it on disk).
_PROJECT_FOR_CHECK: list = [None]


def rec(name, ok_, detail=''):
    results.append({'name': name, 'ok': bool(ok_), 'detail': str(detail)})
    print(('  ✓ ' if ok_ else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)


# ══════════════════════════════════════════════════════════════════
#  一、数据层（临时目录，绝不碰用户的书）
# ══════════════════════════════════════════════════════════════════
def data_layer(root: Path) -> None:
    proj = Project.create_new(root, '回收站验证书')
    names = [f'第{i}次模拟2026-10-{i:02d}-10-00' for i in range(1, 6)]
    for i, nm in enumerate(names, start=1):
        d = proj.root / nm
        (d / '每天的生活').mkdir(parents=True, exist_ok=True)
        (d / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n这是第 {i} 轮的正文。\n', encoding='utf-8')
        (d / 'state.db').write_text('', encoding='utf-8')
        # 一条直线链：1 ← 2 ← 3 ← 4 ← 5
        LG.write_lineage(d, parent=(names[i - 2] if i > 1 else None),
                         kind='resume' if i > 1 else 'fresh')
        (d / '任务介绍.md').write_text(
            f'# 任务介绍\n\n- **项目**：{proj.name}\n- **这一轮从**：测试\n',
            encoding='utf-8')

    # ★ 先算一份**动任何东西之前**的父子关系（子树判据要用）：
    #   `parents_of` 只认识"当前还在盘上的"存档，后面几步会把第 3 次搬进搬出，
    #   那时再算就只剩 1、2 两轮，后代必然是空的。
    # [EN] ★ Take the parent map **before touching anything** (the subtree criterion needs it):
    # [EN] `parents_of` only knows saves currently on disk, and the steps below shuttle round 3 into
    # [EN] and out of the bin -- computing later would leave only rounds 1 and 2, i.e. no descendants.
    parents0 = LG.parents_of(proj.list_runs(), infer_missing=True)

    # ① 删中间一轮 → 旁注写明"属于哪本书"和"父是谁"
    d3 = proj.root / names[2]
    ok, msg = TR.move_run_to_trash(d3, proj.root, root)
    rec('把一轮搬进回收站', ok, str(msg)[-60:])
    side = TR.sidecar_path(Path(msg))
    meta = json.loads(side.read_text(encoding='utf-8')) if side.is_file() else {}
    rec('旁注记下了**原书**（否则永远恢复不回去）',
        meta.get('project') == proj.name, f"project={meta.get('project')!r}")
    rec('旁注记下了**父存档**（回收站靠它撑树）',
        meta.get('parent') == names[1], f"parent={meta.get('parent')!r}")

    # ② 扫描：认得出来、分得清两类
    entries = TR.scan_trash(root)
    rec('扫得到这一条', len(entries) == 1, f'{len(entries)} 条')
    e3 = entries[0]
    rec('解析出原名（去掉时间戳与"存档"前缀）',
        e3.name == names[2] and e3.kind == TR.KIND_RUN, f'{e3.kind}/{e3.name}')

    # ③ 旧备份（没有旁注）也要认得出原书 —— 靠 `任务介绍.md`
    trash = trash_dir_for(root)
    legacy = trash / '20260101-000000_存档_第9次模拟2025-01-01-00-00'
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / '任务介绍.md').write_text(
        f'- **项目**：{proj.name}\n', encoding='utf-8')
    lg = [x for x in TR.scan_trash(root) if x.name.startswith('第9次')]
    rec('旧备份（无旁注）**从《任务介绍》认出原书**',
        bool(lg) and lg[0].project == proj.name
        and lg[0].project_from == '任务介绍',
        f'{lg[0].project_from if lg else "没扫到"}')

    # ④ 恢复：放回原书里，旁注消失
    ok, msg = TR.restore(e3, root)
    rec('恢复回原来的书里', ok and (proj.root / names[2]).is_dir(), str(msg)[-50:])
    rec('恢复之后旁注也清掉了（不然会留一条"名字有、目录没有"的鬼条目）',
        not side.exists(), '')

    # ⑤ 目标已存在 ⇒ 拒绝（绝不覆盖）
    # ⚠ 必须先**造出**那个同名目标再试：第一版是"搬进回收站 → 立刻恢复"，
    #   那时原位置本来就是空的，恢复当然成功 —— 判据测的是"冲突处理"，
    #   却压根没造出冲突（假判据，靠反例法之外的"读一遍自己写的测试"才发现）。
    # [EN] ⚠ The conflicting target must be **created first**: the first version did
    # [EN] "move into the bin -> restore immediately", when the original spot was empty anyway, so
    # [EN] the restore obviously succeeded. The criterion was meant to test conflict handling but
    # [EN] never created a conflict.
    ok2, _ = TR.move_run_to_trash(proj.root / names[2], proj.root, root)
    back = proj.root / names[2]
    back.mkdir(parents=True, exist_ok=True)
    ok3, why = TR.restore(TR.scan_trash(root)[0], root)
    rec('目标已存在时**拒绝恢复**（不覆盖）', (not ok3) and '已经有同名' in why,
        why[-40:])
    assert back.is_dir(), '拒绝恢复时不该动目标'
    back.rmdir()

    # ⑥ 子树：删父节点必须连子节点（用的是上面**动之前**那份 `parents0`）
    kids = TR.descendants(names[1], parents0)     # 第2次 的后代（3、4、5）
    rec('算得出**后代**（删一条带子节点的要一起走）',
        {names[2], names[3], names[4]} <= set(kids), f'{len(kids)} 条：{kids[:2]}…')
    rec('后代按**由深到浅**排（先叶子后父，否则路径会失效）',
        (names[4] in kids and names[2] in kids
         and kids.index(names[4]) < kids.index(names[2])),
        f'{kids}')

    # ⑦ 永久删除：目录真的没了
    ent = TR.scan_trash(root)[0]
    ok, _ = TR.purge(ent, root)
    rec('永久删除**真的删掉目录**', ok and not ent.path.exists(), str(ent.path)[-40:])
    rec('永久删除之后旁注也不留', not TR.sidecar_path(ent.path).exists(), '')

    # ⑧ 护栏：不许删回收站外面的东西
    outside = root / '不该被删'
    outside.mkdir(exist_ok=True)
    fake = TR.TrashEntry(path=outside, kind=TR.KIND_NOVEL, name='不该被删')
    ok, why = TR.purge(fake, root)
    rec('拒绝删除**回收站外面**的目录', (not ok) and outside.is_dir(), why[:30])
    ok, why = TR.restore(fake, root)
    rec('拒绝把**回收站外面**的东西"恢复"', (not ok) and outside.is_dir(), why[:30])

    # ══════════════════════════════════════════════════════════
    #  ⑨ 两边互补：拾卷 + 回收站 = 完整树（2026-10-21 第三批）
    #  用户：「两者合并起来是一个完整的树 两者是应该是互补的」
    #  [EN] Complementary sides: Pick-a-Volume + bin = one complete tree
    # ══════════════════════════════════════════════════════════
    _forest_checks(proj, root)

    # ══════════════════════════════════════════════════════════
    #  ⑩ 同一层按**生成时间正序**（2026-10-22 用户点名，两栏同一句话）
    #  [EN] Per-level order = generation time ascending (named by the user 2026-10-22)
    # ══════════════════════════════════════════════════════════
    _order_checks(root)


def _forest_checks(proj, root) -> None:
    """`forest()`：两边必须是**同一棵树**的两个半边。

    ★ 钉三件事，都是"合并成完整树"这件事的实质：
      ① 两边的 `parents` 与名字集合**完全一致**（各建各的就不一致）；
      ② 两边的 `mine` **不相交**，并集 = 全部名字（互补，不是覆盖）；
      ③ 同一条名字在两边**层级相同**（否则合并后会出现"同一个节点两个深度"）。
    """
    # 造一个"被删的父 + 活着的子"的半吊子局面 —— 这正是用户担心的那种
    # [EN] Build the half-restored case the user is worried about: deleted parent, live child
    names = [f'第{i}次模拟2026-11-{i:02d}-10-00' for i in range(1, 5)]
    for i, nm in enumerate(names, start=1):
        d = proj.root / nm
        (d / '每天的生活').mkdir(parents=True, exist_ok=True)
        (d / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n第 {i} 轮。\n', encoding='utf-8')
        LG.write_lineage(d, parent=(names[i - 2] if i > 1 else None),
                         kind='resume' if i > 1 else 'fresh')
        (d / '任务介绍.md').write_text(f'- **项目**：{proj.name}\n', encoding='utf-8')
    # 删掉第 1、2、3 次，只留第 4 次活着 ⇒ 拾卷里必须出现 1/2/3 三个虚线框
    for nm in names[:3]:
        TR.move_run_to_trash(proj.root / nm, proj.root, root)

    pick = TR.forest(proj.root, root, side='pick')
    trash = TR.forest(proj.root, root, side='trash')
    rec('两边 `parents` **完全一致**', pick.parents == trash.parents,
        f'{len(pick.parents)} vs {len(trash.parents)}')
    rec('两边名字集合一致', (pick.live | pick.deleted) == (trash.live | trash.deleted),
        f'{len(pick.live | pick.deleted)} 个名字')
    rec('两边 `mine` **不相交**（互补，不是互相覆盖）',
        not (pick.mine & trash.mine), f'{sorted(pick.mine)} / {sorted(trash.mine)}')
    rec('两边 `mine` 并集 = 全部（一个不漏）',
        (pick.mine | trash.mine) == (pick.live | pick.deleted),
        f'{len(pick.mine | trash.mine)}/{len(pick.live | pick.deleted)}')
    pm = {lg: d for (_p, d, _h, lg) in pick.rows}
    tm = {lg: d for (_p, d, _h, lg) in trash.rows}
    shared = set(pm) & set(tm)
    rec('同一条在两边的**层级相同**',
        all(pm[lg] == tm[lg] for lg in shared), f'{len(shared)} 条共有')

    # ★★ 用户点名的那一条：父没恢复 ⇒ 拾卷里父是虚线框
    # ⚠ 判据要写"树里的每个虚线框都确实是被删的"（⊆），不能写"两者相等"：
    #   这本书的 `deleted` 里还有**这次夹具之外**的条目（前面的步骤删过别的轮次），
    #   它们不在这棵树里，但确实是被删的 —— 用 `==` 会让判据因为无关数据而红
    #   （第一版就是这么写的，产品其实是对的）。
    # [EN] ⚠ The criterion must say "every dashed frame in the tree really is deleted" (⊆),
    # [EN] not "the two sets are equal": `deleted` also holds entries **outside this fixture**
    # [EN] (earlier steps deleted other rounds). They are not in this tree, but they are deleted --
    # [EN] using `==` makes the criterion red because of unrelated data (the first version did).
    rec('拾卷里出现**虚线框**（父节点还在回收站里）',
        bool(pick.rows) and (set(pm) - pick.mine) <= set(pick.deleted)
        and bool(set(pm) - pick.mine),
        f'虚线框 {sorted(set(pm) - pick.mine)}')
    rec('拾卷的实体里**只有活着的**那一条', pick.mine == pick.live,
        f'{sorted(pick.mine)}')
    # 关系还是对的：第4次挂在第3次下面，而不是被当成根
    # [EN] The lineage still holds: round 4 hangs under round 3 instead of becoming a root
    rec('第4次**挂在第3次下面**（没被顶成根节点）',
        pick.parents.get(names[3]) == names[2]
        and any(lg == names[2] for (_p, _d, _h, lg) in pick.rows),
        f'第4次的父={pick.parents.get(names[3])}')
    rec('回收站里撑树的**活祖先**是虚线框',
        (set(tm) - trash.mine) <= trash.live,
        f'虚线框 {sorted(set(tm) - trash.mine)}')


# ══════════════════════════════════════════════════════════════════
#  一·B、**同一层按生成时间正序**（2026-10-22 用户点名）
#
#  用户原话：「拾卷页面的存档同一级别（即所有根节点以及所有从某个节点推演出来的子节点）
#  默认按照从时间顺序排列 回收站也是这样」。
#
#  ★ 为什么单独造一本书：这件事的错法**只在一棵树有分叉、而且分支中间有一轮在回收站时**
#    才看得出来。一条直的链（每层只有一个孩子）无论怎么排都"看起来是对的" ——
#    第一版探针就差点用直链做夹具，那样判据恒绿而产品是坏的。
#
#  ★ 当时真实的错法（实测，不是推测）：
#    · 拾卷把**排序档**（默认"结束时间倒序"）当同层顺序传下去 ⇒ 兄弟是 5,4,2；
#    · 回收站不传、自己按序号升序 ⇒ 兄弟是 3；
#    · 回收站那个"按序号插值"假设活着的顺序是升序，而默认档是降序 ⇒ 连顺序都不是。
#    所以判据不能只查"是不是升序"，还要查**两栏用的是不是同一句话**。
# ══════════════════════════════════════════════════════════════════
def _time_of(name: str):
    """判据自己解析生成时间（**不用产品那个函数**）。

    ★ 为什么不用 `LG.run_time`：拿被测函数去验被测结果，等于什么都没验 ——
      它要是把时间解析错了，两边一起错，判据照样绿。
      这里独立写一份：名字里最后一个 `年-月-日-时-分`。
    """
    import re as _re
    found = _re.findall(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', str(name or ''))
    if not found:
        return None
    return tuple(int(x) for x in found[-1])


def _siblings(rows) -> dict:
    """从 `forest.rows`（前序 + 层级）还原**每一组兄弟**的先后顺序：`{父名|None: [子名…]}`。

    ★ 前序遍历 + 每行的层数足以还原父子关系：层数 d 的那一行，它的父就是**上一个层数
      小于 d 的行**。用一个按层递推的栈做，不用重新读 `parents`（那样等于用产品的结果
      去验产品的输出）。
    """
    groups: dict = {}
    stack: list = []
    for _p, d, _h, lg in rows or []:
        while len(stack) > d:
            stack.pop()
        parent = stack[d - 1] if (d > 0 and len(stack) >= d) else None
        groups.setdefault(parent, []).append(lg)
        stack.append(lg)
    return groups


def _ascending(groups: dict) -> tuple[bool, str]:
    """每组兄弟是不是**按生成时间非降序**。返回 `(对不对, 说明)`。"""
    bad = []
    for parent, kids in groups.items():
        times = [_time_of(k) for k in kids]
        known = [x for x in times if x is not None]
        if len(known) != len(times):
            bad.append(f'{parent or "根"}：有认不出时间的条目')
            continue
        if known != sorted(known):
            bad.append(f'{parent or "根"}：{[k[:6] for k in kids]}')
    return (not bad), ('；'.join(bad[:3]) if bad else '每组都是正序')


def _order_checks(root: Path) -> None:
    """同一层（根之间 / 同一父的子节点之间）必须按**生成时间正序**，两栏同一句话。"""
    book = Project.create_new(root, '同层排序书')
    # 第1次 = 根；第2/3/4/5 次都是第1次的儿子（分叉）；第3次夹在中间被删到回收站
    # 第6次是第1次的儿子，但**生成时间比谁都早**（数据里序号与时间不一致）——
    #   这一条专门分辨"按时间排"还是"按序号排"：只有真按时间排，它才排到最前面。
    plan = [
        ('第1次模拟2026-10-01-10-00', None),
        ('第2次模拟2026-10-02-10-00', '第1次模拟2026-10-01-10-00'),
        ('第3次模拟2026-10-03-10-00', '第1次模拟2026-10-01-10-00'),
        ('第4次模拟2026-10-04-10-00', '第1次模拟2026-10-01-10-00'),
        ('第5次模拟2026-10-05-10-00', '第1次模拟2026-10-01-10-00'),
        ('第6次模拟2026-09-20-08-00', '第1次模拟2026-10-01-10-00'),
    ]
    for nm, par in plan:
        d = book.root / nm
        (d / '每天的生活').mkdir(parents=True, exist_ok=True)
        (d / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n{nm}。\n', encoding='utf-8')
        LG.write_lineage(d, parent=par, kind='resume' if par else 'fresh')
    TR.move_run_to_trash(book.root / plan[2][0], book.root, root, parent=plan[2][1])

    pick = TR.forest(book.root, root, side='pick')
    trash = TR.forest(book.root, root, side='trash')
    pg, tg = _siblings(pick.rows), _siblings(trash.rows)

    okp, why_p = _ascending(pg)
    rec('排序 ① 拾卷：**每一组兄弟**都按生成时间正序', okp, why_p)
    okt, why_t = _ascending(tg)
    rec('排序 ② 回收站：**每一组兄弟**也按生成时间正序（用户："回收站也是这样"）',
        okt, why_t)

    # ★★★ 钉**具体那一条**（本项目的规矩：只查"是不是升序"会漏掉一半错法 ——
    #   比如"整体反过来"在每组只有一个孩子时看不出来）。
    #   第1次的儿子里有第6次（时间 09-20，比父亲的 10-01 还早）：
    #     · 按时间排 ⇒ [第6, 第2, 第4, 第5]
    #     · 按序号排 ⇒ [第2, 第4, 第5, 第6]（错）
    #     · 旧产品（排序档倒序 + 插值）⇒ [第5, 第4, 第2]（错，连第3次都掉了）
    r1 = '第1次模拟2026-10-01-10-00'
    kids_pick = [k[:3] for k in (pg.get(r1) or [])]
    rec('排序 ③ 拾卷里第1次的儿子 = **第6 / 第2 / 第4 / 第5**（按时间，不是按序号、'
        '更不是 5,4,2 那种倒序）',
        kids_pick == ['第6次', '第2次', '第4次', '第5次'],
        f'{kids_pick}')
    rec('排序 ④ 回收站里第1次的儿子 = **第3**（它是被删的那一个，位置也在中间）',
        [k[:3] for k in (tg.get(r1) or [])] == ['第3次'],
        f'{[k[:3] for k in (tg.get(r1) or [])]}')

    # ★★★ 两栏"同一句话"的**实质证据**：把两边各自的行，拿去和**同一份期望前序**比。
    #   期望前序是判据自己算的（自己的时间解析 + `parents` 这一个人人可见的事实），
    #   所以这不是"拿产品的输出验产品的输出"。
    #   两栏各排各的 ⇒ 至少有一边对不上（这正是修之前的样子）。
    ex_pick = _expected_preorder([lg for (_p, _d, _h, lg) in pick.rows], pick.parents)
    ex_trash = _expected_preorder([lg for (_p, _d, _h, lg) in trash.rows], trash.parents)
    rec('排序 ⑤ 拾卷的**整行顺序** == 独立算出的期望前序',
        ex_pick == [lg for (_p, _d, _h, lg) in pick.rows], f'{len(ex_pick)} 行')
    rec('排序 ⑥ 回收站的**整行顺序** == 同一算法算出的期望前序'
        '（两栏用的是同一句话，不是各排各的）',
        ex_trash == [lg for (_p, _d, _h, lg) in trash.rows], f'{len(ex_trash)} 行')

    # ★ 源码级两条：行为判据只能证明"现在对"，这两条守"以后别又接回去"。
    src = Path('gui/app_flet.py').read_text(encoding='utf-8')
    calls = [ln.strip() for ln in src.splitlines() if 'TRASH.forest(' in ln]
    rec('排序 ⑦ 拾卷调 `forest()` **不带 `order=`**（排序档只管默认选中哪一轮，'
        '不许再左右树的形状）',
        bool(calls) and all('order=' not in ln for ln in calls),
        ' / '.join(calls)[:110])
    body = _squash_src('store/trash.py')
    rec('排序 ⑧ `_merge_order` 的"按序号插值"已经删掉'
        '（它假设活着的顺序是升序，而默认档是降序 ⇒ 同一层排成 5,4,2）',
        'def _merge_order' not in body and '_merge_order(' not in body,
        '定义=%s 调用=%s' % ('def _merge_order' in body, '_merge_order(' in body))
    shutil.rmtree(book.root, ignore_errors=True)


def _expected_preorder(names, parents) -> list[str]:
    """判据自己算一遍"按时间正序的前序遍历"，用来和产品比。

    ★ 只用两样东西：**名字**（自己解析时间）和 `parents`（谁挂谁下面，它自己另有判据）。
      不调 `lineage.tree_order`、不调 `lineage.build_tree` —— 否则就是拿被测函数验它自己。
    """
    uniq = list(dict.fromkeys(names))
    have = set(uniq)

    def key(n):
        t = _time_of(n)
        return (t is None, t or (), n)

    kids: dict = {}
    roots: list = []
    for n in sorted(uniq, key=key):
        p = str((parents or {}).get(n) or '').strip()
        if p and p in have and p != n:
            kids.setdefault(p, []).append(n)
        else:
            roots.append(n)
    out: list = []
    seen: set = set()

    def walk(n):
        if n in seen:
            return
        seen.add(n)
        out.append(n)
        for k in kids.get(n, []):
            walk(k)

    for r in roots:
        walk(r)
    for n in sorted(uniq, key=key):
        walk(n)
    return out


def _squash_src(rel: str) -> str:
    """源码里**去掉 `#` 注释之后**的正文（用来查"某个名字还在不在代码里"）。

    ⚠ 直接 `in` 查全文会被**说明文字**骗到：函数删了但注释里还提到它，判据照样绿。
      所以先按行去掉 `#` 之后的部分，再查 `def 名字(` / `名字(` 这种**代码形状**。
    """
    out = []
    for ln in Path(rel).read_text(encoding='utf-8').splitlines():
        out.append(ln.split('#')[0])
    return '\n'.join(out)


# ══════════════════════════════════════════════════════════════════
#  二、界面层（真机）
# ══════════════════════════════════════════════════════════════════
def _make_ui_fixture(root: Path) -> Project:
    """造一本"父被删、子还活着"的书 —— 这是用户点名的那种半吊子状态。

    结构（5 轮一条链，**只留第 2 轮活着**，删掉第 1、3、4、5 轮）：
        第1次 ── 第2次 ── 第3次 ── 第4次 ── 第5次
        ↑ 已删   ↑ 活着   ↑ 已删   ↑ 已删   ↑ 已删

    ★ 为什么必须是这个形状（2026-10-21 第三批）：用户的原话是「如果我恢复某个节点
      但是其父节点在拾卷里没被恢复则对应节点也要显示成虚线框」—— 要验证这一条，
      夹具里**必须**出现"活着的节点有一个被删的父"。第一版留的是第 1、2 轮活着、
      删 3~5，那种情况下活着的都是根，拾卷里**根本不会**有虚线框，
      判据于是恒红（而产品其实是对的）。

    于是：
      · 拾卷里应显示：第1次 = **虚线框**（在回收站）+ 第2次 = 实体；
      · 回收站里应显示：第1/3/4/5次 = 实体 + 第2次 = **虚线框**（活着的撑树节点）。

        English:
    Build a book where **the parent is deleted while its child is still live** -- exactly the
    half-restored state the user named.
    Structure (a chain of 5; **only round 2 stays live**; rounds 1, 3, 4, 5 are deleted).
    ★ Why this shape (third round, 2026-10-21): the user said "if I restore a node whose parent was
      not restored, that node must also show a dashed frame" -- to test that, the fixture **must**
      contain a live node with a deleted parent. The first version kept rounds 1 and 2 live and
      deleted 3-5; then every live node was a root, Pick-a-Volume would have **no** dashed frame at
      all, and the criterion was permanently red while the product was correct.
    """
    proj = Project.create_new(root, '回收站界面书')
    names = [f'第{i}次模拟2026-10-{i:02d}-10-00' for i in range(1, 6)]
    for i, nm in enumerate(names, start=1):
        d = proj.root / nm
        (d / '每天的生活').mkdir(parents=True, exist_ok=True)
        (d / '每天的生活' / '第001天.md').write_text(
            f'# 第 1 天\n\n第 {i} 轮发生的事情。\n', encoding='utf-8')
        (d / 'state.db').write_text('', encoding='utf-8')
        LG.write_lineage(d, parent=(names[i - 2] if i > 1 else None),
                         kind='resume' if i > 1 else 'fresh')
        (d / '任务介绍.md').write_text(
            f'- **项目**：{proj.name}\n', encoding='utf-8')
    for i in (0, 2, 3, 4):                 # 只留第 2 轮活着
        TR.move_run_to_trash(proj.root / names[i], proj.root, root)
    # 再来一本**整本都在回收站**的书（所有节点都是实体框）
    p2 = Project.create_new(root, '整本已删的书')
    for i in (1, 2):
        d = p2.root / f'第{i}次模拟2026-10-0{i}-09-00'
        (d / '每天的生活').mkdir(parents=True, exist_ok=True)
        (d / '每天的生活' / '第001天.md').write_text('# 第 1 天\n\n正文。\n',
                                                encoding='utf-8')
        (d / 'state.db').write_text('', encoding='utf-8')
        LG.write_lineage(d, parent=(None if i == 1 else f'第1次模拟2026-10-0{i}-09-00'))
    TR.move_project_to_trash(p2.root, root)
    return proj


def _walk(c, depth=0, acc=None):
    """遍历控件树（Flet 的子树藏在 controls / content 里）。"""
    if acc is None:
        acc = []
    if depth > 22 or c is None:
        return acc
    acc.append(c)
    kids = getattr(c, 'controls', None)
    if isinstance(kids, list):
        for x in kids:
            _walk(x, depth + 1, acc)
    v = getattr(c, 'content', None)
    if v is not None and not isinstance(v, (str, int, float)):
        _walk(v, depth + 1, acc)
    return acc


def _texts(c) -> list[str]:
    out = []
    for x in _walk(c):
        if isinstance(x, ft.Text) and isinstance(x.value, str):
            out.append(x.value)
    return out


async def ui_layer(page: ft.Page, tmp: Path) -> None:
    import gui.app_flet as G

    VU.isolate_projects_dir(tmp / 'Projects')
    root = Path(G.CFG.projects_dir())
    proj = _make_ui_fixture(root)
    _PROJECT_FOR_CHECK[0] = proj

    app = G.NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(0.5)
    app.show_projects_dialog()
    await asyncio.sleep(0.8)
    page.update()

    dlg = VU.open_dialogs(page)[-1]
    content = getattr(dlg.content, 'content', dlg.content)

    # ── Tab 条：两个、竖排、在最左边 ──
    tabs = [c for c in _walk(content) if getattr(c, '_tab_key', None)]
    rec('最左边有两个 Tab', len(tabs) == 2,
        ' / '.join(getattr(c, '_tab_key', '') for c in tabs))
    if len(tabs) == 2:
        rec('**拾卷在上、回收站在下**（用户指定的顺序）',
            tabs[0]._tab_key == 'pick' and tabs[1]._tab_key == 'trash',
            f'{tabs[0]._tab_key} → {tabs[1]._tab_key}')
        labels = [''.join(x.value for x in _walk(c) if isinstance(x, ft.Text))
                  for c in tabs]
        rec('两个 Tab 的名字是「拾卷」「回收站」',
            labels[0] == '拾卷' and labels[1] == '回收站', str(labels))
        # Tab 条在整个对话框的**最左**：它是顶层 `Row` 的**第一个**子控件，
        # 而内容（三栏）在第二个 —— 这是"竖排在左边"而不是"横排在上面"的判据。
        # [EN] The strip is the **first** child of the top-level `Row` and the content is the second --
        # [EN] that is what "vertical, on the left" means vs "horizontal, on top".
        top_row, top_kids = _row_with_tabs(content, tabs)
        first_keys = {getattr(x, '_tab_key', None)
                      for x in _walk(top_kids[0])} if top_kids else set()
        second_txt = '\n'.join(_texts(top_kids[1])) if top_kids else ''
        rec('Tab 条在内容**左边**（顶层 Row 的第一个子控件）',
            top_row is not None and 'pick' in first_keys
            and 'trash' in first_keys and '①' in second_txt,
            f'第一个子控件含 Tab={"pick" in first_keys}/'
            f'第二个含三栏={"①" in second_txt}')

    # ── 切到回收站 ──
    tabs[1].on_click(None)
    await asyncio.sleep(0.6)
    page.update()
    trash_view = getattr(dlg.content, 'content')
    all_txt = '\n'.join(_texts(trash_view))
    rec('切到回收站后**换了内容**（不是原样不动）',
        '回收站里的书' in all_txt, all_txt[:40].replace('\n', ' '))
    rec('中间列的**注释**说明了实线/虚线（用户点名要的那句）',
        ('虚线框' in all_txt and '没有' in all_txt and '撑树' in all_txt),
        [x for x in _texts(trash_view) if '虚线' in x][:1])

    # ── 左栏：整本删的书 + 只删了存档的书 ──
    rec('左栏两种书都在（整本已删 / 只有存档被删）',
        '整本已删的书' in all_txt and '回收站界面书' in all_txt,
        '')
    rec('"书还在"那种卡片**说明了它没被删**',
        '书还在' in all_txt, [x for x in _texts(trash_view) if '书还在' in x][:1])

    # ── 打开"只有存档被删"的那一本 → 必须有虚线节点 ──
    bucket_cards = [c for c in _walk(trash_view)
                    if getattr(c, '_bucket', None)]
    live_card = next((c for c in bucket_cards
                      if c._bucket[0] == 'live'), None)
    rec('左栏里找得到"书还在"那一桶', live_card is not None,
        f'{len(bucket_cards)} 张卡')
    if live_card is not None:
        live_card.on_click(None)
        await asyncio.sleep(0.5)
        page.update()
        nodes = [c for c in _walk(getattr(dlg.content, 'content'))
                 if getattr(c, '_card', None) is not None
                 and getattr(c._card, '_t_path', None) is not None]
        placeholders = [c for c in nodes
                        if getattr(c._card, '_placeholder', False)]
        solid = [c for c in nodes if not getattr(c._card, '_placeholder', False)]
        rec('回收站树里有**撑树的父节点**（没被删除的）', len(placeholders) == 1,
            f'{len(placeholders)} 个（应为 1：第2次）'
            f' 树={[c._card._t_path.name[:4] for c in nodes]}')
        rec('真删的节点都在（第1、3、4、5次）', len(solid) == 4,
            f'{len(solid)} 个 桶={live_card._bucket[0]}'
            f' 条目={len(live_card._bucket[2])}')
        rec('撑树的节点是**虚线框**',
            len(placeholders) == 1 and all(
                _has_dashed(c) for c in placeholders),
            f'{sum(1 for c in placeholders if _has_dashed(c))}/'
            f'{len(placeholders)} 有虚线')
        rec('撑树的节点**没有勾选框**（它没被删，不该能删）',
            all(_count_check(c) == 0 for c in placeholders),
            str([_count_check(c) for c in placeholders]))
        rec('真删的节点**有勾选框**',
            all(_count_check(c) >= 1 for c in solid) if solid else False,
            str([_count_check(c) for c in solid]))

    # ── 列头按钮（一对：恢复选中 + 永久删除）──
    # ★ 2026-10-21 第二批用户要求：「除了删除选中 还需要有一个恢复选中 删除小说那边
    #   也有这样一个按钮」⇒ 两栏都要有这一对。
    # [EN] Header buttons (a pair: restore + purge) -- the second request of 2026-10-21.
    heads_del = [x for x in _texts(trash_view) if x.startswith('永久删除')]
    heads_rest = [x for x in _texts(trash_view) if x.startswith('恢复选中')]
    rec('回收站列头有「永久删除（多选）」', len(heads_del) >= 2,
        f'{len(heads_del)} 处（书栏 + 存档栏各一）')
    rec('回收站列头有「恢复选中（多选）」', len(heads_rest) >= 2,
        f'{len(heads_rest)} 处（书栏 + 存档栏各一）')

    # ══════════════════════════════════════════════════════════
    #  两栏的按钮**各管自己列**（2026-10-21 第四批用户报缺陷）
    #  用户：「选中一批 点永久删除没反应 而且两个永久删除互相联动了
    #        它们本来应该自己管自己列才对」
    #
    #  ★★★ 上一版的判据只数了"有没有两个按钮" —— **三条 bug 一条都没抓到**：
    #    ① 两个按钮里面的 `ft.Text` 是**同一个对象**（联动）；
    #    ② 回调不带参数，靠"书栏有勾就先删书"分流（串列）；
    #    ③ `_collect` 按 5 个解包而实际返回 6 个 ⇒ 每次点击 ValueError ⇒ **完全没反应**。
    #    这三条都能通过"数按钮个数"，所以判据必须**点一下、看结果**。
    # [EN] The criteria below pin "each column manages its own" (the user-reported defect of
    # [EN] 2026-10-21, fourth round). ★★★ The previous version only counted buttons, so **none of the
    # [EN] three bugs were caught**: ① the two buttons' `ft.Text` was one shared object (linked);
    # [EN] ② the callback took no argument and split by "books first" (crossed columns);
    # [EN] ③ `_collect` unpacked 5 while returning 6 => ValueError on every click => **nothing
    # [EN] happened**. All three pass "count the buttons", so the criteria must **click and observe**.
    # ══════════════════════════════════════════════════════════
    _head_buttons_checks(page, dlg)

    # ── 拾卷里的虚线框（**必须在恢复之前测**）──
    # ★ 顺序有讲究：`_restore_click_check` 会把被删的存档搬回去，一搬，"父在回收站"这个
    #   局面就没了 —— 之后再测"拾卷里有没有虚线框"必然是零个（夹具已被自己改掉）。
    #   第一版正是这个顺序，判据只能靠运气。
    # [EN] The dashed frame in Pick-a-Volume **must be checked before restoring**: the restore
    # [EN] moves deleted saves back, and once that happens the "parent is in the bin" situation is
    # [EN] gone -- checking afterwards would always find zero (the fixture changed itself).
    tabs[0].on_click(None)
    await asyncio.sleep(0.5)
    page.update()
    _pick_dashed_check(dlg.content.content)
    tabs[1].on_click(None)
    await asyncio.sleep(0.5)
    page.update()

    # ── **真去点**「恢复选中」：把勾上的存档搬回去 ──
    # 用户要的是"能恢复"，不是"按钮在那儿"。所以这里勾一条、点恢复、看它是否
    # 真的回到了原来的书里，并检查勾被清掉、列头数字回到 0。
    # [EN] **Actually click** restore: tick one, click restore, and check it really went back into
    # its book, the ticks were cleared and the header count returned to zero.
    if live_card is not None:
        _restore_click_check(page, dlg, live_card)
        # 恢复会重建整个 Tab（勾与选中都变了），要重新取一次当前的回收站视图
        # [EN] Restore rebuilds the whole tab, so re-read the current view
        tabs[1].on_click(None)
        await asyncio.sleep(0.6)
        page.update()
        trash_view = dlg.content.content

    # ── 提示词：拾卷不要求打名字 / 回收站要求 ──
    tabs[0].on_click(None)           # 切回拾卷
    await asyncio.sleep(0.5)
    page.update()
    pick_view = dlg.content.content
    pv_text = '\n'.join(_texts(pick_view))
    rec('拾卷的栏头有「删除选中」（小说、存档各一个）',
        pv_text.count('删除选中') >= 2, f"{pv_text.count('删除选中')} 个")
    rec('拾卷里**没有**"手打书名"的要求了',
        '手打一次书名' not in pv_text, '')
    # ⚠ 数字是 `1 个小说卡 + 活着的存档数`（这本夹具只有 1 轮活着 ⇒ 2 个）。
    #   写死一个更大的数会让判据因为"夹具里活着的轮次变少"而红 —— 那是夹具的事，不是产品的。
    # [EN] The number is `1 novel card + live saves` (this fixture has 1 live round => 2). A larger
    # [EN] hardcoded number would go red merely because the fixture has fewer live rounds.
    _live_n = len(TR.forest(proj.root, root, side='pick').live)
    rec('拾卷的小说卡、存档节点都带勾选框',
        _count_check(pick_view) == 1 + _live_n,
        f'{_count_check(pick_view)} 个（应为 1 本 + {_live_n} 轮）')

    # ★★ 2026-10-21 第三批（用户：「回收站里的存档条目也应该可以展开」）
    # [EN] Third round: bin entries must be expandable too.
    _bin_expand_check(page, dlg)

    # ══════════════════════════════════════════════════════════
    #  级联勾选（用户：「选中某个节点，其子节点会被自动选中，而且在父节点被选中的时候，
    #  所有子节点的复选框是灰色的，无法被取消选中。要选择子节点，只能够取消父节点选中，
    #  然后在子节点里选择」）
    #  [EN] Cascade ticking (user: "checking a node auto-checks its children, and while the parent
    #  [EN] is checked all child checkboxes are grey and cannot be unchecked. To pick a child you
    #  [EN] must uncheck the parent first")
    # ══════════════════════════════════════════════════════════
    _cascade_checks(page, dlg, proj)

    # ══════════════════════════════════════════════════════════
    #  两栏的「全选」（2026-10-31 用户：「拾卷 回收站里 也需要有全选」）
    #  ★ 放在级联之后：级联那一段收尾时把勾都清了，这里才量得到干净的"未选"档。
    #  ★ 它自己会把勾清干净再退出，不影响后面任何一条判据。
    # [EN] "Select all" in both columns (2026-10-31). ★ Runs after the cascade section, which
    # [EN] ends with everything unticked -- that is the clean state this one measures from.
    # ══════════════════════════════════════════════════════════
    _trash_select_all_check(page, dlg)


def _restore_btns_by_column(view) -> dict:
    """回收站里**两栏各自的**「恢复选中」按钮：`{'novels': …, 'runs': …}`。

    ★ 按**结构**认（顶层三栏 Row 的第 1 / 第 2 个子控件），不按文字：
      两栏的按钮文字一模一样（都叫「恢复选中」），靠文字分不开。
    ★ 为什么需要它：两栏的按钮在 2026-10-21 第四批之后**各管自己列**，
      点错栏的按钮什么也不会发生（这正是用户报的 symptom 之一）。
    """
    row = None
    for c in _walk(view):
        if isinstance(c, ft.Row) and len(c.controls or []) >= 2:
            # ⚠ `_texts()` 返回的是**字符串**，不能再取 `.value`（第一版就是这么写错的，
            #   于是一直"找不到三栏那一排"，而产品其实是对的）
            # [EN] ⚠ `_texts()` returns **strings**, so don't take `.value` on them (the first
            # [EN] version did, so it never found the three-column row while the product was fine)
            if any('① 回收站里的书' in x for x in _texts(c.controls[0])):
                row = c
                break
    if row is None:
        return {}

    def _find(col):
        for c in _walk(col):
            if (isinstance(c, ft.Container) and getattr(c, 'on_click', None)
                    and any('恢复选中' in (x.value or '') for x in _walk(c)
                            if isinstance(x, ft.Text))):
                return c
        return None

    return {'novels': _find(row.controls[0]), 'runs': _find(row.controls[1])}


def _close_extra_dialogs(page) -> None:
    """把**这一轮新开的**确认框都关掉（只留最底下那个拾卷对话框）。

    ★ 为什么要它：判据会连着点好几次「永久删除」，每次都开一个确认框；
      不关的话它们一层层叠着，后面 `open_dialogs(page)[-1]` 读到的就不再是刚开的那个。
    ★ 怎么认"该关的"：拾卷对话框是最底下一层，**只保留 `controls[0]`**。
    """
    try:
        dlgs = VU.open_dialogs(page)
        while len(dlgs) > 1:
            page.pop_dialog()
            dlgs = VU.open_dialogs(page)
    except Exception:                                    # noqa: BLE001
        pass


def _head_buttons_checks(page, dlg) -> None:
    """两栏的删除/恢复按钮：**各自的控件**、**点了有用**、**不串列**。

    ★★★ 这三条是 2026-10-21 用户报的三个 bug 的直接判据。判据必须"点一下看结果"，
      因为三条 bug 全都通过"按钮在不在"这种静态检查：
        ① 联动 —— 两栏按钮里的 `ft.Text` 是同一个对象（改一处两处动）；
        ② 串列 —— 回调不分栏，书栏有勾时在存档栏按下去会删书；
        ③ 没反应 —— `_collect` 解包个数不对，每次点击 ValueError，界面一片安静。

    ★ 怎么认出"书栏那个"和"存档栏那个"：按**结构**（顶层 Row 的第 1 / 第 2 个子控件），
      不按文字 —— 两栏的按钮文字一模一样，认不出来。
    """
    view = dlg.content.content
    row = None
    for c in _walk(view):
        if isinstance(c, ft.Row) and len(c.controls or []) >= 2:
            # ⚠ `_texts()` 返回字符串，不要取 `.value`（第一版这么写，一直"找不到三栏那一排"）
            # [EN] ⚠ `_texts()` returns strings; don't take `.value`
            if any('① 回收站里的书' in x for x in _texts(c.controls[0])):
                row = c
                break
    if row is None:
        rec('栏头按钮：找得到三栏那一排', False, '')
        return
    col_novel, col_save = row.controls[0], row.controls[1]

    def _del_btn_in(col):
        for c in _walk(col):
            if (isinstance(c, ft.Container) and getattr(c, 'on_click', None)
                    and any('永久删除' in (x.value or '') for x in _walk(c)
                            if isinstance(x, ft.Text))):
                return c
        return None

    def _lbl_in(btn):
        return next((x for x in _walk(btn) if isinstance(x, ft.Text)
                     and '永久删除' in (x.value or '')), None)

    b_book, b_save = _del_btn_in(col_novel), _del_btn_in(col_save)
    if b_book is None or b_save is None:
        rec('栏头按钮：两栏各找得到一个「永久删除」', False,
            f'书栏={"有" if b_book else "无"} 存档栏={"有" if b_save else "无"}')
        return

    # ① 不联动：两个按钮、以及它们里面的标签，都必须是**不同的对象**
    # [EN] ① Not linked: the two buttons and their labels must be **different objects**
    rec('① 两栏的「永久删除」是**两个不同控件**（不是同一个对象挂两处）',
        b_book is not b_save, f'id={id(b_book)} / {id(b_save)}')
    lb, ls = _lbl_in(b_book), _lbl_in(b_save)
    rec('① 两栏按钮里的**文字标签**也是两个不同控件（联动的真凶就在这里）',
        lb is not None and ls is not None and lb is not ls,
        f'id={id(lb) if lb else None} / {id(ls) if ls else None}')

    # ② 各算各的数：只有存档被勾时，**书栏的按钮不该显示数字**
    # [EN] ② Independent counts: with only saves ticked, the **book column must show no number**
    rows = [c for c in _walk(col_save) if getattr(c, '_card', None) is not None
            and getattr(c._card, '_t_path', None) is not None
            and not getattr(c._card, '_placeholder', False)]
    if not rows:
        rec('② 存档栏里有可勾的节点', False, '')
        return
    box = _check_box(rows[0])
    if box is None:
        rec('② 那一行有复选框', False, '')
        return
    box.on_click(None)                          # 勾一轮存档
    rec('② 勾存档后：**存档栏**按钮出现数字',
        '（' in (ls.value or '') if ls else False, f'{ls.value if ls else ""!r}')
    rec('② 勾存档后：**书栏**按钮**不跟着变**（各算各的）',
        '（' not in (lb.value or '') if lb else False,
        f'{lb.value if lb else ""!r}')

    # ③ 点存档栏的删除 ⇒ **弹出确认框**（抓"没反应"），并单独记"这一下有没有抛异常"
    #   ★ "抛异常"必须单独成一条断言：`_collect` 解包个数不对那类 bug 会让**整个脚本崩掉**，
    #     那时"判据变红"是假红（红的是"跑完（没有崩）"）。反例法 ⑨ 正是照出这一点的。
    # [EN] ③ Clicking the saves column's delete => **a confirm dialog appears**, and record separately
    # [EN] whether the click raised. ★ The raise must be its own assertion: an arity bug crashes the
    # [EN] whole script, and then "the criterion went red" is fake. Mutation ⑨ exposed this.
    click_err = ''
    before = len(VU.open_dialogs(page))
    try:
        b_save.on_click(None)
    except Exception as e:                               # noqa: BLE001
        click_err = repr(e)
    after = len(VU.open_dialogs(page))
    dlg_txt = '\n'.join(_texts(VU.open_dialogs(page)[-1])) if after > before else ''
    rec('③ 点「永久删除」**本身不抛异常**（抛了就等于"点了没反应"）',
        not click_err, click_err[:100] or '没有异常')
    rec('③ 点存档栏「永久删除」⇒ **真的弹出确认框**（不是点了没反应）',
        after > before, f'对话框 {before} → {after}')
    rec('③ 那个确认框说的是**轮**（存档），不是"本"（小说）',
        ('轮' in dlg_txt) and ('本小说' not in dlg_txt),
        (dlg_txt[:60].replace('\n', ' ') or '（没有对话框）'))
    _close_extra_dialogs(page)

    # ④ **串列**：两栏都勾上，再分别点两栏的按钮，各自只能谈自己那一类。
    #   ★★★ 这一条是返工来的（2026-10-21）：错法是"书栏有勾就先删书"，
    #     只有**两栏都有勾、而用户点的是存档栏**时才会露出来。
    #     ⚠ 我先后写过两版都不对：①只勾存档点存档栏（错法与对法行为一样）；
    #       ②两栏都勾点书栏（两者也都删书）。**判据必须精确命中那个分歧点**，
    #       否则它对变异完全无感 —— 反例法 ⑩ 一直不红就是这两版造成的。
    #   ⚠ 只有 `kind == 'novel'` 的桶卡才有勾选框（"书还在"那几种本来就不该能删）；
    #     第一版找 `_proj`（拾卷的属性名）找错了，于是这条判据静默跳过。
    # [EN] ④ **Cross-column**: tick both columns, then press each one; each must speak only about its
    # [EN] own kind. ★★★ Reworked (2026-10-21): the wrong code is "if a book is ticked, delete
    # [EN] books", which only shows when **both are ticked and the user pressed the SAVES column**.
    # [EN] ⚠ Two earlier versions were both wrong: ① tick only saves and press saves (identical
    # [EN] behaviour); ② tick both and press books (both delete books). **A criterion must hit the
    # [EN] exact point of divergence**, otherwise it is blind to the mutation. ⚠ Only
    # [EN] `kind == 'novel'` bucket cards have a checkbox; the first version looked for `_proj`
    # [EN] (a Pick-a-Volume attribute) and silently skipped the check.
    book_rows = [c for c in _walk(col_novel)
                 if getattr(c, '_bucket', None) and c._bucket[0] == 'novel']
    bchk = _check_box(book_rows[0]) if book_rows else None
    if bchk is None:
        rec('④ 找得到"整本已删"的书卡及其勾选框（要勾一本书才测得了串列）', False, '')
    else:
        bchk.on_click(None)                     # 勾一本书（此时两栏都有勾）
        b0 = len(VU.open_dialogs(page))
        book_err = ''
        try:
            b_save.on_click(None)               # 点**存档栏**的删除
        except Exception as e:                  # noqa: BLE001
            book_err = repr(e)
        a0 = len(VU.open_dialogs(page))
        t0 = '\n'.join(_texts(VU.open_dialogs(page)[-1])) if a0 > b0 else ''
        rec('④ 两栏都勾着时，点**存档栏**删除 ⇒ 只谈**轮**（不串去删书）',
            (not book_err) and a0 > b0 and '轮' in t0 and '本小说' not in t0,
            book_err[:80] or (t0[:70].replace('\n', ' ') or f'对话框 {b0} → {a0}'))
        _close_extra_dialogs(page)
        b1 = len(VU.open_dialogs(page))
        try:
            b_book.on_click(None)               # 再点**书栏**的删除
        except Exception:                       # noqa: BLE001
            pass
        a1 = len(VU.open_dialogs(page))
        t1 = '\n'.join(_texts(VU.open_dialogs(page)[-1])) if a1 > b1 else ''
        rec('④ 两栏都勾着时，点**书栏**删除 ⇒ 只谈**小说**（不串去删存档）',
            a1 > b1 and '小说' in t1 and '轮' not in t1,
            (t1[:70].replace('\n', ' ') or f'对话框 {b1} → {a1}'))
        _close_extra_dialogs(page)
        bchk.on_click(None)                     # 取消这本书
    box.on_click(None)                          # 取消那轮存档
    _ = page


def _pick_dashed_check(view) -> None:
    """**拾卷**里也要有虚线框：父节点还在回收站、子节点已经恢复时，父必须当虚线框撑树。

    ★ 为什么非得看界面：数据层 `forest()` 全绿也可能漏画（`placeholder` 参数传错、
      `mk_dashed_frame` 没套上、勾选框忘了去掉）—— 这个项目踩过"数据对、界面死"。
      这里同时钉三条：有虚线、**没有勾选框**、写着"在回收站"。
    """
    rows = [c for c in _walk(view) if getattr(c, '_card', None) is not None
            and getattr(c._card, '_run', None) is not None]
    dashed = [c for c in rows if getattr(c._card, '_placeholder', False)]
    solid = [c for c in rows if not getattr(c._card, '_placeholder', False)]
    rec('拾卷里**画出了虚线框**节点（父在回收站）', bool(dashed),
        f'{len(dashed)} 个虚线 / {len(solid)} 个实体')
    rec('拾卷的虚线框套了**真的虚线**（不是只改个变量名）',
        bool(dashed) and all(_has_dashed(c) for c in dashed),
        f'{sum(1 for c in dashed if _has_dashed(c))}/{len(dashed)} 有虚线')
    rec('拾卷的虚线框**没有勾选框**（它不在这边，删不到）',
        all(_count_check(c) == 0 for c in dashed) if dashed else False,
        str([_count_check(c) for c in dashed]))
    txt = '\n'.join(_texts(view))
    rec('拾卷的虚线框写着「在回收站」（说出原因，不只画个框）',
        '在回收站' in txt, '')


def _bin_expand_check(page, dlg) -> None:
    """**回收站里的条目也能展开**（用户：「回收站里的存档条目也应该可以展开」）。

    ★ 判据是"点一下三角，展开区真的可见了"：只查"有个三角"是假判据 ——
      本项目刚栽过"三角在那儿、点了永远没反应"（`ft.Icon` 写了 `.name`）。
    """
    tabs = [c for c in _walk(dlg.content.content)
            if getattr(c, '_tab_key', None)]
    trash_tab = next((c for c in tabs if c._tab_key == 'trash'), None)
    if trash_tab is None:
        rec('回收站条目可展开：找得到回收站 Tab', False, '')
        return
    trash_tab.on_click(None)
    view = dlg.content.content
    rows = [c for c in _walk(view) if getattr(c, '_card', None) is not None
            and getattr(c._card, '_t_path', None) is not None
            and not getattr(c._card, '_placeholder', False)]
    if not rows:
        rec('回收站条目可展开：中间栏有实体节点', False, '')
        return
    caret = VU.find_caret(rows[0])
    box = _expand_box_of(rows[0])
    if caret is None or box is None:
        rec('回收站条目可展开：节点上有三角 + 展开区', False,
            f'三角={"有" if caret else "无"} 展开区={"有" if box else "无"}')
        return
    caret.on_click(None)
    opened = bool(getattr(box, 'visible', False))
    flipped = getattr(getattr(caret, 'content', None), 'icon', None) \
        == ft.Icons.KEYBOARD_ARROW_DOWN
    rec('点回收站条目的三角 ⇒ **真的展开**（可见 + 箭头翻转）',
        opened and flipped, f'可见={opened} 翻转={flipped}')
    caret.on_click(None)
    rec('再点一下能收起',
        getattr(box, 'visible', True) is False, '')
    _ = page


def _expand_box_of(card):
    """卡片里那个展开区（`_mk_expander` 的产物：`visible=False` 的容器，内含 Markdown）。"""
    for c in _walk(card):
        if isinstance(c, ft.Container) and getattr(c, 'visible', None) is False:
            inner = getattr(c, 'content', None)
            if inner is not None and any(isinstance(x, ft.Markdown)
                                         for x in _walk(inner)):
                return c
    return None


def _restore_click_check(page, dlg, live_card) -> None:
    """在回收站里勾一条存档，点「恢复选中」，看它是不是真的回到了原来的书里。

    ★ 为什么必须真点：这个项目刚栽过一次"数据全对、按钮点了没反应"。恢复按钮
      尤其危险 —— 它有两个必须同时成立的条件（勾了东西、`_entry_for` 拿到正确的
      **逻辑名**）。名字取错的表现不是报错，而是"恢复到书里之后叫
      `20261021-175403_存档_第3次模拟…`"，血统当场断掉。所以这里查的是
      **磁盘上多出来的目录名**里有没有时间戳前缀。
    """
    proj = _PROJECT_FOR_CHECK[0]
    view = dlg.content.content
    rows = [c for c in _walk(view) if getattr(c, '_card', None) is not None
            and getattr(c._card, '_t_path', None) is not None
            and not getattr(c._card, '_placeholder', False)]
    if not rows:
        rec('恢复选中：中间栏有可勾的节点', False, '一个都没有')
        return
    # ★ 挑**最深**（没有后代）的那一条：勾父节点会级联勾上所有后代，恢复时
    #   会把它们**一起搬回去** —— 那会把夹具改得面目全非（第一版勾了第 1 次，
    #   结果一次恢复搬回 4 条，后面所有判据都在另一套夹具上跑）。
    # [EN] Pick the **deepest** (leaf) node: ticking a parent cascades to all descendants and the
    # [EN] restore moves them **all** back -- which wrecks the fixture (the first version ticked round
    # [EN] 1 and one restore moved 4 rounds, so every later check ran on a different fixture).
    def _depth_key(c):
        return len([x for x in _walk(c) if getattr(x, 'left', None) is not None])
    row = sorted(rows, key=_depth_key)[-1]
    box = _check_box(row)
    if box is None:
        rec('恢复选中：那一行有复选框', False, '')
        return
    target = row._card._t_path
    logical = target.name
    box.on_click(None)                      # 勾上
    rec('勾上一条存档后列头出现数字', _ticked(box), f'勾={_ticked(box)}')

    # 找**存档栏**那个「恢复选中」按钮。
    # ⚠ 不能"点第一个就行"了（2026-10-21 第四批）：两栏的按钮现在**各管自己列**，
    #   第一个是书栏的 —— 点了会说"这一栏（小说）还没勾"，什么也不会发生。
    #   这正是那个 bug 的另一面：**判据必须知道自己在点哪一栏的按钮**。
    # [EN] Find the **saves column's** restore button. ⚠ "Click the first one" no longer works: each
    # [EN] column now manages its own, so the first is the book column's -- clicking it says "nothing
    # [EN] ticked in this column" and nothing happens. That is the other face of the same bug: **the
    # [EN] criterion must know which column's button it is clicking**.
    btns = _restore_btns_by_column(view)
    if not btns.get('runs'):
        rec('恢复选中：找得到**存档栏**那个按钮', False, f'找到 {list(btns)}')
        return
    before = {p.name for p in proj.list_runs()}
    btns['runs'].on_click(None)             # ★ 真点（存档栏那个）
    after = {p.name for p in proj.list_runs()}
    new = sorted(after - before)
    rec('点「恢复选中」⇒ 存档**真的回到了书里**', bool(new),
        f'新增 {new[:2]} / 回收站里原本是 {target.name[:24]}')
    # 恢复回去的名字必须是**逻辑名**（不能带 `20261021-175403_存档_` 前缀）
    # [EN] The restored name must be the **logical** one (no `20261021-..._存档_` prefix)
    rec('恢复回去的名字是**原来的名字**（不带回收站的时间戳前缀）',
        bool(new) and all(not n[:8].isdigit() for n in new),
        f'{new[:1]}')
    _ = page
    _ = logical


def _cascade_checks(page, dlg, proj) -> None:
    """**在回收站里**真去点一个父节点的复选框，看子节点是否被连带勾上并锁灰。

    ★ 为什么在回收站这一侧测（2026-10-21 第三批）：夹具是"父被删、子活着"，
      所以拾卷那边只剩 1 个实体节点（没有父子对可点），而回收站这边有
      第 1、3、4、5 次四个实体，第 3 次下面挂着第 4、5 次 —— 正好能测级联。
      规则本身两边共用一份实现（`_run_toggle` / `_t_run_toggle` 结构相同，
      且都按"树的语义"走），所以在这一侧验证等价于两侧都验证。

    ★ 全程**只通过界面**判断：点那个方框（调它的 `on_click`）、读图标画成什么样。
      不读内部 `state` 字典 —— 那是把判据钉在实现细节上，一改结构就假红；
      而用户看到的就是"勾/没勾、灰/不灰"。

        English:
    **In the recycle bin**, really click a parent's checkbox and see whether its children get
    ticked and locked.
    ★ Why on the bin side (third round): the fixture is "parent deleted, child live", so
      Pick-a-Volume has only one solid node (no parent/child pair to click), while the bin has four
      solid rounds (1, 3, 4, 5) with 4 and 5 under 3 -- exactly what the cascade needs. The rule
      shares one implementation on both sides, so verifying it here verifies both.
    ★ Everything is judged **through the UI only**: click the box (call its `on_click`) and read how
      the icon is painted. Never read the internal `state` dict -- that pins the criterion to an
      implementation detail and goes falsely red on any refactor; what the user sees is
      "ticked/not, grey/not".
    """
    tabs = [c for c in _walk(dlg.content.content)
            if getattr(c, '_tab_key', None)]
    trash_tab = next((c for c in tabs if c._tab_key == 'trash'), None)
    if trash_tab is None:
        rec('级联勾选：找得到回收站 Tab', False, '')
        return
    trash_tab.on_click(None)
    view = dlg.content.content
    # ★ 先点"回收站界面书"那一桶：默认落在第一张卡（整本已删的书），那本书里
    #   只有两轮、没有可供级联的父子对。判据要测的是**有父子关系**的那一本。
    # [EN] Click the "回收站界面书" bucket first: the default is the first card (a whole-book
    # [EN] deletion) which has only two rounds and no parent/child pair to cascade.
    for c in _walk(view):
        bk = getattr(c, '_bucket', None)
        if bk is not None and bk[0] == 'live' and bk[1].startswith('回收站界面书'):
            c.on_click(None)
            break
    view = dlg.content.content
    rows = [c for c in _walk(view) if getattr(c, '_card', None) is not None
            and getattr(c._card, '_t_path', None) is not None]
    by_name = {c._card._t_path.name: c for c in rows}
    # ⚠ 用目录名里的 `第N次模拟` 认（回收站里目录名带时间戳前缀，`2026…_存档_第3次…`，
    #   但子串仍在）—— 不能用"名字开头是数字"之类的判断，那会认错。
    # [EN] Recognise by `第N次模拟` inside the folder name (bin names carry a timestamp prefix).
    parent = next((n for n in by_name if '第3次模拟' in n), None)
    child = next((n for n in by_name if '第4次模拟' in n), None)
    if parent is None or child is None:
        rec('级联勾选：找得到父子两行', False, f'只有 {sorted(by_name)[:3]}')
        return
    bp, bc = _check_box(by_name[parent]), _check_box(by_name[child])
    if bp is None or bc is None:
        rec('级联勾选：两行都有复选框', False, '')
        return
    bp.on_click(None)                       # 点父节点
    rec('勾父节点 ⇒ **子节点自动勾上**', _ticked(bc),
        f'父={_ticked(bp)} 子={_ticked(bc)}')
    rec('勾父节点 ⇒ **子节点变灰**（锁住的外观）', _greyed(bc), f'色={_icon(bc).color}')
    bc.on_click(None)                       # 想取消子节点（应当无效）
    rec('锁住的子节点**点不掉**（用户点名的行为）', _ticked(bc),
        f'点过之后 子={_ticked(bc)}')
    bp.on_click(None)                       # 放开父节点
    rec('取消父节点 ⇒ 子节点**跟着取消并解锁**',
        (not _ticked(bc)) and (not _greyed(bc)),
        f'子={_ticked(bc)} 灰={_greyed(bc)}')
    bc.on_click(None)                       # 现在可以单独勾了
    rec('解锁之后**子节点能单独勾**', _ticked(bc), f'子={_ticked(bc)}')
    bc.on_click(None)
    _ = page


def _bulk_mode(box) -> str:
    """「全选」框现在是哪一档：`all` / `some` / `none`（读不出来时返回 `?<图标>`）。"""
    icon = getattr(getattr(box, 'content', None), 'icon', None)
    if icon == ft.Icons.CHECK_BOX:
        return 'all'
    if icon == ft.Icons.INDETERMINATE_CHECK_BOX:
        return 'some'
    if icon == ft.Icons.CHECK_BOX_OUTLINE_BLANK:
        return 'none'
    return f'?{icon}'


def _trash_columns(view):
    """回收站那个顶层三栏 `Row` 的前两栏（① 书 / ② 存档）。"""
    for c in _walk(view):
        if not isinstance(c, ft.Row) or len(c.controls or []) < 2:
            continue
        if any('① 回收站里的书' in x for x in _texts(c.controls[0])):
            return c.controls[0], c.controls[1]
    return None, None


def _head_del_label(col) -> str:
    """这一栏栏头那颗「永久删除」上的字（`永久删除` / `永久删除（n）`）。"""
    for c in _walk(col):
        if not isinstance(c, ft.Container) or getattr(c, 'on_click', None) is None:
            continue
        if getattr(c, '_bulk_kind', None):          # 全选框本人，跳过
            continue
        for x in _walk(c):
            if isinstance(x, ft.Text) and (x.value or '').startswith('永久删除'):
                return x.value or ''
    return ''


def _trash_select_all_check(page, dlg) -> None:
    """回收站两栏的「全选」（2026-10-31 用户：「拾卷 回收站里 也需要有全选」）。

    ★ 为什么在回收站这一侧另测一遍、不复用拾卷那条判据：
      两边的**勾选集合是分开的**（`tsel` 与 `sel`），而且回收站的"能勾的东西"多一条
      排他规则 —— **撑树的虚线框没有复选框**（它没被删）。全选若绕过这条规则，
      栏头会写出一个用户根本勾不上的数（勾上了也删不了）。拾卷那边没有虚线框，
      测不出这一条。

    ★ 判五件事（都是"点一下、读回来"，静态检查一条也覆盖不到）：
      ① **两栏都有**，而且是**两个不同控件**（共用一份就会重演 2026-10-21 那次联动）；
      ② **算数**：全选之后栏头写的数字 == 这一栏真能勾的个数（书栏数书、存档栏数轮）；
      ③ **三档**：none / some / all 与实际勾选数对得上（图标恒空 = 用户以为没生效）；
      ④ **补满**：部分勾选时再点一下 = 补满，不是清空；
      ⑤ **清空 + 解锁**：全勾状态再点 = 清空这一栏，且被父节点锁灰的子节点要**解锁**
         （只 `force(False)` 不解锁 ⇒ 子节点永远点不亮，用户只能关掉对话框重开）。
    ★ 还有一条**不串列**：在书栏全选，存档栏的数字必须纹丝不动。

      English:
    "Select all" in both bin columns. ★ Why a separate check on the bin side: the tick sets are
    separate (`tsel` vs `sel`) and the bin has one extra exclusion -- **scaffolding rows have no
    checkbox** (they were never deleted). A select-all that ignored that rule would print a number
    the user could never reach. Pick-a-Volume has no dashed rows, so it cannot test this.
    ★ Five things, all "click and read back": ① both columns exist and are **distinct controls**;
    ② arithmetic (header count == what is really tickable); ③ the three states match reality;
    ④ top-up when partially ticked; ⑤ clear **and unlock**. Plus: ticking one column must not move
    the other column's number.
    """
    view = dlg.content.content
    bulks: dict = {}
    for c in _walk(view):
        k = getattr(c, '_bulk_kind', None)
        if k and getattr(c, '_bulk_place', None) == 'trash':
            bulks.setdefault(k, c)
    rec('回收站 ① 书栏有「全选」框', 'novels' in bulks, sorted(bulks))
    rec('回收站 ② 存档栏有「全选」框', 'runs' in bulks, sorted(bulks))
    if not ('novels' in bulks and 'runs' in bulks):
        return
    rec('两栏的「全选」框是**两个不同控件**',
        bulks['novels'] is not bulks['runs'], '')
    novel_col, save_col = _trash_columns(view)
    if novel_col is None:
        rec('回收站：找得到三栏那一排', False, '')
        return

    # ── ① 书栏：全选 ⇄ 全不选 ──
    book_cards = [c for c in _walk(novel_col)
                  if getattr(c, '_bucket', None) is not None
                  and c._bucket[0] == 'novel']
    book_cards = [c for c in book_cards if _check_box(c) is not None]
    runs_before = _head_del_label(save_col)
    rec('书栏里"整本被删"的书**有勾选框**（全选才勾得到）', bool(book_cards),
        f'{len(book_cards)} 本')
    if book_cards:
        bulks['novels'].on_click(None)
        rec(f'书栏点「全选」⇒ 栏头写「永久删除（{len(book_cards)}）」',
            _head_del_label(novel_col) == f'永久删除（{len(book_cards)}）',
            repr(_head_del_label(novel_col)))
        rec('书栏点「全选」⇒ 图标变「全选」档',
            _bulk_mode(bulks['novels']) == 'all', _bulk_mode(bulks['novels']))
        rec('书栏点「全选」⇒ 每本书的方框都勾上',
            all(_ticked(_check_box(c)) for c in book_cards),
            f'{sum(1 for c in book_cards if _ticked(_check_box(c)))}/{len(book_cards)}')
        rec('书栏全选**不影响存档栏**的数字（各算各的）',
            _head_del_label(save_col) == runs_before,
            f'{runs_before!r} → {_head_del_label(save_col)!r}')
        bulks['novels'].on_click(None)
        rec('书栏再点一下 ⇒ 回到「永久删除」',
            _head_del_label(novel_col) == '永久删除', repr(_head_del_label(novel_col)))
        rec('书栏再点一下 ⇒ 图标回「未选」档',
            _bulk_mode(bulks['novels']) == 'none', _bulk_mode(bulks['novels']))
        rec('书栏再点一下 ⇒ 每本书的方框都取消',
            not any(_ticked(_check_box(c)) for c in book_cards), '')

    # ── ② 存档栏：全选（只勾真删的，撑树的虚线框不算）──
    rows = [c for c in _walk(save_col)
            if getattr(c, '_card', None) is not None
            and getattr(c._card, '_t_path', None) is not None]
    solid = [c for c in rows if not getattr(c._card, '_placeholder', False)]
    rec('存档栏里有可勾的真删节点', len(solid) >= 2, f'{len(solid)} 个')
    if len(solid) < 2:
        return
    bulks['runs'].on_click(None)
    rec(f'存档栏点「全选」⇒ 栏头写「永久删除（{len(solid)}）」',
        _head_del_label(save_col) == f'永久删除（{len(solid)}）',
        repr(_head_del_label(save_col)))
    rec('存档栏点「全选」⇒ 图标变「全选」档',
        _bulk_mode(bulks['runs']) == 'all', _bulk_mode(bulks['runs']))
    rec('存档栏点「全选」⇒ 每个真删节点都勾上（撑树的虚线框本来就没框）',
        all(_ticked(_check_box(c)) for c in solid),
        f'{sum(1 for c in solid if _ticked(_check_box(c)))}/{len(solid)}')
    bulks['runs'].on_click(None)
    rec('存档栏再点一下 ⇒ 回到「永久删除」',
        _head_del_label(save_col) == '永久删除', repr(_head_del_label(save_col)))
    rec('存档栏再点一下 ⇒ 图标回「未选」档',
        _bulk_mode(bulks['runs']) == 'none', _bulk_mode(bulks['runs']))
    rec('存档栏再点一下 ⇒ 方框全取消',
        not any(_ticked(_check_box(c)) for c in solid), '')
    # ★ 解锁：清空之后不许留"看起来没勾、其实锁着"的方框（那样再也点不亮）
    rec('存档栏清空后**没有方框还锁着**（灰 = 点了也没用）',
        not any(_greyed(_check_box(c)) for c in solid),
        f'{sum(1 for c in solid if _greyed(_check_box(c)))} 个还是灰的')

    # ── ③ 三档 + 补满：手工勾一条"带子节点但不是整棵"的 ⇒ some ──
    by_name = {c._card._t_path.name: c for c in solid}
    mid = next((n for n in by_name if '第3次模拟' in n), None)
    if mid is None:
        rec('部分档：找得到一条"有子节点但不满整栏"的存档', False,
            sorted(by_name)[:3])
        return
    box_mid = _check_box(by_name[mid])
    box_mid.on_click(None)
    rec('单勾一条 ⇒ 全选框变「部分」档（不是空、也不是全选）',
        _bulk_mode(bulks['runs']) == 'some', _bulk_mode(bulks['runs']))
    rec('单勾一条 ⇒ 栏头数字跟着它自己那一栏走（不是全栏的数）',
        _head_del_label(save_col).startswith('永久删除（')
        and _head_del_label(save_col) != f'永久删除（{len(solid)}）',
        repr(_head_del_label(save_col)))
    bulks['runs'].on_click(None)                    # 部分状态再点 = **补满**
    rec('部分状态再点「全选」⇒ 补满（不是清空）',
        _bulk_mode(bulks['runs']) == 'all'
        and _head_del_label(save_col) == f'永久删除（{len(solid)}）',
        f"{_bulk_mode(bulks['runs'])} / {_head_del_label(save_col)!r}")
    rec('补满之后每一个方框都亮着',
        all(_ticked(_check_box(c)) for c in solid),
        f'{sum(1 for c in solid if _ticked(_check_box(c)))}/{len(solid)}')
    bulks['runs'].on_click(None)                    # 全勾状态再点 = 清空
    rec('全勾状态再点「全选」⇒ 清空这一栏',
        _bulk_mode(bulks['runs']) == 'none'
        and _head_del_label(save_col) == '永久删除'
        and not any(_ticked(_check_box(c)) for c in solid),
        f"{_bulk_mode(bulks['runs'])} / {_head_del_label(save_col)!r}")
    rec('清空后**也没有方框被锁着**',
        not any(_greyed(_check_box(c)) for c in solid), '')
    _ = page


def _check_box(row):
    """这一行里的勾选框容器（`mk_check` 的产物：`content` 是 checkbox 图标的容器）。"""
    for c in _walk(row):
        if not isinstance(c, ft.Container) or getattr(c, 'on_click', None) is None:
            continue
        inner = getattr(c, 'content', None)
        if isinstance(inner, ft.Icon) and getattr(inner, 'icon', None) in (
                ft.Icons.CHECK_BOX, ft.Icons.CHECK_BOX_OUTLINE_BLANK):
            return c
    return None


def _icon(box):
    return getattr(box, 'content', None)


def _ticked(box) -> bool:
    return getattr(_icon(box), 'icon', None) == ft.Icons.CHECK_BOX


def _greyed(box) -> bool:
    """灰 = 颜色被压成了半透明（`#AARRGGBB` 里 AA != FF）。

    ⚠ 不能用"颜色等于某个具体值"来判：明暗两套主题下 `C['muted']` 不一样。
      "被压暗"这个**关系**才是稳定的。
    """
    col = str(getattr(_icon(box), 'color', '') or '')
    return len(col) == 9 and col[1:3].upper() != 'FF'


def _row_with_tabs(content, tabs):
    """找出那个"第一个子控件装 Tab、第二个子控件装内容"的顶层 `Row`。"""
    keys = {getattr(c, '_tab_key', None) for c in tabs}
    for c in _walk(content):
        if not isinstance(c, ft.Row):
            continue
        kids = c.controls or []
        if len(kids) < 2:
            continue
        got = {getattr(x, '_tab_key', None) for x in _walk(kids[0])}
        if keys and keys <= got:
            return c, kids
    return None, None


def _has_dashed(node) -> bool:
    """这个节点卡外面有没有套**虚线框**。

    ★ 认定方式（按 `mk_dashed_frame` 的结构，不按"有没有边框"）：
      一个 `Stack`，里面有 **4 个定位边**（两条 `left+right`、两条 `top+bottom`），
      而每条边的子树里都有若干个 `width/height == 2` 的实心小方块。
      ⚠ 不能只找"第一个 Stack"：树节点本身就是一个 Stack（装树线），
        会先撞上它，然后里面一个 2px 方块都没有 ⇒ 恒定判"没有虚线"（第一版就是
        这么错的，2/2 全红）。
      ⚠ 也不能只数"有 bgcolor 的容器"：卡片自己有底色，那样永远为真。
    """
    for c in _walk(node):
        if not isinstance(c, ft.Stack):
            continue
        kids = [k for k in (getattr(c, 'controls', None) or [])
                if isinstance(k, ft.Container)]
        horiz = [k for k in kids if k.left is not None and k.right is not None]
        vert = [k for k in kids if k.top is not None and k.bottom is not None]
        if len(horiz) < 2 or len(vert) < 2:
            continue
        bits = 0
        for edge in horiz + vert:
            for dash in _walk(getattr(edge, 'content', None)):
                if (isinstance(dash, ft.Container) and dash.bgcolor
                        and dash.width == 2):
                    bits += 1
        if bits >= 8:
            return True
    return False


def _count_check(node) -> int:
    """这一行里有几个勾选框（`mk_check` 的特征：`content` 是 `ft.Icon`，
    图标名是 checkbox 那两档，且挂了 `on_click`）。

    ★★ 2026-10-31：**栏头的「全选」框不算节点框**（它长得一模一样：Container +
      on_click + 一颗 checkbox 图标 ⇒ 特征判法多算了 2 个，实测让「拾卷的小说卡、
      存档节点都带勾选框」变成 5 个"应为 1 本 + 2 轮"）。产品在它身上挂了
      `_bulk_kind`，按这个记号排掉 —— 判"一行里有没有节点框"不该把栏头的开关算进来。
      ⚠ 别改成"数 `_node_kind`"：回收站那两处节点框（18839 / 19048）没挂这个记号，
        改了就会让 placeholders/solid 那两条恒假。
    [EN] ★★ 2026-10-31: **the header "select all" box is not a node box.** It looks identical
    [EN] (Container + on_click + a checkbox icon), so the shape-based count picked up 2 extra and
    [EN] turned "novel cards and save nodes all have checkboxes" into 5 instead of 1 + 2. The
    [EN] product marks it with `_bulk_kind`; exclude by that. ⚠ Do not switch to counting
    [EN] `_node_kind`: the two bin node boxes do not carry it, and those assertions would go
    [EN] permanently false.
    """
    n = 0
    for c in _walk(node):
        if not isinstance(c, ft.Container) or getattr(c, 'on_click', None) is None:
            continue
        if getattr(c, '_bulk_kind', None):          # 栏头「全选」，不是节点框
            continue
        inner = getattr(c, 'content', None)
        if isinstance(inner, ft.Icon) and getattr(inner, 'icon', None) in (
                ft.Icons.CHECK_BOX, ft.Icons.CHECK_BOX_OUTLINE_BLANK):
            n += 1
    return n


def _finish():
    ok_all = all(r['ok'] for r in results)
    print(f"\n=== {sum(1 for r in results if r['ok'])}/{len(results)} 通过 ===",
          flush=True)
    (OUT / 'recycle_bin_report.json').write_text(
        json.dumps({'ok': ok_all, 'checks': results}, ensure_ascii=False,
                   indent=2), encoding='utf-8')
    import os
    os._exit(0 if ok_all else 2)


async def main(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        print('—— 数据层 ——', flush=True)
        data_layer(tmp / 'DataProjects')
        print('—— 界面层（真机）——', flush=True)
        await ui_layer(page, tmp)
    except Exception as e:                                       # noqa: BLE001
        import traceback
        traceback.print_exc()
        rec('跑完（没有崩）', False, repr(e)[:120])
    finally:
        _finish()


ft.run(main)
