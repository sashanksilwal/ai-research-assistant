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
    searchResults.replaceChildren(...papers.map(p => renderPaperCard(p)));
  } catch (err) {
    searchStatus.textContent = `Search failed: ${err.message}`;
  } finally {
    button.disabled = false;
  }
});
