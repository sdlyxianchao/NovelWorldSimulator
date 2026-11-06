# -*- coding: utf-8 -*-
"""客流与群演（临演池）：给故事接上**外部输入**。

为什么要有这一层
----------------
真机跑《临河茶肆》的日志里，词频是这样的：**看 627、擦 565、账 556、茶 267**，
而 **买 0、顾客 0、客人 20**。茶楼没有生意，人物只能内循环 ——
系统还在提示词里教他们"手头有事就继续做（比如「擦紫砂壶」）"，
于是那句话被抄了 565 遍。

所以这里补的不是"更多 NPC"，是**外部输入**：

  · **客流** —— 按天气 / 时辰 / 场所 / 局势算"这一刻有几个生人"，**纯本地算式**；
  · **背景群演** —— 一行式，**不跑模型**（"两个脚夫在门口歇脚，就着粗茶啃干粮"）；
  · **功能群演** —— 带**一个诉求**（讨债的、报信的），进决策上下文，用完就退；
  · **寿命与回收** —— **诉求了结才退场**；一直没人搭话的，等满耐心后
    "等不到人，走了"（给出理由，并记进钩子名册），不留僵尸。

三档里"钩子群演"（反复出现、像有故事的客人）**这一轮没做**：它要跨场记忆
和"值不值得转正成正式人物卡"的判断，等最小的一档跑稳了再说。

⚠ 两条纪律（都是设计稿 §5.2 定的）：
  1. **群演不进记忆主库** —— 只在"当前情况"里给，不写 `memory` 表；
  2. **背景群演不调模型** —— 它存在的意义是"有人在场"，不是"有戏"。

English:
Foot traffic and extras (extra pool): connect **external input** to the story.
Why this layer is needed
----------------
while **买 0, 顾客 0, 客人 20**. The teahouse had no business, the characters could only loop
internally ——
and the system was still teaching them in the prompt "if you have something at hand, keep doing
it (e.g. 「擦紫砂壶」)",
so that sentence got copied 565 times.
So what's added here is not "more NPCs", but **external input**:
  · **Foot traffic** —— compute "how many strangers at this moment" by weather / hour / venue / situation, **pure local formula**;
  · **Functional extras** —— carry **one demand** (debt collector, messenger), enter the decision context, exit when done;
  · **Lifespan and recycling** —— exit when the demand is resolved or expires, no zombies left behind.
Of the three tiers, "hook extras" (recurring, like a guest with a story) **was not done this
round**: it needs cross-scene memory
and a judgment of "whether it's worth promoting to a formal character card", so wait until the
minimal tier runs stably.
⚠ Two disciplines (both set by design doc §5.2):
  1. **Extras do not enter the main memory store** —— only given in "current situation", not written to the `memory` table;
  2. **Background extras do not call the model** —— the point of their existence is "someone is present", not "there is drama".
"""
from __future__ import annotations

import random
import re

from config import CFG

_LOG = __import__("logging").getLogger("nws.world.crowd")

# ── 场所基准：这一刻"本来该有多少生人"（关键词命中即可，`world.scene` 是自由文本）──
# [EN] ── Venue baseline: how many strangers there "should" be at this moment (keyword hits suffice;
# [EN] `world.scene` is free text) ──
_PLACE_BASE: tuple[tuple[str, int], ...] = (
    ("茶楼", 5), ("茶馆", 5), ("酒楼", 5), ("酒馆", 4), ("客栈", 5), ("楼", 4),
    ("街", 8), ("市", 8), ("集", 7), ("集上", 7),
    ("渡", 4), ("桥", 3), ("码头", 5), ("船", 3),
    ("铺", 3), ("店", 3), ("厂", 3), ("坊", 3),
    ("寺", 3), ("庙", 3), ("观", 2), ("祠", 1),
    ("府", 1), ("衙", 1), ("宅", 1), ("院", 2), ("书", 2), ("学", 2),
    ("驿", 3), ("关", 2), ("仓", 1),
    ("山", 0), ("野", 0), ("林", 0), ("路", 1), ("荒", 0), ("坟", 0),
)
# 时辰倍数（用 `GameTime.segment()` 的说法）
# [EN] Hour multiplier (in the terms of `GameTime.segment()`)
_SEG_MULT: dict[str, float] = {
    "清晨": 0.6, "上午": 1.0, "晌午": 1.2, "午后": 1.1,
    "傍晚": 1.0, "入夜": 0.8, "深夜": 0.3, "凌晨": 0.2,
}
# 天气倍数（关键词命中）
# [EN] Weather multiplier (keyword hits)
_WEATHER_MULT: tuple[tuple[str, float], ...] = (
    ("暴雨", 0.2), ("大雨", 0.3), ("雨", 0.5), ("雪", 0.4), ("雹", 0.2),
    ("风", 0.8), ("阴", 0.9), ("雾", 0.7), ("晴", 1.0),
)

# ── 背景群演：一行式（**给的是"场面"，不是"人物"**）──
# [EN] ── Background extras: one-liner form (**what's given is a "scene", not a "character"**) ──
_BG_BY_KIND: dict[str, list[str]] = {
    "茶楼": [
        "两个脚夫在门口歇脚，就着粗茶啃干粮",
        "邻铺的伙计过来借火，站着说了两句闲话",
        "靠窗那桌把昨日的听来的事又讲了一遍",
        "有人把茶碗盖一磕，起身结账走了",
    ],
    "街市": [
        "挑担的货郎从门口过，吆喝声拖得老长",
        "几个孩子追着一只狗跑过去了",
        "巡街的差役慢慢踱过，谁也没多看一眼",
        "卖炭的推着车停在墙根下歇气",
    ],
    "酒馆": [
        "角落里有人喝多了，趴在桌上打呼",
        "有人拍着桌子又添了一壶",
    ],
    "渡口": [
        "船工蹲在石阶上抽烟，等下一趟水",
        "有妇人抱着孩子立在岸边望船",
    ],
    "宅院": [
        "廊下有丫头捧着东西匆匆过去",
        "院里传来一下一下的扫地声",
    ],
    "野外": [
        "风把草压下去又起来",
        "远处有鸟被惊起来，扑棱棱飞走了",
    ],
    "铺子": [
        "有人在柜前挑了半天，最后什么也没买",
        "对门送来一篮新摘的果子，搁在台阶上",
    ],
}
_BG_DEFAULT = [
    "门外有脚步过去，没停",
    "有人远远看了一眼，又走开了",
]

# ── 功能群演：带**一个诉求**（"外部压力"的最小形态）──
# [EN] ── Functional extras: carry **one demand** (the minimal form of "external pressure") ──
_NEED_BY_KIND: dict[str, list[tuple[str, str]]] = {
    "茶楼": [("来讨债的", "要见掌柜，说账拖了三个月"),
             ("来找人的", "找一个说他昨天在这儿的人"),
             ("来避雨的", "坐下就不走了，也没点东西"),
             ("来传话的", "说要当面交给管事的")],
    "街市": [("丢了东西的", "说他的褡裢在这条街上没了"),
             ("卖艺的", "想在门口借块地方"),
             ("送货的", "送来一包没写寄件人的东西")],
    "渡口": [("船主", "说今天的最后一趟船不走了"),
             ("带伤的", "从水里捞上来的，问不出话")],
    "宅院": [("报信的", "递了张帖子就要走"),
             ("查税的", "拿着册子逐户点人")],
    "野外": [("过路的", "问前面还有没有人家"),
             ("猎户", "背着东西,神色不太对")],
    "铺子": [("赊账的", "说下月一定还"),
             ("退东西的", "非说这是你们家的货")],
}
_NEED_DEFAULT = [("敲门的", "敲了很久，问这一带姓什么"),
                 ("问路的", "问的地方谁也没听过")]

_MARKS = ["说话时手指总在抖", "肩上背着个不小的包袱", "走路右脚不太利索",
          "一直戴着斗笠不摘", "袖口磨得发亮", "身边跟着条黄狗"]


# ══════════════════════════════════════════════════════════════════
#  主线挂靠（2026-10-21）—— 群演是"这件事派来的人"，不是"随机路人"
# [EN] Main-line anchoring (2026-10-21) —— extras are "someone sent by this matter", not "a
# [EN] random passer-by"
# ══════════════════════════════════════════════════════════════════
# 用户原话（2026-10-21）：
#   「有些群众演员出现的没道理，群众演员出来也必须跟故事主线有关系才可以，
#     最好不要突然出来一个，没有任何作用就又退场了。群众演员临时演员的意思，
#     是在主角列表之外，承接剧情需要的演员，而不是没有任何作用，突然出现的人。」
#
# 病灶有三处，**都在"因果"上**（不是"人不够多"）：
#   ① 投人（`crew/agents.ExtraCasting`）的提示词明写"**不要直接推动主线**"
#      —— 等于教它投无关的人；
#   ② 进场（`add_extra`）**不问"他是为哪件事来的"** —— 谁都能登记；
#   ③ 退场（`tick_extras`）**按拍数到期**，和他要的事办没办成无关
#      ⇒ 出场与退场都不由剧情决定，读者看到的就是"突然来了又走了"。
#
# 所以这里的判据只有一句：**他挂在哪件事上**。
#   进门要挂得上（`anchor_ok`），挂着才留下（`tick_extras`），
#   要的事被接住了才走（`engaged`）。挂不上的**根本不投** —— 门口空着好过白来一个。
# [EN] The user's words (2026-10-21): "some extras appear for no reason; an extra must be
# [EN] related to the main story, better not to have someone suddenly appear and leave with no
# [EN] function. An extra means: outside the main cast, an actor serving what the plot needs --
# [EN] not a person who shows up for no reason."
# [EN] Three defects, all about **causality** (not "too few people"):
# [EN] 1) the casting prompt (crew/agents.ExtraCasting) explicitly says "**do not push the main
# [EN] line**" -- it literally instructs the model to cast irrelevant people;
# [EN] 2) registration (`add_extra`) **never asks "which matter did he come for"**;
# [EN] 3) exit (`tick_extras`) is **a beat countdown**, unrelated to whether his business got
# [EN] handled => arrival and departure are not decided by the plot, so the reader sees
# [EN] "suddenly came, then left".
# [EN] Hence one criterion: **which matter he is anchored to**. You must be anchorable to enter
# [EN] (`anchor_ok`), you stay only while anchored (`tick_extras`), and you leave when your
# [EN] business is taken up (`engaged`). If nothing can anchor you, **you are not cast at all**
# [EN] -- an empty door is better than a pointless visit.

