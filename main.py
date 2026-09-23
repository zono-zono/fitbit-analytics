import json
import logging
import os
from ast import literal_eval
from datetime import datetime, timedelta, timezone

import fitbit
import pandas as pd
import pandas_gbq
from google.cloud import bigquery, storage

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=+9), "JST")

# 必要なメトリクス
ACTIVITY_METRICS = [
    "duration", "efficiency", "min", "max", "name", "minutes", "caloriesOut",
    "distance", "steps", "lightlyActiveMinutes", "veryActiveMinutes", "sedentaryMinutes",
]
SLEEP_METRICS = [
    "timeInBed", "minutesAwake", "minutesAsleep", "restlessCount", "restlessDuration",
    "minutesToFallAsleep", "startTime", "endTime", "awakeDuration", "awakeningsCount",
    "minuteData",
]
SLEEP_LEVELS = ["deep", "light", "rem", "wake"]

# レスポンスから値を取り出すときに許容する例外。
# 「その日に該当データが無い」場合だけを 0 に倒す。
# API 呼び出し自体の失敗（認証切れ・レート超過・ネットワーク断）は
# ここでは捕まえず、そのまま送出して実行を失敗させる。
_MISSING = (KeyError, IndexError, TypeError)


def _token_blob():
    """トークンを保存している GCS オブジェクトを返す。"""
    bucket_name = os.environ["FITBIT_CREDENTIAL_BUCKET"]
    object_name = os.environ["FITBIT_CREDENTIAL_OBJECT"]

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(
            f"トークンオブジェクトが存在しません: gs://{bucket_name}/{object_name}. "
            "upload_gss.py で初期トークンを配置してください。"
        )
    return blob


def load_token():
    """GCS からトークンを読む。値はログに出さない。"""
    raw = _token_blob().download_as_text()
    try:
        token = json.loads(raw)
    except json.JSONDecodeError:
        # 旧形式（Python の repr を str() で書き出したもの）との後方互換
        token = literal_eval(raw)

    missing = {"access_token", "refresh_token"} - token.keys()
    if missing:
        raise ValueError(f"トークンに必須キーがありません: {sorted(missing)}")

    logger.info("トークンを読み込みました（有効期限: %s）", token.get("expires_at", "unknown"))
    return token


def save_token(token):
    """Fitbit SDK がトークンを更新したときに呼ばれるコールバック。"""
    _token_blob().upload_from_string(json.dumps(token))
    logger.info("トークンを更新しました（有効期限: %s）", token.get("expires_at", "unknown"))


def build_date_list():
    """取得対象の日付リスト。前日分のみを対象にする。"""
    return [str(datetime.now(JST).date() - timedelta(days=i)) for i in range(1, 2)]


def build_days_metrics_dict(authed_client, dates_list):
    days_result_dict = {}

    for date in dates_list:
        day_metrics = []

        activity_response = authed_client.activities(date=date)
        for name in ACTIVITY_METRICS:
            try:
                day_metrics.append(activity_response["summary"][name])
            except _MISSING:
                day_metrics.append(0)

        sleep_response = authed_client.sleep(date=date)
        for name in SLEEP_METRICS:
            try:
                day_metrics.append(sleep_response["sleep"][0][name])
            except _MISSING:
                day_metrics.append(0)

        for level in SLEEP_LEVELS:
            try:
                day_metrics.append(sleep_response["summary"]["stages"][level])
            except _MISSING:
                day_metrics.append(0)

        days_result_dict[date] = day_metrics

    return days_result_dict


def convert_dict_to_dataframe(dic, column_names):
    return pd.DataFrame.from_dict(dic, orient="index", columns=column_names).reset_index()


def get_bq_fitbit_df(project_id, dataset_id, table_id):
    bigquery_client = bigquery.Client(project=project_id)

    # テーブル名は環境変数由来なので、識別子として妥当かを検証してから埋め込む
    table_ref = bigquery.TableReference.from_string(
        f"{project_id}.{dataset_id}.{table_id}"
    )
    return bigquery_client.list_rows(table_ref).to_dataframe()


def append_data_to_bigquery(event, context):
    """Pub/Sub トリガーのエントリポイント。"""
    project_id = os.environ["BIGQUERY_PROJECT_ID"]
    dataset_id = os.environ["BIGQUERY_DATASET_ID"]
    table_id = os.environ["BIGQUERY_TABLE_ID"]
    dataset_table_id = f"{dataset_id}.{table_id}"

    token = load_token()
    fitbit_client = fitbit.Fitbit(
        os.environ["FITBIT_CLIENT_ID"],
        os.environ["FITBIT_CLIENT_SECRET"],
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    append_data_to_bigquery(None, None)
