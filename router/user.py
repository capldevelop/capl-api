# app/routers/user.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core import schemas
from function import user_function
from core.dependencies import get_current_user_id

router = APIRouter(
    prefix="/user", 
    tags=["User"]
)



@router.post("/verify", summary="회원 가입 여부 확인", response_model=schemas.RootResponse)
def validate_user(
    request: schemas.VerifyUserRequest,
    db: Session = Depends(get_db)
):
    user_function.verify_user(db, request.user_name, request.user_phone, request.user_ci)
    return schemas.RootResponse.ok(None)

@router.get("/me", summary="내 정보 조회", response_model=schemas.RootResponse[schemas.UserResponse])
def get_my_info(
    current_user_id: int = Depends(get_current_user_id), # 의존성 주입
    db: Session = Depends(get_db)
):
    user = user_function.get_my_info(db, current_user_id)
    return schemas.RootResponse.ok(schemas.UserResponse.from_orm(user))

@router.delete("/delete", summary="회원 탈퇴", response_model=schemas.RootResponse)
def delete_user(
    current_user_id: int = Depends(get_current_user_id), # 의존성 주입
    db: Session = Depends(get_db)
):
    user_function.delete_user(db, current_user_id)
    return schemas.RootResponse.ok(None)
