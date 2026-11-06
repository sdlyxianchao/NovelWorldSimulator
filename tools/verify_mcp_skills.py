#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真机验证：MCP 服务器 + 技能系统。

MCP 是**独立进程**，没法只靠读代码确认它能用，所以这里真的：
  1. 起进程、走完 initialize 握手、读 tools/list
  2. 对每个工具发真实的 tools/call，断言返回里有预期内容
  3. 造一个临时小说项目当靶子（设定集 + 运行文件夹），验证真的读到了数据
  4. 检查协议层行为：未知方法的错误码、缺参数、业务失败用 isError 而非错误码
  5. 检查 stdout 纯净（MCP 的硬要求：往 stdout 写杂字会让客户端解析失败）
  6. 走一遍 MCPClient（app 真正用的入口）与考据通道的整合

技能侧：注册表能加载、frontmatter 完整、关键词路由命中、附带脚本能跑通。

产出：assets/screenshots/mcp_skills_report.json
退出码：0 = 全过，2 = 有失败

English:
Real-machine verification: MCP server + skill system.
MCP is an **independent process**; you can't confirm it works just by reading code, so here we
actually:
  1. spawn the process, complete the initialize handshake, read tools/list
  2. send a real tools/call for each tool, assert the response contains the expected content
  3. create a temporary novel project as the target (settings collection + run folder), verify it really reads the data
  4. check protocol layer behavior: error code for unknown methods, missing params, business failures use isError rather than error codes
  5. check stdout purity (an MCP hard requirement: writing junk to stdout makes the client fail to parse)
  6. walk through the integration of MCPClient (the entry point the app actually uses) with the research channel
Skill side: registry can load, frontmatter complete, keyword routing hits, bundled scripts run.
Output: assets/screenshots/mcp_skills_report.json
Exit code: 0 = all pass, 2 = has failures
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

VERBOSE = '-v' in sys.argv or '--verbose' in sys.argv
PY = sys.executable
SERVERS_DIR = APP_DIR / 'mcp' / 'servers'
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    mark = '[OK]  ' if ok else '[FAIL]'
    print(f'  {mark} {name}' + (f'  — {detail}' if detail else ''), flush=True)
    return bool(ok)


def head(title: str) -> None:
    print(f'\n── {title} ──', flush=True)


def line_at(text: str, i: int, width: int = 60) -> str:
    """安全取第 i 行（响应可能是单行，直接 [1] 会 IndexError）。
        English:
    Safely take the i-th line (the response may be a single line; directly using [1] would raise
    IndexError).
    """
    lines = (text or '').splitlines()
    if not lines:
        return ''
    return (lines[i] if i < len(lines) else lines[-1])[:width]


