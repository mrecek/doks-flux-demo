# Root Terragrunt configuration. Local state by default.
#
# To switch to a remote backend (recommended for shared use), add a
# `generate "backend"` block here. See:
#   https://developer.hashicorp.com/terraform/language/settings/backends/configuration

generate "_provider" {
  path      = "_provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<-EOF
    terraform {
      required_version = ">= 1.9.0"

      required_providers {
        digitalocean = {
          source  = "digitalocean/digitalocean"
          version = "~> 2.0"
        }
      }
    }

    variable "digitalocean_token" {
      description = "DigitalOcean API token"
      type        = string
      sensitive   = true
    }

    provider "digitalocean" {
      token = var.digitalocean_token
    }
  EOF
}
