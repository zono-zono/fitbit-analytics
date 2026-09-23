terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.62"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # state には変数の値がそのまま入る。ローカルに置くとコミット事故で漏れるため、
  # バージョニングを有効にした GCS バケットで管理する。
  # バケット名は backend.hcl に書き、init 時に渡す:
  #   terraform init -backend-config=backend.hcl
  backend "gcs" {}
}
