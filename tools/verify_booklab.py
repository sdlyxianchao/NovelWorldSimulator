# -*- coding: utf-8 -*-
"""判据：**拆书**（`booklab/`）。

覆盖六层，每层都要能红：

  A 方法论（`theory`）—— 拆什么、四问、提示词里真的写了那些要求
  B 读书（`reader`）—— 分章 · **分层取样（确定性的、开头尾部必留）** · 批次
  C 拆解（`analyzer`）—— MOCK 下四道工序真跑 · 拿不到时**照实记账** · 不抄原文
  D 技能包（`skillgen`）—— 三份齐 · frontmatter 必须字段 · **同名不覆盖**
  E 拆书库（`store`）—— 读回 · **按类型匹配（同题材两种叫法也要配上）** · 不硬塞
  F 接线（行为级）—— `craft_block` 里**三人小组拿完整版、其它职位拿压缩版**

用法：
    python tools/verify_booklab.py
    python tools/verify_booklab.py --logic-only

English:
Criterion: **book dismantling** (`booklab/`).
Cover six layers, each layer must be able to go red:
  A Methodology (`theory`) -- what to dismantle, the four questions, whether the prompt really states those requirements
  B Reading (`reader`) -- chapter splitting · **layered sampling (deterministic, head and tail always kept)** · batching
  C Dismantling (`analyzer`) -- under MOCK the four procedures really run · when unavailable **record honestly** · do not copy the source text
  D Skill pack (`skillgen`) -- the three files present · required frontmatter fields · **same name does not overwrite**
  E Book-dismantle library (`store`) -- read back · **match by type (the same genre under two names must also match)** · do not force-fit
  F Wiring (behavior level) -- in `craft_block` **the three-person group gets the full version, other roles get the compressed version**
Usage:
    python tools/verify_booklab.py
    python tools/verify_booklab.py --logic-only
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / 'assets' / 'screenshots'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG  # noqa: E402

report: dict = {'checks': []}


def ok(name: str, good: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(good),
                             'detail': str(detail)[:300]})
    print(('  ✓ ' if good else '  ✗ ') + name
          + (f'   [{detail}]' if detail and not good else ''))
    return bool(good)


def _rm(p) -> None:
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception:                                            # noqa: BLE001
        pass


def _mkbook(tmp: Path, n: int = 20, *, per: int = 12) -> Path:
    """造一本测试书（每章 `per` 句，够触发分章）。
        English:
    Build a test book (`per` sentences per chapter, enough to trigger chapter splitting).
    """
    tmp.mkdir(parents=True, exist_ok=True)
    chunks = []
    for i in range(1, n + 1):
        body = ('临河茶肆的堂里坐着七八个人。主角把账本翻到昨夜那一页，'
                '墨迹还没干透。外头有人喊了一声，没人应。' * per)
        chunks.append(f'第{i}章 第{i}回的事\n{body}\n')
    p = tmp / '测试书.txt'
    p.write_text('\n'.join(chunks), encoding='utf-8')
    return p


# ══════════════════════════════════════════════════════════════
#  A 方法论
# [EN] A Methodology
# ══════════════════════════════════════════════════════════════
def test_theory(tmp: Path) -> None:
    from booklab import theory as T

    ok('A1 ★ 拆解维度够全（≥7 个：骨架/人设/情绪/情节/结构/语言/设定）',
       len(T.DIMENSIONS) >= 7, f'{len(T.DIMENSIONS)} 个')
    names = '、'.join(T.names_of(T.FINAL_DIMS))
    for need in ('节奏', '人物', '情绪', '情节', '结构', '语言', '设定'):
        ok(f'A2 维度里有「{need}」这一类（用户点名要拆的东西）',
           any(need in n for n in T.names_of(T.FINAL_DIMS)), names)

    qs = T.questions_text()
    keys = [q['key'] for q in qs]
    ok('A3 ★★ 首问就是用户点名的那四件事（书名/类型/好在哪/重点拆什么）',
       keys == ['title', 'genre', 'good', 'focus'], str(keys))
    ok('A4 每问都带提示（作者不知道该怎么答时看它）',
       all(q.get('hint') for q in qs), '')

    # 提示词里必须真的写了那些要求（**方法论文本进不了提示词＝白写**）
    # [EN] The prompt must actually contain those requirements (**methodology text that doesn't make it
    # [EN] into the prompt = written in vain**)
    ok('A5 ★★ 粗扫提示词里有"一句话/功能/情绪/钩子"四样'
       '（少一样，波浪线就画不出来）',
       all(k in T.SCAN_PROMPT for k in ('一句话', '功能', '情绪', '钩子')), '')
    ok('A6 ★★ 精拆提示词里有"怎么写的/为什么有效/怎么用"三样'
       '（少了就退化成读后感）',
       all(k in T.DEEP_PROMPT for k in ('怎么写的', '为什么有效', '怎么用')), '')
    ok('A7 ★★ 精拆提示词里**明令禁止**写"写得很好"这类评价',
       '禁止' in T.DEEP_PROMPT and '写得很好' in T.DEEP_PROMPT, '')
    ok('A8 ★★★ 归纳提示词里点破了"**关于这本书的** vs **能拿走的**"这个分界'
       '（这一步做不好，拆书就只是读书笔记）',
       '能拿走的' in T.FINAL_PROMPT and '扔掉' in T.FINAL_PROMPT, '')
    ok('A9 ★★ 归纳提示词要求写「不适合」' '（说不出不适合什么＝还没看清）',
       '不适合' in T.FINAL_PROMPT and '不许空着' in T.FINAL_PROMPT, '')
    ok('A10 「重点拆什么」空着时不硬凑一句（空串）', T.focus_line('') == '', '')
    ok('A11 「好在哪」空着时不硬凑（空串）', T.prefer_line('') == '', '')
    ok('A12 两者有值时都会变成提示词里的一段',
       '特别想拆' in T.focus_line('节奏') and '好在' in T.prefer_line('第3章'), '')

    # ★★ **四问的 ask / hint 八条都要有英文**（2026-10-07 补的判据）。
    # [EN] ★★ **All eight ask / hint entries of the four questions must have English** (criterion added
    # [EN] 2026-10-07).
    #
    # 为什么在这里单钉一条：这八条是**动态 key**（界面上是 `t(q['ask'])` /
    # `t(q['hint'])`，见 `gui/app_flet`），而 `tools/i18n_check.py` 只扫
    # `t('字面量')` —— **扫不到它们**。结果就是：英文界面下这四条问题一直
    # 显示中文，而检查脚本一声不吭（实测漏过一次）。
    # 判据：`QUESTIONS` 里每个 ask / hint 都必须在 `i18n._ZH2EN` 里有条目。
    # [EN] Why single out a rule here: these eight are **dynamic keys** (in the UI they are `t(q['ask'])` /
    # [EN] `t(q['hint'])`, see `gui/app_flet`), while `tools/i18n_check.py` only scans
    # [EN] `t('literal')` -- **it cannot see them**. The result: under the English UI these four questions
    # [EN] kept
    # [EN] showing Chinese, and the check script said nothing (actually missed once in testing).
    # [EN] Criterion: every ask / hint in `QUESTIONS` must have an entry in `i18n._ZH2EN`.
    from i18n import _ZH2EN
    miss_tr = [str(q.get(k)) for q in T.QUESTIONS for k in ('ask', 'hint')
               if str(q.get(k) or '').strip() and str(q.get(k)) not in _ZH2EN]
    ok('A13 ★★ 四问的 ask/hint **八条都在 i18n 里登记了英文**'
       '（它们是动态 key，`i18n_check` 扫不到 —— 漏过译，'
       '表现是"英文界面下这四条问题还是中文"）',
       not miss_tr, f'缺译：{miss_tr}')


# ══════════════════════════════════════════════════════════════
#  B 读书
# [EN] B Reading
# ══════════════════════════════════════════════════════════════
def test_reader(tmp: Path) -> None:
    from booklab import reader as R

    p = _mkbook(tmp, 20)
    b = R.read_book(p)
    ok('B1 ★ 分章：一份 20 章的文本真的分成 20 章', b.n == 20, f'{b.n} 章')
    ok('B2 章的标题带序号与原名（读者能对回去）',
       '第1章' in b.chapters[0].title, b.chapters[0].title)
    ok('B3 每章的字数是真的（不是标题行也算进去）',
       b.chapters[0].chars > 100, str(b.chapters[0].chars))

    # 读不了的 / 空文件：**不许抛**
    # [EN] Unreadable / empty files: **must not throw**
    empty = tmp / '空.txt'
    empty.write_text('', encoding='utf-8')
    ok('B4 ★ 空文件不抛异常，返回"没有正文"（调用方照实说，不是崩）',
       R.read_book(empty).n == 0, '')

    nochap = tmp / '不分章.txt'
    nochap.write_text('一整段没有章节标题的正文。' * 50, encoding='utf-8')
    b2 = R.read_book(nochap)
    ok('B5 ★ 没有章节标题时整篇当一章（**照样能拆**，不是拒绝服务）',
       b2.n == 1, f'{b2.n} 章')

    # ★★ 分层取样
    # [EN] ★★ Layered sampling
    idx = R.layer_pick(500, 20)
    ok('B6 ★★ 章数超预算时**按位置分层抽**，不是随机（随机不可复现，'
       '同一本书打两次得不同结论）',
       len(idx) == 20 and idx[:4] == [0, 1, 2, 3], str(idx[:6]))
    ok('B7 ★★ 开头四章**必留**（黄金三章 —— 作者的全部本事在这儿用过一遍）',
       all(i < 4 for i in idx[:4]), str(idx[:4]))
    ok('B8 ★★ 末尾三章**也留**（网文按章收钱，尾部最能看出靠什么留人）',
       idx[-3:] == [497, 498, 499], str(idx[-3:]))
    ok('B9 ★ 取样是**确定性**的（同样输入两次结果一样）',
       R.layer_pick(500, 20) == R.layer_pick(500, 20), '')
    ok('B10 书短于预算时**全取**（不抽）', R.layer_pick(20, 288) == list(range(20)), '')
    ok('B11 空书返回空（不抛）', R.layer_pick(0, 20) == [], '')

    gs = R.batches(list(range(25)), 12)
    ok('B12 分批：25 条按 12 一批 → 3 批', len(gs) == 3, f'{len(gs)} 批')

    txt = R.render_batch(b.chapters[:2])
    ok('B13 粗扫那一段带章名与字数（模型能对回去）',
       '【第1章' in txt and '字）' in txt, txt[:40])
    dtxt = R.render_deep(b.chapters[:2])
    ok('B14 精读那一段取得更长（手法要看得到）',
       len(dtxt) > len(txt), f'{len(dtxt)} vs {len(txt)}')

    # ★★ 挑重点章
    # [EN] ★★ Pick key chapters
    scan = [{'章': c.title, '一句话': 'x', '功能': [], '情绪': 1 if i < 5 else 5,
             '钩子': '无'} for i, c in enumerate(b.chapters)]
    deep = R.pick_deep(b, scan, good='')
    ok('B15 ★★ 挑重点章是**确定性**的（两次一样）',
       [c.title for c in R.pick_deep(b, scan)] == [c.title for c in deep], '')
    ok('B16 ★★ 情绪最高的章会被挑进精读（爆点最能看出手法）',
       b.chapters[-1].title in [c.title for c in deep],
       str([c.title[:8] for c in deep]))
    ok('B17 ★★ **开头三章一定进**（立人设与放钩子的手法最密）',
       all(c.title in [x.title for x in deep]
           for c in b.chapters[:3]), str([c.title[:6] for c in deep][:4]))

    ol = R.outline_text(b, scan)
    ok('B18 全书概览按章号排序（不是按情绪排 —— 那是曲线的读法）',
       ol.index('第1章') < ol.index('第3章'), '')


# ══════════════════════════════════════════════════════════════
#  C 拆解 + D 技能包
# [EN] C Dismantling + D Skill packs
# ══════════════════════════════════════════════════════════════
def test_digest(tmp: Path):
    from booklab import analyzer as A
    from booklab import skillgen as SG

    p = _mkbook(tmp / 'a', 20)
    steps: list[str] = []
    d = asyncio.run(A.run(str(p), A.Brief(title='测试书', genre='悬疑·单元剧',
                                          good='第 3 章', focus='节奏'),
                          on_step=lambda k, x='': steps.append(k)))

    ok('C1 ★★ 四道工序都跑了（分章 → 粗扫 → 精读 → 归纳）',
       all(k in steps for k in ('read', 'scan', 'deep', 'final')), str(steps))
    ok('C2 ★★ 粗扫真的拿到逐章行（不是空转）', len(d.scan) >= 15,
       f'{len(d.scan)} 行 / {d.book.n if d.book else 0} 章')
    ok('C3 ★ 精读拿到笔记', len(d.deep) >= 2, f'{len(d.deep)} 条')
    ok('C4 ★★★ 归纳出**可复用的写法**（有模块才算拆成）',
       len(d.modules) >= 2 and d.ok, f'{len(d.modules)} 条')
    ok('C5 ★★ 每条模块都写了"怎么做"（只有名字的模块没法用）',
       all(m.get('怎么做') for m in d.modules), '')
    ok('C6 ★★ 每条模块都写了"什么时候用"（不知道什么时候用＝用不上）',
       all(m.get('什么时候用') for m in d.modules), '')
    ok('C7 ★★ `final` 里有"不适合"（**知道什么不能照搬**与知道什么能拿一样重要）',
       bool(d.final.get('不适合')), str(d.final.get('不适合'))[:60])
    ok('C8 覆盖率照实记（"2/2 批"这种，不是一句"读完了"）',
       '/' in d.coverage and d.batches_all > 0, d.coverage)
    ok('C9 没有意外时 notes 是空的（**不许无端记账** —— 那会让人以为出了问题）',
       not d.notes, str(d.notes))

    # ★★ 拿不到结果时**照实记账**（不许静默降级）
    # [EN] ★★ When results cannot be obtained, **record it faithfully** (no silent degradation)
    import llm.replies as REP
    _orig = REP.ask

    async def _dead(tier, messages, **kw):
        raise RuntimeError('故意失败（判据）')
    A.ask = _dead
    try:
        d2 = asyncio.run(A.run(str(p), A.Brief(title='坏书')))
        ok('C10 ★★★ 模型全程拿不到结果时**照实记账**，'
           '并明说"这本书是跳着读的"（不许静默降级成一份看着完整的报告）',
           bool(d2.notes) and not d2.ok, f'notes={len(d2.notes)} ok={d2.ok}')
        ok('C11 ★★ 那种情况下 `ok` 是 False（调用方据此决定要不要写技能包）',
           d2.ok is False, '')
    finally:
        A.ask = _orig

    # 写技能包
    # [EN] Writing skill packs
    w = SG.write(d, root=tmp / 'skills')
    ok('D1 ★★ 技能包写出三份（SKILL.md 给程序 / digest.json 结构化 / '
       '拆书记录.md 给人）—— 一个包自包含',
       (w.dir / 'SKILL.md').is_file() and (w.dir / 'digest.json').is_file()
       and (w.dir / '拆书记录.md').is_file(),
       str(sorted(f.name for f in w.dir.iterdir())))
    md = w.skill_md.read_text(encoding='utf-8')
    # ★★ frontmatter 的键要**锚在行首**（`^名称:`）——
    #   第一版写 `'适用类型:' in md`，于是把键改成 `_砍掉适用类型:` 时
    #   **仍然是它的子串**，判据照样绿（反例法第 ⑩ 组当场抓到）。
    #   比"有没有这个子串"更强的问法是"**frontmatter 里有没有这一行**"。
    # [EN] ★★ frontmatter keys must be **anchored at line start** (`^name:`).
    # [EN] The first version wrote `'applicable_type:' in md`, so when the key was changed to
    # [EN] `_removed_applicable_type:`,
    # [EN] **it was still a substring of it**, and the criterion stayed green (caught on the spot by
    # [EN] counterexample group 10).
    # [EN] A stronger question than "does this substring exist" is "**does this line exist in the
    # [EN] frontmatter**".
    import re as _re
    _blocks = md.split('---')
    _fm = _blocks[1] if len(_blocks) >= 3 else md

    def _has_key(k: str) -> bool:
        return bool(_re.search(rf'^{_re.escape(k)}:', _fm, _re.MULTILINE))

    ok('D2 ★★ frontmatter 里有 registry 认的必须字段'
       '（名称/触发关键词/用途）—— 键要**在行首**，'
       '不是"哪一句里出现过这几个字"',
       all(_has_key(k) for k in ('名称', '触发关键词', '用途')), '')
    ok('D3 ★★ frontmatter 里有**给匹配用的**两个新字段'
       '（适用类型 / 特点）—— 没有它们，它是"知识"不是"同类经验"',
       _has_key('适用类型') and _has_key('特点'), '')
    ok('D4 ★ 分类是"拆书经验"（与人写的考据技能分得开）',
       '分类: 拆书经验' in md, '')
    ok('D5 ★ 触发关键词含书名与类型（同类书找得到）',
       '测试书' in md and '悬疑' in md, '')
    ok('D6 ★★ 正文里的模块与 digest 一致（不是两份各说各话）',
       all(str(m['名称']) in md for m in d.modules), '')
    # ★ 2026-10-10 改判：目录从 `skills/书拆·<书名>/`（一级）改成
    #   `skills/book-dismantle/<书名>/`（两级）—— 用户原话「放到 skills 下的拆书
    #   （**用拆书的英语翻译作为文件夹名字**）」。拆书产出的技能会在 `skills/` 下
    #   一本一份地长出来，全铺在一级会把 `skills/` 变成一堆书名。
    # [EN] ★ 2026-10-10 re-judgment: the directory was changed from `skills/book-dismantle·<book title>/`
    # [EN] (one level) to
    # [EN] `skills/book-dismantle/<book title>/` (two levels) -- the user's own words "put it under skills
    # [EN] for book dismantling
    # [EN] (**use the English translation of book-dismantling as the folder name**)". Skills produced by
    # [EN] book dismantling will grow under `skills/`
    # [EN] one per book; laying them all flat at the top level would turn `skills/` into a pile of book
    # [EN] titles.
    ok('D7 ★★ 目录是 `skills/book-dismantle/<书名>/`（**两级**，'
       '`book-dismantle` 是"拆书"的英文目录名）',
       w.dir.parent.name == SG.BOOK_DIR and w.dir.name == '测试书', 
       w.dir.as_posix())

    # ★★ 2026-10-10 改判：同名再拆 = **更新那一份**，不再进 v2。
    #   用户原话：「每拆一本书，就看下有类似 skill 存在吗？如果有就**强化更新**，
    #   没有就创建」。旧行为（同名进 v2）会让同一本书越拆越多份，
    #   而"更新"才是用户要的（重新拆过 = 更了解这本书了）。
    # [EN] ★★ 2026-10-10 re-judgment: dismantling a same-named book again = **update that one copy**, no
    # [EN] longer go to v2.
    # [EN] The user's own words: "Each time you dismantle a book, check whether a similar skill already
    # [EN] exists. If it does, **strengthen and update** it;
    # [EN] if not, create it." The old behavior (same name goes to v2) would make the same book multiply
    # [EN] with each dismantling,
    # [EN] whereas "update" is what the user wants (re-dismantling = knowing this book better).
    w2 = SG.write(d, root=tmp / 'skills')
    ndirs = [p.name for p in (tmp / 'skills' / SG.BOOK_DIR).iterdir()]
    ok('D8 ★★★ 同名再拆一次 = **更新同一份**，不新开 v2'
       '（用户点名要的行为；旧判据钉的是"进 v2"，那一条已按用户要求改掉）',
       w2.dir == w.dir and w2.action == 'update' and len(ndirs) == 1,
       f'{w.dir.name} / {w2.dir.name} · action={w2.action} · 目录={ndirs}')
    ok('D9 非法字符不进目录名（书名带 / : * 也不炸）',
       SG.safe_name('某书/第一:部*') == '某书第一部', SG.safe_name('某书/第一:部*'))
    ok('D10 空书名照样能写（拆都拆完了，因为没填名字就丢掉成果最坏）',
       bool(SG.safe_name('')), SG.safe_name(''))

    # ★★ 版权：产物里不许有成段引用（写的是做法）
    # ⚠ 2026-10-10：**`notes` 那几行要排除** —— 它们是"照实记的说明"
    #   （比如"这几条缺门禁字段"），里面本来就可能出现「」。
    #   第一版没排除，于是 mock 补了门禁字段之后 notes 一非空就把它判成"引用原文"。
    # [EN] ★★ Copyright: the output must not contain block quotations (write the method)
    # [EN] ⚠ 2026-10-10: **the `notes` lines must be excluded** -- they are "faithfully recorded
    # [EN] explanations"
    # [EN] (e.g. "these entries lack gating fields"), which may inherently contain 「」.
    # [EN] The first version did not exclude them, so once mock added the gating fields and notes became
    # [EN] non-empty, it judged them as "quoting the original text".
    quotes = [ln for ln in md.splitlines()
              if ln.startswith('>') is False and len(ln) > 80 and '「' in ln
              and ln.count('」') >= 1 and '怎么做' not in ln and '**' not in ln
              and '- 这些模块卡' not in ln]
    ok('D11 ★★ 产物写的是**做法**，没有问题里的成段引用'
       '（版权红线：只学方法，不搬原文）', not quotes, str(quotes[:1])[:90])
    return d, w


# ══════════════════════════════════════════════════════════════
#  E 拆书库与匹配
# [EN] E Book library and matching
# ══════════════════════════════════════════════════════════════
def test_store(tmp: Path, written) -> None:
    from booklab import store as ST
    _d, w = written
    # ★ 2026-10-10：包在两级下（`skills/book-dismantle/<书名>/`），
    #   所以"技能根"要往上退**两层** —— 退一层会得到 `book-dismantle/`，
    #   而 `list_packs` 会在它底下再拼一次 `book-dismantle/` ⇒ 一份都找不到。
    # [EN] ★ 2026-10-10: the pack sits two levels down (`skills/book-dismantle/<book title>/`),
    # [EN] so the "skill root" must go up **two levels** -- going up one level yields `book-dismantle/`,
    # [EN] and `list_packs` will append `book-dismantle/` again underneath it => not a single pack is
    # [EN] found.
    root = w.dir.parent.parent

    packs = ST.list_packs(root)
    ok('E1 ★ 拆书库读得回来（从 digest.json）', len(packs) >= 1,
       str([p.title for p in packs]))
    ok('E2 ★ 读回来的包记得自己有几个模块',
       bool(packs) and packs[0].modules and all(m.get('名称') for m in packs[0].modules), '')

    # ★★★ 类型匹配：**同题材两种叫法也要配上**
    #   （当前书的类型卡写「悬疑灵异」，拆的那本标「悬疑·单元剧」——
    #    谁也不包含谁。第一版用"互相包含"判，于是这一档永远不命中。）
    # [EN] ★★★ Type matching: **two names for the same genre must also match**
    # [EN] (the current book's genre card says "suspense/paranormal", while the dismantled book is labeled
    # [EN] "suspense · anthology drama" --
    # [EN] neither contains the other. The first version judged by "mutual containment", so this tier never
    # [EN] matched.)
    card = {'类型': '悬疑灵异', '钩子库': ['反常细节', '未解之谜'],
            '冲突偏好': {'主引擎': '未知 vs 秩序'}}
    hit = ST.match(card, packs)
    ok('E3 ★★★ 类型匹配认得"同题材的两种叫法"'
       '（悬疑灵异 ↔ 悬疑·单元剧 —— 用"互相包含"判就永远配不上，'
       '拆书库里的东西一本都用不上）',
       bool(hit) and '悬疑' in (hit[0].hit or ''), str([(p.title, p.hit) for p in hit]))
    ok('E4 ★★ 命中的理由说得出来（不是"相似度 0.73"这种没法解释的数）',
       bool(hit and hit[0].hit), hit[0].hit if hit else '')
    ok('E5 ★★ 类型对不上时**不用**（硬塞一本言情的写法进悬疑，比不用更坏）',
       not ST.match({'类型': '言情', '钩子库': ['甜蜜暴击']}, packs), '')
    ok('E6 ★★ 作者问的问题里出现模块名时，也把它想起来',
       bool(ST.match({'类型': '言情'}, packs, question='钩子怎么留')),
       str([(p.title, p.hit) for p in ST.match({'类型': '言情'}, packs,
                                               question='钩子怎么留')]))
    ok('E7 ★ 中文公共片段匹配是对的（"钩子要具体" vs "钩子怎么留" 命中）',
       ST._shares_word('钩子要具体', '钩子怎么留'), '')
    ok('E8 ★ 不同题材不误命中（"言情" vs "悬疑灵异"）',
       not ST._shares_word('言情', '悬疑灵异'), '')

    # 渲染
    # [EN] Rendering
    a = ST.for_agents(card, packs=packs)
    wr = ST.for_writers(card, packs=packs)
    ok('E9 ★★ 给所有职位的是**压缩版**（只有模块名与怎么做）',
       '同类书的写法' in a and '不要照搬' not in a, a[:60])
    ok('E10 ★★ 给三人小组的是**完整版**（多出节奏/立人/文风/不要照搬）',
       '不要照搬' in wr and '节奏' in wr, wr[-120:])
    ok('E11 ★★ 完整版那时也带一句"照不照用由这一场戏自己定"'
       '（别的书的做法是**参考**，不是命令）',
       '自己定' in wr, '')
    ok('E12 没匹配上时返回空串（不硬塞）',
       ST.for_agents({'类型': '言情'}, packs=packs) == '', '')
    # ★★ 字数上限：**得拿一份足够长的包来量**，而且**要长到真的超过上限**。
    #   第一版拿真拆出来的那个包量（三个模块），它渲染出来本来就短于上限 ——
    #   把上限去掉判据照样绿（反例法第 ⑭ 组抓到）。
    #   第二版造了长包但**还不够长**（4 模块 × 132 字 ≈ 530 < 900），
    #   于是还是不红。现在每段都写到 480 字，四条就远超上限了。
    # [EN] ★★ Word-count cap: **must measure with a pack long enough**, and **long enough to actually
    # [EN] exceed the cap**.
    # [EN] The first version measured the pack actually produced by dismantling (three modules); what it
    # [EN] rendered was inherently shorter than the cap --
    # [EN] removing the cap would still leave the criterion green (caught by counterexample group 14).
    # [EN] The second version built a long pack but **not long enough** (4 modules × 132 chars ≈ 530 <
    # [EN] 900),
    # [EN] so it still would not turn red. Now each section is written to 480 chars, so four of them far
    # [EN] exceed the cap.
    _long = '这是一条很长的做法说明，用来确认上限真的在起作用。' * 22
    long_pack = ST.Pack(
        dir=Path('.'), name='书拆·长包', brief={'title': '长包', 'genre': '悬疑'},
        modules=[{'名称': f'写法{i}', '怎么做': _long, '什么时候用': _long}
                 for i in range(8)],
        final={'节奏': _long, '人设': _long, '语言': _long, '不适合': [_long]})
    la = ST.for_agents({'类型': '悬疑'}, packs=[long_pack])
    lw = ST.for_writers({'类型': '悬疑'}, packs=[long_pack])
    # 先确认这份假包**真的够长**（否则判据是恒真的：拿短内容量上限永远过）
    # [EN] First confirm this fake pack **is really long enough** (otherwise the criterion is always true:
    # [EN] measuring the cap with short content always passes)
    ok('E13a ★★ 量上限用的假包本身**超过了上限**'
       '（拿短内容量上限是恒真的 —— 这条是给下一条兜底）',
       len(la) >= ST.AGENT_CHARS or len(lw) >= ST.WRITER_CHARS,
       f'压缩版 {len(la)} / 完整版 {len(lw)}')
    ok('E13 ★★ 两版都有字数上限，而且**超长的包真的被截**'
       '（不设上限会把演员的上下文挤掉）',
       len(la) <= ST.AGENT_CHARS + 10 and len(lw) <= ST.WRITER_CHARS + 10,
       f'{len(la)} / {len(lw)}')

    t = ST.table_md(card, packs)
    ok('E14 ★ 《本书可参考的写法》写了"凭什么用它"'
       '（作者要能核对，不能只有一句"智能匹配"）',
       '为什么用它' in t and ('类型相符' in t or '关键词' in t), '')
    ok('E15 库里空着时也照实说，并指出下一步怎么做（不留空白页）',
       '还没有东西' in ST.table_md(card, []), '')


# ══════════════════════════════════════════════════════════════
#  F 接线（行为级）
# [EN] F Wiring (behavior level)
# ══════════════════════════════════════════════════════════════
def test_wiring(tmp: Path, written) -> None:
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    from craft import craftmix
    from crew import agents as AG

    _d, w = written
    # ★ 让产品**从我们造的库**里取（改 CFG，不 monkey-patch 产品函数）
    # ⚠ 2026-10-10：包在两级下（`skills/book-dismantle/<书名>/`），
    #   `SKILLS_DIR` 要指**技能根**（`skills/`）—— 指成 `book-dismantle/`
    #   会让 `list_packs` 再拼一层，一份都找不到，于是四人全判"拿不到经验"。
    #   ★ 这个"两层 vs 一层"的语义我这轮**踩了三次**（write / test_store / 这里），
    #     所以现在有一条判据专门钉它（I7b）。
    # [EN] ★ Make the product pull **from the library we built** (change CFG, do not monkey-patch product
    # [EN] functions)
    # [EN] ⚠ 2026-10-10: the pack sits two levels down (`skills/book-dismantle/<book title>/`),
    # [EN] `SKILLS_DIR` must point to the **skill root** (`skills/`) -- pointing it at `book-dismantle/`
    # [EN] will make `list_packs` append another level, so not a single pack is found, and all four people
    # [EN] are judged as "cannot obtain experience".
    # [EN] ★ This "two levels vs one level" semantics **tripped me three times** this round (write /
    # [EN] test_store / here),
    # [EN] so there is now a criterion specifically pinning it (I7b).
    _save = CFG.raw('SKILLS_DIR')
    CFG.set('SKILLS_DIR', str(w.dir.parent.parent))
    try:
        proj = make_project(tmp / '夹具', nodes=3)
        run = RunFolder(proj.root, '第1次模拟2026-10-07-17-30').create()
        loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
        world.genre_card = dict(craftmix.card('悬疑灵异') or {})
        from crew import profile as PROF
        PROF.attach(world)
        AG.bind_world(world)

        three = ('novelist', 'screenwriter', 'director', 'settings_room')
        others = ('continuity', 'props', 'polisher', 'actor')
        for k in three:
            blk = AG.craft_block(k, '悬疑灵异', '单元剧')
            ok(f'F·{k} ★★★ 三人小组拿得到拆书经验，而且是**完整版**',
               '同类书的写法' in blk and '不要照搬' in blk,
               f'有经验={"同类书的写法" in blk} 完整={"不要照搬" in blk}')
        miss = []
        for k in others:
            blk = AG.craft_block(k, '悬疑灵异', '单元剧')
            if '同类书的写法' not in blk or '不要照搬' in blk:
                miss.append((k, '同类书的写法' in blk, '不要照搬' in blk))
        ok('F·others ★★ 其它职位拿得到**压缩版**（有经验但不给节奏/立人那几段）',
           not miss, str(miss))

        # 类型对不上 → 谁都不该拿到
        # [EN] Type mismatch -> nobody should get it
        world.genre_card = {'类型': '言情'}
        blk = AG.craft_block('screenwriter', '言情', '')
        ok('F·nomatch ★★ 类型对不上时**一个职位也不拿到**'
           '（不硬塞 —— 这是"引用经验"最容易翻车的地方）',
           '同类书的写法' not in blk, blk[:50])

        # 落盘
        # [EN] Persistence
        world.genre_card = dict(craftmix.card('悬疑灵异') or {})
        PROF.attach(world)
        _rows = list(getattr(world, '_casts', None) or [])
        from actors import casting as CASTING
        if not _rows:
            _rows = [CASTING.instantiate(n, {}) for n in world.people]
        (run.root / '本书可参考的写法.md').write_text(
            __import__('booklab.store', fromlist=['x']).table_md(
                world.genre_card), encoding='utf-8')
        ok('F·file ★★ 运行文件夹里有《本书可参考的写法.md》'
           '（作者能核对"用了哪几份、凭什么"）',
           (run.root / '本书可参考的写法.md').is_file(), '')

        # ★ 导演那条路（不走 craft_block 的位置也要有）
        # [EN] ★ The director path (the position that does not go through craft_block must also exist)
        from director import day_plan as DP
        ok('F·director ★★ 导演验算的提示词里有手艺那一段的占位符'
           '（`_VERIFY_PROMPT` 里那个 {craft} —— 没有它，'
           '导演这条路上接的东西进不去）',
           '{craft}' in DP._VERIFY_PROMPT, '')
    finally:
        if _save is not None:
            CFG.set('SKILLS_DIR', _save)


# ══════════════════════════════════════════════════════════════
#  G 菜单与真机
# [EN] G Menu and real device
# ══════════════════════════════════════════════════════════════
def test_menu() -> None:
    src = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    # ⚠ 2026-10-10：菜单那一行整体换了两次图标（emoji → 单色矢量 → **彩色位图**），
    #   所以这条断言也跟着改。**认的仍然是"菜单那一整行"**，
    #   不是"源码里出现过这几个字" —— `t('拆　书')` 在对话框标题那儿也有一处，
    #   只看字面的话，菜单项被删掉都能蒙混过去。
    #   图像 = **拼图**（槽位 `img:puzzle`），用户 2026-10-10 点名要的那个。
    #   ⚠ 图对不对、挂没挂上，由 `tools/verify_menu_icons.py`（素材）与
    #     `tools/verify_resume_menu.py`（真机渲染）钉，这里只管菜单项还在。
    # [EN] ⚠ 2026-10-10: the menu line as a whole changed icons twice (emoji -> monochrome vector ->
    # [EN] **color bitmap**),
    # [EN] so this assertion changed accordingly. **What is recognized is still "the whole menu line"**,
    # [EN] not "these characters appear somewhere in the source" -- `t('dismantle book')` also appears once
    # [EN] at the dialog title;
    # [EN] if you only look at the literal, deleting the menu item could still slip through.
    # [EN] Image = **puzzle** (slot `img:puzzle`), the one the user specifically named on 2026-10-10.
    # [EN] ⚠ Whether the image is correct and whether it is attached is pinned by
    # [EN] `tools/verify_menu_icons.py` (assets) and
    # [EN] `tools/verify_resume_menu.py` (real-device rendering); here we only care that the menu item
    # [EN] still exists.
    ok('G1 ★★ 开始菜单里有「拆　书」那一项（图像是拼图 `img:puzzle`）'
       '（认的是**菜单那一整行**）',
       ("('img:puzzle', t('拆　书'), t('读一本好书，学写法'), "
        "self._on_booklab, True)") in src, '')
    ok('G2 ★★ 菜单那一项**恒可点**（手上还没有自己的书时，'
       '正好可以先拆一本别人的学写法）',
       "'img:puzzle'" in src and 'self._on_booklab, True' in src, '')
    ok('G3 ★ 有对话框与四个问题的接线',
       'def show_booklab_dialog' in src and 'questions_text' in src, '')
    ok('G4 ★★ 对话框里选文件那条路取的是 `.path`'
       '（`pick_files` 返回**对象列表**不是字符串 —— '
       '按字符串写会静默拿到空串，用户点了文件却提示"还没选书"）',
       "getattr(first, 'path', '')" in src, '')
    ok('G5 ★★ 拆完**自动写**进技能库并重载注册表'
       '（不重载的话，刚拆完在同一个会话里看不到新技能）',
       'BS.write(d)' in src and 'reload_registry' in src, '')
    ok('G6 用 `create_task` 跑（不阻塞界面；几十次调用要等很久）',
       'asyncio.create_task(_run())' in src, '')
    # ★★ 2026-10-10 改：来源改成**四选一、互斥**之后，旧锚点 `if not st['path']`
    #   与文案 `先选一本书` 都不在了（那个门守的是"网址优先"的旧逻辑）。
    #   门现在是 `if not src_st['mode']:`，而且**分两段报错**：
    #   "一个都没选"与"选了网址但没填"是两回事 —— 所以这条判据也拆成两问。
    # [EN] ★★ 2026-10-10 change: after the source was changed to **one of four, mutually exclusive**, the
    # [EN] old anchor `if not st['path']`
    # [EN] and the text `select a book first` are both gone (that gate guarded the old "URL first" logic).
    # [EN] The gate is now `if not src_st['mode']:`, and **errors are reported in two stages**:
    # [EN] "none selected" and "URL selected but not filled in" are two different things -- so this
    # [EN] criterion is also split into two questions.
    ok('G7 ★★ 开跑前检查有没有选来源（没选就说，不是静默不动），'
       '而且**分得清**"一个都没选"与"选了网址但没填"',
       "if not src_st['mode']" in src and '先选一本书：文件' in src
       and 'if not _resolve_src()' in src and '网址还空着' in src, '')
    ok('G8 ★ 关掉总开关时明说被关了（不是"点了没反应"）',
       "CFG.b('BOOKLAB_ENABLED')" in src and '被关掉了' in src, '')

    # ★★★ **名字解析**（2026-10-07）：`ast` 过一遍 —— "被**调用**的光杆名字，
    #   在本模块里必须找得到定义"。
    # [EN] ★★★ **Name resolution** (2026-10-07): run `ast` once -- "a bare name that is **called**
    # [EN] must have a definition findable in this module".
    #
    #   为什么补这一条：改名那一轮在 `_booklab_body` 里留过一个
    #   `_booklab_report(w.dir)` —— **只被调用、从未定义**。它藏在
    #   `lambda e: …` 里，"对话刚打开时"根本不会求值，所以点「看××记录」
    #   才会 NameError；而 G1~G8 那些**查字符串在不在**的哨兵，
    #   原理上就抓不住"名字没定义"这件事（字面量在源码里躺着，好好的）。
    # [EN] Why add this: during the renaming round, one was left in `_booklab_body`
    # [EN] `_booklab_report(w.dir)` —— **only ever called, never defined**. It is hidden in
    # [EN] `lambda e: …`, and is not evaluated at all "when the dialog is first opened", so only when
    # [EN] clicking "view xx record"
    # [EN] does NameError occur; while the G1~G8 sentinels that **check whether a string is present**
    # [EN] in principle cannot catch "the name is not defined" (the literal just sits there in the source,
    # [EN] fine and well).
    #
    #   ⚠ 口径刻意**保守**：凡是任何作用域里出现过绑定的名字都算"有定义"
    #     （宁可漏报，不要误报）。它挡的是"整个模块里就没这个名字"。
    # [EN] ⚠ The criterion is deliberately **conservative**: any name bound in any scope counts as
    # [EN] "defined"
    # [EN] (better to miss a report than a false positive). What it guards against is "this name does not
    # [EN] exist in the whole module".
    import ast as _ast
    import builtins as _bi
    _tree = _ast.parse(src)
    _defined: set[str] = set()
    for _n in _ast.walk(_tree):
        if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            _defined.add(_n.name)
        elif isinstance(_n, _ast.Name) and isinstance(_n.ctx, _ast.Store):
            _defined.add(_n.id)
        elif isinstance(_n, _ast.arg):
            _defined.add(_n.arg)
        elif isinstance(_n, _ast.Import):
            for _a in _n.names:
                _defined.add(_a.asname or _a.name.split('.')[0])
        elif isinstance(_n, _ast.ImportFrom):
            for _a in _n.names:
                if _a.name != '*':
                    _defined.add(_a.asname or _a.name)
    _dangling = sorted({
        _n.func.id for _n in _ast.walk(_tree)
        if isinstance(_n, _ast.Call) and isinstance(_n.func, _ast.Name)
        and _n.func.id not in _defined and not hasattr(_bi, _n.func.id)})
    ok('G9 ★★★ 被**调用**的名字都能在本模块找到定义'
       '（`_booklab_report` 那次断链就是栽在这 —— 查字符串的哨兵看不见它）',
       not _dangling, f'没定义就被调用：{_dangling}')


# ══════════════════════════════════════════════════════════════
#  H 真机：对话框真能打开（源码判据守不住"运行时炸了"）
# [EN] H real machine: the dialog really opens (source-level criteria cannot hold "it blew up at
# [EN] runtime")
# ══════════════════════════════════════════════════════════════
#: 四个"从哪儿读"的来源按钮（互斥的一组；用户 2026-10-10 要求）。
#: `mk_btn` 把**主按钮**做成 `FilledButton`、**次按钮**做成 `TextButton` ——
#: 所以"哪个是实心的"就是"当前选中的哪个"，判据靠**类型**分辨（不判颜色：
#: 颜色随配色方案变，而"是哪种按钮"就是互斥的语义本身）。
# [EN] : four "where to read from" source buttons (a mutually exclusive group; user requested
# [EN] 2026-10-10).
# [EN] : `mk_btn` makes the **primary button** a `FilledButton` and the **secondary button** a
# [EN] `TextButton` ——
# [EN] : so "which one is solid" is "which one is currently selected", and the criterion distinguishes
# [EN] by **type** (not by color:
# [EN] : color changes with the color scheme, whereas "which kind of button it is" is precisely the
# [EN] mutually exclusive semantics itself).
SRC_LABELS = ['选一个文件', '选一个文件夹', '网址', '用 sample 测试']


async def test_gui(page) -> None:
    # ⚠ `flet` 只在这条真机路径上才用得到（模块顶上没有 import flet —— 那一半是
    #   纯逻辑判据，不该把 GUI 依赖抬到模块级）。H4~H6 要判按钮的**类型**
    #   （FilledButton / TextButton），所以在这儿把它拿进来。
    # [EN] ⚠ `flet` is only needed on this real machine path (there is no import flet at the top of the
    # [EN] module —— that half is
    # [EN] pure logic criteria and should not lift the GUI dependency to module level). H4~H6 need to check
    # [EN] the button **type**
    # [EN] (FilledButton / TextButton), so bring it in here.
    import flet as ft
    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp, booklab_start_visible

    # ★★★ 2026-10-14（用户）：「拆书的开始拆 3个字移动到关闭按钮的左边
    #   而不是在里面」—— 按钮从**内容区**搬到了对话框底部的**动作栏**，
    #   于是它**常驻**了：必须自己回答"什么时候该亮"。
    #   这里**行为判**（喂三种 `st` 看返回），不去比"源码里含某个表达式" ——
    #   后者会被注释 / `if False` 骗过去（本项目明令禁止）。
    # [EN] ★★★ 2026-10-14 (user): "move the 3 characters 开始拆 to the left of the close
    # [EN] button, not inside it" -- the button moved from the **content area** to the dialog's
    # [EN] bottom **action bar**, so it now **lives permanently**: it must answer "when should it
    # [EN] light up" itself.
    # [EN] Judged **behaviorally** here (feed three kinds of `st`, look at the return) rather than
    # [EN] comparing "the source contains some expression" -- the latter can be fooled by comments /
    # [EN] `if False` (explicitly forbidden in this project).
    ok('G10 ★★★ 「开 始 拆」只在**填四问**那一段亮着'
       '（跑起来 / 出了结果都隐去 —— 搬进常驻的动作栏之后，这件事得自己管，'
       '否则运行中还能再点一次、重复起一次拆书）',
       booklab_start_visible({'busy': True, 'digest': None}) is False
       and booklab_start_visible({'busy': False, 'digest': object()}) is False
       and booklab_start_visible({'busy': False, 'digest': None}) is True, '')

    tmp = Path(tempfile.mkdtemp(prefix='nws_blgui_'))
    try:
        VU.isolate_projects_dir(tmp / 'Projects')
        app = NovelWorldApp()
        app.main(page)
        # 截图要先开开关（不开时 `take_screenshot()` 返回空 —— 会是 0 字节文件，
        # 而那看起来像"截图坏了"）
        # [EN] For screenshots you must turn the switch on first (when off, `take_screenshot()` returns empty
        # [EN] —— it would be a 0-byte file,
        # [EN] and that looks like "the screenshot is broken")
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.5)

        # ⚠ 取文字要走 `all_texts`（`text_of` 对 `ft.Text` 返回空 ——
        #   它读 `.content`，而 Text 的字在 `.value` 上）。
        # [EN] ⚠ To get text you must go through `all_texts` (`text_of` returns empty for `ft.Text` ——
        # [EN] it reads `.content`, whereas Text's characters are on `.value`).
        menu = VU.all_texts(page)
        # ⚠ 匹配用**宽松的"含拆且含书"**，不比整串：菜单项里是「拆　书」——
        #   中间那个是全角空格（U+3000），直接比 `'拆书' in x` 会漏掉它。
        # [EN] ⚠ For matching use the **loose "contains 拆 and contains 书"**, not the whole string: the menu
        # [EN] item is "拆 书" ——
        # [EN] the character in the middle is a full-width space (U+3000), comparing directly with `'拆书' in x`
        # [EN] will miss it.
        ok('H1 ★★ 开始菜单里真的有「拆　书」那一项（真机，不是源码里有）',
           any('拆' in x and '书' in x for x in menu),
           str([x for x in menu if '拆' in x][:3]))

        app.show_booklab_dialog()
        await asyncio.sleep(1.0)
        # ⚠ 对话框是**浮层**（挂在 `page._dialogs`），不在 `page.controls` 里 ——
        #   遍历错地方会得到"什么都没找到"，而那看着像"对话框没打开"。
        # [EN] ⚠ The dialog is an **overlay** (attached to `page._dialogs`), not in `page.controls` ——
        # [EN] traversing the wrong place yields "found nothing", and that looks like "the dialog did not
        # [EN] open".
        dlgs = getattr(page, '_dialogs', None)
        root = dlgs if dlgs is not None else page
        labels = VU.all_texts(root)
        need = ('这本书叫什么', '它是什么类型', '你觉得它哪些地方好', '想重点拆什么')
        miss = [k for k in need if not any(k in x for x in labels)]
        ok('H2 ★★★ 拆书对话框真的打开了，而且**四个问题都在**'
           '（用户点名要问的那四件）', not miss, f'缺：{miss}')
        ok('H3 ★★ 「开 始 拆」与「选一个文件/文件夹」按钮都在',
           any('开 始 拆' in x for x in labels)
           and any('选一个文件' in x for x in labels), '')

        # ── H3b/H3c：位置（用户 2026-10-14「拆书的开始拆 3个字移动到关闭按钮的
        #    左边 而不是在里面」）──
        #   ★ 必须**真机**判"在哪"：源码级的锚点只能证明"某行代码写在那儿"，
        #     证明不了"打开对话框之后它真的落在动作栏里"（`AlertDialog.actions`
        #     是 Flet 的浮层结构，画在哪儿由 Flet 决定）。
        #   ⚠ 顺序 = `actions` 列表顺序（Flet 自己排成一行靠右）⇒ 比**下标**，
        #     不比坐标 —— 比坐标会随窗口宽度/配色漂移。
        # [EN] ── H3b/H3c: position (user 2026-10-14) ──
        # [EN] ★ Must be judged **on the real machine**: source-level anchors can only prove "a line
        # [EN] of code is written there", not "after opening the dialog it really lands in the action
        # [EN] bar" (`AlertDialog.actions` is a Flet overlay structure; where it is drawn is up to Flet).
        # [EN] ⚠ Order = the `actions` list order (Flet lays them out in one right-aligned row) => compare
        # [EN] **indices**, not coordinates -- coordinates drift with window width / palette.
        _dlg = (VU.open_dialogs(page) or [None])[-1]
        _acts = list(getattr(_dlg, 'actions', None) or [])
        _act_labels = [' '.join(VU.all_texts(a)) for a in _acts]
        _i_start = next((i for i, s in enumerate(_act_labels)
                         if '开 始 拆' in s), -1)
        _i_close = next((i for i, s in enumerate(_act_labels)
                         if '关闭' in s), -1)
        ok('H3b ★★★ 「开 始 拆」就在对话框底部的**动作栏**里，'
           '而且排在「关闭」**左边**',
           _i_start >= 0 and _i_close >= 0 and _i_start < _i_close,
           f'动作栏 = {_act_labels}')
        _inside = VU.all_texts(getattr(_dlg, 'content', None))
        ok('H3c ★★★ 「开 始 拆」**不在内容区里**（用户："而不是在里面"）'
           '（成对：还得在动作栏里 —— 否则"两边都没有"也想过）',
           not any('开 始 拆' in x for x in _inside) and _i_start >= 0,
           f'内容区里冒出来：{[x for x in _inside if "开 始 拆" in x]}')

        # ══════════════════════════════════════════════════════════
        #  H4~H6：**来源四选一、互斥**（用户 2026-10-10）
        #  「把网址移动到下面，可以改成一个名字叫网址的按钮，点了之后输入网址。
        #    而且你要让这几个选项互斥，只能够选择一个」
        # [EN] H4~H6: **one of four sources, mutually exclusive** (user 2026-10-10)
        # [EN] "Move the URL below, you can change it to a button named URL, and after clicking it you input
        # [EN] the URL.
        # [EN] And you have to make these options mutually exclusive, only one can be selected"
        #
        #  ★★ 为什么这三条必须**真机**：源码级的 E8b~E8e 只能证明"代码里写着
        #    那个 `if`"，证明不了"点下去真的会变"。而这一改的核心恰恰是
        #    **点下去会怎样** —— 所以要在真机上把按钮**真点一下**，
        #    再看控件树里发生了什么。
        # [EN] ★★ Why these three must be **real machine**: source-level E8b~E8e can only prove "the code says
        # [EN] that `if`", they cannot prove "clicking it really changes it". And the core of this change is
        # [EN] precisely
        # [EN] **what happens when you click** —— so on the real machine you must **really click** the button,
        # [EN] then look at what happened in the control tree.
        #
        #  ⚠ 只点「网址」这一个：点「选一个文件」会拉起**系统文件选择器**，
        #    那个要人操作，自动化里会一直挂着（`_pick_url` 只切模式，不弹东西）。
        # [EN] which needs a human to operate and will hang forever in automation (`_pick_url` only switches
        # [EN] modes, pops up nothing).
        # ══════════════════════════════════════════════════════════

        def _dialogs_root():
            d = getattr(page, '_dialogs', None)
            return d if d is not None else page

        def _src_buttons():
            """四个来源按钮 → `{标签: 控件}`（`mk_btn` 主按钮是 FilledButton，
            次按钮是 TextButton，都是 `content=Text(标签)`）。

            ⚠ `VU.walk` 是个**生成器**（`yield`），不是"往列表里塞"的写法 ——
              写成 `VU.walk(root, out)` 会静默什么都不收到（多一个位置参数
              直接 TypeError，反而看得见；这里记一笔免得下次踩）。
            
                        English:
            Four source buttons → `{label: control}` (`mk_btn`'s primary button is a FilledButton,
                        the secondary button is a TextButton, both with `content=Text(label)`).
                        ⚠ `VU.walk` is a **generator** (`yield`), not a "stuff into a list" style —
                          writing `VU.walk(root, out)` silently collects nothing (an extra positional argument
                          gives TypeError immediately, which is at least visible; noting it here so we don't step on it next time).
            """
            got = {}
            for c in VU.walk(_dialogs_root()):
                txt = getattr(c, 'content', None)
                if (isinstance(c, (ft.FilledButton, ft.TextButton))
                        and isinstance(txt, ft.Text) and txt.value in SRC_LABELS):
                    got[txt.value] = c
            return got

        def _filled(btns: dict) -> list:
            """哪些是**实心**的 —— 实心 = `FilledButton`（`mk_btn` 的 primary）。

            ★ 判类不判颜色：颜色会随配色方案变，而"是哪种按钮"就是互斥的语义本身。
            
                        English:
            Which ones are **solid** — solid = `FilledButton` (`mk_btn`'s primary).
                        ★ Judge the class, not the color: colors change with the color scheme, whereas "which kind of button it is" is the mutually exclusive semantic itself.
            """
            return [k for k, v in btns.items() if isinstance(v, ft.FilledButton)]

        # 每次用例前把来源清空（`_booklab_src` 挂在 `self` 上、跨次保留 —— 那是有意的，
        # 但测试要从"什么都没选"这个起点开始）。清完**重开一次对话框**拿新的 render()。
        # [EN] Before each test case clear the sources (`_booklab_src` is attached to `self` and persists
        # [EN] across runs —— that is intentional,
        # [EN] but tests must start from "nothing selected"). After clearing, **reopen the dialog** to get a
        # [EN] fresh render().
        app._booklab_src.update({'mode': '', 'path': ''})
        page.pop_dialog()
        app.show_booklab_dialog()
        await asyncio.sleep(0.8)

        btns0 = _src_buttons()
        ok('H4 ★★★ 四个来源按钮都在（选一个文件 / 选一个文件夹 / 网址 / samples）',
           len(btns0) == 4, f'找到 {sorted(btns0)}')

        def _has_url_field() -> bool:
            """那个网址输入框**现在在不在**对话框的控件树里。

            判"是不是**同一个控件对象**"（`is`），不判"有没有名字像网址的框"：
            `f['__url']` 是缓存的**同一个实例**，不在树上时它只是躺在 `_booklab_fields` 里，
            重新渲染后又挂回去 —— 用 `is` 才能分清这两种状态。
            
                        English:
            Whether that URL input box is **currently** in the dialog's control tree.
                        Judge "is it **the same control object**" (`is`), not "is there a box with a name like URL":
                        `f['__url']` is the cached **same instance**; when it's not in the tree it's just lying in `_booklab_fields`,
                        and after re-rendering it's attached again — only using `is` can distinguish these two states.
            """
            w = (app._booklab_fields or {}).get('__url')
            return w is not None and any(c is w for c in VU.walk(_dialogs_root()))

        ok('H4b ★★★ 一开始（什么都没选）主对话框里**没有**网址输入框'
           '（用户要的是"点了按钮才输入"：原来它常驻在下面，现在搬进弹窗了）',
           not _has_url_field(), '')

        ok('H4c ★★★ 一开始**没有一个来源是实心的**'
           '（"一个都没选"要看得见 —— 这正是互斥带来的好处）',
           _filled(btns0) == [], f'实心的：{_filled(btns0)}')

        # ── 四个按钮**排在同一行**（用户："保证在一行里显示出来"）──
        # ★ 判法用**结构**：找一个 `Row`，它的**直接子节点里四个都在**。
        #   ⚠ 一开始想判"它们的 `top`（布局后 Flet 会填）相等"，实测**全是 None**
        #     —— 这条路走不通（`Control.top` 只在被布局系统显式定位时才有值）。
        #     结构判法还更贴题意："在同一个 Row 里"就是"排在一行"，不依赖渲染细节。
        # [EN] ── The four buttons are **arranged in the same row** (user: "make sure they are displayed in one
        # [EN] row") ──
        # [EN] ★ Use **structure** as the criterion: find a `Row` whose **direct children include all four**.
        # [EN] ⚠ At first I wanted to check "their `top` (filled in by Flet after layout) are equal", but in
        # [EN] practice they are **all None**
        # [EN] —— that path does not work (`Control.top` only has a value when explicitly positioned by the
        # [EN] layout system).
        # [EN] The structural criterion also fits the requirement better: "in the same Row" is "arranged in one
        # [EN] row", not dependent on rendering details.
        def _row_of_four() -> list[str]:
            for c in VU.walk(_dialogs_root()):
                if not isinstance(c, ft.Row):
                    continue
                got = []
                for ch in (getattr(c, 'controls', None) or []):
                    txt = getattr(ch, 'content', None)
                    if (isinstance(ch, (ft.FilledButton, ft.TextButton))
                            and isinstance(txt, ft.Text) and txt.value in SRC_LABELS):
                        got.append(txt.value)
                if len(got) == 4:
                    return got
            return []

        _in_one_row = _row_of_four()
        ok('H4d ★★★ 四个按钮**在同一个 `Row` 里**（＝排在同一行，不会换行）'
           '（用户 2026-10-10："这几个按钮之间距离可以近一些 以保证在一行里显示出来"）',
           len(_in_one_row) == 4, f'同一行的按钮：{_in_one_row}')

        # ── 真点一下「网址」──
        # [EN] ── Really click "网址" ──
        url_btn = btns0.get('网址')
        # ★ 记**点之前**有几层真对话框：H5a 必须判"**多了一层**"，
        #   不能判"有一层" —— 主对话框本来就开着，那种判法**永远不会红**
        #   （实测被反例法 ⑲ 抓到：点「网址」什么也不弹，H5a 照样绿）。
        # [EN] ★ Record how many layers of real dialogs there are **before clicking**: H5a must check "**one
        # [EN] more layer**",
        # [EN] not "there is one layer" —— the main dialog is already open, that kind of criterion **never
        # [EN] turns red**
        # [EN] (in practice caught by counterexample method ⑲: clicking "网址" pops up nothing, yet H5a is still
        # [EN] green).
        n_before = len([d for d in VU.open_dialogs(page)
                        if isinstance(d, ft.AlertDialog)])
        clicked = False
        if url_btn is not None and url_btn.on_click is not None:
            url_btn.on_click(None)          # 只弹对话框，不拉系统选择器
            # [EN] Only pop up a dialog, do not bring up the system picker
            page.update()
            clicked = True
        await asyncio.sleep(0.5)

        # ── 点「网址」**弹出一个新对话框**（用户："弹出一个对话框 输入网址"）──
        # ⚠ 只算**真对话框**：`page._dialogs` 里 **SnackBar 也占一层**
        #   （`show_dialog(SnackBar(...))` 就是提示条的实现方式）——
        #   不过滤的话会拿到提示条，它的 `content` 是个 Text、没有 width/height。
        # [EN] ── Click "网址" to **pop up a new dialog** (user: "pop up a dialog to input the URL") ──
        # [EN] ⚠ Count only **real dialogs**: in `page._dialogs` **a SnackBar also occupies a layer**
        # [EN] (`show_dialog(SnackBar(...))` is exactly how the toast is implemented) ——
        # [EN] without filtering you would get the toast, whose `content` is a Text and has no width/height.
        dlgs_now = [d for d in VU.open_dialogs(page)
                    if isinstance(d, ft.AlertDialog)]
        ok('H5a ★★★ 点「网址」→ **多了一层对话框**（就是那个输入地址的）',
           clicked and len(dlgs_now) > n_before,
           f'点前 {n_before} 层 → 点后 {len(dlgs_now)} 层')

        # ── 那个弹窗的**尺寸**（用户 2026-10-10 下午："是不是太高了 但又太窄了"）──
        # 根因：`content` 传的是裸 `Column`（有 width、**没有 height**），
        # 而 `mk_dialog` 从 `content` 上读尺寸 ⇒ `ch=None` ⇒ 内层 `expand=True`
        # 把它**拉到接近满屏**（实测 1081px）；宽度那 440 也是自创的。
        # ⇒ 这条判据直接量 `dlg.content.height/width`（它是 `paper_frame` 造的那层
        #   Container，尺寸就落在那儿）。
        # [EN] ── The **size** of that popup (user 2026-10-10 afternoon: "isn't it too tall but also too
        # [EN] narrow") ──
        # [EN] Root cause: `content` is passed a bare `Column` (has width, **no height**),
        # [EN] and `mk_dialog` reads the size from `content` ⇒ `ch=None` ⇒ the inner `expand=True`
        # [EN] **stretches it to near full screen** (measured 1081px); the width 440 is also made up.
        # [EN] ⇒ This criterion directly measures `dlg.content.height/width` (it is the layer created by
        # [EN] `paper_frame`
        # [EN] Container, the size lands there).
        _d2 = dlgs_now[-1] if dlgs_now else None
        _c2 = getattr(_d2, 'content', None)
        _h2 = getattr(_c2, 'height', None)
        _w2 = getattr(_c2, 'width', None)
        from gui.app_flet import DLG_H_URL, DLG_W_URL
        ok('H5d ★★★ 网址弹窗的**尺寸是受控的**（不是被撑到满屏、也不是自己乱写一个宽度）',
           _h2 == DLG_H_URL and _w2 == DLG_W_URL,
           f'实际 {_w2}×{_h2}，应为 {DLG_W_URL}×{DLG_H_URL}'
           f'（满屏 ≈1081 高就是没给 height）')

        # 那一层里要**真的有输入框**（在**最上面那层**里找，别在主对话框里找）
        # [EN] That layer must **really have an input field** (look in the **topmost layer**, not in the main
        # [EN] dialog)
        top_dlg = dlgs_now[-1] if dlgs_now else None
        top_texts = VU.all_texts(top_dlg) if top_dlg is not None else []
        url_fld = None
        if top_dlg is not None:
            from gui.app_flet import mk_field as _mkf        # noqa: F401
            for c in VU.walk(top_dlg):
                if hasattr(c, '_field') and getattr(c, '_field', None) is not None:
                    url_fld = c
                    break
        # 这一条把"弹出来了、里面有输入框、而且能读写"**合在一起判**
        # （分开判时"能读写"那一条红不了 —— 没有哪种现实变异只让它红）。
        # [EN] This criterion judges "it popped up, there is an input field inside, and it can be read/written"
        # [EN] **all together**
        # [EN] (when judged separately the "can read/write" one cannot turn red —— no realistic mutation makes
        # [EN] only it red).
        writable = False
        if url_fld is not None:
            try:
                from gui.app_flet import field_value as _fv
                # ⚠ `mk_field` 返回的是个 **Row**，真正的 `TextField` 挂在 `._field` 上
                #   （`field_value()` 取的就是 `ctrl._field.value`）。
                # [EN] ⚠ `mk_field` returns a **Row**, the real `TextField` is attached to `._field`
                # [EN] (`field_value()` reads exactly `ctrl._field.value`).
                url_fld._field.value = 'https://example.com/index.html'
                writable = 'example.com' in str(_fv(url_fld))
            except Exception:                                     # noqa: BLE001
                writable = False
        ok('H5 ★★★ 那个弹窗里**真的有输入框、而且能读写**'
           '（源码里有 `show_dialog` ≠ 点下去真弹出来；弹出个画上去的摆设也不算）',
           url_fld is not None and writable,
           f'找到输入框={url_fld is not None} 能读写={writable} 层内文字={top_texts[:3]}')
        # 顺手留一张"网址弹窗"的实拍（这一改的新界面，给人和说明书用）
        # [EN] Also keep a real shot of the "URL popup" (the new UI of this change, for humans and the manual)
        try:
            _p = await page.take_screenshot()
            (OUT / 'booklab_url_dialog.png').write_bytes(_p or b'')
        except Exception:                                         # noqa: BLE001
            pass

        # ── 在弹窗里点「确定」→ 回主对话框，**只有「网址」是实心的** ──
        # ⚠ 顺序很重要：**点了「网址」还不该亮**（那时只是弹了个框、还没填），
        #   亮了反而说明"取消也当选中了"。所以这里分两次判。
        # [EN] ── Click "确定" in the popup → back to the main dialog, **only "网址" is solid** ──
        # [EN] ⚠ Order matters: **after clicking "网址" it should not light up yet** (at that point it only
        # [EN] popped a box, not filled in),
        # [EN] if it lights up that instead means "cancel also counts as selected". So judge this in two steps.
        btns_mid = _src_buttons()
        ok('H5b0 ★★★ 只是弹出对话框、还没确定时，**「网址」不该算选中**'
           '（否则"取消"就变成了"选中一个空地址"）',
           _filled(btns_mid) == [], f'实心的：{_filled(btns_mid)}')

        def _click_label(lbl: str) -> bool:
            """在**最上面那层**里点一个按钮（按标签找）。
                        English:
            In the **topmost layer**, click a button (find by label).
            """
            _root = (VU.open_dialogs(page) or [page])[-1]
            for c in VU.walk(_root):
                txt = getattr(c, 'content', None)
                if (isinstance(c, (ft.FilledButton, ft.TextButton))
                        and isinstance(txt, ft.Text) and txt.value == lbl
                        and c.on_click is not None):
                    c.on_click(None)
                    page.update()
                    return True
            return False

        confirmed = _click_label('确定')
        await asyncio.sleep(0.5)
        btns1 = _src_buttons()
        ok('H5b ★★★ 点「确定」→ 回主对话框，而且**只有「网址」是实心的**'
           '（互斥在界面上真的生效：点它之前谁都不亮，确定之后只有它亮）',
           confirmed and _filled(btns1) == ['网址'],
           f'确定按钮点到={confirmed} 实心的：{_filled(btns1)}')
        ok('H5c ★★ 「网址」排在**四个按钮里的最后**'
           '（用户："把网址移动到下面"）',
           list(btns1) == ['选一个文件', '选一个文件夹', '网址', '用 sample 测试'],
           f'顺序：{list(btns1)}')

        # ── 关掉再重开，并且**真点一个来源**，不报错（用户报的就是这条路上炸的）──
        # 用户原话：「我打开一次 点了网址 再点击其他页面 或者关闭了重新点击拆书 会报错」
        # 根因是 `C['ink']`（`ink` 只在 `INKC` 里），而它**只在"选中了某个来源之后
        # 要画那行回显"的时候**才会被执行 —— 所以这条判据必须真的选一次。
        # ★ 点「用 sample 测试」而不是「选一个文件」：后者会拉起**系统文件选择器**，
        #   自动化里会一直挂着；而 samples 那条路是**自己在 samples/ 里挑一本**、
        #   全程在程序内 —— 而且它**正是用户报错时走的那条**
        #   （日志里那句 `选示例失败: 'ink'` 就是从 `_use_sample` 发出来的）。
        # ⚠ 不能直接调 `_set_src` —— 它是 `_booklab_body` 里的**闭包**，
        #   不是 `NovelWorldApp` 的方法（第一版这么写，报 AttributeError）。
        # [EN] ── Close and reopen, and **really click a source**, no error (what the user reported is that it
        # [EN] blows up on this path) ──
        # [EN] User's exact words: "I open it once, click 网址, then click another page, or close it and click 拆书
        # [EN] again, it errors"
        # [EN] The root cause is `C['ink']` (`ink` is only in `INKC`), and it is **only after "some source has
        # [EN] been selected
        # [EN] and that echo line is about to be drawn"** that it gets executed —— so this criterion must
        # [EN] really select once.
        # [EN] which hangs forever in automation; whereas the samples path is **picking a book from samples/
        # [EN] itself**,
        # [EN] entirely within the program —— and it is **exactly the path the user took when reporting the
        # [EN] error**
        # [EN] ⚠ Cannot call `_set_src` directly -- it is a **closure** inside `_booklab_body`,
        # [EN] not a method of `NovelWorldApp` (the first version did this and raised AttributeError).
        reopen_err = ''
        try:
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
            app.show_booklab_dialog()
            await asyncio.sleep(0.8)
            _click_label('用 sample 测试')
            await asyncio.sleep(1.2)
            _root2 = (VU.open_dialogs(page) or [page])[-1]
            _txt2 = VU.all_texts(_root2)
            # 判"真的跑到底了"：回显那行要出现「选了：…」（说明 render() 走完了，
            # 而那行正是崩的那一行）
            # [EN] To judge "it really ran to the end": the echo line must contain "选了：…" (indicating render()
            # [EN] completed,
            # [EN] and that line is exactly the line that crashes)
            if not any('选了' in x for x in _txt2):
                reopen_err = f'（点了示例却没有回显：{_txt2[:4]}）'
        except Exception as ex:                                   # noqa: BLE001
            reopen_err = repr(ex)
        ok('H6 ★★★ 关掉再重开、并且**真点一个来源** —— 不报错、回显也出来了'
           '（用户报的现场：`C[\'ink\']` 那句 KeyError 就是在这条路上炸的；'
           '`tools/verify_color_keys.py` 静态查这一整类，这条查"真的走一遍不炸"）',
           not reopen_err, reopen_err)

        png = await page.take_screenshot()
        (OUT / 'booklab_dialog.png').write_bytes(png or b'')
    finally:
        _rm(tmp)


def _logic_main(tmp: Path):
    print('\n【A】方法论')
    test_theory(tmp)
    print('\n【B】读书（分章 · 分层取样）')
    test_reader(tmp)
    print('\n【C/D】拆解四道工序 · 技能包')
    written = test_digest(tmp)
    print('\n【E】拆书库与匹配')
    test_store(tmp, written)
    print('\n【F】接线（行为级）')
    test_wiring(tmp, written)
    print('\n【G】菜单与对话框（源码）')
    test_menu()
    print('\n【I】外部借鉴落地（EM 门禁卡 / 标签 / 泄漏门 / 复用优先 / 定量层）')
    test_upgrades(tmp)
    print('\n【J】格式与类型（2026-10-27：常见格式 + 拆专业书做素材）')
    test_formats_and_kinds(tmp)
    return written


# ══════════════════════════════════════════════════════════════
#  J. 格式与类型（2026-10-27）
#
#  用户两句话（同一轮）：
#    「我是不是可以找一些中国古代建筑史等书籍来拆书…让它可以拆小说
#      也可以拆各种专业书籍 用来做素材」
#    「有些书籍是图片格式的 你至少要支持常见格式 包括 pdf 文字 pdf 图片
#      Word 格式 html txt 常见电子书格式 以及 wps 格式等等」
#
#  ★ 这一组的写法纪律（与前面各组同一条）：
#    **在文件里搜得到不算数** —— 调那个函数、看它的返回值。
#    例：J4 不是搜"不做 OCR"这句话在不在，而是**造一份扫描 PDF 真调 `pdf_hint()`**
#    看它吐出来的那句话里有没有"OCR"。
# [EN] J. Formats and types (2026-10-27)
# [EN] Two user lines (same round): "could I feed in books like a history of Chinese architecture
# [EN] ... make it split novels **and** specialist books, for material" and "some books are
# [EN] image-format, support the common formats at least ... text PDF, image PDF, Word, html, txt,
# [EN] common ebook formats, and WPS".
# [EN] ★ Same writing discipline as the other groups: **"findable by grepping the file" does not
# [EN] count** -- call the function and look at what it returns. E.g. J4 does not grep for the
# [EN] sentence "we don't do OCR"; it **builds a scanned PDF and really calls `pdf_hint()`** to see
# [EN] whether the returned sentence mentions OCR.
# ══════════════════════════════════════════════════════════════
def test_formats_and_kinds(tmp: Path) -> None:
    from booklab import sources as S
    from booklab import kind as K
    from booklab import ocr as O
    from booklab import theory as T
    from booklab import reader as R
    from booklab import skillgen as SG

    # ── J1 九种格式都认（**调 `kind_of`，不是数后缀表**）──
    want = {'.txt': 'text', '.docx': 'docx', '.doc': 'ole', '.wps': 'ole',
            '.html': 'html', '.pdf': 'pdf', '.epub': 'epub',
            '.mobi': 'mobi', '.rtf': 'rtf', '.odt': 'odt', '.png': 'image'}
    bad = {k: S.kind_of('x' + k) for k in want
           if S.kind_of('x' + k) != want[k]}
    ok('J1 ★★★ 常见格式都认得出（文字/Word/WPS/epub/mobi/rtf/odt/pdf/图片）',
       not bad and all(S.is_supported('x' + k) for k in want),
       f'不对的：{bad}' if bad else '')

    # ── J2 扫描件判定：**有页无字 ⇒ True，有字 ⇒ False** ──
    #    ★ 判据必须是**比例**不是"一页都没有"（书里常有一两页是插页/空白）
    scan_pages = ['', ''] + [''] * 8
    text_pages = ['这是一页有很多字的正文，' * 12] * 10
    ok('J2 ★★★ 扫描件判定：`有页无字`判扫描、`有字`判不扫描',
       O.is_scan(scan_pages) and not O.is_scan(text_pages),
       f'scan={O.is_scan(scan_pages)} text={O.is_scan(text_pages)}')

    # ── J3 OCR 用不了时要说出**该装什么**（不许只回空串）──
    h = O.hint()
    ok('J3 ★★ OCR 装不了时有话术（含"装什么"，不是一句"读不出来"）',
       bool(h) and 'pip install' in h and 'rapidocr' in h, h[:80])

    # ── J4 扫描 PDF 的提示**不再是死胡同**（原来写着"本项目不做 OCR"）──
    #   ★ 真造一份扫描 PDF 再真调 `pdf_hint()` —— 不搜源码
    hint_txt = ''
    try:
        from PIL import Image, ImageDraw
        p = tmp / 'scan.pdf'
        im = Image.new('RGB', (600, 160), 'white')
        ImageDraw.Draw(im).text((20, 30), 'scan page', fill='black')
        im.save(str(p), 'PDF', resolution=150)
        hint_txt = S.pdf_hint(p)
    except Exception as e:                                       # noqa: BLE001
        hint_txt = f'（造不出扫描 PDF：{e}）'
    ok('J4 ★★★ 扫描 PDF 的提示**不再是死胡同**（不许再说"本项目不做 OCR"）',
       bool(hint_txt) and 'OCR' in hint_txt
       and '本项目不做 OCR' not in hint_txt, hint_txt[:90])

    # ── J5 类型判定：小说 / 专业书 / 混合 都能判对 ──
    novel = ('他低声道：「你不该来的。」「我必须来。」她答道，'
             '心里想着那封信。只见那人身形一晃，忽然喝道：「站住！」') * 12
    ref = ('第三章 大木作\n斗拱由斗、拱、昂组成。柱高 3.6 米，开间 5.2 米。'
           '见图 3-2[1]。第一节 材分制\n参考文献\n[1] 某书，某出版社，'
           'ISBN 978-7-000-00000-0\n索引') * 8
    got_n, got_r, got_m = (K.judge(novel), K.judge(ref),
                           K.judge(novel + ref))
    ok('J5 ★★★ 类型判定：小说判小说、专业书判专业书、混着判混合',
       got_n == K.NOVEL and got_r == K.REFERENCE and got_m == K.MIXED,
       f'{got_n}/{got_r}/{got_m}')

    # ── J6 专业书的维度与门禁**是另一套**（不是七维换个说法）──
    #   ★ 判的是"**核心门禁不同**"，不是"完全不重叠"：
    #     `可替换项` / `不可照搬` 这两条对两条线都成立（"换个题材还能用吗"
    #     "哪些不能跟着搬"），共用是对的；真正该分开的是**各自独有的那几条**。
    #     （这一条判据第一版写成了"交集为空" ⇒ 立刻红了 —— 红的是判据不是产品。）
    # [EN] ★ It judges "**the core gates differ**", not "no overlap at all": `可替换项` /
    # [EN] `不可照搬` hold for both lines ("usable in another genre?" / "what must not be carried
    # over"), so sharing them is correct; what must differ is **each line's own gates**. (The first
    # version of this criterion demanded an empty intersection => it went red at once -- the
    # criterion was wrong, not the product.)
    ref_only = {'这条能怎么用', '可信度', '边界条件'}
    novel_only = {'读者想看什么', '情绪链', '戏剧单元'}
    ok('J6 ★★ 专业书有**自己的**维度与门禁'
       '（独有的三条都在，小说的三条都不在）',
       len(T.REF_DIMENSIONS) >= 5 and len(T.REF_GATES) == 5
       and ref_only <= set(T.REF_GATES)
       and not (novel_only & set(T.REF_GATES))
       and bool(T.REF_MIN_ENTRIES),
       f'缺={ref_only - set(T.REF_GATES) or "无"} '
       f'混进来了={novel_only & set(T.REF_GATES) or "无"}')

    # ── J7 专业书按**信息密度**挑章：空章（绪论/索引）不进 ──
    chaps = [R.Chapter(no=1, title='第1章 绪论', text='前言如下，凡例见后。'),
             R.Chapter(no=2, title='第2章 索引', text='索引\n见参考文献。'),
             R.Chapter(no=3, title='第3章 大木作',
                       text='柱高 3.6 米，开间 5.2 米。《某书》载：材分八等，'
                            '一等材高 9 寸。见图 3-2[1]。')]
    book = type('B', (), {'chapters': chaps, 'n': 3})()
    # ★ **两条路都要守**（第一版只测了兜底那条，于是"主路径的过滤被删掉"
    #   这一刀打上去判据**照样绿** —— 反例法立刻抓到了这个漏）：
    #     ① 主路径：模型填了 `密度`（`scan` 里有值）；
    #     ② 兜底路径：模型没填（老教训：提示词里写了 ≠ 生效）⇒ 本地现算。
    #   判据只测一条 ⇒ 另一条被删掉时它"看着在守，其实没守"。
    # [EN] ★ **Both routes must be guarded** (the first version only tested the fallback, so the
    # [EN] knife "delete the filter on the main route" left the criterion **green** -- the
    # [EN] counterexample method caught this gap at once): ① main route: the model filled `密度`
    # [EN] (`scan` has rows); ② fallback: it didn't (old lesson: in the prompt ≠ in effect) =>
    # [EN] compute locally. Testing only one means the other is "guarded in appearance only".
    scan_rows = [{'章': c.title, '专题': 'x', '密度': K.density(c.text)}
                 for c in chaps]
    picked_main = R.pick_deep(book, scan_rows, good='', kind=K.REFERENCE)
    picked_fallback = R.pick_deep(book, [], good='', kind=K.REFERENCE)
    n1 = [c.title for c in picked_main]
    n2 = [c.title for c in picked_fallback]
    empty_in = lambda ns: any(('绪论' in x or '索引' in x) for x in ns)
    ok('J7 ★★★ 专业书挑章按密度：**绪论/索引不进精读**'
       '（主路径与兜底路径**两条都守**）',
       bool(picked_main) and bool(picked_fallback)
       and not empty_in(n1) and not empty_in(n2),
       f'主={n1} 兜底={n2}')

    # ── J8 素材条目**带出处**才写得进 SKILL（没出处的要照实标出来）──
    from booklab import analyzer as A
    dd = A.Digest()
    dd.kind = K.REFERENCE
    dd.brief = A.Brief(title='测试书', genre='建筑史', good='', focus='')
    dd.final = {'条目': [
        {'名字': '举架', '类别': '规矩', '内容': '屋面坡度由举高定。',
         '出处': '第4章', '这条能怎么用': 'x', '可信度': '通说',
         '边界条件': '明清', '可替换项': 'y', '不可照搬': 'z',
         '这本书的例子': '某殿'},
        {'名字': '无出处条目', '类别': '术语', '内容': '没有写出处。',
         '出处': ''},
    ]}
    md = SG.render_skill(dd)
    ok('J8 ★★★ 素材型 SKILL：条目带出处，没出处的**照实标"未写出处"**',
       '第4章' in md and '未写出处' in md and '素材型' in md,
       f'len={len(md)}')


# ══════════════════════════════════════════════════════════════
#  I. 外部借鉴落地（2026-10-10）
# [EN] I. External borrowings landed (2026-10-10)
# ══════════════════════════════════════════════════════════════
def test_upgrades(tmp: Path) -> None:
    """这一组钉住本轮的借鉴落地（调研报告见 `developers/docs/外部借鉴/06_*.md`）。

    ★ 写法纪律（本项目踩出来的两条，这里都遵守）：
      ① **不许"在文件里搜得到"就算接上了** —— 要在**那个函数的那个块里**查，
         或者干脆**调它一次看返回值**；
      ② **不许只判"名字在不在"** —— 例如空镜那条要判那段真的没了。
    
        English:
    This group pins down this round's landed borrowings (see the survey report in
    `developers/docs/外部借鉴/06_*.md`).
        ★ Writing discipline (two points learned the hard way in this project, both followed here):
          ① **Don't accept "it can be found by searching the files" as wired up** — you must check **inside that block of that function**,
             or just **call it once and look at the return value**;
          ② **Don't just check whether the name exists** — for example, the empty-mirror case must verify that that section is really gone.
    """
    import shutil
    from booklab import theory as T, skillgen as SG, metrics as M, store as ST
    from booklab.analyzer import Brief, Digest
    from skills.registry import SkillRegistry

    # ── A. EM 五门禁卡 ──
    # [EN] ── A. EM five gates ──
    ok('I1 ★★ 门禁是**五条**且名字齐（读者想看什么/情绪链/戏剧单元/可替换项/不可照搬）'
       '—— 原来只有"名称/怎么做/什么时候用/为什么管用/例子"五个工艺字段，'
       '没有"可替换项/不可照搬"这对反抄袭字段',
       len(T.GATES) == 5
       and set(T.GATES) == {'读者想看什么', '情绪链', '戏剧单元', '可替换项', '不可照搬'},
       str(T.GATES))
    # ⚠ 反例法抓出第一版太弱：只判"五条字段名在不在"，于是把提示词里
    #   「**门禁五条**（决定这一招能不能跨书用）」这一整段说法删掉，判据照样绿
    #   （字段名在下文的条目里还留着）。⇒ 补一条：**"门禁"这个说法本身必须在**。
    # [EN] ⚠ Counterexample method caught the first version as too weak: it only checked "are the five
    # [EN] field names present", so deleting
    # [EN] (the field names remained in the entries below). ⇒ Add one more: **the very phrase "门禁" must be
    # [EN] present**.
    ok('I2 ★★ `FINAL_PROMPT` 真的要求了这五条，**而且明说它们是"门禁"**'
       '（在那段提示词里查，不全文件 grep）',
       all(g in T.FINAL_PROMPT for g in T.GATES) and '门禁五条' in T.FINAL_PROMPT,
       str([g for g in T.GATES if g not in T.FINAL_PROMPT]))
    ok('I3 ★★★ 「可替换项」被写成**格式要求**：必须「功能位→任意X」，'
       '并**明确禁止**写成「原书专名→任意X」'
       '—— 这把反抄袭从"事后查"变成"生成时就写不对"',
       '功能位→任意X' in T.FINAL_PROMPT and '原书专名→任意X' in T.FINAL_PROMPT,
       '')

    # ── B. 受控标签 ──
    # [EN] ── B. Controlled labels ──
    ok('I4 ★★ 五个标签轴齐，且**每个轴都有词表**（不是"随便写个词"）',
       set(T.TAG_AXES) == set(T.TAG_VALUES) and all(T.TAG_VALUES.values()),
       str(sorted(T.TAG_VALUES)))
    ok('I4b ★★ 核心轴 = 题材/读者需求/情绪（命中 2 分，其余 1 分）',
       set(T.CORE_AXES) == {'题材', '读者需求', '情绪'}, str(T.CORE_AXES))
    # 写入侧与查询侧的轴必须一致 —— 不一致会让"写进去的标签查不出来"
    # [EN] The write side and the query side must use the same axes -- otherwise "labels written in cannot
    # [EN] be queried out"
    from skills import registry as RG
    ok('I4c ★★★ **写入侧（`theory`）与查询侧（`skills.registry`）的核心轴/轴表必须一致**'
       '—— 两边不一致就是"写进去的标签查不出来"，属于最难查的静默错误',
       tuple(RG.CORE_AXES) == tuple(T.CORE_AXES) and tuple(RG.TAG_AXES) == tuple(T.TAG_AXES),
       f'registry={RG.CORE_AXES}/{RG.TAG_AXES}')
    # 词表过滤：不在表里的值被丢掉、且**照实报告**（不静默）
    # [EN] Vocabulary filtering: values not in the table are dropped, and **reported as-is** (not silently)
    normed = T.norm_tags({'题材': ['悬疑', '瞎编的类型'], '不存在的轴': ['x']})
    ok('I5 ★★ `norm_tags` 丢掉不在词表里的值（**不猜同义词** —— 猜错会把玄幻的拆解挂到悬疑上）',
       normed == {'题材': ['悬疑']}, str(normed))
    # 词表文件与代码同源
    # [EN] The vocabulary file and the code share the same source
    gloss = APP / 'skills' / 'book-dismantle' / '标签词表.md'
    gtext = gloss.read_text(encoding='utf-8') if gloss.is_file() else ''
    # ⚠ 反例法抓出第一版太弱：判的是 `f'- {v}' not in gtext`（**子串**），
    #   于是把词表里的 `- 志怪` 改成 `- 志怪类`，判据照样绿。
    #   ⇒ 改成**行级精确匹配**（整行就是那一个值）。
    # [EN] ⚠ Counterexample method caught the first version as too weak: it checked `f'- {v}' not in gtext`
    # [EN] (**substring**),
    # [EN] so changing `- 志怪` in the vocabulary to `- 志怪类` still left the criterion green.
    # [EN] ⇒ Change to **line-level exact match** (the entire line is exactly that one value).
    _g_lines = {ln.strip() for ln in gtext.splitlines()}
    miss = [v for vals in T.TAG_VALUES.values() for v in vals if f'- {v}' not in _g_lines]
    ok('I5b ★★ `标签词表.md`（给人读）与 `theory.TAG_VALUES`（给程序用）**同源**'
       '（**行级**比对 —— 子串比对会被"志怪 / 志怪类"蒙混过去）'
       '—— 两边不一致会先烂在这个文件上',
       gloss.is_file() and not miss, f'词表文件里缺: {miss[:6]}')
    ok('I5c ★ 核心轴在三轴里（不是随便挑三个）',
       all(x in T.TAG_VALUES for x in T.CORE_AXES), '')

    # ── C. 专名泄漏门 ──
    # [EN] ── C. Proper-noun leakage gate ──
    def _card(**kw):
        base = {'名称': '某招', '怎么做': '这样做', '什么时候用': 'x',
                '为什么管用': 'y', '这本书的例子': '第 1 章',
                '读者想看什么': 'z', '情绪链': 'a→b',
                '戏剧单元': '被轻视者公开反证'}
        base.update(kw)
        return base
    d_ok = Digest(brief=Brief(title='某书', genre='悬疑'),
                  final={'模块': [_card(可替换项=['欺压者→任何压制主角的人'],
                                        不可照搬=['王掌柜', '某书'])]})
    e_ok, _ = SG.leak_check(d_ok)
    ok('I6 ★★★ 干净卡**必须过**（不能把对的报成泄漏 —— 假阳性会让这个门被无视）',
       e_ok == [], str(e_ok[:2]))
    d_spec = Digest(brief=Brief(title='某书', genre='悬疑'),
                    final={'模块': [_card(可替换项=['王掌柜→任意人'],
                                          不可照搬=['王掌柜'])]})
    e_spec, _ = SG.leak_check(d_spec)
    ok('I6b ★★★ `可替换项` 左边是**专名**（出现在 `不可照搬` 里）→ 必须报错'
       '—— "专名→任意X"就是没抽象',
       any('左边是专名' in x for x in e_spec), str(e_spec[:2]))
    d_left = Digest(brief=Brief(title='某书', genre='悬疑'),
                    final={'模块': [_card(可替换项=['陈公子→任意人'])]})
    e_left, _ = SG.leak_check(d_left)
    ok('I6c ★★ 带**中式称谓后缀**的（"陈公子"）也算专名（这条不靠名单，靠词形）',
       any('左边是专名' in x for x in e_left), str(e_left[:2]))
    d_noarrow = Digest(brief=Brief(title='某书', genre='悬疑'),
                       final={'模块': [_card(可替换项=['欺压者，任何压制主角的人'])]})
    e_na, _ = SG.leak_check(d_noarrow)
    ok('I6d ★ 没写 `→` 也算不合格（格式要求就是要机械可判）',
       any('没有用' in x for x in e_na), str(e_na[:2]))
    d_leak = Digest(brief=Brief(title='某书', genre='悬疑'),
                    final={'模块': [_card(怎么做='王掌柜走过来', 不可照搬=['王掌柜'])]})
    e_leak, _ = SG.leak_check(d_leak)
    ok('I6e ★★ 专名出现在**抽象字段**（怎么做）里 → 报错',
       any('机制字段' in x for x in e_leak), str(e_leak[:2]))
    e_title, _ = SG.leak_check(Digest(
        brief=Brief(title='某书', genre='悬疑'),
        final={'模块': [_card(戏剧单元='某书里的那场戏')]}))
    ok('I6f ★★ **书名**出现在抽象字段里 → 报错（机制卡要能脱离这本书读懂）',
       any('书名' in x for x in e_title), str(e_title[:2]))
    # ★ 探测不到名单时报 warning，不静默通过（照 oh-story 的规矩）
    # [EN] ★ When the list cannot be detected, emit a warning rather than silently passing (per oh-story's
    # [EN] rules)
    _, w_noname = SG.leak_check(Digest(
        brief=Brief(title='某书'), final={'模块': [_card()]}))
    ok('I6g ★★★ 卡里没有 `不可照搬` ⇒ **这次没查**，必须报 warning'
       '—— 「探测不到名单就静默通过」正是这个门最容易退化成摆设的地方',
       bool(w_noname) and '没查' in w_noname[0], str(w_noname[:1]))

    # ── D. 落到 `skills/book-dismantle/<书名>/`（两级），且复用优先 ──
    # [EN] ── D. Output to `skills/book-dismantle/<书名>/` (two levels), reuse first ──
    ok('I7 ★★ 目录名是**拆书的英文翻译**（用户点名要的）',
       SG.BOOK_DIR == 'book-dismantle', SG.BOOK_DIR)
    root = tmp / 'skills_i'
    # ⚠ 标签要**含一个非核心轴**（`适用阶段`）与一个**独立于 genre 的核心轴值**
    #   （`解谜满足`）—— 反例法第一版没这么做，于是：
    #     · M12（同类判定不看核心轴）没有反例可测（数据里只有核心轴，撞了就是核心）；
    #     · M15（score 不读标签）也测不出来（查询里那个值已经在 `触发关键词` 里）。
    # [EN] ⚠ The label must contain **one non-core axis** (`适用阶段`) and one **core-axis value independent of
    # [EN] genre**
    # [EN] (`解谜满足`) -- the first version of the counterexample method did not do this, so:
    # [EN] · M12 (same-class determination does not look at the core axis) had no counterexample to test
    # [EN] (the data had only core axes; a collision means it's core);
    # [EN] · M15 (score does not read labels) also could not be tested (that value in the query was already [EN] in `触发关键词`).
    d1 = Digest(brief=Brief(title='甲书', genre='悬疑'),
                final={'模块': [_card()],
                       '标签': {'题材': ['悬疑'], '读者需求': ['解谜满足'],
                                '适用阶段': ['全篇']}})
    w1 = SG.write(d1, root=root)
    ok('I7b ★★★ 写出来的路径是 `skills/book-dismantle/<书名>/`，'
       '**不是** `book-dismantle/book-dismantle/<书名>/`（本轮真踩过一次：'
       '`root` 的语义没统一，两层目录套了两层）',
       w1.dir.parent.name == SG.BOOK_DIR
       and w1.dir.parent.parent == root
       and w1.dir.name == '甲书',
       w1.dir.relative_to(root).as_posix())
    ok('I7c ★ 包里三份齐（SKILL.md / digest.json / 拆书记录.md）—— 自包含',
       all((w1.dir / n).is_file()
           for n in ('SKILL.md', 'digest.json', '拆书记录.md')),
       str(sorted(p.name for p in w1.dir.iterdir())))
    # ★★ 用户点名要的那一步：同一本书再拆 → 更新，不是新建
    # [EN] ★★ The step the user explicitly asked for: re-dismantle the same book → update, not create new
    w1b = SG.write(d1, root=root)
    ndirs = len(list((root / SG.BOOK_DIR).iterdir()))
    ok('I8 ★★★ **同一本书再拆 = 更新那一份**（用户原话：「每拆一本书，就看下有类似'
       'skill 存在吗？如果有就强化更新，没有就创建」）—— 不许新开一份 v2',
       w1b.action == 'update' and w1b.dir == w1.dir and ndirs == 1,
       f'action={w1b.action} 目录数={ndirs}')
    ok('I8b ★ 更新时 `digest.json` 里留下**改了什么的记录**（改动不许静默）',
       'history' in (w1.dir / 'digest.json').read_text(encoding='utf-8')
       and 'rebuild' in (w1.dir / 'digest.json').read_text(encoding='utf-8'), '')
    # 同类书 → 强化（同 Tags 核心轴重合）
    # [EN] Same-class book → strengthen (same Tags core axis overlaps)
    d2 = Digest(brief=Brief(title='乙书', genre='悬疑'),
                final={'模块': [_card(名称='另一招')],
                       '标签': {'题材': ['悬疑'], '情绪': ['紧张']}})
    tgt, act, why = SG.find_similar(d2, root)
    ok('I8c ★★★ **同类书 → 强化**（受控标签核心轴重合）'
       '—— 这是"有类似的就强化更新"的另一半',
       act == 'strengthen' and tgt == w1.dir, f'{act} / {why}')
    # ★★ 只撞"适用阶段"（非核心轴）**不算同类** —— 否则"言情中段"和"悬疑中段"
    #    会被当成一回事，那是比不匹配更坏的错（会把不相干的写法推给作者）
    # 丁书：与甲书**只在非核心轴**（适用阶段=全篇）上重合
    # [EN] would be treated as the same thing, which is worse than a mismatch (it would push irrelevant
    # [EN] writing techniques at the author)
    d2b = Digest(brief=Brief(title='丁书', genre='言情'),
                 final={'模块': [_card(名称='四招')],
                        '标签': {'题材': ['言情'], '适用阶段': ['全篇']}})
    _t2b, act2b, _w2b = SG.find_similar(d2b, root)
    ok('I8c2 ★★★ 只在**非核心轴**上撞了值 ⇒ **不算同类**（仍是新建）'
       '—— "悬疑中段"和"言情中段"不是一回事',
       act2b == 'create', f'{act2b} / {_w2b}')
    # 不同类 → 新建
    # [EN] Different class → create new
    d3 = Digest(brief=Brief(title='丙书', genre='言情'),
                final={'模块': [_card(名称='三招')], '标签': {'题材': ['言情'],
                                                              '读者需求': ['共鸣治愈']}})
    _t3, act3, _why3 = SG.find_similar(d3, root)
    ok('I8d ★★ 不同类 → **新建**（不许把言情的东西塞进悬疑那份）', act3 == 'create', act3)
    ok('I8e ★ `action="new"` 能强制新建（同名进 v2）—— 想留对照时用',
       SG.write(d1, root=root, action='new').dir.name != w1.dir.name, '')

    # ── E. 注册表：两级扫描 + 把"写了没用"的字段接进打分 ──
    # [EN] ── E. Registry: two-level scan + wire fields that were "written but unused" into scoring ──
    CFG.set('SKILLS_DIR', str(root))
    rg = SkillRegistry()
    rg.load(force=True)
    names = [s.dir_name for s in rg.all_skills()]
    ok('I9 ★★★ 注册表**认得出两级结构**（`skills/<分类>/<技能>/SKILL.md`）'
       '—— 只扫一级的话，拆书产出的技能一个都加载不到。'
       '（`甲书·v2` 也在，是 I8e「强制新建」造出来的）',
       '甲书' in names and '甲书·v2' in names
       and not (root / '甲书').exists(),          # 一级目录里**不该有**它
       # [EN] It **should not be** in the first-level directory
       f'{names}｜一级目录存在={ (root / "甲书").exists() }')
    sk = rg.get('甲书')
    ok('I9b ★★ 技能的**父目录名**取自两级结构（`book-dismantle`）'
       '—— 它是"这个技能属于哪一类"的事实来源',
       sk is not None and sk.parent_dir == SG.BOOK_DIR,
       (sk.parent_dir if sk else ''))
    # score 接上 适用类型 / 特点 / 标签
    # [EN] score Connect to applicable type / features / tags
    if sk is not None:
        s_name = sk.score('甲书')
        # ⚠ 查询要**避开 `触发关键词` 里已有的词** —— 否则命中的是关键词那一档，
        #   测不出标签这一档有没有生效（反例法 M15 第一次就是这么漏掉的）。
        # [EN] ⚠ The query must **avoid words already in `触发关键词`** -- otherwise the hit is at the keyword tier,
        # [EN] and you cannot test whether the label tier is in effect (this is how the first counterexample
        # [EN] method M15 missed it).
        s_tag = sk.score('解谜满足')
        s_non = sk.score('今天天气不错啊')
        ok('I9c ★★★ `registry.score` **真的读了受控标签**'
           '—— `标签` 是 `skillgen` 一直写、而注册表从来没读过的字段（写了没用）',
           s_tag > 0, f'标签={s_tag}')
        ok('I9d ★★ 沾边的分**低于**直接叫名字（别让"沾边"盖过"指名道姓"）',
           s_tag < s_name, f'名={s_name} 标签={s_tag}')
        ok('I9e ★★ 完全不相干的问句**不打分**（不许"总能匹配上一点"）',
           s_non == 0, f'不相关={s_non}')

    # ── F. 受控标签进匹配（store.match）+ 核心轴闸门 ──
    # [EN] ── F. Controlled labels into matching (store.match) + core-axis gate ──
    packs = ST.list_packs(root)
    ok('I10 ★★ `store.list_packs` 找到了新位置的包（`book-dismantle/` 两级）',
       len(packs) >= 1, f'{len(packs)} 份')
    if packs:
        hit = ST.match({'类型': '悬疑'}, packs, limit=3,
                       want_tags={'题材': ['悬疑']})
        ok('I10b ★★ `match` 支持 `want_tags`，命中写在 `hit` 里（**可解释**）',
           bool(hit) and '标签命中' in (hit[0].hit or ''), hit[0].hit if hit else '')
        # ⚠ 必须让**类型那一档先命中**，这一条判的才是"核心轴闸门"：
        #   否则返回空的真正原因是"一份都没匹配上"，与闸门无关（假绿）。
        # [EN] ⚠ The **type tier must hit first**, so that this check actually tests the "core-axis gate":
        # [EN] otherwise the real reason for an empty return is "nothing matched at all", unrelated to the gate
        # [EN] (false green).
        none_hit = ST.match({'类型': '悬疑'}, packs, limit=3,
                            want_tags={'题材': ['科幻'], '情绪': ['热血']})
        # 前提自检：不带标签时，同一本书**是匹配得上**的（否则上面那句白判）
        # [EN] Precondition self-check: without labels, the same book **does match** (otherwise the above check
        # [EN] is meaningless)
        _san = ST.match({'类型': '悬疑'}, packs, limit=3)
        ok('I10c0 ★★★ 前提自检：**不带标签**时同一本书匹配得上'
           '（不成立的话，I10c 绿的真正原因就是"压根没匹配"，而不是闸门）',
           bool(_san), f'{len(_san)} 份')
        ok('I10c ★★★ 给了标签却**核心轴一份都没命中** ⇒ 返回空'
           '—— 不设这道闸，只要"适用阶段"撞一个值就会推一份不相干的经验，'
           '那比不返回更坏（模型会照着它写）',
           none_hit == [], str([p.name for p in none_hit]))

    # ── G. 定量层 ──
    # [EN] ── G. Quantitative layer ──
    m = M.scan('他来了。她走了。灯灭了。' * 30)
    ok('I11 ★★ 定量层给出**可复算**的数字（句长/段长/对白占比/虚词密度/短句占比）',
       m.get('可用') and all(k in m for k in ('句长中位', '段长中位', '对白占比',
                                              '虚词密度', '短句占比')),
       str({k: m.get(k) for k in ('句长中位', '对白占比')}))
    ok('I11b ★★ 太短的文本**明说"不可用"**，不硬给数字'
       '（短文本上的句长统计天然失真 —— 这个坑在 `ai_metrics` 上踩过）',
       M.scan('很短。').get('可用') is False, '')
    ok('I11c ★ 定量层**不判好坏**：报告块里写清"是量出来的，不是判断"',
       '不是判断' in M.render_block(m) or '量出来的' in M.render_block(m), '')
    ok('I11d ★ 不可用时 `render_block` 返回空串（宁可不写，也不写"数据不足"）',
       M.render_block({'可用': False}) == '', '')
    # 提示只报越线的（用**一段真正正常的多变文本**）
    # ⚠ 第一版我写的是 `'同一句' * 12` —— 那**本身就是重复文本**，
    #   四字重复率当然爆表，判据红得没道理（是我把"某个文本的性质"
    #   当成了"指标对不对"）。测试数据要真的多样，**且用 `\n\n` 分段**。
    # [EN] Report only those over the line in the prompt (use **a genuinely normal varied text**)
    # [EN] ⚠ In the first version I wrote `'同一句' * 12` -- which **is itself repetitive text**,
    # [EN] so the four-character repetition rate naturally exploded, and the criterion went red for no good
    # [EN] reason (I mistook "a property of some text"
    # [EN] for "whether the metric is right"). Test data must be genuinely varied, **and use `\n\n` to
    # [EN] split paragraphs**.
    normal = (
        '院墙外那条河，早上还看得见石阶，午后就被水漫过了。\n\n'
        '他说：「走吧。」她把包袱往肩上提了提，没答话。\n\n'
        '他没有回头。风从河面上过来，带着一点腥气。船在远处。\n\n'
        '岸边的柳树落了一地叶子，几个孩子在捡，捡了又扔。\n\n'
        '船靠岸时天已经擦黑。他数了数铜钱，又数了一遍。\n\n'
        '「几位？」船家问。「两位。」他说。「上吧。」船家把跳板搭好。\n\n'
        '她把包袱放在脚边，坐下来看着水面。水里有灯影，一晃一晃。\n\n'
        '他想起许多年前也是这么一个晚上，不过他没说出来。\n\n'
        '船到河心，风大了些。船家喊了一声，把帆收了半幅。\n\n'
        '她忽然说：「那件事，你打算什么时候说？」他没应声。\n\n'
        '船到了对岸。他先跳下去，又回身伸手。她没接，自己跳了。\n\n'
        '码头上一盏灯亮着。有人在等他们，也有人只是在等船。\n\n'
        '他们沿着堤往北走。灯越来越远，脚步声倒是越来越清楚。\n\n')
    mn = M.scan(normal)
    # ★★ I11f 是反例法补的：M18 把「四字重复率」换回一个**没有上界**的公式
    #   （`出现≥2次的窗的总次数 / 不同窗数`，一段重复文本能算出 10.5），
    #   而 I11e 只看"提示条数"抓不到它。⇒ 直接钉住"率就是率"：
    #   **凡叫「率」的指标，值必须落在 [0, 1]**。
    # [EN] ★★ I11f was added by the counterexample method: M18 swapped "四字重复率" back to a formula **without
    # [EN] an upper bound**
    # [EN] and I11e only looked at "number of prompt lines" and missed it. ⇒ Directly pin down "a rate is a
    # [EN] rate":
    # [EN] **Any metric called a "rate" must have a value in [0, 1]**.
    _rates = {k: v for k, v in m.items()
              if k.endswith('率') and isinstance(v, (int, float))}
    _rep = M.scan('他说了一句话。' * 30)      # 一段高度重复的文本
    # [EN] A highly repetitive text
    _rates.update({k: v for k, v in _rep.items()
                   if k.endswith('率') and isinstance(v, (int, float))})
    ok('I11f ★★★ 凡叫「率」的指标，值**必须落在 [0, 1]**'
       '（反例法把"四字重复率"换回一个无上界的公式时，10.5 那种值就该被抓住）',
       all(0.0 <= float(v) <= 1.0 for v in _rates.values()),
       str(_rates))
    ok('I11e ★★ 提示**只报越线的**：一段正常的多变文本，提示应当**很少**'
       '（一次报告塞十个数字等于没报告；与"每条问题都要带修法"同一条纪律）',
       len(mn.get('提示') or []) <= 1,
       f'{mn.get("提示")}｜四字重复={mn.get("四字重复率")}')


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    CFG.set('MOCK_LLM', 'true')
    tmp = Path(tempfile.mkdtemp(prefix='nws_booklab_'))
    try:
        _logic_main(tmp)
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        ok('Z 判据自己跑通（没被异常打断）', False,
           traceback.format_exc().splitlines()[-1])
    finally:
        _rm(tmp)

    def _finish() -> int:
        """落报告 + 打结论行 + 返回退出码（**收尾只有这一处**）。

        ★★ 为什么要抽成一个函数（2026-10-10 发现的一个"退出码假绿"）：
          真机段跑在 `ft.run(entry)` 里，而 `entry` 结尾调
          `shutdown(page, code=...)` —— **`shutdown` 内部会 `os._exit(code)`**，
          它**不返回**。于是写在 `ft.run(entry)` 之后的那一段
          （`checks = report['checks']` … `return 0 if report['ok'] else 1`）
          **是死代码**：走真机这条路时，进程在 H 组结束时就被带走了，退出码恒为 0。

          两个后果，本轮实测都撞到了：
            ① **H 组的失败不影响退出码** ⇒ 全量回归（按退出码判成败）对 H 组的红
               **完全看不见** —— 我给 H5d（网址弹窗尺寸）做的变异因此被报成"漏掉"；
            ② 结论行（`拆书：x/y`）**从来没打出来过** ⇒ 回归报告里那一行是一句
               无关的日志（"任务栏图标: 已应用…"），看着像结论、其实不是。
          ⇒ 收尾统一走 `_finish()`：真机段在**关窗之前**调它拿退出码
            （先算分数 → 再定退出码 → 最后 shutdown）。
          ⚠ 与 `util/flet_shutdown.shutdown()` 注释里那条老坑是同一个病：
            "`await shutdown(page)` **之后**的代码永远不会执行"。
        
                English:
        Write the report + print the conclusion line + return the exit code (**finalization happens only
        here**).
                ★★ Why extract it into a function (a "fake-green exit code" found on 2026-10-10):
                  The real-device stage runs inside `ft.run(entry)`, and the end of `entry` calls
                  `shutdown(page, code=...)` — **`shutdown` internally calls `os._exit(code)`**,
                  and it **does not return**. So the block written after `ft.run(entry)`
                  (`checks = report['checks']` … `return 0 if report['ok'] else 1`)
                  **is dead code**: on the real-device path, the process is taken away when group H finishes, and the exit code is always 0.
                  Two consequences, both hit in this round's actual test:
                    ① **Failures in group H don't affect the exit code** ⇒ full regression (which judges pass/fail by exit code) is
                       **completely blind** to group H's reds — the mutation I made for H5d (URL popup size) was therefore reported as "missed";
                    ② The conclusion line (`拆书：x/y`) **was never printed** ⇒ that line in the regression report is an
                       unrelated log entry ("taskbar icon: applied…"), which looks like a conclusion but isn't one.
                  ⇒ Finalization uniformly goes through `_finish()`: the real-device stage calls it **before closing the window** to get the exit code
                    (first compute the score → then decide the exit code → finally shutdown).
                  ⚠ Same disease as the old pitfall in the comment of `util/flet_shutdown.shutdown()`:
                    "code **after** `await shutdown(page)` never executes".
        """
        checks = report['checks']
        bad = [c for c in checks if not c['ok']]
        report['passed'] = len(checks) - len(bad)
        report['total'] = len(checks)
        report['ok'] = not bad
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'booklab_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\n' + '─' * 62)
        print(f'  拆书：{report["passed"]}/{report["total"]}'
              + ('' if report['ok'] else '   ← 有失败'))
        for c in bad:
            print(f'    ! {c["name"]}  [{c["detail"][:110]}]')
        print('─' * 62)
        return 0 if report['ok'] else 1

    if not logic_only:
        try:
            import flet as ft
            print('\n【H】真机：对话框真的能打开')
            OUT.mkdir(parents=True, exist_ok=True)

            async def entry(page) -> None:
                from util.flet_shutdown import shutdown
                try:
                    await test_gui(page)
                except BaseException:                            # noqa: BLE001
                    traceback.print_exc()
                    ok('H 真机判据自己跑通', False,
                       traceback.format_exc().splitlines()[-1])
                # ★ 退出码**在关窗之前**算好、交给 `shutdown` —— 否则它的
                #   `os._exit` 会把后面所有代码变成死代码（见 `_finish`）。
                # [EN] ★ The exit code must be **computed before closing windows** and handed to `shutdown` --
                # [EN] otherwise its
                # [EN] `os._exit` turns all subsequent code into dead code (see `_finish`).
                await shutdown(page, code=_finish())

            ft.run(entry)
            # 正常到不了这里（`shutdown` 已 `os._exit`）；真到了就按同一口径收尾
            # [EN] Normally you cannot reach here (`shutdown` already `os._exit`); if you do, finish up with the
            # [EN] same criteria
            return _finish()
        except Exception:                                        # noqa: BLE001
            traceback.print_exc()
            ok('H 真机段跑通', False, traceback.format_exc().splitlines()[-1])

    return _finish()


if __name__ == '__main__':
    sys.exit(main())
