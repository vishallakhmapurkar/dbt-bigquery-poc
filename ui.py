import gradio as gr
import requests, json, subprocess, os
from settings import REPO_PATH

API = "http://localhost:8000"

# --- Custom CSS: orange/blue theme, hide Gradio chrome ---
custom_css = """
/* Hide Gradio default API docs link, settings, footer */
a[href*="api-docs"], footer,
button[aria-label="Settings"], button[aria-label="Profile"] { display: none !important; }

/* Hide download and fullscreen buttons */
button[aria-label="Download"], button[aria-label="Fullscreen"] {
    display: none !important;
}

/* Theme */
body { background-color: #F9FAFB; font-family: Arial, sans-serif; }
.gradio-container { background-color: #F9FAFB !important; }

/* Buttons */
button {
    background-color: #FF7F50 !important; /* orange */
    color: white !important;
    font-weight: bold !important;
    border-radius: 6px !important;
    padding: 8px 14px !important;
}
button:hover { background-color: #2563EB !important; } /* blue hover */

/* Inputs */
textarea, input, select {
    border: 1px solid #CBD5E1 !important;
    border-radius: 6px !important;
}
/* Logo container */
.logo-container {
    background-color: white;
    text-align: center;
    padding: 10px;
}
/* Tabs */
.tab-nav button[aria-selected="true"] {
    background-color: #2563EB !important; /* active tab blue */
    color: white !important;
    font-weight: bold !important;
}
.tab-nav button {
    background-color: #FF7F50 !important; /* inactive tab orange */
    color: white !important;
}

/* Console styles */
.success { color: green; font-weight: bold; }
.error { color: red; font-weight: bold; }
.warning { color: #F59E0B; font-weight: bold; }
"""

# --- Helpers ---
def append_console(prev, msg, level="info"):
    return (prev or "") + f"<div class='{level}'>[{level.upper()}] {msg}</div>"

def reset_all():
    return {}, {}, None, "", "", "", "", "", ""

def load_spec(file, console):
    if not file:
        return {}, "No file uploaded", [], append_console(console, "No file uploaded", "warning")
    try:
        with open(file.name, encoding="utf-8") as f:
            raw = json.load(f)
        spec = raw.get("spec", {})
        tables = [t.get("name", "") for t in spec.get("tables", [])]
        summary = f"Source: {spec.get('source_name', 'unknown')} | Tables: {', '.join(tables) if tables else 'none'}"
        return spec, summary, tables, append_console(console, "Spec loaded successfully", "success")
    except Exception as e:
        return {}, "", [], append_console(console, f"Failed to parse JSON: {e}", "error")

def save_config(spec, staging_mat, mart_mat, stg_prefix, mart_suffix, console):
    if not isinstance(spec, dict) or "tables" not in spec:
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
            text = resp.text
            try:
                text = json.dumps(resp.json(), indent=2)
            except:
                pass
            return text, append_console(console, f"Error {resp.status_code} on {endpoint}", "error")
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

def git_push_ui(commit_msg, console):
    if not commit_msg.strip():
        return "Commit message required", append_console(console, "Commit message required", "error")
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
                return logs.strip(), append_console(console, f"Git command failed: {' '.join(cmd)}", "error")
        return logs.strip(), append_console(console, "Git push successful", "success")
    except Exception as e:
        return str(e), append_console(console, f"Git push failed: {e}", "error")

# --- UI ---
with gr.Blocks(css=custom_css) as demo:
    # Logo section
    with gr.Row():
        with gr.Column():
            gr.HTML("<div class='logo-container'><img src='file/logo.png' height='80'><h2 style='color:#2563EB;'>dbt Wizard Dashboard</h2></div>")

    spec_state = gr.State({})
    payload_state = gr.State({})
    console = gr.HTML(label="📜 Console")

    with gr.Tabs():
        with gr.Tab("📂 Upload Spec"):
            json_file = gr.File(label="Upload JSON spec", file_types=[".json"])
            summary_box = gr.Textbox(label="Spec summary", interactive=False)
            table_dropdown = gr.Dropdown(label="Tables", choices=[], allow_custom_value=True)
            json_file.change(load_spec, [json_file, console], [spec_state, summary_box, table_dropdown, console])

        with gr.Tab("⚙️ Configure"):
            staging_mat = gr.Dropdown(choices=["view","table","incremental"], value="view", label="Staging materialization")
            mart_mat = gr.Dropdown(choices=["table","view","incremental"], value="table", label="Mart materialization")
            stg_prefix = gr.Textbox(value="stg_", label="Staging prefix")
            mart_suffix = gr.Textbox(value="_mart", label="Mart suffix")
            save_btn = gr.Button("Save Config")
            save_btn.click(save_config, [spec_state, staging_mat, mart_mat, stg_prefix, mart_suffix, console],
                           [payload_state, summary_box, console])

        with gr.Tab("👀 Preview"):
            preview_btn = gr.Button("Generate Preview")
            preview_out = gr.Textbox(lines=12, label="Preview Output")
            preview_btn.click(lambda p,c: api_call("/preview_from_spec", p, c), [payload_state, console], [preview_out, console])

        with gr.Tab("📁 Generate Files"):
            gen_btn = gr.Button("Write dbt Files")
            gen_out = gr.Textbox(lines=12, label="Generation Output")
            gen_btn.click(lambda p,c: api_call("/generate_from_spec", p, c), [payload_state, console], [gen_out, console])

        with gr.Tab("🚀 Run dbt"):
            with gr.Row():
                build_btn = gr.Button("dbt build")
                test_btn = gr.Button("dbt test")
            logs_box = gr.Textbox(lines=12, label="dbt Logs")
            build_btn.click(lambda c: run_simple("/build", c), [console], [logs_box, console])
            test_btn.click(lambda c: run_simple("/test", c), [console], [logs_box, console])

        with gr.Tab("🔗 Git"):
            commit_msg = gr.Textbox(label="Commit message", placeholder="Enter commit message")
            gitpush_btn = gr.Button("Git Push")
            gitpush_out = gr.Textbox(lines=10, label="Git Push Logs")
            gitpush_btn.click(git_push_ui, [commit_msg, console], [gitpush_out, console])

    # Console always visible
    gr.Markdown("### 📝 Console Log")
    console_display = console


    # Reset button
    reset_btn = gr.Button("🔄 Reset")
    reset_btn.click(reset_all, None,
                    [spec_state, payload_state, json_file, summary_box, preview_out, gen_out, logs_box, gitpush_out, console]
                    )

# Launch the app
demo.launch()
