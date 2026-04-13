/* krabb dashboard — main application */

var API = "http://127.0.0.1:4243";

// ---- State ----

var state = {
  tab: "overview",
  events: { data: [], total: 0, page: 1, pageSize: 50 },
  filters: { tool: "", decision: "", search: "", group_by: "", date_from: "", date_to: "" },
  selectedEvent: null,
  detailOpen: false,
  config: {},
  feedFilter: "",
  overviewEvents: [],
};

// ---- API client ----

var api = {
  get: function (path) {
    return fetch(API + path).then(function (r) { return r.json(); });
  },
  post: function (path, body) {
    return fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); });
  },
  put: function (path, body) {
    return fetch(API + path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); });
  },
  del: function (path, body) {
    return fetch(API + path, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) { return r.json(); });
  },
};

// ---- Tab switching ----

document.querySelectorAll(".nav-tab").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var tab = this.getAttribute("data-tab");
    switchTab(tab);
  });
});

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".nav-tab").forEach(function (b) {
    b.classList.toggle("active", b.getAttribute("data-tab") === tab);
  });
  document.querySelectorAll(".tab-content").forEach(function (c) {
    var isActive = c.id === "tab-" + tab;
    c.classList.toggle("active", isActive);
    c.style.display = isActive ? "block" : "none";
  });
  refreshCurrentTab();
}

// ---- Overview Tab ----

function fetchOverview() {
  var statsPromise = api.get("/stats");
  var eventsPromise = api.get("/events?limit=50");

  Promise.all([statsPromise, eventsPromise]).then(function (results) {
    var stats = results[0];
    var eventsData = results[1];
    var events = eventsData.events || [];
    state.overviewEvents = events;
    setStatus("live");

    // Stat cards
    document.getElementById("stat-total").textContent = stats.total_today != null ? stats.total_today : "—";
    document.getElementById("stat-blocked").textContent = stats.blocked_today != null ? stats.blocked_today : "—";
    document.getElementById("stat-domain").textContent = stats.top_domain || "—";
    document.getElementById("stat-sessions").textContent = stats.active_sessions != null ? stats.active_sessions : "—";

    // Tool breakdown — prefer server data, fallback to computing from events
    var byTool = stats.by_tool;
    if (!byTool || Object.keys(byTool).length === 0) {
      byTool = {};
      events.forEach(function (e) {
        byTool[e.tool] = (byTool[e.tool] || 0) + 1;
      });
    }
    renderToolBreakdown(byTool);

    // Render filter chips for activity feed
    renderFeedFilters(events);

    // Render activity feed
    renderActivityFeed(events, state.feedFilter);
  }).catch(function () { setStatus("offline"); });
}

function renderToolBreakdown(byTool) {
  var breakdown = document.getElementById("tool-breakdown");
  var keys = Object.keys(byTool);
  if (keys.length === 0) {
    breakdown.innerHTML = '<div class="empty">No data yet</div>';
    return;
  }
  var total = Object.values(byTool).reduce(function (a, b) { return a + b; }, 0);
  var sorted = Object.entries(byTool).sort(function (a, b) { return b[1] - a[1]; });
  var html = "";
  sorted.forEach(function (entry) {
    var tool = entry[0], count = entry[1];
    var pct = total > 0 ? Math.round((count / total) * 100) : 0;
    html += '<div class="breakdown-row clickable" data-tool="' + escapeHtml(tool) + '">' +
      '<div class="breakdown-label">' + toolBadge(tool) + '</div>' +
      '<div class="breakdown-bar-bg"><div class="breakdown-bar" style="width:' + pct + '%"></div></div>' +
      '<div class="breakdown-value">' + count + '</div>' +
      '</div>';
  });
  breakdown.innerHTML = html;

  // Click breakdown row → switch to Events tab filtered by that tool
  breakdown.querySelectorAll(".breakdown-row.clickable").forEach(function (row) {
    row.addEventListener("click", function () {
      var tool = this.getAttribute("data-tool");
      state.filters.tool = tool;
      state.events.page = 1;
      document.getElementById("filter-tool").value = tool;
      switchTab("events");
    });
  });
}

