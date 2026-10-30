import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { intlLocale } from "@/lib/i18n";
import { moduleErrorMessage } from "../errors";
import {
  callModuleRpc,
  pageRpcQueryKey,
  type PageBlock,
  type PageFormField,
} from "./page-api";
import { valuesFromRecord } from "./page-value";

type FormValue = string | boolean;
type FormValues = Record<string, FormValue>;

interface PageFormProps {
  moduleId: string;
  block: PageBlock;
}

function defaultValue(field: PageFormField): FormValue {
  if (field.type === "checkbox") {
    return typeof field.default === "boolean" ? field.default : false;
  }
  if (field.default === undefined) return "";
  return String(field.default);
}

function initialValues(fields: PageFormField[]): FormValues {
  const values: FormValues = {};
  for (const field of fields) values[field.key] = defaultValue(field);
  return values;
}

function inputId(key: string, index: number): string {
  return `module-page-field-${index}-${key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

export function PageForm({ moduleId, block }: PageFormProps) {
  const { t, i18n } = useTranslation();
  const locale = intlLocale(i18n.language);
  const queryClient = useQueryClient();
  const fields = block.fields;
  const source = block.source;
  const submitMethod = block.submitMethod;

  const [values, setValues] = useState<FormValues>(() => initialValues(fields));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dirty, setDirty] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const seeded = useRef<unknown>(null);

  const sourceQuery = useQuery({
    queryKey: pageRpcQueryKey(moduleId, source),
    queryFn: () => {
      if (!source) throw new Error("missing source");
      return callModuleRpc(moduleId, source.method, source.params ?? {});
    },
    enabled: Boolean(source),
    staleTime: 15_000,
  });

  useEffect(() => {
    const data = sourceQuery.data;
    if (data === undefined || dirty || seeded.current === data) return;
    seeded.current = data;
    setValues({
      ...initialValues(fields),
      ...valuesFromRecord(data, fields),
    });
  }, [sourceQuery.data, dirty, fields]);

  function updateValue(key: string, value: FormValue) {
    setDirty(true);
    setSubmitError(null);
    setErrors((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
    setValues((current) => ({ ...current, [key]: value }));
  }

  function validate(): boolean {
    const next: Record<string, string> = {};
    for (const field of fields) {
      const value = values[field.key];
      if (field.required) {
        const empty =
          typeof value === "boolean"
            ? !value
            : String(value ?? "").trim() === "";
        if (empty) next[field.key] = "modulePage.required";
      }
      if (
        field.type === "number" &&
        typeof value === "string" &&
        value.trim() !== "" &&
        Number.isNaN(Number(value))
      ) {
        next[field.key] = "modulePage.invalidNumber";
      }
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function buildParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {};
    for (const field of fields) {
      const value = values[field.key];
      if (typeof value === "boolean") {
        params[field.key] = value;
      } else if (field.type === "number") {
        params[field.key] = value.trim() === "" ? null : Number(value);
      } else {
        params[field.key] = value;
      }
    }
    return params;
  }

  const submit = useMutation({
    mutationFn: (params: Record<string, unknown>) => {
      if (!submitMethod) throw new Error("missing submit method");
      return callModuleRpc(moduleId, submitMethod, params);
    },
    onSuccess: () => {
      toast.success(t("modulePage.submitSuccess"));
      setDirty(false);
      void queryClient.invalidateQueries({
        queryKey: ["modules", "page-rpc", moduleId],
      });
    },
    onError: (error) => {
      setSubmitError(moduleErrorMessage(error, t));
    },
  });

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!submitMethod || !validate()) return;
    submit.mutate(buildParams());
  }

  const loading = sourceQuery.isPending && Boolean(source);
  const sourceError = sourceQuery.isError;

  return (
    <form
      className="space-y-4"
      onSubmit={onSubmit}
      aria-busy={submit.isPending || loading}
    >
      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-3/4" />
        </div>
      ) : null}

      {sourceError ? (
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("modulePage.rpcError")}</AlertTitle>
          <AlertDescription>
            {moduleErrorMessage(sourceQuery.error, t)}
          </AlertDescription>
        </Alert>
      ) : null}

      {submitError ? (
        <Alert variant="destructive">
          <AlertCircle aria-hidden="true" />
          <AlertTitle>{t("modulePage.submitFailed")}</AlertTitle>
          <AlertDescription>{submitError}</AlertDescription>
        </Alert>
      ) : null}

      {fields.map((field, index) => {
        const id = inputId(field.key, index);
        const value = values[field.key] ?? "";
        const messageKey = errors[field.key];
        const invalid = Boolean(messageKey);
        return (
          <div key={field.key} className="space-y-1.5">
            {field.type === "checkbox" ? (
              <label
                htmlFor={id}
                className="flex items-center gap-2 text-sm leading-none font-medium select-none"
              >
                <input
                  id={id}
                  type="checkbox"
                  checked={value === true}
                  onChange={(event) =>
                    updateValue(field.key, event.target.checked)
                  }
                  className="size-4 rounded border border-input accent-primary"
                />
                <span>{field.label}</span>
                {field.required ? (
                  <span className="text-destructive" aria-hidden="true">
                    *
                  </span>
                ) : null}
              </label>
            ) : (
              <>
                <Label htmlFor={id}>
                  {field.label}
                  {field.required ? (
                    <span className="text-destructive" aria-hidden="true">
                      *
                    </span>
                  ) : null}
                </Label>
                {field.type === "textarea" ? (
                  <Textarea
                    id={id}
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) =>
                      updateValue(field.key, event.target.value)
                    }
                    aria-invalid={invalid}
                  />
                ) : field.type === "select" ? (
                  <Select
                    value={typeof value === "string" ? value : ""}
                    onValueChange={(next) => updateValue(field.key, next)}
                  >
                    <SelectTrigger
                      id={id}
                      className="w-full"
                      aria-invalid={invalid}
                    >
                      <SelectValue
                        placeholder={t("modulePage.selectPlaceholder")}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {field.options.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    id={id}
                    type={
                      field.type === "number"
                        ? "number"
                        : field.type === "date"
                          ? "date"
                          : "text"
                    }
                    step={field.type === "number" ? "any" : undefined}
                    value={typeof value === "string" ? value : ""}
                    onChange={(event) =>
                      updateValue(field.key, event.target.value)
                    }
                    aria-invalid={invalid}
                  />
                )}
              </>
            )}
            {messageKey ? (
              <p className="eh-caption text-destructive">{t(messageKey)}</p>
            ) : null}
          </div>
        );
      })}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="submit"
          disabled={!submitMethod || submit.isPending || loading}
        >
          {submit.isPending
            ? t("modulePage.submitting")
            : t("modulePage.submit")}
        </Button>
        {!submitMethod ? (
          <span className="eh-caption text-muted-foreground">
            {t("modulePage.noSubmitMethod")}
          </span>
        ) : null}
        <span className="sr-only" lang={locale}>
          {submit.isPending ? t("modulePage.submitting") : ""}
        </span>
      </div>
    </form>
  );
}
