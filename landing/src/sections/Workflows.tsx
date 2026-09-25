import { Typo } from "@imfusion/web-ui";
import { WORKFLOW_PY } from "../content";
import { CodeBlock, PerspectiveLayers } from "../ui";
import registration from "../../assets/registration.webp";

export function Workflows() {
  return (
    <section className="section section--dark" id="workflows">
      <div className="layers-bg">
        <PerspectiveLayers count={14} sweep={164} decay={0.964} spin={230} />
      </div>

      <div className="wrap">
        <div className="split split--reverse">
          <div className="split__intro" data-reveal>
            <Typo.H2 className="section__title" variant="oncolor">
              Guided workflows
            </Typo.H2>
            <Typo.Lead variant="oncolor">
              When a study has to run in a fixed order, describe it as a list of steps. WebAppKit
              draws the panel and keeps the step state on that visitor's session.
            </Typo.Lead>
            <Typo.UnorderedList className="ticks" variant="oncolor">
              <li>
                Steps for loading, input roles, parameters, processing, brush correction, validation
                and export.
              </li>
              <li>
                Progress and cancellation are already wired up, and a reviewer can reject a result
                and step back without restarting.
              </li>
            </Typo.UnorderedList>
          </div>

          <div className="split__code" data-reveal>
            <CodeBlock language="workflow.py">{WORKFLOW_PY}</CodeBlock>
            {/* `support` rather than `oncolor`: the ink band remaps the surface
                tokens, so this resolves to a muted light grey instead of the
                full-strength white that would compete with the code. */}
            <Typo.Small className="code__caption" variant="support">
              Eight steps in the order they run, from the segmentation example. The validation step is
              the one that can send the operator back to the brush.
            </Typo.Small>
          </div>
        </div>

        <figure className="shot shot--wide" data-reveal>
          <div className="shot__frame">
            <img
              className="shot__img"
              src={registration}
              width={2880}
              height={1800}
              alt="The registration example at its input step: three orthogonal views and a 3D
                rendering of two brain MRI sessions loaded but not yet aligned, a data model
                listing both sessions, and a workflow panel for assigning the fixed and moving
                roles."
            />
          </div>
          <Typo.Small className="shot__caption" variant="support">
            The screenshot is a different workflow from the snippet above: two steps that assign
            fixed and moving images by role, then the registered result lands in the data model.
          </Typo.Small>
        </figure>
      </div>
    </section>
  );
}
