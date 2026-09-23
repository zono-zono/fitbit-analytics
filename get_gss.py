"""GCS 上のトークンの状態を確認する運用スクリプト。

トークンの値そのものは出力しない。値が必要な場合は
`gsutil cat gs://$FITBIT_CREDENTIAL_BUCKET/$FITBIT_CREDENTIAL_OBJECT` を
直接使うこと（端末履歴に残る点には注意）。
"""

import os
from datetime import datetime, timezone

from main import load_token


def main():
    token = load_token()

    print(f"バケット : {os.environ['FITBIT_CREDENTIAL_BUCKET']}")
    print(f"オブジェクト: {os.environ['FITBIT_CREDENTIAL_OBJECT']}")
    print(f"保持キー : {sorted(token.keys())}")

    expires_at = token.get("expires_at")
    if expires_at:
        expires = datetime.fromtimestamp(float(expires_at), tz=timezone.utc)
        remaining = expires - datetime.now(timezone.utc)
        print(f"有効期限 : {expires.isoformat()} (残り {remaining})")


if __name__ == "__main__":
    main()
