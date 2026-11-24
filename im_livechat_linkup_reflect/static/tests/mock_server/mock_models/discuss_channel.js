import { DiscussChannel as LivechatDiscussChannel } from "@im_livechat/../tests/mock_server/mock_models/discuss_channel";

import { fields, getKwArgs } from "@web/../tests/web_test_helpers";

/**
 * Simulates what `discuss.channel._channel_basic_info` gives of a live
 * chat conversation of LinkUp: its start rule, the role of its live chat
 * channel and whether a reflection may go between its visitor and its
 * member, and the step to answer of the guide of a member
 * (`linkup_guide`). The tests set them; by default a conversation has no
 * rule.
 */
export class DiscussChannel extends LivechatDiscussChannel {
  linkup_start_rule = fields.Char({ default: "off" });
  linkup_start_rule_satisfied = fields.Boolean({ default: true });
  linkup_livechat_kind = fields.Char({ default: false });
  linkup_can_reflect = fields.Boolean({ default: false });
  linkup_guide = fields.Json({ default: false });

  _channel_basic_info(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    const [channel] = this.browse(kwargs.ids);
    return {
      ...super._channel_basic_info(...arguments),
      linkup_start_rule: channel.linkup_start_rule,
      linkup_start_rule_satisfied: channel.linkup_start_rule_satisfied,
      linkup_livechat_kind: channel.linkup_livechat_kind,
      linkup_can_reflect: channel.linkup_can_reflect,
      ...(channel.linkup_guide ? { linkup_guide: channel.linkup_guide } : {}),
    };
  }
}
