# -*- coding: utf-8 -*-
"""**花费顾问**：把 `usage.db` 的账读成人话，并给出"怎么把它降下来"的建议。

用户 2026-11-01：
「这个报告是否可以在天机里有一个Tab，并且记录单独的日志，并且后续可以在这个上
有一个按钮进行智能分析并在现有软件框架下给出优化方法，包括修改配置 选择不同LLM
等等能够想到的方法 再加一个深度优化 是从软件层面给出建议」。

四件事，各管一段
----------------
1. **报表**（`report()`）—— 纯 SQL + 纯计算，**一次模型都不调**。
   与 `tools/report_llm_cost.py` 是**同一份实现**（那个脚本现在只是个薄壳）。
2. **智能分析**（`advise(deep=False)`）—— 把报表 + 配置快照 + 模型价目表喂给模型，
   要它回**结构化 JSON**：哪一步最贵、哪几项配置该改、哪一档该换模型。
3. **深度优化**（`advise(deep=True)`）—— 多喂一块"本程序是怎么拼上下文的"
   （前缀顺序 / 去重 / 缓存 / 每拍固定段），要它给**软件层**建议。
4. **应用建议**（`apply_change()` / `apply_model()`）—— 只认白名单 + 类型校验，
   越权或不合法的建议**不显示按钮**，界面只能看。

## 为什么"能应用"比"能分析"难十倍
模型给出的 `{"key": "...", "value": ...}` 直接写进 `.env` 有三个必踩的坑：
  · **键名瞎编**（`SCRIPT_REVIEW_EVERY` 不存在，真名是 `SCRIPT_REVIEW_EVERY_TICKS`）
    ⇒ 写进去是个死键，`CFG` 读不到，用户以为"改了没效果"；
  · **值越界**（把「剧本审读每 N 拍」写成 0）⇒ 除零或者彻底停摆；
  · **改的不是省钱项**（把 `LOG_DIR` 指到别处、把 `MOCK_LLM` 打开）⇒ 看起来"优化"，
    实际把程序改坏。
所以三道闸：`APPLICABLE` 白名单 → `SPEC` 存在性 + `coerce()` 类型/范围 → 界面二次确认。
**闸门在写入的那一侧**（`apply_change`），不在界面上 —— 万一以后有第二个入口
（托盘、命令行），它照样受管。

## 单独的日志
`logs/cost_advisor.log`（跟随 `LOG_DIR` 设置，见 `logger.log_dir()`）。
记三类：打开这一页、跑了一次分析（含用量与耗时）、应用了一条建议（含改前/改后）。
**为什么不并进主日志**：主日志一次推演几千行，用户回头"我上次为什么把审读改成 3 拍"
根本翻不到；这一份只有几十行，翻得动。

English:
**Cost advisor**: reads `usage.db` into plain words and proposes how to bring it down.
Four parts: 1) report (pure SQL, no model call, the single implementation behind both
the CLI script and the Tianji tab); 2) smart analysis (report + config snapshot + price
list -> structured JSON advice); 3) deep analysis (also explains how this program
assembles context, so it can propose software-level changes); 4) apply -- whitelist +
type/range check + UI confirmation, guarded at the write site (not in the UI).
A dedicated log (`logs/cost_advisor.log`) records page opens, analyses and applications,
because the main log is thousands of lines per run and nobody can find "why did I set
script review to every 3 beats" in it.
"""
from __future__ import annotations

import csv
import json
import sqlite3
import time
from datetime import date
from pathlib import Path

from llm import usage as U

APP = Path(__file__).resolve().parent.parent

#: 命中率低于这个数就值得怀疑（不代表一定有病：短 prompt 天然命中率低）
# [EN] Below this hit ratio is suspicious (not necessarily a defect: short prompts are naturally low)
LOW_HIT = 0.15
#: 低于这么多 token 的用途先不点评（量太小，省不出钱）
# [EN] Purposes below this many tokens are not commented on (too small to matter)
MIN_TOK = 300_000
#: 报表里最多列几行（再多的自己看表格）
# [EN] Max rows in the text report
TOP_ROWS = 18

#: 这一页自己的日志文件名（与主日志同目录）
# [EN] This page's own log filename (same directory as the main log)
LOG_NAME = 'cost_advisor.log'

#: 允许「一键应用」的键 —— **白名单**。
#:
#: 入选标准三条，缺一不可：
#:   ① 直接与花费有关（改大改小都能算出影响）；
#:   ② 改坏了**不会把程序弄坏**（最多效果差一点，随时能改回来）；
#:   ③ 有界（int/float 有 min·max，enum 有 opt，bool 天然安全）。
#: ⚠ 刻意**不在**这张表里的（模型最容易提、但最危险）：
#:   `MOCK_LLM`（改成 true 等于全程序跑假数据）、`LOG_DIR` / `DEFAULT_PROJECTS_DIR`
#:   （指错地方 = 数据"丢了"）、`LLM_BASE_URL` / `LLM_API_KEY`（凭据）、
#:   任何 `LLM_CAP_*`（发错参数会让某些模型直接 400）。
# [EN] Keys that may be applied with one click -- a **whitelist**. Three criteria, all required:
# [EN] cost-related, harmless if wrong, and bounded. Deliberately excluded (though a model
# [EN] loves to suggest them): MOCK_LLM, LOG_DIR / DEFAULT_PROJECTS_DIR, credentials, LLM_CAP_*.
APPLICABLE: tuple[str, ...] = (
    'SCRIPT_REVIEW', 'SCRIPT_REVIEW_EVERY_TICKS', 'SCRIPT_REVIEW_HISTORY',
    'SCRIPT_REVIEW_STRICT', 'SCRIPT_REVIEW_MODEL',
    'DIRECTOR_ENABLED', 'DRAMA_LEVEL', 'CONFLICT_FREQUENCY',
    'TIME_RATIO', 'BEAT_SECONDS', 'QUIET_MINUTES', 'TICK_REAL_MS',
    'AUTOSAVE_SECONDS', 'LAUNCH_TIMEOUT_S',
    'POLISH_MAX_ROUNDS', 'POLISH_MAX_STEPS', 'POLISH_MAX_TOOL_CALLS',
    'TOKEN_BUDGET_PER_DAY', 'TASK_FREEDOM', 'STYLE_FREEDOM',
    'SNAPSHOT_KEEP', 'COST_ADVISOR_TIER',
)
#: ⚠ 白名单里的每一个键**必须**在 `SPEC` 里真实存在 —— 判据 `verify_cost_tab` 的 C2
#: 会把这张表与 `SPEC` 逐条对一遍。写错一个键名的后果是"应用按钮永远不出现"，
#: 而界面上看起来一切正常（用户只会觉得"AI 提的建议怎么点不了"）。
# [EN] ⚠ Every key here **must** really exist in `SPEC` -- criterion C2 of `verify_cost_tab`
# [EN] walks the table against `SPEC`. A typo means "the apply button never appears" while
# [EN] everything looks fine (the user just wonders why the advice is not clickable).

