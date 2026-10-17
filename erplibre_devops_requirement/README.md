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

`test_state`, stocké sur le requis, résume ses lignes par le pire résultat :
aucun test → `none` ; un échec ou une erreur → `failed` ; sinon un test jamais
lancé → `not_run` ; sinon un test réussi → `passed`. Des tests tous ignorés
n'ont rien prouvé : `not_run`. `tour_name` rend la référence de la première
ligne `tour` dans l'ordre de séquence, `""` s'il n'y en a pas.

Un lanceur externe écrit le résultat par XML-RPC ou JSON-RPC :

```python
models.execute_kw(
    db, uid, password,
    "devops.requirement.test", "record_result",
    ["INV-01", "selenium", "script/selenium/inventory_stock.py", "passed"],
    {"log": output, "duration": 12.4},
)
```

`record_result` **ne crée rien** : un requis ou une ligne inconnus rendent
`False` et laissent un avertissement au journal. Un résultat hors de
`not_run`, `passed`, `failed`, `error`, `skipped` est refusé. Le journal est
tronqué à 20 000 caractères, la fin conservée — c'est elle qui porte
l'assertion en échec. Seuls les champs `last_*` sont écrits.

## Droits

| Modèle | Utilisateur interne | Lanceur de tests | Configuration |
|---|---|---|---|
| `devops.requirement` | lire, écrire | lire | tout |
| `devops.requirement.category` | lire | lire | tout |
| `devops.requirement.phase` | lire | lire | tout |
| `devops.requirement.threat` | lire | — | tout |
| `devops.requirement.test` | lire | lire, résultat par `record_result` | tout |

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
