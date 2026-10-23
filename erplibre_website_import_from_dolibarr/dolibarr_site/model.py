# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Serialisable model of a Dolibarr website and validators of source values.

Every dataclass converts to plain JSON types with to_json() and back with
from_json(). Nested dataclasses are rebuilt from the type hints, so a Site
read back from JSON has the same classes as the one written.
"""

import dataclasses
import re
import typing

CONVERTER_VERSION = "1"

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_REF_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_LANG_RE = re.compile(r"^[a-z]{2,3}([_-][A-Za-z]{2})?$")
_SEGMENT_RE = re.compile(r"^[\w ._\-()+,]+$")
_RELPATH_FORBIDDEN = frozenset("'\"\\;<>{}#?%")


class SourceError(Exception):
    """The whole source is unusable; the run fails with a source_error line."""


class PageError(Exception):
    """One page is unusable; only that page is skipped with page_error."""

    def __init__(self, ref, detail):
        super().__init__("%s: %s" % (ref, detail))
        self.ref = ref
        self.detail = detail


def valid_key(value):
    """Dolibarr website key rule, bounded to 64 characters, case kept."""
    return bool(value and _KEY_RE.fullmatch(value)) and ".." not in value


def valid_ref(value):
    """Dolibarr pageurl and alias rule: [A-Za-z0-9_-], 1 to 128 chars."""
    return bool(_REF_RE.fullmatch(value or ""))


def valid_lang(value):
    """Empty (main language) or a code such as fr, ast, fr_CA or fr-ca."""
    return value == "" or bool(_LANG_RE.fullmatch(value))


def valid_relpath(value, key):
    """Media path under image/<key>/ or js/<key>/, safe in CSS and HTML.

    Segments hold letters (Unicode included), digits, space and ._-()+,;
    no segment is empty, "." or "..", and the path has at most 255
    characters. Quotes, backslash, ;<>{}#?% and control characters are
    refused, so the value can never close a CSS url('') or an attribute.
    """
    if not value or len(value) > 255:
        return False
    for char in value:
        if char in _RELPATH_FORBIDDEN or ord(char) < 32 or ord(char) == 127:
            return False
    parts = value.split("/")
    if len(parts) < 3 or parts[0] not in ("image", "js") or parts[1] != key:
        return False
    return all(
        part not in ("", ".", "..") and _SEGMENT_RE.match(part)
        for part in parts[2:]
    )


def slugify_ref(value):
    """Bring any text into the ref alphabet; never returns an empty ref."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value or "").strip("-")
    return slug[:128] or "page"


def primary_lang(value):
    """fr_CA, fr-ca and FR give fr; empty stays empty."""
    return (value or "").replace("-", "_").split("_")[0].lower()


def _decode(hint, value):
    """Rebuild the value of one field from its JSON form and type hint."""
    if value is None:
        return None
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if isinstance(hint, type) and issubclass(hint, JsonMixin):
        return hint.from_json(value)
    if origin is list and args:
        return [_decode(args[0], item) for item in value]
    if origin is dict and len(args) == 2:
        return {k: _decode(args[1], v) for k, v in value.items()}
    return value


class JsonMixin:
    def to_json(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, data):
        hints = typing.get_type_hints(cls)
        kwargs = {}
        for field in dataclasses.fields(cls):
            if field.name in data:
                kwargs[field.name] = _decode(
                    hints[field.name], data[field.name]
                )
        return cls(**kwargs)


def _list():
    return dataclasses.field(default_factory=list)


def _dict():
    return dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Finding(JsonMixin):
    """One report fact: a code and its parameters, never a message text."""

    severity: str
    code: str
    page_ref: str = ""
    lang: str = ""
    url: str = ""
    params: dict[str, str] = _dict()
    detail: str = ""


@dataclasses.dataclass
class Media(JsonMixin):
    """One media file; zip_name locates its bytes inside the zip."""

    relpath: str
    size: int = 0
    zip_name: str = ""


