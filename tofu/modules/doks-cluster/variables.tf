variable "cluster_name" {
  description = "Name of the DOKS cluster."
  type        = string
}

variable "region" {
  description = "DigitalOcean region slug."
  type        = string
}

variable "vpc_name" {
  description = "Name of the existing DigitalOcean VPC to use. DigitalOcean auto-creates a `default-<region>` VPC per region; the demo uses that."
  type        = string
}

variable "kubernetes_version_prefix" {
  description = "Version prefix used to resolve the latest matching Kubernetes release. Empty string picks the latest available."
  type        = string
}

variable "node_size" {
  description = "Droplet slug for worker nodes."
  type        = string
}

variable "node_count" {
  description = "Number of worker nodes in the default pool."
  type        = number
}

variable "auto_upgrade" {
  description = "Allow control plane upgrades during maintenance windows."
  type        = bool
}

variable "surge_upgrade" {
  description = "Use surge upgrades for node pool updates."
  type        = bool
}

variable "destroy_all_associated_resources" {
  description = "Delete cluster-created resources (Load Balancers, Volumes) on destroy."
  type        = bool
}

variable "tags" {
  description = "Tags applied to the cluster and node pool."
  type        = list(string)
}

variable "project_name" {
  description = "DigitalOcean project name."
  type        = string
}

variable "project_description" {
  description = "DigitalOcean project description."
  type        = string
}

variable "project_purpose" {
  description = "DigitalOcean project purpose."
  type        = string
}

variable "project_environment" {
  description = "DigitalOcean project environment tag."
  type        = string
}
