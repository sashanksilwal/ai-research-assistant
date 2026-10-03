// ---------- helpers ----------
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

async function api(path, options) {
  const res = await fetch(path, options);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail || `Request failed (${res.status})`);
  return body;
}

// ---------- tabs ----------
function showTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === name));
  if (name === "library") loadLibrary();
}

document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));

// ---------- shared paper card (search results, library, uploads) ----------
function formatAuthors(authors) {
  if (!authors?.length) return "Unknown authors";
  return authors.length > 6 ? `${authors.slice(0, 6).join(", ")}, et al.` : authors.join(", ");
}

function renderPaperCard(paper, actions = []) {
  const abstract = el("p", { class: "abstract clamped", title: "Click to expand" }, paper.abstract || "No abstract available.");
  abstract.addEventListener("click", () => abstract.classList.toggle("clamped"));

  const title = paper.url
    ? el("a", { href: paper.url, target: "_blank", rel: "noopener" }, paper.title)
    : paper.title;

  return el("article", { class: "card" },
    el("h3", {}, title),
    el("p", { class: "meta" }, `${formatAuthors(paper.authors)} · ${paper.year ?? "Year unknown"}`),
    abstract,
    el("div", { class: "actions" },
      paper.url ? el("a", { href: paper.url, target: "_blank", rel: "noopener" }, "View paper") : null,
      paper.pdf_url ? el("a", { href: paper.pdf_url, target: "_blank", rel: "noopener" }, "PDF") : null,
      ...actions),
  );
}

// ---------- search ----------
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchStatus = document.getElementById("search-status");
const searchResults = document.getElementById("search-results");

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;
  const button = searchForm.querySelector("button");
  button.disabled = true;
  searchStatus.textContent = "Searching arXiv…";
  searchResults.replaceChildren();
  try {
    const papers = await api(`/api/search?q=${encodeURIComponent(q)}`);
    searchStatus.textContent = papers.length
      ? `${papers.length} results for “${q}”`
      : `No results for “${q}”. Try different keywords.`;
    searchResults.replaceChildren(...papers.map(p => renderPaperCard(p, [saveButton(p)])));
  } catch (err) {
    searchStatus.textContent = `Search failed: ${err.message}`;
  } finally {
    button.disabled = false;
  }
});

// ---------- library ----------
// external_id -> saved paper id, so search results can show "Saved".
const savedIds = new Map();

const libraryStatus = document.getElementById("library-status");
const libraryList = document.getElementById("library-list");
const detailContent = document.getElementById("detail-content");

function textBadge(paper) {
  return paper.text_status === "ready"
    ? el("span", { class: "badge ok" }, `Full text ready (${paper.text_chars.toLocaleString()} chars)`)
    : el("span", { class: "badge warn", title: "Summaries and Q&A need the full text" }, "Full text unavailable");
}

function saveButton(paper) {
  const button = el("button", { class: "small" }, "Save to library");
  if (savedIds.has(paper.external_id)) {
    button.textContent = "Saved ✓";
    button.disabled = true;
    return button;
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Saving… (downloading PDF)";
    try {
      const saved = await api("/api/papers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(paper),
      });
      savedIds.set(saved.external_id, saved.id);
      button.textContent = saved.text_status === "ready" ? "Saved ✓" : "Saved (no full text)";
      if (saved.text_error) button.title = saved.text_error;
    } catch (err) {
      button.disabled = false;
      button.textContent = "Save failed — retry";
      button.title = err.message;
    }
  });
  return button;
}

async function loadLibrary() {
  libraryStatus.textContent = "Loading library…";
  try {
    const papers = await api("/api/papers");
    savedIds.clear();
    papers.forEach(p => p.external_id && savedIds.set(p.external_id, p.id));
    libraryStatus.textContent = papers.length
      ? `${papers.length} saved paper${papers.length === 1 ? "" : "s"}`
      : "Your library is empty. Save papers from Search.";
    libraryList.replaceChildren(...papers.map(p => renderPaperCard(p, [
      el("span", { class: "badge source" }, p.source === "upload" ? "Uploaded PDF" : "arXiv"),
      textBadge(p),
      el("button", { class: "small", onclick: () => openPaper(p.id) }, "Open"),
    ])));
  } catch (err) {
    libraryStatus.textContent = `Could not load library: ${err.message}`;
  }
}

// ---------- paper detail ----------
async function openPaper(id) {
  showTab("detail");
  detailContent.replaceChildren(el("p", { class: "muted" }, "Loading…"));
  try {
    const paper = await api(`/api/papers/${id}`);
    detailContent.replaceChildren(
      renderPaperCard(paper, [textBadge(paper)]),
      el("p", { class: "muted" }, "Summary and Q&A coming in M4."),
    );
  } catch (err) {
    detailContent.replaceChildren(el("p", { class: "muted" }, `Could not load paper: ${err.message}`));
  }
}

// ---------- upload ----------
const uploadForm = document.getElementById("upload-form");
const uploadInput = document.getElementById("upload-input");
const uploadStatus = document.getElementById("upload-status");

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = uploadInput.files[0];
  if (!file) return;
  const button = uploadForm.querySelector("button");
  button.disabled = true;
  uploadStatus.textContent = `Uploading “${file.name}” and extracting title, authors, year and abstract…`;
  try {
    const body = new FormData();
    body.append("file", file);
    const paper = await api("/api/upload", { method: "POST", body });
    const notes = [paper.text_error, paper.metadata_warning].filter(Boolean);
    uploadStatus.textContent = `Added “${paper.title}”.` + (notes.length ? ` Note: ${notes.join(" ")}` : "");
    uploadForm.reset();
    await loadLibrary();
  } catch (err) {
    uploadStatus.textContent = `Upload failed: ${err.message}`;
  } finally {
    button.disabled = false;
  }
});

loadLibrary();  // populate savedIds so search results show "Saved ✓"
