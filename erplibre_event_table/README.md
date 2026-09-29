# Event Rotating Tables

[![License: AGPL-3](https://img.shields.io/badge/license-AGPL--3-blue.svg)](http://www.gnu.org/licenses/agpl-3.0-standalone.html)

Seat event participants at rotating tables over several rounds, compare a few
proposals, pick one, and adjust it by hand on a floor plan.

## Description

Turn on **Rotating Tables** on an event (or on an event template, which passes
it on to new events). From the event, add the people who take part: attendees,
other contacts, or guests typed straight into the list. Configure the tables
and their seats, then generate several combinations. Each one is measured by
the same indicators — among them colleague pairs, repeated meetings, table
returns, and people met (minimum and average) — and compared to a **proven
minimum**, so the differences between proposals are visible rather than a
matter of taste.

The floor plan is the working surface throughout: move a table, resize it,
switch it between round and square, then drag people from seat to seat, swap
two of them, seat a latecomer waiting in the tray, or pull someone out of a
round. Before any combination exists the same gesture reserves a seat rather
than taking one, and those reservations constrain the generation to come.
Every change to a seating is recorded in the chatter and the indicators
follow.

## Features

- Rotating tables option on `event.type` and `event.event`.
- Table configurator: number of tables, seats per table, replace the tables or
  add more after the last one.
- Participants from registrations (registered and attended, or attended only),
  from contacts, or typed in by hand. Registrations booked by the same contact
  become one participant.
- Options per plan: separate colleagues, new neighbours each round, new table
  each round, assign seats; number of rounds; number of combinations.
- Display options per plan: show a seat's own number, show each guest's
  company, show whole names — a long name then wraps onto a second line in
  the list beside its table instead of being cut at the column's width, and
  the plan spaces its tables for the wider lists, keeping room for that
  second line chip by chip, for the names long enough to need it and for
  no others — and a visual
  mode that draws real wooden tables and fabric chairs, auto-sized to each
  table's own seat count, instead of a resizable box.
- Synchronous generation of several comparable combinations, with a proven
  minimum and a diagnostic when the configuration cannot avoid every conflict.
- Floor plan by round: drag and drop, highlight a participant, zoom, fit to
  window, full screen, rearrange tables on a grid.
- Adding, excluding and removing people stays possible after a combination is
  chosen; latecomers wait in the tray and are seated by hand.
- Outputs: one PDF per participant, one sheet per table, and an email to each
  participant with their tables.

## Usage

1. Open an event, tick **Rotating Tables**.
2. Click **Add Rotating Table Participants** in the header. Pick the
   registration scope, add other contacts, confirm: the plan is created.
3. On the plan, click **Configure Tables**: number of tables and seats per
   table. The banner compares participants and seats.
4. Set the rounds, the number of combinations and the options, then click
   **Generate Combinations**. Or seat people by hand first: in the **Floor
   Plan** tab, drag someone onto a table and the plan reserves that seat for
   them. A **Reservations** badge says so, and the banner counts who is still
   to place. **Retain This Placement** then holds the reservations and lets
   the generator seat everyone else around them.
5. Compare the proposals in the **Combinations** tab, **Preview** one, then
   **Choose** it.
6. Open the **Floor Plan** tab, or **Full Screen**, to adjust: drag a person
   onto a free seat to move them, onto another person to swap them, onto the
   tray to pull them out of the round.
7. Print the participant cards and the table sheets, or send each participant
   their tables by email.

### States

**Draft**, **Proposed** and **Chosen** order the work without restricting it:
click the status bar to move between them, and nothing is deleted on the way.
Generations accumulate, so several settings can be compared side by side;
**Clear All** prunes the list and keeps the chosen combination.

**Locked** is the one state with teeth. It refuses every change — rounds,
options, tables, participants, and the position of a table on the screen —
while reading, printing and sending stay open. Only the **Lock** and
**Unlock** buttons enter and leave it; unlocking returns the plan to the
state that fits what it holds. To cure a crowded layout on a locked plan,
unlock, use **Rearrange Tables**, and lock again.

To start over without losing the current plan, duplicate it from the
**Actions** menu of the form: the copy keeps the tables, the people and the
reserved seats, and comes back as a draft.

## Configuration

No configuration is required. One system parameter tunes the generation:

| Parameter | Default | Effect |
|---|---|---|
| `erplibre_event_table.search_time_budget` | `10` | Total search budget in seconds for one generation, clamped to 1..45. |

The budget covers the whole generation, not one combination, which keeps the
request under the server's own time limits.

## Development

```bash
# Tests, on a FRESH database (explicit ports: Odoo's test mode still opens
# an HTTP server even with --stop-after-init, and 8069 is usually already
# taken by a running instance). Fresh matters for the WARNING count too:
# reusing an existing database can carry a stray WARNING from demo data
# already loaded into it, which a clean --drop then --database avoids.
./odoo_bin.sh db --drop --database test_erplibre_event_table
./test.sh -d test_erplibre_event_table --db-filter test_erplibre_event_table \
    -i erplibre_event_table --test-tags /erplibre_event_table \
    --http-port=18069 --gevent-port=18072

# JS tests, in a browser. "debug=assets" is NOT decoration: without it the
# instance serves the minified asset bundle it already has in cache, so an
# edited test file re-runs its OLD version, silently, with an identical
# failure count. The LIST of asset files is frozen separately and is not
# lifted by debug mode at all: a NEW test file appears only after the
# instance is restarted.
./run.sh -d test_erplibre_event_table --db-filter test_erplibre_event_table \
    --http-port=18069 --gevent-port=18072
# then open
# http://localhost:18069/web/tests?filter=@erplibre_event_table&debug=assets

# The same suite with no human at the keyboard: opens that URL, waits for
# the suite to end, names the red tests, and exits non-zero if one failed.
# Reads the result from the hoot runner object rather than the console,
# which hoot captures as it loads. Add --gecko_binary_path when geckodriver
# is not on PATH.
.venv.erplibre/bin/python \
    odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/selenium/run_hoot_tests.py \
    --url http://127.0.0.1:18069 --no_dark_mode --headless

# Every Owl template under static/src/ actually COMPILES: catches a
# template-language mistake (e.g. Python's "not" instead of "!") that
# breaks the whole widget at browser load time, on a machine with no
# browser at all. Needs jsdom, a devDependency of the repository root
# (package.json) — an ordinary `npm install` there, once, is enough;
# nothing below needs NODE_PATH or a scratch install. Compiling is not
# rendering: a t-call to a template that does not exist compiles
# cleanly here and fails only in a real browser, at render time — this
# check cannot catch it.
node odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/static/tests/check_templates_compile.mjs

# The PURE JS tests actually RUN, on a machine with no browser at all:
# geometry.js has no Odoo import and no DOM, so every "*.test.js" under
# static/tests/ is discovered and run against a minimal @odoo/hoot shim.
# Plain node, no dependency. floor_plan.test.js is the exception — it
# mounts an Owl component against a real DOM — and the run names it as
# skipped rather than leaving it out silently. The shim implements two
# matchers (toBe, toEqual) and refuses to run at all if a test file
# starts using a third, so its green is never wider than what it
# checked; the browser run above stays the reference for the rest.
node odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/static/tests/run_geometry_under_node.mjs

# Formatting
./script/maintenance/format.sh \
    ./odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table

# Translations: export the template, then update fr_CA.po by hand
# against it and check the result (a second --i18n-export -l fr_CA is
# not used here: Odoo drops any translation identical to its English
# source, such as "ID" or "Table", so it would silently blank them)
./odoo_bin.sh -d test_erplibre_event_table --modules=erplibre_event_table \
    --i18n-export=odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/i18n/erplibre_event_table.pot
msgfmt --check -o /dev/null odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/i18n/fr_CA.po
```

The rotation library under `rotation/` imports nothing from Odoo and is tested
without a database; see `tests/test_rotation_*.py`.

## Known issues / Roadmap

- Dense configurations — few large tables, many rounds — do not always reach
  the proven minimum; the screen then shows the best found next to that
  minimum, and the diagnostic suggests a number of tables that makes an
  algebraic plan applicable.
- Regenerating from a given round while freezing the previous ones, background
  computation, several rooms per plan and a portal view are out of scope.
- Visual mode's auto-computed table footprint, and the band each table's name
  list occupies beside it, both apply only where table positions are freshly
  computed (Configure Tables, Rearrange Tables): turning an option on or off
  moves no table already placed, and neither does upgrading the module when a
  spacing term itself changes. A plan laid out under an earlier spacing draws
  its lists across the next table over — legible, but wrong — until one of
  those two actions runs again. Rearrange Tables is therefore offered in every
  state but locked: it writes nothing but table positions, and a plan already
  chosen is exactly the one that cannot be configured afresh. A locked plan
  refuses it like every other write, so curing a crowded layout there means
  unlocking first.

## Bug Tracker

Report issues through the ERPLibre repository tracker.

## Credits

### Authors

- TechnoLibre

### Contributors

- Mathieu Benoit

### Maintainers

This module is maintained as part of ERPLibre.

---

# Tables tournantes d'événement

Place les participants d'un événement à des tables tournantes sur plusieurs
tours, compare quelques propositions, en fait choisir une, puis la laisse
retoucher à la main sur un plan de salle.

## Description

Activez **Tables tournantes** sur un événement (ou sur un gabarit d'événement,
qui le transmet aux nouveaux événements). Depuis l'événement, ajoutez les
personnes : inscrits, autres contacts, ou invités saisis directement dans la
liste. Configurez les tables et leurs sièges, puis générez plusieurs
combinaisons. Chacune est mesurée par les mêmes indicateurs — dont les paires
de collègues, les rencontres répétées, les retours à une table, et les
personnes rencontrées (minimum et moyenne) — et comparée à un **minimum
prouvé**, ce qui rend les écarts entre propositions visibles plutôt qu'affaire
de goût.

Le plan de salle est le plan de travail d'un bout à l'autre : déplacez une
table, redimensionnez-la, passez-la de ronde à carrée, puis glissez les
personnes d'un siège à l'autre, échangez-en deux, asseyez un retardataire qui
attend dans la réserve, ou retirez quelqu'un d'un tour. Avant qu'une
combinaison existe, le même geste réserve une place au lieu de l'attribuer, et
ces réservations contraignent la génération à venir. Chaque modification d'un
placement est tracée au chatter et les indicateurs suivent.

## Fonctions

- Option de tables tournantes sur `event.type` et `event.event`.
- Configurateur : nombre de tables, sièges par table, remplacer les tables ou
  en ajouter à la suite.
- Participants issus des inscriptions (inscrits et présents, ou présents
  seulement), de contacts, ou saisis à la main. Les inscriptions réservées par
  un même contact deviennent un seul participant.
- Options par plan : séparer les collègues, nouveaux voisins à chaque tour,
  nouvelle table à chaque tour, attribuer les sièges ; nombre de tours ; nombre
  de combinaisons.
- Options d'affichage par plan : afficher le numéro d'un siège, afficher
  l'entreprise de chaque invité, afficher les noms en entier — un nom long
  passe alors à la ligne dans la liste à côté de sa table au lieu d'être
  coupé à la largeur de la colonne, et le plan espace ses tables pour les
  listes élargies, en ne gardant la place de cette seconde ligne que puce
  par puce, pour les noms assez longs pour en avoir besoin et pour aucun
  autre — et un mode visuel qui dessine
  de vraies tables en bois et des chaises en tissu, dimensionnées
  automatiquement selon le nombre de sièges de chaque table, au lieu d'un
  rectangle redimensionnable.
- Génération synchrone de plusieurs combinaisons comparables, avec minimum
  prouvé et diagnostic quand la configuration ne permet pas d'éviter tout
  conflit.
- Plan de salle par tour : glisser-déposer, mise en évidence d'une personne,
  zoom, ajustement à la fenêtre, plein écran, réorganisation en grille.
- Ajouter, exclure ou retirer une personne reste possible après le choix d'une
  combinaison ; les retardataires attendent dans la réserve et se placent à la
  main.
- Sorties : un PDF par participant, une feuille par table, et un courriel à
  chaque participant avec ses tables.

## Usage

1. Ouvrir un événement, cocher **Tables tournantes**.
2. Cliquer **Ajouter des personnes aux tables tournantes** dans l'en-tête.
   Choisir la portée des inscriptions, ajouter d'autres contacts, confirmer :
   le plan est créé.
3. Sur le plan, cliquer **Configurer les tables** : nombre de tables et sièges
   par table. Le bandeau compare participants et sièges.
4. Régler les tours, le nombre de combinaisons et les options, puis cliquer
   **Générer les combinaisons**. Ou placer d'abord des gens à la main : dans
   l'onglet **Plan de salle**, glisser quelqu'un sur une table et le plan lui
   réserve cette place. Un badge **Réservations** le signale, et le bandeau
   compte qui reste à placer. **Retenir ce placement** tient ensuite les
   réservations et laisse le générateur asseoir tous les autres autour.
5. Comparer les propositions dans l'onglet **Combinaisons**, en ouvrir une en
   **Aperçu**, puis la **Choisir**.
6. Ouvrir l'onglet **Plan de salle**, ou le **Plein écran**, pour retoucher :
   glisser une personne sur un siège libre pour la déplacer, sur une autre
   personne pour les échanger, sur la réserve pour la retirer du tour.
7. Imprimer les cartes des participants et les feuilles de table, ou envoyer à
   chaque participant ses tables par courriel.

### États

**Brouillon**, **Proposé** et **Retenu** ordonnent le travail sans le
restreindre : cliquer la barre d'état pour passer de l'un à l'autre, et rien
n'est supprimé en chemin. Les générations s'accumulent, ce qui permet de
comparer plusieurs réglages côte à côte ; **Tout effacer** élague la liste en
gardant la combinaison retenue.

**Bloqué** est le seul état qui ait des dents. Il refuse toute modification —
tours, options, tables, participants, et la position d'une table à l'écran —
la lecture, l'impression et l'envoi restant ouverts. Seuls les boutons
**Bloquer** et **Débloquer** y entrent et en sortent ; le déblocage ramène le
plan à l'état qui correspond à ce qu'il porte. Pour corriger un affichage
encombré sur un plan bloqué : débloquer, **Réorganiser les tables**, rebloquer.

Pour repartir d'une base propre sans perdre le plan en cours, le dupliquer
depuis le menu **Actions** du formulaire : la copie garde les tables, les
personnes et les places réservées, et revient en brouillon.

## Configuration

Aucune configuration requise. Un paramètre système règle la génération :

| Paramètre | Défaut | Effet |
|---|---|---|
| `erplibre_event_table.search_time_budget` | `10` | Budget total de recherche, en secondes, pour une génération ; borné à 1..45. |

Le budget couvre toute la génération, et non une combinaison, ce qui garde la
requête sous les limites de temps du serveur.

## Développement

Les commandes sont celles de la section anglaise ci-dessus ; elles se lancent
depuis la racine du dépôt. La bibliothèque `rotation/` n'importe rien d'Odoo et
se teste sans base de données : voir `tests/test_rotation_*.py`.

Trois limites à connaître avant de lire leurs résultats : les tests ne comptent
zéro `WARNING` que sur une base FRAÎCHE — une base déjà chargée peut porter un
`WARNING` isolé venu de ses propres données de démonstration, sans rapport
avec le code. Et `check_templates_compile.mjs` prouve la compilation, jamais
le rendu : un `t-call` vers un gabarit inexistant compile sans erreur ici et
n'échoue que dans un vrai navigateur, au moment du rendu. Enfin,
`run_geometry_under_node.mjs` ne couvre que les fichiers de test purs : il
annonce ceux qu'il lit comme ceux qu'il écarte, et s'arrête avant d'exécuter
le moindre test si l'un d'eux emploie un comparateur que son shim
n'implémente pas.

## Anomalies connues / Suite

- Les configurations denses — peu de grandes tables, beaucoup de tours —
  n'atteignent pas toujours le minimum prouvé ; l'écran affiche alors le
  meilleur trouvé à côté de ce minimum, et le diagnostic propose un nombre de
  tables qui rend un plan algébrique applicable.
- Régénérer à partir d'un tour en figeant les précédents, le calcul en arrière-
  plan, plusieurs salles par plan et une vue portail sont hors périmètre.
- Le format de table auto-calculé du mode visuel, et la bande qu'occupe à côté
  de chaque table la liste de ses noms, ne s'appliquent que là où les positions
  sont recalculées (Configurer les tables, Réorganiser les tables) : activer ou
  désactiver une option ne déplace aucune table déjà placée, et une mise à jour
  du module qui change un terme d'espacement non plus. Un plan disposé sous un
  espacement antérieur dessine ses listes par-dessus la table voisine —
  lisible, mais faux — tant que l'une de ces deux actions n'a pas tourné.
  Réorganiser les tables est donc offert dans tous les états sauf bloqué : il
  n'écrit que des positions de table, et un plan déjà retenu est justement
  celui qu'on ne peut pas reconfigurer. Un plan bloqué le refuse comme toute
  autre écriture, il faut donc le débloquer d'abord.

## Suivi des anomalies

Signaler les anomalies via le suivi du dépôt ERPLibre.

## Crédits

### Auteurs

- TechnoLibre

### Contributeurs

- Mathieu Benoit

### Mainteneurs

Ce module est maintenu dans le cadre d'ERPLibre.
