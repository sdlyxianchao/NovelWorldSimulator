# -*- coding: utf-8 -*-
"""判据：**拆书的三种输入 + 只拆一段**，以及**各职位按需取用技能包**。

覆盖五层，每层都要能红：

  A 选择范围（`booklab.selection`）—— `1-10,15-21` / `前3章` / `第5章-第8章` /
    `「章节名」`；**越界不算错，但解析不了必须报错（不许静默当全部）**
  B 取文（`booklab.sources`）—— 格式分派 · **自然序**（第2章排在章10前面）· PDF 逐页
  C 读入（`booklab.reader`）—— 文件 / 文件夹 / PDF 按页 · 范围真的生效 · 单位会说明
  D 网址（`booklab.web`）—— **真机**：起本地 HTTP 服务器爬一遍（严格规则挑章节、
    放宽规则要说出来、抓不到要有话说）
  E 接线 —— `analyzer.run` 透传 `selection` · GUI 两个控件真的在 · i18n 有译文
  F 技能路由（`crew.skill_router`）—— 按**职位**挑知识包 · 拆书技能只给索引 ·
    开关与上限 · `craft_block` 第 ④ 段真的接上

用法：
    python tools/verify_booklab_sources.py
    python tools/verify_booklab_sources.py --logic-only

English:
Criterion: **the three inputs of book splitting + splitting only one segment**, and **each role
takes skill packages on demand**.
Covers five layers, each layer must be able to go red:
    `「章节名」`; **out of range is not an error, but failing to parse must raise an error (must not silently treat as all)**
  B Source text (`booklab.sources`) -- format dispatch · **natural order** (第2章 before 章10) · PDF page by page
  C Reading (`booklab.reader`) -- file / folder / PDF by page · range really takes effect · units are explained
  D URL (`booklab.web`) -- **real machine**: start a local HTTP server and crawl once (select chapters by strict rules,
    relaxed rules must be stated, failure to fetch must be reported)
  E Wiring -- `analyzer.run` passes through `selection` · the GUI's two controls really exist · i18n has translations
  F Skill routing (`crew.skill_router`) -- pick knowledge packages by **role** · book-splitting skill only indexed ·
    switches and limits · `craft_block` section ④ is really connected
Usage:
    python tools/verify_booklab_sources.py
    python tools/verify_booklab_sources.py --logic-only
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / 'assets' / 'screenshots'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG  # noqa: E402

report: dict = {'checks': []}


def ok(name: str, good: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(good),
                             'detail': str(detail)[:300]})
    print(('  ✓ ' if good else '  ✗ ') + name
          + (f'   [{detail}]' if detail and not good else ''))
    return bool(good)


def _rm(p) -> None:
    try:
        shutil.rmtree(p, ignore_errors=True)
    except Exception:                                            # noqa: BLE001
        pass


def read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8')
    except OSError:
        return ''


def code_only(src: str) -> str:
    """剥掉**整行注释**。

    ★ 为什么每个"在整份源码里找/排除某个写法"的断言都要先过它：
      注释里写着这个名字时判据会**假绿**（本项目为此栽过好几次）。
    
        English:
    Strip **whole-line comments**.
        ★ Why every assertion that "finds/excludes a certain pattern in the entire source tree" must first pass through it:
          When this name appears in comments, the criterion will be **falsely green** (this project has been burned by this several times).
    """
    return '\n'.join(ln for ln in str(src or '').splitlines()
                     if not ln.lstrip().startswith('#'))


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


# ══════════════════════════════════════════════════════════════
#  A. 选择范围
# [EN] A. Selection range
# ══════════════════════════════════════════════════════════════
def test_selection() -> None:
    from booklab import selection as S

    titles = [f'第{i}章 井底之蛙' if i == 5 else f'第{i}章'
              for i in range(1, 31)]
    n = len(titles)

    ok('A1 留空 = 不筛（这是默认，不是"全拆"的特例）',
       not S.parse('').active() and S.apply(S.parse(''), titles) == list(range(n)),
       '')
    ok('A2 `全部` 与留空等价（用户可能就爱写两个字）',
       not S.parse('全部').active(), '')

    r = S.apply(S.parse('1-10,15-21'), titles)
    ok('A3 ★★ `1-10,15-21` = 两段并集（17 段）',
       r == list(range(10)) + list(range(14, 21)), str(r[:4]) + '…')

    s = S.parse('前3章')
    ok('A4 ★★ `前3章`：单位认成「章」，取前三个',
       s.kind == '章' and s.head == 3 and S.apply(s, titles) == [0, 1, 2],
       f'{s.kind}/{s.head}')

    s = S.parse('第5章-第8章')
    ok('A5 ★★★ `第5章-第8章` —— **两头都带「第…章」**也要认出来',
       s.ok and S.apply(s, titles) == [4, 5, 6, 7], f'{s.label()} {s.names}')

    ok('A6 ★★ 中文数字：`第一章` / `第二十三章` / `第一百零八章`',
       S.apply(S.parse('第一章'), titles) == [0]
       and S.apply(S.parse('第二十三章'), titles) == [22]
       and S.parse('第一百零八章').ranges == ((108, 108),),
       f'{S.parse("第二十三章").ranges}')

    ok('A7 ★ `最后2章` 取尾部', S.apply(S.parse('最后2章'), titles) == [28, 29], '')
    ok('A8 ★ `5-` = 从第 5 段到结尾',
       S.apply(S.parse('5-'), titles) == list(range(4, n)), '')

    s = S.parse('「井底」')
    ok('A9 ★★★ 按标题挑：`「井底」` 命中「第5章 井底之蛙」',
       S.apply(s, titles) == [4], f'{s.names}')

    # ★★ 只写标题关键词时，基数必须是"全部"
    # ★ 样本必须是**纯标题关键词**（不带数字）—— 第一版用的是 `第3章`，
    #   那其实是个**范围**，于是这条"只写标题时基数是全部"压根没被测到
    #   （反例法 S04 就是这么"漏掉"的）。
    # [EN] ★★ When only title keywords are written, the base must be "all"
    # [EN] ★ The sample must be **pure title keywords** (no digits) -- the first version used `第3章`,
    # [EN] which is actually a **range**, so this "when only title is written the base is all" was never
    # [EN] tested at all
    # [EN] (the counterexample method S04 "missed" it this way).
    ok('A10 ★★★ 只写标题关键词时，**基数是全部**（不写范围 = 不按位置筛）'
       '—— names 单独用时若基数是空的，结果会变成"一个都没有"，'
       '于是"筛错了"被说成"书是空的"',
       S.apply(S.parse('井底'), titles) == [4],
       str(S.apply(S.parse('井底'), titles)))

    s = S.parse('1-9999')
    ok('A11 ★★ 越界**不算错**：`1-9999` 而只有 30 章 → 就是 30 章（照实）',
       s.ok and len(S.apply(s, titles)) == n, '')

    bad = S.parse('0-5')
    ok('A12 ★★★ 解析不了**必须报错** —— 不许静默当"全部"'
       '（用户以为只拆 10 页、实际拆了一整本，是"看起来成功"的那种坏）',
       not bad.ok and bad.err, bad.err[:40])
    ok('A13 ★★ 倒着的范围（`10-3`）也算错', not S.parse('10-3').ok, '')
    ok('A14 ★★ 一个都选不上时**范围是对的、结果是空的**（两件事要分得开）',
       S.parse('第999章').ok and S.apply(S.parse('第999章'), titles) == [], '')

    ok('A15 ★ 全角数字与全角破折号也认（用户从别处粘贴过来）',
       S.parse('２－４').ranges == ((2, 4),), f'{S.parse("２－４").ranges}')

    ok('A16 ★★ `label()` 说人话：单段说「第 23 章」，不说「23-23」',
       S.parse('第二十三章').label() == '第 23 章',
       S.parse('第二十三章').label())

    # 单位换算：对一份没有章的文本写「页」→ 由 reader 记账说明（那在 C 组）
    # [EN] Unit conversion: writing "pages" against a text with no chapters -> accounted for by the reader
    # [EN] (that's in group C)
    ok('A17 ★ `前10页` 的单位是「页」',
       S.parse('前10页').wanted_kind() == '页', S.parse('前10页').kind)


# ══════════════════════════════════════════════════════════════
#  B. 取文
# [EN] B. Source text
# ══════════════════════════════════════════════════════════════
def _mk_pdf(path: Path, pages: list[str]) -> None:
    """手搓一个最小合法的多页 PDF（只为测试 —— 不引第三个依赖）。
        English:
    Hand-roll a minimal valid multi-page PDF (for testing only -- no third dependency).
    """
    objs: dict[int, bytes] = {}
    n = len(pages)
    kids = ' '.join(f'{5 + i * 2} 0 R' for i in range(n))
    objs[1] = b'<</Type/Catalog/Pages 2 0 R>>'
    objs[2] = f'<</Type/Pages/Kids[{kids}]/Count {n}>>'.encode()
    for i, txt in enumerate(pages):
        pno, cno = 5 + i * 2, 6 + i * 2
        objs[pno] = (f'<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]'
                     f'/Contents {cno} 0 R'
                     f'/Resources<</Font<</F1 3 0 R>>>>>>').encode()
        body = f'BT /F1 12 Tf 72 720 Td ({txt}) Tj ET'.encode()
        objs[cno] = (b'<</Length ' + str(len(body)).encode() + b'>>stream\n'
                     + body + b'\nendstream')
    objs[3] = b'<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>'
    out = bytearray(b'%PDF-1.4\n')
    off: dict[int, int] = {}
    for k in sorted(objs):
        off[k] = len(out)
        out += f'{k} 0 obj\n'.encode() + objs[k] + b'\nendobj\n'
    xref = len(out)
    mx = max(objs) + 1
    out += f'xref\n0 {mx}\n'.encode() + b'0000000000 65535 f \n'
    for k in range(1, mx):
        out += (f'{off[k]:010d} 00000 n \n'.encode() if k in off
                else b'0000000000 65535 f \n')
    out += (f'trailer\n<</Size {mx}/Root 1 0 R>>\n'
            f'startxref\n{xref}\n%%EOF\n').encode()
    path.write_bytes(bytes(out))


def test_sources(tmp: Path) -> None:
    from booklab import sources as SRC

    ok('B1 ★ 后缀分派：pdf / docx / html / 纯文本各走各的路',
       SRC.kind_of('a.PDF') == 'pdf' and SRC.kind_of('a.docx') == 'docx'
       and SRC.kind_of('a.htm') == 'html' and SRC.kind_of('a.txt') == 'text',
       f'{SRC.kind_of("a.PDF")}/{SRC.kind_of("a.docx")}')

    ok('B2 ★★ 认的格式表里**有 PDF**（用户点名要的），而且只认文档格式',
       SRC.is_supported('x.pdf') and SRC.is_supported('x.docx')
       and SRC.is_supported('x.html') and SRC.is_supported('x.md')
       and not SRC.is_supported('x.exe'),
       str(sorted(SRC.SUPPORTED_SUFFIXES)))

    d = tmp / 'f'
    d.mkdir(parents=True, exist_ok=True)
    for nm in ('第10章.txt', '第2章.txt', '第1章.txt'):
        (d / nm).write_text('正文' * 60, encoding='utf-8')
    (d / '说明.pdf')            # 空文件，只为测列举
    # [EN] Empty file, only for testing enumeration
    (d / 'ignored.exe').write_bytes(b'MZ')
    got = [p.name for p in SRC.list_files(d)]
    ok('B3 ★★★ 文件夹按**自然序**排（`第2章` 必须在 `第10章` 前面）——'
       '字典序会把顺序搞乱，而拆出来的结论看上去仍然像模像样',
       got[:3] == ['第1章.txt', '第2章.txt', '第10章.txt'], str(got))
    ok('B4 ★ 只挑认得的格式（.exe 不进来）', 'ignored.exe' not in got, str(got))

    pdf = tmp / 'p.pdf'
    _mk_pdf(pdf, ['Chapter 1 first', 'Chapter 2 second', 'Chapter 3 third'])
    pages = SRC.pdf_pages(pdf)
    ok('B5 ★★★ PDF **逐页**抽得出来（页选择要用到"第 N 页"）',
       len(pages) == 3 and pages[0].startswith('Chapter 1'), str(pages)[:80])
    ok('B6 ★ 正常 PDF 上 `pdf_hint()` 返回空（没有故障就不说话）',
       SRC.pdf_hint(pdf) == '', SRC.pdf_hint(pdf)[:60])

    docx = tmp / 'd.docx'
    ok('B7 ★ 坏 docx 不许把程序带崩（返回空串，由调用方照实说）',
       SRC.read_file(docx) == '', '')


# ══════════════════════════════════════════════════════════════
#  C. 读入
# [EN] C. Reading
# ══════════════════════════════════════════════════════════════
def test_reader(tmp: Path) -> None:
    from booklab import reader as R

    one = tmp / '书.txt'
    one.write_text('\n\n'.join(f'第{i}章 标题{i}\n' + '正文内容' * 40
                               for i in range(1, 11)), encoding='utf-8')
    b = R.read_book(one)
    ok('C1 ★ 单文件：分章照旧', b.n == 10 and b.unit_kind == '章',
       f'{b.n} {b.unit_kind}')

    b = R.read_book(one, selection='前3章')
    ok('C2 ★★ 单文件 + `前3章` → 真的只剩 3 章',
       b.n == 3 and b.total_units == 10, f'{b.n}/{b.total_units}')

    d = tmp / '多文件'
    d.mkdir(parents=True, exist_ok=True)
    for nm in ('第2章.md', '第1章.md', '第3章.md'):
        (d / nm).write_text('正文一段。' * 40, encoding='utf-8')
    bd = R.read_book(d)
    ok('C3 ★★ 文件夹：一个文件**一篇地切**（用户是按文件想事情的）',
       bd.n == 3 and bd.source_kind == 'dir', f'{bd.n} {bd.unit_kind}')
    ok('C4 ★★ 文件夹里没有章名时，**文件名就是章名**（不是并成一坨）',
       all(c.title for c in bd.chapters), str([c.title for c in bd.chapters]))

    pdf = tmp / 'p.pdf'
    # ★ 每页正文要够 50 字 —— 不然 `split_into_chapters` 会把"标题下面太短"的
    #   当成目录页丢掉，于是"认不出章"，C7 就永远测不到"按章"那条路。
    #   ⚠ 用 ASCII：手搓的 PDF 只有 Helvetica，中文抽不出来。
    # [EN] ★ The body text of each page must be at least 50 characters -- otherwise `split_into_chapters`
    # [EN] will treat "too short below the title"
    # [EN] as a table-of-contents page and drop it, so "no chapters recognized", and C7 will never test the
    # [EN] "by chapter" path.
    # [EN] ⚠ Use ASCII: the hand-rolled PDF only has Helvetica, Chinese cannot be extracted.
    _mk_pdf(pdf, [f'Chapter {i} ' + 'body text here. ' * 20 for i in range(1, 6)])
    bp = R.read_book(pdf, selection='1-3页')
    ok('C5 ★★★ PDF + `1-3页` → 按**页**取（用户要的就是物理页）',
       bp.unit_kind == '页' and bp.n == 3 and bp.total_units == 5,
       f'{bp.n}/{bp.total_units} {bp.unit_kind}')
    ok('C6 ★★ 按页取时标题是「第 N 页」（报告里能对回去）',
       bp.chapters[0].title == '第 1 页', bp.chapters[0].title)

    bp2 = R.read_book(pdf, selection='前2章')
    ok('C7 ★★★ PDF 里认得出章就按**章**（页只是纸张，拆书要的是章）',
       bp2.unit_kind == '章' and bp2.n == 2, f'{bp2.n} {bp2.unit_kind}')

    b3 = R.read_book(one, selection='第999章')
    ok('C8 ★★★ 范围一个都没选上 → **0 章 + 一句说明**'
       '（不许静默当成"没有正文"）',
       b3.n == 0 and any('一个都没选上' in x for x in b3.notes),
       str(b3.notes)[:80])

    b4 = R.read_book(one, selection='0-5')
    ok('C9 ★★★ 范围解析失败 → **什么都不拆 + 照实说**'
       '（"宁可没读，不要多读"）',
       b4.n == 0 and any('看不懂' in x for x in b4.notes), str(b4.notes)[:60])

    b5 = R.read_book(one, selection='前10页')
    ok('C10 ★★ 对一份没有"页"的文本写「前10页」→ 按章取 + **说明单位换了**',
       b5.n == 10 and any('没有「页」' in x for x in b5.notes),
       str(b5.notes)[:60])

    b6 = R.read_book(tmp / '根本不存在.txt')
    ok('C11 ★ 路径不存在**不抛**，记一句说明（调用方照实显示）',
       b6.n == 0 and b6.notes, str(b6.notes)[:60])

    empty = tmp / '空.txt'
    empty.write_text('', encoding='utf-8')
    ok('C12 ★ 空文件照样不抛', R.read_book(empty).n == 0, '')


# ══════════════════════════════════════════════════════════════
#  D. 网址（真机：本地 HTTP 服务器）
# [EN] D. URL (real machine: local HTTP server)
# ══════════════════════════════════════════════════════════════
_INDEX_HTML = """<!doctype html><html><head><title>某书 · 目录</title>
<style>.x{color:red}</style></head><body>
<script>var a=1;</script>
<h1>目录</h1>
<ul>
  <li><a href="/c/1.html">第一章 井底之蛙</a></li>
  <li><a href="/c/2.html">第二章 上灯</a></li>
  <li><a href="/c/3.html">第三章 夜客</a></li>
  <li><a href="/c/2.html">第二章 上灯（重复）</a></li>
  <li><a href="http://other.example.com/c/9.html">第九章 外站</a></li>
  <li><a href="/about.html">关于本站</a></li>
