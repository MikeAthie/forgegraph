"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";

interface SearchInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
  /** Controlled value (optional - if not provided, component manages its own state) */
  value?: string;
  /** Called on every keystroke (for controlled mode) */
  onChange?: (value: string) => void;
  /** Called after debounce with the search value */
  onSearch?: (value: string) => void;
  /** Debounce delay in milliseconds */
  debounceMs?: number;
}

export function SearchInput({
  value: controlledValue,
  onChange,
  onSearch,
  debounceMs = 300,
  className,
  placeholder = "Search",
  ...props
}: SearchInputProps) {
  const isControlled = controlledValue !== undefined;
  const [internalValue, setInternalValue] = useState("");
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchValue = controlledValue ?? internalValue;

  useEffect(() => {
    return () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    };
  }, []);

  const scheduleSearch = (nextValue: string) => {
    if (!onSearch) {
      return;
    }

    if (searchTimerRef.current) {
      clearTimeout(searchTimerRef.current);
    }

    searchTimerRef.current = setTimeout(() => {
      onSearch(nextValue);
    }, debounceMs);
  };

  const updateSearchValue = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    if (!isControlled) {
      setInternalValue(newValue);
    }
    onChange?.(newValue);
    scheduleSearch(newValue);
  };

  const clearSearchValue = () => {
    if (!isControlled) {
      setInternalValue("");
    }
    onChange?.("");
    scheduleSearch("");
  };

  return (
    <div className={cn("relative", className)}>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="absolute left-3 top-1/2 -tranzinc-y-1/2 size-4 text-muted-foreground pointer-events-none"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
          clipRule="evenodd"
        />
      </svg>
      <Input
        type="search"
        value={searchValue}
        onChange={updateSearchValue}
        placeholder={placeholder}
        className="pl-9 pr-11"
        {...props}
      />
      {searchValue && (
        <button
          type="button"
          onClick={clearSearchValue}
          className="absolute right-0 top-1/2 flex size-11 -tranzinc-y-1/2 touch-manipulation items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none"
          aria-label="Clear search"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="size-4">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        </button>
      )}
    </div>
  );
}
