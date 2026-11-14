# Input Loader (key bindings)

XML files in `r6/input/` are merged into the game's input contexts by Input
Loader (RED4ext plugin; log `red4ext/logs/input_loader.log`).

```xml
<bindings>
  <context name="MyContext">
    <action name="MyMod_Activate" map="MyMod_Activate_Key" />
  </context>
  <context name="Exploration" append="true">
    <include name="MyContext" />
  </context>
  <mapping name="MyMod_Activate_Key" type="Button">
    <button id="IK_F7" overridableUI="myModActivate" />
  </mapping>
</bindings>
```

- Existing context names: see `r6/cache/inputContexts.xml` (e.g. Exploration,
  Combat, UIShared, VehicleDrive).
- React in redscript: `player.RegisterInputListener(this, n"MyMod_Activate")`,
  then `OnAction(action: ListenerAction, consumer: ListenerActionConsumer)` with
  `ListenerAction.GetName` / `ListenerAction.GetType` (`gameinputActionType.BUTTON_PRESSED`).
  The `input` template wires this on `PlayerPuppet`.
- A key the player sets in Mod Settings (`EInputKey` field) is the alternative
  when you do not want a game input context.
