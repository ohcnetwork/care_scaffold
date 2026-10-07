# __PLUGIN_TITLE__

__PLUGIN_DESCRIPTION__

A [CARE](https://github.com/ohcnetwork/care) backend plugin. It is an ordinary Django app,
pip-installed into core and registered through `plug_config.py`. Core contains no reference
to this package.

## Install (local development)

Run the `care_scaffold` bootstrap and load this workspace's saved settings first.
Place the plugin inside its dedicated backend checkout as a **real directory**. A symlink breaks
`docker build`, which cannot follow links out of the build context.

```bash
source "$WORKSPACE/care-scaffold.env"
mv /path/to/__PLUGIN_SNAKE__ "$CARE_BE/__PLUGIN_SNAKE__"
```

`care/plug_config.py`:

```python
__PLUGIN_SNAKE__ = Plug(
    name="__PLUGIN_SNAKE__",
    package_name="__PLUGIN_SNAKE__",
    version="",
    configs={
        "__PLUGIN_PREFIX___ENABLED": True,
    },
)

plugs = [__PLUGIN_SNAKE__, ...]
```

Plugins are pip-installed at **image build time**, so a newly registered plug needs a rebuild:

```bash
"$WORKSPACE/.agent/compose.sh" up -d --wait --build
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py makemigrations __PLUGIN_SNAKE__
"$WORKSPACE/.agent/compose.sh" exec backend python manage.py migrate
```

`backend` and `celery` share this workspace's image, so a single rebuild covers both.
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
