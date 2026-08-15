import { Languages } from "lucide-react";
import { useLanguage } from "../i18n/LanguageContext";
import { languageLabels, type Language } from "../i18n/translations";

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage } = useLanguage();

  return (
    <label className="language-switcher" title="Language / භාෂාව / மொழி">
      <Languages size={14} />
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value as Language)}
        aria-label="Language"
        className={compact ? "language-switcher-select compact" : "language-switcher-select"}
      >
        {(Object.keys(languageLabels) as Language[]).map((code) => (
          <option key={code} value={code}>
            {languageLabels[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
