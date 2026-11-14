// {{NAME}} - listen for the action declared in r6/input/{{ID}}.xml.

@wrapMethod(PlayerPuppet)
protected cb func OnGameAttached() -> Bool {
  let result: Bool = wrappedMethod();
  this.RegisterInputListener(this, n"{{ID}}_Activate");
  return result;
}

@wrapMethod(PlayerPuppet)
protected cb func OnAction(action: ListenerAction, consumer: ListenerActionConsumer) -> Bool {
  if Equals(ListenerAction.GetName(action), n"{{ID}}_Activate")
      && Equals(ListenerAction.GetType(action), gameinputActionType.BUTTON_PRESSED) {
    FTLog(s"[{{ID}}] activate pressed");
  }
  return wrappedMethod(action, consumer);
}
