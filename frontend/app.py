"""Streamlit dashboard.  Run from the project root:  streamlit run frontend/app.py"""
import sys
from html import escape
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

# ------------------------------------------------------------------ styling
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea, select {
    font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1240px; }

/* ---------- hero ---------- */
.hero {
    background: linear-gradient(120deg, #1e1b4b 0%, #312e81 55%, #4338ca 100%);
    border-radius: 20px;
    padding: 2rem 2.2rem;
    margin-bottom: 1.4rem;
    color: #fff;
    box-shadow: 0 10px 30px rgba(49, 46, 129, .25);
}
.hero h1 { margin: 0; font-size: 2rem; font-weight: 800; letter-spacing: -.02em; color: #fff; padding: 0; }
.hero p { margin: .5rem 0 0 0; font-size: 1rem; color: #c7d2fe; max-width: 720px; }
.chips { margin-top: 1rem; display: flex; gap: .5rem; flex-wrap: wrap; }
.chip {
    background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2);
    color: #e0e7ff; padding: .25rem .75rem; border-radius: 999px; font-size: .78rem; font-weight: 600;
}

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"] { gap: .4rem; border-bottom: 1px solid rgba(128,128,128,.25); }
.stTabs [data-baseweb="tab"] {
    height: 46px; padding: 0 1.1rem; border-radius: 10px 10px 0 0; font-weight: 600;
}
.stTabs [aria-selected="true"] { color: #4f46e5 !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: #4f46e5 !important; height: 3px; }

/* ---------- metrics ---------- */
[data-testid="stMetric"] {
    background: rgba(128,128,128,.07);
    border: 1px solid rgba(128,128,128,.22);
    border-left: 4px solid #4f46e5;
    border-radius: 14px;
    padding: 1rem 1.2rem;
}
[data-testid="stMetricLabel"] { font-weight: 600; opacity: .75; }
[data-testid="stMetricValue"] { font-weight: 800; letter-spacing: -.02em; }

/* ---------- buttons ---------- */
.stButton > button, .stDownloadButton > button {
    border-radius: 10px; font-weight: 700; padding: .55rem 1.2rem;
    border: 1px solid rgba(128,128,128,.3); transition: all .15s ease;
}
.stButton > button:hover { border-color: #4f46e5; color: #4f46e5; transform: translateY(-1px); }
.stButton > button[kind="primary"] {
    background: linear-gradient(120deg, #4338ca, #6366f1); color: #fff; border: none;
    box-shadow: 0 4px 14px rgba(79, 70, 229, .35);
}
.stButton > button[kind="primary"]:hover { color: #fff; box-shadow: 0 6px 18px rgba(79, 70, 229, .5); }

/* ---------- inputs ---------- */
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div { border-radius: 10px !important; }

/* ---------- section headings ---------- */
.section-title { font-size: 1.25rem; font-weight: 800; letter-spacing: -.01em; margin: .2rem 0 .1rem 0; }
.section-sub { opacity: .65; font-size: .92rem; margin-bottom: 1rem; }

/* ---------- match cards ---------- */
.item-card {
    border-radius: 14px; padding: .9rem 1.1rem; height: 100%;
    background: rgba(128,128,128,.07); border: 1px solid rgba(128,128,128,.2);
}
.item-card.lost  { border-left: 5px solid #f97316; }
.item-card.found { border-left: 5px solid #14b8a6; }
.item-card .tag  { font-size: .72rem; font-weight: 800; letter-spacing: .06em; }
.item-card.lost .tag  { color: #f97316; }
.item-card.found .tag { color: #14b8a6; }
.item-card .name { font-size: 1.05rem; font-weight: 700; margin: .15rem 0; }
.item-card .loc  { font-size: .88rem; opacity: .7; }
.sim-box { text-align: center; padding-top: .4rem; }
.sim-box .pct { font-size: 1.9rem; font-weight: 800; color: #4f46e5; line-height: 1.1; }
.sim-box .lbl { font-size: .75rem; opacity: .65; font-weight: 600; }

/* ---------- pills ---------- */
.pill { display: inline-block; padding: .18rem .65rem; border-radius: 999px; font-size: .75rem; font-weight: 700; margin-right: .4rem; }
.pill-searching { background: rgba(245,158,11,.18); color: #d97706; }
.pill-matched   { background: rgba(99,102,241,.18); color: #6366f1; }
.pill-resolved  { background: rgba(34,197,94,.18);  color: #16a34a; }
.pill-neutral   { background: rgba(128,128,128,.18); }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.2); }
.side-brand { font-size: 1.25rem; font-weight: 800; margin-bottom: .2rem; }
.side-sub { opacity: .65; font-size: .82rem; margin-bottom: 1rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ------------------------------------------------------------------ config check
missing = config.missing("SUPABASE_URL", "SUPABASE_KEY")
if missing:
    st.error(f"Missing settings in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
    st.stop()

db = get_supabase()

# ------------------------------------------------------------------ sidebar
st.sidebar.markdown(
    "<div class='side-brand'>📫 MailSync AI</div><div class='side-sub'>Campus Lost &amp; Found Engine</div>",
    unsafe_allow_html=True,
)
auto = st.sidebar.toggle("Auto-refresh live data (10s)", value=False)
st.sidebar.divider()
st.sidebar.caption("SYSTEM SETTINGS")
st.sidebar.caption(f"🎯 Match threshold: **{config.MATCH_THRESHOLD}**")
st.sidebar.caption(f"✉️ Emails: **{'DRY RUN (not sent)' if config.DRY_RUN_EMAIL else 'real sending'}**")

# ------------------------------------------------------------------ hero
st.markdown(
    """
    <div class="hero">
        <h1>📫 MailSync AI: Campus Lost &amp; Found Engine</h1>
        <p>Email ingestion, LLM extraction and semantic vector matching — reuniting students with their belongings.</p>
        <div class="chips">
            <span class="chip">📥 Email ingestion</span>
            <span class="chip">🧠 LLM extraction</span>
            <span class="chip">🔍 Vector matching</span>
            <span class="chip">🔒 Privacy-safe feed</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

ITEM_COLS = "id,intent,item_name,category,color,brand,location,event_date_time,summary,status,sender_email,created_at"

INTENT_LABELS = {"lost": "🟠 Lost", "found": "🟢 Found"}
STATUS_LABELS = {"searching": "🔎 Searching", "matched": "🤝 Matched", "resolved": "✅ Resolved"}


def load_items() -> pd.DataFrame:
    rows = db.table("items").select(ITEM_COLS).order("created_at", desc=True).execute().data
    return pd.DataFrame(rows)


def safe(value, default="—") -> str:
    """HTML-escape any DB value before putting it in custom HTML."""
    return escape(str(value)) if value not in (None, "") else default


def status_pill(status) -> str:
    kind = status if status in STATUS_LABELS else "neutral"
    label = STATUS_LABELS.get(status, safe(status))
    return f"<span class='pill pill-{kind}'>{label}</span>"


tab1, tab2, tab3 = st.tabs(["📡 Live Campus Feed", "🧪 Live Email Simulator", "🎯 Matches & Analytics"])

# ------------------------------------------------------------------ tab 1
with tab1:
    @st.fragment(run_every=10 if auto else None)
    def live_feed():
        st.markdown("<div class='section-title'>Active Campus Reports</div>"
                    "<div class='section-sub'>Every lost and found email, extracted and logged in real time.</div>",
                    unsafe_allow_html=True)
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 1, 2])
            intent_filter = c1.multiselect("Intent", ["lost", "found"], default=["lost", "found"])
            status_filter = c2.selectbox("Status", ["All", "searching", "matched", "resolved"])
            search = c3.text_input("Search item, place or description", placeholder="e.g. hydroflask, library, keys")

        df = load_items()
        if df.empty:
            st.info("No reports logged yet. Send an email or use the simulator tab to create one.")
            return
        df = df[df["intent"].isin(intent_filter)]
        if status_filter != "All":
            df = df[df["status"] == status_filter]
        if search:
            hay = (df["item_name"].fillna("") + " " + df["location"].fillna("") + " " + df["summary"].fillna("")).str.lower()
            df = df[hay.str.contains(search.lower(), regex=False)]

        # Privacy: hide email usernames and phone numbers on the public feed
        df = df.assign(
            sender_email=df["sender_email"].map(mask_email),
            summary=df["summary"].map(redact_phones),
            created_at=df["created_at"].astype(str).str[:16].str.replace("T", " ", regex=False),
            intent=df["intent"].map(lambda v: INTENT_LABELS.get(v, v)),
            status=df["status"].map(lambda v: STATUS_LABELS.get(v, v)),
        )
        st.caption(f"Showing **{len(df)}** report(s)")
        st.dataframe(
            df[["created_at", "intent", "item_name", "category", "location", "status", "sender_email", "summary"]],
            width="stretch", hide_index=True,
            column_config={
                "created_at": st.column_config.TextColumn("Reported"),
                "intent": st.column_config.TextColumn("Intent"),
                "item_name": st.column_config.TextColumn("Item"),
                "category": st.column_config.TextColumn("Category"),
                "location": st.column_config.TextColumn("Location"),
                "status": st.column_config.TextColumn("Status"),
                "sender_email": st.column_config.TextColumn("Reporter"),
                "summary": st.column_config.TextColumn("Summary", width="large"),
            },
        )

    live_feed()

# ------------------------------------------------------------------ tab 2
with tab2:
    st.markdown("<div class='section-title'>Interactive Email Ingestion Simulator</div>"
                "<div class='section-sub'>Paste a fake campus email to test extraction, embedding and matching live.</div>",
                unsafe_allow_html=True)

    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.container(border=True):
            sim_sender = st.text_input("Sender Email", "student2@university.edu")
            sim_subject = st.text_input("Email Subject", "Found a blue hydroflask at Student Union")
            sim_body = st.text_area(
                "Email Body",
                "Hey guys, I picked up a navy blue Hydro Flask water bottle with a national park sticker near "
                "the 2nd floor lounge in the Student Union around 3pm today. Let me know if it's yours.",
                height=170,
            )
            send_real = st.checkbox("Send real notification emails", value=False,
                                    help="Off = the match is saved but no emails go out (safe for demos).")
            run_sim = st.button("🚀 Process Simulated Email", type="primary")

    with right:
        st.markdown("**Pipeline output**")
        if not run_sim:
            st.info("Results will appear here after you process an email.")
        else:
            try:
                with st.spinner("Extracting details with the LLM..."):
                    extracted = parse_email_content(sim_subject, sim_body)
                st.caption("Step 1 · Extracted details")
                st.json(extracted)
                if not extracted["is_lost_or_found"]:
                    st.warning("⚠️ Flagged as non-lost/found noise. Nothing was stored.")
                else:
                    with st.spinner("Creating embedding and searching for matches..."):
                        msg_id = f"sim-{pd.Timestamp.now().timestamp()}"
                        result = process_and_match_item(extracted, sim_sender, msg_id, send_emails=send_real)
                    st.caption("Step 2 · Matching result")
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

        st.write("")
        if not df.empty:
            ch1, ch2 = st.columns(2)
            with ch1:
                with st.container(border=True):
                    st.caption("Reports by category")
                    st.bar_chart(df["category"].value_counts())
            with ch2:
                with st.container(border=True):
                    st.caption("Reports by status")
                    st.bar_chart(df["status"].value_counts())

        st.markdown("<div class='section-title'>System Matches &amp; Resolution</div>"
                    "<div class='section-sub'>Lost reports paired with found reports by semantic similarity.</div>",
                    unsafe_allow_html=True)
        sel = "id,similarity_score,notified,created_at,"
        sel += "lost:lost_item_id(id,item_name,location,status),found:found_item_id(id,item_name,location,status)"
        matches = db.table("matches").select(sel).order("created_at", desc=True).execute().data
        if not matches:
            st.info("No matches generated yet.")
            return
        for m in matches:
            lost, found = m["lost"], m["found"]
            score = min(max(m["similarity_score"], 0.0), 1.0)
            with st.container(border=True):
                a, mid, b = st.columns([5, 2, 5])
                a.markdown(
                    f"<div class='item-card lost'><div class='tag'>LOST</div>"
                    f"<div class='name'>{safe(lost['item_name'])}</div>"
                    f"<div class='loc'>📍 {safe(lost['location'])}</div></div>",
                    unsafe_allow_html=True,
                )
                mid.markdown(
                    f"<div class='sim-box'><div class='pct'>{m['similarity_score'] * 100:.1f}%</div>"
                    f"<div class='lbl'>similarity ↔</div></div>",
                    unsafe_allow_html=True,
                )
                b.markdown(
                    f"<div class='item-card found'><div class='tag'>FOUND</div>"
                    f"<div class='name'>{safe(found['item_name'])}</div>"
                    f"<div class='loc'>📍 {safe(found['location'])}</div></div>",
                    unsafe_allow_html=True,
                )
                st.progress(score)
                st.markdown(
                    f"{status_pill(lost['status'])}"
                    f"<span class='pill pill-neutral'>{'📧 emailed' if m['notified'] else '📭 not emailed'}</span>"
                    f"<span class='pill pill-neutral'>🕒 {safe(str(m['created_at'])[:16].replace('T', ' '))}</span>",
                    unsafe_allow_html=True,
                )
                if lost["status"] != "resolved" and st.button("Mark as resolved (item returned)", key=f"res-{m['id']}"):
                    db.table("items").update({"status": "resolved"}).in_("id", [lost["id"], found["id"]]).execute()
                    st.rerun()

    matches_and_stats()













# """Streamlit dashboard.  Run from the project root:  streamlit run frontend/app.py"""
# import sys
# from pathlib import Path

# sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `import backend...` works

# import pandas as pd
# import streamlit as st

# from backend.ai_parser import parse_email_content
# from backend.config import config
# from backend.db import get_supabase
# from backend.matcher import process_and_match_item
# from backend.utils import mask_email, redact_phones

# st.set_page_config(page_title="MailSync AI — Campus Dashboard", layout="wide", page_icon="📫")

# missing = config.missing("SUPABASE_URL", "SUPABASE_KEY")
# if missing:
#     st.error(f"Missing settings in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
#     st.stop()

# db = get_supabase()

# st.title("📫 MailSync AI: Campus Lost & Found Engine")
# st.caption("Email ingestion, LLM extraction and semantic vector matching")

# auto = st.sidebar.toggle("Auto-refresh live data (10s)", value=False)
# st.sidebar.caption(f"Match threshold: {config.MATCH_THRESHOLD}")
# st.sidebar.caption(f"Emails: {'DRY RUN (not sent)' if config.DRY_RUN_EMAIL else 'real sending'}")

# ITEM_COLS = "id,intent,item_name,category,color,brand,location,event_date_time,summary,status,sender_email,created_at"


# def load_items() -> pd.DataFrame:
#     rows = db.table("items").select(ITEM_COLS).order("created_at", desc=True).execute().data
#     return pd.DataFrame(rows)


# tab1, tab2, tab3 = st.tabs(["📡 Live Campus Feed", "🧪 Live Email Simulator", "🎯 Matches & Analytics"])

# # ------------------------------------------------------------------ tab 1
# with tab1:
#     @st.fragment(run_every=10 if auto else None)
#     def live_feed():
#         st.subheader("Active Campus Reports")
#         c1, c2, c3 = st.columns([1, 1, 2])
#         intent_filter = c1.multiselect("Intent", ["lost", "found"], default=["lost", "found"])
#         status_filter = c2.selectbox("Status", ["All", "searching", "matched", "resolved"])
#         search = c3.text_input("Search item, place or description")

#         df = load_items()
#         if df.empty:
#             st.info("No reports logged yet.")
#             return
#         df = df[df["intent"].isin(intent_filter)]
#         if status_filter != "All":
#             df = df[df["status"] == status_filter]
#         if search:
#             hay = (df["item_name"] + " " + df["location"] + " " + df["summary"]).str.lower()
#             df = df[hay.str.contains(search.lower(), regex=False)]

#         # Privacy: hide email usernames and phone numbers on the public feed
#         df = df.assign(sender_email=df["sender_email"].map(mask_email),
#                        summary=df["summary"].map(redact_phones))
#         st.dataframe(
#             df[["created_at", "intent", "item_name", "category", "location", "status", "sender_email", "summary"]],
#             width="stretch", hide_index=True,
#         )

#     live_feed()

# # ------------------------------------------------------------------ tab 2
# with tab2:
#     st.subheader("Interactive Email Ingestion Simulator")
#     st.write("Paste a fake campus email to test extraction, embedding and matching live.")
#     sim_sender = st.text_input("Sender Email", "student2@university.edu")
#     sim_subject = st.text_input("Email Subject", "Found a blue hydroflask at Student Union")
#     sim_body = st.text_area(
#         "Email Body",
#         "Hey guys, I picked up a navy blue Hydro Flask water bottle with a national park sticker near "
#         "the 2nd floor lounge in the Student Union around 3pm today. Let me know if it's yours.",
#     )
#     send_real = st.checkbox("Send real notification emails", value=False,
#                             help="Off = the match is saved but no emails go out (safe for demos).")

#     if st.button("🚀 Process Simulated Email"):
#         try:
#             with st.spinner("Extracting details with the LLM..."):
#                 extracted = parse_email_content(sim_subject, sim_body)
#             st.json(extracted)
#             if not extracted["is_lost_or_found"]:
#                 st.warning("⚠️ Flagged as non-lost/found noise. Nothing was stored.")
#             else:
#                 with st.spinner("Creating embedding and searching for matches..."):
#                     msg_id = f"sim-{pd.Timestamp.now().timestamp()}"
#                     result = process_and_match_item(extracted, sim_sender, msg_id, send_emails=send_real)
#                 if result["status"] == "matched":
#                     m = result["match"]
#                     st.success(f"✅ Stored and MATCHED with '{m['item_name']}' ({m['similarity'] * 100:.1f}% similarity).")
#                 else:
#                     st.success("✅ Stored. No match yet. It will be matched when a related report arrives.")
#         except Exception as exc:
#             st.error(f"Something went wrong: {exc}")

# # ------------------------------------------------------------------ tab 3
# with tab3:
#     @st.fragment(run_every=10 if auto else None)
#     def matches_and_stats():
#         df = load_items()
#         m1, m2, m3, m4 = st.columns(4)
#         m1.metric("Total reports", len(df))
#         m2.metric("Still searching", int((df["status"] == "searching").sum()) if not df.empty else 0)
#         m3.metric("Matched", int((df["status"] == "matched").sum()) if not df.empty else 0)
#         m4.metric("Resolved", int((df["status"] == "resolved").sum()) if not df.empty else 0)
#         if not df.empty:
#             st.caption("Reports by category")
#             st.bar_chart(df["category"].value_counts())

#         st.subheader("System Matches & Resolution")
#         sel = "id,similarity_score,notified,created_at,"
#         sel += "lost:lost_item_id(id,item_name,location,status),found:found_item_id(id,item_name,location,status)"
#         matches = db.table("matches").select(sel).order("created_at", desc=True).execute().data
#         if not matches:
#             st.info("No matches generated yet.")
#             return
#         for m in matches:
#             lost, found = m["lost"], m["found"]
#             st.write(f"**{lost['item_name']}** ({lost['location']}) ↔ **{found['item_name']}** ({found['location']})")
#             st.progress(min(max(m["similarity_score"], 0.0), 1.0))
#             st.caption(f"Similarity {m['similarity_score'] * 100:.1f}% · emailed: {'yes' if m['notified'] else 'no'} "
#                        f"· status: {lost['status']} · {m['created_at'][:16]}")
#             if lost["status"] != "resolved" and st.button("Mark as resolved (item returned)", key=f"res-{m['id']}"):
#                 db.table("items").update({"status": "resolved"}).in_("id", [lost["id"], found["id"]]).execute()
#                 st.rerun()
#             st.divider()

#     matches_and_stats()
