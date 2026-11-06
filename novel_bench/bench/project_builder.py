# -*- coding: utf-8 -*-
"""Turn one benchmark case into a runnable simulator project.

The simulator reads exactly nine files from ``<project>/设定集/`` (see
``sim/setup.load_settings``).  This module is the only place that knows how a
benchmark case maps onto them, which keeps the on-disk format in one spot.

Two deliberate choices:

1. ``剧情走向.md`` is written as 起/承/转/合.  The app trims the plot line at
   「承」 before it reaches any prompt (``sim/setup._plot_setup_only``), so the
   ground-truth continuation sits in 承 and **cannot leak** into the run.  The
   recap sits in 起, which is exactly the part that *should* be visible.
2. Person cards keep the simulator's own field names (身份/性格/口癖/秘密/目标/
   红线).  Renaming them here would produce a project that assembles but runs
   with empty characters -- a silent failure this benchmark cannot afford.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .dataset import Case, Work


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _text(path: Path, body: str) -> None:
    """Write a `.md` setting the way the app writes it (yaml-dumped string).

    ``sim/setup._read_text_setting`` accepts both a plain markdown file and a
    yaml-dumped string; using the dumped form keeps byte-format parity with
    projects produced by the real ingest pipeline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _people(work: Work) -> list[dict]:
    """把 `bible.people` 搬成 `人物.yaml`。

    ★★★ 2026-10-21 补两处**漏搬的字段**（判据 J4 当场抓到）：
      · `知情者`（谁可以知道我的秘密）—— 漏了它，`PersonState.knows` 永远是空表，
        于是 `blind_spots()` 认为**所有人都不知道所有人的秘密**，
        "信息差 / 戏剧反讽"那整层（2026-10-18 专门做的）**空转**；
        而"不越过人物已知的信息边界"这句完成判据也就没有实体。
      · `需求`（want vs need 里的 need）—— 漏了它，人物只剩"想要什么"，
        弧光失去地基（Truby 那一维 2026-10-18 加进来，却从来没进过项目）。
    ⚠ 这正是本项目反复记的那条："**prompt 里写了 ≠ 生效**"——
      上游（yaml）写了、下游（项目文件）没搬，中间断一刀，看起来一切正常。

        English:
    Turn `bible.people` into `人物.yaml`.
        ★★★ 2026-10-21: two **missing fields** restored (criterion J4 caught it on the spot):
          · `知情者` (who may know my secret) -- without it `PersonState.knows` is forever empty, so
            `blind_spots()` concludes **nobody knows anyone's secret** and the whole
            "information asymmetry / dramatic irony" layer (built 2026-10-18) **idles**; the node
            criterion "do not cross the character's known information boundary" then has no
            substance. · `需求` (the "need" of want-vs-need) -- without it a character has only
            "what he wants", and the arc loses its foundation (added 2026-10-18, never wired in).
        ⚠ This is exactly the debt recorded repeatedly here: "**written in the prompt != in effect**"
          -- upstream (yaml) has it, downstream (project files) does not carry it, and everything
          looks fine.
    """
    out = []
    for p in work.bible.get("people") or []:
        p = p or {}
        row = {
            "姓名": str(p.get("姓名") or ""),
            "身份": str(p.get("身份") or ""),
            "性格": str(p.get("性格") or ""),
            "口癖": str(p.get("口癖") or ""),
            "秘密": str(p.get("秘密") or ""),
            "目标": str(p.get("目标") or ""),
            "红线": str(p.get("红线") or ""),
        }
        # 只在写了的时候搬（空表 / 空串不进项目文件，免得把"没写"变成"写了个空"）。
        # [EN] Only copy when present: an empty list/string must not turn "unset" into "set to empty".
        _knowers = [str(x).strip() for x in (p.get("知情者") or []) if str(x).strip()]
        if _knowers:
            row["知情者"] = _knowers
        _need = str(p.get("需求") or "").strip()
        if _need:
            row["需求"] = _need
        out.append(row)
    return out


def _places(work: Work) -> list[dict]:
    out = []
    for p in work.bible.get("places") or []:
        p = p or {}
        if not p.get("名称"):
            continue
        row = {"名称": str(p["名称"]), "说明": str(p.get("说明") or "")}
        if p.get("方位"):
            row["方位"] = str(p["方位"])
        if p.get("内里"):
            row["内里"] = list(p["内里"])
        out.append(row)
    return out


