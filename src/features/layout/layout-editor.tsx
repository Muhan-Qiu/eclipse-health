import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowDown,
  ArrowUp,
  Download,
  Eye,
  EyeOff,
  GripVertical,
  RotateCcw,
  Save,
  Upload,
  X,
} from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import {
  LAYOUT_WIDTHS,
  layoutWidthClass,
  type LayoutItem,
  type LayoutWidth,
} from "./layout";

interface LayoutGridProps {
  items: readonly LayoutItem[];
  editing: boolean;
  onChange: (items: LayoutItem[]) => void;
  renderItem: (item: LayoutItem) => ReactNode;
  titleFor: (item: LayoutItem) => string;
  className?: string;
}

/**
 * 仪表盘栅格。非编辑模式只按保存顺序与宽度渲染；
 * 编辑模式给每张卡片加可见性 / 宽度 / 上移下移 / 拖拽手柄。
 */
export function LayoutGrid({
  items,
  editing,
  onChange,
  renderItem,
  titleFor,
  className,
}: LayoutGridProps) {
  const { t } = useTranslation();
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const update = (id: string, patch: Partial<LayoutItem>) => {
    onChange(items.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const move = (id: string, delta: number) => {
    const from = items.findIndex((item) => item.id === id);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= items.length) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  };

  const moveTo = (sourceId: string, targetId: string) => {
    const from = items.findIndex((item) => item.id === sourceId);
    const to = items.findIndex((item) => item.id === targetId);
    if (from < 0 || to < 0 || from === to) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(from < to ? to - 1 : to, 0, moved);
    onChange(next);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>, targetId: string) => {
    event.preventDefault();
    const sourceId = event.dataTransfer.getData("text/plain") || draggingId;
    if (sourceId) moveTo(sourceId, targetId);
    setDraggingId(null);
    setOverId(null);
  };

  if (!editing) {
    return (
      <div className={cn("eh-grid", className)}>
        {items
          .filter((item) => !item.hidden)
          .map((item) => (
            <div
              key={item.id}
              data-layout-id={item.id}
              data-layout-kind={item.kind}
              className={cn("eh-layout-cell", layoutWidthClass(item.width))}
            >
              {renderItem(item)}
            </div>
          ))}
      </div>
    );
  }

  return (
    <div className={cn("eh-grid", className)}>
      {items.map((item, index) => {
        const dragging = draggingId === item.id;
        const over = overId === item.id && draggingId !== null && !dragging;
        return (
          <div
            key={item.id}
            data-layout-id={item.id}
            data-layout-kind={item.kind}
            data-layout-hidden={item.hidden ? "true" : "false"}
            className={cn(
              // 用 outline 标注编辑区域，不加内边距，卡片宽度与浏览模式保持一致。
              "eh-layout-cell gap-2 rounded-2xl outline-1 -outline-offset-1 outline-dashed motion-safe:transition-[background-color,outline-color,opacity]",
              layoutWidthClass(item.width),
              dragging
                ? "bg-accent-soft/40 opacity-60 outline-accent/70"
                : "bg-subtle/30 outline-border",
              over && "bg-accent-soft/60 outline-accent",
            )}
            onDragOver={(event) => {
              if (!draggingId) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              if (overId !== item.id) setOverId(item.id);
            }}
            onDragLeave={() => {
              if (overId === item.id) setOverId(null);
            }}
            onDrop={(event) => onDrop(event, item.id)}
          >
            <div className="mb-2 shrink-0 space-y-1 px-1">
              <div className="flex min-w-0 items-center gap-1">
                <span
                  draggable
                  title={t("dashboard.layout.dragHandle")}
                  aria-hidden="true"
                  className="inline-flex size-6 shrink-0 cursor-grab items-center justify-center rounded-md text-muted-foreground hover:bg-muted active:cursor-grabbing"
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", item.id);
                    setDraggingId(item.id);
                  }}
                  onDragEnd={() => {
                    setDraggingId(null);
                    setOverId(null);
                  }}
                >
                  <GripVertical className="size-3.5" />
                </span>
                <span className="eh-caption min-w-0 flex-1 truncate">
                  {titleFor(item)}
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-1">
                <div
                  className="flex items-center gap-0.5"
                  role="group"
                  aria-label={t("dashboard.layout.width")}
                >
                  {LAYOUT_WIDTHS.map((width, widthIndex) => (
                    <WidthButton
                      key={width}
                      width={width}
                      columns={widthIndex + 1}
                      active={item.width === width}
                      onSelect={() => update(item.id, { width })}
                    />
                  ))}
                </div>

                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={
                    item.hidden
                      ? t("dashboard.layout.show")
                      : t("dashboard.layout.hide")
                  }
                  aria-pressed={item.hidden}
                  onClick={() => update(item.id, { hidden: !item.hidden })}
                >
                  {item.hidden ? <EyeOff /> : <Eye />}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={t("dashboard.layout.moveUp")}
                  disabled={index === 0}
                  onClick={() => move(item.id, -1)}
                >
                  <ArrowUp />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={t("dashboard.layout.moveDown")}
                  disabled={index === items.length - 1}
                  onClick={() => move(item.id, 1)}
                >
                  <ArrowDown />
                </Button>
              </div>
            </div>

            {item.hidden ? (
              <div className="flex min-h-24 flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-surface/60 px-4 py-4">
                <p className="eh-caption text-muted-foreground">
                  {t("dashboard.layout.hidden")}
                </p>
              </div>
            ) : (
              renderItem(item)
            )}
          </div>
        );
      })}
    </div>
  );
}

function WidthButton({
  width,
  columns,
  active,
  onSelect,
}: {
  width: LayoutWidth;
  columns: number;
  active: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Button
      type="button"
      size="icon-xs"
      variant={active ? "secondary" : "ghost"}
      className="eh-num text-[0.7rem]"
      aria-label={t("dashboard.layout.widthOption", { columns })}
      aria-pressed={active}
      data-layout-width={width}
      onClick={onSelect}
    >
      {columns}
    </Button>
  );
}

interface LayoutToolbarProps {
  onSave: () => void;
  onCancel: () => void;
  onReset: () => void;
  onExport: () => void;
  onImport: (file: File) => void;
  error: string | null;
}

export function LayoutToolbar({
  onSave,
  onCancel,
  onReset,
  onExport,
  onImport,
  error,
}: LayoutToolbarProps) {
  const { t } = useTranslation();
  const fileInput = useRef<HTMLInputElement>(null);

  return (
    <div className="mt-4 rounded-xl border border-border bg-subtle/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="eh-caption min-w-0 flex-1 text-muted-foreground">
          {t("dashboard.layout.editHint")}
        </p>
        <Button type="button" size="sm" onClick={onSave}>
          <Save data-icon="inline-start" />
          {t("dashboard.layout.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          <X data-icon="inline-start" />
          {t("dashboard.layout.cancel")}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onReset}>
          <RotateCcw data-icon="inline-start" />
          {t("dashboard.layout.reset")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onExport}>
          <Download data-icon="inline-start" />
          {t("dashboard.layout.export")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => fileInput.current?.click()}
        >
          <Upload data-icon="inline-start" />
          {t("dashboard.layout.import")}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          className="sr-only"
          aria-label={t("dashboard.layout.import")}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onImport(file);
            // 允许连续导入同一个文件
            event.target.value = "";
          }}
        />
      </div>
      {error ? (
        <p className="eh-caption mt-2 text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
