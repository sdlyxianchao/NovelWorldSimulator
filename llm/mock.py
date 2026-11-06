# -*- coding: utf-8 -*-
"""演示模式（MOCK_LLM=true）：不发真实请求，用内置语料跑全流程。
English:
Demo mode (MOCK_LLM=true): sends no real requests, runs the whole flow with built-in corpus.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

DEMO_TAG = "【演示数据】"

_NARRATIVE_POOL = [
    "雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃，影子跟着歪。",
    "他把袖口往下扯了扯，遮住腕上一道旧痕，抬眼时脸上已换了副笑。",
    "话说到一半便断了，两人都听见楼梯上那声轻得几乎不存在的响。",
    "她没有接话，只把茶盏往里推了半寸——这是她拒人的老法子。",
    "街上传来更鼓，一下，又一下，像在替谁数着剩下的时辰。",
    "烛芯爆了个灯花，屋里静了一瞬，谁也没去看那扇没关严的窗。",
    "他心里那句话转了三转，终究没出口，只化作一声很轻的叹。",
    "门帘一动，带进一股湿冷的腥气，几个人同时住了口。",
]

_INNER_POOL = [
    "（这件事，不能让他知道第三个人。）",
    "（又来了。他每次心虚，都要先笑一声。）",
    "（若今晚走不成，往后便再没有今晚。）",
    "（她方才那一眼，是在递话，还是在警告？）",
    "（我原不该来的。可不来，我又去哪里。）",
]

_LINES_POOL = [
    "「你今日话里有话。」", "「话就是话，哪来的里外。」",
    "「那这盏灯，是给谁留的？」", "「留给会回来的人。」",
    "「若他不回来呢？」", "「那就留给等他的人。」",
    "「外头雨大，明日再走不迟。」", "「明日……明日的事，明日再说。」",
]


def _pick(pool, n=1):
    return random.sample(pool, min(n, len(pool)))


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _prompt_text(messages) -> str:
    """把发出去的提示词拼成一整段（演示模式要**从提示词里抠真名**，不是写死）。

    ⚠ 别用 `_crew_day_map` 那种内联写法再抄一遍 —— 那是它能过判据的写法，
      但抄第二遍就是三处维护。新用途用这个。
    
        English:
    Concatenate the outgoing prompts into one whole block (demo mode must **extract real names from
    the prompt**, not hardcode them).
        ⚠ Don't copy it again with an inline style like `_crew_day_map` — that's the style it uses to pass the criterion,
          but copying it a second time means maintaining three places. New purposes should use this.
    """
    out = ''
    for m in (messages or []):
        if isinstance(m, dict) and m.get('role') == 'user':
            out += str(m.get('content') or '') + '\n'
    return out


def _extract_obj():
    """演示用设定对象（供 extract / optimize_apply 共用）。
        English:
    Settings object for demo (shared by extract / optimize_apply).
    """
    return {
        "人物": [
            {"姓名": "主角", "身份": "掌柜", "简介": "主角，沉默寡言，凡事先看三步。",
             "性格": "沉默寡言，凡事先看三步", "口癖": " ……", "秘密": "曾替人顶过一件说不得的罪",
             "目标": "把当年那件事彻底掩过去", "红线": "不主动伤人；不泄露那年之事"},
            {"姓名": "阿枝", "身份": "伙计", "简介": "阿枝，嘴上不饶人，心却软。",
             "性格": "嘴上不饶人，心却软", "口癖": "「罢了。」", "秘密": "一直在等一个不会回来的人",
             "目标": "守住这间铺子不被拆", "红线": ""},
        ],
        "世界观": "一座常年落雨的临河小城，人情密、口风紧，旧事压在青石板底下。",
        "地点": [{"名称": "临河茶肆", "说明": "日常对话与交易场所"}],
        "关系": [{"甲": "主角", "乙": "阿枝", "关系": "旧识，各有保留", "张力": "互相需要又互相提防"}],
        "伏笔": [{"编号": "F01", "内容": "后院那口井夜里会响", "埋设": "开篇", "预计回收": "中段"},
                 {"编号": "F02", "内容": "主角腕上的旧痕", "埋设": "第一章", "预计回收": "高潮前"}],
        "剧情参考线": "起：雨夜来客打破平静；承：旧事被一点点翻出；转：最可信的人露出破绽；合：有人离开，有人留下。",
        # 细节层素材（`world/layers.py` 的「小事」那一层）——
        # 演示模式下也要有条目，否则整条分层链在 MOCK 里是空跑的，
        # 验证脚本就查不出"细节层到底进没进提示词"。
        # [EN] Detail-layer material (the "small things" layer in `world/layers.py`) ——
        # [EN] In demo mode there must also be entries, otherwise the whole layering chain runs empty in MOCK,
        # [EN] and the verify script can't detect "whether the detail layer actually made it into the prompt".
        "细节": [
            {"名称": "缺角的紫砂壶", "内容": "柜上那把壶缺了个角，谁也不许拿去用",
             "场合": "临河茶肆", "涉及": "主角"},
            {"名称": "更漏只校一次", "内容": "店里的更漏一夜只许校一次，校错了当班的人要赔",
             "场合": "临河茶肆", "涉及": ""},
            {"名称": "旧疤", "内容": "掌柜右腕内侧有道旧疤，天阴时他自己会按一按",
             "场合": "", "涉及": "主角"},
        ],
    }


def _extract(messages):
    return _j(_extract_obj())


def _genre(messages):
    return _j({"主题材": "悬疑", "副题材": "世情", "结构": "单元剧", "频道": "男频",
               "置信度": 0.72, "理由": "文本以悬念与旧事翻覆为主，冲突集中在人心而非外力。"})


def _style(messages):
    return _j({
        "句长": "中短句为主，偶有长句收束", "叙事距离": "贴近人物有限视角，少全知议论",
        "词汇偏好": "白描、少形容词、多用器物与天气", "对话占比": "约四成",
        "视角纪律": "第三人称限知，不跳头", "章法偏好": "小节短、段尾留钩",
        "AI腔禁词表": ["首先", "其次", "总的来说", "值得注意的是", "在这个过程里", "不仅仅是"],
    })


def _progress(messages):
    nodes = [
        ("雨夜来客", "一个陌生人在雨夜叩门，带来一件旧事的消息", "来客说出旧事的关键词"),
        ("旧事浮头", "当事人各自反应，线索开始对不上", "至少两人对同一件事说法不一"),
        ("破绽", "最可信的人露出一处说不通的地方", "有人当场抓住这处矛盾"),
        ("摊牌", "秘密被迫摆到台面上，必须做出选择", "当事人当面承认或否认"),
        ("收束", "人各归其位，留一条未尽的线", "场面恢复日常秩序"),
    ]
    return _j({"节点": [{"id": f"N{i+1:02d}", "名称": n, "概要": s, "完成判据": c}
                        for i, (n, s, c) in enumerate(nodes)]})


def _alignment(messages):
    return _j({"对齐": [{"章节": "第1章", "覆盖节点": ["N01"], "摘要": "雨夜来客叩门，旧事被提起。"}],
               "已完成节点": ["N01"], "起始点建议": "接续正文结束处（N01 之后）"})


def _opening(messages):
    return _j({"候选": [
        {"场景": "临河茶肆", "时刻": "入夜·戌时", "在场": ["掌柜", "伙计"],
         "情境": "雨声里来了个不报名号的客人，只问一句旧事。",
         "理由": "信息缺口最大，第一句话就能起钩。"},
        {"场景": "旧宅正堂", "时刻": "午后·未时", "在场": ["主人", "常客"],
         "情境": "清点旧物时翻出一件本不该在的东西。",
         "理由": "器物切入，悬念自然，不靠对白交代。"},
    ]})


def _agent_decide(messages):
    act = random.choice(["speak", "move", "interact", "emote", "wait", "think"])
    # ⚠ 目标里**不要放"对方"这种代词**（2026-10-07）：演示数据也会被当真 ——
    #   `move` 到"对方"会让人物的位置变成一个不存在的地方，屏幕上于是出现
    #   「〔切至 · 对方〕」，这个人还会被踢出在场名单。产品侧已经加了
    #   `sim.loop.target_is_not_a_place` 拦它，但**演示数据本身也该像样**
    #   （演示模式是用户会盯着看的那一版）。
    # [EN] ⚠ Do NOT put pronouns like "the other party" in the target (2026-10-07): demo data also gets
    # [EN] taken for real ——
    # [EN] `move` to "the other party" makes the character's position become a place that doesn't exist, so
    # [EN] the screen then shows
    # [EN] "〔cut to · the other party〕", and this person also gets kicked out of the present roster. The
    # [EN] product side already added
    # [EN] `sim.loop.target_is_not_a_place` to block it, but **the demo data itself should also look sane**
    # [EN] (demo mode is the version the user will be staring at).
    return _j({"动作": act,
               "参数": {"目标": random.choice(["门外", "账台", "后院", "柜台后"])},
               "台词": _pick(_LINES_POOL, 1)[0] if act == "speak" else "",
               "内心": _pick(_INNER_POOL, 1)[0], "理由": "按当下情境最自然的一步",
               # ★ 思维链（2026-10-07 第七轮）：骨架要求"开口之前先过一遍"，
               #   演示数据也给一句 —— 否则演示模式下这段路永远走不到
               #   （`Action.think_trace` 恒空，"记盘算进台账"那一步验不到）。
               # [EN] ★ Chain of thought (2026-10-07 round 7): the skeleton requires "go over it before speaking",
               # [EN] so demo data also gives one line —— otherwise in demo mode this path is never reached
               # [EN] (`Action.think_trace` is always empty, and the "record deliberation into the ledger" step can't
               # [EN] be verified).
               "推演": random.choice([
                   "我要的是把话压住，不能让他当众问出来。",
                   "他刚才那一下是在试探，我接得太快就露底。",
                   "这话只有他能说，我插嘴就变味了。",
                   "先别答，看他还要不要往下说。"])})


def _dialogue(messages):
    a, b = _pick(_LINES_POOL, 2)
    return f"{DEMO_TAG}\n{a}\n{b}\n{_pick(_LINES_POOL,1)[0]}"


def _narrative(messages):
    return (f"{DEMO_TAG} " + "".join(_pick(_NARRATIVE_POOL, 2)) +
            "\n" + _pick(_LINES_POOL, 1)[0] + "　" + _pick(_INNER_POOL, 1)[0])


def _director_event(messages):
    return _j({"推演": "这一拍缺一件外部的事把两个人逼到同一件东西上 —— "
                       "选「门外有人驻足」最省，且能牵出后巷那条线。",
               "是否介入": True, "类型": "外部刺激",
               "事件": random.choice([
                   "门外有人驻足不走，隔着雨看不清脸",
                   "一封没有署名的信被塞进门缝",
                   "更夫报说后巷出了事，官府的人正在路上",
                   "账上少了不该少的一笔钱",
               ]),
               "涉及人物": [], "强度": round(random.uniform(0.3, 0.8), 2),
               "理由": "当前张力偏低，需要一个不大不小的推力"})


def _branch(messages):
    return _j({"候选": [
        {"id": "B1", "标题": "追下去", "后果": "真相更早揭开，但也更早撕破脸", "权重": 0.5},
        {"id": "B2", "标题": "装作不知", "后果": "日常继续，暗线延后到更危险的时点", "权重": 0.3},
        {"id": "B3", "标题": "反将一军", "后果": "人物关系重排，风险与回报都最大", "权重": 0.2},
    ]})


def _progress_eval(messages):
    return _j({"满足": random.random() < 0.35, "理由": "判据的关键征兆已出现（演示判定）。",
               "进展描述": "离判据还差一步"})


def _compliance(messages):
    return _j({"级别": "C2", "判定": "pass", "理由": "虚构创作豁免范围内的正常描写。", "改写": ""})


def _importance(messages):
    return _j({"分数": random.randint(3, 8)})


def _reflect(messages):
    return _j({"反思": random.choice([
        "我总是在别人要说出真话时打断——不是好奇，是怕。",
        "这间铺子守的不是生意，是一个不能让人知道的年份。",
        "我以为自己是棋手，其实只是一条被牵着的线。",
    ])})


def _plan(messages):
    return _j({"日计划": ["照看铺面", "把那件事再压一压", "等一个不会准时来的消息"],
               "时段块": [{"时段": "上午", "行动": "开门、应付常客"},
                          {"时段": "午后", "行动": "去后院看看那口井"},
                          {"时段": "入夜", "行动": "留门，等该来的人"}]})


def _optimize(messages):
    return _j({"诊断": [
        {"项": "人物", "问题": "缺秘密与口癖，行为易趋同", "建议": "为每人补一条秘密、一个口癖", "优先级": "高"},
        {"项": "伏笔", "问题": "未编号、无回收点", "建议": "编号并标注埋设位置与预计回收节点", "优先级": "中"},
        {"项": "大纲", "问题": "节点过粗，无法判完成", "建议": "拆成 4~6 个带完成判据的节点", "优先级": "高"},
    ]})


def _optimize_review(messages):
    """AI 体检（对话，非 JSON）——演示模式文本。
        English:
    AI checkup (dialogue, not JSON) — demo mode text.
    """
    return ("（演示模式）我通读了一遍这份设定。\n"
            "最突出的问题是人物动机偏薄：主角的秘密都没和大纲里的节点绑上，"
            "读者会觉得「有秘密」但不知道它会怎么爆。\n"
            "建议先做三件事：\n"
            "1. 给主角各补一条「不能说的过去」，写明它会在第几个节点被撞破；\n"
            "2. 把两条伏笔的回收点落到具体节点，别只写「中段」；\n"
            "3. 世界观再补一条规矩（当地忌讳或行规），让冲突有制度性的来源。\n"
            "把想法直接打给我，我照你说的改。")


def _optimize_apply(messages):
    """按指令改设定——演示模式返回一份合法设定 + 变更说明。
        English:
    Modify settings per instructions — demo mode returns a valid settings + change description.
    """
    return _j({"修改说明": "（演示模式）已按你的意见改写设定：补齐人物秘密的回收节点，"
                        "并把两条伏笔的预计回收落到具体节点上。",
               "设定": _extract_obj()})


# ── 打磨 Agent（2026-10-07）────────────────────────────────────────────
# ★ 演示模式**必须演得出一段真实的 Agent 循环**，否则：
#   · 界面上永远只看到"AI 一句话都没说"（真的在跑 MOCK 的人也看不出对不对）；
#   · 验证脚本没法在没有真模型的情况下验"工具真的被调了 / 历史真的带上了"。
# [EN] ── Polish Agent (2026-10-07)──────────────────────────────────────
# [EN] ★ Demo mode **must be able to act out a real Agent loop**, otherwise:
# [EN] · The UI forever only shows "the AI didn't say a single word" (even people actually running MOCK
# [EN] can't tell whether it's right);
# [EN] · The verify script can't verify "the tool was really called / the history really was included"
# [EN] without a real model.
#
#   协议（见 `polish/agent._PROTOCOL`）：每回合回一个 JSON 对象。
#   步数从提示词尾巴那句「（这是本轮第 N/M 步）」里读 —— 那句话说人话，
#   模型看得懂，MOCK 也能照着演。
# [EN] Protocol (see `polish/agent._PROTOCOL`): return one JSON object per turn.
# [EN] The step count is read from the sentence at the prompt tail "(this is step N/M of this round)"
# [EN] —— that sentence is plain language,
# [EN] the model can understand it, and MOCK can act it out accordingly.
_STEP_RE = re.compile(r'第\s*(\d+)\s*/\s*(\d+)\s*步')


def _polish_step(messages):
    """打磨 Agent 的一步：第 1 步先看设定，第 2 步收尾（演一段真实的两步流程）。
        English:
    One step of the Polish Agent: step 1 looks at settings first, step 2 wraps up (acting out a real
    two-step flow).
    """
    text = "\n".join(str(m.get("content") or "") for m in messages)
    m = None
    for m in _STEP_RE.finditer(text):
        pass
    step = int(m.group(1)) if m else 1
    if step <= 1:
        return _j({"想": "先看一眼现在的设定再动手",
                   "用": "读设定", "参": {"路径": "人物"}})
    return _j({"想": "看清楚了，可以收口",
               "终": "（演示模式）我看过当前设定了。你把想改的告诉我，"
                     "我会自己动手改，改完还会自查一遍；"
                     "要读你导入的素材、要写个小工具，我也可以现场做。",
               "改了什么": []})


def _polish_reflect(messages):
    """打磨 Agent 的自省一遍：演示模式给"没问题"。
        English:
    One round of self-reflection of the Polish Agent: demo mode gives "no problem".
    """
    return _j({"有问题": False, "问题": [], "下一步": ""})


# ── 拆书（2026-10-07）──────────────────────────────────────────────────
# 三道工序各一个 handler。演示模式下要**真的演得出流水线**：
# 粗扫给出逐章行、精拆给出笔记、归纳给出模块 —— 任何一步给空，
# "这条路通不通"在演示模式里就永远验不到。
# [EN] ── Book splitting (2026-10-07)────────────────────────────────────
# [EN] One handler for each of the three工序. In demo mode it must **really act out the pipeline**:
# [EN] rough scan gives per-chapter lines, deep split gives notes, summarization gives modules —— if
# [EN] any step gives empty,
# [EN] "whether this path works" can never be verified in demo mode.
#
# ★ 章名**从提示词里抓**：演示模式演的是**作者传进来的那本书**，
#   抓不到章名就没法把逐章行对回原书（`pick_deep` 与 `outline_text` 都按章名索引）。
#   这与 `_crew_settings` 从提示词里抓地点是同一手法：**依据从输入取，不硬编码**。
# [EN] ★ Chapter names are **grabbed from the prompt**: demo mode acts out **the book the author passed
# [EN] in**,
# [EN] if chapter names can't be grabbed, the per-chapter lines can't be mapped back to the original
# [EN] book (`pick_deep` and `outline_text` are both indexed by chapter name).
# [EN] This is the same technique as `_crew_settings` grabbing the location from the prompt: **take the
# [EN] basis from the input, don't hardcode**.
def _chapters_in(messages) -> list[str]:
    """从提示词里抓出这一批的章名（`【第X章 …】` 那一行）。
        English:
    Extract this batch's chapter names from the prompt (the line `【第X章 …】`).
    """
    text = "\n".join(str(m.get("content") or "") for m in (messages or []))
    names = re.findall(r'^【(.+?)】(?:（\d+ 字）)?\s*$', text, re.MULTILINE)
    out: list[str] = []
    for n in names:
        n = ' '.join(str(n).split())[:40]
        if n and n not in out:
            out.append(n)
    return out


#: 演示用的逐章"干什么"（轮着用 —— 一本演示书里不可能每章都不同）
# [EN] : per-chapter "what to do" for demo (used in rotation —— in a demo book not every chapter can be
# [EN] different)
_SCAN_POOL = [
    ("主角被一件小事绊住，发现事情不像看上去那样", ["推进主线", "放钩子"], 3, "悬念"),
    ("有人找上门来，说出一件主角不知道的旧事", ["推进主线", "埋伏笔"], 4, "悬念"),
    ("主角试了一次，没成，反而更麻烦", ["推进主线", "制造情绪"], 2, "情绪"),
    ("把上一条伏笔的边掀开一角，但没揭底", ["收伏笔", "放钩子"], 3, "反转"),
    ("两个人把话挑明，关系变了一层", ["立人设", "推进主线"], 4, "情绪"),
    ("一段安静的日常，把人物的性子写透", ["立人设", "铺垫"], 1, "无"),
    ("事情爆了，主角把牌一次打光", ["推进主线", "制造情绪"], 5, "反转"),
    ("收场与余味，同时埋下下一段要用的东西", ["收束", "埋伏笔"], 3, "预告"),
]


def _book_scan(messages):
    """粗扫一批（`book_scan`）：逐章一句话 + 功能 + 情绪 + 钩子。
        English:
    Coarse scan a batch (`book_scan`): one line per chapter + function + emotion + hook.
    """
    names = _chapters_in(messages)
    if not names:
        return _j({"章": [], "这一批的观察": "（演示）提示词里没有章节标题，"
                                            "无法把逐章行对回去。"})
    rows = []
    for i, n in enumerate(names):
        one, func, emo, hook = _SCAN_POOL[i % len(_SCAN_POOL)]
        rows.append({"章": n, "一句话": f"（演示）{one}",
                     "功能": list(func), "情绪": emo, "钩子": hook})
    return _j({"章": rows, "这一批的观察": "（演示）这一批在推进主线，"
                                          "每隔两三章放一个钩子。"})


def _book_deep(messages):
    """精拆（`book_deep`）：手法笔记。

    ⚠ 演示数据**必须真的是"手法"**（怎么写的/为什么有效/怎么用），
      不能是"这一章写得很好" —— 那样演示模式演出来的是一个**错误的示范**，
      而作者会照着它学。出处从提示词里抓。
    
        English:
    Deep breakdown (`book_deep`): technique notes.
        ⚠ Demo data **must really be "techniques"** (how it was written / why it works / how to use it),
          not "this chapter is written well" — that would make demo mode act out a **wrong example**,
          and the author would learn from it. Sources are extracted from the prompt.
    """
    names = _chapters_in(messages)
    at = names[0] if names else "（开头）"
    return _j({"拆解": [
        {"维度": "人物塑造", "出处": f"{at} 人物第一次出场",
         "怎么写的": "（演示）没给人物的相貌，只给了他一个动作和对一句问话的答法；"
                     "读者从'他怎么答'认出他是谁",
         "为什么有效": "省掉了外貌描写，却让人物的性子在读者面前先立起来 —— "
                       "动作比形容更难忘",
         "怎么用": "人物第一次上场，别写他长什么样，写他**怎么做一件小事**"},
        {"维度": "情绪与钩子", "出处": f"{at} 章末",
         "怎么写的": "（演示）把事情解决到九成，留最后一件悬着不说；"
                     "下一章开头才接",
         "为什么有效": "读者带着一个具体的问题翻页，而不是带着'会怎样呢'这种泛泛的期待",
         "怎么用": "章末留的钩子要**具体到一件事**（谁把什么拿走了），"
                   "别留'不知会发生什么'"},
        {"维度": "骨架与节奏", "出处": f"{at} 整章",
         "怎么写的": "（演示）前面压了两章不给，这一章一次给足；"
                     "给完立刻在章末又埋一个新的",
         "为什么有效": "爆点之后马上接新钩子，读者不会在爽完之后合上书",
         "怎么用": "每一次'给足'的后面**立刻**接一个新的悬念，不要留空档"},
    ], "这几章的结论": "（演示）手法集中在这三处：用动作立人、"
                       "章末留具体的钩子、给完就接新的。"})


def _book_final(messages):
    """归纳（`book_final`）：可复用的模块。

    ★ 演示数据要**看得出"能拿走"**：每条都写"怎么做/什么时候用/为什么管用"，
      而且 `不适合` **不许空着**（空着就演示不出"知道什么不能照搬"这一课）。

    ★ 2026-10-10 起模块卡升级成 **EM 五门禁卡**（见 `booklab/theory.GATES`），
      所以这份演示数据也跟着补齐五条 —— 否则：
        · 判据会照实记"这几条缺门禁"，`notes` 非空 ⇒ C9「没有意外时 notes 应为空」直接红；
        · 更要紧的是，演示模式**演示不出新能力**（门禁与受控标签一个都看不见）。
      ⚠ `可替换项` 一律写成 **「功能位→任意X」**，`不可照搬` 里才点名专名
        —— 这正是泄漏门要求的形状（写反了 `leak_check` 会当场报错）。
    
        English:
    Induction (`book_final`): reusable modules.
        ★ Demo data must **show that it can be taken away**: each entry writes "how to do it / when to use it / why it works",
          and `不适合` **must not be left empty** (if empty, the lesson "know what can't be copied" can't be demonstrated).
        ★ As of 2026-10-10 the module card is upgraded to the **EM five-gate card** (see `booklab/theory.GATES`),
          so this demo data is filled out with the five entries accordingly — otherwise:
            · The criterion will honestly record "these entries lack gates", and non-empty `notes` ⇒ C9 "notes should be empty when there are no surprises" goes red directly;
            · More importantly, demo mode **can't demonstrate the new capabilities** (none of the gates or controlled tags are visible).
            — this is exactly the shape the leak gate requires (if written the other way, `leak_check` errors out on the spot).
    """
    return _j({
        "模块": [
            {"名称": "用动作立人",
             "读者想看什么": "想快速认出这一场里谁值得注意，而不是读一段人物小传。",
             "情绪链": "陌生 → 意外 → 好奇 → 记住 → 期待",
             "戏剧单元": "新角色不自我介绍，用一个只有他做得出的动作 + 一句不合常理的回答"
                         "把自己的处境说清",
             "可替换项": ["新角色→任何第一次上场的人",
                          "小动作→任何只有他会做的举动",
                          "不合常理的答法→任何暴露处境的答非所问"],
             "不可照搬": ["原文那件具体道具", "这一场的地点"],
             "怎么做": "（演示）人物第一次出场不写相貌，给一个**只有他会做**的小动作，"
                       "再让他对一句问话给出一个不太合常理的答法。",
             "什么时候用": "新人物第一次上场、且这一场没有空间给他做自我介绍时。",
             "为什么管用": "读者记住的是行为，不是形容词；动作还顺手把他的处境说清了。",
             "这本书的例子": "主要人物第一次出场那一段。"},
            {"名称": "钩子要具体",
             "读者想看什么": "想知道**一件能说清的事**的下文，而不是含糊的「接下来会怎样」。",
             "情绪链": "悬着 → 忍不住往下看 → 得到一点 → 又悬起来",
             "戏剧单元": "收尾不留感慨，留一个具体到能复述的未解之事",
             "可替换项": ["未解之事→任何能一句话说清并复述的悬念",
                          "留给下一节的引子→任何承接物"],
             "不可照搬": ["原文那个引子的具体形态"],
             "怎么做": "（演示）章末留的问题写成**一件事**（谁把什么拿走了、"
                       "那句话是什么意思），不要写成「将会发生什么」。",
             "什么时候用": "每一章的收尾。",
             "为什么管用": "具体的问题读者会带着翻页；模糊的期待会让人放下。",
             "这本书的例子": "前几章的章末都用了这一手。"},
            {"名称": "给完就接新的",
             "读者想看什么": "刚被满足一次，马上又有一件新鲜事要发生。",
             "情绪链": "释放 → 短暂松弛 → 新的紧张 → 继续读",
             "戏剧单元": "一次爆发收束后不留空档，紧接着抛出一个新问题，"
                         "把注意力从「满足」挪到「接下来」",
             "可替换项": ["新问题→任何能被立刻追问的悬念",
                          "承接口→任何把满足感转成好奇的段落"],
             "不可照搬": ["原文爆发事件的内容"],
             "怎么做": "（演示）一次大爆发之后**不要留空档**，紧接着抛一个新的悬念，"
                       "把读者的注意力从「满足」挪到「接下来」。",
             "什么时候用": "一个大单元收尾的时候。",
             "为什么管用": "满足感会让人合上书；好奇不会。",
             "这本书的例子": "每个单元结束的那一章。"},
        ],
        "节奏": "（演示）单元内先压后爆，爆点落在单元倒数第二章，最后一章接新钩子。",
        "人设": "（演示）主要人物靠「做选择」立，不靠旁白评价；配角靠一句口头禅认人。",
        "语言": "（演示）短句为主，叙述少用形容词，情绪靠动作与器物交代。",
        "不适合": ["（演示）靠巧合推进的段落换本书就不成立",
                   "（演示）单元内必须连续读的顺序，不适合拆成独立短篇"],
        "适用": "（演示）适合写单元剧结构的故事参考：每一单元自成闭环、章末留钩子。",
        "标签": {"题材": ["悬疑"], "读者需求": ["解谜满足", "代入沉浸"],
                 "情绪": ["紧张"], "剧情功能": ["开篇立人", "攀峰"],
                 "适用阶段": ["全篇"]},
    })


def _research(messages):
    return _j({"结果": "（演示）该问题未联网核实：宋代交子为世界最早纸币，初由民间富户联保发行，后收归官办。",
               "来源": "演示语料", "置信": "低"})


# ── 剧组（2026-10-07）──────────────────────────────────────────────────
# 五个新职位各一个 handler。**演示模式也要演得出来** ——
# 没登记的用途会落到"占位 JSON"，那几行字段名对不上，解析器一律判成
# "没出活"，于是演示模式里的剧组面板整片显示"——"（看着像功能没做）。
# 演示数据要**贴这本小说的语境**（雨、茶楼、旧事），不然白演示。
# [EN] ── Crew (2026-10-07)──────────────────────────────────────────────
# [EN] One handler for each of the five new positions. **Demo mode must also be able to act it out** ——
# [EN] an unregistered purpose falls to "placeholder JSON", those field names don't line up, and the
# [EN] parser judges them all as
# [EN] "produced nothing", so the crew panel in demo mode shows "——" all over (looks like the feature
# [EN] wasn't built).
# [EN] Demo data must **fit this novel's context** (rain, teahouse, old matters), otherwise the demo is
# [EN] worthless.
def _crew_story(messages):
    return ("雨下了整夜，檐口的水一线一线地淌。堂里只点了两盏灯，"
            "柜上的账本摊着没合。有人把后门推开一条缝又合上，"
            "楼上的脚步停了一下——谁都没抬头。"
            "到天亮时，账上少的那几文还是没有着落，"
            "而昨晚留在门口的那把伞，已经不见了。")


def _crew_script(messages):
    # ⚠ **`剧情简介` 不能漏**（2026-10-07 第八轮补的）：剧作者的提示词要求它、
    #   `crew/agents.Screenwriter` 也把它收进 `data['剧情简介']`、
    #   `sim/loop._compose_day` 照着它推「今日剧情简介」那张卡 ——
    #   而演示数据里一直**没有这个字段**，于是**演示模式下那张卡永远不出现**
    #   （实测连跑两天：brief 0 次）。演示模式是用户会盯着看的那一版，
    #   这里少一个字段，看起来就是"这个功能没做"。
    #   判据：`tools/verify_mock.py` 会逐个检查 Screenwriter 解析的字段。
    # [EN] ⚠ **`剧情简介` must not be missing** (added in 2026-10-07 round 8): the screenwriter's prompt
    # [EN] requires it,
    # [EN] `crew/agents.Screenwriter` also collects it into `data['剧情简介']`,
    # [EN] `sim/loop._compose_day` uses it to derive the "today's plot summary" card ——
    # [EN] yet the demo data has **never had this field**, so **that card never appears in demo mode**
    # [EN] (measured over two consecutive days: brief 0 times). Demo mode is the version the user will be
    # [EN] staring at,
    # [EN] and a missing field here looks like "this feature wasn't built".
    # [EN] Criterion: `tools/verify_mock.py` checks each field Screenwriter parses one by one.
    return _j({"构思": "这一天从「账上不对」推到「有人不想被认出来」——"
                       "三拍各推一步，最后落在门口那把伞上。",
               "剧情简介": "账上少的那几文要摊到台面上，"
                          "而昨晚进过后门的那个人，不想被认出来。",
               "场景介绍": "堂里只留了两盏灯，柜台后头一片暗。檐水顺着瓦沟往下淌，"
                          "把门外那条街的声音都盖住了。",
               "拍": [
        {"拍": 1, "场": "堂内", "发生": "掌柜合上账本，把少的那几文又数了一遍",
         "推进": "账目不对这件事被摊到明面上"},
        {"拍": 2, "场": "堂内", "发生": "伙计说昨晚有人从后门进来过又走了",
         "推进": "线索从账上转到人身上"},
        {"拍": 3, "场": "门口", "发生": "门口那把多出来的伞不见了",
         "推进": "那个人的存在被确认，且他不想被认出来"},
    ],
        "角色任务": {"主角": ["把少了的那几文弄清楚", "别让外人看出楼里出了事"],
                     "阿枝": ["盯住门口来往的人", "问出后门是谁开的"]}})


def _crew_continuity(messages):
    return _j({"核查": "时间、物件、称呼、在场状态逐条核过，未发现矛盾。",
               "问题": [],
               "结论": "（演示）时间、物件、称呼与在场状态都对得上。"})


def _crew_script_doctor(messages):
    """剧本审读（`crew_script_doctor`）：逐条裁决 + 这一批在说什么。

    ★★ 演示数据里**全部判"过"**，这是**故意**的：

    | 如果演示里也拦 | 会发生什么 |
    |---|---|
    | 拦掉几条 | 演示模式的屏幕会莫名其妙缺几句，而用户根本不知道是被拦了 —— 那是"演示模式下演一个假故障" |
    | **改写成别的句子** | 更难接受：演示输出会被一段固定的模板句顶掉，看起来像程序坏了 |

    所以演示模式只演"**程序真的会去问、也真的会读裁决**"这件事（`过: true`
    与那句 `主题` 都进了台账与日志）。**判"不过"的能力靠 `verify_script_review`
    的桩来验**（那里会真的喂一个"过: false + 改成"）。

    ⚠ 序号**按提示词里给了几条就回几条** —— 客户端是拿序号对回去的，
      回错序号等于没回（`crew/review.verdicts_of` 会把它丢掉）。
    
        English:
    Script review (`crew_script_doctor`): per-entry verdicts + what this batch is about.
        ★★ In demo data **everything is marked "pass"**, this is **intentional**:
        | If the demo also blocked | What would happen |
        |---|---|
        | Block a few entries | Demo mode's screen would inexplicably be missing a few lines, and the user wouldn't know they were blocked — that's "acting out a fake failure in demo mode" |
        | **Rewrite into other sentences** | Even less acceptable: the demo output would be replaced by a fixed template sentence, looking like the program is broken |
        So demo mode only acts out "**the program really does ask and really does read the verdict**" (the `过: true`
        and the `主题` line both go into the ledger and logs). **The ability to judge "fail" is verified by the stub of `verify_script_review`**
        (there it really feeds a "过: false + rewrite").
        ⚠ The sequence numbers **return exactly as many as were given in the prompt** — the client maps back by sequence number,
          returning the wrong sequence number equals not returning at all (`crew/review.verdicts_of` will discard it).
    """
    text = "\n".join(str((m or {}).get("content") or "") for m in (messages or []))
    idx = sorted({int(n) for n in re.findall(r"^\s*(\d+)\.\s*〔", text, re.M)})
    rows = [{"序号": i, "过": True, "问题": "", "改成": ""} for i in idx]
    return _j({
        "核查": "逐条读过：这几句都是人话，说话人、称呼与上文都对得上。",
        "裁决": rows,
        "主题": "（演示）这几句围着同一件事在说：楼里有人在做一件不愿明说的事。",
    })


def _crew_props(messages):
    return _j({"道具": [
        {"名称": "摊开的账本", "用途": "少的那几文落在这页上", "反复": True},
        {"名称": "两盏油灯", "用途": "夜里堂中唯一的光", "反复": False},
        {"名称": "檐下的接水缸", "用途": "雨声与时辰的刻度", "反复": False},
        {"名称": "门口那把伞", "用途": "那个人来过的凭据", "反复": True},
        {"名称": "柜台上的铜钱匣", "用途": "数目对不上的地方", "反复": False},
        {"名称": "半冷的茶壶", "用途": "待客与冷场的由头", "反复": False},
    ], "基调": "潮湿、昏暗、器物都比人安静"})


def _crew_art(messages):
    return _j({"画风": "水墨淡彩、纸本质感，低饱和，不做高光与锐利反光",
               "主色": [{"色": "#3B4A52", "用途": "屋瓦与夜色"},
                        {"色": "#C9A24E", "用途": "灯火与暖处"},
                        {"色": "#6A6F78", "用途": "雨与远景"}],
               "忌": ["高饱和霓虹色", "现代器物", "镜头光斑"]})


def _crew_day_map(messages):
    """**当天地图**（美术按今天的戏画的那张）。

    ⚠ 这里**故意从提示词里抠真实地名**，而不是写死几个名字：
    演示模式下要是硬编"临河茶肆 / 里巷"，那这份产出就跟用户的项目无关，
    后面"只许用白名单里的名字"那条判据也就验不出东西了
    （夹具自己编的名字，恰好说明不了白名单生效）。
    做法：把提示词里"设定里真实存在的地点"那一行后面的名字抓出来。
    
        English:
    **Today's map** (the one art drew for today's scenes).
        ⚠ Here we **intentionally extract real place names from the prompt**, rather than hardcoding a few names:
        In demo mode, if we hardcode "临河茶肆 / 里巷", then this output has nothing to do with the user's project,
        and the later criterion "only names from the whitelist may be used" would then verify nothing
        (a name the fixture made up itself happens to prove nothing about whether the whitelist took effect).
        Approach: extract the names that follow the line "locations that actually exist in the setting" in the prompt.
    """
    import re
    text = ''
    for m in messages:
        if isinstance(m, dict) and m.get('role') == 'user':
            text += str(m.get('content') or '')
    names: list[str] = []
    hit = re.search(r'真实存在的地点[^\n]*\n([^\n]+)', text)
    if hit:
        names = [x.strip() for x in re.split(r'[、,，]', hit.group(1)) if x.strip()]
    beats = re.findall(r'^\s*-\s*\[([^\]]+)\]', text, re.M)
    for b in beats:
        b = b.strip()
        if b and b not in names and len(b) <= 8:
            names.append(b)
    # ⚠ 还要滤掉**提示词里的占位说明**（"（设定里没写地点 —— 那就用剧情里出现的
    #   名字）"这种）：它是以 `（` 开头的整句，不是地名。
    #   第一版没滤，于是那份花的 `当天地图.md` 第一行就是个占位说明当"地点"，
    #   看着像产品在编地名 —— 其实是夹具自己没滤干净。
    # [EN] ⚠ Also filter out the **placeholder notes in the prompt** ("(no location is written in the
    # [EN] setting —— so use the
    # [EN] name that appears in the plot)" and the like): it is a whole sentence starting with `（`, not a
    # [EN] place name.
    # [EN] The first version didn't filter, so the flower's `当天地图.md` had a placeholder note as a
    # [EN] "location" on its first line,
    # [EN] looking like the product was making up place names —— when actually the fixture itself hadn't
    # [EN] filtered cleanly.
    names = [n for n in names
             if n and not n.startswith('（') and not n.startswith('(')
             and n not in ('（未标）', '（未定）')][:4]
    if not names:
        names = ['茶肆']
    out = []
    for i, n in enumerate(names):
        out.append({'名称': n,
                    'x': round(0.5 + (0.26 if i % 2 else -0.26), 2) if i else 0.5,
                    'y': round(0.62 - 0.2 * (i // 2), 2) if i else 0.62,
                    '形': '楼' if i == 0 else '屋',
                    '说明': '（演示）这一场戏到过的地方'})
    links = [[names[i], names[i + 1]] for i in range(len(names) - 1)]
    return _j({'地点': out, '通路': links, '题记': '今日'})


def _atlas_overview(messages):
    """**三级底图 · 整体层**（开卷时一次）—— 见 `ingest/atlas.py`。

    ⚠ 和 `_crew_day_map` 同一个规矩：**从提示词里抠真地名**，不写死演示名。
      硬编名字的话，这份产出就跟用户的项目无关，后面"只许用设定里的地名"
      那条判据也就验不出东西（夹具自己编的名字说明不了白名单生效）。
    抠的是"这些地方"清单里 `- 名称：说明` 的那种行。
    
        English:
    **Tier-3 base map · overall layer** (once at book open) —— see `ingest/atlas.py`.
        ⚠ Same rule as `_crew_day_map`: **extract real place names from the prompt**, do not hardcode demo names.
          If names are hardcoded, this output has nothing to do with the user's project, and the later "only place names from the setting may be used"
          criterion would then verify nothing (a name the fixture made up itself proves nothing about whether the whitelist took effect).
        What is extracted is the `- 名称：说明` style of line from the "these places" list.
    """
    import re
    text = _prompt_text(messages)
    names: list[str] = []
    for m in re.finditer(r'^-\s*([^：:\n]{1,12})(?:[：:][^\n]*)?$', text, re.M):
        n = m.group(1).strip()
        if n and not n.startswith(('（', '(')) and n not in names:
            names.append(n)
    names = names[:8]
    if not names:
        names = ['茶肆']
    out = []
    for i, n in enumerate(names):
        out.append({'名称': n,
                    'x': round(0.2 + 0.6 * ((i % 3) / 2), 2),
                    'y': round(0.25 + 0.22 * (i // 3), 2),
                    '形': '楼' if i == 0 else '屋',
                    '说明': '（演示）这一带的去处'})
    links = [[names[i], names[i + 1]] for i in range(len(names) - 1)]
    return _j({'地点': out, '通路': links, '题记': '小世界'})


def _atlas_place(messages):
    """**三级底图 · 局部 + 室内**（每处一次）。

    `周边` 抠提示词里"这一带还有哪些地方"那段（别处的地名）；
    `内部` 抠"这一处地方"说明里出现过的词 —— 说明写着"两层，后院有口井"，
    这里就该出「后院」和「井」。这正是"名字必须来自设定"那条规矩在演示模式下的体现。
    
        English:
    **Tier-3 base map · local + indoor** (once per place).
        `周边` extracts the "what other places are around here" passage from the prompt (place names elsewhere);
        `内部` extracts words that appear in the "this place" description —— if the description says "two floors, a well in the backyard",
        then here it should produce 「后院」 and 「井」. This is exactly the manifestation, in demo mode, of the rule "names must come from the setting".
    """
    import re
    text = _prompt_text(messages)
    hit = re.search(r'^([^：:\n]{1,12})[：:]([^\n]*)$', text, re.M)
    here = (hit.group(1).strip() if hit else '') or '主屋'
    brief = (hit.group(2).strip() if hit else '')
    inner: list[str] = []
    for w in ('堂', '厅', '院', '井', '柜台', '楼', '门', '廊', '厢房', '灶'):
        if w in brief and w not in inner:
            inner.append(w)
    # 说明里没写就按"这类房子总有的"补最少两个（与提示词的硬要求一致）
    # [EN] If the notes don't specify, fill in the minimum two by "this kind of house always has"
    # [EN] (consistent with the prompt's hard requirement)
    for w in ('堂屋', '后院'):
        if w not in inner and len(inner) < 4:
            inner.append(w)
    out_i = [{'名称': n, 'x': 0.5, 'y': round(0.3 + 0.18 * i, 2),
              '形': '屋' if i == 0 else '院',
              '说明': '（演示）这处房子里的一间'} for i, n in enumerate(inner[:4])]
    others = []
    tail = re.search(r'这一带还有哪些地方[^\n]*\n([^\n]+)', text)
    if tail:
        others = [x.strip() for x in re.split(r'[、,，]', tail.group(1))
                  if x.strip() and not x.startswith(('（', '('))]
    others = [o for o in others if o != here][:3]
    out_l = [{'名称': n, 'x': round(0.2 + 0.3 * i, 2), 'y': 0.7,
              '形': '街' if i == 0 else '屋',
              '说明': '（演示）这处外面挨着的'} for i, n in enumerate(others)]
    return _j({'周边': {'地点': out_l,
                        '通路': [[out_l[i]['名称'], out_l[i + 1]['名称']]
                                 for i in range(len(out_l) - 1)]},
               '内部': {'地点': out_i,
                        '通路': [[out_i[i]['名称'], out_i[i + 1]['名称']]
                                 for i in range(len(out_i) - 1)]}})


def _crew_publicity(messages):
    return _j({"一句话": "账上少了七文，比少了七条命还难查",
               "看点": ["一件小事牵出一桩旧案", "楼里每个人都有不想说的那一句",
                        "雨夜的门不止开过一次"],
               "预告": "那天夜里雨没停。掌柜把账本合上又翻开，"
                       "数目还是不对。有人在门口站了很久，"
                       "没敲门，也没走——后来那把伞就不见了。"})


def _crew_research(messages):
    return _j({"核查": "先挑出称谓与器物两处，逐个比过时代，都站得住。",
               "存疑": [],
               "结论": "（演示）称谓与器物未发现与时代不合之处。"})


# ── 六个"以前没登记、落到占位 JSON"的用途（2026-10-07 补）──
# ★ 为什么必须补：没登记的用途会返回**占位 JSON**，而调用方按各自的解析器
#   去读它 —— 表现分成两种，都不好看：
#     · `group_chat`（要"一句台词"）→ 那一坨 JSON 被**当成台词播到屏幕上**；
#     · `dispatch` / `backstage_summary` / `memory_compact`（有兜底）→
#       静默降级，"演示模式下这些功能等于不存在"，验证脚本也就测不到真路径。
#   演示模式是用户会盯着看的那一版，这里不该有洞。
# [EN] ── Six purposes that "were previously unregistered and fell to placeholder JSON" (added
# [EN] 2026-10-07)──
# [EN] ★ Why they must be added: an unregistered purpose returns **placeholder JSON**, and callers read
# [EN] it with their own parsers
# [EN] —— the manifestations split into two kinds, neither pretty:
# [EN] · `group_chat` (wants "one line of dialogue") → that blob of JSON gets **played on screen as
# [EN] dialogue**;
# [EN] · `dispatch` / `backstage_summary` / `memory_compact` (have fallbacks) →
# [EN] silently degrade, "these features amount to nonexistent in demo mode", and the verify script
# [EN] can't test the real path either.
# [EN] Demo mode is the version the user will be staring at, there should be no holes here.
def _group_chat(messages):
    """群聊轮转：只说**一句**口语（调用方要的就是一句话）。
        English:
    Group chat rotation: say only **one sentence** of colloquial speech (what the caller wants is a
    single sentence).
    """
    return _pick(_LINES_POOL, 1)[0].strip('「」')


def _dispatch(messages):
    """导演派活：`{人物, 要什么}`。**名字从提示词里抓**（派给不在场的人会被丢掉）。

    抓不到就返回空表 —— 与真机"拿不到结果"同一个行为（那一层就空着）。
    
        English:
    Director assigning tasks: `{人物, 要什么}`. **Extract names from the prompt** (assigning to someone
    not present gets dropped).
        If nothing can be extracted, return an empty list —— same behavior as the real machine's "could not get a result" (that layer is then left empty).
    """
    text = "\n".join(str((m or {}).get("content") or "") for m in (messages or []))
    m = re.search(r"在场人物[：:]\s*([^\n]+)", text)
    names = [x.strip() for x in re.split(r"[、,，]", m.group(1)) if x.strip()] if m else []
    wants = ["把昨晚那笔账弄清", "盯住门口那个人", "别让话传到外头去",
             "把后院的门闩换掉", "问出来人找的是谁"]
    return _j({"推演": "账上的窟窿还没堵，门口那个人又赖着不走 —— "
                       "先各推一步，把这两件事都往前提。",
               "派活": [{"人物": n, "要什么": wants[i % len(wants)]}
                        for i, n in enumerate(names[:4])]})


def _backstage_summary(messages):
    return ("（演示）台下这几位这几天照常过着：掌柜守着账，伙计守着门，"
            "账房把该藏的账藏得更深了些。")


def _memory_compact(messages):
    return ("（演示）早先这几天，账上少的那几文一直没着落，"
            "来打听旧事的人换了好几拨，楼里的人谁都没松口。")


def _ctx_compact(messages):
    """**上下文主动压缩**（2026-10-10）：把"较早那一段"折成两三句。

    ⚠ 演示模式里必须登记（`verify_mock` A2 盯着）：漏了的话，主动压缩在演示
      模式下会拿不到正文 → 走"原文前几句"兜底 → 看起来没坏，但**演示模式跑的
      是另一条代码路径**，真正的压缩逻辑等于没被演示过。
    
        English:
    **Proactive context compression** (2026-10-10): fold "the earlier passage" into two or three
    sentences.
        ⚠ In demo mode this must be registered (`verify_mock` A2 is watching): if missed, proactive compression in demo
          mode would fail to get the body text → fall back to "the first few sentences of the original text" → looks unbroken, but **demo mode runs
          a different code path**, so the real compression logic is effectively never exercised by demo.
    """
    return "（演示）早些时候几人把旧账翻了一遍，井底那桩事还没了结。"


def _novel_polish(messages):
    """导出润色：调用方要的是**成稿全文**。

    ⚠ 把上面那批 `messages` 里最后一条的正文原样还回去（前面是让它改的稿子）。
    演示模式下**不许凭空编一段** —— 那样导出物会跟推演结果对不上。
    
        English:
    Export polish: what the caller wants is the **full final draft**.
        ⚠ Return the body text of the last entry in the batch of `messages` above unchanged (the preceding ones are the draft it was asked to revise).
        In demo mode, **do not fabricate a passage out of thin air** —— that would make the export not match the simulation result.
    """
    text = ""
    for m in reversed(messages or []):
        if str((m or {}).get("role") or "") == "user":
            text = str(m.get("content") or "")
            break
    # 把提示词那几行剥掉，只留稿子本身（真机也是"给它稿子、它给稿子"）
    # [EN] Strip those prompt lines and keep only the manuscript itself (on a real machine too it's "give
    # [EN] it a manuscript, it gives a manuscript")
    if "---" in text:
        body = text.split("---", 1)[-1]
        return body.strip() or text.strip()
    return text.strip()


def _review(messages):
    return _j({"问题": [], "结论": "（演示）没发现成篇上的明显问题。"})


def _crew_review(messages):
    """复盘（`crew_review`）：今日总结 + 问题 + 修改意见。

    ★ 演示数据里**故意给一条具体的问题**（点到人名）—— 那是提示词里写死的
      要求（"必须指到具体的人名或具体的句子"）。给一条空的问题列表就演示不出
      这件事，而"复盘说不出问题"恰恰是这个功能最容易退化成没用形态的样子。
    
        English:
    Review (`crew_review`): today's summary + problems + revision suggestions.
        ★ In the demo data, **deliberately give one specific problem** (naming a person) —— that is a requirement hardcoded in the prompt
          ("must point to a specific person's name or a specific sentence"). Giving an empty problem list would leave this un-demonstrated,
          and "review cannot state a problem" is precisely the useless form this feature most easily degrades into.
    """
    text = "\n".join(str((m or {}).get("content") or "") for m in (messages or []))
    who = [x for x in re.findall(r"[\u4e00-\u9fa5]{2,3}", text)]
    name = next((x for x in who if x in ("主角", "阿箬", "周迟",
                                         "陆行舟", "林小满", "崔令")), "主角")
    return _j({
        "总结": f"这一天把主要的那条线往前推了一步：{name}从回避变成了正面接招，"
                "代价是让第三个人看出了端倪。",
        "问题": [f"{name}后半程连着三拍都在原地打转（看、擦、等），"
                 "推进感被这三拍吃掉了"],
        "修改意见": ["把那三拍压成一拍 —— 让他做一件事的同时把态度也交代掉",
                     "结尾那句可以再往回收半句，留白比说尽好看"],
        "需要重演": False})


def _crew_stylist(messages):
    """造型（`crew_stylist`）：每个人身上穿什么、带什么、什么姿态。
        English:
    Styling (`crew_stylist`): what each person is wearing, carrying, and their posture.
    """
    return _j({
        "造型": [
            {"人名": "主角", "穿着": "洗得发白的靛布短褂，袖口卷到小臂",
             "随身物": "一枚磨得发亮的铜钥匙", "仪态": "站着时左手总按在桌角"},
            {"人名": "柳娘", "穿着": "枣红布衫外罩一件旧围裙，围裙角有饼油",
             "随身物": "竹篮上搭着块干净屉布", "仪态": "说话时手在围裙上蹭"},
        ],
        "基调": "都是穿旧了但收拾得干净的人"})


def _crew_sound(messages):
    """声音（`crew_sound`）：这一场听得见什么。
        English:
    Sound (`crew_sound`): what can be heard in this scene.
    """
    return _j({
        "底噪": "檐水一滴一滴落在阶前的石窝里",
        "事件声": ["柜上的算盘被谁的手肘碰了一下", "远处坊门落闸的一声闷响"],
        "静默": "该响而没响的：更鼓"})


def _crew_storyboard(messages):
    """分镜（`crew_storyboard`）：把每一拍拆成镜头。

    ★ 形状必须与 `crew/agents.Storyboard.work()` 的契约一致（`"分镜": [...]`），
      否则演示模式里 `data.get('分镜')` 取不到东西，屏幕上会显示"这一稿不用分镜" ——
      那不是"演示模式没实现"，而是看起来像**产品决定不拆镜头**。
    [EN] Shot list (`crew_storyboard`): split each beat into shots.
    [EN] ★ The shape must match `crew/agents.Storyboard.work()`'s contract (`"分镜": [...]`), otherwise
    [EN] in demo mode `data.get('分镜')` finds nothing and the screen says "no shots for this draft" --
    [EN] which does not read as "demo mode not implemented" but as **the product deciding not to cut shots**.
    """
    return _j({"分镜": [
        {"镜": 1, "拍": 1, "景别": "全景", "画面": "屋里两人隔着一张柜台，谁都没先开口",
         "台词": "", "镜头运动": "固定", "意图": "先让观众看清这两个人在哪儿",
         "叙事点": "这间屋子里的规矩比人先到", "收尾": "柜上的盖子轻轻响了一下"},
        {"镜": 2, "拍": 1, "景别": "近景", "画面": "其中一个人的手停在半空",
         "台词": "这话我只说一遍。", "镜头运动": "推", "意图": "把话的重量压到脸上",
         "叙事点": "说出口的话收不回去", "收尾": "手落回桌面"},
        {"镜": 3, "拍": 2, "景别": "中景", "画面": "另一个人转身时衣角扫过门框",
         "台词": "", "镜头运动": "跟", "意图": "让这场戏跟着人走出去",
         "叙事点": "该走的人还是会走", "收尾": "门帘落下"},
    ]})


def _coordinator(messages):
    """协调引擎（`coordinator`）：把用户的一句话归到剧组/人物/全局。

    ★ 形状与 `crew/coordinator.py` 的约定一致（`type` / `target` / `instruction`）。
      漏登记会落到占位 JSON ⇒ `coordinator` 解析不出来就返回 None ⇒
      演示模式里"给剧组下指令"永远**没有任何反应**（看起来像功能没做）。
    [EN] Coordinator (`coordinator`): classify one user sentence to a crew role / actor / global.
    [EN] ★ Shape matches `crew/coordinator.py`'s contract (`type` / `target` / `instruction`).
    [EN] Unregistered falls to placeholder JSON => the coordinator cannot parse it and returns None =>
    [EN] in demo mode "give the crew an instruction" **never does anything** (looks unimplemented).
    """
    return _j({"type": "global",
               "target": "",
               "instruction": "整体节奏放慢一点，多留些人物动作与环境，别急着推进主线。"})


def _crew_polish(messages):
    """语言审校（`crew_polish`）：哪几句 AI 味重、该怎么改。

    ★ 演示数据里的两条都**故意给出可在原文里找到的片段**（提示词里有这条要求）。
      片段找不到，作者照着去搜就搜不着 —— 那比不报还烦人。
    
        English:
    Language polish (`crew_polish`): which sentences are heavy with AI flavor, and how to fix them.
        ★ Both entries in the demo data **deliberately give fragments findable in the original text** (the prompt has this requirement).
          If the fragment cannot be found, the author searching for it will not find it —— that is more annoying than not reporting it at all.
    """
    return _j({
        "核查": "两句都不是这个人物会说的话：一句靠修饰词撑，一句是对仗腔。",
        "问题": [
            {"原句": "他深深地叹了一口气",
             "怎么改": "把「深深地」删掉，或者换成一个具体动作（手在围裙上蹭了两下）"},
            {"原句": "不是害怕，而是失望",
             "怎么改": "这种对仗句用一次可以，连着用就成模板了 —— 改成直接说做了什么"},
        ],
        "总评": "整体干净，主要是修饰词偏多，删掉三分之一会更利落。"})


def _crew_rehearsal(messages):
    """排练（`crew_rehearsal`）：剧本定稿后空走一遍。

    ⚠ 演示数据**给的是「走得通」**（空问题表），不是"故意挑两个毛病"：
      给问题的话，每一条剧本都会被退回重写，日志里一排
      「排演出 N 处走不下去」—— 那是**演示数据造成的假现象**，
      与 `_crew_verify` 当初必须回 `通过: true` 是同一个道理。
      真机下模型会不会挑出问题，是它自己的判断。
    
        English:
    Rehearsal (`crew_rehearsal`): run through the script once after it is finalized.
        ⚠ The demo data **gives "it works out"** (an empty problem list), not "deliberately pick two flaws":
          if problems were given, every script would be sent back for rewrite, with a row in the log of
          「rehearsal hits N places it cannot get through」 —— that is a **false phenomenon caused by the demo data**,
          the same reasoning as why `_crew_verify` had to return `通过: true` back then.
          Whether the model on the real machine will pick out problems is its own judgment.
    """
    return _j({"问题": [], "结论": "（演示）一屋子人过了一遍，这一天的戏走得通。"})


def _crew_day_novel(messages):
    """整理当天这一章（`crew_day_novel`）：把今天实际发生的写成小说形式。

    ★ 与 `_crew_story`（开演前那一段"打算写什么"）**必须不同** ——
      两者要是同一段文字，「当天故事.md」就成了样章的副本，
      而它还标着"按天累积的可读稿"，看起来像真的、其实什么都没做。
      这里的口径是**今天演完之后**的口吻（收尾、余味）。
    
        English:
    Organize today's chapter (`crew_day_novel`): write what actually happened today in novel form.
        ★ It **must differ** from `_crew_story` (the "what we plan to write" passage before the show starts) ——
          if the two were the same text, "当天故事.md" would become a copy of the sample chapter,
          and yet it is still labeled "a readable draft accumulated by day", looking real while actually doing nothing.
          The register here is the tone **after today's performance is over** (wind-down, lingering aftertaste).
    """
    return ("这一天的戏收在灯上。堂里那两盏油灯先后暗下去，"
            "最后只剩下柜台上一点光，照着摊开没合的账本。"
            "人一个个散了，谁也没再提那几文钱的事——"
            "可门闩是夜里才落的，落闩的人还回头看了一眼那张桌子。"
            "雨到后半夜才停。第二天早上，门口那把伞不在原地了。")


def _prose_flow_fix(messages):
    """平铺段重写（`prose_flow_fix`）：把一段"清单"重写成一个铺开的段落。

    ⚠ 返回的**长度必须接近原文**：`_fix_flat_paragraphs` 有 0.6–2.2 倍的长度闸，
      返回空串或一句话会被判"不可用"并保留原文 —— 那样演示模式里这一步
      等于没做，而日志上又写着"重写过"，比不做还糟（用户看到的是原来的碎句）。
    [EN] The returned text **must be close in length to the source**: `_fix_flat_paragraphs`
    [EN] enforces a 0.6-2.2x length gate, and a one-line reply gets rejected (the original is
    [EN] kept) -- so in demo mode the step would look done in the log while the text is unchanged.
    """
    body = str((messages[-1].get('content') if messages else '') or '')
    marker = '── 原文 ──'
    i = body.find(marker)
    src = body[i + len(marker):].strip() if i >= 0 else ''
    if not src:
        return ('他站在那儿没动，手里的东西还没放下，屋里静得能听见窗外的风，'
                '过了一会儿才想起该把门掩上。')
    # 把句号换成逗号并成两句：长度几乎不变，形状从"一句一件事"变成"一句里套着写"。
    # [EN] Turn periods into commas: length stays about the same, but the shape changes from
    # [EN] "one thing per sentence" to "several things inside one sentence".
    flat = src.replace('。', '，').rstrip('，')
    return flat + '。'


def _crew_settings(messages):
    """编剧室三方会审（`crew_settings`）：讨论该补哪些**局部**设定。

    ★ 演示数据里**故意放一条"世界层"的**：它会被 `world/layers.why_reject`
      当场拒收。这不是演示 bug —— 它正是要演示"**剧组不能动总体设定**"
      这条闸门是活的（日志与台账里会写明拒收原因）。
    ★ 场合从提示词里抓（`当前地点：X`），抓不到就改用**限时**作用范围
      —— 一条既不限地点、也不限人、也不限时的"局部设定"会被拒收，
      那样演示模式下这条链就是空跑的。
    
        English:
    Writers' room three-way review (`crew_settings`): discuss which **local** settings should be
    added.
        ★ The demo data **deliberately includes one "world layer" entry**: it will be rejected on the spot by `world/layers.why_reject`.
          This is not a demo bug —— it is precisely to demonstrate that the gate "**the crew must not touch the overall setting**"
          is alive (the rejection reason is written in the log and ledger).
        ★ The occasion is extracted from the prompt (`当前地点：X`); if it cannot be extracted, switch to a **time-limited** scope
          —— a "local setting" that is limited neither by place, nor by person, nor by time would be rejected,
          and in that case this chain in demo mode is just running empty.
    """
    text = "\n".join(str((m or {}).get("content") or "") for m in (messages or []))
    m = (re.search(r"当前地点[：:]\s*([^\n，,。；;|]+)", text)
         or re.search(r"场景[：:]\s*([^\n，,。；;|]+)", text))
    where = (m.group(1).strip() if m else "")[:12]
    scope = {"场合": where} if where else {"生效时机": "第1-30天"}
    items = [
        {"层": "细节", "名称": "缺角的紫砂壶",
         "内容": "柜上那把壶缺了个角，谁也动不得，掌柜自己也不用它",
         "影响谁": ["主角"], "为什么": "给他为什么守着这间铺子一个能演的理由",
         **scope},
        {"层": "场景", "名称": "后门的门轴",
         "内容": "后门门轴旧了，推开总有半声哑响 —— 夜里谁都听得见",
         "为什么": "夜里进出这件事需要一个具体的响声",
         **scope},
        {"层": "世界层", "名称": "这座城其实归外邦管",
         "内容": "整座城其实由外邦暗中治理",
         "为什么": "（演示：这一条会被拒收 —— 剧组不许动总体设定）"},
    ]
    return _j({"讨论": "三人都认为：不必动世界观，补两件小东西就够演了。",
               "新增设定": items})


def _crew_extra(messages):
    """群演统筹投人（`crew_extra`）。

    演示数据要**换着来**：每次都给同一个人就演示不出"投人"这件事的意义
    （真机下模型是照着这一场的戏挑人的）。
    
        English:
    Extra coordinator casting (`crew_extra`).
        Demo data must **vary**: always giving the same person fails to demonstrate the point of "casting"
        (on real machines the model picks people based on that scene's drama).
    """
    pool = [
        {"称呼": "卖炭的老汉", "诉求": "问掌柜收不收昨夜的炭钱", "标志": "肩上落着灰"},
        {"称呼": "讨账的伙计", "诉求": "递上一张没署名的欠条", "标志": "袖口磨破了"},
        {"称呼": "撑伞的女客", "诉求": "打听一个三年前搬走的人", "标志": "伞骨断了一根"},
        {"称呼": "跑腿的小子", "诉求": "送来一封淋湿的信就要走", "标志": "赤着脚"},
    ]
    return _j(random.choice(pool))


def _crew_verify(messages):
    """导演的验算（`day_verify`）。

    ⚠ 以前没登记它 —— 落到占位 JSON（没有 `通过` 字段）→ 被正确地判成
      "没拿到结论" → 于是**演示模式下每一条剧本都要重写满 3 轮**，
      日志里一排「验算仍未通过（照用）」。那不是 bug，是**演示数据缺了一档**：
      真机下模型是会给结论的，演示模式得把它补上，否则看到的现象是假的。
    
        English:
    Director's verification (`day_verify`).
        ⚠ It wasn't registered before -- fell back to placeholder JSON (no `通过` field) -> was correctly judged as
          "no conclusion obtained" -> so **in demo mode every script had to be rewritten for a full 3 rounds**,
          with a row of "verification still not passed (used anyway)" in the logs. That's not a bug, it's **missing a tier of demo data**:
          on real machines the model does give a conclusion, and demo mode must supply it, otherwise the observed behavior is fake.
    """
    return _j({"通过": True, "问题": [],
               "修改意见": "（演示）无需修改。"})



def _help_qa(messages):
    """使用问答（帮助面板的「问个问题」）—— 演示模式。

    ★ 「依据」从**提示词里检索到的小节标题**抓（下面那个正则），不硬编码：
      演示模式没有资格替用户决定"这一问落在说明书的哪一节"。
      抓法：`manual_qa.build_prompt` 把命中章节写成 `## <标题>` 那几行。
    
        English:
    Q&A usage (the help panel's "Ask a question") -- demo mode.
        ★ "Basis" is captured from **the section titles retrieved in the prompt** (the regex below), not hardcoded:
          demo mode has no right to decide for the user "which section of the manual this question falls under".
          Capture method: `manual_qa.build_prompt` writes the matched sections as the `## <title>` lines.
    """
    text = "\n".join(str(m.get("content") or "") for m in messages)
    titles = re.findall(r'(?m)^## (.+)$', text)
    src = titles[0].strip() if titles else "使用说明"
    more = f"（演示模式只列第一条，实际会有 {len(titles)} 条）" if len(titles) > 1 else ""
    return (f"（演示模式）这一条《使用说明》里有写，正式模式下这里会是照着"
            f"上面几节内容给出的回答。\n\n依据：{src}{more}")


def _repair_source(messages):
    """AI 补全缺口（回写引用文件夹，`ingest/repair.py`）—— 演示模式。

    ⚠ 「归类」里的文件名**从提示词里列出的那几个**取（正则在下面），
      不硬编码某个具体名字 —— 那份结果会被写进用户引用文件夹的
      `.nws_classify.json`，mock 没有资格替用户决定哪个文件叫什么。
    
        English:
    AI gap filling (writes back to the reference folder, `ingest/repair.py`) -- demo mode.
        ⚠ In "classification", the filenames **are taken from those listed in the prompt** (regex below),
          not hardcoding a specific name -- that result gets written into the user's reference folder's
          `.nws_classify.json`, mock has no right to decide for the user what each file is called.
    """
    text = "\n".join(str(m.get("content") or "") for m in messages)
    m = re.search(r'写进 "归类"：(.+)', text)
    files = [x.strip() for x in (m.group(1).split("、") if m else []) if x.strip()]
    return _j({
        "人物字段": [],
        "伏笔": [],
        "大纲": "",
        "世界观": "（演示模式）一座常年落雨的临河小城，人情密、口风紧；"
                "旧事压在青石板底下，谁提谁犯忌。",
        "归类": [{"文件": f, "类别": "正文", "理由": "（演示模式）通篇是小说的行文"}
                 for f in files],
    })


def _markdown(kind: str, messages) -> str:
    if kind == "storyline":
        return f"""# 故事线汇总（{DEMO_TAG}）

## 一、故事线脉络
- N01 雨夜来客 → 陌生人带来旧事的消息
- N02 旧事浮头 → 说法不一，缝隙出现

## 二、关键场景
- 临河茶肆·入夜：来客只问一句旧事，屋里的灯晃了一下。

## 三、精彩情节
> {_pick(_LINES_POOL,1)[0]}　{_pick(_INNER_POOL,1)[0]}

## 四、人物弧线
- 掌柜：守秘 → 被动卷入 → 开始主动遮掩

## 五、伏笔状态表
| 编号 | 内容 | 状态 |
| --- | --- | --- |
| F01 | 后院那口井夜里会响 | 已埋设 |

## 六、未选之路
- 若当场摊牌：冲突提前，线索作废。

## 七、可用素材清单
- 雨夜叩门的那段对白，可直接改写进正文开场。
"""
    if kind == "outline":
        return f"""# 大纲建议（{DEMO_TAG}）

## 一、节点对照表
| 节点 | 原计划 | 实际发生 | 建议改写 |
| --- | --- | --- | --- |
| N01 | 来客叩门 | 来客叩门并留下信物 | 把信物提前，作为后文回收点 |

## 二、新增支线
- 后院古井的响声（来源：E004），可作为独立单元。

## 三、伏笔更新
- F01 已埋设，建议回收节点 N04。

## 四、后续节点建议
- N03 破绽：让最可信的人说错一句行话。

## 五、人物弧线大纲
- 掌柜：守 → 疑 → 遮 → 认
"""
    if kind == "summary":
        return f"""# 运行小结（{DEMO_TAG}）

## 1 运行概览
模式 story｜故事 2 天｜事件 6 个｜token 0（演示不计费）

## 2 本次故事线
N01 雨夜来客 → N02 旧事浮头

## 3 关键情节
- 来客留下没有署名的信。

## 4 重要场景
- 临河茶肆·戌时。

## 5 精彩片段
> {_pick(_LINES_POOL,1)[0]}

## 6 人物弧线与表现
- 掌柜：稳，戏份足。伙计：偏扁平，建议补秘密。

## 7 设定与框架优化建议
- 补人物口癖与秘密；伏笔编号。

## 8 后续故事发展建议
- 下一批章节走「破绽」节点。

## 9 新设定建议 / 10 未选之路 / 11 贴单
- 演示模式，零成本。
"""
    return f"{DEMO_TAG}（演示输出）"


def _crew_agents_infer(messages):
    """开卷那一步：为这本书推断各职位的定制（演示模式）。

    ★ 职位名**从提示词里抓**（"key ｜ 中文名 ｜ 职责" 那几行）—— 与
      `_crew_settings` 抓地点、`_book_scan` 抓章名同一手法：
      演示模式没资格替作者决定"这个剧组有哪些职位"，
      名册改了这里要跟着变，而抓提示词就自动跟上。
    
        English:
    The book-opening step: infer each position's customization for this book (demo mode).
        ★ Position names **are captured from the prompt** (the "key | Chinese name | responsibility" lines) -- the same technique as
          `_crew_settings` capturing locations and `_book_scan` capturing chapter names:
          demo mode has no right to decide for the author "which positions this crew has";
          when the roster changes this must change accordingly, and capturing from the prompt keeps up automatically.
    """
    text = _prompt_text(messages)
    keys: list = []
    for line in text.splitlines():
        m = re.match(r'^([A-Za-z_][A-Za-z_0-9]*)\s*｜', line.strip())
        if m:
            keys.append(m.group(1))
    if not keys:
        return json.dumps({}, ensure_ascii=False)
    note = '这一本要贴着题材走：多盯线索与人物关系，别写套话。'
    return json.dumps({k: note for k in keys[:40]}, ensure_ascii=False)


def _crew_custom(messages):
    """作者自建职位的出工（演示模式）。
        English:
    Author-built positions' worker dispatch (demo mode).
    """
    return ('（演示模式）我今天照这份活走了一遍：该看的地方都看过了，'
            '没有发现需要你立刻处理的问题；真机上这里会是这个职位的具体结论。')


def _cost_facts(messages) -> dict:
    """从「花费与优化」那一页发出去的提示词里，把**素材 JSON** 捞回来。

    ★ 演示模式必须**照着这份账**说话：写死一句"建议开启前缀缓存"的话，
      在演示模式下与真实账目毫无关系 —— 而用户第一次点这个按钮多半就在
      演示模式下（还没配模型），看到假建议会以为这功能是装饰。
    ⚠ 解析失败就返回 `{}`（调用方各自给兜底），别抛：演示模式出问题不该
      把界面弄挂。
    [EN] Pull the **material JSON** back out of the prompt sent by the "Cost & Tuning" page.
    ★ Demo mode must speak **from this bill**: a hardcoded line has nothing to do with the real
    numbers, and the first click usually happens in demo mode (no model configured yet), so fake
    advice makes the feature look decorative.
    """
    text = _prompt_text(messages)
    i = text.find('数据：')
    if i < 0:
        return {}
    # ⚠ 不能直接 `json.loads(text[i+3:])`：路由器在 `json_mode` 下会在**末尾**
    #   追加一句"请仅以 JSON 回答"，于是那一段后面挂着中文 —— 严格解析必然失败，
    #   而失败是**静默**的（返回 `{}`，建议看着正常、数字全是兜底值）。
    #   实测就是这么翻的：`model_changes` 一直是空的。
    # [EN] ⚠ Do not `json.loads(text[i+3:])`: under `json_mode` the router appends "answer with
    # [EN] JSON only" **after** the payload, so strict parsing always fails -- and it fails
    # [EN] **silently** (returns `{}`, advice looks fine but every number is a fallback).
    from util.jsonio import extract_json
    v = extract_json(text[i + 3:], default=None)
    return v if isinstance(v, dict) else {}


def _cost_advice(messages):
    """花费分析的演示回复（`cost_advice`）：结论 / 改配置 / 换模型。

    ★ 数字全部**从素材里取**（最贵的那个用途、它当前的命中率、当前配置值），
      这样演示模式下的建议与屏幕上那张表对得上。
    ⚠ 建议值必须过得了 `check_change`（范围合法）—— 否则界面上那颗「应用」
      按钮不出现，演示模式看起来就是"这个功能点不动"。
    [EN] Demo reply for the spend analysis: conclusion / config change / model swap.
    ★ Every number is **taken from the material** so the advice matches the table on screen.
    ⚠ Suggested values must pass `check_change` (in range), otherwise the "Apply" button never
    appears and the demo looks broken.
    """
    f = _cost_facts(messages)
    rows = [r for r in (f.get('按用途') or []) if isinstance(r, dict)]
    top = rows[0] if rows else {}
    name = str(top.get('purpose') or 'agent_decide')
    share = float(top.get('share') or 0)
    hit = float(top.get('hit') or 0)
    cfg = f.get('当前配置') or {}

    def _cur(key, default):
        v = (cfg.get(key) or {}).get('value')
        return default if v is None else v

    every = _cur('SCRIPT_REVIEW_EVERY_TICKS', 1)
    try:
        every_n = int(float(every))
    except (TypeError, ValueError):
        every_n = 1
    nxt = min(20, max(1, every_n + 1))
    # 换模型：从登记表里挑一个**不是现在这个**的（挑不到就不给这条建议）
    models = [m for m in (f.get('可换的模型') or []) if isinstance(m, dict) and m.get('key')]
    tiers = f.get('三档现用模型') or {}
    cur_cheap = (tiers.get('cheap') or {}).get('key') or ''
    alt = next((m for m in models if m['key'] != cur_cheap), None)
    out = {
        'summary': (f'最贵的是 {name}（占 {share:.0%}，命中率 {hit:.0%}）—— '
                    f'先动它，别平均用力。'),
        'where': [{'purpose': name,
                   'why': f'输入 token 里只有 {hit:.0%} 命中缓存，'
                          f'而它摊掉了 {share:.0%} 的花费面。'}],
        'config_changes': [{
            'key': 'SCRIPT_REVIEW_EVERY_TICKS',
            'now': str(every),
            'suggest': str(nxt),
            'why': '审读是每一拍都跑的那一个，隔一拍过一次并看不出差别，'
                   '但调用次数直接少一半。',
            'expect': '审读那一项的调用次数约减半（省的是输入 token）。',
        }],
        'model_changes': [],
        'software': [{
            'title': '把每拍一字不变的纪律段全部前移',
            'how': '拼装顺序改成 固定段 → 半固定段 → 动态段 → 尾部，'
                   '让厂商前缀缓存能连上。',
            'expect': '这一项若能把命中率从个位数提到六成，输入那半边约省一半。',
            'risk': '顺序一动，段与段之间的指代（"上面那条"）要重新检查。',
        }],
    }
    if alt:
        out['model_changes'].append({
            'tier': 'cheap',
            'now': cur_cheap or '（跟默认走）',
            'suggest': alt['key'],
            'why': '便宜档只跑结论型的小活（判定 / 抽取），'
                   '换成单价更低的那个不影响正文质量。',
            'expect': '这一档的单价下来一截；调用量不变。',
        })
    return _j(out)


def _cost_deep(messages):
    """深度优化的演示回复（`cost_deep`）：重点在**软件层**那几条。

    ★ 演示模式也要给出"看得懂、能落地"的软件层建议（拼装顺序 / 裁剪 / 批处理），
      否则演示模式里这一颗按钮永远只吐一句废话，与"没实现"看不出区别。
    [EN] Demo reply for the deep pass: the **software-level** items are the point.
    ★ It must still say something concrete (order / trimming / batching), otherwise the button
    looks unimplemented in demo mode.
    """
    base = json.loads(_cost_advice(messages) or '{}')
    rows = [r for r in (_cost_facts(messages).get('按用途') or []) if isinstance(r, dict)]
    name = str((rows[0] if rows else {}).get('purpose') or 'agent_decide')
    base['summary'] = (f'软件层还有三处可动：{name} 的拼装顺序、上下文裁剪时机、'
                       '以及同一拍里那几个 Agent 的公共段重复发送。')
    base['software'] = [
        {'title': '同一拍的公共段只发一次',
         'how': '人物决策 / 剧本审读 / 导演事件在同一个时间点各发一次请求，'
                '它们的前半段是同一份规则与设定 —— 抽成一次"公共段请求"，'
                '其余几个引用它的结果。',
         'expect': '这一拍的输入量约按 Agent 数量线性下降。',
         'risk': '公共段的结论被后面几个复用，若其中一个需要更细的上下文，'
                 '要单独补发（否则质量会掉）。'},
        {'title': '上下文裁剪从"按字数"改成"按有没有用"',
         'how': '现在超长就掐掉最早的部分；改成先删"这一拍没人提到的旧道具/旧地点"'
                '整段，再考虑动台词。',
         'expect': '同样字数下保住更多有用上文，或同样质量下少发一截。',
         'risk': '"没人提到"的判定会误删伏笔，需要一个"钉住不许删"的清单。'},
        {'title': '把"每拍都要跑"的判定类调用合并',
         'how': '审读的规则层（残留 JSON / 占位话 / 出戏词 / 标点）已经是零成本；'
                '把"要不要过模型"的判断也交给规则，模型那一步只在真的可疑时才发。',
         'expect': '判定类调用次数下降，输入量随之下降。',
         'risk': '规则判不出的问题会漏（例如"像不像这个人"），需要定期抽样回看。'},
    ]
    return _j(base)


_HANDLERS = {
    "extract": _extract, "genre": _genre, "style": _style,
    "progress": _progress, "alignment": _alignment, "opening": _opening,
    "agent_decide": _agent_decide, "dialogue": _dialogue, "narrative": _narrative,
    "director_event": _director_event, "branch": _branch, "progress_eval": _progress_eval,
    # ★★ 2026-10-19：**探测（`probe`）也要有假回复**。
    #   上一轮给 `llm/probe.py` 补了用量记账（`purpose='probe'`），但没在演示模式的
    #   登记表里加这一档 ⇒ `verify_mock` 的 A2 当场抓到「漏登记：['probe']」。
    #   漏登记的后果不是报错，是**静默落到占位 JSON** —— 演示模式下"模型探测"
    #   会显示成"连不上"，看起来像网络故障，其实是演示数据缺一档。
    #   ⚠ 探测要的是"能不能拿到一句话"，所以给一句有内容的短句就够。
    # [EN] ★★ 2026-10-19: **probing needs a canned reply too.** The previous round added usage
    # [EN] bookkeeping to `llm/probe.py` (`purpose='probe'`) without registering it here, and
    # [EN] `verify_mock` A2 caught it ("missing: ['probe']"). The consequence is not an error but a
    # [EN] **silent fallback to placeholder JSON** -- in demo mode "probe model" would look like a
    # [EN] network failure. ⚠ Probing only needs "can we get a line back".
    "probe": lambda m: "好的",
    "compliance": _compliance, "importance": _importance, "reflect": _reflect,
    "plan": _plan, "optimize": _optimize, "research": _research,
    "optimize_review": _optimize_review, "optimize_apply": _optimize_apply,
    "repair_source": _repair_source,
    # 前情提要（跨天时每人一次，见 `RunLoop._summarize_day`）
    # ⚠ `_pick(pool, n)` 返回的是**列表**（`random.sample`），要取 [0]；
    #   写成 `_pick(pool, 0)` 会拿到空列表 —— 摘要那边 `.strip()` 当场抛异常，
    #   被 catch 吞成"这一天的前情提要没生成"（冒烟测出来的，2026-10-06）。
    # [EN] Recap (once per person when crossing days, see `RunLoop._summarize_day`)
    # [EN] ⚠ `_pick(pool, n)` returns a **list** (`random.sample`), take [0];
    # [EN] writing it as `_pick(pool, 0)` gets an empty list —— on the summary side `.strip()` throws
    # [EN] immediately,
    # [EN] caught and swallowed into "today's recap wasn't generated" (found by smoke test, 2026-10-06).
    "day_summary": lambda m: _pick([
        "这一天里，那封没有署名的信始终没人来认领，掌柜把它收进了账本夹层。",
        "阿枝问起了旧事，掌柜没有正面回答 —— 两人之间第一次留下没说完的话。",
        "镇上来了生面孔，四处打听三年前那桩事，没有一个人愿意接话。",
    ], 1)[0],
    # 使用问答（帮助面板的「问个问题」）。**依据从提示词里抓**，不硬编码 ——
    # 演示模式没有资格替用户决定"这一问对应说明书的哪一节"。
    # [EN] Usage Q&A (the help panel's "ask a question"). **Take the basis from the prompt**, don't
    # [EN] hardcode ——
    # [EN] demo mode has no right to decide for the user "which section of the manual this question
    # [EN] corresponds to".
    "help_qa": _help_qa,
    "storyline": lambda m: _markdown("storyline", m),
    "outline": lambda m: _markdown("outline", m),
    "summary": lambda m: _markdown("summary", m),
    # ── 剧组（2026-10-07）──
    # ⚠ `day_story` / `day_script` 是编剧组那两个 purpose 的**既有名字**
    #   （`crew/agents.py` 的 `Novelist` / `Screenwriter` 用的就是它们）——
    #   以前 MOCK 里没登记，落到占位 JSON，字段名对不上 → 演示模式下
    #   编剧组永远"没出活"。现在登记上，演示模式里剧组整班人是活的。
    # [EN] ── Crew (2026-10-07)──
    # [EN] ⚠ `day_story` / `day_script` are the **existing names** of those two screenwriter-group purposes
    # [EN] (what `Novelist` / `Screenwriter` in `crew/agents.py` use) ——
    # [EN] previously unregistered in MOCK, fell to placeholder JSON, field names didn't line up → in demo
    # [EN] mode
    # [EN] the screenwriter group never "produced anything". Now registered, and in demo mode the whole
    # [EN] crew is alive.
    "day_story": _crew_story,
    "day_script": _crew_script,
    "day_verify": _crew_verify,
    "crew_continuity": _crew_continuity,
    "crew_props": _crew_props,
    "crew_art": _crew_art,
    "crew_day_map": _crew_day_map,
    # 三级底图（2026-10-08）：开卷时一次。不登记 → 落到占位 JSON，
    # 底图永远生成不出来，而"每天现画"看起来一切正常（最难发现的那种）。
    # [EN] Three-level base map (2026-10-08): once at book opening. Unregistered → falls to placeholder
    # [EN] JSON,
    # [EN] the base map can never be generated, yet "drawing fresh every day" looks perfectly normal (the
    # [EN] hardest kind to notice).
    "atlas_overview": _atlas_overview,
    "atlas_place": _atlas_place,
    "crew_publicity": _crew_publicity,
    "crew_research": _crew_research,
    "crew_extra": _crew_extra,
    # 编剧室三方会审（`world/layers` 的分层设定：只补场景层/细节层）
    # [EN] Screenwriter's room three-party review (`world/layers` layering setting: only fill in scene
    # [EN] layer / detail layer)
    "crew_settings": _crew_settings,
    "crew_review": _crew_review,
    "crew_stylist": _crew_stylist,
    "crew_sound": _crew_sound,
    # ★ 2026-10-17 补登记（`verify_mock` A2 报漏这两条）：
    #   `crew_storyboard`（分镜）与 `coordinator`（协调引擎）
    #   都是"到模型那儿取一个 JSON 结构"的调用，没假回复就是静默降级。
    # [EN] ★ Registered 2026-10-17 (`verify_mock` A2 reported both missing):
    # [EN]   `crew_storyboard` (shot list) and `coordinator` (instruction classifier) both
    # [EN]   fetch a JSON structure from the model; without a fake reply they degrade silently.
    "crew_storyboard": _crew_storyboard,
    "coordinator": _coordinator,
    "crew_polish": _crew_polish,
    # 剧本审读（2026-10-08）：上屏之前逐条裁决的那一次调用。
    # ⚠ 不登记的话会落到占位 JSON —— 审读拿不到"裁决"就按"全部放行"处理
    #   （那是**正确**的兜底），于是演示模式里这个职位看起来永远在空转。
    # [EN] Script review (2026-10-08): the call that rules item by item before going on screen.
    # [EN] ⚠ If unregistered it falls to placeholder JSON —— the review can't get a "ruling" so treats it
    # [EN] as "release everything"
    # [EN] (which is the **correct** fallback), so in demo mode this position looks like it's forever
    # [EN] spinning idle.
    "crew_script_doctor": _crew_script_doctor,
    # ── 排练与当天整理（2026-10-07）──
    #   排练：`crew/agents.Rehearsal`（剧本定稿后空走一遍）。
    #   ⚠ 演示数据给的是**走得通**（空问题表），否则每一条剧本都会被退回重写，
    #     屏幕上就会看到"排练 → 重新修改"一直在转（那是假现象）。
    # [EN] ── Rehearsal and same-day tidying (2026-10-07)──
    # [EN] Rehearsal: `crew/agents.Rehearsal` (a dry run after the script is finalized).
    # [EN] ⚠ Demo data must be a **workable** path (empty question list), otherwise every script entry gets
    # [EN] sent back for rewrite,
    # [EN] and the screen will show "rehearsal → revise again" spinning forever (that's a false symptom).
    "crew_rehearsal": _crew_rehearsal,
    #   整理当天这一章：`Novelist.work(transcribe=…)`（收工后写成小说）。
    # [EN] Wrap up the day's chapter: `Novelist.work(transcribe=…)` (write it into the novel after
    # [EN] finishing work).
    "crew_day_novel": _crew_day_novel,
    #   整理稿里的**平铺段重写**（`crew/agents.Novelist._fix_flat_paragraphs`，2026-10-19）。
    # [EN] Rewrite of a flat paragraph inside the organized draft (2026-10-19).
    "prose_flow_fix": _prose_flow_fix,
    # ── 六个"以前漏登记"的用途（2026-10-07 补，见上面那段说明）──
    #   漏登记的表现：`group_chat` 把占位 JSON **当台词播出去**；
    #   其余四个静默降级（演示模式里这些功能等于不存在）。
    #   判据：`tools/verify_mock.py`（"产品用到的每个 purpose，MOCK 都要登记"）。
    # [EN] ── Six "previously unregistered" purposes (added 2026-10-07, see the note above) ──
    # [EN] Symptom of missing registration: `group_chat` **broadcasts the placeholder JSON as dialogue**;
    # [EN] the other four silently degrade (in demo mode these features effectively don't exist).
    # [EN] Criterion: `tools/verify_mock.py` ("every purpose the product uses must be registered in MOCK").
    "group_chat": _group_chat,
    "dispatch": _dispatch,
    "backstage_summary": _backstage_summary,
    "memory_compact": _memory_compact,
    "ctx_compact": _ctx_compact,
    "novel_polish": _novel_polish,
    "review": _review,
    # ── 打磨 Agent（2026-10-07）──
    #   演示模式要演得出**真实的 Agent 循环**：第 1 步调一个工具，第 2 步收尾。
    #   一步就收尾的话，"工具那条路通不通"在演示模式里永远验不到。
    # [EN] ── Polish Agent (2026-10-07) ──
    # [EN] Demo mode must show a **real Agent loop**: step 1 calls a tool, step 2 wraps up.
    # [EN] If it wraps up in one step, "whether the tool path works" can never be verified in demo mode.
    "polish_step": _polish_step,
    "polish_reflect": _polish_reflect,
    # ── 拆书（2026-10-07）──
    #   演示模式要**真演得出四道工序**：粗扫给逐章行、精拆给笔记、归纳给模块。
    #   ⚠ 章名**从提示词里抓**（不硬编码）—— 演示模式是拿**用户传进来的那本书**
    #    在演，抓不到章名就没法把逐章行对回去（与 `_crew_settings` 抓地点同一手法）。
    # [EN] ── Book breakdown (2026-10-07) ──
    # [EN] Demo mode must **actually perform the four stages**: coarse scan gives per-chapter lines, deep
    # [EN] breakdown gives notes, induction gives modules.
    # [EN] ⚠ Chapter names are **extracted from the prompt** (not hardcoded) — demo mode is running on
    # [EN] **the book the user passed in**,
    # [EN] so if chapter names can't be extracted, the per-chapter lines can't be mapped back (same
    # [EN] technique as `_crew_settings` extracting locations).
    "book_scan": _book_scan,
    "book_deep": _book_deep,
    "book_final": _book_final,
    # ── 剧组 Agents（2026-10-11）──
    #   ① `crew_agents_infer`：开卷那一步"让 AI 为这本书推断各职位的定制"。
    #      ⚠ 演示模式要**真的演得像**：从提示词里抓职位名，逐个给一句
    #      贴着题材的话 —— 返回空 dict 的话，演示模式下这一步永远是"没推断出
    #      东西"，而那看着和"功能没写"一模一样。
    #   ② `crew_custom`：作者自建职位的通用出工。
    # [EN] ── Crew Agents (2026-10-11) ──
    # [EN] ① `crew_agents_infer`: the "opening book" step — "have the AI infer the customization of each
    # [EN] role for this book".
    # [EN] ⚠ Demo mode must **actually look convincing**: extract role names from the prompt, give each one
    # [EN] a line
    # [EN] that sticks to the genre — if it returns an empty dict, this step in demo mode will always
    # [EN] "infer nothing",
    # [EN] and that looks exactly like "the feature was never written".
    # [EN] ② `crew_custom`: generic output for author-created roles.
    "crew_agents_infer": _crew_agents_infer,
    "crew_custom": _crew_custom,
    # ── 花费与优化（2026-11-01）──
    #   ⚠ 漏登记的后果：`mock_reply` 落到"占位 JSON"，`parse_advice` 解不出建议
    #     ⇒ 演示模式下两颗按钮都只得到"模型这次什么建议都没给出"，与"没实现"
    #     看不出区别。判据 `verify_mock` 的 A2 会当场抓到漏登记。
    # [EN] ── Cost & Tuning (2026-11-01) ──
    # [EN] ⚠ Consequence of not registering: `mock_reply` falls to the placeholder JSON, so
    # [EN] `parse_advice` yields no advice and both buttons look unimplemented in demo mode.
    "cost_advice": _cost_advice,
    "cost_deep": _cost_deep,
}


def mock_reply(messages: list[dict], purpose: str = "") -> str:
    h = _HANDLERS.get(purpose)
    if h:
        try:
            return h(messages)
        except Exception:
            pass
    text = "\n".join(m.get("content", "") for m in messages)
    if "JSON" in text or "json" in text:
        return _j({"结果": f"{DEMO_TAG} 演示输出", "说明": "MOCK_LLM 未登记该用途，返回占位 JSON"})
    return f"{DEMO_TAG} " + "".join(_pick(_NARRATIVE_POOL, 2))