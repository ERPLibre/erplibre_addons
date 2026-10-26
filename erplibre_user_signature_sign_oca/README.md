# ERPLibre — signature de l'utilisateur dans sign_oca

`sign_oca` (OCA) fait signer un document PDF case par case ; une case de
signature ouvre la fenêtre de signature d'Odoo, où le signataire dessine,
écrit son nom ou importe une image. `erplibre_user_signature` garde dans le
profil de l'utilisateur une signature que seul son propriétaire lit.

Ce module relie les deux pour un signataire **connecté**.

## Ce que le module fait

| | |
|---|---|
| Proposer | La fenêtre affiche la signature du profil et un bouton « Adopt my signature » qui la pose dans la case, sans rien dessiner. |
| Enregistrer | La case « Save as my signature » enregistre dans le profil la signature dessinée, puis la pose dans la case. |
| Portée | La signature n'est offerte qu'à l'utilisateur qui signe pour ce signataire : avec `sign_oca_login`, celui que `_is_login_user` reconnaît (tout réviseur du palier avec `sign_oca_tier_validation`) ; sans lui, l'utilisateur dont le partenaire est celui du signataire. Un signataire anonyme, ou un autre utilisateur connecté, garde la fenêtre de `sign_oca`. |
| Format | La signature offerte est un URI de données PNG : la case de `sign_oca` préfixe `data:image/png;base64,` à toute autre valeur, un JPEG du profil est donc converti. Seuls PNG et JPEG s'enregistrent. |

## Côté serveur

| Élément | Rôle |
|---|---|
| `sign.oca.request.signer.get_info` | Ajoute `user_signature` : `False`, ou `{"image": uri}` où `uri` vaut `False` quand le profil n'a pas de signature. |
| `sign.oca.request.signer._get_user_signature_info()` | Calcule cette valeur ; ne lit que la signature de `self.env.user`, l'utilisateur de la session. |
| `sign.oca.request.signer._is_user_signature_signer(user)` | Dit si `user` signe pour ce signataire : `_is_login_user` quand `sign_oca_login` est installé, sinon l'égalité des partenaires. |
| `/sign_oca/user_signature/save` | Route JSON, `auth="user"` : écrit `signature` dans le profil de l'utilisateur connecté, sans privilège, par `SELF_WRITEABLE_FIELDS`. Rend `{"saved": True}` ou `{"error": message}`. |

## Côté navigateur

`UserSignatureDialog` étend la `SignatureDialog` d'Odoo. L'élément
`signature` du registre `sign_oca` ouvre la fenêtre d'Odoo par le
`dialogService` du composant de signature, sans point d'extension pour en
changer : le module enveloppe ce service, une fois par composant et
seulement quand `get_info` offre une signature de profil, pour qu'il ouvre
`UserSignatureDialog` à sa place.
