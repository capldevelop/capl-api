# app/utils/s3_handler.py
import boto3
from fastapi import UploadFile
from core.config import settings
import uuid
from datetime import datetime

# boto3 S3 클라이언트 초기화 주석 처리
s3_client = boto3.client(
    's3',
    aws_access_key_id=settings.AWS_S3_ACCESS_KEY,
    aws_secret_access_key=settings.AWS_S3_SECRET_KEY,
    region_name=settings.AWS_REGION
)

def create_presigned_upload_url(directory: str, filename: str, expiration: int = 3600) -> dict | None:
    """[추가] S3 파일 업로드를 위한 Presigned URL과 파일 경로를 생성합니다."""
    file_extension = filename.split('.')[-1]
    unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4()}.{file_extension}"
    file_path = f"{directory}/{unique_name}"
    
    try:
        url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_S3_BUCKET_NAME, 
                'Key': file_path,
                # 'ContentType': 'image/jpeg' # 필요 시 파일 타입 강제
            },
            ExpiresIn=expiration
        )
        return {"uploadUrl": url, "filePath": file_path}
    except ClientError as e:
        print(f"ERROR: Presigned URL 생성 실패 - {e}")
        return None

def create_presigned_download_url(file_path: str, expiration: int = 3600) -> str | None:
    """[추가] S3 파일 접근(다운로드)을 위한 Presigned URL을 생성합니다."""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_S3_BUCKET_NAME, 'Key': file_path},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        print(f"ERROR: Presigned URL 생성 실패 - {e}")
        return None

def upload_file_to_s3(file: UploadFile, directory: str) -> str:
    """S3에 파일을 업로드하고 파일 경로를 반환합니다."""
    
    print(f"--- S3 Upload Skipped (boto3 not installed) ---")
    print(f"--- File: {file.filename}, Directory: {directory} ---")
    
    # S3 클라이언트 로직 주석 처리
    file_extension = file.filename.split('.')[-1]
    file_name = f"{uuid.uuid4()}-{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.{file_extension}"
    file_path = f"{directory}/{file_name}"

    s3_client.upload_fileobj(
        file.file,
        settings.AWS_S3_BUCKET_NAME,
        file_path
    )
    return file_path
    return f"{directory}/temp_file_path_for_{file.filename}" # 임시 경로 반환

def get_file_url(file_path: str) -> str:
    """S3 파일 경로로 접근 가능한 URL을 생성합니다."""
    return f"{settings.AWS_S3_PUBLIC_URL}/{file_path}"

def delete_files_from_s3(file_paths: list[str]):
    """S3에서 여러 파일을 삭제합니다."""
    print(f"--- S3 Delete Skipped (boto3 not installed) ---")
    print(f"--- Files to delete: {file_paths} ---")
    
    # S3 클라이언트 로직 주석 처리
    if not file_paths:
        return
        
    objects_to_delete = [{'Key': path} for path in file_paths]
    s3_client.delete_objects(
        Bucket=settings.AWS_S3_BUCKET_NAME,
        Delete={'Objects': objects_to_delete}
    )
    pass
