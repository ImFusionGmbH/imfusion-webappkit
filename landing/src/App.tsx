import { useEffect } from "react";
import { Nav } from "./sections/Nav";
import { Hero } from "./sections/Hero";
import { HowItWorks } from "./sections/HowItWorks";
import { Capabilities } from "./sections/Capabilities";
import { Workflows } from "./sections/Workflows";
import { Templates } from "./sections/Templates";
import { Quickstart } from "./sections/Quickstart";
import { Cta } from "./sections/Cta";
import { Footer } from "./sections/Footer";

/**
 * Reveals `[data-reveal]` elements as they scroll into view, staggering
 * siblings so a row of cards arrives in sequence rather than all at once.
 */
function useReveals() {
  useEffect(() => {
    const targets = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reducedMotion || !("IntersectionObserver" in window)) {
      targets.forEach(element => element.classList.add("is-in"));
      return;
    }

    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const element = entry.target as HTMLElement;
          const siblings = Array.from(element.parentElement?.children ?? []).filter(sibling =>
            sibling.hasAttribute("data-reveal")
          );
          const index = Math.max(0, siblings.indexOf(element));
          element.style.transitionDelay = `${Math.min(index, 6) * 70}ms`;
          element.classList.add("is-in");
          observer.unobserve(element);
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0 }
    );

    targets.forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, []);
}

export function App() {
  useReveals();

  return (
    <>
      <a className="skip-link" href="#your-code">
        Skip to content
      </a>
      <Nav />
      <main id="top">
        <Hero />
        <HowItWorks />
        <Capabilities />
        <Workflows />
        <Templates />
        <Quickstart />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
