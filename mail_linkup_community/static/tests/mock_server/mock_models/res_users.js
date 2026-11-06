import { fields } from "@web/../tests/web_test_helpers";

import { ResUsers as PointsResUsers } from "@mail_linkup_gamification/../tests/mock_server/mock_models/res_users";

/** Simulates `res.users._init_store_data` of `mail_linkup_community`. */
export class ResUsers extends PointsResUsers {
  linkup_email_verified = fields.Boolean({ default: true });
  /** The missing consents, separated by commas. */
  linkup_consent_missing_codes = fields.Char();

  _init_store_data(store) {
    super._init_store_data(...arguments);
    const user = this.env.user;
    if (!user?.linkup_is_member) {
      return;
    }
    store.add({
      linkup_email_verified: Boolean(user.linkup_email_verified),
      linkup_consent_missing: (user.linkup_consent_missing_codes || "")
        .split(",")
        .filter(Boolean),
    });
  }
}
