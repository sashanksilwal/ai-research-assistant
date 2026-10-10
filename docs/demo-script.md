# Demo video — narration script

About 3½ minutes. Read each **Say** block while the matching scene plays; the recording pauses on each scene for about as long as its narration (~150 words per minute). Scene numbers match `scripts/record_demo.py`.

---

### 1 · Intro — search page, empty (≈15 s)
**On screen:** the home search page with suggested topics.
**Say:**
> This is my AI Research Assistant for CS593. It lets you search for papers, save them to a local library, upload your own PDFs, and use Gemini to summarize a paper and answer questions about it. I built it with Claude Code; the stack is FastAPI, SQLite, the arXiv API and Gemini.

### 2 · Search (≈20 s)
**On screen:** click the suggested topic "automated program repair"; results appear and scroll.
**Say:**
> Searching uses the arXiv API. I'll click one of the suggested topics, automated program repair. Each result shows the title, authors, year and abstract, with links to the paper and its PDF. I chose arXiv on purpose, because every result has a PDF, so the app can work with the full text later.

### 3 · Save to library (≈15 s)
**On screen:** click "Save to library" on the first result; it changes to "Saved ✓".
**Say:**
> When I save a paper, the backend stores its metadata in SQLite, downloads the PDF and extracts the full text with PyMuPDF. That full text is what the summary and the questions use later.

### 4 · Library (≈15 s)
**On screen:** the Library tab, scrolling past saved papers with their badges.
**Say:**
> The Library tab lists everything I've saved. It's stored in a local SQLite database, so it survives refreshing the page and restarting the server. Each paper shows whether its full text is ready.

### 5 · Upload a PDF (≈25 s)
**On screen:** choose `self-refine.pdf`, click Upload, wait for "Added …", the new card appears.
**Say:**
> I can also upload my own PDF. Here's the Self-Refine paper. The app extracts the text, then asks Gemini to pull out the title, authors, year and abstract from the first pages, with a fallback to the PDF's own metadata if Gemini is unavailable. The uploaded paper is shown just like a search result.

### 6 · Summary (≈30 s)
**On screen:** open the uploaded paper, click "Summarize with Gemini", the summary appears and scrolls.
**Say:**
> Opening the paper, I'll ask for a summary. The app sends the paper's full text to Gemini, minus the reference list, not just the abstract. So the summary covers the problem, the approach, the experiments, the key results with numbers, and the limitations. Summaries are cached in the database, so the second time it's instant.

### 7 · Questions (≈40 s)
**On screen:** click the example question "What datasets are used?"; then type "How does it compare with the baselines?"; then type "Who won the 2022 FIFA World Cup?".
**Say:**
> Next, questions in plain English. These chips are the example questions from the assignment. "What datasets are used" gets an answer from the experiments section. I can also type my own question, like how it compares with the baselines. And if I ask something the paper doesn't cover, like who won the World Cup, it says the paper doesn't say, instead of making something up, because the prompt tells Gemini to answer only from the paper.

### 8 · Extra: citation graph (≈25 s)
**On screen:** Library → "Show citation graph"; hover a well-connected paper; change Labels to Top 10.
**Say:**
> One extra feature: a citation graph of my library. Reference lists come from Semantic Scholar and OpenAlex, and an arrow means one paper cites another. Hovering a paper highlights what it cites and what cites it, and bigger dots are the papers with more links.

### 9 · Close (≈10 s)
**On screen:** back to the search page.
**Say:**
> So that's search, save, upload, summarize, and ask. The code, README and setup instructions are in the GitHub repository. Thanks for watching.
