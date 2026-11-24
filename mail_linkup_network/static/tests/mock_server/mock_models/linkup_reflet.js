import { fields, getKwArgs, makeKwArgs } from "@web/../tests/web_test_helpers";

import { LinkupReflet as PointsLinkupReflet } from "@mail_linkup_gamification/../tests/mock_server/mock_models/linkup_reflet";

/**
 * Simulates the quick replies to a request for action of
 * `mail_linkup_network`: the reply is recorded once, posted in the
 * conversation, and given to both parties on the card.
 */
export class LinkupReflet extends PointsLinkupReflet {
  linkup_action_reply = fields.Char();

  _to_store(ids, store) {
    super._to_store(...arguments);
    const kwargs = getKwArgs(arguments, "ids", "store");
    for (const reflet of this.browse(kwargs.ids)) {
      store.add(this._name, {
        id: reflet.id,
        action_reply: reflet.linkup_action_reply || false,
      });
    }
  }

  action_answer_action_request(ids, reply) {
    const kwargs = getKwArgs(arguments, "ids", "reply");
    const [reflet] = this.browse(kwargs.ids);
    this.write([reflet.id], { linkup_action_reply: kwargs.reply });
    const body = kwargs.reply === "agree" ? "Agreed." : "Not for now.";
    const messageId = this.env["discuss.channel"].message_post(
      reflet.channel_id,
      makeKwArgs({
        body: `<p>${body}</p>`,
        message_type: "comment",
        subtype_xmlid: "mail.mt_comment",
      })
    );
    return { reflet_id: reflet.id, reply: kwargs.reply, message_id: messageId };
  }
}
