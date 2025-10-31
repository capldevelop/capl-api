# app/function/widget_function.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from typing import List

from core import models, schemas
from fastapi import HTTPException, status

def save_layout(db: Session, user_id: int, parking_lot_id: int, request: schemas.SaveLayoutRequest):
    """주차장 도면(위젯 레이아웃)을 저장합니다."""
    # 순환 참조 방지를 위해 함수 내에서 import
    from . import parking_lot_function, parking_function

    # 1. 레이아웃 크기 업데이트
    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    parking_lot.layout_width = request.layout_width
    parking_lot.layout_height = request.layout_height
    parking_lot.update_by = user_id
    
    # 2. 위젯 목록 업데이트 (추가/수정)
    new_widget_ids = set()
    for widget_info in request.widget_list:
        if widget_info.widget_id: # ID가 있으면 수정
            widget_to_update = db.query(models.Widget).filter(models.Widget.widget_id == widget_info.widget_id).first()
            if widget_to_update:
                widget_to_update.category_id = widget_info.category_id
                widget_to_update.grid_x = widget_info.grid_x
                widget_to_update.grid_y = widget_info.grid_y
                widget_to_update.width = widget_info.width
                widget_to_update.height = widget_info.height
                widget_to_update.widget_name = widget_info.widget_name
                widget_to_update.latitude = widget_info.latitude
                widget_to_update.longitude = widget_info.longitude
                widget_to_update.device_id = widget_info.device_id
                widget_to_update.cctv_id = widget_info.cctv_id
                widget_to_update.update_by = user_id
                new_widget_ids.add(widget_to_update.widget_id)
        else: # ID가 없으면 추가
            new_widget = models.Widget(
                parking_lot_id=parking_lot_id,
                category_id=widget_info.category_id,
                grid_x=widget_info.grid_x,
                grid_y=widget_info.grid_y,
                width=widget_info.width,
                height=widget_info.height,
                widget_name=widget_info.widget_name,
                latitude=widget_info.latitude,
                longitude=widget_info.longitude,
                device_id=widget_info.device_id,
                cctv_id=widget_info.cctv_id,
                create_by=user_id,
                update_by=user_id
            )
            db.add(new_widget)
            db.flush() # 새 위젯 ID를 얻기 위해 flush
            new_widget_ids.add(new_widget.widget_id)

    # 3. 삭제된 위젯 처리
    # 현재 DB에 있는 위젯 ID 목록
    current_widgets_in_db = db.query(models.Widget.widget_id).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Widget.del_yn == models.YnType.N
    ).all()
    current_widget_ids_in_db = {w_id for w_id, in current_widgets_in_db}
    
    # 삭제할 위젯 ID = (현재 DB에 있는 ID) - (요청으로 들어온 ID)
    widget_ids_to_delete = current_widget_ids_in_db - new_widget_ids

    if widget_ids_to_delete:
        widgets_to_delete = db.query(models.Widget).filter(
            models.Widget.widget_id.in_(widget_ids_to_delete)
        ).all()

        for widget in widgets_to_delete:
            if parking_function.is_spot_occupied(db, widget.widget_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Cannot delete widget '{widget.widget_name}' (ID: {widget.widget_id}) because it is occupied."
                )
            widget.del_yn = models.YnType.Y
            widget.update_by = user_id
        
    db.commit()

def get_layout(db: Session, parking_lot_id: int) -> schemas.LayoutResponse:
    """주차장 도면 정보를 조회합니다."""
    # 순환 참조 방지를 위해 함수 내에서 import
    from . import parking_lot_function
    
    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    widgets = db.query(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Widget.del_yn == models.YnType.N
    ).all()
    
    widget_list_schema = [schemas.Widget.model_validate(w) for w in widgets]
    
    return schemas.LayoutResponse(
        layout_width=parking_lot.layout_width,
        layout_height=parking_lot.layout_height,
        widget_list=widget_list_schema
    )

def get_available_layout(db: Session, parking_lot_id: int) -> schemas.LayoutResponse:
    """주차 가능한 위젯 목록을 포함한 도면 정보를 조회합니다."""
    # 순환 참조 방지를 위해 함수 내에서 import
    from . import parking_lot_function

    parking_lot = parking_lot_function._get_parking_lot_by_id(db, parking_lot_id)
    
    # 현재 주차된 위젯 ID 목록 조회 (수정된 부분)
    # Parking 모델과 Widget 모델을 조인하여 Widget의 parking_lot_id로 필터링합니다.
    occupied_widget_ids_query = db.query(models.Parking.widget_id).join(
        models.Widget, models.Parking.widget_id == models.Widget.widget_id
    ).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Parking.del_yn == models.YnType.N
    )
    occupied_widget_ids = {w_id for w_id, in occupied_widget_ids_query.all()}
    
    # 주차면 카테고리(ID=1 가정)이면서, 주차되지 않은 위젯만 필터링
    available_widgets = db.query(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Widget.del_yn == models.YnType.N,
        models.Widget.category_id.in_([1, 2, 3, 4]), # '주차면' 카테고리 ID가 1이라고 가정
        ~models.Widget.widget_id.in_(occupied_widget_ids)
    ).all()
    
    widget_list_schema = [schemas.Widget.model_validate(w) for w in available_widgets]
    
    return schemas.LayoutResponse(
        layout_width=parking_lot.layout_width,
        layout_height=parking_lot.layout_height,
        widget_list=widget_list_schema
    )

def remove_all_widgets_in_lot(db: Session, user_id: int, parking_lot_id: int):
    """주차장의 모든 위젯을 삭제합니다. (주차된 위젯이 있으면 실패)"""
    # 순환 참조 방지를 위해 함수 내에서 import
    from . import parking_function
    
    widgets = db.query(models.Widget).filter(
        models.Widget.parking_lot_id == parking_lot_id,
        models.Widget.del_yn == models.YnType.N
    ).all()
    
    for widget in widgets:
        if parking_function.is_spot_occupied(db, widget.widget_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Cannot delete all widgets because spot '{widget.widget_name}' (ID: {widget.widget_id}) is occupied."
            )
        widget.del_yn = models.YnType.Y
        widget.update_by = user_id
    # db.commit()
