# redscript

Script mods in `r6/scripts/<Mod>/*.reds`, compiled by redscript every time the
game starts. Log: `r6/logs/redscript_rCURRENT.log`.

## Loop

1. Find the real target: `cpforge api class PlayerPuppet --filter Attached`,
   `cpforge api search OnAction --kind func`. The index comes from your own
   install (vanilla source in `tools/redmod/scripts`, natives from
   `tools/redmod/metadata.json`, plus installed mods), so it matches your patch.
2. Write the hook. `cpforge check` confirms the class and method exist (and
   suggests close names when they do not).
3. `cpforge check --compile` runs the game's own compiler (`engine/tools/scc.exe`)
   on a scratch copy with your mod plus `script_dependencies` from
   `cpforge.json`. The live `r6/cache` is never touched.

## Hooks

| Annotation | Use | Conflict risk |
|---|---|---|
| `@wrapMethod(Class)` | run code around the original; call `wrappedMethod(...)` | low: wraps stack |
| `@replaceMethod(Class)` | replace the body | high: only one replacement survives |
| `@addMethod(Class)` / `@addField(Class)` | add members | duplicate adds fail to compile |
| `@replaceGlobal()` | replace a global function | high |

Vanilla `event` functions are `cb func ... -> Bool` in redscript, e.g.
`protected cb func OnGameAttached() -> Bool`.

## Things that bite

- `continue` needs redscript 1.0+; 0.5.x reports `UNRESOLVED_REF`.
- Field defaults must be simple literals; a negative float default failed with
  `INVALID_CONSTANT`. Set the value in `OnAttach` instead.
- Natives listed in `metadata.json` are not callable until declared. `LogChannel`
  is native-only in vanilla (`UNRESOLVED_FN`); `FTLog` compiles; Codeware adds `ModLog`.
- The standalone compiler can overflow its stack on huge array literals, very
  long `+` string chains, or a whole 300-mod load order. Split literals (one
  `StrSplit` over a delimited string) and compile with only your dependencies.
- `module A.B` (no semicolon) namespaces a file. A ScriptableSystem in a module
  is registered under the qualified name; keep systems you look up by name
  outside modules or use the full name.
- A `ScriptableService` is created at boot, before Mod Settings loads saved
  values; settings belong on a `ScriptableSystem`.
- Persisted fields (`persistent let`) only store simple types reliably; strings
  were stored as `Int32` char-code arrays in a shipped mod to survive saves.

## Libraries worth knowing

Codeware (callbacks, `DynamicEntitySystem`, UI, reflection), Mod Settings,
RedData (JSON), RedHttpClient (HTTP), RedFileSystem (files). Look up their API
the same way: they are in the index under `mod:<Name>`.
