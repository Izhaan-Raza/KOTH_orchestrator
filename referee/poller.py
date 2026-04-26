import asyncio
import paramiko
import httpx
import datetime
import logging

logger = logging.getLogger(__name__)

class Poller:
    def __init__(self, platform_url: str, ssh_key_path: str, interval_seconds: int, scorer_callback=None):
        self.platform_url = platform_url
        self.ssh_key_path = ssh_key_path
        self.interval = interval_seconds
        self._active_machines: dict[str, dict] = {}  # machine_id → machine info
        self.scorer_callback = scorer_callback

    async def run_forever(self):
        while True:
            try:
                await self._reload_machines()
                await self._poll_all()
            except Exception as e:
                logger.error(f"Poller error: {e}", exc_info=True)
            await asyncio.sleep(self.interval)

    async def _reload_machines(self):
        """Fetch the current active machine list from the registry."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.platform_url}/api/machines/active",
                timeout=5.0
            )
            resp.raise_for_status()
            machines = {m["id"]: m for m in resp.json()}
            
        added   = set(machines) - set(self._active_machines)
        removed = set(self._active_machines) - set(machines)
        
        for mid in added:
            logger.info(f"Referee: tracking new machine {machines[mid]['name']} "
                        f"at {machines[mid]['node_host']}:{machines[mid]['host_port']}")
        for mid in removed:
            logger.info(f"Referee: dropping machine {self._active_machines[mid]['name']}")
            
        self._active_machines = machines

    async def _poll_all(self):
        """Read king.txt on every active machine and submit scores."""
        tasks = [self._poll_one(m) for m in self._active_machines.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for machine, result in zip(self._active_machines.values(), results):
            if isinstance(result, Exception):
                logger.warning(f"Poll failed for {machine['name']}: {result}")
            else:
                owner, timestamp = result
                if owner and self.scorer_callback:
                    await self.scorer_callback(machine["id"], machine["name"], owner, machine.get("points_per_tick", 10))

    async def _poll_one(self, machine: dict) -> tuple[str | None, str]:
        """
        SSH to the machine's host node; read king_file.
        Returns (owner_team_name, timestamp) or (None, timestamp) if unowned.
        Runs in a thread pool because Paramiko is synchronous.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._ssh_read_king_file, machine)

    def _ssh_read_king_file(self, machine: dict) -> tuple[str | None, str]:
        """Synchronous SSH read. Called from executor thread."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        timestamp = datetime.datetime.utcnow().isoformat()
        try:
            ssh.connect(
                hostname=machine["node_host"],
                username=machine["node_ssh_user"],
                key_filename=self.ssh_key_path,
                timeout=5,
                banner_timeout=5,
            )
            # Use docker exec to read the file from inside the container.
            # This avoids needing SSH inside the container itself.
            cmd = (
                f"docker exec {machine['container_id']} "
                f"cat {machine['king_file']} 2>/dev/null || true"
            )
            _, stdout, stderr = ssh.exec_command(cmd, timeout=5)
            stderr.read()  # drain stderr to prevent deadlock
            content = stdout.read().decode("utf-8", errors="replace").strip()
            
            # Simple validation: if content exists and is valid team name (no whitespace usually)
            owner = content if content and "unclaimed" not in content.lower() else None
            return (owner, timestamp)
        except (paramiko.SSHException, OSError) as e:
            raise RuntimeError(f"SSH error for {machine['name']}: {e}") from e
        finally:
            ssh.close()
