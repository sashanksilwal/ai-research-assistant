"""The safety net itself: prove the suite cannot touch real data, keys or services."""
import socket

import httpx
import pytest
from pytest_socket import SocketConnectBlockedError

from app import config, db, llm, main
from conftest import ROOT, SESSION_DATA_DIR
from helpers import run


def test_app_config_points_at_a_temporary_directory():
    assert config.DATA_DIR == SESSION_DATA_DIR
    assert not config.DATA_DIR.is_relative_to(ROOT)


def test_each_test_gets_storage_outside_the_session_and_repo(storage):
    assert db.DB_PATH == storage.db_path
    assert main.PDF_DIR == storage.pdf_dir
    assert not db.DB_PATH.is_relative_to(ROOT)


def test_no_api_key_is_visible_to_the_app():
    with pytest.raises(llm.LLMError, match="GEMINI_API_KEY is not set"):
        llm._get_client()


def test_unplanned_http_call_fails_loudly(external):
    async def call():
        async with httpx.AsyncClient() as client:
            await client.get("https://example.org/")

    with pytest.raises(AssertionError, match="Unexpected external request"):
        run(call())


def test_real_socket_to_a_remote_address_is_blocked():
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("203.0.113.1", 80), timeout=1)
