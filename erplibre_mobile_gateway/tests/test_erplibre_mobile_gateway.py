# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..tools import signature
from ..tools.sms_api_erplibre import analyse_body, non_gsm7_characters


@tagged("post_install", "-at_install")
class TestErplibreSmsEncoding(TransactionCase):
    """Segmentation et encodage, alignes sur le widget du coeur."""

    def test_gsm7_basic(self):
        self.assertEqual(analyse_body("Le rendez-vous de ce soir est annule"), ("gsm7", 1))

    def test_lowercase_cedilla_forces_ucs2(self):
        """Le piege qui double le temps d'envoi en francais du Quebec.

        `Ç` majuscule est dans l'alphabet GSM 03.38, `ç` minuscule NON. Donc
        « recu », « ca », « lecon », « francais » ecrits avec la cedille font
        tomber le message a 70 caracteres par segment au lieu de 160.
        """
        encoding, _segments = analyse_body("Merci, bien reçu")
        self.assertEqual(encoding, "ucs2")
        self.assertEqual(non_gsm7_characters("reçu"), ["ç"])
        self.assertEqual(analyse_body("ÇA VA")[0], "gsm7")

    def test_accents_in_basic_alphabet(self):
        """Les accents courants du francais, eux, restent en GSM-7."""
        for text in ("annulé", "règle", "à 19h", "où", "ìl"):
            self.assertEqual(analyse_body(text)[0], "gsm7", text)

    def test_segment_boundaries(self):
        self.assertEqual(analyse_body("a" * 160), ("gsm7", 1))
        self.assertEqual(analyse_body("a" * 161), ("gsm7", 2))
        self.assertEqual(analyse_body("ç" * 70), ("ucs2", 1))
        self.assertEqual(analyse_body("ç" * 71), ("ucs2", 2))

    def test_extension_characters_count_double(self):
        """Les caracteres de la table d'extension occupent deux septets."""
        self.assertEqual(analyse_body("€" * 80), ("gsm7", 1))
        self.assertEqual(analyse_body("€" * 81), ("gsm7", 2))

    def test_empty_body(self):
        self.assertEqual(analyse_body("")[1], 0)


