"""Database helpers for the Discord crypto bot.

Uses PostgreSQL when DATABASE_URL is set, otherwise SQLite.  The public
functions stay small and synchronous because the existing bot is already built
around synchronous DB calls.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Iterable, List, Tuple, Optional

try:  # Optional; enabled on Railway by setting DATABASE_URL.
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - psycopg is optional in local mode
    psycopg = None
    dict_row = None

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
USE_POSTGRES = bool(DATABASE_URL and str(DATABASE_URL).startswith(("postgres://", "postgresql://")) and psycopg)

_DEFAULT_SQLITE_PATH = os.environ.get("SQLITE_DB_PATH") or os.environ.get("BOT_DB_PATH")
if not _DEFAULT_SQLITE_PATH:
    # Railway Volume friendly fallback. If /app/data exists, use it. Otherwise
    # keep the DB next to this file for local runs.
    volume_path = Path("/app/data")
    _DEFAULT_SQLITE_PATH = str(volume_path / "bot_data.db") if volume_path.exists() else str(Path(__file__).with_name("bot_data.db"))
DB_PATH = Path(_DEFAULT_SQLITE_PATH)


def backend_name() -> str:
    return "postgres" if USE_POSTGRES else "sqlite"


def _now_ts() -> int:
    return int(time.time())


def _today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _json(data: Any) -> str:
    try:
        return json.dumps(data if data is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return "{}"


def _loads(value: Any) -> Any:
    if value in (None, ""):
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def _convert_sql(sql: str) -> str:
    """Convert SQLite qmark placeholders to psycopg placeholders."""
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


@contextmanager
def get_conn():
    if USE_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _execute(conn, sql: str, params: Iterable[Any] = ()):  # returns cursor
    cur = conn.cursor()
    cur.execute(_convert_sql(sql), tuple(params))
    return cur


def _fetchone(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with get_conn() as conn:
        cur = _execute(conn, sql, params)
        row = cur.fetchone()
        return dict(row) if row is not None else None


def _fetchall(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with get_conn() as conn:
        cur = _execute(conn, sql, params)
        return [dict(r) for r in cur.fetchall()]


def _insert_and_id(sql: str, params: Iterable[Any] = ()) -> int:
    with get_conn() as conn:
        cur = _execute(conn, sql, params)
        if USE_POSTGRES:
            row = cur.fetchone()
            return int((row or {}).get("id") or 0)
        return int(cur.lastrowid or 0)


def _exec(sql: str, params: Iterable[Any] = ()) -> None:
    with get_conn() as conn:
        _execute(conn, sql, params)


def _ddl(sqlite_sql: str, pg_sql: str | None = None) -> None:
    with get_conn() as conn:
        _execute(conn, pg_sql if (USE_POSTGRES and pg_sql) else sqlite_sql)


def init_db():
    # Existing user-facing tables ------------------------------------------------
    _ddl('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        coin TEXT NOT NULL,
        target REAL NOT NULL,
        direction TEXT NOT NULL,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS alerts (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        coin TEXT NOT NULL,
        target DOUBLE PRECISION NOT NULL,
        direction TEXT NOT NULL,
        ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        price REAL,
        rsi REAL,
        confidence TEXT,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS signal_history (
        id SERIAL PRIMARY KEY,
        symbol TEXT,
        direction TEXT,
        price DOUBLE PRECISION,
        rsi DOUBLE PRECISION,
        confidence TEXT,
        ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS portfolios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        symbol TEXT,
        entry_price REAL,
        size REAL,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS portfolios (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        symbol TEXT,
        entry_price DOUBLE PRECISION,
        size DOUBLE PRECISION,
        ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
    )
    ''')
    init_closed_table()

    # Operational reliability tables -------------------------------------------
    _ddl('''
    CREATE TABLE IF NOT EXISTS ops_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        payload_json TEXT,
        created_at INTEGER NOT NULL
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS ops_events (
        id SERIAL PRIMARY KEY,
        event TEXT NOT NULL,
        level TEXT DEFAULT 'info',
        payload_json TEXT,
        created_at BIGINT NOT NULL
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS signals_sent (
        signal_id TEXT PRIMARY KEY,
        tier TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry REAL,
        score INTEGER,
        rr REAL,
        confidence TEXT,
        status TEXT DEFAULT 'reserved',
        channel_id INTEGER,
        message_id INTEGER,
        error TEXT,
        meta_json TEXT,
        reserved_at INTEGER NOT NULL,
        sent_at INTEGER
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS signals_sent (
        signal_id TEXT PRIMARY KEY,
        tier TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        entry DOUBLE PRECISION,
        score INTEGER,
        rr DOUBLE PRECISION,
        confidence TEXT,
        status TEXT DEFAULT 'reserved',
        channel_id BIGINT,
        message_id BIGINT,
        error TEXT,
        meta_json TEXT,
        reserved_at BIGINT NOT NULL,
        sent_at BIGINT
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS blocked_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        side TEXT,
        tier TEXT,
        score INTEGER,
        reason TEXT,
        rr REAL,
        meta_json TEXT,
        created_at INTEGER NOT NULL
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS blocked_signals (
        id SERIAL PRIMARY KEY,
        symbol TEXT,
        side TEXT,
        tier TEXT,
        score INTEGER,
        reason TEXT,
        rr DOUBLE PRECISION,
        meta_json TEXT,
        created_at BIGINT NOT NULL
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS discord_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id TEXT,
        tier TEXT,
        channel_id INTEGER,
        attempt INTEGER,
        status TEXT,
        message_id INTEGER,
        error TEXT,
        created_at INTEGER NOT NULL
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS discord_attempts (
        id SERIAL PRIMARY KEY,
        signal_id TEXT,
        tier TEXT,
        channel_id BIGINT,
        attempt INTEGER,
        status TEXT,
        message_id BIGINT,
        error TEXT,
        created_at BIGINT NOT NULL
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS bot_state (
        key TEXT PRIMARY KEY,
        value_json TEXT,
        updated_at INTEGER NOT NULL
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS bot_state (
        key TEXT PRIMARY KEY,
        value_json TEXT,
        updated_at BIGINT NOT NULL
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS daily_counters (
        day TEXT NOT NULL,
        tier TEXT NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day, tier)
    )
    ''')
    _ddl('''
    CREATE TABLE IF NOT EXISTS signal_results (
        signal_id TEXT PRIMARY KEY,
        tier TEXT,
        symbol TEXT,
        side TEXT,
        entry REAL,
        sl REAL,
        tp1 REAL,
        tp2 REAL,
        tp3 REAL,
        remaining_pct REAL DEFAULT 100,
        realized_pnl_pct REAL DEFAULT 0,
        fees_pct REAL DEFAULT 0,
        slippage_pct REAL DEFAULT 0,
        status TEXT DEFAULT 'OPEN',
        hit_json TEXT,
        opened_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        closed_at INTEGER,
        meta_json TEXT
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS signal_results (
        signal_id TEXT PRIMARY KEY,
        tier TEXT,
        symbol TEXT,
        side TEXT,
        entry DOUBLE PRECISION,
        sl DOUBLE PRECISION,
        tp1 DOUBLE PRECISION,
        tp2 DOUBLE PRECISION,
        tp3 DOUBLE PRECISION,
        remaining_pct DOUBLE PRECISION DEFAULT 100,
        realized_pnl_pct DOUBLE PRECISION DEFAULT 0,
        fees_pct DOUBLE PRECISION DEFAULT 0,
        slippage_pct DOUBLE PRECISION DEFAULT 0,
        status TEXT DEFAULT 'OPEN',
        hit_json TEXT,
        opened_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        closed_at BIGINT,
        meta_json TEXT
    )
    ''')
    _ddl("CREATE INDEX IF NOT EXISTS idx_signals_recent ON signals_sent(symbol, side, tier, status, sent_at)")
    _ddl("CREATE INDEX IF NOT EXISTS idx_blocked_recent ON blocked_signals(symbol, created_at)")
    _ddl("CREATE INDEX IF NOT EXISTS idx_attempts_signal ON discord_attempts(signal_id, created_at)")
    _ddl("CREATE INDEX IF NOT EXISTS idx_results_status ON signal_results(status, opened_at)")
    log_event("db_ready", {"backend": backend_name(), "sqlite_path": str(DB_PATH) if not USE_POSTGRES else None})


# Alerts ----------------------------------------------------------------------
def add_alert(user_id: int, coin: str, target: float, direction: str) -> int:
    if USE_POSTGRES:
        return _insert_and_id('INSERT INTO alerts (user_id, coin, target, direction) VALUES (?,?,?,?) RETURNING id', (user_id, coin, target, direction))
    return _insert_and_id('INSERT INTO alerts (user_id, coin, target, direction) VALUES (?,?,?,?)', (user_id, coin, target, direction))


def get_alerts(user_id: int) -> List[Tuple[int, str, float, str, int]]:
    rows = _fetchall('SELECT id, coin, target, direction, ts FROM alerts WHERE user_id=? ORDER BY ts DESC', (user_id,))
    return [(r['id'], r['coin'], r['target'], r['direction'], r['ts']) for r in rows]


def remove_alert(alert_id: int):
    _exec('DELETE FROM alerts WHERE id=?', (alert_id,))


# Signal history --------------------------------------------------------------
def save_signal(symbol: str, direction: str, price: float, rsi: float, confidence: str):
    _exec('INSERT INTO signal_history (symbol, direction, price, rsi, confidence) VALUES (?,?,?,?,?)', (symbol, direction, price, rsi, confidence))


def get_recent_signals(limit: int = 50):
    rows = _fetchall('SELECT symbol,direction,price,rsi,confidence,ts FROM signal_history ORDER BY ts DESC LIMIT ?', (int(limit),))
    return rows


# Portfolios ------------------------------------------------------------------
def add_portfolio_entry(user_id: int, symbol: str, entry_price: float, size: float):
    _exec('INSERT INTO portfolios (user_id, symbol, entry_price, size) VALUES (?,?,?,?)', (user_id, symbol, entry_price, size))


def get_portfolio(user_id: int):
    return _fetchall('SELECT id,symbol,entry_price,size,ts FROM portfolios WHERE user_id=?', (user_id,))


def init_closed_table():
    _ddl('''
    CREATE TABLE IF NOT EXISTS closed_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        symbol TEXT,
        entry_price REAL,
        exit_price REAL,
        size REAL,
        pnl REAL,
        pnl_pct REAL,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''', '''
    CREATE TABLE IF NOT EXISTS closed_positions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        symbol TEXT,
        entry_price DOUBLE PRECISION,
        exit_price DOUBLE PRECISION,
        size DOUBLE PRECISION,
        pnl DOUBLE PRECISION,
        pnl_pct DOUBLE PRECISION,
        ts BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT
    )
    ''')


def close_portfolio_entry(entry_id: int, exit_price: float) -> Optional[dict]:
    with get_conn() as conn:
        cur = _execute(conn, 'SELECT id,user_id,symbol,entry_price,size,ts FROM portfolios WHERE id=?', (entry_id,))
        row = cur.fetchone()
        if not row:
            return None
        entry = dict(row)
        entry_price = float(entry['entry_price'])
        size = float(entry['size'])
        pnl = (float(exit_price) - entry_price) * size
        pnl_pct = ((float(exit_price) - entry_price) / entry_price * 100) if entry_price else 0.0
        _execute(conn, 'INSERT INTO closed_positions (user_id,symbol,entry_price,exit_price,size,pnl,pnl_pct) VALUES (?,?,?,?,?,?,?)',
                 (entry['user_id'], entry['symbol'], entry_price, float(exit_price), size, pnl, pnl_pct))
        _execute(conn, 'DELETE FROM portfolios WHERE id=?', (entry_id,))
    return {
        'user_id': entry['user_id'], 'symbol': entry['symbol'], 'entry_price': entry_price,
        'exit_price': float(exit_price), 'size': size, 'pnl': pnl, 'pnl_pct': pnl_pct
    }


def get_closed_positions(user_id: int):
    return _fetchall('SELECT id,symbol,entry_price,exit_price,size,pnl,pnl_pct,ts FROM closed_positions WHERE user_id=? ORDER BY ts DESC', (user_id,))


# Operational logging ---------------------------------------------------------
def log_event(event: str, payload: Any = None, level: str = "info") -> None:
    try:
        _exec('INSERT INTO ops_events (event, level, payload_json, created_at) VALUES (?,?,?,?)',
              (str(event), str(level or "info"), _json(payload), _now_ts()))
    except Exception:
        # Logging must never crash the bot.
        pass


def set_state(key: str, value: Any) -> None:
    ts = _now_ts()
    if USE_POSTGRES:
        sql = '''INSERT INTO bot_state (key,value_json,updated_at) VALUES (?,?,?)
                 ON CONFLICT (key) DO UPDATE SET value_json=EXCLUDED.value_json, updated_at=EXCLUDED.updated_at'''
    else:
        sql = '''INSERT INTO bot_state (key,value_json,updated_at) VALUES (?,?,?)
                 ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at'''
    _exec(sql, (key, _json(value), ts))


def get_state(key: str, default: Any = None) -> Any:
    row = _fetchone('SELECT value_json FROM bot_state WHERE key=?', (key,))
    return _loads(row.get('value_json')) if row else default


def recent_events(limit: int = 10) -> list[dict]:
    rows = _fetchall('SELECT event, level, payload_json, created_at FROM ops_events ORDER BY id DESC LIMIT ?', (int(limit),))
    for r in rows:
        r['payload'] = _loads(r.pop('payload_json', None))
    return rows


# Signal reserve / dedupe -----------------------------------------------------
def build_signal_id(tier: str, symbol: str, side: str, entry: float | None = None, *, bucket_minutes: int | None = None) -> str:
    bucket_minutes = int(bucket_minutes or os.environ.get("SIGNAL_DEDUPE_BUCKET_MINUTES", "60") or 60)
    bucket_seconds = max(60, bucket_minutes * 60)
    bucket = _now_ts() // bucket_seconds * bucket_seconds
    return f"{tier.lower()}:{symbol.upper()}:{side.upper()}:{bucket}"


def has_recent_signal(symbol: str, side: str, tier: str, cooldown_hours: float) -> bool:
    cutoff = _now_ts() - int(float(cooldown_hours) * 3600)
    row = _fetchone('''SELECT signal_id FROM signals_sent
                       WHERE symbol=? AND side=? AND tier=? AND status='sent' AND sent_at>=?
                       ORDER BY sent_at DESC LIMIT 1''',
                    (symbol.upper(), side.upper(), tier.lower(), cutoff))
    return row is not None


def reserve_signal(signal_id: str, tier: str, symbol: str, side: str, entry: float, score: int | None = None,
                   rr: float | None = None, confidence: str | None = None, meta: Any = None) -> bool:
    try:
        if USE_POSTGRES:
            sql = '''INSERT INTO signals_sent
                     (signal_id,tier,symbol,side,entry,score,rr,confidence,status,meta_json,reserved_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT (signal_id) DO NOTHING'''
            with get_conn() as conn:
                cur = _execute(conn, sql, (signal_id, tier, symbol, side, float(entry or 0), score, rr, confidence, 'reserved', _json(meta), _now_ts()))
                return cur.rowcount == 1
        else:
            with get_conn() as conn:
                cur = _execute(conn, '''INSERT OR IGNORE INTO signals_sent
                     (signal_id,tier,symbol,side,entry,score,rr,confidence,status,meta_json,reserved_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                     (signal_id, tier, symbol, side, float(entry or 0), score, rr, confidence, 'reserved', _json(meta), _now_ts()))
                return cur.rowcount == 1
    except Exception as exc:
        log_event("reserve_signal_error", {"signal_id": signal_id, "error": str(exc)}, level="error")
        return False


def mark_signal_sent(signal_id: str, channel_id: int | None = None, message_id: int | None = None, meta: Any = None) -> None:
    existing = _fetchone('SELECT meta_json FROM signals_sent WHERE signal_id=?', (signal_id,)) or {}
    merged_meta = _loads(existing.get('meta_json'))
    if isinstance(meta, dict):
        merged_meta.update(meta)
    _exec('''UPDATE signals_sent SET status='sent', channel_id=?, message_id=?, sent_at=?, meta_json=? WHERE signal_id=?''',
          (channel_id, message_id, _now_ts(), _json(merged_meta), signal_id))


def mark_signal_failed(signal_id: str, error: str | None = None) -> None:
    _exec('UPDATE signals_sent SET status=?, error=? WHERE signal_id=?', ('failed', str(error or '')[:900], signal_id))


def record_blocked_signal(symbol: str, side: str | None, tier: str, score: int | None, reason: str, rr: float | None = None, meta: Any = None) -> None:
    try:
        _exec('INSERT INTO blocked_signals (symbol, side, tier, score, reason, rr, meta_json, created_at) VALUES (?,?,?,?,?,?,?,?)',
              ((symbol or '').upper(), (side or '').upper(), tier.lower(), score, str(reason)[:900], rr, _json(meta), _now_ts()))
    except Exception as exc:
        log_event("blocked_signal_log_error", {"symbol": symbol, "error": str(exc)}, level="error")


def last_blocked(limit: int = 10, symbol: str | None = None) -> list[dict]:
    if symbol:
        rows = _fetchall('SELECT * FROM blocked_signals WHERE symbol=? ORDER BY id DESC LIMIT ?', (symbol.upper(), int(limit)))
    else:
        rows = _fetchall('SELECT * FROM blocked_signals ORDER BY id DESC LIMIT ?', (int(limit),))
    for r in rows:
        r['meta'] = _loads(r.pop('meta_json', None))
    return rows


def recent_sent(limit: int = 10, symbol: str | None = None) -> list[dict]:
    if symbol:
        rows = _fetchall('SELECT * FROM signals_sent WHERE symbol=? ORDER BY COALESCE(sent_at,reserved_at) DESC LIMIT ?', (symbol.upper(), int(limit)))
    else:
        rows = _fetchall('SELECT * FROM signals_sent ORDER BY COALESCE(sent_at,reserved_at) DESC LIMIT ?', (int(limit),))
    for r in rows:
        r['meta'] = _loads(r.pop('meta_json', None))
    return rows


def record_discord_attempt(signal_id: str | None, tier: str | None, channel_id: int | None, attempt: int, status: str,
                           message_id: int | None = None, error: str | None = None) -> None:
    try:
        _exec('INSERT INTO discord_attempts (signal_id,tier,channel_id,attempt,status,message_id,error,created_at) VALUES (?,?,?,?,?,?,?,?)',
              (signal_id, tier, channel_id, int(attempt), status, message_id, str(error or '')[:900], _now_ts()))
    except Exception:
        pass


# Daily counters --------------------------------------------------------------
def get_daily_count(tier: str, day: str | date | None = None) -> int:
    if isinstance(day, date):
        day = day.isoformat()
    day = str(day or _today_key())
    row = _fetchone('SELECT count FROM daily_counters WHERE day=? AND tier=?', (day, tier.lower()))
    return int(row.get('count') or 0) if row else 0


def increment_daily_counter(tier: str, amount: int = 1, day: str | date | None = None) -> int:
    if isinstance(day, date):
        day = day.isoformat()
    day = str(day or _today_key())
    tier = tier.lower()
    if USE_POSTGRES:
        sql = '''INSERT INTO daily_counters (day,tier,count) VALUES (?,?,?)
                 ON CONFLICT (day,tier) DO UPDATE SET count=daily_counters.count + EXCLUDED.count'''
    else:
        sql = '''INSERT INTO daily_counters (day,tier,count) VALUES (?,?,?)
                 ON CONFLICT(day,tier) DO UPDATE SET count=count + excluded.count'''
    _exec(sql, (day, tier, int(amount)))
    return get_daily_count(tier, day)


def set_daily_counter(tier: str, count: int, day: str | date | None = None) -> None:
    if isinstance(day, date):
        day = day.isoformat()
    day = str(day or _today_key())
    tier = tier.lower()
    if USE_POSTGRES:
        sql = '''INSERT INTO daily_counters (day,tier,count) VALUES (?,?,?)
                 ON CONFLICT (day,tier) DO UPDATE SET count=EXCLUDED.count'''
    else:
        sql = '''INSERT INTO daily_counters (day,tier,count) VALUES (?,?,?)
                 ON CONFLICT(day,tier) DO UPDATE SET count=excluded.count'''
    _exec(sql, (day, tier, int(count)))


# Signal result storage -------------------------------------------------------
def open_signal_result(signal_id: str, tier: str, symbol: str, side: str, entry: float, levels: dict, meta: Any = None) -> None:
    now = _now_ts()
    values = (
        signal_id, tier, symbol, side, float(entry or 0),
        float(levels.get('sl') or 0), float(levels.get('tp1') or 0), float(levels.get('tp2') or 0), float(levels.get('tp3') or 0),
        100.0, 0.0, float(levels.get('fees_pct') or 0), float(levels.get('slippage_pct') or 0),
        'OPEN', _json([]), now, now, _json(meta),
    )
    if USE_POSTGRES:
        sql = '''INSERT INTO signal_results
                 (signal_id,tier,symbol,side,entry,sl,tp1,tp2,tp3,remaining_pct,realized_pnl_pct,fees_pct,slippage_pct,status,hit_json,opened_at,updated_at,meta_json)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT (signal_id) DO NOTHING'''
    else:
        sql = '''INSERT OR IGNORE INTO signal_results
                 (signal_id,tier,symbol,side,entry,sl,tp1,tp2,tp3,remaining_pct,realized_pnl_pct,fees_pct,slippage_pct,status,hit_json,opened_at,updated_at,meta_json)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
    _exec(sql, values)


def update_signal_result(signal_id: str, *, status: str | None = None, remaining_pct: float | None = None,
                         realized_pnl_pct: float | None = None, hits: list | None = None, meta: Any = None,
                         closed: bool = False) -> None:
    row = _fetchone('SELECT meta_json, hit_json FROM signal_results WHERE signal_id=?', (signal_id,))
    if not row:
        return
    current_meta = _loads(row.get('meta_json'))
    if isinstance(meta, dict):
        current_meta.update(meta)
    hit_json = _json(hits if hits is not None else _loads(row.get('hit_json')))
    closed_at = _now_ts() if closed else None
    _exec('''UPDATE signal_results
             SET status=COALESCE(?,status), remaining_pct=COALESCE(?,remaining_pct),
                 realized_pnl_pct=COALESCE(?,realized_pnl_pct), hit_json=?, meta_json=?, updated_at=?,
                 closed_at=COALESCE(?,closed_at)
             WHERE signal_id=?''',
          (status, remaining_pct, realized_pnl_pct, hit_json, _json(current_meta), _now_ts(), closed_at, signal_id))


def result_summary(days: int = 30) -> dict:
    cutoff = _now_ts() - int(days) * 86400
    rows = _fetchall('SELECT status, realized_pnl_pct FROM signal_results WHERE opened_at>=?', (cutoff,))
    total = len(rows)
    closed = [r for r in rows if str(r.get('status') or '').upper() not in ('OPEN', '')]
    wins = [r for r in closed if float(r.get('realized_pnl_pct') or 0) > 0]
    losses = [r for r in closed if float(r.get('realized_pnl_pct') or 0) < 0]
    return {
        'days': days,
        'total': total,
        'open': total - len(closed),
        'closed': len(closed),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        'avg_pnl_pct': round(sum(float(r.get('realized_pnl_pct') or 0) for r in closed) / len(closed), 4) if closed else 0.0,
    }


# Health ----------------------------------------------------------------------
def health_summary() -> dict:
    return {
        'backend': backend_name(),
        'sqlite_path': str(DB_PATH) if not USE_POSTGRES else None,
        'today_free': get_daily_count('free'),
        'today_vip': get_daily_count('vip'),
        'recent_sent': recent_sent(5),
        'recent_blocked': last_blocked(5),
        'events': recent_events(5),
        'results_30d': result_summary(30),
    }
