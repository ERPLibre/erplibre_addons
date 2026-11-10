

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
| preuve dans un autre dépôt | à faire ; *Ce qui manque* nomme le dépôt |
| enfreinte | à faire, étape *Développement* ; *Ce qui manque* décrit l'écart |

*Réalisation* et *Ce qui manque* nomment fichiers et tests sous la même
forme `<dépôt>:<chemin>` que les preuves ci-dessous : chaque renvoi se
résout dans son propre dépôt. Un requis qui protège un secret, un accès ou
un fichier hors du checkout est marqué *Touche la sécurité*.

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
anglais et se traduisent : `i18n/fr_CA.po` porte un terme par texte, et
charger la langue française traduit les requis.