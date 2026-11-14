// {{NAME}} - redscript entry point.
// Look up real names before hooking: cpforge api class PlayerPuppet --filter Attached
// Check hooks and compile against your game: cpforge check --compile
module {{ID}}

// Runs whenever the player object attaches (new game, load, respawn).
// @wrapMethod keeps the original and other mods' wraps working; prefer it to @replaceMethod.
@wrapMethod(PlayerPuppet)
protected cb func OnGameAttached() -> Bool {
  let result: Bool = wrappedMethod();
  FTLog(s"[{{ID}}] player attached");
  return result;
}
