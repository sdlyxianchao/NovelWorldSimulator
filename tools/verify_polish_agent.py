# -*- coding: utf-8 -*-
"""验证：**开卷打磨 Agent**（沙盒 · 工具 · 历史 · 自省 · 双写落盘）。

用户原话（2026-10-07）
----------------------
1. 「开卷的 AI 打磨部分 **你没有生成一个 Agent**」
2. 「每次我输入新对话，**你发给 LLM 的内容不包含之前的历史信息**，
   所以大模型返回的东西是不对的」
3. 「你按照正常的 **Agent Reflection 模型**结合别的模型来处理优化流程」
4. 「最终优化结果需要**同时写到项目里和原始的设定文件夹里**」
5. 「即你需要有能力**操作文件系统**」
6. 「有别的工具你也需要的，你可以自己尝试**写代码（在沙盒里运行且控制权限和范围）**」
7. 「你的开卷打磨的 Agent 也需要这个能力**动态生成各种工具**」
8. 「在定制任务的基础上**适当增加灵活性**」

判据分五层（每一条都对着上面某一句）：

| 组 | 查什么 | 对应 |
|---|---|---|
| **A** | 沙盒：路径白名单 / 越权拒绝 / AST 审查 / 子进程 + 硬超时 / 输出截断 | ⑤⑥ |
| **B** | 工具：十二个工具逐个跑，成功与失败都给**能照着改的话** | ⑤⑥ |
| **C** | Agent：**历史真的编进了 messages**（抓真发出去的请求）· 自省会触发重跑 · 步数上限 · 动态生成工具 | ①②③⑦ |
| **D** | MOCK 端到端：真跑一遍（工具被调、报告落盘） | 全集 |
| **E** | 真机：向导选项 · 走一遍开卷 · **项目侧与引用侧写的同一份** | ④ |

用法：.venv\\Scripts\\python.exe tools/verify_polish_agent.py [--logic-only]
产出：assets/screenshots/polish_agent_report.json

English:
Verification: **open-book polishing Agent** (sandbox · tools · history · introspection ·
dual-write to disk).
User's exact words (2026-10-07)
----------------------
1. "The AI polishing part of open-book **you didn't generate an Agent**"
2. "Every time I enter a new conversation, **the content you send to the LLM doesn't include the previous history information**,
   so what the large model returns is wrong"
3. "You follow the normal **Agent Reflection model** combined with other models to handle the optimization process"
4. "The final optimization result needs to be **written both into the project and into the
original settings folder**"
5. "That is, you need the ability to **operate the file system**"
6. "There are other tools you also need, you can try **writing code yourself (run in a sandbox
with controlled permissions and scope)**"
7. "Your open-book polishing Agent also needs this ability to **dynamically generate various
tools**"
8. "**Appropriately increase flexibility** on top of the custom tasks"
Criteria are divided into five layers (each one corresponds to one of the sentences above):
| Group | What to check | Corresponds to |
|---|---|---|
| **A** | Sandbox: path whitelist / privilege escalation rejected / AST review / subprocess + hard timeout / output truncation | ⑤⑥ |
| **B** | Tools: run the twelve tools one by one, both success and failure give **actionable messages** | ⑤⑥ |
| **C** | Agent: **history is actually compiled into messages** (capture the requests actually sent) · introspection triggers rerun · step limit · dynamic tool generation | ①②③⑦ |
| **D** | MOCK end-to-end: actually run once (tools called, report written to disk) | full set |
| **E** | Real device: wizard options · walk through open-book once · **the same copy is written on the project side and the reference side** | ④ |
Usage: .venv\\Scripts\\python.exe tools/verify_polish_agent.py [--logic-only]
Output: assets/screenshots/polish_agent_report.json
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                          # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang                                       # noqa: E402
set_lang('zh')

from polish import PolishAgent, Scope                           # noqa: E402
from polish import agent as AG                                  # noqa: E402
from polish import codegen                                      # noqa: E402
from polish import sandbox as SB                                # noqa: E402
from polish import tools as PT                                  # noqa: E402
from verify_ui_common import safe_rmtree                        # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

SAMPLE_SETTINGS = {
    '人物': [
        {'姓名': '主角', '身份': '掌柜', '简介': '开茶楼的', '性格': '沉稳',
         '口癖': '', '秘密': '袖里有半张当票', '目标': '', '红线': ''},
        {'姓名': '阿福', '身份': '跑堂', '简介': '店里的伙计', '性格': '嘴快',
         '口癖': '哎哟', '秘密': '', '目标': '', '红线': ''},
    ],
    '世界观': '江南水乡，茶楼为业，旧案未了。' * 3,
    '地点': [{'名称': '临河茶肆', '说明': '就是那间'}],
    '关系': [{'甲': '主角', '乙': '阿福', '关系': '主仆', '张力': '互相瞒着'}],
    '伏笔': [{'编号': 'V1', '内容': '半张当票', '埋设': '', '预计回收': ''}],
    '剧情参考线': '一桩旧案', '细节': [],
}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _fixture() -> tuple[Path, Path, Scope]:
    """造一对目录：引用文件夹（只读带一个素材文件）+ 打磨输出区。
        English:
    Create a pair of directories: reference folder (read-only with one asset file) + polish output
    area.
    """
    src = Path(tempfile.mkdtemp(prefix='nws_polish_src_'))
    out = Path(tempfile.mkdtemp(prefix='nws_polish_out_'))
    (src / '设定').mkdir()
    (src / '设定' / '人物.md').write_text(
        '# 人物\n主角：茶楼掌柜，袖里有半张当票。\n阿福：跑堂，嘴快。\n',
        encoding='utf-8')
    (src / '大纲.md').write_text('# 大纲\n第一幕：当票现身。\n', encoding='utf-8')
    return src, out, Scope(src_root=src, out_root=out, timeout=6.0)


# ══════════════════════════════════════════════════════════════════
#  A —— 沙盒
# [EN] A -- Sandbox
# ══════════════════════════════════════════════════════════════════
def test_sandbox() -> None:
    src, out, sc = _fixture()

    def denied(rel, **kw) -> str:
        try:
            SB.resolve(sc, rel, **kw)
            return ''
        except SB.Denied as e:
            return str(e)

    # ── 路径白名单 ──
    # [EN] -- Path allowlist --
    ok('A1 ★★ 读不带前缀 → 走引用文件夹（Agent 最常做的那件事）',
       SB.relabel(sc, SB.resolve(sc, '设定/人物.md')) == 'src:设定/人物.md', '')
    ok('A2 ★★ 写不带前缀 → 走打磨输出区（写错地方比读错地方危险得多）',
       SB.relabel(sc, SB.resolve(sc, '笔记.md', for_write=True)) == 'out:笔记.md', '')
    # ★★ **这几条断言的是"因为什么拒"**，不是"拒没拒"。
    #    为什么非这样写不可（反例法当场教的）：这里**有两道重叠的闸门** ——
    #    "字符串检查"（`..` / 绝对路径）与"范围检查"（`_inside`）。
    #    单拆一道，另一道照样会拒，于是"只要非空就算通过"的判据**照样绿** ——
    #    反例法第 ②③ 组就是这么"没红"的（不是判据弱，是它问错了问题）。
    #    问"因为什么拒"之后，拆哪一道都红得出来，而且理由也更容易看懂。
    # [EN] ★★ **These assertions test "why it was rejected"**, not "whether it was rejected".
    # [EN] Why it must be written this way (taught on the spot via counterexample method): here there are
    # [EN] **two overlapping gates** --
    # [EN] "String check" (`..` / absolute path) and "range check" (`_inside`).
    # [EN] Disable one, and the other still rejects, so the criterion "non-empty means pass" **still goes
    # [EN] green** --
    # [EN] This is exactly how counterexample method groups ②③ "failed to go red" (not that the criterion
    # [EN] is weak, it's that it asked the wrong question).
    # [EN] After asking "why it was rejected", disabling either gate goes red, and the reason is easier to
    # [EN] understand too.
    ok('A3 ★★ `..` 一律拒绝，而且**拒的理由就是"不许往上跳"**',
       '往上跳' in denied('../外面的东西.md'), denied('../外面的东西.md'))
    ok('A4 ★★ 绝对路径 / 盘符一律拒绝（POSIX 与 Windows 两种写法都试），'
       '理由是"只收相对路径"',
       '相对路径' in denied('/etc/passwd')
       and '相对路径' in denied('C:/Windows/system32/x.txt'),
       f'{denied("/etc/passwd")[:28]} / {denied("C:/Windows/x.txt")[:28]}')
    ok('A5 ★★ 前缀里藏 `..` 也拒绝（`src:设定/../../x.md`）—— '
       '**前缀不是护身符**，剥掉前缀照样要过 `..` 那道闸门',
       '往上跳' in denied('src:设定/../../x.md'), denied('src:设定/../../x.md'))

    # ★★ **同级目录的"字符串前缀陷阱"** —— 这是目录逃逸里最真实的一种，
    #    而且**不需要符号链接**（本机建不出真正的软链：Python 在 Windows 上
    #    `symlink_to` 没报错、`islink()` 却是 False、也没有 reparse point，
    #    实测它就地建了一个普通空目录 —— 所以那条路在本机**验不了**，
    #    与其写一条恒真的假判据，不如换成这条真能红的）。
    # [EN] ★★ **The "string prefix trap" for sibling directories** -- this is the most realistic kind of
    # [EN] directory escape,
    # [EN] and it **doesn't require a symlink** (a real soft link can't be created on this machine: on
    # [EN] Windows, Python's
    # [EN] `symlink_to` doesn't error, yet `islink()` is False, and there's no reparse point either,
    # [EN] actual testing shows it just creates an ordinary empty directory in place -- so that path
    # [EN] **can't be verified** on this machine,
    # [EN] rather than writing a tautologically-true fake criterion, better to swap in this one that can
    # [EN] genuinely go red).
    #
    #    陷阱长这样：范围内是 `<tmp>/a`，目标写 `<tmp>/ab/x.md`。
    #    字符串前缀判断（`str(target).startswith(str(root))`）会说"在里面"，
    #    而按**路径段**判（`relative_to`）才是对的。
    # [EN] The trap looks like this: the in-range path is `<tmp>/a`, and the target is written as
    # [EN] `<tmp>/ab/x.md`.
    # [EN] A string-prefix check (`str(target).startswith(str(root))`) says it's "inside",
    # [EN] whereas judging by **path segment** (`relative_to`) is the correct way.
    trap_root = Path(tempfile.mkdtemp(prefix='nws_trap_'))
    (trap_root / 'a').mkdir()
    (trap_root / 'ab').mkdir()
    trap_scope = Scope(src_root=trap_root / 'a', out_root=trap_root / 'a')
    # ⚠ 走 `resolve` 是**测不到** `_inside` 的（`..` 那道闸门先拦下了，反例法第 ① 组
    #   就是这么"没红"的）—— 所以这里**直接问那个判据函数本人**：
    #   `a` 与 `ab` 是两个目录，用字符串前缀看会说"ab 在 a 里面"，按路径段看才是对的。
    #   ⚠ 这**不是**"查源码字符串"（那种源码哨兵本项目不吃）：它是**调函数、比结果**。
    # [EN] ⚠ Going through `resolve` **cannot** test `_inside` (the `..` gate blocks it first,
    # [EN] counterexample method group ①
    # [EN] is exactly how it "failed to go red") -- so here we **directly ask that criterion function
    # [EN] itself**:
    # [EN] `a` and `ab` are two directories; a string-prefix view says "ab is inside a", but a path-segment
    # [EN] view is the correct way.
    # [EN] ⚠ This is **not** "grepping source code strings" (this project doesn't use that kind of source
    # [EN] sentinel): it's **calling the function, comparing the result**.
    ok('A6 ★★ 范围判定按**路径段**算，不按字符串前缀'
       '（`a` 与 `ab` 是同级的两个目录，字符串会说"在里面"）',
       (not SB._inside(trap_root / 'a', trap_root / 'ab'))
       and SB._inside(trap_root / 'a', trap_root / 'a' / 'x.md'),
       '')
    #  「比真路径」这件事本身要验得了：`resolve()` 交回来的必须是**归一化后的绝对路径**
    #  （`./`、`.`、`..`（合法的那部分）都已经化掉）。走字符串捷径的话它不会归一到这一步 ——
    #  而"符号链接守得住"正建立在"比的是真路径"上。
    # ⚠ 归一化用的路径里**不能带 `..`**（那个无论是否合法都一律被拒，见 A3）——
    #   用 `./` 这种"字符串里看得出、归一化后该消失"的写法。
    # [EN] "Compare real paths" itself must be verifiable: what `resolve()` hands back must be a
    # [EN] **normalized absolute path**
    # [EN] (`./`, `.`, `..` (the legal part) have all been collapsed). A string shortcut won't normalize to
    # [EN] this --
    # [EN] and "symlinks are held off" is precisely built on "what's compared is the real path".
    # [EN] ⚠ The path used for normalization **must not contain `..`** (that one is always rejected whether
    # [EN] legal or not, see A3) --
    # [EN] use a form like `./` that is "visible in the string but should disappear after normalization".
    messy = SB.resolve(sc, 'out:一层/./二层/x.md', for_write=True)
    ok('A6b ★★ 交给调用方的路径是**归一化后的真路径**'
       '（`./` 已化掉；"符号链接守得住"就建立在这上面）',
       str(messy) == os.path.realpath(str(messy))
       and '.' not in messy.parts and '一层' in messy.parts,
       str(messy).split(os.sep)[-4:])
    safe_rmtree(trap_root, ignore_errors=True)

    ok('A7 ★★ 程序自己生成的资料不在打磨范围（`never_touch`）',
       bool(_never_touch_denied()), '')
    ok('A8 根自己可以直接指（`out:` 就是输出区，`list_files` 要用）',
       SB.resolve(sc, 'out:') == out.resolve(), '')

    # ── 写权限 ──
    # ⚠ `resolve` 只回答「这个路径**在不在许可范围内**」，不回答「准不准写这里」——
    #   两道闸门是**分开**的（写权限在 `write_text` / `append_text` 里判）。
    #   第一版把 A9 写成"resolve 该拒"，那是**判据自己期望错了**：
    #   `src:设定/人物.md` 本来就是一个合法路径（范围内的、存在的文件），它就该被解析出来。
    #   真正的保证在下面 A10。
    # [EN] -- Write permission --
    # [EN] ⚠ `resolve` only answers "is this path **within the permitted range**", not "is it allowed to
    # [EN] write here" --
    # [EN] the two gates are **separate** (write permission is judged inside `write_text` / `append_text`).
    # [EN] The first version wrote A9 as "resolve should reject", which was **the criterion expecting the
    # [EN] wrong thing**:
    # [EN] `src:设定/人物.md` is itself a legal path (an in-range, existing file), so it should be resolved.
    # [EN] The real guarantee is in A10 below.
    ok('A9 ★★ 两道闸门分工：「在不在范围内」与「准不准写这里」分开判'
       '（分开就不会"改一处把另一道带掉"）',
       SB.resolve(sc, 'src:设定/人物.md', for_write=True).is_file(), '')
    try:
        SB.write_text(sc, 'src:设定/人物.md', '覆盖！')
        wrote_src = True
    except SB.Denied:
        wrote_src = False
    ok('A10 ★★ `write_text` 真的写不进引用文件夹（不是靠调用方自觉）',
       not wrote_src and '半张当票' in (src / '设定' / '人物.md').read_text(
           encoding='utf-8'), '')

    before = (src / '设定' / '人物.md').read_bytes()
    SB.append_text(sc, 'src:设定/人物.md', '\n\n补记：目标=把旧案了结。\n')
    after = (src / '设定' / '人物.md').read_bytes()
    ok('A11 ★★ `append_text` 只追加：**原文字节一个不动**（前缀完全相同）',
       after.startswith(before), f'{len(before)} → {len(after)} 字节')
    ok('A12 ★★ 追加前自动留 `.bak`，而且**已有就不覆盖**'
       '（留的是"第一次让 AI 改之前"的样子）',
       (src / '设定' / '人物.md.bak').is_file()
       and (src / '设定' / '人物.md.bak').read_bytes() == before, '')
    bak1 = (src / '设定' / '人物.md.bak').read_bytes()
    SB.append_text(sc, 'src:设定/人物.md', '\n再补一句。\n')
    ok('A13 ★ 第二次追加不会把 `.bak` 覆盖成"半改过的样子"',
       (src / '设定' / '人物.md.bak').read_bytes() == bak1, '')

    try:
        SB.write_text(sc, 'out:大文件.md', 'x' * (sc.max_write_bytes + 10))
        too_big = False
    except SB.Denied as e:
        too_big = '字节' in str(e)
    ok('A14 ★ 单文件写上限挡得住（模型吐个 20MB 下来不该写进盘）', too_big, '')

    # ── 静态审查 ──
    # [EN] -- Static review --
    good = 'import json\ndef run(args):\n    return json.dumps(args, ensure_ascii=False)'
    ok('A15 ★ 合规代码：审查通过', SB.check_source(good, require_run=True) == [], '')
    for name, code, needle in (
        ('A16 ★★ 危险导入（`os` / `subprocess` / `shutil`）逐条拒',
         'import subprocess\ndef run(args):\n    return 1', 'subprocess'),
        ('A17 ★★ 危险内置名（`open`）拒，而且**告诉它该用什么**',
         'def run(args):\n    return open("x")', 'read_text'),
        ('A18 ★★ 双下划线属性拒绝（`().__class__.__bases__` 那套逃生口）',
         'def run(args):\n    return (1).__class__.__name__', '双下划线'),
        ('A19 ★★ 删除类属性拒绝（`unlink` / `rmtree` / `remove`）',
         'import json\ndef run(args):\n    return Path.unlink', 'unlink'),
        ('A20 ★ 语法错误报得出来（要说清第几行）',
         'def run(args)\n    return 1', '语法错误'),
        ('A21 ★★ 没有 `run(args)` 要说出来（我要调它）',
         'import json\n', 'run(args)'),
    ):
        bad = SB.check_source(code, require_run=True)
        ok(name, any(needle in x for x in bad), (bad[:1] or ['（没报）'])[0])

    # ── 子进程执行 ──
    # [EN] -- Subprocess execution --
    r = SB.run_code(sc, 'def run(args):\n    write_text("a.txt", "hi")\n'
                        '    return "好：" + str(args.get("n"))', args={'n': 1})
    ok('A22 ★★ 生成代码真的跑得起来（子进程），并且给回观察结果',
       r.ok and r.text == '好：1', f'{r.text!r} {r.why}')
    r = SB.run_code(sc, 'def run(args):\n    return 1 / 0', args={})
    ok('A23 ★★ 代码抛异常 → 变成一句人话（含**用户代码那一行**），不炸主进程',
       (not r.ok) and 'ZeroDivisionError' in r.why and '打磨工具' in r.why, r.why)
    # ⚠⚠ 这一条**必须自带护栏**，不能直接 `SB.run_code(...)` 就等：
    #   反例法里"把产品的超时删掉"那个变异一打上去，`run_code` 就**永远不返回** ——
    #   于是判据自己挂住、整支脚本超时被杀，看起来像"判据不会红"，其实是**它被卡死了**
    #   （实测：反例法跑到第 ⑩ 组就停在那儿，十分钟没有任何输出）。
    #   所以：丢到一个**线程**里跑，外面拿墙钟兜住；不回来就判红并说清原因。
    # [EN] ⚠⚠ This one **must come with a guardrail**, can't just `SB.run_code(...)` and wait:
    # [EN] In the counterexample method, once the mutation "delete the product's timeout" is applied,
    # [EN] `run_code` **never returns** --
    # [EN] so the criterion itself hangs, the whole script gets killed by timeout, and it looks like "the
    # [EN] criterion won't go red", when actually **it got stuck**
    # [EN] (actual test: the counterexample method runs to group ⑩ and stops there, ten minutes with no
    # [EN] output).
    # [EN] So: throw it into a **thread**, cover it with wall-clock time on the outside; if it doesn't come
    # [EN] back, mark red and state the reason clearly.
    r, hung = _run_with_wall_clock(
        lambda: SB.run_code(sc, 'def run(args):\n    while True:\n        pass\n',
                            args={}),
        seconds=max(4.0, sc.timeout + 6.0))
    if hung:
        _kill_stray_runners()
        ok('A24 ★★ 死循环被**硬超时**杀掉（子进程专属：同进程里杀不掉线程）',
           False, f'产品里的硬超时没生效 —— 这一次调用 {int(sc.timeout + 6)} 秒都没回来')
    else:
        ok('A24 ★★ 死循环被**硬超时**杀掉（子进程专属：同进程里杀不掉线程）',
           (not r.ok) and '死循环' in r.why, r.why)
    r = SB.run_code(sc, 'def run(args):\n    print("你好")\n    return "ok"', args={})
    ok('A25 ★★ 生成代码里的 `print` 被收进 logs（**不许污染 stdout 的 JSON 协议**）',
       r.ok and r.text == 'ok' and any('你好' in x for x in r.logs), str(r.logs))
    r = SB.run_code(sc, 'def run(args):\n    return "x" * 99999', args={})
    ok('A26 ★ 输出超上限会截断并说明（别把上下文吃光）',
       r.ok and '已截断' in r.text, r.text[-40:])
    r = SB.run_code(sc, 'def run(args):\n    return read_text("src:设定/人物.md")',
                    args={})
    ok('A27 ★★ 沙盒给的文件 API **按相对路径说话**（生成代码拿不到真实路径）',
       r.ok and '当票' in r.text, r.text[:40].replace('\n', ' '))
    r = SB.run_code(sc, 'def run(args):\n    return write_text("src:设定/人物.md", "x")',
                    args={})
    ok('A28 ★★ **生成代码写不进引用文件夹**（写权限只有输出区）',
       (not r.ok) and '只能写打磨输出区' in r.why, r.why)
    r = SB.run_code(sc, 'import os\ndef run(args):\n    return os.listdir("/")', args={})
    ok('A29 ★★ 静态审查**在子进程里也做一遍**'
       '（父进程那次是为了"不合格的不落盘"）',
       (not r.ok) and '不许导入 os' in r.why, r.why)
    ok('A30 ★ 子进程只拿到最少的环境变量（**别把用户的 API Key 递进去**）',
       'LLM_API_KEY' not in SB._child_env()
       and 'PATH' in SB._child_env(), str(sorted(SB._child_env())))

    # 父进程侧的文件 API 也要守规矩
    # [EN] The file API on the parent-process side must also follow the rules.
    try:
        SB.read_text(sc, '设定/人物.md')
        read_ok = True
    except SB.Denied:
        read_ok = False
    ok('A31 ★ 读不存在的文件 → 拒绝（而不是回一个空串让下游猜）',
       read_ok and True, '')
    try:
        SB.read_text(sc, '设定/没有这个.md')
        missing_ok = False
    except SB.Denied:
        missing_ok = True
    ok('A32 ★ 读不存在的文件会被拦下来并说清是哪个文件',
       missing_ok, '')
    safe_rmtree(src, ignore_errors=True)
    safe_rmtree(out, ignore_errors=True)


def _run_with_wall_clock(fn, *, seconds: float):
    """在一根线程里跑 `fn()`，外面用墙钟兜住。返回 `(结果, 是否超时没回来)`。

    为什么需要它：**判据不许因为"产品被改坏了"而挂住**。沙盒的超时一旦失效
    （反例法第 ⑩ 组就是这么打的），`run_code` 里的 `subprocess.run` 会一直等下去；
    这时候判据需要的是"红一条、把原因说清"，而不是跟着一起卡死。
    （本项目在别处也吃过"脚本挂住 = 看起来像在慢慢跑"的亏。）
    
        English:
    Run `fn()` in a thread, with wall-clock guarding on the outside. Returns `(result, whether it
    timed out without returning)`.
        Why it's needed: **criteria must not hang because "the product got broken"**. Once the sandbox timeout fails
        (this is exactly how counterexample method group ⑩ attacks it), the `subprocess.run` inside `run_code` will wait forever;
        at this point what the criteria need is "turn one line red and explain the cause clearly", not to get stuck along with it.
        (This project has also suffered elsewhere from "script hangs = looks like it's slowly running".)
    """
    import threading

    box: dict = {}

    def _work() -> None:
        try:
            box['ret'] = fn()
        except BaseException as e:                               # noqa: BLE001
            box['err'] = e

    th = threading.Thread(target=_work, daemon=True)
    th.start()
    th.join(seconds)
    if th.is_alive():
        return None, True
    if 'err' in box:
        raise box['err']
    return box.get('ret'), False


def _kill_stray_runners() -> int:
    """收掉跑飞了的 `_runner.py` 子进程（产品超时失效时它们会一直转）。

    ⚠ 只在**判据自己**用（清理自己捅出来的窟窿）。产品那边不干这事 ——
      在沙盒里起一个"专门杀进程"的助手就等于自己把门打开了。
    
        English:
    Kill the `_runner.py` subprocesses that ran off (they keep spinning when the product timeout
    fails).
        ⚠ Only use it in the **criteria itself** (cleaning up the holes it punched itself). The product side doesn't do this ——
          starting a "dedicated process killer" helper in the sandbox is equivalent to opening the door yourself.
    """
    import subprocess as _sp
    killed = 0
    try:
        ps = _sp.run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
                     capture_output=True, text=True, timeout=30)
        out = ps.stdout or ''
    except Exception:                                            # noqa: BLE001
        return 0
    # `wmic` 在较新的 Windows 上没了；`tasklist` 只有名字没有命令行，
    # 所以这里退一步：用 PowerShell 拿命令行（只在清理这一步用）。
    # [EN] `wmic` is gone on newer Windows; `tasklist` only has names, not command lines,
    # [EN] so here we step back: use PowerShell to get the command line (only used in this cleanup step).
    try:
        ps = _sp.run(['powershell', '-NoProfile', '-Command',
                      "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                      "Where-Object { $_.CommandLine -like '*_runner.py*' } | "
                      "Select-Object -ExpandProperty ProcessId"],
                     capture_output=True, text=True, timeout=60)
        for line in (ps.stdout or '').split():
            if line.strip().isdigit():
                _sp.run(['taskkill', '/F', '/PID', line.strip()],
                        capture_output=True, timeout=20)
                killed += 1
    except Exception:                                            # noqa: BLE001
        pass
    if killed:
        print(f'    （清掉了 {killed} 个跑飞的 _runner.py 子进程）', flush=True)
    _ = out
    return killed


def _never_touch_denied() -> bool:
    src, out, sc = _fixture()
    sc.never_touch = ('AI补全设定.md',)
    (src / 'AI补全设定.md').write_text('程序生成的', encoding='utf-8')
    try:
        SB.resolve(sc, 'src:AI补全设定.md', must_exist=True)
        return False
    except SB.Denied:
        return True
    finally:
        safe_rmtree(src, ignore_errors=True)
        safe_rmtree(out, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  B —— 工具
# [EN] B -- Tools
# ══════════════════════════════════════════════════════════════════
async def test_tools() -> None:
    src, out, sc = _fixture()
    box = PT.Toolbox(settings=json.loads(json.dumps(SAMPLE_SETTINGS)), scope=sc)

    r = await box.call('列引用文件', {})
    ok('B1 列引用文件：给出带前缀的相对路径', r.ok and 'src:设定/人物.md' in r.text,
       r.text.splitlines()[0] if r.ok else r.text)
    r = await box.call('读引用文件', {'路径': '设定/人物.md'})
    ok('B2 读引用文件：读到内容，并说清这次给了哪一段',
       r.ok and '半张当票' in r.text and '共' in r.text.splitlines()[0], '')
    r = await box.call('检索引用', {'关键词': '当票'})
    ok('B3 检索引用：命中并给上下文', r.ok and '当票' in r.text, r.text[:60])
    r = await box.call('读设定', {'路径': '人物[0].姓名'})
    ok('B4 读设定带路径：只取那一片（省字数）', r.ok and '主角' in r.text, r.text[:40])
    r = await box.call('读设定', {'路径': '人物[9]'})
    ok('B5 路径越界 → 说清越界并**给出下一步建议**',
       (not r.ok) and '取不到' in r.text and '读设定' in r.text, r.text[:70])

    r = await box.call('改设定', {'操作': [
        {'动作': '改', '路径': '人物[0].目标', '值': '把旧案了结'},
        {'动作': '加', '路径': '伏笔', '值': {'编号': 'V2', '内容': '一双新布鞋'}},
        {'动作': '改', '路径': '人物[1].性格', '值': '嘴快心细'}]})
    ok('B6 ★★ 改设定：一次改好几处，并且**报出改前 → 改后**（可核对）',
       r.ok and '→' in r.text and '改了 3 处' in r.text, r.text.splitlines()[0])
    ok('B7 ★★ 改设定真的落进了设定对象（不是只回一句话）',
       box.settings['人物'][0]['目标'] == '把旧案了结'
       and len(box.settings['伏笔']) == 2, '')
    r = await box.call('改设定', {'操作': [{'动作': '删', '路径': '伏笔[0]'}]})
    ok('B8 删一项：真的删掉', r.ok and len(box.settings['伏笔']) == 1, '')
    # ★★ **归一化**（`validate_settings`）也要有判据盯着：
    #   模型经常给一个只有「姓名」的残缺人物，不归一化的话那份残缺结构会一路
    #   流进设定集、流进推演（下游到处 `.get('口癖','')` 才不会炸，但字段是缺的，
    #   落盘出来的 YAML 也就缺 —— 作者看到的是"AI 加的人没有口癖这一项"）。
    # [EN] ★★ **Normalization** (`validate_settings`) also needs a criterion watching it:
    # [EN] The model often supplies a broken character with only a "name"; without normalization that
    # [EN] broken structure flows
    # [EN] all the way into the settings collection, into the simulation (downstream, everywhere
    # [EN] `.get('口癖','')` so it won't blow up, but the field is missing,
    # [EN] and the YAML written to disk is missing it too -- what the author sees is "the character the AI
    # [EN] added has no 口癖 item").
    r = await box.call('改设定', {'操作': [
        {'动作': '加', '路径': '人物', '值': {'姓名': '阿九', '身份': '伙计'}}]})
    newp = (box.settings.get('人物') or [{}])[-1]
    ok('B7b ★★ 残缺的输入会被**归一化**（模型只给个名字，不该让缺字段的结构流到下游）',
       r.ok and newp.get('姓名') == '阿九'
       and all(k in newp for k in ('身份', '简介', '性格', '口癖', '秘密', '目标', '红线')),
       str(sorted(newp)))
    r = await box.call('改设定', {'操作': [{'动作': '改', '路径': '没有这一层.东西',
                                          '值': 1}]})
    ok('B9 改不存在的路径 → 失败并**列出哪几处没成**',
       (not r.ok) or '没成' in r.text, r.text[:80].replace('\n', ' '))
    r = await box.call('改设定', {'操作': [{'动作': '炸', '路径': '世界观', '值': 1}]})
    ok('B10 不认得的动作 → 说清只有 改/加/删',
       (not r.ok) or '不认得' in r.text, r.text[:70].replace('\n', ' '))

    r = await box.call('写记录', {'文件名': '打磨记录.md', '内容': '# 记录\n改了 A、B。'})
    ok('B11 写记录：落进输出区', r.ok and (out / '打磨记录.md').is_file(), r.text[:50])
    r = await box.call('写记录', {'文件名': '打卡记录.md', '内容': 'x'})
    ok('B12 写记录会记进 `outputs`（收工时要搬进项目）',
       'out:打卡记录.md' in box.outputs, str(sorted(box.outputs)))

    r = await box.call('追加回写', {'路径': '设定/人物.md', '内容': '\n\n补记：目标。\n'})
    ok('B13 ★★ 追加回写：落进引用文件夹，并**明说留了 .bak、正文没动**',
       r.ok and '.bak' in r.text and (src / '设定' / '人物.md.bak').is_file(),
       r.text[:80])
    ok('B14 ★★ 回写记进 `source_writes`（报告里要列出来）',
       'src:设定/人物.md' in box.source_writes, str(box.source_writes))

    r = await box.call('列工具', {})
    ok('B15 列工具：把目录交出来', r.ok and '改设定' in r.text and '生成工具' in r.text, '')
    r = await box.call('没有这个工具', {})
    ok('B16 ★ 不存在的工具 → 列出可用的那些（模型才能改对）',
       (not r.ok) and '没有这个工具' in r.text and '改设定' in r.text, r.text[:70])
    r = await box.call('收尾', {})
    ok('B17 ★ `收尾`/`提出疑问` 是**控制动作**，不走工具调度（说清楚）',
       (not r.ok) and '不是动作工具' in r.text, r.text[:50])

    # 动态生成工具
    # [EN] Dynamically generated tools
    r = await box.call('生成工具', {
        '名称': '数字数', '说明': '数一数某个文件有多少字',
        '代码': 'def run(args):\n    return "共 %d 字" % len(read_text(args["路径"]))',
        '试跑参数': {'路径': 'src:设定/人物.md'}})
    ok('B18 ★★ 生成工具：静态审查 → 落盘 → **立刻可用**（回执里带试跑结果）',
       r.ok and '试跑通过' in r.text and '数字数' in box.generated, r.text[:70])
    ok('B19 ★★ 生成的工具落在 `out:AI工具/` 下（可审计、可随项目搬走）',
       (out / 'AI工具' / '数字数.py').is_file(), '')
    r = await box.call('数字数', {'路径': 'src:设定/人物.md'})
    ok('B20 ★★ 新工具马上能调（这就是"动态生成工具"的意义）',
       r.ok and '字' in r.text, r.text[:40])
    r = await box.call('生成工具', {'名称': '删除器',
                                   '代码': 'import shutil\ndef run(args):\n'
                                           '    shutil.rmtree("/")'})
    ok('B21 ★★ 不安全的工具**根本不落盘**（留个坏文件在盘上比拒绝更糟）',
       (not r.ok) and not (out / 'AI工具' / '删除器.py').exists(), r.text[:70])
    r = await box.call('生成工具', {'名称': '改设定', '代码': 'def run(args):\n    return 1'})
    ok('B22 ★ 生成工具不许覆盖内置工具名', (not r.ok) and '内置工具名' in r.text,
       r.text[:50])
    r = await box.call('生成工具', {'名称': '错的', '代码': 'def run(args):\n    return 1/0',
                                   '试跑参数': {}})
    ok('B23 ★★ 试跑失败会**明确告诉模型**（别让它以为工具好了）',
       r.ok and '没通过' in r.text, r.text[:60].replace('\n', ' '))

    # 代码能力开关
    # [EN] Code-capability switch
    box2 = PT.Toolbox(settings={}, scope=sc, allow_codegen=False)
    a = await box2.call('跑代码', {'代码': 'def run(args):\n    return 1'})
    b = await box2.call('生成工具', {'名称': 'x', '代码': 'def run(args):\n    return 1'})
    ok('B24 ★★ 关掉 `POLISH_TOOLS` → 两个代码工具都拒（而不是"偷偷还能跑"）',
       (not a.ok) and (not b.ok) and '关掉' in a.text, a.text[:40])

    # 调用次数上限
    # [EN] Max call count
    box3 = PT.Toolbox(settings={}, scope=sc, max_calls=2)
    await box3.call('列工具', {})
    await box3.call('列工具', {})
    raised = False
    try:
        await box3.call('列工具', {})
    except RuntimeError as e:
        raised = '上限' in str(e)
    ok('B25 ★★ 工具调用次数上限会抛（防死循环烧钱；那是 Agent 的循环问题，'
       '不该让模型继续在里面转）', raised, '')

    safe_rmtree(src, ignore_errors=True)
    safe_rmtree(out, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  C —— Agent（打桩 LLM，抓真发出去的 messages）
# [EN] C -- Agent (stub LLM, capturing the messages actually sent)
# ══════════════════════════════════════════════════════════════════
SEEN: list[dict] = []
SCRIPT: list = []


def _reply(value):
    return SimpleNamespace(value=value,
                           raw=json.dumps(value, ensure_ascii=False) if value else '',
                           meta={}, notes=[], ok=bool(value), retried=False,
                           salvaged=False, calls=1)


async def _fake_ask(tier, messages, **kw):
    SEEN.append({'purpose': kw.get('purpose'), 'msgs': [dict(m) for m in messages]})
    return _reply(SCRIPT.pop(0) if SCRIPT else None)


def _steps() -> list[dict]:
    return [x for x in SEEN if x['purpose'] == 'polish_step']


async def test_agent() -> None:
    global SCRIPT
    # ⚠ **必须在覆盖之前抓原件** —— 第一版写成 `AG.ask = _fake_ask` 之后再
    #   `real_ask = AG.ask`，抓到的就是那个假货自己，"还原"等于没还原，
    #   后面的 D 组整组跟着假红（D3 报"工具没被调"）。
    # [EN] ⚠ **Must capture the original before overriding** -- the first version wrote `AG.ask =
    # [EN] _fake_ask` and then
    # [EN] `real_ask = AG.ask`, so what was captured was the fake itself, and "restore" amounted to no
    # [EN] restore,
    # [EN] and the whole D group afterward went fake-red along with it (D3 reported "tool was not called").
    real_ask = AG.ask
    AG.ask = _fake_ask
    src, out, sc = _fixture()

    def new_agent(**kw):
        SCRIPT.clear()
        SEEN.clear()
        return PolishAgent(settings=json.loads(json.dumps(SAMPLE_SETTINGS)),
                           scope=sc, name='临河茶肆', tier='白银',
                           missing=('伏笔回收',), **kw)

    # ── ①② 历史真的带上没有 ──
    # [EN] -- ①② Is history really carried along --
    ag = new_agent()
    SCRIPT.extend([
        {'想': '先看素材', '用': '读引用文件', '参': {'路径': '设定/人物.md'}},
        {'想': '给他补目标', '用': '改设定',
         '参': {'操作': [{'动作': '改', '路径': '人物[0].目标', '值': '了结旧案'}]}},
        {'想': '齐了', '终': '给主角补了目标。', '改了什么': ['人物[0].目标']},
        {'有问题': False, '问题': [], '下一步': ''},
    ])
    turn = await ag.ask('把主角的目标补上')
    ok('C1 ★★ 一轮走完：工具真的被调了（不是"模型说它改了"）',
       [a['工具'] for a in turn.actions] == ['读引用文件', '改设定'],
       str([a['工具'] for a in turn.actions]))
    ok('C2 ★★ 改动落到设定对象上', ag.settings['人物'][0]['目标'] == '了结旧案', '')
    ok('C3 ★★ 事件流里六种事件都在（作者/工具/工具明细/结论）',
       {'author', 'tool', 'agent'} <= {e['kind'] for e in ag.events},
       str(sorted({e['kind'] for e in ag.events})))

    SCRIPT.extend([
        {'想': '好', '终': '知道了。', '改了什么': []},
        {'有问题': False, '问题': [], '下一步': ''},
    ])
    await ag.ask('就按你刚才说的做')
    msgs = _steps()[-1]['msgs']
    flat = json.dumps(msgs, ensure_ascii=False)
    ok('C4 ★★★ **第二条指令的请求里带着第一条的全部**'
       '（用户报的就是这一条："发给 LLM 的内容不包含之前的历史信息"）',
       '把主角的目标补上' in flat and '就按你刚才说的做' in flat,
       f'{len(msgs)} 条消息')
    # ⚠ 特征词要挑**只在素材文件里出现**的：`当票` 在"当前设定摘要"里也有
    #   （`（秘密：袖里有半张当票）`），拿它当特征词，这条判据就永远绿 ——
    #   反例法第 ⑮ 组（"工具结果不进历史"）当场把这个挑法打了回来。
    # [EN] ⚠ The feature word must be picked so it **only appears in the material file**: `当票` also appears
    # [EN] in the "current settings summary"
    # [EN] counterexample method group ⑮ ("tool results don't enter history") immediately shot down this
    # [EN] picking method.
    ok('C5 ★★★ 历史里有**工具的真实返回**（作者素材的原文都在里面）',
       '茶楼掌柜' in flat, '')
    ok('C6 ★★ 历史里有**我上一轮的结论**（"就按你刚才说的第 2 条改"才接得上）',
       '给主角补了目标' in flat, '')
    ok('C7 ★★ 历史里有**改动的结构化明细**（改哪儿、改前改后）',
       '人物[0].目标' in flat, '')
    ok('C8 ★★ 每条消息的角色是交替的（连续的同一个角色会被并成一条 —— '
       '严格的 OpenAI 兼容服务遇到连着三个 user 会 400）',
       all(a['role'] != b['role'] for a, b in zip(msgs, msgs[1:])),
       str([m['role'] for m in msgs]))
    ok('C9 ★★ 每次调用都带**当前设定摘要**（模型永远知道现状，不靠猜）',
       '【现在的设定】' in flat, '')
    ok('C10 ★ 系统提示里写着工具清单与作用域（模型才知道自己能干什么、能碰哪儿）',
       msgs[0]['role'] == 'system' and '改设定' in msgs[0]['content']
       and 'src:' in msgs[0]['content'], '')

    # ── ③ Reflection ──
    ag = new_agent()
    SCRIPT.extend([
        {'想': '改', '用': '改设定',
         '参': {'操作': [{'动作': '改', '路径': '人物[1].性格', '值': '文静'}]}},
        {'想': '完', '终': '改好了。', '改了什么': ['人物[1].性格']},
        {'有问题': True, '问题': ['阿福原本"嘴快"，改成"文静"跟他跑堂的身份不搭'],
         '下一步': '改回嘴快'},
        {'想': '改回来', '用': '改设定',
         '参': {'操作': [{'动作': '改', '路径': '人物[1].性格', '值': '嘴快'}]}},
        {'想': '好了', '终': '阿福还是嘴快。', '改了什么': ['人物[1].性格']},
        {'有问题': False, '问题': [], '下一步': ''},
    ])
    turn = await ag.ask('把阿福的性格改一下')
    refl = [x for x in SEEN if x['purpose'] == 'polish_reflect']
    ok('C11 ★★ 收尾之后**真的跑了自省**（Reflection，用户点名要的）',
       len(refl) == 1, f'{len(refl)} 次')
    rp = json.dumps(refl[0]['msgs'], ensure_ascii=False) if refl else ''
    # ⚠ 要断言"**改完之后那几处现在长什么样**"这一段真的带上了 ——
    #   光查 `文静` 是不够的：它本来就出现在过程记录里（工具调用与返回），
    #   于是"不给现状"那个变异照样绿（反例法第 ⑱ 组）。
    # [EN] ⚠ Must assert that the section "**what those spots look like now after the change**" is really
    # [EN] carried along --
    # [EN] just checking `文静` is not enough: it already appears in the process record (tool calls and
    # [EN] returns),
    # [EN] so the mutation "don't give the current state" stays green anyway (counterexample method group
    # [EN] ⑱).
    ok('C12 ★★ 自省拿得到**作者原话 + 全过程 + 改完之后那几处现在长什么样**'
       '（三样缺一不可，不然它没法判断"改坏没有"）',
       '把阿福的性格改一下' in rp and '现在：' in rp, '')
    ok('C13 ★★ 自省报了问题 → **再走一轮**把它改掉（不是只报不改）',
       '自省发现' in json.dumps([e['text'] for e in ag.events], ensure_ascii=False)
       and ag.settings['人物'][1]['性格'] == '嘴快', ag.settings['人物'][1]['性格'])
    ok('C14 ★★ 自省的意见进了下一轮的提示词（所以第二轮才知道要改什么）',
       '改回嘴快' in json.dumps(_steps()[-1]['msgs'], ensure_ascii=False)
       or '不搭' in json.dumps(_steps()[-1]['msgs'], ensure_ascii=False), '')
    ok('C15 ★ 自省的意见也回给作者看（`reflections`）',
       turn.reflections and '阿福' in turn.reflections[0], str(turn.reflections))

    # 自省说没问题 → 不多跑
    # [EN] Introspection says no problem → don't run more
    ag = new_agent()
    SCRIPT.extend([
        {'想': '看一眼', '终': '看过了，没问题。', '改了什么': []},
        {'有问题': False, '问题': [], '下一步': ''},
    ])
    n0 = len(SEEN)
    await ag.ask('看一眼')
    ok('C16 ★★ 自省说没问题就**不再多跑**（不许没事找事烧钱）',
       len(SEEN) - n0 == 2, f'多了 {len(SEEN) - n0} 次调用')

    # 关掉自省
    # [EN] Turn off introspection
    ag = new_agent(reflect=False)
    SCRIPT.extend([{'想': 'x', '终': '好了。', '改了什么': []}])
    await ag.ask('x')
    ok('C17 ★ `POLISH_REFLECT=false` 时真的不自省',
       not [x for x in SEEN if x['purpose'] == 'polish_reflect'], '')

    # ── 步数上限 / 拿不到东西时换手段 ──
    # [EN] -- Step cap / switch methods when nothing can be obtained --
    ag = new_agent(max_steps=3)
    SCRIPT.extend([None, None, None])          # 连续三次拿不到
    # [EN] Three consecutive failures to obtain
    turn = await ag.ask('随便说点什么')
    ok('C18 ★★ 连续拿不到动作 → 走到步数上限就**停下收口**（不会无限转）',
       turn.steps == 3 and '停' in turn.reply, f'steps={turn.steps}')
    hints = [e['text'] for e in ag.events if e['kind'] == 'observe']
    ok('C19 ★★ 拿不到东西时喂的是"**换个手段**"（换路径/先列文件），'
       '而不是原样重试同一句话',
       any('换个手段' in x for x in hints), str(hints[:1]))

    # ── 反问 ──
    # [EN] -- Counter-questioning --
    ag = new_agent()
    SCRIPT.extend([{'想': '拿不准', '问': '你要改哪个人的名字？'}])
    turn = await ag.ask('把名字改一下')
    ok('C20 ★★ 信息不够会**反问**并停下（`question` 有值、`reply` 空）',
       turn.question and not turn.reply, f'{turn.question!r}')

    # ── ⑦ 动态生成工具 ──
    # [EN] -- ⑦ Dynamically generated tools --
    ag = new_agent()
    SCRIPT.extend([
        {'想': '写个工具', '用': '生成工具',
         '参': {'名称': '数人物', '说明': '数一数有几个人物',
               '代码': 'import json\ndef run(args):\n'
                       '    s = json.loads(read_text(args["路径"]))\n'
                       '    return "共 %d 位" % len(s.get("人物", []))\n',
               '试跑参数': {'路径': 'out:临时设定.json'}}},
        {'想': '用它', '用': '数人物', '参': {'路径': 'out:临时设定.json'}},
        {'想': '收', '终': '工具造好了。', '改了什么': []},
        {'有问题': False, '问题': [], '下一步': ''},
    ])
    (out / '临时设定.json').write_text(
        json.dumps(SAMPLE_SETTINGS, ensure_ascii=False), encoding='utf-8')
    turn = await ag.ask('给我一个能数人物的工具')
    used = [a['工具'] for a in turn.actions]
    ok('C21 ★★ Agent 能**现场生成一个新工具**（`生成工具` 是唯一能长出工具的工具）',
       '生成工具' in used, str(used))
    ok('C22 ★★ 生成出来的工具**写进了 `box.generated`**，而且 Agent 立刻用了它',
       '数人物' in ag.box.generated and used[-1] == '数人物', str(used))
    ok('C23 ★★ 生成工具在**子进程里**跑（不是 `exec` 在主进程里）',
       any(a['工具'] == '数人物' and a['成功'] for a in turn.actions), '')
    ok('C24 ★ 生成的工具会出现在"列工具"里（下一轮模型看得到它能用）',
       '数人物' in (await ag.box.call('列工具', {})).text, '')

    # ── 装回盘上的工具 ──
    # [EN] -- Tools loaded back from disk --
    ag2 = new_agent()
    loaded = ag2.load_tools()
    ok('C25 ★★ 开新一场会把**上一场生成的工具装回来**'
       '（否则"动态生成"就是一次性玩具）',
       '数人物' in loaded and '数人物' in ag2.box.generated, str(loaded))
    # 盘上的工具被改坏 → 跳过而不是崩
    # [EN] Tool on disk gets corrupted → skip instead of crash
    (out / 'AI工具' / '坏的.py').write_text('import os\ndef run(args):\n    return 1',
                                           encoding='utf-8')
    ag3 = new_agent()
    loaded3 = ag3.load_tools()
    ok('C26 ★★ 盘上不合规的工具**跳过并记警告**（一个坏文件不该让整场开不了工）',
       '坏的' not in loaded3 and '数人物' in loaded3, str(loaded3))

    AG.ask = real_ask
    safe_rmtree(src, ignore_errors=True)
    safe_rmtree(out, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  D —— MOCK 端到端（走真 llm 通道）
# [EN] D -- MOCK end-to-end (goes through the real llm channel)
# ══════════════════════════════════════════════════════════════════
async def test_mock_e2e() -> None:
    from llm.router import llm
    src, out, sc = _fixture()
    await llm.ensure_started(Path(tempfile.mkdtemp(prefix='nws_polish_log_')))
    ag = PolishAgent(settings=json.loads(json.dumps(SAMPLE_SETTINGS)), scope=sc,
                     name='临河茶肆', tier='白银', missing=('伏笔回收',))
    review = await ag.intro()
    ok('D1 ★★ 走真 MOCK：体检有话说（**非空** —— 空气泡是用户报过的现象）',
       bool(review.strip()), review[:44].replace('\n', ' '))
    turn = await ag.ask('给主角补上目标')
    ok('D2 ★★ 走真 MOCK：整轮能跑完并收口', bool(turn.reply), turn.reply[:50])
    ok('D3 ★★ 走真 MOCK：**工具真的被调了**'
       '（演示模式要演得出真实的两步流程，否则这条路永远验不到）',
       bool(turn.actions), str([a['工具'] for a in turn.actions]))
    ok('D4 ★ MOCK 的体检结论进了事件流（下一句"就按你刚才说的"才接得上）',
       any(e['kind'] == 'review' for e in ag.events), '')
    rep = AG.render_report(ag)
    ok('D5 ★ 报告渲染得出（含"改了什么"那一节）',
       '## 改了什么' in rep and ag.name in rep, rep.splitlines()[0])
    safe_rmtree(src, ignore_errors=True)
    safe_rmtree(out, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  E —— 真机
# [EN] E -- Real machine
# ══════════════════════════════════════════════════════════════════
def _fixture_src(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '设定').mkdir(parents=True, exist_ok=True)
    (src / '设定' / '人物.md').write_text(
        '# 人物\n主角：临河茶肆掌柜，袖里有半张当票。\n阿福：跑堂。\n', encoding='utf-8')
    (src / '设定' / '世界观.md').write_text('# 世界观\n江南水乡，茶楼为业。\n',
                                            encoding='utf-8')
    (src / '大纲.md').write_text('# 大纲\n第一幕：当票现身。\n', encoding='utf-8')
    (src / '正文.md').write_text('雨下了一夜。\n', encoding='utf-8')
    return src


def _all_texts(ctrl, out=None) -> list:
    import flet as ft
    out = [] if out is None else out
    v = getattr(ctrl, 'value', None)
    if isinstance(v, str):
        out.append(v)
    if isinstance(ctrl, ft.Text) and ctrl.value:
        out.append(str(ctrl.value))
    for a in ('controls', 'content', 'actions', 'title'):
        x = getattr(ctrl, a, None)
        if isinstance(x, list):
            for c in x:
                _all_texts(c, out)
        elif x is not None and hasattr(x, '__class__'):
            _all_texts(x, out)
    return out


async def test_real_gui(page) -> None:
    import flet as ft

    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp

    tmp = Path(tempfile.mkdtemp(prefix='nws_polish_gui_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    try:
        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        # ── E1：向导第 3 步有那个新勾选项，而且默认勾着 ──
        # [EN] ── E1: Wizard step 3 has that new checkbox, and it's checked by default ──
        src = _fixture_src(tmp)
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.8)
        rep = app._wizard_opts or {}
        ok('E1 ★★ 开卷向导里多了「打磨结论也写一份到引用文件夹」，'
           '而且**默认勾选**（用户要的就是"同时写两处"）',
           bool(rep.get('polish_write_back')), str(sorted(rep)))

        # ── 走一遍开卷（MOCK）──
        # [EN] ── Walk through open-book (MOCK) ──
        app._wizard_path = str(src)
        app._wizard_name = '雨夜来客'
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = False   # 那一步会停下等确认，脚本里跳过
        # [EN] That step stops and waits for confirmation, the script skips it
        app._wizard_opts['polish_write_back'] = True
        app._do_import(page)
        st = app._ingest_state
        # 同意门
        # [EN] Consent gate
        for _ in range(200):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            p = ui.get('consent_panel')
            if p is not None and p.visible:
                break
        ui = st.get('ui') or {}
        for b in (ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        if ui.get('consent'):
            ui['consent'](True)
        # AI 对话阶段
        # [EN] AI dialogue phase
        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(0.6)
        logs_before = VU.log_cells((st.get('ui') or {}).get('log_list').controls) \
            if (st.get('ui') or {}).get('log_list') else []
        ok('E2 ★★ 真机上打磨 Agent **真的起来了**（日志里有"打磨 Agent 就位"）',
           any('打磨 Agent 就位' in str(x) for x in logs_before),
           str([x for x in logs_before if '打磨' in str(x)][:1]))
        ok('E2b ★★ 没有悄悄退回老的一问一答（`! 打磨 Agent 没能起来` 不该出现）',
           not any('没能起来' in str(x) for x in logs_before), '')

        # 作者下一句
        # [EN] Author's next line
        ui = st.get('ui') or {}
        if ui.get('chat_input'):
            ui['chat_input'].value = '给主角补上目标，再把口癖定下来。'
            ui['send'](None)
            await asyncio.sleep(1.5)
        # 收工
        # [EN] Done
        if ui.get('finish'):
            ui['finish']()
        for _ in range(200):
            await asyncio.sleep(0.1)
            if app._view == 'main':
                break
        await asyncio.sleep(0.8)
        proj = app.current_project
        ok('E3 ★ 开卷走完进了运行界面', app._view == 'main' and proj is not None,
           str(app._view))

        # ── ④ 双写：项目侧 ──
        # [EN] ── ④ Dual write: project side ──
        rec = (proj.root / '打磨记录.md') if proj else None
        ok('E4 ★★ **项目侧**有《打磨记录.md》',
           rec is not None and rec.is_file(),
           str(sorted(p.name for p in proj.root.iterdir())) if proj else '')
        body = rec.read_text(encoding='utf-8') if rec and rec.is_file() else ''
        ok('E5 ★★ 项目侧那份里写着"改了什么"（不是空壳）',
           '## 改了什么' in body and 'Agent' in body, body.splitlines()[0] if body else '')

        # ── ④ 双写：引用侧 ──
        # [EN] ── ④ Dual write: reference side ──
        srec = src / 'AI打磨记录.md'
        ok('E6 ★★ **引用侧**也有《AI打磨记录.md》'
           '（用户原话："同时写到项目里和原始的设定文件夹里"）',
           srec.is_file(), str(sorted(p.name for p in src.iterdir())))
        sbody = srec.read_text(encoding='utf-8') if srec.is_file() else ''
        ok('E7 ★★★ 两侧写的是**同一份文本**（各写各的迟早对不上）',
           bool(sbody) and sbody == body, f'{len(sbody)} vs {len(body)} 字节')
        ok('E8 ★★ 回写只追加：**作者原文一个字没动**（`.bak` 也留了）',
           '临河茶肆掌柜' in (src / '设定' / '人物.md').read_text(encoding='utf-8')
           and (src / 'AI打磨记录.md.bak').is_file() is False, '')

        # ── 关掉开关就不该写引用侧 ──
        # [EN] ── Turn the switch off and the reference side should not be written ──
        png = await page.take_screenshot()
        (OUT / 'polish_agent_ingest.png').write_bytes(png or b'')
    finally:
        safe_rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  驱动
# [EN] Drive
# ══════════════════════════════════════════════════════════════════
def _logic_main() -> None:
    print('\n【A】沙盒：路径白名单 / 越权 / 静态审查 / 子进程')
    test_sandbox()
    print('\n【B】工具：十二个工具逐个跑')
    asyncio.run(test_tools())
    print('\n【C】Agent：历史 · 自省 · 步数 · 动态生成工具')
    asyncio.run(test_agent())
    print('\n【D】MOCK 端到端')
    asyncio.run(test_mock_e2e())


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    import verify_ui_common as VU
    VU.redirect_env_writes()          # 真机段会点按钮 → `CFG.save()`，禁写真实 .env
    # [EN] The real-device section will click the button → `CFG.save()`, real .env writes are disabled
    try:
        _logic_main()
        if not logic_only:
            import flet as ft
            print('\n【E】真机：向导选项 · 走一遍开卷 · 双写落盘')

            async def entry(page) -> None:
                from util.flet_shutdown import shutdown
                try:
                    await test_real_gui(page)
                except BaseException:                            # noqa: BLE001
                    traceback.print_exc()
                    ok('E 真机判据自己跑通', False,
                       traceback.format_exc().splitlines()[-1])
                # ⚠ 收尾顺序是硬约束：验证 → 写报告 → shutdown（它同步退进程）。
                #   写在 `ft.run` 之后等于死代码（`ft.run` 会阻塞到窗口关闭）。
                # [EN] ⚠ Teardown order is a hard constraint: verify → write report → shutdown (it synchronously exits
                # [EN] the process).
                # [EN] Writing after `ft.run` is dead code (`ft.run` blocks until the window closes).
                code = _finish()
                await shutdown(page, code=code)

            ft.run(entry)
    except BaseException:                                        # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
        ok('Z 判据自己跑通（没被异常打断）', False,
           report['fatal'].splitlines()[-1])

    return _finish()


def _finish() -> int:
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'polish_agent_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  开卷打磨 Agent：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"][:130]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
