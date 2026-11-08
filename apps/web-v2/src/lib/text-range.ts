/** Slice Unicode code points without allocating an array for the entire file. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) return "";
  let point = 0;
  let from = -1;
  let offset = 0;
  for (const character of text) {
    if (point === start) from = offset;
    if (point === end) return from < 0 ? "" : text.slice(from, offset);
    offset += character.length;
    point++;
  }
  return from < 0 ? "" : text.slice(from);
}
