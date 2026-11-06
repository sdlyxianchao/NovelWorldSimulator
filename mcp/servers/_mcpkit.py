# -*- coding: utf-8 -*-
"""迷你 MCP 服务器框架（零依赖，可直接照抄写自己的服务器）。

为什么不用官方的 `mcp` 包？
  这个项目的运行环境是「尽可能少依赖」——图像处理都只用 Pillow，没有 numpy。
  MCP 的 stdio 传输其实很薄：**一行一个 JSON-RPC 2.0 消息**，读写 stdin/stdout 即可。
  自己实现 100 行，换来「装完就能跑、不需要额外 pip 包」。

协议要点（stdio 传输）
  - 客户端把请求写进我们的 stdin：`{"jsonrpc":"2.0","id":1,"method":"tools/list"}\\n`
  - 我们把响应写回 stdout：`{"jsonrpc":"2.0","id":1,"result":{...}}\\n`
  - **stdout 只能出现协议消息**，任何调试输出必须走 stderr，否则客户端解析会炸。
  - 通知（notification，无 id）不回响应，如 `notifications/initialized`。

写一个新服务器只要三步：

    from _mcpkit import Server, text_result

    srv = Server('my-server', '1.0.0')

    @srv.tool('greet', '打个招呼', {'name': {'type': 'string'}}, required=['name'])
    def greet(args):
        return text_result(f"你好，{args['name']}")

    if __name__ == '__main__':
        srv.run()

自检（不接客户端也能验工具是否正常）：

    python my_server.py --list-tools          # 打印工具清单
    python my_server.py --call greet '{"name":"主角"}'   # 直接调一个工具

English:
Mini MCP server framework (zero dependencies, can be copied directly to write your own server).
Why not use the official `mcp` package?
  This project's runtime environment is "as few dependencies as possible" — even image processing only uses Pillow, no numpy.
  MCP's stdio transport is actually very thin: **one JSON-RPC 2.0 message per line**, just read/write stdin/stdout.
  Implement 100 lines yourself, in exchange for "runs right after install, no extra pip packages needed".
Protocol key points (stdio transport)
  - The client writes requests into our stdin: `{"jsonrpc":"2.0","id":1,"method":"tools/list"}\\n`
  - We write responses back to stdout: `{"jsonrpc":"2.0","id":1,"result":{...}}\\n`
  - **Only protocol messages may appear on stdout**, any debug output must go to stderr, otherwise the client's parsing will blow up.
  - Notifications (notification, no id) get no response, such as `notifications/initialized`.
Writing a new server only takes three steps:
    from _mcpkit import Server, text_result
    srv = Server('my-server', '1.0.0')
    @srv.tool('greet', 'say hi', {'name': {'type': 'string'}}, required=['name'])
    def greet(args):
        return text_result(f"Hello, {args['name']}")
    if __name__ == '__main__':
        srv.run()
Self-check (can verify whether tools work without connecting a client):
    python my_server.py --list-tools          # print tool list
    python my_server.py --call greet '{"name":"主角"}'   # call a tool directly
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

PROTOCOL_VERSION = '2024-11-05'

# JSON-RPC 2.0 标准错误码
# [EN] JSON-RPC 2.0 standard error codes
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603


def text_result(text: str, *, is_error: bool = False) -> dict:
    """工具返回：MCP 规定 content 是数组，文本用 {"type":"text"}。
        English:
    Tool return: MCP specifies that content is an array, text uses {"type":"text"}.
    """
    return {'content': [{'type': 'text', 'text': str(text)}], 'isError': is_error}


def json_result(obj: Any) -> dict:
    """把结构化数据当文本返回（MCP 的 content 只支持几种类型，文本最通用）。

    用 ensure_ascii=False 保留中文可读性；indent 让客户端（和人）都看得懂。
    
        English:
    Return structured data as text (MCP's content only supports a few types, text is the most
    general).
        Use ensure_ascii=False to keep Chinese readable; indent makes it understandable to both the client (and humans).
    """
    return text_result(json.dumps(obj, ensure_ascii=False, indent=2))


def error_result(message: str) -> dict:
    """工具层面的失败：**不是** JSON-RPC 错误，而是带 isError 的正常响应。

    区别很重要：协议错误（-32601）代表「你不会用这个接口」，
    工具错误（isError=true）代表「接口对了但这次没成功」——比如项目目录还没建。
    后者不该让客户端整个崩掉。
    
        English:
    Failures at the tool level: **not** a JSON-RPC error, but a normal response with isError.
        The distinction matters: a protocol error (-32601) means "you don't know how to use this interface",
        a tool error (isError=true) means "the interface was right but this attempt didn't succeed" — e.g. the project directory doesn't exist yet.
        The latter should not crash the whole client.
    """
    return text_result(message, is_error=True)


class ToolError(Exception):
    """工具内部可预期的失败，会被转成 isError 响应而不是协议错误。
        English:
    Expected failures inside a tool are converted to an isError response rather than a protocol
    error.
    """


class Server:
    """一个 MCP 服务器。注册工具 → run() 起 stdio 循环。
        English:
    An MCP server. Register tools → run() starts the stdio loop.
    """

    def __init__(self, name: str, version: str = '1.0.0',
                 instructions: str = ''):
        self.name = name
        self.version = version
        self.instructions = instructions
        self._tools: dict[str, dict] = {}

    # ── 注册 ──
    # [EN] ── Registration ──
    def tool(self, name: str, description: str, properties: dict | None = None,
             required: list[str] | None = None) -> Callable:
        """装饰器：把一个函数注册成工具。

        properties 用 JSON Schema 片段描述参数，例如
            {'query': {'type': 'string', 'description': '关键词'}}
        
                English:
        Decorator: registers a function as a tool.
                properties uses JSON Schema fragments to describe parameters, e.g.
                    {'query': {'type': 'string', 'description': 'keywords'}}
        """
        schema = {
            'type': 'object',
            'properties': properties or {},
            'required': required or [],
        }

        def deco(fn: Callable[[dict], dict]) -> Callable:
            self._tools[name] = {
                'name': name,
                'description': description,
                'inputSchema': schema,
                'handler': fn,
            }
            return fn
        return deco

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def tools_schema(self) -> list[dict]:
        return [{k: v for k, v in t.items() if k != 'handler'}
                for t in (self._tools[n] for n in self.tool_names())]

    # ── 分发 ──
    # [EN] ── Dispatch ──
    def handle(self, req: dict) -> dict | None:
        """处理一条请求；返回 None 表示这是通知、不该回响应。
                English:
        Handle one request; returning None means this is a notification and no response should be sent.
        """
        method = req.get('method')
        rid = req.get('id')

        # 通知：有 method 但没有 id
        # [EN] Notification: has method but no id
        if rid is None and isinstance(method, str):
            return None

        if method == 'initialize':
            params = req.get('params') or {}
            return self._ok(rid, {
                'protocolVersion': params.get('protocolVersion') or PROTOCOL_VERSION,
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': {'name': self.name, 'version': self.version},
                'instructions': self.instructions,
            })

        if method == 'ping':
            return self._ok(rid, {})

        if method == 'tools/list':
            return self._ok(rid, {'tools': self.tools_schema()})

        if method == 'tools/call':
            params = req.get('params') or {}
            return self._call_tool(rid, params)

        return self._err(rid, ERR_METHOD_NOT_FOUND, f'不支持的方法: {method}')

    def _call_tool(self, rid, params: dict) -> dict:
        name = params.get('name')
        args = params.get('arguments') or {}
        if not isinstance(args, dict):
            return self._err(rid, ERR_INVALID_PARAMS, 'arguments 必须是对象')

        tool = self._tools.get(name)
        if tool is None:
            return self._err(rid, ERR_INVALID_PARAMS,
                             f'没有名为 {name!r} 的工具；可用：'
                             + '、'.join(self.tool_names()))

        # 参数校验：必填项缺失直接给明确信息，别让 handler 里报 KeyError
        # [EN] Argument validation: give clear messages directly when required fields are missing, don't let
        # [EN] handler raise KeyError
        missing = [k for k in tool['inputSchema']['required'] if k not in args]
        if missing:
            return self._err(rid, ERR_INVALID_PARAMS,
                             f'缺少必填参数: {"、".join(missing)}')

        try:
            return self._ok(rid, tool['handler'](args))
        except ToolError as e:                       # 可预期失败
        # [EN] Expected failures
            return self._ok(rid, error_result(str(e)))
        except Exception as e:                       # 意外异常
        # [EN] Unexpected exceptions
            tb = traceback.format_exc()
            print(f'[{self.name}] 工具 {name} 异常:\n{tb}', file=sys.stderr)
            return self._ok(rid, error_result(f'{type(e).__name__}: {e}'))

    @staticmethod
    def _ok(rid, result: dict) -> dict:
        return {'jsonrpc': '2.0', 'id': rid, 'result': result}

    @staticmethod
    def _err(rid, code: int, message: str) -> dict:
        return {'jsonrpc': '2.0', 'id': rid,
                'error': {'code': code, 'message': message}}

    # ── 运行 ──
    # [EN] ── Run ──
    def run(self) -> None:
        """stdio 主循环：一行一个消息，读到 EOF 就退出。
                English:
        stdio main loop: one message per line, exit on EOF.
        """
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._write(self._err(None, ERR_PARSE, 'JSON 解析失败'))
                continue

            if isinstance(req, list):                # 批量请求
            # [EN] Batch requests
                out = [r for r in (self.handle(x) for x in req) if r]
                self._write(out)
                continue

            resp = self.handle(req)
            if resp is not None:
                self._write(resp)

    def _write(self, obj: Any) -> None:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        sys.stdout.flush()          # 不 flush 客户端会一直等，这是最常见的坑
        # [EN] Without flush the client will wait forever, this is the most common pitfall


def serve(server: Server) -> None:
    """命令行入口：支持 --list-tools / --call，方便自检与测试。
        English:
    Command-line entry: supports --list-tools / --call, convenient for self-check and testing.
    """
    argv = sys.argv[1:]
    if '--list-tools' in argv:
        print(json.dumps(server.tools_schema(), ensure_ascii=False, indent=2))
        return
    if '--call' in argv:
        i = argv.index('--call')
        name = argv[i + 1]
        raw = argv[i + 2] if i + 2 < len(argv) else '{}'
        resp = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                              'params': {'name': name,
                                         'arguments': json.loads(raw)}})
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    server.run()