@dataclasses.dataclass
class MenuItem(JsonMixin):
    """A menu entry; target is a dolibarr-page: token or a plain URL."""

    label: str
    target: str
    new_window: bool = False
    children: "list[MenuItem]" = _list()


@dataclasses.dataclass
class Page(JsonMixin):
    """One Dolibarr page or container, from the source to the analysis.

    body_html holds cleaned HTML with engine markers (dolibarr-q,
    dolibarr-loop, DOLIBARRQ<n>Q in attributes) and link tokens
    (dolibarr-page:, dolibarr-media:, dolibarr-logo:).
    qweb_nodes maps a marker id to the payload that idioms.py produced.
    """

    ref: str
    aliases: list[str] = _list()
    kind: str = "page"
    dolibarr_type: str = "page"
    source_id: int = 0
    fk_page: int = 0
    title: str = ""
    description: str = ""
    keywords: str = ""
    lang: str = ""
    image_relpath: str = ""
    author_alias: str = ""
    date_creation: str = ""
    published: bool = True
    seo_title: str = ""
    head_html: str = ""
    body_html: str = ""
    qweb_nodes: dict[str, dict] = _dict()
    includes: list[str] = _list()
    edge_includes: list[str] = _list()
    has_contact_handler: bool = False
    php_mode: str = "static"
    layout_role: str = ""
    findings: list[Finding] = _list()
    analysis_status: str = "import"
    php_plan: str = "none"
    php_unknown_blocks: int = 0
    php_removed_bytes: int = 0
    translates_ref: str = ""
    script_count: int = 0
    script_detail: str = ""


@dataclasses.dataclass
class Site(JsonMixin):
    """A whole Dolibarr website after the engine's analysis."""

    source_key: str = ""
    dolibarr_version: str = ""
    main_lang: str = ""
    lang_locale: str = ""
    other_langs: list[str] = _list()
    home_ref: str = ""
    pages: list[Page] = _list()
    containers: dict[str, str] = _dict()
    media: list[Media] = _list()
    site_css: str = ""
    site_js: str = ""
    head_assets: str = ""
    site_script_count: int = 0
    site_script_detail: str = ""
    menu: list[MenuItem] = _list()
    findings: list[Finding] = _list()
    langs_source: str = ""
    dropped_refs: list[str] = _list()
    dropped_aliases: list[str] = _list()

    def page(self, ref):
        for page in self.pages:
            if page.ref == ref:
                return page
        return None


@dataclasses.dataclass
class PageRow(JsonMixin):
    """Analysis view of one source page, as the Odoo analysis line stores."""

    ref: str
    title: str = ""
    lang: str = ""
    kind: str = "page"
    source_url: str = ""
    target_url: str = ""
    status: str = "import"
    include: bool = True
    imported_before: bool = False
    php_plan: str = "none"
    php_unknown_blocks: int = 0
    php_removed_bytes: int = 0
    script_count: int = 0
    script_detail: str = ""
    translates_ref: str = ""


@dataclasses.dataclass
class PageChoice(JsonMixin):
    ref: str
    include: bool


@dataclasses.dataclass
class RenderedSite(JsonMixin):
    """render_site() output: arch per page ref, content per post ref."""

    pages: dict[str, str] = _dict()
    posts: dict[str, str] = _dict()
    site_css: str = ""
    site_js: str = ""
    head_arch: str = ""
    findings: list[Finding] = _list()


@dataclasses.dataclass
class Options(JsonMixin):
    """Run options the engine reads; the Odoo run and the CLI fill them."""

    filename: str = ""
    source_key: str = ""
    default_lang: str = "en"
    keep_scripts: bool = False
    style_blog_posts: bool = True
    include_unlinked_langs: bool = False
    include_page_refs: list[str] = _list()
    skip_page_refs: list[str] = _list()
    langs_dir: str = ""
    css_hosts: list[str] = dataclasses.field(
        default_factory=lambda: [
            "fonts.googleapis.com",
            "fonts.gstatic.com",
            "use.fontawesome.com",
            "cdnjs.cloudflare.com",
            "cdn.jsdelivr.net",
        ]
    )
    zip_limits: dict[str, int] = _dict()
