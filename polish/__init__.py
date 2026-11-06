# -*- coding: utf-8 -*-
"""**开卷打磨 Agent** —— 把「设定优化」从一个"一问一答的对话框"升级成一个**会动手的 Agent**。

## 为什么要有这个包（用户 2026-10-07 的原话）

> 「开卷的 AI 打磨部分 你没有生成一个 Agent，而且每次我输入新对话，你发给 LLM 的内容
> 不包含之前的历史信息，所以大模型返回的东西是不对的。你按照正常的 Agent Reflection
> 模型结合别的模型来处理优化流程，而且如前所述，最终优化结果需要同时写到项目里和原始的
> 设定文件夹里。即你需要有能力操作文件系统。有别的工具你也需要的，你可以自己尝试写代码
> （在沙盒里运行且控制权限和范围）别的用到的工具你也要自己写一下。而且我会可能提出别的
> 要求，你的开卷打磨的 Agent 也需要这个能力动态生成各种工具。在定制任务的基础上适当
> 增加灵活性。」

拆成六件事，本包逐个对应：

| 用户说的 | 落在哪 |
|---|---|
| 要一个 **Agent** | `polish/agent.py` 的 `PolishAgent`（不是"调一次模型回一段话"） |
| **带上历史** | `agent._compose()` —— 每次调用都把**全部事件流**（作者原话 / 工具调用 / 工具结果 / 我的结论 / 体检）编成 messages |
| **Reflection 模型** | 收尾之后走一遍 `_reflect()`：拿作者原话 + 全过程 + 实际改动，自查「漏改 / 改坏 / 越权」，有问题就带着意见再跑一轮 |
| **写到项目 + 引用文件夹两处** | 工具 `append_source`（引用侧，只追加、自动 `.bak`）与 `write_note` / `patch_settings`（项目侧）——**两条路都在 `Toolbox` 里，都受沙盒管** |
| **操作文件系统** | `polish/sandbox.py` 的 `Scope` + `resolve()`：只有两个根可碰，别的路径一律 `Denied` |
| **沙盒里跑代码、控制权限与范围** | `sandbox.check_source()`（AST 静态审查）+ `sandbox.run_code()`（**子进程**执行，硬超时、输出上限、只给安全 builtins 子集与"相对路径文件 API"） |
| **动态生成工具** | `polish/codegen.py` 的 `write_tool`：Agent 现场写一个 Python 工具 → 静态审查 → 落盘 → 注册 → **立刻能用** |

## 目录

```
polish/sandbox.py    作用域与权限（根白名单 / AST 审查 / 受限执行 / 子进程跑代码）
polish/tools.py      工具注册表 + 内置工具（读 / 检索 / 打补丁 / 回写 / 记录 / 收尾 / 反问）
polish/codegen.py    动态生成工具（Agent 自己写工具那条路）
polish/agent.py      Agent 主循环 + 事件流记忆 + Reflection（对外的主入口）
polish/_runner.py    子进程侧的执行器（**不是包的一部分**，被 `subprocess` 单独拉起来）
```

## 怎么用

```python
from polish import PolishAgent, Scope

agent = PolishAgent(settings=result.settings,
                    scope=Scope(src_root=素材夹, out_root=暂存区),
                    name='临河茶肆', tier='黄金', missing=[...])
out = await agent.ask('把主角的名字改掉，顺便补两条伏笔')      # → PolishTurn
out.settings      # 改完的设定
out.reply         # 给作者看的一段话
out.changes       # 这一轮到底动了什么（结构化，给界面打日志用）
out.actions       # 这一轮调过哪些工具（含动态生成的工具）
```

⚠ **铁律**：本包**不自己发 LLM 请求**，一律走 `llm.replies.ask`（那是全项目唯一
「解析 → 重试 → 抢救」的入口）。这样对话日志、预算台账、输出语言注入**全都自动生效**。

English:
**Open-Book Polishing Agent** — upgrade "setting optimization" from a "Q&A dialog box" into an
**Agent that actually does things**.
## Why this package exists (the user's own words, 2026-10-07)
> "For the AI polishing part of Open-Book, you didn't generate an Agent, and every time I enter a new conversation, the content you send to the LLM
> doesn't include the previous history, so what the large model returns is wrong. You should handle the optimization flow
> following a normal Agent Reflection model combined with other models, and as stated before, the final optimization result needs to be written to both the project and the original
> setting folder. That is, you need the ability to operate the file system. You'll also need other tools; you can try writing the code yourself
> (running in a sandbox with controlled permissions and scope). You should also write the other tools you use yourself. And I may propose other
> requirements, so your open-book polishing Agent also needs the ability to dynamically generate various tools. On top of the customized task,
> appropriately increase flexibility."
Broken into six things, this package maps to them one by one:
| What the user said | Where it lands |
|---|---|
| Want an **Agent** | `PolishAgent` in `polish/agent.py` (not "call a model once and get a paragraph back") |
| **Carry history** | `agent._compose()` — every call composes **the full event stream** (author's own words / tool calls / tool results / my conclusions / checkup) into messages |
| **Reflection model** | After wrapping up, run `_reflect()` once: take the author's own words + the whole process + actual changes, self-check for "missed edits / broken edits / overreach", and if there are problems, run another round with that feedback |
| **Write to both the project + reference folder** | Tools `append_source` (reference side, append-only, auto `.bak`) and `write_note` / `patch_settings` (project side) — **both paths live in `Toolbox` and both are governed by the sandbox** |
| **Operate the file system** | `Scope` + `resolve()` in `polish/sandbox.py`: only two roots are touchable, all other paths are `Denied` |
| **Run code in a sandbox, control permissions and scope** | `sandbox.check_source()` (AST static review) + `sandbox.run_code()` (**subprocess** execution, hard timeout, output cap, only a safe builtins subset and a "relative-path file API") |
| **Dynamically generate tools** | `write_tool` in `polish/codegen.py`: the Agent writes a Python tool on the spot → static review → write to disk → register → **immediately usable** |
## Directory
```
polish/sandbox.py Scope and permissions (root whitelist / AST review / restricted execution /
subprocess code running)
polish/tools.py Tool registry + built-in tools (read / search / patch / write back / record /
wrap up / ask back)
polish/codegen.py    Dynamically generate tools (the path where the Agent writes tools itself)
polish/agent.py Agent main loop + event-stream memory + Reflection (the main external entry
point)
polish/_runner.py The executor on the subprocess side (**not part of the package**, pulled up
separately by `subprocess`)
```
## How to use
```python
from polish import PolishAgent, Scope
agent = PolishAgent(settings=result.settings,
out.settings      # the modified settings
out.reply         # a paragraph for the author to read
out.changes       # what exactly changed this round (structured, for the UI to log)
out.actions       # which tools were called this round (including dynamically generated tools)
```
⚠ **Iron rule**: this package **does not issue LLM requests itself**, everything goes through
`llm.replies.ask` (that is the project-wide sole
entry point for "parse → retry → salvage"). This way conversation logs, budget ledger, and
output-language injection **all take effect automatically**.
"""
from __future__ import annotations

from polish.agent import PolishAgent, PolishTurn, PolishOutcome      # noqa: F401
from polish.sandbox import Denied, Scope, resolve, check_source       # noqa: F401
from polish.tools import TOOLS, Toolbox, ToolResult                   # noqa: F401

__all__ = [
    'PolishAgent', 'PolishTurn', 'PolishOutcome',
    'Denied', 'Scope', 'resolve', 'check_source',
    'TOOLS', 'Toolbox', 'ToolResult',
]