#: 三档在界面上的叫法（模型建议里要用，别在两处各写一份）
# [EN] Tier display names (used in model suggestions; keep one copy)
TIER_LABEL = {'front': '主力档', 'daily': '日常档', 'cheap': '便宜档'}
TIER_KEYS = ('front', 'daily', 'cheap')
_TIER_FIELD = {'front': 'MODEL_FRONT', 'daily': 'MODEL_DAILY', 'cheap': 'MODEL_CHEAP'}


# ══════════════════════════════════════════════════════════════════
#  日志（这一页单独一份）
# [EN] Logging (a dedicated file for this page)
# ══════════════════════════════════════════════════════════════════
def log_path() -> Path:
    """这一页日志的完整路径（跟随 `LOG_DIR`，与主日志同目录）。
        English:
    Full path of this page's log (follows `LOG_DIR`, same directory as the main log).
    """
    try:
        from logger import log_dir
        d = Path(log_dir())
    except Exception:                                            # noqa: BLE001
        d = APP / 'logs'
    return d / LOG_NAME


def log_line(text: str) -> None:
    """往这一页的日志里追加一行。**永不抛** —— 旁路不该变成故障源。
        English:
    Append one line to this page's log. **Never throws** -- a bypass must not become a failure
    source.
    """
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(p, 'a', encoding='utf-8') as f:
            f.write(f'[{stamp}] {text}\n')
    except Exception:                                            # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════════
#  报表（纯计算，不调模型）
# [EN] Report (pure computation, no model calls)
# ══════════════════════════════════════════════════════════════════
def fmt(n: float) -> str:
    if n >= 1e6:
        return f'{n / 1e6:.1f}M'
    if n >= 1e3:
        return f'{n / 1e3:.0f}K'
    return f'{n:.0f}'


def overview(days: float | None = 7, scope: str | None = None,
             path: Path | None = None) -> dict:
    """总账：调用次数 / 输入 / 输出 / 命中 / 花费 / 输入输出比 / 涉及几个用途。

    `path`：**只看另一份台账**（判据用临时库；界面上永远不传，走默认的 `usage.db`）。
        English:
    Totals: calls / input / output / cached / cost / in-out ratio / how many purposes.
        `path`: **read another ledger** (criteria use a temp DB; the UI never passes it).
    """
    rows = U.purposes(days=days, scope=scope, path=path)
    tin = sum(r['in_tok'] for r in rows)
    tout = sum(r['out_tok'] for r in rows)
    cache = sum(r['cache_tok'] for r in rows)
    calls = sum(int(r['calls'] or 0) for r in rows)
    cost = sum(float(r['cost'] or 0) for r in rows)
    return {'rows': rows, 'calls': calls, 'in_tok': tin, 'out_tok': tout,
            'cache_tok': cache, 'cost': cost,
            'hit': (cache / tin) if tin else 0.0,
            'ratio': (tin / max(tout, 1)),
            'purposes': len(rows),
            'days': days, 'scope': scope or ''}


def suspects(ov: dict) -> list[dict]:
    """「低命中 + 量大」的那几条 —— 值得看一眼的嫌疑项（按量降序）。
        English:
    The "low hit + large volume" entries -- suspects worth a look (sorted by volume desc).
    """
    out = [r for r in ov.get('rows') or []
           if (r['cache_tok'] / max(r['in_tok'], 1) < LOW_HIT
               and (r['in_tok'] + r['out_tok']) >= MIN_TOK)]
    out.sort(key=lambda r: -(r['in_tok'] + r['out_tok']))
    return out


