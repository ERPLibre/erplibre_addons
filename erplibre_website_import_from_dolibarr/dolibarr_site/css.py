# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""styles.css.php and javascript.js.php of a Dolibarr website.

The PHP wrapper is removed with Dolibarr's own expression; the few
expressions of the stock templates are evaluated statically; any other
PHP is removed and reported. Top-level html, :root and body selectors are
rescoped so the imported CSS does not restyle Odoo's own pages.

The input is untrusted. Every scan is iterative and linear in the input
(no nested quantifier, no per-token rescan of the block stack), and
malformed CSS (unbalanced braces, unterminated comment or string) is
passed through unchanged instead of raising.
"""

import re

from . import php
from .messages import finding
from .model import valid_key

PHP_WRAPPER = re.compile(
    r"<\?php \/\/ BEGIN PHP[^\?]*END PHP( \?>)?\n*", re.I | re.M | re.S
)
_PHP_OPEN = re.compile(r"<\?(php\b|=)", re.I)
_MAINCOLOR = re.compile(
    r"^echo\s*\(?\s*empty\(\$website->(?:maincolor|maincolorbis)\)\s*\?"
    r"\s*'(?P<lit>[^']*)'\s*:.*$"
)
_GLOBAL = re.compile(
    r"^echo\s*getDolGlobalString\('\w+'\)\s*\?:\s*'(?P<lit>[^']*)'$"
)
_REF = re.compile(r"^echo\s*\$website->ref$")
_MEDIA_URL = re.compile(r"url\(\s*(['\"]?)(?:\./)?medias/", re.I)
_URL_END = re.compile(r"\s*\)")
# Longest tail searched for the end of a url(); media paths stay below it.
_URL_WINDOW = 400
_SAFE_LITERAL = re.compile(r"[\w #%.,()+/-]{0,64}")
_JS_COMMENT_START = re.compile(r"/[*/]")

_SPECIAL = re.compile(r"/\*|['\"\\]")
_STRUCTURE = re.compile(r"[{};]")
_TOP = re.compile(r"^(\s*)(html|:root|body)(?=$|[\s.#:\[>+~])", re.I)
_HTML_BODY = re.compile(
    r"^(\s*)(?:html|:root)(?:\s*>\s*|\s+)body(?![\w-])", re.I
)
_SCOPED = re.compile(r"\.bodywebsite(?![\w-])")
_AT_NAME = re.compile(r"@([\w-]+)")
# At-rules whose block holds style rules of the same level.
_GROUP_AT = frozenset(
    ("media", "supports", "layer", "container", "-moz-document", "document")
)
BODY_SCOPE = "body.bodywebsite"
ROOT_SCOPE = "html:has(> body.bodywebsite)"
# Findings of one kind are capped so a hostile file cannot flood the
# report; the rewriting itself is never capped.
MAX_RESCOPED = 200
MAX_REMOVED = 200


def _unwrap(content):
    """(text, marks): the content without its PHP prelude and postlude.

    marks lists (offset in text, newlines removed so far), so a position
    in text maps back to a line of the original content.
    """
    content = content or ""
    out, marks, pos, removed, size = [], [], 0, 0, 0
    for found in PHP_WRAPPER.finditer(content):
        piece = content[pos : found.start()]
        out.append(piece)
        size += len(piece)
        removed += found.group().count("\n")
        marks.append((size, removed))
        pos = found.end()
    out.append(content[pos:])
    return "".join(out), marks


def unwrap_php(content):
    """Content without Dolibarr's PHP prelude and postlude."""
    return _unwrap(content)[0]


