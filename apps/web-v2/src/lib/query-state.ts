"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Keeps a single filter/search value in the URL so the view is deep-linkable.
 * The local mirror keeps typing responsive while the URL update can be debounced.
 */
export function useQueryState(key: string, fallback = "", debounce = 0) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const urlValue = params.get(key) ?? fallback;
  const [value, setValue] = useState(urlValue);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    queueMicrotask(() => setValue(urlValue));
  }, [urlValue]);

  const update = useCallback((next: string) => {
    setValue(next);
    if (timer.current !== null) window.clearTimeout(timer.current);
    const commit = () => {
      const search = new URLSearchParams(window.location.search);
      if (next) search.set(key, next);
      else search.delete(key);
      const query = search.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    };
    if (debounce > 0) timer.current = window.setTimeout(commit, debounce);
    else commit();
  }, [debounce, key, pathname, router]);

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  return [value, update] as const;
}
