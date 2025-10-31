import logging
import re
from typing import List, Any, Dict
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
import asyncio

from core import models, schemas

# =================================================================
# 유틸리티 함수
# =================================================================

def extract_last_digits(car_no: str) -> str:
    """차량 번호 뒤의 3~4자리 숫자를 추출합니다."""
    if not car_no:
        return ""
    # 정규표현식을 사용하여 문자열 끝에서 3자리 또는 4자리의 숫자를 찾습니다.
    match = re.search(r'(\d{3,4})$', car_no)
    return match.group(1) if match else ""

# =================================================================
# 내부 헬퍼 함수 (신규)
# =================================================================

def _check_spot_status(db: Session, widget_id: int, request_car_id: int) -> tuple[str, models.Parking | None]:
    """
    주차면의 현재 상태를 확인합니다.
    - 'EMPTY': 비어있음
    - 'OCCUPIED_BY_SAME_CAR': 요청과 동일한 차량이 이미 주차되어 있음
    - 'OCC-UPIED_BY_ANOTHER_CAR': 다른 차량이 주차되어 있음
    """
    # 주어진 주차면(widget_id)에 현재 주차된(del_yn='N') 차량 정보를 조회합니다.
    existing_parking = db.query(models.Parking).options(joinedload(models.Parking.widget)).filter(
        models.Parking.widget_id == widget_id,
        models.Parking.del_yn == models.YnType.N
    ).first()

    # 주차된 차량이 없으면 'EMPTY' 상태를 반환합니다.
    if not existing_parking:
        return 'EMPTY', None
    
    # 주차된 차량의 ID가 현재 요청된 차량의 ID와 같으면 'OCCUPIED_BY_SAME_CAR'를 반환합니다.
    if existing_parking.car_id == request_car_id:
        return 'OCCUPIED_BY_SAME_CAR', existing_parking
        
    # 위 두 경우가 아니면 다른 차량이 주차된 것이므로 'OCCUPIED_BY_ANOTHER_CAR'를 반환합니다.
    return 'OCCUPIED_BY_ANOTHER_CAR', existing_parking

# [신규] 특정 주차장의 관리자 user_id를 찾는 함수
def _get_admin_user_id(db: Session, parking_lot_id: int) -> int | None:
    """주어진 주차장의 첫 번째 관리자(ADMIN)의 user_id를 반환합니다."""
    # 주기적 동기화 시 미등록 차량의 소유주를 지정하기 위해 사용됩니다.
    admin = db.query(models.ParkingLotUser.user_id).filter(
        models.ParkingLotUser.parking_lot_id == parking_lot_id,
        models.ParkingLotUser.user_role == models.UserRole.ADMIN,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).first()
    return admin.user_id if admin else None

# =================================================================
# 비즈니스 로직 (DB 처리 및 외부 연동)
# =================================================================

def validate_device_and_get_lot_id(db: Session, device_id: int) -> int | None:
    """
    클라이언트가 보낸 device_id가 DB의 devices 테이블에 등록되어 있는지 확인합니다.
    성공하면 해당 장비가 할당된 parking_lot_id를 반환하고, 실패하면 None을 반환합니다.
    """
    # LPR 클라이언트(미니 PC) 인증의 첫 단계입니다.
    device = db.query(models.Device).filter(models.Device.device_id == device_id).first()
    
    if device:
        # 장비가 존재하면, 장비가 속한 주차장 ID를 반환
        return device.parking_lot_id
    else:
        # 등록되지 않은 장비이면 None 반환
        return None

def update_cctv_info(db: Session, device_id: int, camera_list: List[Dict[str, Any]]):
    """DB에 CCTV 정보를 업데이트(삭제 후 추가)합니다."""
    # LPR 클라이언트가 시작될 때마다 config.json의 최신 카메라 정보를 DB에 동기화합니다.
    if not device_id:
        logging.error(f"Cannot update CCTV info, device_id is missing.")
        return

    try:
        # 기존에 등록된 해당 장비의 모든 CCTV 정보를 삭제합니다.
        db.query(models.Cctv).filter(models.Cctv.device_id == device_id).delete(synchronize_session=False)
        
        # 클라이언트가 보내준 목록으로 새로운 CCTV 정보를 추가합니다.
        for camera in camera_list:
            new_cctv = models.Cctv(
                device_id=device_id,
                cctv_id=camera.get("cameraId"),
                cctv_ip=camera.get("cameraIp")
            )
            db.add(new_cctv)
        db.commit()
        logging.info(f"CCTV info updated for device_id {device_id} with {len(camera_list)} cameras.")
    except Exception as e:
        db.rollback()
        logging.error(f"Error updating CCTV info for device_id {device_id}: {e}")


