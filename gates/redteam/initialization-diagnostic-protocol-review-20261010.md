# Initialization/history diagnostic protocol review

Owner: Frank Asante Van Laarhoven <frankleroyvan@gmail.com>.

Bounded design review: FREEZE-READY DESIGN. The first observation mismatch is
before current-episode actions; prior-episode carryover remains a competing
explanation. Exact decision-36 history indices/ages, cross-repetition guards,
original full snapshot and fixed root/full order are explicit. Full history
claims require all six image and age guards; partial restore has no exemption.

Bounded executable review: FREEZE. Corrected raw RGB versus encoded PNG digests,
optional legacy abstention and absent recovery-state fields. Ordinary frames use
exactly two render calls; direct comparisons use six single unchanged-physics
calls. Each interval checks 10/0 feedback updates and physics time; unknown state
is retained and rejected. Source/assets are checked before and after execution;
actual postflight digests are recorded. Twenty focused tests independently pass.

No reconstruction, simulator probes, additional pilot starts or model-outcome
previews occurred during review. The named freeze precedes all diagnostic runs.
The recovery pilot matching rule and failed result remain unchanged.
