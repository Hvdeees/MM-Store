/* MM Store — web interface. Plain JavaScript, no framework, no build step.
 *
 * How it works:
 *  - After login, the JWT token is kept in localStorage and sent with every API call (see api()).
 *  - Each menu entry ("view") is a function that loads data from /api/... and writes HTML into <main id="view">.
 *  - Everything that comes from the server goes through esc() before it is put into HTML (prevents XSS).
 */

// ---------- Helpers ----------

const state = { token: localStorage.getItem("token"), user: null, storeName: "MM Store", categories: [],
  cart: [], payment: "especes", posCategory: "", prodCategory: "", resellers: [], reseller: null, lowOnly: false };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isAdmin = () => state.user?.role === "admin";
const TZ = "Africa/Casablanca";
const PAYMENT = { especes: "Espèces", carte: "Carte", virement: "Virement", cheque: "Chèque", credit: "À crédit" };
const PAY_NOW = { especes: "Espèces", carte: "Carte", virement: "Virement", cheque: "Chèque" };
const REASON = { achat: "Stock ajouté", vente: "Vendu", annulation: "Vente annulée", ajustement: "Correction" };

/** 15000 centimes -> "150,00 DH" */
const money = (c) => (c / 100).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " DH";
/** "1 299,50" typed by a person -> 129950 centimes (NaN if it isn't a number) */
function toCentimes(text) {
  const n = Number(String(text).replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) : NaN;
}
const toDH = (c) => (c / 100).toFixed(2).replace(".", ",");
const fmtDate = (iso) => new Date(iso).toLocaleString("fr-FR", { timeZone: TZ, dateStyle: "medium", timeStyle: "short" });
const fmtDay = (iso) => new Date(iso).toLocaleDateString("fr-FR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const today = (offsetDays = 0) => new Date(Date.now() + offsetDays * 86400000).toLocaleDateString("en-CA", { timeZone: TZ });

// Line icons (24×24, drawn with the text colour)
const ICONS = {
  caisse: '<path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 1.9-1.5L21 8H6.2"/><circle cx="10" cy="20" r="1.3"/><circle cx="17" cy="20" r="1.3"/>',
  produits: '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  ventes: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><path d="M9 8h6M9 12h6"/>',
  imei: '<path d="M4 6v12M7 6v12M11 6v12M14 6v12M17 6v12M20 6v12"/>',
  rapports: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  equipe: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17.5" cy="9" r="2.5"/><path d="M16 14.5a5 5 0 0 1 6 5"/>',
  compte: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4Z"/><circle cx="12" cy="13" r="3.5"/>',
  print: '<path d="M7 9V3h10v6M7 17H4v-7h16v7h-3"/><path d="M7 14h10v7H7Z"/>',
  empty: '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="M8 11h8"/>',
  phone: '<rect x="7" y="2.5" width="10" height="19" rx="2.2"/><path d="M10.5 18.5h3"/>',
  laptop: '<rect x="4.5" y="5" width="15" height="10" rx="1.4"/><path d="M2.5 18.5h19"/>',
  acc: '<path d="M6 14v-2a6 6 0 0 1 12 0v2"/><rect x="3.5" y="14" width="4" height="6" rx="1.4"/><rect x="16.5" y="14" width="4" height="6" rx="1.4"/>',
  tablet: '<rect x="4.5" y="2.5" width="15" height="19" rx="2"/><path d="M11 18.5h2"/>',
  watch: '<rect x="6.5" y="6.5" width="11" height="11" rx="3"/><path d="M9 6.5 9.6 3h4.8l.6 3.5M9 17.5l.6 3.5h4.8l.6-3.5M12 10v2.5l1.5 1"/>',
  case: '<rect x="6" y="2.5" width="12" height="19" rx="3"/><circle cx="9.5" cy="6.5" r="1.4"/><circle cx="9.5" cy="10" r="1"/>',
  shield: '<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6Z"/><path d="m9 12 2 2 4-4"/>',
  charger: '<rect x="6" y="9" width="12" height="12" rx="2.5"/><path d="M9.5 9V4M14.5 9V4M12 13l-1.5 3h3L12 19"/>',
  cable: '<path d="M7 3v5M17 3v5M5 8h4v4H5zM15 8h4v4h-4zM7 12v3a5 5 0 0 0 10 0v-3"/>',
  adapter: '<rect x="3" y="9" width="8" height="6" rx="1.5"/><path d="M11 12h3"/><rect x="14" y="8" width="7" height="8" rx="1.5"/><path d="M5.5 11.5h3M17 10.5v3"/>',
  battery: '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10.5v3M7 10v4M10.5 10v4"/>',
  speaker: '<rect x="6" y="2.5" width="12" height="19" rx="2.5"/><circle cx="12" cy="14" r="3.5"/><circle cx="12" cy="6.5" r="1.2"/>',
  sdcard: '<path d="M7 2.5h7.5L19 7v13a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 6 20V4A1.5 1.5 0 0 1 7.5 2.5Z"/><path d="M9.5 6v3M12 6v3M14.5 6v3"/>',
  usb: '<rect x="7" y="9" width="10" height="12.5" rx="2"/><path d="M9 9V3h6v6M11 5.5h.01M13 5.5h.01"/>',
  mouse: '<rect x="6.5" y="3" width="11" height="18" rx="5.5"/><path d="M12 3v6"/>',
  holder: '<path d="M8 3h8v9H8z"/><path d="M12 12v4M8 21h8M12 16a4 4 0 0 0-4 4M12 16a4 4 0 0 1 4 4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  revendeurs: '<path d="M3 9 4.5 4h15L21 9"/><path d="M3 9h18v1.5a2.5 2.5 0 0 1-4.5 1.5 2.5 2.5 0 0 1-4.5 0 2.5 2.5 0 0 1-4.5 0A2.5 2.5 0 0 1 3 10.5Z"/><path d="M5 12.5V20h14v-7.5M10 20v-4.5h4V20"/>',
};
const plainText = (text) => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
// Category name -> [drawing, colour family]. Matches on words, so renamed or new categories still get a sensible drawing.
const PICTOS = [
  [["telephone", "smartphone", "mobile"], "phone", "dev"], [["tablette", "ipad"], "tablet", "dev"],
  [["ordinateur", "laptop", "pc"], "laptop", "dev"], [["montre", "watch"], "watch", "dev"],
  [["pochette", "coque", "etui"], "case", "pro"], [["protection", "verre"], "shield", "pro"],
  [["chargeur"], "charger", "pow"], [["cable"], "cable", "pow"], [["adaptateur", "hub"], "adapter", "pow"],
  [["batterie"], "battery", "pow"], [["ecouteur", "casque"], "acc", "aud"], [["enceinte"], "speaker", "aud"],
  [["carte"], "sdcard", "sto"], [["cle", "disque"], "usb", "sto"], [["souris", "clavier"], "mouse", "sto"],
  [["support"], "holder", "sto"],
];
function picto(categoryName) {
  const name = plainText(categoryName);
  const hit = PICTOS.find(([words]) => words.some((w) => name.includes(w)));
  return hit ? { icon: hit[1], family: hit[2] } : { icon: "box", family: "sto" };
}
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;

/** The product's photo, or a drawing of a phone / laptop / accessory if it has none. */
function productPicture(p) {
  if (p.image_url) return `<img src="${esc(p.image_url)}" alt="" loading="lazy">`;
  const { icon: drawing, family } = picto(p.category?.name);
  return `<div class="placeholder ph-${family}">${icon(drawing)}</div>`;
}

function stockLabel(p) {
  if (p.quantity <= 0) return '<span class="stock stock-out">Rupture</span>';
  if (p.is_low_stock) return `<span class="stock stock-low">Plus que ${p.quantity}</span>`;
  return `<span class="stock stock-ok">${p.quantity} en stock</span>`;
}

/** "aujourd'hui", "hier", "il y a 12 jours" — and anything older than 30 days is flagged. */
function ageLabel(days) {
  const text = days === 0 ? "aujourd'hui" : days === 1 ? "hier" : `il y a ${days} jours`;
  return `<span class="age ${days > 30 ? "late" : ""}">${text}</span>`;
}

/** One unpaid purchase: what was taken, what's paid, what's left. */
function debtHtml(o, showReseller = false) {
  return `<article class="debt">
    <div class="debt-head">
      <div><div class="debt-title">${showReseller ? `${esc(o.reseller_name)}, achat n° ${o.sale_id}` : `Achat n° ${o.sale_id}`}</div>
        <div class="row-sub">${new Date(o.date).toLocaleDateString("fr-FR", { timeZone: TZ, day: "numeric", month: "long", year: "numeric" })}, ${ageLabel(o.days_old)}, vendu par ${esc(o.seller_name)}</div></div>
      <div><div class="debt-left price">${money(o.remaining_centimes)}</div>
        <div class="debt-paid">${o.paid_centimes ? `${money(o.paid_centimes)} payés sur ${money(o.total_centimes)}` : `rien payé sur ${money(o.total_centimes)}`}</div></div>
    </div>
    <ul class="debt-items">${o.items.map((i) => `<li><span>${i.quantity} × ${esc(i.product_name)}
      ${i.serial_numbers.map((sn) => `<small>IMEI ${esc(sn)}</small>`).join("")}</span><span class="price">${money(i.quantity * i.unit_price_centimes)}</span></li>`).join("")}</ul>
  </article>`;
}

/** Price for the current sale: the reseller price when selling to a reseller (if the product has one). */
const unitPrice = (p) => (state.reseller && p.wholesale_price_centimes != null ? p.wholesale_price_centimes : p.price_centimes);

function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "show" + (isError ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.className = ""), 3500);
}