#: 诉求被接住之后，还留几拍把这件事收尾（不是"立刻消失"）。
# [EN] : after the demand is taken up, how many more beats to wrap it up (not "vanish at once").
ENGAGE_AFTER = 2
#: 一拍拍等着、**没有任何人搭话**超过这么多拍 ⇒ 白来一趟，退场（并记进名册）。
#: 给它这么长是因为"门外有人站着"本身就是压力，人物要几拍才反应过来。
# [EN] : waiting beat after beat with **nobody responding** for more than this => a wasted visit,
# [EN] exit (and record into the roster). So long because "someone standing outside" is itself
# [EN] pressure; characters need a few beats to react.
FUNC_PATIENCE = 8
#: **同一条线上，一天最多来几个群演**（默认 2）。
#: 实测 run_mwl_v7：「查夜登记」一夜来了四个人（保正/保正手下伙计/赵保正/保正跟班），
#: 同一件事、全都等不到人走了，整篇被这条线绑死（茶×8、碎段 4、卫生 73.7）。
#: 用户要的是"承接剧情需要"，不是"同一份需要派五个演员轮着演"。
#: 2 而不是 1：允许"换个人再催一次"（那是施压的正常写法），不允许车轮战。
# [EN] : **how many extras may come on one thread per day** (default 2).
# [EN] Measured in run_mwl_v7: the "night registration" thread got four people in one night, all
# [EN] about the same matter, all left unaddressed, and the piece got tied to that thread
# [EN] (tea x8, 4 flat spans, hygiene 73.7). The user wants extras to "serve what the plot needs",
# [EN] not five actors taking turns on the same need. 2 rather than 1: "someone else comes to press
# [EN] again" is normal escalation; a relay race is not.
THREAD_CAST_MAX = 2

#: 算"两句话说的是不是同一件事"时要忽略的字（虚词、代词、几乎每句都有的动词）。
#: ⚠ 只用来给**规则池兜底**挑一条搭得上的线，不参与 AI 那一档的判定
#:   （AI 那档用序号，闭集，措辞无处可逃）。
# [EN] : characters ignored when judging "are these two lines about the same thing" (function
# [EN] words, pronouns, verbs in almost every sentence).
# [EN] ⚠ Only used to pick a matching thread for the **rule-pool fallback**; the AI tier uses an
# [EN] index into a closed list, so wording has nowhere to hide.
_STOP = set("的了着过是在有和就都也还又很把被让给对从向于之其这那个一不没我你他她它们"
            "要说来去会能可上下里外后前时天日")


def _one(s, cap: int = 36) -> str:
    """压成一行、限长（挂靠语要能进提示词，不能是一段话）。"""
    return " ".join(str(s or "").split()).strip()[:cap]


def _pget(p, key: str) -> str:
    """人物状态可能是 `PersonState` 也可能是 dict（存档读回来）—— 一处取法。"""
    if isinstance(p, dict):
        return str(p.get(key) or "")
    return str(getattr(p, key, "") or "")


def open_threads(world, cap: int = 6) -> list[str]:
    """此刻**正在推进的几件事**（群演只能挂在这上面）。空列表 = 门口就该空着。

    取四处，都是**现成的状态**，不调模型、不概括：
      · `active_lines` —— 故事线（设定里带来的，可能为空）；
      · `topic` —— 这一段人物**正在谈的那句原话**；
      · 每位在场人物的 `mission`（导演派给他的活）/ `goal`（他自己要的）；
      · ⚠ 不取 `need`（他真正缺的东西）—— 那是**不许说出口**的，群演不该知道。

    ★ 为什么用"清单 + 序号"而不是让模型自由写"这跟主线有什么关系"：
      自由文本的判据只能做字面比对，换个说法就归零（MEMORY：同义词是字面判据的后门）。
      序号是**闭集**：模型只能选一个已存在的编号，选不出来就是没挂上。
    
        English:
    The few things **currently moving** (extras may only anchor to these). Empty = the door should
    stay empty.
        Four sources, all **existing state**, no model call, no summarising:
          · `active_lines` -- story lines (from the setting; may be empty);
          · `topic` -- the **verbatim line** the characters are talking about right now;
          · each present person's `mission` (assigned work) / `goal` (what he wants);
          · ⚠ `need` (what he truly lacks) is **not** included -- it must never be spoken aloud,
            and an extra has no business knowing it.
        ★ Why a numbered list instead of letting the model write "how this relates to the main
          line": free text can only be judged literally, and a synonym resets it to zero (MEMORY:
          synonyms are the back door of literal criteria). An index is a **closed set**: the model
          can only pick an existing number, and failing to pick means "not anchored".
    """
    out: list[str] = []

    def add(s, n: int = 36) -> None:
        t = _one(s, n)
        if len(t) >= 2 and t not in out:
            out.append(t)

    # ★★★ 2026-10-21 真跑修正：**顺序就是优先级**，而 `topic` 必须排在最后。
    #   实测 mwl_v5：清单把"这一段在谈的那句话"排在人物的活前面，AI 从
    #   「水底看不见月亮」里读出的不是一件事，是**氛围** ⇒ 投出来的六个群演是
    #   「还伞的脚夫」「赶夜路的皮货客」「茶炉杂役」——都是背景音，没有压力。
    #   而 mwl_v4（规则池）投的是「讨账的」——**压力型来客**，天然逼掌柜表态。
    #   话题是"他们在说什么"，事件是"有什么必须办"；**派活与投人只该挂后者**。
    # [EN] ★★★ Corrected after a real run on 2026-10-21: **order is priority**, and `topic`
    # [EN] must come last. Measured in mwl_v5: the list put "the line they are talking about"
    # [EN] ahead of the characters' work, and what the model read out of "you can't see the moon at
    # [EN] the bottom of the well" was not a matter but **atmosphere** => the six extras cast were
    # [EN] "the porter returning an umbrella", "the traveller of the night road", "the stove hand" --
    # [EN] all background noise, no pressure. mwl_v4 (rule pool) cast "the debt collector" -- a
    # [EN] **pressure visitor** that forces the shopkeeper to take a position. A topic is "what they
    # [EN] are saying"; an event is "what must be done". Dispatching and casting should only hang on
    # [EN] the latter.
    for x in (getattr(world, "active_lines", None) or []):
        add(x)
    people = getattr(world, "people", None) or {}
    try:
        rows = list(people.values())
    except AttributeError:                       # 不是 dict 就当没有（别在这里炸）
        rows = []
    for p in rows[:8]:
        add(_pget(p, "mission"))
        add(_pget(p, "goal"))
    add(getattr(world, "topic", ""))
    return out[:cap]


def topic_thread(world) -> str:
    """只剩下"这一段在谈什么"那一句（没有说话可谈时为空）。

    ★ 它**不算一件事**：`open_threads` 把它排在最后、`has_pressure` 不认它。
      留这个函数是为了让别处能显式区分"他们在谈"与"有事要办"。
    [EN] Only the "what this stretch is about" line (empty when nothing is being said).
        ★ It is **not a matter**: `open_threads` puts it last and `has_pressure` ignores it.
        Kept so other places can explicitly tell "they are talking" from "there is work to do".
    """
    return _one(getattr(world, "topic", ""))


def anchor_ok(world, cast: dict) -> tuple[str, str]:
    """这个人**挂在哪件事上**？返回 `(挂靠语, 不行的理由)`。

    三条路都通：
      · 挂靠语就在 `open_threads()` 里 —— 正常路径（投人时选了个序号）；
      · `钩子` 群演 —— 他上回没办完的那件事本身就是一条线（跨场记忆的意义所在）；
      · 别的都**不登记**。
    
        English:
    **Which matter is this person anchored to?** Returns `(anchor, reason_if_bad)`.
        Three accepted paths: the anchor is in `open_threads()` (the normal path -- an index was
        picked when casting); a `钩子` extra (the business he left unfinished last time *is* a
        thread, which is the whole point of cross-scene memory); everything else is **refused**.
    """
    anchor = _one((cast or {}).get("挂"))
    if not anchor:
        return "", "没说他是为哪件事来的"
    if (cast or {}).get("钩子"):
        return anchor, ""
    if anchor in open_threads(world):
        return anchor, ""
    return "", "他挂的那件事此刻不在推进"


def _overlap(a: str, b: str) -> int:
    """两句话共用了几个"实字"（去掉虚词）。给规则池兜底挑线用。"""
    sa = {c for c in str(a or "") if "\u4e00" <= c <= "\u9fff" and c not in _STOP}
    sb = {c for c in str(b or "") if "\u4e00" <= c <= "\u9fff" and c not in _STOP}
    return len(sa & sb)


