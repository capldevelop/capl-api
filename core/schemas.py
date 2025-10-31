# app/schemas.py
from pydantic import BaseModel, Field
from typing import TypeVar, Generic, Optional, List
from datetime import datetime, time
# 정의한 Enum import
from .models import MessageType, YnType, UserRole, NotificationType, CarType, RequestStatus, LoginDeviceType, SocialType, TaskType

T = TypeVar('T')

class PageInfo(BaseModel, Generic[T]):
    page_number: int
    page_size: int
    total_pages: int
    total_content_count: int
    content: T

# =================================================================
# Base Config for ORM Mapping (일괄 적용을 위한 기본 클래스)
# =================================================================

class OrmConfig(BaseModel):
    class Config:
        from_attributes = True
        populate_by_name = True

### User ###
# --- Data Transfer Objects (Internal) ---
class TempUser(BaseModel):
    temp_user_id: int
    user_name: str
    user_phone: str
    user_ci: str

class UserDomain(BaseModel):
    user_id: int
    user_name: str
    user_phone: str
    user_ci: str

    # class Config:
    #     from_attributes = True

# --- Request Schemas ---
class VerifyUserRequest(OrmConfig):
    user_name: str = Field(..., alias="userName")
    user_phone: str = Field(..., alias="userPhone")
    user_ci: str = Field(..., alias="userCi")

# --- Response Schemas ---
class UserResponse(OrmConfig):
    user_id: int = Field(..., alias="userId")
    user_name: str = Field(..., alias="userName")
    user_phone: str = Field(..., alias="userPhone")

    # class Config:
    #     from_attributes = True
    #     populate_by_name = True
### User ###

### Auth ###
# AuthSignupResponse.java -> AuthSignupResponse Pydantic 모델
class AuthSignupResponse(BaseModel):
    name: Optional[str] = Field(None, description="이름")
    phone: Optional[str] = Field(None, description="전화번호")
    ci: Optional[str] = Field(None, description="CI (연계정보)")

# RootResponse.java -> RootResponse 제네릭 모델
class RootResponse(BaseModel, Generic[T]):
    status: str = "OK"
    message: str = "success"
    data: Optional[T] = None

    # RootResponse.ok(data)와 동일한 기능을 하는 클래스 메서드
    @classmethod
    def ok(cls, data: T):
        return cls(data=data)
### Auth ###


### Car ###
# --- Request Schemas ---
class AddCarRequest(BaseModel):
    car_number: str = Field(
        ..., 
        alias="carNumber",
        description="차량번호",
        pattern=r"(^[0-9]{2,3}[가-힣]{1}[0-9]{4}$)|(^[가-힣]{2}[0-9]{1,2}[가-힣]{1}[0-9]{4}$)"
    )

# --- Response Schemas ---
class CarResponse(OrmConfig):
    car_id: int = Field(..., alias="carId")
    car_number: str = Field(..., alias="carNumber")
### Car ###


### Chat ###
# --- Request Schemas ---
class ExitChatRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="주차장ID")

class SendRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="주차장ID")
    message: str = Field(..., description="메시지")

class SendFileRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="주차장ID")

class SetChatNotificationRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="주차장ID")
    active_yn: YnType = Field(..., alias="activeYn", description="채팅알림활성여부")

class InviteChatRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="주차장ID")
    user_id_list: List[int] = Field(..., alias="userIdList", description="사용자ID목록")


# --- Response Schemas ---
class ChatUserResponse(OrmConfig):
    user_id: int = Field(..., alias="userId")
    user_nickname: str = Field(..., alias="userNickname")
    user_role: str = Field(..., alias="userRole")
    car_number_list: List[str] = Field(..., alias="carNumberList")

class MessageIdResponse(OrmConfig):
    message_id: Optional[int] = Field(None, alias="messageId")

