const leadId = sessionStorage.getItem("aividgen_lead_id");
const jobId = sessionStorage.getItem("aividgen_job_id");
const firstMessage = sessionStorage.getItem("aividgen_first_message");

if (!leadId || !jobId) {
  window.location.href = "/index.html";
}

const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-text");
const resultEl = document.getElementById("result");
const resultVideo = document.getElementById("result-video");
const fallbackNote = document.getElementById("fallback-note");

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
}

if (firstMessage) addMessage("assistant", firstMessage);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;

  addMessage("user", text);
  input.value = "";
  input.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id: leadId, message: text }),
    });
    const data = await res.json();
    addMessage("assistant", data.reply);

    if (data.done) {
      form.hidden = true;
      pollForVideo();
    }
  } finally {
    input.disabled = false;
    input.focus();
  }
});

async function pollForVideo() {
  addMessage("assistant", "Give me a moment while I finish rendering your video...");

  const maxAttempts = 40; // ~2 minutes at 3s interval
  for (let i = 0; i < maxAttempts; i++) {
    const res = await fetch(`/api/status/${jobId}`);
    const data = await res.json();

    if (data.status === "done" && data.video_url) {
      resultVideo.src = data.video_url;
      fallbackNote.hidden = !data.used_fallback;
      resultEl.hidden = false;
      resultVideo.scrollIntoView({ behavior: "smooth" });
      return;
    }
    if (data.status === "failed") {
      addMessage("assistant", "Sorry, something went wrong on our end. Our team will follow up with you directly.");
      return;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  addMessage("assistant", "This is taking longer than expected. We'll send your video as soon as it's ready.");
}

document.getElementById("pay-full").addEventListener("click", () => {
  alert("Payment flow not wired up yet - this is where checkout would open.");
});
document.getElementById("pay-more").addEventListener("click", () => {
  alert("Payment flow not wired up yet - this is where checkout would open.");
});
