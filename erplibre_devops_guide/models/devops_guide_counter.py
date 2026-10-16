# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import ast
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class DevopsGuideCounterMixin(models.AbstractModel):
    """Résout un décompte décrit par un nom de modèle et un domaine texte.

    Le domaine est stocké en texte pour qu'un projet le pose en données
    sans code. `_count_records` rend TOUJOURS un entier : un modèle absent
    du registre, un domaine illisible, un domaine qui n'est pas une liste
    et un refus de droit d'accès rendent 0 et laissent une trace. Une page
    de présentation ne doit jamais empêcher l'ouverture d'un écran.

    Le domaine est lu par `ast.literal_eval`, qui n'évalue que des
    littéraux : aucun appel, aucun nom, donc rien à exécuter.
    """

    _name = "devops.guide.counter.mixin"
    _description = "Resolve a declared record count"

    count_model = fields.Char(
        string="Counted model",
        help="Technical name of the model to count, e.g. devops.requirement.",
    )
    count_domain = fields.Char(
        string="Counted domain",
        default="[]",
        help="Odoo domain as a literal list, e.g. [('done', '=', True)].",
    )

    def _count_records(self, model_name, domain_text):
        if not model_name:
            return 0
        if model_name not in self.env:
            _logger.warning("Guide counter: unknown model %r", model_name)
            return 0
        try:
            domain = ast.literal_eval(domain_text or "[]")
        except (ValueError, SyntaxError):
            _logger.warning("Guide counter: unreadable domain %r", domain_text)
            return 0
        if not isinstance(domain, list):
            _logger.warning(
                "Guide counter: domain is not a list %r", domain_text
            )
            return 0
        try:
            # Le point de sauvegarde est indispensable : une erreur SQL
            # (valeur de mauvais type) avorte la transaction, et attraper
            # l'exception Python ne la rétablit pas. Sans lui, la requête
            # suivante de la même requête HTTP échouerait.
            with self.env.cr.savepoint():
                return self.env[model_name].search_count(domain)
        except Exception:
            # Champ inconnu, domaine mal formé, droit refusé : la page
            # s'affiche quand même, avec un zéro.
            _logger.warning(
                "Guide counter: cannot count %r on %r",
                domain,
                model_name,
                exc_info=True,
            )
            return 0
