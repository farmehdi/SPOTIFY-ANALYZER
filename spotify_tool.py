from __future__ import annotations

import json
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt
import typer
from dateutil import parser as dtparser
from dateutil import tz

app = typer.Typer()

PARIS = tz.gettz("Europe/Paris")
UTC = tz.UTC


# ---------- Utils ----------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS imports (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          imported_at TEXT NOT NULL,
          export_root TEXT NOT NULL,
          file_path TEXT NOT NULL,
          file_hash TEXT NOT NULL UNIQUE,
          rows_inserted INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          played_at_utc TEXT NOT NULL,
          played_at_local TEXT NOT NULL,
          track_name TEXT,
          artist_name TEXT,
          album_name TEXT,
          ms_played INTEGER NOT NULL,
          platform TEXT,
          content_type TEXT,
          source_file_hash TEXT NOT NULL,
          raw_source TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_played_at_utc ON events(played_at_utc);
        CREATE INDEX IF NOT EXISTS idx_events_artist ON events(artist_name);
        CREATE INDEX IF NOT EXISTS idx_events_source_hash ON events(source_file_hash);
        """
    )
    conn.commit()


def find_candidate_files(export_root: Path) -> list[Path]:
    patterns = [
        "StreamingHistory*.json",
        "*StreamingHistory*.json",
        "endsong*.json",
        "*endsong*.json",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(export_root.rglob(pat))

    # unique
    seen = set()
    out = []
    for f in files:
        if f.is_file():
            rp = str(f.resolve())
            if rp not in seen:
                seen.add(rp)
                out.append(f)
    return out


def already_imported(conn: sqlite3.Connection, file_hash: str) -> bool:
    return conn.execute("SELECT 1 FROM imports WHERE file_hash=? LIMIT 1", (file_hash,)).fetchone() is not None


def to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse_event(obj: dict) -> Optional[tuple]:
    """
    Retourne une ligne prête à insérer dans DB, ou None si format inconnu.
    Supporte:
    - endTime/msPlayed (ancien)
    - ts/ms_played + master_metadata_* (historique étendu)
    """
    # ancien format
    if "endTime" in obj and "msPlayed" in obj:
        end_time = dtparser.parse(obj["endTime"])
        if end_time.tzinfo is None:
            end_local = end_time.replace(tzinfo=PARIS)
        else:
            end_local = end_time.astimezone(PARIS)
        end_utc = end_local.astimezone(UTC)

        ms = int(obj.get("msPlayed") or 0)
        if ms <= 0:
            return None

        return (
            to_iso(end_utc),
            to_iso(end_local),
            obj.get("trackName"),
            obj.get("artistName"),
            None,
            ms,
            None,
            "music",
            "streaming_history_old",
        )

    # format ts (souvent dans exports récents)
    if "ts" in obj and ("ms_played" in obj or "msPlayed" in obj):
        ts_dt = dtparser.isoparse(obj["ts"])
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=UTC)
        ts_utc = ts_dt.astimezone(UTC)
        ts_local = ts_utc.astimezone(PARIS)

        ms = int(obj.get("ms_played") or obj.get("msPlayed") or 0)
        if ms <= 0:
            return None

        # musique
        track = obj.get("master_metadata_track_name") or obj.get("trackName")
        artist = obj.get("master_metadata_album_artist_name") or obj.get("artistName")
        album = obj.get("master_metadata_album_album_name") or obj.get("albumName")

        # podcast fallback
        if not track:
            track = obj.get("episode_name") or obj.get("episode_title")
        if not artist:
            artist = obj.get("episode_show_name") or obj.get("show_name")

        content_type = "podcast" if (obj.get("spotify_episode_uri") or obj.get("episode_name") or obj.get("episode_show_name")) else "music"

        return (
            to_iso(ts_utc),
            to_iso(ts_local),
            track,
            artist,
            album,
            ms,
            obj.get("platform"),
            content_type,
            "streaming_history_new",
        )

    return None


def ingest_export(conn: sqlite3.Connection, export_root: Path) -> dict:
    export_root = export_root.resolve()
    files = find_candidate_files(export_root)

    new_files = 0
    skipped = 0
    rows_total = 0

    for f in files:
        h = sha256_file(f)
        if already_imported(conn, h):
            skipped += 1
            continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            data = []

        rows = []
        if isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    e = parse_event(obj)
                    if e:
                        rows.append(e)

        if rows:
            conn.executemany(
                """
                INSERT INTO events(
                  played_at_utc, played_at_local,
                  track_name, artist_name, album_name,
                  ms_played, platform, content_type,
                  source_file_hash, raw_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], h, r[8]) for r in rows],
            )

        imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO imports(imported_at, export_root, file_path, file_hash, rows_inserted)
            VALUES (?, ?, ?, ?, ?)
            """,
            (imported_at, str(export_root), str(f), h, len(rows)),
        )
        conn.commit()

        new_files += 1
        rows_total += len(rows)

    return {
        "export_root": str(export_root),
        "files_found": len(files),
        "new_files_imported": new_files,
        "files_skipped": skipped,
        "rows_inserted": rows_total,
    }


def load_df(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT played_at_local, track_name, artist_name, album_name, ms_played, platform, content_type
        FROM events
        """,
        conn,
    )
    if df.empty:
        return df

    # Fix fuseaux (+01/+02) : on force UTC puis on convertit en Europe/Paris
    df["played_at_local"] = pd.to_datetime(df["played_at_local"], utc=True, errors="coerce")
    df = df.dropna(subset=["played_at_local"]).copy()
    df["played_at_local"] = df["played_at_local"].dt.tz_convert("Europe/Paris").dt.tz_localize(None)

    df["minutes"] = df["ms_played"] / 60000.0
    df["hour"] = df["played_at_local"].dt.hour
    df["weekday"] = df["played_at_local"].dt.day_name()
    df["month"] = df["played_at_local"].dt.to_period("M").astype(str)
    df["date"] = df["played_at_local"].dt.date
    return df



