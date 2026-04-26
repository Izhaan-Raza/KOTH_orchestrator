from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if "paramiko" not in sys.modules:
    fake_paramiko = types.SimpleNamespace(
        SSHClient=object,
        RejectPolicy=object,
        AutoAddPolicy=object,
    )
    sys.modules["paramiko"] = fake_paramiko

from config import SETTINGS
from ssh_client import SSHClientPool


class _FakeChannel:
    def recv_exit_status(self) -> int:
        return 0


class _FakeStream:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.channel = _FakeChannel()

    def read(self) -> bytes:
        return self._payload


class _FakeSSHClient:
    def __init__(self) -> None:
        self.connect_calls: list[dict[str, object]] = []

    def load_system_host_keys(self) -> None:
        return

    def set_missing_host_key_policy(self, policy) -> None:
        _ = policy

    def connect(self, **kwargs) -> None:
        self.connect_calls.append(kwargs)

    def exec_command(self, command: str, timeout: int):
        _ = command, timeout
        return None, _FakeStream(b"OK\n"), _FakeStream(b"")

    def close(self) -> None:
        return


class SSHClientPoolTargetTests(unittest.TestCase):
    def test_exec_uses_per_host_username_override(self) -> None:
        fake_client = _FakeSSHClient()
        with patch("ssh_client.paramiko.SSHClient", return_value=fake_client):
            pool = SSHClientPool(
                username="root",
                private_key_path="~/.ssh/koth_referee",
                port=22,
                timeout_seconds=5,
                strict_host_key_checking=True,
                host_target_overrides={"192.168.0.102": "nodeA@192.168.0.102"},
            )
            code, out, err = pool.exec("192.168.0.102", "hostname")

        self.assertEqual((code, out, err), (0, "OK\n", ""))
        self.assertEqual(fake_client.connect_calls[0]["hostname"], "192.168.0.102")
        self.assertEqual(fake_client.connect_calls[0]["username"], "nodeA")

    def test_exec_falls_back_to_default_username(self) -> None:
        fake_client = _FakeSSHClient()
        with patch("ssh_client.paramiko.SSHClient", return_value=fake_client):
            pool = SSHClientPool(
                username="recon_admin",
                private_key_path="~/.ssh/koth_referee",
                port=22,
                timeout_seconds=5,
                strict_host_key_checking=False,
            )
            pool.exec("192.168.0.103", "hostname")

        self.assertEqual(fake_client.connect_calls[0]["hostname"], "192.168.0.103")
        self.assertEqual(fake_client.connect_calls[0]["username"], "recon_admin")


class SettingsTargetValidationTests(unittest.TestCase):
    def test_validate_runtime_rejects_mismatched_target_count(self) -> None:
        original_targets = SETTINGS.node_ssh_targets
        original_hosts = SETTINGS.node_hosts
        object.__setattr__(SETTINGS, "node_hosts", ("192.168.0.102", "192.168.0.103"))
        object.__setattr__(SETTINGS, "node_ssh_targets", ("nodeA@192.168.0.102",))
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "node_hosts", original_hosts))
        self.addCleanup(lambda: object.__setattr__(SETTINGS, "node_ssh_targets", original_targets))

        with self.assertRaises(RuntimeError):
            SETTINGS.validate_runtime()
