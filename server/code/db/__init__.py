"""DB migrations package for hornelore.

This package holds the NNNN_*.sql migration files that the migration
runner applies after the monolithic ``server/code/api/db.py:init_db()``
has created the legacy pre-WO schema. Phase 1 of WO-LORI-PHOTO lands
the first migration (``0001_lori_photo_shared.sql``).
"""
