"use client";

import { Button } from "@/components/ui/button";

export default function RunDetailError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-sm font-medium text-destructive">Couldn&apos;t load this run.</p>
      <p className="max-w-md text-sm text-muted-foreground">{error.message}</p>
      <Button variant="outline" className="min-h-11" onClick={() => reset()}>
        Try again
      </Button>
    </div>
  );
}
