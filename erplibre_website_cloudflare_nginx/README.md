# Configuration

Need to get a cloudflare API Tokens with permission `Account Filter Lists:Read` and `DNS:Edit`.

And configure Nginx with following configuration to add into `visudo` :

```text
odoo ALL=(root) NOPASSWD: /usr/sbin/nginx -t
odoo ALL=(root) NOPASSWD: /usr/bin/systemctl reload nginx
odoo ALL=(root) NOPASSWD: /bin/ln -s * /etc/nginx/sites-enabled/*
```
