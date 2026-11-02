import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { assistantApi } from "@/features/assistant/api";
import { useMock } from "@/lib/api/client";

/**
 * 首启引导：没有可用 LLM provider 时提示配置。只调用只读的
 * provider 列表接口；后端不可用或 mock 模式都不打扰用户。
 *
 * 不提供「不再提示」：没有模型服务商时助手、AI 导入、评分建议与教练都不可用，
 * 因此每次启动都会提醒；「稍后」只隐藏本次会话。
 */
export function LlmKeyPrompt() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [hidden, setHidden] = useState(false);
  const [open, setOpen] = useState(false);

  const query = useQuery({
    queryKey: ["assistant", "providers", "onboarding"],
    queryFn: () => assistantApi.providers.list(),
    enabled: !useMock,
    staleTime: 5 * 60_000,
    retry: false,
  });

  useEffect(() => {
    if (useMock || hidden || !query.isSuccess) return;
    const configured = query.data.some(
      (provider) =>
        provider.enabled && (provider.configured || provider.isLocal),
    );
    if (configured) return;
    // 等首屏渲染完成再淡入，避免盖住启动动画的收尾。
    const timer = window.setTimeout(() => setOpen(true), 800);
    return () => window.clearTimeout(timer);
  }, [hidden, query.data, query.isSuccess]);

  const hideForNow = () => {
    setHidden(true);
    setOpen(false);
  };

  const goConfigure = () => {
    setOpen(false);
    navigate("/assistant?focus=provider");
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : hideForNow())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div
            className="mb-1 flex size-9 items-center justify-center rounded-lg bg-accent-soft text-primary"
            aria-hidden="true"
          >
            <KeyRound className="size-4" />
          </div>
          <DialogTitle>{t("onboarding.llm.title")}</DialogTitle>
          <DialogDescription>{t("onboarding.llm.description")}</DialogDescription>
        </DialogHeader>
        <p className="eh-caption text-muted-foreground">
          {t("onboarding.llm.note")}
        </p>
        <DialogFooter className="-mx-4 -mb-4 border-t bg-muted/40 px-4 py-3">
          <Button variant="outline" size="sm" onClick={hideForNow}>
            {t("onboarding.llm.later")}
          </Button>
          <Button size="sm" onClick={goConfigure}>
            {t("onboarding.llm.configure")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
