# SEO Page Refactoring Guide

## Overview

The SEO page (`app/dashboard/seo/page.tsx`) has been refactored from a monolithic 2,486-line file into a modular, maintainable architecture. This guide explains the new structure and how to use the refactored components.

## What Was Refactored

### Before
- **Single file**: 2,486 lines
- **50+ useState hooks** in BlogTab alone
- **Duplicate code**: Modal structures, form patterns, color utilities
- **Poor type safety**: Liberal use of `any`, missing interfaces
- **No performance optimization**: Missing memoization, unnecessary re-renders

### After
- **Modular structure**: Organized into logical folders
- **Reusable components**: Shared UI components, modals, hooks
- **Type-safe**: Proper TypeScript interfaces and types
- **Better performance**: Custom hooks with memoization
- **Maintainable**: Easy to test, update, and extend

## New File Structure

```
web/
├── components/seo/
│   ├── shared/              # Reusable UI components
│   │   ├── HelpTooltip.tsx
│   │   ├── ScoreBadge.tsx
│   │   ├── StatCard.tsx
│   │   ├── IssuePill.tsx
│   │   └── index.ts
│   ├── modals/              # Modal components
│   │   ├── ReadPostModal.tsx
│   │   ├── EditPostModal.tsx
│   │   ├── PublishModal.tsx
│   │   └── index.ts
│   └── tabs/                # Tab components (to be created)
│       ├── OverviewTab.tsx
│       ├── AuditTab.tsx
│       ├── KeywordsTab.tsx
│       ├── BlogTab.tsx
│       ├── CalendarTab.tsx
│       └── AgentChatTab.tsx
├── hooks/seo/               # Custom hooks
│   ├── useBusinessProfile.ts
│   ├── useSeoSummary.ts
│   ├── useBlogPosts.ts
│   ├── useSeoMemory.ts
│   └── index.ts
└── lib/seo/                 # Utilities and types
    ├── types.ts             # TypeScript interfaces
    └── utils.ts             # Helper functions
```

## Usage Examples

### 1. Using Shared Components

```tsx
import { HelpTooltip, ScoreBadge, StatCard, IssuePill } from "@/components/seo/shared";

// Display a score badge
<ScoreBadge score={85} grade="B" />

// Show a stat card
<StatCard label="Total Posts" value={42} sub="Published this month" />

// Add a help tooltip
<span>SEO Score<HelpTooltip text="Your overall SEO health score" /></span>

// Display issue severity
<IssuePill type="critical" />
```

### 2. Using Custom Hooks

```tsx
import { useBusinessProfile, useSeoSummary, useBlogPosts } from "@/hooks/seo";

function MyComponent() {
  const { profile, loading, error } = useBusinessProfile();
  const { summary } = useSeoSummary();
  const { posts, loadPosts, deletePost, updatePost } = useBlogPosts();

  // Use the data...
}
```

### 3. Using Utility Functions

```tsx
import { 
  getScoreColor, 
  getDifficultyLabel, 
  formatDate,
  splitCommaSeparated 
} from "@/lib/seo/utils";

const color = getScoreColor(85); // "bg-blue-100 text-blue-700 border-blue-200"
const label = getDifficultyLabel("low"); // "Easy"
const date = formatDate("2024-01-15"); // "1/15/2024"
const keywords = splitCommaSeparated("seo, marketing, blog"); // ["seo", "marketing", "blog"]
```

### 4. Using Modal Components

```tsx
import { ReadPostModal, EditPostModal, PublishModal } from "@/components/seo/modals";

function BlogList() {
  const [selectedPost, setSelectedPost] = useState<BlogPost | null>(null);
  const [editingPost, setEditingPost] = useState<BlogPost | null>(null);
  const [publishingPost, setPublishingPost] = useState<BlogPost | null>(null);

  return (
    <>
      {/* Read modal */}
      {selectedPost && (
        <ReadPostModal
          post={selectedPost}
          onClose={() => setSelectedPost(null)}
          onPublish={() => setPublishingPost(selectedPost)}
          onEdit={() => setEditingPost(selectedPost)}
          onDelete={async () => {
            await deletePost(selectedPost.id);
            setSelectedPost(null);
          }}
        />
      )}

      {/* Edit modal */}
      {editingPost && (
        <EditPostModal
          post={editingPost}
          onClose={() => setEditingPost(null)}
          onSave={(updated) => {
            updatePost(updated);
            setEditingPost(null);
          }}
        />
      )}

      {/* Publish modal */}
      {publishingPost && (
        <PublishModal
          post={publishingPost}
          onClose={() => setPublishingPost(null)}
          onPublished={() => {
            loadPosts();
            setPublishingPost(null);
          }}
        />
      )}
    </>
  );
}
```

