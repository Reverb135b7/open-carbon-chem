# Contributing to OpenCarbonChem

## Development Process

1. **Fork and clone** the repository.
2. **Create a branch** for your feature or bugfix: `git checkout -b feature/xyz`.
3. **Implement your change** following the existing code style and conventions.
4. **Add or update tests** for new functionality — all new features must have passing tests.
5. **Run the full test suite**: `python -m pytest` (the full suite must pass).
6. **Commit** with a clear message: `git commit -m "feat: add XYZ"`.
7. **Push** to your fork and open a pull request.

## Code Style
- Follow the existing [pep8](https://pep8.org/) conformance (line length ≤ 100 chars).
- Use type hints where practical; all new functions should have type annotations.
- All new modules must be importable from ``opencarbonchem`` via ``src/opencarbonchem/__init__.py``.
- New code must not increase the test suite failure count.

## Adding a New Module
1. Create the package directory under ``src/opencarbonchem/`` (e.g. ``src/opencarbonchem/pcf/``).
2. Add ``__init__.py`` with ``__all__`` exports.
3. Add the package to ``pyproject.toml`` ``[tool.setuptools.packages.find]`` if needed.
4. Add any new error classes to ``src/opencarbonchem/core/exceptions.py`` if they follow the ``OpenCarbonChemError`` hierarchy.
5. Register the new module in the roadmap (`docs/architecture.md`) and README.

## Reporting Bugs
- Use the issue tracker on GitHub.
- Include a minimal reproducer, the Python version, and the operating system.
- Tag the issue with ``bug`` and the relevant component (``pcf``, ``analytics``, ``scenarios``, etc.).

## Feature Requests
- Open an issue with the tag ``feature``.
- Describe the use case, the desired API, and how it fits the project's goals
  (carbon accounting for chemical/process industries, GHG Protocol, ISO 14067/14067).

## License
- Contributions must be licensed under the [Apache-2.0](LICENSE) license.
- Do not contribute any data, emission factors, or standards references that are
  presented as official unless they are genuinely open and properly attributed.