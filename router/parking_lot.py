# app/router/parking_lot.py
from fastapi import APIRouter, Depends, Query, Path, Request
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core import schemas
from function import parking_lot_function
from core.dependencies import get_current_user_id

router = APIRouter(prefix="/parking-lot", tags=["Parking-Lot"])

# =================================================================
# Dependencies for Authorization
# =================================================================

async def verify_admin_role(
    user_id: int = Depends(get_current_user_id),
    parking_lot_id: int = Path(..., description="주차장ID"),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_admin_role(db, user_id, parking_lot_id)

async def verify_user_role(
    user_id: int = Depends(get_current_user_id),
    parking_lot_id: int = Path(..., description="주차장ID"),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)

# =================================================================
# API Endpoints (PUT, POST, GET, DELETE 순서)
# =================================================================

# -----------------------------------------------------------------
# PUT Endpoints
# -----------------------------------------------------------------

@router.put("/{parking_lot_id}/edit", summary="주차장 기본 정보 수정", dependencies=[Depends(verify_admin_role)])
async def edit_parking_lot_info(
    parking_lot_id: int,
    request: schemas.EditParkingLotRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    await parking_lot_function.edit_parking_lot_info(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/edit/name", summary="주차장 이름 수정", dependencies=[Depends(verify_admin_role)])
def edit_parking_lot_name(
    parking_lot_id: int,
    request: schemas.EditParkingLotNameRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_parking_lot_name(db, user_id, parking_lot_id, request.parking_lot_name)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/edit/address", summary="주차장 주소 수정", dependencies=[Depends(verify_admin_role)])
async def edit_parking_lot_address_detail(
    parking_lot_id: int,
    request: schemas.EditParkingLotAddressRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    await parking_lot_function.edit_parking_lot_address(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/edit/public", summary="주차장 공개 여부 수정", dependencies=[Depends(verify_admin_role)])
def edit_parking_lot_public(
    parking_lot_id: int,
    request: schemas.EditParkingLotPublicRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_parking_lot_public(db, user_id, parking_lot_id, request.parking_lot_public)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/join/user/{target_user_id}/edit/role", summary="주차장 참여자 권한 변경", dependencies=[Depends(verify_admin_role)])
def edit_user_role(
    parking_lot_id: int,
    target_user_id: int,
    request: schemas.EditUserRoleRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_role(db, user_id, parking_lot_id, target_user_id, request.user_role)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit", summary="주차장 참여자 정보 수정", dependencies=[Depends(verify_user_role)])
def edit_me(
    parking_lot_id: int,
    request: schemas.EditUserInfoRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_info(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit/pull-out-time", summary="주차장 참여자 고정출차시간 수정", dependencies=[Depends(verify_user_role)])
def edit_pull_out_time(
    parking_lot_id: int,
    request: schemas.EditUserPullOutTimeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_pull_out_time(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit/car", summary="주차장 참여자 차량 수정", dependencies=[Depends(verify_user_role)])
def edit_car(
    parking_lot_id: int,
    request: schemas.EditUserCarRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_car(db, user_id, parking_lot_id, request.car_id_list)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit/nickname", summary="주차장 참여자 닉네임 수정", dependencies=[Depends(verify_user_role)])
def edit_nickname(
    parking_lot_id: int,
    request: schemas.EditUserNicknameRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_nickname(db, user_id, parking_lot_id, request.user_nickname)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit/phone-secret", summary="주차장 참여자 휴대폰번호 공개 여부 수정", dependencies=[Depends(verify_user_role)])
def edit_phone_secret(
    parking_lot_id: int,
    request: schemas.EditUserPhoneSecretRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_phone_secret(db, user_id, parking_lot_id, request.phone_secret_yn)
    return schemas.RootResponse.ok(None)

@router.put("/{parking_lot_id}/me/edit/pull-out-time-yn", summary="주차장 참여자 출차시간 적용 여부 수정", dependencies=[Depends(verify_user_role)])
def edit_pull_out_time_yn(
    parking_lot_id: int,
    request: schemas.EditUserPullOutTimeYnRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.edit_user_pull_out_time_yn(db, user_id, parking_lot_id, request.pull_out_time_yn)
    return schemas.RootResponse.ok(None)

# -----------------------------------------------------------------
# POST Endpoints
# -----------------------------------------------------------------

@router.post("/add", summary="주차장 등록", response_model=schemas.RootResponse[schemas.AddParkingLotResponse])
async def add_parking_lot(
    request: schemas.AddParkingLotRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_id = await parking_lot_function.add_parking_lot(db, user_id, request)
    response_data = schemas.AddParkingLotResponse(parkingLotId=parking_lot_id)
    return schemas.RootResponse.ok(response_data)

@router.post("/{parking_lot_id}/join", summary="주차장 가입 요청")
def request_parking_lot_join(
    parking_lot_id: int,
    request: schemas.JoinParkingLotRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.request_parking_lot_join(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/join/cancel", summary="주차장 가입 요청 취소")
def request_parking_lot_join_cancel(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.request_reject(db, user_id, parking_lot_id, [user_id])
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/join/accept", summary="주차장 참여요청자 승인", dependencies=[Depends(verify_admin_role)])
def request_accept(
    parking_lot_id: int,
    request: schemas.AcceptJoinRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.request_accept(db, user_id, parking_lot_id, request.user_id_list)
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/join/reject", summary="주차장 참여요청자 거절", dependencies=[Depends(verify_admin_role)])
def request_reject(
    parking_lot_id: int,
    request: schemas.RejectJoinRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.request_reject(db, user_id, parking_lot_id, request.user_id_list)
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/policy/setting", summary="주차장 정책 설정", dependencies=[Depends(verify_admin_role)])
def policy_setting(
    parking_lot_id: int,
    request: schemas.PolicySettingRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.parking_lot_policy_setting(db, user_id, parking_lot_id, request.policy_active_info_list)
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/notification/setting", summary="주차장 알람 설정", dependencies=[Depends(verify_user_role)])
def notification_setting(
    parking_lot_id: int,
    request: schemas.NotificationSettingRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.notification_setting(db, user_id, parking_lot_id, request.notification_active_info_list)
    return schemas.RootResponse.ok(None)

@router.post("/{parking_lot_id}/widget/save", summary="주차장 도면 정보 저장", dependencies=[Depends(verify_admin_role)])
def save_widget_list(
    parking_lot_id: int,
    request: schemas.SaveLayoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.save_widget_list(db, user_id, parking_lot_id, request)
    return schemas.RootResponse.ok(None)

# -----------------------------------------------------------------
# GET Endpoints
# -----------------------------------------------------------------

@router.get("/check", summary="주차장 등록 여부 조회")
def check_parking_lot(address: str = Query(..., description="주차장 주소"), db: Session = Depends(get_db)):
    parking_lot = parking_lot_function.check_parking_lot(db, address)
    return schemas.RootResponse.ok(parking_lot)

@router.get("/policy/list", summary="주차장 정책 목록 조회")
def get_policy_list(db: Session = Depends(get_db)):
    policy_list = parking_lot_function.find_parking_lot_policy_list(db)
    return schemas.RootResponse.ok(policy_list)

@router.get("/list", summary="가입 요청용 주차장 목록 조회(등록된 주차장 검색)")
def find_parking_lot_list(
    keyword: str = Query(..., description="검색키워드"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_list = parking_lot_function.find_parking_lot_list_by(db, user_id, keyword)
    return schemas.RootResponse.ok(parking_lot_list)

@router.get("/join/list", summary="가입 주차장 목록 조회")
def find_join_parking_lot_list(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_list = parking_lot_function.get_join_parking_lot_list(db, user_id)
    return schemas.RootResponse.ok(parking_lot_list)

@router.get("/join/{parking_lot_id}", summary="가입 주차장 상세 조회")
def join_parking_lot(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    join_parking_lot = parking_lot_function.find_join_parking_lot(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(join_parking_lot)

@router.get("/{parking_lot_id}", summary="주차장 기본 정보 조회", dependencies=[Depends(verify_admin_role)])
def find_parking_lot_info(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    parking_lot_info = parking_lot_function.find_parking_lot_info(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_lot_info)

@router.get("/{parking_lot_id}/location", summary="주차장 위치 정보 조회", dependencies=[Depends(verify_user_role)])
def find_parking_lot_location(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    location_info = parking_lot_function.find_parking_lot_home_info(db, parking_lot_id)
    return schemas.RootResponse.ok(location_info)

@router.get("/{parking_lot_id}/me", summary="주차장 사용자 참여 정보 조회")
def find_parking_lot_user_info(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    user_info = parking_lot_function.find_parking_lot_user_info(db, parking_lot_id, user_id)
    return schemas.RootResponse.ok(user_info)

@router.get("/{parking_lot_id}/join/request-user/list", summary="주차장 참여요청자 목록 조회", dependencies=[Depends(verify_admin_role)])
def find_request_join_user_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    request_list = parking_lot_function.find_request_join_user_list(db, parking_lot_id)
    return schemas.RootResponse.ok(request_list)

@router.get("/{parking_lot_id}/join/user/list", summary="주차장 참여자 목록 조회", dependencies=[Depends(verify_admin_role)])
def find_join_user_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    user_list = parking_lot_function.find_join_user_list(db, parking_lot_id)
    return schemas.RootResponse.ok(user_list)

@router.get("/{parking_lot_id}/policy/list", summary="주차장 정책 설정 목록 조회", dependencies=[Depends(verify_admin_role)])
def find_policy_setting_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    policy_list = parking_lot_function.find_policy_setting_list(db, parking_lot_id)
    return schemas.RootResponse.ok(policy_list)

@router.get("/notification/list", summary="주차장 알람 목록 조회")
def find_notification_list(db: Session = Depends(get_db)):
    notification_list = parking_lot_function.find_notification_list(db)
    return schemas.RootResponse.ok(notification_list)

@router.get("/{parking_lot_id}/notification/list", summary="주차장 알람 설정 목록 조회", dependencies=[Depends(verify_user_role)])
def find_notification_setting_list(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    setting_list = parking_lot_function.find_notification_setting_list(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(setting_list)

@router.get("/{parking_lot_id}/widget/category/list", summary="주차장 위젯 카테고리 목록 조회", dependencies=[Depends(verify_admin_role)])
def find_widget_category_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    category_list = parking_lot_function.find_widget_category_list(db)
    return schemas.RootResponse.ok(category_list)

@router.get("/{parking_lot_id}/widget/list", summary="주차장 도면 정보 조회", dependencies=[Depends(verify_user_role)])
def find_widget_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    layout = parking_lot_function.find_widget_list(db, parking_lot_id)
    return schemas.RootResponse.ok(layout)

@router.get("/{parking_lot_id}/widget/available/list", summary="주차장 도면 중 빈 주차면 정보 조회", dependencies=[Depends(verify_user_role)])
def find_available_widget_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    layout = parking_lot_function.find_available_widget_list(db, parking_lot_id)
    return schemas.RootResponse.ok(layout)

@router.get("/{parking_lot_id}/cctv/list", summary="주차장 CCTV 목록 조회", dependencies=[Depends(verify_admin_role)])
def find_cctv_list(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    cctv_list = parking_lot_function.find_cctv_list(db, parking_lot_id)
    return schemas.RootResponse.ok(cctv_list)

@router.get("/{parking_lot_id}/parking-info", summary="주차장 주차 현황 조회", dependencies=[Depends(verify_user_role)])
def find_parking_info(parking_lot_id: int, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    parking_info = parking_lot_function.get_parking_info(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_info)

@router.get("/cctv/phone", summary="주차장 CCTV 설치지원팀 전화번호 조회")
def get_cctv_phone(db: Session = Depends(get_db)):
    cctv_phone = parking_lot_function.find_cctv_phone(db)
    return schemas.RootResponse.ok(cctv_phone)

@router.get("/list/car/{car_id}", summary="차량 등록 주차장 목록 조회")
def find_car_parking_lot_list(
    car_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    car_parking_lot_info = parking_lot_function.find_car_parking_lot_info(db, user_id, car_id)
    return schemas.RootResponse.ok(car_parking_lot_info)

# -----------------------------------------------------------------
# DELETE Endpoints
# -----------------------------------------------------------------

@router.delete("/{parking_lot_id}/delete", summary="주차장 삭제", dependencies=[Depends(verify_admin_role)])
def delete_parking_lot(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.delete_parking_lot(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(None)

@router.delete("/{parking_lot_id}/join/user/{target_user_id}/delete", summary="주차장 참여자 삭제", dependencies=[Depends(verify_admin_role)])
def delete_user(
    parking_lot_id: int,
    target_user_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.remove_user(db, user_id, parking_lot_id, target_user_id)
    return schemas.RootResponse.ok(None)

@router.delete("/{parking_lot_id}/me/delete", summary="주차장 나가기", dependencies=[Depends(verify_user_role)])
def delete_me(
    parking_lot_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.remove_user(db, user_id, parking_lot_id, user_id)
    return schemas.RootResponse.ok(None)
