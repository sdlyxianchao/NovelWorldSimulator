# -*- coding: utf-8 -*-
"""验证：**删一本小说要连它名下的存档一起**（2026-10-27 用户点名）。

用户原话：
  「拾卷还有一个问题 我删除小说项目的时候 无论是回收站还是默认Tab 都应该同时把
   对应存档一起删除 而不是我删除了小说项目 存档还在 还需要手工删除
   前者是包含后者的」

★ 这条判据量的是**磁盘事实**，不是界面文案：
  删完书以后，回收站**顶层**还剩几条、那些存档到底在哪儿、恢复书时它们回不回得来。
  （界面上"说了会一起删"而盘上没动，是最容易自欺的一种绿。）

★ 为什么"归位"而不是"一起抹掉"：见 `store/trash.absorb_runs_into` 的说明。
  这里守的是它带来的四个后果 —— 少一条都会退化成用户抱怨的那样。

判据用的是**临时目录**里真造出来的书与存档（绝不碰用户的项目目录）。

English:
Verification: **deleting a book must take its saves with it** (user asked for this, 2026-10-27).

User's words: "one more problem in Pick-a-Volume: when I delete a novel project, on both the
recycle-bin tab and the default tab it should delete the corresponding saves at the same time --
right now the book is gone but the saves are still there and I have to delete them by hand; the
former contains the latter."

★ This measures **disk facts**, not UI copy: after deleting the book, how many entries remain at
the **top level** of the bin, where those saves actually are, and whether they come back when the
book is restored. ("The UI says it deletes them" while the disk is untouched is the easiest kind
of fake green.)
★ Why "absorb" and not "wipe together": see `store/trash.absorb_runs_into`. What is guarded here
is the four consequences -- miss one and it degrades back into what the user complained about.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from store import trash as TR                     # noqa: E402
from store.project import (Project, list_run_dirs,  # noqa: E402
                           trash_dir_for)

#: 一句话一行（与别的判据同一套观感）
# [EN] One line per check (same look as the other verifiers).
REPORT: list[dict] = []


def rec(name: str, ok_: bool, detail: str = '') -> bool:
    REPORT.append({'name': name, 'ok': bool(ok_), 'detail': detail})
    print(f"  {'✓' if ok_ else '✗'} {name}"
          + (f'  | {detail}' if detail else ''), flush=True)
    return bool(ok_)


# ══════════════════════════════════════════════════════════════════
#  夹具：真造一本书 + 两轮存档（**临时目录**，绝不碰用户的书）
# [EN] Fixture: build a real book with two runs (in a temp dir, never the user's).
# ══════════════════════════════════════════════════════════════════
def make_book(root: Path, name: str, runs: int = 2) -> Project:
    proj = Project.create_new(root, name)
    for i in range(1, runs + 1):
        d = proj.root / f'第{i}次模拟'
        d.mkdir(parents=True, exist_ok=True)
        (d / '任务介绍.md').write_text(
            f'- **项目**：{name}\n', encoding='utf-8')
    return proj


def top_names(root: Path) -> list[str]:
    """回收站**顶层**条目的名字（`scan_trash` 的口径）。"""
    return sorted(e.name for e in TR.scan_trash(root))


# ══════════════════════════════════════════════════════════════════
#  A 组：删整本书（"移到回收站"）—— 存档归到书里
# [EN] Group A: delete a whole book ("move to bin") -- saves are absorbed
# ══════════════════════════════════════════════════════════════════
def group_a(root: Path) -> None:
    print('\n【A】删整本书：属于它的存档**归到这本书下面**（用户报的那件事）',
          flush=True)
    p1 = make_book(root, '书一')
    p2 = make_book(root, '书二')          # 另一本，用来确认"级联不等于清空"

    # ① 先单独删掉第 1 次模拟（它成为回收站里的**顶层**条目）
    ok1, _ = TR.move_run_to_trash(p1.root / '第1次模拟', p1.root, root)
    # ★ 另一本书**也**删掉一轮 ⇒ 回收站里躺着一条**属于别人**的存档。
    #   ⚠ 少了这一步，"归位不管归属"那一刀根本打不红（回收站里没有别人的东西可吞）
    #   ⇒ A6 会是恒绿的假判据。反例法第 ③ 刀就是这么抓到它的。
    # [EN] ★ The other book also deletes one run => the bin holds a save **belonging to someone
    # [EN] else**. ⚠ Without it, "absorb regardless of owner" cannot turn anything red (nothing of
    # [EN] anyone else's to swallow) => A6 would be a permanently green fake. Knife ③ caught this.
    ok1b, _ = TR.move_run_to_trash(p2.root / '第1次模拟', p2.root, root)
    rec('A1 前提：两本书各删了一轮 ⇒ 回收站里两条存档（同名，靠**归属**分辨）',
        ok1 and ok1b and top_names(root).count('第1次模拟') == 2,
        str(top_names(root)))

    # ② 再删整本书
    ok2, dest = TR.move_project_to_trash(p1.root, root)
    rec('A2 前提：整本书搬进了回收站', ok2 and Path(dest).is_dir(), dest)

    # ⚠ 两条存档**同名**，只能按归属判 —— 按名字判会把别人的那条也算进来。
    # [EN] ⚠ Both runs share a name, so judge by **ownership**: by name you would count the
    # [EN] other book's.
    mine = [e.name for e in TR.scan_trash(root)
            if (not e.is_novel) and e.project == '书一']
    rec('A3 ★★★ 删完书，回收站**顶层不再有属于它的存档**'
        '（用户："存档还在 还需要手工删除"）',
        not mine, str(mine))

    book = next((e for e in TR.scan_trash(root)
                 if e.is_novel and e.name == '书一'), None)
    inside = sorted(d.name for d in book.path.iterdir() if d.is_dir()) \
        if book else []
    rec('A4 ★★★ 那轮存档**在书的目录里面**（前者包含后者）',
        '第1次模拟' in inside, str(inside))

    # ⚠ 名字必须是**原名**：留着时间戳前缀的话，恢复回去的书里会多一个
    #   `list_run_dirs` 认不出的目录 ⇒ 那一轮等于没了。
    rec('A5 ★★★ 归位后用的是**原名**（`第N次模拟`，不是带时间戳的那串）'
        '—— 否则恢复回去的书里那一轮认不出来',
        bool(list_run_dirs(book.path)) and
        sorted(d.name for d in list_run_dirs(book.path)) == ['第1次模拟', '第2次模拟'],
        str([d.name for d in list_run_dirs(book.path)]))

    others = [e.name for e in TR.scan_trash(root)
              if (not e.is_novel) and e.project == '书二']
    rec('A6 ★★★ 级联**只动这本书的**：回收站里**另一本书**的存档还在'
        '（没被吞进这本书里 —— "级联"不等于"顺手清空回收站"）',
        others == ['第1次模拟'] and (p2.root / '第2次模拟').is_dir(),
        f'回收站里书二的={others} · 书里第2次还在={(p2.root / "第2次模拟").is_dir()}')


# ══════════════════════════════════════════════════════════════════
#  B 组：恢复这本书 —— 存档跟着一起回来（归位前它们是**死条目**）
# [EN] Group B: restore the book -- saves come back (before this they were dead entries)
# ══════════════════════════════════════════════════════════════════
def group_b(root: Path) -> None:
    print('\n【B】恢复这本书：里面那几轮**一起回来**', flush=True)
    p1 = make_book(root, '书三')
    TR.move_run_to_trash(p1.root / '第1次模拟', p1.root, root)
    TR.move_project_to_trash(p1.root, root)

    book = next((e for e in TR.scan_trash(root)
                 if e.is_novel and e.name == '书三'), None)
    ok, msg = TR.restore(book, root)
    rec('B1 前提：书恢复回了项目目录', ok and Path(msg).is_dir(), msg)

    back = Project(Path(msg), '书三') if ok else None
    runs = [d.name for d in back.list_runs()] if back else []
    rec('B2 ★★★ 之前"再也恢复不回去"的那轮**跟着书一起回来了**'
        '（归位之前 `restore()` 会拿"原书不在"拒绝它）',
        runs == ['第1次模拟', '第2次模拟'], str(runs))

    rec('B3 ★★ 回收站里不再有任何属于这本书的东西',
        not [e for e in TR.scan_trash(root)
             if not e.is_novel and e.name == '书三'],
        str(top_names(root)))


# ══════════════════════════════════════════════════════════════════
#  C 组：永久删书 —— 连它那些平级存档一起删
# [EN] Group C: purge a book -- its peer saves go with it
# ══════════════════════════════════════════════════════════════════
def group_c(root: Path) -> None:
    print('\n【C】回收站里**永久删除**一本小说：它的存档一起没', flush=True)
    p1 = make_book(root, '书四')
    p2 = make_book(root, '书五')
    # 书五：删掉一轮 ⇒ 回收站里躺着**属于它**的平级条目（后面要确认它没被动）
    TR.move_run_to_trash(p2.root / '第1次模拟', p2.root, root)
    TR.move_project_to_trash(p1.root, root)

    # ★ 造一条**历史遗留**：书已经在回收站里了，而属于它的存档还**平级躺着**
    #   （这正是这次改版之前留下来的那种：书一删，它谁也恢复不回去）。
    #   删书那一步会顺手归位新产生的那种，所以这里必须手工造 —— 否则 C2 恒绿。
    # [EN] ★ Build a **legacy shape**: the book is already in the bin while a save belonging to it
    # [EN] still sits **beside** it (exactly what pre-change runs left behind: once the book is
    # [EN] gone nobody can restore it). Deleting the book absorbs newly created ones, so this must
    # [EN] be built by hand -- otherwise C2 is permanently green.
    trash = trash_dir_for(root)
    legacy = trash / '20261020-101010_存档_第3次模拟'
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / '任务介绍.md').write_text('- **项目**：书四\n', encoding='utf-8')
    TR.sidecar_path(legacy).write_text(
        '{"kind": "存档", "name": "第3次模拟", "original": "第3次模拟", '
        '"project": "书四", "deleted_at": "2026-10-20 10:10:10"}',
        encoding='utf-8')
    n_before = len(TR.orphan_runs_of('书四', root))
    rec('C1 前提：回收站里躺着一条**属于这本书**的平级存档（历史遗留）',
        n_before == 1, str([e.name for e in TR.orphan_runs_of('书四', root)]))

    book = next((e for e in TR.scan_trash(root)
                 if e.is_novel and e.name == '书四'), None)
    ok, _msg = TR.purge(book, root)
    rec('C1b 前提：书被永久删除了', ok and not book.path.exists(), str(ok))

    left = [e.name for e in TR.scan_trash(root) if e.project == '书四']
    rec('C2 ★★★ 永久删书 ⇒ 回收站里**属于它的**存档也一起没了'
        '（书都没了，那些存档谁也恢复不回去）',
        not left, str(left))

    # ⚠ 关键的反面：别的书的存档必须还在（否则就是"顺手清空回收站"）
    others = [e.name for e in TR.scan_trash(root) if e.project == '书五']
    rec('C3 ★★★ 别的一本书的存档**一条都没动**',
        others == ['第1次模拟'], str(others))


# ══════════════════════════════════════════════════════════════════
#  D 组：搬不动的时候**不许先动存档**
# [EN] Group D: when the move fails, the saves must be left alone
# ══════════════════════════════════════════════════════════════════
def group_d(root: Path) -> None:
    print('\n【D】归位**撞名**时：不许拿旧的换掉新的', flush=True)
    # ⚠ 这一组原来想守"搬不动时不动存档"。那一刀**打不红** —— 搬不动时代码直接
    #   `return`，而 `absorb_runs_into` 自己还有一道 `is_dir` 守卫 ⇒ 两道闸，
    #   无论怎么改都动不了存档 ⇒ 那条判据恒绿，等于没判。
    #   ⇒ 换成"撞名不许覆盖"：它只由**一处**保证，而且覆盖了就是真丢数据
    #   （删掉第 1 次 → 又跑到第 1 次 → 再删整本 ⇒ 旧的回来时名字正好撞上）。
    # [EN] ⚠ This group used to guard "leave saves alone when the move fails". That knife **cannot
    # [EN] turn it red** -- the code returns early on failure *and* `absorb_runs_into` has its own
    # [EN] `is_dir` guard => two gates, so no mutation can touch the saves => the criterion is
    # [EN] permanently green, i.e. it judges nothing. => Replaced with "no overwrite on name
    # [EN] collision": guaranteed by **one place** only, and overwriting really loses data.
    p1 = make_book(root, '书六')
    TR.move_run_to_trash(p1.root / '第1次模拟', p1.root, root)
    # 又跑了一轮新的第 1 次（同名）
    again = p1.root / '第1次模拟'
    again.mkdir(parents=True, exist_ok=True)
    (again / '新的一轮.txt').write_text('new', encoding='utf-8')
    TR.move_project_to_trash(p1.root, root)

    book = next((e for e in TR.scan_trash(root)
                 if e.is_novel and e.name == '书六'), None)
    inside = sorted(d.name for d in book.path.iterdir() if d.is_dir())
    kept = (book.path / '第1次模拟' / '新的一轮.txt').is_file()
    rec('D1 ★★★ 撞名时**加序号、不覆盖**：新跑的那一轮一个字都没被换掉'
        '（覆盖 = 拿回收站里的旧轮换掉现在的）',
        '第1次模拟_2' in inside and kept, f'{inside} 新轮还在={kept}')


def main() -> int:
    # ⚠ 项目根必须是**临时目录下的一层**（`…/项目`）：回收站是**项目根的同级**
    #   （`trash_dir_for` = `root.parent/已删除备份`）。直接拿 mkdtemp 当项目根的话，
    #   回收站就变成整个 Temp 目录里的公共 `已删除备份/` —— 判据会扫到**别的测试
    #   甚至真实项目**留下的几百条（实测第一版就是这样，A1 打印了一大串别人的存档）。
    #   ★ "判据造的数据绝不能落到共享目录里"，这条在回收站上尤其容易犯。
    # [EN] ⚠ The project root must be **a level inside** the temp dir (`…/项目`): the bin is a
    # [EN] **sibling of the project root** (`trash_dir_for` = `root.parent/deleted`). Using mkdtemp
    # [EN] itself as the root makes the bin the shared `Temp/deleted` -- the check then scans
    # [EN] hundreds of entries left by other tests (the first version did exactly that).
    base = Path(tempfile.mkdtemp(prefix='nws_cascade_'))
    tmp = base / '项目'
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        group_a(tmp)
        group_b(tmp)
        group_c(tmp)
        group_d(tmp)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    bad = [c for c in REPORT if not c['ok']]
    print('\n' + '─' * 62)
    print(f'  删除级联验证：{len(REPORT) - len(bad)}/{len(REPORT)}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
