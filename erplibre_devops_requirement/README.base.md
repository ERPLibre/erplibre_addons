<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->

<!-- [en] -->

# ERPLibre — software requirements (MoSCoW)

Tracks what a project **commits to deliver**: one requirement per line,
classified by domain and by phase, with its MoSCoW level and the state of its
delivery. Each requirement takes its place in the DevSecOps loop, carries its
threats and the list of the tests that prove it, with their last result.

The module ships **no requirement**. It ships the model, the screens and the
vocabulary; the requirements come from a project module, as data.

## The model

| | |
|---|---|
| `devops.requirement` | A requirement: code, title, domain, phase, MoSCoW level, priority, effort, owner, DevSecOps stage, acceptance criteria, dependencies. |
| `devops.requirement.threat` | A threat on a requirement, classified by STRIDE, with its mitigation and its residual risk. |
| `devops.requirement.test` | A test that proves a requirement, and its last known result. |
| `devops.requirement.category` | A functional domain. **Data**, not code. |
| `devops.requirement.phase` | A phase or a milestone. **Data**, not code. |
| `devops.requirement.classifier` | Abstract mixin: `code`, `name`, `sequence`, and the uniqueness of the code. |

### Why the domain is a model and the MoSCoW level a Selection

The rule fits in one sentence: **a Selection when the vocabulary is
universal, a model when it belongs to the project.**

MoSCoW has four values, the same everywhere, defined outside any project: it
is a Selection, and a project that wanted a fifth would no longer be dealing
with MoSCoW. Functional domains, on the other hand, only resemble each other
from one project to the next by accident — freezing them in code would force
every project to patch the shared module to name its own.

### The code carries counts

`code` is not a label: data files reference it, and the domains of the counted
figures of a presentation page compare against it. **Renaming it silently
breaks every count that relies on it** — the figure drops to zero without an
error, and the list its button opens arrives empty.

This is also the reason for the rights below.

The requirement's `code` is unique for the same reason: a test runner finds
the requirement by its code. It stays optional — several requirements without
a code coexist.

## DevSecOps planning

| Field | Role |
|---|---|
| `devsecops_stage` | Stage of the loop: plan, code, build, test, release, deploy, operate, monitor. Clickable status bar, kanban columns. The `code` value is labelled "Develop", so as not to share its translation with the `code` field. |
| `requirement_type` | Functional, non-functional, security, compliance, operational. |
| `acceptance_criteria` | Acceptance criteria, one Given / When / Then scenario per criterion. |
| `security_relevant`, `data_classification` | Whether the requirement touches security, and the most sensitive class of data it handles. |
| `depends_on_ids` / `dependent_ids` | What must be delivered before, what waits for this one. A cycle is refused, even through several hops. |

The DevSecOps stage **does not replace** the three booleans: the stage tells
where the work stands, `accepted` / `approved` / `done` what the client has
observed.

## Tests and their result

A test line is declared in data, by the project. Its `kind` tells what its
`reference` designates:

| `kind` | `reference` |
|---|---|
| `tour` | the name of the guided tour |
| `python` | the dotted path of the test method |
| `selenium` | the path of the script, relative to the repository |
| `manual` | free text |
| `repo_unittest` | a unit test of a repository: `<repository>:<path>::<Class>::<method>` |
| `node_test` | a `node --test` test of a repository: `<repository>:<path>::<test name>` |
| `long_test` | a long test of a repository, same form |

`test_state`, stored on the requirement, sums up its lines by the worst
result: no test → `none`; a failure or an error → `failed`; otherwise a test
never run → `not_run`; otherwise a passed test → `passed`. Tests all skipped
have proven nothing: `not_run`. `tour_name` returns the reference of the first
`tour` line in sequence order, `""` if there is none.

An external runner writes the result through XML-RPC or JSON-RPC:

<!-- [fr] -->

# ERPLibre — requis logiciels (MoSCoW)

Suit ce qu'un projet **s'engage à livrer** : un requis par ligne, classé par
domaine et par phase, avec son niveau d'exigence MoSCoW et l'état de sa
réalisation. Chaque requis se place dans la boucle DevSecOps, porte ses
menaces et la liste des tests qui le prouvent, avec leur dernier résultat.

