(() => {
  const toggle = document.getElementById("chat-toggle");
  const panel = document.getElementById("chat-panel");
  const close = document.getElementById("chat-close");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");
  const send = document.getElementById("chat-send");
  if (!toggle || !panel || !form || !input || !messages || !send) return;

  const history = [];
  function addMessage(text, role, isError = false) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble " + (isError ? "error" : role);
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }
  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) input.focus();
  }
  toggle.addEventListener("click", () => setOpen(panel.hidden));
  close?.addEventListener("click", () => setOpen(false));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || send.disabled) return;
    addMessage(message, "user");
    input.value = "";
    history.push({ role: "user", content: message });
    const waiting = addMessage("Thinking…", "bot");
    send.disabled = true;
    input.disabled = true;
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: history.slice(-8, -1) })
      });
      const data = await response.json().catch(() => ({}));
      waiting.remove();
      if (!response.ok) {
        addMessage(data.error || "I could not answer right now. Please try again.", "bot", true);
        history.pop();
        return;
      }
      const answer = String(data.reply || "I didn't receive a response.");
      addMessage(answer, "bot");
      history.push({ role: "assistant", content: answer });
      if (history.length > 10) history.splice(0, history.length - 10);
    } catch (_error) {
      waiting.remove();
      addMessage("Connection problem. Check your internet connection and try again.", "bot", true);
      history.pop();
    } finally {
      send.disabled = false;
      input.disabled = false;
      input.focus();
    }
  });
})();
