import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";

import {LinkupHelp} from "@mail_linkup_reflet/views/help/linkup_help";

import {LinkupHelpNow} from "../../core/common/linkup_help_now";

// "Need help now" heads the LinkUp help (LU-F-118 RM2, CA1), before the
// categories (help_patch.xml); the action context `linkup_section` set to
// `helpNow` gives it the focus.
LinkupHelp.components = {...LinkupHelp.components, LinkupHelpNow};

registry.category("user_menuitems").add("linkup_help_now", (env) => ({
    type: "item",
    id: "linkup_help_now",
    description: _t("Need help now"),
    callback: () =>
        env.services.action.doAction("mail_linkup_reflet.action_linkup_help", {
            additionalContext: {linkup_section: "helpNow"},
        }),
    show: () => Boolean(env.services["mail.store"]?.linkup_is_member),
    sequence: 6,
}));
