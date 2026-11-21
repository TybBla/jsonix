// Wspólne elementy interfejsu: tworzenie elementów, komunikaty, ekrany, stepper.

const APP_NAME = "Odwołania2JSON";

/** Tworzy element: el("p", {class: "x", text: "..."}, [dzieci]). Tekst zawsze przez textContent. */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function $(selector, root = document) {
  return root.querySelector(selector);
}

/** Rozmiar pliku po polsku, np. „1,2 MB”, „830 KB”. */
export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = value < 10 ? 1 : 0;
  return `${value.toLocaleString("pl-PL", { maximumFractionDigits: digits })} ${units[unit]}`;
}

let currentTitle = "";

function applyTitle(hasError) {
  document.title = `${hasError ? "Błąd: " : ""}${currentTitle} – ${APP_NAME}`;
}

/** Podsumowanie błędów (GOV.UK Error summary): lista linków do pól, fokus na podsumowaniu. */
export function showErrors(errors, { focus = true } = {}) {
  const box = $("#error-summary");
  const list = $("#error-summary-list");
  list.replaceChildren();
  if (!errors.length) {
    box.hidden = true;
    applyTitle(false);
    return;
  }
  for (const err of errors) {
    const link = el("a", { href: `#${err.target}`, text: err.message });
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      const target = document.getElementById(err.target);
      if (target) {
        if (!target.hasAttribute("tabindex") && !/^(INPUT|BUTTON|A|SELECT|TEXTAREA)$/.test(target.tagName)) {
          target.setAttribute("tabindex", "-1");
        }
        target.focus();
        target.scrollIntoView({ block: "center" });
      }
    });
    list.append(el("li", {}, [link]));
  }
  box.hidden = false;
  applyTitle(true);
  if (focus) box.focus();
}

export function clearErrors() {
  showErrors([]);
}

/** Komunikat dla czytnika ekranu (region role="status"). */
export function announce(message) {
  const region = $("#status");
  region.textContent = "";
  window.setTimeout(() => {
    region.textContent = message;
  }, 50);
}

const STEP_OF_SCREEN = { upload: 1, results: 2, review: 3 };

/** Przełącza ekran, aktualizuje stepper, tytuł strony i przenosi fokus na nagłówek. */
export function showScreen(name, title, { focus = true } = {}) {
  for (const section of document.querySelectorAll(".screen")) {
    section.hidden = section.dataset.screen !== name;
  }
  setStep(STEP_OF_SCREEN[name] ?? 1);
  currentTitle = title;
  clearErrors();
  if (focus) {
    const heading = document.querySelector(`[data-screen="${name}"] h1`);
    if (heading) heading.focus();
  }
}

export function setStep(active) {
  for (const li of document.querySelectorAll("#stepper .step")) {
    const n = Number(li.dataset.step);
    li.classList.toggle("is-active", n === active);
    li.classList.toggle("is-done", n < active);
    const state = li.querySelector(".step-state");
    if (n === active) {
      li.setAttribute("aria-current", "step");
      state.textContent = ", bieżący krok";
    } else {
      li.removeAttribute("aria-current");
      state.textContent = n < active ? ", ukończony" : "";
    }
  }
}

export function setTitle(title) {
  currentTitle = title;
  applyTitle(!$("#error-summary").hidden);
}

/** Ustawienia wyglądu: wysoki kontrast i rozmiar tekstu (zapamiętane w przeglądarce, jeśli się da). */
export function initA11yBar() {
  const root = document.documentElement;
  const store = {
    get(key) {
      try {
        return window.localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        /* brak dostępu do pamięci przeglądarki — ustawienie działa do odświeżenia strony */
      }
    },
  };
  const contrastBtn = $("#contrast-btn");
  const setContrast = (on) => {
    if (on) root.dataset.contrast = "high";
    else delete root.dataset.contrast;
    contrastBtn?.setAttribute("aria-pressed", String(on));
    store.set("o2j-contrast", on ? "1" : "0");
  };
  contrastBtn?.addEventListener("click", () => setContrast(root.dataset.contrast !== "high"));
  setContrast(store.get("o2j-contrast") === "1");

  const fontBtns = document.querySelectorAll(".font-btn");
  const setFont = (level) => {
    if (level === "1") delete root.dataset.font;
    else root.dataset.font = level;
    for (const b of fontBtns) b.setAttribute("aria-pressed", String(b.dataset.font === level));
    store.set("o2j-font", level);
  };
  for (const b of fontBtns) b.addEventListener("click", () => setFont(b.dataset.font));
  setFont(store.get("o2j-font") || "1");
}
