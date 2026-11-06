# -*- coding: utf-8 -*-
"""剧本式输出：渲染器与解析器（三套形态 + 一种落盘格式）。

同一份 `SceneScript` 要喂三个地方，所以有三套渲染：

| 用途 | 函数 | 特点 |
|---|---|---|
| **屏幕** | `render_blocks()` | 返回结构化块，GUI 按块上色/缩进；界面标签跟随语言 |
| **落盘** | `to_markdown()` | 「每天的生活」用。**标签固定中文**（要能被反解），人可读可改 |
| **回灌 LLM** | `to_context()` | 前情提要注入用。极紧凑，省 token |

外加 `parse_markdown()` 反向解析，用于读**旧格式 / 手改过**的文件。

为什么落盘标签固定中文而不跟随界面语言？
  因为解析要靠它做锚点。如果英文界面写 `CHARACTERS:`、中文界面写「出场」，
  解析器就得猜两种语法，而用户还可能手改文件。
  **落盘格式是数据，界面标签是表现**——两者分开，规则才简单。
  英文用户看到的界面标签仍然是英文（GUI 用 `kind` 映射 i18n 文案）。

English:
Script-style output: renderer and parser (three forms + one persistence format).
The same `SceneScript` must feed three places, so there are three renderings:
| Purpose | Function | Characteristics |
|---|---|---|
| **Screen** | `render_blocks()` | Returns structured blocks, GUI colors/indents by block; UI labels follow language |
| **Persistence** | `to_markdown()` | Used for "everyday life". **Labels fixed to Chinese** (must be parse-back-able), human-readable and editable |
| **Feed back to LLM** | `to_context()` | Used for recap injection. Extremely compact, saves tokens |
Plus `parse_markdown()` for reverse parsing, used to read **old-format / hand-edited** files.
Why is the on-disk tag fixed to Chinese and not following the UI language?
  Because parsing relies on it as an anchor. If the English UI writes `CHARACTERS:` and the Chinese UI writes 「出场」,
  the parser would have to guess two syntaxes, and users may also hand-edit the file.
  **The on-disk format is data, the UI label is presentation** — keeping them separate keeps the rules simple.
  English users still see English UI labels (the GUI maps i18n text via `kind`).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from display import script as S

# ══════════════════════════════════════════════════════════════
#  屏幕块
# [EN] Screen block
# ══════════════════════════════════════════════════════════════
# 角色（GUI 与 CLI 共用一套语义，具体颜色由界面决定）
ROLE_META = 'meta'        # 幕首元信息（时间/地点/在场）→ 最暗
ROLE_LABEL = 'label'      # 类型标签（旁白/同时/切至）
ROLE_BODY = 'body'        # 正文
ROLE_SPEECH = 'speech'    # 台词 → 最显眼
ROLE_DIR = 'dir'          # 舞台指示（出场/退场/停顿）→ 暗且斜
ROLE_TRACK = 'track'      # 并行轨
ROLE_NOTE = 'note'        # 机制标注
# [EN] Role (GUI and CLI share the same semantics; the specific colors are decided by the UI)
# [EN] Act-opening meta info (time/place/present) → darkest
# [EN] Type label (narration/simultaneous/cut-to)
# [EN] Body
# [EN] Dialogue → most prominent
# [EN] Stage direction (entrance/exit/pause) → dark and italic
# [EN] Parallel track
# [EN] Mechanism annotation
ROLE_IMAGE = 'image'
# 2026-10-06 新增的两个（用户要求输出样式要更好区分）：
#   环境白描要比正文更淡、更远；回想是暗色斜体，与「心声」的亮色斜体分开。
ROLE_AMBIENT = 'ambient'   # 环境白描 / 群像背景
ROLE_RECALL = 'recall'     # 回想 / 省思
# 2026-10-07 新增：前情提要 —— 屏幕上是**独立的块**（不是故事正文，也不是
# 「进度/张力」那种体检报告）。界面靠 role 给它单独配色/底色方块。
ROLE_RECAP = 'recap'       # 前情提要（开演前的回顾）
ROLE_BRIEF = 'brief'       # 今日剧情简介（正式剧情之前那一段）
# [EN] Two added on 2026-10-06 (user requested output styles be more distinguishable):
# [EN] Environment description should be fainter and more distant than the body; recollection is dark
# [EN] italic, separated from the bright italic of "inner voice".
# [EN] Environment description / ensemble background
# [EN] Recollection / reflection
# [EN] Added 2026-10-07: recap —— on screen it is an **independent block** (not story body, nor
# [EN] the "progress/tension" kind of health report). The UI uses role to give it its own
# [EN] color/background block.
# [EN] Recap (review before the show starts)
# [EN] Today's plot summary (the segment before the formal plot)

# 屏幕上的类型标签（中文基准；GUI 会用 i18n 再翻一次）
# [EN] Type labels on screen (Chinese baseline; GUI will translate again via i18n)
KIND_LABEL = {
    S.NARRATION: '旁白',
    S.ACTION: '动作',
    S.ASIDE: '心声',
    S.AMBIENT: '环境',
    S.RECALL: '回想',
    S.PARALLEL: '同时',
    S.CUT: '切至',
    S.CUT_BACK: '切回',
    S.EVENT: '事件',
    S.BEAT: '停顿',
    S.NOTE: '标注',
    S.IMAGE: '图',
    S.ENTER: '出场',
    S.EXIT: '退场',
    S.SCENE: '场景',
    S.TIME: '时间',
    S.RECAP: '前情提要',
    S.BRIEF: '今日剧情简介',
}


@dataclass
class Block:
    """屏幕渲染的最小单位。GUI 把每个 Block 变成一个控件。
        English:
    The smallest unit of screen rendering. The GUI turns each Block into a widget.
    """
    kind: str
    text: str
    role: str = ROLE_BODY
    indent: int = 0
    speaker: str = ''
    hint: str = ''                  # 语气/动作提示，如「压低声音」
    # [EN] Tone/action hint, e.g. "lower voice"
    visibility: str = S.PRESENT
    # 标签拆成两段：`label` 是**可翻译的基础词**（界面按语言翻），
    # `label_extra` 是动态部分（地点、事件类型），不翻译。
    # 拆开的原因：GUI 要做 i18n，而 `切至 · 城东渡口` 这种混合串没法整体查表。
    # [EN] Label split into two parts: `label` is the **translatable base word** (UI translates by
    # [EN] language),
    # [EN] `label_extra` is the dynamic part (place, event type), not translated.
    # [EN] Reason for splitting: GUI needs i18n, and mixed strings like `切至 · 城东渡口` cannot be looked up as
    # [EN] a whole.
    label: str = ''
    label_extra: str = ''
    image: str = ''
    caption: str = ''
    # 并行轨分组：同一次 parallel 的块共享 group_id，GUI 可以画成一组
    # [EN] Parallel track grouping: blocks of the same parallel share group_id, GUI can draw them as a
    # [EN] group
    group_id: int = 0
    track_index: int = 0
    track_total: int = 0
    anchors: dict[str, str] = field(default_factory=dict)

    @property
    def is_continuation(self) -> bool:
        return self.track_index > 0

    @property
    def full_label(self) -> str:
        return f'{self.label} · {self.label_extra}' if self.label_extra else self.label


def _vis_suffix(visibility: str) -> str:
    """场外/别处要在屏幕上标出来——这是「同时不同地」看得见的关键。
        English:
    Off-stage/elsewhere must be marked on screen — this is the key to making "same time, different
    place" visible.
    """
    if visibility == S.PRESENT:
        return ''
    return f'（{S.VISIBILITY_LABEL.get(visibility, visibility)}）'


def render_blocks(script: S.SceneScript) -> list[Block]:
    """把一幕渲染成屏幕块序列。
        English:
    Render one act into a sequence of screen blocks.
    """
    out: list[Block] = []

    # ── 幕首 ──
    # [EN] ── Act opening ──
    head = script.time_label or ''
    if script.place:
        head += f' · {script.place}'
    if script.weather:
        head += f' · {script.weather}'
    if head:
        meta = head
        if script.cast:
            meta += f'    在场：{"、".join(script.cast)}'
        out.append(Block(S.SCENE, meta.strip(), role=ROLE_META, indent=0))
    if script.place_desc:
        out.append(Block(S.SCENE, script.place_desc, role=ROLE_META, indent=1))
    if script.anchors:
        # 「本幕依据」：让"这段戏在推进什么"可见
        # [EN] "Basis of this act": makes "what this scene is advancing" visible
        bits = ' · '.join(f'{k} {v}' for k, v in script.anchors.items())
        out.append(Block(S.NOTE, bits, role=ROLE_NOTE, indent=0,
                         label='本幕依据'))

    group = 0
    for entry in script.entries:
        kind = entry.kind

        if kind == S.DIALOGUE:
            out.append(Block(kind, entry.text, role=ROLE_SPEECH,
                             speaker=entry.speaker,
                             hint=f'对{entry.to}' if entry.to else '',
                             visibility=entry.visibility,
                             anchors=entry.anchors))
            if entry.tone:
                out.append(Block(kind, entry.tone, role=ROLE_DIR, indent=1,
                                 speaker=entry.speaker))

        elif kind == S.ACTION:
            out.append(Block(kind, entry.text, role=ROLE_BODY, indent=1,
                             speaker=entry.speaker,
                             visibility=entry.visibility,
                             anchors=entry.anchors))

        elif kind == S.ASIDE:
            out.append(Block(kind, entry.text, role=ROLE_DIR, indent=1,
                             speaker=entry.speaker, label=KIND_LABEL[S.ASIDE]))

        elif kind == S.AMBIENT:
            out.append(Block(kind, entry.text, role=ROLE_AMBIENT, indent=1,
                             place=entry.place, anchors=entry.anchors))

        elif kind == S.RECALL:
            out.append(Block(kind, entry.text, role=ROLE_RECALL, indent=1,
                             speaker=entry.speaker,
                             label=KIND_LABEL[S.RECALL]))

        elif kind in (S.ENTER, S.EXIT):
            label = KIND_LABEL[kind]
            out.append(Block(kind, entry.text, role=ROLE_DIR, indent=0,
                             speaker=entry.speaker, label=label))

        elif kind == S.NARRATION:
            out.append(Block(kind, entry.text, role=ROLE_BODY, indent=0,
                             anchors=entry.anchors))

        elif kind == S.PARALLEL:
            group += 1
            total = len(entry.tracks)
            if not total:
                continue
            for i, tk in enumerate(entry.tracks):
                out.append(Block(kind, tk.text, role=ROLE_TRACK, indent=1,
                                 speaker=tk.subject, visibility=tk.visibility,
                                 label=KIND_LABEL[S.PARALLEL] if i == 0 else '',
                                 group_id=group, track_index=i,
                                 track_total=total, anchors=tk.anchors))

        elif kind == S.CUT:
            out.append(Block(kind, entry.text, role=ROLE_LABEL, indent=0,
                             label=KIND_LABEL[S.CUT], label_extra=entry.place))

        elif kind == S.CUT_BACK:
            out.append(Block(kind, entry.text, role=ROLE_LABEL, indent=0,
                             label=KIND_LABEL[S.CUT_BACK],
                             label_extra=entry.place))

        elif kind == S.EVENT:
            out.append(Block(kind, entry.text, role=ROLE_LABEL, indent=0,
                             label=KIND_LABEL[S.EVENT],
                             label_extra=entry.caption, anchors=entry.anchors))

        elif kind == S.BEAT:
            out.append(Block(kind, entry.text, role=ROLE_DIR, indent=0,
                             label=KIND_LABEL[S.BEAT]))

        elif kind == S.NOTE:
            # `caption` 当标签用（见 `script.note()`）—— 屏幕上显示成
            # `※ 肖像：主角 · 沈家长子`；没有标签时 GUI 兜底成「标注」。
            # [EN] `caption` used as a label (see `script.note()`) —— displayed on screen as
            out.append(Block(kind, entry.text, role=ROLE_NOTE, indent=0,
                             label=entry.caption, anchors=entry.anchors))

        elif kind == S.RECAP:
            # 前情提要：**自己一类 role**（不是 ROLE_NOTE）——「回顾」和
            # 「进度：节点完成」在屏幕上必须一眼分得开（用户 2026-10-07）。
            # [EN] Recap: **its own role category** (not ROLE_NOTE) —— "review" and
            # [EN] "progress: node complete" must be distinguishable at a glance on screen (user 2026-10-07).
            out.append(Block(kind, entry.text, role=ROLE_RECAP, indent=0,
                             label=KIND_LABEL[S.RECAP]))

        elif kind == S.BRIEF:
            # 今日剧情简介：与 RECAP **并列的另一类** —— 用户要的顺序是
            # 「前情提要 → 今日剧情简介 → 正式剧情」，两块必须分得开
            # （前情讲"前面发生了什么"，简介讲"今天要演什么"）。
            # [EN] Today's plot summary: **another category parallel** to RECAP —— the order the user wants is
            # [EN] "recap → today's plot summary → formal plot", the two blocks must be distinguishable
            # [EN] (recap tells "what happened before", summary tells "what will be performed today").
            out.append(Block(kind, entry.text, role=ROLE_BRIEF, indent=0,
                             label=KIND_LABEL[S.BRIEF]))

        elif kind == S.IMAGE:
            out.append(Block(kind, entry.text, role=ROLE_IMAGE, indent=1,
                             label=KIND_LABEL[S.IMAGE], label_extra=entry.caption,
                             image=entry.image, caption=entry.caption))

        else:      # TIME / SCENE 等出现在幕内的
        # [EN] TIME / SCENE etc. appearing within an act
            out.append(Block(kind, entry.text, role=ROLE_META, indent=0,
                             label=KIND_LABEL.get(kind, '')))

    return out


def one_line(entry: 'S.Entry') -> str:
    """把一个词条压成一行 —— 给「阅读节奏器」的显示队列用。

    显示队列是按条投递的，所以并行轨、切至这类**多行结构**在这里
    要退化成一行（屏幕上由 GUI 直接渲染 blocks，不走这条路）。
    
        English:
    Compress one entry into a single line — used by the display queue of the "reading rhythm
    device".
        The display queue delivers item by item, so **multi-line structures** like parallel tracks and cut-to
        must degrade to a single line here (on screen the GUI renders blocks directly and does not go through this path).
    """
    k = entry.kind
    if k == S.DIALOGUE:
        tone = f'（{entry.tone}）' if entry.tone else ''
        to = f'对{entry.to}' if entry.to else ''
        return f'{entry.speaker}{tone}{to}：{entry.text}'
    if k == S.ACTION:
        return f'{entry.speaker}{_vis_suffix(entry.visibility)}：{entry.text}'
    if k == S.ASIDE:
        return f'〔心声·{entry.speaker}〕{entry.text}'
    if k == S.AMBIENT:
        return f'〔环境〕{entry.text}'
    if k == S.RECALL:
        return f'〔回想·{entry.speaker}〕{entry.text}'
    if k == S.NARRATION:
        return entry.text
    if k == S.ENTER:
        return f'〔出场〕{entry.speaker}' + (f'（{entry.text}）' if entry.text else '')
    if k == S.EXIT:
        return f'〔退场〕{entry.speaker}' + (f'（{entry.text}）' if entry.text else '')
    if k == S.PARALLEL:
        inner = '；'.join(f'{t.subject}→{t.text}' for t in entry.tracks)
        return f'〔同时〕{inner}'
    if k == S.CUT:
        return f'〔切至 · {entry.place}〕{entry.text}'
    if k == S.CUT_BACK:
        return f'〔切回 · {entry.place}〕' if entry.place else '〔切回〕'
    if k == S.EVENT:
        label = f' · {entry.caption}' if entry.caption else ''
        return f'〔事件{label}〕{entry.text}'
    if k == S.BEAT:
        return f'〔{entry.text or "片刻"}〕'
    if k == S.NOTE:
        return f'※ {entry.text}'
    if k == S.RECAP:
        return f'※ {KIND_LABEL[S.RECAP]}：{entry.text}'
    if k == S.IMAGE:
        return ''                      # 图不在显示队列里滚动
        # [EN] Diagram does not scroll in the display queue
    return entry.text


def to_screen_text(script: S.SceneScript) -> str:
    """把块拼成纯文本（CLI / 测试 / 日志用；GUI 直接用 render_blocks）。

    按 `role` 分派而不是按 `kind`：同一个 kind 会出不同 role 的块
    （比如台词的「语气提示」也是 DIALOGUE kind，但要渲染成括注而不是台词）。
    
        English:
    Assemble blocks into plain text (for CLI / tests / logs; the GUI uses render_blocks directly).
        Dispatch by `role`, not by `kind`: the same kind can produce blocks with different roles
        (e.g. a line's "tone hint" is also DIALOGUE kind, but must be rendered as a parenthetical note instead of a line).
    """
    lines: list[str] = []
    for b in render_blocks(script):
        pad = '  ' * b.indent

        if b.role == ROLE_META:
            prefix = '── ' if b.indent == 0 else ''
            lines.append(f'{prefix}{b.text}')

        elif b.role == ROLE_NOTE:
            label = f'{b.full_label}：' if b.label else ''
            lines.append(f'{pad}※ {label}{b.text}')

        elif b.role == ROLE_RECAP:
            # 纯文本形态（CLI / 日志 / 测试）：给前情提要一个自己的记号 `§`，
            # 一眼看去就不会跟 `※` 的机制标注混。
            # [EN] Plain-text form (CLI / logs / tests): give recap its own marker `§`,
            # [EN] so at a glance it won't be confused with the `※` mechanism annotation.
            lines.append(f'{pad}§ {b.label}：{b.text}')

        elif b.role == ROLE_BRIEF:
            # 今日剧情简介：另一个记号 `▷`（= "接下来"）——
            # 与前情提要的 `§` 一眼分得开。
            # [EN] Today's plot summary: another marker `▷` (= "next up") ——
            # [EN] distinguishable at a glance from recap's `§`.
            lines.append(f'{pad}▷ {b.label}：{b.text}')

        elif b.role == ROLE_SPEECH:
            tone = f'（{b.hint}）' if b.hint else ''
            lines.append(f'{pad}{b.speaker}{tone}：{b.text}')

        elif b.role == ROLE_DIR:
            if b.kind == S.DIALOGUE:                 # 台词的语气/动作提示
            # [EN] Tone/action hint for dialogue
                lines.append(f'{pad}〔{b.text}〕')
            elif b.kind in (S.ENTER, S.EXIT):
                how = f'（{b.text}）' if b.text else ''
                lines.append(f'{pad}▸ {b.label} {b.speaker}{how}')
            elif b.kind == S.BEAT:
                lines.append(f'〔{b.label}{" · " + b.text if b.text else ""}〕')
            elif b.kind == S.ASIDE:
                lines.append(f'{pad}◇ {b.label}·{b.speaker}：{b.text}')
            else:
                lines.append(f'{pad}{b.text}')

        elif b.role == ROLE_TRACK:
            if b.track_index == 0:
                lines.append(f'{pad}〔{b.label}〕')
            pad2 = '  ' * (b.indent + 1)
            lines.append(f'{pad2}├ {b.speaker}{_vis_suffix(b.visibility)}'
                         f' │ {b.text}')

        elif b.role == ROLE_LABEL:
            label = b.full_label
            lines.append(f'〔{label}〕{b.text}' if b.text else f'〔{label}〕')

        elif b.role == ROLE_IMAGE:
            lines.append(f'{pad}〔{b.label}〕{b.caption}  {b.image}')

        elif b.kind == S.ACTION:
            lines.append(f'{pad}· {b.speaker}{_vis_suffix(b.visibility)}'
                         f'：{b.text}')

        else:
            lines.append(f'{pad}{b.text}')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════
#  落盘格式（Markdown，可反解）
# [EN] Persistence format (Markdown, reversible)
# ══════════════════════════════════════════════════════════════
MD_TIME = '## '
MD_PLACE = '**场景** '
MD_DESC = '**环境** '
MD_CAST = '**在场** '
MD_ANCHOR = '**依据** '
MD_CUT = '〔切至 · '
MD_CUT_BACK = '〔切回'
MD_PARALLEL = '〔同时〕'
MD_BEAT = '〔停顿〕'
MD_EVENT = '〔事件'
MD_IMAGE = '〔图〕'
MD_NOTE = '※ '
MD_ENTER = '▸ 出场 '
MD_EXIT = '▸ 退场 '
MD_ACTION = '· 动作 '
MD_ASIDE = '◇ 心声 '
MD_AMBIENT = '∿ 环境 '
MD_RECALL = '↺ 回想 '
MD_NARRATION = '> '
MD_TRACK = '- '
TRACK_SEP = '｜'          # 全角竖线，避免和 markdown 表格/普通文本冲突
# [EN] Full-width vertical bar, to avoid conflicting with markdown tables/plain text
TONE_WRAP = ('〔', '〕')


def _vis_inline(visibility: str) -> str:
    return _vis_suffix(visibility)


def to_markdown(script: S.SceneScript, *, day_header: str = '') -> str:
    """渲染成可反解的 Markdown（「每天的生活」小节用）。

    `day_header` 只有当天第一幕会传（`# 第 1 天 · 历法 · 天气` 那行由调用方给）。
    
        English:
    Render into reversibly-parseable Markdown (used by the "daily life" section).
        `day_header` is passed only on the first act of the day (the `# 第 1 天 · 历法 · 天气` line is supplied by the caller).
    """
    lines: list[str] = []
    if day_header:
        lines += [day_header, '']

    # 幕首
    # [EN] Act opening
    title = f'{script.time_label}'
    if script.title:
        title += f' · {script.title}'
    lines.append(MD_TIME + title.strip())

    if script.place:
        lines.append(MD_PLACE + script.place)
    if script.place_desc:
        desc = script.place_desc
        if script.weather:
            desc += f' · 天气 {script.weather}'
        lines.append(MD_DESC + desc)
    elif script.weather:
        lines.append(MD_DESC + f'天气 {script.weather}')
    if script.cast:
        lines.append(MD_CAST + '、'.join(script.cast))
    if script.anchors:
        lines.append(MD_ANCHOR + ' · '.join(f'{k} {v}'
                                            for k, v in script.anchors.items()))
    if lines and not lines[-1].startswith(MD_TIME):
        lines.append('')
    else:
        lines.append('')

    # 词条
    # [EN] Entry
    for e in script.entries:
        k = e.kind
        if k == S.NARRATION:
            lines.append(MD_NARRATION + e.text)
        elif k == S.DIALOGUE:
            tone = f'（{e.tone}）' if e.tone else ''
            to = f' →{e.to}' if e.to else ''
            lines.append(f'{e.speaker}{tone}{to}：{e.text}')
        elif k == S.ACTION:
            lines.append(f'{MD_ACTION}{e.speaker}{_vis_inline(e.visibility)}'
                         f'：{e.text}')
        elif k == S.ASIDE:
            lines.append(f'{MD_ASIDE}{e.speaker}：{e.text}')
        elif k == S.AMBIENT:
            lines.append(MD_AMBIENT + e.text)
        elif k == S.RECALL:
            lines.append(f'{MD_RECALL}{e.speaker}：{e.text}')
        elif k == S.ENTER:
            how = f'（{e.text}）' if e.text else ''
            lines.append(f'{MD_ENTER}{e.speaker}{how}')
        elif k == S.EXIT:
            how = f'（{e.text}）' if e.text else ''
            lines.append(f'{MD_EXIT}{e.speaker}{how}')
        elif k == S.PARALLEL:
            lines.append(MD_PARALLEL)
            for tk in e.tracks:
                lines.append(f'{MD_TRACK}{tk.subject}'
                             f'{_vis_inline(tk.visibility)}{TRACK_SEP}{tk.text}')
        elif k == S.CUT:
            # 地点与「同一时刻」这类说明用 ｜ 分隔，避免多写一行 `>` 被反解成旁白
            # [EN] Place and notes like "same moment" are separated by ｜, to avoid writing an extra line of `>`
            # [EN] that gets parsed back as narration
            if e.place and e.text:
                lines.append(f'{MD_CUT}{e.place}{TRACK_SEP}{e.text}〕')
            elif e.place:
                lines.append(f'{MD_CUT}{e.place}〕')
            else:
                lines.append(f'{MD_CUT}〕{e.text}')
        elif k == S.CUT_BACK:
            lines.append(f'{MD_CUT_BACK} · {e.place}〕' if e.place
                         else f'{MD_CUT_BACK}〕')
        elif k == S.EVENT:
            label = f' · {e.caption}' if e.caption else ''
            lines.append(f'{MD_EVENT}{label}〕{e.text}')
        elif k == S.BEAT:
            lines.append(MD_BEAT + (e.text or ''))
        elif k == S.NOTE:
            lines.append(MD_NOTE + e.text)
        elif k == S.RECAP:
            # 日档头部已经有一份 `> **前情提要** …`（`flush_daily_script` 写的）；
            # 这里再写一次是**防雷**：万一哪天 RECAP 词条进了幕里，
            # 落盘也不会丢内容（反解时按 `※` 归回标注，不损坏其余行）。
            # [EN] The daily file header already has a `> **前情提要** …` (written by `flush_daily_script`);
            # [EN] writing it again here is **defensive**: in case one day a RECAP entry gets into an act,
            # [EN] persistence won't lose content (on parse-back it returns to annotation by `※`, without
            # [EN] corrupting the other lines).
            lines.append(f'{MD_NOTE}{KIND_LABEL[S.RECAP]}：{e.text}')
        elif k == S.IMAGE:
            lines.append(f'{MD_IMAGE}{e.caption}  {e.image}'.strip())
        elif k in (S.TIME, S.SCENE):
            lines.append('> ' + e.text)
        else:
            lines.append(e.text)
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


# ── 反解 ──
# [EN] ── Parse-back ──
_RE_DIALOGUE = re.compile(r'^(?P<speaker>[^：:]{1,12}?)(?:（(?P<tone>[^）]*)）)?'
                          r'(?: →(?P<to>[^：:]+))?[：:](?P<text>.*)$')
_RE_ACTION = re.compile(r'^(?P<speaker>.+?)(?:（(?P<vis>在场|场外|别处)）)?'
                        r'[：:](?P<text>.*)$')
_RE_TRACK = re.compile(r'^(?P<subject>.+?)(?:（(?P<vis>在场|场外|别处)）)?'
                       + re.escape(TRACK_SEP) + r'(?P<text>.*)$')
_RE_ENTER = re.compile(r'^▸ 出场 (?P<name>.+?)(?:（(?P<how>.*)）)?$')
_RE_EXIT = re.compile(r'^▸ 退场 (?P<name>.+?)(?:（(?P<how>.*)）)?$')
_RE_TIME = re.compile(r'^## (?P<time>[^·]*?)(?: · (?P<title>.*))?$')
_RE_NOTE = re.compile(r'^※ (?P<text>.*)$')


def parse_markdown(text: str) -> list[S.SceneScript]:
    """把落盘文本反解成幕列表。

    这是**宽容解析**：认不出的行归到上一幕的 `> `（旁白/正文），
    所以手改过的文件也能读——只是结构信息会退化。
    
        English:
    Reverse-parse the on-disk text into a list of acts.
        This is **lenient parsing**: unrecognized lines go to the previous act's `> ` (narration/body),
        so hand-edited files can also be read — only the structural information degrades.
    """
    scripts: list[S.SceneScript] = []
    cur: S.SceneScript | None = None

    def ensure() -> S.SceneScript:
        nonlocal cur
        if cur is None:
            cur = S.SceneScript(time_label='')
            scripts.append(cur)
        return cur

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith('#'):
            if line.startswith('## '):
                m = _RE_TIME.match(line)
                cur = S.SceneScript(
                    time_label=(m.group('time') or '').strip() if m else '',
                    title=(m.group('title') or '').strip() if m else '')
                scripts.append(cur)
            # `# 第N天 · 历法 · 天气` 这类一级标题一律跳过，由调用方处理；
            # 注意 continue 要在**这一层**（早先误缩进进内层 if，
            # 结果一级标题被当成正文，凭空多出一幕）
            # [EN] note that continue must be at **this level** (earlier it was mistakenly indented into the inner
            # [EN] if,
            # [EN] resulting in the top-level heading being treated as body, conjuring an extra act out of thin
            # [EN] air)
            continue

        s = ensure()
        stripped = line.strip()

        if line.startswith(MD_PLACE):
            s.place = line[len(MD_PLACE):].strip()
        elif line.startswith(MD_DESC):
            body = line[len(MD_DESC):].strip()
            m = re.search(r' · 天气 (?P<w>.*)$', body)
            if m:
                s.weather = m.group('w').strip()
                body = body[:m.start()].strip()
            s.place_desc = body
        elif line.startswith(MD_CAST):
            s.cast = [x.strip() for x in
                      re.split(r'[、,，]', line[len(MD_CAST):]) if x.strip()]
        elif line.startswith(MD_ANCHOR):
            s.anchors = {}
            for part in line[len(MD_ANCHOR):].split(' · '):
                part = part.strip()
                if not part:
                    continue
                bits = part.split(' ', 1)
                if len(bits) == 2:
                    s.anchors[bits[0]] = bits[1]
                else:
                    s.anchors[part] = ''
        elif line.startswith(MD_PARALLEL):
            s.add(S.parallel([]))
        elif line.startswith(MD_TRACK):
            m = _RE_TRACK.match(line[len(MD_TRACK):].strip())
            if m and s.entries and s.entries[-1].kind == S.PARALLEL:
                s.entries[-1].tracks.append(S.Track(
                    subject=m.group('subject').strip(),
                    text=m.group('text').strip(),
                    visibility=_vis_to_code(m.group('vis'))))
        elif line.startswith(MD_ENTER):
            m = _RE_ENTER.match(stripped)
            if m:
                s.add(S.enter(m.group('name').strip(), (m.group('how') or '').strip()))
        elif line.startswith(MD_EXIT):
            m = _RE_EXIT.match(stripped)
            if m:
                s.add(S.exit_(m.group('name').strip(), (m.group('how') or '').strip()))
        elif line.startswith(MD_ACTION):
            m = _RE_ACTION.match(line[len(MD_ACTION):].strip())
            if m:
                s.add(S.action(m.group('speaker').strip(), m.group('text').strip(),
                               visibility=_vis_to_code(m.group('vis'))))
        elif line.startswith(MD_ASIDE):
            body = line[len(MD_ASIDE):].strip()
            who, _, what = body.partition('：')
            s.add(S.aside(who.strip(), what.strip() or body))
        elif line.startswith(MD_AMBIENT):
            s.add(S.ambient(line[len(MD_AMBIENT):].strip()))
        elif line.startswith(MD_RECALL):
            body = line[len(MD_RECALL):].strip()
            who, _, what = body.partition('：')
            s.add(S.recall(who.strip(), what.strip() or body))
        elif line.startswith(MD_NARRATION):
            s.add(S.narration(line[len(MD_NARRATION):].strip()))
        elif line.startswith(MD_NOTE):
            m = _RE_NOTE.match(line)
            s.add(S.note(m.group('text').strip() if m else line))
        elif line.startswith(MD_IMAGE):
            body = line[len(MD_IMAGE):].strip()
            cap, _, path = body.rpartition('  ')
            s.add(S.image(path.strip() or body, cap.strip()))
        elif line.startswith(MD_CUT):
            body = line[len(MD_CUT):].rstrip('〕')
            place, _, note = body.partition(TRACK_SEP)
            s.add(S.cut(place.strip(), note.strip()))
        elif line.startswith(MD_CUT_BACK):
            body = line[len(MD_CUT_BACK):].rstrip('〕')
            body = body[3:] if body.startswith(' · ') else body
            place, _, note = body.partition(TRACK_SEP)
            s.add(S.cut_back(place.strip()))
            if note.strip():
                s.add(S.note(note.strip()))
        elif line.startswith(MD_EVENT):
            body = line[len(MD_EVENT):].rstrip('〕')
            kind_name = ''
            if body.startswith(' · '):
                kind_name, _, body = body[3:].partition('〕')
            s.add(S.event(body.strip(), kind_name=kind_name.strip()))
        elif line.startswith(MD_BEAT):
            s.add(S.beat(line[len(MD_BEAT):].strip() or '片刻'))
        else:
            # 台词 / 普通正文
            # [EN] Dialogue / ordinary body
            m = _RE_DIALOGUE.match(stripped)
            if m and _looks_like_speaker(m.group('speaker')):
                s.add(S.dialogue(m.group('speaker').strip(), m.group('text').strip(),
                                 tone=(m.group('tone') or '').strip(),
                                 to=(m.group('to') or '').strip()))
            else:
                s.add(S.narration(stripped))

    # 清掉纯空的幕（只有幕首没有内容且没有幕首信息的）
    # [EN] Clear out purely empty acts (only an act opening with no content and no act-opening info)
    return [s for s in scripts
            if not s.empty or s.time_label or s.place]


# 判断「这个文件到底是不是剧本格式」的结构标记。
# `> `（旁白）故意不算——旧格式的自由文本里也可能有引用行，
# 靠它判断会把旧文件误认成剧本。
# [EN] Structural marker for determining "whether this file is actually script format".
# [EN] `> ` (narration) is deliberately not counted —— old-format free text may also have quote lines,
# [EN] relying on it would misidentify old files as scripts.
_SCRIPT_MARKERS = (
    MD_PLACE, MD_CAST, MD_ANCHOR, MD_DESC,
    MD_ENTER, MD_EXIT, MD_ACTION, MD_ASIDE, MD_NOTE, MD_BEAT,
    MD_AMBIENT, MD_RECALL,
    MD_PARALLEL, MD_CUT, MD_CUT_BACK, MD_EVENT, MD_IMAGE, MD_TRACK,
)


def looks_like_script(text: str) -> bool:
    """这份文本是不是剧本格式？

    为什么要判断：**旧格式（自由文本）的运行文件夹必须还能打开**，
    而且要以"原样纯文本"呈现——不要把一段散文硬拆成旁白/对白，
    那会把它原本的段落结构（`# 第N天`、`> 在场…`）丢掉。
    所以只有确实带结构标记的文件才走解析。
    
        English:
    Is this text in script format?
        Why judge this: **a run folder in the old format (free text) must still be openable**,
        and must be presented as "verbatim plain text" — do not force-split a piece of prose into narration/dialogue,
        So only files that actually carry structural markers go through parsing.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(mk.strip()) for mk in _SCRIPT_MARKERS):
            return True
        if stripped in (MD_PARALLEL, MD_BEAT) or stripped.startswith(MD_CUT_BACK):
            return True
    return False


