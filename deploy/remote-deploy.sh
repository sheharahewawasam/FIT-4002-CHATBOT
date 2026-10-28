#!/usr/bin/env bash
# Runs ON the VM, piped over SSH by .github/workflows/deploy.yml:
#
#     ssh ec2-user@<host> 'bash -s' -- <branch> <sha> < deploy/remote-deploy.sh
#
# Moves /opt/chatbot/app to exactly the commit CI tested, installs any changed
# pins, migrates, restarts, and puts the previous code back if the service does
# not come up. Packages and migrations are not rolled back: a migration that
# needs undoing is a decision for a person, not a script.
set -euo pipefail

BRANCH="$1"
SHA="$2"
APP=/opt/chatbot/app
VENV=/opt/chatbot/.venv
HEALTH_URL=http://127.0.0.1:8000/api/auth/me/

cd "$APP"

# A hand edit on the VM would be silently overwritten, so stop and let a person
# decide. Untracked files (scratch test scripts) are left alone.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Tracked files are modified on the VM; refusing to deploy over them:" >&2
    git status --short --untracked-files=no >&2
    exit 1
fi

PREVIOUS=$(git rev-parse HEAD)
echo "Deploying $BRANCH @ ${SHA:0:7} (was ${PREVIOUS:0:7})"

# Fetched by SHA, not branch name, so a push that lands mid-run cannot be
# deployed untested. The checkout is shallow; depth 1 keeps it that way.
git fetch --quiet --depth 1 origin "$SHA"
git checkout --quiet -B "$BRANCH" "$SHA"

"$VENV/bin/pip" install --quiet --disable-pip-version-check -r mvp_demo/requirements.txt

cd mvp_demo
# --skip-checks: the system checks import the URLconf and with it the embedder
# and reranker (~1.6GB), on top of the copy the running service already holds.
"$VENV/bin/python" manage.py migrate --noinput --skip-checks

healthy() {
    # The worker loads the models before it answers, which takes about a minute.
    for _ in $(seq 1 60); do
        if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$HEALTH_URL")" = 200 ]; then
            return 0
        fi
        sleep 5
    done
    return 1
}

sudo systemctl restart chatbot
if healthy; then
    echo "Healthy on ${SHA:0:7}"
    exit 0
fi

echo "Not healthy after 5 minutes; putting ${PREVIOUS:0:7} back" >&2
sudo journalctl -u chatbot -n 40 --no-pager >&2 || true
git -C "$APP" checkout --quiet -B "$BRANCH" "$PREVIOUS"
sudo systemctl restart chatbot
if healthy; then
    echo "Rolled back: ${PREVIOUS:0:7} is serving again." >&2
else
    echo "The rollback is not healthy either - needs a person." >&2
fi
exit 1