def engaged(world, e: dict) -> bool:
    """这个群演要的事，**这一场里有人接住了吗**？

    判据只有两条（都要，且都廉价）：
      · 有人**叫出了他**（`recent_lines` 里出现他的称呼）；
      · 或者有人**对着他说话**（`to` 就是他的称呼）。

    ★★★ 2026-10-21 真跑修正：**去掉了"诉求与台词共用 ≥2 个实字"那一条**。
      实测：打更人的诉求是「见掌柜，说白衣客没影子」，而同一拍阿九心里想的是
      「柳氏坐桌边没有影子」—— 共用「没/有/影/子」**4 个实字**，于是被判
      "有人接住了他"。其实**没人在跟他说话**，那是阿九自己在犯疑。
      后果正好相反：它被当成"已接"，两拍后静默退场，正文里一次都没出现。
      ⚠ 这条错误的性质是「拿**内容重合**当**有人在理他**」——两件事。
        "他说的那件事被谁想起了"不等于"谁在跟他打交道"。
      ⚠ 所以判据只认**指向他的字**：称呼（专有标识，不是同义词，没有后门），
        以及 `to`（谁在对谁说）—— 都是**关系**，不是**内容**。

    ⚠ 为什么不问模型"他办成了吗"：一问就多一次调用，而且它答的是"他觉得"；
      而"称呼被叫到 / 有人对着他说"是**已经在场上的字**，可数、可复现。
    ⚠ 只看 `recent_lines`（当场听得见的）：群演不在记忆主库里，
      隔了三天的台词不算"接住了他"。
    
        English:
    Did anyone **take up** what this extra wants, in this scene?
        Two cheap criteria (either): someone **names him** in `recent_lines`; or someone **speaks
        to him** (`to` is his appellation).
        ★★★ Corrected after a real run (2026-10-21): **the "demand shares >= 2 content characters
        with a line" rule is gone**. Measured: the night watchman's demand was "see the manager,
        say the white-robed guest casts no shadow", while in the same beat Chen Wang was thinking
        "Lady Liu sits by the table with no shadow" -- they share 4 content characters, so it was
        judged "someone took him up". Nobody was talking to him; that was Chen Wang's own doubt.
        The consequence was inverted: he counted as "taken up", left quietly two beats later, and
        never appeared in the prose once.
        ⚠ The error was treating **overlapping content** as **someone dealing with him**. "Someone
        remembered the thing he mentioned" is not "someone is dealing with him".
        ⚠ So the criteria only accept **words that point at him**: his appellation (a proper label,
        not a synonym, no back door) and `to` (who is speaking to whom) -- both are **relations**,
        not **content**.
        ⚠ Why not ask the model "did he get what he wanted": that costs a call and answers "what
        it thinks"; whereas "his name / someone addressing him" is **already on the page**.
        ⚠ Only `recent_lines` (audible right here): extras are not in the main memory store, so a
        line from three days ago does not count as "taken up".
    """
    who = str(e.get("称呼") or "").strip()
    if len(who) < 2:
        return False
    for r in (getattr(world, "recent_lines", None) or [])[-24:]:
        r = r or {}
        if str(r.get("to") or "").strip() == who:
            return True
        if who in str(r.get("text") or ""):
            return True
    return False


def scene_kind(scene: str) -> str:
    """场所归类（茶楼 / 街市 / 酒馆 / 渡口 / 宅院 / 野外 / 铺子）。
        English:
    Venue categories (teahouse / street market / tavern / ferry / courtyard / wilderness / shop).
    """
    s = str(scene or "")
    for kw, kind in (("茶", "茶楼"), ("楼", "茶楼"), ("酒", "酒馆"),
                     ("街", "街市"), ("市", "街市"), ("集", "街市"),
                     ("渡", "渡口"), ("桥", "渡口"), ("码头", "渡口"), ("船", "渡口"),
                     ("宅", "宅院"), ("院", "宅院"), ("府", "宅院"), ("衙", "宅院"),
                     ("山", "野外"), ("野", "野外"), ("林", "野外"), ("路", "野外"),
                     ("铺", "铺子"), ("店", "铺子"), ("坊", "铺子")):
        if kw in s:
            return kind
    return "铺子"


def crowd_size(world) -> int:
    """这一刻**门外/堂里有几个生人**。纯本地算式，零成本。

    三个因子相乘：场所基准 × 时辰倍数 × 天气倍数，再加一点"局势"加成
    （街上刚出过事 → 看热闹的人反而多）。返回 0 表示"这会儿没人来"。
    
        English:
    How many strangers **outside the door / in the hall** at this moment. Pure local formula, zero
    cost.
        Multiply three factors: venue baseline × hour multiplier × weather multiplier, plus a bit of "situation" bonus
        (something just happened on the street → more onlookers instead). Returning 0 means "nobody comes right now".
    """
    base = 0
    scene = str(getattr(world, "scene", "") or "")
    for kw, v in _PLACE_BASE:
        if kw in scene:
            base = max(base, v)
    if base == 0:
        base = 2                                    # 认不出的场所：默认有点人
        # [EN] Unrecognizable venue: default to some people
    seg = "上午"
    clock = getattr(world, "clock", None)
    if clock is not None and hasattr(clock, "segment"):
        try:
            seg = clock.segment()
        except Exception:                           # noqa: BLE001
            pass
    mult = _SEG_MULT.get(seg, 1.0)
    weather = str(getattr(world, "weather", "") or "")
    for kw, m in _WEATHER_MULT:
        if kw in weather:
            mult *= m
            break
    try:
        if float(getattr(world, "tension", 0.0) or 0.0) > 0.6:
            mult += 0.3                             # 出了事 → 看热闹的
            # [EN] Something happened → onlookers
    except (TypeError, ValueError):
        pass
    n = int(round(base * mult))
    # 夜间在"做夜生意"的茶楼反而有人：这是《临河茶肆》那类故事的常见设置，
    # 但**不硬编码剧情** —— 只给一个温和的加成，具体有没有夜客由世界设定说了算。
    # [EN] At night, teahouses "doing night business" are instead crowded: this is the common setup for [EN] stories like《临河茶肆》,
    # [EN] but **do not hardcode plot** —— only give a mild bonus; whether there are actually night guests
    # [EN] is up to the world settings.
    if seg in ("入夜", "深夜") and scene_kind(scene) in ("茶楼", "酒馆"):
        n = max(n, 2)
    return max(0, n)


def _bg_lines(world, n: int, rng: random.Random) -> list[str]:
    """挑 `n` 条背景"场面"。**优先挑最近没用过的**。

    ⚠ 为什么要避重（2026-10-07，用户报「对话又死循环了」）：
    茶楼那类池子只有 4 条，而背景群演**寿命短、补得勤** ——
    每拍都可能补人，抽出来的还是那 4 条里的，屏幕上就变成同一句反复出现
    （截图里「（邻铺的伙计过来借火，站着说了两句闲话走了）」连着出现 4 次）。
    这里给 `world.bg_recent` 记最近用过的，**先把没用过的挑完**；
    凑不够 `n` 才允许重复（并清空记忆，免得池子太小导致永远挑不出人）。
    
        English:
    Pick `n` background "scenes". **Prefer picking the most recently unused**.
        ⚠ Why avoid repeats (2026-10-07, user reported "dialogue in an infinite loop again"):
        That kind of pool for teahouses has only 4 entries, and background extras **have short lifespans and are topped up frequently** ——
        every beat may top up people, and the ones drawn are still from those 4, so on screen the same line repeatedly appears
        Here `world.bg_recent` records the most recently used, **first pick all the unused ones**;
        only when not enough to fill `n` are repeats allowed (and clear the memory, lest a too-small pool cause never being able to pick anyone).
    """
    kind = scene_kind(str(getattr(world, "scene", "") or ""))
    pool = list(_BG_BY_KIND.get(kind, [])) or list(_BG_DEFAULT)
    recent = [x for x in (getattr(world, "bg_recent", None) or []) if x in pool]
    fresh = [x for x in pool if x not in recent]
    if len(fresh) < n:                 # 没用过的凑不够 → 允许重复，并把记忆清空
    # [EN] If unused ones cannot fill the quota → allow repeats, and clear the memory
        fresh, recent = list(pool), []
    rng.shuffle(fresh)
    picked = fresh[:n]
    # 记忆只留最近的一小段（留太多会把整个池子都记成"用过"）
    # [EN] Memory only keeps the most recent short segment (keeping too much will mark the whole pool as
    # [EN] "used")
    keep = max(1, min(len(pool) - 1, n * 2))
    world.bg_recent = (picked + recent)[:keep]
    return picked


# ── 背景群演的**寿命**与**播报节流**（刻意给成常量，不是旋钮）──
# [EN] ── Background extras' **lifespan** and **broadcast throttling** (deliberately constants, not
# [EN] knobs) ──
#
# 理由同 `HOOK_RETURN`：这两项是**叙事手感**，不是成本开关 ——
# 旋钮太多反而没人调得动。
# [EN] Reason same as `HOOK_RETURN`: these two are **narrative feel**, not cost switches ——
# [EN] too many knobs and nobody can tune them anyway.
#
# ⚠ 以前寿命是**写死的 3 拍**，而每拍都会把背景群演补到 `EXTRAS_MAX_ALIVE`：
#   "补满 → 3 拍后一起退 → 又补满"，于是**每 3 拍必有一批退场**，
#   节奏机械得像节拍器，屏幕上就是一条接一条的「（…走了）」（用户 2026-10-07
#   报的"死循环"）。改成**随机 2~6 拍**，同一批人不会踩着同一步调走。
# [EN] ⚠ Previously the lifespan was **hardcoded to 3 beats**, and every beat topped background extras
# [EN] up to `EXTRAS_MAX_ALIVE`:
# [EN] "top up → all leave together after 3 beats → top up again", so **every 3 beats a batch must
# [EN] exit**,
# [EN] the rhythm mechanical like a metronome, on screen one "(…left)" after another (user 2026-10-07
# [EN] reported "infinite loop"). Changed to **random 2~6 beats**, so the same batch won't leave in
# [EN] lockstep.
BG_LIFE = (2, 6)
#: 背景群演退场**最多**每这么多拍报一句"换过一拨"。
#: 它们来去是**背景**，不该像事件一样占一行字 —— 但也不能一点现场感都没有。
#: 功能/钩子群演（"有事的那个"）不受这条限制：那才是值得点名的。
# [EN] : Background extras exiting report one line of "a new batch has come" at **most** every this
# [EN] many beats.
# [EN] : Their coming and going is **background**, and should not occupy a line of text like an event
# [EN] —— but it also should not be entirely without a sense of presence.
# [EN] : Functional/hook extras ("the one with business") are not subject to this restriction: those
# [EN] are the ones worth naming.
BG_NOTICE_EVERY = 12


