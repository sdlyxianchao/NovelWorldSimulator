# -*- coding: utf-8 -*-
"""验证：**设定提取窗口**装的是该装的东西（2026-10-27 实测事故）。

★ 事故现场（一个素材齐全的项目，2026-10-27 实测）：
    36 个文件、94,118 字，**全量**拼进 12,000 字窗口，`truncate_mid` **掐头留尾**之后
    留下的是：根目录的 `AI打磨记录.md` / `写作底料` / `设定集_说明.md`
    和 `06_地图` 的最后两页（`12_井与地下`、`13_图页清单`）。
    **世界观、七张人物卡、伏笔、地点.yaml、顶级规则 —— 一份都没剩下。**

    根因不是"窗口太小"，是**两条**：
      ① 谁都往窗口里挤 —— `06_地图`（3.6 万字，只服务画图）、`写作参考`
         （1.8 万字，只给人看）、`04_大纲` / `05_正文`（各有 `outline_text` /
         `novel_text` 专门去处）跟世界观抢同一份窗口；
      ② 裁剪**按位置**砍中间 —— 而中间恰好是人物卡和世界观。

★ 修完的三件事，本判据一组守一件：
    · `pick_for_extract`：按用途挡掉一批 + 按重要性排序（A/B 组）；
    · `_build_content`：**整份**取舍，不切半截，跳过了要说出来（C 组）；
    · 该在的东西（世界观/人物卡/伏笔）**真的在**，不该在的（地图册）**真的不在**
      （D 组，直接拿"旧算法"对照，证明这条判据防的就是那件事）。

★ 反面也要守住：排除只发生在**提取窗口**，扫描本身仍是全量的 ——
   画图（`ingest/atlas`）还得读 `06_地图`，挡错了地图就没了（F 组）。

English:
Verification: the **setting extraction window** holds what it should (measured incident,
2026-10-27).

★ The incident (a project with the full set of material, measured 2026-10-27): 36 files, 94,118 chars, all
concatenated into a 12,000-char window; after `truncate_mid` cut the head and kept the tail,
what survived was the root `AI打磨记录.md` / `写作底料` / `设定集_说明.md`
and the last two pages of `06_地图`.
**The worldview, seven character cards, foreshadowing, locations, top rules -- none survived.**

The root cause is not "the window is too small", it is two things: ① everyone squeezes in --
`06_地图` (36k chars, map drawing only), `写作参考` (18k chars, for humans only),
`04_大纲` / `05_正文` (each has its own `outline_text` / `novel_text` destination);
② trimming cuts **by position**, and the middle is exactly the character cards and worldview.

★ The three fixes, one group guarding each: `pick_for_extract` blocks a batch by purpose and
sorts by importance (groups A/B); `_build_content` drops **whole** files, never cuts one in
half, and states what it skipped (group C); what must be there (worldview / character cards /
foreshadowing) **really is**, what must not be (map book) **really isn't** (group D, checked
against the "old algorithm" directly to prove this prevents that very thing).

★ The reverse must hold too: exclusion happens **only** in the extraction window -- scanning
itself is still full, because drawing (`ingest/atlas`) still reads `06_地图` (group F).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from ingest import scanner                        # noqa: E402
from ingest import extractor as EX                # noqa: E402
from util.text import truncate_mid                # noqa: E402

REPORT: list[dict] = []


def rec(name: str, ok_: bool, detail: str = '') -> bool:
    REPORT.append({'name': name, 'ok': bool(ok_), 'detail': detail})
    print(f"  {'✓' if ok_ else '✗'} {name}"
          + (f'  | {detail}' if detail else ''), flush=True)
    return bool(ok_)


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def _mk_project(root: Path, *, big: bool = False) -> None:
    """造一个跟典型设定集同构的项目（目录名决定用途，不是内容）。
        English:
    Build a project with the same shape as a typical setting collection (the directory name
    decides the purpose, not the content).
    """
    n = 3000 if big else 400
    body = ('甲' * n)
    _w(root / '01_设定' / '世界观.md', f'# 世界观\n{body}')
    _w(root / '01_设定' / '顶级规则.md', f'# 顶级规则\n{body}')
    _w(root / '01_设定' / '地点.yaml', f'地点:\n- 名称: 某楼\n  说明: {body}')
    for who in ('甲', '乙', '丙'):
        _w(root / '02_人物' / f'{who}.md', f'# {who}\n- 姓名：{who}\n{body}')
    _w(root / '03_伏笔.md', f'# 伏笔\n{body}')
    _w(root / '写作参考' / '人物细节.md', f'# 人物细节\n{body}')      # 只给人看
    for i in range(3):
        _w(root / '06_地图' / f'{i:02d}_某地.md', f'# 某地{i}\n{body}')  # 只服务画图
    _w(root / '04_大纲' / '故事大纲.md', f'# 大纲\n{body}')
    _w(root / '05_正文' / '第一章 甲.md', f'# 第一章\n{body}')
    _w(root / '素材杂项.md', f'# 素材\n{body}')                      # 杂项：不许被排除
    # 名字**故意排在"世界观"前面**（`01` 的字典序比"世"小）：只有"垫后"标记生效，
    # 它才会排到世界观后面 —— 否则这条判据会被字典序意外满足（空靶）。
    # [EN] The name is **deliberately sorted before "世界观"** (`01` < `世` in code-point order): only
    # [EN] if the "sort last" marker works does it land after the worldview -- otherwise this
    # [EN] criterion is satisfied by accident (an empty target).
    _w(root / '01_设定集说明.md', f'# 说明\n{body}')                   # 同类里垫后
    _w(root / '01_设定' / '空档.md', '')                             # 空文件：不该占位置


def _names(items) -> list[str]:
    return [it.name for it in items]


# ══════════════════════════════════════════════════════════════════
#  【A】谁进窗口 —— 按用途挡，不按类别猜
# [EN] 【A】Who enters the window -- filter by purpose, not by guessing category
# ══════════════════════════════════════════════════════════════════
def group_a(tmp: Path) -> None:
    print('\n【A】谁进「设定提取窗口」—— 另有专门用途的不许来挤', flush=True)
    root = tmp / 'pa'
    _mk_project(root)
    items = scanner.scan_project(root)
    picked = EX.pick_for_extract(items)
    names = _names(picked)

    rec('A1 ★★★ `06_地图` 目录下的**一份都不进**（3.6 万字只服务画图，'
        '挤进来就是把世界观赶出去）',
        not any('06_地图' in str(it.path) for it in picked),
        str([n for n in names if '某地' in n]))
    rec('A2 ★★★ `写作参考` 目录下的**一份都不进**（给人看的参考，不是素材）',
        not any('写作参考' in str(it.path) for it in picked),
        str([n for n in names if '细节' in n]))
    rec('A3 大纲类不进（另有 `outline_text` → `ingest/progress` 拆节点）',
        '故事大纲.md' not in names, str(names))
    rec('A4 正文类不进（另有 `novel_text` → 文风样本）',
        not any('第一章' in n for n in names), str(names))
    rec('A5 ★★★ 规则 / 人物 / 伏笔 / 设定 **都要进** —— 挡错了就是整个设定集做残',
        all(any(k in n for n in names) for k in ('顶级规则', '甲.md', '伏笔', '世界观')),
        str(names))
    rec('A6 ⚠ 「杂项」**不排除**：文件名没类别词不等于不重要'
        '（作者的 `写作底料` 就是靠 `.nws_classify.json` 标成设定的）',
        any('素材杂项' in n for n in names), str(names))
    rec('A7 空文件不进（读了没内容的不占位置）',
        all(it.content for it in picked), str(len(picked)))


# ══════════════════════════════════════════════════════════════════
#  【B】顺序 —— 装不下时先砍谁
# [EN] 【B】Order -- who gets cut first when it doesn't fit
# ══════════════════════════════════════════════════════════════════
def group_b(tmp: Path) -> None:
    print('\n【B】排好顺序 —— 装不下时砍垫后的，不砍人物卡和世界观', flush=True)
    root = tmp / 'pb'
    _mk_project(root)
    picked = EX.pick_for_extract(scanner.scan_project(root))
    order = [EX._CAT_ORDER.get(it.category, 9) for it in picked]
    rec('B1 顺序单调不减：规则(0) → 人物(1) → 伏笔(2) → 设定(3) → 杂项(4)',
        order == sorted(order), str(order))
    cats = [it.category for it in picked]
    rec('B2 规则排在最前（它是作者对故事的硬约束，最不能丢）',
        cats[0] == '规则', str(cats[:3]))
    rec('B3 ★★★ 人物卡排在「设定（素材/说明）」之前 —— '
        '旧算法砍掉的就是这一块',
        cats.index('人物') < cats.index('设定'), str(cats))
    rec('B4 同类里「说明 / 记录 / 底料 / 样章」垫后'
        '（`01_设定集说明.md` 的名字排在世界观**前面**，靠的只能垫后标记，'
        '不是字典序）',
        [it.name for it in picked].index('01_设定集说明.md')
        > [it.name for it in picked].index('世界观.md'),
        str([it.name for it in picked]))


# ══════════════════════════════════════════════════════════════════
#  【C】装不下时怎么取舍
# [EN] 【C】How files are dropped when it doesn't fit
# ══════════════════════════════════════════════════════════════════
def group_c(tmp: Path) -> None:
    print('\n【C】装不下的时候 —— 整份跳过、不切半截、跳过了要说出来', flush=True)
    root = tmp / 'pc'
    _mk_project(root, big=True)
    items = scanner.scan_project(root)
    EX.take_notes()
    body = EX._build_content(items)
    notes = EX.take_notes()

    rec('C1 输出不超过窗口上限', len(body) <= EX._MAX_CONTENT,
        f'{len(body)} / {EX._MAX_CONTENT}')
    rec('C2 ★★★ **不切半截**：窗口里不留截断标记（` …(略)… `）'
        '—— 半截文件会让 JSON 残句，那是最难查的一种坏法',
        ' …(略)… ' not in body, str(len(body)))
    picked = EX.pick_for_extract(items)
    kept = [it for it in picked if f'【{it.category}】{it.name}\n' in body]
    rec('C3 ★★★ 保留下来的文件**首尾都完整**（整份进、整份不进）',
        all((it.content[:120] in body) and (it.content[-120:] in body) for it in kept),
        f'保留 {len(kept)} / {len(picked)} 份')
    rec('C4 ★★★ 装不下时**说出来**跳过了哪几份（`_note` → 界面日志）—— '
        '静默装不下是最坏的一种',
        bool(notes) and '跳过' in ''.join(notes), str(notes[:1]))
    core = [it.name for it in kept if it.category in ('规则', '人物')]
    rec('C5 ★★★ 再挤也**先保规则和人物卡**（被跳过的只能是垫后的）',
        len(core) >= 4, f'核心留下 {len(core)} 份：{core}')


# ══════════════════════════════════════════════════════════════════
#  【D】该在的真的在、不该在的真不在（拿旧算法对照）
# [EN] 【D】What must be there is there, what must not is not (against the old algorithm)
# ══════════════════════════════════════════════════════════════════
def group_d(tmp: Path) -> None:
    print('\n【D】拿旧算法对照 —— 证明这条判据防的就是那件事', flush=True)
    root = tmp / 'pd'
    _mk_project(root, big=True)
    items = scanner.scan_project(root)

    # 旧算法：全量拼 + truncate_mid（掐头留尾）
    old = '\n\n'.join(f'【{it.category}】{it.name}\n{it.content}' for it in items)
    old = truncate_mid(old, 12000)
    new = EX._build_content(items)

    rec('D1 ★★★ 旧算法下**人物卡会整份消失**（这正是 2026-10-27 的现场）',
        '甲.md' not in old and '乙.md' not in old,
        f'旧窗口 {len(old)} 字，含人物卡：{["甲.md" in old]}')
    rec('D2 ★★★ 新算法下**人物卡在**（三张都在）',
        all(f'{w}.md' in new for w in ('甲', '乙', '丙')),
        f'新窗口 {len(new)} 字')
    rec('D3 ★★★ 新算法下**世界观在**（旧算法下它也被砍掉了）',
        '世界观.md' in new and '世界观.md' not in old,
        f'旧={("世界观.md" in old)} 新={("世界观.md" in new)}')
    rec('D4 伏笔在', '03_伏笔.md' in new, '')
    rec('D5 ★★★ 地图册**一份都不在**（旧算法下它反倒留下了两页）',
        not any(f'{i:02d}_某地.md' in new for i in range(3)),
        str([n for n in ('00_某地.md', '01_某地.md', '02_某地.md') if n in new]))
    rec('D6 写作参考不在（旧算法下它也在抢）', '人物细节.md' not in new, '')


# ══════════════════════════════════════════════════════════════════
#  【E】窗口本身
# [EN] 【E】The window itself
# ══════════════════════════════════════════════════════════════════
def group_e() -> None:
    print('\n【E】窗口大小 —— 够装核心素材，又不至于失控', flush=True)
    rec('E1 上限 ≥ 20000（实测：排除掉地图/参考/大纲/正文之后，'
        '该项目的核心素材仍约 1.6 万字）',
        EX._MAX_CONTENT >= 20000, str(EX._MAX_CONTENT))
    rec('E2 上限 ≤ 40000（再大就不是"一份设定集"，而是把整本书塞给模型了）',
        EX._MAX_CONTENT <= 40000, str(EX._MAX_CONTENT))
    # ⚠ 口径已改（2026-10-27 提取配额那一轮）：输出上限 8000 → **12000**。
    #   这条要防的东西没变 —— "改窗口的那次改动不许顺手把**输出上限**也带走"
    #   ⇒ 判据改成查新的数（`verify_extract_quota` B1/B2 是同一个数：满配 7,795 字
    #   装得下，撞线会走"重来一次、细节只剩 4 条"）。
    # [EN] The figure changed (2026-10-27 extraction-quota round): output cap 8000 -> **12000**. What
    # this guards has not changed -- "the change to the window must not quietly take the **output
    # cap** with it" => the criterion now checks the new figure (same number as
    # `verify_extract_quota` B1/B2: a full load of 7,795 chars must fit, since hitting the cap
    # triggers "try again, details down to 4").
    rec('E3 输出上限**没跟着动**（真正要防的是输出超上限）',
        EX._MAX_OUT_TOKENS == 12000, str(EX._MAX_OUT_TOKENS))


# ══════════════════════════════════════════════════════════════════
#  【F】反面：排除只发生在窗口里，别处不受影响
# [EN] 【F】Reverse: exclusion only happens in the window, nowhere else
# ══════════════════════════════════════════════════════════════════
def group_f(tmp: Path) -> None:
    print('\n【F】反面 —— 扫描仍是全量，画图还得读 `06_地图`', flush=True)
    root = tmp / 'pf'
    _mk_project(root)
    items = scanner.scan_project(root)
    all_names = _names(items)
    rec('F1 ★★★ `scan_project` **仍然扫得到** `06_地图`（画图环节靠它，'
        '挡在扫描层地图就没了）',
        sum(1 for n in all_names if '某地' in n) == 3, str(len(all_names)))
    rec('F2 ★★★ 同理，`04_大纲` / `05_正文` 也仍在扫描结果里'
        '（它们只是不进**提取窗口**）',
        '故事大纲.md' in all_names and any('第一章' in n for n in all_names),
        str(all_names[:4]))
    rec('F3 排除目录清单是可配置的常量，不是写死在调用处',
        '06_地图' in EX._EXTRACT_SKIP_PARTS and '写作参考' in EX._EXTRACT_SKIP_PARTS,
        str(sorted(EX._EXTRACT_SKIP_PARTS)))


# ══════════════════════════════════════════════════════════════════
#  【G】兜底：挑完之后不许是空的
# [EN] 【G】Fallback: the window must never end up empty
# ══════════════════════════════════════════════════════════════════
def group_g(tmp: Path) -> None:
    print('\n【G】兜底 —— 作者只丢一本小说进来时，窗口不许是空的', flush=True)
    root = tmp / 'pg'
    _w(root / '05_正文' / '第一章 雨.md', '# 第一章\n雨脚敲着檐瓦。' * 30)
    _w(root / '04_大纲' / '故事大纲.md', '# 大纲\n起承转合。')
    items = scanner.scan_project(root)
    EX.take_notes()
    body = EX._build_content(items)
    notes = EX.take_notes()
    rec('G1 ★★★ 项目里**只有正文 / 大纲**时，窗口**不为空**'
        '（按用途挑完会是空的 → 退回全部有内容的文件）',
        bool(body.strip()), f'{len(body)} 字')
    rec('G2 ★★★ 退回时**要说出来**（不然作者分不清"材料不合适"还是"程序坏了"）',
        any('退回' in n for n in notes), str(notes[:1]))
    root2 = tmp / 'pg2'
    _w(root2 / '01_设定' / '世界观.md', '# 世界观\n' + '甲' * 60)
    _w(root2 / '05_正文' / '第一章.md', '# 第一章\n雨脚敲着檐瓦。')
    EX.take_notes()
    body2 = EX._build_content(scanner.scan_project(root2))
    notes2 = EX.take_notes()
    rec('G4 兜底只在该用的时候用：有设定文档 ⇒ 世界观看得到、'
        '且**没有**"退回"的提示',
        '世界观' in body2 and not any('退回' in n for n in notes2),
        f'{len(body2)} 字 / notes={len(notes2)}')


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_win_'))
    try:
        group_a(tmp)
        group_b(tmp)
        group_c(tmp)
        group_d(tmp)
        group_e()
        group_f(tmp)
        group_g(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    bad = [c for c in REPORT if not c['ok']]
    print('\n' + '─' * 62)
    print(f'  提取窗口验证：{len(REPORT) - len(bad)}/{len(REPORT)}'
          + ('' if not bad else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
