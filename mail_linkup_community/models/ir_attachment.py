# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models

from . import privacy


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Leave out of what a restricted member finds, and so reads, the
        attachments that store the photo of a member not linked to them
        (Q-27). ``ir.attachment`` opens an attachment of a field to whoever
        reads its record once the domain names ``res_field``, and reading
        an attachment by its id searches it here; ``/web/content`` serves
        it through ``ir.binary``."""
        query = super()._search(
            domain, offset=offset, limit=limit, order=order
        )
        if self.env.su or not privacy.contact_closed(self.env):
            return query
        ids = list(query)
        # sudo: ir.attachment - what the attachments found store
        photos = (
            self.sudo()
            .browse(ids)
            .filtered(
                lambda attachment: attachment.res_model in privacy.PHOTO_MODELS
                and attachment.res_field in privacy.IMAGE_FIELDS
            )
        )
        if not photos:
            return query
        owners = {}
        for attachment in photos:
            owner = (
                self.env[attachment.res_model].sudo().browse(attachment.res_id)
            )
            if owner._name == "res.users":
                owner = owner.partner_id
            owners[attachment.id] = owner.id
        closed_partners = privacy.closed_photo_partner_ids(
            self.env, owners.values()
        )
        closed = {
            attachment_id
            for attachment_id, partner_id in owners.items()
            if partner_id in closed_partners
        }
        if not closed:
            return query
        return self.browse(
            [
                attachment_id
                for attachment_id in ids
                if attachment_id not in closed
            ]
        )._as_query(order)