def _vis_to_code(label: str | None) -> str:
    if not label:
        return S.PRESENT
    for code, text in S.VISIBILITY_LABEL.items():
        if text == label:
            return code
    return S.PRESENT


def _looks_like_speaker(name: str) -> bool:
    """判断「冒号前」那段是人名还是正文。

    人名短、不含标点；正文往往长或带标点。宽松一点没关系——
    误判成台词的代价是排版，误判成旁白的代价是主语丢失，后者更糟。
    
        English:
    Determine whether the segment "before the colon" is a character name or body text.
        Character names are short and contain no punctuation; body text tends to be long or contain punctuation. Being lenient is fine —
        the cost of misjudging as dialogue is layout, the cost of misjudging as narration is losing the subject, the latter is worse.
    """
    name = name.strip()
    if not name or len(name) > 12:
        return False
    return not re.search(r'[，。！？；、…—「」《》]', name)


# ══════════════════════════════════════════════════════════════
#  给 LLM 的回灌格式（紧凑）
# [EN] Feed-back format for LLM (compact)
# ══════════════════════════════════════════════════════════════
def to_context(script: S.SceneScript) -> str:
    """紧凑回灌（前情提要 / 上下文注入）。

    比 Markdown 短一半以上：去掉空行、标记压缩、可省掉舞台指示
    （LLM 续写时最需要的是"发生了什么"和"谁说了什么"）。
    
        English:
    Compact re-injection (recap / context injection).
        More than half shorter than Markdown: remove blank lines, compress markers, may omit stage directions
        (what the LLM most needs when continuing is "what happened" and "who said what").
    """
    lines: list[str] = []
    head = f'第{script.day}天 {script.time_label}'
    if script.place:
        head += f' {script.place}'
    if script.weather:
        head += f'（{script.weather}）'
    if script.node:
        head += f' — 节点{script.node}{script.node_name}'
    if script.tension_after:
        head += f' 张力{script.tension_before:.2f}→{script.tension_after:.2f}'
    lines.append(head)

    for e in script.entries:
        k = e.kind
        if k == S.DIALOGUE:
            lines.append(f'{e.speaker}：{e.text}')
        elif k == S.ACTION:
            lines.append(f'{e.speaker}[动作]{_vis_inline(e.visibility)}：{e.text}')
        elif k == S.ASIDE:
            lines.append(f'[{e.speaker}心声] {e.text}')
        elif k == S.NARRATION:
            lines.append(e.text)
        elif k == S.PARALLEL:
            inner = '；'.join(f'{t.subject}→{t.text}' for t in e.tracks)
            lines.append(f'〔同时〕{inner}')
        elif k == S.CUT:
            lines.append(f'〔切至{e.place}·同一时刻〕')
        elif k == S.CUT_BACK:
            lines.append(f'〔切回{("·" + e.place) if e.place else ""}〕')
        elif k == S.EVENT:
            lines.append(f'〔事件{"·" + e.caption if e.caption else ""}〕{e.text}')
        elif k in (S.ENTER, S.EXIT):
            verb = '出场' if k == S.ENTER else '退场'
            lines.append(f'〔{verb}〕{e.speaker}{f"（{e.text}）" if e.text else ""}')
        elif k == S.IMAGE:
            continue                     # 回灌不需要图片路径
            # [EN] Feed-back does not need image paths
        elif k == S.NOTE:
            lines.append(f'※{e.text}')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════
