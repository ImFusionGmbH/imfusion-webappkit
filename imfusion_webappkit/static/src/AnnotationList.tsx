import { formatPoint } from './annotations';
import type { AnnotationDescriptor } from './types';

/**
 * Live state of a set of annotations.
 *
 * Shared by the annotation workflow step, the `AnnotationField` custom-step
 * element and the annotation action parameter, so all three report placement
 * the same way.
 */
export function AnnotationList({
  annotations,
  showMeasurements = false,
  activeId = null,
}: {
  annotations: AnnotationDescriptor[];
  showMeasurements?: boolean;
  activeId?: string | null;
}) {
  if (!annotations.length) return null;

  return (
    <ul className="annotation-list">
      {annotations.map((annotation, index) => {
        const name = annotation.prompt
          || annotation.label
          || annotation.name
          || `${annotation.type} ${index + 1}`;
        const measurement = showMeasurements
          ? annotation.length !== null
            ? `${annotation.length.toFixed(1)} mm`
            : annotation.angle !== null
              ? `${annotation.angle.toFixed(1)}°`
              : ''
          : '';
        return (
          <li
            key={annotation.id}
            className={`annotation-list__item ${
              annotation.id === activeId ? 'annotation-list__item--active' : ''
            } ${annotation.complete ? 'annotation-list__item--complete' : ''}`}
          >
            <span className="annotation-list__name">
              <i
                className={`bi ${
                  annotation.complete
                    ? 'bi-check-circle-fill'
                    : annotation.id === activeId
                      ? 'bi-record-circle'
                      : 'bi-circle'
                }`}
              />
              {name}
            </span>
            {annotation.error ? (
              <span className="annotation-list__error">{annotation.error}</span>
            ) : annotation.points.length ? (
              <span className="annotation-list__points">
                {annotation.points.map((point) => formatPoint(point)).join('  |  ')}
              </span>
            ) : (
              <span className="annotation-list__pending">Not placed</span>
            )}
            {measurement && <span className="annotation-list__measurement">{measurement}</span>}
          </li>
        );
      })}
    </ul>
  );
}
