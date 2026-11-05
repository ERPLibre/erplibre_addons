import { mailModels } from "@mail/../tests/mail_test_helpers";

import { fields, getKwArgs } from "@web/../tests/web_test_helpers";

/**
 * Simulates the start rule of `discuss.channel._channel_basic_info`. The
 * tests set the effective mode and whether it is satisfied; by default a
 * conversation has no rule.
 */
export class DiscussChannel extends mailModels.DiscussChannel {
  linkup_start_rule = fields.Char({ default: "off" });
  linkup_start_rule_satisfied = fields.Boolean({ default: true });

  _channel_basic_info(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    const [channel] = this.browse(kwargs.ids);
    return {
      ...super._channel_basic_info(...arguments),
      linkup_start_rule: channel.linkup_start_rule,
      linkup_start_rule_satisfied: channel.linkup_start_rule_satisfied,
    };
  }
}
