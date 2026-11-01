import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { moduleStateLabel } from "./format";
import type { ModuleState } from "./types";

const VARIANTS: Record<
  ModuleState,
  "default" | "secondary" | "outline" | "destructive"
> = {
  installed: "outline",
  enabled: "secondary",
  running: "default",
  stopped: "outline",
  disabled: "outline",
  crashed: "destructive",
};

export function ModuleStateBadge({ state }: { state: ModuleState }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant={VARIANTS[state] ?? "outline"}
      className="font-normal"
      data-state={state}
    >
      {moduleStateLabel(t, state)}
    </Badge>
  );
}
