# ERPLibre — appels VoIP et fiches contact

`voip_oca` rapproche un appel de sa fiche par **égalité de chaîne** sur `phone`
ou `mobile`. Un numéro présenté « 15145550142 » et une fiche qui porte
« +1 514-555-0142 » désignent la même personne, et l'égalité les sépare.

La conséquence n'est pas cosmétique :

- l'appel s'affiche « No contact info » ;
- le bouton qui ouvre la fiche est conditionné à la présence du contact, donc
  il disparaît ;
- **rappeler** depuis cet appel part sans numéro — le softphone se rabat sur le
  mobile d'une fiche absente — et la création de l'appel échoue sur un champ
  obligatoire vide.

## Ce que le module fait

| | |
|---|---|
| Rapprochement | Par les **chiffres**, la seule comparaison qui survive au formatage. L'essai d'origine de `voip_oca` reste tenté ensuite. |
| Reprise | À l'installation, les appels déjà enregistrés sont rattachés : sans cela l'historique resterait vide jusqu'au prochain appel. |
| Historique | Les échanges précédents avec le même correspondant — **appels et SMS**, chacun repliable par un chevron. Par contact d'abord, par numéro à défaut. |
| Trois moments | L'historique appartient au correspondant, pas à l'appel : il se voit pendant l'appel, **après avoir raccroché**, et **pendant qu'on compose un numéro**. |
| SMS | Un bouton ouvre le compositeur — rattaché à la fiche quand elle existe, au numéro brut sinon. |
| Fiche inconnue | Un bouton crée la fiche, puis rattache l'appel **en cours** à ce qui vient d'être créé. |

L'historique **des appels** est borné à l'utilisateur courant, comme la liste de
l'onglet des appels. Celui **des SMS** ne l'est pas : un SMS est un échange de
l'organisation avec la personne, et celui qu'un collègue a envoyé hier explique
précisément l'appel d'aujourd'hui.

Pendant la composition, rien n'est proposé sous **7 chiffres** : le
rapprochement compare des fins de numéro, et « 514 » se termine comme la moitié
du carnet.

## Deux fiches, un numéro

Quand deux contacts partagent la fin d'un numéro, la première est retenue et un
avertissement est journalisé. C'est presque toujours un doublon à fusionner :

```
erplibre_mobile_gateway: 2 fiches res.partner finissent par 45550142,
la premiere est retenue
```

## Essais

```bash
./test.sh -d test_voip -i erplibre_voip_contact --stop-after-init \
  --log-level=test --db-filter test_voip
```
