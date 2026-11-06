# -*- coding: utf-8 -*-
"""测试夹具：**需要"故事设定例子"时，一律从 `samples/` 取一篇，别自己编。**

规矩（用户 2026-10-07）
----------------------
「测试的时候如果需要故事设定例子，从 samples 里选择一个测试，这个后续作为规则你来遵守」

为什么这条规矩值得写下来
------------------------
自己编人名地名（"林九""临河茶肆"这种）有三个坏处，都是踩过的：

1. **编出来的设定往往太干净** —— 没有"欠痕""漏刻只许校不许改"这类能顶住推演的硬约束，
   于是测试跑得通，真机（用户那本书）不一定通。样例是**按说明书黄金档写的输入文件夹**，
   有世界观 / 顶级规则 / 人物 / 大纲 / 伏笔 / 正文六件套，跟真项目同构。
2. **测试夹具与产品共用一套专有名词会互相污染**：检验"通用性"的那条
   （`tools/verify_generic_project.py`）要扫全仓找某一部作品的专有名词，
   再随手编几个名字进去，只会让那条判据越来越难判。
3. **每次都要重新想名字**，而想出来的东西没有出处；样例里的名字有出处、可核对
   （`tools/verify_samples.py` 管着它们，改坏了会红）。

怎么用
------
```python
from sample_project import pick, prepare, cast, scene, rule, ingest

p = prepare(tmp_path, key='01')        # 01 的完整输入文件夹，**复制**到 tmp
names = cast('01')                     # 第 01 篇的人物名（从 设定/人物/*.md 的文件名读出来）
s = scene('01')                        # 第 01 篇的代表地点（值都有原文出处）
txt = rule('01')                       # 顶级规则原文（硬约束类夹具用这个）

settings = ingest(tmp_path, key='01')  # 真跑一遍 run_ingest（MOCK），返回设定集目录
```

三条纪律
--------
* **只挑一篇**（`pick()` 默认就是 `DEFAULT_KEY`）—— 别把 `samples/` 或 `samples/zh/`
  整层拿去当输入，那样六个故事会被当成一本书（`samples/README.md` 里有这条警告）。
* **用 `prepare()`，不要用 `pick()` 去改** —— 它是把样例**复制**一份到临时目录；
  直接改 `samples/` 会把随程序分发的示例弄脏，而且 `verify_samples` 会红。
* **地点名不要自己写死**：`scene()` 给的值带一条"必须真的出现在这一篇里"的判据
  （见 `tools/verify_sample_fixture.py`），样例改了它就会红 —— 跟着改这里就行。

跑法：本模块不需要单独跑；它由 `tools/verify_sample_fixture.py` 检验。

English:
Test fixture: **when a "story setting example" is needed, always take one from `samples/`; don't
write your own.**
Rule (user 2026-10-07)
----------------------
"When testing, if a story setting example is needed, pick one from samples to test; you shall
follow this as a rule going forward"
Why this rule is worth writing down
------------------------
Inventing your own names and places (like "林九" "临河茶肆") has three downsides, all of which have
been hit:
1. **Invented settings tend to be too clean** —— lacking hard constraints like "欠痕" "the clepsydra may only be calibrated, not altered" that can withstand reasoning,
   so the test passes, but the real thing (the user's book) may not. A sample is **an input folder written to the spec's golden tier**,
   with the full six-piece set of worldview / top rules / characters / outline / foreshadowing / main text, isomorphic to a real project.
2. **Sharing one set of proper nouns between test fixtures and the product causes cross-contamination**: the check for "genericity"
   (`tools/verify_generic_project.py`) scans the whole repo for proper nouns of a given work,
   then casually making up a few names to put in only makes that criterion harder and harder to judge.
3. **You have to think up new names every time**, and what you come up with has no provenance; the names in the samples have provenance and can be verified
   (`tools/verify_samples.py` manages them; breaking them turns things red).
How to use
------
```python
from sample_project import pick, prepare, cast, scene, rule, ingest
p = prepare(tmp_path, key='01')        # full input folder for 01, **copied** to tmp
names = cast('01') # character names of sample 01 (read from filenames of 设定/人物/*.md)
s = scene('01') # representative location of sample 01 (values have source in the original text)
txt = rule('01') # top-level rule text (use this for hard-constraint fixtures)
settings = ingest(tmp_path, key='01') # actually run run_ingest once (MOCK), returns the
settings directory
```
Three disciplines
--------
* **Pick only one sample** (`pick()` defaults to `DEFAULT_KEY`) -- don't pass the whole `samples/` or `samples/zh/`
  layer as input; that way the six stories get treated as one book (there's this warning in `samples/README.md`).
* **Use `prepare()`, don't use `pick()` to modify** -- it **copies** a sample into a temp directory;
  modifying `samples/` directly dirties the examples shipped with the program, and `verify_samples` will turn red.
* **Don't hardcode location names**: the value from `scene()` carries a criterion of "must actually appear in this sample"
  (see `tools/verify_sample_fixture.py`); if the sample changes it turns red -- just update here accordingly.
How to run: this module doesn't need to be run separately; it's checked by
`tools/verify_sample_fixture.py`.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SAMPLES = APP_DIR / 'samples'

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

#: 六篇样例（中文那套的目录名）。**顺序 = `samples/README.md` 的表里的顺序**。
# [EN] : Six samples (directory names of the Chinese set). **Order = the order in the table in
# [EN] `samples/README.md`**.
STORIES: tuple[str, ...] = (
    '01_悬疑单元_更漏子',
    '02_玄幻修仙_借山道人',
    '03_都市_夜班书店',
    '04_历史架空_河工疏',
    '05_言情_灯花记',
    '06_科幻_回声站',
)

#: 英文那套的目录名（与 `STORIES` **一一对应**，靠下标对齐）。
# [EN] : Directory names of the English set (**one-to-one with `STORIES`**, aligned by index).
STORIES_EN: tuple[str, ...] = (
    '01_mystery_the_water_clock',
    '02_xianxia_the_mountain_borrower',
    '03_urban_the_all_night_bookshop',
    '04_alternate_history_the_river_memorial',
    '05_romance_the_lamp_flower',
    '06_scifi_echo_station',
)

#: 默认取哪一篇。**定死 01（悬疑）**是有理由的：
#:   · 它有 `设定/顶级规则.md`（六篇里只有 01 和 03 有）→ 硬约束类夹具能用；
#:   · 两个人物、一个明确地点（司天台）、一条贯穿伏笔，最小但齐全。
#: 需要别的题材就显式传 `key='04'` 这种 —— **别改默认值**，
#: 否则所有调它的脚本会一起飘。
# [EN] : Which one is taken by default. **Hard-pinning 01 (suspense)** has reasons:
# [EN] : · It has `设定/顶级规则.md` (only 01 and 03 of the six have it) → hard-constraint fixtures can be
# [EN] used;
# [EN] : · Two characters, one clear location (司天台), one through-line foreshadowing, minimal but
# [EN] complete.
# [EN] : If another genre is needed, pass it explicitly like `key='04'` —— **do not change the
# [EN] default**,
# [EN] : otherwise every script that calls it drifts together.
DEFAULT_KEY = '01'

#: 每篇一个"说到这个题材就想到的地方"，给台词/场景类夹具用。
#: ⚠ 值**必须真的出现在那一篇的文件里** —— `tools/verify_sample_fixture.py` 的
#:   C 组会逐条去原文里找。样例改了内容、这里没跟，那条判据就红（这是故意的：
#:   宁可红一次让人来改，也不要一个悄悄失效的夹具）。
#: 每篇的**地点**（第 0 个是"说到这个题材就想到的地方"，第 1 个给
#: 换场/切镜头类夹具用 —— 那种判据需要"两个不一样的地方"）。
#: ⚠ 每个值**必须真的出现在那一篇的文件里** —— `tools/verify_sample_fixture.py` 的
#:   C 组会逐条去原文里找。样例改了内容、这里没跟，那条判据就红（这是故意的：
#:   宁可红一次让人来改，也不要一个悄悄失效的夹具）。
#:   实测价值：英文那套我第一版按中文直译（'the old street' / 'the great river' /
#:   'the relay station'），三处在英文样例里**一次都没出现**，C 组当场全红。
# [EN] : One "place you think of when you think of this genre" per story, for dialogue/scene fixtures.
# [EN] : ⚠ The value **must actually appear in that story's files** ——
# [EN] `tools/verify_sample_fixture.py`'s
# [EN] : group C checks item by item against the source text. If the sample content changes and this
# [EN] doesn't follow, that criterion goes red (this is intentional:
# [EN] :   better to go red once and have someone fix it than to have a fixture that silently fails).
# [EN] : Each story's **locations** (item 0 is "the place you think of when you think of this genre",
# [EN] item 1 is
# [EN] : for scene-change/cut fixtures —— that kind of criterion needs "two different places").
# [EN] : ⚠ Each value **must actually appear in that story's files** ——
# [EN] `tools/verify_sample_fixture.py`'s
# [EN] : group C checks item by item against the source text. If the sample content changes and this
# [EN] doesn't follow, that criterion goes red (this is intentional:
# [EN] :   better to go red once and have someone fix it than to have a fixture that silently fails).
# [EN] : Measured value: for the English set, my first version translated literally from Chinese ('the
# [EN] old street' / 'the great river' /
# [EN] : 'the relay station'), and all three **never appeared even once** in the English samples; group
# [EN] C went fully red on the spot.
PLACES: dict[str, tuple[str, ...]] = {
    '01': ('司天台', '西市'),
    '02': ('修真界', '山里'),
    '03': ('城南老街', '收银台'),
    '04': ('大河', '堤'),
    '05': ('渡口', '河上'),
    '06': ('中继站', '地球'),
}

#: 英文那套的地点。⚠ 值取自英文样例的**实际写法**（大小写按英文习惯写得体面，
#:   比对时**不区分大小写** —— 判据要的是"这个地方真的存在"，不是"逐字符一样"）。
#: ⚠ 'Bureau'（司天台）与 'levee'（堤）都是**去英文样例里翻出来的实际用词**：
#:   我先按中文直译写了 'the market' / 'the dike'，两处**一次都没出现** ——
#:   C 组的英文那半当场红。这就是"地点必须有出处"这条判据存在的理由。
# [EN] : Locations for the English set. ⚠ Values are taken from the **actual wording** in the English
# [EN] samples (capitalization styled respectably per English convention,
# [EN] : comparison is **case-insensitive** —— the criterion wants "this place really exists", not
# [EN] "character-for-character identical").
# [EN] : ⚠ 'Bureau' (司天台) and 'levee' (堤) are both **actual wordings dug out of the English samples**:
# [EN] : I first wrote 'the market' / 'the dike' translated literally from Chinese, and both **never
# [EN] appeared even once** ——
# [EN] : the English half of group C went red on the spot. This is the reason the criterion "locations
# [EN] must have a source" exists.
PLACES_EN: dict[str, tuple[str, ...]] = {
    '01': ("Chang'an", 'Bureau'),
    '02': ('the cultivation world', 'the mountain'),
    '03': ('Old Street', 'the counter'),
    '04': ('Great River', 'levee'),
    '05': ('the landing', 'the river'),
    '06': ('the station', 'Earth'),
}


#: 「第三人」用的**行当名**（每篇只有两个具名人物，而三人场景的判据需要第三个）。
#: ⚠ 同样必须有出处：每个值都要**真的出现在那一篇里**（C 组判据核）。
#: 按需增补 —— 用不到某篇就先空着，别为了凑齐六篇去编名字。
# [EN] : The **trade names** used by "the third person" (each story has only two named characters,
# [EN] while the three-person scene criterion needs a third).
# [EN] : ⚠ Likewise must have a source: each value must **really appear in that story** (group C
# [EN] criterion check).
# [EN] : Add as needed —— if some story isn't used, just leave it empty; don't invent names to fill all
# [EN] six.
ROLES: dict[str, tuple[str, ...]] = {
    '01': ('更夫', '仵作'),        # 世界观「日子过得比更夫还安静」· 大纲「仵作都写了意外」
    # [EN] Worldview "days pass quieter than a night watchman" · outline "the coroner wrote it as an
    # [EN] accident"
}


def norm(s) -> str:
    """比对用归一化：去掉 markdown 强调标记与**尾部**标点。

    为什么要有它：样例里那些"规矩"大多是**加粗**写的
    （`**借了必须还，还不上就记账**。`），加粗标记夹在句子与句号之间 ——
    不归一化的话，"这句确实在原文里"会被判成 ✗（假红）。
    判据与夹具用**同一把尺子**，才不会一边说在有、一边说没有。
    
        English:
    Comparison normalization: strip markdown emphasis markers and **trailing** punctuation.
        Why it's needed: those "rules" in the samples are mostly written in **bold**
        without normalization, "this sentence is indeed in the original" would be judged ✗ (false red).
        Criteria and fixtures use **the same ruler**, so one side doesn't say present while the other says absent.
    """
    import re as _re
    return _re.sub(r'[*`]', '', str(s or '')).strip().strip('。，、；：')


def _mid(x) -> str:
    """`'01'` / `1` / `'01_悬疑单元_更漏子'` / `'01_mystery_...'` 都归一成 `'01'`。

    设计成"认不出就报错"：静默地退回默认值，会让一个写错 key 的测试
    悄悄测了另一篇（然后判据的红绿就说不清了）。

    ⚠ `None` 要**单独判**：`str(None)` 是 `'None'`（不是空串），
      写成 `if not str(x).strip()` 会让"不传 key"直接报错
      —— 冒烟测试当场抓到的就是这个。
    
        English:
        Designed to "error out if unrecognized": silently falling back to a default would make a test with a mistyped key
        quietly test another sample (and then the criterion's red/green becomes unclear).
        ⚠ `None` must be checked **separately**: `str(None)` is `'None'` (not an empty string),
          so writing `if not str(x).strip()` makes "no key passed" error out directly
          -- this is exactly what the smoke test caught on the spot.
    """
    if x is None:
        return DEFAULT_KEY
    if isinstance(x, int) and not isinstance(x, bool):
        s = f'{x:02d}'
    else:
        s = str(x).strip()
    if not s:
        return DEFAULT_KEY
    if len(s) >= 2 and s[:2].isdigit() and s[:2] in PLACES:
        return s[:2]
    if s.isdigit() and f'{int(s):02d}' in PLACES:
        return f'{int(s):02d}'
    raise KeyError(f'认不出是哪一篇样例：{x!r}（可选：{sorted(PLACES)}）')


def pick(key=None, *, lang: str = 'zh') -> Path:
    """返回某一篇样例在 `samples/` 里的**原目录**（只读用）。

    ⚠ 要跑要改的场合用 `prepare()` —— 这个返回的是随程序分发的那一份。
    
        English:
    Return a sample's **original directory** in `samples/` (for read-only use).
        ⚠ For cases where you need to run and modify, use `prepare()` -- this returns the one shipped with the program.
    """
    k = _mid(key)
    table = STORIES if lang == 'zh' else STORIES_EN
    sub = 'zh' if lang == 'zh' else 'en'
    p = SAMPLES / sub / table[int(k) - 1]
    if not p.is_dir():
        raise FileNotFoundError(f'样例目录不存在：{p}')
    return p


def prepare(tmp, key=None, *, lang: str = 'zh', name: str = '') -> Path:
    """把某一篇样例**复制**到 `tmp` 下并返回副本路径（要改就改这一份）。

    临时目录里出来的副本 `ingest` 能吃（它就是一份标准输入文件夹）。
    
        English:
    **Copy** a sample into `tmp` and return the copy's path (modify this copy if you need to).
        The copy produced in the temp directory is consumable by `ingest` (it's a standard input folder).
    """
    src = pick(key, lang=lang)
    dst = Path(tmp) / (name or src.name)
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return dst


def cast(key=None, *, lang: str = 'zh') -> list[str]:
    """这一篇的人物名（从 `设定/人物/*.md` 的**文件名**读 —— 不写死在代码里）。

    文件名就是人名（`主角.md` → "主角"），所以样例加了人会自动跟上。
    
        English:
    Character names of this sample (read from the **filenames** of `设定/人物/*.md` -- not hardcoded in
    the code).
        The filename is the character name (`主角.md` → "主角"), so adding a character to the sample updates automatically.
    """
    k = _mid(key)
    root = pick(k, lang=lang)
    sub = '设定/人物' if lang == 'zh' else 'setting/characters'
    d = root / sub
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob('*.md'))


def places(key=None, *, lang: str = 'zh') -> tuple[str, ...]:
    """这一篇的地点（≥2 个；`places(k)[0]` 就是 `scene(k)`）。

    为什么要两个：换场 / "隔门听不见"这类判据需要**两个不一样的地点**才测得出。
    
        English:
    Locations of this sample (≥2; `places(k)[0]` is `scene(k)`).
        Why two: criteria like scene changes / "can't hear through the door" need **two different locations** to be tested.
    """
    k = _mid(key)
    return (PLACES if lang == 'zh' else PLACES_EN)[k]


def scene(key=None, *, lang: str = 'zh') -> str:
    """这一篇的"代表地点"（= `places()` 的第一个；值取自原文，有判据钉住）。
        English:
    The "representative location" of this sample (= the first of `places()`; value comes from the
    original text, pinned by a criterion).
    """
    return places(key, lang=lang)[0]


def roles(key=None) -> tuple[str, ...]:
    """这一篇里**没被列进人物文件、但确实在故事里**的行当名（缺就返回空元组）。

    用途：三人场景的判据（`cast()` 只给两个具名人物）需要一个"在场但不重要"的
    第三人 —— 从这一篇的世界里取一个行当（"更夫"），比自己编一个名字可靠：
    编出来的名字不属于这本书，测的就不是这本书了。
    
        English:
    Profession names in this sample that are **not listed in character files but do appear in the
    story** (returns empty tuple if missing).
        Purpose: criteria for three-person scenes (`cast()` only gives two named characters) need an "present but unimportant"
        third person -- taking a profession from this sample's world ("更夫") is more reliable than inventing a name:
        a made-up name doesn't belong to this book, so what's being tested isn't this book anymore.
    """
    return ROLES.get(_mid(key), ())


def line(key=None, nth: int = 0) -> str:
    """这一篇里可以当**台词**用的短句（取自原文，见 `LINES`）。
        English:
    Short sentences in this sample that can be used as **dialogue** (taken from the original text,
    see `LINES`).
    """
    k = _mid(key)
    pool = LINES.get(k, ())
    return pool[nth % len(pool)] if pool else ''


#: 可以当台词用的短句 —— **都摘自这一篇自己的文字**（世界观 / 顶级规则 / 大纲）。
#: 为什么不自己编台词：夹具里那句"重复的话"如果是我编的，它跟这本书的腔调、
#: 题材都没关系；从原文里取，测的才是"这本书里人物说的话会不会被重复"。
#: （六篇的正文都是**不带引号**的写法，所以短句从设定与大纲里取。）
# [EN] : Short lines usable as dialogue —— **all excerpted from this story's own text** (worldview /
# [EN] top rules / outline).
# [EN] : Why not write the dialogue myself: if that "repeated line" in the fixture were written by me,
# [EN] it would have nothing to do with this book's tone
# [EN] : or genre; taken from the source text, what's tested is "whether the characters' speech in this
# [EN] book gets repeated".
# [EN] : (The main text of all six stories uses the **no-quotation-marks** style, so short lines are
# [EN] taken from the setting and outline.)
LINES: dict[str, tuple[str, ...]] = {
    # 01 悬疑《更漏子》
    '01': ('水不会说谎，人会。',      # 世界观 · 也是伏笔二里"每卷必出现"的那句
           '漏刻只许校，不许改。',    # 世界观/顶级规则 · 世界铁律
           '先看水。',                # 世界观「先看水，再看人」—— 3 个字，**真台词**
           '不许改。',                # 世界观「漏刻只许校，不许改」—— 也是 3 个字
           '更鼓早了整整一刻。'),      # 大纲 · 开局那句
    # 02 玄幻修仙《借山道人》
    '02': ('借了必须还，还不上就记账。',   # 世界观 · 这一行的总规矩
           '出不去，也说不出自己从哪儿来。',  # 世界观 · 说明"借山"的后果
           '山完好，字据履行。'),            # 世界观 · 什么算还清
    # 03 都市《夜班书店》
    '03': ('不劝人买书。',                    # 世界观 · 店里三条规矩之一
           '凌晨三点到四点，不要问客人上什么班。',  # 同一组
           '收银台里那一本不卖。'),            # 同一组
    # 04 历史架空《河工疏》
    '04': ('用印之后不能改。',                # 世界观 · 全书的死线
           '人人都知道算错过，人人都不能改。',  # 世界观 · 这套规矩长出的怪东西
           '私改河工疏者斩。'),              # 世界观的律例原话
    # 05 言情《灯花记》
    '05': ('在船上说的话，第二天谁也不许提。',  # 世界观 · 这一夜唯一的规矩
           '这一夜不唱曲、不说亲事、不递东西。',  # 同一段
           '灯节最后一趟船，不载生客。'),      # 世界观 · 说法的来处
    # 06 科幻《回声站》
    '06': ('站钟比地球快三秒',                # 世界观 · 设计，不是故障
           '十一年刚好是一个人不疯掉的极限',  # 世界观 · 轮换周期的来处
           '把地球来的信号放大、转出去'),      # 世界观 · 这站每天干的活
    # [EN] 01 Suspense — The Water Clock
    # [EN] Worldview · also the line that "must appear in every volume" in foreshadowing two
    # [EN] Worldview/top rules · the world's iron law
    # [EN] Worldview "look at the water first, then the people" —— 3 characters, **real dialogue**
    # [EN] Worldview "the clepsydra may only be calibrated, not altered" —— also 3 characters
    # [EN] Outline · the opening line
    # [EN] Worldview · the overarching rule of this line
    # [EN] Worldview · explains the consequences of "borrowing a mountain"
    # [EN] Worldview · what counts as repaid
    # [EN] Worldview · one of the shop's three rules
    # [EN] Same group
    # [EN] Same group
    # [EN] 04 Historical alternate-world《河工疏》
    # [EN] Worldview · the whole book's deadline
    # [EN] Worldview · the strange thing grown out of this set of rules
    # [EN] The original wording of the worldview's statutes
    # [EN] 05 Romance《灯花记》
    # [EN] Worldview · the only rule of this night
    # [EN] Same paragraph
    # [EN] Worldview · the origin of the saying
    # [EN] 06 Sci-fi《回声站》
    # [EN] Worldview · by design, not a malfunction
    # [EN] Worldview · the origin of the rotation cycle
    # [EN] Worldview · the work this station does every day
}


def rule(key=None, *, lang: str = 'zh') -> str:
    """这一篇的「顶级规则」原文（没有规则文件就返回空串）。

    硬约束类夹具（"这条规矩不许破"）应当用它的原话，而不是自己编一条 ——
    编出来的规矩跟样例的世界观没有关系，测的就不是这本书了。
    
        English:
    The original text of the "top-level rules" for this piece (return an empty string if there is no
    rules file).
        Hard-constraint fixtures ("this rule must not be broken") should use its exact wording, not invent one yourself —
        an invented rule has nothing to do with the sample's worldview, so what gets tested is no longer this book.
    """
    k = _mid(key)
    p = pick(k, lang=lang) / ('设定' if lang == 'zh' else 'setting') / \
        ('顶级规则.md' if lang == 'zh' else 'rules.md')
    return p.read_text(encoding='utf-8') if p.is_file() else ''


def outline(key=None) -> str:
    """这一篇的故事大纲原文（`cover` 类夹具用）。
        English:
    The original text of this piece's story outline (used by `cover`-type fixtures).
    """
    p = pick(key) / '大纲' / '故事大纲.md'
    return p.read_text(encoding='utf-8') if p.is_file() else ''


def ingest(tmp, key=None, *, name: str = '_设定集'):
    """真跑一遍 `run_ingest`（MOCK，零网络），返回设定集目录。

    ⚠ 调用方**自己**保证 `CFG.set('MOCK_LLM', 'true')`：夹具不替测试改全局配置
      （改了别人跟着受影响，而且 MOCK 是"要不要联网"的大事，应该由测试写明）。
    
        English:
    Actually run `run_ingest` once (MOCK, zero network), and return the settings directory.
        ⚠ The caller **itself** guarantees `CFG.set('MOCK_LLM', 'true')`: fixtures do not change global config on behalf of tests
          (changing it affects others too, and MOCK is a big deal about "whether to use the network", so the test should state it explicitly).
    """
    import ingest.pipeline as PL
    src = prepare(tmp, key)
    out = Path(tmp) / name
    asyncio.run(PL.run_ingest(src, settings_dir=out))
    return out
