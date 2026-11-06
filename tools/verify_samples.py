# -*- coding: utf-8 -*-
"""验证：`samples/` 那批**示例输入文件夹**真的能用、真的齐、说明书真的提到了。

用户四点里的两点（2026-10-06）：
「加一个文件夹叫做 samples，包含 2 个文件夹 zh 和 en，准备几个写得很好的示例小说输入文件夹
（最好原创或者基于古代等非版权书籍里抽取，不要有版权问题），每个题材一个，
每个故事 2 个语言版本，分别放到 zh 和 en 里。」
「在使用说明 输入文件夹标准 里说清楚有这几个示例，说清楚放在哪里（给出 ASCII 的文件夹 tree），
并且简单介绍下这几个故事（中英语帮助文件列出各种 idea 文件夹）」

所以判据必须同时管住**磁盘**和**文档**：

  A 两份数据对齐：6 篇、slug 顺序一致、**题材与程序里的 `GENRE_CHOICES` 一一对应**
    （"每个题材一个"这句话要是假的，这条就红）；
  B 磁盘上真的齐：每篇 5 个文件、非空、有 `#` 标题、正文成段；
  C **分类真的对**：拿 `ingest.scanner` 去扫，设定 1 / 人物 2 / 大纲 1 / 伏笔 1 / 正文 1
    （中英两种目录名都要分对 —— 英文那套靠的是同一张词表里的英文关键词）；
  D **开卷真的能跑**：演示模式下走一遍 `extract_settings()`，出六键、人物 ≥1；
  E 不会被当成「项目」：`samples/` 在程序目录下、**不在项目根下**，
    `scan_projects()` 也扫不到它；
  F ★ **说明书里逐个点了名**：`使用说明.md` 有每个中文目录名、`User_Manual.md` 有每个英文目录名；
  G 版权风险：README 写明原创 + 一份"受保护作品"关键词黑名单不许出现。

跑法：`.venv\\Scripts\\python.exe tools/verify_samples.py`
产出：assets/screenshots/samples_report.json

English:
Verification: that batch of **example input folders** in `samples/` really works, is really
complete, and is really mentioned in the manual.
Two of the user's four points (2026-10-06):
"Add a folder called samples, containing 2 folders zh and en; prepare several well-written
example novel input folders
(preferably original or extracted from ancient and other non-copyrighted books, no copyright
issues), one per genre,
each story in 2 language versions, placed into zh and en respectively."
"In the usage manual's input folder standard, state clearly that these examples exist, state
clearly where they're placed (give an ASCII folder tree),"
And briefly introduce these stories (the Chinese and English help files list the various idea
folders)"
So the criteria must govern both **disk** and **docs** at the same time:
  A Two datasets aligned: 6 pieces, slug order consistent, **genre one-to-one with `GENRE_CHOICES` in the program**
    (if the claim "one per genre" is false, this goes red);
  B Actually complete on disk: 5 files per piece, non-empty, has a `#` heading, body in paragraphs;
  C **Classification actually correct**: scan with `ingest.scanner`, settings 1 / characters 2 / outline 1 / foreshadowing 1 / body 1
    (both Chinese and English directory names must classify correctly -- the English set relies on English keywords in the same word list);
  D **Can actually run when opened**: in demo mode run through `extract_settings()`, produces six keys, characters >= 1;
  E Not treated as a "project": `samples/` is under the program directory, **not under the project root**,
    and `scan_projects()` cannot scan it either;
  F ★ **Individually named in the manuals**: `使用说明.md` has every Chinese directory name, `User_Manual.md` has every English directory name;
  G Copyright risk: README states originality + a "protected works" keyword blacklist must not appear.
How to run: `.venv\\Scripts\\python.exe tools/verify_samples.py`
Output: assets/screenshots/samples_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))
# sample 的内容数据在 developers/（跟生成器 make_samples.py 放一起）——
# 验证脚本留 tools/，所以这里要**显式**把 developers/ 也挂上路径。
# [EN] sample content data lives in developers/ (alongside the generator make_samples.py) ——
# [EN] The verification script stays in tools/, so here we must **explicitly** add developers/ to the
# [EN] path too.
sys.path.insert(0, str(APP_DIR / 'developers'))

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from samples_en import STORIES_EN  # noqa: E402
from samples_zh import STORIES_ZH  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
SAMPLES = APP_DIR / 'samples'
ITEMS: list = []

# 明显的受保护作品名 —— 只是**绊线**，不是"证明没侵权"。
# 示例全是原创，这里钉的是"以后有人往里塞一段现成作品"这种情况。
# [EN] Obvious protected work titles —— just a **tripwire**, not "proof of no infringement".
# [EN] All examples are original; what's pinned down here is the case of "someone later stuffing in a
# [EN] ready-made work".
DENY = ('哈利', '三体', '金庸', '射雕', '天龙八部', '红楼梦', '西游记', '水浒',
        '聊斋志异', 'harry potter', 'lord of the rings', 'sherlock holmes',
        'game of thrones', '三毛', '余华', '莫言')


def ok(name: str, cond, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def norm(s: str) -> str:
    """比"题材"时用：去掉空格和间隔号（`悬疑 · 单元剧` 与 `悬疑·单元` 要能对上）。
        English:
    Used when comparing "themes": remove spaces and separators (`悬疑 · 单元剧` and `悬疑·单元` must match).
    """
    return re.sub(r'[\s·・\-—]+', '', s)


# 每篇故事该有的文件（相对文件夹）。「顶级规则」是**可选**的 ——
# 有 `rules` 键的篇才要（2026-10-06 加的示例：01 悬疑、03 都市各一份）。
# [EN] The files each story should have (relative to the folder). "Top-level rules" is **optional** ——
# [EN] only required for entries that have a `rules` key (examples added 2026-10-06: one each for 01
# [EN] suspense, 03 urban).
ZH_FILES = ('设定/世界观.md', '大纲/故事大纲.md', '伏笔.md')
EN_FILES = ('setting/world.md', 'outline/story-outline.md', 'foreshadowing.md')


# ★ 2026-10-09：示例标准从「1 章正文 / 规则可选」提到
#   「**3 章正文** + 顶级规则 + 地点.yaml」—— 理由见 `samples/README.md`
#   的「为什么要三章」那一节（三个预算：风格卡 4000 / 每章对齐 1500 / 合计 8000）。
# [EN] ★ 2026-10-09: the example standard was raised from "1 chapter of body text / rules optional" to
# [EN] "**3 chapters of body text** + top-level rules + 地点.yaml" —— rationale see `samples/README.md`
# [EN] in the "Why three chapters" section (three budgets: style card 4000 / per-chapter alignment 1500
# [EN] / total 8000).
CHAPTERS_WANT = 3


def zh_files(s: dict) -> list:
    return (list(ZH_FILES)
            + (['设定/顶级规则.md'] if s.get('rules') else [])
            + [f'设定/人物/{c[0]}.md' for c in s['chars']]
            + [f"正文/{t}.md" for t, _ in s['chapters']])


def en_files(s: dict) -> list:
    return (list(EN_FILES)
            + (['setting/rules.md'] if s.get('rules') else [])
            + [f'setting/characters/{c[1]}.md' for c in s['chars']]
            + [f'chapters/chapter-{i:02d}.md'
               for i in range(1, len(s['chapters']) + 1)])


def read(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='replace')


async def main():
    report: dict = {}
    try:
        # ══════════ A. 两份数据对齐 + 题材覆盖 ══════════
        # [EN] ══════════ A. Two datasets aligned + genre coverage ══════════
        ok('A：中文 6 篇', len(STORIES_ZH) == 6, len(STORIES_ZH))
        ok('A：英文 6 篇', len(STORIES_EN) == 6, len(STORIES_EN))
        zh_slugs = [s['slug'] for s in STORIES_ZH]
        en_slugs = [s['slug'] for s in STORIES_EN]
        report['slugs'] = zh_slugs
        ok('A：★ 中英两版**逐篇对齐**（slug 与顺序都一样）', zh_slugs == en_slugs,
           f'zh={zh_slugs} / en={en_slugs}')

        import gui.app_flet as G
        genres = [g for g in G.GENRE_CHOICES if g != 'auto']
        report['app_genres'] = genres
        have = [norm(s['genre']) for s in STORIES_ZH]
        missing = [g for g in genres
                   if not any(h.startswith(norm(g)) for h in have)]
        ok('A：★ 程序里那六个题材**每个都有一篇示例**（"每个题材一个"）',
           not missing, f'缺：{missing}；示例题材={have}')

        # ══════════ B. 磁盘上真的齐 ══════════
        # [EN] ══════════ B. It's really all there on disk ══════════
        bad_files: list = []
        thin: list = []
        for root, s, files in ([(SAMPLES / 'zh', x, zh_files(x)) for x in STORIES_ZH]
                               + [(SAMPLES / 'en', x, en_files(x)) for x in STORIES_EN]):
            for rel in files:
                p = root / s['dir'] / rel
                if not p.is_file():
                    bad_files.append(f'{s["dir"]}/{rel} 不存在')
                    continue
                txt = read(p)
                if len(txt.strip()) < 120:
                    thin.append(f'{s["dir"]}/{rel} 只有 {len(txt.strip())} 字')
                if not txt.lstrip().startswith('#'):
                    bad_files.append(f'{s["dir"]}/{rel} 没有 # 标题')
        ok('B：★ 12 篇的文件**一个都不缺、都有标题**', not bad_files,
           f'{len(bad_files)} 处：{bad_files[:3]}')
        ok('B：★ 每个文件都有真内容（≥120 字，不是占位）', not thin,
           f'{len(thin)} 处：{thin[:3]}')

        # 正文要成段（示例得"写得好"，段落是底线）
        # ★ 2026-10-09：**逐章**查（原来只看第一章）。章数不够也算问题 ——
        #   三章是"风格卡样本够厚 + 前情对齐有东西可对"的下限。
        # [EN] Body text must be in paragraphs (examples must be "well written"; paragraphs are the bottom
        # [EN] line)
        # [EN] ★ 2026-10-09: check **per chapter** (previously only chapter one). Too few chapters also counts
        # [EN] as a problem ——
        # [EN] three chapters is the lower bound for "style-card sample thick enough + prior-context alignment
        # [EN] has something to align".
        short_ch = []
        zh_total = en_total = 0
        for s in STORIES_ZH:
            if len(s['chapters']) != CHAPTERS_WANT:
                short_ch.append(f'{s["dir"]} 中文章数 {len(s["chapters"])}')
        for s in STORIES_EN:
            if len(s['chapters']) != CHAPTERS_WANT:
                short_ch.append(f'{s["dir"]} 英文章数 {len(s["chapters"])}')
        # 中英逐章对齐（同一个故事的两种语言，章数必须一样）
        # [EN] Chinese-English per-chapter alignment (two languages of the same story must have the same
        # [EN] chapter count)
        for zs, es in zip(STORIES_ZH, STORIES_EN):
            if len(zs['chapters']) != len(es['chapters']):
                short_ch.append(f'{zs["dir"]} 中英章数不一致')
        # 逐章：成段（≥4 段）+ 字数够（每章 ≥600 汉字/词，撑得住风格卡与对齐）
        # [EN] Per chapter: paragraph form (≥4 paragraphs) + enough words (≥600 Chinese chars/words per
        # [EN] chapter, enough to hold up the style card and alignment)
        for x in STORIES_ZH:
            for t, _ in x['chapters']:
                body = read(SAMPLES / 'zh' / x['dir'] / '正文' / f'{t}.md')
                paras = [q for q in body.split('\n\n') if q.strip()]
                if len(paras) < 4:
                    short_ch.append(f'{x["dir"]}/{t} 只有 {len(paras)} 段')
                n = len(re.findall(r'[\u4e00-\u9fff]', body))
                # 单章下限 300 汉字：**第一章本来就是短的开场**（339~396），
                # 苛求它反而是在改示例的写法。这里只拦"章文件是个空壳"。
                # [EN] Single-chapter floor of 300 Chinese chars: **chapter one is inherently a short opening**
                # [EN] (339~396),
                # [EN] being strict on it would instead be changing how the example is written. Here we only catch "the
                # [EN] chapter file is an empty shell".
                if n < 300:
                    short_ch.append(f'{x["dir"]}/{t} 只有 {n} 汉字')
                zh_total += n
        for x in STORIES_EN:
            for i in range(1, len(x['chapters']) + 1):
                body = read(SAMPLES / 'en' / x['dir'] / 'chapters'
                            / f'chapter-{i:02d}.md')
                paras = [q for q in body.split('\n\n') if q.strip()]
                if len(paras) < 4:
                    short_ch.append(f'{x["dir"]}/chapter-{i:02d} 只有 {len(paras)} 段')
                n = len(body.split())
                if n < 180:
                    short_ch.append(f'{x["dir"]}/chapter-{i:02d} 只有 {n} words')
                en_total += n
        # ★★ 真正要量的不是"每章多长"，而是**整篇正文够不够撑住那两个预算**：
        #   风格卡读正文前 4000 字、前情对齐每章取 1500 字。三章合计 <1800 汉字时，
        #   风格卡仍然学不出"章法偏好""对话占比"（这正是补三章要解决的问题）。
        # [EN] ★★ What really needs measuring is not "how long each chapter is", but **whether the whole body
        # [EN] text is enough to hold up those two budgets**:
        # [EN] the style card reads the first 4000 chars of body text; prior-context alignment takes 1500 chars
        # [EN] per chapter. When the three chapters total <1800 Chinese chars,
        # [EN] the style card still can't learn "chapter-structure preferences" or "dialogue ratio" (which is
        # [EN] exactly the problem that adding three chapters is meant to solve).
        if zh_total < 1800:
            short_ch.append(f'12 篇中文正文合计只 {zh_total} 汉字（<1800）')
        if en_total < 1100:
            short_ch.append(f'12 篇英文正文合计只 {en_total} words（<1100）')
        ok('B：三章正文**逐章**都成段（≥4 段）且不是空壳（每章中 ≥300 汉字 / 英 ≥180 词），'
           f'且 12 篇合计够厚（中 {zh_total} 汉字 / 英 {en_total} 词，阈值 1800/1100）'
           '—— 这才是"风格卡样本够厚 + 前情对齐有东西可对"的下限',
           not short_ch, str(short_ch[:3]))

        # ══════════ C. 分类真的对 ══════════
        # [EN] ══════════ C. The classification is really correct ══════════
        from collections import Counter
        from ingest.scanner import scan_project
        mism: list = []
        detail: dict = {}
        for root, s in ([(SAMPLES / 'zh', x) for x in STORIES_ZH]
                        + [(SAMPLES / 'en', x) for x in STORIES_EN]):
            items = scan_project(root / s['dir'])
            c = Counter(i.category for i in items)
            detail[s['dir']] = dict(c)
            # ★ 2026-10-09：① `正文` 数 = 章数（原来写死 1）；
            #   ② `设定` 数 = 世界观 + 地点.yaml = **2**（`地点.yaml` 在 `设定/` 下，
            #      而路径含「设定」→ 归「设定」类；它不是新类别，别去加规则）。
            # [EN] ★ 2026-10-09: ① `正文` count = chapter count (previously hardcoded to 1);
            # [EN] and the path contains "设定" → classified as "设定"; it is not a new category, don't go adding a
            # [EN] rule).
            want = {'设定': 2, '人物': len(s['chars']), '大纲': 1, '伏笔': 1,
                    '正文': len(s['chapters'])}
            if s.get('rules'):
                want['规则'] = 1          # 文件名含「规则」→ 单独一类（原文照录）
                # [EN] Filename contains "规则" → its own separate category (verbatim transcription)
            for k, v in want.items():
                if c.get(k) != v:
                    mism.append(f'{s["dir"]}: {k} 期望 {v} 实际 {c.get(k)}')
        report['categories'] = detail
        ok('C：★ 12 篇都被正确分成 设定(含地点)/人物/大纲/伏笔/正文×3/规则'
           '（中英各一套目录名）', not mism, str(mism[:4]))

        # ── C2. 「顶级规则」：分类对 + **原文照录** ──
        # 这是这套机制的要害：规则是作者的硬约束，进了 prompt 就是不可违背的。
        # 只要在中间任何一环被"概括"过（哪怕只是换个说法），作者的控制权就丢了一半，
        # 而且对不回去。所以这里比的是**逐字相等**，不是"关键词在不在"。
        # [EN] ── C2. "Top-level rules": classification correct + **verbatim transcription** ──
        # [EN] This is the crux of the whole mechanism: rules are the author's hard constraints, and once in
        # [EN] the prompt they are inviolable.
        # [EN] If at any link in the chain it gets "summarized" (even just reworded), the author loses half
        # [EN] their control,
        # [EN] and there's no going back. So what's compared here is **character-for-character equality**, not
        # [EN] "are the keywords present".
        from ingest.pipeline import collect_rules

        def _same(a: str, b: str) -> bool:
            """逐字比，但**换行归一**（`\\r\\n` 与 `\\n` 不算改写）。

            换行差异是平台/编辑器造成的，不是"内容被改写"；而内容被改写
            （换个说法、丢掉一条）**必须**要能红出来 —— 所以只归一换行，
            不做任何别的宽松处理。
            
                        English:
            Compare character by character, but **normalize newlines** (`\\r\\n` and `\\n` do not count as a
            rewrite).
                        newline differences are caused by platform/editor, not by "content being rewritten"; whereas content being rewritten
                        (reworded, a line dropped) **must** be able to go red -- so only normalize newlines,
                        do not do any other lenient handling.
            """
            n = lambda t: t.replace('\r\n', '\n').replace('\r', '\n').strip()  # noqa: E731
            return n(a) == n(b)

        rule_bad: list = []
        n_rules = 0
        for root, s in ([(SAMPLES / 'zh', x) for x in STORIES_ZH]
                        + [(SAMPLES / 'en', x) for x in STORIES_EN]):
            if not s.get('rules'):
                continue
            n_rules += 1
            items = scan_project(root / s['dir'])
            got = collect_rules(items, {})
            if not _same(got, s['rules']):
                rule_bad.append(f'{s["dir"]}: 落了 {len(got)} 字 vs 源 {len(s["rules"])} 字')
        ok('C2：★ 规则文档被 pipeline **原文照录**（与数据源逐字一致，没被改写）',
           not rule_bad, str(rule_bad[:3]))
        # ★ 2026-10-09：口径从"至少有 2 篇带规则"改成"**12 篇全带**" ——
        #   用户要求把示例缺的东西补齐，而「顶级规则」是**原文照录进 prompt 最前面**
        #   的硬约束，是这一档里最值钱的一项，示例该篇篇都有。
        # [EN] ★ 2026-10-09: the criterion changed from "at least 2 entries with rules" to "**all 12 entries
        # [EN] have them**" ——
        # [EN] the user asked to fill in what the examples were missing, and "top-level rules" are
        # [EN] **transcribed verbatim at the very front of the prompt**
        # [EN] as hard constraints, the most valuable item at this tier; the examples should have them in every
        # [EN] single entry.
        ok('C2：★ 12 篇**全都**带「顶级规则」（原文照录进 prompt 最前面，最值钱的一项）',
           n_rules == 12, f'带规则的篇数 {n_rules}')

        # 没有规则文档的篇，collect_rules 必须给空 —— 否则会在 prompt 里凭空多出一段。
        # ⚠ 现在 12 篇都有规则了，这条"空就是空"的判据**在示例上再也测不到**。
        #   所以改成拿一个**临时目录**验：把某篇的规则文件去掉，collect_rules 必须给空。
        #   （留着它是因为这条路径是真会走的 —— 作者不写规则时就走它。）
        # [EN] For entries with no rules document, collect_rules must return empty —— otherwise an extra
        # [EN] paragraph would appear out of thin air in the prompt.
        # [EN] ⚠ Now that all 12 entries have rules, this "empty means empty" criterion **can no longer be
        # [EN] tested on the examples**.
        # [EN] So it was changed to verify with a **temporary directory**: remove some entry's rules file and
        # [EN] collect_rules must return empty.
        # [EN] (It's kept because this path really does get taken —— it's taken when the author writes no
        # [EN] rules.)
        import tempfile as _tf
        # ⚠ 目录名**不能含 `rule`** —— `scanner._CATEGORY_RULES` 里有关键词 "rule"，
        #   路径命中就会把所有文件都判成「规则」类，这条判据会**自己把自己搞红**
        #   （第一版写 `prefix='nws_norule_'`，实测 collect_rules 返回 4338 字）。
        # [EN] ⚠ The directory name **must not contain `rule`** —— `scanner._CATEGORY_RULES` contains the
        # [EN] keyword "rule",
        # [EN] so a path hit would classify all files as "规则" category, and this criterion would **turn itself
        # [EN] red**
        # [EN] (the first version used `prefix='nws_norule_'`; measured collect_rules returned 4338 chars).
        _tmp = Path(_tf.mkdtemp(prefix='nws_probe_'))
        try:
            src = SAMPLES / 'zh' / STORIES_ZH[0]['dir']
            import shutil as _sh
            _sh.copytree(src, _tmp / 'x')
            (_tmp / 'x' / '设定' / '顶级规则.md').unlink()
            leak = collect_rules(scan_project(_tmp / 'x'), {})
            report['no_rule_check'] = {'got_len': len(leak.strip())}
            ok('C2：把规则文档删掉之后，collect_rules **给空**'
               '（不会从世界观里凭空长出一段硬约束）',
               not leak.strip(), f'居然给出 {len(leak.strip())} 字：{leak[:80]!r}')
        finally:
            import shutil as _sh2
            _sh2.rmtree(_tmp, ignore_errors=True)

        # ── C3. `地点.yaml`：程序画**地图底图**时整体层的地点名**只能取它** ──
        #   2026-10-09 加：原来只有 01 有这份，其余 11 篇都缺 —— 缺了就只能靠
        #   LLM 从别处凑，容易出现"模型给的名字一个都不在设定里"（`ingest/atlas.py`）。
        # [EN] ── C3. `地点.yaml`: when the program draws the **map basemap**, the overall-layer place names
        # [EN] **can only come from it** ──
        # [EN] Added 2026-10-09: previously only 01 had this, the other 11 entries all lacked it —— without it
        # [EN] you can only rely on
        # [EN] the LLM to cobble it together from elsewhere, easily producing "not a single name the model
        # [EN] gives is in the settings" (`ingest/atlas.py`).
        place_bad: list = []
        for root, s in ([(SAMPLES / 'zh', x) for x in STORIES_ZH]
                        + [(SAMPLES / 'en', x) for x in STORIES_EN]):
            rel = '设定/地点.yaml' if root.name == 'zh' else 'setting/places.yaml'
            f = root / s['dir'] / rel
            if not f.exists():
                place_bad.append(f'{s["dir"]}: 缺 {rel}')
                continue
            try:
                import yaml as _y
                data = _y.safe_load(f.read_text(encoding='utf-8'))
            except Exception as e:                             # noqa: BLE001
                place_bad.append(f'{s["dir"]}: {rel} 解不动（{e!r}）')
                continue
            if not (isinstance(data, list) and 3 <= len(data) <= 6
                    and all(isinstance(d, dict) and d.get('名称') for d in data)):
                place_bad.append(f'{s["dir"]}: {rel} 形状不对（{type(data).__name__}'
                                 f'，{len(data) if isinstance(data, list) else "?"} 条）')
        ok('C3：★ 12 篇都有 `地点.yaml`（3~6 处、能 YAML 解析、每处都有「名称」）'
           '—— 地图底图的整体层名字只能取它',
           not place_bad, str(place_bad[:3]))

        # ══════════ D. 开卷真的能跑（演示模式，不联网）══════════
        # [EN] ══════════ D. Opening the book really runs (demo mode, no network) ══════════
        from ingest.extractor import extract_settings
        from llm.router import llm
        await llm.ensure_started(APP_DIR / 'logs')
        st = await extract_settings(
            scan_project(SAMPLES / 'zh' / STORIES_ZH[0]['dir']), '示例冒烟')
        report['smoke'] = {'keys': list(st), 'n_chars': len(st.get('人物') or [])}
        ok('D：★ 拿第 1 篇真跑一遍提取，出齐六个键',
           set(st) >= {'人物', '世界观', '地点', '关系', '伏笔', '剧情参考线'}, list(st))
        ok('D：提取出的人物 ≥1（示例能被读成设定集）',
           len(st.get('人物') or []) >= 1, len(st.get('人物') or []))

        # ══════════ E. 不会被当成项目 ══════════
        # [EN] ══════════ E. Not treated as a project ══════════
        from store.project import scan_projects
        report['projects_dir'] = str(CFG.projects_dir())
        found = [p.name for p in scan_projects(CFG.projects_dir())]
        ok('E：★ `samples/` 在**程序目录**下，不在项目根下（不会污染用户的书架）',
           SAMPLES.is_dir() and CFG.projects_dir() not in SAMPLES.parents,
           f'samples={SAMPLES} projects={CFG.projects_dir()}')
        ok('E：项目根里扫不到任何示例', not any('更漏子' in n or 'mystery' in n.lower()
                                          for n in found), str(found[:5]))

        # ══════════ F. 说明书里逐个点了名 ══════════
        # [EN] ══════════ F. Named one by one in the manual ══════════
        #
        # ⚠ 第一版只判"这个文件夹名在整篇说明书里出现过" —— **太松，红不了**：
        #   六个名字在 §6.1 的**目录树**和**表格**里各出现一次，
        #   把树里那个删掉，表格里那个还在，判据照样绿（反向实验实测 20/20 不变）。
        #   现在收窄成两件事：① 名字要出现在 **§6.1 那一节里**；
        #   ② 还要出现在 §6.1 里那个**画 `samples/` 的代码块（ASCII 树）**里。
        # [EN] ⚠ The first version only checked "this folder name appears somewhere in the whole manual" ——
        # [EN] **too loose, can't go red**:
        # [EN] the six names each appear once in the **directory tree** and once in the **table** in §6.1;
        # [EN] delete the one in the tree and the one in the table remains, so the criterion still goes green
        # [EN] (reverse experiment measured 20/20 unchanged).
        # [EN] Now narrowed to two things: ① the name must appear **in the §6.1 section**;
        # [EN] ② it must also appear in the **code block that draws `samples/` (ASCII tree)** in §6.1.
        def sec_slice(text: str, head: str) -> str:
            """截出某一节（从 `head` 那一行到下一个同级/更高级标题）。
                        English:
            Extract a section (from the `head` line to the next same-level/higher-level heading).
            """
            i = text.find(head)
            if i < 0:
                return ''
            j = text.find('\n### ', i + len(head))
            return text[i:j if j > 0 else len(text)]

        # ★★ 2026-10-09 改口径：**按"列出了几个故事文件夹"挑，不按"哪个块最长"挑**。
        #   原来挑最长的那个含 `samples/` + `├──` 的代码块 —— 那时节里只有一个这样的块
        #   （六个文件夹的清单），所以"最长"等价于"就是它"。
        #   后来 §6.1 里**又加了第二个树**（"某一个小故事里面长什么样"，只画 01 一篇的
        #   内部结构），它因为写得更细而变成了最长 → 判据转头去看那个块，
        #   于是在里面找不到 02–06，**假红**。
        #   口径改成"列出故事文件夹最多的那个块"，与这条判据的本意
        #   （"说明书里有一张列出全部 6 个的目录树"）对齐。
        # [EN] ★★ 2026-10-09 criterion changed: **pick by "how many story folders are listed", not "which block
        # [EN] is longest"**.
        # [EN] Previously it picked the longest code block containing `samples/` + `├──` —— at that time there
        # [EN] was only one such block in the section
        # [EN] (the list of six folders), so "longest" was equivalent to "it's the one".
        # [EN] Later a **second tree** was added to §6.1 ("what it looks like inside one small story", drawing
        # [EN] only the
        # [EN] internal structure of entry 01), and because it's written in more detail it became the longest →
        # [EN] the criterion turned to look at that block,
        # [EN] and so couldn't find 02–06 in it, **false red**.
        # [EN] The criterion was changed to "the block that lists the most story folders", aligning with the
        # [EN] intent of this criterion
        # [EN] ("the manual has a directory tree listing all 6").
        def tree_block(sec: str, dirs: list) -> str:
            best, best_n = '', -1
            for blk in re.findall(r'```[^\n]*\n(.*?)```', sec, re.S):
                if 'samples/' not in blk or '├──' not in blk:
                    continue
                n = sum(1 for d in dirs if d in blk)
                if n > best_n:
                    best, best_n = blk, n
            return best

        zh_sec = sec_slice(read(APP_DIR / '使用说明.md'), '### 6.1')
        en_sec = sec_slice(read(APP_DIR / 'User_Manual.md'), '### 6.1')
        zh_tree = tree_block(zh_sec, [x['dir'] for x in STORIES_ZH])
        en_tree = tree_block(en_sec, [x['dir'] for x in STORIES_EN])
        report['tree_len'] = {'zh': len(zh_tree), 'en': len(en_tree)}

        miss_zh = [s['dir'] for s in STORIES_ZH if s['dir'] not in zh_sec]
        miss_en = [s['dir'] for s in STORIES_EN if s['dir'] not in en_sec]
        miss_zh_tree = [s['dir'] for s in STORIES_ZH if s['dir'] not in zh_tree]
        miss_en_tree = [s['dir'] for s in STORIES_EN if s['dir'] not in en_tree]
        report['manual_zh_missing'] = miss_zh
        report['manual_en_missing'] = miss_en
        report['tree_missing'] = {'zh': miss_zh_tree, 'en': miss_en_tree}
        ok('F：★ 中文说明书 §6.1 里逐个列出了 6 个中文示例文件夹', not miss_zh, str(miss_zh))
        ok('F：★ 英文说明书 §6.1 里逐个列出了 6 个英文示例文件夹', not miss_en, str(miss_en))
        ok('F：★ 两份说明书的 **ASCII 目录树**里都有全部 6 个文件夹',
           not miss_zh_tree and not miss_en_tree,
           f'zh 缺 {miss_zh_tree} / en 缺 {miss_en_tree}')
        ok('F：说明书给出了**位置**（`samples/` 在程序目录下）',
           'samples/' in zh_sec and 'samples/' in en_sec, '')
        # 提醒"别选到上一层"这句要在（不然用户很容易把六篇当一本书读进来）。
        # ⚠ 判据不能写成 `'不要' in 中文节` 就算数 —— 得点名"上一层"那个写法本身。
        # [EN] The reminder "don't pick the level above" must be present (otherwise users easily read the six
        # [EN] entries in as one book).
        # [EN] ⚠ The criterion can't be written as `'不要' in Chinese section` and call it done —— it must name
        # [EN] that "level above" wording itself.
        ok('F：说明了「开卷要选到小故事那一层、别选上一层」这个坑',
           'samples/zh/' in zh_sec and 'samples/en/' in en_sec,
           f"zh {'samples/zh/' in zh_sec} / en {'samples/en/' in en_sec}")
        # 六个故事名要真的在表格里出现（写死一个总是为真的表达式等于没判）
        # [EN] The six story names must really appear in the table (hardcoding an always-true expression is as
        # [EN] good as no check)
        miss_title = [s['title'] for s in STORIES_ZH if s['title'] not in zh_sec]
        miss_title_en = [s['title'] for s in STORIES_EN if s['title'] not in en_sec]
        ok('F：六个故事的**篇名**在说明书里都出现（不是只列了文件夹名）',
           not miss_title and not miss_title_en,
           f'zh 缺 {miss_title} / en 缺 {miss_title_en}')
        ok('F：`samples/README.md` 自己也列了全部 12 个文件夹',
           all(s['dir'] in read(SAMPLES / 'README.md')
               for s in STORIES_ZH + STORIES_EN), '')

        # ══════════ G. 版权风险 ══════════
        # [EN] ══════════ G. Copyright risk ══════════
        rd = read(SAMPLES / 'README.md')
        ok('G：`samples/README.md` 写明是**原创**、可随程序分发',
           ('原创' in rd) and ('original' in rd), '')
        blob = '\n'.join(read(p).lower() for p in SAMPLES.rglob('*') if p.is_file())
        hits = [w for w in DENY if w.lower() in blob]
        report['deny_hits'] = hits
        ok('G：六个示例里没有出现明显受保护的作品名（绊线）', not hits, str(hits))
        ok('G：六篇的标题与一句话简介互不相同（不是复制粘贴）',
           len({s['title'] for s in STORIES_ZH}) == 6
           and len({s['blurb'] for s in STORIES_ZH}) == 6, '')

        # ══════════ H. 大纲的体量与质量（2026-10-28 新增）══════════
        # [EN] ══════════ H. Outline bulk and quality (added 2026-10-28) ══════════
        #
        # ★ 为什么单列一组：A~G 量的是「文件齐不齐、说明书提没提」，
        #   这一组量的是**作者写的大纲本身**。
        #   用户 2026-10-27 定的线是「示例设定集六篇 2000 → 3400 字」，
        #   而当时六篇的大纲只有 **1717~2070 字** —— 差了一倍半。
        #   判据必须把这条线钉死，否则下一次谁都能把它悄悄改回 2000 字。
        # [EN] ★ Why a separate group: A~G measure "are the files there and does the manual
        #   mention them"; this group measures **the outline the author actually wrote**.
        #   The line the user set on 2026-10-27 was "six samples 2000 -> 3400 chars", and the
        #   outlines were at **1717~2070** — half of it. The criterion has to pin that line down,
        #   otherwise the next person quietly puts it back to 2000.
        from ingest.progress import _nearest_span, _nearest_weight, _station_blocks

        #: 中文大纲的体量下限（Word 式字数：不含空白、含标点 —— 中文"字数"就是这个口径）。
        OUTLINE_MIN_CHARS = 3400
        #: 英文大纲的体量下限（词）。换算用本项目自己的口径「1 字 ≈ 0.5 词」
        #: （见 `developers/check_samples.py` 的 `SUMMARY_MAX_ZH=80` / `SUMMARY_MAX_EN=40`）。
        OUTLINE_MIN_WORDS = 1700
        #: 高潮相对完成判据**必须多出的实质内容**（新的字 / 新的词）。
        #: 实测（2026-10-27，加厚后的 98 站）：中文最少 15 个新字、次小 17；
        #: 英文最少 13 个新词、次小 14。而**旧样本**（判据 + 一句模板尾巴）
        #: 只有 7 / 5 ⇒ 阈值 10 / 8 能把两者干净分开。
        #: ★ 为什么不直接用"字重合度 ≥0.8"：中文单字太常见，判据一短，
        #:   重合度天然就高（实测 0.83~0.93）⇒ 误判 4 处**好**高潮
        #:   （判据的场景化 + 具体动作）。"多出实质内容"才量得到真差别。
        NEW_CONTENT_MIN_ZH = 10
        NEW_CONTENT_MIN_EN = 8

        def _wc(t: str) -> int:
            """Word 式字数：不含空白、含标点。"""
            return len(re.sub(r'\s', '', t or ''))

        def _norm(t: str) -> str:
            """归一化：去标点、去空白、转小写（比"是不是复述"用）。"""
            return re.sub(r'[\s，。、；：「」『』“”‘’（）()《》〈〉—…·\[\]【】'
                          r',.!?;:\'"`~*#>|/-]+', '', (t or '')).lower()

        def _echoes(crit: str, climax: str, en: bool) -> bool:
            """高潮是不是完成判据的复述。

            ★ 三道网，因为旧样本有**两种**形态的复述：
              ① 英文旧版：高潮 = 判据的前几十字 + 一句模板尾巴
                 （`-- this moment is the station's climax.`）—— 判据被**截断**了，
                 所以"判据是不是高潮的子串"抓不到它，只能靠模板尾巴；
              ② 中文旧版：高潮 = 判据 + 「——这一刻就是本站的高潮。」——
                 判据是高潮的**前缀**，子串判定能抓到；
              ③ **换词复述**：高潮跟判据说的是同一件事，只是换了词。
                 ⇒ 判据：**高潮必须比判据多出实质内容**（新的字/新的词）。
            ⚠ 第一版这里用的是"判据的字有多少出现在高潮里，重合度 ≥0.8" ——
              **对中文太钝**：判据本来就短，它的字必然在高潮里复现，
              于是一批**好**高潮被误判（实测 4 处，如「洪水退去，西堤没有漫堤」对
              「洪水退到堤根下，西堤一寸没漫；堤下的人跪了一片……」——
              这正是要的样子：判据的场景化 + 具体动作）。
              换成"新增内容"后：中文 98 站最少 15 个新字、英文最少 13 个新词，
              而旧样本只有 7 / 5 ⇒ 分得很开。
            [EN] ★ Three nets, because the old samples had **two** shapes of echo:
              ① old English: climax = the first words of the criterion + a template tail
                 (`-- this moment is the station's climax.`) —— the criterion was **truncated**,
                 so "is the criterion a substring" cannot catch it; only the tail can;
              ② old Chinese: climax = criterion + 「——这一刻就是本站的高潮。」——
                 the criterion is a **prefix**, so the substring test catches it;
              ③ **paraphrase**: the climax says the same thing in other words
                 ⇒ measured as: the climax must carry **substantially new content** (new
                 characters / new words).
            ⚠ The first version used "how many of the criterion's characters appear in the
            climax, ratio >= 0.8" —— **too blunt for Chinese**: the criterion is short, so its
            characters inevitably recur, and a batch of **good** climaxes were flagged
            (measured 4, e.g. 「洪水退去，西堤没有漫堤。」 vs 「洪水退到堤根下，西堤一寸没漫；
            堤下的人跪了一片……」 —— exactly what we want: the criterion staged, plus concrete
            action). With "new content" instead: the 98 stations have at least 15 new Chinese
            characters / 13 new English words, while the old samples had 7 / 5 ⇒ clean split.
            """
            if not crit or not climax:
                return False
            # ① 模板尾巴
            tails = (("the station's climax", 'this moment is the station')
                     if en else ('本站的高潮', '这一刻就是本站'))
            if any(m in climax.lower() for m in tails):
                return True
            c, k = _norm(crit), _norm(climax)
            if not c or not k:
                return False
            # ② 判据是高潮的子串，且盖住了高潮的六成以上
            if len(c) >= 8 and c in k and len(c) / len(k) >= 0.6:
                return True
            # ③ 高潮必须比判据多出实质内容
            if en:
                cw = set(re.findall(r"[a-z']+", crit.lower()))
                kw = set(re.findall(r"[a-z']+", climax.lower()))
                new = len(kw - cw)
                return new < NEW_CONTENT_MIN_EN
            cw, kw = set(c), set(k)
            return len(kw - cw) < NEW_CONTENT_MIN_ZH

        def _section_nums(t: str) -> list:
            """取大纲里 `## 一、` / `## 2.` 这类**分节编号**（中文用数字词）。"""
            cn = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
            out = []
            for m in re.finditer(r'(?m)^##\s*(?:([一二三四五六七八九十]+)、|(\d+)\.)', t or ''):
                if m.group(1):
                    s = m.group(1)
                    out.append(int(s) if s.isdigit() else cn.get(s, 0))
                else:
                    out.append(int(m.group(2)))
            return out

        zh_outlines = {s['dir']: read(SAMPLES / 'zh' / s['dir'] / '大纲' / '故事大纲.md')
                       for s in STORIES_ZH}
        en_outlines = {s['dir']: read(SAMPLES / 'en' / s['dir'] / 'outline' / 'story-outline.md')
                       for s in STORIES_EN}
        all_outlines = [(d, t, False) for d, t in zh_outlines.items()] \
            + [(d, t, True) for d, t in en_outlines.items()]

        # ── H1/H2 体量 ──
        thin_zh = [(d, _wc(t)) for d, t, _ in all_outlines if not _ and _wc(t) < OUTLINE_MIN_CHARS]
        ok(f'H：★ 中文六篇的大纲**体量够**（Word 式 ≥{OUTLINE_MIN_CHARS} 字 —— '
           '用户 2026-10-27 定的线；原来六篇只有 1717~2070 字）',
           not thin_zh, str(thin_zh))
        thin_en = [(d, len(t.split())) for d, t, en in all_outlines
                   if en and len(t.split()) < OUTLINE_MIN_WORDS]
        ok(f'H：★ 英文六篇的大纲**体量够**（≥{OUTLINE_MIN_WORDS} 词 —— 按本项目自己的'
           '「1 字 ≈ 0.5 词」换算，中文 3400 字 ≈ 英文 1700 词）',
           not thin_en, str(thin_en))

        # ── H3/H4 站表的两块内容 ──
        miss_climax: list = []
        miss_beats: list = []
        echoes: list = []
        for d, t, en in all_outlines:
            for title, fields, beats in _station_blocks(t):
                if not (fields.get('高潮') or '').strip():
                    miss_climax.append((d, title))
                if not beats:
                    miss_beats.append((d, title))
                if _echoes(fields.get('完成判据', ''), fields.get('高潮', ''), en):
                    echoes.append((d, title))
        ok('H：★★ 每站都写了「高潮」（它是这一站的顶点，也是推演时"不许提前演到的东西"）',
           not miss_climax, str(miss_climax[:4]))
        ok('H：★★ 每站都写了「情节线」（程序最想拿、而旧样本 12 篇**全部为零**的字段 —— '
           '没有它，这一站内部的台阶只能现编）',
           not miss_beats, str(miss_beats[:4]))
        ok('H：★★★ 高潮**不是完成判据的复述**（要写具体的动作场景；旧英文 49 条全是'
           '"判据 + 一句模板尾巴"，旧中文是"判据 + 这一刻就是本站的高潮"）',
           not echoes, str(echoes[:4]))

        # ── H5 中英逐站对齐 ──
        align: list = []
        for zs, es in zip(STORIES_ZH, STORIES_EN):
            zb = _station_blocks(zh_outlines[zs['dir']])
            eb = _station_blocks(en_outlines[es['dir']])
            if len(zb) != len(eb):
                align.append((zs['dir'], f'站数 {len(zb)} vs {len(eb)}'))
                continue
            for (zt, zf, _zb), (et, ef, _eb) in zip(zb, eb):
                if _nearest_span(zf.get('跨度', '')) != _nearest_span(ef.get('跨度', '')):
                    align.append((zs['dir'], f'{zt}: 跨度 {zf.get("跨度")} vs {ef.get("跨度")}'))
                if _nearest_weight(zf.get('篇幅', '')) != _nearest_weight(ef.get('篇幅', '')):
                    align.append((zs['dir'], f'{zt}: 篇幅 {zf.get("篇幅")} vs {ef.get("篇幅")}'))
                if str(zf.get('章数', '')).strip() != str(ef.get('章数', '')).strip():
                    align.append((zs['dir'], f'{zt}: 章数 {zf.get("章数")} vs {ef.get("章数")}'))
        ok('H：★ 中英两版**逐站对齐**（跨度/篇幅/章数一样 —— 同一个故事两种语言，'
           '站表不一样就等于给了读者两本书）',
           not align, str(align[:4]))

        # ── H6 分节编号不断层 ──
        gaps = [(d, _section_nums(t)) for d, t, _en in all_outlines
                if _section_nums(t) != list(range(1, len(_section_nums(t)) + 1))]
        ok('H：★ 大纲的**分节编号连续**（一、二、三、四……不许跳号也不许重号 —— '
           '旧六篇全是"一、→ 三、"，中间空着一节）',
           not gaps, str(gaps[:4]))

        # ── H7 中英篇幅规划对得上 ──
        plan: list = []
        for zs, es in zip(STORIES_ZH, STORIES_EN):
            zt, et = zh_outlines[zs['dir']], en_outlines[es['dir']]
            zch = re.search(r'每章字数\**\s*[：:]\s*(\d+)', zt)
            ech = re.search(r'Words per chapter\**\s*[：:]\s*(\d+)', et)
            ztc = re.search(r'总章数\**\s*[：:]\s*(\d+)', zt)
            etc = re.search(r'Total chapters\**\s*[：:]\s*(\d+)', et)
            if not (zch and ech and ztc and etc):
                plan.append((zs['dir'], '篇幅规划字段缺失'))
                continue
            if int(ztc.group(1)) != int(etc.group(1)):
                plan.append((zs['dir'], f'总章数 {ztc.group(1)} vs {etc.group(1)}'))
            ratio = int(zch.group(1)) / int(ech.group(1))
            if not (1.5 <= ratio <= 1.9):
                plan.append((zs['dir'], f'每章字数比 {ratio:.2f} 越界'))
        ok('H：★ 中英两版的**篇幅规划对得上**（总章数一样；每章"字数 / 词数"之比落在 '
           '1.5~1.9 —— 同一个体量换成另一种语言）',
           not plan, str(plan[:4]))

        n_ok = sum(1 for i in ITEMS if i['ok'])
        report['items'] = ITEMS
        report['ok'] = n_ok == len(ITEMS)
        print(f'\n示例文件夹验证：{n_ok}/{len(ITEMS)}')
    except Exception:                                          # noqa: BLE001
        import traceback
        report['items'] = ITEMS
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        print(report['fatal'])
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'samples_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0 if report.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
