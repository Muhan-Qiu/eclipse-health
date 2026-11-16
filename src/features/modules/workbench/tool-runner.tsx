import { useMemo, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Copy, Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { callModuleRpc } from "../api";
import { moduleErrorMessage } from "../errors";
import type { ModuleContributionMeta } from "../types";

/**
 * 后端 `/modules/contributions?type=tools` 实际会带上 inputSchema，
 * 但共享类型 `ModuleContributionMeta` 只描述公共字段，这里在工作台内补充。
 */
export interface ModuleToolContribution extends ModuleContributionMeta {
  id: string;
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
}

type FieldType =
  | "string"
  | "number"
  | "integer"
  | "boolean"
  | "enum"
  | "array"
  | "object";

interface ToolField {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  defaultValue?: unknown;
  options: string[];
}

type FieldValue = string | boolean;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fieldType(prop: Record<string, unknown>): FieldType {
  if (Array.isArray(prop.enum)) return "enum";
  if (prop.type === "number") return "number";
  if (prop.type === "integer") return "integer";
  if (prop.type === "boolean") return "boolean";
  if (prop.type === "array") return "array";
  if (prop.type === "object") return "object";
  return "string";
}

function toolFields(schema: Record<string, unknown> | undefined): ToolField[] {
  const props = isRecord(schema?.properties) ? schema.properties : {};
  const required = Array.isArray(schema?.required)
    ? new Set(
        schema.required.filter(
          (item): item is string => typeof item === "string",
        ),
      )
    : new Set<string>();

  return Object.entries(props).map(([key, raw]) => {
    const prop = isRecord(raw) ? raw : {};
    return {
      key,
      label:
        typeof prop.title === "string" && prop.title.length > 0
          ? prop.title
          : key,
      type: fieldType(prop),
      required: required.has(key),
      defaultValue: prop.default,
      options: Array.isArray(prop.enum)
        ? prop.enum.map((option) => String(option))
        : [],
    };
  });
}

function initialValues(fields: ToolField[]): Record<string, FieldValue> {
  const values: Record<string, FieldValue> = {};
  for (const field of fields) {
    if (field.type === "boolean") {
      values[field.key] = field.defaultValue === true;
    } else if (field.defaultValue !== undefined) {
      values[field.key] =
        typeof field.defaultValue === "object"
          ? JSON.stringify(field.defaultValue, null, 2)
          : String(field.defaultValue);
    } else {
      values[field.key] = "";
    }
  }
  return values;
}

export function normalizeToolContribution(
  value: unknown,
  meta: ModuleContributionMeta,
): ModuleToolContribution | null {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id) {
    return null;
  }
  const inputSchema = isRecord(value.inputSchema)
    ? value.inputSchema
    : isRecord(value.parameters)
      ? value.parameters
      : undefined;
  return {
    ...meta,
    id: value.id,
    name: typeof value.name === "string" && value.name ? value.name : value.id,
    description:
      typeof value.description === "string" ? value.description : undefined,
    inputSchema,
    parameters: isRecord(value.parameters) ? value.parameters : undefined,
  };
}

