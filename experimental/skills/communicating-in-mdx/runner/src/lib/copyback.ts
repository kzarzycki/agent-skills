export function serializeAnswers(answers: Record<string, string>): string {
  return `ANSWERS<<<\n${JSON.stringify(answers, null, 2)}\n>>>ANSWERS`;
}
