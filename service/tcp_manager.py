import asyncio
import json
import logging
from typing import Dict, Optional, List, Any, Callable
from sqlalchemy.orm import Session

from core import models, schemas
from core.config import settings
import function.lpr_function as lpr_function
import function.parking_function as parking_function

# =================================================================
# 설정
# =================================================================
REQUEST_TIMEOUT_SECONDS = settings.REQUEST_TIMEOUT_SECONDS
HEARTBEAT_INTERVAL_SECONDS = settings.HEARTBEAT_INTERVAL_SECONDS

# =================================================================
# TCP 서버 핵심 로직
# =================================================================

class ClientState:
    """개별 클라이언트 연결의 상태(Reader, Writer, 대기 중인 요청)를 관리하는 클래스입니다."""
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.pending_requests: Dict[int, Dict[str, Any]] = {}
        self.request_seq_counter = 0

class TCPSessionManager:
    """TCP 클라이언트 세션을 관리하고 비즈니스 로직을 처리하는 중앙 클래스입니다."""
    def __init__(self, db_session_factory: Callable[[], Session]):
        self.get_db_session = db_session_factory
        self.sessions: Dict[int, ClientState] = {} # {park_id: ClientState}
        self.writer_to_park_id: Dict[asyncio.StreamWriter, int] = {} # Writer 객체로 park_id를 찾기 위한 맵
        self.heartbeat_task: Optional[asyncio.Task] = None

    def is_client_connected_for_request(self, db: Session, request_id: int) -> bool:
        """ParkingRequest ID를 기반으로 해당 주차장의 LPR 클라이언트가 연결되어 있는지 확인합니다."""
        try:
            parking_request = db.query(models.ParkingRequest).get(request_id)
            if not parking_request:
                return False
            return parking_request.parking_lot_id in self.sessions
        except Exception as e:
            logging.error(f"Error checking client connection for request {request_id}: {e}")
            return False

    def add_session(self, park_id: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """새로운 클라이언트 세션을 추가하거나 덮어씁니다."""
        if park_id in self.sessions:
            logging.warning(f"Parking lot {park_id} already has an active session. Overwriting.")
            old_state = self.sessions[park_id]
            old_state.writer.close()
            # 이전 세션에 남아있던 타임아웃 타이머들을 정리합니다.
            for req_data in old_state.pending_requests.values():
                if "timer" in req_data and not req_data["timer"].done():
                    req_data["timer"].cancel()
        state = ClientState(reader, writer)
        self.sessions[park_id] = state
        self.writer_to_park_id[writer] = park_id
        logging.info(f"Session added for parking lot ID: {park_id}")

    def remove_session_by_writer(self, writer: asyncio.StreamWriter):
        """Writer 객체를 기반으로 클라이언트 세션을 제거합니다."""
        park_id = self.writer_to_park_id.pop(writer, None)
        if park_id and park_id in self.sessions:
            state = self.sessions.pop(park_id)
            # 해당 세션에 남아있던 타임아웃 타이머들을 모두 정리합니다.
            for req_data in state.pending_requests.values():
                if "timer" in req_data and not req_data["timer"].done():
                    req_data["timer"].cancel()
            logging.info(f"Session removed and resources cleaned for parking lot ID: {park_id}")
        writer.close()

    async def send_message(self, park_id: int, message: dict) -> bool:
        """특정 주차장 클라이언트에게 JSON 메시지를 전송합니다."""
        state = self.sessions.get(park_id)
        if state:
            try:
                json_message = json.dumps(message)
                encoded_message = json_message.encode('utf-8')
                logging.info(f"SOCKET_WRITE :: Sending to park {park_id} -> {json_message}")
                # [길이(4바이트)] + [메시지 본문] 형식으로 전송
                state.writer.write(len(encoded_message).to_bytes(4, 'big') + encoded_message)
                await state.writer.drain()
                logging.info(f"Message sent to park {park_id}: {json_message}")
                return True
            except (ConnectionResetError, BrokenPipeError) as e:
                # [개선] 메시지를 보내려는데 연결이 이미 끊긴 경우, 에러 대신 정보성 로그를 남깁니다.
                logging.info(f"Could not send message to park {park_id}, connection was already closed: {e}")
                self.remove_session_by_writer(state.writer)
                return False
            except Exception as e:
                logging.error(f"Failed to send message to park {park_id}: {e}")
                self.remove_session_by_writer(state.writer)
                return False
        else:
            logging.warning(f"No active session for park ID {park_id} to send message.")
            return False

    async def _handle_request_timeout(self, park_id: int, request_seq: int):
        """지정된 시간이 지나도 클라이언트로부터 응답이 없을 경우 타임아웃 처리를 합니다."""
        await asyncio.sleep(REQUEST_TIMEOUT_SECONDS)
        if park_id not in self.sessions: return
        state = self.sessions[park_id]
        request_info = state.pending_requests.pop(request_seq, None)
        if not request_info: return
        
        parking_request_id = request_info["request_id"]
        request_type = request_info["request_type"]
        logging.warning(f"Timeout for {request_type} request seq {request_seq} at park {park_id}. Triggering Fallback.")
        if request_type == models.RequestType.PULL_IN:
            parking_function.process_parking_fallback(parking_request_id)
        elif request_type == models.RequestType.PULL_OUT:
            parking_function.process_pull_out_fallback(parking_request_id)

    async def send_pull_in_request(self, request_id: int) -> bool:
        """LPR 클라이언트로 입차 감지(cmd: 2)를 요청합니다."""
        db = self.get_db_session()
        try:
            parking_request = db.query(models.ParkingRequest).get(request_id)
            if not parking_request:
                logging.error(f"[API] ParkingRequest not found for ID: {request_id}")
                return False
            park_id = parking_request.parking_lot_id
            state = self.sessions.get(park_id)
            if not state:
                logging.error(f"[API] No active session for park ID {park_id}.")
                return False
            state.request_seq_counter += 1
            request_seq = state.request_seq_counter
            message = {"cmd": 2, "parkId": park_id, "requestSeq": request_seq}
            if await self.send_message(park_id, message):
                # 요청을 보낸 후 타임아웃 타이머를 시작하고, pending_requests에 등록
                timer_task = asyncio.create_task(self._handle_request_timeout(park_id, request_seq))
                state.pending_requests[request_seq] = {
                    "request_id": request_id, 
                    "timer": timer_task,
                    "request_type": models.RequestType.PULL_IN
                }
                logging.info(f"Sent pull-in request for park_id {park_id} with new seq {request_seq}.")
                return True
            return False
        finally:
            db.close()

    async def send_pull_out_request(self, request_id: int) -> bool:
        """LPR 클라이언트로 출차 확인(cmd: 5)을 요청합니다."""
        db = self.get_db_session()
        try:
            parking_request = db.query(models.ParkingRequest).get(request_id)
            if not parking_request or not parking_request.spot_widget_id:
                logging.error(f"[API] Valid ParkingRequest not found for ID: {request_id}")
                return False
            park_id = parking_request.parking_lot_id
            state = self.sessions.get(park_id)
            if not state:
                logging.error(f"[API] No active session for park ID {park_id}.")
                return False
            state.request_seq_counter += 1
            request_seq = state.request_seq_counter
            message = {"cmd": 5, "parkId": park_id, "requestSeq": request_seq, "surfaceId": parking_request.spot_widget_id}
            if await self.send_message(park_id, message):
                timer_task = asyncio.create_task(self._handle_request_timeout(park_id, request_seq))
                state.pending_requests[request_seq] = {
                    "request_id": request_id, 
                    "timer": timer_task,
                    "request_type": models.RequestType.PULL_OUT
                }
                logging.info(f"Sent pull-out verification request for park_id {park_id} with new seq {request_seq}.")
                return True
            return False
        finally:
            db.close()

    async def _heartbeat_loop(self):
        """모든 연결된 클라이언트에게 주기적으로 하트비트 메시지(Ping)를 보냅니다."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            logging.info(f"Sending heartbeats to {len(self.sessions)} clients...")
            heartbeat_message = {"cmd": 4, "requestSeq": 1}
            current_park_ids = list(self.sessions.keys())
            for park_id in current_park_ids:
                await self.send_message(park_id, heartbeat_message)

    def start_heartbeat(self):
        """하트비트 루프를 시작합니다."""
        if not self.heartbeat_task or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logging.info("Heartbeat task started.")

session_manager: Optional[TCPSessionManager] = None

async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """개별 클라이언트 연결을 처리하는 메인 핸들러 함수입니다."""
    addr = writer.get_extra_info('peername')
    logging.info(f"New TCP connection from {addr}")
    authenticated_park_id = None
    
    try:
        while True:
            # 1. 메시지 길이(헤더)를 먼저 읽음
            len_data = await reader.readexactly(4)
            message_length = int.from_bytes(len_data, 'big')
            # 2. 헤더에서 얻은 길이만큼 본문을 읽음
            message_data = await reader.readexactly(message_length)
            
            raw_message = message_data.decode('utf-8', 'ignore')
            logging.info(f"SOCKET_READ :: Received from {addr} ({message_length} bytes) -> {raw_message}")
            
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                logging.error(f"JSON DECODE ERROR :: Received malformed data from {addr}. Data: {raw_message}")
                continue

            cmd = message.get("cmd")
            db: Optional[Session] = None

            try:
                if cmd == 1 and not authenticated_park_id:
                    # 인증(cmd: 1) 처리
                    device_id = message.get("parkId")
                    if device_id:
                        db = session_manager.get_db_session()
                        parking_lot_id = lpr_function.validate_device_and_get_lot_id(db, device_id)
                        if parking_lot_id:
                            session_manager.add_session(parking_lot_id, reader, writer)
                            lpr_function.update_cctv_info(db, device_id, message.get("cameraList", []))
                            response = {"cmd": 1, "requestSeq": message.get("requestSeq"), "parkId": device_id, "code": 0}
                            await session_manager.send_message(parking_lot_id, response)
                            authenticated_park_id = parking_lot_id
                        else:
                            # DB에 등록되지 않은 장비
                            logging.warning(f"Authentication failed for unregistered deviceId {device_id} from {addr}")
                            response = {"cmd": 1, "requestSeq": message.get("requestSeq"), "parkId": device_id, "code": 2}
                            json_msg = json.dumps(response).encode('utf-8')
                            writer.write(len(json_msg).to_bytes(4, 'big') + json_msg)
                            await writer.drain()
                            break # 연결 종료
                    else:
                        logging.warning(f"Authentication failed: no parkId(deviceId) from {addr}")
                        break
                
                elif authenticated_park_id:
                    state = session_manager.sessions.get(authenticated_park_id)
                    if not state: break

                    if cmd == 3:
                        # 입차 감지 결과(cmd: 3) 처리
                        db = session_manager.get_db_session()
                        request_seq = message.get("eventSeq")
                        
                        request_info = state.pending_requests.get(request_seq)
                        if not request_info:
                            logging.warning(f"[TCP] Received cmd:3 for an unknown/already processed eventSeq: {request_seq}. Ignoring.")
                            continue

                        # 클라이언트에 ACK 응답 전송
                        ack_response = {"cmd": 3, "eventSeq": request_seq, "requestSeq": message.get("requestSeq"), "parkId": authenticated_park_id, "code": 0}
                        await session_manager.send_message(authenticated_park_id, ack_response)

                        parking_request_id = request_info["request_id"]
                        parking_request = db.query(models.ParkingRequest).get(parking_request_id)

                        if not parking_request or parking_request.request_status != models.RequestStatus.PENDING:
                            logging.warning(f"[TCP] parking_request {parking_request_id} is no longer PENDING. Cleaning up.")
                            timer = request_info.get("timer")
                            if timer and not timer.done(): timer.cancel()
                            state.pending_requests.pop(request_seq, None)
                            continue

                        # 클라이언트가 보낸 차량 목록을 받음
                        car_list_from_client = message.get("carList", [])
                        logging.warning(f"[LPR_RESULT] For request {parking_request_id}, received carList: {car_list_from_client}")
                        
                        found_match = False
                        
                        # 클라이언트가 보낸 차량 목록을 순회하며 우리가 찾던 차량이 있는지 확인
                        for car_info in car_list_from_client:
                            car_no_from_client = car_info.get("carNo", "")
                            
                            # 요청된 차량 번호와 클라이언트가 찾은 차량 번호의 마지막 4자리를 비교
                            req_digits = lpr_function.extract_last_digits(parking_request.car_number)
                            lpr_digits = lpr_function.extract_last_digits(car_no_from_client)

                            if req_digits and lpr_digits and req_digits in lpr_digits:
                                # 일치하는 차량 발견!
                                logging.info(f"[TCP_MATCH] Found matching car for request {parking_request_id}: {car_info}")
                                
                                # 성공 처리 로직 호출
                                timer = request_info.get("timer")
                                if timer and not timer.done(): timer.cancel()
                                
                                if lpr_function.process_lpr_parking_event(db, parking_request, car_info):
                                    user_info = parking_function._get_parking_lot_user_info(db, parking_request.create_by, parking_request.parking_lot_id)
                                    push_event = schemas.PullInPushEvent(
                                        user_id=parking_request.create_by,
                                        parking_lot_id=parking_request.parking_lot_id,
                                        user_nickname=user_info.user_nickname if user_info else "사용자",
                                        car_number=parking_request.car_number
                                    )
                                    asyncio.create_task(lpr_function.send_pull_in_push_notification(push_event))
                                
                                found_match = True
                                break # 일치하는 차량을 찾았으므로 루프 종료

                        if not found_match:
                            # 목록 전체를 확인했지만 일치하는 차량이 없는 경우 -> Fallback 처리
                            logging.warning(f"[TCP_NO_MATCH] No matching car found in carList for request {parking_request_id}. Triggering fallback.")
                            timer = request_info.get("timer")
                            if timer and not timer.done(): timer.cancel()
                            parking_function.process_parking_fallback(parking_request_id)

                        state.pending_requests.pop(request_seq, None)
                    
                    elif cmd == 6:
                        # 출차 확인 결과(cmd: 6) 처리
                        db = session_manager.get_db_session()
                        event_seq = message.get("eventSeq")
                        request_info = state.pending_requests.get(event_seq)
                        if not request_info: continue
                        
                        parking_request_id = request_info["request_id"]
                        is_present_from_client = message.get("isPresent")
                        logging.warning(f"[LPR_PULL_OUT_RESULT] For request {parking_request_id}, isPresent: {is_present_from_client}")

                        parking_request = db.query(models.ParkingRequest).get(parking_request_id)
                        if not parking_request or parking_request.request_status != models.RequestStatus.PENDING: continue

                        timer = request_info.get("timer")
                        if timer and not timer.done(): timer.cancel()

                        if is_present_from_client is False:
                            # CCTV가 "차 없음"으로 응답 -> 정상 출차 처리 (Fallback 호출)
                            logging.info(f"[TCP] Pull-out for {parking_request_id} confirmed by CCTV. Processing.")
                            # process_pull_out_fallback은 내부에서 푸시를 보낼지 여부를 결정하지 않으므로, 직접 푸시 로직 호출
                            parking_function.process_pull_out_fallback(parking_request_id)
                            # 푸시 알림 발송
                            from function import notification_function
                            user_info = parking_function._get_parking_lot_user_info(db, parking_request.create_by, parking_request.parking_lot_id)
                            push_event = schemas.PullOutPushEvent(
                                user_id=parking_request.create_by,
                                parking_lot_id=parking_request.parking_lot_id,
                                user_nickname=user_info.user_nickname if user_info else "사용자",
                                car_number=parking_request.car_number
                            )
                            notification_function.handle_pull_out_event(push_event)
                        
                        elif is_present_from_client is True:
                            # CCTV가 "차 있음"으로 응답 -> 출차 실패 처리
                            logging.warning(f"[TCP] Pull-out for {parking_request_id} FAILED. Vehicle still present.")
                            parking_request.request_status = models.RequestStatus.FAIL
                            db.commit()
                        
                        else:
                            # isPresent 필드가 없는 비정상 응답 -> 안전하게 실패 처리
                            logging.error(f"[TCP] Invalid pull-out response for {parking_request_id}. Marking as FAIL.")
                            parking_request.request_status = models.RequestStatus.FAIL
                            db.commit()
                
                        state.pending_requests.pop(event_seq, None)

                else:
                    logging.warning(f"Unauthenticated message from {addr}. Closing.")
                    break
            
            finally:
                if db:
                    db.close()
                    
    except (asyncio.IncompleteReadError, ConnectionResetError):
        # [개선] 클라이언트의 정상적인 연결 종료는 INFO 레벨로 기록하여 로그를 깔끔하게 유지합니다.
        logging.info(f"Client {addr} closed the connection.")
    except Exception as e:
        # [개선] 그 외 예상치 못한 모든 에러는 ERROR 레벨로 기록하여 즉시 파악할 수 있도록 합니다.
        logging.error(f"An unexpected error occurred with client {addr}: {e}", exc_info=True)
    finally:
        logging.info(f"Closing connection with {addr}")
        if writer: session_manager.remove_session_by_writer(writer)

async def start_tcp_server(host: str, port: int, db_session_factory: Callable[[], Session]):
    """TCP 서버를 시작하고 전역 session_manager를 초기화합니다."""
    global session_manager
    session_manager = TCPSessionManager(db_session_factory)
    server = await asyncio.start_server(handle_tcp_client, host, port)
    logging.info(f"TCP Server started on {host}:{port}")
    session_manager.start_heartbeat()
    async with server:
        await server.serve_forever()

