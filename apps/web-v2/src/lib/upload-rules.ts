export const acceptedFileTypes = ".txt,.md,.pdf";
export const maxUploadBytes = 8 * 1024 * 1024;

export function uploadError(file: Pick<File, "name" | "size">): string | null {
  if (file.size > maxUploadBytes) return "文件大小不能超过 8 MiB。";
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!acceptedFileTypes.split(",").includes(extension)) return "不支持此文件格式，请选择 TXT、Markdown 或 PDF。";
  return null;
}
