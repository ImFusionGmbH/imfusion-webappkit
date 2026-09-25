import type { ReactNode } from "react";
import { Card, Row, Typo } from "@imfusion/web-ui";

interface Capability {
  title: string;
  body: ReactNode;
  meta?: string[];
  wide?: boolean;
  brand?: boolean;
}

const CAPABILITIES: Capability[] = [
  {
    title: "The viewer",
    wide: true,
    body: (
      <>
        MPR, 3D and 2D views with the display options and interactions people already know from
        ImFusion Suite. Layout and which views are visible are set from Python.
      </>
    ),
    meta: ["ViewLayout", "LayoutConfig"],
  },
  {
    title: "The data model",
    body: (
      <>
        Add, rename or clear data through <Typo.InlineCode>app.data_model</Typo.InlineCode> and the
        browser follows.
      </>
    ),
  },
  {
    title: "A session per visitor",
    body: (
      <>
        Each browser connection has its own data and workflow state, so two people can open the
        app without sharing a volume or a step.
      </>
    ),
  },
  {
    title: "Branding",
    brand: true,
    body: (
      <>
        Logo, colours, panel widths, an About dialog, and bundled sample datasets are set from the
        same Python configuration.
      </>
    ),
    meta: ["BrandingConfig", "ThemeConfig"],
  },
  {
    title: "A command line",
    body: (
      <>
        <Typo.InlineCode>doctor</Typo.InlineCode> checks your environment,{" "}
        <Typo.InlineCode>demo</Typo.InlineCode> runs a sample app,{" "}
        <Typo.InlineCode>init</Typo.InlineCode> scaffolds a project, and{" "}
        <Typo.InlineCode>record</Typo.InlineCode> writes a snapshot you can host with no backend.
      </>
    ),
  },
];

export function Capabilities() {
  return (
    <section className="section section--grey" id="included">
      <div className="wrap">
        <div className="section__head" data-reveal>
          <Typo.H2 className="section__title">What's included</Typo.H2>
          <Typo.Lead>
            The viewer, the HTTP server, and a session for each browser connection come with the
            kit. The imaging function stays in Python and runs on the SDK thread.
          </Typo.Lead>
        </div>

        <div className="cards">
          {CAPABILITIES.map((capability, index) => (
            <div
              key={capability.title}
              className={`cards__cell${capability.wide ? " cards__cell--wide" : ""}`}
              data-reveal
            >
              <Card.Root
                className={`card${capability.brand ? " card--brand" : ""}`}
                variant={capability.brand ? "brand" : "main"}
                shadow="none"
                density="comfortable"
              >
                <Card.Header>
                  <span className="card__idx">{String(index + 1).padStart(2, "0")}</span>
                  <Typo.H3 spacing="none" variant={capability.brand ? "oncolor" : "main"}>
                    {capability.title}
                  </Typo.H3>
                </Card.Header>
                <Card.Content>
                  <Typo.P spacing="none" variant={capability.brand ? "oncolor" : "support"}>
                    {capability.body}
                  </Typo.P>
                </Card.Content>
                {capability.meta && (
                  <Card.Footer>
                    {/* Inline code, not Chip: a Chip label is uppercased, which
                        would turn these API names into VIEWLAYOUT. */}
                    <Row gap="2" wrap>
                      {capability.meta.map(item => (
                        <Typo.InlineCode key={item} className="card__tag">
                          {item}
                        </Typo.InlineCode>
                      ))}
                    </Row>
                  </Card.Footer>
                )}
              </Card.Root>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
