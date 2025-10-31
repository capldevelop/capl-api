# app/function/schedule_function.py

# 순환 참조 문제를 해결하기 위해 함수 내에서 필요한 모듈을 가져오도록 수정했습니다. (지연 Import)
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from core import models, schemas
from core.config import settings

import traceback


# 시간대(Timezone) 객체 정의
KST = ZoneInfo("Asia/Seoul")


def create_schedule(db: Session, event: schemas.ScheduleCreateEvent):
    """
    [수정] 새로운 스케줄을 생성합니다. (중복 방지 로직 강화)
    """
    # 동일한 내용의 PENDING 스케줄이 있는지 먼저 확인
    existing_schedule = db.query(models.Schedule).filter(
        models.Schedule.task_type == event.task_type,
        models.Schedule.type_id == event.type_id,
        models.Schedule.user_id == event.user_id,
        models.Schedule.parking_lot_id == event.parking_lot_id,
        models.Schedule.task_status == models.TaskStatus.PENDING
    ).first()

    if existing_schedule:
        # 이미 존재하면 생성하지 않고 조용히 종료
        return

    new_schedule = models.Schedule(
        execute_time=event.execute_time,
        task_type=event.task_type,
        type_id=event.type_id,
        task_status=models.TaskStatus.PENDING,
        user_id=event.user_id,
        parking_lot_id=event.parking_lot_id
    )
    db.add(new_schedule)
    db.commit()

def delete_schedule(db: Session, event: schemas.ScheduleDeleteEvent):
    """
    [수정] 보류 중인 '출차 관련' 스케줄을 모두 삭제합니다.
    type_id (parking_id)를 기준으로 PULL_OUT_BEFORE와 PULL_OUT_AFTER를 함께 삭제합니다.
    """
    schedules_to_delete = db.query(models.Schedule).filter(
        models.Schedule.task_type.in_([models.TaskType.PULL_OUT_BEFORE, models.TaskType.PULL_OUT_AFTER]),
        models.Schedule.type_id == event.type_id,
        models.Schedule.task_status == models.TaskStatus.PENDING
    ).all()

    if schedules_to_delete:
        for schedule in schedules_to_delete:
            db.delete(schedule)
        db.commit()


def _process_pull_out_notification(db: Session, schedule: models.Schedule):
    """
    [수정] 출차 알림 스케줄을 처리하고, 실제 푸시 알림 함수를 호출합니다.
    """
    from . import notification_function # 지연 Import
    
    car_number = None # 기본값은 None
    
    try:
        # [수정] 스케줄 타입에 따라 차량 번호 조회 방식 변경
        if schedule.task_type in [models.TaskType.PULL_OUT_BEFORE, models.TaskType.PULL_OUT_AFTER]:
            # 개별 알림: type_id는 parking_id 이므로, parking 테이블에서 차량 번호 조회
            parking = db.query(models.Parking).filter(
                models.Parking.parking_id == schedule.type_id,
                models.Parking.del_yn == models.YnType.N
            ).first()
            if not parking:
                schedule.task_status = models.TaskStatus.COMPLETE
                db.commit()
                return
            car_number = parking.car_number
        
        # 통합 알림의 경우, car_number는 None으로 유지되어 차량 번호 없이 알림이 감

        # 알림 전송을 위한 이벤트 데이터 생성
        event = schemas.ScheduledPushEvent(
            user_id=schedule.user_id,
            parking_lot_id=schedule.parking_lot_id,
            car_number=car_number # 조회된 차량 번호 또는 None
        )

        # 스케줄 타입에 따라 적절한 알림 핸들러 호출
        if schedule.task_type in [models.TaskType.PULL_OUT_BEFORE, models.TaskType.FIXED_PULL_OUT_BEFORE]:
            notification_function.handle_pull_out_reminder_event(db, event)
        elif schedule.task_type in [models.TaskType.PULL_OUT_AFTER, models.TaskType.FIXED_PULL_OUT_AFTER]:
            notification_function.handle_pull_out_due_event(db, event)

        # 작업 완료 상태로 변경
        schedule.task_status = models.TaskStatus.COMPLETE
        db.commit()

    except Exception as e:
        # [신규] 어떤 에러가 발생했는지 로그를 남깁니다.
        print(f"Error in _process_pull_out_notification for schedule_id {schedule.task_id}: {e}")
        traceback.print_exc()
        
        schedule.task_status = models.TaskStatus.FAIL
        db.commit()


