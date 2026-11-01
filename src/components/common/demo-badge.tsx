import { FlaskConical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { cn } from "cn";

/**
 * 所有合成/演示数据都必须带这个标记，避免与真实记录混淆。
 */
export function DemoBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 border-dashed font-normal text-muted-foreground",
        className,
      )}
      aria-label={t("a11y.demoData")}
    >
      <FlaskConical aria-hidden="true" />
      {t("common.demo")}
    </Badge>
  );
}
