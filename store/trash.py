# -*- coding: utf-8 -*-
"""**回收站**：拾卷旁边的第二个 Tab 靠它说话（2026-10-21 用户点名加的）。

用户原话：
  「拾卷里加一个总体的 Tab，放到最左边。现在的所有内容改成名字叫做拾卷的 tab，
   然后新加的叫做回收站，放到拾卷 tab 的下面。回收站的 tab 内容跟拾卷的内容相同……
   回收站里删除小说则需要输入小说名字 且提示会被彻底删除……回收站里的存档树状图也是
   树状，不过肯定跟拾卷的有不同的地方。为了维持树的形态，会有一些作为父节点的节点也
   显示在这里，但实际上没有被删除，对于这样的节点，请用一些办法标记出来……」

★★★ 为什么要有这个模块，而不是在界面里直接 `os.scandir('已删除备份')`：

  `store/project._move_to_trash` 把东西搬进 `已删除备份/` 时，**只保留了原名字**
  （`20261015-003559_存档_第2次模拟2026-10-14-23-22`）。于是"这个存档原本属于哪本书"
  这条信息**在搬的那一刻就丢了** —— 而回收站要按书分组、要能恢复回去，
  全都需要它。

  所以新增一个**旁注文件**（与条目同名的 `.json`，就放在 `已删除备份/` 里）：
  `20261015-003559_存档_第2次模拟2026-10-14-23-22.json`
      {'kind': '存档', 'name': '第2次模拟2026-10-14-23-22',
       'project': '望江楼模拟项目', 'parent': '第1次模拟2026-10-13-22-10',
       'deleted_at': '2026-10-15 00:35:59'}
  ⚠ **旁注不放进被搬走的那条目录里**：目录是用户的东西，我们搬它是因为他点了删除，
    不是因为我们想改它。恢复的时候也不用清理（没有东西需要清理）。

★★★ 旧备份没有旁注（这是这次改版之前删的）：**不许当成"来源不明"了事**。
  实测那些目录里有 `任务介绍.md`，头几行就写着 `- **项目**：望江楼模拟项目` ——
  那就是**当时的记录**，不是我们猜的。所以按三级证据取项目名：
  ① 旁注（这一版之后删的）→ ② `任务介绍.md` 里那行「项目」（旧备份）→ ③ 没有。
  第三级才落到"来源不明"，而且界面上会**标出来**（与拾卷里"推断"的父子关系同一套规矩）。

★★★ 为什么"删除一个节点要连它的子节点一起"：
  存档是一棵树（从某一轮起笔，那一轮就是它的父）。只搬走父节点、把子节点留在原处，
  它们会变成**没有父的孤儿**（`build_tree` 会把它们当根）—— 用户看到的是
  "树忽然散成了一堆平级条目"，而他以为只是删了一条。所以删除必须**整棵子树**一起，
  并且提示里要写清查的是几条（见界面里的 `_ask_delete_saves`）。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from store import lineage as LINEAGE
from store.project import (Project, atomic_move, trash_dir_for)

_LOG = logging.getLogger(__name__)

#: 旁注后缀（与条目目录同名，并排放）。⚠ 拿它当"这一条是这一版之后删的"的凭据。
# [EN] Sidecar suffix (same name as the entry folder, side by side). ⚠ It doubles as proof that "this
# [EN] one was deleted after this version".
SIDECAR_SUFFIX = '.json'

#: 识别条目目录名：`20261015-003559_存档_第2次模拟2026-10-14-23-22`
# [EN] Recognize an entry folder name.
_ENTRY_RE = re.compile(r'^(\d{8}-\d{6})_(小说|存档)_(.+?)(?:_(\d+))?$')

#: `任务介绍.md` 里那一行：`- **项目**：望江楼模拟项目`
# [EN] The line in `任务介绍.md`.
_PROJ_RE = re.compile(r'\*\*项目\*\*\s*[：:]\s*(.+)')

KIND_NOVEL = '小说'
KIND_RUN = '存档'


@dataclass
class TrashEntry:
    """回收站里的**一条**（一本书，或一轮存档）。"""

    path: Path                       #: 回收站里的那个目录
    kind: str                        #: `'小说'` / `'存档'`
    name: str                        #: 原来的名字（书名 / 存档名）
    deleted_at: str = ''             #: 删除时间，`YYYY-MM-DD HH:MM:SS`
    project: str = ''                #: 这条存档原本属于哪本书（小说的就是它自己）
    parent: str = ''                 #: 血统上的父存档名（小说没有）
    #: 项目名是从哪儿来的：`sidecar` / `任务介绍` / `''`（不知道）。
    #: ⚠ 界面要把它标出来 —— 旧备份只能靠 `任务介绍.md` 推，那有可能是错的。
    project_from: str = ''
    meta_ok: bool = False            #: 有旁注（这一版之后删的）
    extra: dict = field(default_factory=dict)

    @property
    def is_novel(self) -> bool:
        return self.kind == KIND_NOVEL

    @property
    def run_index(self) -> int:
        return LINEAGE.run_index(self.name)


# ══════════════════════════════════════════════════════════════════
#  读
# ══════════════════════════════════════════════════════════════════
def sidecar_path(entry_dir: Path) -> Path:
    """条目对应的旁注文件路径（可能与条目同名 + `.json`）。
    [EN] The sidecar path for an entry folder (same name + `.json`).
    """
    return entry_dir.parent / (entry_dir.name + SIDECAR_SUFFIX)


def parse_name(dirname: str) -> tuple[str, str, str]:
    """`20261015-003559_存档_第2次模拟…` → `(stamp, kind, name)`。认不出返回 `('', '', dirname)`。

    ⚠ 认不出**不丢**：仍然原样当一个"存档"条目显示出来（宁可多一条认不出的，
      也不能让回收站里的东西凭空少掉 —— 那是这个功能最不能犯的错）。
    [EN] Unrecognized is **never dropped**: it still shows up as a save entry. Better a
    [EN] mislabelled entry than one that vanishes -- the one thing a recycle bin must never do.
    """
    m = _ENTRY_RE.match(dirname or '')
    if not m:
        return '', KIND_RUN, dirname
    stamp, kind, name = m.group(1), m.group(2), m.group(3)
    try:
        when = (f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} '
                f'{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}')
    except Exception:                                            # noqa: BLE001
        when = ''
    return when, kind, name


def project_of_run(run_dir) -> tuple[str, str]:
    """这一轮存档原本属于哪本书 → `(项目名, 证据来源)`。

    三级证据（理由见模块说明）：
      ① 旁注 → `'sidecar'`
      ② `任务介绍.md` 里那行「项目」→ `'任务介绍'`
      ③ 都不知道 → `('', '')`

        English:
    Which book this run belonged to → `(project name, evidence source)`.
    Three levels of evidence (see the module docstring): ① sidecar; ② the `项目` line inside
    `任务介绍.md`; ③ unknown.
    """
    try:
        d = Path(run_dir)
        sc = sidecar_path(d)
        if sc.is_file():
            data = json.loads(sc.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                proj = str(data.get('project') or '').strip()
                if proj:
                    return proj, 'sidecar'
        intro = d / '任务介绍.md'
        if intro.is_file():
            head = intro.read_text(encoding='utf-8', errors='ignore')[:1200]
            m = _PROJ_RE.search(head)
            if m:
                proj = str(m.group(1)).strip()
                # 去掉常见的尾巴（"望江楼模拟项目"就是书名本身；这里只去标点）
                proj = proj.strip('。 .、,，')
                if proj:
                    return proj, '任务介绍'
    except Exception:                                            # noqa: BLE001
        pass
    return '', ''


def _read_sidecar(d: Path) -> dict:
    try:
        sc = sidecar_path(d)
        if not sc.is_file():
            return {}
        data = json.loads(sc.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:                                            # noqa: BLE001
        return {}


def scan_trash(projects_root) -> list[TrashEntry]:
    """扫一遍回收站 → 条目列表（**只列目录**，旁注文件不算条目）。

    ★ 排序：删得晚的在前面（与拾卷"最新的在最上面"同一观感）。
    ★ 认不出的条目也列出来（见 `parse_name`）。

        English:
    Scan the recycle bin -> entries (**directories only**; sidecars are not entries).
    ★ Sorted newest-deletion-first. ★ Unrecognized entries are listed too.
    """
    trash = trash_dir_for(Path(projects_root))
    out: list[TrashEntry] = []
    if not trash.is_dir():
        return out
    try:
        dirs = [d for d in trash.iterdir() if d.is_dir()]
    except OSError:
        return out
    for d in dirs:
        when, kind, name = parse_name(d.name)
        meta = _read_sidecar(d)
        entry = TrashEntry(path=d, kind=kind, name=name, deleted_at=when,
                           meta_ok=bool(meta))
        if kind == KIND_NOVEL:
            entry.project = name
            entry.project_from = 'sidecar' if meta else ''
        else:
            proj, src = project_of_run(d)
            entry.project = str(meta.get('project') or proj or '').strip()
            entry.parent = str(meta.get('parent') or '').strip()
            entry.project_from = 'sidecar' if meta.get('project') else src
            if not entry.parent:
                entry.parent = str(LINEAGE.read_lineage(d).get('parent') or '')
        entry.extra = meta
        out.append(entry)
    out.sort(key=lambda e: (e.deleted_at or '', e.name), reverse=True)
    return out


def runs_inside(project_dir, project_name: str = '') -> list[Path]:
    """一个（也许已经在回收站里的）项目目录里的全部存档目录。

    ⚠ 直接用 `Project(...)` 而不是 `Project.from_nwsproj`：回收站里的整本小说
      仍然带着 `.nwsproj`，但**万一带丢了**，`from_nwsproj` 会抛 —— 那时我们
      仍然应该看得见里面的存档（看不见就等于数据丢了）。`list_runs()` 只按名字认，
      不需要 `.nwsproj`。

        English:
    All run folders inside a (possibly trashed) project directory.
    ⚠ Uses `Project(...)` directly instead of `from_nwsproj`: a trashed book still carries its
      `.nwsproj`, but if that file is missing `from_nwsproj` raises -- and we must still see the runs
      inside (not seeing them equals losing them). `list_runs()` only looks at names.
    """
    try:
        return Project(Path(project_dir), project_name or Path(project_dir).name).list_runs()
    except OSError:
        return []


def orphan_runs_of(project_name: str, projects_root) -> list[TrashEntry]:
    """回收站里**属于这本书、却和它平级躺着**的存档条目。

    ★★★ 为什么会有这种东西（用户 2026-10-27 报的：「删除小说项目的时候……
      存档还在 还需要手工删除 前者是包含后者的」）：

      先单独删掉一轮存档（它进回收站，是**顶层**条目），再删掉整本书（书目录
      整个进回收站，也是顶层条目）⇒ 回收站里于是躺着**两条平级**的东西：
      一条「小说_A」、一条「存档_第1次模拟（属于 A）」。
      用户删完书还得再手工删那条存档 —— 而"书包含存档"是他脑子里当然的结构。

      ★ 更要紧的是：那种存档是**死条目**。书不在项目目录里了，`restore()` 就会
        拒绝（"原书已经不在项目目录里"）⇒ 它**永远回不去**，只能手工永久删除。
        回收站最不能犯的错就是"东西在里面却再也回不来"。

    ★ 只认**顶层**（`scan_trash` 的口径）：已经归到某本书目录里的存档不算
      （那正是我们想要的样子 —— 它们被书**包含**着，不再单独列出）。

        English:
    Save entries in the bin that **belong to this book but sit beside it as peers**.

    ★★★ Why they exist (user, 2026-10-27: "when I delete a novel project ... the saves are still
      there and I have to delete them by hand -- the former contains the latter"):
      delete one run first (it lands in the bin as a **top-level** entry), then delete the whole
      book (its folder lands there too, also top-level) => the bin now holds **two peers**:
      "novel_A" and "save_第1次模拟 (of A)". The user must delete the save by hand, while
      "a book contains its saves" is the structure they take for granted.
      ★ Worse: such a save is a **dead entry**. With the book gone from the projects dir,
      `restore()` refuses it => it can **never come back**, only be purged by hand. A recycle bin
      must never hold something that cannot be restored.
    ★ Only **top-level** counts (same reading as `scan_trash`): saves already absorbed into a
      book's folder are excluded -- being contained is exactly the shape we want.
    """
    want = str(project_name or '').strip()
    if not want:
        return []
    return [e for e in scan_trash(projects_root)
            if (not e.is_novel) and str(e.project or '').strip() == want]


# ══════════════════════════════════════════════════════════════════
#  写
# ══════════════════════════════════════════════════════════════════
def _write_sidecar(entry_dir: Path, data: dict) -> bool:
    """写旁注。**不抛**（写不进去最坏只是这条恢复时找不到原书）。"""
    try:
        sc = sidecar_path(entry_dir)
        sc.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                      encoding='utf-8')
        return True
    except Exception:                                            # noqa: BLE001
        return False


def _drop_sidecar(entry_dir: Path) -> None:
    try:
        sidecar_path(entry_dir).unlink(missing_ok=True)
    except Exception:                                            # noqa: BLE001
        pass


def move_run_to_trash(run_dir, project_root, projects_root,
                      parent: str = '') -> tuple[bool, str]:
    """把一轮存档搬进回收站，并**补上"它原本属于哪本书"**。

    为什么不直接调 `archive_run_dir`：那个函数只搬目录，搬完就不知道是哪本书的了
    （模块说明里的那段）。这里搬完就写旁注，两件事**必须在同一个动作里**完成 ——
    中间断一刀（搬了但没写）就是一条永远恢复不回去的存档。

        English:
    Move one run into the recycle bin **and record which book it belonged to**.
    Not calling `archive_run_dir` directly because that only moves the folder and then nobody knows
    which book it was. Here the move and the record happen in **one action**: breaking between them
    leaves a save that can never be restored.
    """
    from store.project import archive_run_dir
    ok, msg = archive_run_dir(Path(run_dir), Path(project_root), projects_root)
    if not ok:
        return False, msg
    dest = Path(msg)
    proj = Path(project_root).name
    # 父存档名优先取调用方给的（界面从树上拿，最准）；没给就读这一轮自己的记录。
    # [EN] Prefer the caller's parent (from the tree, most accurate); otherwise read this run's own record.
    par = str(parent or '').strip() or str(
        LINEAGE.read_lineage(dest).get('parent') or '')
    _write_sidecar(dest, {'kind': KIND_RUN, 'name': dest.name,
                          'original': Path(run_dir).name,
                          'project': proj, 'parent': par,
                          'deleted_at': _now()})
    return True, str(dest)


def absorb_runs_into(book_dir, project_name: str, projects_root) -> list[str]:
    """把回收站里**属于这本书的平级存档**搬进这本书的目录 → 被搬进去的名字。

    ★★★ 为什么是"搬进书里"而不是"跟着一起删掉"（用户 2026-10-27：
      「删除小说项目的时候……应该同时把对应存档一起删除 …… 前者是包含后者的」）：

      他要的是"**前者包含后者**"。把它翻译成磁盘事实，就是**存档回到书的目录里**
      —— 而不是连书带存档一起抹掉（那不是删除，是销毁；回收站不干这事）。
      归位之后，四个动作全都自然对了：
        · 回收站列表**不再单独列出**那些存档（用户不用手工再删一次）；
        · 永久删除这本书 ⇒ 目录整体删 ⇒ 存档一起走；
        · **恢复这本书 ⇒ 存档跟着一起回来**（死条目就此复活 —— 归位之前它们
          因为"原书不在"而永远恢复不了）；
        · 归档/搬走整本书时也不会再散成两条平级的条目。

    ⚠ 名字要**改回原名**（`20261015-003559_存档_第2次模拟` → `第2次模拟`）：
      书里的存档是按 `第N次模拟` 认的（`project.list_run_dirs`）。留着时间戳前缀
      的话，恢复回去的书里会多出一个**认不出的目录** ⇒ 那一轮等于没了。

    ⚠ 撞名就加序号，**不覆盖**：书里可能真有一轮同名（比如删掉第 2 次之后又跑到
      第 2 次）。覆盖就是拿旧的换掉新的。

    ⚠ 归位之后旁注就**没了意义**（它记录的正是"这条单独躺在回收站里"这件事），
      要删掉 —— 留着会让扫描器以为顶层还有一条。

        English:
    Move the bin's **peer saves that belong to this book** into the book's folder -> moved names.

    ★★★ Why "absorb into the book" rather than "delete them along with it" (user 2026-10-27:
      "when deleting a novel ... the saves should go too ... the former contains the latter"):
      what they want is "**the former contains the latter**". Translated into a disk fact that
      means **the saves go back inside the book's folder** -- not wiping book and saves together
      (that is destruction, not deletion; a recycle bin does not do that). After absorbing, four
      things fall out for free: the bin **no longer lists** those saves separately (no manual
      second delete); purging the book deletes the folder whole, saves included; **restoring the
      book brings the saves back** (dead entries revive -- before this they could never be
      restored because "the book is gone"); and archiving a book never scatters it into peers.
    ⚠ Names are restored to their **original** form (`20261015-003559_存档_第2次模拟` ->
      `第2次模拟`): runs inside a book are recognised by `第N次模拟`. Keeping the timestamped
      prefix would leave an **unrecognised folder** in the restored book, i.e. that run is gone.
    ⚠ Name collisions get a sequence suffix, **never an overwrite**: a new 2nd run may exist.
    ⚠ The sidecar is dropped afterwards (it recorded exactly the fact that is no longer true).
    """
    book_dir = Path(book_dir)
    moved: list[str] = []
    if not book_dir.is_dir():
        return moved
    for e in orphan_runs_of(project_name, projects_root):
        if e.path.resolve() == book_dir.resolve():
            continue
        orig = str((e.extra or {}).get('original') or '').strip() or e.name
        orig = orig.strip() or e.name
        dest = book_dir / orig
        n = 1
        while dest.exists():                      # 撞名 ⇒ 加序号，**不覆盖**
            n += 1
            dest = book_dir / f'{orig}_{n}'
        ok, _msg = atomic_move(e.path, dest)
        if ok:
            _drop_sidecar(e.path)
            moved.append(dest.name)
    return moved


def move_project_to_trash(project_root, projects_root) -> tuple[bool, str]:
    """把整本小说搬进回收站（并在旁注里记下书名，方便回收站列表不必再猜）。

    ★★★ 2026-10-27：**顺手把它那些"已经躺在回收站里"的存档一起归到这本书下面**
      （`absorb_runs_into`）。理由与细节都在那里的文档串里 —— 一句话：
      **删书 = 连它名下的存档一起，前者包含后者**，而且这样那些存档才恢复得回来。
    """
    from store.project import archive_project_dir
    book = Path(project_root).name
    ok, msg = archive_project_dir(Path(project_root), projects_root)
    if not ok:
        return False, msg
    dest = Path(msg)
    absorbed = absorb_runs_into(dest, book, projects_root)
    _write_sidecar(dest, {'kind': KIND_NOVEL, 'name': dest.name,
                          'original': book,
                          'project': book,
                          'absorbed': absorbed,
                          'deleted_at': _now()})
    return True, str(dest)


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ══════════════════════════════════════════════════════════════════
#  恢复 / 永久删除
# ══════════════════════════════════════════════════════════════════
def _inside_trash(path: Path, projects_root) -> bool:
    """护栏：只许动回收站里的东西（`..`、绝对路径、软链都要挡住）。"""
    try:
        p = Path(path).resolve()
        t = trash_dir_for(Path(projects_root)).resolve()
        return p != t and t in p.parents
    except OSError:
        return False


def restore(entry: TrashEntry, projects_root) -> tuple[bool, str]:
    """把这一条**搬回去** → `(成功, 落点或原因)`。

    ★ 存档要回到**它原来那本书**里。书还在 → 搬进 `<书>/`；书不在了（或者根本不知道是哪本）
      → 拒绝并说清楚，**不猜一个目录塞进去**（塞错地方比恢复不了更糟：用户会在
      另一本书里看见不属于它的存档）。

    ★ 目标已存在 → 拒绝（绝不覆盖）。同名在这里意味着"那一轮已经回去了"，
      覆盖就是拿旧的换掉新的。

        English:
    Move this entry **back** -> `(ok, destination or reason)`.
    ★ A save goes back into **the book it came from**. If the book still exists -> move into
      `<book>/`; if it is gone (or unknown) -> refuse and say so, **never guess a folder**
      (dumping it somewhere wrong is worse than not restoring: the user would see a save that does
      not belong to that book).
    ★ Target already exists -> refuse (never overwrite).
    """
    if not _inside_trash(entry.path, projects_root):
        return False, "拒绝：这一条不在回收站目录里"
    if not entry.path.is_dir():
        return False, "拒绝：这一条已经不在了（可能刚被删过）"
    root = Path(projects_root)
    if entry.is_novel:
        dest = root / entry.name
    else:
        if not entry.project:
            return False, ("恢复不了：不知道这一轮原本属于哪本书"
                           "（这次改版之前删的备份，且里面没有《任务介绍》）。"
                           "可以手工把它从回收站搬到对应的项目文件夹里。")
        proj_dir = root / entry.project
        if not proj_dir.is_dir():
            return False, (f"恢复不了：原书《{entry.project}》已经不在项目目录里。"
                           f"先把那本书恢复回来，再恢复这一轮。")
        dest = proj_dir / entry.name
    if dest.exists():
        return False, (f"恢复不了：目标位置已经有同名的了（{dest}）。"
                       f"要恢复请先处理掉那一份。")
    if not dest.parent.is_dir():
        return False, f"恢复不了：目标目录不存在（{dest.parent}）"
    ok, msg = atomic_move(entry.path, dest)
    if ok:
        _drop_sidecar(entry.path)      # 旁注跟着搬走就没意义了（搬的是目录，不是它）
        return True, str(dest)
    return False, msg


def purge(entry: TrashEntry, projects_root) -> tuple[bool, str]:
    """**永久删除**这一条（不可逆） → `(成功, 原因)`。

    ★ 护栏：只许删回收站**里面**的东西，且必须是真的目录。这两条挡的是
      "手滑传了个 `projects_root` 进来"那类事故 —— 那不是"删错一条"，
      是"整本没了"。

    ★ 旁注也要一起删：留着它，下次扫描会出现一条"名字有、目录没有"的鬼条目。

    ★★★ 2026-10-27：**永久删除一本小说要把回收站里属于它的存档一起删掉**
      （用户："删除小说项目的时候……应该同时把对应存档一起删除 前者是包含后者的"）。
      书目录里的存档会随 `rmtree` 一起走；这里补的是**与它平级躺着**的那几条
      （`orphan_runs_of`）—— 它们多半是这次改版之前留下的：**书已经不在了，
      那些存档谁也恢复不回去**，留着只能让用户一条条手工删。
      ⚠ 只删"属于这本书"的那几条，别的一律不动 —— "级联"不等于"顺手清空回收站"。

        English:
    **Permanently delete** this entry (irreversible) -> `(ok, reason)`.
    ★ Guardrails: only things **inside** the recycle bin, and it must be a real directory. These
      block accidents like "a wrong `projects_root` slipped in" -- that is not "one entry deleted",
      it is "a whole book gone".
    ★ The sidecar is deleted too: leaving it would produce a ghost entry (name present, folder gone)
      on the next scan.
    ★★★ 2026-10-27: **purging a book also purges its saves** (user: "when deleting a novel
      project ... the saves should go too -- the former contains the latter"). Saves inside the
      book folder go with the `rmtree`; this adds the ones still sitting **beside** it
      (`orphan_runs_of`) -- mostly leftovers from before this change: with the book gone **nobody
      can restore them anyway**, so all they do is force the user to delete them one by one.
      ⚠ Only the ones belonging to **this** book; cascading is not "empty the bin while we're here".
    """
    if not _inside_trash(entry.path, projects_root):
        return False, "拒绝：这一条不在回收站目录里"
    if not entry.path.is_dir():
        return False, "这一条已经不在了"
    # ★ 先算好要连带删哪些（**书还在的时候算**，删完 `scan_trash` 就扫不到它了）
    # [EN] ★ Compute the cascade **before** the delete (afterwards `scan_trash` cannot see it).
    also: list[TrashEntry] = []
    if entry.is_novel:
        mine = entry.path.resolve()
        also = [e for e in orphan_runs_of(entry.name, projects_root)
                if e.path.resolve() != mine]
    try:
        shutil.rmtree(entry.path)
    except OSError as e:
        return False, (f"删不掉：{e}。可能里面还有文件被占用 —— "
                       f"把程序里相关的推演停掉再试。")
    _drop_sidecar(entry.path)
    # ★★ 书已经删掉了才动这些：删书失败时不该顺手把它的存档也删了
    #    （"书删不掉、存档没了"是比"书还在、存档还在"糟得多的结果）。
    # [EN] ★★ Only after the book is really gone: if the book could not be deleted we must not
    # [EN] delete its saves anyway ("book survived, saves gone" is far worse than "both remain").
    gone: list[str] = []
    for e in also:
        if not e.path.is_dir():
            continue
        try:
            shutil.rmtree(e.path)
        except OSError:
            continue
        _drop_sidecar(e.path)
        gone.append(e.name)
    if gone:
        _LOG.info("永久删除《%s》时连带删掉了 %d 轮存档：%s",
                  entry.name, len(gone), '、'.join(gone))
    return True, str(entry.path)


# ══════════════════════════════════════════════════════════════════
#  子树（"删一个节点要连子节点一起"的依据）
# ══════════════════════════════════════════════════════════════════
def descendants(name: str, parents: dict[str, str | None],
                depth_guard: int = 256) -> list[str]:
    """`name` 的**全部后代**（不含自己），按**由深到浅**排好 —— 搬家就用这个顺序。

    ★ 为什么"由深到浅"：父节点先搬走，子节点的路径当场就失效了。必须**先叶子后根**，
      每一步操作的都是一个还完整存在的目录。

    ★ 防环：`parents` 可能是手改坏的（A→B→A）。走过的名字记下来，绝不重复展开。

        English:
    All descendants of `name` (excluding itself), ordered **deepest first** -- the order used for
    moving.
    ★ Why deepest first: move the parent first and the children's paths die instantly. Leaves must go
      first, so every step operates on a directory that still exists.
    ★ Cycle-safe: `parents` may be hand-edited garbage (A->B->A); visited names are never re-expanded.
    """
    kids: dict[str, list[str]] = {}
    for child, par in (parents or {}).items():
        p = str(par or '').strip()
        if p and p != child:
            kids.setdefault(p, []).append(child)
    out: list[str] = []
    seen: set[str] = {name}

    def _walk(node: str, guard: int) -> None:
        if guard <= 0:
            return
        for k in kids.get(node, []):
            if k in seen:
                continue
            seen.add(k)
            _walk(k, guard - 1)
            out.append(k)              # 后序 ⇒ 深的在前

    _walk(name, depth_guard)
    return out


# ══════════════════════════════════════════════════════════════════
#  「一本书的完整树」—— 拾卷与回收站共用同一份（2026-10-21 第三批）
# ══════════════════════════════════════════════════════════════════
@dataclass
class Forest:
    """一本书的**完整树**，加上"哪一半在哪一边"的归属。

    ★★★ 为什么要有它（用户原话：「拾卷和回收站里两边的树的结构应该是一样的
      或者说两者合并起来是一个完整的树 两者是应该是互补的」「如果我恢复某个节点
      但是其父节点在拾卷里没被恢复则对应节点也要显示成虚线框 也就是说拾卷里也需要
      有虚线框」）：

      以前两边各建各的树 ——
        拾卷：只喂"盘上活着的"；被删的那几轮**从树里消失**，它的子节点于是变成孤儿，
              被当成根节点顶上去（看起来像"树忽然多了一个根"）。
        回收站：只喂"回收站里的" + 撑树的活祖先。
      于是**同一段血统在两边长得不一样**：用户在拾卷里看到的第 4 次是根，在回收站里
      看到的是第 3 次的儿子。两边一合并，就成了两棵互相矛盾的树。

      ⇒ 现在只有**一棵**树（`forest()` 算出来的），两边各自显示它的一部分：
        自己那一边的节点是**实体**（能勾、能点、能删/恢复），另一半的节点是**虚线框**
        （只是撑住形状，不能操作）。两边的并集 = 完整树，交集 = 空。

    ★ 归属判定是**磁盘事实**，不是界面状态：`live` = 这本书目录下现在有那一轮；
      `deleted` = 它在 `已删除备份/` 里有对应条目。所以"恢复了子节点、父节点没恢复"
      这种半吊子状态，会自然变成"父在拾卷里是虚线框、子在回收站里是实体"。

        English:
    A book's **complete tree**, plus which half lives on which side.
    ★★★ Why it exists (user: "the trees in Pick-a-Volume and the recycle bin should have the
      same structure, or rather the two together form one complete tree -- they are
      complementary" and "if I restore a node whose parent was not restored, that node must also
      show a dashed frame, i.e. Pick-a-Volume needs dashed frames too"):
      Previously each side built its own tree -- Pick-a-Volume fed only the **live** rounds (the
      deleted ones vanished and their children were promoted to roots, looking like "the tree
      suddenly grew another root"), while the bin fed only the deleted ones plus live ancestors.
      So the same lineage looked different on the two sides and merged into two contradictory
      trees. => Now there is **one** tree (from `forest()`); each side shows its part: its own
      nodes are **solid** (tickable, clickable, deletable/restorable) and the other side's nodes
      are **dashed frames** (shape only, not operable). Union = the complete tree.
    ★ Ownership is a **disk fact**, not a UI state: `live` = that round is in the book folder
      now; `deleted` = it has an entry in `已删除备份/`. A half-restored state therefore falls
      out naturally.
    """

    rows: list[tuple[Path, int, bool, str]]   #: (路径, 层, 有没有子节点, 逻辑名)
    parents: dict[str, str | None]            #: 逻辑名 → 父逻辑名（合并后）
    live: set[str]                            #: 盘上活着的
    deleted: set[str]                         #: 在回收站里的
    path_of: dict[str, Path]                  #: 逻辑名 → 路径
    entries: dict[str, 'TrashEntry']          #: 只有 `deleted` 里的有
    #: 这一侧是"实体"的那些（`side='pick'` → live；`side='trash'` → deleted）。
    #: 其余出现在 `rows` 里的都是**撑树的虚线框**。
    mine: set[str] = field(default_factory=set)

    def is_placeholder(self, logical: str) -> bool:
        return logical not in self.mine


def forest(project_root, projects_root, *, side: str = 'pick') -> Forest:
    """算一本书的**完整树**，并按 `side` 标出"哪一半是实体"。

    参数
    ----
    project_root   这本书的目录（拾卷里那本）。
    projects_root  项目根（回收站与它同级）。
    side           `'pick'`（拾卷：活着的是实体）或 `'trash'`（回收站：被删的是实体）。

    ★★★ **同层顺序按生成时间正序，而且只有一处规则**（2026-10-22 用户：
      「同一级别（即所有根节点以及所有从某个节点推演出来的子节点）默认按照从时间顺序排列
      回收站也是这样」）。规则就是 `lineage.tree_order()`，两边都调它。
      ⚠ 这里**曾经有一个 `order` 参数**：拾卷把自己的排序档（默认"结束时间倒序"）传进来，
        再由 `_merge_order` 把被删的那几轮按序号"插值"回活着的中间。那个插值假设
        "活着的顺序是升序"，而默认档给的是**降序** ⇒ 同一层排成 `5, 4, 2`（连被删的
        第3次都掉了），既不是正序也不是倒序；而回收站不传 `order`、自己按序号升序排
        ⇒ 同一段血统两栏一正一反。**两处各写一份顺序，必然分叉**（和"两边各建一棵树"
      是同一种病）。所以那个参数**删掉**了：现在没有"按谁给的顺序"这回事。
      ⚠ 排序档没有废 —— 它仍决定打开拾卷时默认选中哪一轮（`_sorted_runs` 的第一条），
        只是不再左右树的形状。

    ★ 三条纪律（都有判据盯着）：
      ① **两边用的是同一棵树**：同一本、同一时刻，`forest(side='pick')` 与
         `forest(side='trash')` 的 `parents`、逻辑名集合、逐行层级必须完全一致 ——
         否则"合并即完整树"就是空话。
      ② **虚线框只用来撑形状**：`mine` 之外的节点不进任何操作集合（勾选、删除、恢复）。
      ③ **一条都不许丢**：`build_tree` 的兜底保证每一条都出现在 `rows` 里。

    ⚠ 性能：每次都重扫回收站目录。调用点是"打开拾卷 / 切 Tab / 删完一轮"，
      不是每帧，所以可以接受；但**不许**在滚动回调里调。

        English:
    Compute one book's **complete tree** and mark which half is solid for `side`.
    ★★★ **Per-level order is generation time ascending, and that rule lives in exactly one place**
      (user, 2026-10-22: "saves at the same level -- all roots and all children derived from a node --
      should default to time order; same for the recycle bin"). The rule is `lineage.tree_order()`
      and both sides call it. ⚠ There **used to be an `order` parameter** here: Pick-a-Volume passed
      its sort profile (default "end time descending") and `_merge_order` interpolated deleted rounds
      back by index -- that interpolation assumed the live order was **ascending** while the default
      profile is **descending**, so a level came out as `5, 4, 2` (losing round 3 entirely), neither
      ascending nor descending, while the bin (no `order`) sorted ascending on its own: one lineage
      read forwards on one tab and backwards on the other. **Two copies of an ordering rule always
      drift** (the same disease as "each side builds its own tree"), so the parameter is **gone**.
      ⚠ Sort profiles are not dead -- they still decide which round is selected by default.
    ★ Three rules (all covered by criteria): ① both sides use the **same** tree -- same parents,
      same name set, same per-row depths, or "union = complete tree" is empty talk; ② dashed
      frames exist **only** to hold the shape and never enter any operation set; ③ nothing lost.
    ⚠ Cost: rescans the bin each call. Called on "open Pick-a-Volume / switch tab / after a
      delete", not per frame -- acceptable, but never from a scroll callback.
    """
    root = Path(project_root)
    proj_name = root.name
    live_runs = Project(root, proj_name).list_runs()
    try:
        entries = [e for e in scan_trash(projects_root)
                   if (not e.is_novel) and e.project == proj_name]
    except OSError:
        entries = []

    # 翻译表：路径 → 逻辑名（回收站目录名带着时间戳前缀）
    # [EN] Translation table: path -> logical name (bin folders carry a timestamp prefix)
    name_of = {str(p): p.name for p in live_runs}
    name_of.update({str(e.path): e.name for e in entries})
    path_of = {v: Path(k) for k, v in name_of.items()}
    key = lambda p: name_of.get(str(p), Path(p).name)      # noqa: E731
    allp = live_runs + [e.path for e in entries]

    parents = LINEAGE.parents_of(allp, infer_missing=True, key=key) if allp else {}
    for e in entries:
        # 旁注里记的父是**删除那一刻的事实**，优先于任何推断
        # [EN] The sidecar's parent is the **fact at delete time**; it beats any inference
        if e.parent:
            parents[e.name] = e.parent

    live_names = {p.name for p in live_runs}
    del_names = {e.name for e in entries}
    all_names = list(dict.fromkeys(list(live_names) + list(del_names)))
    # ★★★ 同层顺序 = **生成时间正序**，两边同一句话（规则在 `lineage.tree_order`）。
    #   ⚠ 这里不许再"按活着的顺序插值"：那种写法要假设活着的顺序是升序，
    #     而拾卷的默认档是降序 ⇒ 被删的那几轮会插到错的位置，连顺序都谈不上。
    # [EN] ★★★ Per-level order = **generation time ascending**, the same sentence on both sides
    # [EN] (the rule lives in `lineage.tree_order`). ⚠ No more "interpolate by the live order": that
    # [EN] assumed the live order was ascending while the default profile is descending, so deleted
    # [EN] rounds landed in the wrong place.
    merged = LINEAGE.tree_order(all_names)

    # 主体 + 祖先链（祖先里另一半的节点就是"撑树的虚线框"）
    # [EN] The body + its ancestor chain (ancestors on the other side become dashed scaffolding)
    mine = live_names if side == 'pick' else del_names
    keep = set(mine)
    for nm in list(keep):
        cur, guard = nm, 0
        while guard < 64:
            guard += 1
            par = str(parents.get(cur) or '').strip()
            if not par or par in keep or par not in path_of:
                break
            keep.add(par)
            cur = par

    kept = [path_of[n] for n in merged if n in keep and n in path_of]
    sub_parents = {key(p): parents.get(key(p)) for p in kept}
    tree = LINEAGE.build_tree(kept, sub_parents, key=key)
    rows = [(p, d, h, key(p)) for p, d, h in tree]
    return Forest(rows=rows, parents=parents, live=live_names, deleted=del_names,
                  path_of=path_of, entries={e.name: e for e in entries},
                  mine=set(mine))
