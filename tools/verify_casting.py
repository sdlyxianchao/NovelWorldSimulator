# -*- coding: utf-8 -*-
"""判据：**选角与项目档**（演员类型库 · 两层提示词 · 剧组按书调整）。

覆盖四样东西，每样都要能红：

  A **类型库本身**：每型有没有骨架/说话/身体/变奏/忌讳；变奏够不够（反刻板）；
    默认型存不存在；匹配表的词有没有型接得住（**死词**）。
  B **匹配与分流**：年龄优先于气质；兜底要说实话；同型多人分不同的变奏。
  C **两层提示词**：预设＋定制＋仲裁规则；定制没料时不编。
  D **真的进到演员提示词里**（行为级：抓真发出去的 messages）。
  E **项目档**：按书生成、顺序对（压在默认手艺之后）、缺席不报错、如实落盘。
  F **拆书来的那几条手艺**：进库了、演员读得到。

用法：
    python tools/verify_casting.py              # 逻辑 + 真机
    python tools/verify_casting.py --logic-only # 只跑逻辑（不起窗口）

English:
Criteria: **casting and project file** (actor type library · two-layer prompt · cast adjusted
per book).
Covers four things, each must be able to go red:
  A **The type library itself**: does each type have skeleton/speech/body/variation/taboo; are variations sufficient (anti-stereotype);
    does the default type exist; can the words in the match table be caught by a type (**dead words**).
  B **Matching and routing**: age takes priority over temperament; the fallback must tell the truth; multiple people of the same type get different variations.
  C **Two-layer prompt**: preset + customization + arbitration rules; do not fabricate when customization has no material.
  D **Actually enters the actor prompt** (behavior level: capture the messages actually sent out).
  E **Project file**: generated per book, correct order (pressed after the default craft), no error when absent, written to disk faithfully.
  F **Those few crafts from book deconstruction**: went into the library, readable by the actor.
Usage:
    python tools/verify_casting.py              # logic + real machine
    python tools/verify_casting.py --logic-only # logic only (no window started)
"""
from __future__ import annotations

import asyncio
import json
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
    print(('  ✓ ' if good else '  ✗ ') + name + (f'   [{detail}]' if detail and not good else ''))
    return bool(good)


def _safe_rmtree(p, **kw) -> None:
    import shutil
    try:
        shutil.rmtree(p, **kw)
    except Exception:                                            # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════
