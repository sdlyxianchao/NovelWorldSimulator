# -*- coding: utf-8 -*-
"""当日剧本 —— 导演**先定框架**，人物在框架内自由发挥。

用户 2026-10-07
--------------
「在一天开始之前 导演自己心里要根据前后背景以及小说整体设定 把当天要演的故事写好
  切记要贴合故事发展 然后在根据人物改写成剧本 然后分配给不同的角色 然后再开眼
  每个角色可以有自己适当的返回 但是总体框架不能够超过导演写的故事
  而且导演写故事和剧本之后要反复验算下是否跟整个故事是顺起来的
  每个人物可以有自己的一定自由度 但是不能够一直做不相干的 跟主线没有关系的事情
  尽量每件事情 每句话都跟主线有关」

在此之前跨天只做两件事：张力回落 + `_plan_day()` 让**每个角色各自**排今日计划。
问题就出在"各自"上 —— 十二个人各排各的、谁也不管谁，合起来不构成一个故事，
屏幕上于是变成"大家都在做自己的小事"，跟主线没关系（用户看到的正是这个）。

这一步补上缺的那一环，顺序**不能反**：

    ① 写当天故事（一段连贯的梗概：今天要推进什么）
         ↓ 依据 = 世界观 + 顶级规则 + 进度节点 + 前情提要 + 昨天小结
    ② 改写成剧本（分几拍，每拍谁做什么、为什么）
    ③ 分配给角色（每个角色的「今天该做的事」）
         ↓
    ④ 开演 —— 人物按剧本走，**允许自由发挥，但框架不超过导演写的**
         ↓
    ⑤ 验算（"这样顺不顺？有没有跟主线无关的？"）→ 不过关就带意见重写

★ 两个刻意的设计：

1. **验算用同一份材料自查，不另开一次生成**。让模型拿"当天故事 + 剧本 + 前情 + 进度"
   自问"顺不顺"，比让另一个模型盲审更省，也更贴这本小说 —— 它刚读完材料。
   `DAY_PLAN_FIX_ROUNDS` 轮还不过就**照用并记下问题**（不无限重写：
   写不出更好的就是写不出，硬重写的钱不如留给推演）。
2. **剧本给的是「目标与框架」，不是台词**。用户明确说"每个人物可以有自己的一定自由度"
   —— 把台词也写死就成提线木偶了，那正是本项目一直在避免的。

English:
The day's script —— the director **sets the framework first**, and the characters improvise
freely within the framework.
User 2026-10-07
--------------
"Before a day begins, the director must, in his own mind, based on the surrounding context and
the novel's overall setting, write the story to be performed that day
  be sure to fit the story's development, then rewrite it into a script based on the characters, then assign it to the different roles, then open your eyes
  each character may have their own appropriate responses, but the overall framework must not exceed the story the director wrote
  and after the director writes the story and script, he must repeatedly verify whether it flows with the whole story
  each character may have a certain degree of freedom, but must not keep doing unrelated things that have nothing to do with the main line
  try to make everything and every line relate to the main line"
Before this, across days only two things were done: tension decay + `_plan_day()` letting **each
character individually** plan today's schedule.
The problem lies exactly in "individually" —— twelve people each plan their own and no one minds
anyone else, and together they don't form a story,
so the screen turns into "everyone doing their own little things", unrelated to the main line
(this is exactly what the user saw).
This step fills in the missing link, and the order **cannot be reversed**:
    ① Write the day's story (a coherent synopsis: what to advance today)
         ↓ basis = worldview + top-level rules + progress nodes + previous recap + yesterday's summary
    ② Rewrite into a script (divided into beats, who does what in each beat, and why)
    ③ Assign to characters (each character's "what to do today")
         ↓
    ④ Perform —— characters follow the script, **free improvisation allowed, but the framework must not exceed what the director wrote**
         ↓
    ⑤ Verify ("does this flow? is anything unrelated to the main line?") → if it fails, rewrite with the comments
★ Two deliberate design choices:
1. **Verification self-checks using the same material, without opening another generation**. Having the model take "the day's story + script + recap + progress"
   and ask itself "does this flow" is cheaper than having another model blind-review it, and fits this novel better —— it just finished reading the material.
   If it still fails after `DAY_PLAN_FIX_ROUNDS` rounds, **use as-is and record the problems** (no infinite rewriting:
   if you can't write anything better, you can't; the money for forced rewriting is better spent on the simulation).
2. **The script gives "goals and framework", not lines**. The user explicitly said "each character may have a certain degree of freedom"
   —— writing the lines down too makes them marionettes, and that is exactly what this project has always avoided.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from config import CFG
from llm.replies import ask
from logger import get_logger

_LOG = get_logger('nws.director')

#: 落盘文件名（运行文件夹里）。**只写运行文件夹** —— 项目文件夹永远只读。
# [EN] : Output filename (inside the run folder). **Write only to the run folder** — the project folder
# [EN] is always read-only.
CACHE_NAME = '当日剧本.json'

#: 剧本里最多几拍（拍太多等于把一天写死，人物没有发挥空间）
# [EN] : Maximum number of beats in the script (too many beats means locking down the whole day,
# [EN] leaving no room for characters to act)
MAX_BEATS = 6
#: 最多给几个角色派活
# [EN] : Maximum number of characters to assign tasks to
MAX_ROLES = 12
#: 原样稿里最多留几拍（`DayScript.from_dict` 读回旧文件时也用它）——
#: 与 `MAX_BEATS` 同值：读回和写出用两个上限，会让"存的时候 6 拍、
#: 读回来只剩 4 拍"这种事悄无声息地发生。
# [EN] : Maximum number of beats kept in the raw draft (also used by `DayScript.from_dict` when reading
# [EN] back old files) —
# [EN] : Same value as `MAX_BEATS`: using two different limits for reading back and writing out will
# [EN] make "6 beats when saved,
# [EN] : only 4 beats when read back" happen silently.
#:
#: ⚠ 样章的长度区间**已经搬去配置**（`CREW_STORY_MIN` / `CREW_STORY_MAX`）：
#:   它是**小说作家的活**，而剧组的提示词在 `crew/agents.py`，两处各写一个
#:   数字早晚会漂（以前这里写死 120/600，用户想调只能改代码）。
#:   下面这两个常数留着只为兼容旧的导入点，**别再拿它们写新提示词**。
# [EN] : ⚠ The sample chapter length range **has been moved to config** (`CREW_STORY_MIN` /
# [EN] `CREW_STORY_MAX`):
# [EN] :   It is **the novelist's job**, while the crew's prompts are in `crew/agents.py`. Writing a
# [EN] : number in both places will eventually drift (previously 120/600 were hardcoded here, and users
# [EN] who wanted to adjust them had to change code).
# [EN] : The two constants below are kept only for compatibility with old import sites. **Do not use
# [EN] them to write new prompts.**
STORY_MIN_CHARS = 120
STORY_MAX_CHARS = 600


@dataclass
class DayScript:
    """一天的剧本。落盘走 `to_dict()` / `from_dict()`。
        English:
    One day's script. Persisted via `to_dict()` / `from_dict()`.
    """

    day: int = 1
    #: 当天要演的故事（一段连贯梗概，导演写给人看的那一版）
    # [EN] : The story to be performed today (a coherent synopsis, the version the director writes for
    # [EN] humans to read)
    story: str = ''
    #: 分拍：[{"拍": 1, "场": "临河茶肆", "发生": "...", "推进": "..."}]
    # [EN] : Beat breakdown: [{"beat": 1, "scene": "Riverside Teahouse", "what_happens": "...", "advance":
    # [EN] "..."}]
    beats: list[dict] = field(default_factory=list)
    #: **这一天的拍预算** `(下限, 上限)`，由当前那一站的「篇幅」档决定（2026-10-26）。
    #:
    #: ★ 为什么它要留在 `DayScript` 上：①验算与排练要看到"这一天本来就该多长"，
    #:   否则会拿"60 拍的标准"去要求一个只该演 1 拍（`带过`）的日子；
    #:   ②界面要显示"第 3 站 · 篇幅中 · 预算 15~25 拍 · 已演 12 拍"，
    #:   作者才知道戏演到哪儿了，而不是只看到一个不动的天数。
    # ⚠ 空元组 = 还没算（老夹具 / 单测直接构造），不是"0 拍"。
    # [EN] **This day's beat budget** `(min, max)`, decided by the current station's length tier.
    # [EN] Kept on `DayScript` so verification/rehearsal can see how long the day is *supposed* to be
    # [EN] (otherwise a 60-beat standard gets applied to a 1-beat `带过` day), and so the UI can show
    # [EN] "station 3 · medium · budget 15-25 · played 12". ⚠ An empty tuple means "not computed yet",
    # [EN] not "0 beats".
    budget: tuple[int, int] = ()
    #: 分派到人：{人名: [今天他该做的事, ...]}
    # [EN] : Assignments to people: {person name: [what he should do today, ...]}
    roles: dict[str, list[str]] = field(default_factory=dict)
    #: **开演前那一小段场景介绍**（剧作者写的，40~80 字）。
    #: 用户 2026-10-07：「前情提要和场景介绍不能够丢」—— 以前"场景介绍"只有
    #: `**场景** / **环境** / **在场**` 三行元数据，不是"一小段"。
    # [EN] : **The short scene introduction before the performance starts** (written by the screenwriter,
    # [EN] 40-80 characters).
    # [EN] : User 2026-10-07: "The recap and the scene introduction must not be dropped" — previously
    # [EN] "scene introduction" only had
    scene_intro: str = ''
    #: **今日剧情简介**（剧作者写的，30~60 字）："今天这一章要讲什么"。
    #: 用户 2026-10-07：「在前情提要后面，正式剧情之前，有一个今日剧情简介」。
    #: ⚠ 它和 `scene_intro` 是两件事，别并成一个字段：
    #:   场景介绍讲"这是什么地方"，剧情简介讲"今天要演什么" ——
    #:   合并之后只能二选一，而用户要的是**两条都在**。
    # [EN] : **Today's plot summary** (written by the screenwriter, 30-60 characters): "what this chapter
    # [EN] is about today".
    # [EN] : User 2026-10-07: "After the recap and before the formal plot, there is a today's plot
    # [EN] summary".
    # [EN] : ⚠ It and `scene_intro` are two different things. Do not merge them into one field:
    # [EN] : The scene introduction tells "what kind of place this is", the plot summary tells "what is to
    # [EN] be performed today" —
    # [EN] :   after merging you can only choose one, but the user wants **both present**.
    day_brief: str = ''
    #: 验算结论与它挑出来的毛病（照实说，别藏）
    # [EN] : The verification conclusion and the problems it picked out (report truthfully, do not hide)
    verdict: str = ''
    problems: list[str] = field(default_factory=list)
    rounds: int = 0
    #: **排练挑出来的毛病**（2026-10-07）：`[{拍,谁,问题,怎么改}, …]`。
    #: ⚠ 与 `problems`（导演验算的意见，是**句子**）分开：那个看的是"故事顺不顺"，
    #:   这个看的是"**上了场走不走得下去**"—— 两件事、两种材料。
    # [EN] : ⚠ Keep separate from `problems` (the director's verification opinions, which are
    # [EN] **sentences**): that one looks at "whether the story flows smoothly",
    # [EN] : this one looks at "**whether it can keep going once on stage**" — two things, two kinds of
    # [EN] material.
    rehearsal: list[dict] = field(default_factory=list)
    #: 排练的结论一句话（"整体成不成"）
    # [EN] : The rehearsal conclusion in one sentence ("whether it works overall")
    rehearsal_verdict: str = ''
    rounds_rehearsed: int = 0
    #: `ai` / `fallback`（后者=一次都没拿到，界面/日志要照实说）
    # [EN] : `ai` / `fallback` (the latter = never obtained even once; the UI/log must report truthfully)
    source: str = 'fallback'
    #: **分镜（镜头清单）**：分镜师把分拍拆成的一镜一镜
    #:   `[{镜, 拍, 景别, 画面, 台词, 镜头运动}, …]`（P2，2026-10-15）。
    #: ⚠ 与 `beats` 分开：beats 是"这一场发生什么"，shots 是"这一场怎么拍"——
    #:   两件事、两种材料（演员读 shots 知道"这一镜我站在哪、镜头怎么动"）。
    # [EN] : **Storyboard (shot list)**: the storyboard artist breaks each beat into one shot at a time
    # [EN] : `[{shot, beat, size, frame, line, move}, ...]` (P2, 2026-10-15).
    # [EN] ⚠ Keep separate from `beats`: beats are "what happens this scene", shots are "how this scene is shot" —
    # [EN] two things, two kinds of material (the actor reads shots to know "where I stand this shot, how the camera moves").
    shots: list[dict] = field(default_factory=list)
    #: **视觉参考图清单**：visref 为出场人物/关键场景生的一致性参考图
    #:   `[{种类, 名, 图}, …]`（P3，2026-10-15）。落盘后下游生图（对话插图/
    #:   分镜脚本导出）可把它当统一参照，不必每次重新瞎画。
    #: ⚠ 与 `shots` 分开：shots 是"这一场怎么拍"，refs 是"这一场长什么样"
    #:   —— 两件事、两种材料（前者给演员，后者给生图）。
    #: [EN] : **Visual reference list**: consistent reference art for characters/scenes (P3).
    #: [EN] `{kind, name, image}`. Persisted so downstream image generation can reuse it.
    #: [EN] Keep separate from `shots`: shots are "how to shoot", refs are "what it looks like".
    refs: list[dict] = field(default_factory=list)

    # ── 给提示词用的三块文本 ──
    # [EN] ── Three blocks of text used for prompts ──
    def frame_text(self, limit: int = 700) -> str:
        """**框架约束**：写进人物决策提示词，让他知道"今天这一场在演什么"。

        ⚠ 这是"框架"不是"剧本原文" —— 只给当天故事 + 他分到的那几件事，
          不把别人的活儿也塞给他（他会去抢别人的戏）。
        
                English:
        **Framework constraint**: written into the character decision prompt, so he knows "what this
        scene today is playing out".
                ⚠ This is the "framework" not the "script text" —— only give the day's story + the few things assigned to him,
                  do not stuff other people's work onto him too (he will steal others' scenes).
        """
        s = (self.story or '').strip()
        if not s:
            return ''
        return s[:limit]

    def roles_text(self) -> str:
        """**派活表**：写进导演派活/人物计划的提示词。
                English:
        **Assignment sheet**: written into the director's assignment / character plan prompt.
        """
        rows = [f'- {n}：{"；".join(v)}' for n, v in (self.roles or {}).items() if v]
        return '\n'.join(rows)

    def shots_text(self, limit: int = 1400) -> str:
        """**分镜清单**：写进人物决策提示词，让他知道"这一镜我站在哪、镜头怎么动"。

        ⚠ 这是"拍摄说明书"不是"剧本原文" —— 只给每镜的景别 / 画面 / 台词 / 镜头运动，
          不把别人的活儿也塞给他。
                English:
        **Shot list**: written into the character decision prompt, so he knows "where I stand this shot,
        how the camera moves".
                ⚠ This is the "shooting instruction" not the "script text" —— only give each shot's size /
        frame / line / camera move, do not stuff others' work onto him.
        """
        if not self.shots:
            return ''
        lines: list[str] = []
        for s in self.shots[:24]:
            if not isinstance(s, dict):
                continue
            head = f"{s.get('镜') or '?'}.（拍{s.get('拍') or '?'}）"
            if s.get('景别'):
                head += f" 景别：{s['景别']}"
            lines.append(head)
            if s.get('画面'):
                lines.append(f"   画面：{s['画面']}")
            if s.get('台词'):
                lines.append(f"   台词：{s['台词']}")
            if s.get('镜头运动'):
                lines.append(f"   镜头运动：{s['镜头运动']}")
        return '\n'.join(lines)[:limit]

    def flat_beats(self) -> list[int]:
        """**没有价值转变的那几拍**（`推进` 空着的拍号）。

        为什么要有这个（2026-10-07 审计补的麦基/贝克那一条）：
        「一场一转变」是本项目工艺库里明写的手艺（`剧作与舞台.yaml`），
        剧作者的提示词里也有"每拍推进了主线的什么" —— 但**没有人验收**：
        模型给出 5 拍、其中 2 拍没写 `推进`，也不会有人吭一声。

        按剧作法，**没有转变的那一拍可以删**（不是为了好看，是它不推进任何东西）。
        这里**只报不删**：删哪一拍是作者的判断 —— 与场记"只报不改"同源。

        ⚠ 这是**规则判据**（看字段空不空），不是"AI 判断这拍好不好"。
          真正的质量判断在 `_verify` 那条自审里（第 ⑤ 条）。
        
                English:
        **Those beats without a value shift** (beat numbers where `推进` is empty).
                Why this is needed (the McKee/Baker item added in the 2026-10-07 audit):
                "one shift per scene" is a craft explicitly written in this project's craft library (`剧作与舞台.yaml`),
                and the screenwriter's prompt also has "what did each beat advance in the main line" —— but **no one verifies it**:
                the model gives 5 beats, 2 of which don't write `推进`, and no one says a word.
                Per dramaturgy, **a beat without a shift can be deleted** (not for looks, but because it advances nothing).
                Here **only report, do not delete**: which beat to delete is the author's judgment —— same lineage as the script supervisor's "report only, don't change".
                ⚠ This is a **rule-based criterion** (checking whether fields are empty), not "AI judging whether this take is good".
                  The real quality judgment is in the self-review at `_verify` (item ⑤).
        """
        out: list[int] = []
        for i, b in enumerate(self.beats or [], 1):
            if not isinstance(b, dict):
                continue
            if not str(b.get('推进') or '').strip():
                try:
                    out.append(int(b.get('拍') or i))
                except (TypeError, ValueError):
                    out.append(i)
        return out

    def to_dict(self) -> dict:
        return {'day': self.day, 'story': self.story, 'beats': list(self.beats),
                'scene_intro': self.scene_intro,
                'day_brief': self.day_brief,
                'roles': {k: list(v) for k, v in (self.roles or {}).items()},
                'verdict': self.verdict, 'problems': list(self.problems),
                'rehearsal': [dict(x) for x in (self.rehearsal or [])],
                'rehearsal_verdict': self.rehearsal_verdict,
                'rounds_rehearsed': self.rounds_rehearsed,
                'rounds': self.rounds, 'source': self.source,
                'shots': [dict(x) for x in (self.shots or [])],
                'refs': [dict(x) for x in (self.refs or [])]}

    @classmethod
    def from_dict(cls, data) -> 'DayScript | None':
        """宽容读回（坏字段丢单个，不整体失败）。
                English:
        Lenient read-back (drop individual bad fields, do not fail as a whole).
        """
        if not isinstance(data, dict):
            return None
        ds = cls()
        try:
            ds.day = int(data.get('day') or 0)
        except (TypeError, ValueError):
            ds.day = 0
        ds.story = str(data.get('story') or '')
        ds.scene_intro = str(data.get('scene_intro') or '')
        ds.day_brief = str(data.get('day_brief') or '')
        beats = data.get('beats')
        if isinstance(beats, (list, tuple)):
            ds.beats = [b for b in beats if isinstance(b, dict)][:MAX_BEATS]
        roles = data.get('roles')
        if isinstance(roles, dict):
            for k, v in list(roles.items())[:MAX_ROLES]:
                tasks = [str(x).strip() for x in (v or []) if str(x).strip()]
                if str(k).strip() and tasks:
                    ds.roles[str(k).strip()] = tasks[:4]
        ds.verdict = str(data.get('verdict') or '')
        probs = data.get('problems')
        if isinstance(probs, (list, tuple)):
            ds.problems = [str(x) for x in probs if str(x).strip()][:6]
        reh = data.get('rehearsal')
        if isinstance(reh, (list, tuple)):
            ds.rehearsal = [dict(x) for x in reh if isinstance(x, dict)][:6]
        ds.rehearsal_verdict = str(data.get('rehearsal_verdict') or '')
        ds.rounds_rehearsed = int(data.get('rounds_rehearsed') or 0) if str(
            data.get('rounds_rehearsed') or '').isdigit() else 0
        ds.rounds = int(data.get('rounds') or 0) if str(
            data.get('rounds') or '').isdigit() else 0
        ds.source = str(data.get('source') or 'fallback')
        shots = data.get('shots')
        if isinstance(shots, (list, tuple)):
            ds.shots = [dict(x) for x in shots if isinstance(x, dict)][:48]
        refs = data.get('refs')
        if isinstance(refs, (list, tuple)):
            ds.refs = [dict(x) for x in refs if isinstance(x, dict)][:24]
        return ds if (ds.story or ds.beats or ds.roles) else None


# ══════════════════════════════════════════════════════════════════════
#  提示词
# [EN] Prompt
# ══════════════════════════════════════════════════════════════════════
# ★★ 2026-10-07：「写故事」与「改写剧本」这两步的提示词**搬去剧组了** ——
#   见 `crew/agents.py` 的 `Novelist` 与 `Screenwriter`。
# [EN] ★★ 2026-10-07: The prompts for the two steps "write story" and "rewrite script" **have been
# [EN] moved to the crew** —
# [EN] see `Novelist` and `Screenwriter` in `crew/agents.py`.
#
#   为什么搬：那两步是**剧组里两个职位的活**（小说作家 / 剧作者），
#   而这位剧作者要读的是**剧作理论**（`craft/playbooks/剧作与舞台.yaml`
#   那一架，老舍《茶馆》的场面调度那一路），小说作家读的是**叙事章法**。
#   以前两块提示词都写在这个文件里、都自称"你是这本小说的导演"，
#   两个人读同一份材料 —— 那就不是两个职位，是一个职位换了两次名。
# [EN] Why moved: those two steps are **the jobs of two positions in the crew** (novelist /
# [EN] screenwriter),
# [EN] and this screenwriter needs to read **dramatic theory** (the `craft/playbooks/剧作与舞台.yaml`
# [EN] shelf, the stage-blocking line of Lao She's 《茶馆》), while the novelist reads **narrative
# [EN] method**.
# [EN] Previously both blocks of prompts were written in this file and both claimed "you are the
# [EN] director of this novel",
# [EN] so two people read the same material — then it is not two positions, it is one position renamed
# [EN] twice.
#
#   现在这个文件只剩**导演自己的活**（验算 + 落盘 + 给下游用的 DayScript）。
#   ⚠ 别把提示词再搬回来：搬回来就意味着 "谁读哪本工艺" 又散成两处。
# [EN] Now this file only has **the director's own job** (verification + output to disk + the DayScript
# [EN] for downstream use).
# [EN] ⚠ Do not move the prompts back: moving them back means "who reads which craft book" is scattered
# [EN] in two places again.
_VERIFY_PROMPT = """你是这本小说的导演，这是**你自己**刚写好的当日剧本。请**审自己一遍**。

