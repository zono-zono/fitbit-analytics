import os
from google.cloud import bigquery
from datetime import datetime

def bigquery_insert_data(request):
    client = bigquery.Client()
    table_id = os.environ.get("BIGQUERY_TABLE_ID")

    rows_to_insert = [
        {
            "field1": "value1",
            "field2": "value2",
            "inserted_at": datetime.utcnow().isoformat()
        },
    ]

    errors = client.insert_rows_json(table_id, rows_to_insert)

    if errors == []:
        return "Inserted rows into {}.".format(table_id), 200
    else:
        return "Encountered errors while inserting rows: {}".format(errors), 400