function renderFeedFilters(events) {
  var container = document.getElementById("feed-filters");
  // Collect unique tools from events
  var toolCounts = {};
  events.forEach(function (e) {
    toolCounts[e.tool] = (toolCounts[e.tool] || 0) + 1;
  });
  var tools = Object.keys(toolCounts).sort();
  if (tools.length <= 1) {
    container.innerHTML = "";
    return;
  }

  var html = '<button class="filter-chip' + (state.feedFilter === "" ? " active" : "") +
    '" data-tool="">All <span class="chip-count">' + events.length + '</span></button>';
  tools.forEach(function (tool) {
    html += '<button class="filter-chip' + (state.feedFilter === tool ? " active" : "") +
      '" data-tool="' + escapeHtml(tool) + '">' + escapeHtml(tool) +
      ' <span class="chip-count">' + toolCounts[tool] + '</span></button>';
  });
  container.innerHTML = html;

  container.querySelectorAll(".filter-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      state.feedFilter = this.getAttribute("data-tool");
      renderFeedFilters(state.overviewEvents);
      renderActivityFeed(state.overviewEvents, state.feedFilter);
    });
  });
}

function renderActivityFeed(events, filter) {
  var feed = document.getElementById("activity-feed");
  var filtered = filter ? events.filter(function (e) { return e.tool === filter; }) : events;
  var shown = filtered.slice(0, 20);

  document.getElementById("feed-count").textContent = shown.length + (filter ? " filtered" : " recent");

  if (shown.length === 0) {
    feed.innerHTML = '<div class="empty">No events' + (filter ? ' for ' + filter : ' yet') + '</div>';
    return;
  }
  feed.innerHTML = shown.map(function (e) {
    var dec = e.decision === "allow"
      ? '<span class="feed-allow">allow</span>'
      : '<span class="feed-deny">deny</span>';
    var summary = escapeHtml(truncate(summarizeInput(e.tool, e.input), 50));
    return '<div class="feed-item">' +
      '<span class="feed-time">' + escapeHtml(formatDateTime(e.ts)) + '</span>' +
      toolBadge(e.tool) +
      '<span class="feed-input" title="' + escapeHtml(summarizeInput(e.tool, e.input)) + '">' + summary + '</span>' +
      dec +
      '</div>';
  }).join("");
}

// ---- Events Tab ----

var _searchTimer = null;

function buildEventsQuery() {
  var params = [];
  params.push("limit=" + state.events.pageSize);
  params.push("offset=" + ((state.events.page - 1) * state.events.pageSize));
  if (state.filters.tool) params.push("tool=" + encodeURIComponent(state.filters.tool));
  if (state.filters.decision) params.push("decision=" + encodeURIComponent(state.filters.decision));
  if (state.filters.search) params.push("search=" + encodeURIComponent(state.filters.search));
  if (state.filters.date_from) params.push("date_from=" + encodeURIComponent(state.filters.date_from));
  if (state.filters.date_to) params.push("date_to=" + encodeURIComponent(state.filters.date_to));
  if (state.filters.group_by) params.push("group_by=" + encodeURIComponent(state.filters.group_by));
  return "?" + params.join("&");
}

function fetchEvents() {
  if (state.filters.group_by) {
    fetchGroupedEvents();
    return;
  }
  var q = buildEventsQuery();
  api.get("/events" + q).then(function (data) {
    var events = data.events || [];
    state.events.data = events;
    renderEventsTable(events);
    renderEventsToolChips();
    setStatus("live");
  }).catch(function () { setStatus("offline"); });

  // Get count for pagination
  var countParams = [];
  if (state.filters.tool) countParams.push("tool=" + encodeURIComponent(state.filters.tool));
  if (state.filters.decision) countParams.push("decision=" + encodeURIComponent(state.filters.decision));
  if (state.filters.search) countParams.push("search=" + encodeURIComponent(state.filters.search));
  if (state.filters.date_from) countParams.push("date_from=" + encodeURIComponent(state.filters.date_from));
  if (state.filters.date_to) countParams.push("date_to=" + encodeURIComponent(state.filters.date_to));
  var countQ = countParams.length > 0 ? "?" + countParams.join("&") : "";
  api.get("/events/count" + countQ).then(function (data) {
    state.events.total = data.count || 0;
    var totalPages = Math.max(1, Math.ceil(state.events.total / state.events.pageSize));
    renderPagination(document.getElementById("pagination"), state.events.page, totalPages, function (pg) {
      state.events.page = pg;
      fetchEvents();
    });
  }).catch(function () {});
}

