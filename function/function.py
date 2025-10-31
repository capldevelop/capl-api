from fastapi import HTTPException, Header, UploadFile
import jwt
from jwt import PyJWTError, ExpiredSignatureError, InvalidTokenError
from datetime import datetime, timedelta
import shutil
import os
import pytz
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
JWT_ACCESS_EXPIRATION_DAYS = int(os.getenv("JWT_ACCESS_EXPIRATION_DAYS", 1))
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", 7))

# Access Token 생성
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_ACCESS_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Refresh Token 생성
def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

#개발용 토큰(만료기한 X) 생성 함수
def create_dev_access_token(data: dict):
    to_encode = data.copy()
    # `exp` 클레임을 추가하지 않음
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# 토큰 추출 함수
def get_token_from_header(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    return authorization[len("Bearer "):]  

# 토큰 검증 및 갱신 함수
def verify_token(token: str):
    try:
        # 토큰 디코딩
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # 기존 payload 데이터 유지
        data = payload.copy()
        data.pop("exp", None)  # 기존 만료 시간 제거

        # 새로운 만료 시간 (일 단위)
        new_expire = datetime.utcnow() + timedelta(days=JWT_ACCESS_EXPIRATION_DAYS)
        data.update({"exp": new_expire})

        # 새로운 토큰 생성
        new_token = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

        return {"payload": payload, "new_token": new_token}

    except ExpiredSignatureError:
        # 토큰이 만료된 경우
        raise HTTPException(status_code=401, detail="Token has expired")
    except InvalidTokenError: 
        # 토큰이 유효하지 않은 경우 
        raise HTTPException(status_code=401, detail="Invalid token")
    except PyJWTError:
        # 토큰이 유효하지 않은 경우
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        # 기타 예외 처리
        raise HTTPException(status_code=500, detail="Token verification failed")

# 글자수 축약 함수
def truncate_string(string, max_length=10):
    return string[:max_length] + "..." if len(string) > max_length else string

# 파일 저장 함수 (수정필요)
def save_file(upload_dir, file):
    file_path = None
    os.makedirs(upload_dir, exist_ok=True)  # 디렉토리가 없으면 생성
    file_path = f"{upload_dir}/{file.filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return file_path

# 현재 날짜(KST) 호출 함수
def current_date():
    kst = pytz.timezone('Asia/Seoul')
    current_time = datetime.now(kst)
    current_time_naive = current_time.replace(tzinfo=None)
    return current_time_naive