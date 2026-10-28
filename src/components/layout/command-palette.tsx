import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Info, Monitor, Moon, Palette, Sun } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { allNav } from "@/lib/nav";
import { PALETTES, useAppTheme, type ThemeMode } from "@/lib/theme";

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const THEME_OPTIONS: {
  mode: ThemeMode;
  icon: typeof Sun;
  keywords: string;
}[] = [
  { mode: "light", icon: Sun, keywords: "light" },
  { mode: "dark", icon: Moon, keywords: "dark" },
  { mode: "system", icon: Monitor, keywords: "system auto" },
];

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { mode, setMode, palette, setPalette } = useAppTheme();

  const run = (action: () => void) => {
    action();
    onOpenChange(false);
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("command.title")}
      description={t("command.description")}
      className="top-[12%] sm:max-w-[560px]"
    >
      <CommandInput placeholder={t("command.placeholder")} />
      <CommandList className="max-h-[min(480px,60vh)]">
        <CommandEmpty>{t("command.noResults")}</CommandEmpty>

        <CommandGroup heading={t("command.groups.navigation")}>
          {allNav.map((item) => {
            const Icon = item.icon;
            const label = t(item.labelKey);
            return (
              <CommandItem
                key={item.path}
                value={`${label} ${item.path}`}
                onSelect={() => run(() => navigate(item.path))}
              >
                <Icon aria-hidden="true" />
                <span>{label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t("command.groups.appearance")}>
          {THEME_OPTIONS.map(({ mode: option, icon: Icon, keywords }) => {
            const label = t(`themeMode.${option}`);
            return (
              <CommandItem
                key={option}
                value={`${label} ${keywords}`}
                data-checked={mode === option}
                onSelect={() => run(() => setMode(option))}
              >
                <Icon aria-hidden="true" />
                <span>{label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t("command.groups.palette")}>
          {PALETTES.map((id) => {
            const label = t(`palette.${id}.name`);
            return (
              <CommandItem
                key={id}
                value={`${label} ${t(`palette.${id}.description`)} palette ${id}`}
                data-checked={palette === id}
                onSelect={() => run(() => setPalette(id))}
              >
                <Palette aria-hidden="true" />
                <span>{label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t("command.groups.help")}>
          <CommandItem
            value={`${t("nav.about")} about`}
            onSelect={() => run(() => navigate("/about"))}
          >
            <Info aria-hidden="true" />
            <span>{t("nav.about")}</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
