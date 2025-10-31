# app/function/parking_lot_function.py
import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from typing import List, Optional, Set
from datetime import time, datetime
from collections import defaultdict
import math

from core import models, schemas
from core.config import settings
# 순환 참조를 유발하는 function 모듈들을 최상단에서 제거합니다.
# from . import policy_function, chat_function, notification_function, parking_function, widget_function, user_function, car_function, notice_function, vote_function

# =================================================================
# 비동기 외부 API 호출 함수
# =================================================================

async def get_geocodes_from_kakao(address: str) -> schemas.Geocodes:
    """카카오맵 API를 호출하여 주소의 좌표를 가져옵니다."""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {settings.KAKAO_MAP_KEY}"}
    params = {"query": address}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if not data.get("documents"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ADDRESS_NOT_FOUND")
            doc = data["documents"][0]
            return schemas.Geocodes(latitude=float(doc['y']), longitude=float(doc['x']))
        except httpx.RequestError:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="KAKAO_API_FAILED")

# =================================================================
# 내부 유틸리티 함수
# =================================================================

def _get_parking_lot_by_id(db: Session, parking_lot_id: int) -> models.ParkingLot:
    """ID로 주차장 정보를 조회하고 없으면 예외를 발생시킵니다."""
    parking_lot = db.query(models.ParkingLot).filter(
        models.ParkingLot.parking_lot_id == parking_lot_id,
        models.ParkingLot.del_yn == models.YnType.N
    ).first()
    if not parking_lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVALID_PARKING_LOT")
    return parking_lot

def _get_parking_lot_user(db: Session, user_id: int, parking_lot_id: int) -> models.ParkingLotUser:
    """주차장 사용자 정보를 조회하고 없으면 예외를 발생시킵니다."""
    user_in_lot = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).first()
    if not user_in_lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_USER_IN_THE_PARKING_LOT")
    return user_in_lot

def _check_shared_access(db: Session, user_id: int, target_parking_lot_id: int) -> bool:
    """사용자가 그룹 공유를 통해 특정 주차장에 접근 권한이 있는지 확인합니다."""
    # 1. 사용자가 직접 속한 모든 주차장 ID 목록을 가져옵니다.
    user_home_lots_query = db.query(models.ParkingLotUser.parking_lot_id).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.del_yn == models.YnType.N,
        models.ParkingLotUser.accept_yn == models.YnType.Y
    )
    user_home_lot_ids = {row[0] for row in user_home_lots_query.all()}

    if not user_home_lot_ids:
        return False

    # 2. 해당 주차장들이 속한 모든 그룹 ID 목록을 가져옵니다.
    home_lot_groups_query = db.query(models.ParkingLotGroupMember.group_id).filter(
        models.ParkingLotGroupMember.parking_lot_id.in_(user_home_lot_ids),
        models.ParkingLotGroupMember.accept_yn == models.YnType.Y
    ).distinct()
    group_ids = {row[0] for row in home_lot_groups_query.all()}

    if not group_ids:
        return False

    # 3. 접근하려는 주차장(`target_parking_lot_id`)이 위 그룹들 중 하나에 속해있는지 확인합니다.
    is_shared_count = db.query(models.ParkingLotGroupMember).filter(
        models.ParkingLotGroupMember.group_id.in_(group_ids),
        models.ParkingLotGroupMember.parking_lot_id == target_parking_lot_id,
        models.ParkingLotGroupMember.accept_yn == models.YnType.Y
    ).count()

    return is_shared_count > 0

# =================================================================
# 거리 계산 유틸리티 함수
# =================================================================

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 위도/경도 지점 간의 거리를 미터(m) 단위로 계산합니다."""
    R = 6371e3  # 지구 반지름 (미터)
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) * math.sin(delta_phi / 2) + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2) * math.sin(delta_lambda / 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance

# =================================================================
# 권한 검증 함수
# =================================================================

def verify_admin_role(db: Session, user_id: int, parking_lot_id: int):
    """사용자가 해당 주차장의 관리자인지 검증합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    if user_in_lot.user_role != models.UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PERMISSION_DENIED")

# def verify_user_role(db: Session, user_id: int, parking_lot_id: int):
#     """사용자가 해당 주차장의 멤버인지 검증합니다."""
#     _get_parking_lot_user(db, user_id, parking_lot_id)

