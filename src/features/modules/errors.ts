import type { TFunction } from "i18next";
import { ApiError } from "@/lib/api/error";

const ERROR_KEYS: Record<string, string> = {
  INVALID_PACKAGE: "moduleUi.errors.invalidPackage",
  INVALID_INPUT: "moduleUi.errors.invalidInput",
  INCOMPATIBLE_API: "moduleUi.errors.incompatible",
  CHECKSUM_MISMATCH: "moduleUi.errors.checksum",
  UNSAFE_PACKAGE_PATH: "moduleUi.errors.unsafePath",
  MODULE_ALREADY_INSTALLED: "moduleUi.errors.alreadyInstalled",
  MODULE_NOT_FOUND: "moduleUi.errors.notFound",
  MODULE_DISABLED: "moduleUi.errors.disabled",
  MODULE_CRASH: "moduleUi.errors.crashed",
  MODULE_TIMEOUT: "moduleUi.errors.timeout",
  PERMISSION_DENIED: "moduleUi.errors.permissionDenied",
  RESOURCE_EXCEEDED: "moduleUi.errors.tooLarge",
  network_error: "moduleUi.errors.network",
  timeout: "moduleUi.errors.timeout",
};

export function moduleErrorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const key = ERROR_KEYS[error.code];
    if (key) return t(key);
    return error.message || t("moduleUi.errors.unknown");
  }
  return t("moduleUi.errors.unknown");
}
