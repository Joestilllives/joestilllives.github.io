# Red-team review: ep01-key-lock (each spoken line checked against the claims and sources)

| Beat | Line | Verdict |
|---|---|---|
| hook | Those bumps on your key are a password, written in metal. | Metaphor, no factual claim. Fair: the cut depths encode which heights the pins must reach. |
| parts | ...a plug that has to turn, and stacks of pins pushed down by springs. | Supported: US 31,278 lists drivers and "their actuating springs" in drilled holes; US 48,475 says the cylinder must be turned. "Down" depends on orientation; fine for the drawing as shown. |
| split | Each stack is split in two, and every stack splits at a different height. | Supported: "two parts of the tumblers" and tumblers "of different lengths" (US 48,475). Different lengths at rest means the splits sit at different heights. |
| jam | With the wrong key, those splits stay scattered, and the plug is jammed. | Follows from US 48,475: all divisions must be in the same line "before the cylinder D can be turned". Not separately sourced; it is the logical converse. Acceptable. |
| turn | The right key lifts every split to one exact line. Now the plug turns. | Supported, nearly verbatim from US 48,475. |
| receipt | Linus Yale Junior described exactly this in his 1865 patent. | Supported: US 48,475, L. Yale Jr., published 1865-06-27. "Exactly this" holds for the mechanism shown. Did NOT say he invented the pin tumbler (disputed; earlier locks exist). |
| send | Send this to the friend who is always losing their keys. | Ask, no claim. |

Visual accuracy notes: show the key lifting pins (pins rise, never fall, as the key enters); splits must line up exactly at the boundary between plug and housing; the plug rotates only after all splits align; wrong key shows at least two splits off the line.
Result: no blocking issues.
