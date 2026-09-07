from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Numeric, Date, ForeignKey
)

metadata = MetaData()

# --- Dimension tables ---

dim_entity = Table("dim_entity", metadata,
    Column("entity_code", String, primary_key=True),
)

dim_fy = Table("dim_fy", metadata,
    Column("fy", Integer, primary_key=True),
)

dim_scenario = Table("dim_scenario", metadata,
    Column("scenario_name", String, primary_key=True),
)

dim_statement = Table("dim_statement", metadata,
    Column("statement_name", String, primary_key=True),
)

dim_period = Table("dim_period", metadata,
    Column("period_date", Date, primary_key=True),
    Column("month", Integer),
    Column("quarter", Integer),
    Column("year", Integer),
)

# --- Fact tables ---

fact_financials = Table("fact_financials", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("fy", Integer, ForeignKey("dim_fy.fy")),
    Column("statement", String, ForeignKey("dim_statement.statement_name")),
    Column("line_item", String),
    Column("entity", String, ForeignKey("dim_entity.entity_code")),
    Column("classification", String),
    Column("value", Numeric),
    Column("scenario", String, ForeignKey("dim_scenario.scenario_name")),
)

fact_raw_outputs = Table("raw_outputs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("section", String),
    Column("metric", String),
    Column("period", Date, ForeignKey("dim_period.period_date")),
    Column("value", Numeric),
    Column("source", String),
    Column("fund_code", String),
    Column("capital_type", String),
    Column("entity", String, ForeignKey("dim_entity.entity_code")),
    Column("statement", String, ForeignKey("dim_statement.statement_name")),
    Column("fy", Integer, ForeignKey("dim_fy.fy")),
    Column("version", String),
    Column("scenario", String, ForeignKey("dim_scenario.scenario_name")),
)

fact_employee = Table("fact_employee", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("period", Date, ForeignKey("dim_period.period_date")),
    Column("fy", Integer, ForeignKey("dim_fy.fy")),
    Column("position_code", Integer),
    Column("position_name", String),
    Column("function", String),
    Column("entity", String, ForeignKey("dim_entity.entity_code")),
    Column("headcount", Numeric),
    Column("fte_share", Numeric),
    Column("salary", Numeric),
    Column("sti_cash", Numeric),
    Column("sti_vesting", Numeric),
    Column("lti", Numeric),
    Column("on_costs", Numeric),
    Column("total_cost", Numeric),
    Column("scenario", String, ForeignKey("dim_scenario.scenario_name")),
)

DIMENSION_TABLES = [dim_entity, dim_fy, dim_scenario, dim_statement, dim_period]
FACT_TABLES = [fact_financials, fact_raw_outputs, fact_employee]

DIM_TABLE_MAP = {
    "dim_entity":    dim_entity,
    "dim_fy":        dim_fy,
    "dim_scenario":  dim_scenario,
    "dim_statement": dim_statement,
    "dim_period":    dim_period,
}

FACT_TABLE_MAP = {
    "financials":  fact_financials,
    "raw_outputs": fact_raw_outputs,
    "employee":    fact_employee,
}