def _process_vote_end(db: Session, schedule: models.Schedule):
    """투표 종료 스케줄을 처리합니다."""
    try:
        vote = db.query(models.Vote).filter(
            models.Vote.vote_id == schedule.type_id,
            models.Vote.del_yn == models.YnType.N
        ).first()
        if vote and vote.active_yn == models.YnType.Y:
            vote.active_yn = models.YnType.N
            vote.update_by = schedule.user_id
        schedule.task_status = models.TaskStatus.COMPLETE
        db.commit()
    except Exception:
        schedule.task_status = models.TaskStatus.FAIL
        db.commit()


# =================================================================
# 주기적 실행 함수 (Java의 @Scheduled 역할)
# =================================================================

def run_pending_schedules(db: Session):
    """[매분 실행] 예약된 작업을 처리합니다. (REQUESTED 상태 적용)"""
    now_kst_naive = datetime.now(KST).replace(tzinfo=None)
    schedules_to_process = []

    try:
        schedules_to_run = db.query(models.Schedule).filter(
            models.Schedule.task_status == models.TaskStatus.PENDING,
            models.Schedule.execute_time <= now_kst_naive
        ).with_for_update().all()
      
        if not schedules_to_run:
            return # 처리할 스케줄이 없으면 조용히 종료
        
        # 찾은 작업들의 상태를 REQUESTED로 변경하고, 처리할 목록에 추가
        for schedule in schedules_to_run:
            schedule.task_status = models.TaskStatus.REQUESTED
            schedules_to_process.append(schedule)
        
        db.commit() # 여기서 commit하여 잠금을 해제하고 상태 변경을 확정

    except Exception as e:
        db.rollback() # 잠그는 과정에서 에러 발생 시 롤백
        print(f"Error while locking schedules: {e}")
        return

    # 작업 실행
    for schedule in schedules_to_process:
        try:
            if schedule.task_type in [
                models.TaskType.PULL_OUT_BEFORE, models.TaskType.PULL_OUT_AFTER,
                models.TaskType.FIXED_PULL_OUT_BEFORE, models.TaskType.FIXED_PULL_OUT_AFTER
            ]:
                _process_pull_out_notification(db, schedule)
            elif schedule.task_type == models.TaskType.VOTE_END_AT:
                _process_vote_end(db, schedule)
            else:
                schedule.task_status = models.TaskStatus.FAIL
                db.commit()
        except Exception as e:
            # 개별 작업 처리 중 에러가 발생해도 다른 작업에 영향을 주지 않도록 예외 처리
            print(f"Error processing individual schedule_id {schedule.task_id}: {e}")
            traceback.print_exc()
            schedule.task_status = models.TaskStatus.FAIL
            db.commit()