/** Every call to the server goes through here: adds the login token, turns errors into French messages. */
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = "Bearer " + state.token;
  let payload;
  if (form) payload = new URLSearchParams(form);
  else if (body instanceof FormData) payload = body;          // file upload: the browser sets the content type
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let response;
  try {
    response = await fetch("/api" + path, { method, headers, body: payload });
  } catch {
    throw new Error("Pas de connexion avec le serveur. Vérifiez qu'il est allumé.");
  }
  if (response.status === 401 && path !== "/auth/login") { logout(); throw new Error("Session expirée, reconnectez-vous."); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Erreur ${response.status}`);
  return data;
}
const query = (params) => "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== false));

// ---------- Modal ----------

/** openModal({ title, body, submitLabel, onSubmit, danger, extraButtons }) — onSubmit errors stay visible in the modal. */
function openModal({ title, body, submitLabel = "Enregistrer", onSubmit, danger = false, closeLabel }) {
  const dialog = $("#modal");
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = body;
  $("#modal-error").textContent = "";
  $("#modal-foot").innerHTML = onSubmit
    ? `<button type="button" class="btn" data-close>Annuler</button><button type="submit" class="btn ${danger ? "btn-danger" : "btn-primary"}">${esc(submitLabel)}</button>`
    : `<button type="button" class="btn ${closeLabel ? "btn-primary" : ""}" data-close>${esc(closeLabel || "Fermer")}</button>`;
  $("#modal-form").onsubmit = async (event) => {
    event.preventDefault();
    if (!onSubmit) return dialog.close();
    const button = $("#modal-foot [type=submit]");
    button.disabled = true;
    try {
      await onSubmit($("#modal-form"));
      dialog.close();
    } catch (error) {
      $("#modal-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
  $$("[data-close]", dialog).forEach((b) => (b.onclick = () => dialog.close()));
  dialog.showModal();
  $("#modal-body input:not([type=file]), #modal-body select, #modal-body textarea")?.focus();
}
function addFooterButton(label, onClick, cls = "btn") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.innerHTML = label;
  b.onclick = onClick;
  $("#modal-foot").prepend(b);
  return b;
}
$("#modal-close").innerHTML = icon("close");
$("#modal-close").onclick = () => $("#modal").close();

// ---------- Login ----------

async function start() {
  try { state.storeName = (await api("/health")).store_name; } catch { /* keep default */ }
  $$(".store-name").forEach((el) => (el.textContent = state.storeName));
  document.title = state.storeName;
  if (!state.token) return showLogin();
  try { state.user = await api("/auth/me"); showApp(); } catch { showLogin(); }
}

function showLogin() {
  $("#app").hidden = true;
  $("#login-screen").hidden = false;
}

$("#login-form").onsubmit = async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    const data = await api("/auth/login", { method: "POST", form: new FormData(event.target) });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("token", state.token);
    event.target.reset();
    showApp();
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
};

function logout() {
  Object.assign(state, { token: null, user: null, cart: [] });
  localStorage.removeItem("token");
  $("#modal").close();
  showLogin();
}
$("#logout-btn").onclick = logout;

function changePassword() {
  openModal({
    title: "Changer mon mot de passe",
    body: `<label>Mot de passe actuel <input name="current_password" type="password" required></label>
           <label>Nouveau mot de passe <input name="new_password" type="password" minlength="8" required><span class="hint">8 caractères minimum</span></label>`,
    submitLabel: "Changer le mot de passe",
    onSubmit: async (f) => {
      await api("/auth/change-password", { method: "POST", body: { current_password: f.current_password.value, new_password: f.new_password.value } });
      toast("Mot de passe changé");
    },
  });
}
$("#password-btn").onclick = changePassword;

// ---------- Navigation ----------

const MENU = [
  { id: "caisse", label: "Caisse" },
  { id: "produits", label: "Produits" },
  { id: "ventes", label: "Ventes" },
  { id: "revendeurs", label: "Revendeurs" },
  { id: "imei", label: "IMEI" },
  { id: "rapports", label: "Rapports", admin: true },
  { id: "equipe", label: "Équipe", admin: true },
];

async function showApp() {
  $("#login-screen").hidden = true;
  $("#app").hidden = false;
  $("#user-name").textContent = state.user.full_name;
  $("#user-role").textContent = isAdmin() ? "Gérant" : "Vendeur";
  $("#nav").innerHTML = MENU.filter((m) => !m.admin || isAdmin())
    .map((m) => `<button class="nav-btn" type="button" data-view="${m.id}">${icon(m.id)}<span>${m.label}</span></button>`).join("")
    + `<button class="nav-btn mobile-only" type="button" data-account>${icon("compte")}<span>Compte</span></button>`;
  $$("#nav [data-view]").forEach((b) => (b.onclick = () => {
    if (location.hash.slice(1) === b.dataset.view) go(b.dataset.view); else location.hash = b.dataset.view;
  }));
  $("#nav [data-account]").onclick = () => {
    openModal({ title: state.user.full_name, body: `<p class="muted">${isAdmin() ? "Gérant" : "Vendeur"}, ${esc(state.user.email)}</p>` });
    addFooterButton("Se déconnecter", logout, "btn btn-danger");
    addFooterButton("Mon mot de passe", changePassword);
  };
  state.categories = await api("/categories");
  go(location.hash.slice(1) || "caisse");
}

const views = {};
function go(name) {
  const item = MENU.find((m) => m.id === name);
  if (!item || (item.admin && !isAdmin())) name = "caisse";
  if (location.hash.slice(1) !== name) history.replaceState(null, "", "#" + name);
  $$("#nav [data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $("#view").innerHTML = '<p class="muted">Chargement…</p>';
  views[name]().catch((error) => { $("#view").innerHTML = `<p class="error">${esc(error.message)}</p>`; });
}
window.addEventListener("hashchange", () => state.user && go(location.hash.slice(1)));

function categoryChips(selected, attr) {
  const all = [{ id: "", name: "Tout" }, ...state.categories];
  return `<div class="chips" role="group" aria-label="Catégories">${all.map((c) =>
    `<button type="button" class="chip ${String(c.id) === String(selected) ? "on" : ""}" ${attr}="${c.id}">${esc(c.name)}</button>`).join("")}</div>`;
}

function searchBox(id, placeholder) {
  return `<div class="search">${icon("search")}<input id="${id}" type="search" placeholder="${esc(placeholder)}" autocomplete="off"></div>`;
}

// ---------- Caisse ----------

views.caisse = async () => {
  $("#view").innerHTML = `
    <div class="pos">
      <section>
        ${searchBox("pos-search", "Chercher un article ou scanner un IMEI")}
        <div id="pos-chips"></div>
        <div id="pos-grid" class="tiles" aria-live="polite"></div>
      </section>
      <aside class="receipt-panel">
        <div class="ticket">
          <div class="ticket-head"><h2>Ticket</h2><span class="muted" id="ticket-date"></span></div>
          <div class="mode" role="group" aria-label="Type de vente">
            <button type="button" data-mode="client">Client</button><button type="button" data-mode="reseller">Revendeur</button>
          </div>
          <div id="reseller-box" hidden>
            <label>Revendeur <select id="reseller-select"></select></label>
            <p class="muted" id="reseller-info"></p>
          </div>
          <ul class="lines" id="cart-lines"></ul>
          <details class="extra" id="extra">
            <summary>Client et remise (facultatif)</summary>
            <label>Nom du client <input id="customer-name" maxlength="120"></label>
            <label>Téléphone du client <input id="customer-phone" maxlength="30" inputmode="tel"></label>
            <label>Remise en DH <input id="discount" value="0" inputmode="decimal"></label>
          </details>
          <div id="paid-now-box" hidden>
            <label>Payé maintenant en DH <input id="paid-now" value="0" inputmode="decimal"><span class="hint">Le reste va sur son compte.</span></label>
          </div>
          <div class="pay" role="group" aria-label="Paiement">${Object.entries(PAY_NOW).map(([v, l]) =>
            `<button type="button" data-pay="${v}">${l}</button>`).join("")}</div>
          <div class="totals" id="totals"></div>
          <button class="btn btn-primary btn-xl" id="checkout" type="button">Encaisser</button>
        </div>
        <div class="ticket-tear"></div>
      </aside>
    </div>
    <button type="button" class="cart-bar" id="cart-bar" hidden></button>`;
  $("#ticket-date").textContent = new Date().toLocaleDateString("fr-FR", { timeZone: TZ, day: "numeric", month: "long" });
  renderPosChips();
  let timer;
  $("#pos-search").oninput = () => { clearTimeout(timer); timer = setTimeout(loadPosProducts, 220); };
  $("#pos-search").focus();
  $("#discount").oninput = renderCart;
  $("#paid-now").oninput = renderCart;
  state.resellers = await api("/resellers");
  if (state.reseller) state.reseller = state.resellers.find((r) => r.id === state.reseller.id) || null;
  $("#reseller-select").innerHTML = '<option value="">Choisir…</option>' + state.resellers.map((r) =>
    `<option value="${r.id}">${esc(r.name)}${r.city ? ` (${esc(r.city)})` : ""}</option>`).join("");
  $$("[data-mode]").forEach((b) => (b.onclick = () => setSaleMode(b.dataset.mode === "reseller", null)));
  $("#reseller-select").onchange = () => setSaleMode(true, state.resellers.find((r) => r.id === +$("#reseller-select").value) || null);
  setSaleMode(state.saleMode === "reseller", state.reseller, false);
  $$("[data-pay]").forEach((b) => (b.onclick = () => { state.payment = b.dataset.pay; renderCart(); }));
  $("#checkout").onclick = checkout;
  $("#cart-bar").onclick = () => $(".receipt-panel").scrollIntoView({ behavior: "smooth" });
  renderCart();
  await loadPosProducts();
};

/** Switch the ticket between a normal customer and a reseller (reseller prices, sale on their account). */
function setSaleMode(resellerMode, reseller, reload = true) {
  state.saleMode = resellerMode ? "reseller" : "client";
  state.reseller = resellerMode ? reseller : null;
  $$("[data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === state.saleMode));
  $("#reseller-box").hidden = !resellerMode;
  $("#paid-now-box").hidden = !resellerMode;
  $("#extra").hidden = resellerMode;
  $("#reseller-select").value = reseller ? reseller.id : "";
  $("#reseller-info").innerHTML = reseller
    ? (reseller.balance_centimes > 0 ? `Doit déjà <strong>${money(reseller.balance_centimes)}</strong>` : "Ne doit rien pour le moment")
    : (state.resellers.length ? "" : 'Aucun revendeur. Le gérant peut en ajouter dans « Revendeurs ».');
  renderCart();
  if (reload) loadPosProducts();
}

function renderPosChips() {
  $("#pos-chips").innerHTML = categoryChips(state.posCategory, "data-cat");
  $$("#pos-chips [data-cat]").forEach((b) => (b.onclick = () => { state.posCategory = b.dataset.cat; renderPosChips(); loadPosProducts(); }));
}

async function loadPosProducts() {
  const q = $("#pos-search").value.trim();
  const products = await api("/products" + query({ q, category_id: state.posCategory, limit: 120 }));
  const grid = $("#pos-grid");
  if (!grid) return;
  grid.innerHTML = products.length ? products.map((p) => {
    const inCart = state.cart.filter((l) => l.product.id === p.id).reduce((n, l) => n + l.quantity, 0);
    return `<button type="button" class="tile" data-add="${p.id}" ${p.quantity ? "" : "disabled"} aria-label="Ajouter ${esc(p.name)}">
      <div class="tile-photo">${productPicture(p)}</div>
      ${inCart ? `<span class="tile-count">${inCart}</span>` : ""}
      <div class="tile-body"><span class="tile-name">${esc(p.name)}</span><span class="tile-price">${money(unitPrice(p))}</span>${stockLabel(p)}</div>
    </button>`;
  }).join("") : `<div class="empty">${icon("empty")}<p>Aucun article ne correspond à « ${esc(q)} ».</p></div>`;
  $$("[data-add]", grid).forEach((b) => (b.onclick = () => addToCart(products.find((p) => p.id === +b.dataset.add), q)));
}

async function addToCart(product, searchText) {
  if (!product.tracks_serial) {
    const line = state.cart.find((l) => l.product.id === product.id);
    if (line) {
      if (line.quantity >= product.quantity) return toast(`Il ne reste que ${product.quantity} « ${product.name} »`, true);
      line.quantity += 1;
    } else state.cart.push({ product, quantity: 1, serial: null });
    renderCart(); return loadPosProducts();
  }
  // Phones & computers: every unit has its own IMEI, so the seller picks which one leaves the shop.
  const inCart = state.cart.filter((l) => l.serial).map((l) => l.serial);
  const available = (await api(`/products/${product.id}/serials`)).map((s) => s.serial).filter((s) => !inCart.includes(s));
  if (!available.length) return toast("Toutes les unités sont déjà dans le ticket", true);
  const pick = (serial) => { state.cart.push({ product, quantity: 1, serial }); renderCart(); loadPosProducts(); };
  const scanned = available.find((s) => s === searchText.toUpperCase());
  if (scanned) { $("#pos-search").value = ""; return pick(scanned); }   // the IMEI was scanned: nothing to ask
  openModal({
    title: product.name,
    body: `<p class="muted" style="margin-bottom:.8rem">Quel appareil vendez-vous ? Vérifiez l'IMEI sur la boîte.</p>
      <div class="imei-choices">${available.map((s) => `<button type="button" data-imei="${esc(s)}">${esc(s)}</button>`).join("")}</div>`,
  });
  $$("[data-imei]").forEach((b) => (b.onclick = () => { pick(b.dataset.imei); $("#modal").close(); }));
}

function cartTotals() {
  const subtotal = state.cart.reduce((sum, l) => sum + l.quantity * unitPrice(l.product), 0);
  const discount = toCentimes($("#discount")?.value || 0);
  return { subtotal, discount, total: subtotal - (Number.isNaN(discount) ? 0 : discount) };
}

function renderCart() {
  if (!$("#cart-lines")) return;
  $("#cart-lines").innerHTML = state.cart.length ? state.cart.map((l, i) => `
    <li class="line">
      <div><div class="line-name">${esc(l.product.name)}</div>${l.serial ? `<div class="line-imei">IMEI ${esc(l.serial)}</div>` : ""}</div>
      <div class="line-total price">${money(l.quantity * unitPrice(l.product))}</div>
      <div class="line-actions">
        ${l.serial ? '<span class="muted">1 appareil</span>' : `<div class="stepper"><button type="button" data-dec="${i}" aria-label="Un de moins">−</button><span>${l.quantity}</span><button type="button" data-inc="${i}" aria-label="Un de plus">+</button></div>`}
        <button type="button" class="remove" data-remove="${i}">Retirer</button>
      </div>
    </li>`).join("") : '<li class="ticket-empty">Touchez un article pour l\'ajouter au ticket.</li>';

  $$("[data-inc]").forEach((b) => (b.onclick = () => { const l = state.cart[+b.dataset.inc]; if (l.quantity < l.product.quantity) l.quantity++; else toast(`Il ne reste que ${l.product.quantity} en stock`, true); renderCart(); loadPosProducts(); }));
  $$("[data-dec]").forEach((b) => (b.onclick = () => { const i = +b.dataset.dec; if (state.cart[i].quantity > 1) state.cart[i].quantity--; else state.cart.splice(i, 1); renderCart(); loadPosProducts(); }));
  $$("[data-remove]").forEach((b) => (b.onclick = () => { state.cart.splice(+b.dataset.remove, 1); renderCart(); loadPosProducts(); }));
  $$("[data-pay]").forEach((b) => b.classList.toggle("on", b.dataset.pay === state.payment));
  const paidNow = state.reseller ? toCentimes($("#paid-now").value || 0) : 0;
  $(".pay").hidden = state.saleMode === "reseller" && !(paidNow > 0);

  const { subtotal, discount, total } = cartTotals();
  const hasDiscount = !Number.isNaN(discount) && discount > 0;
  $("#totals").innerHTML = `
    ${hasDiscount ? `<span>Sous-total</span><span class="price">${money(subtotal)}</span><span>Remise</span><span class="price">− ${money(discount)}</span>` : ""}
    <span class="grand">Total</span><span class="grand price">${money(Math.max(total, 0))}</span>`;
  const button = $("#checkout");
  const resellerMode = state.saleMode === "reseller";
  button.disabled = !state.cart.length || (resellerMode && !state.reseller);
  if (resellerMode) {
    const rest = Math.max(total, 0) - (Number.isNaN(paidNow) ? 0 : paidNow);
    button.textContent = !state.reseller ? "Choisissez le revendeur" : rest > 0 ? `Mettre ${money(rest)} sur son compte` : "Valider la vente";
  } else {
    button.textContent = state.cart.length ? `Encaisser ${money(Math.max(total, 0))}` : "Encaisser";
  }
  const items = state.cart.reduce((n, l) => n + l.quantity, 0);
  $("#cart-bar").hidden = !items;
  $("#cart-bar").innerHTML = `<span>Voir le ticket (${items} article${items > 1 ? "s" : ""})</span><span class="price">${money(Math.max(total, 0))}</span>`;
}

async function checkout() {
  const { discount, subtotal } = cartTotals();
  if (Number.isNaN(discount)) return toast("La remise doit être un nombre", true);
  if (discount > subtotal) return toast("La remise est plus grande que le total", true);
  const body = {
    items: state.cart.map((l) => ({ product_id: l.product.id, quantity: l.quantity, serials: l.serial ? [l.serial] : [] })),
    payment_method: state.payment,
    discount_centimes: discount,
    customer_name: $("#customer-name").value.trim() || null,
    customer_phone: $("#customer-phone").value.trim() || null,
  };
  if (state.saleMode === "reseller") {
    if (!state.reseller) return toast("Choisissez le revendeur", true);
    const paidNow = toCentimes($("#paid-now").value || 0);
    if (Number.isNaN(paidNow)) return toast("Le montant payé doit être un nombre", true);
    Object.assign(body, { reseller_id: state.reseller.id, paid_now_centimes: paidNow, paid_now_method: state.payment,
      payment_method: "credit", customer_name: null, customer_phone: null });
  }
  $("#checkout").disabled = true;
  try {
    const sale = await api("/sales", { method: "POST", body });
    state.cart = [];
    state.payment = "especes";
    $("#customer-name").value = $("#customer-phone").value = "";
    $("#discount").value = "0";
    $("#paid-now").value = "0";
    $("#extra").open = false;
    if (state.reseller) {   // refresh what they owe
      state.resellers = await api("/resellers");
      setSaleMode(true, state.resellers.find((r) => r.id === state.reseller.id) || null, false);
    }
    toast(`Vente n° ${sale.id} encaissée`);
    showSale(sale, "Nouvelle vente");
  } catch (error) {
    toast(error.message, true);
  } finally {
    renderCart();
    loadPosProducts();
  }
}

// ---------- Receipts ----------

function receiptHtml(sale) {
  return `<div class="receipt">
    <div class="receipt-brand"><div class="brand"><span class="brand-mark">MM</span><span class="brand-name">${esc(state.storeName)}</span></div></div>
    <div class="receipt-meta">Ticket n° ${sale.id}<br>${fmtDate(sale.created_at)}<br>Vendeur : ${esc(sale.seller_name)}
      ${sale.customer_name ? `<br>Client : ${esc(sale.customer_name)} ${esc(sale.customer_phone || "")}` : ""}
      ${sale.reseller_name ? `<br>Revendeur : <strong>${esc(sale.reseller_name)}</strong>` : ""}</div>
    <table>${sale.items.map((i) => `<tr><td>${i.quantity} × ${esc(i.product_name)}
      ${i.serial_numbers.map((s) => `<br><small class="muted">IMEI ${esc(s)}</small>`).join("")}</td>
      <td class="r price">${money(i.line_total_centimes)}</td></tr>`).join("")}
      ${sale.discount_centimes ? `<tr><td>Remise</td><td class="r price">− ${money(sale.discount_centimes)}</td></tr>` : ""}
      <tr class="grand"><td>Total</td><td class="r price">${money(sale.total_centimes)}</td></tr>
      ${sale.reseller_name ? `<tr><td class="muted">Payé maintenant</td><td class="r price">${money(sale.paid_now_centimes)}</td></tr>
        <tr><td class="muted">Mis sur le compte</td><td class="r price"><strong>${money(sale.total_centimes - sale.paid_now_centimes)}</strong></td></tr>`
        : `<tr><td class="muted">Payé par</td><td class="r">${PAYMENT[sale.payment_method]}</td></tr>`}</table>
    ${sale.status === "annulee" ? `<p class="cancelled-note">Vente annulée le ${fmtDate(sale.cancelled_at)} : ${esc(sale.cancel_reason)}</p>`
      : `<p class="thanks">Merci pour votre visite</p>`}
  </div>`;
}

function printReceipt(sale) {
  let area = $("#print-area");
  if (!area) { area = document.createElement("div"); area.id = "print-area"; document.body.append(area); }
  area.innerHTML = receiptHtml(sale);
  window.print();
}

function showSale(sale, closeLabel) {
  openModal({ title: `Vente n° ${sale.id}`, body: receiptHtml(sale), closeLabel });
  addFooterButton(`${icon("print")} Imprimer`, () => printReceipt(sale));
  if (isAdmin() && sale.status === "validee") addFooterButton("Annuler la vente", () => cancelSale(sale), "btn btn-danger");
}

function cancelSale(sale) {
  openModal({
    title: `Annuler la vente n° ${sale.id} ?`,
    body: `<p style="margin-bottom:1rem">Les articles reviennent en stock. Le ticket reste dans l'historique, marqué « annulé ».</p>
           <label>Pourquoi ? <input name="reason" minlength="3" required placeholder="Ex. le client a rapporté l'article"></label>`,
    submitLabel: "Annuler la vente",
    danger: true,
    onSubmit: async (f) => {
      await api(`/sales/${sale.id}/cancel`, { method: "POST", body: { reason: f.reason.value } });
      toast("Vente annulée, articles remis en stock");
      if (location.hash === "#ventes") loadSales();
    },
  });
}

// ---------- Produits ----------

views.produits = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Produits</h1>${isAdmin() ? `<div style="display:flex;gap:.5rem;flex-wrap:wrap"><button class="btn" id="p-cats" type="button">Catégories</button><button class="btn btn-primary" id="p-new" type="button">${icon("plus")} Nouveau produit</button></div>` : ""}</div>
    ${searchBox("p-q", "Chercher un produit, une marque ou un IMEI")}
    <div id="p-chips"></div>
    <div id="p-alert"></div>
    <label class="switch" style="width:fit-content;margin-bottom:1rem"><input type="checkbox" id="p-low" ${state.lowOnly ? "checked" : ""}> Seulement ceux qui manquent</label>
    <div id="p-grid" class="tiles"></div>`;
  renderProdChips();
  let timer;
  $("#p-q").oninput = () => { clearTimeout(timer); timer = setTimeout(loadProducts, 220); };
  $("#p-low").onchange = () => { state.lowOnly = $("#p-low").checked; loadProducts(); };
  const low = await api("/products?low_stock=true");
  if (low.length) {
    $("#p-alert").innerHTML = `<button type="button" class="alert" id="p-alert-btn"><span><strong>${low.length} produit${low.length > 1 ? "s" : ""} à recommander</strong><br>
      ${low.slice(0, 3).map((p) => esc(p.name)).join(", ")}${low.length > 3 ? "…" : ""}</span><span>Voir</span></button>`;
    $("#p-alert-btn").onclick = () => { $("#p-low").checked = state.lowOnly = true; loadProducts(); };
  }
  if (isAdmin()) { $("#p-new").onclick = () => productForm(); $("#p-cats").onclick = manageCategories; }
  await loadProducts();
};

