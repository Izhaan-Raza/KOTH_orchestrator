import paramiko

def _exec(ssh: paramiko.SSHClient, command: str, timeout: int) -> str:
    """
    Execute a command over SSH and return stdout.
    Raises RuntimeError if the command exits non-zero.
    IMPORTANT: Read stderr before or concurrently with stdout to avoid
    the deadlock described in paramiko issue #1778.
    """
    stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    stdin.close()  # we never write to stdin
    
    # Read stderr first (or at least drain it) to prevent the
    # transport-layer deadlock when both buffers fill up.
    err = stderr.read().decode("utf-8", errors="replace")
    out = stdout.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    
    if exit_code != 0:
        raise RuntimeError(
            f"Command failed (exit {exit_code}).\n"
            f"Command: {command}\n"
            f"Stderr: {err}\n"
            f"Stdout: {out}"
        )
    return out

def _cleanup_stale(ssh: paramiko.SSHClient, container_name: str):
    try:
        _exec(ssh, f"docker rm -f {container_name}", timeout=10)
    except RuntimeError:
        pass  # container did not exist; that's fine

def deploy_to_node(
    node_host: str,
    ssh_user: str,
    ssh_key_path: str,    
    image: str,
    container_name: str,
    port_mapping: dict,  # {host_port: container_port}
    king_file: str,
) -> str:
    """
    Deploy a container on a remote node via SSH.
    Returns the Docker container ID on success.
    Raises RuntimeError on failure.
    """
    ssh = paramiko.SSHClient()
    # AutoAddPolicy accepts any host key.
    # For production, use RejectPolicy and maintain a known_hosts file.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=node_host,
            username=ssh_user,
            key_filename=ssh_key_path,
            timeout=10,          # connection timeout in seconds
            banner_timeout=10,   # time to wait for SSH banner
        )
        
        _cleanup_stale(ssh, container_name)

        # Build port flags: "-p 10085:80"
        port_flags = " ".join(
            f"-p {hp}:{cp}" for hp, cp in port_mapping.items()
        )
        
        # Pull the image first, separate from run
        pull_cmd = f"docker pull {image}"
        _exec(ssh, pull_cmd, timeout=120)  # image pulls can be slow
        
        # Run the container
        run_cmd = (
            f"docker run -d "
            f"--name {container_name} "
            f"--restart unless-stopped "
            f"{port_flags} "
            f"{image}"
        )
        stdout = _exec(ssh, run_cmd, timeout=30)
        container_id = stdout.strip()
        return container_id
    finally:
        ssh.close()

def undeploy_from_node(
    node_host: str,
    ssh_user: str,
    ssh_key_path: str,
    container_name: str,
):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(node_host, username=ssh_user, key_filename=ssh_key_path)
    try:
        # Stop then remove. Separate commands so stop errors don't
        # prevent removal of an already-exited container.
        try:
            _exec(ssh, f"docker stop {container_name}", timeout=30)
        except RuntimeError:
            pass  # container may already be stopped
            
        _exec(ssh, f"docker rm {container_name}", timeout=10)
    finally:
        ssh.close()
