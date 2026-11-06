# -*- coding: utf-8 -*-
"""验证：**语言审校（polisher）真的会查「语域是不是自然标准普通话」并给出改写**。

用户 2026-10-15 原话（这一支的规格）
------------------------------------
    「台词半文半白不像标准普通话」
配合 2026-10-12 的那一条（"像不像活人说话"）：AI 生成的台词常常端着、
文言文腔、或左右对称的对仗漂亮话——真人说话不这么齐。

P0 已经让 小说作家 / 剧作者 / 演员 在**写**的时候就用自然标准普通话。
这一支（P1）是**兜底**：语言审校每天读样章，把"夹文言词 / 半文半白 /
念稿腔对仗"的句子点出来，并**给一句改写**（不是只打叉）。

判据分两组
----------
  A **约束真的进了提示词（两层都要）**
     A1 ★★★ 软件层 `agents/polisher.md` 的**系统提示词块**含语域硬约束
            （自然标准普通话 / 半文半白 / 改写）—— 这一块是 `catalog.prompt_block`
            剥掉 HTML 注释后发给模型的，等于"改了真的到模型耳朵里"。
     A2 ★★★ P0 的三份角色提示词（actor / screenwriter / novelist）仍带
            **自然标准普通话**语域约束（P1 不能把 P0 弄丢）。
     A3 ★★★ `_tail`（演员台词纪律）与 工艺库「人物与对话」第七组仍带语域约束。
  B **任务提示词 + 行为（真机只用 MOCK）**
     B1a ★★★ 审校那一段**任务提示词**（crew/agents.py `Polisher.work` 里的
             f-string）含「语域违规」字样 —— 这是真正指挥模型"还查语域"的那句。
     B1b ★★★ 同一段任务提示词的 JSON schema 里还有 `"改写"` 字段
            （让模型**给改写后的句子**，而不只是"给方向"）。
     B2 ★★★ **行为**：塞一句半文半白 / 文言的台词进去，审校的产出
            **真的把改写后的标准普通话渲染出来**（含「改写为：…」与「（语域）」）。

⚠ 为什么分两层 + 行为：这一位的提示词是**两份**——
   ① `agents/polisher.md` 的 body（经 `prompt_block` 发）；
   ② `crew/agents.py` 里写死的任务 f-string（"指出 AI 味重的地方"那段）。
   只改一份，另一份会把它盖掉 / 让它形同虚设。A 组盯①，B1 组盯②，B2 用 MOCK
   把"改了真的生效"跑一遍（不联网、不弹窗）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_polisher_register.py
产出：assets/screenshots/polisher_register_report.json

English:
Verification: **the Language Polisher really checks "is the register natural standard Mandarin"
and gives a rewrite**.
User's exact words 2026-10-15 (spec for this branch): "the dialogue is half-classical half-modern,
not like standard Mandarin". Combined with the 2026-10-12 one ("does it sound like a live person"):
AI-written lines are often stiff, classical-flavoured, or symmetrically antithetical -- real people
don't speak that evenly.
P0 already made novelist / screenwriter / actor WRITE in natural standard Mandarin. This branch (P1)
is the **backstop**: the polisher reads the daily sample every day, flags "classical words / half-classical
/ podium-antithesis" lines, and **gives a rewrite** (not just an X).
Criteria in two groups ...
Usage:
    .venv\\Scripts\\python.exe tools/verify_polisher_register.py
Output: assets/screenshots/polisher_register_report.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import verify_ui_common as VU                               # noqa: E402
VU.redirect_env_writes()

from config import CFG                                      # noqa: E402
CFG.set('MOCK_LLM', 'true')

from crew import catalog as CAT                             # noqa: E402
from craft import craftmix as cm                            # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _txt(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def _prompt_const_in_polisher_work() -> str:
    """取 `crew/agents.py` 里 `Polisher.work` 方法内 `prompt = f"..."` 的**恒定部分**
    （`{…}` 那段跳过）。只扫那个函数，不认整份文件。
    [EN] Take the **constant parts** of the `prompt = f"..."` f-string inside `Polisher.work`
    [EN] (skipping the `{...}` segments). Scans only that method, not the whole file.
    """
    src = _txt('crew/agents.py')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != 'Polisher':
            continue
        for sub in node.body:
            if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    or sub.name != 'work':
                continue
            for a in ast.walk(sub):
                if (isinstance(a, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'prompt'
                                for t in a.targets)
                        and isinstance(a.value, ast.JoinedStr)):
                    return ''.join(
                        v.value for v in a.value.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return ''


# ══════════════════════════════════════════════════════════════════════
#  A. 约束真的进了提示词（两层）
# [EN] A. The constraint really entered the prompt (both layers)
# ══════════════════════════════════════════════════════════════════════
def test_prompt() -> None:
    # ★★★ A1：软件层 .md body（剥注释后）含语域硬约束
    # [EN] ★★★ A1: the software-layer .md body (comments stripped) carries the register hard-constraint
    blk = CAT.prompt_block('polisher')
    miss = [k for k in ('标准普通话', '半文半白', '改写')
            if k not in blk]
    ok('A1 ★★★ 语言审校的**系统提示词块**含**语域硬约束**'
       '（自然标准普通话 / 半文半白 / 改写）—— 这是剥注释后真发给模型的',
       not miss, f'缺：{miss}' if miss else '三段都在')

    # ★★★ A2：P0 三份角色提示词仍带自然标准普通话
    # [EN] ★★★ A2: the three P0 role prompts still carry natural-standard-Mandarin
    roles = ('actor', 'screenwriter', 'novelist')
    lost = []
    for r in roles:
        b = CAT.prompt_block(r)
        if '标准普通话' not in b:
            lost.append(r)
    ok('A2 ★★★ P0 三份角色提示词（actor / screenwriter / novelist）'
       '仍带**自然标准普通话**语域约束（P1 不能把 P0 弄丢）',
       not lost, '、'.join(lost) if lost else '三份都在')

    # ★★★ A3：`_tail` 与 工艺库第七组仍带语域约束
    # [EN] ★★★ A3: `_tail` and the craft-library seventh group still carry the register constraint
    core = _txt('agent/core.py')
    tail_hit = '标准普通话' in core
    yaml_txt = _txt('craft/playbooks/人物与对话.yaml')
    yaml_hit = '标准普通话' in yaml_txt
    ok('A3 ★★★ 演员台词纪律 `_tail`（agent/core.py）与工艺库「人物与对话」第七组'
       '仍带**语域约束**（两处都是 P0 落的点，反例法盯过）',
       tail_hit and yaml_hit,
       f'_tail={tail_hit} yaml第七组={yaml_hit}')


# ══════════════════════════════════════════════════════════════════════
#  B. 任务提示词 + 行为（MOCK）
# [EN] B. Task prompt + behaviour (MOCK)
# ══════════════════════════════════════════════════════════════════════
def test_task_prompt() -> None:
    const = _prompt_const_in_polisher_work()
    ok('B1a ★★★ 审校的**任务提示词**（Polisher.work 的 f-string）含「语域违规」字样'
       '—— 这是真正指挥模型"还查语域"的那一句（只改 .md 不碰这段 = 形同虚设）',
       '语域违规' in const, '' if const else '没取到 f-string')
    ok('B1b ★★★ 同一段任务提示词的 JSON schema 里还有 `"改写"` 字段'
       '（让模型**给改写后的句子**，而不只是"给方向"）',
       '"改写"' in const, const[:80].replace('\n', ' | '))


async def test_behaviour() -> None:
    """MOCK 跑一遍：塞一句半文半白的台词，看审校产出**真的渲染出改写**。
    [EN] MOCK one pass: feed a half-classical line, see the polisher output
    [EN] **really renders the rewrite**.
    """
    import crew.agents as A
    real_ask = A.ask

    async def fake_ask(tier, messages, **kw):
        return SimpleNamespace(
            value={'问题': [{'原句': '此乃天意', '类型': '语域',
                             '怎么改': '用大白话', '改写': '这就是命'}],
                   '总评': '有一处语域问题'},
            meta={}, notes=[], ok=True, retried=False, salvaged=False, calls=1)

    A.ask = fake_ask
    try:
        # ⚠ `ctx` 在该方法里没被用到，传 None 即可（MOCK 不联网）。
        # [EN] ⚠ `ctx` is unused in this method, None is fine (MOCK, no network).
        note = await A.Polisher().work(None, story='他缓缓道：此乃天意。')
    finally:
        A.ask = real_ask

    body = str(getattr(note, 'body', '') or '')
    ok('B2 ★★★ 行为：塞半文白台词，审校产出**真的渲染出改写后的标准普通话**'
       '（含「改写为：这就是命」与「（语域）」标签）',
       '改写为：这就是命' in body and '（语域）' in body, body[:120].replace('\n', ' | '))


def main() -> int:
    print('═' * 62)
    print('  验证：语言审校会查语域（自然标准普通话）并给改写')
    print('═' * 62)
    try:
        print('\n【A】约束进了提示词（两层）')
        test_prompt()
        print('\n【B】任务提示词 + 行为（MOCK）')
        test_task_prompt()
        import asyncio
        asyncio.run(test_behaviour())
    except Exception:                                            # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'polisher_register_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  语言审校语域判据：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
