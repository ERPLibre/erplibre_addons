import { fields } from "@web/../tests/web_test_helpers";

import { ResUsersSettings as LinkupResUsersSettings } from "@mail_linkup_reflet/../tests/mock_server/mock_models/res_users_settings";

/** Simulates the setting that hides the points. */
export class ResUsersSettings extends LinkupResUsersSettings {
  linkup_hide_gamification = fields.Boolean({ default: false });
}
