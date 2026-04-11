CREATE INDEX idx_affect_events_session_ts ON affect_events(session_id, ts);

CREATE INDEX idx_attachments_entity ON media_attachments(entity_type, entity_id);

CREATE INDEX idx_attachments_media ON media_attachments(media_id);

CREATE INDEX idx_attachments_person ON media_attachments(person_id);

CREATE INDEX idx_facts_person ON facts(person_id, created_at);

CREATE INDEX idx_facts_session ON facts(session_id);

CREATE INDEX idx_graph_persons_narrator ON graph_persons(narrator_id);

CREATE INDEX idx_graph_rels_from ON graph_relationships(from_person_id);

CREATE INDEX idx_graph_rels_narrator ON graph_relationships(narrator_id);

CREATE INDEX idx_graph_rels_to ON graph_relationships(to_person_id);

CREATE INDEX idx_identity_change_person_created ON identity_change_log(person_id, created_at);

CREATE INDEX idx_interview_a_session_ts ON interview_answers(session_id, ts);

CREATE INDEX idx_interview_q_plan_ord ON interview_questions(plan_id, ord);

CREATE INDEX idx_life_phases_person ON life_phases(person_id, ord);

CREATE INDEX idx_media_person_created ON media(person_id, created_at);

CREATE INDEX idx_narrator_audit_ts ON narrator_delete_audit(ts);

CREATE INDEX idx_people_active ON people(is_deleted, updated_at);

CREATE INDEX idx_rag_chunks_doc ON rag_chunks(doc_id, chunk_index);

CREATE INDEX idx_section_summaries_session ON section_summaries(session_id, section_id);

CREATE UNIQUE INDEX idx_seg_flags_session_question ON segment_flags(session_id, question_id) WHERE question_id IS NOT NULL;

CREATE INDEX idx_segment_flags_session ON segment_flags(session_id);

CREATE INDEX idx_timeline_person_date ON timeline_events(person_id, date);

CREATE INDEX idx_turns_conv_ts ON turns(conv_id, ts, id);

CREATE TABLE affect_events (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          section_id TEXT DEFAULT '',
          affect_state TEXT NOT NULL,
          confidence REAL NOT NULL DEFAULT 0.0,
          duration_ms INTEGER NOT NULL DEFAULT 0,
          source TEXT NOT NULL DEFAULT 'camera',
          ts TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );

CREATE TABLE bio_builder_questionnaires (
            person_id TEXT PRIMARY KEY,
            questionnaire_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'unknown',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE facts (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          session_id TEXT,
          fact_type TEXT NOT NULL DEFAULT 'general',
          statement TEXT NOT NULL,
          date_text TEXT DEFAULT '',
          date_normalized TEXT DEFAULT '',
          confidence REAL DEFAULT 0.0,
          status TEXT NOT NULL DEFAULT 'extracted',
          inferred INTEGER NOT NULL DEFAULT 0,
          source_turn_index INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}', meaning_tags_json TEXT NOT NULL DEFAULT '[]', narrative_role TEXT DEFAULT NULL, experience TEXT DEFAULT NULL, reflection TEXT DEFAULT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE graph_persons (
            id TEXT PRIMARY KEY,
            narrator_id TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            first_name TEXT NOT NULL DEFAULT '',
            middle_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            maiden_name TEXT NOT NULL DEFAULT '',
            birth_date TEXT NOT NULL DEFAULT '',
            birth_place TEXT NOT NULL DEFAULT '',
            occupation TEXT NOT NULL DEFAULT '',
            deceased INTEGER NOT NULL DEFAULT 0,
            is_narrator INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'manual',
            provenance TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(narrator_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE graph_relationships (
            id TEXT PRIMARY KEY,
            narrator_id TEXT NOT NULL,
            from_person_id TEXT NOT NULL,
            to_person_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL DEFAULT '',
            subtype TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual',
            provenance TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(narrator_id) REFERENCES people(id) ON DELETE CASCADE,
            FOREIGN KEY(from_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE,
            FOREIGN KEY(to_person_id) REFERENCES graph_persons(id) ON DELETE CASCADE
        );

CREATE TABLE identity_change_log (
            id TEXT PRIMARY KEY,
            person_id TEXT NOT NULL,
            field_path TEXT NOT NULL,
            old_value TEXT DEFAULT '',
            new_value TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT 'unknown',
            status TEXT NOT NULL DEFAULT 'proposed',
            accepted_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT '',
            meta_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE interview_answers (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          person_id TEXT NOT NULL,
          question_id TEXT NOT NULL,
          answer TEXT NOT NULL DEFAULT '',
          skipped INTEGER NOT NULL DEFAULT 0,
          ts TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(question_id) REFERENCES interview_questions(id) ON DELETE CASCADE
        );

CREATE TABLE interview_plans (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

CREATE TABLE interview_projections (
            person_id TEXT PRIMARY KEY,
            projection_json TEXT NOT NULL DEFAULT '{}',
            source TEXT NOT NULL DEFAULT 'unknown',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE interview_questions (
          id TEXT PRIMARY KEY,
          plan_id TEXT NOT NULL,
          section_id TEXT NOT NULL,
          ord INTEGER NOT NULL,
          prompt TEXT NOT NULL,
          kind TEXT NOT NULL DEFAULT 'text',
          required INTEGER NOT NULL DEFAULT 0,
          profile_path TEXT,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE,
          FOREIGN KEY(section_id) REFERENCES interview_sections(id) ON DELETE CASCADE
        );

CREATE TABLE interview_sections (
          id TEXT PRIMARY KEY,
          plan_id TEXT NOT NULL,
          title TEXT NOT NULL,
          ord INTEGER NOT NULL,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE
        );

CREATE TABLE interview_sessions (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          plan_id TEXT NOT NULL,
          started_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          active_question_id TEXT, interview_softened INTEGER DEFAULT 0, softened_until_turn INTEGER DEFAULT 0, turn_count INTEGER DEFAULT 0,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE,
          FOREIGN KEY(plan_id) REFERENCES interview_plans(id) ON DELETE CASCADE
        );

CREATE TABLE life_phases (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          title TEXT NOT NULL,
          start_date TEXT DEFAULT '',
          end_date TEXT DEFAULT '',
          date_precision TEXT DEFAULT 'year',
          description TEXT DEFAULT '',
          ord INTEGER DEFAULT 0,
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE media (
          id TEXT PRIMARY KEY,
          person_id TEXT,
          kind TEXT NOT NULL DEFAULT 'image',
          filename TEXT NOT NULL DEFAULT '',
          mime TEXT NOT NULL DEFAULT '',
          bytes INTEGER NOT NULL DEFAULT 0,
          sha256 TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}', description TEXT NOT NULL DEFAULT '', taken_at TEXT DEFAULT NULL, location_name TEXT DEFAULT NULL, latitude REAL DEFAULT NULL, longitude REAL DEFAULT NULL, exif_json TEXT NOT NULL DEFAULT '{}',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
        );

CREATE TABLE media_attachments (
          id TEXT PRIMARY KEY,
          media_id TEXT NOT NULL,
          entity_type TEXT NOT NULL DEFAULT 'memoir_section',
          entity_id TEXT NOT NULL,
          person_id TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE SET NULL
        );

CREATE TABLE narrator_delete_audit (
          id TEXT PRIMARY KEY,
          action TEXT NOT NULL,
          person_id TEXT NOT NULL,
          display_name TEXT NOT NULL DEFAULT '',
          requested_by TEXT DEFAULT NULL,
          dependency_counts_json TEXT NOT NULL DEFAULT '{}',
          result TEXT NOT NULL DEFAULT 'success',
          error_detail TEXT DEFAULT NULL,
          ts TEXT NOT NULL
        );

CREATE TABLE people (
          id TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          role TEXT DEFAULT '',
          date_of_birth TEXT DEFAULT '',
          place_of_birth TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        , is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT DEFAULT NULL, deleted_by TEXT DEFAULT NULL, delete_reason TEXT DEFAULT '', undo_expires_at TEXT DEFAULT NULL);

CREATE TABLE profiles (
          person_id TEXT PRIMARY KEY,
          profile_json TEXT NOT NULL DEFAULT '{}',
          updated_at TEXT NOT NULL,
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE rag_chunks (
          id TEXT PRIMARY KEY,
          doc_id TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          text TEXT NOT NULL,
          FOREIGN KEY(doc_id) REFERENCES rag_docs(id) ON DELETE CASCADE
        );

CREATE TABLE rag_docs (
          id TEXT PRIMARY KEY,
          title TEXT,
          source TEXT,
          created_at TEXT,
          text TEXT
        );

CREATE TABLE section_summaries (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          person_id TEXT NOT NULL,
          section_id TEXT NOT NULL,
          section_title TEXT NOT NULL DEFAULT '',
          summary TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );

CREATE TABLE segment_flags (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          question_id TEXT,
          section_id TEXT,
          sensitive INTEGER NOT NULL DEFAULT 0,
          sensitive_category TEXT DEFAULT '',
          excluded_from_memoir INTEGER NOT NULL DEFAULT 1,
          private INTEGER NOT NULL DEFAULT 1,
          deleted INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          FOREIGN KEY(session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
        );

CREATE TABLE sessions (
          conv_id TEXT PRIMARY KEY,
          title TEXT DEFAULT '',
          updated_at TEXT,
          payload_json TEXT DEFAULT '{}'
        );

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE timeline_events (
          id TEXT PRIMARY KEY,
          person_id TEXT NOT NULL,
          date TEXT NOT NULL,                 -- ISO date or datetime string
          title TEXT NOT NULL,
          body TEXT NOT NULL DEFAULT '',
          kind TEXT NOT NULL DEFAULT 'event',
          created_at TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}', end_date TEXT DEFAULT '', date_precision TEXT DEFAULT 'exact_day', is_approximate INTEGER DEFAULT 0, confidence REAL DEFAULT 1.0, status TEXT DEFAULT 'reviewed', source_session_ids TEXT DEFAULT '[]', source_fact_ids TEXT DEFAULT '[]', tags TEXT DEFAULT '[]', display_date TEXT DEFAULT '', phase_id TEXT DEFAULT '',
          FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );

CREATE TABLE turns (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conv_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          ts TEXT NOT NULL,
          anchor_id TEXT DEFAULT '',
          meta_json TEXT DEFAULT '{}',
          FOREIGN KEY(conv_id) REFERENCES sessions(conv_id) ON DELETE CASCADE
        );

