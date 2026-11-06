# -*- coding: utf-8 -*-
"""每轮开场（设计稿 §3.6.1）：**开跑前的一屏扉页**。

一句话定位
----------
**这是这一轮的扉页，不是说明书。** 宁可少写，不许写成属性表。

它同时是**输入档位的体检表**：黄金档（人物卡带口癖/目标/关系 + 有伏笔编号）
出来的是叙事；青铜档出来就是干巴巴几个名字 —— 作者一眼就知道该补什么。

内容从哪来（**不新增任何设定负担**）
------------------------------------
| 开场里的东西 | 取自 |
|---|---|
| 时间 / 地点 / 天气 | 世界状态（起始时钟、`SCENE_NAME`、天气） |
| 那两三句叙事引子 | 世界观 + 风格卡（`OPENING_PROSE=false` 时本地拼装，零成本） |
| 每人身份 / 与主角的关系 | 设定集人物卡 + 关系表 |
| 每人「当下」 | 人物卡的**目标** |
| 每人「标志」 | 人物卡的**口癖** |
| 未登场提示 | `PersonState.debut_day`（只给「哪天会来」，**不给是谁**） |

四条红线（设计稿定的）
----------------------
1. **不解释机制、不剧透** —— "未登场"只给何时会来，不给是谁。
2. 人物「当下」只取**目标**；**秘密一律不进开场**（写在 prompt 里也不写）。
3. 一句话定调：扉页，不是说明书。
4. 开场文本与其它产物走同一道合规闸（由调用方决定要不要过）。

English:
Each round's opening (design draft §3.6.1): **a one-screen title page before the run starts**.
One-line positioning
----------
**This is this round's title page, not an instruction manual.** Better to write less; never turn
it into an attribute table.
It is also a **health check for the input tier**: the golden tier (character cards with verbal
tics/goals/relationships + foreshadowing numbers) produces
narrative; the bronze tier produces just a few dry names —— the author sees at a glance what
needs filling in.
Where the content comes from (**do not add any new setting burden**)
------------------------------------
| Item in the opening | Taken from |
|---|---|
| Time / place / weather | World state (starting clock, `SCENE_NAME`, weather) |
| Those two or three narrative prologue sentences | Worldview + style card (assembled locally when `OPENING_PROSE=false`, zero cost) |
| Each person's identity / relationship to the protagonist | Setting-collection character cards + relationship table |
| Each person's "present" | The character card's **goal** |
| Each person's "signature" | The character card's **verbal tic** |
| Not-yet-appeared hint | `PersonState.debut_day` (only gives "which day they will come," **not who it is**) |
Four red lines (set by the design draft)
----------------------
1. **Do not explain mechanics, do not spoil** —— "not yet appeared" only gives when they will come, not who it is.
2. A person's "present" draws only on the **goal**; **secrets never enter the opening** (not even written in the prompt).
3. One-line tone-setting: a title page, not an instruction manual.
4. The opening text goes through the same compliance gate as other artifacts (the caller decides
whether to pass it).
"""
from __future__ import annotations

import re

from config import CFG
from llm.router import llm
from llm import models as MODELS
from logger import log_dir
from sim import directive as _DIRECTIVE
from util.text import fill

_LOG = __import__("logging").getLogger("nws.sim.opening")

# 引子的字数区间（设计稿：60–150 字）。**超了就截、短了不凑** ——
# 为了凑字数往里灌水，是最容易把"扉页"写成"说明书"的做法。
# [EN] Word count range for the prologue (design draft: 60-150 characters). **Truncate if over, do not
# [EN] pad if short** ——
# [EN] Padding to hit a word count is the easiest way to turn a "title page" into an "instruction
# [EN] manual."
PROSE_MIN = 60
PROSE_MAX = 150
# 人物每行上限（设计稿：每行 ≤ 30 字）
# [EN] Per-line limit for characters (design draft: each line ≤ 30 characters)
LINE_MAX = 30
# 落盘文件名（在**运行文件夹**下；与 `任务介绍.md` 分开 ——
# 那个是配置快照，这个是叙事扉页）。界面与导出都引它，别各处硬编码。
# [EN] Output filename (under the **run folder**; separate from `任务介绍.md` ——
# [EN] That one is a config snapshot, this one is the narrative title page). Both the UI and export
# [EN] reference it; do not hardcode it everywhere.
FILE_NAME = "开场.md"

