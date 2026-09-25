import { usePythonBridge } from './PythonBridge';

/** Connection state, plus the progress and cancel control of a running job.
 *
 * Belongs in the status bar; the header takes it over for apps that hide the
 * status bar, which is why the caller supplies the placement class. */
export function StatusIndicator({ className }: { className: string }) {
  const bridge = usePythonBridge();
  // Busy is the wider of the two: a transfer is not a job, but it is still a
  // reason the client is waiting, and it belongs in the same place.
  const busy = bridge.busy.active;
  const percentage = bridge.busy.progress === null
    ? null
    : Math.round(bridge.busy.progress * 100);
  const state = busy && bridge.status !== 'error' ? 'processing' : bridge.status;

  return (
    <span className={`status-indicator ${className} status-${state}`}>
      <span className="status-indicator__row">
        <span className="status-text">
          {busy
            ? `${bridge.busy.label}${percentage === null ? '' : ` ${percentage}%`}`
            : bridge.status}
        </span>
      </span>
      {busy && percentage !== null && (
        <span
          className="progress-bar"
          role="progressbar"
          aria-label="Processing progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percentage}
        >
          <span className="progress-bar__fill" style={{ width: `${percentage}%` }} />
        </span>
      )}
      {/* Last, so it never comes between the percentage and the bar it belongs to. */}
      {bridge.activeJob && (
        <button
          className="status-indicator__cancel"
          title={bridge.activeJob.status === 'cancel_requested'
            ? 'Cancel requested'
            : 'Cancel processing'}
          aria-label={bridge.activeJob.status === 'cancel_requested'
            ? 'Cancel requested'
            : 'Cancel processing'}
          disabled={bridge.activeJob.status === 'cancel_requested'}
          onClick={bridge.cancelJob}
        >
          <i className="bi bi-x-lg" />
        </button>
      )}
    </span>
  );
}
