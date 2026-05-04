terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  name_prefix = var.project_name
}

# Canonical Ubuntu 24.04 LTS AMI for the selected region.
data "aws_ssm_parameter" "ubuntu_2404_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name_prefix}-vpc"
  }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name_prefix}-public-a"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${local.name_prefix}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${local.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "pipeline" {
  name        = "${local.name_prefix}-sg"
  description = "Access for DeFi streaming MVP node"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "Redpanda Console"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Kafka and Redis are exposed only within this security group scope.
  ingress {
    description = "Kafka internal"
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    self        = true
  }

  ingress {
    description = "Redis internal"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "Outbound internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-sg"
  }
}

resource "aws_instance" "pipeline" {
  ami                         = data.aws_ssm_parameter.ubuntu_2404_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public_a.id
  vpc_security_group_ids      = [aws_security_group.pipeline.id]
  associate_public_ip_address = true
  key_name                    = var.key_name

  user_data = <<-EOT
    #!/usr/bin/env bash
    set -euxo pipefail

    export DEBIAN_FRONTEND=noninteractive

    apt-get update -y
    apt-get install -y ca-certificates curl gnupg lsb-release git python3.11 python3.11-venv python3-pip

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $$(. /etc/os-release && echo $$VERSION_CODENAME) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu || true

    REPO_DIR="/opt/defi-streaming-risk"
    if [ ! -d "$${REPO_DIR}/.git" ]; then
      git clone ${var.repo_url} "$${REPO_DIR}"
    else
      cd "$${REPO_DIR}"
      git fetch --all
      git reset --hard origin/main
    fi

    cd "$${REPO_DIR}"

    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
      cp .env.example .env
    fi

    docker compose up -d

    python3.11 -m venv .venv
    . .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt

    cat >/etc/systemd/system/defi-ingestion.service <<'EOF'
    [Unit]
    Description=DeFi Streaming Risk - Ingestion Service
    After=network-online.target docker.service
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    WorkingDirectory=/opt/defi-streaming-risk
    Environment=PYTHONPATH=/opt/defi-streaming-risk
    ExecStart=/opt/defi-streaming-risk/.venv/bin/python -m src.apps.run_ingestion
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    EOF

    cat >/etc/systemd/system/defi-processing.service <<'EOF'
    [Unit]
    Description=DeFi Streaming Risk - Raw Event Processor
    After=network-online.target docker.service
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    WorkingDirectory=/opt/defi-streaming-risk
    Environment=PYTHONPATH=/opt/defi-streaming-risk
    ExecStart=/opt/defi-streaming-risk/.venv/bin/python -m src.processing.raw_event_consumer
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    EOF

    cat >/etc/systemd/system/defi-inference.service <<'EOF'
    [Unit]
    Description=DeFi Streaming Risk - Inference Service
    After=network-online.target docker.service
    Wants=network-online.target

    [Service]
    Type=simple
    User=ubuntu
    WorkingDirectory=/opt/defi-streaming-risk
    Environment=PYTHONPATH=/opt/defi-streaming-risk
    ExecStart=/opt/defi-streaming-risk/.venv/bin/python -m src.apps.run_inference
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    EOF

    systemctl daemon-reload
    systemctl enable --now defi-ingestion.service
    systemctl enable --now defi-processing.service
    systemctl enable --now defi-inference.service
  EOT

  tags = {
    Name = "${local.name_prefix}-ec2"
  }
}
