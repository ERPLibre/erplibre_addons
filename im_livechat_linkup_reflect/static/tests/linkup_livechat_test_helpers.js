import { livechatModels } from "@im_livechat/../tests/livechat_test_helpers";

import { defineModels } from "@web/../tests/web_test_helpers";

import { linkupModels } from "@mail_linkup_reflet/../tests/linkup_test_helpers";

import { DiscussChannel } from "./mock_server/mock_models/discuss_channel";
import { LinkupReflet } from "./mock_server/mock_models/linkup_reflet";

/** The models of the live chat and of LinkUp, the conversation of both. */
export const linkupLivechatModels = {
  ...livechatModels,
  ...linkupModels,
  DiscussChannel,
  LinkupReflet,
};

export function defineLinkupLivechatModels() {
  return defineModels(linkupLivechatModels);
}