def report(days: float | None = 7, *, scope: str | None = None,
           top: int = TOP_ROWS, path: Path | None = None) -> str:
    """拼出那份**给人看**的文本报表（命令行与界面共用这一份）。
        English:
    Build the **human-readable** text report (shared by the CLI and the UI).
    """
    ov = overview(days, scope, path=path)
    rows = ov['rows']
    if not rows:
        return ('这个时间段里没有记录（程序还没跑过，或时间窗太小）。\n'
                '跑一次推演之后这里就有数了。')
    span = '全部历史' if days is None else f'最近 {days:g} 天'
    tot_tok = ov['in_tok'] + ov['out_tok'] or 1
    lines = [
        f'═══ LLM 花费体检 · {span} ═══',
        f'调用 {ov["calls"]:,} 次 ｜ 输入 {fmt(ov["in_tok"])} ｜ 输出 '
        f'{fmt(ov["out_tok"])} ｜ 输入/输出 = {ov["ratio"]:.1f} 倍',
        f'命中厂商缓存 {fmt(ov["cache_tok"])} = **{ov["hit"]:.1%}**  （命中价约 1/10）'
        f' ｜ 合计 ¥{ov["cost"]:.2f}',
        '',
        f'{"用途":<24}{"次数":>7}{"输入":>9}{"输出":>8}{"命中率":>8}{"占比":>7}{"花费":>9}',
        '─' * 74,
    ]
    for r in rows[:top]:
        share = (r['in_tok'] + r['out_tok']) / tot_tok
        hit = r['cache_tok'] / max(r['in_tok'], 1)
        flag = ' ← 低' if (hit < LOW_HIT and
                           (r['in_tok'] + r['out_tok']) >= MIN_TOK) else ''
        lines.append(f'{r["purpose"][:23]:<24}{int(r["calls"]):>7,}'
                     f'{fmt(r["in_tok"]):>9}{fmt(r["out_tok"]):>8}'
                     f'{hit:>7.1%}{share:>7.1%}{float(r["cost"]):>9.2f}{flag}')
    sus = suspects(ov)
    if sus:
        lines += ['', f'── 值得看一眼的低命中项（命中率 < {LOW_HIT:.0%} 且量 >= '
                      f'{fmt(MIN_TOK)} token）──']
        for r in sus[:8]:
            lines.append(f'  · {r["purpose"]:<22} 命中 {r["cache_tok"] / max(r["in_tok"], 1):5.1%}'
                         f'  输入 {fmt(r["in_tok"]):>7}'
                         f'  摊到 {(r["in_tok"] + r["out_tok"]) / tot_tok:.1%} 的花费面')
        lines += ['',
                  '  ⚠ 低命中**不一定**是病：',
                  '    · prompt 本身很短（几百 token）⇒ 能共享的前缀本来就少，属正常；',
                  '    · 每拍内容全变且**稳定段排在末尾** ⇒ 这是真病，改顺序就能省一大截。',
                  '    区分办法：看它有没有一大段「每拍一字不变」的内容（规则/纪律/标准）。']
    if ov['in_tok']:
        saved = ov['cache_tok'] * 0.9
        lines += ['', '── 已经省下的（按命中部分少付 9 成估）──',
                  f'  命中 {fmt(ov["cache_tok"])} token ≈ 少付 {fmt(saved)} token 的钱'
                  f'（占输入的 {saved / ov["in_tok"]:.1%}）']
    lines += ['', '（口径：`usage.db` 每次真调用一行；外挂服务不经过本项目，不在账上）']
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════
#  「用途」这一列的人话
# [EN] Turning a purpose code into something a human can read
# ══════════════════════════════════════════════════════════════════
#: 用途代号 → 一句话说明（**说"这一步在干什么"，不说"它属于哪个模块"**）。
#:
#: ★★★ 为什么必须有一张表：`purpose` 是写进台账的英文代号（`agent_decide`、
#:   `progress_eval`），作者看到只会问"这是什么"。而这一页的用处正是
#:   "认出哪一项花钱不值" —— 认不出这一步在做什么，就只能看见一堆英文单词。
#:
#: ⚠ 这张表**只写界面与 CSV 上的人话**，不参与取数：代号本身仍是 `usage.db` 里那个。
#:   所以少了某一条不会算错钱，只会显示兜底文案（见 `purpose_desc`）。
#: ⚠ 描述里**不许出现花括号** —— 界面会用 `t()` 过一遍做英文替换，`{}` 是占位符语法。
# [EN] Purpose code -> one plain sentence about **what that step does**.
# [EN] ★★★ Why a table: `purpose` is an English code written into the ledger; the author only
# [EN] asks "what is this". ⚠ This table only feeds the UI/CSV wording, never the numbers: a
# [EN] missing entry costs no accuracy, it just shows the fallback text.
PURPOSE_DESC: dict[str, str] = {
    # ── 推演主干（钱主要花在这里）────────────────────────────────
    'agent_decide': '在场人物决定这一拍做什么、说什么（最贵的一步）',
    'dialogue': '人物开口说一句台词',
    'group_chat': '同场多人时说一句（群聊轮转的一拍）',
    'plan': '给每个前台人物排今天这一天的打算',
    'reflect': '人物反思：攒够重要性才触发一次',
    'progress_eval': '评估这一段到底推进了没有',
    'progress': '从大纲建进度节点表',
    'narrative': '把这一天写成叙述文字',
    'opening': '生成两三个候选开局',
    'day_story': '写当天的故事正文',
    'day_script': '写当天的剧本（能拍的分场分拍）',
    'day_summary': '把刚过去的一天压成一条前情提要',
    'backstage_summary': '把后堂那边的动静压成一批摘要',
    'ctx_compact': '把较早的上下文压成两三句',
    'memory_compact': '把一批老记忆压成两三句',
    'prose_flow_fix': '把整段没铺开的段落重写一遍',
    'dispatch': '每几拍给在场人物各派一件此刻该推进的事',
    'director_event': '导演对某个事件的处置（挑事、接住、还是放过）',
    'branch': '生成两三个剧情走向候选（卡住时给你的那个选择框）',
    'day_verify': '验算当天的剧本：前后接不接得上',
    # ── 材料与设定 ───────────────────────────────────────────────
    'extract': '从文档里抽出结构化设定',
    'genre': '判这本书是什么类型',
    'style': '从正文提取风格卡',
    'alignment': '把写出来的正文对齐回章节结构，找出漏写错位',
    'repair_source': '按缺口清单让模型把材料补上',
    'optimize_review': '给设定做一遍体检，出诊断文本',
    'optimize_apply': '按作者说的一句话修订设定',
    'coordinator': '把作者的一句话解析成要改什么的结构化指令',
    'compliance': '合规检查：有没有不该写的东西',
    'bilingualize': '把中文注释翻成英文（开发者工具）',
    'research': '一次考据：名物、制度、称谓查得对不对',
    'help_qa': '手册问答：回答「这个功能在哪、怎么用」',
    # ── 拆书（读别人的书）────────────────────────────────────────
    'book_scan': '拆书·粗扫：一批章节先过一遍',
    'book_deep': '拆书·精读：挑出来的几章逐章细读',
    'book_final': '拆书·归纳：把读完的变成可复用的素材条目',
    # ── 导出与润色（收工之后的事）────────────────────────────────
    'review': '审稿一遍：贴设定、贴风格、节奏，低分就重写一次',
    'storyline': '生成故事文档',
    'outline': '生成推演之后的写作指导',
    'summary': '生成这一轮运行报告',
    'novel_polish': '把合订本整理成连贯的小说稿',
    'polish_step': '润色 Agent 走一步（改到"收尾"或"问作者"为止）',
    'polish_reflect': '润色时回头查一遍：漏了？改坏了？越权了？',
    # ── 分层创作（atelier）与底图 ────────────────────────────────
    # ⚠ `atelier_L0..L3` 是**动态拼**出来的（`f'atelier_{layer}'`），而层名单是
    #   `crew/atelier.py:LAYERS` 那四层 —— 所以就照它逐个登记，不做前缀匹配：
    #   前缀模板没法进 i18n（替换后才拼成句子），英文界面就会留中文。
    # [EN] `atelier_L0..L3` are built dynamically (`f'atelier_{layer}'`) from
    #   `crew/atelier.py:LAYERS` -- list them individually rather than by prefix: a prefix
    #   template cannot go through i18n (the sentence only exists after substitution).
    'atelier_L0': '分层创作第 0 层：把推演抽成全书骨架（先分章）',
    'atelier_L1': '分层创作第 1 层：把一章拆成节拍',
    'atelier_L2': '分层创作第 2 层：把节拍写成正文草稿',
    'atelier_L3': '分层创作第 3 层：在草稿上补细节（只改质地，不动事实）',
    'atlas_overview': '生成推演世界那张底图（概览）',
    'atlas_place': '生成某一处地点的底图',
    '地图建筑考据': '画地图之前，先查一下这栋建筑该长什么样',
    # ── 历史代号（旧版本用过，现在代码里已经没有这一步）──────────
    # ⚠ 留在表里是因为**台账里还有它们的历史行**：不解释的话，作者翻到那几行
    #   只会看到"（这个代号还没登记说明）"，以为软件坏了。
    # [EN] Kept because the ledger still holds their historical rows; without an entry the
    #   author sees "(no description)" and thinks something is broken.
    'critic': '（旧版留下的代号，现在没有这一步了）',
    'x': '（测试时留下的代号，不是真花费）',
    # ── 剧组各职位（crew/<职位> 在干活）──────────────────────────
    'crew_agents_infer': '为这本书推断各职位的项目级定制',
    'crew_art': '定这一部的画风与配色，管住出图一致性',
    'crew_continuity': '连戏检查：时间、物件、称呼、状态对不对得上',
    'crew_custom': '剧组里你自己加的那个职位在干活',
    'crew_day_map': '画当天那张地图：今天这几场戏在哪、什么位置',
    'crew_day_novel': '写当天这一章（转写材料 + 定点修句子毛病）',
    'crew_extra': '群演：门外的人和事',
    'crew_novelist': '写当天这一章的原著样章',
    'crew_polish': '逐句挑毛病，点名哪几句该怎么改',
    'crew_props': '定这一场该有哪件物件、哪件要反复出现',
    'crew_publicity': '写一句话卖点、看点、预告',
    'crew_rehearsal': '剧本定稿前空走一遍：哪一拍谁做不到',
    'crew_research': '考据：名物、制度、称谓站不站得住',
    'crew_review': '收工复盘：剧情总结 + 问题 + 后续意见',
    'crew_script_doctor': '上屏前逐条读：是不是人话、接不接上文',
    'crew_settings': '三方会审：为该推进的故事补局部设定',
    'crew_sound': '这一场的声音层：环境音、静默、转折',
    'crew_storyboard': '把定稿的分拍拆成镜头清单',
    'crew_stylist': '人物衣着、随身物、仪态（进出图提示词）',
    # ── 这一页自己 / 自检 ────────────────────────────────────────
    'cost_advice': '这一页的「智能分析」（点一次就记一笔）',
    'cost_deep': '这一页的「深度优化」（点一次就记一笔）',
    'probe': '试发一条最小请求：这个模型名现在能不能用',
    'verify': '判据自己造的假账（自检用，不是真花费）',
    'verify_dialogue': '判据真调一次模型，验对话链路（自检用）',
    'crew_story_for_scope_probe': '判据用的探针：量试拍范围（自检用）',
}