def _rules(work: Work, case: Case) -> str:
    style = work.style()
    lines = [f"# 顶级规则 · 《{work.title}》", ""]
    lines.append("## 世界铁律")
    for r in work.bible.get("rules") or []:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## 写法（这一段必须遵守）")
    lines.append(f"- 叙述视角：{style.get('pov', '第三人称限知')}；时态与语气照原著。")
    if style.get("sentence"):
        lines.append(f"- 句法：{style['sentence']}")
    if style.get("diction"):
        lines.append(f"- 用词：{style['diction']}")
    taboos = style.get("taboos") or []
    if taboos:
        lines.append("- 时代/世界禁忌词（一个字都不许出现）：" + "、".join(str(t) for t in taboos))
    # ══════════════════════════════════════════════════════════════
    # 语体：**一种语体，不许半文半白**（2026-10-20 实测补）
    # ══════════════════════════════════════════════════════════════
    # ★ 为什么原来没有：`agent/core.py:1371` 那条"不许夹文言词、不许半文半白"
    #   **只管台词**；分镜那条（`crew/agents.py`）也管台词。
    #   **叙述层一条约束都没有** —— 而用户读到的"半文半白"恰恰在叙述里：
    #       柳氏**西窗坐，白衣映灯**，布料上的暗绣**被暖黄的光勾出浅淡的轮廓**
    #   前半是砍掉"在/着"的文言四字句，后半是"被…勾出…轮廓"的现代翻译腔。
    # ★ 而且 `style.sentence` 只写"句子短、动词多、形容词少"是**纯方向**：
    #   模型要"短"，最省力的办法就是**砍虚词** ⇒ 砍成文言。
    #   这与 R56（"可以不接"没有配额）是同一种病：**只有方向、没有边界**。
    #   ⇒ 所以要成对地写：短 **可以**，靠砍冗余的东西短；**不许**靠砍虚词短。
    # [EN] Register: one register only, never half-classical half-modern. The existing
    # [EN] "no classical wording" rules apply to **dialogue only**; the narration layer had
    # [EN] none, which is exactly where the measured mixture appeared. And `sentence` was a
    # [EN] pure direction ("short, verb-heavy, few adjectives") -- the cheapest way to get
    # [EN] short is to drop function words, which lands you in classical Chinese.
    lines.append(
        "- **语体：全篇一种，叙述与对白都是同一种语体。不许半文半白。**")
    lines.append(
        "  · **不许靠砍虚词变短**：`柳氏西窗坐` ✗ → `柳氏在西窗下坐着` ✓；"
        "`忽闻`／`遂`／`乃`／`其`／`之` 这类词一个都不要；")
    # ★★★ 这一句**必须留着**（2026-10-25 补回来，`verify_reflexion` F11 守着它）。
    #   上一条写"这类词一个都不要"是**开区间**（"这类"指哪些？），
    #   模型最省力的读法是"所有看着文的都别用" ⇒ 把 `方才/为何/可还` 也一起杀掉，
    #   而那四个是**明清白话里本来就有的常用词**。产物会变得不像小说、像白话译文，
    #   实测过一次（"翻译腔 4→0、倒装 3→0，但正常白话也没了"）。
    #   这与"专杀真人"是同一类错误：判据/规则**宁可放过，不许误杀**。
    # [EN] ★★★ This sentence **must stay** (restored 2026-10-25; `verify_reflexion` F11 guards it).
    # [EN] The bullet above says "not one of these words" but "these" is an **open set** -- the
    # [EN] cheapest reading is "drop anything that sounds literary", which sweeps `方才/为何/可还`
    # [EN] away too, and those four are ordinary words in Ming-Qing vernacular. The output turns
    # [EN] into translated prose, measured once (translationese 4->0, inversion 3->0, normal
    # [EN] vernacular also gone). Same family as "killing only real humans": when in doubt, let it pass.
    lines.append(
        "  · ⚠ 但 `方才` `为何` `可还` `不曾` 是**明清白话里本来就有的**，可以用 —— "
        "别把正常白话一起杀掉。")
    lines.append(
        "  · **也不许用现代翻译腔充数**（`被…勾出…轮廓`／`一种…的存在`／"
        "`某种…的感觉`）—— 那是另一种假文采；")
    lines.append(
        "  · 自查：把任何一句念出来，**像一个人在讲一件事**就对了；"
        "像在念碑文、或者像在念译文，都不对。")
    return "\n".join(lines)


