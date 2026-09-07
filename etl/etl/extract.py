import pandas as pd


SHEET_MAP = {
    "FactTable_Financials": "financials",
    "RawOutputs": "raw_outputs",
    "FactTable_Employee": "employee",
}


def extract(filepath: str) -> dict[str, pd.DataFrame]:
    xl = pd.ExcelFile(filepath)

    missing = [s for s in SHEET_MAP if s not in xl.sheet_names]
    if missing:
        raise ValueError(f"Expected sheets not found in file: {missing}")

    return {
        target: pd.read_excel(xl, sheet_name=source)
        for source, target in SHEET_MAP.items()
    }