function FieldControl({
  id,
  field,
  value,
  onChange,
}: {
  id: string;
  field: ToolField;
  value: FieldValue;
  onChange: (value: FieldValue) => void;
}) {
  const { t } = useTranslation();
  const text = typeof value === "string" ? value : "";

  if (field.type === "boolean") {
    return (
      <Switch
        id={id}
        checked={value === true}
        onCheckedChange={(checked) => onChange(checked)}
      />
    );
  }

  if (field.type === "enum") {
    return (
      <Select value={text} onValueChange={(next) => onChange(next)}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={t("moduleWorkbench.selectPlaceholder")} />
        </SelectTrigger>
        <SelectContent>
          {field.options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  if (field.type === "array" || field.type === "object") {
    return (
      <Textarea
        id={id}
        value={text}
        placeholder={t("moduleWorkbench.jsonPlaceholder")}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  if (field.type === "number" || field.type === "integer") {
    return (
      <Input
        id={id}
        type="number"
        step={field.type === "integer" ? 1 : "any"}
        value={text}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  return (
    <Input
      id={id}
      value={text}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

interface ToolRunnerProps {
  moduleId: string;
  tool: ModuleToolContribution;
  disabled?: boolean;
  disabledReason?: string;
}

/**
 * 通用工具试运行：只根据 inputSchema 生成受控表单，不硬编码任何模块字段。
 */
export function ToolRunner({
  moduleId,
  tool,
  disabled = false,
  disabledReason,
}: ToolRunnerProps) {
  const { t } = useTranslation();
  const fields = useMemo(
    () => toolFields(tool.inputSchema ?? tool.parameters),
    [tool.inputSchema, tool.parameters],
  );
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, FieldValue>>(() =>
    initialValues(fields),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function setValue(key: string, value: FieldValue) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    const params: Record<string, unknown> = {};

    for (const field of fields) {
      const raw = values[field.key];
      if (field.type === "boolean") {
        params[field.key] = raw === true;
        continue;
      }

      const text = typeof raw === "string" ? raw.trim() : "";
      if (!text) {
        if (field.required) {
          nextErrors[field.key] = t("moduleWorkbench.requiredField", {
            field: field.label,
          });
        }
        continue;
      }

      if (field.type === "number" || field.type === "integer") {
        const numeric = Number(text);
        if (!Number.isFinite(numeric)) {
          nextErrors[field.key] = t("moduleWorkbench.invalidNumber", {
            field: field.label,
          });
          continue;
        }
        params[field.key] =
          field.type === "integer" ? Math.trunc(numeric) : numeric;
        continue;
      }

      if (field.type === "array" || field.type === "object") {
        try {
          params[field.key] = JSON.parse(text);
        } catch {
          nextErrors[field.key] = t("moduleWorkbench.invalidJson", {
            field: field.label,
          });
        }
        continue;
      }

      params[field.key] = text;
    }

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setPending(true);
    setError(null);
    try {
      const data = await callModuleRpc(moduleId, tool.id, params);
      setResult(JSON.stringify(data, null, 2) ?? String(data));
    } catch (cause) {
      setResult(null);
      setError(moduleErrorMessage(cause, t));
    } finally {
      setPending(false);
    }
  }

  async function copyResult() {
    if (result === null) return;
    try {
      await navigator.clipboard.writeText(result);
      toast.success(t("moduleWorkbench.copied"));
    } catch {
      toast.error(t("moduleWorkbench.copyFailed"));
    }
  }

  return (
    <li className="px-4 py-3.5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{tool.name}</span>
            <code className="eh-caption rounded bg-subtle px-1.5 py-0.5 text-muted-foreground">
              {tool.id}
            </code>
          </div>
          {tool.description ? (
            <p className="eh-caption mt-1 text-muted-foreground">
              {tool.description}
            </p>
          ) : null}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => setOpen((value) => !value)}
        >
          <Play aria-hidden="true" />
          {t("moduleWorkbench.run")}
        </Button>
      </div>

      {disabled && disabledReason ? (
        <p className="eh-caption mt-2 text-muted-foreground">{disabledReason}</p>
      ) : null}

      {open && !disabled ? (
        <form
          className="mt-3 space-y-3 rounded-lg border border-border bg-muted/20 p-3"
          onSubmit={submit}
        >
          {fields.length === 0 ? (
            <p className="eh-small text-muted-foreground">
              {t("moduleWorkbench.noParams")}
            </p>
          ) : (
            <div className="space-y-3">
              {fields.map((field) => {
                const inputId = `tool-${tool.id}-${field.key}`;
                return (
                  <div key={field.key} className="space-y-1.5">
                    <Label htmlFor={inputId}>
                      {field.label}
                      {field.required ? (
                        <span className="text-destructive" aria-hidden="true">
                          *
                        </span>
                      ) : null}
                    </Label>
                    <FieldControl
                      id={inputId}
                      field={field}
                      value={values[field.key] ?? ""}
                      onChange={(value) => setValue(field.key, value)}
                    />
                    {errors[field.key] ? (
                      <p className="eh-caption text-destructive">
                        {errors[field.key]}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}

          <Button type="submit" size="sm" disabled={pending}>
            {pending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Play aria-hidden="true" />
            )}
            {pending
              ? t("moduleWorkbench.running")
              : t("moduleWorkbench.run")}
          </Button>

          {error ? (
            <Alert variant="destructive">
              <AlertCircle aria-hidden="true" />
              <AlertTitle>{t("moduleWorkbench.runFailed")}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {result !== null ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="eh-caption text-muted-foreground">
                  {t("moduleWorkbench.result")}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => void copyResult()}
                >
                  <Copy aria-hidden="true" />
                  {t("moduleWorkbench.copy")}
                </Button>
              </div>
              <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-background p-3 text-xs whitespace-pre-wrap">
                {result}
              </pre>
            </div>
          ) : null}
        </form>
      ) : null}
    </li>
  );
}
