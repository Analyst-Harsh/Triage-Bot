import { describe, expect, it } from "vitest";
import { computeObservationDepths } from "./trace-depth";

describe("computeObservationDepths", () => {
  it("assigns depth 0 to a root observation", () => {
    const depths = computeObservationDepths([{ observation_id: "a", parent_observation_id: null }]);
    expect(depths.get("a")).toBe(0);
  });

  it("assigns increasing depth down a parent chain, regardless of input order", () => {
    const observations = [
      { observation_id: "d", parent_observation_id: "c" },
      { observation_id: "c", parent_observation_id: "b" },
      { observation_id: "b", parent_observation_id: "a" },
      { observation_id: "a", parent_observation_id: null },
    ];
    const depths = computeObservationDepths(observations);
    expect(depths.get("a")).toBe(0);
    expect(depths.get("b")).toBe(1);
    expect(depths.get("c")).toBe(2);
    expect(depths.get("d")).toBe(3);
  });

  it("treats a parent not present in this observation set as a root", () => {
    const depths = computeObservationDepths([
      { observation_id: "orphan", parent_observation_id: "missing-parent" },
    ]);
    expect(depths.get("orphan")).toBe(0);
  });

  it("handles multiple independent root chains", () => {
    const observations = [
      { observation_id: "a1", parent_observation_id: null },
      { observation_id: "a2", parent_observation_id: "a1" },
      { observation_id: "b1", parent_observation_id: null },
    ];
    const depths = computeObservationDepths(observations);
    expect(depths.get("a1")).toBe(0);
    expect(depths.get("a2")).toBe(1);
    expect(depths.get("b1")).toBe(0);
  });

  it("does not infinite-loop on a malformed self-referencing chain", () => {
    const observations = [{ observation_id: "x", parent_observation_id: "x" }];
    expect(() => computeObservationDepths(observations)).not.toThrow();
  });
});