class MessageResponse(OrmConfig):
    message_id: int = Field(..., alias="messageId")
    send_at: datetime = Field(..., alias="sendAt")
    user_id: int = Field(..., alias="userId")
    user_nickname: str = Field(..., alias="userNickname")
    message_type: MessageType = Field(..., alias="messageType")
    content: Optional[str] = None
    file_url: Optional[str] = Field(None, alias="fileUrl")
    file_name: Optional[str] = Field(None, alias="fileName")
    file_size: Optional[str] = Field(None, alias="fileSize")

class ChatNotificationResponse(OrmConfig):
    active_yn: YnType = Field(..., alias="activeYn")


class FileUploadResponse(OrmConfig):
    upload_url: str = Field(..., alias="uploadUrl", description="S3 업로드를 위한 Presigned URL")
    file_path: str = Field(..., alias="filePath", description="S3에 저장될 최종 파일 경로")


# --- Event Schema ---
class ChatMessagePushEvent(BaseModel):
    send_user_id: int
    parking_lot_id: int
    parking_lot_name: str
### Chat ###


### Notification ###
class NotificationActive(BaseModel):
    notification_id: int = Field(..., alias="notificationId")
    active_yn: YnType = Field(..., alias="activeYn")

# --- Event Schemas ---
# Chat과 중복되어 주석 처리
# class ChatMessagePushEvent(BaseModel):
#     send_user_id: int = Field(..., alias="sendUserId")
#     parking_lot_id: int = Field(..., alias="parkingLotId")
#     parking_lot_name: str = Field(..., alias="parkingLotName")

# Parking과 중복되어 주석 처리
# class AutoPullOutPushEvent(BaseModel):
#     user_id: int = Field(..., alias="userId")
#     parking_lot_id: int = Field(..., alias="parkingLotId")
#     car_number: str = Field(..., alias="carNumber")

class NoticeAppendPushEvent(OrmConfig):
    create_by: int = Field(..., alias="createBy")
    parking_lot_id: int = Field(..., alias="parkingLotId")

class VoteAppendPushEvent(OrmConfig):
    create_by: int = Field(..., alias="createBy")
    parking_lot_id: int = Field(..., alias="parkingLotId")
     
# 스케줄 기반 알림 이벤트
class ScheduledPushEvent(BaseModel):
    user_id: int
    parking_lot_id: int
    car_number: Optional[str] = None
     
# 주차 정책 관련 알림 이벤트
class PolicyViolationPushEvent(BaseModel):
    user_id: int
    user_nickname: str
    parking_lot_id: int
    reason: str # 내용 (예: "MULTIPLE_PARKING", "PARKING_LOT_FULL")
    car_number: Optional[str] = None

### Notification ###



### Parking Lot ###
# =================================================================
# Policy Schemas (ParkingLot에서 사용되어 미리 정의)
# =================================================================

class PolicyActive(BaseModel):
    policy_id: int = Field(..., alias="policyId")
    active_yn: YnType = Field(..., alias="activeYn")

# =================================================================
# Widget Schemas (ParkingLot에서 사용되어 미리 정의)
# =================================================================

class Widget(OrmConfig):
    widget_id: Optional[int] = Field(None, alias="widgetId")
    category_id: int = Field(..., alias="categoryId")
    grid_x: int = Field(..., alias="gridX")
    grid_y: int = Field(..., alias="gridY")
    width: int
    height: int
    widget_name: str = Field(..., alias="widgetName")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    device_id: Optional[int] = Field(None, alias="deviceId")
    cctv_id: Optional[int] = Field(None, alias="cctvId")

# =================================================================
# ParkingLot Schemas
# =================================================================

# --- Data Transfer Objects (Internal) ---
class Geocodes(BaseModel):
    latitude: float
    longitude: float

class ParkingLotDomain(BaseModel): # Java의 ParkingLot 도메인 클래스 대체
    parking_lot_id: int
    parking_lot_name: str
    parking_lot_address: str
    parking_lot_address_detail: Optional[str] = None
    latitude: float
    longitude: float

    # class Config:
    #     from_attributes = True

# --- Request Schemas ---
class AcceptJoinRequest(BaseModel):
    user_id_list: List[int] = Field(..., alias="userIdList")

class RejectJoinRequest(BaseModel):
    user_id_list: List[int] = Field(..., alias="userIdList")

