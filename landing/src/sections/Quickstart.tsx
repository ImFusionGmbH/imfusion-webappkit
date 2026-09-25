import { Typo } from "@imfusion/web-ui";
import { docsPage, INIT_COMMANDS, INSTALL_COMMANDS, PIP_COMMANDS } from "../content";
import { CodeBlock } from "../ui";

const WRITES = [
  ["app.py", "contains the application, its actions or its workflow steps"],
  ["algorithm.py", "is the processing function you replace with your own"],
  ["AGENTS.md", "tells coding agents the conventions for sessions, threading and geometry"],
];

export function Quickstart() {
  return (
    <section className="section section--light" id="get-started">
      <div className="wrap">
        <div className="section__head section__head--center" data-reveal>
          <Typo.H2 className="section__title">Get started</Typo.H2>
        </div>

        <ol className="steps steps--pair">
          <li data-reveal>
            <span className="steps__n">01</span>
            <Typo.H3 className="steps__title">Run the bundled demo</Typo.H3>
            <Typo.P variant="support">
              Install the package and start the demo, or sync the dependencies in a checkout of the
              repository if you need more customisation.
            </Typo.P>
            <CodeBlock language="shell" className="steps__code">
              {PIP_COMMANDS}
            </CodeBlock>
            <Typo.Small className="steps__alt" variant="support">
              or from a checkout
            </Typo.Small>
            <CodeBlock language="shell" className="steps__code">
              {INSTALL_COMMANDS}
            </CodeBlock>
          </li>

          <li data-reveal>
            <span className="steps__n">02</span>
            <Typo.H3 className="steps__title">Start your own</Typo.H3>
            <Typo.P variant="support">
              Scaffold one of the templates above. You get a project that already runs, ready to be customised:
            </Typo.P>
            <Typo.UnorderedList className="steps__writes" spacing="none">
              {WRITES.map(([file, description]) => (
                <li key={file}>
                  <Typo.InlineCode>{file}</Typo.InlineCode> {description}
                </li>
              ))}
            </Typo.UnorderedList>
            <CodeBlock language="shell" className="steps__code">
              {INIT_COMMANDS}
            </CodeBlock>
            <Typo.Small className="steps__alt" variant="support">
              <a href={docsPage("cli")}>The command-line reference</a> covers the other templates and
              flags.
            </Typo.Small>
          </li>
        </ol>
      </div>
    </section>
  );
}
