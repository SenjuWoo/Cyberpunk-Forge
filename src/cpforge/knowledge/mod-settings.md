# Mod Settings (in-game menu)

Public fields of a redscript class become menu entries through
`@runtimeProperty` annotations. Template: `cpforge new X --kind modsettings`.

```swift
public class MySettings extends ScriptableSystem {
  private func OnAttach() { ModSettings.RegisterListenerToClass(this); }
  private func OnDetach() { ModSettings.UnregisterListenerToClass(this); }

  @runtimeProperty("ModSettings.mod", "My Mod")
  @runtimeProperty("ModSettings.category", "General")
  @runtimeProperty("ModSettings.displayName", "Strength")
  @runtimeProperty("ModSettings.description", "What it does.")
  @runtimeProperty("ModSettings.step", "0.1")
  @runtimeProperty("ModSettings.min", "0.0")
  @runtimeProperty("ModSettings.max", "2.0")
  public let strength: Float = 1.0;
}
```

- Keys in wide use: `mod`, `category`, `category.order`, `displayName`,
  `description`, `step`, `min`, `max`, `dependency`, `displayValues.<EnumValue>`
  (enum fields show as a list; `EInputKey` fields as a key binder).
- Put settings on a `ScriptableSystem`. Mod Settings writes saved values into
  class defaults at startup; a `ScriptableService` is created before that and
  silently keeps code defaults every launch.
- Read them with `GameInstance.GetScriptableSystemsContainer(GetGameInstance()).Get(n"MySettings") as MySettings`.
- Changes arrive live only for registered listeners.
