# Vehicles (new drivable cars and bikes)

A new player car is an ArchiveXL + TweakXL mod: an `.archive` with meshes, rigs,
an entity (`.ent`), an appearance file (`.app`) and collision (`.phys`), plus a
TweakXL record that points the game at the entity. Build it in the order below
and check each step before the next.

Source of these notes: a complete car build on game 2.5 with WolvenKit CLI 9.1,
ArchiveXL 1.28, TweakXL 1.12 and Blender 5, on the Archer Hella as the base car.
Every rule was checked with tool output (WolvenKit round trips, mesh and bbox
comparisons, `cpforge` checks). In game the car summons, shows its paints,
headlights, light bar, plate and taillights, opens its doors on the new hinges,
deforms in crashes, and sits with its wheels centred in the arches after the
animset fix in section 4 (CET probe: wheels at x 0.799/0.798, y 1.423/1.422,
matching the rig). Doors animate on the car's own animset; hood, trunk and
window animation on it is not verified yet. Confirm against your own base car
before relying on a number.

## 1. Pipeline

1. Pick a vanilla base car and extract it (ent, app, rigs, anims, meshes, phys).
2. Put the source model in Blender in the vehicle frame; measure wheels, hinges,
   seats and the steering column.
3. Group parts into components (one `.mesh` each) on the base car's layout.
4. Write the two rigs (deformation and wheel physics) from the measurements.
5. Export one glb per component in its bone's local frame; import each onto a
   copied vanilla mesh.
6. Textures, masks, mlsetups, materials, appearances (each paint, plus burnt).
7. `.app` (components, lights, proxy), `.ent` (rigs, collision, appearances),
   `.phys` collision.
8. TweakXL records, localization, UI atlas, dealer listing.
9. `cpforge build`, `cpforge res check`, `cpforge check`, `cpforge package`,
   then test in game.

## 2. Base car and extraction

- Choose by body style and drivetrain (`cpforge tweak show Vehicle.<car>_player`).
  A sedan base gives occupant slots, workspots, cameras and destruction for
  four doors.
- `cpforge archive find <path> --vanilla` names the archive; extract with
  `WolvenKit.CLI unbundle <content dir> -r <regex>`. In the regex use `.` for
  path separators: backslashes break the CLI's regex parser.
- Reference glbs: `uncook --mesh-export-type MeshOnly`. `WithRig` fails on
  material export in 9.1.
- Wheel-physics rigs are named by size,
  `base\vehicles\base_rig\v_base_x4_<wheelbase cm>_<track cm>_<n>` (ep1 adds
  more). Copy the closest.

## 3. Frame and mesh conventions

- Vehicle frame: Z up, +Y forward, driver side -X. Wheel centres at z 0; the
  `Base` bone sits 0.44 m above them on the Hella; ground at z = -tyre radius.
  Sources from other games often face -Y: rotate 180 degrees about Z.
- Part meshes are unskinned (no bone names) and authored in the local frame of
  the bone they hang on: body, glass, interior and lights on `Base`; doors at the
  hinge; hood at its rear edge; trunk at its front edge; bumpers at their left
  corner bone (`bumper_front_b`). Mirrors and window glass follow their door or
  window bone.
- The chassis/suspension mesh is skinned (`entSkinnedMeshComponent`, bound to
  `deformation_rig`) and authored in model space; its bones are Base, wheel_*,
  swingarm_*, break_*.
- The distance proxy mesh is in model space, not slot-bound.
- `vehicle_slots` maps slot to bone mostly one to one, except
  `bumper_front` -> `bumper_front_b`, `bumper_back` -> `bumper_back_b`,
  `brake_back_*` -> `swingarm_back_*`, `brake_front_*` -> `break_front_*`.

## 4. Rigs

- Two rigs: `deformation_rig` (all parts; 51 bones on the Hella) and
  `vehicle_rig` (wheel physics; 17 bones). Set suspension positions identically
  in both and keep the `Base` height.
- Edit only `boneTransforms` (parent-relative) and keep bone names and order, so
  the base car's animations and animgraphs still map. Round-trip the rig through
  WolvenKit (`cpforge res roundtrip`); the size must stay equal to vanilla.
- The Hella door, hood, trunk and window clips are additive (deltas), so they
  swing around your new hinge positions and the animation data needs no
  changes. Clip angles: doors 70 degrees about local Z, hood +49.5 and trunk
  -59.9 about local X. Pose the parts at those angles in Blender to look for
  clipping.
