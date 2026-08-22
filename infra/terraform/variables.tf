variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "medisense"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "backend_image" {
  description = "ECR image URI for the backend (SHA-tagged by CI)"
  type        = string
}

variable "frontend_image" {
  description = "ECR image URI for the frontend"
  type        = string
}

variable "backend_desired_count" {
  type    = number
  default = 2
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "frontend_desired_count" {
  type    = number
  default = 2
}

variable "backend_cpu" {
  type    = number
  default = 2048
}

variable "backend_memory" {
  type    = number
  default = 8192
}

variable "certificate_arn" {
  description = "ACM certificate for HTTPS on the ALB; empty = HTTP only (dev)"
  type        = string
  default     = ""
}

variable "app_mode" {
  type    = string
  default = "clinical"
}

variable "case_retention_days" {
  type    = number
  default = 365
}

variable "db_password" {
  description = "Postgres password (prefer injecting via TF_VAR from a secret store)"
  type        = string
  sensitive   = true
}
