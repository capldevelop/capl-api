# app/models.py
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, Enum, Float, Time, func, DECIMAL, VARCHAR, BIGINT, CHAR, UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME # MySQL DATETIME(6)을 위해
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from .database import Base

import enum

# 한국 시간대(KST) 객체 정의
KST = ZoneInfo("Asia/Seoul")

# =================================================================
# Enums (모든 모델 클래스보다 먼저 정의해야 합니다)
# =================================================================
class YnType(str, enum.Enum):
    Y = "Y"
    N = "N"

class MessageType(str, enum.Enum):
    MESSAGE = "MESSAGE"
    FILE = "FILE"
    SYSTEM = "SYSTEM"
     
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class NotificationType(str, enum.Enum):
    # DB 컬럼에 값이 존재함
    CHAT = "CHAT" # 채팅 알림
    PARKING = "PARKING" # 주차 알림
    POLICY = "POLICY" # 주차장 정책 알림
    # DB 컬럼에 값이 존재 안 함
    # 백엔드 처리 시 구분하기 쉽게 추가함
    PULL_OUT = "PULL_OUT" # 출차 알림
    PULL_IN = "PULL_IN" # 가용 진입 알림
    PULL_OUT_START_TIME = "PULL_OUT_START_TIME" # 출차 시간 30분 전 알림
    PULL_OUT_END_TIME = "PULL_OUT_END_TIME" # 출차 시간 알림
    NOTICE = "NOTICE" # 공지
    VOTE = "VOTE" # 투표


class CarType(str, enum.Enum):
    REGISTERED = "REGISTERED"
    UNREGISTERED = "UNREGISTERED"
    VISITOR = "VISITOR"
     
class SocialType(str, enum.Enum):
    KAKAO = "KAKAO"
    GOOGLE = "GOOGLE"
    APPLE = "APPLE"
     
class RequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    FULL = "FULL"
    FAIL = "FAIL"

class TaskType(str, enum.Enum):
    # 투표 종료를 위한 타입
    VOTE_END_AT = "VOTE_END_AT"
    # 예정 출차 알림을 위한 타입
    PULL_OUT_BEFORE = "PULL_OUT_BEFORE"
    PULL_OUT_AFTER = "PULL_OUT_AFTER"
    # 고정 출차 알림을 위한 타입
    FIXED_PULL_OUT_BEFORE = "FIXED_PULL_OUT_BEFORE"
    FIXED_PULL_OUT_AFTER = "FIXED_PULL_OUT_AFTER"

class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    REQUESTED = "REQUESTED"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
     
