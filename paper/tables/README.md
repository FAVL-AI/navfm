# Generated result tables

Every file here is written by `scripts/make_tables.py` from `runs/*/metrics*.json`.

Do not edit them by hand, and do not copy numbers out of them into
`paper/draft.md` — the draft references the table files. Gate G4.c is exactly
this property: "results tables auto-generated from the logs by script, not
hand-typed". `runs/` is gitignored, so these committed files are the durable
record; regenerate with:

    python scripts/make_tables.py

A cell missing any of its pre-registered seeds is a hard failure. See the
script's docstring for the run-name convention that binds a `runs/` directory
to a table row.