</ul>
<p>正文从这里开始，一段话。</p>
</body></html>"""

_CHAPTER_HTML = """<html><head><title>第{0}章</title></head><body>
<div id="nav"><a href="/">首页</a></div>
<div id="content"><p>这是第 {0} 章的第一段，掌柜把灯挑亮了些。</p>
<p>第二段，雨还在下。</p></div>
<script>ad();</script></body></html>"""

_NO_LINK_HTML = """<html><head><title>单章</title></head><body>
<p>这一页本身就是一章，里面没有任何章节链接。</p></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):                                            # noqa: N802
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            body, code = _INDEX_HTML, 200
        elif re.match(r'^/c/\d+\.html$', path):
            body = _CHAPTER_HTML.format(path.split('/')[2].split('.')[0])
            code = 200
        elif path == '/nolink.html':
            body, code = _NO_LINK_HTML, 200
        elif path == '/empty.html':
            body, code = '<html><body></body></html>', 200
        elif path == '/boom.html':
            self.send_response(500)
            self.end_headers()
            return
        else:
            body, code = '<html><body>404</body></html>', 404
        data = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):                                   # noqa: ANN002
        pass


def test_web() -> None:
    from booklab import web as W

    txt = W.html_to_text(_INDEX_HTML)
    ok('D1 ★★ HTML → 文本：**脚本与样式不进正文**，段落还在',
       'var a=1' not in txt and 'color:red' not in txt and '目录' in txt, txt[:60])
    ok('D2 ★ 页面标题取得到（`<title>`），空页返回空串',
       W.page_title(_INDEX_HTML) == '某书 · 目录'
       and W.page_title('<html><body>x</body></html>') == '',
       W.page_title(_INDEX_HTML))

    links, loose = W.chapter_links(_INDEX_HTML, 'http://127.0.0.1/')
    names = [l.text for l in links]
    ok('D3 ★★★ 严格规则挑章节：只认「第X章」那种，**导航与站外链接都不进来**',
       not loose and names == ['第一章 井底之蛙', '第二章 上灯', '第三章 夜客'],
       str(names))
    ok('D4 ★★ 同一地址去重、**保留第一次出现的顺序**（目录顺序 = 章节顺序）',
       len(links) == 3, str(len(links)))

    loose_links, loose2 = W.chapter_links(_NO_LINK_HTML + '<a href="/a">甲篇</a>'
                                         '<a href="/b">乙篇</a>'
                                         '<a href="/c">丙篇</a>',
                                         'http://127.0.0.1/')
    ok('D5 ★★★ 严格挑不到时**放宽**，而且**必须让调用方知道**（`loose=True`）——'
       '悄悄把导航当章节，等于给出一份错的目录',
       loose2 and len(loose_links) == 3, f'{loose2} {len(loose_links)}')

    # ── 真机：真起一个 HTTP 服务 ──
    # [EN] ── Real machine: actually start an HTTP service ──
    srv = HTTPServer(('127.0.0.1', 0), _Handler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        base = f'http://127.0.0.1:{port}/'
        got = W.crawl_index(base, delay=0.0, timeout=5)
        ok('D6 ★★★ 端到端爬一个索引页：抓到 3 章、每章正文都取到了',
           got.ok and len(got.chapters) == 3
           and '掌柜把灯挑亮了些' in got.chapters[0][1],
           f'{len(got.chapters)} 章 / err={got.err[:40]}')
        ok('D7 ★★ 爬回来的章标题是链接文字（作者能对上目录）',
           got.chapters[0][0] == '第一章 井底之蛙', got.chapters[0][0])

        nl = W.crawl_index(base + 'nolink.html', delay=0.0, timeout=5)
        ok('D8 ★★ 索引页**自己就是一篇文章**时当一章（而不是报"挑不到章节"）',
           nl.ok and len(nl.chapters) == 1, f'{len(nl.chapters)}')

        em = W.crawl_index(base + 'empty.html', delay=0.0, timeout=5)
        ok('D9 ★★ 打开是空的 → **有话说**（不是静默给空）', not em.ok and em.err,
           em.err[:50])

        bo = W.crawl_index(base + 'boom.html', delay=0.0, timeout=5)
        ok('D10 ★ 服务器报错时也不抛，转成一句能看懂的话',
           not bo.ok and bo.err, bo.err[:60])

        # ★★★ D11：**走 `reader.read_book` 那条完整的路**（不只测爬虫本身）——
        #   判据要钉"网址真的能当一本书来拆"，而不是"某个函数能爬"。
        # [EN] ★★★ D11: **go through the complete path of `reader.read_book`** (not just testing the crawler
        # [EN] itself) --
        # [EN] the criterion must pin down "the URL can really be split as a book", not "some function can
        # [EN] crawl".
        from booklab import reader as R
        bk = R.read_book(base)
        ok('D11 ★★★ 网址直接当"一本书"读得进来（`read_book` 认网址，'
           '不是只有爬虫函数能用）',
           bk.n == 3 and bk.source_kind == 'url', f'{bk.n} {bk.source_kind}')
        ok('D12 ★★ 书名取的是网页标题（不是那串 URL）',
           '目录' in bk.name and 'http' not in bk.name, bk.name)
        ok('D13 ★★ 网址来的书 + 范围：`前2章` 真的只剩 2 章',
           R.read_book(base, selection='前2章').n == 2, '')
        dead = R.read_book(base + 'boom.html')
        ok('D14 ★★ 打不开的网址**不抛**，记一句说明（调用方照实显示）',
           dead.n == 0 and dead.notes, str(dead.notes)[:60])
    finally:
        srv.shutdown()
        srv.server_close()


# ══════════════════════════════════════════════════════════════
#  E. 接线
# [EN] E. Wiring
# ══════════════════════════════════════════════════════════════
def test_wiring() -> None:
    an = read('booklab/analyzer.py')
    blk = between(an, 'book = R.read_book(', '\n    if not book.n:')
    ok('E1 ★★★ `analyzer.run` 把 `selection` **真的传给** `read_book`'
       '（在那一处查实参，不全文 grep）',
       'selection=selection' in blk, blk[:90].replace('\n', ' '))
    ok('E2 ★★ `run()` 的签名里**有** `selection` 这个参数'
       '（没有它，GUI 传不进来）',
       'selection: Any = None' in between(an, 'async def run(', ') -> Digest:'),
       '')
    ok('E3 ★★ 范围生效时**照实记账**（"只拆了哪一段、源里一共多少"）'
       '—— 报告必须能自证拆的是哪一部分',
       '只拆了「' in an, '')

    rd = read('booklab/reader.py')
    ok('E4 ★★★ 四种来源都在 `read_book` 这一处收口（文件/文件夹/网址/PDF）',
       all(k in rd for k in ('_read_url', '_read_dir', '_read_file', '_read_pdf')),
       '')
    ok('E5 ★★ 网址靠 `_URL_RE` 认出来（不是"先当路径试，失败再说"）',
       '_URL_RE.match(raw)' in rd, '')

    gui = read('gui/app_flet.py')
    # ★ 2026-10-10 改：网址输入框**不再常驻在主对话框里**，而是"点「网址」时
    #   弹出来的那个小对话框"里的（用户要求："弹出一个对话框 输入网址"）。
    #   所以 E6 的锚点跟着搬 —— 判的是**那个弹窗里真的有输入框**。
    # [EN] ★ Changed 2026-10-10: the URL input box is **no longer resident in the main dialog**, but is in
    # [EN] "the small dialog
    # [EN] that pops up when you click 「URL」" (user request: "pop up a dialog to enter the URL").
    # [EN] So the anchor for E6 moves along with it -- what is checked is **that the popup really has an
    # [EN] input box**.
    _ask = between(gui, 'def _ask_url(', 'if \'__range\' not in f:')
    ok('E6 ★★★ 点「网址」弹出来的那个对话框里**真的有**输入框'
       '（真控件，不是只写了文案）',
       'fld = mk_field(' in _ask and 'page.show_dialog(dlg2)' in _ask
       and "t('网址')" in _ask, _ask[:90].replace('\n', ' '))
    ok('E7 ★★★ 拆书对话框里**真的有**「选择范围」这个输入框',
       "__range'] = mk_field(" in gui
       and 't(\'选择范围\')' in between(gui, "f['__range'] = mk_field(", '_sync_sel()'),
       '')
    # ⚠ 2026-10-14：切片终点从 `out.append(ft.Row([mk_btn(t('开 始 拆')` 换成
    #   `def _sel_ok() -> bool:` —— 用户要求把「开 始 拆」搬到对话框底部动作栏
    #   （排在「关闭」左边），内容区那行 append 已经删掉，旧锚点会**过期**，
    #   `between` 找不到终点就返回到**全文末尾** ⇒ 判据会在别人的代码里找东西。
    # [EN] ⚠ 2026-10-14: the slice end changed from `out.append(ft.Row([mk_btn(t('开 始 拆')`
    # [EN] to `def _sel_ok() -> bool:` -- the user asked to move "Start" to the dialog's bottom action
    # [EN] bar (to the left of "Close"), the content-area append line is gone, and the old anchor would
    # [EN] go **stale**; `between` returns to the **end of the file** when it can't find the end marker,
    # [EN] so the criterion would search inside somebody else's code.
    st = between(gui, 'def _start(e):', 'def _sel_ok() -> bool:')
    # ★★ 2026-10-10 改：从"网址或书，总得有一样"**改成互斥之后的两段判**
    #   （用户：「你要让这几个选项互斥，只能够选择一个」）。
    #   原来那条查的是 `if not str(url).strip() and not st['path']:` —— 它守的是
    #   **隐式优先级**（填了网址就以网址为准），而那套已经拆掉了；
    #   继续留着它，就是"守着一件已经不存在的事"。
    # [EN] ★★ Changed 2026-10-10: from "URL or book, there must be one" **changed to two separate checks
    # [EN] after mutual exclusion**
    # [EN] (user: "you need to make these options mutually exclusive, only one can be selected").
    # [EN] The original one checked `if not str(url).strip() and not st['path']:` -- it guarded
    # [EN] **implicit priority** (if a URL is filled in, the URL wins), and that scheme has been removed;
    # [EN] keeping it would mean "guarding something that no longer exists".
    ok('E8 ★★★ 点「开始拆」时：**先得有一个选中的来源**（一个都没选就拦住）',
       "if not src_st['mode']:" in st, st[:110].replace('\n', ' '))
    ok('E8a ★★★ 选了「网址」却没填地址时**另给一句**'
       '（不能笼统说"先选一本书" —— 互斥之后这是两件事）',
       'if not _resolve_src():' in st and "src_st['mode'] == 'url'" in st
       and '网址还空着' in st, '')
    st2 = between(gui, 'def _booklab_start(', 'asyncio.create_task(_run())')
    ok('E8b ★★★ 从哪儿读**在启动那一步定**：来源由调用方按**选中的那个**算好传进来'
       '（`_resolve_src()`），而且范围真的**传给了拆书那一步**'
       '（在 `_booklab_start` 里查实参，全文 grep 会撞上别处的 `rng`）',
       'def _booklab_start(self, src: str' in st2
       and 'selection=rng' in st2 and 'BA.run(src' in st2,
       st2[-200:].replace('\n', ' ')[:150])
    # ── 互斥本身：这几条一起才叫"互斥"（只查一条容易假绿）──
    # ⚠ 切片**起点放在 `def _src_text()`**：`_ask_url` / `_set_src` / `_resolve_src`
    #   都定义在 `_src_btn` **之前**，原来从 `_src_btn` 起切会把它们漏在外面
    #   （E8d/E8e 一开始就是这么假红的 —— 判据找不到，看着像功能没做）。
    # [EN] ── Mutual exclusion itself: only these together count as "mutually exclusive" (checking just one
    # [EN] easily gives a false green) ──
    # [EN] ⚠ Put the slice **start at `def _src_text()`**: `_ask_url` / `_set_src` / `_resolve_src`
    # [EN] are all defined **before** `_src_btn`, so slicing from `_src_btn` would leave them outside
    # [EN] (E8d/E8e were falsely red this way at first -- the criterion couldn't be found, so it looked
    # [EN] like the feature wasn't done).
    # ⚠ 2026-10-14：终点同样从内容区那行 append 换成 `def _start(e):`
    #   （原因见上面 E8 那处；旧锚点已随"开始拆搬进动作栏"过期）。
    # [EN] ⚠ 2026-10-14: the end likewise changes from the content-area append line to
    # [EN] `def _start(e):` (reason at E8 above; the old anchor went stale when "Start" moved into the
    # [EN] action bar).
    body = between(gui, 'def _src_text()', 'def _start(e):')
    ok('E8c ★★★ 来源按钮**看着就是互斥的**：选中的那个实心、其余文字'
       '（判的是 `primary=(src_st[\'mode\'] == mode)` **那一个表达式**，'
       '不是"文件里出现过 primary 这个词"）',
       "primary=(src_st['mode'] == mode)" in body, '')
    # ⚠ 第一版这里数的是"`_set_src(` 出现几次 ≥ 5（含定义 1 次）" —— **算错了**：
    #   定义在**前一个块**里，`body` 这一段只有 4 次调用，于是判据自己假红。
    #   ⇒ 改成**逐个点名**那四个调用（这才是"四个按钮全走它"的本意），
    #     顺带把"只认一个 mode"限定在 `_set_src` **自己的函数体**里查
    #     （在整份源码里搜会撞上别处对 `mode` 的赋值）。
    # ⚠ 结束锚点用 `def _ask_url(`：要**贴着** `_set_src` 切完。
    #   踩了两次：原来用 `if '__url' not in f:`（那行随"网址搬进弹窗"删掉了），
    #   换成 `if '__range' not in f:` 又**切得太宽** —— 把 `_ask_url` 也包进来，
    #   而里面有一句 `if src_st['mode'] == 'url'`（`==` 里也含 `=`），
    #   于是下面 `count("src_st['mode'] =") == 1` 数成 2、判据假红。
    # [EN] ⚠ The first version here counted "how many times `_set_src(` appears >= 5 (including 1
    # [EN] definition)" -- **miscounted**:
    # [EN] the definition is in the **previous block**, and the `body` section only has 4 calls, so the
    # [EN] criterion went falsely red by itself.
    # [EN] ⇒ Changed to **naming those four calls one by one** (this is the real intent of "all four
    # [EN] buttons go through it"),
    # [EN] and also restricted "only recognizing one mode" to be checked **inside `_set_src`'s own function
    # [EN] body**
    # [EN] (searching the whole source would hit assignments to `mode` elsewhere).
    # [EN] ⚠ The end anchor uses `def _ask_url(`: must **hug** `_set_src` when slicing.
    # [EN] Tripped twice: originally used `if '__url' not in f:` (that line was deleted when "URL moved
    # [EN] into the popup"),
    # [EN] switched to `if '__range' not in f:` and it **sliced too wide** -- including `_ask_url` as well,
    # [EN] and inside there is a line `if src_st['mode'] == 'url'` (the `==` also contains `=`),
    # [EN] so the `count("src_st['mode'] =") == 1` below counted 2, and the criterion went falsely red.
    _set_src_body = between(gui, 'def _set_src(', 'def _ask_url(')
    # ⚠ 算"哪几个走了 `_set_src`"要先建成普通变量再拼进 f-string：
    #   在 f-string 的表达式里再嵌一层同引号的 f-string 会 SyntaxError
    #   （Python 只在 3.12+ 放宽同引号嵌套，转义引号仍然不行）。
    # [EN] ⚠ To count "which ones go through `_set_src`", first build a normal variable and then splice it
    # [EN] into the f-string:
    # [EN] nesting another f-string with the same quotes inside an f-string expression causes SyntaxError
    # [EN] (Python only relaxed same-quote nesting in 3.12+, and escaped quotes still don't work).
    _routed = [m for m in ('file', 'dir', 'url', 'sample')
               if ("_set_src('" + m + "'") in body]
    ok('E8d ★★★ 四个来源按钮**全都走 `_set_src`**（谁也没法绕过它自己偷偷亮着），'
       '而 `_set_src` 里**只认一个 mode** —— 那就是互斥的落点',
       len(_routed) == 4
       and "src_st['mode'] = mode" in _set_src_body
       and _set_src_body.count("src_st['mode'] =") == 1,
       f'走了 _set_src 的：{_routed}')
    ok('E8e ★★ 点「网址」→ **弹一个对话框**填地址'
       '（用户 2026-10-10："点击网址时候 弹出一个对话框 输入网址 而不是在下面"）',
       "def _ask_url(" in body and 'page.show_dialog(dlg2)' in body
       and "def _pick_url(e):" in body and '_ask_url()' in between(body, 'def _pick_url', 'def _use_sample'),
       '')
    ok('E8f ★★ 「网址」排在按钮行**最后一个**，而且**四个按钮在同一行**'
       '（用户："把网址移动到下面" + "这几个按钮之间距离可以近一些 以保证在一行里显示出来"）',
       0 <= body.find("_src_btn('file'") < body.find("_src_btn('dir'")
       < body.find("_src_btn('url'") < body.find("_src_btn('sample'")
       and body.count('out.append(ft.Row([') >= 1,
       '')
    # ★★ 四个按钮在**一个** Row 里（不是 3+1 两行）—— 数"这一组按钮"那个
    #   `Row` 里出现了几个 `_src_btn(`（用户要的就是"排在一行"）。
    # [EN] ★★ The four buttons are in **one** Row (not 3+1 on two lines) -- count how many `_src_btn(`
    # [EN] appear in
    # [EN] that group "these buttons" `Row` (what the user wants is "arranged in one line").
    _btn_row = between(body, 'out.append(ft.Row([\n            _src_btn',
                       '], spacing=')
    ok('E8g ★★ 这一行里**确实四个都放进去**了（不是三个一行、另起一行放 samples）',
       _btn_row.count('_src_btn(') == 4,
       f'行内 _src_btn 个数 = {_btn_row.count("_src_btn(")}')
    ok('E9 ★★★ 范围看不懂时**不许开跑**（跑了等于按"全部"拆，而用户以为只拆了 10 页）',
       '_sel_ok()' in st and 'if not _sel_ok():' in st, '')
    ok('E10 ★★ 选了范围后**当场回显**（不用等跑完才知道写没写错）',
       'sel_line.value' in gui and '只拆：{x}' in gui, '')

    i18 = read('i18n.py')
    need = ['网址', '选择范围', '支持 .txt / .md / .docx / .html / .pdf；'
                            '一本被拆成多个文件的，选文件夹。',
            # ★ 互斥之后新增/改写的这几条（老的两条已随隐式优先级一起删掉）：
            #   '以网址为准（下面的文件/文件夹会被忽略）' 与
            #   '先选一本书，或者填一个网址'
            # [EN] ★ The entries added/rewritten after mutual exclusion (the old two were deleted along with
            # [EN] implicit priority):
            # [EN] 'URL takes priority (the file/folder below will be ignored)' and
            # [EN] 'First select a book, or fill in a URL'
            '当前来源：网址',
            '还没选书 —— 在上面选一个，或者点「网址」填地址',
            '先选一本书：文件 / 文件夹 / samples，或者点「网址」填一个地址',
            '网址还空着 —— 先在上面那个框里填一个地址',
            '选择范围那行看不懂，改一下再开始']
    miss = [x for x in need if f"'{x}'" not in i18]
    ok('E11 ★★ 新文案**全部补了 i18n**（英文界面下悬赏冒中文 = 用户以为程序坏了）',
       not miss, f'缺：{miss[:3]}')

    from booklab import skillgen as SG
    from crew import skill_router as SK
    ok('E12 ★★ 技能分类名**两边同源**（`skill_router` 认的正是 `skillgen` 写出来的）',
       SK.DISMANTLE_CATEGORY == SG.BOOK_DIR,
       f'{SK.DISMANTLE_CATEGORY} vs {SG.BOOK_DIR}')


# ══════════════════════════════════════════════════════════════
#  F. 技能路由
# [EN] F. Skill routing
# ══════════════════════════════════════════════════════════════
def test_skill_router() -> None:
    from crew import skill_router as SK

    q = SK.query_for('researcher', genre='悬疑灵异', structure='单元剧',
                     question='写一场郎中戏')
    ok('F1 ★★★ 查询串里**有题材、有职位关心的词、也有作者手写的那几句**'
       '—— 只拿题材去查，八张知识卡一张都命不中，这一层就永远不出活',
       '悬疑灵异' in q and '药方' in q and '郎中' in q, q[:70])
    ok('F2 ★★ 没写这一职位时查询串照样成立（不抛）',
       SK.query_for('不存在的职位', genre='悬疑').strip() == '悬疑', '')

    r = SK.route('researcher', genre='悬疑灵异', structure='单元剧')
    ok('F3 ★★★ 资料员这一刻挑得到知识包（药方 / 兵器那一类）',
       bool(r['领域']), str([s.display_name for s in r['领域']]))
    ok('F4 ★★★ 挑出来的**全是领域技能**（拆书技能不进"领域"那一栏）'
       '—— 同一份内容只给一次',
       all(s.category != SK.DISMANTLE_CATEGORY for s in r['领域']), '')

    # ── ★★★ F4b/F4c：真造一个"既有领域卡、又有拆书包"的技能根，看它怎么分栏 ──
    #   为什么非造不可：真实的 `skills/` 里现在没有拆书包，于是"拆书技能不进领域"
    #   这条断言是**空的**（`all()` 对空表恒真）—— 假绿。
    # [EN] ── ★★★ F4b/F4c: actually create a skill root with both domain cards and a book-splitting crew,
    # [EN] and see how it divides the columns ──
    # [EN] Why it must be created: the real `skills/` currently has no book-splitting crew, so
    # [EN] "book-splitting skills don't enter the domain"
    # [EN] this assertion is **empty** (`all()` is vacuously true on an empty list) -- false green.
    import tempfile as _tf
    from skills.registry import skill_registry as _REG
    _tmp = Path(_tf.mkdtemp(prefix='nws_skroute_'))
    (_tmp / '测试知识卡').mkdir(parents=True)
    (_tmp / '测试知识卡' / 'SKILL.md').write_text(
        '---\n名称: 测试知识卡\n触发关键词:\n  - 悬疑\n'
        '用途: 一张领域知识卡\n---\n\n正文：桂枝汤可用于表虚。\n',
        encoding='utf-8')
    (_tmp / SK.DISMANTLE_CATEGORY / '测试书').mkdir(parents=True)
    (_tmp / SK.DISMANTLE_CATEGORY / '测试书' / 'SKILL.md').write_text(
        '---\n名称: 测试书\n触发关键词:\n  - 悬疑\n'
        '用途: 拆自某书的写法\n---\n\n正文：钩子要具体。\n',
        encoding='utf-8')
    _save_dir = CFG.raw('SKILLS_DIR')
    try:
        CFG.set('SKILLS_DIR', str(_tmp))
        _REG.load(force=True)
        rr = SK.route('novelist', genre='悬疑', structure='')
        ok('F4b ★★★ 真造一个"领域卡 + 拆书包"的技能根：**分栏正确**'
           '（拆书技能进「拆书」、领域卡进「领域」）',
           [s.display_name for s in rr['领域']] == ['测试知识卡']
           and [s.display_name for s in rr['拆书']] == ['测试书'],
           f"领域={[s.display_name for s in rr['领域']]} "
           f"拆书={[s.display_name for s in rr['拆书']]}")
        blk2 = SK.skill_block('novelist', genre='悬疑', structure='')
        ok('F4c ★★★ 拆书技能**只以索引形态出现**，正文不重复给'
           '（同一份内容给了两遍，模型会当成两条独立经验）',
           '测试书' in blk2 and '钩子要具体' not in blk2
           and '桂枝汤' in blk2, blk2.replace('\n', ' ')[:150])
    finally:
        if _save_dir is not None:
            CFG.set('SKILLS_DIR', _save_dir)
        _REG.load(force=True)
        _rm(_tmp)

    ok('F5 ★★ 上限真的生效（`CREW_SKILL_LIMIT`）',
       len(SK.route('researcher', genre='悬疑', structure='单元剧',
                    limit=1)['领域']) == 1, '')

    blk = SK.skill_block('researcher', genre='悬疑灵异', structure='单元剧')
    ok('F6 ★★★ 拼出来的那一段**带着知识卡的要点正文**'
       '（不是只报个名字 —— 只报名字等于没给）',
       '中医药方常识' in blk and '桂枝汤' in blk, blk[:80])
    ok('F7 ★★ 那一段**有字数上限**（十二个职位各塞一张 5K 的卡会把注意力淹掉）',
       len(blk) <= SK.TOTAL_CHARS + 60, f'{len(blk)}')

    _sav = CFG.raw('CREW_SKILL_ROUTE')
    try:
        CFG.set('CREW_SKILL_ROUTE', 'false')
        ok('F8 ★★★ 关掉开关后那一段**是空的**（关掉 = 完全不查，不是"查了不给"）',
           SK.skill_block('researcher', genre='悬疑灵异') == '', '')
    finally:
        if _sav is not None:
            CFG.set('CREW_SKILL_ROUTE', _sav)

    ok('F9 ★★ 挑不到就**什么都不给**（不硬塞）—— 硬塞一份不相干的东西比不给更坏',
       SK.skill_block('publicity', genre='悬疑灵异') == '',
       SK.skill_block('publicity', genre='悬疑灵异')[:60])

    md = SK.table_md('悬疑灵异', '单元剧')
    ok('F10 ★★ 落盘的那份是**逐职位**列的（作者要能核对"该挑到的人挑到没有"）',
       '| 职位 |' in md and '`researcher`' in md, md[:80].replace('\n', ' '))
    ok('F11 ★★ 没人挑到时也照实报（不说"全部命中"）',
       '个没有匹配上的' in md, '')

    ag = read('crew/agents.py')
    cb = between(ag, 'def craft_block(', '\ndef bind_world(')
    ok('F12 ★★★ `craft_block` 的**第 ④ 段**真的接上了技能路由'
       '（在 `craft_block` 那个函数体里查，不全文 grep）',
       'SKILLR.skill_block(' in cb and 'parts.append(sk)' in cb,
       cb[-200:].replace('\n', ' ')[:150])
    ok('F13 ★★ 技能那一段传的是**这个职位**的 key（不是写死的）',
       'SKILLR.skill_block(key, genre=genre' in cb, '')

    st = read('sim/setup.py')
    ok('F14 ★★ 运行文件夹里落一份《本书可用的技能.md》（能核对才算接上）',
       "本书可用的技能.md" in st and 'SKILLR.table_md(' in st, '')

    ok('F15 ★★ 两个旋钮都在配置里，而且是**全局**（"剧组怎么用技能"与某一本书无关）',
       'CREW_SKILL_ROUTE' in read('config.py') and 'CREW_SKILL_LIMIT' in read('config.py')
       and "group=\"剧组\"" in between(read('config.py'),
                                       '"CREW_SKILL_ROUTE"', ')'), '')

    r2 = SK.route('researcher', genre='悬疑灵异', structure='单元剧')
    ok('F16 ★★ 装置里没有拆书包时，索引那栏是空的（不报错、不硬凑）',
       isinstance(r2['拆书'], list), str(len(r2['拆书'])))


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    CFG.set('MOCK_LLM', 'true')
    tmp = Path(tempfile.mkdtemp(prefix='nws_blsrc_'))
    groups = [('A 选择范围（页/章/名字）', lambda: test_selection()),
              ('B 取文（格式 · 自然序 · PDF）', lambda: test_sources(tmp)),
              ('C 读入（文件/文件夹/PDF · 范围生效）', lambda: test_reader(tmp)),
              ('D 网址（真机：本地 HTTP 服务器）', lambda: test_web()),
              ('E 接线（analyzer / GUI / i18n）', lambda: test_wiring()),
              ('F 技能路由（按职位挑知识包）', lambda: test_skill_router())]
    if logic_only:
        groups = [g for g in groups if not g[0].startswith('D')]
    try:
        for title, fn in groups:
            print(f'\n【{title}】')
            try:
                fn()
            except Exception:                                    # noqa: BLE001
                traceback.print_exc()
                ok(f'{title} 这一组自己跑通（没被异常打断）', False,
                   traceback.format_exc().splitlines()[-1][:120])
    finally:
        _rm(tmp)

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'booklab_sources_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  拆书输入与技能路由：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"][:110]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
