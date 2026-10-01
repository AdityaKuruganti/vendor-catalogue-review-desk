const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const view = $("#view");
const send = (method, data) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
const when = iso => new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const LABEL = { pending: "Needs review", approved: "Approved", rejected: "Rejected", error: "Failed" };

async function api(path, opts) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || res.statusText));
  return body;
}
function toast(msg, bad = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.className = ""), 3500);
}

/* ---------- router ---------- */
async function route() {
  const [, page, id] = (location.hash || "#/requests").split("/");
  document.querySelectorAll("nav a[data-page]").forEach(a =>
    a.classList.toggle("on", a.dataset.page === (page === "review" ? "requests" : page)));
  view.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    if (page === "services") await servicesView();
    else if (page === "review") await reviewView(+id);
    else await requestsView();
  } catch (e) { view.innerHTML = `<h1>Something went wrong</h1><p class="err">${esc(e.message)}</p>`; }
}
addEventListener("hashchange", route);
route();

/* ---------- services ---------- */
async function servicesView() {
  const d = await api("/services"), h = d.health;
  view.innerHTML = `
    <h1>Services</h1>
    <div class="facts">
      <div><b>API</b><span class="dot ok"></span>Running</div>
      <div><b>Model</b>${esc(h.model)}</div>
      <div><b>LLM key</b><span class="dot ${h.api_key_configured ? "ok" : "bad"}"></span>${h.api_key_configured ? "Configured" : "Missing. Set OPENROUTER_API_KEY in .env"}</div>
      <div><b>Database</b>${esc(h.database)}</div>
      <div><b>Rows processed at once</b>${h.concurrency}</div>
    </div>
    <h2>Workflow stages</h2>
    <ol class="stages">${d.stages.map(s => `<li><strong>${esc(s.name)}</strong><span>${esc(s.what)}</span><em>${esc(s.mode)}</em></li>`).join("")}</ol>
    <h2>Try one vendor row</h2>
    <textarea id="try" rows="3">Gents navy blue formal shirt made of pure linen fabric. Size XL available.</textarea>
    <p><button id="tryBtn">Generate listing</button></p>
    <pre id="tryOut" hidden></pre>`;
  $("#tryBtn").onclick = async e => {
    const b = e.target, out = $("#tryOut");
    b.disabled = true; b.textContent = "Generating…";
    try { out.textContent = JSON.stringify(await api("/listings/single", send("POST", { raw_row: $("#try").value })), null, 2); }
    catch (err) { out.textContent = err.message; }
    out.hidden = false; b.disabled = false; b.textContent = "Generate listing";
  };
}

/* ---------- requests ---------- */
async function requestsView() {
  const rows = await api("/requests");
  view.innerHTML = `
    <h1>Requests</h1>
    <section class="drop">
      <div><h2>Upload a vendor document</h2><p class="muted">CSV with a raw_row column. sku and vendor columns are optional.</p></div>
      <input type="file" id="file" accept=".csv" aria-label="Vendor CSV file">
      <button id="up">Generate listings</button>
      <button id="sample" class="ghost">Use sample CSV</button>
    </section>
    ${rows.length ? `<div class="tablewrap"><table>
      <tr><th>Document</th><th>Received</th><th class="n">Rows</th><th class="n">Needs review</th><th class="n">Approved</th><th class="n">Rejected</th><th class="n">Failed</th><th></th></tr>
      ${rows.map(r => `<tr><td>${esc(r.filename)}</td><td>${when(r.created_at)}</td><td class="n">${r.total}</td>
        <td class="n">${r.pending}</td><td class="n">${r.approved}</td><td class="n">${r.rejected}</td><td class="n">${r.errors}</td>
        <td class="act"><a href="#/review/${r.id}">Open</a><button class="link" data-del="${r.id}">Remove</button></td></tr>`).join("")}</table></div>`
      : `<p class="empty">No requests yet. Upload a vendor CSV and the generated listings will wait here for review.</p>`}`;
  view.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    const r = rows.find(x => x.id === +b.dataset.del);
    const extra = r.approved ? `, including ${r.approved} approved` : "";
    if (!confirm(`Remove "${r.filename}" and its ${r.total} listings${extra}? This can't be undone.`)) return;
    try { await api(`/requests/${r.id}`, { method: "DELETE" }); toast("Request removed"); requestsView(); }
    catch (e) { toast(e.message, true); }
  });
  const run = async (btn, call) => {
    const old = btn.textContent; btn.disabled = true; btn.textContent = "Generating…";
    try { location.hash = `#/review/${(await call()).id}`; }
    catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = old; }
  };
  $("#up").onclick = e => {
    const f = $("#file").files[0];
    if (!f) return toast("Choose a CSV file first.", true);
    const fd = new FormData(); fd.append("file", f);
    run(e.target, () => api("/requests", { method: "POST", body: fd }));
  };
  $("#sample").onclick = e => run(e.target, () => api("/requests/sample", { method: "POST" }));
}

/* ---------- review desk ---------- */
let S = {};
const FIELDS = [["title", "Title"], ["color", "Color"], ["fabric", "Fabric"], ["size", "Size"]];
const visible = l => S.filter === "all" || l.status === S.filter;

