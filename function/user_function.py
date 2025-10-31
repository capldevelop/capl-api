# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status

from core import models, schemas
# from . import parking_lot_function, car_function, notification_function, login_function, parking_function # 최상위 Import 제거

def get_user_by_id(db: Session, user_id: int) -> models.User:
    """ID로 사용자를 조회하고 없으면 예외를 발생시킵니다."""
    user = db.query(models.User).filter(
        models.User.user_id == user_id,
        models.User.del_yn == models.YnType.N
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_USER")
    return user

def get_user_info_for_parking(db: Session, user_id: int, parking_lot_id: int) -> Dict[str, Any]:
    """
    주차 목록 조회 시 필요한 사용자 정보를 조회합니다. (닉네임, 연락처 공개여부, 연락처)
    """
    # 1. 주차장에 소속된 유저 정보를 먼저 찾습니다. (닉네임, 연락처 공개 여부 등)
    parking_lot_user = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id
    ).first()

    # 주차장에 소속된 유저가 아닌 경우 (예: 탈퇴, 방문객) 빈 정보를 반환합니다.
    if not parking_lot_user:
        return {
            "nickname": "정보 없음",
            "phone_secret_yn": models.YnType.Y,
            "phone": None
        }

    user_info = {
        "nickname": parking_lot_user.user_nickname,
        "phone_secret_yn": parking_lot_user.phone_secret_yn,
        "phone": None
    }

    # 2. 연락처 공개(YnType.N)인 경우에만 users 테이블에서 실제 연락처를 조회합니다.
    if parking_lot_user.phone_secret_yn == models.YnType.N:
        user = get_user_by_id(db, user_id)
        user_info["phone"] = user.user_phone
         
    return user_info


def get_user_by_ci(db: Session, user_ci: str) -> Optional[models.User]:
    """CI로 사용자를 조회합니다. 없으면 None을 반환합니다."""
    return db.query(models.User).filter(
        models.User.user_ci == user_ci,
        models.User.del_yn == models.YnType.N
    ).first()

def get_temp_user(db: Session, user_name: str, user_phone: str) -> models.PhoneAuthTempUser:
    """이름과 전화번호로 임시 사용자를 조회합니다."""
    temp_user = db.query(models.PhoneAuthTempUser).filter(
        models.PhoneAuthTempUser.temp_user_name == user_name,
        models.PhoneAuthTempUser.temp_user_phone == user_phone
    ).first()
    if not temp_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHENTICATED_PHONE_USER")
    return temp_user

def remove_temp_user(db: Session, temp_user_id: int):
    """임시 사용자 정보를 삭제합니다."""
    db.query(models.PhoneAuthTempUser).filter(models.PhoneAuthTempUser.temp_user_id == temp_user_id).delete()
    db.commit()
     
def authenticate_phone_user(db: Session, user_name: str, user_phone: str, user_ci: str) -> models.User:
    """
    PASS 인증으로 받은 CI를 기준으로 사용자를 조회하고,
    이름과 전화번호가 일치하는지 검증합니다.
    """
    # 1. CI 값으로 사용자를 조회합니다.
    user = get_user_by_ci(db, user_ci)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    # 2. 조회된 사용자의 이름과 전화번호가 요청과 일치하는지 확인합니다. (보안 강화)
    if user.user_name != user_name or user.user_phone != user_phone:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="USER_INFO_MISMATCH")
         
    return user
     
     
def get_user_by_social_info(db: Session, social_id: str, social_type: models.SocialType) -> Optional[models.User]:
    """
    user_socials 테이블에서 소셜 정보와 일치하는 사용자를 찾아 반환합니다.
    """
    # 1. user_socials 테이블에서 social_id와 social_type으로 레코드를 찾습니다.
    social_account = db.query(models.UserSocial).filter(
        models.UserSocial.user_social_id == social_id,
        models.UserSocial.social_type == social_type
    ).first()

    # 2. 레코드를 찾았다면, 연결된 user 정보를 반환합니다.
    if social_account:
        return social_account.user  # SQLAlchemy의 relationship 기능을 통해 바로 user 객체에 접근

    # 3. 찾지 못했다면 None을 반환합니다.
    return None

def get_my_info(db: Session, user_id: int) -> models.User:
    """내 정보를 조회합니다."""
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")
    return user

def create_user(db: Session, request: schemas.SignUpRequest, temp_user_ci: str) -> models.User:
    """
    회원가입 요청을 바탕으로 새로운 사용자를 생성합니다.
    PASS 인증을 통해 얻은 CI 값을 필수로 사용합니다.
    """
    # CI 값으로 이미 가입된 사용자인지 최종 확인
    if get_user_by_ci(db, temp_user_ci):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="USER_ALREADY_EXISTS")

    # 새로운 사용자 생성
    new_user = models.User(
        user_name=request.user_name,
        user_phone=request.user_phone,
        user_ci=temp_user_ci
    )
    db.add(new_user)
    db.flush() # new_user.user_id 값을 할당받기 위해 flush

    # 소셜 정보가 함께 넘어온 경우, UserSocial 테이블에도 저장
    if request.user_social_info:
        social_info = request.user_social_info
        new_user_social = models.UserSocial(
            user_social_id=social_info.user_social_id,
            social_type=social_info.social_type,
            user_id=new_user.user_id, # 방금 생성된 사용자의 ID
            user_social_email=social_info.user_social_email,
            refresh_token=social_info.refresh_token
        )
        db.add(new_user_social)

    db.commit()
    db.refresh(new_user)
    return new_user

def delete_user(db: Session, user_id: int):
    """회원 탈퇴를 처리합니다. (기존 로직 유지)"""
    from . import parking_lot_function, car_function, notification_function, login_function, parking_function # 함수 내에서 Import
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USER_NOT_FOUND")

    # ... (관련 데이터 삭제 로직) ...
    parking_lot_function.remove_all_user_associations(db, user_id)
    car_function.remove_all_user_cars(db, user_id)
    notification_function.remove_all_user_settings(db, user_id)
    login_function.remove_all_login_info(db, user_id)
    parking_function.remove_all_user_parking_history(db, user_id)
     
    db.query(models.UserSocial).filter(models.UserSocial.user_id == user_id).delete(synchronize_session=False)
     
    user.del_yn = models.YnType.Y
    db.commit()


def verify_user(db: Session, user_name: str, user_phone: str, user_ci: str):
    """입력된 본인인증 정보가 DB와 일치하는지 검증합니다."""
    user = get_user_by_ci(db, user_ci)

    # 1. CI 없음 (신규 사용자) -> INVALID_USER (404/400)
    if not user:
        # _get_user_by_ci_internal 이 None을 반환하므로 여기서 예외 발생
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_USER")

    # 2. CI 있음, 이름/번호 모두 불일치 -> INVALID_USER (400)
    if user.user_name != user_name and user.user_phone != user_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_USER")

    # 3. CI 있음, 이름 일치, 번호 불일치 -> SIGNED_UP_USER (409)
    if user.user_name == user_name and user.user_phone != user_phone:
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SIGNED_UP_USER")

    # 4. CI 있음, 정보 일치 (기존 사용자) -> 아무 예외도 발생시키지 않고 통과 (200 OK)

