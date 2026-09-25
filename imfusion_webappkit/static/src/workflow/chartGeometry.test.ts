import { describe, expect, it } from 'vitest';
import type { ChartElement } from '../types';
import { CHART_HEIGHT, CHART_WIDTH, chartGeometry, formatChartTick } from './chartGeometry';

function chart(element: Partial<ChartElement> & Pick<ChartElement, 'series'>): ChartElement {
  return { kind: 'chart', variant: 'line', ...element };
}

describe('formatChartTick', () => {
  it('rounds readable magnitudes to two decimals', () => {
    expect(formatChartTick(0)).toBe('0');
    expect(formatChartTick(1.239)).toBe('1.24');
  });

  it('switches to exponential notation outside the readable range', () => {
    expect(formatChartTick(10000)).toBe('1.0e+4');
    expect(formatChartTick(0.005)).toBe('5.0e-3');
    expect(formatChartTick(-0.001)).toBe('-1.0e-3');
  });
});

describe('chartGeometry positions', () => {
  it('falls back to value indices when a series has no positions', () => {
    const { series, ticks, scaleX, scaleY } = chartGeometry(
      chart({ series: [{ label: 'signal', values: [1, 2, 3] }] }),
    );
    expect(series[0].points.map((point) => point.x)).toEqual([0, 1, 2]);
    expect(ticks).toEqual([{ x: 0, label: '0' }, { x: 2, label: '2' }]);
    expect(scaleX(0)).toBeCloseTo(40);
    expect(scaleX(2)).toBeCloseTo(CHART_WIDTH - 10);
    expect(scaleY(3)).toBeCloseTo(10);
    expect(scaleY(1)).toBeCloseTo(154);
  });

  it('maps string positions onto categories shared by every series', () => {
    const { series, ticks } = chartGeometry(chart({
      series: [
        { label: 'a', values: [1, 2], x: ['low', 'high'] },
        { label: 'b', values: [3], x: ['high'] },
      ],
    }));
    expect(series[0].points.map((point) => point.x)).toEqual([0, 1]);
    expect(series[1].points.map((point) => point.x)).toEqual([1]);
    expect(ticks).toEqual([{ x: 0, label: 'low' }, { x: 1, label: 'high' }]);
  });

  it('labels only the outer categories once there are more than four', () => {
    const { ticks } = chartGeometry(chart({
      series: [{
        label: 'a',
        values: [1, 2, 3, 4, 5, 6],
        x: ['c1', 'c2', 'c3', 'c4', 'c5', 'c6'],
      }],
    }));
    expect(ticks).toEqual([{ x: 0, label: 'c1' }, { x: 5, label: 'c6' }]);
  });

  it('gives each series its own color, cycling through the palette', () => {
    const { series } = chartGeometry(chart({
      series: Array.from({ length: 7 }, (_, index) => ({ label: `s${index}`, values: [index] })),
    }));
    expect(new Set(series.slice(0, 6).map((entry) => entry.color)).size).toBe(6);
    expect(series[6].color).toBe(series[0].color);
  });
});

describe('chartGeometry bar charts', () => {
  it('derives bar width from the closest pair of positions', () => {
    const bins = chartGeometry(chart({
      variant: 'bar',
      series: [{ label: 'counts', values: [2, 4], x: [1, 1.5] }],
    }));
    const categories = chartGeometry(chart({
      variant: 'bar',
      series: [{ label: 'counts', values: [2, 4], x: ['left', 'right'] }],
    }));
    expect(bins.slot).toBeCloseTo(categories.slot);
  });

  it('pads the domain by half a bar and measures from zero', () => {
    const { scaleX, scaleY } = chartGeometry(chart({
      variant: 'bar',
      series: [{ label: 'counts', values: [2, 4], x: [1, 1.5] }],
    }));
    // Bars are centered on their position, so the padded domain is 0.75..1.75.
    expect(scaleX(1)).toBeCloseTo(107.5);
    expect(scaleX(1.5)).toBeCloseTo(242.5);
    // Zero stays on the axis even though no value reaches it.
    expect(scaleY(0)).toBeCloseTo(154);
  });
});

describe('chartGeometry degenerate and labelled charts', () => {
  it('keeps the scales finite for a single point', () => {
    const { scaleX, scaleY } = chartGeometry(chart({
      series: [{ label: 'one', values: [5] }],
    }));
    expect(scaleX(0)).toBeCloseTo(175);
    expect(scaleY(5)).toBeCloseTo(82);
  });

  it('reserves room for axis labels', () => {
    const plain = chartGeometry(chart({ series: [{ label: 'a', values: [1, 2] }] }));
    const labelled = chartGeometry(chart({
      series: [{ label: 'a', values: [1, 2] }],
      x_label: 'position',
      y_label: 'intensity',
    }));
    expect(plain.left).toBe(40);
    expect(labelled.left).toBe(52);
    expect(labelled.plotWidth).toBe(CHART_WIDTH - 52 - 10);
    expect(labelled.plotHeight).toBe(CHART_HEIGHT - 10 - 42);
    expect(labelled.plotHeight).toBeLessThan(plain.plotHeight);
  });
});