def _plot(work: Work, case: Case) -> str:
    """起 = recap (visible), 承 = ground truth (trimmed away by the app)."""
    setup = case.previously.strip() or case.scene_seed.strip()
    truth = "\n".join(f"· {b}" for b in case.beats)
    return (
        "【起】\n"
        f"{setup}\n"
        f"此刻：{case.scene_seed.strip()}\n\n"
        "【承】\n"
        f"{truth}\n\n"
        "【转】\n（此处之后原著另有发展，推演不必复刻）\n\n"
        "【合】\n（推演到此为止）\n"
    )


def _worldview(work: Work, case: Case) -> str:
    return (
        f"《{work.title}》（{work.author}，{work.country}，{work.year}）。\n"
        f"{work.bible.get('worldview', '').strip()}\n\n"
        f"【此刻】{case.story_time}，{case.place}。在场：{'、'.join(case.present)}。"
    )


def _genre_card(work: Work) -> dict:
    return {
        "类型": work.genres[0] if work.genres else "世情",
        "子类型": list(work.genres[1:]),
        "载体": work.medium,
        "国别": work.country,
        "一句话": work.representativeness.splitlines()[0][:120] if work.representativeness else "",
    }


def _style_card(work: Work) -> dict:
    s = work.style()
    return {
        "视角": s.get("pov", "第三人称限知"),
        "句法": s.get("sentence", ""),
        "用词": s.get("diction", ""),
        "禁忌": list(s.get("taboos") or []),
        "对白密度": s.get("dialogue", ""),
    }


def _writer_notes(work: Work) -> str:
    """**只给写作层的写法约束**（`style.notes`）—— 演员看不到的那一份。

    ★★★ 为什么必须单独一份（2026-10-21，用户点名）
    ------------------------------------------------------------------
    上一轮我把"某本书实测出来的写法约束"（茶/水/壶/灯每样最多复位三次、
    异常必须指向同一条线、掌柜的沉默不许只有一种形态）写进了 `style.notes`，
    而它随着 `顶级规则.md` → `WorldState.rules_text` → `world_prefix_stable()`
    **原样进了每一个演员的提示词**。

    问题是：**这些是"成品读起来该是什么样"的要求，不是演员能执行的动作**。
      · 「每样最多复位三次」—— 演员在一拍里没法数，他只会因此**不敢碰那只壶**；
      · 「异常必须指向同一条线」—— 那是作者的编织，不是人物该知道的；
      · 「沉默不许只有一种形态」—— 这一条**确实**该给演员（它是表演要求）。
    ⇒ 所以拆成两份文件：
      · `顶级规则.md`      = 世界铁律 + 写法（**演员和作家都读**）；
      · `写作层规则.md`    = `style.notes`（**只有作家读**：写样章 / 导出整理）。
    ⚠ 谁该读 notes 里某一条：问一句「这是**动作**还是**成品的样子**」。
      动作（沉默别只有一种形态）→ 放 `actor_notes`，也给演员；
      成品（每样最多复位三次）→ 放 `notes`，只给作家。
    ⚠ 两份文件都是**存在**的（哪怕空的也写一个标题），否则"文件不在"和
      "作者没写"分不清 —— 那是本项目吃过好几次的亏。
    [EN] **Writing-layer-only constraints** (`style.notes`) -- the half actors never see.
        ★★★ Why a separate file (named by the user, 2026-10-21): last round I put a book's measured
        writing constraints into `style.notes`, and it travelled `顶级规则.md` -> `rules_text` ->
        `world_prefix_stable()` **verbatim into every actor's prompt**.
        The problem: **these describe what the finished prose should read like, not actions an actor
        can perform.** "Each prop resets at most three times" -- an actor cannot count inside one
        beat; he only becomes afraid to touch the teapot. "Anomalies must point at one thread" -- that
        is the author's weaving, not something a character may know. "The shopkeeper's silence must
        not take one form" -- that one **does** belong to the actor (it is a performance note).
        => Split into two files: `顶级规则.md` = world laws + style (both actors and the writer read
        it); `写作层规则.md` = `style.notes` (writer only: sample chapter / export).
        ⚠ To decide where a note belongs, ask: is this an **action** or **what the finished thing
        looks like**? Actions go to `actor_notes`; finished-form requirements go to `notes`.
        ⚠ Both files always exist (even if just a heading) so that "file missing" and "author wrote
        nothing" stay distinguishable -- a lesson this project has paid for several times.
    """
    notes = [str(x).strip() for x in (work.style().get("notes") or []) if str(x).strip()]
    lines = [f"# 写作层规则 · 《{work.title}》", ""]
    lines.append("## 只有写作时适用（演员不知道这些，也不需要知道）")
    if notes:
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("-（这本书没有额外的写作层约束）")
    lines.append("")
    lines.append("## 为什么这些不给演员看")
    lines.append("- 它们是**成品读起来该是什么样**的要求，不是人物在一拍里能执行的动作。")
    lines.append("- 给演员看只会让他不敢动（比如「每样最多复位三次」—— 他一拍里没法数，"
                 "只学会绕开那件东西）。")
    lines.append("- 表演层面的要求写在 `actor_notes` 里，那一份**会**给演员。")
    return "\n".join(lines) + "\n"


