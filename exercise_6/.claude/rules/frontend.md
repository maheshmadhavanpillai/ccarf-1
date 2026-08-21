---
paths:
  - "src/frontend/**/*.tsx"
  - "src/frontend/**/*.ts"
  - "src/frontend/**/*.css"
---

# Frontend Rules (React + TypeScript)

## Component Structure
- Functional components only (no class components)
- Props interface defined above the component, exported if reusable
- Hooks at the top of the component body, before any early returns
- File naming: `PascalCase.tsx` for components, `camelCase.ts` for utilities

## State Management
- Local state: `useState` for component-scoped state
- Shared state: Zustand stores in `src/frontend/stores/`
- Server state: TanStack Query (react-query) for API data
- Never store derived data — compute it in render or useMemo

## API Integration
- Use the generated OpenAPI client (`src/frontend/api/generated/`)
- Never write raw `fetch()` calls — use the typed client
- Loading/error states handled by TanStack Query's `isLoading`/`isError`
- Optimistic updates for user-facing mutations (revert on error)

## Styling
- Tailwind CSS utility classes (no custom CSS unless absolutely necessary)
- Design tokens via CSS custom properties for colors, spacing, typography
- Responsive: mobile-first, breakpoints at sm/md/lg/xl
- Dark mode via `dark:` variant classes

## Accessibility
- All interactive elements must be keyboard-navigable
- ARIA labels on icon-only buttons
- Color contrast: WCAG AA minimum (4.5:1 for text)
- Form inputs must have associated labels (not just placeholders)
