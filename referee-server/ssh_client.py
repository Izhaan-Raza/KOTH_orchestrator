from __future__ import annotations

import threading
from pathlib import Path

import paramiko


class SSHClientPool:
    def __init__(
        self,
        *,
        username: str,
        private_key_path: str,
        port: int,
        timeout_seconds: int,
        strict_host_key_checking: bool,
    ):
        self._username = username
        self._private_key_path = str(Path(private_key_path).expanduser())
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._strict_host_key_checking = strict_host_key_checking
        self._lock = threading.RLock()
        self._clients: dict[str, paramiko.SSHClient] = {}

    def _connect(self, host: str) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if self._strict_host_key_checking:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=self._port,
            username=self._username,
            key_filename=self._private_key_path,
            timeout=self._timeout_seconds,
            banner_timeout=self._timeout_seconds,
            auth_timeout=self._timeout_seconds,
        )
        return client

    def _get_client(self, host: str) -> paramiko.SSHClient:
        with self._lock:
            existing = self._clients.get(host)
            if existing is not None:
                return existing
            client = self._connect(host)
            self._clients[host] = client
            return client

    def exec(self, host: str, command: str) -> tuple[int, str, str]:
        try:
            client = self._get_client(host)
            stdin, stdout, stderr = client.exec_command(command, timeout=self._timeout_seconds)
            _ = stdin
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
            return code, out, err
        except Exception:
            self.reset_host(host)
            raise

    def reset_host(self, host: str) -> None:
        with self._lock:
            client = self._clients.pop(host, None)
            if client is not None:
                client.close()

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()
