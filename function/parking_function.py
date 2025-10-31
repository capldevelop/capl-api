# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict
from fastapi import HTTPException, status, BackgroundTasks
from datetime import datetime, timedelta
import asyncio
import traceback # [디버깅 추가] 상세한 에러 출력을 위해 import

from core import models, schemas
from zoneinfo import ZoneInfo
from core.database import SessionLocal # [수정] 백그라운드 작업을 위해 SessionLocal import

from core.config import settings
# from service.tcp_manager import session_manager # 최상단에서 import하지 않음

# 시간대(Timezone) 객체 정의
KST = ZoneInfo("Asia/Seoul")


# =================================================================
# 내부 유틸리티 함수 (신규 추가 및 수정)
# =================================================================

def _find_closest_match_in_parked(ocr_car_no: str, db_parkings_map: Dict[str, models.Parking]) -> Optional[models.Parking]:
    from . import lpr_function
    """
    OCR로 인식된 차량 번호와 가장 유사한 DB 주차 정보를 찾습니다.
    """
    # 1. 정확히 일치하는 경우 바로 반환
    if ocr_car_no in db_parkings_map:
        return db_parkings_map[ocr_car_no]

    # 2. 마지막 4자리 비교
    ocr_digits = lpr_function.extract_last_digits(ocr_car_no)
    if not ocr_digits:
        return None

    for db_car_no, parking_info in db_parkings_map.items():
        db_digits = lpr_function.extract_last_digits(db_car_no)
        if db_digits and db_digits == ocr_digits:
            return parking_info # 일치하는 DB 주차 정보를 반환
            
    return None # 일치하는 번호가 없으면 None 반환

def _is_fuzzy_match_in_set(ocr_car_no: str, registered_car_numbers_set: set[str]) -> bool:
    from . import lpr_function
    """OCR 번호가 등록된 차량 번호 목록에 유사하게라도 일치하는지 확인합니다."""
    # 1. 정확히 일치하는지 확인
    if ocr_car_no in registered_car_numbers_set:
        return True
    
    # 2. 마지막 4자리 숫자로 비교
    ocr_digits = lpr_function.extract_last_digits(ocr_car_no)
    if not ocr_digits:
        return False
        
    for registered_car_no in registered_car_numbers_set:
        registered_digits = lpr_function.extract_last_digits(registered_car_no)
        if registered_digits and registered_digits == ocr_digits:
            return True # 일치하는 경우 발견
            
    return False

def _get_admin_id_for_lot(db: Session, parking_lot_id: int) -> Optional[int]:
    """[신규] 주차장의 첫 번째 관리자(ADMIN) 사용자의 ID를 반환합니다."""
    admin_user = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_role == models.UserRole.ADMIN,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).first()
    return admin_user.user_id if admin_user else None

def _create_or_update_pull_out_schedules(db: Session, parking: models.Parking):
    """
    [신규] 출차 예정 시간에 대한 알림 스케줄을 생성하거나 업데이트합니다.
    기존 스케줄을 먼저 삭제하고, 새로운 시간에 맞춰 다시 생성합니다.
    """
    from . import schedule_function, notification_function # 지연 Import

    # 1. 이 주차 건(parking_id)과 관련된 기존의 모든 'PENDING' 출차 알림을 삭제합니다.
    delete_event = schemas.ScheduleDeleteEvent(
        task_type=models.TaskType.PULL_OUT_BEFORE,
        type_id=parking.parking_id
    )
    schedule_function.delete_schedule(db, delete_event)

    # 2. 새로운 출차 시간이 설정된 경우에만 새 스케줄을 생성합니다.
    if parking.pull_out_end_at:
        # [수정] DB에서 온 naive한 시간을 비교를 위해 KST-aware로 변환
        pull_out_end_at_kst = parking.pull_out_end_at.replace(tzinfo=KST)
        pull_out_start_at_kst = parking.pull_out_start_at.replace(tzinfo=KST)
           
        now_kst = datetime.now(KST)

        # 3. 30분 전 알림 스케줄 생성 (단, 실행 시간이 현재보다 미래이고, 알림이 켜져 있을 경우에만)
        if notification_function.is_notification_active(db, user_id=parking.create_by, parking_lot_id=parking.widget.parking_lot_id, notification_id=3):
            if pull_out_start_at_kst and pull_out_start_at_kst > now_kst:
                before_event = schemas.ScheduleCreateEvent(
                    user_id=parking.create_by,
                    parking_lot_id=parking.widget.parking_lot_id,
                    task_type=models.TaskType.PULL_OUT_BEFORE,
                    type_id=parking.parking_id,
                    # [수정] DB(KST)에 저장하는 것은 naive한 시간이므로 그대로 전달
                    execute_time=parking.pull_out_start_at
                )
                schedule_function.create_schedule(db, before_event)

        # 4. 정시 알림 스케줄 생성 (단, 실행 시간이 현재보다 미래이고, 알림이 켜져 있을 경우에만)
        if notification_function.is_notification_active(db, user_id=parking.create_by, parking_lot_id=parking.widget.parking_lot_id, notification_id=4):
            if pull_out_end_at_kst and pull_out_end_at_kst > now_kst:
                after_event = schemas.ScheduleCreateEvent(
                    user_id=parking.create_by,
                    parking_lot_id=parking.widget.parking_lot_id,
                    task_type=models.TaskType.PULL_OUT_AFTER,
                    type_id=parking.parking_id,
                    # [수정] DB(KST)에 저장하는 것은 naive한 시간이므로 그대로 전달
                    execute_time=parking.pull_out_end_at
                )
                schedule_function.create_schedule(db, after_event)

def _get_parking_by_widget_id(db: Session, widget_id: int) -> models.Parking:
    """위젯 ID로 현재 주차 정보를 조회합니다. (N+1 방지를 위해 widget join 추가)"""
    parking = db.query(models.Parking).options(joinedload(models.Parking.widget)).filter(
        models.Parking.widget_id == widget_id,
        models.Parking.del_yn == models.YnType.N
    ).first()
    if not parking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PARKING_INFO_NOT_FOUND")
    return parking

def _get_widget_by_id(db: Session, widget_id: int) -> models.Widget:
    """위젯 ID로 위젯 정보를 조회합니다."""
    widget = db.query(models.Widget).filter(
        models.Widget.widget_id == widget_id,
        models.Widget.del_yn == models.YnType.N
    ).first()
    if not widget:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WIDGET_NOT_FOUND")
    return widget

