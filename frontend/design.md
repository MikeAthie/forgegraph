# ForgeGraph Design System

This document defines the design philosophy, color palette, typography, and component guidelines for the ForgeGraph frontend.

## Design Philosophy

ForgeGraph follows a **functional elegance** design philosophy - interfaces should be clear, purposeful, and delightful without sacrificing usability. We prioritize:

1. **Clarity over decoration** - Every element serves a purpose. Visual flourishes enhance understanding, not distract from it.

2. **Consistency through constraints** - A limited, intentional palette of colors, spacing, and typography creates coherence across the application.

3. **Responsive by default** - All components work across screen sizes. Mobile-first thinking guides layout decisions.

4. **Accessible to all** - WCAG 2.1 AA compliance is the baseline. Focus states, contrast ratios, and semantic HTML are non-negotiable.

5. **Dark mode as first-class** - Both light and dark themes are designed with equal care, not derived from each other.

---

## Color Palette

ForgeGraph uses **OKLch color space** for perceptually uniform colors that work beautifully in both light and dark modes.

### Semantic Colors

| Token                  | Light Mode                  | Dark Mode                   | Usage                                 |
| ---------------------- | --------------------------- | --------------------------- | ------------------------------------- |
| `--background`         | `oklch(1 0 0)`              | `oklch(0.145 0 0)`          | Page/container backgrounds            |
| `--foreground`         | `oklch(0.145 0 0)`          | `oklch(0.985 0 0)`          | Primary text                          |
| `--primary`            | `oklch(0.585 0.233 277)`    | `oklch(0.685 0.233 277)`    | Brand color, CTAs, links              |
| `--primary-foreground` | `oklch(0.985 0 0)`          | `oklch(0.985 0 0)`          | Text on primary background            |
| `--secondary`          | `oklch(0.97 0 0)`           | `oklch(0.269 0 0)`          | Secondary buttons, subtle backgrounds |
| `--muted`              | `oklch(0.97 0 0)`           | `oklch(0.269 0 0)`          | Muted backgrounds, disabled states    |
| `--muted-foreground`   | `oklch(0.556 0 0)`          | `oklch(0.708 0 0)`          | Secondary text, placeholders          |
| `--accent`             | `oklch(0.97 0 0)`           | `oklch(0.269 0 0)`          | Hover states, highlights              |
| `--destructive`        | `oklch(0.577 0.245 27.325)` | `oklch(0.704 0.191 22.216)` | Errors, dangerous actions             |
| `--border`             | `oklch(0.922 0 0)`          | `oklch(1 0 0 / 10%)`        | Borders, dividers                     |
| `--input`              | `oklch(0.922 0 0)`          | `oklch(1 0 0 / 15%)`        | Input field borders                   |
| `--ring`               | `oklch(0.585 0.233 277)`    | `oklch(0.685 0.233 277)`    | Focus rings                           |

### Brand Color: Indigo

The primary brand color is **indigo** (hue 277 in OKLch), chosen for:

- Professional yet modern appearance
- Excellent contrast in both light and dark modes
- Strong association with technology and innovation

```css
/* Primary indigo variants */
--primary: oklch(0.585 0.233 277); /* Base */
--primary-hover: oklch(0.525 0.233 277); /* Darker for hover */
--primary-light: oklch(0.685 0.233 277); /* Lighter for dark mode */
```

### Chart Colors

Five distinct colors for data visualization:

| Token       | Light Mode                  | Dark Mode                    |
| ----------- | --------------------------- | ---------------------------- |
| `--chart-1` | `oklch(0.646 0.222 41.116)` | `oklch(0.488 0.243 264.376)` |
| `--chart-2` | `oklch(0.6 0.118 184.704)`  | `oklch(0.696 0.17 162.48)`   |
| `--chart-3` | `oklch(0.398 0.07 227.392)` | `oklch(0.769 0.188 70.08)`   |
| `--chart-4` | `oklch(0.828 0.189 84.429)` | `oklch(0.627 0.265 303.9)`   |
| `--chart-5` | `oklch(0.769 0.188 70.08)`  | `oklch(0.645 0.246 16.439)`  |

### Node Type Colors

Graph editor nodes use semantic colors:

