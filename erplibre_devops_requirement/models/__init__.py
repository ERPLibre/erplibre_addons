# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
# isort: skip_file
# L'ordre compte et n'est PAS alphabétique : le mixin abstrait doit être
# au registre avant les modèles qui en héritent. `_build_model` lève
# « Model %r inherits from non-existing model %r » sinon, et le module ne
# s'installe plus. Trier ces lignes casse le chargement.
from . import devops_requirement_classifier
from . import devops_requirement_category
from . import devops_requirement_phase
from . import devops_requirement