def _actor_notes(work: Work) -> str:
    """**也给演员**的写法约束（`style.actor_notes`）。

    ★ 判据只有一条：**这是演员在一拍里能做/能不做的事吗？**
      · ✅ 「沉默不许只有一种形态」—— 他可以选择这次不说话、这次开口、这次只动一下；
      · ✅ 「拒绝别只用一句台词挡回去」—— 他可以选择换一个动作来拒绝；
      · ❌ 「每样最多复位三次」—— 数不了；
      · ❌ 「异常必须指向同一条线」—— 那是作者的编织。
    ⚠ 没写就返回空（不硬塞一段"这本书没有表演备注"—— 那是噪音）。
    [EN] Writing constraints that **do** reach actors (`style.actor_notes`).
        ★ One test: **can an actor do or not do this inside one beat?**
        ⚠ Returns empty when absent; do not inject "this book has no performance notes" (that is noise).
    """
    rows = [str(x).strip() for x in (work.style().get("actor_notes") or [])
            if str(x).strip()]
    if not rows:
        return ""
    lines = [f"# 表演备注 · 《{work.title}》", "",
             "## 这本书对表演的要求（人物自己心里要有数）"]
    for r in rows:
        lines.append(f"- {r}")
    return "\n".join(lines) + "\n"


def _progress(work: Work, case: Case) -> dict:
    """进度节点表（`故事进度.yaml`）。

    ★★★ 2026-10-21 改：**优先用作品自己写的 `bible.progress`**，没有才退回"单节点"。
    ------------------------------------------------------------------
    为什么改（用户问的正是这件事）：「揭秘后移、结尾加反转，能不能在一开始写小说时解决？」

    查下来的答案是 **同一个机关**：**进度节点这张地图**。
      · 「揭秘后移」——产品 2026-10-14 就修过（用户原话「第一天就想把谜底解开」），
        修法是 `_nodes_text` 只给**当前节点** + 明说"后面的路还没走到，不许提前揭"。
        ⚠ 但它**依赖节点表**：`rows` 空了就只剩一句"这本书还没设定进度节点"。
      · 「结尾加反转」——反转不是文字技巧（在导出层强加就是"新增情节"）；
        它等于"这一天结束时，某人的处境不可逆地变了"，而**那正是节点的完成判据**。

    ★ 而这个函数以前**无条件生成一个节点**（N01 = 「{case.place}这一场」）：
      于是每本书都只有一步棋，没有"层"可揭，"只给当前节点"这条修法**没有东西可给**。
      ⇒ 现在：yaml 里写了 `bible.progress`（多节点）就照它建；没写才退回单节点。
      ⚠ 退回的单节点**不许再叫"这一场"** —— 那个名字等于告诉模型"今天只要演一场"，
        它就不会往"结局要有变化"上想。改成"把当下这一步演完"，并明确要一句变化。

        English:
    Progress node table (`故事进度.yaml`).
        ★★★ Changed 2026-10-21: **prefer the work's own `bible.progress`**, fall back to a single
        node only when absent.
        Why (this is exactly what the user asked): "can moving the reveal later and adding a twist
        at the end be solved when the novel is first written?" The answer is **the same mechanism**:
        the progress-node map.
          · Moving the reveal later -- the product fixed this on 2026-10-14 (the user's words: "it
            wants to crack the mystery on day one") by having `_nodes_text` hand over **only the
            current node** plus "the road past here has not been reached, do not reveal early".
            ⚠ But it **depends on the node table**: an empty `rows` leaves just one sentence
            ("this book has no progress nodes yet").
          · A twist at the end -- not a wording trick (forcing it in the export layer is "adding
            plot"); it means "by the end of this day, someone's situation changed irreversibly",
            which **is exactly a node's completion criterion**.
        ★ This function used to **unconditionally emit one node** (N01 = "{case.place}, this
          scene"), so every book had a single move and there was no "layer" to reveal -- the
          "only the current node" fix had nothing to hand over.
          => Now: if the yaml carries `bible.progress` (multiple nodes), build from it; otherwise
          fall back to one node.
        ⚠ The fallback node must **no longer be called "this scene"** -- that name tells the model
          "today only needs one scene performed", so it never aims for "the ending must change".
          Renamed to "finish the current step", with an explicit requirement that something changes.
    """
    raw = (work.bible or {}).get("progress") or []
    nodes: list[dict] = []
    if isinstance(raw, list):
        for i, n in enumerate(raw):
            if not isinstance(n, dict):
                continue
            nodes.append({
                "id": str(n.get("id") or f"N{i + 1:02d}"),
                "名称": str(n.get("名称") or "").strip(),
                "概要": str(n.get("概要") or "").strip()[:300],
                "完成判据": str(n.get("完成判据") or "").strip(),
                "状态": str(n.get("状态") or ("进行中" if i == 0 else "未开始")),
            })
    nodes = [n for n in nodes if n["名称"]]
    if nodes:
        return {"节点": nodes}

    # 退路：作品没写节点表 —— 只给一步，但把"要有一处变化"写进完成判据。
    return {"节点": [{
        "id": "N01",
        "名称": "把当下这一步走完",
        "概要": case.scene_seed.strip()[:200],
        "完成判据": ("这一场把当下这一步演完，且不越过人物已知的信息边界；"
                 "并且**结束时有一处不可逆的变化**（某个人的处境变了，回不到开场那样）"),
        "状态": "进行中",
    }]}


