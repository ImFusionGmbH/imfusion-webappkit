import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Button } from '@imfusion/web-ui';
import { usePythonBridge } from '../PythonBridge';
import { AnnotationList } from '../AnnotationList';
import { ParameterFields } from '../controls';
import type { FieldsElement, WorkflowStep, WorkflowUIElement } from '../types';
import { CustomChart } from './Chart';

function CustomFields({ element }: { element: FieldsElement }) {
  const bridge = usePythonBridge();
  const descriptors = useMemo(
    () => Object.fromEntries(element.parameters.map((parameter) => [parameter.name, parameter])),
    [element.parameters],
  );
  const serverValues = useMemo(
    () => Object.fromEntries(element.parameters.map((parameter) => [parameter.name, parameter.value])),
    [element.parameters],
  );
  const [values, setValues] = useState<Record<string, unknown>>(serverValues);

  useEffect(() => {
    setValues(serverValues);
  }, [JSON.stringify(serverValues)]);

  const submitAction = element.submit_action;
  return (
    <div
      // Enter submits a composer such as a chat message without a visible
      // button; Shift+Enter still inserts a newline in a multi-line field.
      onKeyDown={
        submitAction
          ? (event) => {
              if (event.key !== 'Enter' || event.shiftKey || bridge.busy.active) return;
              event.preventDefault();
              bridge.workflowRun(submitAction);
            }
          : undefined
      }
    >
      <ParameterFields
        parameters={descriptors}
        values={values}
        onChange={(next) => {
          setValues(next);
          bridge.sendWorkflowData({ values: next });
        }}
      />
    </div>
  );
}

function CustomElement({ element }: { element: WorkflowUIElement }) {
  const bridge = usePythonBridge();
  switch (element.kind) {
    case 'text':
      return (
        <div className="workflow-step-custom__text">
          <ReactMarkdown>{element.content}</ReactMarkdown>
        </div>
      );
    case 'alert':
      return (
        <div
          className={`workflow-step-custom__alert workflow-step-custom__alert--${element.level}`}
          role="status"
        >
          {element.content}
        </div>
      );
    case 'metrics':
      return (
        <dl className="workflow-step-custom__metrics">
          {element.items.map((item) => (
            <div className="workflow-step-custom__metric" key={item.label}>
              <dt>{item.label}</dt>
              <dd>
                {String(item.value)}
                {item.unit && <span className="workflow-step-custom__metric-unit">{item.unit}</span>}
              </dd>
            </div>
          ))}
        </dl>
      );
    case 'table':
      return (
        <table className="workflow-step-custom__table">
          {element.caption && <caption>{element.caption}</caption>}
          <thead>
            <tr>{element.columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {element.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell === null ? '' : String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    case 'chart':
      return <CustomChart element={element} />;
    case 'image':
      return (
        <figure className="workflow-step-custom__figure">
          <img
            className="workflow-step-custom__image"
            src={`data:${element.media_type};base64,${element.data}`}
            alt={element.alt ?? element.caption ?? ''}
          />
          {element.caption && <figcaption>{element.caption}</figcaption>}
        </figure>
      );
    case 'fields':
      return <CustomFields element={element} />;
    case 'annotation':
      return (
        <div className="workflow-step-custom__annotation">
          {element.label && (
            <h4 className="workflow-step-custom__annotation-label">{element.label}</h4>
          )}
          <AnnotationList
            annotations={element.annotations}
            showMeasurements={element.show_measurements}
            activeId={
              element.annotations.find((annotation) => annotation.editing)?.id ?? null
            }
          />
          {(element.place_action || element.clear_action) && (
            <div className="workflow-step-custom__annotation-actions">
              {element.place_action && (
                <Button
                  size="sm"
                  variant="primary"
                  startIcon={<i className="bi bi-vector-pen" />}
                  disabled={element.annotations.some((annotation) => annotation.editing)}
                  onClick={() => bridge.sendWorkflowData({ action: element.place_action })}
                >
                  Place
                </Button>
              )}
              {element.clear_action && (
                <Button
                  size="sm"
                  variant="secondary"
                  startIcon={<i className="bi bi-trash" />}
                  disabled={!element.annotations.some((annotation) => annotation.points.length)}
                  onClick={() => bridge.sendWorkflowData({ action: element.clear_action })}
                >
                  Clear
                </Button>
              )}
            </div>
          )}
        </div>
      );
    case 'button':
      return (
        <Button
          size="sm"
          variant={element.style === 'danger' ? 'negative' : element.style === 'primary' ? 'primary' : 'secondary'}
          className="workflow-step-custom__button"
          disabled={element.disabled || (element.job && bridge.busy.active)}
          onClick={() => {
            if (element.job) bridge.workflowRun(element.action);
            else bridge.sendWorkflowData({ action: element.action });
          }}
        >
          {element.label}
        </Button>
      );
    default:
      return null;
  }
}

export function WorkflowCustomStep({ step }: { step: WorkflowStep }) {
  const elements = step.ui_config.body ?? [];
  if (!elements.length) {
    return <div className="workflow-step-message">{step.ui_config.message ?? 'Custom workflow step'}</div>;
  }

  // A composer — a chat's message field and its buttons — stays visible
  // while everything above it, such as a transcript or a summary, scrolls on
  // its own. Only a *trailing* run of Fields/Button elements counts as the
  // composer, so a step with no such controls at the end is unaffected.
  let split = elements.length;
  while (split > 0 && (elements[split - 1].kind === 'fields' || elements[split - 1].kind === 'button')) {
    split -= 1;
  }
  const history = elements.slice(0, split);
  const footer = elements.slice(split);

  const historyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Jump to the newest entry, e.g. a chat reply, rather than leaving it
    // below the fold under the fixed composer.
    const container = historyRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [JSON.stringify(history)]);

  return (
    <div className="workflow-step-custom">
      {history.length > 0 && (
        <div className="workflow-step-custom__history" ref={historyRef}>
          {history.map((element, index) => (
            <CustomElement key={index} element={element} />
          ))}
        </div>
      )}
      {footer.length > 0 && (
        <div className="workflow-step-custom__footer">
          {/* `index` alone, not `split + index`: the footer is always the
              same fields/buttons in the same order, and keying it off `split`
              — which grows with the transcript — remounted the message field
              on every send, dropping focus after each message. */}
          {footer.map((element, index) => (
            <CustomElement key={index} element={element} />
          ))}
        </div>
      )}
    </div>
  );
}
