"""Google Photos Picker lane -- WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01.

Phase 1 is credentials and session lifecycle only. It creates a Picker
session at Google, opens the matching ``import_batch``, polls, and
deletes the session. It downloads no bytes and creates no candidates --
that is Phase 2, and it is a separate work item on purpose.

The one rule this package exists to honour is import rule 3 from
``import_repository``: NO RAW EXTERNAL TOKENS. Credentials live in the
process environment. Nothing in this package writes a token to the
database, returns one in a response body, or puts one in a log line.
"""
