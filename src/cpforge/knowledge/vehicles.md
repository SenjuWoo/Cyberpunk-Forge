# Vehicles (new drivable cars and bikes)

A new player car is an ArchiveXL + TweakXL mod: an `.archive` with meshes,
rigs, an entity (`.ent`) and appearance (`.app`), and a TweakXL record that
points the game at the entity. Plan for a full car as several steps, each
checked before the next: source model, scene in the game frame, components and
rigs, meshes and materials, entity/appearance/lights, record and listing.

Facts below were read from vanilla 2.5 files (the Archer Hella was the
reference car) and WolvenKit 9.1 CLI round trips in a real vehicle project.
Verify against your own reference car with WolvenKit before relying on one.

## Start from a vanilla car of the same class

- Copy, don't author from zero: a vanilla car of the same layout (doors,
  sedan/coupe, 4 wheels) gives the bone names, animations and animgraphs.
- Keep bone names and order identical to the reference rig. The door, hood,
  trunk and window clips of the Hella are additive (deltas), so the vanilla
  `.anims` (`base\animations\vehicle\standard\vehicle\v_standard2_archer_hella.anims`)
  drive a new car whose pivots are set correctly; no custom animation needed.
- Wheel physics comes from a base rig in `ep1\vehicles\base_rig\`; names encode
  wheelbase and track, e.g. `v_base_x4_286_164_40` = 2.86 m wheelbase, 1.64 m
  track. Pick the closest, copy it, set the exact values.

## Frame and pivots

- Model frame: wheel centre at z 0, wheelbase centred on y, front = +y.
  Sources from other games often face -y: rotate 180 degrees about z.
- Part meshes are unskinned (no bone names). Each mesh sits in the local frame
  of the bone or slot it attaches to: body verts are Base-local (the Base bone is
  0.44 m above the wheel centre on the Hella), doors hinge-local, hood
  rear-edge-local, a bumper local to its corner bone (`bumper_front_b`).
- The skinned chassis mesh is in model space (wheel centre z 0).
- Measure pivots in the source model (hinge axes, wheel centres, steering hub
  and column angle, seat position) and write them into copies of the
  deformation and vehicle rigs. Check by posing at the clip angles (doors
  about 70 degrees, hood about 50, trunk about -60) and looking for clipping.

## Meshes

- Submesh names `submesh_XX_LOD_1`; two UV sets and a vertex colour per mesh.
- Vertex colour is white on normal surfaces and all zero on tyres.
- Lights: material `vehicle_lights.mi`; the light zone is in the red channel
  only, zone = floor(R * 4) (R 0.202 / 0.397 / 0.597 / 0.799 for zones 0-3).
  Each light component in the appearance has a zone and a `lightType` bit mask:
  Head 1, Brake 2, LeftBlinker 4, RightBlinker 8, Reverse 16, Interior 32,
  Utility 64.
- Import geometry onto a copied vanilla mesh: `WolvenKit.CLI import --keep`
  keeps the target's material setup. Textures: copy a vanilla colour, normal or
  data `.xbm` as the target and import over it so the encoding matches.
- Tangents: WolvenKit stores the tangent sign negated relative to the glTF
  spec (w = -sign); a glb writer must flip it or normal maps light from the
  wrong side.
- Mesh export from game files: `uncook --mesh-export-type MeshOnly`. `WithRig`
  failed on material export in WolvenKit 9.1.

## Materials

- Paint and trims: `multilayer_vehicle_destruction.mi` (deforms with damage),
  driven by an `.mlsetup` and a mask (`.mlmask`, built from a `.masklist`: one
  R8 image path per line; a white layer 0 is added unless the first file ends in
  `_0`).
- Glass: `glass_windshield.mi`, `glass_exterior_generic.mi`,
  `glass_lightcovers.mi`. Small flat parts: `metal_base.remt` with scale params.
- In mesh JSON (WolvenKit 9.1 `convert serialize`), per-mesh materials can live
  in `preloadLocalMaterialInstances` (handles with a `CMaterialInstance`:
  `baseMaterial {DepotPath, Flags}` and `values`), with `localMaterialBuffer`
  emptied; vanilla wheels, wipers and lights do this, and it round-trips exactly
  through deserialize/serialize. `appearances` map a `chunkMaterials` name per
  submesh; one appearance per paint, plus a burnt one.

## Still to document

Entity and appearance layout, light components in the `.app`, shadow meshes,
proxy, burnt appearance, the TweakXL vehicle record and the Vehicle Call
Down (VCD) listing, icons and localization. These come from the vehicle
project as it reaches them.

## Forge steps

- `cpforge new "<Car>" --kind archivexl` for the project, resources under
  `source/archive/`.
- `cpforge doctor` shows whether WolvenKit CLI was found (PATH, `WOLVENKIT_CLI`,
  or a known install folder).
- `cpforge build` packs the archive; `cpforge check` verifies that the
  `.archive.xl` paths are inside it and checks the vehicle record in
  `r6/tweaks` (`$base` and references against TweakDB).
- `cpforge archive find <vanilla path> --vanilla` finds which game archive
  holds a reference file to copy.
