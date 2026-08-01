"use client";

import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { MouseEvent } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { components } from "@/lib/api/schema";
import { formatCost, formatDuration } from "@/lib/format";
import { splitRepoFullName } from "@/lib/repo-full-name";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { RelativeTime } from "./relative-time";
import { StatusBadge } from "./status-badge";

type RunSummary = components["schemas"]["RunSummary"];

function runDetailHref(run: RunSummary): string {
  const { owner, repo } = splitRepoFullName(run.repo_full_name);
  return `/dashboard/runs/${owner}/${repo}/${run.issue_number}`;
}

/**
 * `<Table>` is `table-layout: fixed` -- explicit per-column widths here (all
 * but "issue", which takes whatever's left) are what makes that work. Auto
 * table layout sized columns off content instead, which let the row wider
 * than its `overflow-x-auto` container whenever a repo name/thread id was
 * long enough, flashing a horizontal scrollbar on mount.
 */
const COLUMN_WIDTHS: Record<string, string> = {
  run: "w-36",
  repo_full_name: "w-40",
  status: "w-44",
  estimated_cost_usd: "w-20",
  duration_seconds: "w-20",
  started_at: "w-24",
};

const columns: ColumnDef<RunSummary>[] = [
  {
    id: "run",
    header: "Run",
    cell: ({ row }) => (
      <Link
        href={runDetailHref(row.original)}
        className="block truncate font-mono text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        title={row.original.thread_id}
      >
        {row.original.thread_id}
      </Link>
    ),
  },
  {
    accessorKey: "repo_full_name",
    header: "Repository",
    cell: ({ row }) => (
      <span className="block truncate text-sm" title={row.original.repo_full_name}>
        {row.original.repo_full_name}
      </span>
    ),
  },
  {
    id: "issue",
    header: "Issue / Title",
    cell: ({ row }) => (
      <Link
        href={runDetailHref(row.original)}
        className="block truncate text-sm hover:underline"
        title={row.original.issue_title}
      >
        <span className="text-muted-foreground">#{row.original.issue_number}</span>{" "}
        {row.original.issue_title}
      </Link>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => <StatusBadge status={row.original.status} />,
  },
  {
    accessorKey: "estimated_cost_usd",
    header: "Est. Cost",
    cell: ({ row }) => (
      <span className="block truncate font-mono text-xs">
        {formatCost(row.original.estimated_cost_usd)}
      </span>
    ),
  },
  {
    accessorKey: "duration_seconds",
    header: "Duration",
    cell: ({ row }) => (
      <span className="block truncate font-mono text-xs">
        {formatDuration(row.original.duration_seconds)}
      </span>
    ),
  },
  {
    accessorKey: "started_at",
    header: "Started At",
    cell: ({ row }) => (
      <span className="block truncate text-xs text-muted-foreground">
        <RelativeTime isoDate={row.original.started_at} />
      </span>
    ),
  },
];

export function RunsTableEmptyState() {
  return (
    <div className="flex flex-col items-center gap-1 rounded-xl bg-card py-16 text-center ring-1 ring-foreground/10">
      <p className="text-sm font-medium">No runs match these filters</p>
      <p className="text-sm text-muted-foreground">Try widening the period or clearing a filter.</p>
    </div>
  );
}

/**
 * `animationKey` should change exactly when the filters/page change (never
 * on a same-key background poll) -- a React `key` change on the outer
 * `<Table>` remounts it, which is what re-triggers each row's `initial`
 * animation; a same-key data update from polling just re-renders in place
 * with no remount, so rows never re-stagger every ~10s.
 */
export function RunsTable({ runs, animationKey }: { runs: RunSummary[]; animationKey: string }) {
  const reducedMotion = useReducedMotion();
  const router = useRouter();
  const table = useReactTable({ data: runs, columns, getCoreRowModel: getCoreRowModel() });

  if (runs.length === 0) {
    return <RunsTableEmptyState />;
  }

  return (
    <Table key={animationKey}>
      <TableHeader>
        {table.getHeaderGroups().map((headerGroup) => (
          <TableRow key={headerGroup.id}>
            {headerGroup.headers.map((header) => (
              <TableHead key={header.id} className={COLUMN_WIDTHS[header.column.id]}>
                {header.isPlaceholder
                  ? null
                  : flexRender(header.column.columnDef.header, header.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row, index) => (
          <motion.tr
            key={row.id}
            className="cursor-pointer border-b border-border transition-colors hover:bg-muted/50"
            onClick={(event: MouseEvent<HTMLTableRowElement>) => {
              // Real <Link>s in this row (Run, Issue) keep native click/middle-click/cmd-click
              // behavior -- only take over the click when it didn't originate on one of them.
              if ((event.target as HTMLElement).closest("a")) return;
              router.push(runDetailHref(row.original));
            }}
            initial={reducedMotion ? false : { opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{
              duration: 0.3,
              ease: [0.34, 1.56, 0.64, 1],
              delay: reducedMotion ? 0 : index * 0.04,
            }}
          >
            {row.getVisibleCells().map((cell) => (
              <TableCell key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </motion.tr>
        ))}
      </TableBody>
    </Table>
  );
}
