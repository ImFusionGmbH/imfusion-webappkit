export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunkSize = 8192;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

interface Aliasable {
  isAliasOf?(other: object): boolean;
}

export function areAliases<T extends object>(first: T, second: T): boolean {
  const firstHandle = first as Aliasable;
  const secondHandle = second as Aliasable;
  return first === second || Boolean(firstHandle.isAliasOf?.(second) || secondHandle.isAliasOf?.(first));
}

export function selectedDataIndices<T extends object>(allData: T[], selectedData: T[]): number[] {
  return selectedData
    .map((item) => allData.findIndex((candidate) => areAliases(candidate, item)))
    .filter((index) => index >= 0);
}

export function reconcileDataOrder<T extends object>(preferred: T[], actual: T[]): T[] {
  const ordered = preferred.filter(
    (item, index) =>
      preferred.findIndex((candidate) => areAliases(candidate, item)) === index
      && actual.some((candidate) => areAliases(candidate, item)),
  );
  const additions = actual.filter(
    (item) => !ordered.some((candidate) => areAliases(candidate, item)),
  );
  return [...ordered, ...additions];
}

export function resultDataName(sourceName: string, operationName: string): string {
  const shortName = operationName.split('.').at(-1)?.replaceAll('_', ' ') ?? operationName;
  const readableOperation = shortName.replace(/([a-z0-9])([A-Z])/g, '$1 $2');
  return `${sourceName || 'Data'} — ${readableOperation}`;
}
