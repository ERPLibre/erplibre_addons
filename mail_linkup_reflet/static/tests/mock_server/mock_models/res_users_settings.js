import { mailModels } from "@mail/../tests/mail_test_helpers";

import { fields } from "@web/../tests/web_test_helpers";

/** Simulates the sounds and notifications of `res.users.settings`. */
export class ResUsersSettings extends mailModels.ResUsersSettings {
  linkup_sound_enabled = fields.Boolean({ default: true });
  linkup_reward_sounds_enabled = fields.Boolean({ default: false });
  linkup_notify_reflet_received = fields.Boolean({ default: true });
  linkup_notify_confirmed = fields.Boolean({ default: true });
  linkup_notify_highlight = fields.Boolean({ default: true });
  linkup_notify_discreet = fields.Boolean({ default: false });
}
