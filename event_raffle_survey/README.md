# Event Raffle Survey (Tirage par sondage)

[![License: AGPL-3](https://img.shields.io/badge/license-AGPL--3-blue.svg)](http://www.gnu.org/licenses/agpl-3.0-standalone.html)

Draw an event raffle among the respondents of a survey. The French version
follows the English one.

## Description

Adds the *Survey filled only* choice to the **Start a Raffle** wizard of an
event, from the `event_raffle` module. Pick a survey: its respondents enter the
raffle instead of the event's registrations.

The two *Questionnaire* choices of `event_raffle` are a different thing: they
keep the registrations that answered the event's own registration questions.

## Usage

The buttons below keep their French labels in every language, as in
`event_raffle`.

1. Open an event, then click **Démarrer un tirage**: the *Start a Raffle*
   dialog opens.
2. Under **Participants**, choose *Survey filled only*, then pick the
   **Survey**. Closed surveys are listed too: closing a survey archives it, and
   the draw usually comes after.
3. Click **Démarrer**. The survey's respondents become the raffle's
   participants, with the *Survey* source. The event's registrations are not
   copied.

## Who enters

An answer counts when it is completed, is not a test entry, and answers at
least one question. Ending a live session marks every answer of the survey
completed, even one that was only opened: the last condition keeps those out.

Each answer is identified by its contact, else by its email (whatever its
case, and `"Name" <address>` included), else by its nickname. Answers sharing
that identifier enter once, and the oldest of them names the participant: the
contact's name, else the nickname, else the email, else *Guest*. The
participant's email is the one the answer carries.

The identifier is a single one per answer: an answer linked to a contact and
an anonymous answer giving the same email stay two entries.

## Access rights

Reading a survey's answers needs the *Surveys: User* access right, which Odoo
gives every internal user when the survey module is installed. An event user
without it gets Odoo's access error: the module never reads the answers as
superuser, so a survey restricted to some users stays restricted.

Only non-specialised surveys are offered (survey, live session, assessment,
custom): a recruitment survey keeps its answers to the Recruitment app.

## Known issues / Roadmap

- A survey left with Odoo's default settings (anyone with the link, no login)
  gives respondents with no contact, email or nickname. Each one enters as a
  separate *Guest*, and a guest who wins cannot be identified. For a raffle,
  require login, invite people, or add a question saved as email or nickname.

## Development

```bash
# Tests of both modules, on a fresh database (explicit ports: Odoo's test
# mode opens an HTTP server even with --stop-after-init).
./odoo_bin.sh db --drop --database test_event_raffle_survey
./test.sh -d test_event_raffle_survey --db-filter test_event_raffle_survey \
    -i event_raffle_survey --test-tags /event_raffle,/event_raffle_survey \
    --http-port=18069 --gevent-port=18072

# Formatting
./script/maintenance/format.sh \
    ./odoo18.0/addons/ERPLibre_erplibre_addons/event_raffle_survey

# Translations: export the template, then update fr_CA.po by hand against it
# and check the result (an export with -l fr_CA would blank every translation
# identical to its source)
./odoo_bin.sh -d test_event_raffle_survey --modules=event_raffle_survey \
    --i18n-export=odoo18.0/addons/ERPLibre_erplibre_addons/event_raffle_survey/i18n/event_raffle_survey.pot
msgfmt --check -o /dev/null \
    odoo18.0/addons/ERPLibre_erplibre_addons/event_raffle_survey/i18n/fr_CA.po
```

## Credits

### Authors

- TechnoLibre

### Contributors

- Mathieu Benoit

### Maintainers

This module is maintained as part of ERPLibre.

---

# Event Raffle Survey (Tirage par sondage) — français

Tirer au sort un gagnant d'événement parmi les répondants d'un sondage.

## Description

Ajoute le choix *Sondage rempli seulement* à l'assistant **Démarrer un
tirage** d'un événement, issu du module `event_raffle`. Choisissez un sondage :
ses répondants entrent dans le tirage à la place des inscrits de l'événement.

Les deux choix *Questionnaire* d'`event_raffle` sont autre chose : ils gardent
les inscrits qui ont répondu aux questions d'inscription de l'événement.

## Utilisation

1. Ouvrir un événement, puis cliquer **Démarrer un tirage**.
2. Dans **Participants**, choisir *Sondage rempli seulement*, puis le
   **Sondage**. Les sondages fermés sont proposés aussi : fermer un sondage
   l'archive, et le tirage vient souvent après.
3. Cliquer **Démarrer**. Les répondants du sondage deviennent les participants
   du tirage, avec la source *Sondage*. Les inscrits de l'événement ne sont pas
   copiés.

## Qui entre

Une participation compte si elle est terminée, n'est pas un test et répond à
au moins une question. Terminer une session en direct marque terminées toutes
les participations du sondage, même celles qui ont seulement été ouvertes : la
dernière condition les écarte.

Chaque participation est identifiée par son contact, sinon par son courriel
(quelle qu'en soit la casse, `"Nom" <adresse>` compris), sinon par son pseudo.
Les participations qui partagent cet identifiant n'entrent qu'une fois, et la
plus ancienne donne le nom : celui du contact, sinon le pseudo, sinon le
courriel, sinon *Invité*. Le courriel du participant est celui que porte la
participation.

L'identifiant est unique par participation : une participation liée à un
contact et une participation anonyme qui donne le même courriel restent deux
entrées.

## Droits d'accès

Lire les participations d'un sondage demande le droit *Sondages :
Utilisateur*, qu'Odoo donne à tout utilisateur interne quand le module
`survey` s'installe. Un utilisateur des événements qui ne l'a pas reçoit
l'erreur d'accès d'Odoo : le module ne lit jamais les participations en
superutilisateur, et un sondage réservé à certains utilisateurs le reste.

Seuls les sondages non spécialisés sont proposés (sondage, session en direct,
évaluation, personnalisé) : un sondage de recrutement garde ses participations
pour l'application Recrutement.

## Problèmes connus / Feuille de route

- Un sondage aux réglages par défaut d'Odoo (toute personne ayant le lien,
  sans connexion) donne des répondants sans contact, courriel ni pseudo.
  Chacun entre comme un *Invité* distinct, et un invité qui gagne ne peut pas
  être identifié. Pour un tirage, exiger la connexion, inviter les
  participants, ou ajouter une question enregistrée comme courriel ou pseudo.

## Développement

Les commandes de test, de formatage et de traduction sont celles de la section
*Development* ci-dessus.

## Crédits

### Auteurs

- TechnoLibre

### Contributeurs

- Mathieu Benoit

### Mainteneurs

Ce module est maintenu dans le cadre d'ERPLibre.
