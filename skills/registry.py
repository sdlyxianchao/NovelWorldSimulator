# -*- coding: utf-8 -*-
"""技能注册（设计稿 §8.6）：扫描、加载、路由 `skills/` 下的知识包。

技能目录结构：
    skills/
    ├── 朝代制度速查/
    │   └── SKILL.md          ← 必须有，且以 --- 开头的 YAML frontmatter 起头
    ├── 节气物候/
    │   ├── SKILL.md
    │   └── scripts/jieqi.py  ← 可选
    └── ...

路由策略（`find_skill(query)`）
    「触发关键词」用**子串匹配**，所以关键词的选择很关键：
    太短（如「字」）会把「名字」「文字」全命中。因此这里做了两道过滤——
      1. 关键词长度 < 2 的字面量不参与子串匹配（只允许整词相等）
      2. 打分排序：技能名完全相等 > 技能名包含 > 关键词相等 > 关键词包含，
         同分时长关键词优先（更具体 = 更该命中）
    这样「主角的字号怎么取」会命中「姓名称谓生成」，而不是被「字」带偏。

写自己的技能见 skills/README.md。

English:
Skill registration (design doc §8.6): scan, load, route the knowledge packs under `skills/`.
Skill directory structure:
    skills/
    │   └── SKILL.md          ← required, and starts with YAML frontmatter beginning with ---
    │   ├── SKILL.md
    │   └── scripts/jieqi.py  ← optional
    └── ...
Routing strategy (`find_skill(query)`)
    too short (e.g. 「字」) will hit 「名字」「文字」 everywhere. So two filters are applied here——
      1. Literals with keyword length < 2 do not participate in substring matching (only exact word equality allowed)
      2. Scoring order: skill name exactly equal > skill name contains > keyword equal > keyword contains,
         on ties, longer keywords first (more specific = more deserving of a hit)
To write your own skill see skills/README.md.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from config import CFG

_LOG = __import__("logging").getLogger("nws.skills")

# frontmatter 里建议存在的字段（缺失只提示，不阻断加载）
# [EN] Suggested fields in frontmatter (missing only warns, does not block loading)
RECOMMENDED_FIELDS = ('名称', '触发关键词', '用途')

#: 核心标签轴（命中给 2 分，其余 1 分）。
#: ★ 与 `booklab/theory.CORE_AXES` **必须一致** —— 判据会核对这一条，
#:   因为它们分处两个词表：写入侧在 `theory`，查询侧在这里，
#:   两边不一致会让"写进去的标签查不出来"（最难查的一类静默错误）。
# [EN] : core tag axes (2 points on hit, 1 point otherwise).
# [EN] : ★ Must be **consistent** with `booklab/theory.CORE_AXES` —— the judge checks this one,
# [EN] : because they live in two vocabularies: the write side is in `theory`, the query side is here,
# [EN] : inconsistency between the two sides makes "tags written in can't be queried out" (the hardest
# [EN] class of silent bug to find).
CORE_AXES: tuple[str, ...] = ('题材', '读者需求', '情绪')
#: 标签的轴（同样与 `theory.TAG_AXES` 对齐）
# [EN] : axes of tags (likewise aligned with `theory.TAG_AXES`)
TAG_AXES: tuple[str, ...] = ('题材', '读者需求', '情绪', '剧情功能', '适用阶段')


class Skill:
    """一个已加载的技能。
        English:
    A loaded skill.
    """

    def __init__(self, name: str, meta: dict, path: Path):
        self.dir_name = name
        self.meta = meta
        self.path = path

    # ── 元数据 ──
    # [EN] ── metadata ──
    @property
    def display_name(self) -> str:
        return str(self.meta.get('名称') or self.dir_name)

    @property
    def triggers(self) -> list[str]:
        raw = self.meta.get('触发关键词') or []
        if isinstance(raw, str):
            raw = [raw]
        return [str(t).strip() for t in raw if str(t).strip()]

    @property
    def purpose(self) -> str:
        return str(self.meta.get('用途') or '')

    @property
    def content(self) -> str:
        return str(self.meta.get('_content') or '')

    @property
    def scripts(self) -> list[Path]:
        """附带脚本的绝对路径（写在 frontmatter 的 `脚本:` 里）。
                English:
        Absolute path of the attached script (written in frontmatter's `脚本:`).
        """
        raw = self.meta.get('脚本') or []
        if isinstance(raw, str):
            raw = [raw]
        out: list[Path] = []
        for rel in raw:
            p = self.path.parent / str(rel)
            if p.exists():
                out.append(p)
        return out

    # ── 查询 ──
    # [EN] ── query ──
    @property
    def category(self) -> str:
        """分类：优先 frontmatter 的 `分类`，没有就用**父目录名**。

        ★ 2026-10-10 起技能支持**两级**结构（`skills/book-dismantle/<书名>/`）——
          拆书产出的技能归在一处，不跟人写的领域技能混在同一层。
          父目录名恰好就是分类（`book-dismantle`），所以这一处不用额外配置。
        
                English:
        Category: prefer frontmatter's `分类`; if absent use the **parent directory name**.
                ★ Since 2026-10-10 skills support **two-level** structure (`skills/book-dismantle/<书名>/`)——
                  book-dismantle output skills are grouped in one place, not mixed on the same level with human-written domain skills.
                  The parent directory name happens to be the category (`book-dismantle`), so no extra configuration is needed here.
        """
        return str(self.meta.get('分类') or self.parent_dir or '')

    @property
    def parent_dir(self) -> str:
        return str(self.meta.get('_parent') or '')

    @property
    def genre(self) -> str:
        """`适用类型.题材`（`skillgen` 写了这个字段）—— 给匹配用的。
                English:
        `applicable types.genre` (this field is written by `skillgen`) — used for matching.
        """
        raw = self.meta.get('适用类型')
        if isinstance(raw, dict):
            return str(raw.get('题材') or '').strip()
        return ''

    @property
    def traits(self) -> list[str]:
        """`特点` 列表（通常就是拆出来的那几条写法名）—— 给匹配用的。
                English:
        `特点` list (usually the few writing-method names that were dismantled out) —— used for matching.
        """
        raw = self.meta.get('特点') or []
        if isinstance(raw, str):
            raw = [raw]
        return [str(x).strip() for x in raw if str(x).strip()]

    @property
    def tags(self) -> dict[str, list[str]]:
        """受控标签 `{轴: [值]}`（拆书产出的技能有）。
                English:
        Controlled tags `{轴: [值]}` (present for book-dismantle output skills).
        """
        raw = self.meta.get('标签')
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            vals = [v] if isinstance(v, str) else list(v or [])
            vals = [str(x).strip() for x in vals if str(x).strip()]
            if vals:
                out[str(k).strip()] = vals
        return out

    # ── 路由打分 ──
    # [EN] ── routing scoring ──
    def score(self, query: str) -> int:
        q = (query or '').strip().lower()
        if not q:
            return 0
        name = self.display_name.lower()
        best = 0

        if q == name or q == self.dir_name.lower():
            best = max(best, 100)
        elif name and name in q:
            best = max(best, 80)
        elif self.dir_name.lower() in q:
            best = max(best, 75)

        for t in self.triggers:
            tl = t.lower()
            if q == tl:
                best = max(best, 70)
            elif len(tl) >= 2 and tl in q:
                # 越具体（越长）的关键词给分越高
                # [EN] The more specific (longer) the keyword, the higher the score
                best = max(best, 40 + min(len(tl), 20))

        # ★★ 2026-10-10：把 `适用类型` / `标签` 接进打分（`特点` 见下面的说明）。
        # [EN] ★★ 2026-10-10: Wire `applicable types` / `tags` into scoring (see the notes below for
        # [EN] `features`).
        #
        #   权重刻意**低于**名称/关键词命中：那两样是"直接叫得出名字"，
        #   这两样是"沾边"，不该盖过前者。
        # [EN] Weight is deliberately **lower** than name/keyword hits: those two are "you can call it by name
        # [EN] directly",
        # [EN] these two are "tangentially related", and should not override the former.
        if self.genre and len(self.genre) >= 2 and self.genre.lower() in q:
            best = max(best, 36)
        # 标签走**精确命中**（不是子串）：`轴=值` 或 值 原样出现
        # [EN] Tags use **exact hit** (not substring): `轴=值` or 值 appears verbatim
        for axis, vals in self.tags.items():
            for v in vals:
                vl = v.lower()
                if len(vl) < 2:
                    continue
                if f'{axis}={vl}' in q or vl in q:
                    # 核心轴 2 分、其余 1 分（来源：oh-story 的核心轴加权）
                    # [EN] Core axes 2 points, the rest 1 point (source: weighting of core axes in oh-story)
                    best = max(best, 30 + (10 if axis in CORE_AXES else 5))
        # ⚠ **`特点` 故意不参与打分**（2026-10-10 的一个诚实决定）：
        #   `skillgen` 往 `特点` 里写的是**模块名**，而同一个模块名**也**写进了
        #   `触发关键词` —— 于是"接上 `特点`"根本测不出来（两个来源给同一批词打分，
        #   改哪个都不影响结果）。**做了等于没做，那就不做**：
        #   与其留一个无法验证的分支冒充"把闲置字段用起来了"，
        #   不如明说它和触发关键词重复、只当人读的摘要。
        #   （判据 `verify_booklab` 的 I9c 只钉 `标签` —— 它才是真独立的那一列。）
        # [EN] ⚠ **`特点` deliberately does not participate in scoring** (an honest decision on 2026-10-10):
        # [EN] What `skillgen` writes into `特点` is the **module name**, and the same module name is **also**
        # [EN] written into
        # [EN] `触发关键词` —— so "hooking up `特点`" simply can't be measured (both sources score the same batch of
        # [EN] words,
        # [EN] changing either doesn't affect the result). **Doing it is the same as not doing it, so don't do
        # [EN] it**:
        # [EN] rather than keep an unverifiable branch pretending to "put an idle field to use",
        # [EN] better to state plainly that it duplicates 触发关键词 and only serves as a human-read summary.
        # [EN] (The judge `verify_booklab`'s I9c only pins `标签` —— it's the truly independent column.)
        return best

    def as_dict(self) -> dict:
        return {
            '名称': self.display_name,
            '目录': self.dir_name,
            '分类': self.category,
            '用途': self.purpose,
            '触发关键词': self.triggers,
            '标签': self.tags,
            '脚本': [str(p) for p in self.scripts],
            '路径': str(self.path),
        }


class SkillRegistry:
    """技能注册表：扫描、注册、路由技能。
        English:
    Skill registry: scan, register, route skills.
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    # ── 加载 ──
    # [EN] ── loading ──
    def load(self, *, force: bool = False) -> None:
        if self._loaded and not force:
            return
        self._skills.clear()
        self._loaded = True

        if not CFG.b('SKILLS_ENABLED'):
            _LOG.info('技能已由 SKILLS_ENABLED 关闭')
            return

        skills_dir = CFG.resolved('SKILLS_DIR')
        if not skills_dir.is_dir():
            _LOG.info('技能目录不存在: %s', skills_dir)
            return

        # ★ 2026-10-10：支持**两级**结构。
        #   一级：`skills/<技能名>/SKILL.md`（人写的领域技能，一直是这样）；
        #   二级：`skills/<分类>/<技能名>/SKILL.md`（拆书产出：`book-dismantle/<书名>/`）。
        #   为什么要分两级：拆书产出的技能会**一本一份**地长出来，
        #   全铺在一级会把 `skills/` 变成一堆书名，人写的技能被淹在里面。
        #   ⚠ "分类目录"的判定标准是**它自己没有 SKILL.md、而子目录有** ——
        #     不按目录名硬编码，这样以后加别的分类也自动支持。
        # [EN] ★ 2026-10-10: support **two-level** structure.
        # [EN] Level one: `skills/<技能名>/SKILL.md` (human-written domain skills, as it has always been);
        # [EN] Why two levels: book-dismantle output skills grow **one per book**,
        # [EN] laying them all in level one would turn `skills/` into a pile of book titles, drowning the
        # [EN] human-written skills.
        # [EN] ⚠ The criterion for a "category directory" is **it has no SKILL.md itself, while its
        # [EN] subdirectories do** ——
        # [EN] not hardcoded by directory name, so adding other categories later is automatically supported.
        found = 0
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if (skill_dir / 'SKILL.md').exists():
                if self._add(skill_dir.name, skill_dir / 'SKILL.md', ''):
                    found += 1
                continue
            for sub in sorted(skill_dir.iterdir()):
                if sub.is_dir() and (sub / 'SKILL.md').exists():
                    if self._add(sub.name, sub / 'SKILL.md', skill_dir.name):
                        found += 1

        _LOG.info('技能注册完成: %d 个', found)

    def _add(self, name: str, path: Path, parent: str) -> bool:
        """解析并登记一个技能；成功返回 True。
                English:
        Parse and register a skill; returns True on success.
        """
        skill = self._parse(name, path, parent=parent)
        if not skill:
            return False
        self._skills[name] = skill
        missing = [f for f in RECOMMENDED_FIELDS if not skill.meta.get(f)]
        if missing:
            _LOG.warning('技能 %s 的 frontmatter 少了字段: %s',
                         name, '、'.join(missing))
        return True

    @staticmethod
    def _parse(name: str, path: Path, parent: str = '') -> Skill | None:
        """解析 SKILL.md 的 YAML frontmatter。
                English:
        Parse the YAML frontmatter of SKILL.md.
        """
        try:
            content = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            _LOG.warning('读技能文件失败 %s: %s', path, e)
            return None

        if not content.lstrip().startswith('---'):
            _LOG.warning('技能 %s 缺少 frontmatter（文件必须以 --- 开头）', name)
            return None

        parts = content.split('---', 2)
        if len(parts) < 3:
            _LOG.warning('技能 %s 的 frontmatter 没有闭合的 ---', name)
            return None

        try:
            meta = yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            _LOG.warning('技能 %s 的 frontmatter 解析失败: %s', name, e)
            return None
        if not isinstance(meta, dict):
            _LOG.warning('技能 %s 的 frontmatter 不是键值对', name)
            return None

        meta['_content'] = parts[2].strip()
        meta['_path'] = str(path)
        # 两级结构里它的父目录名（没有就是一级技能）
        # [EN] In the two-level structure, its parent directory name (level-one skill if none)
        meta['_parent'] = str(parent or '')
        return Skill(name, meta, path)

    # ── 查询 ──
    # [EN] ── query ──
    def all_skills(self) -> list[Skill]:
        self.load()
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        self.load()
        return self._skills.get(name)

    def match_all(self, query: str) -> list[Skill]:
        """按相关度排序返回全部命中的技能。
                English:
        Return all hit skills sorted by relevance.
        """
        self.load()
        scored = [(s.score(query), s) for s in self._skills.values()]
        hits = [(sc, s) for sc, s in scored if sc > 0]
        hits.sort(key=lambda t: (-t[0], t[1].display_name))
        return [s for _, s in hits]

    def find_skill(self, keyword: str) -> dict | None:
        """按相关度找最佳技能，返回元数据字典（保持旧接口以兼容考据通道）。

        元数据里含 `_content`（正文）与 `_path`，老调用方依赖这两个键。
        
                English:
        Find the best skill by relevance, return a metadata dict (keep the old interface for
        compatibility with the 考据 channel).
                Metadata contains `_content` (body) and `_path`; legacy callers depend on these two keys.
        """
        hits = self.match_all(keyword)
        if not hits:
            return None
        best = hits[0]
        meta = dict(best.meta)
        meta.setdefault('名称', best.display_name)
        return meta

    def get_all_skills(self) -> dict[str, dict]:
        self.load()
        return {name: dict(s.meta) for name, s in self._skills.items()}

    def get_skill_content(self, skill_name: str) -> str | None:
        skill = self.get(skill_name)
        return skill.content if skill else None

    def summary(self) -> list[dict]:
        """给文档/GUI 用的清单。
                English:
        Manifest for docs/GUI.
        """
        return [s.as_dict() for s in self.all_skills()]


# 全局单例
# [EN] Global singleton
skill_registry = SkillRegistry()