class AddParkingLotRequest(BaseModel):
    class PolicyActiveInfo(BaseModel):
        policy_id: int = Field(..., alias="policyId")
        active_yn: YnType = Field(..., alias="activeYn")

    class ParkingLotUserInfo(BaseModel):
        user_nickname: str = Field(..., alias="userNickname")
        phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")
        pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
        pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
        pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
        holiday_exclude_yn: Optional[YnType] = Field(None, alias="holidayExcludeYn")
        car_id_list: Optional[List[int]] = Field(None, alias="carIdList")

    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")
    parking_lot_public: Optional[YnType] = Field(None, alias="parkingLotPublic")
    policy_active_info_list: List[PolicyActiveInfo] = Field(..., alias="policyActiveInfoList")
    parking_lot_user_info: ParkingLotUserInfo = Field(..., alias="parkingLotUserInfo")

class EditParkingLotAddressRequest(BaseModel):
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")

class EditParkingLotNameRequest(BaseModel):
    parking_lot_name: str = Field(..., alias="parkingLotName")

class EditParkingLotRequest(BaseModel):
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")

class EditParkingLotPublicRequest(BaseModel):
    parking_lot_public: YnType = Field(..., alias="parkingLotPublic")

class EditUserCarRequest(BaseModel):
    car_id_list: Optional[List[int]] = Field(None, alias="carIdList")

class EditUserInfoRequest(BaseModel):
    user_nickname: str = Field(..., alias="userNickname")
    phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")
    pull_out_time_yn: YnType = Field(..., alias="pullOutTimeYn")
    pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
    pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
    pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
    holiday_exclude_yn: Optional[YnType] = Field(None, alias="holidayExcludeYn")
    car_id_list: Optional[List[int]] = Field(None, alias="carIdList")

class EditUserNicknameRequest(BaseModel):
    user_nickname: str = Field(..., alias="userNickname")

class EditUserPhoneSecretRequest(BaseModel):
    phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")

class EditUserPullOutTimeRequest(BaseModel):
    pull_out_time_yn: YnType = Field(..., alias="pullOutTimeYn")
    pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
    pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
    pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
    holiday_exclude_yn: Optional[YnType] = Field(None, alias="holidayExcludeYn")

class EditUserPullOutTimeYnRequest(BaseModel):
    pull_out_time_yn: YnType = Field(..., alias="pullOutTimeYn")

class EditUserRoleRequest(BaseModel):
    user_role: UserRole = Field(..., alias="userRole")

class JoinParkingLotRequest(BaseModel):
    user_nickname: str = Field(..., alias="userNickname")
    phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")
    pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
    pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
    pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
    holiday_exclude_yn: Optional[YnType] = Field(None, alias="holidayExcludeYn")
    car_id_list: List[int] = Field(..., alias="carIdList")

class NotificationSettingRequest(BaseModel):
    class NotificationActiveInfo(BaseModel):
        notification_id: int = Field(..., alias="notificationId")
        active_yn: YnType = Field(..., alias="activeYn")
     
    notification_active_info_list: List[NotificationActiveInfo] = Field(..., alias="notificationActiveInfoList")

class PolicySettingRequest(BaseModel):
    class PolicyActiveInfo(BaseModel):
        policy_id: int = Field(..., alias="policyId")
        active_yn: YnType = Field(..., alias="activeYn")

    policy_active_info_list: List[PolicyActiveInfo] = Field(..., alias="policyActiveInfoList")

class SaveLayoutRequest(BaseModel):
    class WidgetInfo(BaseModel):
        widget_id: Optional[int] = Field(None, alias="widgetId")
        category_id: int = Field(..., alias="categoryId")
        grid_x: int = Field(..., alias="gridX")
        grid_y: int = Field(..., alias="gridY")
        width: int
        height: int
        widget_name: str = Field(..., alias="widgetName")
        latitude: Optional[float] = None
        longitude: Optional[float] = None
        device_id: Optional[int] = Field(None, alias="deviceId")
        cctv_id: Optional[int] = Field(None, alias="cctvId")

    layout_width: int = Field(..., alias="layoutWidth")
    layout_height: int = Field(..., alias="layoutHeight")
    widget_list: List[WidgetInfo] = Field(..., alias="widgetList")

