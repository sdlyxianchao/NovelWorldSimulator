# MCP 服务（Model Context Protocol）

MCP 让我们能把「查资料」这件事交给**独立的小进程**，而不是让 LLM 硬编答案，
也不是把整本设定集塞进上下文。

在这个项目里，MCP 是**考据通道的第 4 层提供者**（设计稿 §8.6）：

```
考据请求 → ① 缓存 → ② 资料库 → ③ 技能 → ④ MCP → ⑤ 联网兜底 → ⑥ LLM
```

```
mcp/
├── README.md            ← 本文件
├── client.py            ← 客户端：拉起进程、握手、转发调用
└── servers/
    ├── _mcpkit.py            迷你服务器框架（写新服务器看它）
    ├── _projectfs.py         读小说项目文件夹的工具函数
    ├── project_lore_server.py   项目考据：人物卡/伏笔/世界观/进度/全文检索
    ├── timeline_server.py       故事线：每天的生活/关键事件/前情/全文检索
    └── clock_server.py          虚拟时钟：十二时辰换算/跨日进位/耗时估算
```

配置文件在项目根目录：**`mcp_servers.yaml`**（路径由 `.env` 的 `MCP_CONFIG` 指定）。

---

## 一、随程序发行的 3 个服务器

| 服务 | 读什么 | 工具 | 出机？ |
|---|---|---|---|
| **项目考据** | 项目 `设定集/` | `character` `list_characters` `foreshadows` `worldview` `progress` `lore_search` `project_overview` | ❌ 不出机 |
| **故事线** | 运行文件夹 | `run_overview` `day_index` `recent_days` `key_events` `story_so_far` `search_run` | ❌ 不出机 |
| **虚拟时钟** | 无（纯计算） | `shichen` `shichen_table` `advance` `real_cost` `now` | ❌ 不出机 |

这三个都是**只读**且**零网络**，所以默认就是启用状态，装完即可用。

另在 `mcp_servers.yaml` 里预置了 4 个联网模板（`fetch` / `duckduckgo-search` /
`wikipedia` / `time`），**默认 `enabled: false`**，要用自己改。

### 它们解决什么问题

**1. 上下文不够用。** 一本长篇的设定集可能有几万字，全塞进 prompt 会挤爆预算。
有了 `project_lore_server`，模型可以「按需取一页」：
问「主角的秘密」，只拿回那一张卡，而不是整本人物志。

**2. 前情回忆。** 写第 40 天时想知道第 37 天发生了什么，
`timeline_server.recent_days` 直接给最近几天的正文，不用翻文件。

**3. 算不对的东西交给机器。** 「戌时再过 7 个时辰是哪天」——
LLM 经常算错跨日进位。`clock_server.advance` 用 `divmod` 硬算，不会错。

---

## 二、自己写一个服务器（约 20 行）

MCP 的 stdio 传输就是**一行一个 JSON-RPC 2.0 消息**，没有魔法。
`_mcpkit.py` 把它包成了「注册工具 + 起循环」两步：

```python
# mcp/servers/my_server.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mcpkit import Server, text_result, serve

srv = Server('my-server', '1.0.0', instructions='这个服务器是干什么的')

@srv.tool('count_words',
          '统计一段文字的汉字数',
          {'text': {'type': 'string', 'description': '要统计的文字'}},
          required=['text'])
def count_words(args):
    n = sum(1 for ch in args['text'] if '\u4e00' <= ch <= '\u9fff')
    return text_result(f'汉字数：{n}')

if __name__ == '__main__':
    serve(srv)
```

然后在 `mcp_servers.yaml` 里登记：

```yaml
mcpServers:
  我的服务器:
    command: "{python}"
    args: ["mcp/servers/my_server.py"]
    enabled: true
    timeout: 20
    用途: "统计字数"
```

### 自检（不用接客户端）

```bash
python mcp/servers/my_server.py --list-tools
python mcp/servers/my_server.py --call count_words '{"text":"雨脚敲着檐瓦"}'
```

### 三条硬规矩

1. **stdout 只能出现协议消息。** 调试输出走 `stderr`（`print(..., file=sys.stderr)`），
   往 stdout 写一行多余的文字，客户端就会解析失败。
2. **每条响应都要 flush。** `_mcpkit` 已经处理了；自己写循环时别忘了，
   否则客户端会一直等。
3. **失败要分清层次。** 参数缺失 → JSON-RPC 错误（`-32602`）；
   业务失败（比如项目还没建）→ 正常响应 + `isError: true`。
   前者是「你不会用这个接口」，后者是「接口对了但这次没成功」——
   后者不该让客户端崩掉。

---

## 三、配置字段

| 字段 | 说明 |
|---|---|
| `command` | 可执行文件，一般是 `{python}` |
| `args` | 参数列表（**注意是列表，不是一行字符串**） |
| `enabled` | 默认关的纪律：外部/联网服务一律 `false`，用户自行开 |
| `timeout` | 单次调用超时（秒），不填用 `.env` 的 `MCP_TIMEOUT_SECONDS` |
| `用途` | 给人看的一句话；也会出现在日志里 |
| `url` | HTTP/SSE 型服务器。**本版本不支持**，写了会给出明确提示而不是静默失败 |

### 占位符（跨平台的关键）

写死路径会让配置在你同事的机器上失效。用占位符：

| 占位符 | 替换成 |
|---|---|
| `{python}` | 当前虚拟环境的 python（自动区分 Windows 的 `Scripts` 与 Unix 的 `bin`） |
| `{app_dir}` | 程序根目录 |
| `{project_dir}` | **当前打开的小说项目文件夹**（打开项目时自动同步） |
| `{env:NAME}` | 环境变量 `NAME` |

`{project_dir}` 是本地服务器能读到正确项目的原因 —— 打开哪个项目，就读哪个。

---

## 四、安全与合规

MCP 是**外部进程**，所以有两条纪律：

1. **只读。** 随程序发行的服务器一律不写盘。小说的数据只能由程序本体在
   用户确认后写入（设计稿 §1「程序永不反写项目文件夹」）。
2. **查询内容出机。** 走联网 MCP 时，**只发查询词，绝不发小说全文**。
   这与「联网搜索兜底」共用同一套「默认关 + 二次确认」。

`MCP_ENABLED=false` 是总闸，关掉后客户端**不会拉起任何进程**。

---

## 五、排查

```bash
python tools/verify_mcp_skills.py        # 端到端验证：握手、列工具、真调工具
python tools/verify_mcp_skills.py -v     # 带详细输出
```

常见问题：

| 现象 | 原因 |
|---|---|
| 调用返回 `None`，日志里没有错误 | 服务 `enabled: false`，或 `MCP_ENABLED=false` |
| `MCP 调用失败 … 超时` | 服务器启动慢（如 npx 首次下载），调大 `timeout` |
| `无法启动 'npx'` | 没装 Node.js。这两个是联网模板，不用就保持 `enabled: false` |
| 工具读不到项目 | `{project_dir}` 为空 —— 先在程序里打开一个项目 |

MCP 的失败**永远不会中断模拟**：所有异常都被记进日志并降级为「这一层没结果」，
继续走下一层提供者。
