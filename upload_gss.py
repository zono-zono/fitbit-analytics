"""初回のトークンを GCS に配置するブートストラップ用スクリプト。

Fitbit の認可フローで取得した access_token / refresh_token を
ローカルの JSON ファイルに置いてから 1 度だけ実行する。
以降の更新は Cloud Function 側の save_token() が行う。

このスクリプトが読むファイルは .gitignore 済み。コミットしないこと。
"""

import json
import os
import sys

from google.cloud import storage

DEFAULT_TOKEN_FILE = "fitbit_credential.txt"


def main(file_path):
    with open(file_path, encoding="utf-8") as f:
        token = json.load(f)

    missing = {"access_token", "refresh_token"} - token.keys()
    if missing:
        raise SystemExit(f"必須キーがありません: {sorted(missing)}")

    bucket_name = os.environ["FITBIT_CREDENTIAL_BUCKET"]
    object_name = os.environ["FITBIT_CREDENTIAL_OBJECT"]

    storage.Client().bucket(bucket_name).blob(object_name).upload_from_string(
        json.dumps(token)
    )
    print(f"アップロードしました: gs://{bucket_name}/{object_name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOKEN_FILE)
