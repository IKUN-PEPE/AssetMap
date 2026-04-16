from huey import SqliteHuey
from app.core.config import BASE_DIR

# 使用 SQLite 作为存储后端，文件存放在项目根目录
huey = SqliteHuey(filename=str(BASE_DIR / "huey_db.sqlite3"))
