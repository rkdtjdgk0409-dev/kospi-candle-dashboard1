from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sqlite3
import time

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "kospi.db"
JSON_PATH = ROOT / "docs" / "data" / "kospi.json"

# pykrx에서 사용하는 코스피 종합지수 코드
KOSPI_TICKER = "1001"
INITIAL_START_DATE = "20000101"
KST = ZoneInfo("Asia/Seoul")


def prepare_directories() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)


def prepare_database(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
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
        """
    )
    connection.commit()


def get_last_saved_date(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT MAX(trade_date) FROM kospi_daily"
    ).fetchone()
    return row[0] if row else None


def download_kospi(start_date: str, end_date: str) -> pd.DataFrame:
    last_error: Exception | None = None

    for attempt in range(1, 4):
        try:
            print(
                f"KOSPI 조회 {start_date}~{end_date} "
                f"(시도 {attempt}/3)"
            )
            result = stock.get_index_ohlcv(
                start_date,
                end_date,
                KOSPI_TICKER,
            )
            return result if result is not None else pd.DataFrame()
        except Exception as error:
            last_error = error
            print(f"조회 실패: {error}")
            if attempt < 3:
                time.sleep(attempt * 10)

    raise RuntimeError("KOSPI 데이터 조회에 3회 실패했습니다.") from last_error


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    normalized = df.reset_index().rename(
        columns={
            "날짜": "trade_date",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
            "거래대금": "trade_value",
            "등락률": "change_rate",
        }
    )

    # 라이브러리 버전에 따라 인덱스 열 이름이 다를 때를 대비합니다.
    if "trade_date" not in normalized.columns:
        normalized = normalized.rename(
            columns={normalized.columns[0]: "trade_date"}
        )

    normalized["trade_date"] = pd.to_datetime(
        normalized["trade_date"]
    ).dt.strftime("%Y-%m-%d")

    for required in ("open", "high", "low", "close"):
        if required not in normalized.columns:
            raise RuntimeError(f"필수 데이터 열이 없습니다: {required}")

    for optional in ("volume", "trade_value", "change_rate"):
        if optional not in normalized.columns:
            normalized[optional] = None

    return normalized[
        [
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_value",
            "change_rate",
        ]
    ]


def optional_number(value, converter):
    return converter(value) if pd.notna(value) else None


def save_rows(
    connection: sqlite3.Connection,
    df: pd.DataFrame,
) -> int:
    if df.empty:
        return 0

    updated_at = datetime.now(KST).isoformat(timespec="seconds")
    rows = [
        (
            row.trade_date,
            float(row.open),
            float(row.high),
            float(row.low),
            float(row.close),
            optional_number(row.volume, int),
            optional_number(row.trade_value, int),
            optional_number(row.change_rate, float),
            updated_at,
        )
        for row in df.itertuples(index=False)
    ]

    connection.executemany(
        """
        INSERT INTO kospi_daily (
            trade_date, open, high, low, close,
            volume, trade_value, change_rate, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(trade_date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            trade_value = excluded.trade_value,
            change_rate = excluded.change_rate,
            updated_at = excluded.updated_at
        """,
        rows,
    )
    connection.commit()
    return len(rows)


def export_json(connection: sqlite3.Connection) -> None:
    df = pd.read_sql_query(
        """
        SELECT trade_date, open, high, low, close,
               volume, trade_value, change_rate
        FROM kospi_daily
        ORDER BY trade_date
        """,
        connection,
    )

    if df.empty:
        raise RuntimeError("내보낼 KOSPI 데이터가 없습니다.")

    latest = df.iloc[-1]
    payload = {
        "name": "KOSPI",
        "ticker": KOSPI_TICKER,
        "latest": {
            "trade_date": latest["trade_date"],
            "close": latest["close"],
            "change_rate": latest["change_rate"],
        },
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "data": df.where(pd.notna(df), None).to_dict(orient="records"),
    }
    JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    prepare_directories()

    with sqlite3.connect(DB_PATH) as connection:
        prepare_database(connection)
        last_date = get_last_saved_date(connection)
        start_date = (
            last_date.replace("-", "")
            if last_date
            else INITIAL_START_DATE
        )
        end_date = datetime.now(KST).strftime("%Y%m%d")

        downloaded = download_kospi(start_date, end_date)
        normalized = normalize_dataframe(downloaded)
        count = save_rows(connection, normalized)
        export_json(connection)

    print(f"DB 반영 행 수: {count}")
    print(f"SQLite: {DB_PATH}")
    print(f"웹 JSON: {JSON_PATH}")
    print("KOSPI 갱신 완료")


if __name__ == "__main__":
    main()