def _get_parking_lot_by_id(db: Session, parking_lot_id: int) -> models.ParkingLot:
    """주차장 ID로 주차장 정보를 조회합니다."""
    parking_lot = db.query(models.ParkingLot).filter(models.ParkingLot.parking_lot_id == parking_lot_id).first()
    if not parking_lot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PARKING_LOT_NOT_FOUND")
    return parking_lot

def _get_parking_lot_user_info(db: Session, user_id: int, parking_lot_id: int) -> Optional[models.ParkingLotUser]:
    """주차장 사용자 정보를 조회합니다."""
    return db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).first()

def is_spot_occupied(db: Session, widget_id: int) -> bool:
    """주차 공간이 현재 사용 중인지 확인합니다."""
    return db.query(models.Parking).filter(
        models.Parking.widget_id == widget_id,
        models.Parking.del_yn == models.YnType.N
    ).first() is not None

def _move_to_history(db: Session, parking: models.Parking, updater_id: int, is_auto: bool):
    """[수정] 주차 기록을 히스토리 테이블로 옮기고, 관련 스케줄을 삭제합니다."""
    from . import schedule_function

    history = models.ParkingHistory(
        user_id=parking.create_by,
        parking_lot_id=parking.widget.parking_lot_id,
        car_id=parking.car_id,
        widget_id=parking.widget_id,
        car_number=parking.car_number,
        car_type=parking.car_type,
        pull_in_at=parking.pull_in_at,
        pull_out_at=datetime.now(KST),
        pull_out_start_at=parking.pull_out_start_at,
        pull_out_end_at=parking.pull_out_end_at,
        pull_in_auto_yn=parking.pull_in_auto_yn,
        pull_out_auto_yn=models.YnType.Y if is_auto else models.YnType.N
    )
    db.add(history)

    parking.del_yn = models.YnType.Y
    parking.update_by = updater_id
    parking.pull_out_at = history.pull_out_at

    # 출차 시 관련 스케줄도 함께 삭제
    delete_event = schemas.ScheduleDeleteEvent(
        task_type=models.TaskType.PULL_OUT_BEFORE,
        type_id=parking.parking_id
    )
    schedule_function.delete_schedule(db, delete_event)

def _check_and_handle_policy_violations(parking_lot_id: int, user_id: int):
    """
    [수정] 백그라운드 작업으로 실행되도록 DB 세션을 내부에서 생성하고 관리합니다.
    주차 후 정책 위반(중복 주차, 만차) 여부를 확인하고 알림을 보냅니다.
    """
    db: Session = None
    try:
        print(f"[BG_TASK_DEBUG] Starting _check_and_handle_policy_violations for user: {user_id}, lot: {parking_lot_id}")
        db = SessionLocal()
        from . import notification_function

        # 1. 한 사용자의 중복 주차 확인
        user_parking_count = db.query(models.Parking).join(models.Widget).filter(
            models.Widget.parking_lot_id == parking_lot_id,
            models.Parking.create_by == user_id,
            models.Parking.del_yn == models.YnType.N
        ).count()

        if user_parking_count > 1:
            user_info = _get_parking_lot_user_info(db, user_id, parking_lot_id)
            user_nickname = user_info.user_nickname if user_info else "사용자"
               
            event = schemas.PolicyViolationPushEvent(
                user_id=user_id,
                user_nickname=user_nickname,
                parking_lot_id=parking_lot_id,
                reason="MULTIPLE_PARKING"
            )
            print(f"[BG_TASK_DEBUG] Triggering MULTIPLE_PARKING violation for user: {user_id}")
            notification_function.handle_policy_violation_event(event)

        # 2. 만차 상태 확인
        total_spots = db.query(models.Widget).filter(
            models.Widget.parking_lot_id == parking_lot_id,
            models.Widget.category_id.in_([1, 2]), # 1: 일반, 2: 장애인 주차면
            models.Widget.del_yn == models.YnType.N
        ).count()

        parked_cars = db.query(models.Parking).join(models.Widget).filter(
            models.Widget.parking_lot_id == parking_lot_id,
            models.Parking.del_yn == models.YnType.N
        ).count()

        if total_spots > 0 and parked_cars >= total_spots:
            user_info = _get_parking_lot_user_info(db, user_id, parking_lot_id)
            user_nickname = user_info.user_nickname if user_info else "사용자"

            event = schemas.PolicyViolationPushEvent(
                user_id=user_id,
                user_nickname=user_nickname, # 실제 메시지엔 사용되지 않음
                parking_lot_id=parking_lot_id,
                reason="PARKING_LOT_FULL"
            )
            print(f"[BG_TASK_DEBUG] Triggering PARKING_LOT_FULL violation for lot: {parking_lot_id}")
            notification_function.handle_policy_violation_event(event)
           
        print(f"[BG_TASK_DEBUG] Finished _check_and_handle_policy_violations for user: {user_id}")
    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] in _check_and_handle_policy_violations: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()
           
# 미니 PC(Device) 존재 여부를 확인하는 함수
def does_parking_lot_have_cctv(db: Session, parking_lot_id: int) -> bool:
    """해당 주차장에 Device(미니 PC)가 등록되어 있는지 확인합니다."""
    return db.query(models.Device).filter(models.Device.parking_lot_id == parking_lot_id).first() is not None

# 수동 입차에 대한 CCTV 검증을 시작하는 별도의 백그라운드 함수
def trigger_cctv_verification(request_id: int):
    """
    [수정] 생성된 ParkingRequest ID를 받아 TCP 서버로 검증을 요청하는 백그라운드 작업.
    """
    try:
        print(f"[BG_TASK_DEBUG] Starting trigger_cctv_verification for request_id: {request_id}")
        from service.tcp_manager import session_manager
        import asyncio

        if session_manager:
            # asyncio.run()을 사용해 비동기 함수를 동기적으로 실행합니다.
            # 이 함수가 끝날 때까지 이 라인에서 기다립니다.
            asyncio.run(session_manager.send_pull_in_request(request_id))
            print(f"[BG_TASK_DEBUG] pull_in_request for {request_id} has been COMPLETED.")
        else:
            print(f"[BG_TASK_DEBUG] session_manager not found. Skipping CCTV verification.")
    except Exception as e:
        print(f"[CRITICAL BACKGROUND TASK ERROR] in trigger_cctv_verification: {e}")
        import traceback
        traceback.print_exc()

