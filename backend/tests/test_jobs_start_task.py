from types import SimpleNamespace

from app.api import jobs as jobs_api


class FakeDb:
    def __init__(self, job):
        self.job = job
        self.commit_count = 0

    def get(self, model, job_id):
        return self.job if job_id == self.job.id else None

    def commit(self):
        self.commit_count += 1


def test_start_task_dispatches_collect_job_in_process(monkeypatch):
    job = SimpleNamespace(id="job-1", status="success")
    db = FakeDb(job)
    launched: dict[str, object] = {}

    monkeypatch.setattr(
        jobs_api,
        "run_in_process",
        lambda task, *args, delay=0: launched.update(
            task=task,
            args=args,
            delay=delay,
        ),
        raising=False,
    )

    result = jobs_api.start_task("job-1", db)

    assert job.status == "running"
    assert db.commit_count == 1
    assert launched["args"] == ("job-1",)
    assert launched["delay"] == 1
    assert result == {"message": "Job started in background", "job_id": "job-1"}