- But ship your own copy of the base car's `.anims` with its root `rig` set to
  your deformation rig (the data stays the same). The vanilla set names the base
  car's rig, and `default_car_anim_graph` pulls the `vehicle_rig` bones in
  through an additive pose built against that rig: the game then draws the
  wheels at 2 x your suspension position minus the base car's, on the bones the
  two rigs share. Verified in game: a 2.845 m wheelbase on the Hella (2.86 m
  rig, suspension at 1.685) rendered at 2.32 m until the animset was copied.
  Every vanilla car pairs its own `.anims` with its own deformation rig.
  Repoint `animSet` in both `entAnimatedComponent`s (`vehicle_rig` and
  `deformation_rig`), update the `.ent` `resolvedDependencies`, and give
  `animations.hash` (the `animAnimSetup` hash on both components) a unique
  value: vanilla changes it per animset, and it is not a plain path hash, so
  reusing the base car's value risks a shared cached setup.
  `cpforge res check <car>.ent` warns about this pairing (`RES-ENT-ANIMSET-RIG`).
- Steering: `steering_wheel_zro` carries the column tilt (local +Y along the
  column, rotation Rx(-tilt)); `steering_wheel` counter-rotates so the wheel
  mesh stays model-aligned. Measure the tilt from the rim (PCA).
- Occupants sit on the `seat_*` bones; place them with the base car's
  bone-to-cushion and backrest offsets.

## 5. Meshes: glb rules and import

- One node per submesh named `submesh_XX_LOD_1`, one material per submesh, at
  most 65k vertices per submesh.
- glTF space: game (x, y, z) -> glTF (x, z, -y); UV origin top-left; provide
  TEXCOORD_0 and TEXCOORD_1.
- TANGENT w: WolvenKit stores w = -(glTF spec sign); write the negated sign or
  normal maps light from the wrong side.
- COLOR_0: white on normal parts; light submeshes carry the light zone in R
  only; tyres all zero.
- Import: copy a vanilla vehicle mesh as the container, put the glb at the
  mirrored raw path, run `WolvenKit.CLI import <raw root> -o <archive root> -k`.
  Static parts: any unskinned vanilla part mesh; chassis: the vanilla chassis.
- Skinned imports: joints carry the bones' model transforms (flat hierarchy).
  If every matching joint has identity rotation, WolvenKit keeps the container's
  old bind matrices and the parts land in the wrong place without an error; a
  rotated joint (right wheels, 180 degrees about Z) makes it rebuild them. Check
  `boneRigMatrices` after import.
- The CLI exits non-zero when a folder has no mesh buffers even though
  everything imported: read the "Imported N/N" line, not the exit code.

## 6. Materials

- Vanilla bases: paint and trim
  `base\vehicles\common\materials\multilayer_vehicle_destruction.mi` (deforms
  with damage; `CoatLayerMin/Max` pick the clear-coated layers); lights
  `vehicle_lights.mi` (`Zone0..3EmissiveEV`); glass `glass_windshield.mi`,
  `glass_exterior_generic.mi`, `glass_lightcovers.mi`; burnt `burnt_ext.mi`,
  `burnt_int.mi`; small flat parts `engine\materials\metal_base.remt`.
- Write materials as `preloadLocalMaterialInstances` (`{HandleId, Data:
  CMaterialInstance}`) with `localMaterialBuffer` emptied: it round-trips
  exactly, and vanilla wheels, wipers and lights do the same. Value types:
  `rRef:Multilayer_Mask`, `rRef:Multilayer_Setup`, `rRef:ITexture`, `Float`,
  `Vector4`, `Color`.
- `appearances[].Data.chunkMaterials`: one material name per submesh. Give
  every mesh the same appearance names (default, each paint, burnt) so the
  `.app` can use one meshAppearance name for all components.
- Single-layer mlsetups on one all-white mask give clean surfaces whatever the
  source UVs. Take colour names from each mltemplate's own colour table; for
  exact paint colours append entries to a copy of `car_paint_metallic_01`.
- Masks: a `.masklist` lists one R8 image path per line; a white layer 0 is
  added unless the first file ends in `_0`. The layer images next to it are
  skipped by `import -k` ("No existing redfile"); that is expected.
- Textures: copy a vanilla `.xbm` with the right setup to the target path
  (colour `TCM_QualityColor`/sRGB, normal `TCM_Normalmap`, UI
  `TCM_DXTAlpha`/`TEXG_Generic_UI`/sRGB) and `import -k` the PNG over it.

## 7. Lights

- Emission comes from `vehicle_lights` submeshes: zone = floor(vertex colour R
  x 4); vanilla R values 0.202 / 0.397 / 0.597 / 0.799 for zones 0-3. Each mesh
  has four zones.
