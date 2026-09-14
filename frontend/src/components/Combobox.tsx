import { useEffect, useRef, useState } from "react";

export interface ComboboxOption {
  value: string;
  label: string;
}

/** A searchable single-select: typing filters the option list, but the
 * value committed on selection is always one of the supplied `options` —
 * never arbitrary free text. Branches are a foreign key (CLAUDE.md §4: a
 * staff member's `branch_id` "must reference a branch belonging to the
 * admin's own company"), so this stays a constrained picker; it only adds
 * typing/searching on top of the plain `<select>` it replaces, for admins
 * with more than a handful of branches to scroll through. */
export function Combobox({
  options,
  value,
  onChange,
  placeholder,
  disabled,
  id,
}: {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
}) {
  const selected = options.find((o) => o.value === value);
  const [query, setQuery] = useState(selected?.label ?? "");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  // Keep the displayed text in sync when the selection changes from outside
  // (e.g. form reset) without fighting the user's own typing while open.
  useEffect(() => {
    if (!open) setQuery(selected?.label ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.value]);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery(selected?.label ?? "");
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open, selected?.label]);

  const filtered = query.trim()
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  function commit(option: ComboboxOption) {
    onChange(option.value);
    setQuery(option.label);
    setOpen(false);
  }

  return (
    <div className="relative" ref={rootRef}>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlight(0);
          if (e.target.value === "" && value !== "") onChange("");
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setHighlight((h) => Math.min(h + 1, filtered.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlight((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const option = filtered[highlight];
            if (option) commit(option);
          } else if (e.key === "Escape") {
            setOpen(false);
            setQuery(selected?.label ?? "");
          }
        }}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm transition-colors placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-indigo-400"
      />
      {open && !disabled ? (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-slate-400 dark:text-slate-500">No matches</li>
          ) : (
            filtered.map((option, i) => (
              <li key={option.value}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    commit(option);
                  }}
                  onMouseEnter={() => setHighlight(i)}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    i === highlight
                      ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                      : "text-slate-700 dark:text-slate-200"
                  }`}
                >
                  {option.label}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
