# app/function/car_function.py
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi import HTTPException, status

from core import models, schemas
from core.exceptions import ApiException
from core.constants import ResponseCode

# =================================================================
# 내부 유틸리티 함수
# =================================================================

def _get_or_create_car(db: Session, user_id: int, car_number: str) -> models.Car:
    """차량 번호로 차량을 조회하고, 없으면 새로 생성합니다. 다른 사용자가 이미 등록한 차량인지 확인합니다."""
    # 차량 번호의 공백을 제거하여 중복 조회를 방지합니다.
    normalized_car_number = car_number.replace(" ", "")
    
    car = db.query(models.Car).filter(
        models.Car.car_number == normalized_car_number,
        models.Car.del_yn == models.YnType.N
    ).first()
    

    if car:
        # 차량이 존재할 경우, 다른 활성 사용자가 이미 등록했는지 확인합니다.
        existing_user_car = db.query(models.UserCar).filter(
            models.UserCar.car_id == car.car_id,
            models.UserCar.del_yn == models.YnType.N
        ).first()
        
        if existing_user_car and existing_user_car.user_id != user_id:
            # 다른 사용자에게 등록된 차량이라면 예외를 발생시킵니다.
            raise ApiException(ResponseCode.DUPLICATED_USERS_CAR)

    else:
        # 차량이 존재하지 않으면 새로 생성합니다.
        car = models.Car(
            car_number=normalized_car_number,
            create_by=user_id,
            update_by=user_id
        )
        db.add(car)
        db.commit()
        db.refresh(car)
        
    return car

# =================================================================
# 사용자-차량 관련 함수
# =================================================================

def get_car_by_id(db: Session, car_id: int) -> models.Car:
    """ID로 차량 정보를 조회합니다."""
    car = db.query(models.Car).filter(
        models.Car.car_id == car_id,
        models.Car.del_yn == models.YnType.N
    ).first()
    if not car:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAR_NOT_FOUND")
    return car


def add_car_to_user(db: Session, user_id: int, car_number: str):
    """사용자에게 차량을 등록합니다. (UserCar 테이블)"""
    car = _get_or_create_car(db, user_id, car_number)
    
    existing_user_car = db.query(models.UserCar).filter(
        models.UserCar.user_id == user_id,
        models.UserCar.car_id == car.car_id
    ).first()

    if existing_user_car:
        if existing_user_car.del_yn == models.YnType.N:
            # 현재 사용자가 이미 등록한 경우
            raise ApiException(ResponseCode.DUPLICATED_USERS_CAR)
        # 삭제되었던 차량이면 다시 활성화합니다.
        existing_user_car.del_yn = models.YnType.N
        existing_user_car.update_by = user_id
    else:
        # 새로 등록합니다.
        new_user_car = models.UserCar(
            user_id=user_id,
            car_id=car.car_id,
            create_by=user_id,
            update_by=user_id
        )
        db.add(new_user_car)
    db.commit()

def remove_car_from_user(db: Session, user_id: int, car_id: int):
    """
    사용자에게서 차량을 삭제하고, 관련된 주차장 등록 정보를 삭제합니다.
    다른 사용자와 연결되어 있지 않으면 차량 자체도 논리적으로 삭제합니다.
    """
    # TODO: parking_function에 주차 여부 확인 로직 구현 후 주석 해제
    # if parking_function.is_car_parking(db, car_id):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PARKING_EXISTS")

    # 1. UserCar 관계를 논리적으로 삭제합니다.
    user_car = db.query(models.UserCar).filter(
        models.UserCar.user_id == user_id,
        models.UserCar.car_id == car_id,
        models.UserCar.del_yn == models.YnType.N
    ).first()
    
    if not user_car:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CAR_NOT_FOUND_FOR_USER")

    user_car.del_yn = models.YnType.Y
    user_car.update_by = user_id

    # 2. 해당 사용자가 이 차량을 등록했던 모든 주차장에서 등록 정보를 논리적으로 삭제합니다.
    db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.car_id == car_id,
        models.ParkingLotCar.create_by == user_id
    ).update({"del_yn": models.YnType.Y, "update_by": user_id}, synchronize_session=False)

    # 3. "현재 사용자를 제외한" 다른 활성 사용자가 이 차량에 연결되어 있는지 확인합니다.
    other_user_exists = db.query(models.UserCar).filter(
        models.UserCar.car_id == car_id,
        models.UserCar.del_yn == models.YnType.N,
        models.UserCar.user_id != user_id  # <-- 수정된 부분
    ).first()

    # 4. 다른 활성 사용자가 없으면 cars 테이블의 차량 정보도 논리적으로 삭제합니다.
    if not other_user_exists:
        car_to_delete = db.query(models.Car).filter(models.Car.car_id == car_id).first()
        if car_to_delete:
            car_to_delete.del_yn = models.YnType.Y
            car_to_delete.update_by = user_id
    
    db.commit()


