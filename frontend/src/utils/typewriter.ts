export function createTypingFrames(text: string): string[] {
  const characters = Array.from(text);
  return characters.map((_, index) => characters.slice(0, index + 1).join(""));
}
