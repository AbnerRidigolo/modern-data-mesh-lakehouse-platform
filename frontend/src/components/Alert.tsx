import type { ReactNode } from "react";

interface AlertProps {
  kind: "info" | "success" | "warning" | "error";
  children: ReactNode;
}

export default function Alert({ kind, children }: AlertProps) {
  return <div className={`alert ${kind}`}>{children}</div>;
}
