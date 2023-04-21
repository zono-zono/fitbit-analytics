import os
from google.cloud import bigquery
from google.cloud import storage

def insert_data_to_bigquery(data, context):
    bigquery_client = bigquery.Client()
    
    dataset_id = os.environ.get('BIGQUERY_DATASET_ID')
    table_id = os.environ.get('BIGQUERY_TABLE_ID')
    
    table_ref = bigquery_client.dataset(dataset_id).table(table_id)
    table = bigquery_client.get_table(table_ref)
    
    rows_to_insert = [data]
    
    errors = bigquery_client.insert_rows(table, rows_to_insert)
    if errors == []:
        print('Data inserted successfully!')
    else:
        print('Errors:', errors)