# --- Response Schemas ---
class AddParkingLotResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")

class CarParkingLotResponse(OrmConfig):
    class ParkingInfo(OrmConfig):
        widget_id: int = Field(..., alias="widgetId")
        parking_id: int = Field(..., alias="parkingId")
        create_by: int = Field(..., alias="parkingUserId")
        car_id: Optional[int] = Field(None, alias="carId")
        car_number: str = Field(..., alias="carNumber")
        car_type: CarType = Field(..., alias="carType")
        pull_in_at: datetime = Field(..., alias="pullInAt")
        pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
        pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

    class ParkingLotInfo(OrmConfig):
        parking_lot_id: int = Field(..., alias="parkingLotId")
        parking_lot_name: str = Field(..., alias="parkingLotName")
        parking_lot_address: str = Field(..., alias="parkingLotAddress")
        parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")
        latitude: float
        longitude: float
        parking_info: Optional['ParkingInfo'] = Field(None, alias="parkingInfo")

    parking_lot_list: List[ParkingLotInfo] = Field(..., alias="parkingLotList")

class CategoryResponse(OrmConfig):
    category_id: int = Field(..., alias="categoryId")
    category_name: str = Field(..., alias="categoryName")
    category_description: Optional[str] = Field(None, alias="categoryDescription")
    width: int
    height: int

class CctvPhoneResponse(OrmConfig):
    cctv_phone: str = Field(..., alias="cctvPhone")

class CctvResponse(OrmConfig):
    device_id: int = Field(..., alias="deviceId")
    cctv_id: int = Field(..., alias="cctvId")
    cctv_ip: str = Field(..., alias="cctvIp")

class JoinParkingLotResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")
    latitude: float
    longitude: float
    user_role: UserRole = Field(..., alias="userRole")
    accept_yn: YnType = Field(..., alias="acceptYn")
    chat_join_yn: YnType = Field(..., alias="chatJoinYn")

class JoinUserDetailResponse(OrmConfig):
    class CarInfo(OrmConfig):
        car_id: int = Field(..., alias="carId")
        car_number: str = Field(..., alias="carNumber")

    user_id: int = Field(..., alias="userId")
    user_role: UserRole = Field(..., alias="userRole")
    user_nickname: str = Field(..., alias="userNickname")
    phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")
    user_phone: Optional[str] = Field(None, alias="userPhone")
    pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
    pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
    pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
    car_list: Optional[List[CarInfo]] = Field(None, alias="carList")

class JoinUserListResponse(OrmConfig):
    admin_user_list: List[JoinUserDetailResponse] = Field(..., alias="adminUserList")
    basic_user_list: Optional[List[JoinUserDetailResponse]] = Field(None, alias="basicUserList")

class LayoutResponse(OrmConfig):
    layout_width: Optional[int] = Field(None, alias="layoutWidth")
    layout_height: Optional[int] = Field(None, alias="layoutHeight")
    widget_list: Optional[List[Widget]] = Field(None, alias="widgetList")

class NotificationResponse(OrmConfig):
    class NotificationInfo(OrmConfig):
        notification_id: int = Field(..., alias="notificationId")
        notification_name: str = Field(..., alias="notificationName")
        notification_description: Optional[str] = Field(None, alias="notificationDescription")

    notification_type: NotificationType = Field(..., alias="notificationType")
    notification_type_name: str = Field(..., alias="notificationTypeName")
    notification_list: List[NotificationInfo] = Field(..., alias="notificationList")

class NotificationSettingResponse(OrmConfig):
    notification_id: int = Field(..., alias="notificationId")
    active_yn: YnType = Field(..., alias="activeYn")

class ParkingLotDetailResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")
    user_count: int = Field(..., alias="userCount")
    join_request_user_count: Optional[int] = Field(None, alias="joinRequestUserCount")

class ParkingLotHomeResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    chat_id: int = Field(..., alias="chatId")
    latitude: float
    longitude: float

class ParkingLotResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")

class ParkingLotPublicResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")
    parking_lot_public: str = Field(..., alias="parkingLotPublic")

class ParkingLotUserDetailResponse(OrmConfig):
    user_nickname: str = Field(..., alias="userNickname")
    car_count: Optional[int] = Field(None, alias="carCount")
    phone_secret_yn: YnType = Field(..., alias="phoneSecretYn")
    pull_out_time_yn: Optional[YnType] = Field(None, alias="pullOutTimeYn")
    pull_out_start_time: Optional[time] = Field(None, alias="pullOutStartTime")
    pull_out_end_time: Optional[time] = Field(None, alias="pullOutEndTime")
    pull_out_week: Optional[str] = Field(None, alias="pullOutWeek")
    holiday_exclude_yn: Optional[YnType] = Field(None, alias="holidayExcludeYn")

class PolicyResponse(OrmConfig):
    policy_id: int = Field(..., alias="policyId")
    policy_name: str = Field(..., alias="policyName")
    policy_description: Optional[str] = Field(None, alias="policyDescription")

class PolicySettingResponse(OrmConfig):
    policy_id: int = Field(..., alias="policyId")
    active_yn: YnType = Field(..., alias="activeYn")

class SummaryParkingResponse(OrmConfig):
    empty_count: int = Field(..., alias="emptyCount")
    registered_count: int = Field(..., alias="registeredCount")
    unregistered_count: int = Field(..., alias="unregisteredCount")
    visitor_count: int = Field(..., alias="visitorCount")
### Parking Lot ###

### Parking ###
# --- Data Transfer Objects (Internal) ---
class ParkingDomain(BaseModel):
    parking_id: int
    widget_id: int
    car_id: Optional[int]
    parking_user_id: int # create_by
    car_number: str
    car_type: CarType
    pull_in_at: datetime
    pull_out_start_at: Optional[datetime] = None
    pull_out_end_at: Optional[datetime] = None
    
    # class Config:
    #     from_attributes = True

class CarDomain(BaseModel):
    car_id: Optional[int] = None
    car_number: str

# --- Request Schemas ---
class AutoParkingRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: Optional[int] = Field(None, alias="widgetId")
    car_id: int = Field(..., alias="carId")

class AutoPullOutRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")

class EditCarTypeRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")
    car_type: CarType = Field(..., alias="carType")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class EditParkingRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    car_id: int = Field(..., alias="carId")
    widget_id: int = Field(..., alias="widgetId")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class EditPullOutTimeRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class EditSpotRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")
    update_widget_id: int = Field(..., alias="updateWidgetId")

class ManualParkingRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")
    car_id: Optional[int] = Field(None, alias="carId")
    car_number: Optional[str] = Field(None, alias="carNumber")
    car_type: Optional[CarType] = Field(None, alias="carType")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class ManualPullOutRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")

class PullInPushRequest(BaseModel):
    widget_id: int
    user_id: int
    parking_lot_id: int
    car_number: str

class PullOutPushRequest(BaseModel):
    user_id: int
    parking_lot_id: int
    car_number: str

# --- Response Schemas ---
class AutoParkingRequestResponse(OrmConfig):
    parking_request_id: int = Field(..., alias="parkingRequestId")

class LatestParkingResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    widget_id: int = Field(..., alias="widgetId")
    widget_name: str = Field(..., alias="widgetName")
    car_id: Optional[int] = Field(..., alias="carId")
    car_number: str = Field(..., alias="carNumber")

class ParkingByCarResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    widget_id: int = Field(..., alias="widgetId")
    widget_name: str = Field(..., alias="widgetName")
    car_number: str = Field(..., alias="carNumber")

