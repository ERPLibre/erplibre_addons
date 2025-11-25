odoo.define('aliments_snippet.snippet', function (require) {
       'use strict';

       var publicWidget = require('web.public.widget');

       publicWidget.registry.AlimentsSnippet = publicWidget.Widget.extend({
           selector: '.aliments-snippet',
           events: {
               'submit #add-aliment-form': '_onSubmitForm',
           },

           start: function () {
               var self = this;
               return this._super.apply(this, arguments).then(function () {
                   self._loadAliments();
               });
           },

           _loadAliments: function () {
               var self = this;
               this._rpc({
                   route: '/aliments/get_aliments',
                   params: {},
               }).then(function (aliments) {
                   var $list = self.$('#aliments-list');
                   $list.empty();
                   if (aliments.length) {
                       var $ul = $('<ul>').appendTo($list);
                       aliments.forEach(function (aliment) {
                           $('<li>').text(aliment.name).appendTo($ul);
                       });
                   } else {
                       $list.text('Aucun aliment trouvé.');
                   }
               });
           },

           _onSubmitForm: function (ev) {
               ev.preventDefault();
               var self = this;
               var $input = this.$('#new-aliment-name');
               var name = $input.val().trim();
               if (name) {
                   this._rpc({
                       route: '/aliments/add_aliment',
                       params: {
                           name: name,
                       },
                   }).then(function () {
                       $input.val('');
                       self._loadAliments();
                   });
               }
           },
       });
   });
