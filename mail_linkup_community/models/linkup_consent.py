# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.http import request
from odoo.tools.misc import hmac

PURPOSES = [
    ("terms", "Terms of use"),
    ("privacy", "Privacy policy"),
    ("sensitive_data", "Sensitive information"),
    ("link_visibility", "My links visible to my links"),
    ("energy_visibility", "My energy visible to my links"),
    ("notifications", "Notifications"),
    ("ai", "Artificial intelligence assistance"),
]
# Purposes without which a member sends nothing (LU-F-111 RM1, LU-NF-050).
REQUIRED_PURPOSES = ("terms", "privacy", "sensitive_data")
# Purposes a member withdraws at any time, with immediate effect (LU-F-111
# RM3). The terms of use and the privacy policy are the conditions of the
# account: leaving them is the deletion of the account.
REVOCABLE_PURPOSES = (
    "sensitive_data",
    "link_visibility",
    "energy_visibility",
    "notifications",
    "ai",
)
# Fields of ``res.users`` that hold the current choice of a purpose, when
# the module that brings them is installed: writing one records the
# consent, and granting or withdrawing the consent writes it.
MIRROR_FIELDS = {
    "link_visibility": "linkup_links_visible",
    "energy_visibility": "linkup_energy_visible",
    "ai": "linkup_ai_consent",
}
# The settings of ``res.users.settings`` the consent to notifications turns
# on or off together.
NOTIFICATION_SETTINGS = (
    "linkup_notify_reflet_received",
    "linkup_notify_confirmed",
    "linkup_notify_highlight",
    "linkup_notify_invitation_accepted",
)
# Parameter holding the current version of the text of a purpose; a purpose
# without one is at version "1".
VERSION_PARAM = "linkup.consent_version.%s"
# Scope of the keyed hash of an address IP.
IP_HASH_SCOPE = "linkup.consent.ip"


