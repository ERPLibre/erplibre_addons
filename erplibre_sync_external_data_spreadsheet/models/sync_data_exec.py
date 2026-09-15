import base64
import logging
from datetime import datetime, time
from io import BytesIO

import pytz
from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    # Odoo 18 tourne sous Py>=3.10; openpyxl est la lib la plus sûre pour .xlsx
    import openpyxl
except Exception as e:
    openpyxl = None
_logger = logging.getLogger(__name__)


class SyncDataExec(models.Model):
    _inherit = "sync.data.exec"

    file = fields.Binary(string="Fichier Excel (.xlsx)", required=True)
    filename = fields.Char(string="Nom du fichier")

    sheet_index = fields.Integer(
        string="Index de feuille (0 = première)",
        default=0,
        help="Sélectionne la feuille à lire dans le classeur.",
    )

    skip_header = fields.Boolean(
        string="Ignorer la première ligne (entête)",
        default=True,
    )

    skip_nb_lines = fields.Integer(
        string="Ignorer les premières lignes (entête)", default=-1
    )

    skip_end_nb_lines = fields.Integer(
        string="Ignorer les dernières lignes (entête)", default=-1
    )

    detected_rows = fields.Integer(string="Lignes détectées", readonly=True)
    imported_rows = fields.Integer(string="Lignes importées", readonly=True)

    def _ensure_openpyxl(self):
        if openpyxl is None:
            raise UserError(
                _(
                    "La bibliothèque Python 'openpyxl' n'est pas disponible.\n"
                    "Veuillez l'installer dans l'environnement serveur (ex: pip install openpyxl) puis réessayer."
                )
            )
