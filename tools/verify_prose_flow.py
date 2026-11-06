# -*- coding: utf-8 -*-
"""判据：**整理稿的句法与承接**——别把小说写成"材料逐条翻译"（2026-10-19）。

用户原话
--------
「下面这样的小短句子特别多 每一句都恨不得交代一个事情 而没有像正常小说一样
用长一些的句子慢慢描写 而且这段话逻辑非常混乱 虽然总体剧情是对的 是雪夜有人
送酒来 但是说话没逻辑 酒还温着 你 可能是叶子 希望别出什么事才好 你觉得我是什么样的人
之间没有任何关系 并没有关联到雪夜送酒这个主题上来 非常乱 而且这种问题一直没修复好」

先量，别猜（`developers/probe_*.py`）
------------------------------------
三轮探针把"句子短"这个直觉**否掉**了 —— 产物与真人样本在同一区间：

| 指标 | 真人 | 产物 ykg1000 | 判读 |
|---|---|---|---|
| 句长中位 | 8.4 | 11 | 产物**更长** |
| 叙述句中位 | 10.6 | 10 | 持平 |
| 分句/句号 | 2.38 | 2.30 | 持平 |
| 极短句(≤6字)% | 29.1 | 31.5 | 持平 |
| 相邻句承接% | 31.0 | 23.1 | 偏低但不显著 |

⇒ 问题**不在统计分布**，在**生成机制**：`crew/agents.Novelist._transcribe_once`
把材料（一拍一条动作 / 一条心声 / 一条环境）**逐条翻成一句**。
量出来的形状是"句号多、句子等长"，而用户读到的是"分镜表"。

根因是提示词里那句「材料里有的场次、动作、对白，**一处都不许跳过**」——
它本来是为了防"挑几段写"，模型却理解成"每一行都要在正文里占一句"。

⚠ 所以这里的判据**不许把那条删掉**（那是 `verify_novel_fullness.B11` 守着的
防漏要求），而是要求它**成对**存在：事件一处不漏 + 句子必须合并。
删任何一半都会退回另一种坏（漏内容 / 分镜表）。

判据分组
--------
  A 提示词：逐条翻译是错的（给了反面写法 + 自查线）
  B 提示词：长句要求（每场至少一句 25 字以上，用来铺开动作）
  C 提示词：台词要有来去（后一句回前一句；接不上要用动作垫）
  D 提示词：心里话要有主（不许留裸的疑问句）
  E 成对：口癖"只留第一次"还在，**且**明写"字数不许缩水"
  F 真跑：抓 `_transcribe_once` 实际发出去的 prompt（"写了 ≠ 生效"）
  G 行为：句法闸 —— 长句少于阈值的一段会被判成"清单段"（工具函数必须真能用）

跑法：`.venv/Scripts/python.exe tools/verify_prose_flow.py`
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                         # noqa: E402
from config import SPEC                                        # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'   [{detail}]' if detail else ''),
          flush=True)
    return bool(cond)


def _prompt_src() -> str:
    from crew import agents as A
    return inspect.getsource(A.Novelist._transcribe_once)


# ══════════════════════════════════════════════════════════════
#  A  逐条翻译是错的
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    s = _prompt_src()
    ok('A0 ★ 取到了 `_transcribe_once` 的源码（否则下面全是"没数据 ⇒ 绿"）',
       len(s) > 1500, f'{len(s)} 字')

    ok('A1 ★★★ 明写"这是整理，不是逐条翻译"（把机制说出来，模型才知道'
       '"覆盖材料"不等于"一行动作写一句"）',
       '不是"逐条翻译"' in s or '不是逐条翻译' in s, '')
    ok('A2 ★★★ 点名了**材料的两侧不等价**：一行动作/心声/环境 ⇏ 正文一句',
       '一行的回译' in s or '不等于' in s, '')
    # 反面写法必须是**真跑产物里的原句**（抽象口号模型不当回事）
    ok('A3 ★★★ 给了**反面例子**（真跑产物里那种三短句并排）',
       '指尖碰了碰她耳后' in s or '声音很轻' in s, '')
    ok('A4 ★★★ 也给了**正面例子**（同一信息并成一个长句）',
       '那片皮肤是凉的' in s or '并成一句' in s, '')
    ok('A5 ★★★ 给了**可自查的线**，而且与代码里的判据同口径'
       '（`crew.prose_flow.list_like_spans` 判的是"整段一句都没铺开"，'
       '不是"连着三句都短" —— 后者在真跑产物上**量不出来**：那段句子 8–18 字，不算短）',
       '一句都没铺开' in s and '清单' in s, '')
    # ★★★ 并句的**边界**（2026-10-19 真跑实证）：只说"几条并成一句"，模型把**对话也并进去了**
    #   ⇒ 台词从 29 句掉到 8 句，一场戏变成摘要（"叶子又送酒，驹子催他说出哪儿好"）。
    # [EN] The **boundary** of merging: with only "merge a few items into one sentence", the model
    # [EN] merged **dialogue** too (dialogue lines dropped 29 -> 8 and the scene became a summary).
    ok('A6 ★★★ 明写**台词不并**：开口就照原样写成引号里的一句，不许压成"他说了……"的转述',
       '台词不并' in s and '转述' in s, '')
    ok('A7 ★★ 而且给了**代价**（"一场戏变成了摘要""台词数会掉一大截"）——'
       '只说"不许转述"模型不当回事',
       '摘要' in s and '掉一大截' in s, '')


# ══════════════════════════════════════════════════════════════
#  B  长句要求
# ══════════════════════════════════════════════════════════════
def group_b() -> None:
    s = _prompt_src()
    # ★★★ **例子会被当素材抄**（R23，第九轮补）。实测两次：正面例子"你这个人哪"
    #   真跑用了 8 次；反面例子"你觉得我是个什么样的人？"被**照抄进正文**。
    #   ⇒ 判"提示词里有没有可以直接抄的完整台词"。
    # [EN] **Examples get copied as material** (R23, added in round nine). Measured twice: a
    # [EN] positive example was reused 8 times, a negative one was copied into the prose. So judge
    # [EN] whether the prompt contains whole lines a model can lift verbatim.
    from crew.prose_flow import quotable_examples as _QE
    _bad_ex = _QE(_prompt_src())
    ok('A8 ★★★ 提示词里**没有可以直接抄的完整台词**'
       '（举例子只许给形态和占位；正反例都会被抄 —— 实测正例用了 8 次、'
       '反例被原样写进正文）',
       _bad_ex == [], f'{_bad_ex[:3]}' if _bad_ex else '干净')
    # 成对：占位式写法**不许被判成"可抄"**（否则这条会逼着人删掉必要的格式示例）
    # [EN] Paired: placeholder forms must **not** count as copyable, otherwise this criterion
    # [EN] would push people to delete the format examples that are genuinely needed.
    ok('A9 ★★★ 成对：**占位写法不算可抄**（`“……”` / `“（一句问话）”` / 术语不是台词）',
       _QE('她说：“……”；也可以写“（一句问话）”；字段 `body` 别动；只学笔调。') == [],
       str(_QE('她说：“……”；也可以写“（一句问话）”；字段 `body` 别动；只学笔调。')))

    ok('B1 ★★★ 每场至少一句**长句**，并给了数字（"二十五个字以上"）——'
       '只写"要写长句"没有阈值，模型会写成十五字',
       '二十五个字' in s, '')
    ok('B2 ★★ 说清了长句**拿来干什么**（把动作和它周围的东西一起交代完，不是凑字数）',
       '一起交代完' in s or '铺开' in s, '')
    # ★★★ 钟摆的另一头（2026-10-19 真跑实证）：只加"要有长句"，产出**矫枉过正** ——
    #   句长中位 10 → 20 字、长句占比 15% → 42%，读起来喘不上气。
    #   所以"要有长句"后面必须成对跟一条"**长句最多占三成**"。
    # [EN] The other end of the swing (measured): adding only "must have long sentences" overshot
    # [EN] (median 10 -> 20 chars, long-sentence share 15% -> 42%). So the requirement must be
    # [EN] paired with "long sentences at most 30%".
    # ⚠⚠ **这条判据修过一次（2026-10-19 第九轮）**：原判
    #   `'不超过四十个字' in s`，而那句话后来变成了**反面教材**
    #   （"实测'不超过四十个字'这种字数上限模型根本不数"）——
    #   判据于是靠着一句"这条没用"的话保持常绿。**源码含字符串当判据的典型翻车。**
    #   现在判的是**真正给出的上限**：事件数（两句上限的事）与长句配额。
    # [EN] ⚠⚠ **Rewritten once (round nine)**: the old version judged
    # [EN] `'不超过四十个字' in s`, but that sentence later became a **counter-example**
    # [EN] ("measured: a character-count cap is something the model simply does not count"), so the
    # [EN] criterion stayed green off a sentence saying that approach is useless. Classic failure of
    # [EN] "source contains a string" criteria. It now judges the caps that really exist: how many
    # [EN] events may share one full stop, and the long-sentence quota.
    ok('B3 ★★★ 成对：**不许整篇都是长句**，给的是**能数出来的上限**'
       '（"一个句号里最多装两件事" ＋ "三句里有一句长的就够"）',
       '最多装两件事' in s and '三句里有一句长的就够' in s, '')
    ok('B4 ★★★ 段落也钉了（"一段三到六句 / 两百字以内"）—— 真跑实测最长一段 362 字，'
       '一次写到底读者看不到换气的口子',
       '三到六句' in s and '两百字' in s, '')


# ══════════════════════════════════════════════════════════════
#  C  台词要有来去
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    s = _prompt_src()
    ok('C1 ★★★ 要求后一句**回**前一句（答 / 反问 / 被那句话改变了动作）',
       '回**前一句' in s or '回前一句' in s, '')
    ok('C2 ★★★ 说清了"接不上怎么办"：用**动作或环境垫在中间**把时间接过去'
       '（只说"要接住"不给出路，模型会硬接成一句驴唇不对马嘴的话）',
       '垫在中间' in s, '')
    ok('C3 ★★★ 要求一场戏的话**围着同一件事**，跑题的台词改成"他没接这句"',
       '同一件事' in s and '没接这句' in s, '')
    # ⚠⚠ **这条判据原来要求反例里写具体台词，方向是错的**（2026-10-19 第九轮改）。
    #   原判：`'水还温着' in s and '外头好像有人' in s` —— 它逼着提示词里必须放三句
    #   现成台词。而实测证明**反面例子照样被照抄**（"你觉得我是个什么样的人？"就被抄了）。
    #   ⇒ 新口径：反面例子要**具体到形态**（三个引号各自独立、中间没垫着、彼此看不出关系），
    #     并且**明写"这里故意不给例句"**。具体到句子是错的，具体到形态才对。
    # [EN] ⚠⚠ This criterion previously **required** concrete lines in the counter-example, which
    # [EN] pointed the wrong way: measured, a negative example was copied into the prose just the
    # [EN] same. The new rule: the counter-example must be concrete **about the shape** (three
    # [EN] quotes standing alone, nothing in between, no visible relation) and must **say that no
    # [EN] sample line is given on purpose**. Concrete about the shape is right; concrete about the
    # [EN] word is wrong.
    ok('C4 ★★★ 反面例子**具体到形态**（三个引号各自独立 / 中间没垫着 / 看不出关系），'
       '并且明写"故意不给例句" —— 反例给了句子就会被照抄',
       ('三个引号各自独立' in s and '没有动作或反应垫着' in s
        and '故意不给例句' in s and '照抄' in s), '')


# ══════════════════════════════════════════════════════════════
#  D  心里话要有主
# ══════════════════════════════════════════════════════════════
def group_d() -> None:
    s = _prompt_src()
    ok('D1 ★★★ 明写**不许留裸的疑问句**（产物里"走廊上是谁？"独立成句，'
       '读者以为是叙述者在问）',
       '没有主人的问句' in s or '裸的疑问' in s, '')
    ok('D2 ★★★ 给了**改法**（挂到人身上 / 化成动作里的迟疑），不只是禁令',
       '他没问' in s and '咽下去' in s, '')
    ok('D3 ★★★ 成对：**内心只能来自材料**那条还在（不许因为"要有主"就替人补心事）',
       '心里话只能来自材料' in s or '心里话只有视角人物能说' in s, '')


# ══════════════════════════════════════════════════════════════
#  E  口癖：去得掉，但不许因此变短
# ══════════════════════════════════════════════════════════════
def group_e() -> None:
    s = _prompt_src()
    # ★★★ 2026-10-21 换了锚点。这条原来钉的是「删到只剩一次」——
    #   而那份专业分析报告指出的正是「删到一次」的坏处：读者第四遍就猜到，而且原地踏步。
    #   规则已合并成「最多三次、每次多知道一件」，所以判据跟着钉**新规则**，
    #   并且**成对**钉住「不许退回一刀切」。
    #   ⚠ 背后的教训（字数不许缩水 / 给补法）没有变，见 E2、E3 ——
    #     换锚点不等于放宽，只是把钉子钉到新墙上。
    # [EN] ★★★ Anchor changed 2026-10-21. This used to pin "cut down to a single instance", and the
    # [EN] professional review's complaint is exactly that "single instance" is where the reader stops
    # [EN] learning. The rule merged into "at most three, each revealing one more thing", so the
    # [EN] criterion pins the **new** rule and, pairwise, forbids the old one-size-fits-all wording.
    # [EN] ⚠ The underlying lesson (do not shrink the word count / do provide the refill) is
    # [EN] unchanged -- see E2 and E3. Changing the anchor is not loosening the check.
    ok('E1 ★★★ 重复变奏的**新规则**在（最多三次 + 三次各管一件事）',
       '同一件事最多三次' in s
       and all(k in s for k in ('立规矩', '试规矩', '破规矩')), '')
    ok('E1b ★★★ 成对：**不许退回一刀切**（「删到只剩一次」那条旧说法不许回来）',
       '只留第一次' not in s, '回来了' if '只留第一次' in s else '已合并')

    ok('E2 ★★★ 明写**字数不许因此缩水**（上一轮去口癖把 1225 字压到 534 字，'
       '用户原话："适当去掉口头禅但是不要减少字数"）',
       '不允许因此缩水' in s or '字数不许因此缩水' in s, '')
    ok('E3 ★★★ 给了**补法**（用动作 / 沉默 / 这场戏的细节补足）——'
       '只说"不许变短"不给出路，模型会改成注水',
       '沉默' in s and '补足' in s, '')


# ══════════════════════════════════════════════════════════════
#  F  真跑：发出去的 prompt 里真有这些
# ══════════════════════════════════════════════════════════════
def group_f() -> None:
    """★★★ "模板里写了 ≠ 生效"：A–E 读的是源码，这里读**真发出去的那一坨**。

    ⚠ 必须让 f-string 求值一次 —— 占位符写错名字在语法层看不出来
      （本轮真踩过：`{_inner_rule}` 改名后漏改一处，ast 全绿、运行 NameError）。
    """
    from crew import agents as A
    seen: dict = {}
    real_ask = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''

        class R:
            ok = True
            value = '（测试输出）'
            notes = []
        return R()

    A.ask = fake_ask
    try:
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'

        class Ctx:
            def world_brief(self, k=500):
                return '世界观'

            def genre(self):
                return ('', '')
        asyncio.run(A.Novelist._transcribe_once(
            n, Ctx(), '· 动作 甲：擦壶', scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask

    p = str(seen.get('prompt') or '')
    ok('F0 ★★★ `_transcribe_once` 真跑成功、抓到了 prompt'
       '（f-string 占位符名写错会在这里 NameError，而不是在语法检查里）',
       len(p) > 800, f'{len(p)} 字')
    for key, label in (('不是"逐条翻译"', 'A1 逐条翻译禁令'),
                       ('二十五个字', 'B1 长句阈值'),
                       ('垫在中间', 'C2 台词接不上的出路'),
                       ('没有主人的问句', 'D1 裸疑问禁令'),
                       ('字数不许因此缩水', 'E2 口癖不许减字数')):
        ok(f'F1 ★★★ 发出去的 prompt 里真有「{label}」', key in p, '')
    ok('F2 ★★★ 成对：**"一处都不许跳过"也还在**（防漏那条不许被这次改动冲掉 —— '
       '`verify_novel_fullness.B11` 守着它）',
       '一处都不许跳过' in p, '')
    ok('F3 ★★ 编号从 1 连续到 12，没有重号/跳号'
       '（改编号时最容易留下两个 6、或者 10 之后的 `_inner_rule` 没接上）',
       all(f'{i}. ' in p for i in range(1, 13)), '')


# ══════════════════════════════════════════════════════════════
#  G  行为：清单段检测器（给后续"改写自检"用，现在先钉住它算得对）
# ══════════════════════════════════════════════════════════════
def group_g() -> None:
    from crew.prose_flow import list_like_spans, long_sentence_ratio

    # 真跑产物里那一段（用户点名过的）
    bad = ('他伸手，指尖碰了碰她耳后的皮肤，凉的。声音这么轻，都给雪吸掉了。'
           '走廊上是谁？门外没有脚步声。她忽静，说："她恨我。"笑一声。')
    # 同信息的"并成一句"写法
    good = ('他伸手过去，指尖碰到的那片皮肤是凉的，她没动，屋里静得能听见灯芯炸响，'
            '雪把两个人的呼吸都吸掉了。')
    sb = list_like_spans(bad)
    sg = list_like_spans(good)
    ok('G1 ★★★ 清单段检测器认得**真跑产物里的那一段**（连续短句 ⇒ 报出跨度）',
       bool(sb), f'{len(sb)} 段')
    ok('G2 ★★★ 成对：**并成一句的同一段**不报（否则它只会把好文字也判成坏）',
       not sg, f'{len(sg)} 段')
    ok('G3 ★★ 长句占比：坏的低于好的（同一把尺子，方向不能反）',
       long_sentence_ratio(bad) < long_sentence_ratio(good),
       f'{long_sentence_ratio(bad)} vs {long_sentence_ratio(good)}')
    # 边界：两个短句不算"清单"（真人也会连用两短句 —— 门槛太严会误伤）
    # ── 时序锚（第六轮，用户贴的分析第一条：「时序与因果关系的混乱（最严重）」）──
    # [EN] Time anchors (round six; the user's first complaint: scrambled chronology).
    from crew.prose_flow import time_anchor_issues, time_note
    t_once = ('岛村说：“终于到了，先休息一下吧。”叶子递茶进来。'
              '过了很久，岛村又说：“终于到了，先休息一下吧。”')
    ok('J1 ★★★ **一次性短语**重复被抓出来（"终于到了"说两遍 = 人到过两回 —— '
       '用户原文点名的就是这个）',
       any(b['kind'] == 'once' and b['what'] == '终于到了'
           for b in time_anchor_issues(t_once)), time_note(t_once))
    ok('J2 ★★★ 成对：**只出现一次时不许报**（那是正常叙述，报了就是噪音）',
       time_anchor_issues('岛村说：“终于到了。”随后把行李放下。') == [],
       repr(time_anchor_issues('岛村说：“终于到了。”随后把行李放下。')))
    t_turn = '夜深了，更鼓一声。夜深了。夜深了。'
    ok('J3 ★★★ **时段转折**超配额被抓出来（「夜深了」反复盖章 = 时间轴糊了）',
       any(b['kind'] == 'turn' for b in time_anchor_issues(t_turn)), time_note(t_turn))
    ok('J4 ★★ 边界：**同一个转折报一次就够**（"夜深了"包含"夜深"，不许报两条）',
       len([b for b in time_anchor_issues(t_turn) if b['what'].startswith('夜深')]) == 1,
       time_note(t_turn))
    # ⚠ 台词**要说到超过配额**才能测出这条：第一版只写了两句台词，而
    #   `PERIOD_TURN['夜深了']` 的配额正好是 **2** ⇒ 两句怎么数都 ≤ 2，
    #   把统计口径从"只数叙述"换成"连台词一起数"也照样绿（反例法 M26 抓出来的）。
    #   ⇒ 现在写**三句**台词：只有"只数叙述"这一种口径才会是 0。
    # [EN] ⚠ The dialogue must **exceed the quota** for this to be testable: the first version had
    # [EN] two lines while `PERIOD_TURN['夜深了']` is **2**, so both counting modes stayed under it
    # [EN] and switching to "count dialogue too" still passed (caught by mutation M26). Three lines
    # [EN] now: only "narration only" yields 0.
    _dlg_time = '她说：“夜深了。”他说：“夜深了。”她又说：“夜深了。”'
    ok('J5 ★★★ 成对：**台词里的时间词不算**（人物嘴上说"夜深了"是台词，'
       '不是叙述在盖章 —— 不分台词会把"角色在复述时间"误判成"叙述乱了"）',
       time_anchor_issues(_dlg_time) == [],
       repr(time_anchor_issues(_dlg_time)))
    # ⚠ 判"提示词里有没有"要读**生产侧那份**（`_transcribe_once` 的源码），
    #   不是本文件的 `s`（那是上一组的局部变量，第一版直接 NameError）。
    # [EN] Judge the **production** source (`_transcribe_once`), not a local `s` from the previous
    # [EN] group (the first version raised NameError).
    import inspect as _ins
    from crew import agents as _A2
    _tp = _ins.getsource(_A2.Novelist._transcribe_once)
    ok('J6 ★★★ 提示词里**明确禁止**叙述自己编时间，并指认幕头是唯一真相',
       '时间只准从幕头来' in _tp and '不许自己编' in _tp, '')
    # ★★★ **钟点当句首**（第六轮真跑暴露的新形态）：只写"按幕头写时间"，
    #   产出变成「二十三点三十分…二十三点三十五分…」五处钟点 —— 像值班记录。
    #   用户要的是"清晰的时间轴"，不是"每段盖一个章"。
    # [EN] **Clock time as a sentence head** (the new shape round six exposed): told only "follow
    # [EN] the act header for time", the output became five clock heads -- a duty log. The user
    # [EN] wanted a clear timeline, not a stamp on every paragraph.
    from crew.prose_flow import clock_stamps, time_note as _tn
    _bad = ('二十三点三十分，叶子送酒进来。二十三点三十五分，她又折回。'
            '二十三点三十六分，驹子提壶。')
    ok('J9 ★★★ "钟点当句首"被抓出来（这是"按幕头写时间"的**矫枉过正**形态）',
       clock_stamps(_bad) >= 3, f'{clock_stamps(_bad)} 处')
    ok('J10 ★★★ 成对：**时间藏在事里**不算（"更鼓敲过三下，廊下的灯灭了"是好的写法）',
       clock_stamps('更鼓敲过三下，廊下的灯已经灭了。雪停了很久。') == 0, '')
    ok('J11 ★★★ 只有钟点太多、没有别的毛病时，`time_note` **也要报**'
       '（第一版把"空就返回"写在前面 ⇒ 这种稿子永远报不出来，'
       '而它正是第六轮真跑的实际形态）',
       _tn(_bad) != '' and '钟点' in _tn(_bad), _tn(_bad))
    ok('J12 ★★ 提示词里给了**上限两处**和正反例（钟点当句首 ❌ / 时间藏在事里 ✅）',
       '全篇最多两处' in _tp and '像值班记录' in _tp, '')

    # ── 反应标签配额（第十一轮，用户点名的第二条：「复读机」）──
    # 用户原话：「"慢一拍""没听清""答非所问"出现了七次以上…第一次用是惊艳，
    # 第二次是强化，**第三次开始是重复，第四次之后是读者的疲劳**。」
    # [EN] Reaction-tag quota. The user: "first use is striking, the second reinforces, **the third
    # [EN] is repetition, and from the fourth it is fatigue**."
    from crew.prose_flow import reaction_tag_issues as _RT, reaction_tag_note as _RTN
    _rt_bad = '他把火箸搁下，慢一拍。她又问，他慢一拍。第三次，他还是慢一拍。'
    ok('K1 ★★★ **同一个反应手法用超两次**被抓出来'
       '（"慢一拍"这类现成写法，第三次起就是疲劳）',
       any(b['what'] == '慢一拍' for b in _RT(_rt_bad)), _RTN(_rt_bad))
    ok('K2 ★★★ 成对：**只出现两次不算**（第二次是强化，那是对的）',
       _RT('他慢一拍。后来又一次，他慢一拍。') == [],
       repr(_RT('他慢一拍。后来又一次，他慢一拍。')))
    ok('K3 ★★★ 成对：**台词里的"我没听清"不算**'
       '（那是人物在说话，不是作家在用标签 —— 算进去会把正常对白判成复读）',
       _RT('他说：“我没听清。”她说：“我也没听清。”他又说：“我没听清。”') == [],
       repr(_RT('他说：“我没听清。”她说：“我也没听清。”他又说：“我没听清。”')))
    ok('K4 ★★ 同一个手法只报一次（「慢一拍」包含「慢半拍」，不许报两条）',
       len([b for b in _RT('慢一拍慢半拍慢一拍慢半拍慢一拍') if '慢' in b['what']]) == 1,
       _RTN('慢一拍慢半拍慢一拍慢半拍慢一拍'))
    ok('K5 ★★★ 提示词里给了**上限两次**和**四条替代写法**'
       '（只说"别重复"模型会换成一个更空的形容词）',
       '整章最多两次' in _tp and '把火箸搁在钵沿上' in _tp
       and '答一个跟刚才那句没关系的问题' in _tp, '')
    ok('K6 ★★ 而且说清了**最坏的一种**（同一个人连着几段都"慢一拍"）',
       '连着几段都"慢一拍"' in _tp or '同一个人连着几段' in _tp, '')

    # ── 视角要稳（同一条，用户点名的第三条）──
    # 用户原话：「文本在多个视角之间跳跃，没有一个稳定的锚点…不知道该跟谁共情。」
    # [EN] Stable POV. The user: "the text jumps between viewpoints with no stable anchor".
    ok('K7 ★★★ 提示词要求**一章只跟一个人**，并说清"他听不清的读者也跟着不知道"'
       '（那正是"没听清"该起的作用，而不是靠旁白替他讲）',
       '一章**只跟一个人**' in _tp and '读者也跟着不知道' in _tp, '')
    ok('K8 ★★★ 明写**别人的心里话一个字都不许写**', '别人的心里话**一个字都不许写**' in _tp, '')
    ok('K9 ★★★ 明写"换视角只能**换段**、不许**换句**"'
       '（同一段里从"他觉着"跳到"她觉得"，读者会当场出戏）',
       '换段' in _tp and '不许**换句**' in _tp, '')

    ok('J7 ★★★ 提示词里要求**外部动静必须有人接**'
       '（用户的第三条：「"酒洒了"…之后角色并没有因此产生新的情绪或行动」）',
       '外部动静必须有人接' in _tp and '被打断的那半句' in _tp, '')
    ok('J8 ★★★ 提示词里要求**配角不是跑腿的**'
       '（用户的第四条：「叶子几乎只在送东西和提醒…更像一个 NPC」）',
       # ⚠ 判"给了他具体出路"而不是复述某个字面短语：文案里是
       #   `**至少有一处是"他自己的"**`，写死 '是他自己的' 会漏（中间有引号）。
       #   按纪律：只写方向不给出路 = 可选项，所以要判"多余的举动"这种**做法**。
       # [EN] Judge "a concrete way out was given", not a literal phrase: the text is
       # [EN] `**至少有一处是"他自己的"**`, so a hardcoded '是他自己的' misses (quotes inside).
       '配角不是跑腿的' in _tp and '多余的举动' in _tp, '')

    ok('G4 ★★ 边界：**两句**短句不算清单（真人本来就常这么写）',
       not list_like_spans('他停了停。她没有回头。'), '')

    # ★★★ **一句一段**（2026-10-19 第四次真跑）：连续几行每行一句，
    #   读起来和旧版一样碎，只是换行把它包装成了诗。
    #   提示词治不了排版，`list_like_spans` 也抓不到（每行 1 句 < RUN_MIN）⇒ 纯代码合并。
    # [EN] One-sentence-per-line (fourth run): prompts cannot fix layout and `list_like_spans`
    # [EN] cannot see it (1 sentence per line < RUN_MIN) => merge with pure code.
    from crew.prose_flow import merge_one_line_paragraphs
    stacked = ('驹子急切催他喝酒。\n岛村把火钵挪膝前。火光照纸门。\n'
               '自己在这儿倒叫她不好进来。\n木廊脚步三下到门边停住。\n'
               '岛村手收回。指尖停膝上。\n门外叶子声音里，那句话他没接住。')
    merged = merge_one_line_paragraphs(stacked)
    # ★★★ **长句硬闸**（第六轮）：同一组提示词连跑四次，长句 21%→60%→47%→85.7%，
    #   而提示词里"一个句号不超过四十个字"每条都写着 ⇒ 必须解析层切。
    # [EN] **Long-sentence hard gate**: four runs of identical prompts gave 21/60/47/85.7% while
    # [EN] the prompt said "no more than forty characters per full stop" every time.
    from crew.prose_flow import split_long_sentences as _SPLIT
    _long1 = ('他伸手过去按在窗框上看了很久外头的雪，' * 3 + '然后回过头来看着她不说话。')
    _out1 = _SPLIT(_long1)
    # ⚠ 第一版这条里写了 `max((x[2] for x in [y for y in []]), default=0) == 0 or ...`
    #   —— 左边恒为 True ⇒ **判据永远不会红**（我自己写出来的假绿）。
    #   只判"最长句变短了"这一件事。
    # [EN] The first version had a恒True left operand => the criterion could never go red (a false
    # [EN] green of my own making). Judge only "the longest sentence got shorter".
    def _maxsent(x: str) -> int:
        from crew.prose_flow import _sentences as _S2
        return max([b[2] for b in _S2(x)] or [0])

    ok('G8 ★★★ 一个 60+ 字的长句被**切开**（最长句必须变短 —— '
       '四次真跑长句占比 85.7% vs 真人 14.8%）',
       _maxsent(_out1) < _maxsent(_long1),
       f'最长句 {_maxsent(_long1)} → {_maxsent(_out1)} 字')
    ok('G9 ★★★ **一个字都不动**（只把逗号换成句号，字数完全一样）',
       len(_out1.replace('\n', '')) == len(_long1.replace('\n', '')), '')
    # ⚠ 夹具必须让**台词本身**超过门槛：第一版用的是"“我没听清。”"（5 个字），
    #   遮罩失效也切不到它 ⇒ 两个条件恒真、判据恒绿。现在用一段 45 字以上的台词。
    # [EN] The fixture must make the **dialogue itself** exceed the threshold: the first version
    # [EN] used a 5-char line, so even a broken mask could not cut it and both conditions were
    # [EN] vacuously true. Now a 45+ char line.
    _dlg = ('他说：“这件事你要是真的想知道，我就从头说一遍，'
            '从三年前那个下雪的夜里说起，一直说到今天早上。”')
    _dlg_out = _SPLIT(_dlg)
    ok('G10 ★★★ **台词不许切**（人物怎么断句是他自己的事，切了就是作者替他说话 —— '
       '夹具的台词本身就有 50 字，遮罩一失效就会挨刀）',
       '“这件事你要是真的想知道，我就从头说一遍，从三年前那个下雪的夜里说起，'
       '一直说到今天早上。”' in _dlg_out,
       repr(_dlg_out[:40]))
    # ⚠ 夹具要"切一刀就会留下极短尾巴"：只有这种句子才能证明 `min_part` 真在挡。
    #   第一版用的是三句短句 —— 本来就不超门槛，切不切都一样（变异没改行为）。
    # [EN] The fixture must be one whose single cut would leave a very short tail -- only that
    # [EN] proves `min_part` is doing work. The first version used three short sentences that never
    # [EN] exceeded the threshold anyway (so the mutation changed nothing).
    # ⚠ 夹具必须**超过 hard_max**（45）：第一版 35 字，连切句分支都没进，
    #   去掉 `min_part` 也不会有任何变化 ⇒ 变异无效。现在 46 字，切一刀会留一个 2 字的尾巴。
    # [EN] The fixture must **exceed hard_max**: the first version was 35 chars and never entered
    # [EN] the split branch at all, so removing `min_part` changed nothing. Now 46 chars, where one
    # [EN] cut would leave a 2-character tail.
    _tail = ('他站起来走到窗边把窗子推开看了看外头的雪又关上了窗子'
             '然后回到桌前坐下把茶碗端起来喝了一口水，嗯。')
    ok('G11 ★★ 成对：**切一刀会留下极短尾巴时宁可不切**（切碎是另一头的老毛病，'
       '`min_part` 挡着）',
       _SPLIT(_tail) == _tail, repr(_SPLIT(_tail)[-20:]))
    # ★★★ **"该不该切"按主语切换判，不按长度判**（第七轮定案）
    #   两段等长的真句子，长度分不开：43 字 2 主语（一条动作链，好）vs
    #   40 字 3 主语（串了四件事，坏）。用户说的"一句交代好几件事"就是后者。
    # [EN] Judge "should this be cut" by **subject switches**, not length: a 43-char span with two
    # [EN] subjects is one action chain; a 40-char span with three packs four things in.
    _good_long = ('他伸手过去，指尖碰到的那片皮肤是凉的，她没动，'
                  '屋里静得能听见灯芯炸响，雪把两个人的呼吸都吸掉了。')
    _bad_long = ('驹子手指拨了拨火箸，火苗跳一下，廊板响，'
                 '叶子端着结薄霜的壶回来，弯身放下，她退去没碰出声响。')
    _N3 = ('驹子', '岛村', '叶子')
    ok('G13 ★★★ **一句长长的描写**（43 字、只有 2 个主语）**不许被切** —— '
       '长是对的，那是动作链',
       _SPLIT(_good_long, names=_N3) == _good_long,
       repr(_SPLIT(_good_long, names=_N3)[:40]))
    ok('G14 ★★★ **一句串了四件事**（40 字、主语换了 3 次）**必须被切**'
       '（用户原话："每一句都恨不得交代一个事情"—— 可数形状就是主语切换）',
       _SPLIT(_bad_long, names=_N3) != _bad_long,
       f'切成 {len(_SPLIT(_bad_long, names=_N3))} 字（原 {len(_bad_long)}）')
    ok('G15 ★★ 而且切完**每句都有主语**（切点落在主语前，不产生"弯身放下："这种碎片）',
       not any(sg.strip().startswith(('弯身', '伸手', '放下', '拿')) 
               for sg in _SPLIT(_bad_long, names=_N3).replace('\n', '').split('。') if sg.strip()),
       repr(_SPLIT(_bad_long, names=_N3)))

    # ⚠ **不能用"出现几次"判**：第一版判 `count(...) >= 2`，而变异把**早退分支**那一处
    #   删掉之后仍然剩 2 处（前置 + 末尾）⇒ 判据照绿（反例法 M18 抓出来的）。
    #   计数类判据不要用来判"某一处有没有"——要判**那个位置**。
    # [EN] ⚠ Cannot judge by "how many times it appears": the first version required
    # [EN] `count(...) >= 2`, and deleting the **early-return** occurrence still left two
    # [EN] (up front + at the end) => the criterion stayed green (mutation M18 caught this).
    # [EN] Never use a count to answer "is it in *that* spot".
    _fsp = _ins.getsource(_A2.Novelist._fix_flat_paragraphs)
    _early = _fsp.split('if not spans:', 1)[-1].split('_LOG.info', 1)[0] \
        if 'if not spans:' in _fsp else ''
    ok('G12 ★★★ 接在**生产路径**上，而且**早退分支内部**也切'
       '（第一版只在"有平铺段"的分支末尾切 ⇒ "平铺 0 段但句句 60 字"的稿子一个字都不切，'
       '而 `snow_time2` 正是这种）',
       'split_long_sentences' in _early and 'split_long_sentences' in _fsp,
       f'早退块 {"有" if "split_long_sentences" in _early else "**没有**"} 切句')

    ok('G5 ★★★ "一句一段"的连续短行被**并成一段**（六行 → 一行）',
       len(merged.strip().split('\n')) == 1, repr(merged[:40]))
    ok('G6 ★★★ 而且**一个字都不动**（只改换行）—— 这不是改写，不该碰内容',
       merged.replace('\n', '') == stacked.replace('\n', ''), '')
    # ★★★ **空行算"连续"**（第八轮真跑）：模型会把整篇写成"一句一段 + 每段一个空行"，
    #   而第一版遇空行就断 ⇒ 攒到 1 行就 flush ⇒ **一行都没合并**（44 行正文全没动）。
    # [EN] **Blank lines count as "continuous"** (round eight): the model writes one sentence per
    # [EN] line **with a blank line between each**, and the first version flushed on every blank
    # [EN] line, so it merged **nothing** (44 body lines untouched).
    _spread = '他推开门。\n\n她抬起头。\n\n屋里很静。\n\n他把伞靠在墙边。\n\n她没说话。'
    _spread_out = merge_one_line_paragraphs(_spread)
    # ★★★ **末尾必须再合并一次**（第十二轮真跑抓出来的）
    # `snow_v11` 开头 merge 过，产物里却仍有一整段"一句一行"（8 行）：
    # 根因是**重写平铺段那一步返回的就是一句一行**，而之后没人合并。
    # [EN] **Merge once more at the end** (caught by a real run in round twelve): `snow_v11` was
    # [EN] merged at the start yet still had an 8-line one-sentence-per-paragraph block. The
    # [EN] flat-paragraph rewrite returns one sentence per line and nothing merged afterwards.
    _fix_src = _ins.getsource(_A2.Novelist._fix_flat_paragraphs)
    ok('G19 ★★★ `merge_one_line_paragraphs` **在 `_fix_flat_paragraphs` 里被调用两次**'
       '（开头一次、末尾一次）—— 只调一次时，**重写出来的"一句一行"没人收**',
       _fix_src.count('merge_one_line_paragraphs') >= 2,
       f'{_fix_src.count("merge_one_line_paragraphs")} 次')
    ok('G20 ★★★ 末尾那次排在**切句之后**（切句只加句号不改行，两者互不干扰）',
       _fix_src.rfind('merge_one_line_paragraphs') > _fix_src.rfind('split_long_sentences'),
       '末尾顺序')

    ok('G17 ★★★ **空行不打断"一句一段"的连续判断**（六行夹着空行 ⇒ 仍要并成一段）',
       len([x for x in _spread_out.split('\n') if x.strip()]) == 1,
       repr(_spread_out[:50]))
    ok('G18 ★★★ 但**一段不能并太长**（第八轮实测：不加长度上限时 44 个短行并成 2 段，'
       '比原来更难读）',
       # ⚠ 夹具必须**明显超过上限**：第一版只有 12×17=204 字 < 260，
       #   去掉上限也超不过 ⇒ 变异无效、判据恒绿。现在 24 行 ≈ 408 字。
       # [EN] The fixture must clearly exceed the cap: the first version was 204 chars < 260, so
       # [EN] removing the cap changed nothing. Now 24 lines ~ 408 chars.
       all(len(x) <= 260 for x in merge_one_line_paragraphs(
           '\n\n'.join(['他把窗子推开看了很久外头的雪又关上。'] * 24)).split('\n') if x.strip()),
       '')
    ok('G16 ★★★ 成对：**不足四行的正常排版原样保留，连空行一起**'
       '（第一版把空行吃了 ⇒ 三句一段被压成三行挤在一起，G7 抓到的就是它）',
       merge_one_line_paragraphs('甲句。\n\n乙句。\n\n丙句。') == '甲句。\n\n乙句。\n\n丙句。',
       repr(merge_one_line_paragraphs('甲句。\n\n乙句。\n\n丙句。')))

    ok('G7 ★★★ 成对：**正常的段落不许动**（真人样本里那些一两句一段是有意的节奏）',
       merge_one_line_paragraphs('他推开门。\n\n她抬起头。\n\n屋里很静。') == '他推开门。\n\n她抬起头。\n\n屋里很静。',
       '')


# ══════════════════════════════════════════════════════════════
#  H  生产路径：**自检重写**真的接上了（不是只有工具函数）
# ══════════════════════════════════════════════════════════════
_FLAT = ('他伸手，指尖碰了碰她耳后的皮肤，凉的。声音这么轻，都给雪吸掉了。'
         '走廊上是谁？门外没有脚步声。')
# ★★★ 2026-10-20：**"太碎"不再是待修项**。
#   分开量过的硬证据：真人 18 章「太平」（整段没有一句 ≥25 字）中位 **3**、最大 **9**，
#   而真跑 v21 是 **0** —— 真人比真跑"平"得多，这一类不是病。
#   拿它去重写就是改本来没问题的段落，实测每改一轮反而更差（2 → 3 → 6）。
#   ⇒ H1/H2 的夹具换成**"太长"**（段内长句过半或冒超长句），那一路真人有天花板 1。
# [EN] "Too choppy" is no longer repaired: across 18 human chapters it runs median 3 /
# [EN] max 9 while the real run had 0. The fixture now exercises **"too long"**, which
# [EN] human prose caps at 1.
_LONG = ('他心里明白这时候说什么都不合适，屋里只剩下炭火偶尔炸开一声的动静，'
         '窗纸外面的雪把整条街的脚步声都吞掉了，连远处更鼓的尾音也听不真切。'
         '驹子把手从袖子里抽出来又慢慢放回去，指节在膝上按了一下才松开，'
         '像是要把刚才那句话按回心里去。叶子在门边站着没有动，'
         '她的影子长长地铺在榻榻米上，被灯芯一跳一跳地晃出许多细碎的边。')
_GOOD = ('他伸手过去，指尖碰到的那片皮肤是凉的，她没动，'
         '屋里静得能听见灯芯炸响，雪把两个人的呼吸都吸掉了。')

#:  的好重写：长度与它相当（过长度闸 0.6–2.2 倍），句子有长有短。
_LONG_OK = ('他心里清楚这时候说什么都不合适，屋里只剩炭火偶尔炸开一声。'
            '窗纸外面的雪把整条街的脚步声都吞掉了，连更鼓的尾音也听不真切。'
            '驹子把手从袖子里抽出来，又慢慢放回去。'
            '指节在膝上按了一下才松开，像是要把刚才那句话按回心里去。'
            '叶子在门边站着没有动，影子长长地铺在榻榻米上，'
            '被灯芯一跳一跳地晃出许多细碎的边。')


def _run_fix(text: str, *, limit: int, reply=None, ok=True):
    """调**真的** `_fix_flat_paragraphs`，把 `ask` 换成假的。返回 (结果, 收到的 prompt 列表)。"""
    from crew import agents as A
    real = A.ask
    seen: list[str] = []

    async def fake_ask(tier, messages, **kw):
        seen.append(str((messages or [{}])[-1].get('content') or ''))

        class R:
            pass
        r = R()
        r.ok = ok
        r.value = (reply if reply is not None else _LONG_OK)
        r.notes = []
        return r

    A.ask = fake_ask
    old = CFG.s('PROSE_FLOW_FIX')
    try:
        CFG.set('PROSE_FLOW_FIX', str(limit))
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'
        n._last_why = ''
        out = asyncio.run(A.Novelist._fix_flat_paragraphs(n, text))
    finally:
        A.ask = real
        CFG.set('PROSE_FLOW_FIX', old)
    return out, seen


def group_h() -> None:
    from crew import prose_flow as PF
    out, seen = _run_fix(_LONG, limit=2)
    ok('H1 ★★★ 平铺段**真的**被挑出来送了一次重写（工具函数接上了生产路径，'
       '不是只有 `prose_flow.py` 躺在库里没人用）',
       len(seen) == 1 and '重写这一段' in seen[0], f'{len(seen)} 次调用')
    # ⚠ 不能再判"整段原样相等"：`_fix_flat_paragraphs` 末尾有**切句**那一道
    #   （`split_long_sentences`），它可能把重写结果里的长句切开 ⇒ 整段自然不相等，
    #   而"重写确实进了正文"这件事仍然成立。
    #   改判：**重写结果里的每一句都还在**（切句只加句号，不删字）。
    # [EN] Cannot compare the whole paragraph any more: `_fix_flat_paragraphs` ends with the
    # [EN] sentence-splitter, which may cut long sentences inside the rewrite => the paragraph
    # [EN] differs while "the rewrite did land" still holds. Judge instead: **every sentence of the
    # [EN] rewrite is still present** (splitting only adds full stops, it deletes nothing).
    # ⚠ 比**汉字序列**，不比标点：切句只把逗号换成句号，字的顺序一个不动。
    #   第一版按"。".split 比句子 ⇒ 整段被切成 4 句后一条都对不上（假红）。
    # [EN] Compare the **CJK character sequence**, not punctuation: splitting only turns commas
    # [EN] into full stops and leaves the character order intact. The first version compared
    # [EN] sentences, so once the paragraph was cut into four, nothing matched (false red).
    import re as _re2

    def _zh_only(x: str) -> str:
        return ''.join(_re2.findall(r'[\u4e00-\u9fff]', x))

    ok('H2 ★★★ 重写结果**真的替换进了正文**（不是算出来又丢掉；'
       '末尾的切句只加句号，汉字一个不少、顺序不变）',
       _zh_only(out) == _zh_only(_LONG_OK),
       f'{len(_zh_only(out))} vs {len(_zh_only(_LONG_OK))} 字')
    ok('H3 ★★★ 成对：`PROSE_FLOW_FIX=0` 时**一次都不调**（回到"只靠提示词"的老路，'
       '证明它是个真旋钮而不是装饰）',
       _run_fix(_LONG, limit=0)[1] == [], '')
    ok('H4 ★★★ **好文字不动**：整段铺开了的文本不触发重写（否则每篇都要多花几次调用）',
       _run_fix(_GOOD, limit=2)[1] == [], '')

    # ── 失败一律保住原文（这一步是加分项，不许把整理稿搞砸）──
    out_fail, _ = _run_fix(_LONG, limit=2, ok=False)
    ok('H5 ★★★ 重写调用**失败**时原样返回（不许交出空章）',
       _zh_only(out_fail) == _zh_only(_LONG), out_fail[:40])
    out_short, _ = _run_fix(_LONG, limit=2, reply='重写如下：略。')
    ok('H6 ★★★ 重写结果**长度异常**时保住原文（防"交回一句（重写如下）"或'
       '把三段戏压成一句）',
       _zh_only(out_short) == _zh_only(_LONG), out_short[:40])
    out_long, _ = _run_fix(_LONG, limit=2, reply='啊' * (len(_LONG) * 5))
    ok('H7 ★★ 成对：反过来**过长**也保住原文（模型注水同样不可用）',
       _zh_only(out_long) == _zh_only(_LONG), f'{len(out_long)} 字')
    # ★★★ H8（2026-10-20 实测补的闸）：**重写不许把台词并掉**。
    #   R45/R46/R47 都有这道闸，唯独这一步漏了 —— 代价实测：
    #   `snow_v21` 跑完，两句真台词被并进叙述里没了（台词 26 → 23）。
    #   ⚠ 判的是**这一段**的台词条数：判全篇会让后面的段落替前面的顶包。
    # [EN] The rewrite may not absorb dialogue. Every other fix step had this guard; this
    # [EN] one did not, and it cost two real lines on snow_v21. Judged per paragraph.
    # ⚠ 夹具必须**真的被判成"太长"**（≥3 个叙述句 + 有长句），否则根本不会触发重写，
    #   H8 就成了"因为没修所以通过"的假绿（第一版正是这样，M84 抓不到）。
    # [EN] The fixture must actually trip the length check, or no rewrite happens and the
    # [EN] check passes for the wrong reason (M84 survived, measured).
    # ⚠ 夹具必须**过了切句那一步还太长** —— `_fix_flat_paragraphs` 一进门就先把
    #   >32 字的长句按逗号切开，切完 `long_span_issues` 就判不中了，
    #   于是**重写根本没被调用**（实测：调用 0 次），H8 变成"因为没修所以通过"。
    #   ⇒ 用几句 26–32 字、**不含逗号**（切不动）的句子，靠"长句过半"命中。
    # [EN] The fixture must still be "too long" **after** the splitter runs: it cuts
    # [EN] >32-char sentences at commas, so the rewrite never fired (measured: 0 calls)
    # [EN] and H8 passed for the wrong reason. Use 26-32 char comma-free sentences.
    _with_q = ('他心里清楚这时候说什么都不合适所以一直没有开口的意思。'
               '窗纸外面的雪把整条街的脚步声都吞掉了连更鼓的尾音也不真切。'
               '驹子把手从袖子里抽出来又放回去指节在膝上按了一下才松开。'
               '她低声问：“炭还旺么。”')
    out_lost, _ = _run_fix(_with_q, limit=2,
                           reply='他心里清楚这时候说什么都不合适所以一直没有开口的意思。'
                                 '窗纸外面的雪把整条街的脚步声都吞掉了连更鼓的尾音也不真切。'
                                 '驹子把手从袖子里抽出来又放回去指节在膝上按了一下才松开，'
                                 '低声问炭还旺么。')
    ok('H8 ★★★ **重写不许把台词并掉**（并进叙述就没人替角色说话了 —— '
       '实测在 v21 上丢过两句真台词，26 → 23）',
       _zh_only(out_lost) == _zh_only(_with_q), '台词被并 ⇒ 保留原文')
    # ★★★ H9（2026-10-20 实测补的第 N+1 道闸）：**重写不许引入"感知不成立"**。
    #   来源：多轮计数表报出 `感知自洽 0 → 1` —— 为了把长句拆短，
    #   模型写进了"隔着纸门看清睫毛上的雪"这种句子。
    #   这一步只该改句子长短，没有资格改动"谁能看见什么"。
    #   ⚠ 判的是**这一段**多了几处（delta），不是"有没有"：
    #     原文本来就 1 处的段落，重写后还是 1 处，不该拦。
    # [EN] The rewrite may not introduce new perceptual impossibilities; judged as delta.
    _bad_percept = ('他心里明白这时候说什么都不合适，屋里只剩下炭火偶尔炸开一声的动静，'
                    '窗纸外面的雪把整条街的脚步声都吞掉了。'
                    '叶子在门边站着没有动，影子长长地铺在榻榻米上。'
                    '更鼓从巷子那头慢慢过来，一声比一声轻。')
    out_per, _ = _run_fix(
        _bad_percept, limit=2,
        reply='他心里明白这时候说什么都不合适，屋里只剩炭火偶尔炸开一声。'
              '他隔着纸门看清了她睫毛上沾着的那点雪。'
              '叶子在门边站着没有动。更鼓从巷子那头慢慢过来，一声比一声轻。')
    ok('H9 ★★★ **重写不许引入"感知不成立"**（为了拆长句写出'
       '「隔着纸门看清睫毛上的雪」—— 这一步只该改句子长短，没资格改谁能看见什么）',
       _zh_only(out_per) == _zh_only(_bad_percept),
       f'感知 {len(PF.percept_issues(_bad_percept))} → '
       f'{len(PF.percept_issues(out_per))}')
    # ⚠ 成对：**原文本来就 1 处、重写后还是 1 处 ⇒ 不许拦**。
    #   判"有没有"会把这类段落永久挡住（它本来就有病，forever 回原文）；
    #   必须判 **delta**。这里造一个"原文 1 处、重写后也 1 处"的例子。
    # [EN] Paired case: if the paragraph already had 1 issue and the rewrite still has 1,
    # [EN] it must NOT be rejected -- judged as a delta, or such paragraphs are blocked
    # [EN] forever (they were already bad, so "has any" would always reject).
    # ⚠ 夹具必须**真的被判成"太长"**，否则根本不触发重写 —— H9b 会变成
    #   "因为没修所以通过"的假绿（第一版就是这样，量出 long_span=0）。
    # [EN] The fixture must actually trip the length check, or no rewrite runs and the
    # [EN] paired case passes for the wrong reason (first version measured long_span=0).
    _one_each = ('她站在门外，隔着纸门看见他睫毛上沾着一点雪。'
                 '他一动不动地坐着，屋里的炭火偶尔炸开一声，'
                 '窗纸外面的雪把整条街的脚步声都吞掉了，连远处更鼓的尾音也听不真切。'
                 '更鼓从巷子那头慢慢过来。')
    out_same, _ = _run_fix(
        _one_each, limit=2,
        reply='她站在门外，隔着纸门看见他睫毛上的那点雪。'
              '他一动不动地坐着。屋里的炭火偶尔炸开一声。'
              '窗纸外面的雪把整条街的脚步声都吞掉了。'
              '更鼓从巷子那头慢慢过来。')
    _b1, _a1 = len(PF.percept_issues(_one_each)), len(PF.percept_issues(out_same))
    ok('H9b ★★ 成对：原文本来 1 处、重写后还是 1 处 ⇒ **照收**'
       '（按 delta 判，不按"有没有"判 —— 否则这类段落永远改不动）',
       _b1 == 1 and _a1 == 1
       and _zh_only(out_same) != _zh_only(_one_each),
       f'原文 {_b1} 处 / 重写后 {_a1} 处')


def group_i() -> None:
    """I 组：**悬空第三人称** —— 引语里的"她/他"落不到地上（2026-10-19 第十一轮）。

    用户点名"最致命"的一条：`驹子忽然安静，说"她恨我"，又笑着说"算了"` ——
    那句话在正文里**全文找不到"她"是谁**，情感分量很重却毫无承接。
    它在六次真跑里出现了五次。

    两道闸，都必须各自可判：
      · 导演事件里不许有引语（`director/engine._inject_event`）；
      · 整理材料的行级剔除（`crew/agents.Novelist._drop_dangling_lines`）。
    """
    from crew import prose_flow as PF
    _CAST = ('岛村', '驹子', '叶子')
    _BAD = '【外部刺激】驹子望见火钵边新置的酒壶，忽然安静，轻声说\'她恨我\'，又笑说\'算了\'。'
    _BAD2 = '【外部刺激】驹子忽然安静，说“她恨我”，又笑着说“算了”。'

    ok('I1 ★★★ 引号配对器认得出**开闭同形**的 ASCII 引号'
       '（剧本体/LLM 返回里到处都是 `说\'她恨我\'，又笑\'算了\'`，按方向配会拆坏）',
       len(PF._quoted_spans('说\'她恨我\'，又笑\'算了\'')) == 2,
       repr(PF._quoted_spans('说\'她恨我\'，又笑\'算了\'')))
    ok('I2 ★★★ `其他` 与 `他们/她们` 不算指代（不是每一种"他"都指向一个人）',
       PF._third_persons('其他的人') == [] and PF._third_persons('他们来了') == [],
       repr(PF._third_persons('其他的人他们来了')))
    ok('I3 ★★★ 行为判：同一行里引语之前除说话人外没名字 ⇒ 判悬空（真跑五次命中的那一句）',
       bool(PF.dangling_reference(_BAD, names=_CAST))
       and PF.dangling_reference(_BAD, names=_CAST)[0]['pron'] == '她',
       PF.dangling_reference_note(_BAD, names=_CAST))
    ok('I4 ★★★ 行为判：引语之前出现过别人名字 ⇒ 不判'
       '（"岛村看了眼叶子，低声：\'她恨我\'"是可解的）',
       PF.dangling_reference('岛村看了眼叶子，低声："她恨我。"', names=_CAST) == [],
       '')
    ok('I5 ★★★ 行为判：`speaker` 不传时按**行内最早出现的名字**推断'
       '（中文叙述主语在前；不推断就永远抓不到事件行）',
       PF.dangling_reference(_BAD, names=_CAST) != [],
       '')
    ok('I6 ★★ 成对：**没有引号的事件不判**'
       '（"驹子忽然安静，说她恨我"是叙述，不是替角色写台词）',
       PF.dangling_reference('【外部刺激】驹子忽然安静，说她恨我，又笑说算了。',
                             names=_CAST) == [],
       '')
    ok('I7 ★★★ 成对：**没有在场名单就不判**（不猜 —— 猜出来的名单'
       '会把判据变成"看运气"）',
       PF.dangling_reference(_BAD) != []        # 无 names：靠推断也能判（见 I5）
       and _drop_lines(_BAD, []) == _BAD,        # 材料闸：无名单一个字节不动
       '')
    ok('I8 ★★★ 落单的引号忽略（宁少判，也不把半句话当引语）',
       PF._quoted_spans('他说了一半“就没') == [], repr(PF._quoted_spans('他说了一半“就没')))
    ok('I9 ★★★ 材料闸真的会剔行，且只剔那一行'
       '（别的行一个字节不动 —— 不是"整篇重来"）',
       _drop_lines('驹子（向岛村）：手倒生得白。\n' + _BAD2 + '\n岛村（向驹子）：雪停了。',
                   list(_CAST)) == '驹子（向岛村）：手倒生得白。\n岛村（向驹子）：雪停了。',
       _drop_lines('驹子（向岛村）：手倒生得白。\n' + _BAD2 + '\n岛村（向驹子）：雪停了。',
                   list(_CAST)))
    ok('I10 ★★ 材料闸：**没有引号的事件行不动**（不误伤正常事件）',
       _drop_lines('【外部刺激】门被推开，风灌进来。', list(_CAST)) == '【外部刺激】门被推开，风灌进来。',
       '')
    ok('I11 ★★★ AST：`_drop_dangling_lines` 真的走 `prose_flow.dangling_reference`'
       '（不许在剧组里再写一个判据 —— "同一件事两处实现"是万恶之源）',
       _calls_dangling(), '')
    ok('I12 ★★★ AST：事件闸接在 `_inject_event` 上，判的就是**事件描述本身**'
       '（`has_quoted_speech(event.description)` —— 判空串等于闸门不存在）',
       _event_gate_wired(), '')
    ok('I13 ★★★ AST：闸里**真的有一条 return None**（重写后仍带引语就放弃这一拍，'
       '不是"记一笔就放行"）',
       _event_gate_rejects(), '')
    ok('I14 ★★★ 成对：提示词里也写了"一个引号都不要出现"'
       '（硬闸 + 提示词成对；只有闸没有话，模型不知道为什么被拦）',
       '一个引号都不要出现' in _event_src(), '')


# ══════════════════════════════════════════════════════════════
#  J  进出场断链（2026-10-19 第十二轮，用户报的第四条）
# [EN] J  Presence-chain breaks (round twelve; the user's fourth complaint)
# ══════════════════════════════════════════════════════════════
def _mat(*entries):
    """用**真构造器 + 真渲染器**造材料行（夹具不许手搓 `名字：…` 那种格式）。

    ⚠ 为什么必须走 `script_render.one_line`：材料行的形状由它定。
      手写字符串当夹具，哪天那边改了格式，判据还在绿。
    [EN] Build material lines with the **real constructors and the real
    [EN] renderer** -- hand-writing `name: …` would let the criterion stay green
    [EN] after the format changes.
    """
    from display import script as S
    from display import script_render as SR
    return [SR.one_line(e) for e in entries if SR.one_line(e)]


def _note_via(body: str, names) -> str:
    """调生产侧的那句指令生成器（不实例化整个剧组）。"""
    from crew.agents import Novelist

    class _C:
        people = list(names)

    return Novelist._presence_break_note(None, body, _C())


def group_j() -> None:
    """J 组：**标了退场的人又动了，中间没有标进场**（进出场断链）。

    用户点名的第四条：「叶子行动线逻辑矛盾：送酒→退下→**无回归标记**又出现
    →拿凉壶→送回温好的酒」。

    ★★★ 动手之前先量过，两条更"自然"的路都被实测堵死（所以判据只能挂在
    **结构化标记**上，而标记以前不存在 ⇒ 修法分"造标记"和"盯标记"两半）：
      ① 词表判"退下/回去/离开…"：11 命中里 **10 条误报**
         （"离开膝上的扇子""压回去""咽回去""天亮前不要出门(台词)"）；
      ② 挂 `world` 状态：`_sync_cast` 的退场支在生产里**一次都没响过**
         （19 个项目 / 47 天：`exit` 词条 0 条、`enter` 77 条）。
    """
    from crew import prose_flow as PF
    _CAST = ('岛村', '驹子', '叶子')
    _BREAK = _mat(
        __import__('display.script', fromlist=['x']).event(
            '叶子将纸门推开些许，送进一壶酒置于火钵边，低头退下', kind_name='外部刺激'),
        __import__('display.script', fromlist=['x']).exit_('叶子', '离场'),
        __import__('display.script', fromlist=['x']).dialogue('岛村', '嗯……', to='驹子'),
        __import__('display.script', fromlist=['x']).action(
            '叶子', '她把壶往驹子手边推了推，指尖在壶身停了停。'),
    )
    ok('J0 ★★★ 断链夹具真的含 `〔退场〕叶子` 与之后的 `叶子：…`'
       '（夹具本身就是生产格式，见 `_mat`）',
       any(x.startswith('〔退场〕叶子') for x in _BREAK)
       and any(x.startswith('叶子：') for x in _BREAK),
       str(_BREAK[1]))

    ok('J1 ★★★ 行为判：`〔退场〕X` 之后 X 又作为说话人出现，中间没有 `〔出场〕X`'
       ' ⇒ 判断链（真跑那一句的形状）',
       [b['who'] for b in PF.presence_chain_breaks(_BREAK, names=_CAST)] == ['叶子']
       and '推了推' in PF.presence_chain_breaks(_BREAK, names=_CAST)[0]['line'],
       str(PF.presence_chain_breaks(_BREAK, names=_CAST)))
    ok('J2 ★★★ 成对：中间补一条 `〔出场〕X` ⇒ **不判**'
       '（"回来了再动手"是合法的；不判的就是一刀切）',
       PF.presence_chain_breaks(_mat(
           __import__('display.script', fromlist=['x']).exit_('叶子', '离场'),
           __import__('display.script', fromlist=['x']).enter('叶子', '入画'),
           __import__('display.script', fromlist=['x']).action(
               '叶子', '她把壶往驹子手边推了推。')),
           names=_CAST) == [], '')
    ok('J3 ★★★ 成对：中间**换了幕** ⇒ 不判'
       '（换幕就是换局面，上一幕的在场状态不许带过来）',
       PF.presence_chain_breaks(
           ['〔第 2 幕 · 子时 23:40 · 温泉旅馆二楼〕',
            _mat(__import__('display.script', fromlist=['x']).exit_('叶子', '离场'))[0],
            '〔第 3 幕 · 丑时 01:10 · 温泉旅馆二楼〕',
            _mat(__import__('display.script', fromlist=['x']).dialogue(
                '叶子', '先生，夜深了。', to='岛村'))[0]],
           names=_CAST) == [], '')
    ok('J4 ★★★ 成对：带 `（别处）` 后缀的行**不判**'
       '（那是"这事在别处发生"的合法形状，正是离场的人该有的行）',
       PF.presence_chain_breaks(_mat(
           __import__('display.script', fromlist=['x']).exit_('叶子', '离场'),
           __import__('display.script', fromlist=['x']).action(
               '叶子', '她在廊下把壶放在门边。', visibility='elsewhere')),
           names=_CAST) == [], '')
    ok('J5 ★★★ 成对：`〔心声·X〕` **不判**（人走了也能在心里说话，'
       '心声不是在场证据）',
       PF.presence_chain_breaks(_mat(
           __import__('display.script', fromlist=['x']).exit_('叶子', '离场'),
           __import__('display.script', fromlist=['x']).aside(
               '叶子', '我该下去了，灶上的粥还温着。')),
           names=_CAST) == [], '')
    ok('J6 ★★★ 成对：**没有在场名单就不判**（不猜 —— 猜出来的名单'
       '会把判据变成"看运气"）',
       PF.presence_chain_breaks(_BREAK, names=()) == [], '')
    ok('J7 ★★ `material_speaker` 认得 `名字：` 与 `名字（…）对Y：`，'
       '而**不把以名字开头的叙述句**当说话人行'
       '（"叶子将纸门推开…"是叙述，不是谁在说话）',
       PF.material_speaker('叶子：她把壶推过去。', _CAST) == '叶子'
       and PF.material_speaker('叶子（向岛村）对驹子：夜深了。', _CAST) == '叶子'
       and PF.material_speaker('叶子将纸门推开些许，低头退下', _CAST) == ''
       and PF.material_speaker('〔心声·叶子〕我该下去了。', _CAST) == ''
       and PF.material_speaker('叶子（别处）：她在廊下放壶。', _CAST) == '',
       '')
    ok('J8 ★★ `presence_break_note` 把断链压成一句给作家的指令'
       '（点名到人，并给出路）',
       (lambda n: '叶子' in n and '进场标记' in n and '一次完整动作' in n)(
           PF.presence_break_note(_BREAK, names=_CAST)),
       PF.presence_break_note(_BREAK, names=_CAST))
    ok('J9 ★★★ 成对：材料干净时 `presence_break_note` 返回**空串**'
       '（提示词里一个字都不加 —— 常年挂一条用不上的禁令只会稀释别的规则）',
       PF.presence_break_note(_mat(
           __import__('display.script', fromlist=['x']).action(
               '叶子', '她把壶往驹子手边推了推。')), names=_CAST) == '', '')

    # ── 下半：标记是谁造出来的（`scene_builder.observe_event`）──
    # [EN] The lower half: who makes the mark (`scene_builder.observe_event`).
    ok('J10 ★★★ AST：`observe_event` 里真的调了 `S.exit_` 与 `S.enter`'
       '（不是只加了一条事件词条 —— 那样标记永远不存在）',
       _event_marks_emitted(), '')
    ok('J11 ★★★ AST：`observe_event` 里有**两条护栏**'
       '（在场的才许标离场、不在场的才许标进场；两条都要在源码里）',
       _event_guards_present(), '')
    ok('J12 ★★★ AST：护栏还要求名字**在事件描述里出现过**'
       '（挡模型在那两栏里编名字）',
       _event_guards_named(), '')

    # ── 导演侧：两栏是结构化的，不是从描述里抠字 ──
    # [EN] Director side: the two fields are structured, not carved out of prose.
    ok('J13 ★★★ AST：`DirectorEvent` 上有 `leaving` / `entering` 两个字段'
       '（没有字段 ⇒ 那一栏无处可去，整条链断在最上游）',
       _event_fields_present(), '')
    ok('J14 ★★★ AST：`_inject_event` 从 JSON 的 `离场人物` / `进场人物` 取这两栏'
       '（且只做清洗、不校验 —— 校验在 `observe_event`，不两处实现）',
       _event_fields_parsed(), '')
    ok('J15 ★★★ 成对：提示词里要的键 与 解析时读的键**逐字一致**'
       '（改一面就该红 —— 只改提示词，模型按新键答、代码读旧键 ⇒ 两栏恒空，'
       '标记永远造不出来；这是"提示词与实现脱钩"的可数形状）',
       _event_field_keys_consistent(), '')

    # ── 作家侧：那句指令真的进了 prompt（"写了 ≠ 生效"）──
    # [EN] Novelist side: the instruction really reaches the prompt
    # [EN] ("written in a prompt != in effect").
    ok('J16 ★★★ 抓 `_transcribe_once` **真发出去的 prompt**：有断链时'
       '那句指令在里面（占位符写错名字会在这里炸，而不是在语法检查里）',
       _prompt_carries_note(broken=True), '')
    ok('J17 ★★★ 成对：抓真 prompt —— 材料干净时那句指令**不在**里面'
       '（否则每篇都挂一条用不上的禁令）',
       not _prompt_carries_note(broken=False), '')
    ok('J18 ★★★ AST：`_presence_break_note` 走 `prose_flow.presence_chain_breaks`'
       '（不许在剧组里再写一个判据）',
       _note_calls_prose_flow(), '')


def _scene_builder_tree():
    import ast
    import io
    from pathlib import Path
    src = io.open(Path(__file__).resolve().parent.parent / 'display'
                  / 'scene_builder.py', encoding='utf-8', newline='').read()
    return ast.parse(src)


def _observe_event_fn():
    tree = _scene_builder_tree()
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
           and n.name == 'observe_event']
    return fns[0] if len(fns) == 1 else None


def _event_marks_emitted() -> bool:
    fn = _observe_event_fn()
    if fn is None:
        return False
    called = {c.func.attr for c in ast.walk(fn)
              if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    return {'exit_', 'enter'} <= called


def _event_guards_present() -> bool:
    """两条护栏都必须在源码里：`in cast` 与 `not in cast` / `in desc`。"""
    fn = _observe_event_fn()
    if fn is None:
        return False
    src = ast.unparse(fn)
    return ("n not in cast" in src and "n in cast" in src
            and "n not in desc" in src)


def _event_guards_named() -> bool:
    """名字必须在事件描述里出现过（`n not in desc` 就是那条护栏）。"""
    fn = _observe_event_fn()
    return fn is not None and 'n not in desc' in ast.unparse(fn)


def _event_fields_present() -> bool:
    import ast
    import io
    from pathlib import Path
    src = io.open(Path(__file__).resolve().parent.parent / 'director'
                  / 'engine.py', encoding='utf-8', newline='').read()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == 'DirectorEvent':
            names = {t.target.id for t in n.body
                     if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)}
            return {'leaving', 'entering'} <= names
    return False


def _event_fields_parsed() -> bool:
    from director import engine as E
    import inspect
    s = inspect.getsource(E.DirectorEngine._inject_event)
    return ('leaving=' in s and 'entering=' in s
            and '离场人物' in s and '进场人物' in s)


def _event_field_keys_consistent() -> bool:
    """提示词 JSON 规范里要的四个键 与 解析时读的四个键**逐字一致**。

    ★★★ 为什么不能写成"源码里含 `离场人物`"（2026-10-19 第十二轮实测过一次）
    -----------------------------------------------------------------------
    第一版就是 `'离场人物' in s and '进场人物' in s and '留空' in s` ——
    结果把提示词里的键改名成 `离场者`，判据**照样绿**：`离场人物` 在
    `result.get("离场人物")` 里还出现着。这正是"文案一改，字符串判据反过来"。

    现在的形状是**两侧对照**：从 `_inject_event` 源码里同时抓
      · 提示词那一侧：`"离场人物":` / `"进场人物":` / `"事件":` / `"涉及人物":`
      · 解析那一侧：`result.get("离场人物"` / …
    两边必须**完全同一个集合**。改任何一面 ⇒ 集合不等 ⇒ 红。
    [EN] The four keys the prompt asks for and the four keys the parser reads must
    [EN] match **exactly**. ⚠ The first version was `'离场人物' in s ...` and stayed
    [EN] green when the prompt key was renamed, because the parser still had
    [EN] `result.get("离场人物")`. That is "the criterion flips when the wording
    [EN] changes". Now both sides are collected and compared as sets.
    """
    import re
    from director import engine as E
    import inspect
    s = inspect.getsource(E.DirectorEngine._inject_event)
    keys = ('事件', '涉及人物', '离场人物', '进场人物')
    asked = {k for k in re.findall(r'"([^"]+)":', s) if k in keys}
    read = {k for k in re.findall(r'result\.get\("([^"]+)"', s) if k in keys}
    return asked == read == set(keys)


def _prompt_carries_note(*, broken: bool) -> bool:
    """真跑一次 `_transcribe_once`，看那句指令进没进 prompt。"""
    import asyncio
    from crew import agents as A
    if broken:
        body = '\n'.join(_mat(
            __import__('display.script', fromlist=['x']).exit_('叶子', '离场'),
            __import__('display.script', fromlist=['x']).action(
                '叶子', '她把壶往驹子手边推了推。')))
    else:
        body = '\n'.join(_mat(
            __import__('display.script', fromlist=['x']).action(
                '叶子', '她把壶往驹子手边推了推。')))
    seen: dict = {}
    real_ask = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''

        class R:
            ok = True
            value = '（测试输出）'
            notes = []
        return R()

    class Ctx:
        people = ['岛村', '驹子', '叶子']

        def world_brief(self, k=500):
            return '世界观'

        def genre(self):
            return ('', '')
    A.ask = fake_ask
    try:
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'
        asyncio.run(A.Novelist._transcribe_once(
            n, Ctx(), body, scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask
    return '进场标记' in str(seen.get('prompt') or '')


def _note_calls_prose_flow() -> bool:
    from crew import agents as A
    import inspect
    s = inspect.getsource(A.Novelist._presence_break_note)
    return 'presence_chain_breaks' in s


def _drop_lines(raw: str, names) -> str:
    """调生产侧的材料闸（不实例化整个剧组）。"""
    from crew.agents import Novelist

    class _C:
        people = list(names)

    return Novelist._drop_dangling_lines(None, raw, _C())


def _dangling_src() -> str:
    from crew import agents as A
    import inspect
    return inspect.getsource(A.Novelist._drop_dangling_lines)


def _event_src() -> str:
    from director import engine as E
    import inspect
    return inspect.getsource(E.DirectorEngine._inject_event)


def _calls_dangling() -> bool:
    s = _dangling_src()
    return 'dangling_reference' in s and 'getattr' not in s.replace(
        "getattr(ctx, 'people'", '')


def _engine_tree():
    import ast
    import io
    from pathlib import Path
    src = io.open(Path(__file__).resolve().parent.parent / 'director' / 'engine.py',
                  encoding='utf-8', newline='').read()
    return ast.parse(src)


def _gate_if(tree):
    """`_inject_event` 里那个判"有没有引语"的 `if` 节点（找不到返回 None）。"""
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
           and n.name == '_inject_event']
    if len(fns) != 1:
        return None
    for node in ast.walk(fns[0]):
        if not isinstance(node, ast.If):
            continue
        for c in ast.walk(node.test):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == 'has_quoted_speech'):
                return node
    return None


def _event_gate_wired() -> bool:
    tree = _engine_tree()
    node = _gate_if(tree)
    if node is None:
        return False
    # 判据必须是**事件描述本身**（`event.description` 或 `desc2`），不是空串/常量
    got = {ast.unparse(a) for c in ast.walk(node.test) if isinstance(c, ast.Call)
           and isinstance(c.func, ast.Name) and c.func.id == 'has_quoted_speech'
           for a in c.args}
    return bool(got) and all('description' in g or 'desc' in g for g in got)


def _event_gate_rejects() -> bool:
    tree = _engine_tree()
    node = _gate_if(tree)
    if node is None:
        return False
    # 闸体里（含嵌套）必须有 `return None`
    for sub in ast.walk(node):
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant) \
                and sub.value.value is None:
            return True
    return False


# ══════════════════════════════════════════════════════════════
#  K  同一写法用超了（#573 沉默无层次 / #574 口癖·细节重复超配）
# [EN] K  Same device reused too often (silence with no layers / tics & detail repetition)
# ══════════════════════════════════════════════════════════════
def group_k() -> None:
    """K 组：**同一写法用了一次又一次**（2026-10-19 第十一轮，用户第 5、6 条）。

    三个检测器都在 `crew.prose_flow`（纯代码、零成本）：
      · `silence_gaze_issues`  否定回应 + 紧跟视线落点 的成套句式，一天 >=2 处；
      · `repeated_tic_issues`  对白里同一段 >=4 字的话，一天 >2 次（不问说话人）；
      · `detail_repeat_issues` 旁白里同一「道具+状态动词」，一天 >=3 次；
      · `repeat_issues`        带 `kind` 的合并入口。

    判据设计（全部有实测依据，见各自 docstring）：
      L1a 沉默成套句式被抓出来 —— M51 改上限即红；
      L1b 台词口癖被抓出来 —— M52 改上限即红；
      L1c 细节复读被抓出来 —— M53 改上限即红；
      L2  成对：**都在上限内时一个都不报**（否则是"一刀切也能绿"）；
      L3  口癖**整篇对白累计、不问说话人**：同一句被不同说话人说了 3 次仍报
            （实测从正文归属说话人完全不可靠，按人算会把口癖劈成假人、一次都报不出）；
      L4  成对：**指称类短语不判**（"十五年前"说 3 次是同一件事，不是口癖）。
    """
    from crew.prose_flow import (silence_gaze_issues, repeated_tic_issues,
                                 detail_repeat_issues, repeat_issues)

    # 过度复用（形状来自真跑产物，合成样本）：
    #   沉默 2 处 + 口癖「你这个人哪」3 次 + 细节「炭塌了」3 次
    bad = (
        '岛村没应，看那道门缝雪光。驹子又问了一遍，岛村没接话，只望着手里的杯子。'
        '叶子说："你这个人哪。"驹子笑："你这个人哪。"叶子又低下眼："你这个人哪。"'
        '炭塌了。酒凉了。炭塌了。灯灭了。炭塌了。'
    )
    # 正常复用（都在上限内）：沉默 1、口癖 1、细节 1
    good = (
        '岛村没应，看那道门缝雪光。'
        '叶子说："你这个人哪。"他没接。"你是什么样的人。"'
        '炭塌了。灯亮着。'
    )

    sb = silence_gaze_issues(bad)
    tb = repeated_tic_issues(bad)
    db = detail_repeat_issues(bad)
    rb = repeat_issues(bad)          # 带 kind 的合并入口（L3 用）
    rg = repeat_issues(good)
    ok('L1a ★★★ **沉默成套句式被抓出来**（"没应，看某个东西"一天 >=2 处）',
       bool(sb), f'{sb}')
    ok('L1b ★★★ **台词口癖被抓出来**（同一句 >=4 字的话一天 >2 次）',
       bool(tb), f'{tb}')
    ok('L1c ★★★ **细节复读被抓出来**（同一「道具+状态动词」一天 >=3 次）',
       bool(db), f'{db}')
    # 成对：上限内不报（"一刀切也能绿"会被这条抓到）
    ok('L2 ★★★ 成对：**都在上限内时一个都不报**（否则是"一刀切也能绿"）',
       rg == [], f'{rg}')
    # 口癖按"整篇累计、不问说话人"：不同说话人各说一次、合计 3 次仍报
    ok('L3 ★★★ 口癖**整篇累计、不问说话人**：同一句被不同说话人说了 3 次仍报',
       any(x['kind'] == 'tic' and x['times'] > x['cap'] for x in rb), f'{tb}')
    # 成对：指称类短语不判（"十五年前"说 3 次是同一件事）
    ref = '他说："十五年前。"她接："十五年前。"他又叹："十五年前。"'
    ok('L4 ★★★ 成对：**指称类短语不判**（"十五年前"说 3 次是同一件事，不是口癖）',
       not any(x['kind'] == 'tic' for x in repeat_issues(ref)),
       f'{[(x["kind"], x["what"]) for x in repeat_issues(ref)]}')


def group_l() -> None:
    """L 组：**配角按模版刷存在感**（2026-10-19 第十一轮，用户"叶子台词过多"）。

    检测器 `crew/prose_flow.vocative_share_issues`（纯代码、零成本）：
    台词里以「称呼 + 停顿标点」开头（「先生，…」「X姐，…」）的条数，
    超过 `int(总台词 * VOCATIVE_CAP)` 就报。

    为什么立这一条、**不**立"答非所问"（同一个探针一起量过，见
    `developers/diag_readability.py`）：
      · 真人 18 章（samples/zh）称呼式台词 **中位 0%、最大 0%** —— 一条都没有；
        真跑 snow_v11 19.1% / snow_v12 30.0%。差距干净，立得住。
      · 而"相邻台词共享二元组"（我第一版用来判答非所问的）真人 **88%**、
        问→答 更是 **100%**，比真跑的 74% 还高 ⇒ 字面重合判不了语义是不是
        同一条线（R02）。用它立判据会把真人一起判死，所以**不立**。

    ⚠ 判据必须钉真人：`N1b` 真接读 samples/zh 的 18 章 —— 这条红了就是
      判据在误伤真人，比"抓不到"更严重。
    """
    from crew.prose_flow import (vocative_lines, vocative_share_issues,
                                 repeat_issues)

    # 刷屏形状（来自真跑 snow_v12：叶子九句全是「先生，…」）
    spam = (
        '叶子说："先生，我可以进来吗？"她又道："先生，酒给您放在门口了。"'
        '她退到门外："先生，酒不够的话，随时叫我就好。"'
        '她探身："先生，驹子姐好像有些醉了，我送她回去休息吧。"'
        '她跪下拨火："先生，我把火钵给您拨一拨。"'
        '她提壶："先生，这酒我先提回去了。"'
        '她带上门："先生，廊下风紧了，门我替您带上。"'
        '门外又一句："先生，夜深了，早些歇息吧。"'
        '驹子问："你还听吗？"岛村答："听。"她说："那就好。"'
    )
    # 正常对话：只有一句带称呼（在上限内）
    normal = (
        '叶子说："先生，酒放门口了。"'
        '驹子问："你还听吗？"岛村答："听。"'
        '驹子又说："那我接着念。"岛村点头："念吧。"'
        '驹子念完抬头："你倒是说句话。"岛村笑："说些什么呢。"'
        '驹子低头："说你听见了。"岛村："听见了。"'
        '外面更鼓响了一声。两人都没再开口。'
    )
    # 台词太少（< 8 条）：占比没有意义，不许判
    tiny = '叶子说："先生，酒放门口了。"驹子应："好。"岛村："嗯。"'

    vs = vocative_share_issues(spam)
    vn = vocative_share_issues(normal)
    vt = vocative_share_issues(tiny)
    ok('N1a ★★★ **称呼式台词刷屏被抓出来**（"先生，…"一类按模版刷存在感）',
       bool(vs), f'{vs}')
    ok('N1b ★★★ 真人 18 章（samples/zh）**零误报** —— 这条红了就是判据在误伤真人，'
       '比抓不到更严重',
       _human_vocative_clean(), _human_vocative_detail())
    ok('N2 ★★★ 成对：**上限内不报**（正常对话里一两句称呼是合法的）',
       vn == [], f'{vn}')
    ok('N3 ★★★ 成对：**台词少于 8 条时不判**（短文本算占比全是噪声）',
       vt == [], f'{vt}')
    # 合并入口带上 kind（与另三类同一个形状，修复提示词才说得清"最多留几条"）
    ks = [x['kind'] for x in repeat_issues(spam)]
    ok('N4 ★★ `repeat_issues` 合并入口里带 `vocative` 这个 kind',
       'vocative' in ks, f'{ks}')


def group_m() -> None:
    """M 组：**派活只派了"不做什么"**（R40，2026-10-19 第十一轮）。

    检测器 `crew/prose_flow.passive_task_roles`（纯代码、零成本），入参是解析后的
    `角色任务`（`{人名: [任务, ...]}`）—— 所以这一组测的是**上游派活**，不是成文。

    ⚠ 这是**结构性约束**，不是统计阈值：一个"只被派了不做什么"的人在场上不可能
      有戏，跟"多少算多"无关，所以不需要真人样本定阈值（R11 管的是阈值类判据）。

    判据：
      P1a 全否定型派活被抓出来 —— M56 关掉检测即红；
      P2  成对：**被否定掉的动词不算肯定动作**（"不说话"里有"说"，但那是被否掉的
          —— 检测器第一版就栽在这里，该报的没报）；
      P1b 成对：**只要有一条肯定性动作就不报**（"先忍着、末了挑明"是好派活，
          一刀切会把它一起判死）；
      P3  成对：空任务不报；
      P4  `passive_task_note` 能压成一句给人看的话。
    """
    from crew.prose_flow import passive_task_roles, passive_task_note

    allneg = {'甲': ['不说话', '不回应']}
    neg_verb = {'甲': ['不要说话']}
    silent = {'甲': ['沉默地看着她']}
    good = {'甲': ['先忍着不说', '末了把话挑明']}
    good2 = {'甲': ['送酒到门缝便退不纠缠']}
    empty = {'甲': []}
    move = {'甲': ['从廊道走到纸门外停步不出声惊动屋内']}
    #: 全是否定，且带"看"这种万能词 —— 它**不该**给通行证。
    #: （判据靠它守着：哪天有人把"看 / 观察"加进 `_AFF_VERB`，P6 立刻红。）
    filler = {'甲': ['要看着她不说话', '要忍着不回应']}

    ok('P1a ★★★ **只派了"不做什么"的角色被抓出来**（他在场上无事可做）',
       bool(passive_task_roles(allneg)), f'{passive_task_roles(allneg)}')
    ok('P2 ★★★ 成对：**被否定掉的动词不算肯定动作**（"不说话"里有"说"，但被否掉了）',
       bool(passive_task_roles(neg_verb)) and bool(passive_task_roles(silent)),
       f'{passive_task_roles(neg_verb)} / {passive_task_roles(silent)}')
    ok('P1b ★★★ 成对：**只要有一条肯定性动作就不报**（"先忍着、末了挑明"是好派活）',
       passive_task_roles(good) == [] and passive_task_roles(good2) == [],
       f'{passive_task_roles(good)} / {passive_task_roles(good2)}')
    ok('P3 ★★ 成对：**空任务不报**', passive_task_roles(empty) == [],
       f'{passive_task_roles(empty)}')
    # ⚠ 真跑实证的**误报修正**（2026-10-20）：叶子被派「从廊道走到纸门外停步
    #   不出声惊动屋内」，她明明有事可做，却因"走 / 停"不在肯定动词表里被判成
    #   "只派了不做什么" —— v13 日志里那条 WARNING 就是它。
    #   区分标准：万能词（要 / 做 / 观察）**每条任务都有**，放进来判据就永远绿；
    #   位移与肢体动词**只有真要动起来才有**，放进来不会让它失效。
    ok('P5 ★★★ 成对：**位移动作算肯定动作**（"走到纸门外停步"是有戏的，'
       'v13 曾误报过）', passive_task_roles(move) == [], f'{passive_task_roles(move)}')
    ok('P6 ★★★ 成对：**万能词不算肯定动作**（"要观察"不能给通行证，'
       '否则判据永远绿）', bool(passive_task_roles(filler)),
       f'{passive_task_roles(filler)}')
    ok('P4 ★★ `passive_task_note` 把问题压成一句给人看的话（没问题时是空串）',
       bool(passive_task_note(allneg)) and passive_task_note(good) == '',
       f'{passive_task_note(allneg)}')


def _human_chapters() -> list:
    """真人 18 章正文（samples/zh/*/正文/*.md）。"""
    out = []
    base = APP / 'samples' / 'zh'
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        body = d / '正文'
        if not body.exists():
            continue
        for f in sorted(body.glob('*.md')):
            try:
                out.append((f'{d.name}/{f.stem}', f.read_text(encoding='utf-8')))
            except OSError:
                continue
    return out


def _human_crowd_detail() -> str:
    from crew.prose_flow import crowded_paragraph_issues
    ch = _human_chapters()
    bad = [(n, crowded_paragraph_issues(t)) for n, t in ch]
    bad = [(n, v) for n, v in bad if v]
    return f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:3]}' if bad else '')


def _human_crowd_clean() -> bool:
    from crew.prose_flow import crowded_paragraph_issues
    ch = _human_chapters()
    if len(ch) < 12:                     # 语料被搬走了就红，不许"没数据⇒绿"
        return False
    return all(not crowded_paragraph_issues(t) for _, t in ch)


def group_o() -> None:
    """O 组：**一大段塞了十几件事（流水账）**（2026-10-20 第十二轮）。

    检测器 `crew/prose_flow.crowded_paragraph_issues`（纯代码、零成本）：
    一段里按句号/问号/叹号切出的子句数，最大那段 > `PARA_EVENT_CAP`(7) 就报。

    ★★ **这是目前量到的最干净的一条**：真人 18 章段落最长 125 字、**段内最多 7 件事**，
    18 章**没有一章越界**；真跑 snow_v12 最长一段 638 字 / **44 件事**，
    v13 = 12、v14 = 19 —— 是真人上限的 **1.7~6 倍**。

    为什么它比"答非所问""情感轻放"好判：那些是**语义**层（真人问→答的字面
    零承接率就有 100%，立判据会把真人一起判死）；段落挤不挤只数**一段里断了
    几句**，没有歧义，也不依赖说话人归属。

    ⚠ 判**段内事件数**而不是字数：一段可以很长但只要在一件事里打转就不挤
      （真人最长那段 125 字只有 7 件事）；反过来短短一段塞十件事同样是流水账。
    ⚠ **不并入 `repeat_issues`**：那边的改写提示词整段都在讲"同一个写法用了一次
      又一次"，把"一段太挤"混进去会指错方向 —— 走独立的 `crowded_rewrite_prompt`。
    """
    from crew.prose_flow import (crowded_paragraph_issues,
                                 paragraph_event_counts, crowded_rewrite_prompt)

    # 流水账：十几件事连成一大坨，中间没有分段（真跑 snow_v12 的形状）
    crowd = (
        '她问："你来吗？"他应："唔。"'
        '她又问："到底来不来？"他看向别处。'
        '门响了，叶子端酒进来，放下，退到门外。'
        '她追着问："你说句话。"他摩挲书页。'
        '炭塌了一下。更鼓响了一声。'
        '她再问："你倒是说话呀。"他望窗。'
        '叶子又推门："酒够了吗？"'
        '她低声："那我不问了。"'
        '他终于开口："我多待几天。"'
        '叶子掩门。屋里静了。'
        '她抬头看他。他没接话。'
        '雪光落在榻榻米上。'
    )
    # 正常分段：每件事都另起一段
    normal = (
        '她问："你来吗？"他应："唔。"\n\n'
        '炭塌了一下。\n\n'
        '她又问："到底来不来？"他看向别处。\n\n'
        '她低声："那我不问了。"'
    )
    tiny = '她问："你来吗？"他应："唔。"'

    c1 = crowded_paragraph_issues(crowd)
    c0 = crowded_paragraph_issues(normal)
    ct = crowded_paragraph_issues(tiny)
    ok('S1a ★★★ **一大段塞了十几件事被抓出来**（读起来是一坨流水账）',
       bool(c1) and c1[0]['times'] > c1[0]['cap'], f'{c1}')
    ok('S1b ★★★ 真人 18 章（samples/zh）**零误报** —— 这条红了就是判据在误伤真人，'
       '比抓不到更严重',
       _human_crowd_clean(), _human_crowd_detail())
    ok('S2 ★★★ 成对：**正常分段不报**（每件事都另起一段）',
       c0 == [], f'{c0}  事件分布={paragraph_event_counts(normal)}')
    ok('S3 ★★ 成对：**就一件事时不报**', ct == [], f'{ct}')
    p = crowded_rewrite_prompt(crowd, c1)
    ok('S4 ★★ `crowded_rewrite_prompt` 给出**可数的事实**（"已经 N 件，最多 7 件"）',
       ('已经 **' in p) and '最多 7 件' in p and '事实一个字都不许改' in p,
       f'{len(p)} 字')


def _human_hedge_detail() -> str:
    from crew.prose_flow import hedge_reply_issues
    ch = _human_chapters()
    bad = [(n, hedge_reply_issues(t)) for n, t in ch]
    bad = [(n, v) for n, v in bad if v]
    return f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:3]}' if bad else '')


def _human_hedge_clean() -> bool:
    from crew.prose_flow import hedge_reply_issues
    ch = _human_chapters()
    if len(ch) < 12:                     # 语料被搬走了就红，不许"没数据⇒绿"
        return False
    return all(not hedge_reply_issues(t) for _, t in ch)


def group_n() -> None:
    """N 组：**对话没人正面回答**（2026-10-19 第十一轮，用户"答非所问失控"）。

    两个检测器（都在 `crew/prose_flow`）：
      · `hedge_reply_issues` —— 含糊应答「唔……这么晚了。」（语气词开头 + 不相干尾巴）
      · `reask_chain_issues` —— 同一件事被追问了多少遍（问了没人理，才需要再问）

    ⚠ **这一组是第三轮才立住的**。前两轮我用**占比**当基线，结论是"无区分度、
      立不了判据"——那是**基线错了**，不是判据不行：真人每章只有 3~44 句台词，
      5 句里 1 句应答就是 20%，小样本把真人的最大值抬得比真跑还高。
      改用**绝对条数**后信号立刻干净：
        含糊应答   真人最大 1 条（14 章是 0）  vs  v13 = 5
        追问链     真人最大 2                 vs  v12 = 5
      （探针 `developers/diag_readability.py` 两种口径都留着，可重跑复现。）

    ⚠ 仍然**不**判"答非所问"本身：真人问→答的字面零承接率是 100%，
      比真跑还高（R02 字面重合判不了语义）。能判的只有它这两个**结构性**后果。
    """
    from crew.prose_flow import (hedge_reply_issues, is_hedge_reply,
                                 repeat_issues)

    # 含糊应答刷屏（来自真跑 snow_v13：岛村一律"唔……"滑过去）
    hedgy = (
        '驹子问："您就不好奇我为什么这么晚还过来吗？"岛村："唔……这么晚了。"'
        '驹子凑近："您还没回答我呢。"岛村："唔……路上滑吧。"'
        '驹子再问："您就这么不想知道吗？"岛村："唔……夜深了。"'
        '驹子追着："这里的雪到底是什么样的？"岛村："唔……干净是干净。"'
        '驹子低声："那您就看着雪吧。"岛村："唔……好。"'
    )
    # 正常对白：有问有答，只有一处含糊
    normal = (
        '驹子问："您是从东京来的吧？"岛村："是，前天到的。"'
        '驹子："东京很远吗？"岛村："坐一天的车。"'
        '驹子："那您什么时候走？"岛村："唔……还没定。"'
        '驹子："没定就是还能住几日。"岛村："可以这么说。"'
        '驹子笑："那我明日还来。"岛村："来吧。"'
    )
    # 台词太少（< 8 条）：条数没有意义，不许判
    tiny = '驹子："你来吗？"岛村："唔……来。"驹子："好。"岛村："嗯。"'
    # 同一件事**真的**被追到第五遍（真跑 snow_v12 的形状）
    # ⚠ 这一条是**反面证据**：字面一个二元组都不共享，任何字面聚类的检测器
    #   都抓不到它。留在这里是为了钉死"追问链"那条路已经试过、走不通
    #   （详见 crew/prose_flow.py 里 `_REPEAT_KIND_CN` 上方那段注释）。
    chase = (
        '驹子问："您就不好奇我为什么这么晚还过来吗？"岛村看向别处。'
        '驹子："您还没回答我呢。"岛村望窗。'
        '驹子："就没一句话要问我？"岛村摩挲书页。'
        '驹子："您就这么不想知道吗？"岛村没抬眼。'
        '驹子："您还没回答我呢，这里的雪到底是什么样的？"'
    )

    h1 = hedge_reply_issues(hedgy)
    h0 = hedge_reply_issues(normal)
    ht = hedge_reply_issues(tiny)
    ok('Q1a ★★★ **含糊应答刷屏被抓出来**（"唔……"+ 不相干的尾巴 = 等于没回答）',
       bool(h1) and h1[0]['times'] > h1[0]['cap'], f'{h1}')
    ok('Q1b ★★★ 真人 18 章（samples/zh）**零误报** —— 这条红了就是判据在误伤真人，'
       '比抓不到更严重',
       _human_hedge_clean(), _human_hedge_detail())
    ok('Q2 ★★★ 成对：**正常对白不报**（有问有答，只有一处含糊）',
       h0 == [], f'{h0}')
    ok('Q3 ★★★ 成对：**台词少于 8 条时不判**（短文本数条数全是噪声）',
       ht == [], f'{ht}')
    ok('Q4 ★★ `is_hedge_reply` 认得出单条含糊应答（"是啊"这类纯应答不算）',
       is_hedge_reply('唔……这么晚了。') and not is_hedge_reply('是，前天到的。'),
       f"{is_hedge_reply('唔……这么晚了。')} / {is_hedge_reply('是，前天到的。')}")
    ks = [x['kind'] for x in repeat_issues(hedgy + chase)]
    ok('Q5 ★★ `repeat_issues` 合并入口里带 `hedge` 这个 kind（改写提示词靠它）',
       'hedge' in ks, f'{ks}')


def group_p() -> None:
    """P 组：**在同一个地方打转**（2026-10-20 第十二轮，用户点名"用 LLM 判官"）。

    ★★★ 这一组**不检测语义**，只钉住"判官这条链路"里**可数**的那几段：
      · `parse_spin_verdict` —— 判官回话的**解析层**（安全全在这里）；
      · `topic_hotspots` —— 给判官的**备料**（必须剔掉角色名）；
      · 两个提示词 —— 内容必须到位（判官提示词必须写"不算打转"，
        修复提示词必须给可数事实）。

    为什么**判据里没有检测器**：打转是**换了说法**的重复，四条字面路实测全废：
      · 动宾紧邻：真人 18 章最大 1 次 / 真跑也是 1 次（零区分度）；
      · 全文 2-gram 峰值：真人是**角色名**（阿箬 14）与**核心道具**（老河 14），
        真跑是火钵 13 —— 人是这么写小说的，量分不出病；
      · 字面零承接：真人 **100%**，比真跑还高（R02）；
      · 台词 2-gram：真人是专有名词（主簿 5），真跑是"好人" 10 —— 太近。
    ⇒ 硬立一条字面判据，只会造出一条**专杀真人**的假判据。判决交给判官。

    ⚠ 所以**最关键的两条是安全侧**：判官说没打转、或回话看不懂，一律**不改稿**。
      改坏一篇好稿，比漏改一处打转严重得多 —— 这两条红了就是产品会发坏稿。
    """
    from crew.prose_flow import (parse_spin_verdict, topic_hotspots,
                                 spin_judge_prompt, spin_rewrite_prompt)

    # 判官报打转（真跑 snow_v16 的形状：驹子把同一件事问了七遍）
    spin_yes = (
        '判定：打转' + chr(10)
        + '那一件事：驹子把「我是不是好人」换着说法问了七遍，岛村每回都躲开' + chr(10)
        + '重复的出处：' + chr(10)
        + '- 你说，好人是不是都没好报啊？' + chr(10)
        + '- 那你说，我是不是好人？' + chr(10)
        + '- 我到底算不算好人？'
    )
    # 判官说没打转（真人小说最常见的回话）
    spin_no = '判定：没打转'
    # 判官说了别的（有推进，不算打转）
    spin_no2 = '判定：不算打转。问了有人接住，是戏在走。'
    # 回话看不懂 / 空 / 根本没按格式来
    junk = '这一章写得不错，人物立得住。'
    empty = ''

    v_yes = parse_spin_verdict(spin_yes)
    v_no = parse_spin_verdict(spin_no)
    v_no2 = parse_spin_verdict(spin_no2)
    v_junk = parse_spin_verdict(junk)
    v_empty = parse_spin_verdict(empty)

    ok('T1a ★★★ 判官报**打转**能解析出来（spin=True，且拿到那一件事与出处）',
       v_yes.get('spin') is True and v_yes.get('what')
       and len(v_yes.get('where') or []) >= 2,
       f"spin={v_yes.get('spin')} what={v_yes.get('what', '')[:20]} "
       f"where={len(v_yes.get('where') or [])}")
    ok('T1b ★★★ 成对：判官说**没打转** ⇒ 绝不改稿（"没打转"里也有"打转"两个字）',
       v_no.get('spin') is False, f"{v_no}")
    ok('T1c ★★★ 成对：判官说**不算打转**（有推进）⇒ 同样不改稿',
       v_no2.get('spin') is False, f"{v_no2}")
    ok('T2 ★★★ **回话看不懂/空 ⇒ 绝不改稿**（宁可漏改，不许改坏好稿）',
       v_junk.get('spin') is False and v_empty.get('spin') is False,
       f"junk={v_junk.get('spin')} empty={v_empty.get('spin')}")

    # 备料：给判官的高频词里**不能**是角色名（那是真人小说的常态，当不了线索）
    body = (
        '岛村坐在火钵边。驹子抬眼看他：「你说，好人是不是都没好报啊？」' + chr(10)
        + '叶子将酒壶搁在火钵旁。岛村没应，只把视线落在炭上。' + chr(10)
        + '驹子又问：「那你说，我是不是好人？」火钵里的炭塌了一下。' + chr(10)
        + '叶子把温酒放火钵边。岛村仍旧没接话。'
        + '驹子追着问：「我到底算不算好人？」'
    )
    hot_bare = dict(topic_hotspots(body))
    hot_named = dict(topic_hotspots(body, names=('岛村', '驹子', '叶子')))
    ok('T3 ★★ 给判官的备料**剔掉角色名**（不然线索全是人名，等于没给）',
       '岛村' in hot_bare and '岛村' not in hot_named
       and '好人' in hot_named,
       f"剔名前 {sorted(hot_bare)[:4]} / 剔名后 {sorted(hot_named)[:4]}")

    # 判官提示词：必须把"不算打转"的两类都写进去，否则判官会把好东西当病
    jp = spin_judge_prompt(body, list(hot_named.items())[:4])
    ok('T4 ★★ 判官提示词里写清了**舞台道具不算打转**（没写 ⇒ 判官会去改掉舞台）',
       '道具或场景' in jp and '人名、地名、物件名' in jp and '仅供参考' in jp,
       f"len={len(jp)}")
    # ★★★ T4b（2026-10-20 用户点名「不是所有重复都有问题，要结合上下文语境」）：
    #   提示词必须列出**正当重复**的几种形态，否则判官见到重复就判病 ——
    #   这是本轮改动的核心，缺了它就退回"一刀切"。
    # [EN] The prompt must list the legitimate kinds of repetition; without them the
    # [EN] judge treats any repetition as a defect -- exactly what the author ruled out.
    ok('T4b ★★★ 判官提示词里列出了**正当重复**（回声对答 / 复沓 / 不同人说同一句 / '
       '呼应）—— 缺一条，判官就退回"见重复就判病"',
       all(k in jp for k in ('· **回声式对答**', '· **复沓', '· **不同的人说同一句**',
                             '· **呼应**', '逼一次是戏')),
       '')
    ok('T4c ★★★ 判每条的标准是**可删除性**（"删掉这一条，读者会损失什么"），'
       '不是"重复了几次" —— 这是把"结合语境"变成可执行的一句话',
       '删掉，读者会损失什么' in jp, '')

    # 修复提示词：可数事实必须是**判官抄出来的原句**
    rp = spin_rewrite_prompt(body, v_yes)
    ok('T5 ★★ 修复提示词带上**判官抄的原句**当可数事实（不是我们猜的热点词）',
       '好人是不是都没好报' in rp, f"len={len(rp)}")
    # ★ 2026-10-20 第十三轮追加（R44 的根因）：**修复要求不许再写成结构性措辞** ——
    #   上一版写法"同一件事最多来回三轮""就换个由头"被模型照抄进正文，
    #   变成「算是第二层的新问」「这回只换了个由头」这类元叙述（v17 实测 6 处）。
    # [EN] The repair instructions must no longer be phrased structurally: the old
    # [EN] wording was copied verbatim into the prose as meta-narration.
    ok('T6 ★★ 修复提示词**不再出现"三轮/由头"这类结构性措辞**（那是 R44 的病根）',
       '三轮' not in rp and '由头' not in rp and '不许把上面的要求写进正文' in rp,
       f"len={len(rp)}")


def _human_vocative_detail() -> str:
    from crew.prose_flow import vocative_share_issues
    ch = _human_chapters()
    hit = [(n, vocative_share_issues(t)) for n, t in ch]
    bad = [(n, v) for n, v in hit if v]
    return f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:3]}' if bad else '')


def _human_vocative_clean() -> bool:
    from crew.prose_flow import vocative_share_issues
    ch = _human_chapters()
    if len(ch) < 12:                     # 语料被搬走了就红，不许"没数据⇒绿"
        return False
    return all(not vocative_share_issues(t) for _, t in ch)


# ══════════════════════════════════════════════════════════════
#  U  元叙述：叙述者不许跳出来讲结构（2026-10-20 第十三轮）
# ══════════════════════════════════════════════════════════════
#: 真跑 snow_v17 上**真的出现过**的四种形状（用户对第一类点的名最重）。
#: ⚠ 名字换掉了：判据里不许出现真实角色名，这里用代号。
#: `_U_KEEP` 是**剥完之后必须还在的叙述** —— 少了它，一个"把整句都删掉"的
#:   假剥离也能让"再判一遍 ⇒ 0 条"这条绿（M62 就是这么蒙过去的）。
#: [EN] Each sample keeps a piece of innocent narration: without this, a stripper that
#: [EN] deletes everything would still satisfy "nothing left to flag".
_U_SAMPLES = (
    '目光在他脸上停了停，接住了这第一轮的追问："你说的话是真的吗。"',
    '她问，算是第二层的新问："我算不算个好人。"',
    '叶子重又站在门边探进半张脸："东西我先收走了。" 这回不重复进门送物。',
    '她已不是头回提夜色，这回只换了个由头。',
)
_U_KEEP = ('目光在他脸上停了停', '她问', '叶子重又站在门边探进半张脸', '')


def _human_meta_clean() -> bool:
    from crew.prose_flow import meta_narration_issues
    ch = _human_chapters()
    if len(ch) < 12:                     # 语料被搬走了就红，不许"没数据⇒绿"
        return False
    return all(not meta_narration_issues(t) for _, t in ch)


def _human_meta_detail() -> str:
    from crew.prose_flow import meta_narration_issues
    ch = _human_chapters()
    bad = [(n, meta_narration_issues(t)) for n, t in ch if meta_narration_issues(t)]
    return f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:3]}' if bad else '')


def group_u() -> None:
    """U 组：**叙述者跳出来讲结构**（R44）。

    ★★★ 这一组守的是"我们自己写的修复提示词会被模型念给读者听"这条坑
      —— snow_v12 / v15 / v16 四类信号全为 0，v17 一上打转判官就冒出来 6 处。
      所以它**成对**：既要抓得到，也不能把真人正常的"第二次/不再问"判成病。

    ⚠ U2 / U3 是**假信号防护**，比 U1a 更要紧：
      · 真人 18 章里有 7 条「抄第二遍」「第七遍的时候」—— 那是叙事事实；
      · 真人 18 章里有 5 条「她没听懂，也没再问」—— 那是正常的不再。
      ⇒ 判据必须带上下文（言语行为词 / "这回"+"由头"），只盯一个词会专杀真人。
    """
    from crew.prose_flow import (meta_narration_issues, strip_meta_narration,
                                 meta_markers)

    # ⚠ 一条一条单独判：真人小说里台词自带句末标点（"…吗？"后面没有句号），
    #   几条连在一起会被算成**同一个叙述句**（这是 `\_narration_spans` 有意的行为），
    #   判据条数就会跟着变少 —— 那是合并，不是漏判。
    # [EN] One at a time: dialogue carries its own sentence-end punctuation, so adjacent
    # [EN] samples merge into a single narration sentence by design.
    per: list[tuple[int, int, bool, bool]] = []
    for s, keep in zip(_U_SAMPLES, _U_KEEP):
        h = meta_narration_issues(s)
        stripped, cnt = strip_meta_narration(s)
        per.append((len(h), cnt, not meta_narration_issues(stripped),
                    (keep or '') in stripped))
    kinds = {k for s in _U_SAMPLES for k in
             (m['kind'] for m in meta_narration_issues(s))}
    ok('U1a ★★★ 元叙述能判出来（序数那一类 + 写法对比那一类，四种形状一条不漏）',
       all(c[0] >= 1 for c in per) and kinds == {'order', 'contrast'},
       f'每条 {[c[0] for c in per]} 条，种类 {sorted(kinds)}')

    ok('U1b ★★★ 剥离器删干净了（四条分别再判一遍 ⇒ 0 条）'
       '**且没伤到无辜的叙述**',
       all(c[1] >= 1 and c[2] and c[3] for c in per),
       f'删 {[c[1] for c in per]} 处 / 判净 {[c[2] for c in per]} '
       f'/ 保住叙述 {[c[3] for c in per]}')

    joined = chr(10).join(_U_SAMPLES)
    new, n = strip_meta_narration(joined)
    ok('U1d ★★ 连成一篇也删得干净（同一段再判一遍 ⇒ 0 条）',
       not meta_narration_issues(new) and '先收走了' in new,
       f'删 {n} 处，余 {len(meta_narration_issues(new))} 条')

    ok('U1c ★★★ 真人 18 章（samples/zh）**零误报** —— 这条红了就是判据在误伤真人，'
       '比抓不到严重得多',
       _human_meta_clean(), _human_meta_detail())

    # 成对 ①：叙事里的序数（掸第七遍、抄第二遍）**不许报**
    ok('U2 ★★ 成对：正常叙事里的序数（第二遍 / 第七遍的时候）**不报**',
       not meta_markers('他抄第二遍：从你之后来。')
       and not meta_markers('掸到第七遍的时候，他把算盘抻直。')
       and not meta_markers('头一回问了几更天，第二回就没进门。'),
       '真人 18 章里这一形状有 7 条')

    # 成对 ②：正常的"不再"（不是讲结构，是叙事事实）**不许报**
    ok('U3 ★★ 成对：正常的"不再 / 没再问"（她没听懂，也没再问）**不报**',
       not meta_markers('她没听懂，也没再问。')
       and not meta_markers('老板没再问，弯下腰接着装。')
       and not meta_markers('租约到期，不再续签。'),
       '真人 18 章里这一形状有 5 条')

    # 三条护栏：台词一个字都不许少，带台词的句子不许被整句删掉，第二次跑幂等
    quoted = '掌柜的又说："这回不再赊了。" 她转过身去。'
    ok('U4 ★★ 护栏：**引号里的元叙述字一个都不动**（那是人物说的话）',
       '这回不再赊了' in strip_meta_narration(quoted)[0],
       strip_meta_narration(quoted)[0][:40])

    withline = '他把壶搁下，接住了这第一轮的追问："夜深了。" 窗纸白了一层。'
    out_w, _ = strip_meta_narration(withline)
    ok('U4b ★★ 护栏：**带台词的句子不被整句删掉**（删了就把人物的话端了）',
       '夜深了' in out_w and '第一轮的追问' not in out_w,
       out_w[:46])

    again, n2 = strip_meta_narration(new)
    ok('U4c ★★ 护栏：剥离**幂等**（再跑一遍删 0 处，不会把好句越删越短）',
       n2 == 0 and again == new, f'第二遍删 {n2} 处')


# ══════════════════════════════════════════════════════════════
#  V  感知/物理自洽：听不见的话不许被听见（2026-10-20 第十三轮）
# ══════════════════════════════════════════════════════════════
def _human_percept_clean() -> bool:
    from crew.prose_flow import percept_issues
    ch = _human_chapters()
    if len(ch) < 12:
        return False
    return all(not percept_issues(t) for _, t in ch)


def _human_percept_detail() -> str:
    from crew.prose_flow import percept_issues
    ch = _human_chapters()
    bad = [(n, percept_issues(t)) for n, t in ch if percept_issues(t)]
    return f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:3]}' if bad else '')


def group_v() -> None:
    """V 组：**读者的感官不许被前后打脸**（R45）。

    ★★★ V1b / V2 是这一组的核心 —— 太容易做成"专杀正确写法"：
      · 真人第 6 部第 3 章：「说了三个字，又断在一个收不住的气音上。**那三个字他没听清**」
        —— 低语 + 没听清，这是**作家处理听不清的正确写法**，判它就是把答案当病；
      · 「没打转」含"打转"（T1b）、「没听清」含"听清"（V2）——
        本项目第三次踩"否定词就长在被查的词里"这个坑，别再踩第四次。
    ⚠ V4 钉的是**安全侧**：判官回话看不懂 / 说没问题 ⇒ 一个字都不许改。
    """
    from crew.prose_flow import (percept_issues, parse_plausibility_verdict,
                                 plausibility_judge_prompt,
                                 plausibility_rewrite_prompt,
                                 parse_line_swaps, swap_lines)

    whisper = (
        '她唇几乎没动。齿间漏出那点怨毒的私语。' + chr(10)
        + '只让那几字像叹息般溜出来。' + chr(10)
        + '他正进门便听见了，原本垂着的手骤然收紧。'
    )
    hits = percept_issues(whisper)
    ok('V1a ★★★ 写成几乎听不见的话、隔几句却被"听见了" ⇒ 判得出来',
       any(h['kind'] == 'whisper' for h in hits) and len(hits) == 1,
       f'{len(hits)} 条：{[h["kind"] for h in hits]}')

    micro = '她站在门边探进半张脸，睫毛上沾着一点廊下的寒气。'
    ok('V1c ★★★ 隔着门/写到睫毛那一层 ⇒ 判得出来（微距 × 距离）',
       any(h['kind'] == 'micro' for h in percept_issues(micro)),
       f"{[h['kind'] for h in percept_issues(micro)]}")

    ok('V1b ★★★ 真人 18 章（samples/zh）**零误报** —— 这条红了就是判据在误伤真人',
       _human_percept_clean(), _human_percept_detail())

    # 成对 ①：低语 + **没听清** ⇒ 那是正确写法，不许报
    ok('V2 ★★★ 成对：写了低语却**没听清** ⇒ **不报**（否定必须先查）',
       not percept_issues(
           '是他的声音，说了三个字，又断在一个收不住的气音上。那三个字他没听清。'),
       '真人第 6 部第 3 章正是这么写的')

    # 成对 ②：没有距离/弱光线索的微距 ⇒ 不许报
    ok('V3 ★★ 成对：**近距离**写微距（没有距离/弱光词）⇒ **不报**',
       not percept_issues('她低下头，睫毛在他眼前颤了颤。'),
       '近距离看得到睫毛是正常的描写')

    # 安全侧：判官回话看不懂 / 说没问题 ⇒ 一律不改稿
    j_yes = ('判定：有问题' + chr(10)
             + '不成立的地方：叶子正进门便听见了，原本垂着的手骤然收紧。')
    j_no = '判定：没问题'
    j_empty = ''
    j_junk = '这一章写得不错。'
    j_noline = ('判定：有问题' + chr(10) + '（判官没抄出句子）')
    v_yes = parse_plausibility_verdict(j_yes)
    ok('V4 ★★★ 成对：判官说**没问题 / 空 / 看不懂** ⇒ **绝不改稿**',
       v_yes.get('bad') is True and len(v_yes.get('lines') or []) == 1
       and parse_plausibility_verdict(j_no).get('bad') is False
       and parse_plausibility_verdict(j_empty).get('bad') is False
       and parse_plausibility_verdict(j_junk).get('bad') is False,
       f"yes={v_yes.get('bad')} no={parse_plausibility_verdict(j_no).get('bad')}")

    ok('V4b ★★★ 判官报了"有问题"却**没抄出原句** ⇒ 也**不改稿**'
       '（没原句就没有可数的事实，改就是猜）',
       parse_plausibility_verdict(j_noline).get('bad') is False,
       f"{parse_plausibility_verdict(j_noline)}")

    jp = plausibility_judge_prompt(whisper)
    ok('V4c ★★ 判官提示词里写清了**什么不算**（雪会化 / 比喻 / 人物错觉）',
       '不算' in jp and '别误报' in jp and '比喻' in jp, f'len={len(jp)}')

    rp = plausibility_rewrite_prompt(whisper, v_yes)
    pairs = parse_line_swaps(
        '原句：他正进门便听见了，原本垂着的手骤然收紧。' + chr(10)
        + '新句：他正进门，那句话没听清，手却先一步攥住了门框。')
    swapped = swap_lines(whisper, pairs)
    ok('V4d ★★ 修复是**定点替换**：只动判官点名的那一句，其余一字不动',
       len(pairs) == 1 and '唇几乎没动' in swapped
       and '只让那几字像叹息般溜出来' in swapped
       and '听见了' not in swapped,
       f'pairs={len(pairs)}')

    ok('V4e ★★ 替换只在**整句完全对得上**时发生（对不上的一律不换）',
       swap_lines(whisper, [('原文里根本没有的那一句', '随便改成的另一句')]) == whisper,
       '换不动就原样')


def group_w() -> None:
    """W 组：**问出去的话不许连着没人接**（R46，2026-10-20）。

    ★★★ 这一组的核心是**口径**，不是抓得多狠：
      真人 18 章**单句悬空率**中位 0.8、最高 1.0 —— "问一句不答"本身根本不是病；
      病的是**连续长度**：真人天花板 2，v18 到 5。阈值 ≥3，零误报。
    ⚠ W1/W3 是成对的：只抓 v18 不放真人靠的是「连续」二字，缺一个都是假判据。
    """
    from crew.prose_flow import (qa_drift_issues, qa_drift_runs,
                                 qa_drift_note, answer_drift_rewrite_prompt,
                                 best_swap_prefix, QA_DRIFT_MIN)

    drift = (
        '驹子探身：“你知道吗？我每天都记日记呢。”' + chr(10)
        + '岛村倒酒：“今晚能陪我到几时？”' + chr(10)
        + '驹子低头：“我写下的那些，你要不要看？”' + chr(10)
        + '岛村晃壶：“这酒……还够喝吗？”' + chr(10)
        + '驹子急了：“日记里的事，你就不想知道吗？”' + chr(10)
        + '岛村拨炭：“火快灭了。”')
    iss = qa_drift_issues(drift)
    ok('W1 ★ 抓得住各说各话（v18 原样的五连问）',
       len(iss) == 1 and iss[0]['n'] >= 3,
       f'检出 {len(iss)} 段，最长 {[x["n"] for x in iss]}')

    ch = _human_chapters()
    bad = [(n, qa_drift_issues(t)) for n, t in ch if qa_drift_issues(t)]
    ok('W2 ★★★ 真人 18 章**零误报**（阈值真照着人量过，不是拍脑袋）',
       len(ch) >= 12 and not bad,
       f'{len(ch)} 章，误报 {len(bad)} 章' + (f'：{bad[:2]}' if bad else ''))

    one = ('驹子看他：“你要不要看？”' + chr(10)
           + '岛村没接这茬：“这酒还够喝吗？”' + chr(10)
           + '驹子笑了：“我就知道你不敢看。”')
    ok('W3 ★★ 单次悬空**不报**（真人 80%–100% 都不直接答 —— 那是留白，不是病）',
       qa_drift_issues(one) == [], f'检出 {len(qa_drift_issues(one))} 段')

    answered = ('驹子看他：“今晚能陪我到几时？”' + chr(10)
                + '岛村想了想：“到亥时罢，酒喝完我就睡。”' + chr(10)
                + '驹子又问：“日记呢，你要不要看？”' + chr(10)
                + '岛村说：“看，拿来。”')
    ok('W4 ★★ 真的答了就**不许报**（共享实词 / 应答词都算接住）',
       qa_drift_issues(answered) == [],
       f'检出 {len(qa_drift_issues(answered))} 段')

    q_echo = ('驹子问：“你说呢，我该不该烧了它？”' + chr(10)
              + '岛村反问：“你说呢？”' + chr(10)
              + '驹子不说话了。')
    ok('W4b ★★ 反问 / 重复上一句也算接住（不许把它算成悬空）',
       qa_drift_issues(q_echo) == [],
       f'检出 {len(qa_drift_issues(q_echo))} 段')

    no_ask = ('岛村说：“火快灭了。”' + chr(10)
              + '驹子说：“酒也凉了。”' + chr(10)
              + '岛村说：“灯也暗了。”' + chr(10)
              + '驹子说：“人也乏了。”')
    ok('W5 ★ 没有**问句**就没有悬空（各说各话的资格只属于问出去的话）',
       qa_drift_issues(no_ask) == [],
       f'检出 {len(qa_drift_issues(no_ask))} 段')

    note = qa_drift_note(drift)
    prompt = answer_drift_rewrite_prompt(drift, note)
    ok('W6 ★★ 修复提示词里带了禁写条款（R44 的教训：不写就会被念进正文）',
       '讲第几次' in prompt and '不写自己怎么安排这场戏' in prompt,
       '禁写条款在' if ('讲第几次' in prompt) else '缺了')
    ok('W7 ★★ 提示词不许逼成"有问必答"（回避与沉默是这场戏的味道，修一处就够）',
       '不许把所有问句都改成有问必答' in prompt, '保留回避的条款在/缺')

    # ★★★ 接线：真挂在生产路径上，且排在"内容收拢"之后、"物理自洽"之前
    #   （先接不上话，再判物理 —— 顺序反了会把刚修好的台词再搅一遍）。
    # ⚠ 2026-10-20 起顺序的**唯一真相**是 `Novelist._check_round_steps()`
    #   （多轮检查里的步骤表），不再是源码里 `self._fix_x(` 的书写先后 ——
    #   照字符串顺序判会在改成多轮之后变成一条假判据（实测：链只剩两步）。
    # [EN] Since R48 the single source of truth for the order is
    # [EN] `Novelist._check_round_steps()`, not the textual order of `self._fix_x(`.
    calls = [f.__name__ for f, _cls in
             __import__('crew.agents', fromlist=['x']).Novelist.__new__(
                 __import__('crew.agents', fromlist=['x']).Novelist)._check_round_steps()]
    ok('W8 ★★★ `_fix_answer_drift` 真接在链上（打转之后、自洽之前）',
       '_fix_answer_drift' in calls
       and calls.index('_fix_answer_drift') > calls.index('_fix_topic_spin')
       and calls.index('_fix_answer_drift') < calls.index('_fix_plausibility'),
       f'链：{calls}')

    # ⚠ 判"在册"必须查 `SPEC` 注册表，**不能**查 `CFG.has` —— 那个只看老用户的
    #   `.env` 里有没有这一行；新加的键 `.env` 还没重生，`has` 永远是 False。
    #   （这一条自己踩过一次：值读得到 1，却在"在册"上判红。）
    _spec = __import__('config').SPEC.get('PROSE_DRIFT_FIX')
    ok('W9 ★ 开关 `PROSE_DRIFT_FIX` 在册且默认开（0 = 只报不修）',
       bool(_spec) and int(_spec.get('default', 0)) == 1
       and CFG.i('PROSE_DRIFT_FIX') == 1,
       f"spec={bool(_spec)} default={(_spec or {}).get('default')} "
       f"val={CFG.i('PROSE_DRIFT_FIX')}")

    # ★★★ W10 组：**改几句**（`best_swap_prefix`）。
    #   实测背景：模型一次给了 4 句改写，全用能把最长连续压到 0，但每句都变成
    #   "半句回答；自己的问题"，四句连排是新的模版腔。所以"改到够"为止，
    #   而不是"全都改"。这三条钉的是**够**与**不贪多**这一对。
    _CH = ('她：“你几时动身？”' + chr(10) + '他：“这炭还旺吗？”' + chr(10)
           + '她：“路上要几日？”' + chr(10) + '他：“窗纸破了么？”' + chr(10)
           + '她：“干粮带够没有？”' + chr(10) + '他：“风停了么？”')
    _P = [('他：“这炭还旺吗？”', '他：“对，旺得很。”'),
          ('他：“窗纸破了么？”', '他：“对，破了。”'),
          ('他：“风停了么？”', '他：“对，停了。”')]
    _new, _used, _max = best_swap_prefix(_CH, _P)
    ok('W10a ★★★ 改到**够**就停（五连问只用了前 2 句，最长连续压到人的天花板以下）',
       _used == 2 and _max < QA_DRIFT_MIN, f'used={_used} max={_max}')
    ok('W10b ★★★ **不贪多**：模型给的第 3 句**没被用上**（多改一句就多一分模版味）',
       '风停了么' in _new, '第三对没动' if '风停了么' in _new else '第三对被改了')
    _CH4 = ('她：“你几时动身？”' + chr(10) + '他：“这炭还旺吗？”' + chr(10)
            + '她：“路上要几日？”' + chr(10) + '他：“窗纸破了么？”')
    _n2, _u2, _m2 = best_swap_prefix(_CH4, _P[:1])
    ok('W10c ★★ 一句就够时**只改一句**（不会顺手动别的）',
       _u2 == 1 and _m2 < QA_DRIFT_MIN, f'used={_u2} max={_m2}')
    _n3, _u3, _m3 = best_swap_prefix(_CH, [('原文里没有的句子', '随便改成另一句')])
    ok('W10d ★★ 一句都对不上 ⇒ 原文返回、`used=0`（坏输入不许改稿）',
       _n3 == _CH and _u3 == 0, f'used={_u3}')


def group_x() -> None:
    """X 组：**重复要看语境**（R43 重做，2026-10-20 用户点名）。

    ★★★ 用户的约束原话：「不是所有重复都有问题，要结合上下文语境进行分析」。
      所以这一组钉的不是"抓得到多少重复"，而是**别一刀切**：
        · 代码只负责**找出候选组**（可算），判官负责**判哪条是手法**（要语境）；
        · 判官点谁删谁，代码**绝不自己动**；
        · 首条永不删、超长的条目不收、额度按台词数比例 —— 三道防"删过头"。
    ⚠ 真人基线（量过）：18 章共 22 个组，**21 个是 2 条，只有 1 个 3 条**，
      而那一个 3 条组是"十五年前"的**证据链**（反复强调同一个时间点）——
      真人小说里"3 条以上"极少，且多半是手法 ⇒ 组数本身不能当判据。
    """
    from crew.prose_flow import (repeat_clusters, repeat_groups_note,
                                 drop_spin_lines, parse_spin_verdict,
                                 spin_judge_prompt, _unit_of)

    go = ('驹子抬头看岛村，轻声说：“你看我，是不是个好人？”' + chr(10)
          + '岛村说：“是啊。”' + chr(10)
          + '驹子语速快：“你说，我是不是个好人？”' + chr(10)
          + '岛村轻缓：“这酒，倒是能让人消磨些时光。”' + chr(10)
          + '驹子又急又期待：“你说，好人是不是都没好报啊？”' + chr(10)
          + '驹子声音哑急：“你倒是说呀，好人是不是都没好报？”' + chr(10)
          + '驹子声音追着：“你倒是说说呀，我算不算好人？”')
    gs = repeat_clusters(go)
    # ⚠ 断言写成"至少有一组 ≥3 且里面确实是那几句追问"，
    #   **不要求**"另有一个 2 条组"：把 5 句同题合成一组本来就是更对的答案，
    #   第一版要求 2 条组 + 3 条组同时存在，聚类一变好反而判红（假红）。
    ok('X1 ★★★ 抓得到**换了说法**的同一件事（字面比对抓不到，这正是打转的病根）',
       any(len(g) >= 3 for g in gs)
       and any('好人' in x for g in gs for x in g),
       f'组条数={[len(g) for g in gs]}')
    ok('X2 ★★★ 组里给的是**最小可删单位**（引导语＋台词），不是整段 —— '
       '拿整段去删会一口气删掉好句子（实测删过「给句准话」）',
       all(len(x) < 80 for g in gs for x in g),
       f'最长 {max((len(x) for g in gs for x in g), default=0)} 字')
    ok('X3 ★★ 组信息递进了判官提示词（判官不必自己在一整章里找）',
       '组 1' in repeat_groups_note(go)
       and '组 1' in spin_judge_prompt(go, []), '')

    # ★★★ X4–X7：**首条永不删**这一组，是全组最关键的安全侧。
    def v_of(line: str, src: str = '') -> dict:
        return parse_spin_verdict(
            '判定：打转' + chr(10) + '那一件事：x' + chr(10) + '逐组：'
            + chr(10) + line, src or go)

    # ⚠ "只有 2 条"的组要用**单独的夹具**：`go` 聚出来的是一个 5 条的大组，
    #   在 5 条组里"删 2"是中间条，即使把"首尾都保"写成公式也删得掉 ⇒
    #   M69 抓不到（实测踩过）。这里必须有一个真的只有 2 条的组。
    # [EN] A two-item group needs its own fixture: in the 5-item `go` cluster,
    # [EN] "删 2" is an interior index and the mutation survives.
    _pair = ('她抬头：“你看我，是不是个好人？”' + chr(10)
             + '她低声：“你说，我是不是个好人？”')
    ok('X4 ★★★ 「组 N：删 M」解析得到**那一条**（不是整组、不是全章）',
       len(v_of('- 组 1：删 2')['drops']) == 1, '')
    ok('X5 ★★★ **第一条永远不删**（判官说删 1 也不删：那是第一次开口）',
       not v_of('- 组 1：删 1', go)['drops']
       and not v_of('- 组 1：删 1', _pair)['drops'], '')
    ok('X6 ★★★ 组**只有 2 条**时允许删第 2 条（把"首尾都保"写成公式，'
       '这种组会一条都删不了 ⇒ 整条修复链静默失效，实测踩过）',
       len(v_of('- 组 1：删 2', _pair)['drops']) == 1, '')
    ok('X7 ★★ 组**≥3 条**时末条不删（最后那次是收束）',
       not v_of('- 组 2：删 3')['drops'], '')
    ok('X8 ★★ 「整组留」⇒ 一条都不删（敷衍式的应答就是这种：'
       '人物反复用同一个短句挡话，那是他的嘴脸）',
       not v_of('- 组 1：整组留')['drops'], '')

    # ★★★ X9–X10：**删过头**的两道闸
    # ⚠ 这两条必须**各自只测自己那道闸**：第一版拿"3 个引语的长条目"测长度闸，
    #   结果被额度闸先拦住了 ⇒ 把长度闸删掉（M70）判据**仍然是绿的**，白测。
    # [EN] Each of these must exercise exactly one guard; otherwise the other guard
    # [EN] hides the mutation and the check is fake.
    _long_narr = '驹子抬头看岛村，轻声说：“你看我，是不是个好人？”' + chr(10)

    def _go_with(extra: str) -> str:
        return go + chr(10) + extra
    # 一句超长但**只有一个引语**的条目 ⇒ 只有长度闸能拦，额度闸拦不到。
    # ⚠ 同段必须还有别的句子：单句成段时会被"段落删空"那道闸拦住，
    #   M70（把长度闸拆掉）就测不红了 —— 第一版就是这样白测的。
    # [EN] The paragraph must contain another sentence, otherwise the "would empty the
    # [EN] paragraph" guard fires first and the length guard is never exercised.
    _one_quote_long = ('他把炭拨了拨，火光照到墙上又退回来，屋子里的热气一层一层地' * 3
                       + '说：“你看我，是不是个好人？”')
    _para = _one_quote_long + '岛村没有答。'
    ok('X9 ★★★ 判官抄的是**段落**（>80 字、只含一句台词）⇒ 不收'
       '（否则一条就删掉半段）',
       len(_one_quote_long) > 80
       and drop_spin_lines(_go_with(_para), [_one_quote_long])
       == _go_with(_para), f'{len(_one_quote_long)} 字')
    # ⚠ 这条走**默认额度**（不显式传 max_quote_drops），才测得到"自动按比例"那一路
    _long = ('甲说：“今天冷。”乙说：“是啊。”丙说：“雪大。”丁说：“嗯。”'
             + chr(10) + '戊说：“风停了。”' + chr(10) + '第五段还有一句。')
    _auto = drop_spin_lines(_long, ['甲说：“今天冷。”', '乙说：“是啊。”',
                                    '丙说：“雪大。”'])
    _q0, _q1 = _long.count('“'), _auto.count('“')
    ok('X10 ★★★ 删掉的台词条数**按额度自动封顶**（不封顶就是一刀切：'
       '实测在 v19 上一口气删掉 8 句台词，把好句子也削了）',
       _q1 == _q0 - 2, f'{_q0} → {_q1}（5 条台词 ⇒ 额度 2）')

    # ⚠ X11 分两半：**不配平**的不删，**配平且不撞别的闸**的照删 ——
    #   只测前半是"永远绿"（因为别的闸也会拦），只测后半是"没测那道闸"。
    #   台词放在段首（前面没有"他说："）才不会撞上"说话人+冒号"那道闸。
    ok('X11 ★★★ 切断台词的 key 不删（删掉片段里引号必须配平）',
       drop_spin_lines(_long, ['甲说：“今天冷']) == _long
       and drop_spin_lines('“今天冷。”她抬起眼。',
                           ['“今天冷。”']) == '她抬起眼。', '')
    ok('X12 ★★★ 判官说**没打转** ⇒ 一字不动',
       not parse_spin_verdict('判定：没打转')['drops']
       and not parse_spin_verdict('判定：没打转')['spin'], '')
    ok('X13 ★★ 判官回话**看不懂** ⇒ 当没打转（宁可漏改，不许改坏）',
       not parse_spin_verdict('嗯，还可以吧')['spin']
       and not parse_spin_verdict('')['spin'], '')

    # ★★★ X14：判定类调用的温度必须是 0。
    #   实测（v19 连跑两次，同一份稿子）默认 0.2 会让判官一次说"打转"、
    #   一次说"没打转" —— 判定不是创作，抖动只会让修不修变得随机。
    _src = inspect.getsource(__import__('crew.agents', fromlist=['x']))
    ok('X14 ★★ 打转判官用 `temperature=0`（判定类调用，抖动 = 修不修看运气）',
       'temperature=0.0' in _src, '')
    ok('X15 ★★★ 删除之后要**复检 R46**（删掉一句"答话"会让原本接上的问答变悬空 —— '
       '两条规则同在一条链上，谁都不能把谁搞坏）',
       'after_drift > before_drift' in _src, '')
    ok('X16 ★★★ 真人 18 章**代码一件都不删**（判官不说话就绝不动手）',
       all(drop_spin_lines(_h, []) == _h for _h in ('甲乙丙。', go)) , '')


def _human_flat_hits() -> int:
    """`flat_span_issues` 在真人 18 章上命中几段（**必须是 0**，否则是专杀真人的判据）。"""
    from pathlib import Path
    from crew.prose_flow import flat_span_issues
    n = 0
    base = Path(__file__).resolve().parent.parent / 'samples' / 'zh'
    for d in sorted(base.iterdir()):
        body = d / '正文'
        if not (d.is_dir() and body.exists()):
            continue
        for f in sorted(body.glob('*.md')):
            try:
                n += len(flat_span_issues(f.read_text(encoding='utf-8')))
            except Exception:                                    # noqa: BLE001
                continue
    return n


def _prefers_day_novel() -> bool:
    """`checkup_before_bind` 里是否**先**取 `_day_novel_of`、**才**退回 `_tidy_for_novel`。

    看语法树：找 `src = <调用>` 那一次赋值，确认调用的是 `_day_novel_of`；
    再确认 `_tidy_for_novel` 的调用行号比它大（是兜底，不是主路）。
    [EN] `src` is assigned from `_day_novel_of` first, with `_tidy_for_novel` only as a
    [EN] later fallback (higher line number).
    """
    import ast as _ast
    import textwrap
    nv = __import__('export.novel_version', fromlist=['x'])
    try:
        tree = _ast.parse(textwrap.dedent(
            inspect.getsource(nv.checkup_before_bind)))
    except Exception:                                            # noqa: BLE001
        return False
    main_line = None
    fallback_line = None
    for n in _ast.walk(tree):
        if not (isinstance(n, _ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], _ast.Name)
                and n.targets[0].id == 'src'):
            continue
        v = n.value
        name = (v.func.attr if isinstance(v, _ast.Call) and isinstance(v.func, _ast.Attribute)
                else getattr(getattr(v, 'func', None), 'id', '') if isinstance(v, _ast.Call)
                else '')
        if name == '_day_novel_of':
            main_line = n.lineno
        elif name == '_tidy_for_novel' and fallback_line is None:
            fallback_line = n.lineno
    return main_line is not None and (fallback_line is None
                                      or fallback_line > main_line)


def group_y() -> None:
    """Y 组：**多轮检查**（R48）与**道具循环**（R47）—— 2026-10-20 用户点名。

    用户原话：「我希望一开始写小说和最后导出的时候都可以进行几轮的问题检查
    也修复，把常见的问题都修复掉」+「继续修复道具循环」。
    """

    from crew.prose_flow import (prose_issue_count, issue_total, checkup_report,
                                 prop_cycle_issues, prop_cycle_note,
                                 prop_cycle_rewrite_prompt, PROP_CYCLE_MIN)
    import crew.agents as A

    # ⚠ 判"没碰凭据稿"要看**调用**，不能看"源码里有没有这个字符串" ——
    #   `checkup_before_bind` 的 docstring 里正写着「`write_raw_manuscript` 一字不动」，
    #   按字符串判会永远红（第一版就是这样假红的）。
    # [EN] Check the **call graph**, not the presence of the name: the docstring of
    # [EN] `checkup_before_bind` literally mentions `write_raw_manuscript`.
    _nv = __import__('export.novel_version', fromlist=['x'])
    _calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', '')
              for n in ast.walk(ast.parse(inspect.getsource(_nv.checkup_before_bind)))
              if isinstance(n, ast.Call)}
    ok('Y16 ★★★ 导出关口存在，且只改「小说版本」—— '
       '**「小说原文」是「一字未改」的凭据稿，一个字符都不许动**',
       hasattr(_nv, 'checkup_before_bind')
       and 'write_raw_manuscript' not in _calls, f'调用了：{sorted(_calls)[:6]}')
    ok('Y17 ★★ 两个关口用的是**同一份实现**（导出调 `crew.agents.prose_checkup`，'
       '不另写一份规则）——「同一件事两处实现」是万恶之源',
       hasattr(A, 'prose_checkup')
       and 'A.prose_checkup' in inspect.getsource(
           __import__('export.novel_version', fromlist=['x']).checkup_before_bind), '')
    ok('Y18 ★★★ **`_fix_*` 全部无状态**（模块级入口靠 `__new__` 跳过构造，'
       '谁加了实例状态这里就会炸掉 —— 这条判据把前提钉住）',
       _fix_stateless(), f'用到 self 的属性：{_fix_self_attrs() or "无"}')
    ok('Y19 ★★ 开关 `PROSE_CHECK_ROUNDS` 在册且默认 >1（设 1 = 退回老样子）',
       int(SPEC.get('PROSE_CHECK_ROUNDS', {}).get('default', 1)) > 1, '')
    ok('Y20 ★★ 开关 `PROSE_PROP_FIX` 与 `EXPORT_FINAL_CHECK` 都在册且默认开',
       bool(SPEC.get('PROSE_PROP_FIX')) and bool(SPEC.get('EXPORT_FINAL_CHECK')), '')

    # ── R47 道具循环：口径与安全带 ──────────────────────────
    # ⚠ 夹具要写成**真跑那种形态**：每句都带上那件东西的名字。
    #   "又凉了"单独一句是判不出东西的（状态词不带主语），真人也不会那样写 ——
    #   第一版夹具就是这么写的，结果一段都报不出来（假红）。
    # [EN] The fixture must look like real output: each line names the object.
    cyc = ('他把粗陶茶壶端来：“喝口热的。”' + chr(10)
           + '她抿了一口，把茶杯推回去：“茶凉了。”' + chr(10)
           + '他提起茶壶又倒了半杯：“我给你添上。”' + chr(10)
           + '她按住杯子：“这杯茶也凉了。”' + chr(10)
           + '他把茶壶往火边挪：“再添一回热的。”' + chr(10)
           + '她没动：“茶凉透了吧。”')
    iss = prop_cycle_issues(cyc)
    ok('Y1 ★★★ 抓得到**道具循环**（茶凉→续上→又凉→再续，台词每句都不同）',
       bool(iss) and iss[0]['n'] >= PROP_CYCLE_MIN,
       f"{[(x['cls'], x['n']) for x in iss]}")
    ok('Y2 ★★★ 阈值是量出来的：真人 18 章「最大复位」**中位 0、最大 0**，'
       '真跑 v16/v19/v20 是 4 ⇒ 取 3 在真人上零误报',
       PROP_CYCLE_MIN == 3, f'阈值={PROP_CYCLE_MIN}')
    ok('Y3 ★★★ 成对：**道具只是被提到**不算循环（火钵出现 13 次也不报）',
       not prop_cycle_issues('火钵里的炭暗红。他靠着火钵。火钵边搁着壶。'
                             '火光映在墙上。他看火钵。'),
       '无补给/消耗动作 ⇒ 0 段')
    # ⚠ Y4 的夹具必须**真的能触发消耗正则**（`空着`），而且**不带任何东西名** ——
    #   第一版写的是"没有冰""没有对应"，那些根本不匹配消耗正则，
    #   于是把"必须贴着东西"那道闸拆掉之后仍然一段都不报 ⇒ M74 测不红（白测）。
    # [EN] The fixture must actually fire the consume regex while naming nothing,
    # [EN] otherwise removing the object anchor changes nothing and M74 survives.
    ok('Y4 ★★★ 成对：**"没有""空着"这类词单独不算消耗**（真人科幻那章的误报：'
       '表格里的「没有」「空着」被算成 11 次消耗）',
       not prop_cycle_issues('最后一格空着。' + chr(10) + '第二格也空着。'
                             + chr(10) + '第三格空着没填。' + chr(10)
                             + '他把表收起来。'), '无器皿/可消耗物 ⇒ 0 段')
    ok('Y5 ★★ 提示词把「哪件东西在循环 + 涉及哪几句」递过去了',
       '茶' in prop_cycle_note(cyc) and '茶' in prop_cycle_rewrite_prompt(cyc, '')[:4000], '')
    _pp = prop_cycle_rewrite_prompt(cyc, prop_cycle_note(cyc))
    ok('Y6 ★★★ 明写**不删戏、只换动作**（删句子会把一场戏删成两个人干坐着）',
       '不删戏' in _pp and '换成**另一件事**' in _pp, '')
    ok('Y7 ★★★ 而且明写**不许换同族动作**（又喝了/又添了/又换了 = 换汤不换药）',
       '同族动作' in _pp and '换汤不换药' in _pp, '')
    ok('Y8 ★★ 修复提示词带禁写条款（R44 的教训）',
       '讲第几次' in _pp, '')

    # ── R48 多轮：计数表 ────────────────────────────────────
    cnt = prose_issue_count(cyc)
    ok('Y9 ★★★ 计数表**只收确定性检测器**（判官类会抖动，拿它当收敛判据会被噪声带着跑）',
       set(cnt) == {'憋气段', '平铺段', '重复', '拥挤段', '元叙述', '感知自洽',
                    '问答悬空', '道具循环', '对话标签', '套话'}, f'{sorted(cnt)}')
    # ★★ 2026-10-28：加了「对话标签」这一类（副词盖章式标签，纯正则、零成本）。
    #   它进这张表的前提就是**确定性**：`dialogue_tag_spans` 只认一张闭集副词表，
    #   不调模型、不抖动 ⇒ 可以当收敛判据用。**判官类照旧一个都不许进来。**
    # ★★★ Y9b（2026-10-20 **第三次**修正，这一条记的是我量错过两次的经过）：
    #   用户点名「每一句都恨不得交代一个事情」。我先后量错两次：
    #   ① 判"整段有没有 ≥25 字的句子"（太平）—— 真人中位 3 / 最大 9、真跑 0，
    #      真人比真跑还"平"，这个口径**分不开**，拿它改稿只会打健康段落（2→3→6）；
    #   ② 于是又矫枉过正地宣布"太碎不是病"—— 可 v23 那段读起来明明白白是病。
    #   **真正的区分点是"句子有没有分句"**：
    #     真人再碎也保持 逗号/句 ≥ **0.25**（「三年前二月，宣阳坊。」是 1.0）；
    #     v23 那种「岛村倚着窗框。驹子坐在火钵旁。」是 **0.06**。
    # [EN] Measured wrongly twice. The real signal is **absence of internal clauses**:
    # [EN] human prose stays at >=0.25 commas per sentence even when choppy (0.06 in the
    # [EN] broken run). Threshold 0.2, and 0 hits across 18 human chapters.
    from crew.prose_flow import (long_span_issues, flat_span_issues,
                                 FLAT_CLAUSE_RATIO)
    ok('Y9b ★★★ 「太碎」的可数形态是**句子没有分句**，不是"句子短"'
       '（判"有没有长句"在真人上中位 3 / 最大 9，分不开；判"逗号/句"才分得开）',
       flat_span_issues('岛村倚着窗框。驹子坐在火钵旁。'
                        '炭火映着她半边脸颊。叶子端着壶出去。'
                        '在纸门前停下脚步。将壶放在门外廊下。')
       and not flat_span_issues('三年前二月，宣阳坊。三年前七月，亲仁坊。'
                                '两年前五月，平康坊。两年前九月，安仁坊。'),
       f'阈值 {FLAT_CLAUSE_RATIO}：紧句判、枚举句不判')
    ok('Y21 ★★★ 而且这个阈值**在真人 18 章上一个都不命中**（否则就是专杀真人）',
       _human_flat_hits() == 0, f'真人命中 {_human_flat_hits()} 段')
    # ★★★ Y9b3（2026-10-20 实测）：**两个方向都必须说"长句只留一句"**。
    #   实测 v23：修"太碎"之后憋气段 0→2 —— 提示词只说了"长短掺着来"，
    #   模型写成 2 长 1 短就判中"长句过半"。病只是从一头换到另一头。
    # [EN] Both directions must cap long sentences at one: measured, fixing "choppy"
    # [EN] pushed the run to 2 "too long" paragraphs because "mix lengths" was too vague.
    _p_flat = __import__('crew.prose_flow', fromlist=['x']).rewrite_prompt('x。', too_long=False)
    _p_long = __import__('crew.prose_flow', fromlist=['x']).rewrite_prompt('x。', too_long=True)
    # ⚠ 不能写成 `A and B`（两个方向各一条）：只编一个方向时，另一个还满足 ⇒ 判据仍然绿，
    #   变成假判据（M91 抓不到，实测）。方向各自一条，一条判据只钉一处。
    # [EN] Split per direction: an `A and B` check stays green when only one side mutates,
    # [EN] so the mutation survives (M91).
    ok('Y22 ★★★ **太碎**方向的重写明写「长句只留一句」'
       '（只写"长短掺着来"的话，修完太碎就变成太长 —— 实测 0→2）',
       '长句只留一句' in _p_flat and '别把病从' in _p_flat, '')
    ok('Y23 ★★★ **太长**方向的重写明写「长句最多一句」'
       '（拆完不能整段都是短句，也不能剩两句长的）',
       '长句最多一句' in _p_long and '别把病从' in _p_long, '')
    # ★★★ Y25（2026-10-20 **第二次**修正，这一条也记着我量错的经过）：
    #   初版判"英文引号就是硬伤"，无条件把所有 `"` 换成 `“”`。
    #   **一量真人才发现**：samples/zh 那 18 章**全部用 ASCII `"`，中文引号 0 个**
    #   —— 那是正常写法；而 `_QUOTED` 两种都认，下游一切照常。
    #   真正的病是**同一篇里混着用**（v23：16 个 `"` + 10 个 `“”`）。
    #   ⇒ 只在混用时统一；单一 ASCII（真人同款）/ 单一中文 一个字符不动。
    # [EN] The first version treated ASCII quotes as a defect and rewrote all of them.
    # [EN] Measuring the human samples showed they use ASCII exclusively (zero Chinese),
    # [EN] so a single style is fine. Only **mixing** both in one piece is a defect.
    _pq = __import__('crew.prose_flow', fromlist=['x'])
    _mixed = '她低声' + '"' + '你……你觉得我是好人吗？' + '"' + '又说“算了。”'
    _zh = _pq.normalize_quotes(_mixed)
    ok('Y25 ★★★ 引号**混用**时统一成中文引号（v23：16 个 `"` + 10 个 `“”`）',
       _zh.count('"') == 0 and _zh.count('“') >= 2 and _zh.count('”') >= 2,
       _zh)
    ok('Y25a ★★★ 成对：**单一 ASCII 不动**（真人 18 章全是 ASCII 引号，'
       '那是正常写法 —— 这条初版写成"英文引号即病"，差点专杀真人）',
       _pq.normalize_quotes('她低声"你觉得我是好人吗？"') == '她低声"你觉得我是好人吗？"', '')
    # ⚠ 夹具必须**混用**（同时有 `"` 和 `“`）才走得到奇偶判断 ——
    #   单一 ASCII 会 early return（Y25a），奇数个也"原样不动"，
    #   判据照样绿但测的不是那道闸（第一版就是这么假绿的）。
    # [EN] The fixture must **mix** both styles, or the early return short-circuits the
    # [EN] parity test and this check passes without touching it.
    _Q = chr(34)
    _odd = ('她' + _Q + '甲' + _Q + '又说' + _Q + '乙。' + '丙“算了')
    ok('Y25b ★★★ 成对：**奇数个引号的行原样不动**（台词跨行时猜左右会把配对搞反）',
       _pq.normalize_quotes(_odd) == _odd
       and _odd.count(_Q) == 3 and '“' in _odd, f'{_odd.count(_Q)} 个 ASCII + 1 个中文')
    ok('Y25c ★★ 幂等：已经是中文引号的再跑一遍**一个字符都不变**',
       _pq.normalize_quotes(_zh) == _zh and _pq.normalize_quotes('“问。”') == '“问。”', '')
    # ⚠ 判"接了生产路径"要看**调用**：`novel_rules` 里 Y25 这类只在测工具函数，
    #   把 `_checkup` 那行删掉它照样绿（第一版就漏了这条）。
    # [EN] Check the call site: the tool-function checks stay green even if `_checkup`
    # [EN] stops calling it (caught by M95 in the first run).
    ok('Y25d ★★★ 而且 `_checkup` **真的调了**它（两个关口都覆盖，'
       '否则整篇英文引号没人管）',
       bool({'normalize_quotes'}
            & (_calls_of(A.Novelist._checkup)
               | _calls_of(A.Novelist._checkup_reflexion)
               | _calls_of(A.Novelist._checkup_legacy))), '')
    # ★★★ Y9d（2026-10-20 实测）：**台词收尾就是句子边界**。
    #   `_strip_quotes` 把台词连里面的句号一起蒙成空格 ⇒ 这种极常见的写法整段并成一句：
    #     他翻书：“书名忘了。”（14 字）门外叶子声音清亮：“您真要待十天吗？”（9 字）……
    #   蒙完中间一个句末都没有 ⇒ 61 字"长句"，其实是多人对话连排，读者一点不憋气。
    #   ⇒ `_bare_with_ends` 在台词收尾处留一个 `。`（等长替换，回贴位置不变）。
    #   实测：真人 18 章「太长」中位 0 / 最大 1 **改前改后一样**（零误伤）；
    #        真跑 v19 4→1、v21 2→0、v22 2→0。
    # [EN] A closing quote is a sentence boundary; masking it as a blank merged dialogue
    # [EN] runs into one 61-char "long sentence". Human distribution unchanged, real runs fixed.
    _multi_talk = ('他低头翻了翻膝头那本破旧洋装书：“书嘛，还是那些。”'
                   '门外叶子声音清亮：“先生，您真的要在这里待上十天吗？”'
                   '岛村转向纸门：“嗯，待上十天，也没别的事。”')
    _lens = [x[2] for x in __import__('crew.prose_flow', fromlist=['x'])
             ._sentences(_multi_talk)]
    ok('Y9d ★★★ **台词收尾算句子边界**（不这么算，多人对话连排会并成一句 61 字的'
       '"长句"，然后去重写一段本来没问题的对话）',
       max(_lens) < 20 and len(_lens) >= 3,
       f'切出 {len(_lens)} 句，最长 {max(_lens)} 字')
    # ★★★ Y9e：**「太长」的判据在真人身上零影响**，这是它敢动的唯一理由。
    #   量的是"改后的 `_sentences` 会不会把真人判成更多毛病"。
    ok('Y9e ★★★ 成对：真人那种"长短错落"的段落**仍然不判**'
       '（不能为了修真跑的误报，把真人判成有病）',
       not long_span_issues(
           '更鼓一声一声。驹子身子往前倾。手无意识拨弄火钵里的炭。'
           '岛村停了停，把杯子往膝头挪了挪，像是要想清楚该怎么说才开口。'
           '她起身，将酒壶从门边拿至火钵旁放下，壶底与榻榻米轻碰了一下。'
           '岛村看着她，慢慢地说：“我这次打算待上十天。”'),
       '真人节奏 ⇒ 不判')
    # ★★★ Y9c：**生产路径**（`_fix_flat_paragraphs`）必须真的用 `long_span_issues`。
    #   Y9b 只测了那个函数自己的行为 —— 代码里还留着 `list_like_spans` 的调用，
    #   把生产路径换回去，Y9b 照样绿（M83 抓不到，实测）。
    #   ⚠ 判"调用图"：`_fix_flat_paragraphs` 里不能再出现 `list_like_spans(` 的**调用**。
    # [EN] The production path must actually call `long_span_issues`; Y9b alone only tests
    # [EN] the helper, so swapping the call back survived (M83, measured).
    _fa = __import__('crew.agents', fromlist=['x'])
    _fix_calls = _calls_of(_fa.Novelist._fix_flat_paragraphs)
    ok('Y9c ★★★ 生产路径真的调 `long_span_issues`（不能只在库里备着，'
       '`_fix_flat_paragraphs` 里还留着 `list_like_spans` 的调用）',
       'long_span_issues' in _fix_calls and 'list_like_spans' not in _fix_calls,
       f'调用了：{sorted(_fix_calls)[:10]}')
    ok('Y24 ★★★ **两类都要修**：`_fix_flat_paragraphs` 同时调 `long_span_issues` 与 '
       '`flat_span_issues`（只修"太长"的话，v23 那种整段短句没人管）',
       'long_span_issues' in _fix_calls and 'flat_span_issues' in _fix_calls, '')
    ok('Y10 ★★ 计数表认得出毛病（这段有一处道具循环）',
       cnt.get('道具循环', 0) >= 1, f"道具循环={cnt.get('道具循环')}")
    ok('Y11 ★★ 空文本 ⇒ 0（不能因为空串判"清干净了"就当成修好了）',
       issue_total(prose_issue_count('')) == 0
       and prose_issue_count('') == {}, '')
    ok('Y12 ★ 报告能说清每类变了几处（进日志用）',
       '→' in checkup_report({'道具循环': 2}, {'道具循环': 0}), '')

    # ── R48：两个关口都真接上了 ─────────────────────────────
    _src = inspect.getsource(A.Novelist)
    ok('Y13 ★★★ 写小说时走的是**多轮**（`_transcribe_once` 以 `_checkup` 收尾，'
       '不再是七个 `_fix_*` 串一遍就走）',
       '_checkup(prose' in _src and 'return await self._fix_meta_narration(prose)' not in _src, '')
    _steps = A.Novelist.__new__(A.Novelist)._check_round_steps()
    ok('Y14 ★★★ 一轮里的步骤**排过序**：删（打转）→ 改内容 → 排版 → '
       '元叙述剥离**必须最后**（任何重写都可能再添一句）',
       [f.__name__ for f, _c in _steps][-1] == '_fix_meta_narration', '')
    # ★★★ Y14b（2026-10-20 实测后补）：每一步都要报出**它负责哪一类** ——
    #   没有这张对照表，多轮只能"八步全重跑"，实测 `平铺段 2 → 3 → 6`（越改越差）。
    # [EN] Every step must declare the class it owns; without it each round re-runs all
    # [EN] eight steps and `_fix_flat_paragraphs` re-judges its own rewrite (2 -> 3 -> 6).
    ok('Y14b ★★★ 每一步都报出**它负责哪一类**（否则多轮只能八步全重跑 ⇒ '
       '平铺段会 2→3→6 越改越差）',
       all(isinstance(c, str) and c for _f, c in _steps)
       and '平铺段' in [c for _f, c in _steps], f'{[c for _f, c in _steps]}')
    # ★★★ Y14c：**从第 2 轮起要跳步**，而且"上一轮把某类改多了"的那一步必须跳。
    #   实测 v21：第 2 轮八步全重跑，平铺段 3 → 6 —— 在**把稿子改坏**。
    #   ⚠ 测的是纯函数 `_steps_to_run` 的**行为**，不是源码字符串（字符串判据是假判据）。
    # [EN] From round 2 on, skip steps whose class is clean or which inflated it last
    # [EN] round. Tested as behaviour of the pure helper, not as source text.
    _o = A.Novelist.__new__(A.Novelist)
    _r1 = [c for _f, c in _o._steps_to_run(1, {'平铺段': 2, '拥挤段': 1}, set())]
    _r2 = [c for _f, c in _o._steps_to_run(
        2, {'平铺段': 0, '拥挤段': 2, '重复': 1}, {'拥挤段'})]
    ok('Y14c ★★★ 第 2 轮起**只跑还有指望的步骤**：该类已经是 0 ⇒ 跳过；'
       '该类上一轮被改多了 ⇒ 也跳过；元叙述剥离**永不跳**',
       len(_r1) == len(_steps) and '平铺段' not in _r2
       and '拥挤段' not in _r2 and '重复' in _r2 and '元叙述' in _r2,
       f'第1轮 {len(_r1)} 步 / 第2轮 {_r2}')
    # ★★★ Y15（2026-10-20 作者：「成本可以接受 以质量优先」之后放宽过）：
    #   止损是"**连续几轮**没变少才停"，不是"一轮就停" ——
    #   一轮没进展可能只是模型抖动，同一句下一轮换个说法就通了。
    #   判据看**语法结构**（AST），不看字符串：把 `flat >= patience` 换成 `False`
    #   之后名字还在，按字符串判是假判据。
    # [EN] The brake is "no progress for N consecutive rounds", not "one flat round".
    # [EN] Checked on the syntax tree: a substring test survives `if False:`.
    ok('Y15 ★★★ 两条止损都在：**连续几轮没进展才停**（一轮没变少可能只是抖动）'
       '+ **轮数封顶**',
       _has_patience_guard()
       and "CFG.i('PROSE_CHECK_ROUNDS')" in _src, '')
    ok('Y15c ★★ 轮数上限**按质量优先调过**（≥5，作者 2026-10-20：「成本可以接受」）',
       int(SPEC.get('PROSE_CHECK_ROUNDS', {}).get('default', 1)) >= 5,
       f"rounds={SPEC.get('PROSE_CHECK_ROUNDS', {}).get('default')}")
    ok('Y15d ★★ 「连续几轮」这个数**在册可调**（`PROSE_CHECK_PATIENCE`，设 1 = 老规矩）',
       int(SPEC.get('PROSE_CHECK_PATIENCE', {}).get('default', 0)) >= 1, '')
    # ★★★ Y15b（2026-10-20 实测补的）：**保留总数最小的那一版**。
    #   实测 v20：某一轮修好两处、却把"平铺段"从 2 涨到 3 ——
    #   只看"最后一轮"就会把更差的稿子交出去。
    # [EN] Keep the version with the smallest total: a round can inflate a class
    # [EN] (measured: flat paragraphs 2 -> 3), so "whatever the last round did" is unsafe.
    # ⚠ Y15b 必须看**语法结构**，不能看字符串：第一版写的是
    #   `'best_total' in _src`，把比较整个换成 `if False:` 之后
    #   字符串还在、判据仍然绿 ⇒ 假判据（M80 抓不到，实测）。
    #   ⇒ 要求 `_checkup` 里真的有一次 `X < Y` 的比较，且 `best_text` 被赋值。
    # [EN] Check the syntax tree, not the text: with `if False:` the names still occur,
    # [EN] so a substring test stays green (M80 survived, measured).
    ok('Y15b ★★★ **保留最好的一版**（某一轮可能修好两处、同时把另一类改差；'
       '只看最后一轮就会交出更差的稿子）',
       _has_best_guard(), '')
    # ★★★ Y16b（实测踩到的硬伤）：整理稿开头是 `# 当天故事` + 引用块，那是**版式**。
    #   一起交给"合并平铺段"会被吞掉，实测一整行 `# 当天故事` 消失。
    #   导出关口必须先切头、只检查 `## ` 之后的正文。
    # ⚠ 判据要查**有没有真调用** `_split_md_header`（ast.Call），
    #   而不是查"这个函数在不在" —— 变异把调用换成常量之后，
    #   函数还在、判据仍然绿（M81 抓不到，实测）。
    # [EN] The file header is layout, not prose. Feeding it to the merge step swallowed
    # [EN] the `# title` line entirely (measured). The check must look for a real **call**
    # [EN] to `_split_md_header`, not for the function's existence.
    _nv = __import__('export.novel_version', fromlist=['x'])
    ok('Y16b ★★★ 导出关口**先切掉文件头**再检查（否则「# 当天故事」会被并进正文然后消失）',
       'write_raw_manuscript' not in _nv_calls()
       and '_split_md_header' in _nv_calls(), f'调用了：{sorted(_nv_calls())[:8]}')
    _sh = getattr(_nv, '_split_md_header', None)
    _doc = ('# 当天故事' + chr(10) + chr(10) + '> 说明。' + chr(10) + chr(10)
            + '## 第 1 天' + chr(10) + chr(10) + '正文在这里。')
    _h, _b = _sh(_doc) if _sh else ('', _doc)
    ok('Y16c ★★ 切头的**分界线**也真的分对了（头含书名与说明、正文从 `## ` 起）',
       bool(_sh) and _h.startswith('# 当天故事') and _b.startswith('## 第 1 天')
       and '说明' in _h and '正文在这里' in _b, f'头 {len(_h)} 字 / 正文 {len(_b)} 字')
    # ★★★ Y16d（2026-10-20 修的大坑）：**要检查的是"真正会被装订的那一份"**。
    #   `read_day` 读的是 `每天的生活/第N天.md` —— **剧本呈现层**（场景标记、动作标注）；
    #   而 `render_manuscript` 装订时优先用**当天故事的整理稿**（`_day_novel_of`）。
    #   原来关口直接用剧本检查 ⇒ ① 在剧本上量小说毛病（实测 v22：剧本 2 处"重复"、
    #   整理稿 0 处，那两个是剧本格式的固有特征，当然修不动）；
    #   ② 更致命：`day_bodies` 会**完全替换**正文 ⇒ 真改了就会把剧本装订进小说版本。
    # [EN] Check the text that will actually be bound. `read_day` returns the screenplay
    # [EN] layer while binding prefers the edited daily story -- measuring the screenplay
    # [EN] reported 2 repeats where the draft had none, and `day_bodies` **replaces** the
    # [EN] body, so a real edit would have bound the screenplay into the novel version.
    # ⚠ 2026-10-26：这一条原来只认 `read_day`。上一轮修"导出读错文件"时，
    #   那条路改成了 `read_day_full`（json 优先、同一渲染器）—— 于是判据因为**改了个名字**变红，
    #   而"检查的是不是真正要装订的那一份"一个字都没变。
    #   ⇒ 两个名字都认（口径不变：必须是"整理稿优先、剧本兜底"那一路）。
    # [EN] ⚠ 2026-10-26: this used to accept only `read_day`. When the "export read the wrong
    # [EN] file" bug was fixed, that path became `read_day_full` -- so the criterion went red
    # [EN] purely because of a rename, while "is it checking the copy that actually gets bound"
    # [EN] had not changed at all. Both names are accepted; the rule itself is unchanged.
    _reads = _nv_calls()
    ok('Y16d ★★★ 导出关口检查的是**真正要装订的那一份**（`_day_novel_of` 的整理稿），'
       '不是剧本层 —— 剧本上量小说毛病会量出格式特征，而且改了就装订错',
       '_day_novel_of' in _reads and bool(_reads & {'read_day', 'read_day_full'}), '')
    # ⚠ Y16e 必须测**赋值**，不能写 `'xx' or True`（第一版就是那样 —— 永远绿，假判据）。
    #   要求：存在 `src = _day_novel_of(...)` 这一次赋值（先取整理稿），
    #   并且 `_tidy_for_novel` 在它**之后**才出现（取不到才退回剧本）。
    # [EN] Test the assignment, not a tautology: `src = _day_novel_of(...)` must exist, with
    # [EN] `_tidy_for_novel` only as the later fallback.
    ok('Y16e ★★★ 而且**真的用上了**那份文本（先取整理稿、取不到才退回剧本）',
       _prefers_day_novel(), f'{"src = _day_novel_of(...) 存在" if _prefers_day_novel() else "没找到"}')
def _fix_self_attrs() -> set:
    """`_fix_*` 系列里出现的 `self.xxx` 属性名（白名单之外的要报警）。"""
    import ast as _ast
    src = inspect.getsource(__import__('crew.agents', fromlist=['x']))
    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ClassDef) and node.name == 'Novelist':
            used: set = set()
            for m in node.body:
                if isinstance(m, (_ast.FunctionDef, _ast.AsyncFunctionDef)) \
                        and m.name.startswith('_fix'):
                    for x in _ast.walk(m):
                        if isinstance(x, _ast.Attribute) \
                                and isinstance(x.value, _ast.Name) \
                                and x.value.id == 'self':
                            used.add(x.attr)
            return used - {'_cast_names'}
    return {'__class__not_found__'}


def _fix_stateless() -> bool:
    return not _fix_self_attrs()


def _multi_src(*fns) -> list[str]:
    """取若干函数的源码（去重、去空）。

    ★ 2026-10-20：多轮修稿的实现拆成两条路径 ——
      `_checkup_reflexion`（Reflexion：确定性验收 + archive）与
      `_checkup_legacy`（旧路径，保留可回退）。
      判据要问的是"**这件事有没有人做**"，不是"它在哪个函数里"，
      所以两处源码合起来看：任一处满足就算成立。
    """
    import inspect
    import textwrap
    out: list[str] = []
    for fn in fns:
        try:
            src = textwrap.dedent(inspect.getsource(fn))
        except Exception:                                        # noqa: BLE001
            continue
        if src.strip() and src not in out:
            out.append(src)
    return out


def _checkup_sources() -> list[str]:
    """两条修稿路径 + 反思引擎的源码。"""
    try:
        A = __import__('crew.agents', fromlist=['x'])
        RX = __import__('crew.reflexion', fromlist=['x'])
        return _multi_src(A.Novelist._checkup_legacy,
                          A.Novelist._checkup_reflexion,
                          RX.reflect)
    except Exception:                                            # noqa: BLE001
        return []


def _has_patience_guard() -> bool:
    """`_checkup` 里有没有"连续没进展才停"那一段（看语法树，不看字符串）。

    要求：存在 `flat >= patience` 形式的**比较**，且 `flat` 会被累加/清零。
    [EN] Requires a real `flat >= patience` comparison and an assignment to `flat`.
    """
    import ast as _ast
    for src in _checkup_sources():
        try:
            tree = _ast.parse(src)
        except SyntaxError:                                      # noqa: BLE001
            continue
        has_cmp = False
        for n in _ast.walk(tree):
            if isinstance(n, _ast.Compare) and any(
                    isinstance(o, _ast.GtE) for o in n.ops):
                names = {x.id for x in _ast.walk(n) if isinstance(x, _ast.Name)}
                if {'flat', 'patience'} <= names:
                    has_cmp = True
        has_assign = any(isinstance(n, _ast.Assign)
                         and any(isinstance(t, _ast.Name) and t.id == 'flat'
                                 for t in n.targets)
                         for n in _ast.walk(tree))
        if has_cmp and has_assign:
            return True
    return False


def _has_best_guard() -> bool:
    """`_checkup` 里有没有"比出更小就记下来"那一段（看语法树，不看字符串）。

    要求两件事**同时成立**：
      ① 有一个 `X < Y` 形式的比较（不是常量 `False`）；
      ② `best_text` 被赋过值。
    [EN] Both must hold: a real `<` comparison and an assignment to `best_text`.
    """
    for src in _checkup_sources():
        if _best_guard_in(src):
            return True
    return False


def _best_guard_in(src: str) -> bool:
    """单份源码里有没有"留最优"的实现（两种形态都认）。

    ① 旧形态：`X < best_total` 的比较 + 给 `best_text` 赋值；
    ② 新形态（Reflexion）：调 `better(...)` 且把结果写进 `best`。
       ★ 这一条比"存在某个 `<`"结实：它认的是"按 better 排序取最小"。
    """
    import ast as _ast
    try:
        tree = _ast.parse(src)
    except SyntaxError:                                          # noqa: BLE001
        return False
    calls_better = False
    for n in _ast.walk(tree):
        if isinstance(n, _ast.Call):
            fn = n.func
            if (getattr(fn, 'attr', '') or getattr(fn, 'id', '')) == 'better':
                calls_better = True
    assigns_best = any(
        isinstance(n, _ast.Assign)
        and any(isinstance(t, _ast.Name) and t.id == 'best' for t in n.targets)
        for n in _ast.walk(tree))
    if calls_better and assigns_best:
        return True
    tree2 = tree
    # ⚠ 必须**精确到与 `best_total` 比较**：`_checkup` 里还有别的 `<` / `>=`
    #   （`i >= limit`、`after_total >= before_total`）——
    #   只要求"存在某个 `<`"，把 `after_total < best_total` 改掉之后仍然绿
    #   （M80 抓不到，实测）。所以两边名字都要对上。
    # [EN] Must match the **exact** comparison against `best_total`; other `<`/`>=`
    # [EN] comparisons exist in the same function and would keep the check green (M80).
    has_cmp = False
    for n in _ast.walk(tree2):
        if isinstance(n, _ast.Compare) and any(isinstance(o, _ast.Lt) for o in n.ops):
            names = {x.id for x in _ast.walk(n) if isinstance(x, _ast.Name)}
            if 'best_total' in names:
                has_cmp = True

    def _names_in(target) -> set:
        """赋值目标里的名字 —— **元组赋值要展开**
        （`best_text, best_total, best_round = ...` 的 targets 是 Tuple，不是 Name）。"""
        if isinstance(target, _ast.Name):
            return {target.id}
        if isinstance(target, (_ast.Tuple, _ast.List)):
            out: set = set()
            for e in target.elts:
                out |= _names_in(e)
            return out
        return set()

    has_assign = any(isinstance(n, _ast.Assign)
                     and 'best_text' in set().union(
                         *[_names_in(t) for t in n.targets])
                     for n in _ast.walk(tree))
    return bool(has_cmp and has_assign)


def _calls_of(fn) -> set:
    """某个函数里**真正调用**了哪些函数名（`ast.Call`，不是源码字符串）。"""
    import ast as _ast
    import textwrap
    try:
        tree = _ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except Exception:                                            # noqa: BLE001
        return set()
    out: set = set()
    for n in _ast.walk(tree):
        if isinstance(n, _ast.Call):
            f = n.func
            out.add(f.attr if isinstance(f, _ast.Attribute)
                    else getattr(f, 'id', ''))
    return out


def _nv_calls() -> set:
    """`checkup_before_bind` 里**真正调用**了哪些函数名（ast.Call）。"""
    import ast as _ast
    nv = __import__('export.novel_version', fromlist=['x'])
    fn = getattr(nv, 'checkup_before_bind', None)
    if fn is None:
        return set()
    tree = _ast.parse(inspect.getsource(fn))
    return {n.func.attr if isinstance(n.func, _ast.Attribute)
            else getattr(n.func, 'id', '')
            for n in _ast.walk(tree) if isinstance(n, _ast.Call)}


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d, group_e, group_f, group_g,
               group_h, group_i, group_j, group_k, group_l, group_m, group_n,
               group_o, group_p, group_u, group_v, group_w, group_x, group_y):
        print(f'\n── {fn.__name__} ──', flush=True)
        try:
            fn()
        except Exception:                                      # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, traceback.format_exc()[-300:])
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n整理稿句法/承接验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    for n, _, _d in bad:
        print(f'  ✗ {n}', flush=True)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
