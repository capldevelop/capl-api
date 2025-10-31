# app/core/constants.py
from enum import Enum

class ResponseCode(Enum):
    SUCCESS = ("OK", "성공")
    FAIL = ("FAIL", "오류가 발생했습니다.")
    BAD_REQUEST = ("BAD_REQUEST", "요청이 올바르지 않습니다.")
    UNABLE_TYPE = ("UNABLE_TYPE", "사용할 수 없는 타입입니다.")
    INVALID_REQUEST_PARAMETER = ("INVALID_REQUEST_PARAMETER", "올바르지 않은 파라미터입니다.")

    INVALID_OAUTH_SERVICE = ("INVALID_OAUTH_SERVICE", "지원하지 않는 OAUTH 서비스입니다.")
    INVALID_OAUTH_AUTHORIZATION_CODE = ("INVALID_OAUTH_AUTHORIZATION_CODE", "유효하지 않은 인가코드입니다.")
    FAILED_OAUTH_LOGIN = ("FAILED_OAUTH_LOGIN", "OAUTH 로그인에 실패했습니다.")
    UNVERIFIED_USER = ("UNVERIFIED_USER", "휴대폰 본인인증을 하지 않은 사용자입니다.")
    ALREADY_JOINED_NUMBER = ("ALREADY_JOINED_NUMBER", "이미 가입된 휴대폰 번호입니다.")

    FAIL_VALID_TOKEN = ("FAIL_VALID_TOKEN", "토큰 유효성 검사에 실패했습니다.")
    INVALID_ACCESS_TOKEN = ("INVALID_ACCESS_TOKEN", "엑세스 토큰이 유효한 값이 아닙니다.")
    INVALID_REFRESH_TOKEN = ("INVALID_REFRESH_TOKEN", "리프레시 토큰이 유효한 값이 아닙니다.")
    EXPIRE_ACCESS_TOKEN = ("EXPIRE_ACCESS_TOKEN", "엑세스 토큰이 만료되었습니다.")
    EXPIRE_REFRESH_TOKEN = ("EXPIRE_REFRESH_TOKEN", "리프레시 토큰이 만료되었습니다.")
    PERMISSION_DENIED = ("PERMISSION_DENIED", "권한이 없습니다.")
    INVALID_LOGIN_INFO = ("INVALID_LOGIN_INFO", "로그인 정보가 유효하지 않습니다.")

    INVALID_USER = ("INVALID_USER", "사용자가 유효하지 않습니다.")
    INVALID_SOCIAL_USER = ("INVALID_SOCIAL_USER", "사용자 소셜 정보가 유효하지 않습니다.")
    INVALID_PASSWORD = ("INVALID_PASSWORD", "비밀번호가 일치하지 않습니다.")
    DUPLICATED_USER_ID = ("DUPLICATED_USER_ID", "이미 등록된 계정이 있습니다.")
    UNAUTHENTICATED_PHONE_USER = ("UNAUTHENTICATED_PHONE_USER", "휴대폰 인증이 되지 않은 사용자입니다.")
    FAILED_PHONE_AUTHENTICATION = ("FAILED_PHONE_AUTHENTICATION", "휴대폰 인증에 실패하였습니다.")
    SIGNED_UP_USER = ("SIGNED_UP_USER", "사용자가 가입한 이력이 있습니다.")

    DUPLICATED_PARKING_LOT_ADDRESS = ("DUPLICATED_PARKING_LOT_ADDRESS", "해당 주소로 등록된 주차장이 있습니다.")
    INVALID_PARKING_LOT = ("INVALID_PARKING_LOT", "주차장이 유효하지 않습니다.")
    INVALID_PARKING_LOT_USER_INFO = ("INVALID_PARKING_LOT_USER_INFO", "주차장 사용자 정보가 유효하지 않습니다.")
    ALREADY_REQUESTED = ("ALREADY_REQUESTED", "가입 요청을 한 주차장입니다.")
    INVALID_REQUEST = ("INVALID_REQUEST", "가입 요청이 유효하지 않습니다.")
    NOT_USER_IN_THE_PARKING_LOT = ("NOT_USER_IN_THE_PARKING_LOT", "주차장에 소속된 사용자가 아닙니다.")
    NO_ADMIN_IN_THE_PARKING_LOT = ("NO_ADMIN_IN_THE_PARKING_LOT", "주차장에 관리자가 없습니다.")
    FAILED_GET_GEOCODE = ("FAILED_GET_GEOCODE", "주소 GPS 좌표 요청이 실패했습니다.")
    NOT_CAR_IN_THE_PARKING_LOT = ("NOT_CAR_IN_THE_PARKING_LOT",  "주차장에 소속된 차량이 아닙니다.")
    PARKING_LOT_FULL = ("PARKING_LOT_FULL", "주차장이 가득 찼습니다.")

    INVALID_CAR = ("INVALID_CAR", "차량이 유효하지 않습니다.")
    NOT_USER_CAR = ("NOT_USER_CAR", "사용자의 차량이 아닙니다.")
    DUPLICATED_USERS_CAR = ("DUPLICATED_USERS_CAR", "차량이 이미 등록되어 있습니다.")
    INVALID_CAR_TYPE = ("INVALID_CAR_TYPE", "차량 타입이 유효하지 않습니다.")
    REGISTERED_CAR = ("REGISTERED_CAR", "주차장에 등록된 차량입니다.")

    INVALID_POLICY = ("INVALID_POLICY", "주차장 정책이 유효하지 않습니다.")

    INVALID_NOTIFICATION = ("INVALID_NOTIFICATION", "알람이 유효하지 않습니다.")
    INVALID_NOTIFICATION_SETTING = ("INVALID_NOTIFICATION_SETTING", "알림 설정이 유효하지 않습니다.")

    INVALID_CATEGORY_ID = ("INVALID_CATEGORY_ID", "유효하지 않은 위젯 카테고리ID 입니다.")

    INVALID_WIDGET = ("INVALID_WIDGET", "유효하지 않은 위젯입니다.")
    PARKING_EXISTS = ("PARKING_EXISTS", "주차 정보가 존재합니다.")

    INVALID_PARKING = ("INVALID_PARKING", "주차 정보가 없습니다.")
    INVALID_PARKING_HISTORY = ("INVALID_PARKING_HISTORY", "주차 기록이 없습니다.")
    CAR_PARKED_ON_THE_SPOT = ("CAR_PARKED_ON_THE_SPOT", "해당 주차면에 주차된 차량이 있습니다.")
    ALREADY_PULL_IN = ("ALREADY_PULL_IN", "이미 입차된 차량입니다.")
    ALREADY_PULL_IN_VISITOR = ("ALREADY_PULL_IN_VISITOR", "이미 입차된 방문차량입니다.")
    ALREADY_PULL_IN_UNREGISTERED = ("ALREADY_PULL_IN_UNREGISTERED", "이미 입차된 미등록차량입니다.")
    ALREADY_PULL_IN_REQUESTED = ("ALREADY_PULL_IN_REQUESTED", "이미 입차 요청하였습니다.")
    INVALID_PARKING_REQUEST = ("INVALID_PARKING_REQUEST", "유효하지 않은 주차 요청입니다.")
    NOT_AVAILABLE_REGISTERED = ("NOT_AVAILABLE_REGISTERED", "등록 차량은 변환이 불가능합니다.")

    INVALID_CHAT = ("INVALID_CHAT", "유효하지 않은 채팅방입니다.")
    ALREADY_JOIN_CHAT = ("ALREADY_JOIN_CHAT", "이미 채팅방에 참여중입니다.")
    NOT_JOIN_CHAT = ("NOT_JOIN_CHAT", "참여된 채팅방이 아닙니다.")
    ADMIN_CANNOT_LEAVE_CHAT = ("ADMIN_CANNOT_LEAVE_CHAT", "관리자는 채팅방을 나갈 수 없습니다.")

    AWS_SNS_MESSAGE_PARSING_ERROR = ("AWS_SNS_MESSAGE_PARSING_ERROR", "AWS SNS 메시지 파싱 에러입니다.")

    INVALID_FILE = ("INVALID_FILE", "유효하지 않은 파일입니다.")

    INVALID_NOTICE = ("INVALID_NOTICE", "유효하지 않은 공지입니다.")

    INVALID_VOTE = ("INVALID_VOTE", "유효하지 않은 투표입니다.")
    VOTE_IS_INACTIVE = ("VOTE_IS_INACTIVE", "종료된 투표입니다.")
    MULTIPLE_VOTING_IS_NOT_POSSIBLE = ("MULTIPLE_VOTING_IS_NOT_POSSIBLE", "중복 투표를 할 수 없습니다.")
    INVALID_VOTE_ITEM = ("INVALID_VOTE_ITEM", "유효하지 않은 투표 항목입니다.")
    VOTING_IS_UNDERWAY = ("VOTING_IS_UNDERWAY", "이미 투표가 진행중입니다.")

    INVALID_SCHEDULE = ("INVALID_SCHEDULE", "유효하지 않은 스케줄입니다.")

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
