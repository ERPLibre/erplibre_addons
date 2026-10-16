# ERPLibre — requis logiciels (MoSCoW)

Suit ce qu'un projet **s'engage à livrer** : un requis par ligne, classé par
domaine et par phase, avec son niveau d'exigence MoSCoW et l'état de sa
réalisation.

Le module ne livre **aucun requis**. Il livre le modèle, les écrans et le
vocabulaire ; les requis viennent d'un module de projet, en données.

## Le modèle

| | |
|---|---|
| `devops.requirement` | Un requis : code, titre, domaine, phase, exigence, priorité, effort, responsable. |
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

## Droits

| Modèle | Utilisateur interne | Configuration |
|---|---|---|
| `devops.requirement` | lire, écrire | tout |
| `devops.requirement.category` | lire | tout |
| `devops.requirement.phase` | lire | tout |

Le vocabulaire est en lecture seule pour l'utilisateur : son `code` porte des
décomptes, et une faute de frappe y coûte plus qu'un champ mal rempli sur un
requis.

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
</record>
```

## Les écrans

Liste, formulaire, recherche avec regroupements, graphique par domaine et vue
croisée. Le menu racine est `Requirements`, sa configuration porte les
domaines et les phases.

## Voir aussi

`erplibre_devops_guide` rend une page de présentation décrite en données, et
sait compter des requis dans ses chiffres.
