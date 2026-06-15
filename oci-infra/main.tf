terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
  required_version = ">= 1.5"
}

# ── Provider ──────────────────────────────────────────────────────────────────
provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# ── Data Sources ───────────────────────────────────────────────────────────────
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Latest Ubuntu 22.04 x86_64 image — compatible with VM.Standard.E2.4
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.E2.4"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
  state                    = "AVAILABLE"
}

# ── Networking ────────────────────────────────────────────────────────────────
resource "oci_core_vcn" "chatbot_vcn" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.0.0.0/16"
  display_name   = "chatbot-vcn"
  dns_label      = "chatbotvn"
}

resource "oci_core_internet_gateway" "chatbot_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.chatbot_vcn.id
  display_name   = "chatbot-igw"
  enabled        = true
}

resource "oci_core_route_table" "chatbot_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.chatbot_vcn.id
  display_name   = "chatbot-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.chatbot_igw.id
  }
}

resource "oci_core_security_list" "chatbot_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.chatbot_vcn.id
  display_name   = "chatbot-security-list"

  # Allow all outbound traffic (required for package installs, Ollama pull, HuggingFace downloads)
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # SSH — for Terraform provisioners and manual access
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  # Django/Gunicorn API
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  # HTTP — for future reverse-proxy / Let's Encrypt
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_subnet" "public_subnet" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.chatbot_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "chatbot-public-subnet"
  dns_label         = "chatbotpub"
  route_table_id    = oci_core_route_table.chatbot_rt.id
  security_list_ids = [oci_core_security_list.chatbot_sl.id]
}

# ── Compute Instance ───────────────────────────────────────────────────────────
resource "oci_core_instance" "chatbot" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  display_name        = "triple-a-chatbot"
  shape               = "VM.Standard.E2.4"

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_size_gb
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public_subnet.id
    assign_public_ip = true
    display_name     = "chatbot-vnic"
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    # cloud-init runs on first boot: installs Ollama, Python, systemd services
    user_data = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  # Give cloud-init enough time to finish (Ollama + qwen3 pull can take 15+ min)
  timeouts {
    create = "60m"
  }
}

# ── App Deployment via Provisioners ───────────────────────────────────────────
# Runs after the instance is created. Waits for cloud-init to finish,
# uploads the app, installs Python deps, then starts the Django service.
resource "null_resource" "deploy_app" {
  depends_on = [oci_core_instance.chatbot]

  triggers = {
    instance_id = oci_core_instance.chatbot.id
  }

  connection {
    type        = "ssh"
    host        = oci_core_instance.chatbot.public_ip
    user        = "ubuntu"
    private_key = file(var.ssh_private_key_path)
    timeout     = "30m"
  }

  # 1. Wait for cloud-init to fully complete before doing anything
  provisioner "remote-exec" {
    inline = [
      "echo 'Waiting for cloud-init to complete...'",
      "sudo cloud-init status --wait",
      "echo 'cloud-init done.'"
    ]
  }

  # 2. Upload the entire Django app directory
  provisioner "file" {
    source      = "${path.module}/../mvp_demo/"
    destination = "/opt/chatbot/mvp_demo"
  }

  # 3. Install Python dependencies and pre-download HuggingFace models
  provisioner "remote-exec" {
    inline = [
      "set -e",

      # Python virtual environment
      "python3 -m venv /opt/chatbot/.venv",
      "/opt/chatbot/.venv/bin/pip install --upgrade pip",
      "/opt/chatbot/.venv/bin/pip install -r /opt/chatbot/mvp_demo/requirements.txt",

      # Pre-download BGE embedder and reranker from HuggingFace
      # (avoids 30-60s delay on first API request)
      "echo 'Pre-downloading HuggingFace models...'",
      "/opt/chatbot/.venv/bin/python -c \"from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-base-en-v1.5'); CrossEncoder('BAAI/bge-reranker-base'); print('Models ready.')\"",

      # Django setup
      "cd /opt/chatbot/mvp_demo && /opt/chatbot/.venv/bin/python manage.py migrate --noinput",

      # Install and start the Django systemd service
      "sudo cp /opt/chatbot/mvp_demo/chatbot.service /etc/systemd/system/chatbot.service",
      "sudo systemctl daemon-reload",
      "sudo systemctl enable chatbot",

      # Ensure log files exist and are owned by ubuntu before starting
      "sudo touch /var/log/chatbot-access.log /var/log/chatbot-error.log",
      "sudo chown ubuntu:ubuntu /var/log/chatbot-access.log /var/log/chatbot-error.log",

      "sudo systemctl start chatbot",

      "echo 'Deployment complete. API available on port 8000.'"
    ]
  }
}