#: 查不到时的兜底。**不许返回空串**：空单元格看起来像"这一行没有用途"，
#: 而真相是"这个代号还没人写说明"—— 两种情况的处置完全不一样。
# [EN] Fallback when unknown. Never return an empty string: a blank cell reads as "this row has
# [EN] no purpose", while the truth is "nobody wrote a description for this code yet".
DESC_UNKNOWN = '（这个代号还没登记说明）'


def purpose_desc(p: str) -> str:
    """用途代号 → 一句人话（**永不返回空串**）。
        English:
    Purpose code -> one plain sentence (never an empty string).
    """
    k = str(p or '').strip()
    d = PURPOSE_DESC.get(k)
    return d if d else DESC_UNKNOWN


def desc_rows(ov: dict) -> list[dict]:
    """把 `overview()` 的行补上 `desc` 与占比 —— 界面表格与 CSV **都读这一份**。

    ★★ 为什么不在两处各拼一次：列的顺序、占比的分母、描述取哪个函数，
      任何一处改动只要漏了另一边，屏幕和导出的表就对不上，而两边看着都正常。
    [EN] Add `desc` and share to the overview rows -- the UI table and the CSV **both read this**.
    ★★ Why not build it twice: column order, the share denominator, which function supplies the
    description -- miss one side and the screen no longer matches the export, while both look fine.
    """
    rows = ov.get('rows') or []
    tot = (ov.get('in_tok', 0) + ov.get('out_tok', 0)) or 1
    out = []
    for r in rows:
        tin = max(int(r.get('in_tok') or 0), 1)
        out.append({
            'purpose': r.get('purpose', ''),
            'desc': purpose_desc(r.get('purpose', '')),
            'calls': int(r.get('calls') or 0),
            'in_tok': int(r.get('in_tok') or 0),
            'out_tok': int(r.get('out_tok') or 0),
            'cache_tok': int(r.get('cache_tok') or 0),
            'hit': (int(r.get('cache_tok') or 0) / tin),
            'share': ((int(r.get('in_tok') or 0) + int(r.get('out_tok') or 0)) / tot),
            'cost': float(r.get('cost') or 0.0),
        })
    return out


