/* Voice of the Stone MVP client. Drives the server state machine:
   onboard(q1 voice-then-buttons, q2 voice-then-buttons) -> capture ->
   processing -> review -> explanation. No recognition runs here. */
const $ = (id) => document.getElementById(id);
const api = async (path, opts = {}) => {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error((await res.text()).slice(0, 200));
  return res.json();
};

let sessionId = null;
let corpus = [];

function show(id) {
  for (const s of ["screen-onboard", "screen-capture", "screen-processing", "screen-review", "screen-explain"]) {
    $(s).hidden = s !== id;
  }
}
function fail(msg) { const e = $("error"); e.textContent = msg; e.hidden = false; }
function note(msg) { const n = $("notice"); n.textContent = msg; n.hidden = !msg; }

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

/* ---- onboarding: one 5s voice window, then buttons only (Q1 ruling) ---- */
async function voiceAttempt(question) {
  const status = $("ob-voice-status");
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const rec = new MediaRecorder(stream);
    const chunks = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    rec.start();
    status.textContent = "Listening for 5 seconds… or tap below.";
    await new Promise((r) => setTimeout(r, 5000));
    rec.stop();
    stream.getTracks().forEach((t) => t.stop());
  } catch {
    status.textContent = "Microphone unavailable — please tap below.";
    return null;
  }
  // MVP: audio posted for shape-compat; stub STT always asks for a tap.
  const data = await api(`/api/sessions/${sessionId}/onboarding`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode: "voice" }),
  });
  return data;
}

async function runQuestion(question, title, options) {
  $("ob-title").textContent = title;
  const box = $("ob-buttons");
  box.innerHTML = "";
  const btns = {};
  for (const [label, value] of options) {
    const b = document.createElement("button");
    b.className = "btn"; b.textContent = label;
    b.onclick = async () => {
      try {
        const data = await api(`/api/sessions/${sessionId}/onboarding`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, mode: "button", value }),
        });
        afterAnswer(question, data);
      } catch (e) { fail(e.message); }
    };
    btns[value] = b;
    box.appendChild(b);
  }
  const heard = await voiceAttempt(question);
  if (heard && heard.guess && btns[heard.guess]) {
    btns[heard.guess].classList.add("guess");
    $("ob-voice-status").textContent = "I think you said “" + heard.guess + "” — tap to confirm.";
  } else {
    $("ob-voice-status").textContent = "Voice window closed — please tap below.";
  }
}

function afterAnswer(question, data) {
  if (question === "q1") {
    runQuestion("q2", "Photo or live camera?", [["Photo upload", "photo"]]);
  } else {
    loadCapture();
  }
}

/* ---- capture ---- */
async function loadCapture() {
  show("screen-capture");
  const data = await api("/api/corpus");
  corpus = data.entries;
  const ul = $("demo-list");
  ul.innerHTML = "";
  for (const e of corpus) {
    const li = document.createElement("li");
    const b = document.createElement("button");
    b.innerHTML = `<span class="t">SII II No. ${e.sii_no} — ${e.king}</span><br>` +
      `<span class="a">${e.location} · Photo: ${e.photo.artist} (${e.photo.license})` +
      (e.translation_partial ? " · partial translation" : "") + "</span>";
    b.onclick = () => submitCapture({ demo_entry: e.id });
    li.appendChild(b);
    ul.appendChild(li);
  }
}

async function submitCapture(form) {
  show("screen-processing");
  note("");
  try {
    let res;
    if (form instanceof FormData) {
      res = await fetch(`/api/sessions/${sessionId}/captures`, { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.text()).slice(0, 200));
      res = await res.json();
    } else {
      const fd = new FormData();
      fd.append("demo_entry", form.demo_entry);
      res = await fetch(`/api/sessions/${sessionId}/captures`, { method: "POST", body: fd })
        .then(async (r) => { if (!r.ok) throw new Error((await r.text()).slice(0, 200)); return r.json(); });
    }
    if (res.failure) {
      note(res.failure.message);
      show("screen-capture");
      return;
    }
    showReport(res.report);
  } catch (e) { fail(e.message); show("screen-capture"); }
}

/* ---- review ---- */
function showReport(report) {
  show("screen-review");
  $("coverage").textContent =
    `I could read ${report.coverage.confident} of ${report.coverage.total} lines confidently.`;
  const ol = $("lines");
  ol.innerHTML = "";
  for (const ln of report.lines) {
    const li = document.createElement("li");
    const body = ln.text
      ? document.createTextNode(ln.text + " ")
      : Object.assign(document.createElement("span"),
        { className: "unread", textContent: "could not read this line " });
    li.appendChild(body);
    const s = document.createElement("span");
    s.className = "score " + ln.status;
    s.textContent = `${ln.status} ${Math.round(ln.calibrated_score * 100)}%`;
    li.appendChild(s);
    ol.appendChild(li);
  }
}

/* ---- explanation ---- */
const TAG_LABEL = { stone: "from the stone", published: "published translation", interpretation: "machine interpretation" };

function showExplanation(data) {
  show("screen-explain");
  const box = $("claims");
  box.innerHTML = "";
  for (const c of data.claims) {
    const div = document.createElement("div");
    div.className = "claim";
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = TAG_LABEL[c.tag] || c.tag;
    div.appendChild(tag);
    div.appendChild(document.createTextNode(c.text));
    box.appendChild(div);
  }
  $("audio-note").textContent = data.audio.status === "stubbed"
    ? "Voice: " + data.audio.detail
    : "";
  note(data.quality_flag === "unverified"
    ? "This language rendering is not yet verified by a native-speaker reviewer."
    : "");
  if (data.recovery) note("Below confidence threshold: " + data.recovery.guidance);
}

async function boot() {
  try {
    const s = await api("/api/sessions", { method: "POST" });
    sessionId = s.session_id;
    $("ob-prompt").textContent = s.prompt;
    runQuestion("q1", "Which language should I speak?", [["தமிழ் (Tamil)", "tamil"], ["Indian English", "english"]]);
  } catch (e) { fail("Could not reach the server: " + e.message); }
}

$("upload-btn").onclick = () => {
  const f = $("photo-input").files[0];
  if (!f) { note("Choose a photo first."); return; }
  const fd = new FormData();
  fd.append("photo", f, f.name);
  submitCapture(fd);
};
$("accept-btn").onclick = async () => {
  const data = await api(`/api/sessions/${sessionId}/decision`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision: "accept" }),
  });
  showExplanation(data);
};
$("recapture-btn").onclick = async () => {
  await api(`/api/sessions/${sessionId}/decision`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision: "recapture" }),
  });
  loadCapture();
};
document.querySelectorAll(".lang-btn").forEach((b) => {
  b.onclick = async () => {
    const data = await api(`/api/sessions/${sessionId}/explain`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: b.dataset.lang }),
    });
    showExplanation(data);
  };
});
$("next-btn").onclick = () => location.reload(); // fresh session, then capture
$("new-btn").onclick = () => location.reload();

boot();
