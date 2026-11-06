# -*- coding: utf-8 -*-
"""**Agent 设置**：每个职位的属性（名字 · 简介 · 系统提示词 · 什么时候用）。

用户 2026-10-11
---------------
「我希望可以在合适的位置保存各个 Agent 的 system prompt，比如在一个专门的
 agents 文件夹，每一个 Agent 一个 md 文件保存自己的设置，文件名用 Agent 的
 名字命名（最好是英语），可以加一个 README.md 说明英语 Agent 和中文 Agent
 名字的对照。用户可以在这里编辑各个 Agent 的属性。除此之外，在每个项目的
 文件夹里，也有一个 agents，保存的是各个 Agent 在当前项目中的定制化部分。
 每个 Agent，软件默认系统设定加上项目相关设定一起才是每次运行时候的全部
 Agent 属性。」

所以这里有**三层**，别混（与 `crew/profile.py` 的"职位定义/行当手艺/项目档"
是同一套分层思想，但那一层管的是**手艺内容**，这里管的是**职位本身**）：

| 层 | 在哪 | 随书变吗 | 谁写 |
|---|---|---|---|
| **软件默认** | `<软件目录>/agents/<slug>.md` | 不变（跨书） | 首次运行自动播种，之后由作者改 |
| **项目定制** | `<项目>/agents/<slug>.md` | **每本都变** | 作者在「书斋 · 剧组 Agents」里改（或开卷那一步） |
| **有效属性** | 上面两层合并 | —— | 运行时算出来（`effective()`），**不落盘** |

★ **合并规矩**：项目层只写"与软件默认不同的那几项"（部分覆盖，不是整份替换）。
  这样作者升级软件、内置提示词改好了，没被覆盖的部分会跟着更新 ——
  整份替换会让"我改过一行"变成"我永远停留在旧版"。

⚠ **这是全程序第二个会写进项目文件夹的地方**（第一个是 `ingest/repair.py` 的
  回写引用文件夹）。所以护栏与那边同一套思路：
  · 只写 `<项目>/agents/` 这一个目录，文件名必须是 `slug.md`（认东西不认路径）；
  · 项目层的**内置职位**只允许覆盖，**不允许新建**（新建只在软件层做）；
  · 项目层不删软件层的文件；删项目层那份 = 回到软件默认那一条。

⚠ 别把"有效属性"缓存起来跨轮用：同一台机器上可能同时开着两本书，
  而 `role()` / `prompt_block()` 都是**不带 project 参数**的（它们在剧组里被
  调用了十几处，加参数要改十几处）。所以走 `bind_project()` 这个**模块级绑定**
  ——与 `crew/agents._CURRENT_WORLD` 同一套做法，装配时设一次。

English:
**Agent settings**: each position's attributes (name · description · system prompt · when to
use).
User 2026-10-11
---------------
"I hope the system prompt of each Agent can be saved in a suitable place, e.g. in a dedicated
 agents folder, where each Agent's settings are saved in its own md file, with the file named after the
 Agent's name (preferably English), and a README.md can be added to explain the mapping between English Agent names and Chinese Agent
 names. Users can edit each Agent's attributes here. Besides that, inside each project
 folder there's also an agents folder, storing each Agent's customized parts for the current project.
 For each Agent, only the software default system settings plus the project-related settings together make up the full
 Agent attributes for each run."
So there are **three layers** here, don't mix them up (same layered idea as `crew/profile.py`'s
"position definition / craft skill / project file",
but that layer governs **craft content**, while this one governs **the position itself**):
| Layer | Where | Changes per book | Who writes |
|---|---|---|---|
| **Software default** | `<software dir>/agents/<slug>.md` | No (cross-book) | auto-seeded on first run, then changed by the author |
| **Project customization** | `<project>/agents/<slug>.md` | **Changes per book** | the author edits in "Shuzhai · Crew Agents" (or in the opening step) |
| **Effective attributes** | the two layers above merged | —— | computed at runtime (`effective()`), **not persisted** |
★ **Merge rule**: the project layer only writes "the items that differ from the software
default" (partial override, not a whole-file replacement).
  This way, when the author upgrades the software and the built-in prompt improves, the parts that weren't overridden get updated along with it —
  a whole-file replacement would turn "I changed one line" into "I'm forever stuck on the old version".
⚠ **This is the second place in the whole program that writes into the project folder** (the
first is `ingest/repair.py`'s
  write-back of the reference folder). So the guardrails follow the same idea as there:
  · only write to the single directory `<project>/agents/`, and the filename must be `slug.md` (identify by content, not by path);
  · the project layer's **built-in positions** may only be overridden, **not created** (creation only happens in the software layer);
  · the project layer does not delete the software layer's files; deleting the project layer copy = reverting to the software default entry.
⚠ Don't cache the "effective attributes" across rounds: the same machine may have two books open
at once,
  and `role()` / `prompt_block()` are both **without a project parameter** (they're called in a dozen-plus places inside the crew; adding a parameter would mean changing a dozen-plus places). So go through `bind_project()`, this **module-level binding**
  — same approach as `crew/agents._CURRENT_WORLD`, set once at assembly time.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

import yaml

from crew import roster as ROSTER
from util.io import atomic_write_text

_LOG = logging.getLogger('nws.crew.catalog')

#: 软件级目录名（在程序根目录下）。
# [EN] : Software-level directory name (under the program root directory).
SOFT_DIRNAME = 'agents'
#: 项目级目录名（在项目文件夹下）。
# [EN] : Project-level directory name (under the project folder).
PROJ_DIRNAME = 'agents'
#: 对照表文件名。
# [EN] : Lookup table file name.
README_NAME = 'README.md'

#: 文件里写的字段（**ASCII 键**：md 是给人看的，但键要稳）。
# [EN] : The fields written in the file (**ASCII keys**: the md is for humans, but the keys must be
# [EN] stable).
FIELD_KEYS = ('key', 'name', 'name_en', 'intro', 'usage', 'when', 'tier',
              'feeds', 'builtin', 'order', 'model')

#: `merged_with()` 允许改的字段 = 上面这些 + 三个**派生**的。
#: ⚠ `slug` 必须在这里：它是**文件名**，作者在界面上改英文名时走的就是它。
#:   漏掉它的表现是"改名了但文件没改"（`save_soft` 按老 slug 写回去，
#:   旧文件也不删）—— 判据 A11 当场抓到。
# [EN] : The fields `merged_with()` is allowed to change = the ones above + three **derived** ones.
# [EN] : ⚠ `slug` must be here: it is the **file name**, and it is what the author goes through when
# [EN] changing the English name in the UI.
# [EN] : The symptom of omitting it is "the name changed but the file didn't" (`save_soft` writes back
# [EN] under the old slug,
# [EN] :   and the old file isn't deleted either) —— criterion A11 catches this on the spot.
#:
#: ★★★ `prompt` 必须在这里，**而且它偏偏不在 `FIELD_KEYS` 里** ——
#:   因为它不是 frontmatter 的键，是 md 的**正文**（见 `to_meta` 的说明）。
#:   把两者搞混的代价极大：`_apply()` 读盘时明明把 `prompt` 塞进了 `fields`，
#:   却在这里被 `merged_with` **静默过滤掉** ⇒ **盘上那份 md 的正文从来没生效过**：
#:     · 作者在「天机 · 剧组 Agents」里改系统提示词 → 存了 → 一点用没有；
#:     · 用记事本改 `agents/xxx.md` → 同样一点用没有；
#:     · 界面列表里显示的"提示词开头"还是**内存里那份默认的** ——
#:       于是看起来"改了没变"，而查起来两头都对（写盘成功了、内存那份也自洽）。
#:   ⇒ 这是"我改了它不听话"最典型的一种，也是 `tools/verify_actor_layers`
#:     的 A7 条与变异 `M20` 专门钉住的那件事。
# [EN] : ★★★ `prompt` must be here, **and it just so happens it is not in `FIELD_KEYS`** ——
# [EN] :   because it is not a frontmatter key, it is the md **body** (see the note on `to_meta`).
# [EN] : Confusing the two is extremely costly: when `_apply()` reads from disk it clearly stuffs
# [EN] `prompt` into `fields`,
# [EN] : yet here it gets **silently filtered out** by `merged_with` ⇒ **the body of that md on disk
# [EN] never took effect**:
# [EN] :     · The author edits the system prompt in "Tianji · Crew Agents" → saves → it does nothing;
# [EN] :     · Editing `agents/xxx.md` in Notepad → likewise does nothing;
# [EN] :     · The "prompt preview" shown in the UI list is still **the default one in memory** ——
# [EN] : so it looks like "I changed it but it didn't change", and yet when you investigate both ends
# [EN] check out (the disk write succeeded, and the in-memory copy is self-consistent).
# [EN] : ⇒ This is the most typical kind of "I changed it but it won't obey", and it is exactly the
# [EN] thing that
# [EN] :     clause A7 of `tools/verify_actor_layers` and mutation `M20` are specifically pinning down.
_MUTABLE = FIELD_KEYS + ('overridden', 'slug', 'prompt')

#: `when` 的合法取值（与 `roster.Role.when` 同一套）。
# [EN] : Legal values of `when` (the same set as `roster.Role.when`).
WHEN_VALUES = ('tick', 'day', 'export', 'always')
#: `tier` 的合法取值。
# [EN] : Legal values of `tier`.
TIER_VALUES = ('cheap', 'daily', 'front')
#: `tier` 的**人话**（界面上绝不露 `cheap`/`daily`/`front` —— 与「三档模型」
#: 那一段用同一套说法：摘要档/日常档/华彩档）。
# [EN] : The **plain-language** terms for `tier` (the UI must never expose `cheap`/`daily`/`front` ——
# [EN] this uses the same
# [EN] : wording as the "three-tier models" section: summary tier / daily tier / flourish tier).
TIER_LABEL: dict[str, str] = {'cheap': '摘要档', 'daily': '日常档',
                              'front': '华彩档'}
#: `feeds` 为空时的兜底（产出交给作者）。
# [EN] : Fallback when `feeds` is empty (hand the output to the author).
DEFAULT_FEEDS = 'author'

#: 每个内置职位的**英文文件名**（用户要求"文件名用名字命名，最好是英语"）。
#: ⚠ 这个映射是**文件名的事实来源**：改名可以改 `name`，但 slug 一旦定了
#:   就不要动 —— 它是盘上的文件名，动了等于把作者改过的那份弄丢。
# [EN] : The **English file name** of each built-in role (the user requested "name the file after the
# [EN] name, preferably in English").
# [EN] : ⚠ This mapping is the **source of truth for file names**: renaming can change `name`, but once
# [EN] the slug is set
# [EN] : don't touch it —— it is the file name on disk, and touching it is equivalent to losing the
# [EN] copy the author edited.
SLUGS: dict[str, str] = {
    'novelist': 'novelist',
    'screenwriter': 'screenwriter',
    'settings_room': 'writers_room',
    'reviewer': 'reviewer',
    'stylist': 'stylist',
    'sound': 'sound_designer',
    'polisher': 'polisher',
    'rehearsal': 'rehearsal',
    'director': 'director',
    'actor': 'actor',
    'extra': 'extra',
    'continuity': 'continuity',
    'script_doctor': 'script_doctor',
    'props': 'props',
    'art': 'art_director',
    'publicity': 'publicity',
    'researcher': 'researcher',
    # ── 系统服务 / 特殊 Agent（2026-10-12）──
    # [EN] ── System services / special Agent (2026-10-12) ──
    'ingest': 'ingest',
    'memory': 'memory',
    'progress': 'progress_eval',
    'compliance': 'compliance',
    'novelservices': 'novelservices',
}

#: 英文显示名（README 的对照表 + 英文界面）。
# [EN] : English display name (the README's lookup table + the English UI).
NAMES_EN: dict[str, str] = {
    'novelist': 'Novelist',
    'screenwriter': 'Screenwriter',
    'settings_room': 'Writers Room',
    'reviewer': 'Retrospective',
    'stylist': 'Stylist',
    'sound': 'Sound Designer',
    'polisher': 'Language Polisher',
    'rehearsal': 'Rehearsal',
    'director': 'Director',
    'actor': 'Actor',
    'extra': 'Extra',
    'continuity': 'Continuity',
    'script_doctor': 'Script Doctor',
    'props': 'Props',
    'art': 'Art Director',
    'publicity': 'Publicity',
    'researcher': 'Researcher',
    # ── System services / special Agent (2026-10-12) ──
    'ingest': 'Book Ingest',
    'memory': 'Memory Summarizer',
    'progress': 'Progress Evaluator',
    'compliance': 'Compliance Review',
    'novelservices': 'Creation Service',
}

#: `when` 的人话（写进默认提示词与界面）。
# [EN] : The plain-language wording of `when` (written into the default prompt and the UI).
WHEN_ZH: dict[str, str] = {
    'tick': '每一拍都在场（"活着"本身）',
    'day': '每天出工一次',
    'export': '导出/收尾时出工一次',
    'always': '全程在场（每拍都要看、要判断）',
}

#: 自定义职位的出工时机 —— **只允许 `day`**。
# [EN] : The work timing of custom roles —— **only `day` is allowed**.
#:
#: ★ 为什么不让自定义职位选 `tick`/`always`：那两档要在主循环里逐拍插一脚，
#:   而自定义职位没有经过那一层的接线（`sim/loop` 不认识它）。
#:   给一个选了不生效的选项，就是本项目的"假按钮"。所以对话框里这一项是
#:   **只读**的，并在说明里写清"自定义职位每天收工时出工一次"。
# [EN] : ★ Why not let custom roles choose `tick`/`always`: those two tiers need to poke in
# [EN] tick-by-tick in the main loop,
# [EN] : and custom roles have not gone through that layer of wiring (`sim/loop` doesn't know about
# [EN] them).
# [EN] : Giving an option that does nothing when selected is this project's "fake button". So this item
# [EN] in the dialog is
# [EN] : **read-only**, and the description clearly states "a custom role works once per day at end of
# [EN] day".
CUSTOM_WHEN = 'day'

#: 自定义职位的排序，排在所有内置职位之后。
# [EN] : The ordering of custom roles, placed after all built-in roles.
CUSTOM_ORDER = 500

#: 提示词块的抬头（注入到该职位的提示词里）。
# [EN] : The header of the prompt block (injected into that role's prompt).
HEAD = '【这个职位的工作要求（作者设定，与后面的通用手艺冲突时以这一段为准）】'


# ══════════════════════════════════════════════════════════════════════
#  数据
# [EN] Data
# ══════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class AgentSpec:
    """一个职位的**有效属性**（软件默认 + 项目定制合并之后）。
        English:
    A role's **effective attributes** (after merging software defaults + project customizations).
    """

    key: str
    slug: str
    name: str
    name_en: str
    intro: str                  # 一句话简介（＝名册里的 duty）
    usage: str                  # 什么情况下使用（自由文本，可空）
    prompt: str                 # 系统提示词（可在 md 里改）
    # [EN] One-line summary (= the duty in the roster)
    # [EN] When to use it (free text, may be empty)
    # [EN] System prompt (editable in the md)
    when: str = 'day'
    tier: str = 'daily'
    feeds: str = ''
    #: ★★ 这个职位**点名**要用哪个模型（2026-10-12 加）。
    # [EN] : ★★ This position **explicitly requires** which model to use (added 2026-10-12).
    #:
    #: 值是**模型登记表里的键**（`llm/models.py` → `llm_models.json`）；**空串 = 没点名**，
    #: 跟着它的 `tier` 与「默认模型」走（解析顺序见 `llm/models.resolve()`）。
    #: ⚠ 这里存的是**键**不是模型名：键一改，绑定全断，所以键是稳定的、
    #:   显示名才是给人看的那个。
    # [EN] ★★ Which model this position **explicitly** wants (added 2026-10-12).
    # [EN] The value is a **key in the model registry** (`llm/models.py` -> `llm_models.json`);
    # [EN] **empty string = nothing named**, follow its `tier` and the "default model" (see
    # [EN] `llm/models.resolve()` for the order).
    # [EN] ⚠ What's stored here is the **key**, not the model name: changing the key breaks every
    # [EN] binding, so the key is the stable thing and the display name is what humans read.
    model: str = ''
    #: 它是**剧组成员**（`crew`）还是**系统服务/特殊 Agent**（`service` / `special`）。
    #: 界面按它分组；`ROSTER.roles()` 只认 `crew`（见 `crew/roster.SERVICE_ROLES` 的说明）。
    # [EN] : whether this is a **crew member** (`crew`) or a **system service / special Agent**
    # [EN] (`service` / `special`). The UI groups by it; `ROSTER.roles()` only recognizes `crew`
    # [EN] (see the note at `crew/roster.SERVICE_ROLES`).
    kind: str = 'crew'
    builtin: bool = True        # 软件自带的（不可删）还是作者自建的
    # [EN] Whether it ships with the software (cannot be deleted) or was created by the author
    order: int = 0
    #: 哪几项被**项目层**覆盖过（界面用它在书斋里标出来）。
    # [EN] : Which items have been overridden by the **project layer** (the UI uses this to mark them in
    # [EN] the study).
    overridden: tuple[str, ...] = ()

    @property
    def is_custom(self) -> bool:
        return not self.builtin

    def merged_with(self, **fields: Any) -> 'AgentSpec':
        """返回一份改过几项的新 spec（`None` 表示"这项不动"）。
                English:
        Return a new spec with a few items changed (`None` means "leave this item untouched").
        """
        kw = {k: v for k, v in fields.items()
              if k in _MUTABLE and v is not None}
        return replace(self, **kw)

    def to_meta(self) -> dict[str, Any]:
        """写进 md frontmatter 的那几项（**不含 prompt** —— 那是正文）。
                English:
        The items written into the md frontmatter (**excluding prompt** —— that is the body text).
        """
        meta = {
            'key': self.key,
            'name': self.name,
            'name_en': self.name_en,
            'intro': self.intro,
            'usage': self.usage,
            'when': self.when,
            'tier': self.tier,
            'feeds': self.feeds,
            'builtin': bool(self.builtin),
            'order': int(self.order),
        }
        # ⚠ `model` **只在点名过时才写**（2026-10-12）：每次都写一个 `model: ''`
        #   会让 17 份老 md 都多出一行、还会把"作者从没碰过这一项"变成
        #   "作者写过空值"（`_apply` 判空跳过，两者最终行为一样，
        #   但盘上的 diff 会多出一堆噪音）。
        # [EN] ⚠ `model` is **only written when something was named** (2026-10-12): always writing
        # [EN] `model: ''` would add a line to all 17 old mds and turn "the author never touched
        # [EN] this" into "the author wrote an empty value" (both end up the same in `_apply`, but
        # [EN] the on-disk diff would carry a lot of noise).
        if self.model:
            meta['model'] = self.model
        return meta


def _default_prompt_v1(role: ROSTER.Role, name_en: str) -> str:
    """**上一版**的默认正文（2026-10-11 之前）。

    ⚠ 这个函数**只为升级用**（`upgrade_soft_templates` 拿它算出"旧样板长什么样"，
      好判断盘上那一份是"原样的样板"还是"作者改过的"）——
      **不要**再拿它生成新文件，也不要删：删了就没法判断老用户盘上那份该不该升级。
    
        English:
    The **previous version's** default body text (before 2026-10-11).
        ⚠ This function is **for upgrade only** (`upgrade_soft_templates` uses it to compute "what the old template looks like",
          so it can decide whether the copy on disk is "a pristine template" or "one modified by the author") ——
          **Do not** use it to generate new files again, and do not delete it: if deleted, there is no way to tell whether the old user's on-disk copy should be upgraded.
    """
    when = WHEN_ZH.get(role.when, role.when)
    feeds = ROSTER.BY_KEY.get(role.feeds)
    to = (f'「{feeds.name}」' if feeds is not None else (role.feeds or '作者'))
    return (
        f'你是本剧组的「{role.name}」（{name_en or role.key}）。\n'
        f'职责：{role.duty}。\n'
        f'出工时机：{when}；产出交给：{to}。\n'
        f'边界：只做本职位的事，不越权替别人（尤其是作者）做决定；'
        f'拿不到东西就说清楚没拿到，不要编。'
    )


#: ★★ 给**某些职位**的额外话，分两半（2026-10-11）：
# [EN] : ★★ Extra words for **certain roles**, split into two halves (2026-10-11):
#:
#: | 键 | 给谁看 | 会不会进提示词 |
# [EN] : | Key | For whom | Will it go into the prompt |
#: |---|---|---|
#: | `doc`  | **作者**（包进 HTML 注释里） | ❌ 不会（`prompt_block` 会剥掉注释） |
#: | `body` | **模型**（追加进正文） | ✅ 会 |
# [EN] : | `doc`  | **Author** (wrapped in HTML comments) | ❌ No (`prompt_block` strips out comments) |
# [EN] : | `body` | **Model** (appended to the body) | ✅ Yes |
#:
#: 为什么要分开：`agents/*.md` 的正文既是"作者编辑时看到的说明"、又是"发给模型的
#: 系统提示词"。混在一起时，一句写给作者的话（"别把具体角色写在这里"）会被
#: 模型读成对自己的约束 —— 那种错很隐蔽（表现成"这个角色说话怪怪的"）。
# [EN] : Why split them: the body of `agents/*.md` is both "the explanation the author sees while
# [EN] editing" and "the
# [EN] : system prompt sent to the model". When mixed together, a sentence meant for the author ("don't
# [EN] write specific
# [EN] : characters here") gets read by the model as a constraint on itself —— that kind of error is
# [EN] very subtle (it shows up as "this character talks weirdly").
#:
#: 目前只有这两位需要：**演员**与**群众演员** —— 它们是"系统层没有具体角色、
#: 项目层才有"的那一类（用户 2026-10-11 问的正是这件事）。
# [EN] : Currently only these two need it: **actor** and **extra** —— they are the category of "the
# [EN] system layer has no
# [EN] : specific characters, only the project layer does" (this is exactly what the user asked about
# [EN] on 2026-10-11).
ROLE_NOTES: dict[str, dict[str, str]] = {
    'actor': {
        'doc': (
            #  ⚠ 这里的每一行都**顶格写** —— 缩进由 `write_spec` 统一加
            #    （自己再缩一次会变成 10 空格，看着像跑出注释了）。
            # [EN] ⚠ Every line here is written **flush left** —— indentation is added uniformly by `write_spec`
            # [EN] (indenting again yourself turns it into 10 spaces, which looks like it ran outside the comment).
            '对**演员**多说一句：你的身份由**角色卡**决定（姓名/身份/性格/目标/秘密），\n'
            '这一份只管"演员这个工种"怎么干活 —— 具体角色在「项目 · 剧组 Agents」→\n'
            '「角色设置」里一人一份；这一类演员怎么说话在「演员类型库」里。'
        ),
        'body': (
            '★ 关于"你是谁"：**你不是一个固定的人**。你在每一部戏里演一个具体角色，\n'
            '演谁由**你的角色卡**决定（姓名/身份/性格/目标/秘密，以及"你这一类演员"的\n'
            '说话习惯）。上面这一段说的只是**演员这个工种怎么干活**，它不定义你的身份，\n'
            '也不包括别的角色的任何信息 —— 那些东西不是你的，别拿来说、别拿来想。\n'
            '一句话：**演的是角色卡上那个人，不是"一个演员"。**'
        ),
    },
    'extra': {
        'doc': (
            '对**群众演员**多说一句：这一类**系统层没有具体角色** —— 具体是谁由现场决定\n'
            '（走货的、报信的、街上看热闹的），程序按需要临时生成，不预写。\n'
            '这一份只管**这类人怎么演**：办完自己那件事就走，不进主线、不抢戏。'
        ),
        'body': '',
    },
}


def doc_of(key: str) -> str:
    """这个职位的"给作者看的额外说明"（没有就空串）。
        English:
    This role's "extra notes for the author" (empty string if none).
    """
    return str((ROLE_NOTES.get(str(key or '')) or {}).get('doc') or '')


def _notes_body(key: str) -> str:
    """这个职位的"给模型的额外正文"（没有就空串）。
        English:
    This role's "extra body text for the model" (empty string if none).
    """
    return str((ROLE_NOTES.get(str(key or '')) or {}).get('body') or '')


def _default_prompt(role: ROSTER.Role, name_en: str) -> str:
    """内置职位的**默认系统提示词**。

    ★ 它是**从名册长出来的**（不是又手写一份）：名册改了，默认提示词跟着改，
      不会出现"名册说 A、提示词说 B"。
    ★ 只写"身份 + 职责 + 出工时机 + 边界"，**不抄手艺** ——
      手艺（`craft/playbooks`）是另一层，抄进这里就成了两处各写一份。
    ★ 2026-10-11：末尾按职位追加 `ROLE_NOTES[key]['body']`（只有演员/群众演员有）——
      那两位是"系统层没有具体角色"的一类，需要在正文里把这件事对模型讲清楚。
    
        English:
    Built-in role's **default system prompt**.
        ★ It is **grown from the roster** (not another hand-written copy): when the roster changes, the default prompt changes with it,
          so there will never be a case where "the roster says A, the prompt says B".
        ★ Only write "identity + responsibility + when to work + boundaries", **do not copy the craft** ——
          the craft (`craft/playbooks`) is another layer; copying it here means writing it in two places.
        ★ 2026-10-11: at the end, append `ROLE_NOTES[key]['body']` by role (only actors/extra actors have it) ——
          those two are the kind where "the system layer has no concrete role", and this needs to be explained to the model in the body text.
    """
    base = _default_prompt_v1(role, name_en)
    if getattr(role, 'kind', 'crew') != 'crew':
        # ★ 系统服务 / 特殊 Agent（2026-10-12）：**不能说"你是本剧组的某某"** ——
        #   它们不是人，也不在剧组排班里（见 `crew/roster.SERVICE_ROLES`）。
        #   用同一段模板会让模型以为"今天要出工写一段戏"，而它真正要做的是
        #   一道固定的加工（提设定 / 压摘要 / 判进度 / 复核）。
        # [EN] ★ System services / special Agent (2026-10-12): **must not say "you are so-and-so of
        # [EN] this crew"** -- they are not people and are not in crew scheduling (see
        # [EN] `crew/roster.SERVICE_ROLES`). Using the same template would make the model think
        # [EN] "today I write a scene", while what it actually does is a fixed piece of processing.
        head = ('你是本程序的一个**系统服务**（不是剧组成员，不参与排班）。\n'
                if getattr(role, 'kind', '') == 'service'
                else '你是本程序外挂的**一套独立服务**（不是剧组成员，不参与排班）。\n')
        base = (f'{head}'
                f'名称：{role.name}（{name_en or role.key}）。\n'
                f'职责：{role.duty}。\n'
                f'边界：只做这一件事，不越权替别的步骤做决定；'
                f'拿不到东西就说清楚没拿到，不要编。')
    extra = _notes_body(role.key)
    return f'{base}\n\n{extra}' if extra else base


def _builtin_specs() -> list[AgentSpec]:
    """软件自带的全部条目：**剧组职位 + 系统服务 + 特殊 Agent**（2026-10-12）。

    ⚠ 用 `ROSTER.all_roles()` 而不是 `ROSTER.ROSTER` —— 后者只有剧组那 17 位，
      「剧组 Agents」页面上就看不到 `novelservices` 等 5 条，用户要的
      "novelservices 作为一个特殊 Agent 纳入管理"就落不了地。
      ⚠ 但**排班口径不受影响**：`ROSTER.roles()` 仍然只吐剧组职位
        （见 `crew/roster.SERVICE_ROLES` 上面那段）。

        English:
    Everything that ships with the software: **crew positions + system services + special Agent**
    (2026-10-12).
        ⚠ Uses `ROSTER.all_roles()` rather than `ROSTER.ROSTER` -- the latter only has the 17 crew
        members, so the "Crew Agents" page would not show `novelservices` and the other four, and the
        user's "let novelservices be managed as a special Agent" would not land.
        ⚠ But **scheduling is unaffected**: `ROSTER.roles()` still yields only crew positions (see
        the passage above `crew/roster.SERVICE_ROLES`).
    """
    out: list[AgentSpec] = []
    for i, r in enumerate(ROSTER.all_roles()):
        out.append(AgentSpec(
            key=r.key,
            slug=SLUGS.get(r.key, r.key),
            name=r.name,
            name_en=NAMES_EN.get(r.key, r.key),
            intro=r.duty,
            usage='',
            prompt=_default_prompt(r, NAMES_EN.get(r.key, r.key)),
            when=r.when, tier=r.tier, feeds=r.feeds,
            kind=getattr(r, 'kind', 'crew'),
            builtin=True, order=i))
    return out


# ══════════════════════════════════════════════════════════════════════
#  目录
# [EN] Directory
# ══════════════════════════════════════════════════════════════════════
#: 软件层目录的**临时接管**（判据 / 探针用来隔离）。
# [EN] : **Temporary takeover** of the software-layer directory (used by criteria / probes for
# [EN] isolation).
#:
#: ⚠ 为什么要有它：验证脚本必须能造几个假职位**而完全不碰用户真的
#:   `agents/` 目录**（本项目的老规矩：验证脚本一律隔离用户目录 ——
#:   `verify_ui_common.isolate_projects_dir` 是同一个理由）。
#:   生产代码**不要**动这个变量；要换目录请改 `soft_dir(base=...)` 的入参。
# [EN] : ⚠ Why it must exist: the verification script must be able to create a few fake roles **without
# [EN] touching the user's real
# [EN] : `agents/` directory at all** (this project's old rule: verification scripts always isolate the
# [EN] user directory ——
# [EN] :   `verify_ui_common.isolate_projects_dir` is for the same reason).
# [EN] : Production code should **not** touch this variable; to switch directories, change the argument
# [EN] to `soft_dir(base=...)`.
_SOFT_OVERRIDE: Path | None = None


def soft_dir(base: Path | None = None) -> Path:
    """软件级 `agents/` 目录（程序根目录下）。
        English:
    Software-level `agents/` directory (under the program root directory).
    """
    if base is not None:
        return Path(base)
    if _SOFT_OVERRIDE is not None:
        return Path(_SOFT_OVERRIDE)
    from config import APP_DIR
    return Path(APP_DIR) / SOFT_DIRNAME


def set_soft_dir(path: Path | None) -> None:
    """把软件层目录暂时指到别处（**判据/探针专用**，用完记得还原）。
        English:
    Temporarily point the software-level directory elsewhere (**for criteria/probes only**; remember
    to restore it when done).
    """
    global _SOFT_OVERRIDE
    _SOFT_OVERRIDE = (Path(path) if path is not None else None)
    _CACHE.clear()


def proj_dir(project: Any) -> Path:
    """项目级 `agents/` 目录。`project` 可以是 `Project`，也可以是路径。

    ⚠⚠ **`Path` 也有 `.root` 属性**（`Path('C:/a/b').root` 是 `'C:\\\\'`，
    相对路径是 `''`）—— 所以先 `isinstance` 判一下再取 `.root`。
    第一版写成 `getattr(project, 'root', None)` 就踩了这个：
    传 `Path` 进来时它取到的是**盘根**，于是文件写到了 `C:\\\\agents`（判据 A4c 抓到）。
    
        English:
    Project-level `agents/` directory. `project` can be a `Project` or a path.
        ⚠⚠ **`Path` also has a `.root` attribute** (`Path('C:/a/b').root` is `'C:\\\\'`,
        and for a relative path it is `''`) —— so do an `isinstance` check first before accessing `.root`.
        The first version wrote `getattr(project, 'root', None)` and hit this trap:
        when a `Path` is passed in, it got the **drive root**, so the file was written to `C:\\\\agents` (caught by criterion A4c).
    """
    if project is None:
        return Path()
    if isinstance(project, (str, Path)):
        root: Any = project
    else:
        root = getattr(project, 'root', None) or project
    return Path(root) / PROJ_DIRNAME


def _slugify(text: str) -> str:
    """把用户给的英文名整成文件名（小写、下划线）。

    ⚠ 认不出任何 ASCII 字母/数字时返回空串 —— 由调用方另给一个兜底名。
      别在这里编一个 `agent1` 之类的：那会让"作者起的名字"和"盘上的文件"
      莫名其妙地不一样，而他改完看不出哪里错了。
    
        English:
    Turn the English name given by the user into a filename (lowercase, underscores).
        ⚠ Return an empty string when no ASCII letter/digit is recognized —— the caller supplies a fallback name separately.
          Do not make up an `agent1` or the like here: that would make "the name the author chose" and "the file on disk"
          inexplicably different, and after editing he cannot see where the mistake is.
    """
    s = re.sub(r'[^0-9A-Za-z]+', '_', str(text or '').strip()).strip('_')
    return s.lower()


def unique_slug(soft: Path, want: str, *, keep: str = '') -> str:
    """在软件目录里取一个没被占用的 slug（重名则加 `_2` `_3`…）。
        English:
    Get an unused slug in the software directory (on name collision add `_2` `_3`…).
    """
    base = _slugify(want)
    if not base:
        base = 'agent'
    slug, n = base, 1
    names = {p.stem.lower() for p in _md_files(soft)}
    while slug in names and slug != (keep or ''):
        n += 1
        slug = f'{base}_{n}'
    return slug


def _md_files(d: Path) -> list[Path]:
    try:
        if not d.exists():
            return []
        return sorted(p for p in d.iterdir()
                      if p.is_file() and p.suffix.lower() == '.md'
                      and p.name.lower() != README_NAME.lower())
    except OSError:
        return []


# ══════════════════════════════════════════════════════════════════════
#  读写
# [EN] Read/write
# ══════════════════════════════════════════════════════════════════════
def parse_md(text: str) -> tuple[dict[str, Any], str]:
    """拆 md：返回 `(frontmatter dict, 正文)`。坏文件返回 `({}, 原文)`。
        English:
    Split md: return `(frontmatter dict, body)`. For a bad file return `({}, original text)`.
    """
    raw = str(text or '')
    if not raw.startswith('---'):
        return {}, raw
    end = raw.find('\n---', 3)
    if end < 0:
        return {}, raw
    head = raw[3:end]
    body = raw[end + 4:]
    if body.startswith('\n'):
        body = body[1:]
    try:
        meta = yaml.safe_load(head) or {}
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('agent 文件 frontmatter 解析失败：%r', e)
        return {}, raw
    if not isinstance(meta, dict):
        return {}, raw
    return meta, body.strip('\n')


def render_md(spec: AgentSpec, *, banner: str = '') -> str:
    """把 spec 渲染成 md 文本（frontmatter + 正文＝系统提示词）。
        English:
    Render the spec into md text (frontmatter + body = system prompt).
    """
    meta = spec.to_meta()
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False,
                          default_flow_style=False).strip()
    lines = ['---', head, '---', '']
    if banner:
        lines += [banner, '']
    lines.append(spec.prompt.strip() or '（还没写系统提示词）')
    return '\n'.join(lines).rstrip() + '\n'


def read_dir(d: Path) -> dict[str, dict[str, Any]]:
    """读一个目录（软件级或项目级）→ `{key_or_slug: {..., 'prompt': ...}}`。

    ⚠ 认的是 **frontmatter 里的 `key`/`name_en`**，不是文件名 ——
      这样作者把文件改个名，它的身份也不会跟着变（认东西不认路径）。
      实在没有 key 时才退回文件名当 slug。
    
        English:
    Read one directory (software-level or project-level) → `{key_or_slug: {..., 'prompt': ...}}`.
        ⚠ What is recognized is the **`key`/`name_en` in the frontmatter**, not the filename ——
          this way, even if the author renames the file, its identity does not change along with it (recognize by content, not by path).
          Only when there is truly no key does it fall back to using the filename as the slug.
    """
    out: dict[str, dict[str, Any]] = {}
    for p in _md_files(d):
        try:
            text = p.read_text(encoding='utf-8', errors='replace')
        except OSError as e:
            _LOG.warning('读不了 %s：%r', p, e)
            continue
        meta, body = parse_md(text)
        row: dict[str, Any] = {k: meta.get(k) for k in FIELD_KEYS if k in meta}
        row['prompt'] = body
        row['_file'] = p.name
        kid = str(row.get('key') or row.get('name_en') or p.stem).strip()
        if not kid:
            continue
        # ⚠ slug 一定要**归一化**（`_slugify`）：它是文件名。不归一化的话
        #   写出去的 `Fact Checker.md` 和查回来的 `fact_checker` 对不上 ——
        #   表现是"新建完了删不掉"（自测当场踩到）。
        # [EN] ⚠ The slug must be **normalized** (`_slugify`): it is the file name. Without normalization,
        # [EN] the written-out `Fact Checker.md` and the read-back `fact_checker` won't match ——
        # [EN] the symptom is "it can't be deleted after creation" (hit on the spot during self-test).
        row['slug'] = _slugify(row.get('name_en') or p.stem) or p.stem
        out[kid] = row
    return out


def write_spec(d: Path, spec: AgentSpec, *, banner: str = '') -> Path:
    """把一份 spec 写进目录（文件名 = slug.md）。返回写好的路径。

    `banner` 不给时自动用 `BANNER`（通用说明）+ `doc_of(spec.key)`（这个职位
    额外要嘱咐作者的话）—— 两段都是 HTML 注释，**不进提示词**。
    
        English:
    Write a spec into the directory (filename = slug.md). Return the written path.
        When `banner` is not given, automatically use `BANNER` (general notes) + `doc_of(spec.key)` (this role's
        extra words to the author) —— both segments are HTML comments, **not included in the prompt**.
    """
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f'{spec.slug}.md'
    if not banner:
        _doc = doc_of(spec.key)
        if _doc:
            #  ⚠ doc 要**按行缩进**再拼：BANNER 内文是 5 空格起排的，
            #    不缩进的话那几行会顶到最左边（在 md 里看着像"跑到注释外面"）。
            # [EN] ⚠ `doc` must be **indented line by line** before concatenation: the BANNER's inner text is laid
            # [EN] out starting at 5 spaces,
            # [EN] without indentation those lines stick to the far left (in md it looks like "it ran outside the
            # [EN] comment").
            _doc = '\n'.join(('     ' + ln) if ln.strip() else ''
                             for ln in _doc.splitlines())
            banner = BANNER.replace(' -->', '\n' + _doc + ' -->')
        else:
            banner = BANNER
    atomic_write_text(p, render_md(spec, banner=banner))
    return p


# ══════════════════════════════════════════════════════════════════════
#  播种（首次运行把内置职位落成文件）
# [EN] Seeding (writing the built-in roles to files on first run)
# ══════════════════════════════════════════════════════════════════════
BANNER_V1 = (
    '<!-- 这是本职位在**软件层**的设置。可以直接用文本编辑器改，\n'
    '     也可以在「天机 · 剧组 Agents」里改（两处是同一份文件）。\n'
    '     正文就是该职位的**系统提示词**。 -->')

#: 作者看到的说明（**HTML 注释** —— `prompt_block()` 会剥掉，**不进提示词**）。
#: ★ 2026-10-11 起把"分层"这件事写在这里：作者最常问的就是
#:   "这一份和项目里那份、和那个角色的设置，到底谁管什么"。
# [EN] : The explanation the author sees (**HTML comment** —— `prompt_block()` strips it out, so it
# [EN] **does not go into the prompt**).
# [EN] : ★ Starting 2026-10-11, write the "layering" thing here: what authors ask most is
# [EN] : "between this one, the one in the project, and that character's settings, who governs what
# [EN] exactly".
BANNER = (
    '<!-- 这是本职位在**软件层**的设置。可以直接用文本编辑器改，\n'
    '     也可以在「天机 · 剧组 Agents」里改（两处是同一份文件）。\n'
    '\n'
    '     ⚠ **这一段注释不会发给模型**（`crew/catalog.prompt_block` 会剥掉 HTML 注释）——\n'
    '     它是写给你看的。真正的系统提示词，是注释下面那一段正文。\n'
    '\n'
    '     四层各管什么（越靠下的越具体、越该压过上面的）：\n'
    '       ① 本文件（软件层职位）＝ **这个工种**怎么干活 —— 换本书也该是对的；\n'
    '       ② 「天机 · 剧组 Agents」→「演员类型库」＝ **这类演员**怎么说话（只演员有）；\n'
    '       ③ 项目里同名文件 ＝ **这一部戏**的额外要求；\n'
    '       ④ 具体**角色** ＝ 在「项目 · 剧组 Agents」→「角色设置」里，一人一份。\n'
    '\n'
    '     ⚠ 具体**角色**不要写进任何一份 `.md`：md 是**全组通读**的，\n'
    '     写进来等于让每个角色都读到别人的秘密。 -->')


def seed_soft(base: Path | None = None, *, force: bool = False) -> list[str]:
    """把内置职位的 md 播到软件目录（已存在的不动，除非 `force`）。

    返回这次**新写**的文件名。播种是幂等的：跑一百次结果一样。
    
        English:
    Seed the built-in role md into the software directory (existing ones are left alone unless
    `force`).
        Return the filenames **newly written** this time. Seeding is idempotent: running it a hundred times gives the same result.
    """
    d = soft_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for spec in _builtin_specs():
        p = d / f'{spec.slug}.md'
        if p.exists() and not force:
            continue
        #  ⚠ **不要**在这儿传 `banner=BANNER`：`write_spec` 不传 banner 时会
        #    自己拼上"通用说明 + 这个职位的额外说明（`doc_of`）"。
        #    硬传 BANNER 会把演员/群众演员那两段额外说明**吞掉**
        #    （第一版就是这么写的，播出来的 actor.md 里没有那两句。
        #      它是"看起来播成功了、其实少了一段"的那种安静错）。
        # [EN] ⚠ Do **not** pass `banner=BANNER` here: when `write_spec` isn't passed a banner it
        # [EN] concatenates "general explanation + this role's extra explanation (`doc_of`)" itself.
        # [EN] Hardcoding BANNER will **swallow** the two extra notes for actors/extras
        # [EN] (this is how the first version was written; the broadcast actor.md has neither of those two
        # [EN] sentences.
        # [EN] It's the quiet kind of error where it "looks like it played successfully, but actually a chunk
        # [EN] is missing").
        write_spec(d, spec)
        written.append(p.name)
    return written


def write_readme(base: Path | None = None) -> Path:
    """写 `agents/README.md`（英语名 ↔ 中文名 对照表）。
        English:
    Write `agents/README.md` (English name ↔ Chinese name mapping table).
    """
    d = soft_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in effective(base=base):
        rows.append(f"| `{spec.slug}.md` | {spec.name_en} | {spec.name} | "
                    f"{spec.intro} |")
    text = (
        '# Agents（剧组职位设置）\n\n'
        '这个文件夹里**每个 `.md` 是一个职位**，文件名用英文（`novelist.md`）。\n'
        '正文默认就是该职位的**系统提示词**，frontmatter 里是它的属性。\n\n'
        '英文名 ↔ 中文名对照：\n\n'
        '| 文件 | English | 中文 | 作用 |\n'
        '|---|---|---|---|\n' + '\n'.join(rows) + '\n\n'
        '---\n\n'
        '## 软件层与项目层\n\n'
        '- **本文件夹** = 软件层：跨所有小说生效的默认设定；\n'
        '- **每个项目文件夹下的 `agents/`** = 项目层：只对那一本生效的定制；\n'
        '- 运行时 = **软件层 + 项目层**（项目层只覆盖它写了的字段，其余跟软件层）。\n\n'
        '## 想加一个自己的职位？\n\n'
        '在「天机（程序设置）· 剧组 Agents」里点「新建」。'
        '自建职位会在**每天收工**时出工一次，产出落到那一轮运行文件夹里。\n\n'
        '---\n\n'
        '## ★ 演员：这一份管不了"演谁"（2026-10-11）\n\n'
        '演员是唯一一个**系统层没有具体角色、项目层才有**的职位 —— 所以它的设置\n'
        '分成四处，按"换什么它才变"排（越靠下越具体、越该压过上面的）：\n\n'
        '| 层 | 在哪 | 管什么 |\n'
        '|---|---|---|\n'
        '| ① 系统 · 职位 | 本文件夹的 `actor.md` | 演员**这个工种**怎么干活 |\n'
        '| ② 系统 · 类型库 | `actors/archetypes.yaml`（界面：天机 ·「演员类型库」） | '
        '**预写好的各种演员**怎么说话（每型含变奏轴） |\n'
        '| ③ 项目 · 剧组 | `<项目>/agents/actor.md` | 这**一部戏**的演法基调 |\n'
        '| ④ 项目 · **角色** | `<项目>/设定集/人物.yaml`（界面：书斋 · 演员行的 👥'
        '「角色设置」） | **张三这个人**演成什么样 |\n\n'
        '**一句话**：①②管"怎么演"、③④管"演谁"；冲突时**以角色为准**'
        '（这句话写在提示词里，见 `actors/casting.py`）。\n\n'
        '> ⚠⚠ **具体角色不要写进任何一份 `.md`**（包括 `actor.md`）。\n'
        '> 这里的每一份都是**全剧组通读**的：把"张三高冷、李四热情"写进来，\n'
        '> 等于让**每个角色都读到别人的设定**（张三会知道李四的秘密）——当场串台。\n'
        '> 角色有自己**一人一份**的位置（④），见上一段那个表。\n\n'
        '## 注意\n\n'
        '- 软件自带的职位**不能删**（只能改）；自建职位可以删。\n'
        '- 删掉项目层的那份 = 这一本回到软件默认（不会影响别的书）。\n'
        '- 正文里 `<!-- … -->` 包起来的部分是**写给你看的**（说明、提醒），'
        '不会发给模型；要影响模型的话写在注释**外面**。\n')
    p = d / README_NAME
    atomic_write_text(p, text)
    return p


# ══════════════════════════════════════════════════════════════════════
#  合并（软件默认 + 项目定制）
# [EN] Merge (software default + project customization)
# ══════════════════════════════════════════════════════════════════════
#: 模块级绑定：当前这一轮属于哪本书（`role()` / `prompt_block()` 用它取项目层）。
# [EN] : module-level binding: which book the current round belongs to (`role()` / `prompt_block()` use
# [EN] it to fetch the project layer).
_CURRENT_PROJECT: Any = None


def bind_project(project: Any) -> None:
    """装配时调一次：告诉这一层"这一轮是哪本书"。
        English:
    Call once at assembly time: tell this layer "which book is this round".
    """
    global _CURRENT_PROJECT
    _CURRENT_PROJECT = project


def bound_project() -> Any:
    return _CURRENT_PROJECT


def _apply(spec: AgentSpec, row: dict[str, Any]) -> AgentSpec:
    """把一层（软件或项目）读到的字段盖到 spec 上。
        English:
    Overlay the fields read from one layer (software or project) onto the spec.
    """
    fields: dict[str, Any] = {}
    for k in ('name', 'name_en', 'intro', 'usage', 'when', 'tier', 'feeds', 'model'):
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            fields[k] = s
    # ⚠ `model` 走**与其它字段一样**的稀疏规矩：**不写 = 跟上一层**。
    #   所以这里**不为空串开特例** —— 开特例（"写了空值就撤销上层"）会多出
    #   一条只有手改文件才走得到的路，而那条路没有界面入口（= 死代码）。
    # [EN] ⚠ `model` follows the **same sparse rule as every other field**: **not written = follow
    # [EN] the layer above**. So **no special case for the empty string** here -- such a case would
    # [EN] add a path only reachable by hand-editing a file, with no UI entry point (= dead code).
    if fields.get('when') and fields['when'] not in WHEN_VALUES:
        fields.pop('when')                    # 认不出的时机不采纳（别把职位弄停摆）
        # [EN] Unrecognized timing is not adopted (don't let the position stall)
    if fields.get('tier') and fields['tier'] not in TIER_VALUES:
        fields.pop('tier')
    # ⚠⚠ 判断"这一层到底写没写**正文**"必须先**剥掉注释**再比 ——
    #    `read_dir` 给的 prompt 是**整个正文**（含 `BANNER` 那段给作者的说明）。
    #    作者在项目层只改了名字时（`save_project` 的**稀疏写入**），
    #    那个文件里的正文是 `banner + （还没写系统提示词）`：
    #      · 拿它跟占位符**整段比** → 不相等 → 被当成"写了正文"采纳上来，
    #        于是**软件层的真提示词被一段占位符顶掉**了；
    #      · 剥掉注释再比 → 剩占位符 → 正确地**不覆盖**。
    #    ⚠ 存进 `fields` 的仍是**原样**（含注释）：界面编辑框要能看见那段说明，
    #      剥了再存等于作者一保存就把说明抹了（静默丢内容）。
    #      真正的剥发生在**出口**（`prompt_block`）。
    # [EN] ⚠⚠ To decide whether "this layer actually wrote the **body text**" you must first **strip
    # [EN] comments** before comparing —
    # [EN] The prompt given by `read_dir` is the **entire body text** (including the `BANNER` note for the
    # [EN] author).
    # [EN] When the author only changed the name at the project layer (the **sparse write** of
    # [EN] `save_project`),
    # [EN] the body text in that file is `banner + (system prompt not yet written)`:
    # [EN] · Compare it with the placeholder **as a whole segment** → not equal → adopted as "body text
    # [EN] written",
    # [EN] so **the software layer's real prompt gets displaced by a placeholder**;
    # [EN] · strip comments then compare → only the placeholder remains → correctly **does not overwrite**.
    # [EN] ⚠ What's stored in `fields` is still **as-is** (comments included): the UI edit box needs to
    # [EN] show that note,
    # [EN] stripping before saving would mean the author wipes the note the moment they save (silent
    # [EN] content loss).
    # [EN] The actual stripping happens at the **exit** (`prompt_block`).
    pr = row.get('prompt')
    if isinstance(pr, str):
        _plain = _strip_html_comments(pr).strip()
        if _plain and _plain != '（还没写系统提示词）':
            fields['prompt'] = pr.strip()
    return spec.merged_with(**fields) if fields else spec


def effective(*, base: Path | None = None, project: Any = '____bound____',
              ) -> list[AgentSpec]:
    """算出**有效属性表**：软件默认 → 软件层文件 → 项目层文件。

    `project=None` 表示**不要**项目层（天机里编辑软件层时用）；
    不传 = 用 `bind_project()` 绑的那个。

    ★ 带**按目录指纹的缓存**：`role()` / `prompt_block()` 在剧组里每次出工都要
      调，不缓存就是"每拼一次提示词读一遍 17+ 个文件"。指纹含 mtime 与大小，
      所以作者在记事本里改了 md 也会**当场生效**（不用重启）。
    
        English:
    Compute the **effective attributes table**: software defaults → software-layer file →
    project-layer file.
        `project=None` means **do not** use the project layer (used when editing the software layer in Tianji);
        not passing it = use the one bound by `bind_project()`.
        ★ Has **cache keyed by directory fingerprint**: `role()` / `prompt_block()` are called on every job in the crew,
          without caching it would be "read 17+ files each time the prompt is assembled". The fingerprint includes mtime and size,
          so if the author edits the md in Notepad it also **takes effect immediately** (no restart needed).
    """
    if project == '____bound____':
        project = _CURRENT_PROJECT
    key = signature(base=base, project=project)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    specs: dict[str, AgentSpec] = {s.key: s for s in _builtin_specs()}

    def _overlay(d: Path, *, mark: bool) -> None:
        for kid, row in read_dir(d).items():
            if kid in specs:
                before = specs[kid]
                after = _apply(before, row)
                if mark and after is not before:
                    touched = tuple(sorted({*before.overridden,
                                            *(k for k in ('name', 'name_en',
                                                          'intro', 'usage',
                                                          'prompt', 'when',
                                                          'tier', 'feeds',
                                                          'model')
                                              if getattr(after, k)
                                              != getattr(before, k))}))
                    after = after.merged_with(overridden=touched)
                specs[kid] = after
                continue
            #  ★★★ 2026-10-13：这里原本是 `if True:` —— 那是**一次手工诊断留下的残留**
            #    （手工贴的变异体**不带变异标记**，两条扫描都没抓到它，
            #     `verify_agent_catalog` 的 A8 是唯一把它照出来的判据）。
            #    `mark` 就是"哪一层"的开关：`_overlay(soft_dir, mark=False)` /
            #    `_overlay(proj_dir, mark=True)`。语义是**只有软件层能新建**：
            #      · 软件层（`not mark`）碰到不认识的文件 ⇒ 采纳为**自建职位**；
            #      · 项目层（`mark`）碰到不认识的文件 ⇒ **不采纳**（落到下面的注释上）。
            #    写成 `if True:` 的后果：**项目层写进去的 ghost.md 会被当成自建职位采纳**,
            #    也就是"这本小说能在自己的 agents 目录里凭空造出软件没有的职位"。
            # [EN] ★★★ 2026-10-13: this used to read `if True:` -- the **leftover of a manual
            # [EN] diagnostic** (hand-pasted mutants carry no **variant marker**, so both scans missed it;
            # [EN] A8 in `verify_agent_catalog` is the only criterion that caught it).
            # [EN] `mark` is the "which layer" switch: `_overlay(soft_dir, mark=False)` /
            # [EN] `_overlay(proj_dir, mark=True)`. The semantics are **only the software layer may
            # [EN] create new positions**:
            # [EN]   · software layer (`not mark`) sees an unknown file => adopt it as a **self-built
            # [EN]     position**;
            # [EN]   · project layer (`mark`) sees an unknown file => **not adopted** (falls through to
            # [EN]     the comment below).
            # [EN] With `if True:` a `ghost.md` written into the project layer was adopted as a self-built
            # [EN] position -- i.e. a book could conjure positions the software does not have.
            if not mark:
                # 软件层里的**自建职位**
                # [EN] A **self-built position** in the software layer
                slug = _slugify(row.get('slug') or kid) or _slugify(kid) or kid
                specs[kid] = AgentSpec(
                    key=kid, slug=slug,
                    name=str(row.get('name') or row.get('name_en') or kid),
                    name_en=str(row.get('name_en') or kid),
                    intro=str(row.get('intro') or ''),
                    usage=str(row.get('usage') or ''),
                    prompt=str(row.get('prompt') or ''),
                    when=CUSTOM_WHEN, tier=str(row.get('tier') or 'daily'),
                    feeds=str(row.get('feeds') or 'author'),
                    model=str(row.get('model') or ''),
                    builtin=False, order=CUSTOM_ORDER)
            # 项目层里的「自建职位」：**不采纳** —— 新建只在软件层做。
            # [EN] A "self-built position" in the project layer: **not adopted** — creation only happens in the
            # [EN] software layer.
    _overlay(soft_dir(base), mark=False)
    if project is not None:
        _overlay(proj_dir(project), mark=True)
    out = sorted(specs.values(), key=lambda s: (s.order, s.key))
    _CACHE.clear()                  # 只留最新一份（目录不长，够用）
    # [EN] Keep only the latest copy (the directory is short, good enough)
    _CACHE[key] = out
    return out


#: `effective()` 的缓存（键 = `signature()`）。
# [EN] : cache for `effective()` (key = `signature()`).
_CACHE: dict[tuple, list[AgentSpec]] = {}


def signature(*, base: Path | None = None,
              project: Any = '____bound____') -> tuple:
    """两个目录的**指纹**（文件名 + mtime + 大小）。改了任何一个就换键。
        English:
    **Fingerprints** of the two directories (filename + mtime + size). If any one changes, the key
    changes.
    """
    if project == '____bound____':
        project = _CURRENT_PROJECT

    def _sig(d: Path) -> tuple:
        try:
            return tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                                for p in _md_files(d)))
        except OSError:
            return ()

    sd = soft_dir(base)
    if project is None:
        return (str(sd), _sig(sd), '', ())
    pd = proj_dir(project)
    return (str(sd), _sig(sd), str(pd), _sig(pd))


def effective_map(**kw: Any) -> dict[str, AgentSpec]:
    return {s.key: s for s in effective(**kw)}


def get(key: str, **kw: Any) -> AgentSpec | None:
    """按 key 取一条有效属性（认不出返回 `None`）。
        English:
    Get an effective attribute by key (return `None` if not recognized).
    """
    return effective_map(**kw).get(str(key or '').strip())


# ══════════════════════════════════════════════════════════════════════
#  写作（GUI 用）
# [EN] Writing (used by the GUI)
# ══════════════════════════════════════════════════════════════════════
def save_soft(spec: AgentSpec, *, base: Path | None = None,
              old_slug: str = '') -> Path:
    """把一条写进**软件层**（按 slug 定位文件；改了 slug 就等于改名）。

    `old_slug`：改过英文名时把旧文件删掉 —— 不删就会在 `agents/` 里留下一个
    **孤儿文件**（列表上看不见它，但它还在，下次播种/扫描又冒出来）。
    ⚠ 只删 `.md`，而且**旧 slug 必须真的是自建职位**（内置职位换名不改文件）。
    
        English:
    Write one into the **software layer** (locate the file by slug; changing the slug is equivalent
    to renaming).
        `old_slug`: when the English name was changed, delete the old file —— if not deleted, an
        **orphan file** will be left in `agents/` (invisible in the list, but still there, and it reappears on the next seed/scan).
        ⚠ Only delete `.md`, and the **old slug must truly be a self-created role** (built-in roles change names without changing files).
    """
    p = write_spec(soft_dir(base), spec, banner=BANNER)
    old = _slugify(old_slug)
    if old and old != spec.slug and not spec.builtin:
        q = soft_dir(base) / f'{old}.md'
        if q.suffix == '.md' and q.exists() and q.resolve() != p.resolve():
            try:
                q.unlink()
            except OSError as e:                                 # noqa: BLE001
                _LOG.warning('旧文件没删掉（不影响本次保存）：%r', e)
    return p


def create_custom(*, name: str, intro: str = '', prompt: str = '',
                  name_en: str = '', usage: str = '', tier: str = 'daily',
                  feeds: str = 'author', base: Path | None = None,
                  model: str = '',
                  ) -> AgentSpec:
    """新建一个**自建职位**（只在软件层）。返回写好的 spec。

    `key` 与 `slug` 同一个值（自建职位没有"稳定键"的历史包袱）。
    
        English:
    Create a **user-defined job** (software layer only). Return the written spec.
        `key` and `slug` have the same value (user-defined jobs have no historical baggage of a "stable key").
    """
    d = soft_dir(base)
    slug = unique_slug(d, name_en or name)
    spec = AgentSpec(key=slug, slug=slug, name=str(name).strip() or slug,
                     name_en=str(name_en).strip() or slug,
                     intro=str(intro).strip(), usage=str(usage).strip(),
                     prompt=str(prompt).strip(),
                     when=CUSTOM_WHEN, tier=(tier if tier in TIER_VALUES else 'daily'),
                     feeds=str(feeds or 'author').strip(),
                     model=str(model or '').strip(),
                     builtin=False, order=CUSTOM_ORDER)
    write_spec(d, spec, banner=BANNER)
    return spec


def delete_soft(slug: str, *, base: Path | None = None) -> tuple[bool, str]:
    """删一个**自建**职位。返回 `(是否删掉, 为什么)`。

    ★ 三重护栏（每条都有判据）：**认 slug 不认路径** · **只删 `.md`** ·
      **软件自带的职位一律拒删**（它们是程序的一部分）。
    
        English:
    Delete a **user-defined** job. Return `(whether deleted, why)`.
        ★ Triple guardrail (each with a criterion): **match by slug, not by path** · **only delete `.md`** ·
          **jobs shipped with the software are always refused deletion** (they are part of the program).
    """
    d = soft_dir(base)
    spec = next((s for s in effective(base=base, project=None) if s.slug == slug),
                None)
    if spec is None:
        return False, '没有这个职位'
    if spec.builtin:
        return False, '软件自带的职位不能删（只能改）'
    p = (d / f'{slug}.md')
    if p.parent.resolve() != Path(d).resolve() or p.suffix != '.md':
        return False, '路径不对，拒绝删除'
    if not p.exists():
        return False, '文件不在了'
    try:
        p.unlink()
    except OSError as e:
        return False, f'删不掉：{e}'
    return True, ''


def save_project(project: Any, key: str, *, only: Iterable[str] | None = None,
                 **fields: Any) -> Path:
    """把某几个字段写进**项目层**（**只写被覆盖的那几项**）。

    ★ **稀疏写入**是要紧的：整份抄一遍的话，作者升级软件、内置提示词改好了，
      他这一本还停在旧版（"我改过一行"变成"我永远停在旧版"）。
      所以这里用 `replace(builtin_spec, **patch)` 造一份**只带改动**的 spec，
      其余字段**留空** —— 空字段在 `_apply()` 里就是不覆盖。
    
        English:
    Write certain fields into the **project layer** (**only write the items that are overridden**).
        ★ **Sparse writes** matter: if the whole thing is copied over, then when the author upgrades the software and the built-in prompt is improved,
          their copy stays on the old version ("I changed one line" becomes "I'm stuck on the old version forever").
          So here `replace(builtin_spec, **patch)` is used to build a spec that **carries only the changes**,
          leaving the other fields **empty** —— empty fields are simply not overridden in `_apply()`.
    """
    base = _builtin_or_soft(key)
    if base is None:
        raise KeyError(f'没有这个职位：{key!r}')
    patch = {k: v for k, v in fields.items() if k in FIELD_KEYS
             and v is not None and str(v).strip()}
    if only is not None:
        patch = {k: v for k, v in patch.items() if k in set(only)}
    patch.pop('key', None)
    patch.pop('builtin', None)
    blank = {'name': '', 'name_en': '', 'intro': '', 'usage': '', 'prompt': ''}
    blank.update(patch)          # ⚠ 先铺"空"，再盖上 patch（直接展开两个 kwargs
    sparse = replace(base, **blank)   # 会 ValueError: multiple values）
    # [EN] ⚠ First lay down "empty", then overlay the patch (unpacking both kwargs directly
    # [EN] would raise ValueError: multiple values)
    return write_spec(proj_dir(project), sparse, banner=(
        '<!-- 这是**这一本书**对「' + base.name + '」的定制。\n'
        '     只写了与软件默认不同的字段；删掉本文件即回到软件默认。 -->'))


def clear_project(project: Any, slug: str) -> tuple[bool, str]:
    """删掉项目层那一份（= 这一本回到软件默认）。
        English:
    Delete the project-layer copy (= this copy reverts to the software default).
    """
    p = proj_dir(project) / f'{slug}.md'
    if not p.exists():
        return False, '这一本没有定制这一条'
    try:
        p.unlink()
    except OSError as e:
        return False, f'删不掉：{e}'
    return True, ''


def _builtin_or_soft(key: str) -> AgentSpec | None:
    return next((s for s in effective(project=None) if s.key == key), None)


# ══════════════════════════════════════════════════════════════════════
#  注入（剧组提示词里那一段）
# [EN] Injection (that segment in the crew prompt)
# ══════════════════════════════════════════════════════════════════════
def prompt_block(key: str, *, project: Any = '____bound____') -> str:
    """该职位的**系统提示词块**（空串 = 没有，调用方照旧）。

    只给"有实现、会真的说话"的职位（`OnDuty` 那两位是状态转述，不产生调用）。

    ★★ 2026-10-11：**剥掉 HTML 注释再发**。
      为什么：`agents/*.md` 的正文既是"作者编辑时看到的东西"、又是发给模型的
      系统提示词。而 `BANNER`（以及演员/群众演员各自那段 `doc`）是**写给作者的**
      ——"别把具体角色写在这里""去项目里设角色"这些话对模型毫无意义，
      更坏的是它会当成对自己的约束（表现成"这个角色说话怪怪的"，极难查）。
      ⇒ 用注释把两类文本分开：`<!-- -->` 里的给作者，外面的给模型。
      ⚠ 判据 `verify_actor_layers` 的 C 组与反例法都盯着这一条。
    
        English:
    The job's **system prompt block** (empty string = none, caller behaves as before).
        Only for jobs that "have an implementation and actually speak" (the two `OnDuty` ones are status narrations and produce no calls).
        ★★ 2026-10-11: **Strip HTML comments before sending**.
          Why: the body of `agents/*.md` is both "what the author sees while editing" and the
          system prompt sent to the model. And `BANNER` (as well as the `doc` section for the actor/extra) is **written for the author**
          —— phrases like "don't write specific roles here" and "go set roles in the project" mean nothing to the model,
          and worse, it may take them as constraints on itself (manifesting as "this role talks weirdly", extremely hard to trace).
          ⇒ Use comments to separate the two kinds of text: what's inside `<!-- -->` is for the author, what's outside is for the model.
          ⚠ Criterion: group C of `verify_actor_layers` and the counterexample method both watch this.
    """
    spec = get(key, project=project)
    if spec is None:
        return ''
    body = _strip_html_comments(spec.prompt).strip()
    if not body:
        return ''
    extra = f'\n适用：{spec.usage.strip()}' if spec.usage.strip() else ''
    # ★★ 按**推荐使用的模型**做专项优化（2026-10-12，用户点名）。
    #   拼两段，各管一面（见 `llm/recommend.py` 那段说明）：
    #     ① 这一类活该怎么交代（与模型无关）；
    #     ② **这一家模型**有什么脾气（用哪家由 `llm.models.resolve()` 实时解析 ——
    #        同一位 Agent 换个模型，这一段跟着换）。
    #   ⚠ 解析不出来就**不加第二段**（宁可少叮嘱，也别按错误的模型脾气写提示词）。
    # [EN] ★★ Specialize for the **recommended model** (called out by the user on 2026-10-12).
    # [EN] Two segments are spliced, each covering one side (see the passage in `llm/recommend.py`):
    # [EN] ① how this kind of work should be briefed (model independent);
    # [EN] ② what **this model family** is like (which family is resolved live by
    # [EN] `llm.models.resolve()` -- change the model for one Agent and this segment changes too).
    # [EN] ⚠ When it can't be resolved, **don't add the second segment** (better to give fewer notes
    # [EN] than to write the prompt for the wrong model's temperament).
    tips: list[str] = []
    try:
        from llm import recommend as REC
        from llm import models as MODELS
        tips.append(REC.profile_tip(key))
        _res = MODELS.resolve(agent_key=key)
        _m = str(getattr(_res, 'model', '') or '')
        if _m:
            tips.append(REC.family_tip(_m))
    except Exception:                                            # noqa: BLE001
        tips = []
    tip_block = ('\n\n' + '\n'.join(x for x in tips if x)) if tips else ''
    return f'{HEAD}\n{body}{extra}{tip_block}'


def plain_prompt(text: str) -> str:
    """**公开名字**：剥掉给作者看的 HTML 注释，只留真正发给模型的那段正文。

    ★ 界面列表那行"提示词简略"要用它 —— 修复 `_MUTABLE` 之后 `spec.prompt`
      是**盘上那份原样**（含 `BANNER`），直接截前 52 字会给作者看一段
      `<!-- 这是本职位在**软件层**的设置…`：那不是"提示词开头"，
      而是给你看的说明（判据 `verify_agent_catalog` 的 D1b 当场抓到）。
    
        English:
    **Public name**: strip the HTML comments meant for the author, keeping only the body text
    actually sent to the model.
        ★ The "prompt summary" line in the UI list needs it —— after fixing `_MUTABLE`, `spec.prompt`
          is **the on-disk version as-is** (including `BANNER`), so naively truncating the first 52 chars would show the author
          `<!-- This is the **software-layer** setting for this job...`: that is not the "start of the prompt",
          but an explanation meant for you (criterion D1b of `verify_agent_catalog` catches it on the spot).
    """
    return _strip_html_comments(text)


def _strip_html_comments(text: str) -> str:
    """去掉 `<!-- ... -->`（**多行也算**），并把留下的空行收干净。
        English:
    Remove `<!-- ... -->` (**multi-line counts too**), and tidy up the leftover blank lines.
    """
    out = re.sub(r'<!--.*?-->', '', str(text or ''), flags=re.S)
    return re.sub(r'\n{3,}', '\n\n', out).strip()


def usage_options() -> list[str]:
    """「什么情况下使用」的常见取值（界面上的下拉候选，**不是强制**）。
        English:
    Common values for "when to use" (dropdown candidates in the UI, **not mandatory**).
    """
    return ['', '每一拍', '每天开拍前', '每天收工时', '导出时', '按需触发']


def stats() -> dict[str, int]:
    """给界面用的小结：几个内置、几个自建、几条被项目覆盖。
        English:
    A small summary for the UI: how many built-in, how many user-defined, how many overridden by the
    project.
    """
    eff = effective()
    return {'total': len(eff),
            'builtin': sum(1 for s in eff if s.builtin),
            'custom': sum(1 for s in eff if not s.builtin),
            'overridden': sum(1 for s in eff if s.overridden)}


# ══════════════════════════════════════════════════════════════════════
#  开卷那一步：让 AI 为**这一本书**推断各职位的定制
# [EN] The opening step: have the AI infer each position's customization for **this one book**
# ══════════════════════════════════════════════════════════════════════
#: 推断提示词。**只让模型写"这一本要多做什么"**，不让它重写职位定义 ——
#: 职位定义是软件的一部分，那是「天机 · 剧组 Agents」该改的东西。
# [EN] : inference prompt. **Only let the model write "what this book needs to do extra"**, don't let
# [EN] it rewrite the position definition —
# [EN] : the position definition is part of the software; that's what "Tianji · Crew Agents" should be
# [EN] changing.
INFER_PROMPT = """你是一位影视公司的制片人，正在为一部**新的小说改编项目**派活。

