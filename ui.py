import gradio as gr
import requests
import json
import subprocess
import os
from settings import REPO_PATH
API = "http://localhost:8000"

# --------------- CSS Theme ---------------
custom_css = """
html, body {
    background: #FFFFFF;   /* default white background */
    margin: 0;
    padding: 0;
}

.gradio-container {
    background: #FFFFFF;   /* light orange container */
    color: #333333;
    font-family: 'Segoe UI', sans-serif;
}

/* Headings */
h1, h2, h3, .markdown h1, .markdown h2 {
    color: #FF6600; /* orange */
    text-shadow: 0 0 4px #FFB366;
}

/* Buttons */
button {
    background-color: #FF6600 !important;
    color: #fff !important;
    font-weight: bold !important;
    border-radius: 8px !important;
    padding: 10px 16px !important;
    box-shadow: 0 0 6px #FFB366;
    transition: transform 0.1s ease-in-out;
}
button:hover {
    transform: scale(1.05);
    background-color: #FF8C42 !important;
    box-shadow: 0 0 10px #FFB366;
}

/* Inputs */
textarea, input, select {
    background-color: #FFFFFF !important;
    border: 2px solid #FF6600 !important;
    border-radius: 6px !important;
    color: #333333 !important;
    font-family: 'Courier New', monospace;
}

/* Tabs */
.gradio-tab {
    background-color: #FFEBD6 !important;
    color: #FF6600 !important;
    font-weight: bold;
    border-radius: 6px;
    padding: 10px;
}
.gradio-tab.gradio-tab-active {
    background-color: #FF6600 !important;
    color: #FFFFFF !important;
    text-shadow: 0 0 4px #FFB366;
}

/* Console terminal */
#console {
    background-color: #FFFFFF;
    color: #FF6600;
    font-family: 'Courier New', monospace;
    padding: 12px;
    border-radius: 6px;
    height: 300px;
    overflow-y: auto;
    box-shadow: inset 0 0 6px #FFB366;
}

/* Log levels */
.success { color: #FF6600; font-weight: bold; }
.error   { color: #CC3300; font-weight: bold; }
.warning { color: #FF8C42; font-weight: bold; }

/* Hide Gradio default buttons and footer */
button[aria-label="Settings"],
button[aria-label="Profile"],
button[aria-label="Download"],
button[aria-label="Fullscreen"],
footer {
    display: none !important;
}



.logo-text {
    font-family: 'Orbitron', sans-serif;
    font-size: 32px;
    font-weight: 700;
    text-align: left;   /* align to left */
    margin: 15px 0;
}

.logo-text .dbt {
    color: #194B63; /* blue */
    text-shadow: 0 0 6px #66B2FF;
}

.logo-text .arrow {
    color: #FF6600; /* orange */
    text-shadow: 0 0 6px #FFB366;
}

.logo-text .gen {
    color: #194B63; /* blue */
    text-shadow: 0 0 6px #66B2FF;
}
"""




# --------------- Helpers ---------------
def append_console(prev, msg, level="info"):
    return (prev or "") + f"<div class='{level}'>[{level.upper()}] {msg}</div>"


def clear_console():
    return ""

def load_spec(file, console):
    if not file:
        return {}, "No file uploaded", [], append_console(console, "No file uploaded", "warning")
    try:
        spec = json.load(open(file.name, encoding="utf-8"))
        spec = spec.get('spec')
        tables = [t["name"] for t in spec.get("tables", [])]
        summary = f"Source: {spec.get('source_name')} | Tables: {', '.join(tables)}"
        return spec, summary, tables, append_console(console, "Spec loaded successfully", "success")
    except Exception as e:
        return {}, "", [], append_console(console, f"Failed to parse JSON: {e}", "error")

def save_config(spec, staging_mat, mart_mat, stg_prefix, mart_suffix, console):
    if not isinstance(spec, dict) or "source_name" not in spec or "tables" not in spec:
        return {}, "Invalid or missing spec", append_console(console, "Invalid or missing spec", "error")
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
    return payload, "Configuration saved", append_console(console, "Configuration saved", "success")

