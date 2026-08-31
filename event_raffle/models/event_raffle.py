# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import random

from odoo import _, api, fields, models
from odoo.exceptions import UserError

THEME_SELECTION = [
    ("light", "Light"),
    ("dark", "Dark"),
    ("spectacle", "Show (spotlights)"),
    ("theatre", "Theater (gold & angels)"),
    ("linux", "Linux techno (dark)"),
    ("linux_light", "Linux techno (light)"),
    ("rave", "Rave (lasers)"),
]
CELEBRATION_SELECTION = [
    ("random", "Random (any of the below)"),
    ("candles", "Candles (Tux dances)"),
    ("confetti", "Confetti cannon"),
    ("fireworks", "Fireworks cannon"),
    ("trumpet", "Trumpet fanfare"),
    ("diabolo", "Diabolo juggling"),
]
TUX_ANIMATION_SELECTION = [
    ("rotate", "Rotate (cycle through all)"),
    ("peace", "Peace"),
    ("jump", "Jump with a smile"),
    ("flag", "Free software flag"),
    ("dance", "Dance"),
]
BELLY_LOGO_SELECTION = [
    ("none", "None"),
    ("fleur_de_lys", "Fleur-de-lys (Québec)"),
]


def _default(field, fallback):
    """Field default reading the raffle default-settings singleton."""

    def getter(self):
        cfg = self.env.ref(
            "event_raffle.raffle_config_singleton", raise_if_not_found=False
        )
        return getattr(cfg, field) if cfg else fallback

    return getter


