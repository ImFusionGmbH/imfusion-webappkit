import { Typo } from "@imfusion/web-ui";
import { APP_PY } from "../content";
import { CodeBlock } from "../ui";
import { DemoFrame } from "./Demo";

/**
 * The source and the result in one band. They were briefly two sections, but a
 * heading break between a snippet and the application it produces argues they
 * are separate ideas, which is the opposite of the point.
 */
export function HowItWorks() {
  return (
    <section className="section section--light" id="your-code">
      <div className="wrap">
        <div className="split">
          <div className="split__intro" data-reveal>
            <Typo.H2 className="section__title">Creating an app</Typo.H2>
            <Typo.Lead>
              Decorate a function with the name you want on the button. WebAppKit builds the
              controls from the parameter types and runs the call on the ImFusion SDK thread, then
              publishes a returned image into the session the viewer is showing.
            </Typo.Lead>
            <Typo.UnorderedList className="ticks">
              <li>
                Argument types pick the controls, so a float with bounds arrives as a slider and an
                image argument as a dataset selector.
              </li>
              <li>
                An existing ImFusion algorithm can be registered by name when the processing you
                want is already in the SDK.
              </li>
            </Typo.UnorderedList>
          </div>

          <div className="split__code" data-reveal>
            <CodeBlock language="app.py">{APP_PY}</CodeBlock>
          </div>
        </div>

        <DemoFrame />
      </div>
    </section>
  );
}
