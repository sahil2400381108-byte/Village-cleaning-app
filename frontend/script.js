const $ = (selector) => document.querySelector(selector);
const api = async (path, options = {}) => {
  const response = await fetch(path, { credentials: "same-origin", ...options });
  if (!response.ok) {
    let body = {};
    try { body = await response.json(); } catch (_) {}
    const error = new Error(body.detail || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }
  return response.json();
};
const esc = (value) => String(value || "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
const date = (value) => new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const statusClass = (status) => status === "Resolved" ? "resolved" : status === "In Progress" ? "progress" : "pending";
const badge = (status) => `<span class="badge ${statusClass(status)}">${esc(status)}</span>`;

function header() {
  const current = location.pathname;
  const links = [["/", "Home"], ["/report.html", "Report Complaint"], ["/track.html", "Track Complaint"], ["/complaints.html", "Complaints"]];
  $("#site-header").innerHTML = `<nav class="nav"><a class="brand" href="/"><span class="brand-mark">♧</span>CleanVillage</a><button class="menu-toggle" aria-label="Toggle menu">☰</button><div class="nav-links">${links.map(([href, name]) => `<a href="${href}" class="${current === href ? "active" : ""} ${href === "/report.html" ? "nav-report" : ""}">${name}</a>`).join("")}</div></nav>`;
  $(".menu-toggle").onclick = () => $(".nav-links").classList.toggle("open");
}

function footer() {
  $("#site-footer").innerHTML = '<div class="footer-inner"><span><b>CleanVillage</b> · Together, We Keep Our Village Clean</span><span><a href="/admin-login">Admin Login</a> · © 2026 Village Cleanliness Complaint System</span></div>';
}

async function stats() {
  const box = $("#stats");
  if (!box) return;
  try {
    const result = await api("/stats");
    box.querySelectorAll("strong").forEach((item, index) => item.textContent = [result.total, result.pending, result.in_progress, result.resolved][index]);
  } catch (_) {}
}

function timeline(status) {
  const stage = status === "Pending" ? 1 : status === "In Progress" ? 3 : 4;
  const labels = ["Complaint submitted", "Complaint reviewed", "Work in progress", "Resolved"];
  return `<div class="timeline">${labels.map((label, index) => `<div class="${index + 1 < stage ? "done" : index + 1 === stage ? "current" : ""}"><span>${index + 1 <= stage ? "✓" : "○"}</span>${label}</div>`).join("")}</div>`;
}

function publicCard(complaint) {
  return `<article class="complaint-card"><div class="card-top"><b>${esc(complaint.id)}</b>${badge(complaint.status)}</div><h3>${esc(complaint.category)}</h3><p>${esc(complaint.location)}, ${esc(complaint.area)}</p><p>${esc(complaint.description.slice(0, 100))}${complaint.description.length > 100 ? "…" : ""}</p><div class="card-date">Submitted ${date(complaint.created_at)}</div></article>`;
}

function setupReport() {
  const form = $("#complaint-form");
  if (!form) return;
  const file = form.photo;
  file.onchange = () => $(".file-note").textContent = file.files[0] ? file.files[0].name : "No file selected";
  form.onsubmit = async (event) => {
    event.preventDefault();
    const error = $("#form-error"), button = $("#submit-button"), photo = file.files[0];
    error.textContent = "";
    if (!form.checkValidity()) return error.textContent = "Please complete all required fields.";
    if (!/^[6-9]\d{9}$/.test(form.mobile.value.trim())) return error.textContent = "Enter a valid 10-digit Indian mobile number.";
    if (photo && (!["image/jpeg", "image/png"].includes(photo.type) || photo.size > 5242880)) return error.textContent = "Upload a JPG or PNG image no larger than 5 MB.";
    button.disabled = true; button.textContent = "Submitting…";
    try {
      const result = await api("/complaints", { method: "POST", body: new FormData(form) });
      $("#new-id").textContent = result.id;
      $("#track-new").href = `/track.html?id=${result.id}`;
      $("#success-modal").hidden = false;
    } catch (requestError) { error.textContent = requestError.message; }
    finally { button.disabled = false; button.innerHTML = "Submit complaint <span>→</span>"; }
  };
  $("#copy-id").onclick = async () => { await navigator.clipboard.writeText($("#new-id").textContent); $("#copy-id").textContent = "✓"; };
  $("#report-another").onclick = () => { form.reset(); $(".file-note").textContent = "No file selected"; $("#success-modal").hidden = true; };
}

function showTrack(complaint) {
  const output = $("#tracking-result"); output.hidden = false;
  output.innerHTML = `<article class="result-card"><div class="result-top"><div><p class="eyebrow">${esc(complaint.id)}</p><h2>${esc(complaint.category)} · ${esc(complaint.location)}</h2></div>${badge(complaint.status)}</div><div class="details"><p><b>Description</b>${esc(complaint.description)}</p><p><b>Submitted</b>${date(complaint.created_at)}</p></div>${complaint.photo ? `<img class="complaint-photo" src="${complaint.photo}" alt="Uploaded complaint photo">` : ""}${timeline(complaint.status)}</article>`;
}

function setupTrack() {
  const form = $("#track-form"); if (!form) return;
  form.onsubmit = async (event) => { event.preventDefault(); const error = $("#track-error"); error.textContent = ""; $("#tracking-result").hidden = true; try { showTrack(await api(`/complaints/${encodeURIComponent($("#track-id").value.trim())}`)); } catch (_) { error.textContent = "We couldn't find a complaint with this ID."; } };
  const id = new URLSearchParams(location.search).get("id"); if (id) { $("#track-id").value = id; form.requestSubmit(); }
}

async function listComplaints() {
  const box = $("#complaint-list"); if (!box) return;
  try {
    const complaints = await api("/complaints");
    const render = () => { const query = $("#search").value.toLowerCase(), category = $("#category-filter").value, status = $("#status-filter").value;
      const shown = complaints.filter((item) => !query || [item.id, item.category, item.location, item.area].join(" ").toLowerCase().includes(query)).filter((item) => !category || item.category === category).filter((item) => !status || item.status === status);
      box.innerHTML = shown.length ? shown.map(publicCard).join("") : '<div class="empty">No complaints match those filters.</div>'; };
    ["search", "category-filter", "status-filter"].forEach((id) => $("#" + id).oninput = render); render();
  } catch (_) { box.innerHTML = '<div class="error-box">Unable to load complaints right now.</div>'; }
}

function setupLogin() {
  const form = $("#admin-login-form"); if (!form) return;
  form.onsubmit = async (event) => { event.preventDefault(); const error = $("#login-error"), button = $("#login-button"); error.textContent = ""; if (!form.checkValidity()) return error.textContent = "Enter your username and password.";
    button.disabled = true; button.textContent = "Signing in…";
    try { await api("/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: form.username.value, password: form.password.value }) }); location.assign("/admin"); }
    catch (requestError) { error.textContent = requestError.status === 401 ? "Invalid admin credentials" : "Admin login is not available right now."; }
    finally { button.disabled = false; button.innerHTML = "Sign in <span>→</span>"; }
  };
}

function detailModal(complaint) {
  const modal = $("#complaint-modal");
  modal.innerHTML = `<div class="modal-card detail-modal"><button class="close-modal" aria-label="Close">×</button><p class="eyebrow">${esc(complaint.id)}</p><div class="detail-heading"><h2>${esc(complaint.category)}</h2>${badge(complaint.status)}</div><div class="admin-details"><p><b>Citizen name</b>${esc(complaint.name)}</p><p><b>Mobile number</b><a href="tel:${esc(complaint.mobile)}">${esc(complaint.mobile)}</a></p><p><b>Village / area</b>${esc(complaint.area)}</p><p><b>Location</b>${esc(complaint.location)}</p><p class="wide"><b>Description</b>${esc(complaint.description)}</p><p><b>Submitted</b>${date(complaint.created_at)}</p></div>${complaint.photo ? `<img class="detail-photo" src="${complaint.photo}" alt="Uploaded complaint photo">` : '<div class="no-photo">No photo was attached to this report.</div>'}<div class="update-status"><label>Update status<select id="detail-status"><option ${complaint.status === "Pending" ? "selected" : ""}>Pending</option><option ${complaint.status === "In Progress" ? "selected" : ""}>In Progress</option><option ${complaint.status === "Resolved" ? "selected" : ""}>Resolved</option></select></label><button class="button" id="detail-update" data-id="${esc(complaint.id)}">Update status</button></div></div>`;
  modal.hidden = false; modal.querySelector(".close-modal").onclick = () => modal.hidden = true;
  $("#detail-update").onclick = () => updateStatus(complaint.id, $("#detail-status").value, true);
}

async function updateStatus(id, status, closeModal = false) {
  const message = $("#admin-message"); message.textContent = "";
  try { await api(`/complaints/${encodeURIComponent(id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); message.textContent = "Complaint status updated successfully."; if (closeModal) $("#complaint-modal").hidden = true; await stats(); await admin(); }
  catch (requestError) { message.textContent = requestError.status === 401 ? "Your session has ended. Please sign in again." : "Unable to update the complaint status."; if (requestError.status === 401) location.assign("/admin-login"); }
}

async function admin() {
  const box = $("#admin-list"); if (!box) return;
  try {
    const complaints = await api("/admin/complaints");
    const render = () => { const query = $("#admin-search").value.toLowerCase(), category = $("#admin-category-filter").value, status = $("#admin-status-filter").value, sort = $("#admin-sort").value;
      const shown = complaints.filter((item) => !query || [item.id, item.name, item.category, item.location, item.area].join(" ").toLowerCase().includes(query)).filter((item) => !category || item.category === category).filter((item) => !status || item.status === status).sort((a, b) => sort === "newest" ? new Date(b.created_at) - new Date(a.created_at) : new Date(a.created_at) - new Date(b.created_at));
      box.innerHTML = shown.length ? shown.map((item) => `<article class="admin-row"><div><b>${esc(item.id)}</b><small>${esc(item.category)}</small></div><div>${esc(item.location)}<small>${esc(item.area)}</small></div><div>${date(item.created_at)}</div><div>${badge(item.status)}</div><div><button class="button view-complaint" data-id="${esc(item.id)}">View</button></div></article>`).join("") : '<div class="empty">No complaints match those filters.</div>';
      document.querySelectorAll(".view-complaint").forEach((button) => button.onclick = async () => { try { detailModal(await api(`/admin/complaints/${button.dataset.id}`)); } catch (_) { $("#admin-message").textContent = "Unable to load complaint details."; } });
    };
    ["admin-search", "admin-category-filter", "admin-status-filter", "admin-sort"].forEach((id) => $("#" + id).oninput = render); render();
  } catch (requestError) { if (requestError.status === 401) return location.assign("/admin-login"); box.innerHTML = '<div class="error-box">Unable to load dashboard data.</div>'; }
}

async function setupAdmin() {
  if (!$(".admin-page")) return;
  try { await api("/admin/session"); } catch (_) { location.replace("/admin-login"); return; }
  $("#logout-button").onclick = async () => { await api("/admin/logout", { method: "POST" }); location.assign("/admin-login"); };
  await admin();
}

document.addEventListener("DOMContentLoaded", () => { header(); footer(); stats(); setupReport(); setupTrack(); listComplaints(); setupLogin(); setupAdmin(); });