function renderProdChips() {
  $("#p-chips").innerHTML = categoryChips(state.prodCategory, "data-pcat");
  $$("#p-chips [data-pcat]").forEach((b) => (b.onclick = () => { state.prodCategory = b.dataset.pcat; renderProdChips(); loadProducts(); }));
}

async function loadProducts() {
  const products = await api("/products" + query({ q: $("#p-q").value.trim(), category_id: state.prodCategory,
    low_stock: $("#p-low").checked, include_inactive: isAdmin() }));
  $("#p-grid").innerHTML = products.length ? products.map((p) => `
    <button type="button" class="tile" data-open="${p.id}">
      <div class="tile-photo">${productPicture(p)}</div>
      <div class="tile-body"><span class="tile-name">${esc(p.name)}</span><span class="tile-price">${money(p.price_centimes)}</span>
        ${p.is_active ? stockLabel(p) : '<span class="stock stock-out">Archivé</span>'}</div>
    </button>`).join("") : `<div class="empty">${icon("empty")}<p>Aucun produit ici.</p></div>`;
  $$("[data-open]").forEach((b) => (b.onclick = () => productSheet(products.find((p) => p.id === +b.dataset.open))));
}

function manageCategories() {
  openModal({
    title: "Catégories",
    body: `<p class="muted" style="margin-bottom:1rem">Elles s'affichent dans cet ordre à la caisse. Cliquez sur un nom pour le changer.</p>
      <div class="list" id="cat-list">${state.categories.map((c) => {
        const { icon: drawing, family } = picto(c.name);
        return `<button type="button" class="row cat-row" data-cat-id="${c.id}"><div style="display:flex;align-items:center;gap:.7rem">
          <span class="cat-dot ph-${family}">${icon(drawing)}</span><span class="row-title">${esc(c.name)}</span></div><span class="muted">Renommer</span></button>`;
      }).join("")}</div>
      <label style="margin-top:1.1rem">Nouvelle catégorie <input name="name" maxlength="80" placeholder="Ex. Consoles de jeux"></label>`,
    submitLabel: "Ajouter la catégorie",
    onSubmit: async (f) => {
      if (f.name.value.trim().length < 2) throw new Error("Tapez le nom de la nouvelle catégorie");
      await api("/categories", { method: "POST", body: { name: f.name.value } });
      state.categories = await api("/categories");
      toast("Catégorie ajoutée");
      renderProdChips();
    },
  });
  $$("[data-cat-id]").forEach((b) => (b.onclick = () => {
    const c = state.categories.find((x) => x.id === +b.dataset.catId);
    openModal({
      title: `Renommer « ${c.name} »`,
      body: `<label>Nouveau nom <input name="name" value="${esc(c.name)}" required minlength="2" maxlength="80"></label>`,
      submitLabel: "Renommer",
      onSubmit: async (f) => {
        await api(`/categories/${c.id}`, { method: "PATCH", body: { name: f.name.value } });
        state.categories = await api("/categories");
        toast("Catégorie renommée");
        renderProdChips();
        loadProducts();
      },
    });
  }));
}

