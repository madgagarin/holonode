**EN** | [ES](https://github.com/madgagarin/holonode/blob/main/docs/es/CONTRIBUTING.md) | [RU](https://github.com/madgagarin/holonode/blob/main/docs/ru/CONTRIBUTING.md)

# Contributing to Holonode SDK

Thank you for helping improve the Shell of our ecosystem!

## Setup

1.  Clone the repository and navigate to this directory.
2.  Install development dependencies:
    ```bash
    pip install -e .[dev]
    ```

## Quality Control

We use `ruff` for linting and formatting, and `mypy` for type checking. Please ensure your changes pass these checks:

```bash
# Linting and formatting
ruff check .
ruff format .

# Type checking
mypy src/holonode
```

## Testing

Run the worker-specific tests:

```bash
pytest
```

## Adding New Features

- If adding a new configuration parameter, update `src/holonode/config.py`.
- If changing the protocol interaction, ensure compatibility with the `rxon` package.
- Always update the `README.md` if the user-facing API changes.
- All new code must have type hints.
