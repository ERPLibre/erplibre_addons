# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import fields, models
from odoo.addons.mail.tools.discuss import Store


class LinkupCategory(models.Model):
    """A category of communication of the Help bar.

    A reflection carries one visible category; a precision hides some of
    them as themes to guess. The records are data: an administrator renames,
    reorders or archives them, an archived category leaves the bar and the
    band. Help itself is an interface entry, not a category.
    """

    _name = "linkup.category"
    _description = "LinkUp category of communication"
    _order = "sequence, id"

    code = fields.Char(
        required=True,
        help="Technical key used by the clients and the scoring rules.",
    )
    name = fields.Char(required=True, translate=True)
    definition = fields.Html(translate=True)
    example_do = fields.Text(string="What to say", translate=True)
    example_dont = fields.Text(string="What not to say", translate=True)
    reflet_title = fields.Char(
        string="Card title",
        translate=True,
        help="Title prefilled on a reflection card of this category.",
    )
    starter_self = fields.Char(
        string="First-person starter",
        translate=True,
        help="Text that opens a precision or a disclosure on this theme.",
    )
    starter_reflect = fields.Char(
        string="Reformulation starter",
        translate=True,
        help="Text that opens a reformulation on this theme.",
    )
    icon = fields.Image(max_width=128, max_height=128)
    sequence = fields.Integer(
        default=100, help="Order in the full band of categories."
    )
    in_reflet_bar = fields.Boolean(
        string="In the reduced bar",
        help="Shown in the reduced bar of the Reflet view.",
    )
    reflet_bar_sequence = fields.Integer(
        default=100, help="Order in the reduced bar of the Reflet view."
    )
    is_cnv = fields.Boolean(
        string="Non-violent communication",
        help="Part of the non-violent communication group.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "The category code must be unique."),
    ]

    def _to_store(self, store: Store, /, *, fields=None):
        """Add the categories to a Store by their code only.

        A Store built for a conversation is broadcast to all its members in
        the language of the poster; the texts of the categories, which are
        translated, are therefore left to the client, which reads them in
        its own language and matches them by code.
        """
        store.add(
            self._name,
            self.sudo()._read_format(fields or ["code"], load=False),
        )
