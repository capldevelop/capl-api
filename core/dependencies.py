# app/core/dependencies.py
from fastapi import Request, Depends, HTTPException, status, Header, Query
from typing import Optional
from sqlalchemy.orm import Session

# login_function에서 토큰 검증 함수 import
from function import login_function, user_function
from core.database import get_db
from core import models

def get_token_from_header(authorization: Optional[str] = Header(None)) -> str:
    """
    Authorization 헤더에서 'Bearer ' 부분을 제거하고 토큰만 추출합니다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format"
        )
    return authorization.split(" ")[1]

def get_current_user_id(token: str = Depends(get_token_from_header)) -> int:
    """
    토큰을 검증하고 payload에서 user_id를 추출하여 반환하는 의존성.
    """
    user_id = login_function.validate_token(token)
    return int(user_id)

# (선택) 사용자 객체 자체를 반환하고 싶을 경우
def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
) -> models.User:
    """
    인증된 사용자의 ORM 모델 객체를 반환하는 의존성.
    """
    user = user_function.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

# --- WebSocket 인증을 위한 헬퍼 함수 ---
def get_user_id_from_token_ws(token: Optional[str] = Query(None)) -> int:
    """
    WebSocket 연결 시 Query 파라미터로 받은 토큰을 검증하고 user_id를 반환합니다.
    FastAPI의 Depends 시스템을 직접 사용할 수 없는 웹소켓을 위한 함수입니다.
    """
    if not token:
        # 웹소켓에서는 HTTPException 대신 특정 코드로 연결을 닫는 것이 일반적입니다.
        # 이 함수를 호출하는 쪽에서 예외 처리 대신 None을 반환받아 처리하도록 합니다.
        return None
    
    try:
        user_id = login_function.validate_token(token)
        return int(user_id)
    except HTTPException:
        # validate_token에서 발생하는 HTTPException을 잡아 None을 반환합니다.
        return None

