-- 0064_graph_revision.sql — Batch B-4 (2026-09-23)
--
-- A server-side revision for each narrator's family graph.
--
-- WHY. PUT /api/graph/{narrator_id} is a FULL REPLACEMENT, and until now the
-- server accepted it from any client holding any copy of the graph. Two tabs,
-- or one tab that hydrated before another edit landed, silently replaced the
-- newer family with the older one. The browser's own guards
-- (`_graphRestoreGen`, `_restoreFailedFor`) are local request counters; the
-- server checked nothing.
--
-- Every graph write bumps this revision. GET returns it; a PUT must carry the
-- revision it hydrated from and is refused (409) if the graph moved since.
--
-- ONE ROW PER NARRATOR, keyed on narrator_id alone: the merge collision hunt
-- needs single-column keys. Erased with the narrator by cascade.

CREATE TABLE IF NOT EXISTS graph_revisions (
    narrator_id  TEXT PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    revision     INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_at   TEXT NOT NULL
);
