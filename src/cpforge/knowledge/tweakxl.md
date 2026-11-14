# TweakXL (TweakDB data)

Files in `r6/tweaks/<Mod>/` as `.yaml`/`.yml` (or `.tweak` RED syntax). The
cheapest, most patch-proof way to change items, stats, prices, loot, NPC records.

`cpforge check` parses both. `.tweak` files get a structural check (records,
`[ attributes ]`, typed fields such as `fk< StatModifier >[]`, inline records
with `{ ... } : Base`, top-level flats, missing `;` or `,`, unclosed strings and
brackets) with the line of the first error, then base and reference checks
against TweakDB and installed tweaks. Field types are not checked; TweakXL
reports those in its log at game start.

## Find and read

- `cpforge tweak search lexington preset` - record names (from REDmod's
  `tweakdb*.str` when present, else from the vanilla `.tweak` sources).
- `cpforge tweak show Items.Preset_Lexington_Default` - the vanilla definition,
  its type, and which installed tweak files already change it.
- `cpforge tweak exists A,B,C` - checked against `r6/cache/tweakdb.bin`.

## Write

```yaml
# change one value (a flat)
Items.Preset_Lexington_Default.<field>: <value>

# new record from a type
Items.MyItem:
  $type: Clothing

# new record cloned from another
Items.MyLexington:
  $base: Items.Preset_Lexington_Default
```

Special keys: `$type`, `$base`, `$instances` (templates with `$(name)`).
Array tags: `!append`, `!append-once`, `!prepend`, `!prepend-once`,
`!append-from`, `!prepend-from`, `!remove`.

## Check

`cpforge check` parses every YAML file, then checks `$type` against the record
types in your game, `$base` and record-looking references against
`tweakdb.bin` plus every installed tweak file, and flats whose record does not
exist. TweakXL's own log (`red4ext/plugins/TweakXL/`) is the runtime evidence.

## Conflicts

Several mods may change the same record: `cpforge conflicts --what tweaks`.
Plain values: the last file applied wins. Array tags combine.
