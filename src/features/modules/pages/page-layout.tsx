import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { intlLocale } from "@/lib/i18n";
import { moduleErrorMessage } from "../errors";
import {
  callModuleRpc,
  pageRpcQueryKey,
  type ModuleRpcSource,
  type PageBlock,
  type PageColumn,
  type PageFormField,
} from "./page-api";
import { PageForm } from "./page-form";
import { formatPageValue, readPath } from "./page-value";

const BLOCK_SPAN: Record<string, string> = {
  text: "lg:col-span-12",
  table: "lg:col-span-12",
  list: "lg:col-span-6",
  detail: "lg:col-span-6",
  form: "lg:col-span-6",
};

interface PageLayoutProps {
  moduleId: string;
  blocks: PageBlock[];
}

export function PageLayout({ moduleId, blocks }: PageLayoutProps) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      {blocks.map((block, index) => (
        <PageBlockView
          key={`${block.component}-${index}`}
          moduleId={moduleId}
          block={block}
        />
      ))}
    </div>
  );
}

function PageBlockView({
  moduleId,
  block,
}: {
  moduleId: string;
  block: PageBlock;
}) {
  const { t } = useTranslation();
  const span = BLOCK_SPAN[block.component] ?? "lg:col-span-12";

  if (block.component === "text") {
    if (!block.text) {
      return (
        <BlockNotice
          className={span}
          title={t("modulePage.invalidBlock")}
          description={t("modulePage.invalidBlockDesc")}
        />
      );
    }
    return (
      <p
        className={cn(
          "eh-small whitespace-pre-line text-muted-foreground",
          span,
        )}
      >
        {block.text}
      </p>
    );
  }

  if (
    block.component === "list" ||
    block.component === "table" ||
    block.component === "detail"
  ) {
    if (!block.source) {
      return (
        <BlockNotice
          className={span}
          title={t("modulePage.invalidBlock")}
          description={t("modulePage.invalidBlockDesc")}
        />
      );
    }
    if (block.component === "table" && block.columns.length === 0) {
      return (
        <BlockNotice
          className={span}
          title={t("modulePage.invalidBlock")}
          description={t("modulePage.invalidBlockDesc")}
        />
      );
    }
    return (
      <DataBlock
        className={span}
        moduleId={moduleId}
        block={block}
        kind={block.component}
      />
    );
  }

  if (block.component === "form") {
    if (!block.source || block.fields.length === 0) {
      return (
        <BlockNotice
          className={span}
          title={t("modulePage.invalidBlock")}
          description={t("modulePage.invalidBlockDesc")}
        />
      );
    }
    return (
      <Card className={span}>
        <CardHeader>
          <CardTitle>{block.title ?? t("modulePage.blocks.form")}</CardTitle>
        </CardHeader>
        <CardContent>
          <PageForm moduleId={moduleId} block={block} />
        </CardContent>
      </Card>
    );
  }

  return (
    <BlockNotice
      className={span}
      title={t("modulePage.unsupportedBlock")}
      description={t("modulePage.unsupportedBlockDesc", {
        component: block.component,
      })}
    />
  );
}

function useBlockRpc(moduleId: string, source: ModuleRpcSource | undefined) {
  return useQuery({
    queryKey: pageRpcQueryKey(moduleId, source),
    queryFn: () => {
      if (!source) throw new Error("missing source");
      return callModuleRpc(moduleId, source.method, source.params ?? {});
    },
    enabled: Boolean(source),
    staleTime: 15_000,
  });
}

