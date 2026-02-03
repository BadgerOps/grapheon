output "pages_url" {
  description = "Cloudflare Pages default URL"
  value       = "https://${cloudflare_pages_project.grapheon.name}.pages.dev"
}

output "custom_domain_url" {
  description = "Custom domain URL"
  value       = "https://${var.subdomain}.${var.zone_name}"
}

output "project_name" {
  description = "Cloudflare Pages project name"
  value       = cloudflare_pages_project.grapheon.name
}

output "pages_subdomain" {
  description = "Pages subdomain for DNS configuration"
  value       = "${cloudflare_pages_project.grapheon.name}.pages.dev"
}

output "zone_id" {
  description = "Cloudflare Zone ID (auto-detected)"
  value       = data.cloudflare_zone.main.id
}
