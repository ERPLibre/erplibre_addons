{
    "name": "Projet Dev Code - Claude Code Integration",
    "version": "18.0.1.0.0",
    "author": "TechnoLibre",
    "license": "AGPL-3",
    "website": "https://technolibre.ca",
    "category": "Project",
    "summary": "Lance un agent Claude Code depuis une tâche projet Odoo",
    "description": """
        Ajoute un onglet « Claude Code » dans les tâches projet Odoo.

        Fonctionnalités :
        - Champ workspace ERPLibre
        - Champ répertoire de travail
        - Champ nom du module à développer
        - Bouton pour démarrer un agent Claude Code (claude-agent-sdk)
        - Affichage en temps réel de l'output Claude
        - Bouton d'arrêt de l'agent
    """,
    "depends": ["project"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/project_task_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "projet_dev_code/static/src/css/projet_dev_code.css",
        ],
    },
    "installable": True,
    "application": False,
}
