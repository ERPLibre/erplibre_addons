

# ERPLibre — requis du Stream Deck

Les requis du Stream Deck d'ERPLibre — les programmes du deck, l'extension
GNOME ERPLibre Home, son installation, les jeux et le plugin mobile — en
enregistrements `devops.requirement`, chacun avec les tests de dépôt qui le
prouvent. Ils viennent de l'audit des spécifications de conception du Stream
Deck, ligne par ligne, et des conceptions de l'inventaire Odoo, de sa
surveillance et de son pilotage des réglages du deck et de la disposition
des touches, et vivent ici plutôt que dans un document.

Le module dépend de `erplibre_streamdeck` et de
`erplibre_devops_requirement`, et n'ajoute aucun modèle, aucune vue ni aucun
menu : les requis s'affichent dans l'application Requis, sous treize domaines
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
jour du module. L'exception est un requis dont une nouvelle version récrit
le texte : la migration de cette version le recharge de son fichier, comme
une preuve dont la référence a changé, et son français revient du
catalogue.

## Le domaine Inventaire

Le domaine *Inventaire* (`sd_inv`, fichier `data/requirement_inventory.xml`)
porte les requis de l'inventaire Odoo des postes et de leurs decks : un par
décision, non-objectif et anti-objectif de sa conception, de code
`SD-INV-R<nn>`. Ses preuves sont des tests Odoo d'`erplibre_streamdeck`, des
tests Node de l'extension et des tests unitaires d'ERPLibre. Une décision que
le code ne tient pas encore reste à faire, étape *Développement*, et *Ce qui
manque* décrit l'écart. Un requis dont la garantie repose sur un autre le
liste sous *Dépend de*, et reste à faire, en le nommant dans *Ce qui
manque*, tant que celui-ci n'est pas fait.

Le test `tests/test_requirement_inventory.py` vérifie que chaque preuve
nomme un test qui existe : un test Odoo est importé et doit tourner sous
`--test-tags /<module>` ; dans un checkout d'ERPLibre, un test de l'extension
ou d'ERPLibre doit figurer dans l'arbre commité de son dépôt (ce contrôle est
sauté hors d'un checkout). Un test Node déclaré dans une boucle
`for … of` sur un tableau littéral se nomme une fois par valeur de la
boucle ; un nom que la boucle ne produit pas n'est pas un test. Chaque test
des cinq fichiers de test de l'inventaire d'`erplibre_streamdeck` prouve
au moins un requis.

## Le domaine Surveillance

Le domaine *Surveillance* (`sd_mon`, fichier
`data/requirement_monitoring.xml`) porte les requis de la surveillance des
postes et de leurs decks : un par décision de l'utilisateur, choix de
conception, élément du côté Odoo, non-objectif et anti-objectif de sa
conception, de code `SD-MON-R<nn>`, à part de l'inventaire pour que chaque
partie du travail se vérifie seule. Ses preuves sont des tests Odoo
d'`erplibre_streamdeck`. Une décision de conception qu'aucun test Odoo ne
peut tenir, comme un poste verrouillé compté muet, est faite sans preuve,
MoSCoW *Devrait*, *Non fonctionnel*, sa raison dans *Réalisation*. Un écart
que le code a encore reste à faire et *Ce qui manque* le décrit. Un requis
dont la garantie repose sur un autre le liste sous *Dépend de*, et reste à
faire, en le nommant dans *Ce qui manque*, tant que celui-ci n'est pas fait.

Le test `tests/test_requirement_monitoring.py` vérifie que chaque preuve
nomme un test Odoo qui tourne sous `--test-tags /<module>`, que chaque test
des fichiers `test_streamdeck_monitor*.py` et `test_streamdeck_settings.py`
d'`erplibre_streamdeck` prouve au moins un requis, que les requis encore à
faire sont exactement ceux qu'il nomme, et qu'aucun n'est fait tant qu'un
requis dont il dépend ne l'est pas.

## Le domaine Pilotage

Le domaine *Pilotage* (`sd_ctl`, fichier `data/requirement_control.xml`)
porte les requis du pilotage du deck par Odoo, le troisième lot : un par
décision de l'utilisateur, choix de conception et anti-objectif de sa
conception, de code `SD-CTL-R<nn>`. `SD-CTL-R01` à `R49` couvrent les
réglages, la première partie du lot ; `SD-CTL-R50` à `R71` la disposition
des touches, la seconde, dont les tests prouvent aussi quatre
anti-objectifs de la première. Ses preuves sont des tests Odoo
d'`erplibre_streamdeck`, des tests Node de l'extension et des tests
unitaires d'ERPLibre, puisque la configuration traverse les trois dépôts.

Le test `tests/test_requirement_control.py` vérifie que chaque preuve nomme
un test qui existe, selon les mêmes règles que l'inventaire ; que chaque
test des fichiers `test_streamdeck_config*.py` et
`test_streamdeck_key_layout.py` d'`erplibre_streamdeck` prouve au moins un
requis ; que les tests qui tiennent les points de revue
du lot sont cités ; et que les requis encore à faire sont exactement ceux
qu'il nomme.

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
| Test Python | un module Odoo | son chemin pointé | `odoo.addons.erplibre_streamdeck.tests.test_streamdeck_access.TestStreamdeckAccess.test_the_manager_reads_the_whole_fleet` |

Un test Python est un test Odoo, nommé par le chemin pointé de sa méthode :
`script/test/odoo_test_report.py --modules erplibre_streamdeck` d'ERPLibre
lance les tests du module sur une base jetable et pousse leurs verdicts.

Un lanceur de tests pousse son verdict avec la seule référence, par
`record_result_by_reference` d'`erplibre_devops_requirement`, en tant
qu'utilisateur du groupe des lanceurs :


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


Le verdict atteint tous les requis dont une preuve porte cette référence :
l'exemple ci-dessus met deux requis à jour en un appel.

## Traduction

Les noms et descriptions des requis et les noms des domaines sont écrits en
anglais et livrés en français canadien : `i18n/fr_CA.po` porte le français
de chacun d'eux, et charger la langue française (`fr_CA`) affiche donc les
requis en français. *Réalisation*, *Ce qui manque* et *Notes* restent en
anglais dans les deux langues : `erplibre_devops_requirement` ne déclare pas
ces champs traduisibles, le module n'en livre donc aucun français.