# ══════════════════════════════════════════════════════════════════
#  给模型看的素材
# [EN] Material handed to the model
# ══════════════════════════════════════════════════════════════════
def _models_brief() -> list[dict]:
    """登记表里的模型 + 单价（模型要"换个便宜的"，就得先看见价）。
        English:
    Models in the registry with unit prices (to propose "switch to a cheaper one", the model
    must see the prices first).
    """
    try:
        from llm import models as MODELS
        items = MODELS.ensure_ready()
    except Exception:                                            # noqa: BLE001
        return []
    out = []
    for e in items[:16]:
        out.append({'key': e.key, 'name': e.display(),
                    'price(元/百万 token, 命中/未命中/输出)': e.price_label() or '未填',
                    'note': (e.note or '')[:40]})
    return out


def _tiers_now() -> dict:
    """三档现在各是什么模型（键 + 显示名）。**读不到就如实说读不到**。
        English:
    Which model each tier uses now (key + display name). If it cannot be read, say so.
    """
    from config import CFG
    out = {}
    for tier in TIER_KEYS:
        key = CFG.s(_TIER_FIELD[tier])
        name = key or '（跟默认模型走）'
        try:
            from llm import models as MODELS
            e = MODELS.find(key) if key else None
            if e is not None:
                name = e.display()
        except Exception:                                        # noqa: BLE001
            pass
        out[tier] = {'key': key, 'name': name}
    return out


def _config_now() -> dict:
    """白名单里那些键**当前的生效值**（改之前得知道起点）。
        English:
    The **current effective values** of the whitelisted keys (you need the starting point).
    """
    from config import CFG, SPEC, coerce
    out = {}
    for k in APPLICABLE:
        spec = SPEC.get(k)
        if not spec:
            continue
        try:
            v, _ = coerce(k, CFG.raw(k) if hasattr(CFG, 'raw') else CFG.s(k))
        except Exception:                                        # noqa: BLE001
            v = CFG.s(k)
        out[k] = {'value': v, 'desc': (spec.get('desc') or '')[:80]}
    return out


#: 「已经做过的优化」—— 喂给模型，**避免它把功劳当建议再提一遍**。
#: ⚠ 这一串必须与代码同步：`agent/core.py` 的 `_act` 确实把纪律段前移了；
#:   判据 `verify_prefix_cache.py` 的 E 组守着"纪律段不许回到末尾"。
# [EN] "Already done" -- fed to the model so it does not re-propose finished work.
# [EN] ⚠ Keep in sync with the code; `verify_prefix_cache.py` group E guards it.
DONE_ALREADY = (
    '1) `agent_decide`（人物决策）的 30 条纪律段已前移到最前 —— 四拍公共前缀 '
    '20.7% → 67.2%；',
    '2) 提示词按 pack() 顺序拼装：fixed → semi → dyn → tail，稳定段天然靠前；',
    '3) 同一请求有去重缓存（dedup）与结果缓存（cache），只认**判定类**用途；',
    '4) 推理模型「思考吃光额度」已自愈并记住（`_no_think_learned`），不重复白烧；',
    '5) 剧本审读支持「每 N 拍才过一次模型」，中间几拍只剩零成本规则层。',
)

#: 深度优化时额外告诉模型的**结构事实**（它看不到源码）。
# [EN] Structural facts handed to the model in deep mode (it cannot see the source).
STRUCTURE = (
    '本程序的上下文拼装方式：',
    '· 一次 LLM 请求 = 固定段（铁律/格式/示例）+ 半固定段（设定集摘要、纪律）+ '
    '动态段（这一拍的现场、在场人物、近几拍台词）+ 尾部（JSON 指令）。',
    '· 厂商前缀缓存只认「从头开始连续相同」的前缀：第 1 个不同的字之后全部重算，'
    '命中价约 1/10。所以**顺序**就是钱。',
    '· 推演每拍会并发调用多个 Agent（人物决策 + 剧本审读 + 导演事件），'
    '它们的固定段大体相同、动态段各不相同。',
    '· 长上文会被裁剪/摘要（ctx_compact / memory_compact），裁剪本身也要花一次调用。',
    '· 输出 token 单价通常是输入的 3~8 倍，所以"让它多写"比"让它多读"更贵。',
)


def facts(days: float | None = 7, *, scope: str | None = None,
          deep: bool = False, path: Path | None = None) -> dict:
    """攒一份给模型的素材（纯数据，不含指令）。
        English:
    Assemble the material for the model (pure data, no instructions).
    """
    ov = overview(days, scope, path=path)
    tot = ov['in_tok'] + ov['out_tok'] or 1
    rows = []
    for r in ov['rows'][:20]:
        rows.append({'purpose': r['purpose'], 'calls': int(r['calls']),
                     'in': r['in_tok'], 'out': r['out_tok'],
                     'hit': round(r['cache_tok'] / max(r['in_tok'], 1), 3),
                     'cost': round(float(r['cost']), 4),
                     'share': round((r['in_tok'] + r['out_tok']) / tot, 3)})
    f = {
        '窗口': ('全部历史' if days is None else f'最近 {days:g} 天'),
        '总览': {'调用次数': ov['calls'], '输入token': ov['in_tok'],
                 '输出token': ov['out_tok'], '输入输出比': round(ov['ratio'], 2),
                 '缓存命中率': round(ov['hit'], 3), '花费元': round(ov['cost'], 2)},
        '按用途': rows,
        '三档现用模型': _tiers_now(),
        '可换的模型': _models_brief(),
        '当前配置': _config_now(),
        '已经做过的优化（不要重复建议）': list(DONE_ALREADY),
    }
    if deep:
        f['程序结构事实'] = list(STRUCTURE)
        f['可一键应用的配置键'] = list(APPLICABLE)
    return f