/** Product details with big, plain buttons for each thing you can do with it. */
function productSheet(p) {
  openModal({
    title: p.name,
    body: `<div class="sheet">
      <div class="sheet-photo">${productPicture(p)}</div>
      <div>
        <div class="muted">${esc(p.brand || "")} ${esc(p.category.name)}</div>
        <div class="sheet-price">${money(p.price_centimes)}</div>
        ${p.wholesale_price_centimes != null ? `<p class="muted">Prix revendeur : <strong>${money(p.wholesale_price_centimes)}</strong></p>` : ""}
        ${stockLabel(p)}
        ${isAdmin() ? `<p class="muted" style="margin-top:.6rem">Prix d'achat : ${money(p.cost_centimes)}<br>Marge : ${money(p.price_centimes - p.cost_centimes)} par article</p>` : ""}
        <p class="muted" style="margin-top:.4rem">Référence ${esc(p.sku)}${p.tracks_serial ? ", suivi par IMEI" : ""}</p>
      </div>
    </div>
    <div class="sheet-actions">
      ${isAdmin() ? `<button type="button" class="btn btn-primary" data-act="restock">${icon("plus")} Ajouter du stock</button>
        <button type="button" class="btn" data-act="edit">Modifier</button>` : ""}
      ${p.tracks_serial ? '<button type="button" class="btn" data-act="serials">Voir les IMEI en stock</button>' : ""}
      ${isAdmin() && !p.tracks_serial ? '<button type="button" class="btn" data-act="adjust">Corriger le stock</button>' : ""}
      ${isAdmin() ? '<button type="button" class="btn" data-act="history">Historique</button>' : ""}
    </div>`,
  });
  const actions = { restock: () => restockForm(p), edit: () => productForm(p), serials: () => showSerials(p), adjust: () => adjustForm(p), history: () => showHistory(p) };
  $$("[data-act]").forEach((b) => (b.onclick = () => actions[b.dataset.act]()));
}

function photoPickerHtml(p) {
  return `<div class="photo-picker">
    <div class="photo-preview" id="photo-preview">${p?.image_url ? `<img src="${esc(p.image_url)}" alt="">` : icon("camera")}</div>
    <div><strong>Photo</strong><span class="hint">Prenez l'article en photo sur fond clair, ou choisissez une image.</span>
      <div class="photo-buttons">
        <button type="button" class="btn" id="photo-choose">${icon("camera")} ${p?.image_url ? "Changer la photo" : "Ajouter une photo"}</button>
        ${p?.image_url ? '<button type="button" class="btn btn-danger" id="photo-remove">Retirer</button>' : ""}
      </div>
      <input type="file" id="photo-file" accept="image/*">
    </div></div>`;
}

function productForm(product = null) {
  const p = product || { name: "", brand: "", category: { id: state.categories[0]?.id }, price_centimes: 0, cost_centimes: 0, low_stock_threshold: 3, tracks_serial: false, is_active: true, sku: "" };
  let photoFile = null, removePhoto = false;
  openModal({
    title: product ? `Modifier ${product.name}` : "Nouveau produit",
    body: `${photoPickerHtml(product)}
      <label>Nom de l'article <input name="name" value="${esc(p.name)}" required maxlength="200" placeholder="Ex. Samsung Galaxy A55 128 Go"></label>
      <div class="row2">
        <label>Catégorie <select name="category_id">${state.categories.map((c) => `<option value="${c.id}" ${c.id === p.category.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
        <label>Marque <input name="brand" value="${esc(p.brand || "")}" maxlength="80" placeholder="Ex. Samsung"></label>
        <label>Prix de vente (DH) <input name="price" value="${product ? toDH(p.price_centimes) : ""}" inputmode="decimal" required placeholder="0,00"></label>
        <label>Prix d'achat (DH) <input name="cost" value="${product ? toDH(p.cost_centimes) : ""}" inputmode="decimal" placeholder="0,00"><span class="hint">Visible seulement par le gérant</span></label>
        <label>Prix revendeur (DH) <input name="wholesale" value="${p.wholesale_price_centimes != null ? toDH(p.wholesale_price_centimes) : ""}" inputmode="decimal" placeholder="Facultatif"><span class="hint">Prix pour les magasins qui achètent chez vous</span></label>
      </div>
      <label>Me prévenir quand il en reste <input name="low_stock_threshold" type="number" min="0" value="${p.low_stock_threshold}"></label>
      ${product ? `<label class="switch"><input type="checkbox" name="is_active" ${p.is_active ? "checked" : ""}> <span>Article en vente<span class="hint">Décochez pour l'archiver : il disparaît de la caisse mais reste dans l'historique.</span></span></label>`
        : `<label class="switch"><input type="checkbox" name="tracks_serial"> <span>Téléphone ou ordinateur avec IMEI / numéro de série<span class="hint">Chaque appareil sera suivi un par un.</span></span></label>
           <label>Référence (facultatif) <input name="sku" maxlength="64" placeholder="Créée automatiquement si vide"></label>`}`,
    submitLabel: product ? "Enregistrer" : "Créer le produit",
    onSubmit: async (f) => {
      const price = toCentimes(f.price.value), cost = toCentimes(f.cost.value || 0);
      if (Number.isNaN(price)) throw new Error("Le prix de vente doit être un nombre, par exemple 149,90");
      if (Number.isNaN(cost)) throw new Error("Le prix d'achat doit être un nombre");
      const wholesale = f.wholesale.value.trim() ? toCentimes(f.wholesale.value) : null;
      if (Number.isNaN(wholesale)) throw new Error("Le prix revendeur doit être un nombre");
      const body = { name: f.name.value, brand: f.brand.value || null, category_id: +f.category_id.value,
        price_centimes: price, cost_centimes: cost, wholesale_price_centimes: wholesale, low_stock_threshold: +f.low_stock_threshold.value || 0 };
      let saved;
      if (product) {
        body.is_active = f.is_active.checked;
        saved = await api(`/products/${product.id}`, { method: "PATCH", body });
      } else {
        // No reference typed? Make one from the name + time, e.g. "SAMSUNG-GALAXY-L8K2".
        const auto = f.name.value.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9]+/g, "-").slice(0, 20).replace(/-$/, "");
        Object.assign(body, { sku: f.sku.value.trim() || `${auto}-${Date.now().toString(36).slice(-4).toUpperCase()}`, tracks_serial: f.tracks_serial.checked });
        saved = await api("/products", { method: "POST", body });
      }
      if (photoFile) {
        const data = new FormData();
        data.append("file", photoFile);
        await api(`/products/${saved.id}/image`, { method: "POST", body: data });
      } else if (removePhoto) {
        await api(`/products/${saved.id}/image`, { method: "DELETE" });
      }
      toast(product ? "Produit enregistré" : "Produit créé. Ajoutez maintenant du stock.");
      loadProducts();
    },
  });
  $("#photo-choose").onclick = () => $("#photo-file").click();
  $("#photo-file").onchange = () => {
    photoFile = $("#photo-file").files[0] || null;
    if (photoFile) { removePhoto = false; $("#photo-preview").innerHTML = `<img src="${URL.createObjectURL(photoFile)}" alt="">`; }
  };
  if ($("#photo-remove")) $("#photo-remove").onclick = () => { removePhoto = true; photoFile = null; $("#photo-preview").innerHTML = icon("camera"); };
}

