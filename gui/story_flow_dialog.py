# -*- coding: utf-8 -*-
"""「剧情总览」对话框的**内容**（纯控件，不碰页面、不读盘）。

为什么单独一个文件而不是塞进 `app_flet.py`：
  · `app_flet.py` 已经 3.5 万行 / 2.3MB，任何一次编辑都在赌"没切错段"；
  · 这里的输入只有一份 `剧情总览` 字典 + 一个样式表 ⇒ **可以在判据里直接调用**，
    不必起一个真窗口（本项目"夹具里自己画一遍控件"吃过亏：测的是夹具，不是产品）。
  ⚠ 因此本模块**只依赖 `flet` 与 `i18n`**，绝不 import `app_flet`（会循环导入）。
    颜色/字体由调用方通过 `FlowStyle` 传进来。

图形：**从上往下的流程图**
```
 ●   入楼收留                       第 1 天 · 10 幕
 │   阿九在淄川街头醒来……
 ↓
 ▶   金华旧账                       正在演
 │   …
 ↓
 ◆   开庭抉择                       选择点
 │   [归籍] [祭献] [留门]   ← 点一条，从这里往下看
```
★ 竖线/箭头用 `Container` 画的**线段**，不用 `│`/`↓` 字符：
  字符的行高与基线由字体决定（这台机器装着整族思源宋体），换字号就会断成一截一截
  —— 跑马灯那两个三角当初就是因为这个才改成矢量图标。

English:
Content of the "Story overview" dialog (pure controls; no page access, no disk reads).
Why a separate file: `app_flet.py` is already 35k lines / 2.3 MB and every edit gambles on "did I cut
a block wrong"; and with only a dict + a style table as input, **the criteria can call this
directly** without a real window (this project got burned by fixtures that redrew the controls
themselves -- measuring the fixture, not the product). So this module depends on **flet and i18n
only** and never imports `app_flet` (circular). Drawing: a **top-down flowchart**. The vertical lines
and arrows are `Container` **line segments**, not `│`/`↓` characters: glyph height and baseline follow
the font, and at another size they break into pieces -- exactly why the carousel triangles became
vector icons.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import flet as ft

from i18n import t
from plot import flow as PF

#: 左侧竖排轨道宽（点 + 线都在这条里居中）。
# [EN] Width of the left rail (dot and line are centred in it).
RAIL_W = 22
#: 圆点直径。
# [EN] Dot diameter.
DOT = 10
#: 两点之间那段竖线的高度。
# [EN] Height of the vertical line between two dots.
CONN_H = 12
#: 线段粗细。
# [EN] Line thickness.
LINE_W = 1.4


@dataclass
class FlowStyle:
    """画这张图需要的那点样式（由 `app_flet` 按当前主题填）。

    ★ 收成一个参数而不是从 `app_flet` import 常量：本模块要在判据里裸调，
      那时 `app_flet` 里的 `C` / `UI_FONT` 也许还没准备好（它是按配置算的）。
    [EN] The handful of style values this chart needs (filled by `app_flet` from the live theme).
    ★ Passed in rather than imported: the criteria call this module bare, and `C` / `UI_FONT` may
    not be resolved yet (they are computed from config).
    """
    font: str = ''
    color: dict = field(default_factory=dict)
    body_fs: float = 14.0
    hint_fs: float = 13.5
    paper: str = '#fdfaf2'


# ── 状态 → (圆点/标题色, 标签) ──────────────────────────────────────
# [EN] State -> (dot/title colour, label)
def _state_look(state: str, c: dict) -> tuple[str, str]:
    if state == PF.STATE_DONE:
        return c.get('gold', '#a8781f'), t('已演过')
    if state == PF.STATE_NOW:
        return c.get('accent', '#2f7fb0'), t('正在演')
    return c.get('muted', '#6a6f78'), t('还没演到')


def _dot(point: dict, st: FlowStyle) -> ft.Control:
    """轨道上的那个点：实心（演过）/ 空心带色环（正在演）/ 灰空心（没演到）/ 方块（选择点）。

    ★ 选择点用**方块**不是另一个字符：形状本身就在说"这里不是普通一站"，
      而且不需要用户再学一套记号（圆形那三种含义已经够记了）。
    [EN] The dot: filled (played) / ringed (playing now) / grey hollow (not yet) / square (choice).
    ★ Choice uses a **square**, not another glyph: the shape itself says "this is not an ordinary
    station", with no new notation to learn.
    """
    c = st.color
    col, _lab = _state_look(point.get('state', ''), c)
    if point.get('kind') == 'choice':
        return ft.Container(width=DOT, height=DOT, bgcolor=c.get('seal', '#c02c22'),
                            border_radius=1.5)
    if point.get('state') == PF.STATE_DONE:
        return ft.Container(width=DOT, height=DOT, bgcolor=col, border_radius=DOT / 2)
    if point.get('state') == PF.STATE_NOW:
        return ft.Container(width=DOT, height=DOT, bgcolor=c.get('panel', '#fdfaf2'),
                            border=_border(2, col), border_radius=DOT / 2)
    return ft.Container(width=DOT - 2, height=DOT - 2, bgcolor=None,
                        border=_border(1.2, col), border_radius=DOT / 2)


def _border(w: float, color: str):
    return ft.Border(left=ft.BorderSide(w, color), top=ft.BorderSide(w, color),
                     right=ft.BorderSide(w, color), bottom=ft.BorderSide(w, color))


def _pad(l: float, tp: float, r: float, b: float):
    return ft.Padding(l, tp, r, b)


def detail_text(point: dict) -> str:
    """这一站的实据，说人话：「第 1 天 · 3 幕」/「第 1–2 天 · 7 幕」。

    ★ 数据里存的是**数字**（`days` / `scenes`），句子在这里拼 —— 这样切英文时
      它跟着变（把中文句子写进 `剧情总览.json` 就是"语言被冻进盘里"）。
    ★ 三种情形各有各的话，**不许合并**：
      · 演过 → 天号 + 幕数（可核对）；
      · 没演过、但设定集标了已完成 → 明说"这次推演没演到"（否则读者以为演过）；
      · 其它 → 空串（别再写一遍"还没演到"，左边已经有状态标签了）。
    [EN] The evidence for this station, in words: "day 1 · 3 scenes" / "days 1-2 · 7 scenes".
    ★ The data holds **numbers**; the sentence is assembled here so it follows the UI language.
    ★ Three cases, never merged: played -> day numbers + scene count (checkable); unplayed but marked
    done -> say "this run never played it" (otherwise the reader assumes it was played); otherwise
    empty (the state tag already says "not yet").
    """
    if not point.get('played'):
        return t('设定集标为已完成（这次推演没演到）') if point.get('unplayed_done') else ''
    ds = [int(d) for d in (point.get('days') or [])]
    n = int(point.get('scenes') or 0)
    if not ds:
        return ''
    span = (t('第 {d} 天', d=ds[0]) if len(ds) == 1
            else t('第 {a}–{b} 天', a=ds[0], b=ds[-1]))
    return t('{span} · {n} 幕', span=span, n=n)


def tail_text(flow: dict) -> str:
    """结尾那句说明（`tail` 是**代码**不是句子，理由同上）。"""
    tail = str((flow or {}).get('tail') or '')
    if tail == 'no_table':
        return t('设定集里还没有「故事进度.yaml」，所以这张图只有演过的正文，没有情节骨架。')
    if tail == 'nothing_played':
        return t('这次推演还没演到任何一站。')
    return ''


def stats_line(flow: dict) -> str:
    """「第 1 天 · 12 幕 · 演过 2/8 站」——一句能核对的话。"""
    s = (flow or {}).get('stats') or {}
    days = int(s.get('days') or 0)
    scenes = int(s.get('scenes') or 0)
    played = int(s.get('played') or 0)
    total = int(s.get('points') or 0)
    if not days:
        return t('这次推演还没有落盘的戏')
    return t('第 {d} 天 · {n} 幕 · 演过 {p}/{q} 站',
             d=days, n=scenes, p=played, q=total)


def _option_chip(point: dict, opt: dict, *, picked: str, st: FlowStyle,
                 on_pick: Callable[[str, str], None] | None) -> ft.Control:
    """一条选项（可点）。选中 = 朱砂底白字；未选 = 纸色底描金边。"""
    c = st.color
    label = str(opt.get('label') or '')
    on = bool(picked) and picked == label
    has_next = bool(opt.get('points'))
    tip = (t('这条线后面还有 {n} 个情节', n=len(opt['points'])) if has_next
           else t('点这条，从它往下看（这条后面的事还没演到）'))

    def _tap(e, _lb=label):
        if on_pick:
            # 再点一次 = 取消（不然选错了没有回头路）。
            # [EN] Clicking the picked one again clears it (no dead end if you misclick).
            on_pick(str(point.get('pid') or ''), '' if on else _lb)

    return ft.Container(
        content=ft.Text(label, size=st.hint_fs, font_family=st.font,
                        color=(c.get('panel', '#fdfaf2') if on else c.get('text', '#232830')),
                        no_wrap=True),
        bgcolor=(c.get('seal', '#c02c22') if on else c.get('paper_hi', '#fffdf6')),
        border=_border(1, (c.get('seal', '#c02c22') if on else c.get('border', '#d9c9a3'))),
        border_radius=9,
        padding=_pad(9, 3, 9, 3),
        ink=True,
        tooltip=tip,
        on_click=_tap,
    )


def _branch_rows(point: dict, picked: str, st: FlowStyle) -> list[ft.Control]:
    """选中那条线**后面**的情节（数据里没有就什么都不画）。

    ⚠ 一条都没有时**不许编**。这里返回空表，由 `_choice_block` 补一句
      "这条后面的事还没演到" —— 那句是**说明**，不是情节。
    [EN] What follows the picked line (nothing when the data has none). ⚠ Never invent: return empty
    and let `_choice_block` add "what follows this line hasn't been played yet" -- that is an
    explanation, not a plot point.
    """
    pts = PF.branch_points_of(point, picked)
    c = st.color
    out: list[ft.Control] = []
    for i, p in enumerate(pts, 1):
        title = str(p.get('名称') or p.get('title') or '')
        summ = str(p.get('概要') or p.get('summary') or '')
        out.append(ft.Container(
            content=ft.Column([
                ft.Text(f'{i}. {title}', size=st.hint_fs, font_family=st.font,
                        color=c.get('text', '#232830'), no_wrap=True),
                ft.Text(summ, size=st.hint_fs - 1, font_family=st.font,
                        color=c.get('muted', '#6a6f78'), max_lines=3),
            ], spacing=1, tight=True),
            margin=_pad(14, 2, 0, 0),
            padding=_pad(8, 4, 8, 4),
            bgcolor=c.get('hover', '#f5ecd8'),
            border_radius=4,
        ))
    return out


def _choice_block(point: dict, *, picked: str, st: FlowStyle,
                  on_pick) -> list[ft.Control]:
    """选择点下面那一块：多选 + 选完之后那句"从这里继续"。"""
    c = st.color
    opts = point.get('options') or []
    chips = [_option_chip(point, o, picked=picked, st=st, on_pick=on_pick) for o in opts]
    out: list[ft.Control] = [
        ft.Row(chips, spacing=6, wrap=True, tight=True),
    ]
    if point.get('options_inferred'):
        out.append(ft.Text(
            t('（这几条是从概要里读出来的；想改就在设定的「故事进度」里给这一站加「选项:」）'),
            size=st.hint_fs - 1.5, font_family=st.font, color=c.get('muted', '#6a6f78')))
    if picked:
        out.append(ft.Row([
            ft.Icon(ft.Icons.SUBDIRECTORY_ARROW_RIGHT, size=st.hint_fs,
                    color=c.get('seal', '#c02c22')),
            ft.Text(t('沿「{x}」这条线往下看', x=picked), size=st.hint_fs,
                    font_family=st.font, color=c.get('text', '#232830')),
        ], spacing=4, tight=True))
        br = _branch_rows(point, picked, st)
        if br:
            out.extend(br)
        else:
            out.append(ft.Text(t('（这条线后面的事还没演到）'), size=st.hint_fs - 1,
                               font_family=st.font, color=c.get('muted', '#6a6f78')))
    else:
        out.append(ft.Text(t('点一条，从这里往下看'), size=st.hint_fs - 1,
                           font_family=st.font, color=c.get('muted', '#6a6f78')))
    return out


def _point_card(point: dict, *, picks: dict, st: FlowStyle, on_pick) -> ft.Control:
    """一张情节卡：标题 + 状态 + 实据 + 三两行概要（+ 选择点的选项）。"""
    c = st.color
    col, label = _state_look(point.get('state', ''), c)
    pid = str(point.get('pid') or '')
    title = str(point.get('title') or '')
    detail = detail_text(point)
    is_choice = point.get('kind') == 'choice'

    head = ft.Row([
        ft.Text(title, size=st.body_fs, font_family=st.font, color=col,
                weight=ft.FontWeight.BOLD, no_wrap=True),
        ft.Text(('· ' + label) if not is_choice else ('· ' + t('要你选')),
                size=st.hint_fs - 1, font_family=st.font,
                color=(c.get('seal', '#c02c22') if is_choice else col)),
        ft.Container(expand=True),
        ft.Text(detail, size=st.hint_fs - 1.5, font_family=st.font,
                color=c.get('muted', '#6a6f78'), no_wrap=True),
    ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    body: list[ft.Control] = [head]
    if point.get('summary'):
        body.append(ft.Text(str(point['summary']), size=st.hint_fs, font_family=st.font,
                            color=c.get('muted', '#6a6f78'), max_lines=3))
    if is_choice:
        # ⚠ 直接用 `picks[pid]`，不绕 `PF.pick_of`：这里手上就是一份 `{pid: label}`，
        #   为了调一个"从 flow 里取"的函数去伪造一个 flow，是给自己埋"两份数据"的雷。
        # [EN] Use `picks[pid]` directly instead of `PF.pick_of`: what we hold IS `{pid: label}`;
        # fabricating a flow just to call the getter plants a "two copies of the data" bug.
        body.extend(_choice_block(point, picked=str(picks.get(pid) or ''),
                                  st=st, on_pick=on_pick))

    return ft.Container(
        content=ft.Column(body, spacing=3, tight=True),
        expand=True,
        padding=_pad(10, 7, 10, 7),
        bgcolor=(c.get('hover', '#f5ecd8') if point.get('state') == PF.STATE_NOW else None),
        border=_border(1, (c.get('accent', '#2f7fb0')
                           if point.get('state') == PF.STATE_NOW else c.get('border', '#d9c9a3'))),
        border_radius=5,
    )


def _connector(st: FlowStyle) -> ft.Control:
    """两个点之间那段竖线（`↓` 是靠形状，不是靠字符）。"""
    c = st.color
    return ft.Row([
        ft.Container(
            width=RAIL_W,
            height=CONN_H,
            alignment=ft.Alignment(0, 0),
            content=ft.Container(width=LINE_W, height=CONN_H,
                                 bgcolor=c.get('border_gold', '#c9a24e')),
        ),
    ], spacing=0, tight=True)


def build_flow_controls(flow: dict, *, style: FlowStyle, picks: dict | None = None,
                        on_pick=None) -> list[ft.Control]:
    """把一份剧情总览画成**从上往下**的流程图（返回一串控件，由调用方塞进对话框）。

    :param flow: `plot.flow.build_flow` 的结果（或盘上读回来的同一形状）
    :param style: 颜色/字号（由 `app_flet` 按当前主题填）
    :param picks: `{pid: label}`；不给就用 `flow['picks']`
    :param on_pick: `(pid, label)` 回调；`label` 为空 = 取消选择
    """
    st = style
    c = st.color
    picks = dict(flow.get('picks') or {}) if picks is None else dict(picks)
    out: list[ft.Control] = []

    syn = str(flow.get('synopsis') or '').strip()
    if syn:
        out.append(ft.Container(
            content=ft.Column([
                ft.Text(t('故事线'), size=st.hint_fs - 0.5, font_family=st.font,
                        color=c.get('gold', '#a8781f'), weight=ft.FontWeight.BOLD),
                ft.Text(syn, size=st.hint_fs, font_family=st.font,
                        color=c.get('text', '#232830'), max_lines=6),
            ], spacing=2, tight=True),
            padding=_pad(10, 8, 10, 8),
            bgcolor=c.get('paper_hi', '#fffdf6'),
            border=_border(1, c.get('border', '#d9c9a3')),
            border_radius=5,
        ))
        out.append(ft.Container(height=6))

    out.append(ft.Text(t('情节流程（从上往下）'), size=st.hint_fs - 0.5, font_family=st.font,
                       color=c.get('gold', '#a8781f'), weight=ft.FontWeight.BOLD))
    out.append(ft.Container(height=2))

    points = flow.get('points') or []
    if not points:
        out.append(ft.Text(t('设定集里还没有情节表。'), size=st.hint_fs, font_family=st.font,
                           color=c.get('muted', '#6a6f78')))
    for i, p in enumerate(points):
        out.append(ft.Row([
            ft.Container(width=RAIL_W, height=22, alignment=ft.Alignment(0, 0),
                         content=_dot(p, st)),
            _point_card(p, picks=picks, st=st, on_pick=on_pick),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.START))
        if i < len(points) - 1:
            out.append(_connector(st))

    tail = tail_text(flow)
    if tail:
        out.append(ft.Container(height=4))
        out.append(ft.Text(tail, size=st.hint_fs, font_family=st.font,
                           color=c.get('muted', '#6a6f78')))
    return out


def build_empty_controls(message: str, *, style: FlowStyle) -> list[ft.Control]:
    """一个推演都没有 / 读不出情节时的那句话（**不留白屏**）。"""
    return [ft.Text(str(message or ''), size=style.hint_fs, font_family=style.font,
                    color=style.color.get('muted', '#6a6f78'))]


# ══════════════════════════════════════════════════════════════
#  详细剧情：剧作家的分拍 + 正文 + 关键剧情与转折点
# [EN] Detailed story: the playwright's beats + prose + key beats and turning points
# ══════════════════════════════════════════════════════════════
#: 转折点的 `caption` 是**闭集**（`director/engine.py` 的 `event_type` +
#: 代码里硬给的「导演自救」）。做成表是为了：①英文界面翻得出来；
#: ②以后加一类事件只改这里一处 —— 散在界面里判断字符串，迟早有一处忘了翻。
# [EN] Turning-point captions are a **closed set** (`event_type` in `director/engine.py` plus the
# [EN] hard-coded 「导演自救」). A table so that ① English can translate them and ② adding a kind
# [EN] means editing one place -- scattered string checks would eventually miss one.
CAPTION_KEYS = ('外部刺激', '人物冲突', '巧合', '秘密泄露', '伏笔激活', '导演自救')


def mark_label(mark: dict) -> str:
    """一条标记前面那个词：转折 / 关键 + （事件类别）。"""
    kind = str((mark or {}).get('kind') or '')
    cap = str((mark or {}).get('caption') or '').strip()
    head = t('转折') if kind == PF.MARK_TURN else t('关键')
    if cap:
        return f'{head} · {t(cap)}' if cap in CAPTION_KEYS else f'{head} · {cap}'
    return head


def mark_text(mark: dict) -> str:
    """一条标记的正文。

    ★★ 三种标记的文字**在这里拼**，不在数据层拼（`plot.flow` 只给代码与参数）。
      理由：`剧情总览.json` 会被英文界面读 —— 把「换场：甲 → 乙」写进盘里，
      切英文之后这行还是中文（上一轮 `detail` / `tail` 就栽在这上面）。
    ★ `event` 例外：它的 `text` 是**导演写的原文**（素材），照原样显示，不翻译 ——
      翻译素材等于改写了这个故事。
    [EN] The body of one mark. ★★ All three kinds are assembled **here**, not in the data layer
    (`plot.flow` only emits codes and parameters): `剧情总览.json` is read by the English UI, and a
    baked-in "change of place: A -> B" stays Chinese after switching languages -- exactly what
    `detail` / `tail` did last round. ★ `event` is the exception: its `text` is **the director's own
    wording** (source material) and is shown verbatim -- translating material rewrites the story.
    """
    why = str((mark or {}).get('why') or '')
    if why == 'place':
        return t('换场：{a} → {b}', a=str(mark.get('a') or ''), b=str(mark.get('b') or ''))
    if why == 'node':
        return t('情节推进到「{x}」', x=str(mark.get('node') or ''))
    if why == 'tension':
        return t('张力 {a} → {b}',
                 a=f'{float(mark.get("a") or 0):.2f}',
                 b=f'{float(mark.get("b") or 0):.2f}')
    return str(mark.get('text') or '')


def _mark_row(mark: dict, st: FlowStyle, *, with_day: bool = False) -> ft.Control:
    """一条关键剧情 / 转折点（朱砂色竖条 + 时间地点 + 那句事）。"""
    c = st.color
    turn = str(mark.get('kind') or '') == PF.MARK_TURN
    col = c.get('seal', '#c02c22') if turn else c.get('gold', '#a8781f')
    when = ' · '.join(x for x in (
        (t('第 {d} 天', d=mark.get('day')) if with_day and mark.get('day') else ''),
        str(mark.get('time') or ''),
        str(mark.get('place') or ''),
    ) if x)
    body: list[ft.Control] = []
    if when:
        body.append(ft.Text(when, size=st.hint_fs - 1.5, font_family=st.font,
                            color=c.get('muted', '#6a6f78'), no_wrap=True))
    body.append(ft.Text(mark_text(mark), size=st.hint_fs, font_family=st.font,
                        color=c.get('text', '#232830')))
    return ft.Container(
        content=ft.Row([
            ft.Container(width=3, bgcolor=col, border_radius=2),
            ft.Column([
                ft.Text(mark_label(mark), size=st.hint_fs - 1, font_family=st.font,
                        color=col, weight=ft.FontWeight.BOLD, no_wrap=True),
                *body,
            ], spacing=1, tight=True, expand=True),
        ], spacing=7, vertical_alignment=ft.CrossAxisAlignment.START),
        padding=_pad(8, 5, 8, 5),
        margin=_pad(0, 1, 0, 1),
        bgcolor=c.get('paper_hi', '#fffdf6'),
        border_radius=4,
    )


def _section(title: str, st: FlowStyle, controls: list[ft.Control]) -> list[ft.Control]:
    """一个小节标题 + 内容。"""
    c = st.color
    return [ft.Container(height=4),
            ft.Text(title, size=st.hint_fs - 0.5, font_family=st.font,
                    color=c.get('gold', '#a8781f'), weight=ft.FontWeight.BOLD),
            *controls]


def _beat_card(beat: dict, st: FlowStyle) -> ft.Control:
    """**剧作家写的一小段**：场 / 主题 / 出场 / 发生 / 要点 / 推进 / 目标·难题·道具。

    ★ 顺序有意如此：先"在哪、讲什么"（场+主题），再"发生了什么"（发生），
      再"具体几笔"（要点），最后"它推了什么"（推进）。
      剧作家本来就是按这个顺序想的，读的人也按这个顺序接得住。
    ★ 缺的字段**不占位**（不写"（无）"）：一天里一半的拍没有"难题"，
      每张卡都印一行"难题：（无）"会让真正有的那条被淹掉。
    [EN] **One small segment written by the playwright**: scene / theme / cast / what happens /
    [EN] key points / push / goal-problem-props. ★ The order is deliberate: where and what it is
    [EN] about, then what happens, then the concrete strokes, then what it pushed -- the playwright
    [EN] thinks in that order and the reader follows it. ★ Missing fields are **not padded** (no "(none)"):
    [EN] half a day's beats have no "problem", and printing "(none)" on every card would drown the one
    [EN] that does.
    """
    c = st.color
    head: list[ft.Control] = []
    n = int(beat.get('n') or 0)
    theme = str(beat.get('theme') or '')
    scene = str(beat.get('scene') or '')
    if theme or scene:
        head.append(ft.Row([
            ft.Text(f'{n}.' if n else '·', size=st.hint_fs, font_family=st.font,
                    color=c.get('gold', '#a8781f'), weight=ft.FontWeight.BOLD, no_wrap=True),
            ft.Text(theme or scene, size=st.hint_fs, font_family=st.font,
                    color=c.get('text', '#232830'), weight=ft.FontWeight.BOLD, expand=True),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START))
    meta = ' · '.join(x for x in (
        scene if theme else '',
        '、'.join(beat.get('cast') or []),
        str(beat.get('mood') or ''),
    ) if x)
    if meta:
        head.append(ft.Text(meta, size=st.hint_fs - 1.5, font_family=st.font,
                            color=c.get('muted', '#6a6f78')))

    body: list[ft.Control] = []
    if beat.get('happen'):
        body.append(ft.Text(str(beat['happen']), size=st.hint_fs, font_family=st.font,
                            color=c.get('text', '#232830')))
    for p in (beat.get('points') or []):
        body.append(ft.Row([
            ft.Text('·', size=st.hint_fs, font_family=st.font,
                    color=c.get('border_gold', '#c9a24e'), no_wrap=True),
            ft.Text(str(p), size=st.hint_fs - 0.5, font_family=st.font,
                    color=c.get('text', '#232830'), expand=True),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START))
    tail = ' · '.join(x for x in (
        (t('推进：{x}', x=beat['push']) if beat.get('push') else ''),
        (t('目标：{x}', x=beat['goal']) if beat.get('goal') else ''),
        (t('难题：{x}', x=beat['trouble']) if beat.get('trouble') else ''),
        (t('道具：{x}', x='、'.join(beat['props']) if isinstance(beat.get('props'), list)
           else beat.get('props')) if beat.get('props') else ''),
    ) if x)
    if tail:
        body.append(ft.Text(tail, size=st.hint_fs - 1.5, font_family=st.font,
                            color=c.get('accent', '#2f7fb0')))

    return ft.Container(
        content=ft.Column([*head, *body], spacing=3, tight=True),
        padding=_pad(10, 7, 10, 7),
        margin=_pad(0, 2, 0, 2),
        bgcolor=c.get('paper_hi', '#fffdf6'),
        border=_border(1, c.get('border', '#d9c9a3')),
        border_radius=5,
    )


def _shot_grid(shots: list[dict], st: FlowStyle) -> list[ft.Control]:
    """分镜：**折叠**在一块里（一镜一行，很小）。"""
    c = st.color
    rows: list[ft.Control] = []
    for s in shots:
        bits = ' · '.join(x for x in (
            f"#{s.get('n')}" if s.get('n') else '',
            str(s.get('size') or ''),
            str(s.get('frame') or ''),
        ) if x)
        line = str(s.get('line') or '')
        item: list[ft.Control] = [ft.Text(bits, size=st.hint_fs - 1.5, font_family=st.font,
                                          color=c.get('muted', '#6a6f78'))]
        if line:
            item.append(ft.Text(t('台词：{x}', x=line), size=st.hint_fs - 1.5,
                                font_family=st.font, color=c.get('text', '#232830')))
        rows.append(ft.Column(item, spacing=0, tight=True))
    return rows


def build_detail_controls(flow: dict, *, style: FlowStyle,
                          open_days: int = 2) -> list[ft.Control]:
    """把**详细剧情**画出来：关键剧情与转折点（汇总）+ 按天的分拍 / 正文 / 分镜。

    用户 2026-10-26：「剧情总览太简略了 我希望是每次推演里面的**细节剧情** 要很详细
    （到达每次剧作家写**小段剧情**的程度）要包含当前这次推演的**关键剧情和转折点**」

    结构（从上往下）：

    ```
    ┌ 关键剧情与转折点 ────────────────   ← 结论先行（全推演，跨天）
    │ ⚡ 第1天 辰时 · 秘密泄露 · 牌背旧痕… 
    │ ◇ 第1天 09:40 · 张力 0.30 → 0.52
    ├ 第 1 天 · 08:30 → 20:00 · 12 幕 · 6 拍 [收起]
    │   当天梗概 / 场景介绍
    │   ── 这一天的转折 ──
    │   ── 剧作家的分拍 ──  ① 场 · 主题 / 发生 / 要点 / 推进
    │   ── 正文 ──          逐段（这是用户要的"细节剧情"本体）
    │   ── 分镜 ──          默认收起
    └ 第 2 天 …
    ```

    ★ **关键剧情放最上面**：用户要"包含关键剧情和转折点"，那就别让它埋在第 8 天的第 3 拍里。
    ★ **按天可折叠，默认展开最近 `open_days` 天**：一天实测 6 拍 + 48 段正文 + 18 镜
      ≈ 100 个控件，30 天全展开就是 3000 个 —— 对话框会卡到不能用。
      最近几天默认展开（那正是"我刚演的"），更早的点一下就有。
    ★ 控件是**纯函数产出**，折叠靠"重建这一块"，不靠 Flet 的 `visible`：
      后者在 3000 个控件时一样会先渲染一遍（等于没省）。
    :param open_days: 默认展开最后几天的详细内容（0 = 全收起）
    [EN] Draw the **detailed story**: key beats and turning points (aggregate) plus per-day beats,
    [EN] prose and shots. ★ **Key plot goes on top**: the user asked for it, so it must not be buried
    [EN] on day 8 beat 3. ★ **Days fold, the last `open_days` start open**: one day measures ~100
    [EN] controls (6 beats + 48 prose paragraphs + 18 shots), so thirty open days is 3000 and the
    [EN] dialog becomes unusable. ★ Folding rebuilds that block rather than toggling `visible` --
    [EN] `visible=False` still renders once, which saves nothing at that scale.
    """
    st = style
    c = st.color
    detail = (flow or {}).get('detail') or {}
    days = list(detail.get('days') or [])
    turns = list(detail.get('turns') or [])
    out: list[ft.Control] = []

    if not days:
        out.append(ft.Text(t('这次推演还没有落盘的戏，所以没有详细剧情。'),
                           size=st.hint_fs, font_family=st.font,
                           color=c.get('muted', '#6a6f78')))
        return out

    # ── ① 关键剧情与转折点（全推演，跨天汇总）──
    out.extend(_section(t('关键剧情与转折点（共 {a} 个转折 · {b} 个关键）',
                          a=int((detail.get('stats') or {}).get('turns') or 0),
                          b=int((detail.get('stats') or {}).get('keys') or 0)),
                        st, []))
    if turns:
        for m in turns:
            out.append(_mark_row(m, st, with_day=True))
    else:
        out.append(ft.Text(t('这一轮还没有数出转折点（剧情站没换、张力也没大跳）——'
                             '戏还在铺，属于正常。'),
                           size=st.hint_fs - 1, font_family=st.font,
                           color=c.get('muted', '#6a6f78')))

    # ── ② 按天详细 ──
    out.extend(_section(t('按天详细'), st, []))
    tail_days = set(d.get('day') for d in days[-open_days:]) if open_days > 0 else set()
    for d in days:
        out.append(_day_block(d, st, opened=bool(d.get('day') in tail_days)))
    return out


def _day_block(day: dict, st: FlowStyle, *, opened: bool) -> ft.Control:
    """一天的块：标题行（可点折叠）+ 展开后的详细内容。

    ★ 标题行**永远显示**关键数字（幕数 / 拍数 / 正文字数）：收起状态下也要看得出
      "这一天有很多东西"，否则用户会以为又是简略版。
    [EN] One day: a clickable header plus the expanded detail. ★ The header **always** shows the
    numbers (scenes / beats / prose characters), so even collapsed it is clear "there is a lot in
    this day" -- otherwise it looks like the brief version again.
    """
    c = st.color
    n = int(day.get('day') or 0)
    when = ' → '.join(x for x in (str(day.get('from') or ''),
                                  str(day.get('to') or '')) if x)
    counts = ' · '.join(x for x in (
        when,
        t('{n} 幕', n=int(day.get('scenes') or 0)),
        (t('{n} 拍', n=len(day['beats'])) if day.get('beats') else ''),
        (t('正文 {n} 字', n=len(''.join(day.get('story') or [])))
         if day.get('story') else ''),
        ('、'.join(day.get('nodes') or []) or ''),
    ) if x)

    holder = ft.Column([], spacing=0, tight=True)

    def _render(open_now: bool) -> None:
        rows: list[ft.Control] = []
        if day.get('brief'):
            rows.append(ft.Row([
                ft.Text(t('当天梗概'), size=st.hint_fs - 1, font_family=st.font,
                        color=c.get('gold', '#a8781f'), no_wrap=True),
                ft.Text(str(day['brief']), size=st.hint_fs, font_family=st.font,
                        color=c.get('text', '#232830'), expand=True),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.START))
        if day.get('intro'):
            rows.append(ft.Text(t('场景：{x}', x=day['intro']), size=st.hint_fs - 1,
                                font_family=st.font, color=c.get('muted', '#6a6f78')))
        if day.get('marks'):
            rows.extend(_section(t('这一天的转折与关键'), st,
                                 [_mark_row(m, st) for m in day['marks']]))
        if day.get('beats'):
            rows.extend(_section(t('剧作家的分拍（{n} 小段）', n=len(day['beats'])), st,
                                 [_beat_card(b, st) for b in day['beats']]))
        if day.get('story'):
            paras = [ft.Text(str(p), size=st.hint_fs, font_family=st.font,
                             color=c.get('text', '#232830')) for p in day['story']]
            rows.extend(_section(t('正文（剧作家写的 {n} 段）', n=len(paras)), st, paras))
        if day.get('shots'):
            shots = _shot_grid(day['shots'], st)
            rows.extend(_section(t('分镜（{n} 镜）', n=len(day['shots'])), st, shots))
        for note in (day.get('notes') or []):
            rows.append(ft.Text(t('· {x}', x=note), size=st.hint_fs - 1.5,
                                font_family=st.font, color=c.get('muted', '#6a6f78')))
        holder.controls = rows

    state = {'open': opened}
    caret = ft.Text('▾' if opened else '▸', size=st.hint_fs - 1, font_family=st.font,
                    color=c.get('gold', '#a8781f'), no_wrap=True)

    def _toggle(e=None) -> None:
        state['open'] = not state['open']
        caret.value = '▾' if state['open'] else '▸'
        _render(state['open'])
        page = getattr(e, 'page', None) if e is not None else None
        if page is not None:
            page.update()

    _render(opened)
    head = ft.Container(
        content=ft.Row([
            caret,
            ft.Text(t('第 {d} 天', d=n), size=st.body_fs, font_family=st.font,
                    color=c.get('gold', '#a8781f'), weight=ft.FontWeight.BOLD, no_wrap=True),
            ft.Text(counts, size=st.hint_fs - 1.5, font_family=st.font,
                    color=c.get('muted', '#6a6f78'), expand=True),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=_pad(6, 4, 6, 4),
        ink=True,
        tooltip=t('点这里展开 / 收起这一天的详细剧情'),
        on_click=_toggle,
    )
    return ft.Container(
        content=ft.Column([head, holder], spacing=2, tight=True),
        margin=_pad(0, 4, 0, 4),
        padding=_pad(6, 2, 6, 6),
        border=_border(1, c.get('border', '#d9c9a3')),
        border_radius=5,
    )
