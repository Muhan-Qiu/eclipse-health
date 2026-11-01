import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { CustomCard } from "./custom-card";
import type { CardDraft, DashboardCard } from "./types";

interface CardDraftCardProps {
  draft: CardDraft;
  confirming?: boolean;
  discarding?: boolean;
  onConfirm: () => void;
  onDiscard: () => void;
}

/** 助手草稿：用同一套卡片渲染，但不写入布局，用户点「添加」才保存。 */
export function CardDraftCard({
  draft,
  confirming = false,
  discarding = false,
  onConfirm,
  onDiscard,
}: CardDraftCardProps) {
  const { t } = useTranslation();
  const card: DashboardCard = {
    ...draft.card,
    id: draft.id,
    memberId: draft.memberId,
    createdBy: draft.createdBy,
    createdAt: draft.createdAt,
    updatedAt: draft.updatedAt,
    data: draft.preview,
  };

  return (
    <CustomCard
      card={card}
      data={draft.preview}
      draft
      actions={
        <>
          <Button
            type="button"
            size="sm"
            onClick={onConfirm}
            disabled={confirming || discarding}
          >
            {t("dashboard.customCards.addDraft")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={onDiscard}
            disabled={confirming || discarding}
          >
            {t("dashboard.customCards.discardDraft")}
          </Button>
        </>
      }
    />
  );
}
