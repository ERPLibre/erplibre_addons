# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Event Raffle Survey (Tirage par sondage)",
    "version": "18.0.1.0.0",
    "summary": "Draw a raffle among the respondents of a survey",
    # Rendered as RST on the Apps page: the module is no application (see
    # `application` below) and has no static/description/index.html. A list
    # or an indented line that no blank line sets apart either logs a
    # docutils warning or renders as something else, so the text keeps to
    # plain paragraphs.
    "description": """
English

Adds the "Survey filled only" choice to the Start a Raffle wizard of an
event. Pick a survey: its respondents enter the raffle instead of the
event's registrations. An answer counts when it is completed, is not a
test entry and answers at least one question. Answers sharing an
identifier enter once: the contact, else the email, else the nickname.

Optionally, list required questions of the survey: only the respondents
who answered each of them, or at least one, then enter.

Drawing from a survey needs the Surveys: User access right.

Français

Ajoute le choix « Sondage rempli seulement » à l'assistant « Démarrer un
tirage » d'un événement. Choisissez un sondage : ses répondants entrent
dans le tirage à la place des inscrits de l'événement. Une participation
compte si elle est terminée, n'est pas un test et répond à au moins une
question. Les participations qui partagent un identifiant n'entrent
qu'une fois : le contact, sinon le courriel, sinon le pseudo.

En option, listez des questions exigées du sondage : seuls les répondants
qui ont répondu à chacune, ou à au moins une, entrent alors.

Tirer depuis un sondage demande le droit d'accès Sondages : Utilisateur.
""",
    "author": "TechnoLibre",
    "website": "https://technolibre.ca",
    "category": "Marketing/Events",
    "license": "AGPL-3",
    "depends": ["event_raffle", "survey"],
    "data": [
        "wizard/event_raffle_start_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
