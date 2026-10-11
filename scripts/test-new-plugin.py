#!/usr/bin/env python3
"""Generator smoke checks; Python + Node + Git, no npm install or running CARE needed."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile

GENERATOR = Path(__file__).resolve().with_name("new-plugin.sh")
SCAFFOLD = GENERATOR.parent.parent


def git(path, *args):
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def workspace(path, *, separate_git_dir=None):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "--quiet")
    shutil.copyfile(SCAFFOLD / ".gitignore", path / ".gitignore")
    care = path / "care"
    care.mkdir()
    options = ["--separate-git-dir", str(separate_git_dir)] if separate_git_dir else []
    git(care, "init", "--quiet", *options)
    (care / "core.txt").write_text("Tracked core source must remain unchanged.\n")
    git(care, "add", "core.txt")
    git(care, "-c", "user.name=Generator Test", "-c", "user.email=test@example.invalid",
        "commit", "--quiet", "--no-gpg-sign", "-m", "Core fixture")
    return path


def snapshot(path):
    return {str(file.relative_to(path)): file.read_bytes()
            for file in path.rglob("*") if file.is_file()}


def generate(output, name, *options, succeeds=True, generator=GENERATOR, cwd=None):
    result = subprocess.run(
        ["bash", str(generator), "--name", name,
         *(["--out", str(output)] if output else []), *options],
        cwd=cwd, capture_output=True, text=True, timeout=10,
    )
    assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
    return result


with tempfile.TemporaryDirectory(prefix="care scaffold test ") as temporary:
    temporary = Path(temporary)
    output = workspace(temporary / "workspace")
    core_head = git(output / "care", "rev-parse", "HEAD")
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
        for path in (output / "care" / f"care_{name}", frontend):
            assert (path / ".git").is_dir()
            assert Path(git(path, "rev-parse", "--show-toplevel")).resolve() == path.resolve()
            assert not git(path, "remote") and not git(path, "ls-files")
            assert git(path, "status", "--short", "--", "README.md") == "?? README.md"
            assert git(path, "check-ignore", ".env", ".env.local") == ".env\n.env.local"
            assert subprocess.run(
                ["git", "-C", str(path), "rev-parse", "--verify", "HEAD"],
                capture_output=True,
            ).returncode != 0
            for file in path.rglob("*"):
                if ".git" not in file.relative_to(path).parts and file.is_file():
                    assert not re.search(r"__PLUGIN_|__I18N_PREFIX__", file.read_text()), file
    assert not (output / ".gitmodules").exists()
    assert not git(output, "ls-files", "--stage")
    assert not git(output / "care", "status", "--porcelain", "--untracked-files=all")
    assert git(output / "care", "rev-parse", "HEAD") == core_head
    assert git(output / "care", "check-ignore", "care_first/setup.py") == "care_first/setup.py"
    assert ports[0] != ports[1], ports
    frontend = output / "care_first_fe"
    package = json.loads((frontend / "package.json").read_text())
    assert package["description"] == f"{title} plugin for CARE"
    assert package["scripts"]["dev"] == "node dev.mjs"
    assert json.loads((frontend / "public/locale/en.json").read_text())["first__page_title"] == title
    assert f"window.CARE_API_URL ??= {json.dumps(api_url)};" in (frontend / "src/main.tsx").read_text()
    ast.parse((output / "care/care_first/setup.py").read_text())
    ast.parse((output / "care/care_first/care_first/apps.py").read_text())
    for port in ("-1", "0", "1023", "65536", "abc"):
        generate(output, "invalid", "--port", port, succeeds=False)
    generate(output, "invalid", "--port", succeeds=False)
    generate(output, "invalid", "--api-url", "not-a-url", succeeds=False)
    assert not (output / "care/care_invalid").exists()

    configured = workspace(temporary / "configured")
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
        assert not (output / "care/care_occupied").exists()
        env_path.write_text(f"PLUGIN_PORT='{port}'\n")
        result = generate(configured, "occupied_default", succeeds=False)
        assert "already in use" in result.stderr

        # Exercise the actual dev runner without downloading Vite.
        # This confirms watcher closes on failure, signals are handled, and preview starts correctly.
        vite = frontend / "node_modules/vite"
        vite.mkdir(parents=True)
        (vite / "package.json").write_text(json.dumps({"type": "module", "exports": "./index.mjs"}))
        (vite / "index.mjs").write_text("""
