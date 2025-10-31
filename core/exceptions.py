# app/core/exceptions.py
from typing import Optional, Any
from .constants import ResponseCode

class ApiException(Exception):
    def __init__(self, response_code: ResponseCode, data: Optional[Any] = None):
        self.code = response_code.code
        self.message = response_code.message
        self.data = data

class AuthenticationException(ApiException):
    pass

class AuthorizationException(ApiException):
    pass

class SocialAuthenticationException(ApiException):
    pass