function DataBlock({
  className,
  moduleId,
  block,
  kind,
}: {
  className: string;
  moduleId: string;
  block: PageBlock;
  kind: "list" | "table" | "detail";
}) {
  const { t } = useTranslation();
  const query = useBlockRpc(moduleId, block.source);
  const title = block.title ?? t(`modulePage.blocks.${kind}`);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardAction>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={t("modulePage.refresh")}
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            <RefreshCw
              className={cn(query.isFetching && "animate-spin")}
              aria-hidden="true"
            />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {query.isPending ? <BlockSkeleton /> : null}
        {query.isError ? (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>{t("modulePage.rpcError")}</AlertTitle>
            <AlertDescription>
              {t("modulePage.rpcErrorDesc", {
                message: moduleErrorMessage(query.error, t),
              })}
            </AlertDescription>
          </Alert>
        ) : null}
        {query.isSuccess ? (
          <BlockBody kind={kind} block={block} data={query.data} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function BlockSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true">
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

function BlockBody({
  kind,
  block,
  data,
}: {
  kind: "list" | "table" | "detail";
  block: PageBlock;
  data: unknown;
}) {
  if (kind === "list") return <ListBody block={block} data={data} />;
  if (kind === "table") return <TableBodyBlock block={block} data={data} />;
  return <DetailBody block={block} data={data} />;
}

function rowValues(data: unknown, path?: string): unknown[] {
  const value = readPath(data, path);
  return Array.isArray(value) ? value : [];
}

function ListBody({ block, data }: { block: PageBlock; data: unknown }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const items = rowValues(data, block.itemPath);

  if (items.length === 0) {
    return (
      <p className="eh-small text-muted-foreground">
        {t("modulePage.emptyList")}
      </p>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {items.map((item, index) => {
        const primary = block.primaryPath
          ? readPath(item, block.primaryPath)
          : item;
        const secondary = block.secondaryPath
          ? readPath(item, block.secondaryPath)
          : undefined;
        return (
          <li
            key={index}
            className="flex items-baseline justify-between gap-3 py-2 first:pt-0 last:pb-0"
          >
            <span className="min-w-0 truncate text-sm">
              {formatPageValue(primary, {}, locale, t)}
            </span>
            {secondary !== undefined ? (
              <span className="eh-caption shrink-0 text-muted-foreground">
                {formatPageValue(secondary, {}, locale, t)}
              </span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function TableBodyBlock({ block, data }: { block: PageBlock; data: unknown }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const rows = rowValues(data, block.rowPath);

  if (rows.length === 0) {
    return (
      <p className="eh-small text-muted-foreground">
        {t("modulePage.emptyTable")}
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {block.columns.map((column) => (
            <TableHead key={column.key}>{column.label}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={index}>
            {block.columns.map((column) => (
              <TableCell key={column.key}>
                {formatPageValue(
                  readPath(row, column.key),
                  column,
                  locale,
                  t,
                )}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function autoFields(data: unknown): PageFormField[] {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return [];
  }
  return Object.entries(data)
    .filter(
      ([, value]) =>
        value === null ||
        typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean",
    )
    .slice(0, 64)
    .map(([key]) => ({
      key,
      label: key,
      type: "text" as const,
      required: false,
      options: [],
    }));
}

function DetailBody({ block, data }: { block: PageBlock; data: unknown }) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const fields =
    block.fields.length > 0 ? block.fields : autoFields(data);

  if (fields.length === 0) {
    return (
      <p className="eh-small whitespace-pre-line text-muted-foreground">
        {typeof data === "object" && data !== null
          ? t("modulePage.emptyDetail")
          : formatPageValue(data, {}, locale, t)}
      </p>
    );
  }

  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      {fields.map((field) => (
        <DetailField
          key={field.key}
          field={field}
          value={readPath(data, field.key)}
          locale={locale}
        />
      ))}
    </dl>
  );
}

function DetailField({
  field,
  value,
  locale,
}: {
  field: PageColumn | PageFormField;
  value: unknown;
  locale: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0">
      <dt className="eh-caption text-muted-foreground">{field.label}</dt>
      <dd className="mt-0.5 break-words text-sm">
        {formatPageValue(value, field, locale, t)}
      </dd>
    </div>
  );
}

function BlockNotice({
  className,
  title,
  description,
}: {
  className: string;
  title: string;
  description: string;
}) {
  return (
    <Card className={className}>
      <CardContent className="pt-4">
        <Alert>
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{description}</AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}
