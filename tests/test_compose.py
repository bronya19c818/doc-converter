from pathlib import Path

import yaml


def test_compose_mounts_windows_fonts_for_pdf_preview() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    mounts = compose["services"]["app"]["volumes"]

    font_mount = next(mount for mount in mounts if isinstance(mount, dict) and mount["target"] == "/usr/local/share/fonts/windows")

    assert font_mount == {
        "type": "bind",
        "source": "${DOC_CONVERTER_WINDOWS_FONTS:-C:/Windows/Fonts}",
        "target": "/usr/local/share/fonts/windows",
        "read_only": True,
    }
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]' in dockerfile


def test_dockerfile_installs_the_built_frontend_with_the_python_package() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    frontend_copy = dockerfile.index(
        "COPY --from=frontend-build /build/src/doc_converter/web/ ./src/doc_converter/web/"
    )
    package_install = dockerfile.index("RUN pip install --no-cache-dir .")

    assert frontend_copy < package_install
