# -*- coding: utf-8 -*-
"""**动态生成工具** —— Agent 现场给自己长出一只手。

用户 2026-10-07：「我会可能提出别的要求，你的开卷打磨的 Agent 也需要这个能力
**动态生成各种工具**。在定制任务的基础上适当增加灵活性。」

## 为什么"生成工具"和"临时跑代码"是两个工具

看着重复，其实分工是清楚的：

| | `跑代码` | `生成工具` |
|---|---|---|
| 活多久 | 这一次调用 | **剩下整场**（之后每一步都能调） |
| 落盘吗 | 不落 | 落 `AI工具/<名>.py`（可复用、可审计） |
| 用在哪 | "算一下这段文本有多少字" | "这本书有 37 个人物，我要一个按姓氏归并的助手" |

用户那句"适当增加灵活性"落到这里就是：**当内置工具不够用时，Agent 不该说
"我做不到"，而该写一个出来**。

## 落盘与生命周期

```
<打磨输出区>/AI工具/<名>.py     ← 每生成一个工具就多一个文件
```

* 落盘位置是**输出区**（不是引用文件夹）：生成工具属于"打磨过程的产物"，
  开卷结束时随其它产物一起进项目，将来那一轮推演也能用；
* **开新一场会话时会自动加载**（`load_existing`）—— 上一场生成过的工具
  这一场还在，否则"生成工具"就成了一次性的玩具；
* 加载时**重新过一遍静态审查**：盘上的文件可以被任何人改，
  上一场它是安全的，不代表这一场还是。

## 三道关，缺一不可

1. **`sandbox.check_source`** —— 危险导入/属性/内置名一律拒，**拒了要讲清为什么**；
2. **试跑**（可选，Agent 给了「试跑参数」就真跑一次）—— 让"写了个错的工具"
   当场暴露，而不是等它调的时候才发现；
3. **执行时再检查**（`polish/_runner.py` 里那一遍）—— 纵深防御。

English:
**Dynamic tool generation** —— the Agent grows itself a hand on the spot.
User 2026-10-07: "I may raise other requirements; your open-book polishing Agent also needs this
capability
**dynamically generate various tools**. Add appropriate flexibility on top of the customized
task."
## Why "generate tool" and "run code temporarily" are two separate tools
They look redundant, but the division of labor is clear:
| | `run code` | `generate tool` |
|---|---|---|
| How long it lives | this one call | **the rest of the whole session** (callable at every later step) |
| Written to disk? | no | yes, to `AI工具/<name>.py` (reusable, auditable) |
| Where it's used | "count how many characters this text has" | "this book has 37 characters, I want a helper that groups by surname" |
The user's phrase "add appropriate flexibility" lands here as: **when the built-in tools aren't
enough, the Agent shouldn't say
"I can't do it", but should write one**
## Persistence and lifecycle
```
<polish output area>/AI工具/<name>.py     ← each generated tool adds one more file
```
* The persistence location is the **output area** (not the reference folder): generated tools are "products of the polishing process",
  and at the end of the open-book session they enter the project along with the other products, usable in that future round of simulation;
* **Loaded automatically when a new session starts** (`load_existing`) —— tools generated in the previous session
  are still here in this one, otherwise "generate tool" becomes a one-off toy;
* On load, **re-run the static review**: files on disk can be modified by anyone,
  being safe last session doesn't mean it's still safe this session.
## Three gates, none can be skipped
1. **`sandbox.check_source`** —— dangerous imports/attributes/builtins are all rejected, **and if rejected, explain clearly why**;
2. **Trial run** (optional, actually runs once if the Agent provided "trial-run args") —— makes "wrote a broken tool"
   surface immediately, instead of only being discovered when it's called;
3. **Re-check at execution time** (the pass in `polish/_runner.py`) —— defense in depth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from i18n import t
from polish import sandbox as SB
from polish.tools import Tool, ToolResult

_LOG = __import__("logging").getLogger("nws.polish.codegen")

#: 生成出来的工具放哪儿（输出区下的一个子目录）
# [EN] : Where generated tools go (a subdirectory under the output area)
AI_TOOLS_DIR = 'AI工具'


def tools_dir(box: Any) -> Path:
    """这次会话的"生成工具"目录（不存在就建）。
        English:
    This session's "generated tools" directory (created if it doesn't exist).
    """
    if box.scope.out_root is None:
        raise SB.Denied(t('这次会话没有可写的打磨输出区，生成不了工具'))
    d = Path(box.scope.out_root) / AI_TOOLS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def register(box: Any, name: str, code: str, *, desc: str = '',
             dry_args: dict[str, Any] | None = None) -> ToolResult:
    """把一段源码注册成一个**立刻可用**的工具。

    「先审查、再落盘、再试跑」的顺序是刻意的：审查不过的代码**根本不落盘**
    （不留一个"在盘上躺着但用不了"的文件，那会让下次加载时报一堆看不懂的错）。
    
        English:
    Register a piece of source code as an **immediately usable** tool.
        The order "review first, then persist, then trial-run" is deliberate: code that fails review **is not persisted at all**
        (don't leave a file "lying on disk but unusable", which would cause a pile of incomprehensible errors on the next load).
    """
    bad = SB.check_source(code, require_run=True)
    if bad:
        return ToolResult(False, t('这个工具还不能用，先改这几点：\n· ') + '\n· '.join(bad[:8]))

    try:
        d = tools_dir(box)
    except SB.Denied as e:
        return ToolResult(False, str(e))
    path = d / f'{name}.py'
    existed = path.exists()
    header = (f'# -*- coding: utf-8 -*-\n'
              f'# 由打磨 Agent 现场生成：{name}\n'
              f'# 说明：{desc or "（没写说明）"}\n'
              f'# ⚠ 这个文件会被 `polish.sandbox` 静态审查之后在**子进程**里执行；\n'
              f'#   它只能写打磨输出区（`out:`），不许碰引用文件夹。\n')
    path.write_bytes((header + '\n' + str(code).rstrip() + '\n').encode('utf-8'))

    tool = Tool(name=name, desc=desc or t('（现场生成的工具）'),
                args=t('参数由这个工具自己定（看它的源码）'), needs='codegen')
    box.generated[name] = (tool, path)

    lines = [t('工具「{n}」已经生成好了，现在起你可以直接调它。').format(n=name)]
    if existed:
        lines.append(t('（同名的那份被这次的新版本覆盖了）'))
    lines.append(t('→ 调它：{{"想":"…","用":"{n}","参":{{…}}}}').format(n=name))

    if dry_args is not None:
        out = SB.run_code(box.scope, code, args=dry_args, name=name, require_run=True)
        if out.ok:
            lines.append(t('试跑通过（{s} 秒）。它回的是：\n{x}').format(
                s=round(out.seconds, 2), x=out.text[:800] or t('（空）')))
        else:
            lines.insert(0, t('⚠ 试跑**没通过**，先看这个再决定要不要修：{why}').format(
                why=out.why))
    return ToolResult(True, '\n'.join(lines),
                      {'工具': name, '路径': SB.relabel(box.scope, path),
                       '覆盖': existed})


def load_existing(box: Any) -> list[str]:
    """把**盘上已有的**生成工具装回来（上一场留下的那些）。

    ⚠ 装回来之前**重新过一遍静态审查**：盘上的文件可以被任何人改。
      不合格的**跳过并记一条警告**，不抛 —— 一个坏文件不该让整场打磨开不了工。
    
        English:
    Reinstall the generated tools **already on disk** (those left from the previous session).
        ⚠ Before reinstalling, **re-run the static review**: files on disk can be modified by anyone.
          Skip unqualified ones **and log a warning**, don't throw —— one bad file shouldn't prevent the whole polishing session from starting.
    """
    try:
        d = tools_dir(box)
    except SB.Denied:
        return []
    loaded: list[str] = []
    for p in sorted(d.glob('*.py')):
        name = p.stem
        if name in box.generated or name.startswith('_'):
            continue
        try:
            src = p.read_text(encoding='utf-8')
        except OSError:
            continue
        if SB.check_source(src, require_run=True):
            _LOG.warning('盘上的生成工具 %s 没过审查，跳过', name)
            continue
        box.generated[name] = (
            Tool(name=name, desc=t('（上次生成的工具）'), args='',
                 needs='codegen'), p)
        loaded.append(name)
    return loaded
