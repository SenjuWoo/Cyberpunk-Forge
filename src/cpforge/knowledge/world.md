# World, NPCs, quests

What worked in shipped mods (look every name up with `cpforge api` first):

- Spawning: Codeware `DynamicEntitySystem` with tags, so you can find and
  delete your entities later. Clean them up on session end; do not leave
  spawned NPCs in saves.
- Placement: pick points on the human navmesh (`NavigationSystem`,
  `FindPointInSphereOnlyHumanNavmesh`) rather than raw coordinates.
- Map pins: `MappinSystem` (quest static mappin data for a pin, a custom
  position variant for GPS routing).
- Real story NPCs: find them with a target search (`TSQ_NPC()` with
  `GetTargetParts`) and meet them where they are; commanding story NPCs breaks
  their AI.
- Followers: `AIFollowTargetCommand`.
- Vehicles: `VehicleComponent.GetVehicle`, `GetVehiclePS().UnlockAllVehDoors()`.
- World state for context: `PreventionSystem` heat (`GetHeatStageAsInt`),
  `WeatherSystem` (`GetWeatherState().name`), fast-travel node transforms.
- Sector edits (remove or move placed objects): ArchiveXL `streaming:` blocks
  and sector patches, authored in WolvenKit.
- Story facts (`GameInstance.GetQuestsSystem(...).GetFact(n"name")`) tell you
  where the player is in the story; romance facts follow the pattern
  `sq0xx_<name>_lover`.

Test in a throwaway save. Runtime behaviour is the only proof here; a clean
compile says nothing about AI or streaming.
