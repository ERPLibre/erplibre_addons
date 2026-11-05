import {
  fields,
  getKwArgs,
  models,
  serverState,
} from "@web/../tests/web_test_helpers";

/** Simulates `linkup.report.action_create_report` for a reflection. */
export class LinkupReport extends models.ServerModel {
  _name = "linkup.report";

  reporter_id = fields.Many2one({ relation: "res.users" });
  reflet_id = fields.Many2one({ relation: "linkup.reflet" });
  reason = fields.Char();
  description = fields.Text();

  action_create_report(reflet_id, message_id, user_id, reason, description) {
    const kwargs = getKwArgs(
      arguments,
      "reflet_id",
      "message_id",
      "user_id",
      "reason",
      "description"
    );
    return this.create({
      reporter_id: serverState.userId,
      reflet_id: kwargs.reflet_id || false,
      reason: kwargs.reason,
      description: kwargs.description || false,
    });
  }
}
