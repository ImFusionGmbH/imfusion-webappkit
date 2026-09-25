import { ImFusionLogo, Typo } from "@imfusion/web-ui";

export function Footer() {
  return (
    <footer className="foot">
      <div className="wrap foot__inner">
        <a className="foot__brand" href="https://www.imfusion.com/">
          <ImFusionLogo size="sm" variant="oncolor" />
        </a>

        <Typo.Small className="foot__legal" variant="oncolor">
          imfusion-webappkit 0.3.1 · alpha
        </Typo.Small>
      </div>
    </footer>
  );
}
