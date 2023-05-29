# 健康データの分析基盤

![68747470733a2f2f71696974612d696d6167652d73746f72652e73332e61702d6e6f727468656173742d312e616d617a6f6e6177732e636f6d2f302f3633333239372f38353731656562642d326661642d383538322d383338352d3761393133663139613161382e706e67](https://github.com/zono-zono/fitbit-analytics/assets/131334459/c42a98b8-d243-44fe-a074-a0c74978aa6c)


## 使用技術
一貫性と再現性やバージョン管理の観点から全てをTerraformで作成しております。
### ①定期実行（Scheduler,PubSub）
Cloud Schedulerでは毎日午前1:00にPub/Subを利用して定期実行させて処理を自動化させていきます。特に運用負荷もそこま無いのでリアルタイムメッセージングサービスであるPub/Subは使用する必要性は無いのですが勉強のため使用しています。

```terraform
resource "google_pubsub_topic" "trigger_topic" {
  name = "fitbit-insert-topic"
}

resource "google_cloud_scheduler_job" "daily_job" {
  name             = "fitbit-api-job"
  schedule         = "0 1 * * *"
  time_zone        = "Asia/Tokyo"
  description      = "This job triggers the Cloud Function daily at 1:00 JTC."
  
  pubsub_target {
    topic_name = google_pubsub_topic.trigger_topic.id
    data       = base64encode("example-data")
  }
}
```

### ②過去のデータ取得（CloudFunction,BigQuery）
これまでの数年分のデータがBigQueryに溜まっているのですが、これを毎回Cloud Functionで全取得していきます。1つのデータを既存テーブルに追加する方が処理が楽になるのではないかとは思いますが、この理由については後述します。

必要なクレデンシャル情報については全て環境変数として扱い、Cloud Functionに渡すようにしています。

```terraform
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

resource "google_bigquery_table" "warehouse_health_sleep" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  table_id   = var.bigquery_table_id
  deletion_protection = false
}

resource "google_bigquery_job" "load_csv" {
  job_id = "load_csv_job"

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
  location = var.region
}
```

```python
def get_bq_fitbit_df():
    project_id = os.environ.get("BIGQUERY_PROJECT_ID")
    dataset_id = os.environ.get("BIGQUERY_DARASET_ID")
    table_id = os.environ.get("BIGQUERY_TABLE_ID")
    bigquery_client = bigquery.Client()

    # SQL クエリを作成
    query = f"""
    SELECT *
    FROM `{project_id}.{dataset_id}.{table_id}`
    """

    query_job = bigquery_client.query(query)
    fitbit_df = query_job.to_dataframe()

    return fitbit_df
```

### ③Token,RefreshToken取得（Storage）
FitbitのAPIを叩くにはTokenが必要なのですが、Tokenの有効期限は8時間と短いのでRefreshTokenを使用してTokenとRefreshTokenを更新します。詳しい説明はこちらの記事を見るのが良いと思います。

https://zenn.dev/ayumukob/articles/640cbf4a1ff3ed


今回はこのTokenはCloud Functionで更新するのでTokenの情報はGCSにアップして更新し続けるような設定にしておきました。
```python
def updateToken(token):
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(os.environ.get("FITBIT_CREDENTIAL_BUCKET"))
    blob = bucket.get_blob(os.environ.get("FITBIT_CREDENTIAL_OBJECT"))
    json_token = json.dumps(token)
    bytes_token = json_token.encode() 
    # GCSのオブジェクトを更新
    blob.upload_from_string(bytes_token)
```

### ④前日データ取得（Fitbit API）
FitbitのAPIから前日分のデータを取得するコードを書きます。何故当日ではなく、前日のデータを取得する必要があるでしょうか？
それは前日23:59までの消費カロリーなどのデータを完全な状態で取得したかったからです。

```python
def build_days_metrics_dict(authed_client,dates_list, activity_metrics, sleep_metrics, sleep_levels):
    days_result_dict = {}

    for date in dates_list:
        day_metrics = []        

        activity_metrics = activity_metrics
        activity_response = authed_client.activities(date=date)

        for activity_metrics_name in activity_metrics:
            try:
                day_metrics.append(activity_response['summary'][activity_metrics_name])
            except:
                day_metrics.append(0)                

        sleep_metrics = sleep_metrics
        sleep_response = authed_client.sleep(date=date)

        for sleep_metrics_name in sleep_metrics:
            try:
                day_metrics.append(sleep_response["sleep"][0][sleep_metrics_name])
            except:
                day_metrics.append(0)

        for sleep_level in sleep_levels:
          try:
            day_metrics.append(sleep_response['summary']['stages'][sleep_level])
          except:
            day_metrics.append(0)

        days_result_dict[date] = day_metrics

    return days_result_dict
```

### ⑤データ更新（BigQuery）
③と④で取得した過去データと最新である前日データをconcatしてデータを更新していきます。
なぜ前日データだけを今まで溜まったテーブルにappendしないのでしょうか？これはデータの整合性、冪等性を意識した結果、全データをreplaceする形にした方が良いからです。

詳しいことは以下の記事がすごく参考になります。

https://techblog.zozo.com/entry/idempotent-data-insert-in-bigquery

```python
def append_data_to_bigquery(request, context):
    project_id = os.environ.get("BIGQUERY_PROJECT_ID")
    dataset_id = os.environ.get("BIGQUERY_DARASET_ID")
    table_id = os.environ.get("BIGQUERY_TABLE_ID")
    dataset_table_id = f"{dataset_id}.{table_id}"
    fitbit_client = fitbit.Fitbit(CLIENT_ID, CLIENT_SECRET,
                       access_token = access_token, refresh_token = refresh_token, refresh_cb = updateToken)

    # 必要なメトリクス
    activity_metrics = ['duration','efficiency','min','max','name','minutes','caloriesOut','distance','steps','lightlyActiveMinutes','veryActiveMinutes','sedentaryMinutes']
    sleep_metrics = ['timeInBed','minutesAwake','minutesAsleep','restlessCount','restlessDuration','minutesToFallAsleep','startTime','endTime','awakeDuration','awakeningsCount','minuteData']
    sleep_levels = ['deep', 'light', 'rem', 'wake']

    dates_list = build_date_list()
    days_result_dict = build_days_metrics_dict(fitbit_client, dates_list, activity_metrics, sleep_metrics, sleep_levels)

    days_clumns_name = activity_metrics + sleep_metrics + sleep_levels
    today_fitbit_df = convert_dict_to_dataframe(days_result_dict,days_clumns_name,'date')

    previous_fitbit_df = get_bq_fitbit_df()

    concat_dataframe = pd.concat([previous_fitbit_df, today_fitbit_df], ignore_index=False)

    pandas_gbq.to_gbq(concat_dataframe, dataset_table_id, project_id, if_exists='replace')

    return 'Data has been appended to the table.', 200
```
### ⑥可視化（Looker Studio）
ここからはデータ活用フェーズです。
わざわざBigQueryでクエリを叩かなくともBIツールであるLooker Studioで最新データを可視化できれば良さそうですよね。

![スクリーンショット 2023-04-29 22.08.03.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/633297/176aef5c-6c45-e151-1523-fb2ac586697f.png)
![スクリーンショット 2023-04-29 22.08.35.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/633297/ae25e97c-7e57-39d1-7a89-1bc2a06a87c6.png)
