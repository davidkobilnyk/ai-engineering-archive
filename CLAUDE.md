Tests are written only at public seams (interfaces/behaviour), never against internals; confirm the seams with me before writing tests.
The first test for any feature is a tracer bullet through one end-to-end path.
Expected values in tests come from an independent source (a literal, the spec, a worked example), never recomputed the way the code computes them.
The TDD checklist item "every function has a test" is replaced by "every confirmed seam has a test."
Every implementer subagent follows RED→GREEN regardless of whether the plan says so; every plan task carries explicit RED and GREEN steps.