function renderEventsToolChips() {
  var container = document.getElementById("events-tool-chips");
  var tools = ["WebFetch", "WebSearch", "Bash", "Read", "Write", "Edit"];
  var currentTool = state.filters.tool;

  var html = '<button class="filter-chip' + (currentTool === "" ? " active" : "") +
    '" data-tool="">All tools</button>';
  tools.forEach(function (tool) {
    html += '<button class="filter-chip' + (currentTool === tool ? " active" : "") +
      '" data-tool="' + escapeHtml(tool) + '">' + escapeHtml(tool) + '</button>';
  });
  container.innerHTML = html;

  container.querySelectorAll(".filter-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var tool = this.getAttribute("data-tool");
      state.filters.tool = tool;
      state.events.page = 1;
      document.getElementById("filter-tool").value = tool;
      fetchEvents();
    });
  });
}

function renderEventsTable(events) {
  var tbody = document.getElementById("events-body");
  if (events.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No events found</td></tr>';
    return;
  }
  tbody.innerHTML = events.map(function (e) {
    var dec = e.decision === "allow" ? badge("allow", "allow") : badge("deny", "deny");
    var summary = escapeHtml(truncate(summarizeInput(e.tool, e.input), 60));
    var sel = state.selectedEvent && state.selectedEvent.id === e.id ? " selected" : "";
    return '<tr class="event-row' + sel + '" data-id="' + e.id + '">' +
      '<td class="time-cell">' + escapeHtml(formatDateTime(e.ts)) + '</td>' +
      '<td>' + toolBadge(e.tool) + '</td>' +
      '<td class="input-cell" title="' + escapeHtml(summarizeInput(e.tool, e.input)) + '">' + summary + '</td>' +
      '<td>' + dec + '</td>' +
      '</tr>';
  }).join("");

  // Row click handlers
  tbody.querySelectorAll(".event-row").forEach(function (row) {
    row.addEventListener("click", function () {
      var id = parseInt(this.getAttribute("data-id"));
      openEventDetail(id);
    });
  });
}

function fetchGroupedEvents() {
  var q = "?group_by=" + encodeURIComponent(state.filters.group_by) + "&limit=50";
  api.get("/events" + q).then(function (data) {
    var groups = data.groups || [];
    renderGroupedTable(groups);
    document.getElementById("pagination").innerHTML = "";
    setStatus("live");
  }).catch(function () { setStatus("offline"); });
}

function renderGroupedTable(groups) {
  var tbody = document.getElementById("events-body");
  var gb = state.filters.group_by;

  if (groups.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No data for grouping</td></tr>';
    return;
  }

  // Update table headers
  var thead = tbody.parentElement.querySelector("thead tr");
  if (gb === "domain") {
    thead.innerHTML = '<th>Domain</th><th>Count</th><th>Latest</th><th>Actions</th>';
  } else if (gb === "session") {
    thead.innerHTML = '<th>Session</th><th>Project</th><th>Count</th><th>Latest</th>';
  } else {
    thead.innerHTML = '<th>Tool</th><th>Count</th><th>Latest</th><th>Actions</th>';
  }

  tbody.innerHTML = groups.map(function (g) {
    if (gb === "domain") {
      return '<tr>' +
        '<td><code>' + escapeHtml(g.key) + '</code></td>' +
        '<td>' + g.count + '</td>' +
        '<td>' + escapeHtml(formatDateTime(g.latest_ts)) + '</td>' +
        '<td><button class="btn-sm btn-danger" onclick="blockDomainFromGroup(\'' + escapeHtml(g.key) + '\')">Block</button></td>' +
        '</tr>';
    } else if (gb === "session") {
      return '<tr>' +
        '<td><code>' + escapeHtml(truncate(g.key || "—", 20)) + '</code></td>' +
        '<td>' + escapeHtml(g.project || "—") + '</td>' +
        '<td>' + g.count + '</td>' +
        '<td>' + escapeHtml(formatDateTime(g.latest_ts)) + '</td>' +
        '</tr>';
    } else {
      return '<tr>' +
        '<td>' + toolBadge(g.key) + '</td>' +
        '<td>' + g.count + '</td>' +
        '<td>' + escapeHtml(formatDateTime(g.latest_ts)) + '</td>' +
        '<td><button class="btn-sm" onclick="filterByTool(\'' + escapeHtml(g.key) + '\')">View events</button></td>' +
        '</tr>';
    }
  }).join("");
}

