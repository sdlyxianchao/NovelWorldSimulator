# -*- coding: utf-8 -*-
"""**OCR**：把"没有文字层"的东西读成能拆的正文。

为什么单独一层
--------------
用户 2026-10-27：「有些书籍是图片格式的 你至少要支持常见格式 包括 …
pdf 文字 pdf 图片 …」。图片型的书有两个形状：

  · **扫描版 PDF** —— 有页面、看得见字，但 `pypdf` 一个字都抽不出来；
  · **一堆图片**（`.jpg/.png/.tif`…）—— 书被拆成几百张扫描页/拍照页时就是这样。

★ 这两种**都不是"读不出来"，是"还没 OCR"**。以前 `sources.pdf_hint` 直接写
"要 OCR 才行，本项目不做 OCR" —— 用户拿到的就是一个死胡同。

为什么用 RapidOCR（不是 Tesseract / 系统 OCR）
---------------------------------------------
  · **纯 pip、自带中文模型**：不用另装 exe、不用下载语言包，
    离线可用（本项目的规矩：外部能力要能"不在就拉起来"，不该让用户自己去配）；
  · 中文识别质量远高于 Windows 自带的 OCR，且能处理竖排以外的常规书页；
  · 代价是体积（onnxruntime + 模型，约 80MB）—— 用户已明确选了这条。

⚠ 三个纪律
----------
1. **懒加载**：`import rapidocr_onnxruntime` 会拉起 onnxruntime，**几秒**。
   拆一本**文字版**的书根本不该付这个代价 ⇒ 只有真要 OCR 时才建引擎。
2. **可中断、可看进度**：一本书几百页，OCR 要跑十几分钟。
   ★ 本项目规矩："停止要逐个循环问" —— 每页开头问一次 `should_stop()`，
     而**停下来时交出手上已有的**（半本也比没有强）。
3. **OCR 失败不许静默变空**：读不出来要 `hint()` 说清"该装什么 / 为什么"，
   不许让调用方拿到一个空字符串却不知道发生了什么。

English:
**OCR**: read things that have **no text layer** into splittable body text.
Why a separate layer
--------------
User 2026-10-27: "some books are image-format, at least support the common ones ... text PDF,
image PDF ...". Image books come in two shapes:
  · **scanned PDF** -- has pages, you can see the words, but `pypdf` extracts nothing;
  · **a pile of images** (`.jpg/.png/.tif`...) -- what a book looks like once split into hundreds
    of scanned or photographed pages.
★ Neither is "unreadable"; both are "not OCR'd yet". `sources.pdf_hint` used to say "needs OCR,
this project doesn't do OCR" -- a dead end for the user.
Why RapidOCR (not Tesseract / the system OCR)
---------------------------------------------
  · **pip only, Chinese model bundled**: no extra exe, no language-pack download, works offline
    (this project's rule: an external ability must be startable on demand, not something the user
    has to configure);
  · much better Chinese accuracy than the Windows built-in OCR;
  · the cost is size (onnxruntime + models, ~80MB) -- the user explicitly chose this route.
⚠ Three rules
----------
1. **Lazy load**: `import rapidocr_onnxruntime` pulls up onnxruntime and takes **seconds**. A
   **text** book must not pay that price => the engine is built only when OCR is really needed.
2. **Interruptible, with progress**: a book is hundreds of pages; OCR takes tens of minutes.
   ★ This project's rule: "ask about stopping once per loop" -- ask `should_stop()` at the top of
   every page, and **hand over what you have** when stopping (half a book beats nothing).
3. **OCR failure must not silently become empty**: when it fails, `hint()` must say "what to
   install / why", never let the caller receive an empty string with no idea what happened.
"""
from __future__ import annotations

import logging
from pathlib import Path

_LOG = logging.getLogger('nws.booklab.ocr')

#: 引擎（懒加载，见模块头第 1 条）
# [EN] : The engine (lazy loaded, see rule 1 in the module header)
_ENGINE = None
#: 已经试过加载且**失败**了 ⇒ 不要再试第二次（每拆一页试一次会把界面卡死）
# [EN] : Loading was attempted and **failed** => don't try again (retrying per page would hang the UI)
_LOAD_FAILED = False

#: 扫描件判定：一页少于这么多字就算"这一页没字"
# [EN] : Scan detection: a page with fewer than this many characters counts as "no text"
MIN_CHARS_PER_PAGE = 20
#: 扫描件判定：有字的页**低于这个比例**就算整本是扫描件
# [EN] : Scan detection: if the share of pages with text is **below this**, the whole file is a scan
SCAN_RATIO = 0.15


def available() -> bool:
    """OCR 能不能用（装了没有）。**不建引擎**，只回答"装了没"。
        English:
    Can OCR be used (is it installed). **Does not build the engine**, only answers "installed?".
    """
    try:
        import rapidocr_onnxruntime            # noqa: F401
        return True
    except Exception:                                            # noqa: BLE001
        return False


def hint() -> str:
    """OCR 用不了时**该说的话**（不许只回一个空串）。
        English:
    What to say when OCR is unavailable (never just return an empty string).
    """
    return ('这是图片版的书（没有文字层），要 OCR 才读得出来：'
            'pip install rapidocr-onnxruntime')


