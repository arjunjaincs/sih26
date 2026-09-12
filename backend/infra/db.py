"""
PRAMAAN SQLite persistence layer.

Responsibilities:
  - Initialize the database (create tables, enable WAL)
  - Provide repository objects for each domain entity
  - All SQL is parameterized — no string interpolation

Design choices:
  - Uses stdlib sqlite3 only (no SQLAlchemy)
  - WAL mode for better concurrency on reads
  - Row factory returns sqlite3.Row so columns are accessible by name
  - JSON columns store serialized dicts/lists
  - All timestamps stored as ISO 8601 strings (UTC)
  - Repositories take a connection — callers manage transactions
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.domain.entities import (
    Assessment,
    Asset,
    AuditEvent,
    Dataset,
    DetectorResult,
    Evidence,
    Finding,
    ModelArtifact,
    ProvenanceManifest,
    Sample,
)
from backend.domain.enums import (
    AccessLevel,
    AssetType,
    AssessmentState,
    AssessmentType,
    AuditEventType,
    DatasetFormat,
    DetectorStatus,
    EvidenceType,
    FindingCategory,
    ModelFramework,
    Severity,
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id   TEXT PRIMARY KEY,
    assessment_type TEXT NOT NULL DEFAULT 'live',
    title           TEXT NOT NULL,
    description     TEXT,
    state           TEXT NOT NULL DEFAULT 'created',
    software_version TEXT NOT NULL DEFAULT '1.0.0',
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id        TEXT PRIMARY KEY,
    assessment_id   TEXT NOT NULL REFERENCES assessments(assessment_id),
    asset_type      TEXT NOT NULL,
    name            TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    registered_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id      TEXT PRIMARY KEY REFERENCES assets(asset_id),
    assessment_id   TEXT NOT NULL REFERENCES assessments(assessment_id),
    format          TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    class_names_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS samples (
    sample_id       TEXT PRIMARY KEY,
    dataset_id      TEXT NOT NULL REFERENCES datasets(dataset_id),
    file_name       TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    phash           TEXT,
    dhash           TEXT,
    width           INTEGER,
    height          INTEGER,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    labels_json     TEXT NOT NULL DEFAULT '[]',
    contributor     TEXT
);

CREATE TABLE IF NOT EXISTS model_artifacts (
    model_id        TEXT PRIMARY KEY REFERENCES assets(asset_id),
    assessment_id   TEXT NOT NULL REFERENCES assessments(assessment_id),
    framework       TEXT NOT NULL DEFAULT 'unknown',
    access_level    TEXT NOT NULL DEFAULT 'black_box',
    source_path     TEXT NOT NULL,
    declared_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          TEXT PRIMARY KEY,
    assessment_id       TEXT NOT NULL REFERENCES assessments(assessment_id),
    asset_id            TEXT NOT NULL REFERENCES assets(asset_id),
    category            TEXT NOT NULL,
    subcategory         TEXT NOT NULL DEFAULT '',
    severity            TEXT NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    detection_method    TEXT NOT NULL,
    detector_id         TEXT NOT NULL,
    limitations_json    TEXT NOT NULL DEFAULT '[]',
    recommended_disposition TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT 'LIVE_ANALYSIS',
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id     TEXT PRIMARY KEY,
    finding_id      TEXT NOT NULL REFERENCES findings(finding_id),
    detector_id     TEXT NOT NULL,
    evidence_type   TEXT NOT NULL,
    description     TEXT NOT NULL,
    data_json       TEXT NOT NULL,
    artifact_path   TEXT,
    artifact_sha256 TEXT
);

CREATE TABLE IF NOT EXISTS detector_results (
    result_id           TEXT PRIMARY KEY,
    assessment_id       TEXT NOT NULL REFERENCES assessments(assessment_id),
    asset_id            TEXT NOT NULL REFERENCES assets(asset_id),
    detector_id         TEXT NOT NULL,
    detector_version    TEXT NOT NULL,
    status              TEXT NOT NULL,
    error               TEXT,
    findings_count      INTEGER NOT NULL DEFAULT 0,
    evidence_count      INTEGER NOT NULL DEFAULT 0,
    duration_ms         INTEGER,
    started_at          TEXT NOT NULL,
    completed_at        TEXT
);

CREATE TABLE IF NOT EXISTS provenance_manifests (
    manifest_id             TEXT PRIMARY KEY,
    manifest_version        TEXT NOT NULL DEFAULT '1',
    assessment_id           TEXT NOT NULL REFERENCES assessments(assessment_id),
    input_sha256            TEXT NOT NULL,
    model_sha256            TEXT NOT NULL,
    preprocessing_json      TEXT NOT NULL,
    inference_json          TEXT NOT NULL,
    output_sha256           TEXT NOT NULL,
    timestamp_utc           TEXT NOT NULL,
    nonce                   TEXT NOT NULL,
    sequence                INTEGER NOT NULL DEFAULT 0,
    pramaan_version         TEXT NOT NULL DEFAULT '1.0.0',
    digest                  TEXT,
    signature               TEXT
);

-- AUDIT CHAIN: append-only; no UPDATE/DELETE permitted at application level
CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    timestamp_utc   TEXT NOT NULL,
    assessment_id   TEXT,
    actor           TEXT NOT NULL DEFAULT 'system',
    payload_digest  TEXT NOT NULL,
    previous_hash   TEXT NOT NULL,
    current_hash    TEXT NOT NULL
);

-- Structured JSON payload for each audit event.
-- Keyed by event_id.  Append-only by application convention.
-- Stored separately so the chain table stays compact (no large blobs).
CREATE TABLE IF NOT EXISTS audit_event_payloads (
    event_id        TEXT PRIMARY KEY REFERENCES audit_events(event_id),
    payload_json    TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_assets_assessment
    ON assets(assessment_id);
CREATE INDEX IF NOT EXISTS idx_samples_dataset
    ON samples(dataset_id);
CREATE INDEX IF NOT EXISTS idx_findings_assessment
    ON findings(assessment_id);
CREATE INDEX IF NOT EXISTS idx_evidence_finding
    ON evidence(finding_id);
CREATE INDEX IF NOT EXISTS idx_detector_results_assessment
    ON detector_results(assessment_id);
CREATE INDEX IF NOT EXISTS idx_audit_assessment
    ON audit_events(assessment_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
    ON audit_events(timestamp_utc);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id           TEXT PRIMARY KEY,
    asset_type          TEXT NOT NULL,
    original_filename   TEXT NOT NULL,
    safe_filename       TEXT NOT NULL,
    sha256              TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    content_type        TEXT,
    storage_path        TEXT NOT NULL,
    format              TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uploads_created_at
    ON uploads(created_at);
"""


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def open_db(db_path: Path) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database at *db_path*.

    - Enables WAL journal mode
    - Enables foreign key enforcement
    - Sets row_factory to sqlite3.Row for name-based column access
    - Creates tables and indexes if they do not exist
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(samples)").fetchall()}
    if "contributor" not in cols:
        conn.execute("ALTER TABLE samples ADD COLUMN contributor TEXT")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _j(obj: Any) -> str:
    """Serialize *obj* to JSON string for storage."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _dj(s: str | None) -> Any:
    """Deserialize JSON string from storage; returns None if input is None."""
    if s is None:
        return None
    return json.loads(s)


# ---------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------

class AssessmentRepository:
    """CRUD for Assessment records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, a: Assessment) -> None:
        self._conn.execute(
            """
            INSERT INTO assessments
                (assessment_id, assessment_type, title, description, state,
                 software_version, created_at, started_at, completed_at, error)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                a.assessment_id,
                a.assessment_type.value,
                a.title,
                a.description,
                a.state.value,
                a.software_version,
                a.created_at.isoformat(),
                a.started_at.isoformat() if a.started_at else None,
                a.completed_at.isoformat() if a.completed_at else None,
                a.error,
            ),
        )
        self._conn.commit()

    def update_state(
        self,
        assessment_id: str,
        state: AssessmentState,
        *,
        error: str | None = None,
    ) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        if state == AssessmentState.ANALYZING:
            self._conn.execute(
                "UPDATE assessments SET state=?, started_at=? WHERE assessment_id=?",
                (state.value, now, assessment_id),
            )
        elif state in (AssessmentState.COMPLETE, AssessmentState.FAILED):
            self._conn.execute(
                "UPDATE assessments SET state=?, completed_at=?, error=? WHERE assessment_id=?",
                (state.value, now, error, assessment_id),
            )
        else:
            self._conn.execute(
                "UPDATE assessments SET state=? WHERE assessment_id=?",
                (state.value, assessment_id),
            )
        self._conn.commit()

    def get(self, assessment_id: str) -> Assessment | None:
        row = self._conn.execute(
            "SELECT * FROM assessments WHERE assessment_id=?", (assessment_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_assessment(row)

    def list_all(self) -> list[Assessment]:
        rows = self._conn.execute(
            "SELECT * FROM assessments ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_assessment(r) for r in rows]

    @staticmethod
    def _row_to_assessment(row: sqlite3.Row) -> Assessment:
        from datetime import datetime

        def _dt(s: str | None) -> datetime | None:
            return datetime.fromisoformat(s) if s else None

        return Assessment(
            assessment_id=row["assessment_id"],
            assessment_type=AssessmentType(row["assessment_type"]),
            title=row["title"],
            description=row["description"],
            state=AssessmentState(row["state"]),
            software_version=row["software_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=_dt(row["started_at"]),
            completed_at=_dt(row["completed_at"]),
            error=row["error"],
        )


class AssetRepository:
    """CRUD for Asset records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, a: Asset) -> None:
        self._conn.execute(
            """
            INSERT INTO assets
                (asset_id, assessment_id, asset_type, name, sha256, size_bytes, registered_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                a.asset_id,
                a.assessment_id,
                a.asset_type.value,
                a.name,
                a.sha256,
                a.size_bytes,
                a.registered_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get(self, asset_id: str) -> Asset | None:
        row = self._conn.execute(
            "SELECT * FROM assets WHERE asset_id=?", (asset_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_asset(row)

    def list_by_assessment(self, assessment_id: str) -> list[Asset]:
        rows = self._conn.execute(
            "SELECT * FROM assets WHERE assessment_id=?", (assessment_id,)
        ).fetchall()
        return [self._row_to_asset(r) for r in rows]

    @staticmethod
    def _row_to_asset(row: sqlite3.Row) -> Asset:
        from datetime import datetime
        return Asset(
            asset_id=row["asset_id"],
            assessment_id=row["assessment_id"],
            asset_type=AssetType(row["asset_type"]),
            name=row["name"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            registered_at=datetime.fromisoformat(row["registered_at"]),
        )


class DatasetRepository:
    """CRUD for Dataset records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, d: Dataset) -> None:
        self._conn.execute(
            """
            INSERT INTO datasets
                (dataset_id, assessment_id, format, source_path,
                 sample_count, class_names_json)
            VALUES (?,?,?,?,?,?)
            """,
            (
                d.dataset_id,
                d.assessment_id,
                d.format.value,
                d.source_path,
                d.sample_count,
                _j(d.class_names),
            ),
        )
        self._conn.commit()

    def update_sample_count(self, dataset_id: str, count: int) -> None:
        self._conn.execute(
            "UPDATE datasets SET sample_count=? WHERE dataset_id=?",
            (count, dataset_id),
        )
        self._conn.commit()

    def get(self, dataset_id: str) -> Dataset | None:
        row = self._conn.execute(
            "SELECT * FROM datasets WHERE dataset_id=?", (dataset_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dataset(row)

    @staticmethod
    def _row_to_dataset(row: sqlite3.Row) -> Dataset:
        return Dataset(
            dataset_id=row["dataset_id"],
            assessment_id=row["assessment_id"],
            format=DatasetFormat(row["format"]),
            source_path=row["source_path"],
            sample_count=row["sample_count"],
            class_names=json.loads(row["class_names_json"]),
        )


class SampleRepository:
    """CRUD for Sample records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, s: Sample) -> None:
        self._conn.execute(
            """
            INSERT INTO samples
                (sample_id, dataset_id, file_name, sha256,
                 phash, dhash, width, height, file_size_bytes, labels_json, contributor)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                s.sample_id,
                s.dataset_id,
                s.file_name,
                s.sha256,
                s.phash,
                s.dhash,
                s.width,
                s.height,
                s.file_size_bytes,
                _j(s.labels),
                s.contributor,
            ),
        )
        # Intentionally not committing per-sample — callers batch-commit

    def insert_many(self, samples: list[Sample]) -> None:
        """Insert multiple samples in a single transaction."""
        self._conn.executemany(
            """
            INSERT INTO samples
                (sample_id, dataset_id, file_name, sha256,
                 phash, dhash, width, height, file_size_bytes, labels_json, contributor)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    s.sample_id, s.dataset_id, s.file_name, s.sha256,
                    s.phash, s.dhash, s.width, s.height, s.file_size_bytes,
                    _j(s.labels), s.contributor,
                )
                for s in samples
            ],
        )
        self._conn.commit()

    def list_by_dataset(self, dataset_id: str) -> list[Sample]:
        rows = self._conn.execute(
            "SELECT * FROM samples WHERE dataset_id=?", (dataset_id,)
        ).fetchall()
        return [self._row_to_sample(r) for r in rows]

    def count_by_dataset(self, dataset_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM samples WHERE dataset_id=?", (dataset_id,)
        ).fetchone()
        return row["n"] if row else 0

    @staticmethod
    def _row_to_sample(row: sqlite3.Row) -> Sample:
        contributor = row["contributor"] if "contributor" in row.keys() else None
        return Sample(
            sample_id=row["sample_id"],
            dataset_id=row["dataset_id"],
            file_name=row["file_name"],
            sha256=row["sha256"],
            phash=row["phash"],
            dhash=row["dhash"],
            width=row["width"],
            height=row["height"],
            file_size_bytes=row["file_size_bytes"],
            labels=json.loads(row["labels_json"]),
            contributor=contributor,
        )


class ModelArtifactRepository:
    """CRUD for ModelArtifact records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, m: ModelArtifact) -> None:
        self._conn.execute(
            """
            INSERT INTO model_artifacts
                (model_id, assessment_id, framework, access_level,
                 source_path, declared_sha256)
            VALUES (?,?,?,?,?,?)
            """,
            (
                m.model_id,
                m.assessment_id,
                m.framework.value,
                m.access_level.value,
                m.source_path,
                m.declared_sha256,
            ),
        )
        self._conn.commit()

    def get(self, model_id: str) -> ModelArtifact | None:
        row = self._conn.execute(
            "SELECT * FROM model_artifacts WHERE model_id=?", (model_id,)
        ).fetchone()
        if row is None:
            return None
        return ModelArtifact(
            model_id=row["model_id"],
            assessment_id=row["assessment_id"],
            framework=ModelFramework(row["framework"]),
            access_level=AccessLevel(row["access_level"]),
            source_path=row["source_path"],
            declared_sha256=row["declared_sha256"],
        )