class LinkupConsent(models.Model):
    """The proof of a consent of a member (LU-F-111, LU-NF-013): one row per
    decision, granted or withdrawn, with the version of the text agreed to,
    its date and a keyed hash of the address it came from. The current
    state of a purpose is its most recent row.

    Rows are written by the server only: at the signup, and through
    ``action_grant`` and ``action_revoke``, which force the member to the
    current user. Members read their own rows and create, write or delete
    none; LinkUp administrators read them all.
    """

    _name = "linkup.consent"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp consent"
    _order = "date desc, id desc"
    _rec_name = "purpose"

    user_id = fields.Many2one(
        "res.users",
        string="Member",
        required=True,
        index=True,
        ondelete="cascade",
        readonly=True,
    )
    purpose = fields.Selection(
        PURPOSES, required=True, index=True, readonly=True
    )
    granted = fields.Boolean(readonly=True)
    version = fields.Char(required=True, readonly=True)
    date = fields.Datetime(
        required=True, default=fields.Datetime.now, readonly=True
    )
    # Erased with the account (LU-F-117 RM2).
    ip_hash = fields.Char(
        string="Address hash", readonly=True, groups="base.group_system"
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _linkup_version(self, purpose):
        """The current version of the text of ``purpose``."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(VERSION_PARAM % purpose, "1")
        )

    @api.model
    def _linkup_ip_hash(self):
        """A keyed hash of the address of the current request, or
        ``False`` outside of a request: the address itself is not kept."""
        address = request and request.httprequest.remote_addr
        if not address:
            return False
        return hmac(self.env(su=True), IP_HASH_SCOPE, address)

    @api.model
    def _linkup_available(self, purpose):
        """Whether ``purpose`` applies on this instance: a purpose with a
        mirror field needs the module of that field."""
        field = MIRROR_FIELDS.get(purpose)
        return not field or field in self.env["res.users"]._fields

    @api.model
    def _linkup_record(self, user, purpose, granted):
        """Record a decision of ``user`` on ``purpose``, at the current
        version of its text."""
        return self.sudo().create(
            {
                "user_id": user.id,
                "purpose": purpose,
                "granted": bool(granted),
                "version": self._linkup_version(purpose),
                "ip_hash": self._linkup_ip_hash(),
            }
        )

    @api.model
    def _linkup_latest(self, user):
        """The most recent row of each purpose of ``user``, by purpose."""
        latest = {}
        for consent in self.sudo().search([("user_id", "=", user.id)]):
            latest.setdefault(consent.purpose, consent)
        return latest

    @api.model
    def _linkup_active(self, user, purpose):
        """Whether ``user`` currently grants ``purpose``."""
        consent = self.sudo().search(
            [("user_id", "=", user.id), ("purpose", "=", purpose)], limit=1
        )
        return bool(consent.granted)

    @api.model
    def _linkup_missing(self, user):
        """The required purposes ``user`` does not grant, when their account
        needs them (``res.users._linkup_consents_required``)."""
        if not user._linkup_consents_required():
            return []
        latest = self._linkup_latest(user)
        return [
            purpose
            for purpose in REQUIRED_PURPOSES
            if not (purpose in latest and latest[purpose].granted)
        ]

    @api.model
    def _linkup_check_purposes(self, purposes, allowed):
        """The purposes of a client, as a list, each one in ``allowed``."""
        if isinstance(purposes, str):
            purposes = [purposes]
        if not isinstance(purposes, (list, tuple)) or not purposes:
            raise LinkupError(
                "linkup.validation", _("Choose a consent."), field="purpose"
            )
        for purpose in purposes:
            if purpose not in allowed or not self._linkup_available(purpose):
                raise LinkupError(
                    "linkup.validation",
                    _("This consent cannot be changed here."),
                    field="purpose",
                )
        return list(dict.fromkeys(purposes))

    def _linkup_apply(self, user, purpose, granted):
        """Record a decision and bring the settings it governs along: the
        mirror field, whose write records the decision itself, or the
        notifications of LinkUp."""
        field = MIRROR_FIELDS.get(purpose)
        if field:
            user.sudo().write({field: bool(granted)})
            return
        self._linkup_record(user, purpose, granted)
        if purpose == "notifications":
            settings = (
                self.env["res.users.settings"]
                .sudo()
                ._find_or_create_for_user(user)
            )
            settings.set_res_users_settings(
                {name: bool(granted) for name in NOTIFICATION_SETTINGS}
            )

    # ------------------------------------------------------------------
    # Actions of the member
    # ------------------------------------------------------------------

    @api.model
    @server_context
    def action_grant(self, purposes):
        """Grant ``purposes``, a purpose or a list, for the current member.
        Return ``linkup_consents_info``."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        allowed = [code for code, _label in PURPOSES]
        for purpose in self._linkup_check_purposes(purposes, allowed):
            self._linkup_apply(user, purpose, True)
        user._linkup_send_consent_state()
        return self.linkup_consents_info()

    @api.model
    @server_context
    def action_revoke(self, purposes):
        """Withdraw ``purposes`` for the current member, at once. The terms
        of use and the privacy policy are not withdrawn here: leaving them
        is the deletion of the account. Withdrawing ``sensitive_data``
        stops every sending. Return ``linkup_consents_info``."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        for purpose in self._linkup_check_purposes(
            purposes, REVOCABLE_PURPOSES
        ):
            self._linkup_apply(user, purpose, False)
        user._linkup_send_consent_state()
        return self.linkup_consents_info()

    @api.model
    @server_context
    def linkup_consents_info(self):
        """The consents of the current member, in the order of
        ``PURPOSES``: for each available purpose its state, the date and
        the version of the last decision, the current version of its text,
        and whether it is required and can be withdrawn."""
        self.env["linkup.reflet"]._linkup_check_member()
        user = self.env.user
        latest = self._linkup_latest(user)
        labels = dict(self._fields["purpose"]._description_selection(self.env))
        rows = []
        for purpose, _label in PURPOSES:
            if not self._linkup_available(purpose):
                continue
            consent = latest.get(purpose)
            rows.append(
                {
                    "purpose": purpose,
                    "label": labels[purpose],
                    "granted": bool(consent and consent.granted),
                    "date": consent.date if consent else False,
                    "version": consent.version if consent else False,
                    "current_version": self._linkup_version(purpose),
                    "required": purpose in REQUIRED_PURPOSES,
                    "revocable": purpose in REVOCABLE_PURPOSES,
                }
            )
        return rows
