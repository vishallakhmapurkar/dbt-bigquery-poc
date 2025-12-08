document.addEventListener("DOMContentLoaded", () => {
  // Hide console initially
  const consoleSection = document.querySelector(".card.console");
  consoleSection.classList.add("hidden");

  // Fetch dashboard counts
  fetchDashboardCounts();
});

// =======================
// Console Helpers
// =======================
const consoleBox = document.getElementById("consoleBox");

function log(level, msg) {
  const line = document.createElement("div");
  line.className = `console-line ${level.toLowerCase()}`;

  const icon = document.createElement("span");
  icon.className = "console-icon";

  switch (level.toLowerCase()) {
    case "info":  icon.textContent = "ℹ"; break;
    case "warn":  icon.textContent = "⚠"; break;
    case "error": icon.textContent = "✖"; break;
    case "success": icon.textContent = "✔"; break;
    default:      icon.textContent = "•";
  }

  const timestamp = new Date().toLocaleTimeString();
  const text = document.createElement("span");
  text.textContent = `[${timestamp}] [${level.toUpperCase()}] ${msg}`;

  line.appendChild(icon);
  line.appendChild(text);
  consoleBox.appendChild(line);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

document.getElementById("clearConsole").addEventListener("click", () => {
  consoleBox.innerHTML = "";
});

// =======================
// Navigation
// =======================
const tabs = document.querySelectorAll("[data-tab]");
const navButtons = document.querySelectorAll(".nav-btn");

navButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    const target = btn.getAttribute("data-tab");

    // Hide all tabbed sections
    tabs.forEach(t => t.classList.add("hidden"));
    document.getElementById(target).classList.remove("hidden");

    // Update active nav button
    navButtons.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    // Special rule: Console hidden only on Dashboard
    const consoleSection = document.querySelector(".card.console");
    if (target === "dashboard") {
      consoleSection.classList.add("hidden");
    } else {
      consoleSection.classList.remove("hidden");
    }
  });
});

// =======================
// State
// =======================
let lastSpec = null;
let lastConfigPayload = null;

// =======================
// Dashboard
// =======================
function updateDashboardCounts(counts) {
  document.getElementById("countStaging").textContent = counts.staging;
  document.getElementById("countMart").textContent = counts.mart;
  document.getElementById("countSchema").textContent = counts.schema;
}

function fetchDashboardCounts() {
  fetch("/api/fileCounts")
    .then(res => res.json())
    .then(counts => updateDashboardCounts(counts))
    .catch(err => console.error("Error fetching file counts:", err));
}

// Run once on page load
document.addEventListener("DOMContentLoaded", () => {
  fetchDashboardCounts();
});

// Also run when sidebar Dashboard button is clicked
document.getElementById("btnDashboard").addEventListener("click", () => {
  fetchDashboardCounts();
});

// =======================
// Upload Spec
// =======================
document.getElementById("btnUpload").addEventListener("click", async () => {
  const fileInput = document.getElementById("jsonFile");
  if (!fileInput.files[0]) {
    log("warn", "No file selected");
    return;
  }
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const resp = await fetchWithSpinner("/upload_spec", { method: "POST", body: formData });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Upload failed");

    lastSpec = data.raw || null;
    document.getElementById("uploadSummary").textContent =
      JSON.stringify(lastSpec, null, 2);
    log("success", "Spec uploaded successfully");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// Save Config
// =======================
document.getElementById("btnSaveConfig").addEventListener("click", async () => {
  const formData = new FormData();
  formData.append("staging_mat", document.getElementById("stagingMat").value);
  formData.append("mart_mat", document.getElementById("martMat").value);
  formData.append("stg_prefix", document.getElementById("stgPrefix").value);
  formData.append("mart_suffix", document.getElementById("martSuffix").value);
  try {
    const resp = await fetchWithSpinner("/save_config", { method: "POST", body: formData });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Save config failed");

    lastConfigPayload = data.payload;
    document.getElementById("configResult").textContent = JSON.stringify(data, null, 2);
    log("success", "Configuration saved");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// Preview
// =======================
document.getElementById("btnPreview").addEventListener("click", async () => {
  const previewOut = document.getElementById("previewOut");
  previewOut.textContent = "";
  try {
    const payload = { spec: lastSpec, options: lastConfigPayload?.options || {} };
    const resp = await fetchWithSpinner("/preview_from_spec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Preview failed");

    previewOut.textContent = JSON.stringify(data, null, 2);
    log("success", "Preview generated");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// Generate
// =======================
document.getElementById("btnGenerate").addEventListener("click", async () => {
  const generateOut = document.getElementById("generateOut");
  generateOut.textContent = "";
  try {
    const payload = { spec: lastSpec, options: lastConfigPayload?.options || {} };
    const resp = await fetchWithSpinner("/generate_from_spec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Generation failed");

    generateOut.textContent = JSON.stringify(data, null, 2);
    log("success", "Files generated");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// dbt build
// =======================
document.getElementById("btnBuild").addEventListener("click", async () => {
  const logs = document.getElementById("dbtLogs");
  logs.textContent = "";
  try {
    const resp = await fetchWithSpinner("/build", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Build failed");

    logs.textContent = `${data.stdout}\n${data.stderr}`;
    log("success", "dbt build completed");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// dbt test
// =======================
document.getElementById("btnTest").addEventListener("click", async () => {
  const logs = document.getElementById("dbtLogs");
  logs.textContent = "";
  try {
    const resp = await fetchWithSpinner("/test", { method: "POST" });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Test failed");

    logs.textContent = `${data.stdout}\n${data.stderr}`;
    log("success", "dbt test completed");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// Git push
// =======================
document.getElementById("btnGitPush").addEventListener("click", async () => {
  const msg = document.getElementById("commitMsg").value;
  const logs = document.getElementById("gitLogs");
  logs.textContent = "";
  if (!msg.trim()) {
    log("warn", "Commit message required");
    return;
  }
  try {
    const formData = new FormData();
    formData.append("commit_msg", msg);
    const resp = await fetchWithSpinner("/gitpush", { method: "POST", body: formData });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Git push failed");

    logs.textContent = data.logs || "";
    log("success", "Git push successful");
  } catch (err) {
    log("error", err.message);
  }
});

// =======================
// Spinner Helpers
// =======================
function showSpinner() {
  document.getElementById("spinnerOverlay").style.display = "flex";
}
function hideSpinner() {
  document.getElementById("spinnerOverlay").style.display = "none";
}

// Wrap fetch calls
async function fetchWithSpinner(url, options) {
  try {
    showSpinner();
    const resp = await fetch(url, options);
    return resp;
  } finally {
    hideSpinner();
  }
}