def verify_user_role(db: Session, user_id: int, parking_lot_id: int):
    """
    사용자가 해당 주차장의 멤버이거나, 그룹으로 공유된 주차장인지 검증합니다.
    (Verifies if the user is a member of the parking lot or has access via a shared group.)
    """
    # 1. 직접 멤버인지 확인
    is_direct_member = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.del_yn == models.YnType.N,
        models.ParkingLotUser.accept_yn == models.YnType.Y
    ).first()

    if is_direct_member:
        return  # 직접 멤버이므로 권한 통과

    # 2. 직접 멤버가 아닐 경우, 그룹 공유를 통해 접근 가능한지 확인
    if _check_shared_access(db, user_id, parking_lot_id):
        return  # 그룹 공유를 통해 권한 통과

    # 3. 두 경우 모두 해당하지 않으면 권한 거부
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="PERMISSION_DENIED")


# =================================================================
# 주차장 (ParkingLot) 관련 함수
# =================================================================

def check_parking_lot(db: Session, address: str) -> Optional[schemas.ParkingLotResponse]:
    """주소로 등록된 주차장이 있는지 확인합니다."""
    parking_lot = db.query(models.ParkingLot).filter(
        models.ParkingLot.parking_lot_address == address,
        models.ParkingLot.del_yn == models.YnType.N
    ).first()
    if parking_lot:
        return schemas.ParkingLotResponse.model_validate(parking_lot)
    return None

async def add_parking_lot(db: Session, user_id: int, request: schemas.AddParkingLotRequest) -> int:
    """새로운 주차장을 등록합니다."""
    from . import policy_function, chat_function, notification_function, car_function # 순환 참조 방지를 위한 지연 Import

    existing_parking_lot = check_parking_lot(db, request.parking_lot_address)
    if existing_parking_lot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PARKING_LOT_ALREADY_EXISTS")

    try:
        geocodes = await get_geocodes_from_kakao(request.parking_lot_address)
        
        # parking_lot_public 값을 확인하고 없으면 'N'으로 설정
        public_yn = request.parking_lot_public if request.parking_lot_public is not None else models.YnType.N

        new_parking_lot = models.ParkingLot(
            parking_lot_name=request.parking_lot_name,
            parking_lot_address=request.parking_lot_address,
            parking_lot_address_detail=request.parking_lot_address_detail,
            parking_lot_public=public_yn,
            latitude=geocodes.latitude, 
            longitude=geocodes.longitude,
            create_by=user_id, 
            update_by=user_id
        )
        db.add(new_parking_lot)
        db.flush()  # ID를 가져오기 위해 flush

        parking_lot_id = new_parking_lot.parking_lot_id
        user_info = request.parking_lot_user_info
        
        new_user_in_lot = models.ParkingLotUser(
            user_id=user_id, 
            parking_lot_id=parking_lot_id, 
            user_nickname=user_info.user_nickname,
            user_role=models.UserRole.ADMIN, 
            accept_yn=models.YnType.Y, 
            phone_secret_yn=user_info.phone_secret_yn,
            pull_out_start_time=user_info.pull_out_start_time, 
            pull_out_end_time=user_info.pull_out_end_time,
            pull_out_week=user_info.pull_out_week, 
            holiday_exclude_yn=user_info.holiday_exclude_yn,
            pull_out_time_yn=schemas.YnType.Y if user_info.pull_out_start_time and user_info.pull_out_end_time else schemas.YnType.N,
            create_by=user_id, 
            update_by=user_id
        )
        db.add(new_user_in_lot)
        
        policy_function.set_policy_settings(db, user_id, parking_lot_id, request.policy_active_info_list)
        if user_info.car_id_list:
            car_function.add_cars_to_parking_lot(db, user_id, parking_lot_id, user_info.car_id_list)
        chat_function.append_chat(db, user_id, parking_lot_id)
        notification_function.init_notification_settings(db, user_id, parking_lot_id)
        
        db.commit() # 모든 작업이 성공했을 때만 최종 커밋
        return parking_lot_id
    
    except Exception as e:
        db.rollback() # 에러 발생 시 모든 변경사항을 롤백
        if isinstance(e, HTTPException):
            raise e
        # 예상치 못한 다른 DB 오류의 경우 500 에러로 처리
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

