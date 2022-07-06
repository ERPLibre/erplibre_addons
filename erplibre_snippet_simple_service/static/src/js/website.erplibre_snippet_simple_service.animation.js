odoo.define("erplibre_snippet_simple_service.animation", function (require) {
    "use strict";

    let sAnimation = require("website.content.snippets.animation");

    sAnimation.registry.erplibre_snippet_simple_service =
        sAnimation.Class.extend({
            selector: ".o_erplibre_snippet_simple_service",

            start: function () {
                let self = this;
                this._eventList = this.$(".container");
                this._originalContent = this._eventList[0].outerHTML;
                let def = this._rpc({
                    route: "/erplibre_snippet_simple_service/get_last_item",
                }).then(function (data) {
                    if (data.error) {
                        return;
                    }

                    self._$loadedContent = $(data);

                    if (_.isEmpty(data)) {
                        self.$(
                            ".o_loading_erplibre_snippet_simple_service"
                        ).text("NO DATA");
                        return;
                    }

                    if (data["closed"]) {
                        self.$(".closed_value").text(data["closed"]);
                    }
                    if (data["current_user"]) {
                        self.$(".current_user_value").text(
                            data["current_user"]
                        );
                    }
                    if (data["date"]) {
                        self.$(".date_value").text(data["date"]);
                    }
                    if (data["date_delay"]) {
                        self.$(".date_delay_value").text(data["date_delay"]);
                    }
                    if (data["external_participants"]) {
                        self.$(".external_participants_value").text(
                            data["external_participants"]
                        );
                    }
                    if (data["hash"]) {
                        self.$(".hash_value").text(data["hash"]);
                    }
                    if (data["name"]) {
                        self.$(".name_value").text(data["name"]);
                    }
                    if (data["participants"]) {
                        self.$(".participants_value").text(
                            data["participants"]
                        );
                    }
                    if (data["url"]) {
                        self.$(".url_value").text(data["url"]);
                    }
                    self.$(
                        ".o_loading_erplibre_snippet_simple_service"
                    ).remove();
                });

                return $.when(this._super.apply(this, arguments), def);
            },
            destroy: function () {
                this._super.apply(this, arguments);
                if (this._$loadedContent) {
                    this._eventList.replaceWith(this._originalContent);
                }
            },
        });
});