#  JSON 边车（无损往返）
# [EN] JSON sidecar (lossless round-trip)
# ══════════════════════════════════════════════════════════════
def to_json(scripts: list[S.SceneScript]) -> str:
    """落盘用 JSON 边车：Markdown 给人看，JSON 给机器看（无损）。
        English:
    On-disk storage uses a JSON sidecar: Markdown for humans, JSON for machines (lossless).
    """
    return json.dumps([s.to_dict() for s in scripts], ensure_ascii=False, indent=1)


def from_json(text: str) -> list[S.SceneScript]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [S.SceneScript.from_dict(d) for d in data if isinstance(d, dict)]


# ══════════════════════════════════════════════════════════════
#  统计（供界面显示「这一节有多少对白/动作」）
# [EN] Statistics (for UI to show "how many dialogue/action pairs this section has")
# ══════════════════════════════════════════════════════════════
def stats(scripts: list[S.SceneScript]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for s in scripts:
        for e in s.entries:
            counts[e.kind] = counts.get(e.kind, 0) + 1
    return {
        '幕数': len(scripts),
        '对白': counts.get(S.DIALOGUE, 0),
        '动作': counts.get(S.ACTION, 0),
        '旁白': counts.get(S.NARRATION, 0),
        '同时': counts.get(S.PARALLEL, 0),
        '切至': counts.get(S.CUT, 0),
        '出场': counts.get(S.ENTER, 0),
        '退场': counts.get(S.EXIT, 0),
        '事件': counts.get(S.EVENT, 0),
        '插图': counts.get(S.IMAGE, 0),
    }
