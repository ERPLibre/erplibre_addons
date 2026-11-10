<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->

<!-- [en] -->

# ERPLibre — Stream Deck requirements

The requirements of the ERPLibre Stream Deck — the deck programs, the GNOME
extension ERPLibre Home, its installation, the games and the mobile plugin —
as `devops.requirement` records, each with the repository tests that prove
it. They come from the audit of the Stream Deck design specifications, row
by row, and live here instead of in a document.

The module depends on `erplibre_streamdeck` and `erplibre_devops_requirement`,
and adds no model, no view and no menu: the requirements show in the
Requirements application, under ten domains whose code starts with `sd_`.

## What the data holds

| Audit row | Requirement |
|---|---|
| covered, or a unit test added since | done, with a proof line per test |
| no unit test yet | to do; *What is missing* says so |
| checked by a long test | done, with a proof of kind *Long test* |
| long test to write | to do; *What is missing* says what the long test must check |
| non-goal, out of scope | MoSCoW *Won't*, done, the reason in the description |
| design decision | MoSCoW *Should*, *Non-functional*, done, the reason in *Achievement* |
| open question, open risk, follow-up | MoSCoW *Should*, to do; *What is missing* says what is left |
| security invariant | MoSCoW *Must*, type *Security*, *Security relevant* |
| proof in another repository | done with a proof line per test of that repository; else to do, *What is missing* names the repository |
| violated | to do, stage *Develop*; *What is missing* describes the gap |

*Achievement* and *What is missing* name files and tests in the same
`<repository>:<path>` form as the proofs below, so each pointer resolves in
its own repository. A done requirement leaves *What is missing* empty. A
requirement that protects a secret, an access or a file mode is of type
*Security* and marked *Security relevant*.

*Notes* opens on the origin of the requirement: what the audit found for
its row.

| Origin | Meaning |
|---|---|
| covered by a test | a test of a repository already proved it |
| unit test missing | no unit test proved it |
| long test needed | only the long test, in virtual machines with a GNOME session, can check it |
| documented only | the design states it: a decision, a rule or a non-goal |
| proof in another repository | its test belongs to the games or the mobile repository |
| violated | the code did not hold it |

What follows the origin says what holds the requirement: *a unit test
pins it*, *an existing test covers it*, *its unit test shows the
violation*.

Each requirement carries a stable code `SD-<DOMAIN>-R<row>`, for example
`SD-DEFECTS-R02`. The data is loaded **once**: it is `noupdate`, so a
requirement edited by hand keeps its edit when the module is updated.

## Proofs and verdicts

A proof line is a `devops.requirement.test` whose reference names a test of
a repository:

```text
<repository>:<path>::<test id>
```

| Kind | Repository | Test id | Example |
|---|---|---|---|
| Repository unit test | `erplibre`, `erplibre-home-gnome-extension`, `streamdeck_game` | `Class::method` | `erplibre:test/test_deck_lock.py::LaCommandeSousVerrou::test_a_busy_deck_runs_nothing_and_exits_two` |
| Node test | `erplibre-home-gnome-extension` | the test name | `erplibre-home-gnome-extension:test/unit/deck-service.test.js::restart goes through the unit only when it exists` |
| Long test | `erplibre` | the check name | `erplibre:long_test/install_erplibre_home.py::extension-indicators` |

A test runner pushes its verdict with the reference alone, through
`record_result_by_reference` of `erplibre_devops_requirement`, as a user of
the runner group:

<!-- [fr] -->

# ERPLibre — requis du Stream Deck

Les requis du Stream Deck d'ERPLibre — les programmes du deck, l'extension
GNOME ERPLibre Home, son installation, les jeux et le plugin mobile — en
enregistrements `devops.requirement`, chacun avec les tests de dépôt qui le
prouvent. Ils viennent de l'audit des spécifications de conception du Stream
Deck, ligne par ligne, et vivent ici plutôt que dans un document.

Le module dépend de `erplibre_streamdeck` et de
`erplibre_devops_requirement`, et n'ajoute aucun modèle, aucune vue ni aucun
menu : les requis s'affichent dans l'application Requis, sous dix domaines
dont le code commence par `sd_`.

## Ce que portent les données