{craft}

── 前情提要 ──
{recap}

── 进度节点（主线）──
{nodes}

── 当天要演的故事 ──
{story}

── 改写的剧本 ──
{script}

逐条自问。★★ **先分清"硬伤"和"建议"**（2026-10-18，这一条最要紧）：

· **硬伤**（只有这些才判不通过）：跟前情**真的矛盾**、让人**不在场却出现**、
  **时空说不通**（隔着墙一步过去、时辰对不上）、**踩世界规则/时代**、
  **人物完全 OOC**（不像设定里那个人）。
· **建议**（**不判不通过**，只记下来）：你会**换一种写法**、某个动作更快/更慢、
  某句可以更省、某条线可以更早挑明。
  ⚠ "如果是我，我会这么写"**不是硬伤**。这套推演的用途是给作者找灵感，
    **允许它走一条跟你不一样的路**；只要这条路站得住，就判通过。
  ⚠ 也不要因为"原文没这么写"判不通过 —— 那不在这套标准里。

逐条自问：
① **顺不顺**：这个故事接得上前面的前情吗？有没有跟已发生的事**矛盾**？
② **推不推进主线**：今天动的是哪个节点？说得出吗？
③ **有没有跑题**：剧本里有没有跟主线无关的事、或者只是在凑日常？
④ **人合不合理**：有没有让不在场的人出现？有没有 OOC（不像设定里那个人）？
⑤ **一场一转变**（麦基／贝克）：**每一拍**各自变了什么？
   哪一拍说不出"从怎样变成了怎样"（从瞒住到露馅、从平安到被盯上），
   就在 `问题` 里点名那一拍 —— 那几拍按剧作法可以删。
⑥ **每场戏交代完整吗**（2026-10-11 加；作者点名"很多场景反复切换却没有
   任何人物出场、动作、情节"）：每一拍是不是都写清了 `主题`（这场戏在讲什么）、
   `出场`（有谁）、`要点`（要落到哪些动作与话头）、`道具`、`情绪`？
   ★ 尤其看 `出场` 里的人**真的有事做吗** —— 只挂个名字不出戏的，
   点名那一拍（那正是"无意义的场景切换"的源头）。

