# Lessons from shipped mods

Each line was learned the hard way on game 2.5 with redscript 0.5.x.

- Keys pressed while a custom UI has focus may never reach a global input
  listener; forward them from the UI's own key handler after its typing guard.
- Typing in an in-game text field must not trigger your hotkeys: check a
  "typing" state before handling Y/N style keys.
- Settings on a `ScriptableService` revert every launch; use a `ScriptableSystem`.
- Persist strings across saves as `Int32` char-code arrays on a
  `ScriptableSystem`; restore after load, and say so in logs ("restored N").
- "Restored 0 items" after a fresh launch can be correct: nothing persists
  until the player saves.
- Reasoning-capable LLM APIs may return the reasoning in a separate field; show
  only the content, and retry when `finish_reason` is `length`.
- Keep the stable part of an LLM prompt first and put changing context on the
  last user turn so provider prompt caching keeps working.
- Large literal arrays and long string `+` chains crash the standalone
  compiler; one `StrSplit` over a delimited string is fine.
- No `continue` on redscript 0.5.x; restructure loops.
- `INVALID_CONSTANT` on negative float field defaults; default to 0.0 and set
  the value later.
- The standalone `scc.exe` cannot always compile a whole large load order; the
  in-game compile can. Compile your mod with only its dependencies.
- Zip with forward slashes (PowerShell `Compress-Archive` on older versions
  writes backslashes); `cpforge package` does this for you.
- Leftover `*.vortex_backup` files in plugin folders are Vortex's, harmless,
  and never belong in your package.
- Never ship an API key: placeholders only, and `cpforge validate` scans for
  common key formats.
