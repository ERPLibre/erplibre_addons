# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store

# Texts of a reflection that the moderation hides with its carrier message.
REFLET_TEXT_FIELDS = ("you_said", "understood", "body_text")


class LinkupHiddenContent(models.Model):
    """The original of a content the moderation hid (LU-F-116 RM2).

    Hiding moves the content out of the conversation, so that no reading
    path still serves it: the body and the attachments of the message, and
    the texts of its reflection, leave their records for this one. The
    message keeps ``linkup_hidden`` and an empty body; the reflection keeps
    ``linkup_moderation_hidden`` and empty texts. The attachments move to
    this record, which no access right opens, so that ``/web/content``
    refuses them too.

    Nobody reads this model through the ORM; the console of the moderation
    reads it under ``sudo``, writing each reading to the audit log, and a
    reversed decision puts the content back.
    """

    _name = "linkup.hidden.content"
    _inherit = ["linkup.server.record"]
    _description = "LinkUp content hidden by the moderation"
    _order = "id desc"

    report_id = fields.Many2one(
        "linkup.report", required=True, ondelete="restrict", index=True
    )
    message_id = fields.Many2one("mail.message", ondelete="set null")
    reflet_id = fields.Many2one("linkup.reflet", ondelete="set null")
    body = fields.Html(sanitize=False)
    you_said = fields.Text()
    understood = fields.Text()
    body_text = fields.Text()
    attachment_ids = fields.Many2many("ir.attachment")

    @api.model
    def _linkup_hide(self, report, message, reflet):
        """Hide ``message`` and ``reflet`` for ``report``, either one being
        empty, and tell the conversation. Content already hidden stays as
        it is. Return the record of the originals, or an empty one."""
        message = message.sudo().filtered(lambda m: not m.linkup_hidden)
        reflet = reflet.sudo().filtered(
            lambda r: not r.linkup_moderation_hidden
        )
        if not message and not reflet:
            return self.browse()
        attachments = message.attachment_ids
        hidden = self.sudo().create(
            {
                "report_id": report.id,
                "message_id": message.id,
                "reflet_id": reflet.id,
                "body": message.body or False,
                "attachment_ids": [(6, 0, attachments.ids)],
                **{name: reflet[name] or False for name in REFLET_TEXT_FIELDS},
            }
        )
        if message:
            attachments.write({"res_model": self._name, "res_id": hidden.id})
            message.write(
                {
                    "body": "",
                    "attachment_ids": [(5, 0, 0)],
                    "linkup_hidden": True,
                }
            )
        if reflet:
            reflet._linkup_set_moderation_hidden(True)
        self._linkup_broadcast(message, reflet)
        return hidden

    def _linkup_restore(self):
        """Put the originals back where they were, then delete them."""
        for hidden in self.sudo():
            message = hidden.message_id
            reflet = hidden.reflet_id
            if message:
                hidden.attachment_ids.write(
                    {"res_model": message.model, "res_id": message.res_id}
                )
                message.write(
                    {
                        "body": hidden.body or "",
                        "attachment_ids": [(6, 0, hidden.attachment_ids.ids)],
                        "linkup_hidden": False,
                    }
                )
            if reflet:
                reflet._linkup_set_moderation_hidden(
                    False, {name: hidden[name] for name in REFLET_TEXT_FIELDS}
                )
            self._linkup_broadcast(message, reflet)
        self.sudo().unlink()

    @api.model
    def _linkup_broadcast(self, message, reflet):
        """Send the message and the card as they now are to the
        conversation they belong to."""
        message = message.sudo()
        if message.model == "discuss.channel" and message.res_id:
            channel = self.env["discuss.channel"].sudo().browse(message.res_id)
            store = Store(message, fields=["body"])
            store.add(
                message,
                {
                    "attachment_ids": Store.many(message.attachment_ids),
                    "linkup_hidden": message.linkup_hidden,
                },
            )
            channel._bus_send_store(store)
        if reflet:
            reflet.sudo()._linkup_notify()
