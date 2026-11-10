# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "ERPLibre DevOps Guide",
    "version": "18.0.1.2.0",
    "category": "Project",
    "summary": (
        "Render an implementation project's presentation pages from data: "
        "hero, sections, cards and live counts."
    ),
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "license": "AGPL-3",
    "application": False,
    # erplibre_devops_requirement apporte le menu racine sous lequel la
    # configuration des guides s'accroche, et le modèle que les décomptes
    # d'une page d'implémentation comptent le plus souvent. `web_tour`
    # fournit le service et le registre des visites que les cartes lancent.
    "depends": [
        "base",
        "web",
        "web_tour",
        "erplibre_devops_requirement",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/devops_guide_security.xml",
        "views/devops_guide_views.xml",
        "views/devops_requirement_views.xml",
        "views/devops_guide_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_devops_guide/static/src/guide/guide.scss",
            "erplibre_devops_guide/static/src/guide/guide.xml",
            "erplibre_devops_guide/static/src/guide/guide.js",
        ],
    },
    "installable": True,
}
