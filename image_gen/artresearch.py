"""美术的**查资料 → 落盘成技能** 通道。

## 用户要什么（2026-10-26 原话）

> 「你这个是中式住宅 是针对我这个故事的 我后续还有各种类型的故事 可能还有西方的
>   奇幻的 现代的等等不同的 我希望你能够尽可能包含足够的信息 覆盖常见小说类型
>   如果某些情况下缺少信息 最好是美术Agent可以让LLM去查资料 回来绘制
>   绘制之后相关数据资料还需要落地到skills作为SKILL提供后续参考」

拆成三件事，本模块负责后两件：

1. **覆盖常见类型** —— `worldstyle` 里已有 6 个档案（中式店宅/中式府邸/西式宅邸/
   西式城镇/现代/未来/奇幻），判不出来时老实说判不出来；
2. **缺信息就让 LLM 去查** —— `research()`：把 `worldstyle.needs_research()` 列出的
   问题一次性问清，拿回**结构化**答案；
3. **查完落盘成技能** —— `save()`：写成 `skills/地图-<名>/SKILL.md` + `资料.json`。
   下次同一类建筑**直接读盘**，不再花钱查（这是"提供后续参考"的落地）。

## 三条硬纪律

* **不把"查不到"写成"查到了"**：模型说不知道就记 `unknown`，不填一个像样的答案。
  编出来的建筑常识会一路进到提示词，然后画成图 —— 用户看到的是"这房子怎么长这样"。
* **每一条答案都带来源**：`模型常识`（本机模型的知识，可能过时）/ `用户设定`
  （来自这本书的设定集，最可信）。分不清就不写"权威"。
* **落盘可复查**：文件里存 `问/答/来源/时间/模型`，用户能看出"这条是哪来的"。
  与项目老规矩一致：**看不见的东西是最严重的故障**。

## 与 `worldstyle` 的分工

`worldstyle` 决定"按哪种建筑传统画"（数据）；这里决定"这个传统我们还缺什么、
去哪儿补、补到哪"（流程）。**渲染层永远不需要联网** —— 它只读档案 + 已落盘的资料。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from image_gen import worldstyle as WS

_LOG = logging.getLogger('nws.artresearch')

#: 落盘目录名前缀。所有地图技能都以此开头，方便一眼认出、也方便整批清掉重查。
# [EN] Directory prefix for on-disk map skills, so they are easy to spot and to clear in bulk.
PREFIX = '地图-'

#: 单次最多查几条。⚠ 必须设上限：`needs_research` 在兜底档案下会给出 4 条以上，
#: 而每条都是一个真花钱的调用点。5 条足够覆盖"这房子怎么画"的主要疑问。
# [EN] Max questions per round. ⚠ A cap is required: under the fallback profile
# [EN] `needs_research` returns four or more, and each one is a real paid call site. Five covers
# [EN] the main "how is this building built" questions.
MAX_Q = 5

#: **地图原型**那一问（每个风格都先问这一句）。它的答案决定后面所有画法。
# [EN] The **map prototype** question, asked first for every profile; its answer decides every choice.
PROTO_Q = ('这座城有没有可对照的**真实历史地图**（或同一文化圈、同一时期的同类城镇图）？'
           '请给出：图名/年代/地域，以及图上**确定画了**的要素清单'
           '（城墙、城门、护城河、钟鼓楼、衙署、寺观、坊巷、桥梁、码头、市场等，只列真的有的）；'
           '若没有原型，就说明"无原型"，并给出一个最接近的可参考对象。')


@dataclass
class Answer:
    """一条问答。`来源` 不是装饰：它决定这条能不能进提示词。"""

    q: str
    a: str
    #: `模型常识` / `用户设定` / `unknown`（模型明确说不知道）
    #: ⚠ 不允许出现"看起来很权威"的空话
    # [EN] `模型常识` / `用户设定` / `unknown` (the model explicitly does not know).
    # [EN] ⚠ Empty-but-authoritative-sounding text is not allowed.
    src: str = '模型常识'

    @property
    def usable(self) -> bool:
        """能不能拿来画图。`unknown` 与空答案都不能。
            English: Whether this can be used for drawing; `unknown` and empty answers cannot.
        """
        return self.src != 'unknown' and len(str(self.a or '').strip()) >= 4


@dataclass
class Finding:
    """一个建筑传统的查资料结果（也是落盘单位）。
        English: The research result for one architectural tradition (also the unit written to disk).
    """

    style_key: str
    answers: list[Answer] = field(default_factory=list)
    made_at: str = ''
    model: str = ''
    #: 数据来源说明（"本机模型常识，未联网核验" 这类）。**必须诚实**。
    # [EN] Provenance note ("local model knowledge, not verified online"). **Must be honest.**
    note: str = ''

    def usable_answers(self) -> list[Answer]:
        return [x for x in self.answers if x.usable]

    def as_text(self, limit: int = 6) -> str:
        """拼成一段能直接进提示词的文本（**只放可用的**，并标明来源）。

        ★ 为什么标来源：模型看到"（模型常识）"就知道这条可以质疑；看到"（用户设定）"
          就知道必须遵守。混在一起不标，它会把两者当成同等权威。
        [EN] Render into prompt-ready text, **usable answers only**, each with its provenance.
        [EN] ★ Why label it: seeing "(model knowledge)" tells the model this line is challengeable,
        [EN] while "(user setting)" means it must be obeyed. Unlabelled and merged, it treats both as
        [EN] equally authoritative.
        """
        rows = self.usable_answers()[:limit]
        if not rows:
            return ''
        return '\n'.join(f'- {r.q}\n  → {r.a}（{r.src}）' for r in rows)


# ══════════════════════════════════════════════════════════════════════
#  一、要问什么
# [EN] 1. What to ask
# ══════════════════════════════════════════════════════════════════════
def questions(m: WS.Match, *, have: str = '', limit: int = MAX_Q) -> list[str]:
    """这一轮该去查什么（`worldstyle.needs_research` 的上限版）。

    ★ 已落盘过的答案会进 `have`，于是**同一件事不会被反复查**（省的是真金白银）。
    [EN] What to research this round (a capped `worldstyle.needs_research`). ★ Answers already on
    [EN] disk go into `have`, so **the same thing is never researched twice** (that is real money).
    """
    # ★★★ 2026-10-27（用户）：先确定"这座城照着哪张图来"，再问房子怎么盖。
    #   有原型 ⇒ 按那张历史地图的要素与路网画；无原型 ⇒ 检索"类似地区 + 类似时代"再改。
    # [EN] ★★★ 2026-10-27 (the user): settle "which map is this town based on" before asking how
    #   the houses are built. With a prototype, follow that historical map; without one, search a
    #   similar region in a similar period and adapt it by the same logic.
    rest = WS.needs_research(m, have=have)[:max(1, int(limit)) - 1]
    return [PROTO_Q] + rest


def build_prompt(style: WS.Style, qs: list[str], *, setting: str = '') -> list[dict]:
    """把"要查的几条"拼成一次模型调用。

    ★ 一次问完，不是一条一问：这几条本来就是一个语境（"这种建筑怎么盖"），
      分开问等于把同一段背景重复五遍（前缀不复用 ⇒ 五次全额计费）。
    ★ 硬要求"不知道就写 unknown"：模型默认会**编一个像样的答案**，
      而编出来的建筑常识会一路变成图上的墙和门。
    [EN] Turn the pending questions into a single model call. ★ All at once, not one by one: they
    [EN] share one context ("how is this kind of building built"), and asking separately repeats the
    [EN] same background five times (no prefix reuse => five full-price calls). ★ Require "write
    [EN] unknown if you do not know": by default the model **invents a plausible answer**, and invented
    [EN] building facts become walls and doors on the map.
    """
    sys_msg = (
        '你是建筑考据助手，只回答与**建筑与空间布局**有关的客观常识。\n'
        '规则：\n'
        '1. 只写你能确定的内容；不确定就写 `unknown`，**不要编**。\n'
        '2. 每条不超过 60 字，写具体做法（几进、门在哪面墙、主厅与厨房的位置关系），'
        '不写形容词。\n'
        '3. 只输出 JSON 数组，每项 `{"q": "原问题", "a": "答案或 unknown"}`。\n'
    )
    if setting.strip():
        sys_msg += f'\n这本书已有的设定（供参考，与它冲突时以它为准）：\n{setting.strip()[:1200]}\n'
    user = (f'建筑类型：{style.名}\n依据：{style.依据}\n\n'
            '请回答下面几个问题：\n'
            + '\n'.join(f'{i}. {q}' for i, q in enumerate(qs, 1)))
    return [{'role': 'system', 'content': sys_msg},
            {'role': 'user', 'content': user}]


def parse(raw, style_key: str, qs: list[str], *, model: str = '') -> Finding:
    """把模型输出解析成 `Finding`。**坏一条丢一条**，绝不整体失败。

    Args:
        raw: 模型返回值（JSON 数组 / 带 ``` 的代码块 / 纯文本都试一遍）。
        style_key: 属于哪个档案。
        qs: 当时问的问题（模型漏答的按 `unknown` 补，避免"少一条就当没问过"）。

    ★ 模型漏答的那条要**补成 unknown**：不补的话，下次 `questions()` 不会重问它，
      于是那条疑问**永久消失**（而用户看到的只是"这栋楼看着怪"）。
    [EN] Parse model output into a `Finding`, dropping bad items individually rather than failing
    [EN] wholesale. ★ Questions the model skipped become `unknown`: otherwise `questions()` will not
    [EN] ask again and that doubt **disappears forever** (the user only sees "this building looks
    [EN] off").
    """
    rows: list = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, str):
        txt = raw.strip()
        m = re.search(r'```(?:json)?\s*(.+?)\s*```', txt, re.S)
        if m:
            txt = m.group(1)
        i, j = txt.find('['), txt.rfind(']')
        if 0 <= i < j:
            txt = txt[i:j + 1]
        try:
            got = json.loads(txt)
            rows = got if isinstance(got, list) else []
        except (ValueError, TypeError):
            rows = []

    got: dict[str, str] = {}
    for it in rows:
        if not isinstance(it, dict):
            continue
        q = str(it.get('q') or it.get('问') or '').strip()
        a = str(it.get('a') or it.get('答') or '').strip()
        if q:
            got[q] = a

    out = Finding(style_key=str(style_key or ''), model=str(model or ''),
                  made_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
                  note='本机模型常识，未联网核验；冲突时以设定集为准')
    for q in qs:
        # 允许模型改写字面：先精确匹配，再按前 6 字模糊匹配（它常把问题缩写成短句）
        # [EN] Allow rewording: exact match first, then fuzzy on the first six characters (models
        # [EN] often shorten the question).
        a = got.get(q, '')
        if not a:
            head = q[:6]
            a = next((v for k, v in got.items() if head and head in k), '')
        a = str(a or '').strip()
        if not a or a.lower() in ('unknown', '未知', '不知道', 'n/a', '不确定'):
            out.answers.append(Answer(q=q, a='', src='unknown'))
        else:
            out.answers.append(Answer(q=q, a=a[:200], src='模型常识'))
    return out


# ══════════════════════════════════════════════════════════════════════
#  二、落盘 / 读回（这就是"提供后续参考"）
# [EN] 2. Save / load (this is what "reference for later" means)
# ══════════════════════════════════════════════════════════════════════
def skill_dir(style: WS.Style, root: Path | str) -> Path:
    """这个档案的技能目录：`<root>/地图-<名去括号>`。

    ⚠ 目录名要去掉括号里的话：`地图-现代（公寓／办公楼／城市）` 这种名字里有全角括号，
      Windows 上虽然能建，但**批量脚本/glob 匹配时很容易踩到**（本项目有过教训）。
      所以只用「名」里括号之前的部分。
    [EN] The skill directory for this profile: `<root>/地图-<name without parentheses>`. ⚠ Strip the
    [EN] parenthesised part -- full-width parentheses in a directory name are legal on Windows but
    [EN] trip bulk scripts and globs (learned here before). Use only what precedes the bracket.
    """
    base = re.split(r'[（(]', str(style.名 or style.key))[0].strip() or style.key
    return Path(root) / f'{PREFIX}{base}'


def save(f: Finding, style: WS.Style, root: Path | str) -> Path | None:
    """把一个 `Finding` 落成技能（`SKILL.md` + `资料.json`）。返回目录，失败返回 `None`。

    ★ 失败**不抛**：这是一条增强通道，它挂了不该让这一轮推演失败（最坏结果是下次再查一遍）。
    ★ 两份文件各有分工：
        `SKILL.md` —— 给人/模型看的**说明**（也供 `skills.registry` 路由）；
        `资料.json` —— 给程序读的**结构**（`load()` 用）。
      只写一份都不行：只写 md 程序读不回来，只写 json 技能库扫不到。
    [EN] Write a `Finding` as a skill (`SKILL.md` + `资料.json`), returning the directory or `None`.
    ★ Never raises: this is an enhancement path and must not fail the round (worst case, research
    [EN] again next time). ★ Two files with distinct jobs: `SKILL.md` is the **explanation** for humans
    [EN] and models (and what `skills.registry` routes on), `资料.json` is the **structure** the
    [EN] program reads back. One alone will not do: md-only cannot be read back, json-only is not
    [EN] scanned by the skill library.
    """
    try:
        d = skill_dir(style, root)
        d.mkdir(parents=True, exist_ok=True)
        (d / '资料.json').write_text(
            json.dumps({'风格': f.style_key, '风格名': style.名,
                        '问答': [{'问': a.q, '答': a.a, '来源': a.src} for a in f.answers],
                        '时间': f.made_at, '模型': f.model, '说明': f.note},
                       ensure_ascii=False, indent=2), encoding='utf-8')
        (d / 'SKILL.md').write_text(_markdown(f, style), encoding='utf-8')
        return d
    except Exception as exc:                                  # noqa: BLE001
        _LOG.warning('地图资料落盘失败（不影响推演）：%r', exc)
        return None


def load(style: WS.Style, root: Path | str) -> Finding | None:
    """读回已落盘的资料。没有/读坏都返回 `None`（调用方当作"还没查过"）。
        English: Read saved research back; missing or corrupt returns `None` (the caller treats it as
        "not researched yet").
    """
    try:
        p = skill_dir(style, root) / '资料.json'
        if not p.is_file():
            return None
        d = json.loads(p.read_text(encoding='utf-8'))
        rows = d.get('问答') or []
        return Finding(style_key=str(d.get('风格') or style.key),
                       answers=[Answer(q=str(x.get('问') or ''), a=str(x.get('答') or ''),
                                       src=str(x.get('来源') or '模型常识'))
                                for x in rows if isinstance(x, dict)],
                       made_at=str(d.get('时间') or ''), model=str(d.get('模型') or ''),
                       note=str(d.get('说明') or ''))
    except Exception:                                         # noqa: BLE001
        return None


def _markdown(f: Finding, style: WS.Style) -> str:
    """技能说明书（frontmatter 供 `skills.registry` 路由，正文供人读）。

    ★ `触发关键词` 要放**建筑构件**（堂屋/壁炉/气闸…），不要放"地图""画图"这种泛词 ——
      泛词会把所有画图请求都路由到这里，等于没有路由。
    [EN] The skill document (frontmatter for `skills.registry` routing, body for humans).
    ★ `触发关键词` must be **building elements** (堂屋/壁炉/气闸...), never generic words like
    [EN] "map"/"draw" -- generic words route every drawing request here, i.e. no routing at all.
    """
    kws = list(dict.fromkeys(
        [style.名, style.key] + [w for w in (style.强词 or ())][:8]
        + [w for w in (style.主厅词 or ())][:3]))
    lines = ['---',
             f'名称: 地图·{style.名}',
             '版本: 1.0',
             '分类: 建筑与空间',
             '触发关键词:']
    lines += [f'  - {k}' for k in kws if k]
    lines += ['用途: 画这一类型的建筑与街巷时，用这里的建筑常识约束布局（房间次序、主次比例、门窗位置）。',
              '输入: 地点名单 + 各自说明',
              '输出: 可用的建筑常识条目（含来源）',
              '调用工具: []',
              '---', '',
              f'# 地图·{style.名}', '',
              f'**依据**：{style.依据}', '',
              '## 这份资料是怎么来的', '',
              f'- 生成时间：{f.made_at or "（未记录）"}',
              f'- 模型：{f.model or "（未记录）"}',
              f'- 说明：{f.note or "（未记录）"}', '',
              '> ⚠ 这里的条目来自**模型常识**，不是测绘数据。它用于决定"房间怎么排、',
              '> 谁挨着谁、门窗在哪面墙"，**不用于编造尺寸**（我们没有真实尺寸）。',
              '']
    rows = f.usable_answers()
    # ★★★ 2026-10-27（用户）：「如果地图有真实原型 则先去找这个城市对应时间的历史真实地图…
    #   如果没有真实原型 是架空历史 则先去检索类似地点类似地区和时间的地图」
    #   ⇒ **原型单独成节、排在最前**。它决定"这张图照着什么画"，比任何细节都重要：
    #     后面的房间次序、开间数都只是它的补充。混在"已知条目"里会被当成又一条细节。
    # [EN] ★★★ 2026-10-27 (the user): "if the map has a real prototype, first find a historical map of
    # [EN] that town at that period... if it is invented history, first search maps of similar
    # [EN] places/regions and periods". => The prototype gets **its own section, first**: it decides what
    # [EN] this map is based on, which outweighs any detail, and burying it among "已知条目" would make
    # [EN] it read as one more detail.
    proto = next((a for a in rows if a.q == PROTO_Q), None)
    if proto is not None:
        lines += ['## 一、地图原型（先看这个）', '',
                  '画图**先按这条来**：它是这座城的底图依据。', '',
                  proto.a, '',
                  f'*来源：{proto.src}*', '']
        rows = [a for a in rows if a is not proto]
    if rows:
        lines += ['## 二、建筑与街巷细节' if proto is not None else '## 已知条目', '']
        for a in rows:
            lines.append(f'### {a.q}')
            lines.append('')
            lines.append(a.a)
            lines.append(f'')
            lines.append(f'*来源：{a.src}*')
            lines.append('')
    else:
        lines += ['## 已知条目', '',
                  '（这一轮**一条都没查回来** —— 模型对这些问题都答了 `unknown`。）', '',
                  '⚠ 不要因此编造。要么按 `worldstyle` 档案里的默认词表画（会标注"兜底"），',
                  '要么让作者在设定集里补一句建筑描述。', '']
    return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════
#  三、画完之后：把**这一轮实测到什么**也沉下来
# [EN] 3. After drawing: also sink what this round actually measured
# ══════════════════════════════════════════════════════════════════════
def plan_digest(prog) -> str:
    """把一份任务书压成**一段可复用的描述**（给下一次同类建筑当参考）。

    ★ 为什么要这一步（用户：「绘制之后相关数据资料还需要落地到skills」）：
      光存"查来的常识"不够 —— 真正有用的是**这本书实际画成了什么样**：
      几个空间、谁在哪层、哪两间必须挨着、院子/中庭叫什么。
      下一次画同一类建筑时，这段直接能当**先例**用（"上次是这么排的"）。
    ★ 只写**结构**，不写坐标：坐标是这一次的构图（见 `roomplan` 的说明）。
    [EN] Compress a program into a **reusable description** for the next building of this kind.
    ★ Why (the user: "after drawing, the data should also land in skills"): saving researched
    [EN] generalities is not enough -- what is actually useful is **how this book came out**: how many
    [EN] spaces, which floor each is on, which pairs must touch, what the courtyard is called. Next
    [EN] time it serves as a **precedent**. ★ Structure only, never coordinates (those are this
    [EN] composition; see `roomplan`).
    """
    try:
        d = prog.to_dict()
    except Exception:                                         # noqa: BLE001
        return ''
    by_floor: dict = {}
    for s in d.get('空间') or []:
        if s.get('归属'):        # 陈设不参与"房间怎么排"
            continue
        by_floor.setdefault(int(s.get('层') or 1), []).append(
            f"{s.get('名称')}{'（见天）' if s.get('见天') else ''}"
            f"{'·面积' + str(round(float(s.get('面积') or 0), 1)) if s.get('面积') else ''}")
    lines = [f"地点：{d.get('地点') or '（未命名）'}",
             f"入口：{d.get('入口') or '（未定）'}（街面在{d.get('街面') or '未记录'}侧）"]
    for fl in sorted(by_floor):
        tag = f'B{-fl}' if fl < 0 else f'{fl}层'
        lines.append(f'{tag}：' + '、'.join(by_floor[fl]))
    adj = d.get('邻接') or []
    if adj:
        lines.append('必须相邻：' + '；'.join(f'{a}—{b}' for a, b in adj))
    side = d.get('并排') or []
    if side:
        lines.append('必须并排：' + '；'.join('+'.join(g) for g in side))
    return '\n'.join(lines)


def save_precedent(prog, root: Path | str) -> Path | None:
    """把 `plan_digest` 追加到该风格技能目录的 `先例.md`（**追加，不覆盖**）。

    ★ 为什么要追加：同一类建筑在一本书里会出现很多次（这条街上的每一间铺子），
      每一次都是一个具体样本。覆盖只留一份 ⇒ 下次只剩最后一栋作参考，前面的全丢。
    ★ 但也要**封顶**：不封的话会无限增长（每次推演都加一段）。到 40 段就只留最近的 40 段。
    [EN] Append `plan_digest` to `先例.md` in that style's skill directory (**append, never
    [EN] overwrite**). ★ Why append: one kind of building appears many times in a book (every shop on
    [EN] that street), and each is a concrete sample; overwriting keeps only the last one. ★ But it
    [EN] must be capped: unbounded growth adds a block every round, so keep only the most recent 40.
    """
    try:
        st = prog.style() if hasattr(prog, 'style') else WS.FALLBACK
        d = skill_dir(st, root)
        d.mkdir(parents=True, exist_ok=True)
        p = d / '先例.md'
        digest = plan_digest(prog)
        if not digest:
            return None
        head = '# 先例（这本书实际画出来的布局）\n\n> 这些是**已发生的构图**，不是规范。\n' \
               '> 下一次画同类建筑时可以参照，但**不要照抄名字** —— 换了地方就该换名字。\n\n'
        old = p.read_text(encoding='utf-8') if p.is_file() else head
        blocks = [b for b in old.split('\n---\n') if b.strip()]
        blocks.append(f'\n---\n\n### {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n{digest}\n')
        # 头 + 最近 40 段
        keep = [blocks[0]] + blocks[1:][-40:] if len(blocks) > 1 else blocks
        p.write_text('\n---\n'.join(keep), encoding='utf-8')
        return p
    except Exception as exc:                                  # noqa: BLE001
        _LOG.warning('先例落盘失败（不影响推演）：%r', exc)
        return None


# ══════════════════════════════════════════════════════════════════════
#  四、一站式：判风格 → 有存档就读 → 没存档才去查 → 落盘
# [EN] 4. One-stop: detect -> read if saved -> otherwise research -> save
# ══════════════════════════════════════════════════════════════════════
async def ensure(m: WS.Match, *, root: Path | str, ask=None, setting: str = '',
                 genre: str = '') -> Finding | None:
    """保证"这种建筑我们有一份资料"。已有就直接返回，没有才去查。

    Args:
        m: `worldstyle.detect()` 的结果。
        root: 技能根目录（`CFG.resolved('SKILLS_DIR')`）。
        ask: 可注入的 `async (tier, messages, **kw) -> Reply`。**不给就不查**
             （判据用假 `ask`，产品传真的 `llm.replies.ask`）。
        setting: 这本书的设定摘要（最可信的那一层，会一起喂给模型）。
        genre: 题材（只作弱提示）。

    Returns:
        `Finding`（可能是从盘上读的），或 `None`（没查、也没存档）。

    ★★ 为什么"不给 `ask` 就不查"：这条通道会在**推演过程中**被调到，
      而推演过程中每一次网络调用都要用户付钱。默认不联网 = 默认安全；
      想用就显式传 `ask`。判据正是靠这一点可以在离线下测完整条流程。
    [EN] Ensure we have research for this kind of building: reuse what is on disk, research only
    [EN] when absent. ★★ Why "no `ask` means no research": this path is called **during a
    [EN] simulation**, and every network call there costs the user money. Default offline = default
    [EN] safe; pass `ask` explicitly to enable it. (That is also how the criteria test the whole flow
    [EN] offline.)
    """
    saved = load(m.style, root)
    if saved is not None:
        # ★★ 只要**查到过**就直接用，**不因为"答案不好"再查一遍**。
        #
        #   第一版写的是 `if saved.usable_answers(): return saved` —— 于是"上次模型全答
        #   unknown"这一种会**每次都重查**，而每次都是一个真花钱的调用点。用户看到的是
        #   "跑了半天、钱花了、图还是那样"。
        #   模型说不知道就是不知道；反复问同一件事不会变出不存在的建筑常识。
        #   ⇒ 想重查只能**删掉那个技能目录**（用户可控、看得见）。
        # [EN] ★★ Use whatever was researched before; **never re-research just because the answers
        # [EN] were poor**. The first version returned only when `usable_answers()` was non-empty, so
        # [EN] "the model said unknown to everything" meant a fresh paid call **every round**, with
        # [EN] the user seeing "it ran forever, cost money, and the map looks the same". If the model
        # [EN] does not know, it does not know; asking again will not conjure building facts. => To
        # [EN] re-research, delete that skill directory (user-controlled and visible).
        return saved
    if ask is None:
        return saved
    qs = questions(m, have=(saved.as_text() if saved else ''))
    if not qs:
        return saved
    msgs = build_prompt(m.style, qs, setting=setting)
    try:
        rep = await ask('research', msgs, purpose='地图建筑考据',
                        want='text', max_tokens=1200, temperature=0.15)
        raw = getattr(rep, 'value', None) or ''
    except Exception as exc:                                  # noqa: BLE001
        _LOG.warning('建筑资料查询失败（按已有资料继续）：%r', exc)
        return saved
    f = parse(raw, m.style.key, qs, model=str(genre or ''))
    save(f, m.style, root)
    return f