function restockForm(p) {
  openModal({
    title: `Ajouter du stock : ${p.name}`,
    body: (p.tracks_serial
      ? `<label>IMEI ou numéros de série <textarea name="serials" required placeholder="Un par ligne. Vous pouvez les scanner."></textarea><span class="hint">Un numéro par appareil reçu.</span></label>`
      : `<label>Combien d'articles avez-vous reçus ? <input name="quantity" type="number" min="1" required></label>`)
      + `<label>Nouveau prix d'achat en DH (facultatif) <input name="cost" inputmode="decimal" placeholder="${toDH(p.cost_centimes || 0)}"></label>
         <label>Note (facultatif) <input name="note" maxlength="255" placeholder="Ex. facture n° 118, fournisseur"></label>`,
    submitLabel: "Ajouter au stock",
    onSubmit: async (f) => {
      const serials = p.tracks_serial ? f.serials.value.split(/[\s,;]+/).filter(Boolean) : [];
      const body = { quantity: p.tracks_serial ? serials.length : +f.quantity.value, serials, note: f.note.value || null };
      if (f.cost.value) {
        body.cost_centimes = toCentimes(f.cost.value);
        if (Number.isNaN(body.cost_centimes)) throw new Error("Le prix d'achat doit être un nombre");
      }
      if (!body.quantity) throw new Error("Indiquez au moins un article");
      await api(`/products/${p.id}/restock`, { method: "POST", body });
      toast(`${body.quantity} ajouté(s) au stock`);
      loadProducts();
    },
  });
}