# [신규] 수동 출차에 대한 CCTV 검증을 시작하는 별도의 백그라운드 함수
def trigger_cctv_pull_out_verification(request_id: int):
    """
    [수정] 생성된 출차 ParkingRequest ID를 받아 TCP 서버로 출차 검증을 요청하는 백그라운드 작업.
    """
    try:
        print(f"[BG_TASK_DEBUG] Starting trigger_cctv_pull_out_verification for request_id: {request_id}")
        from service.tcp_manager import session_manager
        import asyncio
           
        if session_manager:
            # 여기도 asyncio.run()으로 변경
            asyncio.run(session_manager.send_pull_out_request(request_id))
            print(f"[BG_TASK_DEBUG] pull_out_request for {request_id} has been COMPLETED.")
        else:
            print(f"[BG_TASK_DEBUG] session_manager not found. Skipping CCTV pull-out verification.")
    except Exception as e:
        print(f"[CRITICAL BACKGROUND TASK ERROR] in trigger_cctv_pull_out_verification: {e}")
        import traceback
        traceback.print_exc()


# =================================================================
# 주차 정보 수정 (PUT)
# =================================================================

def convert_parking_spot(db: Session, user_id: int, request: schemas.EditSpotRequest):
    """차량의 주차면을 이동시킵니다."""
    parking = _get_parking_by_widget_id(db, request.widget_id)
          
    if is_spot_occupied(db, request.update_widget_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TARGET_SPOT_ALREADY_OCCUPIED")
              
    parking.widget_id = request.update_widget_id
    parking.update_by = user_id
    db.commit()

def edit_pull_out_at(db: Session, user_id: int, request: schemas.EditPullOutTimeRequest):
    """
    [수정] 예상 출차 시간을 수정하고, 관련 알림 스케줄을 업데이트합니다.
    """
    parking = _get_parking_by_widget_id(db, request.widget_id)
       
    # [수정] API로 받은 naive한 시간을 그대로 DB에 저장합니다.
    parking.pull_out_start_at = request.pull_out_start_at
    parking.pull_out_end_at = request.pull_out_end_at
       
    parking.update_by = user_id

    # 스케줄 업데이트 함수에는 naive한 시간이 담긴 parking 객체를 그대로 전달합니다.
    _create_or_update_pull_out_schedules(db, parking)
       
    db.commit()

def edit_parking(db: Session, user_id: int, request: schemas.EditParkingRequest):
    """
    주차 정보를 수정하고, 관련 알림 스케줄을 업데이트합니다.
    """
    from . import car_function # 함수 내에서 Import
    parking = _get_parking_by_widget_id(db, request.widget_id)
    car = car_function.get_car_by_id(db, request.car_id)

    parking.car_id = car.car_id
    parking.car_number = car.car_number
       
    # [수정] API로 받은 naive한 시간을 그대로 DB에 저장합니다.
    parking.pull_out_start_at = request.pull_out_start_at
    parking.pull_out_end_at = request.pull_out_end_at
       
    parking.update_by = user_id

    # 스케줄 업데이트
    _create_or_update_pull_out_schedules(db, parking)

    db.commit()

def convert_car_type(db: Session, user_id: int, request: schemas.EditCarTypeRequest):
    """
    입차된 차량의 타입을 변경하고, 관련 알림 스케줄을 업데이트합니다.
    """
    parking = _get_parking_by_widget_id(db, request.widget_id)
    parking.car_type = request.car_type

    # [수정] API로 받은 naive한 시간을 그대로 DB에 저장합니다.
    parking.pull_out_start_at = request.pull_out_start_at
    parking.pull_out_end_at = request.pull_out_end_at

    parking.update_by = user_id

    # 스케줄 업데이트
    _create_or_update_pull_out_schedules(db, parking)

    db.commit()

# =================================================================
# 주차/입차 처리 (POST)
# =================================================================

def manual_parking(db: Session, background_tasks: BackgroundTasks, user_id: int, request: schemas.ManualParkingRequest):
    """
    [수정] 수동으로 차량을 입차시키고, 알림 및 CCTV 검증을 안전한 백그라운드 작업으로 넘깁니다.
    """
    from . import car_function, notification_function # 함수 내에서 Import
       
    try:
        widget = _get_widget_by_id(db, request.widget_id)
        if is_spot_occupied(db, request.widget_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SPOT_ALREADY_OCCUPIED")

        car_id = request.car_id
        car_number = request.car_number

        if car_id:
            car = db.query(models.Car).filter(models.Car.car_id == car_id).first()
            if not car:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAR_NOT_FOUND")
            car_number = car.car_number
        elif car_number:
            car = car_function._get_or_create_car(db, user_id, car_number)
            car_id = car.car_id
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CAR_ID_OR_CAR_NUMBER_REQUIRED")

        existing_request = db.query(models.ParkingRequest).filter(
            models.ParkingRequest.parking_lot_id == request.parking_lot_id,
            models.ParkingRequest.car_id == car_id,
            models.ParkingRequest.request_status == models.RequestStatus.PENDING
        ).first()

        if existing_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ALREADY_PULL_IN_REQUESTED"
            )

        new_parking = models.Parking(
            widget_id=request.widget_id,
            car_id=car_id,
            car_number=car_number,
            car_type=request.car_type or models.CarType.UNREGISTERED,
            pull_in_at=datetime.now(KST),
            pull_out_start_at=request.pull_out_start_at,
            pull_out_end_at=request.pull_out_end_at,
            pull_in_auto_yn=models.YnType.N,
            create_by=user_id,
            update_by=user_id
        )
        db.add(new_parking)
        db.flush()   

        _create_or_update_pull_out_schedules(db, new_parking)

        db.commit()
        db.refresh(new_parking)

        # --- 백그라운드 작업 시작 ---
        # 1. 푸시 알림
        parking_lot_user_info = _get_parking_lot_user_info(db, user_id, widget.parking_lot_id)
        user_nickname = parking_lot_user_info.user_nickname if parking_lot_user_info else "사용자"
        pull_in_event = schemas.PullInPushEvent(
            user_id=user_id,
            parking_lot_id=widget.parking_lot_id,
            user_nickname=user_nickname,
            car_number=car_number
        )
        background_tasks.add_task(notification_function.handle_pull_in_event, pull_in_event)

        # 2. 정책 위반 확인
        # [수정] DB 세션을 전달하지 않습니다.
        background_tasks.add_task(_check_and_handle_policy_violations, widget.parking_lot_id, user_id)
           
        # 3. CCTV 백그라운드 검증
        if settings.CCTV_VERIFICATION_ENABLED and does_parking_lot_have_cctv(db, request.parking_lot_id):
            verification_request = models.ParkingRequest(
                parking_lot_id=request.parking_lot_id,
                car_id=new_parking.car_id,
                spot_widget_id=request.widget_id,
                car_number=new_parking.car_number,
                create_by=user_id,
                request_status=models.RequestStatus.PENDING,
                request_type=models.RequestType.PULL_IN,
                request_method=models.RequestMethod.MANUAL,
                parking_id=new_parking.parking_id
            )
            db.add(verification_request)
            db.commit()
            db.refresh(verification_request)
               
            background_tasks.add_task(trigger_cctv_verification, verification_request.request_id)
       
    except Exception as e:
        print(f"[MANUAL PARKING ERROR] An error occurred: {e}")
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))



