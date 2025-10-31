# app/cron_runner.py
import sys
from core.database import SessionLocal
from function import schedule_function, holiday_function
from service import push_manager

def main():
    """
    Crontab에서 호출하기 위한 스크립트.
    실행 시 인자(argument)를 받아 해당 작업을 1회만 수행하고 종료됩니다.
    """
    
    push_manager.initialize_firebase()
    
    if len(sys.argv) < 2:
        print("Error: Please provide an argument (minute, hourly, daily).")
        sys.exit(1)

    job_type = sys.argv[1]
    
    db = None
    try:
        db = SessionLocal()
        print(f"Running cron job: {job_type}")

        if job_type == "minute":
            schedule_function.run_pending_schedules(db)
        elif job_type == "hourly":
            schedule_function.run_hourly_cleanup(db)
        elif job_type == "daily":
            # 공휴일 업데이트 (고정 출차 보다 먼저 작업 필수)
            holiday_function.sync_public_holidays(db)
            # 고정 출차 업데이트
            schedule_function.apply_fixed_departure_policies(db)
            # 만료된 파일 삭제 - 현재 파일 서버 미적재로 인해 미사용
            # schedule_function.run_daily_cleanup(db)
        else:
            print(f"Error: Unknown job type '{job_type}'")

        print(f"Cron job '{job_type}' finished successfully.")

    except Exception as e:
        print(f"Error running cron job '{job_type}': {e}")
    finally:
        if db:
            db.close()

if __name__ == "__main__":
    main()