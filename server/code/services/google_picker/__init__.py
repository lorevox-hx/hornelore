"""Google Photos Picker lane -- WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01.

Phase 1 is credentials and session lifecycle: it creates a Picker
session at Google, opens the matching ``import_batch``, polls, and
deletes the session. Phase 2A adds one read -- listing the items the
operator picked. Neither downloads bytes nor creates candidates; that
is Phase 2B, and it is a separate work item on purpose.

The one rule this package exists to honour is import rule 3 from
``import_repository``: NO RAW EXTERNAL TOKENS. Credentials live in the
process environment. Nothing in this package writes a token to the
database, returns one in a response body, or puts one in a log line.
"""
