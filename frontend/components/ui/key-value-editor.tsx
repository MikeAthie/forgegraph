"use client";

import * as React from "react";
import { Plus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Input } from "./input";
import { Button } from "./button";

interface KeyValueEditorProps {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * A reusable key-value pair editor component.
 * Used for editing headers, variables, mappings, etc.
 */
function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder = "Key",
  valuePlaceholder = "Value",
  className,
  disabled = false,
}: KeyValueEditorProps) {
  // Convert object to array of entries for rendering
  const entries = Object.entries(value);

  const handleKeyChange = (oldKey: string, newKey: string) => {
    if (newKey === oldKey) return;
    const newValue: Record<string, string> = {};
    for (const [k, v] of Object.entries(value)) {
      if (k === oldKey) {
        if (newKey.trim()) {
          newValue[newKey] = v;
        }
      } else {
        newValue[k] = v;
      }
    }
    onChange(newValue);
  };

  const handleValueChange = (key: string, newVal: string) => {
    onChange({ ...value, [key]: newVal });
  };

  const handleAdd = () => {
    // Generate unique temporary key
    let index = 1;
    let newKey = `key${index}`;
    while (newKey in value) {
      index++;
      newKey = `key${index}`;
    }
    onChange({ ...value, [newKey]: "" });
  };

  const handleRemove = (key: string) => {
    const newValue = { ...value };
    delete newValue[key];
    onChange(newValue);
  };

  return (
    <div className={cn("space-y-2", className)}>
      {entries.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No entries</p>
      ) : (
        entries.map(([key, val], index) => (
          <div key={`${key}-${index}`} className="flex items-center gap-2">
            <Input
              value={key}
              onChange={(e) => handleKeyChange(key, e.target.value)}
              placeholder={keyPlaceholder}
              className="flex-1 text-sm h-8"
              disabled={disabled}
            />
            <Input
              value={val}
              onChange={(e) => handleValueChange(key, e.target.value)}
              placeholder={valuePlaceholder}
              className="flex-1 text-sm h-8"
              disabled={disabled}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => handleRemove(key)}
              disabled={disabled}
              className="shrink-0 text-muted-foreground hover:text-destructive"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        ))
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleAdd}
        disabled={disabled}
        className="w-full"
      >
        <Plus className="h-4 w-4 mr-1" />
        Add {keyPlaceholder.toLowerCase()}
      </Button>
    </div>
  );
}

export { KeyValueEditor };
export type { KeyValueEditorProps };