function filterByTool(tool) {
  state.filters.group_by = "";
  state.filters.tool = tool;
  document.getElementById("filter-group").value = "";
  document.getElementById("filter-tool").value = tool;
  resetTableHeaders();
  state.events.page = 1;
  renderEventsToolChips();
  fetchEvents();
}

function blockDomainFromGroup(domain) {
  showModal("Block domain", "Block " + domain + "? All future requests to this domain will be denied.", "Block").then(function (ok) {
    if (!ok) return;
    api.post("/blocklist", { pattern: domain }).then(function () {
      showToast(domain + " added to blocklist");
    }).catch(function () { showToast("Failed to block domain", "error"); });
  });
}

function resetTableHeaders() {
  var thead = document.querySelector("#events-table-wrapper thead tr");
  thead.innerHTML = '<th>Time</th><th>Tool</th><th>Input</th><th>Decision</th>';
}

// ---- Event Detail Panel ----

function openEventDetail(eventId) {
  api.get("/events/" + eventId).then(function (data) {
    if (!data.event) return;
    state.selectedEvent = data.event;
    state.detailOpen = true;
    document.querySelector(".events-layout").classList.add("detail-open");
    renderEventDetail(data.event);

    // Highlight selected row
    document.querySelectorAll(".event-row").forEach(function (r) {
      r.classList.toggle("selected", parseInt(r.getAttribute("data-id")) === eventId);
    });
  }).catch(function () { showToast("Failed to load event", "error"); });
}

function closeEventDetail() {
  state.selectedEvent = null;
  state.detailOpen = false;
  document.querySelector(".events-layout").classList.remove("detail-open");
  document.querySelectorAll(".event-row.selected").forEach(function (r) {
    r.classList.remove("selected");
  });
}