def process_lpr_parking_event(db: Session, parking_request: models.ParkingRequest, lpr_message: dict) -> bool:
    """
    [수정] LPR 이벤트를 기반으로 주차 처리 로직을 수행하며, 상태를 세분화하여 처리합니다.
    """
    detect_widget_id = lpr_message.get("surfaceId")
    if not detect_widget_id:
        logging.error(f"LPR message for request {parking_request.request_id} is missing 'surfaceId'.")
        parking_request.request_status = models.RequestStatus.FAIL
        db.commit()
        return False

    # --- 수동 입차 후 CCTV 검증 요청 처리 ---
    if parking_request.request_method == models.RequestMethod.MANUAL:
        # 이 요청은 이미 생성된 Parking 레코드를 검증/보정하는 것이 목적입니다.
        existing_parking = db.query(models.Parking).get(parking_request.parking_id)
        if not existing_parking:
            parking_request.request_status = models.RequestStatus.FAIL
            db.commit()
            return False

        # 사용자가 앱에서 지정한 위치와 CCTV가 실제 감지한 위치가 다르면, DB 기록을 보정합니다.
        if existing_parking.widget_id != detect_widget_id:
            logging.info(f"Correcting parking spot for parking_id {existing_parking.parking_id} "
                         f"from {existing_parking.widget_id} to {detect_widget_id}")
            existing_parking.widget_id = detect_widget_id
        
        parking_request.request_status = models.RequestStatus.COMPLETE
        db.commit()
        # '수동 입차'는 이미 API 호출 시점에 알림을 보냈으므로, 여기서는 추가 알림을 보내지 않습니다.
        return False
    
    # --- 자동 입차 요청 처리 ---
    # 헬퍼 함수를 사용하여 주차면의 현재 상태를 명확하게 확인합니다.
    status, existing_parking = _check_spot_status(db, detect_widget_id, parking_request.car_id)

    # --- 상태에 따른 분기 처리 ---
    if status == 'OCCUPIED_BY_SAME_CAR':
        # 이미 동일한 차량이 올바른 위치에 주차되어 있는 경우입니다. (예: 사용자가 수동으로 위치 보정 후 자동 입차 요청)
        # 이 자동 입차 요청은 정상적으로 완료된 것으로 간주합니다.
        logging.info(f"Spot {detect_widget_id} is already correctly occupied by car {existing_parking.car_id}. Request {parking_request.request_id} is considered COMPLETE.")
        parking_request.request_status = models.RequestStatus.COMPLETE
        db.commit()
        # 이미 주차가 완료된 상태이므로, 새로운 알림을 보내지 않습니다.
        return False

    elif status == 'OCCUPIED_BY_ANOTHER_CAR':
        # CCTV가 감지한 위치에 이미 다른 차가 주차되어 있는 경우, 만차(FULL)로 처리합니다.
        logging.error(f"Auto-parking failed for request {parking_request.request_id}. "
                      f"Detected spot {detect_widget_id} is occupied by another car {existing_parking.car_id}.")
        parking_request.request_status = models.RequestStatus.FULL
        db.commit()
        return False

    elif status == 'EMPTY':
        # 주차면이 비어있는 가장 일반적인 경우, 정상적으로 주차를 처리합니다.
        try:
            new_parking = models.Parking(
                widget_id=detect_widget_id,
                car_id=parking_request.car_id,
                car_number=parking_request.car_number,
                car_type=models.CarType.REGISTERED, # 자동 입차는 등록 차량으로 간주
                pull_in_at=datetime.now(models.KST),
                pull_in_auto_yn=models.YnType.Y,
                create_by=parking_request.create_by,
                update_by=parking_request.create_by
            )
            db.add(new_parking)
            parking_request.request_status = models.RequestStatus.COMPLETE
            db.commit()
            logging.info(f"Successfully processed auto-parking for request {parking_request.request_id} "
                         f"at widget {detect_widget_id}.")
            # 이 경우에만 TCP 매니저에게 "푸시 알림을 보내라"고 True를 반환합니다.
            return True
        
        except Exception as e:
            logging.error(f"DB Error during auto-parking for request {parking_request.request_id}: {e}")
            db.rollback()
            parking_request.request_status = models.RequestStatus.FAIL
            db.commit()
            return False
            
    return False

