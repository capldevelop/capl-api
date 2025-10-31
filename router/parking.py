# app/router/parking.py
from fastapi import APIRouter, Depends, Query, Path, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional

from core.database import get_db
from core import schemas
from function import parking_function, parking_lot_function, notification_function
from core.dependencies import get_current_user_id
# from service.tcp_manager import session_manager # TCP 매니저 import

router = APIRouter(
    prefix="/parking", 
    tags=["Parking"]
)

# (가정) ParkingLotRoleValidator.verifyUser를 대체하는 의존성
async def verify_user_in_parking_lot(
    request: schemas.ManualPullOutRequest, # parking_lot_id를 포함하는 DTO
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    print(f"Verifying user role for user {user_id} in parking lot {request.parking_lot_id}")
    # 권한 검증 실패 시 HTTPException 발생 로직 필요

# =================================================================
# API Endpoints
# =================================================================

# -----------------------------------------------------------------
# PUT Endpoints
# -----------------------------------------------------------------

@router.put("/spot/edit", summary="차량 주차면 이동")
def convert_parking_spot(
    request: schemas.EditSpotRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    parking_function.convert_parking_spot(db, user_id, request) # 인자 전달
    return schemas.RootResponse.ok(None)

@router.put("/pull-out-time/edit", summary="예상 출차 시간 수정")
def edit_pull_out_time(
    request: schemas.EditPullOutTimeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    parking_function.edit_pull_out_at(db, user_id, request) # 인자 전달
    return schemas.RootResponse.ok(None)

@router.put("/edit", summary="차량 주차 수정")
def edit_parking(
    request: schemas.EditParkingRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    parking_function.edit_parking(db, user_id, request) # 인자 전달
    return schemas.RootResponse.ok(None)

@router.put("/car-type/edit", summary="입차 정보 차량 타입 전환")
def convert_visitor(
    request: schemas.EditCarTypeRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    parking_function.convert_car_type(db, user_id, request) # 인자 전달
    return schemas.RootResponse.ok(None)

# -----------------------------------------------------------------
# POST Endpoints
# -----------------------------------------------------------------

@router.post("/add/manual", summary="차량 수동 입차")
def add_parking_manual(
    request: schemas.ManualParkingRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    parking_function.manual_parking(db, background_tasks, user_id, request)
    return schemas.RootResponse.ok(None)

@router.post("/add/auto", summary="차량 자동 입차")
async def add_parking_auto(
    request: schemas.AutoParkingRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    자동 입차 요청을 접수하고, 실제 처리는 백그라운드의 중앙 처리 함수로 넘깁니다.
    """
    parking_lot_function.verify_user_role(db, user_id, request.parking_lot_id)
    
    # 'PENDING' 작업
    new_request_obj = parking_function.auto_parking(db, user_id, request)
    response = schemas.AutoParkingRequestResponse(parkingRequestId=new_request_obj.request_id)

    # 새로 만든 중앙 처리 함수를 백그라운드 태스크로 등록
    background_tasks.add_task(
        parking_function.process_auto_parking_flow,
        new_request_obj.request_id
    )
    
    return schemas.RootResponse.ok(response)
    
    # response = await parking_function.auto_parking(db, background_tasks, user_id, request)
    # return schemas.RootResponse.ok(response)

@router.post("/geofence-entry", summary="Geofence 진입 이벤트 수신")
def trigger_geofence_notification(
    request: schemas.GeofenceEntryRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id)
):
    """
    모바일 앱에서 Geofence 진입을 감지했을 때 호출하는 API입니다.
    백그라운드에서 주차장 근접 알림 전송을 처리합니다.
    """
    # 백그라운드 작업으로 알림 함수를 호출합니다.
    # 이 때, DB 세션은 전달하지 않습니다. (함수 내부에서 생성)
    background_tasks.add_task(
        notification_function.handle_geofence_entry_event,
        user_id,
        request.parking_lot_id
    )
    return schemas.RootResponse.ok(None)


@router.post("/sync", summary="CCTV 주차 상태 동기화")
def sync_parking_status_from_cctv(
    request: schemas.ParkingSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    LPR 클라이언트(미니PC)로부터 주기적으로 주차장 상태를 받아 DB와 동기화합니다.
    """
    # 실제 동기화 로직은 무거울 수 있으므로 백그라운드에서 처리합니다.
    background_tasks.add_task(parking_function.sync_parking_status, db, background_tasks, request)
    return schemas.RootResponse.ok({"message": "Sync request received."})

# @router.post("/pull-out/push", summary="자동 출차 푸시 발송 (Hidden)", include_in_schema=False)
# def send_auto_pull_out_push(request: schemas.PullOutPushRequest, db: Session = Depends(get_db)):
#     # parking_function.send_pull_out_push(...) # 실제 함수 호출 로직 필요
#     return True

# @router.post("/pull-in/push", summary="입차 완료 푸시 발송 (Hidden)", include_in_schema=False)
# def send_pull_in_push(request: schemas.PullInPushRequest, db: Session = Depends(get_db)):
#     # parking_function.send_pull_in_push(...) # 실제 함수 호출 로직 필요
#     return True

# -----------------------------------------------------------------
# GET Endpoints
# -----------------------------------------------------------------

@router.get("", summary="주차 정보 조회")
def find_parking(
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    car_number: str = Query(..., alias="car_number"),
    db: Session = Depends(get_db)
):
    parking_info = parking_function.find_parking_by_car(db, parking_lot_id, car_number)
    return schemas.RootResponse.ok(parking_info)

@router.get("/request/{request_id}", summary="차량 입차 요청 상태 조회")
def find_parking_request_status(
    request_id: int,
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    status_response = parking_function.check_parking_request(db, request_id)
    return schemas.RootResponse.ok(status_response)

@router.get("/pull-out-time", summary="사용자 예상 출차 시간 조회")
def find_pull_out_time(
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    pull_out_time = parking_function.get_user_pull_out_time(db, user_id, parking_lot_id)
    return schemas.RootResponse.ok(pull_out_time)

@router.get("/list", summary="주차장 주차 정보 조회")
def find_parking_list(
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    parking_list = parking_function.find_parking_list_by(db, parking_lot_id)
    return schemas.RootResponse.ok(parking_list)

@router.get("/latest", summary="마지막 주차 이용 정보 조회")
def find_latest_parking(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    latest_parking = parking_function.find_last_parking(db, user_id)
    return schemas.RootResponse.ok(latest_parking)

@router.get("/check", summary="차량 주차 상태 조회")
def check_parking(
    parking_lot_id: int = Query(..., alias="parking_lot_id"),
    car_id: int = Query(..., alias="car_id"),
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_lot_function.verify_user_role(db, user_id, parking_lot_id)
    is_parking = parking_function.is_parking(db, parking_lot_id, car_id)
    return schemas.RootResponse.ok(is_parking)

@router.get("/check/car-list", summary="차량 목록 주차 상태 조회")
def check_parking_car_list(
    car_id_list: List[int] = Query(..., alias="car_id_list"),
    db: Session = Depends(get_db)
):
    status_list = parking_function.is_parking_by_car_id_list(db, car_id_list)
    return schemas.RootResponse.ok(status_list)

# -----------------------------------------------------------------
# DELETE Endpoints
# -----------------------------------------------------------------

@router.delete("/delete/manual", summary="차량 수동 출차", dependencies=[Depends(verify_user_in_parking_lot)])
def remove_parking_manual(
    request: schemas.ManualPullOutRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    parking_function.manual_pull_out(db, background_tasks, user_id, request)
    return schemas.RootResponse.ok(None)

@router.delete("/delete/auto", summary="차량 자동 출차", dependencies=[Depends(verify_user_in_parking_lot)])
def remove_parking_auto(
    request: schemas.AutoPullOutRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # parking_function.auto_pull_out(db, background_tasks, user_id, request)
    # return schemas.RootResponse.ok(None)
    """
    자동 출차 요청을 접수하고, 실제 처리는 백그라운드의 중앙 처리 함수로 넘깁니다.
    """
    new_request_obj = parking_function.auto_pull_out(db, user_id, request)
    response = schemas.AutoParkingRequestResponse(parkingRequestId=new_request_obj.request_id)
    
    # 새로 만든 중앙 처리 함수를 백그라운드 태스크로 등록
    background_tasks.add_task(
        parking_function.process_auto_pull_out_flow,
        new_request_obj.request_id
    )

    return schemas.RootResponse.ok(response)