# ══════════════════════════════════════════════════════════════
#  靶子：一个临时小说项目
# [EN] Target: a temporary novel project
# ══════════════════════════════════════════════════════════════
def make_fixture() -> Path:
    root = Path(tempfile.mkdtemp(prefix='nws_mcp_'))
    settings = root / '设定集'
    settings.mkdir(parents=True)

    (root / '雨夜来客.nwsproj').write_text(
        '[项目]\n名称=雨夜来客\n', encoding='utf-8')
    (settings / '人物.yaml').write_text(
        '- 姓名: 主角\n'
        '  身份: 掌柜\n'
        '  简介: 主角，沉默寡言，凡事先看三步。\n'
        '  性格: 沉默寡言\n'
        '  口癖: " ……"\n'
        '  秘密: 曾替人顶过一件说不得的罪\n'
        '  目标: 把当年那件事彻底掩过去\n'
        '  红线: 不主动伤人\n'
        '- 姓名: 阿枝\n'
        '  身份: 伙计\n'
        '  性格: 嘴上不饶人，心却软\n', encoding='utf-8')
    (settings / '世界观.md').write_text(
        '一座常年落雨的临河小城，人情密、口风紧，旧事压在青石板底下。\n',
        encoding='utf-8')
    (settings / '剧情走向.md').write_text(
        '起：雨夜来客打破平静；合：有人离开，有人留下。\n', encoding='utf-8')
    (settings / '伏笔与悬线.yaml').write_text(
        '- 编号: F01\n  内容: 后院那口井夜里会响\n  埋设: 开篇\n  预计回收: 中段\n'
        '- 编号: F02\n  内容: 主角腕上的旧痕\n  埋设: 第一章\n  状态: 未回收\n',
        encoding='utf-8')
    (settings / '故事进度.yaml').write_text(
        '节点:\n'
        '- id: N01\n  name: 开端\n  判据: 雨夜来客登场\n'
        '- id: N02\n  name: 破绽\n  状态: 已完成\n', encoding='utf-8')
    (settings / '已发生故事线.md').write_text(
        '# 已发生故事线\n\n## N02 破绽\n最可信的人露出破绽。\n', encoding='utf-8')

    run = root / '第1次模拟2026-10-05-10-00'
    (run / '每天的生活').mkdir(parents=True)
    (run / '关键事件').mkdir(parents=True)
    (run / '每天的生活' / '第1天.md').write_text(
        '# 第1天\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n'
        '主角没有抬头。\n', encoding='utf-8')
    (run / '每天的生活' / '第2天.md').write_text(
        '# 第2天\n\n阿枝把井绳收了起来。\n', encoding='utf-8')
    (run / '关键事件' / 'E01-雨夜来客.md').write_text(
        '# 雨夜来客\n\n时间：第1天 戌时\n参与者：主角、陌生人\n'
        '经过：来人自称旧识，却不肯说姓名。\n', encoding='utf-8')
    return root