function adjustForm(p) {
  openModal({
    title: `Corriger le stock : ${p.name}`,
    body: `<p style="margin-bottom:1rem">Le stock affiché est de <strong>${p.quantity}</strong>. Combien en avez-vous vraiment ?</p>
      <label>Quantité réelle <input name="real" type="number" min="0" required value="${p.quantity}"></label>
      <label>Raison <input name="note" minlength="3" required placeholder="Ex. un article cassé, inventaire"></label>`,
    submitLabel: "Corriger",
    onSubmit: async (f) => {
      const change = +f.real.value - p.quantity;
      if (!change) throw new Error("La quantité n'a pas changé");
      await api(`/products/${p.id}/adjust`, { method: "POST", body: { change, note: f.note.value } });
      toast("Stock corrigé");
      loadProducts();
    },
  });
}

async function showHistory(p) {
  const moves = await api(`/products/${p.id}/movements`);
  openModal({
    title: `Historique : ${p.name}`,
    body: moves.length ? `<div class="list">${moves.map((m) => `<div class="row">
        <div><div class="row-title">${REASON[m.reason]}${m.sale_id ? ` (vente n° ${m.sale_id})` : ""}</div>
          <div class="row-sub">${fmtDate(m.created_at)}${m.user_name ? ` par ${esc(m.user_name)}` : ""}${m.note ? `<br>${esc(m.note)}` : ""}</div></div>
        <div class="row-amount ${m.change > 0 ? "" : "muted"}">${m.change > 0 ? "+" : ""}${m.change}</div></div>`).join("")}</div>`
      : '<p class="muted">Rien pour le moment.</p>',
  });
}

async function showSerials(p) {
  const serials = await api(`/products/${p.id}/serials`);
  openModal({
    title: `IMEI en stock : ${p.name}`,
    body: serials.length ? `<div class="list">${serials.map((s) => `<div class="row"><div class="row-title" style="font-family:ui-monospace,Menlo,monospace">${esc(s.serial)}</div>
      <div class="row-sub">reçu le ${new Date(s.created_at).toLocaleDateString("fr-FR", { timeZone: TZ })}</div></div>`).join("")}</div>`
      : '<p class="muted">Aucun appareil en stock.</p>',
  });
}

// ---------- Ventes ----------

views.ventes = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Ventes</h1></div>
    <div class="filters">
      <label>Du <input type="date" id="s-from" value="${today(-6)}"></label>
      <label>Au <input type="date" id="s-to" value="${today()}"></label>
    </div>
    <div id="s-list"></div>`;
  $("#s-from").onchange = $("#s-to").onchange = loadSales;
  await loadSales();
};

async function loadSales() {
  const sales = await api("/sales" + query({ from_date: $("#s-from").value, to_date: $("#s-to").value, limit: 500 }));
  const valid = sales.filter((s) => s.status === "validee");
  const total = valid.reduce((sum, s) => sum + s.total_centimes, 0);
  $("#s-list").innerHTML = sales.length ? `
    <p class="summary-line"><strong>${valid.length} vente(s)</strong> pour <strong>${money(total)}</strong>${isAdmin() ? "" : " (vos ventes)"}</p>
    <div class="list">${sales.map((s) => `<button type="button" class="row" data-sale="${s.id}">
      <div><div class="row-title">${s.items.map((i) => `${i.quantity} × ${esc(i.product_name)}`).join(", ")}</div>
        <div class="row-sub">${fmtDate(s.created_at)}, ${PAYMENT[s.payment_method]}, ${esc(s.seller_name)}${s.customer_name ? `, ${esc(s.customer_name)}` : ""}</div>
        ${s.reseller_name ? `<span class="pill pill-info">${esc(s.reseller_name)}</span>` : ""}</div>
      <div><div class="row-amount price">${money(s.total_centimes)}</div>${s.status === "annulee" ? '<span class="pill pill-bad">Annulée</span>' : ""}</div>
    </button>`).join("")}</div>`
    : `<div class="empty">${icon("ventes")}<p>Aucune vente sur ces dates.</p></div>`;
  $$("[data-sale]").forEach((row) => (row.onclick = () => showSale(sales.find((s) => s.id === +row.dataset.sale))));
}

// ---------- Revendeurs ----------

const owes = (r) => r.balance_centimes > 0 ? `<span class="owe price">${money(r.balance_centimes)}<small>à encaisser</small></span>`
  : r.balance_centimes < 0 ? `<span class="pill pill-info">Avance de ${money(-r.balance_centimes)}</span>` : '<span class="pill pill-ok">À jour</span>';

views.revendeurs = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Revendeurs</h1>${isAdmin() ? `<button class="btn btn-primary" id="r-new" type="button">${icon("plus")} Ajouter un revendeur</button>` : ""}</div>
    <p class="muted" style="margin:-.4rem 0 1rem;max-width:62ch">Les magasins qui achètent chez MM Store : ce qu'ils ont pris, ce qu'ils ont payé et ce qu'ils doivent encore.</p>
    <div id="r-total"></div>
    <div class="tabs" role="tablist"><button type="button" class="on" data-rtab="list">Revendeurs</button><button type="button" data-rtab="unpaid">Impayés</button></div>
    <div id="r-tab-list">
      ${searchBox("r-q", "Chercher un magasin, une ville, un téléphone")}
      <div id="r-list" class="list" style="margin-top:1rem"></div>
    </div>
    <div id="r-tab-unpaid" hidden></div>`;
  let timer;
  $("#r-q").oninput = () => { clearTimeout(timer); timer = setTimeout(loadResellers, 220); };
  $$("[data-rtab]").forEach((b) => (b.onclick = async () => {
    $$("[data-rtab]").forEach((x) => x.classList.toggle("on", x === b));
    $("#r-tab-list").hidden = b.dataset.rtab !== "list";
    $("#r-tab-unpaid").hidden = b.dataset.rtab !== "unpaid";
    if (b.dataset.rtab === "unpaid") await loadAllUnpaid();
  }));
  if (isAdmin()) $("#r-new").onclick = () => resellerForm();
  await loadResellers();
};

/** Everything sold to resellers and not paid yet, all shops together, oldest first. */
async function loadAllUnpaid() {
  const open = await api("/resellers/unpaid");
  const total = open.reduce((sum, o) => sum + o.remaining_centimes, 0);
  $("#r-tab-unpaid").innerHTML = open.length
    ? `<p class="summary-line"><strong>${open.length} achat${open.length > 1 ? "s" : ""}</strong> pas encore payé${open.length > 1 ? "s" : ""}, pour <strong>${money(total)}</strong>. Les plus anciens en premier.</p>
       <div class="debts">${open.map((o) => debtHtml(o, true)).join("")}</div>`
    : `<div class="empty">${icon("revendeurs")}<p>Tout est payé. Aucun revendeur ne vous doit d'argent.</p></div>`;
}

