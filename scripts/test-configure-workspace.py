#!/usr/bin/env python3
"""Run with python3 scripts/test-configure-workspace.py (no services are started)."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("configure_workspace", Path(__file__).with_name("configure-workspace.py"))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigurationTests(unittest.TestCase):
    def test_default_workspace_is_script_checkout_not_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "care_scaffold"
            scripts = checkout / "scripts"
            scripts.mkdir(parents=True)
            script = scripts / "configure-workspace.py"
            shutil.copyfile(config.__file__, script)
            result = subprocess.run([sys.executable, str(script)], cwd=temporary,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = config.read_env(checkout / "care-scaffold.env")
            self.assertEqual(Path(values["WORKSPACE"]), checkout.resolve())
            self.assertEqual(Path(values["CARE_BE"]), checkout.resolve() / "care")
            self.assertEqual(Path(values["CARE_FE"]), checkout.resolve() / "care_fe")
            self.assertFalse((Path(temporary) / "care-scaffold.env").exists())

    def test_loopback_conflicts_and_block_allocation(self):
        for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            try:
                listener = socket.socket(family, socket.SOCK_STREAM)
                if family == socket.AF_INET6:
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind((address, 0))
                listener.listen()
            except OSError:
                listener.close()
                if family == socket.AF_INET6:
                    continue
                raise
            with listener:
                self.assertFalse(config.port_available(listener.getsockname()[1]))
        with patch.object(config, "port_available", side_effect=lambda port: port != 20003):
            ports = config.allocate_ports(0)
        self.assertEqual(list(map(int, ports.values())), list(range(20008, 20016)))

    def test_persistence_validation_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace with spaces $HOME"
            values = config.configure(workspace)
            stack_dir = workspace / ".agent"
            env_path = workspace / "care-scaffold.env"
            original = env_path.read_bytes()
            self.assertEqual(len({values[key] for key in config.PORT_KEYS}), 8)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", int(values["CARE_API_PORT"])))
                listener.listen()
                with patch.object(config, "allocate_ports", side_effect=AssertionError("must preserve ports")):
                    self.assertEqual(config.configure(workspace), values)
            self.assertEqual(env_path.read_bytes(), original)
            self.assertTrue(os.access(stack_dir / "compose.sh", os.X_OK))
            env_path.write_text(original.decode().replace(
                f"CARE_FE_PORT='{values['CARE_FE_PORT']}'", f"CARE_FE_PORT='{values['CARE_API_PORT']}'",
            ))
            override_before = (stack_dir / "compose.override.yaml").read_bytes()
            with self.assertRaisesRegex(ValueError, "distinct"):
                config.configure(workspace)
            self.assertEqual((stack_dir / "compose.override.yaml").read_bytes(), override_before)
            env_path.write_bytes(original)
            (workspace / "care").symlink_to(temporary, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                config.configure(workspace)

    def test_wrapper_uses_saved_identity_and_rejects_old_compose(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "space $HOME"
            values = config.configure(workspace)
            binary = Path(temporary) / "docker"
            binary.write_text(
                "#!/usr/bin/env python3\nimport json, os, sys\n"
                "if sys.argv[1:] == ['compose', 'version', '--short']:\n"
                "    print(os.environ.get('TEST_COMPOSE_VERSION', '2.24.4'))\n"
                "else:\n"
                "    print(json.dumps({'args': sys.argv[1:], 'care_be': os.environ['CARE_BE'], "
                "'plugin_be': os.environ.get('PLUGIN_BE'), 'plugin_fe': os.environ.get('PLUGIN_FE')}))\n"
            )
            binary.chmod(0o755)
            env = {**os.environ, "PATH": f"{temporary}:{os.environ['PATH']}", "CARE_BE": "/wrong", "CARE_API_PORT": "9000"}
            wrapper = workspace / ".agent/compose.sh"
            result = subprocess.run([str(wrapper), "config", "--format", "json"], env=env, check=True, capture_output=True, text=True)
            invocation = json.loads(result.stdout)
            self.assertEqual(invocation["care_be"], values["CARE_BE"])
            args = invocation["args"]
            self.assertEqual(args[args.index("--project-name") + 1], values["COMPOSE_PROJECT_NAME"])
            self.assertEqual(args[args.index("--project-directory") + 1], values["CARE_BE"])
            env_file = Path(args[args.index("--env-file") + 1]).resolve()
            self.assertEqual(env_file, (workspace / "care-scaffold.env").resolve())
            self.assertEqual(args.count("-f"), 3)
            self.assertEqual(args[-3:], ["config", "--format", "json"])
            plugins = {key: str(Path(temporary) / f"plugin {key} $HOME")
                       for key in ("PLUGIN_BE", "PLUGIN_FE")}
            (workspace / ".agent/paths.env").write_text(
                "".join(f"{key}='{value}'\n" for key, value in plugins.items())
            )
            result = subprocess.run([str(wrapper), "config"], env=env, check=True, capture_output=True, text=True)
            invocation = json.loads(result.stdout)
            self.assertEqual(invocation["plugin_be"], plugins["PLUGIN_BE"])
            self.assertEqual(invocation["plugin_fe"], plugins["PLUGIN_FE"])
            self.assertEqual(invocation["args"].count("-f"), 3)
            plugin_override = workspace / ".agent/plugin.compose.yaml"
            plugin_override.write_text("services: {}\n")
            result = subprocess.run([str(wrapper), "config", "--format", "json"], env=env, check=True, capture_output=True, text=True)
            invocation = json.loads(result.stdout)
            args = invocation["args"]
            self.assertEqual(
                [Path(args[index + 1]).resolve() for index, arg in enumerate(args) if arg == "-f"],
                [path.resolve() for path in (
                    Path(values["CARE_BE"]) / "docker-compose.yaml",
                    Path(values["CARE_BE"]) / "docker-compose.local.yaml",
                    workspace / ".agent/compose.override.yaml", plugin_override,
                )],
            )
            self.assertEqual(args[-3:], ["config", "--format", "json"])
            old = subprocess.run([str(wrapper), "up"], env={**env, "TEST_COMPOSE_VERSION": "2.24.3"}, capture_output=True, text=True)
            self.assertNotEqual(old.returncode, 0)
            self.assertIn("2.24.4", old.stderr)

    def test_example_accepts_partial_ports_blanks_and_comments(self):
        example = Path(__file__).resolve().parent.parent / "care-scaffold.env.example"
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            env_path = workspace / "care-scaffold.env"
            text = example.read_text()
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                explicit = probe.getsockname()[1]
            text, count = re.subn(r"^CARE_API_PORT=.*$", f"CARE_API_PORT={explicit} # chosen API port", text, flags=re.MULTILINE)
            self.assertEqual(count, 1, "The committed example must expose CARE_API_PORT")
            text = re.sub(r"^CARE_FE_PORT=.*$", "CARE_FE_PORT= # auto", text, flags=re.MULTILINE)
            text = re.sub(r"^PLUGIN_PORT=.*$", "PLUGIN_PORT='' # also auto", text, flags=re.MULTILINE)
            text = re.sub(r"^CARE_DEBUG_PORT=.*\n?", "", text, flags=re.MULTILINE)
            text += f"\nWORKSPACE='{workspace.resolve()}'\nCARE_BE='{workspace.resolve() / 'care'}'\n"
            env_path.write_text(text)
            parsed = config.read_env(env_path)
            self.assertEqual(parsed["CARE_FE_PORT"], "")
            self.assertEqual(parsed["PLUGIN_PORT"], "")
            self.assertNotIn("CARE_DEBUG_PORT", parsed)
            values = config.configure(workspace)
            self.assertEqual(values["CARE_API_PORT"], str(explicit))
            self.assertEqual(len({values[key] for key in config.PORT_KEYS}), 8)
            self.assertTrue(all(1024 <= int(values[key]) <= 65535 for key in config.PORT_KEYS))
            self.assertEqual(values["CARE_API_URL"], f"http://localhost:{explicit}")
            self.assertEqual(config.read_env(env_path), values)

    def test_invalid_unknown_duplicate_and_occupied_initial_ports(self):
        invalid = (
            "CARE_API_PORT=nope\n", "CARE_API_PORT=1023\n", "CARE_API_PORT=65536\n",
            "CARE_API_PORT=24001\nCARE_FE_PORT=24001\n",
            "CARE_API_PORT=24001\nCARE_API_PORT=24002\n", "CARE_AP_PORT=24001\n",
            "WORKSPACE='/different/workspace'\n", "CARE_BE='/different/care'\n",
        )
        for content in invalid:
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                workspace = Path(temporary)
                env_path = workspace / "care-scaffold.env"
                env_path.write_text(content)
                with self.assertRaises(ValueError):
                    config.configure(workspace)
                self.assertEqual(env_path.read_text(), content)
                self.assertFalse((workspace / ".agent").exists())
        with tempfile.TemporaryDirectory() as temporary, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            workspace = Path(temporary)
            env_path = workspace / "care-scaffold.env"
            for metadata in ("", f"WORKSPACE='{workspace.resolve()}'\n"):
                content = f"CARE_API_PORT={listener.getsockname()[1]}\n{metadata}"
                env_path.write_text(content)
                with self.assertRaises(ValueError):
                    config.configure(workspace)
                self.assertEqual(env_path.read_text(), content)
                self.assertFalse((workspace / ".agent").exists())

    def test_migrates_legacy_ports_and_rejects_two_env_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            values = config.configure(workspace)
            env_path = workspace / "care-scaffold.env"
            legacy = workspace / ".agent/stack.env"
            original = env_path.read_bytes()
            env_path.rename(legacy)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", int(values["CARE_API_PORT"])))
                listener.listen()
                self.assertEqual(config.configure(workspace), values)
            self.assertFalse(legacy.exists())
            self.assertEqual(config.read_env(env_path), values)
            legacy.write_bytes(original)
            with self.assertRaises(ValueError):
                config.configure(workspace)
            self.assertEqual(legacy.read_bytes(), original)
            saved = env_path.read_bytes()
            env_path.unlink()
            with patch.object(config.os, "replace", side_effect=OSError("simulated write failure")):
                with self.assertRaises(OSError):
                    config.configure(workspace)
            self.assertEqual(legacy.read_bytes(), original)
            self.assertFalse(env_path.exists())
            env_path.write_bytes(saved)

    def test_check_ports_is_read_only_and_detects_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            values = config.configure(workspace)
            command = [sys.executable, str(Path(config.__file__).resolve()), "--workspace", str(workspace), "--check-ports"]
            paths = [workspace / "care-scaffold.env", *sorted((workspace / ".agent").iterdir())]
            original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
            free = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(free.returncode, 0, free.stderr)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", int(values["CARE_API_PORT"])))
                listener.listen()
                occupied = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(occupied.returncode, 0)
            self.assertIn(values["CARE_API_PORT"], occupied.stderr)
            self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}, original)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            command = [sys.executable, str(Path(config.__file__).resolve()), "--workspace", str(workspace), "--check-ports"]
            missing = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertEqual(list(workspace.iterdir()), [])
            env_path = workspace / "care-scaffold.env"
            env_path.write_text("CARE_API_PORT=\n")
            partial = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(partial.returncode, 0)
            self.assertEqual(env_path.read_text(), "CARE_API_PORT=\n")
            self.assertFalse((workspace / ".agent").exists())

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI unavailable; compose config integration skipped")
    def test_compose_merge_replaces_shared_ports_and_names(self):
        version = subprocess.run(["docker", "compose", "version", "--short"], capture_output=True, text=True)
        if version.returncode:
            self.skipTest("Docker Compose unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace with spaces $HOME"
            values = config.configure(workspace)
            backend = workspace / "care"
            backend.mkdir()
            (backend / "docker-compose.yaml").write_text("""services:
  db:
    image: postgres:alpine
    ports: ["5433:5432"]
    volumes: ["postgres-data:/data"]
  redis:
    image: redis:alpine
    ports: ["6380:6379"]
    volumes: ["redis-data:/data"]
  minio:
    image: minio/minio
    ports: ["9100:9000", "9001:9001"]
    volumes: ["./care/media/minio:/data"]
