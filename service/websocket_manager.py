from typing import Dict, List
from fastapi import WebSocket

class WebSocketManager:
    """
    실시간 WebSocket 연결을 관리하는 클래스.
    [수정] 어떤 사용자가(user_id) 어떤 주차장 채팅방에(parking_lot_id) 연결되어 있는지 추적합니다.
    """
    def __init__(self):
        # [수정] 데이터 구조 변경: {parking_lot_id: {user_id: WebSocket}}
        # user_id를 키로 사용하여 특정 사용자를 식별할 수 있도록 합니다.
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, parking_lot_id: int, user_id: int):
        """[수정] 사용자 ID와 함께 WebSocket 연결을 등록합니다."""
        await websocket.accept()
        if parking_lot_id not in self.active_connections:
            self.active_connections[parking_lot_id] = {}
        self.active_connections[parking_lot_id][user_id] = websocket
        print(f"User {user_id} connected to chat room {parking_lot_id}.")

    def disconnect(self, parking_lot_id: int, user_id: int):
        """[수정] 사용자 ID를 기반으로 WebSocket 연결을 해제합니다."""
        if parking_lot_id in self.active_connections and user_id in self.active_connections[parking_lot_id]:
            del self.active_connections[parking_lot_id][user_id]
            # 만약 룸에 아무도 없으면 룸 자체를 삭제합니다.
            if not self.active_connections[parking_lot_id]:
                del self.active_connections[parking_lot_id]
            print(f"User {user_id} disconnected from chat room {parking_lot_id}.")

    async def broadcast_to_room(self, message: str, parking_lot_id: int, sender_id: int):
        """[수정] 방에 있는 모든 사용자에게 메시지를 브로드캐스트합니다. (발신자 제외)"""
        if parking_lot_id in self.active_connections:
            for user_id, connection in self.active_connections[parking_lot_id].items():
                if user_id != sender_id:
                    await connection.send_text(message)

    def get_connected_user_ids(self, parking_lot_id: int) -> List[int]:
        """[추가] 특정 채팅방에 현재 연결된 모든 사용자의 ID 목록을 반환합니다."""
        if parking_lot_id in self.active_connections:
            return list(self.active_connections[parking_lot_id].keys())
        return []

# 싱글턴 인스턴스로 관리
manager = WebSocketManager()

