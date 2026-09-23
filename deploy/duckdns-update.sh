#!/bin/sh
# Keep the DuckDNS record pointing at this instance.
#
# The EC2 public IP changes whenever the instance is stopped and started unless
# it is an Elastic IP. If that happens, the DNS record goes stale and the site
# becomes unreachable under its own name - which also breaks certificate
# renewal, because Let's Encrypt validates by connecting to the name.
#
# Install:
#     sudo install -m 700 -o ec2-user -g ec2-user duckdns-update.sh /opt/chatbot/duckdns-update.sh
#     printf 'DUCKDNS_DOMAIN=yourname\nDUCKDNS_TOKEN=your-token\n' > /opt/chatbot/duckdns.env
#     chmod 600 /opt/chatbot/duckdns.env
#     ( crontab -l 2>/dev/null; echo '*/5 * * * * /opt/chatbot/duckdns-update.sh' ) | crontab -
#
# DUCKDNS_DOMAIN is the subdomain only - "yourname", not "yourname.duckdns.org".
# The token is a password for every domain on that DuckDNS account, so the env
# file holding it is kept 600 and out of this repository.
set -eu

ENV_FILE=${DUCKDNS_ENV:-/opt/chatbot/duckdns.env}
LOG_FILE=${DUCKDNS_LOG:-/var/log/duckdns.log}

if [ ! -r "$ENV_FILE" ]; then
    echo "$(date -Is) no readable $ENV_FILE" >> "$LOG_FILE"
    exit 1
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

if [ -z "${DUCKDNS_DOMAIN:-}" ] || [ -z "${DUCKDNS_TOKEN:-}" ]; then
    echo "$(date -Is) DUCKDNS_DOMAIN or DUCKDNS_TOKEN not set" >> "$LOG_FILE"
    exit 1
fi

# Leaving ip= empty tells DuckDNS to use the source address it sees, which is
# this instance's public IP. That avoids having to discover it locally, where
# the interface only ever shows the private address.
response=$(curl -fsS --max-time 20 \
    "https://www.duckdns.org/update?domains=${DUCKDNS_DOMAIN}&token=${DUCKDNS_TOKEN}&ip=" 2>&1 || echo "REQUEST_FAILED")

# DuckDNS answers with the literal string OK or KO, not an HTTP status, so a
# failed update still arrives as 200 and has to be read from the body.
case "$response" in
    OK) [ "${DUCKDNS_VERBOSE:-0}" = "1" ] && echo "$(date -Is) OK" >> "$LOG_FILE" ;;
    *)  echo "$(date -Is) update failed: $response" >> "$LOG_FILE"; exit 1 ;;
esac

exit 0
