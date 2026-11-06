# -*- coding: utf-8 -*-
"""设定优化对话：让作者与 AI 多轮打磨摄取出来的结构化设定。

摄取管线（`ingest.pipeline.run_ingest`）跑完后，设定只是「从文档里抠出来的原始形态」。
本模块提供三个能力，供 GUI 的「开卷 · 摄取」对话框把 AI 的优化过程**完整摊开**：

1. `settings_summary(settings)`     —— 把设定渲染成人能读的清单（对话框里给作者看）
2. `review_settings(...)`           —— 让 AI 先做一遍体检，给出诊断与改进建议
3. `apply_instruction(...)`         —— 作者用自然语言下指令，AI 返回改好的完整设定 + 变更说明

所有函数都走全局 `llm` 单例，因此每次请求/响应都会被 `llm` 的事件监听器捕获，
GUI 侧无需额外埋点即可展示「AI 的完整对话」。

English:
Settings optimization dialogue: lets the author iterate with the AI over multiple turns to
polish the structured settings extracted from ingestion.
After the ingestion pipeline (`ingest.pipeline.run_ingest`) runs, the settings are only in their
"raw form scraped out of the document".
This module provides three capabilities, so the GUI's "开卷 · 摄取" dialog can **lay the AI's
optimization process out in full**:
1. `settings_summary(settings)`     —— render the settings into a human-readable list (shown to the author in the dialog)
2. `review_settings(...)`           —— have the AI do a checkup first, giving a diagnosis and improvement suggestions
3. `apply_instruction(...)`         —— the author gives instructions in natural language, and the AI returns the modified complete settings + a change description
All functions go through the global `llm` singleton, so every request/response is captured by
`llm`'s event listeners,
and the GUI side needs no extra instrumentation to display "the AI's full conversation".
"""
from __future__ import annotations

import json
from typing import Any

from llm.replies import ask
from llm import models as MODELS
from ingest.extractor import validate_settings, empty_skeleton
from util.text import fill

_LOG = __import__("logging").getLogger("nws.ingest.optimize")

# 单次注入 LLM 的设定 JSON 上限（字），防止上下文爆炸
# [EN] Upper limit (in characters) of the settings JSON injected into the LLM in a single call, to
# [EN] prevent context explosion
_MAX_JSON = 16000
# 对话历史最多回传几轮（避免越聊越长）
# ★ 「按指令改设定」的输出上限：这一步 AI 要**把整份设定回抄一遍**，
#   设定越长越容易撞上限被截断（2026-10-06 提取那一步就是这么废掉的）。
#   4000 → 8000；真撞上了 `repair_json` 还会兜一道。
# [EN] Maximum number of dialogue history turns passed back (to avoid ever-growing conversations)
# [EN] ★ Upper limit for the output of "modify settings per instruction": in this step the AI has to
# [EN] **copy the entire settings back verbatim**,
# [EN] the longer the settings, the more likely it hits the limit and gets truncated (this is exactly
# [EN] how that extraction step got wrecked on 2026-10-06).
# [EN] 4000 → 8000; if it really hits the limit, `repair_json` still catches it as a fallback.
_APPLY_MAX_TOKENS = 8000

_MAX_HISTORY_TURNS = 8