# ══════════════════════════════════════════════════════════════
#  MCP 协议：直接开进程说 JSON-RPC
# [EN] MCP protocol: spawn a process directly and speak JSON-RPC
# ══════════════════════════════════════════════════════════════
class StdioClient:
    """最小的 MCP 客户端，只为本脚本验证用（app 用的是 mcp/client.py）。
        English:
    Minimal MCP client, used only for this script's verification (the app uses mcp/client.py).
    """

    def __init__(self, script: Path, project_dir: Path | None = None):
        cmd = [PY, str(script)]
        if project_dir is not None:
            cmd += ['--project-dir', str(project_dir)]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=str(APP_DIR))
        self.raw_lines: list[str] = []
        self._id = 0

    def send(self, method: str, params: dict | None = None) -> dict | None:
        self._id += 1
        payload = {'jsonrpc': '2.0', 'id': self._id, 'method': method}
        if params is not None:
            payload['params'] = params
        self.proc.stdin.write((json.dumps(payload) + '\n').encode('utf-8'))
        self.proc.stdin.flush()
        line = self.proc.stdout.readline().decode('utf-8', 'replace').strip()
        self.raw_lines.append(line)
        return json.loads(line) if line else None

    def notify(self, method: str) -> None:
        self.proc.stdin.write(
            (json.dumps({'jsonrpc': '2.0', 'method': method}) + '\n').encode('utf-8'))
        self.proc.stdin.flush()

    def call(self, tool: str, args: dict | None = None) -> dict | None:
        return self.send('tools/call', {'name': tool, 'arguments': args or {}})

    def text_of(self, resp: dict | None) -> str:
        if not resp or 'result' not in resp:
            return ''
        return '\n'.join(b.get('text', '')
                         for b in resp['result'].get('content') or []
                         if isinstance(b, dict))

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def test_protocol(script: Path, project: Path, tools: list[str],
                  expectations: dict) -> bool:
    """握手 + 列工具 + 逐工具实调 + 协议错误码。
        English:
    Handshake + list tools + per-tool real calls + protocol error codes.
    """
    name = script.stem
    ok = True
    cli = StdioClient(script, project)
    try:
        init = cli.send('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'nws-verify', 'version': '1'}})
        assert init and 'result' in init, f'initialize 失败: {init}'
        info = init['result'].get('serverInfo') or {}
        ok &= rec(f'{name}: initialize 握手',
                  bool(info.get('name')) and 'protocolVersion' in init['result'],
                  f'{info.get("name")} v{info.get("version")}')

        cli.notify('notifications/initialized')

        listed = cli.send('tools/list').get('result', {}).get('tools') or []
        got = sorted(t['name'] for t in listed)
        ok &= rec(f'{name}: tools/list 工具齐全', got == sorted(tools),
                  f'{len(got)} 个：{"、".join(got)}')

        # 每个工具都要有描述和合法的 inputSchema，否则 LLM 不会用
        # [EN] Every tool must have a description and a valid inputSchema, otherwise the LLM won't use it
        bad = [t['name'] for t in listed
               if not t.get('description')
               or (t.get('inputSchema') or {}).get('type') != 'object']
        ok &= rec(f'{name}: 每个工具的 schema 合法', not bad,
                  '缺描述或 schema 非 object：' + '、'.join(bad) if bad else '')

        # 实调每个工具（用 expectations 里给的参数；没给就空参）
        # [EN] Actually call each tool (using the arguments given in expectations; if none given, use empty
        # [EN] args)
        for tool in tools:
            args = expectations.get(tool, {})
            resp = cli.call(tool, args)
            text = cli.text_of(resp)
            is_err = bool((resp or {}).get('result', {}).get('isError'))
            expect_kw = expectations.get(f'{tool}:must', '')
            good = bool(text) and not is_err
            if expect_kw:
                good = good and expect_kw in text
            ok &= rec(f'{name}.{tool} 返回内容',
                      good,
                      (text.splitlines()[0][:60] if text else f'空响应 {resp}'))

        # 协议层：未知方法必须报 -32601，而不是崩
        # [EN] Protocol layer: unknown methods must report -32601, not crash
        unknown = cli.send('totally/unknown')
        code = (unknown or {}).get('error', {}).get('code')
        ok &= rec(f'{name}: 未知方法返回 -32601', code == -32601, f'code={code}')

        # 协议层：缺必填参数必须报 -32602，而不是让 handler 抛 KeyError
        # [EN] Protocol layer: missing required params must report -32602, not let the handler throw KeyError
        need = [t['name'] for t in listed
                if (t.get('inputSchema') or {}).get('required')]
        if need:
            miss = cli.call(need[0], {})
            mcode = (miss or {}).get('error', {}).get('code')
            ok &= rec(f'{name}: 缺必填参数返回 -32602', mcode == -32602,
                      f'{need[0]} → code={mcode}')

        # stdout 纯净：每一行都必须是合法 JSON
        # [EN] stdout purity: every line must be valid JSON
        bad_lines = []
        for line in cli.raw_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad_lines.append(line[:60])
        ok &= rec(f'{name}: stdout 无协议外输出', not bad_lines,
                  f'异常行：{bad_lines}' if bad_lines else '')
    finally:
        cli.close()
    return bool(ok)


def test_tool_errors(script: Path, project: Path, empty_dir: Path) -> bool:
    """业务失败要用 isError，不是协议错误 —— 客户端不该因此崩掉。
        English:
    Business failures should use isError, not protocol errors -- the client should not crash because
    of them.
    """
    name = script.stem
    ok = True

    # 指到一个不存在的项目目录
    # [EN] Point at a nonexistent project directory
    cli = StdioClient(script, empty_dir / '不存在')
    try:
        cli.send('initialize', {'protocolVersion': '2024-11-05'})
        cli.notify('notifications/initialized')
        resp = cli.call('project_overview' if 'lore' in name else 'run_overview')
        result = (resp or {}).get('result') or {}
        ok &= rec(f'{name}: 项目不存在时用 isError（不是协议错误）',
                  result.get('isError') is True and 'error' not in (resp or {}),
                  (cli.text_of(resp).splitlines() or [''])[0][:60])
    finally:
        cli.close()

    # 空目录（存在但没有设定集/运行文件夹）
    # [EN] Empty directory (exists but has no settings collection/run folder)
    empty = empty_dir / '空白项目'
    empty.mkdir(parents=True, exist_ok=True)
    cli = StdioClient(script, empty)
    try:
        cli.send('initialize', {'protocolVersion': '2024-11-05'})
        cli.notify('notifications/initialized')
        resp = cli.call('character' if 'lore' in name else 'day_index',
                        {'name': '主角'} if 'lore' in name else {})
        text = cli.text_of(resp)
        ok &= rec(f'{name}: 空项目给出可读提示', bool(text),
                  text.splitlines()[0][:60] if text else '空响应')
    finally:
        cli.close()
    return bool(ok)


def test_clock_math() -> bool:
    """时辰换算是纯计算，可以直接断对错 —— 跨日进位是 LLM 最容易算错的地方。
        English:
    Shichen conversion is pure computation, so correctness can be asserted directly -- cross-day
    carry is where the LLM is most likely to miscalculate.
    """
    ok = True
    script = SERVERS_DIR / 'clock_server.py'
    cli = StdioClient(script)
    try:
        cli.send('initialize', {'protocolVersion': '2024-11-05'})
        cli.notify('notifications/initialized')

        text = cli.text_of(cli.call('shichen', {'hour': 19}))
        ok &= rec('虚拟时钟: 19 点 = 戌时', '戌时' in text and '黄昏' in text,
                  line_at(text, 0, 50))

        text = cli.text_of(cli.call('shichen', {'hour': 23}))
        ok &= rec('虚拟时钟: 23 点归子时（边界）', '子时' in text,
                  line_at(text, 0, 50))

        text = cli.text_of(cli.call('advance',
                                    {'day': 3, 'shichen': '戌', 'hours': 7}))
        ok &= rec('虚拟时钟: 戌时+7h → 第4天丑时（跨日进位）',
                  '第 4 天' in text and '丑时' in text, line_at(text, 1, 50))

        text = cli.text_of(cli.call('advance',
                                    {'day': 2, 'shichen': '丑', 'hours': -30}))
        ok &= rec('虚拟时钟: 负数小时也能正确倒推', '第 0 天' in text,
                  line_at(text, 1, 50))

        text = cli.text_of(cli.call('real_cost', {'days': 3, 'time_ratio': 60}))
        ok &= rec('虚拟时钟: 耗时估算给出数字', '分钟' in text or '小时' in text,
                  line_at(text, 1, 50))
    finally:
        cli.close()
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  配置文件 / MCPClient / 只读性
# [EN] Config file / MCPClient / read-only property
# ══════════════════════════════════════════════════════════════
def test_config() -> bool:
    ok = True
    import yaml
    path = APP_DIR / 'mcp_servers.yaml'
    ok &= rec('mcp_servers.yaml 存在', path.exists(), str(path.name))
    if not path.exists():
        return False

    data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    servers = data.get('mcpServers') or {}
    ok &= rec('配置里有 mcpServers 段', bool(servers),
              f'{len(servers)} 个服务')

    # 每个服务都要有 command / enabled / 用途
    # [EN] Every service must have command / enabled / purpose
    bad = []
    for name, spec in servers.items():
        if not isinstance(spec, dict) or 'command' not in spec:
            bad.append(f'{name}(缺 command)')
        elif 'enabled' not in spec:
            bad.append(f'{name}(缺 enabled)')
        elif not (spec.get('用途') or spec.get('description')):
            bad.append(f'{name}(缺 用途)')
    ok &= rec('每个服务都有 command/enabled/用途', not bad,
              '；'.join(bad) if bad else '')

    # 本地服务器指向的脚本必须真的存在
    # [EN] The script pointed to by the local server must actually exist
    missing = []
    for name, spec in servers.items():
        for a in (spec.get('args') or []):
            if str(a).endswith('.py'):
                if not (APP_DIR / str(a)).exists():
                    missing.append(f'{name} → {a}')
    ok &= rec('本地服务器脚本路径都存在', not missing,
              '；'.join(missing) if missing else '')

    # 联网模板必须默认关闭（纪律：外部服务默认关）
    # [EN] Network templates must be disabled by default (discipline: external services off by default)
    networked = ('fetch', 'duckduckgo-search', 'wikipedia', 'time')
    opened = [n for n in networked
              if servers.get(n, {}).get('enabled') is not False]
    ok &= rec('联网模板默认关闭', not opened,
              f'被打开的：{opened}' if opened else
              '（' + '、'.join(n for n in networked if n in servers) + '）')

    # 本地三个服务应当默认开启（装完即可用）
    # [EN] The three local services should be enabled by default (usable right after install)
    local = ('项目考据', '故事线', '虚拟时钟')
    closed = [n for n in local if not servers.get(n, {}).get('enabled')]
    ok &= rec('本地三个服务默认启用', not closed,
              f'未启用：{closed}' if closed else '（' + '、'.join(local) + '）')
    return bool(ok)


def test_placeholders(project: Path) -> bool:
    ok = True
    from mcp.client import substitute, mcp_client

    text = substitute('{python}|{app_dir}|{project_dir}')
    parts = text.split('|')
    ok &= rec('占位符 {python} 解析成真实解释器',
              Path(parts[0]).exists() and parts[0].endswith(
                  ('python.exe', 'python', 'python3')),
              Path(parts[0]).name)
    ok &= rec('占位符 {app_dir} 解析成程序根目录',
              Path(parts[1]).resolve() == APP_DIR.resolve(), parts[1][-40:])

    mcp_client.set_project_dir(project)
    ok &= rec('占位符 {project_dir} 跟随当前项目',
              substitute('{project_dir}') == str(project),
              substitute('{project_dir}')[-40:])

    ok &= rec('{env:NAME} 读环境变量',
              substitute('{env:NWS_TEST_X}') == '',
              '未设置时给空串（不是原样留着）')
    return bool(ok)


def test_readonly() -> bool:
    """随程序发行的服务器必须是只读的 —— 程序永不反写项目文件夹。
        English:
    Servers shipped with the program must be read-only -- the program never writes back to the
    project folder.
    """
    ok = True
    patterns = [
        (r'\.write_text\(', 'write_text'),
        (r'\.write_bytes\(', 'write_bytes'),
        (r'\.unlink\(', 'unlink'),
        (r'\.mkdir\(', 'mkdir'),
        (r'open\([^)]*[\'"][wa]', 'open 写模式'),
        (r'shutil\.rmtree', 'rmtree'),
    ]
    offenders = []
    for p in sorted(SERVERS_DIR.glob('*.py')):
        src = p.read_text(encoding='utf-8')
        for pat, label in patterns:
            if re.search(pat, src):
                offenders.append(f'{p.name}:{label}')
    ok &= rec('服务器代码里没有任何写盘操作', not offenders,
              '；'.join(offenders) if offenders else
              f'（扫了 {len(list(SERVERS_DIR.glob("*.py")))} 个文件）')
    return bool(ok)


async def test_client_integration(project: Path) -> bool:
    """走 app 真正用的入口：MCPClient + 考据通道。
        English:
    Walk through the entry point the app actually uses: MCPClient + research channel.
    """
    ok = True
    from config import CFG
    from mcp.client import mcp_client

    ok &= rec('MCP_ENABLED 总闸开启', CFG.b('MCP_ENABLED'),
              f'MCP_TIMEOUT_SECONDS={CFG.i("MCP_TIMEOUT_SECONDS")}')

    mcp_client.load(force=True)
    mcp_client.set_project_dir(project)

    enabled = mcp_client.enabled_servers()
    ok &= rec('客户端识别出启用的服务', len(enabled) >= 3,
              '、'.join(enabled))

    tools = await mcp_client.list_tools('项目考据')
    ok &= rec('MCPClient.list_tools 能列出工具', len(tools) >= 5,
              f'{len(tools)} 个')

    text = await mcp_client.call_tool('项目考据', 'character', {'name': '主角'})
    ok &= rec('MCPClient.call_tool 真取到人物卡',
              bool(text) and '主角' in text and '秘密' in text,
              line_at(text or '', 0, 50))

    # 没启用的服务必须直接返回 None，不能去拉进程
    # [EN] A disabled service must directly return None, must not spawn a process
    ok &= rec('未启用的服务直接返回 None',
              await mcp_client.call_tool('wikipedia', 'search', {'q': 'x'}) is None)
    ok &= rec('不存在的服务返回 None（不抛异常）',
              await mcp_client.call_tool('根本没有这个服务', 'x', {}) is None)

    # 考据通道：技能层
    # [EN] Research channel: skill layer
    from research.lookup import research_lookup
    res = await research_lookup.lookup('五刑', '测试')
    ok &= rec('考据通道命中技能层（零网络）',
              str(res.get('来源', '')).startswith('技能/'),
              f'{res.get("来源")}')

    # 考据通道：MCP 层（用技能命中不了的人名，逼它走到 MCP）
    # [EN] Research channel: MCP layer (use a person name that skills can't hit, forcing it to go to MCP)
    res2 = await research_lookup.lookup('主角的秘密', '测试')
    src = str(res2.get('来源', ''))
    ok &= rec('考据通道命中 MCP 层',
              src.startswith('MCP/'), f'{src}')

    await mcp_client.aclose()
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  技能
# [EN] Skills
# ══════════════════════════════════════════════════════════════
def test_skills() -> bool:
    ok = True
    from skills.registry import skill_registry

    skill_registry.load(force=True)
    skills = skill_registry.all_skills()
    # ★★★ 2026-10-27：原来这里写死"== 8"（那是 2026-10-22 的快照）。
    #   后来加了 28 份地图技能（建筑/家具/道路/城市/室内设计…），总数变成 36，
    #   写死的判据就**每次加技能都红一次** —— 那不是"保护"，那是"逼人别加东西"。
    #   ⇒ 改成两条：① **数量只卡下限**（卡的是"根本没加载到"）；
    #              ② **核心技能一个都不许少**（这条才是"不许静静消失"）。
    # [EN] ★★★ 2026-10-27: this used to assert "== 8" (a 2026-10-22 snapshot). 28 map packs
    #   later (architecture / furniture / roads / city / interior design...) the count became 36, and
    #   a hard-coded count goes red **every time a pack is added** -- that is not "protection", that
    #   is "don't add anything". => Two criteria now: ① the count only has a **floor** (it guards
    #   "nothing loaded at all"); ② **no core pack may be missing** (that is the real
    #   "nothing may quietly disappear" guard).
    ok &= rec('注册表加载到 ≥ 8 个内置技能（数量会随地图技能增加，只卡"没加载到"）',
              len(skills) >= 8,
              f'{len(skills)} 个：' + '、'.join(s.display_name for s in skills))

    _core = ('中医药方常识', '兵器甲胄', '古代律法常识', '姓名称谓生成',
             '官职品级对照', '朝代制度速查', '节气物候', '路程与交通估算')
    _have = {s.display_name for s in skills}
    _miss = [c for c in _core if c not in _have]
    ok &= rec('核心 8 个技能**一个都没少**（不许悄悄消失）', not _miss,
              '少了：' + '、'.join(_miss) if _miss else '')

    # frontmatter 必须字段
    # [EN] Required frontmatter fields
    bad = [s.dir_name for s in skills
           if not s.meta.get('名称') or not s.triggers or not s.purpose]
    ok &= rec('每个技能都有 名称/触发关键词/用途', not bad,
              '缺字段：' + '、'.join(bad) if bad else '')

    # 正文要有实质内容
    # [EN] Body must have substantive content
    thin = [s.dir_name for s in skills if len(s.content) < 300]
    ok &= rec('每个技能正文都有实质内容（>300 字）', not thin,
              f'过短：{thin}' if thin else
              f'最短 {min(len(s.content) for s in skills)} 字')

    # 关键词不能只有一个字（会把「名字」「文字」全命中）
    # [EN] Keywords must not be a single character (would match all of "name", "text")
    short = [(s.dir_name, t) for s in skills for t in s.triggers if len(t) < 2]
    ok &= rec('没有单字触发关键词（避免误命中）', not short,
              '；'.join(f'{d}→{t}' for d, t in short) if short else '')

    # 路由：每个技能都要能被一句自然话命中
    # [EN] Routing: each skill must be hittable by one natural sentence
    queries = {
        '五刑里绞和斩哪个重': '古代律法常识',
        '这个官是几品': '官职品级对照',
        '宋代交子兑便': '朝代制度速查',
        '上焦发热该用什么方子': '中医药方常识',
        '这段打斗用什么兵器': '兵器甲胄',
        '清明那天有什么物候': '节气物候',
        '走到临安要几天': '路程与交通估算',
        '主角的字号怎么取': '姓名称谓生成',
    }
    wrong = []
    for q, expect in queries.items():
        hits = skill_registry.match_all(q)
        got = hits[0].display_name if hits else '(无)'
        if got != expect:
            wrong.append(f'{q}→{got}(期望 {expect})')
    ok &= rec('自然语句能路由到正确技能', not wrong,
              '；'.join(wrong) if wrong else f'{len(queries)} 条全中')

    # 无关问题不该命中任何技能
    # [EN] Irrelevant questions should not hit any skill
    noise = ['量子力学是什么', '这个函数怎么优化', '今天股票涨了吗']
    hits = [(q, skill_registry.match_all(q)) for q in noise]
    noisy = [q for q, h in hits if h]
    ok &= rec('无关问题不误命中', not noisy,
              f'误命中：{noisy}' if noisy else '')

    # 附带脚本
    # [EN] Bundled scripts
    with_scripts = [s for s in skills if s.scripts]
    ok &= rec('有技能附带脚本（示范"可选脚本"）', len(with_scripts) >= 3,
              '、'.join(f'{s.display_name}({len(s.scripts)})'
                        for s in with_scripts))

    failed = []
    for s in with_scripts:
        for script in s.scripts:
            r = subprocess.run([PY, str(script)], capture_output=True,
                               cwd=str(APP_DIR), timeout=60)
            out = r.stdout.decode('utf-8', 'replace')
            if r.returncode != 0 or not out.strip():
                failed.append(f'{s.display_name}/{script.name}'
                              f'(rc={r.returncode})')
    ok &= rec('附带脚本无参运行即可给出结果', not failed,
              '；'.join(failed) if failed else
              f'{sum(len(s.scripts) for s in with_scripts)} 个脚本')

    # 脚本可答的具体问题（真调一次，验证算得对）
    # [EN] Specific questions the script can answer (actually call once, verify the computation is correct)
    jieqi = APP_DIR / 'skills' / '节气物候' / 'scripts' / 'jieqi.py'
    r = subprocess.run([PY, str(jieqi), '2026-04-05'], capture_output=True,
                       cwd=str(APP_DIR), timeout=60)
    out = r.stdout.decode('utf-8', 'replace')
    ok &= rec('节气脚本算对了 2026-04-05 = 清明',
              '清明' in out and '桐始华' in out,
              line_at(out, 1, 40))

    travel = APP_DIR / 'skills' / '路程与交通估算' / 'scripts' / 'travel.py'
    r = subprocess.run([PY, str(travel), '1200', '--mode', '快马'],
                       capture_output=True, cwd=str(APP_DIR), timeout=60)
    out = r.stdout.decode('utf-8', 'replace')
    ok &= rec('行程脚本给出区间（不是单一数字）',
              '~' in out and '实际' in out,
              line_at(out, 1, 50))

    names = APP_DIR / 'skills' / '姓名称谓生成' / 'scripts' / 'gen_names.py'
    # ⚠ 夹具要用**像人名的人名** —— 2026-10-26 修：脚本的契约是"取名字第一个字当姓"
    #   （`surname = name[0]`），而原来这里传的是「主角」⇒ 姓算成「主」⇒ 输出
    #   「主大人」，判据当然找不到「沈大人」。**这不是产品坏了，是夹具拿了个不是人名的词**。
    #   换成「沈砚」之后：{姓}→沈、{官}→知府，两条都对得上。
    # [EN] ⚠ The fixture must look like a person's name -- fixed 2026-10-26: the script's contract
    # [EN] is "take the first character as the surname" (`surname = name[0]`), and this used to pass
    # [EN] 「主角」, so the surname became 「主」 and the output read 「主大人」; of course the
    # [EN] criterion never found 「沈大人」. **The product is fine; the fixture was not a name.**
    r = subprocess.run([PY, str(names), '--titles', '沈砚',
                        '--identity', '官员'],
                       capture_output=True, cwd=str(APP_DIR), timeout=60)
    out = r.stdout.decode('utf-8', 'replace')
    ok &= rec('称谓脚本给出「沈大人」这类正确称谓',
              '沈大人' in out and '下官' in out,
              [ln for ln in out.splitlines() if '对称' in ln][:1] and
              [ln for ln in out.splitlines() if '对称' in ln][0][:50] or '')
    return bool(ok)


# ══════════════════════════════════════════════════════════════
def main() -> int:
    print('MCP 与技能验证（真机：起进程、真调工具）', flush=True)
    project = make_fixture()
    empty_dir = Path(tempfile.mkdtemp(prefix='nws_empty_'))
    report['fixture'] = str(project)

    results: list[bool] = []

    head('1. 配置文件')
    results.append(test_config())

    head('2. 占位符替换')
    results.append(test_placeholders(project))

    head('3. 只读性（程序永不反写项目文件夹）')
    results.append(test_readonly())

    head('4. 服务器协议与工具（真起进程）')
    lore_tools = ['character', 'foreshadows', 'list_characters', 'lore_search',
                  'progress', 'project_overview', 'worldview']
    expected_lore = {
        'character': {'name': '主角'},
        'character:must': '秘密',
        'list_characters': {},
        'list_characters:must': '阿枝',
        'foreshadows': {},
        'foreshadows:must': '井',
        'worldview': {},
        'worldview:must': '临河',
        'progress': {},
        'progress:must': '开端',
        'project_overview': {},
        'project_overview:must': '主角',
        'lore_search': {'query': '井'},
        'lore_search:must': '设定集/',
    }
    results.append(test_protocol(SERVERS_DIR / 'project_lore_server.py',
                                 project, lore_tools, expected_lore))

    tl_tools = ['day_index', 'key_events', 'recent_days', 'run_overview',
                'search_run', 'story_so_far']
    expected_tl = {
        'run_overview': {}, 'run_overview:must': '2 天',
        'day_index': {}, 'day_index:must': '第2天',
        'recent_days': {'n': 2}, 'recent_days:must': '檐瓦',
        'key_events': {}, 'key_events:must': '雨夜来客',
        'story_so_far': {}, 'story_so_far:must': '破绽',
        'search_run': {'query': '井绳'}, 'search_run:must': '阿枝',
    }
    results.append(test_protocol(SERVERS_DIR / 'timeline_server.py',
                                 project, tl_tools, expected_tl))

    clock_tools = ['advance', 'now', 'real_cost', 'shichen', 'shichen_table']
    results.append(test_protocol(SERVERS_DIR / 'clock_server.py',
                                 None, clock_tools,
                                 {'shichen': {'hour': 7},
                                  'shichen:must': '辰时',
                                  'shichen_table': {},
                                  'shichen_table:must': '夜半',
                                  'real_cost': {'days': 1},
                                  'real_cost:must': '故事分钟',
                                  'advance': {'day': 1, 'shichen': '辰',
                                              'hours': 2},
                                  'advance:must': '巳时',
                                  'now': {}}))

    head('5. 时辰换算的正确性（跨日进位）')
    results.append(test_clock_math())

    head('6. 业务失败用 isError（客户端不该崩）')
    results.append(test_tool_errors(SERVERS_DIR / 'project_lore_server.py',
                                    project, empty_dir))

    head('7. MCPClient 与考据通道整合')
    results.append(asyncio.run(test_client_integration(project)))

    head('8. 技能：加载 / 路由 / 脚本')
    results.append(test_skills())

    ok = all(results)
    report['ok'] = ok
    passed = sum(1 for s in report['steps'] if s['ok'])
    report['passed'] = passed
    report['total'] = len(report['steps'])
    report['failed'] = [s['name'] for s in report['steps'] if not s['ok']]

    (OUT / 'mcp_skills_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'\n{"=" * 62}')
    print(f'通过 {passed}/{len(report["steps"])} 项'
          + ('' if ok else '　失败：\n  - ' + '\n  - '.join(report['failed'])))
    print(f'报告：assets/screenshots/mcp_skills_report.json')
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
