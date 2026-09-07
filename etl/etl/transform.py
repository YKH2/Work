import pandas as pd


# Excel stores dates as integer day-counts from 1899-12-30
_EXCEL_EPOCH = pd.Timestamp("1899-12-30")


def _excel_serial_to_date(series: pd.Series) -> pd.Series:
    return _EXCEL_EPOCH + pd.to_timedelta(series.astype("Int64"), unit="D")


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (
        df.columns.str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
        .str.replace(r"[^\w]", "", regex=True)
    )
    return df


def transform_financials(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())
    df = df.dropna(subset=["line_item", "entity"])
    df["scenario"] = df["scenario"].where(df["scenario"].notna(), other=None)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def transform_raw_outputs(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())

    # period is an Excel date serial
    df["period"] = _excel_serial_to_date(df["period"])

    # entity/statement/fy were read as float due to NaN rows — coerce to nullable types
    df["entity"] = df["entity"].where(df["entity"].notna(), other=None)
    df["statement"] = df["statement"].where(df["statement"].notna(), other=None)
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def transform_employee(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())

    # period is an Excel date serial
    df["period"] = _excel_serial_to_date(df["period"])

    df["scenario"] = df["scenario"].where(df["scenario"].notna(), other=None)

    numeric_cols = [
        "headcount", "fte_share", "salary", "sti_cash",
        "sti_vesting", "lti", "on_costs", "total_cost",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def transform(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {
        "financials": transform_financials(frames["financials"]),
        "raw_outputs": transform_raw_outputs(frames["raw_outputs"]),
        "employee": transform_employee(frames["employee"]),
    }
