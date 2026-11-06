# -*- coding: utf-8 -*-
"""**去 AI 库** —— 把"AI 味"变成一份可审计的清单。

用户 2026-10-07
---------------
「有时候演员说话会有 AI 味道，你收集整理 AI 味道表达方式相关词语之类的，
  做一个去 AI 库，所有演员说话之前，所有工作人员产出任何内容之前，
  都做去 AI 味道审计处理。」

为什么要有它（不是"写个好提示词"就完了）
----------------------------------------
「AI 味」不是一种风格问题，它是**一批可以点名的习惯**：套话词（"首先/其次/
值得注意的是"）、套路句式（"不是 A 而是 B"）、直白情绪（"五味杂陈"）、
解释腔（"这意味着"）。它们共同的特征是 —— **读者一眼就出戏**，
而写的人（模型）自己看不见。

所以这件事要拆成两半，缺一半都不成立：

* **事前的规矩**（`prompt_block()`）：把清单塞进提示词，让它**别写出来**。
  这是省钱的路径 —— 写对了就不用改。
* **事后的审计**（`audit()`）：产出之后**逐条查**，命中就记下来。
  为什么非要有它：提示词管不住"第 87 拍时它还记不记得这条规矩"。
  这与去重护栏（`SceneBuilder._said`）是同一条道理 ——
  **规则放在出口，比放在入口可靠。**

两半都**不调模型**（零成本）：词表是确定的，命中也是确定的。
这很重要 —— 「每次产出都过一遍审计」如果一次要花一次 LLM 调用，
那就只可能做成"抽样"，而抽样一定漏。

三条设计口径（改这张库之前先读）
--------------------------------
1. **硬禁 / 软提示分开**。`HARD` 里的词一律不该出现（套话词没有"用得好"的场合）；
   `SOFT` 里的是**句式与修辞**，它们本身没问题、**滥用**才是问题 ——
   所以只提示，不判错。混在一起会让审计报告里 90% 是噪音。
2. **只在"输出文本"上查，不查输入**。提示词、设定、说明书里出现"首先"很正常
   （那是说明文）。审计的对象是**小说正文与台词**。
3. **命中不等于有错**。审计产出的是**给人看的清单**，不是自动改写指令 ——
   自动改写会把作者的手笔一起改掉。唯一例外见 `strip_hard()`：
   只在**明确的套话**上做删除式清理，且**必须记一笔**。

外部扩展
--------
`<程序目录>/craft/去AI补充.yaml`（可选）里的条目会**并进**内置库。
格式：`{'词': [...], '句式': [...], '修辞': [...], '情绪': [...], '解释': [...]}`。

English:
**De-AI library** — turn "AI flavor" into an auditable checklist.
User 2026-10-07
---------------
"Sometimes actors' speech has an AI flavor; collect and organize words and such related to
AI-flavored expressions,
  make a de-AI library; before all actors speak, before all staff produce any content,
  all must undergo de-AI-flavor audit processing."
Why it must exist (it is not enough to just "write a good prompt")
----------------------------------------
"AI flavor" is not a style problem; it is **a batch of nameable habits**: stock phrases
("first/second;
it is worth noting"), formulaic sentence patterns ("not A but B"), blunt emotions ("a mix of
five flavors"),
explanatory tone ("this means"). Their common feature is — **the reader is pulled out of the
story at a glance**,
while the writer (the model) cannot see it itself.
So this must be split into two halves; missing either half makes it untenable:
* **Upfront rules** (`prompt_block()`): stuff the checklist into the prompt so it **does not write them out**.
  This is the money-saving path — if written correctly, no revision is needed.
* **Post-hoc audit** (`audit()`): after production, **check item by item**, and record any hit.
  Why it must exist: the prompt cannot control "whether it still remembers this rule at beat 87".
  This is the same principle as the deduplication guardrail (`SceneBuilder._said`) —
  **rules placed at the exit are more reliable than at the entrance.**
Both halves **do not call the model** (zero cost): the vocabulary is deterministic, and matches
are deterministic too.
This matters a lot -- if "run the audit once on every output" costs one LLM call each time,
then it can only be done as "sampling", and sampling always misses things.
Three design principles (read before modifying this library)
--------------------------------
1. **Hard bans / soft hints are kept separate**. Words in `HARD` should never appear (cliche words have no occasion where they are "used well");
   those in `SOFT` are **sentence patterns and rhetoric**; they themselves are not a problem -- **overuse** is the problem --
   so they are only hinted at, not flagged as errors. Mixing them together would make 90% of the audit report noise.
2. **Only check the "output text", not the input**. It is normal for "首先" to appear in prompts, settings, and manuals
   (that is expository writing). The object of the audit is the **novel body text and dialogue**.
3. **A hit does not mean there is an error**. The audit produces a **list for humans to read**, not automatic rewrite instructions --
   automatic rewriting would also alter the author's own style. The only exception is `strip_hard()`:
   it only performs deletion-style cleanup on **clear cliches**, and **must record a note**.
External extension
--------
Entries in `<program dir>/craft/去AI补充.yaml` (optional) are **merged into** the built-in library.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# ══════════════════════════════════════════════════════════════════
#  库本体
# [EN] Library itself
# ══════════════════════════════════════════════════════════════════
#: **硬禁词** —— 一律不该出现在小说正文与台词里。分三类存，
#: 是为了让审计报告能说清"这是哪一类毛病"（报告里只说"你犯了 AI 味"没用）。
# [EN] : **Hard banned words** — should never appear in novel body text or dialogue. Stored in three
# [EN] categories,
# [EN] : so the audit report can clearly state "which category of problem this is" (just saying "you
# [EN] have AI flavor" in the report is useless).
HARD: dict[str, tuple[str, ...]] = {
    # ── 论述腔：这些词属于**说明文/论文**，不是小说 ──
    #   小说里出现"首先……其次……"，读起来像论文提纲，不像人说话。
    # [EN] ── Essayistic tone: these words belong to **expository writing / academic papers**, not novels
    # [EN] ──
    # [EN] When "first...second..." appears in a novel, it reads like an essay outline, not like a person
    # [EN] speaking.
    '论述腔': (
        '首先', '其次', '再次', '最后一点', '第一点', '第二点',
        '综上所述', '总而言之', '总的来说', '总得来说', '一言以蔽之',
        '不言而喻', '毋庸置疑', '众所周知', '不难看出', '由此可见',
        '值得注意的是', '值得一提的是', '需要指出的是', '不得不说',
        '相对而言', '从某种角度', '从某种意义上',
    ),
    # ── 连接词滥用：AI 用它们"粘"句子，人说话不这样 ──
    # [EN] ── Connective abuse: AI uses them to "glue" sentences together; people don't talk like that ──
    '连接腔': (
        '与此同时', '不仅如此', '不仅仅', '在这个过程里', '在这个过程中',
        '在此之后', '除此之外', '另一方面', '换句话说', '简而言之',
        '也就是说', '这意味着', '正因如此', '因此可以说',
    ),
    # ── 情绪直说：把情绪**命名**出来，而不是让人物表现出来 ──
    #   用户 2026-10-07 之前就报过"人物说的话很割裂"，一部分原因是
    #   旁白一直替人物总结心情，人物自己反而没事干。
    # [EN] ── Naming emotions directly: **naming** the emotion instead of letting the character show it ──
    # [EN] The user already reported before 2026-10-07 that "the characters' speech feels disjointed"; part
    # [EN] of the reason is
    # [EN] The narration keeps summarizing the characters' moods for them, while the characters themselves
    # [EN] have nothing to do.
    '情绪直说': (
        '五味杂陈', '百感交集', '心潮澎湃', '心如刀割', '心如死灰',
        '久久不能平静', '说不出话来', '无以言表', '难以言喻',
        '内心翻涌', '思绪万千', '感慨万千', '怅然若失', '恍如隔世',
        '一股暖流', '一阵寒意', '莫名的情绪',
    ),
    # ── 空转修饰：说了等于没说，还占字数 ──
    # [EN] ── Idle modifiers: saying it is the same as not saying it, and it still eats up word count ──
    '空转修饰': (
        '深深地', '深深的', '无比', '极其', '极为', '十分地',
        '不由自主地', '情不自禁地', '下意识地',
    ),
    # ── 文言虚词：台词要"自然标准普通话"，半文半白是 AI 味的重灾区 ──
    #   分镜师提示词早已写"不许文言词、不许半文半白"（crew/agents.py 的 Storyboard）。
    #   这里把"代码级审计"补上：命中即记、可反例法证明。
    # ⚠ **只收近零误报的句末虚词 + 文言发语词**，不收单字「之乎者也」——
    #   之/者/也/乎在现代中文里到处都是（之后/也是/在乎/似乎），按子串硬禁会
    #   把正常台词打成红，审计就失去意义（与模块头第 2 条"只在输出文本上查"同理）。
    #   要禁的是**只在文言文里出现的那种**：矣/焉/欤 作句末，呜呼/嗟乎 类叹词，
    #   若夫/是以/故曰 类发语词，善哉/甚矣/然也/是也/何也/安能 类文言句式。
    #   这些在当代小说正文与台词里几乎绝迹，命中即说明在半文半白。
    # [EN] ── Classical function words: dialogue must be "natural standard Mandarin"; half-classical
    # [EN] half-vernacular is a hotspot of AI flavor. Only near-zero-false-positive sentence-final
    # [EN] particles and classical openers are listed; single chars 之/乎/者/也 are excluded (too common
    # [EN] in modern Chinese to ban by substring).
    '文言虚词': (
        '矣', '焉', '欤',
        '呜呼', '嗟乎', '噫嘻',
        '若夫', '是以', '故曰',
        '善哉', '异哉', '甚矣', '然也', '是也', '何也', '安能',
    ),
}

#: **软提示**（句式 / 修辞）—— 本身没问题，**滥用**才是问题，所以只提醒别扎堆。
#: 用正则（`pattern`），匹配到就记一笔，但**不判错**。
# [EN] : **Soft hints** (sentence patterns / rhetoric) — not a problem in themselves; **abuse** is the
# [EN] problem, so only remind not to cluster them.
# [EN] : Use regex (`pattern`); record a hit when matched, but **do not mark it as an error**.
SOFT: tuple[tuple[str, str, str], ...] = (
    # (类目, 正则, 一句人话)
    # [EN] (category, regex, one plain-language sentence)
    ('对仗句', r'不是[^，。！？]{1,30}，?而是',
     '「不是 A，而是 B」—— 一句里用一次还行，连着用就成了模板'),
    ('对仗句', r'与其说[^，。！？]{1,30}，?不如说',
     '「与其说 A 不如说 B」—— 同上'),
    ('对仗句', r'既[^，。！？]{1,20}[，,]?又[^，。！？]{1,20}[，,]?既是',
     '「既是…又是…」排比式定义，读起来像介绍语'),
    ('比喻堆叠', r'(仿佛|宛如|犹如|好似)[^，。！？]{1,12}[，。，][^。！？]{0,20}'
                 r'(仿佛|宛如|犹如|好似)',
     '一句里两个"仿佛/宛如"—— 比喻堆叠，留一个就够'),
    ('比喻堆叠', r'像[^，。！？]{1,10}[，,]?一样[^，。！？]{0,8}[，,]?(像|仿佛)'
                 r'[^，。！？]{1,10}',
     '连着两个「像…一样」'),
    ('解释腔', r'(这|那)(意思|意味着|代表着|说明)[是着]?[^。！？]{2,}',
     '旁白替读者解释—— 让读者自己看出来'),
    ('三连排比', r'[^，。！？]{2,8}，[^，。！？]{2,8}，[^，。！？]{2,8}，'
                 r'(都|又|也|是|像)',
     '三段排比连着来—— 一次可以，每段都这样就是文体病'),
    # ⚠ 这两条正则原来写成 `——[^。\n]{1,40}——` 那种"中间不许有标点"的形状，
    #   实测**匹配不到任何真实句子**（"他顿了顿——像是——要说什么"里
    #   中间就有标点）。改宽之后才真的生效 —— 是 `verify_deai` 的 A5
    #   拿反例逐条试出来的，不是看出来的。
    # [EN] ⚠ These two regexes were originally written in the `——[^。\n]{1,40}——` shape that "allows no
    # [EN] punctuation in the middle",
    # [EN] and in practice **matched no real sentences at all** (in "he paused——as if——about to say
    # [EN] something"
    # [EN] there is punctuation in the middle). Only after widening them did they actually take effect —
    # [EN] this is `verify_deai`'s A5
    # [EN] found by testing counterexamples one by one, not by eyeballing.
    ('标点', r'——[^。\n]{1,40}——', '一行里两个破折号—— 常见的"补充说明"式绕圈'),
    ('标点', r'……[^。\n]{0,10}……', '省略号连着用两次，读起来像在拖延'),
    ('总结收尾', r'(这|那)(一刻|一天|一夜|一切)[^。！？]{0,12}(都|才|终于)',
     '章末总结腔—— 「这一夜，一切都变了」这类收束句'),
    # ★ 2026-10-12（用户点名："很容易吼 而不是正常说话"）：
    #   真人大部分时间用**平常声量**说话；把"激动"一律写成吼，是最省事也最假的写法
    #   （用一个词把情绪**放大**出来，而不是让情绪落到这句话的形状上）。
    #   ⚠ 为什么放**软提示**而不是硬词表：硬词表会被 `strip_hard()` **真的删掉**，
    #     而"吼道""厉声道"一删，句子就残了（"他吼道：'…'" → "他：'…'"）。
    #     硬词表的既有成员（"首先""深深地"）都是**删了不伤句意**的修饰词，音量词不是。
    # [EN] ★ 2026-10-12 (the user named this: "it shouts easily instead of speaking normally"):
    # [EN] real people speak at **normal volume** most of the time; writing every "excitement" as a shout
    # [EN] is the laziest and fakest approach (using one word to **amplify** the emotion instead of letting
    # [EN] the emotion land on the shape of the sentence).
    # [EN] ⚠ Why it goes in the **soft hints** rather than the hard word list: the hard list gets
    # [EN] **actually deleted** by `strip_hard()`, and deleting "shouted" / "said sternly" maims the
    # [EN] sentence ("he shouted: '...'" -> "he: '...'"). The existing hard-list members ("first",
    # [EN] "deeply") are modifiers that **can be removed without hurting the meaning**; volume words are
    # [EN] not.
    ('喊叫滥用',
     r'(吼道|厉声道|厉声说|怒喝道|咆哮道|嘶吼道|尖声道|尖声叫道|大声喊道)',
     '把"激动"写成吼 —— 真人大部分时间用平常声量说话；吼是动作不是标点，'
     '一场里吼过三次就没人听了'),
)


@dataclass
class Hit:
    """审计命中一条。`where` 只给**类目**，`what` 是命中的原文片段。
        English:
    An audit hit. `where` only gives the **category**, `what` is the matched original text fragment.
    """

    kind: str                      # 类目：论述腔 / 对仗句 / 情绪直说 …
    what: str                      # 命中的词或片段
    level: str = 'hard'            # hard（必删）/ soft（别扎堆）
    note: str = ''                 # 一句人话（soft 才有）
    text: str = ''                 # 出处文本（截断）
    who: str = ''                  # 谁产出的（演员名 / 职位名）
    # [EN] Category: essayistic tone / antithetical sentences / naming emotions directly ...
    # [EN] The word or fragment that hit
    # [EN] hard (must delete) / soft (don't cluster)
    # [EN] one plain-language sentence (only for soft)
    # [EN] Source text (truncated)
    # [EN] Who produced it (actor name / role name)


@dataclass
class AuditResult:
    """一次审计的结果。
        English:
    The result of one audit.
    """

    hits: list[Hit] = field(default_factory=list)
    checked: int = 0               # 查了几段
    #: **连续指标**（2026-10-10 加，第 04 类第 1 条）。
    # [EN] How many paragraphs were checked
    # [EN] : **Continuous metrics** (added 2026-10-10, category 04 item 1).
    #:
    #: 来历：这份审计原来只有「命中 / 没命中」两态 —— 判据是 **有/无**。
    #: 于是它看不见"没命中但读起来就是像机器写的"那种稿子：每个词都对，
    #: 可句长太均匀、四字组合反复、每句都以同两个字开头。
    #: 借鉴 `stef41/lmscan`（Apache-2.0）的四个连续量（突发度 / 句长变异 /
    #: 长 n-gram 重复率 / 句首多样性），把结论从「有/无命中」升级成「命中 + 分数」。
    #: 实现在 `style/ai_metrics.py`（纯本地、零成本、不调模型）。
    # [EN] : Origin: this audit originally had only two states, "hit / no hit" — the criterion was
    # [EN] **present/absent**.
    # [EN] : So it could not see drafts where "nothing hit but it still reads machine-written": every word
    # [EN] is fine,
    # [EN] : but sentence lengths are too uniform, four-character combinations repeat, and every sentence
    # [EN] starts with the same two characters.
    # [EN] : Borrowing four continuous quantities from `stef41/lmscan` (Apache-2.0) (burstiness /
    # [EN] sentence-length variation /
    # [EN] : long n-gram repetition rate / sentence-opening diversity), upgrading the conclusion from
    # [EN] "hit/no hit" to "hits + score".
    # [EN] : Implemented in `style/ai_metrics.py` (fully local, zero cost, no model calls).
    metrics: dict = field(default_factory=dict)
    #: 正文（只在 `audit_text` 传了 `with_metrics=True` 时才有）—— 供调用方再算别的
    # [EN] : Body text (only present when `audit_text` is passed `with_metrics=True`) — for callers to
    # [EN] compute other things
    text: str = ''

    @property
    def hard(self) -> list[Hit]:
        return [h for h in self.hits if h.level == 'hard']

    @property
    def soft(self) -> list[Hit]:
        return [h for h in self.hits if h.level == 'soft']

    @property
    def ok(self) -> bool:
        """**只按硬禁算**（软提示不进结论）—— 见模块头第 1 条。

        ⚠ 2026-10-10：连续指标**故意不进这个结论**。理由同上：
          它是"读起来像不像"的**参考量**，不是一个能一票否决的判据 ——
          `ai_metrics` 那一层已经为它单独定过阈值（`UNIFORM_CV` 等），
          要否决也该由那边否决，别在这里把两套判据混成一个 `ok`。
        
                English:
        **Count only hard bans** (soft hints do not enter the conclusion) -- see rule 1 at the module
        header.
                ⚠ 2026-10-10: continuous metrics are **deliberately not included in this conclusion**. Same reason as above:
                  it is a **reference quantity** for "does it read like it", not a criterion that can veto on its own --
                  the `ai_metrics` layer has already set separate thresholds for it (`UNIFORM_CV` etc.),
                  if a veto is needed it should come from there, don't merge the two sets of criteria into one `ok` here.
        """
        return not self.hard

    def kinds(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for h in self.hits:
            out[h.kind] = out.get(h.kind, 0) + 1
        return out

    # ── 连续指标的三个**人话**结论（阈值全在 `ai_metrics` 里，不在这里另定）──
    # [EN] ── The three **plain-language** conclusions of the continuous metrics (all thresholds are in
    # [EN] `ai_metrics`, not redefined here) ──
    def metric_flags(self) -> list[str]:
        """从连续指标里挑出**值得说一句**的那几条（没有就返回空）。

        ★ 只报"越过阈值"的，不把四个数原样念一遍 —— 一次报告塞十个数字，
          等于没报告（与"每条问题都要带修法"是同一条纪律）。
        
                English:
        Pick out the few items from the continuous metrics that are **worth mentioning** (return empty
        if none).
                ★ Only report those that "cross the threshold", do not recite the four numbers as-is -- cramming ten numbers into one report
                  is as good as no report (the same discipline as "every problem must come with a fix").
        """
        m = self.metrics or {}
        out: list[str] = []
        drift = (m.get('漂移') or {}).get('态') or ''
        if drift == '过于均匀':
            out.append('句长**过于均匀**（窗间变异低于阈值）—— 人写的东西不会这么齐，'
                       '试着把长短句掺开')
        elif drift == '突然跳变':
            out.append('文风**中途突变**（某一窗明显偏离前后）—— 多半是换了模型或换了提示词，'
                       '不是这稿子本身该有的变化')
        elif drift == '逐渐漂移':
            out.append('文风**一路漂移**（不是突变，是越写越不一样）—— 检查是不是'
                       '上下文越喂越长、前半和后半不像一个人写的')
        d = m.get('句首多样性')
        if isinstance(d, float) and d < 0.5:
            out.append(f'句首**重复得多**（多样性 {d:.2f}）—— 换几种开头的写法，'
                       '别每句都"他……"“那……”')
        r = m.get('四字重复率')
        if isinstance(r, float) and r > 0.02:
            out.append(f'四字组合**反复出现**（重复率 {r:.3f}）—— 同一个说法换个词')
        return out


# ══════════════════════════════════════════════════════════════════
#  外部扩展
# [EN] External extension
# ══════════════════════════════════════════════════════════════════
_EXTRA_FILE = 'craft/去AI补充.yaml'
_extra_cache: dict[str, tuple[str, ...]] | None = None


def _extra_words() -> dict[str, tuple[str, ...]]:
    """`craft/去AI补充.yaml` 里的额外词（没有文件就返回空）。

    作者自己觉得"这本书里不许出现"的词，可以往那儿写 —— 不用改代码。
    读不动只记一次日志、**不影响内置库**（审计不能因为一个可选文件就罢工）。
    
        English:
    Extra words from `craft/去AI补充.yaml` (returns empty if there is no file).
        Words the author thinks "must not appear in this book" can be written there -- no need to change code.
        If it fails to load, only log once, **does not affect the built-in library** (the audit must not stop working because of one optional file).
    """
    global _extra_cache
    if _extra_cache is not None:
        return _extra_cache
    out: dict[str, tuple[str, ...]] = {}
    try:
        import yaml
        p = Path(__file__).resolve().parent.parent / _EXTRA_FILE
        if p.is_file():
            d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
            if isinstance(d, dict):
                for k, v in d.items():
                    if isinstance(v, (list, tuple)):
                        words = tuple(str(x).strip() for x in v if str(x).strip())
                        if words:
                            out[str(k)] = words
    except Exception:                                            # noqa: BLE001
        out = {}
    _extra_cache = out
    return out


def all_hard_words() -> dict[str, tuple[str, ...]]:
    """内置硬禁词 + 作者补充（同名的类目**合并**，不回覆盖）。
        English:
    Built-in hard-banned words + author additions (categories with the same name are **merged**, not
    overwritten).
    """
    out = {k: tuple(v) for k, v in HARD.items()}
    for k, v in _extra_words().items():
        out[k] = tuple(dict.fromkeys(tuple(out.get(k, ())) + tuple(v)))
    return out


def words(limit_per_kind: int = 0) -> tuple[str, ...]:
    """全部硬禁词（去重保序）。`limit_per_kind>0` 时每类只取前几个。
        English:
    All hard-banned words (deduplicated, order preserved). When `limit_per_kind>0`, only take the
    first few of each kind.
    """
    out: list[str] = []
    for _k, ws in all_hard_words().items():
        take = ws[:limit_per_kind] if limit_per_kind > 0 else ws
        out.extend(take)
    return tuple(dict.fromkeys(out))


# ══════════════════════════════════════════════════════════════════
#  审计
# [EN] Audit
# ══════════════════════════════════════════════════════════════════
#: 引号/书名号里的是**人物原话**（"他说'首先'"这种是正常的），
#: 但小说里的台词本来就写在引号里 —— 所以这里**不**做"引号内跳过"。
#: 只跳过 markdown 结构行（`#`/`>`/`-` 开头的那些是元信息，不是正文）。
# [EN] : What is inside quotes / book-title marks is **the character's original speech** ("he said
# [EN] 'first'" is normal),
# [EN] : but dialogue in a novel is already written inside quotes — so here we do **not** "skip inside
# [EN] quotes".
# [EN] : Only skip markdown structural lines (those starting with `#`/`>`/`-` are metadata, not body
# [EN] text).
_SKIP_LINE = re.compile(r'^\s*(?:[#>|\-*·▸]|\d+\.\s|〔|（剧组|（编剧室)')


def audit_text(text: str, *, who: str = '', soft: bool = True,
               with_metrics: bool = False) -> AuditResult:
    """查一段文本。返回 `AuditResult`（`hits` 里 hard/soft 分开）。

    `who` 只用来在报告里写清"谁写的"（演员名 / 职位名）。

    `with_metrics=True` 时**顺带算一遍连续指标**（第 04 类第 1 条）。
    ★ 默认关，是刻意的：连续指标要**整篇**才有意义（短文本上"句长变异"天然小，
      会把好文字报成"过于均匀" —— 这一条在 `ai_metrics` 上已经踩过）。
      逐句调 `audit_text` 的地方不该开它，只有"按天按章审计一次"才开。
    
        English:
    Audit a piece of text. Returns `AuditResult` (`hits` separates hard/soft).
        `who` is only used to clearly state "who wrote it" in the report (actor name / role name).
        When `with_metrics=True`, **also compute the continuous metrics** (category 04, rule 1).
        ★ Off by default, deliberately: continuous metrics are only meaningful on the **whole piece** (on short text, "sentence length variation" is naturally small,
          which reports good writing as "too uniform" -- this was already hit on `ai_metrics`).
          Places that call `audit_text` sentence by sentence should not enable it; only "audit once per day per chapter" should enable it.
    """
    res = AuditResult()
    src = str(text or '')
    if not src.strip():
        return res
    lines = [ln for ln in src.splitlines() if not _SKIP_LINE.match(ln)]
    body = '\n'.join(lines)
    if not body.strip():
        return res
    res.checked = len(lines)
    if with_metrics:
        try:
            from style import ai_metrics                         # noqa: PLC0415
            res.metrics = ai_metrics.analyze(body)
            res.text = body
        except Exception as exc:                                 # noqa: BLE001
            # 连续指标是**锦上添花的那一栏**，它算不出来不该让整次审计失败
            # [EN] Continuous metrics are **the icing-on-the-cake column**; failing to compute them should not make
            # [EN] the whole audit fail
            res.metrics = {'错误': f'{exc!r}'}
    for kind, ws in all_hard_words().items():
        for w in ws:
            if w and w in body:
                res.hits.append(Hit(kind=kind, what=w, level='hard',
                                    text=_clip(body), who=who))
    if soft:
        for kind, pat, note in SOFT:
            try:
                for m in re.finditer(pat, body):
                    res.hits.append(Hit(kind=kind, what=m.group(0)[:24],
                                        level='soft', note=note,
                                        text=_clip(body), who=who))
            except re.error:                                     # noqa: BLE001
                continue
    # ★ 2026-10-16（用户：「生成的小说不像人话」）：复读机检测。
    #   同一句口头禅在正文里反复念（或只换几个字），标 soft 命中，
    #   与 `export/novel_version._fold_repeats` 同一口径（出口兜底）。
    #   只动带引号的台词，不动旁白 / 动作。
    # [EN] 2026-10-16 (user: "the generated novel doesn't sound human"): repeat-machine
    # [EN] detection. If the same catchphrase is repeated (or with only a few chars changed),
    # [EN] flag a soft hit -- same calibration as `export/novel_version._fold_repeats`
    # [EN] (export-side fallback). Only touches quoted dialogue.
    _audit_repeat_hits(body, res, who)
    return res


def _deai_quotes(text: str) -> list[tuple[int, int, str]]:
    """找正文里成对引号区间（中文 / 英文），返回 (start, end, quote)。"""
    out: list[tuple[int, int, str]] = []
    i, n = 0, len(text)
    for o, cl in (('“', '”'), ('"', '"'), ('‘', '’'), ("'", "'")):
        j = 0
        while True:
            s = text.find(o, j)
            if s == -1:
                break
            e = text.find(cl, s + 1)
            if e == -1:
                break
            out.append((s, e + 1, text[s + 1:e]))
            j = e + 1
    return out


def _deai_norm(s: str) -> str:
    return re.sub(r"""\s，。！？、；：“”‘’""''（）()—…·\.\,\!\?\;\:\*\·\|\/""", '', s)


def _audit_repeat_hits(body: str, res: 'AuditResult', who: str) -> None:
    quotes = _deai_quotes(body)
    if len(quotes) < 2:
        return
    recent: list[str] = []
    for (_s, _e, q) in quotes:
        k = _deai_norm(q)
        if not k:
            continue
        hit = False
        for r in recent:
            kk = min(len(r), len(k))
            if kk >= 3 and (k.startswith(r[:kk]) or r.startswith(k[:kk])):
                res.hits.append(Hit(kind='复读机', what=q[:24],
                                    level='soft',
                                    note='同一句口头禅反复念（或只换几个字），读者出戏；'
                                         '整理/装订时只留第一次，其余用一句叙述带过',
                                    text=_clip(body), who=who))
                hit = True
                break
        if not hit:
            recent.append(k)
            if len(recent) > 30:
                recent.pop(0)


def audit_many(items: Iterable[tuple[str, str]], *, soft: bool = True) -> AuditResult:
    """`items` = `[(谁, 文本), ...]` —— 一次查一批（演员台词、剧组产出）。
        English:
    `items` = `[(who, text), ...]` -- audit a batch at once (actor dialogue, crew output).
    """
    out = AuditResult()
    for who, text in items:
        r = audit_text(text, who=who, soft=soft)
        out.hits.extend(r.hits)
        out.checked += r.checked
    return out


def _clip(text: str, n: int = 40) -> str:
    t = ' '.join(str(text or '').split())
    return t[:n] + ('…' if len(t) > n else '')


# ══════════════════════════════════════════════════════════════════
#  事前的规矩：给提示词用的一段
# [EN] Upfront rules: a paragraph used for the prompt
# ══════════════════════════════════════════════════════════════════
def prompt_block(*, per_kind: int = 5, include_soft: bool = True,
                 width: int = 0) -> str:
    """拼成提示词里那一段（**默认给演员用**）。

    为什么要有 `per_kind`：全表 90 多个词塞进**每一拍、每个人**的提示词，
    光这一项就把上下文吃掉几百 token，而模型的注意力是有限的 ——
    列 90 个词不如列 15 个最常见的（其余交给事后审计兜底）。
    
        English:
    Assemble that paragraph in the prompt (**default for actors**).
        Why `per_kind` is needed: stuffing all 90+ words of the full table into the prompt of **every beat, every person**
        would consume several hundred tokens on this item alone, and the model's attention is limited --
        listing 90 words is worse than listing the 15 most common ones (the rest are left to post-hoc audit as a fallback).
    """
    hw = all_hard_words()
    rows: list[str] = []
    for kind, ws in hw.items():
        take = list(ws[:per_kind]) if per_kind > 0 else list(ws)
        if take:
            rows.append(f'· {kind}：' + '、'.join(take))
    if include_soft:
        seen: set[str] = set()
        for kind, _pat, note in SOFT:
            if kind in seen:
                continue
            seen.add(kind)
            rows.append(f'· {kind}：{note}')
    if not rows:
        return ''
    head = ('【别写成 AI 腔 —— 下面这些一出现就会被审出来】\n'
            '  这些是"读起来像机器写的"的习惯。**不要为了避开它们而变得别扭** ——'
            '绕开就是，该怎么说还怎么说：')
    body = '\n'.join(rows)
    if width and len(body) > width:
        body = body[:width].rstrip() + '…'
    return head + '\n' + body


def words_only_block(*, per_kind: int = 8) -> str:
    """只要词（给剧组那批"产出结构化文本"的职位用，不带句式说明）。
        English:
    Words only (for the crew roles that "produce structured text", without sentence pattern
    explanations).
    """
    hw = all_hard_words()
    words_all: list[str] = []
    for _k, ws in hw.items():
        words_all.extend(list(ws[:per_kind]) if per_kind > 0 else list(ws))
    if not words_all:
        return ''
    return ('【不要用这些 AI 套话】' + '、'.join(dict.fromkeys(words_all))
            + '\n（它们是论文/说明文的词，出现在小说里会很出戏）')


# ══════════════════════════════════════════════════════════════════
#  报告
# [EN] Report
# ══════════════════════════════════════════════════════════════════
def render_report(res: AuditResult, *, title: str = '去 AI 味审计',
                  extra: str = '') -> str:
    """把审计结果写成一份给人看的 Markdown。
        English:
    Write the audit results as a human-readable Markdown document.
    """
    lines = [f'# {title}', '']
    if extra:
        lines += [extra, '']
    h, s = res.hard, res.soft
    if not res.hits:
        # ★★ 2026-10-10 修：这里原来**直接 return 了**，于是"没命中硬禁词"
        #   就把连续指标栏一起吃掉了 —— 而那恰恰是最需要它的时候：
        #   **一个 AI 味词都没命中、但通篇句长齐得像排版的稿子，光看这份报告
        #   是"完全干净"的**。判据 F4b 正是这么把它抓出来的。
        #   ⇒ 现在这一档也往下走，末尾照样渲染连续指标栏。
        # [EN] ★★ Fixed 2026-10-10: this used to **directly return**, so "no hard banned words hit"
        # [EN] swallowed the continuous metrics column too — and that is exactly when it is needed most:
        # [EN] **A draft where not a single AI-flavored word hits, but sentence lengths throughout are as
        # [EN] uniform as typesetting, judged by this report alone
        # [EN] is "completely clean"**. Criterion F4b is exactly how it caught this.
        # [EN] ⇒ Now this branch also continues downward, and the continuous metrics column is still rendered
        # [EN] at the end.
        lines += [f'> 查了 {res.checked} 段，**没有发现 AI 腔的词句**。', '']
    else:
        lines += [f'> 查了 {res.checked} 段，命中 **{len(h)} 处硬禁**、{len(s)} 处提醒。',
                  '> 硬禁 = 套话词（该删）；提醒 = 句式修辞（本身没错，**别扎堆**）。', '']
    if h:
        lines += ['## 硬禁（这些词不该出现）', '']
        by: dict[str, list[Hit]] = {}
        for x in h:
            by.setdefault(x.kind, []).append(x)
        for kind, xs in by.items():
            lines.append(f'### {kind}')
            cnt: dict[str, int] = {}
            for x in xs:
                key = f'{x.who}｜{x.what}' if x.who else x.what
                cnt[key] = cnt.get(key, 0) + 1
            for key, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
                lines.append(f'- {key}　×{n}')
            lines.append('')
    if s:
        lines += ['## 提醒（句式与修辞，别扎堆）', '']
        by2: dict[str, list[Hit]] = {}
        for x in s:
            by2.setdefault(x.kind, []).append(x)
        for kind, xs in by2.items():
            lines.append(f'### {kind}（{len(xs)} 处）')
            lines.append(f'> {xs[0].note}')
            for x in xs[:6]:
                tag = f'{x.who}：' if x.who else ''
                lines.append(f'- {tag}{x.what}')
            lines.append('')
    flags = res.metric_flags()
    if flags:
        lines += ['## 读起来像不像人写的（**连续指标栏**）', '',
                  '> 不是"命中了哪个词"，是这一稿整体的节奏。来自 `style/ai_metrics.py`，',
                  '> 阈值与作者定稿的基线比对得出（换一本书要重标一次）。', '']
        lines += [f'- {x}' for x in flags]
        lines.append('')
        m = res.metrics or {}
        drift = m.get('漂移') or {}
        if drift.get('态'):
            lines.append(f"> 参考：分句中位 {m.get('分句中位长', '—')} 字 · "
                         f"≤5 字分句 {m.get('≤5字分句占比', '—')} · "
                         f"句首多样性 {m.get('句首多样性', '—')} · "
                         f"文风漂移「{drift.get('态')}」（{drift.get('窗数', '—')} 个窗）")
            lines.append('')
    lines += ['---', '',
              '本页由程序生成 —— 它**只报告，不改写**。',
              '改写会把你自己的手笔一起改掉，所以留给你判断；',
              '想扩这条库，往 `craft/去AI补充.yaml` 里加词即可（不用改代码）。']
    return '\n'.join(lines) + '\n'


def strip_hard(text: str) -> tuple[str, list[str]]:
    """**删除式清理**：把硬禁词从一句里拿掉，返回 `(新文本, 拿掉了什么)`。

    ⚠ 只给**一个用途**服务：`sim/loop` 在**开工前**清掉模型偶发写进台词的
    套话词（那种词删掉之后句子仍然成立 —— "首先，我不去" → "我不去"）。
    **句式与修辞一概不动**（删了会把句子弄坏），所以要配合 `audit()` 看报告。

    调用方**必须**把返回的第二个值记一笔 —— 静默改写文本是本项目明令禁止的
    （用户之前报过"人物说的话讲一遍又说一遍"，就是静默加工的后果）。
    
        English:
    **Deletion-style cleanup**: remove hard-banned words from a sentence, returns `(new text, what
    was removed)`.
        ⚠ Serves only **one purpose**: `sim/loop` clears, **before work starts**, cliche words the model occasionally wrote into dialogue
        **Sentence patterns and rhetoric are left untouched** (removing them would break the sentence), so use `audit()` to see the report alongside.
        The caller **must** record the second returned value -- silently rewriting text is explicitly forbidden in this project
        (the user previously reported "a character says the same thing once and then says it again", which was the result of silent processing).
    """
    out = str(text or '')
    removed: list[str] = []
    for _kind, ws in all_hard_words().items():
        for w in ws:
            if w and w in out:
                out2 = out.replace(w, '')
                if out2 != out:
                    removed.append(w)
                    out = out2
    # 清理之后可能出现"，，"或句首逗号，顺手收拾（这不算改写，是修复）
    # [EN] After cleanup, "，，" or a leading comma may appear; clean it up along the way (this is not
    # [EN] rewriting, it is repair)
    out = re.sub(r'[，、]{2,}', '，', out)
    out = re.sub(r'^[，、]+', '', out)
    return out, removed
