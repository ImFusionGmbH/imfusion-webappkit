/**
 * Actions a recorded demo recomputes in the browser instead of replaying.
 *
 * Recording fixes an action to the parameter values chosen while building, which
 * turns a slider into a short list. An action whose arithmetic the WebAssembly
 * SDK can do just as well does not need that compromise: it runs here, against
 * the same imaging library the viewer is already using, and answers with the
 * same messages the server would have sent. What a static host lacks is Python,
 * not the imaging library, so the result is genuine.
 *
 * A handler is opted into per action from the demo specification, and its name
 * is validated against `AVAILABLE_HANDLERS` in
 * `imfusion_webappkit/static_demo/spec.py` while building.
 */

import type { Data, ImFusion, SharedImageSet } from '@imfusion/sdk';
import { resultDataName } from '../protocol';

export interface HandlerRequest {
  action: string;
  inputs?: Array<{ role: string; index: number }>;
  indices?: number[];
  parameters?: Record<string, unknown>;
}

export interface HandlerResult {
  /** Where the result lands in the data model, which the client appends to. */
  index: number;
  name: string;
  payload: Uint8Array;
}

/** `BasicImageProcessing` mode that labels voxels inside an intensity interval. */
const THRESHOLD_MODE = 4;

export type DemoHandler = (imf: ImFusion, request: HandlerRequest) => HandlerResult;

function requestedIndex(request: HandlerRequest): number {
  if (request.inputs?.length) return Number(request.inputs[0].index) || 0;
  if (request.indices?.length) return Number(request.indices[0]) || 0;
  return 0;
}

function imageSetAt(imf: ImFusion, index: number): SharedImageSet | null {
  const candidate: Data | undefined = Array.from(imf.dataModel)[index];
  // Embind hands back the concrete type, so an image set answers to `get`.
  return candidate && typeof (candidate as SharedImageSet).get === 'function'
    ? candidate as SharedImageSet
    : imf.dataModel.getImage();
}

/**
 * Label every voxel at or above a threshold.
 *
 * The Python version compares physical intensities (`image.numpy()`, with the
 * shift and scale applied) and builds a fresh `uint8` label map on the source
 * grid. The JavaScript bindings can neither copy an image nor set its matrix,
 * so the mask comes from `Base.BasicImageProcessing`, whose threshold mode
 * compares original values and creates a new image that keeps the geometry but
 * not the source's shift and scale.
 */
function runThreshold(imf: ImFusion, request: HandlerRequest): HandlerResult {
  const threshold = Number(request.parameters?.threshold);
  if (!Number.isFinite(threshold)) {
    throw new Error('This action needs a threshold value');
  }

  const source = imageSetAt(imf, requestedIndex(request));
  if (!source) throw new Error('The dataset this action needs is no longer loaded');

  const algorithms = imf.compatibleAlgorithms([source]);
  const candidates = Array.from(algorithms);
  algorithms.delete();
  const algorithm = candidates.find(
    (candidate) => candidate.id() === 'Base.BasicImageProcessing',
  );

  let payload: Uint8Array;
  let outputs: Data[] = [];
  try {
    if (!algorithm) {
      throw new Error('Thresholding is not available in this build of the viewer');
    }
    algorithm.setState({
      ...algorithm.state(),
      mode: THRESHOLD_MODE,
      lowerThreshold: threshold,
      upperThreshold: Math.max(threshold, source.minmaxIntensityOriginal()[1]),
      insideInterval: true,
      createNew: true,
    });
    outputs = Array.from(algorithm.execute());
    const labelMap = imf.bindings.getImage(outputs);
    if (algorithm.status() !== 'Success' || !labelMap) {
      throw new Error('Thresholding the selected dataset failed');
    }
    labelMap.setModality('LABEL');
    payload = imf.bindings.save([labelMap]);
  } finally {
    // `execute` adds its output to the data model; the client appends the
    // payload itself, so the intermediate copy must not stay behind.
    for (const output of outputs) imf.dataModel.remove(output);
    for (const candidate of candidates) candidate.delete();
  }

  return {
    index: Array.from(imf.dataModel).length,
    name: resultDataName(source.name, request.action),
    payload,
  };
}

export const demoHandlers: Record<string, DemoHandler> = {
  threshold: runThreshold,
};
