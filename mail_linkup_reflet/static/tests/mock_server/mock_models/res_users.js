import { mailModels } from "@mail/../tests/mail_test_helpers";

import { fields } from "@web/../tests/web_test_helpers";

/** Simulates `res.users._init_store_data` of `mail_linkup_reflet`. */
export class ResUsers extends mailModels.ResUsers {
  /** Stands for the LinkUp member group of the mock users. */
  linkup_is_member = fields.Boolean({ default: true });
  /** Stands for an active link with the current user, in the Reflet view. */
  linkup_active_link = fields.Boolean({ default: false });
  /** Stands for `linkup_tour_done`: seen unless a test says otherwise. */
  linkup_tour_done = fields.Boolean({ default: true });

  linkup_tour_consume() {
    this.write([this.env.uid], { linkup_tour_done: true });
    return true;
  }

  _init_store_data(store) {
    super._init_store_data(...arguments);
    store.add({
      linkup_is_member: Boolean(this.env.user?.linkup_is_member),
      linkup_max_hidden_themes: 2,
      linkup_tour_pending: Boolean(
        this.env.user?.linkup_is_member && !this.env.user?.linkup_tour_done
      ),
    });
    const LinkupHighlight = this.env["linkup.highlight"];
    const highlightIds = LinkupHighlight._filter([
      ["active", "=", true],
      "|",
      ["sender_id", "=", this.env.uid],
      ["recipient_id", "=", this.env.uid],
    ]).map((highlight) => highlight.id);
    if (highlightIds.length) {
      LinkupHighlight._to_store(highlightIds, store);
    }
  }
}