def get_user_car_list(db: Session, user_id: int) -> List[schemas.CarResponse]:
    """사용자의 모든 차량 목록을 조회합니다."""
    user_cars = db.query(models.Car).join(models.UserCar).filter(
        models.UserCar.user_id == user_id,
        models.UserCar.del_yn == models.YnType.N,
        models.Car.del_yn == models.YnType.N
    ).order_by(models.Car.car_id).all()
    return [schemas.CarResponse.model_validate(car) for car in user_cars]

# =================================================================
# 주차장-차량 관련 함수
# =================================================================

def add_car_to_parking_lot(db: Session, user_id: int, parking_lot_id: int, car_number: str):
    """사용자 차량 한 대를 특정 주차장에 등록합니다."""
    # 1. 차량 번호로 차량을 조회/생성합니다. (이 단계에서 다른 사용자의 중복 등록을 확인)
    car = _get_or_create_car(db, user_id, car_number)

    # 2. 해당 차량이 현재 사용자에게 등록되어 있는지 확인하고, 없으면 등록합니다.
    user_car = db.query(models.UserCar).filter(
        models.UserCar.user_id == user_id,
        models.UserCar.car_id == car.car_id
    ).first()

    if not user_car:
        # 사용자와 차량의 연결이 없으면 새로 생성
        new_user_car = models.UserCar(
            user_id=user_id,
            car_id=car.car_id,
            create_by=user_id,
            update_by=user_id
        )
        db.add(new_user_car)
    elif user_car.del_yn == models.YnType.Y:
        # 연결은 있지만 삭제된 상태면 복구
        user_car.del_yn = models.YnType.N
        user_car.update_by = user_id
    # 이미 활성 상태로 연결되어 있다면 아무것도 하지 않음 (오류 아님)

    # 3. 주차장에 차량을 등록합니다. (여기서 주차장 내 중복을 확인)
    existing_parking_car = db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.car_id == car.car_id,
        models.ParkingLotCar.create_by == user_id
    ).first()

    if existing_parking_car:
        if existing_parking_car.del_yn == models.YnType.N:
            # 이미 이 주차장에 등록된 차량이면 오류 발생
            raise ApiException(ResponseCode.REGISTERED_CAR)
        
        # 삭제된 상태면 복구
        existing_parking_car.del_yn = models.YnType.N
        existing_parking_car.update_by = user_id
    else:
        # 주차장에 새로 등록
        new_parking_car = models.ParkingLotCar(
            parking_lot_id=parking_lot_id,
            car_id=car.car_id,
            create_by=user_id,
            update_by=user_id
        )
        db.add(new_parking_car)
        
    db.commit()

def add_cars_to_parking_lot(db: Session, user_id: int, parking_lot_id: int, car_id_list: List[int]):
    """사용자의 여러 차량을 주차장에 한 번에 등록합니다."""
    for car_id in car_id_list:
        # 사용자의 차량이 맞는지 확인
        user_car = db.query(models.UserCar).filter(
            models.UserCar.user_id == user_id,
            models.UserCar.car_id == car_id,
            models.UserCar.del_yn == models.YnType.N
        ).first()
        if not user_car:
            continue # 사용자의 차량이 아니면 건너뜀

        existing_parking_car = db.query(models.ParkingLotCar).filter(
            models.ParkingLotCar.parking_lot_id == parking_lot_id,
            models.ParkingLotCar.car_id == car_id
        ).first()

        if existing_parking_car:
            if existing_parking_car.del_yn == models.YnType.Y:
                existing_parking_car.del_yn = models.YnType.N
                existing_parking_car.update_by = user_id
        else:
            new_parking_car = models.ParkingLotCar(
                parking_lot_id=parking_lot_id,
                car_id=car_id,
                create_by=user_id,
                update_by=user_id
            )
            db.add(new_parking_car)
    db.commit()

def update_user_cars_in_parking_lot(db: Session, user_id: int, parking_lot_id: int, car_id_list: Optional[List[int]]):
    """주차장에 등록된 사용자의 차량 목록을 업데이트합니다. (기존 목록과 비교하여 추가/삭제)"""
    if car_id_list is None:
        car_id_list = []
        
    # 1. 현재 주차장에 등록된 사용자의 차량 목록 조회
    current_cars_query = db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.create_by == user_id,
        models.ParkingLotCar.del_yn == models.YnType.N
    )
    current_car_ids = {car.car_id for car in current_cars_query.all()}
    new_car_ids = set(car_id_list)

    # 2. 삭제할 차량 처리 (현재 목록에는 있지만 새 목록에는 없는 차량)
    cars_to_delete = current_car_ids - new_car_ids
    if cars_to_delete:
        db.query(models.ParkingLotCar).filter(
            models.ParkingLotCar.parking_lot_id == parking_lot_id,
            models.ParkingLotCar.create_by == user_id,
            models.ParkingLotCar.car_id.in_(cars_to_delete)
        ).update({"del_yn": models.YnType.Y, "update_by": user_id}, synchronize_session=False)

    # 3. 추가할 차량 처리 (새 목록에는 있지만 현재 목록에는 없는 차량)
    cars_to_add = new_car_ids - current_car_ids
    add_cars_to_parking_lot(db, user_id, parking_lot_id, list(cars_to_add))
    
    db.commit()