class EventRaffle(models.Model):
    _name = "event.raffle"
    _description = "Event Raffle"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Name", required=True, default="Tirage")
    event_id = fields.Many2one(
        "event.event",
        string="Event",
        ondelete="cascade",
        index=True,
    )
    context_note = fields.Text(string="Context")
    remove_winner = fields.Boolean(
        string="Remove Winner",
        default=_default("default_remove_winner", True),
        help="Retire le gagnant du pool au prochain tir.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("in_progress", "In Progress"), ("done", "Done")],
        string="Status",
        default="draft",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    participant_ids = fields.One2many(
        "event.raffle.participant",
        "raffle_id",
        string="Participants",
    )
    draw_ids = fields.One2many(
        "event.raffle.draw",
        "raffle_id",
        string="Draws",
    )
    participant_count = fields.Integer(
        compute="_compute_counts",
        string="# Participants",
    )
    eligible_count = fields.Integer(
        compute="_compute_counts",
        string="# Eligible",
    )
    draw_count = fields.Integer(
        compute="_compute_counts",
        string="# Draws",
    )
    spin_duration = fields.Float(
        string="Spin Duration (s)",
        default=_default("default_spin_duration", 6.0),
        help="Durée de rotation de la roue, en secondes.",
    )
    spin_turns = fields.Integer(
        string="Spin Turns",
        default=_default("default_spin_turns", 5),
        help="Nombre de tours complets avant l'atterrissage.",
    )
    show_fireworks = fields.Boolean(
        string="Show Fireworks",
        default=_default("default_show_fireworks", True),
    )
    show_tux = fields.Boolean(
        string="Show Penguin (Tux)",
        default=_default("default_show_tux", False),
        help="Afficher le pingouin Tux à côté de la roue (caché par défaut).",
    )
    belly_logo = fields.Selection(
        BELLY_LOGO_SELECTION,
        string="Belly Logo",
        default=_default("default_belly_logo", "none"),
        required=True,
        help="Logo affiché sur le ventre de Tux (aucun par défaut).",
    )
    tux_animation = fields.Selection(
        TUX_ANIMATION_SELECTION,
        string="Tux Animation",
        default=_default("default_tux_animation", "rotate"),
        required=True,
        help="Animation Tux joue avant chaque tir. 'Rotate' alterne "
        "entre toutes les animations disponibles.",
    )
    flag_text = fields.Text(
        string="Flag Text",
        default=_default("default_flag_text", "Vive le logiciel libre"),
        help="Texte du drapeau (animation 'flag'). Une ligne au hasard "
        "est affichée à chaque tir.",
    )
    theme = fields.Selection(
        THEME_SELECTION,
        string="Theme",
        default=_default("default_theme", "light"),
        required=True,
        help="Thème visuel de la roue.",
    )
    winner_celebration = fields.Selection(
        CELEBRATION_SELECTION,
        string="Winner Celebration",
        default=_default("default_winner_celebration", "candles"),
        required=True,
        help="Effet joué à l'annonce d'un gagnant. 'Random' en choisit "
        "un au hasard à chaque tir.",
    )

    @api.depends(
        "participant_ids",
        "participant_ids.eligible",
        "draw_ids",
    )
    def _compute_counts(self):
        for rec in self:
            rec.participant_count = len(rec.participant_ids)
            rec.eligible_count = len(rec.participant_ids.filtered("eligible"))
            rec.draw_count = len(rec.draw_ids)

    def action_include_all(self):
        self.participant_ids.write({"excluded": False})
        return True

    def action_exclude_all(self):
        self.participant_ids.write({"excluded": True})
        return True

    def _eligible_participants(self):
        self.ensure_one()
        return self.participant_ids.filtered("eligible")

    def get_wheel_data(self):
        self.ensure_one()
        eligible = self._eligible_participants()
        last = (
            self.draw_ids.sorted("sequence")[-1:]
            if self.draw_ids
            else self.env["event.raffle.draw"]
        )
        # The next draw first removes the previous winner (deferred removal),
        # so a draw is only possible if at least one participant would remain
        # eligible afterwards. Guards the "next draw" button against a
        # "no eligible participant" error when a single name is left.
        remaining = eligible
        if self.remove_winner and last:
            remaining = eligible - last.winner_participant_id
        return {
            "raffle_id": self.id,
            "name": self.name,
            "remove_winner": self.remove_winner,
            "spin_duration": self.spin_duration,
            "spin_turns": self.spin_turns,
            "show_fireworks": self.show_fireworks,
            "show_tux": self.show_tux,
            "belly_logo": self.belly_logo,
            "tux_animation": self.tux_animation,
            "flag_text": self.flag_text or "Vive le logiciel libre",
            "theme": self.theme,
            "winner_celebration": self.winner_celebration,
            "eligible": [{"id": p.id, "name": p.name} for p in eligible],
            "can_draw_next": bool(remaining),
            "draw_count": len(self.draw_ids),
            "last_winner": last.winner_name or False,
            "history": [
                {
                    "id": d.id,
                    "sequence": d.sequence,
                    "winner_name": d.winner_name or "",
                    "prize": d.prize or "",
                    "prize_description": d.prize_description or "",
                    "is_absent": d.is_absent,
                    "present": not d.is_absent,
                    "date": (
                        d.date.strftime("%Y-%m-%d %H:%M") if d.date else ""
                    ),
                }
                for d in self.draw_ids.sorted("sequence")
            ],
        }

    def action_open_fullscreen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "event_raffle.wheel",
            "target": "fullscreen",
            "params": {"raffle_id": self.id},
        }

    def action_draw_next(self, prize=False, prize_description=False):
        self.ensure_one()
        # Serialize concurrent draws on the same raffle (the wheel can be
        # open in both the embedded widget and the fullscreen action): lock
        # the raffle row so two spins cannot pick from the same pool or
        # create draws with a duplicate sequence.
        self.env.cr.execute(
            "SELECT id FROM event_raffle WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        self.env["event.raffle.draw"].invalidate_model(["sequence"])
        # Deferred removal: the previous winner stays on the wheel after
        # winning and is only removed here, when the next draw is launched.
        if self.remove_winner and self.draw_ids:
            prev = self.draw_ids.sorted("sequence")[-1].winner_participant_id
            if prev:
                prev.won = True
        eligible = self._eligible_participants()
        if not eligible:
            raise UserError(_("Aucun participant éligible pour le tirage."))
        wheel = [{"id": p.id, "name": p.name} for p in eligible]
        winner = random.choice(eligible)
        winner_index = eligible.ids.index(winner.id)
        sequence = len(self.draw_ids) + 1
        draw = self.env["event.raffle.draw"].create(
            {
                "raffle_id": self.id,
                "sequence": sequence,
                "winner_participant_id": winner.id,
                "winner_name": winner.name,
                "winner_email": winner.email,
                "prize": prize or False,
                "prize_description": prize_description or False,
            }
        )
        # Do NOT mark the new winner as removed yet (see above).
        if self.state == "draft":
            self.state = "in_progress"
        return {
            "draw_id": draw.id,
            "winner": {"id": winner.id, "name": winner.name},
            "winner_index": winner_index,
            "wheel": wheel,
        }
