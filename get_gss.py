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

storage_client = storage.Client()
bucket = storage_client.get_bucket(os.environ.get("FITBIT_CREDENTIAL_BUCKET"))
blob = bucket.get_blob(os.environ.get("FITBIT_CREDENTIAL_OBJECT"))
test_txt_content = blob.download_as_text()
token_dict = literal_eval(test_txt_content)
print(token_dict)