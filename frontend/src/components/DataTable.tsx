import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Banner, Button, EmptyState, TextInput } from "./ui";
import { Icon } from "./icons";
import { TableSkeleton } from "./Skeleton";

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  /** Plain value used for sorting/searching; defaults to not sortable/searchable if omitted. */
  accessor?: (row: T) => string | number;
  /** Custom cell content; falls back to the accessor's value. */
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[] | undefined;
  getRowId: (row: T) => string | number;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  emptyMessage?: string;
  searchPlaceholder?: string;
  /** Column keys to search over (must have an accessor). Omit to hide the search box. */
  searchKeys?: string[];
  pageSize?: number;
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
}

/** §18: "every queue/list" gets this — sortable headers, search, pagination,
 * empty states, and optional row actions, so every dashboard's tables behave
 * identically instead of each page hand-rolling its own. */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  isLoading,
  isError,
  errorMessage = "Could not load data",
  emptyMessage = "Nothing here yet.",
  searchPlaceholder = "Search…",
  searchKeys,
  pageSize = 8,
  onRowClick,
  rowActions,
}: DataTableProps<T>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!query.trim() || !searchKeys || searchKeys.length === 0) return data;
    const needle = query.trim().toLowerCase();
    return data.filter((row) =>
      searchKeys.some((key) => {
        const col = columns.find((c) => c.key === key);
        const value = col?.accessor?.(row);
        return value !== undefined && String(value).toLowerCase().includes(needle);
      }),
    );
  }, [data, query, searchKeys, columns]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.accessor) return filtered;
    const copy = [...filtered];
    copy.sort((a, b) => {
      const av = col.accessor!(a);
      const bv = col.accessor!(b);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.direction === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sort, columns]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const clampedPage = Math.min(page, pageCount - 1);
  const pageRows = sorted.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize);

  function toggleSort(key: string) {
    setPage(0);
    setSort((prev) => {
      if (prev?.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return null;
    });
  }

  return (
    <div>
      {searchKeys && searchKeys.length > 0 ? (
        <div className="mb-3 max-w-xs">
          <TextInput
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </div>
      ) : null}

      {isLoading ? <TableSkeleton cols={columns.length} /> : null}
      {isError ? <Banner kind="error">{errorMessage}</Banner> : null}

      {!isLoading && !isError ? (
        sorted.length === 0 ? (
          <EmptyState>{emptyMessage}</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400 dark:border-slate-800 dark:text-slate-500">
                  {columns.map((col) => (
                    <th key={col.key} className={`py-2 pr-4 font-medium ${col.className ?? ""}`}>
                      {col.sortable ? (
                        <button
                          className="inline-flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-300"
                          onClick={() => toggleSort(col.key)}
                        >
                          {col.header}
                          <Icon
                            name="chevronUpDown"
                            className={`h-3.5 w-3.5 ${sort?.key === col.key ? "text-indigo-600 dark:text-indigo-400" : "text-slate-300 dark:text-slate-600"}`}
                          />
                        </button>
                      ) : (
                        col.header
                      )}
                    </th>
                  ))}
                  {rowActions ? <th className="py-2 pl-4" /> : null}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((row) => (
                  <tr
                    key={getRowId(row)}
                    className={`border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60 ${onRowClick ? "cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-indigo-500/50" : ""}`}
                    onClick={() => onRowClick?.(row)}
                    tabIndex={onRowClick ? 0 : undefined}
                    role={onRowClick ? "button" : undefined}
                    onKeyDown={
                      onRowClick
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              onRowClick(row);
                            }
                          }
                        : undefined
                    }
                  >
                    {columns.map((col) => (
                      <td key={col.key} className={`py-3 pr-4 text-slate-700 dark:text-slate-300 ${col.className ?? ""}`}>
                        {col.render ? col.render(row) : (col.accessor?.(row) ?? null)}
                      </td>
                    ))}
                    {rowActions ? (
                      // Stop both click and keydown from bubbling to the row —
                      // otherwise pressing Enter/Space on a focused action
                      // button would also fire onRowClick via the row's own
                      // keydown handler (keydown bubbles even though the
                      // button's own click doesn't, since that's already
                      // stopped above).
                      <td
                        className="py-3 pl-4 text-right"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        {rowActions(row)}
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>

            {pageCount > 1 ? (
              <div className="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>
                  Page {clampedPage + 1} of {pageCount} · {sorted.length} total
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    className="px-2 py-1 text-xs"
                    disabled={clampedPage === 0}
                    onClick={() => setPage(clampedPage - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    className="px-2 py-1 text-xs"
                    disabled={clampedPage >= pageCount - 1}
                    onClick={() => setPage(clampedPage + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        )
      ) : null}
    </div>
  );
}