Le module ne livre **aucun requis**. Il livre le modèle, les écrans et le
vocabulaire ; les requis viennent d'un module de projet, en données.

## Le modèle

| | |
|---|---|
| `devops.requirement` | Un requis : code, titre, domaine, phase, exigence, priorité, effort, responsable, étape DevSecOps, critères d'acceptation, dépendances. |
| `devops.requirement.threat` | Une menace sur un requis, classée STRIDE, avec sa mitigation et son risque résiduel. |
| `devops.requirement.test` | Un test qui prouve un requis, et son dernier résultat connu. |
| `devops.requirement.category` | Un domaine fonctionnel. **Donnée**, pas code. |
| `devops.requirement.phase` | Une phase ou un jalon. **Donnée**, pas code. |
| `devops.requirement.classifier` | Mixin abstrait : `code`, `name`, `sequence`, et l'unicité du code. |

### Pourquoi le domaine est un modèle et l'exigence une Selection

La règle tient en une phrase : **une Selection quand le vocabulaire est
universel, un modèle quand il appartient au projet.**

MoSCoW a quatre valeurs, les mêmes partout, définies hors de tout projet :
c'est une Selection, et un projet qui en voudrait une cinquième n'aurait pas
affaire à MoSCoW. Les domaines fonctionnels, eux, ne se ressemblent d'un
projet à l'autre que par accident — les figer en code obligerait chaque
projet à patcher le module partagé pour nommer les siens.

### Le code porte des décomptes

`code` n'est pas un libellé : les fichiers de données le référencent, et les
domaines des chiffres comptés d'une page de présentation s'y comparent. **Le
renommer casse en silence tout décompte qui s'appuie dessus** — le chiffre
tombe à zéro sans erreur, et la liste que son bouton ouvre arrive vide.

C'est aussi la raison des droits ci-dessous.

Le `code` du requis est unique pour la même raison : un lanceur de tests
retrouve le requis par son code. Il reste facultatif — plusieurs requis sans
code coexistent.

## La planification DevSecOps

| Champ | Rôle |
|---|---|
| `devsecops_stage` | Étape de la boucle : plan, code, build, test, release, deploy, operate, monitor. Barre d'état cliquable, colonnes du kanban. La valeur `code` se libelle « Develop », pour ne pas partager sa traduction avec le champ `code`. |
| `requirement_type` | Fonctionnel, non fonctionnel, sécurité, conformité, opérationnel. |
| `acceptance_criteria` | Critères d'acceptation, un scénario Given / When / Then par critère. |
| `security_relevant`, `data_classification` | Le requis touche-t-il la sécurité, et quelle est la classe de données la plus sensible qu'il manipule. |
| `depends_on_ids` / `dependent_ids` | Ce qui doit être livré avant, ce qui attend celui-ci. Un cycle est refusé, même par plusieurs sauts. |

L'étape DevSecOps **ne remplace pas** les trois booléens : l'étape dit où en
est le travail, `accepted` / `approved` / `done` ce que le client a constaté.

## Les tests et leur résultat

Une ligne de test se déclare en données, par le projet. Sa `kind` dit ce que
désigne sa `reference` :

| `kind` | `reference` |
|---|---|
| `tour` | le nom de la visite guidée |
| `python` | le chemin pointé de la méthode de test |
| `selenium` | le chemin du script, relatif au dépôt |
| `manual` | un texte libre |
| `repo_unittest` | un test unitaire d'un dépôt : `<dépôt>:<chemin>::<Classe>::<méthode>` |
| `node_test` | un test `node --test` d'un dépôt : `<dépôt>:<chemin>::<nom du test>` |
| `long_test` | un test long d'un dépôt, même forme |

`test_state`, stocké sur le requis, résume ses lignes par le pire résultat :
aucun test → `none` ; un échec ou une erreur → `failed` ; sinon un test jamais
lancé → `not_run` ; sinon un test réussi → `passed`. Des tests tous ignorés
n'ont rien prouvé : `not_run`. `tour_name` rend la référence de la première
ligne `tour` dans l'ordre de séquence, `""` s'il n'y en a pas.

Un lanceur externe écrit le résultat par XML-RPC ou JSON-RPC :

<!-- [common] -->

