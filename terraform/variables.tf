variable "project_id" {
  type        = string
  description = "The ID of the project to deploy the resources in."
}

variable "region" {
  type        = string
  description = "The region to deploy the resources in."
}

variable "bucket_name" {
type = string
description = "The name of the Google Cloud Storage bucket to use for Cloud Function deployment."
}

variable "function_name" {
type = string
description = "The name of the Cloud Function to deploy."
}

variable "bigquery_dataset_id" {
type = string
description = "The ID of the BigQuery dataset to insert data into."
}

variable "bigquery_table_id" {
type = string
description = "The ID of the BigQuery table to insert data into."
}

variable "scheduler_job_name" {
  type        = string
  description = "The name of the Cloud Scheduler job to create."
}

variable "credential_path" {
  type        = string
  description = "Path to the GCP service account credentials JSON file"
}