# ══════════════════════════════════════════════════════════════
#  1. 可读摘要
# [EN] 1. Readable summary
# ══════════════════════════════════════════════════════════════
def settings_summary(settings: dict[str, Any], *, max_chars: int = 2600) -> str:
    """把结构化设定渲染成可读清单（给对话框展示，不是给 LLM 的）。
        English:
    Render the structured settings into a readable list (for dialog display, not for the LLM).
    """
    if not settings:
        return "（设定为空）"
    lines: list[str] = []

    chars = settings.get("人物") or []
    if chars:
        lines.append(f"人物 · {len(chars)} 位")
        for p in chars[:12]:
            name = p.get("姓名") or "未知"
            bits = [b for b in (p.get("身份"), p.get("性格"), p.get("简介")) if b]
            line = f"  · {name}"
            if bits:
                line += "｜" + "｜".join(str(b) for b in bits)
            secret = p.get("秘密")
            if secret:
                line += f"　（秘密：{secret}）"
            lines.append(line)

    if settings.get("世界观"):
        lines.append("世界观")
        lines.append("  " + str(settings["世界观"]).replace("\n", " "))

    places = settings.get("地点") or []
    if places:
        lines.append(f"地点 · {len(places)} 处")
        lines.append("  " + "、".join(str(l.get("名称") or "?") for l in places[:20]))

    rels = settings.get("关系") or []
    if rels:
        lines.append(f"关系 · {len(rels)} 条")
        for r in rels[:12]:
            lines.append(f"  · {r.get('甲','?')} — {r.get('乙','?')}：{r.get('关系','')}")

    hooks = settings.get("伏笔") or []
    if hooks:
        lines.append(f"伏笔 · {len(hooks)} 条")
        for h in hooks[:12]:
            lines.append(f"  · [{h.get('编号','?')}] {h.get('内容','')}")

    if settings.get("剧情参考线"):
        lines.append("剧情参考线")
        lines.append("  " + str(settings["剧情参考线"]).replace("\n", " "))

    text = "\n".join(lines) if lines else "（设定为空）"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…（摘要已截断）"
    return text


