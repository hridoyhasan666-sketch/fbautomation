// Telegram webhook for instant Approve/Reject.
// A tap is answered here in under a second, then GitHub Actions (approve.yml) saves it and schedules on Facebook.
// Secrets (wrangler secret put): TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, WEBHOOK_SECRET, GITHUB_TOKEN
// Var (wrangler.toml): GITHUB_REPO = "owner/repo"

const tg = (env, method, body) =>
  fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET)
      return new Response("forbidden", { status: 403 });

    const update = await request.json().catch(() => ({}));
    const q = update.callback_query;
    if (!q) return new Response("ok");

    if (String(q.from?.id) !== String(env.TELEGRAM_ADMIN_CHAT_ID)) {
      await tg(env, "answerCallbackQuery", { callback_query_id: q.id, text: "Not allowed." });
      return new Response("ok");
    }

    const [action, postId] = (q.data || "").split(":");
    if (!["approve", "reject", "rewrite"].includes(action) || !/^post-[A-Za-z0-9]+$/.test(postId || "")) {
      await tg(env, "answerCallbackQuery", { callback_query_id: q.id, text: "Unknown button." });
      return new Response("ok");
    }

    const gh = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GITHUB_TOKEN}`,
        accept: "application/vnd.github+json",
        "user-agent": "telegram-approval-worker",
      },
      body: JSON.stringify({ event_type: "telegram-tap", client_payload: { action, post_id: postId } }),
    });

    if (!gh.ok) {
      const err = `Could not reach GitHub (${gh.status}). Tap again in a minute.`;
      await tg(env, "answerCallbackQuery", { callback_query_id: q.id, text: err, show_alert: true });
      return new Response("ok");
    }

    const label = action === "approve" ? "✅ Approved — scheduling on Facebook now…" : "❌ Rejected.";
    await tg(env, "answerCallbackQuery", { callback_query_id: q.id, text: label });
    const msg = q.message || {};
    if (msg.message_id) {
      // Replace the buttons with the decision so it can't be tapped twice.
      await tg(env, "editMessageText", {
        chat_id: msg.chat.id,
        message_id: msg.message_id,
        text: `${msg.text || ""}\n\nSTATUS: ${label}`.slice(0, 4096),
      });
    }
    return new Response("ok");
  },
};
