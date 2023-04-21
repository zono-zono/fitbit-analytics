provider "google" {
  project = var.project_id
  region  = var.region
  credentials = "${file("${var.credential_path}")}"
  scopes = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/bigquery",
  ]
}

resource "google_bigquery_dataset" "fitbit_analytics_dataset" {
  dataset_id = var.bigquery_dataset_id
}

resource "google_bigquery_table" "external_health_sleep_table" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  table_id   = var.bigquery_table_id


  external_data_configuration {
    autodetect = true
    source_format = "GOOGLE_SHEETS"

    google_sheets_options {
      skip_leading_rows = 1
    }

    source_uris = [
      "https://docs.google.com/spreadsheets/d/1TKhrmNc70tSsUfBKjWF19KxsCkod-54O6XC9Nj9v_dc/"
    ]
  }
  deletion_protection = false
}

# resource "google_storage_bucket" "bucket" {
#   name = var.bucket_name
# }

# resource "google_storage_bucket_object" "archive" {
#   name   = "cloud_function.zip"
#   bucket = google_storage_bucket.bucket.name
#   source = "path/to/your/cloud_function.zip"
# }

# resource "google_cloudfunctions_function" "function" {
#   name                  = var.function_name
#   entry_point           = "insert_data_to_bigquery"
#   runtime               = "python310"
#   available_memory_mb   = 256
#   source_archive_bucket = google_storage_bucket.bucket.name
#   source_archive_object = google_storage_bucket_object.archive.name
#   trigger_http          = false
#   timeout               = 60

#   event_trigger {
#     event_type = "google.storage.object.finalize"
#     resource   = google_storage_bucket.bucket.id
#   }

#   environment_variables = {
#     BIGQUERY_DATASET_ID = var.bigquery_dataset_id
#     BIGQUERY_TABLE_ID   = var.bigquery_table_id
#   }
# }

# resource "google_project_iam_member" "function_service_account" {
#   role   = "roles/bigquery.dataEditor"
#   member = "serviceAccount:${google_cloudfunctions_function.function.service_account_email}"
# }

# resource "google_cloud_scheduler_job" "daily_job" {
#   name     = var.scheduler_job_name
#   region   = var.region
#   schedule = "0 4 * * *"

#   http_target {
#     uri         = google_cloudfunctions_function.function.https_trigger_url
#     http_method = "POST"
#   }
# }

# variable "scheduler_job_name" {
#   type        = string
#   description = "The name of the Cloud Scheduler job."
# }

