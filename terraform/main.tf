# 認証は Application Default Credentials を使う。
# サービスアカウントキーのファイルは作らない・置かない。
#   gcloud auth application-default login
provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Cloud Function のソースとトークンを置くバケット
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "cloud_function_bucket" {
  name     = var.bucket_name
  location = var.region

  # このバケットには Fitbit のリフレッシュトークンが入る。
  # ACL による個別公開を封じ、IAM だけで制御する。
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # トークンの上書き事故から復旧できるようにする
  versioning {
    enabled = true
  }
}

data "archive_file" "function_source" {
  type        = "zip"
  output_path = "${path.module}/.build/cloud_function.zip"

  source {
    content  = file("${path.module}/../main.py")
    filename = "main.py"
  }

  source {
    content  = file("${path.module}/../requirements.txt")
    filename = "requirements.txt"
  }
}

resource "google_storage_bucket_object" "function_archive" {
  # 内容が変わったら別名にして、Cloud Function に確実に再デプロイさせる
  name   = "cloud_function-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.cloud_function_bucket.name
  source = data.archive_file.function_source.output_path
}

# ---------------------------------------------------------------------------
# Client Secret
#
# 入れ物だけを Terraform で作り、値は CLI で登録する。
# 値を Terraform に渡すと、どう書いても state に平文で残る。
#   gcloud secrets versions add fitbit-client-secret --data-file=- <<< "<secret>"
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret" "fitbit_client_secret" {
  secret_id = var.fitbit_client_secret_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

# ---------------------------------------------------------------------------
# 関数専用のサービスアカウント
#
# 既定の App Engine サービスアカウントは Editor 相当の権限を持つため使わない。
# ---------------------------------------------------------------------------

resource "google_service_account" "function" {
  account_id   = "fitbit-analytics-fn"
  display_name = "Fitbit analytics Cloud Function"
}

resource "google_secret_manager_secret_iam_member" "function_secret_accessor" {
  secret_id = google_secret_manager_secret.fitbit_client_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function.email}"
}

# トークンオブジェクトの読み書きが必要なので objectAdmin。付与範囲はこのバケットのみ。
resource "google_storage_bucket_iam_member" "function_bucket_object_admin" {
  bucket = google_storage_bucket.cloud_function_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.function.email}"
}

resource "google_bigquery_dataset_iam_member" "function_data_editor" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.function.email}"
}

# pandas_gbq の書き込みはロードジョブを作るため jobUser が要る
resource "google_project_iam_member" "function_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.function.email}"
}

# ---------------------------------------------------------------------------
# BigQuery
# ---------------------------------------------------------------------------

resource "google_bigquery_dataset" "fitbit_analytics_dataset" {
  dataset_id = var.bigquery_dataset_id

  # var.region にはしない。ロケーション変更はデータセットの作り直しになる。
  location = "asia-northeast1"

  lifecycle {
    ignore_changes = [
      # Ignore changes to the dataset's configuration
      access,
    ]
  }
}

resource "google_bigquery_table" "warehouse_health_sleep" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  table_id   = var.bigquery_table_id

  # 数年分の健康データが入る。terraform destroy で消えないようにする。
  deletion_protection = true
}

# ---------------------------------------------------------------------------
# 定期実行
# ---------------------------------------------------------------------------

resource "google_pubsub_topic" "trigger_topic" {
  name = "fitbit-insert-topic"
}

resource "google_cloud_scheduler_job" "daily_job" {
  name        = "fitbit-api-job"
  schedule    = "0 1 * * *"
  time_zone   = "Asia/Tokyo"
  region      = var.region
  description = "This job triggers the Cloud Function daily at 1:00 JST."

  pubsub_target {
    topic_name = google_pubsub_topic.trigger_topic.id
    data       = base64encode("example-data")
  }
}

resource "google_cloudfunctions_function" "bigquery_insert_function" {
  name        = "fitbit-bigquery-insert-function"
  region      = var.region
  runtime     = "python310"
  entry_point = "append_data_to_bigquery"

  service_account_email = google_service_account.function.email

  source_archive_bucket = google_storage_bucket.cloud_function_bucket.name
  source_archive_object = google_storage_bucket_object.function_archive.name

  environment_variables = {
    FITBIT_CREDENTIAL_BUCKET = google_storage_bucket.cloud_function_bucket.name
    FITBIT_CREDENTIAL_OBJECT = var.fitbit_credential_object
    FITBIT_CLIENT_ID         = var.fitbit_client_id
    BIGQUERY_PROJECT_ID      = var.project_id
    BIGQUERY_DATASET_ID      = var.bigquery_dataset_id
    BIGQUERY_TABLE_ID        = var.bigquery_table_id
  }

  # 値は実行時に Secret Manager から解決される。state には入らない。
  secret_environment_variables {
    key        = "FITBIT_CLIENT_SECRET"
    project_id = var.project_id
    secret     = google_secret_manager_secret.fitbit_client_secret.secret_id
    version    = "latest"
  }

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.trigger_topic.id
  }

  depends_on = [
    google_secret_manager_secret_iam_member.function_secret_accessor,
  ]
}
