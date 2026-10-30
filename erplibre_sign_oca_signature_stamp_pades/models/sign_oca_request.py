# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le champ de signature PAdES d'une case qui porte un cachet."""

from odoo import models


class SignOcaRequest(models.Model):
    _inherit = "sign.oca.request"

    def _pades_item_rect(self, item, box):
        """Rend le rectangle ``outer`` du cachet quand ``item`` en porte un,
        sinon celui de sign_oca_pades.

        Le rectangle sert à créer le champ et à poser son apparence, qui
        coupe tout ce qui en sort. Il est égal à la case avec les lignes
        dans la case, et la prolonge vers le bas avec les lignes dessous.
        Les champs sont créés à l'envoi de la demande, quand un certificat
        de scellement est configuré : un réglage changé ensuite n'agrandit
        plus ceux d'une demande déjà envoyée.
        """
        __, geometry = self._get_sign_stamp_layout(item, box)
        if geometry:
            return geometry["outer"]
        return super()._pades_item_rect(item, box)
