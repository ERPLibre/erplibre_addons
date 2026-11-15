# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Layout containers of a zip site and its header menu.

A container is a layout container by usage, never by its type: it is
included as the first or last top-level output block of at least half of
the importable main-language pages that include anything.

Every label and target that leaves this module is safe as a plain field
value: a label is plain text, a target is a page token with a valid ref or
an http(s) or root-relative URL.
"""

import collections
import re
import unicodedata
import urllib.parse

from lxml import etree
from lxml import html as lhtml

from .messages import finding
from .model import MenuItem, valid_ref
from .php import MARKER_TAG
from .urls import PAGE, split_token

MAX_MENU_DEPTH = 2
MAX_MENU_ITEMS = 500
MAX_LABEL = 200
MAX_HTML_DEPTH = 250
MAX_TARGET = 2048
_MAX_MARKER_VALUE = 4096
_DROPPED_CATEGORIES = frozenset(("Cc", "Cf", "Cs", "Co", "Cn"))
_SKIPPED_TAGS = frozenset(("script", "style", "template"))
_SUFFIX_OK = re.compile(r"[?#][A-Za-z0-9_\-.~%=&/;:@+,!*()?#\[\]$]*")
_BAD_URL_CHARS = frozenset("<>\"'\\` ")


def detect_layout(pages):
    """Map container ref to header or footer, by how pages include it."""
    candidates = [
        p for p in pages if p.analysis_status == "import" and p.includes
    ]
    if not candidates:
        return {}
    first, last, anywhere = (
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    for page in candidates:
        head, tail = (list(page.edge_includes) + ["", ""])[:2]
        if head:
            first[head] += 1
        if tail:
            last[tail] += 1
        for ref in {head, tail} - {""}:
            anywhere[ref] += 1
    roles = {}
    for ref, count in anywhere.items():
        if count * 2 >= len(candidates):
            roles[ref] = "header" if first[ref] >= last[ref] else "footer"
    return roles


def _clean_text(chunks):
    """Plain text of chunks: control characters gone, blanks collapsed."""
    text = "".join(chunks)
    text = "".join(
        " " if char.isspace() else char
        for char in text
        if char.isspace()
        or unicodedata.category(char) not in _DROPPED_CATEGORIES
    )
    return " ".join(text.split())[:MAX_LABEL].rstrip()


def _marker_text(node):
    """Plain text of a text marker payload; anything else gives ''."""
    value = node.get("value") if isinstance(node, dict) else None
    if node and node.get("kind") != "text":
        return ""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        fragment = lhtml.fragment_fromstring(
            value[:_MAX_MARKER_VALUE], create_parent="span"
        )
    except (etree.LxmlError, ValueError):
        return ""
    return _element_text(fragment, {})


def _element_text(root, nodes):
    """Text of an element, iteratively; markers give their text value.

    Script, style and template contents and comments never count. The
    walk stops once enough chunks are gathered for a bounded label.
    """
    chunks = []
    skip = 0
    for event, el in etree.iterwalk(root, events=("start", "end")):
        is_tag = isinstance(el.tag, str)
        if event == "start":
            if skip:
                skip += 1
            elif is_tag and (el.tag == MARKER_TAG or el.tag in _SKIPPED_TAGS):
                skip = 1
                if el.tag == MARKER_TAG:
                    chunks.append(_marker_text(nodes.get(el.get("id"))))
            elif is_tag and el.text:
                chunks.append(el.text)
        else:
            if skip:
                skip -= 1
                if skip:
                    continue
            if el is not root and el.tail:
                chunks.append(el.tail)
        if len(chunks) > 4 * MAX_LABEL:
            break
    return _clean_text(chunks)


def _safe_suffix(suffix):
    return suffix if _SUFFIX_OK.fullmatch(suffix) else ""


def _safe_target(href):
    """A dolibarr-page: token, an http(s) URL or a /path; else None.

    Blanks, control and format characters (which can hide or reorder
    what the target shows), a user part and an unreadable port refuse
    the target.
    """
    href = (href or "").strip()
    if not href or len(href) > MAX_TARGET:
        return None
    if any(
        c.isspace() or unicodedata.category(c) in ("Cc", "Cf") for c in href
    ):
        return None
    if href.startswith(PAGE):
        ref, suffix = split_token(href)
        return PAGE + ref + _safe_suffix(suffix) if valid_ref(ref) else None
    if any(c in _BAD_URL_CHARS for c in href):
        return None
    if href.startswith("/"):
        return href if not href.startswith("//") else None
    try:
        parts = urllib.parse.urlsplit(href)
        host = parts.hostname
        parts.port  # reading an invalid port raises ValueError
    except ValueError:
        return None
    if "@" in parts.netloc:
        return None
    if parts.scheme in ("http", "https") and host:
        return href
    return None


def _count_links(elements):
    """Internal links inside each element, in one pass over the tree."""
    counts = {}
    for el in reversed(elements):
        total = counts.get(el, 0)
        if el.tag == "a" and (el.get("href") or "").startswith(PAGE):
            total += 1
        counts[el] = total
        parent = el.getparent()
        if parent is not None:
            counts[parent] = counts.get(parent, 0) + total
    return counts


def _own_anchor(li):
    """First link of a list entry outside its sub-lists, in document order."""
    stack = list(reversed(li))
    while stack:
        el = stack.pop()
        if not isinstance(el.tag, str) or el.tag in ("ul", "ol", "li"):
            continue
        if el.tag == "a":
            return el
        stack.extend(reversed(el))
    return None


class _Walk:
    """State shared by one menu extraction."""

    def __init__(self, nodes):
        self.nodes = nodes
        self.findings = []
        self.count = 0
        self.capped = False

    def item(self, anchor):
        """A MenuItem for a link, or None when it must be left out."""
        target = _safe_target(anchor.get("href"))
        if target is None:
            return None
        label = _element_text(anchor, self.nodes) or _clean_text(
            [anchor.get("title") or ""]
        )
        if not label:
            return None
        if self.count >= MAX_MENU_ITEMS:
            self.capped = True
            return None
        self.count += 1
        return MenuItem(
            label=label,
            target=target,
            new_window=anchor.get("target") == "_blank",
        )


def _items(ul, walk, level):
    """Menu entries of one <ul>; below the second level, entries move up.

    A third-level entry, or a deeper one, becomes a sibling of its
    second-level ancestor, right after it, with one menu_flattened
    finding. An entry without a usable link gives its sub-entries to its
    own level.
    """
    items = []
    for li in ul.iterchildren("li"):
        if walk.capped:
            break
        anchor = _own_anchor(li)
        sub = next(li.iterchildren("ul"), None)
        item = walk.item(anchor) if anchor is not None else None
        children = _items(sub, walk, level + 1) if sub is not None else []
        if item is None:
            items.extend(children)
            continue
        if level + 1 < MAX_MENU_DEPTH:
            item.children = children
            items.append(item)
        else:
            items.append(item)
            for child in children:
                if level + 1 == MAX_MENU_DEPTH:
                    walk.findings.append(
                        finding("menu_flattened", label=child.label)
                    )
                items.append(child)
    return items


def _flat_items(nav, walk):
    items = []
    for anchor in nav.iter("a"):
        if walk.capped:
            break
        item = walk.item(anchor)
        if item is not None:
            items.append(item)
    return items


def _depth(root):
    deepest, stack = 0, [(root, 1)]
    while stack:
        el, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in el)
    return deepest


def _menu_root(header):
    """Element tree of the header, or a page_error finding."""
    try:
        root = lhtml.fragment_fromstring(header.body_html, create_parent="div")
        deep = _depth(root) > MAX_HTML_DEPTH
    except (etree.LxmlError, ValueError, RecursionError):
        deep = True
        root = None
    if deep:
        return None, finding(
            "page_error",
            page_ref=header.ref,
            ref=header.ref,
            reason="header markup unreadable or nested too deeply",
        )
    return root, None


def extract_menu(header):
    """Menu items of a header container, at most two levels deep.

    Returns (items, findings). Never raises on hostile markup: a header
    that cannot be read gives no items and a page_error finding.
    """
    if not (header.body_html or "").strip():
        return [], []
    root, error = _menu_root(header)
    if error:
        return [], [error]
    elements = list(root.iter(etree.Element))
    counts = _count_links(elements)
    candidates = [
        el for el in elements if el.tag in ("nav", "ul") and counts[el]
    ]
    if not candidates:
        return [], []
    best = max(candidates, key=counts.__getitem__)
    walk = _Walk(header.qweb_nodes)
    if best.tag == "nav":
        lists = [ul for ul in best.iter("ul") if counts[ul]]
        if lists:
            best = max(lists, key=counts.__getitem__)
            items = _items(best, walk, 0)
        else:
            items = _flat_items(best, walk)
    else:
        items = _items(best, walk, 0)
    if walk.capped:
        walk.findings.append(finding("menu_capped", limit=MAX_MENU_ITEMS))
    return items, walk.findings