networks:
  default:
    name: care
volumes:
  postgres-data:
  redis-data:
""")
            (backend / "docker-compose.local.yaml").write_text("""services:
  backend:
    image: care_local
    build:
      context: .
      dockerfile: docker/dev.Dockerfile
      args:
        ADDITIONAL_PLUGS: stale-build-value
    environment:
      ADDITIONAL_PLUGS: stale-runtime-value
    volumes: [".:/app"]
    entrypoint: ["bash", "scripts/start-dev.sh"]
    ports: ["9000:9000", "9876:9876"]
  celery:
    image: care_local
    environment:
      ADDITIONAL_PLUGS: stale-runtime-value
    volumes: [".:/app"]
    entrypoint: ["bash", "scripts/celery-dev.sh"]
""")
            result = subprocess.run([str(workspace / ".agent/compose.sh"), "config", "--format", "json"], capture_output=True, text=True, check=True)
            merged = json.loads(result.stdout)
            mappings = {
                "backend": [("CARE_API_PORT", 9000), ("CARE_DEBUG_PORT", 9876)],
                "db": [("CARE_DB_PORT", 5432)], "redis": [("CARE_REDIS_PORT", 6379)],
                "minio": [("CARE_S3_PORT", 9000), ("CARE_S3_CONSOLE_PORT", 9001)],
            }
            for service, ports in mappings.items():
                actual = merged["services"][service]["ports"]
                self.assertEqual({(p["host_ip"], p["published"], p["target"]) for p in actual},
                                 {("127.0.0.1", values[key], target) for key, target in ports})
            project = values["COMPOSE_PROJECT_NAME"]
            self.assertEqual(merged["networks"]["default"]["name"], f"{project}_default")
            for key in ("postgres-data", "redis-data"):
                self.assertEqual(merged["volumes"][key]["name"], f"{project}_{key}")
            for service in ("backend", "celery"):
                self.assertEqual(merged["services"][service]["image"], f"{project}_backend:local")
                self.assertEqual(merged["services"][service]["environment"]["BUCKET_EXTERNAL_ENDPOINT"],
                                 f"http://localhost:{values['CARE_S3_PORT']}")
            # Compose escapes literal dollars in its reusable config output.
            source = merged["services"]["minio"]["volumes"][0]["source"].replace("$$", "$")
            self.assertEqual(source, str((backend / "care/media/minio").resolve()))

            # Exercise the documented integration verbatim, so the bootstrap and wrapper
            # cannot silently diverge while unit checks of either still pass.
            bootstrap = (Path(__file__).resolve().parent.parent / "bootstrap.prompt.md").read_text()
            example = re.search(r"### 6\.1 Backend\b.*?```yaml\n(.*?)\n```", bootstrap, re.S)
            self.assertIsNotNone(example, "Bootstrap must include its external backend Compose example")
            stack_dir = workspace / ".agent"
            plugin = backend.resolve() / "care_connect"
            plugin.mkdir()
            (stack_dir / "paths.env").write_text(f"PLUGIN_BE='{plugin}'\n")
            (stack_dir / "plugin.compose.yaml").write_text(example[1] + "\n")
            core_files = {path: path.read_bytes() for path in backend.glob("docker-compose*.yaml")}
            result = subprocess.run([str(stack_dir / "compose.sh"), "config", "--format", "json"], capture_output=True, text=True, check=True)
            merged = json.loads(result.stdout)
            self.assertEqual(merged["services"]["backend"]["build"]["args"]["ADDITIONAL_PLUGS"], "")
            for service, script in (("backend", "start-dev.sh"), ("celery", "celery-dev.sh")):
                settings = merged["services"][service]
                self.assertEqual(json.loads(settings["environment"]["ADDITIONAL_PLUGS"]), [{
                    "name": "care_connect", "package_name": "/plugins/care_connect", "version": "",
                    "configs": {"CONNECT_ENABLED": True},
                }])
                self.assertEqual(settings["entrypoint"], [
                    "bash", "-c", f"python -m pip install -e /plugins/care_connect && exec bash scripts/{script}",
                ])
                mounts = {volume["target"]: volume for volume in settings["volumes"]}
                self.assertEqual(mounts["/app"]["source"].replace("$$", "$"), str(backend.resolve()))
                self.assertEqual(mounts["/plugins/care_connect"]["source"].replace("$$", "$"), str(plugin.resolve()))
                self.assertEqual(mounts["/plugins/care_connect"]["type"], "bind")
                self.assertFalse(mounts["/plugins/care_connect"].get("bind", {}).get("create_host_path", False))
                self.assertEqual(settings["environment"]["BUCKET_EXTERNAL_ENDPOINT"],
                                 f"http://localhost:{values['CARE_S3_PORT']}")
                self.assertEqual(settings["image"], f"{project}_backend:local")
            self.assertEqual({path: path.read_bytes() for path in core_files}, core_files)


if __name__ == "__main__":
    unittest.main()
