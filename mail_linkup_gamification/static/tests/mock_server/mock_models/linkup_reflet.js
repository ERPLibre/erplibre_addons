import { LinkupReflet as CoreLinkupReflet } from "@mail_linkup_reflet/../tests/mock_server/mock_models/linkup_reflet";

/** The energy of the link that `linkup_channel_info` gives, for every pair. */
export const LINKUP_TEST_LINK_ENERGY = 1350;

/** Simulates `linkup_channel_info` of `mail_linkup_gamification`. */
export class LinkupReflet extends CoreLinkupReflet {
  linkup_channel_info() {
    const info = super.linkup_channel_info(...arguments);
    if (info.available) {
      info.link_energy = LINKUP_TEST_LINK_ENERGY;
    }
    return info;
  }
}
