from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sqlite3
import time

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "kospi.db"
JSON_PATH = ROOT / "docs" / "data" / "kospi.json"
KOSPI_TICKER = "1001"
KST = ZoneInfo("Asia/Seoul")


def download(start_date, end_date):
    for attempt in range(1, 4):
        try:
            df = stock.get_index_ohlcv(
                start_date, end_date, KOSPI_TICKER
            )
            return df if df is not None else pd.DataFrame()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(attempt * 10)


def normalize(df):
    if df.empty:
        return df

    df = df.reset_index().rename(columns={
        "날짜": "trade_date",
        "시가": "open",
        "고가": "high",
        "저가": "low",
        "종가": "close",
        "거래량": "volume",
        "거래대금": "trade_value",
        "등락률": "change_rate",
    })

    if "trade_date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "trade_date"})

    df["trade_date"] = pd.to_datetime(
        df["trade_date"]
    ).dt.strftime("%Y-%m-%d")

    for column in ("volume", "trade_value", "change_rate"):
        if column not in df.columns:
            df[column] = None

    return df[[
        "trade_date", "open", "high", "low", "close",
        "volume", "trade_value", "change_rate"
    ]]


def nullable(value, converter):
    return converter(value) if pd.notna(value) else None


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS kospi_daily (
                trade_date TEXT PRIMARY KEY,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER,
                trade_value INTEGER,
                change_rate REAL,
                updated_at TEXT NOT NULL
            )
        """)

        row = connection.execute(
            "SELECT MAX(trade_date) FROM kospi_daily"
        ).fetchone()
        last_date = row[0] if row else None
        start_date = (
            last_date.replace("-", "") if last_date else "20000101"
        )
        end_date = datetime.now(KST).strftime("%Y%m%d")
        df = normalize(download(start_date, end_date))
        updated_at = datetime.now(KST).isoformat(timespec="seconds")

        if not df.empty:
            rows = [(
                item.trade_date,
                float(item.open), float(item.high),
                float(item.low), float(item.close),
                nullable(item.volume, int),
                nullable(item.trade_value, int),
                nullable(item.change_rate, float),
                updated_at,
            ) for item in df.itertuples(index=False)]

            connection.executemany("""
                INSERT INTO kospi_daily (
                    trade_date, open, high, low, close,
                    volume, trade_value, change_rate, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date) DO UPDATE SET
                    open=excluded.open, high=excluded.high,
                    low=excluded.low, close=excluded.close,
                    volume=excluded.volume,
                    trade_value=excluded.trade_value,
                    change_rate=excluded.change_rate,
                    updated_at=excluded.updated_at
            """, rows)
            connection.commit()

        saved = pd.read_sql_query("""
            SELECT trade_date, open, high, low, close,
                   volume, trade_value, change_rate
            FROM kospi_daily ORDER BY trade_date
        """, connection)

    if saved.empty:
        raise RuntimeError("저장된 KOSPI 데이터가 없습니다.")

    latest = saved.iloc[-1]
    payload = {
        "name": "KOSPI",
        "ticker": KOSPI_TICKER,
        "latest": {
            "trade_date": latest["trade_date"],
            "close": latest["close"],
            "change_rate": latest["change_rate"],
        },
        "updated_at": updated_at,
        "data": saved.where(pd.notna(saved), None).to_dict(
            orient="records"
        ),
    }
    JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"갱신 완료: {latest['trade_date']} / {latest['close']}")


if __name__ == "__main__":
    main()

