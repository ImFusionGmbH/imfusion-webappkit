import { Button, Row, Typo } from "@imfusion/web-ui";
import { CONTACT_URL, DOCS_URL, repoPath } from "../content";
import { GitHubMark, PerspectiveLayers } from "../ui";

export function Cta() {
  return (
    <section className="cta">
      <div className="cta__field">
        <PerspectiveLayers count={12} sweep={148} decay={0.958} spin={62} fade={0.86} />
      </div>

      <div className="wrap cta__inner" data-reveal>
        <Typo.Lead variant="oncolor" className="cta__lead">
          The ImFusion WebAppKit is an early prototype - feel free to send us feedback!
        </Typo.Lead>

        <Row className="cta__buttons" gap="3" align="center" wrap>
          <Button variant="secondary" render={<a href={DOCS_URL} />}>
            Read the documentation
          </Button>
          <Button
            variant="ghost"
            className="btn--oncolor"
            startIcon={<GitHubMark />}
            render={<a href={repoPath("imfusion_webappkit/examples")} />}
          >
            Browse the examples
          </Button>
          <Button
            variant="ghost"
            className="btn--oncolor"
            render={<a href={CONTACT_URL} />}
          >
            info@imfusion.com
          </Button>
        </Row>

        <Typo.Small className="cta__terms" variant="oncolor">
          This project depends on the ImFusion SDK, which is free for non-commercial use. For anything commercial,{" "}
          <a href="https://imfusion.com/contact">get in touch</a>.
        </Typo.Small>
      </div>
    </section>
  );
}
