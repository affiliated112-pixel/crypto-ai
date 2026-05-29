import sqlite3
from pathlib import Path
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

DB = Path(__file__).with_name("bot_data.db")
MODEL_OUT = Path(__file__).with_name("model.joblib")


def load_signals():
    if not DB.exists():
        print("No database found at", DB)
        return pd.DataFrame()
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT id,symbol,direction,price,rsi,confidence,ts FROM signal_history", conn)
    conn.close()
    return df


def encode_conf(conf):
    if not isinstance(conf, str):
        return 1
    c = conf.upper()
    if "VERY HIGH" in c or "🌟" in c:
        return 3
    if "HIGH" in c or "🔥" in c:
        return 2
    if "MEDIUM" in c or "⚡" in c:
        return 1
    return 0


def main():
    df = load_signals()
    if df.empty:
        print("No signals to train on. Collect data by running the bot for a while.")
        return
    # Simple features: rsi + confidence encoding
    df['conf_n'] = df['confidence'].apply(encode_conf)
    df = df.dropna(subset=['rsi'])
    X = df[['rsi', 'conf_n']]
    # label: BUY -> 1, SELL -> 0
    df['label'] = df['direction'].apply(lambda v: 1 if str(v).upper()=="BUY" else 0)
    y = df['label']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    clf = LogisticRegression(max_iter=200)
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    print(classification_report(y_test, preds))
    joblib.dump(clf, MODEL_OUT)
    print("Model saved to", MODEL_OUT)


if __name__ == '__main__':
    main()
