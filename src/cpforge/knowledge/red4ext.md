# RED4ext plugins (C++)

Native DLLs in `red4ext/plugins/<Mod>/<Mod>.dll`, loaded by RED4ext. Use them
only for what redscript and Codeware cannot do: new native functions, engine
hooks, heavy computation, OS access.

## Template

`cpforge new MyPlugin --kind red4ext` creates `source/red4ext/` with CMake,
C++20 and the v1 SDK API:

- exports `Main(PluginHandle, EMainReason, const Sdk*)`, `Query(PluginInfo*)`,
  `Supports()` returning `RED4EXT_API_VERSION_1`
- `aInfo->runtime = RED4EXT_V1_RUNTIME_VERSION_LATEST`
- logging: `aSdk->logger->InfoF(aHandle, "...", ...)` into `red4ext/logs/`

The SDK is pinned to commit `0f5eba4` (game 2.5 support). The tagged 1.0.0
release still declares 2.31 as latest, and RED4ext refuses a plugin built for
another runtime. Move the pin only after a test build.

## Build

`cpforge build` runs CMake (`-A x64`) and copies the DLL into
`game/red4ext/plugins/<Mod>/`. Needs CMake and Visual Studio Build Tools with
the C++ workload. The forge's own CI builds this template on Windows.

## Exposing natives to redscript

Register functions/classes through the SDK's RTTI and ship a `.reds` file with
the matching `native func` declarations next to the DLL. See the SDK examples
(`native_class_redscript`, `native_globals_redscript`) in the RED4ext.SDK repo.
