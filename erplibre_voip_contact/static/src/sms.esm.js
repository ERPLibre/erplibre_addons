/* © 2026 TechnoLibre — License AGPL-3.0 or later */

/**
 * Ouvre le compositeur de SMS pour ce correspondant.
 *
 * <p>Deux modes, et le choix ne se devine pas : avec une fiche, le SMS est
 * rattache au contact et se retrouve dans sa conversation ; sans fiche, il
 * part au numero brut et n'est rattache a rien. Le second est un repli, pas
 * un equivalent.
 *
 * @param {Object} action le service `action`
 * @param {Number|false} partnerId la fiche, si elle est connue
 * @param {String} numero le numero, utilise quand aucune fiche ne l'est
 */
export function ouvrirCompositeurSms(action, partnerId, numero) {
    const contexte = partnerId
        ? {
              default_res_model: "res.partner",
              default_res_id: partnerId,
              default_composition_mode: "comment",
          }
        : {default_composition_mode: "numbers", default_numbers: numero};
    return action.doAction({
        type: "ir.actions.act_window",
        res_model: "sms.composer",
        views: [[false, "form"]],
        target: "new",
        context: contexte,
    });
}
