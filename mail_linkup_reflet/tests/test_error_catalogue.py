# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The error catalogue as the clients receive it (LU-F-093 CA1, §9.8): each
code of the server reaches a JSON-RPC client in
``error.data.context.linkup_code``, an expired session gives
``odoo.http.SessionExpiredException``, and no other code can be raised.
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.addons.mail_linkup_reflet.exceptions import (
    LINKUP_ERROR_CODES,
    LinkupError,
)
from odoo.tests import tagged
from odoo.tests.common import HttpCase
from odoo.tools import mute_logger

from .common import LinkupRefletCase
from .test_invitation import LinkupInvitationMixin

# Codes raised by later lots: the scoring module, the public signup.
LATER_CODES = {
    "linkup.cap_reached",
    "linkup.not_verified",
    "linkup.consent_required",
}


@tagged("post_install", "-at_install")
class TestLinkupErrorCatalogue(
    LinkupInvitationMixin, LinkupRefletCase, HttpCase
):
    # Helpers

    def _as(self, user):
        self.authenticate(user.login, user.login)

    def _post(self, route, params):
        """The JSON-RPC ``error`` of ``route``, or ``None`` on success."""
        response = self.url_open(
            route,
            data=json.dumps(
                {"id": 0, "jsonrpc": "2.0", "method": "call", "params": params}
            ),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json().get("error")

    def _call_error(self, model, method, args, kwargs=None):
        return self._post(
            f"/web/dataset/call_kw/{model}/{method}",
            {
                "model": model,
                "method": method,
                "args": args,
                "kwargs": kwargs or {},
            },
        )

    def assertClientCode(self, error, code, field=None):
        """The error a client receives carries ``code`` (and ``field``)."""
        self.assertTrue(error, f"No error, {code} expected.")
        context = error["data"].get("context") or {}
        self.assertEqual(context.get("linkup_code"), code)
        if field:
            self.assertEqual(context.get("linkup_field"), field)

    # Tests

    def test_catalogue_is_closed(self):
        """A code outside the catalogue cannot be raised: no client would
        know it."""
        with self.assertRaises(ValueError):
            LinkupError("linkup.zz_unknown", "Unknown")
        for code in LINKUP_ERROR_CODES:
            self.assertEqual(
                LinkupError(code, "Message").context["linkup_code"], code
            )
        self.assertLessEqual(LATER_CODES, LINKUP_ERROR_CODES)

    @mute_logger("odoo.http", "odoo.addons.mail.models.mail_thread")
    def test_reflet_codes_reach_the_client(self):
        """Each refusal of a reflection reaches the client with its code."""
        self._as(self.sam)
        draft = self._draft(you_said="", understood="")
        self.assertClientCode(
            self._call_error(
                "linkup.reflet", "action_send", [draft.ids, self.france.id]
            ),
            "linkup.validation",
            field="you_said",
        )
        draft.with_user(self.sam).action_discard_draft()
        draft = self._draft()
        self.assertClientCode(
            self._call_error(
                "linkup.reflet", "action_send", [draft.ids, self.luce.id]
            ),
            "linkup.unavailable",
        )
        draft.with_user(self.sam).action_send(self.france.id)
        withdrawn = self._sent(recipient=self.jacques)
        withdrawn.with_user(self.sam).action_withdraw()

        self._as(self.france)
        self.assertIsNone(
            self._call_error("linkup.reflet", "action_confirm", [draft.ids])
        )
        self.assertClientCode(
            self._call_error("linkup.reflet", "action_confirm", [draft.ids]),
            "linkup.already_answered",
        )
        # LU-F-093 CA2: a reflection withdrawn while it is shown.
        self._as(self.jacques)
        self.assertClientCode(
            self._call_error(
                "linkup.reflet", "action_confirm", [withdrawn.ids]
            ),
            "linkup.expired",
        )

    @mute_logger("odoo.http", "odoo.addons.mail.models.mail_thread")
    def test_start_rule_and_rate_limit_reach_the_client(self):
        """A free text before a confirmation, and one report too many."""
        reflet = self._sent()
        self._as(self.france)
        self.assertClientCode(
            self._post(
                "/mail/message/post",
                {
                    "thread_model": "discuss.channel",
                    "thread_id": reflet.channel_id.id,
                    "post_data": {"body": "Bonjour"},
                },
            ),
            "linkup.start_rule",
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "linkup.max_reports_per_day", "1"
        )
        report = {"reflet_id": reflet.id, "reason": "spam"}
        self.assertIsNone(
            self._call_error(
                "linkup.report", "action_create_report", [], report
            )
        )
        self.assertClientCode(
            self._call_error(
                "linkup.report",
                "action_create_report",
                [],
                dict(report, reason="harassment"),
            ),
            "linkup.rate_limited",
        )

    @mute_logger("odoo.http")
    def test_invitation_codes_reach_the_client(self):
        """An invitation cancelled, used or expired refuses a new sending
        of its link with its own code."""
        expected = {
            "cancelled": "linkup.invite_cancelled",
            "accepted": "linkup.invite_used",
            "expired": "linkup.invite_expired",
        }
        self._as(self.sam)
        for state, code in expected.items():
            with self.subTest(state=state):
                reflet, result = self._invite(email=f"{state}@example.com")
                invitation = self._invitation(result)
                if state == "expired":
                    invitation.expiry_date = fields.Datetime.now() - timedelta(
                        days=1
                    )
                else:
                    invitation.state = state
                self.assertClientCode(
                    self._call_error(
                        "linkup.invitation", "action_resend", [invitation.ids]
                    ),
                    code,
                )
                invitation.state = "cancelled"
                reflet.sudo().state = "withdrawn"

    def test_session_expired(self):
        """Without a session, a call gives the error the clients turn into
        "log in again"."""
        self.authenticate(None, None)
        error = self._call_error(
            "linkup.reflet", "linkup_reflet_view_info", []
        )
        self.assertEqual(
            error["data"]["name"], "odoo.http.SessionExpiredException"
        )
