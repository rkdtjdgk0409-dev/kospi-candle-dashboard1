from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sqlite3
import time

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "kospi.db"
JSON_PATH = ROOT / "docs" / "data" / "kospi.json"
SYMBOL = "^KS11"
KST = ZoneInfo("Asia/Seoul")


def download(start_date, end_date):
    """Yahoo Finance에서 KOSPI 일봉을 조회합니다."""
    last_error = None

    for attempt in range(1, 4):
        try:
            df = yf.download(
                SYMBOL,
                start=start_date,
                end=end_date,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=30,
            )
            if df is not None and not df.empty:
                return df
            last_error = RuntimeError("Yahoo Finance 응답이 비어 있습니다.")
        except Exception as error:
            last_error = error

        if attempt < 3:
            print(f"조회 재시도 {attempt}/3: {last_error}")
            time.sleep(attempt * 10)

    raise RuntimeError("KOSPI 데이터 조회에 실패했습니다.") from last_error


def normalize(df):
    # yfinance 버전에 따라 (Price, Ticker) 형태의 다중 열이 반환됩니다.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index().rename(columns={
        "Date": "trade_date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    df["trade_date"] = pd.to_datetime(
        df["trade_date"]
    ).dt.strftime("%Y-%m-%d")
    df["change_rate"] = df["close"].pct_change() * 100
    df["trade_value"] = None

    return df[[
        "trade_date", "open", "high", "low", "close",
        "volume", "trade_value", "change_rate"
    ]].dropna(subset=["open", "high", "low", "close"])


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
        connection.commit()

        row = connection.execute(
            "SELECT MAX(trade_date) FROM kospi_daily"
        ).fetchone()
        last_date = row[0] if row else None

        # 등락률 계산을 위해 기존 마지막 날보다 며칠 앞에서 조회합니다.
        if last_date:
            start = (
                datetime.strptime(last_date, "%Y-%m-%d")
                - timedelta(days=7)
            ).strftime("%Y-%m-%d")
        else:
            start = "2000-01-01"

        # yfinance의 end는 포함되지 않으므로 한국 날짜 다음 날을 사용합니다.
        end = (datetime.now(KST) + timedelta(days=1)).strftime("%Y-%m-%d")
        downloaded = normalize(download(start, end))
        updated_at = datetime.now(KST).isoformat(timespec="seconds")

        rows = [(
            item.trade_date,
            float(item.open),
            float(item.high),
            float(item.low),
            float(item.close),
            nullable(item.volume, int),
            nullable(item.trade_value, int),
            nullable(item.change_rate, float),
            updated_at,
        ) for item in downloaded.itertuples(index=False)]

        connection.executemany("""
            INSERT INTO kospi_daily (
                trade_date, open, high, low, close,
                volume, trade_value, change_rate, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                trade_value=excluded.trade_value,
                change_rate=excluded.change_rate,
                updated_at=excluded.updated_at
        """, rows)
        connection.commit()

        saved = pd.read_sql_query("""
            SELECT trade_date, open, high, low, close,
                   volume, trade_value, change_rate
            FROM kospi_daily
            ORDER BY trade_date
        """, connection)

    if saved.empty:
        raise RuntimeError("저장된 KOSPI 데이터가 없습니다.")

    latest = saved.iloc[-1]
    payload = {
        "name": "KOSPI",
        "ticker": SYMBOL,
        "latest": {
            "trade_date": latest["trade_date"],
            "close": latest["close"],
            "change_rate": latest["change_rate"],
        },
        "updated_at": updated_at,
        "data": saved.where(pd.notna(saved), None).to_dict(orient="records"),
    }

    JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"KOSPI 갱신 완료: {latest['trade_date']} "
        f"종가 {latest['close']}"
    )


if __name__ == "__main__":
    main()

