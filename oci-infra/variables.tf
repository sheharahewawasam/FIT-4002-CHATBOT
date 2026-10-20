variable "tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
}

variable "user_ocid" {
  description = "OCI User OCID"
  type        = string
}

variable "fingerprint" {
  description = "API key fingerprint"
  type        = string
}

variable "private_key_path" {
  description = "Path to the OCI API private key .pem file"
  type        = string
}

variable "region" {
  description = "OCI region"
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment OCID to deploy resources into"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key content (paste contents of your .pub file)"
  type        = string
}

variable "ssh_private_key_path" {
  description = "Path to SSH private key file for Terraform provisioners"
  type        = string
}

variable "instance_ocpus" {
  description = "Number of OCPUs for the compute instance (free tier max: 4)"
  type        = number
  default     = 4
}

variable "instance_memory_gb" {
  description = "RAM in GB for the compute instance (free tier max: 24)"
  type        = number
  default     = 24
}

variable "boot_volume_size_gb" {
  description = "Boot volume size in GB"
  type        = number
  default     = 100
}
