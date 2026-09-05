/* © 2026 TechnoLibre — License AGPL-3.0 or later */

import { onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { Call } from "@voip_oca/components/call/call.esm";
import { durationStr } from "@voip_oca/utils/utils.esm";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

/**
 * Le panneau d'appel, augmente de ce que l'appel apprend sur la personne.
 *
 * <p>Trois manques y sont combles : l'historique des echanges precedents, la
 * fiche ouvrable meme quand le contact vient d'etre trouve, et la creation
 * d'une fiche quand le numero est inconnu.
 */
patch(Call.prototype, {
  setup() {
    super.setup();
    this.orm = useService("orm");
    this.historique = useState({ appels: [] });
    // Charge une fois a l'ouverture du panneau, et non a chaque seconde
    // du minuteur : l'historique d'un correspondant ne change pas pendant
    // l'appel qu'on est en train de lui passer.
    onWillStart(() => this.chargerHistorique());
  },

  async chargerHistorique() {
    const appel = this.voip.call || {};
    const contact = this.voip.partner || {};
    if (!appel.phoneNumber && !contact.id) {
      return;
    }
    this.historique.appels = await this.orm.call(
      "voip.call",
      "historique_du_correspondant",
      [],
      {
        phone_number: appel.phoneNumber || false,
        partner_id: contact.id || false,
        exclude_id: appel.id || false,
      }
    );
  },

  /** La date a montrer : celle du decroche, ou celle de la tentative. */
  dateHistorique(appel) {
    const brut = appel.startDate || appel.createDate || appel.creationDate;
    return brut ? formatDateTime(deserializeDateTime(brut)) : "";
  },

  iconeHistorique(appel) {
    return appel.typeCall === "incoming"
      ? "fa fa-fw fa-arrow-down text-success"
      : "fa fa-fw fa-arrow-up text-primary";
  },

  /**
   * La duree, vide tant que l'appel n'a pas ete pris.
   *
   * <p>Un appel sans decroche n'a pas de duree de zero seconde : il n'en a
   * pas du tout, et afficher « 0 » ferait croire a une communication coupee
   * net plutot qu'a un appel manque.
   */
  dureeHistorique(appel) {
    if (!appel.startDate || !appel.endDate) {
      return "";
    }
    const debut = deserializeDateTime(appel.startDate);
    const fin = deserializeDateTime(appel.endDate);
    return durationStr(Math.round((fin - debut) / 1000));
  },

  /**
   * Cree la fiche, puis rattache l'appel EN COURS a ce qui vient d'etre
   * cree. Sans ce second temps, la fiche existe et l'appel affiche encore
   * « No contact info » : le rapprochement n'a lieu qu'a la creation de
   * l'appel, qui est deja passee.
   */
  onCreerContact() {
    this.action.doAction(
      {
        type: "ir.actions.act_window",
        res_model: "res.partner",
        views: [[false, "form"]],
        target: "new",
        context: { default_phone: this.voip.call.phoneNumber },
      },
      {
        onClose: async () => {
          if (!this.voip.call.id) {
            return;
          }
          const appel = await this.orm.call(
            "voip.call",
            "rattacher_le_contact",
            [[this.voip.call.id]]
          );
          if (appel.partner) {
            this.voip.partner = appel.partner;
          }
          await this.chargerHistorique();
        },
      }
    );
  },
});
