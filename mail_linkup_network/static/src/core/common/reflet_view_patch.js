import {patch} from "@web/core/utils/patch";

import {LinkupRefletView} from "@mail_linkup_reflet/views/reflet_view/reflet_view";

// The Reflet view opens the Network view, and takes from the action context
// `linkup_recipient_user_id` the contact a link card chose as the recipient.
patch(LinkupRefletView.prototype, {
    async load() {
        const first = !this.state.loaded;
        await super.load(...arguments);
        const userId = this.props.action?.context?.linkup_recipient_user_id;
        if (first && this.state.loaded && userId && !this.state.newlink) {
            const contact = this.state.contacts.find((item) => item.user_id === userId);
            if (contact) {
                this.selectRecipient(contact);
            }
        }
    },

    openNetworkView() {
        return this.action.doAction("mail_linkup_network.action_linkup_network");
    },
});
