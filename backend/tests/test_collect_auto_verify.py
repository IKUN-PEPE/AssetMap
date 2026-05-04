from types import SimpleNamespace

from app.tasks import collect


class FakeQuery:
    def __init__(self, job):
        self.job = job

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.job

    def all(self):
        return []


class FakeDb:
    def __init__(self, job):
        self.job = job
        self.commit_count = 0
        self.closed = False

    def query(self, model):
        return FakeQuery(self.job)

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


def test_run_collect_task_dispatches_auto_verify_in_process(monkeypatch):
    job = SimpleNamespace(
        id="job-1",
        status="pending",
        started_at=None,
        finished_at=None,
        error_message=None,
        progress=0,
        sources=[],
        query_payload={"queries": []},
        auto_verify=True,
    )
    fake_db = FakeDb(job)
    launched: dict[str, object] = {}

    monkeypatch.setattr(collect, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(
        collect,
        "run_in_process",
        lambda task, *args, delay=0: launched.update(task=task, args=args, delay=delay),
        raising=False,
    )

    collect.run_collect_task.call_local("job-1")

    assert job.status == "success"
    assert launched["args"] == ("job-1",)
    assert launched["delay"] == 2
    assert fake_db.closed is True
