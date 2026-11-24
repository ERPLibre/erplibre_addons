import {
  fields,
  getKwArgs,
  models,
  serverState,
} from "@web/../tests/web_test_helpers";

/**
 * Simulates `linkup.block`: the blocker is the current user, the blocked
 * member is given by user or by partner id, one block per pair and
 * direction.
 */
export class LinkupBlock extends models.ServerModel {
  _name = "linkup.block";

  blocker_id = fields.Many2one({ relation: "res.users" });
  blocked_id = fields.Many2one({ relation: "res.users" });

  _linkupTarget(userId, partnerId) {
    if (userId) {
      return userId;
    }
    const [user] = this.env["res.users"]._filter([
      ["partner_id", "=", partnerId],
    ]);
    return user?.id || false;
  }

  action_block(user_id, partner_id) {
    const kwargs = getKwArgs(arguments, "user_id", "partner_id");
    const blockedId = this._linkupTarget(kwargs.user_id, kwargs.partner_id);
    const [current] = this._filter([
      ["blocker_id", "=", serverState.userId],
      ["blocked_id", "=", blockedId],
    ]);
    if (!current) {
      this.create({ blocker_id: serverState.userId, blocked_id: blockedId });
    }
    return true;
  }

  action_unblock(user_id, partner_id) {
    const kwargs = getKwArgs(arguments, "user_id", "partner_id");
    const blockedId = this._linkupTarget(kwargs.user_id, kwargs.partner_id);
    const ids = this._filter([
      ["blocker_id", "=", serverState.userId],
      ["blocked_id", "=", blockedId],
    ]).map((block) => block.id);
    this.unlink(ids);
    return true;
  }

  linkup_blocked_members() {
    return this._filter([["blocker_id", "=", serverState.userId]]).map(
      (block) => {
        const [user] = this.env["res.users"].browse(block.blocked_id);
        const [partner] = this.env["res.partner"].browse(user.partner_id);
        return {
          id: block.id,
          user_id: user.id,
          partner_id: user.partner_id,
          name: partner?.name || user.name,
        };
      }
    );
  }
}
