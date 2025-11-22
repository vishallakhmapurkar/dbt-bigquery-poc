import streamlit as st
import requests, json, subprocess, os
from settings import REPO_PATH

API = "http://localhost:8000"

# --- Page config ---
st.set_page_config(page_title="dbt Wizard Dashboard", layout="wide")

# --- Custom CSS ---
st.markdown("""
<style>
body, .main {
    background-color: #F3F4F6;
    font-family: 'Segoe UI', sans-serif;
}

/* Logo bar */
.logo-bar {
    background-color: #FFFFFF;
    padding: 10px 20px;
    display: flex;
    align-items: center;
}
.logo-bar img {
    height: 40px;
    margin-right: 15px;
}
.logo-bar h2 {
    color: #1E3A8A;
    font-size: 22px;
    margin: 0;
}

/* Tabs */
.stTabs [data-baseweb="tab"] {
    background-color: #F97316;
    color: white;
    font-weight: bold;
    font-size: 18px;
    padding: 12px 20px;
    border-radius: 8px;
    margin-right: 8px;
}
.stTabs [aria-selected="true"] {
    background-color: #1E3A8A !important;
    color: white !important;
}

/* Buttons */
button[kind="primary"] {
    background-color: #F97316 !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 6px !important;
    padding: 10px 20px !important;
}
button[kind="primary"]:hover {
    background-color: #1E3A8A !important;
}

/* Hide deploy/download buttons */
button[title="Download"], button[title="Deploy"] {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# Top bar with logo and title
col1, col2 = st.columns([1, 8])
with col1:
    st.image("logo.png", width=150)   # if logo.png is in same folder as app.py
with col2:
    st.markdown("<span style='color:#1E3A8A; margin-top:10px;'>dbt Wizard Dashboard</span>", unsafe_allow_html=True)


# --- Helpers ---
def load_spec(file):
    if file is None:
        return {}, "No file uploaded", []
    try:
        raw = json.load(file)
        spec = raw.get("spec", {})
        tables = [t.get("name", "") for t in spec.get("tables", [])]
        summary = f"Source: {spec.get('source_name', 'unknown')} | Tables: {', '.join(tables) if tables else 'none'}"
        return spec, summary, tables
    except Exception as e:
        return {}, f"Failed to parse JSON: {e}", []

def save_config(spec, staging_mat, mart_mat, stg_prefix, mart_suffix):
    if not isinstance(spec, dict) or "tables" not in spec:
        return {}, "Invalid or missing spec"
    payload = {
        "spec": spec,
        "options": {
            "staging_materialization": staging_mat,
            "mart_materialization": mart_mat,
            "naming_convention_staging_prefix": stg_prefix,
            "naming_convention_mart_suffix": mart_suffix,
            "include_docs": True,
            "include_tests": False
        }
    }
    return payload, "Configuration saved"

def api_call(endpoint, payload):
    try:
        resp = requests.post(f"{API}{endpoint}", json=payload)
        if resp.status_code >= 400:
            return f"Error {resp.status_code}: {resp.text}"
        return json.dumps(resp.json(), indent=2)
    except Exception as e:
        return f"Request failed: {e}"

def run_simple(endpoint):
    try:
        resp = requests.post(f"{API}{endpoint}")
        data = resp.json()
        logs = (data.get("stdout", "") or "") + "\n" + (data.get("stderr", "") or "")
        return logs.strip()
    except Exception as e:
        return f"Request failed: {e}"

def git_push(commit_msg):
    if not commit_msg.strip():
        return "Commit message required"
    try:
        cmds = [
            ["git", "-C", REPO_PATH, "add", "."],
            ["git", "-C", REPO_PATH, "commit", "-m", commit_msg],
            ["git", "-C", REPO_PATH, "push"]
        ]
        logs = ""
        for cmd in cmds:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            logs += f"$ {' '.join(cmd)}\n{proc.stdout}{proc.stderr}\n"
            if proc.returncode != 0:
                return logs.strip()
        return logs.strip()
    except Exception as e:
        return str(e)

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📂 Upload Spec", "⚙️ Configure", "👀 Preview",
    "📁 Generate Files", "🚀 Run dbt", "🔗 Git"
])

with tab1:
    st.subheader("Step 1: Upload Spec")
    uploaded_file = st.file_uploader("Upload JSON spec", type="json")
    spec, summary, tables = load_spec(uploaded_file) if uploaded_file else ({}, "", [])
    st.text_area("Spec summary", summary, height=100)
    if tables:
        st.selectbox("Tables", tables)

with tab2:
    st.subheader("Step 2: Configure Options")
    staging_mat = st.selectbox("Staging materialization", ["view","table","incremental"])
    mart_mat = st.selectbox("Mart materialization", ["table","view","incremental"])
    stg_prefix = st.text_input("Staging prefix", "stg_")
    mart_suffix = st.text_input("Mart suffix", "_mart")
    if st.button("Save Config"):
        payload, msg = save_config(spec, staging_mat, mart_mat, stg_prefix, mart_suffix)
        st.success(msg)
        st.session_state["payload"] = payload

with tab3:
    st.subheader("Step 3: Preview")
    if st.button("Generate Preview"):
        preview = api_call("/preview_from_spec", st.session_state.get("payload", {}))
        st.text_area("Preview Output", preview, height=300)

with tab4:
    st.subheader("Step 4: Generate Files")
    if st.button("Write dbt Files"):
        gen = api_call("/generate_from_spec", st.session_state.get("payload", {}))
        st.text_area("Generation Output", gen, height=300)

with tab5:
    st.subheader("Step 5: Run dbt")
    if st.button("dbt build"):
        logs = run_simple("/build")
        st.text_area("dbt Logs", logs, height=300)
    if st.button("dbt test"):
        logs = run_simple("/test")
        st.text_area("dbt Logs", logs, height=300)

with tab6:
    st.subheader("Step 6: Git Commit & Push")
    commit_msg = st.text_input("Commit message")
    if st.button("Git Push"):
        logs = git_push(commit_msg)
        st.text_area("Git Push Logs", logs, height=300)