import { createServer } from "node:net";
export async function build(options) {
  if (options?.build?.watch) {
    console.log("watch started");
    const interval = setInterval(() => {}, 1000);
    return {
      on(event, callback) {
        if (event === "event") {
          setTimeout(() => {
            console.log("emitting ERROR");
            callback({ code: "ERROR" });
            setTimeout(() => {
              console.log("emitting END 1");
              callback({ code: "END" });
              setTimeout(() => {
                console.log("emitting END 2");
                callback({ code: "END" });
                setTimeout(() => process.kill(process.pid, 'SIGINT'), 20);
              }, 20);
            }, 20);
          }, 20);
        }
      },
      async close() {
        console.log("watch closed");
        clearInterval(interval);
      }
    };
  }
}
export async function preview() {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(Number(process.env.TEST_PORT), "127.0.0.1", () => {
      console.log("preview started");
      resolve({ httpServer: server });
    });
  });
}
""")
        # 1. Occupied port -> binds fail, error propagates, watcher closes.
        result = subprocess.run(
            ["node", "dev.mjs"], cwd=frontend,
            env={**os.environ, "TEST_PORT": port},
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode != 0 and "EADDRINUSE" in result.stderr
        assert "watch closed" in result.stdout

    # 2. Free port -> skips ERROR, starts preview on END 1, ignores END 2, cleans up on SIGINT.
    with socket.socket() as free_sock:
        free_sock.bind(("127.0.0.1", 0))
        free_port = str(free_sock.getsockname()[1])
    result2 = subprocess.run(
        ["node", "dev.mjs"], cwd=frontend,
        env={**os.environ, "TEST_PORT": free_port},
        capture_output=True, text=True, timeout=5,
    )
    assert result2.returncode == 0
    assert "emitting ERROR" in result2.stdout
    assert "emitting END 1" in result2.stdout
    assert result2.stdout.count("preview started") == 1
    assert "emitting END 2" in result2.stdout
    assert "watch closed" in result2.stdout

    # Reruns preserve edits, untracked files, commits, remotes, and every byte of
    # plugin Git metadata. Overrides only configure a newly generated frontend.
    for plugin in (output / "care/care_first", frontend):
        (plugin / "README.md").write_text("User-owned changes.\n")
        (plugin / "custom.txt").write_text("__PLUGIN_TITLE__ is intentional user content.\n")
        git(plugin, "add", "README.md")
        git(plugin, "-c", "user.name=Generator Test", "-c", "user.email=test@example.invalid",
            "commit", "--quiet", "--no-gpg-sign", "-m", "Plugin fixture")
        git(plugin, "remote", "add", "origin", "https://example.invalid/plugin.git")
    before = {plugin: snapshot(plugin) for plugin in (output / "care/care_first", frontend)}
    exclude = output / "care/.git/info/exclude"
    exclude_before = exclude.read_bytes()
    generate(output, "first", "--port", "invalid", "--api-url", "ignored-on-rerun")
    assert all(snapshot(plugin) == saved for plugin, saved in before.items())
    assert exclude.read_bytes() == exclude_before

    # A missing counterpart can be regenerated without touching the surviving repo.
    shutil.rmtree(frontend)
    generate(output, "first")
    assert snapshot(output / "care/care_first") == before[output / "care/care_first"]
    frontend_before = snapshot(frontend)
    shutil.rmtree(output / "care/care_first")
    generate(output, "first", "--port", "invalid")
    assert snapshot(frontend) == frontend_before
    assert Path(git(output / "care/care_first", "rev-parse", "--show-toplevel")).resolve() == (
        output / "care/care_first"
    ).resolve()
    assert exclude.read_bytes() == exclude_before

    # Run a copy of the real scaffold from elsewhere, without --out. Its own root
    # must remain the default, and root-anchored ignores must leave sources visible.
    default = workspace(temporary / "default scaffold")
    (default / "scripts").mkdir()
    shutil.copyfile(GENERATOR, default / "scripts/new-plugin.sh")
    shutil.copytree(SCAFFOLD / "templates", default / "templates")
    for relative in ("skills/example/SKILL.md", "templates/care_example/source.txt",
                     ".github/skills/example/SKILL.md", ".agent/generated.txt",
                     "care-scaffold.env"):
        path = default / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    (default / "care_fe").mkdir()
    git(default / "care_fe", "init", "--quiet")
    generate(None, "default", generator=default / "scripts/new-plugin.sh", cwd=temporary)
    assert (default / "care/care_default/.git").is_dir()
    assert (default / "care_default_fe/.git").is_dir()
    assert not (temporary / "care_default_fe").exists()
    visible = set(git(default, "ls-files", "--others", "--exclude-standard").splitlines())
    status_paths = {line[3:] for line in git(
        default, "status", "--porcelain", "--untracked-files=all"
    ).splitlines()}
    assert {"scripts/new-plugin.sh", "templates/backend/setup.py", "skills/example/SKILL.md",
            "templates/care_example/source.txt"} <= visible
    assert not any(path.startswith(("care/", "care_fe/", "care_default_fe/", ".agent/", ".github/skills/"))
                   or path == "care-scaffold.env" for path in visible | status_paths), status_paths
    assert not git(default / "care", "status", "--porcelain", "--untracked-files=all")

    # Resolve excludes through Git, including checkouts whose .git is a file.
    gitdir = temporary / "separate core gitdir"
    separate = workspace(temporary / "separate", separate_git_dir=gitdir)
    separate_exclude = gitdir / "info/exclude"
    separate_exclude.write_text("# Preserve existing local rules without a trailing newline")
    generate(separate, "separate")
    assert separate_exclude.read_text() == (
        "# Preserve existing local rules without a trailing newline\n/care_separate/\n"
    )
    assert not git(separate / "care", "status", "--porcelain", "--untracked-files=all")
    assert not (separate / "care/.git/info/exclude").exists()

    # Git normally discovers ancestor repos; these are not independent checkouts.
    invalid = temporary / "invalid checkout"
    (invalid / "care").mkdir(parents=True)
    git(invalid, "init", "--quiet")
    original_exclude = (invalid / ".git/info/exclude").read_bytes()
    result = generate(invalid, "missing_root", succeeds=False)
    assert "expected its own Git root" in result.stderr
    assert (invalid / ".git/info/exclude").read_bytes() == original_exclude
    assert not (invalid / "care/care_missing_root").exists()
    (output / "care/care_not_a_repo").mkdir()
    result = generate(output, "not_a_repo", succeeds=False)
    assert "expected its own Git root" in result.stderr
    assert not (output / "care_not_a_repo_fe").exists()
    (output / "care_invalid_frontend_fe").mkdir()
    result = generate(output, "invalid_frontend", succeeds=False)
    assert "expected its own Git root" in result.stderr
    assert not (output / "care/care_invalid_frontend").exists()

    # Symlinked checkouts can belong to another workspace; never write there.
    linked = temporary / "linked checkout"
    linked.mkdir()
    (linked / "care").symlink_to(output / "care", target_is_directory=True)
    result = generate(linked, "linked", succeeds=False)
    assert "not a symlink" in result.stderr
    assert exclude.read_bytes() == exclude_before
    assert not (output / "care/care_linked").exists()
    (output / "care_linked_fe").symlink_to(frontend, target_is_directory=True)
    result = generate(output, "linked", succeeds=False)
    assert "not a symlink" in result.stderr
    assert not (output / "care/care_linked").exists()

print("Generator checks passed: default/overridden workspace, independent plugin roots, ignored generated files, trackable sources, local core excludes, preserved reruns, port configuration, URL escaping, occupied-port rejection, and dev startup failure.")
