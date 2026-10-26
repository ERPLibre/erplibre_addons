/** @odoo-module **/
// © 2026 TechnoLibre (http://www.technolibre.ca)
// License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import "@sign_oca/elements/signature.esm";
import { SignatureDialog } from "@web/core/signature/signature_dialog";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

// La fenêtre de signature de sign_oca, augmentée de la signature du profil.
// « userSignature » est ce que rend le serveur dans « user_signature » de
// get_info : { image: URI de données PNG, ou false }. Le bouton « Adopt my
// signature » pose cette image dans la case ; la case « Save as my
// signature » enregistre dans le profil l'image dessinée avant de la poser.
export class UserSignatureDialog extends SignatureDialog {
    static template = "erplibre_user_signature_sign_oca.UserSignatureDialog";
    static props = {
        ...SignatureDialog.props,
        userSignature: Object,
    };

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.userSignatureState = useState({ saveAsMine: false, saving: false });
    }

    onClickAdoptMine() {
        this.props.uploadSignature({
            name: this.signature.name,
            signatureImage: this.props.userSignature.image,
        });
        this.props.close();
    }

    async onClickConfirm() {
        if (this.userSignatureState.saveAsMine) {
            this.userSignatureState.saving = true;
            let result = {};
            try {
                result = await rpc("/sign_oca/user_signature/save", {
                    signature: this.signature.getSignatureImage(),
                });
            } finally {
                this.userSignatureState.saving = false;
            }
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
            }
        }
        super.onClickConfirm();
    }
}

// Le composant de signature de sign_oca (« parent ») ouvre SignatureDialog
// par son « dialogService ». Quand get_info offre une signature de profil,
// ce service est enveloppé une fois par composant : il ouvre
// UserSignatureDialog à la place, et laisse passer les autres fenêtres.
const wrappedParents = new WeakSet();

function useUserSignatureDialog(parent) {
    if (wrappedParents.has(parent) || !parent.info.user_signature) {
        return;
    }
    wrappedParents.add(parent);
    const dialogService = parent.dialogService;
    parent.dialogService = Object.create(dialogService);
    parent.dialogService.add = (Component, props, options) => {
        if (Component === SignatureDialog) {
            return dialogService.add(
                UserSignatureDialog,
                { ...props, userSignature: parent.info.user_signature },
                options
            );
        }
        return dialogService.add(Component, props, options);
    };
}

patch(registry.category("sign_oca").get("signature"), {
    generate(parent) {
        useUserSignatureDialog(parent);
        return super.generate(...arguments);
    },
});
