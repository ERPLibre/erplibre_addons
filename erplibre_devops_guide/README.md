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
| `devops.requirement` (extension) | `guide_id`, la page détaillée du requis, et `guide_card_ids`, les cartes qui le citent. |

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

Un bouton dont la cible n'est pas ouvrable par le lecteur **n'est pas
rendu** : une action introuvable, qui n'est pas une action, réservée à des
groupes dont il n'est pas membre, ou dont il ne peut pas lire le `res_model` ;
un modèle compté qu'il ne peut pas lire. `get_page` rend alors `action_xmlid`
et `action_label` vides. Vider aussi le libellé empêche le repli sur
`count_model`, qui ouvrirait une autre cible que celle annoncée.

### Une carte réservée à des groupes

`groups_id` vide : tout lecteur du guide voit la carte. Posé : seul un membre
d'au moins un de ces groupes la voit, groupes impliqués compris. C'est ce qui
évite de montrer une visite qui mène vers un menu que le lecteur ne peut pas
ouvrir.

La restriction est une **règle d'accès** sur `devops.guide.card`, pas un
filtre d'affichage : la carte manque à la page, à l'onglet **Guide** du
formulaire du requis et à un appel RPC. L'administrateur (`base.group_system`)
lit toutes les cartes, pour les éditer.

### Une carte rattachée à un requis

`requirement_id` rattache la carte à un requis de
`erplibre_devops_requirement`. La carte affiche alors, en grille comme en
feuille de route :

- une pastille avec le **code** et le **niveau MoSCoW** du requis ;
- une pastille avec son **étape DevSecOps** (`devsecops_stage`), qui dit si
  le requis est livré : un requis « could » encore planifié ne se confond
  pas avec un requis livré ;
- une pastille avec l'**état de ses tests**, colorée par état ;
- un bouton **Requirement**, qui ouvre le formulaire du requis ;
- un bouton **Guide**, si le requis désigne une page détaillée (`guide_id`) ;
- un bouton de **visite**, si une visite connue du navigateur est attachée
  (voir plus bas).

`get_page` rend, pour chaque carte, un dictionnaire `requirement` aux clés
fixes : `id`, `code`, `name`, `moscow`, `moscow_label`, `stage`,
`stage_label`, `test_state`, `test_state_label`, `has_guide`. Une carte sans requis, ou dont le requis
n'est pas lisible, reçoit ces mêmes clés **vides** (`""`) ; `has_guide` vaut
`True` ou `""`. Un requis illisible ne prête pas non plus sa visite : la
carte reste affichée, sans bouton de visite si elle n'en porte pas une à
elle. Les libellés arrivent traduits dans la langue du lecteur.

La pastille d'étape porte une classe par valeur,
`o_devops_guide_pill_stage_<étape>` (`plan`, `code`, `build`, `test`,
`release`, `deploy`, `operate`, `monitor`). Elle est en contour : pointillé
tant que le requis n'est pas livré (`plan` à `test`), plein en `--dg-accent`
une fois publié ou déployé, plein en `--dg-ok` en exploitation ou sous
surveillance. Un projet qui veut une autre lecture redéfinit ces classes.

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

La feuille pose onze variables sur `.o_devops_guide`. Un projet les redéfinit
sans recopier le style :

```scss
.o_devops_guide {
    --dg-accent: #1b6b5a;        // couleur d'accentuation, requis publié
    --dg-accent-soft: #e8f2ef;   // son fond clair
    --dg-bg: #f7f7f8;            // fond de la page
    --dg-surface: #ffffff;       // fond d'une carte
    --dg-ink: #1f2937;           // texte
    --dg-muted: #5b6b70;         // texte secondaire
    --dg-line: #e5e7eb;          // filets et bordures
    --dg-warn: #f6a623;          // icône de problème, pastille, tests à lancer
    --dg-ok: #2e7d32;            // icône de réponse, tests passés, requis en exploitation
    --dg-fail: #c62828;          // tests en échec
    --dg-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
```

Le crochet vert ne s'affiche que lorsqu'un problème est posé : il dit
« réponse à ce problème ». Un texte seul reste du texte.

## Visite guidée

Deux sources de visite :

- `tour_name` du guide, lancée par le premier bouton du bandeau ;
- la visite **effective** d'une carte : son propre `tour_name`, sinon celle
  de son requis (`tour_name` du requis, la référence de sa première ligne de
  test de sorte « tour »).

Le libellé vient de `tour_label`, sinon d'un repli traduit côté serveur
(« Start the tour » au bandeau, « Show me » sur une carte).

**Un bouton de visite ne s'affiche que si la visite est au registre JS**
(`web_tour.tours`) du navigateur. Le service rend sans rien faire pour un nom
inconnu ; un bouton muet n'est donc pas montré. Une visite déclarée seulement
dans `web.assets_tests` n'est au registre qu'en mode test : une visite destinée
au guide se déclare dans `web.assets_backend`, sous `static/src`, où ses `_t`
sont aussi extraits pour la traduction.

### L'Onboarding est rétabli

Le mode manuel du service active l'Onboarding de l'utilisateur **en base**.
Laissé actif, chaque chargement suivant lancerait les visites natives d'Odoo
non consommées, et la fin de la visite enchaînerait sur la suivante. Le guide
lit l'état du chargement de la page (`session.tour_enabled`) et, s'il était
inactif, le rétablit sitôt la visite démarrée.

La visite en cours continue, son état vivant dans le navigateur. En contrepartie,
**un rechargement de page l'efface** : le service ne reprend une visite
manuelle au chargement que si l'Onboarding est actif. Une visite lancée du
guide navigue donc par les menus : pas d'`url` (le guide passe
`redirect: false`), pas de `goToUrl`, pas d'`expectUnloadPage`.

Ne pas livrer d'enregistrement `web_tour.tour` pour une visite du guide, sauf
avec `custom=True` : sinon elle entre dans la file des visites d'Onboarding.

## Guide détaillé d'un requis

`guide_id` sur le requis désigne sa page détaillée. Le bouton **Guide** du
formulaire du requis, visible seulement quand `guide_id` est posé, l'ouvre par
`action_open_guide`, comme le bouton **Preview** d'un guide. L'onglet **Guide**
du formulaire liste les cartes qui citent le requis.

## Voir aussi

`erplibre_devops_requirement`, dont ce module dépend : il apporte le menu
racine sous lequel la configuration des guides s'accroche, et le modèle que
les décomptes d'une page d'implantation comptent le plus souvent.
