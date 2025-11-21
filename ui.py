import gradio as gr
import requests
import json

API = "http://localhost:8000"

# --------------- CSS Theme ---------------
custom_css = """
body { background-color: #FFF4E6; }
.gradio-container { background-color: #FFF4E6 !important; }
button {
    background-color: #FF8C42 !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 8px !important;
    padding: 10px 16px !important;
}
button:hover { background-color: #FF6F00 !important; }
textarea, input, select {
    border: 2px solid #FFB366 !important;
    border-radius: 6px !important;
}
.markdown {
    background-color: #FFEBD6 !important;
    padding: 10px; border-radius: 6px;
}
.success { color: green; font-weight: bold; }
.error { color: red; font-weight: bold; }
.warning { color: #FF6F00; font-weight: bold; }
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

# --------------- UI ---------------
with gr.Blocks(css=custom_css) as demo:
    gr.Markdown("# 🚀 dbt Generator UI (Ollama gemma3:4b + FastAPI)\nUpload a spec, configure materializations, preview, generate files, and run dbt.")

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

    clear_btn = gr.Button("Clear console")
    clear_btn.click(clear_console, None, console)

demo.launch()
