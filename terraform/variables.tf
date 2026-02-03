variable "cloudflare_api_token" {
  description = "Cloudflare API token with Pages and DNS permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "project_name" {
  description = "Name of the Cloudflare Pages project"
  type        = string
  default     = "grapheon"
}

variable "production_branch" {
  description = "Git branch for production deployments"
  type        = string
  default     = "master"
}

variable "zone_name" {
  description = "Cloudflare zone (domain) name"
  type        = string
  default     = "badgerops.foo"
}

variable "subdomain" {
  description = "Subdomain for the Pages project"
  type        = string
  default     = "grapheon"
}