_RULES = """你是这个程序的花费顾问。你的任务**不是**写文章，是让作者少花钱、效果不变。

铁律：
1. 只看给定数据，不要编造数字。数据里没有的东西就说"看不出来"。
2. 每条建议必须能算出"省在哪"：省的是输入、输出、还是调用次数。
3. 输入 token 通常是输出的 7~11 倍，所以**先看输入**；命中率低 + 量大 = 最值得改。
4. 不要建议"少写/降低质量/关掉功能"这种一句话建议，除非你说明了代价。
5. `config_changes` 里的 `key` **必须**是"可一键应用的配置键"里出现过的；其它项写进 `software`。
6. 只输出 JSON，不要解释、不要代码块围栏。"""

_DEEP_RULES = """
7. 这是**深度优化**：要的是软件层的改法（拼装顺序、调用次数、上下文裁剪、模型分流、
   缓存键设计、批处理、增量摘要），不是调参。每条给出"改哪里 + 怎么改 + 预计省多少 + 风险"。
8. 已经做过的优化**不许再提**（见"已经做过的优化"）。要基于它们往下一层想。
9. 若某条建议会让文风变差（比如砍掉审读、缩短上下文），必须**明写代价**。"""

_SCHEMA = """回这个 JSON（字段可以少，不许改名）：
{
  "summary": "一句话结论（不超过 40 字）",
  "where": [{"purpose": "用途名", "why": "它为什么贵/为什么能省"}],
  "config_changes": [{"key": "配置键", "now": "当前值", "suggest": "建议值",
                      "why": "为什么", "expect": "预计省多少"}],
  "model_changes": [{"tier": "front|daily|cheap", "now": "现在用的", "suggest": "模型登记表里的 key",
                     "why": "为什么", "expect": "预计省多少"}],
  "software": [{"title": "标题", "how": "改哪里、怎么改", "expect": "预计省多少", "risk": "代价/风险"}]
}"""


def build_messages(f: dict, deep: bool = False) -> list[dict]:
    """把素材拼成两条消息（system 规则 + user 数据）。
        English:
    Fold the material into two messages (system rules + user data).
    """
    rules = _RULES + (_DEEP_RULES if deep else '')
    task = ('请做**深度优化**：给软件层建议（software 至少 3 条），'
            '配置与模型建议有就给。' if deep else
            '请做常规优化建议：重点在 config_changes 与 model_changes，'
            'software 最多 2 条（那是下一层的事）。')
    body = json.dumps(f, ensure_ascii=False, indent=1)
    return [{'role': 'system', 'content': rules + '\n\n' + _SCHEMA},
            {'role': 'user', 'content': task + '\n\n数据：\n' + body}]


# ══════════════════════════════════════════════════════════════════
#  调模型（一次调用）
# [EN] One model call
# ══════════════════════════════════════════════════════════════════
def advisor_tier() -> str:
    """这次分析用哪一档（读配置 `COST_ADVISOR_TIER`，认不出就退回 cheap）。
        English:
    Which tier this analysis uses (from `COST_ADVISOR_TIER`, falling back to `cheap`).
    """
    from config import CFG
    v = (CFG.s('COST_ADVISOR_TIER') or 'daily').strip().lower()
    return v if v in TIER_KEYS else 'daily'


async def advise(days: float | None = 7, *, deep: bool = False,
                 scope: str | None = None) -> dict:
    """跑一次分析。返回 `{'ok': bool, 'data': {...}, 'error': str, 'meta': {...}}`。

    ★ **永不抛**：分析失败只把原因写在 `error` 里 —— 它是设置页上的一个按钮，
      点一下炸掉整个天机（实测过：`flet` 吞异常 ⇒ 对话框再也开不出来）。
    
        English:
    Run one analysis. Returns `{'ok': ..., 'data': ..., 'error': ..., 'meta': ...}`.
        ★ **Never throws**: a failed analysis just reports why in `error` -- it is a button on
          a settings page, and blowing up would take Tianji down with it.
    """
    from llm.router import llm
    f = facts(days, scope=scope, deep=deep)
    tier = advisor_tier()
    t0 = time.time()
    try:
        raw = await llm.chat(tier, build_messages(f, deep),
                             purpose='cost_deep' if deep else 'cost_advice',
                             json_mode=True, temperature=0.3, max_tokens=2600)
    except Exception as e:                                       # noqa: BLE001
        msg = f'{type(e).__name__}: {e}'
        log_line(f'分析失败（{"深度" if deep else "常规"}）: {msg}')
        return {'ok': False, 'data': {}, 'error': msg,
                'meta': {'tier': tier, 'seconds': round(time.time() - t0, 1)}}
    data = parse_advice(raw)
    took = round(time.time() - t0, 1)
    if not data:
        log_line(f'分析返回的不是 JSON（{"深度" if deep else "常规"}），原文前 400 字：'
                 f'{(raw or "")[:400]}')
        return {'ok': False, 'data': {}, 'error': '模型返回的不是 JSON，换一档模型再试',
                'meta': {'tier': tier, 'seconds': took, 'raw': (raw or '')[:1200]}}
    log_line(f'分析完成（{"深度" if deep else "常规"}，{tier}，{took}s）：'
             f'summary={data.get("summary", "")}；'
             f'改配置 {len(data.get("config_changes") or [])} 条、'
             f'换模型 {len(data.get("model_changes") or [])} 条、'
             f'软件层 {len(data.get("software") or [])} 条')
    return {'ok': True, 'data': data, 'error': '',
            'meta': {'tier': tier, 'seconds': took},
            'facts': f}


