import { useEffect, useState } from "react";

/**
 * Trail a value by `delay` ms.
 *
 * Used for the keyword filter: the input stays fully responsive while the
 * query key -- and therefore the request and its server-side cache entry --
 * only changes once typing pauses.
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
