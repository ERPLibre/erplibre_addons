odoo.define("erplibre_website_cv.animation", function (require) {
    "use strict";

    let sAnimation = require("website.content.snippets.animation");

    sAnimation.registry.demo_website_snippet = sAnimation.Class.extend({
        selector: ".o_erplibre_website_cv",

        start: function () {
            let self = this;
            this._eventList = this.$(".erplibre_website_cv_value");
            this._originalContent = this._eventList.text();
            let def = this._rpc({
                route: "/erplibre_website_cv/website_cv",
            }).then(function (data) {
                if (data.error) {
                    return;
                }

                if (_.isEmpty(data)) {
                    return;
                }
                console.error("error!");
                self._$loadedContent = $(data);
                self._eventList.html(data["fruit"].join("<br/>"));
            });

            return $.when(this._super.apply(this, arguments), def);
        },
        destroy: function () {
            this._super.apply(this, arguments);
            if (this._$loadedContent) {
                this._eventList.text(this._originalContent);
            }
        },
    });
});