- One `vehicleLightComponent` per zone: `parentTransform` bound to the mesh
  component, `materialZone` Zero..Three, `lightType` (Head, Brake,
  LeftBlinker, RightBlinker, Reverse, Interior, Utility; bits 1 to 64), and
  `localTransform` in the mesh's frame (use the zone's vertex centroid).
- Spot lights throw light (heads, brakes, fog): copy the vanilla head and brake
  components, their orientation is right. Point lights only glow (DRL,
  blinkers, centre brake, reverse): copy the vanilla position and reverse
  components (`emissiveOnly`).
- Lights name a `colliderName`; keep the vanilla `entColliderComponent`s and
  rebind them to your lights.
- `cpforge res inspect <file.app>` lists every light with its type, zone and
  binding.

## 8. Entity and appearance files

- The game reads components from `compiledData.Data.Chunks`; `CruidDict` maps
  every chunk index to that chunk's component `id` (in the `.ent`, chunk 0 is the
  vehicle object and maps to `0`). Keep the `components` list identical to the
  chunks.
- `.ent`: chunk 0 references the component chunks, so edit components in place
  (rig paths, `vehicleChassisComponent.collisionResource`, FX and skid slot
  positions); replace `appearances`, `defaultAppearance`,
  `resolvedDependencies`.
- Drop vanilla parts the new model replaces: the shared `fuelport_standard`
  ring clips through a modelled fuel door.
- `.app`: rebuild each appearance from a vanilla one: copy components with
  fresh inline handles and unique `id`s, rebuild the chunks and CruidDict, set the
  visual controller's `appearanceDependency` and `meshProxy`, the proxy
  component and `proxyMesh`, and empty resolved and loose dependencies and the
  parts lists.
- WolvenKit JSON handle ids are document-wide: a `HandleRefId` can point into an
  earlier appearance's compiledData. A repeated `HandleId`, or a repeated
  compiledData `BufferId` (vanilla numbers them 0..n per file), makes
  `convert deserialize` fail with "could not be converted to RedFileDto".
- An empty uint64 ResourcePath is the string `"0"`, not the number 0.
- `cpforge res check` reports all of the above before you run WolvenKit.

## 9. Collision (.phys)

- The Hella interaction collider is convex hulls plus a box, with
  `compiledGeometryBuffer` null (cooked at load).
- An affine per-axis fit from the base car's body extents to the new body's
  keeps every hull convex and its index buffers valid; scale box centres and
  half extents the same way. Frame: the chassis component's localTransform
  (z 0.5 on the Hella).

## 10. TweakXL, localization, UI

- `$base: Vehicle.<base>_player`; set `entityTemplatePath`, `appearanceName`,
  `destroyedAppearance`, `displayName`, `manufacturer`, `vehicleUIData`, `icon`,
  `player_audio_resource`, `headlightColor` and the wheel sizes.
- Override inline sub-records with `$base` on their real names; look them up,
  never guess (`cpforge tweak search <car>_inline`, `cpforge tweak show`). On the
  Hella: inline0 wheel setup, inline1/2 front and back presets, inline3 data
  package, inline4 UI data, inline5 engine data.
- Wheel sizes come from `vehWheelDimensionsSetup` (tireRadius, rimRadius,
  tireWidth, wheelOffset), not from rig scale.
- The manufacturer logo is looked up as `UIIcon.<enumName>`; `productionYear` is
  a plain string.
- Without a CrystalCoat setup, set `hasVisualCustomization: False` and ship
  fixed paint variants.
- Make it a player car: `Vehicle.vehicle_list.list: [!append Vehicle.<id>]`
  (`Vehicle.vehicle_list` lives in the vanilla `.tweak` sources, not in
  tweakdb.bin; `cpforge tweak exists` and `check` know this).
- Virtual Car Dealer fields: `dealerPrice`, `dealerCred`, `dealerAtlasPath`,
  `dealerPartName`, `dealerVariants`.
- Localization: a JsonResource whose root holds
  `localizationPersistenceOnScreenEntries.entries[{femaleVariant, maleVariant "",
  primaryKey "0", secondaryKey}]`, loaded from the `.archive.xl`
  `localization: onscreens:` block.
- inkatlas: `inkTextureAtlas` with `slots.Elements[3]` (4K, 1080p, 720p), each
  with `parts[{partName, clippingRectInUVCoords}]`.

## 11. Measuring in game (CET)

Files can all agree and the game can still draw something else; measure where
the slots actually are. With the car mounted or looked at, in the CET console:

