import { Typo } from "@imfusion/web-ui";
import simpleShot from "../../assets/template-simple.webp";
import workflowShot from "../../assets/template-workflow.webp";
import monaiShot from "../../assets/template-monai.webp";
import chatShot from "../../assets/template-chat.webp";

const TEMPLATES = [
  {
    flag: "simple",
    title: "One action",
    body: "One button, the parameters you declared, and the function behind them: this is the default, and the smallest of the four.",
    image: simpleShot,
    width: 840,
    height: 624,
    alt: "A Segment Image dialog with a dataset selector and an intensity threshold field.",
  },
  {
    flag: "workflow",
    title: "A guided workflow",
    body: "The workflow starter from the section above: load, process, brush-correct, and a review the operator has to accept before export.",
    image: workflowShot,
    width: 640,
    height: 440,
    alt: "A workflow panel on step 6 of 7, Review Result, asking whether the corrected segmentation is acceptable, with Reject and Accept buttons.",
  },
  {
    flag: "monai",
    title: "A MONAI model",
    body: "The spleen bundle from the MONAI Model Zoo, run on the sample CT. The download, tensor layout and coordinate conversions are already in the template.",
    image: monaiShot,
    width: 652,
    height: 652,
    alt: "A 3D rendering of the chest CT with the spleen shaded red where the model segmented it.",
  },
  {
    flag: "chat",
    title: "A conversational assistant",
    body: "A chat panel that can see the selected dataset. The reply function is a placeholder you replace with a call to your own model.",
    image: chatShot,
    width: 720,
    height: 880,
    alt: "An assistant panel with a short conversation about a selected medical image dataset.",
  },
];

export function Templates() {
  return (
    <section className="section section--grey" id="templates">
      <div className="wrap">
        <div className="section__head" data-reveal>
          <Typo.H2 className="section__title">Start from a template</Typo.H2>
          <Typo.Lead>
            <Typo.InlineCode>imfusion-webappkit init</Typo.InlineCode> writes a project that already
            runs, so the first edit is the processing function rather than the application shell.
          </Typo.Lead>
        </div>

        <ul className="tpl">
          {TEMPLATES.map(template => (
            <li key={template.flag} data-reveal>
              <div className="tpl__shot">
                <img
                  src={template.image}
                  width={template.width}
                  height={template.height}
                  alt={template.alt}
                  loading="lazy"
                />
              </div>
              <Typo.Small className="tpl__flag" variant="support">
                --template {template.flag}
              </Typo.Small>
              <Typo.H3 className="tpl__title">{template.title}</Typo.H3>
              <Typo.P spacing="none" variant="support">
                {template.body}
              </Typo.P>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
