include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../modules/doks-cluster"
}

locals {
  region = "sfo3"
}

inputs = {
  cluster_name                     = "doks-flux-demo"
  region                           = local.region
  vpc_name                         = "default-${local.region}"
  kubernetes_version_prefix        = ""
  node_size                        = "s-2vcpu-2gb"
  node_count                       = 2
  auto_upgrade                     = false
  surge_upgrade                    = true
  destroy_all_associated_resources = true
  tags                             = ["doks-flux-demo", "managed-by:terragrunt"]
  project_name                     = "doks-flux-demo-project"
  project_description              = "Demo DOKS cluster managed by Tofu + Flux."
  project_purpose                  = "Operational / Developer tooling"
  project_environment              = "Development"
}
