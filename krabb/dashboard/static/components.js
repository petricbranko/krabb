/* krabb dashboard — reusable UI components */

// ---- Toast notifications ----

function showToast(message, type) {
  type = type || "success";
  var container = document.getElementById("toast-container");
  var toast = document.createElement("div");
  toast.className = "toast toast-" + type;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(function () {
    toast.classList.add("toast-out");
    setTimeout(function () { toast.remove(); }, 300);
  }, 2800);
}

// ---- Modal ----

var _modalResolve = null;

function showModal(title, body, confirmLabel) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent = body;
  var btn = document.getElementById("modal-confirm");
  btn.textContent = confirmLabel || "Confirm";
  document.getElementById("modal-overlay").classList.add("visible");
  return new Promise(function (resolve) { _modalResolve = resolve; });
}

function hideModal() {
  document.getElementById("modal-overlay").classList.remove("visible");
}

document.getElementById("modal-cancel").addEventListener("click", function () {
  hideModal();
  if (_modalResolve) { _modalResolve(false); _modalResolve = null; }
});
document.getElementById("modal-confirm").addEventListener("click", function () {
  hideModal();
  if (_modalResolve) { _modalResolve(true); _modalResolve = null; }
});
document.getElementById("modal-overlay").addEventListener("click", function (e) {
  if (e.target === this) {
    hideModal();
    if (_modalResolve) { _modalResolve(false); _modalResolve = null; }
  }
});

// ---- Badges ----

function badge(text, type) {
  return '<span class="badge badge-' + type + '">' + escapeHtml(text) + "</span>";
}

function toolBadge(tool) {
  var colors = {
    WebFetch: "accent", WebSearch: "accent",
    Bash: "yellow", Read: "muted", Write: "muted", Edit: "muted"
  };
  return '<span class="badge badge-' + (colors[tool] || "muted") + '">' + escapeHtml(tool) + "</span>";
}

// ---- Pagination ----

function renderPagination(container, currentPage, totalPages, onChange) {
  if (totalPages <= 1) { container.innerHTML = ""; return; }

  var parts = [];
  parts.push('<button class="pg-btn" data-page="' + (currentPage - 1) + '"' +
    (currentPage === 1 ? " disabled" : "") + '>&laquo; Prev</button>');

  var pages = [];
  pages.push(1);
  for (var i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) {
    pages.push(i);
  }
  if (totalPages > 1) pages.push(totalPages);

  // deduplicate and sort
  pages = pages.filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });

  var prev = 0;
  for (var j = 0; j < pages.length; j++) {
    var p = pages[j];
    if (p - prev > 1) parts.push('<span class="pg-dots">...</span>');
    parts.push('<button class="pg-btn' + (p === currentPage ? " pg-active" : "") +
      '" data-page="' + p + '">' + p + "</button>");
    prev = p;
  }

  parts.push('<button class="pg-btn" data-page="' + (currentPage + 1) + '"' +
    (currentPage === totalPages ? " disabled" : "") + '>Next &raquo;</button>');

  container.innerHTML = parts.join("");
  container.querySelectorAll(".pg-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var pg = parseInt(this.getAttribute("data-page"));
      if (pg >= 1 && pg <= totalPages) onChange(pg);
    });
  });
}

// ---- Utility functions ----

function escapeHtml(str) {
  var div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, len) {
  if (!str) return "";
  return str.length > len ? str.slice(0, len) + "..." : str;
}

function formatTime(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatDate(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function formatDateTime(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  var date = d.toLocaleDateString([], { month: "short", day: "numeric" });
  var time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return date + " " + time;
}

function summarizeInput(tool, input) {
  try {
    var obj = typeof input === "string" ? JSON.parse(input) : input;
    if (tool === "WebFetch") return obj.url || "";
    if (tool === "WebSearch") return obj.query || "";
    if (tool === "Bash") return obj.command || "";
    if (tool === "Read" || tool === "Write" || tool === "Edit") return obj.file_path || "";
    return JSON.stringify(obj);
  } catch (e) {
    return String(input);
  }
}

function renderJson(obj) {
  if (typeof obj === "string") {
    try { obj = JSON.parse(obj); } catch (e) { return '<span class="json-string">' + escapeHtml(obj) + "</span>"; }
  }
  return _jsonToHtml(obj, 0);
}

function _jsonToHtml(val, depth) {
  if (val === null) return '<span class="json-null">null</span>';
  if (typeof val === "boolean") return '<span class="json-bool">' + val + "</span>";
  if (typeof val === "number") return '<span class="json-number">' + val + "</span>";
  if (typeof val === "string") return '<span class="json-string">"' + escapeHtml(val) + '"</span>';
  if (Array.isArray(val)) {
    if (val.length === 0) return "[]";
    var indent = "  ".repeat(depth + 1);
    var closing = "  ".repeat(depth);
    var items = val.map(function (v) { return indent + _jsonToHtml(v, depth + 1); });
    return "[\n" + items.join(",\n") + "\n" + closing + "]";
  }
  if (typeof val === "object") {
    var keys = Object.keys(val);
    if (keys.length === 0) return "{}";
    var indent2 = "  ".repeat(depth + 1);
    var closing2 = "  ".repeat(depth);
    var entries = keys.map(function (k) {
      return indent2 + '<span class="json-key">"' + escapeHtml(k) + '"</span>: ' + _jsonToHtml(val[k], depth + 1);
    });
    return "{\n" + entries.join(",\n") + "\n" + closing2 + "}";
  }
  return escapeHtml(String(val));
}
