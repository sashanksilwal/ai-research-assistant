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

// Recommended topics under the search bar: keyword phrases (arXiv search matches keywords, not titles).
const SEARCH_TOPICS = [
  "LLM agents software engineering",
  "code generation large language models",
  "automated program repair",
  "LLM test generation",
  "fault localization",
  "retrieval augmented generation",
  "chain of thought reasoning",
  "knowledge distillation",
];
document.getElementById("search-topics").append(...SEARCH_TOPICS.map(topic =>
  el("button", { type: "button", class: "topic-link", onclick: () => { searchInput.value = topic; searchForm.requestSubmit(); } }, topic)));

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;
  const button = searchForm.querySelector("button");
  button.disabled = true;
  document.getElementById("search").classList.remove("home");  // compact layout once results show
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
  graphStatus.textContent = "Looking up citations on Semantic Scholar and OpenAlex… (first time can take up to a minute)";
  try {
    const { nodes, edges } = await api("/api/graph");
    const unmatched = nodes.filter(n => !n.matched).length;
    graphStatus.textContent =
      `${nodes.length} papers, ${edges.length} citation link${edges.length === 1 ? "" : "s"} between them. ` +
      "Arrow A → B means A cites B. Hover a paper to see its full title and links, click to open it; scroll to zoom." +
      (unmatched ? ` ${unmatched} paper(s) without citation data (gray).` : "");

    renderGraph(nodes, edges);
  } catch (err) {
    graphStatus.textContent = `Could not build the citation graph: ${err.message}`;
  }
}

// Obsidian-style graph: dots sized by link count, labels that fade when zoomed out,
// hover highlights a paper and its direct citations, search highlights by title.
const graphSearch = document.getElementById("graph-search");
const graphOrphans = document.getElementById("graph-orphans");
const graphLabels = document.getElementById("graph-labels");
try { graphLabels.value = localStorage.getItem("graphLabels") || graphLabels.value; } catch {}
const GRAPH = {
  arxiv: "#0969da", upload: "#8250df", unmatched: "#afb8c1",
  edge: "#c4cad1", edgeOn: "#0969da", label: "#1f2328",
  faded: 0.12,
};
let graph = null;  // { network, nodes, edges, hovered } for the rendered graph

function renderGraph(nodes, edges) {
  graph?.network.destroy();
  const degree = new Map(nodes.map(n => [n.id, 0]));
  edges.forEach(e => {
    degree.set(e.from, degree.get(e.from) + 1);
    degree.set(e.to, degree.get(e.to) + 1);
  });
  const nodeSet = new vis.DataSet(nodes.map(n => {
    const c = !n.matched ? GRAPH.unmatched : (GRAPH[n.source] ?? GRAPH.arxiv);
    return {
      id: n.id,
      label: "",  // set by applyGraphFocus: top-N papers, or the hovered paper and its neighbours
      short: shortTitle(n.title, 32),
      full: n.year ? `${n.title} (${n.year})` : n.title,
      value: degree.get(n.id) + 1,
      degree: degree.get(n.id),
      search: n.title.toLowerCase(),
      color: { background: c, border: c, highlight: { background: c, border: GRAPH.label }, hover: { background: c, border: c } },
    };
  }));
  const edgeSet = new vis.DataSet(edges.map(e => ({ id: `${e.from}-${e.to}`, from: e.from, to: e.to })));
  const network = new vis.Network(graphContainer, { nodes: nodeSet, edges: edgeSet }, {
    nodes: {
      shape: "dot", borderWidth: 0,
      font: { size: 12, color: GRAPH.label, face: "system-ui" },
      // Labels shrink with zoom and disappear below drawThreshold px, like Obsidian's text fade.
      scaling: { min: 6, max: 20, label: { enabled: true, min: 12, max: 14, drawThreshold: 8 } },
    },
    edges: {
      color: { color: GRAPH.edge, highlight: GRAPH.edgeOn, hover: GRAPH.edgeOn },
      arrows: { to: { enabled: true, scaleFactor: 0.4 } },
      smooth: false, width: 1, selectionWidth: 1,
    },
    physics: {
      solver: "forceAtlas2Based",
      forceAtlas2Based: { gravitationalConstant: -45, centralGravity: 0.01, springLength: 90, springConstant: 0.06, damping: 0.6 },
      stabilization: { iterations: 250 },
    },
    interaction: { hover: true, tooltipDelay: 300 },
  });
  graph = { network, nodes: nodeSet, edges: edgeSet, hovered: null };

  network.once("stabilizationIterationsDone", () => network.fit({ animation: { duration: 400 } }));
  network.on("click", (params) => { if (params.nodes.length) openPaper(params.nodes[0]); });
  network.on("hoverNode", ({ node }) => { graph.hovered = node; applyGraphFocus(); });
  network.on("blurNode", () => { graph.hovered = null; applyGraphFocus(); });
  applyGraphOrphans();
  applyGraphFocus();
}

