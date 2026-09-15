# Transcription kit

Final versions of every file the implementation plan produces, laid out as a
mirror of the repository. Copying it in and running the tests replaces
executing the plan task by task.

From the repository root:

```bash
cp -R docs/superpowers/kit/. .
rm KIT-README.md
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

Expected: `36 passed, 2 skipped`.

The copy overwrites `.gitignore` with the existing content plus `data/` and
`.venv/`. Nothing else in the repo is touched. When the tests pass, delete
`docs/superpowers/kit/` and commit.

If a test fails, paste only that test's output into a Claude session and ask
for the fix. Do not paste the source files; they are on the branch.
