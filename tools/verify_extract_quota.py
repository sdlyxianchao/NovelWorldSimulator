# -*- coding: utf-8 -*-
"""验证：**提取的条数配额**跟得上设定集，而且**代码那一侧不砍条数**（2026-10-27）。

★ 起因（实测）：设定集写了 **30 条细节 / 15 条关系**，开卷之后进设定集的只有
  **8 条 / 8 条** —— 提示词里"最多 8 条"是写死的。丢的东西比数量更要紧：
    · **整类消失**：30 条分五类（器物 / 规矩 / 口癖 / 客人讲究 / 忌讳），
      进来的 8 条里「客人讲究」那 6 条和「忌讳」那 6 条**一条都没有** ——
      而"鬼客的讲究"正是本书幽默四来源之首，"忌讳"里有主角的判定口诀。
    · **反派的关系只剩 1 条**：反派单独写在人物卡上的 4 条张力，只活了「反派 × 主角」。

★ 本判据守三件事：
    A 提示词的上限**放宽了**，而且要求**按类别铺开**（只挑"最具体的"会整类消失）；
    B **输出 token 上限够装下满配** —— 一撞线就走"重来一次、大幅压缩"
      （细节只剩 4 条），等于这次放宽白做，而症状看起来是"模型不肯多写"；
    C **解析层不砍条数** —— 条数只由提示词决定，代码不许再砍一刀
      （两处都砍的话，作者加到 30 条也没用）。

English:
Verification: the **extraction item quotas** keep up with the setting collection, and **the code
side does not cut items** (2026-10-27). Measured cause: the settings wrote **30 details / 15
relations**, but only **8 / 8** reached the setting collection -- the prompt hardcodes "at most 8".
What was lost matters more than the count: **whole categories vanished** (of 30 details in five
categories, none of the 6 "guest customs" and none of the 6 "taboos" survived -- and guest customs
are the first of this book's four sources of humour, while the taboos hold Chen Wang's diagnostic
rhyme), and **the antagonist kept 1 of 4 relations** (of Zhu Bi's four tensions, written on his own
character card, only "Zhu Bi x Chen Wang" lived). This guards: A the prompt limits are **raised**,
and details must be **spread across categories** (picking "the most concrete" kills whole
categories); B the **output token cap fits a full load** -- hitting it triggers "try again, compress
hard" (details down to 4), cancelling this very change, and the symptom reads as "the model won't
write more"; C the **parsing layer cuts nothing** -- count is the prompt's business only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from ingest import extractor as EX                 # noqa: E402
from world import layers as LY                     # noqa: E402

REPORT: list[dict] = []


def rec(name: str, ok_: bool, detail: str = '') -> bool:
    REPORT.append({'name': name, 'ok': bool(ok_), 'detail': detail})
    print(f"  {'✓' if ok_ else '✗'} {name}"
          + (f'  | {detail}' if detail else ''), flush=True)
    return bool(ok_)


def _prompt_cap(section: str) -> int:
    """从提示词里读出某一项的条数上限（"最多 N 条"）。"""
    m = re.search(r'最多\s*(\d+)\s*条', EX._PROMPT)
    return int(m.group(1)) if m else 0


# ══════════════════════════════════════════════════════════════════
#  【A】提示词的上限放宽了 + 要求按类别铺开
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    print('\n【A】提示词里的条数上限 —— 放宽 + 按类别铺开', flush=True)
    p = EX._PROMPT
    m_detail = re.search(r'细节[^。]{0,80}?最多\s*(\d+)\s*条', p)
    m_rel = re.search(r'关系[^。]{0,60}?最多\s*(\d+)\s*条', p)
    n_detail = int(m_detail.group(1)) if m_detail else 0
    n_rel = int(m_rel.group(1)) if m_rel else 0
    rec('A1 ★★★ 细节上限 **>= 20**（以前 8，实测丢掉两整类）',
        n_detail >= 20, str(n_detail))
    rec('A2 ★★★ 关系上限 **>= 16**（以前 8，反派那 4 条只活了 1 条）',
        n_rel >= 16, str(n_rel))
    rec('A3 ★★★ 细节要求**按类别铺开**（只挑"最具体的"会让整类消失）',
        ('按类别' in p or '每一类' in p) and '类' in p)
    # ⚠ 只认"整类消失"这四个字连在一起：单判 `'整类' in p` 的话，下面那句
    #   "'客人讲究'与'忌讳'两整类一条都没有"就把判据顶住了 ⇒ 删掉教训那段照样绿
    #   （反例法 ④ 实测）。这条守的是"**教训写在提示词里**"本身。
    # [EN] Only the four-character phrase counts: checking `'整类' in p` alone is satisfied by the
    # sentence "not one of the two whole categories survived" => deleting the lesson stayed green
    # (mutation knife ④). This guards "**the lesson is written in the prompt**" itself.
    rec('A4 ★★★ 提示词里**明写着**「整类消失」这个教训（后人别再改回"挑最具体的"）',
        '整类消失' in p)
    rec('A5 旧口径（细节"最多 8 条"）已经不在提示词里',
        not re.search(r'细节最多\s*8\s*条', p))
    # ⚠ 两处都判"**每一处**都是同一个数"，不是"提示词里存在某个 70 / 20"：
    #   这份提示词在两处都写了字段上限（字段说明那一段 + 硬要求那一段），
    #   只判"存在"的话，**改一处、另一处留旧值**照样绿 —— 而"修一半比不修更坏"
    #   （下游按 70 截断、提示词却让模型写 40 ⇒ 半句话）。
    # [EN] Both check "**every** occurrence is the same number", not "some 70 / 20 exists": the prompt
    # states the field caps twice, so an existence check stays green when **one is changed and the
    # other left stale** -- and "half a fix is worse than none".
    body_caps = re.findall(r'内容`?\s*≤\s*(\d+)\s*字', p)
    rec('A6 ★★★ **每一处**「内容 ≤ N 字」都是 70（与 `layers.DETAIL_EACH` 同口径）',
        bool(body_caps) and all(c == '70' for c in body_caps),
        f'{body_caps} / layers.DETAIL_EACH={LY.DETAIL_EACH}')
    name_caps = re.findall(r'名称`?\s*≤\s*(\d+)\s*字', p)
    rec('A7 ★★★ **每一处**「名称 ≤ N 字」都是 20（设定集文档写的是 20，不是 12）',
        bool(name_caps) and all(c == '20' for c in name_caps), str(name_caps))


# ══════════════════════════════════════════════════════════════════
#  【B】输出 token 上限够装下满配
# ══════════════════════════════════════════════════════════════════
def group_b() -> None:
    print('\n【B】输出上限 —— 撞线会走"大幅压缩"，等于白放宽', flush=True)
    # 保守估：中文 1 字 ≈ 1 token（各家 tokenizer 只会更少，不会更多）
    per_detail = 20 + 70 + 20 + 40          # 名称+内容+场合+涉及
    full = (20 * per_detail                 # 细节 20 条
            + 16 * 50                       # 关系 16 条
            + 8 * 60                        # 伏笔 8 条
            + 12 * 120                      # 地点 12 条（含内里）
            + 7 * 225                       # 人物 7 位（八字段）
            + 120 + 200 + 180)              # 世界观 + 剧情线 + 规则
    cap = EX._MAX_OUT_TOKENS
    rec('B1 ★★★ 满配估算 %d 字 < 输出上限 %d'
        '（撞线就走"重来一次、细节只剩 4 条"，这次放宽等于白做）' % (full, cap),
        full < cap, f'{full} vs {cap}')
    rec('B2 输出上限 >= 12000（旧值 8000 正好压在线上）',
        cap >= 12000, str(cap))
    rec('B3 重试时的压缩提示仍在（真撞线时还有兜底）',
        '重新输出完整的 JSON' in EX._SHORTER_HINT)


# ══════════════════════════════════════════════════════════════════
#  【C】解析层不砍条数
# ══════════════════════════════════════════════════════════════════
def group_c() -> None:
    print('\n【C】解析层 —— 条数只由提示词决定，代码不许再砍一刀', flush=True)
    raw = {
        '人物': [{'姓名': f'人物{i}'} for i in range(9)],
        '世界观': '世界观',
        '地点': [{'名称': f'地点{i}'} for i in range(15)],
        '关系': [{'甲': 'A', '乙': f'B{i}', '关系': 'x', '张力': 'y'}
                for i in range(20)],
        '伏笔': [{'编号': f'F{i}', '内容': 'c'} for i in range(10)],
        '剧情参考线': '起承转合',
        '顶级规则': [f'规则{i}' for i in range(8)],
        '细节': [{'名称': f'细节{i}', '内容': 'c', '场合': 's', '涉及': 'w'}
                for i in range(30)],
    }
    out = EX._validate(raw)
    rec('C1 ★★★ 喂 30 条细节进去 ⇒ **出来还是 30 条**（代码不砍）',
        len(out.get('细节') or []) == 30, str(len(out.get('细节') or [])))
    rec('C2 喂 20 条关系进去 ⇒ 出来还是 20 条',
        len(out.get('关系') or []) == 20, str(len(out.get('关系') or [])))
    rec('C3 人物 / 地点 / 伏笔也不砍',
        (len(out.get('人物') or []), len(out.get('地点') or []),
         len(out.get('伏笔') or [])) == (9, 15, 10),
        f"{len(out.get('人物') or [])}/{len(out.get('地点') or [])}/"
        f"{len(out.get('伏笔') or [])}")
    # ⚠ 用 `try`：这一条防的正是"抛异常"，一崩整个判据脚本就**什么都不报**了
    #   （反例法 ⑫ 实测：崩掉之后实际红 = []，看上去像"没抓到"）。
    # [EN] Wrapped in `try`: this guards against raising, and a crash makes the whole script report
    # **nothing** (mutation knife ⑫: the crash left "actually red = []", looking like a miss).
    _want = {k: ([] if k != '世界观' and k != '剧情参考线' else '')
             for k in ('人物', '世界观', '地点', '关系', '伏笔',
                       '剧情参考线', '顶级规则', '细节')}
    try:
        _got = EX._validate({})
        _err = ''
    except Exception as _e:                                       # noqa: BLE001
        _got, _err = None, f'{type(_e).__name__}: {_e}'
    rec('C4 ★★★ 缺字段时补空（**不抛异常**，空表与缺文件分得开）',
        _got == _want, _err or str(sorted((_got or {}).keys())))


def main() -> int:
    group_a()
    group_b()
    group_c()
    bad = [c for c in REPORT if not c['ok']]
    print('\n' + '─' * 62)
    print(f'  提取配额验证：{len(REPORT) - len(bad)}/{len(REPORT)}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
