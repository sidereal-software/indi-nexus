Every indicator that shows an INDI state now reads its colour from one place. A component
cannot build a Tailwind class name at runtime, so each of the five places that showed a
state carried its own copy of the four-way mapping, and they drifted. Elements now declare
`data-indi-state` and the theme sets `--indi-state` from it, so a badge, a dot, a bar and
an SVG fill can each use whichever CSS property they need. `StateDot` is exported for
frontends built on the hooks.
