# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.mail_linkup_reflet.models.linkup_report import OPEN_STATES

COLLUSION_DAYS_PARAM = "linkup.collusion_days"
PAIR_CONFIRMATIONS_PARAM = "linkup.collusion_pair_confirmations"
NEW_ACCOUNT_CONFIRMATIONS_PARAM = "linkup.collusion_new_account_confirmations"
NEW_ACCOUNT_HOURS_PARAM = "linkup.collusion_new_account_hours"
DEFAULT_COLLUSION_DAYS = 7
DEFAULT_PAIR_CONFIRMATIONS = 3
DEFAULT_NEW_ACCOUNT_CONFIRMATIONS = 5
DEFAULT_NEW_ACCOUNT_HOURS = 48


class LinkupReport(models.Model):
    _inherit = "linkup.report"

    reason = fields.Selection(
        selection_add=[
            ("confirmation_loop", "Confirmations in a loop"),
            ("new_account_confirmations", "Confirmations of new accounts"),
        ],
        ondelete={
            "confirmation_loop": "cascade",
            "new_account_confirmations": "cascade",
        },
    )

    @api.model
    def _linkup_check_collusion(self, reflet):
        """Alert the moderators of a confirmation that looks like collusion
        (§7.3).

        Over the last ``linkup.collusion_days`` days (7): a pair that
        confirmed more than ``linkup.collusion_pair_confirmations`` (3)
        initial reflections reports both of its members; a member who
        confirmed more than ``linkup.collusion_new_account_confirmations``
        (5) reflections of accounts younger than
        ``linkup.collusion_new_account_hours`` (48) at the confirmation
        reports that member. Each report is created once while it is open,
        and sanctions nobody.
        """
        param = self.env["linkup.reflet"]._linkup_param
        days = param(COLLUSION_DAYS_PARAM, DEFAULT_COLLUSION_DAYS)
        since = fields.Datetime.now() - timedelta(days=days)
        Reflet = self.env["linkup.reflet"].sudo()
        pair_count = Reflet.search_count(
            [
                ("link_id", "=", reflet.link_id.id),
                ("kind", "=", "initial"),
                ("state", "=", "confirmed"),
                ("answered_date", ">=", since),
            ]
        )
        if pair_count > param(
            PAIR_CONFIRMATIONS_PARAM, DEFAULT_PAIR_CONFIRMATIONS
        ):
            for user in reflet.author_id | reflet.recipient_id:
                self._linkup_auto_report(user, "confirmation_loop")
        Reflet.flush_model(
            ["recipient_id", "author_id", "kind", "state", "answered_date"]
        )
        self.env["res.users"].flush_model(["create_date"])
        self.env.cr.execute(
            """
            SELECT COUNT(*) FROM linkup_reflet reflet
            JOIN res_users author ON author.id = reflet.author_id
            WHERE reflet.recipient_id = %s
              AND reflet.kind = 'initial'
              AND reflet.state = 'confirmed'
              AND reflet.answered_date >= %s
              AND author.create_date
                  > reflet.answered_date - make_interval(hours => %s)
            """,
            [
                reflet.recipient_id.id,
                since,
                param(NEW_ACCOUNT_HOURS_PARAM, DEFAULT_NEW_ACCOUNT_HOURS),
            ],
        )
        if self.env.cr.fetchone()[0] > param(
            NEW_ACCOUNT_CONFIRMATIONS_PARAM, DEFAULT_NEW_ACCOUNT_CONFIRMATIONS
        ):
            self._linkup_auto_report(
                reflet.recipient_id, "new_account_confirmations"
            )

    @api.model
    def _linkup_auto_report(self, user, reason):
        """Report ``user`` for ``reason``, unless such a report is open."""
        Report = self.sudo()
        if Report.search_count(
            [
                ("reported_user_id", "=", user.id),
                ("reason", "=", reason),
                ("state", "in", OPEN_STATES),
            ]
        ):
            return Report
        return Report.create(
            {
                "reported_user_id": user.id,
                "reason": reason,
                "auto_generated": True,
            }
        )
