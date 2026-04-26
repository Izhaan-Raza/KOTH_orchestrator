import docker
import os

def build_and_push(
    dockerfile_dir: str,
    tag: str,
    registry_host: str,  # e.g. "localhost:5000" for a local registry
) -> str:
    """
    Build a Docker image from a Dockerfile directory.
    Push to a local registry so nodes can pull it.
    Returns the full image reference: registry_host/tag
    """
    client = docker.from_env()
    full_tag = f"{registry_host}/{tag}"
    
    # client.images.build returns (Image, generator_of_log_lines)
    # The generator must be consumed to avoid the build hanging.
    image, logs = client.images.build(
        path=dockerfile_dir,
        tag=full_tag,
        rm=True,           # remove intermediate containers after build
        forcerm=True,      # remove even on failure
    )
    
    # Consume and surface build logs
    for chunk in logs:
        if "stream" in chunk:
            print(chunk["stream"], end="")
        if "error" in chunk:
            raise RuntimeError(f"Build failed: {chunk['error']}")
            
    # Push to local registry
    push_output = client.images.push(full_tag)
    print(push_output)
    
    return full_tag
