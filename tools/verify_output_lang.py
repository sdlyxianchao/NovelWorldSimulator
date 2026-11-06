# -*- coding: utf-8 -*-
"""验证：**项目级「输出语言」**真的管住了所有输出。

用户（2026-10-06）：
「在项目里设置一个输出语言，这样**所有的输出都用这个语言**，即使小说原来的语言不是这个
（默认请支持中文英文即可，后续再加别的）」

判据分三层，缺一层都不算做到：
  A 纯逻辑：`util/outlang` 怎么解析（`auto`/空/认不出的值 → 跟随**界面语言**；
    `zh`/`en` → 固定）；
  B 指令文本本身：中文那条是中文、英文那条不含中文，两条都**明说"专有名词保留原文"**
    （不写这句，模型会把「王小明」译成 Wang Xiaoming，全书人名跟着一起漂）；
  C ★ **真机看模型收什么**：用 `llm.add_listener` 抓请求事件，直接看
    `llm.chat()` **最终发出去的 messages** ——
      · 输出语言=en → 末尾带英文指令；
      · =zh → 带中文指令；
      · `purpose='compliance'`（合规检测）→ **不带**（它有严格的输出契约，不掺这一句）；
      · **JSON 那句必须还在最后**（顺序敏感：语言指令是在 `_ensure_json_instruction`
        之前注入的，这条判据钉的就是那个顺序）。
  D 落盘：`.nwsproj` 里存得下读得回；空值/认不出的值当 `auto`。
  E 界面：书斋与开卷向导都有这个下拉，选项是人话（键是字面量）；
    **两处共用同一份工厂**（`outlang.options()`），清单不会走样。
  F 换项目会跟着换（同一台机器上"英文稿推中文"与"中文稿推英文"互不干扰）。

跑法：`.venv\\Scripts\\python.exe tools/verify_output_lang.py`
产出：assets/screenshots/output_lang_report.json

English:
Verification: the **project-level "output language"** really does control all output.
User (2026-10-06):
"Set an output language in the project, so that **all output uses this language**, even if the
novel's original language is not this
(default support for Chinese and English is enough, add others later)"
The criteria are in three layers; missing any layer means it doesn't count as done:
  A Pure logic: how `util/outlang` parses (`auto`/empty/unrecognized value → follow the **UI language**;
    `zh`/`en` → fixed);
  B The instruction text itself: the Chinese one is Chinese, the English one contains no Chinese, and both **explicitly state "keep proper nouns in their original form"**
    (without this sentence, the model will translate 「王小明」 into Wang Xiaoming, and the whole book's names drift along with it);
  C ★ **On a real machine, see what the model receives**: use `llm.add_listener` to capture request events, and directly look at
    the **final messages sent out** by `llm.chat()` ——
      · output language=en → English instruction at the end;
      · =zh → Chinese instruction;
      · `purpose='compliance'` (compliance check) → **not included** (it has a strict output contract, don't mix in this sentence);
      · **the JSON sentence must still be last** (order-sensitive: the language instruction is injected
        before `_ensure_json_instruction`, and this criterion pins down exactly that order).
  D Persistence: `.nwsproj` can store and read it back; empty/unrecognized values are treated as `auto`.
  E UI: both the study and the opening wizard have this dropdown, and the options are human-readable (the keys are literals);
    **both places share the same factory** (`outlang.options()`), so the list won't drift.
  F Switching projects switches along (on the same machine, "English draft → Chinese" and "Chinese draft → English" don't interfere with each other).
How to run: `.venv\\Scripts\\python.exe tools/verify_output_lang.py`
Output: assets/screenshots/output_lang_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('UI_LANG', 'zh')

import gui.app_flet as G  # noqa: E402
from gui.app_flet import NovelWorldApp  # noqa: E402
from i18n import set_lang, t  # noqa: E402
from store.project import Project  # noqa: E402
from util import outlang  # noqa: E402
from llm.router import llm  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
CJK = re.compile(r'[\u4e00-\u9fff]')
ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


async def sent_messages(purpose: str, lang: str) -> list:
    """真调一次 `llm.chat()`，把它**最终发出去的 messages** 抓回来。
        English:
    Actually call `llm.chat()` once and capture its **final sent messages**.
    """
    outlang.set_from_project(lang)
    got: list = []

    def cb(ev):
        if ev.get('type') == 'request':
            got.append(ev.get('messages') or [])

    llm.add_listener(cb)
    try:
        await llm.chat('daily', [{'role': 'user', 'content': '请回答。'}],
                       purpose=purpose, json_mode=purpose != 'x')
    finally:
        llm.remove_listener(cb)
    return got[-1] if got else []


def last_text(msgs: list) -> str:
    return str((msgs[-1] or {}).get('content') or '') if msgs else ''


async def main(page: ft.Page):
    report: dict = {}
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    tmp = Path(tempfile.mkdtemp(prefix='nws_outlang_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    try:
        # ══════════ A. 解析逻辑 ══════════
        # [EN] ══════════ A. Parsing logic ══════════
        got: dict = {}
        for ui in ('zh', 'en'):
            set_lang(ui)
            for val in ('', 'auto', 'zh', 'en', 'kuai'):
                outlang.set_from_project(val)
                got[f'{ui}/{val or "空"}'] = outlang.resolve()
        set_lang('zh')
        outlang.set_from_project('')
        report['resolve'] = got
        ok('A：空 / auto / 认不出的值 → 跟随界面语言',
           got['zh/空'] == 'zh' and got['en/空'] == 'en'
           and got['zh/auto'] == 'zh' and got['en/auto'] == 'en'
           and got['zh/kuai'] == 'zh' and got['en/kuai'] == 'en', got)
        ok('A：zh / en 是**固定**的，不随界面语言动',
           got['zh/zh'] == 'zh' and got['en/zh'] == 'zh'
           and got['zh/en'] == 'en' and got['en/en'] == 'en', got)

        # ══════════ B. 指令文本 ══════════
        # [EN] ══════════ B. Instruction text ══════════
        outlang.set_from_project('en')
        en_d = outlang.directive()
        outlang.set_from_project('zh')
        zh_d = outlang.directive()
        report['directive'] = {'zh': zh_d, 'en': en_d}
        ok('B：输出=中文时，指令是中文且不含"English 那套"',
           bool(zh_d) and bool(CJK.search(zh_d)) and 'Output language' not in zh_d, zh_d[:60])
        ok('B：★ 输出=英文时，指令**一个中文都没有**',
           bool(en_d) and not CJK.search(en_d), en_d[:60])
        ok('B：两条都明说「专有名词保留原文」（不然人名会被意译/音译）',
           '保留原文' in zh_d and 'proper nouns' in en_d.lower(), '')

        # ══════════ C. 真机：模型到底收到什么 ══════════
        # [EN] ══════════ C. Real machine: what the model actually receives ══════════
        m_en = await sent_messages('summary', 'en')
        m_zh = await sent_messages('summary', 'zh')
        m_comp = await sent_messages('compliance', 'en')
        report['samples'] = {'en_tail': last_text(m_en)[-90:],
                             'zh_tail': last_text(m_zh)[-60:],
                             'compliance_tail': last_text(m_comp)[-90:]}
        ok('C：★ 输出=en 时，真正发出去的 messages 末尾带英文指令',
           en_d.strip()[-40:] in last_text(m_en), last_text(m_en)[-70:])
        ok('C：★ 输出=zh 时，末尾带中文指令',
           zh_d.strip()[-30:] in last_text(m_zh), last_text(m_zh)[-50:])
        ok('C：★ 合规检测（purpose=compliance）**不掺**这一句'
           '（它有严格的输出契约）',
           'Output language' not in last_text(m_comp)
           and '[Output language]' not in last_text(m_comp)
           and en_d.strip()[-30:] not in last_text(m_comp), last_text(m_comp)[-60:])
        ok('C：只挂在**最后一条 user 消息**上（没有新增 system 消息）',
           len(m_en) == len(m_zh) and all(
               (x.get('role') or '') == 'user' for x in m_en), [x.get('role') for x in m_en])

        # ★ **顺序判据**：语言指令必须在 `_ensure_json_instruction` **之前**注入，
        #   否则文本兜底的「请仅以 JSON 回答」会被挤到前面去、失去"最后一句"的分量。
        #   ⚠ 这一条**只有在关掉 JSON 能力时才有意义** ——
        #     `LLM_CAP_JSON_MODE=true`（默认值）时走的是 `response_format`，
        #     根本**不该**有那句文本（第一版判据没管这个前提，白红了一次）。
        # [EN] ★ **Ordering criterion**: the language instruction must be injected **before**
        # [EN] `_ensure_json_instruction`,
        # [EN] otherwise the text fallback "please answer in JSON only" gets pushed to the front and loses the
        # [EN] weight of the "last sentence".
        # [EN] ⚠ This item **is only meaningful when the JSON capability is turned off** ——
        # [EN] when `LLM_CAP_JSON_MODE=true` (the default), `response_format` is used,
        # [EN] and that text sentence **should not** exist at all (the first version of the criterion ignored
        # [EN] this premise and went red for nothing).
        saved_json = CFG.s('LLM_CAP_JSON_MODE')
        CFG.set('LLM_CAP_JSON_MODE', 'false')
        # ★★ 2026-10-26：**能力开关不一定来自 CFG**（2026-10-12 起由模型登记表解析，
        #   `llm/models.resolve()` 的 `caps` 优先于 `CFG.b()`）。本机登记表里那个模型写着
        #   "支持 JSON" ⇒ 把 CFG 改成 false 一点用都没有，「请仅以 JSON 回答」根本不出现，
        #   判据就红得莫名其妙 —— 而且**换台机器、或用户在「天机」里加一条模型记录，结果就变**。
        #   这一条要测的是 `_ensure_json_instruction` 的**顺序**，跟哪家服务商无关 ⇒
        #   临时让 `resolve()` 交白卷，强制走 CFG 那条老路。判据从此与机器无关。
        # [EN] ★★ The capability switch does **not** necessarily come from CFG (since 2026-10-12
        # [EN] it is resolved by the model registry, whose `caps` take precedence). If the local
        # [EN] registry entry says "JSON supported", flipping CFG does nothing, the fallback
        # [EN] sentence never appears, and the check goes red for no reason — and the result
        # [EN] changes with the machine. This item tests the **ordering** inside
        # [EN] `_ensure_json_instruction`, not any provider ⇒ blank out `resolve()` temporarily to
        # [EN] force the CFG path. The check is now machine-independent.
        from llm import models as _M
        _saved_resolve = _M.resolve
        _M.resolve = lambda *a, **kw: None
        try:
            m_fb = await sent_messages('summary', 'en')
        finally:
            _M.resolve = _saved_resolve
            CFG.set('LLM_CAP_JSON_MODE', saved_json)
        fb_tail = last_text(m_fb)
        report['fallback_tail'] = fb_tail[-60:]
        ok('C：★ 关掉 JSON 能力的模型 → 文本兜底那句「请仅以 JSON 回答」**仍在最后**',
           fb_tail.rstrip().endswith('不要包含其他文字。'), fb_tail[-50:])
        ok('C：★ 语言指令排在它**前面**（两条都在，顺序对）',
           en_d.strip()[-30:] in fb_tail
           and fb_tail.index(en_d.strip()[-30:]) < fb_tail.index('请仅以 JSON'),
           fb_tail[-90:])
        ok('C：JSON 能力开着时**不该**有那句文本兜底（走 response_format）',
           '请仅以 JSON' not in last_text(m_en), last_text(m_en)[-40:])

        # ══════════ D. 落盘 ══════════
        # [EN] ══════════ D. Persistence ══════════
        p_en = Project.create_new(CFG.projects_dir(), 'OutLangEN', output_lang='en')
        p_zh = Project.create_new(CFG.projects_dir(), 'OutLangZH', output_lang='zh')
        raw = (p_en.nwsproj_path).read_text(encoding='utf-8')
        back = Project.from_nwsproj(p_en.nwsproj_path)
        p_auto = Project.create_new(CFG.projects_dir(), 'OutLangAuto', output_lang='auto')
        raw_auto = p_auto.nwsproj_path.read_text(encoding='utf-8')
        report['nwsproj'] = [ln for ln in raw.splitlines() if '输出语言' in ln]
        ok('D：`.nwsproj` 里写了「输出语言=en」', '输出语言=en' in raw, raw[-80:])
        ok('D：读回来还是 en', getattr(back, 'output_lang', '') == 'en',
           getattr(back, 'output_lang', None))
        ok('D：auto 也落盘（存真值，不留空）', '输出语言=auto' in raw_auto, raw_auto[-60:])

        # ══════════ E. 界面 ══════════
        # [EN] ══════════ E. UI ══════════
        app._activate_project(p_en)
        set_lang('zh')
        app.show_project_settings()
        page.update()
        await asyncio.sleep(0.9)
        dlg = next((d for d in reversed(VU.open_dialogs(page))
                    if not isinstance(d, ft.SnackBar)), None)
        dd = next((c for c in VU.walk(dlg)
                   if getattr(c, '_field', None) is not None
                   and isinstance(c._field, ft.DropdownM2)
                   # ⚠ `VU.text_of()` 只看控件**自己的** `content` —— 对一个 Row 它返回空串，
                   #   所以这里要用 `all_texts`（第一版就是踩了这个，一直说"找不到下拉"）。
                   # [EN] ⚠ `VU.text_of()` only looks at the control's **own** `content` —— for a Row it returns an empty
                   # [EN] string,
                   # [EN] so here you have to use `all_texts` (the first version tripped on exactly this and kept saying
                   # [EN] "can't find the dropdown").
                   and t('输出语言') in VU.all_texts(c)), None) if dlg else None

        def opt_label(o) -> str:
            """下拉项**显示的文字**。`DropdownM2` 认 `content`；兼容老的 `text`。
                        English:
            The **displayed text** of the dropdown item. `DropdownM2` recognizes `content`; compatible with
            the old `text`.
            """
            for src in (getattr(o, 'content', None), getattr(o, 'text', None)):
                if isinstance(src, str) and src:
                    return src
                for x in VU.walk(src):
                    if isinstance(x, ft.Text) and x.value:
                        return str(x.value)
            return ''

        keys = [o.key for o in (dd._field.options if dd else [])]
        labels = [opt_label(o) for o in (dd._field.options if dd else [])]
        report['dropdown'] = {'keys': keys, 'labels': labels}
        ok('E：书斋里有「输出语言」下拉', dd is not None, '')
        ok('E：★ 选项键是**字面量** auto/zh/en（存盘值不随界面语言变）',
           keys == ['auto', 'zh', 'en'], keys)
        ok('E：选项显示名是人话（不是 auto/zh/en 裸值）',
           labels and all(x and x not in ('auto', 'zh', 'en') for x in labels), labels)
        # 两处共用一份工厂
        # [EN] Both places share one factory
        import inspect
        # ⚠ 它是**方法**，不是模块级函数 —— 要写 `NovelWorldApp.xxx`
        # （第一版写 `G._wizard_step2_settings`，AttributeError 直接把后面几条判据带走了）
        # [EN] ⚠ It is a **method**, not a module-level function —— you must write `NovelWorldApp.xxx`
        # [EN] (the first version wrote `G._wizard_step2_settings`, and the AttributeError took out all the
        # [EN] later criteria with it)
        src = inspect.getsource(G.NovelWorldApp._wizard_step2_settings)
        ok('E：★ 开卷向导里也有，且与书斋**共用同一份选项工厂**',
           'outlang.options()' in src and 'mk_dropdown' in src, src[:0])
        with open(APP_DIR / 'store' / 'project.py', encoding='utf-8') as f:
            pj = f.read()
        ok('E：项目文件里是 `输出语言` 这个键（沿用现有命名风格）',
           '"输出语言"' in pj and 'sec.get("输出语言"' in pj, '')
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()

        # ══════════ F. 换项目会跟着换 ══════════
        # [EN] ══════════ F. Switching projects switches along ══════════
        app._activate_project(p_zh)
        a = outlang.resolve()
        app._activate_project(p_en)
        b = outlang.resolve()
        report['switch'] = [a, b]
        ok('F：★ 切到 zh 项目 → zh；切到 en 项目 → en（互不干扰）',
           a == 'zh' and b == 'en', [a, b])
        outlang.set_from_project('')

        n_ok = sum(1 for i in ITEMS if i['ok'])
        report['items'] = ITEMS
        report['ok'] = n_ok == len(ITEMS)
        print(f'\n输出语言验证：{n_ok}/{len(ITEMS)}')
    except Exception:                                           # noqa: BLE001
        report['items'] = ITEMS
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
        print(report['fatal'])
    finally:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'output_lang_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        VU.safe_rmtree(tmp, ignore_errors=True)
        await shutdown(page, code=0 if report.get('ok') else 1)


if __name__ == '__main__':
    ft.run(main)
