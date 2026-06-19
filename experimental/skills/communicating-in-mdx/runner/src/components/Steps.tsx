import type { ReactNode } from "react";

export default function Steps({ children }: { children?: ReactNode }) {
  return <ol className="steps">{children}</ol>;
}

export { Steps as Timeline };
