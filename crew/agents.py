# -*- coding: utf-8 -*-
"""剧组成员：每个职位一个真 Agent（各自读自己的工艺、交自己的活）。

与 `crew/roster.py` 的分工
--------------------------
名册是**数据**（谁、干什么、接到哪个东西）；这里是**实现**（怎么干出那件活）。
两者靠 `key` 对齐 —— `Role(key)` 与这里的类一一对应，缺一个
`crew/studio.Studio` 起不来（**故意让它在启动期就报，不要跑到一半才发现**）。

三条共同的规矩
--------------
1. **一个职位一次调用**。每个成员只问模型一次（拿不到就带原因返回），
   不在内部偷偷重试 —— 重试是 `llm.replies.ask()` 的事，而且它会把
   "为什么没拿到"记进 `notes`。剧组里最贵的不是钱，是**说不清为什么没出活**。
2. **各读各的工艺**。小说作家读结构与铺垫（章法/网文），剧作者读场面与可拍性
   （剧作与舞台/编剧正典）。**不许所有人读同一份简报** —— 那样十个职位
   等于一个职位问十遍。
3. **产出一定有人接**。`Role.feeds` 指到哪，产出就往哪走；界面上的「剧组」
   面板也是从同一条链上取状态。没有下游的产出不许写（那就是装饰）。

English:
Crew members: one real Agent per position (each reads its own craft, delivers its own work).
Division of labor with `crew/roster.py`
--------------------------
The roster is **data** (who, does what, receives what); here is **implementation** (how to
produce that work).
The two align by `key` —— `Role(key)` corresponds one-to-one with the classes here, and missing
one
means `crew/studio.Studio` won't start (**deliberately let it fail at startup, don't discover it
halfway through**).
Three shared rules
--------------
1. **One position, one call**. Each member asks the model only once (if it can't get a result, return with the reason),
   no sneaky internal retries —— retrying is the job of `llm.replies.ask()`, and it will record
   "why nothing was obtained" into `notes`. The most expensive thing in a crew is not money, it's **being unable to explain why no work came out**.
2. **Each reads its own craft**. The novelist reads structure and setup (composition/web fiction), the playwright reads scene and filmability
   (drama & stage / screenwriting canon). **Everyone must not read the same brief** —— that way ten positions
   amount to one position asked ten times.
3. **Every output must have a receiver**. Where `Role.feeds` points, the output goes there; the "剧组" on the UI
   panel also takes its state from the same chain. Output with no downstream must not be written (that's just decoration).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import CFG
from craft import craftmix
# ★ 2026-10-24：段进度要进 `DOING` 栈（状态条要显示「第 5/18 段」）。
#   `t()` 是给那一句用的 —— 之前这个模块一个 `t()` 都没用过，所以这里没有 import。
# [EN] ★ 2026-10-24: the chunk progress goes on the `DOING` stack (the status bar must show
# [EN] "chunk 5/18"). `t()` is for that sentence -- this module never used `t()` before,
# [EN] hence no import.
from crew import review as REVIEW
from crew import roster as ROSTER
# ★ 2026-10-26：**按情节单元写**（详略由情节决定，不由字数决定）。
#   `unit_plan` 是纯函数模块（只 import `re` / `dataclasses`），放模块级不会绕回来。
# [EN] ★ 2026-10-26: **write by plot unit** (thickness decided by plot, not by character count).
# [EN] `unit_plan` is a pure module (imports only `re` / `dataclasses`), so a top-level import
# [EN] cannot create a cycle.
from crew import unit_plan as UP
from i18n import t
from llm.replies import ask
from util.jsonio import extract_json_lenient

_LOG = __import__("logging").getLogger("nws.crew")


# ══════════════════════════════════════════════════════════════════════
#  产出
# [EN] Output
# ══════════════════════════════════════════════════════════════════════
@dataclass
class CrewNote:
    """一个职位交上来的一份活。

    `title` 是**界面上那一行**（一句话，短）；`body` 是正文（可以长）。
    拿不到东西时 `ok=False` 且 `why` 写清原因 —— **不许交一份空白的假活**。
    
        English:
    One piece of work handed up by one position.
        `title` is **the line on the UI** (one sentence, short); `body` is the main text (can be long).
        When nothing can be obtained, `ok=False` and `why` states the reason clearly —— **must not hand in a blank fake work**.
    """

    role: str
    title: str = ''
    body: str = ''
    ok: bool = True
    why: str = ''
    #: 给程序读的结构化部分（如道具清单、宣发的 logline）。给人看的是 `body`。
    # [EN] : the structured part for the program to read (e.g. prop list, promotional logline). What humans
    # [EN] read is `body`.
    data: dict = field(default_factory=dict)

    def one_line(self) -> str:
        """界面上那一行：标题 +（拿不到时的原因）。
                English:
        That line in the UI: title + (reason when unobtainable).
        """
        if not self.ok:
            return f'{self.title or "（没出活）"} —— {self.why}'
        return self.title or self.body.splitlines()[0][:40]


# ══════════════════════════════════════════════════════════════════════
#  拍摄现场（喂给每个职位的共同材料）
# [EN] Shooting site (the common material fed to every role)
# ══════════════════════════════════════════════════════════════════════
@dataclass
class SetCtx:
    """**现场**：这一天剧组手上有什么。

    刻意做成一个薄对象（不是把 `world`/`db` 各传一遍）：成员要什么自己取，
    这样"某个成员偷看了不该看的东西"才看得出来（它得先写 `ctx.world.xxx`）。
    
        English:
    **Scene**: what the crew has on hand for this day.
        Deliberately made a thin object (rather than passing `world`/`db` separately): members fetch what they need themselves,
        so that "some member peeked at what it shouldn't" is visible (it has to write `ctx.world.xxx` first).
    """

    world: Any
    db: Any
    day: int = 1
    people: list[str] = field(default_factory=list)
    #: 当天已写好的样章 / 剧本（收工那些职位要用）
    # [EN] : the sample chapter / script already written that day (needed by the roles at wrap)
    story: str = ''
    beats: list[dict] = field(default_factory=list)
    #: 当天落盘的幕（`SceneScript` 列表；场记要用）
    # [EN] : the acts persisted that day (`SceneScript` list; needed by the script supervisor)
    scenes: list = field(default_factory=list)
    #: **这本书叫什么 / 它的项目目录在哪**（2026-10-09 加）。
    # [EN] : **what this book is called / where its project directory is** (added 2026-10-09).
    #: 为什么要有：外部创作服务（MuMuAINovel）要**按书**建项目、并把
    #: "这本书 ↔ 它的项目 id"的映射缓存落到**这本书自己的目录**里。
    #: `world` 上既没有书名也没有目录，而这两件事又只有调用方（`sim/loop`
    #: 或 `Studio`）知道 —— 所以显式传进来，别去 `world` 上瞎猜属性名。
    #: 两个都可缺（拿不到就退化成"按全局表找项目"，功能不丢、只是映射不跟着书走）。
    # [EN] : Why this is needed: the external creation service (MuMuAINovel) must create projects **per
    # [EN] book**, and
    # [EN] : cache the "this book <-> its project id" mapping into **this book's own directory**.
    # [EN] : `world` has neither the book name nor the directory, and only the caller (`sim/loop`
    # [EN] : or `Studio`) knows these two things — so pass them in explicitly, don't go guessing attribute
    # [EN] names on `world`.
    # [EN] : Both can be missing (if unavailable, fall back to "find project by global table";
    # [EN] functionality is not lost, only the mapping no longer follows the book).
    book: str = ''
    novel_dir: Any = None
    #: **正在跑的那个 `RunLoop`**（可选）。只有一样用途：让写稿那一侧能问一句
    #: 「用户点了停止吗」—— 实测点停止之后又写了两遍样章、多等 3 分钟，
    #: 用户把这件事感受成「收尾特别久」，而收尾根本没开始（见 `write_check_retry`）。
    #: ⚠ 默认 None：探针/判据/不跑循环的场合取不到它，那时就当「不停」（旧行为）。
    # [EN] The running `RunLoop` (optional). One purpose only: let the writing side ask
    # [EN] 'did the user hit stop' -- measured, it wrote two more sample passes (3 minutes) after
    # [EN] stop, which the user experienced as 'wrap-up takes forever' when wrap-up had not even
    # [EN] started. ⚠ Defaults to None: probes/criteria have no loop, and then it means 'never stop'.
    loop: Any = None
    #: ★★★ 2026-10-17：**今天开演前写的那份「原著样章」**（小说作家的第一次产出）。
    #   `story` 是**剧作者**的框架（谁在哪、做什么），文笔是"计划"口吻；
    #   这一项是**同一位作家**按小说写法写出的散文，文笔明显更好
    #   （实测：587 字的样章有"擦得慢，像在磨什么"、"水声咚三下"、"西窗的光暗了一截"，
    #   而收工整理出的 670 字是机械改写 —— 同样的事件，一个像小说、一个像报表）。
    #   ⇒ 收工整理时把它当**文笔参照**喂进去：内容照实际发生的写，笔调照这份样章走。
    #   ⚠ **不是**"用它替换整理稿"：样章是开演前写的计划，与实际演出必然有出入
    #     （这次实测里样章写了"角色甲伸手：壶。"，实际那一段没发生），
    #     所以它只能当"笔调样本"，不能当"内容来源"。
    # [EN] ★★★ 2026-10-17: **the "original sample chapter" written before the show** (the novelist's
    # [EN] first output). `story` is the **playwright's** framework (who is where, doing what) in a
    # [EN] "plan" voice; this is prose written in novel style **by the same writer**, visibly better
    # [EN] (measured: the 587-character sample has "wiped it slowly, as if grinding something",
    # [EN] "three dull thuds in the well", "the light through the west window dimmed a notch", while the
    # [EN] 670-character wrap-up is mechanical rewriting -- same events, one reads like a novel, the
    # [EN] other like a report).
    # [EN] => At wrap-up it is fed in as a **style reference**: content follows what actually happened,
    # [EN] tone follows this sample.
    # [EN] ⚠ **Not** "use it to replace the organized draft": the sample is a pre-show plan and will
    # [EN] inevitably differ from what was performed (in this measurement it had "the character reached out:
    # [EN] the pot." which never happened), so it can only be a **style sample**, never a source.
    sample: str = ''

    # ── 常用料（都在这里取，免得每个成员各拼一遍、各漏一样）──
    # [EN] ── Common materials (all fetched here, so each member doesn't assemble them separately and miss
    # [EN] one each time) ──
    def genre(self) -> tuple[str, str]:
        g = getattr(self.world, 'genre_card', None) or {}
        return str(g.get('主题材') or '').strip(), str(g.get('结构') or '').strip()

    def world_brief(self, cap: int = 1200) -> str:
        """这本书是什么（给**作家**读的那一份）。

        ★ 2026-10-21：**把 `writer_notes` 拼进来**。
          它是「这本书实测出来的写法约束」（`style.notes` → `写作层规则.md`），
          与 `rules_text` 分开存，因为 `rules_text` 会原样进每个**演员**的提示词，
          而这些是"成品读起来该是什么样"的要求 —— 演员在一拍里没法执行
          （"每样最多复位三次"，他一拍里数不出来，只学会绕开那件东西）。
          ⚠ 所以：作家走这条路（带上 notes），演员走 `world_prefix_stable()`
            （只带上 `actor_notes`）。两条路各取所需，谁也不多读。
        [EN] What this book is (the copy the **writer** reads).
        [EN] ★ 2026-10-21: **`writer_notes` is appended here**. Those are the book's measured writing
        [EN] constraints (`style.notes` -> `写作层规则.md`), kept apart from `rules_text` because
        [EN] `rules_text` goes verbatim into every **actor** prompt, while these describe "what the
        [EN] finished prose should read like" -- not executable inside one beat. So the writer takes
        [EN] this path (with notes) and actors take `world_prefix_stable()` (only `actor_notes`).
        """
        try:
            base = str(self.world.world_prefix() or '').strip()
        except Exception:                                        # noqa: BLE001
            base = ''
        try:
            wn = str(getattr(self.world, 'writer_notes', '') or '').strip()
        except Exception:                                        # noqa: BLE001
            wn = ''
        if wn:
            base = (base + chr(10) * 2 + wn) if base else wn
        return base[:cap] if base else ''

    def style_block(self) -> str:
        """**风格控制** → 一段能执行的话（作家与 MuMuAINovel 那一侧共用）。

        ★★★ 2026-10-27：这七个旋钮以前是**死的**（`world.humor_level` 读进来
          之后没有任何消费者）。现在它们会变成"最多一处这样的笑点""必须有一处
          拿不回来的东西"这种**能数、能查、能照做**的话。
        ★ 为什么**不挂进 `world_brief()`**：那一串是 `world_prefix()[:cap]`，
          而 `world_prefix()` 最前面就是顶级规则（实测某部真实项目那份 1853 字）⇒
          `cap=1200` 时顶级规则就把位置吃满了，**世界观/类型/风格/写作层规则
          全被挤掉**（实测）。风格控制必须走**独立的一段**。
        ⚠ **开关关掉就一个字都不发**（`STYLE_CONTROL_ACTIVE`）。

            English:
        **Style control** -> one executable paragraph (shared by the writer and the MuMuAINovel side).
        ★★★ 2026-10-27: those seven knobs used to be **dead** (`world.humor_level` was read and then
        [EN] nothing consumed it). Now they become "at most one such joke in this passage" / "there must be
        [EN] one thing you cannot get back" -- countable, checkable, followable.
        ★ Why **not inside `world_brief()`**: that string is `world_prefix()[:cap]`, and `world_prefix()`
        [EN] starts with the top-level rules (measured: 1853 chars for one real book) => at `cap=1200`
        [EN] the rules alone fill the space and **the worldview/type/style/writer notes are all squeezed
        [EN] out** (measured). The style control has to be **its own section**.
        ⚠ **With the switch off, not a single word is emitted** (`STYLE_CONTROL_ACTIVE`).
        """
        try:
            if not CFG.b('STYLE_CONTROL_ACTIVE'):
                return ''
        except Exception:                                        # noqa: BLE001
            return ''

        def _num(attr: str, default: float) -> float:
            try:
                v = getattr(self.world, attr, None)
            except Exception:                                    # noqa: BLE001
                v = None
            if v is None:
                return float(default)
            try:
                return float(v)
            except (TypeError, ValueError):
                return float(default)

        try:
            from util import style_kit as SK
            return SK.style_control_block(
                humor=_num('humor_level', 0.3),
                angst=_num('angst_level', 0.3),
                satisfaction=_num('satisfaction_density', 0.5),
                romance=_num('romance_ratio', 0.3),
                suspense=_num('suspense_density', 0.5),
                worldbuilding=_num('worldbuilding_pace', 0.5),
                iq=_num('character_iq', 0.5),
                pacing=str(getattr(self.world, 'pacing_style', 'medium') or 'medium'),
            )
        except Exception:                                        # noqa: BLE001
            return ''

    def scene_line(self) -> str:
        w = self.world
        return (f'场景：{getattr(w, "scene", "")}，'
                f'时间：{getattr(w, "clock_display", lambda: "")()}，'
                f'天气：{getattr(w, "weather", "")}')

    def recap(self, limit: int = 1500) -> str:
        from director import day_plan as DAYPLAN
        try:
            return DAYPLAN.recap_text(self.db, world=self.world)[-limit:]
        except Exception:                                        # noqa: BLE001
            return ''


# ══════════════════════════════════════════════════════════════════════
#  成员基类
# [EN] Member base class
# ══════════════════════════════════════════════════════════════════════
def _reflexion_on() -> bool:
    """多轮修稿走不走 Reflexion 路径（默认走）。

    ⚠ 读配置**失败也算开** —— 新架构是默认行为，不该因为一个键没登记就悄悄退回旧路
      （那种"静默回退"会让判据和真跑看到两套行为，见 §52.4）。
    """
    try:
        return bool(CFG.b('PROSE_REFLEXION'))
    except Exception:                                            # noqa: BLE001
        return True


class CrewMember:
    """剧组里的一个人。

    子类只实现 `work()`；`run()` 负责"记一条、别让它静默失败"这些共同部分。
    
        English:
    One person in the crew.
        Subclasses only implement `work()`; `run()` handles the shared parts like "log one entry, don't let it fail silently".
    """

    #: 对应名册里的哪个职位（子类必须给）
    # [EN] : which role in the roster this corresponds to (subclasses must provide)
    key: str = ''

    @property
    def role(self):
        return ROSTER.role(self.key)

    @property
    def name(self) -> str:
        return self.role.name

    async def run(self, ctx: SetCtx, **kw) -> CrewNote:
        try:
            note = await self.work(ctx, **kw)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组「%s」出工异常：%r', self.name, e)
            return CrewNote(role=self.key, ok=False,
                            title=self.role.name, why=f'出工异常（{e!r}）')
        if note is None:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='没有产出')
        if not isinstance(note, CrewNote):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why=f'产出类型不对（{type(note).__name__}）')
        if note.ok and not (note.title or note.body):
            # **空白不算出活**：一条 ok=True 的空产出会被界面画成一个空行，
            # 看起来像"这个职位在偷懒"而不是"这次没拿到东西"。
            # [EN] **Blank doesn't count as work**: an empty output with ok=True gets drawn as a blank line in the
            # [EN] UI,
            # [EN] looking like "this role is slacking off" rather than "nothing was obtained this time".
            note.ok, note.why = False, '产出是空的'
        return note

    async def work(self, ctx: SetCtx, **kw) -> CrewNote:
        raise NotImplementedError


def _craft_for(shelves: tuple[str, ...], genre: str, structure: str = '',
               limit: int = 4, prefer: tuple[str, ...] = ()) -> str:
    """按**货架**取 playbook 条目（该职位该读的那几本）。

    ⚠ 与 `craftmix.brief()` 的区别：那个是**导演挑事用的类型简报**（冲突偏好 +
    钩子 + 爽点 + 2 条映射条目）。这里要的是"**这一行手艺的条目**"，
    所以按**来源货架**取，而不是按类型卡的固定映射 —— 写剧本的人该读剧作与舞台，
    哪怕这本小说的类型卡映射里没写它。

    没有类型卡时也要能读（那就不过滤类型，按名字取）—— 手艺是通用的。

    ★★ `prefer` = **这个职位点名要读的那几条**（见 `READS`，2026-10-07 加）。
    以前这里只有"先取映射、再按文件顺序补三条"，于是**同一架书里
    谁读到的都是前三条** —— 具体后果是：场记（它的活儿是"每场有没有落点"）
    读到的是剧作者的写作提示，而它该读的「一场一转变」排在文件第 16 位、
    **永远轮不到**。书架上摆着，人拿到的却总是随手抽的三本。

    所以顺序改成：**优先 `prefer` 指定的 → 再类型卡映射到的 → 最后按货架补满**。
    三条路径都**限定在该职位的货架之内**（不许跨架：跨架就等于职位声明是假的）。
    
        English:
    Fetch playbook entries by **shelf** (the books this position should read).
        ⚠ Difference from `craftmix.brief()`: that one is the **genre brief used by the director to pick material** (conflict preferences +
        hooks + payoff points + 2 mapping entries). What's wanted here is "**the entries of this line of craft**",
        so fetch by **source shelf**, not by the fixed mapping of the genre card —— the person writing the script should read drama & stage,
        even if this novel's genre card mapping doesn't list it.
        It must be readable even without a genre card (then skip genre filtering, fetch by name) —— craft is universal.
        ★★ `prefer` = **the specific entries this position explicitly asks to read** (see `READS`, added 2026-10-07).
        Previously there was only "fetch the mapping first, then fill in three by file order", so **on the same shelf
        everyone read the first three** —— the concrete consequence: the script supervisor (whose job is "does every scene have a landing point")
        read the playwright's writing prompts, while the "one turn per scene" it should read was ranked 16th in the file,
        **Never gets picked**. It sits on the shelf, but people always grab three random ones.
        So the order is changed to: **first the `prefer` specified ones → then those mapped by type cards → finally fill up from the shelf**.
        All three paths are **confined to that position's shelf** (no crossing shelves: crossing shelves means the position's declaration is fake).
    """
    # ⚠ 只做**健康检查**，不再把 `entries` 拿在手上 —— 挑哪几条由调度器决定
    #   （它在 `pick` 里自己 load）。库读不了就返回空串：手艺缺席是常态，
    #   不该让整个提示词装配失败。
    # [EN] Health check only; `entries` is no longer held here -- the dispatcher decides which to
    # [EN] pick (it loads inside `pick`). An unreadable library returns '' : absent craft is normal
    # [EN] and must not break prompt assembly.
    try:
        if not craftmix.load()['entries']:
            return ''
    except Exception:                                            # noqa: BLE001
        return ''
    # ★★★ 2026-10-18：**改走调度器**（`craft/dispatch.pick`）。
    #
    # 为什么换掉那三步（它们已在 2026-10-18 晚删除，见本函数末尾的说明）：
    #   老的第 ③ 步是"遍历 `entries`，按 yaml 文件顺序补满 `limit`" ——
    #   `entries` 的顺序是**文件顺序**，于是每个职位拿到的永远是同一批前几条。
    #   实测（2026-10-18 盘点）：**81 条里有 24 条从来没到过任何人的提示词**，
    #   而且"这一拍是开场还是收束"完全不影响读什么 —— 开场读到「章回钩子」、
    #   收束读到「黄金三章」，都是噪声。
    #   调度器按（职位 × 类型 × 时机 × 品级 × 拍数）挑，且环形轮换保证每条都轮得到。
    #
    # ⚠ `prefer` 与 `shelves` 两个入参保留：`prefer` 现在被调度器当成"重品级"信号
    #   （它在 `READS` 里也在，两条一致），`shelves` 与 `SHELVES` 同源。
    #   —— 判据里对 `_craft_for(shelves, genre, prefer=…, limit=…)` 的调用仍然成立。
    # [EN] ★★★ 2026-10-18: **now goes through the dispatcher** (`craft/dispatch.pick`).
    # [EN] Why the three steps were replaced (removed on 2026-10-18 evening, see the note at
    # [EN] the end of this function):
    # [EN] step ③ walked `entries` in **yaml file order** to fill `limit`, so every role got the
    # [EN] same first few entries. Measured on 2026-10-18: **24 of 81 entries never reached any
    # [EN] prompt**, and "is this beat an opening or a closing" had zero effect on what was read.
    # [EN] The dispatcher picks by (role x genre x moment x grade x tick) with a ring so every
    # [EN] entry gets its turn.
    # [EN] ⚠ `prefer` and `shelves` are kept: `prefer` is now a "heavy grade" signal, `shelves`
    # [EN] shares its source with `SHELVES` -- so existing criteria that call
    # [EN] `_craft_for(shelves, genre, prefer=..., limit=...)` still hold.
    try:
        from craft import dispatch as DISP
        role = next((r for r, sh in SHELVES.items() if sh == tuple(shelves)), '')
        # ★★★ "这一拍是什么时候 / 什么品级"从**世界上**读，不往调用点加参数。
        #   理由与 `_CURRENT_WORLD` 完全相同：`_craft_for` 被 14 个职位各调一次，
        #   加参数就是"十四处各写一份"，一定漏。
        #   `beat_moment` 由 `sim/loop` 每拍算，`craft_level` 由**导演**
        #   （`director/supervisor.grade_beat`）判 —— 这就是"由特定 Agent 负责品级"。
        #   ⚠ 世界上没这两个字段时（老存档、单测）一律按 `日常`/`中`，
        #     行为与改造前一致，不会因为缺字段就少喂东西。
        # [EN] ★★★ "What moment / what grade this beat is" is read **off the world**, never
        # [EN] added as a parameter: `_craft_for` is called once per role, so params would mean
        # [EN] "fourteen places each writing their own copy". `beat_moment` is computed by
        # [EN] `sim/loop`; `craft_level` is judged by the **director**
        # [EN] (`director/supervisor.grade_beat`) -- that is "a specific Agent owns the grade".
        # [EN] ⚠ Missing fields (old saves, unit tests) default to 日常/中, so the behavior is
        # [EN] identical to before the change; nothing gets dropped.
        _w = _CURRENT_WORLD
        _mom = str(getattr(_w, 'beat_moment', '') or '日常') if _w is not None else '日常'
        _lvl = str(getattr(_w, 'craft_level', '') or '中') if _w is not None else '中'
        _tk = int(getattr(_w, 'beat_tick', 0) or 0) if _w is not None else 0
        _av = tuple(getattr(_w, 'craft_read', ()) or ()) if _w is not None else ()
        picked_rows = DISP.pick(
            role, genre=genre, structure=structure,
            moment=_mom, level=_lvl, k=int(limit), tick=_tk, avoid=_av,
        )
        if not picked_rows and not role:
            # 找不到职位（调用方给了裸 shelves）⇒ 退回老路径，绝不返回空
            raise LookupError('no role for shelves')
        # ⚠ `craft_read` 必须**真有人写**：调度器的 `avoid` 靠它把"这一场刚读过的"
        #   排到后面。写完没人写 = 那个参数永远收不到东西 = 半截改动
        #   （审计工具 E 类）。写在这里是因为它是**唯一**的选取出口。
        # [EN] `craft_read` must be **actually written**: the dispatcher's `avoid` uses it to rank
        # [EN] already-read entries last. Written here because this is the **only** selection exit.
        try:
            if _w is not None and hasattr(_w, 'note_craft'):
                _w.note_craft([n for n, _t, _lv in picked_rows])
        except Exception:                                        # noqa: BLE001
            pass
        return DISP.render(picked_rows)
    except LookupError:
        pass
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('手艺调度不可用，退回按货架取（不影响出工）：%r', e)
    # ⚠ 2026-10-18 晚：这里原来还有"prefer → 类型卡映射 → 按文件顺序补满"三步取货。
    #   调度器接上之后它**永远执行不到**（`_craft_for` 的唯一调用点传的是
    #   `SHELVES[key]`，按它一定能反查出 role）⇒ 是死代码，按项目纪律删掉
    #   （"假旋钮要删"、"同一件事两处实现是万恶之源"）。
    #   ⚠ 但**调度器不可用**时不能返回空串（那就是"手艺整个消失"，比读少了更糟）：
    #     退化成"这个职位池子的前 limit 条" —— 一条最小的活路。
    # [EN] 2026-10-18 evening: the old three-step fetch ("prefer -> genre mapping -> fill by file
    # [EN] order") is gone. With the dispatcher wired in it can **never execute** (`_craft_for`'s
    # [EN] only call site passes `SHELVES[key]`, from which role is always recoverable) => dead code,
    # [EN] removed per project discipline. ⚠ But when the dispatcher is unavailable we must not
    # [EN] return an empty string (that is "all craft vanishes", worse than reading less): fall back
    # [EN] to the first `limit` entries of this role's pool -- a minimal live path.
    try:
        from craft import dispatch as DISP
        role = next((r for r, sh in SHELVES.items() if sh == tuple(shelves)), '')
        rows = DISP.pool(role)[:max(0, int(limit))]
        return '\n'.join(f'〔{n}〕{str(e.get("提示词") or e.get("原理") or "").strip()}'
                          for n, e in rows
                          if str(e.get('提示词') or e.get('原理') or '').strip())
    except Exception:                                            # noqa: BLE001
        return ''


#: 各职位读哪几本工艺书（**这就是"参考经典剧作理论"的落点**）。
# [EN] : which craft books each role reads (**this is where "reference classic dramatic theory"
# [EN] lands**).
SHELVES: dict[str, tuple[str, ...]] = {
    # 小说作家：故事怎么讲 —— 结构、铺垫、伏笔、期待感 + **人怎么立、话怎么说**
    # [EN] Novelist: how the story is told — structure, setup, foreshadowing, sense of expectation + **how
    # [EN] people are established, how they speak**
    'novelist': ('中国古典章法', '网络文学方法论', '西方编剧正典', '人物与对话',
                 '场景与空间', '叙事学正典'),
    # 剧作者：怎么落到场上 —— 场、人、话、物、可拍性（台词是他的活的一半）
    # [EN] Playwright: how it lands on stage — scene, people, speech, objects, filmability (dialogue is
    # [EN] half his job)
    'screenwriter': ('剧作与舞台', '西方编剧正典', '人物与对话', '场景与空间',
                     '叙事学正典'),
    # 场记：连戏靠的是"每场都有转变"和"谁在场上"，读剧作与舞台
    # [EN] Script supervisor: continuity depends on "every scene has a turn" and "who is on stage"; reads
    # [EN] drama and stage
    'continuity': ('剧作与舞台', '场景与空间', '叙事学正典'),
    # ★★ 剧本审读（2026-10-08）：它要判的**两半**分别是"这一场立不立得住"
    #   （剧作与舞台）与"这话像不像这个人说的"（人物与对话）——
    #   而"称呼一变关系就变""口癖来自职业与处境"那几条正在后一架里，
    #   用户举的例子（自家伙计被叫"客官"）正是那两条管的。
    # [EN] ★★ Script review (2026-10-08): the **two halves** it must judge are "does this scene hold up"
    # [EN] (drama and stage) and "does this speech sound like this person" (character and dialogue) —
    # [EN] and the entries "a change of address changes the relationship" and "verbal tics come from
    # [EN] profession and circumstance" are in the latter shelf,
    # [EN] and the user's example (their own shop hand being called "customer") is exactly what those two
    # [EN] govern.
    'script_doctor': ('剧作与舞台', '人物与对话', '西方编剧正典', '叙事学正典'),
    # 道具/美术：物件与画面
    # [EN] Props/art: objects and visuals
    'props': ('剧作与舞台', '场景与空间'),
    'art': ('剧作与舞台', '场景与空间'),
    # 资料员：考据靠古典章法与制度
    # [EN] Researcher: textual research relies on classical composition and institutions
    'researcher': ('中国古典章法',),
    # 宣发：钩子与期待感
    # [EN] Promotion: hooks and sense of expectation
    'publicity': ('网络文学方法论',),
    # 编剧室（导演·小说作家·剧作者 三方会审）：既要"戏能演"（剧作与舞台），
    # 也要"补的东西对读者有效"（网文方法论）—— 三方各读各的那一半。
    # [EN] Writers' room (director, novelist, playwright three-way review): needs both "the play can be
    # [EN] performed" (drama and stage),
    # [EN] and "what's added is effective for readers" (web-fiction methodology) — each of the three reads
    # [EN] their own half.
    'settings_room': ('剧作与舞台', '网络文学方法论', '场景与空间', '叙事学正典'),
    # 复盘：既要看结构（编剧正典）也要看文气（古典章法）—— 两半各读各的
    # [EN] Retrospective: must look at both structure (screenwriting canon) and textual verve (classical
    # [EN] composition) — each half reads its own
    'reviewer': ('西方编剧正典', '中国古典章法', '人物与对话', '叙事学正典'),
    # 造型/声音：都从"细节承住戏"那一路来（剧作与舞台里那几条）
    # [EN] Styling/sound: both come from the path of "details carry the drama" (those entries in drama and
    # [EN] stage)
    'stylist': ('剧作与舞台',),
    'sound': ('剧作与舞台',),
    # 语言审校：文气与字法（古典章法）+ **台词得像那个人说的话**（人物与对话）。
    # ★ 2026-10-07 加了后一架：只读古典章法的话，它手上只有"起承转合"这类
    #   **结构**条目，而它要挑的是"这一句读起来像机器写的" —— 那是字法的事。
    # [EN] Language proofreading: textual verve and diction (classical composition) + **dialogue must sound
    # [EN] like what that person would say** (character and dialogue).
    # [EN] ★ 2026-10-07 added the latter shelf: reading only classical composition leaves it with only
    # [EN] items like "introduction, development, turn, conclusion"
    # [EN] **structure** entries, whereas what it must pick out is "this sentence reads like it was written
    # [EN] by a machine" — that's a matter of diction.
    'polisher': ('中国古典章法', '剧作与舞台', '人物与对话', '叙事学正典'),
    # ★★ **演员**（2026-10-07 加）：这是全项目**输出台词最多**的职位，而它
    #   此前**一本工艺书都不读**（`SHELVES` 里根本没有 'actor' 这一项）。
    #   结果就是：剧本那一侧被反复叮嘱"人物一句话立起来"，真正开口的人
    #   手上却没有一条关于"话该怎么说"的手艺 —— 台词像念设定的根子在这。
    #   ⚠ 它读的是"**怎么说**"那一半（说话方式/停顿/话长短/口癖来处），
    #     不读"故事怎么讲"（那是编剧组的事，读了只会让它想推进剧情）。
    # [EN] ★★ **Actor** (added 2026-10-07): this is the role with the **most dialogue output** in the whole
    # [EN] project, and
    # [EN] previously it **read not a single craft book** (`SHELVES` had no 'actor' entry at all).
    # [EN] The result: the script side is repeatedly told "establish a character in one line", but the
    # [EN] person who actually speaks
    # [EN] has not a single craft item about "how to speak" — this is the root of dialogue sounding like
    # [EN] reading off a spec.
    # [EN] ⚠ It reads the "**how to speak**" half (manner of speech / pauses / line length / where verbal
    # [EN] tics come from),
    # [EN] not "how the story is told" (that's the writers' room's job; reading it would only make it want
    # [EN] to advance the plot).
    # ★ 2026-10-18：加「叙事学正典」这一架，但**只用 `READS` 点两条**
    #   （`邻接对` / `场与场的缝`）—— 一整架给它，"反应与决定""欲望与需求"
    #   就会让它去替编剧排结构（上面那条警告说的正是这个）。
    # [EN] ★ 2026-10-18: added the "narratology canon" shelf, but **only two entries are named in
    # [EN] `READS`** (`adjacency pair` / `the seam between scenes`) -- giving it the whole shelf would
    # [EN] push it into arranging structure for the writers (exactly what the warning above is about).
    'actor': ('人物与对话', '叙事学正典'),
    # ★★ **导演**（2026-10-07 加）：它是三人小组里唯一没有货架的一个 ——
    #   而它正是"审剧本、派活、挑事"的那个人（用户说的"用于优化故事"）。
    #   它读两样：**结构那一半**（怎么判断一场戏立不立得住）＋
    #   **人那一半**（这场戏里的人像不像人）。
    #   ⚠ 它此前只通过 `craftmix.brief()`（挑事用的类型简报）间接读到 2 条条目，
    #     `craft_block` 这条路根本没接 —— 而"导演该读什么手艺"从来没被点过名。
    # [EN] ★★ **Director** (added 2026-10-07): it's the only one of the three-person group with no shelf —
    # [EN] and it is precisely the one who "reviews the script, assigns work, stirs things up" (the user's
    # [EN] "used to optimize the story").
    # [EN] It reads two things: **the structure half** (how to judge whether a scene holds up) +
    # [EN] **the people half** (whether the people in this scene seem human).
    # [EN] ⚠ It previously only read 2 entries indirectly through `craftmix.brief()` (the type brief used
    # [EN] for stirring things up),
    # [EN] the `craft_block` path was never wired at all — and "what craft the director should read" had
    # [EN] never been explicitly named.
    'director': ('西方编剧正典', '人物与对话', '场景与空间', '叙事学正典'),
}


#: ★★ **每个职位点名要读的那几条**（2026-10-07 加）。
# [EN] : ★★ **The several entries each role is explicitly told to read** (added 2026-10-07).
#: 为什么要在货架之外再点名：货架只说到"哪一本书"，而一本书里有 8~14 条。
#: 以前取法是"类型卡映射到的 + 货架里文件顺序前三条"，于是 ——
#:   · **场记**（活儿是"每场有没有落点、谁在场上"）拿到的是
#:     人物一句话立起来 / 上场下场都带戏 / 以景写时，也就是**剧作者的写作提示**；
#:     它真正要用的「一场一转变」排在文件第 16 位，永远轮不到。
#:   · **复盘** 只拿到古典章法那一半（起承转合/草蛇灰线/伏脉千里），
#:     而它要评的是"这一段作为一章成不成立"—— 那得看价值转变与人物弧光。
#: 一句话：**手艺是按"这一行"挑的，不是按"这一架"挑的**。
# [EN] : Why name entries beyond the shelf: the shelf only says "which book", and a book has 8~14
# [EN] entries.
# [EN] : The old approach was "those mapped by the type card + the first three files in shelf order",
# [EN] so —
# [EN] : · **Script supervisor** (whose job is "does every scene have a landing point, who is on
# [EN] stage") got
# [EN] : establish a character in one line / entrances and exits both carry drama / use scenery to
# [EN] write time, i.e. **the playwright's writing hints**;
# [EN] :     the "one turn per scene" it actually needs is ranked 16th in the file, never its turn.
# [EN] : · **Retrospective** only got the classical composition half (introduction, development, turn,
# [EN] conclusion / foreshadowing / distant threads),
# [EN] : whereas what it must evaluate is "does this passage hold up as a chapter" — that requires
# [EN] value turns and character arcs.
# [EN] : In one sentence: **craft is chosen by "this line of work", not by "this shelf"**.
#: 硬约束（判据盯着）：这里点到的每一条，**必须属于该职位 `SHELVES` 里的货架**
#: —— 跨架点名等于把"职位读哪本书"这句话变成假的。
# [EN] : Hard constraint (the criterion watches this): every entry named here **must belong to a shelf
# [EN] in that role's `SHELVES`**
# [EN] : — naming across shelves is equivalent to making the statement "which book the role reads"
# [EN] false.
READS: dict[str, tuple[str, ...]] = {
    'settings_room': ('一场一转变', '期待感管理', '里外先分清', '房间是图不是点'),
    'continuity': ('一场一转变', '上场下场都带戏', '群像调度', '走动要有依据',
                   # ★ 2026-10-18（#16 场景连续性）：场记的活就是"上一场没完的那件事
                   #   有没有被带过来"—— 这条手艺 2026-10-18 才补进库里。
                   # [EN] ★ 2026-10-18 (#16 scene continuity): the supervisor's job is exactly "was the
                   # [EN] unfinished thing carried over" -- this entry was only added to the library today.
                   '场与场的缝'),
    # ★★ 剧本审读点名要读的五条（2026-10-08）—— 一条对一类毛病：
    #   「上场下场都带戏」→ 用户报的"突然来了一个人、结果什么都没做"；
    #   「人物一句话立起来」→ "说的话都不个人化"；
    #   「称呼一变关系就变」→ 跑堂把「客官慢用」说给**自家的伙计**（称呼错位）；
    #   「说话方式就是身份」→ "不是人话 / 不像这个人说的"；
    #   「群像靠执念分层」→ "大家各说各的、没有主题"。
    # [EN] ★★ The five entries script review is explicitly told to read (2026-10-08) — one entry per kind
    # [EN] of defect:
    # [EN] "entrances and exits both carry drama" → the user-reported "someone suddenly appears, and does
    # [EN] nothing in the end";
    # [EN] "establish a character in one line" → "what's said is not individualized";
    # [EN] "a change of address changes the relationship" → the waiter saying "enjoy your meal, customer"
    # [EN] to **their own shop hand** (address mismatch);
    # [EN] "manner of speech is identity" → "not human speech / doesn't sound like what this person would
    # [EN] say";
    # [EN] "group portrait layered by obsessions" → "everyone says their own thing, no theme".
    'script_doctor': ('上场下场都带戏', '人物一句话立起来', '称呼一变关系就变',
                      '说话方式就是身份', '群像靠执念分层',
                      # ★ 2026-10-12（用户点名）：审读要**查得出"像不像活人"** ——
                      #   而"整场都在吼"是最容易看出来的那一处假。
                      # [EN] ★ 2026-10-12 (the user named this): the review must be able to **catch "does
                      # [EN] this sound like a live person"** -- and "everyone is shouting the whole scene"
                      # [EN] is the easiest kind of fake to spot.
                      '音量是稀缺的'),
    'props': ('一件小道具承住一切', '以景写时', '里外先分清'),
    'art': ('以景写时', '群像调度', '先有底图再取景', '里外先分清'),
    'publicity': ('期待感管理', '渠道毒点'),
    'stylist': ('一件小道具承住一切', '以景写时'),
    'sound': ('以声写静', '独白节制'),
    'polisher': ('文气', '人物一句话立起来', '独白节制',
                 # ★ 2026-10-07（拆书那一轮）：它要挑"这一句像机器写的"，
                 #   而"像不像人说的"这件事在「人物与对话」那一架里讲得最细。
                 # [EN] ★ 2026-10-07 (the book-deconstruction round): it must pick out "this sentence reads like a
                 # [EN] machine wrote it",
                 # [EN] and "does it sound like what a human would say" is explained in the most detail in the
                 # [EN] "character and dialogue" shelf.
                 '说话方式就是身份', '停顿与不答也是台词', '话长短由处境定',
                 # ★ 2026-10-12：润色的活儿就是挑"这一句像机器写的"，
                 #   而"每句都整整齐齐说完"正是机器最像机器的地方。
                 # [EN] ★ 2026-10-12: polishing is exactly about picking out "this sentence reads like a
                 # [EN] machine wrote it", and "every line tidily finished" is where a machine most looks
                 # [EN] like a machine.
                 '话不是一条直线'),
    'researcher': ('权谋布局', '志怪笔法'),
    # ★ 2026-10-07：编剧组与复盘读「人物与对话」那几条 ——
    #   小说作家管"这个人立不立得住"，剧作者管"这句台词能不能换个人说"，
    #   复盘管"今天的人像不像人"。
    # [EN] ★ 2026-10-07: the writers' room and retrospective read the "character and dialogue" entries —
    # [EN] the novelist handles "does this person hold up", the playwright handles "can this line be said
    # [EN] by someone else",
    # [EN] The review also checks "do today's characters feel like people".
    'novelist': ('起承转合', '期待感管理', '人物弧光', '草蛇灰线',
                 '反差要撞给读者看', '性格靠对外部规则的态度',
                 '说话方式就是身份', '用旁观者拆解代替作者夸',
                 # ★ 2026-10-12 小说作家的两条空间手艺：写环境描写时**先分里外**
                 #   （井在院里、柜台在屋里），写街巷时**按序列交代**。
                 # [EN] ★ 2026-10-12 the novelist's two spatial crafts: **split inside/outside first**
                 # [EN] when writing the setting (the well in the yard, the counter indoors), and
                 # [EN] **describe in sequence** when writing a street.
                 '里外先分清', '街是序列不是点',
                 # ★ 2026-10-12（用户点名）：小说里最容易写成"每句话都对得上"
                 #   —— 那正是念稿。这一条讲**日常就会漏接**。
                 # [EN] ★ 2026-10-12 (the user named this): in a novel it is easiest to write "every line
                 # [EN] gets a reply" -- which is exactly script-reading. This entry is about **everyday
                 # [EN] missed connections**.
                 '不是每句都得接',
                 # ★★★ 2026-10-18（检查表 #10 / #13 / #14）：小说作家是**最终落笔**的人，
                 #   心理距离、闲笔、母题这三样都只在成文那一层才成立
                 #   （导演排戏用不上"这一段的距离是哪一档"）。
                 # [EN] ★★★ 2026-10-18 (checklist #10 / #13 / #14): the novelist is the one who **writes
                 # [EN] it down**; psychological distance, free strokes and motifs only exist at the
                 # [EN] prose layer (a director scheduling scenes has no use for "which distance").
                 '自由间接引语', '闲笔不是废话', '母题回响'),
    'screenwriter': ('一场一转变', '可拍性检查', '上场下场都带戏',
                     '人物一句话立起来',
                     '说话方式就是身份', '弱者用对方的逻辑反打',
                     '群像靠执念分层', '称呼一变关系就变',
                     # ★★ 2026-10-12 剧作家的三条空间手艺（用户点名）：
                     #   「里外先分清」→ 他写的 `场` 必须是"地点·空间"，井归院、柜台归屋；
                     #   「房间是图不是点」→ 室内得说清哪几间、怎么连着；
                     #   「走动要有依据」→ `要点` 里的人物动作要能在地图上走出来。
                     # [EN] ★★ 2026-10-12 the playwright's three spatial crafts (the user named this):
                     # [EN]   "split inside/outside" -> the `场` he writes must be "place·space", the well
                     # [EN]   to the yard, the counter indoors;
                     # [EN]   "rooms are a graph, not points" -> indoors must state which rooms there are
                     # [EN]   and how they connect;
                     # [EN]   "movement must be grounded" -> character actions in `要点` must be walkable
                     # [EN]   on the map.
                     '里外先分清', '房间是图不是点', '走动要有依据',
                     # ★ 2026-10-12（用户点名）：剧作家的活儿有一半是台词，
                     #   而"写出来念着像不像人"就落在**停顿要不要写在纸上**
                     #   与**一次只说一件事**这两条上。
                     # [EN] ★ 2026-10-12 (the user named this): half the playwright's job is dialogue, and
                     # [EN] "does it read like a person when spoken" lands exactly on **whether the pauses
                     # [EN] are written down** and **one thing at a time**.
                     '停顿要落在纸上', '一次说一件事'),
    'reviewer': ('场景=价值转变', '人物弧光', '起承转合',
                 '反差要撞给读者看', '口癖来自职业与处境',
                 # ★ 2026-10-12（用户点名"说话习惯由性格决定"）：复盘看的是
                 #   "今天的人像不像人" —— 而人**对谁说话就换一副样子**，
                 #   这一点最能说明他有没有被人格化地写。
                 # [EN] ★ 2026-10-12 (the user named "speech habits follow character"): the retrospective
                 # [EN] asks "did today's people feel like people" -- and a person **changes shape
                 # [EN] depending on whom they speak to**, which best shows whether they were written as a
                 # [EN] person.
                 '对谁说话就换个样子',
                 # ★★★ 2026-10-18（#7 轮次与反应 / #4 欲望与需求）：复盘要看的是
                 #   "今天这一段有没有落点" —— 而落点正是"他吃完亏之后想了什么、
                 #   改了主意没有"。这两条 2026-10-18 才补进库里。
                 # [EN] ★★★ 2026-10-18 (#7 scene->sequel / #4 want vs need): the retrospective asks
                 # [EN] "did this stretch have a landing point" -- and that is exactly "what he thought
                 # [EN] after taking the hit, and did he change his mind". Both were added today.
                 '反应与决定', '欲望与需求'),
    # ★★ 演员读的六条 —— 全是"**怎么说**"，一条"故事怎么讲"都没有。
    #   这是有意的：演员手上多一条结构手艺，他就会想替编剧干活
    #   （"这一拍该有个转变"），而不是把这一拍的话说好。
    # [EN] ★★ The six lines the actor reads -- all about "**how to say it**", not one about "how the story
    # [EN] is told".
    # [EN] This is intentional: if the actor has one more structural skill in hand, he will want to do the
    # [EN] writer's job
    # [EN] ("this beat should have a turn"), instead of delivering this beat's lines well.
    'actor': ('说话方式就是身份', '停顿与不答也是台词', '话长短由处境定',
              '口癖来自职业与处境', '弱者用对方的逻辑反打',
              '性格靠对外部规则的态度',
              # ★★ 2026-10-12（用户点名："很多 AI 生成的"对白**没有卡顿、从不犹豫**、
              #   还**很容易吼**）—— 这两条正是治它的：一条管**话里的毛边**，
              #   一条管**音量**。演员是真正开口的人，这两条不给他，等于没人管。
              # [EN] ★★ 2026-10-12 (the user named this: "much AI-generated" dialogue **has no stumbles,
              # [EN] never hesitates**, and **shouts easily**) -- these two are exactly the cure: one
              # [EN] governs **the frayed edges in speech**, the other governs **volume**. The actor is the
              # [EN] one who actually speaks; not giving him these two means no one is watching them.
              '话不是一条直线', '音量是稀缺的',
              # ★★★ 2026-10-18：演员只从「叙事学正典」里拿这**两条** ——
              #   `邻接对` 治"别人问他他不答、自己另开一个话题"（用户报的各说各话）；
              #   `场与场的缝` 治"换场之后当什么都没发生过"。
              #   ⚠ 其余八条（反应与决定 / 欲望与需求 / 十五节拍…）**故意不给**：
              #     给了它就会去排结构、替编剧干活，而不是把这一拍的话说好。
              # [EN] ★★★ 2026-10-18: the actor takes only **these two** from the narratology shelf --
              # [EN]   `adjacency pair` fixes "he was asked and didn't answer, opened his own topic";
              # [EN]   `the seam between scenes` fixes "after a scene change, as if nothing happened".
              # [EN]   ⚠ The other eight are **deliberately withheld**: with them it would arrange
              # [EN]   structure and do the writer's job instead of delivering this beat's lines.
              '邻接对', '场与场的缝'),
    # ★★ 导演读的四条（2026-10-07）：**结构两条 + 人两条** ——
    #   它验算的是"每一拍变了什么"（结构），挑事派活时面对的是"人"。
    #   这是三人小组里唯一"两头都要"的职位：另两位各管一头（作家管故事、
    #   剧作者管可拍），导演管**这一场成不成立**。
    # [EN] ★★ The four lines the director reads (2026-10-07): **two structural + two about people** --
    # [EN] What it verifies is "what changed in each beat" (structure); when assigning work it faces
    # [EN] "people".
    # [EN] This is the only position in the three-person group that "needs both ends": the other two each
    # [EN] own one end (the writer owns the story,
    # [EN] the playwright owns shootability), while the director owns **whether this scene holds up**.
    'director': ('场景=价值转变', '期望鸿沟',
                 '反差要撞给读者看', '用旁观者拆解代替作者夸',
                 # ★ 2026-10-12 导演的三条空间手艺：
                 #   "谁从哪儿走到哪儿有依据" / "谁看得见谁" / "这一处热闹还是僻静"
                 #   —— 用户点名"导演和剧作家在设计人物动作的时候要时时刻刻参考地图"。
                 # [EN] ★ 2026-10-12 the director's three spatial crafts:
                 # [EN]   "how someone walks from A to B is grounded" / "who can see whom" / "is this
                 # [EN]   place busy or quiet"
                 # [EN]   -- the user named "the director and playwright must constantly consult the map when
                 # [EN]   designing character movement".
                 '走动要有依据', '看得见是算得出来的', '热闹与僻静由连通决定'),
}


#: 各职位**最多**读几条（默认 3）。
# [EN] : the **maximum** number of lines each position reads (default 3).
#: ★ 为什么演员要更多：它的手艺是"怎么说"，六条各管一面（身份 / 停顿 /
#   长短 / 口癖 / 弱势时的打法 / 性格怎么写），按 3 条截掉的话，
#   读到的永远只是文件顺序前三条 —— 那正是"按架读而不是按行读"的老毛病。
# [EN] : ★ Why the actor needs more: its craft is "how to say it", and the six lines each cover one
# [EN] facet (identity / pause /
# [EN] length / verbal tic / how to fight when weak / how to write personality); if truncated to 3
# [EN] lines,
# [EN] what is read is always just the first three in file order -- that is exactly the old problem of
# [EN] "reading by rack instead of by line".
# ★★ 2026-10-12 上调六个职位的额度：加了「场景与空间」那一架、各人又多点了几条
#   名之后，**新条目会把老条目挤出去**（额度是总数，不是"额外再加"）——
#   那等于拆东墙补西墙。所以：**prefer 多了几条，额度就加几条**。
#   ⚠ 2026-10-12 复测补正：`craft_block` 收尾那句是 `picked[:max(limit, len(prefer))]`,
#     所以**prefer 本身截不掉**（额度只要不超过 prefer 条数，加不加它都一样）——
#     这段"加额度"实际保住的是 **prefer 之外的补位余量**；真正会把老条目弄丢的
#     只有"点名表被改"。下面的额度仍按同数上调（保持余量不变），但别再照字面理解。
#   novelist      5 → 7    （+2：里外先分清 / 街是序列不是点）
#   screenwriter  5 → 8    （+3：里外先分清 / 房间是图不是点 / 走动要有依据）
#   director      4 → 7    （+3：走动要有依据 / 看得见是算得出来的 / 热闹与僻静由连通决定）
#   art           4 → 5    （+2，只加 1 是为它留一条映射来的）
#   settings_room 4 → 5    （+2，同上）
#   continuity    4 → 5    （+1，同上）
#   props 不动（+1 之后 3 条，还留得住一条映射来的）
# [EN] ★★ 2026-10-12: raised the quota for six positions. After adding the "scene and space" shelf and
# [EN] naming a few more entries per person, **the new entries push the old ones out** (the quota is a
# [EN] total, not an add-on) -- that is robbing Peter to pay Paul. So: **as many more named entries, that
# [EN] many more quota.**
# [EN]   novelist      5 -> 7    (+2)
# [EN]   screenwriter  5 -> 8    (+3)
# [EN]   director      4 -> 7    (+3)
# [EN]   art           4 -> 5    (+2; only +1 to keep one mapped entry)
# [EN]   settings_room 4 -> 5    (+2, same)
# [EN]   continuity    4 -> 5    (+1, same)
# [EN]   props unchanged (+1 makes 3, still keeps one mapped entry)
# ★★ 2026-10-12（第二次上调）：加了「**怎么说才像活人**」那一组（六条），
#   各人的点名也跟着多了几条；额度**同步加上同样的数字**，
#   为的是让"**prefer 之外还能再补几条**"这个**余量**保持不变。
#   actor         6 → 8    （+2：话不是一条直线 / 音量是稀缺的）
#   screenwriter  8 → 10   （+2：停顿要落在纸上 / 一次说一件事）
#   novelist      7 → 8    （+1：不是每句都得接）
#   script_doctor 5 → 6    （+1：音量是稀缺的）
#   polisher      4 → 5    （+1：话不是一条直线）
#   reviewer      4 → 5    （+1：对谁说话就换个样子）
# ⚠⚠ **机制别再记错**（2026-10-12 实测纠正）：`craft_block` 末尾那一句是
#   `picked[:max(limit, len(prefer))]` —— **prefer 是无上限的**，
#   额度压到多小都截不到它（实测 `limit=3` 时演员的八条点名仍全部拿到）。
#   额度管的只是"**prefer 之外**还能不能再补"（mapped / 货架兜底）。
#   所以"新条目把老条目挤出去"只可能发生在**点名表本身被改**（`READS` 里删了老条目）
#   的时候 —— 判据 A3 钉的是那个，A3b 钉的是"prefer 不受额度截断"这个机制。
# [EN] ★★ 2026-10-12 (second raise): added the "**how to speak like a live person**" group (six
# [EN] entries); each person's named list grew too, so the quota **rises by the same amount**,
# [EN] in order to keep the **margin** of "how many more can be filled in beyond `prefer`" unchanged.
# [EN]   actor         6 -> 8    (+2)
# [EN]   screenwriter  8 -> 10   (+2)
# [EN]   novelist      7 -> 8    (+1)
# [EN]   script_doctor 5 -> 6    (+1)
# [EN]   polisher      4 -> 5    (+1)
# [EN]   reviewer      4 -> 5    (+1)
# [EN] ⚠⚠ **Do not misremember the mechanism** (corrected by measurement on 2026-10-12): the last line
# [EN] of `craft_block` is `picked[:max(limit, len(prefer))]` -- **`prefer` has no cap**, no matter
# [EN] how small the quota is it cannot be cut (measured: with `limit=3` the actor still received all
# [EN] eight named entries). The quota only governs "how many more can be filled in **beyond
# [EN] `prefer`**" (mapped / shelf fallback). So "new entries push old ones out" can only happen when
# [EN] **the named list itself is edited** (an old entry deleted from `READS`) -- criterion A3 nails
# [EN] that, and A3b nails the mechanism "prefer is not truncated by the quota".
READ_LIMIT: dict[str, int] = {'actor': 8, 'novelist': 8, 'screenwriter': 10,
                              'polisher': 5, 'reviewer': 5, 'director': 7,
                              'art': 5, 'settings_room': 5, 'continuity': 5,
                              # ★ 审读点名了 5 条（一条对一类毛病），
                              #   按 3 条截掉就等于有一类毛病没人管。
                              # [EN] ★ The review named 5 lines (one line per type of flaw),
                              # [EN] truncating to 3 lines means one type of flaw has no one watching it.
                              'script_doctor': 6}


#: ★★ **三人小组**：他们决定"这个故事怎么讲"（用户 2026-10-07 点名的那三位）。
# [EN] : ★★ **The three-person group**: they decide "how this story is told" (the three named by the
# [EN] user on 2026-10-07).
#: 他们拿到的"同类书写法"是**完整版**（模块 + 节奏 + 立人 + 文风 + **不要照搬什么**），
#: 别的职位拿到的是**压缩版**（只给模块名与怎么做）。
#: 为什么区别对待：写法经验是**用在"怎么讲"那一层**的 ——
#: 场记拿它没用（它只查连戏对不对），而作家/剧作者/导演拿它正是为了优化故事。
#: `settings_room` 是"导演·作家·剧作者三方会审"，**本质是同一个组合**，所以也在内。
# [EN] : The "how similar books are written" they get is the **full version** (modules + rhythm +
# [EN] character building + style + **what not to copy**),
# [EN] : other positions get the **compressed version** (only module names and how to do it).
# [EN] : Why the difference: writing experience is **used at the "how to tell it" layer** --
# [EN] : the script supervisor has no use for it (it only checks whether continuity is correct), while
# [EN] the writer/playwright/director use it precisely to optimize the story.
# [EN] : `settings_room` is a "director - writer - playwright three-way joint review", **essentially
# [EN] the same combination**, so it is included too.
WRITERS: frozenset[str] = frozenset({'novelist', 'screenwriter', 'director',
                                     'settings_room'})


# ══════════════════════════════════════════════════════════════════════
#  可选后端：MuMuAINovel（外部写小说服务，见 `novelservices/`）
# [EN] Optional backend: MuMuAINovel (external novel-writing service, see `novelservices/`)
# ══════════════════════════════════════════════════════════════════════
#  两条**跨职位**的写法约束（2026-10-10 用户点名要的）
# [EN] Two **cross-position** writing constraints (named by the user on 2026-10-10)
# ══════════════════════════════════════════════════════════════════════
# 用户原话：
#   ①「我想让小说作家调用 MuMuAINovel 写小说的时候，每段故事先把场景描述的很清楚，
#      按照给美术 Agent 使用可以清晰画出地图为准」；
#   ②「你看下写小说的时候是否可以配合一下编剧和导演的需求，让小说适合改编电影电视剧」。
# [EN] User's exact words:
# [EN] (1) "When I want the novel writer to call MuMuAINovel to write a novel, each story paragraph
# [EN] should first describe the scene very clearly,
# [EN] with the standard that it can be given to the art Agent to draw a map clearly";
# [EN] (2) "See whether when writing the novel it can coordinate with the needs of the playwright and
# [EN] director, so the novel is suitable for adaptation into film and TV".
# 所以这两段**不是"文风建议"，是下游职位真的要用的输入**：
#   场景段 → 美术（画地图 / 定机位）、道具（这一场该有什么）、导演（镜头怎么摆）；
#   可拍性 → 剧作者（能不能分场）、演员（有没有可演的台词与动作）。
# 两段都写成**可核对的条目**：含混的形容词（"写清楚一点"）对模型没有约束力，
# 而"谁靠门、门在东侧、灯笼挂在檐下"这种是能照着画的。
# [EN] So these two paragraphs are **not "style suggestions", they are inputs the downstream positions
# [EN] really use**:
# [EN] scene paragraph -> art (draw map / set camera positions), props (what this scene should have),
# [EN] director (how to place the camera);
# [EN] shootability -> playwright (can it be broken into scenes), actor (are there actable lines and
# [EN] actions).
# [EN] Both paragraphs are written as **checkable items**: vague adjectives ("write it more clearly")
# [EN] have no binding force on the model,
# [EN] whereas "who leans on the door, the door is on the east side, the lantern hangs under the eaves"
# [EN] can be drawn from directly.
SCENE_CARD_RULES = """── 场景要先写清楚（**给美术画地图用**）──
每一段戏**开头先交代清楚你在哪儿**，标准是"别人照着你写的就能把这张地图画出来"：
  · 这是**哪一个地方**：用设定里已有的地名，不要另起新名；
  · 人**在什么位置**：谁靠门、谁在灶边、谁在楼上（写相对方位，别只写"在屋里"）；
  · 这地方**长什么样**：门/窗/楼梯/桌案/器物各在哪一侧，屋里屋外一眼能看见什么；
  · **光从哪来、什么时辰**：灯笼 / 天光 / 灶火，亮到什么程度；
  · 这一段里**谁动了、往哪动**：进出、上楼、挪东西，都要有方向。
  · ★★ **屋里与院里分开写**（用户 2026-10-12 点名的硬要求）：
    **见天的东西**（井、树、影壁、水缸）**只能在院子里**；**有顶的东西**
    （柜台、条案、灶台）**只能在屋里**。**写出一口井，就必须写出一处院子**
    （井在院里打水，院墙把它与街隔开）。⚠ 屋里两间之间**隔着墙** ——
    要过去得经过院子或廊下，别让人一步跨过一整座楼。
⚠ 不许用"气氛肃杀""充满压迫感"这种**画不出来**的话代替方位与器物。"""

FILMABLE_RULES = """── 顺手让它**能拍**（编剧与导演要用）──
这一段既要能读，也要能**分场、分镜**。所以：
  · **一场一事**：一段戏发生在**一个地方、一段连续时间**里；换地方 / 换时间就另起一段；
  · **露在外面的要写足**：看得见的东西、听得见的声音、做得出的动作 ——
    写**具体的**（"手停了一下"、"把碗推远"、"没接那句话"、"指节发白"），
    不写**评价**（"他心里很乱"、"气氛紧张"）—— 后者读者看不见，等于没写。
    这一层是给"能拍"用的；
  · ★★ **心里那一层也要给，只是要装在它自己的地方**
    （用户 2026-10-14：「正常小说…应该有…心理活动」）：
    人物的想法、盘算、犹豫、忍住没说出口的那句，
    写进**心声**那一层（`display/script.ASIDE`，「心声 · 内心活动，不外泄」）——
    **不要**混进上面那层"看得见的描写"里。混在一起，
    导演就分不清"这句是要拍的、还是只在纸上的"，
    而读者也分不清"这是他做的，还是他想的"。
    ⚠ **一整段只有动作、半点内心都没有，读起来是干的** ——
    该想的时候要给，别把人物写成只会做动作的木偶；
  · **人在说话就写出话**：对白用「」，写成**能让人念出来**的话；
    不要用"两人交谈了几句"这种转述；
  · **别用"与此同时"跳来跳去**：一件事说完再说下一件。"""


# ── 2026-10-12 新增：**怎么说话才像个活人**（跨职位硬约束）──
# 用户原话（意思）：真人说话会犹豫、对别人说的话不是每句都回应、速度不会太快、
# 说话习惯由性格决定；而"很多 AI 生成的"对白**没有任何卡顿、速度很快、从不犹豫**，
# 还**很容易吼** —— 一听就不是真人。
# ★ 这一段与上面两段**并列**（都是跨职位的写法硬约束），但它管的是**另一个层面**：
#    · `SCENE_CARD_RULES` 管**看得见的东西**（场景能不能画出来）；
#    · `FILMABLE_RULES` 管**拍不拍得到**（一场一事、只写拍得到的）；
#    · 这一段管**听得出来的东西** —— 同一句话从活人嘴里出来是什么样
#      （卡顿 / 漏接 / 音量 / 长度 / 停顿）。
#   ⚠ 前两段管"写什么"，这一段管"怎么说"。三个层面缺一层，台词都还是"字被念出来"。
# ★ 为什么写成**可机械核对**的形态：这五条各自对应一种**一眼能看出来的假**
#   （句句都整整齐齐 / 句句都被接住 / 处处都在吼 / 一口气说三段 / 没有一处停顿），
#   所以它既能写进提示词，也能在剧本审读那一步**逐条查**。
# ★ 与「停顿与不答也是台词」的分工（这一条最容易和它打架，注释在这里钉死）：
#   那条讲**有秘密时**的不答（戏剧手段，用在"他有东西瞒着"），
#   这一条讲**日常就会漏接、就会卡**（真实质感，没有秘密也照样发生）。
# [EN] -- Added 2026-10-12: **how to speak like a live person** (cross-position hard constraint) --
# [EN] The user's meaning: real people hesitate, do not answer every line, do not talk fast, and their
# [EN] speech habits follow their character; whereas "much AI-generated" dialogue has **no stumbles at
# [EN] all, is fast, never hesitates**, and **shouts easily** -- it does not sound human.
# [EN] ★ This paragraph sits **side by side** with the two above (all are cross-position wording hard
# [EN] constraints), but it governs **another layer**:
# [EN]   · `SCENE_CARD_RULES` governs **what can be seen** (can the scene be drawn);
# [EN]   · `FILMABLE_RULES` governs **what the camera can catch** (one thing per scene, only shootable
# [EN]   things);
# [EN]   · this paragraph governs **what can be heard** -- what the same sentence sounds like coming out
# [EN] of a live person (stumbles / missed connections / volume / length / pauses).
# [EN] ⚠ The first two govern "what to write"; this one governs "how to say it". Missing any one of the
# [EN] three layers leaves the dialogue as "characters reading text aloud".
# [EN] ★ Why it is written in a **mechanically checkable** shape: each of the five corresponds to a kind
# [EN] of **fake you can spot at a glance** (every line neat / every line answered / shouting
# [EN] everywhere / three things in one breath / not a single pause), so it can go into the prompt and
# [EN] also be checked **item by item** at the script-review step.
# [EN] ★ Its division of labour with "pause and not answering are also lines" (the easiest one to
# [EN] collide with, nailed down here in the comment):
# [EN] that one is about not answering **when there is a secret** (a dramatic device, for "he is hiding
# [EN] something"); this one is about **everyday missed connections and stumbles** (real texture, which
# [EN] happens with no secret at all).
LIVE_SPEECH_RULES = """── 说话要**像个活人**（这一条与"能拍"同等硬）──
真人说一句话，和"把字念出来"是两件事。按下面五条自查 —— 每条都在防一种**一眼能看出来的假**：
  · **话不是一条直线**：人一开口会**找词、重复半个字、改口、说一半自己停下**
    （「我……我不是那个意思。」「你说他——等等，你说谁？」）。
    ⚠ 只落在**他心虚、没想到、在算要不要说真话**的那一处，**别每句都卡**
    （句句结巴是另一种假）。
  · **不是每句都得接**：真人对话里**大段是没接上的** —— 听岔了、只听进去半句、
    顺着自己那半句往下说、用一个「嗯」把话头摁回去、干脆装没听见。
    一场戏**不必让每句台词都得到回应**；每句都严丝合缝接住的对话 = 两个人在念稿。
    ⚠ **但一场戏不能一次都不接**（2026-10-20 实测补的边界，别删）：
      有人问了三次、你三次都把话挡回去（「坐」「喝茶」「你再看仔细些」），
      那不是含蓄 —— 是**对方白问了三次**，戏在原地不动，读者会替他不耐烦。
      **一场戏至少要有一处真正的回答**：给出一条对方原本不知道的信息
      （不是态度、不是评语、不是又一句反问）。
      挡回去可以用一次、两次；**第三次还在挡，就必须换成回答**。
  · **音量是稀缺的**：**默认平常声量**。吼、喊、尖声是**动作**，不是标点 ——
    用得少才有用，用了要有代价（旁人回头看、他事后哑了、他自己后悔）。
    ⚠ **激动不等于吼**：激动可以是**压低声音**、**说得更快**、**忽然停下**。
    台词里**不写"吼道""厉声"**，就默认是平常声音。
  · **一次说一件事**：真人不一口气讲三件事。**短句、有断、话里有缝**
    （说一句、停、再说一句）。一口气把一整段说完整 = 念稿。
  · **停顿与口气要写在纸上**：该停的地方（省略号 / 破折号 / 圆括号里的一个动作）、
    该轻该重、该快该慢，**各写一个词就够**（「低着声」「急急地」）。
    ⚠ 只写**做得到**的提示，不写"充满感情地"这种没法执行的。
    不写停顿，念出来就是一路平快地念到底 —— 那正是"一听就是 AI"最显眼的地方。
  · ★★★ **能不说就不说**（2026-10-28 作者点名）：一句话若用**动作、表情、环境、
    手里的东西**就能说清，就不要让它从嘴里出来。台词只用来做"人跟人之间的事"
    （试探、讨价、遮掩、答应、拒绝）；**来历、因果、背景不靠角色交代** ——
    让读者自己看见（一张对不上的账页、井沿上一圈湿印子、他把碗推远），
    比让人说出来强十倍。
    ⚠ 这不是"少写台词"：是**每一句台词都要有用**。只说信息、不带立场的那段，
      就是编辑圈的"互相念说明书"。
  · ★★★ **别拿副词盖章**（2026-10-28）：不写「他严肃地说道」「她冷冷地说」。
    **「××地说 / ××地道」这种句式，一章最多两处**；要让人知道他是怎么说的，
    就写**他说话时手上、脸上在干什么**（把烟掐了、眼睛没抬、说到"当年"两个字时停了一下）。
    **"严肃""冷冷""意味深长""淡淡"这类副词一律删** —— 让读者从话里自己品，
    不用作者贴标签。⚠ 也别改用"他说道""她问道"凑数：标签换十个花样，还是标签。
  · ★★★ **遮名要分得出谁**（2026-10-28）：把这段对话的人名全部遮住，
    读者还认得出谁在说 —— 认不出，就是两个人一个腔调（同一种句长、同一种客气、
    同一种完整），必须重写：换句长、换称呼、换他躲闪的方式。"""


def live_speech_block() -> str:
    """「怎么说才像活人」那一段（**跟着开关走**，关掉返回空串）。

    ★ 为什么抽成一个函数而不是三处各写一遍 `if CFG.b(...)`：
      判据要能**行为级**证明"这个开关真的管用"（开 → 有 / 关 → 没有）。
      三处各写一遍的话，判据只能去正则会话源码（那正是本项目一直在防的
      "字符串哨兵"），抽出来之后一行就能验。

    ★ 为什么挂了**三处**（小说作家 / 剧作者 / 演员），而不是只给演员：
      用户点名的是"剧本生成 小说编写 演员表演"**三条**都要改 ——
      台词不是在演员那一层才第一次出现的，它在作家和剧作者手里就已经写定了。
      只叮嘱演员 = 让最后一个人去补前两个人留下的坑。

    ⚠ 演员那一处**不调这个函数**：演员拿到的是**行动纪律的形态**
      （`agent/core.py` 的 `_tail` 与 `prompts/agent_decide_tail.txt` 里那两条），
      因为它离输出最近，写成长段落反而会被它忽略（见那两处的注释）。
    
        English:
    The "how to speak like a live person" paragraph (**follows the switch**; returns an empty string
    when off).
        ★ Why extract it into a function instead of writing `if CFG.b(...)` in three places:
          the criterion must be able to **prove behaviourally** that this switch really works
          (on -> present / off -> absent). Written three times, the criterion could only regex the
          source (exactly the "string sentinel" this project keeps guarding against); extracted, one
          line verifies it.
        ★ Why it is mounted in **three places** (novelist / playwright / actor) rather than only the
          actor: the user named **all three** -- "script generation, novel writing, actor performance".
          A line does not first appear at the actor layer; it is already fixed in the writer's and
          playwright's hands. Telling only the actor = making the last person fill the pits left by
          the first two.
        ⚠ The actor's spot **does not call this function**: what the actor gets is the **form of
          action discipline** (the two clauses in `agent/core.py`'s `_tail` and in
          `prompts/agent_decide_tail.txt`), because it sits closest to the output and a long paragraph
          would simply be ignored (see the comments there).
    """
    try:
        return LIVE_SPEECH_RULES if CFG.b('CREW_LIVE_SPEECH') else ''
    except Exception:                                            # noqa: BLE001
        return ''


# ════════════════════════════════════════════════════════════════════════════════
#  ★★★ 2026-10-28「叙事层」：机器味的**大头不在词句，在结构**
# [EN] ★★★ 2026-10-28 "narrative layer": the bulk of the machine smell is **structure, not wording**
# ════════════════════════════════════════════════════════════════════════════════
#  来源：StoryScope（Russell et al. 2026，arXiv:2604.03136v6）—— 61,608 篇小说对照
#  （人写一半 / 五个大模型写一半），304 个叙事特征、XGBoost + SHAP。
#  两条最硬的结论：
#    ① 只让分类器看**叙事结构**（不看用词、不看句法）⇒ 准确率仍有 **93.2%**；
#    ② 把 AI 的表面词句**彻底改干净** ⇒ 识别率只从 95.5% 掉到 **93.9%（1.6 个点）**。
#  ⇒ 我们前面做的「说话指纹」「副词盖章」都在**最外那层皮**上，
#    值得做，但它只值那 1.6 个点。**里面这层才是大头。**
#  工具来源：GitHub Nanako0129/sepia（MIT，v0.4.0）的 `references/narrative-pass.md` /
#  `references/rubric.md`（30 项 core features，本文所有 human/AI 数字都出自它）。
#
#  ⚠ 规则是 Sepia 依该研究做的**设计推论**；研究本身没有测过"先改架构再改文风"这个顺序。
# ════════════════════════════════════════════════════════════════════════════════
ANTI_FINGERPRINT_RULES = """── 别把"像人"改成"另一种机器腔"（**叙事层**，四条）──

下面四条**不是文风，是故事的骨**。有实测对照：把机器写的稿子表面词句
全部换干净，机器味只掉 1.6 个点 —— 真正藏不住的是这四样。
⚠ 所以**改词没用，得改结构**；也别指望这四条能靠"换个说法"蒙过去。

1. **情绪别只会写身子**（这一条最要紧，实测差距最大）。
   机器 81% 把情绪全写成身子上的反应（喉咙发紧、手心出汗、胸口发堵），
   真人只有 38% 这么写；而真人 29% 会**直接说出来**（"他怕了""她不高兴"），
   机器只敢 8%。
   ⇒ 四种写法**混着用**，别只认一种：
     · **他在干什么**（把碗推远、没接那句话、转身去添柴）—— 用得最多；
     · **直接说出来**（"他有点怕"）—— 真人常这么写，**别忌讳**；
     · **身子上的反应**（喉咙发紧）—— **全书只留一两个最重的那处**，别场场都来；
     · **看不出他什么心思** —— 也行，读者自己会补。
   ⚠ "要让人看见、不要说出来"这句话被用成了教条：**全篇没有一个情绪
     被写出来**，本身已经是最重的机器腔。

2. **天气就是天气**。
   别场场让雨、风、灯映着人物的心境（真人 3.6 分，机器 4.1 分）。
   该下雨就下雨，跟谁高不高兴没关系；**凑巧撞上一次**可以，回回都撞就是套。
   **气味更要省** —— 机器写嗅觉写了 82%（真人 57%），
   它是机器散文最爱用的那点"高级感"，省着点。

3. **别把意思点破**。
   故事讲完，不要跳出来替读者总结（"他终于明白……""说到底，人都是这样"
   "真正的勇气不是不害怕，而是……"）—— 真人 52% 忍不住，机器 77%。
   把意思留在人物的**选择和后果**里，让读者自己读出来。
   角色之间也别把话聊成**讲道理**（机器 59%，真人 34%）：
   他们该争的是一件具体的事（这笔账算不算、这碗茶谁端），不是"什么叫义"。

4. **给一处真东西**。
   真人 47% 会在故事里点出一件**真有的**东西（一本真书、一个真地名、
   一块真招牌、一味真药），机器只有 24% —— 它不敢指名，
   只敢说"一位名家""一首老曲"。
   ⇒ 这一章里挑**一件真有的**点出来，写清楚它是什么，别含糊带过。
   ⚠ **必须是真的、写对的**；想不起就照实留白，**不许编** ——
     编一个假的真名，比不写更坏。

── 两条"别改过头"（这一层最容易被改坏，务必记住）──
· **对准真人的样，不是对准机器的反面**。
  真人写短句没错，但不是通篇三五个字 —— 真人自己写的东西也有长有短。
  一见机器爱长句就把全文剁碎，等于给自己造了一枚**新的指纹**；
  那种"句句都短、碎得像电报"的稿子，比机器写的还不像人话。
· **一章只挑三五处改**，剩下的**故意留着**。
  处处都改 = 处处都整齐，**整齐本身就是机器腔**。
  上面四条也是：一章挑两三条做透就够，别四条全上、别段段都上。"""


def anti_fp_block() -> str:
    """叙事层那一段（**跟着开关走**，关掉返回空串）。

    ★ 为什么抽成函数：判据要能**行为级**证明"这个开关真的管用"
      （开 → 有 / 关 → 没有），抽出来之后一行就能验
      （见 `live_speech_block()` 那条注释，同一条道理）。
    ⚠ 为什么**不挂演员**：这一段是长段落，而演员离输出最近，
      长段落会被它忽略（项目的实测结论）⇒ 只挂作家与编剧这两层。
      演员那一层对应的形态是 `agent/core.py` `_tail` 里的短句纪律。

        English:
    The narrative-layer paragraph (**follows the switch**; empty string when off).

        ★ Why a function: the criterion must be able to **prove behaviourally** that the switch
          works (on -> present / off -> absent); extracted, one line verifies it (same reasoning
          as `live_speech_block()`).
        ⚠ Why it is **not** mounted on the actor: this is a long paragraph and the actor sits
          closest to the output, so long paragraphs get ignored (measured in this project) =>
          mount only on novelist and playwright. The actor's form of the same idea is the short
          discipline in `agent/core.py`'s `_tail`.
    """
    try:
        return ANTI_FINGERPRINT_RULES if CFG.b('CREW_ANTI_FP') else ''
    except Exception:                                            # noqa: BLE001
        return ''


# ══════════════════════════════════════════════════════════════════════
#  2026-10-10 新增：三条**跨职位**的硬约束（都来自外部调研，见 developers/docs/外部借鉴/）
# [EN] Added 2026-10-10: three **cross-position** hard constraints (all from external research, see [EN] developers/docs/外部借鉴/)
# ══════════════════════════════════════════════════════════════════════
#: ① **记忆是不可信史料**（第 05 类第 3 条 · 借鉴 `a16z-infra/ai-town`，MIT）。
# [EN] : (1) **Memory is unreliable historical material** (Category 05 Item 3 · borrowed from
# [EN] `a16z-infra/ai-town`, MIT).
#: 逐字搬它 `convex/agent/conversation.ts` 的两句，理由与它一样：
#: 记忆是**从过去几天的正文里抽出来的**，而正文里出现的任何一句话都可能
#: 是"某个人物说的假话、某个反派的挑拨、一段被引用的传言"。
#: 把记忆当"事实"直接喂进去，等于**让人物自己给自己下指令** ——
#: 一句剧情里的"你这店明天就得关"会被当成真的背景设定。
# [EN] : Copy verbatim its two sentences from `convex/agent/conversation.ts`, for the same reason as
# [EN] it:
# [EN] : memory is **extracted from the main text of the past few days**, and any sentence appearing in
# [EN] the main text may
# [EN] : be "a lie told by some character, an instigation by some villain, a quoted rumor".
# [EN] : Feeding memory in directly as "fact" is equivalent to **letting characters give instructions
# [EN] to themselves** --
# [EN] : a line in the plot like "your shop has to close tomorrow" will be taken as a real background
# [EN] setting.
#: ⇒ 用法：记忆/前情**一律放进独立的 user 消息里**，并用这条把它包住；
#:    **不要**把它混进 system 提示词（混进去就等于承认它是规则）。
# [EN] : => Usage: memory/previous context **must always go into a separate user message**, wrapped by
# [EN] this line;
# [EN] :   **do not** mix it into the system prompt (mixing it in equals admitting it is a rule).
MEMORY_TRUST_RULES = """── 关于下面的回忆（**重要**）──
下面这些是**回忆**，不是事实：它们是你自己记下来的、可能记错，也可能是当时
听别人转述的、甚至是有人**故意说给你听的假话**。
请把回忆当作**参考**，不要当作绝对真理；两处冲突时，以**你眼前正在发生的事**
与**上面的规矩**为准。"""

#: ② **同场多角色别串台**（第 05 类第 3 条下半 · 同源 AI Town `stopWords`）。
# [EN] : (2) **Multiple characters in the same scene must not cross-talk** (second half of Category 05
# [EN] Item 3 · same source AI Town `stopWords`).
#: 它原来的做法是给每个角色加 `stopWords`（`"人物甲 to 人物乙:"`），
#: 让模型**输出到别人名字时停下**。本项目的场景是一拍一拍推的、不是一次生成
#: 多人对话，所以这里落成更贴合的形态：**在提示词里点明"你只能说自己的话"**，
#: 并给出替别人代言的正确做法。
# [EN] : Its original approach was to add `stopWords` to each character (`"Character A to Character
# [EN] B:"`),
# [EN] : making the model **stop when it outputs someone else's name**. This project's scenes are
# [EN] advanced beat by beat, not generated all at once
# [EN] : as multi-person dialogue, so here it lands in a more fitting form: **state in the prompt "you
# [EN] can only say your own words"**,
# [EN] : and give the correct way to speak on someone else's behalf.
SPEAKER_ISOLATION_RULES = """── 你是**一个人**，不是旁白 ──
只写**你自己**说的话和你**自己做**的动作。
**不要替别人说话、不要替别人做决定、不要用旁白口气总结整场戏**
（那会让好几个人在同一拍里说出同一个意思）。
想表达"对方在做什么"，就写**你看得见的那一部分**（他端着碗没动）。"""

#: ③ **可拍性硬规则**（第 01 类第 1、3 条 · 借鉴 `Open-Write`，Apache-2.0，自己重写）。
# [EN] : (3) **Shootability hard rules** (Category 01 Items 1 and 3 · borrowed from `Open-Write`,
# [EN] Apache-2.0, rewritten ourselves).
#: 两条都是**机械规则**，越机械越好用 —— 因为它们能在提示词里逐条写死，
#: 也能在审读环节逐条查：
#:   · **camera-test（镜头看不见就不写）**：凡是镜头拍不到的（心里怎么想、
#:     别人背后怎么做），一律不写；要写就写它露在外面的样子。
#:   · **knowledge-delta（每句台词先问"他何时学到"）**：一个人说出某件事之前，
#:     必须有**他获得这个消息的那一刻**。没有那一刻的台词，就是编剧在借角色的嘴
#:     说给观众听（这是"人设崩坏"最常见的成因）。
# [EN] : Both are **mechanical rules**, and the more mechanical the more useful -- because they can be
# [EN] written into the prompt item by item,
# [EN] : and also checked item by item in the review stage:
# [EN] : · **camera-test (if the camera cannot see it, do not write it)**: anything the camera cannot
# [EN] capture (what someone thinks inside,
# [EN] : what others do behind their backs) is never written; if written, write only how it shows on
# [EN] the outside.
# [EN] : · **knowledge-delta (for each line of dialogue, first ask "when did he learn it")**: before a
# [EN] person says something,
# [EN] : there must be **the moment he obtained this information**. A line without that moment is the
# [EN] writer borrowing the character's mouth
# [EN] :     to speak to the audience (this is the most common cause of "character collapse").
SCREEN_HARD_RULES = """── 两条硬规则（**逐条能查，不是风格建议**）──
① **镜头里的东西要写具体**：只写"看得见的动作 / 听得见的话 / 现场有的东西"，
   而且写成**看得见的那个样子**（手在袖子里攥紧、茶端起来又放下）。
   ⚠ 2026-10-14 更正（用户：「正常小说…应该有…心理活动」）：
   原来这一条写的是"**镜头看不见就不写**"，于是**心里那一层被整段掐掉了**。
   现在分清楚：**"看得见的那层"写具体**（这条管的就是它），
   而**人物心里那层要写进"心声"**（`display/script.ASIDE`）——
   两样各归各的地方，不是"不许写"，是"**别写错地方**"。
② **每句台词先问"他什么时候知道的"**：一个人说出某件事之前，戏里必须有
   他**获得这件事的那一刻**。没有那一刻，这句台词不许写 ——
   那是编剧借角色的嘴对观众说话，也是"人设崩坏"最常见的来源。"""

#: ⑤ **对话与场景推进**（2026-10-16 加，用户报"生成的小说不像人话"：
#:   角色复读机 + 场景原地打转 + 谶语填词）。这三类是"生成里最假"的，
#:   属正确性不是风格，所以**不另设开关**（与 `SCREEN_HARD_RULES` 同一条口径，
#:   见 1525 行：正确性硬规则关掉没有正当理由）。
#: [EN] (5) **Dialogue and scene progression** (added 2026-10-16, user reported "the generated
#: [EN] novel doesn't sound human": character repeat machine + scene stalling + oracle padding).
#: [EN] These three are "the fakiest in generation"; they are correctness, not style, so **no separate
#: [EN] switch** (same calibration as `SCREEN_HARD_RULES`, see line 1525).
REPEAT_RULES = """── 对话与场景推进（**角色复读机、原地打转，是生成里最假的一种**）──
① **同一角色不许反复说同一句、或只换几个字又是一句**：每人每开口都得带新内容。
   像"俺某地哩！俺要换衣裳"这种口头禅，说一次是性格，连说七八次就是复读机 ——
   读者一眼出戏。要表现"他急着去收拾"，写一次动作就够（人已经拎着包袱往门外挪），
   不用反复喊。
② **别给人物配一句"人设口号"让他反复念**：什么"傻子账上不糊涂""井茶入梦，楼欠因果未销"，
   念一遍是意境，段段都念就是念咒。神秘感靠**具体动作和细节**撑，不靠重复口号。
③ **场景必须往前走**：一段里要有"信息 / 关系 / 情绪 / 动作"里至少一项在推进。
   不准全员站着各念各的、谁也不接谁的话、什么事都没发生就翻篇 ——
   哪怕只推进一点点：一个眼神变了、一句没说完的话、一件对不上的旧物、一个没答上来的问题。
④ **每句台词都要"承重"**：要么透露点什么、要么改变点什么、要么让人更懂这人。
   光为了"显得有对话"而写的闲扯，删掉它故事反而更干净。"""

#: ④ **反思回路**（第 05 类第 5 条 · 借鉴 `noahshinn/reflexion`，MIT）。
# [EN] : (4) **Reflection loop** (Category 05 Item 5 · borrowed from `noahshinn/reflexion`, MIT).
#: 它卖的从来不是"多反思"，而是**反思的形状**：
#: 不是"下次注意点"，而是 **诊断原因 → 给出具体动作计划**。
#: 所以这里把两段话固定下来 —— 少了后一段，反思就退化成一句正确的废话。
# [EN] : What it sells has never been "reflect more", but **the shape of reflection**:
# [EN] : not "be more careful next time", but **diagnose the cause -> give a concrete action plan**.
# [EN] : So here the two paragraphs are fixed -- without the latter paragraph, reflection degenerates
# [EN] into a correct but useless sentence.
REFLECT_INSTRUCTION = """不只是"下次注意"，要写成两段：
① **诊断**：这次哪里不对、**为什么会这样**（指到具体那一句或那个人）；
② **动作**：下一次**具体怎么做**（写成能照着做的一两件事，不写"加强""注意"）。"""


# ══════════════════════════════════════════════════════════════════════
#  ⚠ 这里是**唯一**把"配置 / 桥接层 / 剧组"接起来的地方 ——
#    `novelservices/mumu_bridge.py` 故意不认识 `CFG`（它要能独立跑），
#    剧组这条链故意不认识 HTTP。胶水只在这一段，将来要换服务也只改这里。
# [EN] ⚠ This is the **only** place connecting "config / bridge layer / crew" --
# [EN] `novelservices/mumu_bridge.py` deliberately does not know `CFG` (it must be able to run
# [EN] standalone),
# [EN] the crew chain deliberately does not know HTTP. The glue is only in this passage; if the service
# [EN] is swapped in the future, only this place changes.
def _mumu_enabled_for(key: str) -> bool:
    """这一步该不该交给 MuMuAINovel？**每次都现读配置**（改完不用重启）。

    ★★★ 2026-10-27：**MOCK（演示）模式不许碰外部服务**。
      日志里那句「演示模式：零网络、零成本、可复现」是一个**承诺**，
      而 MuMuAINovel 这条路原来**不认 MOCK** ——
      实测 `tools/verify_setting_layers.py`（登记在 LOGIC 组，号称零花费）
      跑一遍就**真去 MuMuAI 建了个批量任务**，还花了 40 多秒。
      ⇒ 判据组是"每次都跑"的，一支判据偷偷花钱，回归就废了。
      （`novelservices/mumu_bridge.py` 故意不认识 `CFG` —— 那是对的，
        胶水本来就只该在 `crew/agents.py` 这一段。）

        English:
    Should this step be handed to MuMuAINovel? **Read the config fresh every time** (no restart
    needed after changes).
    ★★★ 2026-10-27: **MOCK (demo) mode must not touch external services**.
    [EN] The log line "demo mode: zero network, zero cost, reproducible" is a **promise**, and the
    [EN] MuMuAINovel path did not know about MOCK --
    [EN] measured: `tools/verify_setting_layers.py` (registered in the LOGIC group, which claims zero
    [EN] cost) really created a batch task on MuMuAI and spent over 40 seconds.
    [EN] => The criterion group "runs every time"; one criterion secretly spending money ruins the
    [EN] regression. (`novelservices/mumu_bridge.py` deliberately does not know `CFG` -- that is
    [EN] right; the glue is only supposed to live in this passage of `crew/agents.py`.)
    """
    try:
        if CFG.b('MOCK_LLM'):
            return False
        if not CFG.b('MUMU_ENABLED'):
            return False
        if key == 'novelist':
            return CFG.b('MUMU_FOR_NOVELIST')
        if key == 'export':
            return CFG.b('MUMU_FOR_EXPORT')
        return False
    except Exception:                                        # noqa: BLE001
        return False


def _with_degrade(why: str, degrade: str) -> str:
    """把"为什么没用成 MuMuAINovel"并进失败原因里。

    ★ 一定要并进去：不写的话，用户看到的是「没写出样章」，
      而真正的信息是「MuMuAINovel 超时了 → 回退自写也失败了」。
      少了后半句，查起来要一轮一轮试。
    
        English:
    Fold "why MuMuAINovel wasn't used" into the failure reason.
        ★ Must be folded in: without it, the user sees "no sample chapter written",
          while the real information is "MuMuAINovel timed out → fallback self-write also failed".
          Without the second half, debugging takes round after round of trial.
    """
    if not degrade:
        return why
    return f'{why}（本步原想走 MuMuAINovel，未成功：{degrade}）'


def _history_novel(novel_dir, *, before_day: int = 0, limit: int = 1800) -> str:
    """**历史小说**：前面几天已经写好的**正文**（不是前情提要那种摘要）。

    ★★★ 用户 2026-10-21 点名的输入：「开始阶段写小说用**设定集和历史小说**，
      导出阶段用**设定集 历史小说和本地推演过程**」。
      ⚠ 在此之前喂进去的是 `ctx.recap()` —— 那是**摘要**（"阿九发现荷包在袖"），
        摘要给的是"发生了什么"，而写作真正要学的是**上一章怎么写的**：
        句子多长、视角贴着谁、怎么处理心声、这一段用什么口气。
        实测同一个模型，喂摘要写出来是流水账，喂前文正文才有文气。

    取法：`当天故事.md`（按天累积的可读稿，`## 第 N 天` 分节）→ 按节切，
    取 `before_day` 之前的、**最后** `limit` 字（越近的越像"接着往下写"）。
    读不到就返回空串（**不编**），调用方据此不加这一段。
    
        English:
    **History novel**: the prose **already written** for previous days (not a recap summary).
        ★★★ The input the user named on 2026-10-21: "writing at the start uses **the setting book and
          the history novel**; export uses **the setting book, the history novel and the local
          derivation process**".
        ⚠ Before this, what was fed in was `ctx.recap()` -- a **summary** ("Chen Wang found the
          purse in his sleeve"). A summary gives "what happened", but what writing actually needs to
          learn is **how the last chapter was written**: sentence length, whose head the viewpoint
          sits in, how inner voice is handled, what tone a paragraph carries. Measured: the same
          model produces a ledger with a summary and only finds a voice with the preceding prose.
        How: `当天故事.md` (the day-accumulated readable draft, split by `## 第 N 天`) -> take the
        sections before `before_day`, keep the **last** `limit` characters (the nearest is what
        "continues onward" looks like). Returns an empty string when unreadable (**no inventing**);
        the caller then omits the section.
    """
    try:
        p = Path(str(novel_dir or '')) / '当天故事.md'
        if not str(novel_dir or '').strip() or not p.is_file():
            return ''
        body = p.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''
    # 按 `## 第 N 天` 切节；只要 `before_day` 之前的（当天还没写，不能算历史）
    parts = re.split(r'(?m)^##\s*第\s*(\d+)\s*天', body)
    chunks: list[tuple[int, str]] = []
    for i in range(1, len(parts) - 1, 2):
        try:
            d = int(parts[i])
        except (TypeError, ValueError):
            continue
        if before_day and d >= int(before_day):
            continue
        txt = str(parts[i + 1] or '').strip()
        if txt:
            chunks.append((d, txt))
    if not chunks:
        return ''
    out = ''
    for _d, txt in reversed(chunks):
        if len(out) + len(txt) + 2 > max(200, int(limit)):
            # 放不下整节 ⇒ 只取这一节的**尾部**（离"现在"最近的那一段）
            room = max(0, max(200, int(limit)) - len(out) - 2)
            if room > 120:
                out = txt[-room:] + ('\n' + out if out else '')
            break
        out = txt + ('\n' + out if out else '')
    return out.strip()


#: 这一轮里"已经试过拉起服务"没有（避免每次写稿都重试一遍，白等几十秒）。
#: ⚠ 只在一个进程里记一次：用户手动起服务之后照样能用（`service_status` 每次现探）。
# [EN] Whether "starting the service" has already been attempted in this round (avoids retrying and
# [EN] waiting tens of seconds for every chapter). ⚠ Recorded once per process: after the user starts
# [EN] the service by hand it still works (`service_status` probes fresh every time).
def _sample_words() -> int:
    """**开演前那份样章**该写多少字（0 配置 = 跟随剧组自己的上限）。

    ★★★ 为什么需要它（2026-10-21，用户问「一开始写的小说该是什么程度」时查出来的）：
      系统对"样章"的定义是**质感样本**（`CREW_STORY_MIN~MAX` = 180~600 字），
      理由写在 `Novelist` 的注释里：「分拍是结构，样章是质感 —— 先有'这一天读起来
      是什么样'，改写成分场时才有东西可拆」。
      但走外部服务那条路借用了 `MUMU_TARGET_WORDS`（2500 = **导出重写整章**的字数），
      **两条路差 4~14 倍**，而产物都交给同一个编剧。

      ⚠ 这不是"长一点更好"：样章越长，编剧拆出的拍越细（带更多具体动作），
        演员从"自己决定这一拍做什么"退化成"照着拍子填台词" —— 正好压掉用户要的灵活性。
      ⚠ 所以默认值是 **0 = 跟随 `CREW_STORY_MAX`**，不是"再给一个 2500"。

        English:
    How long the **pre-show sample chapter** should be (0 config = follow the crew's own ceiling).
        ★★★ Why it exists (found 2026-10-21 while the user asked "what degree is right for the
          opening novel"): the system defines the sample as a **texture sample**
          (`CREW_STORY_MIN~MAX` = 180-600 chars), for the reason in `Novelist`'s docstring:
          "shot-splitting is structure, the sample is texture". But the external-service path
          borrowed `MUMU_TARGET_WORDS` (2500 = the **export rewrite** length) -- **4-14x apart**,
          with both products going to the same screenwriter.
        ⚠ Not "longer reads better": the longer the sample, the finer the beats the screenwriter
          cuts, and actors degrade from "decide what this beat does" to "fill in lines per beat" --
          exactly killing the freedom the user wants.
        ⚠ Hence the default is **0 = follow `CREW_STORY_MAX`**, not "another 2500".
    """
    try:
        v = int(CFG.i('MUMU_SAMPLE_WORDS') or 0)
    except Exception:                                        # noqa: BLE001
        v = 0
    if v > 0:
        return v
    try:
        return max(120, int(CFG.i('CREW_STORY_MAX') or 600))
    except Exception:                                        # noqa: BLE001
        return 600


_MUMU_START_TRIED = {'done': False}


def _ensure_mumu(BR) -> tuple[bool, str]:
    """**服务不在就把它拉起来** —— 导出/写稿优先走外部服务，回退只在它真的起不来时发生。

    ★★★ 2026-10-21 架构调整（用户原话）：
      「导出的时候既然已经用外部服务，则**优先使用外部服务**，只有外部服务
        MuMuAINovel 缺失无法启动的时候才回退到内部代码生成小说」。

      改之前的行为是**政策反了**：`MUMU_FOR_EXPORT=true` 只表示"允许用"，
      服务没起就当场 `_fail` → 调用方静默回退内部稿（日志一行 warning）。
      实测：配置全是开的，跑了五轮 bench，**每一轮导出的都是内部稿** ——
      用户看到的一直是自己不喜欢的那种文字，而"开关开着"让人以为在用外部服务。

      ⇒ 现在：允许用 = **必须用**。顺序是
         ① 现探（1.5 秒）；② 不在就 `start_service()` 拉起（最多等 `start_timeout`）；
         ③ 还起不来才回退，并且**把原因带进回退通知**（不静默）。
      ⚠ 拉起的等待有上限、且一个进程只试一次：真没装/端口被占时不能把每次写稿
        都拖成"先等两分钟"。
    
        English:
    **Start the service if it isn't up** -- export/writing prefers the external service; fallback
    happens only when it genuinely cannot start.
        ★★★ Architecture change on 2026-10-21 (the user's words): "since export already uses the
          external service, **prefer the external service**; fall back to in-house generation only
          when MuMuAINovel is missing and cannot start".
          Before this the policy was **inverted**: `MUMU_FOR_EXPORT=true` only meant "allowed to
          use", so with the service down it `_fail`ed on the spot and the caller silently fell back
          to the in-house draft (one warning line). Measured: every config was on, five bench rounds
          ran, and **every single export was the in-house draft** -- the user kept reading the text
          they disliked while "the switch is on" suggested otherwise.
          => Now: allowed = **must use**. Order: ① probe (1.5s); ② if down, `start_service()`
          (wait up to `start_timeout`); ③ only if that fails, fall back **with the reason attached**
          (never silently).
        ⚠ The start wait is bounded, and attempted once per process: if it is genuinely not
          installed or the port is taken, every chapter must not become "wait two minutes first".
    """
    st = BR.service_status()
    if st.ok:
        return True, ''
    if _MUMU_START_TRIED['done']:
        return False, f'服务没在跑，且这一轮已经试过拉起（{st.reason}）'
    _MUMU_START_TRIED['done'] = True
    _LOG.warning('写小说服务没在跑（%s）→ 按"优先外部服务"的架构，现在尝试拉起它',
                 st.reason)
    try:
        ok_start, why = BR.start_service(timeout=float(CFG.i('MUMU_TIMEOUT_SECONDS') or 900) / 6)
    except Exception as e:                                   # noqa: BLE001
        return False, f'拉起服务时出错：{e!r}'
    if not ok_start:
        return False, f'服务起不来：{why or "未知原因"}'
    st2 = BR.service_status()
    if st2.ok:
        _LOG.info('写小说服务已拉起，本次导出走外部服务')
        return True, ''
    return False, f'拉起后仍不可用（{st2.reason}）'


#: **实病**：确定性高、改了不会伤风格 —— 值得退回重写。
#: ⚠ 划分标准不是"严重程度"，而是**"改它会不会伤到作者要的风格"**：
#:   · 元叙述 / 拥挤段 / 感知自洽 / 问答悬空 —— 逻辑与结构错误，任何风格下都是错的；
#:   · 篇幅不足 —— 不是风格问题，是**没写出来**（实测 94 字被当成"干净"交过一次）。
# [EN] **Real defects**: unambiguous, fixing them never hurts the intended style.
# [EN] The split is not severity but "does fixing it damage the author's style":
# [EN] meta narration / crowded clauses / perceptual contradiction / unanswered question are wrong
# [EN] under any style; "too short" is not style, it means nothing was written.
HARD_CLASSES: tuple[str, ...] = ('元叙述', '拥挤段', '感知自洽', '问答悬空', '篇幅不足')

#: **候选**：可能是作者要的风格。
#: ★★★ 2026-10-21（用户问"推演还有足够灵活性吗"时查出来的）：
#:   这几类**不能**当成"毛病"退回重写 ——
#:   · `重复` / `道具循环`：那篇专业分析报告明说"重复变奏手法纯熟"是**优点**，
#:     病与不病的分界是**可删除性**（删掉读者损失什么），而那是**语义判断**，
#:     确定性检测器数不出来（实测：7 次有推进的变奏与 7 次原地打转，检测器判一样多）；
#:   · `憋气段` / `平铺段`：长句节奏与报告体，都是**文风选择**。
#:   ⇒ 它们进提示词当**参考**、进日志当记录，但**不单独触发退回重写**。
#:     这与 `crew/global_checks.py` 里"只出候选、不进自动修复"是同一条纪律：
#:     **可数 ≠ 该自动改**。
# [EN] **Candidates**: may be the author's intended style.
# [EN] ★★★ 2026-10-21 (found while answering "is the simulation still free enough?"): these must
# [EN] **not** be sent back as "defects" -- the professional review called the repetition-variation
# [EN] technique a **strength**, and the real dividing line is **deletability** (what does the reader
# [EN] lose), which is a **semantic** judgement a deterministic detector cannot make (measured: seven
# [EN] advancing variations and seven identical repeats score the same). Long-sentence rhythm and
# [EN] report-style paragraphs are stylistic choices. So they become **reference** in the prompt and
# [EN] a log line, never a standalone trigger for a rewrite -- same discipline as "detect-only,
# [EN] never auto-fix" in `crew/global_checks.py`: **countable != should be auto-changed**.
SOFT_CLASSES: tuple[str, ...] = ('憋气段', '平铺段', '重复', '道具循环')


def issue_split(counts: dict) -> tuple[int, int]:
    """把计数表拆成 `(实病数, 候选数)`。不认识的类**算实病**（宁可多退回一次）。

    ⚠ 不认识就当归实病，是有意的保守选择：新加一类检测器时，最坏结果是"多退回一遍"（花钱），
      而反过来（默认不退回）会让真毛病静默进成品。
    [EN] Split counts into (real defects, candidates). Unknown classes count as **real defects**
    [EN] (fail conservative): a new detector's worst case is one extra rewrite (costs money),
    [EN] whereas defaulting the other way lets real defects ship silently.
    """
    hard = soft = 0
    for k, v in (counts or {}).items():
        n = int(v or 0)
        if n <= 0:
            continue
        if k in SOFT_CLASSES:
            soft += n
        else:
            hard += n
    return hard, soft


def fix_list_line(counts: dict) -> str:
    """把我们**自己的检查清单**数出来的毛病，写成能照着改的几条（给外部服务看）。

    ★★★ 这是"检查归自己、写作归服务"的接口（用户 2026-10-21 点名）。
      退回给服务的话**必须可执行**：
        ❌ 「写得更好一点」「加强细节」——它只能原地再猜一遍；
        ✅ 「憋气段 2 处（长句过半）、道具循环「壶」3 次」——它知道该拆哪一段、
           该换哪个道具。
      所以这里只报**项目自己的检测器数得出来的类**（`prose_flow.prose_issue_count`），
      一条一类，带数量与一句怎么改。判官类的（打转/自洽）不进这张单子 ——
      它们会抖，抖着退回等于让服务猜。

    ★★★ **2026-10-21 分两段写**（这一条是"推演灵活性"那轮查出来的）：
      原来所有类平铺成一张单子，服务读到就以为**每一条都是硬要求**，
      于是把"长句多""有重复"这些**可能是作者风格**的东西也一并改掉 ——
      实测里第 2 遍字数从 3417 涨到 4580、毛病反而更多，正是在追这些候选类。
      ⇒ 现在分「必须改」（实病）和「可以自己判断」（候选）两段，
        并明写候选"改不改由你定，别为了它把戏改散"。**这是保住风格的关键一步。**

    ★ 为什么每条都要写"怎么改"而不只写数量：只给数字它会选择"删掉那一段"，
      而删字数是硬约束（`verdict` 会拦）。给方向它才会改写而不是删除。

        English:
    Turn what **our own checklist** counted into a few actionable lines (for the external service).
        ★★★ The interface of "checking is ours, writing is the service's" (named 2026-10-21):
          what goes back must be **executable**, never "write it better" that it can only guess at.
        ★★★ **Written in two sections since 2026-10-21** (found while auditing simulation freedom):
          everything used to be one flat list, so the service read **every** item as a hard
          requirement and sanded down "long sentences" / "has repetition" -- which may be the
          author's style. Measured: pass 2 grew from 3417 to 4580 characters with *more* defects,
          exactly because it was chasing those candidates. => Now split into "must fix" (real
          defects) and "your call" (candidates), and the candidates explicitly say "changing or not
          is up to you; do not scatter the scene for their sake". **This is the key step that keeps
          the style alive.**
        ★ Each line carries a direction, not just a count: given only a number it deletes the
          paragraph, and word count is a hard constraint (`verdict` blocks it). A direction makes it
          rewrite instead of delete.
    """
    if not counts:
        return ''
    how = {
        '憋气段': '长句太多（一段里长句过半），把它拆成短句，别整段压成一句',
        '平铺段': '全是"主语+动作+结果"的报告句，挑一处铺开（带触感、声音、对方反应）',
        '重复': '同一句/同一手法反复出现，只留一次，其余换成别的写法（不要删情节）',
        '拥挤段': '一个句号里塞了太多件事（上限两件），把第三件另起一句',
        '元叙述': '混进了剧本提示或作者旁白，改成小说里的叙述句',
        '感知自洽': '有句子前后矛盾（看不见的写了、不知道的写了），按视角改顺',
        '问答悬空': '有人问了没被回答，补一句应答或明确写他为什么不答',
        '道具循环': '同一件东西反复"续上—耗掉"，换一样东西承担同一个作用',
        '篇幅不足': '这一版太短了（不像一章），把该发生的写足，不许靠摘要过关',
    }
    hard_rows: list[str] = []
    soft_rows: list[str] = []
    for k, v in (counts or {}).items():
        n = int(v or 0)
        if n <= 0:
            continue
        row = f'· {k} {n} 处：{how.get(k, "按本项目的规矩改掉")}'
        (soft_rows if k in SOFT_CLASSES else hard_rows).append(row)
    _nl = chr(10)
    parts: list[str] = []
    if hard_rows:
        parts.append('── 必须改的（这几条在任何风格下都是错的）──')
        parts.extend(hard_rows)
    if soft_rows:
        parts.append('── 你可以自己判断的（可能正是这一章要的效果，别为了它把戏改散）──')
        parts.extend(soft_rows)
        parts.append('⚠ 这一段**不是硬要求**：如果这几处是这一章想要的效果（比如有意反复、'
                     '刻意的长句），就照原样留着；只在你觉得"这确实读着累"的地方动一点。')
    if not parts:
        return ''
    parts.append('── 共通的两条 ──')
    parts.append('⚠ 这不是让你重写一篇新的：情节、人物、台词都还在，只照上面几条改。')
    parts.append('⚠ **不许靠删减来过关**（字数、台词条数是硬要求）。')
    return ('── 上一版没通过的地方（**按这几条改，别的地方照原样**）──' + _nl
            + _nl.join(parts))


def write_check_retry(BR, make_task, *, tag: str = '正文',
                      min_chars: int = 0,
                      should_stop: 'Callable[[], bool] | None' = None
                      ) -> tuple[str, str]:
    """**服务写 → 我们自己的清单数 → 不过就带着意见退回 → 两版取更好的**。

    ★★★ 为什么只有这一份实现（2026-10-21）：用户的原话是
      「把写小说和导出小说的 Reflection 过程中的**写作过程**调用 MuMuAINovel 服务，
       **检查部分用自己的检查列表**」。**两个阶段**（开演前写样章 / 收工导出重写）
      要做的是同一件事 —— 写归服务、查归自己、不过退回。写成两段就一定会分叉
      （MEMORY 的老账："同一件事两处实现是万恶之源"），所以只有这一个函数，
      两处各传自己的 `make_task`。

    三件必须守住的事（每条都对应一个实测过的坑）：
      ① **退回的话必须可执行**：`fix_list_line` 只报我们检测器数得出来的类，
         一条带数量 + 一句怎么改；不给"写得更好"这种它只能猜的话；
      ② **不许无条件采用新稿**：两版按 `verdict.better()` 比（多目标 + 硬约束），
         否则"改一遍"可能把好的改坏（本项目踩过：修好 A 弄坏 B）；
      ③ **不许白跑**：清单数出 0 处就停；数出来但写不成清单也停；
         预算 `MUMU_EXPORT_TRIES` 由配置定（默认 2）。

    参数
    ----
    BR        桥接层模块（`novelservices.mumu_bridge`）。
    make_task `(fix_list: str) -> ChapterTask`：每次重写重建一份任务（章号由桥接层自己算）。
    tag       进日志用。

    返回 `(正文, 没成功的原因)`；成了就 `(正文, '')`。
    
        English:
    **Service writes -> our own checklist counts -> send back with the list -> keep the better version.**
        ★★★ Why a single implementation (2026-10-21): the user's words are "route the **writing**
          part of writing/export reflection through MuMuAINovel; keep **checking** on our own
          checklist". **Both stages** (the pre-show sample chapter and the wrap-up export rewrite)
          do the same thing -- service writes, we check, send back if it fails. Two copies would
          inevitably diverge (an old MEMORY debt: "two implementations of one thing is the root of
          all evil"), so there is one function and each caller passes its own `make_task`.
        Three things that must hold (each maps to a measured pitfall):
          ① **What goes back must be executable**: `fix_list_line` reports only classes our detectors
             can count, one line with a count and a direction; never "write it better" that it can
             only guess at;
          ② **Never adopt the new draft unconditionally**: compare with `verdict.better()`
             (multi-objective + hard constraints), otherwise "one more pass" can make things worse
             (this project has measured fixing A and breaking B);
          ③ **Never waste a pass**: stop when the checklist counts zero; also stop when it counts
             something but no list can be written; budget comes from `MUMU_EXPORT_TRIES` (default 2).
        Params:
          BR        bridge module (`novelservices.mumu_bridge`).
          make_task `(fix_list: str) -> ChapterTask`: rebuild a task per pass (the bridge computes
                    the chapter number itself).
          tag       for the log.
        Returns `(body, reason it failed)`; on success `(body, '')`.
    """
    from crew import prose_flow as _PF
    from crew import verdict as _V
    try:
        tries = max(1, int(CFG.i('MUMU_EXPORT_TRIES')))
    except Exception:                                        # noqa: BLE001
        tries = 1
    best: tuple[object, str] | None = None
    fix = ''
    last_why = '未成功'
    for attempt in range(1, tries + 1):
        # ★★★ 2026-10-21（用户：「你把收尾时间放长」—— 查下来真因不是慢，是**停止没被尊重**）：
        #   实测日志：`阶段「novelist」用时 52.3s（失败）` → 回退外部服务 →
        #   第 1 遍 52s → 退回重写 → 第 2 遍 74s ⇒ **点停止之后又写了 3 分钟**。
        #   用户看到的"收尾特别久"，其实是"停止之后还在写样章"，收尾根本没开始。
        #   ⇒ 每一遍**开始之前**问一次"要不要停"，要停就立刻带着已有的那一版返回。
        #   ⚠ 保留 `best`：已经写好的那一版不能因为停止而丢掉（那是白花钱）。
        #   ⚠ 不中断**正在跑**的那一次调用：`generate_chapter` 是同步的桥接调用，
        #     硬杀会留下服务端的空章节记录（`trailing_empty_numbers` 那边有代价）。
        # [EN] ★★★ 2026-10-21 (user: "make the wrap-up time longer" -- the root cause was **stop not
        # [EN] being respected**, not slowness): measured log: `阶段「novelist」用时 52.3s（失败）` ->
        # [EN] fall back to the external service -> pass 1 52s -> send back -> pass 2 74s => **three more
        # [EN] minutes of writing after stop was clicked**. What the user perceived as "wrap-up takes
        # [EN] forever" was "it is still writing the sample chapter"; wrap-up had not even started.
        # [EN] => Ask "should we stop?" **before each pass**; if so, return immediately with whatever
        # [EN] version we already have.
        # [EN] ⚠ Keep `best`: a finished version must not be thrown away by a stop (that money is spent).
        # [EN] ⚠ Do not interrupt the **in-flight** call: `generate_chapter` is a synchronous bridge call
        # [EN] and hard-killing it leaves an empty chapter row on the service side.
        if attempt > 1 and should_stop is not None:
            try:
                _halt = bool(should_stop())
            except Exception:                                # noqa: BLE001
                _halt = False
            if _halt:
                _LOG.info('%s：用户点了停止 → 不再重写（留下已有的那一版）', tag)
                break
        try:
            task = make_task(fix)
        except Exception as e:                               # noqa: BLE001
            return '', f'拼任务失败：{e!r}'
        r = BR.generate_chapter(task)
        if not r.ok:
            last_why = r.reason or '未成功'
            _LOG.warning('%s 第 %d/%d 遍没成（%s）%s', tag, attempt, tries, last_why,
                         '→ 用之前那一版' if best else '')
            continue
        text = str(r.text or '')
        try:
            counts = _PF.prose_issue_count(text)
            total = _PF.issue_total(counts)
        except Exception:                                    # noqa: BLE001
            counts, total = {}, 0
        # ★★★ **太短不算过关**（2026-10-21 真跑踩到）：实测服务端偶尔只还回 94 字，
        #   而"我们的清单"数出 **0 处** —— 短到检测器什么都抓不到，于是它被当成"干净"，
        #   就这么交了。这是 MEMORY 里那条"满分可疑"的又一例：**没有毛病 ≠ 写够了**。
        #   ⇒ 按目标字数的比例卡下限（`_NOVEL_MIN_RATIO` 同款思路，这里用 0.4：
        #     1500 字目标 ⇒ 少于 600 字就当没写出来）。
        #   ⚠ 把它算成"毛病"而不是"失败"：这样才能走"退回重写"那条路，
        #     而"失败"会直接回退到内部稿（用户要的是外部服务，不是内部稿）。
        # [EN] ★★★ **Too short does not pass** (hit in a real run on 2026-10-21): the service
        # [EN] occasionally returned only 94 characters, and **our checklist counted 0** -- too short
        # [EN] for any detector to catch, so it passed as "clean" and shipped. Another case of
        # [EN] MEMORY's "a perfect score is suspicious": **no defects != wrote enough**.
        # [EN] => Enforce a floor as a ratio of the target (same idea as `_NOVEL_MIN_RATIO`; 0.4 here:
        # [EN] a 1500-word target means anything under 600 counts as not written).
        # [EN] ⚠ Count it as a **defect**, not a failure: that routes it into "send it back",
        # [EN] whereas a failure would fall back to the in-house draft (the user wants the service).
        try:
            _want = int(task.target_words or 0) or int(CFG.i('MUMU_TARGET_WORDS') or 2500)
        except Exception:                                    # noqa: BLE001
            _want = 2500
        # ★★★ 2026-10-21：**"多短算没写出来"由调用方定，不在这里硬算比例**。
        #   为什么：两个用途的合理长度根本不同 ——
        #     · 导出重写：一整章（2500 目标，0.4 倍 ≈ 1000 字下限）；
        #     · 开演前样章：**质感样本**（180~600 字），剧组自己的宽容下限是
        #       `CREW_STORY_MIN_FLOOR`（80 字）。
        #   用同一个 0.4 倍去卡，样章会被要求 240 字以上 —— 而剧组说 180 字就够。
        #   ⇒ 传 `min_chars` 就按它；不传才退回 0.4 倍（导出重写沿用旧行为）。
        #   ⚠ 这意味着"篇幅下限"这个口径现在只有一处实现、两个入口，
        #     不会再出现"两条路的接受标准不一样"（这正是我刚查出的那种 bug）。
        # [EN] ★★★ 2026-10-21: **the caller decides "how short means not written"**; do not
        # [EN] hard-code a ratio here. The two uses have genuinely different lengths: export rewrite
        # [EN] is a whole chapter (2500 target, 0.4x = 1000 floor); the pre-show sample is a
        # [EN] **texture sample** (180-600) whose own tolerant floor is `CREW_STORY_MIN_FLOOR` (80).
        # [EN] Applying one 0.4x rule would demand 240+ from the sample when the crew says 180 is
        # [EN] enough. => `min_chars` wins when passed; otherwise keep the 0.4x behaviour for exports.
        # [EN] ⚠ So "length floor" has exactly one implementation and two entry points -- no more
        # [EN] "the two paths accept different lengths" (exactly the bug just found).
        _floor = int(min_chars or 0) or max(200, int(_want * 0.4))
        _too_short = len(text) < _floor
        if _too_short:
            counts = dict(counts or {})
            counts['篇幅不足'] = 1
            total = _PF.issue_total(counts)
            _LOG.warning('%s：只还回 %d 字（目标 %d，下限 %d）→ 当没过（这算实病，会退回重写）',
                         tag, len(text), _want, _floor)
        try:
            sc = _V.Score.of(text)
        except Exception:                                    # noqa: BLE001
            sc = None
        # ★★★ **太短的稿子不许当"更好的那一版"**（2026-10-21 判据当场抓到）。
        #   一开始这里是无条件比较的，结果"240 字的碎句"赢过了"816 字的完整段落"——
        #   因为 `Score.of` 只看**毛病数**，而短稿什么毛病都摊不上，字数缩水它看不见。
        #   我虽然把"篇幅不足"算进了 `counts`，但那是**我自己数的**，`Score.of` 不知道。
        #   ⇒ 太短的直接不进候选：它不算一版稿子，只算"这次没写出来"。
        # [EN] ★★★ **A too-short draft must not be "the better version"** (caught by the criterion
        # [EN] on 2026-10-21). This used to compare unconditionally, and "240 characters of chopped
        # [EN] sentences" beat "816 characters of full paragraphs" -- because `Score.of` only sees
        # [EN] **defect counts**, and a short draft cannot carry any; it is blind to word-count
        # [EN] shrinkage. I did add "too short" to `counts`, but that is **my own count** and
        # [EN] `Score.of` knows nothing about it.
        # [EN] => Too-short drafts are not candidates at all: not a draft, just "nothing written".
        if sc is not None and not _too_short and (best is None or _V.better((sc, text), best)):
            best = (sc, text)
        _hard, _soft = issue_split(counts)
        _LOG.info('%s 第 %d/%d 遍：%d 字，清单数出 %d 处（实病 %d / 候选 %d）%s',
                  tag, attempt, tries, len(text), total, _hard, _soft,
                  f'（{counts}）' if total else '')
        if total <= 0:
            break                                            # 干净了，不用再退
        # ★★★ **只有"实病"才退回重写**（2026-10-21，查"推演灵活性"时定的口径）。
        #   剩下的都是**风格候选**（重复 / 道具循环 / 长句节奏 / 报告体）——
        #   它们病与不病的分界是**可删除性**，那是语义判断，确定性检测器本来就分不出来
        #   （实测：7 次有推进的变奏与 7 次原地打转，检测器判成一样多）。
        #   ⇒ 拿它们当"毛病"退回，等于把作者想要的风格往回修。
        #     实测代价也很具体：第 2 遍字数从 3417 涨到 4580，毛病反而更多 ——
        #     它在追这些候选，越追越偏（另一次：2145→2116 字，憋气段 5→4 但新增自洽 1）。
        #   ⚠ 候选类**不丢**：它们照样进日志、照样写进下一次的清单（见下面的 fix_list_line），
        #     只是**不再单独触发一次重写**。
        # [EN] ★★★ **Only "real defects" trigger a rewrite** (decided 2026-10-21 while auditing
        # [EN] simulation freedom). The rest are **style candidates** (repetition / prop cycles /
        # [EN] long-sentence rhythm / report style). Whether they are defects is decided by
        # [EN] **deletability**, a semantic judgement a deterministic detector cannot make (measured:
        # [EN] seven advancing variations and seven identical repeats score the same).
        # [EN] => Sending them back as "defects" sands down the style the author wanted. The measured
        # [EN] cost is concrete: pass 2 grew from 3417 to 4580 characters with more defects -- it was
        # [EN] chasing candidates and drifting (another run: 2145 -> 2116, long spans 5 -> 4 but one
        # [EN] new contradiction).
        # [EN] ⚠ Candidates are **not dropped**: they still go to the log and into the next pass's
        # [EN] list (see `fix_list_line`); they just never trigger a rewrite on their own.
        if _hard <= 0:
            _LOG.info('%s：只剩 %d 处**风格候选**（无实病）→ 不退回，保留这一版的笔法',
                      tag, _soft)
            break
        if attempt >= tries:
            _LOG.warning('%s：写满 %d 遍仍有 %d 处实病 / %d 处候选 → 留下更好的那一版，'
                         '剩下的交给内部检查去修', tag, tries, _hard, _soft)
            break
        # ⚠ 这里**不写** `if not fix: break`：反例法第 ⑩ 刀证明它是一段死代码 ——
        #   上面 `total <= 0` 已经先 break 了，而 `total` 就是 `sum(counts.values())`，
        #   所以走到这里必然至少有一类 > 0，`fix_list_line` 必然非空（未知类也有兜底文案）。
        #   写"双重保险"之前要先问：**外面那道闸会不会先把里面这道挡掉**？
        #   挡掉了，里面那句就永远不会执行 —— 判据也就测不到它（变异删掉它照样绿）。
        # [EN] ⚠ Deliberately **no** `if not fix: break` here: counterexample cut 10 proved it dead
        # [EN] code -- `total <= 0` already broke above, and `total` is `sum(counts.values())`, so
        # [EN] reaching here guarantees at least one class > 0 and `fix_list_line` is never empty
        # [EN] (unknown classes get fallback wording). Before writing a "double safety net", ask
        # [EN] whether the outer gate already blocks the inner one -- if so the inner line never runs
        # [EN] and no criterion can see it (deleting it stays green).
        fix = fix_list_line(counts)
        _LOG.info('%s：把我们清单上的 %d 条退回给服务重写一遍', tag, total)
    if best is not None:
        return str(best[1]), ''
    return '', last_why


def export_outline(*, day: int, raw_novel: str, process: str,
                   characters: list[str] | None = None,
                   setting: str = '', novel_dir=None,
                   fix_list: str = '',
                   style: str = '') -> str:
    """**导出材料**：设定集 + 历史小说 + 本地推演过程（用户 2026-10-21 点名的三件套）。

    为什么抽成模块级纯函数：判据要能测**行为**。
    这段原来内联在 `_mumu_export` 里（那个函数是异步的、还要连服务），
    于是判据只能"看源码里有没有这个字符串" —— 而把
    `+ _hist if _hist else ''` 改成 `+ ''`（不给历史小说）之后字符串还在，
    判据照样绿（反例法当场戳穿，第 ⑥ 刀）。
    抽出来之后，喂一份假材料就知道有没有真的拼进去。

    三样各管一件事，缺一样都不像一本书：
      · 设定集   —— 这人是谁、这地方是什么、这本书守什么规矩；
      · 历史小说 —— 前几章**怎么写的**（句子长度、视角、口气），是**正文**不是摘要；
      · 推演过程 —— 这一天**真的发生了什么**（在场/事件/机制备注）。
    
        English:
    **Export material**: setting book + history novel + local derivation process (the three inputs
    the user named on 2026-10-21).
        Why a module-level pure function: criteria must test **behaviour**. This used to be inlined in
        `_mumu_export` (async, and it talks to the service), so the criterion could only "look for the
        string in the source" -- and after changing `+ _hist if _hist else ''` to `+ ''` (no history
        novel) the string is still there, so the criterion stayed green (caught by the counterexample
        method, cut 6). Extracted, feeding it fake material shows whether it was really assembled.
        Each of the three does one job; missing one and it stops reading like one book:
          · setting book -- who this person is, what this place is, what this book obeys;
          · history novel -- **how** the previous chapters were written (sentence length, viewpoint,
            tone); prose, not a summary;
          · derivation process -- **what actually happened** today (cast / events / notes).
    """
    hist = _history_novel(novel_dir, before_day=int(day or 0))
    return '\n'.join(x for x in [
        '── 任务 ──',
        '下面给你「这本书的设定集」「前几章写成的样子」「这一天的原始稿」'
        '和「这一天的推演过程」。'
        '请据此把这一天**重写**成干净、可读的小说正文（不是提纲、不是剧本）：'
        '有场景、有动作、有对白、有人物心声；不要分场、不要标第几拍、'
        '不要写镜头说明、不要写在场名单这类过程痕迹。',
        '**只整理、不新增情节**：不许编出原文里没有的事件、人物、对话。',
        '保持既有的人称、语气、称呼；人物性格不许漂移。',
        '相邻的日子要读起来连续，不要每天各起一段。',
        ('── 这本书的设定集（人物是谁、这里是什么地方、守什么规矩）──\n'
         + str(setting).strip() if str(setting or '').strip() else ''),
        # ★★★ 2026-10-27（用户点名）：风格控制 + 幽默六步范例也要随导出细纲发过去。
        #   ⚠ 导出那一侧**手上没有** `WorldState`（只有运行文件夹），所以这一段
        #     由调用方从**配置**读出来传进来（`util/style_kit.from_config()`）——
        #     旋钮本来就是配置级的，`sim/setup.py` 也是 `CFG.f(...)` 读的，同一个源。
        # [EN] ★★★ 2026-10-27 (named by the user): the style control + the six-step humor examples go
        # [EN] along with the export outline too.
        # [EN] ⚠ The export side has **no** `WorldState` on hand (only the run folder), so the caller
        # [EN] reads this from the **config** and passes it in (`util/style_kit.from_config()`) -- the
        # [EN] knobs are config-level to begin with (`sim/setup.py` reads them with `CFG.f(...)` too).
        ('── 风格控制（这一章要写成什么样，**逐条照做**）──\n' + str(style).strip()
         if str(style or '').strip() else ''),
        ('── 前几章写成的样子（**接着它的笔调往下写**，不要重复它写过的情节）──\n'
         + hist if hist else ''),
        '── 原始稿（这一天逐字记录的内容）──',
        raw_novel,
        '── 推演过程（这一天的过程痕迹：在场名单 / 本幕依据 / 机制备注）──',
        process,
        ('── 在场人物 ──\n' + '、'.join(characters) if characters else ''),
        str(fix_list or '').strip(),
    ] if str(x or '').strip())


async def _mumu_sample(ctx: 'SetCtx', *, nodes: str, yesterday: str,
                       craft: str) -> tuple[str, str]:
    """让 MuMuAINovel 写当天样章。返回 `(正文, 没成功的原因)`；成了就 `(正文, '')`。

    **整段在子线程里跑**：桥接层是同步 urllib + 轮询等待（最坏十几分钟），
    直接在事件循环里跑会把界面冻住 —— 那种"程序看起来死了"比"这一步慢"
    难解释得多。
    
        English:
    Let MuMuAINovel write the day's sample chapter. Returns `(body, reason it failed)`; on success
    `(body, '')`.
        **The whole thing runs on a child thread**: the bridge layer is synchronous urllib + polling wait (worst case ten-plus minutes),
        running it directly in the event loop would freeze the UI -- that kind of "the program looks dead" is much harder
        to explain than "this step is slow".
    """
    import asyncio

    def _work() -> tuple[str, str]:
        # ★★★ 2026-10-21：**已经在停了就别再开新活**。
        #   实测（查「收尾时间放长」时发现的真因）：点停止之后这里又跑了两遍样章，
        #   一共 3 分钟；用户以为「收尾特别久」，其实收尾根本没开始 ——
        #   它还在写样章。`_open_day` 那边虽然有 `if self.stopping: return`，
        #   但那要等这一整步（含两次重写）跑完才轮得到。
        #   ⚠ 只拦「还没开始的活」：正在跑的那一次调用**不硬杀**
        #     （硬杀会在服务端留下空章节记录，`trailing_empty_numbers` 那边有代价）。
        # [EN] ★★★ 2026-10-21: **do not start new work once stopping**.
        # [EN] Measured while investigating "make the wrap-up time longer": after stop was clicked
        # [EN] this ran two more sample passes (three minutes). The user read that as "wrap-up takes
        # [EN] forever" while wrap-up had not started -- it was still writing the sample.
        # [EN] `_open_day` does check `if self.stopping: return`, but only after this whole step
        # [EN] (including two rewrites) completes.
        # [EN] ⚠ Only blocks work that has **not started**; the in-flight call is not hard-killed
        # [EN] (killing it leaves an empty chapter row on the service side).
        try:
            _lp = getattr(ctx, 'loop', None)
            if _lp is not None and bool(_lp.stopping):
                _LOG.info('已经点了停止 → 不再开始写样章（这一步直接跳过）')
                return '', '已停止（不再开始新的一遍）'
        except Exception:                                    # noqa: BLE001
            pass
        try:
            from novelservices import mumu_bridge as BR
        except Exception as e:                               # noqa: BLE001
            return '', f'接不上工具链（{e!r}）'
        try:
            # ★★ 「创作服务」在 Agents 页里**点名的模型** → 写进**它自己的** `backend/.env`
            #   （2026-10-12，用户要求"novelservices 也作为一个特殊 Agent 纳入管理"）。
            #   ⚠ **只在作者真的点名了才推**：没点名就一个字都不动 ——
            #     那意味着"照你自己在配置页里写的那套跑"，我们不该替他改。
            #   ⚠ 推过去的是**地址 + 密钥 + 模型名**三样一起：只改模型名而地址还是旧的，
            #     等于让它拿甲家的名字去问乙家（必然 404），比不改更坏。
            # [EN] ★★ The model **named for the "Creation Service"** on the Agents page is pushed into
            # [EN] **its own** `backend/.env` (2026-10-12, on the user's request that "novelservices also
            # [EN] be managed as a special Agent").
            # [EN] ⚠ **Only push when the author actually named one**: otherwise touch nothing -- that
            # [EN] means "run with what you wrote on the config page", and we must not change it for
            # [EN] them.
            # [EN] ⚠ Push **endpoint + key + model name together**: changing only the model name while
            # [EN] the endpoint stays old means asking provider B with provider A's name (guaranteed
            # [EN] 404), which is worse than not changing anything.
            try:
                from llm import models as MODELS
                _res = MODELS.resolve(agent_key='novelservices')
                if _res is not None:
                    _kv = {}
                    if _res.base_url:
                        _kv['OPENAI_BASE_URL'] = _res.base_url
                    if _res.api_key:
                        _kv['OPENAI_API_KEY'] = _res.api_key
                    if _res.model:
                        _kv['DEFAULT_MODEL'] = _res.model
                    if _kv:
                        _why = BR.save_service_env(_kv)
                        if _why:
                            _LOG.warning('创作服务的模型没推过去（不影响自写）：%s', _why)
                        else:
                            _LOG.info('创作服务将按「%s」出稿（%s）',
                                      _res.label, _res.model)
            except Exception as _e:                          # noqa: BLE001
                _LOG.warning('推创作服务模型时出错（不影响自写）：%r', _e)

            # 细纲：**把原提示词里那些硬要求搬过来**，别只丢一句"写今天的戏"。
            # 实测：细纲写到"这一章只发生这几件事、别的一律不许出现"，
            # 它才管得住结构；写得含糊 = 拿到一份跑题的第一稿。
            # [EN] Detailed outline: **move over those hard requirements from the original prompt**, do not just
            # [EN] throw in "write today's scene".
            # [EN] Empirically: when the detailed outline says "this chapter only has these events, nothing else
            # [EN] may appear",
            # [EN] it can control the structure; writing it vaguely = getting an off-topic first draft.
            # ★★★ 2026-10-21（用户点名）：**历史小说 = 前面几章的实际正文**。
            #   它不是"前情提要"（那是摘要，只说发生了什么），而是**写法样本**：
            #   句子多长、视角贴谁、心声怎么处理、这一段什么口气。
            #   摘要教内容，正文教文笔 —— 两样都要，缺一样就写不像一本书。
            # [EN] ★★★ 2026-10-21 (named by the user): **history novel = the actual prose of
            # [EN] previous chapters**. Not a recap (a summary of what happened) but a **style
            # [EN] sample**: sentence length, whose head the viewpoint sits in, how inner voice is
            # [EN] handled, the tone of a paragraph. A summary teaches content, prose teaches the
            # [EN] writing -- both are needed; missing one and it stops reading like one book.
            _hist = _history_novel(getattr(ctx, 'novel_dir', None),
                                  before_day=int(getattr(ctx, 'day', 0) or 0))
            _hist_block = ('── 前几章写成的样子（**接着它的笔调往下写**，'
                           '不要重复它写过的情节）──\n' + _hist) if _hist else ''
            outline = '\n'.join(x for x in [
                f'第 {ctx.day} 天。',
                '── 这本书（设定集）──', ctx.world_brief(600),
                # ★★★ 2026-10-27（用户点名：「把类似的例子提供给 MuMuAINovel 服务
                #   让它尽量写」）：**风格控制 + 幽默六步范例**必须随细纲一起发过去。
                #   ⚠ 走服务这条路时，**上面那份 system 提示词是不发的** ——
                #     只有这里的 `outline` 会进它那边（与 `SCENE_CARD_RULES` /
                #     `live_speech_block` 同一条纪律：不挂在这儿，家里的那条路才有效果）。
                #   ⚠ 也不能塞进 `world_brief(600)` —— 那一格会被顶级规则挤掉。
                # [EN] ★★★ 2026-10-27 (named by the user: "give MuMuAINovel similar examples so it tries
                # [EN] hard"): **the style control + the six-step humor examples** must go along with the
                # [EN] detailed outline.
                # [EN] ⚠ On the service path, **the system prompt above is NOT sent** -- only the `outline`
                # [EN] here reaches it (same discipline as `SCENE_CARD_RULES` / `live_speech_block`: if it
                # [EN] isn't here, it only has an effect on the in-house path).
                # [EN] ⚠ It also cannot go inside `world_brief(600)` -- that slot gets squeezed out by the
                # [EN] top-level rules.
                ('── 风格控制（这一章要写成什么样，**逐条照做**）──\n' + ctx.style_block()
                 if ctx.style_block() else ''),
                ('── 今天在场的人 ──\n' + '、'.join(ctx.people[:12])
                 if ctx.people else ''),
                '── 进度节点（主线，必须推进）──', nodes,
                '── 前情提要 ──', ctx.recap(800),
                _hist_block,
                '── 这一章的要求 ──',
                '按小说的写法写这一天是什么样。接着前面的往下写，不要另起炉灶、'
                '不要凭空造新势力。',
                '必须写清：这一天结束时，哪件事变了。人物做的每件事都要跟这条主线有关。',
                # ★★★ 2026-10-21（用户拿了一份专业分析报告，点名要改的三条结构问题）。
                #   这三条**只写在「写样章」这一侧**，因为这里是「设计今天演什么」（计划），
                #   允许安排结构；而「导出整理」那一侧的铁律是「只整理、不新增」——
                #   在同一处要求「把揭秘挪到最后」「加一个反转」，模型只能靠**编**来满足，
                #   那比原来的问题更糟。所以：结构问题在计划层治，不在整理层治。
                # [EN] ★★★ 2026-10-21 (three structural issues the user named from a professional
                # [EN] review). Written **only on the sample-chapter side**, because here we are
                # [EN] "designing what today performs" (a plan) where arranging structure is
                # [EN] legitimate. The export side's iron rule is "organize only, never add"; asking it
                # [EN] to "move the reveal to the end" or "add a twist" forces the model to **invent**,
                # [EN] worse than the original problem. Structure is fixed in the planning layer.
                '── 这一天怎么排（三条结构要求）──',
                # ① 配角功能重叠：报告实测四个角色里有两个都只在「警告」，都没有自己的弧光。
                # [EN] ① Overlapping supporting roles: two of four existed only to warn.
                '每个在场的人都要有一件**只有他能办**的事（别人替不了）。',
                '❌ 反面：两个人都只是在警告主角（「别往那边去」「夜里别出去」）——',
                '那样他们加起来也只顶一个人用，读者记不住谁是谁。',
                '✅ 做法：问一句「这件事为什么非得是他」——他知道别人不知道的一件事、',
                '他能做别人不能做的一件事、他怕一样别人不怕的东西。各占一样，三个人才都立得住。',
                # ② 一次只揭一层：报告实测「核心谜底在 40% 处就说了」，后半段全成了已知信息的验证。
                # [EN] ② Reveal one layer at a time: measured, the core answer came at 40%.
                '这一天**只揭一层底**，不要一次把话说完。',
                '❌ 反面：中途就把「那东西是什么、干什么用、最后会怎样」一口气说完 ——',
                '后面所有戏都变成了「验证已经知道的事」，读者不再紧张。',
                '✅ 做法：这一天到手的只是**一部分**——看见了一样东西、听见了半句话、',
                '猜到一个方向但猜错了；把「它到底是什么」留给后面的日子。',
                # ★★★ 2026-10-21：**以进度节点为准**（这一句是防"两条规则打架"）。
                #   上面那条"只揭一层"和进度节点的"只走这一步"说的是同一件事 ——
                #   同一件事写在两处、还要模型自己调和，它只会随机挑一条
                #   （本项目的老账："同一件事两处实现是万恶之源"）。
                #   ⇒ 明写优先级：给了节点就以节点为准，"只揭一层"只是它的通俗说法。
                # [EN] ★★★ 2026-10-21: **the progress node wins** (this line exists to stop two rules
                # [EN] from fighting). "Reveal one layer" and the node's "walk only this step" are the
                # [EN] same thing -- written twice and left for the model to reconcile, it just picks
                # [EN] one at random (an old debt here: "two implementations of one thing"). So state
                # [EN] the precedence explicitly: when a node is given, the node rules.
                '⚠ 上面若给了**进度节点**，就以节点为准 —— 它写着「只走这一步」，',
                '就是这条要求的准确版；两者不冲突时不用管它。',
                # ③ 结尾要有不可逆的变化：报告实测「结尾停在一个出现过多次的意象上，人物跟开场没区别」。
                # [EN] ③ The ending needs an irreversible change: measured, it ended on an image
                # [EN] already used several times, and the protagonist was unchanged.
                '这一天结束时，必须有**一件不可逆的事**发生了：某个人的处境变了，',
                '回不到早上那样了（他知道了不该知道的、他欠下了、他答应了、他错过了）。',
                '❌ 反面：结尾只是「又一个怪现象」或者「又续了一回茶」——那是停下来的，不是结束。',
                '✅ 自查：把结尾那一句拿掉，这一天有没有损失？没有损失就是没结束。',
                '⚠ 这一条和进度节点的「完成判据」是同一件事：节点判据里写着「结束时某人处境变了」，',
                '照它写就行；节点判据没写这一件事时，按上面这一条补。',
                '这是小说不是提纲：有场景、有动作、有人说话。不要分场、不要标第几拍、'
                '不要写镜头说明（那是剧作者的活）。',
                # ★ 2026-10-10：这两段**必须跟着细纲一起发过去**。
                #   走服务的时候，上面那份 prompt 是**不发的** ——
                #   只有这里的 `outline` 会进它那边。少了这两段，
                #   "场景可画地图"与"能拍"这两条要求就只在家里那条路上生效。
                # [EN] ★ 2026-10-10: these two paragraphs **must be sent along with the detailed outline**.
                # [EN] When going through the service, the prompt above is **not sent** --
                # [EN] only the `outline` here goes into its side. Without these two paragraphs,
                # [EN] the two requirements "scene can be drawn as a map" and "can be filmed" only take effect on the
                # [EN] in-house path.
                (SCENE_CARD_RULES if CFG.b('CREW_SCENE_CARD') else ''),
                (FILMABLE_RULES if CFG.b('CREW_FILMABLE') else ''),
                # ★ 2026-10-10（第 01 类第 1 条）：两条**机械可查**的硬规则
                #   （镜头看不见就不写 / 每句台词先问"他什么时候知道的"）。
                #   与上面两段同理 —— 走服务时必须随细纲一起发过去。
                # [EN] ★ 2026-10-10 (Category 01 Item 1): two **mechanically checkable** hard rules
                # [EN] (if the camera cannot see it, do not write it / for each line of dialogue, first ask "when did
                # [EN] he know").
                # [EN] Same reasoning as the two paragraphs above -- when going through the service, they must be sent
                # [EN] along with the detailed outline.
                SCREEN_HARD_RULES,
                # ★ 2026-10-12（用户点名）：**怎么说话才像个活人**。
                #   与上面几段同理 —— 走服务时必须随细纲一起发过去，
                #   不然"台词要像真人"这条要求只在家里那条路上生效。
                # [EN] ★ 2026-10-12 (the user named this): **how to speak like a live person**.
                # [EN] Same reasoning as the paragraphs above -- when going through the service, it must be
                # [EN] sent along with the detailed outline, otherwise the requirement "dialogue must sound
                # [EN] like real people" only takes effect on the in-house path.
                live_speech_block(),
                # ★★★ 2026-10-28（叙事层）：机器味的大头在结构不在词句
                #   （只改表面词句，识别率只掉 1.6 个点）。与上面几段同理 ——
                #   走服务时必须随细纲一起发过去。
                # [EN] ★★★ 2026-10-28 (narrative layer): the bulk of the machine smell is structure,
                # [EN] not wording (rewording alone moves detection by only 1.6 points). Same
                # [EN] reasoning as the paragraphs above -- must travel with the outline.
                anti_fp_block(),
            ] if str(x or '').strip())
            task = BR.ChapterTask(
                project_key=(str(getattr(ctx, 'book', '') or '').strip() or '未命名'),
                novel_dir=getattr(ctx, 'novel_dir', None),
                title=f'第 {ctx.day} 天',
                outline=outline,
                characters=list(ctx.people[:12]),
                genre=(ctx.genre()[0] or ''),
                # ★★★ 2026-10-21：**样章用样章的字数，不是整章的字数**。
                #   以前这里借用了 `MUMU_TARGET_WORDS`（2500 = 导出重写整章的字数），
                #   而自写路径给的是 `CREW_STORY_MIN~MAX`（180~600 = 质感样本）——
                #   **同一个 `ds.story`、同一个下游编剧，两条路差 4~14 倍**。
                #   后果不是"长一点更好看"，而是**演员被框死**：
                #   2500 字的样章会让编剧拆出更细的拍（每拍带更多具体动作），
                #   演员从"自己决定这一拍做什么"退化成"照着拍子填台词"。
                #   ⇒ 用 `MUMU_SAMPLE_WORDS`（0 = 跟随 `CREW_STORY_MAX`）。
                # [EN] ★★★ 2026-10-21: **a sample uses the sample's length, not a whole chapter's.**
                # [EN] This used to borrow `MUMU_TARGET_WORDS` (2500 = the export rewrite length) while
                # [EN] the in-house path used `CREW_STORY_MIN~MAX` (180-600 = a texture sample) --
                # [EN] **same `ds.story`, same downstream screenwriter, 4-14x apart**. The consequence
                # [EN] is not "longer reads nicer" but **the actors get boxed in**: a 2500-character
                # [EN] sample makes the screenwriter cut finer beats (more concrete actions), and actors
                # [EN] degrade from "decide what this beat does" to "fill in lines per beat".
                # [EN] => Use `MUMU_SAMPLE_WORDS` (0 = follow `CREW_STORY_MAX`).
                target_words=_sample_words(),
                model=str(CFG.s('MUMU_ANALYSIS_MODEL') or ''),
                skill_key=str(CFG.s('MUMU_SKILL_KEY') or ''),
                enable_analysis=CFG.b('MUMU_ENABLE_ANALYSIS'),
                timeout=float(CFG.i('MUMU_TIMEOUT_SECONDS') or 900),
            )
            # ★★★ 2026-10-21 架构：**优先外部服务** —— 不在就拉起来，真起不来才回退。
            # [EN] ★★★ 2026-10-21 architecture: **prefer the external service** -- start it if
            # [EN] down; fall back only if it truly cannot start (see `_ensure_mumu`).
            _ok, _why = _ensure_mumu(BR)
            if not _ok:
                return '', _why
            # ★★★ **写归服务，检查归自己，不过就退回重写**（2026-10-21）。
            #   与导出关口**同一份实现**（`write_check_retry`）—— 用户点名的两个阶段
            #   （「开始阶段写小说」与「导出阶段」）共用一套标准，不许各写一段。
            #   ⚠ 这里的 `_mk` 把上一版的问题清单**接在细纲末尾**（最后一句最容易被遵守）。
            # [EN] ★★★ **Writing is the service's, checking is ours; send it back if it fails**
            # [EN] (2026-10-21). **Same implementation** as the export gate (`write_check_retry`) --
            # [EN] the two stages the user named ("write the novel at the start", "export") share one
            # [EN] standard; never two copies.
            # [EN] ⚠ `_mk` appends the previous pass's problem list to the **end** of the outline
            # [EN] (the last sentence is obeyed most reliably).
            _n = {'i': 0}

            def _next(_fx: str):
                _n['i'] += 1
                task.outline = outline + ((chr(10) * 2 + _fx) if _fx else '')
                if _n['i'] > 1:
                    task.title = f'第 {ctx.day} 天（改第 {_n["i"] - 1} 遍）'
                return task

            # ⚠ **长度下限也按样章的口径**（`CREW_STORY_MIN_FLOOR`，默认 80 字）——
            #   用导出那套 0.4 倍（600×0.4=240）会把一个 200 字的合格样章判成"没写出来"。
            # [EN] ⚠ **The length floor follows the sample's own rule**
            # [EN] (`CREW_STORY_MIN_FLOOR`, default 80). Export's 0.4x rule (600x0.4=240) would
            # [EN] reject a perfectly usable 200-character sample as "not written".
            try:
                _sfloor = int(CFG.i('CREW_STORY_MIN_FLOOR') or 80)
            except Exception:                            # noqa: BLE001
                _sfloor = 80
            # ⚠ 传 `should_stop`：**点停止之后不许再写下一遍**（见 `write_check_retry` 里那段实测）。
            #   `ctx.loop` 是写样章时拿得到的那个 RunLoop（`SetCtx` 上带着），
            #   取不到就当"不停"（旧行为）。
            # [EN] ⚠ Pass `should_stop`: **never write another pass after stop is clicked** (see the
            # [EN] measurement inside `write_check_retry`). `ctx.loop` is the running `RunLoop`;
            # [EN] if unavailable, behave as before (never stop).
            _stop_ask = None
            try:
                _lp = getattr(ctx, 'loop', None)
                if _lp is not None:
                    _stop_ask = lambda: bool(_lp.stopping)          # noqa: E731
            except Exception:                                # noqa: BLE001
                _stop_ask = None
            return write_check_retry(BR, _next, tag=f'写样章·第{ctx.day}天',
                                     min_chars=_sfloor, should_stop=_stop_ask)
        except Exception as e:                               # noqa: BLE001
            return '', f'{type(e).__name__}: {e}'

    return await asyncio.to_thread(_work)


async def prose_checkup(text: str, *, rounds: int = 0,
                        tag: str = '正文', hint: str = '',
                        on_round=None) -> str:
    """**模块级多轮检查修复**（R48）—— 导出关口用它，写小说时用 `Novelist._checkup`。

    ★★★ 为什么要有模块级这一个：
      用户要求「一开始写小说和最后导出的时候都可以进行几轮的问题检查也修复」。
      两个关口跑的是**同一套**规则，所以只能有**一份**实现 ——
      导出层拿到的是纯文本，没有 `Novelist` 实例。

    `on_round` —— 细粒度进度回调 `(第几轮, 共几轮, 步骤名, 第几步, 共几步)`（2026-10-28 加）。
      导出时这一段可以跑一二十分钟（每轮每步一次模型调用），没有它就只能告诉用户
      "检查开始 / 检查结束" —— 实测用户因此判定导出卡死。

    ⚠⚠ **这个函数成立的前提**：`_fix_*` 系列**全部无状态** ——
      它们只依赖 `self._cast_names(text)`（一个纯函数），不读任何实例属性。
      ⇒ 用 `Novelist.__new__(Novelist)` 跳过 `__init__` 是安全的。
      ⚠ 这个前提**已经被判据钉住**（`verify_prose_flow` 的 Y 组）：
        谁将来在 `_fix_*` 里加一个 `self.xxx` 的实例状态，那条判据会立刻变红，
        提醒必须改成"把状态显式传进来"，而不是让这里的 `__new__` 悄悄炸掉。
      [EN] The premise: every `_fix_*` is stateless (only `self._cast_names`, a pure
      [EN] function). A check in `verify_prose_flow` locks that premise down -- adding
      [EN] instance state to any `_fix_*` turns it red immediately.
    """
    if not text:
        return text
    # ★ `hint` = 上一轮/上一天被退回的教训（Reflexion 的反思记忆）。
    #   用 ContextVar 装，改写在**同一个协程**里读得到；并发任务各自隔离。
    #   空串时 `apply_hint` 原样返回提示词 ⇒ 不传 hint 的调用点行为逐字不变。
    try:
        obj = Novelist.__new__(Novelist)
        return await obj._checkup(text, rounds=rounds, tag=tag, hint=hint,
                                  on_round=on_round)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('多轮检查（%s）失败（原样返回）：%r', tag, e)
        return text


async def _mumu_export(*, day: int, title: str, raw_novel: str,
                       process: str, project_key: str, novel_dir,
                       characters: list[str] | None = None,
                       genre: str = "",
                       setting: str = "",
                       target_words: int | None = None) -> tuple[str, str]:
    """让 MuMuAINovel 据「原始稿 + 推演过程」**重写**某一天的可读稿。

    返回 `(正文, 没成功的原因)`；成了就 `(正文, '')`。

    与 `_mumu_sample`（推演时写当天样章）的区别：那里是从零写，
    这里**已经有原文**，要的是「把这一天重写成干净小说」——
    所以 `outline` 里把**原始稿**和**推演过程**都喂进去，并明确
    「只整理、不新增情节」。失败一律回退到内部整理稿（调用方负责兜底）。

    ★ 同样的纪律：整段在子线程里跑（桥接层是同步 urllib + 轮询等待），
      失败返回 `( '', reason )`，**绝不抛异常**出来冻界面。
        English:
    Let MuMuAINovel **rewrite** a day's readable draft from "raw novel text + derivation process".
        Returns `(body, reason it failed)`; on success `(body, '')`.
        Differs from `_mumu_sample` (writing the day's sample chapter during simulation) in that
        here we **already have the raw text** and want "rewrite this day into a clean novel" --
        so the `outline` feeds both the **raw novel text** and the **derivation process**, and
        explicitly says "only organize, don't add new plot". On failure always fall back to the
        internal edited draft (the caller does the fallback).
        ★ Same discipline: the whole thing runs on a child thread (the bridge layer is synchronous
        urllib + polling wait); on failure return `( '', reason )`, **never raise** to freeze the UI.
    """
    import asyncio

    def _work() -> tuple[str, str]:
        try:
            from novelservices import mumu_bridge as BR
        except Exception as e:                               # noqa: BLE001
            return '', f'接不上工具链（{e!r}）'
        try:
            # ★★ 与 `_mumu_sample` 一致：把「创作服务」在 Agents 页点名的模型
            #   推到它自己的 `backend/.env`（只在真的点名了才推）。
            # [EN] ★★ Same as `_mumu_sample`: push the model named for "Creation Service" on the
            # [EN] Agents page into its own `backend/.env` (only when actually named).
            try:
                from llm import models as MODELS
                _res = MODELS.resolve(agent_key='novelservices')
                if _res is not None:
                    _kv = {}
                    if _res.base_url:
                        _kv['OPENAI_BASE_URL'] = _res.base_url
                    if _res.api_key:
                        _kv['OPENAI_API_KEY'] = _res.api_key
                    if _res.model:
                        _kv['DEFAULT_MODEL'] = _res.model
                    if _kv:
                        _why = BR.save_service_env(_kv)
                        if _why:
                            _LOG.warning('创作服务的模型没推过去（不影响自写）：%s', _why)
            except Exception as _e:                          # noqa: BLE001
                _LOG.warning('推创作服务模型时出错（不影响自写）：%r', _e)

            # ★★★ 2026-10-27：风格控制（+ 幽默六步范例）→ 随导出细纲发过去。
            #   这一侧**手上没有** `WorldState`（只有运行文件夹），所以从**配置**读
            #   （旋钮本来就是配置级的，`sim/setup.py` 也是 `CFG.f(...)` 读的，同一个源）。
            # [EN] ★★★ 2026-10-27: the style control (+ the six-step humor examples) go along with the
            # [EN] export outline.
            # [EN] This side has **no** `WorldState` on hand (only the run folder), so read from the
            # [EN] **config** (the knobs are config-level to begin with -- `sim/setup.py` reads them with
            # [EN] `CFG.f(...)` too, same source).
            try:
                from util import style_kit as _SK
                _style_block = _SK.from_config()
            except Exception:                                # noqa: BLE001
                _style_block = ''

            # ★★★ 2026-10-21（用户点名的导出输入）：**设定集 + 历史小说 + 本地推演过程**。
            #   在此之前这里只有「原文 + 推演过程」两样 —— 设定集没给（它不知道柳氏的
            #   身份、这楼是什么地方），历史小说也没给（它不知道怎么接上一章的笔调）。
            #   ⇒ 三条线索各自管一件事，缺一样都不像一本书：
            #     · 设定集      —— 这人是谁、这地方是什么、这本书守什么规矩；
            #     · 历史小说    —— 前几章**怎么写的**（句子长度、视角、口气），不是摘要；
            #     · 推演过程    —— 这一天**真的发生了什么**（在场/事件/机制备注）。
            #   ⚠ 顺序也重要：先给"这本书是什么"，再给"前面写成什么样"，
            #     最后给"今天发生了什么" —— 模型按这个顺序建立上下文，
            #     反过来（先说今天的事）它会把前面两样当补充材料读。
            # [EN] ★★★ 2026-10-21 (the export inputs the user named): **setting book + history
            # [EN] novel + local derivation process**. Before this the section had only "raw text +
            # [EN] process": no setting book (it did not know who Liu is or what this building is)
            # [EN] and no history novel (it did not know how to continue the previous chapter's
            # [EN] voice). => Three threads, each with its own job; missing one and it stops reading
            # [EN] like one book:
            # [EN] · setting book -- who this person is, what this place is, what this book obeys;
            # [EN] · history novel -- **how the previous chapters were written** (sentence length,
            # [EN]   viewpoint, tone), not a summary;
            # [EN] · derivation process -- **what actually happened today** (cast / events / notes).
            # [EN] ⚠ Order matters too: first "what this book is", then "what the previous pages read
            # [EN] like", last "what happened today". The model builds context in that order; reversed
            # [EN] (today's events first) it treats the other two as supplementary material.
            # ★★★ 2026-10-21 架构：**优先外部服务** —— 不在就拉起来，真起不来才回退。
            #   放在生成之前（不是之前那次"探测一下就走"），见 `_ensure_mumu`。
            # [EN] ★★★ 2026-10-21 architecture: **prefer the external service** -- start it if
            # [EN] down; fall back only if it truly cannot start (see `_ensure_mumu`).
            _ok, _why = _ensure_mumu(BR)
            if not _ok:
                return '', _why

            # ★★★ **写归服务，检查归自己，不过就退回重写**（2026-10-21，用户点名）
            # ------------------------------------------------------------------
            # 用户原话：「把写小说和导出小说的 Reflection 过程中的**写作过程**调用
            # MuMuAINovel 服务，**检查部分用自己的检查列表**」。
            # 具体怎么"退回"只有一份实现：`write_check_retry`（两处共用）。
            # ⚠ 以前这里、以及写样章那边是各写一段 —— 那种"同一件事两处实现"
            #   一定会分叉（一处改了阈值、另一处没改，跑起来两个阶段标准不同）。
            # [EN] ★★★ **Writing is the service's, checking is ours; if it fails, send it back**
            # [EN] (2026-10-21, named by the user). The "send back" mechanics exist in exactly one
            # [EN] place: `write_check_retry` (shared by both stages).
            # [EN] ⚠ This used to be separate inline copies here and in the sample path -- "two
            # [EN] implementations of one thing" always diverges (one side changes a threshold, the
            # [EN] other doesn't, and the two stages end up judged by different standards).
            def _make_task(_fix: str, _attempt: int = 0):
                return BR.ChapterTask(
                    project_key=(str(project_key or '').strip() or '未命名'),
                    novel_dir=novel_dir,
                    title=(title if _attempt <= 0 else f'{title}（改第 {_attempt} 遍）'),
                    outline=export_outline(day=day, raw_novel=raw_novel, process=process,
                                           characters=characters, setting=setting,
                                           novel_dir=novel_dir, fix_list=_fix,
                                           # ⚠ `_style_block` 是 `style_kit.from_config()` 返回的
                                           # **一段字符串**，不是函数。写 `_style_block()` 会得到
                                           # `TypeError: 'str' object is not callable`，而它发生在
                                           # `make_task` 里 ⇒ `write_check_retry` 报「拼任务失败」
                                           # ⇒ **每一天都静默回退内部整理稿**（2026-10-28 实测：
                                           #   开了 MUMU_FOR_EXPORT，日志却写着「回退 2/3 天」，
                                           #   重写一天都没发生，用户完全不知道）。
                                           # [EN] `_style_block` is the **string** returned by
                                           # [EN] `style_kit.from_config()`, not a callable;
                                           # [EN] `_style_block()` raises TypeError inside
                                           # [EN] `make_task` => "拼任务失败" => every day silently
                                           # [EN] falls back to the internal draft (measured
                                           # [EN] 2026-10-28: 2/3 days fell back, no rewrite ever ran).
                                           style=_style_block),
                    characters=list(characters or []),
                    genre=genre,
                    target_words=int(target_words or CFG.i('MUMU_TARGET_WORDS') or 2500),
                    model=str(CFG.s('MUMU_ANALYSIS_MODEL') or ''),
                    skill_key=str(CFG.s('MUMU_SKILL_KEY') or ''),
                    enable_analysis=False,
                    timeout=float(CFG.i('MUMU_TIMEOUT_SECONDS') or 900),
                )
            _n = {'i': 0}

            def _next_task(_fix: str):
                _n['i'] += 1
                return _make_task(_fix, _n['i'] - 1)

            # ⚠ 导出这一侧**不传** `should_stop`：这里本来就在收尾里，
            #   中途停掉会让导出稿只剩半章（而导出是用户要的产物）。
            #   它跑得快（通常一遍就过），不构成"点了停止还在等"的主要来源。
            # [EN] ⚠ The export side deliberately does **not** pass `should_stop`: we are already
            # [EN] wrapping up, and stopping mid-way would leave half a chapter (the export IS the
            # [EN] deliverable). It usually finishes in one pass, so it is not the main source of
            # [EN] "still waiting after stop".
            return write_check_retry(BR, _next_task, tag=f'导出重写·第{day}天')
        except Exception as e:                               # noqa: BLE001
            return '', f'{type(e).__name__}: {e}'

    return await asyncio.to_thread(_work)


# ─═════════════════════════════════════════════════════════════════════
#  外部创作服务 · PlotPilot（叙事引擎内核，给**剧作者**设计章节结构）
#               · PenShot（AI 导演/分镜引擎，给**导演/分镜师**拆镜头）
#  与 MuMuAINovel 同一套纪律（这整段是「配置 / 桥接层 / 剧组」唯一的胶水）：
#    ① 每次现读配置；② 整段在子线程跑（桥接层是同步 urllib + 轮询等待）；
#    ③ 绝不抛异常冻界面；④ 失败一律回退到内部自写（调用方负责兜底）。
# [EN] External creation services · PlotPilot (narrative-engine core, designs chapter
# [EN] structure for the **screenwriter**) and PenShot (AI director / storyboard engine,
# [EN] breaks shots for the **director / storyboard artist**). Same discipline as
# [EN] MuMuAINovel (this whole passage is the only glue of "config / bridge / crew"):
# [EN] ① read config fresh each call; ② runs on a child thread (bridge is sync urllib +
# [EN] polling wait); ③ never raises to freeze the UI; ④ on failure always fall back to
# [EN] in-house self-write (the caller does the fallback).
# ───────────────────────────────────────────────────────────────────────
def _plotpilot_enabled_for(key: str) -> bool:
    """这一步该不该交给 PlotPilot？**每次现读配置**（改完不用重启）。

        English:
    Should this step go to PlotPilot? **Read config fresh each call** (no restart
    needed after changes).
    """
    try:
        if not CFG.b('PLOTPILOT_ENABLED'):
            return False
        if key == 'screenwriter':
            return CFG.b('PLOTPILOT_FOR_SCREENWRITER')
        return False
    except Exception:                                        # noqa: BLE001
        return False


def _penshot_enabled_for(key: str) -> bool:
    """这一步该不该交给 PenShot？**每次现读配置**（改完不用重启）。

    ★ PenShot 是「AI 导演/分镜引擎」，本程序里**分镜师**那一档就是导演的分镜活
      （`director` 这一位在名册里只是状态转述，不产 LLM 调用），所以两个 key 都认。

        English:
    Should this step go to PenShot? **Read config fresh each call** (no restart needed).
        ★ PenShot is the "AI director / storyboard engine"; in this program the
        **storyboard artist** position is exactly the director's storyboard work (the
        `director` slot in the roster is only a status recital, it makes no LLM call),
        so both keys are honored.
    """
    try:
        if not CFG.b('PENSHOT_ENABLED'):
            return False
        if key in ('director', 'storyboard'):
            return CFG.b('PENSHOT_FOR_DIRECTOR')
        return False
    except Exception:                                        # noqa: BLE001
        return False


async def _plotpilot_plan(ctx: 'SetCtx', *, story: str,
                         people: list[str] | None = None) -> tuple[str, str]:
    """让 PlotPilot 为「今天这一章」给一份**结构大纲**（分几场 / 每场主题 /
    出场 / 推进主线什么），剧作者写分拍时照着它立结构。

    返回 `(结构文本, 没成功的原因)`；成了就 `(文本, '')`。**整段在子线程跑，
    绝不抛异常**；失败调用方回退到内部推理。
        English:
    Let PlotPilot give a **structure outline** for "today's chapter" (how many scenes /
    each scene's theme / who's on set / what it advances), which the screenwriter follows
    when laying out the beats.
        Returns `(outline_text, reason it failed)`; on success `(text, '')`.
        **Runs on a child thread, never raises**; on failure the caller falls back to
        in-house reasoning.
    """
    import asyncio

    def _work() -> tuple[str, str]:
        try:
            from novelservices import plotpilot_bridge as BR
        except Exception as e:                               # noqa: BLE001
            return '', f'接不上 PlotPilot 桥（{e!r}）'
        try:
            # ★★ 与 `_mumu_sample` 同口径：把「创作服务」在 Agents 页点名的模型推到
            #   PlotPilot 自己的 .env（只在真点名了才推）。
            # [EN] ★★ Same calibration as `_mumu_sample`: push the model named for
            # [EN] "Creation Service" on the Agents page into PlotPilot's own .env.
            try:
                from llm import models as MODELS
                _res = MODELS.resolve(agent_key='novelservices')
                if _res is not None:
                    _kv = {}
                    if _res.base_url:
                        _kv['OPENAI_BASE_URL'] = _res.base_url
                    if _res.api_key:
                        _kv['OPENAI_API_KEY'] = _res.api_key
                    if _res.model:
                        _kv['OPENAI_MODEL'] = _res.model
                    if _kv:
                        _why = BR.save_service_env(_kv)
                        if _why:
                            _LOG.warning('PlotPilot 模型没推过去（不影响自写）：%s', _why)
            except Exception as _e:                          # noqa: BLE001
                _LOG.warning('推 PlotPilot 模型时出错（不影响自写）：%r', _e)

            outline = '\n'.join(x for x in [
                '请为下面这段「原著样章」设计**这一章该发生什么、结构怎么立**：',
                '给一份**分场结构大纲**——今天分几场、每场主题、每场谁在场、'
                '每场推进了主线什么。只给结构，不要写正文、不要写台词。',
                '── 原著样章（剧作者据此立结构）──',
                story,
            ] if str(x or '').strip())
            task = BR.ScreenTask(
                project_key=(str(getattr(ctx, 'book', '') or '').strip() or '未命名'),
                novel_dir=getattr(ctx, 'novel_dir', None),
                title=f'第 {ctx.day} 天',
                premise=f'（由小说世界模拟器剧作者调用）第 {ctx.day} 天',
                outline=outline,
                characters=list((people or [])[:12]),
                genre=(ctx.genre()[0] or ''),
                target_words=2500,
                model=str(CFG.s('PLOTPILOT_MODEL') or ''),
                chapter_number=1,
                timeout=float(CFG.i('PLOTPILOT_TIMEOUT_SECONDS') or 900),
            )
            r = BR.generate_chapter(task)
            if r.ok and len(r.text or '') >= 30:
                return r.text, ''
            return '', (r.reason or 'PlotPilot 未返回结构')
        except Exception as e:                               # noqa: BLE001
            return '', f'{type(e).__name__}: {e}'

    return await asyncio.to_thread(_work)


async def _penshot_storyboard(ctx: 'SetCtx', *, script_text: str,
                             genre: str = '') -> tuple[str, str]:
    """让 PenShot（AI 导演/分镜引擎）把分镜师的「分拍脚本」拆成**导演分镜**，
    作为内部分镜之外的一份**外部参考**附在产出里。

    返回 `(分镜文本, 没成功的原因)`；成了就 `(文本, '')`。**整段在子线程跑，
    绝不抛异常**；失败调用方回退到只用内部分镜。
        English:
    Let PenShot (AI director / storyboard engine) break the storyboard artist's
    beat script into a **director's storyboard**, attached as an **external
    reference** alongside the in-house storyboard.
        Returns `(storyboard_text, reason it failed)`; on success `(text, '')`.
        **Runs on a child thread, never raises**; on failure the caller falls back
        to in-house storyboard only.
    """
    import asyncio

    def _work() -> tuple[str, str]:
        try:
            from novelservices import penshot_bridge as BR
        except Exception as e:                               # noqa: BLE001
            return '', f'接不上 PenShot 桥（{e!r}）'
        try:
            # ★★ 与 `_plotpilot_plan` 同口径：把「创作服务」在 Agents 页点名的
            #   模型推到 PenShot 自己的 .env（`model_env_for` 映射 + `write_llm_env`
            #   落盘）。只在真点名了才推。
            #   ⚠ 2026-10-17 修：前任 `_cutai_storyboard` 这里写死了
            #      `{'GROQ_MODEL': ...}`——既推错了键（PenShot 不认 GROQ_*），
            #      又只覆盖模型名不动地址/密钥，是个假动作。现在按桥的
            #      `model_env_for()` 全量映射 LLM + embedding 三件套。
            # [EN] ★★ Same calibration as `_plotpilot_plan`: push the model named
            # [EN] for "Creation Service" on the Agents page into PenShot's own
            # [EN] .env (`model_env_for` maps + `write_llm_env` writes). Only when
            # [EN] a model is actually named.
            # [EN] ⚠ 2026-10-17 fix: the old `_cutai_storyboard` hardcoded
            # [EN] `{'GROQ_MODEL': ...}` — wrong keys (PenShot ignores GROQ_*)
            # [EN] and it never touched url/key, so it was a no-op. Now the full
            # [EN] LLM + embedding triple via the bridge's `model_env_for()`.
            try:
                from llm import models as MODELS
                _res = MODELS.resolve(agent_key='novelservices')
                if _res is not None:
                    _kv, _warn = BR.model_env_for(_res)
                    if _warn:
                        _LOG.warning('PenShot 模型没推过去（不影响自写）：%s', _warn)
                    elif _kv:
                        _why = BR.write_llm_env(_kv)
                        if _why:
                            _LOG.warning('PenShot 模型没推过去（不影响自写）：%s', _why)
            except Exception as _e:                          # noqa: BLE001
                _LOG.warning('推 PenShot 模型时出错（不影响自写）：%r', _e)

            _m = str(CFG.s('PENSHOT_MODEL') or '')
            task = BR.DirectorTask(
                project_key=(str(getattr(ctx, 'book', '') or '').strip() or '未命名'),
                novel_dir=getattr(ctx, 'novel_dir', None),
                title=f'第 {ctx.day} 天',
                script_text=script_text,
                genre=genre or (ctx.genre()[0] or ''),
                num_scenes=5,
                model=_m,
                timeout=float(CFG.i('PENSHOT_TIMEOUT_SECONDS') or 900),
            )
            r = BR.generate_storyboard(task)
            if r.ok and r.text:
                return r.text, ''
            return '', (r.reason or 'PenShot 未返回分镜')
        except Exception as e:                               # noqa: BLE001
            return '', f'{type(e).__name__}: {e}'

    return await asyncio.to_thread(_work)


def craft_block(key: str, genre: str, structure: str = '') -> str:
    """这个职位该读的工艺条目 ＋ **这本书的特别要求** ＋ **同类书的写法**
    ＋ **可用的技能包** ＋ **作者对本轮走向的要求**。

    空串 = 拿不到任何一段（五样都可缺 —— 缺不是故障）。

    五段拼装的顺序是有讲究的，**越往后越具体、越该压过前面**：

    | 顺序 | 段 | 管什么 | 随什么变 |
    |---|---|---|---|
    | ① | 工艺条目（`craft/playbooks`） | **这一行的手艺**（通用） | 按职位与题材挑 |
    | ② | 这本书的特别要求（`crew/profile`） | 这本要多注意什么 | 每本书 |
    | ③ | 同类书的写法（`booklab/store`） | **别人怎么写这类故事的** | 每本拆过的书 |
    | ④ | 可用的技能（`skills/`） | **手上装着的知识包**（药方·器物·官制…） | 按职位这一刻的活儿 |
    | ⑤ | 作者对本轮走向的要求（`sim/directive`） | **这一轮往哪走**（作者本人填的） | 每轮 |

    ★ ② 与 ③ 都自带"冲突时以我为准"的说法：**具体的压过通用的**。
      ① 是常识，②是这本书的规矩，③是**别人踩出来的路子**（供参考，不是命令 ——
      所以它那句收尾写的是"照不照用由这一场戏自己定"，与 ② 的语气**故意不同**）。
      ④ 与 ③ 共用同一句"用不用由这一场戏自己定"，因为它也是**料**，不是规矩。
      ⑤ 排**最后**：它是作者**此刻**的意图，比这本书的长期规矩还要即时 ——
      但它的抬头也写明了"是意图不是设定"，**不许压过人物与世界**
      （"往这个方向使劲"≠"为了它把人物写歪"）。

    ⚠ 五样都从**世界上挂着的对象**取（`_CURRENT_WORLD`），不往十二个调用点加参数 ——
      那正是"十二处各写一份"的老坑。④ 只需要 `genre` 这个入参，
      所以 world 没绑上也照样给（技能是增强项，不该因为世界没就位就没了）。
    
        English:
    The craft entries this position should read + **this book's special requirements** + **how
    similar books are written**
        + **available skill packs** + **the author's requirement for this round's direction**.
        Empty string = couldn't get any segment (all five may be missing -- missing is not a failure).
        The order in which the five segments are assembled matters, **the further back, the more specific, the more it should override what's in front**:
        | Order | Segment | Governs | Varies with |
        |---|---|---|---|
        | ① | Craft entries (`craft/playbooks`) | **the craft of this line** (general) | chosen by position and genre |
        | ② | This book's special requirements (`crew/profile`) | what this book needs extra attention to | per book |
        | ③ | How similar books are written (`booklab/store`) | **how others write this kind of story** | per book that's been broken down |
        | ④ | Available skills (`skills/`) | **the knowledge packs installed** (prescriptions, artifacts, bureaucratic systems...) | per this moment's task for the position |
        | ⑤ | The author's requirement for this round's direction (`sim/directive`) | **where this round is heading** (filled in by the author) | per round |
        ★ Both ② and ③ carry the phrase "when in conflict, I take precedence": **the specific overrides the general**.
          ① is common sense, ② is this book's rules, ③ is **the path others have trodden** (for reference, not a command --
          so its closing line says "whether to follow it is for this scene to decide", deliberately **different in tone** from ②).
          ④ and ③ share the same phrase "whether to use it is for this scene to decide", because it too is **material**, not a rule.
          ⑤ is placed **last**: it is the author's intent **right now**, even more immediate than this book's long-term rules --
          but its header also states "it is intent, not setting", **it must not override character and world**
          ("push in this direction" ≠ "distort the character for its sake").
        ⚠ All five are fetched from **the object hung on the world** (`_CURRENT_WORLD`), not by adding params to the twelve call sites --
          that is exactly the old pit of "twelve places each writing their own copy". ④ only needs the `genre` input param,
          so it's still provided even when world isn't bound (skills are an enhancement, and shouldn't vanish just because the world isn't in place).
    """
    parts: list[str] = []
    # ★★★ 第 ⓪ 段：**这个职位的系统提示词**（作者在「天机/书斋 · 剧组 Agents」
    #   里可改；有效值 = 软件默认 + 项目定制，见 `crew/catalog.py`）。
    # [EN] ★★★ Paragraph ⓪: **This position's system prompt** (the author can edit it in "Tianji/Shuzhai ·
    # [EN] Crew Agents"
    # [EN] where valid values = software default + project customization, see `crew/catalog.py`).
    #   为什么插在**最前面**：它说的是"你是干什么的、边界在哪"，
    #   是**身份**；后面的手艺/项目档/技能都是"怎么干"。身份该先读到，
    #   而且它自带"与后面的通用手艺冲突时以这一段为准"的说法 ——
    #   与 ② 那段项目档是同一个规矩（具体压过通用）。
    #   ⚠ 这一处是全剧组**唯一**的注入点：14 个职位都走 `craft_block`，
    #     没有一个能漏掉（漏掉的那种表现是"我改了它的系统提示词，它不听话"）。
    # [EN] Why it's inserted **first**: it says "what you do, where the boundaries are",
    # [EN] it is **identity**; the later craft/project profile/skills are all "how to do it". Identity
    # [EN] should be read first,
    # [EN] and it carries its own statement "when conflicting with the generic craft that follows, this
    # [EN] paragraph takes precedence" ——
    # [EN] same rule as paragraph ②'s project profile (specific overrides generic).
    # [EN] ⚠ This is the crew's **only** injection point: all 14 positions go through `craft_block`,
    # [EN] none can be skipped (the symptom of skipping is "I changed its system prompt and it doesn't
    # [EN] obey").
    _head = ''
    try:
        from crew import catalog as _CAT
        _head = _CAT.prompt_block(str(key or ''))
    except Exception as e:                                       # noqa: BLE001
        _head = ''
        _LOG.debug('读 Agent 系统提示词失败（不影响出工）：%r', e)
    if _head:
        parts.append(_head)
    shelves = SHELVES.get(str(key or ''))
    if shelves:
        base = _craft_for(shelves, genre, structure,
                          prefer=READS.get(str(key or ''), ()),
                          # ⚠ 兜底必须是 `_craft_for` 自己的默认值 4 ——
                          #   写成 3 会把没点名的职位从 4 条悄悄削到 3 条。
                          # [EN] ⚠ The fallback must be `_craft_for`'s own default value 4 ——
                          # [EN] writing 3 would silently cut unnamed positions from 4 entries to 3.
                          limit=READ_LIMIT.get(str(key or ''), 4))
        if base:
            parts.append(base)
    world = _CURRENT_WORLD
    # 「作者当前在关注什么」——从**已有的**两处作者手写文本取
    # （书斋里的自定义风格 + 本幕提示）。**不新造一个字段**：
    # 造了没人填就是"假按钮"，而这两处本来就写着作者当下在意的话。
    # ⚠ 它同时喂给第 ③ 段（拆书经验）与第 ④ 段（技能），所以定义在**外面**。
    # [EN] "What the author is currently focused on" —— taken from the **existing** two places of
    # [EN] author-written text
    # [EN] (custom style in Shuzhai + this act's prompt). **Do not create a new field**:
    # [EN] creating one that nobody fills is a "fake button", and these two places already contain what the
    # [EN] author currently cares about.
    # [EN] ⚠ It feeds both paragraph ③ (book-deconstruction experience) and paragraph ④ (skills), so it's
    # [EN] defined **outside**.
    q = ' '.join(str(x or '') for x in (
        getattr(world, 'style_custom', '') if world is not None else '',
        getattr(world, 'scene_hint', '') if world is not None else '',
    )).strip()
    if world is not None:
        try:
            from crew import profile as PROF
            prof = PROF.block_for(getattr(world, 'crew_profile', None), key)
            if prof:
                parts.append(prof)
        except Exception:                                        # noqa: BLE001
            pass
        # ★★ 同类书的写法（拆书库里匹配上的）
        # [EN] ★★ Wording for same-category books (matched in the deconstruction library)
        try:
            from booklab import store as BL
            card = getattr(world, 'genre_card', None) or {}
            fn = BL.for_writers if (str(key or '') in WRITERS
                                    and BL.writers_full()) else BL.for_agents
            lesson = fn(card, question=q)
            if lesson:
                parts.append(lesson)
        except Exception:                                        # noqa: BLE001
            pass
    # ★★★ 第 ④ 段：**技能**（`skills/` 里装着的知识包）
    #   2026-10-10 用户：「拆书功能落地之后 你还得修改相关Agent，
    #   让他们在需要的时候选择合适的SKILL用起来」。
    #   路由规则与"为什么拆书技能的正文不在这里给"写在 `crew/skill_router.py`
    #   的模块头（**同一份内容只给一次**）。
    #   ⚠ 放在**最后**：它比工艺条目具体（是"这一刻这个人手上的活"），
    #     但与第 ③ 段（同类书写法）不分高下，且都自带"用不用由这场戏定"。
    # [EN] ★★★ Paragraph ④: **skills** (knowledge packs stored in `skills/`)
    # [EN] 2026-10-10 user: "After the book-deconstruction feature lands, you still have to modify the
    # [EN] related Agents,
    # [EN] so they pick the appropriate SKILL and use it when needed".
    # [EN] The routing rules and "why the body of the deconstruction skill isn't given here" are written in
    # [EN] `crew/skill_router.py`
    # [EN] 's module header (**the same content is given only once**).
    # [EN] ⚠ Put **last**: it's more specific than craft entries (it's "the work in this person's hands at
    # [EN] this moment"),
    # [EN] but it's on par with paragraph ③ (same-category-book wording), and both carry "whether to use it
    # [EN] is decided by this scene".
    try:
        from crew import skill_router as SKILLR
        sk = SKILLR.skill_block(key, genre=genre, structure=structure, question=q)
        if sk:
            parts.append(sk)
    except Exception:                                            # noqa: BLE001
        pass
    # ★★★ 第 ⑤ 段：**作者对本轮走向的要求**（2026-10-11，`sim/directive.py`）
    #   用户在「起笔」对话框的**前情提要下面**填的那一栏。
    # [EN] ★★★ Paragraph ⑤: **the author's requirements for this round's direction** (2026-10-11,
    # [EN] `sim/directive.py`)
    # [EN] The field the user fills in **below the prior-story recap** in the "Start Writing" dialog.
    #   为什么必须挤进这一处：它是**作者此刻的意图**，而"往哪走"这句话
    #   对**每一个**职位都成立（导演排今天的戏、剧作者分拍、小说作家立人物、
    #   场记盯连续性…谁都该读）。而 `craft_block` 正是全剧组**唯一**的拼装口
    #   （14 个职位 ＋ 演员 `agent/core._actor_craft` ＋ 导演 `day_plan._verify`），
    #   接在这里 = 一处接上、哪一路都漏不掉。
    #   ⚠ 不填时 `block()` 返回空串 ⇒ **一个字都不拼**（老行为逐字退回）。
    #   ⚠ 位置在最后：越往后越具体、越该压过前面（与那张表一致）。
    # [EN] Why it must be squeezed in here: it is **the author's current intent**, and the sentence "which
    # [EN] way to go"
    # [EN] holds for **every** position (director schedules today's scenes, screenwriter splits shots,
    # [EN] novelist establishes characters,
    # [EN] script supervisor watches continuity... everyone should read it). And `craft_block` is exactly
    # [EN] the crew's **only** assembly port
    # [EN] (14 positions + actors `agent/core._actor_craft` + director `day_plan._verify`),
    # [EN] connecting here = connected in one place, no path can miss it.
    # [EN] ⚠ When unfilled, `block()` returns an empty string ⇒ **not a single word is assembled** (old
    # [EN] behavior falls back verbatim).
    # [EN] ⚠ Position is last: the further back, the more specific and the more it should override earlier
    # [EN] ones (consistent with that table).
    if world is not None:
        try:
            from sim import directive as _DIR
            _d = _DIR.block(world)
            if _d:
                parts.append(_d)
        except Exception:                                        # noqa: BLE001
            pass
    # ★★★ 第 ⑥ 段：**协调引擎对这职位的实时指令**（运行窗口底部那个输入框，
    #   经总体协调引擎 `crew/coordinator.Coordinator` 解析后写入；
    #   全局指令对所有职位都生效）。这是**对话式总调度**落进剧组的唯一口子。
    #   ⚠ 放在**最后**：它比 ①–⑤ 都具体（是作者此刻通过对话框给的即时指令），
    #     越往后越该压过前面（与那张表一致）。
    #   ⚠ 每次 `work()` **现读**（惰性 import，不缓存单例里的指令）——
    #     所以用户在运行窗口说一句，下一拍推演就生效，不用重启。
    #   ⚠ `crew_directive(key)` 已经把「全局 + 这职位专属」拼好了，这里只调一次。
    # [EN] ★★★ Paragraph ⑥: **the Coordinator engine's real-time directive for this position**
    # [EN] (the run-window bottom input box, parsed and written by the overall Coordinator engine
    # [EN] `crew/coordinator.Coordinator`; the global directive is effective for every position).
    # [EN] This is the **only port** through which the conversational overall scheduler reaches the crew.
    # [EN] ⚠ Put **last**: it's more specific than ①–⑤ (it's the author's immediate instruction given
    # [EN] through the dialog box right now), the further back the more it should override (consistent
    # [EN] with that table).
    # [EN] ⚠ Read **fresh** every `work()` (lazy import, don't cache the directive in the singleton) --
    # [EN] so the user says one sentence in the run window and the next beat takes effect, no restart.
    # [EN] ⚠ `crew_directive(key)` already concatenates "global + this-position-specific", so one call.
    try:
        from crew import coordinator as _CO
        _cd = _CO.Coordinator.instance().crew_directive(key)
        if _cd:
            parts.append(_cd)
    except Exception:                                            # noqa: BLE001
        pass
    return '\n'.join(parts)


#: 当前世界（**只为取项目档**）。由 `craft_block_with()` 设置。
# [EN] : current world (**only for fetching the project profile**). Set by `craft_block_with()`.
#: 为什么不干脆把 `world` 传进来：`craft_block` 在十二个职位里各被调一次，
#: 加参数要改十二处；而它要的那一样东西（`crew_profile`）是**一轮一份**的 ——
#: 与 `CFG` 同一性质。`sim/setup.assemble` 里 `bind_world(world)` 设一次即可。
# [EN] : why not just pass `world` in: `craft_block` is called once in each of twelve positions,
# [EN] : adding a parameter would require changing twelve places; and the one thing it needs
# [EN] (`crew_profile`) is **one per round** ——
# [EN] : same nature as `CFG`. In `sim/setup.assemble`, `bind_world(world)` sets it once.
_CURRENT_WORLD = None


def bind_world(world) -> None:
    """装配时调一次：让 `craft_block` 能取到这本书的项目档。
        English:
    Call once during assembly: so `craft_block` can reach this book's project profile.
    """
    global _CURRENT_WORLD
    _CURRENT_WORLD = world


def _reset_world() -> None:
    """清掉绑定（判据与多轮之间用 —— 免得上一轮的档漏到下一轮）。
        English:
    Clear the binding (used between criteria and rounds -- so the previous round's profile doesn't
    leak into the next).
    """
    global _CURRENT_WORLD
    _CURRENT_WORLD = None


# ══════════════════════════════════════════════════════════════════════
#  认知模式（思维链 / 反思链）—— 与 `craft_block` 的分工
# [EN] Cognition modes (chain-of-thought / reflection chain) —— division of labor with `craft_block`
# ══════════════════════════════════════════════════════════════════════
# 一句话：`craft_block` 给**手艺内容**（这一行怎么干），`cognition_block` 给
# **思考骨架**（按什么顺序自问）。位置也有讲究 —— 手艺在前（背景），
# 骨架紧挨着输出（纪律），所以各处都把骨架放在"硬要求 / 输出格式"那一段之前。
# [EN] In one sentence: `craft_block` provides **craft content** (how to do this line),
# [EN] `cognition_block` provides
# [EN] the **thinking skeleton** (in what order to ask oneself). Position also matters —— craft comes
# [EN] first (background),
# [EN] the skeleton sits right next to the output (discipline), so everywhere the skeleton is placed
# [EN] before the "hard requirements / output format" paragraph.
# 模式表（谁用哪种模式、为什么）在 `crew/cognition.py` 一处；这里只是两个转发，
# 免得 7 个职位各自 `from crew import cognition` 各写一遍 try/except。
# [EN] The mode table (who uses which mode, and why) is in one place in `crew/cognition.py`; here it's
# [EN] just two forwards,
# [EN] to save 7 positions from each writing `from crew import cognition` and its own try/except.
def cognition_block(key: str) -> str:
    """这个职位的**思考骨架**（`crew/cognition.cot_block`）；拿不到返回空串。

    空串的三种情形都是正常的：模式表里这个职位没有 `cot`、开关关着、
    还没给它写骨架。调用方一律当"这段不出现"处理 —— **提示词与从前一字不差**。
    
        English:
    This position's **thought skeleton** (`crew/cognition.cot_block`); returns empty string if
    unavailable.
        The three cases of empty string are all normal: this position has no `cot` in the mode table, the switch is off,
        its skeleton hasn't been written yet. Callers uniformly treat it as "this segment does not appear" -- **the prompt is identical word-for-word to before**.
    """
    try:
        from crew import cognition as COG
        return COG.cot_block(key)
    except Exception:                                            # noqa: BLE001
        return ''


def think_schema_of(key: str) -> str:
    """思考字段在 **JSON 格式说明**里的那一小段（`"构思": "（…）", `）。

    **关掉时返回空串** —— 字段的启停必须跟骨架走，不然"关掉 = 逐字退回"不成立
    （模型会照着一个"没装骨架却仍在格式里"的字段把内容写出来）。详见
    `crew/cognition.think_schema`。
    
        English:
    The small bit for the thought field in the **JSON format spec** (`"构思": "(...)", `).
        **Returns empty string when off** -- the field's enable/disable must follow the skeleton, otherwise "off = revert word-for-word" doesn't hold
        (the model will produce content for a field that "has no skeleton installed yet still appears in the format"). See
        `crew/cognition.think_schema`.
    """
    try:
        from crew import cognition as COG
        return COG.think_schema_of(key)
    except Exception:                                            # noqa: BLE001
        return ''


# ══════════════════════════════════════════════════════════════════════
#  编剧组
# [EN] Screenwriting group
# ══════════════════════════════════════════════════════════════════════

#: 一天的戏切块整理时，一块大概多少字符。
#: ⚠ 取 6000 是**有依据的**：这个长度的材料在本地模型上一次能稳定写出
#:   5000-6000 字的连贯小说；再长就会被"挑几段写"（实测：一次给 4.4 万字，
#:   中段整段跳过）。
#: `0` = 不分块（整段一次交给模型），给"模型上下文很大、想一次过"的用户留的退路。
# [EN] Roughly how many characters go into one chunk when organizing a day's scenes.
# [EN] ⚠ 6000 is **not arbitrary**: material of this length reliably produces 5000-6000 characters of
# [EN] coherent prose in one pass on the local model; anything longer gets "a few passages picked"
# [EN] (measured: handing over 44k characters at once skipped whole middle sections).
# [EN] `0` = no chunking (hand the whole thing to the model in one go), an escape hatch for users with
# [EN] a very large context window who want a single pass.
_DEFAULT_NOVEL_CHUNK = 6000


def _split_for_transcribe(text: str, size: int) -> list[str]:
    """把一天的材料切成若干块（**按行切，尽量在场景边界断开**）。

    ⚠ 为什么按行而不按字数硬切：材料是 `· 动作 某人：…` / `◇ 心声 某人：…`
      这种**一行一条**的格式，从行中间切开会出现"半句动作" —— 模型只能猜，
      而它猜出来的东西会变成"原著里没有的情节"（违反整理的第 1 条要求）。
    ⚠ 优先在 `## 时辰` 那种场景标题行前断开：一块正好一到两场戏，
      整理出来的章节天然有分段。
    ⚠ `size <= 0` ⇒ 整段返回（不分块）。

        English:
    Split a day's material into chunks (**line-based, preferring scene boundaries**).
        ⚠ Why line-based rather than a hard cut at N characters: the material is one entry per line
          (`· 动作 someone: …` / `◇ 心声 someone: …`), so cutting mid-line leaves "half an action" --
          the model can only guess, and what it guesses becomes "plot that wasn't in the original"
          (violating requirement 1 of the organizing task).
        ⚠ Prefer breaking right before a scene heading like `## 时辰`: one chunk is then one or two
          scenes, and the organized chapter naturally has paragraphs.
        ⚠ `size <= 0` => return the whole text (no chunking).
    """
    body = str(text or '').strip()
    if not body:
        return []
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = _DEFAULT_NOVEL_CHUNK
    if size <= 0 or len(body) <= size:
        return [body]
    lines = body.split('\n')
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for ln in lines:
        # 场景标题行前断开（除非当前块还空着 —— 那会切出一个空块）。
        # [EN] Break before a scene heading (unless the current chunk is still empty -- that would
        # [EN] produce an empty chunk).
        is_head = ln.lstrip().startswith('## ')
        if is_head and cur and cur_len >= size * 0.6:
            chunks.append('\n'.join(cur).strip())
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += len(ln) + 1
        if cur_len >= size:
            chunks.append('\n'.join(cur).strip())
            cur, cur_len = [], 0
    if cur:
        tail = '\n'.join(cur).strip()
        # 最后一块太短（< 15%）就并进前一块：别让模型为两句残料单写一段。
        # [EN] If the final chunk is too short (< 15%) merge it into the previous one: don't make the
        # [EN] model write a separate section for two leftover lines.
        if chunks and len(tail) < size * 0.15:
            chunks[-1] = chunks[-1] + '\n' + tail
        elif tail:
            chunks.append(tail)
    return [c for c in chunks if c.strip()]


def _transcribe_jobs(units, size: int, UP=None) -> list[dict]:
    """把**情节单元**摊成"写作次"（一次 = 一次模型调用）。

    每个 job 是 `{body, block, target, label}`：
      · `body`   —— 这次要整理的材料（原样，一个字不改）；
      · `block`  —— 进提示词的「这一站要写多厚」那一段；
      · `target` —— `unit_plan.Target`（句数区间 + 字上限），预算与超长判据都读它；
      · `label`  —— 状态条上那一截（"入楼收留｜详｜6 幕"）。

    ⚠ 重单元（详/中）材料太长才按行再切 —— 那是**模型上下文**的保护，
      与详略无关；切出来的每一片按**自己那几幕**重算目标（幕是数出来的）。
    ⚠ 轻单元（略/带过）**不切**：切成两片就是"每片两句"，反而写多；
      整站一次写一两句，正是"快速跳过很多时间"的写法。
    ⚠ 相邻的几站都是轻的 ⇒ 合并成**一次"掠过"**（`unit_plan.pack` 已经打好了组）：
      三站各一句话读起来正是"几站之间隔了几个月"，而且省掉带全套提示词的调用。
    [EN] Turn plot units into writing jobs (`body` / `block` / `target` / `label`). Heavy units
    [EN] are split by line only when the material is too long for the model -- that is context
    [EN] protection, not a thickness decision, and each slice recomputes its target from **its own
    [EN] acts**. Light units are **never** split (splitting two sentences in two means writing
    [EN] twice as much), and adjacent light units already arrive packed as one "montage" group.
    """
    if UP is None:                                               # pragma: no cover
        from crew import unit_plan as UP
    jobs: list[dict] = []
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = _DEFAULT_NOVEL_CHUNK
    # ⚠ `size <= 0` = **不分块**（`CREW_DAY_NOVEL_CHUNK=0` 的退路，与 `_split_for_transcribe`
    #   同一口径）。这里必须显式处理：不能拿它去乘/取 max，否则 0 会变成 1，
    #   一块 3 万字的材料会被切成几万个一片 —— 那不是"不分块"，是灾难。
    # [EN] `size <= 0` means **no chunking** (the `CREW_DAY_NOVEL_CHUNK=0` escape hatch, same
    # [EN] rule as `_split_for_transcribe`). Handle it explicitly: arithmetic on 0 turns it into
    # [EN] 1, which would shred a 30k-character piece into tens of thousands of slices.
    light_cap = 0 if size <= 0 else max(int(size * 4), size)
    for grp in UP.pack([u for u in (units or []) if u.material()], size):
        if all(u.light for u in grp):
            body = '\n'.join(u.material() for u in grp).strip()
            # ⚠ 轻单元本来很短（篇幅预算 3~8 拍）；真超长时仍按字数切一刀，
            #   但放宽到 4 倍 —— 切细了会变成"每片两句"。
            # [EN] Light units are short by budget; a pathological one is still split, but at 4x
            # [EN] the normal size -- splitting finer would mean "two sentences per slice".
            for piece in _split_for_transcribe(body, light_cap):
                jobs.append({'body': piece,
                             'block': UP.montage_block(grp),
                             'target': UP.montage_target(grp),
                             'label': '／'.join((u.name or '?') for u in grp)[:24]})
            continue
        for u in grp:
            for piece in _split_for_transcribe(u.material(), size):
                # ⚠ 目标按**这一片**的材料量算（一片 ≈ 一次调用的输入上限），
                #   不是按整站算 —— 否则一站被切成 8 片，每片都按整站的目标写，总量翻八倍。
                # [EN] The target is computed from **this piece's** volume (one piece ~ one call's
                # [EN] input cap), never from the whole station -- otherwise a station split into 8
                # [EN] pieces would write 8x the target.
                tgt = UP.target_of(u.weight, len(piece))
                jobs.append({'body': piece,
                             'block': UP.density_block(u, tgt),
                             'target': tgt, 'label': u.label()})
    return jobs


class Novelist(CrewMember):
    """**小说作家**：写当天这一章的原著样章。

    为什么要有这一步（而不是直接让导演分拍）：
    分拍是**结构**，样章是**质感** —— 先有"这一天读起来是什么样"，
    改写成分场时才有东西可拆。反过来先分拍、再让演员即兴填台词，出来的
    是"每拍都成立、连起来不像一部小说"（用户报的「每个人都在做自己的小事」
    有一半是这个原因）。

    ⚠ 只读到"这一天要推进什么"，**不读** `DayScript`（那还不存在）——
      这一步的产出是给剧作者当素材的，不是给演员当框架的。

    ── 可选后端：MuMuAINovel（2026-10-09 加）────────────────────────
    这是**本项目之外**的一个写小说服务（上游 <https://github.com/xiamuceer-j/MuMuAINovel>，
    跑在本机 8001，见 `novelservices/MuMuAINovel/服务说明.md`）。打开它之后，
    "写当天样章"这一步交给它做，本项目只把**细纲**喂过去、把正文取回来。

    四条约束（都是有意的）：

    1. **默认关**（`MUMU_ENABLED=false`）。它是增强项，不是前提。
    2. **失败一律回退**：服务没起、超时、写空章 —— 全部退回下面这条自写路径，
       并把降级原因写进 `CrewNote.why`。**不许因为它把这一天的戏弄丢。**
    3. **不等它想太久**：它跑在**线程**里（`asyncio.to_thread`），
       上限是 `MUMU_TIMEOUT_SECONDS`。不这么做的话，最长 15 分钟没有产出，
       整个界面会像死了一样。
    4. **"整理稿"不走它**（`_transcribe` 仍走自写路径）。理由：整理稿要求
       「就照实际发生的写，今天没发生的一个字都不许加」，而 MuMuAINovel 是
       **自由写作**——它天生会补细节、改说法。这条活它做不对，不是它不行。
    
        English:
    **Novelist**: writes the day's chapter's original sample chapter.
        Why this step exists (instead of having the director split shots directly):
        shot-splitting is **structure**, the sample chapter is **texture** -- first having "what this day reads like",
        then there's something to break apart when rewriting into scenes. The reverse, splitting shots first and then having actors improvise lines, produces
        "every shot holds up but read together it's not like a novel" (half of the user-reported "everyone is doing their own little thing"
        is due to this).
        ⚠ Only reads "what this day must advance", does **not** read `DayScript` (it doesn't exist yet) --
          this step's output is material for the screenwriter, not a framework for the actors.
        ── Optional backend: MuMuAINovel (added 2026-10-09) ────────────────────────
        This is a novel-writing service **outside this project** (upstream <https://github.com/xiamuceer-j/MuMuAINovel>,
        running on local port 8001, see `novelservices/MuMuAINovel/服务说明.md`). Once it's opened,
        the "write today's sample chapter" step is handed to it; this project only feeds it the **detailed outline** and takes the body text back.
        Four constraints (all intentional):
        1. **Off by default** (`MUMU_ENABLED=false`). It's an enhancement, not a prerequisite.
        2. **On any failure, always fall back**: service not up, timeout, empty chapter -- all fall back to the self-written path below,
           and write the degradation reason into `CrewNote.why`. **Never let it lose that day's drama.**
        3. **Don't wait for it to think too long**: it runs in a **thread** (`asyncio.to_thread`),
           capped by `MUMU_TIMEOUT_SECONDS`. Otherwise, up to 15 minutes with no output,
           and the whole UI looks dead.
        4. **"Cleanup draft" does not go through it** (`_transcribe` still uses the self-written path). Reason: the cleanup draft requires
           "write only what actually happened; not one word about what didn't happen today may be added", whereas MuMuAINovel is
           **free writing** -- it naturally fills in details and rewords things. It can't do this job right; it's not that it's incapable.
    """

    key = 'novelist'

    async def work(self, ctx: SetCtx, *, nodes: str = '', yesterday: str = '',
                   prev: str = '', transcribe: str = '',
                   words: int = 0) -> CrewNote:
        """两件事，同一个职位：

        · `transcribe` 为空 → **写当天这一章**（开演之前，给剧作者当素材）；
        · `transcribe` 非空 → **把今天实际发生的整理成小说**（收工之后，
          见 `sim/loop._day_novel`）。

        ★ 为什么两件事放在一个职位上、而不是再加一个人：**都是小说作家的活**
          （一个"打算怎么写"，一个"实际写成什么样"），而且两者共用同一批
          手艺条目（章法 / 网文方法论 / 编剧正典）。分成两个职位的话，
          两边的提示词与书目各写一份，迟早漂成两套标准。
        
                English:
        Two things, same position:
                · `transcribe` empty → **write today's chapter** (before the show, as material for the playwright);
                · `transcribe` non-empty → **organize what actually happened today into a novel** (after wrap-up,
                  see `sim/loop._day_novel`).
                ★ Why put two things in one role instead of adding another person: **both are the novelist's job**
                  (one is "how do you plan to write it", the other is "what actually got written"), and both share the same set of
                  craft entries (chapter structure / web-fiction methodology / screenwriting canon). If split into two roles,
                  the prompts and reading lists on both sides would each be written separately, and sooner or later they would drift into two sets of standards.
        """
        if str(transcribe or '').strip():
            return await self._transcribe(ctx, transcribe)
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        # ★ 思维链骨架（2026-10-07 第七轮）：作家那一步的产出是**散文正文**，
        #   所以骨架**只进提示词、不要求落成字段**（理由见 `cognition.THINK_FIELD`
        #   上面那段）—— 让它把"这一章变什么 / 谁撞上什么 / 留了什么未了"
        #   想过一遍再动笔。
        # [EN] ★ Chain-of-thought skeleton (2026-10-07 round seven): the writer's step produces **prose body
        # [EN] text**,
        # [EN] so the skeleton **only goes into the prompt, not required to land as fields** (reason see
        # [EN] `cognition.THINK_FIELD`
        # [EN] 's paragraph above) —— let it think through "what changes in this chapter / who runs into what /
        # [EN] what's left unresolved"
        # [EN] before starting to write.
        cot = cognition_block(self.key)
        cot_block = f'\n{cot}\n' if cot else ''
        notes = ''
        if ctx.people:
            notes = f'\n\n── 今天在场的人 ──\n{"、".join(ctx.people[:12])}'
        prev_block = f'── 昨天的小结 ──\n{yesterday[:600]}\n\n' if yesterday.strip() else ''

        # ── ① 先问：这一步交给 MuMuAINovel 做吗？────────────────────
        # [EN] ── ① First ask: does this step go to MuMuAINovel? ────────────────────
        degrade = ''
        if _mumu_enabled_for(self.key):
            text, why = await _mumu_sample(
                ctx, nodes=nodes, yesterday=yesterday, craft=craft)
            if text:
                return CrewNote(role=self.key,
                                title='当天样章（MuMuAINovel · 来自创作服务）',
                                body=text)
            degrade = why                       # 回退：原因待会儿写在 note 上
            # [EN] Fallback: reason will be written in the note later

        # ★ 两条跨职位的写法约束（见 `SCENE_CARD_RULES` / `FILMABLE_RULES` 的来历）。
        #   各自独立开关：**关掉哪条就少给哪条**；两条都关 = 回到从前的提示词
        #   （编号也跟着变，免得出现"只有 5 没有 6"的断号）。
        # [EN] ★ Two cross-position wording constraints (see the origins of `SCENE_CARD_RULES` /
        # [EN] `FILMABLE_RULES`).
        # [EN] Each has its own independent switch: **turn off whichever, and that one is omitted**; both off =
        # [EN] back to the former prompt
        # [EN] (numbering changes accordingly too, to avoid a gap like "only 5 and no 6").
        _rules: list[str] = []
        if CFG.b('CREW_SCENE_CARD'):
            _rules.append('5. **场景先交代清楚**。\n\n' + SCENE_CARD_RULES)
        if CFG.b('CREW_FILMABLE'):
            _rules.append(f'{len(_rules) + 5}. **顺手让它能拍**。\n\n' + FILMABLE_RULES)
        # ★ 2026-10-10（第 01 类第 1 条）：可拍性硬规则。**不另设开关** ——
        #   它的两条规则是"能不能改编"的底线，不是风格偏好，关掉没有正当理由
        #   （真要关，那是 `CREW_FILMABLE=false` 该干的事，别再造一个旋钮）。
        # [EN] ★ 2026-10-10 (category 01 item 1): filmability hard rule. **No separate switch** ——
        # [EN] its two rules are the bottom line of "can it be adapted", not a style preference; there's no
        # [EN] legitimate reason to turn them off
        # [EN] (if you really must turn it off, that's what `CREW_FILMABLE=false` is for, don't build another
        # [EN] knob).
        _rules.append(f'{len(_rules) + 5}. **两条硬规则**。\n\n' + SCREEN_HARD_RULES)
        # ★ 2026-10-16（用户：「生成的小说不像人话」）：角色复读机 + 场景原地打转 +
        #   谶语填词，是"生成里最假"的三类，属正确性不另设开关（与 `SCREEN_HARD_RULES`
        #   同一条口径，见 `REPEAT_RULES` 注释）。样章（开演前写的那份）也要守，
        #   否则读者一翻开就出戏。
        # [EN] 2026-10-16 (user: "the generated novel doesn't sound human"): character repeat
        # [EN] machine + scene stalling + oracle padding are the three fakest kinds of generation;
        # [EN] correctness, no separate switch (same calibration as `SCREEN_HARD_RULES`, see
        # [EN] `REPEAT_RULES` docstring). The sample chapter (written before the show) must obey
        # [EN] too, or the reader is thrown out on page one.
        _rules.append(f'{len(_rules) + 5}. **对话与场景推进（别写复读机）**。\n\n' + REPEAT_RULES)
        # ★ 2026-10-12（用户点名）：**怎么说话才像个活人**。
        #   剧作家的活儿有一半就是台词，所以这一条对他**最要紧** ——
        #   它决定的是"这一句写在纸上，念出来像不像人说的"。
        # [EN] ★ 2026-10-12 (the user named this): **how to speak like a live person**.
        # [EN] Half the playwright's job *is* dialogue, so this one matters **most** to him --
        # [EN] it decides whether "this line, written down and read aloud, sounds like something a person
        # [EN] would say".
        _live = live_speech_block()
        if _live:
            _rules.append(f'{len(_rules) + 5}. **说话要像个活人**。\n\n' + _live)
        # ★★★ 2026-10-28（叙事层）：编剧写的是**故事怎么搭**（因果、时间、情绪怎么给），
        #   而机器味的大头恰好藏在这一层（只改词句只值 1.6 个点）。
        #   ⚠ 只给编剧和作家，不给演员 —— 见 `anti_fp_block()` 那条注释。
        # [EN] ★★★ 2026-10-28 (narrative layer): the playwright writes **how the story is built**
        # [EN] (causality, time, how emotion is delivered) -- and that is exactly where the bulk of
        # [EN] the machine smell hides (rewording alone is worth only 1.6 points).
        # [EN] ⚠ Novelist and playwright only, not the actor -- see `anti_fp_block()`'s note.
        _afp = anti_fp_block()
        if _afp:
            _rules.append(f'{len(_rules) + 5}. **别把"像人"改成另一种机器腔**（叙事层）。\n\n' + _afp)
        extra_rules = ('\n'.join(x + '\n' for x in _rules) + '\n') if _rules else ''
        # ★★ **本轮篇幅目标**（2026-10-11，用户在「起笔」里设的 `ROUND_DAILY_WORDS`）。
        #   设了就**盖过**那对默认区间（`CREW_STORY_MIN~MAX`），因为用户给的
        #   是一个确切的数，再叠一个区间只会让模型自己纠结听谁。
        #   没设（0）→ 一个字都不多说，与从前**逐字相同**。
        # [EN] ★★ **This round's length target** (2026-10-11, the `ROUND_DAILY_WORDS` the user set in "Start
        # [EN] Writing").
        # [EN] If set, it **overrides** that default range pair (`CREW_STORY_MIN~MAX`), because what the user
        # [EN] gave
        # [EN] is an exact number; stacking a range on top only makes the model agonize over whom to listen to.
        # [EN] Not set (0) → not a word more, **verbatim identical** to before.
        _w = max(0, int(words or 0))
        length_line = (f'约 {_w} 字' if _w
                       else f"{CFG.i('CREW_STORY_MIN')}~{CFG.i('CREW_STORY_MAX')} 字")
        # ★★★ 2026-10-17：**把"现在几点"写进提示词，并要求样章从这一刻起**。
        #   实测一次真实运行：样章开头写「**傍晚**的天光从窗里斜进来」，
        #   而推演的时钟固定从 **08:00（辰时）** 起 ⇒ 戏在早上演，剧本是傍晚的
        #   光 ⇒ 读者读到"傍晚"、正文却标着「## 辰时 08:00」，第一屏就出戏。
        #   根因：`compose` 只把 `world_brief()`（世界观 + 人物）给了作家，
        #   **一个字都没提时间**，它就自由发挥了。
        #   ⚠ 不改成"让时钟跟着剧本走"：时钟是推演的**唯一真相**（存档、停点、
        #     夜间暂停、跨天都读它），为了一句描写去倒拨它，代价远大于收益。
        #     让文字服从时钟，是这一层该做的事。
        # [EN] ★★★ 2026-10-17: **put "what time it is" into the prompt, and require the sample
        # [EN] chapter to start from that moment.** Measured on one real run: the sample opened with
        # [EN] "**dusk** light slanting in through the window" while the clock starts at **08:00**
        # [EN] (辰时) => the scene plays in the morning, the script is lit like dusk => the reader
        # [EN] reads "dusk" and the body says "## 辰时 08:00", off-key from the first screen.
        # [EN] Root cause: `compose` gave the writer only `world_brief()` (world + people) and **not a
        # [EN] word about time**, so it improvised.
        # [EN] ⚠ Not "let the clock follow the script": the clock is the **single truth** of the run
        # [EN] (save, stop point, night pause, day crossing all read it); back-dating it for one
        # [EN] description costs far more than it buys. Making the prose obey the clock is this
        # [EN] layer's job.
        _when = ''
        try:
            _clk = getattr(ctx.world, 'clock', None)
            if _clk is not None:
                _disp = str(getattr(ctx.world, 'clock_display',
                                    lambda: '')() or '').strip()
                _seg = _clk.segment() if hasattr(_clk, 'segment') else ''
                if _disp or _seg:
                    _when = (f'── 这一刻 ──\n现在是 **{_disp or _seg}'
                             f'{"（" + _seg + "）" if _seg and _disp else ""}**。\n'
                             '这一天**从这里往下走** —— 你写的第一段，'
                             '光线、声音、人手上的事，必须**就是这个时刻**的样子。\n'
                             '**不许**写成别的时段（别在早上写出傍晚的斜光）。\n\n')
        except Exception:                                        # noqa: BLE001
            _when = ''
        # ★★★ 2026-10-27：**风格控制单独一段**（不塞进 `world_brief()` ——
        #   那一串会被顶级规则挤掉，实测见 `style_block` 的说明）。
        #   这一段是"成品读起来该是什么样" ⇒ 归**作家**（演员一拍里执行不了）。
        # [EN] ★★★ 2026-10-27: **the style control gets its own section** (not inside `world_brief()` --
        # [EN] that string gets squeezed out by the top-level rules, measured; see `style_block`).
        # [EN] This section describes "what the finished prose should read like" => it belongs to the
        # [EN] **writer** (an actor cannot execute it inside one beat).
        _style = ctx.style_block()
        _style_block = (f'── 风格控制 ──\n{_style}\n') if _style else ''
        prompt = f"""你是这本小说的**作家**。今天是第 {ctx.day} 天。

{_when}{ctx.world_brief()}

{_style_block}{craft}

{prev_block}── 进度节点（主线）──
{nodes}

── 前情提要 ──
{ctx.recap()}{notes}
{cot_block}
写一段 **{length_line}** 的**原著样章**：
今天这一天，按小说的写法，该是什么样。

硬要求：
1. **接着前面的往下写**，不要另起炉灶、不要凭空造新势力。
2. **这一天要先有"日常的质地"**：喝茶、擦桌、生火、听客说话、东拉西扯 ——
   这些**不是闲笔**，是这本小说的底子。让读者先愿意跟这些人待着，
   故事才有地方长出来。
3. **主线一次只许向前一小步**：这一天结束时，"哪件**小事**变了"就够了 ——
   一个眼神、一句没说完的话、一件对不上号的旧物、一个没答上来的问题。
   **绝对不许**把谜底说出来、不许让人物讲出他此刻还不可能知道的真相、
   不许把后面几章的转折提前演掉。**慢，是要求，不是失误。**
4. 这是**小说**不是提纲：有场景、有动作、有人说话，读起来是一段文字。
   但**不要**分场、不要标"第几拍"、不要写镜头说明（那是剧作者的活）。
{extra_rules}只输出这段正文本身：不要标题、不要 JSON、不要解释你在做什么。"""
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        # purpose 沿用 `day_story`（**不是新造一个 crew_story**）：
                        # 这就是"写当天故事"那一步，只是现在由剧组里的小说作家来做。
                        # 两个名字指一件事是最容易出现"两边记录对不上"的地方。
                        # [EN] purpose continues to use `day_story` (**not a newly created crew_story**):
                        # [EN] this is the "write today's story" step, just now done by the crew's novelist.
                        # [EN] Two names for one thing is the easiest place for "the two sides' records to disagree".
                        purpose='day_story', want='text',
                        min_chars=CFG.i('CREW_STORY_MIN_FLOOR'),
                        max_tokens=CFG.i('CREW_STORY_TOKENS'))
        if not rep.ok:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why=_with_degrade('；'.join(rep.notes) or '没写出样章',
                                              degrade))
        text = rep.value if isinstance(rep.value, str) else str(rep.value or '')
        text = text.strip()
        if not text:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why=_with_degrade('样章是空的', degrade))
        # ★ 降级事实要让人看得见（标题上带一句），否则"服务明明开着、
        #   为什么产出的还是自家那一路"会变成一个查不出来的疑问。
        # [EN] ★ Degradation facts must be visible (a line on the title), otherwise "the service is clearly on,
        # [EN] why is the output still our own path" becomes an untraceable question.
        title = '当天样章（原著）' + ('｜已回退自写' if degrade else '')
        return CrewNote(role=self.key, title=title, body=text)

    async def _transcribe(self, ctx: SetCtx, raw: str) -> CrewNote:
        """**整理当天这一章**：把这一天实际发生的事，写成小说形式。

        用户 2026-10-07：「每天总结你看下包含当天故事整理吗(整理成小说形式)」。

        ⚠ 与"写当天样章"的区别要分清（两者都叫"小说"，但方向相反）：
          · 样章 = **开演前**写"今天打算演什么"，是**计划**，给剧作者当素材；
          · 整理 = **收工后**把"今天实际演成什么样"写成小说，是**记录**，
            给人读、也进「今日总结」。
          计划与实际之间的差（人物自由发挥出来的那部分）**正是这一份的价值** ——
          所以它的材料必须是**今天真正上屏的那些行**，不是当初的样章。
        
                English:
        **Organize the day's chapter**: write what actually happened that day into novel form.
                User 2026-10-07: "for the daily summary, check whether it includes organizing the day's story (organizing into novel form)".
                ⚠ Distinguish this clearly from "writing the day's sample chapter" (both are called "novel", but they point in opposite directions):
                  · sample chapter = written **before the show starts**, describing "what we plan to perform today", it is a **plan**, raw material for the playwright;
                  · organizing = after **wrapping up**, writing "what actually got performed today" into a novel, it is a **record**,
                    meant for people to read, and also goes into the "today's summary".
                  The gap between plan and actual (the part the characters improvised) **is precisely the value of this piece** ——
                  so its material must be **the lines that actually made it to screen today**, not the original sample chapter.
        """
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        # 整理成小说同样是"动笔之前先想一遍"（与写样章同一段骨架，见上）。
        # [EN] Organizing into a novel is likewise "think it through before writing" (same skeleton segment as
        # [EN] writing the sample chapter, see above).
        _cot = cognition_block(self.key)
        cot_block = f'\n{_cot}\n' if _cot else ''
        # ★★★ **不再 `[:6000]` 一刀切，改成按块整理**（2026-10-17 修）。
        #   以前这里写的是 `body = str(raw or '').strip()[:6000]` ——
        #   而一天的真实材料实测有 **44,736 字符**（30 幕，含 208 条动作、
        #   275 条心声、74 句对白）⇒ **只喂了 13%**，后面 6/7 的戏模型根本没见过，
        #   它当然只能写出 900 字（日志实测 `crew_day_novel · 2153+79 token`）。
        #   用户原话：「为何发生给你了很多事情 最后导出的内容非常少？
        #   剧情部分呢？人物对话呢？导出的应该是一个经过润色的完整的小说才对」。
        #
        #   现在：材料 <= 一块就一次过；超了就按段切块，**每块都写完整**，
        #   块与块之间把上一块的**结尾 300 字**当衔接上下文（与
        #   `export.novel_version.polish_manuscript` 同一套做法 —— 两处不要各写一份）。
        #
        #   ⚠ 为什么要分块而不是一次给 4.4 万字：
        #     ① 一次给完，模型会"挑几段写"，中段整段跳过（实测这个模型的通病）；
        #     ② 输出侧一篇 4.4 万字的材料要出 1.5 万字，超 `max_tokens` 会被截断；
        #     ③ 分块后每块都有明确的"就写这一段"，漏段概率低得多。
        #   ⚠ `CREW_DAY_NOVEL_CHUNK` 给了"改回一次过"的退路（设 0 = 不分块）。
        # [EN] ★★★ **No more one-shot `[:6000]`; organize in chunks instead** (fixed 2026-10-17).
        # [EN] It used to be `body = str(raw or '').strip()[:6000]` -- while a real day's material is
        # [EN] **44,736 characters** (30 scenes: 208 actions, 275 inner thoughts, 74 dialogue lines) =>
        # [EN] **only 13% was fed**, the model never saw the last 6/7 of the day, so of course it could
        # [EN] only write 900 characters (log: `crew_day_novel · 2153+79 token`).
        # [EN] The user's exact words: "why is the exported content so little? Where is the plot? Where
        # [EN] is the dialogue? The export should be a polished, complete novel."
        # [EN] Now: if the material fits in one chunk, one pass; otherwise split into chunks and
        # [EN] **write each one fully**, carrying the previous chunk's **last 300 characters** as
        # [EN] linking context (same approach as `export.novel_version.polish_manuscript` -- do not
        # [EN] write a second implementation).
        # [EN] ⚠ Why chunk instead of handing over 44k at once:
        # [EN]   1. given everything at once the model "picks a few passages" and skips whole middle
        # [EN]      sections (a known weakness of this model);
        # [EN]   2. a 44k-character source needs a 15k-character output, which exceeds `max_tokens` and
        # [EN]      gets truncated;
        # [EN]   3. after chunking each chunk has an explicit "write exactly this stretch", so dropped
        # [EN]      sections are far less likely.
        # [EN] ⚠ `CREW_DAY_NOVEL_CHUNK` provides the escape hatch back to one pass (set 0 = no chunking).
        body_all = str(raw or '').strip()
        # ★★★ **悬空第三人称的引语，先把那一行材料剔掉**（2026-10-19 第十一轮）。
        #
        #   用户点名"最致命"的一条：`驹子忽然安静，说"她恨我"，又笑着说"算了"` ——
        #   那句话在正文里**全文找不到"她"是谁**，情感分量很重却毫无承接。
        #   它在六次真跑里出现了五次（`snow_v10` / `v11` / `scale1` /
        #   `snow_thread3` / `snow_time1` / `ykg1000`）。
        #
        #   ⇒ 第一道闸在导演事件那侧（事件里不许有引语，见
        #     `director/engine._inject_event`）；这里是**第二道**：
        #     同样的形状从别的路进来（某个角色自己说的、心声、旁白）也拦得住。
        #
        #   ⚠ 为什么是"剔行"而不是"改写成第一人称"或"删掉引号里那句"：
        #     剔的是**材料**，不是成稿 —— 少一行不可写的材料，比让改写层
        #     顶着一声"她"硬编一句话要好。而且写这一行的人（小说作家）
        #     本来就不可能知道"她"是谁：他手上只有这些行。
        # [EN] ★★★ **Drop the lines whose quotation contains a third-person pronoun with nothing
        # [EN] to land on** (round eleven). This is the **second** gate: the first bans quoted
        # [EN] speech in injected events (`director/engine._inject_event`), this one catches the
        # [EN] same shape arriving from any other route. ⚠ It drops **material**, not finished
        # [EN] prose: one unwritable line is better than making the novelist invent a "she".
        body_all = self._drop_dangling_lines(body_all, ctx)
        chunk_size = CFG.i('CREW_DAY_NOVEL_CHUNK')

        # ★★★ **按情节单元写，不按字数切块**（2026-10-26）。
        #
        #   用户原话：「真正小说里并不一定每天都有故事 而是根据大纲 可能会快速跳过很多时间
        #   每隔一段时间才会有1个事件集中描写 …… 小说时间不是匀速流逝的」。
        #
        #   改之前这里是 `chunks = _split_for_transcribe(body_all, 6000)`：**按字数**切，
        #   每块都要求"写完整、事件一处不许漏" ⇒ 21.3 万字材料被**等密度**转写成
        #   12.9 万字，读起来是"逐块转录剧本" —— **赶路那三个月和开庭那一场一样厚**。
        #
        #   现在先切成**情节单元**（幕头里本来就带站名，见 `sim/loop._day_lines`），
        #   每个单元按它的**篇幅档**（`ingest.progress.WEIGHTS`）定写多厚：
        #   详的一站写足、略的一站两句带过。目标用**句数**给（模型不数字数）。
        #   ⚠ 一个站都没标（纯文本材料）⇒ 只有一个单元、篇幅按当前站走 ⇒ **旧行为**。
        #   ⚠ 轻的一站**不按字数再切**：切了会变成"每块写两句"，反而写多。
        # [EN] ★★★ **Write by plot unit, not by character count** (2026-10-26). It used to be
        # [EN] `_split_for_transcribe(body_all, 6000)` -- sliced by characters with every slice
        # [EN] demanding "write it in full, skip nothing", so 213k characters became 129k of prose
        # [EN] at uniform density: three months of travel as thick as the hearing. Now the material
        # [EN] is cut into **plot units** (the station name is already in every act header) and each
        # [EN] unit's thickness follows its length tier. Targets are stated in **sentences** (the
        # [EN] model does not count characters). ⚠ No station names => one unit => old behaviour.
        # [EN] ⚠ A light unit is **never** split further: splitting would mean "two sentences per
        # [EN] slice", i.e. more text, not less.
        units = UP.plan_units(
            body_all.split('\n'),
            nodes=getattr(getattr(ctx, 'world', None), 'progress_nodes', None),
            current=str(getattr(getattr(ctx, 'world', None), 'current_node', '') or ''))
        jobs = _transcribe_jobs(units, chunk_size, UP)

        texts: list[str] = []
        tail = ''
        # ★★★ 2026-10-24：**每一段开始前问一句"用户点停止了吗"**。
        #
        #   实测（望江楼 2026-10-24 那轮，`阶段「novelize」用时 2950.9s（失败）`）：
        #   22:22:44 用户点了停止（日志有 `UI 操作: 停止推演`，落盘也做了），
        #   **而整理稿照样一段一段往下写，又跑了 17 分钟**，直到 22:40:07
        #   进程收尾时才被取消 —— 那个"（失败）"就是这么来的（`stage()` 只把
        #   **抛异常**标成失败，正常收尾不会）。
        #
        #   这就是 `write_check_retry` 那条老规矩漏掉的一半：写样章问了停止，
        #   **整理这一路从来没问过**（它的段循环里一个判断都没有）。
        #   ⇒ 现在每段开始前问一次；停了就**用手上已经写好的段收尾**
        #     （钱已经花了，不能因为点了停止就把写好的那几段扔掉 ——
        #      与 `write_check_retry` 的 `best` 同一条理由）。
        #
        #   ⚠ 不打断**正在进行**的那一次调用：那是等模型返回的几十秒，
        #     硬杀没有意义（对方不会因为本地取消就退钱），而且已发出去的请求
        #     回来之后这一段本来就是可用的。所以粒度是"段"，不是"秒"。
        # [EN] ★★★ 2026-10-24: **ask "did the user hit stop?" before every chunk**.
        # [EN] Measured (the Mowenlou run of 2026-10-24, `stage "novelize" took 2950.9s (failed)`):
        # [EN] at 22:22:44 the user clicked stop (the log has `UI: stop simulation`, and the flush ran),
        # [EN] **yet the organized draft kept writing one chunk after another for another 17 minutes**,
        # [EN] only cancelled at 22:40:07 when the process wound down -- which is exactly where that
        # [EN] "(failed)" came from (`stage()` marks **an exception** as failure; a normal finish is not).
        # [EN] This is the half `write_check_retry`'s old rule missed: writing the sample chapter asked,
        # [EN] **the organizing path never asked** (its chunk loop had not a single check).
        # [EN] => Ask before each chunk; when stopped, **finish with the chunks already written**
        # [EN] (the money is spent -- dropping them because stop was clicked is worse; same reason as
        # [EN] `best` in `write_check_retry`).
        # [EN] ⚠ Do not interrupt the **in-flight** call: that is the tens of seconds waiting for the
        # [EN] model, and killing it locally neither refunds nor helps; whatever comes back is usable.
        # [EN] So the granularity is "chunk", not "second".
        def _stop_asked() -> bool:
            try:
                lp = getattr(ctx, 'loop', None)
                return bool(getattr(lp, 'stopping', False)) if lp is not None else False
            except Exception:                                    # noqa: BLE001
                return False

        from crew import doing as DOING
        stopped_at = 0
        for idx, job in enumerate(jobs):
            if _stop_asked():
                stopped_at = idx + 1
                _LOG.info('整理稿：用户点了停止 → 不再写第 %d/%d 段之后的内容'
                          '（已写好的 %d 段留下）', idx + 1, len(jobs), len(texts))
                break
            if len(jobs) == 1:
                scope = ''
            elif idx == 0:
                scope = (f'（这是这一天的第 1/{len(jobs)} 段，后面还有，'
                         '**不要收尾、不要总结这一天**）')
            elif idx == len(jobs) - 1:
                scope = (f'（这是这一天的最后一段，第 {idx + 1}/{len(jobs)} 段，'
                         '到这里才收束这一天）')
            else:
                scope = f'（这是这一天的第 {idx + 1}/{len(jobs)} 段，前后都还有）'
            link = (f'\n── 上一段写到这里（仅供衔接，**不要重复写它**）──\n…{tail}\n'
                    if tail else '')
            # ★ 段进度进 `DOING` 栈：一整天的整理实测要 49 分钟，而状态条
            #   在这 49 分钟里只会显示外层的「整理当天这一章」一个死标签 ——
            #   用户看到的正是"2800 多秒还没结束"。带上「第 5/18 段」之后，
            #   同一个数字立刻能读出"在推进、推到哪儿了"。
            # ★ 2026-10-26：再带上**这一站是哪一站、什么篇幅** —— 同一句进度里
            #   能读出"现在写的是开庭那一场还是赶路那一段"，这正是"详略"在界面上的样子。
            # [EN] Chunk progress goes on the `DOING` stack: organizing one day measured 49 minutes,
            # [EN] during which the status bar showed only the outer "organize today's chapter" label
            # [EN] -- exactly the "2800+ seconds and still not finished" the user reported. With
            # [EN] "chunk 5/18" on it, the same number instantly reads as "moving, and how far".
            # [EN] ★ 2026-10-26: also carry **which station and which length tier** -- the same line
            # [EN] now tells you whether it is writing the hearing or the journey.
            _tok = DOING.push(t('整理第 {i}/{n} 段', i=idx + 1, n=len(jobs))
                              + (f' · {job["label"]}' if job.get('label') else ''))
            try:
                one = await self._transcribe_once(
                    ctx, job['body'], scope=scope, link=link,
                    craft=craft, cot_block=cot_block,
                    unit_block=job.get('block', ''), target=job.get('target'))
            finally:
                DOING.pop(_tok)
            if not one:
                # 某一块失败不该让整天的整理白做：保住已经写好的，
                # 并如实说明少了一段（否则用户拿到的稿子会**静默缺一段**）。
                # [EN] One failed chunk must not waste the whole day's work: keep what was written and
                # [EN] say honestly that a section is missing (otherwise the user silently gets a draft
                # [EN] with a hole in it).
                if texts:
                    texts.append(f'（这一章的第 {idx + 1} 段没能整理出来，原因：'
                                 f'{one_why if (one_why := getattr(self, "_last_why", "")) else "模型没有返回"}）')
                else:
                    return CrewNote(role=self.key, ok=False, title=self.role.name,
                                    why=getattr(self, '_last_why', '')
                                    or '没能整理出这一章')
                continue
            texts.append(one)
            tail = one[-300:]
        text = '\n\n'.join(t for t in texts if t).strip()
        if not text:
            # ★ 2026-10-24：**一段都没写就因为停止**，理由要照实说。
            #   写「整理出来是空的」是把"没来得及写"说成"写了但是空"——
            #   前者是用户自己按的停止，后者是模型没产出，两件事的下一步完全不同
            #   （前者重跑一轮就有，后者要查模型/材料）。
            # [EN] ★ 2026-10-24: **stopped before a single chunk**, say so honestly.
            # [EN] "the organized draft came out empty" reports "had no time to write" as "wrote
            # [EN] something empty" -- the former is the user's own stop, the latter is the model
            # [EN] producing nothing; their next steps are completely different (a rerun fixes the
            # [EN] former; the latter needs the model/material investigated).
            if stopped_at:
                return CrewNote(role=self.key, ok=False, title=self.role.name,
                                why='还没开始整理就点了停止（这一段稿子要重跑一轮才有）')
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='整理出来是空的')
        if stopped_at:
            # ★★★ 停下来的那一版**照样交**，但要**说清只到哪儿**（2026-10-24）。
            #   ⚠ 不写成 `ok=False`：稿子是真的、可用的，缺的是后面几段。
            #     记成失败的话，`_day_novel` 会走"没整理出来"那条路，**一个字都不落盘**
            #     —— 那才是把已经花掉的钱全扔掉。
            # [EN] ★★★ A stopped draft **is still delivered**, but must **say where it ends**
            # [EN] (2026-10-24). ⚠ Not `ok=False`: the draft is real and usable; what is missing is the
            # [EN] rest. Marking it failed sends `_day_novel` down the "could not organize" path and
            # [EN] **writes nothing at all** -- which throws away everything already paid for.
            text += ('\n\n（这一章在整理到第 {i}/{n} 段时，作者点了停止 —— '
                     '上面是已经写好的部分，后面几段没有整理。）'
                     ).format(i=stopped_at, n=len(jobs))
        return CrewNote(role=self.key, title='今天这一章（整理稿）', body=text)

    def _drop_dangling_lines(self, raw: str, ctx) -> str:
        """把"引语里的第三人称指代落不到地上"的**那几行材料**剔掉。

        判据就是 `crew.prose_flow.dangling_reference`：一句引语里用了
        第三人称代词，而**同一行里、引语之前**除说话人自己之外没有出现过
        任何人名。**纯代码、零成本、一个字都不用模型。**

        ★★★ 为什么这道闸必须落在**材料行**上，不能等成稿再判
        -------------------------------------------------------
        成稿是**按段**的：`驹子望火钵边新壶，忽然安静："她恨我。"又笑："算了。"`
        这一行一旦并进段落，段里到处是人名（叶子前两行刚出现过），
        判据就看不见它了 —— 实测把窗口放宽到"同段"后，这条判据**一次都不红**。
        而**写这一行的人（小说作家）手上只有这些行** —— 连写的人都不知道
        "她"是谁，读的人更不可能知道。所以按行判，判的正是"能不能写"。

        实测安全边界：18 个真跑的 **4,959 行**材料里，这条判据命中 **2 行**，
        两次都是同一句"她恨我"，**零误报**。

        ⚠ 名字从 `ctx.people`（今天在场的人）取 —— 那是这一天人物表**唯一
          的真相**。材料里提到但不在场的人不算数：他既然不在场，就更不可能
          被一句"她"随随便便指到。
        [EN] Drop the material lines whose quotation contains a third-person pronoun with no
        [EN] antecedent in the same line. The criterion is `crew.prose_flow.dangling_reference`:
        [EN] pure code, zero model calls. ★ Judged per **line**, never on the finished draft:
        [EN] once the line is merged into a paragraph, names from neighbouring lines make the
        [EN] criterion blind (measured: widening the window to the paragraph makes it **never
        [EN] fire**). Measured safety: 2 hits across **4,959 lines** of 18 real runs, both the
        [EN] same "she hates me", **zero false positives**.
        """
        text = str(raw or '')
        if not text.strip():
            return text
        lines = text.split('\n')
        try:
            names = [str(x).strip() for x in (getattr(ctx, 'people', None) or [])
                     if str(x).strip()]
        except Exception:                                        # noqa: BLE001
            names = []
        if not names:
            # 没有在场名单 ⇒ 无从判断"有没有出现过人名"。**不判**（也不猜）：
            # 猜出来的名单会把判据变成"看运气"。
            # [EN] No cast list => no way to tell whether a name appeared. **Do not judge**
            # [EN] (and do not guess): a guessed list turns the criterion into a lottery.
            return text
        try:
            from crew import prose_flow as PF
            bad = {i for i, ln in enumerate(lines)
                   if ln.strip() and PF.dangling_reference(ln, names=names)}
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('悬空第三人称检查失败（跳过）：%r', e)
            return text
        if not bad:
            return text
        keep = [ln for i, ln in enumerate(lines) if i not in bad]
        _LOG.info('整理材料里有 %d 行的引语指代落不到地上（同行为说话人之外没有名字），'
                  '已剔除：%s', len(bad),
                  '；'.join(lines[i].strip()[:30] for i in sorted(bad)))
        return '\n'.join(keep)

    def _presence_break_note(self, body: str, ctx) -> str:
        """**标了退场的人又动了、中间没有进场标记** ⇒ 一句给作家的指令。

        判据是 `crew.prose_flow.presence_chain_breaks`：材料里 `〔退场〕X（…）`
        之后，X 又作为说话人出现在一行里，而两者之间既没有 `〔出场〕X`
        也没有换幕。**纯代码、零成本、一个字都不调模型**；没问题返回空串
        （提示词里就什么都不加）。

        ★★★ 为什么只"提醒"不"删行"（与 `_drop_dangling_lines` 的关键区别）
        -----------------------------------------------------------------------
        "悬空第三人称"可以剔行：那一行**无论如何都写不了**（连"她"是谁都不知道）。
        而"人在门外却伸手进屋"有两种完全不同的来历，**可数地分不开**：
          ① 真的断链（材料先说叶子退下，又让她进屋推壶）—— 该提醒；
          ② 合法的隔门对话（`〔退场〕叶子` 之后她说"先生，夜深了"）——
             材料行与在场动作行**格式完全相同**（都是 `名字：…`），
             删掉就会把一句真台词连材料一起删了。
        ⇒ 所以这里只把链子指给作家看（"要么补一次他回来，要么把两次
          并成一次完整动作"），**不动材料**。

        ⚠ 名字从 `ctx.people` 取（与 `_drop_dangling_lines` 同一个来源）；
          没有名单 ⇒ 一个字节都不加，不猜。
        [EN] One instruction for the novelist when the presence chain is broken.
        [EN] ★★ Why only warn and not drop the line (the key difference from
        [EN] `_drop_dangling_lines`): a dangling pronoun is unwritable either way, but
        [EN] "acting while outside" has two origins that are **countably
        [EN] indistinguishable** -- a real break, and legitimate speech through a
        [EN] closed door (the two material lines have the **identical** shape
        [EN] `name: …`). Dropping would delete a real line of dialogue along with it.
        """
        try:
            names = [str(x).strip() for x in (getattr(ctx, 'people', None) or [])
                     if str(x).strip()]
        except Exception:                                        # noqa: BLE001
            names = []
        if not names:
            return ''
        try:
            from crew import prose_flow as PF
            note = PF.presence_break_note(str(body or '').split('\n'), names=names)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('进出场断链检查失败（跳过）：%r', e)
            return ''
        if note:
            _LOG.info('整理材料里有进出场断链：%s', note)
        return note

    async def _transcribe_once(self, ctx: SetCtx, body: str, *, scope: str,
                               link: str = '', craft: str = '', cot_block: str = '',
                               unit_block: str = '', target=None) -> str:
        """整理**一次**材料（一个情节单元的一片）。返回正文；失败返回空串并把原因记在 `_last_why`。

        `unit_block` / `target` 由 `crew/unit_plan.py` 给（那一站的篇幅档 + 该写几句）。
        ⚠ 两个都缺省 ⇒ **旧行为逐字不变**：按"写完整一章"写，预算跟材料长度走。
          这条很要紧 —— 探针、判据、外部调用点（`developers/probe_*.py`、
          `tools/verify_*.py`）都是不带单元信息直接调它的。
        [EN] Organize **one pass** of material (a slice of one plot unit). `unit_block` / `target`
        [EN] come from `crew/unit_plan.py` (the station's length tier and how many sentences it
        [EN] deserves). ⚠ Both defaulting to empty means **the old behaviour, byte for byte** --
        [EN] probes, criteria and external call sites all call this without unit information.
        """
        self._last_why = ''
        # ★★★ 2026-10-17：把**开演前那份样章**当**文笔样本**递进去（见 `SetCtx.sample` 那段）。
        #   实测两份产物的差别不在"信息"，而在**笔调**：
        #     · 样章：「擦得慢，像在磨什么」「水声咚三下」「西窗的光暗了一截」；
        #     · 整理稿：「配角盘腿坐西条案，拨两下算盘，抬眼瞥主角，提笔在账页边角画圈」。
        #   同一批事件，前者像小说、后者像值班记录。把样章摆出来当尺子，是最省的修法
        #   （不额外调模型、不引入新素材 —— 那份样章本来就已经写好了）。
        #   ⚠ 只给**开头 900 字**当笔调样本：整份给会诱导模型照抄样章的内容
        #     （样章是"计划"，与实演有出入）。限定字数 + 明说"只学笔调"。
        # [EN] ★★★ 2026-10-17: feed the **pre-show sample chapter** in as a **style sample** (see the
        # [EN] `SetCtx.sample` block). The difference between the two outputs is not information but
        # [EN] **tone**: same events, one reads like a novel, the other like a duty log. Putting the
        # [EN] sample in as a ruler is the cheapest fix (no extra model call, no new material -- that
        # [EN] sample is already written).
        # [EN] ⚠ Only the **first 900 characters** as a tone sample: the whole thing invites copying its
        # [EN] content (the sample is a plan and differs from what was performed). Bounded length plus
        # [EN] an explicit "imitate the tone only".
        #   ★ 来源顺序：`ctx.sample`（显式给的样章）→ `ctx.story`（**它就是**小说作家的样章，
        #     `director.day_plan.compose` 里 `ds.story = await _write_story(...)` 那一笔）。
        #     两条路都留：`story` 在场记/宣发那边含义更宽（"今天的框架"），
        #     以后若有人把它换成剧作者的口径，`sample` 这一路还能保住笔调样本。
        # [EN] ★ Source order: `ctx.sample` (explicitly provided) -> `ctx.story` (**which is** the
        # [EN] novelist's sample, set by `ds.story = await _write_story(...)` in
        # [EN] `director.day_plan.compose`). Both paths kept: `story` means something broader to the
        # [EN] script supervisor / publicity (the day's framework), so if someone later swaps it for the
        # [EN] playwright's version, the `sample` path still preserves the tone sample.
        _sample = (str(getattr(ctx, 'sample', '') or '').strip()
                   or str(getattr(ctx, 'story', '') or '').strip())
        style_block = ''
        if _sample:
            style_block = (
                '── 同样是这位作家、同一天开场前写的样章（**只学笔调**）──\n'
                f'{_sample[:900]}\n'
                '⚠ 上面这份是**开演前**的打算，与今天实际演的有出入 —— '
                '它的**内容一个字都不要搬**，只学它怎么下笔：\n'
                '  句子长短怎么错落、环境怎么带一笔就过、动作怎么写"看得见的样子"、'
                '人物开口之前那半拍怎么写。\n\n')
        # ★★★ 2026-10-18：**今天真正上场的人**（`ROUND_CAST` / `on_stage_names`）。
        #   为什么必须有：实测某个多人样例里，决策层已按名单排除了一个没上场的角色
        #   （日志确认本轮名单只有四个人），但正文照样把那第五个人写进了屋里
        #   —— 因为作家这一侧**只拿到设定集的全部人物**，
        #   不知道今天谁上了场，就照着设定集把五个人都摆进屋里。
        #   ⇒ 把在场名单当**硬边界**递给它，并明写"名单外的人不许出现"。
        #   ⚠ 空名单 = 不限制（与 `is_on_stage` 同一口径：空表示"全体"）。
        # [EN] ★★★ 2026-10-18: **who actually took the stage today** (`ROUND_CAST` /
        # [EN] `on_stage_names`). Measured on a multi-character sample: the decision layer had already
        # [EN] excluded the absent character (the log listed only four names), yet the prose still put
        # [EN] that fifth person in the room -- because the novelist side **only receives the full cast
        # [EN] from the settings** and does
        # [EN] not know who was on stage, so it furnishes the room with all five.
        # [EN] => Pass the on-stage roster as a **hard boundary** and state that nobody outside it may
        # [EN] appear. ⚠ An empty roster means "no restriction" (same rule as `is_on_stage`).
        _os: list[str] = []
        try:
            _os = [str(x) for x in (ctx.world.on_stage_names() or [])]
        except Exception:                                         # noqa: BLE001
            _os = []
        _os_block = ''
        if _os:
            _os_block = ('\n── 今天真正上场的人（正文里**不许出现**名单外的任何人）──\n'
                         + '、'.join(_os) + '\n'
                         '⚠ 名单外的人**一个字都不许写**（不许"某某也在屋里"，'
                         '不许让他说话做事），也不要把他算进"众人都笑了"这类集合里。\n')
        # ★★★ 2026-10-21：**门口来过、并且有人理过的人 —— 在上面那条禁令上开例外**。
        #
        #   这一条是"群演在正文里 0 次"的**真正原因**（实测 mwl v4/v5/v6 三版全为 0，
        #   而 run_mwl_v6 的日志里阿九明明向柳氏打听过那位掏井匠，柳氏也反问了一句）。
        #   上面那段 `_os_block` 取的是 `on_stage_names()`，而群演在 `world.extras` 里，
        #   永远不在那份名单上 ⇒ 模型忠实地"一个字都不写"。
        #
        #   ⇒ 对"今天被叫到名字/被人对着说过话"的群演开一个**显式例外**，并写明必须写。
        #   ⚠ 只对**被理过的**开例外（`world.extras_engaged`）：没人理的群演照样不许进正文，
        #     那才是"白来一趟"。这条与 `crowd.waiting` 是同一件事的两面。
        #   ⚠ 没有这样的人时**一个字都不加**（提示词越短越被遵守）。
        # [EN] ★★★ 2026-10-21: **people who came to the door and were actually dealt with -- an
        # [EN] exception to the ban above**.
        # [EN] This is the **real reason** extras appeared 0 times (measured in mwl v4/v5/v6, while
        # [EN] run_mwl_v6's log shows Chen Wang asking "is that well-digger here for his wages?" and
        # [EN] Lady Liu answering "what do you want with him?"). It was not compressed away, it was
        # [EN] **forbidden**: `_os_block` draws from `on_stage_names()`, and extras live in
        # [EN] `world.extras`, never on that list => the model faithfully wrote "not a single word".
        # [EN] => Carve an **explicit exception** for extras named / spoken to today, and say they
        # [EN] must be written. ⚠ Only for those **dealt with** (`world.extras_engaged`): an ignored
        # [EN] extra still may not enter the prose -- that is "a wasted visit". The other side of
        # [EN] `crowd.waiting`. ⚠ Add nothing when there are none (shorter prompts get obeyed more).
        try:
            _guests = [str(x) for x in (getattr(ctx.world, 'extras_engaged', None) or []) if str(x).strip()]
        except Exception:                                         # noqa: BLE001
            _guests = []
        if _guests:
            _os_block += (
                '\n── 例外的几位：今天门口来过、而且**有人理过**的人 ──\n'
                + '、'.join(_guests[:6]) + '\n'
                '⚠ 这几位**必须写进正文**（他们跟人物说过话，那是今天真实发生过的事）——'
                '上面的禁令对他们不适用。\n'
                '⚠ 但只写**实际发生的那几句**：不要给他补来历、补下场、补心理；'
                '问过什么、答过什么，照材料写。\n')
        # ★★★ 2026-10-19 第十二轮：**进出场断链**给一句针对性指令。
        #   判据是 `prose_flow.presence_chain_breaks`（纯代码、零成本）：
        #   材料里 `〔退场〕X` 之后 X 又动了/说了话，中间没有 `〔出场〕X`。
        #   ⚠ 只在真有断链时才往提示词里加这一段 —— 没问题时**一个字都不加**
        #     （提示词越短越被遵守；常年挂一条用不上的禁令只会稀释别的规则）。
        # [EN] ★★ Round twelve: one targeted instruction for presence-chain breaks
        # [EN] (`prose_flow.presence_chain_breaks`, pure code, zero cost). ⚠ Added
        # [EN] **only when a break actually exists** -- a permanent unused ban only
        # [EN] dilutes the other rules.
        _presence_block = ''
        _presence = self._presence_break_note(body, ctx)
        if _presence:
            _presence_block = f'\n⚠ {_presence}\n'
        # ★★★ 2026-10-18：**心里话的边界按视角分档**。
        #   第一版写死"只能写视角贴着的那个人"，而《红楼梦》是**第三人称全知**
        #   （`bible.style.pov`）—— 全知视角下写多个人内心**本来是对的**，
        #   被我那条规则写成了错。分档之后：限知/第一人称才禁；全知只禁"凭空补判断"。
        # [EN] ★★★ 2026-10-18: **the inner-voice boundary now depends on point of view**. The first
        # [EN] version hardcoded "only the viewpoint character", but Dream of the Red Chamber is
        # [EN] **third-person omniscient**, where writing several people's thoughts is *correct* and was
        # [EN] made wrong by my rule. Split: limited/first-person forbids it; omniscient only forbids
        # [EN] "inventing a verdict the character never reached".
        _pov = ''
        try:
            _pov = str((getattr(ctx.world, 'style_card', None) or {}).get('视角') or '')
        except Exception:                                         # noqa: BLE001
            _pov = ''
        _limited = any(k in _pov for k in ('限知', '第一人称', '多视角'))
        if _limited:
            _inner_rule10 = (
                '10. ★★★ **心里话只有视角人物能说**（2026-10-18）。这本书是「' + (_pov or '限知')
                + '」，所以材料里的 `内心` 只许写成**视角人物自己的**：\n'
                '   · 别人的心思**一个字都不许写**（不许"他心想"，也不许用旁白替他下判断）；\n'
                '   · 不许把别人的心里话改写成叙述事实 —— 他不知道的事，叙述里也不许知道。\n')
        else:
            _inner_rule10 = (
                '10. ★★★ **心里话只能来自材料**（2026-10-18）。这本书是「' + (_pov or '第三人称全知')
                + '」，可以写多个人的内心，但只能是材料里**真的出现过**的那些：\n'
                '   · **不许替人物凭空补一个判断**（尤其"她从不觉得被怠慢"这类他从未说过的结论）；\n'
                '   · 不许把别人的心里话改写成叙述事实 —— 他不知道的事，叙述里也不许知道。\n')
        # ★★★ 2026-10-26：**这一站该写多厚**（用户：「小说时间不是匀速流逝的」）。
        #
        #   改之前提示词里只有"写完整一章""素材多就写长"两句话 ⇒ 模型只有**一个档**，
        #   于是 21.3 万字材料等密度转写成 12.9 万字（"逐块转录剧本"）。
        #
        #   现在由 `crew/unit_plan.py` 按那一站的**篇幅档**给出可数的目标（几句），
        #   并且**把互相打架的那几条改成二选一**（第 2/5/9 条）：
        #     重档要"一处都不许漏"，轻档要"只留结果、不许逐拍写" ——
        #     两条同时出现在提示词里，模型只能随机挑一条（本项目的老教训）。
        #   ⚠ `target` 为空（探针/判据/外部调用点）⇒ 三条**逐字回到旧文案**。
        # [EN] ★★★ 2026-10-26: **how thick this station should be** (user: "novel time does not
        # [EN] flow uniformly"). Previously the prompt only said "write the chapter in full" and
        # [EN] "more material -> write longer", i.e. exactly one gear, so 213k characters became
        # [EN] 129k at uniform density. Now `crew/unit_plan.py` supplies a countable target per
        # [EN] station, and the three conflicting requirements (2 / 5 / 9) become **either-or**:
        # [EN] heavy demands "skip nothing", light demands "result only, no beat-by-beat" -- both
        # [EN] at once and the model picks one at random. ⚠ Empty `target` => the old wording,
        # [EN] byte for byte (probes, criteria, external call sites).
        _density_block = f'\n{unit_block}\n' if unit_block else ''
        _t = target
        if _t is not None and getattr(_t, 'light', False):
            _rule2 = ('2. ★★ **这一站不写场面**：它是"掠过"的一站（见上面的篇幅要求）——\n'
                      '   一两句话把"过了多久 / 到了哪儿 / 变成了什么"交代完，'
                      '**不展开动作、不铺环境、不给它写对白**。\n'
                      '   读者在这里只需要一个交代，不需要一场戏。\n')
            _rule5 = ('5. ★★★ **这一站只留结果，不许逐拍写**：材料里演了很多拍，'
                      '但你**不要逐拍回译** ——\n'
                      '   挑那件真正改变了什么的事写出来，别的（过场、赶路、迎来送往、'
                      '重复的日常）**一概不写**。\n'
                      '   ⚠ 这不违反第 1 条：第 1 条管的是"不许编"，这里说的是"不必逐条写"；\n'
                      '     而"逐拍都不许漏"那一条，只对**写足的那几站**成立，不是对这一站。\n')
            _rule9 = ('9. ★★★ **长度按上面给的句数**：这一站写 '
                      f'{_t.sent_lo}~{_t.sent_hi} 句，**多一句都不行**。\n'
                      '   多写一句，这一站就变回了"写足"，全书的详略又回到一样厚。\n')
        else:
            _rule2 = ('2. 写成**一章小说**：有场面、有动作、有人说话，读下来是连贯的一段文字。\n')
            _rule5 = ('5. **事件一处都不许漏，但句子要合并**：材料里有的场次、动作、对白，\n'
                      '   **情节层面**一处都不许跳过（不许"挑几个有意思的写一写"）；\n'
                      '   而**写法上恰恰相反** —— 同一拍里的几条要合成一句，一场戏写成**连续的一段**，\n'
                      '   不是一串等长的句子。宁可写得朴素，也不能漏事件；但"漏"指的是**事**，不是句子。\n')
            _rule9 = '9. **长度**：素材多就写长，素材少就写短，**别注水**。\n'
        prompt = f"""你是这本小说的**作家**。今天这一章已经演完了，请你把它**整理成小说**。
{scope}{_os_block}{_density_block}
── 这本书 ──
{ctx.world_brief(500)}

── 你写这类文字该守的手艺 ──
{craft}
{style_block}{link}
── 今天实际发生的（按时间顺序，含台词与动作）──
{body}
{cot_block}{_presence_block}要求：
1. **就照上面实际发生的写**，不要加情节、不要改结局、不要**替**人物补心里话。
   今天没发生的事一个字都不要写进去。
1b. ★★★ **但材料里写着的心声，一条都不许丢**（2026-10-21 补，反例见下）。
   `◇ 心声 某人：…` 那些行**就是人物的动机** —— 丢了动机，读者看到的就是
   "他莫名想走 / 他莫名去擦桌子"，全篇读起来"逻辑乱"。
   ❌ 实测反例（内部稿 777 字）：材料里明明有一句「某人心里：不能再问了，再问就露馅了」，
      正文里**一句心声都没有** —— 于是他一遍遍请示要走，读者**不知道他为什么要走**
      （理由全在那句被丢掉的心声里）。同一份材料交给外部写作服务，它保留了这类心声，
      读起来才有人味。
   · 写法：**化成他自己的口气或一个迟疑的动作**（"这话问出口就收不回了"/
     "手在膝上慢慢收拢"），**不要**写成"他想：…"这种贴着标签的句子；
   · ⚠ **也不许写成破折号尾注**（2026-10-21 实测踩到的第二种偷懒形态）：
     ❌ 一句台词，后面紧跟「——」再接一句解释他心里怎么想（形如"…吧。""——后厨的柴还没劈"）
     这读起来是剧本注脚、作者旁白，不是小说。真人成稿里这种形态 **0 处**
     （8 篇成稿平均每篇 2.1 个破折号，**尾注式 0 个**）；同一份材料交给外部写作服务，
     它写的是"他满脑子都是后厨那堆没劈的柴" —— 那才叫人话。
     ✅ 正确形态是**自由间接引语**：不带标签、不带破折号，直接用**人物的判断口气**
     说出来，读者从口气就知道是谁在想（"不能再问了，再问就露馅了"）；
     ✅ 或者把它**长进动作里**（"手在膝上慢慢收拢""话到嘴边又咽回去"）。
   · 限知视角下：**视角人物自己的**心声**必须**落到正文（材料里有几条，就要有几条
     的份量）；**别人**的心声仍然一个字都不许写（见第 10 条）。
{_rule2}3. 台词保留（那是人物自己说的）；把"（谁做了什么）"这类提示改写成
   小说里的叙述句 —— 但**只改写说法，不改事实**。
4. ★★★ **这是"整理"，不是"逐条翻译"**（最容易写坏的一条，2026-10-19）。
   材料是**按拍记的流水**：一行动作、一行心声、一行环境。正文**不是**材料一行的回译 ——
   那样写出来的是分镜表，不是小说。
   · **同一段时间里的几件事要并进一个句子**：动作 + 手上的触感 + 对方的反应 +
     周围的声音，用逗号串起来，一个句号收；
   · ❌ 材料三行 → 正文三个句号：`他伸手，指尖碰了碰她耳后。声音很轻。门外没有脚步声。`
   · ✅ 并成一句：`他伸手过去，指尖碰到的那片皮肤是凉的，她没躲，屋里静得能听见灯芯炸响。`
   · ⚠ **但台词不并**（2026-10-19 真跑实证）：人物开口，就**照原样**写成一句台词，
     **不要压成"他说了……""她催他说出哪儿好"这种转述** ——
     转述把一场戏变成了摘要，而且台词数会掉一大截（实测 29 句 → 8 句）。
     并句说的是**叙述**（动作、环境、感知），不是对话。
   · ⚠ **台词一律加引号**（“”）：说话动词后面先冒号、再进引号，引号里是人物原话。
     不加引号、把原话直接接在冒号后面，读起来像剧本提示，不是小说
     —— 而剧本提示正是这本书要脱掉的那层壳。
   · **自查**：一段里如果**一句都没铺开**（全是"主语 + 动作 + 结果"这种报告句，
     没有一句带"因为 / 像是 / 一边…一边 / 直到"的长句），就是写成了清单 —— 重新铺开这一段；
   · 每一场戏**至少有一句二十五个字以上的长句**，把动作和它周围的东西一起交代完；
   · ⚠⚠ **并句 ≠ 把四件事塞进一句**：**一个句号里最多装两件事**。
     动作 + 一个反应，或者一个动作 + 周围的一样东西 —— 就这两件。
     **第三件另起一句。**
     这条给的是**可数的单位**（几件事），不是"多少个字" ——
     实测"不超过四十个字"这种字数上限模型根本不数（连跑四次长句占比 21→60→47→85.7%），
     而"最多两件事"它判得了。
   · ❌ 反例（三件事塞一句，读起来一口气喘不完）：
     `她手指拨了拨火箸，火苗跳一下，廊板响，伙计端着壶回来，弯身放下，退去没出声响。`
   · ✅ 拆成三句，每句一到两件事：
     `她拨了拨火箸，火苗跳一下。廊板响，伙计端着壶回来。伙计弯身放下，退去时没出声响。`
   · **长句掺着用**：三句里有一句长的就够，其余还是短的。长短交错才叫节奏。
   · ⚠ **段落别一写到底**：一段**三到六句**（两百字以内）就该另起一段 ——
     一次写三百多字不分段，读者看不到换气的口子（同一次真跑实测：最长一段 362 字）。
4.4 ★★★ **同一个"反应手法"整章最多两次**（2026-10-19 第十一轮，用户点名的第二条）。
   用户原话：「"慢一拍""没听清""答非所问"出现了七次以上。这个手法第一次用是惊艳，
   第二次用是强化，**第三次开始是重复，第四次之后就变成了读者的疲劳**。
   某个角色成了一个"复读机"，失去了鲜活感。」
   · 这类**现成写法**（慢一拍 / 没听清 / 迟疑 / 顿了顿 / 怔了怔 / 半晌没作声）
     **一整章最多用两次**；第三次开始必须换**别的**办法写同一个人没接住：
     ✅ 写他**做了什么却没接话**（把火箸搁在钵沿上，没抬眼）；
     ✅ 写**别人怎么看他的沉默**（她把杯子往前推了推，才发现他没动）；
     ✅ 写**他说了别的**（答一个跟刚才那句没关系的问题 —— 那就是"答非所问"，
        但读者看到的是**具体的一句**，不是一个标签）；
     ✅ 干脆**跳过他的反应**，直接写下一个动作 —— 有时候不写比写更有力。
   · ❌ 最坏的一种：同一个人连着几段都"慢一拍"。读者第二次就学会了，
     第三次开始只会觉得作者在偷懒。
4.45 ★★★ **视角要稳**（同一条，用户点名的第三条）。
   「文本在多个视角之间跳跃，没有一个稳定的锚点…读者不知道该跟谁共情。」
   · 一章**只跟一个人**：他看不见的、听不清的，读者也跟着不知道
     —— 那正是"没听清"这个手法该起的作用，而不是靠旁白替他说；
   · 别人的心里话**一个字都不许写**（只能通过他说的话、做的动作、脸上的样子呈现）；
   · ⚠ 换视角只能**换段**，不许**换句**：同一段里从"他觉着"跳到"她觉得"，
     读者会当场出戏。
4.5 ★★★ **时间只准从幕头来**（2026-10-19 第六轮，用户点名的第一条问题）。
   材料里每一幕开头有 `〔第 N 幕 · 子时 23:40 · 地点〕` —— **那是唯一的时间真相**。
   · 事件按幕的先后写，**不许把后面那一幕的事挪到前面**；
   · 交代时间只准用幕头给的钟点/时段，**不许自己编"夜深了""天亮了"**；
   · **"终于到了""一路辛苦""刚到"这类事，一整章只能出现一次** ——
     人只到一次。实测里有一个角色说了两遍"终于到了"，读者立刻就乱了；
   · 同一个时段转折（"夜深了""更鼓一声"）**整章最多两三次**，不要每段都盖一个章；
   · ⚠ 台词里可以提到时间（人物自己说"夜深了"没问题），**不许的是叙述去盖章**。
   · ⚠⚠ **也不要每段都盖一个时间戳**（2026-10-19 第六轮实测）：只加了"按幕头写时间"
     之后，产出变成了「二十三点三十分…二十三点三十五分…二十三点三十六分…
     二十三点三十八分…二十三点四十四分」—— 五处钟点，读起来像**日志**，不像小说。
     ⇒ **全篇最多两处**（换场时 / 真的过了一大段时间），而且这么写：
       ✅ `更鼓敲过三下，廊下的灯已经灭了`（时间藏在事里）
       ✅ `雪停了很久，屋里的炭换过一回`
       ❌ `二十三点三十五分，她从廊下折回`（钟点当句首，像值班记录）
     其余地方**一个字都不要交代时间** —— 让先后顺序自己说明时间在走。
4.6 ★★★ **外部动静必须有人接**（2026-10-19 第六轮，用户点名的第三条）。
   「某几样反复出现的物象……成了装饰品，而非推动情节或揭示心理的工具」；
   「某样东西倒了、或者响了一声之后，角色并没有因此产生新的情绪或行动，只是继续之前的对话」。
   · 材料里凡是**物理上的动静**（酒洒了、碗磕了、炭塌了、门被风磕了一下）——
     写完之后**必须有人对它作出反应**：手停住、话没说完、抬眼、去擦、或者当作没看见；
   · 最要紧的一种：**动静打断了谁**。她正在追问，酒洒了 ⇒ 那句话就没说完 ——
     把**被打断的那半句留在原地**，比接着把话说完真实得多；
   · ❌ 不许"动静 + 然后继续原来的对话"这样的并排放置 —— 那是布景，不是场景。
4.7 ★★★ **配角不是跑腿的**（同一条，用户点名的第四条）。
   实测里有一个配角整场只做两件事：送东西、提醒。那不是人，是推动场景转换的开关。
   · 每个人**都想要点什么**，哪怕是小事（想回屋、想看住门、想被留下、想被记住）；
   · 所以配角除了送东西，**至少有一处是"他自己的"**：一个多余的举动、
     一句不必要的话、一次迟疑 —— 那才是活人；
   · ⚠ 但不要给他加戏加旁支：一句话、一个动作就够，不能抢主线。
   · ❌ 别让一个人整场只出现在"送茶 / 铺被 / 报时辰"这类**差事**上 ——
     那不是配角，是服务铃。
4.8 ★★★ **沉默要换着法子写**（2026-10-19 第十一轮，用户点名的一条）。
   用户原话：「某个角色沉默无层次：全段只有'一句话不说'和'嗯……'两种反应，
   建议用身体语言 / 感知细节 / 回忆联想增加层次。」
   · 人物没接住话时，**不许每次都写"没应，看某个东西"** —— 
     这个成套句式**一天最多出现一次**；
   · 换着来：**手上的动作**（他把火箸搁在钵沿上，没抬眼）、
     **别人看见他沉默的样子**（她把杯子往前推了推，才发现他没动）、
     **他想起的一件事**（他想起去年也有人这样问过他）、
     或者**干脆不写这个反应**，直接写下一个动作；
   · ❌ 最坏的一种：同一个人连着几段都是"不应声 + 看一眼"。读者第二次就学会了。
4.9 ★★★ **口癖与细节，各最多两次**（同轮，用户点名的另一条）。
   原话：「"你这个人哪"4 次、"炭塌了"2 次。建议精简至 2 次。」
   · 同一句**口头禅**（同一个人的同一段话）**一天最多两次**，
     第三次开始必须换成别的说法，或者让别人替他把话说完；
   · 同一个**道具状态**（炭塌了、灯灭了、酒凉了）**一天最多交代两次**，
     其余地方让它在别人手底下**换个样子出现**，或者只写它在场、不写它的状态；
   · ⚠ 道具**名字**反复出现不算重复（真人一章里"漏刻"能出现四五回）——
     算重复的是**同一件东西经历了同一次变化**。
{_rule5}6. ★★★ **台词之间要有来去**（材料按拍记，直接并排会读成各说各的，2026-10-19）。
   · 后一句要能看出在**回**前一句：答、反问、或者没答但被那句话改变了手上的动作；
   · 一个人说完，另一个人的反应**先落下来再开口**（他停了一下才说 / 她把杯子放下）；
   · 材料里两句话如果确实接不上，**用一句动作或环境垫在中间**把时间接过去，
     不要光秃秃地并排放着；
   · 一场戏里的话要围着**同一件事**转；某句台词若跟这场戏没关系，
     宁可写成"他没接这句，转头看别处"，也不要让它孤立地站着。
   · ❌ 三句并排、各说各的：三个引号各自独立、中间没有动作或反应垫着，
     而且前一句和后一句看不出半点关系（一句问、一句说别的、一句自言自语）。
     读者既不知道谁在跟谁说话，也看不出这三句是不是同一件事。
     ⚠ **这里故意不给例句** —— 给了会被原样抄进正文（实测过：反面例子照样抄）。
7. ★★★ **心里话要有主，而且不许漏**（2026-10-19 定"要有主"，2026-10-21 补"不许漏"）。
   材料里的 `内心` **不能直接抄成一句裸的疑问或感叹** ——
   读者会以为是叙述者在问，或者根本不知道是谁在想。
   · ❌ `走廊上是谁？`
   · ✅ `他没问。走廊上是谁，他听了两遍也没听出来。`
   · ✅ `她心里过了一遍：这话该不该问。`
   也可以把心里话化成动作里的迟疑（手停在半空、话到嘴边咽下去），
   但**不能留下一句没有主人的问句**。
   ★ **也不许整条不写**：材料里出现了几条心声，正文里就该有几处的份量。
     那是动机，不是描写（见第 1b 条）。
8. ★★★ **同一件事最多三次，而且一次要比一次多知道一点**（2026-10-21 合并重写）。
   这一条原来是**两条互相打架**的规则：一条让「删到只剩一次」、一条让「写足两三次」——
   同一件事写在两处、说的还不一样，模型只能随机挑一条（"同一件事两处实现"）。
   现在合成一条，并且补上原来两版都缺的那一半：**光是减少次数不算改好，
   每次重复都要让读者多知道一件事**。

   · 材料里一件事反复五六次是**正常的**（人物在打转，那正是这一场的病）；
     整理时**最多留三次**，第四次起用一句带过（"茶又添了一回"）——它们是时间的重量；
   · **三次各管一件事**，这是判断"该不该留"的唯一标准：
     ① **立规矩**：读者第一次发现"这件事不对劲"（某样东西不该是这样，偏偏又这样了）；
     ② **试规矩**：有人试图对抗它、**失败**了 —— 读者由此知道它不是巧合；
     ③ **破规矩**：它变了形（同一件东西上又叠了一样新的异常）—— 读者知道
        之前那两回不是重复，是一条线在往前走；
   · ❌ 反面（真跑实测，读者第四遍就猜到结局）：
     「壶里空了」→「壶嘴又渗水」→「壶又空了」—— 三遍都是同一句话换个说法，
     **读者处境没有变化**，那就等于只写了一遍；
   · ✅ 自查一句话：**把这三处并成一处，读者会少知道什么？** 说得出来就是三次变奏，
     说不出来就是一次重复铺了三遍 —— 删到一次；
   · ⚠ **但不许删戏**：省下的篇幅补给**别的细节**（手上的动作、屋里的变化、
     别人在做什么），**字数不许因此缩水**（用户原话：「适当去掉口头禅但是不要减少字数」——
     上一轮真发生过 1225 字被压到 534 字）。删掉的那几处，要用**他手上的动作、沉默、
     这场戏的细节**补足 —— 只说"不许变短"不给出路，模型就会改成注水。
     这类台词的毛病从来不是"说了废话"，而是"手上的事没有往前走"。

{_rule9}9.5 ★★★ **这地方的「怪」，得是一条规矩，不是一堆现象**（2026-10-21 新加）。
   上面材料里给了「这本书的设定集」，里面写着这地方怎么回事、守什么规矩 ——
   **所有异常都必须能从那条规矩推出来**，不许这一章临时再立一条新的。
   · 读者心里要能回答一句：「这地方的怪，是**哪一种**怪？」
     （是「这里的人忘了自己已经死了」，还是「有个东西在按自己的记忆改这屋子」？）
     —— 答得出来，读到第三个异常他会自己开始推理；答不出来，他只看到一堆零碎怪事；
   · ❌ 反面（真跑实测）：一件东西永远不该满却永远不满（像鬼打墙）+ 一件东西自己回到
     本该不在的地方（像物品有灵）+ 一个人身上少了一样该有的东西（像是非人）——
     三件怪事**各自指向一个不同的解释**，
     谁都说得通、又谁都不成立，读者到最后也不知道自己在读哪一类故事；
   · ✅ 做法：这三件怪事如果都是**同一条规矩**的不同表现，就把那条规矩的**同一处细节**
     重复给它看（都是「井水」的事、或都跟「影子」有关），让读者自己把它们串起来；
   · ⚠ 材料里没有那条规矩、只有零碎怪事时：**照实写那些怪事，不要替它编一条规矩**
     （那是「新增设定」，违反第 1 条）—— 但也不要为了「能解释」而把怪事写弱。
{_inner_rule10}   ⚠ 有据可查：实测出现过"某个没开过口的人，被叙述者代说了心事"、
     "视角人物替另一个当时并未开口的人安了一句心思"。
11. ★★★ **称谓不是名字**（2026-10-18）。`奶奶`／`太太`／`老太太`／`母亲` 这类是**当面称呼
   或贴身视角里的叫法**，**不能当叙述里的专名用**：
   · 叙述句里第一次出现某人，用**名字或名字+身份**；
   · 只有**对话里**、或**视角人物心里**，才用称谓；
   · 通篇拿称谓当这个角色的名字用（叙述里一律写「太太」「奶奶」而不写名字）
     读起来像分镜表，**不是白描**。
12. 只输出这一章正文：不要标题、不要 JSON、不要解释你在做什么。"""
        # ★★ **输出的 token 上限要跟材料长度走**（2026-10-17）。
        #   `CREW_DAY_NOVEL_TOKENS` 是**用户可改的配置**，而老用户的 `.env` 里
        #   还存着 2600（旧默认值）—— 光把代码里的默认值改成 6000 **不管用**，
        #   `.env` 会继续压着它。实测：材料 3,637 字整理出来 1,757 字
        #   ≈ 2,600 token，正好卡在上限上 —— 再多写一点就被截断。
        #   ⇒ 取 `max(配置值, 材料长度×0.8)`：配置只当**下限**，材料多就自动给足。
        #     （中文约 1 字 ≈ 1.5 token，材料整理成小说通常压缩到 0.4-0.6 倍，
        #       ×0.8 是留了余量的。）
        # ★★★ 2026-10-26：**有篇幅目标时，预算按目标给，不按材料给**。
        #   按材料给（下面那条老规矩）在轻档上是灾难：一站材料 6000 字、目标两句，
        #   预算却给到 4800 token ⇒ 模型就放开写 3000 字，"略过"又变成了"写足"。
        #   ⚠ 无目标（探针/判据/外部调用点）⇒ **逐字回到老规矩**（判据 C1/C2/C3 钉着）。
        # [EN] ★★★ 2026-10-26: with a length target, the budget follows the **target**, not the
        # [EN] material. The old rule is a disaster on light tiers: 6000 characters of material
        # [EN] and a two-sentence target would still get 4800 tokens, so the model rambles.
        # [EN] ⚠ No target => the old rule, byte for byte (criteria C1/C2/C3 pin it).
        if _t is not None:
            budget = int(max(400, getattr(_t, 'tokens', 0) or 0))
        else:
            budget = max(CFG.i('CREW_DAY_NOVEL_TOKENS'), int(len(body) * 0.8))
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        purpose='crew_day_novel', want='text',
                        max_tokens=budget)
        if not rep.ok:
            self._last_why = '；'.join(rep.notes) or '没能整理出这一章'
            return ''
        prose = await self._fix_flat_paragraphs(str(rep.value or '').strip())
        prose = await self._fix_repeats(prose)
        # ⚠ 顺序：先收拢**内容**（打转），再把**牛头不对马嘴**的链条接上，
        #   再修**不成立的句子**（自洽），最后收拾**排版**（拥挤）与**元叙述**。
        #   反过来会让拆好的段被内容重写再搅一遍；而元叙述必须最后 ——
        #   它是"多写了一句"，任何先跑的重写都可能再添一句。
        # [EN] Content (spin) first, then the unanswered-question chain, then implausible
        # [EN] sentences, then layout (crowding) and the deterministic meta strip: the
        # [EN] reverse order lets later rewrites scramble what earlier steps just fixed.
        # ★★★ `style_rounds=1`（2026-10-25）：整理稿这条路上**文风类只改第一轮**。
        #   实测（望江楼那轮）：93 次调用里 50 次是 Reflexion 在整段重写，
        #   触发它的是「细节复读」「憋气」「平铺」—— 全是文风类；
        #   而"文风类不触发退回、只有实病才触发"本来就是本项目写在规则里的。
        #   上面两行（`_fix_flat_paragraphs` / `_fix_repeats`）已经在**进复查之前**
        #   把文风类各改过一遍了 ⇒ 复查里再为它多跑几轮，改的是自己刚写出来的东西
        #   （日志实测"太挤"12→21→37，越改越挤）。
        #   ⚠ 只动"要不要再跑一轮"，第一轮照改 —— 活还得做，只是不许它无限续。
        #   ⚠ 实病（元叙述/感知自洽/问答悬空/拥挤）**不受影响**，照旧改到为止。
        # [EN] `style_rounds=1`: on the organizer path, **style classes only run round 1**.
        # [EN] Measured: 50 of 93 calls were Reflexion rewriting whole chunks, triggered by
        # [EN] repetition / breathless / flat -- all style classes -- while "style classes do not
        # [EN] trigger a rewrite" is already this project's own rule. The two lines above already
        # [EN] gave each style class one pass *before* the checkup, so extra rounds just rewrite
        # [EN] their own output (log: crowding 12 -> 21 -> 37). Real defects are unaffected.
        out = await self._checkup(prose, tag='整理稿', style_rounds=1)
        # ★★★ 2026-10-26：**轻档写超了就剪**（详/中绝不剪）。
        #
        #   提示词里写了"只写一两句"，实测遵循率只有 40~74% ⇒ 关键约束必须在**解析层**做。
        #   而这两档的全部意义就是"一两句带过"：放它写成 800 字，这一站就还是"写足"，
        #   全书的详略又回到一样厚 —— 而那不是模型随机犯错，是这一层没管住。
        #   ⚠ 只按**句末**剪（剪出来是完整句子）；一句话都没收住时不剪（半句更糟）。
        #   ⚠ 剪了多少**要留痕**在日志里 —— 静默剪稿等于静默丢内容。
        # [EN] ★★★ 2026-10-26: **trim an over-long light pass** (heavy tiers are never trimmed).
        # [EN] The prompt says "one or two sentences" but obedience runs 40-74%, so the constraint
        # [EN] has to live in the parsing layer. These tiers exist to be one or two sentences; an
        # [EN] 800-character station is "written in full" again and the book goes back to uniform
        # [EN] density. Trim only at a sentence end, never when not a single sentence ended, and
        # [EN] always log how much was cut -- a silent trim is a silent content loss.
        if _t is not None and out:
            _kept, _cut = UP.trim_light(out, _t)
            if _cut:
                _LOG.info('整理稿：轻档（篇幅 %s）写超了 → 按句末剪到 %d 字（删 %d 字）',
                          getattr(_t, 'weight', ''), len(_kept), _cut)
                out = _kept
        return out

    # ══════════════════════════════════════════════════════════
    #  R48 多轮检查：跑一轮 → 数一遍 → 没清干净再来一轮
    # ══════════════════════════════════════════════════════════
    async def _checkup(self, text: str, *, rounds: int = 0,
                       tag: str = '正文', hint: str = '',
                       style_rounds: int = 0, on_round=None) -> str:
        """**多轮检查修复的总入口**（Reflexion 路径 / 旧路径可切）。

        ★★★ 2026-10-20 架构重做：判定权从"写稿的那一方"交给确定性验收层
        ------------------------------------------------------------------
        旧实现（现名 `_checkup_legacy`）的四个结构性缺陷：
          ① 每一步自己判自己写得好不好，跨类退化（修好 A、弄坏 B）没人看得见；
          ② 被拒的尝试整份丢掉，下一轮从零瞎试；
          ③ 一轮只有一个候选，被闸拦下就放弃；
          ④ 收敛判据是单标量求和，把"两类互换"看成"没变化"。
        新路径（`crew/reflexion.py` + `crew/verdict.py`）补齐：
          · 验收层**多目标分别判**、退化就拒、硬约束先于优劣、满分可疑；
          · 被拒时写一条**带原句的教训**进有界记忆，下一轮进提示词；
          · 每步可生成多个候选（`repair_recipes` 里按 kind 定，确定性动作只给 1）；
          · 收敛看**加权**，且 archive 按「毛病 / 台词 / 字数」三级排序取最优
            —— 这一条修掉了旧版"同分时保留原文、把整轮修改丢掉"的真缺陷。
        ⚠ `PROSE_REFLEXION=0` 逐字回到旧路径（判据 `Z6` 钉着"两条都还在"）。
        [EN] Entry point for multi-round repair. Default path is Reflexion: the
        [EN] deterministic verdict layer owns the decision (per-class, reject on any
        [EN] regression), rejected attempts become traceable lessons, and the archive
        [EN] ranks by defects/speeches/length instead of a single sum.
        """
        if not text:
            return text
        from crew import prose_flow as PF
        tok = PF.set_reflect_hint(hint) if hint else None
        try:
            if not _reflexion_on():
                return await self._checkup_legacy(text, rounds=rounds, tag=tag)
            return await self._checkup_reflexion(text, rounds=rounds, tag=tag,
                                                 style_rounds=style_rounds,
                                                 on_round=on_round)
        finally:
            if tok is not None:
                PF.reset_reflect_hint(tok)

    async def _checkup_reflexion(self, text: str, *, rounds: int = 0,
                                 tag: str = '正文',
                                 style_rounds: int = 0,
                                 on_round=None) -> str:
        """Reflexion 路径：确定性验收 + 有界教训库 + Pareto archive。

        `on_round` —— 细粒度进度回调（2026-10-28 加），见 `prose_checkup` 的注释。

        `style_rounds` > 0 时**文风类只改到第几轮**（0 = 不限）——
        理由见 `crew.reflexion.reflect` 的 `style_rounds`：为"重复/憋气/平铺"
        一轮轮整段重写，是 49 分钟里那 50 次改写的主要来源，而本项目自己的规则
        写明"文风类不触发退回"。整理稿这条路实测最贵，所以只有它打开了这个上限。
        [EN] `style_rounds` > 0 caps how many rounds **style** classes may run (0 = unlimited).
        """
        from crew import prose_flow as PF
        from crew import reflexion as RX
        from crew import repair_recipes as REC
        try:
            limit = int(rounds or CFG.i('PROSE_CHECK_ROUNDS'))
        except Exception:                                        # noqa: BLE001
            limit = 5
        if limit < 1:
            limit = 1
        try:
            patience = max(1, int(CFG.i('PROSE_CHECK_PATIENCE')))
        except Exception:                                        # noqa: BLE001
            patience = 2
        cur = text
        # ★ 第 0 步：引号归一（确定性、幂等、零调用）—— 放在所有轮次之前，
        #   放进轮次里只会白跑（它不会失败，也不会再产生新收益）。
        try:
            cur = PF.normalize_quotes(cur)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('引号归一失败（原样继续）：%r', e)
        if PF.issue_total(PF.prose_issue_count(cur)) == 0:
            _LOG.info('检查（%s）：开跑前就没有可数的毛病', tag)
            return cur
        try:
            steps = [(getattr(self, r.attr), r.label, r.n_best)
                     for r in REC.ordered() if getattr(self, r.attr, None)]
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('检查（%s）：修复合约装配失败，退回旧路径：%r', tag, e)
            return await self._checkup_legacy(cur, rounds=rounds, tag=tag)
        _LOG.info('检查（%s）：Reflexion 路径，%d 步 / 最多 %d 轮%s', tag, len(steps), limit,
                  ('（文风类只改 %d 轮）' % int(style_rounds)) if int(style_rounds or 0) > 0 else '')
        try:
            res = await RX.reflect(cur, steps, trials=limit, patience=patience,
                                   memory=RX.Memory(), tag=tag,
                                   style_rounds=int(style_rounds or 0),
                                   style_labels=REC.style_labels(),
                                   on_round=on_round)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('检查（%s）：Reflexion 失败，退回旧路径：%r', tag, e)
            return await self._checkup_legacy(cur, rounds=rounds, tag=tag)
        return res.text or cur

    def _check_round_steps(self) -> list:
        """一轮里要跑的步骤，**顺序就是"改坏风险从小到大"**，并带上**它负责哪一类**。

        ⚠ 这个顺序不是随手排的，每一条都踩过：
          · 先**删**（元叙述剥离、打转逐条删）：确定性动作，不会写进新东西；
          · 再**改内容**（打转重写、答非所问、道具循环、自洽）：要模型，
            可能写坏，所以排在删之后 —— 删掉的不会被动回来；
          · 最后**排版**（拥挤、平铺）：把前面改松的段收一收，必须收尾。
        ⚠ `_fix_meta_narration` 一定在**最后**：它是"多写了一句"，
          任何先跑的重写都可能再添一句（R44 的教训）。

        ★★★ **每步要报出"我负责哪一类"**（2026-10-20 实测后加的）：
          多轮刚上线时，第 2 轮是**把八步全重跑一遍**，结果是
          `平铺段 2 → 3 → 6` —— 越改越差。根因很具体：
          `_fix_flat_paragraphs` 第 2 轮看到的是**它自己上一轮重写的结果**，
          于是把刚写好的段又判成"平铺"再重写一次，一轮比一轮平。
          ⇒ 有了这张对照表，`_checkup` 每轮就能**只跑还有希望的那几步**：
            某一类已经清到 0 ⇒ 跳过它；某一类上一轮被它改**多**了 ⇒ 也跳过。
          ⇒ 这比"盲目多跑几轮"既省钱又更好，这才叫质量优先。
        [EN] Each step reports the class it owns. Running all eight steps every round
        [EN] made things worse (flat paragraphs 2 -> 3 -> 6) because
        [EN] `_fix_flat_paragraphs` re-judges **its own previous rewrite** as flat.
        [EN] Owning a class lets `_checkup` skip steps whose class is already clean or
        [EN] which made that class worse last round.
        """
        # ★★★ 2026-10-20：顺序的**唯一事实来源**换成 `crew/repair_recipes.py`。
        #   以前这张列表在这里、跳过规则在 `_steps_to_run`、计数在
        #   `prose_flow.prose_issue_count`、判据在 verify 脚本 —— 加一类毛病要改四处，
        #   漏一处就"数得出来但没人修"。现在改一处，而且"没人负责的类"由判据查出来。
        from crew import repair_recipes as REC
        return [(fn, label) for fn, label in REC.build(self)]

    def _steps_to_run(self, round_no: int, counts: dict,
                      regressed: set) -> list:
        """这一轮**该跑哪几步**（纯函数，可离线测）。

        规则（从第 2 轮起生效）：
          ① 这一类已经清到 0 ⇒ **跳过**（没什么可修，重跑只会添乱）；
          ② 这一类上一轮被改**多**了 ⇒ **跳过**（它在反复判自己的产物）；
          ③ `元叙述` 那一步**永不跳过** —— 它是确定性剥离，不会写进新东西。
        第 1 轮全跑（那时还没有历史可依据）。
        [EN] Which steps to run this round. From round 2 on: skip a step whose class is
        [EN] already zero or which inflated that class last round. The deterministic meta
        [EN] strip never skips.
        """
        steps = self._check_round_steps()
        if round_no <= 1:
            return steps
        out = []
        for step, cls in steps:
            if cls == '元叙述':
                out.append((step, cls))
                continue
            if int((counts or {}).get(cls, 0)) == 0:
                continue
            if cls in (regressed or set()):
                continue
            out.append((step, cls))
        return out

    async def _checkup_legacy(self, text: str, *, rounds: int = 0,
                              tag: str = '正文') -> str:
        """**旧的多轮检查**（`PROSE_REFLEXION=0` 时走这条；保留是为可回退）。

        用户原话：「我希望一开始写小说和最后导出的时候都可以进行几轮的问题检查
        也修复，把常见的问题都修复掉」。

        两条止损（不然会烧钱烧到天亮）：
          ① **连续几轮都没变少才停**（`PROSE_CHECK_PATIENCE`，默认 2）：
             一轮没变少**不代表改不动了** —— 模型有抖动，同一句它可能这一轮改
             不动、下一轮换个说法就通了。所以给它**一次喘息**再判死刑。
             （2026-10-20 作者原话：「成本可以接受 以质量优先」⇒ 从"一轮就停"
              放宽到"连续两轮没进展才停"。）
          ② **轮数封顶**：`rounds` 缺省读 `PROSE_CHECK_ROUNDS`（默认 5）。
        ⚠ 计数只算**确定性检测器**（`prose_flow.prose_issue_count`）：
          判官类（打转 / 自洽）会抖动，拿它们当收敛判据会让循环被噪声带着跑。
        [EN] Multi-round checkup. Two brakes: stop after `PROSE_CHECK_PATIENCE`
        [EN] consecutive rounds without progress (one flat round can be model jitter,
        [EN] not a dead end), and cap the rounds. Only deterministic detectors feed the
        [EN] count -- judge-based checks jitter and would drive the loop on noise.
        """
        if not text:
            return text
        try:
            limit = int(rounds or CFG.i('PROSE_CHECK_ROUNDS'))
        except Exception:                                        # noqa: BLE001
            limit = 5
        if limit < 1:
            limit = 1
        try:
            patience = max(1, int(CFG.i('PROSE_CHECK_PATIENCE')))
        except Exception:                                        # noqa: BLE001
            patience = 2
        try:
            from crew import prose_flow as _PF
        except Exception:                                        # noqa: BLE001
            return text
        cur = text
        # ★★★ **第 0 步：引号归一**（确定性、幂等、零调用，2026-10-20 实测补）。
        #   `snow_v24` 整篇 24 个英文 `"`、0 个中文引号 —— 中文小说里这是硬伤，
        #   但**没有任何检测器管它**：`_QUOTED` 两种引号都认，下游一切照常工作。
        #   放在所有轮次之前，是因为它幂等且不会失败；放进轮次里只会白跑。
        # [EN] Step zero: normalise quotes. `snow_v24` had 24 ASCII quotes and zero
        # [EN] Chinese ones -- a hard defect in Chinese prose that no detector caught,
        # [EN] because `_QUOTED` accepts both. Idempotent, so it runs once up front.
        try:
            cur = _PF.normalize_quotes(cur)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('引号归一失败（原样继续）：%r', e)
        prev_total = _PF.issue_total(_PF.prose_issue_count(cur))
        if prev_total == 0:
            _LOG.info('检查（%s）：开跑前就没有可数的毛病', tag)
            return cur
        # ★★★ **保留最好的一版**（2026-10-20 实测必须这么做）：
        #   每一轮都是"删几处、又添几处"，某一轮可能**某一类反而变多**
        #   （实测 v20：平铺段 2 → 3，因为重写那两段又写成了平铺）。
        #   只看"最后一轮"就会把更差的稿子交出去。
        #   ⇒ 每轮结束比一次总数，留下**总数最小**的那一版；轮次跑完取它。
        #   这与"没变少就停"是两件事：那个防白烧钱，这个防交出更差的稿子。
        # [EN] Keep the best version seen: a round can fix two classes and inflate a
        # [EN] third (measured: flat paragraphs 2 -> 3), so returning "whatever the last
        # [EN] round produced" can hand back worse prose. Track the minimum total.
        best_text, best_total, best_round = cur, prev_total, 0
        flat = 0                     # 连续几轮没有进展
        # 上一轮每个类的结果（用来决定下一轮跳掉谁）
        prev_counts = dict(_PF.prose_issue_count(cur))
        regressed: set = set()       # 上一轮被"自己的步骤"改多了的那些类
        _LOG.info('检查（%s）：第 1 轮开始，待修 %d 处（上限 %d 轮，'
                  '连续 %d 轮没进展才停）', tag, prev_total, limit, patience)
        for i in range(1, limit + 1):
            before = _PF.prose_issue_count(cur)
            before_total = _PF.issue_total(before)
            for step, cls in self._steps_to_run(i, before, regressed):
                # ★★★ 从第 2 轮起**只跑还有指望的那几步**（规则见 `_steps_to_run`）。
                # [EN] From round 2 on, run only the steps that still have a chance.
                try:
                    cur = await step(cur)
                except Exception as e:                           # noqa: BLE001
                    _LOG.warning('检查第 %d 轮：%s 失败（跳过这一步）：%r',
                                 i, getattr(step, '__name__', step), e)
            after = _PF.prose_issue_count(cur)
            after_total = _PF.issue_total(after)
            _LOG.info('检查（%s）第 %d 轮：%d → %d 处（%s）',
                      tag, i, before_total, after_total,
                      _PF.checkup_report(before, after))
            # 记下"这一轮把哪一类改多了"——下一轮就跳过那一步
            regressed = {k for k in set(before) | set(after)
                         if int(after.get(k, 0)) > int(before.get(k, 0))}
            if regressed:
                _LOG.info('检查（%s）第 %d 轮：这些类被改多了（下一轮跳过对应的步骤）：%s',
                          tag, i, '、'.join(sorted(regressed)))
            prev_counts = dict(after)
            if after_total < best_total:
                best_text, best_total, best_round = cur, after_total, i
            if after_total == 0:
                _LOG.info('检查（%s）：第 %d 轮后清干净了', tag, i)
                break
            flat = flat + 1 if after_total >= before_total else 0
            if flat >= patience:
                _LOG.info('检查（%s）：连着 %d 轮没有变少（%d → %d），'
                          '再试也是白烧，停在这里', tag, flat,
                          before_total, after_total)
                break
            if i >= limit:
                _LOG.info('检查（%s）：到轮数上限 %d，还剩 %d 处',
                          tag, limit, after_total)
        if best_round and best_text is not cur:
            _LOG.info('检查（%s）：取第 %d 轮那一版（%d 处，比最后的 %d 处更好）',
                      tag, best_round, best_total,
                      _PF.issue_total(_PF.prose_issue_count(cur)))
        return best_text

    def _cast_names(self, text: str) -> tuple[str, ...]:
        """这一章里出现过的人名（给 `prose_flow.split_long_sentences` 选切点用）。

        ★ 为什么要传：切在**人名前面**（"……回来，伙计端着……"）后半段就有了主语；
          切在别的词前面常常切出"弯身放下："这种碎片（见那边的说明）。
        ⚠ 从**正文本身**取（按 2–3 字高频片段），不去问世界 —— 整理稿里出现的人
          才是这一章的人，世界里的名单还包括没上场的。
        [EN] Names appearing in this chapter, so the sentence-splitter can prefer breaking right
        [EN] before a subject. Taken from **the text itself** (frequent 2-3 char fragments), not
        [EN] from the world: the people in this chapter are the ones who matter here.
        """
        try:
            from collections import Counter
            import re as _re
            body = _re.sub(r'[^\u4e00-\u9fff]', '', str(text or ''))
            cand: Counter[str] = Counter()
            banned = {'自己', '什么', '怎么', '这个', '那个', '一个', '就是', '不是',
                      '还是', '已经', '现在', '时候', '他们', '我们', '知道', '觉得',
                      '声音', '轻声', '低声', '忽然', '接着', '然后', '这时', '于是'}
            for n in (2, 3):
                for i in range(len(body) - n + 1):
                    w = body[i:i + n]
                    # ⚠ 虚词开头的一律不要（实测会混进"倒是"/"你倒"这种噪音）。
                    # [EN] Drop anything starting with a function word (measured noise).
                    if (w in banned
                            or w[0] in '的了着过是在和与就都也还很太更最把被将给让对向倒然还又才只再挺别没有不你'):
                        continue
                    cand[w] += 1
            # 只在**对话动词附近**出现太麻烦；用"出现 >= 3 次且像姓名"两条粗筛
            names = [w for w, c in cand.most_common(12) if c >= 3 and len(w) >= 2]
            return tuple(names[:8])
        except Exception:                                        # noqa: BLE001
            return ()

    async def _fix_flat_paragraphs(self, text: str) -> str:
        """把"整段一句都没铺开"的段落**重写一遍**（解析层硬处理）。

        ★★★ 为什么不能只靠提示词（2026-10-19，用户第三次报同一个毛病）
        ---------------------------------------------------------------
        原话：「下面这样的小短句子特别多 每一句都恨不得交代一个事情 而没有像正常
        小说一样 用长一些的句子慢慢描写」。
        而 `_transcribe_once` 的提示词里"别写成清单""一段里至少一句长的"早就写着，
        产物照样是分镜表 —— 又是"prompt 里写了 ≠ 生效"。

        四轮探针（`developers/probe_sentence_flow.py` / `probe_clause_density.py` /
        `probe_sentence_link.py`）把"句子短"否掉了：句长中位、分句/句号、极短句占比
        **全部与真人持平**。可数的病是**局部的**：某些段落整段都是报告句，
        一句都没铺开。所以这里**按段**判（`crew.prose_flow.list_like_spans`）、
        **只重写那几段**，不去动全局参数。

        ⚠ 三条边界（失败一律**保住原文**，绝不交出更差的东西）：
          · 只重写被判出来的那几段，整篇不重来（省钱，也不动没问题的文字）；
          · 重写结果长度要在原段 **0.6–2.2 倍**之间，否则判为不可用 ——
            防模型交回一句"（重写如下）"，或者把三段戏压成一句；
          · 异常/超时一律原样返回 —— 这一步是**加分项**，不许把整理稿搞砸。

        `PROSE_FLOW_FIX=0` 关掉它（回到纯提示词的老路）；默认 2 段。
        [EN] Rewrite the paragraphs that **never open up a single sentence** (a hard fix in the
        [EN] parsing layer). The prompt already said "don't write a checklist", and the output is
        [EN] still a shot list -- "written in a prompt != in effect". Four probes disproved "the
        [EN] sentences are too short" (median length, clauses per period, short-sentence share all
        [EN] match human samples); the countable problem is **local** -- some paragraphs are all
        [EN] report sentences. So judge **per paragraph**, rewrite **only those**.
        [EN] ⚠ Failures always keep the original text: only the flagged paragraphs, length ratio
        [EN] 0.6-2.2x, any exception returns the input unchanged. `PROSE_FLOW_FIX=0` disables it.
        """
        try:
            limit = int(CFG.i('PROSE_FLOW_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as PF
            # ★★★ 第一步：**修排版**（纯代码、零成本、一个字不动）——
            #   把"一句一段"的连续短行并成正常段落。这不是改写，是换行：
            #   第四次真跑出现过"六行每行一句"，读起来和旧版一样碎，而提示词治不了排版。
            #   实测：真跑产物 41 段→18 段 / 16 段→11 段；**真人样本 23 段→23 段（零误伤）**。
            # [EN] Step one: **fix layout** (pure code, zero cost, no character changed): merge runs
            # [EN] of one-sentence lines into normal paragraphs. Measured: 41->18 and 16->11 on real
            # [EN] runs; human samples 23->23 (no false positive).
            text = PF.merge_one_line_paragraphs(text)
            # ★★★ **先切句，再检测**（2026-10-19 第七轮，顺序是这轮的关键发现）。
            #
            #   为什么顺序不能反：
            #     · 切句会把"一句 60 字的逗号长龙"拆成几句短句 —— 而那一段**必然**
            #       变成"没有长句"= 平铺段；
            #     · 所以切句**必须排在检测前面**，让这些"切出来的平铺段"被重写那一步接住，
            #       由模型铺回"有长有短"；
            #     · 反过来（先检测后切）就没人管这些段落了 ——
            #       实测那正是"长句压下去了、平铺段涨到 4"的成因。
            #   ⇒ 一行代码的位置，决定了两个相反的判据是**互相接住**还是**互相打架**。
            # [EN] ★★★ **Split first, then detect** (round seven; the ordering is the finding).
            # [EN] Splitting a 60-char comma dragon necessarily yields a paragraph with **no long
            # [EN] sentence** -- i.e. a flat paragraph. So splitting must come **before** detection,
            # [EN] letting the rewrite step catch those paragraphs and lay them back out as
            # [EN] long-and-short. The reverse order leaves them to nobody -- measured, that is
            # [EN] exactly how "long sentences came down while flat paragraphs rose to 4" happened.
            text = PF.split_long_sentences(text, names=self._cast_names(text))
            # ★★★ 2026-10-20：**只挑"太长"的段**，不再挑"太平"的段。
            #   分开量过的硬证据（`diag_span_split.py`）：
            #     真人 18 章 —— 太平 中位 3 / 最大 9；太长 中位 0 / **最大 1**
            #     snow_v21   —— 太平 **0** / 太长 **2**
            #   ⇒ 「太平」（整段没有长句）在真人小说里满地都是（真跑反而一个都没有），
            #     它不是病；拿它去重写就是**在改本来没问题的段落**。
            # [EN] Only rewrite the "too long" half; see `long_span_issues`.
            #
            # ★★★ 但"太碎"确实有病，只是**我量错了口径**（2026-10-20 第三次修正）：
            #   区分点不是"句子多长"，而是"**句子有没有分句**"。
            #   真人再碎的段落也保持 逗号/句 ≥ **0.25**（「三年前二月，宣阳坊。」是 1.0），
            #   而 v23 那种「岛村倚着窗框。驹子坐在火钵旁。」是 **0.06**。
            #   `flat_span_issues` 在真人 18 章上命中 **0 段**、v23 命中 2 段 ⇒ 接回来。
            # [EN] "Too choppy" is real, but the right measure is **absence of clauses**,
            # [EN] not sentence length: human paragraphs stay >=0.25 commas/sentence while
            # [EN] the broken ones run at 0.06. `flat_span_issues`: 0 hits on 18 human
            # [EN] chapters, 2 on the broken run.
            spans = PF.long_span_issues(text) + PF.flat_span_issues(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('平铺段检测失败（跳过这一步）：%r', e)
            return text
        if not spans:
            # ⚠ 早退也要切长句 —— 第一版只在"有平铺段"的分支末尾切，
            #   于是"没有平铺段、但句句 60 字"的那种稿子**一个字都不切**
            #   （而 `snow_time2` 正是这种：平铺 0 段、长句 85.7%）。
            # [EN] The early return must split too: the first version only split at the end of the
            # [EN] "has flat paragraphs" branch, so a draft with no flat paragraphs but 60-char
            # [EN] sentences went through untouched (exactly `snow_time2`: 0 flat, 85.7% long).
            try:
                return PF.split_long_sentences(text, hard_max=30,
                                              names=self._cast_names(text))
            except Exception:                                    # noqa: BLE001
                return text
        _LOG.info('整理稿里有 %d 段"憋气"（长句过半或有超长句），重写其中 %d 段',
                  len(spans), min(limit, len(spans)))
        # 从后往前替换：前面的 span 下标不会被后面的替换挪动。
        # [EN] Replace back to front so earlier spans are not shifted by later replacements.
        for a, b in reversed(spans[:limit]):
            seg = text[a:b]
            if len(seg.strip()) < 20:
                continue
            # 判方向：这一段是"太碎"还是"太长"（两者都要重写，但话术不同）。
            # [EN] Direction: is this paragraph too choppy or too long (both get rewritten, with
            # [EN] different wording in the prompt).
            try:
                _sents = [x for x in PF._sentences(seg) if x[2] >= 2]
                _long = sum(1 for x in _sents if x[2] >= PF.LONG_MIN)
                _too_long = bool(_sents) and (_long * 2 > len(_sents)
                                              or any(x[2] >= PF.SENTENCE_MAX for x in _sents))
            except Exception:                                    # noqa: BLE001
                _too_long = False
            try:
                rp = await ask('daily',
                               [{'role': 'user',
                                 'content': PF.apply_hint(
                                         PF.rewrite_prompt(seg, too_long=_too_long))}],
                               purpose='prose_flow_fix', want='text',
                               max_tokens=max(600, int(len(seg) * 1.6)))
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('平铺段重写失败（保留原文）：%r', e)
                continue
            if not rp.ok:
                continue
            new = str(rp.value or '').strip()
            if not new or new.startswith('（') or '重写如下' in new[:20]:
                _LOG.info('平铺段重写没给出可用正文（保留原文）')
                continue
            ratio = len(new) / max(1, len(seg))
            if not (0.6 <= ratio <= 2.2):
                _LOG.info('平铺段重写长度异常 %.2f 倍（保留原文）', ratio)
                continue
            # ★★★ **台词不许变少**（2026-10-20 实测补的第 N 道闸）。
            #   R45 / R46 / R47 都有这道闸，唯独这里漏了 —— 代价实测：
            #   `snow_v21` 跑完，两句真台词被并进叙述里没了
            #   （「炭我拨好了，我下去了。」「床铺在里侧了，炭我留在火边。」），
            #   台词 26 → 23。这正是 A6 里写过的"台词不并"。
            #   ⚠ 判的是**这一段**的台词条数，不是全篇 —— 全篇判会让后面的段落
            #     替前面的顶包，等于没判。
            # [EN] The rewritten paragraph may not lose dialogue lines. R45/R46/R47 all have
            # [EN] this guard; this step was the only one missing it, and it cost two real
            # [EN] lines on snow_v21 (26 -> 23). Judged **per paragraph**: a whole-text check
            # [EN] would let one paragraph cover for another.
            try:
                if len(PF.quoted_texts(new)) < len(PF.quoted_texts(seg)):
                    _LOG.info('平铺段重写把台词并掉了（%d → %d 句，保留原文）',
                              len(PF.quoted_texts(seg)),
                              len(PF.quoted_texts(new)))
                    continue
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('平铺段重写的台词语检失败（保留原文）：%r', e)
                continue
            # ★★★ **重写不许引入新的"感知不成立"**（2026-10-20 实测补的第 N+1 道闸）。
            #   来源：多轮检查的计数表报出 `感知自洽 0 → 1` ——
            #   为了把长句拆短，模型写进了"隔着纸门看清睫毛上的雪"这种句子。
            #   这一步只该改**句子长短**，没有资格改动"谁能看见什么"。
            #   ⚠ 判的是**这一段**多了几处（不是全篇、也不是"有没有"）：
            #     原文本来就有 1 处的段落，重写后还是 1 处，不算它写坏的。
            # [EN] The rewrite may not introduce new perceptual impossibilities. Source: the
            # [EN] multi-round counter reported `感知自洽 0 -> 1` -- to break long sentences
            # [EN] the model wrote "saw the snow on his lashes through the paper door".
            # [EN] Judged as **delta** for this paragraph, so pre-existing issues don't block.
            try:
                _b = len(PF.percept_issues(seg))
                _a = len(PF.percept_issues(new))
                if _a > _b:
                    _LOG.info('平铺段重写引入了 %d 处"感知不成立"（保留原文）',
                              _a - _b)
                    continue
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('平铺段重写的感知复检失败（保留原文）：%r', e)
                continue
            # 段落边界要留住：原文这一段前后的换行由切分保证，替换时只换这一段的内容。
            # [EN] Keep paragraph boundaries: only this paragraph's content is replaced.
            text = text[:a] + new + text[b:]
        # ★ 末尾**再温和切一次**（重写那一步也可能又写出长句）。
        #   ⚠ 但这次**不能把段落切碎**：此时已经过了"检测→重写"，
        #     切碎出来的平铺段没人接了 ⇒ 门槛放到 30（只收真正的长龙），
        #     而不是前面那次用的 24。
        # [EN] A final, **gentler** pass (the rewrite step may produce long sentences again).
        # [EN] ⚠ It must not chop: detection and rewrite are already behind us, so any flat
        # [EN] paragraph it creates has nobody to catch it => a looser threshold (30, only true
        # [EN] dragons) than the 24 used up front.
        try:
            text = PF.split_long_sentences(text, hard_max=30,
                                          names=self._cast_names(text))
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('长句切分失败（保留原文）：%r', e)
        # ★★ **反应标签配额**只记日志、不改字**（2026-10-19 第十一轮）。
        #
        #   为什么**不**自动改写：这类标签是**句子里的副词性成分**
        #   （"他慢一拍：'是啊。'"），机器要换它就得重写整句 —— 那是重新生成，不是修字，
        #   而"重写整句"在这个管线里已经有一条路（平铺段重写），不该在这里再开一条。
        #   ⇒ 这里只**报**，让下一轮提示词去压；越界时日志里有一行，
        #     跑完能一眼看出"这一章又把人写成复读机了"。
        #   ⚠ 只报不修 = 这条判据**不能**声称"产品已修好"。真正生效的是提示词第 4.4 条。
        # [EN] ★★ **Reaction-tag quota**: log only, never rewrite. These tags are adverbial pieces
        # [EN] inside a sentence; changing one means regenerating the whole sentence, which is a
        # [EN] different job (the flat-paragraph rewrite already owns it). So this only **reports**,
        # [EN] so a run shows at a glance that the chapter turned a person into a broken record.
        # [EN] ⚠ Report-only means this is **not** a fix by itself -- prompt rule 4.4 is.
        try:
            _rt = PF.reaction_tag_note(text)
            if _rt:
                _LOG.info('整理稿反应标签用超了：%s（提示词第 4.4 条压不住时看这里）', _rt)
        except Exception:                                        # noqa: BLE001
            pass
        # ★★★ **末尾再合并一次排版**（2026-10-19 第十二轮，真跑抓出来的）
        # ------------------------------------------------------------------
        #   实测 `snow_v11`：开头 merge 过一遍，但产物里仍然有一整段是"一句一行"
        #   （叶子送酒那 8 行）。
        #   根因：**重写平铺段那一步，模型返回的就是一句一行** —— 它被要求"铺开这一段"，
        #   于是逐句分行写，而这一段之后**再没有任何人合并**。
        #   ⇒ 末尾补一次 merge。它只动"连续 ≥4 行、每行 ≤2 句"的块，
        #     对已经铺开的正常段落零影响（真人样本 23 段→23 段）。
        #   ⚠ 放在**切句之后**：切句只加句号不改行，两者互不干扰。
        # [EN] ★★★ **Merge once more at the end** (round twelve, caught by a real run). `snow_v11`
        # [EN] was merged at the start, yet the output still held a whole paragraph of one sentence
        # [EN] per line (8 lines of Yoko delivering wine). Cause: **the flat-paragraph rewrite step
        # [EN] returns one sentence per line** -- it is asked to "lay this paragraph out" and writes
        # [EN] line by line -- and nothing merges afterwards. It only touches blocks of >= 4 lines
        # [EN] with <= 2 sentences each, so normal paragraphs are untouched (human 23->23).
        # [EN] ⚠ It runs **after** sentence splitting: splitting adds full stops, never lines.
        try:
            text = PF.merge_one_line_paragraphs(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('末尾排版合并失败（保留原文）：%r', e)
        return text


    async def _fix_repeats(self, text: str) -> str:
        """把"同一个写法用了一次又一次"的地方**修掉**（解析层硬处理，一次修复调用）。

        ★★★ 为什么不能只靠提示词（2026-10-19 第十一轮，用户第 5、6 条）
        -------------------------------------------------------
        「岛村沉默无层次」「"你这个人哪"4 次」—— 提示词第 4.4/4.8/4.9 条
        都写了，而真跑产物照样复读。又是"prompt 里写了 ≠ 生效"。
        三条判据都是**纯代码、零成本**（`prose_flow.repeat_issues`），
        所以这里照 `_fix_flat_paragraphs` 的样子配一次修复调用：
        给**可数的事实**（"已经 4 次，最多留 2 次"），让模型换法子重写。

        ⚠ 三条边界（与 `_fix_flat_paragraphs` 同一条纪律）：
          · 异常 / 没开配置 ⇒ **原样返回**（这一步是加分项，不许把整理稿搞砸）；
          · 重写结果长度要在原文 **0.6–2.2 倍**之间，否则判为不可用；
          · 修完再问一次 `repeat_issues`，还超就把**原文交回去**
            （宁可带着病，也不交出一份被删坏的东西）。
        `PROSE_REPEAT_FIX=0` 关掉它（回到只报不修）。
        [EN] Repair the places where one device was used over and over (one repair call).
        [EN] ⚠ Same three guardrails as `_fix_flat_paragraphs`: exceptions return the
        [EN] input, length ratio 0.6-2.2x, and if the repair is still over quota the
        [EN] **original** is handed back.
        """
        try:
            limit = int(CFG.i('PROSE_REPEAT_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            issues = _PF.repeat_issues(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('重复检测失败（跳过这一步）：%r', e)
            return text
        if not issues:
            return text
        _LOG.info('整理稿里同一个写法用超了 %d 处：%s（PROSE_REPEAT_FIX=%d）',
                  len(issues), _PF.repeat_note(text), limit)
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                 _PF.repeat_rewrite_prompt(text, issues))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(1200, int(len(text) * 1.2)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('重复修复失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        new = str(rp.value or '').strip()
        if not new or new.startswith('（') or '重写如下' in new[:20]:
            _LOG.info('重复修复没给出可用正文（保留原文）')
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.6 <= ratio <= 2.2):
            _LOG.info('重复修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        try:
            if _PF.repeat_issues(new):
                _LOG.info('重复修复后还是超配额（保留原文）')
                return text
        except Exception:                                        # noqa: BLE001
            return text
        # 重写可能又交回“一句一行”，照旧合并+温和切一次（都是纯代码）。
        # [EN] The rewrite may return one sentence per line -- merge and split again.
        try:
            new = _PF.merge_one_line_paragraphs(new)
            new = _PF.split_long_sentences(new, hard_max=30,
                                          names=self._cast_names(new))
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('重复修复后的排版整理失败（保留重写稿）：%r', e)
        return new

    async def _fix_crowded(self, text: str) -> str:
        """把"一大段塞了十几件事"的地方**拆开**（解析层硬处理，一次修复调用）。

        ★★★ 为什么这一条比别的都值得修（2026-10-20 第十二轮）
        -------------------------------------------------------
        真人 18 章：段落最长 125 字、**段内最多 7 件事**，18 章**没有一章越界**；
        真跑 snow_v12 最长一段 638 字 / **44 件事**，v13=12、v14=19。
        这是目前量到的**最干净**的一条差距，而且是纯结构（数句子和空行），
        一点语义都不用判 —— 它正对着"读不下去"这件事本身。

        ⚠ 与 `_fix_repeats` 分工：那边是"同一个写法用了一次又一次"，
          那边改写提示词整段都在讲"换法子"；把"一段太挤"混进去会指错方向，
          所以这里是独立的 `crowded_rewrite_prompt`（只动分段，不动事实）。

        ⚠ 三条边界（与 `_fix_flat_paragraphs` / `_fix_repeats` 同一条纪律）：
          · 异常 / 没开配置 ⇒ **原样返回**（这一步是加分项，不许把整理稿搞砸）；
          · 重写结果长度要在原文 **0.6–2.2 倍**之间，否则判为不可用；
          · 修完再问一次，还超就把**原文交回去**（宁可带着病，也不交出坏的东西）。
        `PROSE_CROWD_FIX=0` 关掉它（回到只报不修）。
        [EN] Split up paragraphs that cram too many events. Same three guardrails as
        [EN] `_fix_repeats`; separate prompt because the fix is paragraphing, not rewording.
        """
        try:
            limit = int(CFG.i('PROSE_CROWD_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            issues = _PF.crowded_paragraph_issues(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('段落拥挤检测失败（跳过这一步）：%r', e)
            return text
        if not issues:
            return text
        _LOG.info('整理稿里有一段太挤（最多 %d 件事，上限 %d）（PROSE_CROWD_FIX=%d）',
                  issues[0].get('times', 0), issues[0].get('cap', 0), limit)
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                  _PF.crowded_rewrite_prompt(text, issues))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(1200, int(len(text) * 1.2)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('段落拥挤修复失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        new = str(rp.value or '').strip()
        if not new or new.startswith('（') or '重写如下' in new[:20]:
            _LOG.info('段落拥挤修复没给出可用正文（保留原文）')
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.6 <= ratio <= 2.2):
            _LOG.info('段落拥挤修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        try:
            if _PF.crowded_paragraph_issues(new):
                _LOG.info('段落拥挤修复后还是超（保留原文）')
                return text
        except Exception:                                        # noqa: BLE001
            return text
        # ⚠⚠ **这里绝不能调 `merge_one_line_paragraphs`**（2026-10-20 真跑实测）。
        #   `_fix_repeats` / `_fix_flat_paragraphs` 末尾都会 merge 一次，因为模型常常
        #   交回"一句一行"的稿子；但拥挤修复**要的就是分段** —— 模型按"换个人说话
        #   就另起一段"交回来的稿子，被 merge 一并按回一大坨，等于**刚拆完又合上**。
        #   实测 snow_v15：修复后检查通过（≤7 件），merge 之后成品变成 **27 件**，
        #   比修之前还糟 —— 因为 merge 排在检查**之后**，回头看是绿的。
        #   ⇒ 这一段只做 `split_long_sentences`（切的是长句，不动段落划分）。
        # [EN] Do NOT merge here: merging is exactly what undoes the splitting this fix
        # [EN] is for. v15 measured: passed the check (<=7), then merge produced 27.
        try:
            new = _PF.split_long_sentences(new, hard_max=30,
                                          names=self._cast_names(new))
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('段落拥挤修复后的切句失败（保留重写稿）：%r', e)
        return new

    async def _fix_topic_spin(self, text: str) -> str:
        """把"在同一个地方打转"的这一章收拢（**LLM 判官**判定 + 一次修复调用）。

        ★★★ 为什么这一条必须上判官（2026-10-20 第十二轮，用户点名）
        -------------------------------------------------------
        用户读完 snow_v16 点出两处：叶子反复送酒、驹子反复纠缠"好人好报"。
        两处都是**换了说法**的重复 —— 措辞一次都不重样，于是：
          · 动宾紧邻的正则：真人 1 次 / 真跑 1 次（**零区分度**，实测）；
          · 全文 2-gram 峰值：真人 top 是角色名（阿箬 14）与核心道具（老河 14），
            真跑是火钵 13 —— 人是这么写小说的，这个量分不出病；
          · 字面零承接：真人 **100%**，比真跑还高，拿来判会打死真人。
        ⇒ 四条字面路全堵死，判决交给判官。代码只管住**安全**与**流程**：
          · 判官说"没打转"、或者回话看不懂 ⇒ **一个字都不改**
            （`parse_spin_verdict` 的安全侧，宁可漏改也不许改坏好稿）；
          · 判官说"打转" ⇒ 用**判官自己抄出来的原句**当可数事实去修，
            不拿我们猜的热点词当证据。

        ⚠ 四条边界（比另两条多一条"判官必须先说话"）：
          · 异常 / 没开配置 ⇒ **原样返回**；
          · **判官调用失败 ⇒ 原样返回**（判官是这一条的前提，没判就不许改）；
          · 重写长度要在原文 **0.6–2.2 倍**之间，否则判为不可用；
          · 修完**再问一次判官**，还打转就把**原文**交回去。
        `PROSE_SPIN_FIX=0` 关掉它（回到只报不修）。
        [EN] Collapse chapters that spin in place. The verdict comes from the LLM judge;
        [EN] code only guarantees safety: no verdict (or an unreadable one) means the
        [EN] text is never touched, and a re-check that still spins hands back the original.
        """
        try:
            limit = int(CFG.i('PROSE_SPIN_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            if len(_PF.quoted_texts(text)) < _PF.SPIN_MIN_LINES:
                return text                       # 短到没什么可打转的
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('打转检测失败（跳过这一步）：%r', e)
            return text
        try:
            hots = _PF.topic_hotspots(text, names=self._cast_names(text))
            verdict = await ask('daily',
                                [{'role': 'user',
                                  'content': _PF.spin_judge_prompt(text, hots)}],
                                purpose='crew_day_novel', want='text',
                                max_tokens=420,
                                # ⚠ 判官是**判定**，不是创作：temperature 默认 0.2
                                #   实测会让同一份稿子一次判"打转"、一次判"没打转"
                                #   （v19 连跑两次，结论相反）。判定类调用一律 0。
                                # [EN] A judge decides, it does not write: at the default
                                # [EN] 0.2 the same chapter got opposite verdicts on
                                # [EN] consecutive runs. Always 0 for verdict calls.
                                temperature=0.0)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('打转判官调用失败（保留原文）：%r', e)
            return text
        if not verdict.ok:
            return text
        v = _PF.parse_spin_verdict(str(verdict.value or ''), text)
        if not v.get('spin'):
            _LOG.info('打转判官：%s（不动稿）', v.get('reason') or '没打转')
            return text
        _LOG.info('打转判官报了：%s（候选 %d 组，判删 %d 条）',
                  v.get('what', ''),
                  len(_PF.repeat_clusters(text)),
                  len(v.get('drops') or []))

        # ★★★ **先删，删不动才重写**（2026-10-20 第十四轮，用户点名）
        #   ------------------------------------------------------------
        #   用户原话：「不是所有重复都有问题，要结合上下文语境进行分析」。
        #   ⇒ 语境判断交给判官**逐条**做（它现在对每条都说"删掉会损失什么"），
        #     代码只负责执行「删」—— 因为删是唯一不会写进新东西的动作。
        #
        #   为什么不再走整章重写：snow_v19 就是被这条路卡死的 ——
        #     判官报"5 条出处" → 整章重写 → 复检**还报** → 整篇退回原文，
        #     一小时 1782 秒的成品里，"我是不是好人"照样问了 6 次。
        #     根因是"全有或全无"：重写改好 3 处、留 2 处，等于 0。
        #   ⇒ 现在改成"逐条删"：删掉几条就是几条的成果，不因为还剩几条而作废。
        #     只有判官**没给逐条**（老格式 / 说打转但没标哪条）时才退回整章重写。
        #   [EN] Delete per-line first; only fall back to a whole-chapter rewrite when the
        #   [EN] judge named no individual lines. The old all-or-nothing re-check is what
        #   [EN] made snow_v19 give up entirely after rewriting the whole chapter.
        drops = list(v.get('drops') or [])
        if drops:
            cut = _PF.drop_spin_lines(text, drops)
            if cut == text:
                _LOG.info('打转：判官标了 %d 条可删，但一条都没对上（保留原文）',
                          len(drops))
                return text
            ratio = len(cut) / max(1, len(text))
            if ratio < 0.6:
                _LOG.info('打转：删完只剩 %.0f%% 字（删过头，保留原文）', ratio * 100)
                return text
            # ⚠ 删句子会牵连 R46：删掉一句"答话"，原本接上的问答会变成悬空。
            #   这条闸是跨规则的，必须查（两条规则同在这条链上，谁都不能把谁搞坏）。
            # [EN] Deleting a line can break R46: removing an answer turns a linked
            # [EN] exchange into drift. Cross-rule guard, checked here.
            try:
                before_drift = max(
                    [len(r) for r in _PF.qa_drift_runs(text)] or [0])
                after_drift = max(
                    [len(r) for r in _PF.qa_drift_runs(cut)] or [0])
                if after_drift > before_drift:
                    _LOG.info('打转：删完把问答接续弄差了（%d → %d，保留原文）',
                              before_drift, after_drift)
                    return text
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('打转删除后的问答复检失败（保留原文）：%r', e)
                return text
            _LOG.info('打转修复：按判官逐条删掉 %d 条（%d → %d 字，留了 %d 条）',
                      len(drops), len(text), len(cut), len(v.get('keeps') or []))
            try:
                cut = _PF.split_long_sentences(cut, hard_max=30,
                                               names=self._cast_names(cut))
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('打转删除后的切句失败（保留删除稿）：%r', e)
            return cut
        _LOG.info('打转：判官没给逐条，退回整章重写（老路）')
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                 _PF.spin_rewrite_prompt(text, v))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(1200, int(len(text) * 1.2)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('打转修复失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        new = str(rp.value or '').strip()
        if not new or new.startswith('（') or '重写如下' in new[:20]:
            _LOG.info('打转修复没给出可用正文（保留原文）')
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.6 <= ratio <= 2.2):
            _LOG.info('打转修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        # ★ 修完**再问一次判官**：还打转就把原文交回去（宁可带着病）。
        # [EN] Re-ask the judge; if it still spins, hand back the original.
        try:
            again = await ask('daily',
                              [{'role': 'user',
                                'content': _PF.spin_judge_prompt(
                                    new, _PF.topic_hotspots(
                                        new, names=self._cast_names(new)))}],
                              purpose='crew_day_novel', want='text',
                              max_tokens=420)
            if again.ok and _PF.parse_spin_verdict(
                    str(again.value or ''), new).get('spin'):
                _LOG.info('打转修复后判官仍报（保留原文）')
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('打转复检失败（保留重写稿）：%r', e)
        try:
            new = _PF.split_long_sentences(new, hard_max=30,
                                          names=self._cast_names(new))
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('打转修复后的切句失败（保留重写稿）：%r', e)
        return new

    async def _fix_plausibility(self, text: str) -> str:
        """把"读起来不成立"的句子改掉（**LLM 判官**找出 ⇒ **定点改那一句**）。

        ★★★ 与 `_fix_topic_spin` 的分工（2026-10-20 第十三轮）
        --------------------------------------------------
        那边管"同一个地方打转"，这边管"前后打架"：
          · 「唇几乎没动、像叹息般溜出来」的私语，被"正进门"的叶子**听见了**；
          · 隔着门、光线昏暗，却写到「睫毛上的寒气」；
          · 干燥的釉面自己「流过一道亮痕」。
        前两条**有可数的形状**（`percept_issues`：真人 18 章 0 条 / 《雪国》v17 2 条），
        第三条数与形态都写不出来（"dry glaze cannot run"要的是常识），
        ⇒ 三类一起交给判官：它有常识。代码只做四件事：
          · **触发**：不做随心所欲的阈值 —— 与打转同一条规矩：**不设门槛**，
            正文够长就问（用户原话"阈值可以低一些"），多花的是一次调用；
          · **解析**：判官说没问题 / 回话看不懂 ⇒ 一个字都不改；
          · **定点替换**：只换判官点名的那几句（`swap_lines`），不动全篇 ——
            不像打转那样整章重写，因为这类毛病通常只有一两句，
            整章重写会把前面修好的东西再一次暴露给模型；
          · **四道闸**：替换后感知毛病不许变多、台词条数不许变少、
            长度只在 0.9–1.3 倍之间、新句不许短于原句 0.6 倍。任一不过 ⇒ 回原文。
        `PROSE_PLAUS_FIX=0` 关掉它。
        [EN] Fix sentences that do not hold up: an inaudible line someone hears,
        [EN] micro-detail seen through a door, physically impossible motion. The judge
        [EN] has common sense; code only triggers, parses conservatively, swaps the
        [EN] flagged sentences, and gates the result four ways.
        """
        try:
            limit = int(CFG.i('PROSE_PLAUS_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            if len(_PF.quoted_texts(text)) < _PF.PLAUS_MIN_LINES:
                return text                       # 短到没什么可不成立的
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('感知检测失败（跳过这一步）：%r', e)
            return text
        try:
            vd = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.plausibility_judge_prompt(text)}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=420,
                           # 判定类调用一律 0（理由见 `_fix_topic_spin` 里那段注释）
                           # [EN] Verdict calls always use temperature 0.
                           temperature=0.0)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('自洽判官调用失败（保留原文）：%r', e)
            return text
        if not vd.ok:
            return text
        verdict = _PF.parse_plausibility_verdict(str(vd.value or ''))
        if not verdict.get('bad'):
            _LOG.info('自洽判官：%s（不动稿）', verdict.get('reason') or '没问题')
            return text
        _LOG.info('自洽判官报了 %d 句不成立', len(verdict.get('lines') or []))
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                 _PF.plausibility_rewrite_prompt(
                                     text, verdict))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(900, int(len(text) * 0.8)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('自洽修复调用失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        pairs = _PF.parse_line_swaps(str(rp.value or ''))
        if not pairs:
            _LOG.info('自洽修复没给出可用的替换句（保留原文）')
            return text
        new = _PF.swap_lines(text, pairs)
        if not new or new == text:
            return text
        # ★ 四道闸，任一不过就把原文交回去 —— 这一步改的是**好稿里的几个句子**，
        #   改坏的代价远大于漏改。
        # [EN] Four gates; failing any one hands back the original.
        try:
            before = len(_PF.percept_issues(text))
            if len(_PF.percept_issues(new)) > before:
                _LOG.info('自洽修复把毛病改多了（保留原文）')
                return text
            if len(_PF.quoted_texts(new)) < len(_PF.quoted_texts(text)):
                _LOG.info('自洽修复把台词改少了（保留原文）')
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('自洽修复复检失败（保留原文）：%r', e)
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.9 <= ratio <= 1.3):
            _LOG.info('自洽修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        return new

    async def _fix_answer_drift(self, text: str) -> str:
        """把"连着几句问出去没人接"的链条**修出一处真答复**（R46）。

        用户 2026-10-20：「为何两个主角 说的话又完全牛头不对马嘴了」。
        ★★★ 它和 `_fix_topic_spin` 不一样：那边是"一个人自己打转"，
          这边是"两个人在拨号码，谁也没拨通"。

        **检测是确定性的**（`prose_flow.qa_drift_runs`），判据先在真人 18 章上
        量过：**悬空率**人最高 1.0（连这一项都没区分度），但**最长连续悬空**
        人的天花板是 2，v18 是 5 ⇒ 阈值 ≥3，18 章零误报。

        ★★★ 为什么还必须另外写一道，而不是让 `sim/loop.py::_audit_talk` 去拦：
          那一层本来就每拍在算、也真的报了（v18 日志里 5 次「连着 5 句没人接」），
          但它的注释写着**只算不拦**，理由是"删句会留下空白"。这个理由对**上游**
          成立（那里的产物还是一条一条的词条约，删一句就是一个洞），对**整理稿**不成立 ——
          这一步改的是已经成篇的散文，可以把"改成半句回应"交出去，不会留空。

        收货靠四道闸（与 `_fix_plausibility` 同一套，"漏改"优先于"改坏"）：
        毛病必须**变少**、台词不许变少、长度 0.9–1.3 倍、新句不短于原句 0.6 倍。
        `PROSE_DRIFT_FIX=0` 关掉它。
        [EN] Repair "consecutive unanswered questions". Detection is deterministic and
        [EN] calibrated on human prose (ceiling 2 hits in a row; run length >= 3 here).
        [EN] The sim-layer audit already sees this but only logs; repairing at the
        [EN] transcribed-prose stage can rewrite into a half-answer instead of blanking.
        [EN] Four gates decide acceptance; keeping the original beats damaging good prose.
        """
        try:
            limit = int(CFG.i('PROSE_DRIFT_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            before_runs = _PF.qa_drift_runs(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('问答不接检测失败（跳过这一步）：%r', e)
            return text
        if not before_runs:
            return text
        worst = max(len(r) for r in before_runs)
        _LOG.info('答非所问：%d 段，最长连着 %d 句没人接', len(before_runs), worst)
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                 _PF.answer_drift_rewrite_prompt(
                                     text, _PF.qa_drift_note(text)))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(600, int(len(text) * 0.6)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('答非所问修复调用失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        pairs = _PF.parse_line_swaps(str(rp.value or ''))
        if not pairs:
            _LOG.info('答非所问修复没给出可用的替换句（保留原文）')
            return text
        # ★★★ **少改优先，改不够才加**：为什么是"试前缀"而不是"全用"，
        #   见 `prose_flow.best_swap_prefix` 的说明（那里有实测数字）。
        # [EN] Prefer the fewest edits; see `prose_flow.best_swap_prefix` for the measurements.
        new, used, _new_max = _PF.best_swap_prefix(text, pairs)
        if not new or new == text:
            _LOG.info('答非所问修复换不动（保留原文）')
            return text
        if used > 2 * max(1, len(before_runs)):
            _LOG.info('答非所问修复：为压到阈值以下用了 %d 句（每段 2 句不够用）', used)
        try:
            after_runs = _PF.qa_drift_runs(new)
            if max([len(r) for r in after_runs] or [0]) >= worst:
                _LOG.info('答非所问修复没把它弄短（最长仍是 %d，保留原文）',
                          max([len(r) for r in after_runs] or [0]))
                return text
            if len(_PF.quoted_texts(new)) < len(_PF.quoted_texts(text)):
                _LOG.info('答非所问修复把台词改少了（保留原文）')
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('答非所问修复复检失败（保留原文）：%r', e)
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.9 <= ratio <= 1.3):
            _LOG.info('答非所问修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        _LOG.info('答非所问修复：最长连续 %d → %d', worst,
                  max([len(r) for r in _PF.qa_drift_runs(new)] or [0]))
        return new

    async def _fix_prop_cycle(self, text: str) -> str:
        """把"同一件东西被反复续上—耗掉"改掉（R47，**手在打转**）。

        用户 2026-10-20：「继续修复道具循环」。

        ★★★ 与 `_fix_topic_spin` 的分工：
          那边数"**话**"（同一诉求反复问），这边数"**手**"（同一件东西反复复位）。
          snow_v20 的台词每句都不同、每句都有推进 —— 所以打转判官**放过了它**，
          那是对的判断：它只是不管手上的事。而读者看到的正是"茶又凉了、又续上"。

        ★★★ 检测是**确定性的**（`prose_flow.prop_cycle_issues`），判据先量过：
          真人 18 章"同一件东西的最大复位次数"**中位 0、最大 0**；
          真跑 v12/v15/v17/v18 是 0，v16/v19/v20 是 4 ⇒ 阈值 ≥3，零误报。
          ⚠ 这个数**必须贴着东西**算：不限定"句子里有名有姓的器皿或可消耗物"，
            真人科幻那章会被判进 11 次"消耗"（全是表格里的「没有」「空着」）。

        ★★★ **不删戏，只换动作**：这类毛病的台词都有用，删掉会把一场戏删成两个人干坐着。
          ⇒ 交出去的是"把重复的那个动作换成另一件事"，并且**明写不许换同族动作**
            （又喝了/又添了/又换了，等于没改）。
          四道闸：毛病必须变少 / 台词不许变少 / 长度 0.9–1.3 倍 / 新句不短于原句。
        `PROSE_PROP_FIX=0` 关掉它。
        [EN] Fix a prop that keeps getting refilled and drained again (R47, "the hands
        [EN] spinning"). Detection is deterministic and calibrated on human prose (max
        [EN] resets per object = 0, real runs reach 4 => threshold 3, zero false positives).
        [EN] Never deletes scene: it only swaps the repeated action for another one, and
        [EN] explicitly forbids swapping in a sibling action of the same family.
        """
        try:
            limit = int(CFG.i('PROSE_PROP_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            issues = _PF.prop_cycle_issues(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('道具循环检测失败（跳过这一步）：%r', e)
            return text
        if not issues:
            return text
        worst = issues[0]['n']
        _LOG.info('道具循环：%d 件东西在反复复位，最狠的是「%s」×%d',
                  len(issues), issues[0]['cls'], worst)
        try:
            rp = await ask('daily',
                           [{'role': 'user',
                             'content': _PF.apply_hint(
                                 _PF.prop_cycle_rewrite_prompt(
                                     text, _PF.prop_cycle_note(text)))}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(600, int(len(text) * 0.6)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('道具循环修复调用失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        pairs = _PF.parse_line_swaps(str(rp.value or ''))
        if not pairs:
            _LOG.info('道具循环修复没给出可用的替换句（保留原文）')
            return text
        new = _PF.swap_lines(text, pairs)
        if not new or new == text:
            _LOG.info('道具循环修复换不动（保留原文）')
            return text
        # ── 四道闸（与 R45/R46 同一套，任何一道不过都回原文）──────────
        try:
            after = _PF.prop_cycle_issues(new)
            if max([x['n'] for x in after] or [0]) >= worst:
                _LOG.info('道具循环修复没把它弄少（最狠仍是 %d，保留原文）',
                          max([x['n'] for x in after] or [0]))
                return text
            if len(_PF.quoted_texts(new)) < len(_PF.quoted_texts(text)):
                _LOG.info('道具循环修复把台词改少了（保留原文）')
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('道具循环修复复检失败（保留原文）：%r', e)
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.9 <= ratio <= 1.3):
            _LOG.info('道具循环修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        _LOG.info('道具循环修复：最狠的复位 %d → %d', worst,
                  max([x['n'] for x in _PF.prop_cycle_issues(new)] or [0]))
        return new

    async def _fix_dialogue_tags(self, text: str) -> str:
        """把「他严肃地说道」这类**副词盖章**删到配额以内（确定性，不调模型）。

        ★★★ 为什么要有这一步（2026-10-28，作者转来的一份退稿复盘）：
          编辑圈稿时只圈了三段对话，批注是「你这两个人说话，像在互相念说明书」。
          其中一条破绽就是**标签堆砌**：通篇"他说道""她低声说道""他严肃地说道" ——
          标签换十个花样，还是标签。而"严肃""冷冷""意味深长"这类副词是作者在
          **替读者判情绪**，读者不需要被通知。

        ⚠ 为什么用确定性删除而不是让模型重写：
          副词是"多贴上去的一个词"，删掉它**不会改变事实**（谁在说、说了什么、
          什么语气由台词自己承担）。让模型重写这一步，是把它已经改好的句子
          再交出去赌一次 —— 与 `_fix_meta_narration` 同一条道理。
        ⚠ 配额内的**保留**：真人也这么写（一章一两处），清零比口径更狠。
        [EN] Deterministic removal of adverb-stamped dialogue tags down to the quota.
        [EN] Deleting an adverb adds no new facts, so no model call; the first N are kept
        [EN] because humans write this way too.
        """
        if not text:
            return text
        try:
            from crew import prose_flow as _PF
            new, n = _PF.strip_dialogue_tag_adverbs(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('对话标签清理失败（保留原文）：%r', e)
            return text
        if n:
            _LOG.info('对话标签：删掉 %d 处副词盖章', n)
        return new or text

    async def _fix_slop(self, text: str) -> str:
        """把「不是 X 而是 Y」「他终于明白」这类**套话**改回平实的话（R48）。

        ★★★ 来源（2026-10-28，作者转来的三篇去 AI 味文章 + 两个开源工具）：
          no-ai-slop（原版 petergyang / 中文版 shenxianpeng，MIT）的 "Patterns to cut"，
          收成**中文叙述层**能确定性匹配的闭集 5 类（见 `prose_flow.SLOP_PATTERNS`）。

        ⚠⚠ **别对它期望过高**：StoryScope 61,608 篇的对照实验说明，
          只把表面词句换干净，机器味**只掉 1.6 个点**（95.5% → 93.9%）。
          真正的机器味在叙事结构那一层（由 `anti_fp_block()` 那条管）。
          ⇒ 所以这一步**只改超配额的几处**（前两处不报，真人也这么写），
             `n_best=1`，不追求清零 —— 清零反而会造出一枚"处处整齐"的新指纹。

        ⚠ **只查叙述、不碰台词**：人物说"不是 X，是 Y"是完全自然的
          （判据 E1 专门守这条边界，把它判成套话 = 误伤作者的好句子）。

        ★ 四道闸（与 R45/R46/R47 同一套）：毛病必须变少 / 台词不许变少 /
          长度 0.9–1.3 倍 / 新文不能与原稿逐字相同。任何一道不过都回原文。
        [EN] Rewrite closed-set Chinese slop patterns back into plain speech. Only the hits
        [EN] beyond the quota (the first two are how humans write), never quoted speech.
        [EN] Four gates, same as R45/R46/R47; any failure returns the original text.
        """
        if not text:
            return text
        try:
            from crew import prose_flow as _PF
            issues = _PF.slop_issues(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('套话检测失败（跳过这一步）：%r', e)
            return text
        if not issues:
            return text
        _LOG.info('套话超配额 %d 处：%s', len(issues), '、'.join(issues[:3]))
        todo = '\n'.join(f'- {x}' for x in issues[:6])
        prompt = (
            '下面这段正文里，有几处是**套话**（模型腔）。只改这几处，别的不动。\n\n'
            f'{todo}\n\n'
            '怎么改：\n'
            '· 「不是 A，而是 B」⇒ 直接说 B，别装成洞察；\n'
            '· 「他终于明白……」「说到底……」这类替读者总结的话 ⇒ 整句删掉，'
            '把意思留在动作或后果里；\n'
            '· 「最关键的一点：」这种冒号悬念 ⇒ 改成一句平实的话；\n'
            '· 「标志着 / 彰显了」这类空话 ⇒ 换成具体的事实。\n\n'
            '硬要求：**引号里的台词一个字都不许改**；'
            '不许删戏、不许加情节；改完字数在原稿的 0.9~1.3 倍之间。\n'
            '只输出改完的正文，不要解释。\n\n'
            '【原文】\n' + text)
        try:
            rp = await ask('daily', [{'role': 'user', 'content': prompt}],
                           purpose='crew_day_novel', want='text',
                           max_tokens=max(600, int(len(text) * 0.6)))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('套话修复调用失败（保留原文）：%r', e)
            return text
        if not rp.ok:
            return text
        new = str(rp.value or '').strip()
        if not new or new == text:
            _LOG.info('套话修复没给出可用的稿（保留原文）')
            return text
        # ── 四道闸 ────────────────────────────────────────────────
        try:
            if len(_PF.slop_issues(new)) >= len(issues):
                _LOG.info('套话修复没把它弄少（%d → %d，保留原文）',
                          len(issues), len(_PF.slop_issues(new)))
                return text
            if len(_PF.quoted_texts(new)) < len(_PF.quoted_texts(text)):
                _LOG.info('套话修复把台词改少了（保留原文）')
                return text
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('套话修复复检失败（保留原文）：%r', e)
            return text
        ratio = len(new) / max(1, len(text))
        if not (0.9 <= ratio <= 1.3):
            _LOG.info('套话修复长度异常 %.2f 倍（保留原文）', ratio)
            return text
        _LOG.info('套话修复：%d 处 → %d 处', len(issues), len(_PF.slop_issues(new)))
        return new

    async def _fix_meta_narration(self, text: str) -> str:
        """把**叙述者跳出来讲结构**的那半句删掉（确定性，不调模型）。

        ★★★ 病根是我们自己的修复提示词（详见 `prose_flow.strip_meta_narration` 的说明）：
          提示词里写了"最多来回三轮""换个由头"，模型就把它**念给读者听** ——
          「算是第二层的新问」「把这第三轮收住」「这回不重复进门送物」。
          snow_v12 / v15 / v16 四类信号**全为 0**，一上打转判官就冒出来十条不到。

        ⚠ 这里**故意不调模型**：元叙述是"多写了一句"，删除是唯一不会写坏的动作；
          让模型重写等于把已经修好的事实再交出去一遍（R42 的教训）。
        [EN] Delete the half-sentence where the narrator explains its own structure.
        [EN] Deliberately model-free: this defect is an *addition*, so deletion cannot
        [EN] invent anything new.
        """
        try:
            limit = int(CFG.i('PROSE_META_FIX'))
        except Exception:                                        # noqa: BLE001
            limit = 0
        if limit <= 0 or not text:
            return text
        try:
            from crew import prose_flow as _PF
            new, n = _PF.strip_meta_narration(text)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('元叙述剥离失败（保留原文）：%r', e)
            return text
        if n:
            _LOG.info('元叙述剥离：%d 处', n)
        return new or text


def _str_list(value: Any, cap: int, width: int) -> list[str]:
    """把模型给的"一个字符串 / 一串字符串"统一成**去重保序的短列表**。

    ⚠ 一定要同时认两种写法：提示词里画的是数组，而模型经常给
      `"要点": "他问账；她不应；掌柜按住册子"` 这样一整句。只认数组的话，
      那三条要点会被整句当成**一条**（长度还会被 `width` 砍掉大半）。
      分隔符按中英文标点都切——这是本项目里"模型给串不给数组"的通用兜底。

        English:
    Normalize whatever the model returns -- "a single string / a list of strings" -- into a
    **deduplicated, order-preserving short list**.
        ⚠ It must accept both forms: the prompt draws an array, but models often return a whole
        sentence like `"要点": "he asks about the ledger; she doesn't answer; the boss pins the book"`.
        Recognizing arrays only would make those three points count as **one** (and `width` would chop
        most of it off). Split on both Chinese and English punctuation -- this is the project-wide
        fallback for "the model gave a string instead of an array".
    """
    if isinstance(value, str):
        text = value
        for sep in ('、', '，', ',', '；', ';', '／', '/', '|', '\n'):
            text = text.replace(sep, '\x00')
        raw: list = [x for x in text.split('\x00') if x.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = []
    out: list[str] = []
    for x in raw:
        s = ' '.join(str(x).split())[:width]
        if s and s not in out:
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _cast_list(value: Any, known: set) -> list[str]:
    """`出场` 那一串人名 —— **只留设定里真有的人**。

    与 `角色任务` 同一个口径（那边也只认在场的人）：模型偶尔会写一个
    不在册的名字，留着它只有一个后果 —— 那场戏永远等不到"该出场的人都到齐"，
    收场条件就废了。

        English:
    The list of names in `出场` -- **keep only people who really exist in the settings**.
        Same convention as `角色任务` (which also only recognizes people who are present): models
        occasionally write a name that isn't on the roster, and keeping it has exactly one
        consequence -- that scene can never satisfy "everyone who should appear has arrived",
        and the wrap-up condition is dead.
    """
    names = _str_list(value, 6, 20)
    if not known:
        return names
    return [n for n in names if n in known]


class Screenwriter(CrewMember):
    """**剧作者**：把样章改写成**能拍的剧本**。

    「能拍」在本项目里是个**可检验**的说法（老舍《茶馆》那一路的规矩）：

    | 要有什么 | 为什么 |
    |---|---|
    | 分几拍（`拍`） | 拍 = 一件**事**，不是一串动作。一天的戏要有几个落点 |
    | 每拍在哪儿（`场`） | 没地点就没法调人、没法出图、没法量"谁在场" |
    | 每拍发生什么（`发生`） | 可拍性检查：谁、在哪儿、做什么、说什么 |
    | 每拍推进了主线的什么（`推进`） | 一场一转变；没有转变的拍就该删 |
    | 每拍里人物想要什么（`目标`） | 他为了什么才动；没有目标戏就飘 |
    | 每拍里挡路的什么（`难题`） | 没有难题的拍只是走流程，观众不跟着急 |
    | 分派到人（`角色任务`） | 演员（人物 Agent）从这里拿"我今天该做的事" |

    ⚠ **不写台词**。台词是演员的活 —— 写死了他们就成了提线木偶
      （这条与 `director.engine.dispatch` 的"派要什么、不派怎么做"同源）。
    
        English:
    **Playwright**: rewrite the sample chapter into a **shootable script**.
        "Shootable" is a **verifiable** notion in this project (the Lao She "Teahouse" school of rules):
        | What's required | Why |
        |---|---|
        | How many beats (`拍`) | A beat = one **event**, not a string of actions. A day's drama needs several landing points |
        | Where each beat is (`场`) | Without location, you can't call people, can't generate images, can't measure "who is present" |
        | What happens each beat (`发生`) | Shootability check: who, where, doing what, saying what |
        | What each beat advances in the main line (`推进`) | One turn per scene; a beat with no turn should be cut |
        | What the character wants this beat (`目标`) | Why he moves at all; without a goal the scene drifts |
        | What blocks him this beat (`难题`) | A beat with no obstacle is just procedure; the audience won't care |
        | Assign to people (`角色任务`) | Actors (character Agents) take "what I should do today" from here |
        ⚠ **Do not write dialogue**. Dialogue is the actors' job -- writing it out turns them into marionettes
          (this shares its origin with `director.engine.dispatch`'s "dispatch what is wanted, not how to do it").
    """

    key = 'screenwriter'

    async def work(self, ctx: SetCtx, *, story: str = '', fix: str = '',
                   brief: str = '') -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        fixed = f'── 上次的问题（必须改掉）──\n{fix}\n\n' if str(fix or '').strip() else ''
        # ★★ `brief` = **上游给的**（名册里 `feeds='screenwriter'` 的那几位）：
        #   资料员的考据结论。**这条链以前只写在名册上** —— 名册说"资料员把
        #   考据交给剧作者"，而程序里两者各跑各的，那就只是两句话。
        #   现在它是真的：上游的结论进这里，剧作者写的时候得照着它。
        # [EN] ★★ `brief` = **given by upstream** (those in the roster with `feeds='screenwriter'`):
        # [EN] the researcher's findings. **This chain used to be written only on the roster** ——
        # [EN] the roster says "the researcher hands the findings to the screenwriter", yet in the program the
        # [EN] two run separately, so it was just two sentences.
        # [EN] Now it's real: upstream's conclusions enter here, and the screenwriter must follow them when
        # [EN] writing.
        brief_block = (f'── 上游递来的材料（**写的时候必须照它**）──\n{brief}\n\n'
                       if str(brief or '').strip() else '')
        # ── ② 外部编剧服务 PlotPilot：给本章结构建议（开关式 + 失败回退）──
        #   ★ 它**只进提示词**（像 `brief` 那样当上游材料），不替剧作者落 JSON ——
        #     剧作者仍产出 canonical 分拍，`plotpilot_block` 空着时这一路一字不变。
        #   ★ 失败一律 `degrade_pp` 记着，最后并进 note 的 `data`，不抛异常、不拦流程。
        # [EN] ── ② External screenwriter service PlotPilot: chapter-structure advice ──
        # [EN] ★ It **only enters the prompt** (like `brief`, as upstream material), it does
        # [EN] not produce the JSON for the screenwriter -- the screenwriter still emits the
        # [EN] canonical beats; when `plotpilot_block` is empty this branch is byte-identical.
        # [EN] ★ On failure always record `degrade_pp`, fold it into the note's `data` at the
        # [EN] end, never raise, never block the flow.
        plotpilot_block = ''
        degrade_pp = ''
        if _plotpilot_enabled_for(self.key):
            pp_text, pp_why = await _plotpilot_plan(
                ctx, story=story, people=ctx.people)
            if pp_text:
                plotpilot_block = (
                    f'── 外部编剧服务 PlotPilot 给的本章结构建议'
                    f'（写分拍时照它立结构）──\n{pp_text}\n\n')
            else:
                degrade_pp = pp_why
        people = '、'.join(ctx.people[:12]) or '（还没有人）'
        # ★ 思维链骨架（2026-10-07 第七轮）：先想清"这一天变什么、分几拍、
        #   每拍各自变什么"，再落成分拍 JSON。答案压进 `构思`，随产出落盘
        #   （`Studio.call` 会取它记一条日志，`剧组台账` 里也留得住）。
        # [EN] ★ Chain-of-thought skeleton (2026-10-07 round seven): first think through "what changes today,
        # [EN] how many beats,
        # [EN] what each beat changes", then land it as a split-shots JSON. The answer is compressed into `构思`
        # [EN] and persisted with the output
        # [EN] (`Studio.call` takes it and logs one entry, and it also persists in `剧组台账`).
        cot = cognition_block(self.key)
        cot_block = f'\n── 动手之前先想清楚（答案写进 `构思`）──\n{cot}\n' if cot else ''
        prompt = f"""你是这本小说的**剧作者**。下面是你手上的「原著样章」。
请把它**改写成能拍的剧本**：分几拍、每拍谁做什么、然后分派到每个人头上。

── 原著样章 ──
{story}

{fixed}{brief_block}{plotpilot_block}── 你写这类戏该守的手艺 ──
{craft}

── 在场人物 ──
{people}
{cot_block}
硬要求：
1. **不超过 {CFG.i('CREW_MAX_BEATS')} 拍**。拍 = **一场戏**，不是"一个动作"。
2. ★★ **每一拍都要像一场戏那样交代完整** —— 下面这些缺一样，上了场就会演成
   "东一句西一句、场景乱跳、没有人物出场没有情节"（这是作者点名的问题）：
     · `场`：在哪（**写成「地点·空间」两层**，如「临河茶肆·前厅」「临河茶肆·后院」；
       不能写"门外""对面"这种话）。★ `空间` 这一层要**先分清屋里还是院里**：
       见天的东西（井、树、影壁、水缸）归**院里**，有顶的东西（柜台、条案、灶台）
       归**屋里**。**有井就说明有院子，院子必须一起出现**（用户点名的硬要求）。
       ⚠ 屋里两间之间**隔着墙** —— 要过去得经过院子或廊下，别让人一步跨过一整座楼。
     · `主题`：**这场戏在讲什么**（≤20 字，一句话说清）
     · `出场`：**这场戏有谁**（1~6 个名字，必须是上面"在场人物"里的人）
     · `发生`：**发生了什么事**（一句，读者视角）
     · `要点`：**这一拍必须落到的动作与话头**（2~4 条）——
       写"谁做什么""谁问谁什么"，让演员知道这场戏**演到哪儿算演完**。
       ★ **写谁从哪儿走到哪儿（走位）**：人物移动要**按地图上真的连着的路**走
       （如"井边 → 院中 → 前厅"），不许一步跨过没连着的地方；
       要让地点切换推进剧情的，就在这里明写他为什么过去。
       ⚠ 这是**锚点不是台词**：写"阿九把账签摊开、问他认不认得末一格"，
       不写"阿九说：你认得这格子吗"。台词是演员的活。
     · `道具`：这一拍要动的物件（0~3 个，能反复出现的实物）
     · `情绪`：这一拍的情绪基调（几个字，"试探""压着火"这种）
     · `推进`：推进了主线的什么（**一场一转变**）
     · `目标`：这一拍里人物**想要什么**（一两句，他为了什么才动）
     · `难题`：这一拍里**挡路的什么**（人 / 事 / 环境）让他拿不到 ——
       没有难题的拍只是"顺顺当当走流程"，观众不会跟着急
3. 每一拍里出现的人，必须是上面"在场人物"之一 —— **不许写不在场的人**。
   而且 `出场` 里的人**要真的在这拍有事做** —— 挂个名字不出戏等于没写。
4. `角色任务` 是给每个人的"今天该做的事"，1~3 条、每条一句话；
   **只写"要什么"，不写"怎么做"**（怎么做是他自己的事，写死了就是提线木偶）。
4b. ★★★ 每个人都要有**他能做**的事（肯开口、肯动手都算）——
   **光写"不做什么"，他在场上就没有戏**（只能不动、不说）。
   "先忍着、末了把话说出来"这样的是好的：既有收，也有放。
   ⚠ 这一条有纯代码兜底（`prose_flow.passive_task_roles`），写了不做会被记下来。
5. 每件事都要能指回主线。**跟主线无关的事不要写进去。**
5b. ★★★ **先看清这个岔口**（2026-10-18）：这一天在剧情上是一个**岔口** —— 同一处
   起点，至少有两三条都讲得通的路（谁先开口、先问什么、把哪件事挑明、按住哪件事）。
   在 `岔口` 里列 **2~3 条**，每条一句话（≤24 字），写清**走法**，不要写评价；
   在 `选哪条` 里写你选的那条（≤20 字），在 `为什么` 里写一句理由（≤40 字）。
   ★ 选**最有戏**的那条：有张力、有人物露出新的一面。**不要选"最像原著"的那条**
     —— 这套推演是给作者找灵感用的，跟原著一样等于白跑一趟。
   ★ 也不许为了新奇而选一条站不住的（踩设定、人物走形）。新奇要**立得住**才算数。
   ⚠ 选定之后，**这一天只演那一条**：不许把几条路都演一遍（那会变成走流程）。
6. **不要写台词** —— 台词是演员的活。
7. `场景介绍` 是**开演前给读者的一小段**（40~80 字）：这是什么地方、
   此刻什么光景、空气中有什么。**不写情节、不预告后面** ——
   它的作用是让人先站进这个场面里。
   ★★ **平面要交代清楚**（2026-10-12 用户点名）：「如果要画地图，请在写小说或者
   编剧的时候就把环境平面描述的很清楚」—— 这一段要让人（和美术）
   **照着就能画出平面**：门在哪一面上、什么在屋里、什么在院子里、
   屋子之间怎么连着。**里外不许混**（井在院里、柜台在屋里）。
   ⚠ 只写**看得见的方位与位置**，别写成设定说明（那是 `设定集` 的事）。
8. `剧情简介` 是**今天这一章到底要讲什么**（30~60 字，一到两句）：
   给读者一个"今天会发生什么"的准头，**不吊胃口、不预告结局**。
   它和 `场景介绍` 是两件事 —— 场景介绍讲"这是什么地方"，
   剧情简介讲"今天要演什么"。也不要拿它复述前情。
9. **`构思` 只写一句话（≤60 字）**，它是给你自己想清楚的、不是交付物。
   ⚠ 这一条是**硬要求**，不是客气话：输出额度（{CFG.i('CREW_SCRIPT_TOKENS')} token）
   是有限的，而 `构思` 排在 JSON 最前面 —— 写长了会把「拍」和「角色任务」
   一起挤掉，整份 JSON 被**从中间截断**，这一天就得重写（实测踩过）。
10. 只输出 JSON，不要 ``` 围栏、不要任何解释：

{{{think_schema_of(self.key)}"岔口": [{{"走法": "…"}}, {{"走法": "…"}}],
  "选哪条": "…", "为什么": "…",
  "剧情简介": "…",
  "场景介绍": "…",
  "拍": [{{"拍": 1, "场": "地点·空间（如 临河茶肆·后院）", "主题": "…", "出场": ["人名", "人名"],
          "发生": "…", "要点": ["谁做什么", "谁从哪儿走到哪儿"],
          "道具": ["…"], "情绪": "…", "推进": "…", "目标": "…", "难题": "…"}}],
  "角色任务": {{"人名": ["…", "…"]}}}}"""
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        # 同上：这是"把故事改写成剧本"那一步，沿用既有 purpose。
                        # [EN] Same as above: this is the "rewrite story into script" step, reusing the existing purpose.
                        purpose='day_script', want=dict,
                        max_tokens=CFG.i('CREW_SCRIPT_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给出分拍')
        known = set(ctx.people)
        max_beats = max(1, CFG.i('CREW_MAX_BEATS'))
        beats: list[dict] = []
        for b in (data.get('拍') or data.get('beats') or []):
            if not isinstance(b, dict):
                continue
            row = {'拍': len(beats) + 1,
                   '场': str(b.get('场') or '').strip()[:20],
                   '主题': ' '.join(str(b.get('主题') or '').split())[:40],
                   '出场': _cast_list(b.get('出场'), known),
                   '发生': str(b.get('发生') or '').strip()[:120],
                   '要点': _str_list(b.get('要点'), 4, 60),
                   '道具': _str_list(b.get('道具'), 3, 12),
                   '情绪': ' '.join(str(b.get('情绪') or '').split())[:16],
                   '推进': str(b.get('推进') or '').strip()[:80],
                   '目标': str(b.get('目标') or '').strip()[:80],
                   '难题': str(b.get('难题') or '').strip()[:80]}
            if row['发生']:
                beats.append(row)
            if len(beats) >= max_beats:
                break
        roles: dict[str, list[str]] = {}
        raw_roles = data.get('角色任务') or data.get('roles') or {}
        if isinstance(raw_roles, dict):
            for k, v in list(raw_roles.items())[:12]:
                name = str(k).strip()
                # ★ 只认**在场**的人：模型偶尔会派给不在场（甚至不存在）的名字，
                #   派了也没人接 —— 那是"剧本里有、场上看不见"的假内容。
                # [EN] ★ Only recognize people who are **present**: models occasionally assign to names that are
                # [EN] off-screen (or don't even exist),
                # [EN] and even if assigned, no one picks it up -- that's fake content that's "in the script but
                # [EN] invisible on set".
                if not name or (known and name not in known):
                    continue
                tasks = [str(x).strip()[:60] for x in (v or []) if str(x).strip()]
                if tasks:
                    roles[name] = tasks[:3]
        # ★★★ R40（2026-10-19 第十一轮）：**只派了"不做什么"的角色** ——
        #   他在场上无事可做，只能不动不说；主角被这么派一次，整篇就少一个支点。
        #   纯代码、零成本（`prose_flow.passive_task_roles`）。
        #   ⚠ 这一步只**记日志**，不改派活：改派活要再问一次模型，而这一层
        #     已经问过一次了（再问一次是拿额度换一个不确定的结果）。
        #     先让它**可见** —— 作者和判据都能查到，别让"派了个不动的人"悄悄过去。
        # [EN] R40: a role told only what NOT to do has nothing to play. Log only --
        # [EN] rewriting the dispatch would cost another model call with no guarantee.
        try:
            from crew.prose_flow import passive_task_note as _passive_note
            _pn = _passive_note(roles)
            if _pn:
                _LOG.warning('派活里有人只被派了"不做什么"（他在场上无事可做）：%s', _pn)
        except Exception as _e:                                   # noqa: BLE001
            _LOG.debug('被动派活检测失败（跳过，不影响派活）：%r', _e)
        if not beats and not roles:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='分拍与角色任务都空')
        # ★★★ 2026-10-18：**岔口**（这一天本来有几条都讲得通的路，选了哪条、为什么）。
        #   为什么要解析它：不落下来，`5b` 就是一段"说了但没人看"的提示词 ——
        #   模型的思考不留痕，作者和判据都无从知道它是不是挑了一条最有戏的路。
        #   落进台账之后，报告里可以量"选的路是不是总落在第一条（=总挑最顺的）"。
        # [EN] ★★★ 2026-10-18: **the fork** (which of several workable roads was taken, and why).
        # [EN] Why parse it: without persisting it, rule `5b` is prompt text "said but never read" --
        # [EN] the model's reasoning leaves no trace, so neither the author nor the criteria can tell
        # [EN] whether it picked the most dramatically promising road. Once it lands in the ledger, the
        # [EN] report can measure "does it always take the first option (= always the easiest)".
        forks: list[str] = []
        _raw_forks = data.get('岔口') or data.get('forks') or []
        if isinstance(_raw_forks, list):
            for f in _raw_forks[:3]:
                if isinstance(f, dict):
                    s = str(f.get('走法') or f.get('path') or '').strip()
                else:
                    s = str(f).strip()
                if s:
                    forks.append(s[:40])
        chose = ' '.join(str(data.get('选哪条') or data.get('chosen') or '').split())[:40]
        why_chose = ' '.join(str(data.get('为什么') or data.get('why') or '').split())[:80]
        intro = ' '.join(str(data.get('场景介绍') or '').split())[:200]
        # ★ 「今日剧情简介」（2026-10-07 用户要的）：正式剧情之前那一段。
        #   和 `场景介绍` 一起从**同一次调用**里取出来 —— 零额外成本。
        # [EN] ★ "Today's plot summary" (requested by user 2026-10-07): the paragraph before the formal plot.
        # [EN] Fetched together with `场景介绍` from **the same call** -- zero extra cost.
        brief = ' '.join(str(data.get('剧情简介') or data.get('今日简介')
                             or '').split())[:200]
        # 台账里那一栏：**每拍一块，把"这场戏该有什么"摊开** ——
        # 作者一眼看得出这一天的戏是不是"一场接一场"。
        # [EN] The ledger column: **one block per beat**, laying out "what this scene should
        # [EN] contain" -- the author can see at a glance whether the day is "one scene after another".
        _lines: list[str] = []
        if forks:
            # 把岔口摊在台账最前面：作者一眼能看出"这一天本来还有别的路"。
            # [EN] Put the fork at the top of the ledger so the author sees at a glance that this day
            # [EN] had other roads.
            _lines.append('岔口：' + ' ｜ '.join(forks))
            if chose:
                _lines.append(f'选了：{chose}' + (f'（{why_chose}）' if why_chose else ''))
            _lines.append('')
        for b in beats:
            _what = str(b.get('发生') or '')
            _lines.append(f"{b['拍']}. 【{b.get('主题') or _what[:16]}】"
                          f"[{b.get('场') or '—'}] {_what}")
            _meta = []
            if b.get('出场'):
                _meta.append('出场：' + '、'.join(b['出场']))
            if b.get('道具'):
                _meta.append('道具：' + '、'.join(b['道具']))
            if b.get('情绪'):
                _meta.append('情绪：' + str(b['情绪']))
            if _meta:
                _lines.append('   ' + ' · '.join(_meta))
            if b.get('要点'):
                _lines.append('   要点：' + '｜'.join(str(x) for x in b['要点']))
            if b.get('推进'):
                _lines.append('   → ' + str(b['推进']))
        return CrewNote(role=self.key,
                        title=f'{len(beats)} 拍 · {len(roles)} 人派活'
                              + (' · 已写场景介绍' if intro else ''),
                        body='\n'.join(_lines),
                        data={'拍': beats, '角色任务': roles,
                              '场景介绍': intro, '剧情简介': brief,
                              # ★ 外部编剧服务 PlotPilot 这一次没用成的原因（空=用了或没开）。
                              #   并进 `data` = 台账留得住，作者翻日志能看见"为什么这天的
                              #   结构不是 PlotPilot 给的"，而不是傻傻以为它一直生效。
                              # [EN] ★ Why external screenwriter service PlotPilot wasn't used this
                              # [EN] time (empty = used or not enabled). Into `data` = persists to
                              # [EN] the ledger; the author can see in the log why this day's
                              # [EN] structure wasn't from PlotPilot, instead of assuming it was.
                              'plotpilot_degrade': degrade_pp,
                              # ★ 思维链（2026-10-07 第七轮）：他"为什么这么分拍"。
                              #   进 `data` = 落盘/台账留得住，`Studio.call` 还会
                              #   取它记一条日志（见 `cognition.note_think`）。
                              # [EN] ★ Chain of thought (2026-10-07, seventh round): why he "split the shots this way".
                              # [EN] Putting into `data` = persists to disk/ledger; `Studio.call` will also
                              # [EN] take it and log one entry (see `cognition.note_think`).
                              '构思': str(data.get('构思') or '').strip()[:200]})


# ══════════════════════════════════════════════════════════════════════
#  现场组：场记 · 道具 · 美术
# [EN] On-set crew: script supervisor · props · art
# ══════════════════════════════════════════════════════════════════════
class Continuity(CrewMember):
    """**场记**：连戏检查。

    干什么：把"今天这一场"跟前情与设定对一遍，挑出**对不上的地方** ——
    时间（夜里还是白天）、物件（上一场摔了的壶这一场又在手边）、
    称呼（谁该叫他什么）、状态（离场的人怎么又在说话）。

    为什么值得一个职位：这些错**不会让推演停下**，所以以前一个都没被记过。
    读者读到第三天会发现"那个人明明走了却在说话"，而作者翻日志也查不出来
    （日志里每一拍都"合法"）。场记就是那个**盯着连续性的人**。

    ⚠ **只报不判**：产出是"提请作者注意的清单"，程序**不自动改正文**
      —— 连戏的错误分两种（真错 / 有意的破例），机器分不出来。
      所以它 `feeds='director'`：给作者与导演看，不偷偷动稿子。
    
        English:
    **Continuity**: continuity check.
        What it does: check "today's scene" against prior context and settings, and pick out **mismatches** --
        time (night or day), props (the pot smashed last scene is at hand again this scene),
        address (who should call him what), state (how is someone who left the scene speaking again).
        Why it deserves a position: these errors **won't stop the simulation**, so previously not one was ever recorded.
        By the third day the reader notices "that person clearly left but is speaking", and the author combing the logs can't find it either
        (every beat in the log is "legal"). The continuity person is the one **watching continuity**.
        ⚠ **Report only, don't judge**: the output is a "list to bring to the author's attention"; the program **does not auto-edit the text**
          -- continuity errors come in two kinds (true errors / intentional exceptions), and a machine can't tell them apart.
          So it `feeds='director'`: for the author and director to see, without secretly touching the manuscript.
    """

    key = 'continuity'

    async def work(self, ctx: SetCtx, *, lines: list[str] | None = None,
                   brief: str = '') -> CrewNote:
        if not CFG.b('CREW_CONTINUITY'):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='连戏检查已关闭（CREW_CONTINUITY=false）')
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        # ★ 思维链骨架（2026-10-07 第七轮）：场记的活是"逐条核"，而模型
        #   天生爱跳步（看一眼就下结论）。骨架把它按"先逐条核、再核在场、
        #   最后才下结论"的顺序逼一遍，答案压进 `核查`。
        # [EN] ★ Chain-of-thought skeleton (2026-10-07, seventh round): the script supervisor's job is to
        # [EN] "check item by item", but models
        # [EN] are naturally prone to skipping steps (glance once and conclude). The skeleton forces it through
        # [EN] the order of "first check item by item, then check presence,
        # [EN] and only then conclude", compressing the answer into `核查`.
        _cot = cognition_block(self.key)
        cot_block = f'\n{_cot}\n' if _cot else ''
        body = '\n'.join(str(x) for x in (lines or []) if str(x).strip())[:4000]
        if not body:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='今天没有可查的正文')
        # ★ 上游 = 道具（名册里 `feeds='continuity'`）：**"这一场该有的东西"
        #   是查物件的依据** —— 没有它，场记只能凭印象说"好像少了什么"。
        #   这条链以前只写在名册上；现在真的把道具单递给场记。
        # [EN] ★ Upstream = props (in the roster, `feeds='continuity'`): **"the things this scene should have"
        # [EN] is the basis for checking objects** -- without it, the script supervisor can only say from
        # [EN] impression "seems like something is missing".
        # [EN] This link used to exist only on the roster; now the props list is really handed to the script
        # [EN] supervisor.
        brief_block = (f'── 道具师给这一场定的东西（物件对不上就报）──\n{brief}\n\n'
                       if str(brief or '').strip() else '')
        # 人物名册放进来越准 —— 称呼与在场状态都靠它
        # [EN] The more accurate the character roster, the better -- forms of address and presence status both
        # [EN] rely on it.
        cast = []
        for n in ctx.people[:16]:
            ps = (getattr(ctx.world, 'people', {}) or {}).get(n)
            if ps is None:
                cast.append(n)
                continue
            bits = [n, str(getattr(ps, 'identity', '') or '')]
            loc = str(getattr(ps, 'location', '') or '')
            if loc:
                bits.append(f'在{loc}')
            cast.append(' · '.join(b for b in bits if b))
        prompt = f"""你是一部剧的**场记**。你的活是**盯连续性**：把今天的戏跟前情、
人物设定对一遍，挑出对不上的地方。你不写戏、不改戏，只报问题。

── 这部戏的规矩（你判断"什么算对不上"的依据）──
{craft}

── 人物与此刻状态 ──
{ctx.scene_line()}
{chr(10).join(cast)}

{brief_block}── 前情（到昨天为止发生过什么）──
{ctx.recap(900)}

── 今天拍的戏（正文）──
{body}
{cot_block}
请逐条检查，**只报你真的看出来的问题**（看不出来就报"无"）：
① 时间对不上（前文是夜里，这里像白天；时辰跳得不合理）
② 物件对不上（已经摔了/给了别人的东西，这里又出现；上面写着该有的这里没有）
③ 称呼对不上（同一人被叫成两个名字，或叫法与人设不符）
④ 在场状态对不上（已经离场/还没登场的人在这里说话做事）
⑤ 与前情矛盾（今天做的事跟昨天已经定下的事冲突）

**硬要求**：每条都要**指出具体那一句**，并说清跟什么对不上。
**不要**提文笔、节奏、人物塑造这类意见（那不是场记的活，是导演的）。

★ **只抓重大矛盾，不拦正常的推进**（这条措辞是有来历的）：
  借鉴 `E-Asrar-Haghighi/ai-screenplay-writer`（MIT）那套"连戏检查器"的做法 ——
  它对**新进展、新地点、新人物、人物改变主意**一律**放行**，
  只有下面这几种才算问题：**人死而复生 / 已经毁掉的东西又出现 /
  主线自相矛盾 / 时间倒流且没有交代**。
  为什么必须写死这条：不写的话，场记会把"今天发生的新事"当成"跟昨天不符"报上来，
  于是每一条都会被导演当成假警报忽略 —— 那时它连真问题也一并**失去可信度**。
确实没有问题就输出 `无`。

只输出 JSON：
{{{think_schema_of(self.key)}"问题": ["（具体那一句）→ 跟什么对不上", "…"], "结论": "一句话"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_continuity', want=dict,
                        max_tokens=CFG.i('CREW_CONTINUITY_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没拿到检查结论')
        probs = [str(x).strip() for x in (data.get('问题') or [])
                 if str(x).strip() and str(x).strip() != '无']
        verdict = str(data.get('结论') or '').strip()
        # ★ 思维链（2026-10-07 第七轮）：他**逐条核过之后**才报的问题。
        #   进 `data` 是"落盘留得住"，`Studio.call` 会取它记一条日志。
        # [EN] ★ Chain of thought (2026-10-07, seventh round): he reports problems only **after checking item
        # [EN] by item**.
        # [EN] Putting into `data` means "persists to disk"; `Studio.call` will take it and log one entry.
        check = str(data.get('核查') or '').strip()[:200]
        if not probs:
            return CrewNote(role=self.key, title='连戏无问题' + (
                f'（{verdict[:40]}）' if verdict else ''), body=verdict,
                data={'问题': [], '核查': check})
        return CrewNote(
            role=self.key,
            title=f'连戏提请 {len(probs)} 处',
            body=verdict + ('\n' if verdict else '')
                 + '\n'.join(f'{i}. {x}' for i, x in enumerate(probs[:6], 1)),
            data={'问题': probs, '核查': check})


class Props(CrewMember):
    """**道具**：这一场该有什么物件、哪件要反复出现。

    为什么值得有：物件是**最省的主题外化手段**（老舍那一招：一件小东西反复
    出现，时代压力就自己说话了）。而程序里"场景里有什么"这件事以前完全
    没人管 —— `SCENE_NAME` 是个地名，出图时只把地名给模型，所以
    "同一间屋子的第三天"和"第一天"长得一模一样。

    产出两处用：
      · 进 `image_gen` 的 ctx（**出图的画面里真的会多出这些东西**）；
      · 落进运行文件夹的 `道具单.md`（作者与后面的天都要接着用）。
    
        English:
    **Props**: what objects this scene should have, which one needs to recur.
        Why it deserves to exist: objects are the **cheapest means of externalizing theme** (Lao She's trick: one small thing recurring,
        and the pressure of the era speaks for itself). And in the program, "what's in the scene" was previously completely
        unmanaged -- `SCENE_NAME` is a place name, and at image time only the place name is given to the model, so
        "the third day in the same room" looks exactly like "the first day".
        Output is used in two places:
          · goes into `image_gen`'s ctx (**the generated images really will show these extra things**);
          · lands in the run folder's `道具单.md` (the author and later days will keep using it).
    """

    key = 'props'

    async def work(self, ctx: SetCtx, *, beats: list[dict] | None = None,
                   brief: str = '') -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        beat_txt = '\n'.join(
            f"- [{b.get('场', '')}] {b.get('发生', '')}" for b in (beats or [])[:6]
        ) or '（还没分拍 —— 按场景本身猜）'
        # ★ 上游 = 美术（名册里 `feeds='props'`）：画风与主色决定"该摆什么"。
        #   这条链以前只写在名册上；现在真的把美术指导递给道具师。
        # [EN] ★ Upstream = art (in the roster, `feeds='props'`): art style and primary colors determine "what
        # [EN] should be placed".
        # [EN] This link used to exist only on the roster; now the art direction is really handed to the prop
        # [EN] master.
        brief_block = (f'── 美术定的调子（选东西要合它）──\n{brief}\n\n'
                       if str(brief or '').strip() else '')
        prompt = f"""你是一部剧的**道具师**。请定这一场该有哪些**具体物件**。

── 场景 ──
{ctx.scene_line()}
{ctx.world_brief(600)}

── 这部戏的手艺（物件怎么承住戏）──
{craft}

{brief_block}── 今天要拍的几件事 ──
{beat_txt}

要求：
1. 5~8 件**具体可画**的东西（不要"一些杂物"这种泛称）。
2. 标出其中 1~2 件是**要反复出现**的（承住这条线的那件）。
3. ★★ **每件东西都要落得住地方**（2026-10-12 用户点名「严格区分室内室外」）：
   在 `用途` 里**带上它在哪儿** —— `屋里`（有顶：柜台、条案、灯、账册）还是
   `院里`（见天：井、树、石桌、水缸）。⚠ **见天的东西不许摆进屋里**
   （井不能写在堂屋里）；**有井这件事本身就说明这一处有院子**。
   分不清就**别写它**，换一件明确落得住的。
4. 只给物件与一句用途，**不要写剧情**、不要编新人物。
5. 只输出 JSON：

{{"道具": [{{"名称": "…", "用途": "…（在哪儿）", "反复": true|false}}], "基调": "一句话"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_props', want=dict,
                        max_tokens=CFG.i('CREW_PROPS_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给道具单')
        items: list[dict] = []
        for x in (data.get('道具') or [])[:10]:
            if isinstance(x, str):
                x = {'名称': x}
            if not isinstance(x, dict):
                continue
            nm = str(x.get('名称') or '').strip()
            if not nm:
                continue
            items.append({'名称': nm[:20],
                          '用途': str(x.get('用途') or '').strip()[:40],
                          # ★ 2026-10-12：**每一件都标上它属于哪一类**（屋里/院里/见天）
                          #   —— 确定性算出来的，不看模型脸色。这样"井摆在堂屋里"
                          #   在数据里就看得见（调用方/判据按它断言）。
                          # [EN] ★ 2026-10-12: **every item is tagged with its category** (indoors / in the
                          # [EN] yard / under open sky) -- computed deterministically, not left to the model.
                          # [EN] That way "a well placed in the main hall" is visible in the data (callers and
                          # [EN] criteria assert on it).
                          '属于': _prop_space(nm),
                          '反复': bool(x.get('反复'))})
        if not items:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='道具单是空的')
        key_items = [i['名称'] for i in items if i['反复']]
        body = '、'.join(i['名称'] for i in items)
        tail: list[str] = []
        if key_items:
            tail.append(f'承住这条线的：{"、".join(key_items)}')
        tone = str(data.get('基调') or '').strip()
        if tone:
            tail.append(f'基调：{tone[:60]}')
        # 同 `Art`：title 里已经有件数与关键道具，body 别再重复那两样
        # [EN] Same as `Art`: the title already contains the item count and key props; the body should not
        # [EN] repeat those two.
        if tail:
            body += '\n' + '\n'.join(tail)
        return CrewNote(role=self.key,
                        title=f'{len(items)} 件道具' + (
                            f'（关键 {"、".join(key_items[:2])}）' if key_items else ''),
                        body=body, data={'道具': items, '基调': tone,
                                         '关键': key_items})


def _prop_space(name: str) -> str:
    """一件道具有没有"落得住的地方"（`屋里` / `院里` / `—`）。

    确定性、零成本（复用 `world.spatial` 的那份分类）—— 拿不到就返回 `—`，
    **不猜**。
    [EN] Whether a prop has "a place it can sit" (`indoors` / `in the yard` / `—`).
    [EN] Deterministic and free (reuses `world.spatial`'s classification) -- falls back to `—`,
    [EN] **never guesses**.
    """
    try:
        from world import spatial as _SP
        sp = _SP.space_of(name)
        if sp == _SP.SPACE_IN:
            return '屋里'
        if sp == _SP.SPACE_OUT:
            return '院里'
        return _SP.role_of(name)
    except Exception:                                            # noqa: BLE001
        return '—'


def _atlas_block(layers: list | None) -> str:
    """把**底图的这一层**摊成模型能抄的文字（`draw_day_map` 的"取景"那一步）。

    `layers` = `[(层名, 地点名, Layout), …]`（`world.atlas.Atlas.layers_for()`）。
    空 = 这本书没有底图 → 返回空串，调用方走**没有底图的那份提示词**。

    ★ 为什么要把坐标**逐字摊给模型**（而不是让它"参考一下"）：
      取景这一步的全部意义就是**位置照抄**。只给一份"底图在这儿"的抽象说明，
      模型照样会按自己的理解重排一遍 —— 那就等于底图白做了。
      所以这里连 `x` / `y` 数值一起给，提示词里再写死"逐字沿用"。

    ⚠ 只摊**要用的那一层**（`layers_for` 已经定了"今天最细的那层说了算"），
      三层全摊上去会让模型把室内图也画进整体图里。
    
        English:
    Flatten **this layer of the base map** into text the model can copy (`draw_day_map`'s "framing"
    step).
        `layers` = `[(layer name, place name, Layout), …]` (`world.atlas.Atlas.layers_for()`).
        Empty = this book has no base map -> returns empty string, caller uses **the prompt without a base map**.
        ★ Why the coordinates must be **flattened to the model verbatim** (rather than letting it "take a reference"):
          the entire point of the framing step is **copying positions**. Give only an abstract note that "the base map is here",
          and the model will still rearrange it by its own understanding -- which means the base map was made for nothing.
          So here even the `x` / `y` values are given, and the prompt hard-codes "use verbatim".
        ⚠ Flatten only **the layer to be used** (`layers_for` already decides "the finest layer for today wins"),
          flattening all three layers would make the model draw interior maps into the overall map too.
    """
    blocks: list[str] = []
    for layer, place, lay in (layers or []):
        if lay is None or not getattr(lay, 'places', None):
            continue
        head = f'【{layer}{"·" + place if place else ""}】'
        if getattr(lay, 'caption', ''):
            head += f' 题记：{lay.caption}'
        if str(layer) == '室内' and getattr(lay, 'frame', ''):
            head += f'（整座：{lay.frame}）'
        lines = [head]
        for p in lay.places[:24]:
            note = f' —— {p.note}' if p.note else ''
            # ★★★ 2026-10-12：每一个地点都要**带上它是屋里还是院里**（用户点名
            #   「严格区分室内室外」）。少了这一栏，模型拿到一串平铺的名字，
            #   就会把井和堂屋当成同一种东西 —— 那正是"屋里的井"的来源。
            # [EN] ★★★ 2026-10-12: every location must **carry whether it is indoors or in the yard**
            # [EN] (the user named "strictly distinguish indoors and outdoors"). Without this column the
            # [EN] model receives a flat list of names and treats a well and the main hall as the same
            # [EN] kind of thing -- which is exactly where "a well indoors" comes from.
            role = ''
            try:
                from world import spatial as _SP
                role = f' [{_SP.role_of(p.name)}]'
            except Exception:                                    # noqa: BLE001
                role = ''
            lines.append(f'- {p.name} ({p.x:g}, {p.y:g}) {p.shape}{role}{note}')
        for l in (getattr(lay, 'links', None) or [])[:24]:
            a, b = str(l.get('a') or ''), str(l.get('b') or '')
            if a and b:
                lines.append(f'- 通路：{a} ↔ {b}')
        # ★ 再补一段**空间常识**（有井就有院、屋里见顶院里见天、走法）
        # [EN] ★ Then append a passage of **spatial common sense** (a well implies a courtyard, rooms
        # [EN] have a roof and the yard has open sky, the ways to walk)
        try:
            from world import spatial as _SP
            hint = _SP.hint_block([p.name for p in lay.places],
                                  kind=str(layer),
                                  building=str(getattr(lay, 'frame', '') or place or ''),
                                  links=getattr(lay, 'links', None))
            if hint:
                lines += ['★ 空间事实（**照它写，不许自己猜里外**）：', hint]
        except Exception:                                        # noqa: BLE001
            pass
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


class Art(CrewMember):
    """**美术**：定这一部的画风与配色，管住出图一致性。

    为什么值得有：出图那条路以前是"一个场景名 → 一张图"。同一部戏里，
    第一天的插图和第五天的插图可能一个冷一个暖、一个写实一个写意 ——
    因为**没有任何地方记着"这部戏长什么样"**。
    美术的产出是一条**美术指导**（画风 + 主色 + 忌讳），
    它进 `image_gen` 的提示词前缀，也落进 `美术指导.md`。
    
        English:
    **Art**: set this part's art style and color scheme, and keep image consistency under control.
        Why this is worth having: the image-generation path used to be "one scene name -> one image". Within the same play,
        the illustration for day one and the illustration for day five could be one cold and one warm, one realistic and one impressionistic --
        because **nowhere recorded what this play looks like**.
        The art output is an **art direction** (art style + primary colors + taboos),
        which feeds into the prompt prefix of `image_gen`, and also lands in `美术指导.md`.
    """

    key = 'art'

    async def work(self, ctx: SetCtx, *, day_map: bool = False, here: str = '',
                   places: list[str] | None = None,
                   layers: list | None = None,
                   beats: list[dict] | None = None) -> CrewNote:
        """美术有**两件活**，靠 `day_map=` 分派：

          · `day_map=False`（默认）—— 全剧美术指导，**一部戏一次**（见下）；
          · `day_map=True`  —— **当天这张地图**，每天一次（见 `draw_day_map()`）。

        ★ 为什么要分派而不是各写一个职位：名册里「美术」是一个职位、一条台账、
          一个落盘口 —— 拆成两个职位会让"这一班人在干什么"变得看不清。
          但产出**必须分文件**（见 `studio.FILE_DAY_MAP`），
          不然当天地图会把美术指导覆盖掉。

        `layers` 只有 `day_map=True` 时有意义（开卷定下的三级底图里今天该用的那几层）。
        
                English:
        Art has **two jobs**, dispatched via `day_map=`:
                  · `day_map=False` (default) —— whole-show art direction, **once per show** (see below);
                  · `day_map=True`  —— **the day's map**, once per day (see `draw_day_map()`).
                ★ Why dispatch instead of writing a separate role for each: in the roster, "art" is one role, one ledger entry,
                  one persistence slot —— splitting it into two roles would make "what this crew is doing" unclear.
                  But the outputs **must go to separate files** (see `studio.FILE_DAY_MAP`),
                  otherwise the day map would overwrite the art direction.
                `layers` is only meaningful when `day_map=True` (among the three-level base maps fixed at opening, the layers to use today).
        """
        if day_map:
            return await self.draw_day_map(ctx, here=here,
                                           places=places, layers=layers)
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        style = getattr(ctx.world, 'style_card', None) or {}
        style_line = ('，'.join(f'{k}={v}' for k, v in style.items()
                                if isinstance(v, (str, int, float))
                                and str(v).strip())[:200]
                      if isinstance(style, dict) else '')
        prompt = f"""你是一部剧的**美术指导**。请定下这部的**画风与配色**，
好让全剧出图保持一致。

── 这是什么戏 ──
题材：{genre or '（未定）'}{f'·{structure}' if structure else ''}
{ctx.world_brief(700)}
{('原作风格：' + style_line) if style_line else ''}

── 手艺（画面怎么承住戏）──
{craft}

要求：
1. **画风**一句话（如"水墨淡彩、纸本质感、不做高光"）。
2. **主色 3 个**，各给一个十六进制色与用途（哪一块用它）。
3. **忌** 2~3 条（这部戏的画面**不许**出现什么）。
4. 只输出 JSON：

{{"画风": "…", "主色": [{{"色": "#RRGGBB", "用途": "…"}}], "忌": ["…"]}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_art', want=dict,
                        max_tokens=CFG.i('CREW_ART_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给美术指导')
        look = str(data.get('画风') or '').strip()
        colors: list[dict] = []
        for c in (data.get('主色') or [])[:5]:
            if isinstance(c, str):
                c = {'色': c}
            if not isinstance(c, dict):
                continue
            hexv = str(c.get('色') or '').strip()
            if not hexv.startswith('#'):
                continue
            colors.append({'色': hexv[:9],
                           '用途': str(c.get('用途') or '').strip()[:30]})
        bans = [str(x).strip()[:40] for x in (data.get('忌') or [])
                if str(x).strip()][:4]
        if not look and not colors:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='美术指导是空的')
        # ⚠ body **不再重复 title**：界面上那一行会先写 title 再写 body，
        #   重复的话同一句画风会出现两遍（实测看起来像渲染坏了）。
        # [EN] ⚠ The body **no longer repeats the title**: the UI writes the title first, then the body on that
        # [EN] line,
        # [EN] so repetition would make the same art-style sentence appear twice (in practice it looks like
        # [EN] broken rendering).
        parts: list[str] = []
        if colors:
            parts.append('主色：' + '、'.join(f"{c['色']}（{c['用途']}）"
                                            for c in colors))
        if bans:
            parts.append('忌：' + '、'.join(bans))
        return CrewNote(role=self.key, title=look[:40] or '美术指导',
                        body='\n'.join(parts),
                        data={'画风': look, '主色': colors, '忌': bans})

    @staticmethod
    def prompt_prefix(note: CrewNote) -> str:
        """把美术指导变成**出图提示词的前缀**（这就是"接到 image_gen"那一步）。

        拿不到指导时返回空串 —— 宁可不加，也不要塞一句假的美术要求。
        
                English:
        Turn art direction into a **prefix for the image generation prompt** (this is the "hook up to
        image_gen" step).
                Return an empty string when no direction is available —— better to add nothing than to stuff in a fake art requirement.
        """
        if note is None or not note.ok:
            return ''
        d = note.data or {}
        bits = [str(d.get('画风') or '').strip()]
        cols = [str(c.get('色') or '') for c in (d.get('主色') or [])
                if isinstance(c, dict)]
        if cols:
            bits.append('主色 ' + ' '.join(cols[:3]))
        bans = [str(x) for x in (d.get('忌') or []) if str(x).strip()]
        if bans:
            bits.append('避免：' + '、'.join(bans[:3]))
        return '；'.join(b for b in bits if b)


    async def draw_day_map(self, ctx: SetCtx, *, here: str = '',
                           places: list[str] | None = None,
                           layers: list | None = None) -> CrewNote:
        """**当天的那张地图**：今天这几场戏发生在哪几处、彼此什么位置。

        用户 2026-10-07 的原话（这是本方法的全部理由）：
        「这个小地图还是不对 周围都是小说 而不是实际地图 请把绘制地图改到
          **导演写完当前的小说之后** 有剧组**美术**根据**当天剧情涉及到的地点**
          进行绘制」

        ★ 和 `work()`（全剧美术指导）的分工：
          · `work()`   —— **一部戏一次**：画风 / 主色 / 忌讳，管全剧出图一致；
          · `day_map()` —— **每天一次**：今天这场戏发生在哪几处、怎么摆。
        同一职位两件活，都不该由程序拍脑袋决定。

        ★★ **`places` 只给"今天这几处"，不给整份设定地点表**（2026-10-08）。
          用户第二次点名同一个毛病：小地图上主角所在的那一处旁边画着一串
          **世界层级**的名字（各界、各域），用户说「**这些不是真实的地名**」，
          要求「**只根据当前发生的故事所在的地点画图**，而不是根据整本小说
          设定画图」。

          病根就在**这一份提示词**：以前往 `places` 里塞的是 `地点.yaml` 的**全表**，
          还写着"设定里真实存在的地点"。模型看见那些"界"，自然乖乖画成一本书的
          世界总图 —— **是我们诱导它这么画的**。
          现在这里只列**今天剧本里真的出现过**的那几处（`places_in_day()` 算的），
          校验也只用这几处（`day_layout` 的 `allowed`）——
          "隔壁的客栈"这种编造照样挡得住，因为它同样不在这份表里。

        ★★ **`layers`（2026-10-08 加）＝ 从底图里取景，不再凭空摆位。**
          用户：「在开卷的时候把一些整体地图 局部地图(房屋附近 房屋内部)
          提前画好，**需要的时候基于这些地图让美术加细节**」。

          在这之前，美术每天拿到的东西里**没有任何空间事实** —— 同一处地方
          今天被排在左上、明天可能排在右下（"地图"于是不是地图，是每天的插图）。
          现在把**开卷时定下的那一层底图**给它，它的活变成两件：
            ① **取景**：今天戏在哪几处 → 从底图里挑出该上屏的那一块；
            ② **补细节**：底图没写到的（今天新出现的物件、天气造成的差别）按剧情补。
          位置不再是它编的，是从底图里**读出来**的。

          `layers` = `[(层名, 地点名, Layout), …]`。**空** = 这本书没有底图
          （没生成过 / 生成失败 / `MAP_ATLAS` 关着）→ 退回从前的行为。
          **两条路都要能走**：底图是"更好"，不是"必需"。

        `places` = **今天这几处**（设定里真实存在 ∧ 当天剧本里出现过）。
        
                English:
        **The day's map**: where the scenes of today take place, and their positions relative to each
        other.
                User 2026-10-07's exact words (this is the entire rationale for this method):
                "this small map is still wrong, it's all novels around it, not an actual map. Please move the map drawing to
                  **after the director finishes writing the current novel**, with the crew's **art** drawing it based on **the locations involved in the day's story**"
                ★ Division of labor with `work()` (whole-show art direction):
                  · `work()`   —— **once per show**: art style / primary colors / taboos, keeps image generation consistent across the whole show;
                  · `day_map()` —— **once per day**: where today's scene takes place, and how it is laid out.
                One role, two jobs, neither should be decided arbitrarily by the program.
                ★★ **`places` only gives "today's few places", not the entire setting location table** (2026-10-08).
                  The user called out the same problem a second time: on the small map, next to the place where the protagonist is,
                  a string of **world-tier** names is drawn (various realms, various domains); the user said "**these are not real place names**",
                  and demanded "**draw the map only based on the locations of the story currently happening**, not based on the entire novel
                  setting".
                  The root cause lies in **this prompt**: previously `places` was stuffed with the **full table** from `地点.yaml`,
                  and it even said "locations that truly exist in the setting". Seeing those "realms", the model naturally drew a whole-book
                  world map —— **we induced it to draw that way**.
                  Now it lists only the places that **actually appeared in today's script** (computed by `places_in_day()`),
                  and validation also uses only these places (`day_layout`'s `allowed`) ——
                  fabrications like "the inn next door" are still blocked, because they are likewise not in this table.
                ★★ **`layers` (added 2026-10-08) = take the view from the base map, no longer positioning out of thin air.**
                  User: "at opening time, draw some overall maps and local maps (near the house, inside the house)
                  in advance, **and when needed, have art add details based on these maps**".
                  Before this, what art got each day contained **no spatial facts at all** —— the same place
                  might be placed top-left today and bottom-right tomorrow (so the "map" was not a map, but a daily illustration).
                  Now it is given **the base-map layer fixed at opening time**, and its job becomes two things:
                    ① **framing**: which places today's scene is in → pick the block from the base map that should go on screen;
                    ② **adding details**: things the base map did not cover (objects newly appearing today, differences caused by weather) added per the story.
                  Positions are no longer invented by it; they are **read out** from the base map.
                  `layers` = `[(layer name, place name, Layout), …]`. **Empty** = this book has no base map
                  (never generated / generation failed / `MAP_ATLAS` off) → fall back to the previous behavior.
                  **Both paths must work**: the base map is "better", not "required".
                `places` = **these few places today** (actually exist in the setting ∧ appeared in today's script).
        """
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        beats = list(getattr(ctx, 'beats', None) or [])
        beat_txt = '\n'.join(
            f"- [{b.get('场') or '（未标）'}] {b.get('发生') or ''}"
            for b in beats[:8]) or '（今天还没分拍 —— 那就按「最近这一场」画）'
        names = [str(x).strip() for x in (places or []) if str(x).strip()]
        today = '、'.join(names[:12]) or '（今天没对上一处设定地点 —— 那就只画当前这一处）'
        base = _atlas_block(layers)
        # ★★ 2026-10-10：把**作者写的那一段正文**也给它（用户点名要的闭环）。
        #   用户原话：「每段故事先把场景描述的很清楚，按照给美术 Agent 使用
        #   可以清晰画出地图为准」。所以小说作家那边已经按"可画地图"写场景卡了
        #   （见 `SCENE_CARD_RULES`）—— 但**光写没用，得有人读**：
        #   这张图的"说明"里该有什么器物、屋子朝哪边、哪处亮着灯，
        #   答案就在这段正文里，不在分拍的一句话里。
        #   截 1200 字：地图只需要空间信息，不需要把整章塞进来。
        # [EN] ★★ 2026-10-10: also give it **the passage of prose the author wrote** (the loop the user
        # [EN] explicitly asked for).
        # [EN] The user's exact words: "For each story segment, first describe the scene very clearly, for use
        # [EN] by the art
        # [EN] Agent, with the standard being that it can clearly draw a map". So the novelist side already
        # [EN] writes scene cards to the "drawable map" standard
        # [EN] (see `SCENE_CARD_RULES`) -- but **writing alone is useless; someone has to read it**:
        # [EN] what objects should appear in this image's "description", which way the room faces, where the
        # [EN] light is on --
        # [EN] the answer is in this passage of prose, not in a one-liner from the shot breakdown.
        # [EN] Truncate to 1200 characters: the map only needs spatial information, no need to stuff the whole
        # [EN] chapter in.
        story_txt = (str(getattr(ctx, 'story', '') or '').strip())[:1200] or '（没拿到正文）'
        story_block = ('── 作者写的今天这一段（**照它补细节**：器物、光从哪来、'
                       '人站哪儿）──\n' + story_txt + '\n')

        if base:
            prompt = f"""你是一部剧的**美术**。今天要拍的戏在下面。
这是一本**已经有底图**的书 —— 下面这份底图是**开卷时定好的空间事实**，
你的活是**从底图里取景，再按今天补细节**，不是重新排一遍。

── 今天要拍的几件事（方括号里是这一拍发生的地点）──
{beat_txt}

── 现在人在哪儿 ──
{here or '（未定）'}

{story_block}
── 底图（**位置照抄，不要自己重排**）──
{base}

── 今天这场戏涉及到的地点（**这份清单就是这张图的全部内容**）──
{today}

── 手艺（画面怎么承住戏）──
{craft}

硬要求：
1. **位置一律照底图**：底图里有的，`x` / `y` **逐字沿用**（这是"位置稳定"的全部意义）。
   底图里没有、今天才出现的，才自己定位置，放在相关的那一处旁边。
2. **图上只许出现上面清单里的那几处**，一处都不许多。今天没戏的地方
   —— 尤其是这本书的世界观里那些大地方（各界、各域、各国）—— **一个都不要画**。
   这是"今天这一场的小地图"，不是全书总图。
2b. `说明` **要从上面那段正文里长出来**：正文写了"灶在东边、灯笼挂在檐下"，
   这一处的说明就该带上它，别自己另编一套。正文没写到的，才按这类建筑的常识补。
2c. ★★ **名字写具体、里外分清**（用户 2026-10-12 点名）：
   名称就用**那件东西 / 那个地方本身的名字**（「井」「院子」「柜台」「堂屋」「大门」），
   **别写"某处""一角"这种含糊话** —— 图上"什么在屋里、什么在院里"全靠名字认。
   **见天的东西（井、树、影壁、水缸）归院里**；**有顶的东西（柜台、条案、灶台）
   归屋里**。★ **出现井就必须同时出现院子** —— 没有院子就补一个（院子是这个建筑的一部分）。
   门写在**边界**上（门不在屋里，它是内外之分）。
3. `名称` **必须**从底图或上面那份清单里逐字取；**一个也不许新编**，
   也不要在 `说明` / `题记` 里提到清单以外的名字。
4. `形` 从这些里挑一个：屋 楼 院 桥 船 街 山 树 井 塔 门 田。
5. `通路` 只连**底图里画了、或剧情里真的走过来**的那两处（`[["甲","乙"]]`）。
6. 只输出 JSON，不要 ``` 围栏：

{{"地点": [{{"名称": "…", "x": 0.5, "y": 0.6, "形": "楼", "说明": "一句话"}}],
  "通路": [["甲", "乙"]], "题记": "两个字的题记"}}"""
        else:
            prompt = f"""你是一部剧的**美术**。今天要拍的戏在下面。请画出**今天这张图**：
今天这几场戏发生在哪几处地方、彼此在什么位置。

── 今天要拍的几件事（方括号里是这一拍发生的地点）──
{beat_txt}

── 现在人在哪儿 ──
{here or '（未定）'}

{story_block}
── 今天这场戏涉及到的地点（**这份清单就是这张图的全部内容**）──
{today}

── 手艺（画面怎么承住戏）──
{craft}

硬要求：
1. **图上只许出现上面清单里的那几处**，一处都不许多。今天没戏的地方
   —— 尤其是这本书的世界观里那些大地方（各界、各域、各国）—— **一个都不要画**。
   这是"今天这一场的小地图"，不是全书总图。
2. `名称` **必须**从上面那份清单里逐字取；清单以外的名字**一个也不许出现**，
   也不要在 `说明` / `题记` 里提到它们。
2b. `说明` **要从上面那段正文里长出来**：正文写了什么器物、哪边有门、什么时辰、
   哪一处亮着灯，就照它写；正文没写到的，才按这类建筑的常识补。
2c. ★★ **名字写具体、里外分清**（用户 2026-10-12 点名）：
   名称就用**那件东西 / 那个地方本身的名字**（「井」「院子」「柜台」「堂屋」「大门」），
   **别写"某处""一角"这种含糊话** —— 图上"什么在屋里、什么在院里"全靠名字认。
   **见天的东西（井、树、影壁、水缸）归院里**；**有顶的东西（柜台、条案、灶台）
   归屋里**。★ **出现井就必须同时出现院子** —— 没有院子就补一个（院子是这个建筑的一部分）。
   门写在**边界**上（门不在屋里，它是内外之分）。
3. `x` / `y` 是 0~1 的相对位置（左上角是原点，x 向右、y 向下）。
   把**现在人在的那一处**放在中间偏下（约 0.5, 0.6），其余按剧情里的**先后与方位**排开。
   只有一处时就把它放在画布正中。
4. `形` 从这些里挑一个：屋 楼 院 桥 船 街 山 树 井 塔 门 田。
5. `通路` 只连**剧情里真的走过来**的那两处（`[["甲","乙"]]`）；没走过来就留空数组。
6. 只输出 JSON，不要 ``` 围栏：

{{"地点": [{{"名称": "…", "x": 0.5, "y": 0.6, "形": "楼", "说明": "一句话"}}],
  "通路": [["甲", "乙"]], "题记": "两个字的题记"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_day_map', want=dict,
                        max_tokens=CFG.i('CREW_ART_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title='当天地图',
                            why='；'.join(rep.notes) or '没给出当天的地图')
        raw = [x for x in (data.get('地点') or data.get('places') or [])
               if isinstance(x, dict)]
        if not raw:
            return CrewNote(role=self.key, ok=False, title='当天地图',
                            why='当天的地图是空的')
        got = [str(x.get('名称') or '').strip() for x in raw]
        keep = [g for g in got if g and (not names or g in names)]
        return CrewNote(
            role=self.key,
            title=f'今天 {len(keep or got)} 处：' + '、'.join((keep or got)[:4]),
            body='\n'.join(f"- {x.get('名称')}：{str(x.get('说明') or '')[:40]}"
                            for x in raw[:6]),
            data={'kind': 'day_map',      # ⚠ 必须在**这里**就标上：
                  #   `studio.call()` 拿到返回值之后立刻 `_save_note()`，
                  #   事后再补标记已经晚了（那样当天地图会覆盖「美术指导.md」）
            # [EN] ⚠ Must be marked **here**:
            # [EN] right after `studio.call()` gets the return value, immediately [`_save_note()`],
            # [EN] marking it afterwards is already too late (in that case the day's map would overwrite [EN] 「美术指导.md」).
                  '地点': raw,
                  '通路': data.get('通路') or data.get('links') or [],
                  '题记': str(data.get('题记') or data.get('caption') or '')[:12],
                  '这里': here,
                  # 底图里有哪些层可用（给界面/判据看"这次到底有没有取景"）
                  # [EN] Which layers are available in the base map (for the UI/criteria to see "whether framing was
                  # [EN] actually done this time").
                  '底图': [{'层': k, '地点': n} for k, n, _ in (layers or [])],
                  # 模型编出来的名字**留个痕**（调用方按白名单再滤一遍）
                  # [EN] Leave a **trace** of names the model made up (the caller filters again against a whitelist).
                  '越界': [g for g in got if g and names and g not in names]})


class ExtraCasting(CrewMember):
    """**群众演员**（临演/群演）：门外的人与事。

    这个职位本来就在跑（`world/crowd.py`），但它以前是**从固定池里抽的**：

        pool = _NEED_BY_KIND[kind]   # 一张写死的小表
        who, need = rng.choice(pool)

    后果很实在 —— 同一个茶楼里，**每一个讨债的人说的是同一句话**
    （"你欠的三两银子该还了"），每一个路过的货郎问的是同一件事。
    群演是"外部输入"这件事没错，但输入要是**同一批罐头**，人物很快就学会了
    无视它们（那正是"空转"的另一种形态：有输入，但都是无效输入）。

    所以这里补上 **AI 那一档**：让群演按**这一场正在演什么**来投人 ——
    什么身份的人此刻最可能走进来、他要什么、他跟这条线有没有关系。
    规则池留着当**兜底**（拿不到就照旧抽一个，不能让推演停在这一步）。

    ⚠ 两条硬约束，都在 `cast()` 里落实：
      · **闸门照旧**（`EXTRAS_ENABLED`/上限/当日预算）—— AI 不该绕开预算；
      · **不许造主要人物**：回来的人名若与在场人物重名，直接判废（走兜底）
        —— 群演不能顶替角色，那会把人物关系搅乱。
    
        English:
    **Extras** (background actors/extra): the people and matters outside the door.
        This role was already running (`world/crowd.py`), but it used to be **drawn from a fixed pool**:
            pool = _NEED_BY_KIND[kind]   # a small hardcoded table
            who, need = rng.choice(pool)
        The consequences are very real -- in the same teahouse, **every debt collector says the same line**
        ("You owe three taels of silver, time to pay up"), and every passing peddler asks the same thing.
        Extras being "external input" is not wrong, but if the input is **the same batch of canned goods**, the characters quickly learn to
        ignore them (that is another form of "spinning in place": there is input, but it is all invalid input).
        So the **AI tier** is added here: let extras be cast according to **what is being performed in this scene** --
        what kind of identity is most likely to walk in right now, what they want, whether they have any relation to this thread.
        The rule pool is kept as a **fallback** (if it cannot be obtained, draw one as before; the simulation must not stall at this step).
        ⚠ Two hard constraints, both enforced in `cast()`:
          · **The gates stay as before** (`EXTRAS_ENABLED`/cap/daily budget) -- AI should not bypass the budget;
          · **No creating main characters**: if a returned name duplicates an on-scene character's name, it is rejected outright (falls back)
            -- extras cannot replace roles, that would scramble character relationships.
    """

    key = 'extra'

    async def work(self, ctx: SetCtx, **kw) -> CrewNote:
        """报状态（**不产生 LLM 调用**）—— 见 `OnDuty` 的同名说明。
                English:
        Report status (**does not produce an LLM call**) — see the same-named description in `OnDuty`.
        """
        line = ''
        try:
            from world import crowd
            n = crowd.crowd_size(ctx.world)
        except Exception:                                        # noqa: BLE001
            n = 0
        line = f'门外 {n} 人' if n else '门外无人'
        return CrewNote(role=self.key, title=line, ok=True)

    async def cast(self, ctx: SetCtx, *, kind_hint: str = '',
                   fallback: bool = True) -> dict | None:
        """投一个群演。返回 `{'称呼','诉求','标志'}`，或 `None`。

        `kind_hint` = 这一场的性质（堂/街/渡口…，由 `world.crowd.scene_kind` 给）。
        `fallback=False` 时不走规则兜底（给验证脚本用来**只看 AI 那一档**）。
        
                English:
                `kind_hint` = the nature of this scene (堂/街/渡口…, given by `world.crowd.scene_kind`).
                When `fallback=False`, the rule-based fallback is not used (for the validation script to **look only at the AI tier**).
        """
        from world import crowd
        # ★★★ 2026-10-21：**先把"此刻在推进的几件事"摊出来**（用户报"群演出现没道理"）。
        #   没有正在推进的事 ⇒ 门口本来就该空着，**不投人**，一次调用都不必花。
        # [EN] ★★★ 2026-10-21: **lay out "the few things moving right now" first** (the user
        # [EN] reported extras appearing for no reason). No moving matter => the door should be
        # [EN] empty, **no casting**, not even one call.
        threads = crowd.open_threads(ctx.world)
        if not threads:
            _LOG.info('此刻没有正在推进的事（主线/当时的话/人物手上的活都是空的），不投群演')
            return None
        thread_lines = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(threads))
        pool = list(crowd._NEED_BY_KIND.get(kind_hint or '', [])) or list(
            crowd._NEED_DEFAULT)
        sample = '、'.join(f'{w}（{n}）' for w, n in pool[:4]) or '（无）'
        genre, structure = ctx.genre()
        cast = '、'.join(ctx.people[:10]) or '（还没有人）'
        try:
            rep = await ask('cheap',
                            [{'role': 'user',
                              'content': f"""你是一部剧的**群演统筹**（临时演员）。
请按**这一场正在发生什么**，投一个此刻最可能走进来的人。

── 这是什么戏 ──
{ctx.world_brief(700)}
{ctx.scene_line()}

── 在场的主要人物 ──
{cast}

── 前情 ──
{ctx.recap(600)}

── 此刻正在推进的事（**他只能为这里的一件事来**）──
{thread_lines}

── 这一场常见哪一类人（老规矩，供你参考，**不必照抄**）──
{sample}

要求：
1. **他说得出为什么此刻来**：必须是冲着上面某一件事来的 —— 讨要、打听、报信、
   认错人、送错东西、来找人…说不出由头的，就不要投他。
2. 给一个**具体身份的路人**（不要"一个男人"这种泛称），一句话说清他要什么。
3. 他可以是来**添乱/加码/换个说法**的，不必替主角把事办成 —— 但他要的那件事
   必须和上面某一条**接得上**，不能是无关的另一件事。
4. `称呼` ≤ 8 字、`诉求` ≤ 20 字、`标志` ≤ 10 字（一个记得住的小特征）。
5. **不要用上面在场人物的名字** —— 他是临时演员，不是角色。
6. `挂` = 上面那件事的**序号**（整数，只许填 1~{len(threads)}）；
   `接` = 一句话说清他怎么会搭上这件事（≤ 20 字）。
7. 只输出 JSON：{{"称呼": "…", "诉求": "…", "标志": "…", "挂": 1, "接": "…"}}"""}],
                            purpose='crew_extra', want=dict,
                            max_tokens=CFG.i('CREW_EXTRA_TOKENS'))
        except Exception as e:                                   # noqa: BLE001
            _LOG.info('群演统筹没拿到结果（%r），走规则兜底', e)
            rep = None
        data = rep.value if (rep is not None and rep.ok
                             and isinstance(rep.value, dict)) else None
        if data:
            who = str(data.get('称呼') or '').strip()[:8]
            need = str(data.get('诉求') or '').strip()[:20]
            mark = str(data.get('标志') or '').strip()[:10]
            known = {str(x) for x in ctx.people}
            # ★★★ `挂` 是**闭集序号**：模型只能选一个已经存在的编号。
            #   填不出/越界 ⇒ 这个人没有落点 ⇒ 不投（不是"投得不好"，是"不该来"）。
            #   为什么不让它自己写"跟主线有什么关系"：自由文本只能做字面比对，
            #   换个说法就归零（MEMORY：同义词是字面判据的后门）。
            # [EN] ★★★ `挂` is a **closed-set index**: the model can only pick an existing number.
            # [EN] Missing/out of range => this person has no place to land => do not cast (not
            # [EN] "bad casting", but "he shouldn't come"). Why not let it write "how this relates
            # [EN] to the main line": free text can only be judged literally, and a synonym resets
            # [EN] it to zero (MEMORY: synonyms are the back door of literal criteria).
            try:
                idx = int(str(data.get('挂') or '').strip())
            except (TypeError, ValueError):
                idx = 0
            if who and need and who not in known and 1 <= idx <= len(threads):
                return {'称呼': who, '诉求': need, '标志': mark,
                        '挂': threads[idx - 1],
                        '接': str(data.get('接') or '').strip()[:20]}
            if who and need and who not in known:
                _LOG.info('群演统筹投的人没挂到正在推进的事上（挂=%r，共 %d 件），这次不投',
                          data.get('挂'), len(threads))
                return None
            if who and who in known:
                # 群演顶了角色的名 —— 那不是"投得不好"，那是**错了**，
                # 必须换（会让读者以为那个人来了）。
                # [EN] An extra taking the name of a character -- that's not "bad casting", that's **wrong**,
                # [EN] and must be changed (it would make readers think that person showed up).
                _LOG.info('群演统筹投出一个与在场人物同名的临时演员（%s），改走兜底', who)
        if not fallback:
            return None
        # 兜底：老规矩（固定池抽一个）—— 拿不到 AI 也不能让门外没人。
        # ⚠ 但兜底**也要挂得住那条线**：判据在 `crowd.pick_from_pool` 里
        #   （池子里那条诉求跟正在推进的事共用 ≥2 个实字才算搭得上，否则返回 None）。
        # [EN] Fallback: the old rule (draw one from a fixed pool) -- even if AI is unavailable, don't leave
        # [EN] the door empty. ⚠ But it **must also be anchorable**: the criterion lives in
        # [EN] `crowd.pick_from_pool` (the pool demand must share >= 2 content characters with the
        # [EN] moving matter, else None).
        return crowd.pick_from_pool(ctx.world)


# ══════════════════════════════════════════════════════════════════════
#  排练（2026-10-07 新增）
# [EN] Rehearsal (added 2026-10-07)
# ══════════════════════════════════════════════════════════════════════
class Rehearsal(CrewMember):
    """**排练**：剧本定稿之后、正式开演之前，把这一天**先空走一遍**。

    用户 2026-10-07：「排练你是说剧本出来所有人先快速走一遍但是不出现结果
    在窗口里吗？如果是的话可以加排练这个阶段。」

    ★ 就是这个意思，而且是**一整个剧组那个意义上的"走一遍"**：
    把分拍交给模型，让它**挨个代入每个在场人物**自问 ——

    | 排练要问出来的 | 为什么正式开演时才发现就晚了 |
    |---|---|
    | 这个人物**做不做得到**（性格/处境/能力上） | 演员上了场只能硬演，演出来就是 OOC |
    | 这个人物**在不在这一拍的地方** | 不在场的人被派了活 = 剧本里有、场上看不见 |
    | 这一拍有没有**写死台词/写死动作** | 写死了演员就成了提线木偶（本项目一直在防的） |
    | 拍与拍之间**接不接得上** | 跳步的戏，演员只能在中间自己编一段来圆 |

    ★★ **"不出现结果"是靠结构保证的**，不是靠自觉：
    它的产出**只落进 `排练记录.md` 与日志**（`ARTIFACT['rehearsal']`），
    中栏那一路由 `sim/loop` 的阶段小消息负责 —— 那条消息只会说
    「剧组排练 · 3.2s」，拿不到这里的任何一行字（见 `crew/studio.stage`）。

    ⚠ **为什么一次调用问全体，而不是每人一次**：`N 人 × 每天` 是真金白银的
      调用量，而"读本会"本来就是**一屋子人一起过一遍**的艺术形式 ——
      一次调用让模型逐个代入，正是排练本身的做法，不是省钱的借口。
      拿到的东西照旧具体到人（问题里必须写清"哪一拍、谁、为什么"）。

    ⚠ **没给出问题 ≠ 没出活**："这一天走得通"也是一个合格的结论
      （与编剧室"不用补设定也是结论"同源）。
    
        English:
    **Rehearsal**: after the script is finalized and before the official performance, **walk through
    this day once first**.
        User 2026-10-07: "By rehearsal do you mean after the script comes out everyone quickly walks through it once but no results
        appear in the window? If so, you can add a rehearsal stage."
        ★ That is exactly the meaning, and it is **"a walkthrough" in the sense of the entire crew**:
        hand the shot breakdown to the model, and have it **step into each on-scene character one by one** and ask itself --
        | What rehearsal must ask | Why discovering it only at the official performance is too late |
        |---|---|
        | Can this character **actually do it** (in terms of personality/situation/ability) | The actor is already on stage and can only force the performance, which comes out as OOC |
        | Is this character **at the location of this shot** | Someone not present being assigned work = present in the script, invisible on stage |
        | Does this shot have **hardcoded dialogue/hardcoded actions** | Once hardcoded, the actor becomes a marionette (what this project has been guarding against all along) |
        | Do **shot-to-shot transitions connect** | In a scene with skipped steps, the actor can only improvise a segment in between to make it coherent |
        ★★ **"No results appear" is guaranteed by structure**, not by self-discipline:
        its output **only lands in `排练记录.md` and logs** (`ARTIFACT['rehearsal']`),
        the middle column is handled by `sim/loop`'s stage mini-message -- that message only says
        "Crew rehearsal · 3.2s", and does not get any line from here (see `crew/studio.stage`).
        ⚠ **Why ask everyone in one call instead of one per person**: `N people x every day` is real money in
          call volume, and a "read-through" is inherently an art form of **a room full of people going through it together** --
          one call having the model step in one by one is exactly how rehearsal itself works, not an excuse to save money.
          What is obtained is still specific to individuals (the question must clearly state "which shot, who, why").
        ⚠ **Not being given a question != no output**: "this day works" is also a valid conclusion
          (same origin as the writers' room: "not needing to add setting is also a conclusion").
    """

    key = 'rehearsal'

    async def work(self, ctx: SetCtx, *, story: str = '',
                   beats: list[dict] | None = None,
                   roles: dict | None = None) -> CrewNote:
        if not CFG.b('CREW_REHEARSAL'):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='排练已关闭（CREW_REHEARSAL=false）')
        rows = [b for b in (beats or []) if isinstance(b, dict)]
        if not rows:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='还没有分拍，无从排练')
        people = '、'.join(str(x) for x in (ctx.people or [])[:12]) or '（还没有人）'
        beat_txt = '\n'.join(
            f"{b.get('拍', i)}. [{b.get('场', '')}] {b.get('发生', '')}"
            f"（推进：{b.get('推进', '')}）"
            for i, b in enumerate(rows, 1))
        assign = '\n'.join(f'- {n}：{"；".join(str(x) for x in (v or []))}'
                           for n, v in (roles or {}).items()) or '（还没派活）'
        prompt = f"""你是这个剧组的**排演指导**。剧本已经定稿，现在**开演前排一遍**。

排一遍的意思是：**你挨个代入每个在场人物，把这几拍从头走一遍**，看走不走得下去。
不是评论这个剧本好不好 —— 是"真到了场上，这一步迈得出去吗"。

── 今天要演的故事 ──
{str(story or '')[:900]}

── 分拍 ──
{beat_txt}

── 派活 ──
{assign}

── 在场的人 ──
{people}

── 这本书的底子 ──
{ctx.world_brief(600)}

逐条自问（**每一条都落到实处才算过**）：
① **做不做得到**：这一拍派给他的事，按他的身份、性格、处境，他做得出来吗？
② **人在不在**：写进这一拍的人，那时那地**真的在场**吗？
③ **有没有写死**：有没有把台词或动作写死到"他只能照着念"（那是提线木偶）？
④ **接不接得上**：第 N 拍和第 N+1 拍之间有没有跳步、要靠演员自己编一段来圆？

要求：
1. `问题`：0~4 条。每条必须写清 **哪一拍 · 谁 · 为什么走不下去**，
   再给一句**怎么改**（具体到能照着改）。走得出彩的地方不用夸。
2. **走得通就给空数组** —— 不要为了凑数编问题（"走了一遍没毛病"是合格结论）。
3. `结论`：一句话，说清这一天排下来**整体成不成**。
4. 只输出 JSON，不要 ``` 围栏：

{{"问题": [{{"拍": 3, "谁": "…", "问题": "…", "怎么改": "…"}}],
  "结论": "…"}}"""
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        purpose='crew_rehearsal', want=dict,
                        max_tokens=CFG.i('CREW_REHEARSAL_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没拿到排练结论')
        items: list[dict] = []
        for x in (data.get('问题') or [])[:6]:
            if isinstance(x, str):
                x = {'问题': x}
            if not isinstance(x, dict):
                continue
            what = str(x.get('问题') or '').strip()
            if not what:
                continue
            try:
                beat_no = int(x.get('拍') or 0)
            except (TypeError, ValueError):
                beat_no = 0
            items.append({'拍': beat_no,
                          '谁': str(x.get('谁') or '').strip()[:16],
                          '问题': what[:160],
                          '怎么改': str(x.get('怎么改') or x.get('建议')
                                        or '').strip()[:160]})
        verdict = str(data.get('结论') or '').strip()[:120]
        if not items:
            return CrewNote(role=self.key, ok=True,
                            title='排下来走得通' + (f'（{verdict[:30]}）' if verdict else ''),
                            body=verdict or '一屋子人过了一遍，没发现走不下去的地方。',
                            data={'问题': [], '结论': verdict, '问题数': 0})
        md = [f'**结论**　{verdict}' if verdict else '', '']
        for it in items:
            head = f"- 第 {it['拍']} 拍" if it['拍'] else '- '
            if it['谁']:
                head += f" · {it['谁']}"
            md.append(f'{head}：{it["问题"]}')
            if it['怎么改']:
                md.append(f'  改：{it["怎么改"]}')
        return CrewNote(role=self.key, ok=True,
                        title=f'排演发现 {len(items)} 处走不下去',
                        body='\n'.join(md).strip(),
                        data={'问题': items, '结论': verdict,
                              '问题数': len(items)})


class Researcher(CrewMember):
    """**资料员**：考据 —— 这一处的名物、制度、称谓站不站得住。

    接到的是 `research/`（本地考据）与 `refs/`（参考文本检索）那条路。
    给剧作者用：他写"掌柜拿着一串铜钱去兑银子"时，年代与手续对不上，
    读者是会出戏的。

    ⚠ **没有可查的材料时明说"查不到"**（不编）—— 编出来的考据比不考据更坏，
      因为它看起来像有依据。
    
        English:
    **Researcher**: fact-checking -- whether the names, institutions, and titles in this place hold
    up.
        What is received is the path of `research/` (local fact-checking) and `refs/` (reference text retrieval).
        For the playwright: when he writes "the shopkeeper takes a string of copper coins to exchange for silver", if the era and procedures do not match,
        the reader will be pulled out of the story.
        ⚠ **When there is no verifiable material, say plainly "cannot find it"** (do not make it up) -- fabricated fact-checking is worse than none,
          because it looks like it has a basis.
    """

    key = 'researcher'

    async def work(self, ctx: SetCtx, *, story: str = '') -> CrewNote:
        if not CFG.b('CREW_RESEARCH'):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='考据已关闭（CREW_RESEARCH=false）')
        text = str(story or '').strip()
        if not text:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='今天还没有样章可查')
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        # ★ 思维链骨架（2026-10-07 第七轮）：先把"会被查出来的名物"逐个挑出来，
        #   再判站不站得住 —— 防它跳过"挑"这一步，直接凭印象说"不对"。
        # [EN] ★ Chain-of-thought skeleton (2026-10-07, seventh round): first pick out one by one the "named
        # [EN] items that would be checked",
        # [EN] then judge whether they hold up -- preventing it from skipping the "pick" step and saying
        # [EN] "wrong" straight from impression.
        _cot = cognition_block(self.key)
        cot_block = f'\n{_cot}\n' if _cot else ''
        prompt = f"""你是一部剧的**资料员**（考据）。下面这一段里，凡涉及**名物、制度、
称谓、手续、场合规矩**的地方，请指出**站不住**的，并给出可写的替代。

── 时代与地界 ──
{ctx.world_brief(800)}

── 考据的规矩 ──
{craft}

── 待查的段落 ──
{text[:1800]}
{cot_block}
要求：
1. 只挑**真的会让人出戏**的（名物用错朝代、称谓不合身份、手续不合规矩）。
   文笔、结构、节奏不归你管。
2. 每条写：**原句片段 → 为什么不对 → 那个年代该怎么写**（一句话）。
3. **查不到就明说"查不到"** —— 不要编一条看起来像有依据的说法。
4. 没有可指之处就输出空数组。

只输出 JSON：{{{think_schema_of(self.key)}"存疑": ["…"], "结论": "一句话"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_research', want=dict,
                        max_tokens=CFG.i('CREW_RESEARCH_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没拿到考据结论')
        items = [str(x).strip() for x in (data.get('存疑') or [])
                 if str(x).strip() and str(x).strip() != '无']
        verdict = str(data.get('结论') or '').strip()
        check = str(data.get('核查') or '').strip()[:200]
        if not items:
            return CrewNote(role=self.key, title='考据无存疑' + (
                f'（{verdict[:40]}）' if verdict else ''), body=verdict,
                data={'存疑': [], '核查': check})
        return CrewNote(role=self.key, title=f'考据存疑 {len(items)} 处',
                        body=verdict + ('\n' if verdict else '')
                             + '\n'.join(f'{i}. {x}'
                                         for i, x in enumerate(items[:5], 1)),
                        data={'存疑': items, '核查': check})


# ══════════════════════════════════════════════════════════════════════
#  后期组：宣发
# [EN] Post-production crew: publicity
# ══════════════════════════════════════════════════════════════════════
class Publicity(CrewMember):
    """**宣发**：一句话卖点、看点、预告。

    为什么值得有：一部戏写完了，作者要拿它给别人看 —— 这时候最缺的是
    「一句话说清它是什么」。以前导出里只有事实块（多少天、多少字、多少事件），
    全是**体检数据**，没有一句**能拿出去说的话**。

    产出落进**运行文件夹根**的 `宣发文案.md`，并在收工时上屏一次。

    ⚠ 2026-10-07 审计改的两处**说法**（原文与事实不符，是"文档在撒谎"）：
      · 原文写"落进 `导出/宣发文案.md`" —— 实际落的是运行文件夹根
        （`crew/studio.ARTIFACT` 的路径都相对运行文件夹根）；
      · 名册原来写 `feeds='export'`（"产出交给导出"）—— 而 `export/*` 里
        **搜不到任何一处读 `宣发文案`**。改成 `author`：它就是给作者拿出去说的，
        **不进导出物**（导出装订的是正文与报告，剧组产物是过程档案）。
    
        English:
    **Promotion**: one-line selling point, highlights, trailer.
        Why this is worth having: once a play is written, the author needs to show it to others -- and what is most lacking then is
        "explain clearly in one line what it is". Previously the export only had fact blocks (how many days, how many words, how many events),
        all **checkup data**, not a single **line that can be said out loud**.
        The output lands in `宣发文案.md` at the **root of the run folder**, and is displayed once at wrap-up.
        ⚠ Two **wordings** changed in the 2026-10-07 audit (the original text did not match the facts; "the docs were lying"):
          · The original said "lands in `导出/宣发文案.md`" -- it actually lands at the root of the run folder
            (paths under `crew/studio.ARTIFACT` are all relative to the run folder root);
          · The roster originally said `feeds='export'` ("output goes to export") -- but nowhere under `export/*`
            **can any read of `宣发文案` be found**. Changed to `author`: it is meant for the author to take out and talk about,
            **does not go into the export artifacts** (export binds the main text and reports; crew artifacts are process archives).
    """

    key = 'publicity'

    async def work(self, ctx: SetCtx, *, lines: list[str] | None = None) -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        body = '\n'.join(str(x) for x in (lines or []) if str(x).strip())[:2500]
        if not body:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='还没有可宣的内容')
        core = ctx.recap(700) or ctx.story
        prompt = f"""你是一部剧的**宣发**。请为它写一组宣传物料。

── 这是什么戏 ──
题材：{genre or '（未定）'}{f'·{structure}' if structure else ''}
{ctx.world_brief(700)}

── 手艺（怎么抓人）──
{craft}

── 到目前的剧情 ──
{core[:800]}

── 最近这一段正文 ──
{body}

★ **钩子要换着来**（这一步借鉴 `AICMO/AiCMO-Marketing-Prompt-Collection`，
  Apache-2.0 —— 它那套"钩子转换矩阵"的核心是：**同一条内容，换一种心理触发重新说一遍**。
  只借这个做法，词句全部按中文重写）。五类触发，一条只准用一种：
  · 悬念 —— 抛一个答案还没给的问题（"那只壶他擦了七年，今天第一次没擦"）；
  · 反差 —— 把两个不搭的东西并在一起（"算命的不收钱，只要一句话"）；
  · 代入 —— 说读者自己会碰上的处境（"欠了人情，怎么还都不对"）；
  · 稀缺 —— 时间/数量上有边（"过今晚，这条街就没有这家店了"）；
  · 身份 —— 这是个什么人、会做什么样的事（"管了三十年闲事，只管一件"）。

要求（**不要剧透结局**，不要写成剧情梗概）：
1. `一句话`：**≤ 25 字**，能直接印在海报上。要有具体的物/事，不要空泛形容，
   并且**必须落在上面五类里的一类**上。
2. `看点`：3 条，各 ≤ 20 字，说的是"读者为什么想追下去"。
   **三条要用三种不同的钩子**（同类不算数）—— 三条都在抛悬念，等于只有一条。
3. `预告`：2~3 句，用正文里的语气，最后留一个悬念（不要揭底）。

只输出 JSON：{{"一句话": "…", "看点": ["…"], "预告": "…"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_publicity', want=dict,
                        max_tokens=CFG.i('CREW_PUBLICITY_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给宣发文案')
        one = str(data.get('一句话') or '').strip()
        hooks = [str(x).strip()[:30] for x in (data.get('看点') or [])
                 if str(x).strip()][:5]
        teaser = str(data.get('预告') or '').strip()
        if not (one or hooks or teaser):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='宣发文案是空的')
        parts = []
        if one:
            parts.append(f'**{one}**')
        if hooks:
            parts.append('看点：\n' + '\n'.join(f'- {x}' for x in hooks))
        if teaser:
            parts.append('预告：\n' + teaser)
        return CrewNote(role=self.key, title=one or '宣发文案',
                        body='\n\n'.join(parts),
                        data={'一句话': one, '看点': hooks, '预告': teaser})


# ══════════════════════════════════════════════════════════════════════
#  在位者（演员 / 群众演员 / 导演）
# [EN] Incumbents (actors / extras / director)
# ══════════════════════════════════════════════════════════════════════
# 这三个职位**早就在跑**（各自有成熟的实现），这里只做两件事：
#   ① 提供一个"报状态"的入口，让界面上的剧组面板能显示他们在干什么；
#   ② 把它们也纳入名册的顺序与自查，让剧组是**完整的一班人**，
#      而不是"新来的几个 + 无名氏"。
# [EN] These three roles **have long been running** (each has a mature implementation); here only two
# [EN] things are done:
# [EN] ① Provide a "report status" entry point so the crew panel on the UI can show what they're doing;
# [EN] ② Also bring them into the roster's ordering and self-check, so the crew is **a complete
# [EN] shift**,
# [EN] not "a few newcomers + nameless people".
# ⚠ **不重新实现**。演员就是 `agent.core.Agent`、群众演员就是 `world/crowd`、
#   导演就是 `director.engine.DirectorEngine` —— 这一层只是转述。
# [EN] ⚠ **Do not reimplement**. Actors are `agent.core.Agent`, extras are `world/crowd`,
# [EN] the director is `director.engine.DirectorEngine` -- this layer only relays.
class OnDuty(CrewMember):
    """已在位职位的**状态转述**（不产生 LLM 调用）。

    `status_of` 返回一句"他们此刻在干什么"，供界面显示。
    
        English:
    **Status recital** of positions already in place (does not produce an LLM call).
        `status_of` returns a sentence of "what they are doing right now", for the UI to display.
    """

    def __init__(self, key: str, describe=None):
        self.key = key
        self._describe = describe

    async def work(self, ctx: SetCtx, **kw) -> CrewNote:
        line = ''
        if callable(self._describe):
            try:
                line = str(self._describe(ctx) or '')
            except Exception:                                    # noqa: BLE001
                line = ''
        line = line or self._fallback_line(ctx)
        return CrewNote(role=self.key, title=line, body='', ok=bool(line),
                        why='' if line else '暂时没有可报的')

    def _fallback_line(self, ctx: SetCtx) -> str:
        w = ctx.world
        if self.key == 'actor':
            n = len(ctx.people)
            line = f'{n} 位在场' if n else ''
            # ★ 捎上**最近一次的盘算**（2026-10-07 第七轮）：演员每拍跑一次
            #   思维链（`crew/cognition`），那几句"开口之前在想什么"是这个
            #   职位最值得给作者看的东西 —— 它既不是台词也不是心声，
            #   平时没有任何地方能看到。台账会落盘（`剧组台账.md`），
            #   所以这句话是可以回头查的。
            # [EN] ★ Include **the most recent deliberation** (2026-10-07, seventh round): the actor, once per
            # [EN] shot,
            # [EN] runs a chain of thought (`crew/cognition`); those lines of "what he's thinking before speaking"
            # [EN] are
            # [EN] the most worthwhile thing for this role to show the author -- it is neither dialogue nor inner
            # [EN] monologue,
            # [EN] and normally there's nowhere to see it. The ledger persists to disk (`剧组台账.md`),
            # [EN] so this sentence can be looked up later.
            tr = ''
            try:
                store = getattr(w, 'actor_think', None) or {}
                if isinstance(store, dict) and store:
                    # 取**名字排序最后一个**是不行的（那是随机的人）——
                    # 台账是一行汇总，所以给一条有代表性的：最近被刷新的那位。
                    # `dict` 保序，最后写进去的就是这一拍最后决策的人。
                    # [EN] Taking **the last one in name order** doesn't work (that's a random person) --
                    # [EN] the ledger is a one-line summary, so give a representative one: the person most recently
                    # [EN] refreshed.
                    # [EN] `dict` preserves order, so the last one written is the person who made the last decision in this
                    # [EN] shot.
                    nm, val = next(reversed(store.items()))
                    tr = f'{nm}：{str(val)[:28]}'
            except Exception:                                    # noqa: BLE001
                tr = ''
            if tr:
                line = (line + '｜' if line else '') + tr
            return line
        if self.key == 'extra':
            try:
                from world import crowd
                n = crowd.crowd_size(w)
            except Exception:                                    # noqa: BLE001
                n = 0
            return f'门外 {n} 人' if n else '门外无人'
        if self.key == 'director':
            nd = ''
            try:
                info = w.current_node_info() or {}
                nd = str(info.get('名称') or '')
            except Exception:                                    # noqa: BLE001
                nd = ''
            return f'看着「{nd}」' if nd else '在场'
        return ''


class SettingsRoom(CrewMember):
    """**编剧室**：导演 · 小说作家 · 剧作者 **三方会审**，补**局部**设定。

    用户 2026-10-07
    ---------------
    「有些时候需要导演 和 小说作者 以及 剧作家 讨论生成一些新的设定
      这些都要进行推演 以便方便故事推进 同时不能够影响总体设定」

    为什么**一次调用演三个人**（而不是三次调用 + 一次汇总）：那三次问的是
    同一件事、读的是同一份材料，拆开只是把同一段话问三遍、钱花三倍，
    结论不会更齐。会审的产出是**一张清单**，不是三份意见书。

    两条闸门（**程序强制**，不是靠模型自觉 —— 见 `world/layers.admit_new`）：
      ① 只能新增**场景层 / 细节层**。世界层与主线层是作者的"总体设定"，
         剧组连"新增一条"都不行。
      ② 每条**必须有作用范围**（限地点 / 限人 / 限时间）。既不限地点、也不限人、
         也不限时的"设定"，实质上就是总体设定，只是换了个说法。
    被拒的条目**带原因返回**（`data['拒收']`）—— 静默丢掉的话，表现成
    "剧组讨论了半天什么都没发生"，而真正的原因（它想改世界层）就查不出来。

    ⚠ 产出**只进** `world.local_settings`（渲染时按层拼进提示词），
      **绝不并进** `worldview_text` / `rules_text` / 人物卡 ——
      "不能够影响总体设定"是靠这个结构保证的，不是靠约定。
    
        English:
    **Writers' room**: director · novel writer · playwright **three-way review**, to add **local**
    settings.
        User 2026-10-07
        ---------------
        "Sometimes the director and the novel author and the playwright need to discuss and generate some new settings;
          these all need to be deduced, to make it convenient for the story to advance, and at the same time must not affect the overall setting"
        Why **one call plays three people** (instead of three calls + one aggregation): those three calls ask about
        the same thing and read the same material; splitting it is just asking the same paragraph three times and paying three times,
        with no more coherent a conclusion. The review's output is **one checklist**, not three opinions.
        Two gates (**enforced by the program**, not relying on the model's self-discipline -- see `world/layers.admit_new`):
          ① Only **scene layer / detail layer** may be added. The world layer and mainline layer are the author's "overall setting";
             the crew cannot even "add one entry".
          ② Each entry **must have a scope** (location-limited / person-limited / time-limited). A "setting" limited by neither location, nor person,
             nor time is in essence the overall setting, just under a different name.
        Rejected entries **are returned with a reason** (`data['拒收']`) -- if silently dropped, it looks like
        "the crew discussed for ages and nothing happened", and the real reason (it wanted to change the world layer) cannot be found.
        ⚠ Output **only goes into** `world.local_settings` (assembled into the prompt by layer at render time),
          and **never merges into** `worldview_text` / `rules_text` / character cards --
          "must not affect the overall setting" is guaranteed by this structure, not by convention.
    """

    key = 'settings_room'

    #: 一次会审最多收几条（与 `world/layers.MAX_NEW_PER_ROUND` 同一个意思，
    #: 但这里写给模型看 —— 两边都写是因为一边是硬闸门、一边是提示词）。
    # [EN] : how many entries a single review can take at most (same meaning as
    # [EN] `world/layers.MAX_NEW_PER_ROUND`,
    # [EN] : but here it's written for the model -- both sides have it because one is a hard gate and one
    # [EN] is a prompt).
    MAX_ITEMS = 4

    async def work(self, ctx: SetCtx, *, story: str = '',
                   beats: list[dict] | None = None) -> CrewNote:
        from world import layers as L
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)

        # ── 桌上摆着什么 ──
        # ① 世界层与主线层：**给它们看，但明说不能改**（不改也得知道边界在哪）
        # [EN] ── What's on the table ──
        # [EN] ① World layer and mainline layer: **show them, but state clearly they can't be changed** (even
        # [EN] if not changing, they need to know where the boundary is)
        try:
            view = ctx.world.layer_view()
            canon = '；'.join(i.text for i in view.get('canon'))[:400] or '（没有写世界观）'
            arc = '；'.join(f'{i.name}：{i.text}' for i in view.get('arc'))[:400] \
                or '（没有进度节点）'
            have = '；'.join(
                f'[{L.layer_name(i.layer)}]{i.name}' for i in
                list(view.get('scene')) + list(view.get('detail')))[:500] or '（还没有）'
        except Exception:                                        # noqa: BLE001
            canon = arc = '（读不到）'
            have = '（读不到）'
        story_block = ''
        if str(story or '').strip():
            story_block = f'── 今天要演的戏 ──\n{story[:400]}\n\n'
        elif beats:
            story_block = ('── 今天要演的分拍 ──\n'
                           + '\n'.join(f"{b.get('拍')}. [{b.get('场')}] {b.get('发生')}"
                                       for b in beats[:6] if isinstance(b, dict))
                           + '\n\n')
        people = '、'.join(ctx.people[:12]) or '（还没有人）'

        prompt = f"""你们三位是这本书的**导演、小说作家、剧作者**，正在开**编剧室会审**。
议题只有一个：**为了让接下来这一段戏演得下去，需要补哪些小设定？**

── 世界层（作者写的总体设定，**你们不能改**）──
{canon}

── 主线层（作者写的走向，**你们不能改**）──
{arc}

── 已经有的小设定 ──
{have}

{story_block}── 前情提要 ──
{ctx.recap(800)}

── 在场的人 ──
{people}

── 你们这一行该守的手艺 ──
{craft}

**规矩（违反的条目会被程序当场丢掉，写之前先看清楚）：**
1. **只能补「场景层」和「细节层」** —— 也就是：某个地点上具体的东西
   （器物、门轴、灯、桌上的账本）、某条具体的规矩或习俗、某个人自己的小习惯。
2. **每一场戏都应该由这些具体的东西推动**。不要写"这座城很繁华"这种背景 ——
   那是世界层，作者已经写过了。
3. **每条都必须有作用范围**：「场合」写它在**哪儿**用得上（地点名），
   或者「生效时机」写它在**第几天**用得上，或者「影响谁」写它牵到谁。
   **三样都空 = 等于改总体设定 → 会被丢掉。**
4. **不要改世界层和主线层**：不许新增势力、不许改历史、不许改人物身份、
   不许推进大纲。你们补的是"能演的东西"，不是"世界的规矩"。
5. **没有需要就返回空数组** —— 作者的设定够用的时候，硬编设定比不编更坏。
6. 一次最多 {self.MAX_ITEMS} 条，**每条内容 ≤ 40 字**（写长了会被丢掉）。

只输出 JSON，不要围栏、不要解释：
{{"讨论": "一句话：你们三人的结论",
  "新增设定": [
    {{"层": "细节", "名称": "缺角的紫砂壶", "内容": "谁都不许动它，掌柜自己也不用",
      "场合": "地点名", "生效时机": "", "影响谁": ["人名"], "为什么": "一句话"}}
  ]}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_settings', want=dict,
                        max_tokens=CFG.i('CREW_SETTINGS_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给出结论')

        raw_items = data.get('新增设定') or data.get('设定') or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        talk = ' '.join(str(data.get('讨论') or '').split())[:80]

        # 「已经有的」= 设定集里编进索引的 + 前几天收下的 —— 重复的当场拒
        # （不然界面上会写"新增 2 条"，其中一条只是把作者写过的话又说了一遍）。
        # [EN] "Already existing" = indexed in the settings collection + accepted in previous days -- reject
        # [EN] duplicates on the spot
        # [EN] (otherwise the UI would say "2 new entries added", one of which is just the author's words
        # [EN] repeated).
        existing = set()
        try:
            existing |= {(i.layer, i.name)
                         for i in (getattr(ctx.world, 'layer_index', None) or [])}
            existing |= {(i.layer, i.name)
                         for i in (getattr(ctx.world, 'local_settings', None) or [])
                         if isinstance(i, L.SettingItem)}
        except Exception:                                        # noqa: BLE001
            pass
        accepted, rejected = L.admit_new(raw_items, day=int(ctx.day or 1),
                                         existing=existing)
        if accepted:
            L.add_local(ctx.world, accepted)
        # 拒收原因拼成一行（给人看；也进 `data` 给验证脚本）
        # [EN] Rejection reasons joined into one line (for people to read; also put into `data` for the
        # [EN] validation script).
        rejects = [f'{it.name}（{why}）' for it, why in rejected]

        if not accepted and not rejected:
            # ★ 这是**合格的结论**，不是"没出活"：三人都认为现有设定够用。
            # [EN] ★ This is a **valid conclusion**, not "no output": all three believe the existing settings are
            # [EN] sufficient.
            return CrewNote(role=self.key, ok=True,
                            title='这次不用补（现有设定够用）',
                            body=talk or '（三人都认为不必新增局部设定）',
                            data={'设定': [], '拒收': [], '讨论': talk})

        body_lines = [f'· 新增「{L.layer_name(i.layer)}」{i.name}：{i.text}'
                      f'（{i.scope_line()}）' for i in accepted]
        body_lines += [f'· 拒收 {r}' for r in rejects]
        title = (f'新增 {len(accepted)} 条'
                 + (f' · 拒收 {len(rejected)} 条' if rejected else ''))
        return CrewNote(role=self.key, ok=True, title=title,
                        body='\n'.join(body_lines),
                        data={'设定': [i.to_dict() for i in accepted],
                              '拒收': rejects, '讨论': talk,
                              '条数': len(accepted)})


# ══════════════════════════════════════════════════════════════════════
#  复盘 · 造型 · 声音 · 语言审校（2026-10-07 补的四位）
# [EN] Review · Styling · Voice · Language proofreading (four more added 2026-10-07)
# ══════════════════════════════════════════════════════════════════════
class Reviewer(CrewMember):
    """**复盘**：收工时回答"今天这一段到底怎么样、明天该怎么改"。

    用户 2026-10-07：「在手动停止或者一天落盘之后，有一个今日总结
    （就是你提到的导演 小说作者和剧作家讨论回顾的结论 包括剧情总结
      存在的问题 后续修改意见等）」

    为什么这件事以前没人做：场记查的是**连戏错**（时间/物件/称呼对不上），
    宣发写的是**卖点**，导演验算的是**剧本立不立得住** —— 三样都不回答
    "昨天这一天，作为一章小说，好不好、差在哪、怎么补"。

    它的产出是**三方复盘的结论**（导演看结构、作者看文气、剧作者看可拍性），
    三合一发一次请求：拆成三次只是把同一段话说三遍，白花两次调用。

    ⚠ **它只报不改**（除了 `需要重演` 那面旗，那面旗由 `sim/loop` 决定要不要用）。
      自动改当天的戏风险太大 —— 那是作者的稿子。见 `DIRECTOR_ROLLBACK_MAX`
      与 `DAY_REVIEW_REPLAY` 两道闸。
    
        English:
    **Retrospective**: at wrap-up, answers "how was today's segment really, and what should be
    changed tomorrow".
        User 2026-10-07: "After a manual stop or a day's landing to disk, there is a today summary
        (that is, the conclusion of the retrospective discussion by the director, novel author and playwright you mentioned, including a plot summary,
          existing problems, follow-up revision suggestions, etc.)"
        Why nobody did this before: the script supervisor checks for **continuity errors** (time/prop/address mismatches),
        the publicity writer writes the **selling points**, the director verifies whether **the script holds up** -- none of the three answers
        "yesterday, as a chapter of a novel, was it good, where was it lacking, how to patch it".
        Its output is **the conclusion of a three-way retrospective** (director looks at structure, author looks at prose flow, playwright looks at filmability),
        three-in-one sends one request: splitting into three just says the same paragraph three times, wasting two calls.
        ⚠ **It only reports, does not change** (except the `需要重演` flag, which `sim/loop` decides whether to use).
          Automatically changing the day's scenes is too risky -- that is the author's draft. See `DIRECTOR_ROLLBACK_MAX`
          and `DAY_REVIEW_REPLAY`, two gates.
    """

    key = 'reviewer'

    async def work(self, ctx: SetCtx, *, lines: list[str] | None = None,
                   script: str = '') -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        body_txt = str(script or '').strip() or '\n'.join(
            str(x) for x in (lines or []) if str(x).strip())
        if not body_txt.strip():
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='今天没有可复盘的正文')
        prompt = f"""你是这部剧的**复盘会**，三个人一起说话：导演看结构与节奏、
小说作家看文气与人物、剧作者看"这一段拍得出来吗"。请给出**今天的总结**。

── 这本书 ──
{ctx.genre()[0]} · {ctx.world_brief(400)}

── 手艺（好坏的标准）──
{craft}

── 导演手里的大纲（现在走到哪儿了）──
{str(getattr(ctx.world, 'outline_note', '') or '（还没报过大纲）')}

── 今天推出了什么 ──
{ctx.recap(900) or '（第一天）'}

── 今天的正文 ──
{body_txt[:2600]}

要求：
1. **总结**：2~3 句，说清今天这一段**实际推进了什么**（不要复述情节细节）。
2. **存在的问题**：0~3 条，**必须指到具体的人名或具体的句子**。
   真没问题就给空数组 —— **不要为了凑数编问题**。
3. **修改意见**：0~3 条，每条写清「改哪里 —— 怎么改」。同样要具体。
{REFLECT_INSTRUCTION}
4. **需要重演**：只有当问题严重到"这一天作为一章立不住"时才给 true。
   一般的瑕疵、可以往后补的伏笔，都给 false。
5. 只输出 JSON，不要 ``` 围栏：

{{"总结": "…", "问题": ["…"], "修改意见": ["…"], "需要重演": false}}"""
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        purpose='crew_review', want=dict,
                        max_tokens=CFG.i('CREW_REVIEW_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给出复盘结论')

        def _list_of(name: str, cap: int = 4) -> list[str]:
            v = data.get(name) or data.get(name.replace(' ', '')) or []
            if isinstance(v, str):
                v = [v]
            out: list[str] = []
            for x in v if isinstance(v, (list, tuple)) else []:
                s = str(x or '').strip()
                if s:
                    out.append(s[:120])
            return out[:cap]

        summary = str(data.get('总结') or data.get('剧情总结') or '').strip()
        problems = _list_of('问题')
        advice = _list_of('修改意见')
        replay = bool(data.get('需要重演'))
        if not (summary or problems or advice):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='复盘结论是空的')
        md: list[str] = []
        if summary:
            md += [summary, '']
        if problems:
            md += ['**存在的问题**', ''] + [f'- {x}' for x in problems] + ['']
        if advice:
            md += ['**后续修改意见**', ''] + [f'- {x}' for x in advice] + ['']
        if replay:
            md += ['> ⚠ 复盘认为这一天作为一章站不住，建议回档重排。', '']
        title = (f'{summary[:26]}…' if len(summary) > 26
                 else summary) or '今日复盘'
        if problems:
            title += f'　（{len(problems)} 个问题）'
        return CrewNote(role=self.key, ok=True, title=title,
                        body='\n'.join(md).strip(),
                        data={'总结': summary, '问题': problems,
                              '修改意见': advice, '需要重演': replay})


class Stylist(CrewMember):
    """**造型**：人物**身上**的东西 —— 衣着、随身物、仪态。

    为什么道具与美术都盖不住它：道具管的是**场景里的物件**（茶壶、更鼓），
    美术管的是**画面怎么画**（色调、笔法）。而"这个人身上带着什么、
    穿戴成什么样、站着什么姿态"是**长在人身上**的 —— 两边都不认，
    于是同一件旧布衫在三天里可以有三种写法，出图时人一天一个样。

    产出两处用：落盘 `造型表.md`；进 `image_gen` 的提示词（`image_prefix`）。
    
        English:
    **Styling**: the things **on a character's body** -- clothing, carried items, bearing.
        Why neither props nor art can cover it: props manage **objects in the scene** (teapot, night watch drum),
        art manages **how the picture is drawn** (color tone, brushwork). But "what this person carries on them,
        how they are dressed, what posture they stand in" is **grown onto the person** -- neither side claims it,
        so the same old cloth shirt can be written three ways in three days, and the person looks different each day at image generation.
        Output used in two places: landed to disk as `造型表.md`; and into the `image_gen` prompt (`image_prefix`).
    """

    key = 'stylist'

    async def work(self, ctx: SetCtx, *, brief: str = '') -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        who = '、'.join(ctx.people) or '（还没定人物）'
        art_block = (f'── 美术定的调子（造型要合它）──\n{brief}\n\n'
                     if str(brief or '').strip() else '')
        prompt = f"""你是一部剧的**造型师**。请给在场的每个人定**身上**的东西。

── 这本书 ──
{ctx.scene_line()}
{ctx.world_brief(600)}

{art_block}── 在场的人 ──
{who}

要求：
1. 给**每个人**三条：**穿着**（具体到什么料子/颜色/新旧）、
   **随身物**（他身上带着的、可以反复出现的 1~2 样）、
   **仪态**（站着坐着什么习惯动作）。
2. 每样都要**具体可画**（"洗得发白的靛布短褂"好过"朴素的衣服"）。
3. 不要写剧情、不要编新人物、不要写心情。
4. 只输出 JSON：

{{"造型": [{{"人名": "…", "穿着": "…", "随身物": "…", "仪态": "…"}}],
  "基调": "一句话"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_stylist', want=dict,
                        max_tokens=CFG.i('CREW_STYLIST_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给造型表')
        rows: list[dict] = []
        for x in (data.get('造型') or [])[:12]:
            if not isinstance(x, dict):
                continue
            nm = str(x.get('人名') or x.get('姓名') or '').strip()
            if not nm:
                continue
            rows.append({
                '人名': nm[:16],
                '穿着': str(x.get('穿着') or '').strip()[:40],
                '随身物': str(x.get('随身物') or '').strip()[:40],
                '仪态': str(x.get('仪态') or '').strip()[:40]})
        if not rows:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='造型表是空的')
        body = '\n'.join(
            f"- {r['人名']}：{r['穿着']}｜随身 {r['随身物']}｜{r['仪态']}"
            for r in rows)
        return CrewNote(role=self.key, ok=True,
                        title=f'{len(rows)} 位造型',
                        body=body, data={'造型': rows,
                                         '基调': str(data.get('基调') or '')[:60]})


class Sound(CrewMember):
    """**声音**：这一场**听得见**什么 —— 环境音、静默、声音的转折。

    为什么值得有：小说里"声音"是最省字的氛围手段，而程序以前只写光与物
    （道具单、美术指导全是看的）。"今天有没有一声该响而没响的"
    这类东西，一写出来整场戏的密度就不一样。

    产出落盘 `声音设计.md`，并按天进场景的环境句池（`scene_builder.observe_note`）。
    
        English:
    **Sound**: what can be **heard** in this scene -- ambient sound, silence, turns in the sound.
        Why it is worth having: in a novel "sound" is the most word-economical means of atmosphere, and the program previously only wrote light and objects
        (the prop list and art direction are all visual). Things like "is there a sound today that should have sounded but did not" --
        once written out, the density of the whole scene is different.
        Output lands to disk as `声音设计.md`, and by day enters the scene's ambient sentence pool (`scene_builder.observe_note`).
    """

    key = 'sound'

    async def work(self, ctx: SetCtx, *, beats: list[dict] | None = None) -> CrewNote:
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        beat_txt = '\n'.join(
            f"- [{b.get('场', '')}] {b.get('发生', '')}"
            for b in (beats or [])[:6]) or '（还没分拍 —— 按场景本身猜）'
        prompt = f"""你是一部剧的**声音设计**。请定这一场**听得见**的东西。

── 场景 ──
{ctx.scene_line()}

── 手艺（声音怎么承住戏）──
{craft}

── 今天要拍的几件事 ──
{beat_txt}

要求：
1. 一条**底噪**（从头到尾都在的那个声音）。
2. 2~3 个**可用的事件声**（具体到"哪一下"：不是"人声嘈杂"，是
   "柜上的算盘被谁碰了一下"）。
3. 最多一条**静默** —— 写"**听见了什么没有**"这个**事实**
   （✅「门外没有脚步声」/「火钵半天没响」），
   **不许**写"该响的 X 没有响"这种**替读者解释**的句子
   （❌「该响的敲门声没有响」）。理由：这三样会**原样进正文**当环境句，
   一写"该响的…没响"，读者立刻从场面里退出来、站到作者位子上 ——
   《雪国》那一轮就是这么被评委抓住的（"叙述者在替读者点题"）。
   没有就给空字符串。
4. 每样一句话，**不要写剧情**、不要编新人物。
5. ★★★ **三样别都写同一件东西**：底噪 / 事件声 / 静默要挑**不同的来源**。
   实测（《雪国》一轮）：底噪写"炭火微微"、事件声写"灯芯炸响"、静默写
   "火钵里炭半天没塌" —— 三句都在写火，读者读到第三句就腻了
   （评委原话：「三处都在写火，意象重复」）。
6. 只输出 JSON：

{{"底噪": "…", "事件声": ["…"], "静默": "…"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_sound', want=dict,
                        max_tokens=CFG.i('CREW_SOUND_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给声音设计')
        bed = str(data.get('底噪') or '').strip()[:50]
        ev = [str(x).strip()[:50] for x in (data.get('事件声') or [])
              if str(x).strip()][:4]
        quiet = str(data.get('静默') or '').strip()[:50]
        if not (bed or ev or quiet):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='声音设计是空的')
        md: list[str] = []
        if bed:
            md.append(f'**底噪**　{bed}')
        if ev:
            md += ['', '**事件声**'] + [f'- {x}' for x in ev]
        if quiet:
            md += ['', f'**静默**　{quiet}']
        title = bed or (ev[0] if ev else '声音设计')
        return CrewNote(role=self.key, ok=True,
                        title=f'底噪：{bed}' if bed else title,
                        body='\n'.join(md).strip(),
                        data={'底噪': bed, '事件声': ev, '静默': quiet})


class Polisher(CrewMember):
    """**语言审校**：读当天样章，点名哪几句 AI 味重、该怎么改。

    它和「去 AI 库」（`style/deai.py`）的分工要想清楚，别做成两件重复的事：

    | | 去 AI 库 | 语言审校（本职位） |
    |---|---|---|
    | 查什么 | 词与句式（**确定的**） | 句子读起来对不对（**要判断的**） |
    | 成本 | 零（词表比对） | 每天一次 cheap 调用 |
    | 覆盖 | **每一段产出**都过 | 只查当天的样章 |

    也就是说：库负责"每次都查"，审校负责"每天深查一遍、并给出改法"。
    库能命中"首先"，但"这句话绕了三个弯"只有读过才知道。
    
        English:
    **Language review**: read the day's sample chapter, point out which sentences are heavily
    AI-flavored and how to fix them.
        Its division of labor with the "de-AI library" (`style/deai.py`) must be thought through clearly; don't make them two duplicate things:
        | | de-AI library | Language review (this position) |
        |---|---|---|
        | What it checks | Words and sentence patterns (**definite**) | Whether sentences read correctly (**requires judgment**) |
        | Cost | Zero (wordlist comparison) | One cheap call per day |
        | Coverage | **Every output** passes through | Only the day's sample chapter |
        In other words: the library handles "check every time", the review handles "deep-check once a day and give fix suggestions".
        The library can catch "firstly", but only reading it reveals "this sentence takes three detours".
    """

    key = 'polisher'

    async def work(self, ctx: SetCtx, *, story: str = '') -> CrewNote:
        text = str(story or '').strip()
        if not text.strip():
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='今天没有可查的稿子')
        from style import deai
        # ★ 先把**机器能确定的那一半**做掉：库里命中的词/句式，逐条摆出来。
        #   这一步零成本，而且给了审校一个"起手式"（它不用自己去找套话词）。
        # [EN] ★ First do **the half the machine can determine**: words/sentence patterns hit in the library,
        # [EN] listed one by one.
        # [EN] This step is zero-cost and gives the proofreader a "starting move" (it doesn't have to hunt for
        # [EN] cliches itself).
        res = deai.audit_text(text, who='样章')
        hit_lines = ''
        if res.hits:
            hit_lines = '\n'.join(
                f'- [{h.level}] {h.kind}：{h.what}' for h in res.hits[:16])
        else:
            hit_lines = '（词表这一层没有命中）'
        # ★ 思维链骨架（2026-10-07 第七轮）：审校的活是"读完再判"，而它最容易
        #   变成"扫一眼找几个套话词"。骨架按"这句像不像这个人说的 → 是绕是空
        #   还是在解释 → 改法只给方向"逼它过一遍，答案压进 `核查`。
        # [EN] ★ Chain-of-thought skeleton (2026-10-07, seventh round): the proofreader's job is to "read fully
        # [EN] then judge", and it most easily
        # [EN] becomes "scan for a few boilerplate phrases". The skeleton follows "does this line sound like
        # [EN] this person said it → is it evasive or hollow
        # [EN] or still explaining → the fix only gives direction" and forces it through a pass, squeezing the
        # [EN] answer into `核查`.
        _cot = cognition_block(self.key)
        cot_block = f'\n{_cot}\n' if _cot else ''
        # ★ 这一位**不走 `craft_block`**（审校读的是稿子，不读手艺条目）——
        #   所以它的系统提示词要在这里自己接一次，否则"改了它不听话"。
        # [EN] ★ This one **does not go through `craft_block`** (review reads the script, not the craft
        # [EN] entries) ——
        # [EN] so its system prompt has to be wired in here separately, otherwise "you edited it but it won't
        # [EN] obey".
        _head = ''
        try:
            from crew import catalog as _CAT
            _head = _CAT.prompt_block(self.key)
        except Exception:                                        # noqa: BLE001
            _head = ''
        head_block = f'{_head}\n\n' if _head else ''
        prompt = f"""{head_block}你是这部小说的**语言审校**。请读下面这段稿子，指出**两类**问题：
**① AI 味重的地方**；**② 语域不像自然标准普通话的地方**（夹文言词、半文半白、念稿腔 / 左右对称的对仗漂亮话）。

── 机器已经查出来的（词与句式，供你参考，**不必重复它们**）──
{hit_lines}

── 稿子 ──
{text[:2400]}
{cot_block}
要求：
1. 找出 **0~4 处**问题，分两类：
   - **AI 味**：句子绕、空、解释腔、情绪直说，或不像这个人物会说的话；
   - **语域违规**：夹了文言词（之乎者也、"此乃""日取夜禁"）、半文半白混写、
     或念稿腔 / 左右对称的对仗漂亮话（真人说话不这么齐）；
   ⚠ 人物可以有口癖、有来历，但**口吻必须是现代人**（哪怕演古人也用现代人能脱口而出的话）。
2. 每条写成：先**引出原句关键片段**（不超过 15 字，原文里找得到），
   再写**问题类型**（"AI味" 或 "语域"），然后写**怎么改**（一句话方向），
   最后给一句**改写**（用自然标准普通话，短、碎、带毛边，不文绉绉）。
3. **真读不出问题就给空数组** —— 不要为了凑数硬找。
4. 只输出 JSON：

{{{think_schema_of(self.key)}"问题": [{{"原句": "…", "类型": "AI味|语域", "怎么改": "…", "改写": "…"}}],
  "总评": "一句话"}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_polish', want=dict,
                        max_tokens=CFG.i('CREW_POLISH_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给审校结论')
        rows: list[dict] = []
        for x in (data.get('问题') or [])[:6]:
            if isinstance(x, str):
                x = {'原句': x, '怎么改': ''}
            if not isinstance(x, dict):
                continue
            q = str(x.get('原句') or x.get('句子') or '').strip()
            typ = str(x.get('类型') or x.get('问题类型') or '').strip()
            a = str(x.get('怎么改') or x.get('建议') or '').strip()
            rew = str(x.get('改写') or x.get('改后') or '').strip()
            if q or a or rew:
                rows.append({'原句': q[:40], '类型': typ[:8],
                             '怎么改': a[:80], '改写': rew[:80]})
        summary = str(data.get('总评') or '').strip()[:120]
        # ★ 思维链（2026-10-07 第七轮）：他**读下来最要紧的判断**（`核查`）。
        # [EN] ★ Chain of thought (2026-10-07, seventh round): his **most important judgment after reading it**
        # [EN] (`核查`).
        check = str(data.get('核查') or '').strip()[:200]
        # 机器那一层的命中也算进 body（否则"审校没看出问题"会掩盖"库命中了"）
        # [EN] Hits at the machine layer also count into body (otherwise "review found no problem" would mask
        # [EN] "the library hit")
        md: list[str] = []
        if summary:
            md += [summary, '']
        if rows:
            md += ['**AI 味 / 语域问题**', '']
            for r in rows:
                tag = f'（{r["类型"]}）' if r.get('类型') else ''
                md += [f'- 原句「{r["原句"]}」{tag}',
                       f'  改：{r["怎么改"]}',
                       f'  改写为：{r["改写"]}']
            md.append('')
        if res.hits:
            md += [f'**词表命中 {len(res.hits)} 处**（去 AI 库查出来的，'
                   f'硬禁 {len(res.hard)} / 提醒 {len(res.soft)}）', '']
            md += [f'- [{h.level}] {h.kind}：{h.what}' for h in res.hits[:20]]
        if not md:
            return CrewNote(role=self.key, ok=True, title='这一稿没有 AI 味',
                            body='> 词表没命中，读下来也没发现机器腔。',
                            data={'核查': check})
        title = (f'{len(rows)} 处 AI 味' if rows
                 else f'词表命中 {len(res.hits)} 处')
        return CrewNote(role=self.key, ok=True, title=title,
                        body='\n'.join(md).strip(),
                        data={'问题': rows, '总评': summary, '核查': check,
                              # ⚠ 这个键是给 `studio._is_key_note` 读的
                              #   （`CREW_SCREEN=key` 时靠它判断"要不要上屏"）——
                              #   别只放 `问题` 那个列表，键名对不上就等于没上屏。
                              # [EN] ⚠ This key is read by `studio._is_key_note`
                              # [EN] (when `CREW_SCREEN=key`, it's used to decide "whether to put it on screen") ——
                              # [EN] Don't only put the `问题` list; if the key name doesn't match, it's as if it never went on screen.
                              '问题数': len(rows), '词表命中': len(res.hits)})


class ScriptDoctor(CrewMember):
    """**剧本审读**：上屏之前，把新生成的东西放到已经出现的话里过一遍。

    用户 2026-10-08 点名要的就是这一个（原话见 `crew/review.py` 的模块头）：
    「你看是否有独立的Agent 而不是导演在盯着演员说的每一句话 **没有就做一个**
      在演员真的说出来之前，把新生成的话放到已经出现的话里过一遍，看是否通顺」。

    ★★ **它和演员自己的"台词自省"（`sim.loop._self_review`）不是一回事**：
      · `_self_review` 是**演员审自己**（"我这句话像不像人话"），只看这一句；
      · 本职位是**别人审**（一个独立的读者），而且手上拿着**已经上屏的全部历史**
        —— 所以它能看出演员自己看不见的东西：这句**跟上面接不上**、
        这个人**不会这么称呼**、这一批人**各说各的**（说的都不个人化）。
      用户说的"不是导演盯着演员说的每一句话"就是要这个**独立性**。

    ★ **两条输入，缺一不可**（对应"放到已经出现的话里过一遍"）：
      · `history` —— 台账里**真的上屏了**的那一份（`crew/review.ScriptLog`）；
      · `items`   —— 这一拍新生成、**还没放出来**的那几条（带序号）。
      没有历史就只有"这一句通不通"，那正是演员自省已经在做的；
      有了历史才判得出"接不接上文 / 是不是一个主题"。

    ⚠ **产出不上中栏**：它是读稿意见，不是故事（用户的中栏白名单里没有它）。
      落点是台账（`审读台账.jsonl`）与 `剧本审读.md`，加一行日志。
    
        English:
    **Script review**: before going on screen, run the newly generated content through the lines
    that have already appeared.
        This is exactly what the user requested on 2026-10-08 (original words in the module header of `crew/review.py`):
        "See whether there's an independent Agent instead of the director watching every line the actors say **if not, make one**
          before the actor actually says it, run the newly generated lines through the lines already spoken, to see whether they flow".
        ★★ **It is not the same as the actor's own "line self-review" (`sim.loop._self_review`)**:
          · `_self_review` is **the actor reviewing itself** ("does my line sound human"), looking only at this one line;
          · This position is **someone else reviewing** (an independent reader), and it holds **the entire on-screen history**
            —— so it can see things the actor cannot see itself: this line **doesn't connect with the above**、
            this person **wouldn't address it this way**、this batch of people **each speaks their own way** (none is personalized).
          What the user meant by "not the director watching every line the actors say" is exactly this **independence**.
        ★ **Two inputs, neither can be missing** (corresponding to "run through the lines that have already appeared"):
          · `history` —— the copy in the ledger that **actually went on screen** (`crew/review.ScriptLog`);
          · `items`   —— the lines newly generated in this beat、**not yet released** (with indices).
          Without history there is only "does this line flow", which is exactly what the actor self-review already does;
          With history one can judge "does it connect to the preceding text / is it one theme".
        ⚠ **Output does not go to the center column**: it is reading feedback, not a story (it is not in the user's center-column whitelist).
    """

    key = 'script_doctor'

    async def work(self, ctx: SetCtx, *, items: list[dict] | None = None,
                   history: list[str] | None = None) -> CrewNote:
        if not CFG.b('SCRIPT_REVIEW'):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='剧本审读已关闭（SCRIPT_REVIEW=false）')
        rows = list(items or [])
        if not rows:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='这一拍没有要审的东西')
        genre, structure = ctx.genre()
        craft = craft_block(self.key, genre, structure)
        _cot = cognition_block(self.key)
        cot_block = f'\n{_cot}\n' if _cot else ''
        # 历史太长会挤掉正文；台账那一侧本来就只留最近几十条
        # [EN] Too much history squeezes out the main text; the ledger side only keeps the most recent few
        # [EN] dozen entries anyway
        hist = [str(x) for x in (history or []) if str(x).strip()][-40:]
        hist_txt = '\n'.join(hist) or '（这还是头一遭，前面没有出现过的话）'
        # 人物卡（判"像不像这个人 / 称呼对不对"的依据）
        # [EN] Character card (the basis for judging "does it sound like this person / is the form of address
        # [EN] correct")
        cast: list[str] = []
        for n in list(ctx.people or [])[:16]:
            ps = (getattr(ctx.world, 'people', {}) or {}).get(n)
            if ps is None:
                cast.append(n)
                continue
            bits = [n, str(getattr(ps, 'identity', '') or '')]
            tic = str(getattr(ps, 'catchphrase', '') or '')
            if tic:
                bits.append(f'口癖：{tic}')
            # ★★★ 2026-10-18：**红线也递进来**。它是判"越界"的唯一依据，
            #   而它原来只在演员自己的提示词里（`_persona_static_only`）——
            #   审读这份卡上没有，于是"叶子不许成句"这种越界它判不出来。
            # [EN] ★★★ 2026-10-18: **pass the red line in too**. It is the only basis for judging
            # [EN] "out of bounds", and it used to live only in the actor's own prompt -- so the
            # [EN] reviewer could not catch violations like "Yoko must not speak in full sentences".
            red = str(getattr(ps, 'redline', '') or '').strip()
            if red:
                bits.append(f'红线：{red}')
            cast.append(' · '.join(b for b in bits if b))
        # ★★★ 这本书的**铁律**（世界铁律 / 写法 / 禁忌词）—— 判"越界"的另一半依据。
        #   它一直在 `world.rules_text` 里（顶级规则），可审读的提示词从来没带过：
        #   于是"不许写明确的心理分析""时代禁忌词"这类，审读只能靠语感猜。
        # [EN] ★★★ The book's **iron rules** (world rules / style / taboo words) -- the other half
        # [EN] of the basis for "out of bounds". They were always in `world.rules_text` (top-level
        # [EN] rules) but the review prompt never carried them, so the reviewer could only guess.
        rules_txt = str(getattr(ctx.world, 'rules_text', '') or '').strip()
        rules_txt = rules_txt[:1200] if rules_txt else ''
        rules_blk = (f'\n── 这本书的铁律（**踩一条就是越界**）──\n{rules_txt}\n'
                     if rules_txt else '')
        # ★★★ 「可能是同一件事」的**候选**：由程序按字面挑（零成本），模型只判真假。
        #   为什么不给模型自己搜：它的输出预算 100–200 token，实测"通读 40 行找重复"是漏的；
        #   而"这几对里哪一对真是同一件事"它判得很准（这是理解，不是检索）。
        # [EN] ★★★ Candidates for "may be the same thing": the program picks them by surface form
        # [EN] (zero cost) and the model only rules true/false. Why not have the model search: its
        # [EN] output budget is 100-200 tokens and measured recall was poor; but "which of these
        # [EN] pairs is really the same thing" it judges well (that is understanding, not retrieval).
        try:
            from crew import review as _R
            pairs = _R.dup_candidates(rows, hist)
        except Exception as e:                                   # noqa: BLE001
            pairs = []
            _LOG.warning('挑重复候选失败（按没有候选继续审）：%r', e)
        if pairs:
            pairs_txt = '\n'.join(
                f"- 第 {p.get('序号')} 条 ↔ 「{str(p.get('像这句') or '')[:60]}」"
                f"（相似 {p.get('相似')}，{'同一个人' if p.get('同一个人') else '不同人'}，"
                f"{'同一批里' if p.get('同批') else '前面已上屏'}）"
                for p in pairs
            )
        else:
            pairs_txt = '（这一批没有挑出可疑的配对 —— 就别硬找重复）'
        new_txt = '\n'.join(
            f"{i}. 〔{r.get('类型', '')}"
            + (f"·{r.get('谁')}" if r.get('谁') else '')
            + (f" → {r.get('对')}" if r.get('对') else '')
            + f"〕{r.get('文本', '')}"
            for i, r in enumerate(rows, 1))
        prompt = f"""你是一部剧的**剧本审读**（读稿人）。你**不写戏、不演戏**，
只做一件事：判断**下面这几条还没放出去的内容**，放进**已经出现过的话**里，
是不是通顺、说得通、好不好看。你独立于导演与演员 —— 演员自己觉得没问题的话，
恰恰要靠你来看。

── 这部戏的规矩（你判断"什么算不对"的依据）──
{craft}

── 这是什么戏 ──
{ctx.scene_line()}
{chr(10).join(cast)}
{rules_blk}
── 已经出现过的话（按发生顺序，读者已经看过这些）──
{hist_txt}

── 这一批**还没放出去**的新内容（逐条给意见）──
{new_txt}

── 程序挑出的「可能是同一件事」的配对（它只筛字面，**判不判由你**）──
{pairs_txt}
{cot_block}
逐条看这八件事（**看不出来就说没问题，不要为凑数硬挑**）：
① **是不是人话** —— 读得通吗？有没有生造的词、半截话、看不懂的短语？
   （例：'目光顺着小臂滑到底 才收回 压在壶盖上' —— 这是描写视线的句子，
     不是一个人**做**的动作；'卷了'、'先给你留着' 这类上面没有着落的短语，
   读者会问"什么意思"。）
② **像不像这个人** —— 这话是他的身份、性格、口癖该说出来的吗？
   他会不会这么**称呼**对方？（例：跑堂把「客官慢用」说给**自家楼里的伙计**，
   就不对 —— 那不是他的客；口癖是用在**对的场合**上的。）
③ **接不接上文** —— 跟已经出现过的话接得上吗？有没有人**突然冒出来**、
   冒出来之后**什么都没做**？他说的这句是对**刚才那句**的回应吗？
④ **是不是一个主题** —— 这几条合起来在说**同一件事**吗？还是各说各的、
   散的？（一堆人各干各的、各说一句不相干的话 = 散。）
⑤ **跟场景搭不搭** —— 这话像是此刻这个地点、这个时辰会说的吗？
⑥ **像不像活人在说话**（★ 只查**一眼就能看出来的假**，别把正常的短句判掉）：
   · **句句都严丝合缝接上** —— 真人对话里大段是漏接的（听岔、只应一个「嗯」、
     顺着自己那半句往下说）。整批一条不漏地接住 = 两个人在念稿。
     ⚠ ★★★ **但反过来一样假**（2026-10-19 用户实证）：整场**没有一句**接住上一句，
     就是两个人在各说各的 —— 读者看到的直接是"这段说话没逻辑"。
     判法：**大部分要接，少数可以漏**；**连着三句以上没人接 = 散**，要判出来。
   · **有人在吼** —— 台词里出现"吼道""厉声""咆哮""尖声"就当**假**：
     激动可以压低声音、说得更快、忽然停下，不是把字放大。
   · **一句话一口气交代好几件事** —— 真人不这样，他们一次只说一件。
   · **一处停顿都没有** —— 全都说得又顺又平、一句到底 = 念稿。
⑦ ★★★ **是不是同一件事（重复）** —— 这条跟**已经上屏的**、或**同一批里的**另一条，
   是不是**同一件事换了层皮**？判这个**不看字面像不像，看意思**：
   · 同一个动作做第二遍：'端酒壶过来' → '一壶酒从门里推进来'；
   · 同一句自白换个说法：'我那年冬天没回去过' → '我那年冬天，人还在南边'；
   · 同一个姿态第三次：'眼盯他侧脸' → '眼没离他脸' → '盯他嘴'。
   ⚠ **不算重复**的（别误判）：问答（他问、她答）、追问（increasing 压力）、
     呼应（前面提过一次的东西后面真的用上了）、以及**同一件事的下一步**
     （端进来 → 放下 → 退出去，这是推进，不是重复）。
   ⚠ ★★★ **「回声」也不算重复**（2026-10-18 加）：同一个东西**隔了几句再带一笔**，
     如果它换了角度、换了主语、或者写出了"这件事留下的痕迹"，那是**时间感**，
     是真人小说控节奏的写法 —— 读者需要这一笔才觉得时间在走。
     ✅ 不算：「缸还在，案子没了。」「楼下的琴还在响，还是那一支。」「他这才觉出手上凉。」
     ❌ 算：「她抬眼看他。」→ 隔两句又来一遍「她抬眼，看他。」
     判法：**同一件事、同一个说法**才算重复；**同一个东西、另一种看法**是回声。
     ⚠ 别把"回声"改写成新动作 —— 那会把节奏改没，读起来变成一串事件。
   ⇒ 判"重复"了，就要在 `改成` 里给一句**换过的事**（做别的动作 / 说别的话），
     **不要**只把原句删短 —— 删短了读者看到的是"什么都没发生"。
⑧ ★★★ **有没有越界** —— 对照上面的**铁律**与每个人的**红线**：
   他说的话、做的事，是不是这个人**做不到 / 不该做**的？
   （例：红线上写着"她的声音只用来唤人、传话"，她却在门外成句地问人来不来；
     铁律写着"不许写明确的心里想"，正文里出现"她想：我要说吗"；
     禁忌词表里有的词出现了 —— 那是一条都不能有的。）
   ★ 还有一条最常被漏掉的越界：**时代 / 地点错置** ——
   这个场面里的器物、称呼、计时方式，是不是**这一套世界**里有的？
   （例：日本温泉旅馆的深夜出现"更鼓一声一声"；民国故事里出现"手机"。
     铁律里会写"意象要干净：雪、镜、火……"—— 不在那一套里的东西，读者一眼出戏。）
   ★ 标着 `aside`（心里话）的那几条，**必须是第一人称的心里话**：
   写成"某某抬手指向城楼，又回头看父亲脸色"是把**旁白**塞进了心里话
   （实测这一条最容易不遵守：给了 ✅/❌ 例子仍有 40%–74% 写错）。
   判法很简单：心里话读起来该像"我"在自言自语；出现"他/她 + 动作"就是写错了。
   ⇒ 判"越界"了，也在 `改成` 里给一句**这个人真会做/会说的**，
     **不要**整条判死了事（读者少看一条，比看一句不越界的差）。

**硬要求**：
- 每条都要看；**通过的也要出现在输出里**（`"过": true`），不要只报坏的。
- 判"不过"必须说清**为什么**，并且**必须填 `类别`**：
  `"重复"`（⑦那种）· `"越界"`（⑧那种）· `"其他"`（人话/接不上/主题/场景/念稿）。
  类别决定程序怎么处置：重复与越界**优先改写**，改不动重复的**直接放行**
  （删掉会让这一拍变成空白，那比重复更糟）。
- 能改就直接给一句**改成**（照原意改，别把话改成另一个人说的）。
  ⚠ `改成` 里**只写那句话本身**：不许加 `〔改动作〕`、`〔改成〕`、`（心里）`
  这类标签 —— 那会被原样印进正文（实测发生过）。
  只有**真的改不动**时才留空。
- **只挑你真的看出来的**问题；看不出来就让它过（你是把关的人，
  不是找茬的人 —— 把好句子拦下来比漏一句更糟）。

只输出 JSON：
{{{think_schema_of(self.key)}"裁决": [{{"序号": 1, "过": true, "类别": "其他", "问题": "", "改成": ""}}],
  "主题": "这一批合起来在说的一件什么事（一句话）"}}"""
        # ⚠⚠ 2026-11-01 **试过把「八件事」前移，又撤回来了** —— 记在这里，别有人再试一遍：
        #   它和 `agent/core.decide` 那个病例**看着一样、其实不一样**。
        #   `decide` 的尾部规则是"自足"的（只讲怎么写，不指代别处），所以整段
        #   前移没有任何副作用。而这里 ⑧ 写的是**"对照上面的铁律与每个人的红线"** ——
        #   一旦把八件事挪到最前，"上面"就变成了"下面"，红线（在 cast 里）和铁律
        #   （在 rules_blk 里）都在它之后。想让指代还对，就得把 cast 与铁律一起
        #   前移，而那会把「这是什么戏」这一节拆成两半。
        #   收益实测只有这项输入的 ~6%（`crew_script_doctor` 占全部输入 11.5%，
        #   命中率 8.3% → 估算 ≈ 60%），**不值这个风险**。
        #   ⇒ 判断"能不能前移"的标准不是"它稳不稳"，而是**"它有没有指代别处"**。
        # [EN] ⚠⚠ 2026-11-01 **Tried hoisting the eight-point checklist here and reverted it** --
        # [EN] written down so nobody tries again: it *looks* like the `agent/core.decide` case but
        # [EN] is not. `decide`'s tail rules are **self-contained** (they only say how to write, no
        # [EN] back-references), so hoisting them is free. Here item ⑧ says **"check against the iron
        # [EN] rules above and each person's red line"** -- once the checklist moves to the top,
        # [EN] "above" becomes "below" (red lines live in `cast`, iron rules in `rules_blk`, both
        # [EN] after it). To keep the reference valid you would have to hoist `cast` and the iron
        # [EN] rules too, which splits the "what play is this" section in half.
        # [EN] Measured gain is only ~6% of this item's input (`crew_script_doctor` is 11.5% of all
        # [EN] input, hit rate 8.3% → ~60%), **not worth the risk**.
        # [EN] ⇒ The test for "can it be hoisted" is not "is it stable" but **"does it point
        # [EN] somewhere else"**.
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_script_doctor', want=dict,
                        max_tokens=CFG.i('SCRIPT_REVIEW_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没拿到审读结论')
        verdicts = [x for x in (data.get('裁决') or []) if isinstance(x, dict)]
        bad = [x for x in verdicts if not REVIEW.is_pass(x)]
        theme = str(data.get('主题') or '').strip()
        n_ok = len(verdicts) - len(bad)
        if not verdicts:
            # ⚠ 一条裁决都没拿到 = **这一批都没审**，不许当成"全过"上报。
            # [EN] ⚠ Not a single verdict obtained = **this whole batch was not reviewed**; it must not be reported
            # [EN] as "all passed".
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='没拿到任何逐条裁决')
        title = (f'过 {n_ok} 条 · 有问题 {len(bad)} 条' if bad
                 else f'全过（{n_ok} 条）')
        body = (f'主题：{theme}\n' if theme else '')
        if bad:
            body += '\n'.join(
                f'{i}. 〔{_short(x)}〕{str(x.get("问题") or "")[:80]}'
                + (f' → 改：{x.get("改成")}' if str(x.get("改成") or '').strip()
                   else '')
                for i, x in enumerate(bad[:6], 1))
        return CrewNote(role=self.key, title=title, body=body,
                        data={'裁决': verdicts, '主题': theme,
                              '核查': str(data.get('核查') or '')[:200]})


def _short(row: dict) -> str:
    try:
        return f'#{int(row.get("序号"))}'
    except Exception:                                            # noqa: BLE001
        return '?'


# ══════════════════════════════════════════════════════════════════════
#  **自建职位**（2026-10-11，见 `crew/catalog.py`）
# [EN] **Self-defined position** (2026-10-11, see `crew/catalog.py`)
# ══════════════════════════════════════════════════════════════════════
class Generic(CrewMember):
    """作者在「剧组 Agents」里自建的那个职位。

    ★ 它和内置职位**最大的区别**：产出**不接程序里的任何东西**
      （`hooks` 为空）—— 它只落一份 md、在台账上留一句话。
      这是"自定义职位"的诚实边界：接了才叫接，没接就不假装接了。

    ★ 出工时机固定为 `day`（每天收工时出工一次），理由见
      `crew/catalog.CUSTOM_WHEN` —— 逐拍插一脚那一档要经过主循环的接线，
      自定义职位没有，给一个选了不生效的选项就是假按钮。

    ⚠ 它的提示词走 `craft_block`（那一处已经把这个职位的**系统提示词**
      接在最前面了），所以作者写的提示词一定进得去 ——
      不必在这里再拼一遍（两处各拼一份迟早对不上）。
    
        English:
    The position the author created themselves in "剧组 Agents".
        ★ **Its biggest difference** from built-in positions: its output **connects to nothing in the program**
          (`hooks` is empty) —— it only writes one md、and leaves one line in the ledger.
          This is the honest boundary of a "custom position": connected means connected, not connected means it doesn't pretend to be.
        ★ Work timing is fixed to `day` (works once per day at wrap-up), reason see
          `crew/catalog.CUSTOM_WHEN` —— the beat-by-beat insertion tier requires wiring into the main loop,
          custom positions don't have it; giving an option that doesn't take effect when chosen is a fake button.
        ⚠ Its prompt goes through `craft_block` (that place already attaches this position's **system prompt**
          at the very front), so the prompt the author writes definitely goes in ——
          no need to assemble it again here (two places each assembling one will eventually mismatch).
    """

    def __init__(self, key: str):
        self.key = str(key or '').strip()

    def _spec(self):
        try:
            from crew import catalog as _CAT
            return _CAT.get(self.key)
        except Exception:                                        # noqa: BLE001
            return None

    async def work(self, ctx: SetCtx, **kw) -> CrewNote:
        genre, structure = ctx.genre()
        head = craft_block(self.key, genre, structure)
        spec = self._spec()
        task = str(getattr(spec, 'usage', '') or '').strip() or '照你的系统提示词'
        who = str(getattr(spec, 'name', '') or self.key)
        tier = str(getattr(spec, 'tier', '') or 'cheap')
        if tier not in ('cheap', 'daily', 'front'):
            tier = 'cheap'
        lines = '\n'.join(str(x) for x in list(kw.get('lines') or [])[:80] if str(x))
        prompt = (
            f'{head}\n\n'
            f'── 这本书 ──\n{ctx.world_brief(400)}\n\n'
            f'── 今天 ──\n第 {ctx.day} 天 · {ctx.scene_line()}\n'
            + (f'{ctx.recap()[:400]}\n' if ctx.recap() else '')
            + (f'\n── 今天上屏的（供你做这一天的活）──\n{lines[:3000]}\n'
               if lines else '')
            + f'\n请以「{who}」的身份完成**今天**属于你的那件活（{task}），'
              f'写一段 **120~300 字**、直接给作者看的结论。'
              f'\n只输出这段结论本身：不要标题、不要 JSON、不要解释你在做什么。')
        rep = await ask(tier, [{'role': 'user', 'content': prompt}],
                        # ★ purpose 用**一个固定名字**（不是 `f'crew_{key}'`）：
                        #   ① MOCK 那边要靠字面量登记（`verify_mock` 扫的是字面量），
                        #      动态名字永远登记不上、演示模式下这个职位就哑着；
                        #   ② 按 Agent 拆账本来就靠 `set_ctx(agent=…)`（`Studio.call`
                        #      里设的），不必再让 purpose 也拆一遍。
                        # [EN] ★ purpose uses **one fixed name** (not `f'crew_{key}'`):
                        # [EN] ① The MOCK side must register it by literal (`verify_mock` scans literals),
                        # [EN] a dynamic name can never be registered, and in demo mode this position stays mute;
                        # [EN] ② Splitting accounting by Agent already relies on `set_ctx(agent=…)` (set in
                        # [EN] `Studio.call`), so purpose doesn't need to be split again.
                        purpose='crew_custom', want='text',
                        min_chars=8, max_tokens=1200, default='')
        if not rep.ok:
            return CrewNote(role=self.key, ok=False, title=who,
                            why='；'.join(rep.notes) or '没出活')
        text = str(rep.value or '').strip()
        if not text:
            return CrewNote(role=self.key, ok=False, title=who, why='产出是空的')
        return CrewNote(role=self.key, title=who, body=text)





#: 名册 key → 实现。**缺一个都不行**（见 `crew/studio.py` 的启动自查）。
# [EN] : roster key → implementation. **Missing even one is not allowed** (see the startup self-check
# [EN] in `crew/studio.py`).
class Storyboard(CrewMember):
    """**分镜师**：把定稿剧本的分拍拆成「镜头清单」。

    开源漫剧流程里「剧本→分镜」这一步：导演 / 演员在开演前先有
    "每一镜怎么拍"（景别 / 画面 / 台词 / 镜头运动），下游生图 / 视频才有统一参照。

    ⚠ 与剧作者（写"发生什么"）分工：分镜师写"怎么拍"。
    [EN] **Storyboard artist**: breaks the finalized beat script into a "shot list".
    [EN] The "script -> storyboard" step in the open-source comic-drama pipeline: before the show,
    [EN] the director / actors already have "how each shot is shot" (shot size / frame / line /
    [EN] camera move), so downstream image / video generation has a unified reference.
    """
    key = 'storyboard'

    async def work(self, ctx: SetCtx, *, beats: list[dict] | None = None,
                   story: str = '') -> CrewNote:
        beats = [b for b in (beats or []) if isinstance(b, dict)]
        if not beats:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='没有分拍可拆')
        # ★ 这一位也**不走 `craft_block`**（读的是分拍，不读手艺条目），
        #   所以它的系统提示词要在这里自己接一次 —— 与 Polisher 同一个口径。
        # [EN] ★ This one also **does not go through `craft_block`** (reads beats, not craft entries),
        # [EN] so its system prompt must be wired in here separately -- same convention as Polisher.
        _head = ''
        try:
            from crew import catalog as _CAT
            _head = _CAT.prompt_block(self.key)
        except Exception:                                        # noqa: BLE001
            _head = ''
        head_block = f'{_head}\n\n' if _head else ''
        bt = ''
        for i, b in enumerate(beats[:12], 1):
            bt += f"{b.get('拍') or i}. [{b.get('场') or '—'}] {b.get('发生') or ''}\n"
        prompt = f"""{head_block}你是本剧组的**分镜师**。下面是一天的分拍剧本，请把**每一拍拆成 1~3 个镜头**，
给导演和演员当"拍摄说明书"（景别 / 画面 / 台词 / 镜头运动）。

── 分拍 ──
{bt}

要求：
1. 每个镜头给：镜号（从 1 开始连续）、所属拍号、景别（远景 / 全景 / 中景 / 近景 / 特写 / 过肩）、
   画面描述（这一镜里谁在哪、在做什么、环境）、台词（这一镜里说的一句，没有就空串）、
   镜头运动（推 / 拉 / 摇 / 移 / 固定 / 跟，或空串）。
   ★ 每一镜**再给三样**（皮拉尔·亚历山德拉「意图 / 叙事点 / 收尾」那一套）：
     · `意图`：这一镜**为什么存在**（它要推进哪条线、给观众什么情绪）；
     · `叙事点`：这一镜想让观众**带走的那句话**（整部戏的主题落点）；
     · `收尾`：这一镜最后落下的那一下（一个动作 / 一句收口，给观众一个"喔"的按钮）。
2. 台词用**自然标准普通话**（不许文言词、不许半文半白、不许对仗漂亮话）。
3. 只输出 JSON：

{{{think_schema_of(self.key)}"分镜": [{{"镜": 1, "拍": 1, "景别": "中景", "画面": "…", "台词": "…", "镜头运动": "推",
  "意图": "…", "叙事点": "…", "收尾": "…"}}]}}"""
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_storyboard', want=dict,
                        max_tokens=CFG.i('CREW_STORYBOARD_TOKENS'))
        data = rep.value if isinstance(rep.value, dict) else None
        if not isinstance(data, dict):
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='；'.join(rep.notes) or '没给分镜')
        shots = data.get('分镜') or data.get('shots') or []
        shots = [dict(x) for x in shots if isinstance(x, dict)][:48]
        if not shots:
            return CrewNote(role=self.key, ok=True, title='这一稿不用分镜',
                            body='> 没有可拆的镜头。', data={'shots': []})
        md = [f'**分镜（{len(shots)} 镜）**', '']
        for s in shots:
            md.append(f"{s.get('镜') or '?'}.（拍{s.get('拍') or '?'}）"
                      f" 景别：{s.get('景别') or '—'}")
            if s.get('画面'):
                md.append(f"   画面：{s['画面']}")
            if s.get('台词'):
                md.append(f"   台词：{s['台词']}")
            if s.get('镜头运动'):
                md.append(f"   镜头运动：{s['镜头运动']}")
            if s.get('意图'):
                md.append(f"   意图：{s['意图']}")
            if s.get('叙事点'):
                md.append(f"   叙事点：{s['叙事点']}")
            if s.get('收尾'):
                md.append(f"   收尾：{s['收尾']}")
        # ── ③ 外部导演服务 PenShot：把分拍脚本再拆一份「导演分镜」当外部参考 ──
        #   ★ 内部分镜（`shots`）**一个字不动**——下游 VisualRef 等还指着它；
        #     PenShot 那只是一份**并列的参考**，进 `data['penshot_storyboard']` 与
        #     body 末尾多一段。失败 `degrade_ci` 记着，不抛、不拦。
        # [EN] ── ③ External director service PenShot: break the beat script once more into a
        # [EN] "director's storyboard" as an external reference ──
        # [EN] ★ The in-house storyboard (`shots`) is **untouched** -- downstream VisualRef
        # [EN] still points at it; PenShot's is just a **parallel reference**, into
        # [EN] `data['penshot_storyboard']` and one more section at the end of body. On failure
        # [EN] record `degrade_ci`, never raise, never block.
        degrade_ci = ''
        extra_ci = ''
        if _penshot_enabled_for(self.key):
            ci_text, ci_why = await _penshot_storyboard(ctx, script_text=bt)
            if ci_text:
                md.append('')
                md.append('**── 外部导演服务 PenShot 给的分镜（AI 分镜引擎 · 参考）──**')
                md.append(ci_text.strip())
                extra_ci = ci_text
            else:
                degrade_ci = ci_why
        return CrewNote(role=self.key, ok=True, title=f'{len(shots)} 镜',
                        body='\n'.join(md).strip(),
                        data={'shots': shots,
                              # ★ 外部导演服务 PenShot 这一份（空=没开或没用成）；
                              #   与内部分镜并列，给作者多一个视角，不覆盖 `shots`。
                              # [EN] ★ External director service PenShot's copy (empty = off or
                              # [EN] unused); parallel to the in-house storyboard, an extra
                              # [EN] perspective, never overrides `shots`.
                              'penshot_storyboard': extra_ci,
                              'penshot_degrade': degrade_ci})


class VisualRef(CrewMember):
    """**视觉参考图**：分镜定稿后，为出场人物 / 关键场景生成**一致性参考图**。

    开源漫剧流程里「分镜→视觉（角色 / 场景）」这一步：下游生图 / 视频
    拿这些参考图当统一参照，不用每次重新瞎画。接 `image_gen`。

    ⚠ **只在真能生图时生**（接口失败 / 开关关 = 只产出"参考清单"，
      不拦住这一天的戏）。见 `work` 里的 try/except。
    [EN] **Visual reference art**: after the storyboard is finalized, generate **consistent reference
    [EN] art** for the characters on stage / key scenes.
    [EN] The "storyboard -> visual (character / scene)" step in the open-source comic-drama pipeline:
    [EN] downstream image / video generation uses these references as a unified anchor instead of
    [EN] drawing from scratch each time. Hooks into `image_gen`.
    """
    key = 'visref'

    async def work(self, ctx: SetCtx, *, beats: list[dict] | None = None,
                   story: str = '', world=None) -> CrewNote:
        beats = [b for b in (beats or []) if isinstance(b, dict)]
        if not beats and not story:
            return CrewNote(role=self.key, ok=False, title=self.role.name,
                            why='没有分镜 / 剧本可参考')
        # 从分拍里抽"出场人物"与"场景"，各生成一张参考图
        # [EN] Pull "characters on stage" and "scenes" from the beats, generate one ref each
        people: list[str] = []
        scenes: list[str] = []
        for b in beats[:12]:
            for who in (b.get('出场') or []):
                if isinstance(who, str) and who not in people:
                    people.append(who)
            sc = str(b.get('场') or '').strip()
            if sc and sc not in scenes:
                scenes.append(sc)
        refs: list[dict] = []
        try:
            # ★ 真实接入 image_gen：`generate_portrait` 返回 `Image.Image`、
            #   `save_scene` 直接落盘并返回路径（都不是"返回路径的 generate"）。
            #   落盘到 `generated-images/视觉参考/`，让参考图真的产出来、下游能用。
            # [EN] ★ Real image_gen wiring: `generate_portrait` returns an `Image.Image`,
            # [EN] `save_scene` saves to disk and returns the path. Persist to
            # [EN] `generated-images/视觉参考/` so the refs are real and reusable.
            from image_gen import portrait as POR, scene as SCN
            import re
            from pathlib import Path as _P
            _out = _P(__file__).resolve().parent.parent / 'generated-images' / '视觉参考'
            _out.mkdir(parents=True, exist_ok=True)

            def _safe(s: str) -> str:
                return re.sub(r'[^\w\u4e00-\u9fff]+', '_', str(s)).strip('_')[:40] or 'x'

            for who in people[:6]:
                try:
                    img = POR.generate_portrait(str(who))
                    p = _out / f'人物_{_safe(who)}.png'
                    img.save(p)
                    refs.append({'种类': '人物', '名': who, '图': str(p)})
                except Exception:                            # noqa: BLE001
                    refs.append({'种类': '人物', '名': who, '图': ''})
            for sc in scenes[:6]:
                try:
                    p = _out / f'场景_{_safe(sc)}.png'
                    SCN.save_scene(str(p), str(sc))
                    refs.append({'种类': '场景', '名': sc, '图': str(p)})
                except Exception:                            # noqa: BLE001
                    refs.append({'种类': '场景', '名': sc, '图': ''})
        except Exception as e:                               # noqa: BLE001
            _LOG.warning('视觉参考图接口不可用（只产清单）：%r', e)
        md = ['**视觉参考（%d 项）**' % len(refs), '']
        for r in refs:
            tag = f" → {r['图']}" if r.get('图') else '（未生成）'
            md.append(f"- {r['种类']}：{r['名']}{tag}")
        return CrewNote(role=self.key, ok=True,
                        title=f'{len(refs)} 项参考',
                        body='\n'.join(md).strip(), data={'refs': refs})


MEMBERS: dict[str, CrewMember] = {
    'novelist': Novelist(),
    'screenwriter': Screenwriter(),
    'director': OnDuty('director'),
    'actor': OnDuty('actor'),
    'extra': ExtraCasting(),
    'continuity': Continuity(),
    # ★ 剧本审读（2026-10-08）：上屏之前的闸门 + 全程台账。
    # [EN] ★ Script review (2026-10-08): the gate before going on screen + a full-run ledger.
    'script_doctor': ScriptDoctor(),
    'props': Props(),
    'art': Art(),
    'publicity': Publicity(),
    'researcher': Researcher(),
    # ★ 排练（2026-10-07）：剧本定稿后、开演前把这一天**空走一遍**。
    #   它不是"又一个产出职位"—— 它的活是**替演员先走一遍**，
    #   产出只落 `排练记录.md` 与日志，**不进中栏**（见 `Rehearsal` 的说明）。
    # [EN] ★ Rehearsal (2026-10-07): after the script is finalized and before opening night, **walk the
    # [EN] whole day through empty**.
    # [EN] It is not "yet another output position" —— its job is to **walk through it once on behalf of the
    # [EN] actors**,
    # [EN] and its output only lands in `排练记录.md` and the log, **not in the center column** (see the notes
    # [EN] on `Rehearsal`).
    'rehearsal': Rehearsal(),
    'settings_room': SettingsRoom(),
    # ── 2026-10-07 补的四位（见 roster.py 里那段"补之前先问过一遍缺谁"）──
    # [EN] ── The four positions added on 2026-10-07 (see the passage in roster.py: "before adding, first
    # [EN] ask who's missing") ──
    'reviewer': Reviewer(),
    'stylist': Stylist(),
    'sound': Sound(),
    'polisher': Polisher(),
    # ★ 分镜师（P2, 2026-10-15）：剧本定稿后把分拍拆成镜头清单（开源漫剧「剧本→分镜」）。
    # [EN] ★ Storyboard (P2, 2026-10-15): after the script is finalized, break beats into a shot list.
    'storyboard': Storyboard(),
    # ★ 视觉参考图（P3, 2026-10-15）：分镜定稿后为人物/场景生一致性参考图（接 image_gen）。
    # [EN] ★ Visual reference (P3, 2026-10-15): after storyboard, generate consistent ref art (image_gen).
    'visref': VisualRef(),
}


def member(key: str) -> CrewMember:
    """按 key 取在位者。

    · 出厂职位 → `MEMBERS` 里那一位；
    · **自建职位**（作者在「剧组 Agents」里新建的）→ 现造一个 `Generic`；
    · 其余**认不出就抛** —— 与 `roster.role()` 同一条规矩。
    
        English:
    Fetch the incumbent by key.
        · Factory position → the one in `MEMBERS`;
        · **Custom position** (newly created by the author in "剧组 Agents") → construct a `Generic` on the spot;
        · Otherwise **throw if unrecognizable** —— same rule as `roster.role()`.
    """
    k = str(key or '').strip()
    m = MEMBERS.get(k)
    if m is not None:
        return m
    try:
        from crew import catalog as _CAT
        spec = _CAT.get(k)
    except Exception:                                            # noqa: BLE001
        spec = None
    if spec is not None and spec.is_custom:
        return Generic(k)
    raise KeyError(f'剧组里没有这个职位在位：{key!r}')


def _custom_keys() -> set[str]:
    """软件层里的自建职位（认不出来 = 空集，不影响出厂职位）。
        English:
    Custom positions in the software layer (unrecognizable = empty set, does not affect factory
    positions).
    """
    try:
        from crew import catalog as _CAT
        return {s.key for s in _CAT.effective() if s.is_custom}
    except Exception:                                            # noqa: BLE001
        return set()


def missing_members() -> list[str]:
    """名册里有、但没人到岗的职位（启动自查用）。空 = 一班人齐了。

    ⚠ 判据是**有效名册**（作者改过/新建的也算数）：拿出厂名册比的话，
      自建职位会被天天误报成"缺人"，而那句警告会把人练成不看警告。
    
        English:
    Positions that exist in the roster but have no one on duty (for startup self-check). Empty = a
    full shift is present.
        ⚠ The criterion is the **effective roster** (ones the author modified/created also count): if you compare against the factory roster,
          custom positions would be falsely reported as "missing staff" every day, and that warning would train people not to look at warnings.
    """
    known = set(MEMBERS) | _custom_keys()
    return [r.key for r in ROSTER.roles() if r.key not in known]
