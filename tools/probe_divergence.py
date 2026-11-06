#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""**发散度探针**：同一部小说跑多次，剧情到底有多不一样。

★★★ 为什么需要这个工具（2026-10-19 用户把定位从「AI 写作工具」改成「推演工具」）
--------------------------------------------------------------------------------
用户原话：「每次推演可以发挥自己的作用，给出剧情有可能不同的推演结果，这样的话
最大的程度发挥跟普通 AI 写作工具不一样的地方」。

那个诉求**必须能量**，否则一切「我加了自由度」都是自说自话。已有的度量全都量不到它：

| 已有指标 | 它量的是 | 为什么量不到「剧情不一样」 |
|---|---|---|
| `metrics.repeat_4gram` | **同一篇之内**的重复 | 两篇之间无关 |
| `metrics.hygiene_score` | 文本卫生（像不像人写的） | 两篇都 90 分也可以是同一部戏 |
| `difflib` 文字相似度 | 字面重合 | **实测 9.7%** —— 看起来天差地别，实际是同一部戏换了词 |

⚠ 那个 9.7% 正是最危险的一种「假发散」：字面几乎不重合，读者读起来却是
「又来一遍」。所以这个探针量的不是字，是**骨架**：

  ① **文字重合**（字）—— 参考值，不是结论；
  ② **骨架重合**（谁·做了什么类型的事，顺序）—— 这才是「剧情是否不同」；
  ③ **事件重合**（导演投的那几下是不是同一类）—— 转折是否来自同一个套路；
  ④ **主导权**（谁说得最多）—— 人物关系有没有真的变化；
  ⑤ **收束点**（结束时局面是什么样）—— 结局是否收敛到同一个地方。

判定：骨架重合 ≥ 0.70 或事件重合 ≥ 0.60 ⇒ **假发散**（换词不换戏）。