#  A 类型库
# [EN] A Type library
# ══════════════════════════════════════════════════════════════
def test_library(tmp: Path) -> None:
    from actors import casting as C
    lib = C.load(force=True)
    types = lib['types']
    ok('A1 类型库读得进来（≥12 型）', len(types) >= 12, f'{len(types)} 型')

    miss_骨架 = [k for k in types if not C.entry(k).get('骨架')]
    ok('A2 ★ 每一型都有「骨架」（这一类人是什么样）', not miss_骨架, str(miss_骨架[:4]))

    miss_说 = [k for k in types
              if not isinstance(C.entry(k).get('说话'), dict)
              or not C.entry(k)['说话'].get('句长')]
    ok('A3 ★ 每一型都写了「说话」（句长/语速是"怎么演"的抓手）',
       not miss_说, str(miss_说[:4]))

    miss_身 = [k for k in types if not C.entry(k).get('身体')]
    ok('A4 每一型都写了「身体」（本项目每拍都要出一个动作）',
       not miss_身, str(miss_身[:4]))

    # ★★ 反刻板：一个类型只有一种演法就是套路
    # [EN] ★★ Anti-stereotype: a type with only one way to play it is a cliché
    few = [(k, len(C.variants(k))) for k in types if len(C.variants(k)) < 3]
    ok('A5 ★★ 每一型的变奏轴 ≥3 条（**反刻板的结构保证**：'
       '一个类型只有一种演法＝套路）', not few, str(few[:4]))

    dup = [k for k in types if len(set(C.variants(k))) != len(C.variants(k))]
    ok('A6 同一型里的变奏互不重复（重复了等于没分流）', not dup, str(dup[:4]))

    miss_忌 = [k for k in types if not C.entry(k).get('忌讳')]
    ok('A7 ★ 每一型都写了「忌讳」（别写成什么）', not miss_忌, str(miss_忌[:4]))

    # ★★ 默认型必须真的存在（否则兜底会落到"sorted 之后第一个"，等于没兜底）
    # [EN] ★★ The default type must actually exist (otherwise the fallback lands on "the first after
    # [EN] sorted", which is no fallback at all)
    ok('A8 ★★ `_DEFAULT` 指向的类型**真的存在**'
       '（否则"兜底"其实落到字母序第一个 —— 那不是兜底）',
       lib['default'] in types, f"{lib['default']} / 存在={lib['default'] in types}")

    # ★★ 死词：匹配表里写了词、却没有一型接得住 = 作者写"书生"和写"疯癫"效果一样
    # [EN] ★★ Dead words: a word written in the match table that no type can catch = the author writing
    # [EN] "scholar" has the same effect as writing "madman"
    moods_lib = {k.split('·', 1)[1] for k in types if '·' in k}
    dead = sorted(set(lib['match']) - moods_lib)
    ok('A9 ★★ 匹配表里的每个气质都有类型接得住（**没有死词** —— '
       '表里写着有这个选项、库里没有实现，是本项目最忌的那种"假按钮"）',
       not dead, f'死词：{dead}')

    # 年龄表：每层都要有型
    # [EN] Age table: every layer must have a type
    ages_lib = {k.split('·', 1)[0] for k in types if '·' in k}
    ages_map = set(lib.get('age') or {})
    ok('A10 年龄表里每一层都有对应的型（否则那些年龄词永远配不上）',
       ages_map <= ages_lib, f'缺：{sorted(ages_map - ages_lib)}')

    bad_key = [k for k in types if '·' not in k]
    ok('A11 类型键统一写成「年龄层·气质」（两步匹配靠它拼）',
       not bad_key, str(bad_key[:4]))