async function loadResellers() {
  const list = await api("/resellers" + query({ q: $("#r-q").value.trim(), include_inactive: isAdmin() }));
  const owing = list.filter((r) => r.balance_centimes > 0);
  const total = owing.reduce((sum, r) => sum + r.balance_centimes, 0);
  $("#r-total").innerHTML = list.length ? `<div class="stats">
      <div class="stat ${total ? "owing" : "lead"}"><div class="stat-label">Reste à encaisser</div><div class="stat-value price">${money(total)}</div></div>
      <div class="stat"><div class="stat-label">Revendeurs qui doivent</div><div class="stat-value">${owing.length} sur ${list.length}</div></div></div>` : "";
  $("#r-list").innerHTML = list.length ? list.map((r) => `<button type="button" class="row" data-r="${r.id}">
      <div><div class="row-title">${esc(r.name)} ${r.is_active ? "" : '<span class="pill pill-bad">Désactivé</span>'}</div>
        <div class="row-sub">${[r.city, r.contact_name, r.phone].filter(Boolean).map(esc).join(", ") || "Pas de coordonnées"}
        ${r.last_activity ? `<br>Dernière opération le ${new Date(r.last_activity).toLocaleDateString("fr-FR", { timeZone: TZ })}` : ""}</div></div>
      <div style="text-align:right">${owes(r)}</div></button>`).join("")
    : `<div class="empty">${icon("revendeurs")}<p>${$("#r-q").value ? "Aucun revendeur trouvé." : "Aucun revendeur pour le moment."}</p>
       ${isAdmin() && !$("#r-q").value ? '<p>Ajoutez les magasins qui achètent chez vous pour suivre ce qu\'ils doivent.</p>' : ""}</div>`;
  $$("[data-r]").forEach((b) => (b.onclick = () => showReseller(+b.dataset.r)));
}

function resellerForm(r = null) {
  openModal({
    title: r ? `Modifier ${r.name}` : "Nouveau revendeur",
    body: `<label>Nom du magasin <input name="name" required minlength="2" maxlength="120" value="${esc(r?.name || "")}" placeholder="Ex. Phone House Agadir"></label>
      <div class="row2">
        <label>Ville <input name="city" maxlength="80" value="${esc(r?.city || "")}"></label>
        <label>Téléphone <input name="phone" maxlength="30" inputmode="tel" value="${esc(r?.phone || "")}"></label>
      </div>
      <label>Personne à contacter <input name="contact_name" maxlength="120" value="${esc(r?.contact_name || "")}"></label>
      <label>Notes <input name="notes" maxlength="500" value="${esc(r?.notes || "")}" placeholder="Ex. paie chaque fin de mois"></label>
      ${r ? `<label class="switch"><input type="checkbox" name="is_active" ${r.is_active ? "checked" : ""}> <span>Peut acheter<span class="hint">Décochez pour ne plus lui vendre. Son historique reste.</span></span></label>` : ""}`,
    submitLabel: r ? "Enregistrer" : "Ajouter",
    onSubmit: async (f) => {
      const body = { name: f.name.value, city: f.city.value || null, phone: f.phone.value || null,
        contact_name: f.contact_name.value || null, notes: f.notes.value || null };
      if (r) body.is_active = f.is_active.checked;
      await api(r ? `/resellers/${r.id}` : "/resellers", { method: r ? "PATCH" : "POST", body });
      toast(r ? "Revendeur enregistré" : "Revendeur ajouté");
      loadResellers();
    },
  });
}

const STATEMENT_KIND = { achat: "Achat", paiement: "Paiement", achat_annule: "Annulé" };

function accountFigures(d) {
  return `<div class="stats stats-3">
      <div class="stat"><div class="stat-label">A acheté</div><div class="stat-value price">${money(d.purchases_centimes)}</div></div>
      <div class="stat"><div class="stat-label">A payé</div><div class="stat-value price">${money(d.paid_centimes)}</div></div>
      <div class="stat ${d.balance_centimes > 0 ? "owing" : "lead"}"><div class="stat-label">${d.balance_centimes < 0 ? "Avance" : "Reste à payer"}</div><div class="stat-value price">${money(Math.abs(d.balance_centimes))}</div></div>
    </div>`;
}

function unpaidHtml(d) {
  return d.open_purchases.length
    ? `<p class="summary-line">Ce qu'il a pris et pas encore payé. Ses paiements remboursent d'abord ses achats les plus anciens.</p>
       <div class="debts">${d.open_purchases.map((o) => debtHtml(o)).join("")}</div>`
    : `<div class="empty">${icon("revendeurs")}<p>Tout est payé.</p></div>`;
}

function statementHtml(d) {
  return `${d.statement.length ? `<table class="statement"><tr><th>Date</th><th>Opération</th><th class="r">Montant</th><th class="r">Doit</th></tr>
      ${d.statement.map((e) => `<tr class="${e.kind}"><td>${new Date(e.date).toLocaleDateString("fr-FR", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" })}
        <br><small class="muted">${new Date(e.date).toLocaleTimeString("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" })}</small></td>
        <td>${esc(e.label)}${e.by ? `<br><small class="muted">par ${esc(e.by)}</small>` : ""}</td>
        <td class="r price">${e.debit_centimes ? "+ " + money(e.debit_centimes) : e.credit_centimes ? "− " + money(e.credit_centimes) : "—"}</td>
        <td class="r price">${e.balance_centimes < 0 ? `avance ${money(-e.balance_centimes)}` : money(e.balance_centimes)}</td></tr>`).join("")}</table>`
      : '<p class="muted">Aucune opération pour le moment.</p>'}`;
}

async function showReseller(id) {
  const d = await api(`/resellers/${id}`);
  openModal({
    title: d.name,
    body: `<p class="muted" style="margin-bottom:1.2rem">${[d.city, d.contact_name, d.phone].filter(Boolean).map(esc).join(", ")}${d.notes ? `<br>${esc(d.notes)}` : ""}</p>
      ${accountFigures(d)}
      <div class="tabs"><button type="button" class="on" data-dtab="unpaid">Ce qu'il doit (${d.open_purchases.length})</button><button type="button" data-dtab="all">Relevé complet</button></div>
      <div id="d-tab">${unpaidHtml(d)}</div>`,
  });
  $$("[data-dtab]").forEach((b) => (b.onclick = () => {
    $$("[data-dtab]").forEach((x) => x.classList.toggle("on", x === b));
    $("#d-tab").innerHTML = b.dataset.dtab === "unpaid" ? unpaidHtml(d) : statementHtml(d);
  }));
  $("#modal").classList.add("wide");
  $("#modal").addEventListener("close", () => $("#modal").classList.remove("wide"), { once: true });
  addFooterButton(`${icon("print")} Imprimer le relevé`, () => printStatement(d));
  if (isAdmin()) addFooterButton("Modifier", () => resellerForm(d));
  if (d.is_active) addFooterButton(`${icon("caisse")} Lui vendre`, () => {
    state.saleMode = "reseller";
    state.reseller = d;
    $("#modal").close();
    location.hash = "caisse";
  });
  addFooterButton("Enregistrer un paiement", () => paymentForm(d), "btn btn-primary");
}

function paymentForm(d) {
  let method = "especes";
  openModal({
    title: `Paiement de ${d.name}`,
    body: `<p style="margin-bottom:1rem">${d.balance_centimes > 0 ? `Il doit <strong>${money(d.balance_centimes)}</strong>.` : "Il ne doit rien pour le moment."}</p>
      <label>Montant reçu en DH <input name="amount" inputmode="decimal" required placeholder="0,00" value="${d.balance_centimes > 0 ? toDH(d.balance_centimes) : ""}"></label>
      <div class="pay" role="group" aria-label="Moyen de paiement">${Object.entries(PAY_NOW).map(([v, l]) => `<button type="button" data-pm="${v}" class="${v === method ? "on" : ""}">${l}</button>`).join("")}</div>
      <label>Note (facultatif) <input name="note" maxlength="255" placeholder="Ex. chèque n° 1234"></label>`,
    submitLabel: "Enregistrer le paiement",
    onSubmit: async (f) => {
      const amount = toCentimes(f.amount.value);
      if (!(amount > 0)) throw new Error("Indiquez le montant reçu, par exemple 1500");
      await api(`/resellers/${d.id}/payments`, { method: "POST", body: { amount_centimes: amount, payment_method: method, note: f.note.value || null } });
      toast(`Paiement de ${money(amount)} enregistré`);
      if (location.hash === "#revendeurs") loadResellers();
      showReseller(d.id);
    },
  });
  $$("[data-pm]").forEach((b) => (b.onclick = () => { method = b.dataset.pm; $$("[data-pm]").forEach((x) => x.classList.toggle("on", x === b)); }));
}

function printStatement(d) {
  let area = $("#print-area");
  if (!area) { area = document.createElement("div"); area.id = "print-area"; document.body.append(area); }
  area.innerHTML = `<div class="receipt"><div class="receipt-brand"><div class="brand"><span class="brand-mark">MM</span><span class="brand-name">${esc(state.storeName)}</span></div></div>
    <div class="receipt-meta">Relevé de compte : <strong>${esc(d.name)}</strong><br>Au ${new Date().toLocaleDateString("fr-FR", { timeZone: TZ, dateStyle: "long" })}</div>
    ${accountFigures(d)}
    ${d.open_purchases.length ? `<h2 style="margin:1rem 0 .6rem">Reste à payer</h2><div class="debts">${d.open_purchases.map((o) => debtHtml(o)).join("")}</div>` : ""}
    <h2 style="margin:1.4rem 0 .6rem">Toutes les opérations</h2>${statementHtml(d)}</div>`;
  area.classList.add("print-wide");
  window.print();
  area.classList.remove("print-wide");
}

