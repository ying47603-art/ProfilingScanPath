# ProfilingScanPath

ProfilingScanPath is a Python desktop application skeleton for ultrasonic profiling path planning based on STEP models.

## Project Structure

```text
ProfilingScanPath/
|-- core/
|   |-- __init__.py
|   `-- app.py
|-- data/
|   |-- __init__.py
|   `-- models.py
|-- exporter/
|   |-- __init__.py
|   `-- csv_exporter.py
|-- gui/
|   |-- __init__.py
|   `-- window.py
|-- docs/
|-- tests/
|   `-- test_main.py
|-- main.py
`-- requirements.txt
```

## Recommended Dependencies

- `pytest`: run automated tests.
- `PySide6`: recommended Qt binding for the future GUI layer.

## Installation

Python 3.9 is recommended.

```bash
py -3.9 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Test

If your local environment auto-loads many third-party pytest plugins, disabling plugin autoload keeps the project tests lightweight and predictable.

```bash
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
pytest -q
```

## Current Status

- The repository currently provides only a runnable project skeleton.
- Complex business logic, GUI behavior, and STEP parsing are intentionally left as `TODO`.
