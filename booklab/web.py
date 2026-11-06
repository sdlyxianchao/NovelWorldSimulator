# -*- coding: utf-8 -*-

"""**取网址**：把"一个书的索引页"爬成可以拆的章节列表。

用户 2026-10-10 的原话：「或者一个网址 里面是书籍的索引网页（软件可以去爬取）」。

三段做法
--------
```text
① 打开索引页       → HTML（带编码探测）
② 从里面挑章节链接  → 严格（链接文字像"第X章"）→ 挑不到再放宽（同站链接）
③ 逐章打开取正文    → 每章一段纯文本
```

三条纪律
--------
1. **只读**：只发 GET，不改对方任何东西；两次请求之间**留间隔**（默认 0.3 秒）——
   抓别人的站，快不是本事。
2. **拿不到就说拿不到**：抓失败的那一章**照实记账**（`notes`），
   不假装"这本书就只有这么多章"。少了几章却交出一份看着完整的报告，比失败更坏。
3. **不确定的不猜**：索引页上"哪些链接是章节"这件事，严格规则挑不到时
   **放宽并说出来**（`Crawl.loose`），而不是悄悄把导航菜单也当成章节。

零依赖：HTML 用标准库 `html.parser` 解析（不引 bs4 / lxml）——
本项目对外部依赖的态度是"能不加就不加"，而这里要的东西（取文字、取链接）
标准库刚好都有。

English:
**Fetch URL**: crawl "a book's index page" into a splittable chapter list.
The user's original words on 2026-10-10: "or a URL that contains a book's index page (the
software can crawl it)".
Three-step approach
--------
```text
① Open the index page       -> HTML (with encoding detection)
② Pick chapter links from it -> strict (link text looks like "Chapter X") -> if none picked,
relax (same-site links)
③ Open each chapter to get the body    -> one plain text segment per chapter
```
Three disciplines
--------
1. **Read-only**: only send GET, do not modify anything on the other side; **leave an interval** between two requests (default 0.3 seconds) --
   scraping someone else's site, speed is not a skill.
2. **If you can't get it, say you can't get it**: chapters that fail to scrape **must be recorded truthfully** (`notes`),
   do not pretend "this book only has this many chapters". Missing a few chapters but handing in a report that looks complete is worse than failure.
3. **Do not guess when uncertain**: regarding "which links on the index page are chapters", when the strict rules pick none,
   **relax and say so** (`Crawl.loose`), rather than quietly treating the navigation menu as chapters.
Zero dependencies: HTML is parsed with the standard library `html.parser` (do not import bs4 /
lxml) --
this project's attitude toward external dependencies is "add them only if absolutely necessary",
and what is needed here (extract text, extract links)
the standard library happens to have all of it.
"""
from __future__ import annotations

import html as _html
import logging
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_LOG = logging.getLogger('nws.booklab.web')

#: 默认超时（秒）
# [EN] : Default timeout (seconds)
TIMEOUT = 20.0
#: 两次请求之间的间隔（秒）——抓别人的站，留点余地
# [EN] : Interval between two requests (seconds) -- scraping someone else's site, leave a little room
DELAY = 0.3
#: 最多抓几章（防呆：索引页上挂着两千条链接时，别把程序跑死）
# [EN] : Max number of chapters to scrape (foolproofing: when the index page has two thousand links
# [EN] hanging on it, don't run the program to death)
MAX_CHAPTERS = 160
#: 一次最多读多少字节的 HTML（超大页面直接截断）
# [EN] : Max bytes of HTML to read at once (oversized pages are truncated directly)
MAX_BYTES = 4_000_000
#: 认 HTTP 头里这个键
# [EN] : Recognize this key in HTTP headers
_UA = ('Mozilla/5.0 (compatible; NovelWorldSimulator/1.0; '
       '+book-deconstruction)')

