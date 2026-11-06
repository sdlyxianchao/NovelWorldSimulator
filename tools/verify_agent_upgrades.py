# -*- coding: utf-8 -*-
"""判据：**外部调研的借鉴点是否真的落进了对应的 Agent**（2026-10-10）。

来历
----
用户原话：「所有外部调研的 Agent，你都根据学习的结果优化修改本地对应 Agent 了吗？
**没有的话就实现下**，注意修改完一轮之后需要进行评过，如果效果不好，
可以放弃一部分参考点或者进行针对性优化。」

`developers/docs/外部借鉴/` 下五份报告共提出 40+ 条建议，此前真正落地的只有三四条
（去 AI 指标 / 场记措辞 / 宣发钩子 / 美术读正文）。这一支判据钉住**这一轮新落地的那批**。

★ 这一支判据的写法有两条硬规矩（都是本项目踩出来的）
--------------------------------------------------
1. **不许"在文件里搜得到"就算接上了** —— 必须在**那个函数的那个块里**查。
   反例：`MUMU_AUTOSTART` 在设置页也出现过一次，于是全文件 grep 恒真。
2. **不许只判"名字在不在"** —— 例如空镜那条，要判**人物形象段真的没了**，
   而不是判代码里写了 `no_character` 这个词。

覆盖（每条都写清"防的是什么"）
------------------------------
  A. 第 03 类 美术造型道具声音 —— 画风圣经正负 / 空镜 / 两路权重 / 统一负向 / 声音
  B. 第 02 类 导演与分镜 —— 闭集 / 相邻景别硬规则 / 有界对象 / 节拍配方 / 量化闸门
  C. 第 02 类第 1 条 + 第 01 类第 2 条 —— 场记一致性契约 / 六类检查 / 伏笔账
  D. 第 05 类 多智能体 —— 记忆不可信史料 / 防串台 / Reflexion 反思形状
  E. 第 01 类 编剧 —— 可拍性两条硬规则挂在**两条写作路径**上
  F. 第 04 类 开卷与质量 —— 连续指标接进审计 / 中文分句 / 按句截断

跑法：`.venv/Scripts/python.exe tools/verify_agent_upgrades.py`
报告：`assets/screenshots/agent_upgrades_report.json`

English:
Criterion: **whether the reference points from external research really landed in the
corresponding Agent** (2026-10-10).
Origin
----
User's original words: "For all Agents from external research, did you optimize and modify the
corresponding local Agents based on what you learned?
**If not, then implement it**, note that after a round of modification it needs to be evaluated;
if the effect is not good,
you may abandon some reference points or do targeted optimization."
The five reports under `developers/docs/外部借鉴/` proposed 40+ suggestions in total, but previously
only three or four truly landed
(de-AI metrics / continuity wording / promotion hooks / art reading the main text). This
criterion pins down **the batch newly landed in this round**.
★ There are two hard rules for how this criterion is written (both were learned the hard way in
this project)
--------------------------------------------------
1. **It does not count as wired just because it can be found by searching the file** —— it must be checked **inside that block of that function**.
   Counterexample: `MUMU_AUTOSTART` also appeared once on the settings page, so whole-file grep is always true.
2. **Do not judge only whether the name is present** —— e.g. the empty shot item must judge that **the character image segment is really gone**,
   not judge that the word `no_character` is written in the code.
Coverage (each item clearly states "what it guards against")
------------------------------
  A. Category 03 Art styling props sound —— art style bible positive/negative / empty shot / two-path weights / unified negative / sound
  B. Category 02 Director and Storyboard —— Closed set / hard rules for adjacent shot sizes / bounded objects / beat recipes / quantitative gates
  C. Category 02 item 1 + Category 01 item 2 —— Script supervisor consistency contract / six-category checks / foreshadowing ledger
  D. Category 05 Multi-agent —— Unreliable memory historical material / cross-talk prevention / Reflexion reflection shape
  E. Category 01 Screenwriting —— Two hard rules for filmability hang on **two writing paths**
  F. Category 04 Book opening and quality —— Continuous metrics wired into audit / Chinese sentence splitting / truncate by sentence
How to run: `.venv/Scripts/python.exe tools/verify_agent_upgrades.py`
Report: `assets/screenshots/agent_upgrades_report.json`
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}


def ok(name: str, cond: bool, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    p = APP / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''


def between(text: str, start: str, end: str = '') -> str:
    """取 `start` 之后到 `end` 之前的那一段（**用来把断言钉在一个块里**）。
        English:
    Take the segment after `start` and before `end` (**used to pin assertions inside a block**).
    """
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def code_only(text: str) -> str:
    """去掉**整行注释**后的源码。

    ★★ 为什么必须有这个函数（反例法逼出来的）：本轮有两条判据连着栽在同一个坑上 ——
      `'不可信史料' in core`（撞上旁边的注释）、`'content[:4000]' not in st`
      （撞上我自己写在注释里的"原来是这样写的"）。
      **判据要问"代码干了什么"，不是"文件里有没有这几个字"。**
      凡是要在整份源码里找/排除某个写法的断言，都必须先过这个函数。
      （不处理行尾注释与字符串里的 `#` —— 这里够用，别为它写一个真的词法器。）
    
        English:
    Source code after removing **whole-line comments**.
        ★★ Why this function is required (forced by the counterexample method): this round two criteria failed in the same pit consecutively ——
          `'不可信史料' in core` (collided with the comment next to it), `'content[:4000]' not in st`
          (collided with the "this is how it was originally written" that I myself put in a comment).
          **Criteria must ask "what the code does", not "whether these few characters appear in the file".**
          Any assertion that searches for/excludes a certain writing pattern across the entire source code must first go through this function.
          (Does not handle end-of-line comments or `#` inside strings —— good enough here, don't write a real lexer for it.)
    """
    return '\n'.join(ln for ln in str(text or '').splitlines()
                     if not ln.lstrip().startswith('#'))


# ══════════════════════════════════════════════════════════════════
#  A. 第 03 类：美术 / 造型 / 道具 / 声音
# [EN] A. Category 03: Art / Styling / Props / Sound
# ══════════════════════════════════════════════════════════════════
def test_art() -> bool:
    from image_gen import promptkit as PK
    k = True
    neg = PK.negatives()
    k &= ok('A1 ★★ 负向词有**两档**：通用质量档（lowres / bad anatomy / extra fingers…）'
            '＋ 原有"别画出字"档 —— 原来只有后者',
            all(w in neg for w in ('lowres', 'bad anatomy', 'extra fingers'))
            and 'no watermark' in neg, neg[:90])
    bk = PK.StyleBook('彩墨江南，宣纸质感', palette=['黛青', '赭石'], avoid=['现代物件'])
    k &= ok('A2 ★★ 画风圣经有**正向前缀**（含主色）与**负向前缀**（含这部戏的"忌"）',
            '彩墨江南' in bk.positive_line() and '黛青' in bk.positive_line()
            and '现代物件' in bk.negative_line(), bk.positive_line()[:60])
    # ★ 空镜：要判**那一段真的没了**，不是判代码里有个 no_character 名字
    # [EN] ★ Empty shot: must judge that **that segment is really gone**, not that there is a no_character
    # [EN] name in the code
    full = PK.compose('夜里的院子', book=bk, subject_line='人物形象：掌柜：靛布短褂',
                      no_character=False)
    empty = PK.compose('夜里的院子', book=bk, subject_line='人物形象：掌柜：靛布短褂',
                       no_character=True)
    k &= ok('A3 ★★★ **空镜**真的把人物形象段**整段丢掉**了（不是写一句"不要人"）'
            '—— 原来"空荡的院子"必然画出一个人来',
            '靛布短褂' in full and '靛布短褂' not in empty and '夜里的院子' in empty,
            f'有人版含人物形象={("靛布短褂" in full)} / 空镜版含={("靛布短褂" in empty)}')
    one = PK.compose('x', book=bk, style_boost=1)
    two = PK.compose('x', book=bk, style_boost=2)
    k &= ok('A4 ★★ 两路权重：`style_boost=2` 时风格句**出现两次**（=1 时一次）'
            '——文生图没有数值权重，只能靠位置与重复表达',
            one.count('彩墨江南') == 1 and two.count('彩墨江南') == 2,
            f'boost1={one.count("彩墨江南")} / boost2={two.count("彩墨江南")}')
    k &= ok('A4b ★ `StyleBook.from_art` 拿不到美术产出时返回**空圣经**（宁可不加，也不编）',
            PK.StyleBook.from_art(None).is_empty()
            and PK.StyleBook.from_art(type('N', (), {'ok': False, 'data': {}})()).is_empty(), '')
    # 出图提示词真的走了 promptkit（原来没有质量负向词与空镜）
    # [EN] The image prompt actually went through promptkit (previously there were no quality negative
    # [EN] words and no empty shot)
    src = read('image_gen/ai.py')
    k &= ok('A5 ★★ `image_gen.ai.build_prompt` 真的走了 `promptkit`（块内查，不全文件 grep）',
            'promptkit' in between(src, 'def build_prompt', 'def ai_available')
            and 'no_character' in between(src, 'def build_prompt', 'def ai_available'), '')
    built = __import__('image_gen.ai', fromlist=['ai']).build_prompt('一碗茶', place='茶肆')
    k &= ok('A5b ★ 真调一次 `build_prompt`，出来的负向里**带着质量档**'
            '（原来只有 no text/no watermark）',
            'lowres' in built and 'no watermark' in built, built[-80:])
    # 声音：事件声规整成短名词短语
    # [EN] Sound: event sounds normalized into short noun phrases
    got = PK.event_sounds({'事件声': ['茶盏磕在木桌', '外面传来算盘的响声。', '隔壁响起脚步声']})
    k &= ok('A6 ★★ 事件声被规整成**短名词短语**（砍掉"传来/响起"这类叙述壳）'
            '——将来接音频生成时这一段能直接吃',
            len(got) >= 2 and not any(w in ''.join(got) for w in ('传来', '响起')),
            str(got))
    rows = PK.voice_card_rows({'角色声音': [{'人名': '掌柜', '音色': '低而干', '语速': '慢'}]})
    k &= ok('A7 ★ 声音名片能读出来（人名 + 音色/语速/口音/常用语/非语言五个字段）',
            bool(rows) and rows[0]['人名'] == '掌柜' and rows[0]['语速'] == '慢', str(rows))
    return k


# ══════════════════════════════════════════════════════════════════
#  B. 第 02 类：导演与分镜
# [EN] B. Category 02: Director and storyboard
# ══════════════════════════════════════════════════════════════════
def _fake_world(place='茶肆', seg='入夜', weather='晴'):
    """一个只带 `film.shot_card` 要用的那几样的假世界（不起真程序）。

    ★ 注意这里**不能用 `class W: weather = weather` 那种写法** ——
      类体里被赋值的名字**不会回退到外层函数作用域**，那句会直接 NameError。
      （本轮真踩过：判据整组崩了，而崩因跟被测代码毫无关系。）
    
        English:
    A fake world carrying only what `film.shot_card` needs (does not start the real program).
        ★ Note that here **you cannot use `class W: weather = weather`** ——
          Names assigned inside a class body **do not fall back to the enclosing function scope**; that line will directly raise NameError.
          (Really hit this round: the whole criteria group crashed, and the crash cause had nothing to do with the code under test.)
    """
    class _Clock:
        def segment(self):
            return seg

    class _World:
        pass

    _World.scene = place
    _World.clock = _Clock()
    _World.weather = weather
    _World.on_stage_names = staticmethod(lambda: ['甲'])
    return _World()


def test_film() -> bool:
    from display import film as F
    from crew import gate
    k = True
    k &= ok('B1 ★★ 景别 / 运镜 / 转场都是**闭集**（原来机位是硬编码字符串，不可校验）',
            len(F.SHOT_SIZES) >= 6 and len(F.SHOT_ANGLES) >= 4 and len(F.MOVES) >= 6
            and len(F.TRANSITIONS) >= 3,
            f'{len(F.SHOT_SIZES)}/{len(F.SHOT_ANGLES)}/{len(F.MOVES)}/{len(F.TRANSITIONS)}')
    card = F.shot_card([], _fake_world(), beat='发现')
    d = F.parse_card(card)
    k &= ok('B2 ★★ `shot_card` 出来的机位 / 运镜 / 时长 / 转场**都落在闭集内**',
            F.size_of(d.get('kind', '')) in F.SHOT_SIZES
            and d.get('move') in F.MOVES and d.get('transition') in F.TRANSITIONS
            and bool(d.get('duration')), str({kk: d.get(kk) for kk in ('kind', 'move', 'transition', 'duration')}))
    # ★ 节拍配方：不认识的节拍**不猜**（猜出来的比默认值更糟：会让人以为模型读懂了）
    # [EN] ★ Beat recipe: unknown beats are **not guessed** (a guess is worse than the default: it makes
    # [EN] people think the model understood)
    a = F.recipe_for_beat('发现')
    b = F.recipe_for_beat('一段没人认得出来的情绪')
    k &= ok('B3 ★★ 节拍→镜头配方：认得出的用配方，**认不出的走兜底而不是瞎猜**',
            a[0] == '大特写' and b == F.BEAT_FALLBACK and a != b, f'{a} / {b}')
    # ★★★ 硬规则：相邻景别不得相同
    # [EN] ★★★ Hard rule: adjacent shot sizes must not be the same
    c1 = F.shot_card([], _fake_world(), beat='发现')
    c2 = F.shot_card([], _fake_world(), beat='发现',
                     prev_kind=F.parse_card(c1).get('kind', ''))
    s1, s2 = F.parse_card(c1).get('kind', ''), F.parse_card(c2).get('kind', '')
    k &= ok('B4 ★★★ **相邻镜头景别不得相同**：同一个节拍连给两个镜头，第二个必须换景别'
            '（PenShot 明文规则；没有它，"分镜"就是把同一句话换个说法）',
            s1 != s2 and F.size_of(s1) in F.SHOT_SIZES and F.size_of(s2) in F.SHOT_SIZES,
            f'{s1} → {s2}')
    # 校验器要能抓到坏东西
    # [EN] The validator must be able to catch bad things
    bad_cards = [
        {'day': 1, 'place': 'A', 'kind': '中景·正', 'move': '固定', 'line': '一句'},
        {'day': 1, 'place': 'A', 'kind': '中景·侧45°', 'move': '固定', 'line': '又一句'},   # 撞景别
        {'day': 1, 'place': 'A', 'kind': '超长焦·斜', 'move': '漂移', 'line': ''},          # 不在闭集 + 空行
        # [EN] Shot size collision
        # [EN] Not in the closed set + blank line
    ]
    rep = F.validate_cards(bad_cards)
    names = [f'{f.severity}|{f.what}' for f in rep.findings]
    k &= ok('B5 ★★★ 校验器抓得到三类硬伤：景别不在闭集（P0）/ 相邻同景别（P0）/ 空内容（P1）',
            any(x.startswith('ERROR') and '闭集' in x for x in names)
            and any(x.startswith('ERROR') and '景别相同' in x for x in names)
            and any(x.startswith('CRITICAL') and '空的' in x for x in names), str(names[:4]))
    k &= ok('B5b ★ 运镜不在闭集也要抓（`漂移` 不在表里）',
            any('运镜不在闭集' in f.what for f in rep.findings), '')
    # 有界对象：每场镜头数
    # [EN] Bounded object: number of shots per scene
    few = F.validate_cards([{'day': 1, 'place': 'A', 'kind': '中景·正', 'move': '固定',
                             'line': '一句'}])
    many = F.validate_cards([{'day': 1, 'place': 'A', 'kind': x, 'move': '固定', 'line': '一句'}
                             for x in ('中景·正', '近景·侧45°', '全景·正', '中近景·仰',
                                       '特写·正', '远景·背', '大特写·正', '大远景·俯',
                                       '近景·背')])
    lo, hi = F.SHOTS_PER_SCENE
    k &= ok(f'B6 ★★ 分镜是**有界对象**：一场只有 1 个镜头要报（少于 {lo}）、'
            f'9 个也要报（多于 {hi}）',
            any('少于' in f.what for f in few.findings)
            and any('多于' in f.what for f in many.findings),
            f'{len(few.findings)} / {len(many.findings)}')
    # 同景别连续
    # [EN] Consecutive same shot size
    run4 = F.validate_cards([{'day': 1, 'place': 'A', 'kind': '中景·正', 'move': '固定', 'line': 'x'},
                             {'day': 1, 'place': 'A', 'kind': '近景·正', 'move': '固定', 'line': 'x'},
                             {'day': 1, 'place': 'A', 'kind': '近景·侧45°', 'move': '固定', 'line': 'x'},
                             {'day': 1, 'place': 'A', 'kind': '近景·背', 'move': '固定', 'line': 'x'},
                             {'day': 1, 'place': 'A', 'kind': '近景·仰', 'move': '固定', 'line': 'x'}])
    k &= ok('B7 ★★ 同一景别**连续超过 3 次**要报',
            any('连续' in f.what for f in run4.findings),
            str([f.what for f in run4.findings])[:120])
    # 分镜表带校验结论
    # [EN] Storyboard table with validation conclusion
    md = F.storyboard_md([{'day': 1, 'place': 'A', 'kind': '中景·正', 'move': '固定',
                           'line': '一句', 'transition': '切'}])
    k &= ok('B8 ★ 分镜表末尾带**校验结论**（一份没人核过的分镜表和没有是一样的）',
            '校验' in md and '得分' in md and '| 时长 |' in md, '')
    # 量化闸门
    # [EN] Quantization gate
    g = gate.Report('t')
    k &= ok('B9 ★★ 量化闸门：满分 100 PASSED；扣一个 ERROR（−50）→ 50 FAILED；'
            '扣一个 CRITICAL（−30）→ 70 NEEDS_REVIEW',
            gate.band(100) == 'PASSED' and g.verdict == 'PASSED'
            and (g.add('ERROR', 'w', 'x'), gate.band(g.score))[1] == 'FAILED'
            and (lambda r: (r.add('CRITICAL', 'w', 'y'), gate.band(r.score))[1])(gate.Report('t2'))
            == 'NEEDS_REVIEW', '')
    g2 = gate.Report('t3')
    for _ in range(20):
        g2.add('ERROR', 'w', 'x')
    k &= ok('B9b ★ 扣分**夹在 0 以上**（负分只会让人以为还有额外惩罚）', g2.score == 0, str(g2.score))
    k &= ok('B9c ★ 认不出的档位按 MAJOR 扣（**认不出不等于没问题**）',
            gate.cost('不认识的档') == gate.WEIGHTS['MAJOR'], '')
    return k


# ══════════════════════════════════════════════════════════════════
#  C. 场记契约 + 伏笔账
# [EN] C. Continuity contract + foreshadowing ledger
# ══════════════════════════════════════════════════════════════════
def test_contract() -> bool:
    from crew import contract as CT
    k = True
    # 契约累积 → 六类检查里的「角色」：一个人天天换衣服
    # [EN] Contract accumulation → the "character" among the six checks: a person changing clothes every
    # [EN] day
    c = CT.ConsistencyContract()
    for d, wear in ((1, '靛布短褂'), (2, '月白长衫'), (3, '玄色披风')):
        c.observe(day=d, location='茶肆', time_label='入夜', people=['甲'],
                  outfits={'甲': wear}, props=['茶壶'])
    rep = c.check(day=3, today_people=['甲'], today_place='茶肆', today_time='入夜')
    k &= ok('C1 ★★ 契约累积三天三套穿着 → 「角色」类报 MAJOR（这就是"造型"最容易失效处）',
            any(f.severity == 'MAJOR' and '[角色]' in f.what for f in rep.findings),
            str([f.what[:40] for f in rep.findings])[:150])
    k &= ok('C1b ★ 六类检查的类目名齐（角色/场景/动作/风格/时间/道具）',
            set(CT.KINDS) == {'角色', '场景', '动作', '风格', '时间', '道具'}, str(CT.KINDS))
    # 道具：已毁的东西又出现
    # [EN] Props: something already destroyed appears again
    c2 = CT.ConsistencyContract()
    c2.observe(day=1, location='茶肆', people=['甲'], props=['青瓷壶'])
    c2.mark_prop('茶肆', '青瓷壶', '已毁')
    rep2 = c2.check(day=2, today_place='茶肆', today_props=['青瓷壶'], today_time='入夜')
    k &= ok('C2 ★★★ 「已毁 / 已送出」的东西又出现 → ERROR'
            '（PenShot 六类检查里最实用的一条，也正是模型最常犯的自相矛盾）',
            any(f.severity == 'ERROR' and '[道具]' in f.what for f in rep2.findings),
            str([f.what[:44] for f in rep2.findings])[:150])
    # 去重
    # [EN] Deduplication
    rep3 = c2.check(day=2, today_place='茶肆', today_props=['青瓷壶'], today_time='入夜')
    k &= ok('C3 ★★ 同一条**只报一次**（报过就记账，不重复刷屏）',
            not any('[道具]' in f.what for f in rep3.findings),
            str([f.what[:40] for f in rep3.findings]))
    # 去重键三段
    # [EN] Deduplication key in three segments
    k0 = CT.dedupe_key('道具', '茶肆', 'ERROR', '青瓷壶又出现')
    k &= ok('C4 ★★ 去重键 = **类型_地点_严重度_描述前100字** —— 三段中改任一段，键就必须不同'
            '（少了任一段都会重报或漏报）',
            len({k0, CT.dedupe_key('角色', '茶肆', 'ERROR', '青瓷壶又出现'),
                 CT.dedupe_key('道具', '客栈', 'ERROR', '青瓷壶又出现'),
                 CT.dedupe_key('道具', '茶肆', 'WARNING', '青瓷壶又出现')}) == 4, k0)
    # 伏笔账
    # ⚠ 这里**不许用**任何具体作品的人名/道具名（`verify_generic_project` 盯着这条）——
    #   第一版我随手写了某部书的对联与人物，当场被那支判据打红。
    # [EN] Foreshadowing ledger
    # [EN] ⚠ **Not allowed** here to use any character/prop names from specific works
    # [EN] (`verify_generic_project` watches for this)——
    # [EN] In the first version I casually wrote a couplet and characters from some book, and was
    # [EN] immediately flagged red by that criterion.
    led = CT.ForeshadowLedger()
    led.plant('一件信物', at=1, by=3, keywords=('那把旧钥匙',))
    k &= ok('C5 ★★ 伏笔账三栏齐（埋于 / **最晚回收** / 已回收）—— "最晚哪一章必须回收"'
            '这一栏才是它管用的地方（没有它，"还没回收"永远只是一句感慨）',
            led.items[0].seeded_at == 1 and led.items[0].must_pay_off_by == 3
            and led.items[0].open and led.overdue(1) == [], '')
    k &= ok('C5b ★ 过期限未回收 → 报过期（第 4 天 > 最晚第 3 天）',
            len(led.overdue(4)) == 1 and len(led.overdue(3)) == 0,
            f'at4={len(led.overdue(4))} at3={len(led.overdue(3))}')
    paid = led.scan_text('甲说：把那把旧钥匙收好。', at=2)
    k &= ok('C5c ★★ `scan_text` 按 keywords **确定性**勾回收（"有没有出现"这件事不该靠模型说）',
            paid == ['一件信物'] and not led.items[0].open, str(paid))
    k &= ok('C6 ★★ `pay()` 对**没登记过**的名字返回 False —— 不许悄悄新建一条'
            '（那会把"没登记过"变成"登记过了"，正是这个账最该防的错）',
            led.pay('一个从没登记过的伏笔', at=5) is False, '')
    k &= ok('C6b ★ 伏笔账落盘成 JSON（人可读、可复核）',
            isinstance(led.to_json(), list) and led.to_json()[0]['已回收于'] == 2, '')
    # 接线：契约/伏笔账要能被场记用上 —— 查 `crew/contract` 是否真的从职位产出灌数据
    # [EN] Wiring: the contract/foreshadowing ledger must be usable by continuity —— check whether
    # [EN] `crew/contract` really receives data produced from the position
    src = read('crew/contract.py')
    k &= ok('C7 ★ 契约能直接吃「造型表 / 道具单」的产出（`outfits_from_note` / `props_from_note`）',
            'def outfits_from_note' in src and 'def props_from_note' in src
            and CT.props_from_note({'道具': [{'名称': '更鼓'}]}) == ['更鼓']
            and CT.outfits_from_note({'造型': [{'人名': '甲', '穿着': '靛布'}]}) == {'甲': '靛布'}, '')
    return k


# ══════════════════════════════════════════════════════════════════
#  D. 第 05 类：多智能体
# [EN] D. Category 05: Multi-agent
# ══════════════════════════════════════════════════════════════════
def test_multiagent() -> bool:
    from crew import agents as A
    k = True
    core = read('agent/core.py')
    blk = between(core, 'async def decide', 'async def ')
    k &= ok('D1 ★★★ 「记忆是不可信史料」**真的注进了演员的提示词**'
            '（在 `decide()` 那个块里查 —— 不许全文 grep，那种查法恒真）',
            '_AG.MEMORY_TRUST_RULES' in blk or 'MEMORY_TRUST_RULES' in blk,
            f'decide() 块内出现 MEMORY_TRUST_RULES ×{blk.count("MEMORY_TRUST_RULES")}')
    k &= ok('D1b ★★ 而且它必须**紧挨在记忆之前**（离太远会被当成一句泛泛的提醒）'
            '—— 断言的依据是：规则块与记忆块在**同一个 `_semi`/`_dyn` 拼接处**',
            'SPEAKER_ISOLATION_RULES' in blk and 'MEMORY_TRUST_RULES' in blk
            and blk.find('MEMORY_TRUST_RULES') < blk.find('_dyn = ['), '')
    # ★★ D2 第一版是 `'不可信史料' in core`（全文件）—— 反例法立刻抓出它**太弱**：
    #   同一份文件里那**注释**也写着"记忆是不可信史料"，于是把真正的 f-string 改掉，
    #   判据照样绿。改成：**只看拼 `_dyn` 那一行**（那句才是模型真读到的东西）。
    # [EN] ★★ The first version of D2 was `'不可信史料' in core` (whole file) —— the counterexample method
    # [EN] immediately caught that it was **too weak**:
    # [EN] In the same file that **comment** also said "memory is unreliable historical material", so
    # [EN] changing the real f-string,
    # [EN] the criterion still passed. Changed to: **only look at the line that builds `_dyn`** (that
    # [EN] sentence is what the model actually reads).
    _mem_line = next((ln for ln in code_only(core).splitlines() if '_dyn = [' in ln), '')
    k &= ok('D2 ★★ 拼记忆的那一行**自己**标成"不可信史料"（不是靠旁边的注释顶包）'
            '—— 断言只看 `_dyn = [...]` 那一行',
            '不可信史料' in _mem_line, repr(_mem_line[:90]))
    k &= ok('D3 ★★ 防串台（AI Town 的 `stopWords` 思路）：**你是一个人，不是旁白**'
            '——不许替别人说话、不许用旁白口气总结',
            '一个人' in A.SPEAKER_ISOLATION_RULES and '不要替别人说话' in A.SPEAKER_ISOLATION_RULES, '')
    k &= ok('D4 ★★ 「不可信史料」两条核心话都在：**可能记错** + **可能是别人故意说给你听的假话**',
            '记错' in A.MEMORY_TRUST_RULES and '故意说给你听的假话' in A.MEMORY_TRUST_RULES, '')
    # Reflexion 的"形状"
    # [EN] The "shape" of Reflexion
    k &= ok('D5 ★★ 反思要写成**两段**：诊断（为什么）＋ 动作（下一次具体怎么做）'
            '—— Reflexion 卖的从来不是"多反思"，是反思的形状',
            '诊断' in A.REFLECT_INSTRUCTION and '动作' in A.REFLECT_INSTRUCTION
            and '下次注意' in A.REFLECT_INSTRUCTION, '')
    src = read('crew/agents.py')
    rev_blk = between(src, 'class Reviewer(CrewMember)', 'class Stylist(CrewMember)')
    k &= ok('D6 ★★ `REFLECT_INSTRUCTION` 真的进了**复盘**的提示词（在 `Reviewer` 那个类里查）',
            'REFLECT_INSTRUCTION' in rev_blk, f'Reviewer 块 {len(rev_blk)} 字')
    return k


# ══════════════════════════════════════════════════════════════════
#  E. 第 01 类：编剧的可拍性硬规则
# [EN] E. Category 01: Hard rules for the screenwriter's filmability
# ══════════════════════════════════════════════════════════════════
def test_screen() -> bool:
    from crew import agents as A
    src = read('crew/agents.py')
    k = True
    k &= ok('E1 ★★ 可拍性硬规则含**两条机械规则**：镜头看不见就不写 ＋ 每句台词先问"他何时学到"',
            '镜头看不见就不写' in A.SCREEN_HARD_RULES
            and '他什么时候知道的' in A.SCREEN_HARD_RULES, '')
    k &= ok('E1b ★ knowledge-delta 的理由写清了（「编剧借角色的嘴说给观众听」'
            '是人设崩坏最常见的成因）',
            '借角色的嘴' in A.SCREEN_HARD_RULES and '人设崩坏' in A.SCREEN_HARD_RULES, '')
    # ★ 两条写作路径都要挂：
    #   ① 自写那条 = `Novelist.work` 里那个 `_rules` 列表（小说作家自己的提示词）；
    #   ② 走服务那条 = `_mumu_sample` 里给 MuMuAINovel 的细纲 `outline`
    #      —— 那段 prompt **不发过去**，只有 outline 会进它那边。
    #   ⚠ 锚点必须取在这两个**那个块里**（判据铁律：不许全文件 grep，那种查法恒真）。
    # [EN] ★ Both writing paths must be hooked:
    # [EN] ① The self-writing path = the `_rules` list in `Novelist.work` (the novelist's own prompt);
    # [EN] ② The service path = the detailed outline `outline` given to MuMuAINovel in `_mumu_sample`
    # [EN] —— That prompt is **not sent over**; only the outline enters its side.
    # [EN] ⚠ The anchor must be taken in these two **inside that block** (iron rule of criteria: no
    # [EN] whole-file grep, that kind of check is always true).
    self_path = between(src, 'class Novelist(CrewMember)', 'class Screenwriter(CrewMember)')
    mumu_path = between(src, 'async def _mumu_sample', 'def craft_block')
    k &= ok('E2 ★★★ 硬规则挂在**两条写作路径**上：自写那条（`Novelist` 的 `_rules`）'
            '与走创作服务那条（`_mumu_sample` 的细纲）—— 只挂一条等于另一条路上没这回事',
            'SCREEN_HARD_RULES' in self_path and 'SCREEN_HARD_RULES' in mumu_path,
            f'自写路径 {self_path.count("SCREEN_HARD_RULES")} 次 · '
            f'服务路径 {mumu_path.count("SCREEN_HARD_RULES")} 次')
    k &= ok('E3 ★ 编号是跟着算的（关掉一条不会留下断号）',
            "len(_rules) + 5" in self_path, '')
    return k


# ══════════════════════════════════════════════════════════════════
#  F. 第 04 类：开卷与质量
# [EN] F. Category 04: Open-book and quality
# ══════════════════════════════════════════════════════════════════
def test_ingest_quality() -> bool:
    from style import deai
    from util import text as T
    k = True
    long_zh = ('天还没亮，茶肆的门就开了。掌柜把灯挑亮，火苗跳了一下。\n'
               '外面下着细雨，青石板上积了水。有人从檐下走过，脚步很轻。\n'
               '他把壶放到炉上，等着水开。屋里很静，只有水声。\n'
               '过了半个时辰，来了第一位客人。他披着一件旧蓑衣，抖了抖水。') * 6
    r = deai.audit_text(long_zh, with_metrics=True)
    k &= ok('F1 ★★ 连续指标**真的接进了审计**（`with_metrics=True` 时填 `metrics`）'
            '—— 原来这份审计只有"命中/没命中"两态，看不见"没命中但读着像机器写的"',
            bool(r.metrics) and '漂移' in r.metrics and '句首多样性' in r.metrics,
            str(sorted(r.metrics)[:6]))
    r2 = deai.audit_text('很短的一句。')
    k &= ok('F2 ★★ 默认**不算**连续指标（短文本上句长变异天然小 ⇒ 会把好文字报成"过于均匀"'
            '—— 这个坑在 `ai_metrics` 上踩过，所以默认关）',
            r2.metrics == {} and r2.checked >= 0, str(r2.metrics))
    # ok 不受 metrics 影响
    # [EN] ok is not affected by metrics
    r3 = deai.audit_text(long_zh, with_metrics=True)
    k &= ok('F3 ★★ `ok` **只按硬禁算**，连续指标不参与 —— 两套判据不许混成一个 `ok`',
            r3.ok == (not r3.hard), f'ok={r3.ok} hard={len(r3.hard)}')
    # metric_flags 人话
    # [EN] metric_flags in plain language
    uni = {'metrics': {'漂移': {'态': '过于均匀'}, '句首多样性': 0.2, '四字重复率': 0.05},
           'hits': [], 'checked': 1}
    fake = deai.AuditResult(**{kk: vv for kk, vv in uni.items() if kk != 'metrics'})
    fake.metrics = uni['metrics']
    flags = fake.metric_flags()
    k &= ok('F4 ★★ 连续指标出的是**人话建议**（"句长过于均匀…试着把长短句掺开"），'
            '不是把四个数原样念一遍',
            any('过于均匀' in x for x in flags) and any('掺开' in x for x in flags)
            and len(flags) <= 4, str(flags)[:160])
    mdd = deai.render_report(fake, title='t')
    k &= ok('F4b ★ 报告里有"连续指标栏"这一节',
            '连续指标栏' in mdd or '读起来像不像人写的' in mdd, '')
    # 中文分句
    # [EN] Chinese sentence splitting
    _one_line = '他说：「来了。」……屋里很静；灯灭了。'
    sents = T.sentences_zh(_one_line)
    k &= ok('F5 ★★ 中文分句认**省略号**且不切空句（英文那套按 `.` 切在中文上会切出空句）',
            all(s.strip() for s in sents) and len(sents) >= 3, str(sents))
    # ★★ F5b 是反例法补的：F5 原来只判"切出 ≥3 段且不为空"，把分句退回英文切法
    #   照样绿（切出来的段数差不多）。真正该钉的是**中文分句的两个性质**：
    #     ① **标点留在句子里**（一个字都不许丢）；② 每段都以句末标点收住。
    # [EN] ★★ F5b was added by the counterexample method: F5 originally only judged "split out ≥3 segments
    # [EN] and not empty", regressing the sentence splitting to the English splitting method
    # [EN] and it still passed (the number of split segments was about the same). What should really be
    # [EN] pinned down are **the two properties of Chinese sentence splitting**:
    # [EN] ① **Punctuation stays in the sentence** (not a single character may be lost); ② each segment
    # [EN] ends with sentence-ending punctuation.
    k &= ok('F5b ★★★ 分句**不丢字**且每段都以句末标点收住'
            '（否则"切出几段"这个判据太粗，退回英文切法也照样绿）',
            ''.join(sents).replace(' ', '') == _one_line.replace(' ', '')
            and all(s[-1] in '。！？!?…；;' for s in sents),
            f'拼回={ "".join(sents)!r } 段尾={ [s[-1] for s in sents] }')
    # 按句截断
    # [EN] Truncate by sentence
    cut = T.head_sentences(long_zh, 60)
    k &= ok('F6 ★★★ 开卷的"风格卡前 4000 字 / 前情每章前 1500 字"改成**按句截断**'
            '—— 原来截在半句上，而**残句在模型眼里也是一种句式**，它会跟着学',
            bool(cut) and cut[-1] in '。！？!?…' and len(cut) <= 60, repr(cut[-24:]))
    short = '很短。'
    k &= ok('F6b ★ 文本比预算短时**原样返回**（不做多余处理）',
            T.head_sentences(short, 60) == short, '')
    k &= ok('F6c ★★ 截断**不许退太多**（退到 60% 以下就是白给预算）'
            '—— 判据：100 字的文本取 50 字，结果长度必须 ≥ 20',
            len(T.head_sentences('甲。' + '乙' * 60 + '。' + '丙' * 60 + '。', 50)) >= 20,
            str(len(T.head_sentences('甲。' + '乙' * 60 + '。' + '丙' * 60 + '。', 50))))
    # 接线：ingest 真的用了它（块内查）
    # ★★ F7 第一版判 `'head_sentences' in st` —— 反例法抓出它**太弱**：
    #   把 `head_sentences(content, 4000)` 改回 `content[:4000]` 之后，
    #   **上面那行 `from util.text import head_sentences` 还在** ⇒ 判据照样绿。
    #   ⇒ 要判的是**调用**（带括号），不是"名字出现过"。
    # [EN] Wiring: ingest really used it (checked inside the block)
    # [EN] ★★ The first version of F7 judged `'head_sentences' in st` —— the counterexample method caught
    # [EN] that it was **too weak**:
    # [EN] After changing `head_sentences(content, 4000)` back to `content[:4000]`,
    # [EN] **the line `from util.text import head_sentences` above is still there** ⇒ the criterion still
    # [EN] passes.
    # [EN] ⇒ What must be judged is the **call** (with parentheses), not "the name appeared".
    st = read('ingest/style.py')
    pg = read('ingest/progress.py')
    k &= ok('F7 ★★★ `ingest/style.py`（风格卡 4000 字）与 `ingest/progress.py`（前情 1500 字）'
            '**都真的调用了**按句截断 —— 判"调用"（`head_sentences(`）而不是"名字出现过"，'
            '否则光留着 import 就能骗过它',
            'head_sentences(' in st and 'head_sentences(' in pg,
            f'style={st.count("head_sentences(")} progress={pg.count("head_sentences(")}')
    # ★★ 这一条（F7b）第一版直接在全文件里找 `content[:4000]` —— 撞上了我自己写在
    #   **注释**里的"原来是这样写的"，判据当场假红。⇒ 先剥掉整行注释再找。
    # [EN] ★★ This one (F7b) in its first version directly searched the whole file for `content[:4000]` ——
    # [EN] it hit the "it used to be written like this" that I wrote in
    # [EN] a **comment**, and the criterion went false red on the spot. ⇒ Strip the entire comment line
    # [EN] first, then search.
    k &= ok('F7b ★★★ 代码里**没有**改回裸切片（剥掉注释后找 `content[:4000]` / '
            '`ch_text[:1500]`）—— 上一版没剥注释，被自己写的说明文字顶红了',
            'content[:4000]' not in code_only(st) and 'ch_text[:1500]' not in code_only(pg),
            f'style={code_only(st).count("content[:4000]")} '
            f'progress={code_only(pg).count("ch_text[:1500]")}')
    k &= ok('F7c ★ 顺带钉住那个辅助函数本身：`code_only()` 真的会把整行注释剥掉'
            '（否则上面两条只是"看起来在剥"）',
            '不在这份代码里' not in code_only('# 不在这份代码里\nx = 1\n')
            and 'x = 1' in code_only('# 不在这份代码里\nx = 1\n'), '')
    return k


def main() -> int:
    checks = [('美术造型声音', test_art), ('导演与分镜', test_film),
              ('场记契约与伏笔账', test_contract), ('多智能体', test_multiagent),
              ('编剧可拍性', test_screen), ('开卷与质量', test_ingest_quality)]
    for name, fn in checks:
        try:
            fn()
        except Exception:                                       # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    path = APP / 'assets' / 'screenshots' / 'agent_upgrades_report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n外部借鉴落地验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
        if c['detail']:
            print(f'      {c["detail"][:400]}')
    print('→ 全部通过' if not bad else '→ 有失败项')
    print('报告 ->', path.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
