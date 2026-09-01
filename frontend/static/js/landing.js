const form = document.getElementById("start-form");
const promptEl = document.getElementById("prompt");
const btn = document.getElementById("start-btn");
const errorEl = document.getElementById("error");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorEl.hidden = true;
  btn.disabled = true;
  btn.textContent = "Starting...";

  try {
    const res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: promptEl.value }),
    });
    if (!res.ok) throw new Error("Could not start. Try again.");
    const data = await res.json();

    sessionStorage.setItem("aividgen_lead_id", data.lead_id);
    sessionStorage.setItem("aividgen_job_id", data.job_id);
    sessionStorage.setItem("aividgen_first_message", data.first_message);

    window.location.href = "/chat.html";
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
    btn.disabled = false;
    btn.textContent = "Start my video";
  }
});
