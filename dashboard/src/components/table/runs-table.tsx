"use client";

import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { motion } from "motion/react";
import Link from "next/link";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { components } from "@/lib/api/schema";
import { formatCost, formatDuration, formatRelativeTime } from "@/lib/format";
import { splitRepoFullName } from "@/lib/repo-full-name";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { StatusBadge } from "./status-badge";

type RunSummary = components["schemas"]["RunSummary"];

function runDetailHref(run: RunSummary): string {
  const { owner, repo } = splitRepoFullName(run.repo_full_name);
  return `/dashboard/runs/${owner}/${repo}/${run.issue_number}`;
}

const columns: ColumnDef<RunSummary>[] = [
  {
    id: "run",
    header: "Run",
    cell: ({ row }) => (
      <Link
        href={runDetailHref(row.original)}
        className="font-mono text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        {row.original.thread_id}
      </Link>
    ),
  },
  {
    accessorKey: "repo_full_name",
    header: "Repository",
    cell: ({ row }) => <span className="text-sm">{row.original.repo_full_name}</span>,
  },
  {
    id: "issue",
    header: "Issue / Title",
    cell: ({ row }) => (
      <Link href={runDetailHref(row.original)} className="text-sm hover:underline">
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
      <span className="font-mono text-xs">{formatCost(row.original.estimated_cost_usd)}</span>
    ),
  },
  {
    accessorKey: "duration_seconds",
    header: "Duration",
    cell: ({ row }) => (
      <span className="font-mono text-xs">{formatDuration(row.original.duration_seconds)}</span>
    ),
  },
  {
    accessorKey: "started_at",
    header: "Started At",
    cell: ({ row }) => (
      <span className="text-xs text-muted-foreground">
        {formatRelativeTime(row.original.started_at)}
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
              <TableHead key={header.id}>
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
            className="border-b border-border transition-colors hover:bg-muted/50"
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