# ══════════════════════════════════════════════════════════════
#  B 匹配与分流
# [EN] B Matching and routing
# ══════════════════════════════════════════════════════════════
def test_match(tmp: Path) -> None:
    from actors import casting as C

    k, hit = C.find('沉默寡言，记性极好')
    ok('B1 气质词命中（"寡言" → 高冷）', '高冷' in k and hit, f'{k} / {hit}')

    # ★★ 年龄优先：小孩的语速不能被"毒舌"带成成年人的
    # [EN] ★★ Age takes priority: a child's speech rate must not be dragged into an adult's by "sarcastic"
    k2, _ = C.find('七岁，嘴损，爱怼人')
    ok('B2 ★★ 年龄优先于气质 —— "七岁的毒舌"落在**孩**那一层'
       '（年龄层管嗓子与节奏，比"哪一类人"更难改）',
       k2.startswith('孩·'), k2)

    k3, hit3 = C.find('族里的老人，不苟言笑')
    ok('B3 "老人+威严"落在老年层', k3.startswith('老年·'), k3)

    k4, hit4 = C.find('巷口卖菜的')
    ok('B4a ★ 气质与年龄**都没配上**时落默认型，且命中为空'
       '（不假装配上了）',
       k4 == C.load()['default'] and hit4 == '', f'{k4} / {hit4!r}')

    # ★★ 只有年龄配上：要说清"凭什么配的"（命中词不能吞掉）
    #   ⚠ 这一条是补出来的：变异"把命中词吞掉"**上一版判据抓不住** ——
    #     因为原来只测了"完全没配上"那一路，而这条路走的是另一段代码。
    # [EN] ★★ Only matched by age: must state clearly "why it matched" (the hit word must not be swallowed)
    # [EN] ⚠ This one is a patch: the mutation "swallow the hit word" **could not be caught by the previous
    # [EN] version's criteria** ——
    # [EN] because originally only the "not matched at all" path was tested, and that path goes through a
    # [EN] different piece of code.
    k5, hit5 = C.find('四十来岁的汉子，管着铺子')
    ok('B4b ★★ 只配到年龄层时，要说得出**凭什么**（命中词不能吞掉）'
       '—— 落盘表上那一列就是给作者看的',
       bool(k5) and bool(hit5), f'{k5} / {hit5!r}')

    # 作者点名优先
    # [EN] Author roll-call takes priority
    c = C.instantiate('甲', {'演员类型': '老年·疯癫', '性格': '沉默寡言'})
    ok('B5 人物卡里点名 `演员类型:` 时以它为准（作者的话压过机器配的）',
       c.archetype == '老年·疯癫' and c.matched, f'{c.archetype}/{c.matched}')

    # ★★ 同型多人分流
    # [EN] ★★ Routing for multiple people of the same type
    taken: dict[str, int] = {}
    rows = [C.instantiate(f'人{i}', {'演员类型': '青年·高冷'}, taken=taken)
            for i in range(3)]
    vs = [r.variant for r in rows]
    ok('B6 ★★ 同型多人**分到不同的变奏**（不是复制粘贴 —— '
       '照字面复制会让两个人写出来一模一样）',
       len(set(vs)) == 3, str(vs))

    many = [C.instantiate(f'多{i}', {'演员类型': '青年·高冷'}) for i in range(9)]
    ok('B7 变奏取完一轮**从头再来**（不抛异常、也不空着）',
       all(r.variant for r in many), str([r.variant[:6] for r in many[:4]]))

    rows2 = C.cast_all({'甲': {'性格': '沉默寡言'}, '乙': {'性格': '沉默，不爱理人'}})
    ok('B8 整份人物表能一次选完（dict 与 list 两种入参都认）',
       len(rows2) == 2, str([r.name for r in rows2]))

    # ══════════════════════════════════════════════════════════
    #  B9~B11 ★★★ 2026-10-25（用户报的：导出里「阿九该是少年、沈砚该是老年」）
    #
    #  根因是**中文没有词边界**：`w in blob` 让短词命中长词的一部分。
    #  这里三条各钉一道闸，而且每条都能**单独**把对应的闸弄红：
    #    B9  子串：`六十来岁` **含** `十来岁` ⇒ 六十岁会被配成少年；
    #    B10 否定：`不老实` 含 `老实` ⇒ 意思正好反过来；
    #    B11 显式年龄字段优先（作者写了就按它定，不再猜）。
    #  ⚠ 这三条不是"再测一遍正常路径"，是**反例**：去掉边界检查/否定检查/
    #    年龄优先，它们必须变红（`developers/mutate_casting.py` 里各有一条）。
    # [EN] ★★★ 2026-10-25 (user-reported: "阿九 should be a youth, 沈砚 should be elderly").
    # [EN] Root cause: Chinese has no word boundaries, so `w in blob` lets a short word match part
    # [EN] of a longer one. Each case below pins one gate and can turn **its own** gate red.
    # [EN] ⚠ These are counterexamples, not "test the happy path again".
    k6, _ = C.find('六十来岁灰布长衫，话少')
    ok('B9 ★★★ 年龄词不越界：`六十来岁` 里的 `十来岁` **不算**少年'
       '（中文没词边界，`w in blob` 会让六十岁的掌柜配成少年 —— 用户实跑撞到的就是这条）',
       k6.startswith('老年·'), f'{k6}')

    k7, h7 = C.find('他不老实，爱耍滑')
    ok('B10 ★★★ 否定不取反义：`不老实` **不算**憨厚'
       '（否则"这人一点也不老实"会被配成憨厚 —— 意思正好相反）',
       '憨厚' not in k7 and h7 != '老实', f'{k7} / {h7!r}')

    c_age = C.instantiate('甲', {'性格': '老实', '年龄': '十六'})
    c_old = C.instantiate('乙', {'性格': '老实', '年龄': '五十二'})
    ok('B11 ★★ 人物卡写了 `年龄:` 就**按它定**年龄层（不再从性格倒推）'
       '—— 同一句「老实」，十六岁该是少年、五十二岁该是中年',
       c_age.archetype.startswith('少年·') and c_old.archetype.startswith('中年·')
       and not c_age.age_guessed,
       f'{c_age.archetype} / {c_old.archetype}')


