const $ = (sel, el = document) => el.querySelector(sel);
const root = document.getElementById("app");
const state = { user: null, profile: null, watch: null, matches: [], match: null, keys: {}, unread: 0, ops: null, outbox: [], err: "", loading: false };

function icon(name) {
  const paths = {
    inbox: "M3 7h18v12H3zM3 7l9 6 9-6",
    watch: "M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
    profile: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20a8 8 0 0 1 16 0",
    engine: "M12 8v4M8 12h8M7 4h10l3 4-3 4H7L4 8z",
    mail: "M3 6h18v12H3zM3 6l9 7 9-7",
    mark: "M6 22V8h3l5 9 5-9h3v14",
  };
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name] || paths.inbox}"/></svg>`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
    body: opts.body && typeof opts.body !== "string" ? JSON.stringify(opts.body) : opts.body,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2400);
}

function route() {
  const h = (location.hash || "#inbox").replace(/^#/, "");
  const [view, id] = h.split("/");
  return { view: view || "inbox", id };
}

function go(h) {
  location.hash = h;
}

window.addEventListener("hashchange", () => paint());

async function boot() {
  try {
    const me = await api("/api/auth/me");
    if (me.user) {
      await loadState();
    } else {
      state.user = null;
    }
  } catch {
    state.user = null;
  }
  paint();
}

async function loadState() {
  const s = await api("/api/state");
  state.user = s.user;
  state.profile = s.profile;
  state.watch = s.watch;
  state.keys = s.keys;
  state.unread = s.unread;
}

function paint() {
  if (!state.user) {
    root.innerHTML = landing();
    bindLanding();
    return;
  }
  const r = route();
  root.innerHTML = shell(r);
  bindShell(r);
  loadView(r);
}

function landing() {
  return `
  <div class="landing">
    <header class="topbar">
      <div class="mark">${icon("mark")} WorkDey</div>
      <a class="btn ghost small" href="/download/engine.zip">Download engine</a>
    </header>
    <section class="hero">
      <div>
        <p class="eyebrow">Smart Match & Apply</p>
        <h1>We watch the apps. You only open the ones that fit.</h1>
        <p class="lede">Job posts now land on LinkedIn, X, and Instagram first. WorkDey checks them against your skills on a schedule you choose, emails you a short note, and drafts the reply, cover letter, and CV so applying takes minutes.</p>
        <div class="hero-actions">
          <button class="btn" id="try-demo">Try the demo inbox</button>
          <a class="btn ghost" href="#signup">Create a profile</a>
        </div>
      </div>
      <form class="panel" id="auth-form">
        <div class="tabs">
          <button type="button" class="on" data-tab="login">Log in</button>
          <button type="button" data-tab="signup">Sign up</button>
        </div>
        <div class="stack">
          <label class="field"><span>Name</span><input name="name" placeholder="Adaeze Okonkwo" class="signup-only" style="display:none" /></label>
          <label class="field"><span>Email</span><input name="email" type="email" required placeholder="you@mail.com" /></label>
          <label class="field"><span>Password</span><input name="password" type="password" required minlength="8" placeholder="8+ characters" /></label>
          <p class="err" id="auth-err"></p>
          <button class="btn" type="submit" id="auth-go">Log in</button>
          <p class="muted">Demo: blessing@workdey.app · WorkDey2026!</p>
        </div>
      </form>
    </section>
    <section class="stats">
      <div class="stat"><b>3 / 5 / 24h</b><span>Watch cadence you pick</span></div>
      <div class="stat"><b>≤ 5 lines</b><span>Emails stay short. One match, one reason, one tap.</span></div>
      <div class="stat"><b>X · LI · IG</b><span>Apify adapters, kill-switch per source</span></div>
    </section>
  </div>`;
}

function bindLanding() {
  let mode = "login";
  const form = $("#auth-form");
  form.querySelectorAll("[data-tab]").forEach((b) => {
    b.onclick = () => {
      mode = b.dataset.tab;
      form.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
      form.querySelector(".signup-only").style.display = mode === "signup" ? "block" : "none";
      $("#auth-go").textContent = mode === "signup" ? "Create account" : "Log in";
    };
  });
  $("#try-demo").onclick = async () => {
    try {
      await api("/api/auth/demo", { method: "POST", body: {} });
      await loadState();
      location.hash = "inbox";
      paint();
    } catch (e) {
      $("#auth-err").textContent = e.message;
    }
  };
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    const body = { email: fd.get("email"), password: fd.get("password"), name: fd.get("name") };
    try {
      await api(mode === "signup" ? "/api/auth/signup" : "/api/auth/login", { method: "POST", body });
      if (mode === "signup") toast("Check your inbox — WorkDey just emailed you. Match alerts will come from the same name.");
      await loadState();
      location.hash = mode === "signup" ? "profile" : "inbox";
      paint();
    } catch (e) {
      $("#auth-err").textContent = e.message;
    }
  };
}

