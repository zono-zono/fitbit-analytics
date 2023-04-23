import os
import pandas as pd
from google.cloud import bigquery, storage
import fitbit
from ast import literal_eval
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
import pandas_gbq

storage_client = storage.Client()
bucket = storage_client.get_bucket(os.environ.get("FITBIT_CREDENTIAL_BUCKET"))
blob = bucket.get_blob(os.environ.get("FITBIT_CREDENTIAL_OBJECT"))
test_txt_content = blob.download_as_text()
token_dict = literal_eval(test_txt_content)

CLIENT_ID = os.environ.get("FITBIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("FITBIT_CLIENT_SECRET")
access_token = token_dict['access_token']
refresh_token = token_dict['refresh_token']


def updateToken(token):
    f = open(TOKEN_FILE, 'w')
    f.write(str(token))
    f.close()
    return


def build_date_list():
    date_array = []    
    JST = timezone(timedelta(hours=+9),'JST')
    for i in range(1, 2):
        date = datetime.now(JST).date() - timedelta(days = i)
        date_array.append(str(date))
    return date_array


def build_days_metrics_dict(authed_client,dates_list, activity_metrics, sleep_metrics, sleep_levels):
    days_result_dict = {}

    for date in dates_list:
        singleday_activity_metrics = []        

        activity_metrics = activity_metrics
        activity_response = authed_client.activities(date=date)

        for activity_metrics_name in activity_metrics:
            try:
                singleday_activity_metrics.append(activity_response['summary'][activity_metrics_name])
            except:
                singleday_activity_metrics.append(0)                

        sleep_metrics = sleep_metrics
        sleep_response = authed_client.sleep(date=date)

        for sleep_metrics_name in sleep_metrics:
            try:
                singleday_activity_metrics.append(sleep_response["sleep"][0][sleep_metrics_name])
            except:
                singleday_activity_metrics.append(0)

        for sleep_level in sleep_levels:
          try:
            singleday_activity_metrics.append(sleep_response['summary']['stages'][sleep_level])
          except:
            singleday_activity_metrics.append(0)

        days_result_dict[date] = singleday_activity_metrics

    return days_result_dict


def convert_dict_to_dataframe(dic,column_names,index_name):
    converted_df = pd.DataFrame.from_dict(dic,orient = 'index',columns = column_names).reset_index()
    return converted_df    


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
    today_fitbit_df["startTime"] = today_fitbit_df["startTime"].astype(str)
    today_fitbit_df["endTime"] = today_fitbit_df["endTime"].astype(str)
    today_fitbit_df["minuteData"] = today_fitbit_df["minuteData"].astype(str)

    previous_fitbit_df = get_bq_fitbit_df()

    concat_dataframe = pd.concat([previous_fitbit_df, today_fitbit_df], ignore_index=False)
    concat_dataframe.drop_duplicates(inplace=True)

    pandas_gbq.to_gbq(concat_dataframe, dataset_table_id, project_id, if_exists='replace')

    return 'Data has been appended to the table.', 200


append_data_to_bigquery('test', 'test')