export type ObservationLike = { observation_id: string; parent_observation_id: string | null };

/**
 * Nesting depth for each observation, for TraceSummaryPanel's cheap
 * waterfall indent -- walks each observation's `parent_observation_id`
 * chain up to a root (no parent, or a parent not present in this trace's
 * fetched set). Memoized per call; guards against a cyclic/self-referencing
 * chain (shouldn't happen, but a UI helper should never infinite-loop on
 * malformed upstream data) by capping chain length at the observation count.
 */
export function computeObservationDepths(observations: ObservationLike[]): Map<string, number> {
  const byId = new Map(observations.map((o) => [o.observation_id, o]));
  const depths = new Map<string, number>();

  for (const observation of observations) {
    if (depths.has(observation.observation_id)) continue;
    const chain: string[] = [];
    let current: ObservationLike | undefined = observation;
    while (current && !depths.has(current.observation_id) && chain.length <= observations.length) {
      chain.push(current.observation_id);
      current = current.parent_observation_id ? byId.get(current.parent_observation_id) : undefined;
    }
    const baseDepth = current ? (depths.get(current.observation_id) ?? 0) + 1 : 0;
    chain.reverse().forEach((id, index) => depths.set(id, baseDepth + index));
  }

  return depths;
}
