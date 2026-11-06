# -*- coding: utf-8 -*-
"""**打磨 Agent 的沙盒**：作用域、权限、静态审查、受限执行。

用户 2026-10-07：「**你需要有能力操作文件系统**……你可以自己尝试写代码
（**在沙盒里运行且控制权限和范围**）别的用到的工具你也要自己写一下。」

## 先把话说清楚：这是**护栏**，不是安全边界

沙盒要挡的是**手滑**与**失控**，不是"恶意 AI"：

* 模型写出 `Path('/').unlink()`、写到 `C:\\Windows`、写一个 100MB 的文件；
* 模型写个 `while True: pass` 把界面卡死；
* 模型"顺手"把作者的原始素材覆盖掉（那是最贵的：素材是**不可再生的**）。

所以三层：**路径白名单**（只认两个根）· **AST 静态审查**（危险导入/属性/内置名）·
**子进程执行**（硬超时 + 输出上限 + 独立工作目录 + 只给安全 builtins 子集）。

★ **不哄人的那一句**：静态检查挡不住所有东西（`getattr(x, '__cl'+'ass__')` 这种
拼出来的名字就挡不住）。真正的边界是**使用场景**：这是作者在自己机器上、
对自己的素材、用自己配的模型在跑。本模块的职责是"让绝大多数意外变成一句
清清楚楚的拒绝"，**不是"宣称这里绝对安全"** —— 本项目对"宣称"这件事很敏感
（见 `使用说明` 里那条"不许留假按钮"）。

## 两个根，一个前缀规则

```
根             前缀     能读   能写
引用文件夹     src:      ✅    ✅（**只追加**，且自动留 `.bak`）
打磨输出区     out:      ✅    ✅（默认都写这里；可新建、可覆盖）
```

* **读**不带前缀 → `src:`（Agent 最常做的是读引用文件）
* **写**不带前缀 → `out:`（最安全的那一侧）
* 绝对路径 / `..` / 符号链接逃逸 → **一律 `Denied`**，并给出一句人话原因

## 执行

| 谁 | 在哪儿跑 |
|---|---|
| **内置工具**（`polish/tools.py`，我方代码） | 主进程直接跑（它们自己走 `resolve()` 管路径） |
| **Agent 现场生成的代码**（`write_tool` / `run_python`） | **子进程**（`polish/_runner.py`）：超时可杀、崩了不连累主进程、cwd 在临时目录 |

⚠ 生成代码的**写权限只有 `out:`** —— 想动引用文件夹，必须走内置的
`append_source`（只追加 + 自动备份）。这条是刻意的：**"AI 现场写的代码"
不该有碰用户原始素材的手**。

English:
**Sandbox for the polish Agent**: scope, permissions, static review, restricted execution.
User 2026-10-07: "**You need to be able to operate the filesystem**... you can try writing code
yourself
(**run in a sandbox with permissions and scope controlled**) and you should also write the other
tools you use yourself."
## Straight talk first: this is a **guardrail**, not a security boundary
What the sandbox guards against is **slip-ups** and **losing control**, not a "malicious AI":
* the model writes `Path('/').unlink()`, writes to `C:\\Windows`, writes a 100MB file;
* the model writes a `while True: pass` and freezes the UI;
* the model "casually" overwrites the author's original material (that is the most expensive: material is **non-renewable**).
So three layers: **path whitelist** (only two roots recognized) · **AST static review**
(dangerous imports/attributes/builtin names) ·
**child process execution** (hard timeout + output cap + independent working directory + only a
safe builtins subset).
★ **The line that does not sugarcoat it**: static checks cannot block everything (names
assembled like `getattr(x, '__cl'+'ass__')`
cannot be blocked). The real boundary is the **usage scenario**: this is the author on their own
machine,
running on their own material, with their own configured model. This module's job is "turn the
vast majority of accidents into one
crystal-clear rejection", **not "claim this is absolutely safe"** -- this project is very
sensitive about "claims"
(see the "no fake buttons allowed" entry in `使用说明`).
## Two roots, one prefix rule
```
root           prefix   read   write
reference folder     src:     ✅    ✅ (**append-only**, and automatically keeps a `.bak`)
polish output area out: ✅ ✅ (writes go here by default; can create new, can overwrite)
```
* **Read** without prefix → `src:` (what the Agent does most is read referenced files)
* **Write** without prefix → `out:` (the safest side)
* Absolute paths / `..` / symlink escapes → **always `Denied`**, with a plain-language reason
## Execution
| Who | Where it runs |
|---|---|
| **Built-in tools** (`polish/tools.py`, our own code) | Run directly in the main process (they handle paths themselves via `resolve()`) |
| **Code generated live by the Agent** (`write_tool` / `run_python`) | **Subprocess** (`polish/_runner.py`): can be killed on timeout, a crash doesn't take down the main process, cwd is in a temp directory |
⚠ Generated code's **write permission is only `out:`** -- to touch the reference folder, it must
go through the built-in
`append_source` (append-only + automatic backup). This is deliberate: **"code written live by
the AI"
should not have hands that can touch the user's original material**.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from i18n import t

_LOG = __import__("logging").getLogger("nws.polish.sandbox")

#: 应用根（子进程要靠它 `sys.path.insert` 找得到 `polish` 包）
# [EN] : application root (child processes rely on it to `sys.path.insert` so they can find the
# [EN] `polish` package)
APP_DIR = Path(__file__).resolve().parent.parent
#: 子进程侧的执行器
# [EN] : executor on the child process side
RUNNER = Path(__file__).resolve().parent / "_runner.py"


class Denied(Exception):
    """越权/违规 —— **不是程序错误**，是沙盒的正常拒绝。

    调用方（工具集）必须把它**变成一句给模型看的话**返回，而不是往上抛：
    模型看到"为什么不行"才有机会改正（这正是 Agent 循环里"观察"那一步的意义）。
    
        English:
    Permission violation / rule violation -- **not a program error**, it's the sandbox's normal
    refusal.
        The caller (tool set) must turn it into **a sentence for the model to read** and return it, rather than raising it:
        only when the model sees "why it's not allowed" does it get a chance to correct itself (this is exactly the point of the "observe" step in the Agent loop).
    """


# 路径里允许的前缀
# [EN] allowed prefixes in paths
PREFIX_SRC = 'src:'
PREFIX_OUT = 'out:'


@dataclass
class Scope:
    """一次打磨会话的**权限范围**。逐项都有默认值，给少了就是更严。
        English:
    The **permission scope** of a single polish session. Every item has a default; giving less means
    stricter.
    """

    #: 引用文件夹（作者的原始素材）：读 + **只追加**
    # [EN] : reference folder (the author's original material): read + **append-only**
    src_root: Path | None = None
    #: 打磨输出区（本轮所有新东西落这儿；调用方通常是临时目录，最终搬进项目）
    # [EN] : polish output area (everything new from this round lands here; the caller usually passes a
    # [EN] temp directory, and it is eventually moved into the project)
    out_root: Path | None = None
    #: 允不允许写引用文件夹（关掉则 `append_source` 直接拒绝）
    # [EN] : whether writing to the reference folder is allowed (if off, `append_source` rejects outright)
    allow_write_src: bool = True
    #: 单个文件写入上限（字节）—— 挡住"模型吐了 20MB"
    # [EN] : per-file write cap (bytes) -- blocks "the model dumped 20MB"
    max_write_bytes: int = 512 * 1024
    #: 子进程硬超时（秒）
    # [EN] : hard timeout for the child process (seconds)
    timeout: float = 20.0
    #: 工具返回值/子进程输出的字符上限
    # [EN] : character cap on tool return values / child process output
    max_output_chars: int = 6000
    #: 一次会话最多调多少次工具（防死循环烧钱）
    # [EN] : max tool calls per session (prevents infinite loops burning money)
    max_tool_calls: int = 60
    #: 引用文件夹里**永不动**的文件名（程序自己生成的，见 scanner.GENERATED_NAMES）
    # [EN] : filenames in the reference folder that are **never touched** (generated by the program itself,
    # [EN] see scanner.GENERATED_NAMES)
    never_touch: tuple[str, ...] = ()

    # ── 便捷属性 ──────────────────────────────────────────────
    # [EN] ── Convenience properties ──────────────────────────────────────────────
    @property
    def writable_roots(self) -> list[Path]:
        out: list[Path] = []
        if self.out_root is not None:
            out.append(Path(self.out_root).resolve())
        if self.allow_write_src and self.src_root is not None:
            out.append(Path(self.src_root).resolve())
        return out

    def describe(self) -> str:
        """给模型看的一句话（它会照着这个决定写哪儿）。
                English:
        A sentence for the model to read (it will decide where to write based on this).
        """
        bits = []
        if self.src_root is not None:
            bits.append(t('引用文件夹（前缀 {p}，只能追加）').format(p=PREFIX_SRC))
        if self.out_root is not None:
            bits.append(t('打磨输出区（前缀 {p}，可新建可覆盖）').format(p=PREFIX_OUT))
        return '；'.join(bits) or t('（没有可用的目录，只能改内存里的设定）')


# ══════════════════════════════════════════════════════════════════
#  路径解析（**唯一**入口：所有文件读写都要过这里）
# [EN] Path resolution (**the only** entry point: all file reads and writes must go through here)
# ══════════════════════════════════════════════════════════════════
def _root_of(scope: Scope, prefix: str) -> Path:
    if prefix == PREFIX_SRC:
        if scope.src_root is None:
            raise Denied(t('这次会话没有连接引用文件夹'))
        return Path(scope.src_root).resolve()
    if scope.out_root is None:
        raise Denied(t('这次会话没有可写的打磨输出区'))
    return Path(scope.out_root).resolve()


def _split_prefix(rel: str, *, for_write: bool) -> tuple[str, str]:
    """拆出 `src:` / `out:` 前缀。不带前缀时：**读默认源、写默认出**。
        English:
    Split out the `src:` / `out:` prefixes. When no prefix is present: **read defaults to source,
    write defaults to output**.
    """
    s = str(rel or '').strip()
    low = s.lower()
    for p in (PREFIX_SRC, PREFIX_OUT):
        if low.startswith(p):
            return p, s[len(p):].strip()
    return (PREFIX_OUT if for_write else PREFIX_SRC), s


def _looks_absolute(s: str) -> bool:
    return bool(s.startswith('/') or s.startswith('\\') or re.match(r'^[A-Za-z]:', s))


def resolve(scope: Scope, rel: str, *, for_write: bool = False,
            must_exist: bool = False) -> Path:
    """把工具给的**相对路径**解析成真实路径，顺带把越权挡在外面。

    **所有**文件操作都必须过这里 —— 不允许任何一处自己 `Path(rel)` 拼路径
    （那是"漏一个地方就破功"的写法）。
    
        English:
    Resolve the **relative path** given by a tool into a real path, and block permission violations
    along the way.
        **All** file operations must go through here -- no place is allowed to assemble a path itself with `Path(rel)`
        (that's the style where "miss one spot and the whole thing breaks").
    """
    prefix, rest = _split_prefix(rel, for_write=for_write)
    root = _root_of(scope, prefix)
    raw = rest.replace('\\', '/').strip()
    if not raw:
        # `out:` / `src:` 这样一个前缀就是"这个根自己"（`list_files('out:')` 要用）。
        # ⚠ 不报"路径为空" —— 那会让"列一下输出区有什么"变成一条看不懂的拒绝。
        # [EN] A prefix like `out:` / `src:` means "this root itself" (needed by `list_files('out:')`).
        # [EN] ⚠ Do not report "path is empty" -- that would turn "list what's in the output area" into an
        # [EN] incomprehensible rejection.
        return root
    if _looks_absolute(raw):
        raise Denied(t('只收相对路径（不要盘符、不要开头的斜杠）：{p}').format(p=rest))
    if any(part == '..' for part in raw.split('/')):
        raise Denied(t('路径里不许出现 ..（想往上跳一级是不允许的）：{p}').format(p=rest))

    target = root / raw
    # ★ **必须 resolve 之后再判**：`a/../../b` 光看字符串是合法的，
    #   而 `root/子目录` 如果是个符号链接，字符串检查也看不出来。
    # [EN] ★ **Must resolve before judging**: `a/../../b` looks legal by string inspection alone,
    # [EN] and if `root/subdir` is a symlink, string checks cannot tell either.
    try:
        real = target.resolve()
    except OSError as e:                                        # noqa: BLE001
        raise Denied(t('路径解析失败：{e}').format(e=e)) from e
    if not _inside(root, real):
        raise Denied(t('超出了一次打磨的许可范围：{p}').format(p=rest))

    if scope.never_touch and real.name in tuple(scope.never_touch):
        raise Denied(t('这是程序自己生成的资料，不在打磨范围内：{p}').format(p=real.name))

    if must_exist and not real.is_file():
        raise Denied(t('找不到这个文件：{p}').format(p=rest))
    if for_write and real.exists() and real.is_dir():
        raise Denied(t('那是一个目录，不能当文件写：{p}').format(p=rest))
    return real


def _inside(root: Path, p: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def relabel(scope: Scope, p: Path) -> str:
    """真实路径 → 给模型看带前缀的相对路径（列表/回执都用它）。
        English:
    Real path → a prefixed relative path for the model to read (used by listings/receipts).
    """
    p = Path(p).resolve()
    if scope.src_root is not None and _inside(Path(scope.src_root).resolve(), p):
        return PREFIX_SRC + p.relative_to(Path(scope.src_root).resolve()).as_posix()
    if scope.out_root is not None and _inside(Path(scope.out_root).resolve(), p):
        return PREFIX_OUT + p.relative_to(Path(scope.out_root).resolve()).as_posix()
    return str(p)


# ══════════════════════════════════════════════════════════════════
#  静态审查（AST）
# [EN] Static review (AST)
# ══════════════════════════════════════════════════════════════════
#: 生成代码**可以**导入的标准库（都无副作用、不碰网络与进程）
# [EN] : standard library modules that generated code **may** import (all side-effect free, no network
# [EN] or process access)
SAFE_IMPORTS: frozenset[str] = frozenset({
    'json', 're', 'textwrap', 'string', 'collections', 'itertools', 'functools',
    'math', 'statistics', 'decimal', 'fractions', 'random', 'datetime',
    'unicodedata', 'difflib', 'hashlib', 'typing', 'dataclasses', 'enum', 'copy',
})

#: 直接禁掉的**名字**（它们是"能打开潘多拉盒子"的那几个入口）
# [EN] : **names** that are banned outright (these are the entry points that "open Pandora's box")
BANNED_NAMES: frozenset[str] = frozenset({
    'open',            # 文件读写一律走沙盒给的 read_text / write_text
    # [EN] All file reads and writes must go through the sandbox-provided read_text / write_text
    'eval', 'exec', 'compile', '__import__',
    'globals', 'locals', 'vars', 'dir',
    'input', 'breakpoint', 'exit', 'quit', 'help', 'memoryview',
})

#: 禁掉的**属性**（无论从哪个对象上取）
# [EN] : banned **attributes** (no matter which object they are taken from)
BANNED_ATTRS: frozenset[str] = frozenset({
    # 进程 / 系统
    # [EN] Process / system
    'system', 'popen', 'spawn', 'spawnl', 'spawnv', 'fork', 'execv', 'execve',
    'kill', 'killpg', 'chmod', 'chown', 'umask', 'symlink', 'link', 'mkfifo',
    # 删除与改名（**这一组最要紧**：素材不可再生）
    # [EN] Delete and rename (**this group matters most**: material is non-renewable)
    'unlink', 'rmdir', 'rmtree', 'remove', 'removedirs', 'rename', 'replace',
    'move', 'truncate',
    # pathlib 的写入口（生成代码拿了 Path 对象就有手了）
    # [EN] pathlib write entry points (once generated code gets a Path object, it has hands)
    'write_text', 'write_bytes', 'open', 'touch', 'mkdir', 'makedirs',
    # 反射逃生口（本模块把这些都封了）
    # [EN] Reflection escape hatches (this module seals all of them)
    'import_module', 'reload', 'loads', 'load', 'dump', 'dumps',
})

#: 这些属性虽然在上面表里，但对**特定模块**是安全的（白名单开个口子）
# [EN] : these attributes, though in the table above, are safe for **specific modules** (whitelist
# [EN] pokes a hole)
_ATTR_ALLOW = {
    'json': {'loads', 'dumps', 'load', 'dump'},
}


def check_source(code: str, *, require_run: bool = False) -> list[str]:
    """静态审查一段将被执行的代码。返回**违规清单**（空 = 通过）。

    返回的是**给人/给模型看的句子**：模型拿着它才能改对（只说"不允许"等于没说）。
    
        English:
    Statically review a piece of code about to be executed. Return the **violation list** (empty =
    passed).
        It returns **sentences for a human/model to read**: only with them can the model fix things correctly (saying only "not allowed" is as good as saying nothing).
    """
    bad: list[str] = []
    try:
        tree = ast.parse(str(code or ''))
    except SyntaxError as e:
        return [t('语法错误：第 {n} 行附近 —— {msg}').format(
            n=(e.lineno or 0), msg=(e.msg or e))]

    called_mods: dict[str, str] = {}       # 局部名 → 模块名（`import json as j`）
    # [EN] local name → module name (`import json as j`)

    for node in ast.walk(tree):
        # ① 导入
        # [EN] ① imports
        if isinstance(node, ast.Import):
            for a in node.names:
                root = str(a.name or '').split('.')[0]
                called_mods[str(a.asname or root)] = root
                if root not in SAFE_IMPORTS:
                    bad.append(t('不许导入 {m}（可用的只有：{ok}）').format(
                        m=root, ok='、'.join(sorted(SAFE_IMPORTS))))
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or '').split('.')[0]
            called_mods[root] = root
            if root and root not in SAFE_IMPORTS:
                bad.append(t('不许从 {m} 里导入（可用的只有：{ok}）').format(
                    m=root, ok='、'.join(sorted(SAFE_IMPORTS))))

        # ② 禁名
        # [EN] ② banned names
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            bad.append(t('不许用 {n} —— 文件读写请用沙盒给的 read_text / '
                         'write_text / list_files，它们会替你检查路径').format(n=node.id))

        # ③ 属性
        # [EN] ③ attributes
        elif isinstance(node, ast.Attribute):
            attr = str(node.attr or '')
            if attr.startswith('__') and attr.endswith('__'):
                bad.append(t('不许取双下划线属性（{a}）—— 那是绕开沙盒的经典入口').format(a=attr))
                continue
            if attr in BANNED_ATTRS:
                # 对白名单模块放行（`json.loads` 是安全的，别的 `loads` 不是）
                # [EN] Allow through whitelisted modules (`json.loads` is safe, other `loads` are not)
                owner = ''
                if isinstance(node.value, ast.Name):
                    owner = called_mods.get(node.value.id, node.value.id)
                if attr not in _ATTR_ALLOW.get(owner, set()):
                    bad.append(t('不许调用 {a}（删除 / 改名 / 写盘 / 起进程 这类操作'
                                 '一律不开放；要写东西请用 write_text 写到打磨输出区）'
                                 ).format(a=attr))

    if require_run:
        names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef,))}
        if 'run' not in names:
            bad.append(t('这段代码里必须有一个顶层函数 run(args)（我要调它）'))
    return bad


# ══════════════════════════════════════════════════════════════════
#  受限内置环境（生成代码能看到的全部东西）
# [EN] Restricted builtins environment (everything generated code can see)
# ══════════════════════════════════════════════════════════════════
#: 给生成代码的 builtins 子集 —— **没有 open / eval / exec / __import__**
# [EN] : the subset of builtins given to generated code -- **no open / eval / exec / __import__**
SAFE_BUILTIN_NAMES: tuple[str, ...] = (
    'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
    'callable', 'chr', 'classmethod', 'complex', 'dict', 'divmod', 'enumerate',
    'filter', 'float', 'format', 'frozenset', 'getattr', 'hasattr', 'hash',
    'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list', 'map',
    'max', 'min', 'next', 'object', 'oct', 'ord', 'pow', 'print', 'property',
    'range', 'repr', 'reversed', 'round', 'set', 'setattr', 'slice', 'sorted',
    'staticmethod', 'str', 'sum', 'super', 'tuple', 'type', 'zip',
    # 异常类型（写 try 要用）
    # [EN] Exception types (needed for writing try)
    'Exception', 'ArithmeticError', 'AssertionError', 'AttributeError',
    'IndexError', 'KeyError', 'LookupError', 'NameError', 'NotImplementedError',
    'OSError', 'OverflowError', 'RuntimeError', 'StopIteration', 'TypeError',
    'UnicodeDecodeError', 'UnicodeError', 'ValueError', 'ZeroDivisionError',
    'True', 'False', 'None',
)


def build_builtins(*, import_guard: Any = None) -> dict[str, Any]:
    """搭一个受限制的 builtins 字典（生成代码的 `__builtins__`）。
        English:
    Build a restricted builtins dict (the `__builtins__` for generated code).
    """
    import builtins as _b

    out: dict[str, Any] = {}
    for n in SAFE_BUILTIN_NAMES:
        if hasattr(_b, n):
            out[n] = getattr(_b, n)
    if import_guard is not None:
        out['__import__'] = import_guard
    return out


def make_import_guard() -> Any:
    """只放行 `SAFE_IMPORTS` 的 `__import__`。
        English:
    Only allow the `__import__` from `SAFE_IMPORTS`.
    """
    import builtins as _b
    real = _b.__import__

    def _guard(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        root = str(name or '').split('.')[0]
        if root not in SAFE_IMPORTS:
            raise ImportError(t('沙盒不允许导入 {m}（可用的只有：{ok}）').format(
                m=root, ok='、'.join(sorted(SAFE_IMPORTS))))
        return real(name, globals, locals, fromlist, level)

    return _guard


# ══════════════════════════════════════════════════════════════════
#  在**主进程**里跑内置工具要用的读写（走 resolve）
# [EN] Read/write needed to run built-in tools in the **main process** (goes through resolve)
# ══════════════════════════════════════════════════════════════════
def read_text(scope: Scope, rel: str, *, encoding: str = 'utf-8') -> str:
    p = resolve(scope, rel, must_exist=True)
    raw = p.read_bytes()
    for enc in (encoding, 'utf-8-sig', 'gbk', 'utf-16'):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='replace')


def write_text(scope: Scope, rel: str, text: str) -> Path:
    """往**打磨输出区**写一个文件。**只走 `out:`**。

    ★ 指向 `src:` 时**明确拒绝**，不偷偷改写成输出区的一个同名文件 ——
      "以为写了、其实写到别处去了"是本项目最忌的那种失败（用户会以为
      素材已经被改好，而它其实躺在另一个目录里）。
      想动引用文件夹只有一条路：内置工具 `append_source`（**只追加 + 自动备份**）。
    
        English:
    Write a file to the **polish output area**. **Only via `out:`**.
        ★ When pointed at `src:` **explicitly refuse**, don't secretly rewrite it to a same-named file in the output area --
          "thinking it wrote, but actually wrote somewhere else" is the kind of failure this project most abhors (the user would think
          the material has been modified, while it actually sits in another directory).
          There is only one way to touch the reference folder: the built-in tool `append_source` (**append-only + automatic backup**).
    """
    prefix, rest = _split_prefix(rel, for_write=True)
    if prefix == PREFIX_SRC:
        raise Denied(t('写文件只能写打磨输出区（前缀 {o}）—— 想改引用文件夹请用 '
                       'append_source 工具（只追加、自动留备份）').format(o=PREFIX_OUT))
    body = str(text or '')
    data = body.encode('utf-8')
    if len(data) > scope.max_write_bytes:
        raise Denied(t('这份内容 {n} 字节，超过单文件上限 {m} 字节').format(
            n=len(data), m=scope.max_write_bytes))
    p = resolve(scope, PREFIX_OUT + str(rest or ''), for_write=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    # ⚠ **按原样写字节**，不用 `write_text`（Windows 上会把 `\n` 翻成 `\r\n`，
    #   本项目为这件事吃过一次亏，见 `ingest/repair.py` 的长注释）。
    # [EN] ⚠ **Write bytes as-is**, do not use `write_text` (on Windows it turns `\n` into `\r\n`,
    # [EN] this project has been burned by this before, see the long comment in `ingest/repair.py`).
    p.write_bytes(data)
    return p


def append_text(scope: Scope, rel: str, text: str, *,
                backup_suffix: str = '.bak') -> tuple[Path, bool]:
    """**追加**到引用文件夹里的一个文件（只追加，绝不覆盖）。

    返回 `(路径, 是否是新建的)`。已存在就先留一份 `<名><suffix>`（**已存在不覆盖**：
    留的是"第一次让 AI 改之前"的样子，那个版本最有用）。
    
        English:
    **Append** to a file in the reference folder (append-only, never overwrite).
        Return `(path, whether it's newly created)`. If it already exists, first keep a copy `<name><suffix>` (**existing is not overwritten**:
        what's kept is the "before the AI first modified it" version, that version is the most useful).
    """
    p = resolve(scope, rel, for_write=True)
    body = str(text or '').encode('utf-8')
    if len(body) > scope.max_write_bytes:
        raise Denied(t('要追加的内容 {n} 字节，超过单文件上限 {m} 字节').format(
            n=len(body), m=scope.max_write_bytes))
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    if not fresh:
        bak = p.with_name(p.name + backup_suffix)
        if not bak.exists():
            # 原样搬字节（保住行尾与编码）
            # [EN] Copy bytes as-is (preserve line endings and encoding)
            bak.write_bytes(p.read_bytes())
        # ★ 追加走字节：**原文一个字节都不动**（LF 的文件不许被整篇换成 CRLF）
        # [EN] ★ Append as bytes: **not a single byte of the original is touched** (a LF file must not be
        # [EN] swapped wholesale to CRLF)
        old = p.read_bytes()
        sep = b'' if (not old or old.endswith(b'\n')) else b'\n'
        p.write_bytes(old + sep + body)
    else:
        p.write_bytes(body)
    return p, fresh


def list_files(scope: Scope, rel: str = '', *, limit: int = 200) -> list[str]:
    """列出一个目录下的文件（带前缀的相对路径）。
        English:
    List the files under a directory (prefixed relative paths).
    """
    prefix, rest = _split_prefix(rel, for_write=False)
    root = _root_of(scope, prefix)
    base = resolve(scope, (prefix + rest) if rest else prefix, for_write=False)
    if not base.is_dir():
        base = base.parent
    out: list[str] = []
    for p in sorted(base.rglob('*')):
        if len(out) >= limit:
            break
        if p.is_file() and not any(x.startswith('.') for x in p.parts):
            out.append(relabel(scope, p))
    return out


# ══════════════════════════════════════════════════════════════════
#  在**子进程**里跑生成代码
# [EN] Run generated code in the **child process**
# ══════════════════════════════════════════════════════════════════
@dataclass
class RunOutcome:
    """子进程跑一次的结果。`ok=False` 时 `why` 一定是一句人话。
        English:
    The result of one subprocess run. When `ok=False`, `why` is always a plain-language sentence.
    """

    ok: bool
    text: str = ''
    why: str = ''
    seconds: float = 0.0
    logs: list[str] = field(default_factory=list)

    def as_observation(self) -> str:
        """变成给模型看的那段"观察结果"。
                English:
        Become the "observation result" passage shown to the model.
        """
        if not self.ok:
            return t('（没能跑成）{why}').format(why=self.why)
        body = self.text.strip() or t('（跑完了，没有输出）')
        if self.logs:
            body += '\n' + t('（过程中打印：{x}）').format(x=' / '.join(self.logs[:10]))
        return body


def run_code(scope: Scope, code: str, *, args: dict[str, Any] | None = None,
             name: str = 'inline', require_run: bool = True) -> RunOutcome:
    """把一段生成代码丢到**子进程**里跑一次。

    为什么非得起子进程（不是"优雅一点"，是只有它能做到两件事）：

    1. **超时能真的杀掉** —— 同进程里跑 `while True: pass`，Python 的线程杀不掉，
       只能眼看着界面卡死；
    2. **崩了不连累主进程** —— 生成代码里一个 `sys.setrecursionlimit` 或段错误，
       主进程跟着一起没；子进程崩了只丢这一次调用。

    静态审查**在父进程和子进程各做一遍**（纵深防御：父进程那次是为了"不合格的
    代码根本不落盘"，子进程那次是为了"就算有人绕过落盘检查，执行前还要再拦一道"）。
    
        English:
    Throw a piece of generated code into a **subprocess** and run it once.
        Why a subprocess is mandatory (not "a bit more elegant", but that only it can do two things):
        1. **Timeouts can actually kill it** -- running `while True: pass` in the same process, Python threads can't be killed,
           you can only watch the UI freeze;
        2. **A crash doesn't take down the main process** -- a `sys.setrecursionlimit` or segfault in generated code,
           the main process goes down with it; a subprocess crash only loses this one call.
        Static review is done **in both the parent process and the subprocess** (defense in depth: the parent pass is so that "unqualified
        code never even lands on disk", the subprocess pass is so that "even if someone bypasses the disk-landing check, there's still a gate before execution").
    """
    import time as _time

    bad = check_source(code, require_run=require_run)
    if bad:
        return RunOutcome(ok=False, why='；'.join(bad[:6]))

    t0 = _time.monotonic()
    with tempfile.TemporaryDirectory(prefix='nws_polish_') as tmp:
        tmpd = Path(tmp)
        spec = {
            'code': str(code),
            'args': dict(args or {}),
            'name': str(name or 'inline'),
            'app_dir': str(APP_DIR),
            'roots': {
                'src': str(scope.src_root) if scope.src_root else '',
                'out': str(scope.out_root) if scope.out_root else '',
            },
            'allow_write_src': False,          # 生成代码**永远**不许写引用文件夹
            # [EN] Generated code is **never** allowed to write to the reference folder
            'max_write_bytes': int(scope.max_write_bytes),
            'max_output_chars': int(scope.max_output_chars),
            'require_run': bool(require_run),
        }
        spec_f = tmpd / 'spec.json'
        spec_f.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
        try:
            proc = subprocess.run(
                [sys.executable, '-B', str(RUNNER), str(spec_f)],
                cwd=str(tmpd), capture_output=True, timeout=max(1.0, scope.timeout),
                env=_child_env())
        except subprocess.TimeoutExpired:
            return RunOutcome(ok=False, seconds=_time.monotonic() - t0,
                              why=t('跑了 {n} 秒还没停，已被强制中断（大概率是死循环）'
                                    ).format(n=int(max(1.0, scope.timeout))))
        except OSError as e:                                     # noqa: BLE001
            return RunOutcome(ok=False, seconds=_time.monotonic() - t0,
                              why=t('起不了子进程：{e}').format(e=e))

    dt = _time.monotonic() - t0
    raw = (proc.stdout or b'').decode('utf-8', errors='replace').strip()
    err = (proc.stderr or b'').decode('utf-8', errors='replace').strip()
    payload: dict[str, Any] | None = None
    for ln in reversed(raw.splitlines()):
        ln = ln.strip()
        if ln.startswith('{') and ln.endswith('}'):
            try:
                payload = json.loads(ln)
                break
            except ValueError:
                continue
    if payload is None:
        why = t('子进程没有回话（退出码 {c}）').format(c=proc.returncode)
        if err:
            why += '：' + err.splitlines()[-1][:200]
        return RunOutcome(ok=False, seconds=dt, why=why)
    if payload.get('ok'):
        return RunOutcome(ok=True, seconds=dt, text=str(payload.get('text') or ''),
                          logs=[str(x) for x in (payload.get('logs') or [])])
    return RunOutcome(ok=False, seconds=dt, why=str(payload.get('why') or t('未知原因')))


def _child_env() -> dict[str, str]:
    """子进程的环境：**只留最少几个变量**（别把用户的 API Key 递进去）。
        English:
    The subprocess environment: **keep only the bare minimum of variables** (don't pass the user's
    API Key in).
    """
    env: dict[str, str] = {'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    for k in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'WINDIR'):
        if k in os.environ:
            env[k] = os.environ[k]
    return env