async function reviewView(id) {
  const req = await api(`/requests/${id}`);
  const first = req.listings.find(l => l.status === "pending") || req.listings[0];
  S = { req, filter: "all", sel: first ? first.id : null };
  drawReview();
}

function detail(l) {
  const tag = `<aside class="tag"><h3>Vendor's text</h3><p>${esc(l.raw_row)}</p>
    <dl>${l.vendor ? `<dt>Vendor</dt><dd>${esc(l.vendor)}</dd>` : ""}${l.sku ? `<dt>SKU</dt><dd>${esc(l.sku)}</dd>` : ""}</dl></aside>`;
  const v = l.listing;
  if (!v) return tag + `<section class="editor"><p class="err">${esc(l.error)}</p>
    <p class="muted">This row failed to generate. Correct the vendor text and upload the document again.</p></section>`;
  return tag + `<section class="editor" data-id="${l.id}">
    <span class="status ${l.status}">${LABEL[l.status]}</span>
    <div class="grid2">
      ${FIELDS.map(([k, n]) => `<label>${n}<input data-k="${k}" value="${esc(v[k])}"></label>`).join("")}
      <label>Audience<select data-k="demographic">${["WOMEN", "MEN", "KIDS"].map(d => `<option ${v.demographic === d ? "selected" : ""}>${d}</option>`).join("")}</select></label>
    </div>
    <label>Description in English<textarea data-k="english_description" rows="4">${esc(v.english_description)}</textarea></label>
    <label>Description in Hinglish<textarea data-k="hinglish_description" rows="5">${esc(v.hinglish_description)}</textarea></label>
    <label>Fit guidance<textarea data-k="fit_guidance" rows="3">${esc(v.fit_guidance)}</textarea></label>
    <label>Note for the record<input id="note" value="${esc(l.note || "")}" placeholder="Optional"></label>
    <div class="actions">
      <button data-act="approved">Approve listing</button>
      <button class="danger" data-act="rejected">Reject listing</button>
      <button class="ghost" data-act="save">Save edits</button>
      ${l.status !== "pending" ? `<button class="ghost" data-act="pending">Reopen listing</button>` : ""}
    </div></section>`;
}

function drawReview() {
  const { req, filter, sel } = S, L = req.listings;
  const n = k => L.filter(l => l.status === k).length;
  const cur = L.find(l => l.id === sel);
  view.innerHTML = `
    <header class="bar">
      <div><h1>${esc(req.filename)}</h1><p class="muted">Request ${req.id}, received ${when(req.created_at)}</p></div>
      <a class="btn ghost" href="/requests/${req.id}/export.csv">Download approved (${n("approved")})</a>
    </header>
    <div class="chips">${["all", "pending", "approved", "rejected", "error"].map(k =>
      `<button data-f="${k}" class="${filter === k ? "on" : ""}">${k === "all" ? "All" : LABEL[k]} ${k === "all" ? L.length : n(k)}</button>`).join("")}</div>
    <div class="desk">
      <ul class="queue">${L.filter(visible).map(l => `<li><button data-sel="${l.id}" class="${l.id === sel ? "on" : ""}">
        <span class="dot ${l.status}"></span><span>${esc(l.sku || "Row " + (l.row_index + 1))}<small>${esc(l.listing ? l.listing.title : l.raw_row)}</small></span></button></li>`).join("")
        || `<li class="empty" style="padding:12px">No listings in this view.</li>`}</ul>
      ${cur ? detail(cur) : `<p class="empty">Select a listing to review.</p>`}
    </div>`;
  view.querySelectorAll("[data-f]").forEach(b => b.onclick = () => {
    S.filter = b.dataset.f;
    if (!L.some(l => l.id === S.sel && visible(l))) { const f = L.find(visible); S.sel = f ? f.id : null; }
    drawReview();
  });
  view.querySelectorAll("[data-sel]").forEach(b => b.onclick = () => { S.sel = +b.dataset.sel; drawReview(); });
  view.querySelectorAll("[data-act]").forEach(b => b.onclick = () => act(b.dataset.act));
}

async function act(action) {
  const ed = $(".editor"), id = +ed.dataset.id, l = S.req.listings.find(x => x.id === id);
  const edits = {};
  ed.querySelectorAll("[data-k]").forEach(el => { if (el.value !== (l.listing[el.dataset.k] ?? "")) edits[el.dataset.k] = el.value.trim(); });
  const note = $("#note").value, noteChanged = note !== (l.note || "");
  if (Object.values(edits).some(v => !v)) return toast("Fields can't be empty.", true);
  if (action === "save" && !Object.keys(edits).length && !noteChanged) return toast("No changes to save.");
  ed.querySelectorAll("button").forEach(b => (b.disabled = true));
  try {
    let u = l;
    if (Object.keys(edits).length) u = await api(`/listings/${id}`, send("PATCH", edits));
    const decision = action === "save" ? u.status : action;
    if (action !== "save" || noteChanged) u = await api(`/listings/${id}/decision`, send("POST", { decision, note }));
    Object.assign(l, u);
    toast({ approved: "Listing approved", rejected: "Listing rejected", pending: "Listing reopened", save: "Edits saved" }[action]);
    if (action === "approved" || action === "rejected") {
      const next = S.req.listings.find(x => x.status === "pending");
      if (next) S.sel = next.id;
    }
  } catch (e) { toast(e.message, true); }
  drawReview();
}
