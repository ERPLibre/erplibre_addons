{
    'name': 'Aliments Snippet',
    'version': '16.0.1.0.0',
    'category': 'Website',
    'summary': 'Ajoute un snippet pour afficher une liste d\'aliments',
    'author': 'Votre Nom',
    'website': 'https://www.example.com',
    'depends': ['website', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/aliment_views.xml',
        'views/snippets.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aliments_snippet/static/src/js/snippet.js',
            'aliments_snippet/static/src/scss/snippet.scss',
        ],
    },
    'installable': True,
    'application': False,
}