async def send_pull_in_push_notification(event_data: schemas.PullInPushEvent):
    """입차 완료 시 푸시 알림을 보냅니다. (비동기 백그라운드 태스크용)"""
    from function import notification_function
    try:
        # 이 함수는 TCP 매니저에 의해 asyncio.create_task로 호출됩니다.
        # notification_function.handle_pull_in_event는 내부적으로 DB 세션을 생성하고 닫으므로 안전합니다.
        notification_function.handle_pull_in_event(event_data)
        logging.info(f"Successfully handled pull-in push for user {event_data.user_id}, car {event_data.car_number}")
    except Exception as e:
        logging.error(f"Error handling pull-in push event: {e}")

# [신규] LPR 클라이언트의 출차 검증 응답(cmd: 6)을 처리하는 함수
def process_lpr_pull_out_event(db: Session, parking_request: models.ParkingRequest, lpr_message: dict) -> bool:
    """
    CCTV의 출차 검증 보고(cmd: 6)를 바탕으로 최종 출차를 확정하거나 취소합니다.
    푸시 알림을 보내야 할 경우 True를 반환합니다.
    """
    is_present = lpr_message.get("isPresent")

    if is_present:
        # [시나리오 B: 출차 취소] CCTV가 확인해보니 차가 아직 주차면에 있습니다.
        logging.warning(f"Pull-out cancelled for request {parking_request.request_id}. Vehicle is still present.")
        parking_request.request_status = models.RequestStatus.FAIL
        db.commit()
        # 출차가 취소되었으므로 알림을 보내지 않습니다.
        return False
    else:
        # [시나리오 A: 출차 확정] CCTV가 확인해보니 차가 사라졌습니다.
        logging.info(f"Pull-out confirmed by CCTV for request {parking_request.request_id}.")
        
        # 요청 방식(자동/수동)에 따라 다른 후속 처리를 합니다.
        if parking_request.request_method == models.RequestMethod.AUTO:
            # '자동 출차'의 경우, 이 시점에서 실제 DB 출차 처리를 수행합니다.
            from . import parking_function # 순환 참조 방지를 위한 지연 Import
            parking = db.query(models.Parking).filter(
                models.Parking.widget_id == parking_request.spot_widget_id,
                models.Parking.del_yn == models.YnType.N # 아직 출차 처리되지 않은 건
            ).first()
            
            if parking:
                parking_function._move_to_history(db, parking, parking_request.create_by, is_auto=True)
            
            parking_request.request_status = models.RequestStatus.COMPLETE
            db.commit()
            # TCP 매니저에게 "출차 완료 푸시 알림을 보내라"고 True를 반환합니다.
            return True
        
        elif parking_request.request_method == models.RequestMethod.MANUAL:
            # '수동 출차'의 경우, DB 출차와 알림은 이미 API에서 처리했습니다.
            # 여기서는 CCTV 검증 요청의 상태만 완료로 변경하고 조용히 종료합니다.
            parking_request.request_status = models.RequestStatus.COMPLETE
            db.commit()
            # 추가 알림이 필요 없으므로 False를 반환합니다.
            return False

    return False