_PROSE_TPL = """你在给一部小说的一轮推演写**开场引子**。

【世界】{world}
【风格】{style}
【此刻】{clock} · {weather} · {place}
【这一站要走的】{node}

写 **2~3 句、{lo}~{hi} 字**的一段。硬要求：
- **只写氛围与局势**（此刻是什么时候、什么地方、什么气味声音、谁还没回来）。
- **不许解释机制**、不许交代设定名词、不许写"接下来会发生"。
- 用小说的笔法，与上面的风格一致。**不要**写标题、不要写序号。
- 直接给正文，不要任何解释或前言。"""


def _clip(s: str, n: int) -> str:
    s = str(s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def relation_of(world, name: str, main: str = "") -> str:
    """这个人跟"主角/这地方"的关系（取关系表里跟他沾边的第一条）。

    ⚠ 关系表是**设定集**里的（`关系.yaml`）；没有就返回空串 ——
    开场宁可少一行，也不许编一句关系出来。
    
        English:
    This person's relationship to the "protagonist/this place" (take the first entry in the
    relationship table that touches them).
        ⚠ The relationship table is in the **setting collection** (`关系.yaml`); if absent, return an empty string ——
        the opening would rather omit a line than invent a relationship.
    """
    rels = getattr(world, "relations", None) or []
    for r in rels:
        if not isinstance(r, dict):
            continue
        a, b = str(r.get("甲") or ""), str(r.get("乙") or "")
        if name not in (a, b):
            continue
        other = b if name == a else a
        desc = str(r.get("关系") or "").strip()
        tension = str(r.get("张力") or "").strip()
        bit = f"与{other}：{desc}" if desc else f"与{other}"
        if tension:
            bit += f"（{tension}）"
        return _clip(bit, LINE_MAX)
    if main and name != main:
        return ""
    return ""


def main_character(world, settings_people: list | None = None) -> str:
    """谁是"主角"：人物卡里标了「主角」的优先，否则第一个前台人物。

    开场要写"与主角的关系" —— 得先知道谁是主角。**不猜性格、不猜戏份**，
    只看设定里的显式标注与出场顺序。
    
        English:
    Who is the "protagonist": the one marked "protagonist" in the character cards takes priority,
    otherwise the first foreground character.
        The opening must write "relationship to the protagonist" —— so you must first know who the protagonist is. **Do not guess personality, do not guess screen time**;
        look only at the explicit markings and appearance order in the setting.
    """
    for p in (settings_people or []):
        if not isinstance(p, dict):
            continue
        marks = "".join(str(p.get(k) or "") for k in ("身份", "简介", "备注", "角色"))
        if "主角" in marks or "主人公" in marks:
            nm = str(p.get("姓名") or "").strip()
            if nm:
                return nm
    for ps in world.people.values():
        if ps.is_active():
            return ps.name
    return next(iter(world.people), "")


def person_rows(world, name: str, main: str = "") -> list[str]:
    """一个人的三行：①姓名·身份 ②关系 ③当下（= 人物卡目标）。行尾挂口癖。
        English:
    A person's three lines: ①name · identity ②relationship ③present (= character card goal). Append
    the verbal tic at the end of the line.
    """
    ps = world.people.get(name)
    if ps is None:
        return []
    ident = _clip(ps.identity, LINE_MAX)
    row1 = f"{name}" + (f"　{ident}" if ident else "")
    rel = relation_of(world, name, main)
    goal = _clip(ps.current_goal or ps.goal or "", LINE_MAX)
    rows = [row1]
    if rel:
        rows.append(rel)
    if goal:
        rows.append(f"当下：{goal}" + (f"　　标志：「{ps.catchphrase}」"
                                       if ps.catchphrase else ""))
    elif ps.catchphrase:
        rows.append(f"标志：「{ps.catchphrase}」")
    return rows


def collect(world, *, day: int | None = None, settings_people: list | None = None,
            mode: str = "") -> dict:
    """把开场要用的料都备齐（**不调模型、纯读状态**）。

    返回 `{'place','clock','weather','node','day','mode','people','pending','prose_hint'}`。
    
        English:
    Prepare all the material needed for the opening (**no model calls, pure state reads**).
        Return `{'place','clock','weather','node','day','mode','people','pending','prose_hint'}`.
    """
    node = None
    try:
        node = world.current_node_info()
    except Exception:                                           # noqa: BLE001
        node = None
    node_name = str((node or {}).get("名称") or "")
    main = main_character(world, settings_people)
    people = []
    for nm in world.on_stage_names():
        rows = person_rows(world, nm, main)
        if rows:
            people.append({"name": nm, "rows": rows})
    pending = []
    for nm in world.pending_names():
        ps = world.people.get(nm)
        d = int(getattr(ps, "debut_day", 1) or 1)
        pending.append({"name": nm, "when": f"第 {d} 天" if d < 999 else "后段"})
    return {
        "place": str(world.scene or ""),
        "clock": world.clock_display(),
        "weather": str(world.weather or ""),
        "node_name": node_name,
        "day": int(day if day is not None else world.game_day),
        "mode": str(mode or CFG.s("RUN_MODE") or "story"),
        "people": people,
        "pending": pending,
        "main": main,
        # ★ **作者对本轮走向的要求**（2026-10-11）—— 他在「起笔」对话框里填的
        #   那一栏。开场卡片是"这一轮怎么跑"的说明处，也是作者**这轮开头会看**
        #   的那一块，所以把它记在这里：他填过的要求看得见、也随卡片一起落在
        #   `开场.md` 里（事后要查"那一轮我让他往哪走"查得到）。
        #   没填就是空串 ⇒ `render_md` 整行都不出现。
        # [EN] * **Author's requirements for this round's direction** (2026-10-11) —— what he entered in the
        # [EN] "Start writing" dialog box. The opening card is where "how this round runs" is explained, and it
        # [EN] is also
        # [EN] the block the author **will look at at the start of this round**, so record it here: the
        # [EN] requirements he entered are visible and land together with the card in
        # [EN] `开场.md` (so later you can look up "where I told it to go that round").
        # [EN] If not filled in, it is an empty string ⇒ `render_md` omits the entire line.
        "directive": _DIRECTIVE.of(world),
        "prose_hint": {
            "world": _clip(world.worldview_text or "", 400),
            "style": _clip((world.style_card or {}).get("句长", "")
                           if isinstance(world.style_card, dict) else "", 60),
            "place": str(world.scene or ""),
        },
    }


@MODELS.agent('ingest')
async def make_prose(op: dict) -> str:
    """引子：调一次便宜档（`OPENING_PROSE` 开时）。失败**降级成拼装版**。
        English:
    Prologue: call the cheap tier once (when `OPENING_PROSE` is on). On failure, **fall back to the
    assembled version**.
    """
    hint = op.get("prose_hint") or {}
    prompt = fill(_PROSE_TPL, world=hint.get("world", ""), style=hint.get("style", ""),
                  clock=op.get("clock", ""), weather=op.get("weather", ""),
                  place=op.get("place", ""), node=op.get("node_name", "") or "（未定）",
                  lo=PROSE_MIN, hi=PROSE_MAX)
    try:
        await llm.ensure_started(log_dir())
        text = await llm.chat("cheap", [{"role": "user", "content": prompt}],
                              purpose="opening", temperature=0.7)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("开场引子生成失败，降级为拼装版：%r", e)
        return ""
    if isinstance(text, (list, tuple)):
        text = " ".join(str(x) for x in text)
    text = re.sub(r"(?m)^#+[ \t]*", "", str(text or "")).strip()
    text = re.sub(r"^\s*(引子|开场)[:：]\s*", "", text)
    if len(text) > PROSE_MAX:
        text = text[:PROSE_MAX].rstrip() + "…"
    return text


def assembled_prose(op: dict) -> str:
    """**零成本**拼装版引子（`OPENING_PROSE=false` / MOCK / 生成失败时用）。

    拼的是"此刻的实况"，不是"设定复述"：时间 + 天气 + 地点 + 门外有人没有。
    宁可短，也不灌水。
    
        English:
    **Zero-cost** assembled prologue (used when `OPENING_PROSE=false` / MOCK / generation fails).
        Assemble "the actual situation right now," not "a restatement of the settings": time + weather + place + whether someone is outside the door.
        Better short than padded.
    """
    bits = []
    clock = str(op.get("clock") or "").strip()
    place = str(op.get("place") or "").strip()
    weather = str(op.get("weather") or "").strip()
    if clock and place:
        bits.append(f"{clock}，{place}")
    if weather and weather != "晴":
        bits.append(f"外头{weather}")
    crowd = str(op.get("crowd") or "").strip()
    if crowd:
        bits.append(crowd)
    if not bits:
        return "故事从这里开始。"
    return "。".join(bits) + "。"


def _mode_name(mode: str) -> str:
    """运行模式的口语名（与界面上那三个下拉一致）。
        English:
    Colloquial name for the run mode (consistent with the three dropdowns in the UI).
    """
    from i18n import t
    return {"story": t("走完故事（有终点）"),
            "open": t("不限期限（一直续写）"),
            "story_day": t("定期暂停（每几天停一次）")}.get(
                str(mode or "story"), t("走完故事（有终点）"))


def render_text(op: dict, *, detail: str = "full", title: str = "",
                prose: str = "", resume_line: str = "") -> str:
    """ASCII 形态（命令行 / 落盘 `开场.txt` / 验证脚本用，**一份实现**）。

    ⚠ **屏幕上的开场不读它** —— 界面走 `render_md()` 渲染成一张卡（2026-10-06
    用户改的：开场不做对话框、不用等确认，直接进中栏的叙事流）。
    这里的等宽框线是为"没有富文本的地方"准备的，别拿它去拼界面。
    
        English:
    ASCII form (for the command line / output `开场.txt` / validation scripts, **one
    implementation**).
        ⚠ **The on-screen opening does not read it** —— the UI renders it into a card via `render_md()` (2026-10-06
        user change: the opening is not a dialog box and does not wait for confirmation, it goes directly into the middle-column narrative stream).
        The monospace box-drawing here is for "places without rich text"; don't use it to compose UI.
    """
    full = str(detail or "full").lower() != "brief"
    bar = "─" * 48
    head = f"══════════ {title} · 开场 ══════════" if title else "══════════ 开场 ══════════"
    lines = [head, ""]
    # ── 场景块 ──
    # [EN] ── Scene block ──
    place = op.get("place") or "（未指定地点）"
    lines.append(f"【场景】{place}")
    lines.append(f"  {op.get('clock', '')} · {op.get('weather', '')}")
    if full:
        lines.append("  " + bar)
        if resume_line:
            lines.append(f"  {resume_line}")
        if prose:
            lines.append(f"  {prose}")
        lines.append("  " + bar)
    node = op.get("node_name") or ""
    status = f"  起始节点 {node} ｜ 第 {op.get('day', 1)} 故事日 ｜ {_mode_name(op.get('mode', ''))}"
    lines.append(status)
    lines.append("")
    # ── 人物块 ──
    # [EN] ── Character block ──
    lines.append("【登场人物】")
    for p in (op.get("people") or []):
        rows = p["rows"] if full else [p["rows"][0]]
        if not rows:
            continue
        lines.append(f"  ▸ {rows[0]}")
        for r in rows[1:]:
            lines.append(f"     {r}")
    if op.get("pending"):
        who = "、".join(f"{x['name']}（{x['when']}）" for x in op["pending"][:6])
        lines.append(f"  · 未登场：{who}")
    lines.append("")
    lines.append(bar)
    # 这里以前写的是 `[Enter] 开演  [o] 详略  [e] 导出这一屏` —— 那套按键
    # **2026-10-06 取消了**：开场不再是"停下来等你确认的一屏"，而是开跑瞬间
    # 推给作者的第一张卡（见 `gui/app_flet.py::_push_opening_card`）。
    # [EN] This used to say `[Enter] start  [o] detail level  [e] export this screen` —— those key bindings
    # [EN] **were removed on 2026-10-06**: the opening is no longer "a screen that stops and waits for your
    # [EN] confirmation," but the first card
    # [EN] pushed to the author the moment it starts (see `gui/app_flet.py::_push_opening_card`).
    lines.append(f"  （本开场已存入 {FILE_NAME}）")
    return "\n".join(lines)


def render_md(op: dict, *, title: str = "", detail: str = "full",
              prose: str = "", resume_line: str = "",
              for_novel: bool = False) -> str:
    """Markdown 形态（落盘 `开场.md` / 导出贯通用）。

    `for_novel=True` 时剃掉「未登场」与来源标注 —— 那是**作者的体检表**，
    不该出现在给读者看的稿子里（设计稿 §3.6.1 明确要求）。
    
        English:
    Markdown form (written to disk as `开场.md` / used for export consistency).
        When `for_novel=True`, strip out "not yet appeared" and source annotations -- that's the **author's checklist**,
        and should not appear in the manuscript shown to readers (design doc §3.6.1 explicitly requires this).
    """
    full = str(detail or "full").lower() != "brief"
    md = [f"# 开场{f' · {title}' if title else ''}", ""]
    md.append(f"**{op.get('clock', '')} · {op.get('weather', '')} · {op.get('place', '')}**")
    md.append("")
    if op.get("directive"):
        # ★ 作者对本轮走向的要求（2026-10-11）—— 用引用块，与正文分得开
        #   （它**不是**这一轮演出来的东西，别让人误读成剧情）。
        # [EN] * Author's requirements for this round's direction (2026-10-11) —— use a blockquote to keep it
        # [EN] separate from the body text
        # [EN] (it is **not** something performed in this round, do not let people misread it as plot).
        md.append(f"> {_DIRECTIVE.line_from(op.get('directive'))}")
        md.append("")
    if resume_line:
        md.append(f"> {resume_line}")
        md.append("")
    if full and prose:
        md.append(prose)
        md.append("")
    node = op.get("node_name") or ""
    bits = [b for b in (f"起始节点 {node}" if node else "",
                        f"第 {op.get('day', 1)} 故事日",
                        _mode_name(op.get('mode', ''))) if b]
    md.append("*" + " ｜ ".join(bits) + "*")
    md.append("")
    md.append("## 登场人物")
    md.append("")
    for p in (op.get("people") or []):
        rows = p["rows"] if full else [p["rows"][0]]
        md.append(f"- **{rows[0]}**")
        for r in rows[1:]:
            md.append(f"  - {r}")
    if op.get("pending") and not for_novel:
        who = "、".join(f"{x['name']}（{x['when']}）" for x in op["pending"][:6])
        md.append("")
        md.append(f"*未登场：{who}*")
    return "\n".join(md) + "\n"


def save(run, text_md: str) -> None:
    """落 `<运行文件夹>/开场.md`（与 `任务介绍.md` **分开**：那个是配置快照）。
        English:
    Write to `<run folder>/开场.md` (**separate** from `任务介绍.md`: that one is a config snapshot).
    """
    if not run:
        return
    try:
        (run.root / FILE_NAME).write_text(text_md, encoding="utf-8")
    except OSError as e:
        _LOG.warning("开场落盘失败：%r", e)


def read_saved(run) -> str:
    """读回本轮落盘的那份开场（`opening` 命令用它）。没有就返回空串。
        English:
    Read back the opening written to disk this round (used by the `opening` command). If none
    exists, return an empty string.
    """
    if not run:
        return ""
    try:
        p = run.root / FILE_NAME
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except OSError as e:                                        # noqa: BLE001
        _LOG.warning("开场读回失败：%r", e)
        return ""
