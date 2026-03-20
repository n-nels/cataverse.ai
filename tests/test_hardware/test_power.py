from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config_loader import KasaConfig
from src.hardware.power import KasaPower


def test_login_success_sets_token_and_url() -> None:
    credentials = KasaConfig(
        chiller_id="c",
        variac_id="v",
        variac_id_vsl="vv",
        username="user",
        password="pass",
    )
    power = KasaPower(credentials)

    with patch("src.hardware.power.requests.post") as post:
        response = MagicMock()
        response.json.return_value = {"error_code": 0, "result": {"token": "abc"}}
        post.return_value = response

        assert power.login() is True
        assert power.token == "abc"
        assert power.url in power.endpoints


def test_set_state_returns_response_dict() -> None:
    credentials = KasaConfig(
        chiller_id="c",
        variac_id="v",
        variac_id_vsl="vv",
        username="user",
        password="pass",
    )
    power = KasaPower(credentials)

    with patch("src.hardware.power.requests.post") as post:
        login_response = MagicMock()
        login_response.json.return_value = {"error_code": 0, "result": {"token": "abc"}}
        control_response = MagicMock()
        control_response.json.return_value = {"error_code": 0}
        post.side_effect = [login_response, control_response]

        result = power.set_state("device-id", True)

        assert result == {"error_code": 0}

        # second call is control request
        control_call = post.call_args_list[1]
        assert "?token=abc" in control_call.args[0]
        payload = control_call.kwargs["json"]
        assert payload["params"]["deviceId"] == "device-id"
        assert payload["params"]["requestData"]["system"]["set_relay_state"]["state"] == 1


def test_login_falls_back_to_second_endpoint() -> None:
    credentials = KasaConfig(
        chiller_id="c",
        variac_id="v",
        variac_id_vsl="vv",
        username="user",
        password="pass",
    )
    power = KasaPower(credentials)

    with patch("src.hardware.power.requests.post") as post:
        first_fail = MagicMock()
        first_fail.json.return_value = {"error_code": -1, "msg": "fail"}
        second_ok = MagicMock()
        second_ok.json.return_value = {"error_code": 0, "result": {"token": "tok2"}}
        post.side_effect = [first_fail, second_ok]

        assert power.login() is True
        assert power.token == "tok2"
        assert power.url == power.endpoints[1]
