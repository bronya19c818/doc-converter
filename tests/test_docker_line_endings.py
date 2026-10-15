import subprocess
from pathlib import Path


def test_shell_checkout_is_lf_and_docker_normalizes_crlf_after_copy(tmp_path):
    value = subprocess.check_output(
        ["git", "check-attr", "eol", "--", "docker-entrypoint.sh"], text=True
    )
    assert value.strip().endswith(": lf")
    dockerfile = Path("Dockerfile").read_text()
    assert "sed -i 's/\\r$//' /usr/local/bin/docker-entrypoint.sh" in dockerfile
    assert dockerfile.index("COPY docker-entrypoint.sh") < dockerfile.index("sed -i 's/\\r$//'")
    script = tmp_path / "entrypoint.sh"
    script.write_bytes(b"#!/bin/sh\r\nprintf startup-ok\r\n")
    subprocess.run(["sed", "-i", "s/\r$//", str(script)], check=True)
    script.chmod(0o755)
    assert subprocess.check_output([str(script)], text=True) == "startup-ok"


def test_html_is_revalidated_after_application_updates(tmp_path):
    from fastapi.testclient import TestClient

    from doc_converter.api import create_app

    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    client = TestClient(create_app(data_root=tmp_path / "data", frontend_dist=dist))
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
