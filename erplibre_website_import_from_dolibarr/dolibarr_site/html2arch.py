# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""HTML cleaning, QWeb marker expansion and arch serialisation.

Source HTML is cleaned first: QWeb attributes and <t> elements, comments,
processing instructions, invalid attribute names and XML-forbidden
characters go; an allow-list of elements, attributes and URL schemes
applies; forms that would post to the Odoo form controller go. Only after
that do engine markers become QWeb nodes.

Rendering (render_body and the functions after it) runs in two phases.
The source phase parses the stored HTML, strips QWeb attributes and <t>
elements again, inlines content containers, resolves link and media
tokens and applies the script policy; no QWeb exists yet. The expansion
phase then turns markers into QWeb built only from the fixed templates of
this module, with source values entering an expression only as repr()
literals or integers. finalize() escapes text once more, serialises and
re-parses strictly.
"""

import hashlib
import html
import re
import urllib.parse

import markupsafe
from lxml import etree
from lxml import html as lhtml
from lxml.html import defs
from lxml_html_clean import Cleaner

from . import php
from .messages import finding
from .model import PageError, valid_ref, valid_relpath
from .urls import (
    LOGO,
    MEDIA,
    PAGE,
    local_path,
    split_token,
    srcset_candidates,
)
from .xml_safe import parse_xml_safely, safe_xml_parser

MAX_DEPTH = 250
MAX_TEXT = 10 * 1000 * 1000
_XML_BAD_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_XML_NAME = re.compile(r"[a-z_][a-z0-9_.-]*")
_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):")
_PROBE_STRIP = re.compile(r"[\x00-\x20\x7f\\]+|%(?:[01][0-9a-f]|20|7f)", re.I)
_RAW_OPEN = re.compile(r"<(script|style)\b[^>]*>", re.I)
_TAG_START = re.compile(r"<[A-Za-z/!?]")
_STYLE_BAD = re.compile(
    r"expression\(|javascript:|@import|behavior:|-moz-binding"
)
_RAW_ESCAPE = re.compile(r"</|<!--", re.I)
_CSS_COMMENT = re.compile(r"/\*.*?(?:\*/|$)", re.S)
_IMPORT_AT = re.compile("@import", re.I)
_CSS_WS = "[ \t\r\n\f]*"
_CSS_QUOTED = "\"([^\"\r\n\f]*)\"|'([^'\r\n\f]*)'"
_IMPORT_TARGET = re.compile(
    "{ws}(?:url\\({ws}(?:{q}|([^\"'() \t\r\n\f]*)){ws}\\)|{q})".format(
        ws=_CSS_WS, q=_CSS_QUOTED
    ),
    re.I,
)
_CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")\s]*)", re.I)
_CSS_STRING = re.compile(r"['\"]([^'\"]*)['\"]")
_CSS_STRING_FUNC = re.compile(r"(?:image-set|src)\(", re.I)
SVG_NS = "http://www.w3.org/2000/svg"
_ANIMATIONS = ("animate", "set", "animatemotion", "animatetransform")
_ANIMATION_VALUES = ("to", "from", "by", "values")
_CDN_LIB = re.compile(
    r"(?:^|/)(?:jquery(?:-ui)?|bootstrap)(?:[.-][\w.-]*)?\.(?:js|css)(?:$|[?#])",  # noqa: E501
    re.I,
)
_JQUERY_USE = re.compile(r"(?:\$|jQuery)\s*[(.]")
URL_ATTRS = frozenset(
    "href src action poster background cite longdesc data-slide-bg".split()
)
_FORM_FIELDS = frozenset(
    "email_to email_cc email_bcc website_form_signature".split()
)
SVG_TAGS = frozenset(
    "svg g path circle ellipse line polyline polygon rect text tspan defs"
    " use symbol lineargradient radialgradient stop clippath mask pattern"
    " image desc animate set animatemotion".split()
)
KILL_TAGS = frozenset(
    "base object embed applet frame frameset portal link meta title"
    " noscript".split()
)
ALLOWED_TAGS = (
    (
        frozenset(defs.tags)
        | frozenset(
            "article section header footer hgroup nav aside figure figcaption"
            " main picture source video audio track iframe style script".split()
        )
        | SVG_TAGS
        | {php.MARKER_TAG, php.LOOP_TAG}
    )
    - KILL_TAGS
    - {"html", "head", "body"}
)
SAFE_ATTRS = (
    frozenset(defs.safe_attrs)
    | frozenset(
        "style role target srcset sizes poster loading allow allowfullscreen"
        " frameborder autoplay muted loop controls playsinline preload"
        " download integrity crossorigin referrerpolicy async defer"
        " viewbox d fill stroke stroke-width stroke-linecap stroke-linejoin"
        " cx cy r rx ry x y x1 y1 x2 y2 points transform opacity"
        " fill-opacity stroke-opacity offset stop-color gradientunits"
        " gradienttransform preserveaspectratio attributename to from values"
        " dur repeatcount begin clip-path font-size text-anchor id"
        " contenteditable".split()
    )
) - {"srcdoc", "formaction"}


_UNREADABLE = "invalid:"
# Ids of the module's contact forms, which their data-for span targets.
RESERVED_ID_PREFIX = "dolibarr_form_"


def _probe(value):
    """Comparison form of a URL.

    Character references are decoded once more (a value that a later stage
    decodes again must not turn into a scheme), then ASCII blanks, controls
    and '\\' go and the case is folded.
    """
    try:
        text = html.unescape(value or "")
    except ValueError:
        # An unrepresentable numeric reference: no scheme can be read, so
        # the value must not pass as a plain one.
        return _UNREADABLE
    return _PROBE_STRIP.sub("", text).lower()


def url_allowed(value, attr, keep_scripts):
    match = _SCHEME.match(_probe(value))
    if not match:
        return True
    scheme = match.group(1)
    if scheme in ("http", "https", "mailto", "tel"):
        return True
    if scheme == "data":
        return attr == "src" and _probe(value).startswith("data:image/")
    if scheme == "javascript":
        return keep_scripts
    return False


def style_allowed(value):
    """True when an inline style holds no script vector or unsafe URL.

    Comments are removed first (they can split a keyword), matching runs
    on the case-folded form without blanks, and every URL of a url()
    function or of the string arguments of image-set() and src() must
    pass url_allowed(). A backslash (a CSS escape) and a value _probe()
    cannot read are refused outright.
    """
    if "\\" in value:
        return False
    text = _CSS_COMMENT.sub("", value)
    probed = _probe(text)
    if probed == _UNREADABLE or _STYLE_BAD.search(probed):
        return False
    urls = _CSS_URL.findall(text)
    if _CSS_STRING_FUNC.search(_probe(text)):
        urls += _CSS_STRING.findall(text)
    return all(url_allowed(url, "style", False) for url in urls)


def _data_value_allowed(value, keep_scripts):
    """A data-* value may not open with a script or data: scheme.

    Odoo widgets read some data-* values as URLs, but ordinary values
    (labels, JSON, times) may contain a colon, so only the schemes that
    execute or embed content are refused, and so is a value _probe()
    cannot read.
    """
    probed = _probe(value)
    if probed == _UNREADABLE:
        return False
    match = _SCHEME.match(probed)
    scheme = match.group(1) if match else ""
    if scheme == "javascript":
        return keep_scripts
    return scheme not in ("vbscript", "data")


def _attr_allowed(name, keep_scripts):
    if name.startswith("on"):
        return keep_scripts
    return (
        name in SAFE_ATTRS
        or (name.startswith("data-") and not name.startswith("data-oe-"))
        or name.startswith("aria-")
    )


def _clean_attrs(el, keep_scripts, unsafe, scripts):
    """Apply the attribute allow-list and the URL rules to one element."""
    if "xlink:href" in el.attrib:
        value = el.attrib.pop("xlink:href")
        if "href" not in el.attrib:
            el.set("href", value)
    for name in list(el.attrib):
        lname, value = name.lower(), el.attrib[name]
        if (
            lname.startswith("t-")
            or lname == "groups"
            or lname.startswith("data-oe-")
            or lname in ("srcdoc", "formaction")
        ):
            unsafe.append("%s attribute" % lname)
            del el.attrib[name]
        elif not _XML_NAME.fullmatch(lname):
            unsafe.append("invalid attribute name")
            del el.attrib[name]
        elif not _attr_allowed(lname, keep_scripts):
            if lname.startswith("on"):
                scripts.append("on* handler")
            del el.attrib[name]
        elif lname == "contenteditable":
            el.set(name, "false")
        elif lname == "id" and value.strip().lower().startswith(
            RESERVED_ID_PREFIX
        ):
            unsafe.append("reserved id")
            del el.attrib[name]
        elif (
            lname in URL_ATTRS
            and not url_allowed(value, lname, keep_scripts)
            or lname.startswith("data-")
            and not _data_value_allowed(value, keep_scripts)
        ):
            match = _SCHEME.match(_probe(value))
            if match and match.group(1) == "javascript":
                scripts.append("javascript: URL")
            else:
                unsafe.append("%s URL" % (match.group(1) if match else lname))
            del el.attrib[name]
        elif lname == "srcset" and not all(
            url_allowed(url, "src", keep_scripts)
            for url, _descriptor in srcset_candidates(value)
        ):
            unsafe.append("srcset URL")
            del el.attrib[name]
        elif lname == "style" and not style_allowed(value):
            unsafe.append("style attribute")
            del el.attrib[name]


def _posts_to_odoo_form(action):
    """True when a form action reaches the Odoo form controller.

    Percent-encoding is decoded until stable (a few rounds at most), so
    an encoded letter or slash cannot hide the /website/form path.
    """
    text = action or ""
    for _round in range(4):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return "/website/form" in _probe(text)


def _depth(root):
    deepest, stack = 0, [(root, 1)]
    while stack:
        el, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in el)
    return deepest


def _report(findings, page_ref, code, items):
    if items:
        findings.append(
            finding(
                code,
                page_ref=page_ref,
                ref=page_ref,
                what=", ".join(sorted(set(items))),
            )
        )


def _cleaner(keep_scripts):
    return Cleaner(
        scripts=not keep_scripts,
        javascript=not keep_scripts,
        comments=True,
        style=False,
        inline_style=False,
        links=True,
        meta=True,
        page_structure=True,
        processing_instructions=True,
        embedded=False,
        frames=True,
        forms=False,
        annoying_tags=True,
        remove_unknown_tags=False,
        allow_tags=ALLOWED_TAGS,
        kill_tags=KILL_TAGS,
        safe_attrs_only=False,
    )


def _run_cleaner(root, keep_scripts, unsafe):
    """Run the Cleaner on root; a <style> whose text it changed goes to
    unsafe, since the Cleaner rewrites script vectors in CSS silently."""
    before = [(el, el.text) for el in root.iter("style")]
    _cleaner(keep_scripts)(root)
    for el, text in before:
        if el.text != text and _attached(el, root):
            unsafe.append("<style> rewritten")


def close_raw_elements(text):
    """Close every script or style element the source leaves open.

    The HTML parser reads a raw-text element up to its end tag, so an
    unclosed one would swallow the rest of the source. Its content is cut
    at the next tag-looking '<' (or at the end of the text) and the end tag
    is inserted there; a properly closed element is left untouched.
    """
    out, pos = [], 0
    while True:
        match = _RAW_OPEN.search(text, pos)
        if not match:
            out.append(text[pos:])
            return "".join(out)
        name = match.group(1)
        end = re.compile(r"</%s(?=[\s/>]|$)" % name, re.I).search(
            text, match.end()
        )
        if end:
            out.append(text[pos : end.end()])
            pos = end.end()
            continue
        cut = _TAG_START.search(text, match.end())
        cut = cut.start() if cut else len(text)
        out.append(text[pos:cut] + "</%s>" % name)
        pos = cut


def fragment_html(root):
    """Children of a <div> root serialised as HTML."""
    parts = [root.text or ""]
    parts.extend(lhtml.tostring(child, encoding="unicode") for child in root)
    return "".join(parts)


def _imports(css):
    """Target of each "@import" of css, or None where none can be read.

    Every case-insensitive occurrence of "@import" in the raw text counts,
    inside a comment or a string too: a browser and a comment stripper
    disagree on where those end, so none is skipped. A target is a quoted
    string or the argument of url(), after optional CSS whitespace.
    """
    targets = []
    for at in _IMPORT_AT.finditer(css):
        match = _IMPORT_TARGET.match(css, at.end())
        groups = match.groups() if match else (None,)
        targets.append(next((g for g in groups if g is not None), None))
    return targets


def _import_allowed(target, css_hosts):
    """True when an @import target is relative or on a host of css_hosts.

    A relative target has no host and no scheme; None (an unreadable
    target) is refused.
    """
    if target is None:
        return False
    host = _host(target)
    if host:
        return host in css_hosts
    return not _SCHEME.match(_probe(target))


def _body_style_refusal(css, keep_scripts):
    """Why a body <style> with text css must go; '' when it may stay.

    A backslash (a CSS escape) is refused, as in style_allowed(). An
    @import must be relative, and with keep_scripts False there may be
    none, since the Cleaner rewrites the rule.
    """
    if "\\" in css:
        return "<style> escape"
    imports = _imports(css)
    if imports and not (
        keep_scripts and all(_import_allowed(t, ()) for t in imports)
    ):
        return "<style> @import"
    return ""


def _animates_link_or_handler(el):
    """True when an SVG animation element targets href or an on* handler."""
    target = next(
        (v for k, v in el.attrib.items() if k.lower() == "attributename"), ""
    )
    target = target.strip().lower().rsplit(":", 1)[-1]
    return target == "href" or target.startswith("on")


def _animation_values_allowed(el):
    """True when every to, from, by and values item passes url_allowed().

    The check ignores attributeName, which a later stage may not see, and
    refuses javascript: whatever keep_scripts says: an animated link is not
    a script the review counts.
    """
    for name, value in el.attrib.items():
        if name.lower() not in _ANIMATION_VALUES:
            continue
        for item in (value or "").split(";"):
            if not url_allowed(item, "href", False):
                return False
    return True


def _animation_refusal(el, tag):
    """Why an SVG animation element must go; '' when it may stay."""
    if _animates_link_or_handler(el):
        return "<%s> on href" % tag
    if not _animation_values_allowed(el):
        return "<%s> value URL" % tag
    return ""


def _keep_use_local(el, unsafe):
    """A <use> in the body may reference only a fragment of the document."""
    href = el.get("href")
    if href is not None and not _probe(href).startswith("#"):
        unsafe.append("external <use> href")
        del el.attrib["href"]


def _in_foreign_content(el):
    """True when el sits inside an svg or math element."""
    return any(
        isinstance(up.tag, str) and up.tag.lower() in ("svg", "math")
        for up in el.iterancestors()
    )


def _iframe_src_allowed(el, marker_src):
    """An iframe src is https, or, with marker_src, opens on a marker.

    marker_src holds only for text the assembler produced: its marker
    tokens are its own, source look-alikes having been neutralised. Such
    a src is resolved at render, where the element rules judge the value
    a visitor gets.
    """
    src = el.get("src") or ""
    if _probe(src).startswith("https:"):
        return True
    return marker_src and bool(php.ATTR_TOKEN_RE.match(src))


def _scrub(root, keep_scripts, unsafe, forms, scripts, marker_src=False):
    """Element-level pass shared by the analysis clean and the policy.

    Removes what the allow-list forbids and records it in the three lists;
    the Cleaner runs afterwards and does the rest.
    """
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        _clean_attrs(el, keep_scripts, unsafe, scripts)
        if el is root:
            continue
        if tag == "use":
            _keep_use_local(el, unsafe)
        if tag in KILL_TAGS:
            unsafe.append("<%s>" % tag)
        elif ":" in tag:
            unsafe.append("<%s>" % tag)
            el.drop_tree()
        elif tag in ("script", "style") and (
            _in_foreign_content(el)
            or len(el)
            or _RAW_ESCAPE.search(el.text or "")
        ):
            unsafe.append("<%s> that can leave raw text" % tag)
            el.drop_tree()
        elif tag == "style" and (
            why := _body_style_refusal(el.text or "", keep_scripts)
        ):
            unsafe.append(why)
            el.drop_tree()
        elif tag == "script" and not keep_scripts:
            scripts.append("script element")
        elif tag == "iframe" and not _iframe_src_allowed(el, marker_src):
            unsafe.append("non-https iframe")
            el.drop_tree()
        elif tag in _ANIMATIONS and (why := _animation_refusal(el, tag)):
            unsafe.append(why)
            el.drop_tree()
        elif tag == "form" and _posts_to_odoo_form(el.get("action")):
            forms.append("form")
            el.drop_tree()
        elif (
            tag in ("input", "textarea", "select", "button")
            and (el.get("name") or "").lower() in _FORM_FIELDS
        ):
            forms.append("%s %s" % (tag, el.get("name").lower()))
            el.drop_tree()
        elif el.get("data-for") is not None:
            forms.append("data-for element")
            el.drop_tree()
        elif tag == "t":
            el.drop_tag()


def clean_fragment(
    source, page_ref, findings, keep_scripts=True, trusted_markers=False
):
    """Parse and clean one HTML fragment; return its <div> root.

    trusted_markers keeps the engine's dolibarr-q and dolibarr-loop
    elements and an iframe whose src opens on a marker token; any other
    input has marker look-alikes neutralised first.
    """
    text = close_raw_elements(_XML_BAD_CHARS.sub("", source or ""))
    if not trusted_markers:
        text = php.neutralise(text)
    try:
        root = lhtml.fragment_fromstring(text, create_parent="div")
    except (etree.ParserError, etree.XMLSyntaxError, ValueError) as exc:
        raise PageError(page_ref, "unparseable markup: %s" % exc) from exc
    if _depth(root) > MAX_DEPTH:
        raise PageError(page_ref, "markup deeper than %d levels" % MAX_DEPTH)
    unsafe, forms, scripts = [], [], []
    _scrub(root, keep_scripts, unsafe, forms, scripts, trusted_markers)
    _run_cleaner(root, keep_scripts, unsafe)
    _report(findings, page_ref, "unsafe_markup_removed", unsafe)
    _report(findings, page_ref, "form_removed", forms)
    _report(findings, page_ref, "script_removed", scripts)
    return root


def script_counts(root):
    counts = {
        "inline scripts": 0,
        "script files": 0,
        "on* handlers": 0,
        "javascript: URLs": 0,
        "iframes": 0,
    }
    for el in root.iter(etree.Element):
        tag = el.tag.lower() if isinstance(el.tag, str) else ""
        if tag == "script":
            counts["script files" if el.get("src") else "inline scripts"] += 1
        elif tag == "iframe":
            counts["iframes"] += 1
        for name, value in el.attrib.items():
            if name.lower().startswith("on"):
                counts["on* handlers"] += 1
            elif name.lower() in URL_ATTRS and _probe(value).startswith(
                "javascript:"
            ):
                counts["javascript: URLs"] += 1
    return counts


def add_counts(counts, more):
    """counts plus more, key by key, as a new dict."""
    out = dict(counts)
    for key, value in more.items():
        out[key] = out.get(key, 0) + value
    return out


def external_script_hosts(roots, allowed_hosts):
    """Sorted hosts of the script src URLs of roots outside allowed_hosts."""
    hosts = set()
    for root in roots:
        for el in root.iter("script"):
            host = _host(el.get("src") or "")
            if host and host not in allowed_hosts:
                hosts.add(host)
    return sorted(hosts)


def script_summary(counts, hosts=()):
    """(total, detail) of counts; detail names each external host."""
    detail = "; ".join("%s: %d" % (k, v) for k, v in counts.items() if v)
    if hosts:
        detail = "; ".join(
            filter(None, [detail, "external hosts: %s" % ", ".join(hosts)])
        )
    return sum(counts.values()), detail


def apply_script_policy(root, page_ref, findings, keep_scripts):
    """Keep or remove scripts, on* handlers and javascript: URLs.

    Removal runs the same element pass and Cleaner as a direct clean with
    keep_scripts=False, so a tree parsed back from stored HTML is held to
    the same rules as a fresh one.
    """
    counts = script_counts(root)
    counts.pop("iframes")
    count, detail = script_summary(counts)
    if keep_scripts:
        if count:
            findings.append(
                finding(
                    "script_kept",
                    page_ref=page_ref,
                    ref=page_ref,
                    what=detail,
                )
            )
        return
    unsafe, forms = [], []
    _scrub(root, False, unsafe, forms, [])
    _run_cleaner(root, False, unsafe)
    _report(findings, page_ref, "unsafe_markup_removed", unsafe)
    _report(findings, page_ref, "form_removed", forms)
    if count:
        findings.append(
            finding(
                "script_removed", page_ref=page_ref, ref=page_ref, what=detail
            )
        )


def _host(url):
    """Host a browser would fetch url from; '' for a same-site URL.

    Backslashes count as slashes and tab, CR and LF vanish, as a browser
    reads them. An absolute or protocol-relative URL without a parsable
    host yields '?', which no allow-list contains.
    """
    text = re.sub(r"[\t\r\n]", "", url).strip().replace("\\", "/")
    parts = urllib.parse.urlsplit(text)
    if parts.scheme in ("http", "https") or text.startswith("//"):
        return (parts.hostname or "?").lower()
    return ""


def _describe(el):
    tag = el.tag.lower() if isinstance(el.tag, str) else "node"
    for attr in ("name", "http-equiv", "property", "rel"):
        if el.get(attr):
            return "%s %s=%s" % (tag, attr, el.get(attr)[:60])
    return tag


def _strip_handlers(el, unsafe):
    """Head assets need no event handlers: remove every on* attribute."""
    for name in list(el.attrib):
        if name.lower().startswith("on"):
            unsafe.append("on* handler")
            del el.attrib[name]


def _head_style_ok(el, page_ref, findings, css_hosts, unsafe):
    """True when a head <style> may stay; report why it may not.

    A backslash or an unreadable or non-relative, hostless @import goes
    to unsafe; an @import of a host outside css_hosts is reported as
    css_external_removed.
    """
    text = el.text or ""
    if "\\" in text:
        unsafe.append("<style> escape")
        return False
    bad = [t for t in _imports(text) if not _import_allowed(t, css_hosts)]
    for url in bad:
        if url is not None and _host(url):
            findings.append(
                finding(
                    "css_external_removed",
                    page_ref=page_ref,
                    ref=page_ref,
                    url=url[:200],
                )
            )
        else:
            unsafe.append("<style> @import")
    return not bad


def clean_head(source, page_ref, findings, css_hosts):
    """Keep stylesheets, style and script elements of a head fragment.

    Everything else (meta, base, title, icons) is dropped: Odoo writes its
    own charset, viewport and favicon, and the page's description and
    keywords come from the page columns. Bootstrap and jQuery from a CDN
    are dropped because Odoo ships its own; a stylesheet from a host
    outside css_hosts is dropped.
    """
    text = php.neutralise(
        close_raw_elements(_XML_BAD_CHARS.sub("", source or ""))
    )
    if not text.strip():
        return ""
    doc = lhtml.document_fromstring(
        "<html><head>%s</head><body></body></html>" % text
    )
    kept, dropped, unsafe, jquery = [], [], [], False
    for el in list(doc.head) + list(doc.body):
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.lower()
        given = el.get("href") or ""
        _strip_handlers(el, unsafe)
        _clean_attrs(el, True, unsafe, [])
        href, src = el.get("href") or "", el.get("src") or ""
        if tag == "link" and "stylesheet" in (el.get("rel") or "").lower():
            host = _host(href)
            if given and not href:
                dropped.append("stylesheet link with an unsafe URL")
            elif host and _CDN_LIB.search(href):
                dropped.append("link %s" % href[:80])
            elif host and host not in css_hosts:
                findings.append(
                    finding(
                        "css_external_removed",
                        page_ref=page_ref,
                        ref=page_ref,
                        url=href[:200],
                    )
                )
            elif href:
                kept.append(el)
        elif tag == "style":
            if _head_style_ok(el, page_ref, findings, css_hosts, unsafe):
                kept.append(el)
        elif tag == "script":
            if src and _host(src) and _CDN_LIB.search(src):
                dropped.append("script %s" % src[:80])
                continue
            if not src and _JQUERY_USE.search(el.text or ""):
                jquery = True
            kept.append(el)
        else:
            dropped.append(_describe(el))
    _report(findings, page_ref, "unsafe_markup_removed", unsafe)
    _report(findings, page_ref, "head_asset_dropped", dropped)
    if jquery:
        findings.append(
            finding(
                "inline_script_needs_jquery", page_ref=page_ref, ref=page_ref
            )
        )
    return "".join(lhtml.tostring(el, encoding="unicode") for el in kept)


def sanitize_svg(data):
    """Clean an SVG whatever keep_scripts says; return (bytes, removed).

    The root must be an svg element, in the SVG namespace or in none;
    any other document raises ValueError.

    Removed: every element outside the SVG namespace (an XHTML iframe or
    object is active content), script, foreignObject, style, handler and
    listener elements, on* attributes, non-local href, and animations that
    target href or an on* attribute.
    """
    try:
        root = parse_xml_safely(data)
    except etree.XMLSyntaxError as exc:
        raise ValueError("unreadable SVG: %s" % exc) from exc
    name = etree.QName(root)
    if name.namespace not in (None, SVG_NS) or name.localname != "svg":
        raise ValueError("not an SVG document")
    removed, doomed = [], []
    for el in root.iter():
        if not isinstance(el.tag, str):
            doomed.append(el)
            continue
        name = etree.QName(el)
        local = name.localname.lower()
        if name.namespace not in (None, SVG_NS):
            removed.append("foreign element")
            doomed.append(el)
            continue
        if local in (
            "script",
            "foreignobject",
            "style",
            "handler",
            "listener",
        ):
            removed.append(local)
            doomed.append(el)
            continue
        if local in _ANIMATIONS and _animates_link_or_handler(el):
            removed.append(local)
            doomed.append(el)
            continue
        for attr in list(el.attrib):
            lname = etree.QName(attr).localname.lower()
            value = (el.attrib[attr] or "").strip()
            if lname.startswith("on"):
                removed.append("on* attribute")
                del el.attrib[attr]
            elif lname == "href" and not (
                value.startswith("#")
                or (local != "use" and _probe(value).startswith("data:image/"))
            ):
                removed.append("external href")
                del el.attrib[attr]
    for el in doomed:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
    return (
        etree.tostring(root, xml_declaration=True, encoding="utf-8"),
        sorted(set(removed)),
    )


PREFIX = "dolibarr_import"
TEMPLATE_MODULE = "erplibre_website_import_from_dolibarr"
MAX_INCLUDE_DEPTH = 20
MAX_INCLUDES = 200
_RAW = ("script", "style")
_TOKEN = "DOLIBARRQ%sQ"
_TOKEN_SPLIT = re.compile(r"(DOLIBARRQ[0-9]+Q)")
_LAYOUT_ROLES = ("header", "footer")
# Statuses of a page whose body may be inlined where it is included; the
# body of any other page is empty or was refused.
_USABLE_CONTAINERS = ("container", "import")
_ELEMENT_KINDS = frozenset(
    "company address title text social blog_list blog_field".split()
)
_COMPANY_FIELDS = frozenset("name email phone website zip city street".split())
_BLOG_EXPR = {
    "title": "blog.name",
    "description": "blog.subtitle",
    "author": "blog.author_name",
    "url": "blog.website_url",
    "image": "blog.dolibarr_import_cover_url",
    "date": "blog.post_date and blog.post_date.strftime('%Y-%m-%d')",
}
_LOGO_EXPR = "'/web/image/website/%s/logo' % website.id"
_MAP_EXPR = "res_company.partner_id.google_map_link(13) + '&output=embed'"
# Stand-in for the live map URL while the script policy checks the iframe:
# the policy only needs to see an https URL where Odoo will put one.
_MAP_PROBE = "https://maps.google.com/maps?output=embed"
_ADDRESS_OPTIONS = (
    "{'widget': 'contact', 'fields': ['address'], 'no_marker': True}"
)
_LOOP_EXPR = (
    "request.env['blog.post'].search([('blog_id', '=', %d),"
    " ('website_published', '=', True)], order='post_date desc', limit=%d)"
)
# The link rewriter always writes url('<token>'); a relpath holds no quote,
# so the closing quote ends the token even when the name has parentheses.
_TOKEN_URL = re.compile(
    r"url\(\s*'((?:dolibarr-media|dolibarr-logo):[^']*)'\s*\)"
)
_ANY_TOKEN = re.compile(r"dolibarr-(?:page|media|logo|blog):", re.I)
_TO_ENCODE = re.compile("[ \x80-\U0010ffff]")
_FORM_CONTROLS = ("input", "textarea", "select", "button")
_TOKEN_SUFFIX = re.compile(r"(?:[?#][\w.~%=&+,/:@?#-]*)?")
_QWEB_ATTR_NAME = re.compile(r"[a-z_][a-z0-9_-]*")
_SAFE_PREFIX = re.compile(
    r"(?:https?://[^/]|mailto:|tel:|/[^/\\\s\x00-\x1f]|[?#])", re.I
)
# Literal prefixes after which a company value may bind in a URL
# attribute: each fixes the scheme, and "/" or "https://<host>/" the
# host too, since the value can never start the URL.
_COMPANY_PREFIX = re.compile(
    r"(?:mailto:|tel:|/[^/\\\s\x00-\x1f]|https://[^/\\\s?#@]+/)", re.I
)
# A bare company value in a URL attribute: (condition, value) templates.
# The attribute yields the value only when the condition holds, else ''.
_GUARDED_COMPANY = {
    "website": (
        "(res_company.website or '').lower()"
        ".startswith(('http://', 'https://'))",
        "res_company.website",
    ),
    "email": (
        "res_company.email and ':' not in res_company.email",
        "'mailto:' + res_company.email",
    ),
    "phone": ("res_company.phone", "'tel:' + res_company.phone"),
}


def key_hash(key):
    """First 12 hex digits of the SHA-1 of the source key."""
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def view_key(key, ref):
    """Key and t-name of a page view; ref must pass valid_ref()."""
    if not valid_ref(ref):
        raise PageError(ref, "invalid page ref")
    return "%s.k%s.%s" % (PREFIX, key_hash(key), ref)


def head_key(key):
    return "%s.k%s.head" % (PREFIX, key_hash(key))


def blog_style_key(key):
    return "%s.k%s.blog_style" % (PREFIX, key_hash(key))


class DictResolver:
    """Resolver backed by dicts, for the engine tests and the CLI.

    The protocol: page_url(ref) and media_url(relpath) return a site path
    or None; blog_id() and website_id() return integers. The renderer
    accepts only a path that urls.local_path() keeps; anything else counts
    as unresolved.
    """

    def __init__(self, pages=None, media=None, blog_id=0, website_id=0):
        self.pages = pages or {}
        self.media = media or {}
        self._blog_id = blog_id
        self._website_id = website_id

    def page_url(self, ref):
        return self.pages.get(ref)

    def media_url(self, relpath):
        return self.media.get(relpath)

    def blog_id(self):
        return self._blog_id

    def website_id(self):
        return self._website_id


def _int(value, minimum=0):
    """value as an int no lower than minimum; minimum when unreadable."""
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return minimum


def _xml_text(value):
    """str(value) without the characters XML cannot hold."""
    return _XML_BAD_CHARS.sub("", "" if value is None else str(value))


def _add_text(parent, index, text):
    if not text:
        return
    if index == 0:
        parent.text = (parent.text or "") + text
    else:
        sibling = parent[index - 1]
        sibling.tail = (sibling.tail or "") + text


def _replace(node, items):
    """Put items (strings and elements) where node is; keep its tail."""
    parent = node.getparent()
    if parent is None:
        return
    index = parent.index(node)
    tail = node.tail or ""
    parent.remove(node)
    for item in list(items) + [tail]:
        if isinstance(item, str):
            _add_text(parent, index, item)
        else:
            parent.insert(index, item)
            index += 1


def _drop(node):
    _replace(node, [])


def _attached(el, root):
    return el is root or any(up is root for up in el.iterancestors())


def _size(el):
    html_text = lhtml.tostring(el, encoding="unicode", with_tail=False)
    return len(html_text.encode("utf-8"))


def _strip_qweb(root):
    """Remove what QWeb would read as a directive from source HTML.

    Attributes named t-*, data-oe-* or groups, and attribute names that are
    not plain XML names, go; <t> elements are unwrapped; comments,
    processing instructions and namespaced elements go.
    """
    for el in list(root.iter()):
        if el is root:
            continue
        if not isinstance(el.tag, str):
            _drop(el)
            continue
        tag = el.tag.lower()
        if not _XML_NAME.fullmatch(tag):
            _drop(el)
            continue
        for name in list(el.attrib):
            lname = name.lower()
            if (
                lname.startswith(("t-", "data-oe-"))
                or lname == "groups"
                or not _XML_NAME.fullmatch(lname)
            ):
                del el.attrib[name]
        if tag == "t":
            el.drop_tag()


def _parse(source, ref):
    """Stored HTML as a <div> root, bounded in depth, QWeb stripped."""
    text = close_raw_elements(_XML_BAD_CHARS.sub("", source or ""))
    try:
        root = lhtml.fragment_fromstring(text, create_parent="div")
    except (etree.ParserError, etree.XMLSyntaxError, ValueError) as exc:
        raise PageError(ref, "unparseable markup: %s" % exc) from exc
    if _depth(root) > MAX_DEPTH:
        raise PageError(ref, "markup deeper than %d levels" % MAX_DEPTH)
    _strip_qweb(root)
    return root


def _plain(value):
    """Text content of an untrusted HTML value, marker look-alikes inert."""
    text = php.neutralise(_xml_text(value))
    if not text.strip():
        return text
    try:
        root = lhtml.fragment_fromstring(text, create_parent="span")
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return ""
    return _xml_text(root.text_content())


class _Render:
    """State of one page or post render: target is 'page' or 'post'.

    Marker ids are local to the page or container that holds them; load()
    renumbers them into self.nodes, so a container inlined twice or two
    containers with the same ids never share a payload by accident.
    """

    def __init__(self, site, page, resolver, company, opts, findings, target):
        if target not in ("page", "post"):
            raise ValueError("target must be 'page' or 'post'")
        self.site = site
        self.key = site.source_key if site is not None else ""
        self.page = page
        self.resolver = resolver
        self.company = company or {}
        self.opts = opts
        self.findings = findings
        self.target = target
        self.nodes = {}
        self.attrs = []
        self.includes = 0
        self.inlined_bytes = 0
        self.inlined = set()
        self.logos = []
        self.unsafe = []
        self.spans = []
        self.forms = 0
        self.search_reported = False

    @property
    def live(self):
        return self.target == "page"

    def _el(self, near, tag, attrib):
        return near.makeelement(tag, attrib)

    def _removed(self, what, node=None, nbytes=0):
        self.findings.append(
            finding(
                "php_removed",
                page_ref=self.page.ref,
                ref=self.page.ref,
                line=_int((node or {}).get("line")),
                context=self.target,
                code=what,
                bytes=nbytes,
            )
        )

    # Source phase.

    def load(self, source, owner, depth, stack):
        root = _parse(source, self.page.ref)
        self._bind(root, owner)
        for marker in list(root.iter(php.MARKER_TAG)):
            node = self._node(marker)
            if node.get("kind") == "include":
                _replace(marker, self._include(node, depth, stack))
        return root

    def _bind(self, root, owner):
        """Renumber markers; move attribute markers to self.attrs.

        An attribute holding a marker leaves the tree here and lives only
        in self.attrs as [element, name, value, probe]; text written into
        the tree later (a resolved URL, a payload) can never become one. A
        token value (dolibarr-page: and the like) is never read as a
        marker: resolve_value() refuses one that looks like a marker.
        """
        payloads, local = owner.qweb_nodes or {}, {}

        def global_id(lid):
            if lid not in local:
                key = str(len(self.nodes) + 1)
                node = payloads.get(lid)
                self.nodes[key] = node if isinstance(node, dict) else {}
                local[lid] = key
            return local[lid]

        for el in root.iter(etree.Element):
            if el.tag in (php.MARKER_TAG, php.LOOP_TAG):
                lid = el.get("id") or ""
                el.attrib.clear()
                el.set("id", global_id(lid))
                continue
            for name, value in list(el.attrib.items()):
                if _ANY_TOKEN.match(value) or not php.ATTR_TOKEN_RE.search(
                    value
                ):
                    continue
                del el.attrib[name]
                bound = php.ATTR_TOKEN_RE.sub(
                    lambda m: _TOKEN % global_id(m.group(1)), value
                )
                self.attrs.append([el, name, bound, None])

    def _node(self, marker):
        return self.nodes.get(marker.get("id") or "") or {}

    def _token_node(self, token):
        match = php.ATTR_TOKEN_RE.fullmatch(token)
        return (self.nodes.get(match.group(1)) if match else None) or {}

    def _include(self, node, depth, stack):
        """Content of a content container, or [] with a finding.

        Layout containers go silently (Odoo's header and footer apply). A
        missing container, a cycle, the depth limit and the per-render
        include budget each leave a php_removed line. The stored sizes of
        the containers inlined so far add up, and PageError is raised
        once they pass MAX_TEXT, before the next one is parsed.
        """
        ref = node.get("ref") if isinstance(node.get("ref"), str) else ""
        if self.site.containers.get(ref) in _LAYOUT_ROLES:
            return []
        container = self.site.page(ref) if valid_ref(ref) else None
        why = ""
        if container is None:
            why = "missing container"
        elif container.analysis_status not in _USABLE_CONTAINERS:
            why = "container not imported"
        elif ref in stack:
            why = "include cycle"
        elif depth >= MAX_INCLUDE_DEPTH:
            why = "include deeper than %d levels" % MAX_INCLUDE_DEPTH
        elif self.includes >= MAX_INCLUDES:
            why = "more than %d includes" % MAX_INCLUDES
        if why:
            self._removed("includeContainer %s: %s" % (ref, why), node)
            return []
        self.includes += 1
        self.inlined_bytes += len(container.body_html.encode("utf-8"))
        if self.inlined_bytes > MAX_TEXT:
            raise PageError(
                self.page.ref,
                "page larger than 10 MB once containers are inlined",
            )
        frag = self.load(
            container.body_html, container, depth + 1, stack + (ref,)
        )
        if ref not in self.inlined:
            self.inlined.add(ref)
            self.findings.append(
                finding(
                    "container_inlined",
                    page_ref=self.page.ref,
                    container=ref,
                    ref=self.page.ref,
                )
            )
        return [frag.text or ""] + list(frag)

    def contact_forms(self, root):
        """Forms that post to the page itself, which its handler serves."""
        if not self.page.has_contact_handler:
            return []
        ref = self.page.ref
        own = ("", ref + ".php", "/" + ref + ".php")
        found = []
        for form in root.iter("form"):
            method = (form.get("method") or "get").strip().lower()
            action = (form.get("action") or "").strip()
            if action.startswith(PAGE):
                mine = split_token(action)[0] == ref
            else:
                mine = re.split(r"[?#]", action, maxsplit=1)[0] in own
            if method == "post" and mine:
                found.append(form)
        return found

    def _checked(self, url):
        """A resolver URL made safe, or None.

        Blanks and non-ASCII characters are percent-encoded first; the
        result must be a site path that holds nothing like a marker.
        """
        if not isinstance(url, str):
            return None
        try:
            url = _TO_ENCODE.sub(lambda m: urllib.parse.quote(m.group()), url)
        except UnicodeEncodeError:
            return None
        if not local_path(url) or php.looks_like_marker(url):
            return None
        return url

    def logo_url(self):
        return "/web/image/website/%d/logo" % _int(self.resolver.website_id())

    def resolve_value(self, value):
        """Final URL of a page, media or logo token; None when invalid."""
        if value.startswith(PAGE):
            ref, suffix = split_token(value)
            if not valid_ref(ref) or php.looks_like_marker(ref + suffix):
                return None
            if not _TOKEN_SUFFIX.fullmatch(suffix):
                suffix = ""
            url = self._checked(self.resolver.page_url(ref))
            if url is None:
                url = "/%s.php" % ref
                self.findings.append(
                    finding(
                        "unresolved_link",
                        page_ref=self.page.ref,
                        url=url,
                        ref=self.page.ref,
                    )
                )
            return url + suffix
        if value.startswith(MEDIA):
            # The HTML serialiser percent-encodes src and href; a relpath
            # never holds "%", so decoding is unambiguous.
            relpath = urllib.parse.unquote(split_token(value)[0])
            if not valid_relpath(relpath, self.key) or php.looks_like_marker(
                relpath
            ):
                return None
            url = self._checked(self.resolver.media_url(relpath))
            if url is None:
                url = "/medias/" + urllib.parse.quote(relpath, safe="/()+,")
                self.findings.append(
                    finding(
                        "missing_media",
                        page_ref=self.page.ref,
                        url=url,
                        ref=self.page.ref,
                    )
                )
            return url
        if value.startswith(LOGO):
            return self.logo_url()
        return value

    def _resolve_srcset(self, value):
        out = []
        for url, descriptor in srcset_candidates(value):
            url = self.resolve_value(url)
            if url is not None:
                out.append(" ".join(filter(None, [url, descriptor])))
        return ", ".join(out)

    def _resolve_style(self, value):
        def repl(match):
            url = self.resolve_value(match.group(1))
            return "url('%s')" % url if url is not None else "none"

        return _TOKEN_URL.sub(repl, value)

    def resolve_tokens(self, root):
        """Replace every token by its URL, before the script policy runs.

        url_allowed() refuses the token schemes, so the policy would strip
        an unresolved token. A logo of a live page is noted in self.logos
        and becomes a t-att- expression after the policy.
        """
        for el in root.iter(etree.Element):
            for name in list(el.attrib):
                value = el.attrib[name]
                if name == "srcset":
                    el.set(name, self._resolve_srcset(value))
                elif name == "style":
                    el.set(name, self._resolve_style(value))
                elif value.startswith((PAGE, MEDIA, LOGO)):
                    url = self.resolve_value(value)
                    if url is None:
                        self.unsafe.append("invalid %s token" % name)
                        del el.attrib[name]
                        continue
                    el.set(name, url)
                    if value.startswith(LOGO) and self.live:
                        self.logos.append((el, name, url))
                if _ANY_TOKEN.search(el.get(name) or ""):
                    self.unsafe.append("unresolved %s token" % name)
                    del el.attrib[name]
        _report(
            self.findings, self.page.ref, "unsafe_markup_removed", self.unsafe
        )

    def stash_markers(self, root):
        """Put the rendered form of each marker attribute into the tree.

        The element rules then judge the value a visitor would get.
        """
        for entry in self.attrs:
            el, name, value = entry[:3]
            if _attached(el, root) and name not in el.attrib:
                entry[3] = self._policy_value(el, value)
                el.set(name, entry[3])

    def restore_markers(self, root):
        """Take the rendered forms out again; keep what the rules kept.

        An attribute the rules removed or changed loses its markers, so no
        half-checked value stays.
        """
        for entry in self.attrs:
            el, name, _value, probe = entry
            kept = _attached(el, root) and el.get(name) == probe
            if name in el.attrib and probe is not None:
                del el.attrib[name]
            if not kept:
                entry[3] = None

    def _policy_value(self, el, value):
        parts = _TOKEN_SPLIT.split(value)
        out = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                out.append(part)
                continue
            node = self._token_node(part)
            if node.get("kind") == "map":
                return _MAP_PROBE if self.live else self._map_frozen()
            out.append(self._attr_value(node, el)[1])
        return "".join(out)

    def _map_frozen(self):
        return _xml_text(self.company.get("map_url")) + "&output=embed"

    # Expansion phase.

    def expand(self, root, forms):
        self._replace_forms(root, forms)
        if not self.live:
            for loop in list(root.iter(php.LOOP_TAG)):
                self._removed("blog loop", self._node(loop), _size(loop))
                _drop(loop)
        self._expand_attributes(root)
        for marker in list(root.iter(php.MARKER_TAG)):
            if _attached(marker, root):
                items = self._marker_items(marker, self._node(marker))
                _replace(marker, items)
        for el, name, url in self.logos:
            if _attached(el, root) and el.get(name) == url:
                del el.attrib[name]
                el.set("t-att-%s" % name, _LOGO_EXPR)
        for loop in list(root.iter(php.LOOP_TAG)):
            self._loop(loop)
        self._drop_foreign_raw(root)
        self._sweep(root)

    def _drop_foreign_raw(self, root):
        """Remove script and style elements inside svg or math.

        There they are not raw text for a browser, so markup in their text
        would become live; a payload or a container can put one there.
        """
        unsafe = []
        for el in list(root.iter("script", "style")):
            if _in_foreign_content(el):
                unsafe.append("<%s> in svg or math" % el.tag)
                _drop(el)
        _report(self.findings, self.page.ref, "unsafe_markup_removed", unsafe)

    def _loop(self, loop):
        node = self._node(loop)
        if node.get("kind") != "blog_loop":
            self._removed("loop", node, _size(loop))
            _drop(loop)
            return
        loop.attrib.clear()
        loop.tag = "t"
        loop.set(
            "t-foreach",
            _LOOP_EXPR
            % (_int(self.resolver.blog_id()), _int(node.get("limit"), 1)),
        )
        loop.set("t-as", "blog")

    def _sweep(self, root):
        """Remove leftover markers and marker-like text in attributes."""
        for el in list(root.iter(php.MARKER_TAG, php.LOOP_TAG)):
            _drop(el)
        for el in root.iter(etree.Element):
            for name, value in list(el.attrib.items()):
                if not name.startswith("t-") and php.ATTR_TOKEN_RE.search(
                    value
                ):
                    el.set(name, php.ATTR_TOKEN_RE.sub("", value))

    def _in_loop(self, el):
        return any(
            up.tag == php.LOOP_TAG for up in [el] + list(el.iterancestors())
        )

    def _company_field(self, node):
        field = node.get("field")
        return field if field in _COMPANY_FIELDS else ""

    def _marker_items(self, marker, node):
        """Strings and elements that replace one text marker."""
        build = getattr(self, "_items_%s" % node.get("kind"), None)
        if node.get("kind") not in _ELEMENT_KINDS or build is None:
            return []
        return build(marker, node)

    def _items_company(self, marker, node):
        field = self._company_field(node)
        if not field:
            return []
        if self.live:
            return [self._el(marker, "t", {"t-out": "res_company.%s" % field})]
        return [_xml_text(self.company.get(field))]

    def _items_address(self, marker, node):
        if self.live:
            attrib = {
                "t-field": "res_company.partner_id",
                "t-options": _ADDRESS_OPTIONS,
            }
            return [self._el(marker, "span", attrib)]
        items = []
        lines = _xml_text(self.company.get("address")).splitlines()
        for i, line in enumerate(lines):
            if i:
                items.append(self._el(marker, "br", {}))
            items.append(line)
        return items

    def _items_title(self, marker, node):
        if self.live:
            return [self._el(marker, "t", {"t-out": "main_object.name"})]
        return [_xml_text(self.page.title)]

    def _items_text(self, marker, node):
        """Untrusted text: parsed, then cleaned; never parsed after that."""
        frag = clean_fragment(
            _xml_text(node.get("value")),
            self.page.ref,
            self.findings,
            keep_scripts=False,
        )
        return [frag.text or ""] + list(frag)

    def _items_social(self, marker, node):
        if self.live:
            call = "%s.social_links" % TEMPLATE_MODULE
            return [self._el(marker, "t", {"t-call": call})]
        self._removed("social links loop", node)
        return []

    def _items_blog_list(self, marker, node):
        if not self.live:
            self._removed("blog list", node)
            return []
        call = self._el(
            marker, "t", {"t-call": "%s.blog_post_list" % TEMPLATE_MODULE}
        )
        for name, value in (
            ("blog_id", _int(self.resolver.blog_id())),
            ("blog_limit", _int(node.get("limit"), 1)),
        ):
            call.append(
                self._el(marker, "t", {"t-set": name, "t-value": str(value)})
            )
        return [call]

    def _items_blog_field(self, marker, node):
        field = node.get("field")
        if not self.live or not self._in_loop(marker):
            return []
        if field == "date":
            attrib = {
                "t-field": "blog.post_date",
                "t-options": "{'widget': 'date'}",
            }
            return [self._el(marker, "span", attrib)]
        if field in _BLOG_EXPR:
            return [self._el(marker, "t", {"t-out": _BLOG_EXPR[field]})]
        return []

    def _attr_value(self, node, el):
        """(QWeb expression or None, frozen text) of an attribute marker."""
        kind = node.get("kind")
        if kind == "company":
            field = self._company_field(node)
            if field:
                return (
                    "res_company.%s" % field,
                    _xml_text(self.company.get(field)),
                )
        if kind == "title":
            return "main_object.name", _xml_text(self.page.title)
        if kind == "logo":
            return _LOGO_EXPR, self.logo_url()
        if kind == "text":
            return None, _plain(node.get("value"))
        if kind == "blog_field" and self.live and self._in_loop(el):
            field = node.get("field")
            if field in _BLOG_EXPR:
                return _BLOG_EXPR[field], ""
        return None, ""

    def _expand_attributes(self, root):
        """Expand the marker attributes of self.attrs, never the tree's."""
        doomed = []
        for el, name, value, probe in self.attrs:
            if not _attached(el, root):
                continue
            parts = _TOKEN_SPLIT.split(value)
            nodes = [self._token_node(p) for p in parts[1::2]]
            kinds = {n.get("kind") for n in nodes}
            if "drop_element" in kinds:
                doomed.append(el)
                continue
            if probe is None:
                continue
            if "search_value" in kinds:
                self._search(el, name, nodes, doomed)
                continue
            if not _QWEB_ATTR_NAME.fullmatch(name):
                continue
            if "map" in kinds:
                if self.live:
                    el.set("t-att-%s" % name, _MAP_EXPR)
                else:
                    el.set(name, probe)
                continue
            self._attribute_expression(el, name, parts, nodes, probe)
        for el in doomed:
            if _attached(el, root) and el is not root:
                _drop(el)

    def _search(self, el, name, nodes, doomed):
        """R2: the search input reads the Odoo search parameter."""
        form = next(el.iterancestors("form"), None)
        if not self.live:
            gone = el if form is None else form
            self._removed("search form", nodes[0], _size(gone))
            doomed.append(gone)
            return
        if name != "value":
            return
        el.set("name", "search")
        el.set("t-att-value", "request.params.get('search', '')")
        if form is not None:
            form.set("action", "/website/search")
            form.set("method", "get")
        if not self.search_reported:
            self.search_reported = True
            self.findings.append(
                finding(
                    "search_rewired", page_ref=self.page.ref, ref=self.page.ref
                )
            )

    def _attribute_expression(self, el, name, parts, nodes, probe):
        """t-att-<name> from repr() literals and fixed expressions.

        Without a live expression the attribute gets probe, the value the
        element rules accepted. The ".php" that follows a blog URL marker
        is dropped: website_url is already the post's URL. A live value the
        rules cannot judge in advance is refused (see _dynamic_refusal);
        an iframe refused its src goes whole, since it would load nothing.
        """
        pieces, frozen, dynamic, skip_php = [], [], False, False
        for i, part in enumerate(parts):
            if i % 2 == 0:
                if skip_php and part.startswith(".php"):
                    part = part[4:]
                skip_php = False
                if part:
                    pieces.append(repr(part))
                    frozen.append(part)
                continue
            node = nodes[i // 2]
            expr, text = self._attr_value(node, el)
            skip_php = node.get("kind") == "blog_field" and (
                node.get("field") == "url"
            )
            if expr and self.live:
                pieces.append("(%s or '')" % expr)
                dynamic = True
            elif text:
                pieces.append(repr(text))
            frozen.append(text)
        if not dynamic:
            el.set(name, probe)
            return
        guard = _company_guard(name, parts, nodes)
        why = _dynamic_refusal(el.tag, name, parts, nodes, bool(guard))
        if why:
            _report(
                self.findings,
                self.page.ref,
                "unsafe_markup_removed",
                ["dynamic %s %s: %s" % (el.tag, name, why)],
            )
            if el.tag == "iframe" and name == "src":
                _drop(el)
            return
        if guard:
            condition, value = _GUARDED_COMPANY[guard]
            pieces[0] = value
            expr = "(%s) if %s else ''" % (" + ".join(pieces), condition)
        else:
            expr = " + ".join(pieces)
        el.set("t-att-%s" % name, expr)

    def _replace_forms(self, root, forms):
        """R3: each own POST form becomes the module's contact form.

        A post keeps no form: it is removed with a php_removed line.
        """
        replaced = False
        for form in forms:
            if not _attached(form, root):
                continue
            if not self.live:
                line = {"line": form.sourceline or 1}
                self._removed("contact form", line, _size(form))
                _drop(form)
                continue
            self.forms += 1
            form_id = "%s%d" % (RESERVED_ID_PREFIX, self.forms)
            call = self._el(
                form, "t", {"t-call": "%s.contact_form" % TEMPLATE_MODULE}
            )
            call.append(
                self._el(
                    form, "t", {"t-set": "form_id", "t-value": repr(form_id)}
                )
            )
            self.spans.append(
                self._el(
                    form,
                    "span",
                    {
                        "class": "hidden",
                        "data-for": form_id,
                        "t-att-data-values": "{'email_to': res_company.email}",
                    },
                )
            )
            _replace(form, [call])
            replaced = True
        if replaced:
            self.findings.append(
                finding(
                    "form_replaced", page_ref=self.page.ref, ref=self.page.ref
                )
            )


def render_body(page, site, resolver, company, opts, findings, target):
    """Rendered body of a page ('page', live QWeb) or a post ('post').

    Returns the <div> root and the data-for spans that go outside #wrap.
    The body, once its containers are inlined, must stay within MAX_TEXT
    bytes: a larger one raises PageError.
    """
    state = _Render(site, page, resolver, company, opts, findings, target)
    root = state.load(page.body_html, page, 0, (page.ref,))
    if _size(root) > MAX_TEXT:
        raise PageError(
            page.ref, "page larger than 10 MB once containers are inlined"
        )
    forms = state.contact_forms(root)
    state.resolve_tokens(root)
    state.stash_markers(root)
    _render_policy(root, page.ref, findings, opts.keep_scripts)
    state.restore_markers(root)
    state.expand(root, forms)
    return root, state.spans


_INERT_ATTRS = frozenset("class title alt value placeholder".split())
# Kinds whose live value comes from source text (a page or post title,
# a post's description or author), not from Odoo or a fixed template.
_SOURCE_VALUES = frozenset(
    ("title", "blog_title", "blog_description", "blog_author", "blog_date")
)


def _company_guard(name, parts, nodes):
    """Field whose guarded form a URL attribute takes; '' when none.

    It applies when the attribute opens on a company website, email or
    phone value: that value then decides the scheme of the whole URL.
    """
    if name not in URL_ATTRS or parts[0] or not nodes:
        return ""
    node = nodes[0]
    field = node.get("field")
    if node.get("kind") == "company" and field in _GUARDED_COMPANY:
        return field
    return ""


def _dynamic_refusal(tag, name, parts, nodes, guarded=False):
    """Why a live t-att- value must not be bound there; '' when it may.

    No live value binds to an SVG animation element, which can set any
    attribute of its target. A form action, a form control name and an
    iframe src decide where data goes or what loads: no live value is
    bound to them either. A live value that comes from source text or
    from the company binds only to an inert attribute (class, title, alt,
    value, placeholder, aria-*) or to a URL attribute after a literal
    that fixes the scheme or path; any other attribute (an id, a style, a
    srcset, a data-*) could change what the element does. For a company
    value that literal must be mailto:, tel:, a path or https://<host>/,
    unless guarded is True: the attribute then opens on a guarded company
    value that yields a safe scheme or nothing. Odoo-built URLs keep the
    first two rules only.
    """
    if tag.lower() in _ANIMATIONS:
        return "live value on an animation"
    if (
        (tag == "form" and name == "action")
        or (tag in _FORM_CONTROLS and name == "name")
        or (tag == "iframe" and name == "src")
    ):
        return "decides where data goes"
    kinds = set()
    for node in nodes:
        kind = node.get("kind")
        if kind == "blog_field":
            kind = "blog_%s" % node.get("field")
        kinds.add(kind)
    company = "company" in kinds
    if not (kinds & _SOURCE_VALUES or company):
        return ""
    if name in _INERT_ATTRS or name.startswith("aria-"):
        return ""
    if name in URL_ATTRS or (name == "srcset" and not company):
        if guarded:
            return ""
        if company and not _COMPANY_PREFIX.match(parts[0]):
            return "company value without a fixed scheme"
        if _SAFE_PREFIX.match(parts[0]):
            return ""
        return "source text without a fixed scheme"
    return "live value in an active attribute"


def _render_policy(root, page_ref, findings, keep_scripts):
    """Script policy plus the element rules, whatever keep_scripts says.

    apply_script_policy() alone skips the element pass when scripts are
    kept; at render the pass always runs, on the rendered marker values.
    """
    apply_script_policy(root, page_ref, findings, keep_scripts)
    if not keep_scripts:
        return
    unsafe, forms = [], []
    _scrub(root, True, unsafe, forms, [])
    _run_cleaner(root, True, unsafe)
    _report(findings, page_ref, "unsafe_markup_removed", unsafe)
    _report(findings, page_ref, "form_removed", forms)


def _parse_head(source):
    text = close_raw_elements(_XML_BAD_CHARS.sub("", source or ""))
    if not text.strip():
        return []
    doc = lhtml.document_fromstring(
        "<html><head>%s</head><body></body></html>" % text
    )
    items = list(doc.head) + list(doc.body)
    for el in items:
        _strip_qweb(el)
        for name in list(el.attrib):
            lname = name.lower()
            if lname.startswith(("t-", "data-oe-")) or lname == "groups":
                del el.attrib[name]
    return [el for el in items if isinstance(el.tag, str) and el.tag != "t"]


def _head_children(source, owner, site, resolver, opts, findings):
    """Head elements with tokens resolved, re-cleaned, scripts policed."""
    state = _Render(site, owner, resolver, {}, opts, findings, "post")
    holder = lhtml.Element("div")
    holder.extend(_parse_head(source))
    state.resolve_tokens(holder)
    text = "".join(lhtml.tostring(el, encoding="unicode") for el in holder)
    kept = _parse_head(clean_head(text, owner.ref, findings, opts.css_hosts))
    scripts = [el for el in kept if el.tag == "script"]
    if scripts:
        code = "script_kept" if opts.keep_scripts else "script_removed"
        findings.append(
            finding(
                code,
                page_ref=owner.ref,
                ref=owner.ref,
                what="script element",
            )
        )
        if not opts.keep_scripts:
            kept = [el for el in kept if el.tag != "script"]
    return kept


def _shape(root):
    return [
        (el.tag if isinstance(el.tag, str) else "#", tuple(sorted(el.attrib)))
        for el in root.iter()
    ]


def finalize(root, page_ref):
    """Escape text once more, serialise, then re-parse strictly.

    QWeb writes the text of an arch as it is, so a decoded "<" in a text
    node would become markup; the extra escape keeps it text. Script and
    style text stays byte-exact. The re-parse must give back the same
    elements and attribute names: a reference or a namespace that turned
    into a new element or attribute fails the page. The 10 MB text limit
    applies to the escaped text, before serialisation.
    """
    for el in root.iter():
        if not isinstance(el.tag, str):
            raise PageError(page_ref, "non-element node in the arch")
        if el.text and el.tag.lower() not in _RAW:
            el.text = str(markupsafe.escape(el.text))
        if el.tail:
            el.tail = str(markupsafe.escape(el.tail))
        if len(el.text or "") > MAX_TEXT or len(el.tail or "") > MAX_TEXT:
            raise PageError(page_ref, "text node larger than 10 MB")
    if _depth(root) > MAX_DEPTH:
        raise PageError(page_ref, "arch deeper than %d levels" % MAX_DEPTH)
    text = etree.tostring(root, encoding="unicode", method="xml")
    try:
        again = etree.fromstring(text, safe_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise PageError(page_ref, "invalid arch: %s" % exc) from exc
    if _shape(again) != _shape(root):
        raise PageError(page_ref, "arch changed when parsed again")
    return text


def page_arch(page, site, resolver, company, opts, findings):
    """QWeb arch of a website.page, built with the lxml element API."""
    name = view_key(site.source_key, page.ref)
    body, spans = render_body(
        page, site, resolver, company, opts, findings, "page"
    )
    view = etree.Element("t", {"t-name": name})
    layout = etree.SubElement(view, "t", {"t-call": "website.layout"})
    etree.SubElement(
        layout,
        "t",
        {
            "t-set": "body_classname",
            "t-value": repr("bodywebsite bodywebpage-%s" % page.ref),
        },
    )
    head = etree.SubElement(layout, "t", {"t-set": "head"})
    etree.SubElement(head, "t", {"t-call": head_key(site.source_key)})
    head.extend(
        _head_children(page.head_html, page, site, resolver, opts, findings)
    )
    layout.extend(spans)
    wrap = etree.SubElement(
        layout, "div", {"id": "wrap", "class": "oe_structure"}
    )
    wrap.text = body.text
    wrap.extend(list(body))
    return finalize(view, page.ref)


def post_content(page, site, resolver, company, opts, findings):
    """Frozen HTML of a blog.post: its content field is never QWeb."""
    body, _spans = render_body(
        page, site, resolver, company, opts, findings, "post"
    )
    if _depth(body) > MAX_DEPTH:
        raise PageError(page.ref, "markup deeper than %d levels" % MAX_DEPTH)
    for el in body.iter():
        if len(el.text or "") > MAX_TEXT or len(el.tail or "") > MAX_TEXT:
            raise PageError(page.ref, "text node larger than 10 MB")
    if opts.style_blog_posts:
        body.set("class", "bodywebsite")
        return lhtml.tostring(body, encoding="unicode")
    return fragment_html(body)


class _HeadOwner:
    """Stand-in page for the site-wide htmlheader.html."""

    ref = "htmlheader.html"
    title = ""
    has_contact_handler = False
    qweb_nodes = {}


def head_arch(site, css_url, js_url, resolver, opts, findings):
    """Site-specific head view called by every imported page.

    css_url and js_url must be site paths; the script is referenced only
    with keep_scripts.
    """
    for url in (css_url, js_url):
        if url and not local_path(url):
            raise ValueError("head asset URL must be a site path")
    view = etree.Element("t", {"t-name": head_key(site.source_key)})
    if css_url:
        etree.SubElement(view, "link", {"rel": "stylesheet", "href": css_url})
    if js_url and opts.keep_scripts:
        etree.SubElement(view, "script", {"defer": "defer", "src": js_url})
    owner = _HeadOwner()
    view.extend(
        _head_children(site.head_assets, owner, site, resolver, opts, findings)
    )
    return finalize(view, owner.ref)
