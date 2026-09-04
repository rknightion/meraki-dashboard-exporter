(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function current() { var set = document.documentElement.dataset.theme; return set === "light" || set === "dark" ? set : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  function label() { var next = current() === "dark" ? "light" : "dark"; btn.lastElementChild.textContent = next === "dark" ? "Dark" : "Light"; btn.setAttribute("aria-label", "Switch to " + next + " theme"); }
  btn.addEventListener("click", function () { var next = current() === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; try { localStorage.setItem("mde-theme", next); } catch (e) {} label(); });
  label();
})();
document.querySelectorAll("table.data").forEach(function (table) {
  var tbody = table.tBodies[0]; if (!tbody) return; var original = Array.prototype.slice.call(tbody.rows);
  table.querySelectorAll("th.sortable").forEach(function (th) {
    var index = th.cellIndex; th.setAttribute("tabindex", "0"); th.setAttribute("role", "columnheader");
    function go() { var order = th.getAttribute("aria-sort") === "ascending" ? "descending" : th.getAttribute("aria-sort") === "descending" ? null : "ascending"; table.querySelectorAll("th").forEach(function (other) { other.removeAttribute("aria-sort"); }); if (!order) { original.forEach(function (row) { tbody.appendChild(row); }); return; } th.setAttribute("aria-sort", order); var dir = order === "ascending" ? 1 : -1; var numeric = th.dataset.type === "numeric"; Array.prototype.slice.call(tbody.rows).sort(function (a, b) { var av = value(a.cells[index]), bv = value(b.cells[index]); return numeric ? dir * (num(av) - num(bv)) : dir * av.localeCompare(bv); }).forEach(function (row) { tbody.appendChild(row); }); if (window.__paginate) window.__paginate.reset(); }
    th.addEventListener("click", go); th.addEventListener("keydown", function (event) { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); go(); } });
  });
  function value(cell) { return (cell.dataset.sort || cell.dataset.value || cell.textContent).trim(); } function num(value) { return parseFloat(value.replace(/[^0-9.-]/g, "")) || 0; }
});
document.querySelectorAll("[data-filter-table]").forEach(function (input) { input.addEventListener("input", function () { var query = input.value.toLowerCase(), name = input.dataset.filterTable, selector = "#" + name + ", table[data-filter-group='" + name + "']", tables = document.querySelectorAll(selector); tables.forEach(function (table) { table.querySelectorAll("tbody tr").forEach(function (row) { row.hidden = row.textContent.toLowerCase().indexOf(query) === -1; }); }); document.querySelectorAll("[data-section-of='" + name + "']").forEach(function (section) { section.hidden = !section.querySelector("tbody tr:not([hidden])"); }); var count = document.querySelector("[data-count-for='" + name + "']"); if (count) { var total = 0, visible = 0; tables.forEach(function (table) { total += table.querySelectorAll("tbody tr").length; visible += table.querySelectorAll("tbody tr:not([hidden])").length; }); count.textContent = visible + " of " + total + " shown"; } if (window.__paginate) window.__paginate.reset(); }); });
document.querySelectorAll("[data-expands]").forEach(function (btn) { var target = document.getElementById(btn.dataset.expands); if (!target) return; target.hidden = true; btn.addEventListener("click", function () { target.hidden = !target.hidden; btn.setAttribute("aria-expanded", String(!target.hidden)); btn.textContent = btn.textContent.replace(target.hidden ? "Hide" : "Show", target.hidden ? "Show" : "Hide"); btn.classList.toggle("btn-primary", !target.hidden); }); });
