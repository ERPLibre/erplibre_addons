import {patch} from "@web/core/utils/patch";

import {LinkupProfileMenu} from "@mail_linkup_reflet/core/common/linkup_profile_menu";

/** The section of the profile each entry of the menu opens. */
const PROFILE_SECTIONS = {email: "contact", phone: "contact", photo: "identity", privacy: "privacy"};

// Email, Phone, Photo and Privacy open the profile of the member (LU-F-082)
// on their section, in place of the preferences of Odoo or of no screen.
patch(LinkupProfileMenu.prototype, {
    get entries() {
        return super.entries.map((entry) =>
            entry.id in PROFILE_SECTIONS
                ? {
                      ...entry,
                      hint: undefined,
                      action: {
                          type: "ir.actions.client",
                          tag: "linkup.profile",
                          context: {linkup_section: PROFILE_SECTIONS[entry.id]},
                      },
                  }
                : entry
        );
    },
});
