from backend.db import Store
from backend.secrets import Vault


def test_restart_backup(tmp_path):
    store = Store(tmp_path)
    store.change({"minutes": 35})
    assert Store(tmp_path).settings()["minutes"] == 35
    assert store.backup().stat().st_size > 0


def test_vault(tmp_path):
    vault = Vault(tmp_path)
    vault.save("faceit", "unit-test-only")
    assert b"unit-test-only" not in vault.file("faceit").read_bytes()
    assert vault.read("faceit") == "unit-test-only"
    vault.save("faceit", "")
    assert vault.read("faceit") == ""