| Node Type   | Color   | Hex       |
| ----------- | ------- | --------- |
| Prompt      | Violet  | `#8b5cf6` |
| Tool (HTTP) | Amber   | `#f59e0b` |
| Transform   | Blue    | `#3b82f6` |
| Branch      | Rose    | `#f43f5e` |
| Merge       | Emerald | `#10b981` |
| Output      | Indigo  | `#6366f1` |
| Human Gate  | Orange  | `#f97316` |

---

## Typography

### Font Stack

ForgeGraph uses a system font stack for optimal performance and native feel:

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
```

### Type Scale

| Class       | Size | Weight | Usage                  |
| ----------- | ---- | ------ | ---------------------- |
| `text-xs`   | 12px | 400    | Captions, labels       |
| `text-sm`   | 14px | 400    | Body text, UI elements |
| `text-base` | 16px | 400    | Default body           |
| `text-lg`   | 18px | 500    | Lead paragraphs        |
| `text-xl`   | 20px | 600    | Section headings       |
| `text-2xl`  | 24px | 700    | Page headings          |
| `text-3xl`  | 30px | 700    | Hero text              |
| `text-4xl`  | 36px | 800    | Display text           |
| `text-5xl`  | 48px | 800    | Large display          |

### Font Weights

- **400 (normal)** - Body text, descriptions
- **500 (medium)** - Emphasized text, labels
- **600 (semibold)** - Buttons, headings
- **700 (bold)** - Page titles, important text
- **800 (extrabold)** - Hero text, display

---

## Spacing & Layout

### Spacing Scale

Based on a 4px grid system:

| Token      | Value | Usage                    |
| ---------- | ----- | ------------------------ |
| `space-1`  | 4px   | Tight gaps, icon padding |
| `space-2`  | 8px   | Default element spacing  |
| `space-3`  | 12px  | Form field gaps          |
| `space-4`  | 16px  | Card padding             |
| `space-6`  | 24px  | Section spacing          |
| `space-8`  | 32px  | Large gaps               |
| `space-12` | 48px  | Section margins          |
| `space-16` | 64px  | Page sections            |
| `space-24` | 96px  | Hero sections            |

### Border Radius

A consistent radius system creates visual harmony:

```css
--radius: 0.625rem; /* 10px - base */
--radius-sm: calc(var(--radius) - 4px); /* 6px */
--radius-md: calc(var(--radius) - 2px); /* 8px */
--radius-lg: var(--radius); /* 10px */
--radius-xl: calc(var(--radius) + 4px); /* 14px */
--radius-2xl: calc(var(--radius) + 8px); /* 18px */
```

### Breakpoints

| Breakpoint | Width  | Usage         |
| ---------- | ------ | ------------- |
| `sm`       | 640px  | Large phones  |
| `md`       | 768px  | Tablets       |
| `lg`       | 1024px | Laptops       |
| `xl`       | 1280px | Desktops      |
| `2xl`      | 1536px | Large screens |

---

## Component Guidelines

### Buttons

Buttons use Class Variance Authority (CVA) for type-safe variants:

**Variants:**

- `default` - Primary actions (indigo background)
- `destructive` - Dangerous actions (red background)
- `outline` - Secondary actions (bordered)
- `secondary` - Tertiary actions (gray background)
- `ghost` - Minimal actions (transparent)
- `link` - Text-only links

**Sizes:**

- `sm` - Height 32px, compact UI
- `default` - Height 36px, standard
- `lg` - Height 40px, CTAs
- `icon` - 36x36px, icon-only

```tsx
<Button variant="default" size="lg">Get Started</Button>
<Button variant="outline">Learn More</Button>
<Button variant="ghost" size="icon"><Icon /></Button>
```

### Cards

Cards use a compound component pattern:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description text</CardDescription>
  </CardHeader>
  <CardContent>{/* Content */}</CardContent>
  <CardFooter>
    <Button>Action</Button>
  </CardFooter>
</Card>
```

### Form Fields

Form fields should always include labels and error states:

```tsx
<FormField id="email" label="Email" description="We'll never share your email." error={errors.email}>
  <Input type="email" placeholder="you@example.com" aria-invalid={!!errors.email} />
</FormField>
```

### Badges

Status indicators and labels:

```tsx
<Badge variant="default">Active</Badge>
<Badge variant="secondary">Draft</Badge>
<Badge variant="destructive">Failed</Badge>
<Badge variant="outline">Beta</Badge>
```