def auto_parking(db: Session, user_id: int, request: schemas.AutoParkingRequest) -> schemas.AutoParkingRequestResponse:
    """자동 입차를 요청하고, 실제 처리는 백그라운드에서 수행합니다."""
    # 이미 PENDING 상태의 요청이 있는지 확인하여 중복 실행 방지
    existing_request = db.query(models.ParkingRequest).filter(
        models.ParkingRequest.parking_lot_id == request.parking_lot_id,
        models.ParkingRequest.car_id == request.car_id,
        models.ParkingRequest.request_status == models.RequestStatus.PENDING
    ).first()

    if existing_request:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ALREADY_PULL_IN_REQUESTED"
        )
       
    car = db.query(models.Car).filter(models.Car.car_id == request.car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR_NOT_FOUND")

    new_request = models.ParkingRequest(
        parking_lot_id=request.parking_lot_id,
        car_id=request.car_id,
        spot_widget_id=request.widget_id,
        car_number=car.car_number,
        create_by=user_id,
        request_status=models.RequestStatus.PENDING,
        request_type=models.RequestType.PULL_IN, # 주차 타입 명시
        request_method=models.RequestMethod.AUTO, # 자동 메소드 명시
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
       
    return new_request

# =================================================================
# 주차 정보 조회 (GET) - 변경 없음
# =================================================================

def find_parking_by_car(db: Session, parking_lot_id: int, car_number: str) -> Optional[schemas.ParkingByCarResponse]:
    """차량 번호로 주차 정보를 조회합니다."""
    parking = db.query(models.Parking).join(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.car_number == car_number,
        models.Parking.del_yn == models.YnType.N
    ).first()
          
    if not parking:
        return None
              
    return schemas.ParkingByCarResponse(
        parking_lot_id=parking.widget.parking_lot_id,
        widget_id=parking.widget.widget_id,
        widget_name=parking.widget.widget_name,
        car_number=parking.car_number
    )

def check_parking_request(db: Session, request_id: int) -> schemas.ParkingRequestStatusResponse:
    """입/출차 요청 상태를 조회합니다."""
    request = db.query(models.ParkingRequest).filter(models.ParkingRequest.request_id == request_id).first()
    if not request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REQUEST_NOT_FOUND")

    # 요청이 '입차'이고 '완료' 상태일 때만 주차 정보를 함께 반환
    if request.request_type == models.RequestType.PULL_IN and request.request_status == models.RequestStatus.COMPLETE:
        parking = db.query(models.Parking).join(models.Widget).filter(
            models.Widget.parking_lot_id == request.parking_lot_id,
            models.Parking.car_id == request.car_id,
            models.Parking.del_yn == models.YnType.N
        ).first()
        if parking:
            return schemas.ParkingRequestStatusResponse(
                parking_request_status=request.request_status,
                parking_id=parking.parking_id,
                parking_lot_id=request.parking_lot_id,
                widget_id=parking.widget_id,
                widget_name=parking.widget.widget_name,
                car_id=parking.car_id,
                car_number=parking.car_number,
                pull_out_start_at=parking.pull_out_start_at,
                pull_out_end_at=parking.pull_out_end_at
            )
                  
    return schemas.ParkingRequestStatusResponse(parking_request_status=request.request_status)

def get_user_pull_out_time(db: Session, user_id: int, parking_lot_id: int) -> schemas.PullOutTimeResponse:
    """사용자의 고정 출차 시간을 조회합니다."""
    user_info = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.parking_lot_id == parking_lot_id
    ).first()
    if not user_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_USER_IN_THE_PARKING_LOT")
              
    return schemas.PullOutTimeResponse(
        pull_out_start_at=user_info.pull_out_start_time,
        pull_out_end_at=user_info.pull_out_end_time
    )

def find_parking_list_by(db: Session, parking_lot_id: int) -> List[schemas.ParkingResponse]:
    """주차장의 모든 주차 정보를 조회합니다."""
    from . import user_function # 함수 내에서 Import
    parkings = db.query(models.Parking).join(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.del_yn == models.YnType.N
    ).options(
        joinedload(models.Parking.car),     # 기존 기능을 위해 유지
        joinedload(models.Parking.widget)   # widget_name을 위해 추가
    ).all()
          
    response_list = []
    for p in parkings:
        user_info = user_function.get_user_info_for_parking(db, p.create_by, parking_lot_id)
        response_list.append(schemas.ParkingResponse(
            widget_id=p.widget_id,
            widget_name=p.widget.widget_name,
            parking_id=p.parking_id,
            parking_user_id=p.create_by,
            user_nickname=user_info.get("nickname"),
            user_phone_secret_yn=user_info.get("phone_secret_yn"),
            user_phone=user_info.get("phone"),
            car_id=p.car_id,
            car_number=p.car_number,
            car_type=p.car_type,
            pull_in_at=p.pull_in_at,
            pull_out_start_at=p.pull_out_start_at,
            pull_out_end_at=p.pull_out_end_at
        ))
    return response_list

def find_last_parking(db: Session, user_id: int) -> Optional[schemas.LatestParkingResponse]:
    """사용자의 마지막 주차 기록을 조회합니다."""
    last_history = db.query(models.ParkingHistory).filter(
        models.ParkingHistory.user_id == user_id
    ).order_by(models.ParkingHistory.pull_out_at.desc()).first()
          
    if not last_history:
        return None
              
    widget = _get_widget_by_id(db, last_history.widget_id)
    parking_lot = _get_parking_lot_by_id(db, widget.parking_lot_id)
          
    return schemas.LatestParkingResponse(
        parking_lot_id=parking_lot.parking_lot_id,
        parking_lot_name=parking_lot.parking_lot_name,
        widget_id=widget.widget_id,
        widget_name=widget.widget_name,
        car_id=last_history.car_id,
        car_number=last_history.car_number
    )

def is_parking(db: Session, parking_lot_id: int, car_id: int) -> schemas.ParkingStatusResponse:
    """특정 차량이 주차장에 주차되어 있는지 확인합니다."""
    is_parked = db.query(models.Parking).join(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.car_id == car_id,
        models.Parking.del_yn == models.YnType.N
    ).first() is not None
          
    return schemas.ParkingStatusResponse(
        car_id=car_id,
        parking_yn=models.YnType.Y if is_parked else models.YnType.N
    )

def is_parking_by_car_id_list(db: Session, car_id_list: List[int]) -> List[schemas.ParkingStatusResponse]:
    """여러 차량의 주차 상태를 한 번에 조회합니다."""
    parked_car_ids = {
        res[0] for res in db.query(models.Parking.car_id).filter(
            models.Parking.car_id.in_(car_id_list),
            models.Parking.del_yn == models.YnType.N
        ).all()
    }
          
    return [
        schemas.ParkingStatusResponse(
            car_id=car_id,
            parking_yn=models.YnType.Y if car_id in parked_car_ids else models.YnType.N
        ) for car_id in car_id_list
    ]

# =================================================================
# 출차 처리 (DELETE)
# =================================================================

def manual_pull_out(db: Session, background_tasks: BackgroundTasks, user_id: int, request: schemas.ManualPullOutRequest):
    """
    [수정] 수동으로 차량을 출차시키고, 알림을 보낸 뒤, 백그라운드에서 CCTV 검증을 요청합니다.
    """
    from . import notification_function # 함수 내부에서 import (지연 Import)
       
    try:
        # 1. 주차 정보를 조회합니다.
        parking = _get_parking_by_widget_id(db, request.widget_id)
        parking_lot_user_info = _get_parking_lot_user_info(db, parking.create_by, parking.widget.parking_lot_id)
        user_nickname = parking_lot_user_info.user_nickname if parking_lot_user_info else "사용자"

        # 2. 푸시 알림 이벤트를 생성하고 백그라운드 작업으로 등록합니다. (푸시 선행)
        pull_out_event = schemas.PullOutPushEvent(
            user_id=parking.create_by,
            parking_lot_id=parking.widget.parking_lot_id,
            user_nickname=user_nickname,
            car_number=parking.car_number
        )
        background_tasks.add_task(
            notification_function.handle_pull_out_event,
            pull_out_event
        )

        # 3. DB에서 출차 처리를 먼저 수행합니다.
        _move_to_history(db, parking, user_id, is_auto=False)
           
        # 4. CCTV 연동이 활성화된 경우, 백그라운드 검증을 위한 요청을 생성합니다.
        if settings.CCTV_VERIFICATION_ENABLED and does_parking_lot_have_cctv(db, request.parking_lot_id):
            verification_request = models.ParkingRequest(
                parking_lot_id=request.parking_lot_id,
                car_id=parking.car_id,
                spot_widget_id=request.widget_id,
                car_number=parking.car_number,
                create_by=user_id,
                request_status=models.RequestStatus.PENDING,
                request_type=models.RequestType.PULL_OUT,
                request_method=models.RequestMethod.MANUAL,
                parking_id=parking.parking_id   
            )
            db.add(verification_request)
            db.flush() # request_id를 얻기 위해 flush
               
            # 5. 백그라운드 태스크로 TCP 검증 요청을 보냅니다.
            background_tasks.add_task(trigger_cctv_pull_out_verification, verification_request.request_id)
           
        db.commit()

    except Exception as e:
        print(f"[MANUAL PULL-OUT ERROR] An error occurred: {e}")
        traceback.print_exc()
        if isinstance(e, HTTPException):
            raise e
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def auto_pull_out(db: Session, user_id: int, request: schemas.AutoPullOutRequest) -> schemas.AutoParkingRequestResponse:
    """
    [신규] 자동 출차를 '요청'하고, 실제 처리는 백그라운드 흐름 제어 함수를 통해 수행합니다.
    """
    parking = _get_parking_by_widget_id(db, request.widget_id)

    # 이미 PENDING 상태의 '출차' 요청이 있는지 확인하여 중복 실행 방지
    existing_request = db.query(models.ParkingRequest).filter(
        models.ParkingRequest.spot_widget_id == request.widget_id,
        models.ParkingRequest.request_type == models.RequestType.PULL_OUT,
        models.ParkingRequest.request_status == models.RequestStatus.PENDING
    ).first()

    if existing_request:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ALREADY_PULL_OUT_REQUESTED"
        )

    # 새로운 '출차' 요청 생성
    new_request = models.ParkingRequest(
        parking_lot_id=request.parking_lot_id,
        car_id=parking.car_id,
        spot_widget_id=request.widget_id,
        car_number=parking.car_number,
        create_by=user_id,
        request_status=models.RequestStatus.PENDING,
        request_type=models.RequestType.PULL_OUT,
        request_method=models.RequestMethod.AUTO,
        parking_id=parking.parking_id
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
       
    return new_request

def remove_all_parking_in_lot(db: Session, user_id: int, parking_lot_id: int):
    """주차장의 모든 주차 기록을 삭제(출차) 처리합니다."""
    parkings = db.query(models.Parking).join(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.del_yn == models.YnType.N
    ).all()
          
    for parking in parkings:
        _move_to_history(db, parking, user_id, is_auto=False)

def remove_all_user_parking_history(db: Session, user_id: int):
    """회원 탈퇴 시 모든 주차 기록에서 해당 유저의 ID를 제거(업데이트)합니다."""
    db.query(models.ParkingHistory).filter(
        models.ParkingHistory.user_id == user_id
    ).update({"user_id": 0}, synchronize_session=False)
          
    db.query(models.Parking).filter(
        models.Parking.create_by == user_id
    ).update({"create_by": 0}, synchronize_session=False)

    db.commit()

# =================================================================
# 백그라운드 처리 함수
# =================================================================

def find_available_spot(db: Session, parking_lot_id: int, requested_spot_id: int = None) -> models.Widget:
    """주차 가능한 공간(위젯)을 찾습니다."""
    if requested_spot_id:
        spot = db.query(models.Widget).filter(
            models.Widget.widget_id == requested_spot_id,
            models.Widget.parking_lot_id == parking_lot_id,
            models.Widget.del_yn == models.YnType.N
        ).first()
              
        if not spot:
            raise Exception("REQUESTED_SPOT_NOT_FOUND")
              
        is_parked = db.query(models.Parking).filter(
            models.Parking.widget_id == requested_spot_id,
            models.Parking.del_yn == models.YnType.N
        ).first()

        if is_parked:
            raise Exception("REQUESTED_SPOT_ALREADY_PARKED")
                  
        return spot
    else:
        parking_spot_category_ids = [1, 2]
        parked_widget_ids = db.query(models.Parking.widget_id).filter(
            models.Parking.del_yn == models.YnType.N
        ).subquery()
        available_spot = db.query(models.Widget).filter(
            models.Widget.parking_lot_id == parking_lot_id,
            models.Widget.category_id.in_(parking_spot_category_ids),
            models.Widget.widget_id.notin_(parked_widget_ids),
            models.Widget.del_yn == models.YnType.N
        ).first()

        if not available_spot:
            raise Exception("NO_AVAILABLE_SPOTS")
                  
        return available_spot

def process_parking_fallback(request_id: int):
    """
    [핵심 수정] CCTV 연동 실패/타임아웃 시 API 요청 데이터를 기반으로 입차를 처리하는 통합 Fallback 함수입니다.
    (기존 process_auto_parking_without_cctv에서 이름 변경)
    """
    db: Session = None
    try:
        db = SessionLocal()
        from . import notification_function
        print(f"[BG_TASK_DEBUG] Starting Fallback logic for request_id: {request_id}")
        parking_request = db.query(models.ParkingRequest).get(request_id)
        if not parking_request or parking_request.request_status != models.RequestStatus.PENDING:
            print(f"[BG_TASK_DEBUG] Fallback for {request_id} stopped: Request not found or already processed.")
            return

        # 요청이 '수동' 입차에서 온 것인지 '자동' 입차에서 온 것인지 확인합니다.
        if parking_request.request_method == models.RequestMethod.MANUAL:
            # 수동 입차의 경우, 이미 'manual_parking' 함수에서 주차 처리가 완료되었습니다.
            # 따라서 여기서는 CCTV 검증 요청의 상태만 '완료'로 변경하고 종료합니다.
            # 이렇게 하면 "REQUESTED_SPOT_ALREADY_PARKED" 에러가 발생하지 않습니다.
            print(f"[BG_TASK_DEBUG] Fallback for MANUAL request {request_id}. Marking request as complete.")
            parking_request.request_status = models.RequestStatus.COMPLETE
            db.commit()
            return # 여기서 함수를 종료합니다.

        # --- 아래 로직은 '자동' 입차 요청일 경우에만 실행됩니다. ---
        print(f"[BG_TASK_DEBUG] Fallback for AUTO request {request_id}. Proceeding with parking.")
        available_spot = find_available_spot(db, parking_request.parking_lot_id, parking_request.spot_widget_id)
           
        new_parking = models.Parking(
            widget_id=available_spot.widget_id,
            car_id=parking_request.car_id,
            car_number=parking_request.car_number,
            car_type=models.CarType.REGISTERED,
            pull_in_at=parking_request.create_at,
            pull_in_auto_yn=models.YnType.Y,
            create_by=parking_request.create_by,
            update_by=parking_request.create_by
        )
        db.add(new_parking)
        parking_request.request_status = models.RequestStatus.COMPLETE
        db.commit()
        print(f"[BG_TASK_DEBUG] Fallback for {request_id} successful. Parked at {available_spot.widget_id}")
           
        parking_lot_user_info = _get_parking_lot_user_info(db, parking_request.create_by, parking_request.parking_lot_id)
        user_nickname = parking_lot_user_info.user_nickname if parking_lot_user_info else "사용자"
           
        pull_in_event = schemas.PullInPushEvent(
            user_id=parking_request.create_by,
            parking_lot_id=parking_request.parking_lot_id,
            user_nickname=user_nickname,
            car_number=parking_request.car_number
        )
        notification_function.handle_pull_in_event(pull_in_event)
        _check_and_handle_policy_violations(parking_request.parking_lot_id, parking_request.create_by)

    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] in process_parking_fallback: {e}")
        traceback.print_exc()
        if db:
            db.rollback()
            try:
                # 에러 발생 시 요청 상태를 FAIL로 업데이트 시도
                parking_request = db.query(models.ParkingRequest).get(request_id)
                if parking_request and parking_request.request_status == models.RequestStatus.PENDING:
                    error_detail = str(e)
                    if "NO_AVAILABLE_SPOTS" in error_detail or "ALREADY_PARKED" in error_detail:
                         parking_request.request_status = models.RequestStatus.FULL
                    else:
                        parking_request.request_status = models.RequestStatus.FAIL
                    db.commit()
            except Exception as db_e:
                print(f"[BACKGROUND TASK DB ERROR] Could not update request status to FAIL: {db_e}")
                db.rollback()
    finally:
        if db:
            db.close()

