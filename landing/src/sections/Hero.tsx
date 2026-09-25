import { Button, Row, Typo } from "@imfusion/web-ui";
import { HERO_LEAD, INSTALL_COMMANDS, PIP_COMMANDS } from "../content";
import { ArrowRight, CodeBlock, PerspectiveLayers } from "../ui";
import appOverview from "../../assets/app-overview.webp";

export function Hero() {
  return (
    <section className="hero">
      <div className="hero__field">
        <PerspectiveLayers count={17} sweep={172} decay={0.972} spin={170} />
      </div>

      <div className="wrap hero__inner">
        <div className="hero__head" data-reveal>
          <Typo.H1 className="hero__title" variant="oncolor">
            Python imaging algorithms <em>in a medical web viewer</em>
          </Typo.H1>
        </div>

        <div className="hero__copy" data-reveal>
          <Typo.Lead variant="oncolor" className="hero__lead">
            {HERO_LEAD}
          </Typo.Lead>

          <div className="hero__start">
            <Typo.Small className="hero__label" variant="support">
              From a checkout of the repository
            </Typo.Small>
            <CodeBlock className="hero__command" language="shell">
              {INSTALL_COMMANDS}
            </CodeBlock>
            <Typo.Small className="hero__label" variant="support">
              With pip.
            </Typo.Small>
            <CodeBlock className="hero__command" language="shell">
              {PIP_COMMANDS}
            </CodeBlock>
          </div>

          <Row className="hero__buttons" gap="3" align="center" wrap>
            <Button
              size="hero"
              variant="primary"
              endIcon={<ArrowRight />}
              render={<a href="#demo" />}
            >
              Live demo
            </Button>
            <Button size="hero" variant="outline" render={<a href="#get-started" />}>
              Get started
            </Button>
          </Row>
        </div>

        {/* Wider than its column, so it keeps enough scale to be legible and
            runs off the right edge instead of shrinking to fit. */}
        <div className="hero__shot" data-reveal>
          <div className="shot__frame">
            <div className="shot__chrome">
              <span className="shot__dots">
                <i />
                <i />
                <i />
              </span>
              <span className="shot__url">localhost:8000</span>
            </div>
            <img
              className="shot__img"
              src={appOverview}
              width={2880}
              height={1800}
              alt="The WebAppKit demo in a browser: a CT volume in three orthogonal views and a 3D
                rendering, with a sidebar of datasets, layout and display controls and a row of
                algorithm buttons in the header."
            />
          </div>
        </div>
      </div>
    </section>
  );
}
