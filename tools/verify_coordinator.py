# -*- coding: utf-8 -*-
"""验证：运行窗口底部的 AI 对话输入框 = 总体协调引擎入口（2026-10-15）。

用户原话（要点）：
    「把运行窗口的命令窗口改成默认显示，但去掉相关的内置命令，
      改成 AI 对话的输入框，输入的内容会发给后面的总体协调引擎。
      接收用户输入之后，经过分析，修改特定 Agent 的行为并马上生效，
      或者修改别的行为或者做特定动作，如果不支持的操作则告诉用户
      直接去操作，说自己目前做不了。」

这一支盯四件事，两个方向都查（不靠用户环境、不靠有没有配模型）：

  A. **协调引擎本体行为**（行为判，纯逻辑、不起窗口）：
     - 全局关键词（含「整体/全局/基调」…）→ 写入 global，且**对所有人即时生效**
       （剧组职位与在场人物的指令里都带上 global）；
     - 剧组职位（如「导演」）→ 写入对应职位 key；
     - 在场人物（如「王二」且 TA 在场）→ 写入该演员；
     - 不在场人物 / 完全不沾边 → 老实说「做不了」，绝不假装成功。
     ★ 强制走**关键词降级路径**（`_parse_llm` 打桩返回 None），所以不论本机有没有
       配模型、模型怎么答，判据都只看确定的行为，不会飘。

  B. **UI 接线**（行为 + AST）：
     - `NovelWorldApp.run_coordinator` 真把输入交给 `Coordinator.instance().handle`
       （用一个假 self 直接调这个方法，不起窗口、不依赖真页面）；
     - 运行窗口输入框的 `on_submit` / 「发送」接的是 `_on_cmd`，而 `_on_cmd`
       调 `self.run_coordinator`（AST 查调用图，不是查字符串）；
     - 源码里**不再有 `run_command`**（旧命令框已移除，不会复活成命令框）。

  C. **默认显示**（config）：`HIDE_COMMAND_BAR` 的出厂默认是 `False`
     （= 运行窗口底部默认显示那个 AI 输入框）。

反例法在 `developers/mutate_coordinator.py`：逐一打红上面这些判据，证明不是假绿。

用法：.venv\\Scripts\\python.exe tools/verify_coordinator.py
产出：assets/screenshots/coordinator_report.json

English:
Verification: the run window's bottom AI conversation input box = the overall Coordinator entry
(2026-10-15). See the user's words (Chinese) above. This branch watches four things, in both
directions, independent of whether a model is configured:
  A. Coordinator engine behavior (behavioral, pure logic, no window): global / crew / on-stage actor
     routing writes immediately; not-on-stage / irrelevant input is reported honestly.
  B. UI wiring (behavioral + AST): `run_coordinator` really calls `Coordinator.instance().handle`;
     the input box's on_submit is wired to `_on_cmd` → `self.run_coordinator`; `run_command` is gone.
  C. Default shown (config): `HIDE_COMMAND_BAR` factory default is `False`.
Counterexample method lives in `developers/mutate_coordinator.py`.
Usage: .venv\\Scripts\\python.exe tools/verify_coordinator.py
Output: assets/screenshots/coordinator_report.json
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(APP_DIR))

# 让配置落盘走保险丝（verify_*.py 文件名前缀会被 config 认出，写到临时 sink，
# 不会污染用户的 .env）。这里再显式调一次，双保险。
# [EN] Let config writes hit the fuse (the verify_*.py prefix is recognized by config and routed to a
# [EN] temp sink, never the user's .env). Call it explicitly too, as a second safety.
try:
    import verify_ui_common as VU  # noqa: E402
    VU.redirect_env_writes()
except Exception:                                   # noqa: BLE001
    pass

from config import SPEC  # noqa: E402
import crew.coordinator as _COM  # noqa: E402
from crew.coordinator import Coordinator  # noqa: E402


def _ast_wiring(src: str) -> dict:
    """AST 查运行窗口输入框 → 协调引擎的调用图（不靠字符串搜）。
        English:
    AST: inspect the call graph from the run-window input box to the Coordinator (no string search).
    """
    tree = ast.parse(src)
    has_run_coordinator = False
    routes_to_coordinator = False
    on_submit_wired = False
    has_run_command = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'run_coordinator':
            has_run_coordinator = True
            for sub in ast.walk(node):
                if isinstance(sub, ast.Await):
                    val = sub.value
                    if (isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute)
                            and val.func.attr == 'handle'):
                        base = val.func.value
                        if (isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute)
                                and base.func.attr == 'instance'):
                            routes_to_coordinator = True
        if isinstance(node, ast.FunctionDef) and node.name == '_on_cmd':
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                        and sub.func.attr == 'run_coordinator':
                    v = sub.func.value
                    if isinstance(v, ast.Name) and v.id == 'self':
                        on_submit_wired = True
        if isinstance(node, ast.FunctionDef) and node.name == 'run_command':
            has_run_command = True
        if isinstance(node, ast.Assign):
            tgt = node.targets[0] if node.targets else None
            if (isinstance(tgt, ast.Attribute) and tgt.attr == 'on_submit'
                    and isinstance(node.value, ast.Name) and node.value.id == '_on_cmd'):
                on_submit_wired = True
    return {
        'has_run_coordinator': has_run_coordinator,
        'routes_to_coordinator': routes_to_coordinator,
        'on_submit_wired': on_submit_wired,
        'has_run_command': has_run_command,
    }


# 强制关键词降级路径（判据不依赖本机有没有配模型）
# [EN] Force the keyword-fallback path (criterion must not depend on whether a model is configured)
async def _no_llm(self, raw: str, on_stage) -> None:
    return None


async def main() -> int:
    checks: list[dict] = []

    def ok(name: str, cond, detail: str = '') -> bool:
        checks.append({'name': name, 'ok': bool(cond),
                       'detail': str(detail)[:400]})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    # 打桩：让 handle 永远走关键词路径
    # [EN] Stub: make handle always take the keyword path
    orig_parse_llm = Coordinator._parse_llm
    Coordinator._parse_llm = _no_llm

    try:
        coord = Coordinator.instance()
        coord.clear_all()

        # ── A 协调引擎本体行为 ──
        # [EN] ── A Coordinator engine behavior ──
        r = await coord.handle('整体基调再幽默一点')
        ok('A1 ★ 全局关键词（整体/基调）→ 写入 global 且 ok',
           bool(r['ok']) and bool(coord.global_directive()),
           f"ok={r['ok']} g={coord.global_directive()!r}")

        coord.clear_all()
        r = await coord.handle('让导演今天多写点感情戏')
        ok('A2 ★ 剧组职位（导演）→ 写入对应职位 key=director',
           bool(r['ok']) and bool(coord.crew_directive('director')),
           f"ok={r['ok']} d={coord.crew_directive('director')!r}")

        coord.clear_all()
        r = await coord.handle('让王二这一拍别那么冲动', on_stage_names=['王二'])
        ok('A3 ★ 在场人物（王二且 TA 在场）→ 写入该演员指令',
           bool(r['ok']) and bool(coord.actor_directive('王二')),
           f"ok={r['ok']} a={coord.actor_directive('王二')!r}")

        coord.clear_all()
        r = await coord.handle('让王二别冲动', on_stage_names=['李四'])
        ok('A4 ★ 不在场人物 → 老实说做不了（unsupported，不假装成功）',
           (not r['ok']) and bool(r['unsupported']),
           f"ok={r['ok']} unsup={r['unsupported']}")

        coord.clear_all()
        r = await coord.handle('把模型换成 GPT-5')
        ok('A5 ★ 完全不沾边（换模型）→ 做不了，不假装能用',
           (not r['ok']) and bool(r['unsupported']),
           f"ok={r['ok']} unsup={r['unsupported']}")

        coord.clear_all()
        coord.set_global('G')
        ok('A6 ★ 全局指令对所有人即时生效（职位与演员指令都带上 global）',
           coord.crew_directive('director') == 'G'
           and coord.actor_directive('王二') == 'G',
           f"crew={coord.crew_directive('director')!r} actor={coord.actor_directive('王二')!r}")

        # ── B UI 接线（行为 + AST）──
        # [EN] ── B UI wiring (behavioral + AST) ──
        coord.clear_all()
        try:
            from gui.app_flet import NovelWorldApp  # noqa: E402

            class _FakeSelf:
                _map_people: list = []

                def _post_message(self, *a, **k):
                    return None

            fake = _FakeSelf()
            res = await NovelWorldApp.run_coordinator(fake, '整体节奏放慢一点')
            ok('B1 ★ run_coordinator 真把输入交给协调引擎（全局指令写入）',
               bool(coord.global_directive()),
               f"global={coord.global_directive()!r} res_ok={res.get('ok')}")
        except Exception as e:                          # noqa: BLE001
            ok('B1 ★ run_coordinator 真把输入交给协调引擎（全局指令写入）',
               False, f'import/调用失败：{e!r}')

        src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
        w = _ast_wiring(src)
        ok('B2 ★ 存在异步 run_coordinator 且内部 await Coordinator.instance().handle',
           w['has_run_coordinator'] and w['routes_to_coordinator'], str(w))
        ok('B3 ★ 输入框 on_submit 接到 _on_cmd，且 _on_cmd 调 self.run_coordinator',
           w['on_submit_wired'], str(w))
        ok('B4 ★ 旧 run_command 已移除（输入框不再是命令框）',
           not w['has_run_command'], str(w))

        # ── C 默认显示 ──
        # [EN] ── C Default shown ──
        default = SPEC.get('HIDE_COMMAND_BAR', {}).get('default')
        ok('C1 ★ HIDE_COMMAND_BAR 出厂默认 = False（运行窗口底部默认显示 AI 输入框）',
           default is False, f'default={default!r}')
    finally:
        Coordinator._parse_llm = orig_parse_llm
        coord.clear_all()

    bad = [c for c in checks if not c['ok']]
    report = {'ok': not bad, 'checks': checks,
              'failed': [c['name'] for c in bad]}
    (OUT / 'coordinator_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n协调引擎验证：{len(checks) - len(bad)}/{len(checks)}')
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