#: 链接文字像不像"一章"。
# [EN] : Whether the link text looks like "a chapter".
#:
#: ⚠ 这条正则**只认中文数字与阿拉伯数字**，不认"序章""尾声""番外" ——
#:   那三类各有各的叫法，放进来的话"目录""上一页"这类词也会被卷进来。
#:   宁可漏（有宽松那一道兜底），不要错（错了会把导航当章节）。
# [EN] : ⚠ This regex **only recognizes Chinese numerals and Arabic numerals**, and does not recognize
# [EN] "prologue" "epilogue" "side story" --
# [EN] : those three categories each have their own naming, and if included, words like "catalog"
# [EN] "previous page" would also get swept in.
# [EN] : Better to miss (there is a loose fallback), than to be wrong (a mistake would treat navigation
# [EN] as chapters).
_CH_RE = re.compile(
    r'第\s*[0-9一二三四五六七八九十百千零两]{1,6}\s*[章回节卷篇]'
    r'|[Cc]hapter\s*\d{1,4}'
    r'|^\s*\d{1,4}\s*[、.．,，:：)）]\s*\S'
    r'|^\s*\d{1,4}\s*$'
)
#: 链接地址里像章节的段（有些站点的链接文字是"下一页"这种，靠地址认）
# [EN] : The segment in the link URL that looks like a chapter (some sites' link text is "next page",
# [EN] and you rely on the address to identify it)
_HREF_HINT = re.compile(r'chapter|chap[-_/]|/read/|/(?:book|novel)/\d+', re.I)
#: 这些绝对不是章节
# [EN] : These are definitely not chapters
_BAD_TEXT = re.compile(
    r'^(首页|主页|目录|返回|上一页|下一页|末页|尾页|登录|注册|书架|书评|'
    r'作者|简介|评论区?|排行|分类|搜索|更多|展开|收起|广告|下载|客户端|'
    r'[Hh]ome|[Nn]ext|[Pp]rev(ious)?|[Mm]enu|[Ll]ogin|[Rr]egister)$')


@dataclass
class Link:
    """页面上的一条链接。
        English:
    A link on the page.
    """

    text: str
    href: str

    def as_tuple(self) -> tuple[str, str]:
        return (self.text, self.href)


@dataclass
class Crawl:
    """一次爬取的结果。
        English:
    The result of one crawl.
    """

    url: str = ''
    final_url: str = ''
    title: str = ''
    chapters: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: `True` = 严格规则没挑到章节，用的是放宽规则（**必须说出来**）
    # [EN] : `True` = the strict rules did not pick up chapters, and the relaxed rules were used (**must be
    # [EN] stated**)
    loose: bool = False
    err: str = ''

    @property
    def ok(self) -> bool:
        return bool(self.chapters)

    def summary(self) -> str:
        if self.err:
            return self.err
        return f'{self.title or self.final_url}：{len(self.chapters)} 章'


# ══════════════════════════════════════════════════════════════
#  取页面
# [EN] Fetch page
# ══════════════════════════════════════════════════════════════
def fetch(url: str, *, timeout: float = TIMEOUT) -> tuple[str, str]:
    """取一个页面 → `(HTML, 最终地址)`；失败抛 `RuntimeError`（带能看懂的话）。

    ★ 两条通道：先走 `httpx`（**会用系统代理** —— 用户在墙内、或公司有代理时
      这是唯一能通的路），失败再走 `urllib` + **显式绕过代理**直连
      （本机的回环代理对某些站点返回 502，见项目记忆里那条坑）。
      两条都失败才报错，并在错误里说清**两条都试过了**。
    
        English:
    Fetch one page -> `(HTML, final URL)`; on failure raise `RuntimeError` (with a comprehensible
    message).
        ★ Two channels: first go through `httpx` (**will use the system proxy** -- when the user is behind the GFW, or the company has a proxy,
          this is the only way through), and on failure go through `urllib` + **explicitly bypass the proxy** for a direct connection
          (the local loopback proxy returns 502 for some sites, see that pitfall in the project memory).
          Only report an error if both fail, and state clearly in the error that **both were tried**.
    """
    u = str(url or '').strip()
    if not u:
        raise RuntimeError('没有填网址')
    if not re.match(r'^https?://', u, re.I):
        u = 'http://' + u
    errs: list[str] = []
    try:
        import httpx
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={'User-Agent': _UA}) as c:
            r = c.get(u)
            r.raise_for_status()
            return r.text[:MAX_BYTES], str(r.url)
    except Exception as e:                                       # noqa: BLE001
        errs.append(f'走系统代理不行（{type(e).__name__}）')
    try:
        import urllib.request
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(u, headers={'User-Agent': _UA})
        with op.open(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES)
            return decode_bytes(raw), str(resp.geturl())
    except Exception as e:                                       # noqa: BLE001
        errs.append(f'直连也不行（{type(e).__name__}）')
    raise RuntimeError('这个网址打不开：' + '；'.join(errs)
                       + '。检查一下地址对不对、要不要翻墙')


