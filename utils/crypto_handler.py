# app/utils/crypto_handler.py
import base64
import json
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

from core.config import settings

class MobileOkCrypto:
    def __init__(self):
        self._private_key: rsa.RSAPrivateKey = self._load_private_key()
        # Java의 mobileOK.getServiceId()에 해당하는 값을 여기서 로드하거나 설정할 수 있습니다.
        self.service_id = "your_service_id_from_keyfile" 

    def _load_private_key(self) -> rsa.RSAPrivateKey:
        """
        설정 파일에 명시된 경로에서 개인키 파일을 로드합니다.
        (Java: mobileOK.keyInit)
        """
        try:
            with open(settings.MOBILE_KEY_PATH, "rb") as key_file:
                private_key = serialization.load_pem_private_key(
                    key_file.read(),
                    password=settings.MOBILE_KEY_PASSWORD.encode(),
                    backend=default_backend()
                )
            return private_key
        except Exception as e:
            print(f"개인키 로드 실패: {e}")
            raise RuntimeError("개인키 파일을 로드할 수 없습니다.")

    def create_signature(self, plain_text: str) -> str:
        """
        주어진 문자열에 개인키로 서명(Sign)하고 Base64로 인코딩하여 반환합니다.
        (Java: mobileOK.RSAEncrypt)
        """
        try:
            signed_bytes = self._private_key.sign(
                plain_text.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA1() # Java 라이브러리와 해시 알고리즘을 일치시켜야 합니다.
            )
            return base64.b64encode(signed_bytes).decode('utf-8')
        except Exception as e:
            print(f"RSA 서명 생성 실패: {e}")
            raise ValueError("데이터 서명에 실패했습니다.")

    def decrypt_payload(self, encrypted_base64_text: str) -> dict:
        """
        Base64로 인코딩된 암호화 문자열을 개인키로 복호화(Decrypt)하여 원본 JSON(dict)을 반환합니다.
        (Java: mobileOK.getResultJSON)
        """
        try:
            # Base64 문자열을 다시 바이너리 데이터로 변환
            encrypted_bytes = base64.b64decode(encrypted_base64_text)
            
            # 개인키를 사용하여 데이터 복호화
            decrypted_bytes = self._private_key.decrypt(
                encrypted_bytes,
                padding.PKCS1v15() # 암호화 시 사용된 패딩과 동일해야 합니다.
            )
            
            # 복호화된 바이너리 데이터를 UTF-8 문자열로 디코딩 후 dict로 파싱
            decrypted_json_str = decrypted_bytes.decode('utf-8')
            return json.loads(decrypted_json_str)
        except Exception as e:
            print(f"RSA 복호화 실패: {e}")
            raise ValueError("암호화된 데이터를 복호화하는 데 실패했습니다.")


crypto_handler = MobileOkCrypto()
