# -*- coding: utf-8 -*-
"""判据：**文档布局 —— 开发向文档进 `developers/docs/`，用户文档留在根目录**。

来历（2026-10-10 用户原话）
---------------------------
「`发布版本\\0.1.0` 这里的一些 md（包括子文件夹），如不是代码需要的以及确实给用户用的，
**别的用于给开发者用的，都放到 developers 里并进行整理**。」

判起来才发现，这不只是"搬家"：**它后面藏着一个真 bug**。
`tools/make_release.py` 里原本有一份 `DEV_DOCS = {'Configuration_Classification.md',
'配置分类.md'}`，理由是"描述哪些配置项已删除、引用 config.py，不适合终端用户" ——
**这个判断是错的**：那两份《配置分类》讲的正是"配置放在哪一层、作用范围、优先级"，
而且 `README.md` / `README_EN.md` / `使用说明.md` / `User_Manual.md` /
`配置指南.md` / `Configuration_Guide.md` **六处**都把链接指向它。
按旧清单排除之后，发布包里这些链接**全是断的**（实测：`0.1.0` 发布包的 README
就链到了一个不存在的 `配置分类.md`）。

所以这一支判据的重心不是"文件在不在那个目录"，而是最后那条
**C5：用户文档链接得到的东西，发布包里必须有** —— 它才是这类错误的通用闸门。

覆盖
----
  A. 布局 —— 该搬的搬走了、该留的留下了，且**同一份不许两头都有**
  B. 链接 —— 用户文档里的相对 md 链接**一个都不许断**；并且扫描器**自己能红**
  C. 发布一致性 —— 发布脚本的排除/必带清单与这套判定**必须一致**（C5 是重点；
     C6 是**同一类病的第二处**：`exports/` 是用户自己的作品与日志，却一直没被排除）
  D. 索引 —— `developers/README.md` 与 `developers/docs/` 双向对得上，不许有黑户

跑法：`.venv/Scripts/python.exe tools/verify_doc_layout.py`
报告：`assets/screenshots/doc_layout_report.json`

English:
Criterion: **doc layout -- developer-facing docs go into `developers/docs/`, user docs stay in
the root directory**.
Origin (user's exact words, 2026-10-10)
---------------------------
"Some of the md files in `发布版本\\0.1.0` (including subfolders), if they are not needed by the code
and are genuinely for users,
**put all the others meant for developers into developers and organize them**."
Only when judging did it become clear this isn't just a "move": **a real bug is hidden behind
it**.
`tools/make_release.py` originally had a `DEV_DOCS = {'Configuration_Classification.md',
'配置分类.md'}`, justified as "describes which config items were deleted, references config.py, not
suitable for end users" --
**that judgement is wrong**: those two 《配置分类》 docs are exactly about "which layer config goes
in, its scope, its priority",
and `README.md` / `README_EN.md` / `使用说明.md` / `User_Manual.md` /
`配置指南.md` / `Configuration_Guide.md` **six places** all point their links at it.
After excluding per the old list, these links in the release package **are all broken**
(measured: the `0.1.0` release package's README
So the focus of this branch's criterion is not "is the file in that directory", but the last one
**C5: whatever a user doc links to must be present in the release package** -- that is the
generic gate for this kind of error.
Coverage
----
  A. Layout -- what should be moved is moved, what should stay stays, and **the same file must not exist on both sides**
  B. Links -- relative md links in user docs **must not break, not one**; and the scanner **must be able to go red itself**
  C. Release consistency -- the release script's exclusion/must-carry list **must be consistent** with this decision (C5 is the focus;
     C6 is **the second instance of the same disease**: `exports/` is the user's own work and logs, yet it has never been excluded)
  D. Index -- `developers/README.md` and `developers/docs/` match in both directions; no unlisted entries allowed
How to run: `.venv/Scripts/python.exe tools/verify_doc_layout.py`
Report: `assets/screenshots/doc_layout_report.json`
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}

# ── 判定表（这一支判据的"真相源"，改判定就改这里）───────────────────
# 用户文档：**留在根目录**（给用户看 / 说明书要链它）
# [EN] ── Decision table (the "source of truth" for this branch's criteria; change the decision
# [EN] here)───────────────────
# [EN] User docs: **stay in the root directory** (for users to read / the manual links to them)
USER_DOCS = [
    'README.md', 'README_EN.md', '使用说明.md', 'User_Manual.md',
    'Configuration_Guide.md', '配置指南.md',
    'Configuration_Classification.md', '配置分类.md',
    '剧本输出格式.md', '设定写作指导.md',
]
# 开发向文档：**搬进 `developers/docs/`**（程序不读、也不是给用户看的）
# [EN] Developer-facing docs: **move into `developers/docs/`** (not read by the program, and not for
# [EN] users)
DEV_DOCS = [
    'Agent全景.md', 'Agent认知升级方案.md', '剧情引擎.md',
    '推演测试报告.md', '剧组流程审计.md', '记忆与上下文评估.md',
]
# 外部调研（整目录搬）
# [EN] External research (move the whole directory)
REF_DIR_OLD = 'docs/外部借鉴'
REF_DIR_NEW = 'developers/docs/外部借鉴'
REF_FILES = ['01_编剧与剧本.md', '02_导演与分镜.md', '03_美术造型道具声音.md',
             '04_开卷与分析质量.md', '05_多智能体与宣发.md']


def ok(name: str, cond: bool, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    p = APP / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''


# ══════════════════════════════════════════════════════════════════
#  链接扫描（B 组用；A/B/C 都靠它）
# [EN] Link scanning (used by group B; A/B/C all rely on it)
# ══════════════════════════════════════════════════════════════════
_LINK = re.compile(r'!?\[[^\]]*\]\(([^)\s]+?)\)')


def rel_md_links(doc: str) -> list[str]:
    """一份文档里所有**相对路径的 `.md` 链接**（去掉锚点；外链不要）。
        English:
    All **relative-path `.md` links** in a doc (strip anchors; ignore external links).
    """
    out: list[str] = []
    for m in _LINK.finditer(read(doc)):
        tgt = m.group(1).split('#', 1)[0].strip()
        if not tgt or tgt.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        if not tgt.lower().endswith('.md'):
            continue
        out.append(tgt)
    return out


def scan_doc_commands(text: str) -> tuple[int, list[str], list[str]]:
    """扫一份 md：**代码块里**出现的 `developers/*.py` → (处数, 不存在的, 没写"不随发布包提供"的)。

    为什么只算代码块：正文里顺手提一句"判据在 `developers/x.py`"是常态，
    要求它旁边也写"不随发布包提供"就是一刀切；读者会**照着敲**的只有代码块。
    窗口用"最近一个标题到现在"（这一节开头交代过就算），而不是"紧邻三行" ——
    作者的写法是"小节开头一句话说明，再给命令"，中间常隔着几行说明文字。

    ⚠ 两处已踩过的坑，都写进判据里了：
      ① 代码块里的 bash 注释也以 `#` 开头 ⇒ 认标题必须**限定在块外**，
         否则窗口被挪进块内，"这一节开头写过的那句"就漏了（在已经写好的文档上假红）。
      ② 英文那句常折行成 "**not\\nshipped in the release package**" ⇒
         必须**整段拼起来**再比，按行比永远配不上（在 README_EN 上假红）。
    [EN] Scan one markdown file: `developers/*.py` inside **fenced blocks** ->
    (count, missing, missing-the-"not shipped" note). Fenced blocks only, because inline
    mentions are normal prose. The window is "from the nearest heading to here" (stated at the
    top of the section), not "the three lines above".
    [EN] Two traps already hit, both pinned here: ① a bash comment inside a block also starts
    with `#`, so headings must only count **outside** fences; ② the English note wraps as
    "**not\\nshipped ...**", so the section must be **joined** before matching.
    """
    ship_note = ('不随发布包提供', 'not shipped in the release', 'not shipped')
    lines = str(text or '').splitlines()
    count = 0
    missing: list[str] = []
    undocumented: list[str] = []
    in_code = False
    head = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith('```'):
            in_code = not in_code
            continue
        if not in_code:
            if stripped.startswith('#'):
                head = i
            continue
        # 允许子目录（`developers/sdk/xxx.py`）：只认平铺的话，写了子目录的命令会被**静默漏掉**
        # [EN] Allow subdirectories: matching flat names only would silently skip them
        for m in re.finditer(r'developers/((?:[\w.\-]+/)*[\w.\-]+\.py)', line):
            count += 1
            name = m.group(1)
            if not (APP / 'developers' / name).is_file():
                missing.append(name)
                continue
            if not any(s in ' '.join(lines[head:i + 4]) for s in ship_note):
                undocumented.append(name)
    return count, missing, undocumented


def scan_broken(base: Path, names: list[str]) -> list[str]:
    """返回 `文件 -> 目标` 形式的断链列表。**只认相对链接**。
        English:
    Return the broken-link list in `file -> target` form. **Only relative links count**.
    """
    bad: list[str] = []
    for n in names:
        p = base / n
        if not p.is_file():
            continue
        for tgt in rel_md_links(n if base == APP else str(p)):
            if not (p.parent / tgt).exists():
                bad.append(f'{n} -> {tgt}')
    return bad


# ══════════════════════════════════════════════════════════════════
def test_layout() -> bool:
    """A 组：布局。
        English:
    Group A: layout.
    """
    k = True
    still = [n for n in DEV_DOCS if (APP / n).exists()]
    k &= ok('A1 ★★ 根目录**不再有**开发向文档（是"搬"不是"复制"）',
            not still, f'仍在根目录: {still}')
    miss = [n for n in DEV_DOCS if not (APP / 'developers' / 'docs' / n).is_file()]
    k &= ok('A2 ★★ 六份开发向文档都在 `developers/docs/` 里', not miss, f'缺: {miss}')
    thin = [n for n in DEV_DOCS
            if (APP / 'developers' / 'docs' / n).is_file()
            and (APP / 'developers' / 'docs' / n).stat().st_size < 500]
    k &= ok('A2b ★ 搬过去的是**完整文件**（不是空壳占位）', not thin, f'太小: {thin}')
    k &= ok('A2c ★ 搬过去的文档首行是标题（内容没被截）',
            all(read(f'developers/docs/{n}').lstrip().startswith('#')
                for n in DEV_DOCS if (APP / 'developers' / 'docs' / n).is_file()), '')
    REF_N = len(list((APP / REF_DIR_NEW).glob('*.md'))) if (APP / REF_DIR_NEW).is_dir() else 0
    k &= ok('A3 ★ `docs/外部借鉴/` 整目录已搬走（旧目录不存在），新目录里有 **5 份调研 + 1 份落地对照表**',
            not (APP / REF_DIR_OLD).exists()
            and not (APP / 'docs').exists()
            and REF_N >= 6
            and all((APP / REF_DIR_NEW / n).is_file() for n in REF_FILES)
            and (APP / REF_DIR_NEW / '00_落地对照表.md').is_file(),
            f'新目录 {REF_N} 份')
    lack = [n for n in USER_DOCS if not (APP / n).is_file()]
    k &= ok('A4 ★★ 十份用户文档**仍然在根目录**（别把该给用户看的也搬走）',
            not lack, f'缺: {lack}')
    both = [n for n in DEV_DOCS if (APP / n).exists() and (APP / 'developers' / 'docs' / n).exists()]
    k &= ok('A5 ★★ 同一份文档不许"两头都有"（两份真相最难查）', not both, f'重复: {both}')
    return k


def test_links() -> bool:
    """B 组：链接。
        English:
    Group B: links.
    """
    k = True
    bad = scan_broken(APP, USER_DOCS)
    k &= ok('B1 ★★★ 根目录用户文档里的**相对 md 链接一个都不许断**',
            not bad, f'{len(bad)} 处: ' + ' | '.join(bad[:6]))
    into_dev = [f'{n} -> {t}' for n in USER_DOCS for t in rel_md_links(n)
                if t.replace('\\', '/').startswith('developers/')]
    k &= ok('B2 ★★ 用户文档**不许**用相对链接指进 `developers/`'
            '（那目录不随发布包走 ⇒ 一定是断链；要提就写"源码树里的 …、不随发布包提供"）',
            not into_dev, f'{len(into_dev)} 处: {into_dev[:4]}')
    # ★ 判据自己得能红：造一个坏链接，扫描器必须报出来
    # [EN] ★ The criterion itself must be able to go red: create a bad link and the scanner must report it
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / 'a.md').write_text('[x](没有这个文件.md)\n', encoding='utf-8')
        (t / 'b.md').write_text('[x](a.md)\n', encoding='utf-8')
        probe = scan_broken(t, ['a.md', 'b.md'])
    k &= ok('B3 ★★ 断链扫描器**自己能红**（造一个指向不存在文件的链接，必须被报出来）'
            '—— 否则 B1 绿只是因为"它什么也没看见"',
            len(probe) == 1 and '没有这个文件.md' in probe[0], f'探针结果={probe}')
    return k


def _release_plan() -> tuple[dict, set]:
    """import 发布脚本，用**真** ignore 规则走一遍树，收集"会跳过什么"。
        English:
    Import the release script, walk the tree with the **real** ignore rules, and collect "what would
    be skipped".
    """
    import tools.make_release as MR          # noqa: PLC0415
    args = SimpleNamespace(keep_dev_docs=False, keep_dev_tools=False)
    plan = MR.Plan()
    ignore = MR.make_ignore(args, plan, APP)
    for _cur, _dirs, _files in MR._walk(APP, ignore):
        pass
    flat: set[str] = set()
    for items in plan.skipped.values():
        for s in items:
            flat.add(str(s).replace('\\', '/'))
    return dict(plan.skipped), flat


def _covered(target: str, skipped: set[str]) -> bool:
    """目标（或它的任一上层目录）在排除集里 —— 那就是"发布包里没有它"。
        English:
    The target (or any of its parent directories) is in the exclusion set -- that means "it is not
    in the release package".
    """
    t = target.replace('\\', '/').lstrip('./')
    parts = t.split('/')
    return any('/'.join(parts[:i]) in skipped for i in range(1, len(parts) + 1))


def test_release_consistency() -> bool:
    """C 组：发布脚本的判定必须和这套布局一致。
        English:
    Group C: the release script's decision must be consistent with this layout.
    """
    k = True
    import tools.make_release as MR          # noqa: PLC0415
    # C1：那份"点名排除文档"的清单**必须为空** —— 非空就意味着又有用户文档会被排除
    # [EN] C1: that "named exclusion doc" list **must be empty** -- non-empty means yet another user doc
    # [EN] will be excluded
    k &= ok('C1 ★★ `make_release.DEV_DOCS` 为空（原来那两份《配置分类》已被改判为用户文档）',
            len(MR.DEV_DOCS) == 0, f'DEV_DOCS={sorted(MR.DEV_DOCS)}')
    # C2：用户文档必须进"必带"清单（缺一份 = 发布包缺件，自检才会说话）
    # [EN] C2: user docs must be in the "must-carry" list (one missing = a missing piece in the release
    # [EN] package; only then does self-check speak up)
    miss = [n for n in USER_DOCS if n not in MR.REQUIRED]
    k &= ok('C2 ★★ 十份用户文档全在发布脚本的 `REQUIRED` 里', not miss, f'没登记: {miss}')
    # C3/C4：整目录排除 developers（含 docs），且**不排除**任何一份用户文档
    # [EN] C3/C4: exclude the whole directory developers (including docs), and **do not exclude** any user
    # [EN] doc
    skipped_groups, skipped = _release_plan()
    k &= ok('C3 ★★ 发布排除集里有整个 `developers/`（所以 `developers/docs/` 的文档天然不进包）',
            'developers' in skipped
            and any('开发' in g for g in skipped_groups
                    if 'developers' in [str(x).replace('\\', '/') for x in skipped_groups[g]]),
            f'组={ {g: len(v) for g, v in skipped_groups.items()} }')
    hit = [n for n in USER_DOCS if _covered(n, skipped)]
    k &= ok('C4 ★★ 发布排除集里**没有**任何一份用户文档', not hit, f'被误排除: {hit}')
    # ★★★ C5：本轮那个真 bug 的通用闸门
    # [EN] ★★★ C5: the generic gate for that real bug this round
    bad = [(n, t) for n in USER_DOCS for t in rel_md_links(n) if _covered(t, skipped)]
    k &= ok('C5 ★★★ **用户文档链接得到的东西，发布包里必须有** —— 凡是被用户文档相对链接'
            '指向的目标，都不许出现在发布排除集里（这就是"README 链《配置分类》而发布脚本'
            '把它排除"那个 bug 的通用闸门）',
            not bad, f'{len(bad)} 处: {bad[:4]}')
    # C6：同一类病的第二处 —— **`exports/` 是用户自己的作品与日志，不许进发布包**。
    #     `.gitignore` 早就写了这一条，可排除清单里一直没有它：原先只拦住里面的 `*.log`，
    #     诊断包的 README / 自检 json / 小说正文照走。判据只覆盖了"想得起来的那一半"，
    #     所以要在这里再钉一次。
    # [EN] C6: the second instance of the same disease -- **`exports/` is the user's own work and logs; it
    # [EN] must not go into the release package**.
    # [EN] `.gitignore` has long had this rule, but the exclusion list never included it: originally it
    # [EN] only blocked the `*.log` inside,
    # [EN] while the diagnostic package's README / self-check json / novel text still went through. The
    # [EN] criterion only covered "the half you could remember",
    # [EN] so it must be pinned down again here.
    k &= ok('C6 ★★ 发布排除集里有整个 `exports/`（`.gitignore` 写明它是"用户自己的作品'
            '与运行日志"；只拦里面的 `*.log` 是不够的）',
            'exports' in skipped, f'已排除: {sorted(skipped)[:12]}')
    # C7：**用户文档里给出的、读者会照着敲的那条命令**，脚本必须真的存在，
    #     而且**这一节**必须写清"不随发布包提供"。
    #     ⚠ 为什么单钉这一条：`developers/` **整目录不进发布包**（C3），而 `使用说明.md`
    #     / `README.md` 会给出可复制的命令行。写错一个字、或者以后有人挪了这个脚本，
    #     读者拿到的就是"照着做报 FileNotFoundError"，而**C1–C6 全都照样绿**
    #     （它们只管 md 链接与排除清单，不管"正文里那句命令"）。
    #     ⚠ **只算代码块里的**：正文里顺手提一句"判据在 `developers/x.py`"是常态，
    #       要求它旁边也写"不随发布包提供"就是一刀切（第一版这么写，一次点出 12 条
    #       假红，全是叙述性提及）。读者会**照着敲**的只有代码块。
    # [EN] C7: **Every command a user doc tells you to type** must point at a real script, and
    # [EN] **that section** must say it is not shipped in the release package.
    # [EN] Why pin this: the whole `developers/` tree is excluded from releases (C3), while the
    # [EN] manual/README hand out copy-paste commands; one typo or a moved script and the reader
    # [EN] gets FileNotFoundError -- with C1..C6 still green.
    # [EN] ⚠ **Fenced blocks only**: mentioning a script inline is normal prose; demanding the
    # [EN] note there too is blanket over-reach (the first version did that and produced 12 false
    # [EN] reds). Only fenced blocks get typed by the reader.
    runnable = 0
    miss_cmd: list[str] = []
    undocumented: list[str] = []
    for doc in ('使用说明.md', 'README.md', 'User_Manual.md', 'README_EN.md'):
        n_cmd, miss, undoc = scan_doc_commands(read(doc))
        runnable += n_cmd
        miss_cmd += [f'{doc}:{n}' for n in miss]
        undocumented += [f'{doc}:{n}' for n in undoc]
    k &= ok('C7 ★★★ 用户文档代码块里给出的 `developers/*.py` 命令**都指向真实脚本**，'
            '且这一节写清了"不随发布包提供"（否则读者照着敲就报 FileNotFoundError）',
            runnable > 0 and not miss_cmd and not undocumented,
            f'代码块里 {runnable} 处命令；找不到的 {miss_cmd} / 没写"不随发布包提供" {undocumented}')
    # ── C7b / C7c：**成对**。判据自己也得能被检验（不然它可能只是"看什么都没看见"）──
    # [EN] C7b / C7c: **paired**. The criterion itself must be testable (otherwise it may simply
    # [EN] be "seeing nothing at all").
    _n, _miss, _undoc = scan_doc_commands(
        '## 某节\n\n正文里顺口提一句 `developers/nope.py` 不算命令。\n')
    k &= ok('C7b ★★★ 成对：**正文里提一句**不存在的脚本**不报红**'
            '（读者不会照着敲，一刀切会点出一堆假红）',
            _n == 0 and not _miss and not _undoc, f'{_n}/{_miss}/{_undoc}')
    _n2, _miss2, _undoc2 = scan_doc_commands(
        '## 某节（不随发布包提供）\n\n```bash\n'
        'python developers/nope_dir/nope.py\n```\n')
    k &= ok('C7c ★★★ 代码块里**指向不存在的脚本**必红（这才证明 C7 真的在查）',
            _n2 == 1 and _miss2 == ['nope_dir/nope.py'], f'{_n2}/{_miss2}/{_undoc2}')
    return k


def test_index() -> bool:
    """D 组：`developers/README.md` 是文档的索引，双向都得对得上。
        English:
    Group D: `developers/README.md` is the doc index; both directions must match.
    """
    k = True
    idx = read('developers/README.md')
    k &= ok('D1 ★ 索引里点名的每一份 dev 文档都真实存在',
            all(n in idx and (APP / 'developers' / 'docs' / n).is_file() for n in DEV_DOCS),
            f'缺: {[n for n in DEV_DOCS if not (APP / "developers" / "docs" / n).is_file()]}')
    black = [p.name for p in (APP / 'developers' / 'docs').glob('*.md') if p.name not in idx]
    k &= ok('D2 ★★ `developers/docs/` 里**不许有黑户** —— 每份都得在索引里被点名',
            not black, f'没登记: {black}')
    k &= ok('D3 ★★ 索引里**说清**了 `docs/` 不随发布包走 —— 而且必须**挂在那张文档表的旁边**'
            '（不是随便哪一行提到就算：以后有人拿裸文件名当链接，正是因为有这句没读到）',
            any('`docs/`' in ln and '不随发布包' in ln for ln in idx.splitlines()),
            f'含"docs/"+“不随发布包"的行: '
            f'{[ln[:60] for ln in idx.splitlines() if "docs/" in ln][:3]}')
    return k


def main() -> int:
    checks = [('布局', test_layout), ('链接', test_links),
              ('发布一致性', test_release_consistency), ('索引', test_index)]
    for name, fn in checks:
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-800:]})
    path = APP / 'assets' / 'screenshots' / 'doc_layout_report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')

    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n文档布局验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
        if c['detail']:
            print(f'      {c["detail"][:300]}')
    for x in REPORT['notes']:
        print('  · ', x)
    print('→ 全部通过' if not bad else '→ 有失败项')
    print('报告 ->', path.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
