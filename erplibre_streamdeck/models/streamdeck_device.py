# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.tools import SQL

# USB product id (four lowercase hex digits, vendor 0fd9) -> model name.
# The ids are those of the `streamdeck` Python library that drives the
# deck; that library maps 00b9 to both "MK.2 V2" and "MK.2 Module", which
# share the hardware. An id missing here reads "Stream Deck (<id>)".
USB_MODELS = {
    "0060": "Stream Deck Original",
    "006d": "Stream Deck Original V2",
    "0080": "Stream Deck MK.2",
    "00a5": "Stream Deck MK.2 Scissor",
    "00b9": "Stream Deck MK.2 V2",
    "0063": "Stream Deck Mini",
    "0090": "Stream Deck Mini MK.2",
    "00b8": "Stream Deck Mini MK.2 Module",
    "009a": "Stream Deck Neo",
    "006c": "Stream Deck XL",
    "008f": "Stream Deck XL V2",
    "00ba": "Stream Deck XL V2 Module",
    "0084": "Stream Deck +",
    "0086": "Stream Deck Pedal",
}


def usb_model_name(product_id):
    """Model name of a USB product id; the id is matched without regard
    to case, and an empty id gives the bare family name."""
    if not product_id:
        return "Stream Deck"
    product_id = product_id.lower()
    return USB_MODELS.get(product_id, "Stream Deck (%s)" % product_id)


class StreamdeckDevice(models.Model):
    """A deck, identified across the company by `key`.

    `key` is `sn:<serial>` when the workstation reads a serial; a deck
    without a readable serial gets `nosn:<workstation>:<product>:<path>`,
    so it is never merged with a deck of another workstation. A serial
    has no `:` (the service refuses one), so the two forms never meet.
    `workstation_id` is the workstation that reported it last: a deck
    moved to another workstation follows it, with a `moved` event that
    names both, and its events keep the workstation where each happened.

    `held_by_me` is true for the current user on a deck one of their
    workstations holds or held, as `streamdeck.device.holding` records
    it; the record rule of the employees and « My decks » read it.
    """

    _name = "streamdeck.device"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Stream Deck device"
    _order = "model_name, serial, id"

    key = fields.Char(required=True, readonly=True)
    serial = fields.Char(string="Serial number")
    usb_product_id = fields.Char(string="USB product id", size=4)
    model_name = fields.Char(
        string="Model", compute="_compute_model_name", store=True
    )
    firmware = fields.Char()
    workstation_id = fields.Many2one(
        "streamdeck.workstation",
        string="Current workstation",
        index=True,
        ondelete="set null",
    )
    connected = fields.Boolean()
    connected_since = fields.Datetime(string="Connected since")
    last_seen = fields.Datetime(string="Last seen")
    event_ids = fields.One2many(
        "streamdeck.event", "device_id", string="Events"
    )
    held_by_me = fields.Boolean(
        string="Held by me",
        compute="_compute_held_by_me",
        search="_search_held_by_me",
        help="One of your workstations holds this deck or held it.",
    )

    _sql_constraints = [
        ("key_unique", "UNIQUE(key)", "A deck key is unique."),
    ]

    @api.depends("usb_product_id")
    def _compute_model_name(self):
        for device in self:
            device.model_name = usb_model_name(device.usb_product_id)

    @api.depends("model_name", "serial")
    def _compute_display_name(self):
        for device in self:
            device.display_name = " ".join(
                part for part in (device.model_name, device.serial) if part
            )

    def _holdings_of_me_sql(self):
        """The ids of the decks that `held_by_me` selects, for the user
        of the environment, sudo or not."""
        self.env["streamdeck.device.holding"].flush_model()
        return SQL(
            "SELECT device_id FROM streamdeck_device_holding"
            " WHERE user_id = %s",
            self.env.uid,
        )

    def _compute_held_by_me(self):
        self.env.cr.execute(self._holdings_of_me_sql())
        held = {row[0] for row in self.env.cr.fetchall()}
        for device in self:
            device.held_by_me = device.id in held

    def _search_held_by_me(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise NotImplementedError(
                "held_by_me is searched with = or != and a boolean"
            )
        selected = (operator == "=") == value
        return [
            (
                "id",
                "in" if selected else "not in",
                SQL("(%s)", self._holdings_of_me_sql()),
            )
        ]
