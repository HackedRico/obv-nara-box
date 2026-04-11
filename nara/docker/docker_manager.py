"""
Docker container lifecycle manager for NARA.

Interface (contractual — used by orchestrator and exploiter):
    manager = DockerManager()
    manager.build()              -> None   (build the image)
    manager.run()                -> None   (start the container)
    manager.exec(cmd: str)       -> str    (run cmd inside container, return output)
    manager.reset()              -> None   (stop + remove + fresh run)
    manager.is_running()         -> bool   (health check)
"""

import subprocess
from pathlib import Path

IMAGE_NAME = "nara-target"
CONTAINER_NAME = "nara-container"

# Resolve to the source tree, not the site-packages copy.
# docker_manager.py lives at nara/docker/docker_manager.py,
# so we need nara/docker/ which contains the Dockerfile.
_THIS_DIR = Path(__file__).resolve().parent
# If installed as non-editable, __file__ is in site-packages and the
# Dockerfile won't be there. Walk up to find the repo root instead.
if (_THIS_DIR / "Dockerfile").exists():
    DOCKERFILE_DIR = str(_THIS_DIR)
else:
    # Fallback: assume cwd is the repo root
    DOCKERFILE_DIR = str(Path.cwd() / "nara" / "docker")


class DockerManager:
    def build(self) -> None:
        """Build the nara-target Docker image."""
        subprocess.run(
            ["docker", "build", "-t", IMAGE_NAME, DOCKERFILE_DIR],
            check=True,
        )

    def run(self) -> None:
        """Start the container with VNC (5901) and app (8080) ports mapped."""
        # Remove stale container with the same name if it exists
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
        )
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "-p", "5901:5901",
                "-p", "6080:6080",
                "-p", "8080:8080",
                IMAGE_NAME,
            ],
            check=True,
        )

    def exec(self, cmd: str) -> str:
        """Run a shell command inside the container and return combined stdout+stderr."""
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "bash", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return (result.stdout + result.stderr).strip()

    def reset(self) -> None:
        """Stop and remove the container, then start a fresh one."""
        subprocess.run(
            ["docker", "rm", "-f", CONTAINER_NAME],
            capture_output=True,
        )
        self.run()

    def is_running(self) -> bool:
        """Return True if the container is up and running."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() == "true"
