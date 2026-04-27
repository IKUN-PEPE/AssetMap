from types import SimpleNamespace

from app.api import jobs as jobs_api


class CountQuery:
    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return 0


class FakeDb:
    def query(self, model):
        assert model is jobs_api.SourceObservation
        return CountQuery()


def test_summarize_task_details_prefers_zero_db_counts_over_stale_log_counts(monkeypatch):
    job = SimpleNamespace(id="job-1", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 1,
            "verify_started_count": 1,
            "screenshot_started_count": 1,
            "verify_success": 1,
            "verify_failed": 0,
            "screenshot_success": 1,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Verify failed asset_id=x\nScreenshot failed asset_id=x\n",
        db,
    )

    assert details.post_process.verify.failed == 0
    assert details.post_process.screenshot.failed == 0


def test_summarize_task_details_only_falls_back_when_db_counts_are_missing(monkeypatch):
    job = SimpleNamespace(id="job-2", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": None,
            "verify_started_count": None,
            "screenshot_started_count": None,
            "verify_success": None,
            "verify_failed": None,
            "screenshot_success": None,
            "screenshot_failed": None,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Verify success asset_id=x\nVerify failed asset_id=x\nScreenshot success asset_id=x\nScreenshot failed asset_id=x\n",
        db,
    )

    assert details.post_process.verify.success == 1
    assert details.post_process.verify.failed == 1
    assert details.post_process.screenshot.success == 1
    assert details.post_process.screenshot.failed == 1


def test_summarize_task_details_keeps_verify_and_screenshot_pending_before_post_process_start(monkeypatch):
    job = SimpleNamespace(id="job-3", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 2,
            "verify_started_count": 0,
            "screenshot_started_count": 0,
            "verify_success": 0,
            "verify_failed": 0,
            "screenshot_success": 0,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "",
        db,
    )

    assert details.post_process.verify.started is False
    assert details.post_process.verify.state == "pending"
    assert details.post_process.verify.last_error is None
    assert details.post_process.screenshot.started is False
    assert details.post_process.screenshot.state == "pending"
    assert details.post_process.screenshot.last_error is None


def test_summarize_task_details_marks_verify_started_when_post_process_really_begins(monkeypatch):
    job = SimpleNamespace(id="job-4", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 2,
            "verify_started_count": 1,
            "screenshot_started_count": 0,
            "verify_success": 0,
            "verify_failed": 0,
            "screenshot_success": 0,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(job, "Auto verify start\n", db)

    assert details.post_process.verify.started is True
    assert details.post_process.verify.finished is False
    assert details.post_process.verify.state == "running"


def test_summarize_task_details_marks_screenshot_started_when_current_stage_has_results(monkeypatch):
    job = SimpleNamespace(id="job-5", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 2,
            "verify_started_count": 1,
            "screenshot_started_count": 1,
            "verify_success": 1,
            "verify_failed": 0,
            "screenshot_success": 0,
            "screenshot_failed": 1,
            "verify_last_error": None,
            "screenshot_last_error": "missing",
        },
    )

    details = jobs_api._summarize_task_details(job, "", db)

    assert details.post_process.screenshot.started is True
    assert details.post_process.screenshot.failed == 1
    assert details.post_process.screenshot.finished is True


def test_summarize_task_details_keeps_stage_running_until_all_started_assets_finish(monkeypatch):
    job = SimpleNamespace(id="job-7", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 3,
            "verify_started_count": 3,
            "screenshot_started_count": 2,
            "verify_success": 1,
            "verify_failed": 0,
            "screenshot_success": 1,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Auto verify start\nScreenshot post-process start\n",
        db,
    )

    assert details.post_process.verify.started is True
    assert details.post_process.verify.finished is False
    assert details.post_process.verify.state == "running"
    assert details.post_process.screenshot.started is True
    assert details.post_process.screenshot.finished is False
    assert details.post_process.screenshot.state == "running"
    assert details.post_process.state == "running"


def test_summarize_task_details_uses_log_stage_markers_only_when_db_stage_is_unknown(monkeypatch):
    job = SimpleNamespace(id="job-6", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": None,
            "verify_started_count": None,
            "screenshot_started_count": None,
            "verify_success": None,
            "verify_failed": None,
            "screenshot_success": None,
            "screenshot_failed": None,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Auto verify start\nScreenshot post-process start\n",
        db,
    )

    assert details.post_process.verify.started is True
    assert details.post_process.screenshot.started is True


def test_summarize_task_details_uses_log_markers_when_stage_counts_are_zero_but_logs_show_progress(monkeypatch):
    job = SimpleNamespace(id="job-8", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 0,
            "verify_started_count": 0,
            "screenshot_started_count": 0,
            "verify_success": 0,
            "verify_failed": 0,
            "screenshot_success": 0,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Auto verify start\nVerify failed asset_id=x reason=timeout\nVerify post-process finished success=0 failed=1\n",
        db,
    )

    assert details.post_process.verify.started is True
    assert details.post_process.verify.finished is True
    assert details.post_process.verify.state == "failed"
    assert details.post_process.verify.last_error == "timeout"


def test_summarize_task_details_uses_log_success_state_when_db_stage_counts_are_zero(monkeypatch):
    job = SimpleNamespace(id="job-9", auto_verify=True, status="success", progress=100)
    db = FakeDb()

    monkeypatch.setattr(jobs_api, "_collect_result_assets", lambda _job_id, _db: [])
    monkeypatch.setattr(
        jobs_api,
        "_collect_post_process_asset_stats",
        lambda _job_id, _db: {
            "asset_count": 0,
            "verify_started_count": 0,
            "screenshot_started_count": 0,
            "verify_success": 0,
            "verify_failed": 0,
            "screenshot_success": 0,
            "screenshot_failed": 0,
            "verify_last_error": None,
            "screenshot_last_error": None,
        },
    )

    details = jobs_api._summarize_task_details(
        job,
        "Auto verify start\nVerify success asset_id=x status=200\nVerify post-process finished success=1 failed=0\n",
        db,
    )

    assert details.post_process.verify.started is True
    assert details.post_process.verify.finished is True
    assert details.post_process.verify.state == "success"