# ══════════════════════════════════════════════════════════════
#  C 两层提示词
# [EN] C Two-layer prompt
# ══════════════════════════════════════════════════════════════
def test_layers(tmp: Path) -> None:
    from actors import casting as C

    c = C.instantiate('主角', {'性格': '沉默寡言'})
    card = {'身份': '帐房', '性格': '沉默寡言', '秘密': '他认得那笔账'}
    blk = C.prompt_block(c, card)

    ok('C1 ★ 预设层在（这类演员怎么演）', '〔你这一类演员' in blk, '')
    ok('C2 ★ 定制层在（在这个本子里演谁）', '〔在这个本子里，你演的是〕' in blk, '')
    ok('C3 ★★ 仲裁规则在（两层冲突时怎么办 —— **不写这条，模型会自己挑一套**，'
       '表现就是"这个人忽冷忽热"）', '以角色为准' in blk, '')
    ok('C4 ★★ 仲裁规则明写了**预设只管"怎么演"、不管"演谁"**'
       '（这是"定制优先"能落地的关键切分，不是笼统的"定制优先"）',
       '只管你**怎么演**' in blk and '演谁' in blk, '')
    ok('C5 预设层在定制层**之前**（后写的离输出更近，压得住）',
       blk.find('〔你这一类演员') < blk.find('〔在这个本子里'), '')
    ok('C6 仲裁规则排在**两层之后**（读完两层立刻读到裁决规则）',
       blk.find('以角色为准') > blk.find('〔在这个本子里'), '')

    # 定制没料 → 不许编
    # ★★ 分两条测两段不同的代码路径（上一版只测了"只有身份"那一路，
    #   于是"空卡时编一行"这个变异**抓不住** —— 它走的是另一段）：
    # [EN] Customization has no material → must not fabricate
    # [EN] ★★ Split into two tests covering two different code paths (the previous version only tested the
    # [EN] "identity only" path,
    # [EN] so the mutation "fabricate a line when the card is empty" **could not be caught** —— it goes
    # [EN] through a different piece of code):
    blk_empty = C.prompt_block(c, {})
    ok('C7a ★★ 定制层**完全没料**时不编（空卡 → 不出"性格：…"这类凭空的行）',
       '性格：' not in blk_empty and '秘密：' not in blk_empty, blk_empty[:50])
    blk2 = C.prompt_block(c, {'身份': '帐房'})
    ok('C7b ★ 定制层只有身份时，只出身份那一行（不顺手补性格/秘密）',
       '秘密：' not in blk2 and '身份：帐房' in blk2, '')

    # 认不出类型 → 退化成只给定制，且**不报错**
    # [EN] Type unrecognized → degrades to customization only, and **does not error**
    bad = C.prompt_block(C.Casting(name='甲', archetype='不存在的型'),
                         {'身份': '路人'})
    ok('C8 ★ 类型认不出时退化成只给定制层（**不许因此什么都不给**）',
       '身份：路人' in bad and '你这一类演员' not in bad, bad[:40])

    # 打破类型
    # [EN] Breaking the type
    c2 = C.instantiate('乙', {'演员类型': '青年·高冷', '打破类型': '他其实话很多'})
    blk3 = C.prompt_block(c2, {'身份': '说书的'})
    ok('C9 ★ 定制层写了「打破类型」时才出现那一条（是唯一的例外口子）',
       '打破类型：他其实话很多' in blk3, '')

    # 预设必须短（演员上下文还要留给记忆与在场名单）
    # [EN] The preset must be short (the actor context still needs to be left for memory and the present
    # [EN] roster)
    pre = C.render_preset(c, chars=150)
    ok('C10 预设层有字数上限（提示词里它只占一小段）',
       len(pre) <= 220, f'{len(pre)} 字')


