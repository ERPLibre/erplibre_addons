import {Message} from "@mail/core/common/message";

import {patch} from "@web/core/utils/patch";

import {LinkupRefletCard} from "./reflet_card";

patch(Message, {
    components: {...Message.components, LinkupRefletCard},
});
