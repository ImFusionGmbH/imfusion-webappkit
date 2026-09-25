import type { ChartElement } from '../types';

const CHART_COLORS = [
  'var(--color-primary)',
  'var(--color-info)',
  'var(--color-success)',
  'var(--color-warning)',
  'var(--color-danger)',
  'var(--color-secondary)',
];
export const CHART_WIDTH = 320;
export const CHART_HEIGHT = 180;

export function formatChartTick(value: number) {
  const magnitude = Math.abs(value);
  if (magnitude >= 10000 || (magnitude > 0 && magnitude < 0.01)) return value.toExponential(1);
  return String(Math.round(value * 100) / 100);
}

function chartExtent(numbers: number[]): [number, number] {
  return numbers.reduce<[number, number]>(
    (range, value) => [Math.min(range[0], value), Math.max(range[1], value)],
    [Infinity, -Infinity],
  );
}

/**
 * Resolve a chart into plot coordinates. String positions become evenly spaced
 * categories, numeric positions keep their spacing, and a series without
 * positions falls back to the index of each value.
 */
export function chartGeometry(element: ChartElement) {
  const positionsOf = (series: ChartElement['series'][number]) =>
    series.x ?? series.values.map((_value, index) => index);
  const categorical = element.series.some((series) =>
    series.x?.some((position) => typeof position === 'string'),
  );
  const categories: string[] = [];
  if (categorical) {
    element.series.forEach((series) => {
      positionsOf(series).forEach((position) => {
        const label = String(position);
        if (!categories.includes(label)) categories.push(label);
      });
    });
  }
  const series = element.series.map((entry, index) => {
    const positions = positionsOf(entry);
    return {
      label: entry.label,
      color: CHART_COLORS[index % CHART_COLORS.length],
      points: entry.values.map((value, pointIndex) => ({
        x: categorical
          ? categories.indexOf(String(positions[pointIndex]))
          : Number(positions[pointIndex]),
        value,
      })),
    };
  });

  const bars = element.variant === 'bar';
  const points = series.flatMap((entry) => entry.points);
  const [dataXMin, dataXMax] = chartExtent(points.map((point) => point.x));
  // Bar width follows the closest pair of positions, so histogram bins spaced
  // in data units stay as wide as evenly spaced categories.
  const distinct = [...new Set(points.map((point) => point.x))].sort(
    (first, second) => first - second,
  );
  const gap = distinct
    .slice(1)
    .reduce(
      (smallest, position, index) => Math.min(smallest, position - distinct[index]),
      Infinity,
    );
  const spacing = Number.isFinite(gap) ? gap : 1;
  let [xMin, xMax] = [dataXMin, dataXMax];
  let [yMin, yMax] = chartExtent(points.map((point) => point.value));
  if (bars) {
    // Bars are centered on their position and measured from zero.
    xMin -= spacing / 2;
    xMax += spacing / 2;
    yMin = Math.min(0, yMin);
    yMax = Math.max(0, yMax);
  }
  if (xMax === xMin) [xMin, xMax] = [xMin - 0.5, xMax + 0.5];
  if (yMax === yMin) [yMin, yMax] = [yMin - 0.5, yMax + 0.5];

  const left = element.y_label ? 52 : 40;
  const bottom = element.x_label ? 42 : 26;
  const top = 10;
  const plotWidth = CHART_WIDTH - left - 10;
  const plotHeight = CHART_HEIGHT - top - bottom;
  const manyCategories = categories.length > 4;
  const ticks = categorical
    ? categories
        .map((label, index) => ({ x: index, label }))
        .filter((_tick, index) => !manyCategories || index === 0 || index === categories.length - 1)
    : [dataXMin, dataXMax].map((x) => ({ x, label: formatChartTick(x) }));

  return {
    series,
    ticks,
    yMin,
    yMax,
    left,
    top,
    plotWidth,
    plotHeight,
    slot: (spacing * plotWidth) / (xMax - xMin),
    scaleX: (x: number) => left + ((x - xMin) / (xMax - xMin)) * plotWidth,
    scaleY: (y: number) => top + plotHeight - ((y - yMin) / (yMax - yMin)) * plotHeight,
  };
}
