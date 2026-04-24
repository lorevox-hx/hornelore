"""Migration SQL files live here as ``NNNN_description.sql``.

The runner in ``server/code/db/migrations_runner.py`` applies every file
in this directory alphabetically, once per DB (tracked via the
``schema_migrations`` table it creates).
"""
