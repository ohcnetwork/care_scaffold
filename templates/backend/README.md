# __PLUGIN_TITLE__

__PLUGIN_DESCRIPTION__

A [CARE](https://github.com/ohcnetwork/care) backend plugin. It is an ordinary Django app,
installed in CARE's runtime and registered through `ADDITIONAL_PLUGS`. This directory is
an independent Git repository, with no initial commit or remote. Publish it as its own repo;
never add it as a scaffold submodule.

## Install (local development)

Run `care_scaffold/bootstrap.prompt.md` through Phase 6. By default this repository lives at
`$WORKSPACE/care/__PLUGIN_SNAKE__`, where `$WORKSPACE` is the scaffold checkout. It has its own
Git root and is excluded from core through core's local `.git/info/exclude`; the scaffold ignores
`/care/`. Run Git commands here to track and publish plugin source. Bootstrap mounts it into
both backend and worker containers through `.agent/plugin.compose.yaml`, installs it in editable
mode at startup,
and registers it using `ADDITIONAL_PLUGS` in the container environment.

All implementation work belongs in this plugin repository. Do not edit either core checkout,
including its settings, `plug_config.py`, environment files, or Docker configuration.
If a core limitation blocks the plugin, document the blocker in a `care_scaffold` issue
and continue work that the existing extension points support. Template fixes belong in a
separate `care_scaffold` change.

```bash
source "$WORKSPACE/care-scaffold.env"
"$WORKSPACE/.agent/compose.sh" up -d --wait
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py makemigrations __PLUGIN_SNAKE__
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
```

Use `.agent/compose.sh` for every backend command to preserve its isolated project and ports.
To stop safely, run `"$WORKSPACE/.agent/compose.sh" down` without `-v`.

## API

Mounted automatically at `/api/__PLUGIN_SNAKE__/` by core's `config/urls.py`.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/__PLUGIN_SNAKE__/config/` | Client-safe configuration |

## Settings

Resolution order: `PLUGIN_CONFIGS["__PLUGIN_SNAKE__"][key]` → environment variable → default.
See `__PLUGIN_SNAKE__/settings.py`.
