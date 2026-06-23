const css = getComputedStyle(document.documentElement);
const colors = {
  purple: css.getPropertyValue("--purple").trim(),
  cyan: css.getPropertyValue("--cyan").trim(),
  pink: css.getPropertyValue("--pink").trim(),
  green: css.getPropertyValue("--green").trim(),
  gold: css.getPropertyValue("--gold").trim(),
  muted: css.getPropertyValue("--muted").trim(),
};
const chartData = window.XPENSE_CHARTS || {};
if (typeof Chart !== "undefined") {

    if (document.body.classList.contains("theme-light")) {
    Chart.defaults.color = "#334155";
    Chart.defaults.borderColor = "rgba(0,0,0,0.1)";
} else {
    Chart.defaults.color = "#cbd8ef";
    Chart.defaults.borderColor = "rgba(255,255,255,0.08)";
}
    Chart.defaults.font.family = "Inter, sans-serif";

}

function mountLineChart() {
  const canvas = document.getElementById("spendingLine");
  if (!canvas) return;
  const gradient = canvas.getContext("2d").createLinearGradient(0, 0, 0, 280);
  gradient.addColorStop(0, "rgba(139,61,255,0.55)");
  gradient.addColorStop(1, "rgba(139,61,255,0.02)");
  new Chart(canvas, {
    type: "line",
    data: {
      labels: chartData.lineLabels || ["May 1", "May 4", "May 7", "May 10", "May 13", "May 16", "May 19", "May 22", "May 25", "May 28", "May 31"],
      datasets: [{
        data: chartData.lineData || [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        borderColor: colors.purple,
        backgroundColor: gradient,
        fill: true,
        tension: 0.38,
        pointRadius: 3,
        pointHoverRadius: 7,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `₹${ctx.raw.toLocaleString("en-IN")}` } } },
      scales: { y: { ticks: { callback: value => `₹${value / 1000}K` } } }
    }
  });
}

function mountCategoryChart() {
  document.querySelectorAll("#categoryDoughnut").forEach(canvas => {
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: chartData.categoryLabels || ["No expenses yet"],
        datasets: [{
          data: chartData.categoryData || [1],
          backgroundColor: chartData.categoryColors || ["#203753"],
          borderWidth: 0,
        }]
      },
      options: {
        cutout: "62%",
        plugins: { legend: { display: false } },
        responsive: true,
        maintainAspectRatio: false,
      }
    });
  });
}

function mountSavingsChart() {
  const canvas = document.getElementById("savingsDoughnut");
  if (!canvas) return;
  new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: chartData.goalLabels || ["No goals yet"],
      datasets: [{ data: chartData.goalData || [1], backgroundColor: [colors.purple, colors.cyan, colors.green], borderWidth: 0 }]
    },
    options: { cutout: "66%", plugins: { legend: { position: "bottom" } } }
  });
}

function mountSearch() {
  const input = document.getElementById("searchInput");
  const table = document.getElementById("transactionTable");
  if (!input || !table) return;
  input.addEventListener("input", () => {
    const term = input.value.toLowerCase();
    table.querySelectorAll("tr").forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(term) ? "" : "none";
    });
  });
}

function mountMenus() {
  document.querySelectorAll(".js-menu-btn").forEach(button => {
    button.addEventListener("click", event => {
      event.stopPropagation();
      const id = button.dataset.menu;
      document.querySelectorAll(".popover.open").forEach(menu => {
        if (menu.id !== id) {
          menu.classList.remove("open");
          menu.hidden = true;
        }
      });
      const menu = document.getElementById(id);
      if (!menu) return;
      const willOpen = !menu.classList.contains("open");
      menu.classList.toggle("open", willOpen);
      menu.hidden = !willOpen;
    });
  });
  document.addEventListener("click", () => {
    document.querySelectorAll(".popover.open").forEach(menu => {
      menu.classList.remove("open");
      menu.hidden = true;
    });
  });
}

function mountSettingsTabs() {
  const tabs = document.querySelectorAll("[data-settings-tab]");
  const panels = document.querySelectorAll("[data-settings-panel]");
  if (!tabs.length) return;
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(item => item.classList.remove("active"));
      panels.forEach(panel => panel.hidden = panel.dataset.settingsPanel !== tab.dataset.settingsTab);
      tab.classList.add("active");
    });
  });
}

