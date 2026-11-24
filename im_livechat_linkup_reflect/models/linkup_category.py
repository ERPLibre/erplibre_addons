# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models

# Fields of a category that the answers of the guide follow.
ANSWER_FIELDS = frozenset({"name", "active", "sequence"})

# Fields of a category the widget reads, those the web client of
# ``mail_linkup_reflet`` reads (``LINKUP_CATEGORY_FIELDS``).
PUBLIC_FIELDS = [
    "code",
    "name",
    "definition",
    "example_do",
    "example_dont",
    "reflet_title",
    "starter_self",
    "starter_reflect",
    "sequence",
    "in_reflet_bar",
    "reflet_bar_sequence",
    "is_cnv",
]


class LinkupCategory(models.Model):
    """The answers of the category step of the guide follow the
    categories: a new, renamed, reordered or archived category changes
    them at once."""

    _inherit = "linkup.category"

    @api.model
    def _linkup_public_categories(self):
        """The active categories as the widget of a visitor reads them, in
        the order of the full band and in the language of the context: the
        texts the welcome chatbot already shows to anybody."""
        categories = self.sudo().search([], order="sequence, id")
        return categories.read(PUBLIC_FIELDS)

    @api.model_create_multi
    def create(self, vals_list):
        categories = super().create(vals_list)
        self.env["chatbot.script.step"]._linkup_sync_category_answers()
        return categories

    def write(self, vals):
        res = super().write(vals)
        if ANSWER_FIELDS.intersection(vals):
            self.env["chatbot.script.step"]._linkup_sync_category_answers()
        return res
