The architecture diagrams now follow whichever theme they are rendered in. They carried a
hardcoded light palette, so on a dark page the boxes became a bright island and the labels
went unreadable; ownership is shown with the border instead of colour. CI validates every
diagram with Mermaid's own CLI, so a broken one fails the build rather than rendering as an
empty box.
