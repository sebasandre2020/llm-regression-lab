variable "allow_provisioning" {
  description = "Explicit activation after completing and reviewing the production blueprint."
  type        = bool
  default     = false
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be staging or production."
  }
}
variable "artifact_bucket_name" {
  type = string
}
variable "kms_key_arn" {
  description = "Existing dedicated environment KMS key with reviewed grants."
  type        = string
}
variable "worker_image" {
  description = "Private ECR URI pinned by SHA-256 digest."
  type        = string
  validation {
    condition     = can(regex("^[^ ]+@sha256:[0-9a-f]{64}$", var.worker_image))
    error_message = "Use a digest-pinned image URI."
  }
}
variable "execution_role_arn" {
  type = string
}
variable "worker_role_arn" {
  description = "Project-scoped worker task role, separate from execution role."
  type        = string
}
variable "database_secret_arn" {
  type = string
}
