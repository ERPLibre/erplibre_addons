# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Dolibarr link and media URL forms, rewritten to engine tokens.

Tokens stay in the page HTML until the Odoo records exist, then a
resolver turns them into final URLs: dolibarr-page:<ref> with an
optional ?query or #fragment, dolibarr-media:<relpath>, dolibarr-logo:.

The rewriter runs on HTML the cleaner already accepted and never widens
it. A value comes out either untouched or as a token built only from a
validated media relpath or page ref, plus a query and fragment limited to
a plain alphabet. Absolute URLs (scheme or host), values holding an engine
marker, and anything that fails validation stay as they are.
"""

import re
import urllib.parse

from lxml import etree

from .model import valid_ref, valid_relpath
from .php import ATTR_TOKEN_RE

PAGE = "dolibarr-page:"
MEDIA = "dolibarr-media:"
LOGO = "dolibarr-logo:"
_MEDIA_SCRIPT = re.compile(r"(?:^|/)(?:viewimage|document|wrapper)\.php$")
_PHP_PAGE = re.compile(
    r"^/?(?:(?P<lang>[a-z]{2,3}(?:_[A-Za-z]{2})?)/)?"
    r"(?P<ref>[A-Za-z0-9_-]{1,128})\.php$"
)
_CSS_URL = re.compile(
    r"url\(\s*(?:'(?P<sq>[^']*)'|\"(?P<dq>[^\"]*)\"|(?P<bare>[^'\")]*))\s*\)",
    re.I,
)
_LOGO_CONST = re.compile(r"__LOGO_[A-Z0-9_]*__")
_LINK_ATTRS = ("href", "src", "poster", "data-slide-bg", "background")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ENCODED_SEP = re.compile(r"%(?:2f|5c|00)", re.I)
_SUFFIX_OK = re.compile(r"[\w.~%=&+,/:@?#-]*")
_NOT_SPACE = re.compile(r"[^\s]+")
# Characters that never belong to a URL the import writes: whitespace,
# controls, quotes, angle brackets, the backtick, and the backslash that
# browsers read as a slash.
_UNSAFE_URL_CHAR = re.compile(r"[\s\x00-\x1f\x7f\\<>\"'`]")
_DESCRIPTOR = re.compile(r"(?:[0-9]+(?:\.[0-9]+)?x|[0-9]+[wh])?")


def plain_url(url):
    """True when url is a string without a character of _UNSAFE_URL_CHAR."""
    return isinstance(url, str) and not _UNSAFE_URL_CHAR.search(url)


def local_path(url):
    """url when it is a plain site path, else "".

    A site path starts with one slash, never "//" or "/\\" (another
    host); a scheme, a relative path and a value that plain_url()
    refuses give "".
    """
    if not plain_url(url) or not url.startswith("/") or url.startswith("//"):
        return ""
    return url


def _local(url):
    """Split a site-relative URL; None for an absolute or unsafe one."""
    raw = (url or "").strip().replace("&amp;", "&")
    if _CONTROL.search(raw) or "\\" in raw or ATTR_TOKEN_RE.search(raw):
        return None
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme or parts.netloc:
        return None
    return parts


def _single(query, name):
    """The one value of a query key; None when absent or repeated."""
    values = urllib.parse.parse_qs(query, keep_blank_values=True).get(name)
    return values[0] if values and len(values) == 1 else None


def media_relpath(url, key):
    """Site media path (image/<key>/... or js/<key>/...) or None."""
    parts = _local(url)
    if parts is None:
        return None
    if _MEDIA_SCRIPT.search(parts.path):
        if _single(parts.query, "modulepart") != "medias":
            return None
        path = _single(parts.query, "file") or ""
    else:
        if _ENCODED_SEP.search(parts.path):
            return None
        path = urllib.parse.unquote(parts.path).lstrip("/")
        if path.startswith("medias/"):
            path = path[len("medias/") :]
    path = path.lstrip("/")
    return path if valid_relpath(path, key) else None


def _suffix(parts):
    """Query and fragment kept in a token, or None when not plain."""
    query = "?" + parts.query if parts.query else ""
    fragment = "#" + parts.fragment if parts.fragment else ""
    tail = query + fragment
    return tail if _SUFFIX_OK.fullmatch(tail) else None


def page_link(url, home_ref):
    """dolibarr-page:<ref>[?q][#f] for a page link form, else None."""
    parts = _local(url)
    if parts is None:
        return None
    home = home_ref if valid_ref(home_ref) else ""
    path = parts.path
    match = _PHP_PAGE.match(path)
    # index.php, with or without a language folder, is the home page.
    is_index = bool(match and match.group("ref") == "index")
    if path in ("", "/") or is_index:
        fragment = _suffix(parts._replace(query=""))
        if fragment is None:
            return None
        if "pageref" in urllib.parse.parse_qs(
            parts.query, keep_blank_values=True
        ):
            ref = _single(parts.query, "pageref")
            return PAGE + ref + fragment if valid_ref(ref) else None
        if path == "" or not home:
            return None
        return PAGE + home + fragment
    if not match or _MEDIA_SCRIPT.search(path):
        return None
    tail = _suffix(parts)
    if tail is None:
        return None
    return PAGE + match.group("ref") + tail


def is_logo(url):
    """True for a local company logo form (modulepart=mycompany, __LOGO_).

    A modulepart=medias URL names a site media file, whatever its name.
    """
    parts = _local(url) if url else None
    if parts is None:
        return False
    if _MEDIA_SCRIPT.search(parts.path):
        modulepart = _single(parts.query, "modulepart")
        if modulepart == "mycompany":
            return True
        if modulepart == "medias":
            return False
        name = _single(parts.query, "file") or ""
    else:
        name = urllib.parse.unquote(parts.path)
    return bool(_LOGO_CONST.fullmatch(name.rsplit("/", 1)[-1]))


def split_token(token):
    """Body and ?query#fragment suffix of a page, media or logo token."""
    body = token.split(":", 1)[1]
    cut = min(
        [i for i in (body.find("?"), body.find("#")) if i >= 0] or [len(body)]
    )
    return body[:cut], body[cut:]


def rewrite_url(value, key, home_ref, allow_page=True):
    """Token for a recognised form, or None to leave the value alone.

    allow_page False (src, poster, srcset) accepts media and logo only.
    """
    if not value or ATTR_TOKEN_RE.search(value):
        return None
    if is_logo(value):
        return LOGO
    relpath = media_relpath(value, key)
    if relpath:
        return MEDIA + relpath
    return page_link(value, home_ref) if allow_page else None


def srcset_candidates(value):
    """(url, descriptor) pairs; a comma inside a URL is part of it."""
    pos = 0
    out = []
    while pos < len(value):
        while pos < len(value) and (value[pos].isspace() or value[pos] == ","):
            pos += 1
        match = _NOT_SPACE.match(value, pos)
        if not match:
            break
        url, pos = match.group(), match.end()
        if url.endswith(","):
            out.append((url.rstrip(","), ""))
            continue
        end = value.find(",", pos)
        end = len(value) if end < 0 else end
        out.append((url, value[pos:end].strip()))
        pos = end + 1
    return out


def _rewrite_srcset(value, key, home_ref):
    """srcset with its media URLs as tokens.

    A descriptor that is not a density or a width means a URL held a
    blank the parse cannot place: the value is then left as it is.
    """
    candidates = srcset_candidates(value)
    if not all(_DESCRIPTOR.fullmatch(d) for _url, d in candidates):
        return value
    out = []
    changed = False
    for url, descriptor in candidates:
        new = rewrite_url(url, key, home_ref, False)
        changed = changed or new is not None
        out.append(" ".join(filter(None, [new or url, descriptor])))
    return ", ".join(out) if changed else value


def _rewrite_style(style, key):
    """Replace media url() in a style; a style with a backslash is kept."""
    if "\\" in style:
        return style

    def repl(match):
        raw = match.group("sq") or match.group("dq")
        bare = raw is None
        if bare:
            raw = match.group("bare")
        relpath = media_relpath(raw, key)
        if not relpath or (bare and ("(" in raw or " " in raw)):
            return match.group(0)
        # valid_relpath refuses both quote characters: 'x' is always safe.
        return "url('%s')" % (MEDIA + relpath)

    return _CSS_URL.sub(repl, style)


def rewrite_links(root, key, home_ref):
    """Replace Dolibarr link and media forms by tokens, in place."""
    for el in root.iter(etree.Element):
        for attr in _LINK_ATTRS:
            value = el.get(attr)
            if value is None:
                continue
            new = rewrite_url(
                value, key, home_ref, attr not in ("src", "poster")
            )
            if new is not None:
                el.set(attr, new)
        if el.get("srcset"):
            el.set("srcset", _rewrite_srcset(el.get("srcset"), key, home_ref))
        if el.get("style"):
            el.set("style", _rewrite_style(el.get("style"), key))
