# -*- coding: utf-8 -*-
"""剧组名册（设计稿 §五「多智能体」的落地形态）。

一句话定位
----------
**这是一个剧组，不是一堆提示词。** 每个职位是一个真 Agent：有自己的职责、
自己的模型档、自己的产出、以及**自己的下游**。它们按影视公司的流程排班，
而不是各自对着同一份材料各说各话。

用户的原话（2026-10-07）
------------------------
「你们要组成一个剧组+剧作者的组合，是一个有了故事大纲，随时写故事随时拍电视的
公司。然后各个Agent合理的分配到界面各个位置……我知道的至少有 小说作家 剧作者
导演 各个演员 群众演员 道具 美术 宣发 场记等等需要的角色（跟工具进行合理对接）」

所以这份名册里有两个字段是**故意的、必须的**：

* `feeds` —— 产出交给谁。**没有任何一条是"给用户看"就完了**：写剧本的人
  写给演员，场记写给作者，宣发写给导出。这条链断了，剧组就退化成一堆装饰。
* `hooks` —— **接到软件里的哪个真实东西**。取值是 `模块.符号` 的完整路径，
  `crew/roster.audit_hooks()` 会真的把它们 import 一遍；对不上就报缺。
  为什么非要这样：本项目对"假按钮"零容忍 —— 一个职位如果只是提示词里写了
  一句"你要对接美术"，而程序里根本没有对应的东西，那它就是装饰品。
  **可审计的连接才算连接。**

排班（`when`）
-------------
| 值 | 什么时候出工 |
|---|---|
| `tick`   | 每一拍（只有演员与群众演员在这一档 —— 他们就是"活着"本身） |
| `day`    | 日界出一次（筹备会 + 收工） |
| `export` | 导出/收尾时出一次 |
| `always` | 全程在场（导演：每拍都要看、要判断） |

English:
Crew roster (the concrete form of design doc §5 "multi-agent").
One-line positioning
----------
**This is a film crew, not a pile of prompts.** Each position is a real Agent: with its own
responsibilities,
its own model tier, its own output, and **its own downstream**. They are scheduled per the
workflow of a film company,
rather than each talking to itself against the same material.
The user's own words (2026-10-07)
------------------------
"You should form a crew + playwright combination, a company that, given a story outline, can
write and shoot TV anytime.
Then assign each Agent reasonably to the various UI positions... I know there are at least
novelist, playwright,
director, various actors, extras, props, art, marketing, script supervisor, and so on (properly
interfaced with tools)"
So this roster has two fields that are **intentional and mandatory**:
* `feeds` -- who the output goes to. **None of them just "show it to the user" and stop**: the screenwriter
  writes to the actors, the script supervisor writes to the author, marketing writes to export. If this chain breaks, the crew degrades into a pile of decoration.
* `hooks` -- **which real thing in the software it connects to**. The value is the full path `module.symbol`,
  and `crew/roster.audit_hooks()` will actually import them all; any mismatch is reported.
  Why it must be this way: this project has zero tolerance for "fake buttons" -- if a position merely has a prompt saying
  "you must interface with art", while nothing corresponding exists in the program, then it's an ornament.
  **Only an auditable connection counts as a connection.**
Schedule (`when`)
-------------
| Value | When it works |
|---|---|
| `tick`   | every beat (only actors and extras are in this tier -- they are "being alive" itself) |
| `day`    | once per day boundary (prep meeting + wrap) |
| `export` | once at export/finalization |
| `always` | present throughout (director: must watch and judge every beat) |
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field, replace

_LOG_ROSTER = logging.getLogger('nws.crew.roster')


@dataclass(frozen=True)
class Role:
    """剧组里的一个职位。

    `key` 是稳定标识（配置、验证、界面联动都用它）—— **不要拿显示名当键**：
    显示名要跟随界面语言，键不能。
    
        English:
    A position in the crew.
        `key` is the stable identifier (used by config, validation, UI linkage) -- **do not use the display name as the key**:
        display names follow the UI language, keys must not.
    """

    key: str
    name: str                     # 显示名（中文基准；界面按语言再翻一次）
    duty: str                     # 一句话职责（界面上那行小字）
    tier: str                     # 用哪档模型：cheap / daily / front
    when: str                     # 出工时机：tick / day / export / always
    feeds: str                    # 产出交给谁（另一个职位的 key，或一个功能名）
    hooks: tuple[str, ...] = ()   # 接到软件里的哪些真实东西（`模块.符号`）
    #: 是不是**已经存在于本项目**的职位（演员/导演/群众演员早就在跑了）。
    #: 界面据此把"本来就在跑"和"本轮新设"分开 —— 别把老功能说成新功能。
    # [EN] Display name (Chinese baseline; the UI translates it again per language)
    # [EN] One-line responsibility (the small text on that line in the UI)
    # [EN] Which model tier to use: cheap / daily / front
    # [EN] Work timing: tick / day / export / always
    # [EN] Who receives the output (the key of another role, or a feature name)
    # [EN] Which real things in the software it hooks into (`module.symbol`)
    # [EN] : whether this is a role that **already exists in this project** (actors/director/extras have
    # [EN] been running for a long time).
    # [EN] : the UI uses this to separate "already running" from "newly added this round" -- don't describe
    # [EN] old features as new ones.
    existed: bool = False
    #: ★★ 这一条是**什么性质**（2026-10-12 加，用户要求"novelservices 也作为一个特殊
    #: Agent 纳入管理"）：
    # [EN] : ★★ What **nature** this item is (added 2026-10-12, user requested "novelservices should also
    # [EN] be treated as a special
    # [EN] Agent and brought under management"):
    #:
    #: | 值 | 是什么 | 进不进 `roles()` |
    # [EN] : | value | what it is | goes into `roles()` |
    #: |---|---|---|
    #: | `crew` | 剧组里的一个职位（在推演流程里真的出工） | ✅ 进 |
    #: | `service` | **系统服务**：不是"人"，是程序里一个会花钱的步骤（开卷打磨、记忆摘要…） | ❌ 不进 |
    #: | `special` | **特殊 Agent**：一个外挂的整套服务（创作服务 MuMuAINovel） | ❌ 不进 |
    # [EN] : | `crew` | a position in the crew (actually works in the simulation flow) | ✅ yes |
    # [EN] : | `service` | **system service**: not a "person", but a step in the program that costs money
    # [EN] (opening polish, memory summary...) | ❌ no |
    # [EN] : | `special` | **special Agent**: a whole external service suite (creation service MuMuAINovel)
    # [EN] | ❌ no |
    #:
    #: ⚠ 为什么服务**不能**进 `roles()`：`roles()` 是"剧组今天谁该出工"的口径，
    #:   而剧组会在启动时按它做**缺人自查**（`missing_members`）——服务没有
    #:   `crew/agents.py` 里的实现，混进去会天天误报"缺人"。
    #:   它们出现在**另一个口径**里：`crew/catalog._builtin_specs()`（界面那份名单）。
    # [EN] ★★ What kind of thing this is (added 2026-10-12, on the user's request that
    # [EN] "novelservices also be managed as a special Agent"):
    # [EN] `crew` = a position in the crew (actually works in the simulation pipeline) -> in `roles()`
    # [EN] `service` = a **system service**: not a "person" but a money-spending step in the program
    # [EN] `special` = a **special Agent**: an external whole service (creation service MuMuAINovel)
    # [EN] ⚠ Why services must **not** enter `roles()`: `roles()` is the "who should work today"
    # [EN] view, and the crew runs a **missing-staff self-check** on it (`missing_members`) -- services
    # [EN] have no implementation in `crew/agents.py`, and mixing them in would falsely report
    # [EN] "missing staff" every day. They appear in **another** view:
    # [EN] `crew/catalog._builtin_specs()` (the list shown in the UI).
    kind: str = 'crew'

    @property
    def is_service(self) -> bool:
        """是不是系统服务 / 特殊 Agent（= 不进剧组排班的那两类）。
                English:
        Whether this is a system service / special Agent (= the two kinds not in crew scheduling).
        """
        return self.kind in ('service', 'special')


# ══════════════════════════════════════════════════════════════════════
#  名册
# [EN] Roster
# ══════════════════════════════════════════════════════════════════════
# 顺序就是**界面上的显示顺序**，也大致是流程顺序：
#   编剧组（写）→ 导演组（定）→ 演员组（演）→ 现场组（记）→ 后期组（出）
# [EN] The order is the **display order in the UI**, and roughly the pipeline order:
# [EN] Screenwriting group (write) -> Director group (decide) -> Actor group (perform) -> On-set group
# [EN] (record) -> Post group (ship)
ROSTER: tuple[Role, ...] = (
    Role(
        key='novelist',
        name='小说作家',
        duty='写当天这一章的原著样章',
        tier='daily',
        when='day',
        feeds='screenwriter',
        hooks=('craft.craftmix.brief', 'world.state.WorldState.world_prefix'),
    ),
    Role(
        key='screenwriter',
        name='剧作者',
        duty='把样章改写成能拍的剧本（分场·分拍·谁做什么）',
        tier='daily',
        when='day',
        feeds='director',
        hooks=('craft.craftmix.entries_for', 'director.day_plan'),
    ),
    # ★ 编剧室（2026-10-07）——**排在写样章之前**：先会审补设定，再动笔。
    #   用户：「有些时候需要导演 和 小说作者 以及 剧作家 讨论生成一些新的设定
    #          这些都要进行推演 以便方便故事推进 同时不能够影响总体设定」
    #   它的产出是**局部设定**（场景层/细节层），经 `world/layers.admit_new`
    #   两道闸门之后进 `world.local_settings` —— 与设定集**物理隔离**。
    # [EN] * Writers' room (2026-10-07) -- **scheduled before writing the sample chapter**: first review
    # [EN] and fill in settings, then write.
    # [EN] User: "Sometimes the director, the novelist, and the playwright need to discuss and generate
    # [EN] some new settings
    # [EN] All of these need to be reasoned through to make it easier to advance the story, while not
    # [EN] affecting the overall settings"
    # [EN] Its output is **local settings** (scene layer / detail layer), which after
    # [EN] `world/layers.admit_new`
    # [EN] passes two gates and enters `world.local_settings` -- **physically isolated** from the settings
    # [EN] bible.
    Role(
        key='settings_room',
        name='编剧室',
        duty='导演·小说作家·剧作者三方会审：为该推进的故事补局部设定'
             '（只能动场景层/细节层，不碰总体设定）',
        tier='cheap',
        when='day',
        feeds='screenwriter',
        hooks=('world.layers.admit_new', 'world.layers.SettingItem'),
    ),
    # ★ 下面四位是 2026-10-07 补的（用户：「你再看下现在剧组还缺什么人员
    #   也可以补充进来」）。补之前先问过一遍"缺谁"，结论是缺**四类人**：
    #     ① 收工之后**谁来做复盘** —— 场记只查连戏、宣发只写卖点，
    #        没有一个职位回答"今天这一段到底怎么样、明天该怎么改"；
    #     ② **人身上**的东西没人管 —— 道具管器物、美术管画面，
    #        而衣着/随身物/仪态是**长在人身上**的，两边都不认；
    #     ③ **声音**没人管 —— 每一场都在写"光"和"物"，没人写"听得见什么"，
    #        而"静默"和"环境音"是小说里最省字的氛围手段；
    #     ④ **没有人为"话好不好听"负责** —— 去 AI 库（`style/deai.py`）
    #        能查词，但"这几句该怎么改"需要一个真读稿的人。
    #   —— 补的都是**有真实消费方**的职位，不摆装饰（本项目对"假按钮"零容忍）。
    # [EN] * The four roles below were added on 2026-10-07 (user: "Take another look at what the crew is
    # [EN] still missing
    # [EN] and add them in too"). Before adding, we asked once "who's missing", and the conclusion was four
    # [EN] categories of people:
    # [EN] 1) **Who does the retrospective after wrap** -- the script supervisor only checks continuity,
    # [EN] and marketing only writes selling points,
    # [EN] no role answers "how did today's segment actually go, and how should it be changed tomorrow";
    # [EN] 2) **Nobody manages things on the person** -- props handle objects, art handles visuals,
    # [EN] while clothing / carried items / bearing are **on a person's body**, and neither side claims
    # [EN] them;
    # [EN] 3) **Nobody manages sound** -- every scene writes "light" and "objects", nobody writes "what can
    # [EN] be heard",
    # [EN] and "silence" and "ambient sound" are the most word-economical atmosphere tools in a novel;
    # [EN] 4) **Nobody is responsible for "whether the words sound good"** -- the de-AI library
    # [EN] (`style/deai.py`)
    # [EN] can check words, but "how should these few lines be changed" needs someone who actually reads
    # [EN] the script.
    # [EN] -- All additions are roles with **real consumers**, no decoration (this project has zero
    # [EN] tolerance for "fake buttons").
    Role(
        key='reviewer',
        name='复盘',
        duty='每天收工复盘：剧情总结 + 存在的问题 + 后续修改意见（必要时建议改当天的戏）',
        tier='daily',
        when='day',
        feeds='director',
        hooks=('style.deai.audit_text', 'style.deai.render_report'),
    ),
    Role(
        key='stylist',
        name='造型',
        duty='人物身上的东西：衣着·随身物·仪态 —— 给演员穿戴，并进出图提示词',
        tier='cheap',
        when='day',
        feeds='actor',
        # ★ 2026-10-07 审计：两处下游**都补上了**（以前只写了名册、程序里没接）——
        #   `sim/loop._crew_prep` 把造型压成一段写进 `world.stylist_brief`
        #   → `agent/core._semi` 的 `[你身上]`（演员看得到自己穿什么）；
        #   `crew/studio.image_prefix` 把穿着/随身物拼进出图提示词。
        # [EN] * 2026-10-07 audit: both downstream links are **now connected** (previously only written in the
        # [EN] roster, not wired in the program) --
        # [EN] `sim/loop._crew_prep` compresses the styling into a paragraph and writes it to
        # [EN] `world.stylist_brief`
        # [EN] -> `agent/core._semi`'s `[你身上]` (actors can see what they're wearing);
        # [EN] `crew/studio.image_prefix` splices clothing / carried items into the image-generation prompt.
        hooks=('image_gen.ai.build_prompt', 'agent.core.Agent',),
    ),
    Role(
        key='sound',
        name='声音',
        duty='这一场的声音层：环境音·静默·声音的转折 —— 喂给场景的环境句',
        tier='cheap',
        when='day',
        feeds='actor',
        # ★ 2026-10-07 审计：hook 从 `observe_note` 改成 `observe_quiet` ——
        #   声音的落点是"全场无事的那些片刻写环境白描"，那是 `observe_quiet`
        #   干的活（`observe_note` 只是个通用机制标注，谁都能调）。
        # [EN] * 2026-10-07 audit: hook changed from `observe_note` to `observe_quiet` --
        # [EN] the landing point for sound is "write environmental description for the quiet moments when
        # [EN] nothing happens in the scene", which is what `observe_quiet`
        # [EN] does (`observe_note` is just a generic mechanism annotation, anyone can call it).
        hooks=('display.scene_builder.SceneBuilder.observe_quiet',),
    ),
    Role(
        key='polisher',
        name='语言审校',
        duty='读当天样章，点名哪几句 AI 味重、该怎么改（去 AI 库的每日深查）',
        tier='cheap',
        when='day',
        feeds='screenwriter',
        # ★ 2026-10-07 审计：这位此前**一天都没出工过**——`Studio.polish()`
        #   零调用点（现在由 `crew/studio.wrap` 在收工时调，排在复盘之前）。
        # [EN] * 2026-10-07 audit: this one **has not worked a single day** before this -- `Studio.polish()`
        # [EN] had zero call sites (now called by `crew/studio.wrap` at wrap time, scheduled before the
        # [EN] retrospective).
        hooks=('style.deai.audit_text', 'style.deai.prompt_block'),
    ),
    # ★ **分镜师（P2, 2026-10-15）**：剧本定稿后把分拍拆成镜头清单（开源漫剧「剧本→分镜」）。
    #   真实接入：`director/day_plan.py::compose` 在剧本定稿后调 `studio.call('storyboard', ...)`，
    #   产出落 `ds.shots`（中栏 / 落盘走 `DayScript.shots_text`）。
    # [EN] ★ **Storyboard (P2, 2026-10-15)**: break beats into a shot list after the script is finalized.
    Role(
        key='storyboard',
        name='分镜师',
        duty='把定稿剧本的分拍拆成镜头清单（镜号 / 景别 / 画面 / 台词 / 镜头运动），'
             '给导演和演员当拍摄说明书（开源漫剧「剧本→分镜」这一步）',
        tier='cheap',
        when='day',
        feeds='actor',
        hooks=('crew.agents.Storyboard.work', 'director.day_plan.compose'),
    ),
    # ★ **视觉参考图（P3, 2026-10-15）**：分镜定稿后为出场人物 / 关键场景生一致性参考图（接 image_gen）。
    #   真实接入：`compose` 在分镜之后调 `studio.call('visref', ...)`；接口失败只产清单不拦戏。
    # [EN] ★ **Visual reference (P3, 2026-10-15)**: consistent ref art for characters/scenes (image_gen).
    Role(
        key='visref',
        name='视觉参考图',
        duty='分镜定稿后，为出场人物 / 关键场景生成一致性参考图（接 image_gen），'
             '给下游生图 / 视频当统一参照（开源漫剧「分镜→视觉（角色/场景）」这一步）',
        tier='cheap',
        when='day',
        feeds='art',
        hooks=('crew.agents.VisualRef.work', 'image_gen.portrait.generate_portrait'),
    ),
    # ★ **排练**（2026-10-07）：用户 2026-10-07 问的「剧本出来所有人先快速走一遍
    #   但是不出现结果在窗口里吗？如果是的话可以加排练这个阶段」——
    #   就是这个意思。**排在这条链的正中间**：剧本改完 → 空走一遍 → 有问题就
    #   带意见回去重写（`feeds='screenwriter'` 就是那条回边）。
    # [EN] * **Rehearsal** (2026-10-07): the user asked on 2026-10-07, "once the script is out everyone
    # [EN] quickly walks through it
    # [EN] but the result doesn't appear in the window? If so we can add a rehearsal stage" --
    # [EN] that's exactly what this means. **It sits right in the middle of this chain**: script revised ->
    # [EN] dry run -> if there are problems
    # [EN] take notes back and rewrite (`feeds='screenwriter'` is that back edge).
    #
    #   ⚠ 它的产出**不上中栏**：那是"排给剧组自己看的"，不是故事。
    #     用户要的是「过程用小的消息（只显示阶段名和用时）」，落盘照旧。
    # [EN] ! Its output **does not go to the center column**: that's "rehearsal for the crew's own eyes",
    # [EN] not the story.
    # [EN] What the user wants is "the process uses small messages (showing only the stage name and elapsed
    # [EN] time)", while disk output stays as before.
    Role(
        key='rehearsal',
        name='排练',
        duty='剧本定稿后把这一天**空走一遍**：哪一拍谁做不到、人不在场、'
             '写死了台词 —— 有问题就退回剧作者改',
        tier='daily',
        when='day',
        feeds='screenwriter',
        hooks=('crew.studio.Studio.rehearse', 'director.day_plan.DayScript'),
    ),
    Role(
        key='director',
        name='导演',
        duty='定框架、派活、挑事、验算、**盯戏**、收尾',
        tier='daily',
        when='always',
        feeds='actor',
        hooks=('director.engine.DirectorEngine',
               'director.day_plan.DayScript'),
        existed=True,
    ),
    Role(
        key='actor',
        name='演员',
        duty='在框架之内自由发挥',
        tier='daily',
        when='tick',
        feeds='continuity',
        hooks=('agent.core.Agent', 'display.scene_builder.SceneBuilder'),
        existed=True,
    ),
    Role(
        key='extra',
        name='群众演员',
        duty='门外的人与事（外部输入）',
        tier='cheap',
        when='tick',
        feeds='actor',
        hooks=('world.crowd.sync_crowd', 'world.crowd.new_extra'),
        existed=True,
    ),
    Role(
        key='continuity',
        name='场记',
        duty='连戏检查：时间·物件·称呼·状态对不对得上',
        tier='cheap',
        when='day',
        feeds='director',
        hooks=('store.runfolder.RunFolder', 'sim.loop.RunLoop._push_narrative'),
    ),
    # ★★ **剧本审读**（2026-10-08）：用户点名的那个"独立的 Agent"。
    # [EN] ** ** Script review (2026-10-08): the "independent Agent" the user called out by name.
    #
    #   用户原话：「你看是否有独立的Agent 而不是导演在盯着演员说的每一句话
    #   没有就做一个 **在演员真的说出来之前**，把新生成的话放到已经出现的话里
    #   过一遍，看是否通顺 而且这个Agent要**一直记录生成的所有信息**，
    #   **所有输出到窗口的东西**包括动作 场景切换 伏笔激活 导演动作 人物对话
    #   等等 都要让这个Agent记录下来 任何一个新出现的东西，不管来自哪个
    #   Agent或者来源，都需要这个Agent放到已有历史里看下是否是一个合理的
    #   正确的好看的故事和剧本 **不是就不要放出来**」
    # [EN] The user's exact words: "See whether there's an independent Agent rather than the director
    # [EN] watching every line the actor says
    # [EN] if not, make one **before the actor actually says it**, put the newly generated lines into the
    # [EN] lines that have already appeared
    # [EN] and go over them to see if they read smoothly, and this Agent must **keep recording all
    # [EN] generated information**,
    # [EN] **everything output to the window** including actions, scene switches, foreshadowing
    # [EN] activations, director actions, character dialogue,
    # [EN] etc., all must be recorded by this Agent; any newly appearing thing, no matter which
    # [EN] Agent or source it comes from, needs this Agent to put it into the existing history and check
    # [EN] whether it is a reasonable
    # [EN] correct good-looking story and script **if not, don't release it**"
    #
    #   与已有的三位"看戏的人"**不是同一件事**（那个对照表写在
    #   `crew/review.py` 的模块 docstring 里）：场记与复盘在**一天结束**才看、
    #   导演盯戏只查"重复"且**不能拦** —— 而用户要的是**上屏那一刻**、
    #   逐条过、不通过**就不放出来**。
    # [EN] It is **not the same thing** as the existing three "spectators" (that comparison table is
    # [EN] written in
    # [EN] the module docstring of `crew/review.py`): the script supervisor and the retrospective look only
    # [EN] at **end of day**,
    # [EN] the director watching the scene only checks for "repetition" and **cannot block** -- whereas
    # [EN] what the user wants is **at the moment of going on screen**,
    # [EN] line by line, and if it doesn't pass **it is not released**.
    #
    #   `when='tick'`：它是**每一拍都要看**的（闸门挂在拍上）；
    #   `feeds='director'`：拦下/改写之后，那几条意见要给导演（下一拍派活时用）。
    #   ⚠ 它的产出**不上中栏**（那是"读稿意见"，不是故事）—— 走
    #     `crew/studio.Studio.audit()`，只进台账/日志/小结。
    # [EN] `when='tick'`: it is **watched every tick** (the gate hangs on the tick);
    # [EN] `feeds='director'`: after blocking / rewriting, those notes go to the director (used when
    # [EN] assigning work next tick).
    # [EN] ! Its output **does not go to the center column** (that's "script-reading notes", not the story)
    # [EN] -- it goes through
    # [EN] `crew/studio.Studio.audit()`, and only enters the ledger / log / summary.
    Role(
        key='script_doctor',
        name='剧本审读',
        duty='上屏之前逐条读一遍：是不是人话·像不像这个人·接不接上文·'
             '是不是一个主题 —— 不通过就改写或拦下（全程记账）',
        tier='cheap',
        when='tick',
        feeds='director',
        hooks=('crew.review.ScriptLog', 'sim.loop.RunLoop._script_review'),
    ),
    Role(
        key='props',
        name='道具',
        duty='这一场该有什么物件、哪件要反复出现',
        tier='cheap',
        when='day',
        feeds='continuity',
        hooks=('image_gen.hook.make_image_hook', 'display.script.Entry'),
    ),
    Role(
        key='art',
        name='美术',
        duty='定这一部的画风与配色，管住出图一致性',
        tier='cheap',
        when='day',
        feeds='props',
        hooks=('image_gen.watercolor', 'image_gen.portraits.build_portrait_prompt'),
    ),
    Role(
        key='publicity',
        name='宣发',
        duty='写一句话卖点、看点、预告',
        tier='cheap',
        when='export',
        # ⚠ 2026-10-07 审计改：原来是 `feeds='export'`，但**导出侧从来不读它**
        #   （`export/*` 里搜不到 `宣发文案`）。写 `export` 会让名册说一句
        #   程序里不成立的话 —— 本项目对"名册上写着、程序里没接"零容忍。
        #   改成 `author`：它的去处是"给人看的地方"（运行文件夹里的
        #   `宣发文案.md`），确实是给作者/宣发自己用的，不进导出物。
        # [EN] ! 2026-10-07 audit change: originally it was `feeds='export'`, but **the export side never reads
        # [EN] it**
        # [EN] (searching `export/*` finds no `宣发文案`). Writing `export` would make the roster say something
        # [EN] that doesn't hold in the program -- this project has zero tolerance for "written in the roster
        # [EN] but not wired in the program".
        # [EN] Changed to `author`: its destination is "a place for people to read" (the `宣发文案.md`
        # [EN] in the run folder), which is indeed for the author / marketing themselves, and does not enter
        # [EN] the export artifacts.
        feeds='author',
        hooks=('store.runfolder.RunFolder.export_dir',),
    ),
    Role(
        key='researcher',
        name='资料员',
        duty='考据：这一处的名物、制度、称谓站不站得住',
        tier='cheap',
        when='day',
        feeds='screenwriter',
        hooks=('research.lookup', 'refs.rag'),
        existed=True,
    ),
)

#: 键 → 职位（查表用）。名册是数据，界面/流程/验证都从这里取，不许各写一份。
# [EN] : key -> role (for table lookup). The roster is data; the UI / pipeline / validation all take
# [EN] from here, and no one may write their own copy.
BY_KEY: dict[str, Role] = {r.key: r for r in ROSTER}


# ══════════════════════════════════════════════════════════════════════
#  系统服务与特殊 Agent（2026-10-12）
# [EN] System services and the special Agent (2026-10-12)
# ══════════════════════════════════════════════════════════════════════
# 用户 2026-10-12 的原话：
#   「把Agents配置页强化，所有Agents都加一个模型选项…… novelservices服务也被作为一个
#     特殊Agent纳入管理。」
# [EN] User's exact words on 2026-10-12:
# [EN] "Strengthen the Agents configuration page, add a model option to all Agents... the novelservices
# [EN] service should also be treated as a
# [EN] special Agent and brought under management."
#
# 为什么这几条**不放进上面那个 `ROSTER` 元组**：那一位是"剧组里有人"的名单，
# 剧组会按它排班、按它做缺人自查。而下面这五条**不是人**：
#   · 四个 `service` 是程序里**会花钱的步骤**（开卷打磨、记忆摘要、进度评估、合规复核）——
#     它们本来就在跑，只是以前"用哪个模型"是写死在代码里（三档之一），
#     现在要让作者能挑；
#   · `special` 的 `novelservices` 是**另一个程序**（MuMuAINovel），本项目通过 HTTP 调它。
# 所以它们出现在**另一份口径**里：`crew/catalog._builtin_specs()`（界面那份名单）。
# [EN] The user's exact words (2026-10-12):
# [EN] "Strengthen the Agents config page; give every Agent a model option... let the novelservices
# [EN] service also be managed as a special Agent."
# [EN] Why these are **not** put into the `ROSTER` tuple above: that one is the list of "who is in the
# [EN] crew", used for scheduling and the missing-staff self-check. The five below **are not people**:
# [EN] the four `service` ones are **money-spending steps** in the program (open-book polishing,
# [EN] memory summarization, progress evaluation, compliance review) -- they already run; it's just
# [EN] that "which model" used to be hard-coded (one of the three tiers) and is now the author's
# [EN] choice; and the `special` one, `novelservices`, is **another program** (MuMuAINovel) called
# [EN] over HTTP. So they appear in **another view**: `crew/catalog._builtin_specs()`.
SERVICE_ROLES: tuple[Role, ...] = (
    Role(
        key='ingest',
        name='开卷摄取',
        duty='把作者给的资料读成能用的设定：提取人物与世界观、判类型、定风格、'
             '排进度、拟开局、按需打磨',
        tier='daily',
        when='day',
        feeds='author',
        hooks=('ingest.pipeline.run_ingest', 'ingest.optimize.review_settings'),
        existed=True, kind='service',
    ),
    Role(
        key='memory',
        name='记忆摘要',
        duty='跨天把当天压成几句话、给后台人物补经历 —— 前情提要的来源',
        tier='cheap',
        when='day',
        feeds='author',
        hooks=('agent.core.Agent.compact_memory', 'sim.backstage.Backstage.run_batch'),
        existed=True, kind='service',
    ),
    Role(
        key='progress',
        name='进度评估',
        duty='每一拍判断「这一站的判据满足了没有」—— 推进故事进度节点',
        tier='cheap',
        when='tick',
        feeds='director',
        hooks=('director.engine.DirectorEngine.evaluate_progress',),
        existed=True, kind='service',
    ),
    Role(
        key='compliance',
        name='合规复核',
        duty='按力度复核即将落盘的正文（独立于创作 Agent，只做判级与提示）',
        tier='cheap',
        when='always',
        feeds='author',
        hooks=('compliance.agent.ComplianceAgent.check',),
        existed=True, kind='service',
    ),
)

#: 特殊 Agent（2026-10-12）：**外挂的一整套服务**，不是一个提示词。
#: 目前只有一位：创作服务 MuMuAINovel（`novelservices/mumu_bridge.py`）。
# [EN] : Special Agents (2026-10-12): **an entire external service**, not a prompt.
# [EN] Currently just one: the creation service MuMuAINovel (`novelservices/mumu_bridge.py`).
SPECIAL_ROLES: tuple[Role, ...] = (
    Role(
        key='novelservices',
        name='创作服务',
        duty='外挂的写作后端（MuMuAINovel）：开卷后由它写样章（可选）',
        tier='front',
        when='day',
        feeds='author',
        hooks=('novelservices.mumu_bridge',),
        existed=True, kind='special',
    ),
)

#: 上面两类的合并（界面那份名单要的就是"剧组 + 服务"）。
#  ⚠ **顺序也是界面的分组顺序**：剧组 → 系统服务 → 特殊 Agent。
# [EN] : The merge of the two above (the UI list wants "crew + services").
# [EN] ⚠ **The order is also the UI grouping order**: crew -> system services -> special Agents.
SERVICE_KEYS: frozenset[str] = frozenset(
    r.key for r in (*SERVICE_ROLES, *SPECIAL_ROLES))
SERVICE_BY_KEY: dict[str, Role] = {r.key: r for r in (*SERVICE_ROLES, *SPECIAL_ROLES)}


def service_roles() -> tuple[Role, ...]:
    """系统服务 + 特殊 Agent（**不含剧组职位**）。
        English:
    System services + special Agents (**not including crew positions**).
    """
    return (*SERVICE_ROLES, *SPECIAL_ROLES)


def all_roles() -> tuple[Role, ...]:
    """剧组 + 系统服务 + 特殊 Agent（界面那份名单）。
        English:
    Crew + system services + special Agents (the list shown in the UI).
    """
    return (*ROSTER, *SERVICE_ROLES, *SPECIAL_ROLES)


# ══════════════════════════════════════════════════════════════════════
#  有效名册（软件默认 + 项目定制）—— 2026-10-11
# [EN] Effective roster (software default + project customization) -- 2026-10-11
# ══════════════════════════════════════════════════════════════════════
# ★★ 上面那份 `ROSTER` 是**出厂名册**（软件默认），它**永远不该被改写** ——
#    它是一个模块级常量，多本书共用一个进程时改它就会互相串味。
#    真正给流程/界面/用量用的，是下面这个 `roles()`：出厂名册 + 作者改过的
#    那几项 + 自建职位（见 `crew/catalog.py`）。
# [EN] ** ** The `ROSTER` above is the **factory roster** (software default), and it **should never be
# [EN] rewritten** --
# [EN] it is a module-level constant; when multiple books share one process, changing it causes
# [EN] cross-contamination.
# [EN] What is actually used by the pipeline / UI / usage is the `roles()` below: factory roster + the
# [EN] entries the author changed
# [EN] + self-built roles (see `crew/catalog.py`).
#
#    ⚠ 不要在这里 `from crew import catalog`（模块级）——`catalog` 反过来要读
#      本模块的 `ROSTER`，模块级互引会在 import 期炸。用**惰性 import**。
# [EN] ! Do not `from crew import catalog` here (module level) -- `catalog` in turn needs to read
# [EN] The `ROSTER` of this module; module-level cross-references will blow up at import time. Use
# [EN] **lazy import**.
_ROLES_CACHE: dict = {}
#: 服务/特殊 Agent 的**有效**条目（作者改过名字/职责时以改过的为准）。
#  与 `_ROLES_CACHE` 一起由 `roles()` 填，见那段注释。
# [EN] : The **effective** entries of services / special Agents (author edits win).
# [EN] Filled by `roles()` together with `_ROLES_CACHE`, see that passage.
_SERVICE_CACHE: dict[str, Role] = {}


def roles() -> tuple[Role, ...]:
    """**有效名册**：出厂名册 + 软件层改动 + 项目层定制 + 自建职位。

    认不出（`catalog` 起不来、文件坏了）就**照出厂名册走** ——
    名册读不出来不该让整个剧组停摆（那是"改个名字把戏弄停"）。
    
        English:
    **Effective roster**: factory roster + software-layer changes + project-layer customization +
    self-built positions.
        If unrecognizable (`catalog` can't start, file corrupted), **fall back to the factory roster** --
        an unreadable roster should not halt the entire crew (that would be "renaming the play to a stop").
    """
    try:
        from crew import catalog as CAT
        sig = CAT.signature()
    except Exception as e:                                       # noqa: BLE001
        _LOG_ROSTER.warning('读 Agent 设置失败（按出厂名册干活）：%r', e)
        return ROSTER
    hit = _ROLES_CACHE.get(sig)
    if hit is not None:
        return hit
    try:
        specs = CAT.effective()
    except Exception as e:                                       # noqa: BLE001
        _LOG_ROSTER.warning('算 Agent 有效属性失败（按出厂名册干活）：%r', e)
        return ROSTER
    out: list[Role] = []
    for s in specs:
        base = BY_KEY.get(s.key)
        if base is None:
            # ★ 系统服务 / 特殊 Agent（2026-10-12）：它们**在界面的名单里，但不在剧组排班里**
            #   （见 `SERVICE_ROLES` 上面那段）。这里有两条路：
            #     · 作者改过它的名字/职责 → 按改过的记（`replace`）；
            #     · 没改过 → 用出厂那一条。
            #   两条都**不进 `out`**（= 不进 `roles()`）。
            # [EN] ★ System services / special Agent (2026-10-12): they are **in the UI list but not
            # [EN] in crew scheduling** (see the passage above `SERVICE_ROLES`). Two paths here: if the
            # [EN] author changed its name/duty, record the changed one (`replace`); otherwise use the
            # [EN] factory one. Neither enters `out` (= not in `roles()`).
            svc = SERVICE_BY_KEY.get(s.key)
            if svc is not None:
                _SERVICE_CACHE[s.key] = replace(
                    svc, name=s.name or svc.name,
                    duty=(s.intro or svc.duty),
                    tier=(s.tier if s.tier in ('cheap', 'daily', 'front')
                          else svc.tier))
                continue
            # 自建职位：没有 hooks（它不接程序里的任何东西 —— 这是它和内置
            # 职位最大的区别，也让 `audit_hooks()` 不必为它报缺）。
            # [EN] Self-built positions: no hooks (they don't connect to anything in the program -- this is the
            # [EN] biggest
            # [EN] difference from built-in positions, and it also means `audit_hooks()` doesn't need to report
            # [EN] them missing).
            out.append(Role(key=s.key, name=s.name,
                            duty=s.intro or s.name,
                            tier=(s.tier if s.tier in ('cheap', 'daily', 'front')
                                  else 'daily'),
                            when=(s.when if s.when in
                                  ('tick', 'day', 'export', 'always') else 'day'),
                            feeds=s.feeds or 'author', hooks=(), existed=False))
        else:
            out.append(replace(
                base, name=s.name, duty=(s.intro or base.duty),
                tier=(s.tier if s.tier in ('cheap', 'daily', 'front')
                      else base.tier),
                when=(s.when if s.when in
                      ('tick', 'day', 'export', 'always') else base.when),
                feeds=s.feeds or base.feeds))
    _ROLES_CACHE.clear()
    _ROLES_CACHE[sig] = tuple(out)
    return _ROLES_CACHE[sig]


def role_or_service(key: str) -> Role:
    """按 key 取职位，**服务也算**（界面上的名字/职责都从这儿取）。

    ⚠ 与 `role()` 的区别只有一个：`role()` 是**剧组口径**（服务取不到就抛，
      因为"把服务塞进剧组"是调用方的错），这个是**名单口径**。

        English:
    Fetch a role by key, **services included** (the UI takes names/duties from here).
        ⚠ The only difference from `role()`: `role()` is the **crew view** (a service not found
        raises, because "putting a service into the crew" is the caller's mistake), while this is
        the **list view**.
    """
    k = str(key or '').strip()
    svc = _SERVICE_CACHE.get(k)
    if svc is not None:
        return svc
    if k in SERVICE_BY_KEY:
        return SERVICE_BY_KEY[k]
    return role(k)


def role(key: str) -> Role:
    """按 key 取名册里那个职位（**有效名册**，含作者改过与自建的）。

    ⚠ 认不出就**抛**（不是返回 None、也不是造一个占位职位）：
      调用方拿到一个假职位，会把"我们没设计这个位子"变成"这个位子没干活"。
    
        English:
    Look up that position in the roster by key (**effective roster**, including author-modified and
    self-built).
        ⚠ If unrecognizable, **throw** (not return None, not construct a placeholder position):
          if the caller gets a fake position, it turns "we didn't design this seat" into "this seat did no work".
    """
    k = str(key or '').strip()
    r = BY_KEY.get(k)
    eff = {x.key: x for x in roles()}
    if k in eff:
        return eff[k]
    if r is not None:
        return r                     # catalog 起不来时的兜底
        # [EN] Fallback for when catalog can't start up
    raise KeyError(f'名册里没有这个职位：{key!r}')


def keys() -> list[str]:
    return [r.key for r in roles()]


def by_order(*, when: str = '') -> list[Role]:
    """名册顺序（可按出工时机筛）。界面与流程共用。
        English:
    Roster order (filterable by work timing). Shared by UI and workflow.
    """
    return [r for r in roles() if not when or r.when == when]


def feeds_of(key: str) -> list[str]:
    """谁把产出交给了我（**反向查表**：画流程、查断链都用它）。
        English:
    Who handed output to me (**reverse lookup**: used for drawing flows and finding broken chains).
    """
    return [r.key for r in roles() if r.feeds == key]


# ══════════════════════════════════════════════════════════════════════
#  自查：每条 `hooks` 都得是真的
# [EN] Self-check: every `hooks` entry must be real
# ══════════════════════════════════════════════════════════════════════
def resolve_hook(path: str):
    """把 `模块.属性.属性…` 解析成真对象；解析不出来返回 `None`。

    为什么不能只 `import_module(模块前缀)` 再看模块级属性：名册里写的是
    **真正被用到的那一层** —— `world.state.WorldState.world_prefix` 是个**方法**、
    `sim.loop.RunLoop._push_narrative` 也是。只查模块级会把这些判成"对不上"
    （第一版就是这么红的，而且它红得有道理：不精确的检查等于没有检查）。

    做法：**从最长前缀往回退**，找到第一个能 import 的模块，
    剩下的部分当作属性链 `getattr` 下去。
    
        English:
    Resolve `module.attr.attr...` into a real object; if resolution fails return `None`.
        Why not just `import_module(module prefix)` and then look at module-level attributes: the roster records
        **the level that is actually used** -- `world.state.WorldState.world_prefix` is a **method**,
        and so is `sim.loop.RunLoop._push_narrative`. Only checking module level would mark these as "mismatched"
        (the first version was red exactly like this, and it was right to be red: an imprecise check is no check).
        Approach: **walk back from the longest prefix**, find the first module that can be imported,
        and treat the rest as an attribute chain via `getattr`.
    """
    raw = str(path or '').strip()
    if not raw:
        return None
    parts = raw.split('.')
    for cut in range(len(parts), 0, -1):
        modname = '.'.join(parts[:cut])
        try:
            obj = importlib.import_module(modname)
        except Exception:                                        # noqa: BLE001
            continue
        for attr in parts[cut:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        return obj
    return None


def audit_hooks() -> dict[str, list[str]]:
    """把名册里每条 hook 真的解析一遍，返回 `{职位: [对不上的 hook]}`。

    空 dict = 全部对得上。**这是"对接到软件架构"的唯一凭据** ——
    没有它，"我们接线了"就只是一句话。

    为什么连**方法和私有方法**也查（不只是类）：名字写错时，宽检查照样过，
    要到运行时才炸。这里在启动期就现形（`resolve_hook` 会一路 getattr 到底）。
    
        English:
    Actually resolve every hook in the roster, return `{position: [mismatched hooks]}`.
        Empty dict = all match. **This is the only evidence of "being wired into the software architecture"** --
        without it, "we wired it up" is just a sentence.
        Why check **methods and private methods** too (not just classes): when a name is misspelled, a loose check still passes,
        and it only blows up at runtime. Here it surfaces at startup (`resolve_hook` will getattr all the way down).
    """
    bad: dict[str, list[str]] = {}
    for r in roles():
        miss = [h for h in r.hooks if resolve_hook(h) is None]
        if miss:
            bad[r.key] = miss
    return bad


def roster_md() -> str:
    """名册的 Markdown 一页（落进运行文件夹，给人看**这个剧组是怎么搭的**）。

    故意带上 `hooks`：作者能一眼看到"宣发的产出真的进了导出"，
    而不是只有一句职责描述。
    
        English:
    A Markdown page for the roster (drops into the run folder, shows people **how this crew is put
    together**).
        Deliberately include `hooks`: the author can see at a glance that "the publicity output really made it into the export,"
        rather than just a one-line description of responsibilities.
    """
    lines = ['# 剧组名册', '',
             '| 职位 | 职责 | 出工 | 产出交给 | 接到软件里的 |',
             '|---|---|---|---|---|']
    for r in roles():
        lines.append(
            f'| **{r.name}** | {r.duty} | {r.when} | {r.feeds} | '
            + '、'.join(f'`{h}`' for h in r.hooks) + ' |')
    lines += ['', '> 出工时机：`tick` 每一拍 · `day` 日界 · `export` 导出时 · '
                  '`always` 全程在场。']
    bad = audit_hooks()
    lines.append('> 接线自查：'
                 + ('全部命中 ✓' if not bad else f'有 {len(bad)} 个职位对不上 ✗'))
    return '\n'.join(lines) + '\n'
