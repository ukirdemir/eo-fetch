# Releasing eo-fetch-api to PyPI

PyPI never accepts the same version twice, and a published file cannot be replaced (a bad release can only be "yanked" and superseded by a new version). So every release goes through TestPyPI first.

## One-time setup

1. Create an account at https://pypi.org and at https://test.pypi.org (two separate accounts) and switch on two-factor authentication on both. PyPI requires it for uploading.
2. On each site create an API token: Account settings, API tokens, Add API token. For the first upload the project does not exist yet, so the scope must be "Entire account"; after the first upload, replace it by a token limited to the project `eo-fetch-api`. The token starts with `pypi-` and is shown only once: store it in a password manager. Never put it in the repository, in chat or in a command line.
3. Check the name is free: https://pypi.org/project/eo-fetch-api/ must show "404 Not Found" before the first release. PyPI also rejects names that differ from an existing project only by capitals, hyphens, dots or underscores (`eo-fetch` was refused for this reason). The PyPI name (`eo-fetch-api`) differs from the import name (`eo_fetch`) on purpose.

## Every release

1. Update `CHANGELOG.md`, and `__version__` in `src/eo_fetch/__init__.py` (the only place; `pyproject.toml` reads it). The package page on PyPI is built from `packaging/README_PYPI.md` (Python API only, short); `README.md` is the longer GitHub version. Keep both in step. A practice upload to TestPyPI uses a pre-release version such as `1.0.0rc1`, because a version or file name can never be uploaded twice, even after deleting it.
2. Quality gate: `ruff check .`, `ruff format --check .`, `pytest -q`.
3. Build (creates `dist/eo_fetch_api-X.Y.Z.tar.gz` and `dist/eo_fetch_api-X.Y.Z-py3-none-any.whl`): delete the old `dist` folder, then `python -m build`.
4. Check the metadata: `twine check dist/*` (both files must say PASSED).
5. Try the wheel in a clean environment: `python -m venv %TEMP%\eo-test`, then `%TEMP%\eo-test\Scripts\pip install dist\eo_fetch_api-X.Y.Z-py3-none-any.whl`, then `%TEMP%\eo-test\Scripts\eo-fetch providers`. Use Python 3.12 or 3.13 for the environment.
6. Upload to TestPyPI: `twine upload --repository testpypi dist/*`. Username: `__token__`; password: the TestPyPI token (the prompt is hidden).
7. Install from TestPyPI in a clean environment: `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ eo-fetch-api`, and run `eo-fetch providers`. (The extra index is needed because the dependencies live on the real PyPI.)
8. Upload to PyPI: `twine upload dist/*` with the PyPI token.
9. Tag and publish: `git tag vX.Y.Z`, `git push origin vX.Y.Z`, then `gh release create vX.Y.Z --notes-file CHANGELOG.md` (or write the notes by hand).
10. Verify as a user would: new clean environment, `pip install eo-fetch-api`, then `python -c "import eo_fetch as eof; print(eof.__version__)"`.
