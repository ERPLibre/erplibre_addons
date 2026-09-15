# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
from unittest import mock

from odoo.tests.common import TransactionCase


class TestConstructionMatcher(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env = self.env(
            context=dict(self.env.context, queue_job__no_delay=True)
        )
        patcher = mock.patch(
            "odoo.addons.mail.tools.mail_validation.mail_validate",
            return_value=True,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ticket_matched_to_chantier(self):
        chantier = self.env["project.project"].create(
            {
                "name": "Chantier A",
                "is_chantier": True,
                "no_chantier": "CH-2026-99",
            }
        )
        team = self.env["helpdesk.ticket.team"].create({"name": "QC"})
        # helpdesk.ticket.description is a required Html field.
        matched = self.env["helpdesk.ticket"].create(
            {
                "name": "Problème sur CH-2026-99 urgent",
                "description": "<p>Voir chantier</p>",
                "team_id": team.id,
            }
        )
        other = self.env["helpdesk.ticket"].create(
            {
                "name": "Question generale",
                "description": "<p>rien</p>",
                "team_id": team.id,
            }
        )
        opted_out = self.env["helpdesk.ticket"].create(
            {
                "name": "CH-2026-99 mais ignore",
                "description": "<p>x</p>",
                "team_id": team.id,
                "ignore_associate_chantier": True,
            }
        )
        transform = self.env["sync.data.transform"].create({})
        transform.action_match_chantier_tickets()
        self.assertEqual(matched.chantier_project_id, chantier)
        self.assertFalse(other.chantier_project_id)
        self.assertFalse(opted_out.chantier_project_id)
