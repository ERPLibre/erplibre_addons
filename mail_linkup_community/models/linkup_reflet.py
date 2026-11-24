# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, fields, models
from odoo.addons.mail_linkup_reflet.client_context import server_context
from odoo.addons.mail_linkup_reflet.exceptions import LinkupError
from odoo.tools import SQL

from .linkup_hidden_content import REFLET_TEXT_FIELDS
from .linkup_report import QUEUE_STATES


class LinkupReflet(models.Model):
    _inherit = "linkup.reflet"

    # Set by the moderation, which moves the texts of the reflection to
    # ``linkup.hidden.content`` (LU-F-116 RM2).
    linkup_moderation_hidden = fields.Boolean(
        string="Hidden by the moderation", readonly=True, copy=False
    )
    # Set when the texts are erased for good: the deletion of an account of
    # a party, the retention periods, or the request of the recipient of a
    # rejected reflection (LU-F-117 RM2, RM4, LU-NF-015).
    linkup_content_removed = fields.Boolean(
        string="Content removed", readonly=True, copy=False
    )

    def _linkup_begin(self, actor, states, kinds, exchange=True):
        """Every exchange of a reflection, its sending and its invitations
        included, needs a verified address and the required consents
        (LU-F-110 CA3, LU-F-111 CA2); reading, withdrawing and discarding
        do not."""
        if exchange:
            self.env.user._linkup_check_can_exchange()
        return super()._linkup_begin(actor, states, kinds, exchange=exchange)

    def _linkup_card_values(self):
        """A card hidden by the moderation, or whose texts are erased, says
        so, without its texts."""
        values = super()._linkup_card_values()
        reflet = self.sudo()
        if reflet.linkup_moderation_hidden:
            values.update(
                moderation_hidden=True,
                **dict.fromkeys(REFLET_TEXT_FIELDS, False),
            )
        if reflet.linkup_content_removed:
            values.update(
                content_removed=True,
                real_world_date=False,
                **dict.fromkeys(REFLET_TEXT_FIELDS, False),
            )
        return values

    def _linkup_remove_content(self):
        """Erase the texts of the reflections for good, mark them
        ``linkup_content_removed`` and send the cards again.

        The texts are emptied in SQL: the constraint of a sent reflection
        requires them, and ``write_date`` stays as it was, so that the
        other party does not read when the erasure happened. The category,
        the states and the dates stay: they are the metadata of the pair,
        which the points ledger of the other party points to.
        """
        reflets = self.sudo().filtered(
            lambda reflet: not reflet.linkup_content_removed
        )
        if not reflets:
            return
        reflets.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE linkup_reflet SET linkup_content_removed = TRUE,"
                " you_said = NULL, understood = NULL, body_text = NULL,"
                " real_world_date = NULL WHERE id IN %s",
                tuple(reflets.ids),
            )
        )
        reflets.invalidate_recordset(
            ["linkup_content_removed", "real_world_date", *REFLET_TEXT_FIELDS]
        )
        reflets._linkup_notify()

    def _linkup_held_by_report(self):
        """The reflections of ``self`` a report still open points to: their
        texts stay until the moderation closes it."""
        reports = (
            self.env["linkup.report"]
            .sudo()
            .search(
                [
                    ("reflet_id", "in", self.ids),
                    ("state", "in", QUEUE_STATES),
                ]
            )
        )
        return reports.reflet_id

    @server_context
    def action_erase_content(self):
        """The recipient of a rejected or inaccurate reflection erases its
        texts, which lend them words they did not say (LU-F-117 RM4). A
        reflection an open report points to keeps them until the report
        is closed: ``linkup.unavailable``."""
        reflet = self._linkup_begin(
            "recipient_id",
            ("rejected", "inaccurate"),
            ("initial",),
            exchange=False,
        )
        if reflet._linkup_held_by_report():
            raise LinkupError(
                "linkup.unavailable",
                _(
                    "A report about this reflection is being processed; its"
                    " content can be erased once it is closed."
                ),
            )
        reflet._linkup_remove_content()
        return True

    def _linkup_set_moderation_hidden(self, hidden, texts=None):
        """Hide or show again the texts of the reflection: without
        ``texts``, they are emptied; with them, they are written back.

        The texts move in SQL: the constraint of a sent reflection requires
        them, and the moderation removes them on purpose.
        """
        self.ensure_one()
        texts = texts or dict.fromkeys(REFLET_TEXT_FIELDS)
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE linkup_reflet SET linkup_moderation_hidden = %s,"
                " you_said = %s, understood = %s, body_text = %s"
                " WHERE id = %s",
                bool(hidden),
                texts.get("you_said") or None,
                texts.get("understood") or None,
                texts.get("body_text") or None,
                self.id,
            )
        )
        self.invalidate_recordset(
            ["linkup_moderation_hidden", *REFLET_TEXT_FIELDS]
        )
