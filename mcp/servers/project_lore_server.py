# -*- coding: utf-8 -*-
"""MCP 服务器：项目考据（读设定集）。

给它一个小说项目目录，它把设定集里的东西变成可查询的工具——
这样 LLM 想「主角的秘密是什么」时，不必把整本设定集塞进上下文，
而是调一个工具、拿回一张卡。

工具
    project_overview   项目概况（人物数、运行次数、设定集位置）
    character          查某个人物卡
    list_characters    人物名录
    foreshadows        伏笔清单（可按状态筛）
    worldview          世界观 + 剧情走向
    progress           故事进度表节点
    lore_search        设定集全文检索（带文件名与行号）

运行（一般由 MCP 客户端拉起，不手工跑）
    python mcp/servers/project_lore_server.py --project-dir "E:\\小说\\我的项目"
自检
    python mcp/servers/project_lore_server.py --list-tools
    python mcp/servers/project_lore_server.py --call list_characters

English:
MCP server: project lore (reads the settings collection).
Give it a novel project directory, and it turns the contents of the settings collection into
queryable tools--
so when the LLM wants to know "what is Shen Yan's secret", it doesn't have to stuff the entire
settings collection into context,
but instead calls a tool and gets back a card.
Tools
    project_overview   Project overview (character count, run count, settings collection location)
    character          Look up a character card
    list_characters    Character roster
    foreshadows        Foreshadowing list (filterable by status)
    worldview          Worldview + plot direction
    progress           Story progress table nodes
    lore_search        Full-text search of the settings collection (with filename and line number)
Run (usually launched by the MCP client, not run manually)
Self-check
    python mcp/servers/project_lore_server.py --list-tools
    python mcp/servers/project_lore_server.py --call list_characters
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让 `from _mcpkit import ...` 在本脚本目录下可用（客户端可能从任意 cwd 拉起）
# [EN] Make `from _mcpkit import ...` available in this script's directory (the client may launch from
# [EN] any cwd)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mcpkit import Server, json_result, text_result, error_result, serve  # noqa: E402
import _projectfs as PF  # noqa: E402

srv = Server(
    'nws-project-lore', '1.0.0',
    instructions=(
        '查询一部小说的项目设定集：人物卡、世界观、伏笔、故事进度、设定集全文检索。\n'
        '这是**只读**服务，不会修改任何小说数据。\n'
        '用法：先 project_overview 摸清项目，再按需查具体条目；'
        '找不准名字时用 lore_search 搜关键词。'))

QUERY = {'query': {'type': 'string', 'description': '关键词，例如人物名、地名、事件'}}


@srv.tool('project_overview', '项目概况：设定集位置、人物数量、运行次数、人物名录')
def project_overview(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))
    return text_result(PF.summarize_for_humans(root))


@srv.tool('character', '查某个人物卡（姓名/身份/性格/口癖/秘密/目标/红线）',
          {'name': {'type': 'string', 'description': '人物姓名，可只写一个字'}},
          required=['name'])
def character(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    name = str(args.get('name', '')).strip()
    if not name:
        return error_result('请给一个姓名。')

    found = PF.find_character(root, name)
    if not found:
        people = PF.characters(root)
        if not people:
            return error_result(
                '设定集里没有人物卡（可能还没摄取，或项目目录给错了）。')
        return error_result(
            f'没找到「{name}」。现有：'
            + '、'.join(str(c.get('姓名', '?')) for c in people))

    # 只保留有内容的字段，避免一屏 None
    # [EN] Keep only fields with content, avoid a screen full of None
    lines = [f'【{found.get("姓名", name)}】']
    for key in ('身份', '简介', '性格', '口癖', '秘密', '目标', '红线'):
        val = found.get(key)
        if val:
            lines.append(f'- {key}：{val}')
    for key, val in found.items():              # 设定集里可能多出别的字段
    # [EN] The settings collection may contain extra fields
        if key not in ('姓名', '身份', '简介', '性格', '口癖', '秘密',
                       '目标', '红线') and val:
            lines.append(f'- {key}：{val}')
    return text_result('\n'.join(lines))


@srv.tool('list_characters', '人物名录（姓名 + 身份 + 一句话）')
def list_characters(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    people = PF.characters(root)
    if not people:
        return error_result('设定集里没有人物卡。')
    lines = [f'共 {len(people)} 位：']
    for c in people:
        name = c.get('姓名', '?')
        role = c.get('身份', '')
        brief = str(c.get('简介', '') or c.get('性格', '')).strip()
        lines.append(f'- {name}（{role}）{brief[:60]}' if role
                     else f'- {name} {brief[:60]}')
    return text_result('\n'.join(lines))


@srv.tool('foreshadows', '伏笔与悬线清单',
          {'status': {'type': 'string',
                      'description': '按状态筛，如 未回收 / 已回收；留空看全部'}})
def foreshadows(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    items = PF.foreshadows(root)
    if not items:
        return error_result('设定集里没有伏笔记录。')

    want = str(args.get('status', '') or '').strip()
    if want:
        items = [f for f in items
                 if want in str(f.get('状态', '')) or want in str(f.get('内容', ''))]
        if not items:
            return error_result(f'没有状态含「{want}」的伏笔。')

    lines = [f'共 {len(items)} 条伏笔：']
    for f in items:
        no = f.get('编号', '')
        content = f.get('内容', '')
        placed = f.get('埋设', '')
        expect = f.get('预计回收', '')
        state = f.get('状态', '')
        head = f'- {no} ' if no else '- '
        lines.append(f'{head}{content}')
        tail = [x for x in (f'埋设：{placed}' if placed else '',
                            f'预计回收：{expect}' if expect else '',
                            state) if x]
        if tail:
            lines.append('  ' + ' · '.join(tail))
    return text_result('\n'.join(lines))


@srv.tool('worldview', '世界观与剧情走向（两条主线的参考）')
def worldview(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    sd = PF.settings_dir(root)
    if not sd:
        return error_result('找不到设定集目录。')

    blocks = []
    for label, fname in (('世界观', PF.WORLDVIEW), ('剧情走向', PF.PLOT)):
        text = PF.read_text(sd / fname).strip()
        if text:
            blocks.append(f'## {label}\n{text}')
    if not blocks:
        return error_result('设定集里没有世界观或剧情走向文件。')
    return text_result('\n\n'.join(blocks))


@srv.tool('progress', '故事进度表的节点列表（含完成状态）')
def progress(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    nodes = PF.progress_nodes(root)
    if not nodes:
        return error_result('还没有故事进度表（摄取时会生成）。')

    done = 0
    lines = [f'共 {len(nodes)} 个节点：']
    for n in nodes:
        nid = n.get('id') or n.get('编号') or ''
        name = n.get('name') or n.get('名称') or ''
        state = str(n.get('状态', '') or n.get('status', ''))
        judge = n.get('判据') or n.get('完成判据') or ''
        mark = '✅' if ('完成' in state or '已' in state) else '⬜'
        if mark == '✅':
            done += 1
        lines.append(f'{mark} {nid} {name}' + (f'（{judge}）' if judge else ''))
    lines.insert(1, f'已推进 {done} / {len(nodes)}')
    return text_result('\n'.join(lines))


@srv.tool('lore_search', '设定集全文检索，返回命中片段与所在文件/行号',
          {**QUERY, 'limit': {'type': 'integer', 'description': '最多返回几条，默认 5'}},
          required=['query'])
def lore_search(args):
    try:
        root = PF.resolve_project_dir()
    except PF.ProjectNotFound as e:
        return error_result(str(e))

    query = str(args.get('query', '')).strip()
    if not query:
        return error_result('请给一个关键词。')
    try:
        limit = max(1, min(20, int(args.get('limit') or 5)))
    except (TypeError, ValueError):
        limit = 5

    hits = PF.search(root, query, limit=limit, include_runs=False)
    if not hits:
        return text_result(f'设定集里没有「{query}」。')
    body = '\n\n'.join(f'— {h["文件"]}:{h["行号"]}\n{h["片段"]}' for h in hits)
    return text_result(f'命中 {len(hits)} 处：\n\n{body}')


if __name__ == '__main__':
    serve(srv)
