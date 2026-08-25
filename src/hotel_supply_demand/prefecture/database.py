from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .models import MonthlyRecord, NationalOccupancyRecord

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE source_files (
  id INTEGER PRIMARY KEY, year INTEGER NOT NULL, release_type TEXT NOT NULL,
  url TEXT NOT NULL, filename TEXT NOT NULL, published_on TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, UNIQUE(year, release_type)
);
CREATE TABLE prefectures (code INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE monthly_prefecture_market (
  year INTEGER NOT NULL, month INTEGER NOT NULL, prefecture_code INTEGER NOT NULL,
  release_type TEXT NOT NULL, total_guests INTEGER, japanese_guests INTEGER,
  foreign_guests INTEGER, occupancy_rate REAL, facilities INTEGER,
  source_file_id INTEGER NOT NULL,
  PRIMARY KEY(year, month, prefecture_code, release_type),
  FOREIGN KEY(prefecture_code) REFERENCES prefectures(code),
  FOREIGN KEY(source_file_id) REFERENCES source_files(id)
);
CREATE TABLE national_occupancy (
  year INTEGER NOT NULL, month INTEGER NOT NULL, release_type TEXT NOT NULL,
  occupancy_rate REAL NOT NULL, source_file_id INTEGER NOT NULL,
  PRIMARY KEY(year, month, release_type),
  FOREIGN KEY(source_file_id) REFERENCES source_files(id)
);
CREATE TABLE municipality_source_files (
  id INTEGER PRIMARY KEY,
  year INTEGER NOT NULL, month INTEGER NOT NULL, release_type TEXT NOT NULL,
  stat_inf_id TEXT NOT NULL, url TEXT NOT NULL, filename TEXT NOT NULL,
  published_on TEXT NOT NULL, retrieved_at TEXT NOT NULL,
  sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  UNIQUE(year, month, release_type), UNIQUE(stat_inf_id)
);
CREATE TABLE municipalities (
  id INTEGER PRIMARY KEY, prefecture_code INTEGER NOT NULL,
  prefecture_name TEXT NOT NULL, municipality_name TEXT NOT NULL,
  UNIQUE(prefecture_code, municipality_name)
);
CREATE TABLE monthly_municipality_market (
  year INTEGER NOT NULL, month INTEGER NOT NULL, municipality_id INTEGER NOT NULL,
  room_size_class TEXT NOT NULL, release_type TEXT NOT NULL,
  total_guests INTEGER, japanese_guests INTEGER, foreign_guests INTEGER,
  occupied_rooms REAL, occupancy_rate REAL,
  population_facilities INTEGER, responding_facilities INTEGER,
  source_file_id INTEGER NOT NULL,
  PRIMARY KEY(year, month, municipality_id, room_size_class, release_type),
  FOREIGN KEY(municipality_id) REFERENCES municipalities(id),
  FOREIGN KEY(source_file_id) REFERENCES municipality_source_files(id),
  CHECK(room_size_class IN ('total', '1_to_9', '10_to_19', '20_plus')),
  CHECK(occupancy_rate IS NULL OR occupancy_rate BETWEEN 0 AND 200)
);
CREATE INDEX prefecture_market_period
  ON monthly_prefecture_market(prefecture_code, year, month);
CREATE INDEX municipality_market_period
  ON monthly_municipality_market(year, month, room_size_class);
CREATE VIEW latest_prefecture_market AS
WITH ranked AS (
  SELECT f.*,
    ROW_NUMBER() OVER (
      PARTITION BY year, month, prefecture_code
      ORDER BY CASE release_type WHEN 'final' THEN 1 WHEN 'second_preliminary' THEN 2 ELSE 3 END
    ) AS release_rank
  FROM monthly_prefecture_market AS f
)
SELECT year, month, prefecture_code, release_type, total_guests,
       japanese_guests, foreign_guests, occupancy_rate, facilities,
       source_file_id, p.name AS prefecture_name
FROM ranked
JOIN prefectures AS p ON p.code = ranked.prefecture_code
WHERE release_rank = 1;
CREATE VIEW annual_market AS
SELECT year, prefecture_code, prefecture_name, release_type,
       COUNT(*) AS months,
       SUM(total_guests) AS total_guests,
       SUM(japanese_guests) AS japanese_guests,
       SUM(foreign_guests) AS foreign_guests,
       AVG(occupancy_rate) AS average_occupancy_rate,
       AVG(facilities) AS average_facilities
FROM latest_prefecture_market
GROUP BY year, prefecture_code, prefecture_name, release_type;
"""


def migrate_legacy_prefecture_market(connection: sqlite3.Connection) -> bool:
    """Merge the legacy demand/supply tables in an existing unified database."""
    names = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "monthly_prefecture_market" in names:
        return False
    legacy = {"monthly_demand", "monthly_supply"}
    if not legacy.issubset(names):
        return False

    connection.execute("BEGIN IMMEDIATE")
    try:
        for view in (
            "annual_market",
            "monthly_market",
            "latest_monthly_demand",
            "latest_monthly_supply",
        ):
            connection.execute(f"DROP VIEW IF EXISTS {view}")
        connection.execute(
            """CREATE TABLE monthly_prefecture_market (
                 year INTEGER NOT NULL, month INTEGER NOT NULL,
                 prefecture_code INTEGER NOT NULL, release_type TEXT NOT NULL,
                 total_guests INTEGER, japanese_guests INTEGER,
                 foreign_guests INTEGER, occupancy_rate REAL, facilities INTEGER,
                 source_file_id INTEGER NOT NULL,
                 PRIMARY KEY(year, month, prefecture_code, release_type),
                 FOREIGN KEY(prefecture_code) REFERENCES prefectures(code),
                 FOREIGN KEY(source_file_id) REFERENCES source_files(id)
               )"""
        )
        connection.execute(
            """INSERT INTO monthly_prefecture_market
               SELECT d.year,d.month,d.prefecture_code,d.release_type,
                      d.total_guests,d.japanese_guests,d.foreign_guests,
                      d.occupancy_rate,s.facilities,d.source_file_id
               FROM monthly_demand AS d
               JOIN monthly_supply AS s
                 ON s.year=d.year AND s.month=d.month
                AND s.prefecture_code=d.prefecture_code
                AND s.release_type=d.release_type"""
        )
        demand_count = connection.execute("SELECT count(*) FROM monthly_demand").fetchone()[0]
        merged_count = connection.execute(
            "SELECT count(*) FROM monthly_prefecture_market"
        ).fetchone()[0]
        if merged_count != demand_count:
            raise ValueError("legacy prefecture demand/supply keys do not match")
        connection.execute("DROP TABLE monthly_demand")
        connection.execute("DROP TABLE monthly_supply")
        connection.execute(
            """CREATE INDEX prefecture_market_period
               ON monthly_prefecture_market(prefecture_code, year, month)"""
        )
        connection.execute(
            """CREATE VIEW latest_prefecture_market AS
               WITH ranked AS (
                 SELECT f.*,
                   ROW_NUMBER() OVER (
                     PARTITION BY year, month, prefecture_code
                     ORDER BY CASE release_type
                       WHEN 'final' THEN 1
                       WHEN 'second_preliminary' THEN 2 ELSE 3 END
                   ) AS release_rank
                 FROM monthly_prefecture_market AS f
               )
               SELECT year,month,prefecture_code,release_type,total_guests,
                      japanese_guests,foreign_guests,occupancy_rate,facilities,
                      source_file_id,p.name AS prefecture_name
               FROM ranked
               JOIN prefectures AS p ON p.code=ranked.prefecture_code
               WHERE release_rank=1"""
        )
        connection.execute(
            """CREATE VIEW annual_market AS
               SELECT year,prefecture_code,prefecture_name,release_type,
                      COUNT(*) AS months,SUM(total_guests) AS total_guests,
                      SUM(japanese_guests) AS japanese_guests,
                      SUM(foreign_guests) AS foreign_guests,
                      AVG(occupancy_rate) AS average_occupancy_rate,
                      AVG(facilities) AS average_facilities
               FROM latest_prefecture_market
               GROUP BY year,prefecture_code,prefecture_name,release_type"""
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return True


def _preserve_municipality_data(connection: sqlite3.Connection, previous: Path) -> None:
    if not previous.exists():
        return
    connection.execute("ATTACH DATABASE ? AS previous", (str(previous),))
    try:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM previous.sqlite_master WHERE type='table'"
            )
        }
        required = {
            "municipality_source_files",
            "municipalities",
            "monthly_municipality_market",
        }
        if required.issubset(names):
            connection.execute(
                "INSERT INTO municipality_source_files SELECT * FROM previous.municipality_source_files"
            )
            connection.execute("INSERT INTO municipalities SELECT * FROM previous.municipalities")
            connection.execute(
                "INSERT INTO monthly_municipality_market SELECT * FROM previous.monthly_municipality_market"
            )
        connection.commit()
    finally:
        connection.execute("DETACH DATABASE previous")


def build_database(
    path: Path,
    records: list[MonthlyRecord],
    manifest_entries: list[dict],
    national_occupancy: list[NationalOccupancyRecord] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript(SCHEMA)
        source_ids = {}
        for entry in manifest_entries:
            cursor = connection.execute(
                "INSERT INTO source_files(year,release_type,url,filename,published_on,retrieved_at,sha256,size_bytes) VALUES(?,?,?,?,?,?,?,?)",
                (
                    entry["year"],
                    entry["release_type"],
                    entry["url"],
                    entry["filename"],
                    entry["published_on"],
                    entry["retrieved_at"],
                    entry["sha256"],
                    entry["size_bytes"],
                ),
            )
            source_ids[(entry["year"], entry["release_type"])] = cursor.lastrowid
        connection.executemany(
            "INSERT INTO prefectures(code,name) VALUES(?,?)",
            sorted({(r.prefecture_code, r.prefecture_name) for r in records}),
        )
        connection.executemany(
            "INSERT INTO monthly_prefecture_market VALUES(?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    r.year,
                    r.month,
                    r.prefecture_code,
                    r.release_type,
                    r.total_guests,
                    r.japanese_guests,
                    r.foreign_guests,
                    r.occupancy_rate,
                    r.facilities,
                    source_ids[(r.year, r.release_type)],
                )
                for r in records
            ],
        )
        connection.executemany(
            "INSERT INTO national_occupancy VALUES(?,?,?,?,?)",
            [
                (
                    r.year,
                    r.month,
                    r.release_type,
                    r.occupancy_rate,
                    source_ids[(r.year, r.release_type)],
                )
                for r in national_occupancy or []
            ],
        )
        _preserve_municipality_data(connection, path)
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, path)
