# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # =========================
    # DB 설정
    # =========================
    DB_URL: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_SCHEMA: str
    DATABASE_URL: str

    # =========================
    # JWT
    # =========================
    SECRET_KEY: str
    ALGORITHM: str
    JWT_ACCESS_EXPIRATION_DAYS: int = 1
    JWT_REFRESH_EXPIRATION_DAYS: int = 7

    # =========================
    # OAuth2 Providers
    # =========================
    # Kakao
    KAKAO_CLIENT_ID: str
    KAKAO_CLIENT_SECRET: str
    KAKAO_REDIRECT_URI: str
    KAKAO_TOKEN_URI: str
    KAKAO_USER_INFO_URI: str

    # Google
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    GOOGLE_TOKEN_URI: str
    GOOGLE_USER_INFO_URI: str

    # Apple
    APPLE_CLIENT_ID: str
    APPLE_TEAM_ID: str
    APPLE_LOGIN_KEY: str
    APPLE_KEY_PATH: str
    APPLE_REDIRECT_URI: str
    APPLE_TOKEN_URI: str
    APPLE_KEY_URI: str

    # =========================
    # Kakao Map
    # =========================
    KAKAO_MAP_KEY: str

    # =========================
    # AWS 설정
    # =========================
    AWS_REGION: str

    # SNS
    AWS_SNS_ARN: str
    AWS_SNS_ACCESS_KEY: str
    AWS_SNS_SECRET_KEY: str

    # S3
    AWS_S3_PUBLIC_URL: str
    AWS_S3_BUCKET_NAME: str
    AWS_S3_ACCESS_KEY: str
    AWS_S3_SECRET_KEY: str

    # =========================
    # Mobile 인증
    # =========================
    HOST: str
    MOBILE_KEY_PATH: str
    MOBILE_KEY_PASSWORD: str
    MOBILE_CLIENT_PREFIX: str
    MOBILE_URL: str
    
    # =========================
    # FIREBASE 설정
    # =========================
    FIREBASE_ADMIN_SDK_PATH: str
    
    # =========================
    # API 설정
    # =========================
    HOLIDAY_API_URL: str
    HOLIDAY_API_SERVICE_KEY: str
    
    # =========================
    # CCTV 설정
    # =========================
    CCTV_PHONE: str
    CCTV_VERIFICATION_ENABLED: bool = True
    REQUEST_TIMEOUT_SECONDS: int = 60
    HEARTBEAT_INTERVAL_SECONDS: int = 60
    CLIENT_SECRET_KEY: str
    
    # =========================
    # TCP 설정
    # =========================
    # TCP 서버 설정
    TCP_HOST: str = "0.0.0.0"
    TCP_PORT: int
    
    class Config:
        # This tells Pydantic to load the variables from a file named .env
        env_file = ".env"
        # This allows reading from the environment even if the .env file is not found
        env_file_encoding = 'utf-8'

# Create a single, reusable instance of the settings
settings = Settings()
