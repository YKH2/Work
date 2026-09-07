import pandas as pd


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


def _float_to_nullable_str(series: pd.Series) -> pd.Series:
    """Convert a float column (with NaN) to object with None for nulls."""
    return series.apply(lambda x: None if pd.isna(x) else str(x))


def transform_financials(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())
    df = df.dropna(subset=["line_item", "entity"])
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["scenario"] = _float_to_nullable_str(df["scenario"])
    return df


def transform_raw_outputs(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())
    df["period"] = _excel_serial_to_date(df["period"])
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # entity and statement are float due to NaN — coerce to nullable string
    df["entity"] = _float_to_nullable_str(df["entity"])
    df["statement"] = _float_to_nullable_str(df["statement"])
    return df


def transform_employee(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalise_columns(df.copy())
    df["period"] = _excel_serial_to_date(df["period"])
    df["scenario"] = _float_to_nullable_str(df["scenario"])
    numeric_cols = [
        "headcount", "fte_share", "salary", "sti_cash",
        "sti_vesting", "lti", "on_costs", "total_cost",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_dimensions(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    fin = frames["financials"]
    raw = frames["raw_outputs"]
    emp = frames["employee"]

    entity_vals = pd.concat([
        fin["entity"].dropna(),
        emp["entity"].dropna(),
        raw["entity"].dropna(),
    ]).unique()
    dim_entity = pd.DataFrame({"entity_code": sorted(entity_vals)})

    fy_vals = pd.concat([
        fin["fy"].dropna().astype(int),
        raw["fy"].dropna().astype(int),
        emp["fy"].dropna().astype(int),
    ]).unique()
    dim_fy = pd.DataFrame({"fy": sorted(fy_vals)})

    scenario_vals = pd.concat([
        raw["scenario"].dropna(),
        fin["scenario"].dropna(),
        emp["scenario"].dropna(),
    ]).unique()
    dim_scenario = pd.DataFrame({"scenario_name": sorted(scenario_vals)})

    statement_vals = pd.concat([
        fin["statement"].dropna(),
    ]).unique()
    dim_statement = pd.DataFrame({"statement_name": sorted(statement_vals)})

    period_vals = pd.concat([
        raw["period"].dropna(),
        emp["period"].dropna(),
    ]).drop_duplicates().sort_values()
    dim_period = pd.DataFrame({"period_date": period_vals})
    dim_period["month"] = dim_period["period_date"].dt.month
    dim_period["quarter"] = dim_period["period_date"].dt.quarter
    dim_period["year"] = dim_period["period_date"].dt.year

    return {
        "dim_entity":    dim_entity,
        "dim_fy":        dim_fy,
        "dim_scenario":  dim_scenario,
        "dim_statement": dim_statement,
        "dim_period":    dim_period,
    }


def transform(frames: dict[str, pd.DataFrame]) -> tuple[dict, dict]:
    cleaned = {
        "financials":  transform_financials(frames["financials"]),
        "raw_outputs": transform_raw_outputs(frames["raw_outputs"]),
        "employee":    transform_employee(frames["employee"]),
    }
    dimensions = build_dimensions(cleaned)
    return cleaned, dimensions