# ══════════════════════════════════════════════════════════════
#  D/E 装配与项目档（行为级）
# [EN] D/E Assembly and project file (behavior level)
# ══════════════════════════════════════════════════════════════
def _assemble(tmp: Path, *, with_card: bool = True):
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    proj = make_project(tmp / '夹具', nodes=3)
    run = RunFolder(proj.root, '第1次模拟2026-10-07-16-30').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
    if with_card:
        from craft import craftmix
        world.genre_card = dict(craftmix.card('悬疑灵异') or {})
        from crew import profile as PROF
        PROF.attach(world)
        run.root.joinpath('本剧组守则.md').write_text(
            PROF.table_md(world.crew_profile), encoding='utf-8')
    else:
        world.genre_card = {}
        from crew import profile as PROF
        PROF.attach(world)
    return proj, run, loop, world, db


def test_wiring(tmp: Path) -> list:
    from crew import agents as A
    from crew import profile as PROF
    from craft import craftmix
    from actors import casting as C

    proj, run, loop, world, db = _assemble(tmp / 'a')
    rows = list(world.people.items())

    ok('D1 ★★ 装配后**每个人都有了演员类型**（写进了 PersonState，'
       '不是只活在选角函数里）',
       bool(rows) and all(getattr(ps, 'archetype', '') for _n, ps in rows),
       str([(n, getattr(ps, 'archetype', '')) for n, ps in rows][:3]))
    ok('D2 ★ 同型多人分流后**变奏不同**（真的落到了 ps 上）',
       len({getattr(ps, 'variant', '') for _n, ps in rows}) == len(rows)
       or len(rows) < 2,
       str([getattr(ps, 'variant', '')[:8] for _n, ps in rows]))

    # 落盘两份档
    # [EN] Two files written to disk
    ok('E1 ★★ 运行文件夹里有《选角表.md》', (run.root / '选角表.md').is_file(), '')
    ok('E2 ★★ 运行文件夹里有《本剧组守则.md》'
       '（这本书要剧组多注意什么 —— 能改的前提是看得见）',
       (run.root / '本剧组守则.md').is_file(), '')
    t = (run.root / '选角表.md').read_text(encoding='utf-8') \
        if (run.root / '选角表.md').is_file() else ''
    ok('E3 ★ 选角表逐位写清"怎么配的"（含**未命中就写未命中**）',
       '怎么配的' in t and ('人物卡命中' in t or '未命中' in t), t[:60])
    prof_md = (run.root / '本剧组守则.md').read_text(encoding='utf-8') \
        if (run.root / '本剧组守则.md').is_file() else ''
    ok('E4 ★★ 本剧组守则里有**这本书的具体内容**（钩子库/毒点红线这些，'
       '不是一张空表）',
       '钩子库' in prof_md and '毒点红线' in prof_md, prof_md[:80])

    # ★★ 项目档要真的进职位提示词，而且**排在默认手艺之后**
    # [EN] ★★ The project file must actually enter the role prompt, and **be ordered after the default
    # [EN] craft**
    A.bind_world(world)
    blk = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    ok('E5 ★★ 项目档进了职位的"手艺"那一段（一处设置、十二个职位同时生效）',
       '这本书的特别要求' in blk, blk[:60])
    ok('E6 ★★ 项目档排在**默认手艺之后**（顺序就是优先级：'
       '常识让位于具体，与演员那两层同一条道理）',
       blk.find('这本书的特别要求') > 0
       and blk.find('这本书的特别要求') > blk.find('〔', 0, max(1, len(blk)))
       if '〔' in blk else True, '')
    ok('E7 ★ 项目档自带一句"冲突时以它为准"（制度上写明它有优先权）',
       '以这一段为准' in blk, '')

    # 演员那一侧：手艺（人物与对话）也要读得到
    # [EN] On the actor side: the craft (character and dialogue) must also be readable
    act = A.craft_block('actor', '悬疑灵异', '单元剧')
    # ★★★ 2026-10-18 晚：**口径跟着"动态映射"改**。
    #   原来判「`说话方式就是身份` 这一条必须在里面」—— 在调度器按
    #   （时机 × 品级 × 拍数）挑条目之后，**任何单独一条都可能这一拍不被选中**，
    #   于是这条判据变成了"要求某个条目永不被轮空"，与设计直接冲突。
    #   ⚠ 但它守的那件事仍然要守：**演员读到的必须是"怎么说"那一类，而且不止一条**。
    #   ⇒ 改成按**货架**判（货架是条目的稳定属性，不是这一拍的抽签结果）：
    #     每一条都来自「人物与对话」或「叙事学正典」，且至少两条。
    #   ⚠ 这不是放水：下面 D4 成对守"不许混进故事类"，两条一起才成立。
    # [EN] ★★★ 2026-10-18 evening: **the rule follows dynamic dispatch**. It used to require one
    # [EN] specific entry ("manner of speech is identity") to be present -- once the dispatcher picks
    # [EN] by (moment x grade x tick), **any single entry may be skipped this beat**, so that check
    # [EN] demanded "one entry is never rotated out", which contradicts the design.
    # [EN] ⚠ What it guards still holds: the actor must read **the "how to speak" kind, and more than
    # [EN] one**. => judge by **shelf** (a stable property, not a per-beat lottery): every entry comes
    # [EN] from 人物与对话 or 叙事学正典, and there are at least two. Not a loosening: D4 below pairs it
    # [EN] by forbidding story craft.
    from craft import craftmix as _CM
    _act_names = [ln[1:ln.index('〕')] for ln in act.splitlines() if ln.startswith('〔')]
    _act_shelves = {str((_CM.load()['entries'].get(n) or {}).get('_货架') or '')
                    for n in _act_names}
    ok('D3 ★★ **演员读得到"话该怎么说"的手艺**'
       '（判的是"给的都是这一类、且不止一条"，不是"某一条必须出现"）',
       len(_act_names) >= 2
       and _act_shelves <= {'人物与对话', '叙事学正典'},
       f'{len(_act_names)} 条 / 货架 {sorted(_act_shelves)}')
    ok('D4 ★ 演员拿到的条目全是"怎么说"那一类，**不含"故事怎么讲"**'
       '（多给了它就会想替编剧干活）',
       not (_act_shelves & {'中国古典章法', '西方编剧正典', '剧作与舞台',
                            '网络文学方法论'})
       and '这本书的特别要求' in act, sorted(_act_shelves))

    # 没有类型卡时：项目档为空，**不许报错**
    # [EN] When there is no type card: the project file is empty, **must not error**
    proj2, run2, loop2, world2, db2 = _assemble(tmp / 'b', with_card=False)
    A.bind_world(world2)
    blk2 = A.craft_block('screenwriter', '悬疑异', '')
    ok('E8 ★★ 没有类型卡时**不报错**，只是没有那一段'
       '（拿不到不是故障 —— 剧组按默认手艺干活）',
       '这本书的特别要求' not in blk2, blk2[:50])
    ok('E9 没有类型卡时守则也照写（明说"没有可用的卡"，不留空白）',
       '没有可用的类型卡' in (run2.root / '本剧组守则.md').read_text(
           encoding='utf-8') if (run2.root / '本剧组守则.md').is_file() else False, '')

    return [proj, run, loop, world, db]