class FindingRepository:
    """CRUD for Finding records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, f: Finding) -> None:
        self._conn.execute(
            """
            INSERT INTO findings
                (finding_id, assessment_id, asset_id, category, subcategory,
                 severity, title, description, detection_method, detector_id,
                 limitations_json, recommended_disposition, source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f.finding_id,
                f.assessment_id,
                f.asset_id,
                f.category.value,
                f.subcategory,
                f.severity.value,
                f.title,
                f.description,
                f.detection_method,
                f.detector_id,
                _j(f.limitations),
                f.recommended_disposition,
                f.source,
                f.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def list_by_assessment(self, assessment_id: str) -> list[Finding]:
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE assessment_id=? ORDER BY created_at",
            (assessment_id,),
        ).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def get(self, finding_id: str) -> Finding | None:
        row = self._conn.execute(
            "SELECT * FROM findings WHERE finding_id=?", (finding_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_finding(row)

    @staticmethod
    def _row_to_finding(row: sqlite3.Row) -> Finding:
        from datetime import datetime
        return Finding(
            finding_id=row["finding_id"],
            assessment_id=row["assessment_id"],
            asset_id=row["asset_id"],
            category=FindingCategory(row["category"]),
            subcategory=row["subcategory"],
            severity=Severity(row["severity"]),
            title=row["title"],
            description=row["description"],
            detection_method=row["detection_method"],
            detector_id=row["detector_id"],
            limitations=json.loads(row["limitations_json"]),
            recommended_disposition=row["recommended_disposition"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class EvidenceRepository:
    """CRUD for Evidence records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, e: Evidence) -> None:
        self._conn.execute(
            """
            INSERT INTO evidence
                (evidence_id, finding_id, detector_id, evidence_type,
                 description, data_json, artifact_path, artifact_sha256)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                e.evidence_id,
                e.finding_id,
                e.detector_id,
                e.evidence_type.value,
                e.description,
                _j(e.data),
                e.artifact_path,
                e.artifact_sha256,
            ),
        )
        self._conn.commit()

    def list_by_finding(self, finding_id: str) -> list[Evidence]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE finding_id=?", (finding_id,)
        ).fetchall()
        return [self._row_to_evidence(r) for r in rows]

    @staticmethod
    def _row_to_evidence(row: sqlite3.Row) -> Evidence:
        return Evidence(
            evidence_id=row["evidence_id"],
            finding_id=row["finding_id"],
            detector_id=row["detector_id"],
            evidence_type=EvidenceType(row["evidence_type"]),
            description=row["description"],
            data=json.loads(row["data_json"]),
            artifact_path=row["artifact_path"],
            artifact_sha256=row["artifact_sha256"],
        )


class DetectorResultRepository:
    """CRUD for DetectorResult records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, r: DetectorResult) -> None:
        self._conn.execute(
            """
            INSERT INTO detector_results
                (result_id, assessment_id, asset_id, detector_id,
                 detector_version, status, error, findings_count,
                 evidence_count, duration_ms, started_at, completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                r.result_id,
                r.assessment_id,
                r.asset_id,
                r.detector_id,
                r.detector_version,
                r.status.value,
                r.error,
                r.findings_count,
                r.evidence_count,
                r.duration_ms,
                r.started_at.isoformat(),
                r.completed_at.isoformat() if r.completed_at else None,
            ),
        )
        self._conn.commit()

    def list_by_assessment(self, assessment_id: str) -> list[DetectorResult]:
        rows = self._conn.execute(
            "SELECT * FROM detector_results WHERE assessment_id=? ORDER BY started_at",
            (assessment_id,),
        ).fetchall()
        return [self._row_to_result(r) for r in rows]

    @staticmethod
    def _row_to_result(row: sqlite3.Row) -> DetectorResult:
        from datetime import datetime

        def _dt(s: str | None) -> datetime | None:
            return datetime.fromisoformat(s) if s else None

        return DetectorResult(
            result_id=row["result_id"],
            assessment_id=row["assessment_id"],
            asset_id=row["asset_id"],
            detector_id=row["detector_id"],
            detector_version=row["detector_version"],
            status=DetectorStatus(row["status"]),
            error=row["error"],
            findings_count=row["findings_count"],
            evidence_count=row["evidence_count"],
            duration_ms=row["duration_ms"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=_dt(row["completed_at"]),
        )


class ProvenanceRepository:
    """CRUD for ProvenanceManifest records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, m: ProvenanceManifest) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO assessments (assessment_id, title, state, created_at)
            VALUES (?, ?, 'complete', ?)
            """,
            (m.assessment_id, f"Inference Stream {m.assessment_id}", now_iso),
        )
        self._conn.execute(
            """
            INSERT INTO provenance_manifests
                (manifest_id, manifest_version, assessment_id,
                 input_sha256, model_sha256, preprocessing_json,
                 inference_json, output_sha256, timestamp_utc,
                 nonce, sequence, pramaan_version, digest, signature)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                m.manifest_id,
                m.manifest_version,
                m.assessment_id,
                m.input_sha256,
                m.model_sha256,
                _j(m.preprocessing_config),
                _j(m.inference_config),
                m.output_sha256,
                m.timestamp_utc,
                m.nonce,
                m.sequence,
                m.pramaan_version,
                m.digest,
                m.signature,
            ),
        )
        self._conn.commit()

    def get(self, manifest_id: str) -> ProvenanceManifest | None:
        row = self._conn.execute(
            "SELECT * FROM provenance_manifests WHERE manifest_id=?", (manifest_id,)
        ).fetchone()
        if row is None:
            return None
        return ProvenanceManifest(
            manifest_id=row["manifest_id"],
            manifest_version=row["manifest_version"],
            assessment_id=row["assessment_id"],
            input_sha256=row["input_sha256"],
            model_sha256=row["model_sha256"],
            preprocessing_config=json.loads(row["preprocessing_json"]),
            inference_config=json.loads(row["inference_json"]),
            output_sha256=row["output_sha256"],
            timestamp_utc=row["timestamp_utc"],
            nonce=row["nonce"],
            sequence=row["sequence"],
            pramaan_version=row["pramaan_version"],
            digest=row["digest"],
            signature=row["signature"],
        )

    def list_by_assessment(self, assessment_id: str) -> list[ProvenanceManifest]:
        rows = self._conn.execute(
            "SELECT * FROM provenance_manifests WHERE assessment_id=? ORDER BY sequence",
            (assessment_id,),
        ).fetchall()
        return [self.get(r["manifest_id"]) for r in rows]  # type: ignore[misc]

    def list_all(self) -> list[ProvenanceManifest]:
        """Return all stored manifests ordered by sequence, rowid."""
        rows = self._conn.execute(
            "SELECT manifest_id FROM provenance_manifests ORDER BY sequence, rowid"
        ).fetchall()
        return [m for r in rows if (m := self.get(r["manifest_id"])) is not None]

    def max_sequence(self, assessment_id: str) -> int:
        """Return the highest sequence number for this assessment (or -1)."""
        row = self._conn.execute(
            "SELECT MAX(sequence) AS m FROM provenance_manifests WHERE assessment_id=?",
            (assessment_id,),
        ).fetchone()
        val = row["m"] if row else None
        return val if val is not None else -1


class AuditRepository:
    """
    Append-only repository for AuditEvent records.

    No UPDATE or DELETE methods are provided — this is intentional.
    The only allowed operations are append and read.
    """

    GENESIS_HASH: str = "0" * 64  # 64 zeros — the sentinel for the first event

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event: AuditEvent) -> None:
        """Append a single audit event. No UPDATE, no DELETE."""
        self._conn.execute(
            """
            INSERT INTO audit_events
                (event_id, event_type, timestamp_utc, assessment_id,
                 actor, payload_digest, previous_hash, current_hash)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                event.event_id,
                event.event_type.value,
                event.timestamp_utc,
                event.assessment_id,
                event.actor,
                event.payload_digest,
                event.previous_hash,
                event.current_hash,
            ),
        )
        self._conn.commit()

    def last_hash(self) -> str:
        """Return the current_hash of the most recent event, or GENESIS_HASH."""
        row = self._conn.execute(
            "SELECT current_hash FROM audit_events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row["current_hash"] if row else self.GENESIS_HASH

    def get(self, event_id: str) -> AuditEvent | None:
        """Return a single AuditEvent by ID, or None."""
        row = self._conn.execute(
            "SELECT * FROM audit_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        return self._row_to_event(row) if row else None

    def list_all(self) -> list[AuditEvent]:
        """Return all events in insertion order."""
        rows = self._conn.execute(
            "SELECT * FROM audit_events ORDER BY rowid ASC"
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def list_by_assessment(self, assessment_id: str) -> list[AuditEvent]:
        rows = self._conn.execute(
            "SELECT * FROM audit_events WHERE assessment_id=? ORDER BY rowid ASC",
            (assessment_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            event_id=row["event_id"],
            event_type=AuditEventType(row["event_type"]),
            timestamp_utc=row["timestamp_utc"],
            assessment_id=row["assessment_id"],
            actor=row["actor"],
            payload_digest=row["payload_digest"],
            previous_hash=row["previous_hash"],
            current_hash=row["current_hash"],
        )


class AuditPayloadRepository:
    """
    Append-only store for structured JSON payloads linked to audit events.

    The audit_events table stores only a payload_digest (SHA-256 of the JSON).
    The actual payload JSON lives here, keyed by event_id.  This keeps the
    chain table lean while making payload content available for inspection.

    No UPDATE or DELETE methods — payloads are immutable once recorded.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, event_id: str, payload: dict) -> None:
        """Insert a payload for the given event_id. Raises on duplicate."""
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO audit_event_payloads (event_id, payload_json) VALUES (?,?)",
            (event_id, payload_json),
        )
        self._conn.commit()

    def get(self, event_id: str) -> dict | None:
        """Return the payload dict for *event_id*, or None if not stored."""
        row = self._conn.execute(
            "SELECT payload_json FROM audit_event_payloads WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def get_all_for_events(self, event_ids: list[str]) -> dict[str, dict]:
        """Return a mapping of event_id → payload for the given IDs."""
        if not event_ids:
            return {}
        placeholders = ",".join("?" * len(event_ids))
        rows = self._conn.execute(
            f"SELECT event_id, payload_json FROM audit_event_payloads WHERE event_id IN ({placeholders})",
            event_ids,
        ).fetchall()
        return {r["event_id"]: json.loads(r["payload_json"]) for r in rows}


# ---------------------------------------------------------------------------
# Upload repository
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    asset_type: str
    original_filename: str
    safe_filename: str
    sha256: str
    size_bytes: int
    content_type: str | None
    storage_path: str
    format: str | None
    created_at: str


class UploadRepository:
    """CRUD for Upload records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(self, u: UploadRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO uploads
                (upload_id, asset_type, original_filename, safe_filename,
                 sha256, size_bytes, content_type, storage_path, format, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                u.upload_id,
                u.asset_type,
                u.original_filename,
                u.safe_filename,
                u.sha256,
                u.size_bytes,
                u.content_type,
                u.storage_path,
                u.format,
                u.created_at,
            ),
        )
        self._conn.commit()

    def get(self, upload_id: str) -> UploadRecord | None:
        row = self._conn.execute(
            "SELECT * FROM uploads WHERE upload_id=?", (upload_id,)
        ).fetchone()
        if row is None:
            return None
        return UploadRecord(
            upload_id=row["upload_id"],
            asset_type=row["asset_type"],
            original_filename=row["original_filename"],
            safe_filename=row["safe_filename"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            content_type=row["content_type"],
            storage_path=row["storage_path"],
            format=row["format"],
            created_at=row["created_at"],
        )

    def list_recent(self, limit: int = 50) -> list[UploadRecord]:
        rows = self._conn.execute(
            "SELECT * FROM uploads ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            UploadRecord(
                upload_id=r["upload_id"],
                asset_type=r["asset_type"],
                original_filename=r["original_filename"],
                safe_filename=r["safe_filename"],
                sha256=r["sha256"],
                size_bytes=r["size_bytes"],
                content_type=r["content_type"],
                storage_path=r["storage_path"],
                format=r["format"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

