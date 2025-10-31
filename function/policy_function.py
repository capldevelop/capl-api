# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session
from typing import List
from fastapi import HTTPException, status

from core import models, schemas
# from . import parking_lot_function # 최상위 Import 제거

def get_policy_list(db: Session) -> List[models.Policy]:
    """모든 정책 목록을 조회합니다."""
    return db.query(models.Policy).order_by(models.Policy.policy_id).all()

def get_policy_setting_list(db: Session, parking_lot_id: int) -> List[schemas.PolicyActive]:
    """특정 주차장의 정책 설정 목록을 조회합니다."""
    from . import parking_lot_function # 함수 내에서 Import
    parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)

    settings = db.query(models.PolicySetting).filter(
        models.PolicySetting.parking_lot_id == parking_lot_id
    ).all()
     
    return [
        schemas.PolicyActive(
            policyId=setting.policy_id,
            activeYn=setting.active_yn
        ) for setting in settings
    ]

def is_policy_active(db: Session, policy_id: int, parking_lot_id: int) -> bool:
    """특정 주차장의 특정 정책이 활성화되어 있는지 확인합니다."""
    from . import parking_lot_function # 함수 내에서 Import
    parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)

    setting = db.query(models.PolicySetting).filter(
        models.PolicySetting.parking_lot_id == parking_lot_id,
        models.PolicySetting.policy_id == policy_id
    ).first()

    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_POLICY")
         
    return setting.active_yn == models.YnType.Y

def set_policy_settings(db: Session, user_id: int, parking_lot_id: int, policy_active_list: List[schemas.PolicyActive]):
    """주차장의 정책들을 설정(추가 또는 수정)합니다."""
    from . import parking_lot_function # 함수 내에서 Import
    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)

    for policy_active in policy_active_list:
        # 정책 존재 여부 검증
        policy = db.query(models.Policy).filter(models.Policy.policy_id == policy_active.policy_id).first()
        if not policy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_POLICY")

        # 기존 설정 조회
        setting = db.query(models.PolicySetting).filter(
            models.PolicySetting.parking_lot_id == parking_lot_id,
            models.PolicySetting.policy_id == policy_active.policy_id
        ).first()
         
        if setting: # 기존 설정이 있으면 업데이트
            setting.active_yn = policy_active.active_yn
            setting.update_by = user_id
        else: # 없으면 새로 생성
            new_setting = models.PolicySetting(
                parking_lot_id=parking_lot_id,
                policy_id=policy_active.policy_id,
                active_yn=policy_active.active_yn,
                create_by=user_id,
                update_by=user_id
            )
            db.add(new_setting)
    db.commit()

def remove_policy_settings(db: Session, parking_lot_id: int):
    """특정 주차장의 모든 정책 설정을 삭제합니다."""
    db.query(models.PolicySetting).filter(
        models.PolicySetting.parking_lot_id == parking_lot_id
    ).delete()
    # db.commit()
