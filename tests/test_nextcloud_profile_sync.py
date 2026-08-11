import ast
import inspect
import logging
import textwrap

from source import nc_calendar
from source.callbacks import complete_login_flow_profile
from source.db.repos.users import NEXTCLOUD_FIELD_MISSING
from source.nc_calendar import sync_nextcloud_users_once


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_login_flow_uses_app_password_for_self_profile() -> None:
    calls: list[dict] = []
    saved: list[dict] = []

    def request_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        return FakeResponse(
            {
                "ocs": {
                    "data": {
                        "id": "alice",
                        "email": "alice@example.test",
                        "timezone": "Europe/Warsaw",
                    }
                }
            }
        )

    def save_profile(*args: object, **kwargs: object) -> None:
        saved.append({"args": args, "kwargs": kwargs})

    complete_login_flow_profile(
        42,
        {"loginName": "login-flow-user", "appPassword": "secret"},
        base_url="https://nextcloud.example.test",
        request_get=request_get,
        save_profile=save_profile,
    )

    assert calls[0]["url"].endswith("/ocs/v2.php/cloud/user")
    assert calls[0]["auth"] == ("login-flow-user", "secret")
    assert saved[0]["kwargs"]["timezone_value"] == "Europe/Warsaw"


def test_login_flow_passes_missing_timezone_sentinel() -> None:
    saved: list[dict] = []

    def request_get(_url: str, **_kwargs: object) -> FakeResponse:
        return FakeResponse(
            {
                "ocs": {
                    "data": {
                        "id": "alice",
                        "email": "alice@example.test",
                    }
                }
            }
        )

    def save_profile(*args: object, **kwargs: object) -> None:
        saved.append({"args": args, "kwargs": kwargs})

    complete_login_flow_profile(
        42,
        {"loginName": "alice", "appPassword": "secret"},
        base_url="https://nextcloud.example.test",
        request_get=request_get,
        save_profile=save_profile,
    )

    assert saved[0]["kwargs"]["timezone_value"] is NEXTCLOUD_FIELD_MISSING


def test_login_flow_does_not_log_app_password(
    caplog,
) -> None:
    def request_get(_url: str, **_kwargs: object) -> FakeResponse:
        return FakeResponse(
            {"ocs": {"data": {"id": "alice", "timezone": "UTC"}}}
        )

    with caplog.at_level(logging.DEBUG):
        complete_login_flow_profile(
            42,
            {"loginName": "alice", "appPassword": "top-secret"},
            base_url="https://nextcloud.example.test",
            request_get=request_get,
            save_profile=lambda *args, **kwargs: None,
        )

    assert "top-secret" not in caplog.text


def test_admin_sync_passes_email_and_timezone_in_one_write() -> None:
    calls: list[dict] = []

    def request_get(url: str, **_kwargs: object) -> FakeResponse:
        if url.endswith("cloud/users?limit=1000"):
            return FakeResponse({"ocs": {"data": {"users": ["alice"]}}})
        return FakeResponse(
            {
                "ocs": {
                    "data": {
                        "email": "alice@example.test",
                        "timezone": "Europe/Warsaw",
                    }
                }
            }
        )

    def update_profile(login: str, **kwargs: object) -> bool:
        calls.append({"login": login, **kwargs})
        return True

    assert (
        sync_nextcloud_users_once(
            request_get=request_get,
            update_profile=update_profile,
        )
        == 1
    )
    assert calls == [
        {
            "login": "alice",
            "email": "alice@example.test",
            "timezone_value": "Europe/Warsaw",
        }
    ]


def test_admin_sync_updates_timezone_without_email() -> None:
    calls: list[dict] = []

    def request_get(url: str, **_kwargs: object) -> FakeResponse:
        if url.endswith("cloud/users?limit=1000"):
            return FakeResponse({"ocs": {"data": {"users": ["alice"]}}})
        return FakeResponse({"ocs": {"data": {"timezone": "Asia/Kolkata"}}})

    def update_profile(login: str, **kwargs: object) -> bool:
        calls.append({"login": login, **kwargs})
        return True

    sync_nextcloud_users_once(
        request_get=request_get,
        update_profile=update_profile,
    )

    assert calls[0]["email"] is NEXTCLOUD_FIELD_MISSING
    assert calls[0]["timezone_value"] == "Asia/Kolkata"


def test_nextcloud_profile_sync_paths_are_read_only() -> None:
    methods: list[str] = []

    def request_get(url: str, **_kwargs: object) -> FakeResponse:
        methods.append("GET")
        if url.endswith("cloud/users?limit=1000"):
            return FakeResponse({"ocs": {"data": {"users": ["alice"]}}})
        return FakeResponse({"ocs": {"data": {"timezone": "UTC"}}})

    sync_nextcloud_users_once(
        request_get=request_get,
        update_profile=lambda login, **kwargs: True,
    )

    assert methods == ["GET", "GET"]


def test_periodic_calendar_polling_does_not_write_to_caldav() -> None:
    source = textwrap.dedent(inspect.getsource(nc_calendar.poll_events))
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "set_all_attendees_needs_action" not in called_names
    assert called_attributes.isdisjoint({"put", "save"})
