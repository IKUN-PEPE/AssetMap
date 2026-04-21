from app.tasks.bootstrap import create_all_tables
from app.core.db import SessionLocal
from app.services.system_service import SystemConfigService

def init():
    create_all_tables()
    db = SessionLocal()
    try:
        SystemConfigService.init_defaults(db)
        print("Default configurations initialized.")
    finally:
        db.close()

if __name__ == "__main__":
    init()
    print("Database tables created and seeded.")
