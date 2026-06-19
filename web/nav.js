// Single-source nav for the whole Trade site. Edit HERE once → every page updates.
// Each page just needs: <div id="nav"></div> + <script src="./nav.js"></script>
const NAV = [
  { h: "index.html", t: "◆ Strategy Book" },
  { h: "stocks.html", t: "📈 Stocks — Spike Hunter" },
  { h: "scans.html", t: "🗓️ Daily Scan — report archive" },
  { h: "board.html", t: "📊 Backtest Board — full panel + gauntlet" },
  { h: "backtest-spike.html", t: "🎯 Backtest Spike — framework validation" },
];
(function () {
  const cur = location.pathname.split("/").pop() || "index.html";
  const el = document.getElementById("nav");
  if (!el) return;
  el.className = "nav";
  el.innerHTML = NAV.map(n =>
    `<a href="./${n.h}"${n.h === cur ? ' class="home"' : ""}>${n.t}</a>`
  ).join("");
})();
