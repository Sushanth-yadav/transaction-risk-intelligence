const transactionId = "{{ txn.transaction_id }}";
const chatLog = document.getElementById("chat-log");

function appendMessage(role, text) {
    const div = document.createElement("div");
    div.className = "chat-msg";

    const roleDiv = document.createElement("div");
    roleDiv.className = "role";
    roleDiv.textContent = role;

    const messageDiv = document.createElement("div");
    messageDiv.className = "message-content";

    if (role === "RazorGuard") {
        // Convert escaped Markdown back into normal Markdown.
        let markdown = String(text || "")
            .replace(/\\\*\*/g, "**")
            .replace(/\\\*/g, "*")
            .replace(/\\#/g, "#")
            .replace(/\\`/g, "`")
            .replace(/\\_/g, "_");

        // Render Markdown as HTML.
        messageDiv.innerHTML = marked.parse(markdown);
    } else {
        // User messages are always treated as plain text.
        messageDiv.textContent = text || "";
    }

    div.appendChild(roleDiv);
    div.appendChild(messageDiv);

    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
}
async function askAssistant() {
    const input = document.getElementById("chat-input");
    const question = input.value.trim();
    if (!question) return;
    appendMessage("You", question);
    input.value = "";
    appendMessage("RazorGuard", "Thinking...");

    try {
        const resp = await fetch(`/api/investigate/${transactionId}/ask/`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({question}),
        });
        const data = await resp.json();
        chatLog.lastChild.remove();
        appendMessage("RazorGuard", data.answer || "No answer returned.");
    } catch (e) {
        chatLog.lastChild.remove();
        appendMessage("RazorGuard", "Error reaching the investigation assistant.");
    }
}

document.getElementById("chat-input").addEventListener("keydown", function(e) {
    if (e.key === "Enter") askAssistant();
});