用法
----
    # 目录里每个子目录是一次跑（含 cases/<case>/transcript.jsonl）
    python tools/probe_divergence.py novel_bench/results/ykg1000 novel_bench/results/ykg1000b

    # 或者直接给 run 根目录（自动找它的 cases/*）
    python tools/probe_divergence.py novel_bench/results/*/

⚠ 只读产物，不跑推演、不改任何东西 —— 它是「看结果」的工具，
  要跑新的一次用 `python -m novel_bench.bench.cli run --case <id> --ticks <n> --run-id <新名>`。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

#: 参与「骨架」的条目类型。`crew/stage/note` 是过程日志（每次都一样），
#: `ambient` 是环境句（属于文风不属剧情），都不能进骨架 —— 它们会稀释信号。
# [EN] Entry kinds that form the "skeleton". `crew/stage/note` are process logs (identical every
# [EN] run) and `ambient` is scenery (style, not plot) -- including them dilutes the signal.
SKELETON_KINDS: tuple[str, ...] = ('event', 'dialogue', 'action', 'aside')

#: 判定的三档（不是二分类 —— 实测就落在中间那一档，二分会把它误判成"真发散"）。
#: · ≥ 70% 骨架（或 ≥60% 事件）⇒ **假发散**：换词不换戏；
#: · 50%–70% ⇒ **半发散**：主导权/语气换了，**事件骨架没换**（读者会觉得"眼熟"）；
#: · < 50% ⇒ **真发散**。
# [EN] Three bands, not a binary -- the measurement landed in the middle one and a binary test
# [EN] would call it "true divergence". ≥70% skeleton is fake, 50-70% is half, <50% is real.
SKELETON_FAKE = 0.70
EVENT_FAKE = 0.60
SKELETON_HALF = 0.50


def _read_jsonl(p: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _body(run_dir: Path, case: str) -> str:
    """小说正文（去掉文件头的元信息）。"""
    p = run_dir / 'cases' / case / 'novel.md'
    try:
        t = p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    lines = t.splitlines()
    i = next((k for k, ln in enumerate(lines) if ln.startswith('## ')), 0)
    return '\n'.join(lines[i:]).strip()


def _cjk(s: str) -> int:
    return len(re.findall(r'[\u4e00-\u9fff]', s))


def _names(rows: list[dict]) -> list[str]:
    """从轨迹里**自己认出**有哪些人物（不读设定、不读存档）。

    做法：所有行里 `X：` / `X心想：` 的 X 就是人名候选。
    ⚠ 为什么不从设定读：这个探针只吃**产物**，这样它能用在任何一次跑上
      （包括别人拷过来的结果目录）。
    [EN] Recognize the cast **from the transcript itself** (no settings, no save): the `X` in
    [EN] `X:` / `X thinks:` is a name candidate. ⚠ Not read from settings, so the probe works on any
    [EN] run directory, including one copied from elsewhere.
    """
    seen: Counter = Counter()
    for d in rows:
        t = str(d.get('text') or '')
        # ⚠ 必须用 **lookahead** 分开取：直接写 `([\u4e00-\u9fff]{2,4})(?:心想)?[：:]`
        #   会贪婪吃成「岛村心想」这个"五字人名"（实测出现过：主导权那一行里
        #   `岛村` 与 `岛村心想` 被算成两个人）。lookahead 保证「心想」不被吃进名字。
        # [EN] Use a **lookahead**: the direct pattern greedily produced a five-character "name"
        # [EN] `岛村心想` (measured: `岛村` and `岛村心想` counted as two people).
        for mt in re.finditer(r'([\u4e00-\u9fff]{2,4})(?=心想[：:])', t):
            seen[mt.group(1)] += 1
        for mt in re.finditer(r'([\u4e00-\u9fff]{2,4})[：:]', t):
            # ⚠ 贪婪匹配会把「岛村心想」整体吃进来（`{2,4}` 正好够，且后面就是冒号）
            #   ⇒ 名单里同时有「岛村」和「岛村心想」，主导权统计一半一半。
            #   这里**剥掉尾部标记词**，剥完不足 2 字就丢。
            # [EN] Greedy matching swallows `岛村心想` whole (4 chars, followed by a colon), so the
            # [EN] cast had both `岛村` and `岛村心想` and the dominance count split in half. Strip the
            # [EN] marker suffix; discard if under 2 chars.
            nm = re.sub(r'(心想|低声|自语|心道)$', '', mt.group(1))
            if len(nm) >= 2:
                seen[nm] += 1
    # 出现 2 次以上才算人名（一次性的多半是"他说："这类）
    return [n for n, c in seen.most_common(12) if c >= 2 and n not in ('他说', '她说', '心想', '低声')]


def _who_of(text: str, names: list[str]) -> str:
    """这一行是**谁**做的（认不出就返回空串，由调用方决定怎么办）。

    三行形态各吃一套（产物里就长这样）：
      · `驹子：（向岛村）嗯……`      → 冒号左边
      · `岛村心想：这影子……`        → "心想"左边
      · `（岛村坐在她对面的席上…）`   → 括号内靠前的人名
    ⚠ 第三种的"靠前"要用**名字长度降序**匹配：否则「岛村」会被「岛」这种前缀抢先。
    [EN] Which character did this line. Three shapes: left of the colon / left of "thinks" / the
    [EN] earliest known name inside the leading bracket. ⚠ Match names **longest first**, otherwise a
    [EN] short prefix wins.
    """
    t = ' '.join(str(text or '').split())
    if not t:
        return ''
    head = t[:24]
    for n in sorted(names, key=len, reverse=True):
        if head.startswith(n) or head.startswith(f'（{n}') or head.startswith(f'({n}'):
            return n
    # `XX心想：` 出现在任意位置（有些行前面带场景前缀）——同样要 lookahead，别把「心想」吃进名字
    mt = re.search(r'([\u4e00-\u9fff]{2,4})(?=心想)', t)
    if mt and mt.group(1) in names:
        return mt.group(1)
    return ''


def _skeleton(rows: list[dict], names: list[str]) -> list[tuple[str, str]]:
    """骨架：**(谁, 做了什么类型的事)** 的顺序。

    ⚠ 故意**不含文本内容** —— 含了就成了「文字相似度」，而我们正是要绕开它：
      两版可以字面完全不同（9.7%），骨架完全一样。
    ⚠⚠ **`transcript.jsonl` 里的 `who` 字段一直是空的**（人物名在 `text` 前缀里），
      第一版直接读 `who` ⇒ 骨架 0 段 ⇒ LCS 0 ⇒ 判成「真发散」——
      差一点又是「没数据 ⇒ 量不到 ⇒ 绿」。现在从文本认，且认不出就报数（见 `main`）。
    [EN] Skeleton: the sequence of **(who, what kind of thing)**. ⚠ Deliberately **without the
    [EN] text**: including it becomes "text similarity", exactly what we bypass.
    [EN] ⚠⚠ The `who` field in `transcript.jsonl` is **always empty** (the name sits in the text),
    [EN] so the first version got a 0-segment skeleton => LCS 0 => "true divergence" -- almost the
    [EN] "no data => nothing measured => green" trap again. Now it parses the text and reports misses.
    """
    out: list[tuple[str, str]] = []
    for d in rows:
        k = str(d.get('kind') or '')
        if k not in SKELETON_KINDS:
            continue
        who = _who_of(str(d.get('text') or ''), names)
        if not who:
            continue
        out.append((who, k))
    return out


def _lcs_ratio(a: list, b: list) -> float:
    """最长公共子序列占**较短者**的比例（骨架重合度）。"""
    if not a or not b:
        return 0.0
    n, m = len(a), len(b)
    # 骨架一般几十条，二维 DP 完全够（不做优化，可读优先）
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = (dp[i + 1][j + 1] + 1) if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    return dp[0][0] / min(n, m)


def _event_kinds(rows: list[dict]) -> list[str]:
    """导演投的那几次「事件」的**类型**（从文字里认关键词）。

    ⚠ 不使用导演自己写的 `event_type`：那要读存档，而这里只吃产物。
      关键词法是粗的，但它**方向正确** —— 我们只要判「两次是不是同一个套路」。
    [EN] The **types** of events the director dropped (keyword-matched from the text).
    [EN] ⚠ Not the director's own `event_type` (that lives in the save); this reads artifacts only.
    [EN] Keyword matching is crude but directionally right -- we only need "same routine or not".
    """
    buckets = {
        '来人': ('走进', '拉开', '推门', '进来', '进来', '步声', '脚步声', '出现在', '停在门口'),
        '送物': ('送', '递', '端', '倒酒', '添', '搁在', '放在门口'),
        '传话': ('传话', '叫', '唤', '吩咐', '说有人', '告诉他'),
        '天象': ('雪', '风', '雨', '天亮', '天黑', '冷'),
        '声响': ('响', '敲', '碎', '喊', '叫', '哭声'),
        '静默': ('沉默', '不出声', '没答', '半晌', '空气'),
    }
    out: list[str] = []
    for d in rows:
        if str(d.get('kind') or '') != 'event':
            continue
        t = str(d.get('text') or '')
        hit = next((name for name, kws in buckets.items() if any(k in t for k in kws)), '其他')
        out.append(hit)
    return out


def _dominance(rows: list[dict], names: list[str]) -> list[tuple[str, int]]:
    """谁在场面上最重（台词 + 动作 + 心声的条数）。用来判「主导权有没有换人」。"""
    c: Counter = Counter()
    for d in rows:
        if str(d.get('kind') or '') not in SKELETON_KINDS:
            continue
        who = _who_of(str(d.get('text') or ''), names)
        if who:
            c[who] += 1
    return c.most_common(4)


def _tail(rows: list[dict], n: int = 6) -> list[str]:
    """最后几拍发生了什么（收束点）。"""
    out = [str(d.get('text') or '')[:40] for d in rows
           if str(d.get('kind') or '') in SKELETON_KINDS and str(d.get('text') or '').strip()]
    return out[-n:]


def load_run(path: Path) -> dict | None:
    """读一次跑，返回各项指标。找不到产物就返回 None（**不猜**）。"""
    case = None
    if (path / 'cases').is_dir():
        subs = [p for p in (path / 'cases').iterdir() if p.is_dir()]
        if subs:
            case = subs[0].name
    elif path.name and (path / 'transcript.jsonl').is_file():
        case = path.name
        path = path.parent.parent
    if not case:
        return None
    rows = _read_jsonl(path / 'cases' / case / 'transcript.jsonl')
    if not rows:
        return None
    names = _names(rows)
    return {
        'name': path.name,
        'case': case,
        'rows': rows,
        'body': _body(path, case),
        'names': names,
        'skel': _skeleton(rows, names),
        'events': _event_kinds(rows),
        'dom': _dominance(rows, names),
        'tail': _tail(rows),
    }


#: 骨架少于这个段数就**不下结论**（0 对 0 的 LCS 也是 0，会被读成"完全不同"）。
# [EN] Below this many skeleton segments we **refuse to conclude** (LCS of 0 vs 0 is also 0 and
# [EN] would read as "completely different").
SKELETON_MIN = 3


def compare(a: dict, b: dict) -> dict:
    """两次跑之间的三项差异。`valid=False` 表示**量不到**，不是「没有差异」。"""
    text_sim = SequenceMatcher(None, a['body'], b['body']).ratio() if a['body'] and b['body'] else 0.0
    valid = len(a['skel']) >= SKELETON_MIN and len(b['skel']) >= SKELETON_MIN
    skel_sim = _lcs_ratio(a['skel'], b['skel']) if valid else 0.0
    # 事件：集合重合（顺序不重要 —— 事件是插进来的，位置本来就会浮动）
    ea, eb = a['events'], b['events']
    ev_sim = (len(set(ea) & set(eb)) / max(1, len(set(ea) | set(eb)))) if (ea or eb) else 0.0
    return {'text': text_sim, 'skeleton': skel_sim, 'events': ev_sim, 'valid': valid,
            'len_a': _cjk(a['body']), 'len_b': _cjk(b['body']),
            'skel_a': len(a['skel']), 'skel_b': len(b['skel'])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='同一部小说多次跑的「发散度」探针')
    ap.add_argument('runs', nargs='+', help='每次跑的目录（含 cases/<case>/），或 cases/<case> 本身')
    ap.add_argument('--json', action='store_true', help='只输出 JSON（给判据/脚本用）')
    args = ap.parse_args(argv)

    runs = [r for r in (load_run(Path(x)) for x in args.runs) if r]
    if len(runs) < 2:
        print('需要至少两次跑（各给一个目录）。', file=sys.stderr)
        return 2

    pairs = [(i, j) for i in range(len(runs)) for j in range(i + 1, len(runs))]
    rows = [compare(runs[i], runs[j]) | {'a': runs[i]['name'], 'b': runs[j]['name']}
            for i, j in pairs]

    if args.json:
        print(json.dumps({'runs': [{'name': r['name'], 'case': r['case'],
                                    'chars': _cjk(r['body']), 'events': r['events'],
                                    'dominance': r['dom']} for r in runs],
                          'pairs': rows}, ensure_ascii=False, indent=2))
        return 0

    print('═' * 68)
    print('  发散度探针 · 同一部小说多次跑，剧情到底有多不一样')
    print('═' * 68)
    for r in runs:
        print(f"\n【{r['name']}】case={r['case']} · 正文 {_cjk(r['body'])} 汉字 "
              f"· 骨架 {len(r['skel'])} 段")
        print(f"  主导：{', '.join(f'{w}×{n}' for w, n in r['dom'])}")
        print(f"  导演投的事件：{r['events'] or '（没投）'}")
        print(f"  收束点：{' / '.join(x[:18] for x in r['tail'][-3:])}")

    print('\n' + '─' * 68)
    print('  两两对比')
    print('─' * 68)
    fake = 0
    half = 0
    blind = 0
    for x in rows:
        if not x['valid']:
            blind += 1
            print(f"\n  {x['a']} vs {x['b']}（{x['len_a']} / {x['len_b']} 汉字）")
            print(f"    ⚠ **量不到**：骨架只有 {x['skel_a']} / {x['skel_b']} 段"
                  f"（少于 {SKELETON_MIN} 段不下结论）")
            print('      ⚠ 这一对**不算「真发散」**——0 对 0 也是 0%，会读成完全不同。')
            continue
        flag = ''
        if x['skeleton'] >= SKELETON_FAKE or x['events'] >= EVENT_FAKE:
            flag = '  ← **假发散**（换词不换戏）'
            fake += 1
        elif x['skeleton'] >= SKELETON_HALF:
            flag = '  ← **半发散**（人换了，事件骨架没换）'
            half += 1
        print(f"\n  {x['a']} vs {x['b']}（{x['len_a']} / {x['len_b']} 汉字）")
        print(f"    文字重合 {x['text']:6.1%}   ← 只说明措辞不同，**不是结论**")
        print(f"    骨架重合 {x['skeleton']:6.1%}   ← 这个才是「剧情像不像」"
              f"（{x['skel_a']} / {x['skel_b']} 段）")
        print(f"    事件重合 {x['events']:6.1%}   ← 转折是不是同一个套路")
        if flag:
            print(flag)

    print('\n' + '═' * 68)
    usable = len(rows) - blind
    if blind:
        print(f'  ⚠ {blind}/{len(rows)} 对**量不到**（骨架太少），已排除在结论之外。')
    if fake:
        print(f'  假发散 {fake}/{usable} 对 —— 读者会读出「又来一遍」，虽然每个字都不同。')
    if half:
        print(f'  半发散 {half}/{usable} 对 —— 谁主导、怎么说都换了，'
              f'但**事情还是那几件**（这是「像个写作工具」的根源）。')
    if not fake and not half and usable:
        print(f'  结论：{usable} 对全部真发散（骨架与事件都换了）。')
    if not usable:
        print('  结论：**没有一对是可判的** —— 先确认轨迹里有台词/动作条目。')
    print('  门槛：骨架 ≥70% 或 事件 ≥60% = 假发散；骨架 ≥50% = 半发散。')
    print('═' * 68)
    return 0 if usable else 3


if __name__ == '__main__':
    raise SystemExit(main())
