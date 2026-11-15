# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""One message template and one severity per report code.

_lt returns its argument unchanged. Odoo's .pot extraction reads every
_("...") and _lt("...") call of the module's .py files by name, this file
included, so the templates reach the .pot and fr_CA.po. The Odoo side
translates a template with env._(template, **params) when it writes a line.
"""

import re

from .model import Finding


def _lt(source):
    return source


TEMPLATES = {
    "skipped_translation": (
        "info",
        _lt(
            "Page %(ref)s (%(lang)s, %(url)s) skipped: translation of %(translates)s"
        ),
    ),
    "php_removed": (
        "warning",
        _lt(
            "PHP removed from %(ref)s at line %(line)s (%(context)s): %(code)s; %(bytes)s HTML bytes removed"
        ),
    ),
    "php_unbalanced": (
        "warning",
        _lt(
            "PHP control structure opened in %(ref)s at line %(line)s is never closed: only its opening block was removed"
        ),
    ),
    "php_unpaired": (
        "warning",
        _lt(
            "PHP closing block in %(ref)s at line %(line)s has no opening block: removed alone"
        ),
    ),
    "foreign_lang_skipped": (
        "info",
        _lt("Page %(ref)s (%(lang)s, %(url)s) skipped: not chosen"),
    ),
    "foreign_lang_page": (
        "warning",
        _lt("Page %(ref)s imported although its language is %(lang)s"),
    ),
    "choice_ignored": (
        "warning",
        _lt(
            "Page choice %(ref)s ignored: not a page in another language without a translation link"
        ),
    ),
    "local_edit_kept": (
        "warning",
        _lt(
            '%(kind)s %(ref)s was edited in Odoo: the edit is kept; the option "Overwrite local edits" would replace it'
        ),
    ),
    "local_edit_overwritten": (
        "warning",
        _lt("%(kind)s %(ref)s was edited in Odoo: the edit was overwritten"),
    ),
    "menu_skipped_existing_url": (
        "info",
        _lt(
            "Menu entry %(label)s skipped: %(url)s is already in the menu as %(existing)s"
        ),
    ),
    "stale_record": (
        "warning",
        _lt(
            "%(kind)s %(ref)s is not in this import (%(reason)s): kept unchanged"
        ),
    ),
    "skipped_container_type": (
        "info",
        _lt("Container %(ref)s of type %(type)s skipped"),
    ),
    "unused_container": (
        "info",
        _lt("Container %(ref)s of type %(type)s is not included by any page"),
    ),
    "layout_detected": (
        "info",
        _lt("Container %(ref)s detected as the %(role)s"),
    ),
    "footer_not_imported": (
        "info",
        _lt("Footer container %(ref)s not imported: the Odoo footer applies"),
    ),
    "container_inlined": (
        "info",
        _lt("Container %(container)s inserted into %(ref)s"),
    ),
    "php_approximated": (
        "warning",
        _lt("Text %(key)s of %(ref)s resolved approximately as %(value)s"),
    ),
    "langs_fallback": (
        "warning",
        _lt(
            "No bundled %(domain)s.lang for %(lang)s: texts come from %(used)s"
        ),
    ),
    "langs_version_mismatch": (
        "info",
        _lt(
            "Source made by Dolibarr %(source)s, bundled language files from Dolibarr %(bundled)s"
        ),
    ),
    "main_lang_defaulted": (
        "info",
        _lt("Source main language missing: %(lang)s used"),
    ),
    "form_replaced": (
        "info",
        _lt("Contact form of %(ref)s replaced by the Odoo contact form"),
    ),
    "search_rewired": (
        "info",
        _lt("Search form of %(ref)s sent to the Odoo website search"),
    ),
    "social_unsupported": (
        "info",
        _lt("Social network %(network)s has no Odoo website field"),
    ),
    "literal_placeholder": (
        "info",
        _lt("Page %(ref)s keeps placeholders as text: %(placeholders)s"),
    ),
    "missing_media": (
        "warning",
        _lt("Media %(url)s referenced by %(ref)s not found"),
    ),
    "media_matched_by_name": (
        "info",
        _lt("Media %(wanted)s of %(ref)s matched by name to %(found)s"),
    ),
    "media_url_conflict": (
        "warning",
        _lt(
            "URL %(url)s is already used by another attachment: media served at %(fallback)s"
        ),
    ),
    "media_skipped_type": (
        "info",
        _lt("Media %(relpath)s skipped: file type not allowed"),
    ),
    "media_name_refused": (
        "warning",
        _lt("Media %(relpath)s refused: invalid name"),
    ),
    "media_too_large": (
        "warning",
        _lt(
            "Media %(relpath)s skipped: larger than the %(limit)s per-file limit"
        ),
    ),
    "media_duplicate": (
        "warning",
        _lt("Media %(relpath)s skipped: another file has the same name"),
    ),
    "media_unreadable": (
        "warning",
        _lt("Media %(url)s unreadable in the zip: %(error)s"),
    ),
    "media_capped": (
        "warning",
        _lt("Media import stopped: %(limit)s reached"),
    ),
    "svg_sanitised": (
        "info",
        _lt("SVG %(relpath)s cleaned: %(removed)s"),
    ),
    "unresolved_link": (
        "warning",
        _lt("Link %(url)s in %(ref)s does not match any imported page"),
    ),
    "url_conflict": (
        "warning",
        _lt("Page %(ref)s placed at %(url)s: %(wanted)s is already used"),
    ),
    "rewrite_conflict": (
        "warning",
        _lt(
            "Redirect from %(url)s not created: a redirect the import does not own exists"
        ),
    ),
    "ref_slugified": (
        "warning",
        _lt("Page reference %(original)s changed to %(ref)s"),
    ),
    "form_removed": (
        "warning",
        _lt(
            "Form element posting to the Odoo form controller removed from %(ref)s: %(what)s"
        ),
    ),
    "unsafe_markup_removed": (
        "warning",
        _lt("Unsafe markup removed from %(ref)s: %(what)s"),
    ),
    "head_asset_dropped": (
        "info",
        _lt("Head element dropped from %(ref)s: %(what)s"),
    ),
    "script_removed": (
        "warning",
        _lt("Script removed from %(ref)s: %(what)s"),
    ),
    "script_kept": (
        "warning",
        _lt("Script kept in %(ref)s: %(what)s"),
    ),
    "inline_script_needs_jquery": (
        "warning",
        _lt("Inline script of %(ref)s uses jQuery, which Odoo loads lazily"),
    ),
    "css_rescoped": (
        "info",
        _lt("CSS selector %(selector)s rescoped to %(scoped)s"),
    ),
    "css_external_removed": (
        "info",
        _lt("External CSS reference removed from %(ref)s: %(url)s"),
    ),
    "recreated": (
        "warning",
        _lt("%(kind)s %(ref)s was deleted in Odoo and has been recreated"),
    ),
    "menu_flattened": (
        "info",
        _lt("Menu entry %(label)s moved up: Odoo menus have two levels"),
    ),
    "menu_capped": (
        "warning",
        _lt("Menu import stopped after %(limit)s entries"),
    ),
    "language_mismatch": (
        "warning",
        _lt(
            "Source main language %(source)s differs from the website default language %(website)s"
        ),
    ),
    "author_alias_ignored": (
        "info",
        _lt("Author alias %(alias)s of %(ref)s ignored"),
    ),
    "credits": ("info", _lt("%(file)s: %(text)s")),
    "source_error": ("error", _lt("Source error: %(error)s")),
    "run_error": ("error", _lt("Import failed: %(error)s")),
    "page_error": (
        "error",
        _lt("Page %(ref)s skipped: %(reason)s"),
    ),
}

CODES = tuple(TEMPLATES)

_PLACEHOLDER = re.compile(r"%\((\w+)\)s")


def params_of(code):
    """Names of the %(name)s placeholders of one template."""
    return set(_PLACEHOLDER.findall(TEMPLATES[code][1]))


def finding(
    code, /, page_ref="", lang="", url="", detail="", severity=None, **params
):
    """Build a Finding whose params exactly fill the code's template.

    The lang and url placeholders are filled from the finding's own lang
    and url fields, so a caller never passes them twice. The code is
    positional-only: a template may itself have a parameter named code.
    """
    if code not in TEMPLATES:
        raise KeyError(code)
    expected = params_of(code)
    params = dict(params)
    if "lang" in expected:
        params.setdefault("lang", lang)
    if "url" in expected:
        params.setdefault("url", url)
    if set(params) != expected:
        raise ValueError(
            "%s expects %s, got %s" % (code, sorted(expected), sorted(params))
        )
    return Finding(
        severity=severity or TEMPLATES[code][0],
        code=code,
        page_ref=page_ref,
        lang=lang,
        url=url,
        params={name: str(value) for name, value in params.items()},
        detail=(detail or "")[:300],
    )


def render(code, params, translate=None):
    """Message text of one line; translate maps the template first."""
    template = TEMPLATES[code][1]
    if translate:
        template = translate(template)
    return template % params
