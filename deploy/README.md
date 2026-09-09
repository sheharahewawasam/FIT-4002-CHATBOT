# Deploying to the client EC2 VM

The exact steps used for the running deployment on Amazon Linux 2023
(`ec2-user@13.239.30.166`). `mvp_demo/chatbot.service` is a *different* unit for
the OCI/Ubuntu Terraform path in `oci-infra/` - do not mix them up. This
directory describes the EC2 deployment.

Layout on the VM:

    /opt/chatbot/.venv          virtualenv (python3.12)
    /opt/chatbot/app            this repository
    /opt/chatbot/app/mvp_demo   Django project, working directory of the service

## 1. System packages

    sudo dnf install -y python3.12 python3.12-pip git

Amazon Linux 2023 ships Python 3.9, which is too old: Django 6.0 requires 3.12+.

## 2. Code

    sudo mkdir -p /opt/chatbot && sudo chown -R ec2-user:ec2-user /opt/chatbot
    git clone --depth 1 -b <branch> https://github.com/sheharahewawasam/FIT-4002-CHATBOT.git /opt/chatbot/app

## 3. Dependencies

Install torch from the CPU index FIRST. The default PyPI wheel on Linux bundles
CUDA and costs roughly 2.5GB, which will not fit; installing it first also stops
sentence-transformers pulling the CUDA build in as a dependency.

    python3.12 -m venv /opt/chatbot/.venv
    /opt/chatbot/.venv/bin/pip install --upgrade pip
    /opt/chatbot/.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    /opt/chatbot/.venv/bin/pip install -r /opt/chatbot/app/mvp_demo/requirements.txt

## 4. Configuration

`secrets.env` is not in the repository. Copy it to
`/opt/chatbot/app/mvp_demo/secrets.env` and `chmod 600` it. Required:

    PINECONE_API_KEY, PINECONE_INDEX_NAME
    DJANGO_SECRET_KEY
    DJANGO_DEBUG=False
    DJANGO_ALLOWED_HOSTS=<the VM's hostname or IP>

Optional overrides: `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`,
`DJANGO_CORS_ORIGINS`.

`DJANGO_ALLOWED_HOSTS` must be set: with `DEBUG=False` and no value the app
accepts no hosts at all, by design, so a misconfigured deploy fails loudly
rather than answering on any hostname.

## 5. Database

    cd /opt/chatbot/app/mvp_demo
    /opt/chatbot/.venv/bin/python manage.py migrate

Migrations create the schema and seed the advisers and funds. `db.sqlite3` is
not in the repository - it is created here.

## 6. Service

    sudo cp /opt/chatbot/app/deploy/chatbot.service /etc/systemd/system/
    sudo touch /var/log/chatbot-access.log /var/log/chatbot-error.log
    sudo chown ec2-user:ec2-user /var/log/chatbot-*.log
    sudo systemctl daemon-reload && sudo systemctl enable --now chatbot

Check with `systemctl status chatbot` and `journalctl -u chatbot -n 50`.

## 7. Language model (not yet installed)

Ollama needs roughly 2.9GB (1.4GB runtime plus 1.4GB for `qwen3:1.7b`) and the
instance does not currently have room. Until then `/api/chat/` returns a
connection error while every other endpoint works.

    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen3:1.7b

## Reaching it

Inbound 8000 is not open in the security group. Until it is, tunnel:

    ssh -i <key>.pem -N -L 8080:localhost:8000 ec2-user@13.239.30.166

then open http://localhost:8080.

## Known constraints on this instance

t2.medium: 2 vCPU, 3.8GB RAM, no swap, 8GB disk.

- One Gunicorn worker only. Each worker loads its own copy of the embedder and
  reranker (~1.6GB), so a second will not fit.
- A query takes 20-25s, so real throughput is 2-3 per minute while the throttle
  allows 10/min. Concurrent users queue behind each other.
- `/var/log/chatbot-*.log` and `audit_logs/` have no rotation yet.
