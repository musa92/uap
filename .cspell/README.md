# Spelling dictionaries

A flat allowlist rots: once a word is in it, nobody can tell whether it is real
vocabulary or a typo somebody whitelisted to turn CI green. This repository had
both — `Gayev`, a misspelling of the author's name, and `adsense`, which let the
wrong casing of a trademark pass.

So the dictionaries are split by domain and each one states what belongs in it.

| File | Contains | Test before adding |
|---|---|---|
| `dictionaries/adtech.txt` | Advertising vocabulary | Can you cite the IAB or MRC document that defines it? |
| `dictionaries/cryptography.txt` | Algorithms, encodings | Is that the spelling used by the defining RFC? |
| `dictionaries/protocols.txt` | Named protocols | Is that how its own publisher spells it? |
| `dictionaries/inference.txt` | Serving stack | Is that the project's own name for itself? |
| `dictionaries/project.txt` | Identifiers coined here | Is it greppable in this repository? |
| `dictionaries/proper-nouns.txt` | People, organisations | Have you checked it against the source? |

`flagged.txt` is the opposite: terms that fail the build wherever they appear.
It holds misspellings of words this project uses constantly, where an allowlist
would quietly accept both forms, plus anything that was actually wrong here once.

## Adding a word

Put it in the file whose test it passes. If it passes none of them, it is
probably a typo, or it belongs in prose that should be rewritten. Adding to a
dictionary is a claim that the word is correct — make it deliberately.