── 这本书 ──
项目名：{name}
类型：{genre}
风格：{style}
设定摘要：
{summary}

下面是这个剧组现有的职位（key ｜ 中文名 ｜ 职责）：
{roster}

请为**每一个**职位写一句「**这本书**要它多做什么、少做什么」（≤40 字）。
要求：
- 必须贴着这本书的**类型与风格**说具体的东西（悬疑就盯线索物与误导，
  言情就盯关系推进与情绪层次……），不要泛泛而谈；
- 写的是"这一本的侧重"，**不要**复述职责、不要改职位定义；
- 想不出这一本有什么特别的，就写空字符串 `""`（**宁可空，别凑**）。

只输出一个 JSON 对象，key 就是职位名，value 是那一句（或空串）：
{{"novelist": "…", "screenwriter": "", …}}"""


def settings_digest(settings: Any, limit: int = 1600) -> str:
    """把设定压成一段**够模型看懂这本书**的摘要（拿不到就空串）。
        English:
    Condense the setting into a summary **good enough for the model to understand this book** (empty
    string if unavailable).
    """
    try:
        from ingest.optimize import settings_summary
        return str(settings_summary(settings or {}, max_chars=limit))
    except Exception as e:                                       # noqa: BLE001
        _LOG.info('渲染设定摘要失败（推断会缺材料）：%r', e)
        return ''


async def infer_project_agents(*, name: str = '', genre: str = '',
                               style: str = '', summary: str = '',
                               keys: Iterable[str] | None = None,
                               want_keys: Iterable[str] | None = None,
                               ) -> dict[str, str]:
    """让 AI 为这本书推断各职位的项目级定制。返回 `{key: 一句话}`。

    ★ **失败一律返回空 dict**（调用方那边"没推断出来"就退回软件默认）——
      这是开卷流程里的一个可选步骤，它不该有能力把整趟摄取弄挂。
    ★ 空串/没认出来的 key 一律丢掉：「宁可空，别凑」——
      给每个职位都写一句套话，等于把软件默认冻进项目里（以后改不动了）。
    
        English:
    Have the AI infer project-level customization of each job for this book. Return `{key: one
    sentence}`.
        ★ **On any failure return an empty dict** (the caller falls back to the software default when "nothing was inferred") ——
          this is an optional step in the open-book flow; it should not be able to break the entire ingestion.
        ★ Empty strings / unrecognized keys are always dropped: "better empty than padded" ——
          writing a stock sentence for every job would freeze the software default into the project (unchangeable ever after).
    """
    want = [str(k) for k in (want_keys if want_keys is not None else
                             (keys if keys is not None else []))]
    if not want:
        return {}
    eff = {s.key: s for s in effective(project=None)}
    rows = '\n'.join(f'{k} ｜ {eff[k].name} ｜ {eff[k].intro}'
                     for k in want if k in eff)
    if not rows:
        return {}
    prompt = INFER_PROMPT.replace('{name}', name or '（未命名）') \
                         .replace('{genre}', genre or '（未判定）') \
                         .replace('{style}', style or '（未判定）') \
                         .replace('{summary}', summary or '（没有摘要）') \
                         .replace('{roster}', rows)
    try:
        from llm.replies import ask
        rep = await ask('cheap', [{'role': 'user', 'content': prompt}],
                        purpose='crew_agents_infer', want=dict, json_mode=True,
                        max_tokens=2400, temperature=0.4, default=None)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('推断 Agent 定制失败：%r', e)
        return {}
    obj = rep.value if isinstance(rep.value, dict) else None
    if not obj:
        return {}
    out: dict[str, str] = {}
    for k, v in obj.items():
        kk = str(k or '').strip()
        txt = str(v or '').strip()
        if kk in eff and txt and len(txt) <= 120:
            out[kk] = txt
    _LOG.info('Agent 定制推断：%d 个职位（请求 %d 个）', len(out), len(want))
    return out


# ══════════════════════════════════════════════════════════════════════
#  首次运行：播种 + 写对照表
# [EN] First run: seed + write the mapping table
# ══════════════════════════════════════════════════════════════════════
def upgrade_soft_templates(base: Path | None = None) -> list[str]:
    """把**没被改过**的内置样板 md 升级到当前模板。返回升级了哪些文件。

    ★ 为什么需要这一步：`seed_soft()` 是"已存在就不动"的（那是对的 ——
      作者改过的东西绝不能被覆盖）。可这样一来，**升级模板就永远到不了
      老用户盘上**：他看到的还是旧措辞，表现成"你说加了这个说明，我这没有"。

    判定"没被改过"的办法：盘上那份的**正文逐字等于上一版渲染出来的全文**
    （`BANNER_V1` + `_default_prompt_v1`）。逐字相同 ⇒ 是原样样板 ⇒ 安全升级。
    **只要作者动过一个字**（哪怕只是加了个空行），这条就不成立 ⇒ 一个字都不碰。

    ⚠ 这是本项目"不许静默覆盖用户内容"的直接推论。判据与反例法都盯着它：
      反例法会把 `BANNER_V1` 改一个字符，看"作者改过的不被覆盖"那条会不会红。
    
        English:
    Upgrade the **unmodified** built-in template md to the current template. Return which files were
    upgraded.
        ★ Why this step is needed: `seed_soft()` is "leave alone if it already exists" (which is correct ——
          what the author has modified must never be overwritten). But then **template upgrades never reach
          old users' disks**: they still see the old wording, manifesting as "you said you added this note, but I don't have it".
        The way to determine "unmodified": the **body text on disk is verbatim equal to the full text rendered by the previous version**
        (`BANNER_V1` + `_default_prompt_v1`). Verbatim equal ⇒ it is an untouched template ⇒ safe to upgrade.
        **If the author has touched a single character** (even just added a blank line), this does not hold ⇒ not a single character is touched.
        ⚠ This is a direct corollary of the project's "never silently overwrite user content". Criteria and the counterexample method both watch it:
          the counterexample method changes one character in `BANNER_V1` to see whether the "author-modified content is not overwritten" check turns red.
    """
    d = soft_dir(base)
    if not d.is_dir():
        return []
    upgraded: list[str] = []
    # ⚠ 用 `_builtin_specs()` 拿 spec（**不要**在这儿另拼一份）：
    #   它带着 `order`/`when`/`tier`/`feeds` 的**正确值** ——
    #   自己 new 一个 AgentSpec 会把 `order` 写成 0，升级完 18 个职位的顺序全乱
    #   （README 与界面的列表顺序都跟着乱，而这是"看着像小事"的那类损坏）。
    # [EN] ⚠ Use `_builtin_specs()` to get specs (**don't** assemble another copy here):
    # [EN] it carries the **correct values** for `order`/`when`/`tier`/`feeds` —
    # [EN] doing `new AgentSpec` yourself would write `order` as 0, and after upgrading the order of all 18
    # [EN] positions would be scrambled
    # [EN] (the README and the UI's list order would be scrambled too, and this is the "looks like a minor
    # [EN] thing" kind of damage).
    for spec in _builtin_specs():
        role = ROSTER.BY_KEY.get(spec.key)
        if role is None:
            continue
        p = d / f'{spec.slug}.md'
        if not p.is_file():
            continue
        try:
            cur = p.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        _meta, body = parse_md(cur)
        v1 = render_md(replace(spec, prompt=_default_prompt_v1(role, spec.name_en)),
                       banner=BANNER_V1)
        if body.strip() != parse_md(v1)[1].strip():
            continue                                    # 作者改过（或已是最新）⇒ 不动
            # [EN] Author changed it (or it's already latest) ⇒ leave it alone
        new_spec = replace(spec, prompt=_default_prompt(role, spec.name_en))
        try:
            write_spec(d, new_spec)
            upgraded.append(p.name)
            _LOG.info('样板升级：%s（原样未改，换成新模板）', p.name)
        except Exception as e:                          # noqa: BLE001
            _LOG.warning('升级 %s 失败（保持原样）：%r', p.name, e)
    return upgraded


def ensure_ready(base: Path | None = None) -> list[str]:
    """幂等：软件目录缺什么补什么（播种 + 样板升级 + README）。返回新写的文件名。
        English:
    Idempotent: fill in whatever is missing in the software directory (seeding + template upgrades +
    README). Return the names of newly written files.
    """
    wrote = seed_soft(base)
    try:
        wrote += upgrade_soft_templates(base)
    except Exception as e:                              # noqa: BLE001
        # 升级失败**不该挡住启动**（最坏是作者继续用旧样板）
        # [EN] Upgrade failure **should not block startup** (worst case the author keeps using the old
        # [EN] template)
        _LOG.warning('样板升级没跑成（继续用盘上那份）：%r', e)
    d = soft_dir(base)
    if not (d / README_NAME).exists() or wrote:
        write_readme(base)
    return wrote
