import { defineActions, defineModels } from "@web/../tests/web_test_helpers";

import { linkupModels } from "@mail_linkup_reflet/../tests/linkup_test_helpers";
import { LinkupReflet } from "@mail_linkup_gamification/../tests/mock_server/mock_models/linkup_reflet";
import { ResUsersSettings } from "@mail_linkup_gamification/../tests/mock_server/mock_models/res_users_settings";

import { ResUsers } from "./mock_server/mock_models/res_users";

export function defineLinkupCommunityModels() {
  defineActions([
    {
      id: 9200,
      xml_id: "mail_linkup_community.action_linkup_profile",
      name: "My profile",
      type: "ir.actions.client",
      tag: "linkup.profile",
    },
  ]);
  return defineModels({
    ...linkupModels,
    LinkupReflet,
    ResUsers,
    ResUsersSettings,
  });
}

/** A consent row as `linkup_consents_info` gives it. */
export function consentRow(purpose, values = {}) {
  return {
    purpose,
    label: purpose,
    granted: true,
    date: "2026-10-26 14:03:00",
    version: "1",
    current_version: "1",
    required: ["terms", "privacy", "sensitive_data"].includes(purpose),
    revocable: !["terms", "privacy"].includes(purpose),
    ...values,
  };
}

/** A profile as `linkup_profile_info` gives it. */
export function profileInfo(values = {}) {
  return {
    user_id: 2,
    partner_id: 3,
    name: "Camille",
    email: "camille@example.com",
    email_verified: true,
    phone: "",
    lang: "en_US",
    langs: [
      ["en_US", "English (US)"],
      ["fr_CA", "French (CA)"],
    ],
    first_reflet_scope: "code",
    code: "ABCDE-FGHJK",
    consents: [
      consentRow("terms"),
      consentRow("privacy"),
      consentRow("sensitive_data"),
      consentRow("notifications", {
        granted: false,
        date: false,
        version: false,
      }),
    ],
    age_bracket: "25_34",
    jurisdiction: "CA",
    terms_url: "",
    privacy_url: "",
    deletion_requested: false,
    deletion_date: false,
    deletion_grace_days: 30,
    ...values,
  };
}
