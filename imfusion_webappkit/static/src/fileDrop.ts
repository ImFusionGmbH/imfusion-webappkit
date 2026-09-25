interface DroppedFileItem extends DataTransferItem {
  getAsFileSystemHandle?: () => Promise<FileSystemHandle | null>;
}

interface DroppedDirectoryHandle extends FileSystemDirectoryHandle {
  entries(): AsyncIterableIterator<[string, FileSystemHandle]>;
}

async function collectDroppedHandle(
  handle: FileSystemHandle,
  files: File[],
  relativePath = '',
): Promise<void> {
  if (handle.kind === 'file') {
    const file = await (handle as FileSystemFileHandle).getFile();
    files.push(
      relativePath
        ? new File([file], `${relativePath}${file.name}`, {
            type: file.type,
            lastModified: file.lastModified,
          })
        : file,
    );
    return;
  }
  const directory = handle as DroppedDirectoryHandle;
  for await (const [name, child] of directory.entries()) {
    await collectDroppedHandle(
      child,
      files,
      child.kind === 'directory' ? `${relativePath}${name}/` : relativePath,
    );
  }
}

export async function droppedFiles(dataTransfer: DataTransfer): Promise<File[]> {
  try {
    const items = Array.from(dataTransfer.items) as DroppedFileItem[];
    const handles = items.map((item) => item.getAsFileSystemHandle?.());
    if (handles.some(Boolean)) {
      const files: File[] = [];
      for (const pending of handles) {
        const handle = await pending;
        if (handle) await collectDroppedHandle(handle, files);
      }
      return files;
    }
  } catch (error) {
    console.warn('Could not traverse dropped folders; using the file list instead', error);
  }
  return Array.from(dataTransfer.files);
}
