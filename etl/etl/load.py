import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

from etl.schema import metadata, DIMENSION_TABLES, FACT_TABLES, DIM_TABLE_MAP, FACT_TABLE_MAP


def _upsert_dimension(conn, table, df: pd.DataFrame) -> None:
    """Insert dimension rows, ignoring conflicts (existing keys are kept)."""
    if df.empty:
        return
    rows = df.to_dict(orient="records")
    stmt = insert(table).values(rows).on_conflict_do_nothing()
    conn.execute(stmt)


def _load_fact(conn, table, df: pd.DataFrame) -> None:
    """Bulk-insert fact rows. Call after fact table has been truncated."""
    if df.empty:
        return
    # Drop the auto-generated id column if present; Postgres assigns it
    cols = [c.name for c in table.columns if not c.autoincrement or c.name != "id"]
    df = df[[c for c in cols if c in df.columns]]
    df.to_sql(table.name, conn, if_exists="append", index=False, method="multi")


def load(
    frames: dict[str, pd.DataFrame],
    dimensions: dict[str, pd.DataFrame],
    database_url: str,
) -> dict[str, int]:
    engine = create_engine(database_url)

    with engine.begin() as conn:
        # 1. Ensure dimension tables exist
        for table in DIMENSION_TABLES:
            table.create(conn, checkfirst=True)

        # 2. Upsert dimensions (additive — never removes existing keys)
        for key, table in DIM_TABLE_MAP.items():
            _upsert_dimension(conn, table, dimensions[key])

        # 3. Drop and recreate fact tables (clean full reload each run)
        for table in reversed(FACT_TABLES):
            table.drop(conn, checkfirst=True)
        for table in FACT_TABLES:
            table.create(conn)

        # 4. Bulk-load facts
        for key, table in FACT_TABLE_MAP.items():
            _load_fact(conn, table, frames[key])

    # 5. Report row counts
    row_counts = {}
    with engine.connect() as conn:
        for table in DIMENSION_TABLES + FACT_TABLES:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table.name}"))
            row_counts[table.name] = result.scalar()

    engine.dispose()
    return row_counts
