# -*- coding: utf-8 -*-
"""哪个 Agent 该用哪一类模型 —— **推荐表**（2026-10-12）。

## 为什么要有这张表

用户 2026-10-12 的原话：

> 「我发现只用一种模型是不足以较好的完成任务，Deepseek小说能力不足。
>   我希望你根据不同Agent的功能，结合不同模型的能力，推荐不同的模型。」
> 「不同功能的Agents打开配置之后会有一个推荐模型…… 请主要推荐国内外主要模型，
>   Hy3我测试了 写小说还可以 可以作为候选」

所以这张表回答两个问题：

1. **这一类活要什么能力**（`profile`）—— 不是"哪个模型更强"，而是
   "写样章要看文笔、判定只要一个结论、抽取要吐得出合法 JSON"。
2. **具体推荐哪几个**（`names`）—— 用**模型名的子串**表示，因为它要跟
   **作者已经配好的那些条目**去对（`best_match()`）：对上了才叫"已配置的推荐模型"，
   对不上就老实说"你还没配这类模型"。

## 三条设计规矩

1. **推荐的是"类别"不是"名次"**：`names` 里排前面的优先，但没有"最好"这一说 ——
   同一个活儿用不同模型都能干，作者自己的口味（贵/便宜、本地/云端）说了算。
2. **对不上就说没配上，别硬推**。凭空给出一个作者根本没配的模型名 = 假按钮。
3. **`tip` 是给"专项优化"用的**：写进提示词里的一段注意事项
   （`crew/catalog._default_prompt` 会按模型能力挑一段加进去）。
   它是**给模型看的**，所以不进 i18n、保持中文。

English:
Which kind of model each Agent should use -- the **recommendation table** (2026-10-12).
## Why this table exists
The user's exact words (2026-10-12):
> "I found that one model isn't enough to do the job well; DeepSeek's novel ability is
> insufficient. I want you to recommend different models for different Agents based on their
> functions and the models' strengths."
> "...when you open the config of an Agent with a different function there will be a recommended
> model... please mainly recommend the major domestic and international models; I tested Hy3 and
> it writes novels reasonably well, so it can be a candidate."
So this table answers two questions: (1) **what ability this kind of work needs** (`profile`) --
not "which model is stronger" but "writing a sample chapter needs prose skill, judging needs only
a conclusion, extraction must emit valid JSON"; and (2) **which specific ones are recommended**
(`names`) -- expressed as **substrings of the model name**, because it must be matched against
**what the author has already configured** (`best_match()`).
## Three design rules
1. **It recommends a "category", not a ranking**: earlier entries in `names` go first, but there is
   no "best" -- several models can do the same job, and the author's own taste decides.
2. **If nothing matches, say so; don't push.** Inventing a model the author never configured is a
   fake button.
3. **`tip` is for "specialization"**: a note written into the prompt (picked by model capability in
   `crew/catalog._default_prompt`). It is **for the model to read**, so it stays Chinese and does
   not go into i18n.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ══════════════════════════════════════════════════════════════════════
#  能力档（这一类活要什么）
# [EN] Ability profiles (what this kind of work needs)
# ══════════════════════════════════════════════════════════════════════
#: 键 → (中文名, 一句话说明, 给模型的注意事项)
#  ★ 说明会出现在界面上，所以**必须同时登记进 `i18n.py`**（动态取值，扫描器扫不到）。
# [EN] : key -> (Chinese name, one-line explanation, note for the model)
# [EN] ★ The explanation appears in the UI, so it **must also be registered in `i18n.py`** (dynamic
# [EN] values, which the checker cannot scan).
PROFILES: dict[str, tuple[str, str, str]] = {
    'write': (
        '文笔与长文',
        '要写出能读的散文：句子要有节奏、人物要有口气、一段能写几百字不散。'
        '便宜模型在这里最容易露馅（重复、套话、一句话掰成三句）。',
        '你这一发请求只求一件事：**把这个故事写好**。宁可少写情节，也不要写水词、'
        '不要重复上一段已经说过的话、不要用「不禁」「仿佛」「心中五味杂陈」这类'
        '现成套语收尾。写完就停，不要总结。',
    ),
    'adapt': (
        '改写与编排',
        '把已有的材料重新组织成另一种东西（样章→剧本、设定→开局）。'
        '要求**读得懂输入、改得动结构**，而且不能丢原意。',
        '你的活是**改写与编排**，不是自由创作：输入里有的东西不许凭空换掉，'
        '输入里没有的东西不许编。改完要让人一眼看出"这还是原来那件事"。',
    ),
    'judge': (
        '判断与把关',
        '只要**一个结论**（满足了没有 / 属于哪一类 / 有几个问题）。'
        '这类调用最频繁、最不该花大钱，而且**思考会连输出额度一起吃掉**。',
        '只给结论，不要思考过程、不要解释你在做什么。'
        '第一行就给出答案，之后最多补一句理由（40 字以内）。',
    ),
    'extract': (
        '抽取与结构化',
        '把一堆散文本变成**程序能读的 JSON**：字段名固定、条数固定、'
        '长了会被截断在半句话里。',
        '严格按给定的字段名输出**完整合法**的 JSON，不要加注释、不要用 Markdown 代码块包住。'
        '每个字段写短（人名地名照抄原文），**宁可少写一条，也不要写半句就停**。',
    ),
    'perform': (
        '高频演出',
        '每一拍都要跑（人物的动作与台词）。它决定"故事活着没有"，'
        '也决定账单 —— 所以**要快、要短、要像人说话**。',
        '你在演一个活人，不是写小说：台词要短（一句话为主）、可以答非所问、'
        '可以沉默、可以只说半句。**不要每句都完整、不要每次都解释自己为什么这么做**。',
    ),
    'craft': (
        '事务清单',
        '交一份**短清单**（道具单、造型表、宣发一句话、场记核对）。'
        '质量要求是"齐、对、短"，不是"华丽"。',
        '输出一份短清单：每行一件事，不超过 20 字。不要写导语和总结。',
    ),
    'service': (
        '外挂服务',
        '这一条指向**另一个程序**（创作服务），它有自己的模型配置；'
        '这里选的是"用它的时候按哪个模型算"。',
        '（这条是外挂服务，提示词由对方程序自己管。）',
    ),
}


# ══════════════════════════════════════════════════════════════════════
#  每个 Agent 的推荐
# [EN] Recommendation per Agent
# ══════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Advice:
    """一个 Agent 的推荐：哪一档能力 + 为什么 + 推荐哪几个模型名。
        English:
    Recommendation for one Agent: which ability profile + why + which model names.
    """

    profile: str
    why: str
    names: tuple[str, ...] = ()
    #: 这一位是不是**每一拍都跑**（界面上标一下"这一个是花钱大户"）。
    # [EN] : whether this one **runs on every beat** (the UI tags it as a big spender).
    hot: bool = False

    @property
    def profile_name(self) -> str:
        """能力档的中文名（界面要过 `t()`）。
                English:
        The Chinese name of the ability profile (the UI runs it through `t()`).
        """
        return PROFILES.get(self.profile, PROFILES['craft'])[0]

    @property
    def profile_why(self) -> str:
        """能力档的说明。
                English:
        The explanation of the ability profile.
        """
        return PROFILES.get(self.profile, PROFILES['craft'])[1]


#: 推荐顺序：**先强后弱**，同档之内先写"作者大概率已经有的那几家"。
#  ★ 名字用**子串**匹配（`best_match` 按 `entry.model` / `entry.key` / `entry.label`
#    小写包含判断）—— 版本号经常变（`claude-sonnet-4-5` → `claude-sonnet-5`），
#    写死全名会一年就过期。
# [EN] : Recommendation order: **strong first**, and within one profile the providers the author
# [EN] most likely already has. ★ Names are matched by **substring** (`best_match` checks lowercase
# [EN] containment against `entry.model` / `entry.key` / `entry.label`) -- version numbers change
# [EN] often (`claude-sonnet-4-5` -> `claude-sonnet-5`), and a hardcoded full name expires within a
# [EN] year.
_W_WRITE = ('hy3', 'claude', 'gpt-5', 'gpt-4.1', 'gemini', 'deepseek-v4-pro',
            'qwen3-max', 'qwen-max', 'kimi', 'glm-4', 'minimax', 'deepseek')
_W_ADAPT = ('hy3', 'claude', 'gpt-5', 'deepseek-v4-pro', 'qwen3', 'glm-4', 'kimi',
            'gemini', 'deepseek')
_W_JUDGE = ('deepseek-flash', 'hy3', 'qwen-turbo', 'qwen-flash', 'glm-4-flash',
            'gpt-4o-mini', 'gemini-flash', 'deepseek', 'glm', 'qwen')
_W_EXTRACT = ('deepseek-v4-pro', 'deepseek-flash', 'hy3', 'qwen3', 'glm-4',
              'gpt-4o', 'gemini', 'claude', 'deepseek')
_W_PERFORM = ('hy3', 'deepseek-flash', 'qwen-flash', 'qwen-plus', 'glm-4-flash',
              'gpt-4o-mini', 'gemini-flash', 'deepseek', 'glm', 'qwen')
_W_CRAFT = ('deepseek-flash', 'hy3', 'glm-4-flash', 'qwen-turbo', 'gpt-4o-mini',
            'gemini-flash', 'deepseek', 'glm', 'qwen')

ADVICE: dict[str, Advice] = {
    # ── 编剧组（写）──
    # [EN] ── Writing team (writes) ──
    'novelist': Advice(
        'write',
        '它是全剧组**唯一写正文**的人：样章要能当小说读，文笔不行整条链都白搭。'
        '「DeepSeek 小说能力不足」最先卡在这儿。',
        _W_WRITE, hot=True),
    'screenwriter': Advice(
        'adapt',
        '把样章拆成能拍的分场分拍 —— 要读得懂原著、又要下得了刀，'
        '便宜模型容易写成"原句搬运"。',
        _W_ADAPT),
    'settings_room': Advice(
        'adapt',
        '导演·作家·剧作者三方会审补局部设定 —— 要同时理解世界规则与当前剧情，'
        '是最容易"编出与设定打架的东西"的一步。',
        _W_ADAPT),
    'reviewer': Advice(
        'judge',
        '收工复盘：结论 + 修改意见。用的是**已经落盘的正文**，'
        '不需要文笔，要的是一眼看得出问题。',
        _W_JUDGE),
    'stylist': Advice(
        'craft',
        '衣着·随身物·仪态，一人一条 — 短清单。',
        _W_CRAFT),
    'sound': Advice(
        'craft',
        '这一场的声音层：环境音·静默·转折，一句话即可。',
        _W_CRAFT),
    'polisher': Advice(
        'judge',
        '点名"哪几句 AI 味重、该怎么改"。它读稿子、不改稿子，'
        '所以**要便宜**（每天一次）但**要认得出来**。',
        _W_JUDGE),
    'rehearsal': Advice(
        'judge',
        '剧本定稿后空走一遍，报"哪里会卡住"。产出不进正文，'
        '结论型任务。',
        _W_JUDGE),

    # ── 导演组（定）──
    # [EN] ── Director team (decides) ──
    'director': Advice(
        'adapt',
        '每拍判断"要不要挑事、挑什么事"—— 它决定故事有没有劲。'
        '事件本身要贴世界观、要扣人物，写砸了整段戏都平。',
        _W_ADAPT, hot=True),

    # ── 演员组（演）──
    # [EN] ── Actor team (acts) ──
    'actor': Advice(
        'perform',
        '**全程序花钱最多的一位**：每一拍每个在场人物各一次。'
        '它要的是"像人说话"，不是"辞藻漂亮" —— 用大模型写台词既贵又容易演成朗诵。',
        _W_PERFORM, hot=True),
    'extra': Advice(
        'perform',
        '群众演员：一句半句、有诉求的那种。同样高频，但比主要角色更短。',
        _W_PERFORM, hot=True),

    # ── 现场组（记）──
    # [EN] ── On-site team (records) ──
    'continuity': Advice(
        'craft',
        '场记：每场有没有落点、谁在场上 —— 核对型短输出。',
        _W_CRAFT),
    'script_doctor': Advice(
        'judge',
        '上屏**之前**的闸门：是不是人话、接不接上文。它每一拍都跑，'
        '所以"便宜 + 判得准"比"文笔好"重要得多。',
        _W_JUDGE, hot=True),
    'props': Advice(
        'craft',
        '道具单：这一场台面上该有什么。',
        _W_CRAFT),
    'art': Advice(
        'craft',
        '当天那张地图与画面要素 —— 短清单。',
        _W_CRAFT),
    'publicity': Advice(
        'craft',
        '宣发：一句话卖点与 logline。',
        _W_CRAFT),
    'researcher': Advice(
        'extract',
        '考据：名物/制度/称谓站不站得住。它要把结论整理成短条目，'
        '还要在不确定时**明确说不知道**（编一个错的制度比说不知道坏得多）。',
        _W_EXTRACT),
    # ★★★ 2026-10-22：`storyboard` / `visref` 是 2026-10-15 新增的两个职位，
    #   但推荐表一直没跟上 —— `verify_llm_models` 的 C11「每个剧组职位都配了推荐」
    #   因此**长期红着**，而它红得对：这两位的模型是随手挑的。
    #   ⚠ 这两个 key 必须在这里各有一条，否则 `advice_for()` 会退到通用建议
    #     （那等于"这行没有专门建议"，与"忘了写"在界面上看不出来）。
    # [EN] ★★★ 2026-10-22: `storyboard` / `visref` were added as positions on 2026-10-15, but the
    # [EN] recommendation table never caught up -- `verify_llm_models` C11 "every crew position has a
    # [EN] recommendation" was **red for a long time**, and it was right: those two had an arbitrary
    # [EN] model. ⚠ Both keys need an entry here, otherwise `advice_for()` falls back to the generic
    # [EN] advice, which looks identical to "forgot to write one".
    'storyboard': Advice(
        'craft',
        '分镜：把定稿剧本拆成镜号/景别/画面/台词/镜头运动 —— 结构化短行，'
        '一条拍一行。**不需要文笔，怕的是漏镜与编号乱**；'
        '所以便宜档够用，但要能稳出结构化条目。',
        _W_CRAFT),
    'visref': Advice(
        'extract',
        '视觉参考：为出场人物/关键场景写**生图用的描述**（外貌、服装、光线、构图），'
        '要求同一角色跨天一致。产出是给生图用的短提示，不是散文 —— 便宜档即可。',
        _W_EXTRACT),

    # ── 系统服务 ──
    # [EN] ── System services ──
    'ingest': Advice(
        'extract',
        '开卷：把作者给的资料读成人物/世界观/地点/伏笔/进度表/开局方案 —— '
        '**一次要吐几百上千行合法 JSON**，是所有步骤里最容易"被长度截断"的一个。'
        '这一位建议配一个**输出上限大、JSON 稳**的模型。',
        _W_EXTRACT, hot=True),
    'memory': Advice(
        'judge',
        '把当天压成 2~3 句前情提要、给后台人物补经历。一天一次、纯压缩，'
        '便宜的够了。',
        _W_JUDGE),
    'progress': Advice(
        'judge',
        '每一拍问"这一站的判据满足了没有"。**它是最典型的"只要一个结论"**：'
        '不需要推理过程，而思考会把输出额度整份吃掉（2026-10-06 的事故就是它）。'
        '建议配一个**支持关掉思考**的模型。',
        _W_JUDGE, hot=True),
    'compliance': Advice(
        'judge',
        '合规复核：会不会越线、该判哪一级。安全功能，'
        '**拿不到结论时按"不放行"处理**，所以宁可配一个稳的。',
        _W_JUDGE),

    # ── 特殊 Agent ──
    # [EN] ── Special Agents ──
    'novelservices': Advice(
        'service',
        '它是**外挂的整个写作后端**（MuMuAINovel），写的是整章正文 —— '
        '按"写小说好不好"挑，你自己实测过的那家优先。',
        _W_WRITE),
}

#: 认不出的 Agent（作者自建的职位）用这一条兜底。
# [EN] : Fallback for unrecognized Agents (roles the author created).
DEFAULT_ADVICE = Advice(
    'craft',
    '这是你自己加的职位，没有预设推荐 —— 按它的活像上面哪一类来挑即可。',
    _W_CRAFT)


def advice_for(agent_key: str) -> Advice:
    """这个 Agent 的推荐（认不出就给兜底那条，**不抛**）。
        English:
    The recommendation for this Agent (falls back silently if unrecognized, **never raises**).
    """
    return ADVICE.get(str(agent_key or '').strip(), DEFAULT_ADVICE)


def best_match(agent_key: str, entries: list[Any]) -> Any | None:
    """在**作者已经配好的模型**里，找第一个符合这个 Agent 推荐的。

    返回的是登记表里的那一条（`llm.models.ModelEntry`）；一条都合不上返回 `None`
    —— 那种情况界面要**老实说"你还没配这类模型"**，而不是随便挑一个顶上。

        English:
    Among the models **the author has already configured**, find the first that matches this Agent's
    recommendation.
        Returns the registry entry (`llm.models.ModelEntry`); `None` if nothing matches -- in that
        case the UI must **honestly say "you haven't configured this kind of model yet"** rather than
        picking one arbitrarily.
    """
    adv = advice_for(agent_key)
    if not adv.names or not entries:
        return None
    items = list(entries)
    for want in adv.names:
        w = want.lower()
        for e in items:
            hay = f'{getattr(e, "model", "")} {getattr(e, "key", "")} ' \
                  f'{getattr(e, "label", "")}'.lower()
            if w in hay:
                return e
    return None


def suggest_names(agent_key: str, limit: int = 4) -> list[str]:
    """界面上那句「建议加一个：hy3 / claude / …」用哪几个名字。
        English:
    Which names the UI's "suggest adding one of: hy3 / claude / ..." line uses.
    """
    adv = advice_for(agent_key)
    return list(adv.names[:max(1, int(limit))])


# ══════════════════════════════════════════════════════════════════════
#  按**模型家族**的专项优化（2026-10-12）
# [EN] Specialization by **model family** (2026-10-12)
# ══════════════════════════════════════════════════════════════════════
# 用户原话：「各个Agents请根据推荐使用的LLM进行专项优化」。
# [EN] User's original words: "Each Agent should be specially optimized according to the recommended
# [EN] LLM".
#
# 这一层与上面的 `PROFILES` 分工不同：
#   · `PROFILES[k][2]` 说的是**这类活**该怎么交代（与模型无关）；
#   · 下面这张表说的是**这一家模型**有什么脾气 —— 同一段提示词，
#     给 deepseek 要额外叮嘱"别写思考过程"，给 claude 要额外叮嘱"别总结"。
# 两者**都会拼进该 Agent 的系统提示词**（见 `crew/catalog.prompt_block`）。
# [EN] This layer has a different division of labor from `PROFILES` above:
# [EN] · `PROFILES[k][2]` says how **this kind of work** should be instructed (independent of the
# [EN] model);
# [EN] · The table below says what **this model** is like -- for the same prompt,
# [EN] for deepseek you need to additionally instruct "don't write the thinking process", for claude
# [EN] you need to additionally instruct "don't summarize".
# [EN] Both **get concatenated into that Agent's system prompt** (see `crew/catalog.prompt_block`).
#
# ⚠ 顺序即匹配顺序（具体名放前面），与 `llm/capabilities._MODELS` 同一条规矩。
# ⚠ 这些是**给模型看的**，不进 i18n。
# [EN] The user's exact words: "specialize each Agent for the LLM it is recommended to use".
# [EN] This layer differs from `PROFILES` above: `PROFILES[k][2]` says how **this kind of work**
# [EN] should be briefed (model-independent); the table below says what **this model family** is like
# [EN] -- the same prompt needs "don't write out your reasoning" added for deepseek, and "don't
# [EN] summarize" added for claude. Both get spliced into that Agent's system prompt (see
# [EN] `crew/catalog.prompt_block`).
# [EN] ⚠ Order is match order (specific names first), same rule as `llm/capabilities._MODELS`.
# [EN] ⚠ These are **for the model to read**, so they do not go into i18n.
FAMILY_TIPS: tuple[tuple[str, str], ...] = (
    ('hy3',
     '【混元 Hy3 的脾气】中文小说的语感是它的强项，长段落不容易散；'
     '但**要 JSON 的时候它爱用 ```json 代码块包起来** —— 这一条明确说过：'
     '只输出 JSON 本身，不要代码块、不要任何解释文字。'),
    ('hunyuan',
     '【混元的脾气】中文语感好、长文稳；结构化输出偶尔会包 Markdown 代码块，'
     '要 JSON 时必须另说一句"不要代码块"。'),
    ('deepseek',
     '【DeepSeek 的脾气】**默认会先"想"再答，而思考会连输出额度一起吃掉**。'
     '所以凡是"只要一个结论"的活，请在提示词里直说：不要输出思考过程，第一行就给结论。'
     '另外它的中文容易滑向套话（不禁、仿佛、五味杂陈、眼中闪过一丝），'
     '写正文时请刻意避开现成词组。'),
    ('claude',
     '【Claude 的脾气】服从性好、长文稳；但它**爱在结尾加总结与客套**。'
     '请严格按要求的段落数输出，写完就停，不要加"希望这对你有帮助"这类收尾。'),
    ('gpt-image', '【出图模型】它只出图，不做文本判断。'),
    ('chatgpt', '【ChatGPT 的脾气】指令跟随强；o 系列不接受 temperature，'
                '而且**思考占用输出额度**，判定型任务要明说"直接给结论"。'),
    ('gpt-5', '【GPT-5 的脾气】指令跟随强、结构感好；'
              '但输出容易"过度完整"（该短的也写长），请把字数上限当真。'),
    ('gpt-4', '【GPT-4 系的脾气】稳、听话；中文文笔偏"翻译腔"，'
              '写正文时请刻意用中文口语，不要用英文句式的长定语。'),
    ('o3', '【o 系列的脾气】**思考占用输出额度**，且不认 temperature。'
           '判定型任务请明说"直接给结论、不要推理过程"。'),
    ('o1', '【o 系列的脾气】**思考占用输出额度**，且不认 temperature。'
           '判定型任务请明说"直接给结论、不要推理过程"。'),
    ('gemini',
     '【Gemini 的脾气】长上下文强、读长材料不易漏；'
     '但输出有时自带 Markdown 小标题与列表，要纯文本时必须明确说清。'),
    ('qwen',
     '【通义千问的脾气】中文好、性价比高；'
     '**长输出容易绕回重复**（同一句换个说法再说一遍），请明说"不要重复已经说过的内容"。'),
    ('glm',
     '【智谱 GLM 的脾气】快而便宜；字段一多就容易漏，'
     '所以结构化任务请**把字段名一次列全**，并要求"每个字段都不能省"。'),
    ('kimi',
     '【Kimi 的脾气】长上下文、中文写作稳；速度一般，'
     '不要给它"顺手多写一点"的空间 —— 明确字数。'),
    ('moonshot', '【Kimi 的脾气】长上下文、中文写作稳；速度一般，明确字数即可。'),
    ('minimax',
     '【MiniMax 的脾气】口语化台词出得自然；'
     '但容易"太热闹"（每句都带情绪），需要安静的时候请明确说"这一句只是动作，不要台词"。'),
)

#: 认不出家族时的兜底提示（**写一句通用的，别硬猜**）。
# [EN] : Fallback note when the family is unrecognized (**write a generic one, don\'t guess**).
GENERIC_TIP = ('【通用】按上面写的要求做；拿不到就直说拿不到，不要编。')


def family_tip(model: str) -> str:
    """这个模型家族的专项叮嘱（认不出就给通用那句）。

    ⚠ **认不出不猜** —— 与 `llm/capabilities` 同一条纪律：瞎猜会把用户
      带进"明明是这个模型，提示词却按另一个模型的脾气写"的坑。

        English:
    The specialization note for this model family (generic when unrecognized).
        ⚠ **Don\'t guess when unrecognized** -- the same discipline as `llm/capabilities`: guessing
        leads users into "this is model A but the prompt is written for model B".
    """
    name = str(model or '').strip().lower()
    if not name:
        return ''
    for pat, tip in FAMILY_TIPS:
        if pat in name:
            return tip
    return GENERIC_TIP


def profile_tip(agent_key: str) -> str:
    """这类活的专项叮嘱（与模型无关）。
        English:
    The specialization note for this kind of work (model independent).
    """
    return PROFILES.get(advice_for(agent_key).profile, PROFILES['craft'])[2]
