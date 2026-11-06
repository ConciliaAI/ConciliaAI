import time

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.config import Config
from app.config import get_settings


def client():
    s = get_settings()
    return boto3.client("s3", endpoint_url=f"http://{s.minio_endpoint}",
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
        region_name="us-east-1", config=Config(signature_version="s3v4"))


def ensure_bucket() -> None:
    bucket = get_settings().minio_bucket
    for attempt in range(30):
        try:
            s3 = client()
            try:
                s3.head_bucket(Bucket=bucket)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
                    raise
                s3.create_bucket(Bucket=bucket)
            return
        except (EndpointConnectionError, ConnectionError):
            if attempt == 29:
                raise
            time.sleep(2)


def upload_stream(key: str, body, content_type: str):
    client().upload_fileobj(body, get_settings().minio_bucket, key,
        ExtraArgs={"ContentType": content_type})


def download_bytes(key: str) -> bytes:
    response = client().get_object(Bucket=get_settings().minio_bucket, Key=key)
    try:
        return response["Body"].read()
    finally:
        response["Body"].close()
