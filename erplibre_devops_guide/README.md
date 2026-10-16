# ERPLibre — guide de présentation

Rend la **page de présentation d'un projet d'implantation** : un bandeau avec
ses chiffres, des sections de cartes, une feuille de route, un pied de page.
Tout vient de la base ; le composant ne sait rien d'un projet en particulier.

Le module ne livre **aucune page**. Il livre le moteur de rendu ; un module de
projet décrit la sienne en données.

## Pourquoi en données

Une page écrite en JavaScript se recopie d'un projet à l'autre, et chaque
copie dérive. Décrite en données, elle se traduit, se corrige sans
redéploiement, et ses chiffres se comptent sur les tables plutôt que de
vieillir en dur dans le gabarit.

## Le modèle

| | |
|---|---|
| `devops.guide` | La page : bandeau, boutons, pied de page. |
| `devops.guide.stat` | Un chiffre du bandeau, littéral ou compté. |
| `devops.guide.section` | Une section, dont la **forme** tient dans `kind`. |
| `devops.guide.card` | Une carte : un problème, sa réponse, au plus un bouton. |
| `devops.guide.counter.mixin` | Mixin abstrait : résout un décompte décrit en données. |

### Les trois formes de section

| `kind` | Ce qui est rendu |
|---|---|
| `lead` | Son `intro` seule, comme corps de texte. |
| `cards` | Ses cartes, en grille. |
| `roadmap` | Ses cartes, en étapes numérotées. |

Une section `lead` **refuse** de porter des cartes : son rendu s'arrête à
l'introduction, et des cartes posées là disparaîtraient de la page sans que
rien ne le dise. La contrainte joue dans les deux sens — à la création d'une
carte comme au changement de forme d'une section qui en porte.

### Le bouton d'une carte

Trois sources, dans cet ordre : `url` ouvre un onglet, `action_xmlid` appelle
l'action, `count_model` ouvre ce modèle filtré par `count_domain`. Les trois
vides : aucun bouton, ce qui rend une étape de feuille de route.

**Une cible sans libellé ne rend aucun bouton** : un bouton ne portant que sa
flèche n'apprend rien sur ce qu'il ouvre.

### Un chiffre du bandeau n'est pas filtré par son domaine

Une carte comptée ouvre **son** modèle filtré par **son** domaine. Un chiffre
du bandeau, lui, ouvre l'action que son `action_xmlid` nomme, telle quelle :
le module ne devine pas de filtre à la place de celui qui a choisi l'action.
Un chiffre qui doit ouvrir une liste filtrée désigne une action qui l'est.

### Le marqueur `{count}`

`action_label`, le libellé du bouton d'une carte, accepte `{count}`,
remplacé par le décompte quand `count_model` est posé. Un libellé reste ainsi juste quand les données
bougent, là où un nombre écrit en dur dérive. Sans modèle compté, le marqueur
reste tel quel.

### Un décompte ne casse jamais la page

`_count_records` rend **toujours** un entier. Un modèle absent du registre, un
domaine illisible, un domaine qui n'est pas une liste, un champ inconnu ou un
droit refusé rendent `0` et laissent une trace dans le journal. Une page de
présentation ne doit jamais empêcher l'ouverture d'un écran.

Le domaine est lu par `ast.literal_eval`, qui n'évalue que des littéraux :
aucun appel, aucun nom, donc rien à exécuter. Le `search_count` tourne dans un
point de sauvegarde, sans quoi une erreur SQL avorterait la transaction
entière — attraper l'exception Python ne la rétablit pas.

## Ouvrir une page

Le module ne livre pas d'action cliente : un projet déclare la sienne et
désigne son guide par son identifiant XML.

```xml
<record id="guide_implantation" model="devops.guide">
    <field name="name">Implantation</field>
    <field name="title">Le projet, de bout en bout</field>
</record>

<record id="action_guide_implantation" model="ir.actions.client">
    <field name="name">Implantation</field>
    <field name="tag">devops_guide.page</field>
    <field name="context">{'guide_xmlid': 'mon_module.guide_implantation'}</field>
</record>
```

Le bouton **Preview** du formulaire ouvre la même page sans qu'aucune action
n'existe, en passant `guide_id` au contexte.

Un `guide_xmlid` inconnu, ou qui désigne un autre modèle, rend une page vide
qui le dit — l'écran s'ouvre plutôt que de casser.

## Thème

La feuille pose dix variables sur `.o_devops_guide`. Un projet les redéfinit
sans recopier le style :

```scss
.o_devops_guide {
    --dg-accent: #1b6b5a;        // couleur d'accentuation
    --dg-accent-soft: #e8f2ef;   // son fond clair
    --dg-bg: #f7f7f8;            // fond de la page
    --dg-surface: #ffffff;       // fond d'une carte
    --dg-ink: #1f2937;           // texte
    --dg-muted: #5b6b70;         // texte secondaire
    --dg-line: #e5e7eb;          // filets et bordures
    --dg-warn: #f6a623;          // icône de problème, pastille
    --dg-ok: #2e7d32;            // icône de réponse
    --dg-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
```

Le crochet vert ne s'affiche que lorsqu'un problème est posé : il dit
« réponse à ce problème ». Un texte seul reste du texte.

## Visite guidée

`tour_name` lance une visite au premier bouton du bandeau. Le service de
visite est absent quand `web_tour` n'est pas installé : le bouton ne s'affiche
alors pas, plutôt que de faire échouer le montage du composant.

## Voir aussi

`erplibre_devops_requirement`, dont ce module dépend : il apporte le menu
racine sous lequel la configuration des guides s'accroche, et le modèle que
les décomptes d'une page d'implantation comptent le plus souvent.