function renderEventDetail(e) {
  var dec = e.decision === "allow" ? badge("allow", "allow") : badge("deny", "deny");
  var inputObj;
  try { inputObj = typeof e.input === "string" ? JSON.parse(e.input) : e.input; }
  catch (err) { inputObj = e.input; }

  var html = '<div class="detail-meta">' +
    '<div class="meta-row"><span class="meta-label">Decision</span>' + dec + '</div>' +
    '<div class="meta-row"><span class="meta-label">Tool</span>' + toolBadge(e.tool) + '</div>' +
    '<div class="meta-row"><span class="meta-label">Time</span><span>' + escapeHtml(formatTime(e.ts)) + " — " + escapeHtml(formatDate(e.ts)) + '</span></div>' +
    '<div class="meta-row"><span class="meta-label">Session</span><span><code>' + escapeHtml(truncate(e.session_id || "—", 24)) + '</code></span></div>' +
    '<div class="meta-row"><span class="meta-label">Project</span><span>' + escapeHtml(e.project || "—") + '</span></div>';

  if (e.reason) {
    html += '<div class="meta-row"><span class="meta-label">Reason</span><span class="text-deny">' + escapeHtml(e.reason) + '</span></div>';
  }
  html += '</div>';

  html += '<div class="detail-section-label">Input</div>';
  html += '<pre class="json-viewer">' + renderJson(inputObj) + '</pre>';

  // Contextual actions
  html += '<div class="detail-actions">';
  if (e.tool === "WebFetch" || e.tool === "WebSearch") {
    var url = "";
    try {
      var inp = typeof e.input === "string" ? JSON.parse(e.input) : e.input;
      url = inp.url || inp.query || "";
    } catch (err2) { /* ignore */ }
    if (url) {
      var domain;
      try { domain = new URL(url).hostname; }
      catch (err3) { domain = url; }
      html += '<button class="btn-danger btn-action" onclick="blockDomainAction(\'' + escapeHtml(domain) + '\')">Block ' + escapeHtml(domain) + '</button>';
    }
  }
  if (e.tool === "Write" || e.tool === "Edit") {
    var filePath = "";
    try {
      var inp2 = typeof e.input === "string" ? JSON.parse(e.input) : e.input;
      filePath = inp2.file_path || "";
    } catch (err4) { /* ignore */ }
    if (filePath) {
      html += '<button class="btn-danger btn-action" onclick="protectFileAction(\'' + escapeHtml(filePath).replace(/'/g, "\\'") + '\')">Protect ' + escapeHtml(truncate(filePath, 30)) + '</button>';
    }
  }
  html += '</div>';

  document.getElementById("detail-content").innerHTML = html;
}

function blockDomainAction(domain) {
  showModal("Block domain", "Block " + domain + "? All future requests will be denied.", "Block").then(function (ok) {
    if (!ok) return;
    api.post("/blocklist", { pattern: domain }).then(function () {
      showToast(domain + " added to blocklist");
    }).catch(function () { showToast("Failed to block domain", "error"); });
  });
}

function protectFileAction(filePath) {
  showModal("Protect file", "Protect " + filePath + "? Claude Code will be denied write access.", "Protect").then(function (ok) {
    if (!ok) return;
    api.post("/protected-files", { pattern: filePath }).then(function () {
      showToast("File protected: " + filePath);
    }).catch(function () { showToast("Failed to protect file", "error"); });
  });
}

document.getElementById("close-detail").addEventListener("click", closeEventDetail);

// ---- Filter controls ----

document.getElementById("search-input").addEventListener("input", function () {
  clearTimeout(_searchTimer);
  var val = this.value;
  _searchTimer = setTimeout(function () {
    state.filters.search = val;
    state.events.page = 1;
    fetchEvents();
  }, 300);
});

document.getElementById("filter-tool").addEventListener("change", function () {
  state.filters.tool = this.value;
  state.events.page = 1;
  fetchEvents();
});

document.getElementById("filter-decision").addEventListener("change", function () {
  state.filters.decision = this.value;
  state.events.page = 1;
  fetchEvents();
});

document.getElementById("filter-date-from").addEventListener("change", function () {
  state.filters.date_from = this.value;
  state.events.page = 1;
  fetchEvents();
});

document.getElementById("filter-date-to").addEventListener("change", function () {
  state.filters.date_to = this.value;
  state.events.page = 1;
  fetchEvents();
});

document.getElementById("filter-group").addEventListener("change", function () {
  state.filters.group_by = this.value;
  if (!this.value) resetTableHeaders();
  state.events.page = 1;
  fetchEvents();
});

// ---- Rules Tab ----

function fetchBlocklist() {
  api.get("/blocklist").then(function (data) {
    var patterns = data.patterns || [];
    var container = document.getElementById("blocklist-list");
    document.getElementById("blocklist-count").textContent = patterns.length + " patterns";

    if (patterns.length === 0) {
      container.innerHTML = '<div class="empty">No patterns — nothing blocked</div>';
      return;
    }

    container.innerHTML = patterns.map(function (p) {
      var pat = typeof p === "object" ? p.pattern : p;
      var added = typeof p === "object" && p.added ? formatDate(p.added) : "";
      return '<div class="rule-item">' +
        '<div class="rule-info"><code>' + escapeHtml(pat) + '</code>' +
        (added ? '<span class="text-muted rule-date">' + added + '</span>' : '') +
        '</div>' +
        '<button class="btn-sm btn-danger" onclick="removeBlocklistPattern(\'' + escapeHtml(pat).replace(/'/g, "\\'") + '\')">Remove</button>' +
        '</div>';
    }).join("");
  }).catch(function () {});
}

function fetchProtectedFiles() {
  api.get("/protected-files").then(function (data) {
    var patterns = data.patterns || [];
    var container = document.getElementById("protected-list");
    document.getElementById("protected-count").textContent = patterns.length + " patterns";

    if (patterns.length === 0) {
      container.innerHTML = '<div class="empty">No protected files</div>';
      return;
    }

    container.innerHTML = patterns.map(function (p) {
      var pat = typeof p === "object" ? p.pattern : p;
      var added = typeof p === "object" && p.added ? formatDate(p.added) : "";
      return '<div class="rule-item">' +
        '<div class="rule-info"><code>' + escapeHtml(pat) + '</code>' +
        (added ? '<span class="text-muted rule-date">' + added + '</span>' : '') +
        '</div>' +
        '<button class="btn-sm btn-danger" onclick="removeProtectedFile(\'' + escapeHtml(pat).replace(/'/g, "\\'") + '\')">Remove</button>' +
        '</div>';
    }).join("");
  }).catch(function () {});
}

function addBlocklistPattern() {
  var input = document.getElementById("blocklist-input");
  var pattern = input.value.trim();
  if (!pattern) return;
  api.post("/blocklist", { pattern: pattern }).then(function () {
    input.value = "";
    showToast("Pattern added: " + pattern);
    fetchBlocklist();
  }).catch(function () { showToast("Failed to add pattern", "error"); });
}

function removeBlocklistPattern(pattern) {
  api.del("/blocklist", { pattern: pattern }).then(function () {
    showToast("Pattern removed");
    fetchBlocklist();
  }).catch(function () { showToast("Failed to remove pattern", "error"); });
}

function addProtectedFile() {
  var input = document.getElementById("protected-input");
  var pattern = input.value.trim();
  if (!pattern) return;
  api.post("/protected-files", { pattern: pattern }).then(function () {
    input.value = "";
    showToast("File protected: " + pattern);
    fetchProtectedFiles();
  }).catch(function () { showToast("Failed to add pattern", "error"); });
}

function removeProtectedFile(pattern) {
  api.del("/protected-files", { pattern: pattern }).then(function () {
    showToast("Pattern removed");
    fetchProtectedFiles();
  }).catch(function () { showToast("Failed to remove pattern", "error"); });
}

function fetchBlockedCommands() {
  api.get("/blocked-commands").then(function (data) {
    var patterns = data.patterns || [];
    var container = document.getElementById("commands-list");
    document.getElementById("commands-count").textContent = patterns.length + " patterns";

    if (patterns.length === 0) {
      container.innerHTML = '<div class="empty">No blocked commands</div>';
      return;
    }

    var html = '<table class="commands-table"><thead><tr>' +
      '<th>Type</th><th>Pattern</th><th>Added</th><th></th>' +
      '</tr></thead><tbody>';
    html += patterns.map(function (p) {
      var pat = typeof p === "object" ? p.pattern : p;
      var added = typeof p === "object" && p.added ? formatDate(p.added) : "—";
      var type = "prefix";
      if (pat.startsWith("tool:")) type = "tool";
      else if (pat.startsWith("/") && pat.endsWith("/") && pat.length > 2) type = "regex";
      else if (pat.indexOf("*") !== -1 || pat.indexOf("?") !== -1) type = "glob";
      var typeBadge = '<span class="cmd-type cmd-type-' + type + '">' + type + '</span>';
      return '<tr>' +
        '<td>' + typeBadge + '</td>' +
        '<td><code>' + escapeHtml(pat) + '</code></td>' +
        '<td class="text-muted">' + escapeHtml(added) + '</td>' +
        '<td class="cmd-actions"><button class="btn-sm btn-danger" onclick="removeBlockedCommand(\'' + escapeHtml(pat).replace(/'/g, "\\'") + '\')">Remove</button></td>' +
        '</tr>';
    }).join("");
    html += '</tbody></table>';
    container.innerHTML = html;
  }).catch(function () {});
}

function addBlockedCommand() {
  var input = document.getElementById("commands-input");
  var pattern = input.value.trim();
  if (!pattern) return;
  api.post("/blocked-commands", { pattern: pattern }).then(function () {
    input.value = "";
    showToast("Command blocked: " + pattern);
    fetchBlockedCommands();
  }).catch(function () { showToast("Failed to add pattern", "error"); });
}

function removeBlockedCommand(pattern) {
  api.del("/blocked-commands", { pattern: pattern }).then(function () {
    showToast("Pattern removed");
    fetchBlockedCommands();
  }).catch(function () { showToast("Failed to remove pattern", "error"); });
}

document.getElementById("blocklist-add").addEventListener("click", addBlocklistPattern);
document.getElementById("blocklist-input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") addBlocklistPattern();
});
document.getElementById("protected-add").addEventListener("click", addProtectedFile);
document.getElementById("protected-input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") addProtectedFile();
});
document.getElementById("commands-add").addEventListener("click", addBlockedCommand);
document.getElementById("commands-input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") addBlockedCommand();
});