def build_project(work: Work, case: Case, projects_root: Path):
    """Create ``<projects_root>/NB_<case_id>`` and write the nine settings files."""
    from store.project import Project       # imported lazily: keeps `check` fast

    proj = Project.create_new(
        projects_root,
        f"NB_{case.id}",
        genre=(work.genres[0] if work.genres else ""),
        style=(work.style().get("pov") or ""),
        source_folder=str(work.path or ""),
    )
    sd = proj.settings_dir
    _dump(sd / "人物.yaml", _people(work))
    _text(sd / "世界观.md", _worldview(work, case))
    _text(sd / "剧情走向.md", _plot(work, case))
    _text(sd / "顶级规则.md", _rules(work, case))
    _dump(sd / "地点.yaml", _places(work))
    _dump(sd / "关系.yaml", [
        {"甲": str(r.get("甲")), "乙": str(r.get("乙")), "关系": str(r.get("关系") or "")}
        for r in (work.bible.get("relations") or []) if r
    ])
    _dump(sd / "伏笔与悬线.yaml", [
        {"编号": str(f.get("编号") or f"F{i + 1}"), "内容": str(f.get("内容") or "")}
        for i, f in enumerate(work.bible.get("foreshadows") or []) if f
    ])
    _dump(sd / "细节设定.yaml", [
        {"名称": str(d.get("名称") or ""), "说明": str(d.get("说明") or "")}
        for d in (work.bible.get("details") or []) if d
    ])
    _dump(sd / "类型卡.yaml", _genre_card(work))
    _dump(sd / "风格卡.yaml", _style_card(work))
    _dump(sd / "故事进度.yaml", _progress(work, case))
    # ★ 2026-10-21：**写作层规则单独一份**，演员读不到（见 `_writer_notes`）。
    _text(sd / "写作层规则.md", _writer_notes(work))
    _an = _actor_notes(work)
    if _an:
        _text(sd / "表演备注.md", _an)
    _dump(sd / "小世界地图.yaml", {"名称": "待生成", "地点": []})

    meta = {
        "work": work.id,
        "title": work.title,
        "author": work.author,
        "case": case.id,
        "cut": case.cut,
        "place": case.place,
        "present": case.present,
        "story_time": case.story_time,
        "focus": case.focus,
        "genres": work.genres,
        "medium": work.medium,
        "license": work.license,
    }
    (proj.root / "bench_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return proj