def _engine():
    """建（并缓存）OCR 引擎。**失败只记一次**，之后一律返回 None。
        English:
    Build (and cache) the OCR engine. **Failure is recorded once**; afterwards this returns None.
    """
    global _ENGINE, _LOAD_FAILED
    if _ENGINE is not None:
        return _ENGINE
    if _LOAD_FAILED:
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
        return _ENGINE
    except Exception as e:                                       # noqa: BLE001
        _LOAD_FAILED = True
        _LOG.warning('OCR 引擎起不来（%r）—— 这次拆书不再试', e)
        return None


def _result_to_text(result) -> str:
    """RapidOCR 的结果 → 一段文本（按识别顺序一行一条）。
        English:
    RapidOCR result -> one text block (one line per recognized run, in detection order).
    """
    if not result:
        return ''
    lines: list[str] = []
    for row in result:
        try:
            txt = str(row[1] or '').strip()
        except (IndexError, TypeError):
            continue
        if txt:
            lines.append(txt)
    return '\n'.join(lines)


def ocr_image(src) -> str:
    """一张图 → 文本（路径 / bytes / ndarray 都收）。
        English:
    One image -> text (accepts a path / bytes / ndarray).
    """
    eng = _engine()
    if eng is None:
        return ''
    try:
        result, _elapse = eng(src)
        return _result_to_text(result)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('OCR 这一张失败了：%r', e)
        return ''


def render_pdf_pages(path: Path | str, *, dpi: int = 200) -> list[bytes]:
    """PDF 逐页渲染成 PNG（**给 OCR 用的**，不是给人看的预览）。

    ★ 用 `pypdfium2`：纯 pip、无需 poppler/Ghostscript（那是 `pdf2image` 的坑）。
      渲染失败返回空列表 —— 调用方要能据此给出"这份 PDF 打不开"。

        English:
    Render PDF pages into PNGs (**for OCR**, not a preview for humans).
        ★ Uses `pypdfium2`: pip only, no poppler/Ghostscript needed (that is `pdf2image`'s trap).
        Returns an empty list on failure -- callers must be able to say "this PDF won't open".
    """
    try:
        import pypdfium2 as pdfium
    except Exception:                                            # noqa: BLE001
        _LOG.warning('没装 pypdfium2 —— 扫描版 PDF 要它把页面渲染成图')
        return []
    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('PDF 打不开 %s：%r', path, e)
        return []
    out: list[bytes] = []
    try:
        for i in range(len(doc)):
            try:
                page = doc[i]
                img = page.render(scale=dpi / 72).to_pil()
                import io as _io
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                out.append(buf.getvalue())
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('第 %d 页渲染失败：%r', i + 1, e)
                out.append(b'')
    finally:
        try:
            doc.close()
        except Exception:                                        # noqa: BLE001
            pass
    return out


def ocr_pdf(path: Path | str, *, dpi: int = 200,
            progress=None, should_stop=None) -> list[str]:
    """扫描版 PDF → 逐页文本。

    Args:
        path:        PDF 路径。
        dpi:         渲染精度（200 够 OCR；再高只慢不更准）。
        progress:    `f(已完成页数, 总页数)` —— 界面显示进度用。
        should_stop: `f() -> bool` —— **每页开头问一次**（本项目规矩）。
                     返回 True ⇒ **立刻停下，把已经识别的那些页交回去**（半本也比没有强）。

    Returns:
        逐页文本列表（与页码同序；失败的页是空串）。

        English:
    Scanned PDF -> per-page text.
        Args:
        path:        PDF path.
        dpi:         render scale (200 is enough for OCR; higher is only slower).
        progress:    `f(done, total)` -- for the UI to show progress.
        should_stop: `f() -> bool` -- **asked once at the top of every page** (project rule).
                     True => **stop at once and hand back the pages already recognized**
                     (half a book beats nothing).
        Returns:
        Per-page text list (in page order; failed pages are empty strings).
    """
    eng = _engine()
    if eng is None:
        return []
    imgs = render_pdf_pages(path, dpi=dpi)
    if not imgs:
        return []
    out: list[str] = []
    total = len(imgs)
    for i, data in enumerate(imgs):
        if should_stop is not None:
            try:
                if should_stop():
                    _LOG.info('OCR 在第 %d/%d 页被叫停 —— 交出已识别的部分',
                              i, total)
                    break
            except Exception:                                    # noqa: BLE001
                pass
        out.append(ocr_image(data) if data else '')
        if progress is not None:
            try:
                progress(i + 1, total)
            except Exception:                                    # noqa: BLE001
                pass
    return out


def is_scan(pages: list[str]) -> bool:
    """这份 PDF 是不是扫描件（有页面但抽不出字）。

    ★ 判据是**比例**不是"一页都没有"：书里常有一两页是插页/空白页，
      要求"一页都没有字"会把"整本扫描 + 一页版权声明"判成文字版。

        English:
    Is this PDF a scan (has pages but no extractable text)?
        ★ The test is a **ratio**, not "not one page has text": books often have a plate or blank
        page, and demanding "zero pages with text" would classify "whole-book scan + one copyright
        page" as a text PDF.
    """
    if not pages:
        return False
    with_text = sum(1 for t in pages if len((t or '').strip()) >= MIN_CHARS_PER_PAGE)
    return (with_text / len(pages)) < SCAN_RATIO
