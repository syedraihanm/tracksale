/**
 * TrackSale Modern UI/UX Controller (v3.0)
 * - Sidebar Collapse & Mobile Drawer
 * - Automatic DOM Polish (Ticket Pills, Customer Avatars, Status Dots, Filter Chips)
 * - Global Search Keyboard Navigation (Ctrl+K, /, Arrows, Enter, Esc)
 * - HTMX 409/422 Swap Config & Accessible Toast Notifications
 */
(function () {
  "use strict";

  const SIDEBAR_STORAGE_KEY = "tracksale.sidebar.collapsed";

  const STATUS_DOT_COLORS = {
    "received": "#3b82f6",           // Blue
    "awaiting approval": "#f59e0b",  // Amber
    "in progress": "#6366f1",        // Indigo
    "awaiting parts": "#f97316",     // Orange
    "ready for pickup": "#10b981",   // Emerald
    "declined": "#f43f5e",           // Rose
    "unrepairable": "#ef4444",       // Red
    "delivered": "#64748b",          // Slate
  };

  const AVATAR_PALETTES = [
    "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
    "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    "bg-sky-50 text-sky-700 ring-sky-600/20",
    "bg-amber-50 text-amber-700 ring-amber-600/20",
    "bg-purple-50 text-purple-700 ring-purple-600/20",
    "bg-rose-50 text-rose-700 ring-rose-600/20",
  ];

  document.addEventListener("DOMContentLoaded", function () {
    if (window.htmx) {
      window.htmx.config.responseHandling = [
        { code: "204", swap: false },
        { code: "[23]..", swap: true },
        { code: "409", swap: true, error: false },
        { code: "422", swap: true, error: false },
        { code: "403", swap: true, error: false },
        { code: "[45]..", swap: false, error: true },
      ];
    }

    initSidebarState();
    initGlobalSearchKeyboard();
    initFormDoubleSubmitProtection();
    enhanceModernUI(document);

    // Re-apply modern UI enhancements whenever HTMX swaps any partial
    document.body.addEventListener("htmx:afterSwap", function (e) {
      enhanceModernUI(e.target || document);
    });
  });

  // =========================================================================
  // 1. Automatic Modern SaaS DOM Enhancer (Works across all existing templates)
  // =========================================================================
  function enhanceModernUI(root) {
    if (!root || !root.querySelectorAll) return;

    // A. Style Ticket Number links (e.g. R-1098) as sleek monospace pills
    root.querySelectorAll('td a[href^="/tickets/"]').forEach((link) => {
      const text = (link.textContent || "").trim();
      if (/^[A-Z]+-\d+$/i.test(text) && !link.classList.contains("ticket-id-pill")) {
        link.classList.add("ticket-id-pill");
      }
    });

    // B. Colorize Status Group Header Dots (Received, Awaiting Approval, In Progress, etc.)
    root.querySelectorAll("summary, div, h2, h3").forEach((el) => {
      if (el.children.length >= 2 && el.children.length <= 5) {
        const firstChild = el.children[0];
        const secondChild = el.children[1];
        if (
          firstChild &&
          secondChild &&
          firstChild.tagName === "SPAN" &&
          (firstChild.textContent || "").trim() === ""
        ) {
          const label = (secondChild.textContent || "").trim().toLowerCase();
          for (const [statusKey, hex] of Object.entries(STATUS_DOT_COLORS)) {
            if (label.startsWith(statusKey)) {
              firstChild.style.backgroundColor = hex;
              firstChild.style.borderColor = hex;
              firstChild.style.boxShadow = `0 0 0 3px ${hex}22`;
              break;
            }
          }
        }
      }
    });

    // C. Upgrade harsh black filter pills into modern tinted chips
    root.querySelectorAll("button, a").forEach((btn) => {
      const cls = btn.className || "";
      const txt = (btn.textContent || "").trim();

      // Hide duplicate "+ Intake New Ticket" button inside Queue card when sidebar CTA exists
      if (txt.includes("Intake New Ticket") && document.getElementById("app-sidebar")) {
        btn.classList.add("lg:hidden");
      }

      if (cls.includes("rounded-full") && (cls.includes("bg-slate-900") || cls.includes("bg-gray-900"))) {
        btn.classList.remove("bg-slate-900", "bg-gray-900", "text-white");
        btn.classList.add("modern-chip-active");
      } else if (
        cls.includes("rounded-full") &&
        (cls.includes("bg-white") || cls.includes("bg-slate-100")) &&
        btn.closest("form, [hx-get], .flex")
      ) {
        btn.classList.add("modern-chip-inactive");
      }
    });

    // D. Add Initials Avatars to Customer cells in Queue / Ready tables
    root.querySelectorAll("table tbody tr").forEach((row) => {
      const cells = row.querySelectorAll("td");
      if (cells.length >= 5) {
        const customerCell = cells[1];
        if (customerCell && !customerCell.dataset.avatarEnhanced) {
          const lines = customerCell.innerText
            .split("\n")
            .map((s) => s.trim())
            .filter(Boolean);
          if (lines.length >= 1 && !/^\d+$/.test(lines[0])) {
            const name = lines[0];
            const initials = name
              .split(/\s+/)
              .slice(0, 2)
              .map((w) => w[0] || "")
              .join("")
              .toUpperCase();
            const palette = AVATAR_PALETTES[name.charCodeAt(0) % AVATAR_PALETTES.length];

            customerCell.dataset.avatarEnhanced = "1";
            const wrapper = document.createElement("div");
            wrapper.className = "flex items-center gap-3";

            const avatar = document.createElement("div");
            avatar.className = `w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ring-1 ring-inset shrink-0 ${palette}`;
            avatar.textContent = initials || "C";

            const info = document.createElement("div");
            info.className = "min-w-0";
            while (customerCell.firstChild) {
              info.appendChild(customerCell.firstChild);
            }

            wrapper.appendChild(avatar);
            wrapper.appendChild(info);
            customerCell.appendChild(wrapper);
          }
        }
      }
    });
  }

  // =========================================================================
  // 2. Sidebar Desktop Collapse & Mobile Drawer Controls
  // =========================================================================
  function initSidebarState() {
    try {
      if (localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1") {
        document.body.classList.add("sidebar-collapsed");
      }
    } catch (_) {}
  }

  function toggleDesktopSidebar() {
    const collapsed = document.body.classList.toggle("sidebar-collapsed");
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
    } catch (_) {}
  }

  function openMobileSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (sidebar) sidebar.classList.remove("-translate-x-full");
    if (backdrop) backdrop.classList.remove("hidden");
  }

  function closeMobileSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    if (sidebar) sidebar.classList.add("-translate-x-full");
    if (backdrop) backdrop.classList.add("hidden");
  }

  // =========================================================================
  // 3. Global Search Keyboard Shortcuts (Ctrl+K, /, Arrows, Enter, Esc)
  // =========================================================================
  function initGlobalSearchKeyboard() {
    const searchInput = document.getElementById("global-search-input");
    const resultsBox = document.getElementById("global-search-results");
    const container = document.getElementById("global-search-container");

    if (!searchInput || !resultsBox) return;

    let selectedIndex = -1;

    document.addEventListener("keydown", function (e) {
      const tag = (e.target && e.target.tagName) || "";
      const isEditable =
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target.isContentEditable;

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleDesktopSidebar();
        return;
      }

      if (e.altKey && e.key.toLowerCase() === "n") {
        e.preventDefault();
        window.location.href = "/tickets/new";
        return;
      }

      if (!isEditable && e.key === "/") {
        e.preventDefault();
        searchInput.focus();
        return;
      }

      if (e.key === "Escape") {
        resultsBox.innerHTML = "";
        closeMobileSidebar();
      }
    });

    resultsBox.addEventListener("htmx:afterSwap", function () {
      selectedIndex = -1;
    });

    searchInput.addEventListener("keydown", function (e) {
      const links = Array.from(resultsBox.querySelectorAll("a[href], .search-result-item[href]"));
      if (!links.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % links.length;
        highlightSearchLink(links, selectedIndex);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex = (selectedIndex - 1 + links.length) % links.length;
        highlightSearchLink(links, selectedIndex);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const targetLink = selectedIndex >= 0 ? links[selectedIndex] : links[0];
        if (targetLink) {
          window.location.href = targetLink.getAttribute("href");
        }
      } else if (e.key === "Escape") {
        resultsBox.innerHTML = "";
        searchInput.blur();
      }
    });

    document.addEventListener("click", function (e) {
      if (container && !container.contains(e.target)) {
        resultsBox.innerHTML = "";
      }
    });
  }

  function highlightSearchLink(links, activeIdx) {
    links.forEach((el, idx) => {
      if (idx === activeIdx) {
        el.classList.add("search-item-active");
        el.scrollIntoView({ block: "nearest" });
      } else {
        el.classList.remove("search-item-active");
      }
    });
  }

  // =========================================================================
  // 4. Toast Notification System & Modal Controls
  // =========================================================================
  function showToast(message, type = "success", durationMs = 4000) {
    const container = document.getElementById("toast-container");
    if (!container || !message) return;

    const palette = {
      success: "bg-slate-900 text-white border-emerald-500/40",
      error: "bg-rose-950 text-white border-rose-500/50",
      warning: "bg-amber-950 text-white border-amber-500/50",
      info: "bg-slate-900 text-white border-indigo-500/40",
    };

    const dotColor = {
      success: "bg-emerald-400",
      error: "bg-rose-400",
      warning: "bg-amber-400",
      info: "bg-indigo-400",
    };

    const toast = document.createElement("div");
    toast.className = `pointer-events-auto flex items-center justify-between gap-3 px-4 py-3 rounded-xl shadow-xl border text-sm font-medium transition-all duration-200 ${
      palette[type] || palette.success
    }`;

    const left = document.createElement("div");
    left.className = "flex items-center gap-2.5";

    const dot = document.createElement("span");
    dot.className = `w-2.5 h-2.5 rounded-full shrink-0 ${dotColor[type] || dotColor.success}`;

    const text = document.createElement("span");
    text.textContent = message;

    left.appendChild(dot);
    left.appendChild(text);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "text-slate-400 hover:text-white text-xs ml-2";
    closeBtn.innerHTML = "&#10005;";
    closeBtn.onclick = () => toast.remove();

    toast.appendChild(left);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("opacity-0", "translate-y-2");
      setTimeout(() => toast.remove(), 200);
    }, durationMs);
  }

  function handleToastEvent(e) {
    const detail = e.detail;
    if (!detail) return;
    if (typeof detail === "string") {
      showToast(detail, "success");
    } else if (detail.value && typeof detail.value === "string") {
      showToast(detail.value, "success");
    } else if (detail.message) {
      showToast(detail.message, detail.type || "success");
    }
  }

  document.body.addEventListener("showToast", handleToastEvent);
  document.body.addEventListener("toast", handleToastEvent);

  document.addEventListener("htmx:afterRequest", function (evt) {
    const trigger = evt.detail && evt.detail.xhr && evt.detail.xhr.getResponseHeader("HX-Trigger");
    if (trigger) {
      try {
        const data = JSON.parse(trigger);
        if (data.showToast) {
          showToast(data.showToast.message || data.showToast, data.showToast.type || "success");
        } else if (data.toast) {
          showToast(data.toast.message || data.toast, data.toast.type || "success");
        }
      } catch (e) {
        if (typeof trigger === "string" && !trigger.startsWith("{")) {
          showToast(trigger);
        }
      }
    }
  });

  function openModal(id) {
    const el = document.getElementById(id);
    if (el && typeof el.showModal === "function") {
      el.showModal();
    }
  }

  function closeModal(id) {
    const el = document.getElementById(id);
    if (el && typeof el.close === "function") {
      el.close();
    }
  }

  function initFormDoubleSubmitProtection() {
    document.addEventListener("submit", function (e) {
      const form = e.target;
      if (!form || form.hasAttribute("hx-post") || form.hasAttribute("hx-put") || form.hasAttribute("hx-delete")) {
        return;
      }
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn && !submitBtn.disabled) {
        submitBtn.disabled = true;
        setTimeout(() => {
          submitBtn.disabled = false;
        }, 5000);
      }
    });
  }

  window.TrackSaleUI = {
    toggleDesktopSidebar,
    openMobileSidebar,
    closeMobileSidebar,
    showToast,
    openModal,
    closeModal,
    printReceipt: function () {
      window.print();
    },
  };
  window.showToast = showToast;
  window.openModal = openModal;
  window.closeModal = closeModal;
})();
