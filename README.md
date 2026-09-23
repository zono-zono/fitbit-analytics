# 健康データの分析基盤

![アーキテクチャ図](https://github.com/zono-zono/fitbit-analytics/assets/131334459/c42a98b8-d243-44fe-a074-a0c74978aa6c)


---

## セットアップ

### 前提

- `gcloud` / `terraform` / Python 3.10
- Fitbit の開発者アプリ（[dev.fitbit.com](https://dev.fitbit.com/apps)）

### 1. 認証

サービスアカウントキーのファイルは作りません。ADC を使います。

```bash
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
```

### 2. Terraform の state 用バケット（初回のみ）

state には変数の値が平文で入ります。ローカルに置かず、バージョニングを有効にした
GCS バケットで管理します。

```bash
gsutil mb -l asia-northeast1 gs://<PROJECT_ID>-tfstate
gsutil versioning set on gs://<PROJECT_ID>-tfstate

cp terraform/backend.hcl.example terraform/backend.hcl   # バケット名を書く
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

### 3. Client Secret を Secret Manager に入れる

**`terraform.tfvars` には書きません。** 書くと state に平文で残ります。

```bash
gcloud secrets create fitbit-client-secret --replication-policy=user-managed --locations=asia-northeast1
printf '%s' '<Fitbit Client Secret>' | gcloud secrets versions add fitbit-client-secret --data-file=-
```

Terraform はシークレットの「入れ物」だけを作り、値は名前で参照します
（`secret_environment_variables`）。値は state を経由しません。

### 4. デプロイ

```bash
terraform -chdir=terraform init -backend-config=backend.hcl
terraform -chdir=terraform apply
```

Cloud Function の zip は `data "archive_file"` が `main.py` と `requirements.txt` から
生成します。手動で zip を作ってコミットする必要はありません。

### 5. 初期トークンの配置

Fitbit の認可フローで取得した `access_token` / `refresh_token` を JSON で保存し、
1 度だけアップロードします。以降の更新は Cloud Function が行います。

```bash
export FITBIT_CREDENTIAL_BUCKET=<バケット名>
export FITBIT_CREDENTIAL_OBJECT=fitbit_credential.txt
python upload_gss.py fitbit_credential.txt   # このファイルは .gitignore 済み
```

状態の確認は `python get_gss.py`（トークンの値そのものは表示しません）。

---

## このリポジトリで秘密情報を扱うときの約束

過去に Terraform の plan ファイルが `terraform/google_storage_bucket_object.function_archive`
という名前でコミットされ、**Fitbit の Client Secret が公開されました**。
名前からは Terraform の成果物だと分からず、`.gitignore` も正規表現も素通りしました。

そのため、次の 3 つを守ってください。

1. **秘密の値を Terraform の変数として渡さない。** 入れ物だけを Terraform で作り、
   値は `gcloud secrets versions add` で入れる。変数に渡すと必ず state に平文で残る
2. **state と plan をリポジトリに置かない。** backend を GCS にして、
   plan は `-out` を使うなら `*.tfplan` という名前にする
3. **CI の `secret-scan` を落としたままマージしない。**
   `scripts/check_tf_artifacts.py` が zip と JSON の中身を開いて state / plan を検出します


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

必要なクレデンシャル情報のうち、秘密でないもの（プロジェクト ID やバケット名、OAuth の仕様上公開される Client ID）は環境変数として Cloud Function に渡します。
**Client Secret だけは値を Terraform に渡さず**、Secret Manager のシークレット名を参照させます。Terraform の変数に渡すと state に平文で残るためです。

なお、過去データの初回ロード（`google_bigquery_job`）は一度きりの作業で、BigQuery のジョブ ID は再利用できず 2 回目の `apply` で衝突します。Terraform の管理対象からは外しました。

```terraform
resource "google_cloudfunctions_function" "bigquery_insert_function" {
  name        = "fitbit-bigquery-insert-function"
  runtime     = "python310"
  entry_point = "append_data_to_bigquery"

  source_archive_bucket = google_storage_bucket.cloud_function_bucket.name
  source_archive_object = google_storage_bucket_object.function_archive.name

  service_account_email = google_service_account.function.email

  environment_variables = {
    FITBIT_CREDENTIAL_BUCKET = google_storage_bucket.cloud_function_bucket.name
    FITBIT_CREDENTIAL_OBJECT = var.fitbit_credential_object
    FITBIT_CLIENT_ID         = var.fitbit_client_id
    BIGQUERY_PROJECT_ID      = var.project_id
    BIGQUERY_DATASET_ID      = var.bigquery_dataset_id
    BIGQUERY_TABLE_ID        = var.bigquery_table_id
  }

  # Client Secret は値ではなく名前で参照する。state には入らない。
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
}

resource "google_bigquery_table" "warehouse_health_sleep" {
  dataset_id = google_bigquery_dataset.fitbit_analytics_dataset.dataset_id
  table_id   = var.bigquery_table_id

  # 数年分の健康データが入る。terraform destroy で消えないようにする。
  deletion_protection = true
}
```

```python
def get_bq_fitbit_df(project_id, dataset_id, table_id):
    bigquery_client = bigquery.Client(project=project_id)

    # クエリではなく tabledata.list で読む。全件 SELECT * の課金が発生しない。
    table_ref = bigquery.TableReference.from_string(
        f"{project_id}.{dataset_id}.{table_id}"
    )
    return bigquery_client.list_rows(table_ref).to_dataframe()
```

### ③Token,RefreshToken取得（Storage）
FitbitのAPIを叩くにはTokenが必要なのですが、Tokenの有効期限は8時間と短いのでRefreshTokenを使用してTokenとRefreshTokenを更新します。詳しい説明はこちらの記事を見るのが良いと思います。

https://zenn.dev/ayumukob/articles/640cbf4a1ff3ed


今回はこのTokenはCloud Functionで更新するのでTokenの情報はGCSにアップして更新し続けるような設定にしておきました。
```python
def save_token(token):
    """Fitbit SDK がトークンを更新したときに呼ばれるコールバック。"""
    _token_blob().upload_from_string(json.dumps(token))
    # トークンの値そのものはログに出さない
    logger.info("トークンを更新しました（有効期限: %s）", token.get("expires_at", "unknown"))
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

ただし replace はテーブルを作り直すため、取得側が壊れていると数年分が消えます。書き込み前に行数が減っていないかを確認し、減る場合は書き込まずに失敗させています。

詳しいことは以下の記事がすごく参考になります。

https://techblog.zozo.com/entry/idempotent-data-insert-in-bigquery

```python
def append_data_to_bigquery(event, context):
    """Pub/Sub トリガーのエントリポイント。"""
    project_id = os.environ["BIGQUERY_PROJECT_ID"]
    dataset_id = os.environ["BIGQUERY_DATASET_ID"]
    table_id = os.environ["BIGQUERY_TABLE_ID"]
    dataset_table_id = f"{dataset_id}.{table_id}"

    token = load_token()
    fitbit_client = fitbit.Fitbit(
        os.environ["FITBIT_CLIENT_ID"],
        os.environ["FITBIT_CLIENT_SECRET"],   # Secret Manager から実行時に解決される
        access_token=token["access_token"],
        refresh_token=token["refresh_token"],
        refresh_cb=save_token,
    )

    dates_list = build_date_list()
    days_result_dict = build_days_metrics_dict(fitbit_client, dates_list)

    column_names = ACTIVITY_METRICS + SLEEP_METRICS + SLEEP_LEVELS
    today_fitbit_df = convert_dict_to_dataframe(days_result_dict, column_names)
    for column in ("startTime", "endTime", "minuteData"):
        today_fitbit_df[column] = today_fitbit_df[column].astype(str)

    previous_fitbit_df = get_bq_fitbit_df(project_id, dataset_id, table_id)

    concat_dataframe = pd.concat([previous_fitbit_df, today_fitbit_df], ignore_index=False)
    concat_dataframe.drop_duplicates(inplace=True)

    # if_exists="replace" はテーブルを作り直す。行数が減る結果になったら
    # 取得側のどこかが壊れているので、書き込まずに失敗させる。
    if len(concat_dataframe) < len(previous_fitbit_df):
        raise RuntimeError(
            "書き込み後の行数が既存より少なくなります "
            f"（既存 {len(previous_fitbit_df)} 行 → {len(concat_dataframe)} 行）。"
            "全件 replace のため中断します。"
        )

    pandas_gbq.to_gbq(concat_dataframe, dataset_table_id, project_id, if_exists="replace")
    logger.info("%s に %d 行を書き込みました", dataset_table_id, len(concat_dataframe))

    return "Data has been appended to the table.", 200
```
### ⑥可視化（Looker Studio）
ここからはデータ活用フェーズです。
わざわざBigQueryでクエリを叩かなくともBIツールであるLooker Studioで最新データを可視化できれば良さそうですよね。

![スクリーンショット 2023-04-29 22.08.03.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/633297/176aef5c-6c45-e151-1523-fb2ac586697f.png)
![スクリーンショット 2023-04-29 22.08.35.png](https://qiita-image-store.s3.ap-northeast-1.amazonaws.com/0/633297/ae25e97c-7e57-39d1-7a89-1bc2a06a87c6.png)
