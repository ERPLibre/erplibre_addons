# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import _, api, fields, models


class EventRaffleDraw(models.Model):
    _name = "event.raffle.draw"
    _description = "Raffle Draw"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    raffle_id = fields.Many2one(
        "event.raffle",
        string="Raffle",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Draw #", default=1)
    name = fields.Char(string="Name", compute="_compute_name", store=True)
    prize = fields.Char(string="Prize")
    prize_description = fields.Text(string="Prize Description")
    winner_participant_id = fields.Many2one(
        "event.raffle.participant",
        string="Winner",
        ondelete="set null",
    )
    winner_name = fields.Char(string="Winner Name", tracking=True)
    winner_email = fields.Char(string="Winner Email")
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="winner_participant_id.partner_id",
        store=True,
        index=True,
        help="Winning contact, taken from the participant. Stored so that "
        "the contact form can list its draws without going through the "
        "participants.",
    )
    is_absent = fields.Boolean(string="Absent", default=False, tracking=True)
    date = fields.Datetime(string="Date", default=fields.Datetime.now)
    comment = fields.Text(string="Comment")
    prize_received = fields.Boolean(
        string="Prize Received",
        default=False,
        tracking=True,
    )
    prize_received_date = fields.Datetime(string="Prize Received Date")
    notification_ids = fields.One2many(
        "event.raffle.draw.notification",
        "draw_id",
        string="Notifications Sent",
    )
    notification_count = fields.Integer(
        string="Notifications",
        compute="_compute_notification_count",
        store=True,
        help="Number of notifications sent to the winner from this draw.",
    )
    notified = fields.Boolean(
        string="Notified",
        compute="_compute_notification_count",
        store=True,
        help="At least one notification was sent to the winner.",
    )
    notification_read = fields.Boolean(
        string="Read",
        compute="_compute_notification_read",
        help="The winner has seen the latest chat notification in Discuss. "
        "An email notification never counts as read.",
    )

    @api.onchange("prize_received_date")
    def _onchange_prize_received_date(self):
        # Dating the hand-over says it happened. The flag stays editable on
        # its own, and emptying the date deliberately leaves it alone: only
        # the person who ticked it knows whether the prize came back.
        if self.prize_received_date:
            self.prize_received = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("prize_received_date"):
                vals["prize_received"] = True
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("prize_received_date"):
            vals["prize_received"] = True
        return super().write(vals)

    @api.depends("notification_ids")
    def _compute_notification_count(self):
        for rec in self:
            rec.notification_count = len(rec.notification_ids)
            rec.notified = bool(rec.notification_ids)

    @api.depends("notification_ids.is_read")
    def _compute_notification_read(self):
        # The latest chat notification decides, taken by id since the
        # one2many cache keeps creation order rather than the model order.
        # An email sent after it does not hide a read chat message.
        for rec in self:
            chats = rec.notification_ids.filtered(
                lambda n: n.channel == "chat"
            )
            latest = chats.sorted("id")[-1:]
            rec.notification_read = bool(latest.is_read)

    @api.depends("sequence", "winner_name")
    def _compute_name(self):
        for rec in self:
            label = rec.winner_name or ""
            name = _("Draw #%s") % rec.sequence
            if label:
                name = "%s - %s" % (name, label)
            rec.name = name

    def action_mark_absent(self):
        for rec in self:
            rec.is_absent = True
            if rec.winner_participant_id:
                rec.winner_participant_id.present = False
            rec.message_post(body=_("Winner marked absent."))
        return True

    def action_mark_present(self):
        for rec in self:
            rec.is_absent = False
            if rec.winner_participant_id:
                rec.winner_participant_id.present = True
            rec.message_post(body=_("Winner marked present."))
        return True

    def action_open_notify_wizard(self):
        """Open the wizard that sends a notification to this winner."""
        self.ensure_one()
        self.check_access("write")
        return {
            "type": "ir.actions.act_window",
            "name": _("Notify the Winner"),
            "res_model": "event.raffle.draw.notify.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_draw_id": self.id},
        }
