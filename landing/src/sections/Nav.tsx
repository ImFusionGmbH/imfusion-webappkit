import { useEffect, useState } from "react";
import { Button, ImFusionLogo, Row } from "@imfusion/web-ui";
import { DOCS_URL, REPO_URL } from "../content";
import { GitHubMark } from "../ui";

const LINKS = [
  { href: "#your-code", label: "Creating an app" },
  { href: "#workflows", label: "Workflows" },
  { href: "#templates", label: "Templates" },
  { href: "#get-started", label: "Get started" },
];

/** True once the page has scrolled far enough for the nav to need a ground. */
function useStuckNav() {
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        setStuck(window.scrollY > 24);
        ticking = false;
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return stuck;
}

export function Nav() {
  const stuck = useStuckNav();
  const [open, setOpen] = useState(false);

  return (
    <header className={`nav${stuck ? " is-stuck" : ""}${open ? " is-open" : ""}`}>
      <div className="wrap nav__inner">
        {/* The glyph already reads as ImFusion, so the wordmark beside it carries
            the product name rather than repeating the company's. */}
        <a className="brand" href="#top" aria-label="ImFusion WebAppKit, top of page">
          <ImFusionLogo glyph size="xs" variant="oncolor" />
          <span className="brand__text">
            <b>ImFusion WebAppKit</b>
          </span>
        </a>

        <nav className="nav__links" aria-label="Sections">
          {LINKS.map(link => (
            <a key={link.href} href={link.href} onClick={() => setOpen(false)}>
              {link.label}
            </a>
          ))}
        </nav>

        <Row className="nav__cta" gap="2" align="center">
          <Button
            size="sm"
            variant="ghost"
            render={<a href={REPO_URL} aria-label="Source on GitHub" />}
            startIcon={<GitHubMark />}
          >
            <span className="nav__label">GitHub</span>
          </Button>
          <Button size="sm" variant="ghost" className="nav__docs" render={<a href={DOCS_URL} />}>
            Documentation
          </Button>
          <Button size="sm" variant="primary" render={<a href="#demo" />}>
            Live demo
          </Button>
        </Row>

        <button
          className="nav__toggle"
          type="button"
          aria-expanded={open}
          aria-label="Toggle navigation"
          onClick={() => setOpen(value => !value)}
        >
          <span />
          <span />
        </button>
      </div>
    </header>
  );
}