def _safe_literal(text):
    """True when text cannot leave the CSS value it is put into.

    Refused: any of ;{}<>\\ quotes, "/*", "@", ":" (so no url() with a
    scheme), "//" (no protocol-relative URL), a newline, more than 64 characters, and unbalanced
    parentheses that could close the surrounding function.
    """
    if not _SAFE_LITERAL.fullmatch(text) or "/*" in text or "//" in text:
        return False
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _evaluate(code, key):
    """Static value of a normalised block, or None when not evaluable."""
    for pattern in (_MAINCOLOR, _GLOBAL):
        found = pattern.match(code)
        if found:
            lit = found.group("lit")
            return lit if _safe_literal(lit) else None
    if _REF.match(code):
        return key if valid_key(key) else None
    return None


def evaluate_css(content, key, findings):
    """Stylesheet text with its PHP evaluated or removed, and rescoped.

    Each block is compared with the known idioms; the value of one is put
    in place, any other block (or an idiom whose literal or key is not
    safe in CSS) is removed with a php_removed finding.
    """
    text, marks = _unwrap(content)
    out, pos, n = [], 0, len(text)
    line, line_pos, mark, reported = 1, 0, 0, 0
    while pos < n:
        opened = _PHP_OPEN.search(text, pos)
        if not opened:
            break
        code_start = opened.end()
        code_end, after, _closed = php._php_end(text, code_start)
        code = text[code_start:code_end]
        if opened.group(1) == "=":
            code = "echo " + code
        value = _evaluate(php.normalise(code), key)
        if value is None:
            # Lines are counted from the previous block, never from the
            # start; a stripped wrapper before the block adds its lines.
            line += text.count("\n", line_pos, opened.start())
            line_pos = opened.start()
            while mark < len(marks) and marks[mark][0] <= line_pos:
                line += marks[mark][1] - (marks[mark - 1][1] if mark else 0)
                mark += 1
            if reported < MAX_REMOVED:
                reported += 1
                findings.append(
                    finding(
                        "php_removed",
                        page_ref="styles.css.php",
                        ref="styles.css.php",
                        line=line,
                        context="css",
                        code=php.report_code(code),
                        bytes=0,
                    )
                )
            value = ""
        out.append(text[pos : opened.start()])
        out.append(value)
        pos = after
    out.append(text[pos:])
    return rescope(_rewrite_media("".join(out)), findings)


def _rewrite_media(text):
    """url(medias/x) becomes url(/medias/x); unsafe paths become url().

    The end of each url() is searched in a bounded window, so the scan is
    linear. A path with a ".." segment, a backslash (a CSS escape), a
    percent-encoded dot or backslash, a quote or a parenthesis is not
    turned into a site path: the whole url() is emptied.
    """
    out, pos = [], 0
    for found in _MEDIA_URL.finditer(text):
        if found.start() < pos:
            continue
        quote, begin = found.group(1), found.end()
        stop = text.find(quote or ")", begin, begin + _URL_WINDOW)
        if stop < 0:
            continue
        tail = _URL_END.match(text, stop + len(quote))
        if not tail:
            continue
        rest = text[begin:stop]
        unsafe = re.search(r"\.\.|[\\'\"()\x00-\x1f]|%2e|%5c", rest, re.I)
        out.append(text[pos : found.start()])
        if unsafe:
            out.append("url(%s%s)" % (quote, quote))
        else:
            out.append("url(%s/medias/%s%s)" % (quote, rest, quote))
        pos = tail.end()
    out.append(text[pos:])
    return "".join(out)


