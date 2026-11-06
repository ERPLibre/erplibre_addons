import { fields } from "@web/../tests/web_test_helpers";

import { ResUsers as LinkupResUsers } from "@mail_linkup_reflet/../tests/mock_server/mock_models/res_users";

/** The default point scale (§7.1), by code. */
export const LINKUP_TEST_RULES = {
  reflect_sent: 100,
  reflect_rejected: -150,
  reflect_confirmed: 1000,
  answer_exact: 250,
  precision_sent: 1000,
  theme_guessed: 100,
  continue_sent: 250,
  continue_confirmed: 250,
  call_answered: 250,
  virtual_round: 100,
};

/** Simulates `res.users._init_store_data` of `mail_linkup_gamification`. */
export class ResUsers extends LinkupResUsers {
  linkup_karma = fields.Integer({ default: 0 });
  linkup_rank = fields.Char();

  _init_store_data(store) {
    super._init_store_data(...arguments);
    if (!this.env.user?.linkup_is_member) {
      return;
    }
    store.add({
      linkup_karma: this.env.user.linkup_karma || 0,
      linkup_rank: this.env.user.linkup_rank || false,
      linkup_points_last_id: 0,
      linkup_points_rules: { ...LINKUP_TEST_RULES },
    });
  }
}
