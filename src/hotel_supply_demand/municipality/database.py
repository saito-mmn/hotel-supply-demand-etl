"""SQLite persistence for municipality-level monthly statistics."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import MunicipalityMonthlyRecord
from .sources import MunicipalitySource
from .validation import validate_municipality_records


MUNICIPALITY_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS municipality_source_files (
  id INTEGER PRIMARY KEY,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  release_type TEXT NOT NULL,
  stat_inf_id TEXT NOT NULL,
  url TEXT NOT NULL,
  filename TEXT NOT NULL,
  published_on TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  UNIQUE(year, month, release_type),
  UNIQUE(stat_inf_id)
);
CREATE TABLE IF NOT EXISTS municipalities (
  id INTEGER PRIMARY KEY,
  prefecture_code INTEGER NOT NULL,
  prefecture_name TEXT NOT NULL,
  municipality_name TEXT NOT NULL,
  UNIQUE(prefecture_code, municipality_name)
);
CREATE TABLE IF NOT EXISTS monthly_municipality_market (
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  municipality_id INTEGER NOT NULL,
  room_size_class TEXT NOT NULL,
  release_type TEXT NOT NULL,
  total_guests INTEGER,
  japanese_guests INTEGER,
  foreign_guests INTEGER,
  occupied_rooms REAL,
  occupancy_rate REAL,
  population_facilities INTEGER,
  responding_facilities INTEGER,
  source_file_id INTEGER NOT NULL,
  PRIMARY KEY(year, month, municipality_id, room_size_class, release_type),
  FOREIGN KEY(municipality_id) REFERENCES municipalities(id),
  FOREIGN KEY(source_file_id) REFERENCES municipality_source_files(id),
  CHECK(room_size_class IN ('total', '1_to_9', '10_to_19', '20_plus')),
  CHECK(occupancy_rate IS NULL OR occupancy_rate BETWEEN 0 AND 200)
);
CREATE INDEX IF NOT EXISTS municipality_market_period
  ON monthly_municipality_market(year, month, room_size_class);
"""


def load_municipality_records(
    database: Path,
    records: list[MunicipalityMonthlyRecord],
    source: MunicipalitySource,
    provenance: dict,
) -> dict:
    """Validate and replace one municipality month in a single transaction."""
    quality = validate_municipality_records(records)
    if (quality["year"], quality["month"], quality["release_type"]) != (
        source.year,
        source.month,
        source.release_type,
    ):
        raise ValueError("source period does not match municipality records")
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(MUNICIPALITY_SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO municipality_source_files(
                 year,month,release_type,stat_inf_id,url,filename,published_on,
                 retrieved_at,sha256,size_bytes
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(year,month,release_type) DO UPDATE SET
                 stat_inf_id=excluded.stat_inf_id,
                 url=excluded.url,
                 filename=excluded.filename,
                 published_on=excluded.published_on,
                 retrieved_at=excluded.retrieved_at,
                 sha256=excluded.sha256,
                 size_bytes=excluded.size_bytes""",
            (
                source.year,
                source.month,
                source.release_type,
                source.stat_inf_id,
                source.url,
                source.filename,
                source.published_on,
                provenance["retrieved_at"],
                provenance["sha256"],
                provenance["size_bytes"],
            ),
        )
        source_id = connection.execute(
            """SELECT id FROM municipality_source_files
               WHERE year=? AND month=? AND release_type=?""",
            (source.year, source.month, source.release_type),
        ).fetchone()[0]
        municipalities = sorted(
            {
                (record.prefecture_code, record.prefecture_name, record.municipality_name)
                for record in records
            }
        )
        connection.executemany(
            """INSERT INTO municipalities(prefecture_code,prefecture_name,municipality_name)
               VALUES(?,?,?)
               ON CONFLICT(prefecture_code,municipality_name) DO UPDATE SET
                 prefecture_name=excluded.prefecture_name""",
            municipalities,
        )
        municipality_ids = {
            (row[1], row[2]): row[0]
            for row in connection.execute(
                "SELECT id,prefecture_code,municipality_name FROM municipalities"
            )
        }
        connection.execute(
            """DELETE FROM monthly_municipality_market
               WHERE year=? AND month=? AND release_type=?""",
            (source.year, source.month, source.release_type),
        )
        connection.executemany(
            """INSERT INTO monthly_municipality_market VALUES(
                 ?,?,?,?,?,?,?,?,?,?,?,?,?
               )""",
            [
                (
                    record.year,
                    record.month,
                    municipality_ids[(record.prefecture_code, record.municipality_name)],
                    record.room_size_class,
                    record.release_type,
                    record.total_guests,
                    record.japanese_guests,
                    record.foreign_guests,
                    record.occupied_rooms,
                    record.occupancy_rate,
                    record.population_facilities,
                    record.responding_facilities,
                    source_id,
                )
                for record in records
            ],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {**quality, "database": str(database), "source_file_id": source_id}
