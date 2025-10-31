# from fastapi import APIRouter, Depends, Query
# from sqlalchemy.orm import Session
# from typing import List

# from core.database import get_db
# from core import schemas
# from function import group_function, parking_lot_function
# from core.dependencies import get_current_user_id

# router = APIRouter(
#     prefix="/parking_lot_group",
#     tags=["Parking-Lot Group"]
# )

# @router.post("/", summary="주차장 그룹 생성", response_model=schemas.RootResponse[schemas.GroupResponse])
# def create_group(
#     request: schemas.CreateGroupRequest,
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 요청 Body에 담긴 parking_lot_id를 기준으로 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, request.creator_parking_lot_id)
    
#     group = group_function.create_group(db, user_id, request.creator_parking_lot_id, request)
#     return schemas.RootResponse.ok(schemas.GroupResponse.model_validate(group))

# @router.get("/list", summary="특정 주차장이 속한 그룹 및 멤버 목록 조회", response_model=schemas.RootResponse[List[schemas.MyGroupInfoResponse]])
# def get_my_groups(
#     parking_lot_id: int = Query(..., description="조회 기준이 되는 주차장 ID"),
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 쿼리 파라미터로 받은 parking_lot_id에 대한 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, parking_lot_id)
    
#     groups = group_function.get_my_groups(db, parking_lot_id)
#     return schemas.RootResponse.ok(groups)
    
# @router.post("/{group_id}/invite", summary="다른 주차장을 그룹에 초대", response_model=schemas.RootResponse)
# def invite_to_group(
#     group_id: int,
#     request: schemas.InviteToGroupRequest,
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 요청 Body에 담긴 inviter_parking_lot_id를 기준으로 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, request.inviter_parking_lot_id)

#     group_function.invite_to_group(db, user_id, request.inviter_parking_lot_id, group_id, request.target_parking_lot_id)
#     return schemas.RootResponse.ok(None)

# @router.get("/invitations", summary="받은 그룹 초대 목록 조회", response_model=schemas.RootResponse[List[schemas.GroupInvitationResponse]])
# def get_pending_invitations(
#     parking_lot_id: int = Query(..., description="초대 목록을 조회할 주차장 ID"),
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 쿼리 파라미터로 받은 parking_lot_id에 대한 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, parking_lot_id)
    
#     invitations = group_function.get_pending_invitations(db, parking_lot_id)
#     return schemas.RootResponse.ok(invitations)

# @router.post("/invite/{group_id}/accept", summary="그룹 초대 수락", response_model=schemas.RootResponse)
# def accept_invitation(
#     group_id: int,
#     request: schemas.HandleGroupInvitationRequest,
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 요청 Body에 담긴 parking_lot_id를 기준으로 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    
#     group_function.handle_invitation(db, user_id, request.parking_lot_id, group_id, accept=True)
#     return schemas.RootResponse.ok(None)

# @router.post("/invite/{group_id}/reject", summary="그룹 초대 거절", response_model=schemas.RootResponse)
# def reject_invitation(
#     group_id: int,
#     request: schemas.HandleGroupInvitationRequest,
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 요청 Body에 담긴 parking_lot_id를 기준으로 관리자 권한 확인
#     parking_lot_function.verify_admin_role(db, user_id, request.parking_lot_id)
    
#     group_function.handle_invitation(db, user_id, request.parking_lot_id, group_id, accept=False)
#     return schemas.RootResponse.ok(None)

# @router.get("/shared-list", summary="공유된 주차장 목록 조회", response_model=schemas.RootResponse[List[schemas.SharedParkingLotResponse]])
# def get_shared_parking_lots(
#     parking_lot_id: int = Query(..., description="조회 기준이 되는 나의 주차장 ID"),
#     user_id: int = Depends(get_current_user_id),
#     db: Session = Depends(get_db)
# ):
#     # 사용자가 해당 주차장의 멤버(또는 공유 멤버)인지 기본 권한 확인
#     parking_lot_function.verify_user_role(db, user_id, parking_lot_id)

#     shared_lots = group_function.get_shared_parking_lots(db, parking_lot_id)
#     return schemas.RootResponse.ok(shared_lots)