class LoginDeviceType(str, enum.Enum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"
    
# [신규] ParkingRequest의 작업 종류를 정의하는 Enum
class RequestType(str, enum.Enum):
    PULL_IN = "PULL_IN"   # 입차
    PULL_OUT = "PULL_OUT" # 출차

# [신규] ParkingRequest의 요청 방식을 정의하는 Enum
class RequestMethod(str, enum.Enum):
    AUTO = "AUTO"     # 자동 (GPS 기반 등)
    MANUAL = "MANUAL" # 수동 (사용자 직접 입력)


### User ###
# UserEntity -> User 모델
class User(Base):
    __tablename__ = "users"

    user_id = Column(BIGINT, primary_key=True, index=True, name="user_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    user_name = Column(VARCHAR(32), nullable=False)
    user_phone = Column(VARCHAR(16), nullable=False)
    user_ci = Column(Text, unique=True, nullable=False)
    
    socials = relationship("UserSocial")

# UserSocialEntity -> UserSocial 모델 (복합 키)
class UserSocial(Base):
    __tablename__ = "user_socials"

    user_social_id = Column(VARCHAR(64), primary_key=True)
    social_type = Column(Enum(SocialType), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    user_id = Column(BIGINT, ForeignKey("users.user_id"), nullable=False)
    refresh_token = Column(Text)
    user_social_email = Column(VARCHAR(32))

    user = relationship("User", back_populates="socials")
### User ###

### Auth ###
class PhoneAuthTempUser(Base):
    __tablename__ = "phone_auth_temp_users"

    temp_user_id = Column(BIGINT, primary_key=True, index=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    expire_at = Column(MYSQL_DATETIME(fsp=6), nullable=False)
    temp_user_name = Column(VARCHAR(32), nullable=False)
    temp_user_phone = Column(VARCHAR(16), nullable=False)
    temp_user_ci = Column(Text, nullable=False)
### Auth ###


### Car ###
# CarEntity -> Car 모델
class Car(Base):
    __tablename__ = "cars"

    car_id = Column(BIGINT, primary_key=True, index=True, name="car_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    car_number = Column(VARCHAR(9), unique=True, nullable=False)
     
# UserCarEntity -> UserCar 모델 (복합 키)
class UserCar(Base):
    __tablename__ = "user_cars"

    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)
    car_id = Column(BIGINT, ForeignKey("cars.car_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)

    user = relationship("User")
    car = relationship("Car")
### Car ###

### Chat ###
# ChatEntity -> Chat 모델
class Chat(Base):
    __tablename__ = "chats"

    chat_id = Column(BIGINT, primary_key=True, index=True, name="chat_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
     
    # Java의 @ManyToOne parkingLotEntity에 해당
    parking_lot = relationship("ParkingLot")

# MessageEntity -> Message 모델
# 채팅 서버에 저장하지 않는 것으로 변경되어 사용 X
# class Message(Base):
#     __tablename__ = "chat_messages"

#     message_id = Column(Integer, primary_key=True, index=True, name="message_id")
#     chat_id = Column(Integer, ForeignKey("chats.chat_id"), nullable=False)
#     user_id = Column(Integer, nullable=False)
#     message_type = Column(Enum(MessageType), nullable=False)
#     content = Column(Text, nullable=True)
#     file_id = Column(Integer, ForeignKey("chat_messages_files.file_id"), nullable=True)
#     send_at = Column(DateTime, nullable=False, default=lambda: datetime.now(KST)) # create_at 역할

#     chat = relationship("Chat")
#     file = relationship("File")

# # FileEntity -> File 모델
# class File(Base):
#     __tablename__ = "chat_messages_files"

#     file_id = Column(Integer, primary_key=True, index=True, name="file_id")
#     origin_file_name = Column(String(255), nullable=False)
#     upload_file_name = Column(String(255), nullable=False)
#     expire_at = Column(DateTime, nullable=False)
#     create_by = Column(Integer, nullable=False)
#     create_at = Column(DateTime, nullable=False, default=lambda: datetime.now(KST))
### Chat ###


### Notification ###
# NotificationEntity -> Notification 모델
class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(BIGINT, primary_key=True, index=True, name="notification_id")
    notification_type = Column(Enum(NotificationType), nullable=False)
    notification_type_order = Column(Integer, nullable=False)
    notification_name = Column(VARCHAR(64), nullable=False)
    notification_description = Column(VARCHAR(512))
    notification_order = Column(Integer, nullable=False)
     

# NotificationSettingEntity -> NotificationSetting 모델
# 복합 기본 키(Composite Primary Key)를 사용합니다.
class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)
    notification_id = Column(BIGINT, ForeignKey("notifications.notification_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    active_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)
     
    # SQLAlchemy가 관계를 이해하도록 설정
    user = relationship("User")
    parking_lot = relationship("ParkingLot")
    notification = relationship("Notification")
### Notification ###

### Parking Lot ###
# ParkingLotEntity -> ParkingLot 모델
class ParkingLot(Base):
    __tablename__ = "parking_lots"

    parking_lot_id = Column(BIGINT, primary_key=True, index=True, name="parking_lot_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    parking_lot_name = Column(VARCHAR(20), nullable=False)
    parking_lot_address = Column(VARCHAR(64), nullable=False)
    parking_lot_address_detail = Column(VARCHAR(64))
    latitude = Column(DECIMAL(17, 14), nullable=False)
    longitude = Column(DECIMAL(17, 14), nullable=False)
    layout_width = Column(Integer)
    layout_height = Column(Integer)
    parking_lot_public = Column(Enum(YnType), nullable=False, default=YnType.N)
    
    # group_memberships = relationship("ParkingLotGroupMember", back_populates="parking_lot")

# ParkingLotUserEntity -> ParkingLotUser 모델 (복합 키)
class ParkingLotUser(Base):
    __tablename__ = "parking_lot_users"

    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    accept_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    user_nickname = Column(VARCHAR(20), nullable=False)
    user_role = Column(Enum(UserRole), nullable=False)
    phone_secret_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)
    pull_out_start_time = Column(Time)
    pull_out_end_time = Column(Time)
    pull_out_week = Column(CHAR(7))
    pull_out_time_yn = Column(Enum(YnType), default=YnType.Y)
    holiday_exclude_yn = Column(Enum(YnType), default=YnType.N)
    chat_join_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)
    user_address_detail = Column(VARCHAR(64))
    # last_read_message_id = Column(BIGINT) # 채팅 서버 미저장으로 인한 미사용 컬럼

    parking_lot = relationship("ParkingLot")
    user = relationship("User")

# ParkingLotCarEntity -> ParkingLotCar 모델 (복합 키)
class ParkingLotCar(Base):
    __tablename__ = "parking_lot_cars"

    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), primary_key=True)
    car_id = Column(BIGINT, ForeignKey("cars.car_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, primary_key=True) # 등록한 사용자 ID
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(Integer, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)

    parking_lot = relationship("ParkingLot")
    car = relationship("Car")
### Parking Lot ###



### Policy ###
class Policy(Base):
    __tablename__ = "parking_lot_policies"

    policy_id = Column(BIGINT, primary_key=True, index=True, name="policy_id")
    policy_name = Column(VARCHAR(64), nullable=False)
    policy_description = Column(VARCHAR(512))

# PolicySettingEntity -> PolicySetting 모델 (복합 키)
class PolicySetting(Base):
    __tablename__ = "policy_settings"

    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), primary_key=True)
    policy_id = Column(BIGINT, ForeignKey("parking_lot_policies.policy_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    active_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)

    parking_lot = relationship("ParkingLot")
    policy = relationship("Policy")
### Policy ###

### Parking ###
# ParkingEntity -> Parking 모델
class Parking(Base):
    __tablename__ = "parking"

    parking_id = Column(BIGINT, primary_key=True, index=True, name="parking_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    car_id = Column(BIGINT, ForeignKey("cars.car_id")) # 비회원 차량은 car_id가 없을 수 있음
    car_number = Column(VARCHAR(9), nullable=False)
    car_type = Column(Enum(CarType), nullable=False)
    pull_out_start_at = Column(MYSQL_DATETIME(fsp=6))
    pull_out_end_at = Column(MYSQL_DATETIME(fsp=6))
    pull_in_at = Column(MYSQL_DATETIME(fsp=6), nullable=False)
    pull_out_at = Column(MYSQL_DATETIME(fsp=6))
    pull_in_auto_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    widget_id = Column(BIGINT, ForeignKey("parking_lot_widgets.widget_id"), nullable=False, unique=True)

    widget = relationship("Widget")
    car = relationship("Car")

# ParkingHistoryEntity -> ParkingHistory 모델
class ParkingHistory(Base):
    __tablename__ = "parking_histories"

    parking_history_id = Column(BIGINT, primary_key=True, index=True, name="parking_history_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    user_id = Column(BIGINT)
    parking_lot_id = Column(BIGINT, nullable=False)
    car_id = Column(BIGINT)
    car_number = Column(VARCHAR(9), nullable=False)
    car_type = Column(Enum(CarType), nullable=False)
    pull_out_start_at = Column(MYSQL_DATETIME(fsp=6))
    pull_out_end_at = Column(MYSQL_DATETIME(fsp=6))
    pull_in_at = Column(MYSQL_DATETIME(fsp=6), nullable=False)
    pull_out_at = Column(MYSQL_DATETIME(fsp=6), nullable=False)
    pull_in_auto_yn = Column(Enum(YnType), nullable=False)
    pull_out_auto_yn = Column(Enum(YnType), nullable=False)
    widget_id = Column(BIGINT, nullable=False)


# ParkingRequestEntity -> ParkingRequest 모델
class ParkingRequest(Base):
    __tablename__ = "parking_requests"

    request_id = Column(BIGINT, primary_key=True, index=True, name="request_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    parking_lot_id = Column(BIGINT, nullable=False)
    spot_widget_id = Column(BIGINT)
    car_id = Column(BIGINT, nullable=False)
    car_number = Column(VARCHAR(9), nullable=False)
    request_status = Column(Enum(RequestStatus), nullable=False, default=RequestStatus.PENDING)
    
    # [추가] 'manual_verify_yn'을 더 명확한 두 개의 Enum 컬럼으로 대체합니다.
    request_type = Column(Enum(RequestType), nullable=False, default=RequestType.PULL_IN, comment="요청종류(입차/출차)")
    request_method = Column(Enum(RequestMethod), nullable=False, comment="요청방식(자동/수동)")
    
    # '수동 입차 후 검증' 시나리오를 위해 이 컬럼은 계속 필요합니다.
    # 수동 입차 API가 먼저 'parking' 테이블에 기록을 생성한 뒤,
    # 그 parking_id를 여기에 담아 백그라운드 검증을 요청하기 때문입니다.
    parking_id = Column(BIGINT, ForeignKey("parking.parking_id"), nullable=True)
    
### Parking ###


### Schedule ###
class Schedule(Base):
    # fcm 용으로 테이블 복제 및 교체
    __tablename__ = "fcm_schedules"

    task_id = Column(BIGINT, primary_key=True, index=True, name="task_id")
    execute_time = Column(MYSQL_DATETIME(fsp=6), nullable=False)
    task_type = Column(Enum(TaskType), nullable=False)
    type_id = Column(BIGINT, nullable=False)
    task_status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    user_id = Column(BIGINT, nullable=False)
    parking_lot_id = Column(BIGINT, nullable=False)
     
    # 복합 고유 키(UNIQUE KEY)
    __table_args__ = (
        UniqueConstraint('execute_time', 'task_type', 'type_id', 'user_id', 'parking_lot_id', name='fcm_schedules_unique_01'),
        {'comment': '스케줄등록정보'}
    )
### Schedule ###


### Login ###
# LoginInfoEntity -> LoginInfo 모델 (복합 키)
class LoginInfo(Base):
    __tablename__ = "login_infos"

    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)
    login_device_uuid = Column(CHAR(36), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    login_device_type = Column(Enum(LoginDeviceType), nullable=False)
    login_device_name = Column(VARCHAR(32), nullable=False)
    login_device_os = Column(VARCHAR(32), nullable=False)
    push_token = Column(Text)
    push_arn = Column(Text)
    refresh_token = Column(Text)

    user = relationship("User")

# LoginHistoryEntity -> LoginHistory 모델 (복합 키)
class LoginHistory(Base):
    __tablename__ = "login_histories"

    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)
    create_at = Column(MYSQL_DATETIME(fsp=6), primary_key=True, default=lambda: datetime.now(KST))
    result = Column(VARCHAR(10), nullable=False) # ResultType Enum으로 대체 가능
    login_device_uuid = Column(CHAR(36), nullable=False)
    login_device_type = Column(Enum(LoginDeviceType), nullable=False)
    login_device_name = Column(VARCHAR(32), nullable=False)
    login_device_os = Column(VARCHAR(32), nullable=False)

    user = relationship("User")
### Login ###


### Notice ###
# NoticeEntity -> Notice 모델
class Notice(Base):
    __tablename__ = "notices"

    notice_id = Column(BIGINT, primary_key=True, index=True, name="notice_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), nullable=False)
    notice_title = Column(VARCHAR(30), nullable=False)
    notice_content = Column(Text, nullable=False)

    parking_lot = relationship("ParkingLot")
### Notice ###


### Vote ###
# VoteEntity -> Vote 모델
class Vote(Base):
    __tablename__ = "votes"

    vote_id = Column(BIGINT, primary_key=True, index=True, name="vote_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), nullable=False)
    vote_title = Column(VARCHAR(30), nullable=False)
    active_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)
    multiple_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    anonymous_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    end_at = Column(MYSQL_DATETIME(fsp=6))

    parking_lot = relationship("ParkingLot")
    items = relationship("VoteItem", back_populates="vote")

# VoteItemEntity -> VoteItem 모델
class VoteItem(Base):
    __tablename__ = "vote_items"

    vote_item_id = Column(BIGINT, primary_key=True, index=True, name="vote_item_id")
    vote_id = Column(BIGINT, ForeignKey("votes.vote_id"), nullable=False)
    content = Column(VARCHAR(15), nullable=False)

    vote = relationship("Vote", back_populates="items")
    choices = relationship("VoteChoice", back_populates="item")

# VoteChoiceEntity -> VoteChoice 모델 (복합 키)
class VoteChoice(Base):
    __tablename__ = "vote_choices"

    vote_item_id = Column(BIGINT, ForeignKey("vote_items.vote_item_id"), primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.user_id"), primary_key=True)

    item = relationship("VoteItem", back_populates="choices")
    user = relationship("User")
### Vote ###


### Widget ###
# WidgetCategoryEntity -> WidgetCategory 모델
class WidgetCategory(Base):
    __tablename__ = "parking_lot_widget_categories"

    category_id = Column(BIGINT, primary_key=True, index=True, name="category_id")
    category_name = Column(VARCHAR(64), nullable=False)
    category_description = Column(VARCHAR(32))
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    use_yn = Column(Enum(YnType), nullable=False, default=YnType.Y)

# DeviceEntity -> Device 모델
class Device(Base):
    __tablename__ = "devices"
    device_id = Column(BIGINT, primary_key=True, index=True, name="device_id")
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), nullable=False)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    device_ip = Column(VARCHAR(15))

# CctvEntity -> Cctv 모델 (복합 키)
class Cctv(Base):
    __tablename__ = "cctvs"
    device_id = Column(BIGINT, ForeignKey("devices.device_id"), primary_key=True)
    cctv_id = Column(Integer, primary_key=True)
    cctv_ip = Column(VARCHAR(15), nullable=False)

# WidgetEntity -> Widget 모델
class Widget(Base):
    __tablename__ = "parking_lot_widgets"

    widget_id = Column(BIGINT, primary_key=True, index=True, name="widget_id")
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), nullable=False)
    category_id = Column(BIGINT, ForeignKey("parking_lot_widget_categories.category_id"), nullable=False)
    grid_x = Column(Integer, nullable=False)
    grid_y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    widget_name = Column(VARCHAR(15), nullable=False)
    latitude = Column(DECIMAL(17, 14))
    longitude = Column(DECIMAL(17, 14))
    device_id = Column(BIGINT)
    cctv_id = Column(Integer) # Cctv 복합키의 일부이므로 직접적인 FK는 아님

    parking_lot = relationship("ParkingLot")
    category = relationship("WidgetCategory")
### Widget ###


### Group ###
class ParkingLotGroup(Base):
    """주차장 그룹 메타 정보 모델"""
    __tablename__ = "parking_lot_groups"

    group_id = Column(BIGINT, primary_key=True, index=True)
    group_name = Column(VARCHAR(30), nullable=False)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False)
    update_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT, nullable=False)
    del_yn = Column(Enum(YnType), nullable=False, default=YnType.N)

    members = relationship("ParkingLotGroupMember", back_populates="group", cascade="all, delete-orphan")

class ParkingLotGroupMember(Base):
    """주차장 그룹 멤버 매핑 모델"""
    __tablename__ = "parking_lot_group_members"

    group_id = Column(BIGINT, ForeignKey("parking_lot_groups.group_id"), primary_key=True)
    parking_lot_id = Column(BIGINT, ForeignKey("parking_lots.parking_lot_id"), primary_key=True)
    accept_yn = Column(Enum(YnType), nullable=False, default=YnType.N)
    create_at = Column(MYSQL_DATETIME(fsp=6), nullable=False, default=lambda: datetime.now(KST))
    create_by = Column(BIGINT, nullable=False) # 초대한 관리자의 user_id
    update_at = Column(MYSQL_DATETIME(fsp=6), onupdate=lambda: datetime.now(KST))
    update_by = Column(BIGINT) # 수락/거절한 관리자의 user_id

    group = relationship("ParkingLotGroup", back_populates="members")
    # parking_lot = relationship("ParkingLot", back_populates="group_memberships")

### Group ###


### etc ###
class Holiday(Base):
    __tablename__ = "holidays"

    holiday = Column(Date, primary_key=True)

### etc ###
