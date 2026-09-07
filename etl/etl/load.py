import pandas as pd
from sqlalchemy import create_engine, text


# Maps logical table name → PostgreSQL table name
TABLE_MAP = {
    "financials": "fact_financials",
    "raw_outputs": "raw_outputs",
    "employee": "fact_employee",
}


def load(frames: dict[str, pd.DataFrame], database_url: str) -> dict[str, int]:
    engine = create_engine(database_url)
    row_counts = {}

    with engine.begin() as conn:
        for key, table_name in TABLE_MAP.items():
            df = frames[key]
            # replace=drop+recreate table; swap for 'append' once schema is stable
            df.to_sql(table_name, conn, if_exists="replace", index=False)
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            row_counts[table_name] = result.scalar()

    engine.dispose()
    return row_counts
