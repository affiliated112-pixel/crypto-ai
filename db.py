from pathlib import Path
import sqlite3
from typing import List, Tuple, Optional

DB_PATH = Path(__file__).with_name("bot_data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        coin TEXT NOT NULL,
        target REAL NOT NULL,
        direction TEXT NOT NULL,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        price REAL,
        rsi REAL,
        confidence TEXT,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS portfolios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        symbol TEXT,
        entry_price REAL,
        size REAL,
        ts INTEGER DEFAULT (strftime('%s','now'))
    )
    ''')
    conn.commit()
    conn.close()

# Alerts
def add_alert(user_id: int, coin: str, target: float, direction: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO alerts (user_id, coin, target, direction) VALUES (?,?,?,?)', (user_id, coin, target, direction))
    conn.commit()
    aid = c.lastrowid
    conn.close()
    return aid

def get_alerts(user_id: int) -> List[Tuple[int,str,float,str,int]]:
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, coin, target, direction, ts FROM alerts WHERE user_id=? ORDER BY ts DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [(r['id'], r['coin'], r['target'], r['direction'], r['ts']) for r in rows]

def remove_alert(alert_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM alerts WHERE id=?', (alert_id,))
    conn.commit()
    conn.close()

# Signal history
def save_signal(symbol: str, direction: str, price: float, rsi: float, confidence: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO signal_history (symbol, direction, price, rsi, confidence) VALUES (?,?,?,?,?)', (symbol, direction, price, rsi, confidence))
    conn.commit()
    conn.close()

def get_recent_signals(limit: int = 50):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT symbol,direction,price,rsi,confidence,ts FROM signal_history ORDER BY ts DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Portfolios
def add_portfolio_entry(user_id: int, symbol: str, entry_price: float, size: float):
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO portfolios (user_id, symbol, entry_price, size) VALUES (?,?,?,?)', (user_id, symbol, entry_price, size))
    conn.commit()
    conn.close()

def get_portfolio(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id,symbol,entry_price,size,ts FROM portfolios WHERE user_id=?', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def init_closed_table():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
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
    ''')
    conn.commit()
    conn.close()


def close_portfolio_entry(entry_id: int, exit_price: float) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id,user_id,symbol,entry_price,size,ts FROM portfolios WHERE id=?', (entry_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    entry = dict(row)
    entry_price = entry['entry_price']
    size = entry['size']
    # compute pnl (absolute) and percent
    pnl = (exit_price - entry_price) * size
    pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0.0
    c.execute('INSERT INTO closed_positions (user_id,symbol,entry_price,exit_price,size,pnl,pnl_pct) VALUES (?,?,?,?,?,?,?)',
              (entry['user_id'], entry['symbol'], entry_price, exit_price, size, pnl, pnl_pct))
    c.execute('DELETE FROM portfolios WHERE id=?', (entry_id,))
    conn.commit()
    conn.close()
    return {
        'user_id': entry['user_id'], 'symbol': entry['symbol'], 'entry_price': entry_price,
        'exit_price': exit_price, 'size': size, 'pnl': pnl, 'pnl_pct': pnl_pct
    }


def get_closed_positions(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id,symbol,entry_price,exit_price,size,pnl,pnl_pct,ts FROM closed_positions WHERE user_id=? ORDER BY ts DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