```lua
local p = Game.GetPlayer()
local v = Game.GetMountedVehicle(p) or Game.GetTargetingSystem():GetLookAtObject(p, false, false)
local s = v:FindComponentByName(CName.new("vehicle_slots"))
local o, F, R, U = v:GetWorldPosition(), v:GetWorldForward(), v:GetWorldRight(), v:GetWorldUp()
local function dot(a, b) return a.x * b.x + a.y * b.y + a.z * b.z end
for _, n in ipairs({"wheel_front_left", "wheel_front_right", "wheel_back_left", "wheel_back_right",
                    "Base", "bumper_front", "bumper_back", "trunk_a"}) do
  local ok, wt = s:GetSlotTransform(CName.new(n))
  local w = WorldPosition.ToVector4(WorldTransform.GetWorldPosition(wt))
  local d = Vector4.new(w.x - o.x, w.y - o.y, w.z - o.z, 0)
  print(string.format("%-18s x=%.3f y=%.3f z=%.3f", n, dot(d, R), dot(d, F), dot(d, U)))
end
```

- If `WorldPosition.ToVector4` is not available in your CET build, read the
  FixedPoint position directly: `wt.Position.x.Bits / 131072` (17 fractional
  bits), same for y and z.
- CET hands `out` parameters back as extra return values:
  `GetSlotTransform(name)` returns `ok, WorldTransform`. Passing a transform in
  fails with "requires 1 parameter(s)".
- Output is in the car's own frame (x right, y forward, z up). Compare with the
  rig values. Body slots (Base, bumpers, trunk) printed next to the wheels tell a
  wheel-only shift from a whole-frame shift.
- `vehicle_slots` hangs on the deformation rig, so these are where the meshes
  are drawn.
- The applied wheel sizes: `TweakDB:GetRecord(v:GetRecordID()):VehWheelDimensionsSetup()`,
  then `FrontPreset()` / `BackPreset()` and `WheelOffset()`, `TireRadius()`,
  `TireWidth()`.

## 12. Pitfalls (symptom -> cause -> fix)

| Symptom | Cause | Fix |
|---|---|---|
| Steering column tilts upward | Torque/BeamNG quaternions are stored inverted | transpose the rotation |
| Doors would swing through the body | mesh authored around the base car's hinge | author parts in the new hinge's frame, move the bone in the rig |
| Hubs and brakes 25 cm off after import | skin joints all identity, old bind matrices kept | include real joint rotations (right wheels), check `boneRigMatrices` |
| Wipers zig-zag up the glass | "lowest vertex per slice" on a coarse mesh | follow the glass's open boundary |
| Face materials lost when regrouping in Blender | `materials.clear()` resets face indices | read the indices first |
| Paint previews washed out | AgX view transform and a bright world on metallic paint | Standard view transform |
| Wrong inline record used for engine data | guessed name | look it up with `cpforge tweak show` |
| `.app` will not deserialize with several appearances | repeated handles or BufferId | re-id per appearance (`cpforge res check` names it) |
| Wheels too close together (or too far apart) in game, body fine | base car's `.anims` still names the base car's rig | own `.anims` copy with `rig` = your deformation rig, unique `animations.hash` (`cpforge res check` names it) |
| Fuel-port ring pokes through the body | vanilla `fuelport_standard` component kept beside a modelled fuel door | remove that component |
| CET probe errors "requires 1 parameter(s)" | `out` parameter passed in | take it as the second return value |

## 13. Forge commands for vehicle work

- `cpforge plan "<car request>"` routes to these notes and the steps.
- `cpforge doctor` shows the WolvenKit CLI it found (PATH, `WOLVENKIT_CLI`, the
  dotnet tools folder or the Reverse THIS! kit folder).
- `cpforge res check <files>`: handle, BufferId, ResourcePath, CruidDict,
  components-vs-chunks and mesh material rules on `.mesh`, `.app`, `.ent` (CR2W
  or WolvenKit JSON), and every referenced resource looked up in the project's
  `source/archive` and the game's archives. On an `.ent` it reads the project's
  own `.anims` and checks that each animset embeds the `deformation_rig`
  component's rig and is listed in `resolvedDependencies`.
- `cpforge res inspect <files>`: the same plus components, meshes, lights,
  slots and proxy per appearance.
- `cpforge res roundtrip <files>`: CR2W -> JSON -> CR2W must give the same bytes
  (or JSON -> CR2W -> JSON the same data).
- `cpforge check`: `TWEAK-RESOURCE` for resource paths in tweaks that exist
  nowhere, `VEHICLE-NOT-LISTED` for a player car missing from
  `Vehicle.vehicle_list`.
- `cpforge build` packs the archive; `cpforge package` makes the release zip.
