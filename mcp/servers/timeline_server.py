# -*- coding: utf-8 -*-
"""MCP 服务器：故事线考据（读运行文件夹）。

和 project_lore_server 的分工：
  - project_lore_server 读「设定集」——写小说**之前**定下来的东西（人物、伏笔、进度表）
  - 本服务器读「运行文件夹」——**已经发生**的东西（每天的生活、关键事件卡、运行小结）

这是写续章前最需要的一类查询：「前面到底发生了什么事」。

工具
    run_overview   运行概况（几次模拟、跑了多少天、多少事件）
    day_index      已生成的日清单
    recent_days    最近 N 天的正文（默认 3）
    key_events     关键事件卡
    story_so_far   已发生故事线.md
    search_run     运行文件夹全文检索

运行
    python mcp/servers/timeline_server.py --project-dir "E:\\小说\\我的项目"
自检
    python mcp/servers/timeline_server.py --call recent_days '{"n":2}'

English:
MCP server: story timeline lore lookup (reads the run folder).
Division of labor with project_lore_server:
  - project_lore_server reads the "setting collection" — things decided **before** writing the novel (characters, foreshadowing, progress table)
  - this server reads the "run folder" — things that **have already happened** (daily life, key event cards, run summaries)
This is the most needed type of query before writing a sequel chapter: "what exactly happened
earlier".
Tools
    run_overview   run overview (how many simulations, how many days run, how many events)
    day_index      list of generated days
    recent_days    body text of the most recent N days (default 3)
    key_events     key event cards
    story_so_far   story_so_far.md
    search_run     full-text search of the run folder
Run
Self-check
    python mcp/servers/timeline_server.py --call recent_days '{"n":2}'
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mcpkit import Server, text_result, error_result, serve  # noqa: E402
import _projectfs as PF  # noqa: E402

srv = Server(
    'nws-timeline', '1.0.0',
    instructions=(
        '查询一部小说**已经发生过**的内容：每日正文、关键事件、已发生故事线。\n'
        '写续章前先用它回忆前情。只读，不修改任何数据。\n'
        '建议顺序：run_overview → recent_days / key_events → 需要细节时 search_run。'))


def _resolve():
    """返回 (root, 错误文本)；错误文本非空时应当直接 error_result 返回。
        English:
    Returns (root, error_text); when error_text is non-empty, it should be returned directly as
    error_result.
    """
    try:
        return PF.resolve_project_dir(), ''
    except PF.ProjectNotFound as e:
        return None, str(e)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f'\n…（已截断，共 {len(text)} 字）'


@srv.tool('run_overview', '运行概况：几次模拟、各跑了多少天、多少事件卡')
def run_overview(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    runs = PF.run_dirs(root)
    if not runs:
        return error_result(
            f'还没跑过模拟（{root} 下没有「第N次模拟…」文件夹）。')

    lines = [f'项目：{root.name}｜共 {len(runs)} 次模拟', '']
    for r in runs:
        days = sorted((r / PF.DAILY_DIR).glob('*')) if (r / PF.DAILY_DIR).is_dir() else []
        events = sorted((r / PF.EVENT_DIR).glob('*')) if (r / PF.EVENT_DIR).is_dir() else []
        lines.append(f'· {r.name}：{len(days)} 天正文、{len(events)} 个事件卡')
    latest = runs[-1]
    lines += ['', f'最新一次：{latest.name}']
    summary = latest / '运行小结.md'
    if summary.exists():
        lines.append('（已有运行小结.md）')
    return text_result('\n'.join(lines))


@srv.tool('day_index', '已生成的日子清单（跨全部运行，按顺序）')
def day_index(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    files = PF.daily_files(root)
    if not files:
        return error_result('还没有「每天的生活」产物。')
    lines = [f'共 {len(files)} 天：']
    lines += [f'- {p.stem}' for p in files]
    return text_result('\n'.join(lines))


@srv.tool('recent_days', '最近 N 天的正文（默认 3 天），写续章前回忆前情用',
          {'n': {'type': 'integer', 'description': '要几天，默认 3，最多 20'},
           'chars': {'type': 'integer', 'description': '每天最多返回多少字，默认 1200'}})
def recent_days(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    try:
        n = max(1, min(20, int(args.get('n') or 3)))
    except (TypeError, ValueError):
        n = 3
    try:
        chars = max(200, min(20000, int(args.get('chars') or 1200)))
    except (TypeError, ValueError):
        chars = 1200

    files = PF.daily_files(root)
    if not files:
        return error_result('还没有「每天的生活」产物，无法回忆前情。')

    picked = files[-n:]
    blocks = []
    for p in picked:
        body = PF.read_text(p).strip()
        blocks.append(f'══ {p.stem} ══\n{_clip(body, chars)}')
    header = (f'最近 {len(picked)} 天（共 {len(files)} 天）'
              + ('' if len(files) <= n else f'，未显示前 {len(files) - n} 天'))
    return text_result(header + '\n\n' + '\n\n'.join(blocks))


@srv.tool('key_events', '关键事件卡（时间/参与者/经过/分支）',
          {'limit': {'type': 'integer', 'description': '最多几个，默认 5（取最新）'}})
def key_events(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    try:
        limit = max(1, min(50, int(args.get('limit') or 5)))
    except (TypeError, ValueError):
        limit = 5

    files = PF.event_files(root)
    if not files:
        return error_result('还没有关键事件卡。')

    picked = files[-limit:]
    blocks = []
    for p in picked:
        blocks.append(f'── {p.stem} ──\n{_clip(PF.read_text(p), 900)}')
    return text_result(f'最新 {len(picked)} / {len(files)} 个事件：\n\n'
                       + '\n\n'.join(blocks))


@srv.tool('story_so_far', '已发生故事线（按进度节点整理的「前情提要」）')
def story_so_far(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    sd = PF.settings_dir(root)
    for candidate in ([sd / PF.STORY_SO_FAR] if sd else []) + \
                     [r / PF.LOCAL_SETTINGS_DIR / PF.STORY_SO_FAR
                      for r in reversed(PF.run_dirs(root))]:
        if candidate and candidate.exists():
            text = PF.read_text(candidate).strip()
            if text:
                return text_result(f'（来源：{candidate.name}）\n\n{_clip(text, 6000)}')
    return error_result('还没有「已发生故事线.md」。')


@srv.tool('search_run', '在运行文件夹里全文检索（找某个地名/台词/事件的出处）',
          {'query': {'type': 'string', 'description': '关键词'},
           'limit': {'type': 'integer', 'description': '最多几条，默认 5'}},
          required=['query'])
def search_run(args):
    root, err = _resolve()
    if err:
        return error_result(err)

    query = str(args.get('query', '')).strip()
    if not query:
        return error_result('请给一个关键词。')
    try:
        limit = max(1, min(20, int(args.get('limit') or 5)))
    except (TypeError, ValueError):
        limit = 5

    hits = PF.search(root, query, limit=limit)
    if not hits:
        return text_result(f'运行文件夹里没有「{query}」。')
    body = '\n\n'.join(f'— {h["文件"]}:{h["行号"]}\n{h["片段"]}' for h in hits)
    return text_result(f'命中 {len(hits)} 处：\n\n{body}')


if __name__ == '__main__':
    serve(srv)