async def edit_parking_lot_info(db: Session, user_id: int, parking_lot_id: int, request: schemas.EditParkingLotRequest):
    """주차장 기본 정보를 수정합니다 (이름, 주소)."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    
    if parking_lot.parking_lot_address != request.parking_lot_address:
        geocodes = await get_geocodes_from_kakao(request.parking_lot_address)
        parking_lot.latitude = geocodes.latitude
        parking_lot.longitude = geocodes.longitude
        parking_lot.parking_lot_address = request.parking_lot_address

    parking_lot.parking_lot_name = request.parking_lot_name
    parking_lot.parking_lot_address_detail = request.parking_lot_address_detail
    parking_lot.update_by = user_id
    db.commit()

def edit_parking_lot_name(db: Session, user_id: int, parking_lot_id: int, name: str):
    """주차장 이름을 수정합니다."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    parking_lot.parking_lot_name = name
    parking_lot.update_by = user_id
    db.commit()

async def edit_parking_lot_address(db: Session, user_id: int, parking_lot_id: int, request: schemas.EditParkingLotAddressRequest):
    """주차장 주소를 수정합니다."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    if parking_lot.parking_lot_address != request.parking_lot_address:
        geocodes = await get_geocodes_from_kakao(request.parking_lot_address)
        parking_lot.latitude = geocodes.latitude
        parking_lot.longitude = geocodes.longitude
        parking_lot.parking_lot_address = request.parking_lot_address
    
    parking_lot.parking_lot_address_detail = request.parking_lot_address_detail
    parking_lot.update_by = user_id
    db.commit()

def delete_parking_lot(db: Session, user_id: int, parking_lot_id: int):
    """주차장과 관련된 모든 하위 데이터를 삭제(소프트 삭제)합니다."""
    from . import car_function, widget_function, policy_function, notice_function, chat_function, vote_function, parking_function # 지연 Import

    car_function.remove_all_cars_from_parking_lot(db, user_id, parking_lot_id)
    remove_all_users_from_parking_lot(db, user_id, parking_lot_id)
    widget_function.remove_all_widgets_in_lot(db, user_id, parking_lot_id)
    policy_function.remove_policy_settings(db, parking_lot_id)
    notice_function.remove_all_notices_in_lot(db, user_id, parking_lot_id)
    chat_function.remove_chat(db, user_id, parking_lot_id)
    vote_function.remove_all_votes_in_lot(db, user_id, parking_lot_id)
    parking_function.remove_all_parking_in_lot(db, user_id, parking_lot_id)
    
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    parking_lot.del_yn = models.YnType.Y
    parking_lot.update_by = user_id
    db.commit()

def find_parking_lot_list_by(db: Session, user_id: int, keyword: str) -> List[schemas.ParkingLotResponse]:
    """키워드로 주차장 전체 목록을 검색합니다."""
    parking_lots = db.query(models.ParkingLot).filter(
        (models.ParkingLot.parking_lot_name.contains(keyword)) |
        (models.ParkingLot.parking_lot_address.contains(keyword)),
        models.ParkingLot.del_yn == models.YnType.N
    ).all()
    return [schemas.ParkingLotResponse.model_validate(lot) for lot in parking_lots]

def find_parking_lot_info(db: Session, parking_lot_id: int) -> schemas.ParkingLotDetailResponse:
    """주차장 상세 정보를 조회합니다."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    
    user_count = db.query(func.count(models.ParkingLotUser.user_id)).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.Y,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).scalar()

    join_request_user_count = db.query(func.count(models.ParkingLotUser.user_id)).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.N,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).scalar()

    return schemas.ParkingLotDetailResponse(
        parking_lot_id=parking_lot.parking_lot_id,
        parking_lot_name=parking_lot.parking_lot_name,
        parking_lot_address=parking_lot.parking_lot_address,
        parking_lot_address_detail=parking_lot.parking_lot_address_detail,
        user_count=user_count,
        join_request_user_count=join_request_user_count
    )