function shell(r) {
  const items = [
    ["inbox", "inbox", "Match inbox"],
    ["profile", "profile", "Profile"],
    ["watch", "watch", "Watch"],
    ["engine", "engine", "Engine"],
    ["outbox", "mail", "Outbox"],
  ];
  return `
  <div class="shell">
    <aside class="nav">
      <div class="mark">${icon("mark")} WorkDey</div>
      <nav>
        ${items.map(([id, ic, label]) => `<a href="#${id}" class="${r.view === id || (r.view === "match" && id === "inbox") ? "on" : ""}">${icon(ic)} ${label}${id === "inbox" && state.unread ? ` · ${state.unread}` : ""}</a>`).join("")}
      </nav>
      <div class="grow muted" style="font-size:12px">
        ${(state.user && state.user.name) || ""}<br/>
        <button class="linkish" id="logout" style="padding:8px 0;color:var(--fg-muted)">Sign out</button>
      </div>
    </aside>
    <main class="main" id="view"></main>
  </div>`;
}

function bindShell() {
  const out = $("#logout");
  if (out) out.onclick = async () => {
    await api("/api/auth/logout", { method: "POST", body: {} });
    state.user = null;
    paint();
  };
}

async function loadView(r) {
  const view = $("#view");
  if (r.view === "profile") return renderProfile(view);
  if (r.view === "watch") return renderWatch(view);
  if (r.view === "engine") return renderEngine(view);
  if (r.view === "outbox") return renderOutbox(view);
  if (r.view === "match" && r.id) return renderMatch(view, r.id);
  return renderInbox(view);
}

function srcChip(s) {
  const label = { x: "X", linkedin: "LinkedIn", instagram: "Instagram", workdey: "WorkDey" }[s] || s;
  return `<span class="chip ${s}">${label}</span>`;
}

async function renderInbox(view) {
  view.innerHTML = `<div class="page-head"><div><h1>Match inbox</h1><p>Short cards. One reason. Open a match to draft a reply.</p></div><button class="btn" id="run-now">Run Watch now</button></div><div class="list" id="cards"><p class="muted">Loading…</p></div>`;
  $("#run-now").onclick = async () => {
    $("#run-now").disabled = true;
    try {
      const r = await api("/api/watch/run", { method: "POST", body: {} });
      toast(`${r.matches} new match${r.matches === 1 ? "" : "es"}`);
      await loadState();
      renderInbox(view);
    } catch (e) {
      toast(e.message);
    } finally {
      $("#run-now").disabled = false;
    }
  };
  const data = await api("/api/matches");
  state.matches = data.matches;
  const el = $("#cards");
  if (!data.matches.length) {
    el.innerHTML = `<div class="empty"><p>Nothing yet. Complete your profile, turn Watch on, then run it.</p></div>`;
    return;
  }
  el.innerHTML = data.matches.map((m) => `
    <a class="card" href="#match/${m.id}">
      <div class="row">
        <h3>${esc(m.opportunity.title)}</h3>
        <span class="score">${Math.round(m.fit_score * 100)}</span>
      </div>
      <div class="meta">${srcChip(m.opportunity.source)} <span>${esc(m.opportunity.author_name || "")}</span> <span>${esc(m.opportunity.location || "")}</span> <span class="chip">${m.status}</span></div>
      <p class="why">${esc((m.fit_reasons || [])[0] || "Related to your profile.")}</p>
    </a>`).join("");
}