def apply_fixed_departure_policies(db: Session):
    """
    [매일 자정 실행] 고정 출차 정책을 현재 주차된 차량에 적용합니다.
    """
    from . import notification_function

    today_kst = date.today()
    is_holiday = db.query(models.Holiday).filter(models.Holiday.holiday == today_kst).first() is not None
    today_week_index = (today_kst.weekday() + 1) % 7

    users_with_policy = db.query(models.ParkingLotUser).filter(
        models.ParkingLotUser.pull_out_time_yn == models.YnType.Y,
        models.ParkingLotUser.pull_out_end_time.isnot(None),
        models.ParkingLotUser.del_yn == models.YnType.N
    ).all()

    for user in users_with_policy:
        # 스케줄을 생성하기 전에, 이 사용자가 현재 로그인 상태인지 확인합니다.
        active_login_session = db.query(models.LoginInfo).filter(
            models.LoginInfo.user_id == user.user_id
        ).first()

        if not active_login_session:
            continue # 로그인 기록이 없으면(로그아웃 상태), 이 사용자에 대한 모든 작업을 건너뜁니다.
        
        if user.holiday_exclude_yn == models.YnType.Y and is_holiday:
            continue
            
        if not (user.pull_out_week and len(user.pull_out_week) == 7 and user.pull_out_week[today_week_index] == '1'):
            continue
            
        eligible_car_exists = db.query(models.Parking).join(models.Widget).filter(
            models.Widget.parking_lot_id == user.parking_lot_id,
            models.Parking.create_by == user.user_id,
            models.Parking.del_yn == models.YnType.N,
            models.Parking.pull_out_end_at.is_(None)
        ).first()

        if not eligible_car_exists:
            continue

        now_kst = datetime.now(KST)
        pull_out_end_at_kst = datetime.combine(today_kst, user.pull_out_end_time).replace(tzinfo=KST)
        
        if pull_out_end_at_kst < now_kst:
            continue

        pull_out_start_at_kst = pull_out_end_at_kst - timedelta(minutes=30)
        
        # 30분 전 통합 알림 스케줄 생성 (알림 설정 ON일 때만)
        if notification_function.is_notification_active(db, user_id=user.user_id, parking_lot_id=user.parking_lot_id, notification_id=3):
            if pull_out_start_at_kst > now_kst:
                before_event = schemas.ScheduleCreateEvent(
                    user_id=user.user_id, parking_lot_id=user.parking_lot_id,
                    task_type=models.TaskType.FIXED_PULL_OUT_BEFORE,
                    type_id=user.user_id,
                    # [수정] UTC 변환 로직 제거, KST aware 시간을 naive하게 저장
                    execute_time=pull_out_start_at_kst.replace(tzinfo=None)
                )
                create_schedule(db, before_event)

        # 정시 통합 알림 스케줄 생성 (알림 설정 ON일 때만)
        if notification_function.is_notification_active(db, user_id=user.user_id, parking_lot_id=user.parking_lot_id, notification_id=4):
            after_event = schemas.ScheduleCreateEvent(
                user_id=user.user_id, parking_lot_id=user.parking_lot_id,
                task_type=models.TaskType.FIXED_PULL_OUT_AFTER,
                type_id=user.user_id,
                # [수정] UTC 변환 로직 제거, KST aware 시간을 naive하게 저장
                execute_time=pull_out_end_at_kst.replace(tzinfo=None)
            )
            create_schedule(db, after_event)


def run_hourly_cleanup(db: Session):
    """[매시 실행] 만료된 임시 사용자를 삭제합니다."""
    now = datetime.now(KST)
    # 1. 기존의 임시 사용자 삭제 로직
    try:
        expired_count = db.query(models.PhoneAuthTempUser).filter(
            models.PhoneAuthTempUser.expire_at <= now
        ).delete(synchronize_session=False)
        db.commit()
        if expired_count > 0:
            print(f"Cleaned up {expired_count} expired temporary users.")
    except Exception as e:
        db.rollback()
        print(f"Error during hourly temp user cleanup: {e}")

    # 2. [신규] 만료된 토큰 정리 로직 (제안해주신 아이디어)
    from . import login_function
    
    try:
        # Refresh Token의 만료 기간(예: 7일)을 기준으로, 그보다 오래된 세션을 찾습니다.
        # cutoff_date = now - timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
        # 테스트로 1개월만 적용
        cutoff_date = now - timedelta(days=30)
        
        # [핵심 수정] update_at 대신 create_at을 기준으로 만료된 세션을 찾습니다.
        expired_sessions = db.query(models.LoginInfo).filter(
            models.LoginInfo.create_at < cutoff_date
        ).all()

        if not expired_sessions:
            return # 정리할 세션이 없으면 종료

        print(f"Found {len(expired_sessions)} expired login sessions to clean up.")
        for session in expired_sessions:
            # 기존 logout 함수를 재사용하여 SNS Endpoint 삭제 및 DB 레코드 삭제를 한 번에 처리합니다.
            print(f"  - Deleting session for user_id={session.user_id}, device_uuid={session.login_device_uuid}")
            login_function.logout(db, session.user_id, session.login_device_uuid)
        
        print("Expired login session cleanup finished.")

    except Exception as e:
        # logout 함수가 개별 commit을 하므로 rollback은 불필요
        print(f"Error during hourly token cleanup: {e}")


def run_daily_cleanup(db: Session):
    """[매일 자정 실행] 만료된 파일을 삭제합니다."""
    # 채팅 기능 미사용으로 현재는 호출되지 않음
    return