@tagged("post_install", "-at_install")
class TestErplibreSmsSignature(TransactionCase):

    def setUp(self):
        super().setUp()
        self.patcher = patch.dict(
            "os.environ", {signature.ENV_HMAC_SECRET: "secret-de-test"}
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_round_trip(self):
        body = json.dumps({"v": 1, "hello": "wörld"}, separators=(",", ":"), ensure_ascii=False)
        header = signature.SIGNATURE_PREFIX + signature.compute(body)
        self.assertTrue(signature.verify(body.encode("utf-8"), header))

    def test_tampered_body_rejected(self):
        body = '{"v":1}'
        header = signature.SIGNATURE_PREFIX + signature.compute(body)
        self.assertFalse(signature.verify(b'{"v":2}', header))
        self.assertFalse(signature.verify(body.encode("utf-8") + b" ", header))

    def test_missing_signature_rejected(self):
        self.assertFalse(signature.verify(b'{"v":1}', ""))
        self.assertFalse(signature.verify(b'{"v":1}', None))

    def test_missing_secret_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(signature.MissingSecret):
                signature.get_hmac_secret()


@tagged("post_install", "-at_install")
class TestErplibreSmsDispatch(TransactionCase):
    """Machine a etats : c'est elle qui empeche le systeme de mentir."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        # Le repli du cron d'expiration resout une passerelle PAR SOCIETE
        # quand l'envoi n'en porte aucune. Une passerelle deja presente dans
        # la base gagnerait ce tri (meme sequence, id plus petit) et
        # recevrait l'alerte a la place de celle du test. La transaction est
        # annulee en fin de test : rien n'est desactive durablement.
        self.env["erplibre.sms.gateway"].search(
            [("company_id", "=", self.company.id)]
        ).write({"active": False})
        self.gateway = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de test",
            "company_id": self.company.id,
        })

    def _dispatch(self, uuid="uuid-0001", state="published", **values):
        return self.env["erplibre.sms.dispatch"].create({
            "sms_uuid": uuid,
            "number": "+15145550123",
            "body": "Cours annule",
            "company_id": self.company.id,
            "gateway_id": self.gateway.id,
            "state": state,
            **values,
        })

    def test_progression(self):
        dispatch = self._dispatch()
        self.assertTrue(dispatch._apply_event("submitted", seq=1))
        self.assertEqual(dispatch.state, "submitted")
        self.assertTrue(dispatch._apply_event("delivered", seq=2))
        self.assertEqual(dispatch.state, "delivered")

    def test_replayed_sequence_ignored(self):
        dispatch = self._dispatch()
        dispatch._apply_event("submitted", seq=1)
        self.assertFalse(dispatch._apply_event("submitted", seq=1))
        self.assertFalse(dispatch._apply_event("delivered", seq=1))

    def test_report_without_sequence_rejected(self):
        """Un rapport non numerote ne peut pas etre ordonne : on le refuse.

        L'accepter rouvrirait la faille que la sequence existe pour fermer.
        `seq=0` doit etre traite comme invalide, et non comme « absent ».
        """
        dispatch = self._dispatch()
        dispatch._apply_event("submitted", seq=1)
        self.assertFalse(dispatch._apply_event("delivered", seq=0))
        self.assertEqual(dispatch.state, "submitted")

    def test_state_regression_ignored(self):
        dispatch = self._dispatch()
        dispatch._apply_event("submitted", seq=1)
        self.assertFalse(dispatch._apply_event("published", seq=9))
        self.assertEqual(dispatch.state, "submitted")

    def test_late_delivered_cannot_overwrite_failed(self):
        """LE test qui compte.

        Le coeur d'Odoo ne protege pas de ce cas : dans
        `sms.tracker._update_sms_notifications`, la liste d'ignorance d'un
        nouveau statut `sent` ne contient que `sent` -- un `sent` tardif ecrase
        donc un `bounce`. Ici, un `delivered` rejoue apres un `failed` ferait
        croire a l'expediteur qu'il a prevenu ses destinataires alors que
        rien recu.
        """
        dispatch = self._dispatch()
        dispatch._apply_event("submitted", seq=1)
        dispatch._apply_event("failed", seq=2, android_code="RESULT_ERROR_NO_SERVICE")
        self.assertEqual(dispatch.state, "failed")
        self.assertFalse(dispatch._apply_event("delivered", seq=3))
        self.assertEqual(dispatch.state, "failed")

    def test_server_originated_event_needs_no_sequence(self):
        dispatch = self._dispatch()
        self.assertTrue(dispatch._apply_event("failed", android_code="GATEWAY_DOWN"))
        self.assertEqual(dispatch.report_seq, 1)

    def test_expire_stale_raises_alarm(self):
        dispatch = self._dispatch(
            send_deadline=fields.Datetime.now() - timedelta(minutes=5),
        )
        self.env["erplibre.sms.dispatch"]._cron_expire_stale()
        dispatch.invalidate_recordset()
        self.assertEqual(dispatch.state, "expired")
        self.assertEqual(dispatch.android_code, "GATEWAY_DEADLINE")
        self.assertTrue(self.gateway.alarm_active)

    def test_expired_without_gateway_spares_other_company(self):
        """Un envoi sans passerelle n'alerte pas celle d'une AUTRE societe.

        Le repli cherchait la premiere passerelle venue, sans filtrer sur la
        societe. Un envoi expire chez A pouvait donc mettre en alerte le
        telephone SAIN de B — et une alerte bloque tous les envois de B. La
        societe est pourtant toujours connue : `company_id` est requis.
        """
        autre_societe = self.env["res.company"].create({"name": "Autre OBNL"})
        # `sequence = 1` place DELIBEREMENT la passerelle de B en tete du tri
        # global `sequence, id`. C'est ce qui rend ce test discriminant :
        # l'ancien repli, qui cherchait sans filtre de societe, tombait alors
        # sur elle. Sans cette sequence, il tombait par hasard sur la bonne
        # passerelle et le test passait aussi sur le code bogue — donc ne
        # prouvait rien.
        passerelle_b = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de B",
            "company_id": autre_societe.id,
            "sequence": 1,
        })
        # L'envoi expire appartient a A et ne porte AUCUNE passerelle : c'est
        # exactement le cas qui declenchait le repli fautif.
        dispatch = self._dispatch(
            uuid="uuid-sans-passerelle",
            gateway_id=False,
            send_deadline=fields.Datetime.now() - timedelta(minutes=5),
        )

        self.env["erplibre.sms.dispatch"]._cron_expire_stale()

        dispatch.invalidate_recordset()
        self.assertEqual(dispatch.state, "expired")
        passerelle_b.invalidate_recordset()
        self.assertFalse(
            passerelle_b.alarm_active,
            "la passerelle d'une autre societe a ete mise en alerte",
        )
        self.assertTrue(
            self.gateway.alarm_active,
            "la passerelle de la societe concernee aurait du etre alertee",
        )

    def test_expired_without_gateway_nor_fallback_is_silent(self):
        """Sans passerelle active dans la societe, on n'alerte personne.

        Choisir une passerelle etrangere pour avoir l'air d'agir serait pire
        que de ne rien faire : le journal le dit, et rien n'est bloque.
        """
        autre_societe = self.env["res.company"].create({"name": "Autre OBNL"})
        passerelle_b = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de B",
            "company_id": autre_societe.id,
            "sequence": 1,
        })
        self.gateway.active = False
        dispatch = self._dispatch(
            uuid="uuid-orphelin",
            gateway_id=False,
            send_deadline=fields.Datetime.now() - timedelta(minutes=5),
        )

        self.env["erplibre.sms.dispatch"]._cron_expire_stale()

        dispatch.invalidate_recordset()
        self.assertEqual(dispatch.state, "expired")
        passerelle_b.invalidate_recordset()
        self.assertFalse(passerelle_b.alarm_active)

    def test_android_code_maps_to_allowed_provider_error(self):
        """Tout code annonce doit se traduire en une valeur que le coeur accepte.

        `sms.tracker._action_update_from_provider_error` remplace par `unknown`
        tout `sms_<code>` absent de `sms.sms.DELIVERY_ERRORS` : un mappage vers
        une valeur hors liste ferait afficher « Unknown error » a l'utilisatrice
        et perdrait tout le diagnostic.
        """
        from ..models.erplibre_sms_dispatch import ANDROID_CODE_TO_PROVIDER_ERROR
        allowed = self.env["sms.sms"].DELIVERY_ERRORS
        for android_code, provider_error in ANDROID_CODE_TO_PROVIDER_ERROR.items():
            self.assertIn(
                f"sms_{provider_error}", allowed,
                f"{android_code} -> {provider_error} n'est pas dans DELIVERY_ERRORS",
            )


@tagged("post_install", "-at_install")
class TestErplibreSmsGuards(TransactionCase):
    """Garde-fous du compositeur : ils doivent LEVER, pas etre avales."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.sms_provider = "erplibre"
        # Le compositeur ne recoit pas sa passerelle : il la RESOUT, par un
        # `search(limit=1)` sur la societe, trie par `sequence, id`. Une
        # passerelle deja presente dans la base — celle d'une demonstration,
        # par exemple — a la meme sequence par defaut et un id plus petit :
        # elle gagne le tri. Les garde-fous se verifiaient alors sur elle et
        # non sur celle du test, et les deux `assertRaises` echouaient alors
        # que le code teste etait juste.
        #
        # On isole donc au lieu de dependre de ce qui traine dans la base.
        # La transaction est annulee en fin de test : rien n'est desactive
        # durablement.
        self.env["erplibre.sms.gateway"].search(
            [("company_id", "=", self.company.id)]
        ).write({"active": False})
        self.gateway = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de test",
            "company_id": self.company.id,
            "max_recipients_per_send": 2,
        })

    def _composer(self, numbers):
        return self.env["sms.composer"].create({
            "body": "Cours annule",
            "composition_mode": "numbers",
            "numbers": numbers,
        })

    def test_api_class_is_selected(self):
        self.assertEqual(self.company._get_sms_api_class().__name__, "SmsApiErplibre")

    def test_recipient_cap_raises(self):
        composer = self._composer("+15145550001,+15145550002,+15145550003")
        with self.assertRaises(UserError):
            composer._erplibre_check_allowed()

    def test_recipient_cap_allows_under_limit(self):
        composer = self._composer("+15145550001,+15145550002")
        composer._erplibre_check_allowed()

    def test_alarm_blocks_sending(self):
        self.gateway.max_recipients_per_send = 60
        self.gateway._raise_alarm("test de panne")
        composer = self._composer("+15145550001")
        with self.assertRaises(UserError):
            composer._erplibre_check_allowed()
        self.gateway._clear_alarm()
        composer._erplibre_check_allowed()

    def test_segments_per_minute_cannot_exceed_android_limit(self):
        with self.assertRaises(UserError):
            self.gateway.segments_per_minute = 31

    def test_estimate_mentions_ucs2_offenders(self):
        composer = self._composer("+15145550001")
        composer.body = "Bien reçu, ça commence à 19h"
        composer._compute_erplibre_estimate()
        self.assertIn("UCS2", composer.erplibre_estimate)
        self.assertIn("ç", composer.erplibre_estimate)


