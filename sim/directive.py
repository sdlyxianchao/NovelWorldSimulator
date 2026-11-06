# -*- coding: utf-8 -*-
"""**作者对本轮走向的建议** —— 「起笔」对话框里那一栏。

用户 2026-10-11 的原话（这就是本模块的全部规格）：

    「我希望在起笔的时候，可以有一个地方加上用户自己对于故事接下来走向的建议。
      我觉得可以在提笔的前情提要的下面……然后在下面加上"您对接下来剧情发展的建议"
      这个文本框。而且请确保这里的前情提要和后续运行窗口对话显示的时候给的前情提要一样。」

## 它存在哪

**挂在 `world` 对象上**（`world.user_directive`），与风格控制那几项
（`world.angst_level` / `world.pacing_style`）同一套做法。三个理由：

1. **生命周期天然对**：它是"**这一轮**怎么走"，跟着这一轮的世界走 ——
   这一轮结束（`world` 被丢掉）它就没了，不会像进程级全局量那样
   偷偷漏进下一轮、或者漏进开卷 / 帮助问答那些**根本不属于推演**的调用。
2. **注入点是现成的**：`crew/agents.craft_block()` 已经从这个世界对象上取
   项目档 / 风格自定义 / 本幕提示（`_CURRENT_WORLD`），而它正是
   **全剧组 14 个职位 ＋ 演员 ＋ 导演**唯一的提示词拼装口
   （见那边的说明：`craft_block` 一处接上，十四个职位同时拿到）。
3. **不牵动存盘格式**：像 `world.relations` 一样挂实例属性，不进 dataclass schema。

⚠ 一处**刻意不做**的事：**不许**并进 `worldview_text`。
  那是"这本书是什么样"（设定），而作者的建议是"这一轮往哪走"（意图）。
  混在一起之后，下一轮 / 下一次开卷都会带着上一轮的建议 —— 那是**静默的错误**。

## 空的时候必须"逐字退回"

没填（或填了空白）时，`block()` / `line()` 都返回**空串**，提示词里
**一个字都不多**（判据 B4 钉着这条：不填建议时，拼出来的 craft 块与以前逐字相同）。
"没人填就别加戏"—— 这也是本项目对"静默改行为"的一贯态度。

English:
**The author's suggestion for this round's direction** -- that field in the "start writing"
dialog.
User's original words on 2026-10-11 (this is the entire spec for this module):
    "I hope that when starting to write, there can be a place to add the user's own suggestion for where the story goes next.
      I think it can go below the previous-context recap when starting to write... then below that add the text box
      "your suggestion for the next plot development." And please make sure the previous-context recap here is the same as the one shown in the subsequent running-window dialogue."
## Where it lives
**Attached to the `world` object** (`world.user_directive`), same approach as the style-control
items
(`world.angst_level` / `world.pacing_style`). Three reasons:
1. **Lifecycle is naturally right**: it is "how **this round** goes", and it follows this round's world --
   when this round ends (`world` is discarded) it is gone, and it will not, like a process-level global,
   silently leak into the next round, or leak into opening / help Q&A calls that **do not belong to simulation at all**.
2. **The injection point already exists**: `crew/agents.craft_block()` already takes from this world object
   the project profile / style customization / current-act hint (`_CURRENT_WORLD`), and it is exactly
   the sole prompt-assembly point for **all 14 crew positions + actors + director**
   (see the notes there: hook up `craft_block` in one place, and all fourteen positions get it at once).
3. **Does not touch the save format**: attach it as an instance attribute like `world.relations`, not into the dataclass schema.
⚠ One thing **deliberately not done**: **do not** merge it into `worldview_text`.
  That is "what this book is like" (setting), whereas the author's suggestion is "where this round goes" (intent).
  Mixed together, the next round / next opening would all carry the previous round's suggestion -- that is a **silent error**.
## When empty it must "fall back verbatim"
When unfilled (or filled with whitespace), both `block()` / `line()` return an **empty string**,
and the prompt has
**not one extra character** (criterion B4 pins this down: when no suggestion is filled, the
assembled craft block is verbatim identical to before).
"If nobody filled it, don't add drama" -- this is also the project's consistent stance on
"silently changing behavior".
"""
from __future__ import annotations

#: 挂在 `world` 上的属性名（**只在这里写一次** —— 别处用 `ATTR` 或下面几个函数）
# [EN] : The attribute name attached to `world` (**write it only here** -- elsewhere use `ATTR` or the
# [EN] functions below)
ATTR = 'user_directive'

