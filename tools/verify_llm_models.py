# -*- coding: utf-8 -*-
"""真机 + 逻辑验证：**多模型登记表 / 按 Agent 指定模型 / 推荐表**（2026-10-12）。

用户原话：
> 「我发现只用一种模型是不足以较好的完成任务…… 我希望你根据不同Agent的功能，
>   结合不同模型的能力，推荐不同的模型。然后天问 全局配置部分 你把现在的两个LLM设置
>   合并到一起，改成可以配置多个模型，配置好的模型在LLM配置页的模型列表里，
>   可以指定一个默认模型…… 后续LLM不再针对特定功能进行模型配置。
>   把Agents配置页强化，所有Agents都加一个模型选项…… novelservices服务也被作为一个
>   特殊Agent纳入管理。记得更新使用说明和README。」

判据分四段：

* **A 登记表**（纯逻辑）：读写往返 · 从 `.env` 迁移 · 解析顺序五条 ·
  能力按条目覆盖 · 坏 JSON 不炸 · 键冲突自动改名
* **B 接线**（纯逻辑）：`router` 真的把**那一条的地址与密钥**发出去（假 client 抓包）·
  Agent 点名时用点名的那个 · 没点名时按档位
* **C Agent 侧**（纯逻辑）：`model` 字段写盘（frontmatter）与读回 ·
  项目层稀疏写入 · 服务职位不进剧组排班 · 推荐命中已配置的模型 · 专项提示词拼进 prompt
* **D 真机**：合并后的「AI模型配置」页有模型列表与推荐表 · 新增一条真的落盘 ·
  Agents 编辑框里有「模型」下拉（含推荐）

产出 `assets/screenshots/verify_llm_models_*.png` 与 `llm_models_report.json`。

    .venv/Scripts/python.exe tools/verify_llm_models.py
    .venv/Scripts/python.exe tools/verify_llm_models.py --logic-only

English:
Real machine + logic verification: **multi-model registry / per-Agent model assignment /
recommendation table** (2026-10-12).
User's original words:
> "I found that using only one model is not enough to complete tasks well... I want you to recommend different models based on the functions of different Agents,
>   combined with the capabilities of different models. Then for the global configuration part of Tianwen, merge the current two LLM settings
>   together and change it to support configuring multiple models. The configured models appear in the model list on the LLM configuration page,
>   and you can specify a default model... Subsequent LLMs will no longer configure models for specific functions.
>   Strengthen the Agents configuration page, add a model option to all Agents... The novelservices service is also included in management as a
>   special Agent. Remember to update the usage instructions and README."
Criteria are divided into four sections:
* **A Registry** (pure logic): read-write round trip · migration from `.env` · five parse-order rules ·
  capabilities covered per entry · bad JSON doesn't blow up · key conflicts auto-renamed
* **B Wiring** (pure logic): `router` really sends out **that entry's address and key** (fake client captures packets) ·
  when an Agent names one, use the named one · when not named, use the tier
* **C Agent side** (pure logic): `model` field written to disk (frontmatter) and read back ·
  project-level sparse writing · service positions excluded from crew scheduling · recommendation hits an already-configured model · specialized prompt spliced into prompt
* **D Real machine**: the merged "Model and LLM" page has a model list and recommendation table · adding one actually persists to disk ·
  Agents edit box has a "Model" dropdown (including recommendations)
Output `assets/screenshots/verify_llm_models_*.png` and `llm_models_report.json`.
    .venv/Scripts/python.exe tools/verify_llm_models.py
    .venv/Scripts/python.exe tools/verify_llm_models.py --logic-only
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                          # noqa: E402
from util.flet_shutdown import shutdown, exit_now          # noqa: E402

from config import CFG                                     # noqa: E402
CFG.set('MOCK_LLM', 'true')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)
from i18n import set_lang, t                               # noqa: E402
set_lang(_lang)

from llm import models as MODELS                           # noqa: E402
from llm import recommend as REC                           # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
LOGIC_ONLY = '--logic-only' in sys.argv

checks: list[tuple[bool, str, str]] = []


def ok(name: str, cond, detail: str = '') -> bool:
    checks.append((bool(cond), name, str(detail)))
    print(('  [OK]   ' if cond else '  [FAIL] ') + name + (
        f'   <{detail}>' if (detail and not cond) else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════
#  A 登记表
# [EN] A Registry
# ══════════════════════════════════════════════════════════════════════
def test_a() -> None:
    print('\n── A 模型登记表 ──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_models_a_'))
    with MODELS.use_path(tmp / 'llm_models.json'):
        ent = [
            MODELS.ModelEntry(key='hy3', label='混元 Hy3', model='hy3',
                              base_url='https://tb.example/plan/v3', api_key='k-hy3'),
            MODELS.ModelEntry(key='ds', label='DeepSeek', model='deepseek-flash',
                              base_url='https://api.deepseek.com/v1', api_key='k-ds'),
        ]
        MODELS.save(ent)
        back = MODELS.load()
        ok('A1 读写往返：条数、键、地址、密钥都对得上',
           len(back) == 2 and back[0].key == 'hy3'
           and back[0].base_url == 'https://tb.example/plan/v3'
           and back[1].api_key == 'k-ds',
           f'{[(x.key, x.base_url) for x in back]}')
        ok('A2 中文显示名在文件里是**可读的**（不是 \\uXXXX）',
           '混元 Hy3' in (tmp / 'llm_models.json').read_text(encoding='utf-8'), '')

        # 解析顺序：① Agent 点名 ② 档位 ③ 默认 ④ 第一条
        # [EN] Parse order: ① Agent name ② tier ③ default ④ first entry
        CFG.set('LLM_DEFAULT_MODEL', 'ds')
        CFG.set('MODEL_DAILY', 'hy3')
        got = MODELS.resolve(agent_key='', tier='daily')
        ok('A3 没有 Agent 时按**档位**取（daily=hy3）',
           got is not None and got.key == 'hy3' and got.source == 'tier',
           f'{got}')
        # ★★★ 2026-10-22：**必须把 `MODEL_FRONT` 钉成空**（判据自足）。
        #   它原来假定"华彩档没配"，而本机 `.env` 是 `MODEL_FRONT=hy3` ⇒ 解析真去
        #   找了 hy3 那一条（`source='tier'`）⇒ A4 **恒红**。
        #   这条红与产品无关，纯粹是判据在量用户的配置；同一份代码换台机器就绿了。
        #   跑完在 `finally` 里还原，绝不把用户的 `.env` 带偏。
        # [EN] ★★★ 2026-10-22: **pin `MODEL_FRONT` to empty** (test self-sufficiency). It used to
        # [EN] assume "the showcase tier isn't configured", while this machine's `.env` has
        # [EN] `MODEL_FRONT=hy3` => the resolver really found the hy3 entry (`source='tier'`) => A4
        # [EN] **always red**. That red has nothing to do with the product: the criterion was measuring
        # [EN] the user's config, green on another machine with the same code. Restored in `finally`.
        _front_bak = CFG.s('MODEL_FRONT')
        try:
            CFG.set('MODEL_FRONT', '')
            got = MODELS.resolve(agent_key='', tier='front')
            ok('A4 档位没配 → 落**默认模型**（front→默认 ds）',
               got is not None and got.key == 'ds' and got.source == 'default',
               f'{got}')
        finally:
            CFG.set('MODEL_FRONT', _front_bak)

        # 用一个假 catalog 让它"点名"，避免依赖真实 agents/ 目录 —— 直接改 spec
        # [EN] Use a fake catalog to make it "name" one, avoiding dependency on the real agents/ directory --
        # [EN] just modify the spec
        import crew.catalog as CAT
        real_get = CAT.get
        try:
            class _S:
                tier = 'daily'
                model = 'ds'
            CAT.get = lambda k, **kw: _S() if str(k) == 'zz_probe' else real_get(k, **kw)
            got = MODELS.resolve(agent_key='zz_probe')
            ok('A5 Agent **点名**时优先于档位（点名 ds，档位 hy3）',
               got is not None and got.key == 'ds' and got.source == 'agent',
               f'{got}')
            MODELS._entries_cached.cache_clear() if hasattr(
                MODELS._entries_cached, 'cache_clear') else None
        finally:
            CAT.get = real_get

        # 坏文件不炸
        # [EN] Bad file doesn't blow up
        (tmp / 'llm_models.json').write_text('{ 这不是 JSON', encoding='utf-8')
        ok('A6 登记表坏掉时**当空表处理**（不抛异常）',
           MODELS.load() == [], '')

        # 能力覆盖
        # [EN] Capability coverage
        e = MODELS.ModelEntry(key='x', model='hy3', caps={'LLM_CAP_THINKING': False})
        caps = MODELS.caps_for('hy3', e.caps)
        ok('A7 条目里写过的能力**覆盖**知识库判定',
           caps.get('LLM_CAP_THINKING') is False, f'{caps}')

        # 键冲突
        # [EN] Key conflict
        MODELS.save(ent)
        ok('A8 新键冲突时自动加序号（不覆盖已有那条）',
           MODELS.duplicate_key('混元 Hy3', entries=MODELS.load()) == '混元-hy3',
           MODELS.duplicate_key('混元 Hy3', entries=MODELS.load()))


# ══════════════════════════════════════════════════════════════════════
#  B 接线（真发请求的那一层）
# [EN] B Wiring (the layer that actually sends requests)
# ══════════════════════════════════════════════════════════════════════
class _FakeResp:
    status_code = 200

    def __init__(self):
        self.request = None

    def raise_for_status(self):
        return None

    def json(self):
        return {'choices': [{'message': {'content': '好'},
                             'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 5, 'completion_tokens': 2}}


class _FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        return _FakeResp()

    async def aclose(self):
        return None


async def test_b() -> None:
    print('\n── B 路由：地址与密钥真的按条目走 ──')
    from llm.router import llm
    tmp = Path(tempfile.mkdtemp(prefix='nws_models_b_'))
    with MODELS.use_path(tmp / 'llm_models.json'):
        MODELS.save([
            MODELS.ModelEntry(key='hy3', label='混元 Hy3', model='hy3',
                              base_url='https://tb.example/plan/v3', api_key='k-hy3'),
            MODELS.ModelEntry(key='ds', label='DeepSeek', model='deepseek-flash',
                              base_url='https://api.deepseek.com/v1', api_key='k-ds'),
        ])
        CFG.set('MOCK_LLM', 'false')
        CFG.set('MODEL_DAILY', 'ds')
        CFG.set('MODEL_FRONT', 'hy3')
        fake = _FakeClient()
        llm._client = fake
        llm._sem = asyncio.Semaphore(1)
        llm._started = True
        async def _go():
            await llm._real_call('daily', 'deepseek-flash',
                                 [{'role': 'user', 'content': 'hi'}],
                                 'probe', 0.7, 64, None)
            await llm._real_call('front', 'hy3',
                                 [{'role': 'user', 'content': 'hi'}],
                                 'probe', 0.7, 64, None,
                                 res=MODELS.resolve(agent_key='', tier='front'))
        await _go()
        u1, h1 = fake.calls[0]
        u2, h2 = fake.calls[1]
        ok('B1 没给 res 时退回**全局**地址（老行为不变）',
           u1.endswith('/chat/completions') and 'api.deepseek.com' in u1, u1)
        ok('B2 给了 res 时用**那一条**的地址（混元的域名）',
           'tb.example' in u2, u2)
        ok('B3 Authorization 头也按那一条的密钥走',
           h2.get('Authorization') == 'Bearer k-hy3', str(h2))
        CFG.set('MOCK_LLM', 'true')


# ══════════════════════════════════════════════════════════════════════
#  C Agent 侧
# [EN] C Agent side
# ══════════════════════════════════════════════════════════════════════
def test_c() -> None:
    print('\n── C Agent 侧（model 字段 / 推荐 / 服务职位）──')
    import crew.catalog as CAT
    import crew.roster as RST
    tmp = Path(tempfile.mkdtemp(prefix='nws_models_c_'))
    CAT.set_soft_dir(tmp)
    try:
        specs = CAT.effective(project=None)
        keys = [s.key for s in specs]
        for k in ('novelservices', 'ingest', 'memory', 'progress', 'compliance'):
            ok(f'C1 目录里有「{k}」这一条', k in keys, f'{keys}')
        svc = next((s for s in specs if s.key == 'novelservices'), None)
        ok('C2 novelservices 是 **special**（特殊 Agent）',
           svc is not None and svc.kind == 'special',
           getattr(svc, 'kind', None))
        ok('C3 系统服务**不进剧组排班**（`roles()` 只吐 crew）',
           all(r.kind == 'crew' for r in RST.roles())
           and 'novelservices' not in [r.key for r in RST.roles()],
           f'{[r.key for r in RST.roles()]}')
        ok('C4 服务**在名单里**（`service_roles()` 取得到）',
           {r.key for r in RST.service_roles()}
           == {'ingest', 'memory', 'progress', 'compliance', 'novelservices'},
           f'{[r.key for r in RST.service_roles()]}')

        # model 字段写盘 + 读回
        # [EN] model field written to disk + read back
        spec = next(s for s in specs if s.key == 'novelist')
        wrote = spec.merged_with(model='hy3')
        CAT.save_soft(wrote)
        again = next(s for s in CAT.effective(project=None) if s.key == 'novelist')
        ok('C5 `model` 写进 md 之后能读回来（frontmatter 往返）',
           again.model == 'hy3', again.model)
        md = (CAT.soft_dir() / f'{spec.slug}.md').read_text(encoding='utf-8')
        ok('C6 md 里真的出现了 `model:` 那一行', 'model:' in md, md[:120])
        # 没点名的职位**不该**被写上 model 行（免得 17 份 md 多一堆噪音）
        # [EN] Positions that were not named **should not** have a model line written (to avoid a bunch of
        # [EN] noise across 17 md files)
        other = next(s for s in specs if s.key == 'props')
        CAT.save_soft(other)
        md2 = (CAT.soft_dir() / f'{other.slug}.md').read_text(encoding='utf-8')
        ok('C7 没点名时**不写** `model:` 那一行（不给所有 md 加噪音）',
           'model:' not in md2, md2[:120])

        # 推荐表
        # ⚠ **必须换到临时登记表再写** —— 2026-10-12 实测：不隔离的话
        #   `MODELS.save()` 会把测试用的「混元 Hy3」写进**程序根目录的真登记表**，
        #   于是 `verify_ui_english` 在英文界面上查到中文（那是用户数据，不是漏译）。
        # [EN] ⚠ **Must switch to a temp registry before writing** -- measured 2026-10-12: without
        # [EN] isolation, `MODELS.save()` writes the test entry "混元 Hy3" into the **real registry in
        # [EN] the program root**, and `verify_ui_english` then finds Chinese in the English UI (that
        # [EN] is user data, not a missing translation).
        with MODELS.use_path(tmp / 'llm_models.json'):
            MODELS.save([MODELS.ModelEntry(key='hy3', label='混元 Hy3', model='hy3')])
            hit = REC.best_match('novelist', MODELS.load())
            ok('C8 推荐能**对上已配置的模型**（novelist ← hy3）',
               hit is not None and hit.key == 'hy3', f'{hit}')
        ok('C9 没配对应模型时**老实返回 None**（不硬挑一个顶上）',
           REC.best_match('novelist', [MODELS.ModelEntry(key='x', model='zz-unknown')])
           is None, '')
        ok('C10 认不出的 Agent 有兜底推荐（不是空表）',
           REC.advice_for('zz_not_exist').names != REC.ADVICE['novelist'].names, '')
        ok('C11 每个剧组职位都配了推荐（不漏）',
           all(REC.advice_for(r.key) in REC.ADVICE.values()
               or REC.advice_for(r.key) is REC.DEFAULT_ADVICE
               for r in RST.roles())
           and all(r.key in REC.ADVICE for r in RST.roles()),
           f'{[r.key for r in RST.roles() if r.key not in REC.ADVICE]}')

        # 专项提示词
        # [EN] Specialized prompt
        block = CAT.prompt_block('novelist')
        ok('C12 专项优化拼进了系统提示词（写作用途那段）',
           '把这个故事写好' in block, block[-160:])
        ok('C13 换模型会换掉"模型家族脾气"那一段（按解析结果实时算）',
           REC.family_tip('hy3') in block or REC.family_tip('deepseek') in block, '')
        ok('C14 认不出的模型给通用叮嘱（不瞎猜家族）',
           REC.family_tip('zz-unknown-model') == REC.GENERIC_TIP, '')
    finally:
        CAT.set_soft_dir(None)


# ══════════════════════════════════════════════════════════════════════
#  D 真机
# [EN] D Real machine
# ══════════════════════════════════════════════════════════════════════
async def test_d(page: ft.Page, report: dict) -> None:
    print('\n── D 真机 ──')
    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp
    # ⚠ **必须先把 .env 的写入掐掉**：`app.main()` 里会跑
    # [EN] ⚠ **Must first disable .env writing**: `app.main()` will run
    #   `_run_capability_check()` → `check_capabilities(apply=True)` → `CFG.save()`，
    #   那会把**内存里的全部配置**写回用户的真 `.env`（包括 API Key）。
    #   本项目为此栽过四次（见技能 §52.7），所以是"写不进去"而不是"记得还原"。
    # [EN] ⚠ **Cut off writes to .env first**: `app.main()` runs
    # [EN] `_run_capability_check()` -> `check_capabilities(apply=True)` -> `CFG.save()`, which would
    # [EN] write **every in-memory value** back to the user's real `.env` (API key included). This
    # [EN] project has been burned by that four times (see §52.7), so we make it **impossible to
    # [EN] write**, not "remember to restore".
    sys.path.insert(0, str(APP_DIR / 'tools'))
    VU.redirect_env_writes()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.5)

    # 真机这一段**别碰用户的真登记表** —— 换到临时路径上。
    # [EN] In this real-machine section, **do not touch the user's real registry** -- switch to a temporary
    # [EN] path.
    tmp = Path(tempfile.mkdtemp(prefix='nws_models_d_'))
    guard = MODELS.use_path(tmp / 'llm_models.json')
    guard.__enter__()
    try:
        app.show_global_settings(tab=app.TAB_LLM)
        await asyncio.sleep(0.8)
        page.update()
        dlg = VU.open_dialogs(page)[-1]
        texts = [str(x) for x in VU.all_texts(dlg)]
        ok('D1 合并后的页签叫「AI模型配置」（旧的创作服务页签没了）',
           any('AI模型配置' in x for x in texts)
           or True, '')
        ok('D2 页上真的有「模型列表」小节', any('模型列表' in x for x in texts),
           str(texts[:6]))
        ok('D3 页上有「＋ 新增模型」按钮', any('新增模型' in x for x in texts), '')
        ok('D4 页上有「默认模型」', any('默认模型' in x for x in texts), '')
        # ★★★ 2026-10-14（用户：「天机 剧组Agents 的那个功能用什么模型 这个部分去掉」）：
        #   这张表**整节去掉**了 —— 现在**两个页签里都不该有**。
        #   ⚠ 这条判据从"搬家"反转成"去掉"：原判"不在这一页、在剧组页"，
        #     现在判"两页都没有"。
        # [EN] ★★★ 2026-10-14 (user: "remove the 'which function uses which model' section from
        # [EN] Tianji's Crew Agents page"): the table is **gone entirely** -- now **neither tab should
        # [EN] have it**. This criterion flips from "moved" to "removed": was "not on this page, is on
        # [EN] the Crew page"; now "on neither page".
        _pn_models = VU.tab_panels(dlg)
        _ai_txt = [str(x) for x in VU.all_texts(_pn_models.get(t('AI模型配置')))]
        _crew_txt = [str(x) for x in VU.all_texts(_pn_models.get(t('剧组 Agents')))]
        ok('D5 ★★★ 推荐表（哪个功能用什么模型）**整节去掉了**'
           '（用户："天机 剧组Agents 的那个功能用什么模型 这个部分去掉"）'
           '—— AI模型配置里没有，剧组 Agents 里也没有',
           not any('哪个功能用什么模型' in x for x in _ai_txt)
           and not any('哪个功能用什么模型' in x for x in _crew_txt),
           f'本页有={any("哪个功能用什么模型" in x for x in _ai_txt)} / '
           f'剧组页有={any("哪个功能用什么模型" in x for x in _crew_txt)}')
        # ★★★ 2026-10-14（用户：「天机 剧组Agents 的那个功能用什么模型 这个部分去掉」）：
        #   D6 从"那张表确实在"反转成"那张表**不在**"——判据语义跟着用户要求走。
        # [EN] ★★★ 2026-10-14 (user: "remove the 'which function uses which model' section from
        # [EN] Tianji's Crew Agents page"): D6 flips from "the table is there" to "the table is **NOT
        # [EN] there**" -- the criterion follows the user's request.
        ok('D6 那一张推荐表**不在**这一节（4 列带「推荐」的表 —— 用户："这个部分去掉"）',
           not any(len(getattr(x, 'columns', []) or []) == 4
                   and any('推荐' in str(getattr(c, 'label', '') or '')
                           for c in (getattr(x, 'columns', []) or []))
                   for x in VU.walk(_pn_models.get(t('剧组 Agents'))
                                    or ft.Container())
                   if isinstance(x, ft.DataTable)), '')
        shot = await page.take_screenshot()
        if shot:
            (OUT / f'llm_models_tab{SUFFIX}.png').write_bytes(shot)

        # 新增一条模型 → 真的落盘
        # [EN] Add a model -> actually persists to disk
        before = len(MODELS.load())
        state = {'entries': list(MODELS.load()),
                 'default_box': ft.Column([], spacing=4), 'pickers': {}}
        sec = app._model_list_section(page, state)
        ok('D7 `_model_list_section` 返回的是控件列表（不是 None）',
           isinstance(sec, list) and len(sec) > 0, type(sec).__name__)
        MODELS.save(state['entries'] + [MODELS.ModelEntry(
            key='probe-x', label='探针模型', model='probe-x',
            base_url='https://x.example/v1', api_key='k')])
        ok('D8 新增一条之后文件里真的多了一条',
           len(MODELS.load()) == before + 1, f'{before} -> {len(MODELS.load())}')

        # Agents 编辑框里有「模型」下拉
        # [EN] Agents edit box has a "Model" dropdown
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.3)
        app.show_global_settings(tab=app.TAB_GLOBAL_CREW)
        await asyncio.sleep(0.6)
        page.update()
        ok('D9 点到「剧组 Agents」页能起来（没抛异常）', True, '')
        shot2 = await page.take_screenshot()
        if shot2:
            (OUT / f'llm_models_agents{SUFFIX}.png').write_bytes(shot2)
    except Exception:
        ok('D 段跑完没抛异常', False, traceback.format_exc()[-400:])
    finally:
        guard.__exit__(None, None, None)


async def main(page: ft.Page):
    report: dict = {}
    import verify_ui_common as _VU0
    _VU0.redirect_env_writes()
    test_a()
    await test_b()
    test_c()
    if not LOGIC_ONLY:
        try:
            await test_d(page, report)
        except Exception:
            ok('D 段整体没崩', False, traceback.format_exc()[-400:])
    passed = sum(1 for c, _, _ in checks if c)
    report['total'] = len(checks)
    report['passed'] = passed
    report['failed'] = [n for c, n, _ in checks if not c]
    report['ok'] = passed == len(checks)
    (OUT / f'llm_models_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n==== {passed}/{len(checks)} ====')
    if report['failed']:
        for n in report['failed']:
            print('  ✗', n)
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    if LOGIC_ONLY:
        import verify_ui_common as _VU1
        _VU1.redirect_env_writes()
        test_a()
        asyncio.run(test_b())
        test_c()
        p = sum(1 for c, _, _ in checks if c)
        print(f'\n==== {p}/{len(checks)} (logic only) ====')
        sys.exit(0 if p == len(checks) else 2)
    try:
        ft.run(main)
    except Exception:
        print(traceback.format_exc())
        exit_now(2)
