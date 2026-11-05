# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.tools import email_normalize
from odoo.tools.misc import hmac

# Scope of the keyed hash of an address, so that the same address gives
# another value in any other use of the secret of the database.
EMAIL_HASH_SCOPE = "linkup.email.blocklist"
# Months an entry is kept (LU-NF-015).
RETENTION_MONTHS = 24


class LinkupEmailBlocklist(models.Model):
    """Addresses LinkUp never writes to, kept as keyed hashes only.

    ``email_hash`` is an HMAC of the normalized address, keyed by the secret
    of the database: the list answers "is this address in it?" and never
    gives an address back. ``invite_optout`` records the refusal of every
    invitation from the link of an invitation email (LU-F-020 RM7);
    ``banned`` is for the moderation of a later lot. An entry lasts
    ``RETENTION_MONTHS`` months, then the purge of the invitations deletes
    it.

    Only LinkUp administrators read it; the server writes it under ``sudo``.
    """

    _name = "linkup.email.blocklist"
    _description = "LinkUp blocklist of email addresses"
    _order = "id desc"

    email_hash = fields.Char(required=True, index=True, readonly=True)
    reason = fields.Selection(
        [
            ("invite_optout", "Refuses the invitations"),
            ("banned", "Banned"),
        ],
        required=True,
        readonly=True,
    )
    expiry_date = fields.Datetime(required=True, readonly=True)

    _sql_constraints = [
        (
            "hash_reason_unique",
            "UNIQUE(email_hash, reason)",
            "An address is listed once for a reason.",
        ),
    ]

    @api.model
    def _linkup_hash(self, email):
        """The keyed hash of an address, or ``False`` for an invalid one."""
        normalized = email_normalize(email or "")
        if not normalized:
            return False
        return hmac(self.env(su=True), EMAIL_HASH_SCOPE, normalized)

    @api.model
    def _linkup_is_listed(self, email):
        """Tell whether an address is listed, for any reason not expired."""
        email_hash = self._linkup_hash(email)
        return bool(email_hash) and bool(
            self.sudo().search_count(
                [
                    ("email_hash", "=", email_hash),
                    ("expiry_date", ">", fields.Datetime.now()),
                ],
                limit=1,
            )
        )

    @api.model
    def _linkup_add(self, email, reason):
        """List an address for a reason, or extend its entry; return
        whether the address is valid."""
        email_hash = self._linkup_hash(email)
        if not email_hash:
            return False
        expiry = fields.Datetime.now() + relativedelta(months=RETENTION_MONTHS)
        self.flush_model()
        self.env.cr.execute(
            """
            INSERT INTO linkup_email_blocklist
                (email_hash, reason, expiry_date,
                 create_uid, create_date, write_uid, write_date)
            VALUES (%s, %s, %s,
                    %s, now() at time zone 'UTC',
                    %s, now() at time zone 'UTC')
            ON CONFLICT (email_hash, reason)
            DO UPDATE SET expiry_date = EXCLUDED.expiry_date
            """,
            [email_hash, reason, expiry, self.env.uid, self.env.uid],
        )
        self.invalidate_model()
        return True

    @api.model
    def _linkup_purge(self):
        """Delete the entries past their date."""
        self.sudo().search(
            [("expiry_date", "<=", fields.Datetime.now())]
        ).unlink()
