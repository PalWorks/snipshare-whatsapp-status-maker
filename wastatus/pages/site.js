/* SnipShare's public pages: which buttons show for a signed-in visitor, Google
   sign-in, and the request access form. No framework and no build: three small
   jobs on pages that are mostly words. */

const page = document.body.dataset.page;
const CLIENT_ID = document.body.dataset.clientId || "";
const SITEKEY = document.body.dataset.sitekey || "";
const GOOGLE_KEY = "snipshare.google";   // a sign-in carried from Sign in to Request access

const $ = (id) => document.getElementById(id);
const show = (element, on = true) => { if (element) element.hidden = !on; };

/* Signed in or not decides which of a pair of buttons is on the page. */
const signedIn = document.body.dataset.signedIn === "1";
document.querySelectorAll("[data-when]").forEach((element) => {
  show(element, (element.dataset.when === "signed-in") === signedIn);
});
/* A footer link whose address is not set on this server is not drawn at all. */
document.querySelectorAll("[data-optional]").forEach((element) => {
  if (!element.dataset.optional) element.remove();
});

async function call(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SnipShare": "1" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout ? AbortSignal.timeout(30000) : undefined,
    });
  } catch (error) {
    throw new Error(error && error.name === "TimeoutError"
      ? "The connection is too slow right now. Try again"
      : "Could not reach SnipShare. Check the connection and try again");
  }
  let payload = {};
  try { payload = await response.json(); } catch { /* an empty answer */ }
  if (!response.ok) {
    throw new Error(payload.error || `something went wrong (${response.status}). Try again`);
  }
  return payload;
}

/* Where to go after signing in: only ever a plain path on this site. Anything
   else, `//host` and `/\host` included, which browsers read as another site,
   goes to the page. */
function next() {
  const asked = new URLSearchParams(location.search).get("next") || "/app";
  return /^\/[A-Za-z0-9_-]*$/.test(asked) ? asked : "/app";
}

/* The name and address in a Google credential, for showing them back to the
   person. The server checks the credential itself; this only reads it. */
