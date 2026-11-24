import { useMemo, useState, type FocusEvent, type KeyboardEvent } from "react";
import { ChevronDown, Search } from "lucide-react";
import * as countries from "i18n-iso-countries";
import ruLocale from "i18n-iso-countries/langs/ru.json";
import enLocale from "i18n-iso-countries/langs/en.json";

countries.registerLocale(ruLocale);
countries.registerLocale(enLocale);

type Country = { code: string; name: string; englishName: string };

const countryOptions: Country[] = Object.keys(countries.getAlpha2Codes())
  .map((code) => ({
    code,
    name: countries.getName(code, "ru") || countries.getName(code, "en") || code,
    englishName: countries.getName(code, "en") || code,
  }))
  .sort((left, right) => left.name.localeCompare(right.name, "ru"));

function normalize(value: string) {
  return value.trim().toLocaleLowerCase("ru").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

type CountrySelectProps = {
  value: string;
  onChange: (code: string) => void;
};

export default function CountrySelect({ value, onChange }: CountrySelectProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const selected = countryOptions.find((country) => country.code === value);

  const filtered = useMemo(() => {
    const search = normalize(query);
    if (!search) return countryOptions;
    return countryOptions.filter((country) =>
      normalize(`${country.name} ${country.englishName} ${country.code}`).includes(search),
    );
  }, [query]);

  const choose = (country: Country) => {
    onChange(country.code);
    setQuery("");
    setOpen(false);
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpen(false);
      setQuery("");
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.min(current + 1, Math.max(filtered.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter" && open && filtered[activeIndex]) {
      event.preventDefault();
      choose(filtered[activeIndex]);
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  };

  return (
    <div className="country-picker" onBlur={handleBlur}>
      <div className="country-input-wrap">
        <Search size={15} aria-hidden="true" />
        <input
          aria-label="Страна · ISO-2"
          aria-autocomplete="list"
          aria-controls="country-options"
          aria-expanded={open}
          autoComplete="off"
          placeholder="Поиск страны или ISO-кода"
          role="combobox"
          value={open ? query : selected ? `${selected.name} · ${selected.code}` : ""}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
            setOpen(true);
          }}
          onFocus={() => {
            setQuery("");
            setActiveIndex(0);
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
        <ChevronDown size={15} aria-hidden="true" />
      </div>
      {open && (
        <div className="country-menu">
          {filtered.length ? (
            <ul id="country-options" role="listbox" aria-label="Страны">
              {filtered.map((country, index) => (
                <li key={country.code} role="presentation">
                  <button
                    aria-selected={country.code === value}
                    className={index === activeIndex ? "active" : ""}
                    role="option"
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(country)}
                  >
                    <span>{country.name}</span>
                    <code>{country.code}</code>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="country-empty" role="status">Страна не найдена</div>
          )}
        </div>
      )}
    </div>
  );
}

export function CountryMultiSelect({ value, onChange }: { value: string[]; onChange: (codes: string[]) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selected = countryOptions.filter((country) => value.includes(country.code));
  const filtered = useMemo(() => {
    const search = normalize(query);
    if (!search) return countryOptions;
    return countryOptions.filter((country) =>
      normalize(`${country.name} ${country.englishName} ${country.code}`).includes(search),
    );
  }, [query]);

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpen(false);
      setQuery("");
    }
  };

  const toggle = (code: string) => {
    onChange(value.includes(code) ? value.filter((item) => item !== code) : [...value, code]);
  };
  const summary = selected.length <= 2
    ? selected.map((country) => `${country.name} · ${country.code}`).join(", ")
    : `Выбрано стран: ${selected.length} (${selected.map((country) => country.code).join(", ")})`;

  return (
    <div className={`country-picker ${open ? "is-open" : ""}`} onBlur={handleBlur}>
      <div className="country-input-wrap">
        <Search size={15} aria-hidden="true" />
        <input
          aria-label="Поиск стран или ISO-кода"
          aria-autocomplete="list"
          aria-controls="country-options"
          aria-expanded={open}
          autoComplete="off"
          placeholder={open ? "Поиск страны или ISO-кода" : summary ? "" : "Выберите страны"}
          role="combobox"
          value={open ? query : summary}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => { setQuery(""); setOpen(true); }}
          onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); setQuery(""); } }}
        />
        <ChevronDown size={15} aria-hidden="true" />
      </div>
      {open && (
        <div className="country-menu country-multi-menu">
          {filtered.length ? (
            <ul id="country-options" aria-label="Страны">
              {filtered.map((country) => (
                <li key={country.code}>
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={value.includes(country.code)}
                    className="country-checkbox-option"
                    onClick={() => toggle(country.code)}
                  >
                    <span className={`country-checkbox-square ${value.includes(country.code) ? "checked" : ""}`} aria-hidden="true" />
                    <span>{country.name}</span>
                    <code>{country.code}</code>
                  </button>
                </li>
              ))}
            </ul>
          ) : <div className="country-empty" role="status">Страна не найдена</div>}
          <div className="country-multi-footer">
            <span>{selected.length ? `Выбрано: ${selected.length}` : "Выберите одну или несколько стран"}</span>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => { setOpen(false); setQuery(""); }}>Готово</button>
          </div>
        </div>
      )}
    </div>
  );
}
