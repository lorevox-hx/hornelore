-- 0017_photo_sessions_trip_scope.sql
-- WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C3 (2026-07-05).
--
-- A photo session can be scoped to a trip (or one stop of it): the
-- selector then draws ONLY photos linked to that trip/stop, and the
-- prompt grounds Lori's opener in the stop name ("This one's from
-- Prague"). Unscoped sessions behave exactly as before.

ALTER TABLE photo_sessions ADD COLUMN trip_id TEXT;
ALTER TABLE photo_sessions ADD COLUMN trip_stop_id TEXT;
