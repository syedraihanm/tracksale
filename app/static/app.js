// Minimal client helpers: toasts, modals, keyboard search navigation, print

function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    const bg = type === "error" ? "bg-red-600 text-white" : "bg-slate-900 text-white";
    toast.className = `${bg} px-4 py-3 rounded-lg shadow-lg text-sm flex items-center justify-between transition-all duration-300 transform translate-y-2 opacity-0`;
    toast.innerHTML = `<span>${message}</span><button type="button" class="ml-4 text-white hover:text-slate-200" onclick="this.parentElement.remove()">&times;</button>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.remove("translate-y-2", "opacity-0");
    }, 10);

    setTimeout(() => {
        toast.classList.add("opacity-0");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// HTMX trigger listener for toasts
document.addEventListener("htmx:afterRequest", function(evt) {
    const trigger = evt.detail.xhr.getResponseHeader("HX-Trigger");
    if (trigger) {
        try {
            const data = JSON.parse(trigger);
            if (data.toast) {
                showToast(data.toast.message, data.toast.type || "success");
            }
        } catch (e) {
            if (typeof trigger === "string" && !trigger.startsWith("{")) {
                showToast(trigger);
            }
        }
    }
});

// Configure HTMX 2 so 422 and 409 responses swap normally
document.addEventListener("htmx:beforeSwap", function(evt) {
    if (evt.detail.xhr.status === 422 || evt.detail.xhr.status === 409) {
        evt.detail.shouldSwap = true;
        evt.detail.isError = false;
    }
});

// Modal helper
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

// Search dropdown keyboard navigation
document.addEventListener("keydown", function(e) {
    const results = document.getElementById("search-results");
    if (!results || results.classList.contains("hidden")) return;

    const items = results.querySelectorAll(".search-result-item");
    if (!items.length) return;

    let currentIndex = -1;
    items.forEach((item, idx) => {
        if (item.classList.contains("bg-slate-100")) {
            currentIndex = idx;
        }
    });

    if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = (currentIndex + 1) % items.length;
        items.forEach((it, idx) => it.classList.toggle("bg-slate-100", idx === next));
    } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = (currentIndex - 1 + items.length) % items.length;
        items.forEach((it, idx) => it.classList.toggle("bg-slate-100", idx === prev));
    } else if (e.key === "Enter") {
        if (currentIndex >= 0 && items[currentIndex]) {
            e.preventDefault();
            items[currentIndex].click();
        }
    } else if (e.key === "Escape") {
        results.classList.add("hidden");
    }
});

// Close search dropdown on click outside
document.addEventListener("click", function(e) {
    const searchBox = document.getElementById("search-box-container");
    const results = document.getElementById("search-results");
    if (searchBox && results && !searchBox.contains(e.target)) {
        results.classList.add("hidden");
    }
});
