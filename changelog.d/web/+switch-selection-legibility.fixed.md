The selected member of a switch vector is now unmistakable, and safer to click. It was
drawn with the same `accent` token the toggles hover to, so a hovered unselected member
looked identical to the selected one, and the fill itself was nearly invisible against the
card; it now wears the same teal as the Set button, a colour hovering never reaches.

Clicking the member that is already on no longer turns it off. Under `OneOfMany` exactly
one member is on by definition, so there was no such state to reach - a stray click on a
lit "On" would have switched the instrument off. Selecting the member you want is now the
only way to change it. `AtMostOne`, which genuinely permits none, still clears that way.