def find_parking_lot_home_info(db: Session, parking_lot_id: int) -> schemas.ParkingLotHomeResponse:
    """주차장 홈 정보를 조회합니다."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    chat = db.query(models.Chat).filter(models.Chat.parking_lot_id == parking_lot_id).first()
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CHAT_NOT_FOUND")
        
    return schemas.ParkingLotHomeResponse(
        parking_lot_id=parking_lot.parking_lot_id,
        parking_lot_name=parking_lot.parking_lot_name,
        chat_id=chat.chat_id,
        latitude=parking_lot.latitude,
        longitude=parking_lot.longitude
    )
    
def edit_parking_lot_public(db: Session, user_id: int, parking_lot_id: int, public_yn: models.YnType):
    """주차장 공개 여부를 수정합니다."""
    parking_lot = _get_parking_lot_by_id(db, parking_lot_id)
    parking_lot.parking_lot_public = public_yn
    parking_lot.update_by = user_id
    db.commit()

# =================================================================
# 주차장 사용자 (ParkingLotUser) 관련 함수
# =================================================================

def request_parking_lot_join(db: Session, user_id: int, parking_lot_id: int, request: schemas.JoinParkingLotRequest):
    """주차장 가입을 요청합니다."""
    from . import car_function # 지연 Import

    # to-be : 거리 제한 추가 예정
    _get_parking_lot_by_id(db, parking_lot_id) # 주차장 존재 여부 확인
    
    existing_request = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id
    ).first()

    if existing_request:
        if existing_request.del_yn == models.YnType.N:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_JOINED_OR_REQUESTED")
        else: # 재가입 요청
            existing_request.del_yn = models.YnType.N
            existing_request.accept_yn = models.YnType.N
            existing_request.user_nickname = request.user_nickname
            # ... 다른 필드 업데이트
    else:
        new_request = models.ParkingLotUser(
            user_id=user_id,
            parking_lot_id=parking_lot_id,
            user_nickname=request.user_nickname,
            user_role=models.UserRole.USER,
            accept_yn=models.YnType.N,
            phone_secret_yn=request.phone_secret_yn,
            pull_out_start_time=request.pull_out_start_time,
            pull_out_end_time=request.pull_out_end_time,
            pull_out_week=request.pull_out_week,
            holiday_exclude_yn=request.holiday_exclude_yn,
            pull_out_time_yn=schemas.YnType.Y if request.pull_out_start_time and request.pull_out_end_time else schemas.YnType.N,
            create_by=user_id,
            update_by=user_id
        )
        db.add(new_request)

    car_function.add_cars_to_parking_lot(db, user_id, parking_lot_id, request.car_id_list)
    db.commit()

def request_accept(db: Session, user_id: int, parking_lot_id: int, user_id_list: List[int]):
    """주차장 가입 요청을 승인합니다."""
    from . import chat_function # 지연 Import

    users_to_accept = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_id.in_(user_id_list),
        models.ParkingLotUser.accept_yn == models.YnType.N,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()
    
    for user in users_to_accept:
        user.accept_yn = models.YnType.Y
        user.update_by = user_id
        chat_function.append_chat_user(db, user.user_id, parking_lot_id) # 승인 시 채팅방 자동 참여
    db.commit()

def request_reject(db: Session, user_id: int, parking_lot_id: int, user_id_list: List[int]):
    """주차장 가입 요청을 거절(삭제)합니다."""
    users_to_reject = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_id.in_(user_id_list),
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()

    for user in users_to_reject:
        user.del_yn = models.YnType.Y
        user.update_by = user_id
    db.commit()

def get_join_parking_lot_list(db: Session, user_id: int) -> List[schemas.JoinParkingLotResponse]:
    """사용자가 가입/요청한 주차장 목록을 조회합니다."""
    results = db.query(models.ParkingLot, models.ParkingLotUser).join(
        models.ParkingLotUser, models.ParkingLot.parking_lot_id == models.ParkingLotUser.parking_lot_id
    ).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLot.del_yn == models.YnType.N,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()
    
    response_list = []
    for lot, user_info in results:
        response_item = schemas.JoinParkingLotResponse(
            parking_lot_id=lot.parking_lot_id,
            parking_lot_name=lot.parking_lot_name,
            parking_lot_address=lot.parking_lot_address,
            parking_lot_address_detail=lot.parking_lot_address_detail,
            latitude=lot.latitude,
            longitude=lot.longitude,
            user_role=user_info.user_role,
            accept_yn=user_info.accept_yn,
            chat_join_yn=user_info.chat_join_yn
        )
        response_list.append(response_item)
    return response_list

def find_join_parking_lot(db: Session, user_id: int, parking_lot_id: int) -> schemas.JoinParkingLotResponse:
    """사용자가 가입한 특정 주차장의 상세 정보를 조회합니다."""
    result = db.query(models.ParkingLot, models.ParkingLotUser).join(
        models.ParkingLotUser, models.ParkingLot.parking_lot_id == models.ParkingLotUser.parking_lot_id
    ).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLot.del_yn == models.YnType.N,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).first()

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_USER_IN_THE_PARKING_LOT")

    lot, user_info = result
    return schemas.JoinParkingLotResponse(
        parking_lot_id=lot.parking_lot_id,
        parking_lot_name=lot.parking_lot_name,
        parking_lot_address=lot.parking_lot_address,
        parking_lot_address_detail=lot.parking_lot_address_detail,
        latitude=lot.latitude,
        longitude=lot.longitude,
        user_role=user_info.user_role,
        accept_yn=user_info.accept_yn,
        chat_join_yn=user_info.chat_join_yn
    )

def find_parking_lot_user_info(db: Session, parking_lot_id: int, user_id: int) -> schemas.ParkingLotUserDetailResponse:
    """주차장 내 자신의 참여 정보를 조회합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    car_count = db.query(func.count(models.ParkingLotCar.car_id)).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.create_by == user_id, # create_by가 사용자 ID와 같아야 함
        models.ParkingLotCar.del_yn == models.YnType.N
    ).scalar()

    return schemas.ParkingLotUserDetailResponse(
        user_nickname=user_in_lot.user_nickname,
        car_count=car_count,
        phone_secret_yn=user_in_lot.phone_secret_yn,
        pull_out_time_yn=user_in_lot.pull_out_time_yn,
        pull_out_start_time=user_in_lot.pull_out_start_time,
        pull_out_end_time=user_in_lot.pull_out_end_time,
        pull_out_week=user_in_lot.pull_out_week,
        holiday_exclude_yn=user_in_lot.holiday_exclude_yn
    )