### Dialogs

Modal dialogs for confirmations and forms:

```tsx
<Dialog>
  <DialogTrigger asChild>
    <Button>Open Dialog</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Confirm Action</DialogTitle>
      <DialogDescription>This action cannot be undone.</DialogDescription>
    </DialogHeader>
    {/* Content */}
    <DialogFooter>
      <Button variant="outline">Cancel</Button>
      <Button>Confirm</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

---

## Animation Guidelines

### Core Principles

1. **Purposeful motion** - Animations should guide attention, not distract
2. **Respect user preferences** - Honor `prefers-reduced-motion`
3. **Performance first** - Only animate `transform` and `opacity`
4. **Consistent timing** - Use standard duration and easing curves

### Duration Scale

| Duration | Usage                                |
| -------- | ------------------------------------ |
| `75ms`   | Micro-interactions (hover states)    |
| `150ms`  | Quick transitions (buttons, toggles) |
| `200ms`  | Default UI transitions               |
| `300ms`  | Modal enter/exit                     |
| `500ms`  | Page transitions                     |

### Easing Functions

```css
/* Standard easing */
transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);

/* Enter easing */
transition-timing-function: cubic-bezier(0, 0, 0.2, 1);

/* Exit easing */
transition-timing-function: cubic-bezier(0.4, 0, 1, 1);
```

### Built-in Animations

| Animation        | Usage                   |
| ---------------- | ----------------------- |
| `animate-spin`   | Loading spinners        |
| `animate-pulse`  | Skeleton loaders        |
| `animate-bounce` | Attention indicators    |
| `animate-ping`   | Active state indicators |

### Custom Animations

```css
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
```

---

## Accessibility Requirements

### Focus States

All interactive elements must have visible focus states:

```css
.focus-visible:ring-2
.focus-visible:ring-ring
.focus-visible:ring-offset-2
```

### Contrast Ratios

- **Normal text**: Minimum 4.5:1 contrast ratio
- **Large text (18px+)**: Minimum 3:1 contrast ratio
- **UI components**: Minimum 3:1 contrast ratio

### Keyboard Navigation

- All interactive elements must be keyboard accessible
- Tab order must be logical
- Focus traps in modals must be properly managed

### Screen Reader Support

- Use semantic HTML elements (`<button>`, `<nav>`, `<main>`)
- Provide `aria-label` for icon-only buttons
- Use `role` attributes sparingly and correctly

---

## Dark Mode Implementation

### Activation

Dark mode is controlled via the `next-themes` package:

```tsx
import { ThemeProvider } from "next-themes";

<ThemeProvider attribute="class" defaultTheme="system" enableSystem>
  {children}
</ThemeProvider>;
```

### CSS Variables

The `.dark` class on `<html>` activates dark mode variables:

```css
.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  /* ... other dark mode values */
}
```

### Component Considerations

- Never use hardcoded colors (`bg-white`, `text-gray-900`)
- Always use semantic tokens (`bg-background`, `text-foreground`)
- Test all components in both light and dark modes
- Ensure sufficient contrast in both themes

---

## File Organization

```
frontend/
├── components/
│   ├── ui/                    # Base UI components (shadcn)
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── theme-toggle.tsx
│   │   └── index.ts           # Barrel exports
│   ├── graph-editor/          # Graph-specific components
│   └── Header.tsx             # Layout components
├── styles/
│   └── globals.css            # Theme variables & base styles
├── lib/
│   └── utils.ts               # Utility functions (cn)
└── design.md                  # This file
```

---

## Best Practices Checklist

### Before Shipping

- [ ] Component works in both light and dark mode
- [ ] Focus states are visible and accessible
- [ ] Keyboard navigation works correctly
- [ ] Screen reader announces content appropriately
- [ ] Animations respect `prefers-reduced-motion`
- [ ] Component is responsive across breakpoints
- [ ] Loading and error states are handled
- [ ] Empty states are designed

### Code Quality

- [ ] Use `cn()` utility for conditional classes
- [ ] Export from `components/ui/index.ts`
- [ ] Add `data-slot` attribute for testing
- [ ] Use CVA for variant components
- [ ] Avoid inline styles; use Tailwind classes
- [ ] Keep components focused and composable