// Fade everything except the focus: the hovered paper + its neighbours, else search matches.
// Only focused papers are labelled; with no focus, only the N most-linked papers are.
function applyGraphFocus() {
  if (!graph) return;
  const { network, nodes, edges, hovered } = graph;
  const term = graphSearch.value.trim().toLowerCase();
  const limit = graphLabels.value === "all" ? Infinity : Number(graphLabels.value);
  const top = new Set(nodes.get().sort((a, b) => b.degree - a.degree).slice(0, limit).map(n => n.id));
  let keepNodes = null, keepEdges = new Set();
  if (hovered !== null) {
    keepNodes = new Set([hovered, ...network.getConnectedNodes(hovered)]);
    keepEdges = new Set(network.getConnectedEdges(hovered));
  } else if (term) {
    keepNodes = new Set(nodes.get({ filter: n => n.search.includes(term) }).map(n => n.id));
  }
  nodes.update(nodes.get().map(n => {
    const on = !keepNodes || keepNodes.has(n.id);
    const labelled = keepNodes ? keepNodes.has(n.id) : top.has(n.id);
    return { id: n.id, opacity: on ? 1 : GRAPH.faded, label: n.id === hovered ? n.full : labelled ? n.short : "" };
  }));
  edges.update(edges.get().map(e => {
    const lit = keepEdges.has(e.id);
    const faded = keepNodes && !lit;
    return { id: e.id, width: lit ? 2 : 1, color: { color: lit ? GRAPH.edgeOn : faded ? "rgba(196, 202, 209, 0.15)" : GRAPH.edge } };
  }));
}

function applyGraphOrphans() {
  if (!graph) return;
  const show = graphOrphans.checked;
  graph.nodes.update(graph.nodes.get().map(n => ({ id: n.id, hidden: !show && n.degree === 0 })));
}

graphSearch.addEventListener("input", applyGraphFocus);
graphLabels.addEventListener("change", () => {
  try { localStorage.setItem("graphLabels", graphLabels.value); } catch {}
  applyGraphFocus();
});
graphOrphans.addEventListener("change", applyGraphOrphans);

// ---------- paper detail: summary + Q&A ----------
const EXAMPLE_QUESTIONS = [
  "What problem does this paper address?",
  "What is the main idea of the proposed approach?",
  "What datasets are used?",
  "What are the major limitations?",
  "How does this method compare with the baselines?",
];

// LLM output is Markdown; render it, but sanitize first. Falls back to plain text if the CDN libs didn't load.
// LLM output is Markdown that may contain LaTeX ($...$ / $$...$$). Math is pulled out first (Markdown
// would turn subscript underscores into italics), rendered with KaTeX, and put back after sanitizing.
const MATH = /\$\$([\s\S]+?)\$\$|\$(?![\s\d])([^$\n]+?)(?<!\s)\$/g;  // "$5 and $10" is not math

function markdown(text) {
  const node = el("div", { class: "markdown" });
  if (!(window.marked && window.DOMPurify)) {
    node.textContent = text;
    return node;
  }
  const rendered = [];
  if (window.katex) {
    text = text.replace(MATH, (_, display, inline) => {
      rendered.push(katex.renderToString(display ?? inline, { displayMode: display != null, throwOnError: false, output: "html" }));
      return `KATEXMATH${rendered.length - 1}END`;
    });
  }
  node.innerHTML = DOMPurify.sanitize(marked.parse(text)).replace(/KATEXMATH(\d+)END/g, (_, i) => rendered[i]);
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