function readCredential(credential) {
  try {
    const part = credential.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const text = decodeURIComponent(atob(part).split("").map(
      (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join(""));
    const claims = JSON.parse(text);
    return { email: claims.email || "", name: claims.name || "" };
  } catch {
    return { email: "", name: "" };
  }
}

function busy(button, label) {
  // The button keeps its width while its label changes.
  button.style.minWidth = `${button.offsetWidth}px`;
  button.dataset.label = button.textContent;
  button.textContent = label;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
}

function idle(button) {
  button.textContent = button.dataset.label || button.textContent;
  button.disabled = false;
  button.removeAttribute("aria-busy");
}

/* Google's script arrives on its own time. */
function whenGoogle(ready) {
  const error = $("google-error");
  if (!CLIENT_ID) {
    error.textContent = "Google sign-in is not set up on this server yet.";
    return show(error);
  }
  let waited = 0;
  const tick = () => {
    if (window.google && google.accounts && google.accounts.id) return ready(google.accounts.id);
    waited += 200;
    if (waited > 15000) {
      error.textContent = "Google sign-in did not load. Check the connection and reload "
        + "the page; an ad or tracker blocker can also stop it.";
      return show(error);
    }
    setTimeout(tick, 200);
  };
  tick();
}

function googleButton(id, text, callback) {
  id.initialize({ client_id: CLIENT_ID, callback, ux_mode: "popup",
                  auto_select: false, itp_support: true });
  const holder = $("google-button");
  const draw = () => {
    const dark = document.documentElement.dataset.theme === "dark"
      || (document.documentElement.dataset.theme !== "light"
          && matchMedia("(prefers-color-scheme: dark)").matches);
    holder.textContent = "";
    // Google's own dark button on a dark page, its light one on a light page, and
    // a pill like the rest of this site's controls.
    id.renderButton(holder, {
      type: "standard", size: "large", text, shape: "pill",
      theme: dark ? "filled_black" : "outline",
      width: Math.min(holder.clientWidth || 320, 400),
    });
  };
  draw();
  // The theme switched in the header, or by the system: the button follows.
  document.addEventListener("snipshare:theme", draw);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
}

/* ── Sign in ─────────────────────────────────────────────── */

function signinPage() {
  const message = $("message");
  const say = (text, tone = "") => {
    message.textContent = text;
    message.className = `notice${tone ? ` notice--${tone}` : ""}`;
    show(message);
  };
  if (signedIn) {
    say("You are already signed in.");
    location.replace(next());
    return;
  }
  whenGoogle((id) => googleButton(id, "signin_with", async ({ credential }) => {
    show($("unknown"), false);
    say("Signing you in...");
    let answer;
    try {
      answer = await call("/api/session", { credential });
    } catch (error) {
      return say(error.message, "error");
    }
    if (answer.status === "approved") {
      say("Signed in. Opening SnipShare...");
      return location.assign(next());
    }
    if (answer.status === "pending") {
      return say("Your request is with the operator. You can sign in once it is approved.",
                 "warn");
    }
    if (answer.status === "unknown") {
      try {
        sessionStorage.setItem(GOOGLE_KEY, JSON.stringify({ credential }));
      } catch { /* private mode: the form will ask again */ }
      say(`There is no request from ${answer.email} yet.`, "warn");
      return show($("unknown"));
    }
    say("This account does not have access to SnipShare.", "error");
  }));
}

/* ── Request access ──────────────────────────────────────── */

function signupPage() {
  const form = $("signup-form");
  const fields = { name: $("name"), email: $("email") };
  let credential = "";
  let turnstileToken = "";

  function useGoogle(found) {
    const { email, name } = readCredential(found);
    if (!email) return;
    credential = found;
    $("google-email").textContent = email;
    fields.email.value = email;
    fields.email.readOnly = true;
    if (!fields.name.value) fields.name.value = name;
    show($("google-done"));
    show($("google-button"), false);
    show($("or"), false);
    clearError("email");
    $("use").focus({ preventScroll: true });
  }

  $("google-undo").addEventListener("click", () => {
    credential = "";
    fields.email.readOnly = false;
    fields.email.value = "";
    show($("google-done"), false);
    show($("google-button"));
    show($("or"));
    try { sessionStorage.removeItem(GOOGLE_KEY); } catch { /* fine */ }
    fields.email.focus();
  });

  // Carried over from Sign in, where Google said this address has not asked yet.
  try {
    const carried = JSON.parse(sessionStorage.getItem(GOOGLE_KEY) || "null");
    if (carried && carried.credential) useGoogle(carried.credential);
  } catch { /* nothing carried */ }

  whenGoogle((id) => googleButton(id, "signup_with", ({ credential: found }) => useGoogle(found)));

  let turnstileMissing = false;
  if (SITEKEY) {
    let waited = 0;
    const start = () => {
      // Not `window.turnstile` alone: an element with that id would answer to it.
      if (!(window.turnstile && typeof window.turnstile.render === "function")) {
        waited += 200;
        if (waited > 15000) {
          // Blocked or not reachable: say so once, rather than "wait a moment" forever.
          turnstileMissing = true;
          return setError("form", "The check that you are a person did not load. Check the "
            + "connection and reload the page; an ad or tracker blocker can also stop it.");
        }
        return setTimeout(start, 200);
      }
      turnstile.render("#human-check", {
        sitekey: SITEKEY,
        callback: (token) => { turnstileToken = token; clearError("form"); },
        "expired-callback": () => { turnstileToken = ""; },
        "error-callback": () => { turnstileToken = ""; },
      });
    };
    start();
  } else {
    show($("human-check"), false);
  }

  function setError(key, text) {
    const box = $(`${key}-error`);
    box.textContent = text;
    show(box);
    if (fields[key]) fields[key].setAttribute("aria-invalid", "true");
  }
  function clearError(key) {
    show($(`${key}-error`), false);
    if (fields[key]) fields[key].removeAttribute("aria-invalid");
  }
  Object.keys(fields).forEach((key) =>
    fields[key].addEventListener("input", () => clearError(key)));

  function valid() {
    let ok = true;
    fields.name.value = fields.name.value.trim();
    fields.email.value = fields.email.value.trim().toLowerCase();
    if (!fields.name.value) { setError("name", "Say your name, so the operator knows who is asking."); ok = false; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email.value)) {
      setError("email", "That does not look like an email address. Check it, for example name@example.com.");
      ok = false;
    }
    if (!ok) (fields.name.getAttribute("aria-invalid") ? fields.name : fields.email).focus();
    return ok;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError("form");
    if (!valid()) return;
    if (SITEKEY && !turnstileToken) {
      return setError("form", turnstileMissing
        ? "The check that you are a person did not load. Reload the page, with any ad "
          + "or tracker blocker paused for this site, then send again."
        : "Wait a moment for the check above that you are a person, then send again.");
    }
    const button = $("submit");
    busy(button, "Sending...");
    let answer;
    try {
      answer = await call("/api/signup", {
        credential, name: fields.name.value, email: fields.email.value,
        use: $("use").value, heard: $("heard").value, chrome: $("chrome").checked,
        turnstile: turnstileToken,
      });
    } catch (error) {
      idle(button);
      if (SITEKEY && window.turnstile) { turnstile.reset("#human-check"); turnstileToken = ""; }
      return setError("form", error.message);
    }
    try { sessionStorage.removeItem(GOOGLE_KEY); } catch { /* fine */ }
    if (answer.status === "approved" && answer.next) return location.assign(answer.next);
    const title = $("sent-title");
    const text = $("sent-text");
    if (answer.status === "approved") {
      title.textContent = "You already have access";
      text.textContent = "Sign in with Google using that address.";
    } else if (answer.status === "pending" && !answer.new) {
      title.textContent = "Already asked";
      text.textContent = "A request from that address is with the operator. You can "
        + "sign in once it is approved.";
    } else if (answer.status !== "pending") {
      title.textContent = "Not available";
      text.textContent = "That address does not have access to SnipShare.";
    }
    show($("request"), false);
    show($("sent"));
    $("sent").focus();
  });
}

if (page === "signin") signinPage();
if (page === "signup") signupPage();
