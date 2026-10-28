import { useTranslation } from "react-i18next";

/** 记录标签是用户数据；已知标签走翻译，未知标签原样显示。 */
export function useTagLabel() {
  const { t } = useTranslation();
  return (tag: string) => t(`records.tagLabels.${tag}`, { defaultValue: tag });
}
