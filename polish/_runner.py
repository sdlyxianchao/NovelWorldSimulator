# -*- coding: utf-8 -*-
"""**子进程侧**的执行器：跑 Agent 现场生成的代码。

被 `polish.sandbox.run_code()` 用 `subprocess` 拉起来，**不是包的一部分**
（所以文件名带下划线，也不从 `__init__` 导出）。

## 契约

    python -B polish/_runner.py <spec.json>

`spec.json`：

```json
{"code": "...", "args": {...}, "name": "工具名", "app_dir": "…",
 "roots": {"src": "…", "out": "…"}, "allow_write_src": false,
 "max_write_bytes": 524288, "max_output_chars": 6000, "require_run": true}
```

最后一行 stdout 输出：

```json
{"ok": true,  "text": "给模型看的返回值", "logs": ["…"]}
{"ok": false, "why": "一句人话原因"}
```

## 三条必须守住的

1. **stdout 只能是最后那一行 JSON** —— 生成代码里的 `print` 一律被收进 `logs`，
   否则父进程解析不到结果（本项目为"stdout 被污染"吃过亏，见 MCP 那节）。
2. **静态审查在这里**再**做一遍**（父进程那次是为了"不合格的代码根本不落盘"）。
3. **写权限只有 `out:`** —— 生成代码永远不许碰引用文件夹。

English:
**Subprocess-side** executor: runs code generated on the fly by the Agent.
Launched via `subprocess` by `polish.sandbox.run_code()`, **not part of the package**
(hence the underscore in the filename, and it is not exported from `__init__`).
## Contract
    python -B polish/_runner.py <spec.json>
`spec.json`:
```json
{"code": "...", "args": {...}, "name": "tool name", "app_dir": "…",
 "roots": {"src": "…", "out": "…"}, "allow_write_src": false,
 "max_write_bytes": 524288, "max_output_chars": 6000, "require_run": true}
```
The last line of stdout outputs:
```json
{"ok": true,  "text": "return value shown to the model", "logs": ["…"]}
{"ok": false, "why": "a one-sentence human-readable reason"}
```
## Three things that must be upheld
1. **stdout may only be that last line of JSON** -- any `print` in generated code is captured
into `logs`,
otherwise the parent process cannot parse the result (this project has been burned by "stdout polluted", see the MCP section).
   2. **Static review is done once more** here (the parent process's pass is to ensure "non-conforming code never hits disk").
3. **Write permission is only `out:`** -- generated code may never touch the reference folder.
Load `polish/sandbox.py` by **file path**.
"""
from __future__ import annotations

import ast
import io
import json
import sys
import traceback
from pathlib import Path

#: 生成代码里能用的模块级名字（**唯一**的清单 —— 改这里就够了）
# [EN] : module-level names usable in generated code (the **only** list -- edit here and nowhere else)
HELPER_NAMES = ('read_text', 'write_text', 'list_files', 'read_json', 'write_json',
                'log', 'exists', 'args')


