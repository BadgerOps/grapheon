# Cloudflare Deployment

Graphēon uses Cloudflare Pages for the frontend, with infrastructure managed via OpenTofu in `terraform/`.

## Prerequisites

- Cloudflare account
- Zone (domain) configured in Cloudflare
- API token with Pages and DNS permissions
- R2 bucket for OpenTofu state

## GitHub Secrets

Add the following secrets in the GitHub repo settings:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

## Terraform Setup

1. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`.
2. Fill in your account and domain details.
3. Run OpenTofu locally, or let CI handle it via PRs and deploy workflow.

## Workflows

- `CI` runs tests, lint, and the frontend build.
- `Deploy` is currently disabled while OpenTofu automation is paused.

## Backend Note

The FastAPI backend is not yet deployed on Cloudflare. To make the backend Cloudflare-native, plan a port to Workers + D1 or another Cloudflare-compatible runtime.

The current backend/container runtime flow is documented in `docs/example_deployment.md` (NixOS + Podman + systemd services).
