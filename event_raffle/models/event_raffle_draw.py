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
    is_absent = fields.Boolean(string="Absent", default=False, tracking=True)
    date = fields.Datetime(string="Date", default=fields.Datetime.now)

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
