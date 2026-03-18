from __future__ import annotations

PANEL_HTML = r"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ctx panel</title>
    <style>
      :root {
        --paper: #f4efe4;
        --ink: #1e2d2f;
        --muted: #5f6f69;
        --line: #d4c5a8;
        --accent: #b85c38;
        --accent-2: #2f6f65;
        --panel: rgba(255, 251, 242, 0.92);
        --shadow: 0 14px 40px rgba(45, 42, 36, 0.12);
        --mono: "SFMono-Regular", "Menlo", "Consolas", monospace;
        --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(184, 92, 56, 0.18), transparent 28%),
          radial-gradient(circle at top right, rgba(47, 111, 101, 0.16), transparent 24%),
          linear-gradient(180deg, #f7f2e8 0%, #efe4cf 100%);
        font-family: var(--serif);
      }

      .shell {
        display: grid;
        grid-template-columns: 340px minmax(0, 1fr);
        min-height: 100vh;
      }

      .sidebar,
      .main {
        padding: 24px;
      }

      .sidebar {
        border-right: 1px solid rgba(212, 197, 168, 0.85);
        background: rgba(255, 248, 237, 0.82);
        backdrop-filter: blur(8px);
      }

      .main {
        display: grid;
        grid-template-rows: auto auto minmax(0, 1fr);
        gap: 18px;
      }

      .card {
        background: var(--panel);
        border: 1px solid rgba(212, 197, 168, 0.92);
        border-radius: 18px;
        box-shadow: var(--shadow);
        padding: 18px;
      }

      h1,
      h2,
      h3 {
        margin: 0;
        font-weight: 700;
      }

      h1 {
        font-size: 28px;
        letter-spacing: -0.02em;
      }

      h2 {
        font-size: 18px;
        margin-bottom: 12px;
      }

      p,
      li,
      label,
      button,
      input,
      textarea,
      code,
      pre,
      span,
      small,
      td,
      th {
        font-size: 14px;
      }

      .lede {
        margin-top: 10px;
        color: var(--muted);
        line-height: 1.5;
      }

      .field {
        display: grid;
        gap: 6px;
        margin-bottom: 12px;
      }

      .field:last-child {
        margin-bottom: 0;
      }

      label {
        font-weight: 700;
        color: var(--muted);
      }

      input,
      textarea,
      select,
      button {
        border-radius: 12px;
        border: 1px solid var(--line);
      }

      input,
      textarea,
      select {
        width: 100%;
        padding: 10px 12px;
        color: var(--ink);
        background: rgba(255, 255, 255, 0.88);
      }

      input,
      textarea,
      pre,
      code {
        font-family: var(--mono);
      }

      textarea {
        min-height: 300px;
        resize: vertical;
        line-height: 1.5;
      }

      button {
        cursor: pointer;
        padding: 10px 14px;
        background: #fff7eb;
        transition: transform 140ms ease, background 140ms ease, border-color 140ms ease;
      }

      button:hover {
        transform: translateY(-1px);
        border-color: var(--accent);
        background: #fff3e2;
      }

      .button-row {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .button-row button.primary {
        color: #fff;
        background: linear-gradient(135deg, var(--accent), #ca7746);
        border-color: transparent;
      }

      .button-row button.secondary {
        background: rgba(47, 111, 101, 0.08);
        border-color: rgba(47, 111, 101, 0.26);
      }

      .button-row button.danger {
        background: rgba(184, 92, 56, 0.1);
        border-color: rgba(184, 92, 56, 0.32);
      }

      .pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 5px 10px;
        border-radius: 999px;
        border: 1px solid var(--line);
        color: var(--muted);
        background: rgba(255, 255, 255, 0.75);
      }

      .status {
        min-height: 24px;
        color: var(--muted);
        line-height: 1.4;
      }

      .status.error {
        color: #9f2f17;
      }

      .status.ok {
        color: #2f6f65;
      }

      .tree,
      .breadcrumbs {
        margin: 0;
        padding: 0;
        list-style: none;
      }

      .tree li {
        margin: 6px 0;
      }

      .tree ul {
        list-style: none;
        margin: 6px 0 0 18px;
        padding: 0 0 0 12px;
        border-left: 1px dashed rgba(95, 111, 105, 0.42);
      }

      .tree button,
      .breadcrumbs button,
      .entry-name {
        border: none;
        background: transparent;
        padding: 0;
        font: inherit;
        text-align: left;
        color: var(--ink);
      }

      .tree button:hover,
      .breadcrumbs button:hover,
      .entry-name:hover {
        color: var(--accent);
        transform: none;
      }

      .tree .kind,
      .entry-kind {
        color: var(--accent-2);
        font-family: var(--mono);
        margin-right: 8px;
      }

      .overview {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
      }

      .metric {
        border-radius: 14px;
        border: 1px solid rgba(212, 197, 168, 0.92);
        padding: 14px;
        background: rgba(255, 255, 255, 0.72);
      }

      .metric .label {
        color: var(--muted);
        margin-bottom: 6px;
      }

      .metric .value {
        font-size: 20px;
        font-weight: 700;
      }

      .workspace-layout {
        display: grid;
        grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
        gap: 18px;
        min-height: 0;
      }

      .entries {
        width: 100%;
        border-collapse: collapse;
      }

      .entries th,
      .entries td {
        text-align: left;
        padding: 10px 8px;
        border-bottom: 1px solid rgba(212, 197, 168, 0.7);
        vertical-align: top;
      }

      .entries th {
        color: var(--muted);
      }

      .entries td:last-child,
      .entries th:last-child {
        width: 116px;
      }

      .meta-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
        margin-bottom: 14px;
      }

      .meta-card {
        border-radius: 14px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(212, 197, 168, 0.92);
      }

      .meta-card .label {
        color: var(--muted);
        margin-bottom: 6px;
      }

      .meta-card .value {
        font-family: var(--mono);
        word-break: break-word;
      }

      .hint {
        margin-top: 10px;
        color: var(--muted);
        line-height: 1.5;
      }

      .hidden {
        display: none;
      }

      .search-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
      }

      .search-grid .field:first-child,
      .search-grid .field.scope-field {
        grid-column: 1 / -1;
      }

      .search-results {
        display: grid;
        gap: 12px;
        max-height: 420px;
        overflow: auto;
      }

      .search-hit {
        border-radius: 16px;
        border: 1px solid rgba(212, 197, 168, 0.92);
        background: rgba(255, 255, 255, 0.72);
        padding: 14px;
      }

      .search-hit h3 {
        margin-top: 10px;
        font-size: 16px;
      }

      .search-snippet {
        margin: 10px 0 0;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(47, 111, 101, 0.07);
        border: 1px solid rgba(47, 111, 101, 0.14);
        white-space: pre-wrap;
        word-break: break-word;
        line-height: 1.5;
      }

      .reason-list {
        margin: 10px 0 0;
        padding-left: 18px;
        color: var(--muted);
      }

      .checkbox {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .checkbox input {
        width: auto;
        margin: 0;
      }

      @media (max-width: 1100px) {
        .shell {
          grid-template-columns: 1fr;
        }

        .sidebar {
          border-right: none;
          border-bottom: 1px solid rgba(212, 197, 168, 0.85);
        }

        .workspace-layout,
        .overview,
        .search-grid {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <aside class="sidebar">
        <div class="card">
          <div class="pill">ctx panel / browse-first mvp</div>
          <h1 style="margin-top: 12px;">Know What Is In ctx</h1>
          <p class="lede">Use this panel to browse `ctx://` workspaces, inspect files, and make small deliberate updates without guessing the current tree from memory.</p>
        </div>

        <div class="card" style="margin-top: 18px;">
          <h2>Connection</h2>
          <div class="field">
            <label for="token">Bearer token</label>
            <input id="token" type="password" placeholder="Paste token once; stored in this browser">
          </div>
          <div class="field">
            <label for="userId">Default userId</label>
            <input id="userId" type="text" placeholder="shiuing">
          </div>
          <div class="field">
            <label for="treeDepth">Tree depth</label>
            <input id="treeDepth" type="number" min="1" max="8" value="3">
          </div>
          <div class="button-row">
            <button id="saveToken" class="primary">Save local settings</button>
            <button id="clearToken" class="secondary">Clear local settings</button>
          </div>
          <p class="hint">The page itself is safe to load without auth, but all data fetches still require the same bearer token as the filesystem API.</p>
        </div>

        <div class="card" style="margin-top: 18px; min-height: 240px;">
          <h2>Tree</h2>
          <ul id="tree" class="tree"></ul>
        </div>
      </aside>

      <main class="main">
        <section class="card">
          <div class="field">
            <label for="currentUri">Current URI</label>
            <input id="currentUri" type="text" placeholder="ctx://shiuing/defaultWorkspace">
          </div>
          <div class="button-row">
            <button id="loadPath" class="primary">Load</button>
            <button id="goUserRoot" class="secondary">User root</button>
            <button id="goDefault" class="secondary">defaultWorkspace</button>
            <button id="goDocs" class="secondary">docs</button>
            <button id="goMemory" class="secondary">memory</button>
          </div>
          <ul id="breadcrumbs" class="breadcrumbs" style="margin-top: 14px;"></ul>
          <div id="status" class="status" style="margin-top: 14px;"></div>
        </section>

        <section class="card">
          <h2>Search</h2>
          <div class="search-grid">
            <div class="field">
              <label for="searchQuery">Query</label>
              <input id="searchQuery" type="text" placeholder="cloud cutover / 24040 / import-tree">
            </div>
            <div class="field">
              <label for="searchMode">Mode</label>
              <select id="searchMode">
                <option value="auto">auto</option>
                <option value="lexical">lexical</option>
                <option value="semantic">semantic</option>
                <option value="hybrid">hybrid</option>
              </select>
            </div>
            <div class="field">
              <label for="searchWorkspaceMode">Workspace mode</label>
              <select id="searchWorkspaceMode">
                <option value="default-only" selected>default-only</option>
                <option value="default-first">default-first</option>
                <option value="user">user</option>
              </select>
            </div>
            <div class="field">
              <label for="searchExpansions">Expansions</label>
              <input id="searchExpansions" type="text" placeholder="import-tree, 24040, plugin mismatch">
            </div>
            <div class="field">
              <label for="searchGlob">Glob</label>
              <input id="searchGlob" type="text" placeholder="*.md">
            </div>
            <div class="field">
              <label for="searchPathPrefix">Path prefix</label>
              <input id="searchPathPrefix" type="text" placeholder="archive/2026 or docs">
            </div>
            <div class="field scope-field">
              <label for="searchScope">Optional scope URI</label>
              <input id="searchScope" type="text" placeholder="Leave empty to use workspace mode; or set ctx://.../docs">
            </div>
          </div>
          <div class="button-row">
            <button id="runSearch" class="primary">Run search</button>
            <button id="scopeCurrentPath" class="secondary">Use current path as scope</button>
            <button id="clearSearchScope" class="secondary">Clear scope</button>
            <label class="checkbox" style="margin-left: auto;">
              <input id="searchRerank" type="checkbox" checked>
              <span>rerank</span>
            </label>
            <label class="checkbox">
              <input id="searchExplain" type="checkbox" checked>
              <span>explain</span>
            </label>
          </div>
          <div id="searchStatus" class="status" style="margin-top: 12px;"></div>
          <div id="searchMeta" class="hint hidden" style="margin-top: 10px;"></div>
          <div id="searchResults" class="search-results" style="margin-top: 14px;"></div>
        </section>

        <section class="overview">
          <div class="metric">
            <div class="label">Kind</div>
            <div id="metricKind" class="value">-</div>
          </div>
          <div class="metric">
            <div class="label">Children / lines</div>
            <div id="metricCount" class="value">-</div>
          </div>
          <div class="metric">
            <div class="label">Size</div>
            <div id="metricSize" class="value">-</div>
          </div>
        </section>

        <section class="workspace-layout">
          <section class="card" style="min-height: 0;">
            <h2>Entries</h2>
            <table class="entries">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Kind</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody id="entriesBody"></tbody>
            </table>
            <div id="entriesEmpty" class="hint hidden">No directory entries to show for this path.</div>
          </section>

          <section class="card" style="min-height: 0; display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); gap: 14px;">
            <div>
              <h2>Content</h2>
              <div class="hint">Browse-first MVP: read everything, overwrite current file deliberately, create directories, and remove paths when you mean it.</div>
            </div>

            <div class="meta-grid">
              <div class="meta-card">
                <div class="label">Current path</div>
                <div id="metaUri" class="value">-</div>
              </div>
              <div class="meta-card">
                <div class="label">Current name</div>
                <div id="metaName" class="value">-</div>
              </div>
            </div>

            <div>
              <div class="field">
                <label for="newDirName">Create child directory</label>
                <input id="newDirName" type="text" placeholder="tasks or docs/new-folder">
              </div>
              <div class="button-row">
                <button id="createDir" class="secondary">Create directory</button>
                <button id="refreshView" class="secondary">Refresh</button>
                <label class="checkbox" style="margin-left: auto;">
                  <input id="recursiveDelete" type="checkbox">
                  <span>recursive delete</span>
                </label>
                <button id="deletePath" class="danger">Delete current path</button>
              </div>
            </div>

            <div style="min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; gap: 10px;">
              <label for="fileContent">File content</label>
              <textarea id="fileContent" placeholder="Open a file to preview or edit it."></textarea>
              <div class="button-row">
                <button id="saveFile" class="primary">Overwrite current file</button>
              </div>
            </div>
          </section>
        </section>
      </main>
    </div>

    <script>
      const tokenInput = document.getElementById("token");
      const userIdInput = document.getElementById("userId");
      const treeDepthInput = document.getElementById("treeDepth");
      const currentUriInput = document.getElementById("currentUri");
      const statusEl = document.getElementById("status");
      const treeEl = document.getElementById("tree");
      const breadcrumbsEl = document.getElementById("breadcrumbs");
      const entriesBody = document.getElementById("entriesBody");
      const entriesEmpty = document.getElementById("entriesEmpty");
      const fileContent = document.getElementById("fileContent");
      const newDirNameInput = document.getElementById("newDirName");
      const recursiveDeleteInput = document.getElementById("recursiveDelete");
      const searchQueryInput = document.getElementById("searchQuery");
      const searchModeInput = document.getElementById("searchMode");
      const searchWorkspaceModeInput = document.getElementById("searchWorkspaceMode");
      const searchExpansionsInput = document.getElementById("searchExpansions");
      const searchGlobInput = document.getElementById("searchGlob");
      const searchPathPrefixInput = document.getElementById("searchPathPrefix");
      const searchScopeInput = document.getElementById("searchScope");
      const searchRerankInput = document.getElementById("searchRerank");
      const searchExplainInput = document.getElementById("searchExplain");
      const searchStatusEl = document.getElementById("searchStatus");
      const searchMetaEl = document.getElementById("searchMeta");
      const searchResultsEl = document.getElementById("searchResults");

      let currentStat = null;

      function setStatus(message, kind = "") {
        statusEl.textContent = message;
        statusEl.className = `status ${kind}`.trim();
      }

      function setSearchStatus(message, kind = "") {
        searchStatusEl.textContent = message;
        searchStatusEl.className = `status ${kind}`.trim();
      }

      function getStored(key, fallback = "") {
        try {
          return window.localStorage.getItem(key) || fallback;
        } catch {
          return fallback;
        }
      }

      function setStored(key, value) {
        try {
          window.localStorage.setItem(key, value);
        } catch {
          // ignore localStorage failures
        }
      }

      function defaultUserId() {
        return userIdInput.value.trim() || "shiuing";
      }

      function defaultUserRoot() {
        return `ctx://${defaultUserId()}`;
      }

      function defaultWorkspace() {
        return `${defaultUserRoot()}/defaultWorkspace`;
      }

      function normalizeCurrentUri() {
        const raw = currentUriInput.value.trim();
        return raw || defaultWorkspace();
      }

      function parentUri(uri) {
        const trimmed = uri.replace(/\/$/, "");
        if (!trimmed.startsWith("ctx://")) return trimmed;
        const withoutScheme = trimmed.slice("ctx://".length);
        const parts = withoutScheme.split("/");
        if (parts.length <= 1) return trimmed;
        if (parts.length === 2) return `ctx://${parts[0]}`;
        return `ctx://${parts.slice(0, -1).join("/")}`;
      }

      function treeRootUri(uri) {
        if (currentStat && currentStat.kind === "file") return parentUri(uri);
        return uri;
      }

      async function apiRequest(path, options = {}) {
        const token = tokenInput.value.trim();
        const headers = { Accept: "application/json", ...(options.headers || {}) };
        if (token) headers.Authorization = `Bearer ${token}`;
        const response = await fetch(path, { ...options, headers });
        const text = await response.text();
        if (!response.ok) {
          throw new Error(`${response.status} ${text || response.statusText}`);
        }
        return text ? JSON.parse(text) : null;
      }

      function renderTreeNode(node) {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.innerHTML = `<span class="kind">${node.kind === "dir" ? "[dir]" : "[file]"}</span>${escapeHtml(node.name || node.uri)}`;
        button.addEventListener("click", () => {
          currentUriInput.value = node.uri;
          loadPath();
        });
        item.appendChild(button);

        if (Array.isArray(node.children) && node.children.length > 0) {
          const childList = document.createElement("ul");
          node.children.forEach((child) => childList.appendChild(renderTreeNode(child)));
          item.appendChild(childList);
        }

        return item;
      }

      function renderEntries(entries) {
        entriesBody.innerHTML = "";
        entriesEmpty.classList.toggle("hidden", entries.length !== 0);
        entries.forEach((entry) => {
          const row = document.createElement("tr");

          const nameCell = document.createElement("td");
          const openName = document.createElement("button");
          openName.type = "button";
          openName.className = "entry-name";
          openName.textContent = entry.name;
          openName.addEventListener("click", () => {
            currentUriInput.value = entry.uri;
            loadPath();
          });
          nameCell.appendChild(openName);

          const kindCell = document.createElement("td");
          kindCell.innerHTML = `<span class="entry-kind">${entry.kind}</span>`;

          const actionCell = document.createElement("td");
          const openButton = document.createElement("button");
          openButton.type = "button";
          openButton.className = "secondary";
          openButton.textContent = "Open";
          openButton.addEventListener("click", () => {
            currentUriInput.value = entry.uri;
            loadPath();
          });
          actionCell.appendChild(openButton);

          row.append(nameCell, kindCell, actionCell);
          entriesBody.appendChild(row);
        });
      }

      function renderBreadcrumbs(uri) {
        breadcrumbsEl.innerHTML = "";
        const trimmed = uri.replace(/\/$/, "");
        const pieces = trimmed.startsWith("ctx://") ? trimmed.slice("ctx://".length).split("/") : [trimmed];
        let current = trimmed.startsWith("ctx://") ? "ctx://" : "";
        pieces.forEach((piece, index) => {
          if (trimmed.startsWith("ctx://")) {
            current = index === 0 ? `ctx://${piece}` : `${current}/${piece}`;
          } else {
            current = index === 0 ? piece : `${current}/${piece}`;
          }
          const item = document.createElement("li");
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = index === 0 && trimmed.startsWith("ctx://") ? `ctx://${piece}` : piece;
          const nextUri = current;
          button.addEventListener("click", () => {
            currentUriInput.value = nextUri;
            loadPath();
          });
          item.appendChild(button);
          if (index < pieces.length - 1) {
            item.appendChild(document.createTextNode(" / "));
          }
          breadcrumbsEl.appendChild(item);
        });
      }

      function updateMetrics(stat) {
        document.getElementById("metricKind").textContent = stat?.kind || "-";
        document.getElementById("metricCount").textContent = stat?.kind === "dir"
          ? String(stat.childCount ?? 0)
          : String(stat?.lineCount ?? 0);
        document.getElementById("metricSize").textContent = stat?.sizeBytes == null ? "-" : `${stat.sizeBytes} B`;
        document.getElementById("metaUri").textContent = stat?.uri || "-";
        document.getElementById("metaName").textContent = stat?.name || "-";
      }

      function searchExpansions() {
        return searchExpansionsInput.value
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
      }

      function renderSearchResults(result) {
        searchResultsEl.innerHTML = "";
        const hits = result?.hits || [];
        const plan = result?.plan || {};
        const metaParts = [
          `source ${plan.source || "-"}`,
          `mode ${result?.mode || "-"}`,
          result?.scopeUri ? `scope ${result.scopeUri}` : "scope from workspace mode",
          `candidates ${plan.candidateCount ?? 0}`,
        ];
        if (plan.semantic) metaParts.push("semantic on");
        if (plan.rerank) metaParts.push("rerank on");
        if (plan.fallback) metaParts.push(`fallback: ${plan.fallback}`);
        searchMetaEl.textContent = metaParts.join(" · ");
        searchMetaEl.classList.remove("hidden");

        if (hits.length === 0) {
          const empty = document.createElement("div");
          empty.className = "hint";
          empty.textContent = "No search hits for this query.";
          searchResultsEl.appendChild(empty);
          return;
        }

        hits.forEach((hit) => {
          const card = document.createElement("div");
          card.className = "search-hit";
          const reasons = (hit.reasons || []).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
          const meta = [
            `score ${Number(hit.score || 0).toFixed(3)}`,
            hit.lineNumber ? `line ${hit.lineNumber}` : null,
            hit.docType || null,
            hit.workspaceKind === "agentWorkspace" && hit.agentId ? `agent:${hit.agentId}` : hit.workspaceKind,
          ].filter(Boolean).join(" · ");
          card.innerHTML = `
            <div class="button-row" style="justify-content: space-between; align-items: flex-start;">
              <div>
                <div class="pill">${escapeHtml(hit.docType || "file")} / ${escapeHtml(hit.workspaceKind || "-")}</div>
                <h3>${escapeHtml(hit.title || hit.uri)}</h3>
                <div class="hint">${escapeHtml(hit.uri)}</div>
              </div>
              <button type="button" class="secondary open-search-hit">Open</button>
            </div>
            <div class="hint" style="margin-top: 10px;">${escapeHtml(meta)}</div>
            <div class="search-snippet">${escapeHtml(hit.snippet || "")}</div>
            ${reasons ? `<ul class="reason-list">${reasons}</ul>` : ""}
          `;
          card.querySelector(".open-search-hit").addEventListener("click", () => {
            currentUriInput.value = hit.uri;
            loadPath();
          });
          searchResultsEl.appendChild(card);
        });
      }

      async function runSearch() {
        const query = searchQueryInput.value.trim();
        if (!query) {
          setSearchStatus("Search query is required.", "error");
          return;
        }
        const payload = {
          userId: defaultUserId(),
          query,
          scopeUri: searchScopeInput.value.trim() || null,
          mode: searchModeInput.value,
          expansions: searchExpansions(),
          glob: searchGlobInput.value.trim() || null,
          pathPrefix: searchPathPrefixInput.value.trim() || null,
          workspaceMode: searchWorkspaceModeInput.value,
          rerank: searchRerankInput.checked,
          explain: searchExplainInput.checked,
          limit: 10,
        };
        try {
          setStored("ctx-panel-search-query", payload.query);
          setStored("ctx-panel-search-mode", payload.mode);
          setStored("ctx-panel-search-workspace-mode", payload.workspaceMode);
          setStored("ctx-panel-search-expansions", searchExpansionsInput.value);
          setStored("ctx-panel-search-glob", searchGlobInput.value);
          setStored("ctx-panel-search-prefix", searchPathPrefixInput.value);
          setStored("ctx-panel-search-scope", searchScopeInput.value);
          setSearchStatus(`Searching ${payload.workspaceMode} ...`);
          const result = await apiRequest("/v1/fs/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          renderSearchResults(result);
          setSearchStatus(`Found ${(result.hits || []).length} hit(s).`, "ok");
        } catch (error) {
          searchMetaEl.classList.add("hidden");
          searchResultsEl.innerHTML = "";
          setSearchStatus(String(error), "error");
        }
      }

      async function refreshTree(uri) {
        const root = treeRootUri(uri);
        const depth = Math.max(1, Number(treeDepthInput.value || 3));
        const tree = await apiRequest(`/v1/fs/tree?uri=${encodeURIComponent(root)}&depth=${depth}`);
        treeEl.innerHTML = "";
        treeEl.appendChild(renderTreeNode(tree));
      }

      async function loadPath() {
        const uri = normalizeCurrentUri();
        currentUriInput.value = uri;
        renderBreadcrumbs(uri);
        setStored("ctx-panel-uri", uri);
        setStored("ctx-panel-user", defaultUserId());
        currentStat = null;
        fileContent.value = "";
        try {
          setStatus(`Loading ${uri} ...`);
          const stat = await apiRequest(`/v1/fs/stat?uri=${encodeURIComponent(uri)}`);
          currentStat = stat;
          updateMetrics(stat);

          if (stat.kind === "dir") {
            const listing = await apiRequest(`/v1/fs/ls?uri=${encodeURIComponent(uri)}`);
            renderEntries(listing.entries || []);
            fileContent.placeholder = "Open a file to preview or edit it.";
            fileContent.value = "";
          } else {
            renderEntries([]);
            const read = await apiRequest(`/v1/fs/read?uri=${encodeURIComponent(uri)}`);
            fileContent.value = read.text || "";
          }

          await refreshTree(uri);
          setStatus(`Loaded ${uri}`, "ok");
        } catch (error) {
          renderEntries([]);
          treeEl.innerHTML = "";
          updateMetrics(null);
          setStatus(String(error), "error");
        }
      }

      async function createDirectory() {
        const currentUri = normalizeCurrentUri();
        if (!currentStat || currentStat.kind !== "dir") {
          setStatus("Open a directory before creating a child directory.", "error");
          return;
        }
        const name = newDirNameInput.value.trim();
        if (!name) {
          setStatus("Directory name is required.", "error");
          return;
        }
        const nextUri = `${currentUri.replace(/\/$/, "")}/${name}`;
        try {
          setStatus(`Creating ${nextUri} ...`);
          await apiRequest("/v1/fs/mkdir", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ uri: nextUri, parents: true }),
          });
          newDirNameInput.value = "";
          currentUriInput.value = nextUri;
          await loadPath();
        } catch (error) {
          setStatus(String(error), "error");
        }
      }

      async function saveFile() {
        const uri = normalizeCurrentUri();
        if (!currentStat || currentStat.kind !== "file") {
          setStatus("Open a file before saving.", "error");
          return;
        }
        try {
          setStatus(`Overwriting ${uri} ...`);
          await apiRequest("/v1/fs/write", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              uri,
              text: fileContent.value,
              createParents: true,
              overwrite: true,
            }),
          });
          await loadPath();
        } catch (error) {
          setStatus(String(error), "error");
        }
      }

      async function deleteCurrentPath() {
        const uri = normalizeCurrentUri();
        if (!currentStat) {
          setStatus("Open a path before deleting it.", "error");
          return;
        }
        const recursive = recursiveDeleteInput.checked;
        const confirmed = window.confirm(`Delete ${uri}?${recursive ? " (recursive)" : ""}`);
        if (!confirmed) return;
        try {
          setStatus(`Deleting ${uri} ...`);
          await apiRequest("/v1/fs/rm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ uri, recursive }),
          });
          currentUriInput.value = parentUri(uri);
          await loadPath();
        } catch (error) {
          setStatus(String(error), "error");
        }
      }

      function escapeHtml(value) {
        return String(value)
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#39;");
      }

      document.getElementById("saveToken").addEventListener("click", () => {
        setStored("ctx-panel-token", tokenInput.value.trim());
        setStored("ctx-panel-user", defaultUserId());
        setStored("ctx-panel-depth", treeDepthInput.value.trim());
        setStored("ctx-panel-search-query", searchQueryInput.value.trim());
        setStored("ctx-panel-search-mode", searchModeInput.value);
        setStored("ctx-panel-search-workspace-mode", searchWorkspaceModeInput.value);
        setStored("ctx-panel-search-expansions", searchExpansionsInput.value);
        setStored("ctx-panel-search-glob", searchGlobInput.value);
        setStored("ctx-panel-search-prefix", searchPathPrefixInput.value);
        setStored("ctx-panel-search-scope", searchScopeInput.value);
        setStatus("Panel settings saved in browser localStorage.", "ok");
      });

      document.getElementById("clearToken").addEventListener("click", () => {
        [
          "ctx-panel-token",
          "ctx-panel-user",
          "ctx-panel-uri",
          "ctx-panel-depth",
          "ctx-panel-search-query",
          "ctx-panel-search-mode",
          "ctx-panel-search-workspace-mode",
          "ctx-panel-search-expansions",
          "ctx-panel-search-glob",
          "ctx-panel-search-prefix",
          "ctx-panel-search-scope",
        ].forEach((key) => {
          try {
            window.localStorage.removeItem(key);
          } catch {
            // ignore localStorage failures
          }
        });
        tokenInput.value = "";
        userIdInput.value = "shiuing";
        currentUriInput.value = defaultWorkspace();
        treeDepthInput.value = "3";
        searchQueryInput.value = "";
        searchModeInput.value = "auto";
        searchWorkspaceModeInput.value = "default-only";
        searchExpansionsInput.value = "";
        searchGlobInput.value = "";
        searchPathPrefixInput.value = "";
        searchScopeInput.value = "";
        searchResultsEl.innerHTML = "";
        searchMetaEl.classList.add("hidden");
        setSearchStatus("");
        setStatus("Panel settings cleared from browser localStorage.", "ok");
      });

      document.getElementById("loadPath").addEventListener("click", loadPath);
      document.getElementById("refreshView").addEventListener("click", loadPath);
      document.getElementById("createDir").addEventListener("click", createDirectory);
      document.getElementById("saveFile").addEventListener("click", saveFile);
      document.getElementById("deletePath").addEventListener("click", deleteCurrentPath);
      document.getElementById("runSearch").addEventListener("click", runSearch);
      document.getElementById("scopeCurrentPath").addEventListener("click", () => {
        searchScopeInput.value = normalizeCurrentUri();
        setSearchStatus(`Search scope set to ${searchScopeInput.value}`, "ok");
      });
      document.getElementById("clearSearchScope").addEventListener("click", () => {
        searchScopeInput.value = "";
        setSearchStatus("Search scope cleared; workspace mode will decide the scope.", "ok");
      });

      document.getElementById("goUserRoot").addEventListener("click", () => {
        currentUriInput.value = defaultUserRoot();
        loadPath();
      });
      document.getElementById("goDefault").addEventListener("click", () => {
        currentUriInput.value = defaultWorkspace();
        loadPath();
      });
      document.getElementById("goDocs").addEventListener("click", () => {
        currentUriInput.value = `${defaultWorkspace()}/docs`;
        loadPath();
      });
      document.getElementById("goMemory").addEventListener("click", () => {
        currentUriInput.value = `${defaultWorkspace()}/memory`;
        loadPath();
      });

      tokenInput.value = getStored("ctx-panel-token", "");
      userIdInput.value = getStored("ctx-panel-user", "shiuing");
      treeDepthInput.value = getStored("ctx-panel-depth", "3");
      currentUriInput.value = getStored("ctx-panel-uri", defaultWorkspace());
      searchQueryInput.value = getStored("ctx-panel-search-query", "");
      searchModeInput.value = getStored("ctx-panel-search-mode", "auto");
      searchWorkspaceModeInput.value = getStored("ctx-panel-search-workspace-mode", "default-only");
      searchExpansionsInput.value = getStored("ctx-panel-search-expansions", "");
      searchGlobInput.value = getStored("ctx-panel-search-glob", "");
      searchPathPrefixInput.value = getStored("ctx-panel-search-prefix", "");
      searchScopeInput.value = getStored("ctx-panel-search-scope", "");
      loadPath();
    </script>
  </body>
</html>
"""