def process_pull_out_fallback(request_id: int):
    """
    [핵심 수정] CCTV 연동 실패/타임아웃 시 API 요청 데이터를 기반으로 출차를 처리하는 통합 Fallback 함수입니다.
    (기존 process_auto_pull_out_without_cctv에서 이름 변경)
    """
    db: Session = None
    try:
        db = SessionLocal()
        from . import notification_function
        print(f"[BG_TASK_DEBUG] Starting Fallback auto-pull-out for request_id: {request_id}")
        parking_request = db.query(models.ParkingRequest).get(request_id)
        if not parking_request or parking_request.request_status != models.RequestStatus.PENDING:
            print(f"[BG_TASK_DEBUG] Fallback for pull-out {request_id} stopped: Request not found or already processed.")
            return

        parking = db.query(models.Parking).options(joinedload(models.Parking.widget)).filter(
            models.Parking.widget_id == parking_request.spot_widget_id,
            models.Parking.del_yn == models.YnType.N
        ).first()

        if not parking:
            print(f"[BG_TASK_DEBUG] Fallback for pull-out {request_id}: Parking info not found. Marking as FAIL.")
            parking_request.request_status = models.RequestStatus.FAIL
            db.commit()
            return

        parking_lot_user_info = _get_parking_lot_user_info(db, parking.create_by, parking.widget.parking_lot_id)
        user_nickname = parking_lot_user_info.user_nickname if parking_lot_user_info else "사용자"

        pull_out_event = schemas.PullOutPushEvent(
            user_id=parking.create_by,
            parking_lot_id=parking.widget.parking_lot_id,
            user_nickname=user_nickname,
            car_number=parking.car_number
        )

        _move_to_history(db, parking, parking_request.create_by, is_auto=True)
        parking_request.request_status = models.RequestStatus.COMPLETE
        db.commit()
        print(f"[BG_TASK_DEBUG] Fallback for pull-out {request_id} successful.")

        notification_function.handle_pull_out_event(pull_out_event)

    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] in process_pull_out_fallback: {e}")
        traceback.print_exc()
        if db:
            db.rollback()
    finally:
        if db:
            db.close()


