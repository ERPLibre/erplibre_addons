# ERPLibre — cachet de signature dans sign_oca

`sign_oca` (OCA) pose l'image d'une signature dans sa case, sans rien
autour. Ce module l'encadre d'un cachet qui dit qui a signé, quand, et
quel code retrouve la signature depuis le PDF imprimé.

## Le cachet

| Élément | Rendu |
|---|---|
| Cadre | Guilloché : deux ondes sinusoïdales de phases opposées qui se croisent tout autour de la case, et un filet fin à l'intérieur. |
| Emblème | Sceau-plume dans le coin haut-gauche : disque de la première couleur, plume de la seconde, paraphe blanc. Il coupe la bordure. |
| Signature | L'image garde ses proportions et sa transparence, centrée dans la place qui reste ; elle est posée après l'emblème, qui ne la cache jamais. |
| Nom, rôle | Le partenaire qui a signé, et son rôle dans la demande. |
| Date | `signed_on` en `AAAA-MM-JJ HH:MM ZZZ`, dans le fuseau du signataire, sinon celui de la société, sinon UTC. |
| Code | Les 16 premiers caractères de `stamp_code`, groupés par 4. |

Chaque ligne s'active seule. Elles vont, au choix, **dans la case** — une
bande en bas, l'image rétrécit au-dessus, et la police rétrécit jusqu'à
3 points pour laisser à l'image au moins 40 % de la case — ou **sous la
case**, où elles recouvrent ce que le document y montre.

## Le code de la signature

`stamp_code`, sur le signataire, est le SHA-256 d'un JSON trié qui porte :
la demande, le signataire, son partenaire et son rôle, `signed_on`, le
SHA-256 du document tel qu'il était avant cette signature, et le SHA-256 de
chaque image de signature posée.

Le SHA-256 du PDF final (`signature_hash`) ne peut pas s'imprimer dans le
PDF qu'il mesure : le code en est indépendant, et se calcule avant le
dessin. Il est calculé dès que la demande porte un cachet, même quand sa
ligne n'est pas imprimée. Seul le processus de signature l'écrit
(`_get_server_fields`).

Le champ de recherche **Signature Code** des demandes retrouve celle d'un
code lu sur le papier : espaces et casse ignorés, un préfixe suffit.

## Réglage

Dans *Signer › Paramètres*, bloc **Signature Stamp**, par société :
activation, cadre, les quatre lignes, placement, couleurs.

| Couleurs | Source |
|---|---|
| ERPLibre (défaut) | violet `#280353` et orange `#f15928` |
| Couleurs des documents | `primary_color` et `secondary_color` de la société, celles de la mise en page des rapports |
| Personnalisées | deux sélecteurs |

Une couleur absente ou mal formée retombe sur celle d'ERPLibre au même
rang.

Sur un modèle, **Signature Stamp** vaut *As the company* (défaut), *Always*
ou *Never*. Une demande sans modèle suit la société.

## Avec sign_oca_pades

Une case de signature scellée devient l'apparence d'un champ de signature
PDF, qui coupe tout dessin hors de son rectangle.
`erplibre_sign_oca_signature_stamp_pades`, installé de lui-même avec les
deux modules, donne à ce champ le rectangle du cachet entier : les lignes
placées sous la case restent visibles, et le sceau reste valide. Les champs
sont créés à l'envoi de la demande ; un réglage changé ensuite n'agrandit
plus ceux d'une demande déjà envoyée.

## Limites

- Le cachet n'apparaît que dans le PDF : la page de signature du
  navigateur montre la case comme sign_oca.
- Un signataire porte un seul code, même avec plusieurs cases de
  signature ; chaque case l'imprime.
