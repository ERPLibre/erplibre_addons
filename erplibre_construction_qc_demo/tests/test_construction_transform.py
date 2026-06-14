# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from odoo.tests.common import TransactionCase


class TestConstructionTransform(TransactionCase):
    def test_context_sets_no_match_default(self):
        # default_option_no_match is an editable stored computed field with a
        # base default="", so the compute does not fire on create; writing
        # context_name (e.g. selecting it in the UI) triggers it.
        transform = self.env["sync.data.transform"].create({})
        transform.context_name = "QC-CONSTRUCTION - update"
        self.assertIn(
            "ignore_associate_chantier", transform.default_option_no_match
        )

    def test_helpdesk_opt_out_field(self):
        self.assertIn(
            "ignore_associate_chantier",
            self.env["helpdesk.ticket"]._fields,
        )
