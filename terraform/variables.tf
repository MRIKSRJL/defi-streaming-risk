variable "aws_region" {
  description = "AWS region to deploy the MVP stack."
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Project name used for resource naming and tags."
  type        = string
  default     = "defi-streaming-risk"
}

variable "instance_type" {
  description = "EC2 instance type sized for Redpanda + Redis + Python services."
  type        = string
  default     = "t3.medium"
}

variable "ssh_allowed_cidr" {
  description = "CIDR block allowed to SSH to EC2 (restrict in production)."
  type        = string
  default     = "0.0.0.0/0"
}

variable "repo_url" {
  description = "Git repository URL to clone on the EC2 node."
  type        = string
  default     = "https://github.com/MRIKSRJL/defi-streaming-risk.git"
}

variable "key_name" {
  description = "Optional AWS EC2 key pair name for SSH access."
  type        = string
  default     = null
  nullable    = true
}
