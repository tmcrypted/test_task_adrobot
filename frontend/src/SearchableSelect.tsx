import { useId, useMemo, useState, type FocusEvent } from "react";
import { ChevronDown, Search } from "lucide-react";

type SearchableOption = { id: number; name: string };

type SearchableSelectProps = {
  label: string;
  options: SearchableOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
};

export default function SearchableSelect({ label, options, value, onChange, placeholder = "Поиск по имени или ID" }: SearchableSelectProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const listId = useId();
  const selected = options.find((item) => String(item.id) === value);
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    return options.filter((item) => !needle || `${item.id} ${item.name}`.toLocaleLowerCase("ru").includes(needle));
  }, [options, query]);

  const closeOnBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpen(false);
      setQuery("");
    }
  };

  return (
    <div className="catalog-picker" onBlur={closeOnBlur}>
      <div className="catalog-picker-control">
        <Search size={15} aria-hidden="true" />
        <input
          aria-label={`Поиск: ${label}`}
          aria-autocomplete="list"
          aria-controls={listId}
          aria-expanded={open}
          autoComplete="off"
          placeholder={open || !selected ? placeholder : ""}
          role="combobox"
          value={open ? query : selected ? `#${selected.id} · ${selected.name}` : ""}
          onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
          onFocus={() => { setQuery(""); setOpen(true); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") { setOpen(false); setQuery(""); }
            if (event.key === "Enter" && open && filtered.length) {
              event.preventDefault();
              onChange(String(filtered[0].id));
              setOpen(false);
              setQuery("");
            }
          }}
        />
        <ChevronDown size={15} aria-hidden="true" />
      </div>
      {open && (
        <div className="catalog-picker-menu">
          {filtered.length ? (
            <ul id={listId} role="listbox" aria-label={label}>
              {filtered.map((item) => (
                <li key={item.id} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={String(item.id) === value}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => { onChange(String(item.id)); setOpen(false); setQuery(""); }}
                  >
                    <span>#{item.id} · {item.name}</span>
                    {String(item.id) === value && <span className="catalog-selected-mark">Выбрано</span>}
                  </button>
                </li>
              ))}
            </ul>
          ) : <div className="country-empty" role="status">Ничего не найдено</div>}
        </div>
      )}
    </div>
  );
}
