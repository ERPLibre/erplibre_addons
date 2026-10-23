# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Ordered table of known Dolibarr PHP idioms and their decisions.

classify() normalises a block, splits it into top-level statements, drops
the silent ones, and matches the single remaining statement against the
table; the first match wins. A blog loop is recognised on its last two or
three statements. Payloads are fixed dicts. The include ref (a ref
alphabet) and the blog limit (a bounded integer) are validated. Three
values are UNTRUSTED source text and reach the payload raw: text.value
(the O1 literal and the T1 translation), and seo_title (the S2 literal
or translation); html2arch must escape or clean them when it expands
them. Silent and drop idioms match whole statements only: no trailing
code, no nested calls.
"""

import dataclasses
import re

from . import php


def _rx(pattern):
    """Compile ASCII-only: \\w and \\d never match non-ASCII source text."""
    return re.compile(pattern, re.ASCII)


ECHO = r"^(?:echo|print) "
COMPANY_FIELDS = {
    "name": "name",
    "email": "email",
    "phone": "phone",
    "url": "website",
    "zip": "zip",
    "town": "city",
    "address": "street",
}
_COMPANY_ID = {"name": "C1", "email": "C2", "phone": "C3"}
_RESERVED_VARS = frozenset(
    "mysoc websitepage website weblangs langs socInfo conf db user".split()
)
_ARGS = r"\((?:[^()]|array\([^()]*\))*\)"
_TERM = r"(?:'[^'()]*'|\$\w+(?:->\w+)?)"
_BODY = r"\{ ?(?:(?:echo|print) " + _TERM + r"(?: ?\. ?" + _TERM + r")*; ?)*\}"
_SILENT = (
    ("T3", _rx(r"^\$(?:weblangs|langs|emaillang)->\w+" + _ARGS + "$")),
    (
        "L5",
        _rx(
            r"^(?:include|include_once|require|require_once) (?:"
            r"DOL_DATA_ROOT\.'/website/'\.\$websitekey\."
            r"'/containers/_library_lib\.php'"
            r"|'[A-Za-z0-9_/.-]*_library_lib\.php')$"
        ),
    ),
    ("L5", _rx(r"^setSessionLang\(\)$")),
    ("L5", _rx(r"^\$\w+ = getSocInfo\(\)$")),
    (
        "P2",
        _rx(
            ECHO + r"\(\$websitepage->ref == '[A-Za-z0-9_-]+'"
            r" \? ' ?active' : ''\)$"
        ),
    ),
    ("S1", _rx(ECHO + r"getStructuredData\([^()]*\)$")),
)
_FETCH = _rx(
    r"^\$(?P<arr>\w+) = \$websitepage->fetchAll\(\$website->id, 'DESC',"
    r" 'date_creation', (?P<limit>\$\w+|[0-9]{1,6}), 0,"
    r" array\('type_container' ?=> ?'blogpost'"
    r"(?:, ?'[a-z_]+' ?=> ?(?:[0-9]+|'[A-Za-z0-9_]*'))*\)\)$"
)
_FOREACH_OPEN = _rx(r"^foreach ?\(\$(?P<arr>\w+) as \$(?P<var>\w+)\) ?\{$")
_FOREACH_FULL = _rx(
    r"^foreach ?\(\$(?P<arr>\w+) as \$(?P<var>\w+)\) ?" + _BODY + "$"
)
_ASSIGN = _rx(r"^\$(?P<var>\w+) = (?P<value>[0-9]{1,6}|''|new User\(\$db\))$")


@dataclasses.dataclass
class IdiomContext:
    site_key: str
    main_lang: str
    resolver: object = None
    table: object = None


def split_statements(code):
    """Split on ';' at depth zero of (), [] and {}, outside strings."""
    parts, buf, depth, quote, i = [], [], 0, "", 0
    while i < len(code):
        char = code[i]
        if quote:
            buf.append(char)
            if char == "\\" and i + 1 < len(code):
                buf.append(code[i + 1])
                i += 2
                continue
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            buf.append(char)
        elif char in "([{":
            depth += 1
            buf.append(char)
        elif char in ")]}":
            depth -= 1
            buf.append(char)
        elif char == ";" and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
        i += 1
    parts.append("".join(buf).strip())
    return [part for part in parts if part]


def _text(value, key="", exact=True):
    return {"kind": "text", "value": value, "key": key, "exact": exact}


def _company(match, ctx):
    field = match.group("f")
    if field not in COMPANY_FIELDS:
        return None
    return php.Decision(
        _COMPANY_ID.get(field, "C1"),
        node={"kind": "company", "field": COMPANY_FIELDS[field]},
    )


def _socinfo(match, ctx):
    field = match.group("f")
    if field not in COMPANY_FIELDS:
        return None
    return php.Decision(
        "C11", node={"kind": "company", "field": COMPANY_FIELDS[field]}
    )


def _trans(match, ctx):
    key = match.group("key")
    value, exact = ctx.resolver.trans(key, ctx.table)
    return php.Decision("T1", node=_text(value, key, exact), exact=exact)


def _seo(match, ctx):
    if match.group("key"):
        value, exact = ctx.resolver.trans(match.group("key"), ctx.table)
    else:
        value, exact = match.group("lit"), True
    return php.Decision("S2", seo_title=value, exact=exact)


def _blog_field(field):
    def build(match, ctx):
        if match.group("v") in _RESERVED_VARS:
            return None
        return php.Decision(
            "G2",
            node={"kind": "blog_field", "field": field},
            needs_loop=True,
        )

    return build


def _closed_with_tail(code):
    """True when the '{' just before code is closed and text follows."""
    depth, quote, i = 1, "", 0
    while i < len(code):
        char = code[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return bool(code[i + 1 :].strip())
        i += 1
    return False


def _drop(idiom, **kw):
    def build(match, ctx):
        if _closed_with_tail(match.group("body")):
            return None
        return php.Decision(idiom, region="drop", **kw)

    return build


def _fixed(idiom, node=None, **kw):
    return lambda match, ctx: php.Decision(idiom, node=node, **kw)


STATEMENT_IDIOMS = (
    (
        _rx(r"^includeContainer\('(?P<ref>[A-Za-z0-9_-]{1,128})'\)$"),
        lambda m, ctx: php.Decision(
            "INC", node={"kind": "include", "ref": m.group("ref")}
        ),
    ),
    (
        _rx(ECHO + r"urlencode\(\$mysoc->getFullAddress\([^)]*\)\)$"),
        _fixed("C6", {"kind": "map"}),
    ),
    (
        _rx(ECHO + r"\$mysoc->getFullAddress\([^()]*\)$"),
        _fixed("C4", {"kind": "address"}),
    ),
    (
        _rx(
            ECHO + r"(?:getImageFileNameForSize\("
            r"\$mysoc->logo(?:_squarred)?"
            r"(?: \? \$mysoc->logo_squarred : \$mysoc->logo)?"
            r", '_[a-z]+'\)|\$mysoc->logo(?:_squarred)?)$"
        ),
        _fixed("C8", {"kind": "logo"}),
    ),
    (_rx(ECHO + r"\$mysoc->(?P<f>\w+)$"), _company),
    (_rx(ECHO + r"\$socInfo\['(?P<f>\w+)'\]$"), _socinfo),
    (
        _rx(
            r"^foreach ?\(\$mysoc->socialnetworks as \$\w+ => \$\w+\) ?"
            + _BODY
            + "$"
        ),
        _fixed("C7", {"kind": "social"}),
    ),
    (
        _rx(ECHO + r"\$websitepage->title$"),
        _fixed("P1", {"kind": "title"}),
    ),
    (
        _rx(ECHO + r"newToken\(\)$"),
        _fixed("R1", {"kind": "drop_element"}),
    ),
    (
        _rx(ECHO + r"dol_escape_htmltag\(GETPOST\('s', ?'alphanohtml'\)\)$"),
        _fixed("R2", {"kind": "search_value"}),
    ),
    (
        _rx(r"^if ?\(GETPOST\('action'\) == 'sendmail'\) ?\{(?P<body>.*)"),
        _drop("R3", contact_handler=True),
    ),
    (
        _rx(
            r"^if ?\(function_exists\('getPagesFromSearchCriterias'\)\) ?\{(?P<body>.*)"
        ),
        _drop("R6"),
    ),
    (
        _rx(
            r"^define\('__SEO_PAGE_TITLE__', ?(?:'(?P<lit>[^']*)'"
            r"|\$weblangs->trans\('(?P<key>[\w.-]+)'\))\)$"
        ),
        _seo,
    ),
    (
        _rx(ECHO + r"\$weblangs->trans\('(?P<key>[A-Za-z0-9_.-]+)'\)$"),
        _trans,
    ),
    (
        _rx(ECHO + r"\$(?:weblangs|langs)->defaultlang$"),
        lambda m, ctx: php.Decision("T4", node=_text(ctx.main_lang)),
    ),
    (
        _rx(ECHO + r"getDolGlobalString\('\w+'\) \?: '(?P<lit>[^']*)'$"),
        lambda m, ctx: php.Decision("O1", node=_text(m.group("lit"))),
    ),
    (
        _rx(ECHO + r"\$website->ref$"),
        lambda m, ctx: php.Decision("REF", node=_text(ctx.site_key)),
    ),
    (
        _rx(ECHO + r"\$(?P<v>\w+)->(?P<f>title|description)$"),
        lambda m, ctx: _blog_field(m.group("f"))(m, ctx),
    ),
    (_rx(ECHO + r"\$(?P<v>\w+)->pageurl$"), _blog_field("url")),
    (
        _rx(
            ECHO + r"\(\$(?P<v>\w+)->author_alias \? \$(?P=v)->author_alias"
            r" : '[^']*'\)$"
        ),
        _blog_field("author"),
    ),
    (
        _rx(
            ECHO + r"dol_print_date\(\$(?P<v>\w+)->date_creation"
            r"(?:, ?(?:'[A-Za-z_]*'|\$weblangs)){0,3}\)$"
        ),
        _blog_field("date"),
    ),
    (
        _rx(
            ECHO + r"\(\$(?P<v>\w+)->image \? (?:\$(?P=v)->image"
            r"|'[^'()]*'\.\$(?P=v)->image) : (?:'[^'()]*'"
            r"|\$mysoc->logo)\)$"
        ),
        _blog_field("image"),
    ),
)


def _silent(statement):
    for idiom, pattern in _SILENT:
        if pattern.fullmatch(statement):
            return idiom
    return ""


def _blog_loop(statements):
    """G1: [assignments...], fetchAll of blogposts, foreach over it."""
    if len(statements) < 2:
        return None
    *pre, fetch, loop = statements
    assigned = {}
    for statement in pre:
        match = _ASSIGN.fullmatch(statement)
        if not match:
            return None
        assigned[match.group("var")] = match.group("value")
    fetch_match = _FETCH.fullmatch(fetch)
    if not fetch_match:
        return None
    limit = fetch_match.group("limit")
    if limit.startswith("$"):
        limit = assigned.get(limit[1:], "")
    if not re.fullmatch(r"[0-9]{1,6}", limit):
        return None
    open_match = _FOREACH_OPEN.fullmatch(loop)
    if open_match and open_match.group("arr") == fetch_match.group("arr"):
        return php.Decision(
            "G1",
            node={"kind": "blog_loop", "limit": int(limit)},
            region="loop",
        )
    full_match = _FOREACH_FULL.fullmatch(loop)
    if full_match and full_match.group("arr") == fetch_match.group("arr"):
        return php.Decision(
            "G1P", node={"kind": "blog_list", "limit": int(limit)}
        )
    return None


def classify(tok, ctx):
    """Decision for one PHP block, or None when the block is unknown."""
    norm = php.normalise(tok.code)
    if tok.echo and norm:
        norm = "echo " + norm
    if not norm:
        return php.Decision("T6")
    kept, silent = [], ""
    for statement in split_statements(norm):
        idiom = _silent(statement)
        if idiom:
            silent = silent or idiom
        else:
            kept.append(statement)
    if not kept:
        return php.Decision(silent)
    loop = _blog_loop(kept)
    if loop:
        return loop
    if len(kept) != 1:
        return None
    for pattern, build in STATEMENT_IDIOMS:
        match = pattern.fullmatch(kept[0])
        if match:
            return build(match, ctx)
    return None
