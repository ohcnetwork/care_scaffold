#!/usr/bin/env python3
"""Generator smoke checks; Python + Node only, no npm install or running CARE needed."""
import ast
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

GENERATOR = Path(__file__).with_name("new-plugin.sh")


def generate(output, name, *options, succeeds=True):
    result = subprocess.run(
        ["bash", str(GENERATOR), "--name", name, "--out", str(output), *options],
        capture_output=True, text=True, timeout=10,
    )
    assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
    return result


with tempfile.TemporaryDirectory(prefix="care scaffold test ") as temporary:
    output = Path(temporary)
    title = 'Care | "Check" & <test> \\ value'
    api_url = "http://localhost:19000/base?a=b&c=d|e"
    generate(output, "first", "--title", title, "--api-url", api_url)
    generate(output, "second")
    ports = []
    for name in ("first", "second"):
        frontend = output / f"care_{name}_fe"
        config = (frontend / "vite.config.ts").read_text()
        ports.append(int(re.search(r"port:\s*(\d+)", config)[1]))
        assert "strictPort: true" in config and 'host: "127.0.0.1"' in config
        for path in (output / f"care_{name}", frontend):
            for file in path.rglob("*"):
                if file.is_file():
                    assert not re.search(r"__PLUGIN_|__I18N_PREFIX__", file.read_text()), file
    assert ports[0] != ports[1], ports
    frontend = output / "care_first_fe"
    package = json.loads((frontend / "package.json").read_text())
    assert package["description"] == f"{title} plugin for CARE"
    assert package["scripts"]["dev"] == "node dev.mjs"
    assert json.loads((frontend / "public/locale/en.json").read_text())["first__page_title"] == title
    assert f"window.CARE_API_URL ??= {json.dumps(api_url)};" in (frontend / "src/main.tsx").read_text()
    ast.parse((output / "care_first/setup.py").read_text())
    ast.parse((output / "care_first/care_first/apps.py").read_text())
    for port in ("-1", "0", "1023", "65536", "abc"):
        generate(output, "invalid", "--port", port, succeeds=False)
    generate(output, "invalid", "--port", succeeds=False)
    generate(output, "invalid", "--api-url", "not-a-url", succeeds=False)
    assert not (output / "care_invalid").exists()

    configured = output / "configured"
    configured.mkdir()
    env_path = configured / "care-scaffold.env"
    marker = configured / "must-not-exist"
    env_content = (
        f"PLUGIN_PORT='{ports[0]}'\nCARE_API_PORT='{ports[1]}'\n"
        "CARE_API_URL='http://localhost:1'\n"
        f"IGNORED='$(touch \"{marker}\")'\n"
    )
    env_path.write_text(env_content)
    generate(configured, "configured_first")
    generated = configured / "care_configured_first_fe"
    assert f"port: {ports[0]}," in (generated / "vite.config.ts").read_text()
    assert f'"http://localhost:{ports[1]}"' in (generated / "src/main.tsx").read_text()
    generate(configured, "configured_second")
    config = (configured / "care_configured_second_fe/vite.config.ts").read_text()
    assert int(re.search(r"port:\s*(\d+)", config)[1]) not in ports
    generate(configured, "overridden", "--port", str(ports[1]), "--api-url", api_url)
    generated = configured / "care_overridden_fe"
    assert f"port: {ports[1]}," in (generated / "vite.config.ts").read_text()
    assert json.dumps(api_url) in (generated / "src/main.tsx").read_text()
    assert env_path.read_text() == env_content and not marker.exists()

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = str(occupied.getsockname()[1])
        result = generate(output, "occupied", "--port", port, succeeds=False)
        assert "already in use" in result.stderr
        assert not (output / "care_occupied").exists()
        env_path.write_text(f"PLUGIN_PORT='{port}'\n")
        result = generate(configured, "occupied_default", succeeds=False)
        assert "already in use" in result.stderr

        # Exercise the actual dev runner without downloading Vite: preview's
        # bind failure must reach npm, without leaving a watcher alive.
        vite = frontend / "node_modules/vite"
        vite.mkdir(parents=True)
        (vite / "package.json").write_text(json.dumps({"type": "module", "exports": "./index.mjs"}))
        (vite / "index.mjs").write_text("""
import { createServer } from "node:net";
export async function build(options) {
  if (options?.build?.watch) {
    console.log("watch started");
    setInterval(() => {}, 1000);
  }
}
export async function preview() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(Number(process.env.TEST_PORT), "127.0.0.1", () => resolve(server));
  });
}
""")
        result = subprocess.run(
            ["node", "dev.mjs"], cwd=frontend,
            env={**os.environ, "TEST_PORT": port},
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode != 0 and "EADDRINUSE" in result.stderr
        assert "watch started" not in result.stdout

    # Issue #7 regression: outer repository directory shadowing as a namespace package

    # 1. Unfixed
    shadow_test = f"""
import sys
sys.path.insert(0, '{output}')
import care_first
assert not hasattr(care_first, '__file__') or care_first.__file__ is None
assert len(care_first.__path__) == 1
assert 'care_first/care_first' not in list(care_first.__path__)[0]
"""
    subprocess.run(["python3", "-c", shadow_test], check=True)

    # 2. Fixed
    fixed_test = f"""
import sys
from pathlib import Path
plug_config_file = Path('{output / "plug_config.py"}')
sys.path.insert(0, str(plug_config_file.resolve().parent / "care_first"))
sys.path.insert(1, '{output}')

import care_first
import care_first.models

assert care_first.__file__ is not None
assert len(care_first.__path__) == 1
assert list(care_first.__path__)[0].endswith('care_first/care_first')
assert care_first.models.__file__.endswith('care_first/care_first/models/__init__.py')
"""
    subprocess.run(["python3", "-c", fixed_test], check=True)

print("Generator, workspace defaults/overrides, URL escaping, distinct ports, occupied-port rejection, and dev startup checks passed.")