function mountQuickCategories() {
  const categorySelect = document.querySelector("select[name='category']");
  if (!categorySelect) return;
  document.querySelectorAll("[data-category-name]").forEach(button => {
    button.addEventListener("click", () => {
      const name = button.dataset.categoryName;
      [...categorySelect.options].forEach(option => {
        if (option.text.includes(name)) categorySelect.value = option.value;
      });
    });
  });
}

function mountReminderDismiss() {
  document.querySelectorAll("[data-dismiss-reminder]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      const card = button.closest("[data-reminder-card]");
      const popover = button.closest(".notification-popover");
      const badge = document.querySelector(".notification-badge");
      if (card) card.hidden = true;
      if (badge) badge.remove();
      if (popover && !popover.querySelector(".notification-card.complete")) {
        const emptyCard = document.createElement("div");
        emptyCard.className = "notification-card complete";
        emptyCard.innerHTML = "<b>Reminder dismissed</b><p>Add today's transaction to clear it fully.</p>";
        popover.appendChild(emptyCard);
      }
    });
  });
}

function mountFlashMessages() {
  const seenMessages = new Set();
  document.querySelectorAll(".message").forEach(message => {
    const text = message.textContent.trim();
    if (seenMessages.has(text)) {
      message.remove();
      return;
    }
    seenMessages.add(text);
    window.setTimeout(() => {
      message.classList.add("is-hiding");
      window.setTimeout(() => message.remove(), 350);
    }, 4000);
  });
}

function mountFormSubmitGuard() {
  document.querySelectorAll("form").forEach(form => {
    form.addEventListener("submit", event => {
      if (form.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = "true";
      form.querySelectorAll("button[type='submit']").forEach(button => {
        button.setAttribute("aria-disabled", "true");
        button.style.pointerEvents = "none";
        button.dataset.originalText = button.textContent;
        button.textContent = "Please wait...";
      });
    });
  });
}

if (typeof Chart !== "undefined") {

    mountLineChart();
    mountCategoryChart();
    mountSavingsChart();

}
mountSearch();
mountMenus();
mountSettingsTabs();
mountQuickCategories();
mountReminderDismiss();
mountFlashMessages();
mountFormSubmitGuard();

document.addEventListener("DOMContentLoaded", function () {

    const passwordInput =
        document.querySelector("input[name='password']");

    const togglePassword =
        document.getElementById("togglePassword");

    if (togglePassword && passwordInput) {

        togglePassword.addEventListener("click", function () {

            const icon = this.querySelector("i");

            if (passwordInput.type === "password") {

                passwordInput.type = "text";

                icon.classList.remove("fa-eye");
                icon.classList.add("fa-eye-slash");

            } else {

                passwordInput.type = "password";

                icon.classList.remove("fa-eye-slash");
                icon.classList.add("fa-eye");

            }

        });

    }

});

function togglePasswordVisibility() {

    const password =
        document.querySelector("input[name='password']");

    const eye =
        document.getElementById("eyeIcon");

    if(password.type === "password") {

        password.type = "text";

        eye.classList.remove("fa-eye");
        eye.classList.add("fa-eye-slash");

    }
    else {

        password.type = "password";

        eye.classList.remove("fa-eye-slash");
        eye.classList.add("fa-eye");

    }

}

document.addEventListener("DOMContentLoaded", function () {

    function setupPasswordToggle(inputId, buttonId) {

        const passwordInput =
            document.getElementById(inputId);

        const toggleButton =
            document.getElementById(buttonId);

        if (!passwordInput || !toggleButton) return;

        toggleButton.addEventListener("click", function () {

            const icon = this.querySelector("i");

            if (passwordInput.type === "password") {

                passwordInput.type = "text";

                icon.classList.remove("fa-eye");
                icon.classList.add("fa-eye-slash");

            } else {

                passwordInput.type = "password";

                icon.classList.remove("fa-eye-slash");
                icon.classList.add("fa-eye");

            }

        });

    }

    setupPasswordToggle("id_password1", "togglePassword1");
    setupPasswordToggle("id_password2", "togglePassword2");

});