def _settings_json(settings: dict[str, Any]) -> str:
    """把设定序列化成给 LLM 的 JSON 文本（限长）。
        English:
    Serialize the settings into JSON text for the LLM (length-limited).
    """
    try:
        s = json.dumps(settings, ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        s = "{}"
    if len(s) > _MAX_JSON:
        s = s[:_MAX_JSON] + "\n…（已截断，请保留未展示的原有条目）"
    return s


# ══════════════════════════════════════════════════════════════
#  2. AI 体检
# [EN] 2. AI checkup
# ══════════════════════════════════════════════════════════════
# ★ 2026-10-06 的事故：这一步原来 `max_tokens=800`，而模型是**推理型** ——
#   思考内容也吃这份额度，800 个 token 全被思考吃掉，`content` 是**空字符串**，
#   `finish_reason=length`。界面上就是「AI 优化」对话框里 AI **一句话都没说**，
#   作者对着一个空气泡不知道该干什么（对话日志里「对话 · AI → 作者」后面是空的）。
# [EN] ★ The 2026-10-06 incident: this step originally had `max_tokens=800`, and the model is a
# [EN] **reasoning model** —
# [EN] the thinking content also eats this budget, so all 800 tokens were consumed by thinking and
# [EN] `content` was an **empty string**,
# [EN] `finish_reason=length`. In the UI, in the "AI optimization" dialog the AI **didn't say a single
# [EN] word**,
# [EN] and the author stared at an empty bubble not knowing what to do (in the conversation log, after [EN] "对话 · AI → 作者" there was nothing).
#
#   所以：预算按"思考 + 正文"一起给足（正文本身只要 300 字，但思考可能上千 token）；
#   并且**提示词里把格式与长度写死**，不给模型自由发挥的余地。
#   "提示词写得再清楚，也救不了预算不够" —— 两条都要做。
# [EN] So: give the budget generously for "thinking + body" together (the body itself only needs 300
# [EN] characters, but thinking can take over a thousand tokens);
# [EN] and **hard-code the format and length in the prompt**, leaving the model no room to improvise.
# [EN] "No matter how clearly the prompt is written, it can't save you from an insufficient budget" —
# [EN] both must be done.
_REVIEW_MAX_TOKENS = 2400
# 少于这个字数就不算"给出了体检"（几个残字对作者没用）→ 走重试
# [EN] Below this character count it doesn't count as "giving a checkup" (a few leftover characters are
# [EN] useless to the author) → go to retry
_REVIEW_MIN_CHARS = 40

_REVIEW_PROMPT = """你是一位资深小说编辑，正在帮作者把自动提取出来的项目设定做一遍体检。

项目名称：{name}
评档：{tier}
缺口：{missing}

目前的设定（JSON）：
---
{settings_json}
---

请**严格按下面这三段**输出，段首的方括号标题原样照抄，全文合计 300 字以内：

【最突出的问题】一句话点出来（不超过 60 字）。
【建议优先打磨】**编号**列 2~3 条，每条独占一行，写成「1. 改哪里 —— 怎么改」、
「2. …」；必须点到具体的人物名／伏笔编号／剧情线，不要泛泛而谈。
★ 编号是**要紧的**：作者接下来很可能直接说「处理 1 2」「先改第 2 条」
  —— 他指的就是这里这几个号，所以编号必须连续、从 1 开始、每条一行。
【等你回话】一句话邀请作者直接把改法打字告诉你（顺便告诉他可以按上面的编号说）。

硬性要求（违反其中任何一条，这次输出都算失败）：
- **第一行就是「【最突出的问题】」**，不要任何开场白（不要"好的""我来分析一下""这份设定整体…"）。
- **不要输出思考过程**，不要解释你正在做什么，不要说"让我看看"。
- **不要用 JSON**、不要罗列 JSON 的字段名（不要把"人物/世界观/地点"当小标题排一遍）、
  不要复述设定原文。
- 写完这三段就**立即停止**，不要再加总结、祝福或客套话。
- 就用作者的语言写（见文末的【输出语言】说明）。"""

# 彻底拿不到体检时的兜底。**必须非空** —— 空字符串在界面上就是一个看不见的气泡，
# 作者会以为"反正就是没反应"，而不是"这次体检没成功、但我可以直接下指令"。
# [EN] Fallback for when the checkup is completely unobtainable. **Must be non-empty** — an empty
# [EN] string is an invisible bubble in the UI,
# [EN] and the author will think "it just didn't respond anyway" rather than "this checkup didn't
# [EN] succeed, but I can just give instructions directly".
_REVIEW_FALLBACK = (
    "（这次 AI 体检没能给出结果 —— 可能是模型把额度用在思考上了，"
    "不影响你继续。）\n"
    "你可以直接打字告诉我要改什么，我照样照办，例如：\n"
    "· 把主角改个名字　· 加强主线的悬念　· 补两条伏笔　· 世界观再冷一点")


@MODELS.agent('ingest')
async def review_settings(settings: dict[str, Any], *, name: str = "",
                          tier: str = "", missing: list[str] | None = None) -> str:
    """让 AI 给设定做一遍体检，返回给作者看的诊断文本。

    ★ **返回值保证非空**（拿到的是空串就换个兜底文案）：
    界面上这是一个对话气泡，空串等于"AI 什么都没说"，是本次报修的原始现象。

    ★ 拿不到就**重试一次**（`llm/replies.ask` 负责：上限翻倍 + 明确要求"直接给正文"）。
    写在这里的手工 try/except 只兜"连调用都炸了"这一种。
    
        English:
    Have the AI do a checkup on the settings, returning diagnostic text for the author to read.
        ★ **The return value is guaranteed non-empty** (if an empty string comes back, swap in a fallback message):
        in the UI this is a dialogue bubble, and an empty string equals "the AI said nothing" — the original symptom of this bug report.
        ★ If it can't be obtained, **retry once** (`llm/replies.ask` handles it: double the limit + explicitly demand "give the body directly").
        The manual try/except written here only catches the "even the call blew up" case.
    """
    prompt = fill(_REVIEW_PROMPT,
                  name=name or "（未命名）",
                  tier=tier or "未知",
                  missing="、".join(missing or []) or "无",
                  settings_json=_settings_json(settings))
    rep = await ask("daily", [{"role": "user", "content": prompt}],
                    purpose="optimize_review", want="text",
                    max_tokens=_REVIEW_MAX_TOKENS, temperature=0.6,
                    min_chars=_REVIEW_MIN_CHARS)
    _REVIEW_NOTES[:] = list(rep.notes)      # 给界面/管线取用（见 take_review_notes）
    # [EN] For the UI/pipeline to consume (see take_review_notes)
    text = str(rep.value or "").strip()
    if rep.retried or not rep.ok:
        _LOG.info("AI 体检：重试=%s，成功=%s，说明=%s", rep.retried, rep.ok, rep.notes)
    return text or _REVIEW_FALLBACK


# 这一步攒下的提示（重试/抢救/彻底失败）。**用完取走**，与 `extractor.take_notes()`
# 同一个套路：由 GUI 折进摄取日志，作者才知道"这次体检其实重试过"。
# [EN] The notes accumulated in this step (retry/rescue/total failure). **Take them away when done**,
# [EN] same pattern as `extractor.take_notes()`
# [EN] the GUI folds them into the ingestion log, so the author knows "this checkup actually retried".
_REVIEW_NOTES: list[str] = []


def take_review_notes() -> list[str]:
    """取走并清空这次体检攒下的提示。
        English:
    Take away and clear the notes accumulated during this checkup.
    """
    out = list(_REVIEW_NOTES)
    _REVIEW_NOTES.clear()
    return out


# ══════════════════════════════════════════════════════════════
#  3. 按指令改设定
# [EN] 3. Modify settings per instruction
# ══════════════════════════════════════════════════════════════
_APPLY_PROMPT = """你是小说项目设定的修改助手。下面是当前完整的项目设定（JSON）。

当前设定：
---
{settings_json}
---

作者刚刚提出了一条修改意见，请严格按它修改设定，并保持其余内容不变：

「{instruction}」

★ **作者的指代要看上文，别只看这一句**（2026-10-11 用户报的）：
  他很可能**指着你上一条消息里的编号**说话，例如「处理 1 2」「先改前两个」
  「第 2 条和第 3 条一起」「后面那条不用了」。
  这些号指的是**上面那几条建议**（对话历史里你自己发的那条）。
  所以：先把编号对上号、再动手；**对不上号就问一句**（在「修改说明」里说明
  "你说的第 N 条我这边看不到，请再点一下是哪一条"），**不要闷头挑一条改**。

要求：
- 只改作者要求改的部分，其余条目一字不动地保留（尤其是人名、伏笔编号）。
- 如果作者的要求在现有信息下无法执行，就在「修改说明」里说明原因，并原样返回设定。
- 输出必须是 JSON 对象，顶层只有两个 key：
  {{"修改说明": "一句话说明你改了什么", "设定": {{完整设定，结构与输入一致}}}}
- 不要输出任何 JSON 以外的文字，**不要**用 ```json 代码块包起来。

★ 长度是这一步最容易失手的地方（输出要把整份设定回抄一遍，很容易撞上限被砍断）。
所以写的时候**宁短勿长**：
- 「修改说明」一句话，40 字以内；
- 每个字段都保持**和输入一样短或更短**，不要趁机扩写、不要加修饰、不要补充细节；
- 「概要/简介/身份/性格」这类一句话字段控制在 30 字以内，「秘密/目标/红线/说明」40 字以内；
- 「关系」不超过 8 条，「伏笔」不超过 8 条，「细节」不超过 8 条，其余数组条目数**不许增加**；
- 不确定要不要动的字段，就原样照抄。
- ⚠ **「必出日」那一栏一个字都不许改**（它是"第 N 章必出"的唯一程序保证，
  改了等于把"跨章埋/收"悄悄弄没了，而设定集里看不出任何变化）。

设定结构（务必保持）：
{{"人物": [{{"姓名","身份","简介","性格","口癖","秘密","目标","红线"}}],
 "世界观": "...", "地点": [{{"名称","说明"}}],
 "关系": [{{"甲","乙","关系","张力"}}],
 "伏笔": [{{"编号","内容","埋设","预计回收"}}], "剧情参考线": "...",
 "细节": [{{"名称","内容","场合","涉及","必出日"}}]}}"""


@MODELS.agent('ingest')
async def apply_instruction(settings: dict[str, Any], instruction: str,
                            history: list[dict] | None = None,
                            context: str = '') -> tuple[dict[str, Any], str]:
    """按作者的自然语言指令修订设定。

    返回 (新设定, AI 变更说明)。无法解析或失败时原样返回 settings + 说明。
    history：此前的对话轮次（[{"role","content"}]），用于让 AI 记住上下文。
    context：**这一场开头那段诊断/建议**（体检查出来的那几条）——
      作者接下来常说「处理 1 2」「前两个」，指的就是它里面的编号。
      ⚠ 为什么不干脆把它塞进 `history` 当一条 assistant 消息：
      那会让 messages 以 **assistant 打头**（多数 OpenAI 兼容服务对
      "第一条不是 user" 是**不容错**的），而这段文本本来就是"背景"，
      放在提示词里比放在角色序列里更稳、也更显式（判据只看得到一个字段）。

    ★ 「拿不到东西」的四种情形都由 `llm/replies.ask` 统一处理（重试 → 抢救），
    这里只负责把结果**接住并解释给作者听** —— 以前这一步在"截断"和"格式不对"
    两种失败上都只回一句"没能解析成设定"，作者看不出区别，也不知道该不该重试。
    
        English:
    Revise the settings per the author's natural-language instructions.
        Returns (new settings, AI change description). On parse failure or failure, returns settings unchanged + a description.
        history: previous dialogue turns ([{"role","content"}]), used to let the AI remember the context.
        context: **the diagnosis/suggestions from the start of this session** (the items found by the checkup) —
          when the author next says "handle 1 2" or "the first two", this is what they're referring to by number.
          ⚠ Why not just stuff it into `history` as an assistant message:
          that would make messages start with **assistant** (most OpenAI-compatible services are **not tolerant** of
          "the first message not being user"), and this text is inherently "background",
          so putting it in the prompt is more stable and more explicit than putting it in the role sequence (the criterion reads only one field).
        ★ The four cases of "can't get anything" are all handled uniformly by `llm/replies.ask` (retry → rescue),
        here we only **catch the result and explain it to the author** — previously this step, for both "truncation" and "bad format"
        failures, only replied with "failed to parse into settings", so the author couldn't tell the difference or know whether to retry.
    """
    instruction = (instruction or '').strip()
    if not instruction:
        return settings, "（空指令，未做修改）"

    messages: list[dict] = []
    for h in (history or [])[-_MAX_HISTORY_TURNS * 2:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)[:4000]})
    prompt = fill(_APPLY_PROMPT, settings_json=_settings_json(settings),
                  instruction=instruction)
    ctx = str(context or '').strip()
    if ctx:
        # 放在**最前面**（作者的话之前）：先给背景，再说要干什么。
        # [EN] Put it **at the very front** (before the author's words): give the background first, then say
        # [EN] what to do.
        prompt = (f'── 你上一条给作者的诊断与改进建议（他可能按里面的编号说话）──\n'
                  f'{ctx[:3000]}\n\n{prompt}')
    messages.append({"role": "user", "content": prompt})

    rep = await ask("daily", messages, purpose="optimize_apply", want=dict,
                    json_mode=True, max_tokens=_APPLY_MAX_TOKENS, temperature=0.3,
                    default=None)
    obj = rep.value
    if not isinstance(obj, dict) or not obj:
        # 连抢救都没拿到 -> 把"为什么"讲清楚（而不是笼统一句"没能解析"）
        # [EN] Even the rescue got nothing -> explain the "why" clearly (instead of a vague "failed to parse")
        why = "；".join(rep.notes) or "模型没有返回可解析的设定"
        _LOG.warning("AI 修改拿不到可用设定: %s", why)
        return settings, f"（这次的改动没能生效：{why}）\n" \
                         f"可以换个说法再试一次，或把要求拆小一点（比如一次只改一个人物）。"
    if rep.notes:
        _LOG.info("AI 修改：%s", rep.notes)

    note = str(obj.get("修改说明") or obj.get("说明") or "").strip()
    new_raw = obj.get("设定") if isinstance(obj.get("设定"), dict) else obj
    # 顶层不是设定结构（既没有人物也没有世界观）→ 视为无效
    # [EN] Top level is not a settings structure (neither characters nor worldview) → treat as invalid
    if not any(k in new_raw for k in ("人物", "世界观", "剧情参考线", "伏笔", "细节")):
        return settings, note or "（AI 未返回完整设定，未做修改）"

    new_settings = validate_settings(new_raw)
    if rep.salvaged:
        # **明说**：这是从半截输出里救回来的，末尾的设定可能没写上。
        # [EN] **State explicitly**: this was salvaged from a truncated output, and the settings at the end may
        # [EN] not have been written.
        note = (note + " ⚠ 这次的输出被长度上限截断，已按可闭合的前半段应用，"
                       "**末尾的设定可能没写进去**，请核对一下。").strip()
    return new_settings, note or "（已按你的意见更新设定）"


def empty() -> dict[str, Any]:
    """空设定骨架（供 GUI 兜底）。
        English:
    Empty settings skeleton (as a GUI fallback).
    """
    return empty_skeleton()
