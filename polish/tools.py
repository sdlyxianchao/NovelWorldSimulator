# -*- coding: utf-8 -*-
"""打磨 Agent 的**工具集**：一把能读、能改、能跑代码、能长出新手的手。

用户 2026-10-07：「你需要有能力操作文件系统。有别的工具你也需要的，**你可以自己尝试
写代码**（在沙盒里运行且控制权限和范围）别的用到的工具你也要自己写一下。而且我会
可能提出别的要求，你的开卷打磨的 Agent 也需要这个能力**动态生成各种工具**。
在定制任务的基础上适当增加灵活性。」

## 十二个工具，分四类

| 类 | 工具 | 干什么 |
|---|---|---|
| **看** | `读设定` · `列引用文件` · `读引用文件` · `检索引用` · `列工具` | 零副作用，随便调 |
| **改** | `改设定`（**结构化打补丁**）· `追加回写`（引用文件夹，只追加+备份）· `写记录` | 都受沙盒管，都留痕 |
| **动手写代码** | `生成工具`（**当场长出一个新工具**）· `跑代码`（临时算点东西） | 走 `polish/sandbox.run_code`：子进程、硬超时、只能写输出区 |
| **收口** | `收尾` · `提出疑问` | 由 `agent` 处理，不作为"动作"返回观察结果 |

## 两个刻意的设计

1. ★ **`改设定` 是"打补丁"，不是"回抄整份"**。上一版让模型把整份设定 JSON 重写
   一遍再回来 —— 那是**输出越长越容易撞上限被截断**，截断了就等于这一步白干
   （2026-10-06 那次「人物 7 位全丢」就是这么来的）。现在只回"改哪几处"：
   输出短、可校验、改没改一眼看得出。
2. ★ **引用文件夹只能"追加"，不能"覆盖"**。作者的原始素材是**不可再生的**；
   `追加回写` 走 `sandbox.append_text`（自动留 `.bak`、按字节追加），
   而生成代码那条路**连追加都不许**（写权限只有输出区）。

English:
Polish the Agent's **toolset**: a hand that can read, modify, run code, and grow new hands.
User 2026-10-07: "You need the ability to operate the filesystem. There are other tools you need
too, **you can try
writing code yourself** (running in a sandbox with controlled permissions and scope). Other
tools you need, you should write yourself too. And I will
possibly make other requests; your open-book polishing Agent also needs this ability to
**dynamically generate various tools**.
On top of the customized tasks, add appropriate flexibility."
## Twelve tools, in four categories
| Category | Tool | What it does |
|---|---|---|
| **Actually write code** | `生成工具` (**grow a new tool on the spot**) · `跑代码` (compute something temporarily) | Goes through `polish/sandbox.run_code`: subprocess, hard timeout, can only write to the output area |
## Two deliberate design choices
1. ★ **`改设定` is "patching", not "copying back the whole thing"**. The previous version made the model rewrite the entire settings JSON
   and send it back - that means **the longer the output, the more likely it hits the limit and gets truncated**, and truncation makes this step wasted
   (the 2026-10-06 incident where "all 7 characters lost" came from exactly this). Now it only returns "which spots to change":
   short output, verifiable, obvious at a glance whether it changed.
2. ★ **The reference folder can only be "appended to", never "overwritten"**. The author's original material is **non-renewable**;
   `追加回写` goes through `sandbox.append_text` (auto `.bak`, byte-wise append),
   while the code-generation path **is not even allowed to append** (write permission is only in the output area).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from i18n import t
from polish import sandbox as SB
from polish.sandbox import Denied, Scope

_LOG = __import__("logging").getLogger("nws.polish.tools")

#: 打补丁用的路径语法：`人物[0].性格` / `世界观` / `伏笔`
# [EN] : Path syntax used for patching: `人物[0].性格` / `世界观` / `伏笔`
_SEG_RE = re.compile(r'^([^\[\].]+)(?:\[(\d+)\])?$')


@dataclass
class ToolResult:
    """一次工具调用的结果。`text` 是**给模型看的观察结果**（必须是人话）。
        English:
    The result of one tool call. `text` is the **observation shown to the model** (must be
    human-readable).
    """

    ok: bool
    text: str = ''
    data: dict[str, Any] = field(default_factory=dict)

    def short(self) -> str:
        """给界面日志用的一行。
                English:
        One line for the UI log.
        """
        return ' '.join(str(self.text or '').split())[:120]


@dataclass
class Tool:
    """一个工具的自述。`kind` 为 `control` 的由 Agent 处理，不走工具调度。
        English:
    A tool's self-description. Those with `kind` = `control` are handled by the Agent, not routed
    through tool dispatch.
    """

    name: str
    desc: str
    args: str                      # 参数说明（一行，写给人看也写给模型看）
    # [EN] Parameter description (one line, written for both humans and the model)
    kind: str = 'tool'             # tool | control
    needs: str = ''                # read | write_out | write_src | codegen


#: **工具目录**（唯一事实来源：提示词、界面、「列工具」都读它）
# [EN] : **Tool catalog** (single source of truth: prompts, UI, "list tools" all read it)
TOOLS: tuple[Tool, ...] = (
    Tool('读设定', '看当前设定。可只取一个片段（省字数）。',
         '路径（可选，如「人物[0].性格」「伏笔」，不填=整份）', needs='read'),
    Tool('改设定', '**改设定请用这个**，不要回抄整份。一次可以改好几处。',
         '操作（数组）：每项 {"动作":"改|加|删","路径":"人物[0].性格","值":...}',
         needs='write_out'),
    Tool('列引用文件', '列出作者的引用文件夹里有哪些文件（带前缀的相对路径）。',
         '', needs='read'),
    Tool('读引用文件', '读引用文件夹里的一个文件（可只取一段）。',
         '路径；起（可选，从第几个字开始）；长度（可选，默认 4000）', needs='read'),
    Tool('检索引用', '在引用文件夹里搜一个词，返回命中位置与上下文。',
         '关键词；上限（可选，默认 20）', needs='read'),
    Tool('追加回写', '把一段话**追加**到引用文件夹里的文件（自动留 .bak；不能覆盖）。',
         '路径；内容', needs='write_src'),
    Tool('写记录', '在打磨输出区写一份文件（打磨记录、建议清单这类）。',
         '文件名（默认「打磨记录.md」）；内容', needs='write_out'),
    Tool('生成工具', '**你现场写一个新工具**（Python），沙盒静态审查后立刻可用。'
                     '以后每一步都能调它。',
         '名称；说明；代码（必须含顶层函数 run(args)，用沙盒给的 '
         'read_text/write_text/list_files，只能写输出区）；试跑参数（可选）',
         needs='codegen'),
    Tool('跑代码', '临时跑一段 Python 算点东西（不注册成工具）。'
                   '可以 print，也可以 write_text 到输出区。',
         '代码；参数（可选）', needs='codegen'),
    Tool('列工具', '看看现在有哪些工具可用（含你之前生成的）。', '', needs='read'),
    Tool('收尾', '这一轮做完了，给作者一句回话，并列出你改了什么。',
         '回话；改了什么（数组，每项一句话）', kind='control'),
    Tool('提出疑问', '信息不够、要作者拍板时用。这一轮就此停下，等作者回答。',
         '问题', kind='control'),
)

BY_NAME: dict[str, Tool] = {x.name: x for x in TOOLS}

#: 会**改动盘上东西**的工具（沙盒审计/界面日志按它分类）
# [EN] : Tools that **modify things on disk** (sandbox audit / UI log classify by it)
WRITING = frozenset(x.name for x in TOOLS if x.needs in ('write_out', 'write_src'))


def catalog_text(*, generated: tuple[str, ...] = ()) -> str:
    """渲染给模型看的工具清单。生成出来的工具**排在最后并标出来**。
        English:
    The tool list rendered for the model. Generated tools are **placed last and marked**.
    """
    lines: list[str] = []
    for x in TOOLS:
        arg = f'　参数：{x.args}' if x.args else ''
        lines.append(f'· {x.name} —— {x.desc}{arg}')
    if generated:
        lines.append(f'（你这次已经生成的工具：{"、".join(generated)}）')
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════
#  路径语法（`人物[0].性格`）
# [EN] Path syntax (`人物[0].性格`)
# ══════════════════════════════════════════════════════════════════
class PathError(ValueError):
    """路径写错了（**不是越权**）—— 消息要能指导模型改对。
        English:
    Path written wrong (**not a permission violation**) - the message must guide the model to fix
    it.
    """


def parse_path(path: str) -> list[Any]:
    """`人物[0].性格` → `['人物', 0, '性格']`。"""
    s = str(path or '').strip().replace('．', '.').replace('。', '.')
    if not s:
        return []
    out: list[Any] = []
    for seg in s.split('.'):
        seg = seg.strip()
        if not seg:
            continue
        m = _SEG_RE.match(seg)
        if not m:
            raise PathError(t('路径片段看不懂：{s}（写法像「人物[0].性格」或「伏笔」）'
                              ).format(s=seg))
        out.append(m.group(1))
        if m.group(2) is not None:
            out.append(int(m.group(2)))
    return out


def get_path(obj: Any, path: list[Any]) -> Any:
    cur = obj
    for k in path:
        if isinstance(k, int):
            if not isinstance(cur, list) or k >= len(cur):
                raise PathError(t('下标越界：{k}').format(k=k))
            cur = cur[k]
        else:
            if not isinstance(cur, dict) or k not in cur:
                raise PathError(t('没有这一项：{k}').format(k=k))
            cur = cur[k]
    return cur


def set_path(obj: Any, path: list[Any], value: Any) -> None:
    if not path:
        raise PathError(t('不能把整份设定替换掉（请指定具体路径）'))
    parent = get_path(obj, path[:-1]) if len(path) > 1 else obj
    last = path[-1]
    if isinstance(last, int):
        if not isinstance(parent, list) or last >= len(parent):
            raise PathError(t('下标越界：{k}').format(k=last))
        parent[last] = value
    else:
        if not isinstance(parent, dict):
            raise PathError(t('这一层不是对象，改不了：{k}').format(k=last))
        parent[last] = value


def del_path(obj: Any, path: list[Any]) -> Any:
    if not path:
        raise PathError(t('不能删掉整份设定'))
    parent = get_path(obj, path[:-1]) if len(path) > 1 else obj
    last = path[-1]
    if isinstance(last, int):
        if not isinstance(parent, list) or last >= len(parent):
            raise PathError(t('下标越界：{k}').format(k=last))
        return parent.pop(last)
    if not isinstance(parent, dict) or last not in parent:
        raise PathError(t('没有这一项：{k}').format(k=last))
    return parent.pop(last)


# ══════════════════════════════════════════════════════════════════
#  工具箱
# [EN] Toolbox
# ══════════════════════════════════════════════════════════════════
class Toolbox:
    """一次打磨会话的工具箱。**所有状态都在这里**（Agent 只负责决策与说话）。

    `settings` 是**活的**引用：`改设定` 直接改它，Agent 拿回去的就是改完的
    （不搞"返回新设定"，那样很容易出现两个版本各改一半）。
    
        English:
    The toolbox of one polishing session. **All state lives here** (the Agent only handles decisions
    and talking).
        `settings` is a **live** reference: `改设定` modifies it directly, and what the Agent gets back is the modified version
        (no "return a new settings", which easily leads to two versions each half-modified).
    """

    def __init__(self, *, settings: dict[str, Any], scope: Scope,
                 name: str = '', tier: str = '', missing: tuple[str, ...] = (),
                 allow_codegen: bool = True, max_calls: int | None = None):
        self.settings = settings
        self.scope = scope
        self.name = name
        self.tier = tier
        self.missing = tuple(missing or ())
        self.allow_codegen = bool(allow_codegen)
        self.max_calls = int(max_calls if max_calls is not None
                             else (scope.max_tool_calls or 60))
        #: 生成出来的工具：名字 → (Tool, 源码路径)
        # [EN] : Generated tools: name -> (Tool, source path)
        self.generated: dict[str, tuple[Tool, Path]] = {}
        #: 累计调用次数（防死循环）
        # [EN] : Cumulative call count (prevents infinite loops)
        self.calls = 0
        #: 这一轮改过的东西（给界面日志与 Reflection 用）
        # [EN] : Things changed this round (used by UI log and Reflection)
        self.changes: list[str] = []
        #: 往引用文件夹追加过的文件
        # [EN] : Files appended to the reference folder
        self.source_writes: list[str] = []
        #: 待取走的文件（Agent 收工时要落盘/搬进项目的）
        # [EN] : Files pending pickup (to be persisted/moved into the project when the Agent finishes)
        self.outputs: dict[str, str] = {}
        self._src_cache: dict[str, str] = {}

    # ── 对外 ────────────────────────────────────────────────────
    # [EN] ── External ────────────────────────────────────────────────────
    async def call(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """调度一次工具调用。**异常一律变成一句人话**返回给模型。

        只有一种情况会往上抛：调用次数超限（那是 Agent 自己的循环问题，
        不该让模型继续在里面转）。
        
                English:
        Dispatch one tool call. **All exceptions become a human-readable sentence** returned to the
        model.
                Only one case is thrown upward: call count exceeded (that's the Agent's own loop problem,
                the model shouldn't be allowed to keep spinning inside it).
        """
        nm = str(name or '').strip()
        a = dict(args or {})
        tool = BY_NAME.get(nm)
        gen = self.generated.get(nm)
        if tool is None and gen is not None:
            tool = gen[0]
        if tool is None:
            return ToolResult(False, t('没有这个工具：{n}。可用的有：{ok}').format(
                n=nm or '（空）',
                ok='、'.join(x.name for x in TOOLS) + (
                    '、' + '、'.join(self.generated) if self.generated else '')))
        if tool.kind == 'control':
            return ToolResult(False, t('{n} 不是动作工具（它由流程处理）').format(n=nm))
        if self.calls >= self.max_calls:
            raise RuntimeError(t('工具调用次数超过上限（{n} 次）—— 停下来收尾吧'
                                 ).format(n=self.max_calls))
        self.calls += 1
        try:
            if gen is not None:
                return await self._run_generated(nm, gen[1], a)
            handler: Callable = getattr(self, f'_t_{_slug(nm)}', None)  # type: ignore[assignment]
            if handler is None:
                return ToolResult(False, t('这个工具还没接上：{n}').format(n=nm))
            return await handler(a)
        except Denied as e:
            # 沙盒的正常拒绝 —— **要原样讲给模型听**，它才有机会改对
            # [EN] Normal sandbox rejection - **must be relayed verbatim to the model** so it has a chance to fix
            # [EN] it
            return ToolResult(False, t('不行：{why}').format(why=e))
        except PathError as e:
            return ToolResult(False, t('路径写法有问题：{why}').format(why=e))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('工具 %s 出错：%r', nm, e)
            return ToolResult(False, t('这个工具自己出错了：{e!r}').format(e=e))

    def describe(self) -> str:
        return catalog_text(generated=tuple(self.generated))

    def take_outputs(self) -> dict[str, str]:
        out = dict(self.outputs)
        self.outputs.clear()
        return out

    def take_changes(self) -> list[str]:
        out = list(self.changes)
        self.changes.clear()
        return out

    # ── 看 ──────────────────────────────────────────────────────
    # [EN] ── Read ──────────────────────────────────────────────────────
    async def _t_读设定(self, a: dict) -> ToolResult:               # noqa: N802
        path = str(a.get('路径') or a.get('path') or '').strip()
        if path:
            try:
                got = get_path(self.settings, parse_path(path))
            except PathError as e:
                return ToolResult(False, t('取不到这一段：{why}。'
                                           '可以先用「读设定」不填路径看全貌').format(why=e))
            body = json.dumps(got, ensure_ascii=False, indent=1)
        else:
            body = json.dumps(self.settings, ensure_ascii=False, indent=1)
        cap = self.scope.max_output_chars
        if len(body) > cap:
            body = body[:cap] + t('\n…（设定较长，已截断；可以用「读设定」带路径'
                                  '只看某一段）')
        return ToolResult(True, body)

    async def _t_列引用文件(self, a: dict) -> ToolResult:            # noqa: N802
        if self.scope.src_root is None:
            return ToolResult(False, t('这次没有连接引用文件夹'))
        try:
            files = SB.list_files(self.scope, SB.PREFIX_SRC)
        except Denied as e:
            return ToolResult(False, str(e))
        if not files:
            return ToolResult(True, t('（引用文件夹里没有可读的文件）'))
        return ToolResult(True, '\n'.join(files[:200]),
                          {'文件数': len(files)})

    async def _t_读引用文件(self, a: dict) -> ToolResult:            # noqa: N802
        rel = str(a.get('路径') or a.get('path') or '').strip()
        if not rel:
            return ToolResult(False, t('要给出「路径」（可以先「列引用文件」看看）'))
        if not rel.lower().startswith(SB.PREFIX_SRC):
            rel = SB.PREFIX_SRC + rel
        text = self._src_text(rel)
        if text is None:
            return ToolResult(False, t('读不到这个文件：{p}').format(p=rel))
        try:
            start = max(0, int(a.get('起') or a.get('start') or 0))
        except (TypeError, ValueError):
            start = 0
        try:
            length = int(a.get('长度') or a.get('length') or 4000)
        except (TypeError, ValueError):
            length = 4000
        body = text[start:start + max(200, length)]
        head = t('（{p} 共 {n} 字，这次给你第 {s}~{e} 字）').format(
            p=rel, n=len(text), s=start, e=start + len(body))
        return ToolResult(True, head + '\n' + body, {'总字数': len(text)})

    async def _t_检索引用(self, a: dict) -> ToolResult:              # noqa: N802
        kw = str(a.get('关键词') or a.get('keyword') or '').strip()
        if not kw:
            return ToolResult(False, t('要给出「关键词」'))
        try:
            limit = max(1, min(60, int(a.get('上限') or a.get('limit') or 20)))
        except (TypeError, ValueError):
            limit = 20
        if self.scope.src_root is None:
            return ToolResult(False, t('这次没有连接引用文件夹'))
        hits: list[str] = []
        scanned = 0
        for rel in SB.list_files(self.scope, SB.PREFIX_SRC):
            if len(hits) >= limit or scanned > 400000:
                break
            body = self._src_text(rel)
            if not body:
                continue
            scanned += len(body)
            for m in re.finditer(re.escape(kw), body):
                if len(hits) >= limit:
                    break
                s = max(0, m.start() - 60)
                snippet = ' '.join(body[s:m.start() + 100].split())
                hits.append(f'{rel}：…{snippet}…')
        if not hits:
            return ToolResult(True, t('（没有搜到「{k}」）').format(k=kw))
        return ToolResult(True, t('搜到 {n} 处：').format(n=len(hits))
                          + '\n' + '\n'.join(hits))

    async def _t_列工具(self, a: dict) -> ToolResult:                # noqa: N802
        return ToolResult(True, self.describe())

    # ── 改 ──────────────────────────────────────────────────────
    # [EN] ── Modify ──────────────────────────────────────────────────────
    async def _t_改设定(self, a: dict) -> ToolResult:                # noqa: N802
        ops = a.get('操作') or a.get('ops') or []
        if isinstance(ops, dict):
            ops = [ops]
        if not isinstance(ops, list) or not ops:
            return ToolResult(False, t('要给出「操作」，形如 '
                                       '[{"动作":"改","路径":"人物[0].性格","值":"…"}]'))
        done: list[str] = []
        failed: list[str] = []
        for op in ops:
            if not isinstance(op, dict):
                failed.append(t('这一项不是对象：{x}').format(x=str(op)[:40]))
                continue
            act = str(op.get('动作') or op.get('op') or '改').strip()
            raw_path = str(op.get('路径') or op.get('path') or '').strip()
            val = op.get('值') if '值' in op else op.get('value')
            try:
                path = parse_path(raw_path)
                before = None
                try:
                    before = get_path(self.settings, path)
                except PathError:
                    before = None
                if act in ('改', 'set', 'replace'):
                    set_path(self.settings, path, val)
                elif act in ('加', 'append', 'add'):
                    # 路径指向数组 → 追加一项；指向对象 → 给这个 key 赋值
                    # [EN] Path points to an array -> append an item; points to an object -> assign a value to this key
                    target = None
                    try:
                        target = get_path(self.settings, path)
                    except PathError:
                        target = None
                    if isinstance(target, list):
                        target.append(val)
                    else:
                        set_path(self.settings, path, val)
                elif act in ('删', 'del', 'remove'):
                    del_path(self.settings, path)
                else:
                    failed.append(t('不认得的动作「{a}」（只有 改/加/删）').format(a=act))
                    continue
                done.append(t('{a} {p}：{b} → {v}').format(
                    a=act, p=raw_path or '(空)',
                    b=_brief(before), v=_brief(val)))
            except (PathError, Denied) as e:
                failed.append(t('{p}：{why}').format(p=raw_path or '(空路径)', why=e))

        if not done:
            return ToolResult(False, t('一处都没改成：\n') + '\n'.join(failed[:6]))

        # 归一化（顺手把畸形输入整平，与摄取那一步用同一套校验）
        # [EN] Normalization (also flattens malformed input along the way, using the same validation as the
        # [EN] ingestion step)
        try:
            from ingest.extractor import validate_settings
            self.settings = validate_settings(self.settings)
        except Exception:                                        # noqa: BLE001
            pass
        self.changes.extend(done)
        body = t('改了 {n} 处：').format(n=len(done)) + '\n' + '\n'.join(done)
        if failed:
            body += '\n' + t('这几处没成：') + '\n' + '\n'.join(failed[:6])
        return ToolResult(True, body, {'改动': done, '失败': failed})

    async def _t_追加回写(self, a: dict) -> ToolResult:              # noqa: N802
        rel = str(a.get('路径') or a.get('path') or '').strip()
        body = str(a.get('内容') or a.get('text') or '')
        if not rel or not body.strip():
            return ToolResult(False, t('要给出「路径」和「内容」'))
        if self.scope.src_root is None:
            return ToolResult(False, t('这次没有连接引用文件夹'))
        if not self.scope.allow_write_src:
            return ToolResult(False, t('这次会话被设定为不回写引用文件夹'))
        if not rel.lower().startswith(SB.PREFIX_SRC):
            rel = SB.PREFIX_SRC + rel
        p, fresh = SB.append_text(self.scope, rel, body)
        shown = SB.relabel(self.scope, p)
        self.source_writes.append(shown)
        self._src_cache.pop(shown, None)
        if fresh:
            return ToolResult(True, t('已新建 {p}（{n} 字）').format(
                p=shown, n=len(body)), {'回写': shown, '新建': True})
        return ToolResult(True, t('已**追加**到 {p}（{n} 字）；原文件留了一份 '
                                  '{p}.bak，正文一个字没动').format(
            p=shown, n=len(body)), {'回写': shown, '新建': False})

    async def _t_写记录(self, a: dict) -> ToolResult:                # noqa: N802
        fn = str(a.get('文件名') or a.get('name') or '打磨记录.md').strip()
        body = str(a.get('内容') or a.get('text') or '')
        if not body.strip():
            return ToolResult(False, t('要给出「内容」'))
        p = SB.write_text(self.scope, SB.PREFIX_OUT + fn, body)
        shown = SB.relabel(self.scope, p)
        self.outputs[shown] = body
        return ToolResult(True, t('已写入 {p}（{n} 字）').format(
            p=shown, n=len(body)), {'写了': shown})

    # ── 动手写代码 ──────────────────────────────────────────────
    # [EN] ── Actually write code ──────────────────────────────────────────────
    async def _t_跑代码(self, a: dict) -> ToolResult:                # noqa: N802
        if not self.allow_codegen:
            return ToolResult(False, t('这次会话关掉了「现场写代码」'))
        code = str(a.get('代码') or a.get('code') or '')
        if not code.strip():
            return ToolResult(False, t('要给出「代码」'))
        args = a.get('参数') if isinstance(a.get('参数'), dict) else {}
        out = SB.run_code(self.scope, code, args=args, name='临时代码',
                          require_run=bool(args) or 'def run' in code)
        return ToolResult(out.ok, out.as_observation(),
                          {'用时': round(out.seconds, 2)})

    async def _t_生成工具(self, a: dict) -> ToolResult:              # noqa: N802
        if not self.allow_codegen:
            return ToolResult(False, t('这次会话关掉了「动态生成工具」'))
        nm = str(a.get('名称') or a.get('name') or '').strip()
        desc = str(a.get('说明') or a.get('desc') or '').strip()
        code = str(a.get('代码') or a.get('code') or '')
        if not nm or not code.strip():
            return ToolResult(False, t('要给出「名称」和「代码」'))
        if not re.fullmatch(r'[\w\u4e00-\u9fff·\-]{1,24}', nm):
            return ToolResult(False, t('工具名只用汉字/字母/数字/下划线，最长 24 字'))
        if nm in BY_NAME:
            return ToolResult(False, t('{n} 是内置工具名，换一个').format(n=nm))

        from polish import codegen
        res = codegen.register(self, nm, code, desc=desc,
                               dry_args=(a.get('试跑参数')
                                         if isinstance(a.get('试跑参数'), dict) else None))
        return res

    # ── 内部 ────────────────────────────────────────────────────
    # [EN] ── Internal ────────────────────────────────────────────────────
    async def _run_generated(self, name: str, path: Path, a: dict) -> ToolResult:
        """跑一个**生成出来的**工具（子进程 + 沙盒）。
                English:
        Run a **generated** tool (subprocess + sandbox).
        """
        try:
            code = path.read_text(encoding='utf-8')
        except OSError as e:                                     # noqa: BLE001
            return ToolResult(False, t('读不出这个工具的源码：{e}').format(e=e))
        out = SB.run_code(self.scope, code, args=a, name=name, require_run=True)
        return ToolResult(out.ok, out.as_observation(),
                          {'用时': round(out.seconds, 2), '生成工具': name})

    def _src_text(self, rel: str) -> str | None:
        """读引用文件（带缓存：同一次会话里反复读同一个文件很常见）。
                English:
        Read a reference file (with cache: reading the same file repeatedly in one session is very
        common).
        """
        if rel in self._src_cache:
            return self._src_cache[rel]
        try:
            body = SB.read_text(self.scope, rel)
        except (Denied, OSError):
            return None
        # 缓存也吃上限：素材可能有几十万字，别把内存吃掉
        # [EN] Cache also hits the limit: material may be hundreds of thousands of characters, don't eat up
        # [EN] memory
        self._src_cache[rel] = body[:200000]
        return self._src_cache[rel]


def _slug(name: str) -> str:
    """工具名 → 方法名后缀（`读设定` → `读设定`，方法名用中文，可读性最好）。
        English:
    Tool name → method name suffix (`读设定` → `读设定`, method names use Chinese for best readability).
    """
    return re.sub(r'[^\w\u4e00-\u9fff]', '_', str(name or ''))


def _brief(v: Any, limit: int = 40) -> str:
    if v is None:
        return '（无）'
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
    else:
        s = str(v)
    s = ' '.join(s.split())
    return s[:limit] + ('…' if len(s) > limit else '')
