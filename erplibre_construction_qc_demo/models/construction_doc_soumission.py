# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import logging
import math

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ConstructionDocSoumission(models.Model):
    _name = "construction.doc_soumission"
    _description = "Soumission de chantier (mirror)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "numero_soumission"
    _order = "numero_soumission, id"

    numero_soumission = fields.Char(tracking=True)
    nom_chantier = fields.Char(tracking=True)
    code_projet = fields.Char(tracking=True)
    entrepreneur_name = fields.Char(string="Entrepreneur", tracking=True)
    montant = fields.Float(tracking=True)
    date_soumission = fields.Date(tracking=True)
    statut = fields.Char(tracking=True)
    actif = fields.Boolean(tracking=True)
    coordonnees_gps = fields.Char(
        string="Coordonnées GPS",
        help="Position du chantier au format « latitude, longitude ».",
        tracking=True,
    )
    # Pas de digits= : on garde la double précision native (float8),
    # idéale pour des coordonnées GPS et sans rendre la précision
    # trompeuse (Odoo ignore le 1er élément du tuple digits).
    latitude = fields.Float(
        string="Latitude",
        compute="_compute_lat_lon",
        store=True,
        help="Latitude décimale extraite de coordonnees_gps "
        "(prête pour une carte Leaflet).",
    )
    longitude = fields.Float(
        string="Longitude",
        compute="_compute_lat_lon",
        store=True,
        help="Longitude décimale extraite de coordonnees_gps "
        "(prête pour une carte Leaflet).",
    )
    file_no_line = fields.Integer(string="No line spreadsheet", tracking=True)
    project_id = fields.Many2one(
        comodel_name="project.project", string="Chantier", tracking=True
    )

    @api.depends("coordonnees_gps")
    def _compute_lat_lon(self):
        """Parse « lat, lon » en deux flottants pour l'affichage carte.

        Une valeur vide ou mal formée laisse les deux champs à 0.0
        afin de ne jamais bloquer l'import de la soumission. Le 0.0
        sert donc à la fois de « non géolocalisé » et de « parsing
        échoué » : une couche carte devrait ignorer les soumissions
        dont coordonnees_gps est rempli mais lat == lon == 0.0.
        """
        for rec in self:
            lat = lon = 0.0
            raw = (rec.coordonnees_gps or "").strip()
            if raw:
                parts = raw.split(",")
                ok = False
                if len(parts) == 2:
                    try:
                        lat = float(parts[0].strip())
                        lon = float(parts[1].strip())
                        # float() accepte « nan »/« inf » : on les
                        # rejette pour ne jamais propager un non-fini
                        # (qui ferait planter float_round à l'écriture).
                        ok = math.isfinite(lat) and math.isfinite(lon)
                    except ValueError:
                        ok = False
                if not ok:
                    lat = lon = 0.0
                    _logger.warning(
                        "Coordonnée GPS illisible pour %s : %r",
                        rec.numero_soumission or rec.id,
                        rec.coordonnees_gps,
                    )
            rec.latitude = lat
            rec.longitude = lon
