# -*- coding: utf-8 -*-
"""**全书级候选检测** —— 给导出关口的 Reflection 提供"具体锚点"，**不判病**。

★★★ 为什么单章指标看不见（2026-10-20 读稿实测）
===============================================
四篇真跑（红楼梦 / 边城 / 诛仙 / 望江楼）逐篇读过，肉眼能看见三类毛病，
而八项指标全是 0：

| 肉眼看到的 | 当时所有指标 |
|---|---|
| 王夫人反复问"缺什么"、黛玉反复答"够使"，问法每次不同、答法不变 | 重复 **0** |
| 碧瑶说 5 次"跟我走"、张小凡 3 次"我跟你走"，立场来回横跳 | 重复 **0** |
| 那只鸭子被提来推去 7 次 | 道具循环 **0**（词表里没有"鸭子"）|

共同点：**跨句、跨段、跨天**才成形。原来的检测器都在单句/单段粒度上量。

★★★ 但这一层**故意不产出"毛病数"** —— 本轮最重要的一个判断
==========================================================
第一版把 `echo_phrase` 的命中数当毛病数，然后**在真人 18 章上量**：

    真人命中 5 处：崇仁坊 ×3（地名，对话里提到三次）、
    「十五年前」×3、「这段堤」×3（话题聚焦，每句都在推进新信息）、
    「记完了」×3（确认式回答）

**真人很正常。** 而真跑的病（"缺什么"）在纯频次上跟它们一模一样。
这正是项目里付过学费的那条结论：**"重复"不能直接当病** ——
真人比真跑重复得更多（最长同题链人中位 2 / 最大 4，真跑全 1–2），
标准是**可删除性**：删掉这条，读者会损失什么。说不出损失，才算病。

那是语义判断，代码没有资格做。所以分工是：

    代码：**找出候选组**（哪些片段/哪些道具反复出现，带可回查的原句）
    顾问：判**哪一条是手法、哪一条是原地打转**（`reflexion.verbalize`）

因此这里的返回值**不进 `verdict.RUBRIC`、不进 `prose_issue_count`** ——
它只进导出时的"反思记录"。混进确定性计数里，就变成"拿会抖的判官当收敛判据"。

⚠ 阈值一律先用真人样本校准（`tools/verify_reflexion.py` 的 D 组）：
  `ECHO_MIN = 4`（真人最高 3，4 是"零命中"的最小值）· `CHURN_MIN = 4`。
[EN] Book-level candidate detection for export-time Reflection. It deliberately emits
[EN] **candidates with traceable quotes**, never a defect count: measured on 18 human
[EN] chapters, three-phrase echoes are ordinary writing (place names, topic focus).
[EN] Whether a repetition is a device or a loop is a deletability judgement -- the
[EN] advisor's job, not the counter's. Hence nothing here enters RUBRIC.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: 台词片段频次门槛。**真人 18 章在 4 这一档零命中**（3 会命中 5 处，都是正常写法）。
ECHO_MIN = 4
#: 同一片段至少要出现在这么多句**不同**台词里。单句里重复同一个短语是修辞，不报。
ECHO_MIN_SENTENCES = 4
#: 道具流转门槛。同一件东西被转手 ≥4 次才算"反复"。
CHURN_MIN = 4

#: 虚词表：要求片段里至少有 1 个实字（挡"的了着""我这你"这种纯虚片段）。
#: ⚠ "什么"**不在这里** —— 它是疑问代词、承担语义（"缺什么"是有效信号）。
_SKIP_CHARS = set('的了着过是在有和就都也很不我这你那他她它们个么呢吧啊呀哦嗯'
                  '一二三四五六七八九十几什怎样为以所因为如果但是而且还又再')

#: **称谓词**：中文小说里"姑娘""妹妹""太太"满地都是，重复是正常的。
#: 不加这条，真人样本立刻被"姑娘 ×8"顶红 —— 那不是病，是汉语。
#: ⚠ 只放**通用称谓**；具体人名（"小凡"）故意不放：叫 10 次确实值得看一眼。
_ADDRESS = (
    '姑娘', '妹妹', '姐姐', '太太', '老太太', '嫂子', '哥哥', '弟弟',
    '丫头', '小丫头', '婆子', '小厮', '老爷', '少爷', '夫人', '奶奶',
    '母亲', '父亲', '舅舅', '姨娘', '叔叔', '婶婶', '大哥', '大姐',
    '爷', '娘', '爹', '老祖宗',
    # ★ 2026-10-20 补（望江楼那篇实测）：**店家类**称谓。
    #   不加这一条时，「掌柜这」被判成"台词回声 ×6" —— 假阳性：
    #   那是"称谓 + 指代"，不是"同一句话换着说"。加了之后该篇归零，
    #   而诛仙那三条（「小凡你」「跟你走」「你师父」）一条都没漏。
    # [EN] Shopkeeper-style address forms. Without them "掌柜这" was reported as a
    # [EN] six-fold echo -- a false positive (title + deictic, not a repeated line).
    '掌柜', '老板', '店主', '公子', '小姐', '大人', '师傅', '先生',
)

#: 宾语候选黑名单：这些词出现在转移类动词旁边是**正常汉语**，不是道具。
_STOP_NOUN = {
    '手', '眼睛', '眼', '头', '脸', '口', '声', '心', '身', '肩', '脚',
    '门', '窗', '屋', '天', '地', '人', '事', '话', '时候', '地方', '东西',
    '自己', '对方', '过来', '过去', '出来', '起来', '下来', '进来', '上去',
    '一边', '一下', '一点', '一声', '一句', '一口气', '一把', '一眼',
}

#: 转移类动词（递/推/塞/提/放…）。判定用"名词 ± 窗口内出现它"，**不要求紧邻** ——
#: 中文的"把"字句让宾语跑到动词前面（"把鸭子放她脚边"），紧邻写法会漏一半。
_MOVE_VERB = re.compile(
    r'递给|递|推给|推|塞给|塞|交给|交|送给|送|传给|传|拿给|拿|'
    r'抱给|抱|拎|提|端给|端|放回|放到|放|搁|挂在|挂|扔给|扔|接|抢|'
    r'了?指|留着|留|还你|还|收下|收')

#: 量词短语 = 中文里指称**具体物件**的强信号（"这两只鸭子""那只碗"）。
#: ⚠ 捕获组只能取 **1~2 字**：写成 {1,3} 会把谓语一起吃进去
#:   （实测"这两只鸭子肥不肥"抓成"鸭子肥"、"把汗巾搭回肩上"抓成"汗巾搭"，
#:    于是同一个物件被拆成十几个"不同的名词"，计数永远到不了门槛）。
_MEASURE = re.compile(
    r'(?:这|那)(?:两|三|几)?(?:只|条|个|张|把|碗|壶|支|件|块|包|盘|袋|根|枚|片)'
    r'([\u4e00-\u9fff]{1,2})')
#: "把/将 + 名词"（把字句里最常见的形式）
_BA = re.compile(r'(?:把|将)([\u4e00-\u9fff]{1,2})')

#: 名词与转移动词的"同场"窗口（字）。
_CHURN_WINDOW = 10


@dataclass
class BookIssue:
    """一条**候选**。`samples` 的原句必须能在正文里逐字找到 ——
    给不出原句的检测等于让作者去猜，那是无效信号。"""
    kind: str
    count: int
    detail: str
    samples: tuple[str, ...] = ()
    days: tuple[int, ...] = ()
    key: str = ''

    def one_line(self) -> str:
        where = f'（第 {"、".join(str(d) for d in self.days)} 天）' if self.days else ''
        return f'{self.kind} ×{self.count}{where}：{self.detail}'


def _speeches(text: str) -> list[str]:
    try:
        from crew import prose_flow as PF
        return [str(x).strip() for x in PF.quoted_texts(text or '') if str(x).strip()]
    except Exception:                                            # noqa: BLE001
        return []


def _phrases(sentence: str, lo: int = 3, hi: int = 6) -> set[str]:
    """一句台词里的 3~6 字片段（去掉纯虚与称谓）。"""
    body = re.sub(r'[^\u4e00-\u9fff]', '', sentence or '')
    out: set[str] = set()
    for n in range(lo, hi + 1):
        for i in range(0, max(0, len(body) - n + 1)):
            frag = body[i:i + n]
            if len(set(frag) - _SKIP_CHARS) < 1:      # 纯虚片段（"的了着"）丢掉
                continue
            if any(w in frag or frag in w for w in _ADDRESS):
                continue                              # 称谓重复是汉语，不是病
            out.add(frag)
    return out


def echo_phrase(text: str) -> list[BookIssue]:
    """**换着说法重复**：核心短语被反复用，但每句措辞都不同。

    就是"反复问缺什么"的可数形态 —— 几句话都不一样，共享的是"缺 / 什么"。
    **候选，不是判决。**
    """
    sents = _speeches(text)
    if len(sents) < ECHO_MIN_SENTENCES:
        return []
    where: dict[str, list[int]] = {}
    for idx, s in enumerate(sents):
        for frag in _phrases(s):
            where.setdefault(frag, []).append(idx)
    hits: list[BookIssue] = []
    for frag, idxs in where.items():
        if len(idxs) < ECHO_MIN or len(set(idxs)) < ECHO_MIN_SENTENCES:
            continue
        hits.append(BookIssue(
            kind='台词回声', count=len(idxs), key=frag,
            detail=f'「{frag}」出现在 {len(set(idxs))} 句不同台词里'
                   f'（措辞各不相同，核心短语没变）',
            samples=tuple(sents[i][:40] for i in sorted(set(idxs))[:3])))
    # 只留**最长的那个**：3 字片段命中时它的 4/5/6 字扩展也会命中，
    # 全报出来会把一条毛病说成十条（作者看到就关掉了）。
    hits.sort(key=lambda x: (-len(x.key), -x.count))
    kept: list[BookIssue] = []
    for h in hits:
        if any(h.key in k.key for k in kept):
            continue
        kept.append(h)
    return kept[:4]


def _nouns(raw: str) -> dict[str, list[int]]:
    """候选物件 → 它在正文里出现的位置（量词短语 + "把/将"两路）。"""
    pos: dict[str, list[int]] = {}
    for rx in (_MEASURE, _BA):
        for m in rx.finditer(raw):
            noun = (m.group(1) or '').strip()
            if not noun or noun in _STOP_NOUN:
                continue
            if len(set(noun) - _SKIP_CHARS) < 1:
                continue
            pos.setdefault(noun, []).append(m.start(1))
    return pos


def prop_churn(text: str) -> list[BookIssue]:
    """**同一件东西被反复转手**（"那只鸭子提来推去 7 次"）。

    与 `prop_cycle_issues` 分工：那个数"补给—消耗"（续水、添炭），
    这个数"在几个人手里传来传去"。判定用**同场窗口**而不是紧邻 ——
    中文的"把"字句让宾语跑到动词前面，紧邻写法会漏掉最常见的那一半。
    """
    raw = str(text or '')
    if not raw.strip():
        return []
    out: list[BookIssue] = []
    for noun, spots in _nouns(raw).items():
        near = 0
        for p in spots:
            seg = raw[max(0, p - _CHURN_WINDOW): p + _CHURN_WINDOW]
            if _MOVE_VERB.search(seg):
                near += 1
        if near < CHURN_MIN:
            continue
        quotes = [ln.strip()[:60] for ln in raw.splitlines() if noun in ln][:2]
        out.append(BookIssue(
            kind='道具流转', count=near, key=noun,
            detail=f'「{noun}」在递/推/提/放这类动作里出现 {near} 次 '
                   f'（同一件东西在转手，事情没有往前走）',
            samples=tuple(quotes)))
    out.sort(key=lambda x: -x.count)
    return out[:3]


def cross_day_echo(days: list[tuple[int, str]]) -> list[BookIssue]:
    """**跨天逐字重复**：同一条长台词在不同天里一模一样。

    单天看每句都合理（当天确实说了这句），合订成书就是复读。
    """
    if not days or len(days) < 2:
        return []
    where: dict[str, list[int]] = {}
    for day, text in days:
        for s in set(_speeches(text)):
            key = re.sub(r'[^\u4e00-\u9fff]', '', s)
            if len(key) < 6:                     # 太短（"嗯""好"）不算复读
                continue
            where.setdefault(key, []).append(int(day))
    out: list[BookIssue] = []
    for key, ds in where.items():
        uniq = sorted(set(ds))
        if len(uniq) < 2:
            continue
        out.append(BookIssue(
            kind='跨天复读', count=len(ds), key=key[:20], days=tuple(uniq),
            detail=f'这句话在 {len(uniq)} 天里逐字一样：「{key[:18]}…」',
            samples=(key[:40],)))
    out.sort(key=lambda x: -x.count)
    return out[:4]



# ══════════════════════════════════════════════════════════════
# 「概述句代替场景」—— 只检测，**不自动修**
# ══════════════════════════════════════════════════════════════
#: 抽象宾语：接在叙述动词后面时，最容易变成"交代"而不是"演"。
#: ⚠ 过泛的词（"什么""这些""事情"）**一律不许进** —— 它们在任何中文叙述里
#:   满地都是，加进来真人样本立刻被顶红（实测加"什么"时真人命中 1 处，
#:   是「商量什么事」，那明明是具体动作）。
_TELL_ABSTRACT = (
    '习惯', '琐碎', '心事', '往事', '旧事', '家务', '近况', '情形',
    '光景', '心思', '打算', '经历', '来历', '身世', '种种', '交情', '规矩',
)
#: 叙述动词（把这些内容"说掉"的动词）
_TELL_VERB = (
    '吐露', '说起', '谈到', '讲了', '说了些', '交代', '诉说', '提起',
    '告诉', '讲了讲', '聊起', '议论', '商量',
)
_TELL_RE = re.compile(
    r'(?:' + '|'.join(_TELL_VERB) + r')[^。！？]{0,12}?(?:'
    + '|'.join(_TELL_ABSTRACT) + r')')
#: "说些/做些/讲些 + 一长串" —— 典型形态是「说些只有纸笔知道的琐碎」，
#: 宾语被一个定语从句挡在后面，纯词表抓不到，所以另开一条。
_TELL_LOOSE = re.compile(r'(?:说些|做些|讲些|谈些|聊些)[^。！？]{0,16}')


def telling_sentences(text: str) -> list[tuple[int, int, str]]:
    """**「概述句代替场景」**：一句没有台词、只有"他把什么事说了"的交代。

    典型形态（`snow_v25` 实测那一句）：

        忽然对岛村吐露自己长年记日记的私密习惯，说些只有纸笔知道的琐碎。

    前后全是具体动作与台词，中间插一句总结 —— 读者被告知"有这件事"，
    却没有看到这件事发生。

    ★★★ 为什么**只出候选、不进自动修复**
    ------------------------------------
    修它必须**新增内容**：要写出她具体说了什么。而修复合约的铁律是
    **事实一个字不许改**（`crew/verdict.py` 的硬约束：台词不许变少、
    字数 0.85~1.45、句子数不许暴涨）。"概述 → 场景"必然要编造细节，
    那已经不是改写，是创作 —— 机器做这件事就会写出假的日记内容。

    ⇒ 它进**候选清单**（导出时给人看），不进 `prose_issue_count`、
      不进 `verdict.RUBRIC`、**没有 repair recipe**。
      `repair_recipes.uncovered()` 会因为"这一类没人修"报出来吗？不会 ——
      因为它压根不在计数表里。这正是刻意的：**可数 ≠ 该自动改**。
    [EN] Detect-only. Repairing it requires inventing what was actually said, which
    [EN] breaks the hard invariant "facts may not change". So it is a candidate for the
    [EN] human/advisor, never an automated rewrite.
    """
    out: list[tuple[int, int, str]] = []
    raw = str(text or '')
    pos = 0
    for para in raw.split('\n'):
        start, pos = pos, pos + len(para) + 1
        p = para.strip()
        if not p or p.startswith(('#', '>')):
            continue
        for m in re.finditer(r'[^。！？]+[。！？]?', para):
            seg = m.group(0)
            if not seg.strip():
                continue
            # 有台词就不是"概述"，那是"演"。
            if any(q in seg for q in ('\u201c', '\u201d', '\u300c', '"')):
                continue
            if _TELL_RE.search(seg) or _TELL_LOOSE.search(seg):
                out.append((start + m.start(), start + m.end(), seg.strip()))
    return out


# ══════════════════════════════════════════════════════════════
# 「手上动作密度」—— 外部评审逼出来的一条真判据
# ══════════════════════════════════════════════════════════════
#: 手上动作的**可数形态 = 动宾结构**（动词 + 具体物件）。
#: ⚠ 第一版只匹配动词本身，于是「点」「按」「收」这类单字把"一点点""按住""收下"
#:   全算了进去 —— 实测把 6 处数成 **35 处**，还据此判"成立"。
#:   外部评审说的本来就是「抹壶、放壶、端盏、搁盏」这种**动宾**，口径就该是动宾。
#: [EN] Countable form = verb + concrete object. Matching bare verbs over-counted 6 as 35.
ACTION_OBJ = re.compile(
    r'(?:抹|擦|放|搁|端|推|递|倒|斟|捡|拾|攥|捏|捧|提|拿|拨|敲|叩|添|续|'
    r'吹|捻|摩|抚|按|拍|抖|收|拢|拎|举起|放下)'
    r'(?:了|着|过|一|两|半|起|下|回)?'
    r'(?:把|只|块|个|支|张)?'
    r'(?:壶|盏|碗|杯|盘|碟|桌|案|几|布|抹布|算盘|烟杆|烟袋|灯|灯芯|炭|'
    r'纸|册|账本|账册|账|筷|巾|帕|袖|衣角|围裙|手|肩|腕|脸|眉|袖口|壶把)')

#: 每千字几处算"过多"。**量出来的**：真人 36 篇中位 0.0、最高 **5.6**；
#: 实测 mwl_v2（被外部评审点名"大量琐碎动作"那版）是 **19.4**、mwl_v3 是 6.5。
#: 取 6.0 —— 在真人最高值之上，留一点余量，保证真人样本零命中。
ACTION_PER_K = 6.0

#: 密度判定的**最短文本**。低于它就是「样本太小，不下结论」。
MIN_DENSITY_CHARS = 300


def action_density(text: str) -> dict:
    """**手上动作密度**（每千字几处）。

    外部评审（2026-10-20）原话：「大量对话夹杂琐碎动作描写（抹壶、放壶、端盏、搁盏），
    打断对话节奏……关键信息被淹没在茶具动作中」。

    这条是那 5 条批评里**唯一一条既真、又可数、真人基线还干净**的：
      · 真人 36 篇：中位 **0.0** / 最高 **5.6**
      · `mwl_v2`（被评审那版）：**19.4**（真人上限的 3.5 倍）
      · `mwl_v3`：6.5

    ⚠ 它是**密度**不是**总数**：同样的 15 处，写在 3000 字里很正常，
      挤在 770 字里就是"茶具淹没对话"。
    ⚠ 只数**动宾**（"抹壶""搁盏"），不数光杆动词（"点""按""收"）——
      后者在任何中文里都高频（"一点点""按住""收下"），数它会把密度虚高 5 倍。
    [EN] Hand-action density per 1000 characters. The only one of the five external
    [EN] complaints that is true, countable, AND clean on the human baseline
    [EN] (human median 0.0 / max 5.6; the reviewed run measured 19.4).
    """
    raw = str(text or '')
    zh = len([c for c in raw if '\u4e00' <= c <= '\u9fff'])
    n = len(ACTION_OBJ.findall(raw))
    per = (n / zh * 1000.0) if zh else 0.0
    # ⚠ **短文本不下结论**：300 字以下，一处动作就能把密度顶到 50+，
    #   那个数没有意义（实测 220 字的夹具算出 59.1）。这时 `judged=False`，
    #   调用方必须据此说"验不了"，**不许**拿它判"没超"。
    #   第一版就是这里错的：判 `over=False` 之后消息写成"每千字 ≤6.0"，
    #   而实测是 59.1 —— **一句话里自相矛盾**，读日志的人会以为程序算错了。
    # [EN] Short texts get no verdict: one action in 220 chars reads as 59.1/1k, which is
    # [EN] meaningless. `judged=False` so callers say "cannot verify" instead of "not over"
    # [EN] -- the first version printed "<= 6.0" next to a measured 59.1.
    judged = bool(zh >= MIN_DENSITY_CHARS)
    return {'n': n, 'zh': zh, 'per_k': round(per, 1),
            'judged': judged,
            'over': bool(judged and per > ACTION_PER_K),
            'limit': ACTION_PER_K,
            'need': MIN_DENSITY_CHARS}

def audit_book(days: list[tuple[int, str]]) -> dict:
    """导出关口用：对整本书跑一遍，返回**候选清单**（不是毛病数）。

    `counts` 的键与 `prose_issue_count` **不重叠**，也不进 `verdict.RUBRIC` ——
    这一层的产物是"给人看的一页清单"，不是"收敛判据"。
    """
    days = [(int(d), str(t or '')) for d, t in (days or []) if str(t or '').strip()]
    whole = '\n\n'.join(t for _d, t in days)
    issues: list[BookIssue] = []
    for fn in (echo_phrase, prop_churn):
        try:
            issues += fn(whole)
        except Exception:                                        # noqa: BLE001
            pass
    try:
        issues += cross_day_echo(days)
    except Exception:                                            # noqa: BLE001
        pass
    # 「概述句代替场景」：只报候选，**不自动修**（修它要新增内容）。
    try:
        for _s, _e, seg in telling_sentences(whole):
            issues.append(BookIssue(
                kind='概述代场景', count=1, key=seg[:14],
                detail='这句把"发生了什么事"一句话交代掉了，'
                       '读者被告知而没有看到（周边都是具体动作与台词）',
                samples=(seg[:50],)))
    except Exception:                                            # noqa: BLE001
        pass
    counts: dict[str, int] = {}
    for x in issues:
        counts[x.kind] = counts.get(x.kind, 0) + 1
    return {'issues': issues, 'counts': counts, 'total': len(issues),
            'days': len(days), 'zh': len([c for c in whole
                                          if '\u4e00' <= c <= '\u9fff'])}


def report_lines(found: dict) -> list[str]:
    """给人看的一份清单（进 `导出/反思记录.md`）。"""
    issues = (found or {}).get('issues') or []
    if not issues:
        return ['- 没有发现值得复核的跨句/跨天形态。']
    lines = ['- 下面是**候选**，不是判决：重复也可能是手法，'
             '要按"删掉它读者会损失什么"来判。']
    for x in issues:
        lines.append(f'- **{x.kind}** ×{x.count} —— {x.detail}')
        for s in x.samples:
            if s:
                lines.append(f'  - 原文：{s}')
    return lines


__all__ = ['BookIssue', 'echo_phrase', 'prop_churn', 'cross_day_echo',
           'telling_sentences', 'action_density', 'ACTION_PER_K',
           'audit_book', 'report_lines', 'ECHO_MIN', 'CHURN_MIN']
