(() => {
  const list = document.getElementById("messages");
  const form = document.getElementById("send-form");
  const input = document.getElementById("message-input");
  const counter = document.getElementById("counter");
  const button = document.getElementById("send-button");
  const status = document.getElementById("status");
  const csrfToken = document.getElementById("csrf-token").value;
  let lastSignature = "";

  function updateCounter() {
    counter.textContent = `${Array.from(input.value).length}/25`;
  }
  input.addEventListener("input", updateCounter);

  function render(messages) {
    const signature = JSON.stringify(messages);
    if (signature === lastSignature) return;
    const wasNearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 60;
    lastSignature = signature;
    list.replaceChildren();
    for (const message of messages) {
      const li = document.createElement("li");
      li.className = "message";
      const top = document.createElement("div");
      top.className = "message-top";
      const user = document.createElement("span");
      user.className = "message-user";
      user.textContent = message.username;
      const time = document.createElement("span");
      time.className = "message-time";
      time.textContent = message.created_at || "";
      const body = document.createElement("p");
      body.className = "message-body";
      body.textContent = message.body;
      top.append(user, time);
      li.append(top, body);
      list.append(li);
    }
    if (wasNearBottom) list.scrollTop = list.scrollHeight;
  }

  async function loadMessages() {
    try {
      const response = await fetch("/api/messages", { cache: "no-store" });
      if (response.status === 401) {
        location.href = "/login";
        return;
      }
      if (!response.ok) throw new Error("메시지를 불러오지 못했어.");
      render(await response.json());
      status.textContent = "연결됨 · 2초마다 새 메시지 확인";
    } catch (_error) {
      status.textContent = "서버 연결을 확인하는 중…";
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    if (Array.from(body).length > 25) {
      status.textContent = "메시지는 최대 25자까지 보낼 수 있어.";
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch("/api/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ body })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "전송에 실패했어.");
      input.value = "";
      updateCounter();
      await loadMessages();
      input.focus();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  loadMessages();
  setInterval(loadMessages, 2000);
})();
