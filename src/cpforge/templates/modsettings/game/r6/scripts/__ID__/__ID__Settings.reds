// {{NAME}} - Mod Settings menu.
// Why a ScriptableSystem: Mod Settings writes saved values into class defaults at
// startup and pushes later changes only to registered listeners. A
// ScriptableSystem is created each session after that load, so its fields start
// with the saved values. (A ScriptableService is created earlier and would not.)
// No module line here: the system is looked up by its plain class name below.

public class {{ID}}Settings extends ScriptableSystem {

  private func OnAttach() {
    ModSettings.RegisterListenerToClass(this);
  }

  private func OnDetach() {
    ModSettings.UnregisterListenerToClass(this);
  }

  public static func Get() -> ref<{{ID}}Settings> {
    return GameInstance.GetScriptableSystemsContainer(GetGameInstance()).Get(n"{{ID}}Settings") as {{ID}}Settings;
  }

  @runtimeProperty("ModSettings.mod", "{{NAME}}")
  @runtimeProperty("ModSettings.category", "General")
  @runtimeProperty("ModSettings.category.order", "1")
  @runtimeProperty("ModSettings.displayName", "Enabled")
  @runtimeProperty("ModSettings.description", "Turn {{NAME}} on or off.")
  public let enabled: Bool = true;

  @runtimeProperty("ModSettings.mod", "{{NAME}}")
  @runtimeProperty("ModSettings.category", "General")
  @runtimeProperty("ModSettings.category.order", "1")
  @runtimeProperty("ModSettings.displayName", "Strength")
  @runtimeProperty("ModSettings.description", "Example slider.")
  @runtimeProperty("ModSettings.step", "0.1")
  @runtimeProperty("ModSettings.min", "0.0")
  @runtimeProperty("ModSettings.max", "2.0")
  public let strength: Float = 1.0;
}
