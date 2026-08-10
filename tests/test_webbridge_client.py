import pytest

from brandpulse.collectors import webbridge_client


def test_local_webbridge_bypasses_environment_proxy(monkeypatch):
    """本地 WebBridge 不应被 HTTP_PROXY 转发到外部代理。"""

    captured = {}

    direct_socket = object()

    def fake_tcp_connection(*args, **kwargs):
        captured["tcp_address"] = args[0]
        captured["tcp_timeout"] = kwargs["timeout"]
        return direct_socket

    def fake_connection(*args, **kwargs):
        captured["url"] = args[0]
        captured.update(kwargs)
        raise RuntimeError("stop after checking connection options")

    monkeypatch.setattr(webbridge_client.socket, "create_connection", fake_tcp_connection)
    monkeypatch.setattr(webbridge_client.websocket, "create_connection", fake_connection)

    with pytest.raises(RuntimeError, match="stop after checking"):
        webbridge_client.WebBridgeClient().execute("snapshot", {})

    assert captured["url"] == "ws://127.0.0.1:10086/ws"
    assert captured["tcp_address"] == ("127.0.0.1", 10086)
    assert captured["socket"] is direct_socket
    assert captured["suppress_origin"] is True


def test_remote_webbridge_keeps_proxy_configuration(monkeypatch):
    captured = {}

    def fake_connection(*args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after checking connection options")

    monkeypatch.setattr(webbridge_client.websocket, "create_connection", fake_connection)

    with pytest.raises(RuntimeError, match="stop after checking"):
        webbridge_client.WebBridgeClient("wss://bridge.example.test/ws").execute("snapshot", {})

    assert "http_no_proxy" not in captured