def parse_advice(raw: str) -> dict:
    """把模型回的那段文本解析成字典；**解析不出来返回 `{}`**（不抛、不猜）。
        English:
    Parse the model's reply into a dict; **returns `{}` when it cannot** (no throw, no guessing).
    """
    from util.jsonio import extract_json
    v = extract_json(raw or '', default=None)
    if not isinstance(v, dict):
        return {}
    # 只认这几个字段，其余丢掉（模型偶尔会自己加字段，前端不该被它牵着走）
    # [EN] Only keep these fields; drop the rest (models sometimes invent extra keys)
    out: dict = {}
    if isinstance(v.get('summary'), str):
        out['summary'] = v['summary'].strip()[:200]
    for k in ('where', 'config_changes', 'model_changes', 'software'):
        items = v.get(k)
        out[k] = [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    return out


# ══════════════════════════════════════════════════════════════════
#  应用建议（白名单 + 类型校验）
# [EN] Apply advice (whitelist + type check)
# ══════════════════════════════════════════════════════════════════
def check_change(key: str, value) -> tuple[bool, str, object]:
    """这条建议能不能写。返回 `(能不能, 给人看的一句话, 生效值)`。

    三道闸（见模块开头）：白名单 → `SPEC` 里有 → `coerce()` 认。
    ★ 值被**夹紧**（比如上限 100 写了 999）算能写，但会如实说出来；
      值被**打回默认**（枚举不认识 / 解析失败）算不能写 —— 那等于没改，
      而用户会以为改了。
    
        English:
    Whether this suggestion can be written. Returns `(ok, message, effective_value)`.
        Three gates: whitelist -> present in `SPEC` -> accepted by `coerce()`. A **clamped**
        value is allowed but reported; a value **reset to default** (unknown enum / unparsable)
        is rejected -- that means nothing changed while the user thinks it did.
    """
    k = str(key or '').strip()
    if not k:
        return False, '没有给配置键', None
    if k not in APPLICABLE:
        return False, f'{k} 不在可自动应用的清单里（要改请去对应页签手动改）', None
    from config import SPEC, coerce
    spec = SPEC.get(k)
    if not spec:
        return False, f'配置表里没有 {k} 这一项（模型可能编了个键名）', None
    raw = str(value)
    v, warn = coerce(k, raw)
    if warn:
        if '回默认' in warn or '无法解析' in warn:
            return False, warn, None
        return True, warn, v
    if spec.get('type') in ('int', 'float') and isinstance(value, bool):
        return False, f'{k} 要的是数字，给的是布尔值', None
    return True, '', v


def apply_change(key: str, value, *, save: bool = True) -> tuple[bool, str]:
    """写进 `.env`（`CFG` 内存 + 落盘）。返回 `(成功?, 一句话)`。
        English:
    Write into `.env` (in-memory `CFG` + persist). Returns `(ok, message)`.
    """
    ok, msg, eff = check_change(key, value)
    if not ok:
        log_line(f'拒绝应用 {key}={value!r}：{msg}')
        return False, msg
    from config import CFG
    before = CFG.raw(key) if hasattr(CFG, 'raw') else CFG.s(key)
    CFG.set(key, str(eff))
    err = None
    if save:
        try:
            CFG.save()
        except Exception as e:                                   # noqa: BLE001
            err = f'{type(e).__name__}: {e}'
    log_line(f'应用 {key}: {before!r} → {eff!r}'
             + (f'（落盘失败：{err}）' if err else '（已写入 .env）'))
    if err:
        return False, f'写内存成功，但落盘失败：{err}'
    return True, f'{key}：{before} → {eff}' + (f'（{msg}）' if msg else '')


def apply_model(tier: str, key: str, *, save: bool = True) -> tuple[bool, str]:
    """把某一档换成登记表里的某个模型。返回 `(成功?, 一句话)`。

    ⚠ 校验的是**登记表里有没有这个 key**，不是"名字像不像"：
      把 `MODEL_CHEAP` 写成一个不存在的 key ⇒ 那一档解析不到模型，
      退回第一条，界面上看着"配了"，实际没用上。
    
        English:
    Point a tier at a model from the registry. Validates that the key **exists in the
    registry**, not that the name looks right: an unknown key makes that tier unresolvable
    (it silently falls back to the first entry) while the UI still shows it as configured.
    """
    t = str(tier or '').strip().lower()
    if t not in TIER_KEYS:
        return False, f'没有「{tier}」这一档（只有 主力/日常/便宜）'
    from llm import models as MODELS
    items = MODELS.ensure_ready()
    hit = next((e for e in items if e.key == key), None)
    if hit is None:
        log_line(f'拒绝换模型 {t} → {key!r}：登记表里没有这个键')
        return False, f'登记表里没有 {key} 这个模型（先在「AI模型配置」里加一条）'
    from config import CFG
    field = _TIER_FIELD[t]
    before = CFG.s(field)
    CFG.set(field, hit.key)
    err = None
    if save:
        try:
            CFG.save()
        except Exception as e:                                   # noqa: BLE001
            err = f'{type(e).__name__}: {e}'
    log_line(f'换模型 {t}（{field}）: {before!r} → {hit.key!r}'
             + (f'（落盘失败：{err}）' if err else '（已写入 .env，重启后生效）'))
    if err:
        return False, f'写内存成功，但落盘失败：{err}'
    return True, f'{TIER_LABEL[t]}：{before or "（默认）"} → {hit.display()}'


def export_markdown(result: dict, *, out: Path | None = None) -> Path:
    """把一次分析结果落成 md（用户要"记录单独的日志"，这是**内容**那份）。

    ⚠ 与 `text` 报表不同：报表每次现算，这一份是**某一次建议的存档** ——
      以后回看"上次为什么这么改"靠它。
    
        English:
    Save one analysis result as markdown (the **content** log the user asked for).
        ⚠ Unlike the text report (recomputed every time), this is an archive of one
        suggestion set -- it is how "why did I change this last time" gets answered.
    """
    d = log_path().parent / 'cost_advice'
    d.mkdir(parents=True, exist_ok=True)
    p = out or d / time.strftime('advice_%Y%m%d_%H%M%S.md')
    data = result.get('data') or {}
    meta = result.get('meta') or {}
    lines = [f'# 花费分析 · {time.strftime("%Y-%m-%d %H:%M")}', '',
             f'- 窗口：{meta.get("window", "")}', f'- 用的模型档：{meta.get("tier", "")}',
             f'- 耗时：{meta.get("seconds", "")}s', '',
             '## 结论', '', data.get('summary', '（无）'), '']
    if data.get('where'):
        lines += ['## 钱花在哪', '']
        for x in data['where']:
            lines.append(f'- **{x.get("purpose", "")}**：{x.get("why", "")}')
        lines.append('')
    for key, title in (('config_changes', '改配置'), ('model_changes', '换模型'),
                       ('software', '软件层面')):
        items = data.get(key) or []
        if not items:
            continue
        lines += [f'## {title}', '']
        for x in items:
            if key == 'config_changes':
                lines.append(f'- `{x.get("key", "")}`：{x.get("now", "")} → '
                             f'{x.get("suggest", "")}（{x.get("why", "")}；'
                             f'{x.get("expect", "")}）')
            elif key == 'model_changes':
                lines.append(f'- {x.get("tier", "")}：{x.get("now", "")} → '
                             f'{x.get("suggest", "")}（{x.get("why", "")}；'
                             f'{x.get("expect", "")}）')
            else:
                lines.append(f'- **{x.get("title", "")}** —— {x.get("how", "")}'
                             f'（预计 {x.get("expect", "")}；风险 {x.get("risk", "")}）')
        lines.append('')
    try:
        p.write_text('\n'.join(lines), encoding='utf-8')
        log_line(f'分析结果已存档：{p}')
    except Exception as e:                                       # noqa: BLE001
        log_line(f'存分析结果失败：{e!r}')
    return p


#: CSV 的列（**顺序就是屏幕上的顺序**）。`desc_rows()` 的键名一一对应。
# [EN] CSV columns, in the same order as the on-screen table.
CSV_COLUMNS = (
    ('purpose', '用途'),
    ('desc', '描述'),
    ('calls', '调用次数'),
    ('in_tok', '输入 token'),
    ('out_tok', '输出 token'),
    ('hit', '命中率'),
    ('share', '占比'),
    ('cost', '花费（元）'),
)


def csv_path(days: float | None = 7, *, out: Path | None = None) -> Path:
    """导出的 CSV 落在哪（文件名带范围与时间戳，**不覆盖旧的**）。
        English:
    Where the CSV goes (name carries the window and a timestamp -- never overwrites an old one).
    """
    if out is not None:
        return Path(out)
    d = log_path().parent / 'cost_report'
    d.mkdir(parents=True, exist_ok=True)
    tag = 'all' if days is None else f'{float(days):g}d'
    return d / time.strftime(f'cost_{tag}_%Y%m%d_%H%M%S.csv')


def export_csv(days: float | None = 7, *, scope: str | None = None,
               path: Path | None = None, out: Path | None = None) -> Path:
    """把「按用途」那张表导成 CSV（**Excel 双击就能开**）。返回文件路径。

    ★★★ 三个必须：
      ① **`utf-8-sig`**（带 BOM）：不带 BOM 的 UTF-8，Excel 双击打开是乱码 ——
         而"乱码"在作者眼里等于"导出坏了"，他不会去研究编码。
      ② **`csv` 模块**，不许 `','.join`：描述里有逗号（"时间、物件、称呼"这类改写）、
         有引号，手拼一次就把整行错列 —— 而且错得整齐，看着像数据本来就那样。
      ③ **列头跟着 `CSV_COLUMNS` 走**（与屏幕同一份顺序），别在这里另写一串中文。
    ⚠ 不加"合计"行：加在表里，`pandas.read_csv` 会把那一行读成 NaN；
      合计在页面上已经写了，CSV 只负责"能被别的工具吃进去"。
    [EN] Export the "by purpose" table as CSV (opens by double-click in Excel).
    ★★★ Three musts: ① `utf-8-sig` (BOM) or Excel shows mojibake and the author concludes
    "export is broken"; ② use the `csv` module, never `','.join` -- descriptions contain commas
    and quotes, and a hand-joined row is silently misaligned; ③ headers come from `CSV_COLUMNS`
    so the order matches the screen. ⚠ No totals row: it would read as NaN in `pandas.read_csv`.
    """
    ov = overview(days, scope, path)
    rows = desc_rows(ov)
    p = csv_path(days, out=out)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline='' 是 `csv` 模块的硬要求（否则 Windows 上每行多一个空行）
    # [EN] newline='' is required by the csv module, or Windows gets a blank line per row.
    with p.open('w', encoding='utf-8-sig', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow([h for _k, h in CSV_COLUMNS])
        for r in rows:
            wr.writerow([
                r['purpose'], r['desc'], r['calls'], r['in_tok'], r['out_tok'],
                f'{r["hit"]:.4f}', f'{r["share"]:.4f}', f'{r["cost"]:.4f}',
            ])
    log_line(f'导出 CSV：{p}（{len(rows)} 行，范围 '
             f'{"全部历史" if days is None else f"{float(days):g} 天"}）')
    return p


# ══════════════════════════════════════════════════════════════════
#  自检（判据与"我到底连的是哪个库"用）
# [EN] Self-check (for criteria and "which DB am I reading")
# ══════════════════════════════════════════════════════════════════
def db_file() -> Path:
    """报表读的是哪个库（界面上要显示出来 —— 不然"为什么是 0"查不动）。
        English:
    Which database the report reads (shown in the UI, otherwise "why is it 0" is unanswerable).
    """
    return U.db_path()
