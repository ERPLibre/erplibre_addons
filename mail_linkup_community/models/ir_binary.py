# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models

from . import privacy


class IrBinary(models.AbstractModel):
    _inherit = "ir.binary"

    def _record_to_stream(self, record, field_name):
        """Serve the placeholder instead of the photo of a member who is
        neither the reader nor linked to them, when the reader is a
        restricted member (Q-27): ``/web/image`` and the avatars of Discuss
        go through here, also with an access token."""
        if (
            record._name in ("res.partner", "res.users")
            and field_name in privacy.IMAGE_FIELDS
            and privacy.contact_closed(self.env)
        ):
            record.ensure_one()
            partner = (
                record if record._name == "res.partner" else record.partner_id
            )
            if partner != self.env.user.partner_id:
                linked = (
                    self.env["res.users"]
                    .sudo()
                    .browse(privacy.linked_user_ids(self.env))
                )
                if partner not in linked.partner_id:
                    return self._get_placeholder_stream(
                        partner.sudo()._avatar_get_placeholder_path()
                    )
        return super()._record_to_stream(record, field_name)
