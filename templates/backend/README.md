# __PLUGIN_TITLE__

__PLUGIN_DESCRIPTION__

A [CARE](https://github.com/ohcnetwork/care) backend plugin. It is an ordinary Django app,
pip-installed into core and registered through `plug_config.py`. Core contains no reference
to this package.

## Install (local development)

Place the plugin inside the backend checkout as a **real directory**. A symlink breaks
`docker build`, which cannot follow links out of the build context.

```bash
mv /path/to/__PLUGIN_SNAKE__ $CARE_BE/__PLUGIN_SNAKE__
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
cd $CARE_BE
make down      # safe stop. NOT `make teardown` — that deletes the database volume.
make build     # re-runs install_plugins.py
make up
make makemigrations && make migrate
```

`backend` and `celery` share one image, so a single rebuild covers both.

## API

Mounted automatically at `/api/__PLUGIN_SNAKE__/` by core's `config/urls.py`.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/__PLUGIN_SNAKE__/config/` | Client-safe configuration |

## Settings

Resolution order: `PLUGIN_CONFIGS["__PLUGIN_SNAKE__"][key]` → environment variable → default.
See `__PLUGIN_SNAKE__/settings.py`.