async function renderMatch(view, id) {
  view.innerHTML = `<p class="muted">Opening match…</p>`;
  const data = await api(`/api/matches/${id}`);
  const m = data.match;
  const o = m.opportunity;
  const formal = m.pack === "formal";
  view.innerHTML = `
    <div class="detail">
      <div class="page-head">
        <div>
          <p class="eyebrow"><a href="#inbox" style="color:inherit">Inbox</a> / match</p>
          <h1>${esc(o.title)}</h1>
          <p class="meta">${srcChip(o.source)} ${esc(o.author_name || o.author_handle)} · ${esc(o.location || "Location unknown")}</p>
        </div>
        <div class="actions">
          <button class="btn ghost small" data-st="applied">Mark applied</button>
          <button class="btn ghost small" data-st="dismissed">Not for me</button>
          <button class="btn danger small" data-st="spam">Spam</button>
        </div>
      </div>
      <div class="split">
        <article class="post">
          <p class="eyebrow">Why it fits</p>
          ${(m.fit_reasons || []).map((r) => `<p>${esc(r)}</p>`).join("") || "<p class='muted'>Related to your profile.</p>"}
          <p class="eyebrow" style="margin-top:20px">The post</p>
          <p class="body">${esc(o.body)}</p>
          ${o.external_url ? `<p style="margin-top:16px"><a class="btn ghost small" href="${esc(o.external_url)}" target="_blank" rel="noopener">Open original</a></p>` : ""}
        </article>
        <section class="studio">
          <p class="eyebrow">AI studio · draft only</p>
          <h2 style="margin-bottom:8px">${formal ? "Official pack" : "Post pack"}</h2>
          <p class="muted" style="margin-bottom:16px">${formal
            ? "This looks official — start with a cover letter and a tightened CV. A short reply is available if you would rather DM."
            : "This looks like a post, not a portal. Start with a short reply. Cover letter is optional."}</p>
          <div class="actions" style="margin-bottom:12px">
            <button class="btn ${formal ? "ghost" : ""} small" data-kind="reply">Suggest reply</button>
            <button class="btn ${formal ? "" : "ghost"} small" data-kind="cover">Cover letter</button>
            <button class="btn ${formal ? "" : "ghost"} small" data-kind="cv">Revamp CV</button>
          </div>
          <label class="field"><span>Regenerate note</span><input id="note" placeholder="more concise, mention NYSC" /></label>
          <textarea id="draft" placeholder="Drafts appear here. Edit before you send.">${esc((m.drafts[0] && m.drafts[0].body) || "")}</textarea>
          <div class="facts" id="facts">${(m.drafts[0] && (m.drafts[0].facts_used || []).map((f) => `<span class="chip on">${esc(f)}</span>`).join("")) || ""}</div>
          <div class="actions" style="margin-top:12px">
            <button class="btn ghost small" id="copy">Copy</button>
            <a class="btn ghost small" id="pdf" href="#">Download PDF</a>
          </div>
          <p class="muted" style="margin-top:12px">Draft only. Check every date, title, and company before you send.</p>
        </section>
      </div>
    </div>`;
  let kind = m.drafts[0] ? m.drafts[0].kind : formal ? "cover" : "reply";
  const setPdf = () => { $("#pdf").href = `/api/matches/${id}/pdf/${kind}`; };
  setPdf();
  view.querySelectorAll("[data-kind]").forEach((b) => {
    b.onclick = async () => {
      kind = b.dataset.kind;
      b.disabled = true;
      try {
        const out = await api(`/api/matches/${id}/generate`, { method: "POST", body: { kind, note: $("#note").value } });
        $("#draft").value = out.draft.body;
        $("#facts").innerHTML = (out.draft.facts_used || []).map((f) => `<span class="chip on">${esc(f)}</span>`).join("");
        setPdf();
        if (out.draft.fallback) toast("Template draft — add an xAI key for Grok");
        if (out.draft.refused) toast("WorkDey refused to draft this one");
      } catch (e) {
        toast(e.message);
      } finally {
        b.disabled = false;
      }
    };
  });
  view.querySelectorAll("[data-st]").forEach((b) => {
    b.onclick = async () => {
      await api(`/api/matches/${id}/status`, { method: "POST", body: { status: b.dataset.st } });
      toast(b.dataset.st === "applied" ? "Marked applied" : "Noted");
      go("inbox");
    };
  });
  $("#copy").onclick = async () => {
    await navigator.clipboard.writeText($("#draft").value);
    toast("Copied");
  };
}