#: 给模型看的那一段的**前缀**（判据按它找"进没进提示词"）。
# [EN] : The **prefix** of the segment shown to the model (the criterion uses it to find "whether it
# [EN] entered the prompt").
PROMPT_HEAD = '【作者对这一轮的走向要求】'

#: 开场卡片上那一行的前缀（给人看的，走 i18n）。
# [EN] : The prefix of that line on the opening card (for humans, goes through i18n).
LINE_HEAD = '作者对本轮走向的要求'

#: 长度上限（字符）。作者写多长都行，但塞进**每一拍每个人的提示词**里，
#: 太长会把这一轮的开销抬起来 —— 超了就截断，并在提示词里**说明截断了**
#: （不说的话，模型读到半句会当成写完了）。
# [EN] : Length cap (characters). The author can write any length, but it gets stuffed into **every
# [EN] character's prompt at every beat**,
# [EN] : too long and it raises the cost of this round -- truncate when over, and **state in the prompt
# [EN] that it was truncated**
# [EN] : (otherwise the model reads half a sentence and treats it as finished).
MAX_CHARS = 600


def attach(world, text: str | None) -> str:
    """把作者的建议挂到这一轮的世界对象上。返回**规范化之后**的值。

    ⚠ 规范化就三件：去首尾空白、把整段里的换行收成单个（提示词段落里
      换行多了会把后面的材料挤散）、超长截断。**不改一个字的内容**。
    
        English:
    Attach the author's suggestion to this round's world object. Return the **normalized** value.
        ⚠ Normalization is just three things: strip leading/trailing whitespace, collapse newlines in the whole
          segment into single ones (too many newlines in a prompt paragraph scatter the following material),
        and cap overlong text. **Do not change one character of the content**.
    """
    v = norm(text)
    try:
        setattr(world, ATTR, v)
    except Exception:                                            # noqa: BLE001
        pass
    return v


def norm(text: str | None) -> str:
    """去空白 / 收换行 / 截断（**空 → 空串**，调用方按空串判"没填"）。
        English:
    Strip whitespace / collapse newlines / truncate (**empty -> empty string**; the caller treats an
    empty string as "unfilled").
    """
    s = str(text or '')
    s = '\n'.join(x.strip() for x in s.splitlines() if x.strip())
    s = ' '.join(s.split())
    if len(s) > MAX_CHARS:
        s = s[:max(1, MAX_CHARS - 1)].rstrip('，。；、 ') + '…'
    return s


def of(world) -> str:
    """这一轮的作者建议（没挂上 / 没填 → 空串）。
        English:
    This round's author suggestion (not attached / not filled -> empty string).
    """
    if world is None:
        return ''
    return str(getattr(world, ATTR, '') or '')


def block(world) -> str:
    """给模型的那一段。**没填就返回空串**（调用方直接不拼这一节）。
        English:
    The segment for the model. **Return an empty string if unfilled** (the caller just does not
    assemble this section).
    """
    s = of(world)
    if not s:
        return ''
    return (
        f'{PROMPT_HEAD}（作者本人填在「起笔」对话框里，**只对当前这一轮有效**）\n'
        f'{s}\n'
        '> 往这个方向使劲：该铺的时候铺、该收的时候收，别硬塞。\n'
        '> 它是**意图**，不是设定 —— 人物是什么样、已经发生过的事、世界的规矩\n'
        '> 照旧一条都不能违背。'
    )


def line(world) -> str:
    """开场卡片上那一行（给人看的）。没填就没有这一行。
        English:
    That line on the opening card (for humans). If unfilled, there is no such line.
    """
    return line_from(of(world))


def line_from(text: str | None) -> str:
    """同上，但直接吃**已经取出来的**那段文本。

    ★ 为什么要两个入口：`sim/opening.render_md()` 手上只有 `collect()` 备好的
      那个 dict（`op['directive']`），拿不到 world 了。从 `of(world)` 里
      **再取一次**会让"显示的那份"与"喂给模型的那份"可能来自不同的读取时刻 ——
      一处取、两处用，才是本项目那条老规矩。
    
        English:
    Same as above, but directly takes the **already-fetched** text segment.
        ★ Why two entry points: `sim/opening.render_md()` only has the
          dict prepared by `collect()` (`op['directive']`) on hand, and can no longer get the world. From `of(world)`
          **fetching again** would let "the displayed copy" and "the copy fed to the model" possibly come from different read moments --
          fetch in one place, use in two, is that old rule of this project.
    """
    from i18n import t
    s = norm(text)
    if not s:
        return ''
    return t('{head}：{text}', head=t(LINE_HEAD), text=s)