def test_in_prompt(tmp: Path, bundle: list) -> None:
    """★ 行为级：抓**真发出去的 messages**，看两层是不是真到了演员面前。
        English:
    ★ Behavior level: capture the **messages actually sent out**, see whether the two layers really
    reach the actor.
    """
    from agent.core import Agent

    _proj, _run, loop, world, db = bundle
    name = next(iter(world.people))
    ps = world.people[name]
    ps.archetype = '青年·高冷'
    ps.variant = '冷在防（怕被看穿，对熟人话就多）'
    ps.casting_note = '对账房先生才多说两句'

    seen: list = []
    import llm.router as R
    _orig = R.llm.chat

    async def fake(tier, messages, **kw):
        if kw.get('purpose') == 'agent_decide':
            seen.append([dict(m) for m in messages])
        return await _orig(tier, messages, **kw)
    R.llm.chat = fake
    try:
        ag = Agent(ps, db, world)
        asyncio.run(ag.decide(''))
    finally:
        R.llm.chat = _orig

    txt = seen[-1][0]['content'] if seen else ''
    ok('F1 ★★ 预设层**真的进了决策提示词**（不是"函数存在"）',
       '〔你这一类演员' in txt, '')
    ok('F2 ★★ 仲裁规则**真的进了决策提示词**', '以角色为准' in txt, '')
    ok('F3 ★★ 定制层真的进了（身份/秘密都在）',
       '〔在这个本子里' in txt and '帐房' in txt if '帐房' in str(ps.identity)
       else '〔在这个本子里' in txt, '')
    ok('F4 ★★ 演员那一行的手艺真的进了提示词',
       '你这一行的手艺' in txt and '说话方式就是身份' in txt, '')
    ok('F5 提示词没有因此爆掉（仍在预算量级内）',
       600 < len(txt) < 12000, f'{len(txt)} 字')


