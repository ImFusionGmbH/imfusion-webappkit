/**
 * The two pieces of interface a recording needs and a live application does
 * not: a standing reminder that nothing is being computed by a server, and an
 * explanation for the interactions the recording has no answer for.
 *
 * Both render nothing when Python is behind the page.
 */

import { Button } from '@imfusion/web-ui';
import { usePythonBridge } from '../PythonBridge';
import { Modal } from '../Modal';

export function DemoChrome() {
  const bridge = usePythonBridge();
  if (!bridge.recorded) return null;

  return (
    <>
      <div className="demo-badge">Recorded demo — no Python behind this page</div>
      {bridge.notice && (
        <Modal
          className="demo-notice"
          title="That interaction was not recorded"
          onClose={bridge.dismissNotice}
          footer={(
            <Button size="sm" variant="primary" type="button" onClick={bridge.dismissNotice}>
              Keep exploring
            </Button>
          )}
        >
          <p>{bridge.notice}</p>
        </Modal>
      )}
    </>
  );
}
