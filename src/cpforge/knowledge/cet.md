# Cyber Engine Tweaks (Lua)

`bin/x64/plugins/cyber_engine_tweaks/mods/<Mod>/init.lua`, run by CET's bundled
Lua runtime. A mod reads and writes only inside its own folder.

## Events

`registerForEvent(name, fn)` with `onInit`, `onUpdate` (dt), `onDraw`,
`onOverlayOpen`, `onOverlayClose`, `onShutdown`, `onTweak`. `cpforge check`
rejects other event names.

## Input

`registerHotkey(id, label, fn)` (fires on press) and
`registerInput(id, label, fn(isDown))` (press and release). Players bind them
in the CET overlay.

## UI

ImGui inside `onDraw`, only while the overlay is open:

```lua
if ImGui.Begin('My Window') then
    value = ImGui.Checkbox('Enabled', value)
end
ImGui.End()
```

## Logs

Per-mod `<Mod>.log` next to `init.lua`, plus `scripting.log` and
`cyber_engine_tweaks.log` in the CET folder. `cpforge logs` collects them.
Typical errors: `attempt to index a nil value` (object not ready, or an API
renamed by a patch), `attempt to call a nil value` (function gone).

## Lua syntax check

`cpforge check` runs `luajit -b` or `luac -p` when one is on PATH (or set
`CPFORGE_LUA`). Without one it reports the syntax check as a gap.
