import type { ChartElement } from '../types';
import { CHART_HEIGHT, CHART_WIDTH, chartGeometry, formatChartTick } from './chartGeometry';

export function CustomChart({ element }: { element: ChartElement }) {
  if (!element.series.some((series) => series.values.length)) return null;
  const { series, ticks, yMin, yMax, left, top, plotWidth, plotHeight, slot, scaleX, scaleY } =
    chartGeometry(element);
  const baseline = scaleY(0);
  const barWidth = Math.max(1, (slot * 0.8) / series.length);
  const axisBottom = top + plotHeight;

  return (
    <figure className="workflow-step-custom__figure">
      <svg
        className="workflow-step-custom__chart"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label={
          element.caption
          ?? `${element.variant} chart of ${series.map((entry) => entry.label).join(', ')}`
        }
      >
        <path
          className="workflow-step-custom__chart-axis"
          d={`M${left} ${top}V${axisBottom}H${left + plotWidth}`}
        />
        {[yMax, yMin].map((value, index) => (
          <text
            key={index}
            className="workflow-step-custom__chart-tick"
            x={left - 6}
            y={index === 0 ? top + 4 : axisBottom + 3}
            textAnchor="end"
          >
            {formatChartTick(value)}
          </text>
        ))}
        {ticks.map((tick, index) => (
          <text
            key={index}
            className="workflow-step-custom__chart-tick"
            x={scaleX(tick.x)}
            y={axisBottom + 14}
            textAnchor={index === 0 ? 'start' : index === ticks.length - 1 ? 'end' : 'middle'}
          >
            {tick.label}
          </text>
        ))}
        {element.x_label && (
          <text
            className="workflow-step-custom__chart-axis-label"
            x={left + plotWidth / 2}
            y={CHART_HEIGHT - 6}
            textAnchor="middle"
          >
            {element.x_label}
          </text>
        )}
        {element.y_label && (
          <text
            className="workflow-step-custom__chart-axis-label"
            transform={`translate(12 ${top + plotHeight / 2}) rotate(-90)`}
            textAnchor="middle"
          >
            {element.y_label}
          </text>
        )}
        {series.map((entry, entryIndex) => {
          if (element.variant === 'bar') {
            const offset = (entryIndex - (series.length - 1) / 2) * barWidth - barWidth / 2;
            return (
              <path
                key={entry.label}
                fill={entry.color}
                d={entry.points
                  .map((point) => {
                    const y = scaleY(point.value);
                    const height = Math.max(1, Math.abs(baseline - y));
                    return `M${scaleX(point.x) + offset} ${Math.min(y, baseline)}h${barWidth}v${height}h${-barWidth}z`;
                  })
                  .join('')}
              />
            );
          }
          if (element.variant === 'scatter') {
            return (
              <g key={entry.label} fill={entry.color}>
                {entry.points.map((point, pointIndex) => (
                  <circle key={pointIndex} cx={scaleX(point.x)} cy={scaleY(point.value)} r={2.5} />
                ))}
              </g>
            );
          }
          return (
            <polyline
              key={entry.label}
              fill="none"
              stroke={entry.color}
              strokeWidth={1.5}
              points={[...entry.points]
                .sort((first, second) => first.x - second.x)
                .map((point) => `${scaleX(point.x)},${scaleY(point.value)}`)
                .join(' ')}
            />
          );
        })}
      </svg>
      {series.length > 1 && (
        <ul className="workflow-step-custom__chart-legend">
          {series.map((entry) => (
            <li key={entry.label}>
              <span style={{ background: entry.color }} />
              {entry.label}
            </li>
          ))}
        </ul>
      )}
      {element.caption && <figcaption>{element.caption}</figcaption>}
    </figure>
  );
}
