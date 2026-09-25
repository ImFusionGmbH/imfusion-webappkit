import { useState } from "react";
import { Button, Typo } from "@imfusion/web-ui";
import { docsPage } from "../content";
import poster from "../../assets/demo-poster.webp";

/** `index.html` is required: Vite's dev server treats `/demo/` as a SPA route
 *  and would serve this landing page into the iframe. */
const DEMO_URL = `${import.meta.env.BASE_URL}demo/index.html`;

/**
 * The second half of "What you write": the application that snippet produces,
 * running for real, directly below its own source.
 *
 * It stays behind a poster until asked for. The viewer is a WebAssembly build of
 * the ImFusion library and costs several megabytes, which is a poor trade for
 * the majority of visitors who will scroll past — and an unacceptable one on the
 * mobile connections where the launch button is hidden outright.
 */
export function DemoFrame() {
  const [launched, setLaunched] = useState(false);
  const [ready, setReady] = useState(false);

  return (
    <div className="demo" id="demo">
      <div className="demo__head" data-reveal>
        <Typo.Lead>
          The threshold snippet above, played back in this page. You can scroll the slices, change
          the window, and rearrange the layout. The Threshold button does not run Python, because
          this page is a static recording rather than a server.
        </Typo.Lead>
      </div>

      <figure className="demo__figure" data-reveal>
        <div className="shot__frame">
          <div className="shot__chrome">
            <span className="shot__dots">
              <i />
              <i />
              <i />
            </span>
            <span className="shot__url">localhost:8000</span>
          </div>

          <div className="demo__stage">
            <img
              className="demo__poster"
              src={poster}
              width={2880}
              height={1800}
              alt="The Image Tools demo in a browser: a chest CT in axial, sagittal and
                coronal views with a 3D rendering beside them, a sidebar listing the sample
                dataset with view and display controls, and a Threshold button in the header."
            />

            {launched && (
              <iframe
                className={`demo__frame${ready ? " demo__frame--ready" : ""}`}
                src={DEMO_URL}
                title="ImFusion WebAppKit demo"
                onLoad={() => setReady(true)}
                allow="fullscreen"
              />
            )}

            {!launched && (
              <div className="demo__launch">
                <Button size="hero" variant="primary" onClick={() => setLaunched(true)}>
                  Launch the demo
                </Button>
                <Typo.Small variant="oncolor" className="demo__weight">
                  Runs in this tab · about 6 MB
                </Typo.Small>
              </div>
            )}

            {launched && !ready && (
              <div className="demo__launch demo__launch--loading">
                <Typo.Small variant="oncolor">Starting the viewer…</Typo.Small>
              </div>
            )}
          </div>
        </div>

        <Typo.Small className="demo__desktop-only" variant="support">
          The live demo needs a desktop browser. Above is a screenshot of it running.
        </Typo.Small>
        <Typo.Small className="code__caption" variant="support">
          This is a recorded WebAppKit app: nothing is sent to a server; everything runs in this tab. Build a recording like this with{" "}
          <Typo.InlineCode>record</Typo.InlineCode>. See the{" "}
          <a href={docsPage("guides/static-demos")}>static demos guide</a>.
        </Typo.Small>
      </figure>
    </div>
  );
}
