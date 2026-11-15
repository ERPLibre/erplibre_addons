# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""PHP blocks of a Dolibarr page: tokenizer, pairing and marker assembly.

tokenize() runs before any HTML parsing. A small HTML automaton, fed with
the HTML between blocks, records the context of each block: text,
attribute (with its name), script (raw text of script or style) or tag
(between attributes). A last unclosed block runs to the end of the
content, as in PHP. The content is only scanned, never executed, and every
scan is iterative and linear in the input.
"""

import dataclasses
import re

_PHP_OPEN = re.compile(r"<\?(?:php\b|=)", re.I)
_TAG_OPEN = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:-]*)")
_ATTR_NAME = re.compile(r"[^\s=>/\"']+")
_UNQUOTED = re.compile(r"[^\s>]*")
RAW_TAGS = ("script", "style")


@dataclasses.dataclass
class Html:
    text: str


@dataclasses.dataclass
class Php:
    code: str
    line: int = 1
    context: str = "text"
    attr: str = ""
    closed: bool = True
    echo: bool = False
    raw_at: tuple = None


def _scan(code, keep_strings):
    """Drop PHP comments outside strings; empty strings unless kept."""
    out, i, n = [], 0, len(code)
    while i < n:
        char = code[i]
        if char in "'\"":
            j = i + 1
            while j < n and code[j] != char:
                j += 2 if code[j] == "\\" else 1
            out.append(code[i : j + 1] if keep_strings else char + char)
            i = j + 1
            continue
        if code.startswith("/*", i):
            j = code.find("*/", i + 2)
            out.append(" ")
            i = n if j < 0 else j + 2
            continue
        if char == "#" or code.startswith("//", i):
            j = code.find("\n", i)
            i = n if j < 0 else j
            continue
        out.append(char)
        i += 1
    return "".join(out)


def strip_comments(code):
    """Code without its comments; strings are kept as written."""
    return _scan(code, keep_strings=True)


def mask(code):
    """Code without its comments and with every string emptied."""
    return _scan(code, keep_strings=False)


def _php_end(content, i):
    """End of the block whose code starts at i: (code_end, next, closed).

    '?>' ends a block outside strings and block comments; it also ends a
    '//' or '#' line comment, as in PHP.
    """
    n = len(content)
    while i < n:
        char = content[i]
        if char in "'\"":
            j = i + 1
            while j < n and content[j] != char:
                j += 2 if content[j] == "\\" else 1
            i = j + 1
            continue
        if content.startswith("/*", i):
            j = content.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if char == "#" or content.startswith("//", i):
            while (
                i < n
                and content[i] != "\n"
                and not content.startswith("?>", i)
            ):
                i += 1
            continue
        if content.startswith("?>", i):
            return i, i + 2, True
        i += 1
    return n, n, False


class _HtmlState:
    """HTML automaton fed with the HTML found between PHP blocks."""

    def __init__(self):
        self.mode = "text"
        self.tag = ""
        self.closing = False
        self.attr = ""
        self.quote = ""
        self.expect_value = False
        self._raw_end = None
        self.chunk = 0
        self.tag_at = None

    def context(self):
        if self.mode in ("value", "unquoted") or (
            self.mode == "tag" and self.expect_value
        ):
            return "attribute", self.attr
        if self.mode == "tag":
            return "tag", ""
        if self.mode == "raw":
            return "script", self.tag
        return "text", ""

    def after_php(self):
        """A PHP block standing where a value is expected starts that value.

        The value then continues, unquoted, until whitespace or '>'.
        """
        if self.mode == "tag" and self.expect_value:
            self.mode, self.expect_value = "unquoted", False

    def feed(self, text):
        i, n = 0, len(text)
        while i < n:
            if self.mode == "text":
                j = text.find("<", i)
                if j < 0:
                    return
                if text.startswith("<!--", j):
                    self.mode, i = "comment", j + 4
                    continue
                match = _TAG_OPEN.match(text, j)
                if not match:
                    i = j + 1
                    continue
                self.tag_at = (self.chunk, j)
                self.mode = "tag"
                self.closing = bool(match.group(1))
                self.tag = match.group(2).lower()
                self.attr, self.expect_value = "", False
                i = match.end()
                continue
            if self.mode == "comment":
                j = text.find("-->", i)
                if j < 0:
                    return
                self.mode, i = "text", j + 3
                continue
            if self.mode == "raw":
                if self._raw_end is None:
                    self._raw_end = re.compile("</" + self.tag, re.I)
                found = self._raw_end.search(text, i)
                if not found:
                    return
                self.mode, i = "text", found.start()
                continue
            if self.mode == "unquoted":
                i = _UNQUOTED.match(text, i).end()
                if i >= n:
                    return
                self.mode = "tag"
                continue
            if self.mode == "value":
                j = text.find(self.quote, i)
                if j < 0:
                    return
                self.mode, self.expect_value, i = "tag", False, j + 1
                continue
            char = text[i]
            if char == ">":
                raw = self.tag in RAW_TAGS and not self.closing
                self.mode = "raw" if raw else "text"
                self._raw_end = None
                self.expect_value = False
                i += 1
            elif char.isspace():
                i += 1
            elif self.expect_value:
                if char in "\"'":
                    self.mode, self.quote = "value", char
                    i += 1
                else:
                    self.mode = "unquoted"
                self.expect_value = False
            elif char == "=":
                self.expect_value = True
                i += 1
            else:
                match = _ATTR_NAME.match(text, i)
                if match:
                    self.attr = match.group(0).lower()
                    i = match.end()
                else:
                    i += 1


def tokenize(content):
    """Split content into Html and Php tokens, in order."""
    tokens, state, i = [], _HtmlState(), 0
    line, counted = 1, 0
    while i < len(content):
        match = _PHP_OPEN.search(content, i)
        if not match:
            tokens.append(Html(content[i:]))
            break
        if match.start() > i:
            chunk = content[i : match.start()]
            tokens.append(Html(chunk))
            state.chunk = len(tokens) - 1
            state.feed(chunk)
        line += content.count("\n", counted, match.start())
        counted = match.start()
        end, nxt, closed = _php_end(content, match.end())
        context, attr = state.context()
        tokens.append(
            Php(
                code=content[match.end() : end],
                line=line,
                context=context,
                attr=attr,
                closed=closed,
                echo=match.group(0).endswith("="),
                raw_at=state.tag_at if context == "script" else None,
            )
        )
        state.after_php()
        i = nxt
    return tokens


MARKER_TAG = "dolibarr-q"
LOOP_TAG = "dolibarr-loop"
ATTR_TOKEN = "DOLIBARRQ%dQ"
ATTR_TOKEN_RE = re.compile(r"DOLIBARRQ([0-9]+)Q")
_TAG_LOOKALIKE = re.compile(r"dolibarr-(q|loop)\b", re.I)
_TOKEN_LOOKALIKE = re.compile(r"DOLIBARRQ(\d+)Q", re.I)
_ALT_CLOSE = re.compile(r"^end(if|foreach|for|while|switch)$", re.I)
_ALT_MIDDLE = re.compile(r"^(else\s*:|(elseif|else\s+if)\b.*:)$", re.I | re.S)
_ALT_OPEN = re.compile(
    r"^(if|foreach|for|while|switch)\s*\(.*\)\s*:$", re.I | re.S
)
_DYNAMIC_ATTR = re.compile(r"\s([^\s=<>\"']+)\s*=\s*([\"'])$")
_SECRET = re.compile(r"dol_hash|securekey|password|api_?key", re.I)


def normalise(code):
    """Comparison form of a block: no comments, one space, one quote."""
    text = re.sub(r"\s+", " ", strip_comments(code)).strip()
    return text.replace('"', "'").rstrip("; ").strip()


def report_code(code):
    """Normalised code for a report line; secret-bearing blocks hide it."""
    text = normalise(code)
    if _SECRET.search(text):
        return "(secret-bearing block)"
    return text[:300]


_NAME_REF = re.compile(r"&#(?:[xX]([0-9a-fA-F]+)|([0-9]+));?")


def _decode_name_ref(match):
    """The character a numeric reference names, if it is [A-Za-z0-9_-]."""
    digits = (match.group(1) or match.group(2)).lstrip("0")
    if len(digits) > 7:
        return match.group(0)
    code = int(digits or "0", 16 if match.group(1) else 10)
    char = chr(code) if code < 128 else ""
    if char and (char.isalnum() or char in "_-"):
        return char
    return match.group(0)


def looks_like_marker(text):
    """True when text holds anything shaped like an engine marker."""
    return bool(_TOKEN_LOOKALIKE.search(text) or _TAG_LOOKALIKE.search(text))


def neutralise(text):
    """Make source text that looks like an engine marker inert.

    Numeric character references that spell a name character are decoded
    first: a token written through them parses to the same characters, so
    it must be recognised the same way.
    """
    text = _NAME_REF.sub(_decode_name_ref, text)
    text = _TAG_LOOKALIKE.sub(lambda m: "dolibarr_x" + m.group(1), text)
    return _TOKEN_LOOKALIKE.sub(lambda m: "DOLIBARRX%sX" % m.group(1), text)


@dataclasses.dataclass
class Region:
    open: int
    close: int
    middles: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Pairing:
    regions: list
    unbalanced: list
    orphans: list


def block_role(code):
    """('open'|'close'|'middle'|'none', count) of one PHP block."""
    text = re.sub(r"\s+", " ", mask(code)).strip().rstrip(";").strip()
    if _ALT_CLOSE.match(text):
        return "close", 1
    if _ALT_MIDDLE.match(text):
        return "middle", 0
    if _ALT_OPEN.match(text):
        return "open", 1
    delta = text.count("{") - text.count("}")
    if delta > 0:
        return "open", delta
    if delta < 0:
        return "close", -delta
    if text.startswith("}") and text.endswith("{"):
        return "middle", 0
    return "none", 0


def pair(tokens):
    """Match openers with closers by brace depth and alternative syntax."""
    stack, regions, orphans, middles = [], [], [], {}
    for idx, tok in enumerate(tokens):
        if not isinstance(tok, Php):
            continue
        role, count = block_role(tok.code)
        if role == "open":
            stack.extend([idx] * count)
        elif role == "middle":
            if stack:
                middles.setdefault(stack[-1], []).append(idx)
            else:
                orphans.append(idx)
        elif role == "close":
            for _i in range(count):
                if not stack:
                    orphans.append(idx)
                    break
                opener = stack.pop()
                regions.append(Region(opener, idx, middles.pop(opener, [])))
    return Pairing(regions, sorted(set(stack)), orphans)


def top_level_blocks(tokens):
    """Indexes of PHP blocks that no region encloses."""
    inside = set()
    for region in pair(tokens).regions:
        inside.update(range(region.open + 1, region.close))
    return [
        i
        for i, tok in enumerate(tokens)
        if isinstance(tok, Php) and i not in inside
    ]


@dataclasses.dataclass
class Decision:
    """How assemble() renders one block that idioms.py recognised.

    node is the marker payload (None renders nothing). region "loop" opens
    a dolibarr-loop up to the block's closer; region "drop" removes the
    block's region (or the block alone when it has no closer) and records
    it like any removal (line, code, bytes), without counting it as
    unknown. needs_loop marks a block that is only
    meaningful inside a loop region.
    """

    idiom: str
    node: dict = None
    region: str = ""
    needs_loop: bool = False
    exact: bool = True
    seo_title: str = ""
    contact_handler: bool = False


@dataclasses.dataclass
class Assembly:
    html: str = ""
    nodes: dict = dataclasses.field(default_factory=dict)
    removed: list = dataclasses.field(default_factory=list)
    warnings: list = dataclasses.field(default_factory=list)
    unknown_blocks: int = 0
    removed_bytes: int = 0


def _size(text):
    return len(text.encode("utf-8"))


def _raw_end(text, tag):
    """Index just after '</tag ...>' in text, or -1."""
    start = text.lower().find("</" + tag)
    if start < 0:
        return -1
    end = text.find(">", start)
    return -1 if end < 0 else end + 1


# Engine markers are built from NUL-delimited sentinels, which source text
# never carries (they are removed on entry): the lookalike scrub then runs
# once on the fully joined page, so text split around a removed block
# cannot be spliced into a marker.
_SENTINEL = re.compile(r"\x00([QALESK])([\d_]*)\x00")
_POSITION = re.compile(r"\x00[SK][\d_]*\x00")
_SENTINEL_FORMS = {
    "Q": '<%s id="%%s"></%s>' % (MARKER_TAG, MARKER_TAG),
    "A": ATTR_TOKEN.replace("%d", "%s"),
    "L": '<%s id="%%s">' % LOOP_TAG,
    "E": "</%s>" % LOOP_TAG,
    "S": "",
    "K": "",
}


def _sentinel(kind, num=""):
    return "\x00%s%s\x00" % (kind, num)


def _finish(joined):
    """Scrub source lookalikes, then expand the sentinels into markers.

    Position sentinels vanish first: they leave no trace between the
    pieces of text they separated.
    """
    joined = _POSITION.sub("", joined)
    return _SENTINEL.sub(
        lambda m: _SENTINEL_FORMS[m.group(1)].replace("%s", m.group(2)),
        neutralise(joined),
    )


def _source_size(text):
    return _size(_SENTINEL.sub("", text))


def _cut_script(out, raw_at):
    """Drop the raw element in progress from out; return its output size.

    The cut starts at the sentinel of that element's own opening tag; when
    the tag went with a skipped region, the cut starts where that region
    ended (the K sentinel), so its remaining content goes too. Loop
    markers inside the cut part are kept, so loops stay balanced.
    """
    joined = "".join(out)
    key = _sentinel("S", "%d_%d" % raw_at) if raw_at else ""
    start = joined.rfind(key) if key else -1
    if start < 0:
        start = joined.rfind(_sentinel("K"))
    if start < 0:
        return 0
    tail = joined[start:]
    out[:] = [joined[:start]] + [
        m.group(0) for m in _SENTINEL.finditer(tail) if m.group(1) in "LE"
    ]
    return _source_size(tail)


def _cut_attribute(out, following):
    """Drop a fully dynamic attribute from out; return its quote or ''."""
    joined = "".join(out)
    match = _DYNAMIC_ATTR.search(joined)
    if (
        match
        and isinstance(following, Html)
        and following.text.startswith(match.group(2))
    ):
        out[:] = [joined[: match.start()]]
        return match.group(2)
    return ""


def _raw_starts(tokens):
    """Html token index -> positions where a script or style tag opens."""
    starts = {}
    for tok in tokens:
        if isinstance(tok, Php) and tok.raw_at:
            where, pos = tok.raw_at
            if pos not in starts.setdefault(where, []):
                starts[where].append(pos)
    return starts


def _html_pieces(idx, text, cuts, quote, raw_tag):
    """Html text as (kept pieces, removed size, raw_tag still open).

    A leading quote of a removed attribute goes, and so does the raw
    element's remainder up to its closing tag. A sentinel marks each
    place where a script or style tag opens.
    """
    cuts = [(c, len(text[:c].replace("\x00", ""))) for c in cuts]
    text = text.replace("\x00", "")
    offset = 1 if quote and text.startswith(quote) else 0
    removed = 0
    if raw_tag:
        end = _raw_end(text[offset:], raw_tag)
        cut = text[offset:] if end < 0 else text[offset : offset + end]
        removed = _size(cut)
        if end < 0:
            return [], removed, raw_tag
        offset += end
    pieces, last = [], offset
    for orig, cut in sorted(c for c in cuts if c[1] >= offset):
        pieces += [text[last:cut], _sentinel("S", "%d_%d" % (idx, orig))]
        last = cut
    pieces.append(text[last:])
    return pieces, removed, ""


def assemble(tokens, decisions):
    """Rebuild the page HTML with markers; remove unknown PHP by region."""
    pairing = pair(tokens)
    close_of = {}
    for region in pairing.regions:
        close_of[region.open] = max(
            close_of.get(region.open, -1), region.close
        )
    unbalanced, orphans = set(pairing.unbalanced), set(pairing.orphans)
    raw_starts = _raw_starts(tokens)
    asm, out = Assembly(), []
    loop_closes = {}
    skip_until, skip_record = -1, None
    raw_tag, strip_quote = "", ""

    def marker(node, tok):
        """Store a copy of node with the block's source line."""
        key = str(len(asm.nodes) + 1)
        asm.nodes[key] = dict(node, line=tok.line)
        return key

    def record(tok, context, nbytes):
        entry = {
            "line": tok.line,
            "context": context,
            "code": report_code(tok.code),
            "bytes": nbytes,
        }
        asm.removed.append(entry)
        asm.removed_bytes += nbytes
        return entry

    def skip(idx, record_entry):
        """Skip the region opened at idx; loops it closes still close."""
        nonlocal skip_until, skip_record
        skip_until, skip_record = close_of[idx], record_entry
        for pos in sorted(loop_closes):
            if idx < pos <= skip_until:
                out.append(_sentinel("E") * loop_closes.pop(pos))
        out.append(_sentinel("K"))

    for idx, tok in enumerate(tokens):
        if idx <= skip_until:
            if isinstance(tok, Html) and skip_record is not None:
                skip_record["bytes"] += _size(tok.text)
                asm.removed_bytes += _size(tok.text)
            continue
        if isinstance(tok, Html):
            pieces, removed, raw_tag = _html_pieces(
                idx, tok.text, raw_starts.get(idx, []), strip_quote, raw_tag
            )
            strip_quote = ""
            if removed:
                asm.removed[-1]["bytes"] += removed
                asm.removed_bytes += removed
            out.extend(pieces)
            continue
        if idx in loop_closes:
            out.append(_sentinel("E") * loop_closes.pop(idx))
            continue
        if raw_tag:
            continue
        dec = decisions.get(idx)
        loop_depth = sum(loop_closes.values())
        if dec is not None and dec.needs_loop and not loop_depth:
            dec = None
        if dec is not None and dec.region == "loop":
            if idx in close_of:
                out.append(_sentinel("L", marker(dec.node, tok)))
                loop_closes[close_of[idx]] = (
                    loop_closes.get(close_of[idx], 0) + 1
                )
                continue
            dec = None
        if dec is not None and dec.region == "drop":
            entry = record(tok, "text", 0)
            if idx in close_of:
                skip(idx, entry)
            continue
        if dec is not None:
            if dec.node is None or tok.context == "tag":
                continue
            if tok.context == "text":
                out.append(_sentinel("Q", marker(dec.node, tok)))
                continue
            if tok.context == "attribute":
                out.append(_sentinel("A", marker(dec.node, tok)))
                continue
            if dec.node.get("kind") == "text":
                value = str(dec.node.get("value", ""))
                out.append(value.replace("\x00", "").replace("</", "<\\/"))
                continue
        asm.unknown_blocks += 1
        if tok.context == "script":
            record(tok, "script", _cut_script(out, tok.raw_at))
            raw_tag = tok.attr or "script"
            continue
        if tok.context == "attribute":
            following = tokens[idx + 1] if idx + 1 < len(tokens) else None
            strip_quote = _cut_attribute(out, following)
            record(tok, "attribute", 0)
            continue
        if tok.context == "tag":
            record(tok, "tag", 0)
            continue
        if idx in close_of:
            skip(idx, record(tok, "text", 0))
            continue
        if idx in unbalanced:
            asm.warnings.append(("php_unbalanced", tok.line))
        elif idx in orphans:
            asm.warnings.append(("php_unpaired", tok.line))
        record(tok, "text", 0)
    asm.html = _finish("".join(out))
    return asm