只输出 JSON，不要围栏、不要解释：
{{"通过": true, "硬伤": ["…"], "建议": ["…"], "修改意见": "…"}}
`通过` 只有在 `硬伤` 非空时才给 false。`建议` 可以很多，但**不影响通过**。
`修改意见` 要写成**具体到能照着改**的一句话（比如
"第 3 拍换成让账房把昨夜的账本摔在桌上，因为那才是账目线索的起点"），
不要写"再顺一顺"这种空话；`通过` 为 true 时它可以空着。"""


#: 喂给导演的章纲长度上限（当前站那几章够用了，别把整本塞进来）。
# [EN] Cap on the chapter-plan text handed to the director (this station's chapters are enough).
_CHAPTER_PLAN_VIEW = 900


def _nodes_text(world, db, limit: int = 6) -> str:
    """进度节点（主线）。取不到就照实说"没有"，别编。

    ⚠ 2026-10-07 修：以前读 `db.list_progress_nodes()` —— **DB 上没有这个方法**
      （它只有 `get_summaries` / `recent_events` 那几个）。`hasattr` 一直是 False，
      于是"进度节点"永远只剩 `world.current_node` 那一条。改读
      `world.progress_nodes`（那才是内存里那份真表）。
    
        English:
    Progress node (mainline). If it can't be fetched, say so honestly: "none". Don't make it up.
        ⚠ 2026-10-07 fix: previously read `db.list_progress_nodes()` -- **the DB has no such method**
          (it only has `get_summaries` / `recent_events` and those few). `hasattr` was always False,
          so "progress node" was forever left with only the single entry `world.current_node`. Changed to read
          `world.progress_nodes` (that's the real table in memory).
    """
    node = str(getattr(world, 'current_node', '') or '').strip()
    rows = []
    try:
        raw = getattr(world, 'progress_nodes', None) or []
        rows = [r for r in raw if isinstance(r, dict)]
    except Exception:                                            # noqa: BLE001
        rows = []
    if not rows and hasattr(db, 'list_progress_nodes'):
        try:
            rows = list(db.list_progress_nodes() or [])
        except Exception:                                        # noqa: BLE001
            rows = []
    out: list[str] = []
    if node:
        out.append(f'-（当前）{node}')
    # ★★★ 2026-10-14（用户：「推演感觉故事线推进的特别快 …… 第一天就想把谜底解开」）：
    #   **只给「当前节点」，不再列出后面那些节点的名字**。
    #   为什么：节点名本身**就是剧透** —— 这个项目的表里写着
    #   `懵懂入局 / 迷雾渐起 / 真相浮现 / 破局抉择`，后两个名字等于把
    #   "会揭真相、会做抉择"直接告诉作家，而这段文本是**排在硬要求前面**的
    #   （`── 进度节点（主线）──`），作家写这一天时满脑子是"要走完这条路"。
    #   ⇒ 现在只给当前节点**名字 + 它的完成判据**（判据是这一步的目标，该知道），
    #     并明说"后面的路还没走到" —— **不点名**，模型就无从提前跳。
    # [EN] ★★★ 2026-10-14 (user: "the simulation feels way too fast ... it wants to crack the mystery on
    # [EN] day one"): **hand over only the *current* node, and stop listing the later node names.**
    # [EN] Why: the names themselves **are spoilers** -- this project's table reads
    # [EN] `懵懂入局 / 迷雾渐起 / 真相浮现 / 破局抉择`; the last two literally announce "the truth will
    # [EN] be revealed, a choice will be made", and this text sits **above the hard requirements** in the
    # [EN] prompt (`── 进度节点（主线）──`), so the writer plans the day around "finish this road".
    # [EN] => Now only the current node's **name + its completion criterion** (the criterion is this
    # [EN] step's goal and is fair to know), plus an explicit "the road past here has not been reached"
    # [EN] -- **without naming anything**, the model has nothing to jump to.
    _cur = next((r for r in rows
                 if str(r.get('id') or '') == node
                 or str(r.get('名称') or '') == node), None)
    if _cur is None and rows:
        _cur = rows[0]
    _cname = str((_cur or {}).get('名称') or '').strip()
    _cdone = str((_cur or {}).get('完成判据') or '').strip()
    if _cname:
        out.append(f'-（当前节点）{_cname}')
        if _cdone:
            out.append(f'  这一步要做到：{_cdone}')
        # ★★★ 2026-10-27：**这一站内部的台阶**（高潮 / 情节线）—— 作者写了、
        #   以前却一个字都进不了推演的那一层。`完成判据` 只说了**终点线**，
        #   于是"这一站要演 5 章"时导演每天只能拿概要现编 ⇒ 天数够了、进度没有。
        #   ⚠ 措辞上明说它是**参考不是清单**：推演按判据走，不按条目打勾
        #   （把推演变成逐条执行就与"推演引擎"的定位冲突了）。
        # [EN] ★★★ 2026-10-27: the station's **inner steps** (climax / beats) -- the layer the
        # [EN] author wrote that never reached the run. `criteria` states only the **finish line**, so
        # [EN] a five-chapter station left the director improvising from the summary => days spent,
        # [EN] no progress. ⚠ Worded as **reference, not checklist**: the run follows criteria, it does
        # [EN] not tick off items (item-by-item execution would clash with the "simulation engine"
        # [EN] purpose).
        _cclimax = str((_cur or {}).get('高潮') or '').strip()
        _cbeats = [str(x).strip() for x in ((_cur or {}).get('情节线') or [])
                   if str(x or '').strip()]
        if _cbeats:
            out.append('  这一站的台阶（**参考**，不必按顺序打勾）：'
                       + '；'.join(_cbeats))
        if _cclimax:
            out.append(f'  这一站的高潮：{_cclimax}')
            out.append('  ⚠ **高潮是最后才到的那一下** —— 今天还没走到就别写它，'
                       '先把上面的台阶走过去；写完了这一站就没什么可演的了。')
        # ★ 2026-10-27：**当前站的章纲**（章一级施工图，只给这一站的几章）。
        #   ⚠ 措辞必须是"参考"：推演按判据走，不按章打勾 —— 否则导演会把
        #   "一章一天"当成硬排期，判据还没成立也硬往下走。
        # [EN] ★ 2026-10-27: the **current station's chapter plan** (chapter-level blueprint, only
        # [EN] this station's chapters). ⚠ It must read as "reference": the run follows criteria, it
        # [EN] does not tick off chapters -- otherwise the director treats "one chapter a day" as a
        # [EN] hard schedule and pushes on even when the criterion is not met.
        _cplan = str((_cur or {}).get('章纲') or '').strip()
        if _cplan:
            out.append('  这一站的章纲（**参考**，不是排期 —— 判据没成立就还在这一站）：')
            out.append(_cplan[:_CHAPTER_PLAN_VIEW])
        out.append('  ⚠ **只走这一步**：后面的路还没走到，名字也不必猜 —— '
                   '不许提前揭开后面的真相、不许让人物说出他这时还不知道的事。')
    elif node:
        out.append(f'-（当前节点）{node}')
        out.append('  ⚠ **只走这一步**：后面的路还没走到，不许提前揭开。')
    if not out:
        # 没有进度表也要能跑 —— 但**明说没有**，让模型别硬编一个节点出来
        # [EN] It must be able to run even without a progress table — but **explicitly say there is none**, so
        # [EN] the model does not force out a node.
        return '（这本书还没设定进度节点 —— 那就按前情往下推最自然的一步，别急着揭底）'
    return '\n'.join(out)


def recap_text(db, limit: int = None, world=None) -> str:
    """**公开名字**：前情提要（日档开头也要用它，见 `store/runfolder.flush_daily_script`）。

    以前它只喂给模型，正文里一个字都没有 —— 用户 2026-10-07 明确说
    「前情提要和场景介绍不能够丢」。一份实现两处用（本项目老规矩）。

    `world` 传进来时，**故事刚开始**（还没有任何摘要与事件）也能给出一小段
    —— 见 `_opening_context`。用户 2026-10-07：「每次推演开始一开始应该有
    一小段前情提要 你这个也没有」：第一天/刚续上时屏幕上确实什么都没有。

    ★ 粒度（2026-10-07 用户第二次提）：
      **要小**（`RECAP_MAX_CHARS`，默认 240 字）· **只讲最近几天**
      （`RECAP_DAYS`，默认往回 3 天）· **按天平分额度**（不是整体截尾，
      否则"最近三天"只剩最后一天的后半句）。
      只有**第一章**才用背景故事，而且取的是【剧情参考线】的「起」
      —— 是**故事**不是**设定**（见 `_opening_context`）。
    
        English:
    **Public name**: recap (the daily script opening also uses it, see
    `store/runfolder.flush_daily_script`).
        Previously it was only fed to the model, not a single word in the body text -- user on 2026-10-07 explicitly said
        "the recap and scene introduction must not be dropped". One implementation, two uses (this project's old rule).
        When `world` is passed in, even at the **very start of the story** (no summaries or events yet) it can still produce a short
        paragraph -- see `_opening_context`. User on 2026-10-07: "every simulation should have
        a short recap at the start, and you don't even have this": on the first day / just resumed, the screen indeed shows nothing.
        ★ Granularity (2026-10-07, user's second mention):
          **keep it small** (`RECAP_MAX_CHARS`, default 240 chars) · **only cover the last few days**
          (`RECAP_DAYS`, default 3 days back) · **split the budget evenly per day** (not truncating the whole thing,
          otherwise "the last three days" would only keep the second half of the last day's sentence).
          Only the **first chapter** uses the backstory, and it takes the "setup" of 【Story Reference Line】
          -- it's **story**, not **setting** (see `_opening_context`).
    """
    return _recap_text(db, limit, world)


def _section(text: str, name: str) -> str:
    """抽出设定集里 `【name】` 那一段（到下一个 `【` 标题为止）。没有就空串。
        English:
    Extract the `【name】` section from the setting collection (until the next `【` heading). Empty
    string if none.
    """
    i = text.find(f'【{name}】')
    if i < 0:
        return ''
    body = text[i + len(name) + 2:]
    j = body.find('\n【')
    return ' '.join((body[:j] if j >= 0 else body).split()).strip()


def _clip(text: str, limit: int) -> str:
    """按字数收一下（**保证结果 ≤ limit**，含结尾那个"…"），收尾不留半截标点。

    ⚠ 第一版是 `text[:limit] + '…'` —— 加省略号**没算进额度**，
    于是"总共 240 字"实际出来 245（3 天各超 1 字 + 2 个分隔符）。
    这种"差几个字"在判据里就是硬红，而且看着莫名其妙。
    
        English:
    Trim by character count (**guarantee the result ≤ limit**, including the trailing "…"), and
    don't leave a half-cut punctuation at the end.
        ⚠ The first version was `text[:limit] + '…'` -- the ellipsis **wasn't counted against the budget**,
        so "240 chars total" actually came out to 245 (3 days each over by 1 char + 2 separators).
        This kind of "a few chars off" is a hard red in the criteria, and it looks inexplicable.
    """
    text = ' '.join(str(text or '').split())
    if len(text) <= limit:
        return text
    return text[:max(1, limit - 1)].rstrip('，。；、 ') + '…'


def opening_context(worldview_text: str, limit: int = 200) -> str:
    """**公开名字**：第一章的「前情」＝背景故事（只吃**那段世界观文本**）。

    ★ 为什么要跟 `_opening_context(world, …)` 分家（2026-10-11）：
      「起笔」对话框要在**还没装配 world** 的时候算出"这一轮开头会念哪句
      前情提要"，给作者看。它手上只有项目设定集里那段文本，没有 world 对象。
      分出一个只吃文本的入口，两边就是**同一份实现** ——
      用户点名过这条："请确保这里的前情提要和后续运行窗口对话显示的时候给的
      前情提要一样"。各写一份那是迟早要漂的。
    
        English:
    **Public name**: the first chapter's "recap" = backstory (consumes only **that worldview
    text**).
        ★ Why it's split from `_opening_context(world, …)` (2026-10-11):
          the "start writing" dialog needs to compute "which recap sentence will be read at the start of this round" **before world is assembled**, to show the author. It only has the text from the project setting collection, no world object.
          Factoring out an entry that only consumes text makes both sides **the same implementation** --
          the user specifically called out this: "please ensure the recap here and the recap
          given when the subsequent run window dialogue is displayed are the same". Writing two separate copies is bound to drift eventually.
    """
    text = str(worldview_text or '').strip()
    if not text:
        return ''

    # ⓪ **接续导入的故事**：前情提要优先（2026-10-28）。
    #   用户实测的症状：「导出的故事起点跟前情提要对不上，故事情节没从之前的故事开始」。
    #   根因：第一章前情走的是①【剧情参考线】的「起」段 —— 那是"大纲从哪里**起头**"，
    #   而接续推演要的是"导入的故事**停在哪里**"。摄取把对齐出的前情+末段写进
    #   `前情提要.md`，经 `load_settings.recap` → `_worldview_text` 变成【前情提要】段；
    #   有它就**优先取它**，没有才走原来的①②（老项目零变化）。
    # [EN] ⓪ **Continuing an imported story**: the recap takes priority (2026-10-28). The user's
    # [EN] symptom: "the exported story's start point mismatched the recap -- the plot did not
    # [EN] continue from the previous story." Root cause: day-1 recap used the outline's "setup"
    # [EN] clause (where the outline **starts**) instead of where the imported story **stopped**.
    # [EN] Ingest writes the aligned recap + tail into 前情提要.md -> load_settings.recap ->
    # [EN] _worldview_text composes the 【前情提要】 section; prefer it when present, otherwise
    # [EN] fall through to ①② (old projects unchanged).
    prev = _section(text, '前情提要')
    if prev:
        return _clip(prev, limit)

    # ① 背景故事：【剧情参考线】的「起」段（到"承"之前）
    # [EN] ① Backstory: the "setup" section of 【Story Reference Line】 (before "development")
    arc = _section(text, '剧情参考线')
    if arc:
        cut = len(arc)
        for mark in ('承', '转', '合'):
            k = arc.find(mark)
            if k > 0:
                cut = min(cut, k)
        head = arc[:cut].strip(' 　，。；、·—-.')
        head = head.lstrip('起：: 　')
        if len(head) >= 12:               # 太短说明这条"起"没写内容 → 走退路
        # [EN] Too short means this "起" has no content written → take the fallback
            return _clip(head, limit)

    # ② 退路：世界观（**只给一半额度**：它是设定，不是故事）
    # [EN] ② Fallback: worldbuilding (**only give half the budget**: it is setting, not story)
    body = _section(text, '世界观')
    if body:
        return _clip(body, max(60, limit // 2))
    return _clip(arc, limit) if arc else ''


def _opening_context(world, limit: int = 200) -> str:
    """**第一章的「前情」＝背景故事**（还没有任何跨天摘要时用）。

    用户 2026-10-07：
    「前情提要内容要小 是针对已经发生的最近今天或者一段时间的故事的总结
      除非第一章 否则不要用很大的背景故事来作为前情提要
      （第一张可以用背景故事，但尽量不要用背景设定来代替背景故事）」

    ★ 所以**第一顺位是【剧情参考线】里的「起」那一段** —— 那是"故事从哪儿
      起头"，是**背景故事**（发生过什么），不是**背景设定**（这世道是怎样）。
      而且**只取到"承"之前就停**：再往后就是大纲了，拿来当前情等于剧透。

      ⚠ 这一条**推翻了本函数上一版的判断**（当时写的是"【剧情参考线】刻意不用"）。
        那个判断对**第三天以后**是对的（那时该看摘要，不该回到背景），
        但对**第一章**过头了 —— 用户要的恰恰是"开头那点背景故事"。
        现在两者分开：第一章用「起」，其余用最近几天的摘要。

    ★ 第二顺位（退路）才是【世界观】，而且**只给一半额度** ——
      用户明确说"尽量不要用背景设定来代替背景故事"，那就让它短、别喧宾夺主。
    三样都没有 → 空串（**不编**，本项目对"假装有内容"零容忍）。

    ⚠ 实现已收进 `opening_context(文本)`（同一份口径）—— 这里只负责从 world 取文本。
    
        English:
        用户 2026-10-07：
    """
    return opening_context(str(getattr(world, 'worldview_text', '') or ''), limit)


def _recap_text(db, limit: int = None, world=None) -> str:
    """（实现）见公开入口 `recap_text()` 的说明。
        English:
    (Implementation) see the description of the public entry `recap_text()`.
    """
    try:
        from config import CFG as _C
        limit = int(limit or _C.i('RECAP_MAX_CHARS'))
        days = max(1, int(_C.i('RECAP_DAYS')))
    except Exception:                                            # noqa: BLE001
        limit, days = int(limit or 240), 3

    # ① 最近 N 天的跨天摘要（**按天平分额度**，不是整体截尾）
    # [EN] ① The cross-day summaries of the most recent N days (**split the budget evenly by day**, not
    # [EN] truncate the whole thing)
    texts: list[str] = []
    try:
        rows = db.get_summaries(days) if hasattr(db, 'get_summaries') else []
        for r in (rows or []):
            t = str((r or {}).get('text') or '').strip()
            if t:
                texts.append(t)
    except Exception:                                            # noqa: BLE001
        texts = []
    if texts:
        # 额度要**扣掉分隔符**再平分，否则总数会超（`_clip` 也保证 ≤ 额度）
        # [EN] The budget must **subtract the separators** before being split evenly, otherwise the total will
        # [EN] exceed it (`_clip` also guarantees ≤ budget)
        per = max(40, (limit - (len(texts) - 1)) // len(texts))
        return '　'.join(_clip(t, per) for t in texts)[:limit]

    # ② 没有摘要 → 退到最近的记忆条目（有内容但不是"总结"，所以更要短）
    # [EN] ② No summary → fall back to the most recent memory entry (it has content but is not a "summary",
    # [EN] so it should be even shorter)
    try:
        if hasattr(db, 'recent_events'):
            # 位置参数：真 DB 的签名是 `recent_events(n=20, game_day=0)`
            # [EN] Positional arguments: the real DB signature is `recent_events(n=20, game_day=0)`
            rows = db.recent_events(max(4, days * 2))
        elif hasattr(db, 'list_events'):
            rows = db.list_events(limit=max(4, days * 2))
        else:
            rows = []
    except Exception:                                            # noqa: BLE001
        rows = []
    lines = [f'- {_clip(_event_line(r), 40)}' for r in (rows or []) if _event_line(r)]
    if lines:
        return _clip(' '.join(lines), limit)

    # ③ **只有第一章**才端出背景故事。
    #   用户 2026-10-07：「除非第一章 否则不要用很大的背景故事来作为前情提要」
    #   —— 所以这里真的判天数：第 2 天以后要是连摘要都没有（比如摘要那一步失败），
    #   就**空着**，不拿背景故事顶替（"没有"比"用错的东西充数"更诚实）。
    # [EN] ③ **Only the first chapter** brings out the backstory.
    # [EN] User 2026-10-07: "Unless it is the first chapter, do not use a very large backstory as the
    # [EN] recap"
    # [EN] — so here it really checks the day count: after day 2, if there is not even a summary (e.g. the
    # [EN] summary step failed),
    # [EN] then **leave it empty**; do not substitute the backstory ("nothing" is more honest than "padding
    # [EN] with the wrong thing").
    day = int(getattr(world, 'game_day', 0) or 0) if world is not None else 0
    if world is not None and day <= 1:
        return _opening_context(world, limit)
    return ''


def _event_line(row) -> str:
    """一条事件记录取正文（不同表/假对象用的字段名不一样，都认）。
        English:
    Take the body text of an event record (different tables/fake objects use different field names,
    all are accepted).
    """
    d = row or {}
    if not isinstance(d, dict):
        return ''
    return str(d.get('content') or d.get('description') or '').strip()


# ══════════════════════════════════════════════════════════════════════
#  主流程
# [EN] Main flow
# ══════════════════════════════════════════════════════════════════════
# ★★ 2026-10-07：这两步**改由剧组的专业人士来做**。
# [EN] ★★ 2026-10-07: These two steps **are now done by crew professionals**.
#
# 为什么（用户原话）：「让作者和剧作者参考经典小说和剧作以及影视剧理论
# 和老舍茶馆等剧本理论 去写剧本」。
# [EN] Why (the user's own words): "let the author and screenwriter refer to classic novels and drama
# [EN] and film/TV theory
# [EN] and script theory such as Lao She's Teahouse to write the script".
#
# 以前这两个提示词是**自带身份的一块文本** —— 它让同一个模型"先当作家、
# 再当剧作者"，但两边的活儿读的是同一份简报，写剧本的那位**根本看不到
# 剧作理论**（`craft/` 里那几本工艺书只有导演挑事时才读）。
# [EN] Previously these two prompts were **a single block of text carrying its own identity** — it made
# [EN] the same model "first act as author,
# [EN] then act as screenwriter", but both jobs read the same brief, and the one writing the script
# [EN] **could not see
# [EN] dramatic theory at all** (the craft books in `craft/` were only read when the director was
# [EN] picking a fight).
#
# 现在：`crew/agents.py` 的 `Novelist`（读古典章法/网文方法论）与
# `Screenwriter`（读剧作与舞台/编剧正典）各自成篇，这里是**调度**。
# 提示词与工艺全在 `crew/agents.py` 一处 —— 免得两边各写一份、各漏一样。
# [EN] Now: `Novelist` in `crew/agents.py` (reads classical method / web-fiction methodology) and
# [EN] `Screenwriter` (reads drama and stage / screenwriting canon) are each complete in themselves;
# [EN] this is **scheduling**.
# [EN] Prompts and craft are all in one place in `crew/agents.py` — to avoid writing one copy on each
# [EN] side and each missing something.
async def _write_story(world, db, *, people: list[str], yesterday: str = '',
                       studio=None) -> str:
    """第一步：**小说作家**写当天这一章的原著样章。
        English:
    Step one: the **novelist** writes the original sample chapter for that day.
    """
    from crew import agents as CREW
    from crew.agents import SetCtx
    # ★ `book` / `novel_dir`（2026-10-09 加）：外部创作服务要**按书**建项目，
    #   并把映射缓存落到这本书自己的目录里。`world` 上既没有书名也没有目录，
    #   只有 `studio.runfolder` 知道 —— 所以在这儿取，别去 `world` 上猜属性名。
    # [EN] ★ `book` / `novel_dir` (added 2026-10-09): the external creation service needs to **create
    # [EN] projects per book**,
    # [EN] and write the mapping cache into this book's own directory. `world` has neither the book title
    # [EN] nor the directory;
    # [EN] only `studio.runfolder` knows — so get it here, do not go guessing attribute names on `world`.
    _rf = getattr(studio, 'runfolder', None) if studio is not None else None
    _pdir = getattr(_rf, 'project_dir', None)
    ctx = SetCtx(world=world, db=db,
                 day=int(getattr(world, 'game_day', 0)
                         or getattr(world.clock, 'day', 1) or 1),
                 people=list(people or []),
                 # 书名：目录名就是书名（`Project.create_new` 建的就是 `<项目根>/<书名>/`）。
                 # 拿不到就是空串 —— 桥接层会退化成"按全局表找项目"，功能不丢。
                 # [EN] Book title: the directory name is the book title (what `Project.create_new` creates is `<project
                 # [EN] root>/<book title>/`).
                 # [EN] If it cannot be obtained, it is an empty string — the bridge layer degrades to "find project by
                 # [EN] global table", and functionality is not lost.
                 book=str(getattr(_pdir, 'name', '') or ''),
                 novel_dir=_pdir)
    # ★ 本轮篇幅目标（`ROUND_DAILY_WORDS`，0 = 不限）—— 由 `sim/setup` 灌到 world 上。
    # [EN] ★ This round's length target (`ROUND_DAILY_WORDS`, 0 = unlimited) — injected into world by
    # [EN] `sim/setup`.
    _words = max(0, int(getattr(world, 'daily_words', 0) or 0))
    if studio is not None:
        note = await studio.call('novelist', ctx, words=_words,
                                 nodes=_nodes_text(world, db), yesterday=yesterday)
        return note.body if note.ok else ''
    # 没有制片厂（单测直接调这一步）时**就地起一个**，走同一份实现。
    # [EN] When there is no studio (unit tests call this step directly), **start one on the spot**, using
    # [EN] the same implementation.
    note = await CREW.Novelist().run(
        ctx, words=_words, nodes=_nodes_text(world, db), yesterday=yesterday)
    return note.body if note.ok else ''


def current_node_of(world, db=None) -> dict | None:
    """取**当前正在推进的进度节点**（那一站）。取不到返回 `None`。

    ⚠ 只认 `world.progress_nodes` 里 `状态 == '进行中'` 的那一条；一条都没有时
      退回 `world.current_node`（按 id 或名字匹配）。**不拿"第一个未开始的"凑** ——
      那会让"还没到那一站"的日子按下一站的篇幅开演。
    [EN] Fetch the **progress node currently being advanced**. Only the entry whose status is
    [EN] `进行中` counts; failing that, match `world.current_node` by id or name. It never falls back
    [EN] to "the first not-started node" -- that would play a day at the *next* station's length.
    """
    rows = []
    try:
        rows = [r for r in (getattr(world, 'progress_nodes', None) or [])
                if isinstance(r, dict)]
    except Exception:                                            # noqa: BLE001
        rows = []
    for r in rows:
        if str(r.get('状态') or '') == '进行中':
            return r
    cur = str(getattr(world, 'current_node', '') or '').strip()
    if cur:
        for r in rows:
            if cur in (str(r.get('id') or ''), str(r.get('名称') or '')):
                return r
    return None


def beat_budget_for(world, db=None) -> tuple[int, int, str]:
    """**这一天该分几拍**（`(下限, 上限, 为什么)`）。

    ★★★ 2026-10-26（用户：「小说时间不是匀速流逝的……这个模拟最大的问题就是这里」）：
    以前拍数是模型自己给的，**没有任何上限** —— `ROUND_DAILY_WORDS` 是软目标且默认 0（不限）
    ⇒ 实测一天演了 **133 幕 / 21.3 万字**，一天就把两天的故事演完，而下一站又从头铺一遍。

    现在：拍预算**挂在当前那一站的「篇幅」档上**（`ingest.progress.BEAT_BUDGET`），
    所以"详"的那一站能演 40~60 拍、"带过"的那一站只有 1 拍 —— 详略由**情节**决定，
    不再由"一天有多少分钟"决定。

    ⚠ 取不到节点时给一个**保守的默认**（`中` 的区间），绝不返回"不限"：
      返回不限就等于回到旧行为，而旧行为正是这个 bug。
    [EN] ★★★ 2026-10-26 (user: "novel time does not flow uniformly ... this is the biggest
    [EN] problem"): the beat count used to be whatever the model produced, with **no cap** --
    [EN] `ROUND_DAILY_WORDS` is a soft target defaulting to 0 (unlimited) -- so one day ran **133
    [EN] acts / 213k characters**. Now the budget hangs on the current station's **length tier**, so a
    [EN] `详` station gets 40-60 beats and a `带过` station gets one. ⚠ When no node is available it
    [EN] returns a conservative default, **never "unlimited"** -- unlimited is the old behaviour,
    [EN] which is the bug.
    """
    try:
        from ingest.progress import (BEAT_BUDGET, DEFAULT_WEIGHT, WEIGHTS,
                                     beat_budget)
    except Exception:                                            # noqa: BLE001
        return 15, 25, '取不到篇幅表，按「中」处理'

    node = current_node_of(world, db)
    if node is None:
        # ⚠ 这里**不能直接 return**：`每章字数` 那道封顶也得走到，
        #   否则"没有正在推进的节点"那几天会绕过字数目标（判据 C 组测的就是这条）。
        # [EN] ⚠ Must not return early here: the words-per-chapter cap below has to apply too,
        # [EN] otherwise days without a running node silently ignore the word target.
        w = DEFAULT_WEIGHT
        lo, hi = BEAT_BUDGET[w]
        why = f'没有正在推进的节点，按默认「{DEFAULT_WEIGHT}」档'
        return _cap_by_words(world, lo, hi, why, w)

    w = str(node.get('篇幅') or '').strip()
    if w not in WEIGHTS:
        # 节点上没写篇幅（老项目 / 装配时没补）⇒ 现推一个，别崩
        # [EN] No length tier on the node (old project, or not filled at assembly) -> infer one.
        try:
            from ingest.progress import ProgressNode, infer_weight
            w = infer_weight(ProgressNode(id=str(node.get('id') or ''),
                                          name=str(node.get('名称') or ''),
                                          summary=str(node.get('概要') or ''),
                                          criteria=''))
        except Exception:                                        # noqa: BLE001
            w = DEFAULT_WEIGHT
    lo, hi = beat_budget({'篇幅': w})
    why = f'当前站「{str(node.get("名称") or node.get("id") or "?")}」篇幅={w}'
    return _cap_by_words(world, lo, hi, why, w)


#: 篇幅档 → 换算出来的拍数再乘多少（**详略不许被字数目标抹平**）。
#:
#: ⚠ 为什么需要它：只按"每章字数 ÷ 550"封顶的话，「详 / 中 / 略」算出来是同一个数
#:   （2,500 字都 → 5 拍）—— 于是作者在节点上写的 `篇幅` **静默失效**，
#:   而那正是本项目反复栽的坑（"字段写了、两条路都能跑、只是永远不生效"）。
#:   现在：`详` 一天写厚一点（×1.4 ≈ 3,500 字）、`略` 薄一点（×0.6 ≈ 1,500 字）、
#:   `带过` 仍然一句话（1 拍）。**"这一站占几章"由 `章数` 管，不靠这里撑厚度。**
# [EN] Length tier -> multiplier applied to the converted beat count (**the tier must not be flattened
# [EN] by the word target**). ⚠ Without it, 详/中/略 all convert to the same number (2,500 words -> 5
# [EN] beats) and the node's `篇幅` silently stops mattering -- the recurring trap in this project.
# [EN] `详` writes thicker per day (x1.4), `略` thinner (x0.6), `带过` stays a single beat.
_WORDS_TIER_FACTOR: dict[str, float] = {
    '详': 1.4,
    '中': 1.0,
    '略': 0.6,
    '带过': 0.0,
}


def _cap_by_words(world, lo: int, hi: int, why: str,
                  weight: str = '') -> tuple[int, int, str]:
    """**每章字数再压一刀**（`篇幅` 是上限，字数才是目标）。

    由来：用户问"一天到底给多少字"。实测一拍 ≈ 550 字（见 `progress.CHARS_PER_BEAT`），
    而旧表是按"一拍 ≈ 76 字"那个年代定的 ⇒ 中档 15~25 拍实际写出 8,000~13,000 字（五章的体量），
    设定集里写的"每章 2,500 字"完全对不上 —— 一天就把一站写完了。

    ⇒ 设定集（或「起笔」里的「每天字数」）写了每章字数时，用它换算拍数：
      `2,500 ÷ 550 ≈ 4.5 → 5 拍`（`详` 再 ×1.4、`略` ×0.6，见 `_WORDS_TIER_FACTOR`）。
    ⚠ 没写（0）就**保持原表** —— 绝不猜一个字数，那是"没配置却按配置走"。
    ⚠ 只压不抬：算出来比原表上限还多时，**按原表**（作者的"详"不该被一个偏大的字数目标推翻）。
    [EN] **Cap the beats by the book's words-per-chapter** (`篇幅` is an upper bound; the word count is
    [EN] the target). Measured yield is ~550 chars/beat, while the old table assumed ~76, so a `中` day
    [EN] of 15-25 beats wrote 8k-13k characters (five chapters) and finished a station in one day.
    [EN] ⚠ With no target (0) the table stays untouched; never invent a number. ⚠ Cap only, never raise.
    """
    _words = 0
    try:
        _words = int(getattr(world, 'daily_words', 0) or 0)
    except Exception:                                            # noqa: BLE001
        _words = 0
    if _words <= 0:
        return lo, hi, why
    try:
        from ingest.progress import beats_for_words
        _base_cap = beats_for_words(_words)
    except Exception:                                            # noqa: BLE001
        _base_cap = 0
    if not _base_cap:
        return lo, hi, why
    _f = _WORDS_TIER_FACTOR.get(str(weight or ''), 1.0)
    _cap = 1 if _f <= 0 else max(1, int(round(_base_cap * _f)))
    if _cap >= hi:
        return lo, hi, why
    _orig_hi = hi
    hi = _cap
    lo = min(lo, hi)
    _tier = '' if abs(_f - 1.0) < 1e-6 else f'（篇幅{weight} ×{_f:g}）'
    return lo, hi, why + (f'；每章 {_words} 字 ÷ 实测 550 字/拍{_tier}'
                          f' ⇒ 封顶 {_cap} 拍（原表上限 {_orig_hi}）')


def _beat_budget_cached(world, db=None) -> tuple[int, int, str]:
    """`beat_budget_for` 的**一天只算一次**版本。

    ⚠ 为什么要缓存：它在重写循环里被调用（验算不过会重写 1~2 轮），
      而 `beat_budget_for` 每次都要遍历节点表 + 可能推一次篇幅。
      重写不该改变预算 —— 改的是**怎么拍**，不是**拍几拍**。
    [EN] `beat_budget_for` computed **once per day**. It sits inside the rewrite loop (verification may
    [EN] trigger 1-2 rewrites), and the budget must not drift between rewrites: what changes is *how*
    [EN] the day is shot, not *how many* beats it gets.
    """
    key = (id(world), int(getattr(world, 'game_day', 0) or 0),
           str(getattr(world, 'current_node', '') or ''))
    cache = getattr(world, '_beat_budget_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            world._beat_budget_cache = cache
        except Exception:                                        # noqa: BLE001
            return beat_budget_for(world, db)
    if cache.get('key') != key:
        cache.clear()
        cache['key'] = key
        cache['val'] = beat_budget_for(world, db)
    return cache['val']


def span_minutes_for(world, db=None) -> int:
    """**这一站吃掉多少故事分钟**（`跨度` 档）。取不到节点就给 `当日`。

    ⚠ 一定返回**正数**：0 会让 `sim/loop._beat_minutes_now` 判成"时间用完了"，
      于是一整天一秒钟都不走 —— 而那是"查不到跨度"的症状，不是"这一站没内容"。
    [EN] How many story minutes this station eats (from the span tier); `当日` when unavailable.
    [EN] ⚠ Always positive: 0 would make `_beat_minutes_now` read "time is used up" and freeze the
    [EN] clock for a whole day -- that is a failed lookup, not "this station has no content".
    """
    try:
        from ingest.progress import DEFAULT_SPAN, span_minutes
    except Exception:                                            # noqa: BLE001
        return 12 * 60
    node = current_node_of(world, db)
    span = DEFAULT_SPAN
    if isinstance(node, dict):
        span = str(node.get('跨度') or '').strip() or DEFAULT_SPAN
    return max(1, int(span_minutes({'跨度': span})))


def beat_minutes_for(world, db=None) -> tuple[int, str]:
    """**这一拍推多少故事分钟**（`(分钟, 为什么)`）。取不到节点就给 `当日 + 中`。

    ★★★ 2026-10-26（用户选 A：**日界 = 拍预算用完**）：

    以前一拍推多久是恒定的（`BEAT_SECONDS` 60 故事秒 = 1 分钟），于是
    "一场审讯"和"三个月赶路"占用一样长的故事时间 —— 那是秒表，不是小说。
    现在一拍推多久 = **这一站的故事时长 ÷ 这一站的拍数**（`ingest.progress.beat_minutes`）：
      · `一场 + 详`  ⇒ 120 分钟 / 50 拍 ≈ 2.4 分钟/拍（像真在演）
      · `当日 + 中`  ⇒ 720 分钟 / 20 拍 = 36 分钟/拍
      · `数月 + 带过` ⇒ 129600 分钟 / 1 拍 = 90 天/拍（一句话带过）

    ⚠ 这是"故事时间"那一侧唯一的入口；`TIME_RATIO` 从此只控**观看速度**
      （拍与拍之间等多少真实秒），一个字节都不再影响故事时间。
    ⚠ 结果**按天缓存**：一天里拍数、跨度不该中途变化（重写/续拍都不该改时间流速）。
    [EN] **How many story minutes this beat advances** (plus the reason). Falls back to `当日 + 中`
    [EN] when no station is available. ★★★ 2026-10-26 (the user chose A: the day ends when the
    [EN] beat budget runs out): the per-beat duration used to be a constant 60 story seconds, so
    [EN] "one interrogation" and "three months on the road" occupied the same story time -- a
    [EN] stopwatch. Now it is the station's story duration divided by its beat count. ⚠ This is the
    [EN] only entry point on the **story time** side; `TIME_RATIO` from now on controls only **how
    [EN] fast you watch** and no longer touches story time at all. ⚠ Cached per day.
    """
    try:
        from ingest.progress import (DEFAULT_SPAN, DEFAULT_WEIGHT, beat_minutes,
                                     beat_budget)
    except Exception:                                            # noqa: BLE001
        return 12 * 60 // 20, '取不到跨度表，按「当日 + 中」处理'

    node = current_node_of(world, db)
    span, weight = DEFAULT_SPAN, DEFAULT_WEIGHT
    if isinstance(node, dict):
        span = str(node.get('跨度') or '').strip() or DEFAULT_SPAN
        weight = str(node.get('篇幅') or '').strip() or DEFAULT_WEIGHT
    lo, hi = beat_budget({'篇幅': weight})
    mins = beat_minutes({'跨度': span}, weight, hi)
    who = str((node or {}).get('名称') or (node or {}).get('id') or '（无节点）')
    return mins, f'当前站「{who}」跨度={span} 篇幅={weight} → 一拍 {mins} 故事分钟'


def _beat_minutes_cached(world, db=None) -> int:
    """`beat_minutes_for` 的**一天只算一次**版本（与 `_beat_budget_cached` 同一套缓存键）。

    ⚠ 缓存键必须与拍预算那个**完全一致**：两个值描述的是同一件事（这一站怎么演），
      键不一致就会出现"预算按新站、时间流速按旧站"——那种错查不出来（数字都合理）。
    [EN] Per-day cache for `beat_minutes_for`, using the **same key** as the beat budget: the two
    [EN] describe the same thing (how this station is played), and a mismatched key would give
    [EN] "budget from the new station, time rate from the old one" -- an untraceable error, since
    [EN] both numbers look plausible.
    """
    key = (id(world), int(getattr(world, 'game_day', 0) or 0),
           str(getattr(world, 'current_node', '') or ''))
    cache = getattr(world, '_beat_minutes_cache', None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            world._beat_minutes_cache = cache
        except Exception:                                        # noqa: BLE001
            return beat_minutes_for(world, db)[0]
    if cache.get('key') != key:
        cache.clear()
        cache['key'] = key
        cache['val'] = beat_minutes_for(world, db)
    return int(cache['val'][0])


def _clamp_beats(beats: list[dict], lo: int, hi: int
                 ) -> tuple[list[dict], str]:
    """把分拍**压到预算区间**，返回 `(拍, 说明)`。

    ★ 这是**硬闸**，不是建议：模型给的拍数必须落进 `[lo, hi]`。
      按项目的既有实测，提示词里的"请写 N 拍"只能挡住 40~74% —— 关键约束必须在解析层做。
    ★ 超了：**截断到 hi**，但**先保住"推进判据"那一拍**（见下）；
      不够：**不补**（补出来的拍是空的，等于花钱买废句），只记一笔日志。
    [EN] A **hard gate**, not advice: the model's beat count is clamped into `[lo, hi]`. Measured
    [EN] experience says a prompt-level "write N beats" only holds 40-74%, so the constraint has to
    [EN] live in the parsing layer. Over budget: truncate to `hi` but **keep the criterion-advancing
    [EN] beat first**; under budget: do **not** pad (padding invents empty beats).
    """
    n = len(beats)
    if lo <= n <= hi:
        return beats, ''
    if n > hi:
        # ⚠ 不能简单砍尾巴：那一站**推进判据**的那一拍常常在最后。
        #   先找出"推进"字样最强的一拍保下来，再按原顺序取前 hi-1 拍。
        # [EN] ⚠ Can't just cut the tail: the beat that advances the criterion is often last. Keep the
        # [EN] most "advancing" beat, then take the first hi-1 in original order.
        keep_idx = None
        for i, b in enumerate(beats):
            blob = str(b.get('做什么') or b.get('目标') or b.get('说明') or b)
            if any(k in blob for k in ('推进', '完成判据', '达成', '揭晓', '决定')):
                keep_idx = i
        head = [b for i, b in enumerate(beats) if i != keep_idx][:max(0, hi - (1 if keep_idx is not None else 0))]
        out = head + ([beats[keep_idx]] if keep_idx is not None else [])
        return out, f'拍数 {n} 超出上限 {hi} → 截到 {len(out)}（已保住推进那一拍）'
    return beats, f'拍数 {n} 少于下限 {lo}（不补空拍，只记一笔）'


def _beats_from(note) -> tuple[list[dict], dict[str, list[str]]]:
    """把「剧作者」交上来的活拆成 `(拍, 角色任务)`（校验过的那一份）。
        English:
    Split the work submitted by the "playwright" into `(beat, character task)` (the validated copy).
    """
    d = (note.data or {}) if note is not None else {}
    beats = [b for b in (d.get('拍') or []) if isinstance(b, dict)]
    roles = {str(k): [str(x) for x in (v or [])]
             for k, v in (d.get('角色任务') or {}).items()
             if str(k).strip() and (v or [])}
    return beats, roles


def _intro_from(note) -> str:
    """剧作者写的**那一小段场景介绍**（没有就是空串 —— 不拿元数据凑数）。
        English:
    **That short scene introduction** written by the playwright (empty string if none -- don't pad
    it out with metadata).
    """
    d = (note.data or {}) if note is not None else {}
    return ' '.join(str(d.get('场景介绍') or '').split())[:200]


def _brief_from(note) -> str:
    """剧作者写的**今日剧情简介**（用户 2026-10-07 要的"正式剧情之前那一段"）。

    和 `_intro_from` 一样是**空就是空**：拿不到就不上屏（不编、不拿前情凑数）——
    "今日剧情简介"写成前情的复述，比没有更糟。
    
        English:
        "Today's plot summary" written as a recap of prior events is worse than nothing.
    """
    d = (note.data or {}) if note is not None else {}
    return ' '.join(str(d.get('剧情简介') or '').split())[:200]


async def _write_script(world, story: str, *, people: list[str],
                        fix: str = '', studio=None, brief: str = ''
                        ) -> tuple[tuple[list[dict], dict[str, list[str]]],
                                   str, str]:
    """第二步：**剧作者**把样章改写成能拍的剧本。

    `brief` = **上游递来的材料**（名册里 `feeds='screenwriter'` 的那几位给的）——
    眼下是资料员的考据结论。这条链以前只写在名册上（"资料员把考据交给剧作者"），
    而程序里两者各跑各的；现在它是真的：上游的结论进提示词，剧作者得照着写。
    
        English:
    Step 2: the **screenwriter** rewrites the sample chapter into a shootable script.
        `brief` = **material handed down from upstream** (from those listed in the roster with `feeds='screenwriter'`) ——
        currently the researcher's findings. This chain used to exist only on the roster ("the researcher hands the findings to the screenwriter"),
        but in the program the two ran independently; now it's real: upstream conclusions go into the prompt, and the screenwriter must write accordingly.
    """
    from crew.agents import SetCtx
    ctx = SetCtx(world=world, db=None if studio is None else studio.db,
                 day=int(getattr(world, 'game_day', 0)
                         or getattr(world.clock, 'day', 1) or 1),
                 people=list(people or []), story=story)
    if studio is not None:
        note = await studio.call('screenwriter', ctx, story=story, fix=fix,
                                 brief=brief)
        return _beats_from(note), _intro_from(note), _brief_from(note)
    from crew import agents as CREW
    note = await CREW.Screenwriter().run(ctx, story=story, fix=fix, brief=brief)
    return _beats_from(note), _intro_from(note), _brief_from(note)


def beats_text(beats: list[dict]) -> str:
    """把分拍表摊成**给模型读的一段文本**（验算与排练共用）。

    ★ 2026-10-11：以前只有 `N. [场] 发生（推进：…）` —— 新加的
      `主题 / 出场 / 要点 / 道具 / 情绪` 那些字段**一个字都没露出来**，
      于是 `_VERIFY_PROMPT` 新加的「⑥ 每场戏交代完整吗」这条**无从判断**
      （看都看不到，怎么可能指出哪样没写）。
      一份实现两处用（本项目的规矩）：`_verify` 和任何要看分拍表的地方都调它。

        English:
    Lay the beat sheet out as **a block of text for a model to read** (shared by verification and
    rehearsal).
        ★ 2026-10-11: previously only `N. [place] what happens (advance: ...)` -- the newly added
          `主题 / 出场 / 要点 / 道具 / 情绪` fields **never showed up at all**, so the newly added
          item 6 in `_VERIFY_PROMPT` ("is every scene fully set up?") **had nothing to judge**
          (how could it point out what was missing when it could not even see it?).
          One implementation used in two places (the house rule): `_verify` and anything else that
          needs to see the beat sheet calls this.
    """
    lines: list[str] = []
    for b in (beats or []):
        if not isinstance(b, dict):
            continue
        head = f"{b.get('拍') or '?'}. [{b.get('场') or '—'}]"
        if b.get('主题'):
            head += f" 主题：{b['主题']}"
        lines.append(head)
        if b.get('出场'):
            lines.append(f"   出场：{'、'.join(str(x) for x in b['出场'])}")
        if b.get('发生'):
            lines.append(f"   发生：{b['发生']}")
        if b.get('要点'):
            lines.append(f"   要点：{'｜'.join(str(x) for x in b['要点'])}")
        if b.get('道具'):
            lines.append(f"   道具：{'、'.join(str(x) for x in b['道具'])}")
        if b.get('情绪'):
            lines.append(f"   情绪：{b['情绪']}")
        if b.get('推进'):
            lines.append(f"   推进：{b['推进']}")
        if b.get('目标'):
            lines.append(f"   目标：{b['目标']}")
        if b.get('难题'):
            lines.append(f"   难题：{b['难题']}")
    return '\n'.join(lines)


async def _verify(world, db, story: str, beats: list[dict],
                  roles: dict[str, list[str]]) -> tuple[bool, list[str], str]:
    script_txt = beats_text(beats) or '（没有分拍）'
    if roles:
        script_txt += '\n分派：' + '；'.join(
            f'{n}={"/".join(v)}' for n, v in roles.items())
    # ★★ **导演这一行的手艺**（2026-10-07 第六轮）——
    #   导演是三人小组里唯一没有货架、也不走 `craft_block` 的那一个，
    #   而它正是"审剧本、判断这一场成不成立"的人（用户说的"用于优化故事"）。
    #   于是把 `craft_block('director', …)` 接在这里：它同时带来
    #   ① 结构手艺（场景=价值转变 / 期望鸿沟）② 人那一半（反差/旁观者拆解）
    #   ③ 这本书的项目档 ④ **拆书库里匹配上的同类书写法**（完整版）。
    # [EN] ★★ **The craft of this director line** (2026-10-07, sixth round) —
    # [EN] The director is the only one of the three-person group who has no shelf and does not go through
    # [EN] `craft_block`,
    # [EN] and it is precisely the one who "reviews the script and judges whether this scene holds up"
    # [EN] (what the user called "used to optimize the story").
    # [EN] So hook `craft_block('director', …)` in here: it brings both
    # [EN] ① structural craft (scene = value shift / expectation gap) ② the human half (contrast /
    # [EN] bystander deconstruction)
    # [EN] ③ this book's project file ④ **the matching same-type book's writing method found in the
    # [EN] book-deconstruction library** (full version).
    #
    #   ⚠ 位置：放在"你自己刚写好的当日剧本"**之前**、五条自问**之前** ——
    #     读手艺要在下判断之前，不是事后补一句。
    # [EN] ⚠ Position: place it **before** "the day's script you just wrote yourself", and **before** the
    # [EN] five self-questions ——
    # [EN] Reading the craft must come before judging, not as an afterthought patched in afterwards.
    _craft = ''
    try:
        from crew.agents import craft_block
        g = getattr(world, 'genre_card', None) or {}
        _craft = craft_block('director', str(g.get('主题材') or ''),
                             str(g.get('结构') or ''))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('导演的手艺没拼上（不影响验算）：%r', e)
        _craft = ''
    msg = _VERIFY_PROMPT.format(recap=_recap_text(db, world=world),
                                nodes=_nodes_text(world, db),
                                story=story, script=script_txt,
                                craft=_craft)
    rep = await ask('cheap', [{'role': 'user', 'content': msg}],
                    purpose='day_verify', want=dict, max_tokens=1500)
    data = rep.value if isinstance(rep.value, dict) else None
    if not isinstance(data, dict):
        # ★ 拿不到结论**不许当成通过**（合规那边 fail-open 的教训）：
        #   照实记"没验成"，但仍然让这一天往下走（有剧本总比没有强）。
        # [EN] ★ Not reaching a conclusion **must not be treated as passing** (the lesson from compliance's
        # [EN] fail-open):
        # [EN] Record truthfully "not verified", but still let the day move on (a script is better than none).
        return False, ['（这次没拿到验算结论）'], ''
    # ★★★ 2026-10-18：**按严重度分级**，别让"我会换个写法"变成重写理由。
    #   以前只有一个 `问题` 清单 + 一个 `通过` 布尔，任何一条意见都能判不通过
    #   ⇒ 实测四例里三例跑满 3 轮重写（骆驼祥子、雪国、嫌疑人X），而其中
    #   相当一部分是"这样写也行，只是我会那样写"。重写一次要几十秒 + 一次调用，
    #   而**改完未必更好** —— 代价全花在口味差异上。
    #   现在：只有 `硬伤` 判不通过；`建议` 收进返回值但**不阻断**。
    #   ⚠ 兼容旧键 `问题`：老提示词/老模型可能还给 `问题`，那时**当作硬伤**
    #     （宁可多改一次，也不要把真矛盾放过去）。
    # [EN] ★★★ 2026-10-18: **severity split** -- stop letting "I'd write it differently" force a
    # [EN] rewrite. Previously there was one `问题` list plus a boolean `通过`, so any remark could fail
    # [EN] the script ⇒ measured: three of four cases ran the full three rewrites (Luotuo Xiangzi,
    # [EN] Snow Country, Suspect X), and a good share of them were "this works too, I'd just do it
    # [EN] another way". One rewrite costs tens of seconds and a call, and **the result is not
    # [EN] necessarily better** -- the cost goes entirely to taste differences.
    # [EN] Now only `硬伤` fails it; `建议` is returned but does not block.
    # [EN] ⚠ Backwards compatible with the old `问题` key: if it appears (older prompt or model),
    # [EN] treat it as a hard fault -- better one extra rewrite than letting a real contradiction pass.
    hard = [str(x).strip() for x in (data.get('硬伤') or data.get('hard') or [])
            if str(x).strip()][:6]
    soft = [str(x).strip() for x in (data.get('建议') or data.get('suggest') or [])
            if str(x).strip()][:8]
    legacy = [str(x).strip() for x in (data.get('问题') or []) if str(x).strip()][:6]
    if legacy and not hard:
        hard = legacy
    declared = data.get('通过')
    if declared is None and 'ok' in data:
        declared = data.get('ok')
    # 通过与否**以硬伤为准**；模型说通过但列了硬伤，按硬伤算（自相矛盾时从严）。
    ok = not hard
    if declared is not None and not declared and not hard:
        # 模型明确说不通过却列不出硬伤 ⇒ 那是口味，不是问题。记一条建议后放行。
        soft.append('（模型标记为不通过，但列不出硬伤）')
    probs = hard + soft
    fix = str(data.get('修改意见') or '').strip()[:200]
    if soft:
        _LOG.info('导演给的建议（不阻断）：%s', '；'.join(soft)[:200])
    return ok, probs, fix


async def _rehearse(world, studio, *, story: str, beats: list[dict],
                    roles: dict, people: list[str]) -> tuple[list[dict], str]:
    """**排练**：把这一天**空走一遍**（见 `crew/agents.Rehearsal`）。

    返回 `(问题清单, 结论一句话)`。**拿不到就是两个空** —— 排练失败不该拦住
    这一天的戏（"排不了"不等于"不能演"），但我们**不假装排过了**：
    `ds.rehearsal_verdict` 留空、日志里记一笔。
    
        English:
    **Rehearsal**: **walk through** this day once (see `crew/agents.Rehearsal`).
        Returns `(issue list, one-sentence verdict)`. **If unavailable, both are empty** —— a failed rehearsal should not block
        the day's scenes ("can't rehearse" does not equal "can't perform"), but we **do not pretend it was rehearsed**:
        `ds.rehearsal_verdict` is left empty, and a note is written to the log.
    """
    if studio is None or not (CFG.b('CREW') and CFG.b('CREW_REHEARSAL')):
        return [], ''
    try:
        from crew.agents import SetCtx
        # ★ 阶段标记**在这里打**、不在 `compose()` 里打：关掉排练时不该
        #   出现「▸ 剧组排练」。
        # [EN] ★ The stage marker **is set here**, not in `compose()`: when rehearsal is off it should not

        #   （反例法当场抓到的：判据 E7 说"关掉开关后阶段序列里不该有
        #     rehearsal"，而它还在 —— 因为那一圈 `with _staged(...)` 是无条件
        #     进的。表现就是**屏幕上报了一段根本没跑的流程**。）
        # [EN] (Caught on the spot by the counterexample method: criterion E7 says "after turning the switch
        # [EN] off, the stage sequence should not contain
        # [EN] rehearsal", yet it's still there —— because that round of `with _staged(...)` was entered
        # [EN] unconditionally. The symptom is **the screen reporting a process that never ran**.)
        with _staged(studio, 'rehearsal'):
            note = await studio.rehearse(
                SetCtx(world=world, db=getattr(studio, 'db', None),
                       day=int(getattr(world, 'game_day', 0) or 1),
                       people=list(people or []), story=story),
                story=story, beats=beats, roles=roles)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('排练失败（照原稿开演）：%r', e)
        return [], ''
    if note is None or not note.ok:
        _LOG.info('排练没给出结论（%s）—— 照原稿开演',
                  str(getattr(note, 'why', '') or '没有产出')[:80])
        return [], ''
    d = note.data or {}
    return list(d.get('问题') or []), str(d.get('结论') or '')


def _rehearsal_fix(problems: list[dict]) -> str:
    """把排练的问题压成**给剧作者的一句修改意见**（他照着改得动的那种）。

    ⚠ 要写成"第 3 拍 · 主角：他这时人不在柜上，改成让他从后院听见动静走出来"
      —— 而不是"第 3 拍有问题"。退回去的是**可执行的意见**，
      不是一句"再顺一顺"（那正是 `_VERIFY_PROMPT` 里明令禁止的空话）。
    
        English:
    Compress the rehearsal's issues into **a single revision note for the screenwriter** (something
    he can actually act on).
        ⚠ Write it as "beat 3 · Shen Yan: he is not at the counter at this moment, change it so he hears the noise from the back courtyard and walks out"
          —— not "there's a problem with beat 3". What is sent back is an **actionable note**,
          not a vague "smooth it out a bit" (which is exactly the empty talk `_VERIFY_PROMPT` explicitly forbids).
    """
    bits: list[str] = []
    for p in list(problems or [])[:4]:
        if not isinstance(p, dict):
            continue
        head = f"第 {p.get('拍')} 拍" if p.get('拍') else '某处'
        who = f" · {p['谁']}" if p.get('谁') else ''
        line = f'{head}{who}：{p.get("问题") or ""}'
        if p.get('怎么改'):
            line += f'（{p["怎么改"]}）'
        bits.append(line)
    if not bits:
        return ''
    return '排练走了一遍，下面这些地方**走不下去**，请改掉：\n' + '\n'.join(
        f'- {x}' for x in bits)


async def compose(world, db, *, people: list[str] | None = None,
                  yesterday: str = '', studio=None) -> DayScript:
    """写今天这一天的：故事 → 剧本 → 分派 → 验算 → **排练**（不过关就重写）。

    `people` = 今天在场的人（剧本只许用他们）。取不到就不限制（但会明说"还没有人"）。
    `studio` = 制片厂（`crew/studio.Studio`）。传了它，这几步就**记进剧组台账**
    （界面上「剧组」面板那几行才有状态）；不传就地起一个等价实现
    （单测直接调这一步时走这条，**同一份提示词**，不是两套）。

    ★★ 2026-10-07 加的**排练**这一环（用户点名要的）::

        ① 作家写样章 → ② 剧作者改剧本 → ③ 导演验算（故事顺不顺）
                                        → ④ 排练（**上了场走不走得下去**）
                                            ↓ 走不下去
                                         ⑤ 带意见退回 ②（"重新修改" → "再排练"）

    为什么 ③ 和 ④ 都要有、不是重复：**验算问的是"故事顺不顺"，排练问的是
    "这一步迈得出去吗"**。一个剧本完全可以故事上成立、而场上演不出来
    （把人派到他不在的地方、把台词写死到只能照念）—— 两种毛病，
    一次判断挑不干净。`DAY_PLAN_FIX_ROUNDS` 与 `CREW_REHEARSAL_ROUNDS`
    各管各的额度，只是共用同一圈循环。

    返回的 `DayScript.source`：`ai` = 正常走完；`fallback` = 故事都没写出来
    （调用方照旧跑，只是没有框架 —— **不许假装有**）。
    
        English:
    Write today's: story → script → assignment → verification → **rehearsal** (rewrite if it doesn't
    pass).
        `people` = the people present today (the script may only use them). If unavailable, no restriction (but it will state "no one yet").
        `studio` = the studio (`crew/studio.Studio`). If passed, these steps are **recorded in the crew ledger**
        (only then do the lines in the "crew" panel on the UI have status); if not passed, an equivalent implementation is spun up locally
        (used when unit tests call this step directly, **the same prompt**, not two different sets).
        ★★ 2026-10-07 added the **rehearsal** stage (requested by name by the user)::
            ① writer writes sample chapter → ② screenwriter revises script → ③ director verifies (is the story coherent)
                                            → ④ rehearsal (**can it be walked through once on stage**)
                                                ↓ can't be walked through
                                             ⑤ sent back with notes to ② ("revise" → "rehearse again")
        Why both ③ and ④ are needed and not redundant: **verification asks "is the story coherent", rehearsal asks
        "can this step be taken"**. A script can be perfectly sound as a story yet unperformable on stage
        (sending a person where he isn't, hard-coding dialogue so it can only be read aloud) —— two kinds of problems,
        one judgment cannot catch them all cleanly. `DAY_PLAN_FIX_ROUNDS` and `CREW_REHEARSAL_ROUNDS`
        each govern their own quota, they just share the same loop.
        The returned `DayScript.source`: `ai` = completed normally; `fallback` = the story itself wasn't written
        (the caller runs as usual, just without a framework —— **must not pretend there is one**).
    """
    day = int(getattr(world, 'game_day', 0) or getattr(world.clock, 'day', 1) or 1)
    names = [str(x) for x in (people or [])][:MAX_ROLES]
    ds = DayScript(day=day)
    t0 = time.monotonic()
    with _staged(studio, 'novelist'):
        story = await _write_story(world, db, people=names, yesterday=yesterday,
                                   studio=studio)
    if not story:
        ds.verdict = '这次没写出当天的故事（调用失败或返回为空）'
        _LOG.warning('第 %d 天：当天的故事没写出来（导演这一步跳过）', day)
        return ds
    ds.story = story

    # ★★ 资料员考据（`crew/agents.Researcher`）——名册里写着它 `feeds='screenwriter'`，
    #   所以它必须**真的**递到剧作者手上，否则那条"合作"只是名册上的一句话。
    #   顺序也正好：样章写出来了才有得查，查完才给剧作者。
    #   拿不到（关掉 / 没写出结论）就是空串，剧作者照常写（**不塞假的**）。
    # [EN] ★★ Researcher investigation (`crew/agents.Researcher`) —— the roster says it
    # [EN] `feeds='screenwriter'`,
    # [EN] so it must **actually** be handed to the screenwriter, otherwise that "collaboration" is just a
    # [EN] line on the roster.
    # [EN] The order works out too: only after the sample chapter is written is there anything to look
    # [EN] into, and only after looking into it is it given to the screenwriter.
    # [EN] If it can't be obtained (turned off / no conclusion written), it's an empty string, and the
    # [EN] screenwriter writes as usual (**no faking it**).
    brief = ''
    if studio is not None and CFG.b('CREW') and CFG.b('CREW_RESEARCH'):
        try:
            from crew.agents import SetCtx
            r = await studio.research(
                SetCtx(world=world, db=db, day=day, people=names, story=story),
                story=story)
            if r.ok:
                brief = r.body or ''
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('第 %d 天资料员考据失败（不影响写剧本）：%r', day, e)

    # ★★ **语言审校（上一天）→ 剧作者**（2026-10-12 用户要求"把下游接上"）。
    #   名册里写着 `polisher.feeds == 'screenwriter'`，文档也写着它的下游是
    #   「剧作者（下一天的剧本）」—— 而**代码里从来没人读回它**（那份 md 只有写、
    #   没有读，grep 全仓可证）。现在真的接上：把昨天点出的"AI 味重的原句 + 怎么改"
    #   并进 `brief`（上游材料），剧作者今天照着避。
    #   ⚠ 读**上一天**那一份（`studio.polish_brief` 里认文件头 `> 第 N 天`，
    #     且必须正好是 `day - 1`）—— 同一天重写时读到的就是昨天的，回档重演
    #     当天时读到的是今天自己写的 ⇒ 那一处**跳过**（见那边的说明）。
    #   ⚠ 读不到就是空串，**不编**（与资料员那条同一个口径）。
    # [EN] ★★ **Language review (previous day) -> screenwriter** (user request 2026-10-12: "wire up the
    # [EN] downstream").
    # [EN] The roster says `polisher.feeds == 'screenwriter'`, and the docs say its downstream is "the
    # [EN] screenwriter (next day's script)" -- yet **nothing in the code ever read it back** (that md is
    # [EN] only written, never read; grep the whole repo to confirm). Now it really is wired: yesterday's
    # [EN] "AI-flavoured original sentences + how to fix" are merged into `brief` (upstream material), and
    # [EN] today's screenwriter avoids them.
    # [EN] ⚠ It reads the **previous day's** copy (`studio.polish_brief` recognises the `> 第 N 天` header
    # [EN] and it must be exactly `day - 1`) -- when rewriting the same day it reads yesterday's; when the
    # [EN] day is rolled back and replayed it would read today's own ⇒ that case is **skipped** (see the
    # [EN] note there).
    # [EN] ⚠ Unreadable means empty string, **no making it up** (same convention as the researcher's).
    if studio is not None:
        try:
            _pb = studio.polish_brief(day)
            if _pb:
                brief = f'{brief}\n\n{_pb}'.strip() if brief else _pb
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('第 %d 天读语言审校（上一天）失败（不影响写剧本）：%r', day, e)

    rounds = max(0, CFG.i('DAY_PLAN_FIX_ROUNDS'))
    reh_rounds = max(0, CFG.i('CREW_REHEARSAL_ROUNDS'))
    # ★★ **两个额度是分开记的，不是一个总预算**（2026-10-07）。
    # [EN] ★★ **The two quotas are tracked separately, not one total budget** (2026-10-07).
    #
    #   · `verify_used`（验算重写）只由"验算不通过"消耗 —— 上限 `rounds`；
    #   · `reh_used`（排练重写）只由"排演出问题"消耗 —— 上限 `reh_rounds`。
    # [EN] · `verify_used` (verification rewrite) is consumed only by "verification failed" —— cap
    # [EN] `rounds`;
    # [EN] · `reh_used` (rehearsal rewrite) is consumed only by "rehearsal found a problem" —— cap
    # [EN] `reh_rounds`.
    #
    # ⚠ 第一版把它们合成一个 `budget = rounds + reh_rounds + 1` 的循环计数。
    #   那意味着**验算一直不通过时也能多写两版**（排练那份额度被它吃掉了）——
    #   用户把 `DAY_PLAN_FIX_ROUNDS` 设成 0 时说得很清楚"别重写"，
    #   而它仍然重写了一次（`verify_day_plan` 的 A4b 当场抓到：rounds=2）。
    #   两个开关各管各的，就不该共用一个计数器。
    # [EN] ⚠ The first version merged them into one loop counter `budget = rounds + reh_rounds + 1`.
    # [EN] That means **when verification keeps failing it can still write two more versions** (the
    # [EN] rehearsal quota gets eaten by it) ——
    # [EN] when the user set `DAY_PLAN_FIX_ROUNDS` to 0 they said clearly "don't rewrite",
    # [EN] yet it still rewrote once (`verify_day_plan`'s A4b caught it on the spot: rounds=2).
    # [EN] Two switches each mind their own business, so they shouldn't share one counter.
    verify_used = 0
    reh_used = 0
    fix = ''
    while True:
        with _staged(studio, 'screenwriter' if ds.rounds == 0 else 'rewrite'):
            (beats, roles), intro, brief_txt = await _write_script(
                world, ds.story, people=names, fix=fix, studio=studio,
                brief=brief)
        ds.beats, ds.roles = beats, roles
        # ★★★ 2026-10-26：**拍预算硬闸**（详略由情节决定，不由"一天有多少分钟"决定）。
        #   放在这里（拿到拍之后、验算之前）：验算看到的就是**最终会上演的那几拍**，
        #   否则"验算通过、上演时被截掉一半"等于白验。
        # [EN] ★★★ 2026-10-26: **beat budget hard gate**. Placed here (after the beats arrive, before
        # [EN] verification) so verification sees exactly what will be performed -- otherwise
        # [EN] "passes verification, half truncated at show time" is verification for nothing.
        _blo, _bhi, _bwhy = _beat_budget_cached(world, db)
        ds.beats, _note = _clamp_beats(ds.beats, _blo, _bhi)
        if _note:
            _LOG.info('第 %d 天：%s（%s，预算 %d~%d）', day, _note, _bwhy, _blo, _bhi)
        ds.budget = (_blo, _bhi)
        ds.rounds += 1
        if intro:
            ds.scene_intro = intro
        if brief_txt:
            ds.day_brief = brief_txt
        if not beats and not roles:
            # 这一版什么都没给（JSON 坏了）—— 也占一次验算额度，
            # 否则"每次都返回空"会在这里无限转。
            # [EN] This version gave nothing (broken JSON) —— it still consumes one verification quota,
            # [EN] otherwise "return empty every time" would spin here forever.
            if verify_used < rounds:
                verify_used += 1
                fix = '上一版没有给出分拍或角色任务，请这次务必给出 JSON。'
                continue
            ds.source = 'ai'
            _LOG.warning('第 %d 天：剧作者始终没给出分拍（照用空剧本）', day)
            break
        ok, probs, fix = await _verify(world, db, ds.story, beats, roles)
        ds.problems = probs
        ds.verdict = '通过' if ok else ('不通过：' + '；'.join(probs)[:200] if probs
                                      else '不通过')
        if not ok:
            if verify_used < rounds:
                verify_used += 1
                _LOG.info('第 %d 天：剧本验算不通过（第 %d 轮），带意见重写：%s',
                          day, verify_used, fix[:80] or '；'.join(probs)[:80])
                continue
            # 验算额度用完 —— **照用并记下来**（不无限重写：写不出更好的就是写不出，
            # 那笔钱留给推演更值）。⚠ 到这一步**不再排练**：故事都还不顺，
            # 再花一次调用排它没有意义（排练问的是"上了场走不走得下去"，
            # 而它此刻连"故事顺不顺"都还没过）。
            # [EN] Verification quota exhausted —— **use as-is and record it** (no infinite rewriting: if you can't
            # [EN] write anything better, you can't;
            # [EN] that money is better spent on the simulation). ⚠ At this point **no more rehearsal**: the story
            # [EN] isn't even smooth yet,
            # [EN] so spending another call to rehearse it is pointless (rehearsal asks "can it keep going once on
            # [EN] stage",
            # [EN] and right now it hasn't even passed "is the story smooth").
            ds.source = 'ai'
            _LOG.warning('第 %d 天：剧本 %d 轮验算仍未通过（照用）：%s',
                         day, ds.rounds, ds.verdict[:120])
            break
        # ── **排练**：验算过了才排 ──
        # [EN] ── **Rehearsal**: rehearse only after verification passes ──
        rproblems, rverdict = await _rehearse(
            world, studio, story=ds.story, beats=beats, roles=roles,
            people=names)
        if rproblems or rverdict:
            # 只有**真的排过**才记轮数（关掉排练时不许谎报"排了 1 轮"）
            # [EN] Record the round count only if it **actually rehearsed** (when rehearsal is off, don't falsely
            # [EN] report "rehearsed 1 round")
            ds.rehearsal, ds.rehearsal_verdict = rproblems, rverdict
            ds.rounds_rehearsed += 1
        if rproblems and reh_used < reh_rounds:
            reh_used += 1
            fix = _rehearsal_fix(rproblems)
            _LOG.info('第 %d 天：排演出 %d 处走不下去（第 %d 轮），带意见重写：%s',
                      day, len(rproblems), reh_used, fix[:80])
            continue
        ds.source = 'ai'
        break
    # ★★ **分镜师（P2）+ 视觉参考图（P3）真实接入**（2026-10-15，用户要求"真实接入，pipeline 打通"）。
    #   剧本定稿（无论验算通过、还是额度用完照用）后，把分拍交给分镜师拆成镜头清单，
    #   再把镜头里的人物 / 场景交给视觉参考图生一致性参考图（接 image_gen）。
    #   ⚠ 两条都在"出工"里只走 `studio.call` 这一条唯一入口（台账 / 落盘 / 播报一次到位），不绕过；
    #     开关关、或没有出工对象、或当天没有分拍时，直接跳过（不拦戏）。
    #   ⚠ 视觉参考图接口失败**不拦戏**：它内部已经 try/except，这里再兜一层，绝不让它打断定稿剧本。
    # [EN] ★★ **Storyboard (P2) + Visual ref (P3) real wiring** (2026-10-15, "wire it for real").
    # [EN] After the script is finalized (whether verification passed or quota ran out), hand the beats
    # [EN] to the storyboard artist for a shot list, then hand characters/scenes to visual ref (image_gen).
    # [EN] Both go through the single `studio.call` entry point; off / no studio / no beats → skip (no blocking).
    if studio is not None and ds.beats:
        from crew.agents import SetCtx
        _ctx = SetCtx(world=world, db=db, day=day, people=names,
                      story=ds.story)
        if CFG.b('CREW_STORYBOARD'):
            try:
                _sb = await studio.call('storyboard', _ctx,
                                        beats=ds.beats, story=ds.story)
                if _sb.ok:
                    _shots = (_sb.data or {}).get('shots') or []
                    ds.shots = [dict(x) for x in _shots
                                if isinstance(x, dict)][:48]
            except Exception as e:                        # noqa: BLE001
                _LOG.warning('第 %d 天分镜失败（不影响定稿剧本）：%r', day, e)
        if CFG.b('CREW_VISREF'):
            try:
                _vr = await studio.call('visref', _ctx,
                                        beats=ds.beats, story=ds.story, world=world)
                # ★ P3 闭环（2026-10-15）：visref 的产出以前被丢弃，现在收进
                #   `ds.refs` 落盘，下游生图（场景插图/分镜脚本导出）能当统一参照。
                # [EN] P3 closure: capture visref output into `ds.refs` (was discarded before).
                if getattr(_vr, 'ok', False):
                    _refs = ((getattr(_vr, 'data', None) or {}).get('refs')) or []
                    ds.refs = [dict(x) for x in _refs
                               if isinstance(x, dict)][:24]
            except Exception as e:                        # noqa: BLE001
                _LOG.warning('第 %d 天视觉参考图失败（不影响定稿剧本）：%r', day, e)
    if ds.problems or ds.rehearsal:
        # 轮次用完就**照用并把意见记下来**（不无限重写：写不出更好的就是写不出，
        # 那笔钱留给推演更值）。界面/日志里能看到"这一天的剧本仍有意见"。
        # [EN] When the rounds are exhausted, **use as-is and record the comments** (no infinite rewriting: if
        # [EN] you can't write anything better, you can't;
        # [EN] that money is better spent on the simulation). The UI/log shows "this day's script still has
        # [EN] comments".
        _LOG.warning('第 %d 天：剧本 %d 轮验算 · %d 轮排练后仍有意见（照用）：%s',
                     day, ds.rounds, ds.rounds_rehearsed,
                     (ds.verdict + ' ; 排练：' + ds.rehearsal_verdict)[:140])
    _LOG.info('第 %d 天剧本：%d 拍 · %d 人分派 · %d 轮验算 · %d 轮排练 · %s（%.1fs）',
              day, len(ds.beats), len(ds.roles), ds.rounds,
              ds.rounds_rehearsed, ds.verdict[:40], time.monotonic() - t0)
    return ds


class _staged:
    """给一段流程打上**阶段标记**（用时由 `Studio.stage` 量）。

    `studio` 为 `None`（单测直接调 `compose` 的情形）时**什么都不做** ——
    阶段播报是"制片厂"的能力，没有制片厂就没有人可报。
    
        English:
    Tag a flow with a **stage marker** (timing measured by `Studio.stage`).
        When `studio` is `None` (the case where a unit test calls `compose` directly), **do nothing** ——
        stage announcements are a "studio" capability; without a studio there is no one to announce to.
    """

    __slots__ = ('_studio', '_key', '_cm')

    def __init__(self, studio, key: str):
        self._studio = studio
        self._key = key
        self._cm = None

    def __enter__(self):
        if self._studio is not None and hasattr(self._studio, 'stage'):
            self._cm = self._studio.stage(self._key)
            self._cm.__enter__()
        return self

    def __exit__(self, *exc):
        if self._cm is not None:
            return self._cm.__exit__(*exc)
        return False


# ══════════════════════════════════════════════════════════════════════
#  落盘（**只写运行文件夹** —— 项目文件夹铁律：永不反写）
# [EN] Persist to disk (**write only to the run folder** —— project folder iron rule: never write back)
# ══════════════════════════════════════════════════════════════════════
def save_cached(run_dir, ds: DayScript) -> None:
    """按天记进 `当日剧本.json`（覆盖同一天的那条）。

    为什么不一天一个文件：这东西是**过程稿**（导演的工作底稿），
    一天一份会让运行文件夹多出一堆小文件；按天覆盖正好，也方便对比"第 3 天写的什么"。
    
        English:
    Record by day into `当日剧本.json` (overwriting the entry for the same day).
        Why not one file per day: this thing is a **working draft** (the director's working document),
        one file per day would make the run folder accumulate a pile of small files; overwriting by day is just right, and also convenient for comparing "what was written on day 3".
    """
    if ds is None or not (ds.story or ds.beats or ds.roles):
        return
    root = Path(run_dir)
    path = root / CACHE_NAME
    data: dict = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(old, dict):
                data = {k: v for k, v in old.items() if str(k) != str(ds.day)}
        except Exception:                                        # noqa: BLE001
            data = {}
    data[str(ds.day)] = ds.to_dict()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8')


def load_cached(run_dir, day: int) -> DayScript | None:
    """读回某一天的剧本（没有 / 坏了都返回 None，不抛）。
        English:
    Read back a given day's script (returns None on missing / broken, does not raise).
    """
    try:
        path = Path(run_dir) / CACHE_NAME
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return None
        return DayScript.from_dict(data.get(str(int(day))))
    except Exception:                                            # noqa: BLE001
        return None
