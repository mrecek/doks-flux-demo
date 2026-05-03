output "cluster_id" {
  description = "UUID of the DOKS cluster."
  value       = digitalocean_kubernetes_cluster.cluster.id
}

output "cluster_name" {
  description = "Name of the DOKS cluster."
  value       = digitalocean_kubernetes_cluster.cluster.name
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = digitalocean_kubernetes_cluster.cluster.endpoint
}

output "cluster_version" {
  description = "Resolved Kubernetes version."
  value       = digitalocean_kubernetes_cluster.cluster.version
}

output "vpc_id" {
  description = "UUID of the VPC backing the cluster."
  value       = data.digitalocean_vpc.vpc.id
}

output "project_id" {
  description = "UUID of the DigitalOcean project grouping the cluster resources."
  value       = digitalocean_project.project.id
}
