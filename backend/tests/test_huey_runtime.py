from threading import Event

from app.core import huey as huey_runtime


def test_run_in_process_calls_task_locally():
    event = Event()
    captured: dict[str, object] = {}

    class FakeTask:
        def call_local(self, *args):
            captured["args"] = args
            event.set()

    thread = huey_runtime.run_in_process(FakeTask(), "job-1", delay=0)

    assert thread.daemon is True
    assert event.wait(1)
    assert captured["args"] == ("job-1",)