class ParkingRequestStatusResponse(OrmConfig):
    parking_request_status: RequestStatus = Field(..., alias="parkingRequestStatus")
    parking_id: Optional[int] = Field(None, alias="parkingId")
    parking_lot_id: Optional[int] = Field(None, alias="parkingLotId")
    widget_id: Optional[int] = Field(None, alias="widgetId")
    widget_name: Optional[str] = Field(None, alias="widgetName")
    car_id: Optional[int] = Field(None, alias="carId")
    car_number: Optional[str] = Field(None, alias="carNumber")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class ParkingResponse(OrmConfig):
    widget_id: int = Field(..., alias="widgetId")
    widget_name: Optional[str] = Field(None, alias="widgetName")
    parking_id: int = Field(..., alias="parkingId")
    parking_user_id: int = Field(..., alias="parkingUserId")
    user_nickname: Optional[str] = Field(None, alias="userNickname")
    user_phone_secret_yn: Optional[YnType] = Field(None, alias="userPhoneSecretYn")
    user_phone: Optional[str] = Field(None, alias="userPhone")
    car_id: Optional[int] = Field(None, alias="carId")
    car_number: str = Field(..., alias="carNumber")
    car_type: CarType = Field(..., alias="carType")
    pull_in_at: datetime = Field(..., alias="pullInAt")
    pull_out_start_at: Optional[datetime] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[datetime] = Field(None, alias="pullOutEndAt")

class ParkingStatusResponse(OrmConfig):
    car_id: int = Field(..., alias="carId")
    parking_yn: YnType = Field(..., alias="parkingYn")

class PullOutTimeResponse(OrmConfig):
    pull_out_start_at: Optional[time] = Field(None, alias="pullOutStartAt")
    pull_out_end_at: Optional[time] = Field(None, alias="pullOutEndAt")