# ══════════════════════════════════════════════════════════════
#  F 拆书来的手艺进了库
# [EN] F The craft from book deconstruction went into the library
# ══════════════════════════════════════════════════════════════
def test_craft(tmp: Path) -> None:
    from craft import craftmix
    ent = craftmix.load(force=True)['entries']
    mine = {k: v for k, v in ent.items() if v.get('_货架') == '人物与对话'}
    ok('G1 ★★ 新货架「人物与对话」在库里（≥10 条）', len(mine) >= 10,
       f'{len(mine)} 条')
    ok('G2 ★ 每条都有「提示词」（能进提示词的才算手艺，'
       '只有原理那部分是给人读的）',
       all(v.get('提示词') for v in mine.values()),
       str([k for k, v in mine.items() if not v.get('提示词')][:3]))

    # 版权：这一架是**方法**，不许出现成句的原文引用
    # [EN] Copyright: this shelf is a **method**, verbatim quotes from the original text must not appear
    long_quotes = []
    for k, v in mine.items():
        for field in ('原理', '提示词'):
            s = str(v.get(field) or '')
            for ln in s.replace('。', '。\n').splitlines():
                if '「' in ln and '」' in ln and len(ln) > 60:
                    long_quotes.append((k, ln[:40]))
    ok('G3 ★★ 这一架写的是**方法**，不含成句的原文引用'
       '（版权红线：只讲怎么做，不搬原句）', not long_quotes,
       str(long_quotes[:2]))

    from crew import agents as A
    bad = []
    for k, names in A.READS.items():
        sh = A.SHELVES.get(k, ())
        for n in names:
            e = ent.get(n)
            if e is None:
                bad.append((k, n, '条目不存在'))
            elif str(e.get('_货架')) not in sh:
                bad.append((k, n, '架不符'))
    ok('G4 ★★ 每个职位点名的条目都属于它的书架（跨架点名＝把'
       '"这个职位读哪本书"变成假话）', not bad, str(bad[:3]))
    ok('G5 ★ 有书架的职位都点了名（新加的 actor 也在内）',
       all(k in A.READS for k in A.SHELVES), '')


def _logic_main(tmp: Path) -> list:
    print('\n【A】类型库本身')
    test_library(tmp)
    print('\n【B】匹配与同型分流')
    test_match(tmp)
    print('\n【C】两层提示词与仲裁规则')
    test_layers(tmp)
    print('\n【G】拆书来的手艺')
    test_craft(tmp / 'craft')
    print('\n【D/E】装配 · 项目档 · 两份落盘')
    bundle = test_wiring(tmp / 'wire')
    print('\n【F】行为级：真的进了演员提示词')
    test_in_prompt(tmp / 'prompt', bundle)
    return bundle


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix='nws_casting_'))
    try:
        _logic_main(tmp)
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        ok('Z 判据自己跑通（没被异常打断）', False,
           traceback.format_exc().splitlines()[-1])
    finally:
        _safe_rmtree(tmp, ignore_errors=True)

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'casting_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print('\n' + '─' * 62)
    print(f'  选角 / 两层提示词 / 项目档：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"][:110]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
