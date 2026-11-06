# -*- coding: utf-8 -*-
"""修 ops1 暴露的两个问题（2026-10-18，**等 6 例跑完再执行**）。

⚠ 不能在模拟进行中跑：会让不同用例跑在不同代码上，破坏可比性。
   用法：`python novel_bench/dataset/_fix_stage_and_pov.py`

## 问题 1：作家把不在场的人写进正文

实测 `hlm-01`：`ROUND_CAST=贾母、林黛玉、王熙凤、王夫人`（决策层日志确认已排除宝玉），
但正文里出现"**贾宝玉也在屋里，没言语**"。

根因：`Novelist._transcribe_once` 拼 prompt 时**从不读在场名单** ——
它只有 `ctx.people`（设定集里的全部人物）和 `body`（今天的材料）。
模型按设定集写，就把没上场的人也摆进屋里。

## 问题 2：我加的"心里话只归视角人物"把全知视角写窄了

`hlm-01` 的 `bible.style.pov` 是**第三人称全知**，写王夫人的内心是合规的；
而 2026-10-18 加的第 6 条写成"只能写视角贴着的那个人"，等于禁止了全知视角。
改成按视角分档。
"""
from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent.parent
AGENTS = APP / "crew" / "agents.py"


def fix1(text: str) -> str:
    """把在场名单作为硬边界写进作家 prompt。"""
    old = '''        prompt = f"""你是这本小说的**作家**。今天这一章已经演完了，请你把它**整理成小说**。
{scope}'''
    new = '''        # ★★★ 2026-10-18：**今天真正上场的人**（`ROUND_CAST` / `on_stage_names`）。
        #   为什么必须有：实测 `hlm-01` 的决策层已按名单排除了宝玉（日志确认
        #   "本轮出场名单：贾母、林黛玉、王熙凤、王夫人"），但正文照样写
        #   "**贾宝玉也在屋里**" —— 因为作家这一侧**只拿到设定集的全部人物**，
        #   不知道今天谁上了场，就照着设定集把五个人都摆进屋里。
        #   ⇒ 把在场名单当**硬边界**递给它，并明写"名单外的人不许出现"。
        #   ⚠ 空名单 = 不限制（与 `is_on_stage` 同一口径：空表示"全体"）。
        # [EN] ★★★ 2026-10-18: **who actually took the stage today** (`ROUND_CAST` /
        # [EN] `on_stage_names`). Measured on `hlm-01`: the decision layer had already excluded Bao Yu
        # [EN] (log: "本轮出场名单：贾母、林黛玉、王熙凤、王夫人"), yet the prose still said "**贾宝玉也在屋里**"
        # [EN] -- because the novelist side **only receives the full cast from the settings** and does
        # [EN] not know who was on stage, so it furnishes the room with all five.
        # [EN] => Pass the on-stage roster as a **hard boundary** and state that nobody outside it may
        # [EN] appear. ⚠ An empty roster means "no restriction" (same rule as `is_on_stage`).
        _os: list[str] = []
        try:
            _os = [str(x) for x in (ctx.world.on_stage_names() or [])]
        except Exception:                                         # noqa: BLE001
            _os = []
        _os_block = ''
        if _os:
            _os_block = ('\\n── 今天真正上场的人（正文里**不许出现**名单外的任何人）──\\n'
                         + '、'.join(_os) + '\\n'
                         '⚠ 名单外的人**一个字都不许写**（不许"某某也在屋里"，'
                         '不许让他说话做事），也不要把他算进"众人都笑了"这类集合里。\\n')
        # ★★★ 2026-10-18：**心里话的边界按视角分档**。
        #   第一版写死"只能写视角贴着的那个人"，而《红楼梦》是**第三人称全知**
        #   （`bible.style.pov`）—— 全知视角下写多个人内心**本来是对的**，
        #   被我那条规则写成了错。分档之后：限知/第一人称才禁；全知只禁"凭空补判断"。
        # [EN] ★★★ 2026-10-18: **the inner-voice boundary now depends on point of view**. The first
        # [EN] version hardcoded "only the viewpoint character", but Dream of the Red Chamber is
        # [EN] **third-person omniscient**, where writing several people's thoughts is *correct* and was
        # [EN] made wrong by my rule. Split: limited/first-person forbids it; omniscient only forbids
        # [EN] "inventing a verdict the character never reached".
        _pov = ''
        try:
            _pov = str((getattr(ctx.world, 'style_card', None) or {}).get('视角') or '')
        except Exception:                                         # noqa: BLE001
            _pov = ''
        _limited = any(k in _pov for k in ('限知', '第一人称', '多视角'))
        if _limited:
            _inner_rule = (
                '6. ★★★ **心里话只有视角人物能说**（2026-10-18）。这本书是「' + (_pov or '限知')
                + '」，所以材料里的 `内心` 只许写成**视角人物自己的**：\\n'
                '   · 别人的心思**一个字都不许写**（不许"他心想"，也不许用旁白替他下判断）；\\n'
                '   · 不许把别人的心里话改写成叙述事实 —— 他不知道的事，叙述里也不许知道。\\n')
        else:
            _inner_rule = (
                '6. ★★★ **心里话只能来自材料**（2026-10-18）。这本书是「' + (_pov or '第三人称全知')
                + '」，可以写多个人的内心，但只能是材料里**真的出现过**的那些：\\n'
                '   · **不许替人物凭空补一个判断**（尤其"她从不觉得被怠慢"这类他从未说过的结论）；\\n'
                '   · 不许把别人的心里话改写成叙述事实 —— 他不知道的事，叙述里也不许知道。\\n')
        prompt = f"""你是这本小说的**作家**。今天这一章已经演完了，请你把它**整理成小说**。
{scope}{_os_block}'''
    if old not in text:
        raise SystemExit("锚点 1 没匹配（作家 prompt 头部）")
    return text.replace(old, new, 1)


def fix2(text: str) -> str:
    """把写死的那条内心规则换成按视角生成的变量。"""
    old = '''6. ★★★ **心里话只有这一个人能说**（2026-10-18）。材料里的 `内心` 是**每个角色自己**的
   心里话，整理时只许写成**那个人自己的**：
   · 只能写**这一段视角贴着的那个人的**心里话；别人的心思**一个字都不许写**
     （不许"他心想""她暗自盘算"，也不许用旁白替他说出他没说过的判断）；
   · 不许把别人的心里话改写成叙述事实 —— 他不知道的事，叙述里也不许知道。
   ⚠ 这一条是有据可查的：实测里出现过"岛村被叙述者代说了心事"、
     "黛玉心想'王夫人嫌那奶奶'，而王夫人当时并未开口"。'''
    new = '''{_inner_rule}   ⚠ 有据可查：实测出现过"岛村被叙述者代说了心事"、
     "黛玉心想'王夫人嫌那奶奶'，而王夫人当时并未开口"。'''
    if old not in text:
        raise SystemExit("锚点 2 没匹配（内心规则那一条）")
    return text.replace(old, new, 1)


def main() -> int:
    src = AGENTS.read_text(encoding="utf-8")
    src = fix1(src)
    src = fix2(src)
    AGENTS.write_text(src, encoding="utf-8")
    print("✓ 已修：在场名单硬边界 + 内心规则按视角分档（_inner_rule / _os_block）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