def find_request_join_user_list(db: Session, parking_lot_id: int) -> List[schemas.JoinUserDetailResponse]:
    """주차장 가입 요청자 목록을 조회합니다."""
    from . import car_function # 지연 Import

    requesting_users = db.query(models.ParkingLotUser).options(joinedload(models.ParkingLotUser.user)).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.N,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()
    
    response_list = []
    for user_in_lot in requesting_users:
        cars = car_function.get_user_cars_in_parking_lot(db, user_in_lot.user_id, parking_lot_id)
        response_list.append(schemas.JoinUserDetailResponse(
            user_id=user_in_lot.user_id,
            user_role=user_in_lot.user_role,
            user_nickname=user_in_lot.user_nickname,
            phone_secret_yn=user_in_lot.phone_secret_yn,
            user_phone=user_in_lot.user.user_phone,
            pull_out_start_time=user_in_lot.pull_out_start_time,
            pull_out_end_time=user_in_lot.pull_out_end_time,
            pull_out_week=user_in_lot.pull_out_week,
            car_list=[schemas.JoinUserDetailResponse.CarInfo.model_validate(car) for car in cars]
        ))
    return response_list

def find_join_user_list(db: Session, parking_lot_id: int) -> schemas.JoinUserListResponse:
    """주차장 참여자 목록을 조회합니다."""
    from . import car_function # 지연 Import

    joined_users = db.query(models.ParkingLotUser).options(joinedload(models.ParkingLotUser.user)).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.Y,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()

    admin_list = []
    user_list = []
    for user_in_lot in joined_users:
        cars = car_function.get_user_cars_in_parking_lot(db, user_in_lot.user_id, parking_lot_id)
        user_detail = schemas.JoinUserDetailResponse(
            user_id=user_in_lot.user_id,
            user_role=user_in_lot.user_role,
            user_nickname=user_in_lot.user_nickname,
            phone_secret_yn=user_in_lot.phone_secret_yn,
            user_phone=user_in_lot.user.user_phone if user_in_lot.phone_secret_yn == models.YnType.N else None,
            pull_out_start_time=user_in_lot.pull_out_start_time,
            pull_out_end_time=user_in_lot.pull_out_end_time,
            pull_out_week=user_in_lot.pull_out_week,
            car_list=[schemas.JoinUserDetailResponse.CarInfo.model_validate(car) for car in cars]
        )
        if user_in_lot.user_role == models.UserRole.ADMIN:
            admin_list.append(user_detail)
        else:
            user_list.append(user_detail)
            
    return schemas.JoinUserListResponse(admin_user_list=admin_list, basic_user_list=user_list)

def edit_user_role(db: Session, admin_user_id: int, parking_lot_id: int, target_user_id: int, role: models.UserRole):
    """주차장 참여자의 권한을 변경합니다."""
    user_to_edit = _get_parking_lot_user(db, target_user_id, parking_lot_id)
    user_to_edit.user_role = role
    db.commit()

def edit_user_info(db: Session, user_id: int, parking_lot_id: int, request: schemas.EditUserInfoRequest):
    """주차장 내 자신의 정보를 수정합니다."""
    from . import car_function # 지연 Import

    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    user_in_lot.user_nickname = request.user_nickname
    user_in_lot.phone_secret_yn = request.phone_secret_yn
    user_in_lot.pull_out_time_yn = request.pull_out_time_yn
    user_in_lot.pull_out_start_time = request.pull_out_start_time
    user_in_lot.pull_out_end_time = request.pull_out_end_time
    user_in_lot.pull_out_week = request.pull_out_week
    user_in_lot.holiday_exclude_yn = request.holiday_exclude_yn
    
    car_function.update_user_cars_in_parking_lot(db, user_id, parking_lot_id, request.car_id_list)
    db.commit()

