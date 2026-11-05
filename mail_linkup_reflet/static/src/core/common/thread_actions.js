import {threadActionsRegistry} from "@mail/core/common/thread_actions";

import {_t} from "@web/core/l10n/translation";

import {LinkupPanel} from "./linkup_panel";

threadActionsRegistry.add("linkup-panel", {
    component: LinkupPanel,
    condition(component) {
        const thread = component.thread;
        return (
            component.store?.linkup_is_member &&
            thread?.model === "discuss.channel" &&
            thread.channel_type === "chat" &&
            (!component.props.chatWindow || component.props.chatWindow.isOpen)
        );
    },
    panelOuterClass: "o-linkup-Panel bg-inherit",
    icon: "fa fa-fw fa-link",
    iconLarge: "fa fa-fw fa-lg fa-link",
    name: _t("LinkUp"),
    nameActive: _t("Hide LinkUp"),
    sequence: 15,
    sequenceGroup: 10,
    toggle: true,
});