def decode_bytes(raw: bytes) -> str:
    """字节 → 文本（utf-8 优先，失败再 chardet 探测，最后 replace 兜底）。

    ★ 与开卷那套解码（`ingest.scanner._decode_bytes`）**同一条规矩**：
      先 utf-8，再探测，**最后一定要给出一个字符串**（宁可带几个替换符，
      也不要因为一个字符把整本书判死）。
    
        English:
    Bytes -> text (utf-8 first, then chardet detection on failure, finally replace as a fallback).
        ★ Same rule as the decoding in the unboxing pipeline (`ingest.scanner._decode_bytes`):
          utf-8 first, then detect, **and finally always produce a string** (better to have a few replacement characters
          than to condemn the entire book to death over one character).
    """
    if not raw:
        return ''
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        det = chardet.detect(raw[:10000]) or {}
        enc = det.get('encoding') or 'utf-8'
        return raw.decode(enc, errors='replace')
    except Exception:                                            # noqa: BLE001
        return raw.decode('utf-8', errors='replace')


# ══════════════════════════════════════════════════════════════
#  解析 HTML（标准库，零依赖）
# [EN] Parse HTML (standard library, zero dependencies)
# ══════════════════════════════════════════════════════════════
#: 这些标签里的东西不是正文
# [EN] : The content inside these tags is not body text
_SKIP_TAGS = frozenset({'script', 'style', 'noscript', 'template', 'svg',
                        'head', 'select', 'option', 'iframe'})
#: 这些标签结束时要换行（块级）
# [EN] : These tags require a line break at their end (block-level)
_BLOCK_TAGS = frozenset({'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4',
                         'h5', 'h6', 'section', 'article', 'blockquote',
                         'table', 'ul', 'ol', 'dl', 'dt', 'dd', 'pre', 'hr'})


