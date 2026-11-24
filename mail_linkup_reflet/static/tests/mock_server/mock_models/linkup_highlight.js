import { mailDataHelpers } from "@mail/../tests/mock_server/mail_mock_server";

import {
  fields,
  getKwArgs,
  models,
  serverState,
} from "@web/../tests/web_test_helpers";

/**
 * Simulates `linkup.highlight`: the sender is the current user, one active
 * highlight per direction, and each change sent to both partners.
 */
export class LinkupHighlight extends models.ServerModel {
  _name = "linkup.highlight";

  sender_id = fields.Many2one({ relation: "res.users" });
  recipient_id = fields.Many2one({ relation: "res.users" });
  channel_id = fields.Many2one({ relation: "discuss.channel" });
  active = fields.Boolean({ default: true });

  _to_store(ids, store) {
    const kwargs = getKwArgs(arguments, "ids", "store");
    const ResUsers = this.env["res.users"];
    for (const highlight of this.browse(kwargs.ids)) {
      const [sender] = ResUsers.browse(highlight.sender_id);
      const [recipient] = ResUsers.browse(highlight.recipient_id);
      for (const partner of this.env["res.partner"].browse([
        sender.partner_id,
        recipient.partner_id,
      ])) {
        store.add("res.partner", { id: partner.id, name: partner.name });
      }
      store.add(this._name, {
        id: highlight.id,
        sender: { id: sender.partner_id, type: "partner" },
        recipient: { id: recipient.partner_id, type: "partner" },
        active: highlight.active,
        channel_id: highlight.channel_id || false,
      });
    }
  }

  _linkupNotify(id, type = "mail.record/insert") {
    const [highlight] = this.browse(id);
    const ResUsers = this.env["res.users"];
    const ResPartner = this.env["res.partner"];
    const store = new mailDataHelpers.Store();
    this._to_store([id], store);
    const result = store.get_result();
    const [sender] = ResUsers.browse(highlight.sender_id);
    const [recipient] = ResUsers.browse(highlight.recipient_id);
    // The bus takes one record per target, as `browse` returns a list.
    const [senderPartner] = ResPartner.browse(sender.partner_id);
    const [recipientPartner] = ResPartner.browse(recipient.partner_id);
    this.env["bus.bus"]._sendone(senderPartner, "mail.record/insert", result);
    this.env["bus.bus"]._sendone(recipientPartner, type, result);
  }

  action_send(recipient_id, channel_id) {
    const kwargs = getKwArgs(arguments, "recipient_id", "channel_id");
    const current = this._filter([
      ["sender_id", "=", serverState.userId],
      ["recipient_id", "=", kwargs.recipient_id],
      ["active", "=", true],
    ])[0];
    if (current) {
      return current.id;
    }
    const id = this.create({
      sender_id: serverState.userId,
      recipient_id: kwargs.recipient_id,
      channel_id: kwargs.channel_id || false,
    });
    this._linkupNotify(id, "linkup.highlight/received");
    return id;
  }

  action_withdraw(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { active: false });
    this._linkupNotify(kwargs.ids[0]);
    return true;
  }

  action_dismiss(ids) {
    const kwargs = getKwArgs(arguments, "ids");
    this.write(kwargs.ids, { active: false });
    this._linkupNotify(kwargs.ids[0]);
    return true;
  }
}
