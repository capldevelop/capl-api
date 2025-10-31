# app/function/holiday_function.py
# 공휴일 정보를 API로부터 가져와 DB에 동기화하는 스크립트입니다.
# 매일 1회 실행되는 것을 전제로 합니다.

import requests
import xmltodict
from datetime import datetime, date
from calendar import monthrange
from typing import List, Optional
from zoneinfo import ZoneInfo

# SQLAlchemy 관련 import
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert
from core import models
from core.config import settings # .env 파일의 설정을 가져옵니다.

# 시간대(Timezone) 객체 정의
KST = ZoneInfo("Asia/Seoul")

# --- 1. Helper Function: API 호출 및 파싱 ---
def _fetch_and_parse_holidays(year: int, month: Optional[int] = None) -> Optional[List[str]]:
    """
    [수정] 공공 API를 호출하고 XML 응답을 파싱하여 날짜 문자열('YYYYMMDD') 리스트를 반환합니다.
    API 호출 실패 또는 API 레벨 에러 시 None을 반환합니다.
    """
    if not settings.HOLIDAY_API_URL or not settings.HOLIDAY_API_SERVICE_KEY:
        print("Holiday API URL or Service Key is not configured.")
        return None

    params = {
        'serviceKey': settings.HOLIDAY_API_SERVICE_KEY,
        'solYear': str(year)
    }
    if month:
        params['solMonth'] = str(month).zfill(2)
    else:
        params['numOfRows'] = 100 

    try:
        response = requests.get(settings.HOLIDAY_API_URL, params=params, timeout=15)
        response.raise_for_status()
        
        data_dict = xmltodict.parse(response.content.decode('utf-8'))
        
        # API 응답 헤더의 resultCode를 확인합니다.
        header = data_dict.get('response', {}).get('header', {})
        result_code = header.get('resultCode')
        
        if result_code != '00':
            result_msg = header.get('resultMsg', 'Unknown API Error')
            print(f"API returned an error: Code={result_code}, Msg={result_msg}")
            return None # API 레벨 에러 시 None을 반환하여 DB 작업을 막습니다.

        items_container = data_dict.get('response', {}).get('body', {}).get('items')
        items = []
        if items_container:
            item_data = items_container.get('item', [])
            if isinstance(item_data, dict):
                items = [item_data]
            else:
                items = item_data
        
        raw_holidays = [item['locdate'] for item in items if 'locdate' in item]
        unique_holidays = sorted(list(set(raw_holidays)))
        return unique_holidays

    except requests.exceptions.RequestException as e:
        print(f"API request failed for year={year}, month={month}: {e}")
        return None
    except Exception as e:
        print(f"An error occurred during API fetch/parse for year={year}, month={month}: {e}")
        return None


# --- 2. Helper Function: DB 작업 ---
def _delete_holidays_for_month(db: Session, year: int, month: int):
    """DB에서 특정 연/월에 해당하는 모든 공휴일 데이터를 삭제합니다."""
    # 해당 월의 첫째 날과 마지막 날 계산
    first_day = date(year, month, 1)
    last_day_of_month = monthrange(year, month)[1]
    last_day = date(year, month, last_day_of_month)
    
    try:
        deleted_count = db.query(models.Holiday).filter(
            models.Holiday.holiday.between(first_day, last_day)
        ).delete(synchronize_session=False)
        print(f"{year}년 {month}월의 기존 공휴일 {deleted_count}개를 삭제했습니다.")
    except Exception as e:
        print(f"DB 삭제 중 에러 발생: {e}")
        raise # 에러 발생 시 상위로 전파하여 롤백 처리

def _insert_holidays(db: Session, holiday_str_list: List[str]):
    """날짜 문자열 리스트를 받아 DB에 중복을 방지하며 저장합니다."""
    if not holiday_str_list:
        print("DB에 새로 추가할 공휴일이 없습니다.")
        return

    holidays_to_insert = []
    for date_str in holiday_str_list:
        try:
            holiday_date = datetime.strptime(date_str, '%Y%m%d').date()
            holidays_to_insert.append({'holiday': holiday_date})
        except ValueError:
            print(f"잘못된 날짜 형식입니다: {date_str}")

    if not holidays_to_insert:
        return

    # INSERT IGNORE를 사용하여 기본 키가 중복될 경우 무시
    stmt = insert(models.Holiday).prefix_with('IGNORE')
    
    try:
        # [핵심 수정] result.rowcount를 사용하지 않도록 변경
        db.execute(stmt, holidays_to_insert)
        print(f"DB 작업 완료. {len(holidays_to_insert)}개의 공휴일 데이터에 대한 삽입/무시 작업을 시도했습니다.")
    except Exception as e:
        print(f"DB 삽입 중 에러 발생: {e}")
        raise # 에러 발생 시 상위로 전파하여 롤백 처리


# --- 3. Main Function: 전체 로직 실행 ---
def sync_public_holidays(db: Session):
    """
    날짜를 기준으로 공휴일 정보를 동기화하는 메인 함수.
    이 함수를 매일 1회 스케줄러로 호출합니다.
    """
    today = datetime.now(KST).date()
    current_year = today.year
    current_month = today.month

    try:
        # 매년 1월 1일에는 1년치 전체 데이터를 가져와서 추가 (삭제 없음)
        if today.month == 1 and today.day == 1:
            print(f"연초 작업: {current_year}년 전체 공휴일 정보를 업데이트합니다.")
            yearly_holidays = _fetch_and_parse_holidays(current_year)
            if yearly_holidays is not None: # API 호출이 성공했을 때만 실행
                _insert_holidays(db, yearly_holidays)
        
        # 그 외의 모든 날에는 현재 월의 데이터만 '삭제 후 삽입'하여 갱신
        else:
            print(f"일일 작업: {current_year}년 {current_month}월 공휴일 정보를 갱신합니다.")
            
            # 1. API에서 현재 월의 최신 공휴일 정보 먼저 가져오기
            monthly_holidays = _fetch_and_parse_holidays(current_year, current_month)
            
            # [핵심 수정] API 호출이 성공하고 데이터를 받아왔을 때만 DB 작업을 수행합니다.
            if monthly_holidays is not None:
                # 2. 현재 월의 기존 공휴일 데이터 삭제
                _delete_holidays_for_month(db, current_year, current_month)
                
                # 3. 최신 정보 삽입
                _insert_holidays(db, monthly_holidays)
            else:
                print("API로부터 공휴일 정보를 가져오지 못했으므로 DB 작업을 건너뜁니다.")

        db.commit() # 모든 작업이 성공했을 때만 최종 commit
        print("공휴일 동기화 작업이 성공적으로 완료되었습니다.")

    except Exception as e:
        print(f"공휴일 동기화 작업 중 심각한 에러 발생: {e}")
        db.rollback()