// ---- Settings Tab ----

function fetchConfig() {
  api.get("/config").then(function (data) {
    state.config = data.config || {};
    var cfg = state.config;

    document.getElementById("cfg-default-decision").value = cfg.default_decision || "allow";

    var bashToggle = document.getElementById("cfg-log-bash");
    bashToggle.classList.toggle("on", cfg.log_bash === "true");

    var readsToggle = document.getElementById("cfg-log-reads");
    readsToggle.classList.toggle("on", cfg.log_reads === "true");
  }).catch(function () {});
}

document.getElementById("cfg-default-decision").addEventListener("change", function () {
  api.put("/config", { key: "default_decision", value: this.value }).then(function () {
    showToast("Default decision updated");
  }).catch(function () { showToast("Failed to update", "error"); });
});

document.querySelectorAll(".toggle").forEach(function (toggle) {
  toggle.addEventListener("click", function () {
    var isOn = this.classList.toggle("on");
    var key = this.getAttribute("data-key");
    if (key) {
      api.put("/config", { key: key, value: isOn ? "true" : "false" }).then(function () {
        showToast("Setting updated");
      }).catch(function () { showToast("Failed to update", "error"); });
    }
  });
});

document.getElementById("btn-export").addEventListener("click", function () {
  api.get("/events/export").then(function (data) {
    var blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "krabb-events-" + new Date().toISOString().slice(0, 10) + ".json";
    a.click();
    URL.revokeObjectURL(url);
    showToast("Events exported");
  }).catch(function () { showToast("Failed to export", "error"); });
});

