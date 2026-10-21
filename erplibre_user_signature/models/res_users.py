# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""La signature de l'utilisateur, réservée à son propriétaire et aux
administrateurs."""

import base64

from lxml import etree
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.mimetypes import guess_mimetype

# Les formats d'image matricielle acceptés pour une signature ; le canevas du
# widget produit du PNG. Un SVG en est exclu : il peut porter du script.
SIGNATURE_MIMETYPES = ("image/png", "image/jpeg")


class ResUsers(models.Model):
    _inherit = "res.users"

    # Le propriétaire la lit et l'écrit par SELF_READABLE_FIELDS et
    # SELF_WRITEABLE_FIELDS, que base_user_signature déclare ; un rapport qui
    # l'imprime la lit en superutilisateur.
    digital_signature = fields.Image(groups="base.group_system")

    @api.constrains("digital_signature")
    def _check_digital_signature_format(self):
        """Refuse une signature qui n'est ni PNG ni JPEG.

        Le propriétaire écrit sa signature en superutilisateur, par
        SELF_WRITEABLE_FIELDS, ce qui lève aussi le refus du SVG que le
        champ binaire réserve aux non-administrateurs.
        """
        for user in self.with_context(bin_size=False):
            if user.digital_signature and (
                guess_mimetype(base64.b64decode(user.digital_signature))
                not in SIGNATURE_MIMETYPES
            ):
                raise ValidationError(
                    self.env._("A signature must be a PNG or JPEG image.")
                )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Refuse un domaine sur la signature hors administrateurs : le
        groupe du champ en protège le contenu, pas l'existence, qu'un
        ``('digital_signature', '!=', False)`` révélerait."""
        if not self.env.is_system() and domain:
            domain_fields = {
                term[0] for term in domain if isinstance(term, (tuple, list))
            }
            if "digital_signature" in domain_fields:
                raise AccessError(self.env._("Invalid search criterion"))
        return super()._search(domain, offset, limit, order)

    def _get_view_postprocessed(self, view, arch, **options):
        """Garde le libellé « Signature » dans « Mon profil » pour chacun.

        Le cœur lève la restriction de groupes des SELF_READABLE_FIELDS sur
        les seuls nœuds ``field`` de la vue des préférences ; un ``label``
        hérite des groupes de son champ et serait retiré aux non-admins.
        """
        arch, view_models = super()._get_view_postprocessed(
            view, arch, **options
        )
        if view == self.env.ref("base.view_users_form_simple_modif"):
            tree = etree.fromstring(arch)
            for node in tree.xpath("//label[@for][@__groups_key__]"):
                if node.get("for") in self.SELF_READABLE_FIELDS:
                    node.attrib.pop("__groups_key__")
            arch = etree.tostring(tree)
        return arch, view_models