@tagged("post_install", "-at_install")
class TestErplibreSmsInbound(TransactionCase):

    def setUp(self):
        super().setUp()
        self.gateway = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de test",
            "company_id": self.env.company.id,
        })

    def test_stop_feeds_blacklist(self):
        record = self.env["erplibre.sms.inbound"]._record(self.gateway, {
            "id": "in-0001", "from": "+15145559999", "body": "STOP", "at": 1754300000,
        })
        self.assertTrue(record.is_opt_out)
        self.assertTrue(record.blacklist_id)
        self.assertTrue(record.blacklist_id.active)

    def test_french_keyword_recognised(self):
        for keyword in ("ARRET", "arrêt", "Desabonnement", "stop"):
            self.env["erplibre.sms.inbound"].search([]).unlink()
            record = self.env["erplibre.sms.inbound"]._record(self.gateway, {
                "id": "in-" + keyword, "from": "+15145559998", "body": keyword,
            })
            self.assertTrue(record.is_opt_out, keyword)

    def test_ordinary_reply_is_not_opt_out(self):
        record = self.env["erplibre.sms.inbound"]._record(self.gateway, {
            "id": "in-0002", "from": "+15145559997",
            "body": "Merci, je serai là",
        })
        self.assertFalse(record.is_opt_out)
        self.assertFalse(record.blacklist_id)

    def test_duplicate_ignored(self):
        payload = {"id": "in-0003", "from": "+15145559996", "body": "STOP"}
        self.assertTrue(self.env["erplibre.sms.inbound"]._record(self.gateway, payload))
        self.assertFalse(self.env["erplibre.sms.inbound"]._record(self.gateway, payload))