// ---------- IMEI ----------

views.imei = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Vérifier un IMEI</h1></div>
    <p class="muted" style="margin-bottom:1rem;max-width:60ch">Pour une garantie ou un retour : retrouvez quand l'appareil est arrivé au magasin et à qui il a été vendu.</p>
    <form id="imei-form" style="max-width:640px">
      <div class="search">${icon("search")}<input name="serial" required placeholder="Tapez ou scannez l'IMEI" autocomplete="off"></div>
      <button class="btn btn-primary" style="margin-top:.7rem" type="submit">Vérifier</button>
    </form>
    <div id="imei-result" style="max-width:640px;margin-top:1.2rem"></div>`;
  $("#imei-form").onsubmit = async (event) => {
    event.preventDefault();
    const box = $("#imei-result");
    try {
      const r = await api(`/serials/${encodeURIComponent(event.target.serial.value.trim())}`);
      box.innerHTML = `<div class="panel">
        <h2>${esc(r.product_name)}</h2>
        <p style="font-family:ui-monospace,Menlo,monospace;margin:.3rem 0 .8rem">${esc(r.serial)}</p>
        ${r.status === "vendu" ? '<span class="pill pill-info">Vendu</span>' : '<span class="pill pill-ok">En stock au magasin</span>'}
        <table style="margin-top:.8rem">
          <tr><th>Arrivé le</th><td>${fmtDate(r.received_at)}</td></tr>
          ${r.sale_id ? `<tr><th>Vendu le</th><td>${fmtDate(r.sold_at)} (vente n° ${r.sale_id})</td></tr>
            <tr><th>Client</th><td>${esc(r.customer_name || "Non renseigné")} ${esc(r.customer_phone || "")}</td></tr>` : ""}
        </table></div>`;
    } catch (error) {
      box.innerHTML = `<p class="error">${esc(error.message)}</p>`;
    }
  };
};

// ---------- Rapports ----------

views.rapports = async () => {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Rapports</h1><label style="margin:0">Journée <input type="date" id="r-day" value="${today()}"></label></div>
    <div id="r-daily"></div>
    <div class="split">
      <div class="panel"><h2>Les 7 derniers jours</h2><div id="r-days" class="bars"></div></div>
      <div class="panel"><h2>Meilleures ventes</h2><div id="r-top"></div></div>
    </div>`;
  $("#r-day").onchange = loadDaily;
  await Promise.all([loadDaily(), loadPeriod()]);
};

async function loadDaily() {
  const r = await api("/reports/daily" + query({ day: $("#r-day").value }));
  const stat = (label, value, lead = false) => `<div class="stat ${lead ? "lead" : ""}"><div class="stat-label">${label}</div><div class="stat-value price">${value}</div></div>`;
  $("#r-daily").innerHTML = `
    <div class="stats">
      ${stat("Chiffre d'affaires", money(r.revenue_centimes), true)}
      ${stat("Bénéfice", money(r.margin_centimes))}
      ${stat("Ventes", r.sale_count)}
      ${stat("Articles vendus", r.items_sold)}
    </div>
    ${r.reseller_payments_centimes || r.by_payment.some((p) => p.payment_method === "credit") ? `<p class="summary-line">Revendeurs : ${money(r.by_payment.find((p) => p.payment_method === "credit")?.total_centimes || 0)} vendus à crédit, <strong>${money(r.reseller_payments_centimes)}</strong> reçus en paiement ce jour-là.</p>` : ""}
    <div class="panel"><h2>Par moyen de paiement</h2>
      ${r.by_payment.length ? `<table>${r.by_payment.map((p) => `<tr><td>${PAYMENT[p.payment_method]}</td><td class="r muted">${p.sale_count} vente(s)</td><td class="r price"><strong>${money(p.total_centimes)}</strong></td></tr>`).join("")}</table>`
        : '<p class="muted">Aucune vente ce jour-là.</p>'}
      ${r.cancelled_count || r.discount_centimes ? `<p class="muted" style="margin-top:.7rem">${r.cancelled_count} vente(s) annulée(s), ${money(r.discount_centimes)} de remises.</p>` : ""}
    </div>`;
}

async function loadPeriod() {
  const params = { from_date: today(-6), to_date: today() };
  const [days, top] = await Promise.all([api("/reports/daily-totals" + query(params)), api("/reports/top-products" + query({ ...params, limit: 5 }))]);
  const max = Math.max(1, ...days.map((d) => d.revenue_centimes));
  $("#r-days").innerHTML = days.map((d) => `<div class="bar-row">
      <span class="muted">${new Date(d.date + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" })}</span>
      <div class="bar ${d.revenue_centimes ? "" : "zero"}" style="width:${(d.revenue_centimes / max) * 100}%"></div>
      <span class="price" style="text-align:right">${money(d.revenue_centimes)}</span></div>`).join("");
  $("#r-top").innerHTML = top.length ? `<table>${top.map((t) => `<tr><td>${esc(t.name)}</td><td class="r muted">× ${t.quantity_sold}</td><td class="r price">${money(t.revenue_centimes)}</td></tr>`).join("")}</table>`
    : '<p class="muted">Pas encore de ventes cette semaine.</p>';
}

// ---------- Équipe ----------

views.equipe = async () => {
  $("#view").innerHTML = `<div class="page-head"><h1>Équipe</h1><button class="btn btn-primary" id="u-new" type="button">${icon("plus")} Ajouter un vendeur</button></div><div id="u-list" class="list"></div>`;
  $("#u-new").onclick = () => openModal({
    title: "Ajouter un membre de l'équipe",
    body: `<label>Nom <input name="full_name" required minlength="2"></label>
      <label>Email <input name="email" type="email" required><span class="hint">Il servira à se connecter.</span></label>
      <label>Mot de passe provisoire <input name="password" type="password" minlength="8" required><span class="hint">8 caractères minimum. La personne pourra le changer.</span></label>
      <label>Rôle <select name="role"><option value="vendeur">Vendeur : vend et consulte le stock</option><option value="admin">Gérant : accès à tout</option></select></label>`,
    submitLabel: "Ajouter",
    onSubmit: async (f) => {
      await api("/users", { method: "POST", body: { full_name: f.full_name.value, email: f.email.value, password: f.password.value, role: f.role.value } });
      toast("Compte créé");
      loadUsers();
    },
  });
  await loadUsers();
};

async function loadUsers() {
  const users = await api("/users");
  $("#u-list").innerHTML = users.map((u) => `<div class="row">
    <div><div class="row-title">${esc(u.full_name)} ${u.is_active ? "" : '<span class="pill pill-bad">Désactivé</span>'}</div>
      <div class="row-sub">${u.role === "admin" ? "Gérant" : "Vendeur"}, ${esc(u.email)}</div></div>
    <div>${u.id === state.user.id ? '<span class="muted">C\'est vous</span>' : `<button type="button" class="btn" data-user="${u.id}">Gérer</button>`}</div></div>`).join("");
  $$("[data-user]").forEach((b) => (b.onclick = () => manageUser(users.find((u) => u.id === +b.dataset.user))));
}

function manageUser(u) {
  const patch = async (body, message) => {
    try { await api(`/users/${u.id}`, { method: "PATCH", body }); toast(message); $("#modal").close(); loadUsers(); }
    catch (e) { $("#modal-error").textContent = e.message; }
  };
  openModal({
    title: u.full_name,
    body: `<p class="muted" style="margin-bottom:1rem">${u.role === "admin" ? "Gérant" : "Vendeur"}, ${esc(u.email)}</p>
      <div class="list">
        <button type="button" class="btn" data-a="role">${u.role === "admin" ? "Passer en vendeur" : "Passer en gérant"}</button>
        <button type="button" class="btn" data-a="pwd">Donner un nouveau mot de passe</button>
        <button type="button" class="btn ${u.is_active ? "btn-danger" : ""}" data-a="active">${u.is_active ? "Bloquer l'accès" : "Redonner l'accès"}</button>
      </div>`,
  });
  $('[data-a="role"]').onclick = () => patch({ role: u.role === "admin" ? "vendeur" : "admin" }, "Rôle changé");
  $('[data-a="active"]').onclick = () => patch({ is_active: !u.is_active }, u.is_active ? "Accès bloqué" : "Accès rendu");
  $('[data-a="pwd"]').onclick = () => openModal({
    title: `Nouveau mot de passe pour ${u.full_name}`,
    body: `<label>Mot de passe <input name="password" type="password" minlength="8" required><span class="hint">8 caractères minimum</span></label>`,
    submitLabel: "Enregistrer",
    onSubmit: async (f) => { await api(`/users/${u.id}`, { method: "PATCH", body: { password: f.password.value } }); toast("Mot de passe changé"); },
  });
}

start();
