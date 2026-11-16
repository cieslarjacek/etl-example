# etl-example

Tracking-survey ETL API example: validate, clean, transform, load
and summarise survey waves.

## Development

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.15
from `.python-version`.

```bash
make install     # create .venv from uv.lock
make check       # lint, type-check and test
make help        # list all targets
```
