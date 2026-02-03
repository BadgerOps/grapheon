terraform {
  required_version = ">= 1.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  # R2 backend configuration - uses S3-compatible API
  backend "s3" {
    bucket                      = "terraform-state"
    key                         = "grapheon/terraform.tfstate"
    region                      = "auto"
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true
    # endpoints configured via environment variables:
    # AWS_ENDPOINT_URL_S3 = https://<account_id>.r2.cloudflarestorage.com
    # AWS_ACCESS_KEY_ID = R2 access key
    # AWS_SECRET_ACCESS_KEY = R2 secret key
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