def _load_sandbox(app_dir: str):
    """按**文件路径**加载 `polish/sandbox.py`。

    ⚠ 不能写 `from polish.sandbox import …` —— 那会先执行 `polish/__init__.py`，
      把 `agent` / `tools` / `llm` 整条链拖进子进程（慢，而且多一份出错的机会）。
      子进程只需要"沙盒本身"，那就只加载沙盒这一份文件。
    
        English:
    ⚠ Do not write `from polish.sandbox import …` -- that would first execute `polish/__init__.py`,
        dragging the whole chain `agent` / `tools` / `llm` into the subprocess (slow, and one more chance to fail).
          The subprocess only needs "the sandbox itself", so just load this one sandbox file.
    """
    import importlib.util

    path = Path(app_dir) / 'polish' / 'sandbox.py'
    spec = importlib.util.spec_from_file_location('nws_polish_sandbox', path)
    if spec is None or spec.loader is None:                     # pragma: no cover
        raise RuntimeError(f'加载沙盒失败：{path}')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['nws_polish_sandbox'] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({'ok': False, 'why': '缺少 spec 文件参数'}, ensure_ascii=False))
        return 2
    spec = json.loads(Path(argv[1]).read_text(encoding='utf-8'))
    out = io.StringIO()

    # ── 直接用一个裸 dict 当 Scope（子进程不需要完整 dataclass）──
    # [EN] -- use a bare dict as the Scope (the subprocess doesn't need the full dataclass) --
    class _S:                                                  # noqa: N801
        src_root = Path(spec['roots']['src']) if spec['roots'].get('src') else None
        out_root = Path(spec['roots']['out']) if spec['roots'].get('out') else None
        allow_write_src = False
        max_write_bytes = int(spec.get('max_write_bytes') or 512 * 1024)
        max_output_chars = int(spec.get('max_output_chars') or 6000)
        timeout = 0.0
        max_tool_calls = 0
        never_touch: tuple = ()
        # 生成代码只能写 out:，所以把 src 从"可写根"里摘掉
        # [EN] Generated code can only write out:, so remove src from the "writable roots"
        writable_roots: list = []

        def describe(self) -> str:
            return ''

    app_dir = str(spec.get('app_dir') or '.')
    # ⚠ **必须先把 app_dir 放进 sys.path**：沙盒自己要 `from i18n import t`，
    #   而子进程的 cwd 是一个临时目录（刻意的），不插这一下就 ModuleNotFoundError。
    #   （不靠环境变量 `PYTHONPATH`：那等于把"能不能跑"寄托在父进程的环境上。）
    # [EN] ⚠ **app_dir must be put into sys.path first**: the sandbox itself does `from i18n import t`,
    # [EN] and the subprocess's cwd is a temp directory (deliberately), so without this insertion you get
    # [EN] ModuleNotFoundError.
    # [EN] (Not relying on the env var `PYTHONPATH`: that would stake "whether it can run" on the parent
    # [EN] process's environment.)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    try:
        sb = _load_sandbox(app_dir)
    except Exception as e:                                       # noqa: BLE001
        print(json.dumps({'ok': False, 'why': f'沙盒装载失败：{e!r}'},
                         ensure_ascii=False))
        return 2

    scope = _S()

    # ── 静态审查（第二遍）──
    # [EN] -- static review (second pass) --
    bad = sb.check_source(spec.get('code') or '',
                          require_run=bool(spec.get('require_run', True)))
    if bad:
        print(json.dumps({'ok': False, 'why': '；'.join(bad[:6])}, ensure_ascii=False))
        return 0

    logs: list[str] = []

    def log(msg) -> None:
        logs.append(str(msg)[:400])

    # ⚠ 生成代码能用的文件读写**只有这一套**：全部走 `sb.resolve`。
    #   它们是"相对路径 API"——生成代码**拿不到真实路径**，也就没有逃逸的抓手。
    # [EN] ⚠ The **only** file read/write available to generated code is this one set: everything goes
    # [EN] through `sb.resolve`.
    # [EN] They are "relative path APIs" -- generated code **cannot obtain real paths**, so there is no
    # [EN] handle for escaping.
    def read_text(rel: str) -> str:
        return sb.read_text(scope, str(rel))

    def write_text(rel: str, text) -> str:
        p = sb.write_text(scope, str(rel), str(text or ''))
        return sb.relabel(scope, p)

    def list_files(rel: str = '') -> list:
        return sb.list_files(scope, str(rel or ''))

    def read_json(rel: str):
        return json.loads(read_text(rel) or 'null')

    def write_json(rel: str, obj) -> str:
        return write_text(rel, json.dumps(obj, ensure_ascii=False, indent=2))

    def exists(rel: str) -> bool:
        try:
            sb.resolve(scope, str(rel), must_exist=True)
            return True
        except Exception:                                        # noqa: BLE001
            return False

    g: dict = {
        '__name__': 'nws_polish_tool',
        '__builtins__': sb.build_builtins(import_guard=sb.make_import_guard()),
        'read_text': read_text, 'write_text': write_text,
        'list_files': list_files, 'read_json': read_json,
        'write_json': write_json, 'log': log, 'exists': exists,
        'args': dict(spec.get('args') or {}),
        # 沙盒自己那几个名字也给它（生成代码有时候要 `Denied` 来做判断）
        # [EN] Also give it the sandbox's own names (generated code sometimes needs `Denied` for checks)
        'Denied': sb.Denied,
        'json': json,
    }

    real_stdout = sys.stdout
    try:
        sys.stdout = out                                   # 生成代码的 print 全收走
        # [EN] Capture all print output from generated code
        try:
            exec(compile(spec.get('code') or '', '<打磨工具>', 'exec'), g)
            fn = g.get('run')
            if not callable(fn):
                raise RuntimeError('代码里没有可调用的 run(args)')
            result = fn(dict(g.get('args') or {}))
            text = '' if result is None else str(result)
        finally:
            sys.stdout = real_stdout
        for chunk in str(out.getvalue() or '').splitlines():
            if chunk.strip():
                logs.append(chunk.strip()[:400])
    except Exception as e:                                       # noqa: BLE001
        sys.stdout = real_stdout
        tb = traceback.format_exc().splitlines()
        # 只留"最贴近用户代码"的那一行（别的都是执行器的栈，对模型没帮助）
        # [EN] Keep only the line "closest to the user's code" (the rest is executor stack, no help to the
        # [EN] model)
        loc = next((ln.strip() for ln in reversed(tb)
                    if '打磨工具' in ln or 'line ' in ln), '')
        why = f'{type(e).__name__}: {e}'
        if loc:
            why += f'（{loc[:160]}）'
        print(json.dumps({'ok': False, 'why': why, 'logs': logs[-10:]},
                         ensure_ascii=False))
        return 0

    cap = int(spec.get('max_output_chars') or 6000)
    if len(text) > cap:
        text = text[:cap] + f'\n…（输出超过 {cap} 字，已截断）'
    print(json.dumps({'ok': True, 'text': text, 'logs': logs[-20:]},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv))
    except Exception:                                            # noqa: BLE001
        print(json.dumps({'ok': False, 'why': '执行器自己崩了：'
                          + traceback.format_exc().splitlines()[-1][:200]},
                         ensure_ascii=False))
        sys.exit(0)
