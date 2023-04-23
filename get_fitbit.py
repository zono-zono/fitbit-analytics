import fitbit
from ast import literal_eval
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

# fitbit APIに必要な情報の定義
TOKEN_FILE = "test.txt"
tokens = open(TOKEN_FILE).read()

token_dict = literal_eval(tokens)
CLIENT_ID = "2398NR"
CLIENT_SECRET = "187c78a52eacdb491f98fb980ec807f2"
access_token = token_dict['access_token']
refresh_token = token_dict['refresh_token']

def updateToken(token):
    f = open(TOKEN_FILE, 'w')
    f.write(str(token))
    f.close()
    return

client = fitbit.Fitbit(CLIENT_ID, CLIENT_SECRET,
                       access_token = access_token, refresh_token = refresh_token, refresh_cb = updateToken)

# 日付リストを作成する。範囲は自分で設定する。
def build_date_list():
    date_array = []    
    # タイムゾーンの生成
    JST = timezone(timedelta(hours=+9),'JST')
    for i in range(0, 1):
        date = datetime.now(JST).date() - timedelta(days = i)
        date_array.append(str(date))
    return date_array

# データを日別で取得し、辞書を返却する(Activity系とSleep系の2つを含む)
def build_days_metrics_dict(authed_client,dates_list, activity_metrics, sleep_metrics):
    days_result_dict = {}

    for date in dates_list:
        singleday_activity_metrics = []        

        # 該当日のActivity系の指標を取得
        activity_metrics = activity_metrics
        activity_response = authed_client.activities(date=date)
        for activity_metrics_name in activity_metrics:
            try:
                singleday_activity_metrics.append(activity_response['summary'][activity_metrics_name])
            except:
                singleday_activity_metrics.append(0)                

        # 該当日のSleep系の指標を取得
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

        # 該当日の指標を辞書に格納
        days_result_dict[date] = singleday_activity_metrics

    return days_result_dict


# 必要なメトリクス
activity_metrics = ['duration','efficiency','min','max','name','minutes','caloriesOut','distance','steps','lightlyActiveMinutes','veryActiveMinutes','sedentaryMinutes']
sleep_metrics = ['timeInBed','minutesAwake','minutesAsleep','restlessCount','restlessDuration','minutesToFallAsleep','startTime','endTime','awakeDuration','awakeningsCount','minuteData']
sleep_levels = ['deep', 'light', 'rem', 'wake']

# 時系列リストの生成
dates_list = build_date_list()

# DictをDataFrameに変換する
def convert_dict_to_dataframe(dic,column_names,index_name):
    converted_df = pd.DataFrame.from_dict(dic,orient = 'index',columns = column_names).reset_index()
    return converted_df    

# 日別データの取得 -> DataFrameに変換
## データの取得
days_result_dict = build_days_metrics_dict(client, dates_list, activity_metrics, sleep_metrics)

## DataFrameに変換
days_clumns_name = activity_metrics + sleep_metrics + sleep_levels
days_result_df = convert_dict_to_dataframe(days_result_dict,days_clumns_name,'date')
renamed_days_result_df = days_result_df.rename(columns = {'min': 'active_min', 'max': 'active_max','minutes': 'active_minutes'})

print(renamed_days_result_df)