def _mask(css):
    """css with comments blanked and string contents replaced by "_".

    The result has the length of css, so an offset found in it is valid in
    css. Structural characters inside a comment, a string or after a
    backslash cannot be seen in it. An unterminated comment runs to the
    end; an unterminated string stops at a newline, as in CSS.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        found = _SPECIAL.search(css, i)
        if not found:
            out.append(css[i:])
            break
        out.append(css[i : found.start()])
        i = found.start()
        char = css[i]
        if char == "/":
            end = css.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(" " * (end - i))
            i = end
        elif char == "\\":
            width = min(2, n - i)
            out.append("_" * width)
            i += width
        else:
            j = i + 1
            while j < n and css[j] != char and css[j] not in "\n\r\f":
                j += 2 if css[j] == "\\" else 1
            j = min(j, n)
            closed = j < n and css[j] == char
            out.append(char + "_" * (j - i - 1) + (char if closed else ""))
            i = j + 1 if closed else j
    return "".join(out)


def _pieces(masked):
    """(start, end) of each comma-separated selector, outside brackets."""
    pieces, depth, start = [], 0, 0
    for i, char in enumerate(masked):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            pieces.append((start, i))
            start = i + 1
    pieces.append((start, len(masked)))
    return pieces


def _scope_selector(orig, masked):
    """The rescoped selector, or None when it needs no change."""
    combined = _HTML_BODY.match(masked)
    if combined:
        lead, head, end = combined.group(1), BODY_SCOPE, combined.end()
        if _SCOPED.match(masked, end):
            return None
    else:
        top = _TOP.match(masked)
        if not top:
            return None
        lead, end = top.group(1), top.end()
        if top.group(2).lower() == "body":
            if _SCOPED.match(masked, end):
                return None
            head = BODY_SCOPE
        else:
            head = ROOT_SCOPE
    return orig[: len(lead)] + head + orig[end:]


def _rescope_prelude(orig, masked, findings, room):
    """The prelude of a style rule with its top-level selectors rescoped.

    At most room css_rescoped findings are appended; returns the new
    prelude and the number of findings written.
    """
    out, cursor, written = [], 0, 0
    for start, end in _pieces(masked):
        new = _scope_selector(orig[start:end], masked[start:end])
        if new is None:
            continue
        out.append(orig[cursor:start])
        out.append(new)
        cursor = end
        if written < room:
            written += 1
            findings.append(
                finding(
                    "css_rescoped",
                    selector=orig[start:end].strip()[:100],
                    scoped=new.strip()[:100],
                )
            )
    out.append(orig[cursor:])
    return "".join(out), written


def rescope(css, findings):
    """Rewrite top-level html, :root and body selectors, @media included.

    A style rule is rewritten when every enclosing block is a conditional
    group at-rule (@media, @supports, @layer, @container); rules nested
    in a rule and the content of any other at-rule (@keyframes,
    @font-face) are left alone. Comments and strings are skipped when
    looking for braces. An unterminated comment or string swallows the
    rest of the input, which is then returned unchanged; unbalanced braces
    do not stop the rewriting of the rules that precede or follow them.
    """
    css = css or ""
    masked = _mask(css)
    out, last, start = [], 0, 0
    stack, blocked, reported = [], 0, 0
    for token in _STRUCTURE.finditer(masked):
        i, char = token.start(), token.group()
        if char == "{":
            prelude = masked[start:i]
            group = False
            if blocked == 0:
                lead = prelude.strip()
                if lead.startswith("@"):
                    name = _AT_NAME.match(lead)
                    group = bool(name) and name.group(1).lower() in _GROUP_AT
                else:
                    new, written = _rescope_prelude(
                        css[start:i],
                        prelude,
                        findings,
                        MAX_RESCOPED - reported,
                    )
                    reported += written
                    out.append(css[last:start])
                    out.append(new)
                    last = i
            stack.append(group)
            if not group:
                blocked += 1
        elif char == "}" and stack:
            if not stack.pop():
                blocked -= 1
        start = i + 1
    out.append(css[last:])
    return "".join(out)


def is_empty_js(content):
    """True when the script holds nothing but comments and whitespace."""
    text = unwrap_php(content)
    pos, n = 0, len(text)
    while pos < n:
        found = _JS_COMMENT_START.search(text, pos)
        if text[pos : found.start() if found else n].strip():
            return False
        if not found:
            return True
        if found.group() == "/*":
            end = text.find("*/", found.end())
            pos = n if end < 0 else end + 2
        else:
            end = text.find("\n", found.end())
            pos = n if end < 0 else end + 1
    return True