def process_auto_parking_flow(request_id: int):
    """
    [백그라운드] 모든 자동 입차 요청의 흐름을 제어하는 중앙 처리 함수입니다.
    """
    db: Session = None
    cctv_triggered = False
    try:
        db = SessionLocal()
        from service.tcp_manager import session_manager
        print(f"[BG_TASK_DEBUG] Starting auto-parking flow for request_id: {request_id}")
        parking_request = db.query(models.ParkingRequest).get(request_id)
        if not parking_request:
            return

        if settings.CCTV_VERIFICATION_ENABLED and does_parking_lot_have_cctv(db, parking_request.parking_lot_id):
            if session_manager and session_manager.is_client_connected_for_request(db, request_id):
                print(f"[BG_TASK_DEBUG] CCTV verification is possible. Triggering TCP request for {request_id}.")
                # loop = asyncio.get_event_loop()
                # loop.create_task(session_manager.send_pull_in_request(request_id))
                asyncio.run(session_manager.send_pull_in_request(request_id))
                cctv_triggered = True
                return   
            else:
                print(f"[BG_TASK_DEBUG] CCTV client not connected. Proceeding with fallback for {request_id}.")
                   
    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] in process_auto_parking_flow: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()

    # CCTV 연동을 시도하지 않은 경우에만 Fallback을 실행합니다.
    # (연결 실패, 설정 비활성화 등)
    if not cctv_triggered:
        process_parking_fallback(request_id)

