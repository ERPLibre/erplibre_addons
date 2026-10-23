# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Engine entry points: source to analysed Site, choices, rendering.

build_from_zip() reads the zip, runs the PHP pass on every page, sorts the
pages with the table of the spec (first matching case wins), detects the
layout containers, then assembles and cleans the pages that are kept.
"""

import hashlib
import os
import posixpath

from lxml import html as lhtml

from . import css, html2arch, idioms, langs, layout, php, urls, zipsource
from .messages import finding
from .model import (
    PageError,
    PageRow,
    RenderedSite,
    Site,
    SourceError,
    valid_key,
)

SKIPPED_TYPES = ("library", "service", "setup")
IMAGE_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".avif")


def all_findings(site):
    found = list(site.findings)
    for page in site.pages:
        found.extend(page.findings)
    return found


def _library_code(site):
    return "\n".join(
        tok.code
        for page in site.pages
        if page.dolibarr_type == "library"
        for tok in php.tokenize(page.body_html)
        if isinstance(tok, php.Php)
    )


def _page_domains(codes, library_code):
    domains = []
    if any("setSessionLang(" in code for code in codes):
        domains.extend(langs.weblangs_domains(library_code))
    for code in codes:
        for domain in langs.weblangs_domains(code):
            if domain not in domains:
                domains.append(domain)
    return domains


def _edges(tokens, decisions):
    """[first, last] edge include refs of a page, for detect_layout().

    Among the top-level PHP blocks that give output (an unknown block, or
    a known one with a node), the first and the last each give their
    includeContainer ref, or "" when they are anything else.
    """
    output = []
    for idx in php.top_level_blocks(tokens):
        dec = decisions.get(idx)
        if dec is None or dec.node is not None:
            output.append(dec)
    if not output:
        return ["", ""]

    def ref(dec):
        if dec is not None and dec.node.get("kind") == "include":
            return dec.node["ref"]
        return ""

    return [ref(output[0]), ref(output[-1])]


def _php_pass(site, resolver):
    """Tokenize and classify every block; fill includes and page flags.

    The result is keyed by page identity (id()), never by ref.
    """
    library = _library_code(site)
    fallback_seen, parsed = set(), {}
    for page in site.pages:
        tokens = php.tokenize(page.body_html)
        codes = [t.code for t in tokens if isinstance(t, php.Php)]
        table = resolver.table(_page_domains(codes, library))
        for item in table.findings:
            if item.params["domain"] not in fallback_seen:
                fallback_seen.add(item.params["domain"])
                site.findings.append(item)
        ctx = idioms.IdiomContext(
            site.source_key, site.main_lang, resolver, table
        )
        decisions = {
            i: idioms.classify(t, ctx)
            for i, t in enumerate(tokens)
            if isinstance(t, php.Php)
        }
        for dec in decisions.values():
            if dec is None:
                continue
            if dec.node and dec.node.get("kind") == "include":
                if dec.node["ref"] not in page.includes:
                    page.includes.append(dec.node["ref"])
            if dec.seo_title and not page.seo_title:
                page.seo_title = dec.seo_title
            if dec.contact_handler:
                page.has_contact_handler = True
        page.edge_includes = _edges(tokens, decisions)
        parsed[id(page)] = (tokens, decisions)
    return parsed


def _classify(site, include_targets):
    """Analysis status and kind of each page, first matching case wins."""
    by_id = {p.source_id: p for p in site.pages}
    linked_to = {p.fk_page: p for p in site.pages if p.fk_page}
    for page in site.pages:
        kind = page.dolibarr_type
        foreign = bool(page.lang) and page.lang != site.main_lang
        page.kind = "post" if kind == "blogpost" else "page"
        if page.ref == site.home_ref:
            page.analysis_status, page.kind = "import", "page"
        elif kind in SKIPPED_TYPES:
            page.analysis_status = "skipped"
            page.findings.append(
                finding(
                    "skipped_container_type",
                    page_ref=page.ref,
                    ref=page.ref,
                    type=kind,
                )
            )
        elif page.ref in include_targets:
            page.analysis_status = "container"
        elif foreign and (page.fk_page or page.source_id in linked_to):
            other = by_id.get(page.fk_page) or linked_to.get(page.source_id)
            page.analysis_status = "translation"
            page.translates_ref = other.ref if other else ""
            page.findings.append(
                finding(
                    "skipped_translation",
                    page_ref=page.ref,
                    lang=page.lang,
                    url="/%s/%s.php" % (page.lang, page.ref),
                    ref=page.ref,
                    translates=page.translates_ref,
                )
            )
        elif foreign:
            page.analysis_status = "foreign_unlinked"
        elif kind in ("page", "blogpost", "banner"):
            page.analysis_status = "import"
        else:
            page.analysis_status = "skipped"
            page.findings.append(
                finding(
                    "unused_container",
                    page_ref=page.ref,
                    ref=page.ref,
                    type=kind,
                )
            )


def _refuse_oversized(ref, text, what):
    """Raise PageError when text reaches the parser's text-node limit.

    libxml2's HTML parser cuts a text node at about MAX_TEXT UTF-8 bytes
    and silently drops the rest of its input. A text node never holds more
    bytes than the source it is parsed from, so a source under the limit
    parses whole; one at the limit is refused, never truncated.
    """
    size = len(text.encode("utf-8", "surrogatepass"))
    if size >= html2arch.MAX_TEXT:
        raise PageError(
            ref,
            "%s of %d bytes reaches the %d-byte parser limit"
            % (what, size, html2arch.MAX_TEXT),
        )


def _reset_skipped(page, mark):
    """Skip a page that failed: drop what its analysis wrote after mark."""
    del page.findings[mark:]
    page.analysis_status = "skipped"
    page.body_html = page.head_html = ""
    page.qweb_nodes = {}
    page.php_plan, page.php_mode = "none", "static"
    page.php_unknown_blocks = page.php_removed_bytes = 0
    page.script_count, page.script_detail = 0, ""


def _assemble(site, page, tokens, decisions, opts):
    """Assemble, clean, then rewrite links of one page, in that order.

    Cleaning runs first because url_allowed() refuses the dolibarr-*
    token schemes that rewrite_links() writes. Scripts are kept here;
    the script policy applies at render. PHP in the page head is never
    translated: every block there is removed as unknown and reported, its
    lines counted from the start of the head.
    """
    asm = php.assemble(tokens, decisions)
    head_tokens = php.tokenize(page.head_html)
    head_asm = php.assemble(head_tokens, {})
    _refuse_oversized(page.ref, asm.html, "page HTML")
    _refuse_oversized(page.ref, head_asm.html, "page head")
    has_php = any(isinstance(t, php.Php) for t in tokens + head_tokens)
    unknown = asm.unknown_blocks + head_asm.unknown_blocks
    page.php_unknown_blocks = unknown
    page.php_removed_bytes = asm.removed_bytes + head_asm.removed_bytes
    if not has_php:
        page.php_plan, page.php_mode = "none", "static"
    elif unknown:
        page.php_plan, page.php_mode = "remove", "stripped"
    else:
        page.php_plan, page.php_mode = "translated", "qweb"
    url = "/%s.php" % page.ref
    head_removed = [
        dict(rec, context="head %s" % rec["context"])
        for rec in head_asm.removed
    ]
    for rec in asm.removed + head_removed:
        page.findings.append(
            finding(
                "php_removed", page_ref=page.ref, url=url, ref=page.ref, **rec
            )
        )
    for code, line in asm.warnings + head_asm.warnings:
        page.findings.append(
            finding(code, page_ref=page.ref, url=url, ref=page.ref, line=line)
        )
    seen = set()
    for dec in decisions.values():
        node = dec.node if dec is not None else None
        if node and node.get("kind") == "text" and not dec.exact:
            if node["key"] not in seen:
                seen.add(node["key"])
                page.findings.append(
                    finding(
                        "php_approximated",
                        page_ref=page.ref,
                        key=node["key"],
                        ref=page.ref,
                        value=node["value"][:100],
                    )
                )
    root = html2arch.clean_fragment(
        asm.html,
        page.ref,
        page.findings,
        keep_scripts=True,
        trusted_markers=True,
    )
    urls.rewrite_links(root, site.source_key, site.home_ref)
    page.body_html = html2arch.fragment_html(root)
    page.qweb_nodes = asm.nodes
    head = html2arch.clean_head(
        head_asm.html, page.ref, page.findings, opts.css_hosts
    )
    head_root = lhtml.fragment_fromstring(head, create_parent="div")
    urls.rewrite_links(head_root, site.source_key, site.home_ref)
    page.head_html = html2arch.fragment_html(head_root)
    page.script_count, page.script_detail = _script_summary(
        [root, head_root], opts
    )


def _script_summary(roots, opts, extra=None):
    """(count, detail) of the scripts of roots, as the review shows them.

    Counts add up over roots and extra; a script src on a host outside
    css_hosts is named in the detail.
    """
    counts = extra or {}
    for root in roots:
        counts = html2arch.add_counts(counts, html2arch.script_counts(root))
    hosts = html2arch.external_script_hosts(roots, opts.css_hosts)
    return html2arch.script_summary(counts, hosts)


def _placeholders(page, raw_text):
    found = zipsource.find_placeholders(raw_text)
    if found:
        page.findings.append(
            finding(
                "literal_placeholder",
                page_ref=page.ref,
                ref=page.ref,
                placeholders=", ".join(sorted(set(found)))[:200],
            )
        )


def _resolve_cover(site, page):
    """Blog cover: exact path, same name, same stem, first image, or none."""
    names = [m.relpath for m in site.media]
    raw = page.image_relpath.strip().lstrip("/")
    if raw.startswith("medias/"):
        raw = raw[len("medias/") :]
    if raw:
        parts = raw.split("/")
        if len(parts) >= 3 and parts[0] in ("image", "js"):
            parts[1] = site.source_key
        wanted = "/".join(parts)
        if wanted in names:
            return wanted
        base = posixpath.basename(wanted)
        for name in names:
            if posixpath.basename(name) == base:
                return name
        stem = os.path.splitext(base)[0]
        for name in names:
            name_stem, ext = os.path.splitext(posixpath.basename(name))
            if name_stem == stem and ext.lower() in IMAGE_EXTENSIONS:
                page.findings.append(
                    finding(
                        "media_matched_by_name",
                        page_ref=page.ref,
                        wanted=page.image_relpath,
                        ref=page.ref,
                        found=name,
                    )
                )
                return name
    root = lhtml.fragment_fromstring(page.body_html or "", create_parent="div")
    for img in root.iter("img"):
        src = img.get("src") or ""
        if src.startswith(urls.MEDIA):
            return urls.split_token(src)[0]
    if raw:
        page.findings.append(
            finding(
                "missing_media",
                page_ref=page.ref,
                url=page.image_relpath,
                ref=page.ref,
            )
        )
    return ""


def _site_head(site, opts):
    """Cleaned htmlheader.html, or "" with page_error when too large."""
    name = "htmlheader.html"
    try:
        _refuse_oversized(name, site.head_assets, "site head")
    except PageError as exc:
        site.findings.append(
            finding("page_error", page_ref=name, ref=name, reason=exc.detail)
        )
        return ""
    return html2arch.clean_head(
        site.head_assets, name, site.findings, opts.css_hosts
    )


def build_from_zip(data, opts, source=None):
    """Zip bytes to an analysed Site; nothing is written anywhere."""
    source = source or zipsource.open_zip(data, opts)
    site = zipsource.load_zip(data, opts, source=source)
    resolver = langs.LangResolver(site.lang_locale, opts.langs_dir or None)
    site.langs_source = resolver.source_label
    bundled = langs.bundled_version()
    if (
        resolver.bundled
        and site.dolibarr_version
        and bundled
        and site.dolibarr_version.split(".")[0] != bundled.split(".")[0]
    ):
        site.findings.append(
            finding(
                "langs_version_mismatch",
                source=site.dolibarr_version,
                bundled=bundled,
            )
        )
    raw_text = {id(p): p.body_html + p.head_html for p in site.pages}
    parsed = _php_pass(site, resolver)
    include_targets = {ref for p in site.pages for ref in p.includes}
    _classify(site, include_targets)
    roles = layout.detect_layout(site.pages)
    for ref in sorted(include_targets):
        site.containers[ref] = roles.get(ref, "content")
    for page in site.pages:
        page.layout_role = roles.get(page.ref, "")
        if (
            page.analysis_status == "container"
            and page.ref not in roles
            and page.dolibarr_type in ("page", "banner")
        ):
            page.analysis_status = "import"
    for ref, role in sorted(roles.items()):
        site.findings.append(finding("layout_detected", ref=ref, role=role))
    for page in site.pages:
        if page.analysis_status not in (
            "import",
            "foreign_unlinked",
            "container",
        ):
            page.body_html = page.head_html = ""
            continue
        tokens, decisions = parsed[id(page)]
        mark = len(page.findings)
        try:
            _assemble(site, page, tokens, decisions, opts)
        except PageError as exc:
            _reset_skipped(page, mark)
            page.findings.append(
                finding(
                    "page_error",
                    page_ref=page.ref,
                    ref=page.ref,
                    reason=exc.detail,
                )
            )
            continue
        _placeholders(page, raw_text[id(page)])
        if page.kind == "post":
            page.image_relpath = _resolve_cover(site, page)
            if page.author_alias:
                page.findings.append(
                    finding(
                        "author_alias_ignored",
                        page_ref=page.ref,
                        alias=page.author_alias,
                        ref=page.ref,
                    )
                )
    site.site_css = css.evaluate_css(
        site.site_css, site.source_key, site.findings
    )
    site.site_js = (
        "" if css.is_empty_js(site.site_js) else css.unwrap_php(site.site_js)
    )
    head = _site_head(site, opts)
    head_root = lhtml.fragment_fromstring(head, create_parent="div")
    urls.rewrite_links(head_root, site.source_key, site.home_ref)
    site.head_assets = html2arch.fragment_html(head_root)
    site_file = {"site script file": 1} if site.site_js.strip() else {}
    site.site_script_count, site.site_script_detail = _script_summary(
        [head_root], opts, site_file
    )
    for ref, role in sorted(roles.items()):
        header = site.page(ref)
        if role == "header" and header is not None and not site.menu:
            site.menu, menu_findings = layout.extract_menu(header)
            site.findings.extend(menu_findings)
    return site


def _source_url(page):
    if page.analysis_status == "translation":
        return "/%s/%s.php" % (page.lang, page.ref)
    return "/%s.php" % page.ref


def analyse(site, opts, imported_refs=frozenset()):
    """One analysis row per source page, with its default choice.

    A page in another language without a translation link is included when
    it was imported before; then the last rule that applies wins: all
    languages, the named includes, the named skips. A named ref that is not
    such a page adds a choice_ignored finding to the site and changes
    nothing.
    """
    foreign = {
        p.ref for p in site.pages if p.analysis_status == "foreign_unlinked"
    }
    known = {f.page_ref for f in site.findings if f.code == "choice_ignored"}
    for ref in list(opts.include_page_refs) + list(opts.skip_page_refs):
        if ref not in foreign and ref not in known:
            known.add(ref)
            site.findings.append(
                finding("choice_ignored", page_ref=ref, ref=ref)
            )
    rows = []
    for page in site.pages:
        status = page.analysis_status
        include = status == "import"
        if status == "foreign_unlinked":
            include = page.ref in imported_refs
            if opts.include_unlinked_langs:
                include = True
            if page.ref in opts.include_page_refs:
                include = True
            if page.ref in opts.skip_page_refs:
                include = False
        target = ""
        if page.kind == "page" and status in ("import", "foreign_unlinked"):
            target = "/%s" % page.ref
        rows.append(
            PageRow(
                ref=page.ref,
                title=page.title,
                lang=page.lang,
                kind=page.kind,
                source_url=_source_url(page),
                target_url=target,
                status=status,
                include=include,
                imported_before=page.ref in imported_refs,
                php_plan=page.php_plan,
                php_unknown_blocks=page.php_unknown_blocks,
                php_removed_bytes=page.php_removed_bytes,
                script_count=page.script_count,
                script_detail=page.script_detail,
                translates_ref=page.translates_ref,
            )
        )
    return rows


def apply_choices(site, choices):
    """Copy of site without the unchosen pages in another language.

    A chosen page becomes a plain page to import; any other page in
    another language without a translation link is dropped and listed in
    dropped_refs, its aliases in dropped_aliases. The given site is left
    as it was.
    """
    chosen = {choice.ref: choice.include for choice in choices}
    out = Site.from_json(site.to_json())
    kept = []
    for page in out.pages:
        if page.analysis_status == "foreign_unlinked":
            if chosen.get(page.ref, False):
                page.analysis_status = "import"
                out.findings.append(
                    finding(
                        "foreign_lang_page",
                        page_ref=page.ref,
                        lang=page.lang,
                        ref=page.ref,
                    )
                )
            else:
                out.findings.append(
                    finding(
                        "foreign_lang_skipped",
                        page_ref=page.ref,
                        lang=page.lang,
                        url=_source_url(page),
                        ref=page.ref,
                    )
                )
                out.dropped_refs.append(page.ref)
                out.dropped_aliases.extend(page.aliases)
                continue
        kept.append(page)
    out.pages = kept
    return out


def _check_key(key):
    """Raise SourceError unless key may name a site path segment."""
    if not valid_key(key):
        raise SourceError("invalid source key")


def css_url(site):
    """Site path of the imported stylesheet; "" when the site has no CSS.

    The digest of the CSS text in the query string changes the URL, and so
    the browser cache entry, whenever the stylesheet changes.
    """
    if not site.site_css.strip():
        return ""
    _check_key(site.source_key)
    digest = hashlib.sha256(site.site_css.encode("utf-8")).hexdigest()[:8]
    return "/dolibarr-import/%s/styles.css?v=%s" % (site.source_key, digest)


def js_url(site):
    """Site path of the imported script; "" when the site has none."""
    if not site.site_js.strip():
        return ""
    _check_key(site.source_key)
    return "/dolibarr-import/%s/javascript.js" % site.source_key


def render_site(site, resolver, company_values, opts):
    """Render every kept page, post and the site head against resolver.

    Only pages with the import status are rendered: a layout or content
    container is inlined into the pages that include it, and a skipped page
    is never one, whatever site.containers lists. A PageError drops that
    page or the head and adds a page_error finding carrying the error's own
    ref, which is a site-level name such as htmlheader.html for the head.
    """
    rendered = RenderedSite(site_css=site.site_css, site_js=site.site_js)
    for page in site.pages:
        if page.analysis_status != "import":
            continue
        build = (
            html2arch.post_content
            if page.kind == "post"
            else html2arch.page_arch
        )
        try:
            out = build(
                page, site, resolver, company_values, opts, rendered.findings
            )
        except PageError as exc:
            rendered.findings.append(_render_error(page.ref, exc))
            continue
        target = rendered.posts if page.kind == "post" else rendered.pages
        target[page.ref] = out
    try:
        rendered.head_arch = html2arch.head_arch(
            site,
            css_url(site),
            js_url(site),
            resolver,
            opts,
            rendered.findings,
        )
    except PageError as exc:
        rendered.findings.append(_render_error(exc.ref, exc))
    return rendered


def _render_error(page_ref, exc):
    return finding(
        "page_error", page_ref=page_ref, ref=page_ref, reason=exc.detail
    )