function renderProfile(view) {
  const p = state.profile || {};
  view.innerHTML = `
    <div class="page-head"><div><h1>Profile</h1><p>Skills, education, target roles. Matching runs at 40% complete.</p></div>
      <div style="min-width:160px"><div class="bar"><i style="width:${p.completeness || 0}%"></i></div><p class="muted">${p.completeness || 0}% complete</p></div>
    </div>
    <form class="stack" id="pf" style="max-width:640px">
      <label class="field"><span>Name</span><input name="name" value="${esc(state.user.name || "")}" /></label>
      <label class="field"><span>Target roles (comma, max 3)</span><input name="target_roles" value="${esc((p.target_roles || []).join(", "))}" placeholder="Data Analyst, Accountant" /></label>
      <label class="field"><span>Skills as tags (comma)</span><input name="skills_tags" value="${esc((p.skills_tags || []).join(", "))}" /></label>
      <label class="field"><span>Skills as text</span><textarea name="skills_text">${esc(p.skills_text || "")}</textarea></label>
      <label class="field"><span>Education</span><input name="education" value="${esc(p.education || "")}" placeholder="BSc Accounting, UNILAG · NYSC completed" /></label>
      <div class="grid-2">
        <label class="field"><span>Years</span><input name="years_experience" type="number" min="0" max="40" value="${p.years_experience || 0}" /></label>
        <label class="field"><span>Seniority</span>
          <select name="seniority">${["intern", "junior", "mid", "senior"].map((s) => `<option ${p.seniority === s ? "selected" : ""}>${s}</option>`).join("")}</select>
        </label>
      </div>
      <div class="grid-2">
        <label class="field"><span>Locations</span><input name="locations" value="${esc((p.locations || []).join(", "))}" placeholder="Lagos, Remote" /></label>
        <label class="field"><span>Work type</span>
          <select name="work_type">${["either", "full-time", "gig"].map((s) => `<option ${p.work_type === s ? "selected" : ""}>${s}</option>`).join("")}</select>
        </label>
      </div>
      <label class="field"><span>Summary</span><textarea name="summary">${esc(p.summary || "")}</textarea></label>
      <button class="btn" type="submit">Save profile</button>
    </form>
    <form id="cv" style="margin-top:28px;max-width:640px" class="stack">
      <p class="eyebrow">CV upload</p>
      <input type="file" name="file" accept=".pdf,.docx,.doc,.txt" />
      <button class="btn ghost" type="submit">Extract skills from CV</button>
      <p class="muted">${p.has_cv ? "A CV is on file." : "PDF or DOCX. We never invent employers from this."}</p>
    </form>`;
  $("#pf").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    const body = Object.fromEntries(fd.entries());
    body.target_roles = split(body.target_roles).slice(0, 3);
    body.skills_tags = split(body.skills_tags);
    body.locations = split(body.locations);
    body.years_experience = Number(body.years_experience);
    await api("/api/profile", { method: "POST", body });
    await loadState();
    toast("Profile saved");
    renderProfile(view);
  };
  $("#cv").onsubmit = async (ev) => {
    ev.preventDefault();
    const file = ev.target.file.files[0];
    if (!file) return toast("Choose a file");
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/profile/cv", { method: "POST", body: fd, credentials: "include" });
    const data = await res.json();
    if (!res.ok) return toast(data.error || "upload failed");
    await loadState();
    toast("CV parsed");
    renderProfile(view);
  };
}

