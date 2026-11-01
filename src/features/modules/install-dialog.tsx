import { useTranslation } from "react-i18next";
import { Package } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MarketplacePanel } from "./marketplace/marketplace-panel";
import type { MarketplaceTab } from "./marketplace/types";
import type { ModuleSummary } from "./types";

interface InstallDialogProps {
  open: boolean;
  installed: ModuleSummary[];
  initialTab?: MarketplaceTab;
  onClose: () => void;
  onInstalled: () => void;
}

/**
 * 安装入口外壳：官方市场 / 社区市场 / 本地文件三个 tab。
 * 本地安装的预览与权限确认仍在 LocalInstall 内部完成。
 */
export function InstallDialog({
  open,
  installed,
  initialTab,
  onClose,
  onInstalled,
}: InstallDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="size-4" aria-hidden="true" />
            {t("moduleUi.marketplace.title")}
          </DialogTitle>
          <DialogDescription>
            {t("moduleUi.marketplace.description")}
          </DialogDescription>
        </DialogHeader>

        <MarketplacePanel
          open={open}
          initialTab={initialTab}
          installed={installed}
          onInstalled={onInstalled}
        />
      </DialogContent>
    </Dialog>
  );
}
