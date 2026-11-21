"""Streamlit dashboard.  Run from the project root:  streamlit run frontend/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import backend...` works

import pandas as pd
import streamlit as st

from backend.ai_parser import parse_email_content
from backend.config import config
from backend.db import get_supabase
from backend.matcher import process_and_match_item
from backend.utils import mask_email, redact_phones

st.set_page_config(page_title="MailSync AI — Campus Dashboard", layout="wide", page_icon="📫")

missing = config.missing("SUPABASE_URL", "SUPABASE_KEY")
if missing:
    st.error(f"Missing settings in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
    st.stop()

db = get_supabase()

st.title("📫 MailSync AI: Campus Lost & Found Engine")
st.caption("Email ingestion, LLM extraction and semantic vector matching")

auto = st.sidebar.toggle("Auto-refresh live data (10s)", value=False)
st.sidebar.caption(f"Match threshold: {config.MATCH_THRESHOLD}")
st.sidebar.caption(f"Emails: {'DRY RUN (not sent)' if config.DRY_RUN_EMAIL else 'real sending'}")

ITEM_COLS = "id,intent,item_name,category,color,brand,location,event_date_time,summary,status,sender_email,created_at"


def load_items() -> pd.DataFrame:
    rows = db.table("items").select(ITEM_COLS).order("created_at", desc=True).execute().data
    return pd.DataFrame(rows)


tab1, tab2, tab3 = st.tabs(["📡 Live Campus Feed", "🧪 Live Email Simulator", "🎯 Matches & Analytics"])

# ------------------------------------------------------------------ tab 1
with tab1:
    @st.fragment(run_every=10 if auto else None)
    def live_feed():
        st.subheader("Active Campus Reports")
        c1, c2, c3 = st.columns([1, 1, 2])
        intent_filter = c1.multiselect("Intent", ["lost", "found"], default=["lost", "found"])
        status_filter = c2.selectbox("Status", ["All", "searching", "matched", "resolved"])
        search = c3.text_input("Search item, place or description")

        df = load_items()
        if df.empty:
            st.info("No reports logged yet.")
            return
        df = df[df["intent"].isin(intent_filter)]
        if status_filter != "All":
            df = df[df["status"] == status_filter]
        if search:
            hay = (df["item_name"] + " " + df["location"] + " " + df["summary"]).str.lower()
            df = df[hay.str.contains(search.lower(), regex=False)]

        # Privacy: hide email usernames and phone numbers on the public feed
        df = df.assign(sender_email=df["sender_email"].map(mask_email),
                       summary=df["summary"].map(redact_phones))
        st.dataframe(
            df[["created_at", "intent", "item_name", "category", "location", "status", "sender_email", "summary"]],
            width="stretch", hide_index=True,
        )

    live_feed()

# ------------------------------------------------------------------ tab 2
with tab2:
    st.subheader("Interactive Email Ingestion Simulator")
    st.write("Paste a fake campus email to test extraction, embedding and matching live.")
    sim_sender = st.text_input("Sender Email", "student2@university.edu")
    sim_subject = st.text_input("Email Subject", "Found a blue hydroflask at Student Union")
    sim_body = st.text_area(
        "Email Body",
        "Hey guys, I picked up a navy blue Hydro Flask water bottle with a national park sticker near "
        "the 2nd floor lounge in the Student Union around 3pm today. Let me know if it's yours.",
    )
    send_real = st.checkbox("Send real notification emails", value=False,
                            help="Off = the match is saved but no emails go out (safe for demos).")

    if st.button("🚀 Process Simulated Email"):
        try:
            with st.spinner("Extracting details with the LLM..."):
                extracted = parse_email_content(sim_subject, sim_body)
            st.json(extracted)
            if not extracted["is_lost_or_found"]:
                st.warning("⚠️ Flagged as non-lost/found noise. Nothing was stored.")
            else:
                with st.spinner("Creating embedding and searching for matches..."):
                    msg_id = f"sim-{pd.Timestamp.now().timestamp()}"
                    result = process_and_match_item(extracted, sim_sender, msg_id, send_emails=send_real)
                if result["status"] == "matched":
                    m = result["match"]
                    st.success(f"✅ Stored and MATCHED with '{m['item_name']}' ({m['similarity'] * 100:.1f}% similarity).")
                else:
                    st.success("✅ Stored. No match yet. It will be matched when a related report arrives.")
        except Exception as exc:
            st.error(f"Something went wrong: {exc}")

# ------------------------------------------------------------------ tab 3
with tab3:
    @st.fragment(run_every=10 if auto else None)
    def matches_and_stats():
        df = load_items()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total reports", len(df))
        m2.metric("Still searching", int((df["status"] == "searching").sum()) if not df.empty else 0)
        m3.metric("Matched", int((df["status"] == "matched").sum()) if not df.empty else 0)
        m4.metric("Resolved", int((df["status"] == "resolved").sum()) if not df.empty else 0)
        if not df.empty:
            st.caption("Reports by category")
            st.bar_chart(df["category"].value_counts())

        st.subheader("System Matches & Resolution")
        sel = "id,similarity_score,notified,created_at,"
        sel += "lost:lost_item_id(id,item_name,location,status),found:found_item_id(id,item_name,location,status)"
        matches = db.table("matches").select(sel).order("created_at", desc=True).execute().data
        if not matches:
            st.info("No matches generated yet.")
            return
        for m in matches:
            lost, found = m["lost"], m["found"]
            st.write(f"**{lost['item_name']}** ({lost['location']}) ↔ **{found['item_name']}** ({found['location']})")
            st.progress(min(max(m["similarity_score"], 0.0), 1.0))
            st.caption(f"Similarity {m['similarity_score'] * 100:.1f}% · emailed: {'yes' if m['notified'] else 'no'} "
                       f"· status: {lost['status']} · {m['created_at'][:16]}")
            if lost["status"] != "resolved" and st.button("Mark as resolved (item returned)", key=f"res-{m['id']}"):
                db.table("items").update({"status": "resolved"}).in_("id", [lost["id"], found["id"]]).execute()
                st.rerun()
            st.divider()

    matches_and_stats()