function renderWatch(view) {
  const w = state.watch || {};
  const cadence = w.cadence_hours || 24;
  view.innerHTML = `
    <div class="page-head"><div><h1>Watch</h1><p>Tell us how often to look. We email you only when something actually fits.</p></div>
      <button class="switch ${w.enabled ? "on" : ""}" id="en" aria-label="Watch on"><i></i></button>
    </div>
    <div class="stack" style="max-width:640px">
      <p class="eyebrow">Cadence</p>
      <div class="actions" id="cad">
        ${[3, 5, 24].map((h) => `<button class="btn ${cadence === h ? "" : "ghost"} small" data-h="${h}">Every ${h} hour${h === 1 ? "" : "s"}</button>`).join("")}
      </div>
      <div class="grid-2">
        <label class="field"><span>Quiet start (WAT)</span><input id="qs" type="time" value="${w.quiet_start || "21:00"}" /></label>
        <label class="field"><span>Quiet end (WAT)</span><input id="qe" type="time" value="${w.quiet_end || "07:00"}" /></label>
      </div>
      <label class="field" style="flex-direction:row;align-items:center;gap:12px">
        <button class="switch ${w.email_on ? "on" : ""}" id="em"><i></i></button>
        <span>Email alerts</span>
      </label>
      <p class="eyebrow">Sources</p>
      <div class="actions" id="src">
        ${["workdey", "x", "linkedin", "instagram"].map((s) => {
          const on = (w.sources || {})[s] !== false;
          return `<button class="btn ${on ? "" : "ghost"} small" data-s="${s}">${s}</button>`;
        }).join("")}
      </div>
      <p class="muted">Next run: ${w.next_run_at ? new Date(w.next_run_at).toLocaleString() : "off"} · Last: ${w.last_run_at ? new Date(w.last_run_at).toLocaleString() : "never"}</p>
      <p class="muted">Cap: 3 emails a day unless you opt into every match.</p>
    </div>`;
  const save = async (patch) => {
    await api("/api/watch", { method: "POST", body: patch });
    await loadState();
    renderWatch(view);
  };
  $("#en").onclick = () => save({ enabled: !w.enabled });
  $("#em").onclick = () => save({ email_on: !w.email_on });
  view.querySelectorAll("#cad [data-h]").forEach((b) => {
    b.onclick = () => save({ cadence_hours: Number(b.dataset.h) });
  });
  $("#qs").onchange = () => save({ quiet_start: $("#qs").value });
  $("#qe").onchange = () => save({ quiet_end: $("#qe").value });
  const sources = { ...(w.sources || {}) };
  view.querySelectorAll("#src [data-s]").forEach((b) => {
    b.onclick = () => {
      sources[b.dataset.s] = !b.classList.contains("btn") || b.classList.contains("ghost");
      // toggle current
      const next = { ...sources };
      next[b.dataset.s] = (w.sources || {})[b.dataset.s] === false;
      save({ sources: { ...(w.sources || {}), [b.dataset.s]: (w.sources || {})[b.dataset.s] === false } });
    };
  });
}

