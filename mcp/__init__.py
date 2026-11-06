# -*- coding: utf-8 -*-
"""MCP 集成（设计稿 §8.6）。

  client.py    MCP 客户端：拉起服务器进程、握手、转发工具调用
  servers/     随程序发行的示例服务器（纯标准库，可直接照抄改）

写自己的服务器：读 servers/_mcpkit.py 的模块文档，或用 servers/clock_server.py
当模板（最短的那个）。配置写在项目根目录的 mcp_servers.yaml。
详细说明见 mcp/README.md。

English:
MCP integration (design doc §8.6).
  client.py    MCP client: spawns server process, handshake, forwards tool calls
  servers/     example servers shipped with the program (pure standard library, can be copied and modified directly)
To write your own server: read the module docstring of servers/_mcpkit.py, or use
servers/clock_server.py
as a template (the shortest one). Configuration goes in mcp_servers.yaml at the project root.
See mcp/README.md for details.
"""
