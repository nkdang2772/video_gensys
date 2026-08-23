from sqlalchemy import text


def test_every_connection_has_sqlite_pragmas(engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1

