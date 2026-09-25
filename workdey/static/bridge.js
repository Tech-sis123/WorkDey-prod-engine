/* Minimal Grok preview host bridge — hash-router guest. */
(function () {
  const CHANNEL = "grok-preview-bridge";
  function isSafe(path) {
    return typeof path === "string" && path.startsWith("/") && !path.startsWith("//") && !path.includes("\\");
  }
  window.addEventListener("message", function (ev) {
    const d = ev.data;
    if (!d || d.channel !== CHANNEL) return;
    if (d.type === "navigate" && isSafe(d.path)) {
      if (d.path.startsWith("/app")) {
        location.hash = d.path.replace(/^\/app\/?/, "") || "inbox";
      } else {
        history.pushState({}, "", d.path);
      }
    }
    if (d.type === "history" && (d.delta === -1 || d.delta === 1)) history.go(d.delta);
  });
})();
