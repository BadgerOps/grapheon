# Cloudflare Pages + DNS for Graphēon

data "cloudflare_zone" "main" {
  name = var.zone_name
}

resource "cloudflare_pages_project" "grapheon" {
  account_id        = var.cloudflare_account_id
  name              = var.project_name
  production_branch = var.production_branch

  # Direct Upload mode; GitHub Actions uploads build artifacts with Wrangler.
  deployment_configs {
    production {
      compatibility_date = "2024-01-01"
    }
    preview {
      compatibility_date = "2024-01-01"
    }
  }
}

resource "cloudflare_pages_domain" "grapheon" {
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.grapheon.name
  domain       = "${var.subdomain}.${var.zone_name}"
}

resource "cloudflare_record" "grapheon" {
  zone_id = data.cloudflare_zone.main.id
  name    = var.subdomain
  content = "${cloudflare_pages_project.grapheon.name}.pages.dev"
  type    = "CNAME"
  ttl     = 1
  proxied = true
}