def api_call(endpoint, payload, console):
    try:
        resp = requests.post(f"{API}{endpoint}", json=payload)
        if resp.status_code >= 400:
            # Show exact server error JSON for transparency
            return json.dumps(resp.json(), indent=2), append_console(console, f"Error {resp.status_code} on {endpoint}", "error")
        data = resp.json()
        return json.dumps(data, indent=2), append_console(console, f"OK {endpoint}", "success")
    except Exception as e:
        return "", append_console(console, f"Request failed: {e}", "error")

def run_simple(endpoint, console):
    try:
        resp = requests.post(f"{API}{endpoint}")
        data = resp.json()
        logs = (data.get("stdout", "") or "") + "\n" + (data.get("stderr", "") or "")
        return logs.strip(), append_console(console, f"OK {endpoint}", "success")
    except Exception as e:
        return "", append_console(console, f"Request failed: {e}", "error")
# NEW: Git push logic
def git_push_ui(commit_msg, console):
    if not commit_msg.strip():
        return "Commit message required", append_console(console, "Commit message required", "error")
    try:
        # Run git commands in REPO_PATH
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
                return logs.strip(), append_console(console, f"Git command failed: {' '.join(cmd)}", "error")
        return logs.strip(), append_console(console, "Git push successful", "success")
    except Exception as e:
        return str(e), append_console(console, f"Git push failed: {e}", "error")
# --------------- UI ---------------
with gr.Blocks(title="dbt>Gen",css=custom_css) as demo:
    gr.Markdown("""
<div class="logo-text">
   🚀 <span class="dbt">dbt</span><span class="arrow">&gt;</span><span class="gen">Gen</span>
</div>
""")

    spec_state = gr.State({})
    payload_state = gr.State({})
    console = gr.HTML(label="📜 Console")

    with gr.Tab("Upload spec"):
        json_file = gr.File(label="Upload JSON spec", file_types=[".json"])
        summary_box = gr.Textbox(label="Spec summary", interactive=False)
        table_dropdown = gr.Dropdown(label="Tables", choices=[], allow_custom_value=True)
        json_file.change(load_spec, [json_file, console], [spec_state, summary_box, table_dropdown, console])

    with gr.Tab("Configure"):
        staging_mat = gr.Dropdown(choices=["view", "table", "incremental"], value="view",
                                  label="Staging materialization", allow_custom_value=True)
        mart_mat = gr.Dropdown(choices=["table", "view", "incremental"], value="table",
                               label="Mart materialization", allow_custom_value=True)
        stg_prefix = gr.Textbox(value="stg_", label="Staging prefix")
        mart_suffix = gr.Textbox(value="_mart", label="Mart suffix")
        save_btn = gr.Button("Save config")
        save_btn.click(save_config, [spec_state, staging_mat, mart_mat, stg_prefix, mart_suffix, console],
                       [payload_state, summary_box, console])

    with gr.Tab("Preview"):
        preview_btn = gr.Button("Generate preview")
        preview_out = gr.Textbox(lines=20, label="Preview output")
        preview_btn.click(lambda payload, console: api_call("/preview_from_spec", payload, console),
                          [payload_state, console], [preview_out, console])

    with gr.Tab("Generate files"):
        gen_btn = gr.Button("Write dbt files")
        gen_out = gr.Textbox(lines=20, label="Generation output")
        gen_btn.click(lambda payload, console: api_call("/generate_from_spec", payload, console),
                      [payload_state, console], [gen_out, console])

    with gr.Tab("Run dbt"):
        build_btn = gr.Button("dbt build")
        test_btn = gr.Button("dbt test")
        logs_box = gr.Textbox(lines=16, label="dbt logs")
        build_btn.click(lambda console: run_simple("/build", console), [console], [logs_box, console])
        test_btn.click(lambda console: run_simple("/test", console), [console], [logs_box, console])
    with gr.Tab("Git"):
        commit_msg = gr.Textbox(label="Commit message", placeholder="Enter commit message")
        gitpush_btn = gr.Button("Git Push")
        gitpush_out = gr.Textbox(lines=12, label="Git Push logs")
        gitpush_btn.click(git_push_ui, [commit_msg, console], [gitpush_out, console])
    clear_btn = gr.Button("Clear console")
    clear_btn.click(clear_console, None, console)

demo.launch(favicon_path="logo.png")