def sync_crowd(world, rng: random.Random | None = None) -> None:
    """让"背景群演"的数量跟上客流。多了减、少了补（**不跑模型**）。
        English:
    Make the number of "background extras" keep up with foot traffic. Reduce when too many, top up
    when too few (**no model run**).
    """
    if not CFG.b("EXTRAS_ENABLED"):
        return
    rng = rng or random.Random()
    want = min(crowd_size(world), max(0, CFG.i("EXTRAS_MAX_ALIVE")))
    bg = [e for e in getattr(world, "extras", []) if e.get("kind") == "背景"]
    other = [e for e in getattr(world, "extras", []) if e.get("kind") != "背景"]
    keep = max(0, want - len(other))
    if len(bg) > keep:
        bg = bg[:keep]
    elif len(bg) < keep:
        life_lo, life_hi = BG_LIFE
        for line in _bg_lines(world, keep - len(bg), rng):
            bg.append({"kind": "背景", "一行": line,
                       "剩余": rng.randint(life_lo, life_hi)})
    world.extras = other + bg


def can_cast(world) -> bool:
    """现在**允不允许**造一个功能群演？（三条闸门：总开关 · 同场上限 · 当日预算）

    ★ 2026-10-07 抽出来的公共判据。为什么必须抽：功能群演现在有**两条**造法 ——
    规则池（`new_extra`）与剧组里「群众演员」投人（`crew/agents.ExtraCasting`）。
    两条路各判一遍闸门，迟早会漂（"AI 那条路绕过了预算"这种 bug 最难看出来，
    因为它只在花了钱之后才显形）。**判据一处、两条路共用。**
    
        English:
    Now, **are we allowed** to create a functional extra? (Three gates: master switch · same-scene
    cap · daily budget)
        ★ Common criterion extracted on 2026-10-07. Why it must be extracted: functional extras now have **two** creation paths ——
        the rule pool (`new_extra`) and casting "background actors" from the crew (`crew/agents.ExtraCasting`).
        If each path judges the gates on its own, they will drift sooner or later ("the AI path bypassed the budget" is the hardest kind of bug to spot,
        because it only shows up after money has been spent). **One criterion, shared by both paths.**
    """
    if not CFG.b("EXTRAS_ENABLED"):
        return False
    alive = [e for e in getattr(world, "extras", []) if e.get("kind") == "功能"]
    if len(alive) >= max(1, CFG.i("EXTRAS_MAX_ALIVE") // 2):
        return False
    if int(getattr(world, "extras_today", 0) or 0) >= max(0, CFG.i("EXTRAS_DAILY_BUDGET")):
        return False
    return True


def add_extra(world, cast: dict, rng: random.Random | None = None) -> dict | None:
    """把**已经定好的人**（谁、要什么、什么标志）登记成一个功能群演。

    与 `new_extra` 的分工：那个是"从池子里抽一个"，这个是"已经有人了，登记一下"。
    剧组里「群众演员」投出来的人走这里 —— 这样外面（`sim/loop`）不必知道
    `extras` 这条记录的字段长什么样。

    ★ **同一个人不重复在场**（2026-10-07 修）：返回 `None` = 这次没来。
      表现是"门外已经有了一个讨账的伙计，又来了一个讨账的伙计" ——
      真机上也会发生（规则池只有那么几条、模型投出来的也会撞），
      而它的后果是**退场时播报成「（讨账的伙计走了；讨账的伙计走了）」**。
      同一个人不会有两个，所以这里直接不收。

      三个来源都走这一个函数（规则池 / 剧组投人 / 别处登记），
      所以去重放在这里是**一处管住三个来源**。
    
        English:
    Register **already-decided people** (who, what they want, what marker) as a functional extra.
        Division of labor with `new_extra`: that one is "draw one from the pool", this one is "someone is already here, just register them".
        People cast by "background actors" in the crew go through here —— this way the outside (`sim/loop`) doesn't need to know
        what the fields of this `extras` record look like.
        ★ **The same person is not present twice** (fixed 2026-10-07): returning `None` = they didn't come this time.
          The symptom is "there's already a debt collector at the door, and another debt collector arrives" ——
          this also happens on real hardware (the rule pool only has so many entries, and model-cast ones can collide too),
          and its consequence is that **on exit it broadcasts as "(the debt collector left; the debt collector left)"**.
          The same person cannot be two, so we simply don't accept them here.
          All three sources go through this one function (rule pool / crew casting / registration elsewhere),
          so putting dedup here means **one place controls three sources**.
    """
    rng = rng or random.Random()
    who = str((cast or {}).get("称呼") or "路人")[:12]
    need = str((cast or {}).get("诉求") or "")[:40]
    mark = str((cast or {}).get("标志") or "")[:12]
    # ★★★ 2026-10-21：**挂不上主线的人不登记**（用户报"群众演员出现没道理"）。
    #   这道闸放在 `add_extra` 而不是 `cast()` 里，因为这里是**三个来源**的唯一漏斗
    #   （规则池 / 剧组投人 / 别处登记）—— 判据一处，三条路都拦。
    #   挡掉的表现是"门口本来就没人来"，那是**对的**：白来一个比空着更伤戏。
    # [EN] ★★★ 2026-10-21: **someone who cannot be anchored to the main line is not registered**
    # [EN] (the user reported "extras appear for no reason"). The gate lives in `add_extra`, not
    # [EN] `cast()`, because this is the single funnel for **all three sources** -- one criterion,
    # [EN] three paths blocked. The visible result is "nobody came to the door", which is
    # [EN] **correct**: a pointless visit hurts the story more than an empty doorway.
    anchor, why = anchor_ok(world, cast or {})
    if not anchor:
        _LOG.info("这个临时演员不登记（%s）：%s", who, why)
        return None
    # ★★★ 2026-10-21 第四次真跑：**同一条线上，别一晚上来五拨人**。
    #   实测 run_mwl_v7：「查夜登记」这一条线上，一夜投出「保正」「保正手下伙计」
    #   「赵保正」「保正跟班」——四个人**同一件事**，全都等不到人走了，
    #   而整篇被这条线绑死（道具循环「茶」×8、碎段 4、卫生 73.7，是四版里最差）。
    #   用户要的是"群演承接剧情需要"，不是"同一份需要派五个演员来演一遍"。
    #   ⇒ 同一条线一天最多来 `THREAD_CAST_MAX` 个（默认 2：允许"换个人再催一次"，
    #     不允许"车轮战"）。
    #   ⚠ **钩子群演豁免**：老熟人回来挂的正是他上回那件事，那本来就该让他进
    #     （跨场记忆的意义就在这儿）。
    # [EN] ★★★ Fourth real run (2026-10-21): **one thread, not five visitors a night**.
    # [EN] Measured in run_mwl_v7: on the "night registration" thread, one evening cast four
    # [EN] people -- all about the SAME matter, all left unaddressed, and the whole piece got tied
    # [EN] to that thread (prop cycle "tea" x8, 4 flat spans, hygiene 73.7 -- the worst of four
    # [EN] versions). The user wants extras to "serve what the plot needs", not five actors playing
    # [EN] the same need in turn. => At most `THREAD_CAST_MAX` per thread per day (default 2:
    # [EN] "someone else comes to press again" is allowed, "relay race" is not).
    # [EN] ⚠ **Hook extras are exempt**: a returning acquaintance is anchored to his own unfinished
    # [EN] business, which is exactly the point of cross-scene memory.
    if not (cast or {}).get("钩子"):
        try:
            used = getattr(world, "extras_by_thread", None)
            if used is None:
                world.extras_by_thread = used = {}
            if int(used.get(anchor, 0) or 0) >= THREAD_CAST_MAX:
                _LOG.info("「%s」这件事今天已经来过 %d 个人了，不再派人（同一条线不车轮战）",
                          anchor, used.get(anchor))
                return None
        except Exception:                                    # noqa: BLE001
            pass
    key = f"{who}|{mark}"
    for old in (getattr(world, "extras", None) or []):
        if _hook_key(old) == key:
            _LOG.info("门外已经有「%s」了，这个不再登记（同一个人不会有两个）", who)
            return None
        # ★★★ 2026-10-21 真跑修（第四次）：**换个称呼不算另一个人**。
        #   实测 run_mwl_v7：因为"查夜登记"这条线，一晚投出「保正」「保正手下伙计」
        #   「赵保正」「保正跟班」「保正」五个人 —— 去重键是 `称呼|标志`，
        #   这四个称呼**两两不相等**，于是全部放行。读者看到的是"保正怎么又来一次"。
        #   这是 MEMORY 里那条老病：**同义词是字面判据的后门**。
        #   判据改成"互相包含即同一人"（≥2 字才判，"老王"⊂"老王爷"这类不误伤）。
        # [EN] ★★★ Fixed after the fourth real run (2026-10-21): **a different appellation is not
        # [EN] a different person**. Measured in run_mwl_v7: because of the "night registration"
        # [EN] thread, one evening cast five people -- "the constable", "the constable's man",
        # [EN] "Constable Zhao", "the constable's follower" -- and since the dedup key is
        # [EN] `appellation|marker` and those four are pairwise unequal, all went through. What the
        # [EN] reader sees is "why is the constable back again". This is the old MEMORY disease:
        # [EN] **synonyms are the back door of literal criteria**. The criterion is now "mutually
        # [EN] contained counts as the same person" (only when >= 2 chars, so "Wang" inside
        # [EN] "Old Master Wang" is not misjudged).
        try:
            old_who = str(old.get("称呼") or "")
            if len(who) >= 2 and len(old_who) >= 2 and (who in old_who or old_who in who):
                _LOG.info("门外已经有「%s」了（这个叫「%s」，是同一个人），不再登记",
                          old_who, who)
                return None
        except Exception:                                    # noqa: BLE001
            pass
    e = {
        "kind": "功能",
        "称呼": who,
        "诉求": need,
        "标志": mark,
        # 他**为哪件事来的**（进门时说的话）+ 一句"怎么搭上的"
        # [EN] **which matter he came for** (said at the door) + one line on how he connects
        "挂": anchor,
        "接": _one((cast or {}).get("接"), 20),
        # 等了多久没人搭话（`tick_extras` 数；到了 `FUNC_PATIENCE` 就走）
        # [EN] how long he has waited with nobody responding (`tick_extras` counts; leaves at
        # [EN] `FUNC_PATIENCE`)
        "候": 0,
        # 这一拍刚进门：第一拍只让他被看见，不判生死
        # [EN] just walked in this beat: the first beat only lets him be seen, no life-or-death call
        "新": True,
        "一行": f"{who}——{need}",
    }
    world.extras.append(e)
    world.extras_today = int(getattr(world, "extras_today", 0) or 0) + 1
    # 记一笔"这条线上今天来过几个"（去重看它，见上面那段）
    # [EN] Record "how many have come on this thread today" (the dedup above reads it)
    try:
        used = getattr(world, "extras_by_thread", None)
        if used is None:
            world.extras_by_thread = used = {}
        used[anchor] = int(used.get(anchor, 0) or 0) + 1
    except Exception:                                        # noqa: BLE001
        pass
    return e


def waiting(world, *, min_wait: int = 1) -> list[dict]:
    """门口**还等着、没人理**的功能群演（导演派活要用这张单子）。

    ★★★ 为什么必须有这一层（2026-10-21 真跑判决）：
      mwl_v5 来了 6 个群演、**正文出现 0 次**。查日志，打更人进门那一拍，
      导演派的三条活是「回屋歇下」「吩咐续茶」「低念一句」——**没有一条与他有关**。
      也就是说：群演进门了、被看见了、进了决策提示词，**但没有任何人被要求去理他**。
      人物各忙各的，他站几拍、等不到人、走掉。这正是用户说的
      "突然出来一个，没有任何作用就又退场了"——**根因不在群演，在没人接**。

    判据可数：`kind=功能` + 有 `挂` + 没 `已接` + 已等 `min_wait` 拍。
    
        English:
    Functional extras **still waiting at the door and unaddressed** (the list the director's
    dispatch needs).
        ★★★ Why this layer must exist (verdict from a real run on 2026-10-21): mwl_v5 brought in 6
        extras and they appeared **zero times** in the prose. The log shows that on the beat the
        night watchman arrived, the director assigned three tasks -- "go back and rest", "tell him to
        pour tea", "murmur a line" -- **none of them about him**. So: the extra arrived, was seen,
        entered the decision prompt, **but nobody was asked to deal with him**. Everyone went about
        their business; he stood a few beats, got no response, and left. This is exactly the user's
        "someone suddenly appears and leaves with no function" -- **the root cause is not the extra,
        it is that nobody takes him up**.
        Countable: `kind=功能` + has `挂` + not `已接` + has waited `min_wait` beats.
    """
    out: list[dict] = []
    for e in (getattr(world, "extras", None) or []):
        if str(e.get("kind") or "") != "功能":
            continue
        if not str(e.get("挂") or "") or e.get("已接"):
            continue
        if int(e.get("候", 0) or 0) < min_wait:
            continue
        out.append(e)
    return out


def waiting_line(world, *, min_wait: int = 1) -> list[str]:
    """门口等着的人，一句一个（**按序号排**，给派活的提示词用）。

    写法里带着"他为什么在这儿"，导演才派得出与他有关的活：
        `打更人——见掌柜，说白衣客没影子（为「柳氏没有影子」来的）`
    
        English:
    The waiting people, one per line (**numbered**, for the dispatch prompt).
        The line carries "why he is here", so the director can assign something about him:
        `night watchman -- see the manager, say the white-robed guest casts no shadow (here about
        "Lady Liu has no shadow")`
    """
    return [f"{str(e.get('称呼') or '有人')}——{str(e.get('诉求') or '')}"
            f"（为「{_one(e.get('挂'), 18)}」来的）"
            for e in waiting(world, min_wait=min_wait)]


def handoff_line(e: dict) -> str:
    """给"门口这位"派活时用的那句话（**是"要什么"，不是"怎么做"**）。

    形如：`先了结门口「打更人」的事（他说白衣客没影子）`
    ⚠ 只写"要达成什么"：不提"去门口问一句"这种动作步骤 —— 那是人物的自由
      （派活的硬线，见 `director.engine.dispatch`）。
    
        English:
    The line used when assigning work about "the one at the door" (**what is wanted, not how**).
        Like: `settle the matter of the night watchman at the door first (he says the white-robed
        guest casts no shadow)`
        ⚠ Only "what to achieve": no action steps like "go to the door and ask" -- that is the
        character's freedom (the hard line of dispatch, see `director.engine.dispatch`).
    """
    who = str(e.get("称呼") or "有人")
    need = _one(e.get("诉求"), 20)
    return f"先了结门口「{who}」的事" + (f"（{need}）" if need else "")


def pick_handler(world, e: dict, names: list[str]) -> str:
    """这件事该派给谁：在场人里**与这条线最相关**的那个。

    判据：他的 `mission`/`goal` 与群演的 `挂`/`诉求` 共用实字最多的人。
    全 0（谁都搭不上）⇒ 取在场的第一个人 —— **总要有人管门口**，
    这比"谁都不管"好；而"谁都不管"正是实测到的那个结局。
    
        English:
    Who should get this: the present character **most related to this thread**.
        Criterion: whoever's `mission`/`goal` shares the most content characters with the extra's
        anchor/demand. All zero (nobody connects) => take the first person present -- **somebody has
        to mind the door**, which beats "nobody does"; and "nobody does" is exactly the outcome
        measured.
    """
    who_list = [str(n) for n in (names or []) if n]
    if not who_list:
        return ""
    target = f"{str(e.get('挂') or '')} {str(e.get('诉求') or '')}"
    best, best_n = who_list[0], -1
    people = getattr(world, "people", None) or {}
    for n in who_list:
        p = people.get(n) if hasattr(people, "get") else None
        own = f"{_pget(p, 'mission')} {_pget(p, 'goal')}" if p is not None else ""
        score = _overlap(own, target)
        if score > best_n:
            best, best_n = n, score
    return best


def unhandled(world, assignments) -> list[dict]:
    """派完活之后，门口**仍然没人被派去理**的那几位。

    ★ 判据：这批派活里有没有任何一条**提到他的称呼或他那件事**。
      提到就算"有人接了"——写的是"要什么"，人物怎么接是他的事。
    ⚠ 这一条不看 `engaged`（那是"已经有人跟他说上话了"）。这一层管的是
      **派活有没有把他算进去**，是 `engaged` 的上游：先有人被要求去理他，
      才可能有人真的理他。两者混成一件事，就会"派活明明没算他，
      却因为别人碰巧提了一句而判'已经接住了'"—— 实测就是这么错的。
    
        English:
    After dispatch, the ones at the door whom **nobody was assigned to deal with**.
        ★ Criterion: does any assignment **mention his appellation or his matter**. Mentioning
          counts as "someone took him up" -- assignments state "what is wanted"; how to take it up
          is the character's business.
        ⚠ This does not look at `engaged` (which means "someone has actually spoken with him"). This
          layer is about **whether dispatch accounted for him at all**, i.e. upstream of `engaged`:
          someone must first be asked to deal with him before anyone can. Merging the two produces
          "dispatch never counted him, yet a passing mention by someone else is read as 'taken up'"
          -- which is exactly the measured error.
    """
    texts = [str(v or "") for v in (assignments or {}).values()]
    if isinstance(assignments, dict):
        texts = [f"{k} {v}" for k, v in assignments.items()]
    out: list[dict] = []
    for e in waiting(world):
        who = str(e.get("称呼") or "")
        need = str(e.get("诉求") or "")
        if any((who and who in t) or _overlap(t, need) >= 3 for t in texts):
            continue
        out.append(e)
    return out


def pick_from_pool(world, rng: random.Random | None = None, *,
                   anchor: str = "") -> dict | None:
    """规则池里挑一个**跟某件正在推进的事搭得上**的人。只挑，不登记。

    与 `new_extra` 的分工：那个是"挑一个并登记"，这个是"给我一个人选"
    （剧组投人那条路自己会走 `add_extra` 登记，不能再登记第二遍）。

    ★ 判据：池子里那条诉求必须跟目标线**共用 ≥2 个实字**，否则返回 None。
      看起来粗，但它是**可数的**：一条线讲"账拖了三个月"，池里"要见掌柜，
      说账拖了三个月"能对上；讲"阿枝找她爹"就一个也对不上 ⇒ 这次不投。
      ⚠ 这就是"门口空着好过白来一个"的落实处。
    
        English:
    Pick a rule-pool person **who connects to something currently moving**. Pick only, do not
    register.
        Division of labor with `new_extra`: that one picks **and** registers; this one hands back a
        candidate (the crew casting path registers via `add_extra` itself and must not register
        twice).
        ★ Criterion: the pool demand must share **>= 2 content characters** with the target
          thread, else None. Crude, but **countable**: a thread about "the debt is three months
          overdue" matches "wants to see the shopkeeper, says the debt is three months overdue";
          a thread about "Azhi looking for her father" matches nothing => nobody is cast.
          ⚠ This is where "an empty door beats a pointless visit" is enforced.
    """
    rng = rng or random.Random()
    threads = open_threads(world)
    if not threads:
        return None
    kind = scene_kind(str(getattr(world, "scene", "") or ""))
    pool = list(_NEED_BY_KIND.get(kind, [])) or list(_NEED_DEFAULT)
    best: tuple[int, str, str, str] | None = None
    for th in ([anchor] if anchor else threads):
        who, need = max(pool, key=lambda wn: _overlap(wn[1], th))
        score = _overlap(need, th)
        if best is None or score > best[0]:
            best = (score, th, who, need)
    if best is None or best[0] < 2:
        return None
    _score, th, who, need = best
    return {"称呼": who, "诉求": need, "标志": rng.choice(_MARKS),
            "挂": th, "接": "（规则池）"}


def new_extra(world, rng: random.Random | None = None, *,
              anchor: str = "") -> dict | None:
    """按缺口造一个**功能群演**（带一个诉求）。返回它，或 None（闸门/挂靠拦下）。

    三条闸门：总开关 · 同场上限 · 当日预算。**都不满足就干脆不造** ——
    群演是"外部输入"，不是"必须凑够的人数"。

    ★★★ 2026-10-21 起多一道**挂靠闸**：池子里的人必须跟"此刻正在推进的某件事"
      搭得上（共用 ≥2 个实字）才准进来。搭不上就**不投** —— 门口空着是对的。
      ⚠ 以前是 `rng.choice(pool)`：抽到谁算谁，和这一场在演什么毫无关系，
        正是用户说的"突然出来一个，没有任何作用又退场"。

    ⚠ 这是**规则那一档**（从 `_NEED_BY_KIND` 池子里抽）。真机上优先走
      剧组里「群众演员」的投人（`crew/agents.ExtraCasting`），抽池子只是兜底 ——
      池子抽出来的人每次都长一个样，用多了人物就学会无视它们。
    
        English:
    Create a **functional extra** (with one want) based on the gap. Return it, or None (blocked by a
    gate or by anchoring).
        Three gates: master switch · same-scene cap · daily budget. **If none are satisfied, just don't create** ——
        extras are "external input", not "a headcount that must be filled".
        ★★★ Since 2026-10-21 there is one more **anchoring gate**: a pool person must connect to
        "something currently moving" (sharing >= 2 content characters) to be allowed in. If not,
        **do not cast** -- an empty doorway is correct.
        ⚠ It used to be `rng.choice(pool)`: whoever was drawn, regardless of what this scene is
          about -- exactly the user's "someone suddenly appears and leaves with no function".
        ⚠ This is the **rule tier** (drawing from the `_NEED_BY_KIND` pool). On real hardware, prefer
          casting "background actors" from the crew (`crew/agents.ExtraCasting`); drawing from the pool is only a fallback ——
          people drawn from the pool look the same every time, and with overuse the characters learn to ignore them.
    """
    if not can_cast(world):
        return None
    rng = rng or random.Random()
    got = pick_from_pool(world, rng, anchor=anchor)
    if got is None:
        _LOG.info("规则池里没有跟这一场搭得上的人，这次不投（门口空着好过白来一个）")
        return None
    return add_extra(world, got, rng)


def tick_extras(world) -> list[dict]:
    """群演过一拍。返回**退场名单**（每项 `{'kind','label'}`，空等的人多一个 `空等: True`）。

    ★★★ 2026-10-21：**有挂靠的功能群演不再按拍数退场**（用户报"没有任何作用就又退场"）。
      两种人两种走法：

        · **背景群演** —— 场面，没有人会"办完事"，照旧按 `剩余` 走；
        · **有 `挂` 的功能/钩子群演** —— 按**他要的那件事有没有被接住**：
            - 被接住了（`engaged`）→ 再留 `ENGAGE_AFTER` 拍收尾，然后走；
            - 一直没人搭话 → 等满 `FUNC_PATIENCE` 拍，**空等而走**（`空等: True`），
              并记进钩子名册 —— 他下次回来时带着"上回没办完的事"，那一趟就不白来。
        · **没有 `挂` 的老存档记录** —— 老规矩按 `剩余` 走（存档里没有挂靠信息，
          不能凭空判"他走没走成"）。⚠ 生产路径已经造不出这种记录：`add_extra` 会拦。

    ⚠ 第一拍只让新人被看见（`新` 标记），不判生死 —— 刚进门就"等不到人"是荒谬的。

    每项是 `{'kind': '背景'|'功能'|'钩子', 'label': '…'}` ——
    **带上 kind 是刻意的**：调用方要靠它决定"这句话值不值得上屏"
    （背景来去是背景，功能/钩子才是"有事的那个"，见 `exit_notice()`）。

    ★ 退场时把"值得记住的人"写进钩子名册（`remember_hook`）——
    这是"下次还认得他"的唯一入口。
    
        English:
    Extras advance one tick. Returns the **exit list** (each `{'kind','label'}`, plus `空等: True`
    for those who waited in vain).
        ★★★ 2026-10-21: **anchored functional extras no longer exit on a beat count** (user reported
        "leaves with no function"). Two kinds, two exits:
          · **background extras** -- scenery; nobody ever "finishes" them, so `剩余` still runs;
          · **functional/hook extras with `挂`** -- exit by **whether their matter was taken up**:
              - taken up (`engaged`) -> stay `ENGAGE_AFTER` more beats to wrap up, then leave;
              - never taken up -> after `FUNC_PATIENCE` beats leave **having waited in vain**
                (`空等: True`) and be recorded into the hook roster -- next time he returns with
                "the business left unfinished", so that visit is not wasted.
          · **old saves without `挂`** -- the old `剩余` countdown (an old save has no anchor
            information, so "did he get it done" cannot be judged). ⚠ The production path can no
            longer produce such records: `add_extra` blocks them.
        ⚠ The first beat only lets a newcomer be seen (`新` flag), no life-or-death call -- it is
        absurd for someone to "wait in vain" the moment he walks in.
        **including kind is deliberate**: the caller relies on it to decide "whether this line is worth putting on screen"
        (background coming and going is background; only functional/hook ones are "the one with something going on", see `exit_notice()`).
        ★ On exit, write "people worth remembering" into the hook roster (`remember_hook`) --
        this is the only entry point for "still recognizing them next time".
    """
    gone: list[dict] = []
    keep: list[dict] = []
    for e in getattr(world, "extras", []):
        kind = str(e.get("kind") or "")
        label = str(e.get("称呼") or e.get("一行") or "有人")
        if kind != "背景" and e.pop("新", False):
            keep.append(e)                       # 刚进门：先让人看见
            continue
        anchored = kind != "背景" and str(e.get("挂") or "")
        if not anchored:
            # 背景（场面）/ 老存档：照旧按拍数
            e["剩余"] = int(e.get("剩余", 1)) - 1
            if e["剩余"] > 0:
                keep.append(e)
            else:
                remember_hook(world, e)
                gone.append({'kind': kind, 'label': label})
            continue
        # ★ 挂了线的：按"他要的事有没有被接住"走
        if engaged(world, e):
            if not e.get("已接"):
                e["已接"] = True
                e["剩余"] = ENGAGE_AFTER         # 有人接了 → 再留两拍把这件事收尾
                # ★★★ 2026-10-21：**记进"今天被理过的群演"**（`WorldState.extras_engaged`）。
                #   收工整理时靠它给"名单外的人一个字都不许写"那条禁令开例外 ——
                #   不开的话，台本里真的发生过的对话进不了正文（实测三版全是 0 次）。
                # [EN] ★★★ 2026-10-21: **record into "extras dealt with today"**
                # [EN] (`WorldState.extras_engaged`). The wrap-up organizing pass uses it to carve an
                # [EN] exception in the ban "not a single word about anyone outside the list" --
                # [EN] without it, dialogue that really happened in the transcript cannot enter the
                # [EN] prose (measured: 0 times across three versions).
                try:
                    who_now = str(e.get("称呼") or "").strip()
                    book = getattr(world, "extras_engaged", None)
                    if book is None:
                        world.extras_engaged = book = []
                    if who_now and who_now not in book:
                        book.append(who_now)
                except Exception:                            # noqa: BLE001
                    pass
            e["剩余"] = int(e.get("剩余", 1)) - 1
            if e["剩余"] > 0:
                keep.append(e)
            else:
                remember_hook(world, e)
                gone.append({'kind': kind, 'label': label})
            continue
        e["候"] = int(e.get("候", 0)) + 1
        if e["候"] >= FUNC_PATIENCE:
            remember_hook(world, e)
            gone.append({'kind': kind, 'label': label, '空等': True})
            continue
        keep.append(e)
    world.extras = keep
    return gone


def exit_notice(world, gone: list[dict], *, tick: int = 0) -> str | None:
    """退场**该不该说一句、说什么**（`None` = 什么都别说）。

    为什么要把这个判断从 `sim/loop` 搬到这里：它是**叙事手感**，
    和"谁在门外、谁走了"是同一件事的两面，应该在同一个文件里看得见；
    而且放这儿才能脱离界面/主循环单独测（`verify_hooks` 就是这么测的）。

    规则（2026-10-07 定，用户报「对话又死循环了」）：

      · **功能 / 钩子群演** —— "有事的那个"。点名叫出来：`（来讨债的走了）`。
        它们本来就是事件，占一行天经地义。
      · **背景群演** —— **不逐条报**。它们寿命短（`BG_LIFE`）、补得勤，
        逐条报就是刷屏（截图里同一句连着出现 4 次）。改成最多每
        `BG_NOTICE_EVERY` 拍说一句"堂里的人换过一拨"，**且要有冷却**。

    ⚠ 以前这里是 `for who in gone[:2]: push(f"（{who}走了）")` —— 两个毛病：
      ① 背景也逐条报（刷屏）；
      ② `who` 取的是**整句场面描写**，而句子里往往已经有动作了
         （"有人把茶碗盖一磕，起身结账走了"），再拼个"走了"就成
         **"走了走了"**（那个重词就是这么来的）。
    
        English:
    On exit, **should we say something, and what** (`None` = say nothing).
        Why move this judgment from `sim/loop` to here: it's **narrative feel**,
        and it's two sides of the same thing as "who's at the door, who left", so it should be visible in the same file;
        and only here can it be tested independently of the UI/main loop (that's how `verify_hooks` tests it).
        Rules (set 2026-10-07, user reported "the dialogue is looping forever again"):
            They are events by nature, so taking a line is only natural.
          · **Background extras** —— **do not report them individually**. Their lifetime is short (`BG_LIFE`) and they're replenished frequently,
            so reporting each one is spam (in the screenshot the same line appears 4 times in a row). Instead, at most every
            `BG_NOTICE_EVERY` ticks, say "the people in the hall have swapped out", **and there must be a cooldown**.
        ⚠ Previously this was `for who in gone[:2]: push(f"（{who}走了）")` —— two problems:
          ① background ones were also reported individually (spam);
          ② `who` was the **entire scene description**, and the sentence often already contained an action
             ("someone clacks the teacup lid, gets up, pays, and leaves"), so appending "left" produced
             **"left left"** (that's where the duplicated word came from).
    """
    named = [g for g in gone if g.get('kind') != '背景']
    if named:
        # ★ **名字要去重**（2026-10-07）：`add_extra` 那道"同一个人不重复在场"
        #   是第一道防线，这里是第二道 —— 老数据（外面手里那份 `extras` 已经
        #   存了重复的）与别的写入路径都可能绕过它，而播报重复是**一眼能看见**
        #   的那种怪（「（讨账的伙计走了；讨账的伙计走了）」）。
        # [EN] ★ **Names must be deduplicated** (2026-10-07): the "same person not present twice" check in
        # [EN] `add_extra`
        # [EN] is the first line of defense, this is the second —— old data (the `extras` already in external
        # [EN] hands
        # [EN] with duplicates stored) and other write paths can both bypass it, and broadcast duplicates are
        # [EN] **visible at a glance**
        # [EN] as that kind of weirdness ("(the debt-collecting clerk left; the debt-collecting clerk left)").
        #
        # ★ 2026-10-21：**走的时候要给出理由**。等满了还没人搭话的人不是"走了"，
        #   是"等不到人，走了" —— 读者看得到因果，才不会觉得这个人凭空消失。
        # [EN] ★ 2026-10-21: **state the reason on the way out**. Someone who waited out the
        # [EN] patience and got no response did not just "leave", he "waited in vain and left" --
        # [EN] the reader sees the causality, so it does not read as a person vanishing.
        uniq: list[dict] = []
        for g in named:
            if not any(u.get('label') == g.get('label') for u in uniq):
                uniq.append(g)
        parts = [f"{g.get('label')}等不到人，走了" if g.get('空等')
                 else f"{g.get('label')}走了" for g in uniq[:2]]
        return '（' + '；'.join(parts) + '）'
    n_bg = sum(1 for g in gone if g.get('kind') == '背景')
    if not n_bg:
        return None
    last = int(getattr(world, 'bg_notice_tick', -10 ** 6) or -10 ** 6)
    if tick and (tick - last) < BG_NOTICE_EVERY:
        return None
    if tick:
        world.bg_notice_tick = tick
    return '（堂里的人换过一拨）'


# ══════════════════════════════════════════════════════════════════
#  钩子群演（第三档）：反复出现、像有故事的客人 —— 要**跨场记忆**
# [EN] Hook extras (third tier): recurring, like a guest with a story —— they need **cross-scene
# [EN] memory**
# ══════════════════════════════════════════════════════════════════
# 回来时有多大概率是"老熟人"而不是新面孔。给成常量而不是旋钮：
# 它是**叙事手感**不是成本开关（开关是 `EXTRAS_HOOKS`），
# 旋钮太多反而没人调得动。
# [EN] for the probability of being an "old acquaintance" rather than a new face on return. Given as a
# [EN] constant rather than a knob:
# [EN] it is **narrative feel** not a cost switch (the switch is `EXTRAS_HOOKS`),
# [EN] too many knobs and nobody can tune them anyway.
HOOK_RETURN = 0.35


def _hook_key(e: dict) -> str:
    """一个群演"是不是同一个人"的判据 = 称呼 + 标志。

    ⚠ **不能用随机 id**：群演每次是现场造的 dict，没有稳定身份；
    而"同一个人"对读者来说就是"还是那个讨债的、还是那个戴着斗笠的"。
    
        English:
    Criterion for whether an extra "is the same person" = appellation + marker.
        ⚠ **Cannot use a random id**: extras are dicts created on the spot each time, with no stable identity;
        and to the reader, "the same person" just means "still that debt collector, still the one wearing the straw hat".
    """
    return f"{e.get('称呼', '')}|{e.get('标志', '')}"


def remember_hook(world, e: dict) -> dict | None:
    """把一个**走掉的**功能群演记进钩子名册（跨场记忆的写入端）。

    只记"功能"群演：背景群演是**场面**（"两个脚夫在门口歇脚"），
    不是人；把场面记成人名册，名册里很快就会全是"两个脚夫"。
    
        English:
    Record a **departed** functional extra into the hook roster (the write end of cross-scene
    memory).
        Only record "functional" extras: background extras are **scene** ("two porters resting at the door"),
        not people; record scenes as people and the roster will soon be full of "two porters".
    """
    if not CFG.b("EXTRAS_HOOKS"):
        return None
    if e.get("kind") != "功能":
        return None
    who = str(e.get("称呼") or "").strip()
    if not who:
        return None
    key = _hook_key(e)
    book = getattr(world, "hooks", None)
    if book is None:
        world.hooks = book = []
    for rec in book:
        if rec.get("key") == key:
            rec["见面次数"] = int(rec.get("见面次数", 1)) + 1
            rec["上次第几天"] = int(getattr(world, "game_day", 1) or 1)
            pend = str(e.get("诉求") or "").strip()
            if pend and pend not in (rec.get("前情") or []):
                rec.setdefault("前情", []).append(pend)
            return rec
    rec = {
        "key": key,
        "称呼": who,
        "标志": str(e.get("标志") or ""),
        "前情": [str(e.get("诉求") or "")] if e.get("诉求") else [],
        "见面次数": 1,
        "首次第几天": int(getattr(world, "game_day", 1) or 1),
        "上次第几天": int(getattr(world, "game_day", 1) or 1),
    }
    book.append(rec)
    return rec


def recall_hook(world, rng: random.Random | None = None) -> dict | None:
    """让一个**老熟人**再来一次，带着前情。没有合适的就返回 None。

    条件：见过至少一次、最近 3 个故事日内没来过（刚走又回来就成了骚扰）。
    回来时 `诉求` 用"上一次没办完的那件"或新的一件，并**把前情挂在身上**
    —— `needs_line()` 会把它讲给人物听（"上回那个讨债的又来了"）。
    
        English:
    Bring back an **old acquaintance** once more, carrying prior context. Return None if there is no
    suitable one.
        Conditions: has been seen at least once, and has not shown up within the last 3 story days (leaving and immediately returning would be harassment).
        On return, `诉求` uses "the one left unfinished last time" or a new one, and **drapes the prior context on them**
        -- `needs_line()` will tell it to the character ("that debt collector from last time is back").
    """
    if not CFG.b("EXTRAS_HOOKS"):
        return None
    rng = rng or random.Random()
    book = list(getattr(world, "hooks", None) or [])
    day = int(getattr(world, "game_day", 1) or 1)
    alive = {_hook_key(e) for e in getattr(world, "extras", [])}
    cands = [r for r in book
             if r.get("key") not in alive
             and day - int(r.get("上次第几天", day) or day) >= 3]
    if not cands:
        return None
    if rng.random() > HOOK_RETURN:
        return None
    rec = rng.choice(cands)
    kind = scene_kind(str(getattr(world, "scene", "") or ""))
    pool = list(_NEED_BY_KIND.get(kind, [])) or list(_NEED_DEFAULT)
    _who, need = rng.choice(pool)
    prev = [x for x in (rec.get("前情") or []) if str(x).strip()]
    e = {
        "kind": "功能",
        "称呼": str(rec.get("称呼") or _who),
        "诉求": need,
        "标志": str(rec.get("标志") or ""),
        # ★ 老熟人回来**天生就挂着一条线**：他上回没办完的那件事。
        #   没有前情记录（老存档）就退化成"上回没办完的那件事"，不编具体内容。
        # [EN] ★ A returning acquaintance is **anchored by nature**: the business he left
        # [EN] unfinished. Without prior-context records (old saves) it degrades to "the thing left
        # [EN] unfinished last time" rather than inventing content.
        "挂": (_one(prev[-1], 36) if prev else "上回没办完的那件事"),
        "接": "（老熟人）",
        "候": 0,
        "新": True,
        "钩子": True,
        "见面次数": int(rec.get("见面次数", 1)) + 1,
        "前情": prev[-2:],
        "一行": f"{rec.get('称呼')}（又来了）——{need}",
    }
    world.extras.append(e)
    world.extras_today = int(getattr(world, "extras_today", 0) or 0) + 1
    return e


def hook_suggestions(world) -> list[dict]:
    """够格转正为**正式人物卡**的钩子群演（程序只给建议，不代造）。

    判据：见面次数 ≥ `EXTRAS_HOOK_PROMOTE_AT`。它说的是"这个人在读者眼里
    已经是个角色了"—— 但**要不要给他一张人物卡是作者的判断**，
    所以这里只产出一张清单（`hooks_md`），绝不自动写进设定集。
    
        English:
    Hook extras eligible for promotion to an **official character card** (the program only offers
    suggestions, it does not create them itself).
        Criterion: meeting count >= `EXTRAS_HOOK_PROMOTE_AT`. It means "this person is already a character
        in the reader's eyes" -- but **whether to give them a character card is the author's call**,
        so here it only produces a list (`hooks_md`), and never automatically writes into the setting bible.
    """
    if not CFG.b("EXTRAS_HOOKS"):
        return []
    need = max(2, CFG.i("EXTRAS_HOOK_PROMOTE_AT"))
    done = set(getattr(world, "hooks_promoted", None) or [])
    out = []
    for rec in getattr(world, "hooks", None) or []:
        if int(rec.get("见面次数", 1) or 1) >= need and rec.get("key") not in done:
            out.append(rec)
    return out


def hooks_md(world) -> str:
    """`可转正群演.md`：给作者看的建议清单（不自动改设定集）。
        English:
    `可转正群演.md`: a suggestion list for the author to read (does not automatically modify the setting
    bible).
    """
    rows = list(getattr(world, "hooks", None) or [])
    need = max(2, CFG.i("EXTRAS_HOOK_PROMOTE_AT"))
    lines = ["# 钩子群演（反复出现的人）", "",
             "> 他们只是临演。但**反复出现过的人，在读者眼里已经是角色了** ——",
             f"> 见过 {need} 次以上的列在下面，要不要给一张正式人物卡由你定。",
             "> 程序**不会**自动把他们写进设定集。", "",
             "| 称呼 | 标志 | 见面次数 | 首见 | 最近 | 前情 |",
             "|---|---|---|---|---|---|"]
    if not rows:
        lines.append("| — | （还没有反复出现的人） | | | | |")
    for r in sorted(rows, key=lambda x: -int(x.get("见面次数", 1) or 1)):
        lines.append("| {} | {} | {} | 第{}天 | 第{}天 | {} |".format(
            r.get("称呼", ""), r.get("标志", "—"), r.get("见面次数", 1),
            r.get("首次第几天", "?"), r.get("上次第几天", "?"),
            "；".join(str(x) for x in (r.get("前情") or [])[:2]) or "—"))
    hot = hook_suggestions(world)
    if hot:
        lines += ["", "## 建议转正（见过 {} 次以上）".format(need), ""]
        for r in hot:
            lines.append(f"- **{r.get('称呼', '')}**"
                         f"（{r.get('标志', '—')}）见过 {r.get('见面次数')} 次"
                         f" —— 他在这本书里已经不只是背景了。")
    return "\n".join(lines) + "\n"


def needs_line(world) -> str:
    """功能群演拼成的一句"当前情况"（进决策上下文；没有就空串）。

    ⚠ 只给**看得见听得见**的部分（谁的诉求是什么），不给身份背景 ——
    群演不进记忆主库，也不该抢主角的戏。
    
        English:
    A "current situation" assembled from functional extras (goes into the decision context; empty
    string if none).
        ⚠ Only give the parts that are **visible and audible** (who wants what), not identity/background --
        extras do not enter the main memory store, and should not steal the protagonist's spotlight.
    """
    bits: list[str] = []
    for e in getattr(world, "extras", []):
        if e.get("kind") != "功能":
            continue
        who = str(e.get("称呼") or "有人")
        need = str(e.get("诉求") or "")
        mark = str(e.get("标志") or "")
        # ★ 钩子群演要**把前情一起讲出来**，否则"又来了"这三个字对人物毫无意义
        #   —— 跨场记忆的全部价值就在于"人物认得出他、记得上回的事"。
        # [EN] ★ Hook extras must **tell the backstory along with it**, otherwise the words "here again" mean
        # [EN] nothing for the character
        # [EN] —— the entire value of cross-scene memory lies in "the character recognizes him and remembers
        # [EN] last time's business".
        if e.get("钩子"):
            prev = [str(x) for x in (e.get("前情") or []) if str(x).strip()]
            if prev:
                who = f"{who}（上回来过：{'；'.join(prev[-1:])}）"
        line = f"{who}：{need}"
        if mark:
            line += f"（{mark}）"
        # ★ 2026-10-21：**把他为什么在这儿一起给人物看**。
        #   只给"门外有个讨债的"，人物不知道该不该理他；给"为「掌柜欠账」来的"，
        #   接不接就成了一件可判断的事 —— 群演才真的"承接剧情需要"。
        # [EN] ★ 2026-10-21: **show the characters why he is here**.
        # [EN] "there's a debt collector outside" gives them nothing to judge; "here about 'the
        # [EN] shopkeeper's debt'" turns taking him up into a decision -- only then does the extra
        # [EN] truly "serve what the plot needs".
        anchor = _one(e.get("挂"), 20)
        if anchor:
            line += f"〔为「{anchor}」来的〕"
        bits.append(line)
    return "；".join(bits)


def ledger_md(world) -> str:
    """群演台账（本轮都有谁来过）。落 `<运行文件夹>/群演台账.md`。
        English:
    Extras ledger (who came this round). Written to `<run folder>/群演台账.md`.
    """
    rows = getattr(world, "extras", [])
    lines = ["# 群演台账", "",
             "> 只记「来过的人」，不记剧情。背景群演是场面，功能群演带一个诉求。",
             "> 「为哪件事来的」就是他能进门的理由 —— **这一栏空着的人不该在场**。",
             "",
             "| 类型 | 称呼 | 诉求 / 一行 | 标志 | 为哪件事来的（挂靠） |",
             "|---|---|---|---|---|"]
    if not rows:
        lines.append("| — | （本轮还没人来） | | | |")
    for e in rows:
        lines.append("| {} | {} | {} | {} | {} |".format(
            e.get("kind", ""), e.get("称呼", "—"),
            e.get("诉求") or e.get("一行", ""), e.get("标志", "—"),
            e.get("挂") or "—"))
    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════
#  导出期的最后一道：**只报了个到的人，不进事实底账**
# [EN] The last gate at export: **those who only reported in do not enter the fact ledger**
# ══════════════════════════════════════════════════════════════════
#: `【来人】称呼——诉求` / `【又来了】称呼——诉求`（`_sync_crowd` 推的那一行）
# [EN] : the line pushed by `_sync_crowd`
_CAST_TAG = re.compile(r"^【(来人|又来了)】\s*([^—\-\n]{1,12})")


def drop_orphan_casts(events: list[dict],
                      rows: list[dict]) -> tuple[list[dict], int]:
    """把"**只报了个到、全书再没人提过**"的群演事件从事实底账里摘掉。

    判据是**可删除性**（MEMORY：判"重复"看删掉读者损失什么）：
    如果这个称呼在整份台本里**只出现过那一次**，删掉它读者什么都没丢 ——
    那它就不是一件事，只是一声门响。反过来，只要后文有人提过他
    （点名叫他、说起他那件事），这条就**必须留**，否则后文就成了凭空出现的人。

    ⚠ 为什么在导出这一层还要再拦一道：推演期已经要求"挂上线才准进"，
      但**挂上了不等于有人理**。这一道兜的正是"挂得住、没人接"的残余 ——
      用户报的"没有任何作用"，指的常常就是这种人。

    ⚠ 只摘 `【来人】/【又来了】` 这两类行，别的一概不动
      （events 里全是"真的发生了"的事实，误删就是丢内容）。

    返回 `(保留的 events, 摘掉几条)`。
    
        English:
    Remove extras events that **only reported in and are never mentioned again** from the fact
    ledger.
        The criterion is **deletability** (MEMORY: judge redundancy by what the reader loses): if
        the appellation appears **exactly once** in the whole transcript, deleting it loses nothing
        -- it was not an event, just a knock. Conversely, if anyone mentions him later (calls him by
        name, refers to his business), the row **must stay**, otherwise later text would have a
        person appearing out of nowhere.
        ⚠ Why gate again at export: casting already requires an anchor, but **being anchored does
        not mean anyone responded**. This catches the residue -- "anchored but ignored" -- which is
        exactly the "no function at all" the user reported.
        ⚠ Only `【来人】/【又来了】` rows are touched; everything else is left alone (events are all
        "things that really happened"; deleting by mistake means losing content).
        Returns `(kept events, how many dropped)`.
    """
    texts = [str((r or {}).get("text") or "") for r in (rows or []) if isinstance(r, dict)]
    if not texts:
        # ⚠ 拿不到**整份台本**就一律不动：只看 events 的话每个称呼都只出现一次，
        #   会把所有群演事件全删光（那是"量错了对象"，比不判更糟）。
        # [EN] ⚠ Without the **whole transcript**, do nothing: looking only at `events` makes every
        # [EN] appellation appear exactly once, which would delete *all* extras events (measuring the
        # [EN] wrong object is worse than not judging at all).
        return list(events or []), 0
    kept: list[dict] = []
    dropped = 0
    for e in (events or []):
        text = str((e or {}).get("text") or "")
        m = _CAST_TAG.match(text)
        if m:
            who = m.group(2).strip()
            if len(who) >= 2 and sum(1 for t in texts if who in t) <= 1:
                dropped += 1
                continue
        kept.append(e)
    return kept, dropped
