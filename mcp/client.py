# -*- coding: utf-8 -*-
"""MCP 客户端（设计稿 §8.6）：拉起 MCP 服务器进程并通过 stdio 调用。

传输是 **一行一个 JSON-RPC 2.0 消息**，握手顺序：

    客户端 → initialize
    服务端 → result（protocolVersion / capabilities / serverInfo）
    客户端 → notifications/initialized     ← 通知，无 id，服务端不回
    客户端 → tools/list  /  tools/call
    服务端 → result

设计取舍
  · 一个服务器**只拉一个常驻进程**，懒启动、进程内复用（启动开销比调用贵得多）
  · 任何失败都**只记日志并返回 None**，绝不让考据层把模拟循环带崩
  · 全局开关 `MCP_ENABLED=false` 时完全不拉进程
  · 参数里的 `{python}` / `{app_dir}` / `{project_dir}` / `{env:NAME}` 启动时替换，
    这样配置文件跨平台可移植（venv 的 python 在 Windows 是 Scripts、Unix 是 bin）

配置见 mcp_servers.yaml，写法见 mcp/README.md。

English:
MCP client (design doc §8.6): spawn MCP server processes and call them via stdio.
The transport is **one JSON-RPC 2.0 message per line**, handshake order:
    client → initialize
    server → result (protocolVersion / capabilities / serverInfo)
    client → notifications/initialized     ← notification, no id, server does not reply
    client → tools/list  /  tools/call
    server → result
Design trade-offs
  · One server spawns **only one long-running process**, lazy-started, reused within the process (startup overhead is much higher than a call)
  · Any failure **only logs and returns None**, never letting the research layer crash the simulation loop
  · When the global switch `MCP_ENABLED=false`, no process is spawned at all
  · `{python}` / `{app_dir}` / `{project_dir}` / `{env:NAME}` in parameters are substituted at startup,
    so the config file is portable across platforms (venv's python is in Scripts on Windows, bin on Unix)
See mcp_servers.yaml for config, mcp/README.md for usage.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from config import APP_DIR, CFG

_LOG = __import__("logging").getLogger("nws.mcp")

_PROTOCOL_VERSION = '2024-11-05'
_PLACEHOLDER = re.compile(r'\{([a-zA-Z_]+|env:[A-Za-z_][A-Za-z0-9_]*)\}')


class MCPServerError(Exception):
    """服务器启动/协议层面的失败。
        English:
    Server startup/protocol-level failure.
    """


class _Server:
    """一个已配置的 MCP 服务器（持有进程与工具清单）。
        English:
    A configured MCP server (holds the process and tool list).
    """

    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec
        self.proc: asyncio.subprocess.Process | None = None
        self.tools: list[dict] = []
        self.server_info: dict = {}
        self._lock = asyncio.Lock()
        self._next_id = 0
        self._start_failed = ''

    # ── 配置 ──
    # [EN] ── Config ──
    @property
    def enabled(self) -> bool:
        return bool(self.spec.get('enabled', False))

    @property
    def timeout(self) -> float:
        try:
            return float(self.spec.get('timeout') or CFG.i('MCP_TIMEOUT_SECONDS'))
        except (TypeError, ValueError):
            return 20.0

    @property
    def purpose(self) -> str:
        return str(self.spec.get('用途') or self.spec.get('description') or '')

    def _argv(self) -> list[str]:
        cmd = str(self.spec.get('command') or '').strip()
        if not cmd:
            raise MCPServerError(f'{self.name}: 缺少 command')
        args = self.spec.get('args') or []
        if not isinstance(args, list):
            raise MCPServerError(f'{self.name}: args 必须是列表')
        return [substitute(cmd)] + [substitute(str(a)) for a in args]

    @property
    def url(self) -> str:
        """url 型服务器（HTTP/SSE）本版本不支持，但要给出明确提示而非静默忽略。
                English:
        url-type servers (HTTP/SSE) are not supported in this version, but must give a clear hint rather
        than silently ignore.
        """
        return str(self.spec.get('url') or '')

    # ── 进程 ──
    # [EN] ── Process ──
    async def ensure_started(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            return
        if self._start_failed:
            raise MCPServerError(self._start_failed)
        if self.url and not self.spec.get('command'):
            msg = (f'{self.name}: 本版本只支持 stdio 型服务器（command/args），'
                   f'暂不支持 url 型：{self.url}')
            self._start_failed = msg
            raise MCPServerError(msg)

        argv = self._argv()
        # ★★ 2026-10-10：Windows 上给子进程加 `CREATE_NO_WINDOW`。
        # [EN] ★★ 2026-10-10: On Windows, add `CREATE_NO_WINDOW` to subprocesses.
        #
        #   MCP 服务器是 `python.exe`（**控制台子系统**程序）。如果本进程
        #   自己没有控制台（被 `pythonw.exe` / 快捷方式拉起，或者以后改成
        #   无窗口启动），Windows 会给每个子进程**新分配一个控制台** ——
        #   于是每拉起一个 MCP 服务器就多一个黑窗（本项目已经踩过一次，
        #   见 `novelservices/mumu_bridge._run_service` 的注释）。
        #   带上这个标志，无论宿主有没有控制台都不会出窗口。
        # [EN] The MCP server is `python.exe` (a **console subsystem** program). If this process
        # [EN] itself has no console (launched by `pythonw.exe` / a shortcut, or later changed to
        # [EN] windowless startup), Windows will **allocate a new console** for each subprocess ——
        # [EN] thus every MCP server spawned adds another black window (this project has already hit this once,
        # [EN] see the comment in `novelservices/mumu_bridge._run_service`).
        # [EN] With this flag, no window appears regardless of whether the host has a console.
        _kw: dict = {}
        if os.name == 'nt':
            _kw['creationflags'] = 0x08000000              # CREATE_NO_WINDOW
            _si = subprocess.STARTUPINFO()
            _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            _si.wShowWindow = 0                            # SW_HIDE
            _kw['startupinfo'] = _si
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=str(APP_DIR), **_kw)
        except (OSError, ValueError) as e:
            self._start_failed = (f'{self.name}: 无法启动 {argv[0]!r}（{e}）。'
                                  f'检查 command 是否存在、依赖是否装好。')
            raise MCPServerError(self._start_failed) from e

        try:
            await self._request('initialize', {
                'protocolVersion': _PROTOCOL_VERSION,
                'capabilities': {},
                'clientInfo': {'name': 'novel-world-simulator', 'version': '1.0.0'},
            })
            await self._notify('notifications/initialized')
            listed = await self._request('tools/list', {})
            self.tools = list((listed or {}).get('tools') or [])
            _LOG.info('MCP 服务已就绪: %s（%d 个工具）', self.name, len(self.tools))
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()
        except ProcessLookupError:
            pass

    # ── 协议 ──
    # [EN] ── Protocol ──
    async def _write(self, obj: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))
        await self.proc.stdin.drain()

    async def _notify(self, method: str, params: dict | None = None) -> None:
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        await self._write(payload)

    async def _request(self, method: str, params: dict, *, timeout: float | None = None):
        """发一条请求并等对应的响应（跳过服务端的通知）。
                English:
        Send a request and wait for the corresponding response (skipping server notifications).
        """
        if self.proc is None:
            raise MCPServerError(f'{self.name}: 进程未启动')
        if self.proc.returncode is not None:
            err = await self._drain_stderr()
            raise MCPServerError(f'{self.name}: 进程已退出（{err[:300]}）')

        self._next_id += 1
        rid = self._next_id
        await self._write({'jsonrpc': '2.0', 'id': rid, 'method': method,
                           'params': params})

        deadline = timeout or self.timeout
        try:
            return await asyncio.wait_for(self._await_response(rid), timeout=deadline)
        except asyncio.TimeoutError:
            raise MCPServerError(
                f'{self.name}: {method} 超时（>{deadline:g}s）') from None

    async def _await_response(self, rid: int):
        assert self.proc and self.proc.stdout
        while True:
            raw = await self.proc.stdout.readline()
            if not raw:                      # EOF：服务器挂了
            # [EN] EOF: the server died
                err = await self._drain_stderr()
                raise MCPServerError(f'{self.name}: 连接中断（{err[:300]}）')
            try:
                msg = json.loads(raw.decode('utf-8', 'replace'))
            except json.JSONDecodeError:
                continue                     # 非协议行（服务端误写了 stdout）忽略
                # [EN] Non-protocol lines (server mistakenly wrote to stdout) are ignored
            if isinstance(msg, list):
                for m in msg:
                    if m.get('id') == rid:
                        return _unwrap(self.name, m)
                continue
            if msg.get('id') != rid:
                continue                     # 别人的响应或通知
                # [EN] Someone else's response or notification
            return _unwrap(self.name, msg)

    async def _drain_stderr(self) -> str:
        if not (self.proc and self.proc.stderr):
            return ''
        try:
            data = await asyncio.wait_for(self.proc.stderr.read(), timeout=1)
            return data.decode('utf-8', 'replace').strip()
        except Exception:
            return ''

    # ── 对外 ──
    # [EN] ── Public ──
    async def call(self, tool: str, arguments: dict) -> str | None:
        """调用一个工具，返回文本结果；失败返回 None（已记日志）。
                English:
        Call a tool, return the text result; on failure return None (already logged).
        """
        try:
            await self.ensure_started()
            result = await self._request('tools/call',
                                         {'name': tool, 'arguments': arguments or {}})
        except Exception as e:
            _LOG.warning('MCP 调用失败 %s.%s: %s', self.name, tool, e)
            return None
        if not isinstance(result, dict):
            return None
        text = _content_text(result)
        if result.get('isError'):
            _LOG.info('MCP 工具返回错误 %s.%s: %s', self.name, tool, text[:200])
            return None
        return text


def _unwrap(server: str, msg: dict):
    """把 JSON-RPC 响应解成 result / 抛异常。
        English:
    Decode a JSON-RPC response into result / raise an exception.
    """
    if 'error' in msg:
        err = msg['error'] or {}
        raise MCPServerError(f'{server}: {err.get("message")}'
                             f'（code {err.get("code")}）')
    return msg.get('result')


def _content_text(result: dict) -> str:
    """把 MCP 的 content 数组拼成一段文本。
        English:
    Concatenate MCP's content array into a single text.
    """
    parts: list[str] = []
    for block in result.get('content') or []:
        if not isinstance(block, dict):
            continue
        if block.get('type') == 'text':
            parts.append(str(block.get('text', '')))
        elif block.get('type') == 'resource':
            parts.append(str((block.get('resource') or {}).get('text', '')))
    return '\n'.join(p for p in parts if p).strip()


# ══════════════════════════════════════════════════════════════
#  占位符
# [EN] Placeholder
# ══════════════════════════════════════════════════════════════
# 当前项目目录。用模块级变量而不是回调 MCPClient，避免模块内循环引用。
# [EN] Current project directory. Use a module-level variable instead of a callback to MCPClient, to
# [EN] avoid circular imports within the module.
_PROJECT_DIR = os.environ.get('NWS_PROJECT_DIR', '')


def substitute(text: str) -> str:
    """替换 {python} / {app_dir} / {project_dir} / {env:NAME}。
        English:
    Substitute {python} / {app_dir} / {project_dir} / {env:NAME}.
    """
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key == 'python':
            return sys.executable
        if key == 'app_dir':
            return str(APP_DIR)
        if key == 'project_dir':
            return _PROJECT_DIR
        if key.startswith('env:'):
            return os.environ.get(key[4:], '')
        return m.group(0)                    # 认不出来就原样留着，便于排查
        # [EN] If unrecognized, keep it as-is for easier troubleshooting
    return _PLACEHOLDER.sub(repl, text)


class MCPClient:
    """MCP 客户端：加载配置、管理服务器进程、转发工具调用。
        English:
    MCP client: load config, manage server processes, forward tool calls.
    """

    def __init__(self) -> None:
        self._config: dict[str, dict] = {}
        self._servers: dict[str, _Server] = {}
        self._loaded = False
        self._project_dir = _PROJECT_DIR

    # ── 当前项目（供 {project_dir} 占位符与本地服务器定位）──
    # [EN] ── Current project (for the {project_dir} placeholder and locating local servers) ──
    @property
    def project_dir(self) -> str:
        return self._project_dir

    def set_project_dir(self, path: str | Path | None) -> None:
        """切换当前小说项目；会同步到 {project_dir} 占位符。
                English:
        Switch the current novel project; syncs to the {project_dir} placeholder.
        """
        global _PROJECT_DIR
        _PROJECT_DIR = str(path) if path else ''
        self._project_dir = _PROJECT_DIR

    # ── 配置 ──
    # [EN] ── Config ──
    def load(self, *, force: bool = False) -> None:
        if self._loaded and not force:
            return
        self._config.clear()
        self._loaded = True

        path = CFG.resolved('MCP_CONFIG')
        if not path.exists():
            _LOG.info('MCP 配置文件不存在: %s', path)
            return
        try:
            data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except (yaml.YAMLError, OSError) as e:
            _LOG.warning('加载 MCP 配置失败: %s', e)
            return

        servers = data.get('mcpServers') if isinstance(data, dict) else None
        if isinstance(servers, dict):
            self._config = {str(k): (v or {}) for k, v in servers.items()
                            if isinstance(v, dict)}
            _LOG.info('加载 MCP 服务: %d 个（启用 %d）', len(self._config),
                      sum(1 for s in self._config.values() if s.get('enabled')))
        else:
            _LOG.warning('MCP 配置里没有 mcpServers 段: %s', path)

    def get_server(self, name: str) -> dict | None:
        self.load()
        return self._config.get(name)

    def get_all_servers(self) -> dict[str, dict]:
        self.load()
        return dict(self._config)

    def is_enabled(self, name: str) -> bool:
        spec = self.get_server(name)
        return bool(spec and spec.get('enabled'))

    def enabled_servers(self) -> list[str]:
        self.load()
        return [n for n, s in self._config.items() if s.get('enabled')]

    @property
    def globally_enabled(self) -> bool:
        return CFG.b('MCP_ENABLED')

    # ── 服务器句柄 ──
    # [EN] ── Server handle ──
    def _server(self, name: str) -> _Server:
        srv = self._servers.get(name)
        if srv is None:
            srv = _Server(name, self._config[name])
            self._servers[name] = srv
        return srv

    async def list_tools(self, name: str) -> list[dict]:
        """列出某服务器的工具（会拉起进程）。
                English:
        List a server's tools (will spawn the process).
        """
        if not self.globally_enabled or not self.is_enabled(name):
            return []
        try:
            srv = self._server(name)
            await srv.ensure_started()
            return list(srv.tools)
        except Exception as e:
            _LOG.warning('MCP 列工具失败 %s: %s', name, e)
            return []

    async def call_tool(self, name: str, tool: str,
                        arguments: dict | None = None) -> str | None:
        """调用工具，返回文本；未启用/失败返回 None。
                English:
        Call a tool, return text; returns None if not enabled/failed.
        """
        if not self.globally_enabled:
            _LOG.debug('MCP 全局开关关闭，跳过 %s.%s', name, tool)
            return None
        if not self.is_enabled(name):
            return None
        srv = self._server(name)
        text = await srv.call(tool, arguments or {})
        if text is not None:
            _LOG.info('MCP 调用成功 %s.%s（%d 字）', name, tool, len(text))
        return text

    async def call(self, server_name: str, tool: str,
                   arguments: dict | None = None) -> str | None:
        """`call_tool` 的旧签名别名（保持向后兼容）。
                English:
        Old signature alias for `call_tool` (kept for backward compatibility).
        """
        return await self.call_tool(server_name, tool, arguments)

    async def search(self, query: str) -> dict | None:
        """考据层用的便捷入口：在**所有启用的服务器**里找第一个有结果的。

        依次试每台服务器的检索类工具；
        返回 {"结果": 文本, "来源": "MCP/<服务名>/<工具>", "置信": "中"}。
        
                English:
        Convenience entry for the research layer: find the first one with a result among **all enabled
        servers**.
                Try each server's retrieval-type tool in turn;
        """
        if not self.globally_enabled:
            return None
        for name in self.enabled_servers():
            tools = {t.get('name') for t in await self.list_tools(name)}
            for tool in ('lore_search', 'search_run', 'search'):
                if tool not in tools:
                    continue
                text = await self.call_tool(name, tool, {'query': query, 'limit': 3})
                if text:
                    return {'结果': text,
                            '来源': f'MCP/{name}/{tool}',
                            '置信': '中'}
        return None

    async def aclose(self) -> None:
        """关掉所有服务器进程（退出程序或测试收尾时调）。
                English:
        Shut down all server processes (called on program exit or test teardown).
        """
        for srv in list(self._servers.values()):
            await srv.close()
        self._servers.clear()


# 全局单例
# [EN] Global singleton
mcp_client = MCPClient()
