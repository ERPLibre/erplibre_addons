# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The context of a client pays no point (LU-NF-001): a rule an
administrator archived pays nothing with ``active_test`` turned off, and
``default_<field>`` keys change no line of the ledger."""

from odoo.tests import tagged

from .common import LinkupPointsCase


@tagged("post_install", "-at_install")
class TestLinkupPointsContext(LinkupPointsCase):
    def test_archived_rule_pays_nothing(self):
        """The rule of the sending, archived, pays nothing at the
        confirmation, whatever the context of the confirmation says."""
        self._rule("reflect_sent").active = False
        reflet = self._sent()
        reflet.with_user(self.france).with_context(
            active_test=False
        ).action_confirm()
        self.assertEqual(
            self._lines(self.sam).rule_id.mapped("code"),
            ["reflect_confirmed"],
        )
        self.assertFalse(
            self.Rule.with_context(active_test=False)._linkup_apply_event(
                "reflect_sent", self.sam, reflet=reflet, key="probe"
            )
        )

    def test_defaults_of_the_context_change_no_line(self):
        """``default_points`` and ``default_capped`` in the context of the
        confirmation leave the scale as it is."""
        reflet = self._sent()
        reflet.with_user(self.france).with_context(
            default_points=99999, default_capped=True
        ).action_confirm()
        self.assertEqual(self.sam.sudo().karma, 1100)
        self.assertEqual(self.france.sudo().karma, 1000)
        self.assertFalse(
            (self._lines(self.sam) | self._lines(self.france)).filtered(
                "capped"
            )
        )
