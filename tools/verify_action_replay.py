# -*- coding: utf-8 -*-
"""验证：**同一个人不会连着几拍重演同一段动作**（2026-10-17）。

用户要求「用某楼以及 samples 里的示例项目全部走一遍推演，看各环节是否还存在
质量问题」。真跑了两个项目、并量了 6 份历史存档，最刺眼的一条是：

    同一个角色连着几拍把同一段动作演一遍，只换几个字。

| 材料 | 同角色相邻动作对 | 相似度 >60% |
|---|---|---|
| 悬疑《更漏子》（本次真跑） | 2 对 | **2 对**（87% / 83%） |
| 《某楼》（本次真跑） | 1 对 | **1 对**（65%） |
| 存档 10-16-11（208 个动作） | 196 对 | 5 对（82% / 79%） |

原文（悬疑那两拍）：
    · 动作 主角：自院里青石井拎木桶推门进屋，走到北墙条案前。将桶水倒入铜壶。
                  手指沿铜标尺刻线划过，水面靠着刻线——比该到的刻度高了一截。
    · 动作 主角：拎木桶推门进屋，走到北墙条案前。将桶水倒入铜壶。
                  手指沿铜标尺刻线划过，水面靠着刻线，比昨夜该到的刻度高了一截。

根因不是模型懒：`[刚才]` 只给 6 条（`DIALOGUE_CONTEXT_LINES`），
一拍里七个人各说一句就把他自己的动作挤出窗口，于是下一拍他手上只剩
"我的目标"，只好把刚做过的事再做一遍。

修法两处：
  · `world/state.last_own_action()` —— 单独捞出"这个人最近一条动作"；
  · `agent/core.decide()` —— 在 `[刚才]` 之后加一段 `[你上一拍做的]`，明写别重演。

判据分组：纯逻辑（造 `recent_lines`、AST 查语句），秒级 ⇒ LOGIC 组。
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

REPORT = APP_DIR / 'assets' / 'screenshots' / 'action_replay_report.json'
report: dict = {'checks': [], 'ok': False}


def ok(name: str, cond: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(f'{"✓" if cond else "✗"} {name}' + (f'  [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _rows() -> list[dict]:
    """一段贴近真机的 `recent_lines`：别人的话、自己的动作（带「别处」后缀）、
    自己的心声、又一句别人的话 —— 顺序与真实主循环一致（最新的在最后）。"""
    return [
        {'who': '丙', 'text': '这楼早先从某地走。', 'kind': 'speak',
         'to': '', 'place': '某楼'},
        {'who': '乙（别处）', 'text': '拎木桶推门进屋，倒水进铜壶，手指划过铜标尺。',
         'kind': 'act', 'to': '', 'place': '某楼'},
        {'who': '甲', 'text': '擦桌。', 'kind': 'speak', 'to': '乙', 'place': '某楼'},
        {'who': '乙', 'text': '我是谁。怎么躺在这。', 'kind': 'aside',
         'to': '', 'place': '某楼'},
    ]


def group_a() -> None:
    from world.state import WorldState

    ok('A1 ★ `WorldState.last_own_action` 存在（防重演的取数口子只有这一处）',
       callable(getattr(WorldState, 'last_own_action', None)), '')

    w = WorldState()
    w.scene = '某楼'
    w.recent_lines = _rows()
    got = w.last_own_action('乙')
    ok('A2 ★★★ 取到的是**动作**（不是后面那条 `aside` 心声、也不是别人的话）',
       got.startswith('拎木桶推门进屋'), got[:50])
    ok('A3 ★★★ 名字带后缀也认得出（`乙（别处）` 是他本人在别处做的，'
       '不认就会「在别处做的事查不到 ⇒ 照样重演」）',
       '铜标尺' in got, got[:50])

    w2 = WorldState()
    w2.scene = '某楼'
    w2.recent_lines = [r for r in _rows() if r['kind'] != 'act']
    ok('A4 ★★ 成对：**只有台词和心声时返回空串**'
       '（不能把"我刚想过什么"当成"我刚做过什么"喂回去）',
       w2.last_own_action('乙') == '', repr(w2.last_own_action('乙')))

    w3 = WorldState()
    w3.scene = '某楼'
    w3.recent_lines = _rows()
    ok('A5 ★ 成对：问一个不在场的人 ⇒ 空串（不是拿别人的动作充数）',
       w3.last_own_action('路人甲') == '', repr(w3.last_own_action('路人甲')))

    # A6：真的取"最近"那条（造两条自己的动作，后来的覆盖前面的）
    w4 = WorldState()
    w4.scene = '某楼'
    w4.recent_lines = [
        {'who': '乙', 'text': '第一拍：拎桶进屋', 'kind': 'act', 'to': '', 'place': '某楼'},
        {'who': '乙', 'text': '第二拍：蹲下擦桌', 'kind': 'act', 'to': '', 'place': '某楼'},
    ]
    ok('A6 ★★ 取的是**最近**那条动作（不是最早那条 —— 否则提醒的是半小时前的事）',
       w4.last_own_action('乙') == '第二拍：蹲下擦桌',
       repr(w4.last_own_action('乙')))


def group_b() -> None:
    src = (APP_DIR / 'agent' / 'core.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    decide = next((n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == 'decide'), None)
    ok('B1 ★ `decide` 在 AST 里找得到', decide is not None, '')
    if decide is None:
        return

    # ★ 认的是**语句**（`AugAssign` 往 `_stage` 追加），不是"源码里有这几个字" ——
    #   MEMORY 里那条坑：`if False:` 里写一遍源码也照样命中。
    # [EN] ★ Recognize the **statement** (an `AugAssign` appending to `_stage`), not "the source
    # [EN] contains these characters" -- the MEMORY pitfall: the same text inside `if False:` matches.
    adds = [n for n in ast.walk(decide)
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
            and n.target.id == '_stage']
    joined = '\n'.join(ast.unparse(n) for n in adds)
    # ★ `_own`（上一拍做的动作）必须**真被追加**。只数"有几处 += _stage"不够：
    #   2026-10-18 加了「上一拍说的」那段之后，把动作那段删掉，计数照样 > 0
    #   ⇒ 判据还是绿的（反例法 ⑤ 当场抓出来的）。
    # [EN] ★ `_own` (last beat's action) must be **actually appended**. Counting "how many += _stage"
    # [EN] is not enough: after the 2026-10-18 "what you said" block was added, deleting the action
    # [EN] block still leaves a positive count => the check stays green (caught by mutation ⑤).
    ok('B2 ★★★ `decide` 里把**动作那一段**追加进 `_stage`（不是只算了一次就扔掉）',
       any('_own' in ast.unparse(n) for n in adds), f'{len(adds)} 处 += _stage')
    ok('B3 ★★★ 追加的内容里有 `[你上一拍做的]` 这个段名',
       '[你上一拍做的]' in joined, joined[:120])
    ok('B4 ★★★ 而且**明写了"不要再把这段演一遍"**'
       '（只说"你刚才做了X"不够 —— 模型会理解成"接着做"）',
       '不要再把这段演一遍' in joined, joined[-120:])

    # 成对：受 `DIALOGUE_CONTEXT` 控制（关掉就一个字都不给，别偷偷加 token）
    # [EN] Paired: gated by `DIALOGUE_CONTEXT` (off = not a single character, no sneaky tokens).
    has_gate = any(
        isinstance(n, ast.If) and 'DIALOGUE_CONTEXT' in ast.unparse(n.test)
        and 'last_own_action' in ast.unparse(n)
        for n in ast.walk(decide))
    ok('B5 ★★★ 成对：这段受 `DIALOGUE_CONTEXT` 控制（关掉就完全不给，'
       '与 `[刚才]` 同一个开关 —— 用户要省 token 时一键全关）', has_gate, '')

    # 成对：不许把台词（speak）当成"上一拍做的动作"
    # [EN] Paired: dialogue must not be treated as "what I did last beat".
    # ★★★ 2026-10-18：这一条原来断言的是源码里有 `'action', 'move', 'enter'` ——
    #   而**产品从来不写 `'action'`**（`sim/loop._note_stage_line` 写的是 `'act'`）
    #   ⇒ 夹具自说自话、判据全绿，防重演块整整一个版本没有生效。
    #   现在改成**行为判**：`ACT_KINDS` 必须含生产侧真写的 `'act'`，且不含 `aside` / `speak`。
    # [EN] ★★★ 2026-10-18: this used to assert the source contains `'action', 'move', 'enter'` --
    # [EN] but **the product never writes `'action'`** (`sim/loop._note_stage_line` writes `'act'`),
    # [EN] so the fixture talked to itself and every criterion was green while the anti-replay block
    # [EN] never ran for a whole version. Now it is a **behavioral** check: `ACT_KINDS` must contain
    # [EN] the `'act'` the production side really writes, and must not contain `aside` / `speak`.
    from world.state import WorldState as _W
    _kinds = tuple(getattr(_W, 'ACT_KINDS', ()))
    ok('B6 ★★★ `WorldState.ACT_KINDS` 认**生产侧真写的** `act`，且不含 `aside` / `speak`',
       'act' in _kinds and 'aside' not in _kinds and 'speak' not in _kinds,
       str(_kinds))


def main() -> int:
    group_a()
    group_b()
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['ok'] = not bad
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n防重演验证：{len(checks) - len(bad)}/{len(checks)}', flush=True)
    return 0 if not bad else 2


if __name__ == '__main__':
    raise SystemExit(main())
