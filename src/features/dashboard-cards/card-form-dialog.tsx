import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  autoCardTitle,
  CARD_AGGREGATIONS,
  CARD_COLORS,
  CARD_VIEWS,
  CUSTOM_CARD_KINDS,
  type CardAggregation,
  type CardFields,
  type CardTemplate,
  type CardView,
  type ColorToken,
  type CustomCardKind,
} from "./types";

interface CardFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templates: readonly CardTemplate[];
  submitting?: boolean;
  error?: string | null;
  onSubmit: (input: CardFields) => void;
  onAskAssistant: (input: CardFields) => void;
}

const DEFAULT_WINDOW_DAYS = 30;

function clampDays(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return DEFAULT_WINDOW_DAYS;
  return Math.min(365, Math.max(1, parsed));
}

export function CardFormDialog({
  open,
  onOpenChange,
  templates,
  submitting = false,
  error,
  onSubmit,
  onAskAssistant,
}: CardFormDialogProps) {
  const { t } = useTranslation();
  const [kind, setKind] = useState<CustomCardKind>("spo2");
  const [aggregation, setAggregation] =
    useState<CardAggregation>("latest");
  const [view, setView] = useState<CardView>("stat");
  const [windowDays, setWindowDays] = useState(String(DEFAULT_WINDOW_DAYS));
  const [unit, setUnit] = useState("");
  const [colorToken, setColorToken] = useState<ColorToken>("signal");
  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind("spo2");
    setAggregation("latest");
    setView("stat");
    setWindowDays(String(DEFAULT_WINDOW_DAYS));
    setUnit("");
    setColorToken("signal");
    setTitle("");
    setTitleTouched(false);
  }, [open]);

  const autoTitle = autoCardTitle(kind, aggregation, t);
  const kindTemplates = templates.filter((template) => template.kind === kind);

  const buildFields = (): CardFields => ({
    title: (titleTouched ? title.trim() : "") || autoTitle,
    kind,
    aggregation,
    windowDays: clampDays(windowDays),
    view,
    unit: unit.trim() || null,
    colorToken,
  });

  const applyTemplate = (template: CardTemplate) => {
    setKind(template.kind);
    setAggregation(template.aggregation);
    setView(template.view);
    setWindowDays(String(template.windowDays));
    setUnit(template.unit ?? "");
    setColorToken(template.colorToken);
    setTitle(
      t(`dashboard.customCards.templates.${template.id}`, {
        defaultValue: template.title,
      }),
    );
    setTitleTouched(true);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("dashboard.customCards.formTitle")}</DialogTitle>
          <DialogDescription>
            {t("dashboard.customCards.formDescription")}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {kindTemplates.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {kindTemplates.map((template) => (
                <Button
                  key={template.id}
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 rounded-full px-3 text-xs font-normal"
                  onClick={() => applyTemplate(template)}
                >
                  {t(`dashboard.customCards.templates.${template.id}`, {
                    defaultValue: template.title,
                  })}
                </Button>
              ))}
            </div>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="custom-card-kind">
                {t("dashboard.customCards.fields.kind")}
              </Label>
              <Select
                value={kind}
                onValueChange={(value) => {
                  const next = value as CustomCardKind;
                  setKind(next);
                  if (!titleTouched) setTitle("");
                }}
              >
                <SelectTrigger id="custom-card-kind" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CUSTOM_CARD_KINDS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`dashboard.customCards.kinds.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="custom-card-aggregation">
                {t("dashboard.customCards.fields.aggregation")}
              </Label>
              <Select
                value={aggregation}
                onValueChange={(value) =>
                  setAggregation(value as CardAggregation)
                }
              >
                <SelectTrigger id="custom-card-aggregation" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CARD_AGGREGATIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`dashboard.customCards.aggregations.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="custom-card-view">
                {t("dashboard.customCards.fields.view")}
              </Label>
              <Select
                value={view}
                onValueChange={(value) => setView(value as CardView)}
              >
                <SelectTrigger id="custom-card-view" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CARD_VIEWS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`dashboard.customCards.views.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="custom-card-window">
                {t("dashboard.customCards.fields.windowDays")}
              </Label>
              <Input
                id="custom-card-window"
                type="number"
                min={1}
                max={365}
                value={windowDays}
                onChange={(event) => setWindowDays(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="custom-card-title">
                {t("dashboard.customCards.fields.title")}
              </Label>
              <Input
                id="custom-card-title"
                value={title}
                placeholder={autoTitle}
                onChange={(event) => {
                  setTitle(event.target.value);
                  setTitleTouched(true);
                }}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="custom-card-unit">
                {t("dashboard.customCards.fields.unit")}
              </Label>
              <Input
                id="custom-card-unit"
                value={unit}
                placeholder={t("dashboard.customCards.unitPlaceholder")}
                onChange={(event) => setUnit(event.target.value)}
              />
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="custom-card-color">
                {t("dashboard.customCards.fields.color")}
              </Label>
              <Select
                value={colorToken}
                onValueChange={(value) =>
                  setColorToken(value as ColorToken)
                }
              >
                <SelectTrigger id="custom-card-color" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CARD_COLORS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {t(`dashboard.customCards.colors.${item}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <p className="eh-caption text-muted-foreground">
            {t("dashboard.customCards.aiHint")}
          </p>
          {error ? (
            <p className="eh-caption text-destructive" role="alert">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
          >
            {t("dashboard.customCards.cancel")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => onAskAssistant(buildFields())}
          >
            <Sparkles data-icon="inline-start" />
            {t("dashboard.customCards.askAssistant")}
          </Button>
          <Button
            type="button"
            onClick={() => onSubmit(buildFields())}
            disabled={submitting}
          >
            {t("dashboard.customCards.save")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
