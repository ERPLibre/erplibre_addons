odoo.define('erplibre_snippet_multiple_dialog.widgets', function (require) {
    "use strict";

    var ajax = require("web.ajax");
    var core = require('web.core');
    var widget = require("web_editor.widget");
    var _t = core._t;
    var Dialog = widget.Dialog;
    var options = require('web_editor.snippets.options');
    var sAnimation = require('website.content.snippets.animation');
    var rpc = require('web.rpc');
    var weContext = require("web_editor.context");

    let list_rooms = [];


    var result = $.Deferred(),
        _templates_loaded = ajax.loadXML(
            "/erplibre_snippet_multiple_dialog/static/src/xml/widgets.xml",
            core.qweb
        );


    var ParamsForm = Dialog.extend({
        template: "erplibre_snippet_multiple_dialog.ParamsForm",

        /**
         * Store models info before creating widget
         *
         * @param {Object} parent Widget where this dialog is attached
         * @param {Object} options Dialog creation options
         * @param {Object} rooms rooms list
         * @param {String} chosen Prechosen model
         * @returns {Dialog} New Dialog object
         */
        init: function (parent, options, rooms, chosen) {
            this.chosen = chosen;
            this.rooms = rooms;

            var _options = $.extend({}, {
                title: _t("Form Settings"),
                size: "small",
            }, options);
            return this._super(parent, _options);
        },

        /**
         * Save data
         */
        save: function () {
            this.final_data = this.$("#model").val();
            console.log("save: " + this.final_data);

            document.getElementById("message").innerHTML = "Jitsi url: " + this.final_data;

            rpc.query({
                model: 'sinerkia_jitsi_meet.external_user',
                method: 'search_read',
                kwargs: {
                    domain: [
                        ["meet", "=", parseInt(this.final_data)],
                    ],
                    fields: [
                        "name",
                        "id"
                    ]
                },
            }).then(function (users_list) {
                console.log("users: " + JSON.stringify(users_list));

                var usersDialog = new UsersParamsForm(
                    $(".multiple_dialog"), {}, users_list, ""
                );
                usersDialog.open();
            });



            this._super.apply(this, arguments);
        },
    });
    var UsersParamsForm = Dialog.extend({
        template: "erplibre_snippet_multiple_dialog.UsersParamsForm",

        /**
         * Store models info before creating widget
         *
         * @param {Object} parent Widget where this dialog is attached
         * @param {Object} options Dialog creation options
         * @param {Object} users users list
         * @param {String} chosen Prechosen model
         * @returns {Dialog} New Dialog object
         */
        init: function (parent, options, users, chosen) {
            this.chosen = chosen;
            this.users = users;

            var _options = $.extend({}, {
                title: _t("Form Settings"),
                size: "small",
            }, options);
            return this._super(parent, _options);
        },

        /**
         * Save data
         */
        save: function () {
            this.final_data = this.$("#model").val();
            console.log("save: " + this.final_data);

            document.getElementById("message").innerHTML = "Jitsi url: " + this.final_data;


            this._super.apply(this, arguments);
        },
    });


    _templates_loaded.done(function () {
        result.resolve({
            ParamsForm: ParamsForm,
        });
    });

    sAnimation.registry.multiple_dialog = sAnimation.Class.extend({
        selector: '.multiple_dialog',

        /**
         * @override
         */
        start: function () {
            let def = this._rpc({
                model: 'sinerkia_jitsi_meet.jitsi_meet',
                method: 'search_read',
                kwargs: {
                    fields: [
                        "name",
                        "roomName",
                        "domaineName",
                        "url",
                        "id",
                    ],
                context: weContext.get()},
            }).done(function (models_list) {
                console.log("in rpc " + JSON.stringify(models_list));
                list_rooms = models_list;
                //_models_def.resolve(_.indexBy(models_list, "model"));

                var dialog = new ParamsForm(
                    $(".multiple_dialog"), {}, list_rooms, ""
                );
                dialog.open();
            });


            return $.when(this._super.apply(this, arguments), def);

        },
    });


});