def save_bar(series: pd.Series, out: Path, title: str, xlabel: str, ylabel: str) -> None:
    fig = plt.figure()
    ax = fig.add_subplot(111)
    series.plot(kind="bar", ax=ax)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


def save_line(series: pd.Series, out: Path, title: str, xlabel: str, ylabel: str) -> None:
    fig = plt.figure()
    ax = fig.add_subplot(111)
    series.plot(kind="line", marker="o", ax=ax)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)


# ---------- CLI ----------
@app.command()
def init(db: Path = Path("spotify.sqlite")):
    conn = connect(db)
    init_db(conn)
    conn.close()
    print(f"DB initialisée: {db}")


@app.command("import-export")
def import_export(export_root: Path, db: Path = Path("spotify.sqlite")):
    conn = connect(db)
    init_db(conn)
    summary = ingest_export(conn, export_root)
    conn.close()
    print("Import terminé:")
    for k, v in summary.items():
        print(f"- {k}: {v}")


@app.command()
def stats(db: Path = Path("spotify.sqlite")):
    conn = connect(db)
    init_db(conn)
    events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    imports = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]
    conn.close()
    print(f"events: {events}")
    print(f"imports: {imports}")


@app.command()
def report(out_dir: Path = Path("report"), db: Path = Path("spotify.sqlite")):
    conn = connect(db)
    init_db(conn)
    df = load_df(conn)
    conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "report.md"

    if df.empty:
        md.write_text("# Rapport Spotify RGPD\n\nAucune donnée.\n", encoding="utf-8")
        print(f"Rapport généré: {md}")
        return

    p_hour = out_dir / "listening_by_hour.png"
    p_day = out_dir / "listening_by_weekday.png"
    p_top = out_dir / "top_artists.png"

    by_hour = df.groupby("hour")["minutes"].sum().sort_index()
    by_day = df.groupby("weekday")["minutes"].sum()
    top_art = df.dropna(subset=["artist_name"]).groupby("artist_name")["minutes"].sum().sort_values(ascending=False).head(15)

    save_bar(by_hour, p_hour, "Écoute par heure", "Heure", "Minutes")
    save_bar(by_day, p_day, "Écoute par jour", "Jour", "Minutes")
    save_bar(top_art, p_top, "Top artistes (minutes)", "Artiste", "Minutes")

    total_minutes = float(df["minutes"].sum())
    days = int(df["date"].nunique())
    avg = total_minutes / days if days else 0.0

    md.write_text(
        f"""# Rapport Spotify RGPD

## Résumé
- Minutes totales : **{total_minutes:,.0f}**
- Jours couverts : **{days}**
- Moyenne minutes/jour : **{avg:,.1f}**

## Graphiques
### Écoute par heure
![](listening_by_hour.png)

### Écoute par jour
![](listening_by_weekday.png)

### Top artistes
![](top_artists.png)
""",
        encoding="utf-8",
    )
    print(f"Rapport généré: {md}")


if __name__ == "__main__":
    app()
