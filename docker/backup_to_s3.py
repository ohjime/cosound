"""Stream a pg_dump from stdin to S3 and prune old backups.

Runs inside the app container (boto3 + AWS env vars already present):
    pg_dump ... | python backup_to_s3.py cosound-db-20260611.dump

Keeps the newest DB_BACKUP_RETAIN (default 14) objects under db-backups/.
"""

import os
import sys

import boto3

PREFIX = "db-backups/"
RETAIN = int(os.environ.get("DB_BACKUP_RETAIN", 14))

bucket = os.environ["AWS_STORAGE_BUCKET_NAME"]
key = PREFIX + sys.argv[1]

s3 = boto3.client("s3", region_name=os.environ.get("AWS_S3_REGION_NAME"))
s3.upload_fileobj(sys.stdin.buffer, bucket, key)
print(f"uploaded s3://{bucket}/{key}")

# Timestamped names sort chronologically, so key order == age order
objects = sorted(
    s3.list_objects_v2(Bucket=bucket, Prefix=PREFIX).get("Contents", []),
    key=lambda o: o["Key"],
)
for old in objects[:-RETAIN]:
    s3.delete_object(Bucket=bucket, Key=old["Key"])
    print(f"pruned s3://{bucket}/{old['Key']}")
