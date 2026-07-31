## O2DESPy

O2DESPy is a **Python library for Object-Oriented Discrete-Event Simulation (O2DES)**.
It provides a small set of primitives (e.g., a simulation “sandbox”, event scheduling, child components, and random distributions) to build modular, composable discrete-event simulation models.

This repository also contains a set of runnable demos (`demos/demo1` … `demos/demo10`) that illustrate common patterns such as:

- hello-world style event scheduling
- birth–death processes
- queues / servers and tandem queue networks (push/pull variants)

## Requirements

- Python **>= 3.7**

## Install (recommended: editable install for local development)

From the repository root:

```bash
python -m venv .venv
```

On Windows PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

On macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Quick start

Run the smallest demo (prints 10 “Hello World” events with timestamps):

```bash
python -m demos.demo1
```

## Run the demos

Each demo is a Python module with a `__main__.py`. Run them from the repo root:

```bash
python -m demos.demo1
python -m demos.demo2
python -m demos.demo3
python -m demos.demo4
python -m demos.demo5
python -m demos.demo6
python -m demos.demo7
python -m demos.demo8
python -m demos.demo9
python -m demos.demo10
```

There is also a `demos/main.py`, but it currently imports `Config` from `o2des.config`. If you see an `ImportError` about `Config`, use the per-demo commands above (they’re the most reliable entrypoints).

## Build and test

If you have tests set up in `tests/`:

```bash
pytest
```

## Project layout (high level)

- `o2des/`: the library code
- `demos/`: runnable demo models
- `requirements.txt`: runtime dependencies
- `pyproject.toml`: packaging metadata (setuptools)