| Ligne d'audit | Requis |
|---|---|
| couverte, ou un test unitaire ajouté depuis | fait, une ligne de preuve par test |
| encore sans test unitaire | à faire ; *Ce qui manque* le dit |
| vérifiée par un test long | fait, une preuve de sorte *Test long* |
| test long à écrire | à faire ; *Ce qui manque* dit ce que le test long doit vérifier |
| non-objectif, hors périmètre | MoSCoW *Ne fera pas*, fait, la raison dans la description |
| décision de conception | MoSCoW *Devrait*, *Non fonctionnel*, fait, la raison dans *Réalisation* |
| question ouverte, risque ouvert, suite | MoSCoW *Devrait*, à faire ; *Ce qui manque* dit ce qui reste |
| invariant de sécurité | MoSCoW *Doit*, type *Sécurité*, *Touche la sécurité* |
| preuve dans un autre dépôt | fait, une ligne de preuve par test de ce dépôt ; sinon à faire, *Ce qui manque* nomme le dépôt |
| enfreinte | à faire, étape *Développement* ; *Ce qui manque* décrit l'écart |

*Réalisation* et *Ce qui manque* nomment fichiers et tests sous la même
forme `<dépôt>:<chemin>` que les preuves ci-dessous : chaque renvoi se
résout dans son propre dépôt. Un requis fait laisse *Ce qui manque* vide.
Un requis qui protège un secret, un accès ou le mode d'un fichier est de
type *Sécurité* et marqué *Touche la sécurité*.

*Notes* s'ouvre sur l'origine du requis, ce que l'audit a trouvé pour sa
ligne. Le libellé reste en anglais, comme tout le champ :

| Origine | Sens |
|---|---|
| covered by a test | un test d'un dépôt le prouvait déjà |
| unit test missing | aucun test unitaire ne le prouvait |
| long test needed | seul le test long, dans des machines virtuelles avec une session GNOME, peut le vérifier |
| documented only | la conception l'énonce : une décision, une règle ou un non-objectif |
| proof in another repository | son test relève du dépôt des jeux ou du dépôt mobile |
| violated | le code ne le tenait pas |

Ce qui suit l'origine dit ce qui tient le requis : *a unit test pins it*
(un test unitaire le fixe), *an existing test covers it* (un test existant
le couvre), *its unit test shows the violation* (son test unitaire montre
l'écart).

Chaque requis porte un code stable `SD-<DOMAINE>-R<ligne>`, par exemple
`SD-DEFECTS-R02`. Les données se chargent **une fois** : elles sont
`noupdate`, un requis retouché à la main garde donc sa retouche à la mise à
jour du module.

## Preuves et verdicts

Une ligne de preuve est un `devops.requirement.test` dont la référence nomme
un test d'un dépôt :

```text
<dépôt>:<chemin>::<identifiant du test>
```

| Sorte | Dépôt | Identifiant | Exemple |
|---|---|---|---|
| Test unitaire de dépôt | `erplibre`, `erplibre-home-gnome-extension`, `streamdeck_game` | `Classe::méthode` | `erplibre:test/test_deck_lock.py::LaCommandeSousVerrou::test_a_busy_deck_runs_nothing_and_exits_two` |
| Test Node | `erplibre-home-gnome-extension` | le nom du test | `erplibre-home-gnome-extension:test/unit/deck-service.test.js::restart goes through the unit only when it exists` |
| Test long | `erplibre` | le nom du contrôle | `erplibre:long_test/install_erplibre_home.py::extension-indicators` |

Un lanceur de tests pousse son verdict avec la seule référence, par
`record_result_by_reference` d'`erplibre_devops_requirement`, en tant
qu'utilisateur du groupe des lanceurs :

<!-- [common] -->

```python
models.execute_kw(
    db, uid, api_key,
    "devops.requirement.test", "record_result_by_reference",
    ["repo_unittest",
     "erplibre:test/test_deck_lock.py::LaCommandeSousVerrou"
     "::test_a_busy_deck_runs_nothing_and_exits_two",
     "passed"],
    {"log": output, "duration": 0.8},
)
```

<!-- [en] -->

The verdict reaches every requirement whose proof carries that reference:
the example above updates two requirements in one call.

## Translation

The requirement names, descriptions and domain names are written in English
and ship in Canadian French: `i18n/fr_CA.po` holds the French of every one
of them, so loading the French language (`fr_CA`) shows the requirements in
French. *Achievement*, *What is missing* and *Notes* stay in English in
both languages: `erplibre_devops_requirement` does not declare these fields
translatable, so the module ships no French for them.

<!-- [fr] -->

Le verdict atteint tous les requis dont une preuve porte cette référence :
l'exemple ci-dessus met deux requis à jour en un appel.

## Traduction

Les noms et descriptions des requis et les noms des domaines sont écrits en
anglais et livrés en français canadien : `i18n/fr_CA.po` porte le français
de chacun d'eux, et charger la langue française (`fr_CA`) affiche donc les
requis en français. *Réalisation*, *Ce qui manque* et *Notes* restent en
anglais dans les deux langues : `erplibre_devops_requirement` ne déclare pas
ces champs traduisibles, le module n'en livre donc aucun français.
