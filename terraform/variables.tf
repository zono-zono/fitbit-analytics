variable "project_id" {
  type        = string
  description = "The ID of the project to deploy the resources in."
}

variable "region" {
  type        = string
  description = "The region to deploy the resources in."
  default     = "asia-northeast1"
}

variable "bucket_name" {
  type        = string
  description = "The name of the Google Cloud Storage bucket to use for Cloud Function deployment."
}

variable "bigquery_dataset_id" {
  type        = string
  description = "The ID of the BigQuery dataset to insert data into."
}

variable "bigquery_table_id" {
  type        = string
  description = "The ID of the BigQuery table to insert data into."
}

variable "fitbit_client_id" {
  type        = string
  description = "Fitbit の Client ID。OAuth の仕様上クライアントに露出する値であり秘密ではない。"
}

variable "fitbit_credential_object" {
  type        = string
  description = <<-EOT
    Fitbit のトークンを保存する GCS オブジェクト名。
    中身は Cloud Function が実行のたびに更新するため、Terraform では管理しない。
    初期値の配置は upload_gss.py で行う。
  EOT
  default     = "fitbit_credential.txt"
}

variable "fitbit_client_secret_id" {
  type        = string
  description = <<-EOT
    Fitbit の Client Secret を保持する Secret Manager のシークレット ID。
    値そのものは Terraform に渡さない（渡すと state に平文で残るため）。
    gcloud secrets versions add で登録すること。
  EOT
  default     = "fitbit-client-secret"
}
