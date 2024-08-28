#!/usr/bin/env python3
# © 2021-2024 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

{
    "name": "Survey matrix selection",
    "version": "16.0.1.0.0",
    "category": "Extra Tools",
    "summary": "Enhance your survey matrix type with selection",
    "description": "Add feature selection into matrix for your survey. This permit support for mobile with 1 choise.",
    "author": "TechnoLibre",
    "company": "TechnoLibre",
    "maintainer": "TechnoLibre",
    "website": "https://www.technolibre.ca",
    "images": [
        "static/description/icon.png",
    ],
    "depends": ["base", "survey", "website", "enhanced_survey_management"],
    "data": [
        "views/survey_templates.xml",
        "views/survey_question_views.xml",
        "views/survey_templates_print.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "survey_matrix_selection/static/src/js/survey_submit.js",
        ]
    },
    "license": "AGPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
}