def edit_user_pull_out_time(db: Session, user_id: int, parking_lot_id: int, request: schemas.EditUserPullOutTimeRequest):
    """자신의 고정 출차 시간을 수정합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    user_in_lot.pull_out_time_yn = request.pull_out_time_yn
    user_in_lot.pull_out_start_time = request.pull_out_start_time
    user_in_lot.pull_out_end_time = request.pull_out_end_time
    user_in_lot.pull_out_week = request.pull_out_week
    user_in_lot.holiday_exclude_yn = request.holiday_exclude_yn
    db.commit()
    
def edit_user_car(db: Session, user_id: int, parking_lot_id: int, car_id_list: Optional[List[int]]):
    """자신의 차량 정보를 수정합니다."""
    from . import car_function # 지연 Import
    car_function.update_user_cars_in_parking_lot(db, user_id, parking_lot_id, car_id_list)
    db.commit()

def edit_user_nickname(db: Session, user_id: int, parking_lot_id: int, nickname: str):
    """자신의 닉네임을 수정합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    user_in_lot.user_nickname = nickname
    db.commit()

def edit_user_phone_secret(db: Session, user_id: int, parking_lot_id: int, phone_secret_yn: models.YnType):
    """자신의 휴대폰 번호 공개 여부를 수정합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    user_in_lot.phone_secret_yn = phone_secret_yn
    db.commit()

def edit_user_pull_out_time_yn(db: Session, user_id: int, parking_lot_id: int, pull_out_time_yn: models.YnType):
    """고정 출차 시간 적용 여부를 수정합니다."""
    user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
    user_in_lot.pull_out_time_yn = pull_out_time_yn
    db.commit()

def remove_user(db: Session, request_user_id: int, parking_lot_id: int, target_user_id: int):
    """주차장에서 사용자를 내보내거나 스스로 나갑니다."""
    from . import car_function, chat_function # 지연 Import

    # 1. 삭제할 사용자를 먼저 조회
    user_to_remove = _get_parking_lot_user(db, target_user_id, parking_lot_id)
    
    # 2. 관련된 하위 데이터들을 정리
    car_function.remove_user_cars_from_parking_lot(db, request_user_id, parking_lot_id, target_user_id)
    chat_function.remove_chat_user(db, target_user_id, parking_lot_id)
    
    # 3. 모든 하위 데이터 정리가 끝난 후, 사용자 정보를 논리적으로 삭제
    user_to_remove.del_yn = models.YnType.Y
    user_to_remove.update_by = request_user_id
    
    # 4. 모든 변경사항을 하나의 트랜잭션으로 커밋
    db.commit()

# =================================================================
# 정책/알림/위젯/CCTV 등 설정 관련 함수
# =================================================================

def find_parking_lot_policy_list(db: Session) -> List[schemas.PolicyResponse]:
    """모든 주차장 정책 목록을 조회합니다."""
    policies = db.query(models.Policy).all()
    return [schemas.PolicyResponse.model_validate(p) for p in policies]

def find_policy_setting_list(db: Session, parking_lot_id: int) -> List[schemas.PolicySettingResponse]:
    """특정 주차장의 정책 설정 목록을 조회합니다."""
    settings = db.query(models.PolicySetting).filter(models.PolicySetting.parking_lot_id == parking_lot_id).all()
    return [schemas.PolicySettingResponse.model_validate(s) for s in settings]

def parking_lot_policy_setting(db: Session, user_id: int, parking_lot_id: int, policy_list: List[schemas.PolicyActive]):
    """주차장 정책을 설정합니다."""
    from . import policy_function # 지연 Import
    policy_function.set_policy_settings(db, user_id, parking_lot_id, policy_list)

def find_notification_list(db: Session) -> List[schemas.NotificationResponse]:
    """모든 알림 종류 목록을 조회합니다."""
    notifications = db.query(models.Notification).all()
    
    grouped_notifications = defaultdict(list)
    for n in notifications:
        group_key = n.notification_type 
        grouped_notifications[group_key].append(schemas.NotificationResponse.NotificationInfo.model_validate(n))

    response_list = []
    for notification_type, notification_list in grouped_notifications.items():
        response_list.append(schemas.NotificationResponse(
            notification_type=notification_type,
            notification_type_name=notification_type.value,
            notification_list=notification_list
        ))
    return response_list

def find_notification_setting_list(db: Session, user_id: int, parking_lot_id: int) -> List[schemas.NotificationSettingResponse]:
    """사용자의 주차장 알림 설정 목록을 조회합니다."""
    settings = db.query(models.NotificationSetting).filter(
        models.NotificationSetting.user_id == user_id,
        models.NotificationSetting.parking_lot_id == parking_lot_id
    ).all()
    return [schemas.NotificationSettingResponse.model_validate(s) for s in settings]

def notification_setting(db: Session, user_id: int, parking_lot_id: int, notification_list: List[schemas.NotificationActive]):
    """주차장 알림을 설정합니다."""
    from . import notification_function # 지연 Import
    notification_function.set_notification_settings(db, user_id, parking_lot_id, notification_list)

def find_widget_category_list(db: Session) -> List[schemas.CategoryResponse]:
    """위젯 카테고리 목록을 조회합니다."""
    categories = db.query(models.WidgetCategory).filter(models.WidgetCategory.use_yn == models.YnType.Y).all()
    return [schemas.CategoryResponse.model_validate(c) for c in categories]

def save_widget_list(db: Session, user_id: int, parking_lot_id: int, request: schemas.SaveLayoutRequest):
    """주차장 도면(레이아웃)을 저장합니다."""
    from . import widget_function # 지연 Import
    widget_function.save_layout(db, user_id, parking_lot_id, request)

def find_widget_list(db: Session, parking_lot_id: int) -> schemas.LayoutResponse:
    """주차장 도면 정보를 조회합니다."""
    from . import widget_function # 지연 Import
    return widget_function.get_layout(db, parking_lot_id)

def find_available_widget_list(db: Session, parking_lot_id: int) -> schemas.LayoutResponse:
    """주차 가능한 위젯 목록을 포함한 도면 정보를 조회합니다."""
    from . import widget_function # 지연 Import
    return widget_function.get_available_layout(db, parking_lot_id)

def find_cctv_list(db: Session, parking_lot_id: int) -> List[schemas.CctvResponse]:
    """주차장의 CCTV 목록을 조회합니다."""
    results = db.query(models.Device, models.Cctv).join(
        models.Cctv, models.Device.device_id == models.Cctv.device_id
    ).filter(models.Device.parking_lot_id == parking_lot_id).all()
    
    return [schemas.CctvResponse(device_id=d.device_id, cctv_id=c.cctv_id, cctv_ip=c.cctv_ip) for d, c in results]

def find_cctv_phone(db: Session) -> schemas.CctvPhoneResponse:
    """CCTV 설치 지원팀 전화번호를 조회합니다."""
    phone_number = settings.CCTV_PHONE
    return schemas.CctvPhoneResponse(cctvPhone=phone_number)

# =================================================================
# 주차 현황 및 기타 조회 함수
# =================================================================

def get_parking_info(db: Session, parking_lot_id: int) -> schemas.SummaryParkingResponse:
    """주차 현황 요약 정보를 조회합니다."""
    # 카테고리 ID 1(주차면)과 2(장애인주차면)를 모두 주차 공간으로 집계
    total_spots = db.query(func.count(models.Widget.widget_id)).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Widget.category_id.in_([1, 2]),
        models.Widget.del_yn == models.YnType.N
    ).scalar() or 0

    # Parking 모델과 Widget 모델을 조인하여 Widget의 parking_lot_id로 필터링
    parking_counts = db.query(
        func.count(models.Parking.parking_id),
        models.Parking.car_type
    ).join(
        models.Widget, models.Parking.widget_id == models.Widget.widget_id
    ).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.del_yn == models.YnType.N
    ).group_by(models.Parking.car_type).all()
    
    counts = {car_type: count for count, car_type in parking_counts}
    registered = counts.get(models.CarType.REGISTERED, 0)
    unregistered = counts.get(models.CarType.UNREGISTERED, 0)
    visitor = counts.get(models.CarType.VISITOR, 0)
    
    parked_count = registered + unregistered + visitor
    empty_count = total_spots - parked_count

    return schemas.SummaryParkingResponse(
        empty_count=max(0, empty_count), # 음수가 되지 않도록
        registered_count=registered,
        unregistered_count=unregistered,
        visitor_count=visitor
    )

def find_car_parking_lot_info(db: Session, user_id: int, car_id: int) -> schemas.CarParkingLotResponse:
    """특정 차량이 등록된 주차장 목록과 현재 주차 정보를 조회합니다."""
    # 1. 차량이 등록된 주차장 목록 조회
    parking_lot_cars = db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.car_id == car_id,
        models.ParkingLotCar.create_by == user_id,
        models.ParkingLotCar.del_yn == models.YnType.N
    ).all()
    
    parking_lot_ids = [plc.parking_lot_id for plc in parking_lot_cars]
    
    if not parking_lot_ids:
        return schemas.CarParkingLotResponse(parking_lot_list=[])

    # 2. 해당 주차장들의 정보 조회
    parking_lots = db.query(models.ParkingLot).filter(
        models.ParkingLot.parking_lot_id.in_(parking_lot_ids),
        models.ParkingLot.del_yn == models.YnType.N
    ).all()
    
    parking_lot_info_list = []
    for lot in parking_lots:
        parking_info_schema = None
        
        # 3. 각 주차장별로 현재 주차 정보 조회
        current_parking_in_lot = db.query(models.Parking).join(
            models.Widget, models.Parking.widget_id == models.Widget.widget_id
        ).filter(
            models.Widget.parking_lot_id == lot.parking_lot_id,
            models.Parking.car_id == car_id,
            models.Parking.del_yn == models.YnType.N
        ).first()

        if current_parking_in_lot:
            parking_info_schema = schemas.CarParkingLotResponse.ParkingInfo.model_validate(current_parking_in_lot)
            
        parking_lot_info_list.append(schemas.CarParkingLotResponse.ParkingLotInfo(
            parking_lot_id=lot.parking_lot_id,
            parking_lot_name=lot.parking_lot_name,
            parking_lot_address=lot.parking_lot_address,
            parking_lot_address_detail=lot.parking_lot_address_detail,
            latitude=lot.latitude,
            longitude=lot.longitude,
            parking_info=parking_info_schema
        ))
        
    return schemas.CarParkingLotResponse(parking_lot_list=parking_lot_info_list)

# =================================================================
# 기타 함수들
# =================================================================

# 채팅 서버 미적재로 인하여 미사용
# def update_last_chat_message_id(db: Session, user_id: int, parking_lot_id: int, message_id: int):
#     """사용자의 마지막 확인 메시지 ID를 업데이트합니다."""
#     user_in_lot = _get_parking_lot_user(db, user_id, parking_lot_id)
#     user_in_lot.last_read_message_id = message_id
#     db.commit()

def get_chat_user_list(db: Session, parking_lot_id: int, chat_join_yn: models.YnType) -> List[models.ParkingLotUser]:
    """채팅 참여 여부 조건에 맞는 사용자 목록을 조회합니다."""
    return db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.Y,
        models.ParkingLotUser.del_yn == models.YnType.N,
        models.ParkingLotUser.chat_join_yn == chat_join_yn
    ).all()
    
def remove_all_users_from_parking_lot(db: Session, updater_id: int, parking_lot_id: int):
    """주차장의 모든 사용자 정보를 논리적으로 삭제합니다."""
    db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id
    ).update({"del_yn": models.YnType.Y}, synchronize_session=False)
    # db.commit()

def remove_all_user_associations(db: Session, user_id: int):
    """회원 탈퇴 시 모든 주차장에서 해당 유저의 정보를 논리적으로 삭제합니다."""
    db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id
    ).update({"del_yn": models.YnType.Y}, synchronize_session=False)
    
    # ParkingLotCar 정보도 삭제
    db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.create_by == user_id
    ).update({"del_yn": models.YnType.Y}, synchronize_session=False)

    db.commit()

def get_user_info_list(db: Session, parking_lot_id: int, user_ids: Set[int]) -> List[schemas.VoteUserResponse.VoteUser]:
    """[Vote용] 주어진 사용자 ID 목록에 대해 주차장 내 닉네임을 조회합니다."""
    if not user_ids:
        return []

    user_info_list = db.query(
        models.ParkingLotUser.user_id,
        models.ParkingLotUser.user_nickname
    ).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_id.in_(user_ids)
    ).all()

    return [
        schemas.VoteUserResponse.VoteUser(user_id=uid, user_nickname=nickname)
        for uid, nickname in user_info_list
    ]
    
def find_join_user_list_internal(db: Session, parking_lot_id: int) -> List[models.ParkingLotUser]:
    """[Notification용] 특정 주차장에 가입 승인된 모든 사용자 모델 목록을 반환합니다."""
    return db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.accept_yn == models.YnType.Y,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()
