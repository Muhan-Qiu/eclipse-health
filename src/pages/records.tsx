import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { FilePlus2, FileSearch } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/common/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { RecordListSkeleton } from "@/components/common/loading";
import { RecordRow } from "@/components/records/record-row";
import { api } from "@/lib/api/client";
import { useTagLabel } from "@/lib/tags";

type TimeFilter = "all" | "7d" | "30d";
type DeviceFilter = "all" | "apple" | "samsung" | "huawei";

function filterChipClass(active: boolean) {
  return cn(
    "h-7 rounded-full border px-3 text-xs transition-colors",
    active
      ? "border-primary bg-accent-soft font-medium text-foreground"
      : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

export function RecordsPage() {
  const { t } = useTranslation();
  const tagLabel = useTagLabel();
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [deviceFilter, setDeviceFilter] = useState<DeviceFilter>("all");
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["records"],
    queryFn: () => api.records.list({ limit: 50 }),
  });

  const records = useMemo(() => data ?? [], [data]);

  const tags = useMemo(
    () => [...new Set(records.flatMap((record) => record.tags))],
    [records],
  );

  const filtered = useMemo(() => {
    const now = Date.now();
    const windowMs =
      timeFilter === "7d" ? 7 * 86_400_000 : timeFilter === "30d" ? 30 * 86_400_000 : null;

    return records.filter((record) => {
      if (deviceFilter !== "all" && record.device.vendor !== deviceFilter) {
        return false;
      }
      if (tagFilter && !record.tags.includes(tagFilter)) return false;
      if (windowMs !== null) {
        const recorded = new Date(record.recordedAt).getTime();
        if (Number.isNaN(recorded) || now - recorded > windowMs) return false;
      }
      return true;
    });
  }, [records, timeFilter, deviceFilter, tagFilter]);

  const hasFilters =
    timeFilter !== "all" || deviceFilter !== "all" || tagFilter !== null;
  const clearFilters = () => {
    setTimeFilter("all");
    setDeviceFilter("all");
    setTagFilter(null);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("records.eyebrow")}
        title={t("records.title")}
        description={t("records.description")}
        actions={
          <Button
            size="sm"
            onClick={() => toast(t("dashboard.guide.importPending"))}
          >
            <FilePlus2 data-icon="inline-start" />
            {t("records.emptyAction")}
          </Button>
        }
      />

      <Card>
        <CardContent className="px-0">
          <div className="flex flex-wrap items-end gap-3 border-b border-border px-5 py-3">
            <div className="flex flex-col gap-1">
              <span className="eh-caption text-muted-foreground">
                {t("records.filters.time")}
              </span>
              <Select
                value={timeFilter}
                onValueChange={(value) => setTimeFilter(value as TimeFilter)}
              >
                <SelectTrigger
                  size="sm"
                  className="min-w-[128px]"
                  aria-label={t("records.filters.time")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">
                    {t("records.filters.allTime")}
                  </SelectItem>
                  <SelectItem value="7d">
                    {t("records.filters.last7")}
                  </SelectItem>
                  <SelectItem value="30d">
                    {t("records.filters.last30")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1">
              <span className="eh-caption text-muted-foreground">
                {t("records.filters.device")}
              </span>
              <Select
                value={deviceFilter}
                onValueChange={(value) =>
                  setDeviceFilter(value as DeviceFilter)
                }
              >
                <SelectTrigger
                  size="sm"
                  className="min-w-[148px]"
                  aria-label={t("records.filters.device")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">
                    {t("records.filters.allDevices")}
                  </SelectItem>
                  <SelectItem value="apple">Apple</SelectItem>
                  <SelectItem value="samsung">Samsung</SelectItem>
                  <SelectItem value="huawei">Huawei</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div
              className="flex flex-wrap items-center gap-1.5"
              role="group"
              aria-label={t("a11y.tagFilter")}
            >
              <span className="eh-caption mr-1 text-muted-foreground">
                {t("records.filters.tag")}
              </span>
              <button
                type="button"
                aria-pressed={tagFilter === null}
                className={filterChipClass(tagFilter === null)}
                onClick={() => setTagFilter(null)}
              >
                {t("records.filters.allTags")}
              </button>
              {tags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  aria-pressed={tagFilter === tag}
                  className={filterChipClass(tagFilter === tag)}
                  onClick={() => setTagFilter(tag)}
                >
                  {tagLabel(tag)}
                </button>
              ))}
            </div>

            <span className="eh-caption ml-auto text-muted-foreground">
              {filtered.length} / {records.length}
            </span>
          </div>

          {isLoading ? <RecordListSkeleton rows={3} /> : null}

          {isError ? (
            <p className="eh-small px-5 py-8 text-center text-muted-foreground">
              {t("common.loadError")}
            </p>
          ) : null}

          {!isLoading && !isError && records.length === 0 ? (
            <div className="px-5 py-6">
              <EmptyState
                icon={FilePlus2}
                title={t("records.emptyTitle")}
                description={t("records.emptyDesc")}
                className="border-0 bg-transparent"
              >
                <Button
                  size="sm"
                  onClick={() => toast(t("dashboard.guide.importPending"))}
                >
                  {t("records.emptyAction")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {!isLoading &&
          !isError &&
          records.length > 0 &&
          filtered.length === 0 ? (
            <div className="px-5 py-6">
              <EmptyState
                icon={FileSearch}
                title={t("records.noMatchTitle")}
                description={t("records.noMatchDesc")}
                className="border-0 bg-transparent"
              >
                <Button variant="outline" size="sm" onClick={clearFilters}>
                  {t("records.clearFilters")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {filtered.length > 0 ? (
            <div className="divide-y divide-border">
              {filtered.map((record) => (
                <RecordRow key={record.id} record={record} />
              ))}
            </div>
          ) : null}

          {hasFilters && filtered.length > 0 ? (
            <div className="flex justify-end border-t border-border px-5 py-2">
              <Button variant="ghost" size="xs" onClick={clearFilters}>
                {t("records.clearFilters")}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </>
  );
}
