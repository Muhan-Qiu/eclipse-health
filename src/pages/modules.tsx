import { ModulesWorkspace } from "@/features/modules/modules-workspace";
import { ModuleInstallWatcher } from "@/features/modules/marketplace/install-watcher";

export function ModulesPage() {
  return (
    <>
      <ModuleInstallWatcher />
      <ModulesWorkspace />
    </>
  );
}
