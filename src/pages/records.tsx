import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FilePlus2, FileSearch, GitCompare, RefreshCw } from "lucide-react";
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
import { useImport } from "@/components/import/import-provider";
import { useRecords } from "@/lib/api/queries";
import { useTagLabel } from "@/lib/tags";

type TimeFilter = "all" | "7d" | "30d";
type DeviceFilter = "all" | "apple" | "samsung" | "huawei";

const PAGE_SIZE = 20;

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
  const { openPicker } = useImport();
  const navigate = useNavigate();
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [deviceFilter, setDeviceFilter] = useState<DeviceFilter>("all");
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const capturedFrom = useMemo(() => {
    if (timeFilter === "7d") return new Date(Date.now() - 7 * 86_400_000).toISOString();
    if (timeFilter === "30d") return new Date(Date.now() - 30 * 86_400_000).toISOString();
    return undefined;
  }, [timeFilter]);

  const query = useRecords({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    capturedFrom,
    recordType: "org.eclipsehealth.ecg",
  });

  const records = query.data?.items ?? [];
  const total = query.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    if (page > 0 && page >= pageCount) setPage(pageCount - 1);
  }, [page, pageCount]);

  const tags = useMemo(
    () => [...new Set(records.flatMap((record) => record.tags))],
    [records],
  );

  const filtered = useMemo(
    () =>
      records.filter((record) => {
        if (deviceFilter !== "all" && record.device.vendor !== deviceFilter) {
          return false;
        }
        if (tagFilter && !record.tags.includes(tagFilter)) return false;
        return true;
      }),
    [records, deviceFilter, tagFilter],
  );

  const hasFilters =
    timeFilter !== "all" || deviceFilter !== "all" || tagFilter !== null;
  const clearFilters = () => {
    setTimeFilter("all");
    setDeviceFilter("all");
    setTagFilter(null);
    setPage(0);
  };

  const toggleSelection = (id: string) => {
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 2) return current;
      return [...current, id];
    });
  };

  const compareSelected = () => {
    if (selectedIds.length !== 2) return;
    navigate(`/compare?ids=${selectedIds.join(",")}`);
  };

  return (
    <>
      <PageHeader
        eyebrow={t("records.eyebrow")}
        title={t("records.title")}
        description={t("records.description")}
        actions={
          <Button size="sm" onClick={openPicker}>
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
                onValueChange={(value) => {
                  setTimeFilter(value as TimeFilter);
                  setPage(0);
                }}
              >
                <SelectTrigger
                  size="sm"
                  className="min-w-[128px]"
                  aria-label={t("records.filters.time")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("records.filters.allTime")}</SelectItem>
                  <SelectItem value="7d">{t("records.filters.last7")}</SelectItem>
                  <SelectItem value="30d">{t("records.filters.last30")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1">
              <span className="eh-caption text-muted-foreground">
                {t("records.filters.device")}
              </span>
              <Select
                value={deviceFilter}
                onValueChange={(value) => setDeviceFilter(value as DeviceFilter)}
              >
                <SelectTrigger
                  size="sm"
                  className="min-w-[148px]"
                  aria-label={t("records.filters.device")}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t("records.filters.allDevices")}</SelectItem>
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
              {t("records.count", {
                shown: filtered.length,
                total: query.data ? total : "—",
              })}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-2">
            <span className="eh-caption text-muted-foreground">
              {selectedIds.length > 0
                ? t("records.selected", { count: selectedIds.length })
                : t("records.compareHint")}
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              {selectedIds.length > 0 ? (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => setSelectedIds([])}
                >
                  {t("records.clearSelection")}
                </Button>
              ) : null}
              <Button
                size="xs"
                onClick={compareSelected}
                disabled={selectedIds.length !== 2}
              >
                <GitCompare data-icon="inline-start" />
                {t("records.compare")}
              </Button>
            </div>
          </div>

          {query.isLoading ? <RecordListSkeleton rows={4} /> : null}

          {query.isError ? (
            <div className="px-5 py-8">
              <EmptyState
                icon={RefreshCw}
                title={t("common.loadError")}
                description={t("records.errorDesc")}
                className="border-0 bg-transparent py-6"
              >
                <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
                  <RefreshCw data-icon="inline-start" />
                  {t("common.retry")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {!query.isLoading && !query.isError && total === 0 ? (
            <div className="px-5 py-6">
              <EmptyState
                icon={FilePlus2}
                title={t("records.emptyTitle")}
                description={t("records.emptyDesc")}
                className="border-0 bg-transparent"
              >
                <Button size="sm" onClick={openPicker}>
                  {t("records.emptyAction")}
                </Button>
              </EmptyState>
            </div>
          ) : null}

          {!query.isLoading &&
          !query.isError &&
          total > 0 &&
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
                <RecordRow
                  key={record.id}
                  record={record}
                  selection={{
                    selected: selectedIds.includes(record.id),
                    disabled: selectedIds.length >= 2,
                    onToggle: toggleSelection,
                  }}
                />
              ))}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-5 py-2">
            <div className="flex items-center gap-2">
              {hasFilters ? (
                <Button variant="ghost" size="xs" onClick={clearFilters}>
                  {t("records.clearFilters")}
                </Button>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="xs"
                onClick={() => setPage((current) => Math.max(0, current - 1))}
                disabled={page === 0 || query.isFetching}
              >
                {t("records.previous")}
              </Button>
              <span className="eh-caption text-muted-foreground">
                {t("records.page", { page: page + 1, pages: pageCount })}
              </span>
              <Button
                variant="outline"
                size="xs"
                onClick={() =>
                  setPage((current) => Math.min(pageCount - 1, current + 1))
                }
                disabled={page + 1 >= pageCount || query.isFetching}
              >
                {t("records.next")}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
