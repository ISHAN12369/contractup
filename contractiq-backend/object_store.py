"""Private S3/R2 objects; short-lived download signatures issued after ownership checks."""
import hashlib
from typing import Any

import boto3
from botocore.config import Config

from config import Settings
from errors import ServiceError


class ObjectStore:
    def __init__(self, settings: Settings, client: Any = None, signing_client: Any = None):
        self.settings = settings
        options = dict(region_name=settings.s3_region, aws_access_key_id=settings.s3_access_key,
                       aws_secret_access_key=settings.s3_secret_key,
                       config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=15,
                                     retries={"max_attempts": 2}, s3={"addressing_style": "path"}))
        self.client = client or boto3.client("s3", endpoint_url=settings.s3_endpoint, **options)
        self.signer = signing_client or (boto3.client("s3", endpoint_url=settings.s3_public_endpoint, **options)
                                         if settings.s3_public_endpoint else self.client)

    @staticmethod
    def key(owner: str, doc_id: str) -> str:
        return f"documents/{hashlib.sha256(owner.encode()).hexdigest()}/{doc_id}/original"

    def put(self, key: str, content: bytes) -> None:
        self.client.put_object(Bucket=self.settings.s3_bucket, Key=key, Body=content,
                               ContentType="application/octet-stream")

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.settings.s3_bucket, Key=key)
        stream = response["Body"]
        try:
            content = stream.read(self.settings.max_upload_bytes + 1)
            if len(content) > self.settings.max_upload_bytes:
                raise ServiceError(413, "Stored upload exceeds the size limit.")
            return bytes(content)
        finally:
            stream.close()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.settings.s3_bucket, Key=key)

    def signed_url(self, key: str, seconds: int) -> str:
        return str(self.signer.generate_presigned_url("get_object", Params={
            "Bucket": self.settings.s3_bucket, "Key": key,
            "ResponseContentDisposition": 'attachment; filename="contract.pdf"',
            "ResponseContentType": "application/pdf"}, ExpiresIn=seconds))
