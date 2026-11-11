# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

MANAGER_GROUP = "erplibre_streamdeck.group_streamdeck_manager"
TODO = "mail.mail_activity_data_todo"

# Le deck naît chez A, passe chez B, puis C remonte un événement qui porte
# son numéro de série.
DAY_A = datetime(2026, 5, 1, 10, 0, 0)
DAY_B = datetime(2026, 5, 2, 10, 0, 0)
DAY_C = datetime(2026, 5, 3, 10, 0, 0)


@tagged("post_install", "-at_install")
class TestStreamdeckMonitorThread(TransactionCase):
    """Le fil des postes et des decks, où la surveillance pose ses
    activités et ses notes : qui le lit, qui le modifie.

    A, B et C sont trois employés, M le gestionnaire. Les remontées passent
    par le service, comme les routes, l'heure du serveur figée à chacune.
    Les notes et les activités sont posées en superutilisateur, comme le
    cron les posera.
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

    DECK = {
        "serial": "SN-THREAD",
        "usb_product_id": "0084",
        "usb_path": "1-2",
        "firmware": None,
    }

    def _report(self, token, moment, decks=True, events=()):
        """Une remontée à `moment` : le deck dans l'état si `decks`."""
        with freeze_time(moment):
            status, body = self.Service.report(
                token,
                {
                    "protocol": "1.0",
                    "state": {
                        "hostname": "host",
                        "os": {"name": "Debian GNU/Linux", "version": "13"},
                        "service_state": "active",
                        "decks": [self.DECK] if decks else [],
                    },
                    "events": list(events),
                    "lost_events": 0,
                },
            )
        self.assertEqual(status, 200, body)

    def _device(self):
        return self.env["streamdeck.device"].search(
            [("key", "=", "sn:SN-THREAD")]
        )

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

    def _activity(self, record, moment, user, summary):
        """Une activité de `record` pour `user`, créée à `moment`. L'ORM
        date `create_date` du début de la transaction, que freeze_time ne
        déplace pas : la date est posée en SQL."""
        activity = record.activity_schedule(
            TODO, user_id=user.id, summary=summary
        )
        activity.flush_recordset()
        self.env.cr.execute(
            "UPDATE mail_activity SET create_date = %s WHERE id = %s",
            (moment, activity.id),
        )
        activity.invalidate_recordset(["create_date"])
        return activity

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

    def test_a_new_holder_reads_the_deck_thread_from_their_arrival(self):
        # Le fil du deck suit la borne de son historique : B ne lit ni
        # note ni activité d'avant son arrivée, sauf une activité qui lui
        # est assignée ; A, le prêteur, et M lisent tout ; C, dont un
        # événement porte le numéro du deck sans le détenir, lit le deck
        # et rien de son fil.
        self._report(self.token_a, DAY_A)
        device = self._device()
        before = DAY_A.replace(hour=12)
        after = DAY_B.replace(hour=12)
        note_before = self._note(device, before, "Unplugged for long")
        act_before = self._activity(
            device, before, self.user_a, "Deck unplugged for long"
        )
        for_b_before = self._activity(
            device, before, self.user_b, "Assigned to B"
        )
        self._report(self.token_b, DAY_B)
        note_after = self._note(device, after, "Changed workstation")
        act_after = self._activity(
            device, after, self.manager, "Deck changed workstation"
        )
        plugged = {
            "uuid": "00000000-0000-4000-8000-000000000001",
            "kind": "plugged",
            "at": DAY_C.isoformat() + "Z",
            "serial": self.DECK["serial"],
            "usb_product_id": self.DECK["usb_product_id"],
            "usb_path": self.DECK["usb_path"],
        }
        self._report(self.token_c, DAY_C, decks=False, events=[plugged])
        notes = note_before | note_after
        activities = act_before | for_b_before | act_after
        expected = {
            self.user_a: (notes, activities),
            self.manager: (notes, activities),
            self.user_b: (note_after, for_b_before | act_after),
            self.user_c: (notes.browse(), activities.browse()),
        }
        for user, (read_notes, read_activities) in expected.items():
            with self.subTest(user=user.name):
                # Le cache des x2many est commun aux utilisateurs : il est
                # vidé comme au début d'une requête.
                self.env.invalidate_all()
                as_user = device.with_user(user)
                self.assertEqual(as_user.message_ids & notes, read_notes)
                self.assertEqual(
                    as_user.activity_ids & activities, read_activities
                )
                hidden = list(notes - read_notes) + list(
                    activities - read_activities
                )
                for record in hidden:
                    with self.assertRaises(AccessError):
                        record.with_user(user).read(["create_date"])
        # Le fil d'un autre modèle ne change pas : B lit celui de son poste.
        own = self._note(self.workstation_b, after, "On host-b")
        self.env.invalidate_all()
        self.assertIn(
            own, self.workstation_b.with_user(self.user_b).message_ids
        )
