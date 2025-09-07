from typing import Tuple
from azure.storage.blob import BlobServiceClient
import boto3
from botocore.client import Config as BotoConfig
from core.config import AzureBlobStorageConfigs, S3StorageConfigs, FileStorageConfigs, HostingConfigs
import os


def _upload_to_azure(file) -> Tuple[bool, str, str | None]:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AzureBlobStorageConfigs.CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AzureBlobStorageConfigs.CONTAINER_NAME)
        blob_client = container_client.get_blob_client(file.filename)
        file_content = file.file.read()
        blob_client.upload_blob(file_content, overwrite=True)
        url = blob_client.url
        return True, f"File '{file.filename}' uploaded successfully to Azure Blob Storage.", url
    except Exception as e:
        return False, f"Error uploading file to Azure Blob: {e}", None


def _upload_to_s3(file) -> Tuple[bool, str, str | None]:
    try:
        has_explicit_creds = (
            S3StorageConfigs.ACCESS_KEY_ID and 
            S3StorageConfigs.SECRET_ACCESS_KEY and 
            S3StorageConfigs.SESSION_TOKEN
        )
        if has_explicit_creds:
            credentials = {
                "aws_access_key_id": S3StorageConfigs.ACCESS_KEY_ID,
                "aws_secret_access_key": S3StorageConfigs.SECRET_ACCESS_KEY,
                "aws_session_token": S3StorageConfigs.SESSION_TOKEN,
                "region_name": S3StorageConfigs.REGION or "us-east-1",
                "config": BotoConfig(s3={"addressing_style": "virtual"}),
            }
        else:
            credentials = {
                "region_name": S3StorageConfigs.REGION or "us-east-1",
                "config": BotoConfig(s3={"addressing_style": "virtual"}),
            }

        s3_client = boto3.client("s3", **credentials)
        file_content = file.file.read()
        object_key = file.filename
        bucket_name = S3StorageConfigs.BUCKET_NAME
        if not bucket_name:
            return False, "S3 bucket name is not configured.", None
        s3_client.put_object(Bucket=bucket_name, Key=object_key, Body=file_content)
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket_name, 'Key': object_key},
            ExpiresIn=86400
        )
        return True, f"File '{file.filename}' uploaded successfully to S3.", url
    except Exception as e:
        return False, f"Error uploading file to S3: {e}", None


def _save_to_local(file) -> Tuple[bool, str, str | None]:
    try:
        uploads_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        destination_path = os.path.join(uploads_dir, file.filename)
        with open(destination_path, "wb") as out_f:
            out_f.write(file.file.read())
        url = f"{HostingConfigs.URL}/uploads/{file.filename}"
        return True, f"File '{file.filename}' saved locally.", url
    except Exception as e:
        return False, f"Error saving file locally: {e}", None


def upload_file_to_blob(file):
    provider = (FileStorageConfigs.PROVIDER or "azure").lower()
    if provider == "s3":
        return _upload_to_s3(file)
    elif provider == "local":
        return _save_to_local(file)
    else:
        return _upload_to_azure(file)


