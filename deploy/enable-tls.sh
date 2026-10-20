#!/bin/bash
# Turn the self-signed HTTPS on this VM into a trusted certificate.
#
#     sudo ./enable-tls.sh yourname.duckdns.org you@example.com
#
# Run it on the VM, after the DNS name already resolves to this instance's
# public IP. Let's Encrypt validates by connecting to the name over port 80, so
# a record that has not propagated yet fails the challenge and burns one of the
# five-per-hour rate limit slots for that domain.
#
# Safe to re-run: certbot will not reissue a certificate that is still current
# unless asked, and every step below is idempotent.
set -euo pipefail

DOMAIN=${1:-}
EMAIL=${2:-}
CONF=/etc/nginx/conf.d/chatbot.conf

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "usage: sudo $0 <domain> <email>" >&2
    exit 64
fi

echo "==> Checking that $DOMAIN points here"
resolved=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
public=$(curl -fsS --max-time 10 https://checkip.amazonaws.com | tr -d '[:space:]' || true)
if [ -z "$resolved" ]; then
    echo "    $DOMAIN does not resolve yet. Wait for DNS, then re-run." >&2
    exit 1
fi
if [ "$resolved" != "$public" ]; then
    # Not fatal - a proxy or split-horizon DNS can legitimately differ - but it
    # is the most common reason the ACME challenge fails, so say so loudly.
    echo "    WARNING: $DOMAIN resolves to $resolved but this host is $public" >&2
    echo "    The certificate request will fail unless that is deliberate." >&2
    read -r -p "    Continue anyway? [y/N] " reply
    [ "$reply" = "y" ] || exit 1
else
    echo "    $DOMAIN -> $resolved (matches this host)"
fi

echo "==> Installing certbot"
dnf install -y certbot python3-certbot-nginx >/dev/null

echo "==> Naming the server blocks"
# certbot --nginx finds the block to edit by server_name. The blocks ship as
# "_" (match anything), which certbot cannot match to a domain, so name them.
if grep -q "server_name _;" "$CONF"; then
    cp "$CONF" "$CONF.bak.$(date +%Y%m%d%H%M%S)"
    sed -i "s/server_name _;/server_name $DOMAIN;/" "$CONF"
    nginx -t
    systemctl reload nginx
    echo "    server_name set to $DOMAIN"
else
    echo "    already named, leaving alone"
fi

echo "==> Requesting the certificate"
# --redirect makes certbot add the 80 -> 443 redirect itself, so the plain HTTP
# path stops serving the app. ACME still works afterwards: Let's Encrypt follows
# redirects when fetching the challenge.
certbot --nginx \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --redirect \
    --non-interactive

echo "==> Enabling automatic renewal"
# Certificates last 90 days. The timer renews at 30 days remaining; without it
# the site breaks silently one quarter from now.
systemctl enable --now certbot-renew.timer
systemctl list-timers certbot-renew.timer --no-pager | head -3

echo "==> Pointing Django at the new name"
ENV=/opt/chatbot/app/mvp_demo/secrets.env
python3 - "$ENV" "$DOMAIN" <<'PY'
import io, sys
path, domain = sys.argv[1], sys.argv[2]
text = io.open(path, encoding="utf-8").read()
lines = [l.rstrip("\r") for l in text.split("\n")]

def upsert(key, value):
    """Set key=value, appending only if it is not already there."""
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")

hosts = [h for h in next(
    (l.split("=", 1)[1] for l in lines if l.startswith("DJANGO_ALLOWED_HOSTS=")), ""
).split(",") if h.strip()]
if domain not in hosts:
    hosts.append(domain)
upsert("DJANGO_ALLOWED_HOSTS", ",".join(hosts))

# The three that only become correct once TLS is real.
upsert("DJANGO_SECURE_COOKIES", "true")
upsert("DJANGO_TRUST_PROXY_PROTO", "true")
upsert("DJANGO_CSRF_TRUSTED_ORIGINS", f"https://{domain}")

io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
print(f"    updated {path}")
PY

echo "==> Restarting the application"
systemctl restart chatbot
sleep 20
systemctl is-active chatbot

echo
echo "Done. Verify with:"
echo "    curl -sS -o /dev/null -w '%{http_code}\\n' https://$DOMAIN/"
echo "    curl -sS -o /dev/null -w '%{http_code} -> %{redirect_url}\\n' http://$DOMAIN/"