def get_user_car_list_in_parking_lot(db: Session, user_id: int, parking_lot_id: int) -> List[schemas.CarResponse]:
    """특정 주차장에 등록된 사용자의 차량 목록을 조회합니다."""
    parking_lot_cars = db.query(models.Car).join(models.ParkingLotCar, models.Car.car_id == models.ParkingLotCar.car_id).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.create_by == user_id,
        models.ParkingLotCar.del_yn == models.YnType.N,
        models.Car.del_yn == models.YnType.N
    ).order_by(models.Car.car_id).all()
    return [schemas.CarResponse.model_validate(car) for car in parking_lot_cars]

def get_all_registered_cars_for_user(db: Session, user_id: int) -> List[schemas.CarResponse]:
    """사용자가 참여중인 모든 주차장에 등록한 차량 목록 전체를 중복 없이 조회합니다."""
    # 1. 사용자가 승인된 멤버로 있는 모든 주차장의 ID를 조회합니다.
    accepted_parking_lots_subquery = db.query(models.ParkingLotUser.parking_lot_id).filter(
        models.ParkingLotUser.user_id == user_id,
        models.ParkingLotUser.accept_yn == models.YnType.Y,
        models.ParkingLotUser.del_yn == models.YnType.N
    ).subquery()

    # 2. 해당 주차장들에서 사용자가 등록한 모든 차량을 중복 없이 조회합니다.
    cars = db.query(models.Car).join(models.ParkingLotCar).filter(
        models.ParkingLotCar.parking_lot_id.in_(accepted_parking_lots_subquery),
        models.ParkingLotCar.create_by == user_id,
        models.ParkingLotCar.del_yn == models.YnType.N,
        models.Car.del_yn == models.YnType.N
    ).distinct(models.Car.car_id).order_by(models.Car.car_id).all()
    
    return [schemas.CarResponse.model_validate(car) for car in cars]

def get_user_cars_in_parking_lot(db: Session, user_id: int, parking_lot_id: int) -> List[models.Car]:
    """[내부용] 특정 주차장에 등록된 사용자의 차량 모델 목록을 반환합니다."""
    return db.query(models.Car).join(models.ParkingLotCar, models.Car.car_id == models.ParkingLotCar.car_id).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.create_by == user_id,
        models.ParkingLotCar.del_yn == models.YnType.N,
        models.Car.del_yn == models.YnType.N
    ).all()

def remove_user_cars_from_parking_lot(db: Session, updater_id: int, parking_lot_id: int, target_user_id: int):
    """특정 사용자가 주차장에 등록한 모든 차량을 삭제 처리합니다."""
    db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id,
        models.ParkingLotCar.create_by == target_user_id
    ).update({"del_yn": models.YnType.Y, "update_by": updater_id}, synchronize_session=False)
    # db.commit()

def remove_all_cars_from_parking_lot(db: Session, updater_id: int, parking_lot_id: int):
    """주차장의 모든 차량 등록 정보를 삭제 처리합니다."""
    db.query(models.ParkingLotCar).filter(
        models.ParkingLotCar.parking_lot_id == parking_lot_id
    ).update({"del_yn": models.YnType.Y, "update_by": updater_id}, synchronize_session=False)
    # db.commit()

def remove_all_user_cars(db: Session, user_id: int):
    """회원 탈퇴 시 해당 유저가 등록한 모든 차량 정보를 논리적으로 삭제합니다."""
    # 1. UserCar 테이블에서 user_id와 일치하는 모든 car_id를 찾습니다.
    user_cars = db.query(models.UserCar).filter(models.UserCar.user_id == user_id).all()
    if not user_cars:
        return
        
    car_ids_to_check = [uc.car_id for uc in user_cars]
    
    # 2. UserCar 매핑 정보를 삭제합니다.
    db.query(models.UserCar).filter(models.UserCar.user_id == user_id).delete(synchronize_session=False)

    # 3. Car 매핑 정보를 삭제합니다.
    #    (방금 삭제한 user_id 외에 다른 user_id와 연결된 car_id가 없는 차량)
    
    # 삭제 대상이었던 차량들(car_ids_to_check) 중에서
    cars_to_delete_query = db.query(models.Car.car_id).filter(
        models.Car.car_id.in_(car_ids_to_check)
    ).except_(
        # UserCar 테이블에 아직 남아있는 car_id들을 제외
        db.query(models.UserCar.car_id)
    )
    
    car_ids_to_delete = [c.car_id for c in cars_to_delete_query.all()]

    if car_ids_to_delete:
        db.query(models.Car).filter(
            models.Car.car_id.in_(car_ids_to_delete)
        ).update({"del_yn": models.YnType.Y}, synchronize_session=False)

    db.commit()
