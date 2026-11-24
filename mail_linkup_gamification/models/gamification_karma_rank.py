# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import api, models

# The native ranks, each replaced by the LinkUp rank of the same level.
NATIVE_RANKS = {
    "rank_newbie": "rank_spark",
    "rank_student": "rank_flame",
    "rank_bachelor": "rank_fire",
    "rank_master": "rank_blaze",
    "rank_doctor": "rank_sun",
}


class GamificationKarmaRank(models.Model):
    _inherit = "gamification.karma.rank"

    @api.model
    def _linkup_replace_native_ranks(self):
        """Replace the native ranks, Newbie to Doctor, by those of LinkUp
        (LU-F-102 RM1).

        Each native rank is deleted, and its external id then names the
        LinkUp rank of the same level: an update of ``gamification`` finds
        its noupdate records in place and creates none again. The ranks of
        the users with karma are computed again.
        """
        Data = self.env["ir.model.data"].sudo()
        replaced = False
        for native, linkup in NATIVE_RANKS.items():
            data = Data.search(
                [("module", "=", "gamification"), ("name", "=", native)]
            )
            rank = self.env.ref(
                f"mail_linkup_gamification.{linkup}", raise_if_not_found=False
            )
            if not data or not rank or data.res_id == rank.id:
                continue
            old = self.sudo().browse(data.res_id).exists()
            data.write({"res_id": rank.id})
            if old:
                old.unlink()
            replaced = True
        if replaced:
            self.env["res.users"].sudo().search(
                [("karma", "!=", 0)]
            )._recompute_rank()
