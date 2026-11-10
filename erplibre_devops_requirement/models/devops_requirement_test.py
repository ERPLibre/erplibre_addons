# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)

# Borne du journal conservé par résultat. Au-delà, seule la FIN est gardée :
# c'est elle qui porte l'assertion en échec et la trace d'appel.
LOG_MAX_LENGTH = 20000
LOG_TRUNCATED_MARK = "[...]\n"

RUNNER_GROUP = "erplibre_devops_requirement.group_devops_requirement_runner"


class DevopsRequirementTest(models.Model):
    """Test qui prouve un requis, et son dernier résultat connu.

    La ligne est déclarée en données par le projet ; un lanceur (script
    Selenium, visite guidée, suite Python) n'y écrit que son résultat, par
    `record_result`. Le triplet (requis, sorte, référence) identifie la
    ligne : c'est la clé qu'un lanceur connaît sans lire la base.
    """

    _name = "devops.requirement.test"
    _description = "Requirement test"
    _order = "requirement_id, sequence, id"

    requirement_id = fields.Many2one(
        "devops.requirement",
        string="Requirement",
        required=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Title", translate=True)
    kind = fields.Selection(
        [
            ("python", "Python test"),
            ("tour", "Guided tour"),
            ("selenium", "Selenium script"),
            ("manual", "Manual check"),
        ],
        string="Kind",
        required=True,
    )
    reference = fields.Char(
        string="Reference",
        required=True,
        help=(
            "Guided tour: the tour name. Python test: the dotted path of the "
            "test method. Selenium script: the script path, relative to the "
            "repository. Manual check: free text."
        ),
    )
    last_result = fields.Selection(
        [
            ("not_run", "Not run"),
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("error", "Error"),
            ("skipped", "Skipped"),
        ],
        string="Last result",
        default="not_run",
        required=True,
        index=True,
    )
    last_run = fields.Datetime(string="Last run")
    last_duration = fields.Float(string="Duration (s)")
    last_log = fields.Text(string="Last log")

    _sql_constraints = [
        (
            "requirement_kind_reference_uniq",
            "unique(requirement_id, kind, reference)",
            "A requirement cannot list the same test twice.",
        ),
    ]

    @api.depends("name", "reference")
    def _compute_display_name(self):
        # Le titre est facultatif : la référence le remplace, plutôt que
        # l'affichage générique « modèle,id ».
        for line in self:
            line.display_name = line.name or line.reference or ""

    @api.model
    def record_result(
        self, code, kind, reference, result, log=None, duration=None
    ):
        """Enregistre le résultat d'un test déclaré ; ne crée rien.

        Point d'écriture d'un lanceur externe, en XML-RPC ou en JSON-RPC.
        `code` désigne le requis, (`kind`, `reference`) la ligne de test.
        Rend True quand la ligne est mise à jour, False quand le requis ou
        la ligne n'existe pas, ou quand `code`, `kind` ou `reference` est
        vide : un lanceur qui se trompe de référence ne doit pas créer de
        traçabilité fantôme, et l'avertissement au journal le signale.

        Lève AccessError si l'appelant n'est ni du groupe des lanceurs ni
        administrateur, ValidationError si `result` n'est pas une valeur de
        `last_result`. L'écriture passe en sudo, bornée aux champs `last_*` :
        le lanceur n'a que la lecture sur le modèle.

        `log` est tronqué à LOG_MAX_LENGTH caractères, fin conservée ;
        `duration` est en secondes.
        """
        if not (
            self.env.is_superuser()
            or self.env.user.has_group(RUNNER_GROUP)
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError(
                _("Only a requirement test runner can record a test result.")
            )
        # Un code vide se lirait `code IS NULL` et désignerait le premier
        # requis sans code : le verdict tomberait sur un requis que
        # personne n'a nommé. Même garde pour la sorte et la référence.
        if not (code and kind and reference):
            _logger.warning(
                "Requirement test result ignored: empty code, kind or "
                "reference (%r, %r, %r)",
                code,
                kind,
                reference,
            )
            return False
        results = dict(self._fields["last_result"].selection)
        if result not in results:
            raise ValidationError(
                _(
                    "Unknown test result %(result)r, expected: %(expected)s.",
                    result=result,
                    expected=", ".join(results),
                )
            )
        requirement = (
            self.env["devops.requirement"]
            .sudo()
            .search([("code", "=", code)], limit=1)
        )
        if not requirement:
            _logger.warning(
                "Requirement test result ignored: no requirement %r", code
            )
            return False
        line = self.sudo().search(
            [
                ("requirement_id", "=", requirement.id),
                ("kind", "=", kind),
                ("reference", "=", reference),
            ],
            limit=1,
        )
        if not line:
            _logger.warning(
                "Requirement test result ignored: %r declares no %s test %r",
                code,
                kind,
                reference,
            )
            return False
        if log and len(log) > LOG_MAX_LENGTH:
            keep = LOG_MAX_LENGTH - len(LOG_TRUNCATED_MARK)
            log = LOG_TRUNCATED_MARK + log[-keep:]
        line.write(
            {
                "last_result": result,
                "last_run": fields.Datetime.now(),
                "last_duration": float(duration or 0.0),
                # Un appel sans journal efface celui du lancement précédent :
                # garder l'ancien le ferait passer pour celui-ci.
                "last_log": log or False,
            }
        )
        return True
