# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import Command, api, models

# Challenges of the gamification data that target every internal user.
NATIVE_CHALLENGES = (
    "gamification.challenge_base_discover",
    "gamification.challenge_base_configure",
)


class GamificationChallenge(models.Model):
    _inherit = "gamification.challenge"

    @api.model
    def _linkup_close_native_challenges(self):
        """Close the native challenges, which would give every member Odoo
        goals unrelated to LinkUp (LU-NF-033).

        Their users and running goals are removed first: closing a
        challenge posts its result to its users.
        """
        for xmlid in NATIVE_CHALLENGES:
            challenge = self.env.ref(xmlid, raise_if_not_found=False)
            if not challenge or challenge.state == "done":
                continue
            challenge = challenge.sudo()
            self.env["gamification.goal"].sudo().search(
                [("challenge_id", "=", challenge.id)]
            ).unlink()
            challenge.write({"user_ids": [Command.clear()]})
            challenge.write({"state": "done"})
