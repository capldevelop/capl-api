# from fastapi import HTTPException, status
# from sqlalchemy.orm import Session, joinedload
# from typing import List

# from core import models, schemas

# def _get_group_by_id(db: Session, group_id: int) -> models.ParkingLotGroup:
#     """ID로 그룹 정보를 조회하고 없으면 예외를 발생시킵니다."""
#     group = db.query(models.ParkingLotGroup).filter(
#         models.ParkingLotGroup.group_id == group_id,
#         models.ParkingLotGroup.del_yn == models.YnType.N
#     ).first()
#     if not group:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GROUP_NOT_FOUND")
#     return group

# def create_group(db: Session, user_id: int, creator_parking_lot_id: int, request: schemas.CreateGroupRequest) -> models.ParkingLotGroup:
#     """새로운 주차장 그룹을 생성합니다."""
#     # 그룹 생성
#     new_group = models.ParkingLotGroup(
#         group_name=request.group_name,
#         create_by=user_id,
#         update_by=user_id
#     )
#     db.add(new_group)
#     db.flush()

#     # 그룹을 생성한 주차장을 첫 멤버로 자동 추가 (수락 상태)
#     new_member = models.ParkingLotGroupMember(
#         group_id=new_group.group_id,
#         parking_lot_id=creator_parking_lot_id, # 생성자 주차장 ID 자동 등록
#         accept_yn=models.YnType.Y, # 생성자는 자동 수락
#         create_by=user_id,
#         update_by=user_id
#     )
#     db.add(new_member)
#     db.commit()
#     db.refresh(new_group)
#     return new_group

# def invite_to_group(db: Session, user_id: int, inviter_parking_lot_id: int, group_id: int, target_parking_lot_id: int):
#     """그룹에 다른 주차장을 초대합니다."""
#     _get_group_by_id(db, group_id)
    
#     # 초대하는 주차장이 해당 그룹의 멤버인지 확인
#     inviter_membership = db.query(models.ParkingLotGroupMember).filter_by(
#         group_id=group_id, parking_lot_id=inviter_parking_lot_id, accept_yn=models.YnType.Y
#     ).first()
#     if not inviter_membership:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="NOT_A_GROUP_MEMBER")

#     # 초대 대상 주차장이 이미 멤버이거나 초대 대기 중인지 확인
#     existing_member = db.query(models.ParkingLotGroupMember).filter_by(
#         group_id=group_id, parking_lot_id=target_parking_lot_id
#     ).first()
#     if existing_member:
#         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="ALREADY_MEMBER_OR_INVITED")
        
#     # 초대 생성
#     new_invitation = models.ParkingLotGroupMember(
#         group_id=group_id,
#         parking_lot_id=target_parking_lot_id,
#         accept_yn=models.YnType.N, # 초대 상태
#         create_by=user_id
#     )
#     db.add(new_invitation)
#     db.commit()

# def get_pending_invitations(db: Session, parking_lot_id: int) -> List[schemas.GroupInvitationResponse]:
#     """해당 주차장이 받은 그룹 초대 목록을 조회합니다."""
#     invitations = db.query(models.ParkingLotGroupMember).options(
#         joinedload(models.ParkingLotGroupMember.group)
#     ).filter(
#         models.ParkingLotGroupMember.parking_lot_id == parking_lot_id,
#         models.ParkingLotGroupMember.accept_yn == models.YnType.N
#     ).all()
    
#     response_list = []
#     for inv in invitations:
#         # 초대한 주차장 정보 조회
#         inviter_parking_lot_user = db.query(models.ParkingLotUser).filter_by(user_id=inv.create_by).first()
#         if inviter_parking_lot_user:
#             response_list.append(schemas.GroupInvitationResponse(
#                 groupId=inv.group_id,
#                 groupName=inv.group.group_name,
#                 invitingParkingLotId=inviter_parking_lot_user.parking_lot_id,
#                 invitingParkingLotName=inviter_parking_lot_user.parking_lot.parking_lot_name
#             ))
            
#     return response_list

# def handle_invitation(db: Session, user_id: int, parking_lot_id: int, group_id: int, accept: bool):
#     """그룹 초대를 수락하거나 거절합니다."""
#     invitation = db.query(models.ParkingLotGroupMember).filter_by(
#         group_id=group_id, parking_lot_id=parking_lot_id, accept_yn=models.YnType.N
#     ).first()

#     if not invitation:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="INVITATION_NOT_FOUND")

#     if accept:
#         invitation.accept_yn = models.YnType.Y
#         invitation.update_by = user_id
#         db.commit()
#     else:
#         db.delete(invitation)
#         db.commit()

# def get_shared_parking_lots(db: Session, parking_lot_id: int) -> List[schemas.SharedParkingLotResponse]:
#     """현재 주차장과 그룹으로 묶인 다른 모든 주차장 목록을 조회합니다."""
#     # 1. 현재 주차장이 속한 모든 그룹 ID 찾기
#     my_groups = db.query(models.ParkingLotGroupMember.group_id).filter(
#         models.ParkingLotGroupMember.parking_lot_id == parking_lot_id,
#         models.ParkingLotGroupMember.accept_yn == models.YnType.Y
#     ).all()
#     my_group_ids = [g.group_id for g in my_groups]

#     if not my_group_ids:
#         return []

#     # 2. 해당 그룹들에 속한 다른 모든 주차장 ID 찾기
#     shared_members = db.query(models.ParkingLotGroupMember).options(
#         joinedload(models.ParkingLotGroupMember.parking_lot)
#     ).filter(
#         models.ParkingLotGroupMember.group_id.in_(my_group_ids),
#         models.ParkingLotGroupMember.parking_lot_id != parking_lot_id, # 자기 자신은 제외
#         models.ParkingLotGroupMember.accept_yn == models.YnType.Y
#     ).all()
    
#     # 중복 제거 및 응답 객체 생성
#     shared_lots = {member.parking_lot_id: member.parking_lot for member in shared_members}
    
#     return [schemas.SharedParkingLotResponse.model_validate(lot) for lot in shared_lots.values()]

# def get_my_groups(db: Session, parking_lot_id: int) -> List[schemas.MyGroupInfoResponse]:
#     """현재 주차장이 속한 그룹 및 멤버 목록을 조회합니다."""
#     my_memberships = db.query(models.ParkingLotGroupMember).filter(
#         models.ParkingLotGroupMember.parking_lot_id == parking_lot_id,
#         models.ParkingLotGroupMember.accept_yn == models.YnType.Y
#     ).all()
#     my_group_ids = [m.group_id for m in my_memberships]

#     if not my_group_ids:
#         return []

#     all_members_in_my_groups = db.query(models.ParkingLotGroupMember).options(
#         joinedload(models.ParkingLotGroupMember.parking_lot),
#         joinedload(models.ParkingLotGroupMember.group)
#     ).filter(
#         models.ParkingLotGroupMember.group_id.in_(my_group_ids)
#     ).all()

#     groups_data = {}
#     for member in all_members_in_my_groups:
#         if member.group_id not in groups_data:
#             groups_data[member.group_id] = {
#                 "group_name": member.group.group_name,
#                 "members": []
#             }
#         groups_data[member.group_id]["members"].append(
#             schemas.MyGroupInfoResponse.GroupMemberInfo(
#                 parkingLotId=member.parking_lot_id,
#                 parkingLotName=member.parking_lot.parking_lot_name,
#                 acceptYn=member.accept_yn
#             )
#         )
    
#     return [
#         schemas.MyGroupInfoResponse(groupId=gid, groupName=data["group_name"], members=data["members"])
#         for gid, data in groups_data.items()
#     ]
