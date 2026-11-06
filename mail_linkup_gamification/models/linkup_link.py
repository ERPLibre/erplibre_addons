# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models


class LinkupLink(models.Model):
    _inherit = "linkup.link"

    # Kept to LinkUp administrators: the side of the other member tells
    # the caps they reached elsewhere and whether their account earns
    # points. A member reads their own side through ``_linkup_energy_for``.
    energy_a = fields.Integer(groups="mail_linkup_reflet.group_linkup_admin")
    energy_b = fields.Integer(groups="mail_linkup_reflet.group_linkup_admin")
    linkup_round_user_id = fields.Many2one(
        "res.users",
        string="Round opened by",
        ondelete="set null",
        readonly=True,
        groups="mail_linkup_reflet.group_linkup_admin",
        help="Author of the free text that opened the current round of the"
        " pair; the other member closes it by posting free text in turn.",
    )

    def _linkup_energy_for(self, user):
        """The energy of the link as ``user`` reads it: the points they
        received in the events of the pair (LU-F-071 RM2)."""
        self.ensure_one()
        link = self.sudo()
        if link.user_a_id == user:
            return link.energy_a
        if link.user_b_id == user:
            return link.energy_b
        return 0
