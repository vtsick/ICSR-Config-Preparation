# Repository Guidelines

## Project Structure & Module Organization

This repository is intentionally small:

- `modify_config.py`: the only source file; reads two StarOS config snapshots and generates `nn-b2b-sae-4-1-new.cfg`
- `README.md`: user-facing overview and usage notes
- `.gitignore`: excludes generated and source config files from version control
- `*.cfg`: local input/output data files used for execution only; present in the working directory but ignored by git

Keep new code in the repository root unless the project grows enough to justify a `tests/` or `src/` directory.

## Build, Test, and Development Commands

- `python3 modify_config.py`: run the tool with the expected fixed filenames in the current directory
- `python3 -m py_compile modify_config.py`: quick syntax check
- `python3 - <<'PY' ... PY`: acceptable for small local checks when debugging parsing behavior

There is no separate build step.

## Coding Style & Naming Conventions

- Use Python 3 with 4-space indentation.
- Prefer small, single-purpose functions over inline parsing logic.
- Use descriptive `UPPER_CASE` names for regex constants and `snake_case` for functions and variables.
- Keep file handling explicit with `encoding="utf-8"`.
- Preserve the script’s current style: straightforward standard-library code, no extra dependencies.

## Testing Guidelines

There is no formal test suite yet. Validate changes by:

- running `python3 modify_config.py`
- checking the reported replacement counts
- inspecting relevant lines in `nn-b2b-sae-4-1-new.cfg` with commands such as `rg -n "system hostname|nas-identifier|diameter endpoint"`

If tests are added later, place them under `tests/` and prefer `pytest` with filenames like `test_modify_config.py`.

## Commit & Pull Request Guidelines

- Keep commit messages short and imperative, for example: `Add hostname replacement logic`
- Separate behavioral changes from documentation-only changes when practical
- In pull requests, describe the config elements affected, the validation commands used, and any assumptions about StarOS syntax

## Security & Configuration Tips

- Do not commit real `.cfg` files; they may contain sensitive network details.
- Treat generated configs as local artifacts unless explicitly sanitized.
