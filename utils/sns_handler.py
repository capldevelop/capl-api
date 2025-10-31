# # app/utils/sns_handler.py
# import boto3
# import json
# from core.config import settings

# sns_client = boto3.client(
#     'sns',
#     aws_access_key_id=settings.AWS_SNS_ACCESS_KEY,
#     aws_secret_access_key=settings.AWS_SNS_SECRET_KEY,
#     region_name=settings.AWS_REGION
# )

# def _make_android_message(title: str, content: str, parking_lot_id: int) -> str:
#     """Android용 푸시 알림 메시지 페이로드를 생성합니다."""
#     gcm_payload = {
#         "notification": {
#             "title": title,
#             "body": content,
#             "click_action": "FLUTTER_NOTIFICATION_CLICK"
#         },
#         "data": {
#             "parkingLotId": str(parking_lot_id)
#         },
#         "priority": "high"
#     }
#     message = {
#         "GCM": json.dumps(gcm_payload)
#     }
#     return json.dumps(message)

# def send_push_notification(endpoint_arn: str, title: str, content: str, parking_lot_id: int):
#     """지정된 엔드포인트로 푸시 알림을 보냅니다."""
#     if not endpoint_arn:
#         print(f"SNS Error: endpoint_arn is empty for title: {title}")
#         return

#     try:
#         message = _make_android_message(title, content, parking_lot_id)
#         sns_client.publish(
#             TargetArn=endpoint_arn,
#             Message=message,
#             MessageStructure='json'
#         )
#         print(f"SNS push sent to {endpoint_arn}")
#     except Exception as e:
#         print(f"SNS push failed for {endpoint_arn}: {e}")

# def create_platform_endpoint(push_token: str) -> str:
#     """SNS 플랫폼 엔드포인트를 생성하고 ARN을 반환합니다."""
#     try:
#         response = sns_client.create_platform_endpoint(
#             PlatformApplicationArn=settings.AWS_SNS_ARN,
#             Token=push_token
#         )
#         return response.get('EndpointArn')
#     except Exception as e:
#         print(f"Failed to create SNS endpoint: {e}")
#         return None