# 주기적 동기화 로직
def synchronize_parking_status(db: Session, device_id: int, cctv_car_list: List[Dict]) -> Dict:
    """주기적으로 LPR 클라이언트가 보내주는 전체 주차 현황과 DB를 동기화합니다."""
    from . import car_function # 순환 참조 방지를 위한 지연 Import

    # 1. 인증 및 기본 정보 조회
    parking_lot_id = validate_device_and_get_lot_id(db, device_id)
    if not parking_lot_id:
        logging.error(f"[Sync] Invalid device_id: {device_id}")
        return {"error": "Invalid device_id"}
    
    admin_user_id = _get_admin_user_id(db, parking_lot_id)
    if not admin_user_id:
        logging.error(f"[Sync] No admin found for parking_lot_id: {parking_lot_id}")
        return {"error": "Parking lot admin not found"}

    # 2. 데이터 준비
    # CCTV 스캔 결과: { 101: "12가3456", 102: "45나6789" } 형태의 딕셔너리로 변환 (효율적인 조회를 위해)
    cctv_status = {item['surfaceId']: item['carNo'] for item in cctv_car_list}
    
    # DB 현재 주차 현황: { 101: ParkingObject, 103: ParkingObject } 형태의 딕셔너리로 변환
    db_parkings = db.query(models.Parking).join(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.del_yn == 'N'
    ).all()
    db_status_by_widget = {p.widget_id: p for p in db_parkings}
    db_status_by_car_no = {p.car_number: p for p in db_parkings}

    # 변경 사항 카운트를 위한 변수
    newly_parked_count = 0
    position_corrected_count = 0
    
    # --- 3. 동기화 로직 실행 ---

    # (우선순위 1 & 2: 미등록 차량 검출 및 등록)
    for widget_id, car_no in cctv_status.items():
        # CCTV에는 차가 있는데, DB 장부(차량번호 기준)상에 아예 없는 경우 -> 미등록 신규 입차(유령 차량)
        if car_no not in db_status_by_car_no:
            # 안전장치: 해당 주차면에 DB상 다른 차가 있다고 되어있으면, 일단 처리하지 않음 (혼선 방지)
            if widget_id in db_status_by_widget:
                logging.warning(f"[Sync] Spot {widget_id} is occupied by another car in DB. Skipping ghost vehicle {car_no}.")
                continue

            logging.info(f"[Sync] Ghost vehicle detected: {car_no} at spot {widget_id}. Registering...")
            
            # 차량 정보가 없으면 '관리자' 소유로 새로 생성
            car = car_function._get_or_create_car(db, admin_user_id, car_no)
            
            new_parking = models.Parking(
                widget_id=widget_id,
                car_id=car.car_id,
                car_number=car_no,
                car_type=models.CarType.UNREGISTERED,
                pull_in_at=datetime.now(models.KST),
                pull_in_auto_yn=models.YnType.Y,
                create_by=admin_user_id,
                update_by=admin_user_id
            )
            db.add(new_parking)
            newly_parked_count += 1

    # 만약 새로 등록된 차량이 있다면, DB에 즉시 반영하여 이후 위치 보정 로직에 포함되도록 함
    if newly_parked_count > 0:
        db.flush()

    # (우선순위 3: 기존 차량 위치 보정)
    # DB에 있는 모든 차들을 기준으로, CCTV 스캔 결과와 위치가 다른 경우를 찾음
    for car_no, parking_info in db_status_by_car_no.items():
        # DB에 있는 차가 CCTV 스캔 결과에도 존재할 때
        if car_no in cctv_status.values():
            # CCTV가 감지한 실제 위치를 찾음
            actual_widget_id = next((wid for wid, cn in cctv_status.items() if cn == car_no), None)
            
            # DB에 기록된 위치와 실제 감지된 위치가 다른 경우
            if actual_widget_id and parking_info.widget_id != actual_widget_id:
                # 안전장치: 보정하려는 위치에 이미 다른 차가 DB에 등록되어 있는지 확인
                if actual_widget_id in db_status_by_widget and db_status_by_widget[actual_widget_id].car_number != car_no:
                     logging.warning(f"[Sync] Cannot correct position for {car_no}. Target spot {actual_widget_id} is already taken in DB.")
                else:
                    logging.info(f"[Sync] Position correction for {car_no}: from {parking_info.widget_id} to {actual_widget_id}")
                    parking_info.widget_id = actual_widget_id
                    parking_info.update_by = admin_user_id
                    position_corrected_count += 1
    
    # 모든 변경사항을 한 번에 DB에 최종 저장
    db.commit()

    # API 응답으로 처리 결과를 요약하여 반환
    summary = {
        "newlyParked": newly_parked_count,
        "positionCorrected": position_corrected_count
    }
    logging.info(f"[Sync] Synchronization complete for parking lot {parking_lot_id}. Summary: {summary}")
    return summary

