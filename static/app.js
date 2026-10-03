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
    if (!graphPanel.hidden) loadGraph();  // keep the graph in sync with the library
  } catch (err) {
    libraryStatus.textContent = `Could not load library: ${err.message}`;
  }
}

// ---------- citation graph ----------
const graphToggle = document.getElementById("graph-toggle");
const graphPanel = document.getElementById("graph-panel");
const graphStatus = document.getElementById("graph-status");
const graphContainer = document.getElementById("graph");

graphToggle.addEventListener("click", () => {
  graphPanel.hidden = !graphPanel.hidden;
  graphToggle.textContent = graphPanel.hidden ? "Show citation graph" : "Hide citation graph";
  if (!graphPanel.hidden) loadGraph();
});

function shortTitle(title, max = 40) {
  return title.length > max ? title.slice(0, max - 1) + "…" : title;
}

async function loadGraph() {
  if (!window.vis) {
    graphStatus.textContent = "Graph library failed to load (no internet connection to the CDN?).";
    return;
  }
  graphStatus.textContent = "Looking up citations on OpenAlex… (first time can take a few seconds per paper)";
  try {
    const { nodes, edges } = await api("/api/graph");
    const unmatched = nodes.filter(n => !n.matched).length;
    graphStatus.textContent =
      `${nodes.length} papers, ${edges.length} citation link${edges.length === 1 ? "" : "s"} between them. ` +
      "Arrow A → B means A cites B. Click a paper to open it." +
      (unmatched ? ` ${unmatched} paper(s) not found on OpenAlex (shown faded).` : "");

    const data = {
      nodes: nodes.map(n => ({
        id: n.id,
        label: `${shortTitle(n.title)}\n${n.year ?? ""}`,
        title: n.title,  // full title on hover
        color: n.matched ? undefined : { background: "#eee", border: "#ccc" },
        font: { color: n.matched ? "#1f2328" : "#999" },
      })),
      edges: edges.map(e => ({ from: e.from, to: e.to, arrows: "to" })),
    };
    const network = new vis.Network(graphContainer, data, {
      nodes: { shape: "box", margin: 8, widthConstraint: { maximum: 220 },
               color: { background: "#ddf4ff", border: "#0969da" } },
      edges: { color: "#8c959f", smooth: { type: "dynamic" } },
      physics: { stabilization: true, barnesHut: { springLength: 180 } },
    });
    network.on("click", (params) => { if (params.nodes.length) openPaper(params.nodes[0]); });
  } catch (err) {
    graphStatus.textContent = `Could not build the citation graph: ${err.message}`;
  }
}

// ---------- paper detail: summary + Q&A ----------
const EXAMPLE_QUESTIONS = [
  "What problem does this paper address?",
  "What is the main idea of the proposed approach?",
  "What datasets are used?",
  "What are the major limitations?",
  "How does this method compare with the baselines?",
];

// LLM output is Markdown; render it, but sanitize first. Falls back to plain text if the CDN libs didn't load.
function markdown(text) {
  const node = el("div", { class: "markdown" });
  if (window.marked && window.DOMPurify) node.innerHTML = DOMPurify.sanitize(marked.parse(text));
  else node.textContent = text;
  return node;
}

const TRUNCATED_NOTE = "Note: this paper is very long, so only the first ~300,000 characters were sent to the model.";

function summarySection(paper) {
  const body = el("div", {}, paper.summary ? markdown(paper.summary) : el("p", { class: "muted" }, "No summary yet."));
  const status = el("p", { class: "muted" });
  const button = el("button", {}, paper.summary ? "Regenerate summary" : "Summarize with Gemini");

  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Generating summary from the full paper… (can take up to ~30 s)";
    try {
      const refresh = paper.summary ? "?refresh=true" : "";
      const res = await api(`/api/papers/${paper.id}/summary${refresh}`, { method: "POST" });
      paper.summary = res.summary;
      body.replaceChildren(markdown(res.summary));
      button.textContent = "Regenerate summary";
      status.textContent = res.truncated ? TRUNCATED_NOTE : "";
    } catch (err) {
      status.textContent = `Summary failed: ${err.message}`;
    } finally {
      button.disabled = false;
    }
  });

  return el("section", { class: "card" }, el("h3", {}, "Summary"), button, status, body);
}

function qaSection(paper) {
  const input = el("textarea", { rows: "2", placeholder: "Ask a question about this paper…", maxlength: "1000" });
  const askButton = el("button", { type: "submit" }, "Ask");
  const history = el("div", { class: "qa-history" });

  async function ask(question) {
    question = question.trim();
    if (!question) return;
    askButton.disabled = true;
    const answerNode = el("div", { class: "muted" }, "Thinking…");
    history.prepend(el("div", { class: "qa-item" }, el("p", { class: "question" }, question), answerNode));
    try {
      const res = await api(`/api/papers/${paper.id}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      answerNode.replaceWith(markdown(res.answer), ...(res.truncated ? [el("p", { class: "muted" }, TRUNCATED_NOTE)] : []));
    } catch (err) {
      answerNode.textContent = `Could not answer: ${err.message}`;
    } finally {
      askButton.disabled = false;
    }
  }

  const form = el("form", { class: "qa-form" }, input, askButton);
  form.addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); input.value = ""; });
  input.addEventListener("keydown", (e) => {  // Enter sends, Shift+Enter adds a newline
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });

  const examples = el("div", { class: "examples" },
    ...EXAMPLE_QUESTIONS.map(q => el("button", { type: "button", class: "chip", onclick: () => ask(q) }, q)));

  return el("section", { class: "card" }, el("h3", {}, "Ask about this paper"), examples, form, history);
}

async function openPaper(id) {
  showTab("detail");
  detailContent.replaceChildren(el("p", { class: "muted" }, "Loading…"));
  try {
    const paper = await api(`/api/papers/${id}`);
    const sections = paper.text_status === "ready"
      ? [summarySection(paper), qaSection(paper)]
      : [el("p", { class: "muted" }, "This paper's full text is unavailable, so it can't be summarized or questioned. Upload its PDF in the Library tab.")];
    detailContent.replaceChildren(el("div", { class: "cards" }, renderPaperCard(paper, [textBadge(paper)]), ...sections));
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