class _Extract(HTMLParser):
    """一次遍历同时拿到：正文文本、`<a>` 链接、`<title>`。
        English:
    One traversal obtains at the same time: body text, `<a>` links, `<title>`.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[Link] = []
        self.title: str = ''
        self._skip = 0
        self._in_a = False
        self._a_text: list[str] = []
        self._a_href = ''
        self._in_title = False

    # ── 标签 ──
    # [EN] ── Tags ──
    def handle_starttag(self, tag: str, attrs) -> None:           # noqa: ANN001
        t = str(tag or '').lower()
        # ★★ `title` 必须先判 —— `<title>` 永远在 `<head>` 里，而 `head`
        #   是**跳过标签**：先判跳过的话，标题永远读不到（第一版就是这么错的，
        #   而且症状很隐蔽：页面文本是对的，就是标题空着）。
        # [EN] ★★ `title` must be checked first -- `<title>` is always inside `<head>`, and `head`
        # [EN] is a **skip tag**: if you check skip first, the title can never be read (that was the first
        # [EN] version's mistake,
        # [EN] and the symptom was very subtle: the page text was correct, but the title was empty).
        if t == 'title':
            self._in_title = True
            return
        if t in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if t == 'a':
            self._in_a = True
            self._a_text = []
            self._a_href = ''
            for k, v in attrs or []:
                if str(k or '').lower() == 'href':
                    self._a_href = str(v or '')
        if t in _BLOCK_TAGS:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        t = str(tag or '').lower()
        if t == 'title':
            self._in_title = False
            return
        if t in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if t == 'a' and self._in_a:
            self._in_a = False
            txt = ' '.join(''.join(self._a_text).split())
            if self._a_href:
                self.links.append(Link(text=txt, href=self._a_href))
        if t in _BLOCK_TAGS:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        if not data:
            return
        # 标题**先收**：它在 `head` 里，而 `head` 会让 `_skip` 加一
        # [EN] The title **is collected first**: it is inside `head`, and `head` causes `_skip` to be
        # [EN] incremented by one
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        if self._in_a:
            self._a_text.append(data)
        self.parts.append(data)

    # ── 结果 ──
    # [EN] ── Results ──
    def text(self) -> str:
        s = _html.unescape(''.join(self.parts))
        s = re.sub(r'[ \t\u00a0\u3000]+', ' ', s)
        s = re.sub(r' *\n *', '\n', s)
        s = re.sub(r'\n{3,}', '\n\n', s)
        return s.strip()


def parse_page(html: str) -> _Extract:
    """解析一页 HTML（坏标签不抛 —— **半页也能用**）。
        English:
    Parse one HTML page (bad tags do not throw -- **half a page is still usable**).
    """
    ex = _Extract()
    try:
        ex.feed(str(html or ''))
        ex.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('HTML 解析中途出错（已拿到的部分照用）：%r', e)
    return ex


def html_to_text(html: str) -> str:
    """HTML → 纯文本。
        English:
    HTML -> plain text.
    """
    return parse_page(html).text()


def page_title(html: str) -> str:
    """页面标题（`<title>` 优先，取不到就空串）。
        English:
    Page title (`<title>` preferred, empty string if unavailable).
    """
    return ' '.join(parse_page(html).title.split())


# ══════════════════════════════════════════════════════════════
#  挑章节链接
# [EN] Pick chapter links
# ══════════════════════════════════════════════════════════════
def looks_like_chapter(text: str, href: str) -> bool:
    """这条链接像不像"一章"（严格规则）。
        English:
    Whether this link looks like "a chapter" (strict rules).
    """
    t = ' '.join(str(text or '').split())
    if not t or len(t) > 60:
        return False
    if _BAD_TEXT.match(t):
        return False
    if _CH_RE.search(t):
        return True
    return bool(_HREF_HINT.search(str(href or '')))


def chapter_links(html: str, base_url: str) -> tuple[list[Link], bool]:
    """从索引页里挑章节链接 → `(链接, 是不是放宽规则挑的)`。

    两道：
      ① **严格** —— 链接文字像"第X章"（或地址里带 chapter）。
      ② **放宽** —— 严格一个都没挑到时，退而取"同站、文字 2~40 字"的链接。
         放宽**必须让调用方知道**（返回值的第二个），因为这一道可能混进导航条目。
    
        English:
    Pick chapter links from the index page → `(links, whether they were picked with relaxed rules)`.
        Two passes:
          ① **Strict** —— link text looks like "Chapter X" (or the URL contains chapter).
          ② **Relaxed** —— when strict picks nothing, fall back to links "same site, text 2~40 chars".
             Relaxed **must be known to the caller** (second return value), because this pass may mix in navigation entries.
    """
    links = parse_page(html).links
    host = urlparse(base_url).netloc.lower()

    def _abs(h: str) -> str:
        return urljoin(base_url, str(h or '').strip())

    def _same_host(u: str) -> bool:
        return urlparse(u).netloc.lower() == host

    strict: list[Link] = []
    for lk in links:
        u = _abs(lk.href)
        if not u.lower().startswith(('http://', 'https://')):
            continue
        if not _same_host(u):
            continue
        if looks_like_chapter(lk.text, u):
            strict.append(Link(text=' '.join(lk.text.split()) or u, href=u))
    if strict:
        return _dedup(strict), False

    loose: list[Link] = []
    for lk in links:
        u = _abs(lk.href)
        t = ' '.join(str(lk.text or '').split())
        if not u.lower().startswith(('http://', 'https://')):
            continue
        if not _same_host(u) or u.rstrip('/') == str(base_url).rstrip('/'):
            continue
        if not (2 <= len(t) <= 40) or _BAD_TEXT.match(t):
            continue
        if '#' in u or urlparse(u).path in ('', '/'):
            continue
        loose.append(Link(text=t, href=u))
    return _dedup(loose), bool(loose)


def _dedup(links: list[Link]) -> list[Link]:
    """按地址去重（**保留第一次出现的顺序** —— 目录页的顺序就是章节顺序）。
        English:
    Deduplicate by URL (**keep order of first occurrence** —— index page order is chapter order).
    """
    seen: set[str] = set()
    out: list[Link] = []
    for lk in links:
        key = lk.href.split('#')[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(Link(text=lk.text, href=key))
    return out


# ══════════════════════════════════════════════════════════════
#  爬一整本
# [EN] Crawl a whole book
# ══════════════════════════════════════════════════════════════
def crawl_index(url: str, *, limit: int = MAX_CHAPTERS,
                delay: float = DELAY, timeout: float = TIMEOUT,
                on_step=None) -> Crawl:
    """爬一个索引页 → `Crawl`。

    `on_step(key, extra)` 用来给界面报进度（与开卷/拆书其它步骤同一个约定）。

    ⚠ 索引页**自己就是一篇文章**时（没有章节链接）会把这一页当成一章 ——
      用户给的是"某一章的网址"而不是索引时，这样仍然能拆（而不是报"挑不到章节"）。
    
        English:
    Crawl one index page → `Crawl`.
        `on_step(key, extra)` reports progress to the UI (same convention as the other open-book/split-book steps).
        ⚠ When the index page **is itself an article** (no chapter links), treat this page as one chapter ——
          when the user gives "the URL of a single chapter" rather than an index, splitting still works (instead of reporting "no chapters found").
    """
    def _emit(key: str, extra: str = '') -> None:
        if callable(on_step):
            try:
                on_step(key, extra)
            except Exception:                                    # noqa: BLE001
                pass

    c = Crawl(url=str(url or '').strip())
    _emit('web_index')
    try:
        html, final = fetch(c.url, timeout=timeout)
    except Exception as e:                                       # noqa: BLE001
        c.err = str(e)
        return c
    c.final_url = final
    c.title = page_title(html) or c.url
    links, loose = chapter_links(html, final)
    c.loose = loose
    if loose:
        c.notes.append(f'索引页上没有认出标准的章节链接，'
                       f'按同站链接取了 {len(links)} 条（可能混进导航条目，'
                       f'自己核一下）')
    if not links:
        # 没有章节链接 → 这一页**自己**当成一章
        # [EN] No chapter links -> this page **itself** is treated as one chapter
        text = html_to_text(html)
        if text.strip():
            c.chapters = [(c.title or '正文', text)]
            c.notes.append('这个网址上没挑到章节链接，'
                           '把这一页本身当成了一章（如果它是章节目录，'
                           '换那一页的地址再试）')
        else:
            c.err = '这个网址打开是空的（或者内容全是脚本渲染出来的，抓不到文字）'
        return c

    links = links[:max(1, int(limit))]
    _emit('web_chapters', f'{len(links)} 章')
    bad = 0
    for i, lk in enumerate(links, 1):
        try:
            one, _f = fetch(lk.href, timeout=timeout)
            t = html_to_text(one)
        except Exception as e:                                   # noqa: BLE001
            bad += 1
            if bad <= 8:
                c.notes.append(f'第 {i} 章（{lk.text[:24]}）抓失败：'
                               f'{type(e).__name__}')
            t = ''
        if t.strip():
            c.chapters.append((lk.text, t))
        else:
            bad += 1
        _emit('web_one', f'{i}/{len(links)}')
        if delay > 0 and i < len(links):
            time.sleep(float(delay))
    if bad:
        c.notes.append(f'共 {bad} 章没抓到 / 抓到的是空的（**这本书是残缺的**，'
                       f'别把这次的结论当成全书的结论）')
    return c
