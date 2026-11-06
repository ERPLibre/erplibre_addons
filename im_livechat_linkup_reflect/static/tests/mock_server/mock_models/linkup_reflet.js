import { LinkupReflet as CoreLinkupReflet } from "@mail_linkup_reflet/../tests/mock_server/mock_models/linkup_reflet";

import { fields, getKwArgs, makeKwArgs } from "@web/../tests/web_test_helpers";

/**
 * Simulates the reflections of a live chat conversation: a party may be a
 * visitor (`author_guest_id`, `recipient_guest_id`), and the card says it
 * lives in a live chat (`livechat`).
 */
export class LinkupReflet extends CoreLinkupReflet {
  author_guest_id = fields.Many2one({ relation: "mail.guest" });
  recipient_guest_id = fields.Many2one({ relation: "mail.guest" });
  livechat = fields.Boolean();

  _to_store(ids, store) {
    const kwargs = getKwArgs(arguments, "ids", "store");
    super._to_store(...arguments);
    const Guest = this.env["mail.guest"];
    for (const reflet of this.browse(kwargs.ids)) {
      const values = { id: reflet.id, livechat: Boolean(reflet.livechat) };
      for (const [party, field] of [
        ["author", "author_guest_id"],
        ["recipient", "recipient_guest_id"],
      ]) {
        if (reflet[field]) {
          store.add(
            Guest.browse(reflet[field]),
            makeKwArgs({ fields: ["name"] })
          );
          values[party] = { id: reflet[field], type: "guest" };
        }
      }
      store.add(this._name, values);
    }
  }
}
