import { useLocation, useSearchParams } from "react-router-dom";
import "@/features/assistant/i18n";
import { AssistantWorkspace } from "@/features/assistant/assistant-workspace";
import type { AssistantMode } from "@/features/assistant/types";

interface AssistantRouteState {
  prompt?: unknown;
}

export function AssistantPage() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const state = location.state as AssistantRouteState | null;
  const queryPrompt = searchParams.get("prompt");
  const prompt =
    queryPrompt ?? (typeof state?.prompt === "string" ? state.prompt : null);
  const mode: AssistantMode =
    searchParams.get("mode") === "coach" ? "coach" : "chat";

  return <AssistantWorkspace initialPrompt={prompt} initialMode={mode} />;
}
