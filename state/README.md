state/

watchlist.txt — optional; one name per line ('#' comments). Names listed
here get the ranked Watch List section on /predictions/ (P(called in the
next 7 days, expected window, family notes). Everything else on that page
— the hit ledger, scorecard, on-clock list — is DERIVED at build time from
data/days/ and needs no stored state. (The old predictions.json was removed
2026-09-28: CI builds discarded it on every run, so the committed hit ledger
had sat frozen/empty since launch and could never record a hit.)
