"""Isolated UI test host. All FACEIT requests are intercepted before transport."""

import sys
from pathlib import Path

import uvicorn

from backend import worker
from backend.api import create
from backend.db import Store
from backend.secrets import Vault
from tests.conftest import fixture_client


def main():
    path, port = sys.argv[1], int(sys.argv[2])
    store = Store(path)
    vault = Vault(store.root)
    worker.FaceitClient = fixture_client
    engine = worker.Engine(store, vault)
    app = create(
        store, vault, engine, "ui-test-only", f"127.0.0.1:{port}", Path("frontend/dist")
    )
    engine.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
