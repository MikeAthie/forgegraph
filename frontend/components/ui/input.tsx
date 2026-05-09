import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, autoComplete, ...props }, ref) => {
    const resolvedAutoComplete = autoComplete ?? (type === "password" ? "new-password" : undefined);
    const shouldIgnorePasswordManagers =
      type === "password" && resolvedAutoComplete !== "username" && resolvedAutoComplete !== "current-password";

    return (
      <input
        ref={ref}
        type={type}
        autoComplete={resolvedAutoComplete}
        data-lpignore={shouldIgnorePasswordManagers ? "true" : undefined}
        data-1p-ignore={shouldIgnorePasswordManagers ? "true" : undefined}
        data-form-type={shouldIgnorePasswordManagers ? "other" : undefined}
        data-slot="input"
        className={cn(
          "file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input min-h-11 w-full min-w-0 rounded-md border bg-transparent px-3 py-2.5 text-base shadow-xs transition-[color,border-color,box-shadow,background-color] outline-none motion-reduce:transition-none file:inline-flex file:min-h-8 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
          "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
          "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
