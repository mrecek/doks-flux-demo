data "digitalocean_kubernetes_versions" "available" {
  version_prefix = var.kubernetes_version_prefix
}

data "digitalocean_vpc" "vpc" {
  name = var.vpc_name
}

resource "digitalocean_kubernetes_cluster" "cluster" {
  name                             = var.cluster_name
  region                           = var.region
  version                          = data.digitalocean_kubernetes_versions.available.latest_version
  vpc_uuid                         = data.digitalocean_vpc.vpc.id
  auto_upgrade                     = var.auto_upgrade
  surge_upgrade                    = var.surge_upgrade
  ha                               = false
  destroy_all_associated_resources = var.destroy_all_associated_resources
  tags                             = var.tags

  node_pool {
    name       = "${var.cluster_name}-workers"
    size       = var.node_size
    node_count = var.node_count
    tags       = var.tags
  }

  maintenance_policy {
    start_time = "04:00"
    day        = "sunday"
  }
}

resource "digitalocean_project" "project" {
  name        = var.project_name
  description = var.project_description
  purpose     = var.project_purpose
  environment = var.project_environment

  resources = [
    digitalocean_kubernetes_cluster.cluster.urn,
  ]
}
