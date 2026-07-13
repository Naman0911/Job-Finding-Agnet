"""
dashboard/app.py
Streamlit dashboard for the AI Job Hunter agent.

v9 Change 17: A read-mostly view into the existing database/jobs.db.
Does NOT duplicate or replace any pipeline logic — just visualizes
what's already there.

Usage:
    streamlit run dashboard/app.py

Features:
    - Job table with sorting/filtering (company, source, date range)
    - New vs. previously seen badges
    - Apply button (opens job URL in new tab)
    - Company management (add to companies.json from the UI)
    - Basic stats view (total jobs, this week, top companies chart)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# ── Path setup ────────────────────────────────────────────────────────────────
# Use the same DB path as the pipeline via config/settings.py
import sys

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from config.settings import settings

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Job Hunter Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
COMPANIES_JSON = _ROOT / "config" / "companies.json"
ALLOWED_ATS_TYPES = [
    "greenhouse", "lever", "ashby", "custom",
    "naukri", "instahyre", "cutshort", "wellfound",
    "indeed", "glassdoor",
]


# ── Database helpers ──────────────────────────────────────────────────────────
@st.cache_data(ttl=60)  # Cache for 60 seconds
def load_jobs_df() -> pd.DataFrame:
    """Load all jobs from the SQLite database into a DataFrame."""
    db_path = settings.db_path
    if not db_path.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            "SELECT * FROM jobs ORDER BY first_seen_at DESC", conn
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()

    if not df.empty and "first_seen_at" in df.columns:
        df["first_seen_at"] = pd.to_datetime(df["first_seen_at"], errors="coerce")

    return df


@st.cache_data(ttl=60)
def load_run_log() -> pd.DataFrame:
    """Load the run log from the SQLite database."""
    db_path = settings.db_path
    if not db_path.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            "SELECT * FROM run_log ORDER BY started_at DESC LIMIT 50", conn
        )
    except Exception:
        df = pd.DataFrame()
    finally:
        conn.close()

    return df


def load_companies() -> list[dict]:
    """Load the companies config."""
    if not COMPANIES_JSON.exists():
        return []
    with open(COMPANIES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_companies(companies: list[dict]):
    """Save the companies config."""
    with open(COMPANIES_JSON, "w", encoding="utf-8") as f:
        json.dump(companies, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Header styling */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #6c63ff;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem;
        color: #888;
        margin-top: -10px;
        margin-bottom: 20px;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border: 1px solid #3d3d5c;
        border-radius: 12px;
        padding: 16px;
    }
    [data-testid="stMetricValue"] {
        color: #6c63ff;
        font-size: 2rem;
    }

    /* Badge styling */
    .new-badge {
        background: linear-gradient(135deg, #6c63ff 0%, #a78bfa 100%);
        color: white;
        padding: 2px 8px;
        border-radius: 8px;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0e0e1a 0%, #1a1a2e 100%);
    }

    /* Success/error messages */
    .stSuccess {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ── Main App ──────────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown('<div class="main-header">🤖 AI Job Hunter Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Monitor your job pipeline, browse openings, and manage sources</div>', unsafe_allow_html=True)

    # Load data
    df = load_jobs_df()

    # ── Sidebar: Filters + Company Management ────────────────────────────────
    with st.sidebar:
        st.header("🔎 Filters")

        # Company filter
        if not df.empty:
            all_companies = sorted(df["company"].dropna().unique().tolist())
            selected_companies = st.multiselect(
                "Company",
                options=all_companies,
                default=[],
                placeholder="All companies",
            )

            # Source filter
            all_sources = sorted(df["source"].dropna().unique().tolist())
            selected_sources = st.multiselect(
                "Source",
                options=all_sources,
                default=[],
                placeholder="All sources",
            )

            # Date range filter
            st.subheader("📅 Date Range")
            min_date = df["first_seen_at"].min()
            max_date = df["first_seen_at"].max()

            if pd.notna(min_date) and pd.notna(max_date):
                date_range = st.date_input(
                    "First seen between",
                    value=(min_date.date(), max_date.date()),
                    min_value=min_date.date(),
                    max_value=max_date.date(),
                )
            else:
                date_range = None
        else:
            selected_companies = []
            selected_sources = []
            date_range = None

        st.divider()

        # ── Company Management ───────────────────────────────────────────────
        st.header("➕ Add Company")
        with st.form("add_company_form", clear_on_submit=True):
            new_name = st.text_input("Company Name *")
            new_ats_type = st.selectbox("ATS Type *", options=ALLOWED_ATS_TYPES)
            new_identifier = st.text_input(
                "Identifier *",
                help="ATS slug (e.g. 'razorpay') or comma-separated keywords for aggregators",
            )
            new_location = st.selectbox(
                "Location Priority",
                options=["pune", "india"],
                index=0,
            )
            new_search_location = st.text_input(
                "Search Location",
                help="For aggregators only (e.g. 'pune', 'india', 'Pune, Maharashtra')",
            )

            submitted = st.form_submit_button("Add Company", use_container_width=True)

            if submitted:
                if not new_name or not new_identifier:
                    st.error("Name and Identifier are required!")
                elif new_ats_type not in ALLOWED_ATS_TYPES:
                    st.error(f"Invalid ATS type: {new_ats_type}")
                else:
                    companies = load_companies()
                    existing_names = {c["name"].lower() for c in companies}

                    if new_name.lower() in existing_names:
                        st.warning(f"'{new_name}' already exists in companies.json!")
                    else:
                        entry = {
                            "name": new_name,
                            "ats_type": new_ats_type,
                            "identifier": new_identifier,
                            "location_priority": new_location,
                            "enabled": True,
                            "notes": f"Added from dashboard on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        }
                        if new_search_location:
                            entry["search_location"] = new_search_location

                        companies.append(entry)
                        save_companies(companies)
                        st.success(f"✅ Added '{new_name}' ({new_ats_type})")
                        st.cache_data.clear()

    # ── Stats Section ────────────────────────────────────────────────────────
    if df.empty:
        st.info(
            "📂 No jobs found in the database yet. "
            "Run the pipeline first: `python -m scheduler.run --mode once`"
        )
        return

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)

    total_jobs = len(df)
    jobs_this_week = len(df[df["first_seen_at"] >= week_ago]) if "first_seen_at" in df.columns else 0
    total_companies = df["company"].nunique()

    # Most recent run
    run_log = load_run_log()
    last_run = run_log.iloc[0]["started_at"] if not run_log.empty else "Never"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 Total Jobs Tracked", total_jobs)
    with col2:
        st.metric("📅 This Week", jobs_this_week)
    with col3:
        st.metric("🏢 Companies", total_companies)
    with col4:
        st.metric("🕐 Last Run", str(last_run)[:16] if last_run != "Never" else "Never")

    st.divider()

    # ── Top Companies Bar Chart ──────────────────────────────────────────────
    tab_jobs, tab_stats = st.tabs(["📋 Jobs", "📈 Analytics"])

    with tab_stats:
        st.subheader("Top 10 Companies by Job Count")
        top_companies = df["company"].value_counts().head(10)
        st.bar_chart(top_companies)

        st.subheader("Jobs by Source")
        source_counts = df["source"].value_counts()
        st.bar_chart(source_counts)

        st.subheader("Jobs Over Time (Daily)")
        if "first_seen_at" in df.columns:
            daily = df.set_index("first_seen_at").resample("D").size()
            if not daily.empty:
                st.line_chart(daily)

    # ── Job Table ────────────────────────────────────────────────────────────
    with tab_jobs:
        # Apply filters
        filtered = df.copy()

        if selected_companies:
            filtered = filtered[filtered["company"].isin(selected_companies)]
        if selected_sources:
            filtered = filtered[filtered["source"].isin(selected_sources)]
        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                (filtered["first_seen_at"].dt.date >= start_date)
                & (filtered["first_seen_at"].dt.date <= end_date)
            ]

        st.subheader(f"📋 Jobs ({len(filtered)} shown)")

        if filtered.empty:
            st.info("No jobs match the current filters.")
        else:
            # Add "New" badge column
            filtered = filtered.copy()
            filtered["Status"] = filtered["first_seen_at"].apply(
                lambda x: "🆕 New" if pd.notna(x) and x >= day_ago else ""
            )

            # Display columns
            display_cols = ["Status", "company", "title", "location", "source", "first_seen_at", "url"]
            available_cols = [c for c in display_cols if c in filtered.columns]
            display_df = filtered[available_cols].copy()

            # Rename for display
            display_df.columns = [
                c.replace("_", " ").title() if c != "Status" else c
                for c in display_df.columns
            ]

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Url": st.column_config.LinkColumn(
                        "Apply Link",
                        display_text="Apply →",
                    ),
                    "First Seen At": st.column_config.DatetimeColumn(
                        "First Seen",
                        format="YYYY-MM-DD HH:mm",
                    ),
                },
            )

            # Download button
            csv = filtered.to_csv(index=False)
            st.download_button(
                "📥 Download as CSV",
                data=csv,
                file_name=f"jobs_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
