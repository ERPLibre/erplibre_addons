import {Component, useState} from "@odoo/owl";

import {_t} from "@web/core/l10n/translation";
import {useService} from "@web/core/utils/hooks";
import {formatInteger} from "@web/views/fields/formatters";

/**
 * The energy of the member, their karma (LU-F-071 RM1, §7.2), with their
 * rank; pressing it opens "My points". The `bubble` sits next to the
 * avatar of the member in the Reflet view, the `card` heads the LinkUp
 * panel of a conversation. The "+N" of the points rise above it
 * (`data-linkup-points-anchor`). Nothing shows when the member hides the
 * points.
 *
 * @typedef {Object} Props
 * @property {"bubble"|"card"} [variant]
 * @extends {Component<Props, Env>}
 */
export class LinkupEnergy extends Component {
    static template = "mail_linkup_gamification.LinkupEnergy";
    static props = {variant: {type: String, optional: true}};
    static defaultProps = {variant: "bubble"};

    setup() {
        super.setup();
        this.store = useState(useService("mail.store"));
        this.action = useService("action");
    }

    get hidden() {
        return Boolean(this.store.settings?.linkup_hide_gamification) || !this.store.linkup_is_member;
    }

    get karma() {
        return formatInteger(this.store.linkup_karma || 0);
    }

    get rankLabel() {
        return this.store.linkup_rank ? _t("Rank: %(name)s", {name: this.store.linkup_rank}) : _t("No rank yet");
    }

    get label() {
        return _t("My energy: %(points)s points. %(rank)s. Open my points.", {
            points: this.karma,
            rank: this.rankLabel,
        });
    }

    openMyPoints() {
        return this.action.doAction("mail_linkup_gamification.action_linkup_my_points");
    }
}
