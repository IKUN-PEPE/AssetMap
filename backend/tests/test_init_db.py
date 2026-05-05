import init_db


class DummyDb:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.committed = 0
        self.closed = False

    def execute(self, statement) -> None:
        self.executed.append(str(statement))

    def commit(self) -> None:
        self.committed += 1

    def close(self) -> None:
        self.closed = True


def test_drop_legacy_selection_tables_executes_expected_sql():
    db = DummyDb()

    init_db.drop_legacy_selection_tables(db)

    assert db.executed == [
        "DROP TABLE IF EXISTS selection_items",
        "DROP TABLE IF EXISTS saved_selections",
    ]
    assert db.committed == 1


def test_init_database_runs_schema_setup_and_closes_session(monkeypatch):
    db = DummyDb()
    calls: list[str] = []

    monkeypatch.setattr(init_db, "SessionLocal", lambda: db)
    monkeypatch.setattr(init_db, "create_all_tables", lambda drop_all=False: calls.append(f"create:{drop_all}"))
    monkeypatch.setattr(init_db, "wait_for_database", lambda *args, **kwargs: calls.append("wait"))
    monkeypatch.setattr(init_db, "drop_legacy_selection_tables", lambda session: calls.append("drop"))
    monkeypatch.setattr(
        init_db.SystemConfigService,
        "init_defaults",
        lambda session: calls.append("defaults"),
    )

    init_db.init_database()

    assert calls == ["wait", "create:False", "drop", "defaults"]
    assert db.closed is True
