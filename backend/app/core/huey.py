import threading
import time

from huey import SqliteHuey

from app.core.config import BASE_DIR

huey = SqliteHuey(filename=str(BASE_DIR / "huey_db.sqlite3"))


def run_in_process(task, *args, delay: int | float = 0):
    def runner():
        if delay:
            time.sleep(delay)
        task.call_local(*args)

    thread = threading.Thread(
        target=runner,
        daemon=True,
        name=f"huey-local-{getattr(task, 'name', 'task')}",
    )
    thread.start()
    return thread


from app.tasks import collect  # noqa: E402,F401