## Type Definitions

All types are centralized in `lib/seo/types.ts`:

```tsx
import type { 
  Tab, 
  CalendarWritePayload, 
  DraftStatus,
  ChatMsg,
  SeoMemory,
  BusinessData,
  PerformanceData,
  SeoBusinessContext,
  BlogPost,
  SeoKeyword
} from "@/lib/seo/types";
```

## Migration Steps

To complete the refactoring of the main `page.tsx` file:

### Step 1: Extract Tab Components
Move each tab function (OverviewTab, AuditTab, etc.) into separate files in `components/seo/tabs/`.

### Step 2: Update Imports
Replace inline components with imports:

```tsx
// Before
function OverviewTab({ ... }) { ... }

// After
import { OverviewTab } from "@/components/seo/tabs";
```

### Step 3: Replace Utilities
Replace inline helper functions with imported utilities:

```tsx
// Before
const color = score >= 90 ? "bg-green-100..." : ...;

// After
import { getScoreColor } from "@/lib/seo/utils";
const color = getScoreColor(score);
```

### Step 4: Use Custom Hooks
Replace useState/useEffect patterns with custom hooks:

```tsx
// Before
const [posts, setPosts] = useState<BlogPost[]>([]);
useEffect(() => {
  seoApi.listPosts().then(setPosts);
}, []);

// After
const { posts, loadPosts } = useBlogPosts();
```

### Step 5: Add Performance Optimizations
Wrap expensive computations with useMemo and callbacks with useCallback:

```tsx
const sortedPosts = useMemo(() => 
  posts.sort((a, b) => ...), 
  [posts]
);

const handleDelete = useCallback((id: string) => {
  deletePost(id);
}, [deletePost]);
```

## Benefits

### 1. **Maintainability**
- Each component has a single responsibility
- Easy to locate and update specific functionality
- Clear separation of concerns

### 2. **Reusability**
- Shared components can be used across the app
- Custom hooks encapsulate common patterns
- Utilities prevent code duplication

### 3. **Type Safety**
- Centralized type definitions
- Proper TypeScript interfaces
- Reduced runtime errors

### 4. **Performance**
- Custom hooks prevent unnecessary re-renders
- Memoization for expensive computations
- Optimized component structure

### 5. **Testability**
- Small, focused components are easier to test
- Utilities can be unit tested independently
- Hooks can be tested in isolation

## Next Steps

1. **Extract remaining tab components** from `page.tsx`
2. **Add performance optimizations** (React.memo, useMemo, useCallback)
3. **Write unit tests** for utilities and hooks
4. **Add Storybook stories** for shared components
5. **Document component APIs** with JSDoc comments

## Common Patterns

### Color Utilities
All color-related logic is centralized in `utils.ts`:
- `getScoreColor(score)` - SEO score colors
- `getDifficultyColor(difficulty)` - Keyword difficulty colors
- `getStatusColor(status)` - Post status colors
- `getTrafficColor(traffic)` - Traffic estimate colors
- `getPriorityStyle(priority)` - Priority badge styles

### Data Transformations
- `splitCommaSeparated(value)` - Parse comma-separated strings
- `joinWithCommas(values)` - Join array into comma-separated string
- `formatDate(dateString)` - Format dates consistently
- `formatDateTime(dateString)` - Format date and time

### Custom Hooks Pattern
All hooks follow this pattern:
```tsx
export function useResourceName() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Load data
  // Provide actions

  return { data, loading, error, ...actions };
}
```

## Troubleshooting

### Import Errors
If you see import errors, ensure:
1. Path aliases are configured in `tsconfig.json`
2. Files are in the correct directories
3. Index files export all components

### Type Errors
If you see type errors:
1. Check that types are imported from `@/lib/seo/types`
2. Use type assertions for optional properties: `(post as any).calendar_week`
3. Ensure API types are up to date

### Hook Errors
If hooks don't work as expected:
1. Ensure they're called at the top level of components
2. Check dependency arrays in useEffect
3. Verify API endpoints are correct

## Conclusion

This refactoring significantly improves the SEO page's code quality, maintainability, and performance. The modular structure makes it easier to add features, fix bugs, and onboard new developers.

For questions or issues, refer to the individual component files or consult the team.
