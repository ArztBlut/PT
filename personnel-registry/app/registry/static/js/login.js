"use strict";

(function () {
  const form = document.getElementById("login-form");
  const error = document.getElementById("login-error");
  const button = form.querySelector("button[type=submit]");

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const username = form.elements.username.value.trim();
    const password = form.elements.password.value;
    if (!username || !password) {
      showError("Enter your username and password.");
      return;
    }
    button.disabled = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (res.ok) {
        window.location.assign("/");
        return;
      }
      const data = await res.json().catch(() => ({}));
      showError(typeof data.detail === "string" ? data.detail : "Sign-in failed. Try again.");
      form.elements.password.select();
    } catch {
      showError("Can't reach the server. Check that the container is running.");
    } finally {
      button.disabled = false;
    }
  });
})();
