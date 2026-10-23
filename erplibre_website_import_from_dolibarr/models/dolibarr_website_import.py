# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""A Dolibarr website import run; it is also the import report.

The engine (dolibarr_site) builds and analyses the site; this model
stores the run options, the analysis rows, the report lines and the
state machine. All ORM writes of the website records live in
dolibarr_website_import_writer.py.

A run is an analysis, which writes only the run, its analysis rows and
its report lines, then a stop for review, an analyse-only end, or the
import. Each batch rebuilds the Site from the stored zip, whose sha256
is checked again; a batch never commits, its caller does.
"""

import base64
import dataclasses
import hashlib
import logging
import os
import re
import time

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..dolibarr_site import messages, pipeline, zipsource
from ..dolibarr_site.messages import finding
from ..dolibarr_site.model import (
    Options,
    PageChoice,
    SourceError,
    primary_lang,
    valid_key,
)
from ..dolibarr_site.zipsource import ZipLimits

_logger = logging.getLogger(__name__)

PARAM = "erplibre_website_import_from_dolibarr."
# Seconds of one inline batch started from the wizard or the run form.
INLINE_BUDGET = 60
# Context key that lets the orchestration write state; see write().
STATE_CONTEXT = "dolibarr_import_state"
# Codes that the writer emits only when it first creates or rewrites a
# record: a resumed batch finds the record done and does not emit them
# again, so their lines are kept across the batches of one run.
ONE_TIME_CODES = (
    "url_conflict",
    "recreated",
    "local_edit_overwritten",
    "media_url_conflict",
)
# Secrets that an error message may carry; their value never reaches the
# run or its report. A value is a quoted string, whole, or one word; an
# authorization scheme (Bearer, Basic...) is kept and its value masked.
_VALUE = r"(\"[^\"]*\"|'[^']*'|\S+)"
_SECRET = re.compile(
    r"(?i)(\w*(?:password|passwd|pwd|secret|token|key|authorization)\w*)"
    r"(\s*[=:]\s*)((?:bearer|basic|digest|token)\s+)?" + _VALUE
)
_AUTH_SCHEME = re.compile(r"(?i)\b(bearer|basic|digest)(\s+)" + _VALUE)
# userinfo of a URL, up to the last "@" before the host.
_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s?#]*@")

# Char columns of an analysis row: an empty Char reads False in Odoo and
# is "" in the JSON report, while include and imported_before stay booleans.
_ROW_CHARS = (
    "ref", "lang", "source_url", "target_url", "status", "php_plan",
)  # fmt: skip

STATES = [
    ("draft", "Draft"),
    ("running", "Running"),
    ("to_review", "To review"),
    ("done", "Done"),
    ("failed", "Failed"),
    ("cancelled", "Cancelled"),
]


class BudgetExhausted(Exception):
    """Raised between two records once the time budget of a call is spent."""


class UrlUnavailable(UserError):
    """No free URL was found for a page within MAX_URL_CANDIDATES."""


def error_text(exc):
    """Short text of an exception for the run and its report.

    The class name and the first line of the message, secrets masked,
    at most 500 characters: no traceback and no credential is kept.
    """
    lines = str(exc).strip().splitlines()
    text = lines[0] if lines else ""
    text = _URL_USERINFO.sub(r"\1***@", text)
    text = _SECRET.sub(r"\1\2\3***", text)
    text = _AUTH_SCHEME.sub(r"\1\2***", text)
    # The class name goes in after masking: "KeyError: 'x'" would read as
    # a key and its value.
    return ("%s: %s" % (type(exc).__name__, text))[:500]


class DolibarrWebsiteImport(models.Model):
    _name = "dolibarr.website.import"
    _description = "Dolibarr website import"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(compute="_compute_name", store=True)
    website_id = fields.Many2one("website", required=True, ondelete="cascade")
    zip_file = fields.Binary(attachment=True)
    zip_filename = fields.Char()
    zip_sha256 = fields.Char(readonly=True)
    source_key = fields.Char(required=True)
    blog_name = fields.Char(default="Blog")
    lang = fields.Char(help="Language of the report lines.")
    import_menu = fields.Boolean(default=True)
    set_homepage = fields.Boolean(default=True)
    style_blog_posts = fields.Boolean(default=True)
    keep_scripts = fields.Boolean(default=False)
    overwrite_local_edits = fields.Boolean(
        default=False,
        help="Replace the changes made in Odoo since the last import.",
    )
    review_before_import = fields.Boolean(default=False)
    analyse_only = fields.Boolean(default=False)
    include_unlinked_langs = fields.Boolean()
    include_page_refs = fields.Text(help="One page reference per line.")
    skip_page_refs = fields.Text(help="One page reference per line.")
    max_media = fields.Integer(default=2000)
    page_ids = fields.One2many("dolibarr.website.import.page", "import_id")
    line_ids = fields.One2many("dolibarr.website.import.line", "import_id")
    map_ids = fields.One2many("dolibarr.website.import.map", "last_import_id")
    state = fields.Selection(
        STATES, default="draft", required=True, tracking=True
    )
    phase = fields.Selection(
        [("analyse", "Analysis"), ("import", "Import")], default="analyse"
    )
    import_done = fields.Boolean(readonly=True)
    date_start = fields.Datetime(readonly=True)
    date_end = fields.Datetime(readonly=True)
    error = fields.Text(readonly=True)
    dolibarr_version = fields.Char(readonly=True)
    main_lang = fields.Char(readonly=True)
    other_langs = fields.Char(readonly=True)
    langs_source = fields.Char(readonly=True)
    site_script_count = fields.Integer(string="Site Scripts", readonly=True)
    site_script_detail = fields.Char(
        string="Site Script Detail", readonly=True
    )
    page_count = fields.Integer(compute="_compute_counters")
    post_count = fields.Integer(compute="_compute_counters")
    media_count = fields.Integer(compute="_compute_counters")
    redirect_count = fields.Integer(compute="_compute_counters")
    warning_count = fields.Integer(compute="_compute_counters")
    error_count = fields.Integer(compute="_compute_counters")
    foreign_proposed = fields.Integer(compute="_compute_counters")
    foreign_imported = fields.Integer(compute="_compute_counters")
    foreign_skipped = fields.Integer(compute="_compute_counters")
    php_translated_count = fields.Integer(compute="_compute_counters")
    php_removed_count = fields.Integer(compute="_compute_counters")
    scripts_kept_count = fields.Integer(compute="_compute_counters")

    @api.depends("website_id.name", "source_key", "zip_filename")
    def _compute_name(self):
        for run in self:
            run.name = "%s / %s" % (
                run.website_id.name or "",
                run.source_key or run.zip_filename or "",
            )

    def _compute_counters(self):
        Map = self.env["dolibarr.website.import.map"]
        for run in self:
            touched = Map.search([("last_import_id", "=", run.id)])
            codes = run.line_ids.mapped("code")
            foreign = run.page_ids.filtered(
                lambda page: page.status == "foreign_unlinked"
            )
            kinds = touched.mapped("kind")
            run.page_count = kinds.count("page")
            run.post_count = kinds.count("post")
            run.media_count = kinds.count("media")
            run.redirect_count = kinds.count("redirect")
            severities = run.line_ids.mapped("severity")
            run.warning_count = severities.count("warning")
            run.error_count = severities.count("error")
            run.foreign_proposed = len(foreign)
            run.foreign_imported = codes.count("foreign_lang_page")
            run.foreign_skipped = codes.count("foreign_lang_skipped")
            plans = run.page_ids.mapped("php_plan")
            run.php_translated_count = plans.count("translated")
            run.php_removed_count = plans.count("remove")
            run.scripts_kept_count = codes.count("script_kept")

    def _check_import_access(self):
        """Gate of the action methods.

        Requires a system administrator, the superuser or a sudo
        environment (the command line). It is unrelated to the ORM's own
        _check_access(operation) hook, which the model inherits untouched.
        """
        if not self.env.su and not self.env.user.has_group(
            "base.group_system"
        ):
            raise AccessError(
                self.env._("Only system administrators can import websites.")
            )

    @staticmethod
    def _refs(text):
        """Page references of a one-per-line text field, blanks dropped."""
        return [
            line.strip() for line in (text or "").splitlines() if line.strip()
        ]

    def _add_line(self, found, record=None):
        """Store one engine finding as a report line.

        The finding is site-level when its page_ref is empty or names a
        site file; either way the reference is kept as text and never
        looked up as a page.
        """
        self.ensure_one()
        template = messages.TEMPLATES[found.code][1]
        env = self.env
        if self.lang:
            env = env(context=dict(env.context, lang=self.lang))
        try:
            message = env._(template, **found.params)
        except (KeyError, ValueError, TypeError):
            message = messages.render(found.code, found.params)
        return self.env["dolibarr.website.import.line"].create(
            {
                "import_id": self.id,
                "severity": found.severity,
                "code": found.code,
                "phase": self.phase or "analyse",
                "page_ref": found.page_ref,
                "lang": found.lang,
                "url": found.url,
                "message": message,
                "detail": (found.detail or "")[:300],
                "res_model": record._name if record else False,
                "res_id": record.id if record else False,
            }
        )

    def _last_import_run(self):
        """Latest other run of this (website, key) that finished importing."""
        self.ensure_one()
        return self.search(
            [
                ("website_id", "=", self.website_id.id),
                ("source_key", "=", self.source_key),
                ("import_done", "=", True),
                ("id", "!=", self.id),
            ],
            order="id desc",
            limit=1,
        )

    def _imported_refs(self):
        """Pages and posts that the last import run touched."""
        last = self._last_import_run()
        if not last:
            return set()
        maps = self.env["dolibarr.website.import.map"].search(
            [
                ("website_id", "=", self.website_id.id),
                ("source_key", "=", self.source_key),
                ("kind", "in", ("page", "post")),
                ("last_import_id", "=", last.id),
            ]
        )
        return set(maps.mapped("ref"))

    def _filter_site(self, site):
        """Extension point: the last word on the Site before writing."""
        return site

    # Orchestration

    @api.model_create_multi
    def create(self, vals_list):
        """A run is created as a draft unless STATE_CONTEXT is set."""
        for vals in vals_list:
            if vals.get("state", "draft") != "draft":
                self._check_state_context()
        return super().create(vals_list)

    def write(self, vals):
        """state changes only through the orchestration (STATE_CONTEXT);
        keep_scripts is decided at the review step, after the script
        list, and nowhere else; creation is not concerned."""
        if "state" in vals and any(run.state != vals["state"] for run in self):
            self._check_state_context()
        if "keep_scripts" in vals:
            for run in self:
                if run.state != "to_review" and bool(
                    vals["keep_scripts"]
                ) != bool(run.keep_scripts):
                    raise UserError(
                        self.env._(
                            "Keep scripts can only change while the import"
                            " waits for review."
                        )
                    )
        return super().write(vals)

    def _check_state_context(self):
        if not self.env.context.get(STATE_CONTEXT):
            raise UserError(
                self.env._("The state of an import changes by its actions.")
            )

    def _set_state(self, vals):
        """write() of vals, state included, by the orchestration."""
        return self.with_context(**{STATE_CONTEXT: True}).write(vals)

    def _zip_bytes(self, analyse=False):
        """The stored zip; raises SourceError when the run has none.

        The analysis records the zip's sha256, replacing any older one;
        the import raises SourceError when the zip no longer matches it.
        """
        stored = self.with_context(bin_size=False).zip_file
        data = base64.b64decode(stored or b"")
        if not data:
            raise SourceError("the run has no zip file")
        digest = hashlib.sha256(data).hexdigest()
        if analyse:
            self.zip_sha256 = digest
        elif self.zip_sha256 != digest:
            raise SourceError(
                "the stored zip changed since its analysis;"
                " use Reimport or Start over to analyse it again"
            )
        return data

    def _css_hosts(self):
        """Hosts of the css_hosts parameter, comma separated, or the
        engine's default list when the parameter is empty."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(PARAM + "css_hosts")
        )
        if not value:
            return Options().css_hosts
        return [host.strip() for host in value.split(",") if host.strip()]

    def _zip_limits(self):
        """ZipLimits overrides from the zip_<limit> parameters; a value
        that is not a plain integer is ignored."""
        params = self.env["ir.config_parameter"].sudo()
        limits = {}
        for field in dataclasses.fields(ZipLimits):
            value = (
                params.get_param(PARAM + "zip_" + field.name) or ""
            ).strip()
            if value.isdigit():
                limits[field.name] = int(value)
        return limits

    def _engine_options(self):
        """Engine Options of this run.

        langs_dir comes from the context, and only in a superuser
        environment (the command): no interface can set a server path.
        """
        return Options(
            filename=self.zip_filename or "",
            source_key=self.source_key or "",
            default_lang=self.website_id.default_lang_id.code or "en_US",
            keep_scripts=self.keep_scripts,
            style_blog_posts=self.style_blog_posts,
            include_unlinked_langs=self.include_unlinked_langs,
            include_page_refs=self._refs(self.include_page_refs),
            skip_page_refs=self._refs(self.skip_page_refs),
            langs_dir=(
                self.env.su and self.env.context.get("dolibarr_langs_dir")
            )
            or "",
            css_hosts=self._css_hosts(),
            zip_limits=self._zip_limits(),
        )

    def _check_no_running_other(self):
        """UserError when another run of this (website, key) is running."""
        self.ensure_one()
        busy = self.search_count(
            [
                ("website_id", "=", self.website_id.id),
                ("source_key", "=", self.source_key),
                ("state", "=", "running"),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if busy:
            raise UserError(
                self.env._(
                    "Another import of %(key)s into this website is running.",
                    key=self.source_key,
                )
            )

    @api.model
    def _create_from_cli(self, opts):
        """A draft run for the command line and odoo shell.

        Private: the command runs it as the superuser, so it must never be
        callable over RPC. The zip comes from opts["zip_bytes"] or is read
        from opts["zip_path"] under the size limit, as a regular file only.
        The run never stops for review. It is a draft; the caller starts
        it through the orchestration (_set_state, then _process).
        """
        self._check_import_access()
        website = self.env["website"].browse(opts["website_id"]).exists()
        if not website:
            raise UserError(
                self.env._("Website %s not found.", opts["website_id"])
            )
        data = opts.get("zip_bytes")
        if not data:
            data = zipsource.read_zip_file(
                opts["zip_path"],
                ZipLimits.from_options(self._zip_limits()).max_total,
            )
        filename = opts.get("zip_filename") or os.path.basename(
            opts.get("zip_path") or ""
        )
        key = opts.get("source_key") or zipsource.key_from_filename(filename)
        if not key:
            raise UserError(
                self.env._(
                    "The file name carries no source key; give --source-key."
                )
            )
        if not valid_key(key):
            raise UserError(self.env._("Invalid source key %s.", key))
        lang = opts.get("lang") or website.default_lang_id.code
        if not self.env["res.lang"].search_count(
            [("code", "=", lang), ("active", "=", True)], limit=1
        ):
            raise UserError(self.env._("Language %s is not active.", lang))
        return self.create(
            {
                "website_id": website.id,
                "zip_file": base64.b64encode(data),
                "zip_filename": filename,
                "source_key": key,
                "lang": lang,
                "blog_name": opts.get("blog_name") or "Blog",
                "import_menu": opts.get("import_menu", True),
                "set_homepage": opts.get("set_homepage", True),
                "style_blog_posts": opts.get("style_blog_posts", True),
                "keep_scripts": opts.get("keep_scripts", False),
                "max_media": opts.get("max_media", 2000),
                "include_page_refs": "\n".join(
                    opts.get("include_page_refs") or []
                ),
                "skip_page_refs": "\n".join(opts.get("skip_page_refs") or []),
                "include_unlinked_langs": opts.get(
                    "include_unlinked_langs", False
                ),
                "overwrite_local_edits": opts.get(
                    "overwrite_local_edits", False
                ),
                "analyse_only": opts.get("analyse_only", False),
                "review_before_import": False,
            }
        )

    def _report_dict(self):
        """Header, counters, lines and analysis rows, for --report-json."""
        self.ensure_one()
        rows = (
            "ref", "lang", "source_url", "target_url", "status", "include",
            "imported_before", "php_plan", "php_unknown_blocks",
            "php_removed_bytes", "script_count",
        )  # fmt: skip
        return {
            "run": {
                "id": self.id,
                "state": self.state,
                "website_id": self.website_id.id,
                "source_key": self.source_key,
                "zip_filename": self.zip_filename or "",
                "zip_sha256": self.zip_sha256 or "",
                "dolibarr_version": self.dolibarr_version or "",
                "main_lang": self.main_lang or "",
                "other_langs": self.other_langs or "",
                "langs_source": self.langs_source or "",
                "site_script_count": self.site_script_count,
                "site_script_detail": self.site_script_detail or "",
                "date_start": str(self.date_start or ""),
                "date_end": str(self.date_end or ""),
                "error": self.error or "",
            },
            "counters": {
                name: self[name]
                for name in (
                    "page_count", "post_count", "media_count",
                    "redirect_count", "warning_count", "error_count",
                    "foreign_proposed", "foreign_imported",
                    "foreign_skipped", "php_translated_count",
                    "php_removed_count", "scripts_kept_count",
                )
            },  # fmt: skip
            "lines": [
                {
                    "severity": line.severity,
                    "code": line.code,
                    "page_ref": line.page_ref or "",
                    "lang": line.lang or "",
                    "url": line.url or "",
                    "message": line.message or "",
                    "detail": line.detail or "",
                    "res_model": line.res_model or "",
                    "res_id": line.res_id or 0,
                }
                for line in self.line_ids
            ],
            "pages": [
                {
                    name: (
                        (row[name] or "") if name in _ROW_CHARS else row[name]
                    )
                    for name in rows
                }
                for row in self.page_ids
            ],
        }

    def _process(self, budget=None):
        """One batch; returns (done, remaining).

        The analysis phase is followed by a stop for review, an
        analyse-only end, or the import phase in the same call. A spent
        budget raises BudgetExhausted in the writer: what was written so
        far stays, each record with its map line, the phase stays import
        and the next batch resumes it, since every upsert is idempotent.
        A SourceError fails the run. The state is left to the caller
        until the run ends.
        """
        self.ensure_one()
        self._check_import_access()
        run = self.with_context(lang=self.lang or self.env.lang or "en_US")
        deadline = time.monotonic() + budget if budget is not None else None
        try:
            if run.phase != "import":
                run._run_analyse()
                if run.review_before_import:
                    run._set_state({"state": "to_review"})
                    run._post_analysis_message()
                    return 1, 0
                if run.analyse_only:
                    run._finish()
                    return 1, 0
                run.phase = "import"
            run._run_import(deadline)
            return 1, 0
        except BudgetExhausted:
            return 0, 1
        except SourceError as exc:
            run._fail(error_text(exc))
            return 0, 0

    def _run_analyse(self):
        """Analysis rows and report lines, rebuilt from scratch.

        The rows are deleted and created again, never written: the
        include of a row changes only while the run waits for review.
        """
        opts = self._engine_options()
        site = pipeline.build_from_zip(self._zip_bytes(analyse=True), opts)
        self.page_ids.unlink()
        self.line_ids.unlink()
        rows = pipeline.analyse(site, opts, self._imported_refs())
        writer = self._writer()
        values = []
        for row in rows:
            vals = dict(row.to_json(), import_id=self.id)
            if row.kind == "page" and row.target_url:
                line = writer._map_line("page", row.ref)
                own = writer._line_record("page", line, "website.page")
                try:
                    vals["target_url"] = (
                        own.url if own else writer._target_url(row.ref)[0]
                    )
                except UrlUnavailable:
                    vals["target_url"] = ""
            values.append(vals)
        self.env["dolibarr.website.import.page"].create(values)
        for item in pipeline.all_findings(site):
            self._add_line(item)
        website_lang = primary_lang(self.website_id.default_lang_id.code)
        if site.main_lang and website_lang and site.main_lang != website_lang:
            self._add_line(
                finding(
                    "language_mismatch",
                    source=site.main_lang,
                    website=website_lang,
                )
            )
        self.write(
            {
                "dolibarr_version": site.dolibarr_version,
                "main_lang": site.main_lang,
                "other_langs": ",".join(site.other_langs),
                "langs_source": site.langs_source,
                "site_script_count": site.site_script_count,
                "site_script_detail": site.site_script_detail,
            }
        )

    def _apply_page_choices(self, site):
        """Site without the pages in another language left unchecked."""
        choices = [
            PageChoice(row.ref, row.include)
            for row in self.page_ids
            if row.status == "foreign_unlinked"
        ]
        return pipeline.apply_choices(site, choices)

    def _run_import(self, deadline):
        """Rebuild the Site from the stored zip, apply the choices and
        _filter_site, then run the writer.

        The import lines of an earlier batch are deleted first, since this
        batch emits them again, except the ONE_TIME_CODES lines: a resumed
        import thus reports each finding once, like a single batch.
        """
        self._check_no_running_other()
        self.line_ids.filtered(
            lambda line: line.phase == "import"
            and line.code not in ONE_TIME_CODES
        ).unlink()
        opts = self._engine_options()
        data = self._zip_bytes()
        source = zipsource.open_zip(data, opts)
        site = pipeline.build_from_zip(data, opts, source=source)
        base = len(site.findings)
        site = self._filter_site(self._apply_page_choices(site))
        for item in site.findings[base:]:
            self._add_line(item)
        self._writer()._write_site(site, source, opts, deadline)
        self._finish()

    def _finish(self):
        """done, with import_done after an import, and a summary post."""
        vals = {"state": "done", "date_end": fields.Datetime.now()}
        if self.phase == "import":
            vals["import_done"] = True
        self._set_state(vals)
        if self.phase != "import":
            self._post_analysis_message()
            return
        self.message_post(
            body=self.env._(
                "Import finished: %(pages)s pages, %(posts)s posts,"
                " %(media)s media, %(warnings)s warnings, %(errors)s errors.",
                pages=self.page_count,
                posts=self.post_count,
                media=self.media_count,
                warnings=self.warning_count,
                errors=self.error_count,
            )
        )

    def _fail(self, error, code="source_error"):
        """failed, with the error on the run and a line of code:
        source_error for a SourceError, run_error for any other error."""
        self._set_state(
            {
                "state": "failed",
                "error": error[:2000],
                "date_end": fields.Datetime.now(),
            }
        )
        self._add_line(finding(code, error=error[:250]))

    def _post_analysis_message(self):
        """Message that tells the creator the analysis is finished."""
        rows = self.page_ids
        self.message_post(
            body=self.env._(
                "Analysis finished: %(pages)s pages; %(waiting)s pages in"
                " another language await a choice.",
                pages=len(rows.filtered(lambda r: r.status == "import")),
                waiting=len(
                    rows.filtered(lambda r: r.status == "foreign_unlinked")
                ),
            ),
            partner_ids=self.create_uid.partner_id.ids,
        )

    def _run_inline(self, budget):
        """One batch in a savepoint; returns (done, remaining).

        An exception undoes the batch and fails the run with a short
        message from error_text(); the traceback goes to the server log
        only.
        """
        try:
            with self.env.cr.savepoint():
                return self._process(budget=budget)
        except Exception as exc:
            _logger.exception("Dolibarr website import %s failed", self.id)
            self._fail(error_text(exc), code="run_error")
            return 0, 0

    def _form_action(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_start(self):
        """Start the analysis, inline with INLINE_BUDGET.

        Only a draft starts: an analysed, stopped or finished run keeps
        its rows and report, and continues through action_resume.
        """
        self._check_import_access()
        if any(run.state != "draft" for run in self):
            raise UserError(self.env._("Only a draft import can be started."))
        for run in self:
            run._check_no_running_other()
            run._set_state(
                {
                    "state": "running",
                    "phase": "analyse",
                    "date_start": fields.Datetime.now(),
                    "date_end": False,
                    "error": False,
                }
            )
            run._run_inline(INLINE_BUDGET)
        return self[:1]._form_action()

    def action_import(self):
        """Import a run that waits for review, inline with INLINE_BUDGET."""
        self._check_import_access()
        self.ensure_one()
        if self.state != "to_review":
            raise UserError(
                self.env._("Only an analysed import can be imported.")
            )
        self._check_no_running_other()
        self._set_state({"state": "running", "phase": "import"})
        self._run_inline(INLINE_BUDGET)
        return self._form_action()

    def action_resume(self):
        """A run cancelled at review returns to review; a failed,
        cancelled or unfinished run continues its phase."""
        self._check_import_access()
        self.ensure_one()
        if (
            self.state == "cancelled"
            and self.phase == "analyse"
            and self.review_before_import
            and self.page_ids
        ):
            self._set_state({"state": "to_review"})
        elif self.state in ("failed", "cancelled", "running"):
            self._check_no_running_other()
            self._set_state({"state": "running", "error": False})
            self._run_inline(INLINE_BUDGET)
        return self._form_action()

    def action_cancel(self):
        """Cancel the runs that are not done; rows and lines stay."""
        self._check_import_access()
        self.filtered(lambda run: run.state != "done")._set_state(
            {"state": "cancelled"}
        )
        return self[:1]._form_action()

    def action_start_over(self):
        """The wizard, filled in from this run."""
        self._check_import_access()
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "dolibarr.website.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"dolibarr_import_from_run": self.id},
        }

    def action_reimport(self):
        """New run with the same source, options and page choices.

        Checked rows go to include_page_refs, unchecked foreign rows to
        skip_page_refs; overwrite_local_edits and keep_scripts start
        unchecked, and the new run is analysed and reviewed again.
        """
        self._check_import_access()
        self.ensure_one()
        foreign = self.page_ids.filtered(
            lambda r: r.status == "foreign_unlinked"
        )
        new = self.create(
            {
                "website_id": self.website_id.id,
                "zip_file": self.with_context(bin_size=False).zip_file,
                "zip_filename": self.zip_filename,
                "source_key": self.source_key,
                "blog_name": self.blog_name,
                "lang": self.lang,
                "import_menu": self.import_menu,
                "set_homepage": self.set_homepage,
                "style_blog_posts": self.style_blog_posts,
                "max_media": self.max_media,
                "review_before_import": True,
                "include_unlinked_langs": self.include_unlinked_langs,
                "include_page_refs": "\n".join(
                    foreign.filtered("include").mapped("ref")
                ),
                "skip_page_refs": "\n".join(
                    foreign.filtered(lambda r: not r.include).mapped("ref")
                ),
            }
        )
        new.action_start()
        return new._form_action()

    def action_open_website(self):
        self._check_import_access()
        self.ensure_one()
        website = self.website_id
        return {
            "type": "ir.actions.act_url",
            "url": website.get_base_url() + (website.homepage_url or "/"),
            "target": "new",
        }

    def action_open_blog(self):
        """The blog of this (website, key), or the website's blog list."""
        self._check_import_access()
        self.ensure_one()
        writer = self._writer()
        blog = writer._line_record(
            "blog", writer._map_line("blog", ""), "blog.blog"
        )
        path = "/blog"
        if blog:
            path = "/blog/%s" % self.env["ir.http"]._slug(blog)
        return {
            "type": "ir.actions.act_url",
            "url": self.website_id.get_base_url() + path,
            "target": "new",
        }
