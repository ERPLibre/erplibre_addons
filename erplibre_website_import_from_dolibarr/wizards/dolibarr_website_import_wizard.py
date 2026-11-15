# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Step 1 of the import: choose the source and the options, then analyse.

Steps 2 to 4 (analysis, review, import) happen on the run record, which
outlives this transient record and keeps the page choices for Reimport.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..dolibarr_site.model import valid_key
from ..dolibarr_site.zipsource import key_from_filename

# Run fields that the wizard copies from a run and to a run.
COPIED = (
    "zip_filename",
    "source_key",
    "blog_name",
    "import_menu",
    "set_homepage",
    "style_blog_posts",
    "overwrite_local_edits",
)


class DolibarrWebsiteImportWizard(models.TransientModel):
    _name = "dolibarr.website.import.wizard"
    _description = "Import a website from Dolibarr"

    website_id = fields.Many2one(
        "website",
        required=True,
        default=lambda self: self.env["website"].get_current_website(),
    )
    zip_file = fields.Binary(string="Export zip")
    zip_filename = fields.Char()
    source_key = fields.Char(
        compute="_compute_source_key", store=True, readonly=False
    )
    previous_key = fields.Char(compute="_compute_previous_key")
    blog_name = fields.Char(default="Blog")
    import_menu = fields.Boolean(default=True)
    set_homepage = fields.Boolean(default=True)
    style_blog_posts = fields.Boolean(default=True)
    overwrite_local_edits = fields.Boolean(
        help="Replace the changes made in Odoo since the last import."
    )

    @api.depends("zip_filename")
    def _compute_source_key(self):
        for wizard in self:
            wizard.source_key = (
                key_from_filename(wizard.zip_filename or "")
                or wizard.source_key
            )

    @api.depends("website_id", "source_key")
    def _compute_previous_key(self):
        """Key of the latest run into the website, when it differs."""
        Run = self.env["dolibarr.website.import"]
        for wizard in self:
            last = Run.search(
                [("website_id", "=", wizard.website_id.id)],
                order="id desc",
                limit=1,
            )
            wizard.previous_key = (
                last.source_key
                if last and last.source_key != wizard.source_key
                else False
            )

    @api.model
    def default_get(self, fields_list):
        """Copy a run when the context names one (Start over)."""
        values = super().default_get(fields_list)
        run_id = self.env.context.get("dolibarr_import_from_run")
        if run_id:
            run = self.env["dolibarr.website.import"].browse(run_id)
            run._check_import_access()
            values["website_id"] = run.website_id.id
            values["zip_file"] = run.with_context(bin_size=False).zip_file
            for name in COPIED:
                values[name] = run[name]
        return values

    def action_analyse(self):
        """Create the run, analyse it, and open it on its review step.

        A transient model is reachable by RPC, so the group is checked
        here as well as by the access rules.
        """
        self.ensure_one()
        Run = self.env["dolibarr.website.import"]
        Run._check_import_access()
        if not self.source_key:
            raise UserError(
                self.env._(
                    "Give the source key of the site; the zip file name"
                    " does not carry one."
                )
            )
        if not valid_key(self.source_key):
            raise UserError(
                self.env._(
                    "The source key %(key)s is not valid: use letters,"
                    " digits, dot, dash and underscore.",
                    key=self.source_key,
                )
            )
        if not self.zip_file:
            raise UserError(self.env._("Choose a Dolibarr export zip."))
        run = Run.create(
            {
                "website_id": self.website_id.id,
                "zip_file": self.zip_file,
                "lang": self.env.lang or self.env.user.lang,
                "review_before_import": True,
                **{name: self[name] for name in COPIED},
            }
        )
        return run.action_start()