def process_auto_pull_out_flow(request_id: int):
    """
    [신규] [백그라운드] 모든 자동 출차 요청의 흐름을 제어하는 중앙 처리 함수입니다.
    """
    db: Session = None
    cctv_triggered = False
    try:
        db = SessionLocal()
        from service.tcp_manager import session_manager
        print(f"[BG_TASK_DEBUG] Starting auto-pull-out flow for request_id: {request_id}")
        parking_request = db.query(models.ParkingRequest).get(request_id)
        if not parking_request:
            return

        if settings.CCTV_VERIFICATION_ENABLED and does_parking_lot_have_cctv(db, parking_request.parking_lot_id):
            if session_manager and session_manager.is_client_connected_for_request(db, request_id):
                print(f"[BG_TASK_DEBUG] CCTV pull-out verification possible. Triggering TCP for {request_id}.")
                # loop = asyncio.get_event_loop()
                # loop.create_task(session_manager.send_pull_out_request(request_id))
                asyncio.run(session_manager.send_pull_out_request(request_id))
                cctv_triggered = True
                return   
            else:
                print(f"[BG_TASK_DEBUG] CCTV client not connected for pull-out. Proceeding with fallback for {request_id}.")
                   
    except Exception as e:
        print(f"[BACKGROUND TASK ERROR] in process_auto_pull_out_flow: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()

    # CCTV 연동을 시도하지 않은 경우에만 Fallback을 실행합니다.
    if not cctv_triggered:
        process_pull_out_fallback(request_id)


# =================================================================
# CCTV 동기화 처리 (신규)
# =================================================================

def sync_parking_status(db: Session, background_tasks: BackgroundTasks, request: schemas.ParkingSyncRequest):
    """
    CCTV가 감지한 주차 상태를 DB와 동기화하는 핵심 로직.
    """
    from . import notification_function # 지연 Import

    try:
        # 1. parkId(device_id)로 parking_lot_id 조회
        device = db.query(models.Device).filter(models.Device.device_id == request.parkId).first()
        if not device:
            print(f"[SYNC_ERROR] Device with ID {request.parkId} not found.")
            return

        parking_lot_id = device.parking_lot_id
        print(f"[SYNC_START] parkId: {request.parkId}, parkingLotId: {parking_lot_id}")

        # 2. 주차장 관리자 ID 조회 (신규 차량 등록 및 출차 처리에 사용)
        admin_id = _get_admin_id_for_lot(db, parking_lot_id)
        if not admin_id:
            print(f"[SYNC_ERROR] No admin user found for parking lot {parking_lot_id}. Aborting sync.")
            return

        # [수정] 3. DB 주차 상태 조회 로직을 2단계로 분리하여 명확성 확보
        # 3-1. 먼저, 해당 주차장에 속한 모든 위젯 ID 목록을 조회합니다.
        widget_ids_in_lot = db.query(models.Widget.widget_id).filter(
            models.Widget.parking_lot_id == parking_lot_id
        ).scalar_subquery()

        # 3-2. 위에서 찾은 위젯 ID 목록을 사용하여, 정확히 해당 주차장의 주차 정보만 조회합니다.
        db_parkings = db.query(models.Parking).options(joinedload(models.Parking.widget)).filter(
            models.Parking.widget_id.in_(widget_ids_in_lot),
            models.Parking.del_yn == models.YnType.N
        ).all()
        # [개선] DB 데이터를 차량 번호와 위젯 ID, 두 가지 방식으로 조회할 수 있도록 맵을 만듭니다.
        db_cars_by_number = {p.car_number: p for p in db_parkings}
        db_cars_by_widget = {p.widget_id: p for p in db_parkings}


        # [신규] 4. 주차장에 등록된 모든 차량 번호 조회 (필터 1)
        registered_cars_query = db.query(models.Car.car_number).join(
            models.ParkingLotCar, models.ParkingLotCar.car_id == models.Car.car_id
        ).filter(
            models.ParkingLotCar.parking_lot_id == parking_lot_id, 
            models.ParkingLotCar.del_yn == models.YnType.N
        )
        registered_car_numbers_set = {car[0] for car in registered_cars_query.all()}


        # [수정] 5. CCTV 데이터를 '위젯 ID' 중심의 맵으로 변경하여, '미인식 차량' 정보도 유지합니다.
        cctv_spots_map = {
            car.surfaceId: car.carNo
            for car in request.cars
            if car.surfaceId and car.surfaceId > 0
        }
        print(f"[SYNC_INFO] DB Cars: {len(db_cars_by_number)}, CCTV Spots: {len(cctv_spots_map)}, Registered Cars for Lot: {len(registered_car_numbers_set)}")
        print(f"[SYNC_INFO] Received CCTV Data: {cctv_spots_map}")

        # [수정] 6. 처리 순서 문제를 해결하기 위해 '계획'과 '실행' 단계로 분리
        
        # 6-1. [계획 단계] 수행할 작업을 미리 식별하여 목록에 저장 (로직 개선)
        actions_to_move = []        # 위치를 이동해야 할 차량 정보
        actions_to_create = []      # 새로 입차 처리할 미등록 차량 정보
        
        cctv_identified_cars = {}   # CCTV에서 식별된 차량 (차량번호 -> 위젯ID)
        db_cars_found_in_cctv = set() # CCTV에서 발견된 DB 차량의 실제 번호 (이동 포함)

        # [개선] 계획 단계 1: CCTV 데이터를 순회하며 '이동'과 '신규' 가능성을 탐지
        for widget_id, ocr_car_no in cctv_spots_map.items():
            # [Case A: 인식 성공 차량]
            if ocr_car_no: 
                cctv_identified_cars[ocr_car_no] = widget_id
                matched_parking_info = _find_closest_match_in_parked(ocr_car_no, db_cars_by_number)

                if matched_parking_info:
                    db_cars_found_in_cctv.add(matched_parking_info.car_number)
                    # 위치가 변경되었다면 '이동' 작업으로 추가
                    if matched_parking_info.widget_id != widget_id:
                        actions_to_move.append({
                            "parking_info": matched_parking_info,
                            "new_widget_id": widget_id,
                            "ocr_car_no": ocr_car_no
                        })
            
            # [Case B: 미인식 차량 또는 DB에 없는 신규 차량]
            # 해당 자리에 원래 주차된 차가 있는지 확인
            original_car = db_cars_by_widget.get(widget_id)
            
            # 원래 차가 없었거나, 있었더라도 다른 번호의 차가 인식된 경우 -> '신규 입차' 후보
            if not original_car or (ocr_car_no and original_car.car_number != ocr_car_no):
                # 단, 인식된 번호가 다른 곳에 주차된 차의 번호와 같다면 '이동'이므로 여기서 처리하지 않음
                if ocr_car_no and _find_closest_match_in_parked(ocr_car_no, db_cars_by_number):
                    continue

                # '주차장에 등록된 전체 차량 목록'과도 유사도 검사를 하여 유령 차량인지 최종 판단
                if ocr_car_no and _is_fuzzy_match_in_set(ocr_car_no, registered_car_numbers_set):
                    print(f"[SYNC_INFO] Registered car {ocr_car_no} newly detected. As per requirements, taking no action.")
                    continue
                
                # 최종적으로 새로운 차량으로 판단되면 '생성' 작업으로 추가
                actions_to_create.append({
                    "car_no": ocr_car_no if ocr_car_no else f"미인식_{widget_id}",
                    "widget_id": widget_id
                })


        # 6-2. [실행 단계] 계획된 작업을 올바른 순서로 실행

        # [1순위] 출차 처리: CCTV에서 발견되지 않은 DB 차량들을 먼저 출차시켜 자리를 비움
        db_car_numbers_set = set(db_cars_by_number.keys())
        departed_car_numbers = db_car_numbers_set - db_cars_found_in_cctv

        for car_no in departed_car_numbers:
            parking_to_remove = db_cars_by_number[car_no]
            if not parking_to_remove.widget:
                 parking_to_remove.widget = db.query(models.Widget).get(parking_to_remove.widget_id)

            if parking_to_remove.widget.parking_lot_id == parking_lot_id:
                print(f"[SYNC_PULL_OUT] Car {car_no} in spot {parking_to_remove.widget_id} has departed.")
                _move_to_history(db, parking_to_remove, admin_id, is_auto=True)
            else:
                 print(f"[SYNC_CRITICAL_WARN] An attempt to remove car {car_no} from another parking lot ({parking_to_remove.widget.parking_lot_id}) was prevented.")

        # [2순위] 위치 보정 처리: 이제 빈자리가 확보되었을 수 있으므로 이동 작업을 수행
        for move_action in actions_to_move:
            parking_info = move_action["parking_info"]
            new_widget_id = move_action["new_widget_id"]
            ocr_car_no = move_action["ocr_car_no"]

            # 이동하려는 위치에 (출차 처리 후에도) 여전히 다른 차가 있는지 확인
            target_spot_parking = db_cars_by_widget.get(new_widget_id)

            # [핵심 수정] 목표 지점에 차가 있더라도, 그 차가 '출차 예정'이거나 '다른 곳으로 이동 예정'이라면 이동 허용
            is_target_spot_freeing_up = False
            if target_spot_parking:
                # 목표 지점의 차가 출차 목록에 있는지 확인
                is_departing = target_spot_parking.car_number in departed_car_numbers
                
                # 목표 지점의 차가 다른 이동 목록에 있는지 확인
                is_moving_away = any(
                    move["parking_info"].parking_id == target_spot_parking.parking_id
                    for move in actions_to_move
                )
                if is_departing or is_moving_away:
                    is_target_spot_freeing_up = True

            # 목표 지점이 비어있거나, 점유한 차가 자리를 비울 예정이라면 이동 실행
            if not target_spot_parking or is_target_spot_freeing_up:
                print(f"[SYNC_MOVE] Car {parking_info.car_number} (OCR: {ocr_car_no}) moved from {parking_info.widget_id} to {new_widget_id}.")
                parking_info.widget_id = new_widget_id
                parking_info.update_by = admin_id
                parking_info.update_at = datetime.now(KST)
            else:
                print(f"[SYNC_WARN] Cannot move car {parking_info.car_number}. Target spot {new_widget_id} is genuinely occupied by {target_spot_parking.car_number}.")
                continue


        # [3순위] 미등록 차량 신규 입차 처리
        for create_action in actions_to_create:
            car_no = create_action["car_no"]
            widget_id = create_action["widget_id"]
            
            # [개선] DB 재조회 대신 계획을 확인하여 해당 자리가 정말 비어있는지 최종 확인
            # 그 자리를 차지하고 있던 차가 출차 또는 이동 예정인지 확인
            original_car = db_cars_by_widget.get(widget_id)
            is_spot_now_free = True
            if original_car:
                 is_moving = any(move["parking_info"].parking_id == original_car.parking_id for move in actions_to_move)
                 is_departing = original_car.car_number in departed_car_numbers
                 if not (is_moving or is_departing):
                     is_spot_now_free = False
            
            if not is_spot_now_free:
                print(f"[SYNC_WARN] Target spot {widget_id} for new car {car_no} is still occupied by {original_car.car_number}. Skipping registration.")
                continue

            print(f"[SYNC_PULL_IN] Truly unregistered car {car_no} detected at spot {widget_id}.")
            # car = car_function._get_or_create_car(db, admin_id, car_no)
            
            new_parking = models.Parking(
                widget_id=widget_id,
                car_id=None,
                car_number=car_no,
                car_type=models.CarType.UNREGISTERED,
                pull_in_at=datetime.now(KST),
                pull_in_auto_yn=models.YnType.Y,
                create_by=admin_id,
                update_by=admin_id
            )
            db.add(new_parking)
            
            # 관리자에게 푸시 알림 (백그라운드)
            background_tasks.add_task(
                notification_function.handle_unregistered_car_event, 
                parking_lot_id, 
                car_no
            )
            print(f"[SYNC_NOTIFY] TODO: Send notification for unregistered car {car_no} to admin.")

        db.commit()
        print(f"[SYNC_COMPLETE] Synchronization finished for parking lot {parking_lot_id}.")

    except Exception as e:
        print(f"[SYNC_CRITICAL_ERROR] An unexpected error occurred during sync: {e}")
        traceback.print_exc()
        db.rollback()
