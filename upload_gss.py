import os
import pandas as pd
from google.cloud import bigquery, storage
import fitbit
from ast import literal_eval
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
import pandas_gbq
import json

# ファイルを読み込む関数
def read_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    return content

# ファイルのパスを指定
file_path = 'fitbit_credential.txt'

# ファイルを読み込み、文字列を取得
text = read_file(file_path)

# 取得した文字列を出力
print(text)

# GCSのオブジェクトを更新
storage_client = storage.Client()
bucket = storage_client.get_bucket(os.environ.get("FITBIT_CREDENTIAL_BUCKET"))
blob = bucket.get_blob(os.environ.get("FITBIT_CREDENTIAL_OBJECT"))
blob.upload_from_string(text)