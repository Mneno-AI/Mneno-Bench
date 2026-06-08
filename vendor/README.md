# Local Mneno SDK

Place private or pre-release Mneno SDK wheels in `vendor/wheels/`. Wheels are
ignored by Git.

Install a specific wheel:

```bash
pip install vendor/wheels/mneno-*.whl
```

Or point setup at a wheel:

```bash
MNENO_WHEEL_PATH=/absolute/path/to/mneno.whl scripts/setup_dev.sh
```

The public package path remains:

```bash
pip install mneno
```
