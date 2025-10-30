from typing import Any, Dict, List
import numpy as np
import pandas as pd

# Columns that leak post-decision info
LEAKY_COLUMNS = [
    "Approved Benefit Amount","Status","Posted Date","Agreed Tenant Settlement",
    "Agreed Tenant Settlement Date","Collected Date","Collected Amount",
    "Collection Processed Date","Review Claim Adjudication","Review Tenant Information",
    "Update YRIG Policy Info","Open Collections","PM Notification of Claim Received",
    "Send to Collections","Audit Selection","Approval Date",
]

CURRENCY_LIKE = ["Max Benefit", "Monthly Rent", "Amount of Claim", "Approved Benefit Amount"]
DATE_LIKE = [
    "Claim Date","Lease Start Date","Lease End Date",
    "Move-Out Date","Posted Date","Agreed Tenant Settlement Date",
    "Collected Date","Collection Processed Date",
]

DATE_DIFFS = [
    ("Claim Date", "Move-Out Date", "days_claim_minus_moveout"),
    ("Lease End Date", "Lease Start Date", "days_lease_duration"),
    ("Move-Out Date", "Lease Start Date", "days_moveout_minus_lease_start"),
]

# From your error list (features model expects)
REQUIRED_BY_MODEL = {
    '#2 Relationship','days_moveout_minus_lease_start','lease_start_is_month_start',
    'Tenant Contacted','claim_to_max_ratio','Property Manager Name','Status',
    'num_tenants_reported','claim_month','moveout_year','Is there a 3rd Tenant?',
    'moveout_is_month_end','#2 Tenant Employer Name','claim_day','days_lease_duration',
    'moveout_day','View PM Information','days_claim_minus_moveout','Collection Status',
    'moveout_is_month_start','claim_year','lease_start_is_month_end','lease_start_day',
    'claim_is_month_end','PM Explanation','#2 Tenant Employer Phone #','Is there a 2nd Tenant?',
    'Property Management Company','Tenant Collection Status','Hold Reason','claim_is_month_start',
    'moveout_month','lease_start_month','lease_start_dow','claim_to_rent_ratio','claim_dow',
    'Pending Docs from PM','moveout_dow','Lease Street Address','Primary Tenant Employer Name',
    'lease_start_year'
}

def _parse_money(s):
    if pd.isna(s): return np.nan
    try:
        return float(str(s).replace(',', '').replace('$', '').strip())
    except Exception:
        return np.nan

def _to_bool(s):
    if isinstance(s, bool): return s
    if s is None: return False
    ss = str(s).strip().lower()
    return ss in ("1","true","yes","y")

def _parse_date(s):
    if pd.isna(s) or s is None or str(s).strip()=="":
        return pd.NaT
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return pd.to_datetime(s, format=fmt, errors="raise")
        except Exception:
            continue
    return pd.to_datetime(s, errors="coerce")

def _add_date_parts(df, col, prefix):
    d = df[col]
    df[f"{prefix}_year"]  = d.dt.year.fillna(0).astype(int)
    df[f"{prefix}_month"] = d.dt.month.fillna(0).astype(int)
    df[f"{prefix}_day"]   = d.dt.day.fillna(0).astype(int)
    df[f"{prefix}_dow"]   = d.dt.dayofweek.fillna(0).astype(int)  # Monday=0
    df[f"{prefix}_is_month_start"] = d.dt.is_month_start.fillna(False).astype(bool)
    df[f"{prefix}_is_month_end"]   = d.dt.is_month_end.fillna(False).astype(bool)

def preprocess_input(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1) Drop leakage if present
    to_drop = [c for c in LEAKY_COLUMNS if c in df.columns]
    if to_drop:
        df = df.drop(columns=to_drop)

    # 2) Ensure base columns exist
    base_needed = [
        "Max Benefit","Monthly Rent","Amount of Claim","Lease Street Address",
        "Property Management Company","Property Manager Name","Primary Tenant Employer Name",
        "Tenant Contacted","Tenant Collection Status","Collection Status","Status",
        "Hold Reason","PM Explanation","Pending Docs from PM","View PM Information",
        "Is there a 2nd Tenant?","Is there a 3rd Tenant?","#2 Relationship",
        "#2 Tenant Employer Name","#2 Tenant Employer Phone #",
        "Claim Date","Lease Start Date","Lease End Date","Move-Out Date",
    ]
    for col in base_needed:
        if col not in df.columns:
            df[col] = np.nan

    # 3) Parse currency-like
    for c in CURRENCY_LIKE:
        if c in df.columns:
            df[c] = df[c].apply(_parse_money)

    # 4) Parse dates
    for c in DATE_LIKE:
        if c in df.columns:
            df[c] = df[c].apply(_parse_date)

    # 5) Date parts
    if "Claim Date" in df.columns:      _add_date_parts(df, "Claim Date", "claim")
    if "Move-Out Date" in df.columns:   _add_date_parts(df, "Move-Out Date", "moveout")
    if "Lease Start Date" in df.columns:_add_date_parts(df, "Lease Start Date", "lease_start")

    # 6) Date diffs
    for a,b,out in DATE_DIFFS:
        if a in df.columns and b in df.columns:
            delta = (df[a] - df[b]).dt.days
            df[out] = delta.fillna(0).astype(int)
        else:
            df[out] = 0

    # 7) Ratios
    amt  = df.get("Amount of Claim", pd.Series(np.nan, index=df.index))
    maxb = df.get("Max Benefit", pd.Series(np.nan, index=df.index))
    rent = df.get("Monthly Rent", pd.Series(np.nan, index=df.index))
    df["claim_to_max_ratio"]  = (amt / maxb).replace([np.inf,-np.inf], np.nan).fillna(0.0)
    df["claim_to_rent_ratio"] = (amt / rent).replace([np.inf,-np.inf], np.nan).fillna(0.0)

    # 8) Booleans + counts
    df["Tenant Contacted"]      = df["Tenant Contacted"].apply(_to_bool)
    df["Is there a 2nd Tenant?"]= df["Is there a 2nd Tenant?"].apply(_to_bool)
    df["Is there a 3rd Tenant?"]= df["Is there a 3rd Tenant?"].apply(_to_bool)
    df["num_tenants_reported"]  = 1 + df["Is there a 2nd Tenant?"].astype(int) + df["Is there a 3rd Tenant?"].astype(int)

    # 9) Ensure required columns exist with sane defaults
    for col in REQUIRED_BY_MODEL:
        if col not in df.columns:
            if "days_" in col: df[col] = 0
            elif col.endswith(("_year","_month","_day","_dow")): df[col] = 0
            elif col.endswith(("_is_month_start","_is_month_end")): df[col] = False
            elif "ratio" in col: df[col] = 0.0
            elif col in ("Is there a 2nd Tenant?","Is there a 3rd Tenant?","Tenant Contacted"): df[col] = False
            else: df[col] = ""

    # 10) NA fills
    for c in df.columns:
        if pd.api.types.is_bool_dtype(df[c]): df[c] = df[c].fillna(False)
        elif pd.api.types.is_numeric_dtype(df[c]): df[c] = df[c].fillna(0)
        else: df[c] = df[c].fillna("")

    return df

def clip_predictions(df_raw: pd.DataFrame, preds) -> pd.Series:
    preds = pd.Series(np.maximum(preds, 0))  # non-negative
    if "Max Benefit" in df_raw.columns:
        mb = df_raw["Max Benefit"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
        mb = pd.to_numeric(mb, errors="coerce")
        preds = preds.where(mb.isna(), preds.clip(upper=mb))
    return preds