class GeofenceEntryRequest(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")

# --- Event Schemas ---
class PullOutPushEvent(BaseModel):
    user_id: int
    parking_lot_id: int
    user_nickname: str
    car_number: str

class PullInPushEvent(BaseModel):
    user_id: int
    parking_lot_id: int
    user_nickname: str
    car_number: str

class ParkingRequestEvent(BaseModel):
    parking_request_id: int
    parking_lot_id: int
    user_id: int
    car_id: int
    spot_widget_id: Optional[int] = None

class ScheduleCreateEvent(BaseModel):
    user_id: int
    parking_lot_id: int
    task_type: TaskType
    type_id: int
    execute_time: datetime

class ScheduleDeleteEvent(BaseModel):
    task_type: TaskType
    type_id: int
### Parking ###


### Login ###
# --- Data Transfer Objects (Internal) ---
class UserTokens(BaseModel):
    access_token: str
    refresh_token: str

class LoginDevice(BaseModel):
    login_device_uuid: str
    login_device_type: LoginDeviceType
    login_device_name: str
    login_device_os: str

class OauthUserInfo(BaseModel):
    social_login_id: str

# --- Request Schemas ---
class LoginDeviceInfo(BaseModel):
    login_device_uuid: str = Field(..., alias="loginDeviceUuid")
    login_device_type: LoginDeviceType = Field(..., alias="loginDeviceType")
    login_device_name: str = Field(..., alias="loginDeviceName")
    login_device_os: str = Field(..., alias="loginDeviceOs")

class LoginRequest(BaseModel):
    user_name: str = Field(..., alias="userName")
    user_phone: str = Field(..., alias="userPhone")
    # PASS 인증을 통해 받은 CI 값을 필수로 받도록 추가
    user_ci: str = Field(..., alias="userCi")
    login_device_info: LoginDeviceInfo = Field(..., alias="loginDeviceInfo")
    push_token: Optional[str] = Field(None, alias="pushToken")

class SocialLoginRequest(BaseModel):
    social_type: SocialType = Field(..., alias="socialType")
    code: str
    login_device_info: LoginDeviceInfo = Field(..., alias="loginDeviceInfo")
    push_token: str = Field(..., alias="pushToken")

class SignUpRequest(BaseModel):
    class UserSocialInfo(BaseModel):
        user_social_id: str = Field(..., alias="userSocialId")
        social_type: SocialType = Field(..., alias="socialType")
        user_social_email: Optional[str] = Field(None, alias="userSocialEmail")
        refresh_token: Optional[str] = Field(None, alias="refreshToken")

    user_name: str = Field(..., alias="userName")
    user_phone: str = Field(..., alias="userPhone")
    user_social_info: Optional[UserSocialInfo] = Field(None, alias="userSocialInfo")
    login_device_info: LoginDeviceInfo = Field(..., alias="loginDeviceInfo")
    push_token: str = Field(..., alias="pushToken")

class EditPhoneRequest(BaseModel):
    user_name: str = Field(..., alias="userName")
    user_phone: str = Field(..., alias="userPhone")
    login_device_info: LoginDeviceInfo = Field(..., alias="loginDeviceInfo")
    push_token: str = Field(..., alias="pushToken")

class TokenRequest(BaseModel):
    push_token: str = Field(..., alias="pushToken")
    login_device_uuid: str = Field(..., alias="loginDeviceUuid")

class LogoutRequest(BaseModel):
    login_device_uuid: str = Field(..., alias="loginDeviceUuid")

# --- Response Schemas ---
class LoginResponse(BaseModel):
    access_token: str = Field(..., alias="accessToken")

class TokenResponse(BaseModel):
    access_token: str = Field(..., alias="accessToken")
    refresh_token: str = Field(..., alias="refreshToken")
### Login ###


### Notice ###
class NoticeDomain(BaseModel):
    notice_id: int
    parking_lot_id: int
    notice_title: str
    notice_content: str
    create_by: int
    # ... 기타 필요한 필드 ...

    class Config:
        from_attributes = True

# --- Request Schemas ---
class AddNoticeRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    notice_title: str = Field(..., alias="noticeTitle", max_length=30)
    notice_content: str = Field(..., alias="noticeContent")

class EditNoticeRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    notice_id: int = Field(..., alias="noticeId")
    notice_title: str = Field(..., alias="noticeTitle", max_length=30)
    notice_content: str = Field(..., alias="noticeContent")

class DeleteNoticeRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    notice_id: int = Field(..., alias="noticeId")
### Notice ###


### Vote ###
# --- Data Transfer Objects (Internal) ---
class VoteDomain(BaseModel):
    vote_id: int
    parking_lot_id: int
    vote_title: str
    active_yn: YnType
    multiple_yn: YnType
    anonymous_yn: YnType
    end_at: Optional[datetime] = None
    create_by : int

    # API 응답에 추가될 필드들
    vote_yn: Optional[YnType] = None
    total_vote_count: Optional[int] = None

    # class Config:
    #     from_attributes = True

# --- Request Schemas ---
class AddVoteRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    vote_title: str = Field(..., alias="voteTitle")
    vote_item_list: List[str] = Field(..., alias="voteItemList")
    multiple_yn: YnType = Field(..., alias="multipleYn")
    anonymous_yn: YnType = Field(..., alias="anonymousYn")
    end_at: Optional[datetime] = Field(None, alias="endAt")

class EditVoteRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    vote_id: int = Field(..., alias="voteId")
    vote_title: str = Field(..., alias="voteTitle")
    vote_item_list: Optional[List[str]] = Field(None, alias="voteItemList")
    multiple_yn: YnType = Field(..., alias="multipleYn")
    anonymous_yn: YnType = Field(..., alias="anonymousYn")
    end_at: Optional[datetime] = Field(None, alias="endAt")

class DeleteVoteRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    vote_id: int = Field(..., alias="voteId")

class VoteRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    vote_id: int = Field(..., alias="voteId")
    vote_item_id_list: List[int] = Field(..., alias="voteItemIdList")

class CancelVoteRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    vote_id: int = Field(..., alias="voteId")

# --- Response Schemas ---
class VoteItemResponse(OrmConfig):
    vote_item_id: int = Field(..., alias="voteItemId")
    content: str

class VoteUserResponse(OrmConfig):
    class VoteUser(OrmConfig):
        user_id: int = Field(..., alias="userId")
        user_nickname: str = Field(..., alias="userNickname")

    vote_item_id: int = Field(..., alias="voteItemId")
    vote_yn: YnType = Field(..., alias="voteYn")
    vote_user_count: int = Field(..., alias="voteUserCount")
    vote_user_list: List[VoteUser] = Field(..., alias="voteUserList")
### Vote ###


### Widget ###
# --- Data Transfer Objects (Internal) ---
class CctvDomain(BaseModel):
    device_id: int
    cctv_id: int
    cctv_ip: str

class WidgetCategoryDomain(BaseModel):
    category_id: int
    category_name: str
    category_description: Optional[str] = None
    width: int
    height: int

    # class Config:
    #     from_attributes = True

# --- Response Schemas ---
class WidgetResponse(OrmConfig):
    widget_id: Optional[int] = Field(None, alias="widgetId")
    category_id: int = Field(..., alias="categoryId")
    grid_x: int = Field(..., alias="gridX")
    grid_y: int = Field(..., alias="gridY")
    width: int
    height: int
    widget_name: str = Field(..., alias="widgetName")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    device_id: Optional[int] = Field(None, alias="deviceId")
    cctv_id: Optional[int] = Field(None, alias="cctvId")

    # class Config:
    #     from_attributes = True
### Widget ###


### Group ###
# --- Request Schemas ---
class CreateGroupRequest(BaseModel):
    group_name: str = Field(..., alias="groupName", max_length=30, description="생성할 그룹의 이름")
    creator_parking_lot_id: int = Field(..., alias="creatorParkingLotId", description="그룹을 생성하는 주차장 ID")

class InviteToGroupRequest(BaseModel):
    inviter_parking_lot_id: int = Field(..., alias="inviterParkingLotId", description="초대하는 주차장 ID")
    target_parking_lot_id: int = Field(..., alias="targetParkingLotId", description="초대받는 주차장 ID")

class HandleGroupInvitationRequest(BaseModel):
    parking_lot_id: int = Field(..., alias="parkingLotId", description="초대를 수락/거절하는 주차장 ID")

# --- Response Schemas ---
class GroupResponse(OrmConfig):
    group_id: int = Field(..., alias="groupId")
    group_name: str = Field(..., alias="groupName")

class GroupInvitationResponse(OrmConfig):
    group_id: int = Field(..., alias="groupId")
    group_name: str = Field(..., alias="groupName")
    # 초대한 주차장 정보를 추가하여, 어떤 주차장이 초대했는지 알 수 있도록 함
    inviting_parking_lot_id: int = Field(..., alias="invitingParkingLotId")
    inviting_parking_lot_name: str = Field(..., alias="invitingParkingLotName")

class SharedParkingLotResponse(OrmConfig):
    parking_lot_id: int = Field(..., alias="parkingLotId")
    parking_lot_name: str = Field(..., alias="parkingLotName")
    parking_lot_address: str = Field(..., alias="parkingLotAddress")
    parking_lot_address_detail: Optional[str] = Field(None, alias="parkingLotAddressDetail")

class MyGroupInfoResponse(OrmConfig):
    class GroupMemberInfo(OrmConfig):
        parking_lot_id: int = Field(..., alias="parkingLotId")
        parking_lot_name: str = Field(..., alias="parkingLotName")
        accept_yn: YnType = Field(..., alias="acceptYn")

    group_id: int = Field(..., alias="groupId")
    group_name: str = Field(..., alias="groupName")
    members: List[GroupMemberInfo]

### Group ###



### LPR ###

class SyncCarInfo(BaseModel):
    surfaceId: int = Field(..., description="주차면 ID (widget_id)")
    carNo: str = Field(..., description="인식된 차량 번호")

class ParkingSyncRequest(BaseModel):
    parkId: int = Field(..., description="주차장 Mini PC ID (device_id)")
    cars: List[SyncCarInfo] = Field(..., description="현재 CCTV에 감지된 차량 목록")

class LprSyncRequest(OrmConfig):
    park_id: int = Field(..., alias="parkId")
    car_list: list[dict] = Field(..., alias="carList")


### LPR ###