```python
models.execute_kw(
    db, uid, password,
    "devops.requirement.test", "record_result",
    ["INV-01", "selenium", "script/selenium/inventory_stock.py", "passed"],
    {"log": output, "duration": 12.4},
)
```

<!-- [en] -->

`record_result` **creates nothing**: an unknown requirement or line returns
`False` and leaves a warning in the log. A result outside `not_run`, `passed`,
`failed`, `error`, `skipped` is refused. The log is truncated to 20,000
characters, the end kept — it is the end that carries the failing assertion.
Only the `last_*` fields are written.

### Verdict by reference

A repository test runner — ERPLibre's unit tests, the `node --test` suite of
an extension, the long tests — knows its test and none of the requirements it
proves: the link lives in the database only. It writes through
`record_result_by_reference`, with the `kind` and the `reference` alone:

<!-- [fr] -->

`record_result` **ne crée rien** : un requis ou une ligne inconnus rendent
`False` et laissent un avertissement au journal. Un résultat hors de
`not_run`, `passed`, `failed`, `error`, `skipped` est refusé. Le journal est
tronqué à 20 000 caractères, la fin conservée — c'est elle qui porte
l'assertion en échec. Seuls les champs `last_*` sont écrits.

### Verdict par référence

Un lanceur de tests de dépôt — les tests unitaires d'ERPLibre, la suite
`node --test` d'une extension, les tests longs — connaît son test et aucun des
requis qu'il prouve : le lien ne vit que dans la base. Il écrit par
`record_result_by_reference`, avec la seule `kind` et la seule `reference` :

<!-- [common] -->

```python
models.execute_kw(
    db, uid, password,
    "devops.requirement.test", "record_result_by_reference",
    ["repo_unittest", "erplibre:test/test_inventory.py::TestStock::test_count",
     "passed"],
    {"log": output, "duration": 0.8},
)
```

<!-- [en] -->

The verdict goes to **every** line that carries this `kind` and this
`reference`, whatever their requirement: one test that proves several
requirements updates them all in one call. The method returns the number of
lines updated; `0`, with a warning in the log, when the `kind` or the
`reference` is empty or when no line declares them. It creates nothing, and
shares with `record_result` its rights, the validation of the result and the
truncation of the log.

A repository reference reads `<repository>:<path>::<test id>`: the
repository by its name, the path of the test file relative to it, then
`Class::method` for a unit test or the test name for a Node test.

## Rights

| Model | Internal user | Test runner | Configuration |
|---|---|---|---|
| `devops.requirement` | read, write | read | all |
| `devops.requirement.category` | read | read | all |
| `devops.requirement.phase` | read | read | all |
| `devops.requirement.threat` | read | — | all |
| `devops.requirement.test` | read | read, result through `record_result` and `record_result_by_reference` | all |

The vocabulary is read-only for the user: its `code` carries counts, and a
typo there costs more than a badly filled field on a requirement.

The **Requirement test runner** group is meant for the technical account of a
runner, whose credentials live on an integration machine. It does **not**
inherit the internal user: on its own, it reads what the runner matches and
writes nothing directly. `record_result` refuses any caller that is neither in
this group nor an administrator, then writes, as sudo, the result fields only:
the runner can neither declare a line, nor change its reference, nor touch the
requirement. The table holds for a dedicated account only: an internal user
who also receives the group keeps their write access to the requirements.

`test_state` and `test_count` follow the results of the tests: `create` and
`write` refuse them to any caller (AccessError), administrator included. Only
the superuser overrides it.

Threats and tests are declared through the configuration or in data: the
internal user sees them in the requirement form without being able to modify
them.

## Laying down your data

A project module declares the dependency, then its records:

<!-- [fr] -->

Le verdict va sur **toutes** les lignes qui portent cette `kind` et cette
`reference`, quel que soit leur requis : un test qui prouve plusieurs requis
les met tous à jour d'un seul appel. La méthode rend le nombre de lignes mises
à jour ; `0`, avec un avertissement au journal, quand la `kind` ou la
`reference` est vide ou qu'aucune ligne ne les déclare. Elle ne crée rien, et
partage avec `record_result` ses droits, la validation du résultat et la
troncature du journal.

Une référence de dépôt se lit `<dépôt>:<chemin>::<identifiant du test>` : le
dépôt par son nom, le chemin du fichier de test relatif à lui, puis
`Classe::méthode` pour un test unitaire ou le nom du test pour un test Node.

