# Fonts of the signature

Shipped with the module so that the signature renders without fetching
anything from a third party. All three are under the SIL Open Font License
1.1 (`OFL-*.txt` next to them), none with a Reserved Font Name: a subset
may keep its name.

| File | Font | Source in github.com/google/fonts |
|---|---|---|
| `PublicSans.woff2` | Public Sans, variable weight 100–900 | `ofl/publicsans/PublicSans[wght].ttf` |
| `JetBrainsMono.woff2` | JetBrains Mono, variable weight 100–800 | `ofl/jetbrainsmono/JetBrainsMono[wght].ttf` |
| `Fraunces-Italic.woff2` | Fraunces Italic, static 400 | `ofl/fraunces/Fraunces-Italic[SOFT,WONK,opsz,wght].ttf` |

Taken at commit `bd8f81ddb5c74d5c8897b36ad88b440266245103`, then reduced to the Latin
ranges (French and the other Latin-script languages), with fontTools 4.55.3
and brotli 1.1.0:

```
fonttools varLib.instancer Fraunces-Italic[SOFT,WONK,opsz,wght].ttf \
    SOFT=0 WONK=drop opsz=24 wght=400 -o Fraunces-Italic-400.ttf
pyftsubset <font>.ttf --layout-features='*' --flavor=woff2 \
    --unicodes="U+0000-024F,U+0259,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0300-0301,U+0303-0304,U+0308,U+0327,U+1E00-1EFF,U+2000-206F,U+20AC,U+2122,U+2190-2193,U+2212,U+FEFF,U+FFFD"
```

A character outside these ranges falls back to a system font.
