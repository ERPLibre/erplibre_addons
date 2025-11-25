from odoo import http
from odoo.http import request


class AlimentsController(http.Controller):

    @http.route('/aliments/get_aliments', type='json', auth='public', website=True)
    def get_aliments(self):
        aliments = request.env['aliment.aliment'].search_read([], ['name'])
        return aliments

    @http.route('/aliments/add_aliment', type='json', auth='public', website=True)
    def add_aliment(self, name):
        new_aliment = request.env['aliment.aliment'].create({'name': name})
        return {'success': bool(new_aliment), 'id': new_aliment.id}