async function renderEngine(view) {
  view.innerHTML = `<div class="page-head"><div><h1>Engine</h1><p>Scheduler, pinger, source kill-switches. First-party jobs keep running if a network dies.</p></div>
    <div class="actions">
      <button class="btn small" id="ingest">Harvest now</button>
      <button class="btn ghost small" id="matchall">Match due watches</button>
    </div>
  </div><div id="ops"><p class="muted">Reading heartbeats…</p></div>`;
  $("#ingest").onclick = async () => {
    toast("Harvest started");
    await api("/api/ops/ingest", { method: "POST", body: {} });
    renderEngine(view);
  };
  $("#matchall").onclick = async () => {
    const r = await api("/api/ops/match", { method: "POST", body: {} });
    toast(`${r.matches || 0} matches`);
    renderEngine(view);
  };
  const h = await api("/api/ops/health");
  const beats = h.heartbeats || {};
  const keys = h.keys || {};
  $("#ops").innerHTML = `
    <div class="stats">
      <div class="stat"><b><span class="pulse ${h.scheduler.running ? "" : "off"}"></span> ${h.scheduler.running ? "live" : "down"}</b><span>Scheduler</span></div>
      <div class="stat"><b>${keys.apify ? "on" : "off"}</b><span>Apify token</span></div>
      <div class="stat"><b>${keys.brevo ? "on" : "off"}</b><span>Brevo mail</span></div>
    </div>
    <p class="muted">Grok drafts: ${keys.xai ? "xAI connected" : "template fallback until XAI_API_KEY is set"}</p>
    <table class="table">
      <thead><tr><th>Job</th><th>OK</th><th>Last beat</th></tr></thead>
      <tbody>
        ${Object.entries(beats).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.ok ? "yes" : "no"}</td><td>${v.at ? new Date(v.at).toLocaleString() : "—"}</td></tr>`).join("") || `<tr><td colspan="3">Pinger has not ticked yet.</td></tr>`}
      </tbody>
    </table>
    <p class="eyebrow" style="margin-top:24px">Source runs</p>
    <table class="table">
      <thead><tr><th>Source</th><th>Status</th><th>In / kept</th><th>Kill</th></tr></thead>
      <tbody>
        ${(h.runs || []).map((r) => `<tr><td>${esc(r.source)}</td><td>${esc(r.status)}</td><td>${r.in} / ${r.kept}</td><td></td></tr>`).join("") || `<tr><td colspan="4">No harvests yet. First-party WorkDey jobs are already seeded.</td></tr>`}
      </tbody>
    </table>
    <div class="actions" style="margin-top:16px">
      ${["x", "linkedin", "linkedin_posts", "instagram", "workdey"].map((s) => {
        const killed = (h.kills || {})[s] === "1";
        return `<button class="btn ${killed ? "danger" : "ghost"} small" data-kill="${s}">${killed ? "Enable" : "Kill"} ${s}</button>`;
      }).join("")}
    </div>
    <p class="muted" style="margin-top:16px">Drop APIFY_API_TOKEN and BREVO_API_KEY in .env on your server. Harvest uses apidojo/twitter-scraper-lite, curious_coder/linkedin-jobs-scraper, supreme_coder/linkedin-post, apify/instagram-scraper.</p>
    <p><a class="btn ghost small" href="/download/engine.zip">Download the extractable engine</a></p>
  `;
  view.querySelectorAll("[data-kill]").forEach((b) => {
    b.onclick = async () => {
      const src = b.dataset.kill;
      const killed = (h.kills || {})[src] !== "1";
      await api("/api/ops/kill", { method: "POST", body: { source: src, killed } });
      renderEngine(view);
    };
  });
}

async function renderOutbox(view) {
  view.innerHTML = `<div class="page-head"><div><h1>Outbox</h1><p>If Brevo is not keyed yet, alerts land here so you can still see the short email.</p></div></div><div id="ob"><p class="muted">Loading…</p></div>`;
  const data = await api("/api/ops/outbox");
  if (!data.emails.length) {
    $("#ob").innerHTML = `<div class="empty">No emails yet. Run Watch on a complete profile.</div>`;
    return;
  }
  $("#ob").innerHTML = `<div class="list">${data.emails.map((e) => `
    <article class="card">
      <div class="row"><h3>${esc(e.subject)}</h3><span class="chip">${esc(e.status)}</span></div>
      <p class="muted">${esc(e.to)} · ${e.created_at ? new Date(e.created_at).toLocaleString() : ""}</p>
      <p class="why">${esc(e.text || "").slice(0, 280)}</p>
    </article>`).join("")}</div>`;
}

function split(s) {
  return String(s || "").split(",").map((x) => x.trim()).filter(Boolean);
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => {
    if (c === "&") return "\u0026amp;";
    if (c === "<") return "\u0026lt;";
    if (c === ">") return "\u0026gt;";
    if (c === '"') return "\u0026quot;";
    return "\u0026#39;";
  });
}

boot();