document.getElementById("btn-clear").addEventListener("click", function () {
  showModal(
    "Clear all events",
    "This will permanently delete all logged events. This action cannot be undone.",
    "Clear all"
  ).then(function (ok) {
    if (!ok) return;
    api.del("/events").then(function (data) {
      showToast("Cleared " + (data.deleted || 0) + " events");
      fetchOverview();
      fetchEvents();
    }).catch(function () { showToast("Failed to clear events", "error"); });
  });
});

// ---- Status indicator ----

function setStatus(status) {
  var dot = document.getElementById("status-dot");
  var text = document.getElementById("status-text");
  dot.className = "status-dot " + status;
  text.textContent = status === "live" ? "live" : status === "offline" ? "hook offline" : "connecting...";
}

// ---- Refresh logic ----

function refreshCurrentTab() {
  if (state.tab === "overview") fetchOverview();
  else if (state.tab === "events") fetchEvents();
  else if (state.tab === "rules") { fetchBlocklist(); fetchProtectedFiles(); fetchBlockedCommands(); }
  else if (state.tab === "settings") fetchConfig();
}

// Initial load
refreshCurrentTab();

// Auto-refresh — only refresh the active tab
setInterval(function () {
  if (state.tab === "overview") fetchOverview();
  else if (state.tab === "events" && !state.detailOpen) fetchEvents();
}, 3000);

setInterval(function () {
  if (state.tab === "rules") { fetchBlocklist(); fetchProtectedFiles(); fetchBlockedCommands(); }
}, 10000);
