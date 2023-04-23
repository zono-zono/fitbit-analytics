provider "google" {
  project = var.project_id
  region  = var.region
  credentials = "${file("${var.credential_path}")}"
}

resource "google_storage_bucket_object" "fitbit_credential" {
  name   = var.fitbit_credential_path
  bucket = google_storage_bucket.cloud_function_bucket.name
  source = "../${var.fitbit_credential_path}"
}

resource "google_storage_bucket_object" "csv" {
  name   = "df.csv"
  bucket = google_storage_bucket.cloud_function_bucket.name
  source = "../df.csv"
}

resource "google_bigquery_table" "warehouse_health_sleep" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  table_id   = var.bigquery_table_id
  deletion_protection = false
}

resource "google_bigquery_job" "load_csv" {
  job_id = "load_csv_job2"

  load {
    destination_table {
      project_id = google_bigquery_table.warehouse_health_sleep.project
      dataset_id = google_bigquery_table.warehouse_health_sleep.dataset_id
      table_id   = google_bigquery_table.warehouse_health_sleep.table_id
    }

    source_uris = ["gs://${google_storage_bucket.cloud_function_bucket.name}/${google_storage_bucket_object.csv.name}"]

    source_format         = "CSV"
    skip_leading_rows     = 1
    allow_quoted_newlines = true
    field_delimiter       = ","
    quote                 = "\""
    autodetect            = true
    write_disposition = "WRITE_TRUNCATE"
  }
}

resource "google_bigquery_dataset" "fitbit_analytics_dataset" {
  dataset_id = var.bigquery_dataset_id
  location   = "asia-northeast1"
  lifecycle {
    ignore_changes = [
      # Ignore changes to the dataset's configuration
      access,
    ]
  }
}

# resource "google_bigquery_table" "external_health_sleep_table" {
#   dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
#   table_id   = var.bigquery_table_id


#   external_data_configuration {
#     autodetect = true
#     source_format = "GOOGLE_SHEETS"

#     google_sheets_options {
#       skip_leading_rows = 1
#     }

#   }
#   deletion_protection = false
# }


resource "google_cloudfunctions_function" "bigquery_insert_function" {
  name        = "fitbit-bigquery-insert-function"
  runtime     = "python310"
  entry_point = "append_data_to_bigquery"

  source_archive_bucket = google_storage_bucket.cloud_function_bucket.name
  source_archive_object = google_storage_bucket_object.function_archive.name

  environment_variables = {
    FITBIT_CREDENTIAL_BUCKET = google_storage_bucket.cloud_function_bucket.name
    FITBIT_CREDENTIAL_OBJECT = google_storage_bucket_object.fitbit_credential.name
    FITBIT_CLIENT_ID = var.fitbit_client_id
    FITBIT_CLIENT_SECRET = var.fitbit_client_secret
    BIGQUERY_PROJECT_ID = var.project_id
    BIGQUERY_DARASET_ID = var.bigquery_dataset_id
    BIGQUERY_TABLE_ID = var.bigquery_table_id
  }

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.trigger_topic.id
  }
}

resource "google_storage_bucket" "cloud_function_bucket" {
  name = var.bucket_name
  location = var.region
}

resource "google_storage_bucket_object" "function_archive" {
  name   = "cloud_function.zip"
  bucket = google_storage_bucket.cloud_function_bucket.name
  source = "../cloud_function.zip" # main.pyとrequirements.txtをzipしたアーカイブのパス
}

resource "google_pubsub_topic" "trigger_topic" {
  name = "fitbit-insert-topic"
}

resource "google_cloud_scheduler_job" "daily_job" {
  name             = "fitbit-api-job"
  schedule         = "0 4 * * *"
  time_zone        = "UTC"
  description      = "This job triggers the Cloud Function daily at 4:00 UTC."
  
  pubsub_target {
    topic_name = google_pubsub_topic.trigger_topic.id
    data       = base64encode("example-data")
  }
}