## Droits

| Modèle | Utilisateur interne | Lanceur de tests | Configuration |
|---|---|---|---|
| `devops.requirement` | lire, écrire | lire | tout |
| `devops.requirement.category` | lire | lire | tout |
| `devops.requirement.phase` | lire | lire | tout |
| `devops.requirement.threat` | lire | — | tout |
| `devops.requirement.test` | lire | lire, résultat par `record_result` et `record_result_by_reference` | tout |

Le vocabulaire est en lecture seule pour l'utilisateur : son `code` porte des
décomptes, et une faute de frappe y coûte plus qu'un champ mal rempli sur un
requis.

Le groupe **Requirement test runner** est destiné au compte technique d'un
lanceur, dont les identifiants vivent sur une machine d'intégration. Il
n'hérite **pas** de l'utilisateur interne : seul, il lit ce que le lanceur
rapproche et n'écrit rien en direct. `record_result` refuse tout appelant qui
n'est ni de ce groupe ni administrateur, puis écrit en sudo les seuls champs
de résultat : le lanceur ne peut ni déclarer une ligne, ni changer sa
référence, ni toucher au requis. Le tableau ne vaut que pour un compte
dédié : un utilisateur interne qui reçoit aussi le groupe garde son droit
d'écriture sur les requis.

`test_state` et `test_count` suivent les résultats des tests : `create` et
`write` les refusent à tout appelant (AccessError), administrateur compris.
Seul le superutilisateur passe outre.

Les menaces et les tests se déclarent par la configuration ou en données :
l'utilisateur interne les voit dans le formulaire du requis sans pouvoir les
modifier.

## Poser ses données

Un module de projet déclare la dépendance, puis ses enregistrements :


<!-- [common] -->

```xml
<record id="categorie_inventaire" model="devops.requirement.category">
    <field name="code">inventaire</field>
    <field name="name">Inventaire et réception</field>
    <field name="sequence">50</field>
</record>

<record id="req_inv_01" model="devops.requirement">
    <field name="code">INV-01</field>
    <field name="name">Stock physique par entrepôt</field>
    <field name="category_id" ref="categorie_inventaire"/>
    <field name="phase_id" ref="phase1"/>
    <field name="moscow">must</field>
    <field name="priority">high</field>
    <field name="size">m</field>
    <field name="devsecops_stage">code</field>
    <field name="requirement_type">functional</field>
</record>

<record id="req_inv_01_test_stock" model="devops.requirement.test">
    <field name="requirement_id" ref="req_inv_01"/>
    <field name="name">Stock per warehouse</field>
    <field name="kind">selenium</field>
    <field name="reference">script/selenium/inventory_stock.py</field>
</record>

<record id="req_inv_01_threat_tampering" model="devops.requirement.threat">
    <field name="requirement_id" ref="req_inv_01"/>
    <field name="stride">tampering</field>
    <field name="description">A user edits a stock count without trace.</field>
    <field name="mitigation">Stock moves are the only way to change a quantity.</field>
    <field name="residual_risk">low</field>
</record>
```

<!-- [en] -->

## The screens

List grouped by domain, kanban by DevSecOps stage, form, search with
groupings, graph by domain and pivot view. The form carries the stage status
bar and the Description, Acceptance, Security, Tests and Dependencies tabs.
The search filters the security requirements, those with a failing test and
those without any test. The root menu is `Requirements`; its configuration
holds the domains and the phases.

## See also

`erplibre_devops_guide` renders a presentation page described in data, and
can count requirements in its figures.

<!-- [fr] -->

## Les écrans

Liste groupée par domaine, kanban par étape DevSecOps, formulaire, recherche avec regroupements,
graphique par domaine et vue croisée. Le formulaire porte la barre d'état de
l'étape et les onglets Description, Acceptance, Security, Tests et
Dependencies. La recherche filtre les requis de sécurité, ceux dont un test
échoue et ceux qui n'ont aucun test. Le menu racine est `Requirements`, sa
configuration porte les domaines et les phases.

## Voir aussi

`erplibre_devops_guide` rend une page de présentation décrite en données, et
sait compter des requis dans ses chiffres.
