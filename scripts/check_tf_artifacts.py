#!/usr/bin/env python3
"""Terraform の state / plan がコミットされていないかを中身で判定する。

このリポジトリでは過去に、plan ファイルが
`terraform/google_storage_bucket_object.function_archive` という
Terraform とは無関係な名前でコミットされ、Client Secret が公開された。

ファイル名でも正規表現でも防げなかったので、
「zip を開いて tfstate / tfplan が入っているか」「JSON が state の形か」
という構造で判定する。
"""

import json
import subprocess
import sys
import zipfile

# plan アーカイブに必ず含まれるエントリ名
PLAN_ENTRIES = {"tfstate", "tfplan", "tfstate-prev"}

# state JSON を特定するキーの組み合わせ
STATE_KEYS = {"terraform_version", "lineage", "resources"}


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def inspect(path):
    """問題があれば理由の文字列を返す。無ければ None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None

    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                names = {n.rsplit("/", 1)[-1] for n in z.namelist()}
        except zipfile.BadZipFile:
            return None
        hit = names & PLAN_ENTRIES
        if hit or any(n.endswith(".tfstate") for n in names):
            return f"Terraform の plan/state アーカイブ（内包: {sorted(hit or names)}）"
        return None

    if head.lstrip()[:1] == b"{":
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        if isinstance(data, dict) and STATE_KEYS <= data.keys():
            return "Terraform の state JSON"

    return None


def main():
    paths = tracked_files()
    findings = [(p, r) for p in paths if (r := inspect(p))]

    if findings:
        print("Terraform の state / plan がコミットされています。", file=sys.stderr)
        print("変数の値が平文で含まれます。削除したうえで、含まれる資格情報を", file=sys.stderr)
        print("すべてローテーションしてください。\n", file=sys.stderr)
        for path, reason in findings:
            print(f"  {path}: {reason}", file=sys.stderr)
        return 1

    print(f"OK: 追跡中の {len(paths)} ファイルに state / plan は無し")
    return 0


if __name__ == "__main__":
    sys.exit(main())
