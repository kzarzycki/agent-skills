import type { ReactNode } from "react";

export default function FileTree({ tree, children }: { tree?: string; children?: ReactNode }) {
  return <pre className="filetree">{tree ?? children}</pre>;
}
