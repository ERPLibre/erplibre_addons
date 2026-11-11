# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
TODO = "mail.mail_activity_data_todo"

DAY_A = datetime(2026, 5, 1, 10, 0, 0)


@tagged("post_install", "-at_install")
class TestStreamdeckMonitorThread(TransactionCase):
    """Le fil des postes et des decks, où la surveillance pose ses
    activités et ses notes : qui le lit, qui le modifie.

    A, B et C sont trois employés, M le gestionnaire. Les notes et les
    activités sont posées en superutilisateur, comme le cron les posera.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["streamdeck.service"]
        cls.user_a, cls.user_b, cls.user_c = (
            new_test_user(
                cls.env,
                login="zz_sd_thread_%s" % seed,
                name="Employee %s" % seed.upper(),
                groups="base.group_user",
            )
            for seed in "abc"
        )
        cls.manager = new_test_user(
            cls.env,
            login="zz_sd_thread_m",
            name="Manager M",
            groups="base.group_user,%s" % MANAGER_GROUP,
        )
        cls.token_a, cls.workstation_a = cls._enroll(cls.user_a, "a")
        cls.token_b, cls.workstation_b = cls._enroll(cls.user_b, "b")
        cls.token_c, cls.workstation_c = cls._enroll(cls.user_c, "c")

    @classmethod
    def _enroll(cls, user, seed):
        code = cls.Service.new_pairing_code(user)
        status, body = cls.Service.enroll(
            {
                "protocol": "1.0",
                "method": "pairing_code",
                "code": code.code,
                "fingerprint": seed * 64,
                "hostname": "host-%s" % seed,
            }
        )
        assert status == 200, body
        workstation = cls.env["streamdeck.workstation"].browse(
            body["workstation_id"]
        )
        return body["token"], workstation

    # -- helpers ---------------------------------------------------------

    def _note(self, record, moment, body):
        """Une note du gestionnaire au fil de `record`, datée de
        `moment`."""
        with freeze_time(moment):
            return record.message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_note",
                author_id=self.manager.partner_id.id,
            )

    # -- tests -----------------------------------------------------------

    def test_an_employee_keeps_the_thread_of_others_on_their_workstation(
        self,
    ):
        # A écrit son poste pour le renommer ; ce droit ne s'étend pas au
        # fil : A ne modifie, ne ferme ni ne supprime une activité ou une
        # note d'un autre. Les siennes restent à A, et le gestionnaire
        # ferme celles de tous.
        workstation = self.workstation_a
        of_manager = workstation.activity_schedule(
            TODO, user_id=self.manager.id, summary="Workstation silent"
        )
        note = self._note(workstation, DAY_A, "Checked by the manager")
        as_a = workstation.with_user(self.user_a)
        self.assertEqual(as_a.activity_ids, of_manager)
        self.assertIn(note, as_a.message_ids)
        as_employee = of_manager.with_user(self.user_a)
        for name, attempt in (
            ("write", lambda: as_employee.write({"summary": "Nothing"})),
            ("unlink", as_employee.unlink),
            ("feedback", lambda: as_employee.action_feedback("Nothing")),
            ("note", note.with_user(self.user_a).unlink),
        ):
            with self.subTest(attempt=name):
                with self.assertRaises(AccessError):
                    attempt()
        self.assertTrue(of_manager.exists().active)
        self.assertTrue(note.exists())
        # Ce que A garde : renommer son poste, fermer sa propre activité.
        as_a.write({"name": "renamed-a"})
        own = workstation.activity_schedule(
            TODO, user_id=self.user_a.id, summary="Deck service failed"
        )
        own.with_user(self.user_a).action_feedback(feedback="Restarted")
        self.assertFalse(own.exists().active)
        # Le gestionnaire ferme l'activité d'un employé.
        of_a = workstation.activity_schedule(
            TODO, user_id=self.user_a.id, summary="Workstation silent"
        )
        of_a.with_user(self.manager).action_feedback(feedback="Seen")
        self.assertFalse(of_a.exists().active)
