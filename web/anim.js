// Motion One — vanilla-JS engine by the Framer Motion author (same API, no React/build).
// Staggered entrance + scroll-reveal for the static dashboards.
import { animate, inView, stagger } from "https://cdn.jsdelivr.net/npm/motion@11.11.13/+esm";

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const E = [0.2, 0.7, 0.2, 1];

if (!reduce) {
  // 1. hero load-in (staggered)
  const hero = [".eyebrow", "h1", ".lede", ".chips", ".nav"]
    .map(s => document.querySelector(s)).filter(Boolean);
  if (hero.length)
    animate(hero, { opacity: [0, 1], transform: ["translateY(14px)", "translateY(0)"] },
      { delay: stagger(0.07), duration: 0.55, easing: "ease-out" });

  // 2. scoreboard cards — staggered pop after hero
  const bots = document.querySelectorAll(".bot");
  if (bots.length)
    animate(bots, { opacity: [0, 1], transform: ["translateY(18px) scale(.97)", "translateY(0) scale(1)"] },
      { delay: stagger(0.05, { start: 0.35 }), duration: 0.5, easing: E });

  // 3. section reveals on scroll (h2 + content cards; in-view fires for above-fold too)
  document.querySelectorAll("h2, .card:not(.bot)").forEach(el => {
    el.style.opacity = "0";
    inView(el, () => {
      animate(el, { opacity: [0, 1], transform: ["translateY(20px)", "translateY(0)"] },
        { duration: 0.5, easing: "ease-out" });
      return () => {}; // run once
    }, { margin: "0px 0px -12% 0px" });
  });

  // 4. table rows cascade when their card scrolls in
  document.querySelectorAll("tbody").forEach(tb => {
    const rows = tb.querySelectorAll("tr");
    inView(tb.closest(".card") || tb, () => {
      animate(rows, { opacity: [0, 1], transform: ["translateX(-8px)", "translateX(0)"] },
        { delay: stagger(0.04), duration: 0.4, easing: "ease-out" });
    }, { margin: "0px 0px -8% 0px" });
  });
}