@tagged("post_install", "-at_install")
class TestErplibreSmsNonce(TransactionCase):

    def test_single_use(self):
        model = self.env["erplibre.sms.nonce"]
        self.assertTrue(model._consume("nonce-1", "dev-1"))
        self.assertFalse(model._consume("nonce-1", "dev-1"))
        self.assertTrue(model._consume("nonce-2", "dev-1"))

    def test_empty_nonce_refused(self):
        self.assertFalse(self.env["erplibre.sms.nonce"]._consume("", "dev-1"))
        self.assertFalse(self.env["erplibre.sms.nonce"]._consume(None, "dev-1"))


@tagged("post_install", "-at_install")
class TestErplibreSmsCron(TransactionCase):

    def test_core_send_cron_was_retuned(self):
        """Le cron d'envoi du coeur est HORAIRE : inacceptable pour une alerte.

        Il est declare dans un bloc `noupdate="1"`, donc un XML de surcharge
        serait ignore a chaque mise a jour. C'est le `post_init_hook` qui le
        corrige, et ce test verifie qu'il l'a fait.
        """
        cron = self.env.ref("sms.ir_cron_sms_scheduler_action")
        self.assertEqual(cron.interval_type, "minutes")
        self.assertLessEqual(cron.interval_number, 5)


@tagged("post_install", "-at_install")
class TestErplibreSmsPolling(TransactionCase):
    """Remise des travaux par interrogation, et reprise apres perte."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.gateway = self.env["erplibre.sms.gateway"].create({
            "name": "Passerelle de test",
            "company_id": self.company.id,
            "poll_interval_seconds": 60,
            "redelivery_seconds": 300,
        })

    def _queued(self, uuid, **values):
        return self.env["erplibre.sms.dispatch"].create({
            "sms_uuid": uuid,
            "number": "+1514555" + uuid[-4:],
            "body": "Cours annule",
            "company_id": self.company.id,
            "gateway_id": self.gateway.id,
            "state": "queued",
            **values,
        })

    def test_claim_marks_delivered_and_returns_once(self):
        dispatch = self._queued("uuid-p001")
        claimed = self.gateway._claim_pending()
        self.assertIn(dispatch, claimed)
        self.assertEqual(dispatch.state, "published")
        self.assertTrue(dispatch.published_at)
        # Une seconde interrogation immediate ne doit pas le reproposer.
        self.assertNotIn(dispatch, self.gateway._claim_pending())

    def test_unconfirmed_job_is_offered_again_after_delay(self):
        """Le telephone a pu mourir entre la reception et l'enregistrement.

        Sans cette reprise, le SMS disparaitrait en silence — le mode de
        defaillance que toute cette conception s'interdit.
        """
        dispatch = self._queued("uuid-p002")
        self.gateway._claim_pending()
        self.assertNotIn(dispatch, self.gateway._claim_pending())
        # On recule la remise au-dela du delai de reprise.
        dispatch.write({
            "published_at": fields.Datetime.now() - timedelta(seconds=600),
        })
        self.assertIn(dispatch, self.gateway._claim_pending())

    def test_confirmed_job_is_never_offered_again(self):
        dispatch = self._queued("uuid-p003")
        self.gateway._claim_pending()
        dispatch._apply_event("submitted", seq=1)
        dispatch.write({
            "published_at": fields.Datetime.now() - timedelta(seconds=600),
        })
        self.assertNotIn(dispatch, self.gateway._claim_pending())

    def test_claim_is_bounded(self):
        self.gateway.max_jobs_per_poll = 3
        for index in range(5):
            self._queued(f"uuid-p1{index:02d}")
        self.assertEqual(len(self.gateway._claim_pending()), 3)

    def test_payload_writes_body_once_per_group(self):
        for index in range(3):
            self._queued(f"uuid-p2{index:02d}")
        self._queued("uuid-p299", body="Autre message")
        groups = self.gateway._payload_for(self.gateway._claim_pending())
        self.assertEqual(len(groups), 2)
        by_body = {group["body"]: group for group in groups}
        self.assertEqual(len(by_body["Cours annule"]["to"]), 3)
        self.assertEqual(len(by_body["Autre message"]["to"]), 1)

    def test_poll_counts_as_liveness(self):
        self.assertFalse(self.gateway.last_poll_at)
        self.gateway._record_poll({
            "sms_permission": True, "sim_ready": True, "battery": 88, "charging": True,
        })
        self.assertTrue(self.gateway.last_poll_at)
        self.assertTrue(self.gateway.is_healthy)

    def test_poll_reporting_a_revoked_permission_raises_alarm(self):
        """Le telephone parle, mais pour dire qu'il ne peut pas envoyer."""
        self.gateway._record_poll({"sms_permission": False, "sim_ready": True})
        self.assertTrue(self.gateway.alarm_active)
        self.assertIn("permission", self.gateway.alarm_reason.lower())

    def test_silence_raises_alarm(self):
        self.gateway._record_poll({"sms_permission": True, "sim_ready": True})
        self.env["erplibre.sms.gateway"]._cron_check_heartbeat()
        self.assertFalse(self.gateway.alarm_active)
        # Trois intervalles manques : la passerelle est declaree muette.
        self.gateway.write({
            "last_poll_at": fields.Datetime.now() - timedelta(seconds=600),
        })
        self.env["erplibre.sms.gateway"]._cron_check_heartbeat()
        self.assertTrue(self.gateway.alarm_active)

    def test_poll_interval_floor(self):
        with self.assertRaises(UserError):
            self.gateway.poll_interval_seconds = 5
