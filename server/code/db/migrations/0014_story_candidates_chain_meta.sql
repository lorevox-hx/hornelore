-- WO-LORI-FACTUAL-CHAIN-CAPTURE-01 Phase 4 (2026-06-24) — chain metadata
-- column on story_candidates. When factual_chain_capture.detect_factual_
-- chain fires on a narrator turn, the chat path records the chain's
-- anchors / cue_labels / confidence into chain_meta_json so:
--   * the operator review surface can flag chain stories distinct from
--     emotional / sensory stories;
--   * Phase 4 memoir export can prefer chain-shaped narration when
--     stitching trip / induction / migration / medical sequences;
--   * downstream extractor passes get a high-signal "this row is a
--     chronological chain" hint without re-running the classifier.
--
-- Default '{}' preserves byte-stable behavior for rows that pre-date
-- the wiring and for any caller that omits the kwarg.
--
-- Shape (written by chat_ws via story_preservation.preserve_turn):
--   {
--     "chain_story_candidate": true,
--     "chain_anchors": ["Stanley", "Fargo", "top score", "meal tickets"],
--     "chain_cue_labels": ["multi_place_sequence", "travel_leg_sequence"],
--     "chain_confidence": 0.90,
--     "chain_missing_links": []          -- reserved for Phase 4 follow-up
--   }
--
-- Idempotent under SQLite via the schema_migrations runner — this file
-- executes exactly once per fresh DB.

BEGIN;

ALTER TABLE story_candidates
    ADD COLUMN chain_meta_json TEXT NOT NULL DEFAULT '{}';

COMMIT;
